---
title: "Gateway 一致性测试"
description: "`backend/tests/test_client.py::TestGatewayConformance` — 验证 `DeerFlowClient`（SDK 直接调用）返回的 dict 与 Gateway HTTP API 的 Pyda"
topics: [testing, ci, quality-assurance]
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

共 10 个测试，覆盖所有 dict-returning client 方法。

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
- **不启动 Gateway** — 所有后端依赖被 mock，测试在纯 Python 进程中运行
- **双向锁定** — 既验证字段存在（`**result`），又验证值正确（`assert parsed.models[0].name == ...`）
- **跨层 import** — 测试同时 import `deerflow.client`（Harness）和 `app.gateway.routers.*`（App），这在正常代码中是禁止的，但测试文件不受 harness boundary 限制

## 为什么重要

Gateway 路径在 SDK 之上引入了多层序列化：
1. Python AIMessage → JSON（Pydantic `model_dump`）
2. JSON → SSE event（JSON stringify + SSE framing）
3. SSE event → JSON parse（前端 LangGraph client）
4. JSON → LangChain Message（Pydantic `model_validate`）

任何一层的数据丢失/类型变化都会导致 Gateway 行为和 SDK 行为不一致。一致性测试在序列化层引入 regression 时立刻捕获。

## 与 blocking_io 测试的区别

GatewayConformance 测试**不需要** `@pytest.mark.allow_blocking_io` 标记 — 它们操作的是 mock 对象和内存数据，不涉及 real IO。只有 `tests/blocking_io/` 目录下的测试被 Blockbuster gate 包裹。
