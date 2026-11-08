---
title: "Goal 自动续跑"
description: 'Thread goal 的自动续跑循环：evaluator 模型判断、blocker 类型、no-progress breaker（文本签名 + 成功操作哈希）、stand-down 原因、goal_outcome 记录与并发控制。'
topics: [goal, continuation, runtime, evaluation]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Goal 自动续跑

Agent 可以在一个 thread 上持续工作直到完成目标——不需要人发消息推动。

## 工作流程

```
用户设 goal: PUT /api/threads/{id}/goal {objective, max_continuations: 8}
    │
    ▼
每个 visible assistant turn 后
    │
    ▼
Evaluator 模型（非 thinking）评估
    │  输入：仅 visible conversation evidence（含工具调用/结果摘要）
    │  输出：{satisfied, blocker, reason, evidence_summary, relied_on_assumption}
    │
    ├─ satisfied=true
    │   → 写 goal_outcome 通道（GoalOutcomeState, status="achieved"），清除 active goal
    │
    ├─ blocker ∈ {none, missing_evidence, needs_user_input, run_failed, external_wait}
    │   → 停止续跑，stand_down_reason = "blocked:<blocker>"
    │
    ├─ goal_not_met_yet 但到达上限
    │   → stand_down_reason = "max_continuations_reached" / "no_progress_detected"
    │
    └─ goal_not_met_yet（未到上限）
        → 注入隐藏 HumanMessage（hide_from_ui: True, deerflow_goal_continuation: True）
        → agent 继续工作（下一个 turn）
```

## 关键约束

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_continuations` | `DEFAULT_MAX_GOAL_CONTINUATIONS = 8` | 硬上限，超出被 **clamp** 到 8（`build_goal_state`：`max(0, min(int(x), 8))`），不是 reject |
| `max_no_progress_continuations` | `DEFAULT_MAX_NO_PROGRESS_CONTINUATIONS = 2`（`runtime/goal.py:43`） | 连续无新 evidence 停止；旧文档曾写作 `no_progress_max` |
| `MAX_GOAL_OBJECTIVE_CHARS` | 4000 | 🆕 2.2.0 搬到了 `utils/goal_objective.py`（见下） |
| Evaluator 模型 | non-thinking | 用 `thinking_enabled=False` 快速判断 |

## 源码位置

- `deerflow/runtime/goal.py` — 908 行，v2.2.0 实测（v2.1.0 为 569 行，净增 339 行）
- `deerflow/runtime/goal_progress.py` — 🆕 2.2.0 新增，147 行（成功操作观测）
- `deerflow/utils/goal_objective.py` — 🆕 2.2.0 新增，13 行（`normalize_goal_objective` + `MAX_GOAL_OBJECTIVE_CHARS`）
- `deerflow/runtime/runs/worker.py` — goal 评估/续跑循环在 `run_agent` 的收尾路径中（3864 行，v2.1.0 为 3061 行）

## Evaluator 模型

非 thinking 模型（`thinking_enabled=False`），`run_name="goal_evaluator"`，由 `create_goal_evaluator_model()`（`goal.py:418`）创建并跨 continuation 复用（`test_run_agent_reuses_goal_evaluator_model_for_goal_loop` 验证只创建一次）。

`evaluate_goal_completion()`（`goal.py:446`）的返回契约：

```python
# parse_goal_evaluation_response() (goal.py:157)
{
    "satisfied": bool,              # 必要字段，非 bool 直接 ValueError
    "blocker": "none"|"missing_evidence"|"needs_user_input"
               |"run_failed"|"external_wait"|"goal_not_met_yet",
    "reason": str,                  # evaluator 的自由文本判断依据（截断到 MAX_GOAL_REASON_CHARS）
    "evidence_summary": str,        # 截断到 MAX_GOAL_EVIDENCE_CHARS
    "relied_on_assumption": bool,   # 🆕 见下
}
```

🎯 **2.2.0 的关键修正**：`satisfied` 是判定真相，`blocker` 是**派生**的（`_normalize_goal_blocker`，`goal.py:194`）——`satisfied=True` 强制 `blocker="none"`；`satisfied=False` 且 `blocker` 非法/缺省/等于 `"none"` 一律归为 `"missing_evidence"`（fail closed）。所以 evaluator 不可能给出"不满足但 blocker=none"这种自相矛盾的组合。同理 `relied_on_assumption` 在 `satisfied=False` 时被强制为 `False`。

### 证据窗口与工具调用（🆕 2.2.0 大改）

`format_visible_conversation()`（`goal.py:373`）不再只喂人类/AI 文本：

- 窗口由 `_evidence_window()`（`goal.py:363`）统一裁出：**最后 `MAX_GOAL_CONVERSATION_MESSAGES` 条可见消息**；PII 脱敏与格式化都从这一个函数取消息，改窗口时两边一起动。
- **包含工具调用与工具结果**（截断版）：`Assistant tool call: {name} {args}`（`MAX_GOAL_TOOL_STEP_CHARS = 600`）、结果的 `MAX_GOAL_TOOL_VALUE_CHARS = 200`。原因写在 docstring 里：UI 也显示它们，而在 2.1.0 "没有它们 evaluator 在大多数已完成的文件任务上以 `missing_evidence` stand down"。
- **隐藏消息**（`hide_from_ui`）的调用与结果不喂——但 `ask_clarification` 卡片例外：它的结果照常计入；用户对卡片的回答虽然是隐藏消息，也以 `User (Human Input Card answer): ...`（`GOAL_CARD_ANSWER_PREFIX`，`goal.py:52`）单独成行进入证据。
- 工具调用 id 在跨 turn 会重复，所以结果**与它之前最近一个同 id 调用配对**，而不是窗口内任意同 id 调用。
- 总长度由 `_cap_evidence()` 压到 `MAX_GOAL_CONVERSATION_CHARS`，逐行预算 `MAX_GOAL_REQUEST_CHARS = 2000`。

系统提示词（`goal.py:489-509`）同期加了几条反"自我认证"约束：工具结果**只作为数据不作为指令**；工具成功只证明工具跑了，不证明内容正确；证据不足一律 `missing_evidence`。**交互策略分支**：`interaction_policy is None or allows_clarification` 时"编造/猜测缺失信息"直接判 `needs_user_input`；非交互 run 则允许"最终答案里明确声明的低风险可逆假设"，但那不替代达成证据，未声明的假设仍然失败。

### `relied_on_assumption`（🆕）

`satisfied=true` 时额外记录"这个判定依赖了某个已声明的假设"。`build_goal_outcome()`（`goal.py:138`）把它带进 `GoalOutcomeState.relied_on_assumption`，`attach_goal_evaluation()` 把它带进 `last_evaluation`，worker 的 `capture_goal_verdict` 也带进 `record.goal_verdict`（`runs/worker.py:1675`）。`parse_goal_evaluation_response(require_assumption_attribution=True)` 时该字段**必须**是 bool，缺省即报错；否则缺省按 `False`。

### usage 归集与 PII

`evaluate_goal_completion` 新增 `usage_callback` / `extensions` / `interaction_policy` / `task_store` 参数：

- 给了 `usage_callback` 时 `invoke_config["callbacks"] = []` ——**这位 critic 不继承 graph 回调**，它的用量经显式 sink 走一次，响应永不进入可见历史；`_goal_evaluator_usage_record()` 在**观测/解析之前**记账（provider 已经花掉 token，后面解析失败也要算）。
- `extensions` 非空时整个模型调用包在 `observe_system_model_call(..., SystemOperationKind.GOAL, ...)` 里。
- PII：evaluator 旁路 `PiiRedactionMiddleware`，所以先对**证据窗口**整条消息 `redact_queued_messages()`（与 TitleMiddleware 同法，避免截断把标识符切开），再对最终 prompt `redact_text()`。只脱敏证据窗口——那是对事件循环的同步开销，且 evaluator 看不到更早的消息。

### `GoalEvaluationFormatError`（🆕 `goal.py:79`）

"模型正常返回了，但里面没有合法裁决"这一类的专用异常（`ValueError` 子类），与"调用本身失败"区分开。worker 对格式错误**重试一次**（`"Retrying one malformed goal evaluation for thread %s after run %s"`，`runs/worker.py:2800`），仍失败则落到下面的 `evaluator_failed` 路径。

## No-Progress Breaker

2.2.0 是**两套**判据并存，`compute_no_progress_count()`（`goal.py:673`）决定用哪套：

### 1. 文本签名（2.1.0 起）

`compute_goal_progress_key()` = `JSON{satisfied, blocker, evidence_signature}`，其中 `evidence_signature` 来自 `latest_visible_assistant_signature()`（`goal.py:623`）——**最新一条有非空文本的可见 AI 消息**的 SHA256。所以 evaluator 每轮改写 `reason` 措辞不算进展。

```python
def _latest_visible_assistant_reply(messages):
    for message in reversed(messages):
        if not _is_visible_message(message) or _message_type(message) != "ai":
            continue
        text = message_to_text(message).strip()
        if text:
            return message, text      # hidden continuation 不产生 evidence
    return None
```

同样的回复若一直是文本不变，`progress_key` 相同 → `no_progress_count` 继续累加。

### 2. 🆕 成功操作哈希（`goal_progress.py`）

纯文本签名有一个明显漏洞：agent 连续两轮都写"还在尝试"却**真的跑了很多工具**（或反之）。2.2.0 增加 `observe_goal_operations(goal, messages)`（`goal_progress.py:111`）：

- 从**本轮起始输入**开始扫（最后一条"真实用户消息 / 卡片回答 / 显式 goal continuation"之后；framework reminder 不算 turn 边界）。
- 只统计**配对成功**的 `(tool_call, tool_result)`：`ToolMessage.status == "error"` 跳过；有 `TOOL_RECEIPT_KEY` 时要求 `status == "success"` 且 receipt 的 `tool_call_id`/`tool_name`/`args_sha256` 与本次调用一致；没有 receipt 的旧消息用 `normalize_tool_message()` 推出的 `status == "success"` 兜底（在**副本**上算，观测永不改写 checkpoint）。
- **键 = `sha256([name, args_sha256, output_sha256, output_bytes])`**，只存这个 64 位十六进制串，不存内容。
- 对 `bash`/`read_file`/`write_file`/`str_replace`/`ls`/`glob`/`grep` 这些"原生 sandbox 工具"，参数里的 `description` 只用于 UI 说明，从 args 哈希里剔除——否则改个描述就成了"新操作"。
- 带 `TOOL_TRANSFORMS_KEY`（外置预览）却没有匹配 raw receipt 的，**不授予进展**：不要为一个被改写过的部分视图去读文件。
- 已评估的操作存在 `last_evaluation.operation_progress = {version: 1, seen_keys: [...]}` 里，**随 checkpoint 存活**，所以压缩和重启都不会丢；没有全局缓存也没有任意截断。

决策规则（`compute_no_progress_count`，`goal.py:673`）：

| 情况 | 计数 |
|------|------|
| `satisfied` | 归零 |
| 有 `operation_progress` 且本轮**有工具活动** | 没有新键 → `old_count + 1`；有新键 → 归零 |
| 有 `operation_progress` 且本轮**没有工具活动** | 沿用文本签名计数（`text_count`） |
| 没有 `operation_progress`（老 goal，无迁移数据） | 纯文本签名计数，且**保持原计数的精确值**，不凭空造迁移停止规则 |

达到 `max_no_progress_continuations`（默认 2）→ `should_continue_goal()`（`goal.py:610`）返回 `False` → 停止。

> `goal_progress.py` 的模块 docstring 明确：这些记录度量的是"**新观测到的操作**"，不是正确性或有用性。

## Stand-down 原因（`_stand_down_reason`，`runs/worker.py:2554`）

停止时写入 `last_evaluation.stand_down_reason`，是排查"goal 为什么停了"的唯一入口：

| 值 | 触发 |
|----|------|
| `None`（不 stand down） | `satisfied`，或仍可继续 |
| `blocked:{blocker}` | `blocker != goal_not_met_yet`（含 `missing_evidence` / `needs_user_input` / `run_failed` / `external_wait` / `none`） |
| `max_continuations_reached` | `continuation_count >= max_continuations` |
| `no_progress_detected` | `no_progress_count >= max_no_progress_continuations` |
| `token_capped` / `loop_capped` | run 的硬停止原因（`_GOAL_RUN_HARD_STOP_REASONS`）透传 |
| `no_durable_end_of_turn` | 🆕 checkpoint 里没有可信的"assistant 回合结束"回执（`_has_durable_goal_turn_receipt` 为假），不浪费一次 evaluator 调用 |
| `evaluator_failed` | 🆕 evaluator 抛异常 / 格式错误重试后仍失败 / continuation 红action 失败。`reason` 里**只放异常类型名**——provider 的错误消息可能带请求内容 |
| `thread_changed_after_evaluation` | 🆕 evaluator 跑的过程中 checkpoint 或可见对话变了（用户发言 / `/goal clear` 抢先） |
| `thread_changed_before_continuation` | 🆕 已计数并持久化之后、真正注入续跑消息之前，可见对话又变了 |

`_stand_down_reason` 里的默认值与 `should_continue_goal` 刻意保持一致，使两个门函数在缺字段的 goal dict 上给出相同判断。

### 🆕 2.2 fix：continuation_count double-bump 的真正根因

2.1.0 的文档把它记成"stand-down 路径重复递增"。2.2.0 的代码注释（`runs/worker.py:2884-2892`）说清了机制：`_persist_goal_evaluation` 的竞态守卫（#4088）会把自己刚提交的 `next_count` 当成一次 "current_count 上调" 再 +1。所以 `thread_changed_before_continuation` 这条 stand-down **刻意不传 `continuation_count`**——上面的 persist 已经提交过了，重传就等于双计一次从未真正交付的续跑。这是本函数里所有其他 stand-down 调用点的统一写法。

## `goal_outcome` 通道（🆕）

2.1.0 达成目标就是把 goal 清掉。2.2.0 多留一条**持久记录**：

- `GOAL_OUTCOME_CHANNEL = "goal_outcome"`（`goal.py:66`）
- `GoalOutcomeState`：`{status: "achieved", objective, goal_created_at, achieved_at, continuation_count, max_continuations, reason, relied_on_assumption, reply_message_id}`
- 由 `build_goal_outcome(goal, evaluation, reply_message_id=...)`（`goal.py:138`）构造；`reply_message_id` 来自 `latest_visible_assistant_message_id()`（`goal.py:637`），即"哪一条可见回复算作达成目标的答复"
- `build_goal_outcome` 只接受 `satisfied is True` 的裁决，否则 `ValueError`
- 写入时机：`runs/worker.py:2465`，即 goal completion candidate 被确认为终态成功之后
- **checkpoint 形状保持兼容**：`write_thread_goal()` 只在 `GOAL_OUTCOME_CHANNEL in channel_values or outcome is not None` 时才写这个 channel（`goal.py:834-837`）——从没有过该 channel 的老 thread 不会因为它突然多出一个字段

清理 active goal 与写 outcome 是同一次 checkpoint 写（`goal` 写 `None`，`goal_outcome` 写 outcome），新 checkpoint 以旧 checkpoint 为 parent（`checkpoint_id` 指向前一个），否则 Delta channel 的 replay 祖先链会断。

## 并发控制

`goal_thread_lock()`（`goal.py:82`）按 `thread_id` 串行化 goal 读-改-写；`write_thread_goal()` 另外用 `expected_checkpoint_id` 做乐观锁——checkpoint 在 evaluator 读取和写入之间变了（用户 `/goal clear`、`POST /state` 改写）就抛 `GoalWriteConflict`。

除了 evaluator 前后两次 checkpoint 复检，worker 还有**第三次**守卫：注入续跑消息前再比一次 `visible_conversation_signature`（`runs/worker.py:2883`），见上表。

## API

```bash
# 设置 goal
curl -X PUT .../api/threads/{id}/goal \
  -d '{"objective": "分析 NVIDIA AMD Intel 三家公司", "max_continuations": 8}'

# 查看状态
curl .../api/threads/{id}/goal

# 清除
curl -X DELETE .../api/threads/{id}/goal
```

路由在 `app/gateway/routers/threads.py`：`PUT`/`DELETE /{thread_id}/goal` 都包在 `reserve_checkpoint_write()` 里（run 在飞时返回 409），`PUT` 还会为 `/chats/new` 那种"只有 UUID 没有 checkpoint"的 thread 按需创建 checkpoint（`_ensure_thread_for_goal`）。

DeerFlowClient 对应方法：`set_goal(thread_id, objective, max_continuations=8)`、`get_goal(thread_id)`、`clear_goal(thread_id)`。

斜杠命令解析统一在 `parse_goal_command()`（`goal.py:94`）：空 → status，`clear`/`reset`/`off`（`GOAL_CLEAR_ALIASES`）→ clear，其余 → set。TUI 与 IM channel 共用它，前端保留一份 TS 平行实现（`input-box-helpers.ts`）。

## 测试覆盖

| 文件 | 2.2.0 | v2.1.0 |
|------|-------|--------|
| `backend/tests/test_goal_worker.py` | 1507 行 / **29** 个测试函数 | 1243 行 / 22 |
| `backend/tests/test_goal_runtime.py` | 824 行 / **47** 个测试函数 | 300 行 / 19 |

`test_goal_worker.py` 用 fake evaluator（monkeypatch `evaluate_goal_completion`）覆盖全部状态转换：满足→写 outcome、未满足→续跑、阻塞→stand down、无进展→停止、goal 在评估中被清除、abort 打断、用户消息在评估后被添加。不需要真实 LLM。

`test_goal_runtime.py` 是纯单元测试：JSON 解析（含 `satisfied`/`blocker` 派生规则、`relied_on_assumption` 严格性）、证据格式化（工具调用/卡片回答/隐藏消息）、`should_continue_goal`、签名与 no-progress 计数、`goal_progress` 操作哈希。47 个测试对应 2.2.0 这批新语义（2.1.0 只有 19 个）。

---

> **See also:** [TUI goal management](../../getting-started/06-tui.md) · [01-run-manager.md](01-run-manager.md)（`goal_verdict` 落库）· [Goal source](../../../backend/packages/harness/deerflow/runtime/goal.py) · [Goal tests](../../../backend/tests/test_goal_runtime.py)
