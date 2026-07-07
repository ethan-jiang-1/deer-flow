# LangGraph 打地基，DeerFlow 盖房子

## LangGraph 的 AgentState：最简地基

LangChain 的 `AgentState`（`langchain/agents/middleware/types.py` L350-355）只有两个字段：

```python
class AgentState(TypedDict, Generic[ResponseT]):
    messages: Required[Annotated[list[AnyMessage], add_messages]]
    jump_to: NotRequired[Annotated[JumpTo | None, EphemeralValue, PrivateStateAttr]]
```

| 字段 | 作用 | Reducer |
|------|------|---------|
| `messages` | 对话历史——所有 HumanMessage、AIMessage、ToolMessage | `add_messages`（追加） |
| `jump_to` | middleware 逃生口——设 `"end"` 直接终止循环 | `EphemeralValue`（读一次消失） |

就这两个。LangChain 不假定你在做什么应用——聊天机器人、代码助手、客服系统，都从这两个字段开始。

## DeerFlow 的 ThreadState：给地基盖了三层楼

`deerflow/agents/thread_state.py` L223-235：

```python
class ThreadState(AgentState):        # 继承 LangChain 的 AgentState
    sandbox: SandboxStateField        # 沙箱管理
    thread_data: NotRequired[...]     # 线程元数据（workspace 路径等）
    title: NotRequired[str | None]    # 自动生成标题
    artifacts: Annotated[list[str], merge_artifacts]        # 产出文件列表
    todos: Annotated[list | None, merge_todos]               # 待办事项
    goal: Annotated[GoalState | None, merge_goal]            # 目标追踪
    uploaded_files: NotRequired[list[dict] | None]           # 上传文件
    viewed_images: Annotated[dict, merge_viewed_images]      # 图片缓存
    promoted: Annotated[PromotedTools | None, merge_promoted] # MCP 工具提升
    delegations: Annotated[list[DelegationEntry], merge_delegations]  # 子任务委托
    skill_context: Annotated[list[SkillEntry], merge_skill_context]    # 已加载 skill
    summary_text: NotRequired[str | None]                    # 历史总结
```

### 每个字段谁能读、谁能写

这是理解 state 的实战关键——不是所有 node 都能写所有字段：

| 字段 | 谁写 | 谁读 |
|------|------|------|
| `messages` | model node（AIMessage）、ToolNode（ToolMessage）、middleware | 所有 node |
| `jump_to` | middleware（`after_model` 中设 `"end"`） | 条件边函数 |
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

**关键洞察**：大部分字段是"特定 middleware 写，model node 读"。这就是 middleware → state → model 的数据流。

### DeerFlow 的 5 个自定义 Reducer

这些都是从 DeerFlow 源码直接提取的，位于 `thread_state.py`：

| Reducer | 逻辑 | 为什么不用 last_value |
|---------|------|----------------------|
| `merge_artifacts` | 并集 + 去重 | 多个 tool 同时产出文件，后面的不应该覆盖前面的 |
| `merge_todos` | `None` = 保留旧值，非 `None` = 覆盖 | `write_todos` 不返回 todos 时不应该清空已有列表 |
| `merge_delegations` | 追加，同 ID 最新胜，终态保护，上限 50 | 多个子任务同时完成，状态不能互相覆盖 |
| `merge_promoted` | catalog-hash 作用域，catalog 变更时全替换 | catalog 更新后，旧 promotion 应该失效 |
| `merge_skill_context` | 按 path 去重，最近读取优先，上限 8 | 重复读同一个 skill 不应重复存储 |

---

## 你加字段时继承的是这个

```python
from deerflow.agents.thread_state import ThreadState

class MyWorkflowState(ThreadState):
    # 你拥有：
    # - messages（LangGraph 原生）
    # - jump_to（LangGraph 原生）
    # - sandbox, thread_data, title, artifacts, todos, goal,
    #   uploaded_files, viewed_images, promoted, delegations,
    #   skill_context, summary_text（DeerFlow 扩展）
    # +
    # - 你自己加的字段
    my_custom_field: NotRequired[int]
```

**你不需要从头开始。** ThreadState 已经处理好了沙箱、记忆、子任务、skill——你只需要加 workflow 特有的字段。
