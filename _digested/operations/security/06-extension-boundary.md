---
title: "Extension 安全边界 — 插件能力、授权目标与宿主授予"
description: "v2.2.0 的 21 个新增/改写文件把扩展面从『可信 operator 代码自由发挥』收紧为『宿主逐项授予、逐次鉴权的窄能力』：plugin action/management 目标串、restart-bound host_access、model invocation 预算、skill mutation 发布闸门、completed-run evidence 只读投影。"
topics: [security, extension, plugin, authz, capability-grant, skill-mutation, run-evidence]
---

# Extension 安全边界 — 插件能力、授权目标与宿主授予

> **2.2.0 里程碑 | 扩展面从"信任"改为"授予"**：`deerflow_extension_api` 一次性长出 7 个模块（`agent_runs` / `completed_run_evidence` / `host_capabilities` / `model_invocation` / `plugins` / `settings` / `skill_mutations`），宿主侧新增 8 个文件 + 改写 11 个。共同主题只有一句：**插件不再"因为被 import 就什么都拿到"，每项宿主能力都要 operator 在 `config.yaml` 里显式写一行 grant，并在每次调用时重新回答"这个用户、这个 namespace、这个动作，允不允许"。**

> 权威事实源：`backend/packages/harness/deerflow/extensions/AGENTS.md`、`backend/packages/extension-api/deerflow_extension_api/`（公开契约）、`docs/full-stack-plugins.md`（插件面）、`docs/skill-evolution-host.md`（skill mutation）。

## 一、三块扩展面的信任等级（2.2.0 后仍不变）

| 配置面 | 文件 | 谁能写 | 内容 | 风险 |
|--------|------|--------|------|------|
| `plugins:` | `config.yaml` 顶层 | **仅 operator**（只读挂载） | 打包 Python 扩展入口点 → **启动时被 import** | 代码执行边界 |
| `extensions:` | `extensions_config.json` | Gateway HTTP API 可写 | MCP servers、skill 开关、middleware 声明 | 不可承载代码 |
| 插件 settings | `PluginContribution.fields`（部署清单） | **仅 operator** | 非敏感设置，`defaults()` 直出 | 无运行时覆写面 |

2.2.0 新增的每一类宿主能力（`host_access` / `model_invocation` / `skill_mutations`）都挂在第一块面里——即 **grant 只能通过重启生效，永远不在 API 可写面上**。`extensions/host_access.py:73` 的 `bind_host_access()` 是唯一入口：`config.plugins` 里没有 `host_access` 的 spec，`HostAccess.granted` 为 `False`（`host_access.py:53`），该插件拿到的所有 capability 都是 `None`。

---

## 二、Plugin 授权：目标串是唯一 key

### 2.1 为什么需要"目标串"

插件资源的授权问题是：RBAC 要在 `config.yaml` 里写一条 policy，而 policy 的 key 必须**同时**满足两件事——能唯一标识一个被保护对象，且**只能由宿主生成**（插件自己拼的字符串若被接受，就等于让被保护者定义自己的 key）。

2.2.0 引入 `authz/plugin_targets.py`（77 行，全模块 `__all__` 只有 3 个构造器 + 2 个常量 + 1 个异常）作为**唯一编码器**：

| 构造器 | 行 | 产出 | 用途 |
|--------|-----|------|------|
| `plugin_action_target(namespace, action)` | `authz/plugin_targets.py:61` | `"<namespace>/<action>"` | 模型/浏览器触发一个 backend action |
| `plugin_page_target(namespace, surface)` | `authz/plugin_targets.py:64` | `"<namespace>/<surface>"` | 声明式前端页面（**尚未接线**，见 2.5） |
| `plugin_management_target(namespace, part)` | `authz/plugin_targets.py:77` | `"<namespace>/<part>"`，part ∈ `permissions.read` / `permissions.write` | 插件自有管理路由 |

字符集是硬约束（`plugin_targets.py:27-31`）：namespace `[a-z][a-z0-9_.-]{0,95}`、action `[a-z][a-z0-9_-]{0,63}`、surface `[a-z][a-z0-9-]{0,63}`。**三条 charset 规则在仓库里有三份拷贝**——authz、extension-api（`deerflow_extension_api/auth.py:26` 的 `_NAMESPACE_RE`）、`deerflow.config.plugin_settings`——`backend/tests/test_plugin_targets.py` 用同一批 `VALID_NAMESPACES` / `INVALID_NAMESPACES` 钉住三份不许漂移；宿主不 import 契约包、契约包不 import 宿主，所以"容忍重复但测试强制相等"是刻意选择。

不合法的输入一律 `PluginTargetError`（`ValueError` 子类，`plugin_targets.py:24`），**不是**静默降级成 `"invalid"`。

### 2.2 两个新 RBAC resource

`authz/rbac.py:36-39` 的 `_RESOURCE_POLICY_KEYS` 增加两行：

```python
"plugin_action": "plugin_actions",
"plugin_management": "plugin_management",
```

要点：

- 左侧是 `AuthzRequest.resource`（单数），右侧是 `config.yaml` 的 key（**故意分开**）——早期版本用同一个字符串查表，导致 `"tool"` 去查 `"tool"` 而不是 `"tools"` 的静默误查，因此显式映射。
- `plugin_management` 是**自映射**（和 `sandbox` 一样）合法；`plugin_action` 不是——把 `plugin_action` 当 config key 写在 `authorization:` 下会在构造期被拒绝。
- **没有 policy key 的 resource = 不受限**，这是"部署方启用了 authorization 但没列这两个 key"的向后兼容路径（`rbac.py:33-38` 注释明说）。
- RBAC 还在 `rbac.py:133` 新增 `known_roles` 属性，供 `app/gateway/authz.py:217` 的 `assignable_role_names()` 枚举——管理员分配角色时不能分配一个不存在的 role。

### 2.3 执行面：`plugin_authz.py`（398 行）

| 函数 | 行 | 语义 |
|------|-----|------|
| `enforce_plugin_action` / `aenforce_plugin_action` | `authz/plugin_authz.py:277` / `:299` | 单个 action 的放行/拒绝；拒绝抛 `PluginAuthorizationError`（`:78`） |
| `enforce_plugin_management` / `aenforce_plugin_management` | `:321` / `:344` | 管理动作，`part` 由 `MANAGEMENT_READ_PART`/`MANAGEMENT_WRITE_PART` 决定 |
| `afilter_plugin_pages` / `afilter_plugin_management` | `:367` / `:384` | Layer 1 可见性过滤（列页面/列插件） |

三条不变量：

1. **provider 答不出来 = 拒绝**。`_unanswerable`（`:105`）把"provider 抛异常 / 返回 None / 返回非 bool / `authorization.enabled` 为 false 以外的空答案"统一折叠为 deny；这是 plugin 面比 tool 面更严的地方——tool 面还有 `fail_closed=false` 的 fail-open 开关，plugin action 路由没有。
2. **authorization 关闭 → 全部放行**。`app/gateway/authz.py:733` 的 `authorize_plugin_action_for_request` 在 `provider is None`（即 `authorization.enabled` 不是 `True`）时直接 `return`，保持"关掉 authorization 不突然开始拒绝企业路由"。
3. **principal 为 `None` 也要过**。`afilter` / `_afilter`（`:242`）在匿名调用者下不短路放行——匿名者拿到空列表。

### 2.4 Gateway 接线：授权在**读 body 之前**

`app/gateway/routers/plugins.py:135` 的 `POST /api/plugins/{namespace}/actions/{action_name}` 顺序被刻意设计（`plugins.py:160-168` 有注释钉住）：

```
1. resolve_principal(request) → None ⇒ 401
2. x-deerflow-plugin-viewer ≠ principal.user_id ⇒ 409（同一浏览器标签换了账号）
3. namespace 未安装 ⇒ 404；action_name 未声明 ⇒ 404
4. plugin_settings(source, plugin) 读部署清单 ⇒ ValueError/OSError ⇒ 503
5. settings["enabled"] is not True ⇒ 403
6. authorize_plugin_action_for_request(...) ⇒ 403 "Plugin action not permitted for your role."
7. 之后才 request.stream() 读 body，>256 KiB ⇒ 413
8. json.loads 失败/非 object ⇒ 422
9. action.handler 超 30s ⇒ 504；AgentRunError ⇒ 原 status；ValueError ⇒ 422；其它 ⇒ 502
```

**第 6 步在第 7 步之前**是安全属性而不是风格：被拒的调用者连输入预算都消耗不到，handler 也永远看不见、触发不了。反过来（先读 body 再鉴权）会让一个 256 KiB 的上传在 403 之前就被接收，构成一个免费的带宽/内存放大点。

**为什么先解析 action 再鉴权**：这样 target 里的 `action_name` 一定是宿主校验过的声明名，未知 action 稳定返回 404 而不是 403——不会把"这个插件有哪些 action"泄露给无权者。

### 2.5 尚未接线的部分（必须知道的缺口）

| 项 | 现状 | 后果 |
|----|------|------|
| 声明式前端页面（`plugin_page`） | `RESOURCE_PLUGIN_PAGE`（`plugin_authz.py:71`）、`plugin_page_target`、`afilter_plugin_pages` 都在，**`_RESOURCE_POLICY_KEYS` 里没有 `plugin_pages`，Gateway 也没有任何调用点** | 声明页面**尚未被 gate**；`config.example.yaml:3444` 的注释原话："their `plugin_pages` row ships with the page-authorization slice" |
| `require_plugin_management` 的 `PermissionError` | 契约包 helper 抛 `PermissionError`（`deerflow_extension_api/auth.py:87`），**Gateway 不翻译** | 插件路由若直接让它逃逸，客户端看到 **500** 而不是 403；插件必须自己 `except PermissionError` 转 403/503 |
| 模型可见插件工具的授权 | `build_plugin_tools()`（`extensions/plugin_tools.py:124`）只按 `plugin_settings(...)["enabled"]` 过滤 | 插件工具进入 agent 工具表后，**由通用 Layer 2 `authorize` 按 `"tool"` resource 管**，不经过 `plugin_actions`；要给某个插件的模型工具单独限权，写 `tools:` policy |

### 2.6 `afilter`/`enforce` 的 offload 规则

`authz/provider.py` 的 `filter_resources` docstring 在 2.2.0 增加两句硬要求：provider 的答案**只能收窄候选**（不能扩充），且**必须线程安全**——因为它会被 offload 到 worker 线程执行。异步路径（`aenforce_*` / `afilter_*`）刻意不复用同步 resolver 槽：`EXTENSION_PLUGIN_AUTHZ_RESOLVER_ASYNC_KEY`（`deerflow_extension_api/auth.py:12`）与同步 key 并存，**没有**"异步没有就用同步顶上"的回退——那会把宿主侧的配置读取搬回 event loop。

---

## 三、Host access grant：重启绑定，不是沙箱

`extensions/host_access.py`（91 行）定义"一个插件被授予了哪些宿主数据面"：

| 字段 | 行 | 约束 |
|------|-----|------|
| `EvidenceAccess.owners` | `:17` | ≤1000 条、唯一、**无通配**（拒绝 `*`）、单条 ≤128 字符、无首尾空白、无控制字符 |
| `SkillMutationAccess.operations` | `:38` | ⊆ `{stage, check, commit, revert}` |
| `SkillMutationAccess.trigger_agents` / `target_skills` | `:43` | 同一批 identifier 规则；`target_skills` 还要求**规范 skill 名** `[a-z0-9]+(-[a-z0-9]+)*` 且 ≤64 |
| `SkillMutationAccess.topology` | `:35` | 只接受 `"single_host_local"`，且**必须 operator 显式断言**（不写就拒） |
| `HostAccess.granted` | `:57` | `owners` 或 `operations` 任一非空即视为"已授予" |

`bind_host_access(specs)`（`:83`）的两条规则：

1. **身份取 64 位 hex 摘要**：`sha256(json.dumps([spec.name, spec.use]))`——身份来自宿主注册表数据，**不是**插件自报的 ID。改 `name` 或改 `use` 都会故意产生一个**新的持久身份**。
2. **一旦授予，全部 enabled 注册点必须指向同一个安装**：若 `name` 在 enabled spec 里重复、或 `use` 重复，直接 `ValueError` 中止启动。未被授予的 legacy 重复入口点仍然合法（向后兼容）。

**范围声明**：`host_access.py:1` 的模块 docstring 第一句就是 "Restart-bound, host-owned grants; **not a sandbox for trusted Python code**"。插件代码和 Gateway 同进程同权限，`host_access` 是用来**防止误用与审计归属**的，不是用来防恶意的——真正的隔离仍在进程/容器层（见 [02-sandbox-isolation.md](02-sandbox-isolation.md)）。

`extensions/loader.py:52` 增加 `ExtensionSpec.host_access` 字段与 `model_validator`：`host_access.granted` 为真时 `name` 必须显式、稳定、无首尾空白、≤128 字符——没有稳定名就无法归属证据与恢复记录。

---

## 四、Model invocation grant：把"插件调模型"变成有预算的资源

### 4.1 授权形状

`extensions/model_access.py:12` 的 `ModelInvocationGrant`（`extra="forbid"`、`frozen`、`allow_inf_nan=False`）：

| 字段 | 默认 | 范围 | 含义 |
|------|------|------|------|
| `roles` | 必填，≥1 | — | **逻辑角色 → 配置里的模型名**。插件只说自己要哪个 role，不能点具体模型 |
| `max_concurrency` | 2 | 1..64 | 同时在途调用数 |
| `timeout_seconds` | 60 | (0, 600] | 单次调用上限（请求自己的 `timeout_seconds` 只能更小） |
| `max_input_chars` | 262144 | 1..1048576 | 输入字符上限 |
| `max_output_chars` | 65536 | 1..1048576 | 输出字符上限 |

### 4.2 生命期与预算

- `ModelInvocationScope`（`model_access.py:35`）：**一次 `install()` 一个 scope**——即使它注册了多个 service 也共用一份预算（避免"多注册几个 service 就把并发放大 N 倍"）。
- `ModelInvocationBudget`（`:51`）：`asyncio.Semaphore(max_concurrency)` + **`capacity = 2 × max_concurrency`** 的准入计数。为什么是 2 倍：一个调用方取消后，被 shield 住的 provider 任务仍持有槽位，若准入计数等于信号量容量，取消风暴会立刻表现为 `capacity exceeded`；2 倍给"已放弃但在途"的工作留一层。
- `ModelInvocationService`（`:71`）是宿主适配层：`start()` 直接 `RuntimeError`（必须走 `start_with_host`），`start_with_host()` 先把 invoker 绑上再调插件 `start()`，**任何 `BaseException`（含宿主取消）都先 `invoker.close()`** 再抛；`stop()` 同样先 revoke 再停插件。`extensions/gateway.py:601` 用 `isinstance(service, ModelInvocationService)` 分派，未授予的 service 走原来的共享 `deps` 对象（保留对象身份，legacy 行为不变）。

### 4.3 `HostModelInvoker.invoke()` 的拒绝路径（`extensions/model_invocation.py:130`）

```
closed?                          → Unavailable("capability has stopped")
不在 service 的 event loop 上?     → Unavailable
admitted >= capacity?            → Failed("capacity exceeded")
request 不是 ModelInvocationRequest → Failed
timeout_seconds 非有限正数        → Failed
role 不在 grant.roles 里           → Unauthorized("Model role is not granted")
response_schema 不匹配            → ModelOutputValidationError
超时                            → Failed（区分 caller deadline / provider timeout）
```

关键设计：**provider 的异常文本不进插件**。`except ModelInvocationError` 分支只复制"我们自己归一化过的文本"（`type(exc)(str(exc))`），其余 `Exception` 一律 `ModelInvocationFailed("Model invocation failed")` + 只记 `type(exc).__name__` 到宿主日志——防止 provider 的报错（常含 endpoint、model id、有时还有凭据片段）经 `__context__` 漏给扩展。`_provider_call` 用 `asyncio.to_thread(create_chat_model, ...)` 构造模型（不可取消），因此 `_closed`/`abandoned` 在构造后**再查一次**。

---

## 五、Skill mutation：最高危的能力，闸门最多

`extension-api` 的 `skill_mutations.py`（161 行）把"让插件改用户 skill"拆成一组**条件更新**原语，`MutationCapabilities`（`:25`）把全部上限写成常量：

| 常量 | 值 | 作用是 |
|------|-----|--------|
| `protocol_version` | `skill-mutations-v1` | 协议钉版本 |
| `max_main_bytes` | 131072 | `SKILL.md` 主体上限 |
| `max_package_bytes` / `max_package_files` | 16777216 / 256 | 整包上限 |
| `max_sources` / `max_pending_proposals` | 20 / 20 | 单次 stage 的源数、每 owner 未决提案数 |
| `max_model_scan_files` / `_bytes` / `_file_bytes` | 32 / 1MiB / 128KiB | 模型扫描的**读预算** |
| `max_concurrent_scans` / `max_owner_plugin_concurrent_scans` / `max_owner_plugin_scans_per_hour` | 4 / 2 / 20 | 扫描配额（按 owner×plugin 分层） |
| `check_timeout_seconds` | 120 | 单次 check |
| `proposal_ttl_seconds` / `check_ttl_seconds` / `rollback_ttl_seconds` | 86400 / 900 / 2592000 | 提案 1 天、检查结论 15 分钟、回滚窗口 30 天 |
| `topology` | `posix-single-host-local-filesystem` | 能力自述 |

### 5.1 启动期三道断言（`extensions/host_capabilities.py:47`）

`HostCapabilities.start()` 在有 mutation 绑定时逐条检查：

1. `skill_mutations.topology == "single_host_local"`，否则 `HostCapabilityError("UNSUPPORTED_TOPOLOGY", ...)`——**没有显式断言就没这个能力**（NFS/CSI 多写者下 rename 语义不成立）。
2. `skill_mutations.owners ⊆ evidence.owners`，否则 `HostCapabilityError("INVALID_GRANT", ...)`——能改 skill 的插件必须**同时**能读完整运行证据，理由是把"改了哪个 skill 的哪个版本"与"哪次 run 提议的"绑在一起，事后可归因。
3. `evidence._supported()` 被显式调用一次以**在启动期就拒绝"看起来能跑"的 API**（存储不支持就现在炸，而不是等第一次 commit 时才发现），`host_capabilities.py:82` 有注释。
4. 数据库后端必须是 `sqlite` 或 `postgres`，否则 `UNSUPPORTED_TOPOLOGY`（`host_capabilities.py:48`）。

### 5.2 恢复生命期与插件解耦（这是重点）

`HostCapabilities` docstring（`host_capabilities.py:23`）写明："Persisted enrollment is intentionally **independent of the current plugin list**: uninstalling a plugin cannot turn off recovery or let an old managed writer bypass an unresolved publication."

落实方式：

- `owners` 集合 = DB 里 `SkillOwnerRow.owner_id` ∪ `SkillAssetRow.owner_id` ∪ grant 里的 owners（`host_capabilities.py:56-64`）——**卸载插件后 owner 行还在，恢复照跑**。
- `_maintain()`（`:127`）每 60 秒 `recover_all()` + `collect_garbage()`，失败只记一句**不含任何候选字节/模型诊断/DB 参数/路径**的 WARNING。
- `close()`（`:139`）顺序固定：停 maintain 任务 → 关各 service → 关 workers → `configure_mutation_runtime(None)` → dispose engine → 释放 topology 锁。`app/gateway/deps.py:932` 在**任何锁/worker 之前**就 `stack.push_async_callback(host_capabilities.close)`，因此 LIFO teardown 里插件先停、宿主后关。

### 5.3 七步集成流与"没有 force"

`docs/skill-evolution-host.md` 的规范流程是 `discover → read_skill → stage → read_proposal_bundle → check → commit → find_operation`：

- `stage` 必须带 `expected_revision: AssetRevision(incarnation_id, mutation_seq, content_digest)`——**乐观并发**，基线变了就失败，没有"覆盖写"选项。
- `commit` 需 `idempotency_key`，可选 `assessment_ref: AssessmentRef(candidate_hash, base_revision, evaluator, evaluator_version, report_id)`——评估结论也被绑到具体 candidate hash + base revision 上，换一个字节就作废。
- `revert` 也要 `expected_current_revision`，且受 `rollback_ttl_seconds` 限制。
- `Operation` 带 `generation` 与 `superseded_by_generation`，故"被后来者取代"是可查状态而不是隐藏行为。
- P0 能力边界：只更新**已存在且启用**的 custom skill 的 `SKILL.md` 正文 + description，不做新建/删除。

### 5.4 管理面路由

`app/gateway/routers/skill_mutations.py` 提供 `APIRouter(prefix="/api/skill-mutations")`、**admin-only**：

| 路由 | 用途 | 校验 |
|------|------|------|
| `GET /operations` | 列操作 | `limit ≤ 100` |
| `GET /operations/{operation_id}` | 查一个操作 | `operation_id` 必须 32-hex |
| `POST /operations/{operation_id}/recover` | 单个恢复 | 503 `UNAVAILABLE` / 404 / 409 映射 |
| `POST /owners/{owner_id}/recover` | 按 owner 批量恢复 | 同上 |

这是**运维面的手动闸门**：自动恢复跑不动（或需要人工判断）时，管理员可以定向触发，而不是等 60 秒。

---

## 六、Completed-run evidence：只读投影，引用不授予权限

`extension-api` 的 `completed_run_evidence.py`（90 行）与 `extensions/completed_run_evidence.py`（322 行）是 2.2.0 最"证据化"的一对：

| 对象 | 行 | 约束 |
|------|-----|------|
| `EvidenceLimits.max_events` | `:12` | 默认 200，**1..2000** |
| `EvidenceLimits.max_bytes` | `:13` | 默认 256 KiB，**1 KiB..1 MiB**（含 envelope） |
| `CompletedRunSnapshot.coverage` | `:43` | `lead-journal-v1` |
| `CompletedRunSnapshot.seal_state` | `:38` | 默认 `"partial"`（配合 `seal_error`），**默认为"未封"而不是"已封"** |
| `CompletedRunEvent.content_sha256` | `:55` | 对**落库的 UTF-8 内容**取 hash，早于任何 preview；`content_bytes` 是内容字节数而非 JSON envelope |

`HostCompletedRunEvidenceReader.__init__`（`extensions/completed_run_evidence.py:51`）的三条硬要求：

1. `plugin_id` 必须是非空稳定串；`owner_ids` 必须是非空、非 `str`/`bytes`、**逐项非空且不含 `*`** 的 owner 白名单——否则 `ValueError`。
2. 内部 `_scope = sha256([plugin_id, sorted(owners)])`（`:59`）——scope 摘要由宿主算，**不来自调用参数**；cursor（`:69`）绑 kinds + position + reference，翻页越界即拒绝。
3. `_sf` 只在 `run_store` 与 `event_store` **共享同一个 session factory** 时才非空（`:59`）；否则所有读路径 `_supported()` 失败。

docstring（`:39`）如实声明边界："This is a supported capability boundary for **trusted in-process plugins**, not a sandbox against code holding a raw database session factory." 以及 legacy digest 的累积上限 **每页 1 MiB / 64 个 SQL chunk / 2 秒**，超限抛 `LIMIT_EXCEEDED`——**绝不编造 hash，也绝不信任事件 metadata 里给出的 digest**。

请求态版本走 `resolve_run_evidence_reader(request)`（`deerflow_extension_api/run_evidence.py`）：resolver 拿的是 **request 对象**而不是调用方自报的 user id，宿主在 `app/gateway/app.py:1237` 实现并要求 `runs:read` 权限；不支持时返回 `None`，鉴权失败抛 `PermissionError`，**其它 resolver 异常直接传播、绝不回退到全局 reader**（全局 reader 是 `user_id=None` 的跨用户可见视图，只给受信 service 用）。

---

## 七、Plugin runtime 的资源上限（拒绝服务面）

| 面 | 上限 | 位置 |
|----|------|------|
| 内联浏览器模块 | 512 KiB | `docs/full-stack-plugins.md` |
| `BrowserAssets` 单文件 | 4 MiB | `extensions/browser_assets.py:15` |
| `BrowserAssets` 整包 | 16 MiB | `:17` |
| `BrowserAssets` 文件数 | 256 | `:18` |
| asset 路径 | ≤512 字符、每段 `[A-Za-z0-9_-][A-Za-z0-9_.-]*` | `browser_assets.py:39` |
| action 请求 body | 256 KiB → 413 | `routers/plugins.py` |
| action handler 时限 | 30 s → 504 | 同上 |
| 模型工具输入 / 输出 | 256 KiB / 64 KiB | `docs/full-stack-plugins.md` |
| 结构化 artifact | 64 KiB | 同上 |
| `AgentRuns.read_artifact` | 2 MiB | `deerflow_extension_api/agent_runs.py` |

`load_browser_assets()`（`browser_assets.py:85`）逐段**拒绝 symlink**（不是只查最终目标）——否则包内一个 `assets/ -> /etc` 就能把整个宿主机变成静态站点。Gateway 侧 assets 路由额外发 `Content-Security-Policy: sandbox` 与 `X-Content-Type-Options: nosniff`（`routers/plugins.py:126-131`），因为 SVG 可以被当文档打开。

### 7.1 插件工具进模型工具面之前的三道校验

| 校验 | 机制 | 为什么 |
|------|------|--------|
| **内联 schema only** | `validate_schema()`（`plugin_tools.py:33`）拒绝 `$ref`/`$dynamicRef`/`$recursiveRef`，并 `Draft202012Validator.check_schema` | 引用解析要么需要网络访问、要么需要读任意文件——两条都不该由插件工具定义触发 |
| **保留参数名** | `runtime` / `config` 不给插件工具用 | 这两个名字由宿主注入，插件重名会覆盖宿主语义 |
| **隔离进程做 schema 检查** | `extensions/model_schema_worker.py` 按**文件路径**起一个独立 Python 进程 | "Expensive schema checking and regex validation must never execute on the Gateway loop or its GIL"；管道上只走有界 JSON 与固定状态词，`_reject_constant()` 拒绝非有限浮点 |
| **工具名可去重** | `plugin_tool_name()` = `ext_{ns[:20]}_{name[:25]}_{sha256(namespace:name)[:12]}`（非字母数字的 namespace 字符折成 `_`） | 两段都截断，所以不同 namespace 的同名工具**只靠摘要后缀区分**——这也是撞名判重必须比较全名、不能比较前缀的原因 |
| **撞名即失败** | `build_plugin_tools()` 撞名抛 `ValueError`（`plugin_tools.py:124`） | 不让"后加载的静默覆盖前者"——那是一个隐藏的权限提升面 |

### 7.2 middleware 顺序是被断言的，不是靠约定

`extensions/ordering.py` 用**声明式不变量**取代手写下标比较：

- 扩展贡献的 middleware 在**校验运行之前**就已经合并，所以任何一条贡献都**不可能绕过**不变量；
- 失败信息**点名是哪个扩展**违反了顺序——否则在十几个贡献者里找一条错序是灾难。

对安全的意义：像 authorization / guardrail / sandbox audit 这类"必须在某个位置"的中间件，其位置不再是注释里的口头约定，而是启动期硬校验。

插件工具名由 `plugin_tool_name()`（`extensions/plugin_tools.py:58`）生成：`ext_{ns[:20]}_{name[:25]}_{sha256(namespace:name)[:12]}`——截断 + 摘要后缀，保证不同 namespace 的同名工具不会撞车；`build_plugin_tools()` 还对撞名的工具直接 `ValueError`（`plugin_tools.py:140`），而不是让后一个静默覆盖。schema 校验（`validate_schema`，`:33`）只接受**内联** schema：出现 `$ref`/`$dynamicRef`/`$recursiveRef` 一律拒绝（不做引用解析、不做网络访问），并保留参数名 `runtime` / `config` 不给插件工具用。

---

## 八、Agent run 控制面：宿主代持身份

`deerflow_extension_api/agent_runs.py`（167 行）让插件**以调用者的身份**发起/读取/取消 agent run，而不是以插件自己的身份：

- `resolve_agent_runs(request)`（`:153`）只从 `request.app.state` 的 resolver 取，**绝不接收调用方给的 user id**；身份不一致抛 `PermissionError`，**没有 ambient user 回退**。
- `_BoundAgentRuns._request()`（`app/gateway/extension_agent_runs.py:98`）每次操作都重新验：`host.active`、用户仍存在、`token_version` 未变、`needs_setup` 为假、`permissions ∩ resolve_route_permissions(user)` 仍包含所需权限——**撤回即失效**，句柄不是长期凭据。
- **PAT 不算**：`bind()`（`:63`）只接受 `AUTH_SOURCE_SESSION` 与 `AUTH_SOURCE_AUTH_DISABLED`，注释写明"PAT revocation and internal-owner delegation need separate durable grants. Never turn either into an unrestricted session capability."——PAT 撤销无法立即反映到长期句柄上，所以干脆不给。
- `request.state.run_origin = make_origin("extension", namespace=...)`（`:118`）：来源由**宿主盖章**，不是 HTTP 输入。
- 线程访问额外过 `thread_store.check_access(..., require_existing=True)`（`:127`）：历史只读路由可以接受未登记的 legacy 线程，**委托句柄不行**。

### `ExecutionFence`（2.2.0 契约新增）

`agent_runs.py:25` 的 `ExecutionFence(namespace, resource_id, holder_id, epoch)` 把"哪个进程有权推进这次执行"变成数据库里的一行租约：表 `extension_execution_leases`，复合键 `(namespace, resource_id)`，外加 `user_id`/`holder_id`/`epoch BIGINT`/`expires_at`（DB 时钟 Unix 秒）。规则写在 docstring 里：**每次 takeover 递增 epoch、保留 tombstone、加锁串行化获取**；宿主在准入与取消事务**内部**锁该行并校验 user/holder/epoch/expiry。

诚实边界（同一段 docstring）："This fences **new admission/cancellation**, not arbitrary external effects from an admitted Agent."，并且 `start` 还额外要求跨进程 stream bridge——即它防的是双写/脑裂推进，不防已准入的 agent 干坏事。

---

## 九、仍然存在的缺口

| 缺口 | 说明 |
|------|------|
| 声明式页面未 gate | `plugin_page` resource 与 `afilter_plugin_pages` 已就绪，policy key 与 Gateway 调用点未落地（见 2.5） |
| `PermissionError` 未翻译 | `require_plugin_management` 失败逃逸成 500，插件必须自己转 403/503 |
| 插件代码无沙箱 | 插件与 Gateway 同进程同权限；`host_access` 是"归属 + 防误用"，不是隔离 |
| model invocation 无货币预算 | 只有并发/字符/时限上限，没有金额或 token 总量配额 |
| 多 Gateway 无故障切换 | AgentRuns / ExecutionFence 契约明确单进程、单 store；"POSIX, one process/store" 写在根 `AGENTS.md` |
| evidence 覆盖不完整 | `coverage_limits` 自述：后台 subagent、远程 MCP、外部副作用无完整覆盖；对话正文与附件正文不在其中；skill 实际内容 hash 除非记录否则未知 |
| skill mutation 单机限定 | `posix-single-host-local-filesystem`；NFS/CSI 或多写者部署直接不支持 |

---

## 十、配置速查

```yaml
# config.yaml（operator 独占；任何改动都要重启）
plugins:
  - name: acme.reports                       # host_access 存在时必须显式、稳定
    use: acme_ext.reports:install
    enabled: true
    config: { ... }
    host_access:
      # 读完整运行证据（completed-run evidence）的 owner 白名单，禁止通配
      evidence:
        owners: [u_1, u_2]
      # 改 skill 的能力：必须同时具备 evidence.owners，且显式断言单机拓扑
      skill_mutations:
        topology: single_host_local          # 不写 → 启动期 UNSUPPORTED_TOPOLOGY
        owners: [u_1]                        # 必须是 evidence.owners 的子集
        operations: [stage, check, commit, revert]
        trigger_agents: [lead_agent]
        target_skills: [weekly-report]       # 规范 skill 名
      # 调模型：只能点逻辑 role，不能点具体模型
      model_invocation:
        roles: { summarizer: gpt-4.1-mini }
        max_concurrency: 2
        timeout_seconds: 60
        max_input_chars: 262144
        max_output_chars: 65536

authorization:
  enabled: true
  provider:
    use: deerflow.authz.rbac:RbacAuthorizationProvider
  roles:
    analyst:
      plugin_actions: ["acme.reports/run-report"]      # 单 action
      plugin_management: ["acme.reports/permissions.read"]
      plugin_actions: ["acme.reports/ex-port"]         # action 名允许 - 与 _，不允许 .
# 未列 plugin_actions / plugin_management 的 role = 这两类资源不受限（向后兼容）
# plugin_pages 键尚不存在：声明式页面授权是后续 slice
```

---

> **See also:** [03-guardrail.md](03-guardrail.md)（工具级风险门） · [04-trust-boundary.md](04-trust-boundary.md)（端到端信任链） · [01-auth.md](01-auth.md)（RBAC 与 principal） · [../../internals/harness-hooks/09-packaged-extensions.md](../../internals/harness-hooks/09-packaged-extensions.md)（加载/注册机制） · [../it-ops/03-policy-enforcement.md](../it-ops/03-policy-enforcement.md)（治理视角）
