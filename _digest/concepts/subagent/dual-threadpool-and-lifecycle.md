---
title: "子 Agent 系统"
description: "Lead Agent 把复杂任务委派给后台子 Agent 并行执行。"
topics: [subagent, orchestration, parallel-execution]
---

# 子 Agent 系统

Lead Agent 把复杂任务委派给后台子 Agent 并行执行。

## LLM 怎么知道 subagent 类型？

LLM 不会凭空知道有哪些 subagent — 它通过**两个独立的信息源**获知，缺一不可。

![Subagent Discovery](../../internals/agent-loop/figures/subagent-discovery.svg)

### Channel 1: Tool Schema（`task` 工具的 description）

在 `task_tool.py:186`，`@tool("task", parse_docstring=True)` 装饰器把函数的 docstring 提取为这个 tool 的 `description`，langchain 在 `create_agent()` 时把它绑到 model 的 function-calling schema 里。LLM 在决定调哪个 tool 时直接能看到它。

**问题：** docstring 是写死的。builtins (`general-purpose`, `bash`) 的描述硬编码在源码里。自定义 agent 只泛泛提了一句 "may be defined in config.yaml" — LLM 无法通过这个 channel 知道自定义 subagent 的类型名。

### Channel 2: System Prompt（`<subagent_system>` 块）

`prompt.py:213` 的 `_build_subagent_section()` 在 graph 构建时跑，动态生成 `<subagent_system>` 块注入 system prompt。

它调用 `_build_available_subagents_description()`，遍历 `get_available_subagent_names()`：
- **builtins 有匹配**: 用 `builtin_descriptions` 字典的硬编码一行文案
- **自定义 agent**: 读 `SubagentConfig.description` 的**第一行**作为描述

system prompt 还教 LLM 何时用 `task`、并发限制（max 3）、分批策略、反例（何时直接执行）。

### 三套描述的问题

同一个 subagent 类型 (`general-purpose`) 在三处代码写了三套文案：

| 位置 | 内容（节选） | LLM 看得到？ |
|------|------------|-------------|
| Tool docstring `task_tool.py:201` | "A capable agent for complex, multi-step tasks that require both exploration and action..." | ✓ 在 function-calling schema 里 |
| System prompt dict `prompt.py:191` | "For ANY non-trivial task — web research, code exploration, file operations, analysis, etc." | ✓ 在 system prompt 里 |
| `SubagentConfig.description` `general_purpose.py:7` | 多行带 bullet points | ✗ **builtins 永远读不到** |

第三处只在自定义 agent 时通过 registry 进入 Channel 2（取第一行）。对 builtins，`_build_available_subagents_description()` 直接用 `builtin_descriptions` 字典跳过 `SubagentConfig.description`。

### 总开关：`subagent_enabled`

`subagent_enabled=False` 时**两端同时切断**：
- `get_available_tools(subagent_enabled=False)` → `task` tool 不加入 tools 列表 → model 的 function-calling schema 里没有它
- `_build_subagent_section()` → 检查 `subagent_enabled`，false 时整个 `<subagent_system>` 块不注入 system prompt

## 三个核心问题

| 问题 | 答案 |
|------|------|
| **怎么触发？** | LLM 产出 `task` tool_call → `SubagentLimitMiddleware` 截断到并发上限（min(请求, `subagent_runtime.max_running`, 64)）→ LangGraph 路由到 `task_tool` |
| **怎么检查回来？** | `task_tool` 每 5s 调 `get_background_task_result(execution_id)` 读共享的 `_background_tasks` dict，有新消息就推 SSE `task_running` 事件 |
| **谁管理生命周期？** | 单持久隔离 loop `_isolated_subagent_loop`(1 daemon thread) + 异步 FIFO 容量准入器 `SubagentExecutionCapacity`；timeout 由 loop 内 `asyncio.wait_for` 承担 |

---

## Benefit-based Routing Policy 🆕

**2.1（同步 #4，`fix(agent): route subagents by net benefit (#4384)`）**：启用 subagent 后，委派是**优化手段**，不是对复杂度的默认回应。

Lead prompt 默认**直接执行**，只在以下情况允许 `task`：
- **并行延迟收益** — 多个独立任务并行
- **专家能力收益** — 某个 subagent 类型（如 bash）明显更专业
- **上下文隔离收益** — 需要隔离大上下文

**硬性否决**（veto）：
- 任务间有**输出依赖**（B 需要 A 的结果）
- 任务间**可变状态重叠**（都改同一文件）
- 并行 scope 必须独立且不重叠

当强制并发上限为 1 时，prompt 会移除并行/多批收益指引，只允许专家或隔离收益。

路由策略在 `lead_agent/prompt.py`、`task` tool 描述、两个内置角色描述间保持一致（回归测试：`test_subagent_routing_prompt.py`）。

## User-Scoped Skills + Callback 隔离 🆕

**同步 #4 两项 subagent 加固**：

1. **User-scoped skills**（`fix(subagents): load user-scoped skills (#4356)`）：subagent 通过 `get_or_new_user_skill_storage(user_id)` 解析配置的 skills（用 parent runtime identity），保持 custom-skill shadowing 与 lead agent 一致，而不是只读全局 catalog
2. **Callback 隔离**（`fix(subagents): isolate callbacks and activate skills lazily (#4497)`）：sync 委派和 `execute_async()` 把 ambient ContextVars 复制进持久 subagent loop（checkpoint lineage、user identity、tracing、tags、metadata、namespaced stream handler）；只移除标记了 `deerflow_loop_bound` 的 handler（`RunJournal` 携带该标记，因为持有 parent-loop tasks 和 SQL store/pool）——避免 `Future attached to a different loop` 和重复 token 记账

---

## 完整生命周期时序图

![Subagent Lifecycle](../../internals/agent-loop/figures/subagent-lifecycle.svg)

---

## Phase 1: 触发 — LLM 决定委派

Lead Agent 的 LLM 返回一个 `tool_call(name="task")`：

```json
{
  "name": "task",
  "args": {
    "subagent_type": "general-purpose",
    "description": "Research Python async patterns",
    "prompt": "Find the top 3 async libraries and compare them"
  }
}
```

**`SubagentLimitMiddleware` (after_model)** 拦截这个 tool_call：

```
_last_aimessage.tool_calls 中数 "task" 的数量
  ├── ≤ max_concurrent (默认 3) → 放行
  └── > 3 → 截断，只保留前 3 个，后面的丢弃
```

截断在 `agent.py:328` 装配，`subagent_limit_middleware.py:71` 触发。用 `clone_ai_message_with_tool_calls()` 替换最后一条 AIMessage，保留前 N 个 task call，丢弃其余。

**过检后**，LangGraph 的 ToolNode 路由到 `task_tool()`。

---

## Phase 2: 启动 — task_tool 装配并丢到后台

`task_tool` 是一个 `async def`，用 `@tool("task")` 装饰。位于 `tools/builtins/task_tool.py:187`。

**第一步：解析 subagent_type**

```
get_subagent_config(subagent_type)
  ├── builtins: "general-purpose" | "bash"
  ├── custom_agents: config.yaml → subagents.custom_agents.<name>
  ├── managed subagents: 部署级持久定义（file/sql store，启用且不冲突）
  └── per-agent overrides: config.yaml → subagents.agents.<name>
      (timeout_seconds, max_turns, model, skills 可在 agent 级别覆盖)
```

**第二步：获取 tools（防止递归委派）**

```python
tools = get_available_tools(subagent_enabled=False)
```

`subagent_enabled=False` 是关键 — 这会从 tool 列表中移除 `task` tool，防止 subagent 再创建 sub-subagent。builtins 里的 `task` tool 本身就排除了 `task`，这里是双重保障。

**第三步：创建 SubagentExecutor**

```python
executor = SubagentExecutor(
    config=subagent_config,
    tools=tools,
    parent_model=lead_agent_model,
    sandbox_state=runtime.state.get("sandbox"),
    thread_data=runtime.state.get("thread_data"),
)
```

**第四步：execute_async — fire and forget**

```python
task_id = executor.execute_async(task=prompt, task_id=tool_call_id)
# 立即返回 task_id，不等待 subagent 完成
```

`execute_async` 做了三件事（`executor.py:1312`）：
1. 生成服务端唯一 `execution_id`(uuid4)，创建 `SubagentResult(PENDING)` 存入全局 `_background_tasks[execution_id]`；provider `tool_call_id` 只存入 `external_task_id` 作关联，不作为 registry key
2. `_submit_to_isolated_loop_in_context(run_with_timeout)` — 把 `asyncio.wait_for(_aexecute, timeout)` 包装的协程丢到持久 isolated loop
3. 立即返回 `execution_id`

---

## Phase 3: 执行 — 持久隔离 loop + 容量准入

同步 #5 起，执行模型从"调度线程池 + 隔离 loop"收敛为**单一持久隔离 loop + 异步容量准入器**。旧的 `_scheduler_pool`(ThreadPoolExecutor) 已删除；超时不再由调度线程阻塞在 `future.result(timeout)`，改由 loop 内 `asyncio.wait_for` 承担。

```
_isolated_subagent_loop (asyncio.run_forever() daemon thread, 全局单例, 懒初始化)
    │
    │  run_with_timeout()（execute_async 包装）
    │    └─ asyncio.wait_for(_aexecute(task), timeout=config.timeout_seconds)
    │
    └──► _aexecute(task):
          1. async with capacity.slot()          ← SubagentExecutionCapacity 准入
             ├── running < max_running → 直接进入
             ├── reject 策略或队列满 → SubagentCapacityRejected
             └── 否则 FIFO waiter，wait_for(queue_timeout) → 超时 SubagentCapacityTimeout
          2. RUNNING, started_at=now
          3. _build_initial_state(task)
             ├── _load_skills() → 加载 subagent 专属 skills
             ├── _load_skill_messages() → SystemMessage(skill content)
             ├── merge system_prompt + skill messages → single SystemMessage
             └── append HumanMessage(task)
          4. _create_agent(filtered_tools)
             ├── create_chat_model(thinking_enabled=False)
             ├── build_subagent_runtime_middlewares()
             │    （SubagentDateContextMiddleware → … → SystemMessageCoalescingMiddleware）
             └── create_agent(model, tools, middleware, ThreadState)
          5. async for chunk in agent.astream(state, stream_mode="values"):
             ├── 每个 chunk: 收集 AIMessage → result.ai_messages
             ├── 检查 result.cancel_event → 置位则 CANCELLED
             └── 完成: try_set_terminal(COMPLETED, result=text)
          6. exception → try_set_terminal(FAILED)
```

**关键细节：**

- **thinking 关闭**: `create_chat_model(thinking_enabled=False)` — subagent 不需要 thinking 模式
- **max_turns**: `RunnableConfig(recursion_limit=config.max_turns)` — 防止 subagent 无限循环（默认 150（general-purpose），bash 是 60）
- **cancel_event**: `threading.Event` — cooperative 取消信号，subagent 在每次 `astream` chunk 后检查，不强制杀线程
- **容量准入**: `capacity.slot()` 在模型执行**之前**发生；reject/队列满抛 `SubagentCapacityRejected`、排队超时抛 `SubagentCapacityTimeout` → `try_set_terminal(FAILED, admission_failure=True)`（batch 场景会 requeue 且不消耗 attempt）
- **timeout**: `execute_async` 用 `asyncio.wait_for(..., timeout=config.timeout_seconds)` — 超时后设 cancel_event + try_set_terminal(TIMED_OUT)

---

## Phase 4: 轮询 — task_tool 每 5 秒检查

task_tool 在 Phase 2 拿到 `execution_id` 后立刻进入轮询循环（SSE 里对外展示的 `task_id` 是 provider `tool_call_id` 关联键，registry 键是 `execution_id`）：

```python
# task_tool.py
while True:
    result = get_background_task_result(execution_id)  # 读 _background_tasks

    # 推送 SSE 进度事件
    new_msgs = result.ai_messages[last_count:]
    for msg in new_msgs:
        stream_writer.write_event("task_running", {
            "task_id": tool_call_id,   # 关联键，前端卡片据此对齐
            "message": msg,
            "index": i,
            "total": len(result.ai_messages)
        })

    # 检查终止状态
    if result.status == COMPLETED:
        return "Task Succeeded. Result: {text}"
    elif result.status == FAILED:
        return "Task failed. Error: {error}"
    elif result.status == CANCELLED:
        return "Task cancelled by user."
    elif result.status == TIMED_OUT:
        return "Task timed out."

    await asyncio.sleep(5)  # ← 5 秒间隔
```

**SSE 事件流向 Browser:**

```
task_started  → "Subagent 已启动"
task_running  → "Subagent 正在思考..."  (每 5s, 仅新消息)
task_running  → "Subagent 正在执行工具..."
...
task_completed → "Subagent 完成"
```

前端通过 `task_id` 和 `message.index` 渲染 subagent 的实时输出。

**轮询上限**: `max_poll_count = (timeout + 60) / 5` — 超时后还有 12 次额外轮询的机会，然后 task_tool 主动发 `task_timed_out` + 请求取消。

---

## Phase 5: 完成 — 结果回到 Lead Agent

**正常完成**: `COMPLETED` → `try_set_terminal()` → 返回 `"Task Succeeded. Result: {text}"` 给 Lead Agent → Lead Agent 的 LLM 在下一轮 step 看到这个结果（作为 ToolMessage 追加到 messages）→ 决定下一步动作。

**超时**: `TIMED_OUT` → 返回 `"Task timed out."` → cleanup_background_task 清理 `_background_tasks`。

**取消**: 用户点停止 → 父协程收到 `CancelledError` → task_tool 调用 `request_cancel_background_task(execution_id)` 设 cancel_event → 用 `asyncio.shield()` 等 subagent 到 terminal 状态（确保 token 用量不丢失）→ 若未到 terminal 则 schedule deferred cleanup。

**Token 合并**: `SubagentTokenCollector` 在 subagent 每次 `on_llm_end` 时按 `tool_call_id` 缓存 token 用量。`TokenUsageMiddleware` 通过 `pop_cached_subagent_usage()` 将 subagent 用量合并回父 agent 的 AIMessage，在前端 workspace UI 展示总用量时计入 subagent 消耗。

---

## 容量准入与单事件循环（同步 #5 取代双线程池）

旧的"调度线程池 + 隔离 loop"双池模型已被**单一持久隔离 loop + 异步 FIFO 容量准入器**取代：

| 组件 | 角色 |
|------|------|
| `_isolated_subagent_loop` | 1 个 daemon thread 跑 `asyncio.run_forever()`，所有 subagent 的 `_aexecute()` 与 timeout 包装都在这里调度 |
| `SubagentExecutionCapacity`（`subagents/capacity.py`） | 进程级异步准入器：`running`/`max_running` 计数、FIFO waiter 队列、reject/queue 策略、队列超时 |

**为什么能合并成一个 loop？**

超时不再需要一个独立线程阻塞等待：`execute_async` 用 `asyncio.wait_for(..., timeout=config.timeout_seconds)` 在 loop 内部等待，超时同样触发 `cancel_event` + `TIMED_OUT`。于是"阻塞等待超时"这个需要独立线程的理由消失，调度线程池整体删除。

**为什么队列等待不占线程？**

`capacity._acquire()` 在 pool 满时创建一个 `asyncio.Future` waiter 追加到 `deque`，`await wait_for(waiter, queue_timeout_seconds)`。排队的执行**不占用任何线程**（不像线程池那样每个排队任务占一个 worker）。释放 slot 时 `_release_locked` 把 slot 转移给最老 waiter（`_running` 保持不变）。

**为什么 isolated loop 仍是全局单例？**

避免每个 subagent 创建/销毁 event loop；共享 async 原语（httpx client 连接池等）在 loop 销毁时会被关闭。全局单例 daemon thread 保活，所有 subagent（普通 + durable batch）复用同一 loop。容量控制器也绑定到该 loop（`get_subagent_execution_capacity()`），执行活跃时拒绝跨 loop 迁移。

### 容量配置（`config.yaml -> subagent_runtime`，startup-only）

| 字段 | 默认 | 范围 | 含义 |
|------|------|------|------|
| `max_running` | 3 | 1-64 | 单进程同时执行的 native subagent 上限 |
| `max_queued` | 64 | 0-10000 | 等待 slot 的排队上限 |
| `admission_policy` | `queue` | queue/reject | pool 满时排队还是立即拒绝 |
| `queue_timeout_seconds` | 300 | 1-86400 | 排队等待 slot 的最长时间 |

启动时 `configure_subagent_execution_capacity()` 安装冻结快照；`SubagentLimitMiddleware` 与 lead prompt 用同一份 `min(请求, max_running, 64)` 结果，热更新不会让两层广告出超过已建控制器的容量（`subagent_runtime` 是 restart-required 字段）。源码：`deerflow/config/subagent_runtime_config.py`、`deerflow/subagents/capacity.py`。

## Durable Batch 批量执行 🆕

**同步 #5（`feat(subagents): unified capacity and durable batch execution (#4998)`）**：新增显式 durable 批量模式。普通 `task()` 走进程内 `SubagentExecutor` + 容量准入 + 轮询；显式 `batch_task()` 把许多独立条目持久化成 batch/item 行，由租约驱动的 batch service 逐步执行。批量模式**只由显式工具选择，绝不从 prompt 大小推断**。

**为什么需要 durable batch？** 普通 `task` 每次委派都把结果插回 lead 上下文，成千上万条目会压爆 lead 上下文；batch 只返回一个 batch_id，结果留在 owner-scoped API/JSONL 导出里，且**跨 Gateway 重启存活**。

**执行链**：

```
batch_task() → SubagentBatchService.submit()（校验 + create_batch 持久化）
    → poller 循环 run_once() → claim_items()（租约 + skip_locked 多 worker 认领）
    → _execute_item() → SubagentExecutor（同一 capacity.slot()）
    → 租约续期 + 状态轮询 → finalize_item()（截断结果 + token/stop_reason 落库）
```

**两套状态**：

- batch：`queued → running → completed/failed`，可 `paused`/`cancelled`（`pause/resume/cancel`）
- item：`pending → queued → leased → running → succeeded/failed/cancelled`（`retry` 只允许 failed）

**关键机制**：

- **租约（lease）**：`claim_items` 用 `lease_owner = hostname:uuid` + `lease_expires_at` 原子认领，`skip_locked` 支持多 worker；worker 崩溃后租约过期，另一 worker 回收同一稳定 item key
- **attempt 预算**：`max_attempts`(默认 3)；**容量准入失败发生在模型执行之前** → `requeue_item_after_admission_failure` 恢复 attempt，不消耗重试预算；真实执行失败/租约过期才消耗
- **幂等**：`(user_id, submission_key)` 唯一约束防重复提交；`submission_key = {run_id or thread_id}:{tool_call_id}`
- **结果有界**：`max_result_chars`(100k) 截断、`result_preview_max_chars`(2k) 预览、`token_usage`/`model_name`/`stop_reason` 落库
- **取消**：`cancel_batch` 立即 terminalize 所有非终态 item 并清租约，fence 掉 stale worker 完成写入

**配置（`config.yaml -> subagent_batches`，startup-only，默认 `enabled: false`）**：`poll_interval_seconds`(1.0)、`lease_seconds`(120)、`max_items_per_batch`(5000)、`default_max_live_items`(100)/`max_live_items_per_batch`(1000)、`default_max_running_items`(3)/`max_running_items_per_batch`(64)、`max_attempts`(3)、`max_result_chars`(100000)、`result_preview_max_chars`(2000)。`enabled: true` 而 SQL 后端缺失会在 Gateway 启动时报错。源码：`deerflow/config/subagent_batches_config.py`、`deerflow/subagents/batch_service.py`、`deerflow/persistence/subagent_batches/{model,sql}.py`、迁移 `0016_subagent_batches.py`。

### Gateway REST API（`app/gateway/routers/subagent_batches.py`）

前缀 `/api/threads/{thread_id}/subagent-batches`（owner-scoped + `threads:*` 权限）：

| 端点 | 作用 |
|------|------|
| `GET ""` | 列出该线程的 batch |
| `GET /{batch_id}` | 单个 batch + `counts` |
| `GET /{batch_id}/items` | 分页列出 item（可 `status` 过滤） |
| `POST /{batch_id}/pause` / `resume` / `cancel` | 控制；cancel 要求 worker 运行（否则 503） |
| `POST /{batch_id}/items/{item_id}/retry` | 重试单个 failed item（非 failed 返回 409） |
| `GET /{batch_id}/results.jsonl` | NDJSON 流式导出完整结果 |

`GET /api/features` 暴露 `subagent_batches.{enabled,repository_available,worker_running}`：历史在 worker 未运行时仍可读（repo 与 worker 状态分离）。

## 批量专用 Builtin 工具 🆕

`deerflow/tools/builtins/batch_task_tool.py` 定义三个工具，仅当进程内安装了 startup SQL-backed batch submitter 时加入 tools：

| 工具 | 作用 |
|------|------|
| `batch_task` | 显式提交 durable batch（title、items[key+prompt]、subagent_type、可选 max_live_items/max_running_items），立即返回 batch_id |
| `batch_status` | 紧凑进度快照（batch_id/status/total_items/counts） |
| `cancel_batch` | 持久取消 batch |

约束：item key 必须唯一；subagent_type 必须命中 `allowed_subagents` 作用域（与 `task` 同源）；需 `thread_id`；`submission_key` 幂等。结果永不批量注入 lead 上下文（`"never inserts thousands of results into the lead agent context"`）。`bind_batch_tools()` 为 direct `create_deerflow_agent` 调用者克隆绑定到显式 `SubagentRuntime` 的 submitter，worker stop 后这些工具报告 unavailable 而不回落到其它应用的 process-global submitter。

> ⚠️ **与 `background_tasks_tool.py` 的区别**：后者（`list_background_tasks` / `cancel_background_task`）管理的是 **durable MCP 任务**（`deerflow.mcp.tasks.runtime` 的 submitter），不是 subagent batch；其 docstring 写明 "Natural-language management tools for the current thread's MCP tasks"。两者是不同领域、不同 submitter（`get_mcp_task_submitter` vs `get_subagent_batch_submitter`），不要混用。

## 受管子代理（Managed Subagents）🆕

**同步 #5（`feat: managed subagents and delegation scopes (#4887)`）**：新增管理员管理的、跨 deployment 的 subagent 定义，存于 config.yaml 之外。

**注册优先级**（`registry.get_subagent_config`）：builtin → config.yaml `custom_agents` → 启用的 managed 定义 → `subagents.agents.<name>` per-agent override。managed 定义若与 builtin/config 重名，**仍持久化**（Settings UI 可见）但从运行时发现中排除。

**持久化**（`deerflow/persistence/managed_subagents/`）：

- 后端选择随 custom agent 定义的 `agent_storage.backend`：`db` → `SqlManagedSubagentStore`（表 `managed_subagents`：`id`、唯一 `name`、JSON `definition`、时间戳；迁移 `0014_managed_subagents.py`），否则 → `FileManagedSubagentStore`（`managed_subagents_dir` 下每名一个 JSON，temp + `os.replace` + fsync 原子写）
- `ManagedSubagentDefinition` 强校验：name 归一化为小写 `^[A-Za-z0-9-]+$`；`REQUIRED_DISALLOWED_TOOLS = {task, ask_clarification, present_files}` 永远并入 `disallowed_tools`；`extra="forbid"`
- 注册表进程内缓存用 `store.signature()` 失效（SQL：每行 `(id, updated_at)` 元组；file：每文件 `(name, mtime_ns, size)`），TTL 1s

**与普通临时 subagent 的区别**：managed 是**部署级持久注册**（管理员 CRUD、跨请求/进程可见、可 enable/disable），临时 subagent 是 `config.yaml custom_agents` 或 builtin；两者最终都解析成 `SubagentConfig` 走同一个 `SubagentExecutor`。

**Gateway 接口（`/api/subagents`，`app/gateway/routers/subagents.py`）**：`GET ""` 列目录（system_prompt 仅 admin 可见）、`POST ""` 创建（admin；重名/保留名 409）、`PUT /{name}` 更新（admin）、`DELETE /{name}` 删除（admin，204）。响应含 `source=builtin|config|managed`、`editable`、`conflict`、`config_overrides`。

## Delegation Scopes（作用域授权）🆕

`AgentConfig.allowed_subagents` 是自定义 agent 的委派作用域：`None`=全部启用的定义、`[]`=禁止委派、list=allowlist。默认 Lead Agent 无 `AgentConfig`，保持全目录可见。

作用域在装配时**快照进 run metadata**（`metadata.allowed_subagents`），同时过滤：

- **prompt 发现**：`_build_subagent_section` 只用 allowlist 里的名字生成 `<subagent_system>`
- **执行**：`task_tool` 与 `batch_task` 都用 `get_available_subagent_names(allowed_subagents=...)` 校验 `subagent_type`，不在 allowlist 里直接失败
- **硬否决**：`allowed_subagents=[]` 时 `subagent_enabled = requested_subagent_enabled and allowed_subagents != []` → 整个委派开关关闭

绝不从可变 agent config 重新加载 caller policy（避免工具执行期间配置变化导致授权漂移）。源码：`config/agents_config.py`、`agents/lead_agent/agent.py`、`tools/builtins/task_tool.py`、`subagents/registry.py`。

## Isolated Date-Only Context 🆕

**同步 #5（`feat(subagents): isolated date-only context (#4797)`）**：`SubagentDateContextMiddleware`（`dynamic_context_middleware.py`）在每次 built-in subagent 执行时注入一次隐藏的 `<current_date>` SystemMessage（`before_agent`）。它只给日期锚点：**不**读 `AppConfig.memory`、**不**调 memory manager、**不**重写任务 HumanMessage、**不**继承 lead 的 frozen-conversation ID swap / midnight 刷新生命周期（subagent graph 是一次性的，从 fresh state 起）。

注册位置在 `build_subagent_runtime_middlewares` 里紧贴 `SystemMessageCoalescingMiddleware` 之前，coalescer 把日期提醒与 subagent 静态 prompt 合并成单一 leading SystemMessage，strict backend 仍然只收到一个 system 块。lead-only 的 `DynamicContextMiddleware`（日期 + 可选 memory + midnight 更新）保持不变。

## 背景任务 ID 隔离 🆕

**同步 #5（`fix(subagents): isolate background tasks from reused tool call IDs (#4758)`）**：`execute_async()` 生成服务端唯一 `execution_id`(uuid4) 作为 `SubagentResult.task_id` 与 `_background_tasks`/`_background_futures` 的 registry key；provider `tool_call_id` 存入 `external_task_id` 仅作关联（ToolMessage、`task_*` SSE、持久化 lifecycle 事件、前端卡片、`ExtensionData.scope_id`）。provider ID 跨 parent run 不唯一，因此**绝不能**成为 registry 所有权 key；scheduler 闭包持有自己的 `SubagentResult` 而非通过可变 registry 重新解析所有权。终止 token 用量从 message state 归属，`subagent_token_usage_attributed=true` 保证幂等（不重复记账）。

---

## 内置 Subagent

### general-purpose

- `tools=None` — 继承父 agent 全部工具
- `disallowed_tools=["task", "ask_clarification", "present_files"]` — 不能委派、不能追问、不能弹文件
- `max_turns=150`
- 适用于研究、分析、多步骤推理

### bash

- `tools=["bash", "ls", "read_file", "write_file", "str_replace"]` — 仅沙箱工具
- `disallowed_tools=["task", "ask_clarification", "present_files"]`
- `max_turns=60`
- 仅当 `is_host_bash_allowed()=True` 时对 LLM 可见

---

## 自定义 Subagent

```yaml
# config.yaml
subagents:
  custom_agents:
    code-reviewer:
      description: "Reviews code for bugs and style issues"
      system_prompt: "You are a senior code reviewer. Check for..."
      tools: ["bash", "read_file", "grep", "glob"]
      skills: ["code-review"]
      model: inherit
      max_turns: 100
      timeout_seconds: 600
```

**模型指定**（按优先级）：

1. Agent 级覆盖: `subagents.agents.{name}.model` — 最高优先级
2. Custom agent 自身的 `model` 字段 — 例如 `model: gpt-4o`
3. `"inherit"`（默认）— 使用父 agent 的模型，fallback 到 `models[0].name`

> ⚠️ `model` 的值必须是 `config.yaml` 中 `models[].name` 之一。`"inherit"` 是特殊字符串，其余值直接传给 `create_chat_model(name)`。

源码：`resolve_subagent_model_name()` in `subagents/config.py:44`

---

## SubagentConfig

```python
@dataclass
class SubagentConfig:
    name: str                      # 唯一标识
    description: str               # 告诉 LLM 何时委派
    system_prompt: str | None      # subagent 专属 system prompt
    tools: list[str] | None        # None=继承父 agent 全部, [] = 无工具
    disallowed_tools: list[str]    # 默认 ["task"]
    skills: list[str] | None       # None=全部, [] = 无 skill
    model: str                     # "inherit" | 明确模型名
    max_turns: int                 # 默认 50
    timeout_seconds: int           # 默认 900 (15 分钟)
```

---

## SubagentResult 状态机

```
PENDING → RUNNING → COMPLETED  → (cleanup)
                         ↓
                  FAILED / CANCELLED / TIMED_OUT / MAX_TURNS_REACHED 🆕
```

`try_set_terminal()` 线程安全 first-terminal-wins。

## Stop Reason：三轴 Guard Cap 🆕

**2.1 增强**：三个独立轴可以提前终止 subagent run，都通过 additive `stop_reason` 字段（而非新 status enum）暴露原因：

| 轴 | Guard | 触发 | 行为 |
|----|-------|------|------|
| **Turn** | `recursion_limit` = `max_turns` | 耗尽 turn 预算 | LangGraph 抛 `GraphRecursionError`，`_aexecute` 专门 catch |
| **Token** | `TokenBudgetMiddleware` | 达到 `subagents.token_budget.max_tokens` | 剥离 tool_calls，强制 `finish_reason="stop"`，自然完成 |
| **Loop** | `LoopDetectionMiddleware` | 重复相同 tool-call 集合 | 剥离 tool_calls，记录 `loop_capped` |

**为什么 additive 而非新 enum**：可选字段被旧版 frontend/ledger reader 忽略，向后兼容。`SubagentResult.stop_reason` 流经 `task_tool` → lead agent 可见 `Task Succeeded (capped: token_capped)`。

## Delegation Ledger 🆕

源码：`deerflow/agents/middlewares/delegation_ledger.py`

系统维护的委托账本，解决两个问题：

1. **防重复委托**：同一 in-flight task 不会重复委派（按 task description hash 去重）
2. **Total delegation cap**：`SubagentLimitMiddleware` 同时执行 per-run 总委托数限制（默认 `subagents.max_total_per_run=6`），防止模型通过反复 planning checkpoint 分批绕过并发限制

账本条目持久化在 `ThreadState.delegations`（通过 `DurableContextMiddleware` 捕获），标记 `run_id` 以区分当前 run 和历史 run。只有当前 run 的条目消耗 cap。

## Step Capture & Persistence 🆕

源码：`deerflow/subagents/step_events.py`

`capture_new_step_messages()` 遍历每个新追加的消息（不只 `messages[-1]`），保留多工具调用的所有 `ToolMessage`。`build_subagent_step()` 截断超大内容。`_SubagentEventBuffer` **批量写入** `RunEventStore`（`put_batch` 而非逐条 `put`），category=`"subagent"`，前端通过 `list_events?task_id=...` 分页拉取。

🆕 **Summarization 收缩处理**：当 summarization 通过 `RemoveMessage(id=REMOVE_ALL_MESSAGES)` 重写消息通道时，`capture_new_step_messages` 检测 `total < processed_count` 并重置 cursor，避免步骤丢失。

## Subagent Summarization 继承 🆕

Subagent 现在**继承** lead agent 的 summarization 配置：
- 通过 `build_subagent_runtime_middlewares` 附加 `DeerFlowSummarizationMiddleware`
- 共享 `summarization.enabled` 开关 + trigger/keep/model/prompt 配置
- `DurableContextMiddleware` 在 summarization 之前附加，确保压缩后的 context 仍可注入
- `SystemMessageCoalescingMiddleware` 放在最内层（合并所有 SystemMessage，防 strict backends 拒绝）
- `skip_memory_flush=True`：subagent 共享 parent `thread_id`，不将内部 turn 写入 lead 的 durable memory

## Checkpointer Isolation

Subagent 编译时 `checkpointer=False`——永不继承父 run 的 checkpointer。每次运行独立 `ThreadState`，deferred MCP tool 提升按 subagent run 隔离。Checkpoint lineage 通过 ContextVar 继承（非显式 coordinate 传递），防止 child AI/tool 帧泄漏到 parent `messages` 流。

---

## 关键约束

| 约束 | 值 | 强制位置 |
|------|-----|----------|
| 🆕 进程容量 max_running | 3（1-64） | `subagent_runtime.max_running` → `SubagentExecutionCapacity.slot()` |
| 🆕 队列上限 / 策略 / 超时 | 64 / queue / 300s | `subagent_runtime.max_queued` / `admission_policy` / `queue_timeout_seconds` |
| 普通 task 并发 | min(请求, max_running, 64) | `SubagentLimitMiddleware`（与 lead prompt 同一份） |
| 🆕 Per-run 总委托上限 | 6（1-50） | `SubagentLimitMiddleware` + delegation ledger |
| 不能递归委派 | `subagent_enabled=False` | `task_tool` → `get_available_tools()` |
| 默认超时 | 30 min | `subagents.timeout_seconds=1800`（builtins；custom 用自己的 `timeout_seconds`） |
| 默认 max_turns | 150（general-purpose） | `SubagentConfig.max_turns` |
| 🆕 Token budget | 1M（summarization on）/ 2M（off） | `TokenBudgetMiddleware`（subagent 专用） |
| 轮询间隔 | 5s | `task_tool` polling loop |
| thinking | 关闭 | `create_chat_model(thinking_enabled=False)` |
| checkpointer | 隔离（False） | `executor.py` |
| 🆕 batch 上限 | 见 `subagent_batches` 配置 | `SubagentBatchService` + SQL repository |
| 🆕 Subagent 卡片 | 显示 effective model + token usage | `task_running` event |

---
> **See also:** [Lead Agent factory](../lead-agent/factory-and-threadstate.md) · [Middleware: SubagentLimitMiddleware](../../internals/middleware/03-catalog.md) · [Testing sub-agents](../../testing/04-agent-test-patterns.md)
