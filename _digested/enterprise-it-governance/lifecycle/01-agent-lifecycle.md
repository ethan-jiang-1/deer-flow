---
title: "Agent 生命周期"
description: "创建、配置热更新、停用删除。"
topics: [governance, lifecycle]
---

# Agent 生命周期

创建、配置热更新、停用删除。

## Agent 生命周期

### Agent 创建

| Agent 类型 | 创建方式 | 存储位置 |
|-----------|---------|---------|
| **Lead agent** | `langgraph.json` 注册 + `make_lead_agent()` | 代码 |
| **Custom agent** | `setup_agent` tool（bootstrap 模式） | `users/{user_id}/agents/{name}/` |
| **Subagent（内置）** | 代码（`bash_agent.py`, `general_purpose.py`） | 代码 |
| **Subagent（自定义）** | `config.yaml` → `subagents.custom_agents` | config.yaml |
| **ACP agent** | `config.yaml` → `acp_agents` | config.yaml |

### Agent 配置热更新

| 变更 | 生效方式 |
|------|---------|
| `config.yaml` 策略字段（model, tool, memory, prompt） | mtime 检测 → 下次请求 |
| `config.yaml` 基础设施字段（database, sandbox, channels） | **需要重启** |
| `extensions_config.json`（MCP, skills） | API 保存 + 立即生效 |
| Custom agent SOUL.md | `update_agent` tool → 下次交互 |
| Custom agent config.yaml | `update_agent` tool → 下次交互 |

