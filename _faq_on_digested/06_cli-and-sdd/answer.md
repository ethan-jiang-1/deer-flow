## 核心结论

**DeerFlow 有一套完整的命令行实验工具链，且从 v2.2.0 起还真的有可安装的 `deerflow` 命令**（TUI 终端工作台 + headless `--print`/`--json`）。**SDD 协作完全可行**：custom mount + SOUL.md + SKILL.md + git via bash 就是一个完整的"项目目录即 agent 上下文"方案。

> 🔄 同步 #8（v2.2.0）：原结论断言「DeerFlow 没有可安装的 `deerflow` CLI 二进制」——该断言**已失效**，见 A.1 的订正。

---

# Part A：命令行实验

## A.1 有什么可用的？

| 入口 | 启动方式 | 流式 | 适合 |
|------|---------|------|------|
| **`deerflow` TUI** 🆕 | `deerflow`（或 `cd backend && PYTHONPATH=. uv run python -m deerflow.tui`） | 是（后台 daemon 线程跑 `stream()`，渲染成 transcript） | 日常终端使用、演示 |
| **`deerflow --print` / `--json`** 🆕 | `deerflow --print "问题"` / `deerflow --json "问题"` | `--json` 逐行 StreamEvent JSON | shell 脚本、CI、管道 |
| **debug.py REPL** | `cd backend && PYTHONPATH=. uv run python debug.py` | 否（阻塞式 ainvoke） | 断点调试、快速测试 |
| **DeerFlowClient Python REPL** | `python` 然后 `from deerflow.client import DeerFlowClient` | 是（`stream()` generator） | 程序化实验、检查内部事件 |
| **chat.sh** | `bash skills/public/claude-to-deerflow/scripts/chat.sh "问题"` | 是（SSE via curl，需 Gateway 活着） | 纯 shell 环境、脚本集成 |
| **status.sh** | `bash skills/public/claude-to-deerflow/scripts/status.sh [models/skills/agents/threads/memory]` | 不适用 | 查看资源状态 |
| **curl** | `curl -N -X POST localhost:8001/api/runs/stream ...` | 是（SSE） | 原始 HTTP 控制 |

> 🔄 同步 #8（v2.2.0）：原文写「没有 `console_scripts`、没有 `__main__.py`、没有 `pip install` 后能敲的 `deerflow` 命令」——三句**全部已失效**：
> - console script 注册在 `packages/harness/pyproject.toml:69-70`：`deerflow = "deerflow.tui.cli:main"`；
> - `tui/__main__.py` 存在，`python -m deerflow.tui` 与 console script 走同一个 `main()`；
> - `textual` 是可选依赖（`packages/harness/pyproject.toml:75` 的 extra `tui`，`textual>=0.80`），所以 `deerflow --print` 在没装 textual 时也照常工作。
>
> 另外 `deerflow extensions install/upgrade/list/enable/disable/remove` 是 `plan_launch()` **之前**就被拦截的转发子命令（`tui/cli.py:242` 起，`argv[0] == "extensions"` → `deerflow.extensions.cli.main`）。
>
> 完整契约（五种启动模式、退出码、18 条 slash 命令、键位、降级路径）见 `_digested/getting-started/06-tui.md`。

## A.2 debug.py — 内置 REPL

源码：`backend/debug.py`（171 行，v2.2.0 行数不变）

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

源码：`deerflow/client.py:177`（`class DeerFlowClient`；文件 2002 行，`stream()` L859、`chat()` L1314，`StreamEvent` 在 L136）

> 🔄 同步 #8（v2.2.0）：原引用 `client.py:145` / `stream()` L770 / `chat()` L1193 / 「约 1780 行」均已漂移，按当前源码更新如上。

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

> 🔄 同步 #8（v2.2.0）：脚本本身未变（v2.2.0 仍为 234 行）。与 v2.2.0 新增的 `deerflow --print "问题"` 的分工是：`chat.sh` 走 Gateway（`DEERFLOW_URL`，默认 `http://localhost:2026`；先 `POST /api/langgraph/threads` 建线程，再 `POST /threads/{id}/runs/stream`），必须 Gateway 活着；`--print` 是**内嵌**运行，不需要 Gateway 与 Nginx，失败时退出码 1（`tui/cli.py:359`）。纯脚本场景优先用后者。

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

> 完整 Gateway API 参考见 `_digested/operations/app-layer/01-api-reference.md`。

## A.7 推荐实验路径

1. **先敲 `deerflow`**（有 TTY 就是全屏 TUI），随便聊几句感受 agent 行为；不想装 textual 就用 `deerflow --print "问题"` 🆕
2. **开 Web UI**（`localhost:2026`），选 flash 模式，看 tool call 卡片和 artifacts 的完整渲染
3. **开 `debug.py`** 或 **Python REPL + `DeerFlowClient.stream()`**，做带工作目录的实验（挂 custom mount、让 agent 读写文件）
4. 感觉摸清了 → 写 Python 脚本用 `DeerFlowClient` 做自动化，或直接用 `deerflow --json` 接管道

> 🔄 同步 #8（v2.2.0）：第 1 步是新增的——v2.2.0 之前没有 `deerflow` 命令，第一步只能是 Web UI。

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

源码依据（行号已按 v2.2.0 更新）：
- `VolumeMountConfig` 定义：`deerflow/config/sandbox_config.py:162` — 字段 `host_path` / `container_path` / `read_only`（原 L115 已漂移）
- mount → PathMapping 转换：`deerflow/sandbox/local/local_sandbox_provider.py:122` — `_setup_path_mappings()`（静态映射：`skills/public` + 自定义 mount；每个 mount 要过「`host_path` 必须绝对路径且存在、`container_path` 必须绝对且不与保留前缀 `/mnt/skills/{public,custom,integrations,legacy}`、`/mnt/user-data`、`/mnt/acp-workspace` 冲突」四道校验，不合规的 mount 被**跳过并记日志**）；per-thread 的 `/mnt/user-data/...`、`/mnt/skills/custom` 映射在 `:334` 的 `_build_thread_path_mappings()` 里追加
- 文件每次从磁盘新读取：`deerflow/sandbox/local/local_sandbox.py:1246` — `with open(resolved_path, ...) as f`（在 `read_file()`，`local_sandbox.py:1233`），无内存缓存（原 L822 已漂移）
- 路径安全校验覆盖 custom mount：`deerflow/sandbox/tools.py:456` — `_is_custom_mount_path()` 定义；`validate_local_tool_path()` 在 `tools.py:1019`，其中 `:1071` 起按 `read_only` 配置拒绝写只读 mount（`PermissionError: Write access to read-only mount is not allowed`）（原 L419/L904 已漂移）

## B.2 三层约定机制

光有物理挂载不够，agent 需要知道"怎么对待这个目录"。DeerFlow 提供了三层可组合的约定：

### 层 1：SOUL.md — 始终激活的人格

每个自定义 agent 的 SOUL.md **每轮对话**都注入到系统 prompt 的 `<soul>` 块中（`get_agent_soul()` 做 HTML 转义后渲染为 `<soul>` 块，`deerflow/agents/lead_agent/prompt.py:1029`；真实读取/回落逻辑在 `deerflow/config/agents_config.py:360` 的 `load_agent_soul()`）。

> 🔄 同步 #8（v2.2.0）：原引用 `prompt.py:954-966` / `agents_config.py:344` 已漂移，符号仍在。另有两处 v2.2.0 语义变化值得注意：
> - **SOUL.md 的存放位置**：补丁前的共享布局 `{base_dir}/agents/{name}/` 现在是 **legacy 只读回退**；当前布局是 `{base_dir}/users/{user_id}/agents/{name}/`（`deerflow/config/paths.py:143-145` 的布局注释、`user_agent_dir()` 在 `paths.py:276`）。写路径只落在 per-user 目录，legacy 目录即使存在也不会被覆写。
> - **删除语义**：`FileAgentStore.delete()`（`deerflow/persistence/agents/file.py:168`）用 `rmtree` 一次性删掉 `config.yaml` + `SOUL.md` + 同目录的 `memory.json`；若目录里没有 `config.yaml`（只是记忆/facts 数据）则返回 `not-custom-agent` 予以保留，legacy 布局的 agent 返回 `legacy` 且原地不动。

```markdown
# {base}/users/{user_id}/agents/sdd-agent/SOUL.md

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
# {base}/users/{user_id}/skills/custom/sdd-workflow/SKILL.md
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

> 🔄 同步 #8（v2.2.0）：`allowed-tools` **不再是工具过滤器**（上游 #6935，commit `0d73798be`）。v2.2.0 里它只是**兼容元数据**——仍会被解析、校验、导出、写进 skill catalog 指纹，并在 `describe_skill` 里以 `Allowed tools (compatibility metadata, not enforced):` 前缀展示，但**从不**授予或收窄工具集；`SkillActivationMiddleware` 只注入 SKILL.md 正文，不动工具表。原来的强制逻辑已删除（v2.1.0 的 `skills/tool_policy.py` 已删除、`agents/middlewares/skill_tool_policy_middleware.py` 已删除）。工具权限天花板由两层决定：Layer 1 的授权过滤 + Layer 2 的 `GuardrailAuthorizationAdapter`。
>
> 所以这段 frontmatter 留着没坏处（别的 agent 框架可能读它），但**别指望它限制 agent**——在 DeerFlow 里要收窄工具，请用 `disallowed_tools`、`authorization`（Layer 1 能力过滤 + Layer 2 `GuardrailAuthorizationAdapter`），或 custom agent 的 `tool_groups` / `skills` / `mcp_plugins`（`deerflow/config/agents_config.py:211-227` 的 `AgentConfig`），以及 `subagents.custom_agents.<name>.tools`。完整机制见 `_digested/concepts/skills-tools/skill-md-and-tool-assembly.md`（§「`allowed-tools`：从「工具过滤器」降级为「兼容元数据」」）。

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
| **mount 在 provider 初始化时创建** | 如果 host_path 当时不存在，mount 被跳过——需要先建好目录再启动 |

> 🔄 同步 #8（v2.2.0）：「静默跳过」已不准确（上游 #3244）。现在 `_setup_path_mappings()`（`deerflow/sandbox/local/local_sandbox_provider.py:122`）对不合规 mount 分两类处理：非绝对路径、与保留前缀冲突 → `logger.warning` 跳过；`host_path` 从 Gateway 进程视角不存在 → **`logger.error`**，并在日志里直接给出补救指引（`make up` 部署时该路径必须同时 bind-mount 进 `deer-flow-gateway` 容器，或改用 `make dev` 本地模式）。相关字段说明也写进了 `config.example.yaml` 的 `sandbox.mounts` 注释（`config.example.yaml:1731-1735`）。所以 mount 没生效时**先翻 Gateway 日志**，不会再无声无息。
| **可加多个 mount** | 比如知识库挂只读 + 项目目录挂读写，隔离不同用途 |

---

## 相关 digest 笔记

| 主题 | 路径 |
|------|------|
| TUI 终端工作台（`deerflow` CLI 真值） | `_digested/getting-started/06-tui.md` |
| Sandbox 三种实现 + 路径映射 | `_digested/concepts/sandbox/` |
| Gateway API 完整参考 | `_digested/operations/app-layer/01-api-reference.md` |
| 系统 prompt 组装 | `deerflow/agents/lead_agent/prompt.py:1155`（`apply_prompt_template()`） |
| 中间件全链（39 个条目位） | `_digested/internals/middleware/03-catalog.md` |
| Agent 循环执行流 | `_digested/internals/agent-loop/` |
| skill 工具装配（`allowed-tools` 降级） | `_digested/concepts/skills-tools/skill-md-and-tool-assembly.md` |

> 🔄 同步 #6（v2.1.0-rc0）：middleware 总数当时为 37 个（新增 `ToolReceiptMiddleware` 与 `DeferredToolPromotionAuditMiddleware`），digest 目录迁移为 `_digested/internals/middleware/`。本 FAQ 描述的 CLI/REPL/SDD 工作流本身不受影响，但上表源码行号已按 v2.1.0-rc0 更新。

> 🔄 同步 #8（v2.2.0）：middleware 口径从 37 改为 **39 个条目位**（分两阶段组装：`_build_runtime_middlewares()` 前 16 条 + `build_middlewares()` 追加 23 条），v2.2.0 新增 `KnowledgeScopeMiddleware` / `ArtifactResolutionMiddleware` / `ArtifactCaptureMiddleware` / `PiiRedactionMiddleware` / `ModelContentCompatibilityMiddleware`，`SkillToolPolicyMiddleware` 已删除（#6935）。`apply_prompt_template()` 现位于 `prompt.py:1155`（原 L1070 已漂移）。CLI 侧最大的变化是**多了可安装的 `deerflow` 命令**，见 A.1 与 `_digested/getting-started/06-tui.md`。

## 相关 FAQ

| 问题 | 路径 |
|------|------|
| Agent Workflow 编排：Main Agent 启动 Sub-agent | [agent-workflow-orchestration.md](agent-workflow-orchestration.md) |
| 🔰 一步步跟我做：从零到 DeerFlow 跑起来 | [step-by-step-setup.md](step-by-step-setup.md) |
| 所有交互手段 + Agent 测试 + 从实验到 CI | [interaction-methods-and-testing.md](interaction-methods-and-testing.md) |

| 问题 | 路径 |
|------|------|
| 不依赖 Docker 可以跑吗？ | `_faq_on_digested/05_getting-started-first-flow/no-docker.md` |
| 本地文件系统和 Git 集成 | `_faq_on_digested/05_getting-started-first-flow/filesystem-and-git.md` |
| Agent 专属工作目录 | `_faq_on_digested/05_getting-started-first-flow/agent-workspace.md` |
| 入门完整指南 | `_faq_on_digested/05_getting-started-first-flow/` |

Sources:
- `deerflow/tui/cli.py:119`（`plan_launch()`）、`:242`（`main()`）— 可安装的 `deerflow` 命令（console script 在 `packages/harness/pyproject.toml:69-70`）
- `backend/debug.py` — prompt_toolkit REPL 实现（171 行，配置 dict 在 `:96-104`）
- `skills/public/claude-to-deerflow/scripts/chat.sh` — bash CLI
- `skills/public/claude-to-deerflow/scripts/status.sh` — status CLI
- `deerflow/client.py:177` — DeerFlowClient 完整实现（2002 行；`stream()` L859、`chat()` L1314）
- `deerflow/config/sandbox_config.py:162` — VolumeMountConfig
- `deerflow/sandbox/local/local_sandbox_provider.py:122` — mount → PathMapping（`_setup_path_mappings()`；per-thread 映射在 `:334`）
- `deerflow/sandbox/tools.py:456` — `_is_custom_mount_path()` 定义；`:1019` `validate_local_tool_path()`，`:1071` 起拒绝写只读 mount
- `deerflow/sandbox/local/local_sandbox.py:1246` — read_file 每次从磁盘新读（`read_file()` 在 `:1233`）
- `deerflow/agents/lead_agent/prompt.py:1029, 1155` — `get_agent_soul()`（`<soul>` 注入）+ `apply_prompt_template()`
- `deerflow/config/agents_config.py:360` — `load_agent_soul()`
- `deerflow/config/paths.py:143`、`:276` — `users/{user_id}/agents/{name}/` 布局与 `user_agent_dir()`；legacy `agents_dir()` 在 `:207`
- `deerflow/persistence/agents/file.py:168` — `FileAgentStore.delete()`（`legacy` / `not-custom-agent` / `deleted` 三种结果）
- `deerflow/agents/middlewares/dynamic_context_middleware.py:364` — DynamicContextMiddleware 类定义（v2.2.0 文件 860 行）

> 🔄 同步 #8（v2.2.0）：上面所有行号已按 v2.2.0 源码重核（括号内为旧值或说明）。`config.example.yaml` 也在同步更新：`config_version` 已是 **63**（`config.example.yaml:23`），全文 3680 行，新增 `blob_storage` / `knowledge_base` / `typesafe` / `deployment` / `pii_redaction` / `tool_artifacts` / `agents_api` / `lead_prompt_overlay` 等段；`STARTUP_ONLY_FIELDS` 从 18 项增至 **27** 项（`deerflow/config/reload_boundary.py:45`）。改完配置后用 `make config-upgrade` 合并，别手抄。
