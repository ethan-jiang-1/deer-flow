---
title: "部署与运维"
description: "配置热更新、健康检查、迁移、多实例声明。"
topics: [governance, cost]
---

# 部署与运维

配置热更新、健康检查、迁移、多实例声明。

## 部署与运维

### 配置热更新

| 类型 | 变更方式 | 生效时间 |
|------|---------|---------|
| 基础设施（database, sandbox, channels） | 编辑 config.yaml | **需要重启** |
| 策略（model, tool, memory, prompt） | 编辑 config.yaml | mtime 检测 → 下次请求 |
| MCP servers | `PUT /api/mcp/config` 或编辑 extensions_config.json | 立即 |
| Skills 开关 | `PUT /api/skills/{name}` 或编辑 extensions_config.json | 立即 |

### 健康检查

`GET /health` — Gateway 健康检查端点。不涉及 agent runtime 深度健康检测。

### 迁移

`persistence/migrations/` — Alembic-based 数据库 schema 迁移。支持 user isolation 迁移脚本 `scripts/migrate_user_isolation.py`。

### 缺失

- 无 Agent 级 SLO/error budget
- 无 Circuit breaker 级别的自动降级（LLMErrorHandlingMiddleware 有 per-call retry + circuit breaker，但无 agent 级熔断）
- 无 Chaos engineering 支持
- 无 Agent 灰度发布
