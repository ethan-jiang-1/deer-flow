---
title: "TUI 终端工作台"
description: 'deerflow CLI：安装、五种启动模式（TUI / headless print / headless JSON / 降级 help / 透明背景）、命令全集与别名、键位真值、会话持久化与输入历史、流式渲染与滚动语义。'
topics: [tui, cli, terminal]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# TUI 终端工作台

DeerFlow 有可安装的 `deerflow` 命令:一个跑在**内嵌** `DeerFlowClient` 上的终端工作台,不需要 Gateway / Nginx / Docker。源码:`backend/packages/harness/deerflow/tui/`(下文简称 `tui/`,共 **15** 个 `.py` 文件:`app.py`、`cli.py`、`command_registry.py`、`input_history.py`、`message_format.py`、`persistence.py`、`render.py`、`runtime.py`、`session.py`、`theme.py`、`view_state.py`、`__init__.py`、`__main__.py`、`widgets/__init__.py`、`widgets/composer.py`)。

> 真值顺序:本页所有契约以 v2.2.0 源码为准(`app.py` 927 行、`cli.py` 412 行、`view_state.py` 362 行、`session.py` 103 行、`persistence.py` 119 行)。设计说明另见 `backend/docs/TUI.md` 与 `tui/AGENTS.md`。

## 安装与前置

```bash
uv pip install 'deerflow-harness[tui]'     # 或:pip install textual
```

- console script 注册在 `packages/harness/pyproject.toml:70-71`:`deerflow = "deerflow.tui.cli:main"`。
- `textual` 是**可选**依赖 `textual>=0.80`(`packages/harness/pyproject.toml:73-75`),核心 harness 不因它变重。
- 从源码跑(在 `backend/` 目录;harness 已 editable 安装进 backend 的 venv):

```bash
cd backend && PYTHONPATH=. uv run python -m deerflow.tui
```

`python -m deerflow.tui` 走 `tui/__main__.py`,与 console script 同一个 `cli.main()`。

## 启动模式(`plan_launch()` 真值)

`plan_launch(*, stdin_isatty, stdout_isatty, env)` 是**纯函数**(无 I/O、不构造 client),`tui/cli.py:119`。注意三个参数从 v2.1.0 起是**仅关键字**参数。四种 `mode`(另加透明背景开关):

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| `print` | `--print MESSAGE`(或 `--print` + 管道 stdin);`--cli` + 位置参数 / 管道 / `--continue` | `stream()` 后只打印**最后一条** AI 消息的累计文本到 stdout |
| `json` | `--json MESSAGE`(或 `--json` + 管道 stdin) | 逐行 `{"type": ..., "data": ...}` JSON,`ensure_ascii=False` 且每行 flush |
| `tui` | `--tui` 或 `DEER_FLOW_TUI` 为真 或 **stdin 与 stdout 都是 TTY** | 全屏 Textual UI(可叠加 `--tui-transparent` / `DEER_FLOW_TUI_TRANSPARENT`) |
| `headless-help` | 以上都不满足,或参数不完整 | 打印降级帮助到 stderr |

判定优先级(自上而下,先命中先返回):

1. `--print`(`tui/cli.py:136-147`)
2. `--json`(`tui/cli.py:149-160`)
3. `--cli`(`tui/cli.py:162-184`)
4. `--tui` / `DEER_FLOW_TUI` / TTY 自动检测(`tui/cli.py:186-196`;`forced_tui = bool(args.tui)` 在 `tui/cli.py:186`,`transparent` 判定在 `tui/cli.py:187`)
5. 兜底 `headless-help`(`tui/cli.py:198-201`)

契约级细节:

- **退出码**:`headless-help` 且带原因 → **2**;不带原因 → **0**(`tui/cli.py:259` 的 `return 0 if not plan.reason else 2`)。所以"没 TTY 又没给 headless 参数"是 exit 2,不会挂起。
- **🆕 `--print` / `--json` 失败 → exit 1**(v2.2.0 新增)。两类失败都算:抛异常(`tui/cli.py:389` 的 `return 1`),以及**流正常结束但最后一条 AI 消息被 LLM error middleware 标成 `deerflow_error_fallback`**。后者由 `_RunOutcome.error_text()`(`tui/cli.py:326`)识别,`_run_print` 会把 `Error: LLM request failed (error_type=…, error_reason=…)` 打到 stderr 并返回 1(`tui/cli.py:366-368`);`--json` 则额外写一行 `{"type":"error","data":{"message":…}}` 到 stdout(`_report_json_error`,`tui/cli.py:335`)。**这条是脚本可依赖的契约**——不加它就区分不出"真回答"和"错误兜底文本"。
- **🆕 `--print` 与 `--json` 互斥**(argparse `add_mutually_exclusive_group`,`tui/cli.py:58-72`),一次调用只跑一个 headless 模式,避免丢掉另一侧的消息。
- **🆕 消息只能给在一处**:`args.print` / `args.json` 现在是 `nargs="*"`,`_headless_message()`(`tui/cli.py:103`)把"flag 后面的词"和"位置参数"二选一——两处都给会直接 argparse 报错(因为 argparse 丢失了 flag 词与位置词的先后关系,不做猜测性拼接)。
- **`--print` / `--json` 缺 MESSAGE 且 stdin 是 TTY** → 直接 `headless-help`(原因:`--print needs a MESSAGE argument or piped stdin.` / `--json needs a MESSAGE argument or piped stdin.`),`--continue` 也救不回来。要"续跑最近线程"走 `--cli` 或 TUI。
- `--cli` 缺消息时,只要给了 `--continue` **或** stdin 不是 TTY 就进入 `print` 模式并读 stdin(注意此时 `read_stdin=True` 是无条件的,stdin 是 TTY 而只给 `--continue` 会一直读到 EOF);两者都没有时报 `--cli needs a message. Try: deerflow --print "your question".`
- `--recursion-limit` 只接受正整数(`_positive_int`,`tui/cli.py:41`),且**必须**同时给 `--print`/`--json`/`--cli`,否则 argparse 报错(parser 定义在 `tui/cli.py:86-91`)。
- 首位置参数 `chat` 是默认会话面的别名,会被剥掉(`_strip_chat`,`tui/cli.py:95`)——`deerflow chat` ≡ `deerflow`。
- `extensions` 是唯一在 `plan_launch` **之前**被拦截的子命令,转发给 `deerflow.extensions.cli.main`(`tui/cli.py:242-247`)。`deerflow extensions --help` 因此不经过 argparse。
- 环境变量真值:`_truthy()` 只认字符串 `1` / `true` / `yes` / `on`(大小写不敏感、去空白)(`tui/cli.py:115`)。TUI 相关两个:`DEER_FLOW_TUI`(强制 TUI)、`DEER_FLOW_TUI_TRANSPARENT`(透明背景)。
- TUI 模式下的位置参数(`deerflow --tui "问题"`)会存进 `LaunchPlan.message`,在 `on_mount`(以及 `tui/app.py:290` 的 `_restore_draft`)里自动发送;发送失败时把原文塞回输入框,不静默丢消息。

### 🆕 透明背景模式

`--tui-transparent`(`tui/cli.py:77-82`)或 `DEER_FLOW_TUI_TRANSPARENT` 为真时,`LaunchPlan.transparent=True`;`DeerFlowTUI.__init__` 在 `tui/app.py:206` 把 `_TRANSPARENT_CSS`(`tui/app.py:65-76`,把 `Screen`/`#header`/`#scroll`/`#status`/`#palette`/`#composer` 及 `SelectScreen` 的背景统一改成 `ansi_default`)追加进 `self.CSS`,并以 `ansi_color=True` 启动。默认仍是 solid 主题。

### headless 用法

```bash
# 一次性文本回答
deerflow --print "用 Python 写冒泡排序"
echo "hello" | deerflow --print

# JSON 流(每行一个 StreamEvent:{"type","data"})
deerflow --json "列出 workspace 文件"
echo "scan files" | deerflow --json | while read -r line; do process "$line"; done

# 指定线程 / 最近线程
deerflow --print "继续上次" --resume my-thread-id
deerflow --print "继续" --continue

# 放宽 super-step 预算
deerflow --recursion-limit 250 --print "长任务"
```

- headless 走 `open_session(persistence=False)`——**不写 `threads_meta`,不起后台 DB 事件循环/连接池**(`tui/cli.py:270-276`)。
- `--resume` / `--continue` 在 headless 下同样生效:都经 `Session.resolve_thread(plan)`(`tui/session.py:27-35`)。
- recursion limit 缺省 **100**(`client.py:328` 的 `overrides.get("recursion_limit", 100)`)。`max_recursion_limit` 是 Gateway 对客户端传入值的上限,不是内嵌 CLI 的默认值。

## 命令全集与别名

内置命令是 `BUILTIN_COMMANDS` 常量,顺序即 `/help` 与 palette 的展示顺序(`tui/command_registry.py:38-57`),共 **18** 条:

| 命令 | 注册表描述 | 实际行为(`tui/app.py:469` 的 `_handle_builtin`) |
|------|-----------|-------------------------------|
| `/help` | Show commands and keybindings | 输出一行全命令表 + 一行键位表(`tui/app.py:43-44` 的 `_HELP_KEYS` / `_HELP_TEXT`) |
| `/new` | Start a fresh thread | 清 `_conv_thread_id` + 重置 `ViewState`;**run 进行中被拦** |
| `/clear` | Clear the transcript display | 只发 `ClearRows`(清行,不换 thread、不动持久化);**run 进行中被拦** |
| `/threads` | Open the thread switcher | 模态线程选择器(最近 20 条,`_open_thread_switcher`,`tui/app.py:543`) |
| `/switch` | Open the thread switcher | `/threads` 的**别名** |
| `/resume` | Resume a thread by id or title | `args` 为空 → 打开选择器;否则切换线程(`_resume_thread`,`tui/app.py:568`;`_switch_to_thread` 在 `tui/app.py:584`) |
| `/goal` | Set, show or clear the active goal | 空 = 显示;`clear`/`reset`/`off` = 清除;其它 = 设为目标(`_handle_goal`,`tui/app.py:593`;语义真值 `runtime/goal.py`) |
| `/model` | Open the model picker | 模态模型选择器(`_open_model_picker`,`tui/app.py:524`),选中后作为 `model_name` 传给 `stream()` |
| `/skills` | Browse enabled and available skills | 列出已启用 skill 名(`_show_skills`,`tui/app.py:631`) |
| `/tools` | Show built-in, MCP and sandbox tools | **占位提示**:工具在 agent 运行时里,MCP 请用 `/mcp` |
| `/mcp` | Show MCP server status | 每个 server 的 `on`/`off`(`_show_mcp`,`tui/app.py:635`) |
| `/memory` | Show memory status and injected facts | fact 数量 + top of mind(`_show_memory`,`tui/app.py:647`)。实现读的是**顶层** `data["topOfMind"]`,而默认 deermem 文档把它嵌在 `user.topOfMind`,所以实际通常渲染成 `—` |
| `/uploads` | Show uploaded files for this thread | 当前线程上传文件列表(`_show_uploads`,`tui/app.py:670`) |
| `/artifacts` | Show generated artifacts | **占位提示**:artifact 随 agent 写入内联出现 |
| `/details` | Toggle verbose activity rendering | **占位提示**:本构建始终显示详细信息(无折叠开关) |
| `/usage` | Show token usage and context | 读 `ViewState.usage`(无记录时提示;`_show_usage`,`tui/app.py:657`) |
| `/config` | Show resolved config paths and overrides | 只输出 `cwd` 与当前 model(`_show_config`,`tui/app.py:665`) |
| `/quit` | Exit the TUI | 若正在跑先中断,再 `exit()`;中断期间再按 Ctrl+C 立刻退出(`_QUIT_PENDING_TEXT`,`tui/app.py:45`) |

解析规则(`resolve()`,`tui/command_registry.py:110-131`):

- 不以 `/` 开头 → 普通消息,原文交给 agent。
- `/name args`:命中内置集合 → `builtin`;命中已启用 skill 名 → `skill`;否则 `unknown`(TUI 出错误行 "Unknown command /name. Try /help.")。
- 空名(如单独一个 `/`)→ `unknown`。

Skill 命令:每个**已启用** skill 贡献一条 `/skill-name`,但会被剔除两类名字(`build_registry`,`tui/command_registry.py:73-83`):与内置命令同名的,以及在共享保留名 `RESERVED_SLASH_SKILL_NAMES = frozenset({"agent", "bootstrap", "context", "goal", "help", "memory", "model", "models", "new", "status"})` 里的(`skills/slash.py:17`;v2.2.0 新增了 `context` 与 `model`)。剔除是刻意的——TUI 不能宣传一个 agent 运行时会拒绝的 skill 激活。

> **唯一的例外**:保留名 `context` 仍可注册成 `/context`,因为 agent 侧只拦 `context` 带 `compact` 参数的那一种调用(`skills/slash.py:19` 的 `_CONTEXT_COMPACT_ARGUMENT = "compact"`,判定在 `skills/slash.py:46`)。所以 `build_registry` 用 `name == "context"` 开了口子。

Palette(`_open_palette`,`tui/app.py:384`;输入变化监听在 `on_text_area_changed` `tui/app.py:302`):输入框内容以 `/` 开头且**不含空格**时打开;`filter_commands()` 按 名字前缀 → 名字子串 → 描述子串 排序(`tui/command_registry.py:86-107`)后展示。渲染成 8 行窗口,超出显示 `… N more`(`render_palette`,`tui/render.py:116-137`)。

## 键位(`DeerFlowTUI.BINDINGS` 真值)

`tui/app.py:190-204`。除 `Ctrl+C`(`show=True`)外全部 `show=False`:**只有 Ctrl+C 会出现在 Textual 的快捷键栏**,其余靠 `/help` 的键位行或本文档。

| 键 | 动作 | priority | 语义 |
|----|------|----------|------|
| `Ctrl+C` | `interrupt` | ✓ | 正在跑 → 中断 run;空闲 → 退出(`action_interrupt`,`tui/app.py:801`) |
| `Ctrl+L` | `redraw` | — | `refresh(layout=True)` + 全量重绘(`tui/app.py:840`) |
| `Ctrl+U` | `clear_composer` | — | 清空输入框(`tui/app.py:844`) |
| `↓` / `↑` | `nav_down` / `nav_up` | ✓ | palette 打开时移动高亮(`tui/app.py:413`/`:418`);否则走输入历史(`_history_move`,`tui/app.py:376`) |
| `Tab` | `palette_complete` | ✓ | palette 打开时补全高亮项(补 `"/name "`,`tui/app.py:423`);关闭时**吃掉按键**,保持焦点在输入框 |
| `Enter` | `palette_accept` | ✓ | palette 打开时:内置命令直接执行,skill 只补全(还要补任务参数)(`tui/app.py:430`);关闭时让位给 composer 的 `Submitted` 正常提交 |
| `Esc` | `escape` | ✓ | palette 打开 → 关 palette;否则若在跑 → 中断 run(`action_escape`,`tui/app.py:807`) |
| `PageUp` / `PageDown` | `transcript_page_up/down` | ✓ | 翻 transcript,**不移动输入框焦点**(`tui/app.py:847`/`:852`) |

`check_action()` 是这套键的围栏(`tui/app.py:324`):

- `screen_stack > 1`(模态浮层压在上面)时,上述自定义动作全部返回 `None`——浮层原生处理这些键,绝不被抢占。
- 其余情况:历史导航 / 翻页 / Tab / Esc 始终被消费;`Enter` 只在 palette 打开时被消费。

**没有** `/model`、`/threads` 的快捷键——它们只能通过 slash 命令(或 palette 选中)打开。

## 界面构成

| 区域 | 内容 | 源码 |
|------|------|------|
| header | `DeerFlow` + model + thread 标签 + cwd + `N skills` | `render_header`,`tui/render.py:140-152`;调用点 `tui/app.py:829`(`_refresh_header`) |
| transcript | `UserRow`/`AssistantRow`/`ToolRow`/`SystemRow` 渲染;空态提示 "Type a message to begin. Press / for commands, ? for help." | `render_transcript`,`tui/render.py:24-36` |
| tool card | `  ⚙ Title  detail   ◐/✓/✗`,完成后追加 dim 的结果预览 | `_render_tool`,`tui/render.py:77-87` |
| status | run 状态 + spinner + 标题 + model + thread + `N tok` + 运行中 `esc interrupt` | `render_status`,`tui/render.py:90-113` |
| palette | 8 行窗口,选中行 `▌ /name  description` | `tui/render.py:116-137` |
| composer | 圆角输入框,`Message DeerFlow…   ( / for commands )`;🆕 多行模式下高度 5(`#composer.multiline`,`tui/app.py:158-160`) | `tui/app.py:234`(`compose`)、`widgets/composer.py` |

- **Markdown 语义**:只有"当前正在生成"的那条 assistant 行渲染为纯文本(避免 Markdown 回流抖动),历史与已完成的回答都渲染 Markdown;流结束的瞬间会立刻重绘成 Markdown(`tui/render.py:24-36`、`_on_action` 里 `RunEnded` 分支 `tui/app.py:784-788`)。
- **工具摘要**是纯函数:工具名→友好标题(`read_file`→Read、`bash`→Bash、`task`→Subagent…,未知名做 humanize),detail 从每个工具最相关的参数键里取第一个非空字符串,否则退化为紧凑 JSON;detail 截断 **80** 字符,result 截断 **160** 字符(`DEFAULT_DETAIL_LIMIT` / `DEFAULT_RESULT_LIMIT`,`tui/message_format.py:50-51`;截断函数 `tui/message_format.py:53`)。
- **🆕 模态浮层里的字面文本**:`SelectScreen`(`tui/app.py:79`)把标题和每个选项都包成 `rich.text.Text` 再交给 `Label` / `Option`。Textual 会把裸 `str` 当内容标记解析,所以线程标题写成 `Fix [/bold] in parser` 会抛 `MarkupError`、`[a]` 会直接消失。
- **CJK/IME 光标**:`widgets/composer.py` 覆写 `cursor_position` 的 getter/setter,在"光标位于值末尾"时不做 Textual 那个无条件的 `+1`,修正双宽字符后 IME 候选窗跟随的硬件光标漂移;`can_move_up` / `can_move_down` 依据 TextArea 的**视觉换行行**判断,长行软换行时 ↑/↓ 先在同一逻辑行内移动。

## 流式渲染管线

1. `DeerFlowClient.stream()` 是**同步生成器**,因此跑在一条 **daemon 线程**上:`Thread(target=self._stream_worker, name="deerflow-tui-run", daemon=True).start()`(`_start_run_thread`,`tui/app.py:723`)。v2.2.0 **刻意不用 Textual 的 thread worker**——后者跑在 asyncio 默认 executor 上,`App.run()` 和解释器退出都会 join 它,于是"退出"会被卡在一个已中断但还没到下一个事件的步骤上。现在退出由 app 自己等 worker 停(`_exit_once_workers_stop`, `tui/app.py:834`)。
2. 每个产出 action 先过 `_on_stream_action(run, action)`(`tui/app.py:769`)做**身份与取消校验**:run 已被替换、线程已切换、已取消或已结束时直接丢弃,防止上一轮的事件写进新一轮。通过后再 `call_from_thread` 编组回 UI 线程 fold 进 `reduce(state, action)`。
3. transcript 重绘是**合并**的:`set_interval(0.06, _flush_transcript)` ≈ 16fps 的 flush 定时器,只在 dirty 时渲染;`RunEnded` 时立即 flush(`tui/app.py:251-252`、`_on_action` 的 `RunEnded` 分支)。spinner 是 `set_interval(0.1, _tick_spinner)` 的 100ms tick(`tui/app.py:251`)。
4. **🆕 中断**:`Ctrl+C`/`Esc` 置 `_Run.cancelled`(`_Run` dataclass 在 `tui/app.py:48-62`,`worker_running()` 用 `started`/`stopped` 两个 Event 判活)。同步生成器无法被真正打断,所以 worker 会**跑到下一个事件**才停;在此期间同一线程上的新消息被拒绝并提示等它停下,或用 `/new` / `/resume` 换线程(`tui/app.py:700-702`)。

`runtime.translate()` 的事件映射(`tui/runtime.py:41`,私有分派在 `tui/runtime.py:57`):

| StreamEvent | 产出的 action |
|-------------|---------------|
| `messages-tuple` + `type=ai` | 有文本 → `AssistantDelta`;每个 `tool_calls[]` → `ToolStarted` |
| `messages-tuple` + `type=tool` | `ToolResult`(`is_error` 或 `status=="error"` 置错) |
| `end` | `RunEnded(usage=...)` |
| `values` | 仅当 `title` 为非空字符串时产 `ThreadTitle`(取 `.strip()`) |
| `custom` | **不增量渲染**,忽略 |

`stream_actions()`(`tui/runtime.py:99`)用 `RunStarted` / `RunEnded` 给每次 run 加括号,**任何异常**都转成 `AssistantError` 行再补 `RunEnded`,不会崩 UI。

`view_state.reduce()` 的关键契约(`tui/view_state.py:167`):

- `ViewState` 与所有 row 都是 frozen dataclass;状态只能通过 action 变化。
- 🆕 `AssistantDelta` 按 **id** 在整个 transcript 里匹配已有行(而不是只匹配末尾行——同一条消息的 delta 都属于它自己那行,哪怕后面已经追加了别的行),匹配到就**原样追加**:`rows[i] = replace(row, text=row.text + action.text)`(`_apply_assistant_delta`,`tui/view_state.py:210`,追加在 `:241`)。v2.1.0 那套"累计重发→替换 / 更短陈旧重发→保留 / 真增量→追加"的合并启发式(`_merge_stream_text`)**已删除**——`DeerFlowClient.stream()` 只发增量文本,从不重发已交付内容、不重放历史轮次、不发累计快照,所以重复或延续的文本(如 `"ha"` + `"ha"`)是真的新文本。
- **空 id** 的 delta 不能按 id 匹配(所有无 id 分片共享 `""`),改由 `streaming_anonymous_row_index` 按**行位置**追踪本轮匿名行,且只在它仍是最后一行时复用(`_apply_assistant_delta_anonymous`,`tui/view_state.py:246`);`RunStarted`/`RunEnded`/`ClearRows` 都会重置该索引。
- `ToolStarted` / `ToolResult` 按 `tool_call_id` 去重(`tui/view_state.py:308` / `:338`);**空 id 的分片直接丢弃**;收到没有对应卡片的 result 时补一张卡片。
- `ClearRows` 只清 `rows`(并重置 streaming 指针),不动 `usage` / `title`。

## 滚动与折叠语义

- **保持阅读位置**:`_refresh_transcript()`(`tui/app.py:894`)先判断 `scroll.is_vertical_scroll_end`。在底部 → 跟随输出 `scroll_end()`;不在底部(用户上翻)→ 记下 `scroll_y`,重绘后再 `scroll_to(y=..., animate=False)` 恢复**绝对位置**(`tui/app.py:894-909`)。这就是 #4975 的行为:流式更新不再把视口拉回底部。
- **翻页不与流式打架**:`PageUp`/`PageDown` 会置 `_transcript_scroll_pending=True`,在其完成回调 `_finish_transcript_scroll`(`tui/app.py:857`)里清除;此期间到达的流式重绘**跳过**跟随/恢复逻辑,让翻页动作胜出(`tui/app.py:849-857`、`899-902`)。
- **没有折叠(collapse)能力**:`view_state.py` 没有折叠状态,`/details` 只是占位提示"本构建始终显示详细信息"。所以只有"清空显示"(`/clear`),没有"折叠"。

## 会话持久化与恢复

`session.py` 负责装配,`persistence.py` 负责 Web UI 可见性。

- `open_session(persistence=True)`(`tui/session.py:84`):`get_checkpointer()` → `DeerFlowClient(checkpointer=...)`;`persistence=True` 时再建 `ThreadMetaWriter`。TUI 启动用默认 `persistence=True`,并在 `finally` 里 `session.close()` 关闭后台 DB loop 与引擎(`run_tui`,`tui/app.py:915-927`);headless 用 `persistence=False`(`tui/cli.py:270-276`)。
- **写什么**:首个 turn 前在 worker 线程调 `writer.ensure_created(thread_id, assistant_id="lead-agent", metadata={"source": "tui"})`——只在 `threads_meta` 里没有该线程时创建一行(`tui/app.py:751-755`、`tui/persistence.py:72-88`)。
- **写在哪**:与 Gateway **同一个** DB(`threads_meta` SQL 表),owner 是本地默认用户 `DEFAULT_USER_ID`(`"default"`)(`ThreadMetaWriter.__init__`,`tui/persistence.py:63-66`)。用 harness 自己的 `deerflow.persistence.engine.init_engine_from_config(config.database)` + `make_thread_store(session_factory)` 建 store,**不需要 Gateway 进程**。
- **DB 事件循环**:SQLAlchemy async engine 绑定创建它的 loop,所以所有 DB 工作跑在一个名为 `deerflow-tui-db` 的常驻 daemon 线程上的单一 loop。`session.close()` 先 `close_engine()` 再停 loop(`tui/session.py:69-81`)。
- **标题回写**:只有 run **正常完成**(未被 cancel)且收到过非空 `ThreadTitle` 时才 `update_display_name`——被中断的 run 可能只拿到标题中间件的截断猜测,不落库(`tui/app.py:764-767`;`set_title` 在 `tui/persistence.py:90`)。
- **Web UI 为什么看得见**:Web UI 的侧边栏列的是 `threads_meta`(按 `user_id` 过滤),不是 checkpointer;内嵌运行只写 checkpointer,所以这一行就是补齐缺口的关键。

`Session.resolve_ref()` 的恢复语义(`tui/session.py:37-64`):先按 **thread id** 精确匹配(拉最多 100 条),再按**标题**精确匹配;都没命中时把入参当字面 id,先过 `validate_thread_id`(1–64 个 ASCII 字母/数字/`-`/`_`),不合法就抛错而不是静默建一个新命名空间。

🆕 `--continue` 取的是 `list_threads(limit=1, sort_by="updated_at")` 的第一条(`tui/session.py:31-34`)。加显式排序是必须的:不带 `sort_by` 时服务端默认序不一定按更新时间,`--continue` 可能续到一条旧线程。

**不持久化的东西**:transcript 行、滚动位置、palette 状态都只在内存里;输入历史也没有持久层(见下)。

### 输入历史

`InputHistory` 是纯内存、有界(`DEFAULT_LIMIT = 200`)的栈(`tui/input_history.py:10-58`):

- `add()`(`tui/input_history.py:23`)忽略纯空白,且**忽略与上一条完全相同的连续重复**;超出上限从头裁剪。
- `up(draft)`(`tui/input_history.py:35`):首次上翻时把当前草稿存起来("stash draft"),一路往回翻;`down()`(`tui/input_history.py:46`)翻过最新一条后恢复草稿。
- `↑`/`↓` 在 palette 关闭时驱动它;单条提交后 `add()` 会重置游标与草稿。TUI 关闭即丢失,不落盘。

## 与 `DeerFlowClient` 的关系

TUI 是 `DeerFlowClient` 的 **UI shell**,不 fork agent 行为:同一套 `config.yaml`、同一套 `DEER_FLOW_HOME`、同一个 checkpointer provider。

- 用到的 client 方法:`stream()` / `chat()`(headless)、`list_models()`、`list_skills(enabled_only=True)`、`list_threads()`、`get_goal()` / `set_goal()` / `clear_goal()`、`get_mcp_config()`、`get_memory()`、`list_uploads()`。
- action 经 `call_from_thread` 编组,`reduce()` 是唯一状态入口——UI 侧没有第二套对话状态机。
- `/model` 的选择结果作为 `model_name` kwarg 透传给 `client.stream()`;`--recursion-limit` 作为 `recursion_limit` 透传。

## 已知降级路径

| 条件 | 行为 | 源码 |
|------|------|------|
| `textual` 未安装,且**未**强制 `--tui` | stderr 打印安装提示 + headless help,退出码 **0** | `_run_tui` 的 import 兜底,`tui/cli.py:392`(`from deerflow.tui.app import run_tui` 在 `tui/cli.py:397`) |
| `textual` 未安装,且给了 `--tui` | 只打印安装提示,退出码 **1** | `tui/cli.py:392-406`(`forced_tui` 分支) |
| 无 TTY 且无 headless 参数 | stderr 打印原因 + help,退出码 **2** | `tui/cli.py:198-201`、`259` |
| 🆕 `--print` / `--json` 的 run 失败(含 LLM error fallback) | stderr 打 `Error: …`,`--json` 额外写一行 error 事件,退出码 **1** | `tui/cli.py:326`、`335`、`366-368`、`389` |
| `database.backend = memory`(无 SQL store)或持久化初始化失败 | `ThreadMetaWriter` 静默 no-op(`enabled=False`),TUI 照常工作 | `tui/persistence.py:68-70`、`96` 起 |
| header 的 model / skills 查询失败 | 吞掉异常,model 置空、skills 置 0 | `_load_session_info`,`tui/app.py:254` |
| `/goal`、`/mcp`、`/memory`、`/uploads` 查询失败 | 出一行错误 `SystemRow`,不崩 | `tui/app.py:593-682` |
| `client.stream()` 抛异常 | `AssistantError` 行 + `RunEnded`,可继续对话 | `_stream_worker`,`tui/app.py:725-739` |
| `/tools`、`/artifacts`、`/details` | 占位提示(见命令表) | `tui/app.py:469` 的 `_handle_builtin` |

## 架构分层(15 个文件)

| 层 | 文件 | 职责 |
|----|------|------|
| 入口 | `cli.py` | `plan_launch()` 决策 + headless `print`/`json`(含失败退出码)+ `main()` |
| App | `app.py` | Textual `App`;daemon 线程跑 `DeerFlowClient.stream()`,`_on_stream_action` 校验身份后编组 action |
| 状态 | `view_state.py` | 不可变 `ViewState` + 纯 `reduce(state, action)` |
| 运行时 | `runtime.py` | `translate(StreamEvent) → [Action]` + `stream_actions()` 括号化一次 run |
| 会话/持久化 | `session.py` / `persistence.py` | 构建 client + checkpointer;`ThreadMetaWriter` 写 `threads_meta` |
| UI | `widgets/composer.py`、`render.py`、`theme.py` | 输入框(含 CJK 光标修正)、Rich 渲染器、颜色/符号 |
| 纯辅助 | `command_registry.py`、`input_history.py`、`message_format.py` | slash 注册表 + 解析、↑↓ 历史、工具摘要与截断 |

除 `app.py`(与 `widgets/composer.py`)外都不依赖 Textual,可直接单测。测试是 `backend/tests/test_tui_*.py`,共 **19** 个文件:`test_tui_app.py`、`test_tui_cli.py`、`test_tui_cli_main.py`、`test_tui_command_registry.py`、`test_tui_composer.py`、`test_tui_input_history.py`、`test_tui_interrupted_run_drain.py`、`test_tui_message_format.py`、`test_tui_overlays.py`、`test_tui_palette.py`、`test_tui_palette_render.py`、`test_tui_persistence.py`、`test_tui_render.py`、`test_tui_run_isolation.py`、`test_tui_runtime.py`、`test_tui_session.py`、`test_tui_thread_switching.py`、`test_tui_transparent.py`、`test_tui_view_state.py`。

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k tui -q
```
