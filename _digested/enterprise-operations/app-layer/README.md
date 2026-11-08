---
title: "App Layer — 应用层"
description: "Gateway 应用层：41 个 router / 221 条端点、认证挂载、上传安全管道与 agent 包导入导出。"
type: index
topics: [gateway, api, upload, agent-package]
---

# App Layer — 应用层

> **定位**：FastAPI Gateway 的实现面——lifespan 启动、认证与权限入口、端点挂载顺序、上传安全、agent 包交换。给改后端与对接 REST API 的工程师看。同步基线 v2.2.0（`58fc5bd5b`）。
> **边界**：从调用方视角看 API 与 SSE 协议见 [integration/02-api-reference.md](../integration/02-api-reference.md)；上线加固见 [security/](../security/README.md)。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 网关架构、lifespan、认证系统、探针与 router 挂载顺序。
2. **再看**：[01-api-reference.md](01-api-reference.md) — 221 条端点穷举、「领域异常 → HTTP 映射」与状态码矩阵。
3. **深入**：[03-agent-package.md](03-agent-package.md) — `deerflow.custom-agent` v1 交换文档与导入的四道门。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 网关架构全景、认证、探针与 router 挂载 | 概览 |
| [01-api-reference.md](01-api-reference.md) | 221 条 REST 端点与异常/状态码映射 | 深入 |
| [02-upload-security.md](02-upload-security.md) | 上传安全管道：预留名、`O_EXCL` 提交、staging 清扫 | 深入 |
| [03-agent-package.md](03-agent-package.md) | Agent 包导入/导出与 owner-scoped create-only | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)。
- 版本基线：v2.2.0（`58fc5bd5b`，上一基线 v2.1.0 = `345f08be`）。

## 相关目录

- [Enterprise Operations 总览](../README.md) — 部署、安全、追踪与通道全景。
- [Integration](../integration/README.md) — 面向接入方的 API / Docker / IM 配置。
- [安全与信任边界](../security/README.md) — 认证与信任链的实施细节。
- [根 README](../../README.md) — 全库阅读地图与 README 约定。
- [企业 IT 治理卷](../../enterprise-it-governance/README.md) — 认证与权限的控制点判断。
- [部署架构](../deployment/README.md) — Gateway 在 compose 拓扑中的位置。
