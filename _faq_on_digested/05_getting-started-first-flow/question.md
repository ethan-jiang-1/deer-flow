# Q5: DeerFlow 入门 — 从零安装到搭建第一个 Agent Flow

> **问题：** 我想从零开始把 DeerFlow 跑起来（安装、配模型、体验），然后借助这个框架搭建一个 agent flow。完整的工程过程是怎样的？

> 🔄 同步 #8（v2.2.0）：本目录 7 篇已按 v2.2.0 源码重核。最影响"从零开始"体验的三处变化：① 新增可安装的 `deerflow` 终端命令（TUI / `--print` / `--json`），`uv pip install 'deerflow-harness[tui]'` 后就能在终端里直接聊，不必先起 Gateway；② `config_version` 45 → **63**（`config.example.yaml:23`，模板 3680 行），升级用 `make config-upgrade`；③ `.env` 由 `DEER_FLOW_ENV_FILE` 选择器决定（`deerflow/env.py:10`），没设才退回 `load_dotenv()` 自动发现。入口仍是 [answer.md](answer.md)。
