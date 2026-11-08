---
title: "DeerFlow 配置钩子与插件机制全景"
description: "用户更新配置后 DeerFlow 怎么「知道」并让改动生效：没有文件系统 watcher，靠拉模式 + 多层传播 + 反射动态加载；外加 9 类扩展机制的接入口。"
type: index
topics: [hooks, hot-reload, reflection-loading, extensions]
---

# DeerFlow 配置钩子与插件机制全景

> **定位**：面向「想改配置或挂自定义代码」的读者，回答两件事：配置改完谁去检测、哪些立即生效；扩展代码通过什么协议/反射/定位系统被加载。
> **边界**：不逐个讲 middleware 实现（去 [../middleware/](../middleware/README.md)）；不展开每个配置字段（去 [../configuration/04-config-reference.md](../configuration/04-config-reference.md)）；打包扩展的运行契约在 [09](09-packaged-extensions.md)。

## 阅读路径

1. **先看**：[01-config-hot-reload.md](01-config-hot-reload.md) — `get_app_config()` 的三步检测与路径解析链。
2. **再看**：[03-reflection-loading.md](03-reflection-loading.md) — `resolve_variable` / `resolve_class`，6 种扩展机制的共同底座。
3. **深入**：[09-packaged-extensions.md](09-packaged-extensions.md) — 打包扩展的 9 个注册方法、CLI 事务与信任边界。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-config-hot-reload.md](01-config-hot-reload.md) | ContextVar → custom → mtime 三步检测、`config_version` 版本检查、路径感知 | 概览 |
| [02-singleton-propagation.md](02-singleton-propagation.md) | AppConfig → 12 个子配置单例（title / summarization / memory / guardrails / checkpointer…）的原子推送链、热/冷字段、失败不污染旧配置 | 概览 |
| [03-reflection-loading.md](03-reflection-loading.md) | 任意 Python 模块路径 → 动态 import → 类型校验 | 深入 |
| [04-agent-middleware-hooks.md](04-agent-middleware-hooks.md) | 6 种 hook、3 种状态修改方式、`@Next`/`@Prev`、`RuntimeFeatures` 三元开关 | 深入 |
| [05-guardrail-plugin.md](05-guardrail-plugin.md) | `GuardrailProvider` Protocol、`fail_closed` 策略、动态加载 | 深入 |
| [06-mcp-interceptors.md](06-mcp-interceptors.md) | MCP 拦截器链、OAuth 注入、Gateway 写回与读取管道 | 深入 |
| [07-context-config-override.md](07-context-config-override.md) | ContextVar 栈：per-request 隔离、测试注入、多租户路径 | 深入 |
| [08-agent-self-modification.md](08-agent-self-modification.md) | `update_agent_tool` / `setup_agent_tool`：对话中原子更新 SOUL.md / config.yaml | 深入 |
| [09-packaged-extensions.md](09-packaged-extensions.md) | 9 个注册方法、`deerflow extensions` CLI、manager 事务与锁、信任边界 | 深入 |
| [10-extension-examples.md](10-extension-examples.md) | 14 个 `examples/deerflow-extension-*` 包的贡献点/测试/入口地图 | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。打包扩展的成文契约见 [09](09-packaged-extensions.md) 与 [backend/packages/harness/deerflow/extensions/AGENTS.md](../../../backend/packages/harness/deerflow/extensions/AGENTS.md)。

## 相关目录

- [internals 父级](../README.md) — 13 个内部机制子目录的总入口。
- [configuration](../configuration/README.md) — 配置字段与动态加载的用户视角。
- [middleware](../middleware/README.md) — hook 点的执行流与 39 个条目。
- [capabilities](../capabilities/README.md) — 声明式能力目录与安装身份。
- [扩展边界](../../enterprise-operations/security/06-extension-boundary.md) — 第三方代码的信任模型。

## 速览

- **没有 watcher**：不依赖 inotify/watchdog/WebSocket，靠每次 `get_app_config()` 比较 mtime；改动由请求链自然触发。
- **原子传播**：`_apply_singleton_configs()` 先装进临时对象，验证通过才统一替换 12 个单例；失败保留旧配置。
- **必须重启的类别**：`database.*`、`checkpointer.*`、`sandbox.use`、`log_level`、`channels.*`（完整表在 [02](02-singleton-propagation.md)）。
- **一个底座六种用法**：model / tool / sandbox / guardrail / MCP interceptor / extension 全部经 `resolve_variable` 反射加载，无需重编译。
- **定位透明**：`@Next(GuardrailMiddleware)` 表达意图，不依赖 import 顺序或配置 key 顺序。
