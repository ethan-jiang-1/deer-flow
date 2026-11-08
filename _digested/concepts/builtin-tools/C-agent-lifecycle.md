---



title: "C. Agent 定义管理"
description: '这 3 个 tool 让 Agent 可以创建和修改自身的配置——包括 SOUL.md（行为定义）、config.yaml（配置）和 skills（自定义技能）。'
topics: [tools, builtin, sandbox-tools]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# C. Agent 定义管理

这 3 个 tool 让 Agent 可以创建和修改自身的配置——包括 SOUL.md（行为定义）、config.yaml（配置）和 skills（自定义技能）。

---

## setup_agent

**源码**: `packages/harness/deerflow/tools/builtins/setup_agent_tool.py:16`
**加载条件**: bootstrap 模式（`configurable` 中 `is_bootstrap: true`，`agents/lead_agent/agent.py:1170` 的 `raw_tools = get_available_tools(...) + [setup_agent]` 把 `setup_agent` 追加到 `get_available_tools()` 返回值之后；2.1 记录的行号 `agent.py:1057` 已位移）
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
**加载条件**: custom agent 模式（`configurable` 中 `agent_name` 已设置且非 bootstrap，`agents/lead_agent/agent.py:1318` 的 `extra_tools = [update_agent] if agent_name and not is_webhook_channel else []` 决定是否追加；2.1 记录的行号 `agent.py:1176` 已位移）。🆕 **2.2 新增 webhook 通道抑制**：`_WEBHOOK_CHANNELS = frozenset({"github"})`（`agent.py:92`），`channel_name` 由 `ChannelManager._resolve_run_params` 塞进 `run_context`（`agent.py:1315-1317`）。理由写在 `agent.py:1302-1310` 的注释里：webhook 的 prompt 来自任意外部评论者，任何能在配置仓库里发 `@<bot>` 的人都能过触发门，若还能拿到 `update_agent` 就能改掉 agent 的 `tool_groups` / `SOUL.md` / `model` 且**对后续每个 run 生效**；自我改写只应留在操作者可信任的面（聊天 UI、HTTP API）。bootstrap 与直接调用不带 `channel_name`，因此 `update_agent` 仍可用。
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

**源码**: `packages/harness/deerflow/tools/skill_manage_tool.py:354`（`@tool("skill_manage", parse_docstring=True)` 装饰器 + `async def skill_manage_tool` 薄壳，`:355-382`；实现主体 `_skill_manage_impl` 自 `:216` 起，同步桥在同文件末行 `skill_manage_tool.func = make_sync_tool_wrapper(...)`）。2.1 里 `:262-263` 那组行号已随 2.2 的锁重构位移。
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

**两级扫描，静态的先跑**（`skill_manage_tool.py:163-188` 的 `_scan_static_candidate_or_raise` + `:131-140` 的 `_scan_or_raise`）：

1. **确定性静态扫描** `enforce_static_scan()` —— 在临时目录里对"**候选 skill 树**"（现有整棵 skill 树 + 本次改动覆盖其上的文件）跑静态规则；命中 `block` 直接抛 `StaticScanBlockedError`，**不进入**第 2 步的 LLM 审核。🆕 2.2 起现有树是在 **`managed_read(skill_storage)` 内** `shutil.copytree` 出来的（`skill_manage_tool.py:170-176`），与宿主 mutation 服务的读路径共享同一把 guard 锁——否则插件正在 CAS 发布时可能拷到半新半旧的树。候选文件的落盘用 `write_text(..., encoding="utf-8", newline="")`（`:177-180`）：默认文本模式会在扫描器读它之前把 LF 改写成 CRLF，导致"扫的内容"和"最终发布的内容"不是同一份字节。
2. **LLM 审核** `scan_skill_content()`（`skill_manage_tool.py:131-140`）：

```python
result = await scan_skill_content(content, executable=executable, location=location,
                                  static_findings=static_findings or [], attach_tracing=False)
if result.decision == "block":
    raise ValueError(f"Security scan blocked the write: {result.reason}")
if executable and result.decision != "allow":
    raise ValueError(f"Security scan rejected executable content: {result.reason}")
```

- `action=create/edit/patch` → `executable=False`（SKILL.md 本身不可执行）
- `action=write_file` + 路径在 `scripts/` 下 → `executable=True`（额外校验）
- 决策三态：`allow`（放行）/ `warn`（警告但允许）/ `block`（拒绝）
- `delete` / `remove_file` 不跑扫描，history 里固定记 `scanner={"decision":"allow","reason":"Deletion requested."}`（`skill_manage_tool.py:298,339`）

`patch` 的 `expected_count` 语义（`skill_manage_tool.py:275-281`）：**给了就必须精确相等**，否则 `ValueError("Expected N replacements but found M.")`；**不给则只替换 1 次**（不是全局替换）。附带文件路径走 `skill_storage.ensure_safe_support_path()` 白名单校验（`:307`），目录会被拒（`:308-309`）。

🆕 **可执行判定改用共享规则**：`executable = is_code_file(path, content[:8].encode("utf-8", "surrogatepass"))`（`skill_manage_tool.py:321`，`is_code_file` 来自 `skills/package_files.py`）。判据是三条并集——位于顶层 `scripts/` 下、任意层级命中代码后缀（21 个，含 `.py`/`.js`/`.ts`/`.sh`/`.bat`/`.psm1`/`.vbs` 等）、或**无后缀且以 shebang 开头**。注释写明了为什么不再用子串匹配：位于 `references/` 或 `templates/` 下、路径里恰含 `scripts` 字样的静态支持文件（如 `overview.md`）会被子串匹配误判成可执行；而只认 `scripts/` 成员又会漏掉 `references/`、`assets/` 下真正可运行的 `.py` / `.js`。`prev_content` 走 `read_optional_text(skill_storage, target)`（`:312-314`），不做 utf-8 严格解码炸穿。

### 只读保护

- `public/` 下的内置技能**不可编辑/删除**
- 要定制内置技能 → 创建同名 custom skill 覆盖

### 并发

锁粒度是 **`(user_id, skill_name)`**（`skill_manage_tool.py:97-110`，`WeakValueDictionary[tuple[str,str], _SkillLock]`，字典由 `_skill_locks_guard = threading.Lock()` 保护）——同一用户对同一 skill 串行化，**不同用户之间不互相阻塞**。

⚠️ **锁类型在 2.2 换了（上游 #5846）**：不再是 `asyncio.Lock`，而是自定义的 **`_SkillLock`**（`skill_manage_tool.py:40-92`）。原因写在类 docstring 里：同步包装 `skill_manage_tool.func` 给**每次调用一个独立的 `asyncio.run` 循环**，而 `asyncio.Lock` 绑定在创建它的循环上，会让其它循环上的等待者永久挂住。现在的实现：

- 等待者各自持有一个 `Future` + 自己的 `asyncio.AbstractEventLoop`，通过 `await asyncio.wrap_future(waiter)` 停在自己的循环上——**等待不占 executor 线程**（否则等锁本身会吃满默认线程池）。
- `_release()` 把锁**直接交接给最老的等待者**（FIFO），因此后到的调用不能插队。
- 取消安全：`__aenter__` 捕获 `BaseException` 时，若 `waiter.cancel()` 返回 `False`（说明释放方已经把锁交出去了），就自己 `_release()` 往下传，否则后面的等待者会饿死；`_release()` 用 `set_running_or_notify_cancel()` 让抢在取消之前的那个 future 生效，并在**状态锁之外** `set_result`，避免持锁时调度唤醒。

### 历史记录

每次操作记录到 skill 目录下的 history（含 action、author=`"agent"`、thread_id、prev_content、new_content、scanner 结果）。记录由 `_history_record(...)`（`skill_manage_tool.py:119-128`）统一构造，非删除类 action 的 `scanner` 里还会带 `static_findings`（如 `:236`）。

> 变更后刷新：**per-user** 版本 `refresh_user_skills_system_prompt_cache_async(user_id)`（`agents/lead_agent/prompt.py:373`）才是实际调用点；无参版本 `refresh_skills_system_prompt_cache_async()`（`prompt.py:347`）只服务 SDK/无用户上下文路径。cache 失效不重建 storage 单例（详见 [skills-tools 的存储契约](../../concepts/skills-tools/skill-md-and-tool-assembly.md)）。

### 变更落地单元 `_settle_skill_mutation` 🆕（2.2）

所有六个 action（含 `delete` / `remove_file`）都以同一个形式收尾：`await _settle_skill_mutation(user_id, name, persist)`（`skill_manage_tool.py:190-215`）。它把四件事打包成**一个 drained 单元**：

1. `await persist()` —— 真正写盘 + 写 history（各 action 传进去的闭包）；
2. `await refresh_user_skills_system_prompt_cache_async(user_id)` —— 本进程的 prompt 缓存；
3. `publish_skills_cache_reset(user_id=user_id)`，跑在 `_to_thread` 里（文件系统 IO，`prompt.py:121-160`）——**共享失效标记**，让共享同一份 home 卷的其它 Gateway 进程也丢掉缓存的技能列表；
4. 整体包在 `await_drained(...)` 里。

为什么需要 `await_drained`：取消 `asyncio.to_thread` 只会放弃 await，**不会杀掉 worker**。所以一个被取消的 run 若在写盘后展开，就会留下"写已经落地、本进程与其它进程还在发旧技能列表"的状态。`await_drained` 保证这套尾巴跑完。

第 3 步失败时**不会**把整个操作报成失败：只记 `logger.error`，然后抛 `SkillCacheResetPublishError("The change to custom skill '<name>' was applied, but other Gateway processes were not notified and may keep serving the previous skill list: ...")`——语义是"写入已持久化，别重试"，因为模型看到"写入失败"会去重试。

共享标记本体：`SKILLS_CACHE_RESET_MARKER = SharedResetMarker("skills-cache-reset")`（`prompt.py:76-77`），`publish_skills_cache_reset()` 在 `prompt.py:121-160` 里 `publish(config_path, user_id=user_id)` 并返回 generation。Gateway 侧 `POST /api/skills/reload` 用的是同一套机制。

### prompt 缓存刷新

所有修改操作**结束时**（在 `_settle_skill_mutation` 内）都调用 `refresh_user_skills_system_prompt_cache_async(user_id)`，确保下一个 turn system prompt 中的技能列表是最新的——并额外发布跨进程失效标记，见上。

---

## 不属于本类：新增的执行类 builtin 工具（同步 #5）

> **分类说明**：本文件只收录「Agent 定义管理」（改 SOUL.md / config.yaml / skills）。上游新增的 `batch_task_tool.py` 与 `background_tasks_tool.py` 是**执行编排**工具，不属于本类——批量工具是 `task`（subagent 委派）的持久化扩展（见 [`D-task-toolsearch.md`](D-task-toolsearch.md)），后台任务工具属于 MCP 持久化任务子系统（见 [`../../internals/mcp/`](../../internals/mcp/README.md)）。此处仅做最小交叉引用，不展开重复文档。

### `batch_task` / `batch_status` / `cancel_batch`（`tools/builtins/batch_task_tool.py`）

- **加载条件**：仅当启动时安装了 SQL 后端的 durable batch submitter（`config.yaml → subagent_batches.enabled: true` + SQL 数据库）时加入；结果走 owner 作用域的 API/JSONL 导出，不塞回 lead context。
- **用途**：显式 durable batch 模式——一次性提交大量**彼此独立、幂等/只读**的 native-subagent item（`title` + `items[key,prompt]` + `subagent_type`，可选 `max_live_items`/`max_running_items`），立即返回 batch id，跨 Gateway 重启存活；`batch_status` 读紧凑进度快照，`cancel_batch` 取消 pending+running。
- **可用性**：submitter 未安装时返回 `"Durable subagent batches are unavailable..."` error。

### `list_background_tasks` / `cancel_background_task`（`tools/builtins/background_tasks_tool.py`）

- **加载条件**：仅当进程内 MCP task submitter 已安装（`mcp_tasks.enabled` + SQL 持久化）时加入。
- **用途**：自然语言管理当前线程的 durable MCP 后台任务——`list_background_tasks(active_only?)` 列出至多 50 条本地任务（含是否请求取消），`cancel_background_task(task?)` 按任务名/id 取消一个活跃任务；**永不暴露远程 task handle**，取消持久化后立即返回，远程调用与重试由后台服务负责。
