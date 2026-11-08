---
title: "Integration — 集成参考"
description: "| 文件 | 内容 |"
type: index
---

# Integration — 集成参考

> 如何将 DeerFlow 接入你的应用。
>
> 涵盖源码：`app/gateway/routers/`（HTTP 面）、`app/channels/`（IM 通道）、`packages/harness/deerflow/integrations/`（托管集成）、`docker/`（部署栈）。基线 v2.2.0。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| `01-overview.md` | 总览：4 种集成手段对比 + 决策树 + 最小示例 |
| `02-api-reference.md` | 完整 HTTP API 端点详解 + SSE 流式协议 |
| `03-docker.md` | Docker 部署：compose 结构、5 个服务（redis/nginx/frontend/gateway/provisioner） |
| `04-im-channels.md` | IM 频道集成：9 个聊天平台（含 QQ）+ GitHub webhook 通道、总线/租约/凭据相关配置项 |
| `05-lark-cli-managed-integration.md` | Lark CLI 托管集成：安装事务/版本标记、每用户凭据切换、`sandbox_runtime_mode` 四态、Pattern A/B 与 broker 边界、v2.2.0 加固（原子发布/broker 模式 fail-closed/device-login 单飞） |
