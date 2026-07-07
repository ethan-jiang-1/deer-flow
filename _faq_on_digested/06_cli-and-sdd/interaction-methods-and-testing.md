# 补充：所有交互手段 + Agent 测试 + 从实验到自动化

> **问题一：** DeerFlow 到底支持哪些交互形式？CLI？WebUI？我想都了解一下。
> **问题二：** Agent 测试怎么搞？DeerFlow 内部有什么支持？有没有最佳实践？
> **问题三：** CLI 上快速实验完了之后，怎么接到自动化 / CI 里去？

---

# Part A：所有交互手段一览

DeerFlow 没有可安装的 `deerflow` CLI 二进制（无 console_scripts、无 __main__.py），但它支持 8 种交互形式。按「从最快到最重」排列：

| # | 方式 | 启动命令 | 流式 | 可见性 | 适合 |
|---|------|---------|------|--------|------|
| 1 | **Python REPL + DeerFlowClient** | `uv run python` → `from deerflow.client import DeerFlowClient` | ✅ `stream()` | token 级 + tool call 内部可见 | 程序化实验、调试 |
| 2 | **debug.py REPL** | `PYTHONPATH=. uv run python debug.py` | ❌ `ainvoke` 阻塞 | 最终结果 + artifacts | 断点调试、快速问答 |
| 3 | **chat.sh (bash)** | `bash skills/.../chat.sh "问题"` | ✅ SSE via curl | 最终文本 | shell 环境、脚本集成 |
| 4 | **status.sh (bash)** | `bash skills/.../status.sh [models/skills/agents]` | — | 资源列表 | 环境巡检 |
| 5 | **Web UI** | `http://localhost:2026` | ✅ SSE → React | 全部：tool call 卡片、artifacts、todos、token | 交互体验、演示 |
| 6 | **curl → Gateway API** | `curl -N -X POST :8001/api/runs/stream` | ✅ SSE raw | 全部原始 JSON | HTTP 集成 |
| 7 | **IM Channels** | Feishu/Slack/Telegram/DingTalk/WeCom/Discord/WeChat | 部分（仅 Feishu/WeCom） | 仅文本 | 团队日常使用 |
| 8 | **Jupyter/脚本** | 普通 `.py` 文件 | ✅ `stream()` | 自定义 | 自动化流水线 |

下面逐一详解。

## 1. Python REPL + DeerFlowClient（最灵活）

源码：`deerflow/client.py:82-850`

```bash
cd /Users/bowhead/ai_deerflow_wiki
DEER_FLOW_HOME=/Users/bowhead/ai_deerflow_wiki/.deer-flow \
DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills \
  uv run python
```

```python
>>> from deerflow.client import DeerFlowClient
>>> c = DeerFlowClient()

# 阻塞式一问一答
>>> c.chat("hello")

# 流式 — 逐 token 出 + 看 tool call
>>> for e in c.stream("分析 /mnt/project/src/"):
...     if e.type == "messages-tuple":
...         d = e.data
...         if d.get("type") == "ai" and d.get("content"):
...             print(d["content"], end="", flush=True)
...         elif d.get("type") == "ai" and d.get("tool_calls"):
...             print(f"\n[调用: {[t['name'] for t in d['tool_calls']]}]")
...         elif d.get("type") == "tool":
...             print(f"\n[结果: {d['name']} → {d['content'][:100]}...]")
...     elif e.type == "end":
...         print(f"\n[Token: {e.data['usage']}]")

# 管理 API
>>> c.list_models(); c.list_skills(); c.get_memory()
```

`stream()` 事件类型（`StreamEvent` dataclass）：
- `messages-tuple` + `type: "ai"` + `content` — token 级 delta（需自己按 `id` 累积）
- `messages-tuple` + `type: "ai"` + `tool_calls` — agent 决定调工具
- `messages-tuple` + `type: "tool"` — 工具执行结果
- `values` — 完整状态快照
- `custom` — 应用级事件（如 `task_running`）
- `end` — 流结束 + token 用量

## 2. debug.py REPL（最快上手）

源码：`backend/debug.py`（169 行）

```bash
cd /Users/bowhead/deer-flow/backend
PYTHONPATH=. uv run python debug.py
```

特性：
- `prompt_toolkit.PromptSession` + `InMemoryHistory`（↑↓ 历史、Ctrl-R 搜索）
- 无 prompt_toolkit 时自动降级为 `input()`
- 日志全进 `debug.log`，终端干净
- 使用原始 `make_lead_agent()` + `agent.ainvoke()`，不走 DeerFlowClient
- 阻塞式——等完整 response 回来才打印
- 显示 `present_files` 暴露的 artifacts（虚拟 → 物理路径）

编辑 `debug.py` 第 93-100 行改配置：
```python
config = {"configurable": {
    "thread_id": "debug-thread-001",
    "thinking_enabled": True,
    "is_plan_mode": True,
    "model_name": "deepseek-v3",     # 指定模型
}}
```

## 3. chat.sh（纯 shell）

源码：`skills/public/claude-to-deerflow/scripts/chat.sh`

```bash
# 一次性
bash chat.sh "用 Python 写个冒泡排序"

# 多轮
bash chat.sh "我叫 Alice"

# 四种模式
bash chat.sh "审查代码" "" pro
# flash:    无 thinking, 无 plan, 无 subagent
# standard: thinking, 无 plan
# pro:      thinking + plan_mode（默认）
# ultra:    thinking + plan_mode + subagent

# 自定义 endpoint
DEERFLOW_URL=http://host:2026 bash chat.sh "hi"
```

内部原理：curl + SSE → 5 步（health check → 创建 thread → 构建请求 → SSE 流式读 → 解析 values 事件提取 AI 回复）。

## 4. status.sh（环境巡检）

源码：`skills/public/claude-to-deerflow/scripts/status.sh`

```bash
bash status.sh              # 健康检查 + 总览
bash status.sh models       # 模型列表
bash status.sh skills       # Skills 列表
bash status.sh agents       # Agent 列表
bash status.sh threads      # 最近对话线程
bash status.sh memory       # 记忆内容
bash status.sh thread <id>  # 特定线程历史
```

## 5. Web UI

启动后 `http://localhost:2026`：
- 实时流式渲染（SSE → `useThreadStream` hook → React）
- Tool call 卡片可视化
- Artifacts 内联展示
- Token 用量实时显示
- 模型/Agent/Settings 切换
- 4 种模式：flash / thinking / pro / ultra

前端源码：`frontend/src/core/threads/hooks.ts`（`sendMessage` 回调）

## 6. curl → Gateway API

```bash
# 无状态流式（自动创建临时 thread）
curl -N -X POST http://localhost:8001/api/runs/stream \
  -H "Content-Type: application/json" \
  -H "X-DeerFlow-Internal-Token: my-token" \
  -d '{"input":{"messages":[{"role":"human","content":"Hello"}]}}'

# 有 thread 的多轮
curl -X POST http://localhost:8001/api/threads -H "..." -d '{}'
curl -N -X POST http://localhost:8001/api/threads/{id}/runs/stream -H "..." -d '{...}'
```

关键端点：
- `POST /api/runs/stream` — 无状态流式
- `POST /api/runs/wait` — 无状态阻塞
- `POST /api/threads/{id}/runs/stream` — 有状态流式
- `GET /api/threads/{id}/runs/{rid}/events` — 事后审计

完整 API：`_digest/app-layer/01-api-reference.md`

## 7. IM Channels

7 个平台：Feishu、Slack、Telegram、DingTalk、WeCom、Discord、WeChat。

源码：`app/channels/`（manager.py 为入口，各平台有独立实现）
- DM 机器人 → 消息进 MessageBus → ChannelManager 分发 → agent 响应
- Feishu/WeCom 支持流式（卡片增量更新）
- 其他平台用 `runs.wait()` 阻塞等待

**不适合做实验**——延迟大、无 tool call 可见性、响应可能被截断。

## 8. Jupyter / 普通 Python 脚本

```python
# 任何 .py 文件
from deerflow.client import DeerFlowClient
client = DeerFlowClient(subagent_enabled=True, plan_mode=True)
result = client.chat("分析三家公司", thread_id="auto-task-1")
print(result)
```

配合 `DEER_FLOW_HOME` 和固定 `thread_id`，就是自动化流水线的基础。

---

# Part B：Agent 测试 —— DeerFlow 里有什么

## B.1 内置测试基础设施

### 三层测试金字塔

源码：`_digest/testing/00-overview.md:113`

| 层 | 内容 | 运行方式 |
|----|------|---------|
| **L1 单元测试** | 工具逻辑、中间件行为、配置解析 | `make test`（CI 必需） |
| **L2 Gateway 一致性** | SDK ↔ Gateway 返回格式一致 | `TestGatewayConformance` |
| **L3 边界检查** | Harness 不 import App、阻塞 IO 检测 | `test_harness_boundary.py` + Blockbuster |

### L1：单元测试的关键文件

源码位置：`backend/tests/`

| 测试文件 | 测什么 |
|---------|--------|
| `test_task_tool_core_logic.py` | `task()` 工具的 polling 逻辑、事件发射、取消、清理 |
| `test_subagent_executor.py` | `SubagentExecutor` 的 async/sync 执行、skill 加载 |
| `test_subagent_limit_middleware.py` | 多余 task 调用的截断行为 |
| `test_create_deerflow_agent.py` | 工厂装配、中间件排序、extra_middleware 定位 |
| `test_tool_search.py`（610 行） | DeferredToolRegistry 的搜索、promote、ContextVar 隔离 |
| `test_client.py`（77 个测试） | DeerFlowClient 全方法单元测试 |
| `test_memory_updater.py` | Memory 提取、去重、原子写入 |
| `test_tracing_factory.py` | LangSmith/Langfuse callback 构建 |
| `test_harness_boundary.py` | AST 扫描 → deerflow.* 不 import app.*（CI 硬门禁） |

### L2：Gateway 一致性

`TestGatewayConformance`（`test_client.py`）——每个 client 方法的返回 dict 都经过 Gateway Pydantic response model 校验。Gateway 加新字段 → client 没跟 → CI 报错。

### L3：边界检查 + 阻塞 IO 门禁

Blockbuster（`tests/support/detectors/blocking_io_runtime.py`）——在 async 路径中检测同步阻塞 IO。两个回归锚：skill 加载的 `asyncio.to_thread` 卸载（fix #1917）、SQLite 路径解析的卸载（fix #1912）。CI 硬门禁在 `.github/workflows/backend-blocking-io-tests.yml`。

阻塞 IO AST 检测（`make detect-blocking-io`）——静态扫描 `app/`、`packages/harness/`、`scripts/`，输出 JSON 报告。优先级是确定性的（从操作类型推导），不保证有 bug 但提供审查线索。

### `@requires_llm` 标记

需要真实 LLM 调用的测试用 `@requires_llm` 标记，CI 自动跳过。这些是**集成级 agent 行为测试**——验证 agent 在真实 LLM 下的行为。

```python
@pytest.mark.requires_llm
def test_agent_follows_skill_instructions():
    ...
```

源码：`backend/tests/test_client_e2e.py`

## B.2 核心测试模式：FakeToolCallingModel

DeerFlow 测试中最关键的发明——**不用真 LLM 也能跑完整 agent 图**。

源码：`backend/tests/_agent_e2e_helpers.py`

```python
class FakeToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self  # 不需要真 bind——响应是预先编程的

def build_single_tool_call_model(*, tool_name, tool_args, tool_call_id, final_text):
    return FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[{...}]),  # turn 1: 调工具
        AIMessage(content=final_text),               # turn 2: 最终回答
    ])
```

这个模式让你能**确定性地**验证 agent 行为：
- Agent 收到第一条 fake 响应（含 tool_call）→ 执行真实工具 → 工具结果注入 → Agent 收到第二条 fake 响应 → 返回 final_text
- 全程零 API 调用，但经过了真实的 `create_agent` 图、真实中间件链、真实工具执行

使用这个模式的测试：
- `test_setup_agent_e2e_user_isolation.py` — fake LLM + 真实生产图 + 真实文件 IO
- `test_setup_agent_http_e2e_real_server.py` — fake LLM + 真实 FastAPI + 真实 Gateway
- `test_runtime_lifecycle_e2e.py` — fake LLM + 真实 `run_agent()` 完整生命周期
- `test_deferred_tool_registry_promotion.py` — fake LLM + 真实 tool_search/promotion 循环

## B.3 缺失的东西

DeerFlow **没有**以下 agent 测试能力：

| 缺失 | 为什么重要 |
|------|-----------|
| **LLM mock / 确定性 replay** | 没有预录 LLM 响应然后回放验证的机制。每次 agent 测试都要真实调 LLM（贵、慢、不稳定） |
| **Skill 行为断言** | 没有框架帮你验证"agent 加载了 skill X 后是否执行了步骤 1-2-3" |
| **Tool call 序列验证** | 不能声明"agent 应该先调 read_file 再调 write_file"，只能事后检查 |
| **Agent eval harness** | 没有类似 LangSmith Evaluation 的评估框架集成——没有自动跑 agent → 收集结果 → 打分 → 对比的流水线 |
| **Sub-agent 结果验证** | 没有端到端测试验证"main agent 分派 3 个 sub-agent → 结果被正确汇总" |

## B.3 当前实践中怎么测 Agent

基于现有源码和模式，下面是目前可用的测试策略：

### 策略 1：单元测试每个组件

```python
# 测 tool 逻辑——不涉及 LLM
def test_task_tool_polling():
    executor = SubagentExecutor(config=mock_config, ...)
    executor.execute_async(prompt)
    result = wait_for_completion(task_id)
    assert result.status == SubagentStatus.COMPLETED
```

### 策略 2：用 @requires_llm 做集成验证

```python
@pytest.mark.requires_llm
def test_agent_can_list_workspace():
    client = DeerFlowClient()
    response = client.chat("ls /mnt/user-data/workspace")
    assert "workspace" in response.lower()
```

### 策略 3：流式事件断言

```python
def test_agent_stream_events():
    client = DeerFlowClient()
    events = list(client.stream("hello", thread_id="test-1"))
    
    # 验证事件类型序列
    types = [e.type for e in events]
    assert "messages-tuple" in types
    assert types[-1] == "end"
    
    # 验证 token 用量
    assert events[-1].data["usage"]["total_tokens"] > 0
```

### 策略 4：Tool call 事后检查

```python
@pytest.mark.requires_llm
def test_agent_uses_ls_tool():
    client = DeerFlowClient()
    tool_calls_seen = []
    for e in client.stream("列出 workspace 的文件"):
        if e.type == "messages-tuple" and e.data.get("tool_calls"):
            tool_calls_seen.extend(tc["name"] for tc in e.data["tool_calls"])
    assert "ls" in tool_calls_seen
```

---

# Part C：从 CLI 实验到自动化 / CI

## C.1 实验阶段（你现在在哪儿）

```bash
# 1. Python REPL 快速试
uv run python
>>> from deerflow.client import DeerFlowClient
>>> c = DeerFlowClient()
>>> c.chat("hello")

# 2. debug.py 深度调试
PYTHONPATH=. uv run python debug.py

# 3. 感觉摸清了 → 写脚本
```

## C.2 脚本化阶段

```python
# experiment.py — 放在 ai_deerflow_wiki/ 下
from deerflow.client import DeerFlowClient

client = DeerFlowClient(
    subagent_enabled=True,
    plan_mode=True,
)

result = client.chat(
    "读 /mnt/project/specs/ 下的所有规范，"
    "检查 /mnt/project/src/ 下的实现是否匹配规范。"
    "输出审查报告到 /mnt/project/outputs/review.md",
    thread_id="ci-review"
)
print(result)
```

```bash
DEER_FLOW_HOME=.deer-flow \
DEER_FLOW_SKILLS_PATH=../deer-flow/skills \
  uv run python experiment.py
```

## C.3 CI 阶段

DeerFlow 自己的 CI 流水线（6 个 workflow）：

```yaml
# .github/workflows/agent-review.yml
name: Agent Code Review
on: [pull_request]

jobs:
  agent-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      
      - name: Install DeerFlow
        run: |
          git clone https://github.com/bytedance/deer-flow.git /tmp/deer-flow
          uv add deerflow-harness --path /tmp/deer-flow/backend/packages/harness
      
      - name: Run agent review
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          DEER_FLOW_HOME: .deer-flow
        run: uv run python ci_review.py
```

## C.4 从实验到 CI 的关键决策

| 决策 | 方案 |
|------|------|
| **thread_id 策略** | 固定 `thread_id` → 同一对话线程，适合持续审查；随机 UUID → 每次独立 |
| **checkpointer** | SQLite → 跨 run 持久化对话状态；MemorySaver → 仅进程内 |
| **模型选择** | CI 用便宜模型（如 deepseek-chat），开发用强模型 |
| **输出验证** | 检查 agent 是否写入了预期文件、生成了预期格式 |
| **Token 预算** | CI 中设 `max_turns` 限制，避免超时 |
| **失败处理** | agent 返回空、超时、工具错误 → CI fail |

---

## 关键源码索引

| 内容 | 位置 |
|------|------|
| DeerFlowClient 全方法 | `deerflow/client.py:82-850` |
| StreamEvent 定义 | `deerflow/client.py` `StreamEvent` dataclass |
| debug.py REPL | `backend/debug.py` |
| chat.sh | `skills/public/claude-to-deerflow/scripts/chat.sh` |
| status.sh | `skills/public/claude-to-deerflow/scripts/status.sh` |
| Gateway SSE 端点 | `app/gateway/routers/thread_runs.py` |
| 测试金字塔 | `_digest/testing/00-overview.md` |
| 边界测试 | `tests/test_harness_boundary.py` |
| 阻塞 IO 检测 | `tests/support/detectors/blocking_io_runtime.py` |
| @requires_llm 标记 | `tests/test_client_e2e.py` |
| TestGatewayConformance | `tests/test_client.py` |
