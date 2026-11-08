---
title: "Overview — 全景图 + 架构概览"
description: "DeerFlow 是什么、后端怎么分层、请求与启动怎么流转。入门第一站。"
type: index
topics: [architecture, system-overview, onboarding]
---

# Overview — 全景图 + 架构概览

> **定位**：整个知识库的入口。用 7 篇讲清「DeerFlow 是什么、怎么分层、一次请求怎么走完」，5 分钟拿到四层同心圆与进程拓扑，给第一次读源码的人。
> **边界**：不覆盖安装与配置（见 [getting-started](../getting-started/README.md)），不展开 Agent 内部循环与中间件链（见 [internals](../internals/README.md)）；设计理念只汇总一手证据、不做完整论证（07 是证据底稿）。

## 阅读路径

1. **先看**：[01-system-overview.md](01-system-overview.md) — 同心圆四层架构（Agent Loop → Harness → Gateway → Access）与进程拓扑，先建立整体图。
2. **再看**：[05-request-flow.md](05-request-flow.md) — 一次 `POST /api/threads/{id}/runs/stream` 从 HTTP 到 SSE 返回的完整生命周期。
3. **深入**：[07-design-philosophy-evidence.md](07-design-philosophy-evidence.md) — 任务执行、运行时边界、上下文分层、完成验证，以及 SDLC 门禁与多实例「声明 + 启动门 + 租约」三件套。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-system-overview.md](01-system-overview.md) | 系统全景：同心圆四层架构与进程拓扑 | 概览 |
| [02-harness-app-boundary.md](02-harness-app-boundary.md) | Harness / App 两层拆分：CI 强制的 import 隔离 | 深入 |
| [03-logical-architecture.md](03-logical-architecture.md) | 逻辑结构图：四层同心圆 + Agent Loop + Middleware Chain | 概览 |
| [04-component-architecture.md](04-component-architecture.md) | 组件结构图：进程、端口与依赖关系 | 概览 |
| [05-request-flow.md](05-request-flow.md) | 请求数据流：HTTP → Gateway → Agent → SSE | 深入 |
| [06-startup-flow.md](06-startup-flow.md) | 启动全流程：6 阶段从命令到 `agent.astream` | 深入 |
| [07-design-philosophy-evidence.md](07-design-philosophy-evidence.md) | 设计理念的源码证据：执行治理、SDLC、多实例三件套 | 深入 |
| [08-upstream-docs-map.md](08-upstream-docs-map.md) | `docs/`、`backend/docs/`、`frontend/src/content` 的证据地图与范围声明 | 概览 |

> 图示：`figures/` 下 10+ 张 SVG（四层同心圆、进程拓扑、启动时序、请求生命周期、sandbox 路径等），浏览器直接打开渲染；配色与绘制规范见 [figures/README.md](figures/README.md)。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 结论写正文、图做辅助；引用行号以当期工作树为准，上游演进后按 [_upstream-sync/SYNC.md](../_upstream-sync/SYNC.md) 复核。

## 相关目录

- [getting-started/](../getting-started/README.md) — 装起来、跑起来；读完架构想动手时去这里。
- [concepts/](../concepts/README.md) — 架构图上的抽象（Agent / Sandbox / Subagent / Memory）展开成专章。
- [internals/](../internals/README.md) — 机制层：Agent Loop、Middleware Chain、模型层、配置与运行时。
- [根 README](../README.md) — 全局阅读地图、时间预算与关键词检索表。
