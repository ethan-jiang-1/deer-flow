---
title: "Goal 自动续跑"
description: "Thread goal 的自动续跑循环：evaluator 模型判断、blocker 类型、no-progress breaker、并发控制。"
topics: [goal, continuation, runtime, evaluation]
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
    │  输入：仅 visible conversation evidence
    │  输出：GoalBlocker 类型
    │
    ├─ none / missing_evidence / needs_user_input / run_failed
    │   → 停止续跑，记录 stand_down_reason
    │
    ├─ goal_not_met_yet
    │   → 注入隐藏 HumanMessage（hide_from_ui: True）
    │   → agent 继续工作（下一个 turn）
    │
    └─ 无可见进度（SHA256 最新 assistant 文本 2 次无变化）
        → no-progress breaker 触发，停止
```

## 关键约束

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_continuations` | 8 | 硬上限，超出被 clamp 或 reject（422） |
| `no_progress_max` | 2 | 连续无新 evidence 停止 |
| Evaluator 模型 | non-thinking | 用 thinking_enabled=False 快速判断 |

## 并发控制

- `goal_thread_lock()` 按 `thread_id` 串行化读写
- `expected_checkpoint_id` 防止写冲突

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

DeerFlowClient 对应方法：`set_goal(thread_id, objective, max_continuations=8)`、`get_goal(thread_id)`、`clear_goal(thread_id)`。

源码：`deerflow/runtime/goal.py`（522 行），`deerflow/runtime/runs/worker.py`（goal 续跑循环在 `run_agent` finally 块中）

## Evaluator 模型

非 thinking 模型（`thinking_enabled=False`），`run_name="goal_evaluator"`，由 `create_goal_evaluator_model()` 创建并跨 continuation 复用（`test_run_agent_reuses_goal_evaluator_model_for_goal_loop` 验证只创建一次）。

`evaluate_goal_completion()` 将可见对话证据传给 evaluator，解析返回的 JSON：

```python
# goal.py: parse_goal_evaluation_response()
{
    "should_continue": True,       # 是否续跑
    "blocker": "goal_not_met_yet", # none|missing_evidence|needs_user_input|run_failed|external_wait|goal_not_met_yet
    "reason": "...",               # evaluator 的自由文本判断依据
    "evidence_signature": "sha256..." # 最新可见 assistant 文本的 SHA256
}
```

## No-Progress Breaker

Breaker 基于 `evidence_signature`（SHA256 最新可见 assistant 文本），**不是** evaluator 的自由文本 `reason`。同一个 evidence + 不同的 reason 措辞 = 仍然计为无进展。连续 2 次（`DEFAULT_MAX_NO_PROGRESS_CONTINUATIONS`）无新 evidence → 停止。

```python
# latest_visible_assistant_signature() 只计数可见的 assistant turn
# hidden continuation 不产生 evidence
def latest_visible_assistant_signature(messages):
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not m.additional_kwargs.get("hide_from_ui"):
            return hashlib.sha256(m.content.encode()).hexdigest()
```

## 并发控制

`goal_thread_lock()` 按 `thread_id` 串行化 goal 读写。`write_thread_goal()` 使用 `expected_checkpoint_id` 乐观锁——如果 checkpoint 在 evaluator 读取和写入之间被其他操作修改（如用户 `/goal clear`），写入被拒绝。

## 测试覆盖

`test_goal_worker.py`（689 行，13 个测试函数）用 fake evaluator（monkeypatch `evaluate_goal_completion`）覆盖全部状态转换：满足→清除、未满足→续跑、阻塞→stand down、无进展→停止、goal 在评估中被清除、abort 打断、用户消息在评估后被添加。不需要真实 LLM。

`test_goal_runtime.py`（236 行，18 个测试函数）是纯粹的单元测试：JSON 解析、对话格式化、续跑逻辑、evidence signature 计算。

源码：`deerflow/runtime/goal.py`（522 行），`deerflow/runtime/runs/worker.py`（goal 续跑循环在 `run_agent` 的 finally 块中），`deerflow/client.py`（`set_goal`/`get_goal`/`clear_goal` 方法）

---
> **See also:** [TUI goal management](../../getting-started/06-tui.md) · [Goal source](../../../backend/packages/harness/deerflow/runtime/goal.py) · [Goal tests](../../../backend/tests/test_goal_runtime.py)
