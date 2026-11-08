---




title: "Capability 目录 — 清单 schema、adapter 注册表与发现 API"
description: 'Capability 目录 — 清单 schema、adapter 注册表与发现 API：架构、契约与源码锚点。'
topics: [capabilities, catalog, manifest, adapters, gateway, api]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Capability 目录 — 清单 schema、adapter 注册表与发现 API

本页覆盖「**目录**」这一半：清单长什么样、怎么校验、怎么派发到既有服务。另一半（installation identity 与 Agent 工具选择）见 [02-installation-identity-and-agent-selection.md](02-installation-identity-and-agent-selection.md)；三个需要自带 HTTP 客户端的 provider 见 [03-bundled-business.md](03-bundled-business.md)。

## 相关文件

- `deerflow/capabilities/catalog.py`（51 行）— `PluginManifest`（`catalog.py:10-41`）+ `load_catalog()`（`catalog.py:44-51`）
- `deerflow/capabilities/builtin.json`（732 行）— 15 条清单数据，被上面两者校验并在 Gateway 的 `/api/capabilities/catalog` 原样投影
- `app/gateway/capabilities.py`（249 行）— `CapabilityInstallation` / `InstallationList` / `AdapterContext` / `CapabilityAdapter` 协议 + 4 个 adapter + `AdapterRegistry` + `list_installations()`
- `app/gateway/routers/capabilities.py`（51 行）— `/api/capabilities/catalog`、`/installations/{adapter}`、`POST /installations`
- `app/gateway/app.py:1344` — `app.include_router(capabilities.router)`
- `backend/tests/test_capability_registry.py`（90 行）/ `backend/tests/test_capability_api.py`（262 行）/ `backend/tests/blocking_io/test_capabilities_router.py`（27 行）

---

## 1. 清单 schema：`PluginManifest`（`catalog.py:10-41`）

`model_config = ConfigDict(extra="forbid")`（`catalog.py:11`）——**清单多写一个键就是加载失败**，不允许自由扩展。

| 字段 | 行号 | 约束 | 语义 |
|------|------|------|------|
| `schema_version` | `catalog.py:13` | `Literal[1] = 1` | 清单版本，与 provider 版本无关 |
| `id` | `catalog.py:14` | `^[a-z0-9][a-z0-9.-]*$`，≤128 | 唯一键；重复即加载失败 |
| `version` | `catalog.py:15` | 1–80 字符 | **这个清单**的版本，不是远端服务探测出的版本（`docs/capability-center.md` 同义） |
| `name` / `description` / `setup` | `catalog.py:16-18` | `dict[str, str]` | 本地化文案（`en-US` / `zh-CN`） |
| `category` | `catalog.py:19` | 6 值枚举 `office/knowledge/research/business/development/custom` | 画廊分组 |
| `kind` | `catalog.py:20` | 3 值枚举 `mcp/cli/native` | **执行机制** |
| `adapter` | `catalog.py:21` | `^[a-z][a-z0-9_-]*$` | **选择集成流程**（与 `kind` 正交，见下） |
| `source` | `catalog.py:22` + 校验器 `catalog.py:29-34` | **必须 `https://` 开头** | 提供方文档链接 |
| `icon` | `catalog.py:23` + 校验器 `catalog.py:36-41` | 必须是 `/images/plugins/` 下的本地资源，禁止 `..`、`?`、`#` | 品牌图；不得指向远端 |
| `aliases` | `catalog.py:24` | 默认 `[]` | 搜索别名 |
| `auth_methods` | `catalog.py:25` | `none/api_key/oauth` 子集 | 账号机制，**不代表已实现交互式 OAuth** |
| `contributions` | `catalog.py:26` | `tools/skills` 子集 | 该条目贡献什么 |
| `config_schema` | `catalog.py:27` | 默认 `{"type": "object"}` | 前端表单描述 |

**`kind` 与 `adapter` 是两件正交的事**——这是 `docs/capability-center.md` 显式点出的设计。实测 15 条里的分布：

| `kind` → `adapter` | 条数 | 条目 |
|--------------------|------|------|
| `mcp` → `mcp` | 6 | tencent-docs（`builtin.json:151`）、notion（`:207`）、openviking（`:262`）、database（`:472`）、github（`:582`）、atlassian（`:637`） |
| `mcp` → `business` | 3 | dingtalk（`:42`）、wecom（`:99`）、hubspot（`:531`） |
| `native` → `guide` | 4 | web-search（`:318`）、exa（`:398`）、firecrawl（`:435`）、browser（`:695`） |
| `native` → `guide` | 1 | web-fetch（`:360`） |
| `cli` → `lark` | 1 | lark（`:3`） |

即：`kind` 只说"执行靠 MCP / CLI / 原生工具"，`adapter` 才决定"安装时走哪个集成流程"。dingtalk/wecom/hubspot 的 `kind` 是 `mcp`，但 `adapter` 是 `business`——它们**最终也落成 MCP server 配置**，只是 launcher 由 server 生成（见 [03-bundled-business.md](03-bundled-business.md)）。

`auth_methods` 的实际分布：5 条 `guide` 条目一律声明 `["none","api_key"]`；6 条 `mcp` 条目一律 `["api_key","oauth"]`；3 条 `business` 条目 `["api_key"]`；lark 单独 `["oauth"]`。`contributions`：只有 lark 是 `["tools","skills"]`，其余 14 条是 `["tools"]`。

`config_schema` 的三种形状：

- **`guide` 与 lark**：`properties: {}` + `additionalProperties: false`（无表单）。
- **`mcp` 型**：`name` / `url` / `authorization`（`format: "password"`）三字段，`required` 含 `name`+`url`。
- **`business` 型**：**没有 `url` 字段**，只有 provider 凭据——dingtalk 是 `name`/`access_token`/`sign_secret`，wecom 是 `name`/`webhook_key`，hubspot 是 `name`/`access_token`。这与 `business.py` 的 `CREDENTIALS` 白名单严格一致（键名完全对齐，`business.py:24-28`）。

## 2. `load_catalog()`：三条失败策略（`catalog.py:44-51`）

```python
source = path or Path(__file__).with_name("builtin.json")     # :46
items = [PluginManifest.model_validate(i) for i in json.loads(source.read_text(encoding="utf-8"))]  # :47
ids = [item.id for item in items]                             # :48
if len(ids) != len(set(ids)):
    raise ValueError("Duplicate plugin identifiers in catalog")  # :50
```

1. **默认只读包内 `builtin.json`**；`path` 参数是给测试与"运维另供一份清单"用的入口（docstring `catalog.py:45`：*"An operator may supply another manifest file; never load executable code."*）。目前生产调用方全部不传 `path`。
2. **逐条 pydantic 校验**，`extra="forbid"` + `source`/`icon` 两个校验器 → 任何不合规条目让整个目录加载失败（不是跳过该条）。
3. **id 重复 → `ValueError`**，不静默取第一条。`test_capability_registry.py:43-50` 用临时 JSON 复制同一 manifest 两份钉住这条。

失败的影响面：`GET /api/capabilities/catalog` 直接抛 500（`routers/capabilities.py:26-28` 没有 try/except）；`POST /installations` 在 `load_catalog()` 之后才找 manifest（`routers/capabilities.py:43-46`），所以目录坏了安装也一起坏。**这是有意的 fail-closed**——目录是部署物，坏了应该在启动/请求时立刻可见，而不是悄悄变少。

## 3. Gateway 侧 adapter 注册表（`app/gateway/capabilities.py`）

### 3.1 契约

```python
@dataclass(frozen=True)
class AdapterContext:                     # capabilities.py:44-49
    request: Request
    config: AppConfig
    user_id: str
    scope: Literal["deployment", "user"] = "deployment"

class CapabilityAdapter(Protocol):        # capabilities.py:52-55
    async def list_installations(self, context: AdapterContext) -> list[CapabilityInstallation]: ...
    async def install(self, context, manifest: PluginManifest, name: str, configuration: dict[str, Any]) -> None: ...
```

`scope` 是 `AdapterContext` 的**唯一开关**：同一个 adapter 在不同 scope 下读不同的存储（部署 `extensions_config.json` vs 用户 `mcp.json`）。`AdapterRegistry.register()` 对重名直接 `ValueError`（`capabilities.py:222-225`），注册发生在模块导入期（`capabilities.py:234-238`），所以重复注册是启动期崩溃而不是运行期覆盖。

`registry.get(name)` 对未注册 adapter 抛 **422** 而不是 404：`"This capability only has a setup guide; no installation adapter is available"`（`capabilities.py:227-231`）。这就是 5 条 `guide` 条目的处理方式——它们在目录里可见，但**点"安装"会被 422**，前端在 `plugin-gallery.tsx:57,69,132` 用 `adapter === "guide"` 把按钮文案换成"查看指南"并跳过安装调用。

### 3.2 四个 adapter

| adapter | 类 | list_installations | install |
|---------|----|--------------------|---------|
| `mcp` | `MCPAdapter`（`capabilities.py:89`） | 读 `servers` 原始 JSON（部署态 `mcp._load_raw_mcp_server_responses`，用户态 `read_user_mcp_config`），投影成 `CapabilityInstallation`，**只输出安全字段** | `validate_mcp_connection()`（HTTP/SSE 要合法 URL 且无内嵌凭据；stdio 要 command）→ 盖 `capability` 元数据 → 复用 `mcp.create_mcp_servers()` / `personal_mcp.create_servers()` |
| `business` | `BusinessAdapter(MCPAdapter)`（`capabilities.py:156`） | `super().list_installations()` 后按 `plugin_id in CREDENTIALS` 过滤 | 先 `connection_config(manifest.id, configuration)` 生成固定 launcher（ValueError → 422），再走 `MCPAdapter.install` |
| `lark` | `LarkAdapter`（`capabilities.py:173`） | 调 `get_lark_integration_status(user_id, config)`，把 `installed` / `manifest_version` / `auth.status` 投影（`auth_status` 三态：`connected` 仅当 `authenticated and verified`，`configured` 当 `authenticated`，否则 `required`） | 委托 `integrations.install_lark()` |
| `skills` | `SkillAdapter`（`capabilities.py:195`） | `skills._get_user_skill_storage(...).load_skills(enabled_only=False)` + `_filter_visible_skills()`（**与 `/api/skills` 同一可见性策略**，含 `authorization.fail_closed` 语义，`routers/skills.py:462-485`） | 直接 422：`"Use the existing skill archive upload API"`（`capabilities.py:214-215`） |

注意 `BusinessAdapter.list_installations` 里对 `CREDENTIALS` 的 import 是**函数内延迟导入**（`capabilities.py:160`）——`capabilities.py` 顶部已经 import 了 `connection_config`（`:13`），这处内层 import 在源码上冗余，考证不到具体动机（可能是避免循环导入权衡的残留）。**未逐行核实**是否存在循环依赖路径。

### 3.3 安全投影（`MCPAdapter.list_installations`，`capabilities.py:90-136`）

MCP 条目的连接定义里含 URL / command / env / headers / OAuth；公开发现**逐字段挑白名单**，而不是"挑黑名单删除"：

- 输出字段只有 `id / plugin_id / adapter / name / reference / description / enabled / version / auth_status / health / scope / icon / selectable`（`CapabilityInstallation`，`capabilities.py:21-36`）。
- 注释原文（`capabilities.py:116-117`）：*"Public discovery projects explicit safe fields, never connection URLs, commands, env, OAuth configuration, or another user's IDs."*
- `icon` 只接受 `presentation.icon` 且必须是 `data:image/png;base64,` 前缀、≤100 000 字符（`capabilities.py:133`）——与前端"只渲染本地/受控 PNG"的规则配套。
- `plugin_id` / `version` 非法类型时降级为 `None`（`:124,131`），不让脏的 legacy 扩展字段炸掉整个列表（`test_capability_api.py:20` 就用 `"capability": {"plugin_id": 42}` 这种脏数据钉住）。
- `auth_status` 的推导（`:107-113`）：`user_auth.enabled` → 看该 user 是否有映射（`configured` / `required`）；否则若有 `oauth` / `headers` / `env` 任一 → `configured`；都没有 → `not_required`。**`configured` 只表示"有凭据"，不代表连接测试成功**；`health` 固定 `unknown`（没有 live check 时有意为之，`docs/capability-center.md` 同义）。

`test_capability_api.py:38-47` 把这条钉死：带 `headers: {"Authorization": "Bearer private-secret"}` 与 `https://private.example/mcp` 的 heritage server，响应文本里不能出现 `private-secret` / `private.example` / `Authorization` / `headers` 任何一个。

## 4. 三个端点与权限闸门（`routers/capabilities.py`）

| 方法/路径 | 行号 | 权限 | 语义 |
|-----------|------|------|------|
| `GET /api/capabilities/catalog` | `:26-28` | 认证用户可读（router docstring `:1`：*"Capability discovery is public to authenticated users"*） | `await asyncio.to_thread(load_catalog)`——**文件读不占事件循环** |
| `GET /api/capabilities/installations/{adapter}?scope=` | `:31-33` | 认证用户可读；`scope ∈ {deployment,user,all}` | 委托 `list_installations()` |
| `POST /api/capabilities/installations` | `:36-51` | 见下 | 查找 manifest → `registry.get(manifest.adapter).install(...)` → 回读该 adapter 的列表 |

`POST` 的权限规则（`routers/capabilities.py:37-51`）逐句是：

1. `body.scope` 默认 `"deployment"`（`InstallRequest`，`:18-23`，`extra="forbid"`，`name` ≤128）。
2. `scope == "deployment"` → `require_admin_user(...)`（403，`deps.py:1442-1450`）。**PAT 一律不算 admin**（`deps.py:1428-1434`：*"PAT credentials never carry admin capability"*），所以"管理员用自动化 token 装插件"会 403——这是与 `/api/mcp/config` 共用的一条既有规则。
3. `scope == "user"` → `user_id` 改成真实登录用户 id；`user_id = get_effective_user_id()` 的默认值只在部署态使用。
4. `scope == "user"` 且 `manifest.adapter not in {"mcp", "business"}` → **仍要 admin**（`:47-48`）。即普通用户可自助安装的只有 MCP 与内置 business 两类；lark（个人 OAuth 账号流程）与 skills 走各自既有 API。
5. manifest 找不到 → **404 "Plugin not found"**（`:45-46`）；adapter 未注册（`guide`）→ **422**（`capabilities.py:230`）。
6. 安装成功后再 `list_installations(manifest.adapter, request, config, body.scope)` 回读并返回 `InstallationList`（`installation` + `can_manage`）。

前端 `frontend/src/core/capabilities/hooks.ts:37-58` 的 `useInstallCapability` **硬编码 `scope: "user"`**——网页端自助安装天然走个人态。反过来，**部署态安装必须走管理员 API**（`/api/mcp/config*`）或直接改文件。

`can_manage` 的定义（`capabilities.py:249`）：`scope == "user" or await is_admin_user(request)`。部署态且非管理员 → `can_manage: false`，前端据此把共享条目渲染成只读。

### scope 语义（`list_installations`，`capabilities.py:241-249`）

- `deployment`（默认）：用 `get_effective_user_id()` 的内置默认用户，读部署配置。
- `user`：`user_id` 取真实登录用户，读个人文件。
- `all`：仅对 `mcp` / `business` 生效，**先部署 + 再追加用户**两份列表（`:247-248`）。lark/skills 的 adapter 本身已经按用户过滤，不重复追加。

`GET /installations/{adapter}` 的失败隔离是**按请求边界**而不是按条目：`AdapterRegistry.get()` 未注册 → 422（`test_capability_api.py:93` 断言 `/installations/unknown` 是 422）；某个 adapter 内部抛错（比如个人 MCP 文件损坏 → `mcp._raise_invalid_mcp_configuration`）就只影响该 adapter 的那一次请求，前端 `plugin-gallery.tsx:139` 用 `states[index]?.isError` 给单个 adapter 标"不可用"而不是整页失败。

## 5. 文件读在事件循环外

`catalog()` 与 `install()` 都写 `await asyncio.to_thread(load_catalog)`（`routers/capabilities.py:28,43`）；`MCPAdapter` 的两次存储读也各自 `await asyncio.to_thread(...)`（`capabilities.py:95,100`），`SkillAdapter` 用 `asyncio.to_thread(lambda: ...)`（`:197`），`LarkAdapter` 用 `asyncio.to_thread(get_lark_integration_status, ...)`（`:175`）。这是 app 层"blocking I/O 必须在循环外"纪律的一个具体落点，`blocking_io/test_capabilities_router.py`（27 行）专门钉住 catalog 与 installation 两条读路径。

## 6. 前端配套（一句话）

`frontend/src/core/capabilities/{types,hooks,static}.ts` 与 `components/workspace/capabilities/*` 消费本节的 catalog + 安全投影，**不在本包内**。两条硬规则：`plugin-catalog.ts` 只做本地化文本与显式安装元数据解析，**禁止从 server 显示名推断 provider 身份**；静态 demo 的 `builtin.demo.json` 由 `pnpm catalog:sync` 从 `builtin.json` 生成（`frontend/scripts/sync-capability-catalog.mjs:6-13`），改清单必须重跑。前端域细节见 [../../frontend/04-workspace-layout.md](../../frontend/04-workspace-layout.md)。
