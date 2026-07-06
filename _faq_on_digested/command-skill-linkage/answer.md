## 答案：**不能。没有准确的机制。**

这个问题的本质和 Q1 的 skill 选取精度问题是**同一个问题**——只是换了载体。Q1 里用户打字说"帮我部署 k8s"，DeerFlow 依赖 LLM 阅读理解 skill 列表来决定调用 `k8s-deploy` skill。当用户把需求写进 MD 文件，情况完全一样：MD 文件内容进入对话消息流→LLM 读→LLM 判断该用哪个 skill。没有任何新的机制介入。

**不存在一个"声明式"通道**让任务 MD 文件说"我必须用 skill xyz"并且系统强制执行。

---

## DeerFlow 现有机制分析

### 前端→后端的 context 传递通道

前端 `sendMessage` 支持 `extraContext` 参数：

```typescript
// frontend/src/core/threads/hooks.ts:607-609
context: {
  ...extraContext,   // 调用方传入
  ...context,        // settings context
  ...
}
```

这个 `context` 最终作为 `RunCreateRequest.context` 发送到后端，经过 `merge_run_context_overrides()` 注入到 `config.configurable` 和 `config.context`。

### 白名单限制

```python
# backend/app/gateway/services.py:124-136
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset({
    "model_name",
    "mode",
    "thinking_enabled",
    "reasoning_effort",
    "is_plan_mode",
    "subagent_enabled",
    "max_concurrent_subagents",
    "agent_name",
    "is_bootstrap",
})
```

**没有任何 skill 相关字段在这个白名单里。** 即使前端传了 `skills: ["k8s-deploy"]`，也会被 `merge_run_context_overrides()` 静默忽略。

### 仅有的两种 skill 过滤机制

**机制 1：`/bootstrap` 命令**（硬编码，唯一 command→skill 映射）

```python
# backend/app/channels/manager.py:936-941
if command == "bootstrap":
    await self._handle_chat(chat_msg, extra_context={"is_bootstrap": True})

# backend/packages/harness/deerflow/agents/lead_agent/agent.py:356-358
def _available_skill_names(agent_config, is_bootstrap: bool) -> set[str] | None:
    if is_bootstrap:
        return {"bootstrap"}  # 硬编码，只暴露 bootstrap skill
```

`/bootstrap` 设置 `is_bootstrap=True`，经由 `_available_skill_names()` 将可用 skill 限定为 `{"bootstrap"}`。`get_skills_prompt_section()` 然后将系统 prompt 中的 `<available_skills>` 缩减为仅一个 skill。

**机制 2：Agent config 中的 `skills` 白名单**

```python
# agent.py:359-361
if agent_config and agent_config.skills is not None:
    return set(agent_config.skills)
```

每个 agent 的 `config.yaml` 可以配置 `skills: [...]` 来控制可见 skill。但这需要**提前人工配置**，且 agent 一旦选定，skill 集合就固定了——不能根据单个任务动态变化。

### `CONTEXT_CONFIGURABLE_KEYS` 中没有 skills 的原因

```python
# agent.py:397-403
cfg = _get_runtime_config(config)
...
is_bootstrap = cfg.get("is_bootstrap", False)
agent_name = validate_agent_name(cfg.get("agent_name"))

available_skills = _available_skill_names(agent_config, is_bootstrap)
```

`available_skills` 完全由 `(agent_config, is_bootstrap)` 二元组决定。不读取 `config.configurable` 中的任何 skill 相关字段。白名单里当然也不会包含它。

---

## 管道分析：用户输入 → Skill 选择 全链路

```
Channel: /bootstrap → extra_context={is_bootstrap: True} → is_bootstrap → {"bootstrap"}
                                                                              │
IM 消息文本 / MD 文件任务描述                                                   │
        │                                                                      │
        ▼                                                                      │
  对话消息流 (human message)                                                   │
        │                                                                      │
        ▼                                                                      │
  LLM 读取系统 prompt 中的 <available_skills> 块 ──────────────────────────────┘
        │
        ▼
  LLM 阅读理解所有 skill description → 决定调用 read_file 加载哪个 SKILL.md
```

关键观察：
- **IM 消息和 MD 文件没有区别**：内容都变成 human message，进入 LLM 的上下文窗口。LLM 用同样的阅读理解来做 skill 选择。
- **`/bootstrap` 是唯一的"确定性管道"**：不依赖 LLM 判断，直接通过代码逻辑限定了 skill 集合。

---

## 任务 MD 文件中指定 skill 为什么不可靠

假设你写了一个 MD 文件：

```markdown
# 长城任务：部署微服务集群

使用 @k8s-deploy skill 来完成以下任务...
```

然后通过上传/粘贴发给 Agent。发生什么？

1. MD 文本进入 human message `content`
2. LLM 读取，同时看到 `<available_skills>` 列表（可能有 50+ 个 skill）
3. LLM 需要理解"使用 @k8s-deploy skill"这句话的含义
4. LLM 在 skill 列表中寻找匹配 `k8s-deploy` 名称的 skill
5. LLM 调用 `read_file` 加载 SKILL.md

问题出在第 3-4 步：**这和用户打字说"帮我用 k8s-deploy"是同一条推理路径。** Q1 分析中讨论的所有问题都在这里重现：

- LLM 可能忽略 MD 中的"使用 X skill"指令（attention dilution）
- 长任务 MD 有大量文本，skill 指定可能被淹没在细节中
- 如果 skill 描述和 MD 中的表达式不完全匹配，LLM 可能选错

**MD 文件不提供任何"强制路由"能力。** 它只是 more text。

---

## Codex 的对比：显式调用作为解决方案

Codex 支持两种 skill 触发方式：

| 方式 | 机制 | 可靠性 |
|------|------|--------|
| **显式调用** | 用户/系统输入 `$skill-name` | 100%（框架级强制） |
| **隐式匹配** | LLM 语义匹配 description | ~80%（LLM 依赖） |

在 Codex 中，你可以在任务文件里写：

```
请执行 $k8s-deploy 来完成以下部署...
```

`$skill-name` 是框架级别的触发语法——Codex 解析器在把文本发给 LLM **之前**就把对应 skill 的 SKILL.md 注入上下文。不依赖 LLM 判断。

DeerFlow **没有这个 `$` 触发语法**。它是 Codex 的独家功能（`codex-rs/core/src/skills/render.rs` 处理）。

---

## 改进方向

### 短期：利用现有基础设施加 context key

最小的侵入性改动——在 `_CONTEXT_CONFIGURABLE_KEYS` 中加一个 `skills` key：

```python
# services.py:124-136 — 新增 "skills"
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset({
    ...
    "skills",  # 新增
})
```

然后在 `_make_lead_agent()` 中读取它：

```python
# agent.py — 新增 skill override 逻辑
requested_skills = cfg.get("skills")
if requested_skills is not None:
    available_skills = set(requested_skills)
elif is_bootstrap:
    available_skills = {"bootstrap"}
elif agent_config and agent_config.skills is not None:
    available_skills = set(agent_config.skills)
else:
    available_skills = None
```

这样前端 `sendMessage` 就可以传：

```typescript
sendMessage(threadId, message, { skills: ["k8s-deploy", "python-testing"] })
```

**但这仍然要求调用方（人或系统）知道 skill 的名字。** 对一个"长城任务"MD 文件来说，你需要预先在文件里写出具体的 skill 名称，然后由某个解析器提取出来放到 `extraContext.skills` 里。这个解析器目前不存在。

### 中期：给系统 prompt 加 skill 触发指令

不改变架构，但强化 prompt 中的 skill 指令——告诉 LLM 如果在用户输入或任务文件中看到 "use skill X" 或 "@skill-name" 这样的标记，就优先选择对应 skill：

```
If the user's message or any attached file mentions a skill by name
(e.g., "use @k8s-deploy", "请使用 python-testing skill"),
you MUST invoke that skill via read_file before proceeding.
```

这利用了 LLM 的指令跟随能力，不是决定性机制，但在实践中可以降低忽略率。

### 方式三：前端解析 MD 文件中的 skill 标记

在发送请求前，前端（或中间层）扫描任务 MD 内容，提取类似 `@k8s-deploy` 的标记，然后通过上述新增的 `skills` context key 传入：

```
MD: "使用 @k8s-deploy, @python-testing 完成..."
     → 前端解析 → extraContext: { skills: ["k8s-deploy", "python-testing"] }
     → API → merge_run_context_overrides → config.configurable.skills
     → _make_lead_agent → available_skills = {"k8s-deploy", "python-testing"}
     → get_skills_prompt_section → 只注入这两个 skill
```

这给了任务 MD 文件**半精确**的 skill 指定能力：仍然依赖前端解析，但一旦提取成功，后端就是确定性的。

### 长期：实现类似 Codex 的 `$skill-name` 触发语法

在消息处理管道中插入一层解析——在 human message 注入 LLM 上下文之前，扫描文本中的 `$skill-name` 模式，找到匹配就直接加载对应 SKILL.md 到上下文。这需要：

1. 在 `make_lead_agent` 或 middleware 层加消息预处理
2. 或在前端 `sendMessage` 中加文本扫描
3. 匹配 skill 注册表（同 Q1 的 `trigger_keywords` 方案）

---

## 结论

**DeerFlow 目前没有任何方法让任务 MD 文件可靠地指定 skill。** 唯一确定性的 command→skill 映射是 `/bootstrap`→`{"bootstrap"}`，而且这是硬编码在 channel manager 里的。

核心矛盾是：DeerFlow 的 skill 选择**完全是 LLM 自主决策**——不管需求来自聊天输入还是 MD 文件，都是同一套"LLM 读描述→判断"流程。要改变这一点，需要在 LLM 之前的管道中加入**确定性路由**。

三个改进层次：
1. **加 context key**（改 5 行代码）— 让 API 调用方能传入 skill 名称，后端确定性过滤
2. **加 prompt 指令**（改 0 行代码）— 让 LLM 更重视 MD 中的 skill 标记（但不保证可靠性）
3. **加触发语法**（改 ~50 行代码）— 类似 Codex 的 `$skill-name`，在消息预处理阶段做确定性匹配

方案 1 最务实，给 API 调用方（前端、channel、外部系统）提供了一个刚性管道。方案 3 提供最好的用户体验但需要最多的实现工作。

---

## 相关 digest 笔记

- `_faq_on_digested/skill-selection-accuracy/` — Q1: skill 选取精度问题的根源分析
- `_digest/harness-hooks/07-context-config-override.md` — ContextVar 运行时覆盖机制，`_CONTEXT_CONFIGURABLE_KEYS` 白名单模式
- `_digest/harness-hooks/08-agent-self-modification.md` — `update_agent` 的自修改流程
- `_digest/middleware/01-hooks-and-flow.md` — 中间件生命周期中如何处理上下文

Sources:
- DeerFlow 源码: `backend/packages/harness/deerflow/agents/lead_agent/agent.py:356-361, 397-403`
- DeerFlow 源码: `backend/app/gateway/services.py:124-153`
- DeerFlow 源码: `backend/app/channels/manager.py:936-941`
- DeerFlow 源码: `backend/app/channels/commands.py:11-20`
- DeerFlow 源码: `backend/packages/harness/deerflow/agents/lead_agent/prompt.py:626-656`
- DeerFlow 源码: `frontend/src/core/threads/hooks.ts:607-609`
- [Codex Skills — OpenAI Developers](https://developers.openai.com/codex/skills)
