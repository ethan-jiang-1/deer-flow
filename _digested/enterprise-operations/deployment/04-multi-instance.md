---

title: "多实例部署：前置、启动门与运行语义"
description: '跨 Pod 与多 worker 的部署前置和运行语义：本地双 Gateway 试验台、Helm 副本与 Service、启动门、Redis stream bridge、频道 leader lease 与 ExecutionFence；不替代治理判断。'
type: deep-dive
topics: [deployment, multi-instance, kubernetes, redis, startup-gate]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 多实例部署：前置、启动门与运行语义

> **定位**：回答「把 DeerFlow 从单进程复制成多 worker / 多 Pod 时，哪些前置必须先成立、启动时谁在强制、跨实例的 SSE / 频道 / 执行权靠什么衔接」。偏部署与运行语义，不替平台做「该不该复制」的取舍。
> **边界**：治理判断、成本归属与缺口见 [governance/cost/04](../../enterprise-it-governance/cost/04-multi-instance.md)；镜像构建、Compose 步骤见 [01-docker.md](01-docker.md)，Nginx 路由/SSE 细节见 [02-nginx-and-k8s.md](02-nginx-and-k8s.md)；本文只点到 Helm 的副本与 Service。

## 0. 先分清三种「多」

| 形态 | 谁看得见 | 关键信号 | 证据 |
|---|---|---|---|
| 同一进程树内多 worker | Gateway 自己 | `GATEWAY_WORKERS`，或 uvicorn 读取的 `WEB_CONCURRENCY` | `backend/app/gateway/deps.py:64-91` |
| 多个 Pod × 每 Pod 1 worker | **worker 计数看不见** | 显式 `deployment.multi_instance` / `DEER_FLOW_MULTI_INSTANCE` | `backend/app/gateway/deps.py:104-118`；`backend/packages/harness/deerflow/config/deployment_config.py:3-13` |
| 跨进程运行面 | 依赖共享存储/租约 | Postgres、Redis bridge、run heartbeat、channel lease、ExecutionFence | `backend/app/gateway/deps.py:137-158` |

## 1. 本地双实例：`make dev-multi`

`Makefile:185-192` 提供 `dev-multi` / `dev-multi-check` / `dev-multi-down`，分别转调 `scripts/dev_multi_instance.sh` 的 `up` / `check` / `down`（帮助文本见 `Makefile:52-54`）。

| 它做什么 | 证据 |
|---|---|
| 两个 Gateway（默认 `8001` / `8011`）、共享 Postgres（`55432`）与 Redis（`56379`） | `scripts/dev_multi_instance.sh:27-32` |
| 使用独立状态目录（默认 `.deer-flow/multi-instance`），不碰 `make dev` 的 `backend/.deer-flow` | `scripts/dev_multi_instance.sh:12-13,21-26` |
| 渲染多实例 config：`deployment.multi_instance: true`、Postgres、`run_events: db`、heartbeat、Redis bridge、sandbox ownership 指向 Redis | `scripts/dev_multi_instance.py:89-123,145-159` |
| 两个 Gateway 都固定 `GATEWAY_WORKERS=1 WEB_CONCURRENCY=1`，各自 `uvicorn` 单进程 | `scripts/dev_multi_instance.sh:281-293` |
| 先 A 后 B 冷启动；因为 checkpointer 的 `setup()` 没有 advisory lock，不能并行 | `scripts/dev_multi_instance.sh:515-518` |
| 可选 nginx 在 `:2027` 做 round-robin；不存在时仍可直连两个 Gateway | `scripts/dev_multi_instance.sh:337-361` |
| `check` 验证共享会话、跨实例 thread、上传、skill 开关、SSE 续传 | `scripts/dev_multi_instance.py:685-692,517-523,556-564,657-683` |

两个容易踩的运维点：`up` 默认把 IM channels 关掉，只有 `DEERFLOW_MI_KEEP_CHANNELS=1` 才保留（`scripts/dev_multi_instance.py:161-173`；`scripts/dev_multi_instance.sh:83`）；`make stop` / `make dev` 会回收 `8001`，不要和这套 harness 同时跑（`scripts/dev_multi_instance.sh:86-87`）。`down` 会删容器与本 harness 数据，日志保留（`scripts/dev_multi_instance.sh:60,544-549`），状态目录靠 marker 防误删（`scripts/dev_multi_instance.sh:163-176`）。

## 2. Helm：副本、声明与 Service

| 对象 | 默认/取值 | 证据 | 说明 |
|---|---|---|---|
| `gateway.replicas` | `1` | `deploy/helm/deer-flow/values.yaml:50` | 保守默认；>1 时 chart 导出 `DEER_FLOW_MULTI_INSTANCE=true` |
| `gateway.multiInstance` | `null`（从 replicas 推导） | `deploy/helm/deer-flow/values.yaml:51-60`；`deploy/helm/deer-flow/templates/_helpers.tpl:85-95` | `kubectl scale` / HPA 不触发 Helm upgrade，需显式设 `true` |
| Gateway env | `DEER_FLOW_MULTI_INSTANCE=<derived>` | `deploy/helm/deer-flow/templates/gateway-deployment.yaml:188-193` | 启动门因此能看到「同库多 Pod」 |
| Gateway Service | 固定 `ClusterIP`，端口 `8001` | `deploy/helm/deer-flow/templates/gateway-service.yaml:9-14` | 集群内入口，不直接对外 |
| nginx Service | 默认 `ClusterIP`，可改 `LoadBalancer`/`NodePort` | `deploy/helm/deer-flow/values.yaml:132-139`；`deploy/helm/deer-flow/templates/nginx-service.yaml:10` | Web 入口的 Service（Ingress 在其前面）；`port` 默认 `2026` |
| `provisioner.replicas` | `1` | `deploy/helm/deer-flow/values.yaml:166`；`deploy/helm/deer-flow/templates/provisioner-deployment.yaml:11` | 多副本安全，见下 |
| Provisioner Service | `ClusterIP`，端口 `8002` | `deploy/helm/deer-flow/templates/provisioner-service.yaml:10-15` | 请求可落到任一副本，无 affinity |
| 捆绑 Redis | `StatefulSet` 副本数固定 `1` | `deploy/helm/deer-flow/templates/redis-statefulset.yaml:16` | 用外部 Redis 时设 `redis.enabled: false`（`values.yaml:270-271`） |

滚动策略是 surge-then-drain：`maxSurge: 1`、`maxUnavailable: 0`（`values.yaml:61-68`）；Gateway PDB 仅在多实例渲染（`templates/gateway-pdb.yaml:9`），Provisioner PDB 仅在 `replicas > 1` 渲染（`templates/provisioner-pdb.yaml:11`）。

**Provisioner 多副本**：它不在请求之间保存状态，sandbox Pod/Service 的标签就是注册表；create 容忍并发副本产生的 `409 AlreadyExists`（`docker/provisioner/app.py:1327-1336`），并在 409 后回读容量（`app.py:1355-1364`）；NodePort 由 API server 分配，Service 会把调用摊到所有副本，因此 `provisioner.replicas > 1` 安全（`values.yaml:154-165`）。它没有 `multiInstance` 开关，因为 chart 没有其他按副本数变化的行为（`values.yaml:165`）。不要把它和 `config.sandbox.replicas: 3` 混为一谈：后者是每个 Gateway 进程的 sandbox 容量（`values.yaml:407`；`backend/packages/harness/deerflow/config/sandbox_config.py:260-263`）。

## 3. 启动门：什么被强制

声明有两种来源：环境变量 `DEER_FLOW_MULTI_INSTANCE` 优先，其次是 `deployment.multi_instance`（`backend/packages/harness/deerflow/config/deployment_config.py:76-106`）。空、`0`、`false`、`no`、`off` 视为未声明；**其他任何值都算声明**，拼错也会跑闸门，这是刻意的 fail-closed（`deployment_config.py:28,76-90`）。Helm 用副本数生成该 env（`deploy/helm/deer-flow/templates/_helpers.tpl:85-95`），所以 K8s 的「每 Pod 1 worker」不再绕过启动门。

`_enforce_postgres_for_multi_worker` 在启动时调用（`backend/app/gateway/deps.py:784`），先取 worker 信号（`deps.py:94-118`），再按声明执行检查（`deps.py:137-158`）：

| 检查 | 拒绝条件 | 证据 |
|---|---|---|
| Postgres | `database.backend != "postgres"` | `deps.py:221-223` |
| 运行事件 | `run_events.backend != "db"` | `deps.py:224-230` |
| Run 所有权 | `run_ownership.heartbeat_enabled` 不为 true | `deps.py:231-238` |
| 跨进程 SSE | `stream_bridge` 不是 redis，且无 `DEER_FLOW_STREAM_BRIDGE_REDIS_URL` | `deps.py:121-125,240-246` |
| 浏览器工具 | 启用进程内 browser 工具 | `deps.py:216-219` |
| 调度器 | `scheduler.enabled=true` 但 `scheduler.multi_instance` 不为 true | `deps.py:212-214` |
| Sandbox 归属 | 显式 `sandbox.ownership.type: memory` | `deps.py:248-254` |
| IM 频道 | `channels.leader_lease.enabled: false` 且启用了非 GitHub 频道 | `deps.py:255-265` |

worker 计数的细节：先读 `GATEWAY_WORKERS`，再读 `WEB_CONCURRENCY`；空白值视为未设置，无法解析的值继续找下一个，最后才回落为 1（`deps.py:64-91`）。Compose 把 `GATEWAY_WORKERS` 作为 `uvicorn --workers` 传入（`docker/docker-compose.yaml:127-141`），而 `backend/Dockerfile` 与 `scripts/serve.sh` 不给 worker 数，此时 uvicorn 读 `WEB_CONCURRENCY`——两个都要读，否则多进程部署的闸门会保持惰性（`deps.py:64-70`）。

## 4. `channels.leader_lease`

默认 `auto`：只有看到多进程信号时才启用；单实例不写 lease 行（`backend/packages/harness/deerflow/config/channel_leader_lease_config.py:42-50,62-75`）。启用后每个 provider 在 `channel_leases` 表有一行，只有持有者连接平台；GitHub webhook 例外，仍在每个实例上（`channel_leader_lease_config.py:47-48`；`deploy/helm/deer-flow/values.yaml:35-39`）。租约默认 30 秒、宽限 10 秒，续租间隔为 `lease_seconds // 3`（`channel_leader_lease_config.py:51-59`），最坏接管时间为 `lease_seconds + grace_seconds` 再加一个续租间隔。

启动门在 `leader_lease.explicitly_disabled` 且存在非 GitHub IM 频道时直接拒绝（`deps.py:255-265`）；`auto` 跟随 `multi_process_deployment()`（`deps.py:267-276`），所以它和启动门用的是同一个信号，不会出现「门认为多实例、lease 却以为单实例」的分裂。

## 5. Redis stream bridge

作用是把每次 run 的 SSE 事件放到跨 Pod 可见的 Redis Streams，让客户端连到任一 Pod 都能收到实时事件并在重连时补放（`deploy/helm/deer-flow/values.yaml:266-271`；`values.yaml:426-432`）。类型选择在 `stream_bridge.type`；省略时若设置了 `DEER_FLOW_STREAM_BRIDGE_REDIS_URL` 就按 redis 处理（`backend/packages/harness/deerflow/runtime/stream_bridge/async_provider.py:29,32-46`），工厂再懒加载 `RedisStreamBridge`（`async_provider.py:78-94`）。

关键运行参数：每个 run 的 key 是 `deerflow:stream_bridge:<run_id>`（`runtime/stream_bridge/redis.py:216-217`）；`queue_maxsize` 对应 Redis `MAXLEN`，`stream_ttl_seconds` 是滚动 TTL（`config/stream_bridge_config.py:26-30,48-55`）；生产者租约 30 秒、每 10 秒续租（`redis.py:59-60`），`producer_lease_recovery_enabled` 默认关闭，必须等所有 writer 升级且旧 run 排空后再统一打开（`stream_bridge_config.py:65-68`）。捆绑 Redis 只有一个副本（`templates/redis-statefulset.yaml:16`）；要用外部 Redis 时设 `redis.enabled: false` 并配置 `redis.external`（`values.yaml:270-271,299-306`）。

## 6. `ExecutionFence`

`ExecutionFence(namespace, resource_id, holder_id, epoch)` 是 extension API 的「执行世代」句柄；宿主库里的 `extension_execution_leases` 以 `(namespace, resource_id)` 为复合键，另有 `user_id`、`holder_id`、`epoch`、`expires_at`（`backend/packages/extension-api/deerflow_extension_api/agent_runs.py:22-37`）。规则：每次 takeover 递增 epoch、保留 tombstone、获取时锁行；宿主在准入与取消事务内校验 user/holder/epoch/expiry（`agent_runs.py:29-37`）。字段在构造时做长度与 epoch 范围校验（`agent_runs.py:40-50`）。

它的诚实边界写在 docstring 里：fence 的是**新的准入/取消**，不是已准入 Agent 的任意外部副作用；fenced 调用要求 run ownership heartbeat，`start` 还额外要求跨进程 stream bridge（`agent_runs.py:27,36-37`）。示例用法见 `examples/deerflow-extension-workflows/deerflow_extension_workflows/cluster.py:21-24`；更完整的双写/脑裂讨论见 [security/06](../security/06-extension-boundary.md)。

## 7. 上线前最少核对

| 项 | 要求 | 证据 |
|---|---|---|
| 共享会话密钥 | 每个 Pod 用同一 `AUTH_JWT_SECRET`；否则并发启动会各写各的 `.jwt_secret` | `deploy/helm/deer-flow/templates/gateway-deployment.yaml:144-156` |
| 凭据加密键 | 启用 `channel_connections` 的多实例部署必须有共享 `DEER_FLOW_CREDENTIALS_KEY` | `gateway-deployment.yaml:159-166`；`values.yaml:340-348` |
| 共享 home | 多节点要 `persistence.home.accessMode: ReadWriteMany` | `values.yaml:41-42,314-318` |
| Agent catalog | 多副本要 `agent_storage.backend: db`，否则各 Pod 看到的自定义 agent 不同 | `values.yaml:42,444-454` |

## 阅读路径

1. **先跑**：`make dev-multi`，再 `make dev-multi-check`；先建立「两个 Gateway 共享一个库/Redis/home」的直觉（`Makefile:185-192`；`scripts/dev_multi_instance.py:685-692`）。
2. **再看 Helm**：读 `values.yaml:27-77,119-183` 的 replicas / multiInstance / Service / PDB，再看 `templates/gateway-deployment.yaml:188-193` 如何把副本数变成启动门信号。
3. **深入**：按 `deps.py:94-265` 的检查顺序读启动门，再看 `channel_leader_lease_config.py`、`stream_bridge/redis.py` 与 `agent_runs.py:22-37` 的运行语义。

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)（不修改源码、结论带 `file:line`、缺口写三态）。
- 治理取舍与成本判断不在本文展开，统一见 [governance/cost/04](../../enterprise-it-governance/cost/04-multi-instance.md)。

## 相关目录

- [deployment/](README.md) — 4 种部署模式与 Docker/Nginx 步骤；本文只补多实例运行语义。
- [security/](../security/README.md) — 认证、信任边界与 [06-extension-boundary](../security/06-extension-boundary.md) 的 ExecutionFence 全文。
- [governance/cost/04](../../enterprise-it-governance/cost/04-multi-instance.md) — 为什么声明、拒绝哪些配置、还有哪些治理缺口。
- [observability/02](../../observability/02-run-events-and-journal.md) 与 [07](../../observability/07-production-checklist.md) — run events 跨实例序列、上线检查。
- [channels/](../channels/README.md) — IM 频道与 leader lease 的上层行为。
