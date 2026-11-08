---
title: "Overview 图库 — SVG 架构图索引"
description: "overview/ 的图目录索引：14 张自包含 SVG，覆盖同心圆分层、Agent Loop、进程拓扑、启动流程与请求路径。"
type: index
topics: [figures, svg, architecture]
---

# Overview 图库 — SVG 架构图索引

> **定位**：`overview/` 的图目录索引，回答「DeerFlow 的同心圆分层、Agent Loop、进程拓扑、启动与请求路径长什么样、该看哪张图」；给读 overview 正文的人按图索骥。
> **边界**：只存图与索引，不写论证；文字解释在 [overview 正文](../README.md) 各篇（01–07），其他目录的配图各自放在所在目录的 `figures/`。

## 阅读路径

1. **先看**：[agent-runtime-overview.svg](agent-runtime-overview.svg) — 四层同心圆总览，先建立分层直觉。
2. **再看**：[agent-loop.svg](agent-loop.svg) — Agent Loop 与 middleware 链，理解一轮请求怎么转。
3. **深入**：[request-lifecycle.svg](request-lifecycle.svg) — HTTP → Nginx → Auth → Pregel → SSE 的完整生命周期。

## 本篇目

| 文件 | 所属 | 内容 |
|---|---|---|
| [agent-runtime-overview.svg](agent-runtime-overview.svg) | [01-system-overview](../01-system-overview.md) | Agent Runtime 分层：中心引擎、Core Services、层层外扩 |
| [agent-loop.svg](agent-loop.svg) | [03-logical-architecture](../03-logical-architecture.md) | Agent Loop 核心循环与 middleware 链 |
| [agent-loop-core.svg](agent-loop-core.svg) | 未嵌入正文 | 内核：LangGraph 状态机 × 6 Hook 点 × 19 Middleware（图内口径） |
| [concentric-rings.svg](concentric-rings.svg) | [03-logical-architecture](../03-logical-architecture.md) | 四层同心圆：Access → Gateway → Harness → Core |
| [skills-loading.svg](skills-loading.svg) | [03-logical-architecture](../03-logical-architecture.md) | Skills 加载链：SKILL.md → load_skills → prompt → LLM |
| [subagent-delegation.svg](subagent-delegation.svg) | [03-logical-architecture](../03-logical-architecture.md) | Sub-agent 委派：Lead → Executor → 3 并行 subagent → 聚合 |
| [sandbox-paths.svg](sandbox-paths.svg) | [03-logical-architecture](../03-logical-architecture.md) | 虚拟路径映射与多层安全防护 |
| [harness-app-boundary.svg](harness-app-boundary.svg) | [02-harness-app-boundary](../02-harness-app-boundary.md)（未嵌入） | Harness / App 两层边界与依赖方向 |
| [process-topology.svg](process-topology.svg) | [04-component-architecture](../04-component-architecture.md) | 进程拓扑：Nginx / Gateway / Frontend / Provisioner 及端口 |
| [dependency-graph.svg](dependency-graph.svg) | [04-component-architecture](../04-component-architecture.md) | Harness 内部依赖关系图 |
| [gateway-lifespan.svg](gateway-lifespan.svg) | [06-startup-flow](../06-startup-flow.md) | Gateway 启动：module load → create_app → lifespan |
| [startup-sequence.svg](startup-sequence.svg) | [06-startup-flow](../06-startup-flow.md) | 四种启动入口对比 |
| [request-flow.svg](request-flow.svg) | [05-request-flow](../05-request-flow.md) | 请求数据流：HTTP/SSE → Agent Runtime 完整路径 |
| [request-lifecycle.svg](request-lifecycle.svg) | [06-startup-flow](../06-startup-flow.md) | HTTP → Nginx → Auth → stream_run → Pregel → SSE |

## 宪章与约定

- 本目录无独立宪章；命名与引用纪律沿用 [根 README](../../README.md)：小写连字符命名、SVG 自包含、浏览器直接打开。
- 配色约定沿用现有图：绿 = Access / 成功、蓝 = Gateway / API、橙 = Harness / 工具、紫 = 基础设施、红 = 安全 / 边界、灰 = 存储、青 = 模型层。

## 相关目录

- [overview/](../README.md) — 正文：系统总览、Harness/App 边界、逻辑与组件架构、请求与启动流程。
- [../../README.md](../../README.md) — 根索引：全部目录的阅读地图。
