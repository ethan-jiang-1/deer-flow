---
title: "测试策略全景"
description: "DeerFlow 有三层测试体系：边界测试（CI 强制执行）、Gateway 一致性测试、E2E + 单元测试。"
topics: [testing, ci, quality-assurance]
---

# 测试策略全景

DeerFlow 有三层测试体系：边界测试（CI 强制执行）、Gateway 一致性测试、E2E + 单元测试。

## 测试金字塔

```
          ┌──────┐
          │ E2E  │  Playwright — 完整用户流程
          │  (~15) │
          ├──────┤
          │ Gate │  TestGatewayConformance — SDK/Gateway 格式一致性
          │ (~8)  │
          ├──────┤
          │ Unit │  Vitest (frontend) + pytest (backend provider/middleware)
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

`backend/tests/test_gateway_conformance.py` — 验证 SDK 路径和 Gateway 路径产出相同的结果：

### 测试原理

同一个 Agent 配置，通过两条路径执行相同的输入：
1. **SDK 路径：** 直接在 Python 进程中使用 `create_chat_model()` + `create_agent()` 
2. **Gateway 路径：** 通过 HTTP API `POST /api/threads/{id}/runs` + SSE stream

比较两者的输出——确保 Gateway 的序列化/反序列化层没有改变 Agent 行为。

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

### Frontend (Vitest)

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
| `test_claude_provider.py` | auto_thinking_budget、thinking 模式切换 |

### Runner 配置

- **Frontend：** Vitest 4.x，jsdom 环境，`vitest.config.ts`
- **Backend：** pytest，`pyproject.toml` 中 `[tool.pytest.ini_options]`
- **CI：** 通过 GitHub Actions（如果配置）或手动 `make test`
