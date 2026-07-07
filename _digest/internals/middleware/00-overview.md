---
title: "Middleware 设计哲学与批判性分析"
description: "29 个 middleware，6 种 hook 点，一个扁平列表。这是 DeerFlow 架构上最聪明的设计，还是只是把一堆功能塞进了叫 "middleware" 的抽屉里？"
topics: [middleware, hooks, interceptor-chain]
---

# Middleware 设计哲学与批判性分析

29 个 middleware，6 种 hook 点，一个扁平列表。这是 DeerFlow 架构上最聪明的设计，还是只是把一堆功能塞进了叫 "middleware" 的抽屉里？

## 入口处思考

作为使用者，你只需要知道两件事：**middleware 是什么**，和**你怎么加自己的**。

| 我想... | 去哪里 |
|---------|--------|
| 加一个自定义 middleware | `extra_middleware` 参数，用 `@Next(X)` / `@Prev(X)` 定位 |
| 关掉 guardrail | `config.yaml` → `guardrails.enabled: false` |
| 关掉 loop detection | `config.yaml` → `loop_detection.enabled: false` |
| 关掉 token usage 统计 | `config.yaml` → `token_usage.enabled: false` |
| 关掉自动标题 | `config.yaml` → `title.enabled: false` |
| 关掉自动总结 | `config.yaml` → `summarization.enabled: false` |
| 关掉 plan mode (todo list) | 请求时不传 `plan_mode=True` |
| 看 middleware 执行日志 | 日志级别 DEBUG，搜索 middleware 名称 |
| 换掉某个 middleware 的默认实现 | `RuntimeFeatures` 传自定义实例（SDK 路径）或 `extra_middleware` + `@Prev` 覆盖（lead agent 路径） |

**关键理解：** middleware 链是 Agent 每一次 step 都经过的管道。它不是 HTTP 层的 middleware（那是 AuthMiddleware/CSRFMiddleware 的事），而是 **Agent Loop 内部的扩展点**。

## 是什么

DeerFlow 的 middleware 系统位于 LangGraph agent loop 和 LLM/tool 执行之间。每次 agent step 都要穿过这 29 层：

```
Agent Loop 一轮 step:
  before_agent hooks → before_model hooks → [wrap_model_call onion] → LLM call
  → after_model hooks → 如果有 tool_calls → [wrap_tool_call onion] → tool 执行
  → 循环回到 before_model → ... → 没有 tool_calls 了 → after_agent hooks → END
```

基类是 LangChain 的 `AgentMiddleware[State]`（不是 DeerFlow 自己发明的协议），来自 LangChain >= 1.2.15。这意味着 middleware 的核心约定（有哪些 hook、签名什么样）是 LangChain 定的，DeerFlow 做的是**选择和排序**。

## 为什么存在

Agent loop 的核心逻辑极其简单：**call model → execute tools → repeat**。但实际产品需要：

- 注入系统上下文（日期、memory）→ DynamicContextMiddleware
- 防止 LLM 错误导致崩溃 → LLMErrorHandlingMiddleware / ToolErrorHandlingMiddleware
- 安全审计 → GuardrailMiddleware / SandboxAuditMiddleware
- 资源管理 → SandboxMiddleware (acquire/release)
- 防止死循环 → LoopDetectionMiddleware
- 自动标题/总结/统计 → TitleMiddleware / SummarizationMiddleware / TokenUsageMiddleware
- 文件上传预处理 → UploadsMiddleware
- 子 agent 限制 → SubagentLimitMiddleware
- ...

如果没有 middleware，这些都得塞进 agent loop 核心代码里。有了 middleware，每个关注点隔离在自己的类里，agent loop 核心保持简洁。

## 核心理念

两个原则支配整个设计：

### 1. Onion Composition（洋葱组合）for `wrap_*`

`wrap_model_call` 和 `wrap_tool_call` 不是 graph node，是**内联嵌套的 callable 链**。第一个 middleware 的 wrapper 是最外层，它调用 `handler(request)` 进入下一层，以此类推，最内层是真正的 model 调用或 tool 执行：

```
wrap_tool_call 洋葱:
  GuardrailMiddleware.wrap_tool_call        ← 最外层：看 tool_name，决定 allow/deny
    → handler(request)
      SandboxAuditMiddleware.wrap_tool_call  ← 第 2 层：看 bash 命令，regex 匹配
        → handler(request)
          ToolErrorHandlingMiddleware.wrap_tool_call  ← 第 3 层：try/except 兜底
            → handler(request)
              真正执行 tool
```

这和 WSGI/ASGI middleware 的 "Russian doll" 模式一模一样。外层可以看到 request（修改参数或拒绝），也能看到 response（修改返回值）。

### 2. Forward Setup / Reverse Teardown for `before_*` / `after_*`

`before_agent` 和 `before_model` 按链顺序执行（0→N）。`after_model` 和 `after_agent` 按**反向**执行（N→0）。

这保证了一个 middleware 的 setup 和 teardown 是对称的——就像栈的 push/pop，或者 `try/finally`：

```
before_agent[0] → before_agent[1] → ... → before_agent[N]  (setup: first registered = first to setup)
  ... agent 执行 ...
after_agent[N] → after_agent[N-1] → ... → after_agent[0]    (teardown: first registered = last to teardown)
```

这是 LangChain `create_agent()` 在 graph edge 接线时硬编码的行为。DeerFlow 只是利用了它。

**特别重要的例子：** SafetyFinishReasonMiddleware 特意注册在 custom middleware 之后（接近链末尾），正是因为 `after_model` 反向执行——最后注册的最先执行——Safety 必须第一个看到 model 的原始输出，在 LoopDetection 和 SubagentLimit 处理之前清除被 safety filter 污染的 tool_calls。这个排序决策说明 DeerFlow 团队**理解**反向分发的含义并有意识地利用它。

## 与 Flask middleware 的对比

| 维度 | Flask | DeerFlow |
|------|-------|----------|
| **注册方式** | `@app.before_request` 装饰器 | 列表 append，硬编码在 `_build_middlewares()` |
| **执行顺序** | 装饰器调用顺序 | 列表索引顺序 |
| **Hook 粒度** | `before_request` / `after_request` / `teardown_request` | 6 种：`before_agent` / `before_model` / `after_model` / `after_agent` / `wrap_model_call` / `wrap_tool_call` |
| **Request 修改** | 通过 `request` 全局对象（thread-local proxy） | 通过 `state` dict 或 `request.override()` 不可变模式 |
| **Response 修改** | `after_request` 接收并返回 response | `after_model`/`after_agent` 返回 dict 被 LangGraph reducer 合并；`wrap_*` 直接返回替代值 |
| **短路能力** | `before_request` 返回 response 即短路 | `wrap_tool_call` 不调 `handler()` 即短路；`Command(goto=END)` 中断 graph |
| **上下文传递** | `g` 对象（thread-local） | `runtime.state`（LangGraph state dict） |
| **错误处理** | Flask 有默认 error handler | 无集中错误处理——每个 middleware 自己管自己 |
| **第三方扩展** | `flask_cors`、`flask_limiter` 等 pip 包 | `extra_middleware` 参数 + `@Next`/`@Prev` 定位 |
| **定位控制** | 无——完全取决于 `@app.before_request` 调用顺序 | `@Next(Anchor)` / `@Prev(Anchor)` 显式定位 |

**核心差异：** Flask 的 middleware 注册是**声明式**的（装饰器分散在各处），DeerFlow 的 middleware 装配是**命令式**的（一个函数里集中组装）。Flask 的方式更灵活但顺序难以追踪；DeerFlow 的方式顺序一目了然但不够"开放"。

DeerFlow 更像**在 Flask 的 `before_request`/`after_request` 基础上，额外引入了 WSGI 中间件的洋葱包装模式**。它是两者的混合体——`before_*`/`after_*` 是 Flask 风格（分散的 hook 节点），`wrap_*` 是 WSGI 风格（嵌套的 callable 链）。

### 与 Claude Code Hooks 的关系

如果你用过 Claude Code，会发现它的 Hooks 系统和 DeerFlow 的 Middleware 在理念上**高度一致**——两者都在 Agent 生命周期的关键节点挂入自定义逻辑。Claude Code 的 `PreToolUse` ≈ DeerFlow 的 `wrap_tool_call`（Guardrail），`PostToolUse` ≈ `wrap_tool_call`（ToolErrorHandling），`SessionStart` ≈ `before_agent`。

核心分歧不在理念，而在实现选择：Claude Code 面向终端用户（声明式 JSON、任意语言、外部进程、并行执行），DeerFlow 面向框架开发者（Python 类、代码装配、有序洋葱链）。

详见 **[04-claude-code-comparison.md](04-claude-code-comparison.md)** — 含完整概念映射表、设计哲学对比、互相借鉴分析。

## 漂亮的地方

### 1. 洋葱组合给了 middleware 完整的控制权

`wrap_tool_call` 和 `wrap_model_call` 的 middleware 可以看到 request 和 response 两端。GuardrailMiddleware 可以在 tool 执行前拦截，ToolErrorHandlingMiddleware 可以在 tool 抛异常后补救，TodoMiddleware 可以在 model 输出后注入提醒。比单纯的 `before`/`after` hook 强大得多。

### 2. @Next/@Prev 定位系统优雅解决了排序问题

Flask 的 `@app.before_request` 装饰器顺序完全取决于 Python 文件的 import 顺序——脆弱、隐式、难以追踪。DeerFlow 的 `@Next(ClarificationMiddleware)` / `@Prev(GuardrailMiddleware)` 是**显式、声明式**的定位，带冲突检测（两个 middleware 抢同一个 anchor 会报错），支持交叉引用（A 跟在 B 后面，B 跟在 C 后面，最终 C→B→A）。

这是这套系统最让我惊喜的设计。`_insert_extra()` 的实现（`factory.py:306-378`）用迭代插入 + 环形依赖检测，干净利落。

### 3. LoopDetection 的警告注入时机体现了对 LLM provider 的深刻理解

LoopDetectionMiddleware 在 `after_model` 中检测到重复 tool call 循环后，**不在 `after_model` 中注入警告消息**。因为 OpenAI 和 Moonshot 要求 AIMessage(tool_calls) 后面紧跟对应的 ToolMessage——在中间插入 HumanMessage 会破坏这个配对校验。

所以警告被放入 `_pending_warnings` 队列，延迟到 `wrap_model_call` 中、**在下一个 AIMessage 生成之前**才注入。这是对 provider 约束的精确应对，不是随便写的。

### 4. ClarificationMiddleware 的最后位置 + Command(goto=END) 是干净的控制流

ClarificationMiddleware 拦截 `ask_clarification` tool call，不执行 tool，直接返回 `Command(goto=END)`——跳转到 graph 的 END 节点，中断 agent 执行，等待用户回复。这个机制利用了 LangGraph 的 `Command` primitive，干净地实现了 "agent 向用户提问→暂停→用户回答→继续" 的交互模式。

强制 ClarificationMiddleware 必须在链末尾（否则它之后的 middleware 永远不会执行，因为 `goto=END` 跳过了它们）——这个 invariant 在两条装配路径中都被显式 enforce。

### 5. RuntimeFeatures 的 True/False/自定义实例 API 很干净

```python
class RuntimeFeatures:
    guardrail: bool | AgentMiddleware = True   # True=用默认, False=关闭, AgentMiddleware实例=替换
    summarization: bool | AgentMiddleware = True
    loop_detection: bool | AgentMiddleware = True
    ...
```

三元开关（默认/关闭/自定义）给了使用者精确的控制粒度，比一堆 `enable_xxx: bool` 的 config key 灵活太多。

## 不足的地方

### 1. 扁平硬编码位置——没有优先级系统

29 个 middleware 的位置是 `_build_middlewares()` 里的 append 顺序决定的。如果你想让自己的 middleware 插在 GuardrailMiddleware 和 SandboxAuditMiddleware 之间，你必须知道它们的类名并用 `@Next`/`@Prev`。

Flask 后来也面临同样的问题——Blueprints 的 `before_request` 执行顺序取决于 blueprint 注册顺序，调试起来很痛苦。更成熟的方案是**优先级数字**（如 Django middleware 的 `MIDDLEWARE` 列表里每个元素有明确的序号），或者**阶段分组**（如 `SERVER`, `SECURITY`, `APPLICATION`, `OBSERVABILITY`）。

DeerFlow 的 `@Next`/`@Prev` 部分解决了这个问题，但只要有人动了 `_build_middlewares()` 里的顺序（比如把一个 middleware 往上挪了三位），所有依赖那个 anchor 的第三方 middleware 的插入位置都会被意外改变。

### 2. 两条装配路径有重复代码

`_build_middlewares()` (lead_agent/agent.py:266) 和 `_assemble_from_features()` (factory.py:155) 是两个独立的函数，各自维护一份 middleware 装配逻辑。两条路径的 middleware 集合不完全一致（factory 路径少了 LLMErrorHandling、SandboxAudit、DynamicContext、TokenUsage、DeferredToolFilter、SafetyFinishReason），而且同一 middleware 在两条路径中的位置也不同。

这就意味着：**你在 lead agent 路径下测试通过的 middleware 行为，在 SDK 路径下可能不一样。** 两条路径应该共享同一份 middleware 列表构建逻辑，只通过 config/feature flag 控制开关。

### 3. 没有 middleware 间的错误隔离

一个 middleware 在 `before_agent` 中抛异常 → 后续所有 middleware 的 `before_agent` 全部跳过。没有 try/except 包裹每个 middleware 的执行。这意味着一个第三方 middleware 的 bug 可以让整个 agent 崩溃。

对比 Flask：虽然 Flask 也没有在 `before_request` 之间加错误隔离，但 Flask 有全局 error handler 可以兜底。DeerFlow 的 middleware 没有任何安全网。

### 4. wrap_model_call 内联执行——慢 middleware 阻塞 model 调用

`wrap_model_call` 的所有洋葱层在 `model_node` 内部**同步执行**。如果一个 middleware 的 `wrap_model_call` 做了耗时操作（比如发网络请求做内容审核），它直接阻塞 LLM 调用。对比：`before_model` 是独立的 graph node，可以异步执行。`wrap_model_call` 应该是轻量的（参数修改、日志记录），重操作应该放在 `before_model` 或 `after_model`。

目前所有内置 middleware 的 `wrap_model_call` 实现都是轻量的（LLMErrorHandling 的 retry 除外，但那是必要的），但第三方 middleware 不一定遵守这个约定。

### 5. 基类来自 unreleased LangChain 版本

`AgentMiddleware` 的 import 路径 `langchain.agents.middleware` 在当前安装的 langchain 0.3.x 中不存在。pyproject.toml 依赖 `langchain>=1.2.15`，但这是一个未来版本。这意味着：

- 如果 LangChain 改了 `AgentMiddleware` 的接口，DeerFlow 的所有 middleware 都得跟着改
- 没法用当前 langchain 版本的 `AgentMiddleware` 做类型检查或 IDE 补全
- 这是架构上的耦合风险——middleware 系统是 DeerFlow 最核心的扩展机制，但它的基类定义不在 DeerFlow 控制范围内

## 总体评价

**这套 middleware 是认真设计过的，不是拍脑袋的。** 证据：

1. 洋葱组合 + 反向 teardown 的组合拳说明作者理解 middleware 模式的内在逻辑（不只是抄了个名字）
2. LoopDetection 的延迟警告注入说明作者测试过 OpenAI/Moonshot 的 message 配对约束并为之做了适配
3. `@Next`/`@Prev` 定位 + 冲突检测 + 循环依赖检测说明作者预见到了第三方 middleware 的集成需求
4. SafetyFinishReason 的排序（利用反向分发获得最先执行权）说明作者有意识地利用执行顺序特性

**但它不够"open"。** Flask 的 middleware 生态系统之所以繁荣，是因为任何人都可以 `pip install flask-xxx` 然后装饰一下就接入。DeerFlow 的 middleware 需要你了解 29 个 middleware 的位置关系、选了正确的 anchor、处理 `@Next`/`@Prev` 的冲突——门槛远高于 Flask。这是一个**内部架构的整洁 > 外部扩展的便利**的选择——对于 ByteDance 的内部项目可能合理，对于开源项目可能限制了社区贡献。

**类比：** 如果 Flask 是自动挡（装饰器随便加，框架自己理顺序），DeerFlow 就是手动挡（`@Next(A)` 挂三档，`@Prev(B)` 挂四档）——更精确、更可控，但需要你知道档位在哪。

## 完整示例：自定义 Middleware

```python
from langchain.agents.middleware import AgentMiddleware, Next, Prev
from deerflow.agents.middlewares.tool_error_handling_middleware import ToolErrorHandlingMiddleware

class AuditLoggingMiddleware(AgentMiddleware):
    """每次 tool 执行后记录审计日志。"""

    def after_tool(self, state, runtime):
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "name"):
            print(f"[AUDIT] tool={last_msg.name} thread={runtime.context.get('thread_id')}")
        return None  # 不修改 state

# 使用 extra_middleware 注入（自动定位在 ToolErrorHandling 之前）
from deerflow.agents.factory import create_deerflow_agent, RuntimeFeatures
agent = create_deerflow_agent(
    model=model,
    features=RuntimeFeatures(sandbox=True),
    extra_middleware=[(AuditLoggingMiddleware(), Prev(ToolErrorHandlingMiddleware))],
)
```

`@Next(X)` / `@Prev(X)` 定位机制让你精确控制插入位置，无需知道链中其他 middleware 的索引。
