## 核心结论

**DeerFlow 没有可安装的 `deerflow` CLI 二进制**，但有一套完整的命令行实验工具链。**SDD 协作完全可行**：custom mount + SOUL.md + SKILL.md + git via bash 就是一个完整的"项目目录即 agent 上下文"方案。

---

# Part A：命令行实验

## A.1 有什么可用的？

DeerFlow 没有 `console_scripts`、没有 `__main__.py`、没有 `pip install` 后能敲的 `deerflow` 命令。但它给了你三层命令行入口：

| 入口 | 启动方式 | 流式 | 适合 |
|------|---------|------|------|
| **debug.py REPL** | `cd backend && PYTHONPATH=. uv run python debug.py` | 否（阻塞式 ainvoke） | 断点调试、快速测试 |
| **DeerFlowClient Python REPL** | `python` 然后 `from deerflow.client import DeerFlowClient` | 是（`stream()` generator） | 程序化实验、检查内部事件 |
| **chat.sh** | `bash skills/public/claude-to-deerflow/scripts/chat.sh "问题"` | 是（SSE via curl） | 纯 shell 环境、脚本集成 |
| **status.sh** | `bash skills/public/claude-to-deerflow/scripts/status.sh [models/skills/agents/threads/memory]` | 不适用 | 查看资源状态 |
| **curl** | `curl -N -X POST localhost:8001/api/runs/stream ...` | 是（SSE） | 原始 HTTP 控制 |

## A.2 debug.py — 内置 REPL

源码：`backend/debug.py`（169 行）

```bash
cd backend && PYTHONPATH=. uv run python debug.py
```

特性：
- 使用 `prompt_toolkit.PromptSession` + `InMemoryHistory`（支持箭头键、Ctrl-R 搜索、彩色提示）
- 如果没有 prompt_toolkit，自动降级为 `input()`（`uv sync --group dev` 安装）
- 所有日志输出到 `debug.log`，终端保持干净
- 使用 `agent.ainvoke()` 而非流式——等待完整响应后一次性打印
- 显示 `present_files` 工具暴露的文件（含虚拟路径→物理路径转换）
- 输入 `quit` 或 `exit` 退出

可配置项（编辑脚本中的 `config` 字典）：

```python
config = {
    "configurable": {
        "thread_id": "debug-thread-001",
        "thinking_enabled": True,
        "is_plan_mode": True,
        "model_name": "kimi-k2.5",      # 取消注释来指定模型
    }
}
```

**注意**：它使用原始的 `make_lead_agent()` + 手动构建 `Runtime`，不走 `DeerFlowClient`。这意味着它最接近底层 agent 行为，适合源码级调试。

## A.3 DeerFlowClient Python REPL — 最灵活

源码：`deerflow/client.py:82-850`

```bash
cd backend && PYTHONPATH=. uv run python
```

```python
>>> from deerflow.client import DeerFlowClient
>>> client = DeerFlowClient()

# 快速一问一答（阻塞）
>>> client.chat("用 Python 写一个冒泡排序")
'当然，这里是冒泡排序的 Python 实现...'

# 流式实验 — 逐 token 输出，能看到每个 tool call
>>> for evt in client.stream("扫描 /mnt/user-data/workspace 下的所有 .md 文件"):
...     if evt.type == "messages-tuple":
...         t = evt.data.get("type")
...         if t == "ai" and evt.data.get("content"):
...             print(evt.data["content"], end="", flush=True)   # 实时逐 token
...         elif t == "ai" and evt.data.get("tool_calls"):
...             print(f"\n[调用工具: {[tc['name'] for tc in evt.data['tool_calls']]}]")
...         elif t == "tool":
...             print(f"\n[工具 {evt.data['name']}: {evt.data['content'][:200]}...]")
...     elif evt.type == "end":
...         print(f"\n[Token: {evt.data['usage']}]")

# 多轮对话（需要 checkpointer）
>>> from langgraph.checkpoint.memory import MemorySaver
>>> c2 = DeerFlowClient(checkpointer=MemorySaver())
>>> c2.chat("我的名字是 Alice", thread_id="test-1")
>>> c2.chat("我叫什么？", thread_id="test-1")
'你的名字是 Alice。'

# 查看环境信息
>>> client.list_models()       # 可用模型
>>> client.list_skills()       # 已启用的 skills
>>> client.get_mcp_config()    # MCP 服务器配置
>>> client.get_memory()        # 用户记忆
```

**这本质上就是一个 Python REPL**——你在 `>>>` 提示符下实时发送消息、观察返回、调整参数。`stream()` 给了你 token 级的可见性：你能看到 agent 什么时候决定调工具、调了什么、结果是什么。

## A.4 chat.sh — 纯 Shell CLI

源码：`skills/public/claude-to-deerflow/scripts/chat.sh`

```bash
# 一次性提问
bash skills/public/claude-to-deerflow/scripts/chat.sh "解释什么是递归"

# 多轮对话（传 thread_id）
bash chat.sh "你好，我叫 Alice"

# 四种模式
bash chat.sh "审查这段代码" "" pro     # flash | standard | pro | ultra
# flash:    无 thinking, 无 plan, 无 subagent（最快）
# standard: thinking, 无 plan, 无 subagent
# pro:      thinking + plan_mode（推荐）
# ultra:    thinking + plan_mode + subagent（全能力）
```

内部原理：curl + SSE，5 步流程——
1. 健康检查 Gateway
2. 自动创建或复用 thread
3. 根据 mode 构建请求体
4. SSE 流式读取
5. 解析最后一个 `values` 事件提取 AI 回复

## A.5 status.sh — 环境查看

源码：`skills/public/claude-to-deerflow/scripts/status.sh`

```bash
bash status.sh              # 健康检查 + 总览
bash status.sh models       # 列出所有模型
bash status.sh skills       # 列出所有 skills
bash status.sh agents       # 列出所有 agent
bash status.sh threads      # 列出最近的对话线程
bash status.sh memory       # 查看记忆内容
bash status.sh thread <id>  # 查看特定线程的对话历史
```

## A.6 curl — 原始 HTTP

```bash
# 需要先设置内部 auth token（本地测试用）
export DEER_FLOW_INTERNAL_AUTH_TOKEN=my-test-token

# 无状态流式聊天
curl -N -X POST http://localhost:8001/api/runs/stream \
  -H "Content-Type: application/json" \
  -H "X-DeerFlow-Internal-Token: my-test-token" \
  -d '{
    "input": {"messages": [{"role": "human", "content": "Hello"}]},
    "context": {"thinking_enabled": true}
  }'
```

> 完整 Gateway API 参考见 `_digest/app-layer/01-api-reference.md`。

## A.7 推荐实验路径

1. **先开 Web UI**（`localhost:2026`），选 flash 模式，随便聊几句感受 agent 行为
2. **开 `debug.py`** 或 **Python REPL + `DeerFlowClient.stream()`**，做带工作目录的实验（挂 custom mount、让 agent 读写文件）
3. 感觉摸清了 → 写 Python 脚本用 `DeerFlowClient` 做自动化

---

# Part B：SDD 项目目录协作

## B.1 核心机制：Custom Mount

SDD 的物理基础就一个东西——`config.yaml` 的 `sandbox.mounts`。把宿主机上的项目目录映射为 agent 能看到的虚拟路径：

```yaml
# config.yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: true              # git 操作需要 bash
  mounts:
    - host_path: /Users/bowhead/my-sdd-project
      container_path: /mnt/project
      read_only: false               # agent 可以读写
```

配置后，agent 看到 `/mnt/project/README.md`，实际读写的就是 `/Users/bowhead/my-sdd-project/README.md`。你在宿主机上 `vim` 改了这个文件，agent 下一次 `read_file` 读到的就是新内容。

源码依据：
- `VolumeMountConfig` 定义：`deerflow/config/sandbox_config.py:4-10`
- mount → PathMapping 转换：`deerflow/sandbox/local/local_sandbox_provider.py:82-169`
- 文件每次从磁盘新读取：`deerflow/sandbox/local/local_sandbox.py:373` — `with open(resolved_path, ...) as f`，无内存缓存
- 路径安全校验覆盖 custom mount：`deerflow/sandbox/tools.py:669-673` — `_is_custom_mount_path()` 检查

## B.2 三层约定机制

光有物理挂载不够，agent 需要知道"怎么对待这个目录"。DeerFlow 提供了三层可组合的约定：

### 层 1：SOUL.md — 始终激活的人格

每个自定义 agent 的 SOUL.md **每轮对话**都注入到系统 prompt 的 `<soul>` 块中（`deerflow/agents/lead_agent/prompt.py:659-664`）。

```markdown
# {base}/users/default/agents/sdd-agent/SOUL.md

你是一个 SDD（Specification-Driven Development）agent。

## 目录约定
- 项目根：/mnt/project/
- 规范文件：/mnt/project/specs/
- 源代码：/mnt/project/src/
- 测试：/mnt/project/tests/

## 工作原则
1. 每次会话开始，先读 /mnt/project/README.md
2. 实现前，先读对应的 spec 文件
3. 修改后，通过 git diff 检查变更
4. 测试通过后才 commit
```

### 层 2：SKILL.md — 按需激活的工作流

```markdown
# skills/custom/sdd-workflow/SKILL.md
---
name: sdd-workflow
description: SDD 工作流：按规范实现、验证、提交
allowed-tools: [read_file, write_file, bash, ls, glob, grep, str_replace]
---

## 工作流
1. 读 /mnt/project/README.md 了解项目
2. 读 /mnt/project/specs/ 下相关规范
3. 在 /mnt/project/src/ 中实现
4. 用 `bash("cd /mnt/project && pytest")` 跑测试
5. 用 `bash("cd /mnt/project && git diff --stat")` 确认变更
6. 用 `bash("cd /mnt/project && git add -A && git commit -m '...'")` 提交
```

### 层 3：项目内 README.md — 项目级约定

```markdown
# /mnt/project/README.md（即宿主机上的 /Users/bowhead/my-sdd-project/README.md）

# My SDD Project

## Agent 使用说明
- 所有规范文件在 specs/ 下，命名格式：{feature}.spec.md
- 源码在 src/ 下，与 specs/ 目录结构对应
- 构建命令：make build
- 测试命令：make test
- 提交信息格式：feat({scope}): {description}
```

这三个层次叠加的效果：agent 的 SOUL.md 告诉它"你是什么"，SKILL.md 告诉它"怎么做"，项目 README.md 告诉它"在这个项目里具体是什么"。每一层都可以独立修改。

## B.3 Git 集成

agent 通过 `bash` 工具执行 git 操作（没有专用的 git tool）：

```bash
# agent 在对话中可以：
cd /mnt/project && git status          # 看工作区状态
cd /mnt/project && git diff            # 看人改了什么
cd /mnt/project && git log --oneline    # 看提交历史
cd /mnt/project && git add -A && git commit -m "..."  # 提交
```

前提：
- `sandbox.allow_host_bash: true`（本地模式 bash 默认关闭）
- 宿主机 PATH 上有 git
- mount 是 `read_only: false`

## B.4 协作模式

```
┌─────────────────────────────────────────────┐
│              宿主机文件系统                    │
│                                             │
│  /Users/bowhead/my-sdd-project/             │
│  ├── README.md          ← 你 vim 编辑        │
│  ├── specs/                                  │
│  │   └── new-feature.spec.md  ← 你写规范     │
│  ├── src/                                    │
│  │   └── new_feature.py     ← agent 实现     │
│  └── tests/                                  │
│      └── test_new_feature.py  ← agent 生成   │
│                                             │
│  ▲ custom mount (read_only: false)          │
│  │  实时双向映射                              │
│  ▼                                          │
│  /mnt/project/          ← agent 看到的       │
│                                             │
│  Agent 操作：                                │
│  read_file("/mnt/project/specs/new-feature.spec.md")│
│  write_file("/mnt/project/src/new_feature.py", ...)│
│  bash("cd /mnt/project && git add -A && ...") │
└─────────────────────────────────────────────┘
```

人在宿主机上：
```bash
vim specs/new-feature.spec.md     # 写规范
git add specs/ && git commit -m "spec: add new-feature"
```

然后告诉 agent：
```python
client.chat(
    "new-feature 的规范我写好了在 specs/new-feature.spec.md，"
    "请按规范实现并提交。",
    thread_id="sdd-session"
)
```

Agent 读规范 → 实现 → 跑测试 → git diff 确认 → commit。人和 agent 通过 git 和文件系统自然协作。

## B.5 多 session 连续性

`DeerFlowClient` 配合 SQLite checkpointer 和固定 `thread_id`：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient(agent_name="sdd-agent")

# 第一次 session
client.chat("初始化项目结构...", thread_id="sdd-project")

# ... 过一阵，甚至重启进程后 ...

# 第二次 session — agent 记得之前的对话
client.chat("继续之前的工作，实现 spec-3", thread_id="sdd-project")
```

对话状态（消息历史、artifacts、todos）通过 checkpointer 持久化在 SQLite 中。文件状态通过 custom mount 持久化在宿主机上。

## B.6 注意事项

| 事项 | 说明 |
|------|------|
| **没有文件监听** | agent 不能自动感知人的文件变更——需要人发消息告诉它，或者 agent 主动重读 |
| **Custom mount 是全局的** | 所有线程的 agent 看到的是同一个 `/mnt/project`，需要靠 agent 的自觉（或 SOUL.md 约定）来避免冲突 |
| **没有跨 sandbox 写锁** | 多个 agent 同时写同一个文件可能冲突（`write_file` 只在单个 sandbox 内串行化） |
| **git 必须宿主机上有** | 本地 sandbox 下 bash 直接在宿主机执行，git 必须在 PATH 中 |
| **mount 在 provider 初始化时创建** | 如果 host_path 当时不存在，mount 被静默跳过——需要先建好目录再启动 |
| **可加多个 mount** | 比如知识库挂只读 + 项目目录挂读写，隔离不同用途 |

---

## 相关 digest 笔记

| 主题 | 路径 |
|------|------|
| Sandbox 三种实现 + 路径映射 | `_digest/architecture/06-sandbox.md` |
| Gateway API 完整参考 | `_digest/app-layer/01-api-reference.md` |
| 系统 prompt 组装 | `deerflow/agents/lead_agent/prompt.py:768-823` |
| 中间件全链（19 个） | `_digest/middleware/03-catalog.md` |
| Agent 循环执行流 | `_digest/agent-loop/` |

## 相关 FAQ

| 问题 | 路径 |
|------|------|
| Agent Workflow 编排：Main Agent 启动 Sub-agent | [agent-workflow-orchestration.md](agent-workflow-orchestration.md) |
| 🔰 一步步跟我做：从零到 DeerFlow 跑起来 | [step-by-step-setup.md](step-by-step-setup.md) |
| 所有交互手段 + Agent 测试 + 从实验到 CI | [interaction-methods-and-testing.md](interaction-methods-and-testing.md) |

| 问题 | 路径 |
|------|------|
| 不依赖 Docker 可以跑吗？ | `_faq_on_digested/getting-started-first-flow/no-docker.md` |
| 本地文件系统和 Git 集成 | `_faq_on_digested/getting-started-first-flow/filesystem-and-git.md` |
| Agent 专属工作目录 | `_faq_on_digested/getting-started-first-flow/agent-workspace.md` |
| 入门完整指南 | `_faq_on_digested/getting-started-first-flow/` |

Sources:
- `backend/debug.py` — prompt_toolkit REPL 实现
- `skills/public/claude-to-deerflow/scripts/chat.sh` — bash CLI
- `skills/public/claude-to-deerflow/scripts/status.sh` — status CLI
- `deerflow/client.py:82-850` — DeerFlowClient 完整实现
- `deerflow/config/sandbox_config.py:4-10` — VolumeMountConfig
- `deerflow/sandbox/local/local_sandbox_provider.py:82-169` — mount → PathMapping
- `deerflow/sandbox/tools.py:624-675` — validate_local_tool_path（含 custom mount 校验）
- `deerflow/sandbox/local/local_sandbox.py:373` — read_file 每次从磁盘新读
- `deerflow/agents/lead_agent/prompt.py:659-664, 768-823` — SOUL.md 注入 + 系统 prompt 组装
- `deerflow/config/agents_config.py:129-151` — load_agent_soul()
- `deerflow/agents/middlewares/dynamic_context_middleware.py:81` — 动态上下文注入
