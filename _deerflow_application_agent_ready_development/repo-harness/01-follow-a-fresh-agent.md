# 新 agent 的参与路径：指南网络

## 这页解决什么问题

一个从未来过的 coding agent（或开发者）进入 DeerFlow 仓库的第一小时读什么。答案是一张分层的 `AGENTS.md` 网络——DeerFlow 把"参与知识"放进仓库文件，而不是留在口头传统里。

## 机制（运行时事实，对 v2.2.0 核验）

**根指南只做定位**。根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md) 第一句即自述 "Guidance source; `CLAUDE.md` imports `@AGENTS.md`"，正文只承担地图职责：仓库地图、服务拓扑、跨模块约定（文档同步、TDD、格式、版本一致五源）、root 与 module 两级命令，深度一律下放给模块指南。（v2.1.0 里自称 "the monorepo orientation layer" 的那句、以及 "Where to Go Next" 节与 "root `make` = the full application; `backend/Makefile` = per-module work" 这条经验规则，在 v2.2.0 中已不再出现，**已删除**；对应内容由 "Commands: Root vs. Module" 与 "References" 两节承担。）同仓的 `CLAUDE.md` 只有一行 `@AGENTS.md` 导入——对读 AGENTS.md 的工具（Claude Code、Codex 等）而言，指南是跨工具共享的单一事实源。但"不为单个工具维护指南"并不成立：仓库另有一份 231 行的 Copilot 专属上手指南 [copilot-instructions.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/.github/copilot-instructions.md)（放在 `.github/` 下 Copilot 的约定位置），自称 "Use this file as the default operating guide for this repository. Follow it first"，其 Instruction Priority 节直接写 "Trust this onboarding guide first"——它与 AGENTS.md 网络是**两套并存、互不引用**的指南面，且优先级主张不同。

**深度按目录下放**。[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/AGENTS.md) 承接后端深度（harness/app 分层、中间件链、测试布局、迁移），更深的子系统各有自己的指南文件。解决"读哪份"的规则只有一句：

> Read the nearest scoped `AGENTS.md` for subsystem ownership.
>
> — [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/AGENTS.md)

（v2.1.0 的措辞是 "Follow the nearest file in the directory tree"；v2.2.0 收紧为上面这句，并把它放在 Configuration 一节末尾而非开头。）

**网络的规模（对 tag 核验）**。仓库共 57 个 `AGENTS.md` 指南：根 1、模块层 3（backend、frontend、scripts）、子系统层 53。子系统层在 v2.2.0 大幅扩张——harness 包根（`backend/packages/harness/deerflow/`）及其下的 agents、agents/memory、agents/middlewares、**agents/task_continuity**、extensions、mcp、models、sandbox、skills、subagents、tools、config、reflection、runtime、tracing、tui、utils、persistence/migrations、persistence/user、**persistence**、**storage**、**typesafe**、**uploads**，`community/` 下从 tavily 一份扩到 **12 份**（aio_sandbox、brave、ddg_search、e2b_sandbox、groundroute、image_search、infoquest、jina_ai、opensandbox、ragflow、serper、tavily），app 侧的 gateway、**gateway/routers**、channels，以及 **backend/tests**，frontend/src、**frontend/src/core/auth**、**frontend/src/core/memory**、**frontend/src/components/workspace/browser-view**、**frontend/tests/e2e**，以及 **6 个扩展示例的目录内指南**（`examples/deerflow-extension-{agent-teams,knowledge-management,knowledge-platform,lightrag,weknora,workflows}/AGENTS.md`）与 `skills/public/{data-analysis,video-generation}`；另有 `backend/docs/GITHUB_AGENTS.md` 与指南网络同名但**不是指南**——它是 GitHub 事件驱动 agent 的功能文档，正好演示了"文件名不是成员证"。（对 `git ls-tree -r v2.2.0 | grep 'AGENTS\.md$'` 计数得 58 个以 `AGENTS.md` 结尾的文件：57 个指南 + 1 个 `GITHUB_AGENTS.md`；v2.1.0 同法为 29 个：28 个指南 + 1 个同名文档。）

**入口按任务路由**。根指南的 "References" 节把任务映射到指南（后端 → backend 指南、前端 → frontend 指南、装与配置 → `Install.md`/`CONTRIBUTING.md`、发版 → `RELEASING.md`），"Repository Map" 的目录注释再把每个目录指到自己的指南。命令分两级写在 "Commands: Root vs. Module" 节：**Root stack commands** 驱动整个应用栈（`make dev`/`make start`/`make up`、`make extension-*` 等），**Module commands** 在单模块内执行（`cd backend && make test`、`cd frontend && pnpm check`）。

**给 agent 的操作语义**：进仓先读根指南拿地图；改某目录前读**离你最近的**那份指南；两份指南冲突时信更具体的那份、并以代码与测试为最终仲裁。

## 应用仓能借鉴什么

**可移用**：三层结构（定位层 / 模块层 / 子系统层）+ 最近文件规则 + 单一事实源（不为每个读 AGENTS.md 的工具复制指南）。这三个决定加起来，回答的是应用仓引入 coding agent 后最先出现的问题——"它进来读什么、信哪份"。**按规模裁剪**：小仓可以只有根指南一份；出现第二份时就值得写下"nearest file"规则。**应用仓建议**：如果你的应用仓有 AGENTS.md，把"指南与代码冲突时信代码"写明——这比指望指南永远不过期便宜得多，DeerFlow 自己也是这么做的。另外，DeerFlow 同时维护 AGENTS.md 网络与 Copilot 专属指南、两者互不引用且优先级主张不同——应用仓若出现第二个工具专属指南面，把"两套指南冲突时信谁"写成显式规则，别留成悬案。

## 证据入口

- 根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md)（首句自述、Repository Map、Commands: Root vs. Module、References）
- [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/AGENTS.md)（nearest-file 规则与后端深度）
- [.github/copilot-instructions.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/.github/copilot-instructions.md)（Copilot 专属指南面）；57 份指南 + 1 份 GITHUB_AGENTS 文档对 `git ls-tree -r v2.2.0 | grep 'AGENTS\.md$'` 核验
