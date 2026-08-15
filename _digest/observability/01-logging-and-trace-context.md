---
title: "日志体系与 trace_id 请求关联"
description: "DeerFlow 的日志是标准 Python logging + 一个可选的 trace 关联增强。logging.enhance 打开后，trace_id 同时进日志、HTTP 响应头、Langfuse metadata 三处，靠一个 ContextVar 串起来。"
topics: [logging, trace-id, observability, correlation]
---

# 日志体系与 trace_id 请求关联

DeerFlow 的日志本身是朴素的 Python `logging`，真正的价值在一个可选的 **trace 关联增强**：打开 `logging.enhance` 后，一次请求的 `trace_id` 会同时出现在日志、HTTP 响应头、Langfuse metadata 三处，靠一个 `ContextVar` 串起来——这是"出问题时从日志 grep 到同一次请求"的关键。

## 源文件

| 文件 | 职责 |
|------|------|
| `deerflow/logging_config.py` | 根 handler 装配：默认 formatter、trace filter、JSON/text formatter |
| `deerflow/trace_context.py` | `trace_id` 的 ContextVar 载体 + 生成/规范化/上下文管理器 |
| `app/gateway/trace_middleware.py` | `TraceMiddleware`：HTTP 请求级绑定 + 写响应头 |
| `deerflow/config/app_config.py` | `apply_logging_level()` / `is_trace_correlation_enabled()` |

## 默认行为（`logging.enhance.enabled: false`）

- 输出 stderr（`logging.basicConfig`），Docker 中被容器 runtime 捕获
- 格式：`%(asctime)s - %(name)s - %(levelname)s - %(message)s`（日期 `%Y-%m-%d %H:%M:%S`）
- 级别：`config.log_level`（默认 `info`），`apply_logging_level()` **只改 `deerflow` / `app` 两个 logger 层级**，不动第三方（uvicorn / sqlalchemy）；根 handler 的阈值只降不升，避免挡住第三方日志的既有阈值

> **日志落哪 / 最佳位置**：DeerFlow 无内置文件 sink，日志走 **stderr**（不是 Workspace，Workspace 是 agent 的工作目录）。生产上由编排层（docker/k8s）把 stderr 送进集中日志系统。见 [08-direct-usage.md](08-direct-usage.md)。

## 增强模式（`logging.enhance.enabled: true`）

打开后发生三件事，全部由同一个 `trace_id`（`deerflow.trace_context` 的 ContextVar）驱动：

1. **日志注入 `trace_id` 字段** — `TraceContextFilter` 在每个 log record 上设 `record.trace_id = get_current_trace_id() or "-"`
2. **HTTP 响应头 `X-Trace-Id`** — `TraceMiddleware` 在 `http.response.start` 写入，覆盖 SSE/流式响应（不消费 body）
3. **Langfuse metadata `deerflow_trace_id`** — `build_langfuse_trace_metadata()` 读同一个 ContextVar 注入

格式可选 `text` 或 `json`（`logging.enhance.format`）：

- **text**：`%(asctime)s - %(name)s - %(levelname)s - [trace_id=%(trace_id)s] - %(message)s`
- **json**（`JsonTraceFormatter`）：`{timestamp, logger, level, trace_id, message, exc_info?, stack_info?}`，`ensure_ascii=False`

## trace_id 的生成与规范化（`trace_context.py`）

- 生成：`uuid4().hex`（header-safe）
- `normalize_trace_id()` 只接受**可打印 ASCII**（0x20–0x7E）、非空、≤512 字符。拒绝 C0 控制符 / DEL / 高位码点，原因有二：**log-injection 防御** + **HTTP 响应头安全**（Starlette 用 latin-1 编码 header，码点 >0xFF 会 `UnicodeEncodeError` 触发 500；0x80–0x9F 会被 nginx/envoy 剥掉）
- 传入非法值 → 自动生成一个新 id，而不是报错

## 三层上下文管理器

| 函数 | 语义 |
|------|------|
| `request_trace_context(id)` | 绑定请求级 id；`None` → 生成新 id（Gateway 用） |
| `ensure_trace_context(id)` | `id` → 继承当前 → 生成新 id（嵌入式/入口点用） |
| `set_current_trace_id` / `reset` | 底层绑定/恢复（返回/接收 `Token`） |

## TraceMiddleware：启动快照，不是每请求热读

`logging` 是 **restart-required** 字段（`STARTUP_ONLY_FIELDS["logging"]`）。`configure_logging()` 只在 lifespan 启动时装 trace filter + formatter，`TraceMiddleware` 的 `enabled` 标志也在 `create_app()` 时快照一次。

> 为什么必须快照：如果每请求热读 `logging.enhance.enabled`，一个运行时的 `config.yaml` 编辑会让响应头 `X-Trace-Id` 和 Langfuse `deerflow_trace_id` **立即**出现，而日志 formatter 还停在启动值——三者不再一致。所以整个关联链靠"重启生效"来保证一致。

## trace_id 的来源优先级

`resolve_deerflow_trace_id(metadata_trace_id)` 决定一次 run 的有效 `deerflow_trace_id`：

1. **入站 `X-Trace-Id` 有效** → 用它（调用方既发 header 又发 metadata 时，header 赢）
2. **caller metadata `config.metadata.deerflow_trace_id`** → 用它
3. **环境请求 trace context** → 用它

## 嵌入式 / TUI / CLI 路径

`DeerFlowClient.stream()` 每个 turn 铸造（或继承）一个请求级 trace id——但只在 flag 打开时。flag 关时**不**铸造新 id，调用方仍可显式用 `request_trace_context(...)` 包住 `stream()` 选择 opt-in。因为 `stream()` 是同步生成器（共享调用方 context），绑定在每次 `next()` 前后 set/reset，而不是包住整个 `yield from`——避免 yield 之间泄漏到调用方 context、以及被遗弃生成器 GC 关闭时的跨 context 报错。

## 关联契约速查

| 落点 | 字段 | 开关 |
|------|------|------|
| 日志 | `trace_id`（text 或 json 字段） | `logging.enhance.enabled` |
| HTTP 响应头 | `X-Trace-Id` | 同上 |
| Langfuse | `deerflow_trace_id` | 同上 |

> `deerflow_trace_id` 是 DeerFlow 自己的关联键，**不是** Langfuse 原生 trace id，**也不是** run_id。subagent 执行日志里的短 `trace_id` 字段是另一回事，仅用于 subagent 日志/状态。

## 测试覆盖

| 测试文件 | 覆盖 |
|---------|------|
| `test_trace_context.py` | 规范化（ASCII 边界、长度、非法回退生成）、上下文管理器、来源优先级 |
| `test_client_langfuse_metadata.py` | `stream()` 不在 yield 之间泄漏 trace id、遗弃生成器不跨 context 报错 |

## 重要 logger 名称清单（要监听就盯这些）

DeerFlow 源码里 **217 处 `logging.getLogger(__name__)`，零处显式命名** —— 所以 logger 名 = 模块路径，你按**层级**监听，不用背全名。两条主 hierarchy 就是总开关。

### 两条主 hierarchy（`config.log_level` 只管这两个）

| logger | 覆盖 |
|--------|------|
| `deerflow` | harness 框架（agent / middleware / runtime / tracing / tools / sandbox …） |
| `app` | Gateway + IM 通道 |

`apply_logging_level()` 只调这两个层级（`info` 默认），**不碰**第三方（uvicorn / sqlalchemy / langchain / langgraph）。

### DeerFlow 关键子 logger（模块路径 = logger 名）

| logger 名 | 发什么 | 为什么盯 |
|-----------|--------|---------|
| `deerflow.agents.middlewares.sandbox_audit_middleware` | `[SandboxAudit]` 命令审计：info 记录、warning `BLOCKED` / `WARN` / `INVALID INPUT` | 安全审计 trail；guardrail 触发了什么 |
| `deerflow.agents.middlewares.llm_error_handling_middleware` | LLM 错误分类、重试、断路器状态 | 模型降级/重试雪崩 |
| `deerflow.agents.middlewares.loop_detection_middleware` | loop 检测告警 | agent 跑飞/打转 |
| `deerflow.runtime.runs.worker` | run 生命周期：`cancelled`、abort、orphan/takeover、subagent 事件落盘失败、stream modes | 多 worker 运维、run 状态排查 |
| `deerflow.runtime.journal` | RunJournal 回调→事件 | 事件流链路 |
| `deerflow.tracing.factory` | tracing callback 构建、provider 检测 | 追踪没起来的原因 |
| `deerflow.tracing.monocle` | Monocle OTel 初始化 | 第三个 provider |
| `deerflow.utils.custom_events` | 自定义事件分发（debug） | 你发的 `emit_custom_event` |
| `app.gateway.trace_middleware` | trace 中间件 | trace_id 绑定 |
| `app.gateway.routers.console` | Console API（pricing 解析失败等 warning） | 运营端点 |

### IM 通道（`app.channels.*`）

每个平台一个 logger：`app.channels.feishu` / `slack` / `telegram` / `dingtalk` / `discord` / `wechat` / `wecom` / `github` / `buzz`，加上 `app.channels.manager`（调度）、`message_bus`、`service`（生命周期）。

### LangGraph / LangChain 那边

| logger 名 | 是什么 | 备注 |
|-----------|--------|------|
| `langgraph` | LangGraph 运行时（显式 `getLogger("langgraph")`，在 `pregel/_log.py`） | 总开关 |
| `langgraph.pregel.*` / `langgraph.checkpoint.*` | 图执行 / checkpoint（`__name__` 层级） | 内部 loop、状态读写 |
| `langchain_core.callbacks.manager` | callback 分发（LangSmith tracer 挂这） | 追踪/回调事件 |
| `langchain_core.agents` | agent executor | agent 内部 |

> DeerFlow 的 `apply_logging_level()` **不调这些**，它们停在默认 `WARNING`。要看 LangGraph 内部 loop / checkpoint，得手动设。

### 怎么调单个 logger

```python
import logging
logging.getLogger("deerflow.agents.middlewares.sandbox_audit_middleware").setLevel(logging.DEBUG)  # 看每条命令
logging.getLogger("langgraph").setLevel(logging.DEBUG)   # 看 LangGraph 运行时
logging.getLogger("langchain_core.callbacks.manager").setLevel(logging.DEBUG)  # 看回调分发
```

生产上用日志系统的层级配置（docker/k8s 的日志驱动 + 聚合器的 logger 过滤）来做，而不是在代码里写死。

## 示例：把全部日志收进一个文件

DeerFlow 默认只写 stderr、没有文件 sink。要"全量收进一个文件、出事了知道怎么找"，两条路。这里直接从源码给结论，不用上网查。

### 路 A（推荐，生产）：stderr → 容器日志驱动 → 一个文件

```yaml
# config.yaml
log_level: info
logging:
  enhance:
    enabled: true
    format: json      # 每条日志带 trace_id，结构化
```

```yaml
# docker-compose.yml（gateway 服务）—— 容器 runtime 把 stderr 收进文件
logging:
  driver: json-file
  options:
    max-size: "100m"
    max-file: "5"
```

`docker logs gateway > deerflow.log`，或让编排层把 stderr 送进集中日志系统（Loki/ELK/CloudWatch）。这是 DeerFlow 设计的方式——**日志归属让部署层决定**。

### 路 B（Python logging 机制）：挂一个 handler 到 root = 全收

Python logging 的关键是 **propagation（传播）**：每个 logger（`deerflow.runtime.worker`、`langchain_core.callbacks.manager`…）默认 `propagate=True`，它产出的每条记录会一路向上传给所有祖先的 handler，最终到 root。DeerFlow / LangChain / LangGraph 全都用 `getLogger(...)` 挂在同一棵树上，**所以只要在 root 挂一个 handler，就能收到底下所有库登记的内容**。

最小例子：

```python
import logging

root = logging.getLogger()               # root logger，所有 logger 的祖先

handler = logging.FileHandler("deerflow.log")
handler.setLevel(logging.DEBUG)          # handler 层：什么级别都收
handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
root.addHandler(handler)                 # ← 挂上去，全收

root.setLevel(logging.DEBUG)             # 关键 1：root 级别也要降，否则先被 root 拦掉
# 关键 2：光降 root 不够——每个库 logger 有自己的 level（LangChain/LangGraph 默认 WARNING），
#   DEBUG 记录在"到达 root 之前"就会被它们自己的 logger 拦掉，所以要一并降
for name in ("deerflow", "app", "langchain_core", "langgraph"):
    logging.getLogger(name).setLevel(logging.DEBUG)
```

**⚠️ 三个坑（第一个最容易忘）：**

1. **`logging.basicConfig(filename=...)` 是 no-op** —— 它只在 root **还没有任何 handler** 时生效。DeerFlow 启动时 `configure_logging()` 已经 `basicConfig(...)` 给 root 挂了 stderr handler，所以你**再调 `basicConfig` 不会加文件**。正确做法是上面的 `root.addHandler(...)`。
2. **级别在 logger 层就被拦** —— 一条 DEBUG 记录要先过 `deerflow`/`langgraph` 等 logger 的 level，才能 propagate 到 root。只设 root 级别，抓不到库内部的 DEBUG。
3. **`dictConfig` 默认 `disable_existing_loggers=True`** —— 会把配置里没点名的老 logger 全禁掉。用 `dictConfig` 一定要 `disable_existing_loggers: False`。

**正规写法（`dictConfig`，带旋转 + trace_id + JSON）**：

```python
import logging.config

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,          # 坑 3
    "filters": {"trace": {"()": "deerflow.logging_config.TraceContextFilter"}},
    "formatters": {"json": {"()": "deerflow.logging_config.JsonTraceFormatter"}},
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "deerflow.log", "maxBytes": 50_000_000, "backupCount": 5,
            "encoding": "utf-8", "level": "DEBUG",
            "formatter": "json", "filters": ["trace"],
        },
    },
    "root": {"handlers": ["file"], "level": "DEBUG"},
    "loggers": {
        "deerflow": {"level": "DEBUG"},
        "app": {"level": "DEBUG"},
        "langgraph": {"level": "DEBUG"},
        "langchain_core": {"level": "DEBUG"},
    },
})
```

`JsonTraceFormatter` + `TraceContextFilter` 就是 DeerFlow `logging.enhance` 内部用的类，手动挂等于把 `trace_id` 带进文件。`langgraph`/`langchain_core` 全开 DEBUG 会非常啰嗦，生产按需。

### 出了事怎么找

1. 拿到 `trace_id`（前端响应头 `X-Trace-Id`，或报错时间点附近的日志）
2. `grep '"trace_id": "<id>"' deerflow.log` → 一条线串起整个请求（日志 + 响应头 + Langfuse 三处同一个 id）
3. 没有 trace_id 时按 `"level": "ERROR"` / `[SandboxAudit]` / 上面的 logger 名过滤
