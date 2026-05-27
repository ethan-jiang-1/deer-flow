# 子 Agent 系统

DeerFlow 支持 Lead Agent 将复杂任务委派给专门的子 Agent 在后台并行执行。

## 系统约束

| 约束 | 值 | 强制位置 |
|------|-----|----------|
| 最大并发 | 3 | `SubagentLimitMiddleware` + `MAX_CONCURRENT_SUBAGENTS` |
| 默认超时 | 15 分钟 (900s) | `SubagentConfig.timeout_seconds` |
| 最大轮次 | 可配置 | `SubagentConfig.max_turns` |

## 架构

```
Lead Agent
    │
    │  tool call: task(description, prompt, subagent_type)
    ▼
SubagentExecutor
    │
    ├── SubagentRegistry ── 解析 subagent_type → SubagentConfig
    │
    ├── _scheduler_pool (3 workers)  ── 调度新 subagent
    │       │
    │       └── 检查并发数 → 未达上限则启动
    │
    ├── _isolated_subagent_loop ── async-in-sync 隔离
    │       │
    │       └── 在独立线程中运行 subagent graph
    │
    └── 5s 轮询 ── 等待 subagent 完成/失败/超时
            │
            └── SSE events:
                - task_started → 已启动
                - task_running → 执行中
                - task_completed → 成功完成
                - task_failed → 异常失败
                - task_timed_out → 超时
```

## 双线程池设计

```python
_scheduler_pool = ThreadPoolExecutor(max_workers=3)  # 调度
_execution_pool = ThreadPoolExecutor(max_workers=3)  # 执行
```

- **scheduler pool**：管理 subagent 启动、轮询、取消
- **execution pool**：隔离的 `_isolated_subagent_loop`，在 sync 上下文中跑 async graph

为什么需要 `_isolated_subagent_loop`？
- Subagent 的 LangGraph 图是 async 的（`graph.astream()`）
- SubagentExecutor 在 threading 环境中被调用
- 需要在独立线程中创建 event loop 来运行 async graph

## SubagentConfig

```python
@dataclass
class SubagentConfig:
    name: str
    description: str
    system_prompt: str
    tools: list[str] | None        # None = 继承父 Agent 工具
    skills: list[str] | None       # None = 继承全部，[] = 禁用
    model: str | None              # None = 继承父 Agent 模型
    max_turns: int
    timeout_seconds: int
```

## 内置 Subagents

### general-purpose

- 继承所有父 Agent 工具**除了** `task`（防止无限递归委派）
- 适用于研究、分析、多步骤推理等通用任务
- 可配置独立模型（如用 Ollama 本地模型降低成本）

### bash

- 专门用于 shell 命令执行
- 工具限制为基础 shell 操作
- 更短的默认超时（5 分钟）

## 自定义 Subagents

```yaml
subagents:
  custom_agents:
    analysis:
      description: "Data analysis specialist"
      system_prompt: "You are a data analysis subagent..."
      tools: ["bash", "read_file", "write_file"]
      skills: ["data-analysis", "visualization"]
      model: inherit
      max_turns: 80
      timeout_seconds: 600
```

## 执行生命周期

```
SubagentResult (thread-safe 状态机)
│
├── PENDING    → 刚创建，等待调度
├── RUNNING    → 执行中
├── COMPLETED  → 成功完成，包含 final_output
├── FAILED     → 异常失败，包含 error_message
├── CANCELLED  → 被父 Agent 取消
└── TIMED_OUT  → 超时（需要 cooperative cancellation）
```

每个 SubagentResult 有 `cancel_event` (threading.Event)，用于 cooperative cancellation。

## 模型继承与覆盖

```yaml
# 子 Agent 默认继承 Lead Agent 当前模型
# 但可以显式指定不同模型（如用 Ollama 本地模型降低成本）
subagents:
  agents:
    general-purpose:
      model: qwen3:32b      # 使用配置中名为 qwen3:32b 的模型
```

`resolve_subagent_model_name()` 处理解析：
1. Agent 级覆盖 → 使用指定模型
2. 全局覆盖 (`subagents.model`) → 使用全局指定模型
3. 继承 → 使用 Lead Agent 当前模型

## Token 收集

`SubagentTokenCollector` 按 `tool_call_id` 缓存在 token 追踪启用期间。Subagent 完成后，用量合并回发起调用的 AIMessage，按 message position（而非 message id）对齐。
