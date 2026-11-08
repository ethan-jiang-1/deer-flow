---
title: "上游文档地图：证据源，不是消化对象"
description: "docs、backend/docs 与 frontend/src/content 的计数、分组和 digest 引用状态；只做证据地图，不复制正文，也不把用户手册改写成摘要。"
type: index
topics: [upstream-docs, evidence, map, navigation]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 上游文档地图：证据源，不是消化对象

> **定位**：把仓库里的三类上游文档——`docs/`（跨切面设计/计划/历史）、`backend/docs/`（后端专题）、`frontend/src/content/{en,zh}/`（Nextra 用户手册）——当成**引用与核对的证据源**。本页只回答「有多少、怎么分组、哪些被 `_digested/` 引用过、要核对时去哪里找」。
> **边界**：不复制任何正文，不把用户手册再摘要成「手册的消化」。代码级结论以源码 `file:line` 为准；上游文档用于设计意图、历史与契约背景。范围声明同样适用于 [frontend/06-architecture](../frontend/06-architecture.md) 已记录的手册结构。

## 0. 口径

- 基线 `v2.2.0`；下列计数用 `find` 在当期工作树实测，并与 `v2.2.0` tag 的 `git ls-tree` 计数一致（2026-11-08）。
- 「被 digest 引用」的判定：在 `_digested/**/*.md` 中出现**显式路径** `docs/<name>`、`backend/docs/<name>` 或 `frontend/src/content/...`。只出现同名概念（如 `runtime`、`engine`）不算，避免把 175 个同名碰撞当成引用。
- 「0 引用」不是「无价值」；它是证据储备，或说明当前结论主要来自源码而不是该文档。

## 1. 总表

| 区域 | 文件数 | 分组 | digest 显式引用 |
|---|---:|---|---|
| `docs/` 根 | 11 md | 架构/契约/恢复/发布/SOP/历史修复 | **7 / 11** |
| `docs/` 嵌套 | 45 md | `agents/` 1、`experiments/` 6、`plans/` 13、`superpowers/` 25 | 未逐篇统计；根表只列 11 |
| `backend/docs/` | 47 md | 10 组（见 §3） | **18 / 47**（29 篇 0） |
| `frontend/src/content/` | 134 md/mdx | 6 组 + 根 `index.mdx`（见 §4） | `extensions` 手册 + `customization`/`middlewares` 测试夹具；其余仅结构/计数 |

`docs/` 全树 56 md = 根 11 + 嵌套 45；`frontend/src/content` 的 134 = 67（en）+ 67（zh），两语言镜像同构。

## 2. `docs/` 根 11 篇

| 文件 | 角色 | digest 引用 |
|---|---|---:|
| `ARCHITECTURE.md` | 顶层架构总览，指向 backend/frontend 模块指南 | 0 |
| `capability-center.md` | Capability Center 集成契约 | 5 |
| `CODE_CHANGE_SUMMARY_BY_FILE.md` | 基于 `git diff HEAD` 的逐文件历史变更总结 | 0 |
| `database-forward-revision-recovery.md` | thread-incarnation 数据库版本恢复 | 5 |
| `full-stack-plugins.md` | 全栈插件贡献面 | 2 |
| `OPENVIKING.md` | OpenViking memory backend | 1 |
| `RELEASE_SOP.md` | 发布 SOP | 1 |
| `SKILL_NAME_CONFLICT_FIX.md` | public/custom 同名技能冲突的历史修复记录 | 0 |
| `skill-evolution-host.md` | Skill evolution host API（P0） | 3 |
| `skill-usage-ui.md` | answer details 里的 skill usage 展示契约 | 0 |
| `task-continuity.md` | compaction 后的任务连续性 | 6 |

被引用的 7 篇是当前 digest 的设计/契约来源；0 引用的 4 篇见 §5 的抽查。它们的共同点是**历史或总览**，不是某条结论的唯一依据。

## 3. `backend/docs/` 47 篇：10 组

| 组 | 篇数 | 被引用 | 0 引用 |
|---|---:|---|---|
| A 架构/配置/安装 | 6 | `CONFIGURATION.md` | `APPLE_CONTAINER.md`、`ARCHITECTURE.md`、`PATH_EXAMPLES.md`、`README.md`、`SETUP.md` |
| B API/流式/运行时 | 8 | `middleware-execution-flow.md`、`REPLAY_E2E.md`、`RUN_EVENT_STREAM.md`、`THREAD_LIFECYCLE.md` | `API.md`、`RUN_INTERACTION_POLICY.md`、`STREAMING.md`、`summarization.md` |
| C 认证/安全/IO | 7 | `AUTH_TEST_DOCKER_GAP.md`、`AUTH_TEST_PLAN.md`、`BLOCKING_IO_DETECTION.md`、`GUARDRAILS.md`、`SSO.md` | `AUTH_DESIGN.md`、`AUTH_UPGRADE.md` |
| D 沙箱/文件/持久化 | 4 | `blob-storage.md`、`checkpoint-retention-contract.md`、`FILE_UPLOAD.md` | `SANDBOX_MEMORY_PROFILING.md` |
| E MCP/扩展 | 4 | — | `extension-agent-runs.md`、`extension-model-invocation.md`、`MCP_SERVER.md`、`mcp-control-leases.md` |
| F 记忆/标题/运行时提示 | 7 | — | `AUTO_TITLE_GENERATION.md`、`MEMORY_COGNITIVE_STYLE.md`、`MEMORY_IMPROVEMENTS_SUMMARY.md`、`MEMORY_IMPROVEMENTS.md`、`MEMORY_SETTINGS_REVIEW.md`、`runtime-guidance-details.md`、`TITLE_GENERATION_IMPLEMENTATION.md` |
| G 知识/工具/循环 | 4 | `KNOWLEDGE.md`、`LOOP_DETECTION.md` | `plan_mode_usage.md`、`task_tool_improvements.md` |
| H 通道/集成 | 2 | `GITHUB_AGENTS.md`、`IM_CHANNEL_CONNECTIONS.md` | — |
| I TUI | 1 | `TUI.md` | — |
| J RFC/待办 | 4 | — | `rfc-create-deerflow-agent.md`、`rfc-extract-shared-modules.md`、`rfc-grep-glob-tools.md`、`TODO.md` |

合计 47 篇：18 被显式引用、29 篇 0。最值得注意的空白是 **E 组（MCP/扩展）4 篇全 0**、**F 组（记忆/标题）7 篇全 0**、**J 组（RFC/待办）4 篇全 0**——至少说明当前 MCP 与记忆的 digest 结论主要建立在源码、测试与 `AGENTS.md` 上，而不是这两组说明文档上。

## 4. `frontend/src/content/` 134 篇：分组

| 组 | 每语言 | 双语合计 | digest 状态 |
|---|---:|---:|---|
| `harness/` | 45 | 90 | 顶层 13 页（`customization`/`middlewares` 被测试引用）+ `checkpoints/` 10 + `extensions/` 11 + `subagents/` 11；`extensions` 有手册级引用 |
| `application/` | 7 | 14 | 只在结构层被提及，无页面级 digest |
| `introduction/` | 4 | 8 | 同上，0 页面级引用 |
| `reference/` | 2 | 4 | `reference/model-providers/`；0 页面级引用 |
| `tutorials/` | 5 | 10 | 0 页面级引用 |
| `posts/` | 3 | 6 | 0 页面级引用 |
| 根 `index.mdx` | 1 | 2 | 0 |
| **合计** | **67** | **134** | — |

`harness/` 的 11/11/10 三组页数与目录结构由 [frontend/06-architecture:129,137-144](../frontend/06-architecture.md) 记录：`subagents/` 11、`extensions/` 11、`checkpoints/` 10；`extensions` 还有独立佐证（[09-packaged-extensions:17](../internals/harness-hooks/09-packaged-extensions.md)），`subagents/` 的目录化见 06:146。但页面级引用只有少数：`customization.mdx`/`middlewares.mdx` 作为 middleware 示例的测试夹具被点名（[01-agent-docs-system:79](../harness-engineering/01-agent-docs-system.md)），`extensions/` 手册被 09:17 点名 11 页；`subagents/`、`checkpoints/` 目前只有目录/计数（如 06:129 与 [frontend/README:37](../frontend/README.md)），`application/`、`introduction/`、`reference/`、`tutorials/`、`posts/` 只在 06:139 的目录枚举里出现。按页面计，这 134 篇里绝大多数是 0 引用。

## 5. 0 引用抽查：为什么不影响结论

| 文档 | 内容 | 0 引用的解释 |
|---|---|---|
| `docs/ARCHITECTURE.md` | 顶层架构总览，首段就指向 `backend/AGENTS.md` / `backend/docs/ARCHITECTURE.md` / `frontend/AGENTS.md` | digest 的 `overview/` 与各模块页直接从源码建立同一张图；总览不是唯一证据，0 引用合理 |
| `docs/CODE_CHANGE_SUMMARY_BY_FILE.md` | 开头明说「基于 `git diff HEAD` 的完整 diff，按文件列出」 | 这是一次性历史变更快照；稳定结论应回到代码/测试，不能依赖它 |
| `docs/SKILL_NAME_CONFLICT_FIX.md` | 2026-02-10 的同名技能冲突修复记录，且标注「已知问题保留」 | 历史修复笔记；当前技能隔离结论应看现行代码与测试 |
| `docs/skill-usage-ui.md` | answer toolbar 的 skill usage 捕获/历史契约 | 展示层契约，digest 更关心实现与测试；0 引用不代表实现不存在 |

同样，`backend/docs/ARCHITECTURE.md`、`MCP_SERVER.md`、`mcp-control-leases.md`、`MEMORY_*.md` 也都在 0 列表里；它们可作为交叉核对材料，但本文不把它们当「已消化的正文」。

## 6. 使用规则

1. **引用而不是搬运**：digest 里提到上游文档时给路径与章节；本页不复制段落。
2. **代码优先**：文档与源码冲突时，以源码 `file:line` 和测试为准；文档只解释意图与历史。
3. **显式路径才算引用**：同名概念不算；新增引用时尽量写全路径，方便机械校验。
4. **0 引用是状态，不是缺陷**：它提示「这块结论目前没有文档级依赖」，评审时应优先检查源码锚点是否足够。

## 阅读路径

1. **先看总表与 `docs/` 根 11 篇**：知道三类证据源的规模与边界；需要设计背景时先查这里。
2. **按主题进组**：后端问题查 §3 的 10 组；用户手册/页面问题查 §4 的 6 组。每组先看「被引用」列，再决定是否打开 0 引用文档做交叉核对。
3. **回到源码**：任何要写进 digest 的断言，最终都要在源码或测试里找到 `file:line`；上游文档只作为解释层。

## 相关目录

- [根 README](../README.md) — 全库阅读地图与写作纪律；本页沿用其「不复制正文、结论带证据」的约定。
- [_upstream-sync/SYNC.md](../_upstream-sync/SYNC.md) — 上游同步流程与机械校验器；本页的计数口径应与它一致。
- [07-design-philosophy-evidence.md](07-design-philosophy-evidence.md) — 用一手证据讲设计理念的样例；上游文档在其中只作背景。
- [frontend/06-architecture.md](../frontend/06-architecture.md) — `frontend/src/content` 的结构与页数记录。
- [internals/mcp/](../internals/mcp/README.md) 与 [internals/persistence/](../internals/persistence/README.md) — 两个最常需要回查 `backend/docs/` 的机制域。
