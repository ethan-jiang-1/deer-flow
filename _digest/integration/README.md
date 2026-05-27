# DeerFlow 集成指南

> 如何将 DeerFlow 接入你的应用。这里是总入口，不堆内容，细节在各子文件中。

## 导航

| 文件 | 内容 |
|------|------|
| [01-quick-start.md](01-quick-start.md) | 快速启动：本地/Docker 两种方式，启动后验证 |
| [02-configuration.md](02-configuration.md) | 配置详解：`config.yaml` + `extensions_config.json` 所有段 |
| [03-api-reference.md](03-api-reference.md) | API 端点详解：全部路由、请求/响应格式、SSE 流式协议 |
| [04-python-sdk.md](04-python-sdk.md) | Python SDK：`DeerFlowClient` 嵌入模式，无需 HTTP |
| [05-docker.md](05-docker.md) | Docker 部署：compose 结构、4 个服务、环境变量 |
| [06-environment.md](06-environment.md) | 环境变量全参考：按类别排列，每个变量的作用 |
| [07-im-channels.md](07-im-channels.md) | IM 频道集成：7 个平台（飞书/Slack/Telegram/WeChat 等） |

## 三种接入路径

```
┌─────────────────────────────────────────────────────────┐
│  接入方式                  适合                          │
│  ─────────                ─────                         │
│  HTTP API (REST + SSE)    前端应用、外部系统              │
│  Python SDK (DeerFlowClient)  Python 应用嵌入            │
│  Docker Compose            生产/开发环境一键部署           │
│  IM Channels               飞书/Slack/Telegram 等        │
└─────────────────────────────────────────────────────────┘
```

## 先看哪个

- 想跑起来 → [01-quick-start.md](01-quick-start.md)
- 想理解配置 → [02-configuration.md](02-configuration.md)
- 想写代码接入 → [04-python-sdk.md](04-python-sdk.md) 或 [03-api-reference.md](03-api-reference.md)
- 想部署 → [05-docker.md](05-docker.md)
