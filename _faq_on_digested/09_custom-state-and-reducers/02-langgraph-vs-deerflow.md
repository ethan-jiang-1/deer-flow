# LangGraph 打地基，DeerFlow 盖房子

## LangGraph 的 AgentState：最简地基

LangChain 的 `AgentState`（`langchain/agents/middleware/types.py` L347-353，实装 langchain 1.3.14）只有三个字段：

```python
class AgentState(TypedDict, Generic[ResponseT]):
    messages: Required[Annotated[list[AnyMessage], add_messages]]                                  # L350
    jump_to: NotRequired[Annotated[JumpTo | None, EphemeralValue, PrivateStateAttr]]               # L351
    structured_response: NotRequired[Annotated[ResponseT, OmitFromInput]]                          # L352
```

| 字段 | 作用 | Reducer / 标记 |
|------|------|---------|
| `messages` | 对话历史——所有 HumanMessage、AIMessage、ToolMessage | `add_messages`（追加） |
| `jump_to` | middleware 改流向：`"tools"` / `"model"` / `"end"` | `EphemeralValue`（读一次消失）+ `PrivateStateAttr` |
| `structured_response` | 结构化输出解析结果 | 用 LangChain 的 OmitFromInput 标记——不从调用方 input 接收，只能由 model node 写 |

就这三个。LangChain 不假定你在做什么应用——聊天机器人、代码助手、客服系统，都从这三个字段开始。

> 🔄 同步 #8（v2.2.0）：旧版写「只有两个字段」并漏了 `structured_response`；实装 langchain 1.3.14 是三个。另外 `jump_to` 的取值是 `Literal["tools", "model", "end"]`（`types.py` L66），不是只有 `"end"`——它也不是「逃生口」而是**唯一的合法流向原语**：`wrap_model_call` 里返回 `Command(goto=...)` 会 `NotImplementedError`（`agents/factory.py` L213-227），只能改用 `jump_to`。详见 [Q7 §3.3](../07_graph-nodes/answer.md)。

## DeerFlow 的 ThreadState：给地基盖了三层楼

`deerflow/agents/thread_state.py` L379-397（**逐字对照 v2.2.0，共 17 个自有字段**）：

```python
class ThreadState(AgentState):                                            # L379 继承 AgentState
    sandbox: SandboxStateField                                            # L380
    thread_data: NotRequired[ThreadDataState | None]                      # L381
    title: NotRequired[str | None]                                       # L382
    artifacts: Annotated[list[str], merge_artifacts]                      # L383
    todos: Annotated[list | None, merge_todos]                            # L384
    goal: Annotated[GoalState | None, merge_goal]                          # L385
    goal_outcome: NotRequired[GoalOutcomeState | None]                     # L386  ← 2.2.0
    uploaded_files: NotRequired[list[dict] | None]                        # L387
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]  # L388
    promoted: Annotated[PromotedTools | None, merge_promoted]             # L389
    delegations: Annotated[list[DelegationEntry], merge_delegations]       # L390
    skill_context: Annotated[list[SkillEntry], merge_skill_context]         # L391
    tool_artifacts: Annotated[list[ArtifactEntry], merge_tool_artifacts]    # L392
    tool_artifact_processed: Annotated[list[str], merge_artifacts]          # L393
    task_notes: Annotated[dict | None, TaskNotesChannel(dict | None, merge_task_notes)]  # L394
    task_history: NotRequired[dict | None]                                # L395
    summary_text: NotRequired[str | None]                                 # L396
    background_tasks: NotRequired[list[BackgroundTaskState]]               # L397
```

> 🔄 同步 #8（v2.2.0）：旧版这段代码块**漏了四个字段、并把行号写成 L280+**。真实差异：(1) 新增 `goal_outcome`（目标判定的终局态，与 `goal` 分开存——`goal` 是「当前目标」，`goal_outcome` 是「这个目标判成什么」）；(2) 新增 `tool_artifacts` 与 `tool_artifact_processed`（工具产出的结构化工件清单 + 「哪些已被消费」的账本，对应 2.2.0 的 artifact 消费语义）；(3) `task_notes` 的 reducer 是**类**不是函数：`TaskNotesChannel(dict | None, merge_task_notes)`，`TaskNotesChannel` 定义在 `agents/task_continuity/state.py` L92，继承 LangGraph 的 `BinaryOperatorAggregate`。另外 `DelegationEntry`（thread_state.py L197-215）含 `receipt_verdict` / `acceptance_verdict`，`ViewedImageData`（L62-76）含 `sha256` / `source_sandbox_id`。中间件与字段的归属见 [_digested/internals/middleware/03-catalog.md](../../_digested/internals/middleware/03-catalog.md)。

### 每个字段谁能读、谁能写

这是理解 state 的实战关键——不是所有 node 都能写所有字段：

| 字段 | 谁写 | 谁读 |
|------|------|------|
| `messages` | model node（AIMessage）、ToolNode（ToolMessage）、middleware | 所有 node |
| `jump_to` | middleware 的 `before_model`/`after_model`/`before_agent`/`after_agent` 钩子（返回 `{"jump_to": "model"}` 等）；须先在 `hook_config(can_jump_to=...)` 里声明目标 | 条件边函数（`jump_edge` / `model_to_tools`） |
| `sandbox` | `SandboxMiddleware`（初始化时） | sandbox tools（执行命令时） |
| `thread_data` | `ThreadDataMiddleware`（初始化时） | sandbox tools |
| `title` | `TitleMiddleware`（第一次对话后） | 前端展示、Gateway API |
| `artifacts` | sandbox tools（`present_files`） | 前端展示 |
| `todos` | `write_todos` tool（plan mode） | 前端展示（任务列表卡片） |
| `goal` | `PUT /goal` API、`set_goal()` | goal evaluator（每轮后检查） |
| `uploaded_files` | `UploadsMiddleware` | 前端展示、agent 上下文 |
| `viewed_images` | `ViewImageMiddleware` | model node（注入 base64） |
| `promoted` | `describe_skill` tool | `DeferredToolFilterMiddleware` |
| `delegations` | `DurableContextMiddleware` | model node（注入上下文） |
| `skill_context` | `SkillActivationMiddleware` | model node（注入上下文） |
| `summary_text` | `SummarizationMiddleware` | model node（注入上下文） |
| `task_notes` / `task_history` | task_continuity tools（`write_task_notes` 等） | model node（恢复任务上下文） |
| `goal_outcome` | goal evaluator（判定完成后写终局态） | Gateway API、前端 | ← 2.2.0 新增 |
| `tool_artifacts` / `tool_artifact_processed` | 产出工件的工具（写清单）+ 消费方（写已消费账本） | model node、`present_files` 一类工具 | ← 2.2.0 新增 |

**关键洞察**：大部分字段是"特定 middleware 写，model node 读"。这就是 middleware → state → model 的数据流。

### DeerFlow 的自定义 Reducer

这些都是从 DeerFlow 源码直接提取的，位于 `thread_state.py`：

| Reducer | 逻辑 | 为什么不用 last_value |
|---------|------|----------------------|
| `merge_artifacts` | 并集 + 去重 | 多个 tool 同时产出文件，后面的不应该覆盖前面的 |
| `merge_viewed_images` | dict 合并（支持 middleware 清空） | 图片缓存按 path 合并，处理完可整体清除 |
| `merge_todos` | `None` = 保留旧值，非 `None` = 覆盖 | `write_todos` 不返回 todos 时不应该清空已有列表 |
| `merge_delegations` | 追加，同 ID 最新胜，终态保护，上限 50 | 多个子任务同时完成，状态不能互相覆盖 |
| `merge_promoted` | catalog-hash 作用域，catalog 变更时全替换 | catalog 更新后，旧 promotion 应该失效 |
| `merge_skill_context` | 按 path 去重，最近读取优先，上限 8 | 重复读同一个 skill 不应重复存储 |
| `merge_task_notes` | task_continuity 笔记合并 | 🔄 同步 #6 新增：跨轮任务笔记不应互相覆盖 |
| `merge_sandbox` | 沙箱状态合并（`thread_state.py` L79） | 沙箱重建时只覆盖变化的键，不整块替换 |
| `merge_goal` | 目标状态合并（L152） | 目标分多步更新，不能一步写丢前面的 |
| `merge_tool_artifacts` | 工具工件清单合并（L340） | 🔄 同步 #8 新增：多个工具同时产出工件 |
| `merge_message_writes` | `messages` 的 delta 折叠（L430），语义等同 `add_messages` | 🔄 同步 #8 新增：delta 模式下 messages 走 `DeltaChannel`，线性折叠保持全语义 |

> 🔄 同步 #8 补一条**你没在这里看到但更重要的 reducer**：delta 模式下 `messages` 不是 `add_messages`，而是 `DeltaChannel(merge_message_writes, snapshot_frequency=...)`（`delta_messages_field()` L487-497、`DeltaThreadState` L498-499）。`merge_message_writes` 刻意复刻 `add_messages` 的全部语义（删除/替换/id 冲突），所以你写代码时按 `add_messages` 想就行；但对**写 checkpoint 的人**来说，通道变了、存储代价变了、fork 能力也变了。同一份 `ThreadState` 在两种 mode 下对应的**不是同一个 schema**——这就是 `get_thread_state_schema(mode)` 存在的理由（L520-530）。

---

## 你加字段时继承的是这个

```python
from deerflow.agents.thread_state import ThreadState

class MyWorkflowState(ThreadState):
    # 你拥有：
    # - messages / jump_to / structured_response（LangChain 原生）
    # - sandbox, thread_data, title, artifacts, todos, goal, goal_outcome,
    #   uploaded_files, viewed_images, promoted, delegations, skill_context,
    #   tool_artifacts, tool_artifact_processed, task_notes, task_history,
    #   summary_text, background_tasks（DeerFlow 扩展，共 17 个）
    # +
    # - 你自己加的字段
    my_custom_field: NotRequired[int]
```

**你不需要从头开始。** ThreadState 已经处理好了沙箱、记忆、子任务、skill——你只需要加 workflow 特有的字段。

> 🔄 同步 #8（v2.2.0）**必读的一条约束**：如果你的自定义字段里也有 `messages` 之类的 delta 通道语义，**不要自己写 `Annotated[..., add_messages]` 就交给 `create_agent`**——先看清 mode。`assemble_lead_agent` 在用 `get_thread_state_schema(mode)` 取 schema 的同时，还会调 `normalize_middleware_state_schemas(middlewares, mode)`（`agents/lead_agent/agent.py` L1248），把**每个 middleware 自己声明的 `state_schema`** 也换成适配当前 mode 的版本（`thread_state.py` L558-571，逐项 `copy.copy` 后重写 `state_schema`）。full 模式直接原样返回（L559-560），delta 模式才改动。所以：**同一个 middleware 类，在两种 mode 下拿到的 `self.state_schema` 不是同一个类对象**——任何依赖 `type(self.state_schema) is Xxx` 或缓存了类对象的代码都会在 delta 模式下失配。这条约束在 2.1.0 的 FAQ 里没有。
