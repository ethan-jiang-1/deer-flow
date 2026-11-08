---
title: "怎么组织基于 deer-flow 的开发工作区？"
question: "我的 deep_research_harness 跑在 deer-flow 里面，强依赖 deer-flow 的运行时，仓库离开它跑不起来。但根目录放了大量不是我重点关心的框架代码，Coding Agent（Claude Code 等）一进来就被这些文件淹没、容易迷糊，不知道我的重点在哪。我想重新整理出一个全新的干净 repo，把 deer-flow 囊括进来（submodule 或其他形式），同时让 agent 一眼锁定重点。怎么做？"
topics: [workflow, repo-layout, git, submodule, workspace, coding-agent]
---

# 怎么组织基于 deer-flow 的开发工作区？

我的 `deep_research_harness` 跑在 deer-flow 里面，强依赖它的运行时，仓库离开它跑不起来。但根目录放了大量不是我重点关心的框架代码，Coding Agent 一进来就被淹没、容易迷糊。我想重新整理出一个全新的干净 repo，把 deer-flow 囊括进来（submodule 或其他形式），同时让 agent 一眼锁定重点。怎么做？

> 🔄 同步 #8（v2.2.0）：本目录三篇已按 v2.2.0 复核。方案结论（submodule 钉 ethan 分支、根目录只留应用、`AGENTS.md` 划界）不随版本变；但重建 V2 时钉的 commit 应换成含 upstream v2.2.0 的 ethan HEAD，并注意 `config_version` 已到 **63**（`config.example.yaml:23`）、`.env` 由 `DEER_FLOW_ENV_FILE` 选择（`deerflow/env.py:10`）、`.deer-flow/` 顶层 `memory.json` 与 `agents/` 现为 legacy 只读回退、skill 的 `allowed-tools` 不再限制工具（#6935）。详见 [answer.md](answer.md) 与 [migration-steps.md](migration-steps.md) 末尾的同步注记。
