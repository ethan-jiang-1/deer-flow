---
title: "错误处理与调试"
description: "Loop detection 双层检测、LLM 错误分类与重试、Tool 错误元数据、日志配置、调优参数。"
topics: [error-handling, debugging, loop-detection, logging, circuit-breaker]
---

# 错误处理与调试

## Loop Detection：防止 Agent 跑飞

文件：`deerflow/agents/middlewares/loop_detection_middleware.py`

两层检测机制，配置在 `loop_detection` 段：

### Layer 1：Hash-based（相同 tool call 集合）

每次 `after_model`，对当前 tool calls 做 MD5 哈希（顺序无关——同一组 tool call 无论怎么排列都产生相同哈希）。`read_file` 的行范围被按 200 行分桶，所以相邻行号的变化不会误判为新调用。

| 参数 | 默认 | 说明 |
|------|------|------|
| `warn_threshold` | 3 | 相同调用集出现 N 次后注入警告 |
| `hard_limit` | 5 | 超过后剥离 tool_calls 强制文本回答 |
| `window_size` | 20 | 滑动窗口大小 |

### Layer 2：Per-tool 频率（跨文件循环）

独立于参数，纯计数每个工具被调用了多少次。

| 参数 | 默认 | 说明 |
|------|------|------|
| `tool_freq_warn` | 30 | 单工具调用 N 次后警告 |
| `tool_freq_hard_limit` | 50 | 超过后强制停止 |

支持 per-tool 覆盖：`tool_freq_overrides.bash.warn: 150`。

### 警告注入机制

警告不在 `after_model` 中直接注入（会破坏 OpenAI tool-call 配对——每次 AIMessage.tool_calls 必须有 ToolMessage 响应）。而是排队到 per-(thread, run) 队列，在下次 `wrap_model_call` 时作为 `HumanMessage(name="loop_warning")` 注入。每条 run 最多 4 条待处理警告。

---

## LLM 错误处理

文件：`deerflow/agents/middlewares/llm_error_handling_middleware.py`

### 错误分类（`_classify_error`）

| 类别 | 可重试 | 匹配模式 |
|------|--------|---------|
| `quota` | 否 | billing/quota/credit |
| `auth` | 否 | key/permission/authentication |
| `transient` | 是 | timeout, connection, internal server error, httpx read, StreamChunkTimeout, IndexError from empty generations |
| `busy` | 是 | busy/overload/high demand/rate limit |

### 重试策略

- 默认最多 3 次，base delay 1000ms，指数退避 `delay * 2^(attempt-1)`，上限 8000ms
- 尊重 `Retry-After` / `retry-after-ms` 响应头
- `StreamChunkTimeoutError` 预算减半（2 次），并给用户提示拆分工作

### 断路器

状态机：`closed → open → half_open → closed`。Open 时返回 `error_type="CircuitBreakerOpen"`。Half-open 允许恰好一个探测请求。

配置：`circuit_breaker.failure_threshold`（默认 5）、`circuit_breaker.recovery_timeout_sec`（默认 60）

---

## Tool 错误元数据

文件：`deerflow/agents/middlewares/tool_result_meta.py`

每个 ToolMessage 被标记 `deerflow_tool_meta`（`additional_kwargs`）：

```python
{
    "status": "success" | "error" | "partial_success",
    "error_type": str | None,        # auth, rate_limited, transient, config,
                                     # permission, no_results, not_found, internal
    "recoverable_by_model": bool,     # LLM 能否自行恢复
    "recommended_next_action": "continue" | "rewrite_query" | "try_alternative" | "summarize" | "stop",
    "source": "exception" | "tool_return" | "content_analysis" | "progress_middleware"
}
```

错误分类规则（`_ERROR_RULES`，按顺序匹配）：`rate_limited`（rate limit 关键词）、`auth`（permission/access denied）、`transient`（timeout/connection）、`config`（invalid API key）、`no_results`（not found/no results）、`not_found`（does not exist）

---

## 大文件操作与截断

两层：工具层截断 + 中间件层输出预算。

### 工具层截断（`tools.py`）

| 工具 | 配置 | 默认 | 方式 |
|------|------|------|------|
| bash | `sandbox.bash_output_max_chars` | 20,000 | 中间截断 |
| read_file | `sandbox.read_file_output_max_chars` | 50,000 | 头部截断 |
| ls | `sandbox.ls_output_max_chars` | 20,000 | 头部截断 |

`max_chars=0` 禁用截断。

### 中间件层：ToolOutputBudgetMiddleware

文件：`deerflow/agents/middlewares/tool_output_budget_middleware.py`

两层独立工作：工具层截断发生在工具函数内部；中间件在结果返回后再次检查。

**外部化（首选）**：结果超过 `externalize_min_chars`（默认 12,000）→ 完整输出写入磁盘 `{outputs}/.tool-results/{tool}-{id}.{ext}`，ToolMessage.content 替换为 head（2,000）+ 文件引用 + tail（1,000）。

**Fallback 截断**：磁盘不可用时 → `fallback_max_chars`（30,000）硬截断。

配置在 `tool_output` 段。`read_file` 和 `read_file_tool` 默认豁免（防止 persist-read-persist 循环）。

bash 输出额外经过 `mask_secret_values()`（≥4 字符的注入密钥值被脱敏）和 `mask_local_paths_in_output()`（宿主路径替换回虚拟路径）。

---

## 日志配置

文件：`deerflow/logging_config.py`

- 日志级别：`config.log_level`（`info`，支持标准 Python 级别名）
- 输出：默认 stderr（`logging.basicConfig`），Docker 中被容器 runtime 捕获
- 格式：`%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- 重启生效（非热加载字段）

### 增强模式（`logging.enhance.enabled: true`）

注入 `trace_id`（来自 `deerflow.trace_context`）到每条日志。同时写入 HTTP `X-Trace-Id` 响应头（Gateway）和 Langfuse metadata（`deerflow_trace_id`）。格式可选 `text` 或 `json`。

---

## Gateway API 认证

文件：`app/gateway/auth_middleware.py`

三种认证模式（按优先级）：

| 模式 | 机制 | 用途 |
|------|------|------|
| Internal Token | `X-DeerFlow-Internal-Token` header | IM channel worker 回调 |
| Session/JWT | `access_token` cookie | 浏览器/Web UI |
| Auth Disabled | 无认证 | 本地开发（`is_auth_disabled()`） |

公开路径（无需认证）：`/health`、`/docs`、`/api/v1/auth/login/local`、`/api/v1/auth/register`、`/api/webhooks/*`

分页模式：cursor-based（`before_seq`/`after_seq`），查询 `limit + 1` 行，`trim_run_message_page()` 判断 `has_more`。

---

## 速率限制

DeerFlow **没有通用 HTTP 速率限制中间件**。仅有登录爆破保护（`auth.py:243`，基于 IP 的 LRU 计数器，最多跟踪 10,000 个 IP）。

Tool 错误元数据将 `rate_limited` 视为可恢复错误（`recoverable_by_model=False`，`recommended_next_action="summarize"`），但这只是分类，不是强制。
