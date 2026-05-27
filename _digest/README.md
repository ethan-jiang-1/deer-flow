# DeerFlow 源码研究笔记

> **核心规则：绝不碰源代码。本目录 `_digest/` 是唯一可以修改的地方。**

## 为什么不碰源代码

1. 本项目是 [bytedance/deer-flow](https://github.com/bytedance/deer-flow) 的 fork，`main` 分支的唯一职责是**跟踪上游**
2. 上游更新频繁（每周数十个 commit），`main` 必须保持干净才能无冲突地 `git pull`
3. 所有研究笔记、个人理解、集成实验记录都在 `_digest/` 下，在 `ethan` 分支上独立演进
4. `ethan` 分支永远不会 merge 回 `main`，它只是一个研究工作台

简而言之：**`main` = 上游镜像，`ethan` + `_digest/` = 学习空间。**

## 研究优先级

1. **Integration（集成）** — 如何接入 DeerFlow，如何在我的应用中使用它
2. **Architecture（架构）** — 内部设计、数据流、核心抽象
3. **Modules（模块）** — 各子系统的实现细节
4. **Notes（笔记）** — 零散发现、待深入的点

## 目录结构

```
_digest/
  README.md          # 本文件 — 规则、说明、研究策略
  integration/       # 集成指南：配置、启动、API、SDK、部署
  architecture/      # 架构分析：分层、数据流、Middleware、核心抽象
  modules/           # 模块深挖：逐个包/模块的源码阅读笔记
  notes/             # 零散笔记、TODO、待追踪的上游变更
```

## 工作流

- 切到 `ethan` 分支工作：`git checkout ethan`
- 研究过程中发现值得记录的内容 -> 写入 `_digest/` 对应目录
- 定期回到 `main` 拉上游：`git checkout main && git pull upstream main`
- 需要时把上游的新变更 merge 到 `ethan`：`git checkout ethan && git merge main`

## 上游信息

- 仓库：https://github.com/bytedance/deer-flow
- 协议：MIT
- 技术栈：Python 3.12+ / Node.js 22+ / LangGraph / Next.js 16
