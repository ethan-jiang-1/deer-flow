# 链装配：Middleware 是怎么串起来的

两条装配路径，一套定位系统。理解这个才能知道怎么把自己的 middleware 挂上去。

## 入口处思考

| 我想... | 去哪里 |
|---------|--------|
| 在 lead agent 中加 middleware | `extra_middleware` 参数，或直接改 `_build_middlewares()`（不推荐） |
| 在 SDK/create_deerflow_agent 中加 middleware | `extra_middleware` 参数，通过 `RuntimeFeatures` 控制开关 |
| 让 middleware 在某个特定 middleware 之后执行 | 类上加 `@Next(ThatMiddleware)` |
| 让 middleware 在某个特定 middleware 之前执行 | 类上加 `@Prev(ThatMiddleware)` |
| 看完整的 middleware 装配代码 | `deerflow/agents/lead_agent/agent.py:_build_middlewares()` (lead agent) 或 `deerflow/agents/factory.py:_assemble_from_features()` (SDK) |

## 两条装配路径

DeerFlow 有两条独立的 middleware 装配路径，共享大部分 middleware 但集合不同、顺序不同。

### 路径 A: Lead Agent（应用级）

`deerflow/agents/lead_agent/agent.py:_build_middlewares()` (line 266)

分两步：
1. `build_lead_runtime_middlewares()` (`tool_error_handling_middleware.py:70-126`) 返回前 8 个
2. `_build_middlewares()` 追加剩余 11 个

```python
# 简化逻辑
def _build_middlewares(config, ...):
    middlewares = build_lead_runtime_middlewares(...)
    # 返回: ThreadData, Uploads, Sandbox, DanglingToolCall,
    #       LLMErrorHandling, Guardrail(条件), SandboxAudit, ToolErrorHandling

    middlewares.append(DynamicContextMiddleware(...))

    if config.summarization.enabled:
        middlewares.append(SummarizationMiddleware(...))

    if is_plan_mode:
        middlewares.append(TodoMiddleware(...))

    if config.token_usage.enabled:
        middlewares.append(TokenUsageMiddleware(...))

    middlewares.append(TitleMiddleware(...))
    middlewares.append(MemoryMiddleware(...))

    if model_supports_vision:
        middlewares.append(ViewImageMiddleware(...))

    if config.tool_search.enabled:
        middlewares.append(DeferredToolFilterMiddleware(...))

    if subagent_enabled:
        middlewares.append(SubagentLimitMiddleware(...))

    if config.loop_detection.enabled:
        middlewares.append(LoopDetectionMiddleware(...))

    # 自定义 middleware 插入点
    middlewares.extend(extra_middleware)

    if config.safety_finish_reason.enabled:
        middlewares.append(SafetyFinishReasonMiddleware(...))

    middlewares.append(ClarificationMiddleware(...))  # 强制最后
    return middlewares
```

**19 个 middleware**，5 个是条件性的（Guardrail、Summarization、TokenUsage、LoopDetection、SafetyFinishReason），2 个是运行时决定的（Todo=plan_mode、SubagentLimit=subagent_enabled）。

### 路径 B: SDK（`create_deerflow_agent`）

`deerflow/agents/factory.py:_assemble_from_features()` (line 155)

接受 `RuntimeFeatures` dataclass 和 `extra_middleware` 列表：

```python
# 简化逻辑
def _assemble_from_features(features: RuntimeFeatures, extra_middleware, ...):
    middlewares = [
        ThreadDataMiddleware(),
        UploadsMiddleware(),
        SandboxMiddleware(),
        DanglingToolCallMiddleware(),
    ]

    if features.guardrail is not False:
        middlewares.append(features.guardrail if isinstance(features.guardrail, AgentMiddleware)
                          else GuardrailMiddleware())

    middlewares.append(ToolErrorHandlingMiddleware())  # 注意：无 SandboxAudit

    if features.summarization is not False:
        middlewares.append(features.summarization if isinstance(...)
                          else SummarizationMiddleware())

    if plan_mode:
        middlewares.append(TodoMiddleware())

    if features.auto_title is not False:
        middlewares.append(TitleMiddleware())

    if features.memory is not False:
        middlewares.append(MemoryMiddleware())

    if features.vision is not False:
        middlewares.append(ViewImageMiddleware())

    if features.subagent is not False:
        middlewares.append(SubagentLimitMiddleware())

    if features.loop_detection is not False:
        middlewares.append(LoopDetectionMiddleware())

    # 插入 extra
    _insert_extra(middlewares, extra_middleware)

    middlewares.append(ClarificationMiddleware())  # 强制最后
    return middlewares
```

### 两条路径的差异

| | Lead Agent | SDK (create_deerflow_agent) |
|---|---|---|
| **Middleware 数量** | 19（全量） | 13（精简） |
| **缺少的 middleware** | — | LLMErrorHandling, SandboxAudit, DynamicContext, TokenUsage, DeferredToolFilter, SafetyFinishReason |
| **位置差异** | ToolErrorHandling 在位置 7 | ToolErrorHandling 在位置 5 |
| **配置来源** | `config.yaml` 各 section | `RuntimeFeatures` dataclass |
| **自定义方式** | `extra_middleware` 列表 | `extra_middleware` 列表 |
| **适用场景** | Gateway 启动的 agent | 嵌入式/第三方集成 |

**为什么有这个差异？** Lead agent 是全功能的生产路径——需要 circuit breaker、沙箱审计、token 统计。SDK 路径是轻量的集成接口——使用者可能只想跑一个简单的 agent，不需要这些生产级关注点。但这也意味着**两条路径的 middleware 行为不完全一致**，如果你从 SDK 切到 lead agent 路径（或反过来），middleware 的执行会有差异。

## RuntimeFeatures: 三元开关

`deerflow/agents/features.py:15`:

```python
@dataclass
class RuntimeFeatures:
    guardrail: bool | AgentMiddleware = True
    summarization: bool | AgentMiddleware = True
    loop_detection: bool | AgentMiddleware = True
    auto_title: bool | AgentMiddleware = True
    memory: bool | AgentMiddleware = True
    vision: bool | AgentMiddleware = True
    subagent: bool | AgentMiddleware = True
```

每个 feature 三个选项：
- **`True`**（默认）— 使用 DeerFlow 内置的 middleware 实现
- **`False`** — 完全跳过这个 feature（middleware 不会加入链）
- **`AgentMiddleware 实例`** — 用你自己的实现替换默认的

两个 feature 没有内置实现：`summarization` 和 `guardrail`。它们只接受 `False` 或自定义实例。

这是这个系统在 "可配置性" 维度最精妙的设计。不需要 20 个 `enable_xxx: bool` 的 config key——一个 dataclass 同时控制了开关和自定义实现。

## @Next / @Prev 定位系统

`deerflow/agents/features.py:42-63`:

```python
class Next:
    """放在目标 middleware **之后**"""
    def __init__(self, anchor: type[AgentMiddleware]): ...

class Prev:
    """放在目标 middleware **之前**"""
    def __init__(self, anchor: type[AgentMiddleware]): ...
```

使用方式——在你的 middleware 类上直接装饰：

```python
@Next(GuardrailMiddleware)
class MyCustomAuditMiddleware(AgentMiddleware):
    """会在 GuardrailMiddleware 之后执行"""
    ...
```

```python
@Prev(ClarificationMiddleware)
class MyCustomTool(AgentMiddleware):
    """会在 ClarificationMiddleware 之前执行"""
    ...
```

### 插入算法

`_insert_extra()` (`factory.py:306-378`) 的规则：

1. 检查 19 个 anchor 都在当前链中（不在 → 报错）
2. 遍历 extra 列表，对每个找到它的 anchor，插入到正确位置
3. 支持交叉引用——A 跟在 B 后面，B 跟在 C 后面，最终顺序 C→B→A
4. 环形依赖 → 报错
5. 两个 extra 抢同一个 anchor（同方向或反方向）→ 报错
6. 没有 anchor 的 extra → 默认插在 `ClarificationMiddleware` 之前
7. 最后强制 `ClarificationMiddleware` 到末尾

### 设计评价

这个定位系统**比 Flask 的隐式 import-order 强太多**，但仍有脆弱性：如果你的 `@Next(GuardrailMiddleware)` 依赖于 GuardrailMiddleware 在链中的位置（比如它必须是 `wrap_tool_call` 的第 5 个），而 DeerFlow 升级把 GuardrailMiddleware 移到了位置 8，你的 middleware 会跟着移动但你不知道。

理想情况是 middleware 声明自己需要什么**阶段**（如 `Phase.SECURITY`, `Phase.AUDIT`），而不是绑定到具体的 middleware 类名。但 `@Next`/`@Prev` 在实用性和简单性上已经足够好了。

## Subagent 的 Middleware 链

Subagent 使用精简的链，由 `build_subagent_runtime_middlewares()` (`tool_error_handling_middleware.py:139`) 构建。只包含核心 middleware：ThreadData、Sandbox、DanglingToolCall、LLMErrorHandling、Guardrail（条件）、SandboxAudit、ToolErrorHandling、Clarification。

Subagent 不需要 TitleMiddleware（子 agent 不生成标题）、不需要 DynamicContextMiddleware（上下文从父 agent 继承）、不需要 SummarizationMiddleware（子 agent 的消息量小）。

## Config 驱动的 Middleware 开关

| Config Key | 控制的 Middleware |
|---|---|
| `guardrails.enabled` | GuardrailMiddleware |
| `sandbox.use` | SandboxMiddleware (provider 选择) |
| `summarization.enabled` | DeerFlowSummarizationMiddleware |
| `token_usage.enabled` | TokenUsageMiddleware |
| `title.enabled` | TitleMiddleware |
| `memory.enabled` | MemoryMiddleware |
| `tool_search.enabled` | DeferredToolFilterMiddleware |
| `loop_detection.enabled` | LoopDetectionMiddleware |
| `safety_finish_reason.enabled` | SafetyFinishReasonMiddleware |
| `models[name].supports_vision` | ViewImageMiddleware |
| `circuit_breaker.failure_threshold` | LLMErrorHandlingMiddleware (参数) |

注意：很多 middleware 没有开关——它们是**非可选的**（ThreadData、Uploads、Sandbox、DanglingToolCall、ToolErrorHandling、Title、Memory、Clarification）。要移除它们只能通过 `extra_middleware` + `@Prev` 覆盖（或用 `RuntimeFeatures` 在 SDK 路径关闭，但 SDK 路径本来就没有全部这些 middleware）。
