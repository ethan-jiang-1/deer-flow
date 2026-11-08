# 示例扩展与公共契约

## 这页解决什么问题

应用开发者能对照抄的两类"可执行样板"：一组完整跑得通的示例包，和一套机器可读的公共契约。它们合起来回答"扩展到底能依赖什么"。

## 机制（运行时事实，对 v2.2.0 树核验）

**示例包：从最小骨架到全栈插件**。v2.2.0 的 `examples/` 从 1 个示例扩到 **14 个**独立 Python 包（每个都有自己的 `pyproject.toml`、README 与 `tests/`，入口页是 [examples/README.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/examples/README.md)）。按用途分四组：

| 组 | 示例 | 演示什么 |
|---|---|---|
| 起点 | [deerflow-extension-example](https://github.com/bytedance/deer-flow/blob/v2.2.0/examples/deerflow-extension-example/README.md) | 自述 "compact" 的后端骨架，覆盖五种贡献（中间件计数、task 生命周期归并、system-model 观察、Gateway 服务、eager 路由） |
| 全栈插件（实验面） | bookmarks、agent-teams | bookmarks 演示浏览器页面 + 会话动作 + 后端动作 + 打包资源 + 模型工具；agent-teams 演示 full Agent 编排 |
| 知识提供者（v2.2.0 新增贡献面） | knowledge、knowledge-management、knowledge-platform、lightrag、weknora | 只读知识提供者：离线合成样例、provider-owned 摄取、平台连接与分层知识空间策略、LightRAG / WeKnora 检索 |
| 策略与流程 | jev-classify、jev-context、jev-screening、report-sections、retrieval、workflows | Jev 分类 / 上下文剪枝 / 抓取内容筛查（risk gate 的三个消费面）、分段长报告、插件工具产物检索样例、受约束的 AgentRuns 脚本编排 |

`deerflow-extension-example` 示范的三件事在其余示例里同样成立：契约级包测试怎么写（只用公共契约加自身依赖，不 import harness 与 Gateway）、安装事务长什么样（快照 → 依赖组 → lock → `plugins:` 条目 → 重启）、以及**分发自包含**（Docker 构建包含本地快照，生产容器不在网络上解析依赖）。

**示例的打包检查**。v2.2.0 新增 [scripts/check_extension.py](https://github.com/bytedance/deer-flow/blob/v2.2.0/scripts/check_extension.py)：在临时目录构建 wheel，检查恰好一个 `deerflow.extensions` 入口点、打包的 Python 模块语法、依赖区间是否接受当前 checkout 的契约版本，并用与 Gateway 相同的校验器验证 `ui_manifest.json`（含"清单没进 wheel"的 flat 与 `src/` 布局漏包检测）。自定义清单文件名要用 wheel 相对路径显式指定（`--manifest`）。**它刻意不 import 扩展、不调用 `install()`、不装扩展、不改部署配置**——注册与 `@extension` 版本标记要等加载插件时才校验，所以通过打包检查后仍必须跑包测试并在装好的实例上验证。

**extension-api：零依赖的公共契约包**。[backend/packages/extension-api/](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/packages/extension-api/deerflow_extension_api/contracts.py) 按模块分面（v2.2.0 目录共 19 个文件——`__init__.py` + 17 个主题模块 + `py.typed`（18 个 `.py` 可 import，`py.typed` 是类型标记）；v2.1.0 目录为 12 个文件）：`contracts`（注册与贡献类型）、`placement`（语义位置）、`assembly`（组装描述）、`auth`（principal 解析）、`provenance`（消息生产者声明）、`release` / `state` / `compaction` / `run_evidence` / `runtime_bridge`，以及 v2.2.0 新增的 `agent_runs`（AgentRun 生命周期与 `ExecutionFence`）、`completed_run_evidence`（完成态运行证据）、`host_capabilities`（宿主能力探测）、`model_invocation`（模型调用面）、`plugins`（全栈插件契约）、`settings`（插件设置字段）、`skill_mutations`（技能变更合同）。它刻意不依赖任何框架——扩展声明自己 import 的一切，且：

> Never import `deerflow.*` or `app.*`: those are host internals with no compatibility promise.
>
> — [extensions quick-start](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/extensions/quick-start.mdx)

**contracts/：跨组件 JSON 契约**。仓库根的 [contracts/](https://github.com/bytedance/deer-flow/blob/v2.2.0/contracts/subagent_status_contract.json) 收纳跨语言/跨栈的机器可读契约，v2.2.0 共 **13 个文件**（v2.1.0 为 7 个）：`subagent_status_contract.json`（子代理状态枚举）、`slash_skill_contract.json`（slash 技能）、`run_event_stream_contract.json`（run 事件流）、`skill_review/` 四个 schema（`review_facts`、`review_report`、`package_snapshot`、`waiver_manifest`），以及 v2.2.0 新增的 `knowledge_sources.v1.json`（知识来源）、`thread_goal_contract.json`、`thread_origin_contract.json`、`scheduled_goal_notes_contract.json`、`scheduled_task_errors_contract.json`、`ui_locales.v1.json`。契约消费者（前端、外部工具）对照 schema 校验，而不是解析实现。

**三者分工**：示例包回答"怎么写"，extension-api 回答"能 import 什么"，contracts/ 回答"跨组件约定什么"。误读：把某一个示例当契约上限——最小的 `deerflow-extension-example` 只演示五种贡献类型，v2.2.0 的注册契约是九种（**含**实验性全栈插件面与只读知识提供者），而全栈插件、知识提供者这些面只能从 bookmarks / knowledge-* 等示例里学到（见[术语页](../application-development-model/02-terms.md)）。

## 应用仓能借鉴什么

**可移用**：① 给每种接入形态一个**跑得通的最小示例**，并让它的测试就是你想让用户抄的测试；② 公开契约与宿主内部严格分离，且对内部代码明说"无兼容承诺"——这比含糊的"内部使用"诚实；③ 跨组件约定落成 schema 文件而不是散在代码注释里。**应用仓建议**：extension 包仓最便宜而见效最快的动作是让自己的 README 达到示例包的标准：入口声明、测试口径、安装事务、信任边界四段俱全。

## 证据入口

- [examples/README.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/examples/README.md)（14 个示例的分组与 checker 用法）、[示例包 README](https://github.com/bytedance/deer-flow/blob/v2.2.0/examples/deerflow-extension-example/README.md) 与 `plugin.py`、`pyproject.toml`
- [scripts/check_extension.py](https://github.com/bytedance/deer-flow/blob/v2.2.0/scripts/check_extension.py)（打包检查覆盖面与"不 import 扩展"的边界）
- [extension-api 包](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/packages/extension-api/deerflow_extension_api/contracts.py)（19 个文件对 tag 核验）
- [contracts/ 目录](https://github.com/bytedance/deer-flow/blob/v2.2.0/contracts/subagent_status_contract.json)（13 个文件对 tag 核验）
