---
title: "Agent 中间件 Hook 系统：生命周期 + 定位 + 开关"
description: "- `deerflow/agents/features.py` — `RuntimeFeatures` + `@Next`/`@Prev` 装饰器"
topics: [hooks, extension, plugin-system]
---

# Agent 中间件 Hook 系统：生命周期 + 定位 + 开关

> **交叉引用：** 本文侧重**用户如何把自己的 middleware 挂上去**。6 种 hook 点的运行时行为详见 [middleware/01-hooks-and-flow.md](../middleware/01-hooks-and-flow.md)。链装配的完整代码流程见 [middleware/02-chain-assembly.md](../middleware/02-chain-assembly.md)。

**核心文件：**
- `deerflow/agents/features.py` — `RuntimeFeatures` + `@Next`/`@Prev` 装饰器
- `deerflow/agents/factory.py:61-380` — SDK 路径的 `create_deerflow_agent()` + `_assemble_from_features()`
- `deerflow/agents/lead_agent/agent.py:266+` — Lead Agent 路径的 `_build_middlewares()`
- `deerflow/agents/middlewares/tool_error_handling_middleware.py:70-126` — `build_lead_runtime_middlewares()`

## 两条装配路径

DeerFlow 有两个独立的 middleware 装配入口：

| | Lead Agent（生产路径） | SDK（`create_deerflow_agent`） |
|---|---|---|
| 入口 | Gateway 的 `make_lead_agent()` | `factory.py:create_deerflow_agent()` |
| 数量 | 29 个（全量） | ~10 个（精简） |
| 配置源 | `config.yaml` 各 section | `RuntimeFeatures` dataclass |
| 用户注入 | `extra_middleware` 参数 | `extra_middleware` 参数 |

Lead Agent 多了 5 个生产级 middleware：`LLMErrorHandling`（熔断器）、`SandboxAudit`（审计）、`DynamicContext`（上下文注入）、`TokenUsage`（token 统计）、`SafetyFinishReason`（安全终止检测）。

## 用户挂自己的 middleware 的 3 种方式

### 方式 1：`extra_middleware` 参数（两条路径通用）

```python
# 直接把实例加到列表里
extra_middleware = [MyCustomMiddleware()]
agent = make_lead_agent(config, extra_middleware=extra_middleware)
```

不加 `@Next`/`@Prev` 时，默认插在 `ClarificationMiddleware` 之前（链中倒数第二个位置）。

### 方式 2：`@Next`/`@Prev` 定位（两条路径通用）

```python
from deerflow.agents.features import Next, Prev
from deerflow.agents.middlewares.guardrail_middleware import GuardrailMiddleware

@Next(GuardrailMiddleware)
class MyCustomAuditMiddleware(AgentMiddleware):
    """会在 GuardrailMiddleware 之后执行"""
    ...

# 不需要手动指定位置
extra_middleware = [MyCustomAuditMiddleware()]
```

### 方式 3：`RuntimeFeatures` 替换（仅 SDK 路径）

```python
from deerflow.agents.features import RuntimeFeatures

features = RuntimeFeatures(
    guardrail=MyCustomGuardrail(),    # 替换默认 guardrail
    vision=False,                     # 禁用 vision
    subagent=True,                    # 使用默认 subagent
)
agent = create_deerflow_agent(model, tools, features=features)
```

## RuntimeFeatures: 三元开关

```python
@dataclass
class RuntimeFeatures:
    sandbox: bool | AgentMiddleware = True
    memory: bool | AgentMiddleware = False
    summarization: Literal[False] | AgentMiddleware = False  # 无内置实现
    subagent: bool | AgentMiddleware = False
    vision: bool | AgentMiddleware = False
    auto_title: bool | AgentMiddleware = False
    guardrail: Literal[False] | AgentMiddleware = False       # 无内置实现
    loop_detection: bool | AgentMiddleware = True
```

每个 feature 三选一：
- **`True`**（默认）→ 使用 DeerFlow 内置 middleware
- **`False`** → 完全跳过
- **`AgentMiddleware` 实例** → 用你的替换默认的

`summarization` 和 `guardrail` 没有 `True` 选项——因为它们的构造函数需要额外参数（summarization 需要 model；guardrail 需要 provider），不能零参创建。你必须传入自定义实例。

## `_insert_extra()` 算法

`factory.py:306-378` 的插入算法：

1. **检测冲突**：两个 extra 抢同一个 anchor（同方向或反方向）→ 报错
2. **支持交叉引用**：A `@Next(B)`，B `@Next(C)` → 最终 C → B → A
3. **环形依赖检测**：A `@Next(B)` + B `@Next(A)` → 报错
4. **无 anchor 的 extra** → 默认插在 `ClarificationMiddleware` 之前
5. **ClarificationMiddleware 强制末位**：插入完成后，如果 ClarificationMiddleware 被挤走了，把它移回末尾

```python
# 环形检测：
circular = anchor_types & remaining_types
if circular:
    raise ValueError(f"Circular dependency: {', '.join(...)}")
```

## 用户改配置后 middleware 链怎么更新

关键点：**middleware 链不是在每次 `get_app_config()` reload 时自动重建的。** 它是在每次**构建 agent** 时重新组装的。

Lead Agent 路径（`make_lead_agent`）：
- 在 `langgraph.json` 中注册为 graph factory
- LangGraph runtime 在每次 run 开始时调用
- `_build_middlewares()` 读取当前 `get_app_config()` 的各种 `.enabled` 开关
- 所以配置热重载 → 下次 run → 新的 middleware 链

SDK 路径（`create_deerflow_agent`）：
- 用户显式调用
- `_assemble_from_features()` 根据 `RuntimeFeatures` 拼装
- 调用方负责在 config 变化时重新调用

## 实际例子：加一个自定义审核 middleware

```python
from langchain.agents.middleware import AgentMiddleware
from deerflow.agents.features import Next
from deerflow.agents.middlewares.guardrail_middleware import GuardrailMiddleware

@Next(GuardrailMiddleware)
class CustomAuditMiddleware(AgentMiddleware):
    """在每个 tool call 执行后记录审计日志"""

    def wrap_tool_call(self, request, handler):
        audit_log(request.tool_call["name"], request.tool_call["args"])
        return handler(request)  # 继续执行（不短路）
```

然后在调用时：

```python
agent = make_lead_agent(config, extra_middleware=[CustomAuditMiddleware()])
```

或者在 SDK 路径：

```python
agent = create_deerflow_agent(
    model, tools,
    features=features,
    extra_middleware=[CustomAuditMiddleware()],
)
```

## 6 种 Hook 点速查

| Hook | 时机 | 执行方式 | 典型用途 |
|------|------|----------|----------|
| `before_agent` | agent graph 启动时（一次） | Graph node，正向 0→N | 初始化：thread 目录、sandbox、上传文件 |
| `before_model` | 每次 LLM 调用前 | Graph node，正向 0→N | 注入 vision 内容、检测 context loss |
| `wrap_model_call` | 包裹 LLM 调用 | 内联洋葱，正向 0→N | 错误重试、循环检测、completion 提醒 |
| `after_model` | LLM 调用后 | Graph node，**反向 N→0** | 安全终止检测、token 统计、截断 subagent 调用 |
| `wrap_tool_call` | 包裹每个 tool 执行 | 内联洋葱，正向 0→N | 权限检查、审计、错误兜底、短路 |
| `after_agent` | agent graph 结束时（一次） | Graph node，**反向 N→0** | 释放 sandbox、持久化 memory、清理状态 |

### `wrap_model_call` 签名（完整版）

```python
def wrap_model_call(
    self,
    request: ModelRequest,    # model, messages, tools, system_message,
                              # tool_choice, response_format, state, runtime
    handler: Callable[[ModelRequest], ModelCallResult],
) -> ModelCallResult:        # 通常是 AIMessage
    ...
```

### `wrap_tool_call` 签名（完整版）

```python
def wrap_tool_call(
    self,
    request: ToolCallRequest,  # tool_call (dict), tool (BaseTool | None),
                               # state, runtime
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    ...
```

### 三种状态修改方式

1. **返回 dict**（`before_*` / `after_*`）：被 LangGraph reducer 合并到 state
2. **`request.override()` + `handler()`**（`wrap_*`）：修改参数后传给内层
3. **`Command(goto=...)`**（任意 hook）：中断 graph 执行流
