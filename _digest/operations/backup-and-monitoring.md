---
title: "备份恢复与监控"
description: "生产数据备份策略、恢复流程、性能监控（Console API、LangFuse、token 追踪）。"
topics: [backup, restore, monitoring, observability, production]
---

# 备份恢复与监控

## 数据存储清单

| 数据 | 位置 | 格式 |
|------|------|------|
| 对话状态 | `.deer-flow/data/deerflow.db`（SQLite）或 PostgreSQL | SQL |
| Run 记录 | 同上 | SQL |
| 用户账户 | 同上 | SQL |
| 记忆 | `.deer-flow/users/{uid}/memory.json` | JSON 文件 |
| 上传文件 | `.deer-flow/users/{uid}/threads/{tid}/user-data/` | 文件系统 |
| Agent 配置 | `.deer-flow/users/{uid}/agents/{name}/` | Markdown + YAML |
| Skills | `skills/custom/` | Markdown 文件 |
| 配置 | `config.yaml`, `extensions_config.json` | YAML/JSON |

## 备份

### SQLite（单节点）

```bash
# 在线备份（WAL 模式下安全）
sqlite3 .deer-flow/data/deerflow.db ".backup deerflow-$(date +%Y%m%d).bak"

# 或直接 cp（WAL 模式下安全，会自动 checkpoint）
cp .deer-flow/data/deerflow.db deerflow-backup-$(date +%Y%m%d).db
```

### PostgreSQL

```bash
pg_dump -Fc deerflow > deerflow-$(date +%Y%m%d).dump
```

### 文件数据

```bash
tar czf deerflow-files-$(date +%Y%m%d).tar.gz \
  .deer-flow/users/ \
  config.yaml \
  extensions_config.json \
  skills/custom/
```

### 综合脚本

```bash
#!/bin/bash
DATE=$(date +%Y%m%d-%H%M)
BACKUP_DIR=/backup/deerflow/$DATE
mkdir -p $BACKUP_DIR

# SQLite
sqlite3 .deer-flow/data/deerflow.db ".backup $BACKUP_DIR/deerflow.db"

# 文件
tar czf $BACKUP_DIR/files.tar.gz .deer-flow/users/ config.yaml extensions_config.json skills/custom/

echo "Backup: $BACKUP_DIR"
```

## 恢复

### SQLite

```bash
# 停止 Gateway，替换文件
cp /backup/deerflow/20260707-1200/deerflow.db .deer-flow/data/deerflow.db
# 重启
make dev
```

### PostgreSQL

```bash
pg_restore -d deerflow --clean /backup/deerflow/20260707-1200/deerflow.dump
```

### 文件数据

```bash
tar xzf /backup/deerflow/20260707-1200/files.tar.gz -C /
```

## 监控

### Console API

需要 `database.backend: sqlite` 或 `postgres`（memory 返回 503）：

```bash
# 总体统计
curl http://localhost:8001/api/console/stats
# → {total_runs, active_runs, failed_runs, total_threads, total_agents, total_tokens, total_cost}

# 运行列表（分页）
curl "http://localhost:8001/api/console/runs?limit=20&status=failed"

# 每日 token 用量（90 天窗口）
curl "http://localhost:8001/api/console/usage"
```

### 费用追踪

需要在 `config.yaml` 中配置模型定价：

```yaml
models:
  - name: gpt-4o
    pricing:
      currency: USD
      input_per_million: 2.50
      output_per_million: 10.00
      input_cache_hit_per_million: 1.25
```

配置后 Console API 自动计算每次 run 的成本。

### LangFuse 集成

```bash
export LANGFUSE_TRACING=true
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

提供：调用链追踪、token 成本、延迟分布、session 回放。

### Token 追踪

每次 run 的 `end` SSE 事件携带累积用量。`GET /api/threads/{id}/token-usage` 返回 per-model 和 per-caller（lead/subagent/middleware）细分。

### RunJournal 延迟

`RunJournal` 记录每个 LLM 调用的延迟（`on_chat_model_start` → `on_llm_end`）。数据可通过 `GET /api/console/runs` 获取，每个 run 包含 `duration_seconds`。

### 告警

DeerFlow 没有内置告警。建议：
- 在 LangFuse 中配置 cost/latency threshold 告警
- 用 `GET /api/console/stats` 做 cron 健康检查（`active_runs` 持续 > 0 可能是卡住）
- 配置 `circuit_breaker` 防止 LLM 错误雪崩
