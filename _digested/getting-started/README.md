---
title: "Getting Started — 安装、配置、首次运行"
description: "从零到第一次跑通：两套配置文件、本地与 Docker 启动、嵌入式 SDK 与终端 TUI。"
type: index
topics: [setup, configuration, quickstart]
---

# Getting Started — 安装、配置、首次运行

> **定位**：把仓库变成能对话的服务。回答「需要什么前提、改哪两套配置、用哪种方式启动、不启服务怎么调」——给第一次部署 DeerFlow 的开发者。
> **边界**：不做字段级配置参考（见 [internals/configuration](../internals/configuration/README.md)），不覆盖生产部署形态与运维（见 [enterprise-operations/deployment](../enterprise-operations/deployment/README.md)），也不讲上线后怎么观察（见 [observability](../observability/README.md)）。

## 阅读路径

1. **先看**：[01-quick-start.md](01-quick-start.md) — Python 3.12+ 前提与本地 / Docker 两条最快上手路径。
2. **再看**：[00-config-overview.md](00-config-overview.md) — `config.yaml` 与 `extensions_config.json` 各自的加载路径、缓存策略与热更新行为。
3. **深入**：[06-tui.md](06-tui.md) — `deerflow` 终端工作台：五种启动模式、18 条内置命令与别名、键位真值、流式与滚动语义。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-config-overview.md](00-config-overview.md) | 配置系统全景：两套文件、加载路径、缓存与热更新 | 概览 |
| [01-quick-start.md](01-quick-start.md) | 前提条件 + 本地 / Docker 启动 | 概览 |
| [02-configuration.md](02-configuration.md) | 配置接入：怎么生成、怎么读写（接入/运维视角） | 概览 |
| [03-python-sdk.md](03-python-sdk.md) | `DeerFlowClient` 嵌入式 SDK，不需要 HTTP 服务 | 深入 |
| [04-local-dev.md](04-local-dev.md) | `make dev`：Gateway + Frontend + Nginx 三服务拓扑 | 概览 |
| [05-environment.md](05-environment.md) | 环境变量全参考：来源、读取点、默认值（含 `DEER_FLOW_ENV_FILE`、`DEER_FLOW_MULTI_INSTANCE`、`DEER_FLOW_CREDENTIALS_KEY`） | 深入 |
| [06-tui.md](06-tui.md) | TUI 终端工作台：启动模式、命令全集、键位、持久化与输入历史 | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 配置以 `config.example.yaml` / `extensions_config.example.json` 为准；两个运行态文件 gitignored、可被 Gateway 编辑，绝不提交。

## 相关目录

- [overview/](../overview/README.md) — 先懂架构再动手：四层同心圆与请求流。
- [internals/configuration/](../internals/configuration/README.md) — `config.yaml` 全字段参考与 `extensions_config.json` 解析。
- [enterprise-operations/deployment/](../enterprise-operations/deployment/README.md) — Compose、Nginx 路由、K8s Provisioner。
- [configuration/01-config-yaml.md](../internals/configuration/01-config-yaml.md) — 模型配置详解（正文页）。
- [step-by-step-setup.md](../../_faq_on_digested/06_cli-and-sdd/step-by-step-setup.md) — 纯本地零 Docker 的一步步安装指南（问答区正文页）。
