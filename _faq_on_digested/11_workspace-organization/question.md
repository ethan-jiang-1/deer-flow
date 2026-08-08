---
title: "怎么组织基于 deer-flow 的开发工作区？"
question: "我的 deep_research_harness 跑在 deer-flow 里面，强依赖 deer-flow 的运行时，仓库离开它跑不起来。但根目录放了大量不是我重点关心的框架代码，Coding Agent（Claude Code 等）一进来就被这些文件淹没、容易迷糊，不知道我的重点在哪。我想重新整理出一个全新的干净 repo，把 deer-flow 囊括进来（submodule 或其他形式），同时让 agent 一眼锁定重点。怎么做？"
topics: [workflow, repo-layout, git, submodule, workspace, coding-agent]
---

# 怎么组织基于 deer-flow 的开发工作区？

我的 `deep_research_harness` 跑在 deer-flow 里面，强依赖它的运行时，仓库离开它跑不起来。但根目录放了大量不是我重点关心的框架代码，Coding Agent 一进来就被淹没、容易迷糊。我想重新整理出一个全新的干净 repo，把 deer-flow 囊括进来（submodule 或其他形式），同时让 agent 一眼锁定重点。怎么做？
