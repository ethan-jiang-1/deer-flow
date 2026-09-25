---
title: "TUI 终端工作台"
description: "`deerflow` CLI：安装、四种启动模式（TUI / headless print / headless JSON / 降级 help）、命令全集与别名、键位真值、会话持久化与输入历史、流式渲染与滚动语义。"
topics: [tui, cli, terminal]
---

# TUI 终端工作台

DeerFlow 有可安装的 `deerflow` 命令：一个跑在**内嵌** `DeerFlowClient` 上的终端工作台，不需要 Gateway / Nginx / Docker。源码：`backend/packages/harness/deerflow/tui/`（下文简称 `tui/`，共 **15** 个 `.py` 文件：`app.py`、`cli.py`、`command_registry.py`、`input_history.py`、`message_format.py`、`persistence.py`、`render.py`、`runtime.py`、`session.py`、`theme.py`、`view_state.py`、`__init__.py`、`__main__.py`、`widgets/__init__.py`、`widgets/composer.py`）。

> 真值顺序：本页所有契约以 v2.1.0（`345f08be`）源码为准。设计说明另见 `backend/docs/TUI.md` 与 `tui/AGENTS.md`。

## 安装与前置

```bash
uv pip install 'deerflow-harness[tui]'     # 或：pip install textual
```

- console script 注册在 `packages/harness/pyproject.toml:61-62`：`deerflow = "deerflow.tui.cli:main"`。
- `textual` 是**可选**依赖 `textual>=0.80`（`packages/harness/pyproject.toml:64-67`），核心 harness 不因它变重。
- 从源码跑（在 `backend/` 目录；harness 已 editable 安装进 backend 的 venv）：

```bash
cd backend && PYTHONPATH=. uv run python -m deerflow.tui
```

`python -m deerflow.tui` 走 `tui/__main__.py`，与 console script 同一个 `cli.main()`。

## 启动模式（`plan_launch()` 真值）

`plan_launch(argv, stdin_isatty, stdout_isatty, env)` 是**纯函数**（无 I/O、不构造 client），`tui/cli.py:104-189`。四种 `mode`：

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| `print` | `--print MESSAGE`（或 `--print` + 管道 stdin）；`--cli` + 位置参数 / 管道 / `--continue` | `client.chat()`，最终回答打到 stdout |
| `json` | `--json MESSAGE`（或 `--json` + 管道 stdin） | 逐行 `{"type": ..., "data": ...}` JSON，`ensure_ascii=False` 且每行 flush |
| `tui` | `--tui` 或 `DEER_FLOW_TUI` 为真 或 **stdin 与 stdout 都是 TTY** | 全屏 Textual UI |
| `headless-help` | 以上都不满足，或参数不完整 | 打印降级帮助到 stderr |

判定优先级（自上而下，先命中先返回，`tui/cli.py:117-189`）：

1. `--print`（`tui/cli.py:121-132`）
2. `--json`（`tui/cli.py:134-145`）
3. `--cli`（`tui/cli.py:147-169`）
4. `--tui` / `DEER_FLOW_TUI` / TTY 自动检测（`tui/cli.py:171-181`）
5. 兜底 `headless-help`（`tui/cli.py:183-189`）

契约级细节：

- **退出码**：`headless-help` 且带原因 → **2**；不带原因 → **0**（`tui/cli.py:238-242`）。所以"没 TTY 又没给 headless 参数"是 exit 2，不会挂起。
- **`--print` / `--json` 缺 MESSAGE 且 stdin 是 TTY** → 直接 `headless-help`（原因："needs a MESSAGE argument or piped stdin"），`--continue` 也救不回来（`tui/cli.py:123-124`、`136-137`）。要"续跑最近线程"走 `--cli` 或 TUI。
- `--cli` 缺消息时，只要给了 `--continue` **或** stdin 不是 TTY 就进入 `print` 模式并读 stdin（`tui/cli.py:156-165`；注意此时 `read_stdin=True` 是无条件的，stdin 是 TTY 而只给 `--continue` 会一直读到 EOF）。
- `--recursion-limit` 只接受正整数（`_positive_int`），且**必须**同时给 `--print`/`--json`/`--cli`，否则 argparse 报错（`tui/cli.py:38-45`、`118-119`）。
- 首位置参数 `chat` 是默认会话面的别名，会被剥掉（`_strip_chat`，`tui/cli.py:92-97`）——`deerflow chat` ≡ `deerflow`。
- `extensions` 是唯一在 `plan_launch` **之前**被拦截的子命令，转发给 `deerflow.extensions.cli.main`（`tui/cli.py:227-230`）。`deerflow extensions --help` 因此不经过 argparse。
- 环境变量真值集合：`_truthy()` 只认字符串 `1` / `true` / `yes` / `on`（大小写不敏感、去空白）（`tui/cli.py:100-101`）。
- TUI 模式下的位置参数（`deerflow --tui "问题"`）会存进 `LaunchPlan.message`，在 `on_mount` 时自动发送（`tui/app.py:216-217`）。

### headless 用法

```bash
# 一次性文本回答
deerflow --print "用 Python 写冒泡排序"
echo "hello" | deerflow --print

# JSON 流（每行一个 StreamEvent：{"type","data"}）
deerflow --json "列出 workspace 文件"
echo "scan files" | deerflow --json | while read -r line; do process "$line"; done

# 指定线程 / 最近线程
deerflow --print "继续上次" --resume my-thread-id
deerflow --print "继续" --continue

# 放宽 super-step 预算
deerflow --recursion-limit 250 --print "长任务"
```

- headless 走 `open_session(persistence=False)`——**不写 `threads_meta`，不起后台 DB 事件循环/连接池**（`tui/cli.py:253-259`）。
- `--resume` / `--continue` 在 headless 下同样生效：都经 `Session.resolve_thread(plan)`（`tui/session.py:27-35`）。
- recursion limit 缺省 **100**（`client.py:293` 的 `overrides.get("recursion_limit", 100)`；与 `tui/cli.py:87` 的帮助文本一致）。`max_recursion_limit` 是 Gateway 对客户端传入值的上限，不是内嵌 CLI 的默认值。

## 命令全集与别名

内置命令是 `BUILTIN_COMMANDS` 常量，顺序即 `/help` 与 palette 的展示顺序（`tui/command_registry.py:38-57`），共 **18** 条：

| 命令 | 注册表描述 | 实际行为（`tui/app.py:396-447`） |
|------|-----------|-------------------------------|
| `/help` | Show commands and keybindings | 输出一行全命令表 + 一行键位表（`tui/app.py:40-41`） |
| `/new` | Start a fresh thread | 清 `_conv_thread_id` + 重置 `ViewState`；**run 进行中被拦** |
| `/clear` | Clear the transcript display | 只发 `ClearRows`（清行，不换 thread、不动持久化）；**run 进行中被拦** |
| `/threads` | Open the thread switcher | 模态线程选择器（最近 20 条，`tui/app.py:470-490`） |
| `/switch` | Open the thread switcher | `/threads` 的**别名** |
| `/resume` | Resume a thread by id or title | `args` 为空 → 打开选择器；否则切换线程（`tui/app.py:492-498`） |
| `/goal` | Set, show or clear the active goal | 空 = 显示；`clear`/`reset`/`off` = 清除；其它 = 设为目标（`runtime/goal.py:76-89`） |
| `/model` | Open the model picker | 模态模型选择器，选中后作为 `model_name` 传给 `stream()` |
| `/skills` | Browse enabled and available skills | 列出已启用 skill 名 |
| `/tools` | Show built-in, MCP and sandbox tools | **占位提示**：工具在 agent 运行时里，MCP 请用 `/mcp` |
| `/mcp` | Show MCP server status | 每个 server 的 `on`/`off` |
| `/memory` | Show memory status and injected facts | fact 数量 + top of mind。注意实现读的是**顶层** `data["topOfMind"]`（`tui/app.py:560-568`），而默认 deermem 文档把它嵌在 `user.topOfMind`（`.../deermem/core/storage.py:95-110`），所以实际通常渲染成 `—` |
| `/uploads` | Show uploaded files for this thread | 当前线程上传文件列表 |
| `/artifacts` | Show generated artifacts | **占位提示**：artifact 随 agent 写入内联出现 |
| `/details` | Toggle verbose activity rendering | **占位提示**：本构建始终显示详细信息（无折叠开关） |
| `/usage` | Show token usage and context | 读 `ViewState.usage`（无记录时提示） |
| `/config` | Show resolved config paths and overrides | 只输出 `cwd` 与当前 model |
| `/quit` | Exit the TUI | 若正在跑先中断，再 `exit()` |

解析规则（`resolve()`，`tui/command_registry.py:110-129`）：

- 不以 `/` 开头 → 普通消息，原文交给 agent。
- `/name args`：`name` 命中内置集合 → `builtin`；命中已启用 skill 名 → `skill`；否则 `unknown`（TUI 出错误行 "Unknown command /name. Try /help."）。
- 空名（如单独一个 `/`）→ `unknown`。

Skill 命令：每个**已启用** skill 贡献一条 `/skill-name`，但会被剔除两类名字（`tui/command_registry.py:73-83`）：与内置命令同名的，以及在共享保留名 `RESERVED_SLASH_SKILL_NAMES = {agent, bootstrap, goal, help, memory, models, new, status}` 里的（`skills/slash.py:17`）。剔除是刻意的——TUI 不能宣传一个 agent 运行时会拒绝的 skill 激活。

Palette（`tui/app.py:250-261`）：输入框内容以 `/` 开头且**不含空格**时打开；`filter_commands()` 按 名字前缀 → 名字子串 → 描述子串 排序（`tui/command_registry.py:86-107`）后展示。渲染成 8 行窗口，超出显示 `… N more`（`tui/render.py:116-137`）。

## 键位（`DeerFlowTUI.BINDINGS` 真值）

`tui/app.py:160-174`。除 `Ctrl+C` 外全部 `show=False`：**只有 Ctrl+C 会出现在 Textual 的快捷键栏**，其余靠 `/help` 的键位行或本文档。

| 键 | 动作 | priority | 语义 |
|----|------|----------|------|
| `Ctrl+C` | `interrupt` | ✓ | 正在跑 → 中断 run；空闲 → 退出（`tui/app.py:662-666`） |
| `Ctrl+L` | `redraw` | — | `refresh(layout=True)` + 全量重绘 |
| `Ctrl+U` | `clear_composer` | — | 清空输入框 |
| `↓` / `↑` | `nav_down` / `nav_up` | ✓ | palette 打开时移动高亮；否则走输入历史 |
| `Tab` | `palette_complete` | ✓ | palette 打开时补全高亮项（补 `"/name "`）；关闭时**吃掉按键**，保持焦点在输入框 |
| `Enter` | `palette_accept` | ✓ | palette 打开时：内置命令直接执行，skill 只补全（还要补任务参数）；关闭时让位给 `Input.Submitted` 正常提交 |
| `Esc` | `escape` | ✓ | palette 打开 → 关 palette；否则若在跑 → 中断 run（`tui/app.py:668-672`） |
| `PageUp` / `PageDown` | `transcript_page_up/down` | ✓ | 翻 transcript，**不移动输入框焦点** |

`check_action()` 是这套键的围栏（`tui/app.py:265-293`）：

- `screen_stack > 1`（模态浮层压在上面）时，上述自定义动作全部返回 `None`——浮层原生处理这些键，绝不被抢占。
- 其余情况：历史导航 / 翻页 / Tab / Esc 始终被消费；`Enter` 只在 palette 打开时被消费。

**没有** `/model`、`/threads` 的快捷键——它们只能通过 slash 命令（或 palette 选中）打开。这一点与源码一致。

## 界面构成

| 区域 | 内容 | 源码 |
|------|------|------|
| header | `DeerFlow` + model + thread 标签 + cwd + `N skills` | `tui/render.py:140-152` |
| transcript | `UserRow`/`AssistantRow`/`ToolRow`/`SystemRow` 渲染；空态提示 "Type a message to begin. Press / for commands, ? for help." | `tui/render.py:24-36` |
| tool card | `  ⚙ Title  detail   ◐/✓/✗`，完成后追加 dim 的结果预览 | `tui/render.py:77-87` |
| status | run 状态 + spinner + 标题 + model + thread + `N tok` + 运行中 `esc interrupt` | `tui/render.py:90-113` |
| palette | 8 行窗口，选中行 `▌ /name  description` | `tui/render.py:116-137` |
| composer | 3 行圆角输入框，`Message DeerFlow…   ( / for commands )` | `tui/app.py:122-130`、`208` |

- **Markdown 语义**：只有"当前正在生成"的那条 assistant 行渲染为纯文本（避免 Markdown 回流抖动），历史与已完成的回答都渲染 Markdown；流结束的瞬间会立刻重绘成 Markdown（`tui/render.py:24-36`、`tui/app.py:645-649`）。
- **工具摘要**是纯函数：工具名→友好标题（`read_file`→Read、`bash`→Bash、`task`→Subagent…，未知名做 humanize），detail 从每个工具最相关的参数键里取第一个非空字符串，否则退化为紧凑 JSON；detail 截断 **80** 字符，result 截断 **160** 字符（`tui/message_format.py:15-50`、`53-57`）。
- **transparent 模式**：`--tui-transparent` 或 `DEER_FLOW_TUI_TRANSPARENT` 为真时，把 Textual 的 `ansi_default` 背景追加进 CSS，并以 `ansi_color=True` 启动；默认仍是 solid 主题（`tui/app.py:44-55`、`176-180`）。
- **CJK/IME 光标**：`widgets/composer.py` 覆写 `_cursor_offset`，去掉 Textual 在"光标位于值末尾"时无条件的 `+1`，修正双宽字符后 IME 候选窗跟随的硬件光标漂移。

## 流式渲染管线

1. `DeerFlowClient.stream()` 是**同步生成器**，因此跑在 Textual worker **线程**上：`run_worker(..., thread=True, exclusive=True, group="agent")`（`tui/app.py:608-613`）。
2. 每个产出的 action 经 `call_from_thread` 编组回 UI 线程，fold 进 `reduce(state, action)`（`tui/app.py:628-641`）。
3. transcript 重绘是**合并**的：`set_interval(0.06, ...)` ≈ 16fps 的 flush 定时器，只在 dirty 时渲染；`RunEnded` 时立即 flush（`tui/app.py:214`、`655-658`、`645-649`）。spinner 是 `set_interval(0.1, ...)` 的 100ms tick（`tui/app.py:213`）。

`runtime.translate()` 的事件映射（`tui/runtime.py:41-89`）：

| StreamEvent | 产出的 action |
|-------------|---------------|
| `messages-tuple` + `type=ai` | 有文本 → `AssistantDelta`；每个 `tool_calls[]` → `ToolStarted` |
| `messages-tuple` + `type=tool` | `ToolResult`（`is_error` 或 `status=="error"` 置错） |
| `end` | `RunEnded(usage=...)` |
| `values` | 仅当 `title` 为非空字符串时产 `ThreadTitle`（取 `.strip()`） |
| `custom` | **不增量渲染**，忽略 |

`stream_actions()` 用 `RunStarted` / `RunEnded` 给每次 run 加括号，**任何异常**都转成 `AssistantError` 行再补 `RunEnded`，不会崩 UI（`tui/runtime.py:99-114`）。

`view_state.reduce()` 的关键契约（`tui/view_state.py:167-390`）：

- `ViewState` 与所有 row 都是 frozen dataclass；状态只能通过 action 变化。
- `AssistantDelta` 按 **id** 在整个 transcript 里匹配已有行（因为客户端每轮会重发历史消息），而不是只匹配末尾行；文本合并分三种情形：累计重发→替换、更短的陈旧重发→保留、真增量→追加（`_merge_stream_text`，`tui/view_state.py:322-333`）。
- **空 id** 的 delta 不能按 id 匹配（所有无 id 分片共享 `""`），改由 `streaming_anonymous_row_index` 按**行位置**追踪本轮匿名行，且只在它仍是最后一行时复用；`RunStarted`/`RunEnded`/`ClearRows` 都会重置该索引（`tui/view_state.py:257-319`）。
- `ToolStarted` / `ToolResult` 按 `tool_call_id` 去重；**空 id 的分片直接丢弃**；收到没有对应卡片的 result 时补一张卡片（`tui/view_state.py:336-390`）。
- `ClearRows` 只清 `rows`（并重置 streaming 指针），不动 `usage` / `title`。

## 滚动与折叠语义

- **保持阅读位置**：`_refresh_transcript()` 先判断 `scroll.is_vertical_scroll_end`。在底部 → 跟随输出 `scroll_end()`；不在底部（用户上翻）→ 记下 `scroll_y`，重绘后再 `scroll_to(y=..., animate=False)` 恢复**绝对位置**（`tui/app.py:735-749`）。这就是 #4975 的行为：流式更新不再把视口拉回底部。
- **翻页不与流式打架**：`PageUp`/`PageDown` 会置 `_transcript_scroll_pending=True`，在其完成回调里清除；此期间到达的流式重绘**跳过**跟随/恢复逻辑，让翻页动作胜出（`tui/app.py:688-699`、`740-743`）。
- **没有折叠（collapse）能力**：`view_state.py` 没有折叠状态，`/details` 只是占位提示"本构建始终显示详细信息"（`tui/app.py:444-445`）。所以"折叠语义"在 v2.1.0 不存在，只有"清空显示"（`/clear`）。

## 会话持久化与恢复

`session.py` 负责装配，`persistence.py` 负责 Web UI 可见性。

- `open_session(persistence=True)`：`get_checkpointer()` → `DeerFlowClient(checkpointer=...)`；`persistence=True` 时再建 `ThreadMetaWriter`（`tui/session.py:84-103`）。
- TUI 启动用默认 `persistence=True`，并在 `finally` 里 `session.close()` 关闭后台 DB loop 与引擎（`tui/app.py:756-767`）；headless 用 `persistence=False`（`tui/cli.py:253-259`）。
- **写什么**：首个 turn 前在 worker 线程调 `writer.ensure_created(thread_id, assistant_id="lead-agent", metadata={"source": "tui"})`——只在 `threads_meta` 里没有该线程时创建一行（`tui/app.py:620-625`、`tui/persistence.py:64-80`）。
- **写在哪**：与 Gateway **同一个** DB（`threads_meta` SQL 表），owner 是本地默认用户 `DEFAULT_USER_ID`（`"default"`）（`tui/persistence.py:58`）。用 harness 自己的 `deerflow.persistence.engine.init_engine_from_config(config.database)` + `make_thread_store(session_factory)` 建 store，**不需要 Gateway 进程**（`tui/persistence.py:91-111`）。
- **DB 事件循环**：SQLAlchemy async engine 绑定创建它的 loop，所以所有 DB 工作跑在一个名为 `deerflow-tui-db` 的常驻 daemon 线程上的单一 loop，调用默认超时 15s（`tui/persistence.py:28-45`）。`session.close()` 先 `close_engine()` 再停 loop（`tui/session.py:69-81`）。
- **标题回写**：只有 run **正常完成**（未被 cancel）且收到过非空 `ThreadTitle` 时才 `update_display_name`——被中断的 run 可能只拿到标题中间件的截断猜测，不落库（`tui/app.py:631-638`）。
- **Web UI 为什么看得见**：Web UI 的侧边栏列的是 `threads_meta`（按 `user_id` 过滤），不是 checkpointer；内嵌运行只写 checkpointer，所以这一行就是补齐缺口的关键（`tui/persistence.py:1-16`）。

`Session.resolve_ref()` 的恢复语义（`tui/session.py:37-64`）：先按 **thread id** 精确匹配（拉最多 100 条），再按**标题**精确匹配；都没命中时把入参当字面 id，先过 `validate_thread_id`（1–64 个 ASCII 字母/数字/`-`/`_`），不合法就抛错而不是静默建一个新命名空间。`--continue` = 取 `list_threads(limit=1)` 的第一条（`tui/session.py:31-34`）。

**不持久化的东西**：transcript 行、滚动位置、palette 状态都只在内存里；输入历史也没有持久层（见下）。

### 输入历史

`InputHistory` 是纯内存、有界（`DEFAULT_LIMIT = 200`）的栈（`tui/input_history.py:10-58`）：

- `add()` 忽略纯空白，且**忽略与上一条完全相同的连续重复**；超出上限从头裁剪。
- `up(draft)`：首次上翻时把当前草稿存起来（"stash draft"），一路往回翻；`down()` 翻过最新一条后恢复草稿。
- `↑`/`↓` 在 palette 关闭时驱动它；单条提交后 `add()` 会重置游标与草稿。TUI 关闭即丢失，不落盘。

## 与 `DeerFlowClient` 的关系

TUI 是 `DeerFlowClient` 的 **UI shell**，不 fork agent 行为：同一套 `config.yaml`、同一套 `DEER_FLOW_HOME`、同一个 checkpointer provider。

- 用到的 client 方法：`stream()` / `chat()`（headless）、`list_models()`、`list_skills(enabled_only=True)`、`list_threads()`、`get_goal()` / `set_goal()` / `clear_goal()`、`get_mcp_config()`、`get_memory()`、`list_uploads()`（`tui/app.py:221-237`、`451-596`）。
- action 经 `call_from_thread` 编组，`reduce()` 是唯一状态入口——UI 侧没有第二套对话状态机。
- `/model` 的选择结果作为 `model_name` kwarg 透传给 `client.stream()`；`--recursion-limit` 作为 `recursion_limit` 透传（`tui/app.py:615-628`、`tui/cli.py:219-222`）。

## 已知降级路径

| 条件 | 行为 | 源码 |
|------|------|------|
| `textual` 未安装，且**未**强制 `--tui` | stderr 打印安装提示 + headless help，退出码 **0** | `tui/cli.py:294-302` |
| `textual` 未安装，且给了 `--tui` | 只打印安装提示，退出码 **1** | `tui/cli.py:297-299` |
| 无 TTY 且无 headless 参数 | stderr 打印原因 + help，退出码 **2** | `tui/cli.py:183-189`、`238-242` |
| `database.backend = memory`（无 SQL store）或持久化初始化失败 | `ThreadMetaWriter` 静默 no-op（`enabled=False`），TUI 照常工作 | `tui/persistence.py:96-111`、`60-62` |
| header 的 model / skills 查询失败 | 吞掉异常，model 置空、skills 置 0 | `tui/app.py:224-237` |
| `/goal`、`/mcp`、`/memory`、`/uploads` 查询失败 | 出一行错误 `SystemRow`，不崩 | `tui/app.py:513-596` |
| `client.stream()` 抛异常 | `AssistantError` 行 + `RunEnded`，可继续对话 | `tui/runtime.py:112-114` |
| `/tools`、`/artifacts`、`/details` | 占位提示（见命令表） | `tui/app.py:438-445` |

## 架构分层（15 个文件）

| 层 | 文件 | 职责 |
|----|------|------|
| 入口 | `cli.py` | `plan_launch()` 决策 + headless `print`/`json` + `main()` |
| App | `app.py` | Textual `App`；worker 线程跑 `DeerFlowClient.stream()`，`call_from_thread` 编组 action |
| 状态 | `view_state.py` | 不可变 `ViewState` + 纯 `reduce(state, action)` |
| 运行时 | `runtime.py` | `translate(StreamEvent) → [Action]` + `stream_actions()` 括号化一次 run |
| 会话/持久化 | `session.py` / `persistence.py` | 构建 client + checkpointer；`ThreadMetaWriter` 写 `threads_meta` |
| UI | `widgets/composer.py`、`render.py`、`theme.py` | 输入框（含 CJK 光标修正）、Rich 渲染器、颜色/符号 |
| 纯辅助 | `command_registry.py`、`input_history.py`、`message_format.py` | slash 注册表 + 解析、↑↓ 历史、工具摘要与截断 |

除 `app.py`（与 `widgets/composer.py`）外都不依赖 Textual，可直接单测。测试是 `backend/tests/test_tui_*.py`，共 **16** 个文件：`test_tui_app.py`、`test_tui_cli.py`、`test_tui_cli_main.py`、`test_tui_command_registry.py`、`test_tui_composer.py`、`test_tui_input_history.py`、`test_tui_message_format.py`、`test_tui_overlays.py`、`test_tui_palette.py`、`test_tui_palette_render.py`、`test_tui_persistence.py`、`test_tui_render.py`、`test_tui_runtime.py`、`test_tui_session.py`、`test_tui_transparent.py`、`test_tui_view_state.py`。

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k tui -q
```
