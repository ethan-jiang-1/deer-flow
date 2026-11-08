# 应用手册与架构文档：两级文档阶梯

## 这页解决什么问题

应用开发者（人）在 DeerFlow 仓库里现成的官方入门路径：从零跑到按主题深入。这张阶梯是 v2.2.0 对应用面最完整的官方文档，接入形态各有自己的专题入口页（extension → `extensions/`、子代理 → `subagents/`、检查点 → `checkpoints/`）；仓库内另有一层面向贡献者与运维的架构与工程文档，本页一并盘点。

## 阶梯结构（运行时事实，对 v2.2.0 树核验）

docs 站 harness 节（`frontend/src/content/en/harness/`，中文镜像在 `zh/harness/`，两套同结构维护）分三层：平铺 14 个 `.mdx`（另有 `_meta.ts` 导航配置），加三个专题子目录 `extensions/`（11 个主题页）、`subagents/`（11 个主题页）、`checkpoints/`（10 个主题页）。

**第一层：起步与总览**

| 页 | 回答 |
|---|---|
| [index](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/index.mdx) / [design-principles](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/design-principles.mdx) | harness 是什么、设计原则 |
| [quick-start](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/quick-start.mdx) | "最快的理解路径"：跑通第一个 agent（`create_deerflow_agent`） |
| [integration-guide](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/integration-guide.mdx) | 把 harness 作为库嵌进你的系统（`DeerFlowClient`、FastAPI、LangGraph 组合） |

**第二层：按主题**——[lead-agent](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/lead-agent.mdx)、[middlewares](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/middlewares.mdx)、[customization](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/customization.mdx)、[skills](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/skills.mdx)、[mcp](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/mcp.mdx)、[tools](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/tools.mdx)、[sandbox](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/sandbox.mdx)、[memory](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/memory.mdx)、[configuration](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/configuration.mdx)。

**第三层：按接入形态的专题手册**——三个子目录：

| 子目录 | 页数与主题页 |
|---|---|
| `extensions/` | 11 个主题页：index、quick-start、middleware、observers、runtime、services-and-routes、run-evidence、operations、troubleshooting、reference，以及 v2.2.0 新增的 **plugins**（实验性全栈插件面） |
| `subagents/` | 11 个主题页：index、quick-start、delegation、catalog、developers、results、limits、sandbox、observability、reference、troubleshooting |
| `checkpoints/` | 10 个主题页（**v2.2.0 新增**）：index、quick-start、modes、cadence、history-cache、resume-and-rollback、operations、observability、reference、troubleshooting |

（`extensions/` 在 v2.1.0 是 10 个主题页——没有 `plugins.mdx`；`checkpoints/` 整个子目录在 v2.1.0 不存在，是本版新增的会话检查点/恢复手册。）

**双语**：en 与 zh 两套镜像同结构维护。**边界**：手册描述的是发布时的行为快照；它与代码的一致性靠主仓自己的文档纪律维持（见[指南预算与文档测试](./02-guidance-budgets-and-doc-tests.md)），不是独立保证——卷一的 integration-guide 快照警示（示例与源码三处不符）在 v2.2.0 仍未修正，就是这条边界的具体实例。

## 仓库内的架构与工程文档层（对 tag 核验）

docs 站手册之外，仓库还有一层面向贡献者与运维的文档：

**顶层架构总览**。[docs/ARCHITECTURE.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/docs/ARCHITECTURE.md) 自称 "the top-level architecture overview"：What DeerFlow Is（super-agent harness 定位与 2.0 重写背景）、Service Topology、Backend: Harness/App Split、Agent runtime path、Cross-Cutting Subsystems、Security & Isolation Model，逐节指向模块指南——比根 AGENTS.md 更面向"通读"的架构入口。

**backend/docs 工程文档层**。48 个文件、全在顶层（含一份 JSON 样例 `memory-settings-sample.json`；v2.1.0 为 40 个），按功能大致六类：设计与 RFC（三份 `rfc-*.md`、`AUTH_DESIGN.md`、`MEMORY_IMPROVEMENTS*.md`、v2.2.0 新增 `MEMORY_COGNITIVE_STYLE.md`）；运行时行为（`STREAMING.md`、`RUN_EVENT_STREAM.md`、`THREAD_LIFECYCLE.md`、`middleware-execution-flow.md`、v2.2.0 新增 `RUN_INTERACTION_POLICY.md`、`runtime-guidance-details.md`）；门禁配套（`BLOCKING_IO_DETECTION.md`、`REPLAY_E2E.md`——见[卷二·CI 门禁](../sdlc-reference/05-ci-gates.md)）；契约（`checkpoint-retention-contract.md`、v2.2.0 新增 `blob-storage.md`、`KNOWLEDGE.md`、`mcp-control-leases.md`）；扩展面设计（v2.2.0 新增 `extension-agent-runs.md`、`extension-model-invocation.md`）；部署运维（`SETUP.md`、`SSO.md`、`IM_CHANNEL_CONNECTIONS.md`、`GITHUB_AGENTS.md`）。[配置与检查面](./05-config-and-inspection.md)引用的 CONFIGURATION.md 与 GUARDRAILS.md 也在这一层。

**docs/ 的其他设计文档**。`docs/` 顶层在 v2.2.0 也扩容（`docs/plans/` 13 个、`docs/superpowers/` 25 个、`docs/experiments/` 51 个，另有 `docs/agents/`、`docs/tui/`、`docs/images/`）：与扩展面直接相关的有 `full-stack-plugins.md`（全栈插件设计）、`capability-center.md`（能力中心入口）、`task-continuity.md`、`skill-evolution-host.md`、`skill-usage-ui.md`、`RELEASE_SOP.md`；v2.1.0 存在的 `docs/pr-evidence/` 在 v2.2.0 不再存在。

**两层的分工**（应用仓建议层的归纳）：docs 站手册面向应用开发者（怎么用），架构与工程文档面向贡献者与运维（怎么改、怎么查）。应用仓借鉴时同样值得分两层：对外手册按接入形态分册（见上），对内文档按"设计/行为/门禁/契约/运维"归类。

## 应用仓怎么用

**按形态选入口**：内嵌 → quick-start → integration-guide；extension → extensions/quick-start 起步、reference 查契约；skill → skills 手册；MCP → mcp 手册 + CONFIGURATION。**应用仓建议**：这张阶梯的**结构**值得抄——"起步一页 → 主题分层 → 每种接入形态一本专题手册"，且起步页的写法是"the fastest way to understand"——model setup、agent creation、streaming a response 三步走完就有东西在跑。你的应用仓对外文档如果有多种接入方式，为每种形态给一本专题手册比一份大而全的文档好维护得多。

## 证据入口

`frontend/src/content/en/harness/` 与 `frontend/src/content/zh/harness/` 目录树（v2.2.0，`git ls-tree` 核验）；上列各页与 [extensions/plugins](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/extensions/plugins.mdx)、[checkpoints/index](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/checkpoints/index.mdx)。架构与工程文档层：[docs/ARCHITECTURE.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/docs/ARCHITECTURE.md)、[docs/full-stack-plugins.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/docs/full-stack-plugins.md) 与 backend/docs 目录清单（v2.2.0，48 文件 `git ls-tree` 核验）。
