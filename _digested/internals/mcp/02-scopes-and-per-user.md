---
title: "MCP scope 与 per-user 连接"
description: 'mcp_scope.py 的会话身份编码与解析，以及 per-user MCP 连接从文件、runtime 名、权限准入到每次调用守卫的契约；session pool 与凭据缓存细节不在这里。'
type: deep-dive
topics: [mcp, scope, per-user, isolation, fail-closed]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# MCP scope 与 per-user 连接

> **定位**：回答两个契约问题——「一个 MCP 会话的身份键怎么编码、怎么判定归属」与「用户自己的 MCP 连接怎么从磁盘解析成运行时工具，凭什么保证只属于他」。前者是 `mcp_scope.py` 的 95 行纯函数，后者是 `user_config.py` / `user_tools.py` / `personal_access.py` / `routers/personal_mcp.py` 的协作。
> **边界**：会话池键控、LRU、binding、OAuth token 落库与缓存失效见 [session-pool-oauth-cache-invalidation.md](session-pool-oauth-cache-invalidation.md)；治理层的授权判断见 [authorization/05](../../enterprise-it-governance/authorization/05-mcp-scope.md)。本文只讲身份与 per-user 解析，不重复 session/cache 细节。

## 1. `mcp_scope.py`：会话身份只有两种编码

`mcp_session_scope_key` 接受 `user_id` / `thread_id` / `thread_incarnation`，返回：

| 形态 | 输出 | 何时用 | 证据 |
|---|---|---|---|
| legacy | `{user_id}:{thread_id}` | `thread_incarnation is None`，保留迁移前的会话 | `backend/packages/harness/deerflow/mcp_scope.py:36-38` |
| v2 | `v2:` + 紧凑 JSON `[user_id, thread_id, thread_incarnation]` | 有 incarnation 的所有新调用 | `mcp_scope.py:39-45` |
| 非法 | 抛 `RuntimeError` | incarnation 为空串/非字符串 | `mcp_scope.py:18-20,34-35` |

JSON 元组不是审美选择：legacy 用 `:` 分隔，而不透明 ID 本身可能含 `:`；JSON 数组让 `a:b` + `c` 与 `a` + `b:c` 不会碰撞（`mcp_scope.py:39-41`；测试 `backend/tests/test_mcp_scope.py:20-24`）。v2 前缀 `v2:` 同时是版本号与识别标记（`mcp_scope.py:12-15`）。

## 2. 归属判定：故意宽松的「只多关、不泄露」

`mcp_scope_belongs_to_thread(scope_key, user_id, thread_id)` 只回答「这个键是否属于这对 user/thread」（`mcp_scope.py:48-71`）：

- legacy 分支做逐字比较 `f"{user_id}:{thread_id}"`（`:63-64`）。
- v2 分支解析 `v2:` 后的 JSON，要求三元数组且前两项精确匹配；未知前缀、坏 JSON、长度不对都返回 `False`（`:65-71`；测试 `test_mcp_scope.py:83-98`）。
- **故意不比较 incarnation**（`:53-56`）。删 thread 时要清掉该线程的**所有代**：删除路径拿不到可靠当前 incarnation，且新代可能正在并发铸造（`session_pool.py:875-899`）。
- legacy 的冒号歧义可能误伤另一个 owner 的键，但方向只会**过度关闭**（多拆一个可重建会话），不会把会话交给别人；v2 是精确编码（`mcp_scope.py:58-61`）。

`runtime_thread_incarnation(runtime)` 负责从 `ToolRuntime.context` 读服务端拥有的 incarnation（`mcp_scope.py:74-95`）：

| 输入 | 行为 | 证据 |
|---|---|---|
| `runtime is None`（直接工具调用） | 返回 `None`，保留 legacy scope | `mcp_scope.py:76-79` |
| 有 runtime 但缺 `thread_incarnation` 键 | `RuntimeError` | `mcp_scope.py:80-82` |
| 值非 `None` 且非空字符串 | `RuntimeError` | `mcp_scope.py:83-85` |
| guard 开启且持久化值缺失（当前值非 None）或不一致 | `RuntimeError("stale thread incarnation")` | `mcp_scope.py:86-94` |

调用点在每次工具调用前生成 scope（`backend/packages/harness/deerflow/mcp/tools.py:694-700`），durable task 提交同样走它（`mcp/task_tool_caller.py:193-197`），session pool 的线程清理用归属函数跨域匹配（`mcp/session_pool.py:893-899`）。

## 3. per-user 连接：从文件到每次调用

**文件与命名。** 每个用户的 personal MCP 存在 `<user_dir>/integrations/mcp.json`，不是用户根下的 `mcp.json`（`backend/packages/harness/deerflow/mcp/user_config.py:25-27`）；`get_paths().user_dir` 负责用户名校验（`backend/packages/harness/deerflow/config/paths.py:238-240`）。文件由 owner-only 路由读写，目录 `0700`、文件 `0600`（`backend/app/gateway/routers/personal_mcp.py:66-68,105-106`）。personal 文件只接受字面量，不做宿主 `$ENV` 展开（`user_config.py:56-58`；`personal_mcp.py:99`）。

**runtime 名。** `personal_server_name` 把 `[user_id, name, configuration]` 做 SHA-256，取前 32 位加 `personal_` 前缀（`user_config.py:37-44`）。因此改配置就换 runtime 名，旧名自然失效，也不会和部署连接或另一个用户撞名；`personal_server_name_variants` 额外给出 enabled 真/假两种变体，供 OAuth token 清理匹配开关（`user_config.py:47-53`）。

**发现与准入。** 个人工具不进部署单例缓存：`get_user_mcp_tools` 读一次字面快照后单独发现（`mcp/user_tools.py:50-61`），发现前先用 `authorized_personal_config` 把当前无管理员权限的特权连接过滤掉，避免 discovery 阶段就启动或联系它们（`mcp/personal_access.py:42-46`；`mcp/tools.py:1255-1270`）。

**每次调用守卫。** 每个 personal 工具都被 `_guard` 包一层（`user_tools.py:18-40`）：

1. `resolve_runtime_user_id` 必须仍是 owner，否则 `ToolException`（`:31-33`）。
2. 按 `(dev, ino, size, mtime_ns, ctime_ns)` 签名重读文件，连接必须仍存在且 enabled，否则提示「changed, disabled or removed」（`:23-28,35-36`；`user_config.py:66-86`）。
3. 过 `require_personal_mcp_access(owner, server)`，每次实时判管理员（`:37`；`personal_access.py:37-39`）。

**网络边界。** 非管理员保存的 personal 连接只能是公网 `http`/`sse`，或**不带 `cwd` 的内置 bundled stdio**，且不能带 `oauth`；违规分别是 403 / 400（`personal_mcp.py:47-62`）。保存时写入 `personal_public_network = not admin`（`:78-81,91,95`）。该标记为 true 的 HTTP/SSE 连接由 `personal_httpx_client_factory` 接管：每次请求重新解析并钉住已校验公网 IP、按原始 origin 分池、`follow_redirects=False`、`trust_env=False`（`mcp/client.py:39-42`；`mcp/personal_network.py:11-22,30-51`；URL 校验契约见 `community/url_safety.py:144-170`）。

**与 `user_auth` 的区别。** `user_auth` 是部署方拥有的一个 server 上，按用户映射不同凭据；personal 连接是用户拥有的整个 server 定义。前者在每次调用按 runtime user 重写 header，缺映射默认 fail-closed（`mcp/user_scoped_auth.py:1-19,105-120`）；后者走上面的文件解析与 owner 守卫。两者都要求「当前调用者」而不是配置里的静态身份。

## 4. fail-closed 清单

| 场景 | 行为 | 证据 |
|---|---|---|
| incarnation 为空/类型不对 | `RuntimeError`，不生成 scope | `mcp_scope.py:34-35` |
| runtime 缺 incarnation 键或值非法 | `RuntimeError` | `mcp_scope.py:80-85` |
| 上下文与持久化 metadata 不一致 | `RuntimeError("stale ...")` | `mcp_scope.py:86-94` |
| scope 编码未知/坏 JSON/结构不对 | 返回 `False`，不认领 | `mcp_scope.py:65-71` |
| personal 工具被另一个 user 调用 | `ToolException` | `user_tools.py:32-33` |
| 连接被改配置/禁用/删除 | `ToolException`，要求新 run | `user_tools.py:35-36` |
| 管理员判定缺失、异常或非 True | 视为非管理员；缺 `personal_public_network` 标记的连接一律要管理员 | `personal_access.py:20-34` |
| 特权连接在 discovery 前 | 被过滤，不启动/不联系 | `personal_access.py:42-46` |
| 非管理员注册 host command / OAuth / 私网 URL | 403 或 400 | `personal_mcp.py:55-61` |
| 公网目标在请求时被重绑定 | 每次请求重新校验并钉 IP | `personal_network.py:11-22,30-51` |

## 5. 与 `knowledge_scope.py` 的类比/区别

| 维度 | `mcp_scope.py` | `knowledge_scope.py` |
|---|---|---|
| 回答的问题 | 谁能复用哪个 MCP 会话（身份） | 这一轮检索允许看哪些数据集/文档（能力包络） |
| 编码 | legacy 字符串或 `v2:` JSON 元组 | versioned Pydantic JSON，`version`/`mode` 固定 |
| 解析失败 | 生成时 `RuntimeError`；匹配时 `False` | `ValidationError`（严格、`extra=forbid`） |
| 拆除语义 | 故意跨所有 incarnation，宁多关不泄露 | 不适用；`execution_scope` 剥掉不可信 display |
| 证据 | `mcp_scope.py:23-71` | `backend/packages/harness/deerflow/knowledge_scope.py:95-102,161-170,179-182` |

两者都把「版本化 JSON + 明确失败方向」当成契约，但 `knowledge_scope` 有 64 KiB 上限、严格字段与不可信 display 投影（`knowledge_scope.py:27-28,168,179-182`；测试 `backend/tests/test_knowledge_scope.py:84-101`），`mcp_scope` 则只有 95 行、只做身份与归属。

## 6. 测试锚点

- `backend/tests/test_mcp_scope.py:11-29`：legacy/v2 编码、含冒号 ID 的消歧、空 incarnation 拒绝。
- `backend/tests/test_mcp_scope.py:32-80`：跨 incarnation 匹配、拒绝其他 user/thread、第三项形状宽松。
- `backend/tests/test_mcp_scope.py:83-98`：坏 JSON、未知前缀、长度不对都不认领。
- `backend/tests/test_personal_mcp.py:88-110`：同名连接按 owner 隔离、文件权限；`:280-292` 普通用户不能启动 host command / 连私网；`:378-425` 旧工具在配置变化后被拒；`:433-475` 文件替换/失效快照；`:484-524` 后台任务只解析持久化 owner；`:721-751` 删除/编辑连接清 token 行。
- `backend/tests/test_personal_mcp_access.py:61-122`：降级/删除/查询失败都阻断 discovery、已有工具与缓存 durable 调用。
- `backend/tests/test_personal_mcp.py:356-374`：同一个 client 的第二次请求重新校验目标，DNS 变私网即被拒。

## 阅读路径

1. **先读契约**：`mcp_scope.py` 全文（95 行）+ `test_mcp_scope.py`，先分清「编码」与「归属匹配」两件事。
2. **再读 per-user**：`mcp/user_config.py` → `mcp/user_tools.py` → `mcp/personal_access.py`，沿着「文件 → runtime 名 → 发现 → 每次调用」走一遍。
3. **深入**：`mcp/session_pool.py:875-899` 看跨 incarnation 清理，再读 [session-pool-oauth-cache-invalidation.md](session-pool-oauth-cache-invalidation.md) 的 session/cache 细节。

## 宪章与约定

- 本目录有包内宪章：[backend/packages/harness/deerflow/mcp/AGENTS.md](../../../backend/packages/harness/deerflow/mcp/AGENTS.md)（87 行），其中「Personal MCP configs」「Personal definitions」两条是本文的上级约束。
- 写作纪律沿用 [根 README](../../README.md)；`mcp_scope.py` 只有 95 行，是一层薄契约，不要为「功能完整」把它长胖。

## 相关目录

- [internals/mcp/](README.md) — 本目录入口；[session-pool-oauth-cache-invalidation.md](session-pool-oauth-cache-invalidation.md) 是 session/cache 正文，[durable-tasks.md](durable-tasks.md) 是后台任务。
- [authorization/05](../../enterprise-it-governance/authorization/05-mcp-scope.md) — 治理视角的 MCP 作用域与 personal MCP 判断。
- [configuration/02](../../internals/configuration/02-extensions-json.md) — `extensions_config.json` 的部署侧字段；personal 文件结构同源但走独立路由。
- [persistence/](../../internals/persistence/README.md) — `mcp_oauth_tokens` 与 durable task 的落库。
- [security/06](../../enterprise-operations/security/06-extension-boundary.md) — 扩展边界；MCP 不在该 fence 的准入范围内，但共享「按 owner 隔离」的思路。
