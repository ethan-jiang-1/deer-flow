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
