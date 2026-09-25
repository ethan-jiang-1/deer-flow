---
title: "共享 Utils 契约"
description: "`backend/packages/harness/deerflow/utils/` 里被多处 import、因而必须当作契约的不变量：事件双发、文件/装配线程池与 ContextVar、消息身份、thread_id 规则、端口分配、图外 LLM 调用、outline 解析边界。"
topics: [internals, utils, contract]
---

# 共享 Utils 契约

`backend/packages/harness/deerflow/utils/`（v2.1.0 实测，13 个模块）大多是一次性小工具，但有若干模块被多个子系统 import：**改它们的语义等于改所有调用方的语义**，所以这里只记非琐碎契约，不抄函数体。

| 模块 | 引用它的文件数（`grep -rl 'deerflow.utils.<mod>'` over `packages/harness/deerflow` + `app`，排除 `utils/` 自身） | 是否契约级 |
|------|------|------|
| `thread_id.py` | 23 | ✅ |
| `time.py` | 22 | 部分（`coerce_iso` 线格式） |
| `messages.py` | 18 | ✅ |
| `file_io.py` | 12 | ✅ |
| `llm_text.py` | 5 | ✅（think 块裁剪语义） |
| `assembly_io.py` | 4 | ✅ |
| `custom_events.py` | 3 | ✅ |
| `text_detection.py` | 3 | ✅（MIME 安全判定） |
| `file_conversion.py` | 3 | 部分（转换器回退策略） |
| `readability.py` | 3 | 部分（base URL 解析） |
| `file_outline.py` | 2 | ✅ |
| `oneshot_llm.py` | 2 | ✅ |
| `network.py` | 1（`aio_sandbox/local_backend.py`，每次起本地 sandbox 都走） | ✅ |

---

## 1. `custom_events.py` — 事件"双发"不变量

```python
def emit_custom_event(payload, *, writer) -> None      # 同步
async def aemit_custom_event(payload, *, writer) -> None  # 异步图钩子必须用这个
```

三条不可破坏的顺序/容错规则（`custom_events.py:25-57`）：

1. **writer 先跑、且是权威路径**。`writer(payload)` 是第一条语句（`:33`、`:48`）；Gateway / Web UI / embedded client 的可见性只依赖它。
2. **callback 派发是 best-effort 的第二步**。只有 `payload["type"]` 是**非空字符串**时才继续（`_event_name`，`:17-22`）；否则只留 writer，`astream_events(version="v2")` 消费者看不到这条事件。这个"带类型的 payload 才会被双发"就是 AGENTS.md 写死的 custom-event invariant——**typeless payload 保持 writer-only**。
3. **`GraphBubbleUp` 必须原样抛**（`:39-40`、`:54-55`），其余异常吞掉只记 debug（`:41-42`、`:56-57`）。否则一个可选的事件消费者能中断既有 run，或把 LangGraph 的内部控制流（interrupt/pause）吞掉。

调用方：`tools/builtins/task_tool.py`（8 处 **`aemit_custom_event`**，异步版）、`agents/middlewares/safety_finish_reason_middleware.py:268,291` 与 `agents/middlewares/llm_error_handling_middleware.py:758,779`（这两处 middleware 走**同步 `emit_custom_event`**）。

> 迁移纪律：不要直接拿 `StreamWriter` 单发内置事件；异步图钩子不要在有 running loop 时调用同步版（`langchain_core.callbacks.dispatch_custom_event` 在 loop 里会炸）。

---

## 2. `file_io.py` — 文件专用池 + ContextVar 保留 + 取消排空

### `run_file_io(func, /, *args, **kwargs)`（`:41-52`）

- 跑在**专用** `ThreadPoolExecutor`（`thread_name_prefix="file-io"`，`:31`），不是 loop 默认 executor；默认 `min(32, cpu+4)`，可用 `DEER_FLOW_FILE_IO_WORKERS` 覆盖（非法值告警后回落，`:18-28`）。`atexit` 时 `shutdown(wait=False, cancel_futures=True)`（`:34-38`）。
- **ContextVar 必须显式拷贝**：`ctx = contextvars.copy_context()`，然后 `loop.run_in_executor(_FILE_IO_EXECUTOR, ctx.run, call)`（`:50-52`）。`asyncio.to_thread` 会自动拷贝 context，裸 `run_in_executor` **不会**——不拷的话 `get_effective_user_id()` 这类用户域 helper 在 worker 线程里读到空值。这是该模块存在的核心理由，任何"简化成 to_thread"的改动都必须同时接受默认池被阻塞的风险。

### `await_drained(coro)`（`:55-82`）

"被取消也要把内层跑完再抛"的契约：`asyncio.ensure_future` + `asyncio.shield`；`CancelledError` 落到 `while not task.done(): await asyncio.wait({task})` 并**吞掉重复取消**，内层结束后先 `task.exception()` 取回异常（避免 "exception never retrieved" 噪声），再重新抛取消（`:69-82`）。

为什么必须如此：持锁的 DB 事务 await 文件 offload 时，若取消 `await`，被放弃的是 await 而不是 worker 线程——行锁会在 worker 仍在删文件时释放（取消的 purge 回滚解锁，而 unlink worker 仍在跑，并发 restore 可能读到即将被删的字节）。唯一现调用方：`persistence/projects/sql.py`。

---

## 3. `assembly_io.py` — 装配专用池（与 `file_io` 同构、多两个不变量）

`run_assembly(...)`（`:50-122`）把"会阻塞的事件循环工作"（tool/agent assembly 会重入 `get_available_tools()`，可能卡在整个 MCP discovery 时长上）挡在 loop 默认 executor 之外：

- 默认 **8** worker，`DEER_FLOW_ASSEMBLY_WORKERS` 可覆盖（`:18-32`）。与 `utils/file_io.py`、`tools/sync.py` 同一模式，**刻意独立成池**：把装配塞进 loop 默认池会让几个卡住的装配挡住所有其它 `asyncio.to_thread` 调用方。
- ContextVar 同样显式 `copy_context()`（`:85-86`），供 `bind_agent_build_extensions` 等装配期 helper 在 worker 里用。
- **饱和告警**：pending 计数 `> _ASSEMBLY_WORKERS` 且距上次告警超过 30s 时 warning（`:37-40,69-83`）——卡死的 MCP server 会让后续装配无限排队但 loop 看起来健康，没有这条日志就完全不可见。
- **计数归属在"派发出去的工作项"上，不在 asyncio future 上**（`:88-99`）：`_work()` 的 `finally` 里递减。理由是提交方 loop 若在 worker 还在跑时关闭，future 永不 resolve，挂 future 回调会让计数永久上涨并伪造 starvation。
- 两个补偿路径必须都在：`executor.submit` 抛异常时手动回退刚占的槽（`:101-108`）；提交后立刻被 cancel 的作业由 `add_done_callback` 精确释放一次（`future.cancelled()` 为真 ⟺ `_work` 没跑过，`:110-121`）。
- 最终 `await asyncio.wrap_future(executor_future, loop=loop)`（`:122`）。

---

## 4. `messages.py` — 消息身份与"模型文本 ≠ 展示文本"契约

四个跨模块常量（`:9-27`）：`ORIGINAL_USER_CONTENT_KEY`、`SUMMARY_MESSAGE_NAME`、`UNTRUSTED_INPUT_KEY`、`INJECTED_USER_MESSAGE_ID_SUFFIX`。

- **`INJECTED_USER_MESSAGE_ID_SUFFIX = "__user"`**（`:27`）。`DynamicContextMiddleware` 做 ID 交换：真用户消息拿 `{id}__user`，提醒 SystemMessage 拿原 id，好让 `add_messages` **原地替换**。由此派生两条规则：`is_real_user_message`/注入逻辑会把带 `__user` 的消息当作"非注入目标"；而**重放持久化的用户轮次必须剥掉该后缀**——`strip_injected_user_message_id_suffix()`（`:30-41`）就是为了重放时补回日期/记忆块，否则 replay 静默丢掉当轮注入。常量放在这个 utils 模块（而不是 middleware 旁）是因为 `runtime/events/message_identity` 也要用，从那边 import middleware 会成环（`:21-26`）。
- **`UNTRUSTED_INPUT_KEY` 是"隐瞒标记 + 不可信标记"的组合**（`:12-19`）：Gateway 给带框架标记（`hide_from_ui`、`name="summary"`）的外部消息打上它，于是这些消息**继续对 transcript 隐藏**，但 `requires_input_sanitization` 仍知道内容来自信任边界外。不要改成"剥掉标记"——那会误伤三个合法前端发送方（quoted / sidecar / agent save）。
- **`restore_original_human_message()`（`:112-166`）** 是 run-event 历史的唯一还原入口：读 `additional_kwargs[ORIGINAL_USER_CONTENT_KEY]`，把**第一个**文本块换成原文、丢弃后续文本块、保留所有非文本块及其相对顺序；没有文本块时在首位插入 `{"type":"text", ...}`。`model_copy(update=..., deep=True)` 里的 `deepcopy` 是刻意的：Pydantic 只深拷原模型，对 `update` 传入的值不拷贝，必须手动隔离（`:156-165`）。调用方：`runtime/journal.py`。
- **`message_to_text(message, *, text_attribute_fallback=False)`（`:61-101`）** 与 `message_content_to_text`（`:44-58`）语义**刻意不同**：前者吃整只 message（`BaseMessage` 属性或 dict key），list 块**无分隔符拼接**，并额外认嵌套 `{"content": ...}`；后者吃裸 content，list 块用 `\n` 连接。`text_attribute_fallback=True` 才回落到 `message.text`（对齐 `RunJournal._message_text`）。调用方遍布 `runtime/journal.py`、`runtime/goal.py`、`runtime/runs/worker.py`、`app/gateway/routers/thread_runs.py`。
- `is_real_user_message()`（`:169-181`）是 slash-skill 激活 / MCP routing 这类"用户意图特征"的判据：非 `HumanMessage`、`name == "summary"`、或 `additional_kwargs["hide_from_ui"]` 一律返回 False。

---

## 5. `thread_id.py` — 唯一 ID 规则

- 模式 `^[A-Za-z0-9_-]{1,64}$`（`:11`）。ID 是**调用方自定义的不透明标识**（不一定是 UUID），但必须对所有持久化/文件系统后端安全。
- `validate_thread_id(s)` 失败抛 `ValueError`（`:15-23`）；`resolve_thread_id(s | None)` **只在 `None` 时**生成 `uuid4()`，给了值就校验（`:26-30`）——"空字符串"不是"没给"，会直接报错。
- `ThreadId = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=...), AfterValidator(validate_thread_id)]`（`:33-36`）供 Pydantic 模型复用。
- 调用方含 `client.py`、`config/paths.py`、`uploads/manager.py`、`runtime/events/store/jsonl.py`、`app/gateway/routers/{threads,runs,thread_runs,skills,suggestions}.py`、`app/scheduler/service.py`、`tui/session.py`。

---

## 6. `network.py` — 端口分配即"预留"

`PortAllocator`（`:8-106`）+ 进程级单例 `get_free_port` / `release_port`（`:110-139`）。

- **可用性探测绑定 `0.0.0.0`，不是 `127.0.0.1`**（`:47-56`）：Docker 绑 wildcard，只查 loopback 会把已被 Docker 占用的端口误判为空闲。
- 探测与预留**同一把 `threading.Lock` 内**完成（`:74-80`）：分配即加入 `_reserved_ports`，在 `release()` 前一直占用（`:82-89`），并发调用不会拿到同一个端口。`allocate_context()` 是 `try/finally` 自动释放（`:91-106`）。
- `max_range` 是**开区间步长**：搜索 `range(start_port, start_port + max_range)`，耗尽抛 `RuntimeError`（`:75-80`）。
- 进程级单例意味着**跨进程不互斥**；`get_free_port` 的返回值仍要靠调用方 `release_port`（`community/aio_sandbox/local_backend.py:943,946,1209`；`:921` 是 `get_free_port` 本身）。

---

## 7. `oneshot_llm.py` — 图外单轮 LLM 调用契约

`run_oneshot_llm(*, system_instruction, user_content, run_name, app_config, model_name=None, thread_id=None) -> str`（`:33-72`）。

- 存在理由：多条 Gateway 路由（输入润色、后续建议、标题改写）做同一串动作——按 config 建 chat model、挂 Langfuse trace metadata、单次 system+user 调用、抽出纯文本。集中后 **tracing 字段与调用形状不会各抄一份而漂移**（模块 docstring `:1-14`）。
- 固定形状：`create_chat_model(name=model_name, thinking_enabled=False, app_config=app_config)`（`:55`）→ `invoke_config = {"run_name": run_name}` → `inject_langfuse_metadata(..., thread_id=, user_id=get_effective_user_id(), assistant_id=run_name, model_name=, environment=...)`（`:56-64`）→ `await model.ainvoke([SystemMessage, HumanMessage])`（`:65-71`）。
- `environment` 取 `DEER_FLOW_ENV` 或 `ENVIRONMENT`（`:29-30`）；`thread_id` **只用于 tracing**，不参与任何路由/持久化。
- **契约边界**：返回 `extract_response_text(response.content)` 的**未清洗原文**。think-block / code-fence 剥离与 JSON 解析**故意留给调用方**（各自后处理不同，`:11-13`）。调用方：`runtime/goal.py`、`skills/security_scanner.py`、`app/gateway/routers/{suggestions,input_polish}.py`。

---

## 8. `file_outline.py` — 三种标题的 ATX 解析边界

被 `uploads_middleware` 与 `list_uploaded_files` 工具共用（模块 docstring `:1-5`）；`file_conversion.py` 只做**向后兼容 re-export**（`file_conversion.py:23-27`）。

`extract_outline(md_path) -> list[dict]`（`:92-172`）的边界：

1. **围栏代码块整体跳过**：`_CODE_FENCE_RE = ^ {0,3}(\`{3,}|~{3,})(.*)$`（`:46`）。关闭要求同字符、长度 ≥ 开启、且后缀只有空白（`:127-132`）；反引号围栏的 info string 不能含反引号，波浪号没有该限制（`:133-140`）。缩进超过 3 个空格的行不会被当成围栏/标题——缩进代码不能升级成 heading（`:48-50`）。
2. **ATX 标题**：`^ {0,3}#{1,6}(?:[ \t]+(.*))?$`，即 1–6 个 `#` 后必须有空格/tab 或行尾；结尾用 `_strip_atx_closing_hashes()` **线性**去掉空白分隔的尾随 `#` 串（`:53-59`）。
3. **粗体结构标题**：`**ITEM 1. BUSINESS**` 这类 SEC 风格只认 8 个结构关键字（ITEM/PART/SECTION/SCHEDULE/EXHIBIT/APPENDIX/ANNEX/CHAPTER，`:20`）。中文标题（`第三节`）由 pymupdf4llm 输出标准 `#` 标题，不走这条（`:17-19`）。
4. **拆分粗体标题**：`**1** **Introduction**`（`:33`）。第二个块用 negative lookahead 排除纯数字/标点（避免 `**2023** **2022** **2021**` 财务表头误命中），最多四个块、块内 `[^*]+` 保持正则线性（防 ReDoS）。
5. **上限与哨兵**：`MAX_OUTLINE_ENTRIES = 50`（`:37`）。超过时**弹掉刚加入的那条**再追加 `{"truncated": True}` 并 break（`:165-168`）——所以结果最多 50 条标题 + 1 条哨兵。
6. 标题经 `_clean_bold_title()` 合并相邻粗体 span 并剥掉最外层 `**`（`:62-80`），截断到 200 字符且把 `… (truncated)` 标记算进预算（`:40-42,83-89`）。读文件失败/无标题一律 `[]`（`:169-170`）。
7. `extract_outline_for_file(file_path)`（`:175-215`）找同 stem 的 `.md`：outline 非空 → `preview=[]`；outline 为空才给前 5 行内的非空行，**全 preview 合计** 2000 字符，超长即断。

---

## 9. `llm_text.py` — think 块裁剪的两种调用姿态

- `strip_think_blocks(text, *, truncate_unclosed=True)`（`:13-30`）：完整 `<think>...</think>` 一定删；**未闭合**的 `<think>` 默认视为"max_tokens 截断"而在该处截断正文。
- `truncate_unclosed=False` 是给"输出里可能合法出现字面 `<think>`"的调用方（输入润色器重写含该标签的草稿）用的，避免静默吞掉后半段（`:20-23`）。
- 典型配对：JSON 解析方（`suggestions`/`goal`）用默认值丢尾部垃圾。`strip_markdown_code_fence()` 只剥**一层**包裹围栏（`:33-41`）；`extract_response_text()` 只认 `type ∈ {text, output_text}` 的块并用 `\n` 连接（`:44-60`）。

---

## 10. `text_detection.py` — 内容采样 + "活动内容" MIME 判定

- `is_text_file_by_content(path, sample_size=8192)`（`:8-16`）：只读前 8 KiB，含 `\x00` 即判非文本；任何异常一律 False（含不可读/不存在）。调用方：`projects/documents.py`、`app/gateway/routers/{project_documents,artifacts}.py`。
- `ACTIVE_CONTENT_MIME_TYPES` 只列**精确**匹配（`text/html`、两个 XHTML/SVG XML、`text/xml`、`application/xml`、`text/xsl`，`:19-28`）；`_is_active_content_mime_type()` 额外把**所有 `+xml` 子类型**算作活动内容（`:31-43`）。语义是"We浏览器可能执行脚本的内联渲染"：任意 XML 都能携带 XHTML 命名空间的 `<script>`，所以 `report.xml`/`feed.rss` 与 `page.html` 在应用同源下同样危险——这是安全契约，不要收窄成只认 HTML。

---

## 11. 线格式例外（不单独成节）

- **`time.py`**：`now_iso()` 是**所有**线程/运行时间戳的唯一生成口（ISO 8601 UTC，与 LangGraph Platform schema 对齐，模块 docstring `:1-13`）。真正有契约价值的是读路径 `coerce_iso(value)`（`:58-95`）：把历史遗留的 `str(time.time())` 浮点/字符串迁成 ISO，`datetime` 必须先于 `int/float` 分支处理（否则 `str(dt)` 生成空格分隔的 `"YYYY-MM-DD HH:MM:SS+00:00"` 破坏严格 ISO 消费者），tz-naive 视为 UTC，空值 → `""`。legacy 字符串靠 `^\d{10}(?:\.\d+)?$` 锚定 10 位秒，避免误改年份（`:42-47`）。`is_lease_expired()` 把 **NULL 与不可解析一律当已过期**（`:23-39`），这是接管/对账的 fail-open 语义。纯格式化函数本身不另立契约。
- **`file_conversion.py`**：PDF 双转换器策略（`:1-15,110-140`）——`auto` 先 pymupdf4llm，输出 **chars/page < 50**（页数不可得时退回绝对 200 字符）判定为图片型 PDF 再落 MarkItDown；显式 `pymupdf4llm` 则不看长度。`_ASYNC_THRESHOLD_BYTES = 1 MiB`（`:45`），超过走 `asyncio.to_thread`。`pdf_converter` 配置小写化并校验，非法值告警回落 `auto`（`:190,202-217`）。`CONVERTIBLE_EXTENSIONS` 7 个后缀（`:32-40`）。
- **`readability.py`**：契约点是**抽取前先解析 URL**（`_resolve_html_urls`，`:64-82`）——`<base>` 只在有字面 start-tag 时才用 BeautifulSoup 解析，候选 base 必须落在 `urlparse(...).scheme in uses_relative` 内（不透明 scheme 回落抓取 URL，分层 FTP 仍有效）；`_DestinationRewriter` 只在 `a[href]`/`img[src]` 上、按**源码 span** 替换（不重建畸形 HTML），只改第一个重复属性（浏览器语义），文本元素（script/style/textarea/title/…）内不 tokenize（`:90-149`）。`ReadabilityExtractor.extract_article()`（`:152-179`）在 Readability.js 子进程失败（`CalledProcessError`/`FileNotFoundError`）时**降级到纯 Python 抽取**，空内容/空标题分别落到 `"No content could be extracted from this page"` / `"Untitled"`。3+ 社区工具依赖该形状。

---

> **See also:** [Agent Loop: 错误处理与调试](agent-loop/04-error-handling-and-debugging.md) · [Runtime: RunManager](runtime/01-run-manager.md) · [Middleware 目录](middleware/03-catalog.md) · [Harness Hooks](harness-hooks/README.md)
