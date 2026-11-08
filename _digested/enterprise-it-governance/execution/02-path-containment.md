---



title: "路径防穿透"
description: '六层叠加的路径防护、每层的真实实现位置与边界，以及一个容易被忽略的事实：CWD 注入用的是分号而不是 &&。'
topics: [governance, execution]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 路径防穿透

防路径穿越不是一层，是**六层叠加**。
本页列出每层的真实实现与它挡不住的情况。

## 1. 六层防护

| 层 | 位置 | 机制 |
|----|------|------|
| **1. 虚拟路径体系** | `sandbox/local/local_sandbox.py:263`（`class PathMapping`） | agent 主要看到 `/mnt/user-data/{workspace,uploads,outputs}`；还映射 `/mnt/skills`（只读）与 `/mnt/acp-workspace`（`local_sandbox_provider.py:138-182`） |
| **2. 工具层路径翻译** | `backend/packages/harness/deerflow/sandbox/tools.py:754`（`replace_virtual_path`） | 每个文件工具把虚拟路径转成宿主路径 |
| **3. `allow_host_bash` 开关** | `sandbox/security.py:35`（`is_host_bash_allowed`） | Local 模式下默认**禁止**宿主 bash |
| **4. CWD 注入** | `backend/packages/harness/deerflow/sandbox/tools.py:2917` | 命令前注入 `cd {VIRTUAL_PATH_PREFIX}/workspace;` |
| **5. 路径参数校验** | 各 tool 实现 | 拒绝 `..`、系统绝对路径、符号链接逃逸 |
| **6. 输出路径脱敏** | `backend/packages/harness/deerflow/sandbox/tools.py:862`（`mask_local_paths_in_output`） | 宿主路径意外出现在输出中时替换回虚拟路径 |

前六层的顺序是有意义的：**进入时逐层收窄，输出时再擦一遍**。

## 2. 第 4 层的一个细节：分号不是 &&

`backend/packages/harness/deerflow/sandbox/tools.py:2917` 的实际注入是：

```python
command = f"cd {VIRTUAL_PATH_PREFIX}/workspace; {command}"
```

用的是 **`;`**（无论 cd 成功与否都继续执行），不是 `&&`。

| 写法 | 语义 | 后果 |
|---|---|---|
| `cd X && cmd` | cd 失败则**不执行** cmd | 更严格 |
| **`cd X; cmd`（实际）** | cd 失败也**继续执行** cmd | 若 workspace 不存在且未被 `ensure_thread_directories_exist` 创建，命令在**原 CWD** 执行 |

**这不是漏洞，但改变了防线的作用方式**：
第 4 层保证的是「默认工作目录」，而不是「命令被限制在 workspace 内」。
真正限制目录的是第 1、2 层（虚拟挂载）与**文件工具**的第 5 层；
bash 不经过第 5 层，只受第 1 层挂载替换和 SandboxAudit 正则约束。

## 3. 第 6 层：为什么要擦输出

即使有前五层，宿主路径仍可能通过多种渠道泄露：

| 渠道 | 例子 |
|---|---|
| 工具的报错信息 | `FileNotFoundError: /Users/x/deer-flow/.deer-flow/...` |
| `pwd` / `realpath` 的输出 | agent 主动查询 |
| 第三方工具打印的路径 | `git status` 的绝对路径 |

`mask_local_paths_in_output`（`backend/packages/harness/deerflow/sandbox/tools.py:862`）按已知前缀做正则替换，
详见 [../data/02-redaction.md](../data/02-redaction.md)。

**这一层的定位**：它不阻止访问，只阻止「知道真实路径」。
对提示注入场景有用——攻击者拿不到可用于构造下一跳的真实路径。

## 4. Bash 子命令审计

SandboxAuditMiddleware 先对**整条命令**做 high-risk 扫描，再按 `&&` / `||` / `;`
（以及管道 `|`）切分后逐条匹配，防止用 `ls /safe/path && rm -rf /` 这种拼接绕过。
（`_classify_command` 的两遍逻辑见 `sandbox_audit_middleware.py:425-433`。）

`_classify_command`（`sandbox_audit_middleware.py:414`）的短路逻辑：
一旦某条子命令判定为 `block`，整个命令就被拒，不再看后续
（`:437-438` 的注释："can't get worse"）。

展开见 [../audit/03-sandbox-audit.md](../audit/03-sandbox-audit.md)。

## 5. 六层之后仍然存在的路径

| 场景 | 是否被挡 |
|---|---|
| `cat /etc/passwd` | **不挡**——第 5 层只校验文件工具的 path 参数；bash 不走它（`sandbox/tools.py:1019`、`local_sandbox.py:706-738`） |
| `cat ../../../../etc/passwd` | **不挡**——`..` 只在文件工具参数校验；bash 的 `..` 原样交给 shell。Local + `allow_host_bash: true` 时可越出 thread 目录 |
| 符号链接指向外部 | **取决于实现**——第 5 层声明拒绝，实际覆盖需实测 |
| 通过 `bash -c` 执行未分类命令 | **可能漏**（正则盲区） |
| 通过 Python 代码读写任意路径 | **可能漏**——这是沙箱模式的根本边界 |
| workspace 不存在时的相对路径命令 | **第 4 层失效**（见 §2） |

**第五行是本质**：只要 agent 能执行任意代码（`python -c`、`bash -c`），
路径校验就只能在「工具参数」这一层生效，拦不住代码内部的读写。
真正隔离任意代码执行要靠沙箱后端（见 [01-sandbox-modes.md](01-sandbox-modes.md)）。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 代码内部路径访问的控制 | **无** | 只在工具参数层校验，拦不住 `python -c` 内部读写 |
| 符号链接逃逸的完整覆盖 | **有但不覆盖** | 声明拒绝，实际覆盖范围需逐工具实测 |
| CWD 注入的失败保护 | **部分** | 用 `;` 而非 `&&`，cd 失败仍执行 |
| 正则盲区的运行时披露 | **无** | 盲区只写在代码注释里（`:49-51`） |
| 跨 thread 的路径隔离（Local 模式） | **有但不覆盖** | 目录分开，但同进程可互相访问 |

## 7. 与其他章节的关系

- 沙箱模式与隔离强度：[01-sandbox-modes.md](01-sandbox-modes.md)
- 命令审计细节：[../audit/03-sandbox-audit.md](../audit/03-sandbox-audit.md)
- 输出脱敏：[../data/02-redaction.md](../data/02-redaction.md)
- 存储布局：[../data/01-storage-and-isolation.md](../data/01-storage-and-isolation.md)
