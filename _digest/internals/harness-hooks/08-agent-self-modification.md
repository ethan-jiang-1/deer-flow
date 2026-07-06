---
title: "Agent 自修改：update_agent / setup_agent + SOUL.md 原子写入"
description: "- `deerflow/tools/builtins/update_agent_tool.py` — agent 在对话中更新自己的 SOUL.md/config.yaml"
topics: [hooks, extension, plugin-system]
---

# Agent 自修改：update_agent / setup_agent + SOUL.md 原子写入

**核心文件：**
- `deerflow/tools/builtins/update_agent_tool.py` — agent 在对话中更新自己的 SOUL.md/config.yaml
- `deerflow/tools/builtins/setup_agent_tool.py` — bootstrap 创建新 agent
- `deerflow/config/agents_config.py` — agent 目录解析 + SOUL.md 加载
- `deerflow/config/skill_evolution_config.py` — 技能演化开关

DeerFlow 的 agent 可以在**对话中修改自己的配置和人格描述**。这在所有 AI agent 框架中是少见的 self-evolution 机制。

## 两种自修改工具

| 工具 | 何时绑定 | 用途 |
|------|----------|------|
| `setup_agent` | `is_bootstrap=True`（首次创建 agent） | 创建新 agent：写 SOUL.md + config.yaml |
| `update_agent` | `agent_name` 已设置 + `is_bootstrap=False` | 修改现有 agent：部分更新 SOUL.md/config.yaml |

两个工具互斥——同一个 agent 要么有 `setup_agent`（创建中），要么有 `update_agent`（已存在），不会同时。

## update_agent 的原子写入

`update_agent_tool.py:36-224` 实现了一个**多文件原子提交**协议：

```python
# 阶段 1: 数据准备
config_data = {"name": agent_name, "description": ...}
soul_content = "..."

# 阶段 2: 所有文件先写 temp（暂存）
config_tmp = _stage_temp(config_target, yaml.dump(config_data))
soul_tmp = _stage_temp(soul_target, soul_content)

# 阶段 3: 全部 temp 就绪 → 原子 rename（提交）
for tmp, target in pending:
    tmp.replace(target)   # Path.replace 是原子操作（POSIX/NTFS）
```

**为什么需要原子性？** 如果 SOUL.md 写入了但 config.yaml 写入失败，agent 的状态是不一致的（新人格 + 旧配置）。原子提交保证了要么全部生效，要么全部不生效。

**部分写入的检测与恢复：** 如果两个文件都 temp 成功了，但在第一个 `replace` 和第二个 `replace` 之间进程崩溃，`update_agent` 会报告哪些文件已被提交、哪些失败，让调用方重试。

```python
if committed:
    return _err(
        f"Partial update for agent '{agent_name}': "
        f"{[p.name for p in committed]} were updated, but the rest failed. "
        f"Re-run update_agent to retry the remaining fields."
    )
```

## 部分更新语义

`update_agent` 只更新你传入的字段——省略的字段保持原值：

```python
def update_agent(
    runtime: Runtime,
    soul: str | None = None,          # 传入 → 全量替换 SOUL.md
    description: str | None = None,   # 传入 → 更新 description
    skills: list[str] | None = None,  # 传入 → 更新 skill whitelist（[] = 禁用所有）
    tool_groups: list[str] | None = None,
    model: str | None = None,
) -> Command:
```

`skills=None` 的含义是"不改变现有配置"，不是"禁用所有 skills"。要禁用所有 skills 需要传 `skills=[]`。

## 配置的生效时机

**关键：** agent 自修改后的新配置在下一次**用户对话 turn** 时生效，不是立即：

```
User: "add skill foo to this agent"
  → Agent 调用 update_agent(skills=["foo"])
  → ToolMessage 返回 "Agent updated. Changes take effect on the next user turn."
  → 当前 turn 继续用旧配置（本次对话不变）

User: "now use that skill"  ← 新 turn
  → make_lead_agent() 重新执行
  → load_agent_config("my-agent") 读到新的 skills=["foo"]
  → 系统 prompt 包含 foo skill
  → agent 可以使用 foo
```

这是因为 `make_lead_agent` 在每次 run 开始时执行，每次都重新调用 `load_agent_config()`。

## SOUL.md 注入链路

```
load_agent_config(name, user_id)
    │
    ├─ resolve_agent_dir(name, user_id)
    │     ├─ 1. {base_dir}/users/{uid}/agents/{name}/  （per-user）
    │     └─ 2. {base_dir}/agents/{name}/               （legacy fallback）
    │
    └─ agent_dir / "config.yaml" → AgentConfig(name, description, model, tool_groups, skills)
    
load_agent_soul(name, user_id)
    │
    └─ agent_dir / "SOUL.md" → 字符串

应用在系统 prompt 中:
    <soul>
    {soul_content}
    </soul>
```

## 安全控制

### 技能演化开关

```python
class SkillEvolutionConfig(BaseModel):
    enabled: bool = False  # 默认关闭！
    moderation_model_name: str | None = None  # 可选的安全审核 model
```

`SkillEvolutionConfig.enabled` 控制 agent 是否能调用 `skill_manage` tool（创建/修改 `skills/custom/` 下的技能）。默认是 **关闭** 的——用户可以给 agent 开通这个能力，但要明确操作。

### User 隔离

`update_agent` 总是写到当前用户的目录：

```python
user_id = resolve_runtime_user_id(runtime)
agent_dir = paths.user_agent_dir(user_id, agent_name)
```

这意味着：
- User A 的 agent 修改只影响 User A
- User B 看不到 User A 创建的 agent（文件在不同目录）
- Legacy（共享）agent 不能被修改——`update_agent` 会拒绝并提示运行 `scripts/migrate_user_isolation.py`

### 安全限制

- `update_agent` 只能修改**当前 agent**（`runtime.context["agent_name"]`），不能跨 agent 修改
- 不能在 `update_agent` 调用中改变 `agent_name`（名字由目录决定）
- `model` 参数必须在 `config.yaml` 的 `models[]` 中存在（提前校验，不等到运行时方发现）

## BeforeSummarizationHook: 总结前的记忆勾子

`deerflow/agents/memory/summarization_hook.py` 提供了另一种钩子——在总结压缩历史消息之前，把即将被压缩的消息 flush 到 memory 队列：

```python
class BeforeSummarizationHook(Protocol):
    def __call__(self, event: SummarizationEvent) -> None: ...

# SummarizationEvent:
#   messages_to_summarize: 即将被总结压缩的消息
#   preserved_messages: 会被保留的消息
#   thread_id: 当前 thread
#   agent_name: 当前 agent 名
#   runtime: Runtime 对象
```

`memory_flush_hook` 是这个协议的内置实现——在总结前把 user + assistant 消息入队到 memory 更新队列，确保重要信息在压缩前被保存。这保证了即使对话历史被压缩，memory 系统仍然能提取到关键信息。

```python
def memory_flush_hook(event: SummarizationEvent) -> None:
    if not get_memory_config().enabled:
        return
    filtered = filter_messages_for_memory(event.messages_to_summarize)
    user_msgs = [m for m in filtered if m.type == "human"]
    assistant_msgs = [m for m in filtered if m.type == "ai"]
    correction = detect_correction(filtered)
    queue.add_nowait(...)
```

## 总结

DeerFlow 的自修改机制构建了一条完整的"agent 进化"管道：

1. **开始** — `setup_agent` 创建 agent（bootstrap）
2. **演化** — `update_agent` 在对话中修改 SOUL.md / config.yaml
3. **生效** — 下次 turn 时 `load_agent_config()` + `load_agent_soul()` 读入新配置
4. **持久化** — `BeforeSummarizationHook` 确保总结前的信息进入 memory，即使历史被压缩也不丢失
5. **安全** — per-user 隔离 + 开关控制 + 原子写入防数据损坏
