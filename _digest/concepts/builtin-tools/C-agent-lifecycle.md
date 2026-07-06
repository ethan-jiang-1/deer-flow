---
title: "C. Agent 定义管理"
description: "这 3 个 tool 让 Agent 可以创建和修改自身的配置——包括 SOUL.md（行为定义）、config.yaml（配置）和 skills（自定义技能）。"
topics: [tools, builtin, sandbox-tools]
---

# C. Agent 定义管理

这 3 个 tool 让 Agent 可以创建和修改自身的配置——包括 SOUL.md（行为定义）、config.yaml（配置）和 skills（自定义技能）。

---

## setup_agent

**源码**: `packages/harness/deerflow/tools/builtins/setup_agent_tool.py:16`
**加载条件**: bootstrap 模式（`configurable` 中 `is_bootstrap: true`，`agent.py:461` 将 `setup_agent` 追加到 `get_available_tools()` 返回值之后）
**Tool Name**: `setup_agent`

### 用途

在 Agent 创建向导（bootstrap 流程）中，创建全新的自定义 Agent。写好 SOUL.md 和 config.yaml 后 Agent 即持久化存在。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `soul` | `str` | 完整的 SOUL.md 内容，定义 Agent 的人格和行为 |
| `description` | `str` | 一行描述，Agent 是干什么的 |
| `runtime` | `Runtime` | 注入的运行时上下文 |
| `skills` | `list[str] \| None` | 可选技能白名单：`None`=用全部启用的技能，`[]`=不用任何技能 |

### 输出路径

```python
# 有 agent_name → 自定义 Agent
agent_dir = paths.user_agent_dir(user_id, agent_name)
# {base_dir}/users/{user_id}/agents/{name}/

# 无 agent_name → 全局默认（bootstrap 过程）
agent_dir = paths.base_dir
```

写入文件：
- `{agent_dir}/SOUL.md` — Agent 人格定义
- `{agent_dir}/config.yaml` — 包含 `name`, `description`, `skills`

### 原子性（回滚）

```python
except Exception as e:
    if agent_name and is_new_dir and agent_dir is not None and agent_dir.exists():
        shutil.rmtree(agent_dir)  # 清理本次新创建的目录
```

如果创建过程中出错且目录是本次新建的，会删除整个 agent 目录回滚。如果目录之前就存在则保留。

### 返回值

成功 → `ToolMessage("Agent '{name}' created successfully!")` + 设置 `created_agent_name` state
失败 → `ToolMessage("Error: {e}")`

### 与 update_agent 的分工

| | setup_agent | update_agent |
|------|-------------|--------------|
| 场景 | 首次创建 Agent | 已有 Agent 的自我优化 |
| 触发 | bootstrap 向导 | 普通对话中 |
| soul | 必传 | 可选 |
| 目录不存在 | 自动创建 | 报错 |
| 失败 | 回滚删除目录 | temp 文件机制 |

---

## update_agent

**源码**: `packages/harness/deerflow/tools/builtins/update_agent_tool.py:70`
**加载条件**: custom agent 模式（`configurable` 中 `agent_name` 已设置且非 bootstrap，`agent.py:479` 将 `update_agent` 追加到 `get_available_tools()` 返回值之后）
**Tool Name**: `update_agent`

### 用途

已有的自定义 Agent 在对话中自我优化——修改自己的身份、技能白名单、工具组、默认模型等。**只更新传了的字段**，不传的保持不变。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `runtime` | `Runtime` | 注入的运行时上下文 |
| `soul` | `str \| None` | 可选，**完整替换** SOUL.md 内容（无 patch 语义） |
| `description` | `str \| None` | 可选，新的一句话描述 |
| `skills` | `list[str] \| None` | 可选技能白名单：`[]`=禁用所有技能，不传=保持不变 |
| `tool_groups` | `list[str] \| None` | 可选工具组白名单 |
| `model` | `str \| None` | 可选模型覆盖（必须在 `config.yaml` 的 models 中存在） |

### 原子写入协议

关键设计——避免部分写入导致 config.yaml 更新了但 SOUL.md 还是旧的：

```
1. 把所有要改的文件写到 temp 文件（_stage_temp）
   └── {agent_dir}/config.yaml.tmp
   └── {agent_dir}/SOUL.md.tmp

2. 全部 temp 文件写成功后 → Path.replace()（POSIX 原子 rename）

3. 任意一步失败：
   └── 已创建的 temp 文件被清理
   └── 目标文件从未被修改
```

**极端情况**：两次 `Path.replace()` 之间进程崩溃 → 返回 partial write 错误，告知用户哪些文件已更新哪些没更新，让 LLM 重试剩余字段。

### 校验

1. 至少传一个字段，否则 `"No fields provided"`
2. `agent_name` 必须在 runtime context 中存在，否则 `"update_agent is only available inside a custom agent's chat"`
3. `model` 必须在 config 中存在，否则 `"Unknown model 'xxx'"`
4. Agent 必须已存在，否则 `"Agent 'xxx' does not exist for the current user"`
5. 不支持 legacy 共享目录下的 agent（提示跑迁移脚本）

### 用户隔离

```python
user_id = resolve_runtime_user_id(runtime)
agent_dir = paths.user_agent_dir(user_id, agent_name)
```

写回到 `{base_dir}/users/{user_id}/agents/{name}/`，不同用户互不可见。

---

## skill_manage

**源码**: `packages/harness/deerflow/tools/skill_manage_tool.py:204`
**加载条件**: `skill_evolution.enabled: true`（`config.yaml` 中 `skill_evolution` 段）
**Tool Name**: `skill_manage`

### 用途

让 Agent 管理 `skills/custom/` 下的自定义技能。支持完整的 CRUD + 附带文件（如脚本、模板）管理。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `action` | `str` | 操作类型（见下表） |
| `name` | `str` | 技能名（hyphen-case） |
| `content` | `str \| None` | 文件内容（create/edit/write_file 时） |
| `path` | `str \| None` | 附带文件路径（write_file/remove_file 时） |
| `find` | `str \| None` | 要被替换的文本（patch 时） |
| `replace` | `str \| None` | 替换后文本（patch 时） |
| `expected_count` | `int \| None` | 期望替换次数（patch 时，可选） |

### action 枚举

| action | 说明 | 必传参数 |
|--------|------|----------|
| `create` | 新建 custom skill（SKILL.md） | `name`, `content` |
| `edit` | 全量替换 SKILL.md 内容 | `name`, `content` |
| `patch` | 子串替换 SKILL.md 中部分内容 | `name`, `find`, `replace` |
| `delete` | 删除整个 custom skill | `name` |
| `write_file` | 写附带文件（如 `scripts/run.sh`） | `name`, `path`, `content` |
| `remove_file` | 删附带文件 | `name`, `path` |

### 安全扫描

每次写入前过 `scan_skill_content()`：

```python
result = await scan_skill_content(content, executable=executable, location=location)
if result.decision == "block":
    raise ValueError(f"Security scan blocked the write: {result.reason}")
```

- `action=create/edit/patch` → `executable=False`（SKILL.md 本身不可执行）
- `action=write_file` + 路径在 `scripts/` 下 → `executable=True`（额外校验）
- 决策三态：`allow`（放行）/ `warn`（警告但允许）/ `block`（拒绝）

### 只读保护

- `public/` 下的内置技能**不可编辑/删除**
- 要定制内置技能 → 创建同名 custom skill 覆盖

### 并发

同一 skill name 用 `asyncio.Lock` 串行化，防止并发的 create + edit 竞争。

### 历史记录

每次操作记录到 skill 目录下的 history（含 action、author=`"agent"`、thread_id、prev_content、new_content、scanner 结果）。

### prompt 缓存刷新

所有修改操作后都调用 `refresh_skills_system_prompt_cache_async()`，确保下一个 turn system prompt 中的技能列表是最新的。
