---
title: "Overview — 全景图 + 架构概览"
description: "DeerFlow 是什么、怎么跑起来、请求怎么流转。入门第一站。"
type: index
---

# Overview — 全景图 + 架构概览

DeerFlow 是什么、怎么跑起来、请求怎么流转。入门第一站。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| `01-system-overview.md` | 同心圆四层架构：Agent Loop → Harness → Gateway → Access |
| `02-harness-app-boundary.md` | Harness / App 边界：CI 强制的 import 隔离 |
| `03-logical-architecture.md` | 逻辑结构图：四层同心圆 + Agent Loop + Middleware Chain |
| `04-component-architecture.md` | 组件结构图：进程拓扑 + 依赖关系 |
| `05-request-flow.md` | 完整请求生命周期：HTTP POST → SSE 返回 |
| `06-startup-flow.md` | 启动流程图：6 阶段从命令到 agent.astream |

SVG 文件在 `figures/` 下（10+ 张），浏览器打开渲染。颜色规范见 `figures/README.md`。
