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
