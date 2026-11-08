---
title: "Browser Automation — Playwright agentic 浏览器会话"
description: '有状态的 navigate → observe → act 循环：进程内私有 loop-affine Playwright event-loop 线程，每步返回带稳定 [ref] 索引的页面快照，URL SSRF 过滤在浏览器请求边界生效。'
topics: [tools, community, browser, playwright, ssrf, live-screencast]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Browser Automation — Playwright agentic 浏览器会话

> 同步 #4（e5c62cab）新增。与只读的 `web_fetch`/`web_capture` 不同，这个工具集维护一个 **per-thread 存活浏览器会话**，让 agent 点击、输入、提交表单、走多步流程（JavaScript-heavy 或需要登录的页面）。每个动作返回**新鲜的页面快照**，可交互元素用**稳定数字 `[ref]` 索引**寻址——模型对它刚观察到的内容行动，而不是猜选择器或持过期句柄。

## 定位

```
community/browser_automation/
├── __init__.py    # 包导出 + BrowserSessionManager 单例
├── session.py     # ~1100 行：_PlaywrightLoopThread / BrowserSession / 快照 / 请求守卫 / Live screencast
└── tools.py       # 8 个 tool 定义 + URL 校验 + 截图落盘
```

工具清单（`config.yaml tools:` 配 `group: browser`）：

| tool | 作用 |
|------|------|
| `browser_navigate` | 导航到 URL（`wait_until="domcontentloaded"`）→ 返回快照 |
| `browser_snapshot` | 重新渲染当前页面快照（不动作） |
| `browser_click` | 按 `[ref]` 点击元素 → 返回新快照 |
| `browser_type` | 按 `[ref]` 输入文本，可选 `submit` 回车 |
| `browser_get_text` | 提取页面可见文本（`max_chars` 上限，默认 8000） |
| `browser_back` | 浏览器后退 → 新快照 |
| `browser_screenshot` | 页面截图（可选 `full_page`），写入 outputs 隐藏子目录 |
| `browser_close` | 关闭会话 |

## 会话架构：进程内私有 loop-affine 事件循环线程

`BrowserSessionManager`（进程级单例）拥有一**条**私有 asyncio event loop，跑在守护线程 `deerflow-browser-loop` 上（与 BoxLite provider 相同模式）：

```python
class _PlaywrightLoopThread:              # session.py
    self._loop = asyncio.new_event_loop()
    self._thread = threading.Thread(target=self._run, name="deerflow-browser-loop", daemon=True)
    # run(): run_coroutine_threadsafe(coro, self._loop) → wrap_future → await
    # submit(): 后台调度，add_done_callback 记失败
```

- 跨 turn 存活：每个线程一个 `BrowserSession`，无论调用方在哪个 loop（Gateway / TUI / test），Playwright 句柄永远回到**它自己的** loop 上——loop-affine 句柄跨 loop 用会崩。
- `BrowserSession` 每个动作用 `_activity()` 上下文管理器 `_pin()/_unpin()`（引用计数 + 刷新 recency），`_on_activity` 回调让 manager 知道会话仍在使用。

## 页面快照与 `[ref]`

快照 = 交互元素列表，不是整个 DOM。`SnapshotElement` 携带 `ref / tag / role / type / name`，渲染成模型可直接引用的索引：

```
URL: https://example.com
Title: ...
Interactive elements (address them by [ref] number):
[0] link: Sign in
[1] button type=submit: Submit
[2] textbox: Email
```

`[ref]` 在快照时以 `data-df-ref` 打进 DOM——模型看到的索引就是下次动作的寻址。每次 action 返回**新快照**（`_snapshot_impl`），所以状态永远新鲜。

## SSRF 守卫：在浏览器请求边界而非单点 URL

`validate_public_http_url`（`community/url_safety.py:145`）筛显式导航 URL（`allow_private_addresses` 仅在故意内网目标时 opt-out）。但 **Playwright 会跟随重定向、发 subresource/popup 请求**——单次初始 URL 检查看不到这些。所以 `_install_request_guard()` 在 **context 级别** 挂 `context.route("**/*")`：

```python
async def _route(route):
    url = route.request.url
    if url.startswith(("http://", "https://")) and guard(url) is not None:
        await route.abort("blockedbyclient")   # SSRF 命中 → abort
    await route.continue_()
```

覆盖：顶层导航、每个重定向 hop、popup/新 tab、iframe、subresource fetch——**公开 URL 30x 重定向到 `http://169.254.169.254/...`（云 metadata）会在响应暴露给快照/text 之前被 abort**。跳过 CDP-attached 真 Chrome（它拥有自己的 browsing context）。

实现在 `session.py:497-529`（2.2.0 已改为 `await asyncio.to_thread(guard, url)`——守卫要做 DNS 解析，不能跑在共享的浏览器事件循环上）；拦截日志用 `redact_browser_url(url)` 脱敏；`route.abort("blockedbyclient")` 与 `route.continue_()` 都包在 `contextlib.suppress` 里，避免一条畸形请求炸掉整个 context。

### 但 request guard 只解决了一半：DNS rebinding 🆕

守卫在**筛 URL 时会解析一次主机名**，而 **Chromium 在真正建连时会再解析一次**。一个 rebinding DNS 服务器可以先返回公网地址通过筛选，紧接着返回私网或云 metadata 地址给 Chromium。2.2.0 新增 `browser_automation/egress.py`（206 行）把「解析」这一步从浏览器里拿走：

```
Chromium ──SOCKS5 CONNECT host:port──▶ BrowserEgressProxy (127.0.0.1:<ephemeral>)
                                          │
                                          ├─ 用自己的 resolver 解析**恰好一次**
                                          │   （resolve_browser_egress → 同一个
                                          │    allow_private_addresses 策略）
                                          ├─ 只连 resolver 认可的那些地址
                                          └─ 之后纯字节转发，永不解析隧道内流量
```

关键设计（`egress.py` 模块 docstring 与实现）：

| 点 | 说明 |
|----|------|
| 只支持无认证 `CONNECT` | 「which is everything Chromium sends for HTTP, HTTPS, and WebSocket traffic」；不支持的 command / 地址类型回 `_REPLY_COMMAND_NOT_SUPPORTED` / `_REPLY_ADDRESS_TYPE_NOT_SUPPORTED` |
| 三种地址类型都解析成 IP 字符串再交给 resolver | IPv4 / IPv6 / DOMAIN（DOMAIN 必须是纯 ASCII 且非空，否则回 `ADDRESS_TYPE_NOT_SUPPORTED`） |
| **拒绝与故障可区分** | `ValueError` → `_REPLY_NOT_ALLOWED`（策略拒绝，warn）；解析超时 → `HOST_UNREACHABLE`；其它异常 → `GENERAL_FAILURE` 并 `logger.exception`——「A resolver fault is not a policy refusal; keep the two distinguishable in the log and in the browser's error.」 |
| **地址共享一个连接预算** | `_open_first()` 用 15s 总 deadline，第 i 个地址只拿 `remaining / (剩下几个)`——「a black-holed first answer cannot strand reachable candidates」 |
| 超时分层 | 握手 15s、解析 15s、连接 15s、关闭 2s |
| `close()` 不挂在残留隧道上 | `Server.wait_closed()` 会等所有连接，所以先把 `_client_writers` 里的隧道全 close，再 `wait_for(..., timeout=2)` 吞掉异常——「it must not hold up session close or eviction」 |
| 关闭后不再建隧道 | `_handle()` 开头 `if self._server is None: writer.close(); return`（抢在 `close()` 之后 accepted 的连接） |

接线（`session.py`）：

- `BrowserSession.__init__` 新增 `egress_resolver` 参数（`:314`），注释就是上面那段 rebinding 论证；
- `_egress_proxy_settings()`（`:455-462`）：没有 resolver → 返回 `None`（不启用代理）；否则懒建 `BrowserEgressProxy` 并返回 `{"server": "socks5://127.0.0.1:<port>", "bypass": "<-loopback>"}`——注释强调「Playwright already proxies loopback for Chromium unless an environment override disables it; spell it out so **localhost is never exempt**」；
- `chromium.launch(..., proxy=await self._egress_proxy_settings())`（`:445`），会话关闭时 `await self._egress_proxy.close()`（`:748-752`）；
- resolver 是 `tools.py:182` 的 `resolve_browser_egress(host, *, tool_name="browser_navigate")`——它读同一个 `allow_private_addresses` 配置，走 `resolve_public_addresses(host, action="browse", ...)`，最后 `dict.fromkeys` 去重保序。

**两层是互补而非冗余**：request guard 让被拒请求**不发出**（快、能拦住 subresource），egress proxy 保证**发出去的连接只能落在被审查过的地址上**（抗 rebinding）。两者都跳过 CDP-attached 真 Chrome。

## Live Screencast（浏览器实时画面）

- 工具调用和 **Live WebSocket** 共享同一会话，可能并发观察到已关闭页面——`_ensure_page` 用 `asyncio.Lock` 保证只有一人重建浏览器层级，第二个在锁内复用结果。
- 截图以 **JPEG 字节**留在 harness 和 Gateway 的**有界、drop-oldest** 帧队列。WebSocket 客户端要 `frame_format=binary` 收二进制帧；控制元数据是 JSON；旧的无参数协议在 Gateway 边界 base64 编码进 JSON（向后兼容）；未知 `frame_format` 收 JSON error + close code 1008。
- **screencast 可 re-bind 到新页面**：登录/OAuth 流程常开 popup 或新 tab，用户必须看到（并驱动）它——`_on_frame` 保留，新页面激活时 `_rebind_screencast`（`_screencast_binding` 标志防重入递归）。
- **Live 输入独立于 JPEG 捕获**：非移动动作启动**限速后台刷新循环**，指针/滚轮/键盘输入保持响应，连续手势全程持续产帧。

## 线程亲和约束（多 worker 拒绝）

浏览器会话是 **process-local**。Gateway 启动安全门在 `browser_navigate` 配置时**拒绝 `GATEWAY_WORKERS > 1`**（`browser_multi_worker_error`）——普通 uvicorn worker 分派没有 thread affinity，无法保证 browser tools、REST 导航和 Live WebSocket 落在同一进程。

## 会话容量与驱逐

`BrowserSessionManager` 有硬性 `max_sessions` 上限：

- **pinned（Live/operation）会话永不驱逐**；新线程在无法关闭任何 unpinned 会话时被拒绝
- 一个 Live viewer 同时独占一个会话
- Browser REST/Live 访问要求**精确非 NULL thread owner**（而非通用 legacy shared-thread 策略）——因为保留的页面可能含已认证状态

## CDP 附加（"连接你的真实浏览器"）

`cdp_url` 附加到已在跑的 Chrome（`--remote-debugging-port`，复用默认 context + 现有 tab），用户看着 agent 驱动自己可见的浏览器、带真实登录会话。**不能给已有 Chrome context 装 request guard**，所以 `cdp_url` 除非操作者显式设 `allow_unguarded_cdp: true`（信任的本地浏览器）否则 **fail-closed**。

## 依赖与安装

```bash
cd backend && uv sync --extra browser && uv run playwright install chromium
```

- `scripts/detect_uv_extras.py` 在 `config.yaml` 启用 `browser_navigate` 时保留该 extra
- Gateway 启动在配置的浏览器控制无法 import Playwright 时**快速失败**（fail fast）
- 每步自动截图写入 `outputs/<BROWSER_FRAMES_DIRNAME>/`（隐藏子目录，`BROWSER_FRAMES_DIRNAME` 是共享常量）——workspace-changes review **不把瞬时浏览器帧列为文件改动**

## 源码索引

| 机制 | 位置 |
|------|------|
| 私有 loop 线程 | `session.py:_PlaywrightLoopThread`（183-214） |
| 快照 / `[ref]` | `session.py:SnapshotElement` / `PageSnapshot` / `_snapshot_impl` |
| 请求级 SSRF | `session.py:_install_request_guard`（497-529） |
| **出网固定（SOCKS5）** 🆕 | `egress.py:BrowserEgressProxy`（`:58`）/ `session.py:_egress_proxy_settings`（455-462）/ `tools.py:resolve_browser_egress`（`:182`） |
| CDP 附加 | `session.py:__init__` cdp_url 分支 / `_ensure_page` |
| Live screencast | `session.py:_start_screencast` / `_rebind_screencast` / `_emit_live_frame` |
| 工具定义 + URL 校验 | `tools.py:validate_browser_url` / 各 tool 函数 |
| URL 安全 | `community/url_safety.py:validate_public_http_url` / `resolve_host_addresses` / `is_blocked_address` |
| 测试 | `tests/test_browser_automation.py`（mock + 真 Chromium integration，`importorskip` 守卫） |

## 相关

- 装配 / 集成矩阵 / 选型 → [`00-overview.md`](00-overview.md)
- 如何添加新 provider（同目录约定）→ [`05-how-to-add-provider.md`](05-how-to-add-provider.md)
- workspace-changes 对浏览器帧的排除 → [`../../concepts/workspace-changes.md`](../../concepts/workspace-changes.md)
- BoxLite 的同类私有 loop 模式 → [`../../concepts/sandbox/abstract-interface-and-seven-impls.md`](../../concepts/sandbox/abstract-interface-and-seven-impls.md)
