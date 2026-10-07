# 术语表

## 这页解决什么问题

卷内其他页用 DeerFlow 的原生词汇组织内容。第一次遇到某个词时来这里查：一句话定义、出处与**常见误读**。所有定义对 v2.1.0 核验；标"应用仓建议"的条目是本语料的归纳，不是 DeerFlow 官方术语规定。

## 分层与依赖

**harness** — 可发布的 agent 框架包（`backend/packages/harness/`，import 前缀 `deerflow.*`）：agent 编排、工具、沙箱、模型、MCP、技能、配置——构建和运行 agent 所需的一切（[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)）。误读：把 harness 当作"必须连 Gateway 一起部署的应用"。harness 可独立嵌入。

**app（应用层）** — 不发布的仓库代码（import 前缀 `app.*`）：FastAPI Gateway 与 IM 渠道集成。依赖方向单向：app import deerflow，反向被 CI 中的 AST 边界测试禁止（[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)）。误读：以为扩展可以 import `app.*` 借用 Gateway 内部——那是不承诺兼容的宿主内部。

**extension-api（公共契约包）** — `backend/packages/extension-api/`，import 前缀 `deerflow_extension_api.*`，刻意**零框架依赖**；扩展自己声明用到的 FastAPI/LangChain/LangGraph（[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）。误读：以为装了契约包就间接有了框架依赖——没有，漏声明会在装包时暴露。

**Gateway** — 承载运行时的 FastAPI 应用（默认 8001 端口），前面有 nginx 统一入口。扩展的装载发生在 Gateway 构建应用时。

## 执行模型

**lead agent** — 主 agent：模型、工具与中间件构成的 LangGraph 执行循环，由 factory 组装（[lead-agent 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/lead-agent.mdx)）。误读：把它当作固定业务流程图——路由决策在模型侧，运行边界在中间件与配置侧。

**middleware（中间件）** — 包裹模型调用/工具调用的组合单元。扩展贡献的中间件声明 lead/subagent 作用域、稳定顺序与**语义 placement**（`MODEL_LOGICAL`、`MODEL_PHYSICAL`、`TOOL_VISIBLE`、`TOOL_RAW`、`STANDARD`），而不是脆弱的列表下标（[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）。误读：靠"插到第 N 个位置"控制顺序——顺序由 placement 约束在组装点解析。

**thread / thread state** — 会话及其持久状态；`thread_id` 是隔离单位，配 checkpointer 后跨轮保留历史（[integration-guide](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/integration-guide.mdx)）。误读：checkpoint 持久化等于业务完成——它只保存对话状态。

**subagent** — 经委派启动的子 agent，默认隔离执行；委派由 lead 的决策触发，不是复杂度的自动后果。

**sandbox** — 工具执行（bash、文件操作等）的受控执行环境；provider 可配置（[sandbox 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/sandbox.mdx)）。误读：把沙箱边界当成扩展代码的边界——扩展代码以 **Gateway 权限**执行，不在沙箱里。

## 能力面

**skill** — 自包含能力包：结构化指令、工作流、领域实践、资源与工具配置；`SKILL.md` 是权威定义，按需加载、不占常驻上下文（[skills 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/skills.mdx)）。误读：skill 是工具——skill 教 agent **怎么做**，工具才**实际执行**。

**MCP server** — 经 `extensions_config.json` 的 `mcpServers` 接入的外部工具服务；`routing` 字段提供软性偏好提示，不构成硬性强制（[CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/docs/CONFIGURATION.md)）。

**工具四分类** — DeerFlow 把工具分为四类：**内置工具**（built-in，harness 自带的核心运行时能力，如 `task` 委派、`present_files`、`view_image`，无需配置即可用）、**community 工具**（外部搜索/抓取/图像服务的集成，如 web search、web fetch、渲染截屏，经 `config.yaml` 的 `tools:` 配置）、**MCP 工具**（外部 MCP server 提供）、**skill 自带工具**（随技能包捆绑）（[tools 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/tools.mdx)）。另有沙箱文件工具（`ls`/`read_file`/`grep`/`bash` 等）需配置并激活沙箱。误读：把 web search/fetch 当"内置"——它们是 community 工具，要经 `config.yaml` 配置才可用。

## 装载与配置

**`plugins:` 条目** — `config.yaml` 顶层、**startup-only** 的扩展装载清单：每次变更（install/enable/disable/remove/手改）都要重启 Gateway 才生效；刻意放在 operator 控制的文件里，不放进 API 可写的 `extensions_config.json`（[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）。误读：**enabled ≠ loaded**——启用状态变了，运行中的进程没变。

**入口点（entry point）** — 托管包恰好一个 PEP 621 入口点，位于 `deerflow.extensions` 组，形如 `example = "deerflow_extension_example:install"`；入口点名是 operator 面向的稳定名（[示例 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md)）。

**贡献类型（contribution kinds）** — 注册契约（registry contract）暴露**七种**：middleware、task-lifecycle、system-model-call 观察、agent-assembly 观察、context-compaction 观察、Gateway-lifetime 服务、eager 路由（[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）；示例包演示其中五种（[示例 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md)）。误读：从示例的五种推断契约只有五种。

**`config.yaml` 与 `extensions_config.json`** — 前者是 operator 控制的主配置（含 `plugins:`）；后者是运行时可写的 MCP server 与技能启用状态，两者刻意分离（[CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/docs/CONFIGURATION.md)）。`config_version` 追踪 schema 变化，旧配置启动时得到升级指引而非静默失效。

**技能归档安装** — Gateway 的运行时技能安装面：`POST /api/skills/install` 从线程产物里的 `.skill` 归档安装，admin-only 的 `POST /api/skills/install/upload` 接受 multipart 上传；装入前过安全扫描，声明的依赖首次加载时安装（[Gateway 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/app/gateway/AGENTS.md)、[skills 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/skills.mdx)）。误读：把它当成 extension manager 事务——技能安装不动 `plugins:`、不改依赖组与 `uv.lock`、无需重启。

## 验证词汇

**包级测试（package tests）** — 只用公共契约加包自身声明的依赖、不 import harness 与 Gateway 的测试——示例包的标准口径（[示例 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md)）。**应用仓建议**：包级测试证明契约用法正确，不证明宿主组合成立；后者要装进真实 checkout 重启后观察。

**安装验证（install verification）** — 三层证据的第二层：经 extension manager 装入真实 checkout（快照 → 依赖组 → lock → `plugins:` 条目）、重启 Gateway、确认扩展出现在列表。它证明分发物可安装、装载链成立，**不证明**贡献产生了预期行为——那是第三层"宿主侧行为观察"的事（示例的做法是贡献路由后 curl 它），两层共同构成 extension 形态的最低真实证据。

**ruff** — Python lint/format 工具，示例包自带配置；主仓 CI 强制格式检查（详见 [SDLC Reference](../sdlc-reference/00-index.md)）。

## 读法提醒

这些词的关系比定义更重要：**harness/app 是依赖方向，placement 是顺序语义，skill/tool 是"教"与"做"，`plugins:` 是装载边界，包测试/安装验证/宿主侧观察是三层证据。**把它们混着用，后面的闭环就会在错误的地方找证据。
