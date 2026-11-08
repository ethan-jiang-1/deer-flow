# Q8: Middleware 和 Node 的关系——概念澄清

## 先回答你的三个困惑

**"是不是所有的 node 都是 LangGraph node？"**

**是的。图上每一个顶点都是 LangGraph node。** 不管它来源是什么——LangChain 原生也好、middleware 编译来的也好——最终都是 `RunnableCallable` 对象，注册在同一个 `StateGraph` 上，被 LangGraph 的 runtime 统一调度。

**"这些 node 有的是 LM 的，有的是什么？"**

图上的 node 按来源分三类：

| 来源 | 有哪些 | 谁加的 |
|------|--------|--------|
| **LangChain 固定 node** | `"model"`、`"tools"` | `create_agent()` 直接 `graph.add_node()`（`factory.py:1502` / `:1506`） |
| **Middleware hook 编译来的 node** | `"TitleMiddleware.after_model"`、`"ClarificationMiddleware.after_model"` 等 | `create_agent()` 检测到 middleware 覆写了 hook → `graph.add_node()` |
| **不存在第三种来源** | — | — |

**"middleware 在 DeerFlow 里到底是什么角色？"**

Middleware 是 DeerFlow 的**业务逻辑插件系统**。LangChain 提供了 middleware 的抽象接口（`AgentMiddleware`），DeerFlow 的 lead 链是 **39 个条目位 = 19 个共享基础层 + 20 个 lead-only 层**（v2.2.0，sync #8；v2.1.0 是 37）——负责总结、标题、记忆、错误处理、安全检查等等。每个 middleware 通过覆写 hook 方法，把自己的逻辑"注入"到 agent 循环的正确位置。

> ⚠️ **2.2.0 变化**：v2.1.0 的 `SkillToolPolicyMiddleware` 已在 v2.2.0 **删除**（`agents/middlewares/skill_tool_policy_middleware.py` 整文件已删除，#6935；`skills/tool_policy.py` 同样已删除），它那条 hook→node 位也一起下线。详见[下文](#deerflow-实际上有多少-node)。

---

## 核心概念：三个东西，别搞混

### 1. LangGraph Node（图顶点）

这是最底层概念。`StateGraph` 上的一个顶点，有 name、有执行函数（`RunnableCallable`）、通过 edge 和其他 node 连接。图运行时，LangGraph 按边的方向逐个执行 node。

### 2. LangChain AgentMiddleware（抽象类）

LangChain 定义的 Python 接口（`langchain/agents/middleware/types.py`）。它有 6 个 hook 方法可以覆写：

```python
class AgentMiddleware:
    def before_agent(self, state, runtime) -> dict | None: ...       # types.py:419
    def before_model(self, state, runtime) -> dict | None: ...       # types.py:443
    def after_model(self, state, runtime) -> dict | None: ...        # types.py:467
    def after_agent(self, state, runtime) -> dict | None: ...        # types.py:638
    def wrap_model_call(self, request, handler) -> ModelResponse: ...  # types.py:491
    def wrap_tool_call(self, request, handler) -> ToolMessage: ...     # types.py:662
```

每个方法都有对应的 `a*` 异步版本。前 4 个 hook 返回 `dict | None`（state 更新），后 2 个是洋葱拦截器。

### 3. DeerFlow Middleware（具体业务逻辑）

DeerFlow 写的具体类，每个都继承 `AgentMiddleware`，覆写自己需要的 hook。比如 `TitleMiddleware` 只覆写 `after_model`（`title_middleware.py:373`），`ToolErrorHandlingMiddleware` 只覆写 `wrap_tool_call`。

**关键关系：**

```
DeerFlow Middleware（Python 类）
    ↓ 继承
LangChain AgentMiddleware（抽象接口）
    ↓ 实现了哪些 hook？
        → 覆写了 before_agent？ → 编译成一个 LangGraph Node
        → 覆写了 before_model？  → 编译成一个 LangGraph Node
        → 覆写了 after_model？   → 编译成一个 LangGraph Node
        → 覆写了 after_agent？   → 编译成一个 LangGraph Node
        → 覆写了 wrap_model_call / wrap_tool_call？ → 不产生 Node，作为洋葱拦截器注入
```

---

## Hook → Node 的编译过程（源码级）

`factory.py`（LangChain 1.3.14 的 `langchain/agents/factory.py`，DeerFlow 锁定版本见 `backend/uv.lock:2051-2052`）。`create_agent()` 遍历 middleware 列表（`factory.py:1509-1592`），对每个 middleware 检查 4 个 hook：

```python
graph.add_node("model", RunnableCallable(model_node, amodel_node, trace=False))   # :1502
if tool_node is not None:
    graph.add_node("tools", tool_node)                                            # :1506

for m in middleware:
    # 检查 before_agent 是否被覆写（sync 或 async 任一覆写即算）
    if (m.__class__.before_agent is not AgentMiddleware.before_agent
            or m.__class__.abefore_agent is not AgentMiddleware.abefore_agent):
        sync_before_agent  = m.before_agent  if m.__class__.before_agent  is not AgentMiddleware.before_agent  else None
        async_before_agent = m.abefore_agent if m.__class__.abefore_agent is not AgentMiddleware.abefore_agent else None
        graph.add_node(f"{m.name}.before_agent",
                       RunnableCallable(sync_before_agent, async_before_agent, trace=False),
                       input_schema=resolved_state_schema)

    # before_model / after_model / after_agent 同理
    graph.add_node(f"{m.name}.before_model",  before_node, input_schema=resolved_state_schema)       # :1548
    graph.add_node(f"{m.name}.after_model",   after_node)                                            # :1569
    graph.add_node(f"{m.name}.after_agent",   after_agent_node, input_schema=resolved_state_schema)   # :1588
```

**判断方式很直接**：用 `is not` 比较子类（及其实例的类）的方法和父类的默认实现。如果子类覆写了（方法对象不是父类的那个），就创建一个 `RunnableCallable` 并 `add_node`。**sync 和 async 任一覆写都算**——这正是 `DeerFlowSummarizationMiddleware` 只在父类 `SummarizationMiddleware` 之外补了 `before_model`（`summarization_middleware.py:721`）、`TodoMiddleware` 六个 hook 全覆写却不会重复建 node 的原因。

**命名规则**：`{middleware.name}.{hook_name}`，例如 `"TitleMiddleware.after_model"`。

### 6 个 Hook 的命运

| Hook | 变成 Node？ | 在图上的表现形式 |
|------|------------|-----------------|
| `before_agent()` | ✅ 是 | `graph.add_node(f"{name}.before_agent", ...)` |
| `before_model()` | ✅ 是 | `graph.add_node(f"{name}.before_model", ...)` |
| `after_model()` | ✅ 是 | `graph.add_node(f"{name}.after_model", ...)` |
| `after_agent()` | ✅ 是 | `graph.add_node(f"{name}.after_agent", ...)` |
| `wrap_model_call()` | ❌ 否 | 在 `"model"` node 内部组成洋葱链 |
| `wrap_tool_call()` | ❌ 否 | 在 `ToolNode` 内部组成洋葱链 |

**为什么前 4 个是 node、后 2 个不是？**

因为前 4 个需要：
- **读/写 graph state**（返回 `dict` 更新 state）
- **独立的路由决策**（返回 `{"jump_to": ...}` 改变图走向）

这只能在独立的 graph node 中完成——LangGraph 的 state 更新和路由都发生在 node 之间的边上。

后 2 个是拦截器——它们在 model node / ToolNode **内部**运行，不参与图路由。它们接收 `handler` 回调，决定是否调用、调用几次、如何修改结果。这是洋葱模式，不需要独立 node。

---

## 完整的图结构

下面是一张简化的图（假设有 3 个 middleware 分别实现了不同 hook）：

```
                        START
                          │
                          ▼
              ┌──────────────────────┐
              │ M1.before_agent      │ ← 只执行一次
              │ M2.before_agent      │
              └──────────────────────┘
                          │
                          ▼
              ╔══════════════════════╗
              ║     AGENT LOOP      ║ ← 以下循环执行
              ║                      ║
              ║  ┌────────────────┐  ║
              ║  │ M1.before_model │  ║ ← 每次 LLM 调用前
              ║  │ M2.before_model │  ║
              ║  └────────────────┘  ║
              ║          │           ║
              ║          ▼           ║
              ║  ┌────────────────┐  ║
              ║  │    "model"     │  ║ ← 固定 node（内部有 wrap_model_call 洋葱链）
              ║  └────────────────┘  ║
              ║          │           ║
              ║          ▼           ║
              ║  ┌────────────────┐  ║
              ║  │ M3.after_model │  ║ ← 反向执行！后加的 middleware 先跑
              ║  │ M2.after_model │  ║
              ║  │ M1.after_model │  ║
              ║  └────────────────┘  ║
              ║          │           ║
              ║    有 tool_calls?    ║
              ║    ↙           ↘     ║
              ║ "tools"        END   ║ ← 固定 node（内部有 wrap_tool_call 洋葱链）
              ║    │                 ║
              ║    └──→ 回到 loop ──╝
              ╚══════════════════════╝
                          │
                          ▼
              ┌──────────────────────┐
              │ M2.after_agent       │ ← 只执行一次（同样反向）
              │ M1.after_agent       │
              └──────────────────────┘
                          │
                          ▼
                         END
```

**颜色说明**：
- `"model"` 和 `"tools"` —— LangChain 原生 node
- `M*.before_agent`、`M*.before_model`、`M*.after_model`、`M*.after_agent` —— middleware 编译来的 node
- **它们都在同一个 `StateGraph` 上，都是 LangGraph node**

---

## DeerFlow 实际上有多少 node？

DeerFlow 有 **39 个 middleware 条目位**（v2.2.0；组装分两阶段：`tool_error_handling_middleware.py` 的 `build_lead_runtime_middlewares()`（`:538`，内部 `_build_runtime_middlewares()` `:347`）产出共享基础层 19 条 + `lead_agent/agent.py` 的 `build_middlewares()`（`agent.py:485`）再追加 20 条 lead-only 层）。但不是每个都覆写了 4 个 node 类 hook。按 v2.2.0 源码逐个类 AST 扫描（只看 DeerFlow 侧类**自身**定义的 hook）：

| node 类 hook | 定义它的类（lead 链上） | 数量 |
|---|---|---|
| `before_agent` | ThreadData、Uploads、Sandbox、Dangling、KnowledgeScope、ToolProgress、DynamicContext、Todo（条件） | 7 常量 + 1 条件 |
| `before_model` | ArtifactCapture、Sandbox、DeferredToolFilter、McpRouting、DurableContext、Summarization（条件）、Todo（条件） | 5 常量 + 2 条件 |
| `after_model` | DurableContext、Title、TokenUsage（条件）、SubagentLimit（条件）、LoopDetection（条件）、TokenBudget（条件）、CompletedSubagentUsage（条件）、TerminalResponse、ModelLengthFinishReason、SafetyFinishReason（条件）、Clarification | 5 常量 + 6 条件 |
| `after_agent` | Sandbox、Memory、LoopDetection（条件）、TokenBudget（条件） | 2 常量 + 2 条件 |

按**默认配置**（`tool_progress`/`token_budget`/`summarization`/`subagent` 关，`loop_detection`/`token_usage`/`read_before_write` 开，plan mode 关，vision 视模型而定）估算：

```
2 个固定 node（"model" + "tools"，无工具时 "tools" 不建）
+ 7 before_agent × 1  + 5 before_model × 1  + 5 after_model × 1  + 2 after_agent × 1
= 2 + 19 ≈ 21 个 node
```

把所有可选位都打开并叠加 custom / configured-extension 槽位时，上限会到 **40 个左右**（×6 个 hook 逐一展开）。每次 agent 循环（一次 model 调用 + 可能的 tool 执行）依次经过：before_model 链 → model → after_model 链 → 条件判断 → 可能走 tools → 回到 loop。

> 🔄 同步 #6（v2.1.0-rc0）：middleware 总数 35 → 37（新增 `ToolReceiptMiddleware` #12 与 `DeferredToolPromotionAuditMiddleware` #22）。
>
> 🔄 同步 #8（v2.2.0）：37 → **39 条目位**。**删除** `SkillToolPolicyMiddleware`（`skill_tool_policy_middleware.py` 整文件已删除，#6935；`skills/tool_policy.py` 同样已删除；`allowed-tools` 降级为兼容元数据）；**新增** `KnowledgeScopeMiddleware`（#2）、`PiiRedactionMiddleware`（#5，默认关）、`ArtifactResolutionMiddleware`（#11）、`ArtifactCaptureMiddleware`（#19）、`ModelContentCompatibilityMiddleware`（#36）。共享基础层 14 → 19，lead-only 层 23 → 20。旧的 "~44 / ~46" 估算作废。

---

## 边的连接规则

### 关键节点定义（`factory.py:1592-1620`）

```python
# 入口：第一个 before_agent，或第一个 before_model，或 "model"
entry_node = middleware_w_before_agent[0].before_agent_node or \
             middleware_w_before_model[0].before_model_node or "model"      # :1592-1598

# 循环入口（tools 执行完后回到这里）：第一个 before_model 或 "model"
loop_entry_node = middleware_w_before_model[0].before_model_node or "model"  # :1601-1605

# 循环出口（model_to_tools 条件边挂在这）：第一个 after_model 或 "model"
loop_exit_node = middleware_w_after_model[0].after_model_node or "model"     # :1608-1612

# 最终出口：最后一个 after_agent 或 END
exit_node = middleware_w_after_agent[-1].after_agent_node or END             # :1615-1618
```

> ⚠️ 注意：选的是**列表里的第一个** `before_agent` / `before_model` / `after_model`，而 `after_agent` 选的是**最后一个**（因为 after_agent 反向执行，最后加的最靠近 END）。

**这四个节点的含义**：
- `entry_node`：图从哪开始
- `loop_entry_node`：每次循环从哪进入（tools 执行完后回到这里）
- `loop_exit_node`：每次循环从哪出来（`model_to_tools` 条件边挂在这，决定下一步是 tools 还是 END）
- `exit_node`：图从哪结束

### before_model 边（正向，`factory.py:1715-1733`）

```
M1.before_model → M2.before_model → ... → "model"
```

**正向**——先加的 middleware 先执行。如果你想让自己的 middleware 在 LLM 调用前注入数据，把它加在列表前面。

### after_model 边（反向，`factory.py:1737-1750`）

```python
# model 先连到最后加的 middleware
graph.add_edge("model", f"{middleware_w_after_model[-1].name}.after_model")   # :1738

# 然后倒序连：最后加的 → 倒数第二 → ... → 第一个加的
for idx in range(len(middleware_w_after_model) - 1, 0, -1):
    m1 = middleware_w_after_model[idx]
    m2 = middleware_w_after_model[idx - 1]
    _add_middleware_edge(graph, name=f"{m1.name}.after_model",
                         default_destination=f"{m2.name}.after_model", ...)
```

效果：

```
"model" → 最后一个 middleware.after_model → 倒数第二个.after_model → ... → 第一个 middleware.after_model → [条件边 → tools 或 END]
```

**反向——后加的 middleware 先执行**，最靠近 model 的输出。

⚠️ **2.2.0 的结尾顺序修正**：v2.1.0 时代这篇 FAQ 说"`ClarificationMiddleware` 在 `after_model` 里第一个检查模型输出"。2.2.0 的 `build_middlewares()` 尾部是

```
... → ModelContentCompatibility → custom* → configured* → TerminalResponse → ModelLengthFinishReason → SafetyFinishReason(cond) → Clarification
```

（`lead_agent/agent.py:747-778`）。`ClarificationMiddleware` 仍是**列表最后一个**（`agent.py:778`），所以 after_model 反向分发时它**仍然最先执行**；`SafetyFinishReasonMiddleware` 紧随其后。注意 `ModelLengthFinishReason` 与 `SafetyFinishReason` 都排在 Clarification **之前**注册，因此它们的 after_model 在反向链上排第 2/第 3。

`ClarificationMiddleware` 为什么必须最后：
- 它的 `wrap_tool_call`（`clarification_middleware.py:524`）在检测到 `ask_clarification` 时返回 `Command(update={"messages": [...]}, goto=END)`（`:518-521`）——**这是 `wrap_tool_call` 级别**的短路，不是 hook→node；
- 它的 `after_model`（`clarification_middleware.py:574-575`）只做一件事：当 `ask_clarification` 与别的工具调用出现在同一轮时，**重写 AIMessage、丢掉兄弟 tool_calls**（`_drop_parallel_non_clarification_tools`，`:395-445`），让 `create_agent` 的 `return_direct` 路由能干净地走到 END。它不设 `jump_to`。

### 每个 middleware node 都自带 jump_to 检查

`_add_middleware_edge`（`factory.py:1957-1990`）：

```python
def jump_edge(state: dict[str, Any]) -> str:
    return (
        _resolve_jump(state.get("jump_to"),
                      model_destination=model_destination,
                      end_destination=end_destination)
        or default_destination      # 没设 jump_to 就走默认路径
    )
```

只有声明了 `can_jump_to` 的 hook 才挂条件边：`@hook_config(can_jump_to=[...])` 把 `__can_jump_to__` 写在被装饰的函数上，`_get_can_jump_to()`（`factory.py:491-523`）先查 sync 覆写的方法、再查 async 覆写的方法，都没有就返回 `[]`——`[]` 让 `_add_middleware_edge` 退化成普通边，**不会**挂 `jump_edge`。v2.2.0 lead 链上真正用到它的是 **`TodoMiddleware`**：它的 `after_model` 被 `@hook_config(can_jump_to=["model"])` 标注（`todo_middleware.py:313`），发现"还有未完成 todo 但模型想收尾"时返回 `{"jump_to": "model"}`（`:372`）把 agent 拽回 loop。`ClarificationMiddleware` 走的是 `wrap_tool_call` 里的 `Command(goto=END)`，不是 `jump_to`。

---

## 从你的场景出发：哪几个 middleware 最值得读？

你的场景是**构建 agentic workflow**——让 agent 自动执行多步骤任务。DeerFlow 39 个条目位你不用全看，下面按"你最可能涉足的"挑 7 个，用它们反复强化你对 middleware 的理解。

### 必读 1：`ToolErrorHandlingMiddleware`（共享基础层 tail 内层）

**它覆写了什么 hook**：`wrap_tool_call`

**为什么重要**：这是 agent 不崩溃的底线。每个 tool 执行都在它的洋葱链里——它捕获所有异常，转成 error ToolMessage 并注入 `deerflow_tool_meta`，让模型看到错误后自己修正。**没有它，一个 bash 命令失败，整个 run 就崩了。**

**你的场景**：你的 agent 调工具（bash、文件读写、API），工具总会偶尔出错。这个 middleware 保证"做"失败了，"想"还能继续。

```python
# 效果：工具抛异常 → 不崩溃 → 模型看到 "Error: ... Please fix your mistakes."
ToolMessage(content="Error: RuntimeError('command not found')\n Please fix your mistakes.",
            tool_call_id="call_abc", status="error")
```

### 必读 2：`LLMErrorHandlingMiddleware`（共享基础层 tail）

**它覆写了什么 hook**：`wrap_model_call`

**为什么重要**：LLM API 调用也会失败——quota 耗尽、认证过期、服务繁忙。这个 middleware 在 `wrap_model_call` 洋葱链里做了指数退避重试 + 断路器。**理解它你就理解了 `wrap_model_call` 的最强用法。** 🆕 2.2：对"真空 stop"（没有任何可见内容就结束）额外给一次 model-boundary 重试，响应分类共用 `model_response.py` 的助手（`last_ai_message` `:10`、`has_tool_call_intent` `:20`、`has_visible_content` `:28`）。

**你的场景**：生产环境中 LLM 不可靠。这个 middleware 让你的 agent 在 API 抖动时自动恢复，而不是直接挂。

### 必读 3：`ClarificationMiddleware`（lead-only 最后一个，`agent.py:778`）

**它覆写了什么 hook**：`after_model`（+ `wrap_tool_call`）

**为什么重要**：这是理解"middleware 为什么是 node + after_model 为什么反向执行"的**最佳范例**。`wrap_tool_call` 检测 `ask_clarification` → 抛 `Command(goto=END)` 终止图；`after_model` 负责丢弃同轮的兄弟 tool_calls。它必须在列表最后，因为 after_model 反向执行——只有靠最后，它才能第一个看到原始 model 输出。

**你的场景**：你可能不需要反问用户，但你会需要类似的模式——在模型输出后做检查，必要时短路后续流程。这就是 `after_model` + 兄弟调用清理（或 `jump_to`）的用法模板。

### 必读 4：`SandboxMiddleware`（共享基础层 thread_hooks，`sandbox/middleware.py`）

**它覆写了什么 hook**：`before_agent`、`before_model`、`after_agent`

**为什么重要**：`before_agent` 的典型用法——在 agent 循环开始前做**一次性初始化**（获取 sandbox、存 `sandbox_id` 到 state）。它只在图启动时执行一次，`after_agent` 里做对称的释放（栈语义）。

**你的场景**：如果你的 workflow 需要在启动时做资源分配（比如创建一个临时目录、初始化一个数据库连接），就写一个 `before_agent` middleware，并在 `after_agent` 里对称释放。

### 必读 5：`TitleMiddleware`（lead-only）

**它覆写了什么 hook**：`after_model`（`title_middleware.py:373`）

**为什么重要**：最简单的 `after_model` 示例——在第一次对话交换完成后自动生成线程标题。不设 `jump_to`，不短路，只是默默观察并写 state。

**你的场景**：如果你想在模型输出后做**轻量级后处理**（比如记录日志、统计 token、检测敏感词），照这个模式写。

### 必读 6：`SummarizationMiddleware`（lead-only，条件是 `summarization.enabled`）

**它覆写了什么 hook**：`before_model`（`DeerFlowSummarizationMiddleware.before_model`，`summarization_middleware.py:721`，继承父类 `SummarizationMiddleware` 的其余行为）

**为什么重要**：展示 middleware 如何做**有状态决策**。它跟踪 token 消耗，当超过阈值时触发对话总结，把旧消息压缩成摘要。不是每次 `before_model` 都行动，而是在特定条件下。🆕 2.2：`fraction` 阈值的分母来自 **summary 模型声明的 `context_window`**（`summarization.model_name` 优先），缺 `context_window` 时降级丢弃该条款并告警。

**你的场景**：任何需要在多次循环中积累状态、在特定条件下触发的逻辑（比如"每 5 轮检查一次进度"），都参考这个模式。

> ⚠️ 2.1 时代这篇 FAQ 把 Summarization 归为 `after_agent`。2.2.0 源码里它只定义 `before_model`（另加 `wrap_model_call`），**不产生 after_agent node**。

### 必读 7：`LoopDetectionMiddleware`（lead-only，条件是 `loop_detection.enabled`）

**它覆写了什么 hook**：`before_agent`、`after_model`、`after_agent`

**为什么重要**：展示 middleware 如何做**循环检测 + 强制终止**。它比较连续几轮的 `tool_calls`，发现重复模式就清除 tool_calls 让模型给出文本回答。这是 `after_model` 的最强干预之一——不仅读输出，还修改它。🆕 2.2：检测/警告事件持久化到 `runtime/events`（`middleware:loop_detection`），警告延后到**下一圈** `wrap_model_call` 注入以保证 tool-call 配对。

**你的场景**：如果你需要检测 agent 是否陷入死循环（反复调同一个工具、反复问同一个问题），照这个模式。

### 2.2 值得补读的 3 个

| middleware | hook | 为什么
|---|---|---|
| **`TerminalResponseMiddleware`**（#39） | `after_model` | 空 terminal AIMessage 恢复：post-tool 响应仍无用户可见文本时补一条 hidden recovery 提示并重试一次，二次空响应换成 error fallback。**不新增 graph 级恢复轮次**——这是"在 node 里改 state 而不是改图"的范式 |
| **`ModelLengthFinishReasonMiddleware`** | `after_model` | provider 长度截断（`finish_reason=length` / `MAX_TOKENS`）时标 `stop_reason=model_length_capped`、**抑制该响应的 tool_calls**。和 Todo 的 `jump_to` 打配合：Todo 见到 `model_length_termination` 标记就不再拽回 loop |
| **`SafetyFinishReasonMiddleware`**（`safety_finish_reason.enabled`，默认开） | `after_model` | 检测 provider 安全终止（`finish_reason=content_filter`）并清掉被污染的 `tool_calls`。它注册在 Clarification **之前**，所以反向分发时**第二个**执行——必须赶在 LoopDetection / SubagentLimit 读 tool_calls 之前把污染清掉 |

### 这 7 个覆盖了什么

| 你学到的东西 | 通过哪个 middleware |
|-------------|-------------------|
| `wrap_tool_call` 洋葱拦截 | ToolErrorHandlingMiddleware |
| `wrap_model_call` 洋葱拦截 + 重试 | LLMErrorHandlingMiddleware |
| `after_model` 检查 + `wrap_tool_call` 的 `Command(goto=END)` 短路 | ClarificationMiddleware |
| `before_agent` 一次性初始化 / `after_agent` 对称释放 | SandboxMiddleware |
| `after_model` 轻量后处理 | TitleMiddleware |
| `before_model` 有状态条件触发 | SummarizationMiddleware |
| `after_model` 强干预（修改输出） | LoopDetectionMiddleware |

**这 7 个看完，你就能自己写 middleware 了。** 剩下 32 个是 DeerFlow 特定业务（TokenUsage、Memory、SkillActivation、ToolReceipt、DeferredToolPromotionAudit、DeferredToolFilter、ArtifactCapture/Resolution、KnowledgeScope、PiiRedaction、ModelContentCompatibility 等），需要时再看。

---

## 总结：一张表说清楚

| 问题 | 答案 |
|------|------|
| 所有 node 都是 LangGraph node？ | **是。** 不管来源，最终都是 `StateGraph` 上的 `RunnableCallable` |
| middleware 和 node 是什么关系？ | middleware 的 **hook 方法** 被编译成 node。不是 "middleware 就是 node"，而是 "hook → node" |
| 哪些 hook 变 node？ | `before_agent`、`before_model`、`after_model`、`after_agent` |
| 哪些 hook 不变 node？ | `wrap_model_call`、`wrap_tool_call`（在 node 内部，洋葱模式） |
| DeerFlow 图上有多少 node？ | 2 固定 + 约 19 个默认启用的 middleware node ≈ **21**（上限 ~40），对应 39 个 middleware 条目位（v2.2.0） |
| 为什么 after_model 反向？ | 后加的 middleware 先看到模型输出。ClarificationMiddleware 必须最后加，最先执行 |
| 每个 middleware node 能跳转吗？ | **只有声明 `can_jump_to` 的才能**。v2.2.0 lead 链上实际使用的是 `TodoMiddleware` 的 `jump_to: model` |
| 三类概念的层次？ | LangGraph Node（图顶点）← LangChain AgentMiddleware（抽象接口）← DeerFlow Middleware（业务实现） |

## 关键源码

- `langchain/agents/factory.py`（LangChain 1.3.14 库源码）：固定 node `:1502/:1506`，middleware node 创建 `:1509-1592`，关键节点定义 `:1592-1620`，before_model 边 `:1715-1733`，after_model 反向边 `:1737-1750`，after_agent 反向边 `:1753-1775`，`_add_middleware_edge` `:1957-1990`，`_get_can_jump_to` `:491-523`（先看 sync `__can_jump_to__` 再看 async）
- `langchain/agents/middleware/types.py`：`AgentMiddleware` 抽象类定义（hook 默认实现 `:419-780`，`hook_config(can_jump_to=...)` `:867`）
- `deerflow/agents/lead_agent/agent.py`：`build_middlewares()` `:485` 起，lead-only 层 20 条，尾部顺序 `:747-778`（`ClarificationMiddleware` 在 `:778` 必须最后，最后再 `compose_with_extensions()` `:786-800`）
- `deerflow/agents/middlewares/tool_error_handling_middleware.py`：`_build_runtime_middlewares()` `:347`（共享基础层 outer_wrappers → thread_hooks → tail，拼接点 `:529`）与 `build_lead_runtime_middlewares()` `:538`

> 🔄 同步 #6（v2.1.0-rc0）：middleware 组装改两阶段——共享基础层在 `build_lead_runtime_middlewares()`，lead-only 层在 `build_middlewares()`；新增 `ToolReceiptMiddleware` 与 `DeferredToolPromotionAuditMiddleware`。
>
> 🔄 同步 #8（v2.2.0）：**`SkillToolPolicyMiddleware` 已删除（`skill_tool_policy_middleware.py` 整文件，`skills/tool_policy.py` 一并，均已删除，#6935）**，37 → 39 条目位；新增 KnowledgeScope/PiiRedaction/ArtifactResolution/ArtifactCapture/ModelContentCompatibility；尾部补 TerminalResponse/ModelLengthFinishReason/SafetyFinishReason；`compose_with_extensions()`（`deerflow/extensions/stack.py`）成为唯一最终合成点，`extensions/ordering.py::core_ordering_constraints()` 在最终栈上一次性校验顺序不变量。**hook → node 的编译映射本身没有变**。

## 补充文件

- [complete-catalog.md](complete-catalog.md) —— **39 条目位的算法、两阶段拆分与 canonical 目录指引**（sync #8，v2.2.0；完整逐条表见 `_digested/internals/middleware/03-catalog.md`）
