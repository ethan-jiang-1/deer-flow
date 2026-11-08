---



title: "部署与运维的成本视角"
description: '两个健康端点（/health 静态、/health/ready 真探测）、50 个迁移版本、多实例的成本含义，以及为什么「运维成本」和「token 成本」要分开看。'
topics: [governance, cost, ops]
verified_against: v2.2.0
last_verified: 2026-11-08
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

## 2. 迁移：50 个版本

`persistence/migrations/versions/` 下有 **50** 个 Alembic 版本文件，head 是
`0048_extension_execution_leases.py`。

| 事实 | 含义 |
|---|---|
| 50 个版本文件 | 升级路径长，跨版本升级要跑完整链条 |
| `migrate_user_isolation.py` 不在版本表内 | 一次性数据迁移脚本，位于 `backend/scripts/`，由运维单独执行 |
| 迁移的副本串行化 | **有**：Postgres 用 session advisory lock 串行化，SQLite 单进程串行（`persistence/bootstrap.py:52-96`） |

**第三行不再是未知项**：`persistence/bootstrap.py` 的 "Concurrency safety" 明确写了
Postgres 的 advisory lock 与 SQLite 的 30s busy_timeout/幂等 revision。多副本同时启动
会排队等锁，第二个实例观察到 head 后 no-op。

## 3. 多实例的成本含义

多实例本身不增加 token 成本，但会增加几类**非 token 成本**：

| 成本项 | 来源 |
|---|---|
| 数据库连接数 | 每副本一套连接池 |
| Redis 占用 | stream bridge 每副本连 |
| 迁移并发风险 | 见 §2 |
| 凭据密钥一致性 | 未设时单实例自动生成 `{base_dir}/.credentials_key`；只有声明 multi_instance 且有凭据消费者时才拒绝启动（`config/credentials_key.py:9`、`app/gateway/deps.py:333-377`） |
| 登录限速失效 | 默认 `throttle_storage=auto`：有 sqlite/postgres 时共享 db 表；只有显式 `memory` 才 N 副本 = N 倍额度（`config/auth_config.py:81-96`） |

最后一行是安全成本而非金钱成本，但同样由「多实例」这个决定带来。
展开见 [04-multi-instance.md](04-multi-instance.md)。

## 4. 配置热更新与运维成本

| 类型 | 生效方式 | 运维成本 |
|---|---|---|
| 策略字段（model / tool / memory / prompt） | 内容签名（mtime + size + sha256）→ 下次请求 | 低 |
| MCP servers / Skills 开关 | API 保存 → 立即 | 低 |
| 基础设施（database / sandbox / channels） | **重启** | 中——需安排窗口 |
| guardrails `fail_closed` / provider | 下一次 agent invocation 重新装配 | 低 |
| `allow_host_bash` | **重启** | 中 |

热加载的实现是文件签名（`config/app_config.py:756`、`config/file_signature.py:53-55`），
详见 [../lifecycle/01-agent-lifecycle.md](../lifecycle/01-agent-lifecycle.md) §2。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| Agent 级 SLO / error budget | **无** | 只有进程级健康；`LLMErrorHandlingMiddleware` 是 per-call retry + 实例级断路器 |
| Agent 级熔断 | **无** | 断路器挂在 middleware 实例上，跨 run 共享；没有按 agent 维度的 SLO/预算 |
| 灰度发布 | **无** | 配置全量生效 |
| Chaos engineering 支持 | **无** | — |
| 迁移的副本串行化保证 | **有** | Postgres advisory lock 强制串行；SQLite 单进程串行 + 30s busy_timeout（`persistence/bootstrap.py:52-96`） |
| 就绪探针的含义说明 | **有但不覆盖** | docstring 写清了，但没有面向运维的说明页 |

## 5.1 成本可观测性：有后视镜，没有刹车

- **有**：`/api/console/stats|runs|usage` 按当前用户聚合 token、per-model 用量和成本
  （`app/gateway/routers/console.py:289-360`、`:448-457`），前提是配置了 `models[*].pricing`。
- **无**：跨用户/集群视图、实时告警、按 agent 预算、货币预算执行。

所以「实时成本预算告警」的准确表述是「有事后成本视图，无实时预算告警」，
不是「连价格都不知道」。

## 6. 与其他章节的关系

- 部署步骤与备份：[../../enterprise-operations/](../../enterprise-operations/README.md)
- 多实例的治理影响：[04-multi-instance.md](04-multi-instance.md)
- 变更管理与生效路径：[../lifecycle/02-change-control.md](../lifecycle/02-change-control.md)
- 成本归属：[01-cost-attribution.md](01-cost-attribution.md)
