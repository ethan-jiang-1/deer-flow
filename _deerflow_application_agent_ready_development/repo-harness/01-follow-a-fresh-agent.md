# 新 agent 的参与路径：指南网络

## 这页解决什么问题

一个从未来过的 coding agent（或开发者）进入 DeerFlow 仓库的第一小时读什么。答案是一张分层的 `AGENTS.md` 网络——DeerFlow 把"参与知识"放进仓库文件，而不是留在口头传统里。

## 机制（运行时事实，对 v2.1.0 核验）

**根指南只做定位**。根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md) 自称 "the monorepo orientation layer"：仓库地图、服务拓扑、跨模块约定（文档同步、TDD、格式、版本一致），深度一律下放给模块指南。同仓的 `CLAUDE.md` 只有一行 `@AGENTS.md` 导入——对读 AGENTS.md 的工具（Claude Code、Codex 等）而言，指南是跨工具共享的单一事实源。但"不为单个工具维护指南"并不成立：仓库另有一份 213 行的 Copilot 专属上手指南 [copilot-instructions.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/copilot-instructions.md)（放在 `.github/` 下 Copilot 的约定位置），自称 "Use this file as the default operating guide for this repository. Follow it first"，其 Instruction Priority 节直接写 "Trust this onboarding guide first"——它与 AGENTS.md 网络是**两套并存、互不引用**的指南面，且优先级主张不同。

**深度按目录下放**。[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md) 承接后端深度（harness/app 分层、中间件链、测试布局、迁移），更深的子系统各有自己的指南文件。解决"读哪份"的规则只有一句：

> More specific `AGENTS.md` files in backend code directories contain the subsystem sections split from this file. Follow the nearest file in the directory tree.
>
> — [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)

**网络的规模（对 tag 核验）**。仓库共 29 个名为 `AGENTS.md` 的文件：根 1、模块层 3（backend、frontend、scripts）、子系统层 24——harness 包根（`backend/packages/harness/deerflow/`）及其下的 agents、agents/memory、agents/middlewares、extensions、mcp、models、sandbox、skills、subagents、tools、config、reflection、runtime、tracing、tui、utils、community/tavily、persistence/migrations、persistence/user，app 侧的 gateway、channels，另 frontend/src 与 backend/tests；第 29 个 `backend/docs/GITHUB_AGENTS.md` 与指南网络同名但**不是指南**——它是 GitHub 事件驱动 agent 的功能文档，正好演示了"文件名不是成员证"。

**入口按任务路由**。根指南的 "Where to Go Next" 节把任务映射到指南：后端工作 → backend 指南；前端 → frontend 指南；发版 → RELEASING。命令也分两级：根 `make` 驱动整个应用栈，模块内命令驱动单模块——"root `make` = the full application; `backend/Makefile` = per-module work"。

**给 agent 的操作语义**：进仓先读根指南拿地图；改某目录前读**离你最近的**那份指南；两份指南冲突时信更具体的那份、并以代码与测试为最终仲裁。

## 应用仓能借鉴什么

**可移用**：三层结构（定位层 / 模块层 / 子系统层）+ 最近文件规则 + 单一事实源（不为每个读 AGENTS.md 的工具复制指南）。这三个决定加起来，回答的是应用仓引入 coding agent 后最先出现的问题——"它进来读什么、信哪份"。**按规模裁剪**：小仓可以只有根指南一份；出现第二份时就值得写下"nearest file"规则。**应用仓建议**：如果你的应用仓有 AGENTS.md，把"指南与代码冲突时信代码"写明——这比指望指南永远不过期便宜得多，DeerFlow 自己也是这么做的。另外，DeerFlow 同时维护 AGENTS.md 网络与 Copilot 专属指南、两者互不引用且优先级主张不同——应用仓若出现第二个工具专属指南面，把"两套指南冲突时信谁"写成显式规则，别留成悬案。

## 证据入口

- 根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)（orientation layer 定位、命令分级、Where to Go Next）
- [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)（nearest-file 规则与后端深度）
- [.github/copilot-instructions.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/copilot-instructions.md)（Copilot 专属指南面）；29 文件清单对 `git ls-tree -r v2.1.0 | grep AGENTS.md` 核验
