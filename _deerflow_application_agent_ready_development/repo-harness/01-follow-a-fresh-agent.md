# 新 agent 的参与路径：指南网络

## 这页解决什么问题

一个从未来过的 coding agent（或开发者）进入 DeerFlow 仓库的第一小时读什么。答案是一张分层的 `AGENTS.md` 网络——DeerFlow 把"参与知识"做成仓库资产，而不是口头传统。

## 机制（运行时事实，对 v2.1.0 核验）

**根指南只做定位**。根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md) 自称 "the monorepo orientation layer"：仓库地图、服务拓扑、跨模块约定（文档同步、TDD、格式、版本一致），深度一律下放给模块指南。同仓的 `CLAUDE.md` 只有一行 `@AGENTS.md` 导入——指南是跨 agent 共享的单一事实源，不为某个工具单独维护。

**深度按目录下放**。[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md) 承接后端深度（harness/app 分层、中间件链、测试布局、迁移），更深的子系统各有自己的指南文件。解决"读哪份"的规则只有一句：

> More specific `AGENTS.md` files in backend code directories contain the subsystem sections split from this file. Follow the nearest file in the directory tree.
>
> — [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)

**入口按任务路由**。根指南的 "Where to Go Next" 节把任务映射到指南：后端工作 → backend 指南；前端 → frontend 指南；发版 → RELEASING。命令也分两级：根 `make` 驱动整个应用栈，模块内命令驱动单模块——"root `make` = the full application; `backend/Makefile` = per-module work"。

**给 agent 的操作语义**：进仓先读根指南拿地图；改某目录前读**离你最近的**那份指南；两份指南冲突时信更具体的那份、并以代码与测试为最终仲裁。

## 应用仓能借鉴什么

**可移用**：三层结构（定位层 / 模块层 / 子系统层）+ 最近文件规则 + 单一事实源（不按工具复制指南）。这三个决定加起来，回答的是应用仓引入 coding agent 后最先出现的问题——"它进来读什么、信哪份"。**按规模裁剪**：小仓可以只有根指南一份；出现第二份时就值得写下"nearest file"规则。**应用仓建议**：如果你的应用仓有 AGENTS.md，把"指南与代码冲突时信代码"写明——这比指望指南永远不过期便宜得多，DeerFlow 自己也是这么做的。

## 证据入口

- 根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)（orientation layer 定位、命令分级、Where to Go Next）
- [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)（nearest-file 规则与后端深度）
