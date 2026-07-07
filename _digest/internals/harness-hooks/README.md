---
title: "DeerFlow 配置钩子与插件机制全景"
description: "DeerFlow 没有文件系统 watcher（inotify/watchdog），也不依赖 WebSocket 推送。它靠的是**拉模式 + 多层传播 + 动态加载**的组合。"
type: index
---

# DeerFlow 配置钩子与插件机制全景

> **核心问题：用户更新配置后，DeerFlow 怎么"知道"并让改动生效？**

DeerFlow 没有文件系统 watcher（inotify/watchdog），也不依赖 WebSocket 推送。它靠的是**拉模式 + 多层传播 + 动态加载**的组合。

---

## 两大类别

| 类别 | 核心机制 | 触发方式 | 生效时机 |
|------|----------|----------|----------|
| **配置热重载** | mtime 比较 + 路径感知 + 单例推送链 | `get_app_config()` 每次被调用时检测 | 部分立即生效，部分需重启 |
| **插件/扩展** | Protocol 协议 + 反射动态加载 + @Next/@Prev 定位 | 用户写代码/改 JSON 配置 | 下一条消息 / 下次 agent 构建 |

---

## 文件导航

### 配置如何热生效

1. **[01-config-hot-reload.md](01-config-hot-reload.md)** — `get_app_config()` 的三步检测（ContextVar → custom → mtime），config_version 版本检查，路径解析链
2. **[02-singleton-propagation.md](02-singleton-propagation.md)** — AppConfig → 12 个子配置单例的推送链，哪些字段热生效、哪些必须重启，验证失败不污染旧配置
3. **[07-context-config-override.md](07-context-config-override.md)** — ContextVar 栈实现 per-request 配置隔离、测试注入、多租户路径

### 如何让自定义代码被加载

4. **[03-reflection-loading.md](03-reflection-loading.md)** — `resolve_variable` / `resolve_class`：任意 Python 模块路径 → 动态 import → 类型校验，是 6 种扩展机制的共同基础
5. **[04-agent-middleware-hooks.md](04-agent-middleware-hooks.md)** — Agent 生命周期的 6 种 Hook 点、3 种状态修改方式、定位系统 `@Next`/`@Prev`、`RuntimeFeatures` 三元开关
6. **[05-guardrail-plugin.md](05-guardrail-plugin.md)** — `GuardrailProvider` Protocol 协议栈、`fail_closed` 策略、动态加载
7. **[06-mcp-interceptors.md](06-mcp-interceptors.md)** — MCP 拦截器链、OAuth 注入、`extensions_config.json` 的 Gateway 写回 + LangGraph 读取管道
8. **[08-agent-self-modification.md](08-agent-self-modification.md)** — `update_agent_tool` / `setup_agent_tool`：agent 在对话中原子更新自己的 SOUL.md/config.yaml

---

## 全景数据流

```
用户修改 config.yaml
         │
         ▼
  ┌──────────────────────────────────────────────────┐
  │  get_app_config()                                │
  │  ├─ 1. ContextVar override? → 直接返回           │
  │  ├─ 2. custom override (set_app_config)? → 返回  │
  │  └─ 3. mtime 变了? / 路径变了?                    │
  │       └─ AppConfig.from_file()                   │
  │           ├─ 读 YAML                             │
  │           ├─ 版本检查 (config_version)            │
  │           ├─ resolve_env_variables ($VAR)         │
  │           ├─ _apply_singleton_configs()           │
  │           │  ├─ title_config 单例                │
  │           │  ├─ summarization_config 单例         │
  │           │  ├─ memory_config 单例               │
  │           │  ├─ guardrails_config 单例           │
  │           │  ├─ checkpointer_config → reset()?   │
  │           │  └─ ... 共 12 个                     │
  │           └─ 缓存 mtime + 结果                    │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────────────┐
  │  下一条消息到达时：                               │
  │  - Gateway deps → get_app_config() → 热字段已生效 │
  │  - middleware 链根据新 config 重新条件组装        │
  │  - 系统 prompt 重新生成（含新 memory/skills）     │
  │  - model 参数已更新                              │
  │                                                  │
  │  需要重启才能生效的：                             │
  │  - database.* (connection pool)                  │
  │  - checkpointer.* (persistent state)             │
  │  - sandbox.use (provider 单例)                   │
  │  - log_level (只在 startup 读)                   │
  │  - channels.* (IM 凭证)                         │
  └──────────────────────────────────────────────────┘
```

## 与已有笔记的关系

- `middleware/01-hooks-and-flow.md` — Agent 生命周期的 6 个 hook 点，这里是**面向中间件开发者**的详细 API。本目录 04 篇提供**面向用户**的视角：怎么把自己的 middleware 挂上去、怎么控制位置、怎么开关。
- `middleware/02-chain-assembly.md` — 链装配的 `@Next`/`@Prev` 定位系统。本目录 04 篇覆盖同样的机制但从 `extra_middleware` 注入和 `RuntimeFeatures` 的角度。
- `middleware/03-catalog.md` — 29 个 middleware 的逐个目录。本目录 04 篇提供架构层面的"怎么加第 20 个"。

## 关键设计原则

1. **拉模式，不推模式** — 没有 watcher。每次 `get_app_config()` 调用时比较 mtime。依赖 Gateway 的 request-time 调用链触发。
2. **失败安全** — 验证失败时 `_app_config` 不变，系统继续用旧配置，不会崩溃。
3. **原子传播** — `_apply_singleton_configs()` 先加载到临时对象，验证通过后才替换所有单例。checkpointer 变化时连带重置 store。
4. **动态加载** — 所有扩展（model, tool, sandbox, guardrail, MCP interceptor）都通过 `resolve_variable` 反射加载，不需要重新编译。
5. **定位透明** — `@Next(GuardrailMiddleware)` 清晰表达意图，不依赖隐式的 import 顺序或配置 key 顺序。
