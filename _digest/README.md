# DeerFlow 源码研究笔记

> **核心规则：绝不碰源代码。本目录 `_digest/` 是唯一可以修改的地方。**

## 为什么不碰源代码

1. 本项目是 [bytedance/deer-flow](https://github.com/bytedance/deer-flow) 的 fork，`main` 分支的唯一职责是**跟踪上游**
2. 上游更新频繁，`main` 必须保持干净才能无冲突地 `git pull`
3. 所有研究笔记、个人理解、集成实验记录都在 `_digest/` 下，在 `ethan` 分支上独立演进
4. `ethan` 分支永远不会 merge 回 `main`，它只是一个研究工作台

**`main` = 上游镜像，`ethan` + `_digest/` = 学习空间。**

## 研究维度

| 维度 | 回答的问题 | 状态 |
|------|-----------|------|
| **Architecture** | 内部怎么设计的？核是什么，外围怎么挂？ | 7 篇 + 8 图 |
| **Integration** | 怎么接入使用？API / SDK / Docker / IM？ | 8 篇 |
| **Configuration** | 怎么挂自定义东西上去？MCP / Skills / Tools？ | 待开始 |
| **Security** | 一段 prompt 到 `rm -rf /` 之间有多少层防护？ | 待开始 |
| **Model Layer** | 怎么做到换模型不改代码的？thinking/vision 怎么统一？ | 待开始 |

## 目录结构

```
_digest/
├── README.md             # 本文件
├── architecture/         # 内部设计：Agent Loop、Middleware、Sandbox、Subagent、Memory...
├── integration/          # 接入指南：Quick Start、Config、API、SDK、Docker、IM Channels
├── configuration/        # 配置与扩展：Config System、MCP、Skills、Custom Tools/Agents
├── security/             # 安全边界：Auth、Sandbox Isolation、Guardrail、Trust Boundary
└── model-layer/          # LLM 抽象：Model Factory、Thinking/Vision、Streaming
```

## 工作流

- 切到 `ethan` 分支工作：`git checkout ethan`
- 研究过程中发现值得记录的内容 → 写入 `_digest/` 对应目录
- 定期回到 `main` 拉上游：`git checkout main && git pull upstream main`
- 需要时把上游的新变更 merge 到 `ethan`：`git checkout ethan && git merge main`

## 待追踪

- 上游每次大版本更新的关键 diff
- 值得关注的上游 issue/PR

## 上游信息

- 仓库：https://github.com/bytedance/deer-flow
- 协议：MIT
- 技术栈：Python 3.12+ / Node.js 22+ / LangGraph / Next.js 16
