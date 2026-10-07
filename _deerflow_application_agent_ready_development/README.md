# DeerFlow Application Agent-ready Development

本语料面向新建的独立 DeerFlow **应用仓**——以维护者与 coding agent 为读者——说明如何沿用 DeerFlow 的原生机制组织意图、事实源、实现、文档、测试证据与交付判断。目标不是复制 DeerFlow 主仓库的内部治理，而是让应用开发者复用其可验证的扩展、组合与验证方式，构建自己的 agent-ready 应用。

## 目标读者与适用边界

目标读者是在独立仓库中构建 DeerFlow 应用的维护者与 coding agent。"应用"取完整口径，覆盖四种接入形态：

1. **Python extension 包**——通过 `deerflow.extensions` 入口点贡献 middleware、生命周期观察者、Gateway 服务与路由；
2. **Skill**——`SKILL.md` 及其资源的能力模块，走发现/激活/审查机制；
3. **MCP server**——外部工具经 `extensions_config.json` 接入；
4. **内嵌 harness**——进程内直接使用 harness 能力（`create_deerflow_agent()` 或 `DeerFlowClient`）的应用。

读者应能从 DeerFlow 自带的应用文档（docs 站 harness 手册、extension 示例、extension-api 契约）找到可运行的最小入口，再逐步为自己的仓库建立源码、配置、测试预期、可重复验证与交付记录。

**适用边界**：应用仓可以采用 DeerFlow 的 extension 装载与事务、skill 发现与审查、配置组合、嵌入式 client 与契约测试模式。DeerFlow 主仓库的 SDLC 制度（spec/plan 纪律、CI 门禁矩阵、发版版本门、迁移链治理）属于主仓治理，不会因为使用 DeerFlow 就自动适用于应用仓。应用仓应为自己的公开接口、用户可见行为、升级兼容与发布方式确定权威归属与验证路径。

## 四类陈述

正文区分四类陈述，防止最常见的误读——把上游的内部治理当成随依赖继承的义务：

- **运行时事实**：DeerFlow v2.1.0 的接口、实际行为与仓库内容（文档、指南、workflow 等可对钉定 tag 核验的事实）；
- **主仓要求**：DeerFlow 主仓库自身的贡献、测试与发布规则，仅约束向主仓提交的变更；
- **应用仓建议**：本语料归纳出的开发做法，不是 DeerFlow 官方规定；
- **仓库自定**：应用仓自己的组织、审批与发布选择。

## 独立使用与发行

复制本目录的全部内容并保留相对目录结构，即可独立阅读和验证；不需要宿主仓库的研究笔记或本次会话。跨卷链接供深入查阅，不构成前置顺序。核对一手事实需要访问钉定版本的 DeerFlow 来源；离线核对可另备该版本的 checkout。

## 三卷入口

三卷按下列顺序编号（卷一/卷二/卷三），正文跨卷引用一律用这套卷号：

| 卷 | 路径 | 应用仓读者的问题 | 使用方式 |
|---|---|---|---|
| 卷一 | [应用开发模型](./application-development-model/README.md) | 新建独立应用仓后如何起步，并组织一次完整的应用变更？ | 先看总览页，再按问题深入 |
| 卷二 | [SDLC Reference（流程参考）](./sdlc-reference/README.md) | DeerFlow 主仓的具体条件、状态和例外是什么？哪些机制可移用于应用仓？ | 按问题查阅，并遵守适用边界 |
| 卷三 | [Development Harness（开发 Harness）](./repo-harness/README.md) | DeerFlow 仓库怎样让 agent 定位知识、扩展点和验证方式？应用仓能借鉴什么？ | 按参与任务查阅 |

三卷各有 README 与入口页，只依赖 DeerFlow 一手来源，彼此不构成前置阅读顺序。

## DeerFlow 在这里扮演什么角色，理解从哪里来

本语料对 DeerFlow 的全部理解都只从 GitHub 仓库 `bytedance/deer-flow` 的固定 release tag `v2.1.0` 挖出：源码、`AGENTS.md` 指南、docs 站 harness 手册、extension-api 契约、示例扩展、CI workflows、测试与 git 历史。语料不使用任何二手转述；宿主仓库的研究笔记不参与本语料的证据链。

结论在正文里讲清楚，关键规则以 Markdown blockquote 摘录仓库原文，并给出钉定 tag 的可核对链接。仓库没有声明的制度（例如它从未宣布一套面向下游应用仓的开发方法论）一律表述为"可观察机制的综合"，而不是官方方法名。钉定基线、证据范围与重审触发由[维护页](_coverage/00-corpus-maintenance.md)拥有。

## 目录：每个子目录为什么存在，什么时候改它

| 路径 | 为什么要有它 | 什么时候需要改它 |
|---|---|---|
| [application-development-model/](./application-development-model/README.md) | 从新仓起步开始，说明独立应用仓怎样组合 DeerFlow 的事实源、证据与交付判断 | DeerFlow 的接入形态、事实归属或测试层变化时复核 |
| [sdlc-reference/](./sdlc-reference/README.md) | 查阅 DeerFlow 主仓的精确条件、状态与例外，并判断哪些机制适用于应用仓 | 任何一手事实变化（workflows、PR 模板、发布、迁移制度）按维护页的重审触发改对应页 |
| [repo-harness/](./repo-harness/README.md) | 查找 DeerFlow 的知识入口、文档阶梯、示例与契约面，选择应用仓实际需要的部分 | 仓库机制清单变化时改（AGENTS.md 增减、docs 站结构、示例扩展、contracts 面变化） |
| [_coverage/](_coverage/README.md) | 语料的可信度取决于证据范围与复核记录：钉了哪个版本、哪些来源核过、上游什么变化触发重审、历轮改了什么 | 每轮挖取/re-pin 都必须留一条带日期的记录 |
| [verify.mjs](./verify.mjs) | 语料的结构规则（严格 UTF-8、结尾换行、相对链接与锚点、钉版外链、目录 README、SVG 规范）用可执行脚本强制，不靠人记 | 只在结构规则本身变化时改；同步更新自测负例 |
| [verify.test.mjs](./verify.test.mjs) | 在临时复制的完整语料中，通过真实 verifier 入口测试接受和拒绝条件 | 修改引用政策、隔离或链接约束时更新对应负例 |

## 验证

修改本目录后，使用支持 ESM 与 Unicode 正则的 Node.js（本轮使用 Node 22）运行。位于本目录时：

```sh
node verify.mjs
```

位于宿主仓库根目录时：

```sh
node _deerflow_application_agent_ready_development/verify.mjs
```

脚本仅用 Node 内置模块，不依赖包管理器、宿主脚本、Git 或网络；它按自身文件位置定位语料，不按当前工作目录猜路径。该命令检查严格 UTF-8、单个结尾换行、Markdown 相对链接和锚点、目录 README、固定 DeerFlow 外链，以及 SVG 的固有尺寸与无障碍元数据。它不核对远端来源内容、不证明语义准确，也不替代图示视觉检查。

修改验证规则后，在本目录运行 `node verify.test.mjs`：测试将完整语料复制到独立临时目录，确认有效副本通过，且非钉版外链、失效锚点、越界链接、缺失结尾换行与 SVG 缺无障碍标题被真实入口拒绝。证据复核记录见[维护页](_coverage/00-corpus-maintenance.md)。
