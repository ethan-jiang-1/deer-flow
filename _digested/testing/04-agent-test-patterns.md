---
title: "Agent 测试模式"
description: "从 DeerFlow 源码和社区提取的核心测试模式：FakeToolCallingModel、tool call 验证、sub-agent 测试、流式输出、prompt 生成、文件系统安全。"
topics: [testing, agent, patterns, deterministic, fixtures]
---

# Agent 测试模式

测试 Agent 最难的是 LLM 的非确定性。DeerFlow 的解法：**分层测试 + Fake LLM + monkeypatch**。90% 的测试不需要真实 API key。

## 核心武器：FakeToolCallingModel

源码：`backend/tests/_agent_e2e_helpers.py`

```python
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

class FakeToolCallingModel(FakeMessagesListChatModel):
    """Fake LLM + no-op bind_tools。通过 responses=[] 控制每轮输出。"""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self  # 不需要真实 bind——输出是预编程的

def build_single_tool_call_model(*, tool_name, tool_args,
    tool_call_id="call_1", final_text="done"):
    """两轮模型：第一轮调工具，第二轮回复文本。"""
    return FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[{
            "name": tool_name, "args": tool_args,
            "id": tool_call_id, "type": "tool_call"
        }]),
        AIMessage(content=final_text),
    ])
```

原理：LangChain 的 `create_agent()` 执行 `model.bind_tools(...)` 来暴露 tool schema。`FakeToolCallingModel` 让它空操作——工具 schema 无所谓，因为输出是 `responses=[]` 预先写死的。

## 测试「Agent 调了正确的工具」

### 方式 A：图级别——用 Recording Model

```python
class RecordingModel(FakeToolCallingModel):
    """每轮记录 bind_tools 收到的工具名列表。"""
    bound_tools_per_turn: list[list[str]] = []

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        names = [getattr(t, "name", str(t)) for t in tools]
        self.bound_tools_per_turn.append(names)
        return self

def test_deferred_tools_hidden_on_first_turn():
    model = RecordingModel(responses=[
        AIMessage(content="", tool_calls=[{"name": "tool_search", "args": {"query": "x"}, "id": "t1"}]),
        AIMessage(content="found it"),
    ])

    graph = create_agent(model=model, tools=tools, middleware=[DeferredToolFilterMiddleware()])
    graph.invoke({"messages": [HumanMessage(content="search")]})

    # Turn 1: deferred tools 不可见
    assert "github_create_issue" not in model.bound_tools_per_turn[0]
    # Turn 2: promote 后可见
    assert "github_create_issue" in model.bound_tools_per_turn[1]
```

### 方式 B：流式事件——检查 tool_calls

```python
def test_agent_calls_ls():
    client = DeerFlowClient()
    tool_names = []
    for e in client.stream("list files"):
        if e.type == "messages-tuple" and e.data.get("tool_calls"):
            tool_names.extend(tc["name"] for tc in e.data["tool_calls"])
    assert "ls" in tool_names
```

## 测试中间件链装配

**永远 patch `create_agent`——不真正跑 agent，只验证参数：**

```python
@patch("deerflow.agents.factory.create_agent")
def test_middleware_order(mock_create_agent):
    mock_create_agent.return_value = MagicMock()

    create_deerflow_agent(model, features=RuntimeFeatures(
        sandbox=True, memory=True, subagent=True, auto_title=True
    ))

    mw_types = [type(m).__name__ for m in mock_create_agent.call_args[1]["middleware"]]
    assert mw_types == [
        "ThreadDataMiddleware", "UploadsMiddleware", "SandboxMiddleware",
        "DanglingToolCallMiddleware", "ToolErrorHandlingMiddleware",
        "TitleMiddleware", "MemoryMiddleware", "SubagentLimitMiddleware",
        "LoopDetectionMiddleware", "ClarificationMiddleware",
    ]
```

## 测试 Sub-agent 调度

### 方式 A：mock 掉 SubagentExecutor

```python
def test_task_tool_emits_events(monkeypatch):
    events = []

    class DummyExecutor:
        def execute_async(self, prompt, task_id=None):
            return task_id or "generated-id"

    monkeypatch.setattr("deerflow.tools.builtins.task_tool.SubagentExecutor", DummyExecutor)
    monkeypatch.setattr("deerflow.tools.builtins.task_tool.get_background_task_result",
        lambda tid: SubagentResult(status=SubagentStatus.COMPLETED, result="all done"))
    monkeypatch.setattr("deerflow.tools.builtins.task_tool.get_stream_writer",
        lambda: events.append)

    result = task_tool(runtime, description="sub", prompt="do work",
                       subagent_type="general-purpose", tool_call_id="tc-1")

    assert "all done" in result
    assert [e["type"] for e in events] == ["task_started", "task_running", "task_completed"]
```

### 方式 B：mock 掉 _create_agent

```python
@pytest.mark.anyio
async def test_subagent_execution():
    mock_agent = MagicMock()
    mock_agent.astream = lambda *a, **kw: async_iter([{
        "messages": [HumanMessage(content="task"), AIMessage(content="done", id="m1")]
    }])

    executor = SubagentExecutor(config=cfg, tools=[], thread_id="t1")
    with patch.object(executor, "_create_agent", return_value=mock_agent):
        result = await executor._aexecute("Do task")

    assert result.status == SubagentStatus.COMPLETED
    assert result.result == "done"
```

## 测试流式输出格式

```python
def test_stream_emits_token_deltas():
    agent = MagicMock()
    agent.stream.return_value = iter([
        ("messages", (AIMessageChunk(content="Hel", id="ai-1"), {})),
        ("messages", (AIMessageChunk(content="lo", id="ai-1"), {})),
    ])

    with patch.object(client, "_agent", agent):
        events = list(client.stream("hi", thread_id="t1"))

    contents = [e.data["content"] for e in events
                if e.type == "messages-tuple" and e.data.get("content")]
    assert "".join(contents) == "Hello"
```

## 测试 Prompt 生成

不跑 agent，只验证 prompt 里有没有正确注入内容：

```python
def test_prompt_includes_custom_mounts(monkeypatch):
    mounts = [SimpleNamespace(container_path="/mnt/my-project", read_only=False)]
    monkeypatch.setattr("deerflow.config.get_app_config",
        lambda: SimpleNamespace(sandbox=SimpleNamespace(mounts=mounts), ...))
    monkeypatch.setattr(prompt_module, "_get_enabled_skills", lambda: [])

    prompt = apply_prompt_template()
    assert "/mnt/my-project" in prompt
    assert "Custom Mounted Directories" in prompt
```

## 测试文件系统安全

**参数化 + 精确的错误断言：**

```python
@pytest.mark.parametrize("command", [
    "cat /etc/passwd",
    "ls /Users/bowhead/.ssh",
    "cp /bin/sh /mnt/user-data/workspace/",
])
def test_blocks_host_paths(command):
    with pytest.raises(PermissionError, match="Unsafe absolute paths"):
        validate_local_bash_command_paths(command, thread_data)

@pytest.mark.parametrize("command", [
    "cat ../uploads/secret.txt",
    "echo ok > ../../outputs/result.txt",
])
def test_blocks_dotdot_traversal(command):
    with pytest.raises(PermissionError, match="path traversal"):
        validate_local_bash_command_paths(command, thread_data)

def test_allows_legit_git_clone():
    validate_local_bash_command_paths(
        "cd /mnt/user-data/workspace && git clone https://github.com/x/y.git",
        thread_data
    )  # 不抛异常 = 通过
```

## 完整模板：新增 Middleware 测试

```python
"""Tests for MyMiddleware."""

import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from deerflow.agents.middlewares.my_middleware import MyMiddleware

def _runtime(thread_id="t-1"):
    r = MagicMock()
    r.context = {"thread_id": thread_id}
    return r

def _ai(content="", tool_calls=None):
    return AIMessage(content=content, tool_calls=tool_calls or [])

class TestMyMiddleware:
    def test_triggers_on_condition(self):
        mw = MyMiddleware()
        state = {"messages": [_ai(content="trigger")]}
        result = mw._apply(state, _runtime())
        assert result is not None

    def test_passes_through_otherwise(self):
        mw = MyMiddleware()
        state = {"messages": [_ai(content="normal")]}
        assert mw._apply(state, _runtime()) is None

    def test_empty_messages(self):
        mw = MyMiddleware()
        assert mw._apply({"messages": []}, _runtime()) is None
```

## 测试环境隔离

```python
@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """每个测试有独立的 DEER_FLOW_HOME。"""
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    monkeypatch.setattr("deerflow.sandbox.sandbox_provider._default_sandbox_provider", None)

    # 禁用副作用
    monkeypatch.setattr("deerflow.config.title_config._title_config",
                        TitleConfig(enabled=False))
    monkeypatch.setattr("deerflow.config.memory_config._memory_config",
                        MemoryConfig(enabled=False))

    config = AppConfig.model_validate({...})  # 纯内存配置
    monkeypatch.setattr("deerflow.client.get_app_config", lambda: config)
    return tmp_path
```

## 关键源码

| 文件 | 内容 |
|------|------|
| `backend/tests/_agent_e2e_helpers.py` | FakeToolCallingModel |
| `backend/tests/test_create_deerflow_agent.py` | 中间件链装配测试（42 个） |
| `backend/tests/test_subagent_executor.py` | Sub-agent 执行测试（45 个） |
| `backend/tests/test_task_tool_core_logic.py` | task() 工具测试（27 个） |
| `backend/tests/test_sandbox_tools_security.py` | 路径安全测试（93 个） |
| `backend/tests/test_client.py` | 流式输出测试（143 个） |
| `backend/tests/conftest.py` | 全局 fixture：单例重置、circular import mock |

---
> **See also:** [Testing Skills & Workflows](05-testing-skills-and-workflows.md) · [CI & Automation](06-ci-and-automation.md) · [Pattern Reference](08-testing-patterns-reference.md)
