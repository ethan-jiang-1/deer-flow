---
title: "借鉴 DeerFlow 自己的测试实践"
description: "DeerFlow 项目自己的 CI 配置、测试工具、验收模式——可以直接复制到你自己的项目中。"
topics: [testing, ci, automation, acceptance]
---

# 借鉴 DeerFlow 自己的测试实践

DeerFlow 项目本身有一套成熟的测试体系。以下是你可以直接复制到你自己的 Agent 项目中的内容。

## 1. CI Workflow（直接复制）

DeerFlow 的 `.github/workflows/backend-unit-tests.yml`，改一下项目名就能用：

```yaml
name: Agent Tests
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - name: Install DeerFlow
        run: |
          git clone https://github.com/bytedance/deer-flow.git /tmp/deer-flow
          uv add deerflow-harness --path /tmp/deer-flow/backend/packages/harness
      - run: uv run pytest tests/ -m "not llm" -v
```

**关键**：LLM 测试默认跳过，单元测试秒级完成。DeerFlow 自己就是这么做的。

## 2. @requires_llm 标记（直接复制）

```python
# tests/conftest.py
import os, pytest

requires_llm = pytest.mark.skipif(
    os.getenv("CI", "").lower() in ("true", "1")
    or not os.getenv("DEEPSEEK_API_KEY"),
    reason="Needs LLM API key — skipped in CI"
)
```

```ini
# pyproject.toml
[tool.pytest.ini_options]
markers = ["llm: tests that need a real LLM API call"]
```

用法：
```python
@requires_llm
def test_agent_reviews_code():
    client = DeerFlowClient()
    result = client.chat("Review this PR diff: ...")
    assert "security" in result.lower()
```

DeerFlow 的 3451 个测试中，只有约 12 个用真实 LLM。其余全部用 fake model。

## 3. FakeToolCallingModel（直接复制）

DeerFlow 的核心测试发明。从 `backend/tests/_agent_e2e_helpers.py` 复制：

```python
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

class FakeToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self  # 输出由 responses=[] 预编程

def build_single_tool_call_model(*, tool_name, tool_args, tool_call_id="t1", final_text="done"):
    return FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[{"name": tool_name, "args": tool_args, "id": tool_call_id}]),
        AIMessage(content=final_text),
    ])
```

用法：不花一分钱 API 费用，跑完整的 agent 图（真实 middleware、真实工具执行）。

## 4. 测试隔离（直接复制）

```python
@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    monkeypatch.setattr("deerflow.sandbox.sandbox_provider._default_sandbox_provider", None)
    monkeypatch.setattr("deerflow.config.title_config._title_config", TitleConfig(enabled=False))
    monkeypatch.setattr("deerflow.config.memory_config._memory_config", MemoryConfig(enabled=False))
    config = AppConfig.model_validate({...})  # 纯内存配置
    monkeypatch.setattr("deerflow.client.get_app_config", lambda: config)
    return tmp_path
```

每个测试独立 `DEER_FLOW_HOME`，不污染全局状态。DeerFlow 194 个测试文件都这么用。

## 5. Record/Replay E2E

DeerFlow 最先进的测试模式。录一次（需要 API key），永久回放（零 key，毫秒级）。

```bash
# 录制
DEERFLOW_WRITE_GOLDEN=1 uv run pytest tests/test_replay_golden.py

# 回放（CI 中零成本运行）
uv run pytest tests/test_replay_golden.py
```

验证的是 SSE event 形状漂移——不是 volatile 文本值。

## 6. 验收测试 checklist

写你自己的 agent 项目时，DeerFlow 的做法：

| 测什么 | 方法 | 来源 |
|--------|------|------|
| Agent wiring（中间件链） | `@patch create_agent` + 列表断言 | `test_create_deerflow_agent.py` |
| Agent 图行为（tool call） | `FakeToolCallingModel` + real `create_agent` | `test_deferred_tool_registry_promotion.py` |
| Gateway e2e（shape drift） | Hermetic replay + golden JSON | `test_replay_golden.py` |
| LLM-based 功能 | Fake evaluator + guardrail-at-apply | `test_goal_worker.py` |
| Router 端点 | `make_authed_test_app` | `test_console_router.py` |
| 文件系统安全 | 参数化 + `PermissionError` | `test_sandbox_tools_security.py` |
| 并发安全 | `threading.Barrier` | `test_subagent_executor.py` |

## 7. 你的 Agent 验收测试模板

```python
# tests/test_my_code_review_agent.py
import pytest
from deerflow.client import DeerFlowClient

requires_llm = pytest.mark.skipif(...)  # 复制上面的

class TestCodeReviewAgent:
    @requires_llm
    def test_reviews_pr_diff(self):
        """Agent 收到 PR diff 后应产出结构化 review。"""
        client = DeerFlowClient(agent_name="code-reviewer")
        result = client.chat(
            "Review this PR: https://github.com/owner/repo/pull/42",
            thread_id="test-review-1"
        )
        assert "security" in result.lower()
        assert len(result) > 200  # 不应太短

    def test_agent_wiring_has_correct_tools(self):
        """Agent 应配置了正确的工具集。"""
        client = DeerFlowClient(agent_name="code-reviewer")
        # 用 FakeToolCallingModel 验证 wiring
        ...
```

## 8. 阻塞 IO 检测

DeerFlow 用 Blockbuster 检测 async 路径上的同步阻塞 IO。你的项目也可以：

```bash
uv run pytest tests/ --blockbuster
```

或直接从 DeerFlow 复制 `tests/blocking_io/conftest.py` 的 `detect_blocking_io_strict` context manager。

## 关键文件（可以直接复制）

| 文件 | 用途 |
|------|------|
| `backend/tests/_agent_e2e_helpers.py` | FakeToolCallingModel |
| `backend/tests/conftest.py` | 全局 fixture、单例重置 |
| `backend/tests/_replay_fixture.py` | Hermetic Gateway 配置 |
| `.github/workflows/backend-unit-tests.yml` | CI workflow 模板 |
| `backend/tests/blocking_io/conftest.py` | Blockbuster 阻塞 IO 门禁 |
