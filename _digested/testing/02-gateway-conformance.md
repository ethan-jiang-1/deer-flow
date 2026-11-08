---




title: "Gateway 一致性测试"
description: 'Gateway 一致性测试：架构、契约与源码锚点。'
topics: [testing, ci, quality-assurance]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Gateway 一致性测试

`backend/tests/test_client.py::TestGatewayConformance` — 验证 `DeerFlowClient`（SDK 直接调用）返回的 dict 与 Gateway HTTP API 的 Pydantic 响应模型完全一致。

## 测试原理

```
                 ┌─ SDK 路径 ─────────────────┐
                 │ DeerFlowClient.list_models() │
  Agent Config ──┤ DeerFlowClient.get_model()  ├── Pydantic 解析
                 │ DeerFlowClient.list_skills()│     ↓
                 └────────────────────────────┘  ValidationError?
                 ┌─ Gateway 路径 ──────────────┐     ↓
                 │ GET /api/models              │  CI 红/绿
                 │ GET /api/models/{name}       │
                 │ GET /api/skills              │
                 └────────────────────────────┘
```

核心思想：不是对比两个路径的输出（那样需要启动 Gateway），而是**用 Gateway 的 Pydantic response model 解析 client 的返回 dict**。如果 client 缺少 Gateway 标记为 required 的字段，或者字段类型不匹配，Pydantic 会抛出 `ValidationError` — CI 捕获 drift。

## 覆盖的响应模型

| 测试方法 | Client 方法 | Gateway Model |
|---------|------------|---------------|
| `test_list_models` | `list_models()` | `ModelsListResponse` |
| `test_get_model` | `get_model(name)` | `ModelResponse` |
| `test_list_skills` | `list_skills()` | `SkillsListResponse` |
| `test_get_skill` | `get_skill(name)` | `SkillResponse` |
| `test_install_skill` | `install_skill(path)` | `SkillInstallResponse` |
| `test_get_mcp_config` | `get_mcp_config()` | `McpConfigResponse` |
| `test_update_mcp_config` | `update_mcp_config(...)` | `McpConfigResponse` |
| `test_get_memory_config` | `get_memory_config()` | `MemoryConfigResponse` |
| `test_get_memory_status` | `get_memory_status()` | `MemoryStatusResponse` |
| `test_upload_files` | `upload_files(...)` | `UploadResponse` |
| `test_goal_methods` | `set_goal()` / `clear_goal()` | `ThreadGoalResponse` |

共 11 个测试，覆盖所有 dict-returning client 方法。**v2.2.0 的定位修正**：类定义在 `backend/tests/test_client.py:4256`（v2.1.0 页面写的 `:3540` 是文件增长后的旧偏移），首个方法 `test_list_models` 在 `:4264`，最后一个 `test_get_memory_status` 在 `:4445`；`test_client.py` 全文 5594 行。

**v2.2.0 新增的一条**：`test_goal_methods`（`:4418`）钉住的是 **thread goal** 这组 v2.2.0 新方法——`set_goal(thread_id, objective)` / `clear_goal(thread_id)` 返回的 dict 必须能被 `ThreadGoalResponse` 解析，且语义是"set 后 `goal.objective` 等于传入值、clear 后 `goal is None`"。它同时对应仓库里的跨语言契约 `contracts/thread_goal_contract.json`（另有 `backend/tests/test_thread_goal_contract.py` 与前端 `thread-goal-contract.test.ts` 三端钉同一份文档）——**一个新 Gateway 能力至少要过三道门：conformance 形状、契约 JSON 语义、前端消费方**。

它也是这个类里唯一**需要真 checkpointer** 的测试（方法体里 `client._checkpointer = InMemorySaver()`）——其余十个都靠 mock 就能跑。

## 测试模式

每个测试遵循相同的三步：

```python
def test_list_models(self, mock_app_config):
    # 1. 设置 mock config
    model = MagicMock()
    model.name = "test-model"
    model.model = "gpt-test"
    model.supports_thinking = False
    mock_app_config.models = [model]

    # 2. 调用 client（SDK 路径）
    with patch("deerflow.client.get_app_config", return_value=mock_app_config):
        client = DeerFlowClient()
    result = client.list_models()

    # 3. 用 Gateway Pydantic model 解析 → drift 检测
    parsed = ModelsListResponse(**result)
    assert parsed.models[0].name == "test-model"
```

关键设计：
- **不启动 Gateway** — 所有后端依赖被 mock，测试在纯 Python 进程中运行（`test_goal_methods` 是唯一例外，用 `InMemorySaver` 提供真 checkpointer，但仍不起 HTTP 进程）
- **双向锁定** — 既验证字段存在（`**result`），又验证值正确（如 `test_list_models` 断言 `parsed.token_usage.enabled is True`、`test_upload_files` 断言 `parsed.files[0].size == len("hello")`）
- **跨层 import** — 测试同时 import `deerflow.client`（Harness）和 `app.gateway.routers.*`（App），这在正常代码中是禁止的（`test_harness_boundary.py` 零豁免扫描 `packages/harness/deerflow/`），但**测试文件不在扫描范围内**——边界守的是发布出去的框架包，不是仓库里的测试代码

## 为什么重要

Gateway 路径在 SDK 之上引入了多层序列化：
1. Python AIMessage → JSON（Pydantic `model_dump`）
2. JSON → SSE event（JSON stringify + SSE framing）
3. SSE event → JSON parse（前端 LangGraph client）
4. JSON → LangChain Message（Pydantic `model_validate`）

任何一层的数据丢失/类型变化都会导致 Gateway 行为和 SDK 行为不一致。一致性测试在序列化层引入 regression 时立刻捕获。

## 与 blocking_io 测试的区别

GatewayConformance 测试**不需要** `@pytest.mark.allow_blocking_io` 标记 — 它们操作的是 mock 对象和内存数据，不涉及 real IO。只有 `tests/blocking_io/` 目录下的测试被 Blockbuster gate 包裹（`backend/tests/blocking_io/conftest.py:26` 的 `hookwrapper` 只对路径落在 `_BLOCKING_IO_TEST_ROOT` 下的 item 生效）。

## v2.2.0 补充：这个类**没有**覆盖的东西

值得把它的盲区写清楚，因为"Gateway 一致性"这个词很容易被误读成"Gateway 全对"：

| 不在这里证明 | 由谁证明 |
|---|---|
| 真 HTTP/SSE 的序列化与 framing | `test_client_e2e.py`（真 Gateway 进程）+ `test_replay_golden.py`（SSE 形状 golden） |
| Gateway 的路由/权限表 | `backend/tests/test_auth_me_permissions.py` 与前端 `auth-disabled-contract.spec.ts` 双端钉（`frontend/AGENTS.md:45` 要求"update both"） |
| langgraph_sdk 真实 payload 的可接受性 | `test_run_request_validation.py::test_gateway_accepts_langgraph_sdk_default_payload`（`:167`）——`backend/app/gateway/AGENTS.md:201` 明文说明为什么 channel 测试抓不到这类漂移："channel tests mock the SDK and miss this drift" |
| 跨语言契约字段语义 | `contracts/*.json` + 双端测试（`test_strategy/00-overview.md` 契约层） |
