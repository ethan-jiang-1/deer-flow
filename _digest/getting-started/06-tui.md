---
title: "TUI 终端工作台"
description: "`deerflow` CLI：安装、三种模式（TUI/headless print/headless JSON）、slash palette、goal 管理。"
topics: [tui, cli, terminal]
---

# TUI 终端工作台

DeerFlow 现在有可安装的 `deerflow` CLI 命令了。

## 安装

```bash
uv pip install deerflow-harness[tui]
```

需要 `textual>=0.80`（可选依赖）。如果 `textual` 未安装，CLI 降级为 headless help 并提示安装。

也可以不安装直接用：
```bash
cd backend && PYTHONPATH=. uv run python -m deerflow.tui
```

## 三种模式

| 模式 | 触发 | 说明 |
|------|------|------|
| `--tui` | TTY 自动检测 或 `DEER_FLOW_TUI=1` | 全屏终端 UI（Textual） |
| `--print MESSAGE` | 显式指定 或 管道输入 | Headless，打印最终回答 |
| `--json MESSAGE` | 显式指定 或 管道输入 | Headless，逐行输出 JSON StreamEvents |

```bash
# TUI 模式
deerflow
DEER_FLOW_TUI=1 deerflow

# Headless 文本输出
deerflow --print "用 Python 写冒泡排序"
echo "hello" | deerflow --print

# Headless JSON 流（适合脚本消费）
deerflow --json "列出 workspace 文件"
echo "scan files" | deerflow --json | while read line; do process "$line"; done
```

## TUI 功能

- **Slash palette**：输入 `/` 打开命令面板（`/goal`、`/models`、`/new`），Tab 补全
- **Goal 管理**：`/goal set "目标描述"` → agent 自动续跑到完成
- **Model switcher**：`Ctrl+P` 切换模型
- **Thread switcher**：`Ctrl+T` 切换/创建线程
- **流式渲染**：60ms flush 间隔，100ms spinner
- **键盘**：`Ctrl+C` 中断/退出，`Ctrl+L` 重绘，`Ctrl+U` 清空输入
- **Web UI 可见**：TUI session 写入 `threads_meta` 表，在 Web UI 左侧栏显示

源码：`deerflow/tui/`（14 个文件），`pyproject.toml [project.scripts]`

## 支持 headless CI

```bash
# 在 CI 中用管道输入
echo "审查 src/ 目录的安全问题" | deerflow --print > review.txt

# 或 JSON 流
echo "analyze" | deerflow --json | tee /tmp/agent-output.jsonl
```

Headless 模式使用 `persistence=False`（不写 threads_meta，无后台 DB loop）。

## 架构

TUI 14 个源文件的分层：

| 层 | 文件 | 职责 |
|----|------|------|
| 入口 | `cli.py` | `plan_launch()` 决策 + `main()` 分发 |
| App | `app.py` | Textual `App`，worker thread 跑 `DeerFlowClient.stream()` |
| 状态 | `view_state.py` | 不可变 `ViewState` + `reduce(state, action)` |
| 运行时 | `runtime.py` | `translate(StreamEvent) → [Action]` |
| 持久化 | `persistence.py` | `ThreadMetaWriter` 写 `threads_meta` 表 |
| 会话 | `session.py` | `open_session()` 构建 `DeerFlowClient` + checkpointer |
| UI | `widgets/composer.py`, `render.py`, `theme.py` | 输入框、Rich 渲染、颜色 |
| 辅助 | `command_registry.py`, `input_history.py`, `message_format.py` | Slash 命令、↑↓ 历史、工具摘要 |

纯层（无 Textual 依赖）全部可单元测试：`test_tui_cli.py`、`test_tui_view_state.py`、`test_tui_runtime.py` 等 12 个测试文件。

## 持久化与 Web UI 集成

TUI 通过 `persistence.py` 的 `ThreadMetaWriter` 写入 `threads_meta` SQL 表（与 Gateway 共享同一 DB）。TUI session 自动出现在 Web UI 左侧栏。`open_session(persistence=True)`（TUI 模式）启用此功能；`persistence=False`（headless 模式）跳过。

## 与 DeerFlowClient 的关系

TUI 是 `DeerFlowClient` 的 UI shell——不 fork agent 行为。`DeerFlowClient.stream()` 在 worker 线程上同步运行，action 通过 `call_from_thread` 编组到 UI 线程。同一套 `config.yaml`、同一套 `DEER_FLOW_HOME`。
