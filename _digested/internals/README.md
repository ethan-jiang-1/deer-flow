---
title: "Internals — 内部机制深入"
description: "当你要理解「它为什么这样工作」而不是「怎么用它」时，来这里：Agent Loop、Middleware、Model Layer、Config、Runtime、MCP、持久化与 2.2 新子系统的源码级契约。"
type: index
topics: [internals, architecture, agent-runtime, contracts]
---

# Internals — 内部机制深入

> **定位**：`_digested/` 的源码级机制层，13 个子目录按机制切分，回答「这条机制为什么这样设计、契约落在哪个文件、改它要动哪里」，给要读源码或写扩展的开发者。
> **边界**：不覆盖上手与用法（[getting-started](../getting-started/README.md)、[concepts](../concepts/README.md)）；不覆盖部署、安全与合规（[enterprise-operations](../enterprise-operations/README.md)）；不覆盖测试策略（[testing](../testing/README.md)、[test-strategy](../test-strategy/README.md)）。

## 阅读路径

1. **先看**：[agent-loop/README.md](agent-loop/README.md) — 先弄清 loop 在哪里、middleware 怎样长进 loop。
2. **再看**：[middleware/00-overview.md](middleware/00-overview.md) — 一次 model/tool 调用究竟穿过哪些 hook。
3. **深入**：[runtime/README.md](runtime/README.md) — 自建运行时如何把图执行、事件流与日志接成一条管道。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [shared-utils-contract.md](shared-utils-contract.md) | `deerflow/utils/` 被多域依赖的不变量：事件双发、文件/装配线程池、消息身份、thread_id、图外 oneshot LLM | 深入 |
| [authz/README.md](authz/README.md) | `authz/` 的三块契约：RBAC 默认 allow、plugin principal fail-closed、sandbox:execute 复用前重查 | 深入 |
| [agent-loop/README.md](agent-loop/README.md) | Agent loop 归属、middleware 即结构、扩展点、代码追踪、错误处理 | 概览 |
| [capabilities/README.md](capabilities/README.md) | 声明式能力目录：清单、adapter、installation identity、MCP 选择 | 概览 |
| [configuration/README.md](configuration/README.md) | 两套配置文件、字段参考、动态加载、上下文压缩 | 概览 |
| [harness-hooks/README.md](harness-hooks/README.md) | 配置热重载、单例传播、反射加载、插件与打包扩展 | 概览 |
| [knowledge/README.md](knowledge/README.md) | provider 中立的只读检索契约：能力位、证据、预算、失败策略 | 概览 |
| [mcp/README.md](mcp/README.md) | MCP 会话池、OAuth、缓存失效、个人连接与 durable task | 概览 |
| [middleware/README.md](middleware/README.md) | 39 个 middleware 条目、6 种 hook、链装配与目录 | 概览 |
| [model-layer/README.md](model-layer/README.md) | `create_chat_model()` 工厂、thinking/vision、streaming、托管模型 | 概览 |
| [openai-decisions/README.md](openai-decisions/README.md) | 第二个决策后端：只拥有线协议，传输继承 typesafe | 概览 |
| [persistence/README.md](persistence/README.md) | DB/Checkpointer/Store 三后端、full/delta 双模式与历史缓存 | 概览 |
| [runtime/README.md](runtime/README.md) | RunManager、StreamBridge、序列化、RunJournal、归属与 goal 续跑 | 概览 |
| [storage/README.md](storage/README.md) | 内容寻址 blob 存储：契约、local_fs 后端、producer | 概览 |
| [typesafe/README.md](typesafe/README.md) | 共用判定客户端：一套传输、多个适配器、相反失败方向 | 概览 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。各子目录若有包内 `AGENTS.md`，在各自 README 的「宪章与约定」里链接。

## 相关目录

- [根 README](../README.md) — 全库入口与按阶段选择的阅读地图。
- [overview](../overview/README.md) — 先看全景与架构，再进机制细节。
- [concepts](../concepts/README.md) — 概念解释层；本目录是它的源码级下钻。
- [observability](../observability/README.md) — 事件流、日志与追踪的观测视角（runtime 的姊妹面）。
- [enterprise-operations](../enterprise-operations/README.md) — 安全、部署与运维的实现视角。
