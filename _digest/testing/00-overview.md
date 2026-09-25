---
title: "测试策略全景"
description: "DeerFlow 有三层测试体系：边界测试（CI 强制执行）、Gateway 一致性测试、E2E + 单元测试。🆕 2.1 新增 Monocle Test Tools（trace-based behavioral tests）和 skill review CI。"
topics: [testing, ci, quality-assurance]
---

# 测试策略全景

DeerFlow 有三层测试体系：边界测试（CI 强制执行）、Gateway 一致性测试、E2E + 单元测试。🆕 2.1 新增 Monocle Test Tools（trace-based behavioral tests）和 skill review CI。

## 测试金字塔

```
          ┌──────┐
          │ E2E  │  Playwright — 完整用户流程
          │  (~15) │
          ├──────┤
          │ Gate │  TestGatewayConformance — SDK/Gateway 格式一致性
          │ (~11) │
          ├──────┤
          │ Unit │  Rstest (frontend) + pytest (backend provider/middleware)
          │(100+)│
          ├──────┤
          │Bound │  test_harness_boundary.py — CI-enforced import rules
          └──────┘
```

## CI 强制边界：test_harness_boundary.py

`backend/tests/test_harness_boundary.py` — DeerFlow 最重要的测试基础设施：

### 目的

强制执行 Harness/App 两层架构的 import 边界：
- **Harness 层**（`backend/packages/harness/`）：框架代码，不依赖 App
- **App 层**（`backend/app/`）：应用代码，可以依赖 Harness

### 机制

使用 AST 分析扫描 import 语句：
1. 解析 Harness 层所有 Python 文件的 AST
2. 提取 `import X` 和 `from X import Y` 语句
3. 验证没有任何 Harness 文件 `import app.` 或 `from app.`
4. 同样验证 Harness 文件没有循环依赖（harness 包内互相 import 但方向错误）

### 豁免机制

harness 文件有少量被批准的豁免（如测试辅助代码），通过注释标记 `# harness-boundary: allow`。

## Gateway 一致性测试

`backend/tests/test_client.py::TestGatewayConformance` — 验证 SDK 路径和 Gateway 路径的结果格式一致（`test_client_live.py` 只有 `TestLive*` 系列的真实 API 测试，不含 conformance）：

### 测试原理

不是真的同时跑两条路径（那样要起 Gateway），而是**用 Gateway 的 Pydantic response model 解析 `DeerFlowClient` 返回的 dict**：
1. **SDK 路径：** 在 Python 进程里直接调 `DeerFlowClient` 的方法
2. **Gateway 契约：** 把返回的 dict 交给对应的 Gateway Pydantic response model 解析

字段缺失或类型不符时 Pydantic 抛 `ValidationError`，CI 因此能抓到 drift。

### 覆盖范围

- 消息格式一致性（AIMessage、ToolMessage 的 content 和 metadata）
- Tool call arguments 一致性
- Streaming chunk 一致（数量、顺序、内容）
- Token usage 数据传递

## E2E 测试（Playwright）

`frontend/tests/e2e/` — 基于 Playwright 的完整用户流程测试：

### 测试模式

- 使用 Playwright 的 `page.route()` 拦截 API 调用
- Mock SSE 流（模拟 LangGraph 的 stream events）
- 验证 UI 响应——消息渲染、tool call 卡片、thinking block 展开/折叠、artifact 面板

### 关键测试场景

- 发送消息 → 流式响应渲染
- Tool call 展示（web_search, read_file, bash）
- 文件上传 + artifact 预览
- Subagent dispatch + SubtaskCard 状态转换
- Dark/Light 主题切换
- i18n 切换 (en-US ↔ zh-CN)

## 单元测试

### Frontend (Rstest)

`frontend/tests/unit/` — 镜像 `src/` 结构：

| 区域 | 测试内容 |
|------|---------|
| `core/messages/` | `getMessageGroups()` 分组逻辑、`extractReasoningContentFromMessage()` 三源提取、`parseSubtaskResult()` 状态解析 |
| `core/threads/` | 消息合并策略、token usage 基线追踪 |
| `core/settings/` | localStorage 序列化、useSyncExternalStore 订阅 |
| `core/i18n/` | 翻译 key 覆盖率、locale 切换 |

### Backend (pytest)

`backend/tests/` — per-module 单元测试：

| 文件 | 覆盖 |
|------|------|
| `test_vllm_provider.py` | vLLM reasoning 字段提取、chat template 兼容、thinking 开关 |
| `test_patched_minimax.py` | MiniMax reasoning_split、<think> 剥离、streaming delta 拼接 |
| `test_patched_deepseek.py` | DeepSeek reasoning_content outbound 重注入、多轮保持 |
| `test_mindie_provider.py` | MindIE tool+stream 降级、XML 解析、message 格式修复 |
| `test_codex_provider.py` | Codex SSE 解析、response 合并、message 格式转换 |
| `test_patched_openai.py` | Gemini thought_signature 保留 |
| `test_claude_provider_prompt_caching.py` | prompt cache breakpoint ≤4 上限、候选位置选择 |
| `test_claude_provider_oauth_billing.py` | OAuth billing block 注入、metadata.user_id、cache_control 剥离 |

### Runner 配置

- **Frontend：** Rstest（`@rstest/core` 0.10.x，`pnpm test` → `rstest`），`rstest.config.ts` 分两个 project——`node`（多数纯逻辑测试）与 `dom`（`*.dom.test.*`，happy-dom）
- **Backend：** pytest，`pyproject.toml` 中 `[tool.pytest.ini_options]`
- **CI：** 通过 GitHub Actions（如果配置）或手动 `make test`

> 🆕 同步 #6：`make test` 默认 `--ignore=tests/blocking_io`（只跑离线套件）；阻塞 IO 严格套件单独跑 `make test-blocking-io`。CI 后端单测拆 4 个 duration-aware 并行分片（#5137，`make test-shard` + `backend/.test_durations` 时长基线），Node CI 版本升到 24（#5063）；skill review CI 新增 waivers 机制——详见 `06-ci-and-automation.md`。
