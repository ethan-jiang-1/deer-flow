---


title: "扩展示例目录：14 个 deerflow-extension-* 包的贡献点地图"
description: '把 examples/ 下 14 个可安装扩展示例按 9 个 registry 注册方法归类，逐包给出贡献点、入口、测试与延伸阅读，作为 09 契约页与 security/06 授权页之间的选型地图。'
type: deep-dive
topics: [extensions, examples, plugin-system, contribution-points, knowledge]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 扩展示例目录：14 个 `deerflow-extension-*` 包的贡献点地图

> **定位**：`examples/` 下 14 个独立打包扩展示例的横向地图，回答「想做一个 X 类扩展，先抄哪个包」以及每个包演示了 9 个注册方法中的哪些。
> **边界**：不替代 [09-packaged-extensions.md](09-packaged-extensions.md) 的 loader / CLI / 回滚 / 版本契约，也不替代 [security/06](../../enterprise-operations/security/06-extension-boundary.md) 的宿主授权与 plugin action 目标边界；包的安装流程、`@extension(api=...)` 与回滚语义一律以 09 为准。

## 三信任面

| 信任面 | 载体与时机 | 谁能写 | 代码执行 |
|---|---|---|---|
| `plugins:` | `config.yaml` 顶层，启动时按序 `import` 入口点 | 仅 operator（文件只读挂载） | 是；扩展代码以 Gateway 权限运行 |
| `extensions_config.json` | Gateway 运行期可写：MCP servers、skills 状态、声明的 middleware | 用户/管理员经 API | 间接；middleware 的 `module:Class` 仍会 import |
| extension runtime | `install(registry, config)` 在 Gateway 进程内注册 | 扩展作者（受上面两面约束） | 是；middleware / service / router 无独立沙箱 |

结论先行：`plugins:` 是代码执行边界，所以它不能搬进 API 可写的 `extensions_config.json`。三面的逐项授权见 [security/06](../../enterprise-operations/security/06-extension-boundary.md)。

## 9 个注册方法（`ExtensionRegistry`）

| 方法 | 用途 | 示例包是否演示 |
|---|---|---|
| `plugin` | 全栈插件：BrowserAssets、BackendAction、SettingsField、ModelTool | 演示（9 包） |
| `knowledge_provider` | 注册只读 `RetrievalProvider`；宿主校验 capabilities / catalog / documents | 演示（3 包） |
| `middlewares` | 注入 `MiddlewareContributor`，按 placement + scope 装配 | 演示（4 包） |
| `task_lifecycle` | `on_task_start` / `on_task_stop` 任务生命周期回调 | 演示（`example`） |
| `system_model_observer` | 观察系统模型调用（kind / request / result） | 演示（`example`） |
| `agent_assembly_observer` | 同步观察 agent 装配完成，必须廉价且不抛错 | **无** |
| `context_compaction_observer` | 异步观察上下文压缩事件 | **无** |
| `service` | 注册带 `start/stop` 的 Gateway 生命周期服务 | 演示（3 包） |
| `routers` | 挂载安装期构造的 FastAPI router | 演示（3 包） |

> `plugin()` / `knowledge_provider()` 返回 `False` 表示宿主不支持该贡献；示例包用 `is not True` 立即抛错，不做静默降级。注册方法的完整签名见 [09](09-packaged-extensions.md) 与 `backend/packages/extension-api/deerflow_extension_api/contracts.py`。

## 14 个包

> 入口均为 `<pkg>/__init__.py` 的 `install`；入口点名与目录名不同的只有 `knowledge` → `knowledge-example`、`lightrag` → `lightrag-relations`。只有 `example` 带包内 `tests/`，其余包的可执行覆盖在 `backend/tests/`；[test-strategy/08](../../test-strategy/08-upper-layer-apps.md) 记录了「包内测试不强制、有测试就跑」的取舍。

| 包 | 演示的贡献点 | 有 tests？ | 入口文件 | digest 关联页 |
|---|---|---|---|---|
| `example` | `middlewares` + `task_lifecycle` + `system_model_observer` + `service` + `routers`，五类最小演示 | 有 · 包内 `tests/`（3 文件） | [deerflow_extension_example/__init__.py](../../../examples/deerflow-extension-example/deerflow_extension_example/__init__.py) | [09](09-packaged-extensions.md)、[04](04-agent-middleware-hooks.md) |
| `bookmarks` | `plugin`：BrowserAssets + 5 个 BackendAction + `search_bookmarks` tool；SQLite 按 user_id 隔离 | 有 · `test_bookmark_plugin.py` | [deerflow_extension_bookmarks/__init__.py](../../../examples/deerflow-extension-bookmarks/deerflow_extension_bookmarks/__init__.py) | [09](09-packaged-extensions.md)、[security/06](../../enterprise-operations/security/06-extension-boundary.md) |
| `agent-teams` | `plugin`（页面 + 9 actions + 8 tools）+ `service` + `middlewares`（LEAD 提及路由） | 有 · `test_agent_teams_plugin.py` | [deerflow_extension_agent_teams/__init__.py](../../../examples/deerflow-extension-agent-teams/deerflow_extension_agent_teams/__init__.py) | [04](04-agent-middleware-hooks.md)、[09](09-packaged-extensions.md) |
| `workflows` | `plugin`（页面 + 14 actions + 6 tools）+ `service`；opt-in、POSIX、进程内状态机 | 有 · `test_workflow_plugin.py` 等 | [deerflow_extension_workflows/__init__.py](../../../examples/deerflow-extension-workflows/deerflow_extension_workflows/__init__.py) | [09](09-packaged-extensions.md)、[编排扩展点](../../graph-engineering/08-orchestration-extension-points.md) |
| `knowledge-management` | `plugin`（`contract` action）+ `routers`；provider-owned 文档摄入，无前端/索引 | 有 · `test_knowledge_management_extension.py` | [deerflow_extension_knowledge_management/__init__.py](../../../examples/deerflow-extension-knowledge-management/deerflow_extension_knowledge_management/__init__.py) | [知识抽象](../../concepts/community-tools/09-knowledge-abstraction.md)、[09](09-packaged-extensions.md) |
| `knowledge-platform` | `plugin`（`contract` action）+ `routers`；space policy + 成员/共享，SQLite 存策略 | 有 · `test_knowledge_platform_extension.py` | [deerflow_extension_knowledge_platform/__init__.py](../../../examples/deerflow-extension-knowledge-platform/deerflow_extension_knowledge_platform/__init__.py) | [知识抽象](../../concepts/community-tools/09-knowledge-abstraction.md)、[09](09-packaged-extensions.md) |
| `weknora` | `knowledge_provider("weknora")`：只读文档 + scope 收窄 + 引用预算 | 有 · `test_weknora_extension.py`（+ live / blocking_io） | [deerflow_extension_weknora/__init__.py](../../../examples/deerflow-extension-weknora/deerflow_extension_weknora/__init__.py) | [Knowledge 契约](../knowledge/README.md)、[知识抽象](../../concepts/community-tools/09-knowledge-abstraction.md) |
| `lightrag` | `knowledge_provider("lightrag-relations")`：文档 + 实体关系，`relations_search` | 有 · `test_lightrag_relations_extension.py` | [deerflow_extension_lightrag/__init__.py](../../../examples/deerflow-extension-lightrag/deerflow_extension_lightrag/__init__.py) | [Knowledge 契约](../knowledge/README.md)、[LightRAG](../../concepts/community-tools/08-lightrag.md) |
| `jev-classify` | `plugin`：3 个 SettingsField + `status` action + `classify_texts` tool | 有 · `test_jev_classify_extension.py` | [deerflow_extension_jev_classify/__init__.py](../../../examples/deerflow-extension-jev-classify/deerflow_extension_jev_classify/__init__.py) | [TypeSafe](../typesafe/README.md)、[09](09-packaged-extensions.md) |
| `jev-context` | `plugin`（`status` action）+ `middlewares`：`JevCompaction` 位于 `MODEL_LOGICAL` | 有 · `test_jev_context_extension.py` | [deerflow_extension_jev_context/__init__.py](../../../examples/deerflow-extension-jev-context/deerflow_extension_jev_context/__init__.py) | [04](04-agent-middleware-hooks.md)、[TypeSafe](../typesafe/README.md) |
| `jev-screening` | `middlewares`：`TOOL_VISIBLE` / `BOTH` 的只读告警式内容筛查 | 有 · 3 个 `test_jev_*screening*.py` | [deerflow_extension_jev_screening/__init__.py](../../../examples/deerflow-extension-jev-screening/deerflow_extension_jev_screening/__init__.py) | [04](04-agent-middleware-hooks.md)、[TypeSafe 失败策略](../typesafe/02-adapters-failure-policy.md) |
| `report-sections` | `plugin`：单个有状态 `save_section` tool，拼装结果走 artifact 不回灌上下文 | 有 · `test_report_sections_extension.py` | [deerflow_extension_report_sections/__init__.py](../../../examples/deerflow-extension-report-sections/deerflow_extension_report_sections/__init__.py) | [工具设计](../../harness/04-tool-and-interface-design.md)、[09](09-packaged-extensions.md) |
| `retrieval` | `plugin`：只读 `search_docs` tool，演示 `content_and_artifact` | 有 · `test_retrieval_plugin_artifacts.py` | [deerflow_extension_retrieval/__init__.py](../../../examples/deerflow-extension-retrieval/deerflow_extension_retrieval/__init__.py) | [工具设计](../../harness/04-tool-and-interface-design.md)、[09](09-packaged-extensions.md) |
| `knowledge` | `knowledge_provider("synthetic-example")`：离线合成语料 + catalog/documents/scope | 有 · `test_knowledge_provider.py` | [deerflow_extension_knowledge/__init__.py](../../../examples/deerflow-extension-knowledge/deerflow_extension_knowledge/__init__.py) | [Knowledge 契约](../knowledge/README.md)、[知识抽象](../../concepts/community-tools/09-knowledge-abstraction.md) |

## 阅读路径

1. **先看**：[`example`](../../../examples/deerflow-extension-example/)（五类最小骨架 + 包内 tests）→ [`bookmarks`](../../../examples/deerflow-extension-bookmarks/)（`plugin` 全栈：前端、action、tool、按用户隔离）。两条合起来覆盖「无 UI」与「有 UI」两个起点。
2. **再看**：[`knowledge`](../../../examples/deerflow-extension-knowledge/) → [`weknora`](../../../examples/deerflow-extension-weknora/) / [`lightrag`](../../../examples/deerflow-extension-lightrag/)，对照 [Knowledge 契约](../knowledge/README.md) 看 `knowledge_provider` 从合成 provider 到真实 HTTP provider 的增量。
3. **深入**：[`agent-teams`](../../../examples/deerflow-extension-agent-teams/) 与 [`workflows`](../../../examples/deerflow-extension-workflows/) 的组合面（`plugin` + `service` + `middlewares`），再回 [09](09-packaged-extensions.md) 与 [security/06](../../enterprise-operations/security/06-extension-boundary.md) 核对授权和事务边界。

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)（不改源码、`main` 镜像上游、笔记只落在 `ethan`）。
- 扩展契约以 [09](09-packaged-extensions.md) 与 [backend/packages/harness/deerflow/extensions/AGENTS.md](../../../backend/packages/harness/deerflow/extensions/AGENTS.md) 为准；`@extension(api=...)` 只是兼容声明，不是授权。
- 示例包持续演进：本页按 v2.2.0 基线核对，行为差异以各包源码与其 `README.md` / `AGENTS.md` 为准，不确定处标「未核实」，不补写贡献点。

## 相关目录

- [harness-hooks/](README.md) — 本目录：09 讲契约，本篇讲 14 个包怎么用。
- [middleware/](../middleware/README.md) — `middlewares` 贡献点背后的 39 个 middleware 条目与装配顺序。
- [knowledge/](../knowledge/README.md) — `knowledge_provider` 的只读检索契约、能力位与预算。
- [configuration/02-extensions-json.md](../configuration/02-extensions-json.md) — `extensions_config.json` 的字段与写回路径。
- [security/06](../../enterprise-operations/security/06-extension-boundary.md) — plugin / action / host_access 的授权边界。
- [examples/](../../../examples/) — 14 个包的源码与各自 README。
