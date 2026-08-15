---
title: "直接利用：从配置到命令"
description: "不看原理，直接上手的实操层：日志到底落在哪、数据在哪、开什么、curl 什么、grep 什么。先回答'日志放哪'——不是 Workspace，是 stderr。"
topics: [observability, usage, logging, operations]
---

# 直接利用：从配置到命令

前面几篇讲原理，这篇只讲"我们怎么直接用"。先回答最关键的——**日志放哪**。

## 日志到底落在哪

**DeerFlow 自己的日志写到 stderr，不是 Workspace，也没有内置文件 sink。**

- `logging_config.py` 里 `_ensure_root_handler()` 只调 `logging.basicConfig(...)` —— 默认输出 **stderr**，没有写文件的 handler
- Docker 里被容器 runtime 捕获 → `docker logs` / journald
- **Workspace 不是放日志的地方**：`/mnt/user-data/workspace`（物理 `{DEER_FLOW_HOME}/users/{uid}/threads/{tid}/user-data/workspace/`）是 **agent 的工作目录**——agent 在这里 bash/read/write。把 operator 日志塞进去会：① 和 agent 工作文件混在一起；② 每个 thread 一份，不是单一运维日志；③ agent（或被 prompt-injection 的代码）能读改它

**最佳位置**：`stderr → 容器/编排层收集 → 集中日志系统`（Loki / ELK / CloudWatch / Splunk），并开 `logging.enhance`（JSON + `trace_id`）让聚合器能按 `trace_id` 索引。

> 若你坚持要落文件：在编排层重定向 stderr（docker/k8s 的日志驱动就是干这个的），或自己给 root logger 挂一个 `FileHandler`。DeerFlow 不内置文件 sink，这是有意为之——日志归属让部署层决定。

## 三处"日志"别混淆

| 概念 | 是什么 | 落在哪 |
|------|--------|--------|
| **app 日志** | Python `logging`（gateway/agent 框架） | stderr → 日志系统 |
| **run 事件** | `RunEventStore`（run.start / llm.* / run.error …） | DB 表 / JSONL / memory |
| **agent 文件** | agent 在沙箱里读写的文件 + tool 输出外部化 | thread `user-data/{workspace,outputs}` + `.tool-results/` |

排障时三条线都要能走：日志 grep `trace_id`、事件端点查 `run_id`、workspace 审查看 agent 到底改了哪些文件。完整磁盘清单见 [operations/backup-and-monitoring.md](../operations/backup-and-monitoring.md)。

## 最小接入清单（copy-paste）

```yaml
# config.yaml（logging 是 restart-required，改了要重启）
log_level: info
logging:
  enhance:
    enabled: true      # 日志带 trace_id、响应带 X-Trace-Id、Langfuse 带 deerflow_trace_id
    format: json       # 结构化，便于聚合器索引

database:
  backend: sqlite      # 单机；多实例用 postgres（Console + 持久事件依赖它）
```

```bash
# 环境变量（追踪，重启后生效）
export LANGFUSE_TRACING=true
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export DEER_FLOW_ENV=production          # 给 trace 打 env:production 标签
```

## 分场景命令

### 看运营大盘

```bash
curl -s http://localhost:8001/api/console/stats
# → {total_runs, active_runs, failed_runs, total_threads, total_agents, total_tokens, total_cost, currency}

curl -s "http://localhost:8001/api/console/runs?limit=20&status=failed"   # 失败 run 列表
curl -s "http://localhost:8001/api/console/usage?days=30"                 # 30 天每日成本 + per-model
```

### 查一次失败的 run

```bash
# 先拿 run_id（上面 runs?status=failed），再：
curl -s "http://localhost:8001/api/threads/{tid}/runs/{rid}/events?event_types=run.error,llm.error"
curl -s "http://localhost:8001/api/threads/{tid}/runs/{rid}/events?event_types=context:memory"   # memory identity
curl -s "http://localhost:8001/api/threads/{tid}/runs/{rid}/workspace-changes"                    # 改了哪些文件
```

### grep 日志按 trace_id

```bash
# 前端/响应头拿到的 X-Trace-Id，直接：
docker logs gateway 2>&1 | grep '<trace_id>'
# 或 json 格式下用 jq 过滤（看你的聚合器）
```

### 打包排查

```bash
make support-bundle   # 脱敏：配置 + 日志 + 系统信息 + AI issue draft + 可选 zip
```

## 排障决策树

```
出问题了
 ├─ 有用户可见报错？ → 拿 trace_id（X-Trace-Id）→ grep 日志 + Langfuse 按 deerflow_trace_id 过滤
 ├─ 某个 run 失败？   → /runs?status=failed 拿 run_id → /events 看 run.error / llm.error
 ├─ subagent 卡住？  → /events?task_id= 翻 subagent.step，看 stop_reason（token/turn/loop_capped）
 ├─ agent 改错文件？ → /workspace-changes 看 diff
 └─ 要甩锅给上游？   → make support-bundle
```

## 上线前最后三问

1. `database.backend` 是 sqlite/postgres 吗？（memory 会 503 Console，没历史）
2. `GATEWAY_WORKERS>1` 时 `run_events.backend: db` 了吗？（否则事件 seq 不跨进程）
3. `logging.enhance.enabled: true` 且 `DEER_FLOW_ENV` 设了吗？（否则日志/响应/追踪三处对不齐）
