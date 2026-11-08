---
title: "GDPR 对照"
description: "六项 GDPR 要求对应的技术机制与缺口：访问权、删除权、处理记录、数据最小化、存储限制、跨境传输。每项给出现状边界。"
topics: [governance, compliance, gdpr]
---

# GDPR 对照

> ⚠️ **本页不构成合规结论**。以下只描述「有没有对应技术机制」，
> 不判定任何系统是否满足 GDPR，也不替代法律意见。

## 1. 六项要求一览

| GDPR 要求 | 机制状态 | 一句话 |
|---|---|---|
| 访问权（Art. 15） | **有数据，无端点** | per-user 存储使导出可行，但没有导出 API |
| 删除权（Art. 17） | **部分** | thread 可删；memory/上传无 TTL |
| 处理记录（Art. 30） | **有但不覆盖** | 有 journal 与 tracing，但非全量结构化 |
| 数据最小化（Art. 5） | **有但不覆盖** | PII 脱敏默认关闭 |
| 存储限制（Art. 5） | **部分** | 仅项目回收站有 TTL |
| 跨境传输（Ch. V） | **取决于部署** | 由 provider endpoint 配置决定 |

## 2. 访问权（Art. 15）

**数据确实按用户聚合**（`paths.py:344`）：

```
{base}/users/{user_id}/threads/{thread_id}/
```

所以「导出这个人的全部数据」在**文件系统层面**是可行的：
打包 `users/{user_id}/` 即可。

| 边界 | 事实 |
|---|---|
| 导出端点 | **无** |
| 关系库里的数据 | users 行、PAT、thread 记录**不在该目录下** |
| 需合并两处 | 是——目录 + 库 |

**结论**：技术上可导出，但需要两步手工操作（目录打包 + 库查询），
没有单一出口。

## 3. 删除权（Art. 17）

| 数据 | 可删 | 方式 |
|---|---|---|
| thread（库记录 + 目录） | 是 | `DELETE /api/threads/{id}`（`routers/threads.py:758`） |
| memory.json | 是 | 手工删文件；无 API |
| 上传文件 | 是 | 随 thread 删除 |
| **run 事件 / journal** | **是** | 随 thread 删除（`routers/threads.py:850-854`）；删除会把证据置 `partial` |
| **已发出的 LLM 请求** | **做不到** | 已离开部署边界 |

### 3.1 用户级删除的连带效果

删用户会让其 PAT 立即失效（`pat.py:224-228`：`authenticate_pat` 对已删除用户返回失败）。

**但文件目录不自动清理**——`users/{user_id}/` 需要手工删除。

### 3.2 最关键的一条边界

已发送给 LLM provider 的内容**无法撤回**。这不是 DeerFlow 的限制，
而是任何调用外部模型的系统的共同边界。它意味着：
删除权在技术上只能覆盖**本地留存**，不能覆盖**已发生的传输**。

## 4. 处理记录（Art. 30）

| 记录能力 | 状态 |
|---|---|
| RunJournal（per-run 中间件决策） | 有，见 [../audit/01-audit-chain.md](../audit/01-audit-chain.md) |
| Sandbox 审计 | 有 |
| Tracing（Langfuse/LangSmith 等） | 有，需配置 |
| **结构化的「处理活动登记」** | **无**——没有 Activity 级别的记录表 |

**Art. 30 要求的是「处理活动登记簿」**，即「为哪些目的处理哪类数据、存多久」。
这是文档性产物，DeerFlow 不生成也不维护它。

有 journal 支撑的是「某次运行里发生了什么」，而不是「这个系统的处理活动清单」。
两者的差距在 [../audit/01-audit-chain.md](../audit/01-audit-chain.md) §5 有说明。

## 5. 数据最小化（Art. 5）

| 机制 | 状态 |
|---|---|
| PII 脱敏 | **默认关闭**（`config.example.yaml:1538`） |
| 脱敏作用范围 | 用户消息 + 远程工具结果 + memory/compaction/title//goal 的出站；assistant 与本地工具结果不覆盖（`config.example.yaml:1525-1536`） |
| TypeSafe 出站 | **不覆盖**（`config.example.yaml:2372`） |
| 存储层脱敏 | **无**（原文留在 thread state） |

详见 [../data/05-pii-redaction.md](../data/05-pii-redaction.md)。

**最小化在这里的实际含义**：默认配置下，对话原文全量存进 thread state，
全量发给 LLM provider，且（若开启 memory）部分发给 TypeSafe API。

## 6. 存储限制（Art. 5(1)(e)）

| 数据 | TTL |
|---|---|
| 项目回收站 | **30 天**（`projects_config.py:49-52`） |
| thread | 无 |
| memory | 无 |
| 上传 | 无 |
| run 事件 | 无 |

且回收站清扫是**启动 + `GET /api/trash/documents` 惰性触发**（`app.py:327-331`、`routers/trash.py:146-158`）——
没有周期定时器，无人访问时不保证按时。详见 [../data/06-retention-and-residency.md](../data/06-retention-and-residency.md) §2。

## 7. 跨境传输（Chapter V）

数据出境的路径：

| 路径 | 谁决定目的地 |
|---|---|
| LLM 调用 | 运营方（`config.yaml` 的 provider） |
| 搜索/抓取 API | 运营方 |
| TypeSafe API（memory-extraction） | 功能开关 |
| personal MCP | **用户**（自填 URL） |
| IM channels | 运营方 |

**没有机制层面的地域约束**：单一 `base_dir`、单一 `database.backend`、
无按区域路由能力。blob 与 knowledge 的驻留也分别由 `blob_storage` 后端
和 provider 决定（见 [../data/06-retention-and-residency.md](../data/06-retention-and-residency.md) §5.1）。

所以跨境合规完全依赖**部署选址**与**provider 选择**，框架不参与。

### 7.1 personal MCP 是唯一的用户可控出口

其他出口都由运营方配置。personal MCP 的 URL 由用户自己填
（见 [../authorization/05-mcp-scope.md](../authorization/05-mcp-scope.md) §6）——
这是框架层无法限制的一条出境路径。

## 8. 缺口汇总

| 缺口 | 状态 | 边界 |
|---|---|---|
| 用户级数据导出端点 | **无** | 目录可打包，需手工合并库内数据 |
| 用户级删除（含目录） | **部分** | PAT 连带失效，目录需手工清 |
| 处理活动登记簿 | **无** | journal ≠ Art. 30 登记 |
| PII 脱敏默认启用 | **无** | `enabled: false` |
| thread/memory 的 TTL | **无** | 只有项目回收站有 |
| 定时清扫 | **无周期定时器** | 启动 + 回收站列表惰性触发 |
| 地域路由 | **无** | 单后端 |
| 已传输数据的撤回 | **做不到** | 架构边界，非缺陷 |

## 9. 与其他章节的关系

- 存储布局：[../data/01-storage-and-isolation.md](../data/01-storage-and-isolation.md)
- 保留期与驻留：[../data/06-retention-and-residency.md](../data/06-retention-and-residency.md)
- PII 脱敏：[../data/05-pii-redaction.md](../data/05-pii-redaction.md)
- 审计链：[../audit/01-audit-chain.md](../audit/01-audit-chain.md)
