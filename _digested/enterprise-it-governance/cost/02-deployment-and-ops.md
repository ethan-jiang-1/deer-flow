---
title: "部署与运维的成本视角"
description: "两个健康端点（/health 静态、/health/ready 真探测）、51 个迁移版本、多实例的成本含义，以及为什么「运维成本」和「token 成本」要分开看。"
topics: [governance, cost, ops]
---

# 部署与运维的成本视角

本页只关心一件事：**哪些运维动作会带来成本，以及成本落在哪里**。
安装、配置、备份的操作步骤在 [enterprise-operations/](../../enterprise-operations/README.md)。

## 1. 两个健康端点（不是一回事）

这一点在编排配置里最容易搞错。

| 端点 | 行 | 实际行为 |
|---|---|---|
| `GET /health` | `app/gateway/app.py:1446` | **静态返回** `{"status": "healthy", ...}`——永远 200 |
| `GET /health/ready` | `app/gateway/app.py:1455` | **真探测**后端，失败返回 503 `degraded` |

### 1.1 `/health/ready` 到底探什么

`backend/app/gateway/app.py:1457-1472` 的 docstring 写得很清楚：在**同一个有界超时**下并发探测：

| 探测目标 | 是否阻塞就绪 |
|---|---|
| `database:` 背后的 ORM engine | **是** |
| 生效的 LangGraph checkpointer / Store 后端 | **是** |
| stream bridge 的 Redis 后端 | **是** |
| sandbox provisioner 的 `/health` | **否**（仅报告，不 gate） |

最后一行有一个明确理由（原文）：

> the provisioner verdict is informational because **every replica shares one provisioner**

即：所有副本共用一个 provisioner，让它 gate 每个副本的就绪状态没有意义。

### 1.2 对可用性的直接含义

| 用错端点 | 后果 |
|---|---|
| 用 `/health` 做就绪探针 | 数据库还没起来，网关就报告 ready → **请求进来后失败** |
| 用 `/health/ready` 做存活探针 | 后端短暂抖动 → **容器被重启**（不该重启时重启） |

另一条：`/health/ready` 的目标来自**启动快照**，不读热加载后的配置
（docstring: "Targets come from the startup snapshot recorded by `langgraph_runtime`"）。
所以改了 `database:` 之后，就绪探针仍然探旧目标，直到重启。

## 2. 迁移：51 个版本

`persistence/migrations/versions/` 下有 **51** 个 Alembic 版本文件，head 是
`0048_extension_execution_leases.py`。

| 事实 | 含义 |
|---|---|
| 51 个版本文件 | 升级路径长，跨版本升级要跑完整链条 |
| 有 `migrate_user_isolation.py` | 用户隔离是一次性的数据迁移，不是纯 schema 变更 |
| 迁移的副本串行化 | **未文档化**，多副本同时启动时的行为需自行实测 |

**第三行是风险来源**：多实例部署时，若 N 个副本同时启动并各自尝试迁移，
要么框架内部有锁，要么就需要运维侧保证只有一个副本跑迁移。

## 3. 多实例的成本含义

多实例本身不增加 token 成本，但会增加几类**非 token 成本**：

| 成本项 | 来源 |
|---|---|
| 数据库连接数 | 每副本一套连接池 |
| Redis 占用 | stream bridge 每副本连 |
| 迁移并发风险 | 见 §2 |
| 凭据密钥一致性 | `DEER_FLOW_CREDENTIALS_KEY` 未设时**拒绝启动**（`config/credentials_key.py:10-13`） |
| 登录限速失效 | N 副本 = 攻击者有 N 倍尝试额度（`auth_config.py:139-140`） |

最后一行是安全成本而非金钱成本，但同样由「多实例」这个决定带来。
展开见 [04-multi-instance.md](04-multi-instance.md)。

## 4. 配置热更新与运维成本

| 类型 | 生效方式 | 运维成本 |
|---|---|---|
| 策略字段（model / tool / memory / prompt） | mtime 检测 → 下次请求 | 低 |
| MCP servers / Skills 开关 | API 保存 → 立即 | 低 |
| 基础设施（database / sandbox / channels） | **重启** | 中——需安排窗口 |
| guardrails `fail_closed` / provider | **重启** | 中 |
| `allow_host_bash` | **重启** | 中 |

热加载的实现是文件签名（`config/app_config.py:756`、`config/file_signature.py:53-55`），
详见 [../lifecycle/01-agent-lifecycle.md](../lifecycle/01-agent-lifecycle.md) §2。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| Agent 级 SLO / error budget | **无** | 只有进程级健康；`LLMErrorHandlingMiddleware` 是 per-call retry + 断路器，无 agent 级熔断 |
| Agent 级熔断 | **无** | `LLMErrorHandlingMiddleware` 有 per-call retry + circuit breaker，但作用域仅单次调用 |
| 灰度发布 | **无** | 配置全量生效 |
| Chaos engineering 支持 | **无** | — |
| 迁移的副本串行化保证 | **有但不覆盖** | 框架有迁移机制，但副本间串行化未文档化 |
| 就绪探针的含义说明 | **有但不覆盖** | docstring 写清了，但没有面向运维的说明页 |

## 6. 与其他章节的关系

- 部署步骤与备份：[../../enterprise-operations/](../../enterprise-operations/README.md)
- 多实例的治理影响：[04-multi-instance.md](04-multi-instance.md)
- 变更管理与生效路径：[../lifecycle/02-change-control.md](../lifecycle/02-change-control.md)
- 成本归属：[01-cost-attribution.md](01-cost-attribution.md)
