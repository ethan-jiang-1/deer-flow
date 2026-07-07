# Q8: Middleware 和 Node 的关系——概念澄清

## 先回答你的三个困惑

**"是不是所有的 node 都是 LangGraph node？"**

**是的。图上每一个顶点都是 LangGraph node。** 不管它来源是什么——LangChain 原生也好、middleware 编译来的也好——最终都是 `RunnableCallable` 对象，注册在同一个 `StateGraph` 上，被 LangGraph 的 runtime 统一调度。

**"这些 node 有的是 LM 的，有的是什么？"**

图上的 node 按来源分三类：

| 来源 | 有哪些 | 谁加的 |
|------|--------|--------|
| **LangChain 固定 node** | `"model"`、`"tools"` | `create_agent()` 直接 `graph.add_node()` |
| **Middleware hook 编译来的 node** | `"SummaryMiddleware.after_model"`、`"TitleMiddleware.after_model"` 等 | `create_agent()` 检测到 middleware 覆写了 hook → `graph.add_node()` |
| **不存在第三种来源** | — | — |

**"middleware 在 DeerFlow 里到底是什么角色？"**

Middleware 是 DeerFlow 的**业务逻辑插件系统**。LangChain 提供了 middleware 的抽象接口（`AgentMiddleware`），DeerFlow 写了 29 个具体实现——负责总结、标题、记忆、错误处理、安全检查等等。每个 middleware 通过覆写 hook 方法，把自己的逻辑"注入"到 agent 循环的正确位置。

---

## 核心概念：三个东西，别搞混

### 1. LangGraph Node（图顶点）

这是最底层概念。`StateGraph` 上的一个顶点，有 name、有执行函数（`RunnableCallable`）、通过 edge 和其他 node 连接。图运行时，LangGraph 按边的方向逐个执行 node。

### 2. LangChain AgentMiddleware（抽象类）

LangChain 定义的 Python 接口。它有 6 个 hook 方法可以覆写：

```python
class AgentMiddleware:
    def before_agent(self, state, runtime) -> dict | None: ...
    def before_model(self, state, runtime) -> dict | None: ...
    def after_model(self, state, runtime) -> dict | None: ...
    def after_agent(self, state, runtime) -> dict | None: ...
    def wrap_model_call(self, request, handler) -> ModelResponse: ...
    def wrap_tool_call(self, request, handler) -> ToolMessage: ...
```

前 4 个 hook 返回 `dict | None`（state 更新），后 2 个是洋葱拦截器。

### 3. DeerFlow Middleware（具体业务逻辑）

DeerFlow 写的 29 个类，每个都继承 `AgentMiddleware`，覆写自己需要的 hook。比如 `TitleMiddleware` 只覆写 `after_model`，`LLMErrorHandlingMiddleware` 只覆写 `wrap_model_call`。

**关键关系：**

```
DeerFlow Middleware（Python 类）
    ↓ 继承
LangChain AgentMiddleware（抽象接口）
    ↓ 实现了哪些 hook？
        → 覆写了 before_model？ → 编译成一个 LangGraph Node
        → 覆写了 after_model？  → 编译成一个 LangGraph Node
        → 覆写了 wrap_model_call？→ 不产生 Node，作为洋葱拦截器注入
```

---

## Hook → Node 的编译过程（源码级）

`factory.py` L1372-1453。`create_agent()` 遍历 middleware 列表，对每个 middleware 检查 4 个 hook：

```python
for m in middleware:
    # 检查 before_agent 是否被覆写
    if m.__class__.before_agent is not AgentMiddleware.before_agent:
        before_agent_node = RunnableCallable(m.before_agent, m.abefore_agent)
        graph.add_node(f"{m.name}.before_agent", before_agent_node)

    # 检查 before_model 是否被覆写
    if m.__class__.before_model is not AgentMiddleware.before_model:
        before_node = RunnableCallable(m.before_model, m.abefore_model)
        graph.add_node(f"{m.name}.before_model", before_node)

    # 检查 after_model 是否被覆写
    if m.__class__.after_model is not AgentMiddleware.after_model:
        after_node = RunnableCallable(m.after_model, m.aafter_model)
        graph.add_node(f"{m.name}.after_model", after_node)

    # 检查 after_agent 是否被覆写
    if m.__class__.after_agent is not AgentMiddleware.after_agent:
        after_agent_node = RunnableCallable(m.after_agent, m.aafter_agent)
        graph.add_node(f"{m.name}.after_agent", after_agent_node)
```

**判断方式很直接**：用 `is not` 比较子类的方法和父类的默认实现。如果子类覆写了（方法对象不是父类的那个），就创建一个 `RunnableCallable` 并 `add_node`。

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
- **独立的路由决策**（通过 `jump_to` 改变图走向）

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
              │ M2.after_agent       │ ← 只执行一次
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

DeerFlow 有 29 个 middleware（`agent.py` L269-405），但不是每个都覆写了所有 4 个 hook。实际情况：

- 大部分 middleware 只覆写 `after_model` → 每个产生 1 个 node
- 少数覆写 `before_agent`（如 `UploadsMiddleware`、`SandboxMiddleware`）
- `wrap_model_call` 和 `wrap_tool_call` 不产生 node

粗略估算：**2 个固定 node + ~40 个 middleware node ≈ 图上共 ~42 个 node**。每次 agent 循环（一次 model 调用 + 可能的 tool 执行），图上大约有 15-20 个 node 被依次执行（before_model 链 → model → after_model 链 → 条件判断 → 可能走 tools → 回到 loop）。

---

## 边的连接规则

### 关键节点定义（factory.py L1455-1481）

```python
# 入口：第一个 before_agent，或第一个 before_model，或 "model"
entry_node = middleware_w_before_agent[0].before_agent or \
             middleware_w_before_model[0].before_model or "model"

# 循环入口（tools 执行完后回到这里）：第一个 before_model 或 "model"
loop_entry_node = middleware_w_before_model[0].before_model or "model"

# 循环出口（model_to_tools 条件边挂在这）：第一个 after_model 或 "model"
loop_exit_node = middleware_w_after_model[0].after_model or "model"

# 最终出口：最后一个 after_agent 或 END
exit_node = middleware_w_after_agent[-1].after_agent or END
```

**这四个节点的含义**：
- `entry_node`：图从哪开始
- `loop_entry_node`：每次循环从哪进入（tools 执行完后回到这里）
- `loop_exit_node`：每次循环从哪出来（`model_to_tools` 条件边挂在这，决定下一步是 tools 还是 END）
- `exit_node`：图从哪结束

### before_model 边（正向，L1578-1597）

```
M1.before_model → M2.before_model → ... → "model"
```

**正向**——先加的 middleware 先执行。如果你想让自己的 middleware 在 LLM 调用前注入数据，把它加在列表前面。

### after_model 边（反向，L1600-1614）

```python
# model 先连到最后加的 middleware
graph.add_edge("model", f"{middleware_w_after_model[-1].name}.after_model")

# 然后倒序连：最后加的 → 倒数第二 → ... → 第一个加的
for idx in range(len(middleware_w_after_model) - 1, 0, -1):
    graph.add_edge(
        f"{middleware_w_after_model[idx].name}.after_model",
        f"{middleware_w_after_model[idx - 1].name}.after_model",
    )
```

效果：

```
"model" → 最后一个 middleware.after_model → 倒数第二个.after_model → ... → 第一个 middleware.after_model → [条件边 → tools 或 END]
```

**反向——后加的 middleware 先执行**，最靠近 model 的输出。

这就是为什么 `ClarificationMiddleware` 必须在列表最后（L404 `middlewares.append(ClarificationMiddleware())`）。它对 `after_model` 的执行顺序敏感——它需要第一个检查模型输出，发现 `ask_clarification` 就设 `jump_to="end"` 短路整个后续流程。如果它在列表前面（= after_model 最后执行），其他 middleware 可能先把反问消息当成正常输出处理掉了。

### 每个 middleware node 都自带 jump_to 检查

`_add_middleware_edge`（L1819-1864）：

```python
def jump_edge(state: dict[str, Any]) -> str:
    return (
        _resolve_jump(state.get("jump_to"), ...)
        or default_destination  # 没设 jump_to 就走默认路径
    )
```

每个 middleware node 执行完后，条件边先检查 `state["jump_to"]`。如果某个 middleware 设置了 `jump_to="end"`，后续 middleware 直接被跳过，图跳到 END。

---

## 从你的场景出发：哪几个 middleware 最值得读？

你的场景是**构建 agentic workflow**——让 agent 自动执行多步骤任务。DeerFlow 29 个 middleware 你不用全看，下面按"你最可能涉足的"挑 7 个，用它们反复强化你对 middleware 的理解。

### 必读 1：`ToolErrorHandlingMiddleware`（共享基础层第 12 个）

**它覆写了什么 hook**：`wrap_tool_call`

**为什么重要**：这是 agent 不崩溃的底线。每个 tool 执行都在它的洋葱链里——它捕获所有异常，转成 error ToolMessage，让模型看到错误后自己修正。**没有它，一个 bash 命令失败，整个 run 就崩了。**

**你的场景**：你的 agent 调工具（bash、文件读写、API），工具总会偶尔出错。这个 middleware 保证"做"失败了，"想"还能继续。

```python
# 效果：工具抛异常 → 不崩溃 → 模型看到 "Error: ... Please fix your mistakes."
ToolMessage(content="Error: RuntimeError('command not found')\n Please fix your mistakes.",
            tool_call_id="call_abc", status="error")
```

### 必读 2：`LLMErrorHandlingMiddleware`（共享基础层第 7 个）

**它覆写了什么 hook**：`wrap_model_call`

**为什么重要**：LLM API 调用也会失败——quota 耗尽、认证过期、服务繁忙。这个 middleware 在 `wrap_model_call` 洋葱链里做了指数退避重试 + 断路器。**理解它你就理解了 `wrap_model_call` 的最强用法。**

**你的场景**：生产环境中 LLM 不可靠。这个 middleware 让你的 agent 在 API 抖动时自动恢复，而不是直接挂。

### 必读 3：`ClarificationMiddleware`（lead-only 最后一个，L404）

**它覆写了什么 hook**：`after_model`

**为什么重要**：这是理解"middleware 为什么是 node + after_model 为什么反向执行"的**最佳范例**。它的逻辑极其简单——检测 `ask_clarification` → 设 `jump_to="end"` → 图终止。但它的位置必须在列表最后，因为 after_model 反向执行。

**你的场景**：你可能不需要反问用户，但你会需要类似的模式——在模型输出后做检查，必要时短路后续流程。这就是 `after_model` + `jump_to` 的用法模板。

### 必读 4：`SandboxMiddleware`（共享基础层第 5 个）

**它覆写了什么 hook**：`before_agent`

**为什么重要**：`before_agent` 的典型用法——在 agent 循环开始前做**一次性初始化**（获取 sandbox、存 sandbox_id 到 state）。它只在图启动时执行一次，不会在每次循环都跑。

**你的场景**：如果你的 workflow 需要在启动时做资源分配（比如创建一个临时目录、初始化一个数据库连接），就写一个 `before_agent` middleware。

### 必读 5：`TitleMiddleware`（lead-only 第 19 个）

**它覆写了什么 hook**：`after_model`

**为什么重要**：最简单的 `after_model` 示例——在第一次对话完成后自动生成线程标题。不设 `jump_to`，不短路，只是默默观察并写 state。

**你的场景**：如果你想在模型输出后做**轻量级后处理**（比如记录日志、统计 token、检测敏感词），照这个模式写。

### 必读 6：`SummarizationMiddleware`（lead-only 第 16 个）

**它覆写了什么 hook**：`after_model`

**为什么重要**：展示 middleware 如何做**有状态决策**。它跟踪 token 消耗，当超过阈值时触发对话总结，把旧消息压缩成 `summary_text`。不是每次 `after_model` 都行动，而是在特定条件下。

**你的场景**：任何需要在多次循环中积累状态、在特定条件下触发的逻辑（比如"每 5 轮检查一次进度"），都参考这个模式。

### 必读 7：`LoopDetectionMiddleware`（lead-only 第 25 个）

**它覆写了什么 hook**：`after_model`

**为什么重要**：展示 middleware 如何做**循环检测 + 强制终止**。它比较连续几轮的 `tool_calls`，发现重复模式就强制清除 tool_calls 让模型给出文本回答。这是 `after_model` 的最强干预——不仅读输出，还修改它。

**你的场景**：如果你需要检测 agent 是否陷入死循环（反复调同一个工具、反复问同一个问题），照这个模式。

### 这 7 个覆盖了什么

| 你学到的东西 | 通过哪个 middleware |
|-------------|-------------------|
| `wrap_tool_call` 洋葱拦截 | ToolErrorHandlingMiddleware |
| `wrap_model_call` 洋葱拦截 + 重试 | LLMErrorHandlingMiddleware |
| `after_model` 短路（jump_to） | ClarificationMiddleware |
| `before_agent` 一次性初始化 | SandboxMiddleware |
| `after_model` 轻量后处理 | TitleMiddleware |
| `after_model` 有状态条件触发 | SummarizationMiddleware |
| `after_model` 强干预（修改输出） | LoopDetectionMiddleware |

**这 7 个看完，你就能自己写 middleware 了。** 剩下 22 个是 DeerFlow 特定业务（TokenUsage、Memory、SkillActivation、DeferredToolFilter 等），需要时再看。

---

## 总结：一张表说清楚

| 问题 | 答案 |
|------|------|
| 所有 node 都是 LangGraph node？ | **是。** 不管来源，最终都是 `StateGraph` 上的 `RunnableCallable` |
| middleware 和 node 是什么关系？ | middleware 的 **hook 方法** 被编译成 node。不是 "middleware 就是 node"，而是 "hook → node" |
| 哪些 hook 变 node？ | `before_agent`、`before_model`、`after_model`、`after_agent` |
| 哪些 hook 不变 node？ | `wrap_model_call`、`wrap_tool_call`（在 node 内部，洋葱模式） |
| DeerFlow 图上有多少 node？ | 2 固定 + ~40 middleware node ≈ 42 个 |
| 为什么 after_model 反向？ | 后加的 middleware 先看到模型输出。ClarificationMiddleware 必须最后加，最先执行 |
| 每个 middleware node 能跳转吗？ | 能。每个 node 后都有条件边检查 `jump_to` |
| 三类概念的层次？ | LangGraph Node（图顶点）← LangChain AgentMiddleware（抽象接口）← DeerFlow Middleware（业务实现） |

## 关键源码

- `langchain/agents/factory.py`：middleware node 创建 L1372-1453，关键节点定义 L1455-1481，before_model 边 L1578-1597，after_model 反向边 L1600-1614，after_agent 反向边 L1617-1639，`_add_middleware_edge` L1819-1864
- `langchain/agents/middleware/types.py`：`AgentMiddleware` 抽象类定义
- `deerflow/agents/lead_agent/agent.py`：`build_middlewares()` L269-405，展示 29 个 middleware 的完整列表和添加顺序

## 补充文件

- [complete-catalog.md](complete-catalog.md) —— **完整 29 个 middleware 一览表**（按顺序、按 hook 类型、按使用频率分类）
