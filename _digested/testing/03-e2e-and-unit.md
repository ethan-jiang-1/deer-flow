---



title: "E2E + 单元测试"
description: '可抄的前端 Rstest / Playwright 与后端 pytest 测试样例；机制、分类与计数以 test-strategy 为 canonical。'
topics: [testing, ci, quality-assurance]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# E2E + 单元测试

> **边界**：前端/TUI 测试的机制、分类与计数以 [test-strategy/06-frontend-and-tui.md](../test-strategy/06-frontend-and-tui.md) 为 canonical；本页只保留可抄的测试样例与运行方式，不重复维护统计口径。

## Frontend 单元测试（Rstest）

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

# 指定分片（CI 把 mock 车道切成 4 片、每片 1 worker）
pnpm test:e2e -- --shard=2/4 --workers=1
```

**v2.2.0 的变化**：mock 车道从 45 个 spec 长到 **85 个**（369 个 `test(`），CI 相应从单 job 改为 `matrix.shard = [1,2,3,4]` + `--shard=/4 --workers=1`，每个分片上传 `playwright-report-<n>` artifact；只有 shard 1 额外跑认证恢复用例（`frontend/AGENTS.md:47`）。本地复现 CI 失败时**必须带同一个 `--shard`**，否则跑的用例集不同。

## Backend 单元测试（pytest）

### 关键测试文件

（计数为 v2.2.0 实测 `def test` 数；v2.1.0 的旧值在括号里。）

| 文件 | 测试数量 | 覆盖重点 |
|------|---------|---------|
| `backend/tests/test_vllm_provider.py` | **24**（v2.1.0 为 16） | reasoning 字段提取、chat template 兼容、thinking 开关、streaming chunk |
| `backend/tests/test_patched_minimax.py` | **12**（v2.1.0 为 5） | reasoning_split 强制启用、reasoning_details 映射、<think> 剥离、delta 拼接 |
| `backend/tests/test_patched_deepseek.py` | **16**（v2.1.0 为 10） | reasoning_content 重注入、多轮保持、positional fallback |
| `backend/tests/test_mindie_provider.py` | **83**（v2.1.0 为 45） | tool+stream 降级、XML 解析、message 修复、timeout 归一化 |
| `backend/tests/test_codex_provider.py` | **28**（v2.1.0 为 24） | SSE 解析、response 合并、message 转换、tool arg 处理 |
| `backend/tests/test_patched_openai.py` | 8 | thought_signature 重注入、snake_case/camelCase 双检测 |
| `backend/tests/test_claude_provider_prompt_caching.py` | **20**（v2.1.0 为 13） | cache_control breakpoint ≤4 上限、候选位置选择 |
| `backend/tests/test_claude_provider_oauth_billing.py` | 11 | OAuth billing block 注入顺序、metadata.user_id、cache_control 剥离 |

**解释（为什么模型 provider 的测试在 2.2 涨得最快）**：这八份里六份都涨了，`test_mindie_provider` 从 45 涨到 83、`test_patched_minimax` 从 5 涨到 12。原因不在「提供商变多了」，而在**每个 provider 的降级路径都被枚举成了参数化用例**——tool+stream 不支持时怎么退、timeout 怎么归一、XML 解析失败怎么救。这类逻辑的失败模式是组合式的，只测主路径等于不测。

### 运行

```bash
cd backend

# 全量（本地默认：四片并行，排除 live 与 blocking_io）
make test

# 单文件 / 单测试
uv run pytest tests/test_vllm_provider.py -v
uv run pytest tests/test_vllm_provider.py::test_vllm_provider_preserves_explicit_enable_thinking_kwarg -q

# 与 CI 完全同源的分片
make test-shard SPLITS=4 GROUP=2

# 慢但真实的套件（都不在默认路径里）
make test-live           # 需显式开门
make test-blocking-io    # 严格阻塞 IO 套件
```

**v2.2.0 的一处命令变更**：`make test` 已从"单进程全量"变成 `$(MAKE) -k -j$(TEST_JOBS) $(TEST_SHARD_TARGETS)`（`backend/Makefile:26-30`，`TEST_JOBS ?= 4` 在 `:23`）。`-k` 让某一片失败不取消其余片——对 agent 来说这是关键改进：**一次跑完能看到尽可能多的失败，而不是只看到第一个**。根 `AGENTS.md` 也同步把 `cd backend && make test` 的注释改成了 "Four parallel shards; excludes live and blocking-I/O tests"。
