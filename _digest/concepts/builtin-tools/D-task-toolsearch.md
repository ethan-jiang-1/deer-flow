---
title: "D. 任务委派 & 工具发现"
description: "## task (Subagent)"
topics: [tools, builtin, sandbox-tools]
---

# D. 任务委派 & 工具发现

---

## task (Subagent)

**源码**: `packages/harness/deerflow/tools/builtins/task_tool.py:186`
**加载条件**: `subagent_enabled: true`（运行时参数或 `config.yaml` → `subagents.enabled`）
**Tool Name**: `task`

### 用途

把复杂任务委派给独立运行的子 Agent。子 Agent 在后台线程池中执行，有自己的工具集、模型、sandbox 和上下文隔离。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | `str` | 3-5 词任务描述，用于日志/展示。**必须第一个传** |
| `prompt` | `str` | 完整的任务说明。**必须第二个传** |
| `subagent_type` | `str` | 子 Agent 类型。**必须第三个传** |

### 内置子 Agent 类型

| 类型 | 工具集 | 适用场景 |
|------|--------|----------|
| `general-purpose` | 全工具（**不含** `task`，防止递归嵌套） | 需要多步推理和操作的复杂任务 |
| `bash` | bash 命令执行 | 需要跑命令的任务（需要 `allow_host_bash: true` 或隔离沙箱） |
| 自定义 | 按 `config.yaml` → `subagents.custom_agents` 配置 | 特定领域的定制 Agent |

### 执行流程

```
1. LLM 调用 task(description, prompt, subagent_type)
          │
2. task_tool() 获取子 Agent 配置 + 构建工具集（不含 task）
          │
3. SubagentExecutor.execute_async(prompt) → 后台线程池启动
          │
4. ┌─ 轮询循环（asyncio.sleep(5)）─────────────┐
   │  - 检查状态变化                            │
   │  - SSE 推送 task_running（新 AI 消息）      │
   │  - 检测完成/失败/超时/取消                   │
   └────────────────────────────────────────────┘
          │
5. 返回结果字符串或错误信息
```

### 并发控制

- `SubagentLimitMiddleware`（middleware 位置 16）
- 最多 **3 个并发**子 Agent（`MAX_CONCURRENT_SUBAGENTS = 3`）
- 超量 tool call 被中间件**直接截断**，不会启动

### 超时机制

```
polling_timeout = (subagent_execution_timeout + 60s) / 5 次轮询
```

超时后：
1. `request_cancel_background_task(task_id)` — 发合作式取消信号
2. `_schedule_deferred_subagent_cleanup()` — 异步等子 Agent 真正终止后清理

### SSE 事件

| 事件 | 触发时机 |
|------|----------|
| `task_started` | 子 Agent 启动 |
| `task_running` | 子 Agent 产生新的 AI 消息（含 `message`, `message_index`, `total_messages`） |
| `task_completed` | 正常完成（含 `result` + `usage`） |
| `task_failed` | 执行失败（含 `error` + `usage`） |
| `task_timed_out` | 超时（含 `error` + `usage`） |
| `task_cancelled` | 用户取消 |

### Token 追踪

- 子 Agent 的 token 消耗缓存在 `_subagent_usage_cache[tool_call_id]`
- `TokenUsageMiddleware` 消费缓存 → 合并到父 Agent 的 AIMessage `usage_metadata`
- 同时通过 `RunJournal` 报告给 tracing 系统

### 技能继承

子 Agent 继承父 Agent 的技能白名单（交集），不会获得父 Agent 没有的技能。

### 工具集隔离

子 Agent 调用 `get_available_tools()` 时：
- `subagent_enabled=False` — **不会有** task tool（防止递归嵌套）
- 继承父 Agent 的 `tool_groups`

---

## tool_search

**源码**: `packages/harness/deerflow/tools/builtins/tool_search.py:164`
**加载条件**: `tool_search.enabled: true`（`config.yaml` 中 `tool_search` 段）+ 存在启用的 MCP server
**Tool Name**: `tool_search`

### 用途

运行时发现延迟加载的 MCP 工具。MCP server 可能提供几十个工具（如 GitHub MCP），把全部 schema 塞进 `bind_tools` 会浪费大量 context 且降低模型准确度。`tool_search` 让 Agent 在需要时按需查询。

### 背景：Deferred Tool 机制

```
启动时：
  MCP tools JSON schema
      │
      ▼
  DeferredToolRegistry.register(tool)
      │
      ▼
  System Prompt 注入 <available-deferred-tools> 列表（仅 name）
      │
      ▼
  DeferredToolFilterMiddleware 从 bind_tools 中移除这些工具
      │
      ▼
  LLM 看不到完整 schema，只知道 name 存在

运行时：
  LLM → tool_search("select:GitHub_create_issue")
      │
      ▼
  DeferredToolRegistry.search(query)
      │
      ▼
  DeferredToolRegistry.promote({tool_name})
      │
      ▼
  DeferredToolFilterMiddleware 不再过滤这些工具
      │
      ▼
  下一轮 LLM 调用：工具完整 schema 可见 + 可调用
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `query` | `str` | 查询字符串，支持 3 种语法 |

### 查询语法

#### 1. 直接选择 — `select:name1,name2,...`

```
tool_search("select:GitHub_create_issue,GitHub_search_repos")
```

精确匹配 tool name，返回对应工具的完整 schema。

#### 2. 必须匹配 — `+keyword [ranking terms]`

```
tool_search("+github issue create")
```

要求 name 中包含 "github"，然后按 "issue create" 相关性排序。

#### 3. 通用搜索 — `keyword query`

```
tool_search("notebook jupyter")
```

对 `{name} {description}` 做正则搜索，name 匹配权重 ×2，最多返回 5 个结果。

### 返回格式

JSON 数组，每个元素是 OpenAI function calling 格式：

```json
[
  {
    "name": "GitHub_create_issue",
    "description": "Create a new GitHub issue...",
    "parameters": { ... }
  }
]
```

### ContextVar 隔离

```python
_registry_var: contextvars.ContextVar[DeferredToolRegistry | None] = \
    contextvars.ContextVar("deferred_tool_registry", default=None)
```

- 每个请求有独立的 registry（ContextVar），并发安全
- 子 Agent 创建时复用父的 registry → 已 promote 的工具不会被重新 deferred
- 这是 #2884 号 bug 修复的核心：
  > 之前 `get_available_tools` 每次重建 registry，导致父 Agent promote 的工具被子 Agent 重建时 wipe，
  > LLM 能看见工具名但无法调用

### 配置

```yaml
# config.yaml
tool_search:
  enabled: true  # 默认 false
```
