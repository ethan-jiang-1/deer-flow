# docs 站应用手册阶梯

## 这页解决什么问题

应用开发者（人）在 DeerFlow 仓库里现成的官方入门路径：从零跑到按主题深入。这张阶梯是 v2.1.0 对应用面最完整的官方文档，四种接入形态各有自己的入口页。

## 阶梯结构（运行时事实，对 v2.1.0 树核验）

docs 站 harness 节（`frontend/src/content/en/harness/`，中文镜像在 `zh/harness/`）分三层：

**第一层：起步与总览**

| 页 | 回答 |
|---|---|
| [index](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/index.mdx) / [design-principles](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/design-principles.mdx) | harness 是什么、设计原则 |
| [quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/quick-start.mdx) | 十分钟跑通第一个 agent（`create_deerflow_agent`） |
| [integration-guide](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/integration-guide.mdx) | 把 harness 作为库嵌进你的系统（`DeerFlowClient`、FastAPI、LangGraph 组合） |

**第二层：按主题**——[lead-agent](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/lead-agent.mdx)、[middlewares](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/middlewares.mdx)、[customization](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/customization.mdx)、[skills](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/skills.mdx)、[mcp](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/mcp.mdx)、[tools](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/tools.mdx)、[sandbox](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/sandbox.mdx)、[memory](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/memory.mdx)、[configuration](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/configuration.mdx)。

**第三层：按接入形态的专题手册**——`extensions/` 九页（quick-start、middleware、observers、runtime、services-and-routes、run-evidence、operations、troubleshooting、reference）与 `subagents/` 十一页（quick-start、delegation、catalog、developers、limits、observability、results、sandbox、troubleshooting、reference）。

**双语**：en 与 zh 两套镜像同结构维护。**边界**：手册描述的是发布时的行为快照；它与代码的一致性靠主仓自己的文档纪律维持（见[指南预算与文档测试](./02-guidance-budgets-and-doc-tests.md)），不是独立保证。

## 应用仓怎么用

**按形态选入口**：内嵌 → quick-start → integration-guide；extension → extensions/quick-start 起步、reference 查契约；skill → skills 手册；MCP → mcp 手册 + CONFIGURATION。**应用仓建议**：这张阶梯的**结构**值得抄——"起步一页 → 主题分层 → 每种接入形态一本专题手册"，且起步页的判据是"读者十分钟后有东西在跑"。你的应用仓对外文档如果有多种接入方式，为每种形态给一本专题手册比一份大而全的文档好维护得多。

## 证据入口

`frontend/src/content/en/harness/` 与 `frontend/src/content/zh/harness/` 目录树（v2.1.0，`git ls-tree` 核验）；上列各页。
