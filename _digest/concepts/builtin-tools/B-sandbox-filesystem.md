---
title: "B. 沙箱 / 文件系统"
description: "全部定义在 `packages/harness/deerflow/sandbox/tools.py`，通过 `config.yaml` 的 `tools[]` 段加载。默认配置标配全部 7 个。"
topics: [tools, builtin, sandbox-tools]
---

# B. 沙箱 / 文件系统

全部定义在 `packages/harness/deerflow/sandbox/tools.py`，通过 `config.yaml` 的 `tools[]` 段加载。默认配置标配全部 7 个。

统一特征：
- 第一个参数始终是 `runtime: Runtime`（注入 thread state/sandbox 引用）
- 第二个参数始终是 `description: str`（LLM 解释为什么要做这个操作，用于日志/审计）
- 本地沙箱模式下有虚拟路径 → 宿主机路径翻译
- 所有写操作（`write_file`, `str_replace`）有 `(sandbox_id, path)` 粒度的文件锁
- 错误统一返回 `"Error: ..."` 字符串，不会抛异常破坏 Agent 执行流

---

## bash

**源码**: `sandbox/tools.py:1328`
**Tool Name**: `bash`
**Tool Group**: `bash`

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 为什么要跑这个命令（短词） |
| `command` | `str` | 要执行的 bash 命令 |

### 执行流程（本地沙箱模式）

1. `ensure_sandbox_initialized(runtime)` — 懒获取/创建 sandbox
2. 检查 `allow_host_bash` — 默认禁用本地 bash，返回错误提示
3. `ensure_thread_directories_exist(runtime)` — 确保 workspace/uploads/outputs 目录存在（只创建一次，`thread_directories_created` flag）
4. `validate_local_bash_command_paths(command, thread_data)` — **安全扫描**（见下）
5. `replace_virtual_paths_in_command(command, thread_data)` — `/mnt/user-data/` → 宿主机路径
6. `_apply_cwd_prefix(command, thread_data)` — 在命令前加 `cd <workspace> &&`
7. `sandbox.execute_command(command)` → 执行
8. `mask_local_paths_in_output(output, thread_data)` — 输出中掩码宿主机路径回虚拟路径
9. `_truncate_bash_output(output, max_chars)` — 中间截断（头尾各 50%）

### 安全扫描详解

`validate_local_bash_command_paths()` 对命令做以下检查：

- **拒绝 `file://` URL**: 防止绕过绝对路径正则的本地文件渗透
- **拒绝 `..` 路径穿越**: 用正则 `/\.\./` 检查
- **绝对路径白名单**: 只允许：
  - `/mnt/user-data/*` — 线程工作目录
  - `/mnt/skills/*` — 技能目录
  - `/mnt/acp-workspace/*` — ACP 工作区
  - 配置的 custom mount 路径
  - 系统路径前缀 (`/bin/`, `/usr/bin/`, `/usr/sbin/`, `/sbin/`, `/opt/homebrew/bin/`, `/dev/`)
  - MCP filesystem server 配置的路径
- **`cd`/`pushd` 目标校验**: 不允许跳转到 `$VAR`、`` `cmd` ``、`~`、未允许的绝对路径
- **root-path 命令限制**: `cat`, `ls`, `find`, `grep`, `sed`, `rm`, `cp`, `mv` 等命令不允许使用 `/` 根路径
- **命令替换注入**: 拒绝 `$(...cd...)`、`$(...pushd...)`

### 输出截断

默认 20,000 chars，中间截断（头和尾各保留约 50%），因为 stderr/stdout 的先后顺序不确定，错误可能出现在任意位置：

```python
# 截断标记格式
"... [middle truncated: {skipped} chars skipped] ..."
```

### 异步路径

`bash_tool.coroutine = _bash_tool_async` — 对 AIO sandbox（Docker），先异步初始化 sandbox，再到线程池执行同步工具体。

---

## ls

**源码**: `sandbox/tools.py:1384`
**Tool Name**: `ls`
**Tool Group**: `file:read`

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 为什么列出这个目录 |
| `path` | `str` | 要列出的目录绝对路径 |

### 行为

- 调用 `sandbox.list_dir(path)` → 返回 tree 格式列表，最大 2 层深度
- 本地模式下先 `validate_local_tool_path(path, read_only=True)` 校验路径
- 允许读取 `/mnt/skills/`、`/mnt/acp-workspace/`、custom mount（read_only）
- 输出头部截断（默认 20,000 chars），保留文件列表的顶部

### 输出格式

```
dir/
├── file1.py
├── file2.py
└── subdir/
    └── file3.py
```

空目录返回 `(empty)`。

---

## read_file

**源码**: `sandbox/tools.py:1606`
**Tool Name**: `read_file`
**Tool Group**: `file:read`

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 为什么读这个文件 |
| `path` | `str` | 文件绝对路径 |
| `start_line` | `int \| None` | 起始行号（1-indexed，含） |
| `end_line` | `int \| None` | 结束行号（1-indexed，含） |

### 行为

- 行范围切割在 truncation 之前执行
- 空文件返回 `(empty)`
- 输出头部截断（默认 50,000 chars），因为代码/文档从头读

### 特殊处理：LoopDetectionMiddleware

```python
# LoopDetectionMiddleware treats read_file calls in 200-line buckets
```

`read_file` 被 `LoopDetectionMiddleware` 特殊对待——按 200 行 bucket 粒度计数，避免 Agent 逐行读大文件时被误判为死循环。

---

## write_file

**源码**: `sandbox/tools.py:1674`
**Tool Name**: `write_file`
**Tool Group**: `file:write`

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 为什么写这个文件 |
| `path` | `str` | 文件绝对路径 |
| `content` | `str` | 要写入的内容 |
| `append` | `bool` | 是否追加（默认 `False`=覆盖） |

### 行为

- 本地模式下先 `validate_local_tool_path(path)` 校验（不允许写 `/mnt/skills/`、`/mnt/acp-workspace/` 和 read-only mount）
- 自动创建父目录（sandbox 内部处理）
- `append=True` → 在文件末尾追加
- `append=False` → 覆盖写入
- 成功返回 `"OK"`

### 并发安全

```python
with get_file_operation_lock(sandbox, path):
    sandbox.write_file(path, content, append)
```

`file_operation_lock` 对 `(sandbox_id, path)` 粒度的锁，同一进程内并发写同一文件串行化。不同 sandbox 不互锁。

### 错误处理

错误信息包含请求路径 + 截断后的错误详情（最大 2000 chars），避免泄露宿主机路径。

---

## str_replace

**源码**: `sandbox/tools.py:1734`
**Tool Name**: `str_replace`
**Tool Group**: `file:write`

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 为什么替换 |
| `path` | `str` | 文件绝对路径 |
| `old_str` | `str` | 要被替换的子串 |
| `new_str` | `str` | 替换后的新子串 |
| `replace_all` | `bool` | 是否替换所有出现（默认 `False`=只替换第一次） |

### 行为

1. 读文件内容
2. 校验 `old_str` 在文件中存在 → 不存在返回 `"Error: String to replace not found"`
3. `replace_all=False`：`content.replace(old_str, new_str, 1)` — 只替换**第一次**出现
4. `replace_all=True`：`content.replace(old_str, new_str)` — 全部替换
5. 写回文件（同一并发锁保护）
6. 成功返回 `"OK"`

### "恰好一次"的契约

Tool description 告诉 LLM 在 `replace_all=False` 时 `old_str` 必须恰好出现一次，但代码**不检查出现次数**，仅检查是否存在后替换首次出现。这个约束是 prompt 层的契约，不是代码级的 enforcement。如果 LLM 遵守契约，它能避免误替换多处出现的字符串；如果 LLM 不遵守，代码也只会替换第一次出现，不会报错。

---

## glob

**源码**: `sandbox/tools.py:1438`
**Tool Name**: `glob`
**Tool Group**: `file:read`

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 为什么搜索 |
| `pattern` | `str` | glob 模式，如 `**/*.py` |
| `path` | `str` | 搜索的根目录绝对路径 |
| `include_dirs` | `bool` | 是否包含目录（默认 `False`） |
| `max_results` | `int` | 最大结果数（默认 200） |

### 结果限制

```python
_DEFAULT_GLOB_MAX_RESULTS = 200
_MAX_GLOB_MAX_RESULTS = 1000
```

硬上限 1000，通过 `_resolve_max_results()` 取 `min(requested, configured, hard_max)`。

### 输出格式

```
Found {N} paths under {path}
1. path/to/file1.py
2. path/to/file2.py
...
```
结果超出时附截断提示。

---

## grep

**源码**: `sandbox/tools.py:1510`
**Tool Name**: `grep`
**Tool Group**: `file:read`

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 为什么搜索内容 |
| `pattern` | `str` | 搜索的字符串或正则 |
| `path` | `str` | 搜索的根目录绝对路径 |
| `glob` | `str \| None` | 可选，文件名过滤如 `**/*.py` |
| `literal` | `bool` | 是否字面量匹配（默认 `False`=正则） |
| `case_sensitive` | `bool` | 是否大小写敏感（默认 `False`） |
| `max_results` | `int` | 最大结果数（默认 100） |

### 结果限制

```python
_DEFAULT_GREP_MAX_RESULTS = 100
_MAX_GREP_MAX_RESULTS = 500
```

硬上限 500。

### 输出格式

```
Found {N} matches under {path}
path/to/file.py:42: matching line content
path/to/file.py:87: another match
```

### 正则错误处理

`re.error` → 返回 `"Error: Invalid regex pattern: {e}"`，不会崩溃。
