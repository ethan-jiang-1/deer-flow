---
title: "保留期与数据驻留"
description: "唯一存在的自动保留机制是项目回收站（trash_retention_days，默认 30 天），启动 + 回收站列表惰性清扫。thread、memory、上传文件均无 TTL；blob 与 knowledge 由后端/provider 决定。数据驻留完全依赖部署形态。"
topics: [governance, data, retention, residency]
---

# 保留期与数据驻留

数据生命周期的两个问题：「到期会自动删吗」和「数据一定在某个地域吗」。
DeerFlow 对前者**只有一个机制**，对后者**没有任何机制**。

## 1. 唯一的自动保留机制：项目回收站

`config.example.yaml` 的 projects 段与 `packages/harness/deerflow/config/projects_config.py:49-52`：

| 项 | 值 |
|---|---|
| 键 | `projects.trash_retention_days` |
| 默认 | **30 天** |
| 约束 | `ge=1, le=3650` |
| 作用对象 | **回收站中的项目文档** |

`projects_config.py:24-25` 的语义：

> `trash_retention_days` is the window after which trashed documents become
> eligible for the retention purge.

**关键词是 "eligible"**——进入可清除窗口，不等于立刻删除。

## 2. 清扫时机：启动 + 惰性触发

`app/gateway/app.py:327-331` 的 docstring 写的是：

> One trash retention sweep at gateway startup ...
> Runs beside the lazy trigger on the trash listing — no daemon, no scheduler.

也就是说，除了启动，`GET /api/trash/documents` 每次列表都会惰性触发一次清扫
（`routers/trash.py:146-158`）。

| 特征 | 事实 |
|---|---|
| 触发时机 | **Gateway 启动** + **`GET /api/trash/documents` 列表时** |
| 频率 | 启动一次 + 每次列表请求一次 |
| 是否持续运行 | **否**——没有后台定时任务/守护进程 |
| 清扫内容 | 过期文档清除、孤儿清理、staging 清理（`app.py:347`） |
| 可观测 | 有结构化日志：`purged/failures/orphans/staging/content_missing`（`app.py:348-351`） |

**运维含义**：长期不重启**不会**「永远不清扫」——只要有人打开回收站列表就会触发；
但它不是周期任务，无人访问时「30 天后自动删除」不保证按时发生。
要严格 SLA，仍需外部 cron 调列表端点或自行跑清理。

## 3. 其余数据都没有 TTL

| 数据 | 自动过期 | 清理方式 |
|---|---|---|
| **thread** | **无** | 显式 `DELETE /api/threads/{id}`（`routers/threads.py:758` `delete_thread_data`） |
| **memory.json** | **无** | 无 |
| **上传文件**（uploads） | **无** | 随 thread 删除 |
| **workspace / outputs** | **无** | 随 thread 删除 |
| **run 事件与 journal** | **无** | 无 |
| **项目回收站** | **有**（30 天默认） | 启动时清扫 |

所以「保留期策略」的实际形态是：**除回收站外，一律人工删除**。

## 4. 删除的实际范围

`routers/threads.py:758` 的 `delete_thread_data` 是唯一的数据删除入口：

| 删除对象 | 覆盖 |
|---|---|
| LangGraph thread 记录 | 是 |
| 本地 thread 目录（`users/{id}/threads/{tid}/`） | 是 |
| 沙箱内的残留 | 取决于沙箱模式 |
| 已产生的 run 事件 | **是**——`delete_by_thread` 删事件行，并把 `evidence_seal_state` 置 `partial`、revision +1、删 `CompletedRunSnapshotRow`（`routers/threads.py:850-854`、`runtime/events/store/db.py:583`、`:401-416`） |

**user 删除的边界**（见 [../identity/08-pat.md](../identity/08-pat.md) §2.3）：
删用户会让其 PAT 立即失效，但文件系统目录需要自行清理。

## 5. 数据驻留：无机制

| 层面 | 事实 |
|---|---|
| 数据库 | 单一 `database.backend`，无按区域路由 |
| 文件系统 | 单一 `base_dir` |
| 模型调用 | 发往配置的 provider endpoint |
| 外部出口 | memory-extraction 的 TypeSafe API（见 [05-pii-redaction.md](05-pii-redaction.md) §5.1） |
| MCP | 用户自定义的 personal MCP 可连任意 URL |

**结论**：数据驻留只能靠**部署形态**保证——把整个栈部署在目标地域。

### 5.1 blob 与 knowledge 的驻留边界

| 存储 | 默认 | 驻留位置 | 保留期 |
|---|---|---|---|
| `blob_storage` | `enabled: false` | `local_fs` 默认根 `{runtime_home}/blobs`（`blob_storage_config.py:27-52`） | **无 TTL**；删 thread/文档不会自动清 blob |
| `knowledge_base` | `enabled: false` | 由 provider tool 决定（RAGFlow 等外部服务，`knowledge_base_config.py:1-15`） | **由 provider 决定**，框架不管 |

所以「知识库数据驻留在哪」这个问题，答案不在 DeerFlow，而在你选的 provider 和它的部署地域。
框架本身不提供「按用户/租户路由到不同地域」的能力。

### 5.1 出站流量清单

数据可能离开部署边界的路径：

| 路径 | 目的地 | 可控性 |
|---|---|---|
| LLM 调用 | `config.yaml` 里的 provider | 运营方配置 |
| `web_fetch` / `web_search` | 工具配置的搜索 API | 运营方配置 |
| memory-extraction | TypeSafe API | 功能开关 |
| personal MCP | 用户自填 URL | **用户控制** |
| IM channels | Slack/Lark 等 | 运营方配置 |

最后一条值得单独标注：**personal MCP 的出口地址由用户决定**，
运营方无法在框架层限制（见 [../authorization/05-mcp-scope.md](../authorization/05-mcp-scope.md) §6）。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| thread / memory / 上传的自动过期 | **无** | 只有项目回收站有 TTL |
| 周期定时清扫 | **无** | 有启动 + `GET /api/trash/documents` 惰性触发，但没有后台定时器；无人访问时不保证按时 |
| 按用户/租户的保留期策略 | **无** | `trash_retention_days` 是全局值 |
| 数据驻留路由 | **无** | 单后端 |
| 按用户导出 | **无** | 见 [01-storage-and-isolation.md](01-storage-and-isolation.md) §5 |
| 删除的完整性（事件是否连带删） | **有** | thread 目录、runs、run 事件、feedback 一起删；事件删除会把证据置 `partial`（见 §4） |
| 保留期变更的生效时机 | **有但不覆盖** | `trash_retention_days` 每请求现读（`routers/trash.py:155`），不需重启；但只在触发清扫时生效 |

## 7. 与其他章节的关系

- 存储布局与清理范围：[01-storage-and-isolation.md](01-storage-and-isolation.md)
- PII 与出站：[05-pii-redaction.md](05-pii-redaction.md)
- GDPR 的存储限制原则：`../compliance/02-gdpr.md`
- personal MCP 的出口：[../authorization/05-mcp-scope.md](../authorization/05-mcp-scope.md)
