---
title: "E2E + 单元测试"
description: "## Frontend 单元测试（Vitest）"
topics: [testing, ci, quality-assurance]
---

# E2E + 单元测试

## Frontend 单元测试（Vitest）

`frontend/tests/unit/` — 镜像 `src/` 的结构：

### 消息处理测试

```typescript
// core/messages/utils.test.ts 示例场景
describe("getMessageGroups", () => {
  it("classifies human messages as 'human' group")
  it("classifies AI messages with content only as 'assistant'")
  it("classifies AI messages with tool_calls as 'assistant:processing'")
  it("classifies AI messages with task tool_calls as 'assistant:subagent'")
  it("hides internal messages (summary, loop_warning, todo_reminder)")
  it("handles mixed reasoning+tool_calls in one message")
})

describe("extractReasoningContentFromMessage", () => {
  it("extracts from additional_kwargs.reasoning_content (Anthropic)")
  it("extracts from content[0].thinking (Anthropic gateway)")
  it("extracts from inline <think> tags (DeepSeek/R1)")
  it("handles unclosed <think> tag during streaming")
  it("returns empty for messages without reasoning")
})

describe("splitInlineReasoning", () => {
  it("splits <think>reasoning</think> from content")
  it("handles missing </think> (streaming partial)")
  it("handles multiple <think> blocks")
})
```

### Subtask 状态解析测试

```typescript
// core/tasks/subtask-result.test.ts
describe("parseSubtaskResult", () => {
  it("parses 'Task Succeeded. Result: ...' as completed")
  it("parses 'Task failed.' as failed")
  it("parses 'Task timed out' as failed")
  it("parses 'Error: something went wrong' as failed")
  it("returns in_progress for unknown format (defensive default)")
})
```

### Settings 测试

```typescript
// core/settings/
describe("LocalSettings", () => {
  it("persists to localStorage under 'deerflow.local-settings' key")
  it("syncs across tabs via 'storage' event")
  it("applies per-thread model override from thread-specific key")
})
```

## Frontend E2E 测试（Playwright）

`frontend/tests/e2e/` — 完整用户流程：

### API Mock 策略

使用 Playwright 的 `page.route()` 拦截 API 调用，注入 mock 响应：

```typescript
// Mock SSE stream
await page.route("**/api/langgraph/runs/stream", (route) => {
  route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    body: [
      `event: metadata\ndata: ${JSON.stringify({ run_id: "test-run" })}\n\n`,
      `event: messages-tuple\ndata: ${JSON.stringify([{ type: "AIMessageChunk", content: "Hello" }])}\n\n`,
      `event: messages-tuple\ndata: ${JSON.stringify([{ type: "AIMessageChunk", content: " world" }])}\n\n`,
      `event: end\ndata: ${JSON.stringify({})}\n\n`,
    ].join(""),
  });
});
```

### 关键测试场景

| 场景 | 验证 |
|------|------|
| 发送消息 → 流式响应 | 文本逐步出现（word animation） |
| Tool call 展示 | web_search、read_file、bash 卡片显示参数 |
| Thinking block | 可折叠，展开后渲染 reasoning |
| 文件上传 | 文件卡片显示，上传进度展示 |
| Artifact 打开 | 右侧面板滑入，CodeEditor/Markdown 预览 |
| Subagent dispatch | SubtaskCard 出现，shimmer → completed 转换 |
| Dark/Light 切换 | Theme CSS 变量切换 |
| i18n 切换 | 界面文字从英文切换到中文 |

### Test Runner

```bash
# 安装 Playwright 浏览器
pnpm exec playwright install

# 运行 E2E 测试
pnpm test:e2e

# 交互式调试
pnpm test:e2e -- --debug

# 特定测试
pnpm test:e2e -- --grep "thinking block"
```

## Backend 单元测试（pytest）

### 关键测试文件

| 文件 | 测试数量 | 覆盖重点 |
|------|---------|---------|
| `test_vllm_provider.py` | 7 | reasoning 字段提取、chat template 兼容、thinking 开关、streaming chunk |
| `test_patched_minimax.py` | 4 | reasoning_split 强制启用、reasoning_details 映射、<think> 剥离、delta 拼接 |
| `test_patched_deepseek.py` | 5 | reasoning_content 重注入、多轮保持、positional fallback |
| `test_mindie_provider.py` | 5 | tool+stream 降级、XML 解析、message 修复、timeout 归一化 |
| `test_codex_provider.py` | 5 | SSE 解析、response 合并、message 转换、tool arg 处理 |
| `test_patched_openai.py` | 3 | thought_signature 重注入、snake_case/camelCase 双检测 |
| `test_claude_provider.py` | 3 | auto_thinking_budget、thinking 模式切换 |

### 运行

```bash
# 全量
pytest backend/tests/

# per-module
pytest backend/tests/test_vllm_provider.py -v

# CI 模式
pytest backend/tests/ --tb=short -q
```
