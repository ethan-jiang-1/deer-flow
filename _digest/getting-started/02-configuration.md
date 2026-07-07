---
title: "配置接入概览"
description: "| 文件 | 用途 | 生成方式 |"
topics: [setup, configuration, quickstart]
---

# 配置接入概览

> 从接入/运维视角看 DeerFlow 的配置体系。字段级参考见 [configuration/ section](../getting-started/00-config-overview.md)。

## 两份配置文件

| 文件 | 用途 | 生成方式 |
|------|------|----------|
| `config.yaml` | 主配置（1100+ 行） | `make config` 从 `config.example.yaml` 生成 |
| `extensions_config.json` | MCP + Skills 启停 | 从 `extensions_config.example.json` 复制 |

## 配置解析优先级

1. 显式代码传参
2. 环境变量 `DEER_FLOW_CONFIG_PATH` / `DEER_FLOW_EXTENSIONS_CONFIG_PATH`
3. 当前目录 `./config.yaml`
4. 父目录 `../config.yaml`（项目根，**推荐**）

环境变量替换：`api_key: $OPENAI_API_KEY` → 自动读取环境变量。

## config.yaml 核心段

| 段 | 用途 | 需要重启？ |
|----|------|-----------|
| `config_version` | Schema 版本号，`make config-upgrade` 合并新字段 | — |
| `models` | LLM 模型列表，8 种 provider 适配器 | **否**（热加载） |
| `models[].use` | Provider 类路径，reflection 加载 | 否 |
| `tool_groups` | 工具分组（web/ file:read/ file:write/ bash） | 否 |
| `tools` | 内置工具 provider 列表（web_search/web_fetch/image_search/ls/bash 等） | 否 |
| `sandbox` | 沙箱实现选择（Local/Docker/K3s/BoxLite/E2B） | **是**（`sandbox.use`） |
| `sandbox.allow_host_bash` | 主机 bash 开关，默认 false | 否 |
| `subagents` | 子 Agent 超时/最大轮次/模型覆盖 | 否 |
| `acp_agents` | 外部 Agent 协议（Claude Code/Codex） | 否 |
| `summarization` | 上下文摘要触发条件 + 保留策略 | 否 |
| `memory` | 用户记忆存储 + 注入策略 | 否 |
| `database` | 持久化后端（memory/sqlite/postgres） | **是** |
| `guardrails` | 工具调用鉴权（Allowlist/OAP/自定义） | 否 |
| `circuit_breaker` | LLM 连续失败熔断 | 否 |
| `loop_detection` | Agent 死循环检测 + 频次限制 | 否 |
| `uploads` | 文件上传大小限制 + 文档自动转换 | 否 |
| `title` | 对话标题自动生成 | 否 |
| `log_level` | debug/info/warning/error | **是** |

## extensions_config.json 核心段

| 键 | 用途 |
|----|------|
| `mcpServers` | MCP 服务器注册（stdio/sse/http），含 OAuth 支持 |
| `mcpInterceptors` | MCP 连接认证拦截器 |
| `skills` | Skill 启用/禁用开关 |

运行时 API：`PUT /api/mcp/config`、`PUT /api/skills/{name}`。

## 接入关键决策

1. **模型选择** — `models[].use` 填 provider 类路径，Ollama 必须用 `langchain_ollama:ChatOllama`（OpenAI 兼容模式会丢失 thinking 内容）
2. **沙箱选择** — 开发用 Local，团队测试用 Docker，生产用 K3s Provisioner。macOS 自动优先 Apple Container
3. **web_search 只能有一个** — 多个 provider 按 config.yaml 顺序去重，先列出的生效
4. **Internal Token** — 模块加载时自动生成，多 worker 必须手动设为相同值
5. **数据库** — sqlite 单机够用，postgres 用于多 worker 生产

## 改后生效规则

| 无需重启（热加载） | 需重启 |
|---------------------|--------|
| models、summarization、title、memory、subagents、tools、system prompt、guardrails | database.backend、checkpointer、run_events、stream_bridge、sandbox.use、log_level、channels 凭证 |

## 完整参考

字段级配置手册见 [configuration/04-config-reference.md](../internals/configuration/04-config-reference.md)，设计原理见 [configuration/00-overview.md](../getting-started/00-config-overview.md)。
