---
title: "Skills 与 Tool 系统"
description: 'Skills 加载（legacy + deferred 双模式）、request-scoped secrets、slash 激活、Tool 装配链。'
topics: [skills, tools, prompt-engineering]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Skills 与 Tool 系统

Skills 是可复用、可组合的 Agent 能力模块。每个 Skill 是一个包含 `SKILL.md` 的目录。

## 目录结构

```
skills/
├── public/                          # 已提交到 Git
│   ├── deep-research/
│   │   └── SKILL.md
│   └── ...
└── custom/                          # gitignored，用户/Agent 安装
    └── my-custom-skill/
        └── SKILL.md
```

## SKILL.md 格式

```markdown
---
name: deep-research
description: Deep research on any topic
license: MIT
allowed-tools: [web_search, web_fetch, read_file, write_file]
required-secrets: [GITHUB_TOKEN]           # 🆕 可选：skill 需要的密钥
secrets-autonomous: true                    # 🆕 可选：agent 自主加载时是否绑定密钥
---

# Deep Research Skill

Instructions for conducting deep research...
```

YAML frontmatter：

| 字段 | 说明 |
|------|------|
| `name` | 唯一标识 |
| `description` | 简述，LLM 选择 skill 时依赖此字段 |
| `license` | 许可证 |
| `allowed-tools` | ⚠️ 2.2 起**只是兼容元数据**，不再过滤/授予任何工具（见[下文专节](#allowed-tools从工具过滤器降级为兼容元数据--22-重大变更)）。解析本身未变：标量形式支持可移植拼写（`Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`/`WebFetch`/`WebSearch` 映射到 `bash`/`read_file`/`write_file`/`str_replace`/`glob`/`grep`/`web_fetch`/`web_search`），未知名保持原样；分词器保留引号与括号模式（含空格/转义括号）内部完整，未闭合引号或括号直接报错（#4984） |
| `required-secrets` | 🆕 字符串或 `{name, optional}` 列表——skill 需要的请求级密钥 |
| `secrets-autonomous` | 🆕 `true`（默认）= agent 自主加载时绑定密钥；`false` = 仅显式 `/skill-name` 激活时绑定 |

**白名单全集（11 个键）**：`ALLOWED_FRONTMATTER_PROPERTIES = {name, description, license, allowed-tools, argument-hint, required-secrets, secrets-autonomous, metadata, compatibility, version, author}`（`deerflow/skills/frontmatter.py:14-26`）。上表 6 个之外还有 `argument-hint`、`metadata`、`compatibility`、`version`、`author`——它们能通过安装/写入门校验，但不参与运行时装配。未知键在安装/写入门是**硬失败**（`skills/validation.py:42-44`），在 review core 里只是 warning `structure.unknown-frontmatter-field`（`skills/review/analyzer.py:164-175`）。非字符串 YAML 键会被 `str()` 化后当成未知字段，而不是崩溃（`frontmatter.py:57-62`）。

**frontmatter 定界符边界（2.2 收紧）🆕**：`_FRONTMATTER_RE` 从 `^---\s*\n(.*?)\n---\s*\n?` 改为 `^\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)`（`frontmatter.py:31`，`re.DOTALL`）。三条硬边界：① 开头可带 **UTF-8 BOM**（Windows Notepad / PowerShell `Set-Content -Encoding UTF8` 会写），匹配时被吃掉，frontmatter 与正文都不再携带它；② 定界符后的空白**只允许空格/制表符，且必须仍在单独一行**——旧写法会把正文的缩进一并吃掉；③ 结尾必须是恰好三个连字符，像 `---suffix` 这样的前缀行**不能**关闭 frontmatter。LF 与 CRLF 都接受；正文空白原样保留。回归见 `tests/test_skill_frontmatter_boundaries.py`（`skills/AGENTS.md`「Frontmatter boundaries」）。运行时解析、安装校验、review 三条路径共用这一个正则。

## 🔄 加载模式：Legacy vs Deferred Discovery

Skill 加载有两种模式，由 `skills.deferred_discovery` 控制（默认 `false`，即 legacy 模式）。

### Legacy 模式（默认）

```
LocalSkillStorage.load_skills()
    │  递归扫描 skills/{public,custom}
    ├── 解析 YAML frontmatter
    ├── 读取 extensions_config.json 的启用状态
    └── 返回 List[Skill]
        │
        ▼
apply_prompt_template()
    │  全量注入 <available_skills> XML 块
    │  包含 name, description, category, file_path
    │  → 系统 prompt 前缀缓存不稳定（skill 数量变化即失效）
```

### Deferred 模式（`skills.deferred_discovery: true`）

```
SkillCatalog（不可变，可搜索的内存索引）
    │  三种查询模式（#5369 起排序语义与 tool search 分化）：
    │  - select:name1,name2  → 精确匹配，无结果上限
    │  - +keyword rest       → name 必须含 keyword，其余项按 intent 排序（上限 5）
    │  - free text           → 按 intent 匹配 name+description（上限 5）
    │
    ▼
describe_skill 工具
    │  注册到 agent 工具列表
    │  闭包持有 catalog 引用
    │  返回 Command(ToolMessage) 包含结构化元数据
    │
    ▼
系统 prompt
    │  <skill_system> 块只含 <skill_index>（名字列表）
    │  → 前缀缓存稳定，元数据按需加载
```

**对比**：

| 维度 | Legacy | Deferred |
|------|--------|----------|
| Prompt 大小 | 全量 metadata | 仅名字列表 |
| 前缀缓存 | skill 变化即失效 | 稳定 |
| Agent 工具 | 无 `describe_skill` | 有 `describe_skill` |
| 发现方式 | 预加载 | 按需 fetch |

源码：`deerflow/skills/catalog.py`（`SkillCatalog`），`deerflow/skills/describe.py`（`build_describe_skill_tool`，`build_skill_search_setup`）

**Intent 排序 🆕（#5369）**：free-text 与 `+keyword` 查询不再做正则命中计数，改用**字面 intent 词排名**（`_rank_by_intent` / `_intent_score`）：从查询提取有界去重的字面词，按（词覆盖度、name 命中权重、词序相邻度等多级 score 元组）排序，未命中的 skill 仅在 `include_unmatched` 时追加在尾部。与 tool_search 共享查询语法但排名语义刻意不同。

**deferred 装配契约（`skills/describe.py`，补深）**：

- `build_skill_search_setup(skills, *, enabled, container_base_path=..., skill_authorization=None) -> SkillSearchSetup(describe_skill_tool, skill_names)`：`enabled=False` 或 `skills` 为空 → `SkillSearchSetup(None, frozenset())`，agent **回退到 legacy 全量元数据 prompt**；否则用**过滤后的**列表建 `SkillCatalog`，`skill_names = catalog.names`（`describe.py:156-183`，dataclass 见 `:36-49`）。`skill_authorization` 由 `make_lead_agent()` 从 `deerflow.authz.skill_filter` 解析后透传（`agents/lead_agent/agent.py:1164-1168,1297-1302`）。
- `build_describe_skill_tool(catalog, *, container_base_path=..., skill_authorization=None)`（`describe.py:52-154`）用 `StructuredTool.from_function(func=describe_skill, coroutine=adescribe_skill, ...)` 同时挂同步与协程：同步调用（`invoke`、测试、同步链）走 provider 的同步 `authorize()`，异步调用（`ainvoke`，即 agent 实际执行路径）在事件循环上 `await aauthorize()`——**loop-affine 的自定义 provider 绝不能看到同步 API**。无匹配返回文本 `"No skills matched: {query}"`，命中返回 markdown 块；返回值是 `Command` 包 `ToolMessage(name="describe_skill")`，**不写 graph state**（不同于会提升 deferred tool 的 `tool_search`）。
- **`skill:activate` 动作级授权门 🆕（2.2）**：catalog 只装 Layer 1 的**可见性**集合（与动作无关），所以一个带动作感知的 provider 可能列出模型不该加载的 skill。`skill_authorization` 非 `None` 时，命中项还要过 `skill_activation_allowed()` / `skill_activation_allowed_async()`（`authz/skill_filter.py`）；被拒的 skill **从输出里静默剔除**，与"没匹配"不可区分（不泄露原因），失败按 provider 配置的 fail-closed / fail-open 走，只记 `describe_skill: omitted N skill(s) denied by the skill:activate policy`（`describe.py:78-101`）。`None`（授权关闭）时照常描述全部 catalog。
- 渲染时 name / description / allowed-tools / 容器路径全部做 HTML entity 转义——frontmatter 是不可信输入，不转义就能伪造框架标签（`_render_skill_metadata`，`describe.py:188-207`）。allowed-tools 行的前缀固定是 `Allowed tools (compatibility metadata, not enforced):`，`None` 渲染为 `(not declared)`、显式空声明渲染为 `(empty declaration)`。
- `get_skill_index_prompt_section(*, skill_names, container_base_path, skill_evolution_section="")` 名字为空返回 `""`；否则按名排序渲染 `<skill_system>…<skill_index>…</skill_index>`，响应里固定写一句「`allowed-tools` 是别的 agent 框架的兼容信息，在 DeerFlow 既不收紧也不授予工具；你的工具由 Agent 配置与授权控制」，并附 `Skills are located at: {container_base_path}`（`describe.py:213-252`）。
- **catalog 查询边界**（`skills/catalog.py`）：`select:` 在截断之前解析，无长度/结果上限且保持 catalog 顺序；其它查询先截断到 `MAX_QUERY_CHARS=256` 字符（`:26`）；裸 `+`（无 required token）→ `[]`；单字符 ASCII term 按整词匹配，`a`/`I` 被忽略（其余单字符保留，如 C++/R）；词数上限 `MAX_QUERY_TERMS=16`（`:27`）；结果上限 `MAX_RESULTS=5`（`:25`）；同分稳定排序保留 catalog 顺序（`_intent_score` 5 元组 `:77-100`，`_rank_by_intent` `:103-117`，`search` `:144-180`）。`SkillCatalog` 是 frozen dataclass 但**不能加 `slots=True`**：`names` / `_search_index` 是 `cached_property`，靠 `__dict__` 缓存（`:119-143`）。

## `/skill-name` 斜杠激活

文件：`deerflow/agents/middlewares/skill_activation_middleware.py`

`SkillActivationMiddleware` 检测用户消息中的 `/skill-name task` 语法：

1. `parse_slash_skill_reference()` 解析严格格式（`skills/slash.py:39-51`）
2. 拒绝保留命令（10 个，见下）
3. 解析到的 skill 必须已启用且在 agent 白名单内
4. 注入 `SKILL.md` body 为隐藏 HumanMessage（`hide_from_ui: True`），插入到触发消息之前
5. 记录审计事件 `middleware:skill_activation`（name、category、path、content_hash——不含 body）

**保留命令全集 🆕（2.2 扩容）**：`RESERVED_SLASH_SKILL_NAMES = {agent, bootstrap, context, goal, help, memory, model, models, new, status}`（`skills/slash.py:17`）——2.1 的 8 个之外新增 **`context`** 与 **`model`**。唯一的例外分支：`context` 不是无条件保留——只有当其后文本（去空白、casefold）**不等于** `compact` 时才返回 `None`；即 `/context compact` 会被当成一次**普通 skill 激活引用**放行，其它 `/context …` 继续是控制命令（`_CONTEXT_COMPACT_ARGUMENT = "compact"`，`slash.py:19,44-47`）。这条分支必须与前端的 composer 行为一致，否则 `/context compact` 会在一侧被吞掉。

**跨语言契约**：保留名单与 skill 名语法由 `contracts/slash_skill_contract.json` 固定，后端解析器 `deerflow/skills/slash.py` 与前端展示解析器 `frontend/src/core/skills/slash.ts` 必须一致——否则 transcript 会为后端根本不会当作激活的文本渲染激活 chip。约定内容：`reserved_slash_skill_names` = `agent` / `bootstrap` / `context` / `goal` / `help` / `memory` / `model` / `models` / `new` / `status`（**10 个**保留控制命令）；`skill_name_pattern` = `^/([a-z0-9]+(?:-[a-z0-9]+)*)(?:\s+|$)`。两侧各有一份契约测试（`backend/tests/test_slash_skill_contract.py`、`frontend/tests/unit/core/skills/slash-contract.test.ts`）钉住 fixture。注意 fixture 只固定"名单 + 语法"两件事，`context compact` 这个**参数级例外**不在 fixture 里，两侧各自实现（后端 `slash.py:46`，前端 `frontend/src/core/skills/slash.ts:48`）。

## Request-Scoped Secrets

完整六步生命周期，允许调用方传递短期密钥给 skill 脚本，值不进入 prompt、不进入 trace、不 checkpoint。

**1. 声明** — Skill 在 `SKILL.md` frontmatter 中声明 `required-secrets:`。解析结果：`SecretRequirement(name, optional)`。`name` 既是 lookup key 也是环境变量名。

**2. 携带** — 调用方在 run request 的 `context.secrets` 中传递 `{name: value}` mapping。永远不在 message 中，不在 checkpoint 中。

**3. 绑定** — `SkillActivationMiddleware._resolve_secret_bindings()` 在每个 model call 上重算注入集。两个来源取并集：
- **斜杠源**：当前 run 最近一次 `/skill` 激活的 canonical container path
- **上下文源**：`ThreadState.skill_context` 中 model 实际加载过的 skill

两个源都实时对照 registry 解析（不信任存储数据）。授权三重门：enabled × caller-supplied × declared（交集语义）。`secrets-autonomous: false` 阻止上下文源但不阻止显式斜杠。

**4. 注入** — `bash_tool` 读取 context 中的 `__active_skill_secrets`，传给 `execute_command(env=...)`。AIO sandbox 走 `bash.exec` API（需要镜像 ≥1.9.3）。

**5. 擦洗** — `env_policy.build_sandbox_env()` 从继承环境删除 `*KEY*`、`*SECRET*`、`*TOKEN*`、`*PASSWORD*`、`*CREDENTIAL*`、`*DSN*`，以及 `DATABASE_URL`、`REDIS_URL` 等连接串常量名。Benign 变量（`PATH`、`HOME`、`LANG`）保留。

**6. 脱敏** — `secret_context.REDACTED_CONTEXT_KEYS` 确保 secret-bearing context key 从 trace、log、持久化 run record、API 响应中剥离。

源码：`deerflow/runtime/secret_context.py`，`deerflow/sandbox/env_policy.py`

## 加载流程

```
LocalSkillStorage.load_skills()          # 同步纯扫描；调用方负责 offload（同步 API 亦被直接调用）
    │  递归扫描 skills/{public,custom} 寻找 SKILL.md
    │
    ├── 解析 YAML frontmatter（包含 required-secrets；一律以 encoding="utf-8" 读取，
    │   不依赖平台 locale，无效 UTF-8 按解析错误处理，#4995）
    ├── 读取 extensions_config.json 的启用状态
    └── 返回 List[Skill]
```

**热加载纠偏 🆕（v2.1.0 源码）**：早前本文写的"`get_or_new_skill_storage()` 检测 `extensions_config.json` 变化后重建 storage"**不成立**——storage 不缓存 catalog，`load_skills()` 每次调用都重新扫描目录并重读 `ExtensionsConfig.from_file()`（`skills/storage/skill_storage.py:349-375`，注释原话「re-read every call so changes made by another process are picked up immediately」，`:368-369`）；进程单例只按当前 `AppConfig` 身份失效/重建（`skills/storage/__init__.py:36-101`）。外部写入后的失效入口是 admin-only `POST /api/skills/reload`（`app/gateway/routers/skills.py:598-644`，处理函数 `reload_skills` 在 `:607`）→ `refresh_skills_system_prompt_cache_async()`（`agents/lead_agent/prompt.py:347-353`）：它 `_invalidate_enabled_skills_cache()` 拿到刷新句柄后 `await asyncio.to_thread(refresh_handle.wait, _ENABLED_SKILLS_REFRESH_WAIT_TIMEOUT_SECONDS)`（5.0 s，`:44`）**真正等待重建完成**（超时抛 `TimeoutError`，刷新线程报错抛 `RuntimeError`），清掉的是 prompt 层按 `(config, user_id)` 的启用态缓存与 prompt 段落 LRU（`@lru_cache(maxsize=32)`，`:907-908`），**不重建 storage 单例**。单用户版本 `refresh_user_skills_system_prompt_cache_async(user_id)` 供 `skill_manage` 使用（`prompt.py:373-382`，内部只调 `invalidate_user_skill_cache(user_id)`，`prompt.py:360-371`）。

**跨进程失效 🆕（2.2）**：`publish_skills_cache_reset(*, user_id=None)`（`prompt.py:121-160`）把一份 reset 标记写到共享配置目录，同一目录上的其它 Gateway 进程在**下一次缓存查找**时（`_check_shared_skills_cache_reset()`，`prompt.py:80-96`，由 tracker 把文件系统开销限流到**每秒最多一次标记读取**，且不阻塞在并发轮询之后；轮询失败时继续用当前缓存，下次重试）看到新 generation 后走 `_apply_shared_skills_cache_reset(change)`（`prompt.py:97-107`）：`change.user_ids is None` → `_invalidate_enabled_skills_cache()`，否则逐个 `invalidate_user_skill_cache(user_id)`。标记文件名是共享配置旁的点文件 `.<extensions config name>.skills-cache-reset.json`（`prompt.py:64-77` 的模块注释是这套机制的权威说明）。发布方自己通过 `note_own_publication(generation)` 记住 generation，**不会**把刚重建好的缓存再退一遍。返回 `None` 表示解析不到共享配置路径、标记只在进程内生效。失败抛 `SkillCacheResetPublishError`——刻意**不是** `OSError`/`ValueError` 子类，免得被 Gateway 的 404/400 分支误吞（docstring 原话：标记写失败不该借用这两个状态码）。

## Skill 存储契约（`skills/storage/`）

| 实现 | 职责 |
|------|------|
| `SkillStorage`（ABC） | 模板方法基类：校验、路径助手、`load_skills()` 流程、历史序列化（`skill_storage.py:20-327`） |
| `LocalSkillStorage` | 全局 `public/` + `custom/` 的本地文件系统实现（`local_skill_storage.py:29-270`） |
| `UserScopedSkillStorage` | public 读全局；custom/history/状态按用户重定向，并做 LEGACY 回退（`user_scoped_skill_storage.py:50-434`） |

**工厂与缓存**（`storage/__init__.py`）：

- 传 `skills_path` 或 `app_config` → **每次新建、不入缓存**；两者都不传 → 进程单例，按 `AppConfig` 身份重建，冷启动双检锁下构造（`36-101`）。
- per-user 缓存：key = `make_safe_user_id(user_id)`，value 绑定 `AppConfig` 身份；LRU 上限 `_MAX_USER_SCOPED_STORAGES = 64`，`reset_user_skill_storage(user_id=None)` 清单人或全部（`26,104-149,168-197`）。`reset_skill_storage()` 同时清两类缓存（`168-175`）。
- `user_should_see_legacy_skills(user_id)`：非零 LEGACY 才需要挂载 legacy 视图——"sandbox 挂载不得比发现更宽松"是这里集中的契约（`152-165`）。

**分类与容器路径**（`skills/types.py`）：`SkillCategory` 是 4 值 StrEnum——`public`（内置只读）/ `custom`（用户可编辑）/ `integrations`（受管集成只读）/ `legacy`（迁移前的全局 custom，只读，挂 `/mnt/skills/legacy/<name>/`）（`types.py:10-24`）。`Skill.relative_path` 是**相对类别根**的命名空间路径（可含多层，如 `team/helper`），容器内位置由 `get_container_path()` 拼成 `{container_base_path}/{category}/{relative_path}`、`get_container_file_path()` 再补 `/SKILL.md`；`relative_path == "."` 时省略该段（`types.py:59-91`）。这两个方法就是 prompt 里 `Location:` 字段（`describe_skill` 渲染、slash 解析）的唯一来源。

**`load_skills(enabled_only=False)` 模板方法**（`skill_storage.py:277-314`）：遍历 `_iter_skill_files()` → `parse_skill_file` → 以 **name 为键建 dict** → 合并 `extensions_config` 启用态（CUSTOM 无显式条目时默认启用）→ 可选过滤 → 按 name 排序。因为按 name 建 dict，**后遍历到的同名 skill 覆盖先前的**；遍历顺序由 `_iter_skill_files()` 决定：

- `LocalSkillStorage`：按 `SkillCategory` 枚举序 `public → custom → integrations → legacy`（`local_skill_storage.py:75-92`）。
- `UserScopedSkillStorage`：`public → integrations → custom →`（仅当用户 custom 目录为空时）全局 `custom/` 作为 `LEGACY`（`user_scoped_skill_storage.py:273-319`）。所以同名时 custom/integration 覆盖 public（锚 `backend/tests/test_skills_loader.py:144`）。

**LEGACY 回退是 shadow 语义**：用户一旦有了自己的 custom skill，全局 `skills/custom/` 就不再以 LEGACY 出现（`user_scoped_skill_storage.py:65-69,306-319`，锚 `tests/test_user_scoped_skill_storage.py:194`）；LEGACY 只读、不可编辑/删除，挂载在 `/mnt/skills/legacy/<name>/`。

**每用户启用态**：`{user_base}/users/{id}/skills/_skill_states.json`（缺文件/损坏 → `{}`，默认 `True`；写入是同目录临时文件 + replace）。CUSTOM/LEGACY 最终启用 = per-user 状态 **AND** 全局 `extensions_config` 默认（防止升级前的全局禁用被"无 per-user 条目"悄悄重新启用）；PUBLIC 仍只由 `extensions_config.json` 决定（`user_scoped_skill_storage.py:96-161,213-221`）。

**写入门共用校验**（`SkillStorage` 静态方法，installer / Gateway 路由 / `skill_manage` 都走）：

- `validate_skill_name`：hyphen-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）且 ≤64 字符（`skill_storage.py:17,36-44`）。
- `validate_relative_path`：解析（跟随符号链接）后必须仍在 skill 目录内（`46-62`）。
- `validate_skill_markdown_content`：在临时目录里跑 `_validate_skill_frontmatter`，并要求 frontmatter `name` == 请求的目录名（`64-79`）。
- `ensure_safe_support_path`：support 文件只允许落在 `references/ | templates/ | scripts/ | assets/` 顶层目录，禁止绝对路径与 `..`（`98-118`）。
- 外部包目录符号链接：只允许 custom 类别根下**第一层目录**是符号链接这一种兼容形态，`SKILL.md` 本身是链接一律拒绝（`81-96,150-160`）；`UserScopedSkillStorage` 额外接受 user-custom 与 global-custom 两个根（`user_scoped_skill_storage.py:404-434`）。

**写入/删除与 projection 同一临界区**：`LocalSkillStorage._skill_projection_mutation` 在 user-scoped 时走 `projection.skill_projection_mutation(self, "user")`；全局存储只取 `<root>/custom` 的投影锁（`local_skill_storage.py:237-249`）。写盘是"同目录临时文件 + `Path.replace`"，随后 `permissions.make_skill_written_path_sandbox_readable` 把 skill 根到目标逐级改成沙箱只读（`99-112`）。

**历史**：`custom/.history/<name>.jsonl`（user-scoped 在用户目录下），append-only，每条自动补 UTC `ts`（`local_skill_storage.py:251-270`；路径契约 `skill_storage.py:259-271`）。删除时历史写失败只在 `EACCES/EPERM/EROFS` 下降级为告警并继续删目录（`local_skill_storage.py:216-235`）。`read_history()` **不做逐行容错**，单行非法 JSON 会抛（`260-269`）。

**可编辑性**：只有 CUSTOM 可编辑；PUBLIC / LEGACY / INTEGRATION 各有专属错误文案（`skill_storage.py:316-327`；`user_scoped_skill_storage.py:250-271`）。

## 共享文件分类与权限助手

- **`package_files.py` 是"哪些是代码 / 哪些字节是可执行"的唯一来源**——installer 的抽取 guard、export 的阻断规则、SkillScan 都 import 它，不得各自再写一份（模块 docstring，`package_files.py:1-5`）。契约（2.2 现状）：`CODE_SUFFIXES` **21** 个后缀（`.bash .bat .cjs .cmd .hta .js .jse .mjs .php .pl .ps1 .psm1 .py .rb .sct .sh .ts .vbe .vbs .wsf .zsh`）；`is_scripts_member` 单独判"顶层目录是 `scripts/`"；`is_code_path` = `is_scripts_member` **或**后缀命中；`is_code_file` 再加"无后缀且 `head` 以 `#!` 开头"；`is_executable_binary_prefix` 用完整 magic（ELF、`MZ`、8 种 Mach-O，不用共享短前缀以免误判数据文件），并**容忍有限前导填充**——`_EXEC_SNIFF_FILLER`（空白 + NUL）最多跳 63 字节，填满 64 字节即判无 magic；UTF-8 BOM 只能整体跳过一次（它末字节 `\xbf` 也是 Mach-O fat64 LE magic 的首字节，按字节剥会误判）（`package_files.py:12-20,43-62,66-98`）。锚点：`backend/tests/test_skillscan_native.py:382`（与安装器抽取 guard 一致）、`393`（截断 magic 不算可执行）。
- **`package_paths.py` 是 eval fixture 判定的唯一来源**：路径中出现 `evals` 且其后仍 ≥2 段时，`evals` 的下一段必须是 `fixtures`；`is_eval_fixture_skill_md` 在此基础上加"末段是 `SKILL.md`"（`package_paths.py:12-24`）。review 与 SkillScan 的豁免/收紧都以它为准。
- **`permissions.py`**：目录 → `0o555`、文件 → `0o444`（去掉 group/other 写位再或上只读位），符号链接直接跳过；`make_skill_tree_sandbox_readable` 递归整棵树（含隐藏路径），`make_skill_written_path_sandbox_readable(skill_root, target)` 只处理"根 → 目标"这一条路径且要求 target 已在 skill_root 内，否则抛 `ValueError`（`permissions.py:7-34`，锚 `backend/tests/test_skill_permissions.py:19,49`）。

## Projection 物化契约（`skills/projection.py`）

> 共享/线程投影的**行为变化**（enabled-only、按策略隔离）见下文「`/mnt/skills` 收归 managed enabled-only projection」一节；这里列的是它之下调用方必须知道的不变量。

- **常量**：manifest `version=1`、每个 scope 最多重建 `_MAX_REBUILD_ATTEMPTS=2` 次、线程策略版本 `_THREAD_PROJECTION_POLICY_VERSION=2`（2.1 是 1；+1 使所有既有线程视图在升级后必然判 stale 并重建一次）（`projection.py:39-41`）。清单落在 `<scope_root>/.projection-manifest.json`，含 `source_signature` + `view_signature`，用 mkstemp + `replace` 原子写；失败清理由 `deerflow.utils.atomic_write.cleanup_failed_atomic_write(temporary, fd)` 统一接管（关闭 fd + unlink，`BaseException` 也走），不再裸 `unlink(missing_ok=True)`（`projection.py:430-449`）。
- **路径作用域**：全局 public 视图一份；user custom/legacy/integrations 每人一份；线程视图在 `users/{uid}/threads/{tid}/skills_view/{public,custom,legacy,integrations}`。线程投影要求 user-scoped storage，否则 `ValueError`（`projection.py:54-90`）。`thread_skill_projection_exists()` 只看该线程 scope 根目录是否存在（`:91-102`）。
- **锁 🆕（2.2 重写）**：每个 scope 一把进程内 `RLock` + `<parent>/.<name>.projection.lock` 的 POSIX `flock`（Windows 走 msvcrt）。`_projection_lock(root, *, timeout=None, check=None)` 现在统一服务变更与读锁两条路径：进程内锁以 0.05s 片段轮询并允许传入 deadline；文件锁用非阻塞 `LOCK_EX | LOCK_NB`（Windows `LK_NBLCK`）再经 `deerflow.utils.file_lock.retry_until_locked` 在**只在争用时**重试，死锁/超时消息仍是 `Skill projection lock timeout`。关键新增是**同线程重入共享 fd**：`_held_projection_locks`（`threading.local` 集合）记录已持有的 `lock_path`，嵌套读锁直接复用外层 fd 而不是重开一个再 flock——否则 RLock 可重入、fd 却会自死锁（`projection.py:104-155`）。稳态新鲜度检查仍在锁外做；只有 stale/异常才进锁并**二次检查**。
- **新鲜度 = 清单双读一致 + 源签名相等 + 视图签名相等**（`_thread_projection_is_fresh` / `_public_projection_is_fresh`，`projection.py:527-543`）。源签名覆盖源目录树 + `extensions_config`（user scope 另加 per-user states）`_source_signature`（`:383-408`）；public/user 的视图签名仍只哈希**视图元数据**（`_view_signature`，`:495-507`）。
- **线程视图签名改为哈希真实字节 🆕（2.2）**：`_thread_view_signature(paths)`（`projection.py:452-492`）逐文件打开（`O_NOFOLLOW|O_NONBLOCK`）用 `hashlib.file_digest` 算 sha256，值为 `["file", sha256, mode & 0o111]`；符号链接只记 `["link", readlink]` 从不打开，特殊文件只记 `S_IFMT`，目录记 `["dir"]`。动机写在 docstring 里：**inode/size/mtime 这类元数据在 NFS/CSI 上会滞后沉降**，只比元数据会导致"刚重建就被判 stale"或"漏掉沙盒内真实改写"；读字节换来"下一次 acquire 一定修好沙盒越权编辑，而单纯元数据沉降不会触发整视图重拷"。
- **源签名只哈希目录元数据**（inode/mode/size/mtime_ns），刻意不读文件内容：换来每次 sandbox acquire 都能 O(files) 检查；代价是"inode+size+mtime 都不变的外部改写"不可见，直到下一次显式重建。代码路径内的写入不受影响——变更路径持锁重建，原子替换一定换 inode（`projection.py:340-381`）。custom/legacy 类别根下第一层包目录符号链接会被跟随并将其 target 路径计入签名。
- **线程策略重建先撤销再挂新**：清空四个类别 → 逐个填充，fail-closed。并发读者可能短暂看到更少的 skill，但绝不会看到被新策略撤销的 skill；类别根 inode 保持稳定以服务 live bind mount（`projection.py:607-697`，锚 `tests/test_skill_projection.py:441`）。
- **零拷贝快路径**：`ensure_thread_skill_projection(storage, thread_id, allowed_skills)` 在 `allowed_skills is None` 且线程 scope 目录不存在时返回 `None`（继续用共享视图）；一旦线程有了 scope，后续无限制 run 也会把同一线程根重建为"全量启用"视图，避免切换 agent 后线程被意外限制（`projection.py:699-752`）。
- **谁负责修**：`ensure_skill_projections` 修 stale 的 public/user scope；`ensure_thread_skill_projection` 修线程 scope；启动期 `ensure_public_skill_projection` **只**处理全局 public（否则 readiness 会随租户数增长），失败时清空 public 视图、记 warning 并返回 `False`，等 sandbox acquire 自愈（`projection.py:796-800,918-944`）。
- **嵌套顺序由 mutation guard 固定 🆕（2.2）**：`ensure_skill_projections` / `ensure_thread_skill_projection` / `rebuild_skill_projections` 三个公开入口都是薄包装，先 `managed_global_read(storage)`（global 投影锁，只有 enrolled owner 才真取）再 `managed_read(storage)`（user 投影读锁 + readiness 屏障）才进原实现——注释写明「Global -> owner -> thread. No fresh-view fast path bypasses recovery」，即 fast path 也不能绕过未决发布的恢复（`projection.py:703-712,757-766,797-804`）。变更侧 `skill_projection_mutation(...)` 新增 `mutation_names: tuple[str, ...]`：外层再加一把**按 skill 名的写栅栏** `managed_name_writes(storage, names)`（锁目录 `<public parent>/.skill-mutation-names/{sha256(name)}`），并在真正 yield 前包 `managed_writer(storage, names)`（`projection.py:846-916`）。
- **读锁 `skill_projection_read_lock(storage, *, timeout=5.0, check=None)`**：非变更、有界；超时抛 `TimeoutError`；`check` 在每次等待前被调用（导出用它做取消/预算检查）。2.2 起它只是 `_projection_lock(root, timeout=timeout, check=check)` 的一层包装（不再复制一遍加锁逻辑），取的仍是 user projection 那把锁，非 user storage 退化为 `<skills_root>/custom` scope（`projection.py:945-950`）。导出在它下面捕获与复核，且导出方**不重建**投影（`export.py:378-383`，锚 `tests/test_skill_export.py:285`）。
- **失败即清空**：任何 scope 重建异常都会先清空该 scope 的类别根 + 清单再抛（选择"看到少"而不是"看到旧/越权"）（`projection.py:497-514,517-546,563-609,786-788`，锚 `tests/test_skill_projection.py:534,551`）。
- **写隔离靠拷贝**：投影一律 `shutil.copy2`，刻意不用 hardlink——LocalSandbox 的 bash 写会透传 inode，`PathMapping.read_only` 只约束 `write_file`/`update_file`，不约束 `execute_command`。
- **策略作用域符号链接 fail-closed**：绝对链接、解析到包外的相对链接、断链，都在任何 live 视图被改动之前抛错。
- 受管的 integrations 包是**全局安装**的，但其投影类别按用户分离（启用态是 per-user 的）。

## ⚠️ Breaking Change：SKILL.md 即 Package Boundary

**2.1**：含有 `SKILL.md` 的目录现在是 runtime package boundary。该目录内的嵌套 `SKILL.md` 文件被视为 support data，不再注册为独立 skill。不寻常的自定义布局需将独立可加载 skill 移到不含自身 `SKILL.md` 的 namespace 目录下。

## ⚠️ Breaking Change：`/mnt/skills` 收归 managed enabled-only projection 🆕（#4178）

**2.1**：`/mnt/skills` 不再是 skills 目录的直接透传挂载，而是 `skills/projection.py` 物化的 **enabled-only 只读投影**——只有启用的 skill 才出现在 sandbox 视图里（public / custom / legacy / integrations 四个 scope，各 scope 独立 fail-closed：单个 scope 重建失败只清空该视图并自愈，不中止 Gateway 启动）。影响：

- **operator 配置的 mounts 指向 `/mnt/skills`（或其子路径）会被跳过并告警**（E2B：`Skipping e2b mount that conflicts with managed skills projection`）——托管投影与操作者挂载不再叠加
- 每个用户/线程的投影按全局 enable 状态重建；用户 projection **重读全局 enable 状态，跨 worker 生效**（启用/禁用即时反映到下一次 sandbox acquire）
- 关闭 skill 后 sandbox 文件系统视图同步消失，而不是"文件还在、只是不激活"

## 本地 skill 归档安装 🆕（#5039）

`POST /api/skills/install` 支持上传 `.skill` ZIP 归档安装到 `custom/`。Gateway 侧用有界 multipart 解析器流式落盘（`_BoundedSkillArchiveMultiPartParser` + 双重字节上限：单文件 100 MiB，含 multipart 开销的请求级上限），超限在 Starlette 写盘前中止以便及时关闭 spool 文件；nginx/helm 相应放宽了 body size（`test_nginx_langgraph_body_size.py` + chart 脚本 `scripts/check_chart_skill_upload_size.sh` pin）。归档内容仍过 SkillScan 静态扫描。**完整安装链路（`installer.py` 的预检/抽取/内容扫描/原子落地/失败清理与错误→HTTP 映射）见** [`skill-package-intake.md`](skill-package-intake.md#2-skillsinstallerpy--skill-安装链路)。

## 自定义 skill 包导出 🆕（#5332）

`skills/export.py`（harness）+ `app/gateway/skill_export.py` + `routers/skills.py`：把自定义 skill 打包成可分发的 ZIP，**全程只读快照**——导出不会激活或执行 skill。硬边界：4096 entries / 单文件 64 MiB / 总量与 ZIP 各 100 MiB / 路径 1024 字节 / 深度 32 / 60s deadline，持 projection 读锁；拒绝敏感文件（`.env`、`id_rsa`、`credentials.json` 等）、Windows 保留名、非 `[a-z0-9-]` 名称。**revision-bound preview**：请求携带 skill 内容的 SHA-256 revision，预览与下载都绑定该 revision——skill 在导出过程中被修改则整个导出失败，不会产出半新半旧的包。

## SKILL.md 空描述在写入门被拒 🆕（#4867）

`_validate_skill_frontmatter` 之前只在 description **truthy** 时应用规则，空白描述能过写入门但被 loader 拒绝——PUT 编辑端点先写盘再 404（原本可用的 skill 直接消失且无回滚），`.skill` 安装路径与 `skill_manage` 工具同样报告一个永远加载不出来的 skill。现在空白/纯空白 description 在写入门被拒（400 "Description cannot be empty"），rollback 恢复含空描述历史条目同样被拒且**磁盘保持原样**。

## `allowed-tools` portable 模式安全 token 化 🆕（#4984）

Portable Agent Skills 的标量语法是空白分隔、允许带括号命令模式（如 `Bash(tvly *)`）。解析器（`skills/parser.py::parse_allowed_tools`）现在把含空格的括号模式**保持为单个字面条目**，不再 `raw.split()` 碎片化；YAML 列表形式仍逐字保留大小写敏感的 MCP/运行时工具名。DeerFlow 当前策略只匹配**精确工具名**：`Bash(...)` 条目保持字面且不生效（不会宽化为 unrestricted shell），直到有显式的命令模式授权模型。

## SkillScan 静态分析 🆕

`packages/harness/deerflow/skills/skillscan/` — 加载时对 skill package 做确定性静态扫描：

- **单入口编排**：`scan_skill_dir` 顺序遍历文件、按路径类型分派给各 analyzer，`scan_archive_preflight` 顺序遍历 ZIP 成员——**模块自身无并发**（文件叫 orchestrator 但没有线程/协程/线程池 import）；并发只发生在调用方把整个同步扫描 offload 到 worker 线程这一层（`skillscan/orchestrator.py:1-36,224-258`）
- **Network sink 检测**：识别 `requests`/`httpx` HTTP methods、`urllib` 等外泄路径
- **Environment access 检测**：识别 `os.environ` 读取（含 `from os import environ` 模式）
- **Subprocess shell 检测**：`os.system`/`os.popen`/`subprocess` 调用 `shell=True` 视为外泄路径；`shell=` 非字面量（变量/表达式/`**kwargs`）**fail-closed** 视为 shell=True（`_call_shell_may_be_true`，同步 #4 加固）
- **分级阻断**：`CRITICAL` 阻断安装，非 CRITICAL 放行但传给 LLM 扫描器
- **纯同步**：`scan_archive_preflight()` / `scan_skill_dir()` 可 offload 出 event loop
- `skill_scan.enabled` kill switch

### SkillScan 契约补深（v2.1.0 源码）

> 全量 **39 条规则表**、全部上限常量与异常层级见 [`skill-package-intake.md`](skill-package-intake.md#3-skillscan-补深规则表--上限--异常类型)。

- **规则表即契约**：`RULES: dict[rule_id, RuleSpec]`，Phase 1 共 **39** 条，severity 分布 CRITICAL 19 / HIGH 14 / MEDIUM 5 / LOW 1（`skillscan/orchestrator.py:46-93`）。`rule_id` 前缀编码类别与所属 analyzer（`package-` / `secret-` / `declaration-` / `python-` / `shell-` / `network-` / `resource-`），**没有**独立的 category/analyzer 字段（`skillscan/models.py:1-8`）。规则 spec 与匹配它的 analyzer 写在同一文件内，不引入 Semgrep/OpenGrep/YAML 规则引擎。
- **阻断策略只有一个常量**：`_BLOCK_SEVERITY = "CRITICAL"`。`enforce_static_scan(skill_dir, *, skill_name=None, app_config=None)` 命中 CRITICAL 抛 `StaticScanBlockedError(findings, skill_name=...)`；其余 finding 只记 warning 并**原样返回**给调用方（交给 LLM 审核阶段）（`orchestrator.py:41,155-177`，锚 `tests/test_skillscan_native.py:201`）。
- **kill switch 默认开**：`skill_scan_enabled(app_config=None)` 在配置缺失/无 `skill_scan` 段时返回 `True`；关闭时 `enforce_static_scan` 直接返回 `[]`（`131-142,161-162`，锚 `219`）。`LocalSkillStorage` 在 `host_path` 构造分支里允许 `app_config=None`，kill switch 在扫描时懒解析，所以这里不是"忽略配置"（`local_skill_storage.py:52-58`）。
- **两个入口都是纯同步函数**（模块 docstring 明确要求 async 调用方自行 offload）：`scan_archive_preflight(archive_path)` 只读 ZIP 成员元数据 + 限量 peek，不解压安装，坏 ZIP → `StaticScannerError`；`scan_skill_dir(skill_dir)`，非目录 → `StaticScannerError`（`orchestrator.py:1-8,180-227`）。安装路径在 worker 线程里调 `scan_archive_preflight_or_raise`（`local_skill_storage.py:187-189`）。
- **上限**：`MAX_TOTAL_ARCHIVE_BYTES = 512 MiB`、`MAX_FILE_BYTES = 64 MiB`、`_MAX_ARCHIVE_MEMBERS = 4096`（超成员数在逐成员读取**之前** early-return 一条 CRITICAL，避免小体积大成员数的 DoS）、`_NESTED_ZIP_PEEK_MEMBER_LIMIT = 256`、`_TEXT_PROBE_BYTES = 4096`、Python client 句柄分析工作预算 `_PYTHON_CLIENT_ANALYSIS_BUDGET = 100_000`（`38-44,187-191,516,798`）。
- **嵌套归档分级**：只对 `PK\x03\x04` 的 ZIP 做 peek（≤256 成员）；若内部含可执行 magic，同一条 `package-nested-archive` 升为 CRITICAL，否则保持 HIGH（`500-527`）。
- **finding 去重键 = `(rule_id, file, line)`**，保留首次出现（`549-558`）；`secret-*` 规则的 evidence 一律替换成 `"[redacted]"`——连前缀都不保留，因为 findings 会流入 Gateway 响应与 LLM 上下文（`472-475,537-541`，锚 `tests/test_skillscan_native.py:460`）。
- **文件级判定**：NUL/非 UTF-8 的**代码文件**（走 `package_files` 判定）记 `package-undecodable-script`（HIGH）后用有损解码继续跑文本规则，让一个坏字节不能藏文件或降级 CRITICAL 匹配；若它同时带可执行 magic，则跳过文本规则（避免把字符串表读成 secret/URL）（`224-258`，锚 `517,532,543`）。
- **Python 侧只做 AST 静态判定**：`eval`/`exec`/`compile(mode="exec")` → `python-dynamic-exec`；`os.system`/`os.popen`/`subprocess.*` 且 `shell=` 无法证明为字面 `False`（含变量、表达式、`**kwargs` 解包）→ `python-shell-exec`（fail-closed）；其余 `subprocess.*` → `python-subprocess`（HIGH，不阻断）；敏感路径读取 × 网络 sink → `python-sensitive-exfil`；`os.environ` × sink → `python-env-dump-exfil`；`socket` + `dup2` + `subprocess` 三件套 → `python-reverse-shell`（`357-434,710-730`；shell=True fail-closed 锚 `test_skillscan_native.py:255,279,298,324`）。
- **实例 client 是独立的有界信号**：`_PYTHON_CLIENT_SPECS` 只认 `http.client.HTTP(S)Connection`、`requests.Session`、`urllib3.PoolManager`、`aiohttp.ClientSession` 的"构造 → 简单名/别名 → 同名方法调用"链；预算耗尽或递归超限只放弃该信号并保留已收集的确定性 finding（`759-798`，锚 `test_skillscan_native.py:110,140,181`）。
- **Shell 强弱分级**：`/dev/tcp/`、`nc -e` → CRITICAL `shell-reverse-shell`（直接阻断）；`bash -i`、`mkfifo` → HIGH `shell-reverse-shell-heuristic`（只告警后交 LLM）；另有 `shell-sensitive-exfil`(CRITICAL)、`shell-curl-pipe-shell`/`shell-destructive-command`(HIGH)、`shell-env-dump`(MEDIUM)（`437-453`，锚 `test_skillscan_native.py:474,489`）。
- **evidence 里的 `file` 是包内相对路径**，绝对路径/穿越/ADS 冒号在归档预检阶段就被独立 rule 拦下（`package-absolute-path` / `package-path-traversal` / `package-ads-stream-name`）（`261-274,565-587`）。

## Custom Skill 导出（revision 绑定预览）🆕

`deerflow/skills/export.py` + `app/gateway/skill_export.py`（+ `backend/scripts/benchmark/skill_export.py` 基准）——把用户 custom skill 打包为 `.skill` zip 下载，快照绝不激活或执行 skill：

- **两步 API**：`GET /api/skills/custom/{name}/export-manifest`（预览：文件清单、requirements、warnings/blockers、revision）→ `GET /api/skills/custom/{name}/export?expected_revision=...`（下载；revision 是文件树内容哈希，与预览不一致返回 409 `skill_changed`，需刷新后重试）
- **只捕获 `storage.get_custom_skill_dir(name)`**，无 public/legacy 回退；捕获与复核都在 `skill_projection_read_lock` 下（与存储变更同一把锁），导出不重建 projection
- **有界且可取消**：≤4096 条目、单文件 64 MiB、总量/zip 100 MiB、路径 1024 字节、深度 32、60s deadline；拒绝符号链接/特殊文件而非跟踪
- **敏感文件提示**：`.env`、`.npmrc`、`.pypirc`、`.netrc`、`.git`、`.svn`、`.hg`、`credentials.json`、`id_rsa`、`id_ed25519`（含 `.env.*`）记 `skill_export_sensitive_filename` **warning**，不阻断；详见下方纠偏 1。导出是原始文件快照，不是 secret 审计
- **Gateway 侧**：每进程 2 个导出槽位（跨用户共享，占满返回 429 `skill_export_busy`），传输空闲超时 120s，客户端断连与服务器取消分开处理
- 前端配套 `skill-export-dialog.tsx`（见 frontend digest）
- 测试：`tests/test_skill_export.py`、`tests/blocking_io/test_skill_export.py`（fd 目录遍历不可用的平台上 capture 套件跳过，#5372）

### 导出契约补深（`skills/export.py`）与两处纠偏

**纠偏 1：敏感文件名是 warning，不是 blocker。** `_SENSITIVE = {".env", ".npmrc", ".pypirc", ".netrc", ".git", ".svn", ".hg", "credentials.json", "id_rsa", "id_ed25519"}`（以及 `.env.*` 前缀）只产生 `skill_export_sensitive_filename` **warning**，导出照常可用（`export.py:43,155-157`）。blocker 来自结构性原因：符号链接/硬链接（`nlink != 1`）、非普通文件、可执行 magic、非法/冲突/不可移植路径、嵌套 `SKILL.md`、无效 frontmatter。

**纠偏 2：limits 是"报错"而不是"截断"。** 条目数/深度/路径字节/单文件/总量/zip 超限一律抛 413 `skill_export_limit_exceeded`，不产出被裁剪的包（`export.py:89-90,133-150,182-183,209-210,422-423,475-476`）。

错误码 ↔ HTTP status 是固定契约，诊断里不出现主机路径或源文本（`SkillExportError(status, code, message, path=None)`）：

| status | code | 触发点 |
|--------|------|--------|
| 413 | `skill_export_limit_exceeded` | 任一资源上限 |
| 409 | `skill_changed` | 遍历/复核期间 identity、内容摘要或清单漂移；`expected_revision` 不匹配 |
| 503 | `skill_export_timeout` / `skill_export_cancelled` | 60s deadline / cancel_event；以及 5s 内拿不到 projection 读锁 |
| 422 | `skill_export_unsupported` | 非法修订号、非法 skill 名、平台缺 `O_NOFOLLOW`/`dir_fd`/`scandir(fd)` 支持、存在 blocker |
| 404 | `skill_not_found` | custom skill 目录不存在 |
| 500 | `skill_export_failed` | 其它 OSError / 构建失败 |

来源：`export.py:46-55,82-102,370-412,446-449`。

- **预算对象 `_Budget`**：`DEADLINE_SECONDS = 60.0` + 可选 `cancel_event`，每个循环点 `check()`；锁等待也把 `check` 传进 `skill_projection_read_lock`，`LOCK_TIMEOUT_SECONDS = 5.0`（`77-88,374`）。
- **平台能力是硬前置**：`os.O_NOFOLLOW` 缺失、`os.open` 不支持 `dir_fd`、`os.scandir` 不支持 fd → 直接 422，不做不安全降级（`375-376`）。
- **两遍捕获**：第一遍写快照并算 `(path, identity, digest)`；第二遍只复核这份三元组与 blockers 是否逐一相等，不等 → 409。每个目录 fd 在递归前后 identity 也必须一致，根目录与其父目录同样复核（`388-395`）。锚 `tests/test_skill_export.py:116,371`。
- **修订号算法**：`_revision(name, entries)` 对 `"deerflow-skill-export-v1"`、skill 名、每个条目的 `(path, type, size, content_digest, executable)` 逐字段做 8 字节大端长度前缀后 SHA-256；**mtime 不参与**（`231-243`，锚 `430`）。`blockers` 非空时 `revision=None`，预览不给可下载修订号（`331`）。
- **ZIP 确定性**：固定 `date_time=(1980,1,1)`、`create_system=3`、条目名 `<skill>/<rel>`（目录带尾 `/`）、权限 `0o755`（目录/executable 文件）或 `0o644`，DEFLATE 压缩；写入经 `_LimitedWriter` 卡 100 MiB zip 上限（`452-476`）。导出是原始快照，**不是** secret 审计。
- **frontmatter 前置守卫 `_guard_frontmatter`**：用 `yaml.parse` 只走事件流，不构造别名、不展开 merge key；YAML alias → blocker `skill_export_yaml_alias`；事件数 > `MAX_YAML_EVENTS=16384` 或嵌套 > `MAX_YAML_DEPTH=32` → blocker `skill_export_yaml_complexity`；frontmatter 本身另有 `MAX_FRONTMATTER_BYTES = 1 MiB` 上限（`34-36,254-275,287-295`）。
- **`requirements` 只抽三个声明**：`compatibility`、`allowed-tools`（经 `parse_allowed_tools`）、`required-secrets`（名称必须匹配 `[A-Za-z_][A-Za-z0-9_]*`，重名去重，非法条目降级为 `skill_export_invalid_declaration` warning）；只要声明了 tools/secrets 就追加 `skill_export_platform_declarations` warning（"目标环境需自行配置"）（`280-324`，锚 `421`）。

## 本地 .skill 归档上传安装 🆕

除线程内 `POST /api/skills/install` 外，新增 `POST /api/skills/install/upload`：admin-only multipart，直接上传本地 `.skill` 归档安装到当前用户 custom 目录。授权先于解析；上限 100 MiB 文件 + 1 MiB multipart 框架开销（#5039）。nginx/Helm Ingress 的 `proxy-body-size: 101m` 与 `proxy-request-buffering: off` 只作用于该上传路由，`scripts/check_chart_skill_upload_size.sh` 在 CI 中断言渲染后的 Helm 配置不被回退。

## Skill 开关不再持久化展开后的密钥 🆕

**修复（#5357）**：此前 Gateway skill toggle 与 `DeerFlowClient.update_skill` 经 `ExtensionsConfig.from_file()` 读 `extensions_config.json`，会把 `"$GITHUB_TOKEN"` 之类的引用展开成明文环境值（未设置则展开为空串并永久丢失）再整体写回。现在所有写入方走 raw 读改写：`read_raw_extensions_config()`（读磁盘原始 JSON）→ `set_raw_skill_enabled()`（只改目标条目）→ `validate_raw_extensions_config()`（按运行时加载方式校验候选）→ 原子写；`update_mcp_config` 的非 `mcpServers` 键同样修复。

## Skill Review 质量门禁 🆕

`packages/harness/deerflow/skills/review/` + `skills/public/skill-reviewer/`：
- **CLI**：`python -m deerflow.skills.review.cli --fail-on error --fail-on-incomplete` 用于 CI
- **内置 tool**：`review_skill_package` — 模型可见的是 compact JSON（tag 中性化），完整 payload 在 `ToolMessage.artifact`
- **CI 集成**：`.github/workflows/skill-review-ci.yml`
- **JSON Schema 契约**：`contracts/skill_review/` 除 waiver manifest 外还有三个 schema，对应审查管线三层（`backend/tests/test_skill_review_core.py:50-52` 用它们校验实际产物）：
  - `package_snapshot.v1.schema.json` — **快照**：`LocalDirectoryReader` 有界只读抓取 skill 包的结果（`schema_version`/`subject`/`limits`/`files`/`truncated`/`reader_errors`），不执行 skill
  - `review_facts.v1.schema.json` — **事实**：`analyze_skill_package(snapshot)` 的确定性分析输出（`profile`/`completeness`/`summary`/`findings`/`resources`/`evals`/`analyzer_errors`）
  - `review_report.v1.schema.json` — **报告**：`build_static_report(facts)` 的评分结果（`readiness`/`assurance`/`dimensions`/`issues`/`evidence`/`recommended_actions`），即 `review_skill_package` 放进 `ToolMessage.artifact` 的完整 payload（模型可见的只是 compact JSON）
- **Waiver manifest 🆕（#5143）**：`.github/skill-review-waivers.v1.json` + schema `contracts/skill_review/waiver_manifest.v1.schema.json`，由 `scripts/skill_review_waivers.py` 解析、`scripts/review_changed_public_skills.py` 在 CI 中执行。每条 waiver 精确匹配一个 finding（package 需 `skills/public/` 前缀 + `rule_id`/`path`/`line`/`evidence`），携带被审文件的 `file_sha256`（`sha256:...`）与 `expires_on` 日期，上限 256 条；`preapproved_file_sha256s`（≤8 个）可预授权未来文件哈希，仅当 manifest 变更合入可信 base 后生效——所以依赖 waiver 需两次合并：先合 manifest，再合 skill 改动，随后把消费过的哈希提升为 `file_sha256`。waiver 只能豁免 error 级 finding（blocker 永不可豁免），且在 CI 输出中保持可见。

## Per-User Skill 隔离 🆕

Custom skill 按用户隔离存储，`SkillStorage` 按 `(app_config, user_id)` 缓存。Sandbox 挂载用户级 skill 目录。

## `allowed-tools`：从「工具过滤器」降级为「兼容元数据」 ⚠️ 2.2 重大变更

> **sync #8 重写**（对应 upstream #6935 `0d73798be`，2.2.0 引入）。这一节在 2.1 时代描述的是
> 已删除的 `skills/tool_policy.py` 的工具过滤机制——**该文件和它配套的 `SkillToolPolicyMiddleware`（529 行）
> 在 2.2 已被整体删除**。下面是 2.1 的历史，以及 2.2 的现行语义。

### 2.1 的行为（历史，仅供理解迁移）

`allowed-tools` 只对 slash-activated 或实际 loaded 的 lead-agent skill 生效，Passive enabled skill
不限制全局 toolset。实现落在两处：

- **已删除**：`skills/tool_policy.py`（65 行）——`ALWAYS_AVAILABLE_BUILTIN_TOOL_NAMES`（describe_skill /
  read_file / review_skill_package / tool_search）、`allowed_tool_names_for_skills()`、
  `filter_tools_by_skill_allowed_tools()`；语义要点是「没有 skill 声明 → 返回 `None` 全放行；
  一旦有 skill 声明，未声明的 skill 贡献 0 个工具」。
- **已删除**：`agents/middlewares/skill_tool_policy_middleware.py`（529 行）——把上述并集同时应用到
  **模型可见性、tool_search 结果、执行**三层，并带 slash 授权与持久化 `skill_context` 的重新授权。

**分词加固（#4984，2.1 遗留、2.2 不再用于过滤）**：可移植标量形式按状态机分词——引号内、转义字符、
括号模式内的空格不切分；未闭合引号/未闭合括号/多余右括号直接报错（fail-closed）。

### 2.2 的现行语义（#6935 之后）

`allowed-tools` **只是兼容元数据**：为老 skill 保留解析与展示，**不再过滤、授予或拒绝任何工具**。

- 删除了 `skills/tool_policy.py` 与 `agents/middlewares/skill_tool_policy_middleware.py`；
  `build_middlewares()` 里对 `SkillToolPolicyMiddleware` 的注册一并移除（`agents/lead_agent/agent.py`）。
- `SkillActivationMiddleware` 的职责收窄为：识别 `/skill-name task` 语法、只解析「已启用且运行时允许」的
  skill、注入 `SKILL.md` 正文、记录 `middleware:skill_activation` 审计事件——**激活本身不再改变工具集**。
- **权限上限的唯一所有者变成「agent 组装 + 执行授权」**：Layer 1 能力过滤
  （`authorization.enabled` 的 `AuthorizationProvider`）与 Layer 2 执行前检查
  （`GuardrailAuthorizationAdapter`）决定模型能看到、能调用什么；`middleware/AGENTS.md` #18 原文：
  「Agent assembly/execution authorization owns the permission ceiling」。
- 对文档/测试的影响：任何「skill 声明 allowed-tools 就看不到 bash」式断言**在 2.2 已不成立**；
  要限制工具请走 `disallowed_tools`、`authorization` 或 custom agent 的 `skills`/工具配置。
- 迁移提示：老 skill 的 `allowed-tools` 字段可以留着（不报错、仍可展示），但**不要再指望它做安全边界**。

## `capabilities/` 能力目录 🆕（2.2 新增包）

`backend/packages/harness/deerflow/capabilities/` 是 2.2 新增的**声明式能力发现**层，模块 docstring 一句话定性：`"""Declarative capability discovery; execution stays with the owning runtime."""`（`capabilities/__init__.py:1`）。它只回答"有哪些能力、装在哪、需不需要凭据"，**不执行任何东西**——MCP server 仍由 MCP 运行时跑，skill 仍是 skill 包，CLI 适配器仍交给已安装的扩展。

### 组成（4 个模块 + 1 份 JSON）

| 文件 | 职责 |
|------|------|
| `capabilities/builtin.json` | 内置能力的 **manifest 清单**，纯数据，不含可执行内容 |
| `capabilities/catalog.py`（51 行） | pydantic `PluginManifest` 模型 + `load_catalog(path=None)` |
| `capabilities/runtime.py`（38 行） | 运行时身份：`installation_id()` / `ambiguous_installation_ids()` / `filter_mcp_plugins()` |
| `capabilities/business.py`（178 行） | 内置业务 MCP provider（钉钉 / 企微 / HubSpot）的 stdio 连接与工具实现 |

### manifest 契约（`capabilities/catalog.py`）

`PluginManifest` 是 `extra="forbid"` 的 pydantic 模型（拼错字段直接炸，不会静默忽略）。关键约束：

- `schema_version: Literal[1] = 1`；`id` 正则 `^[a-z0-9][a-z0-9.-]*$` 且 ≤128 字符；`version` 1–80 字符。
- `category ∈ {office, knowledge, research, business, development, custom}`；`kind ∈ {mcp, cli, native}`。
- `adapter` 正则 `^[a-z][a-z0-9_-]*$`（决定 Gateway 侧用哪个 `CapabilityAdapter`）。
- `source` 必须是 `https://` 开头；`icon` 必须以 `/images/plugins/` 开头且不含 `..` / `?` / `#`（防路径穿越与 query 注入）。
- `auth_methods ∈ {none, api_key, oauth}`；`contributions ∈ {tools, skills}`；`config_schema` 必须是 object；`name` / `description` / `setup` 都是 `dict[str, str]`（即**按 locale 分键**的展示文案）。

`load_catalog(path=None)` 读同目录的 `builtin.json`，对重复 `id` 抛 `ValueError("Duplicate plugin identifiers in catalog")`，**从不 import 或 eval 清单里的任何东西**。

**`builtin.json` 当前规模（2.2.0 实测）**：**15** 条 manifest —— `lark, dingtalk, wecom, tencent-docs, notion, openviking, web-search, web-fetch, exa, firecrawl, database, hubspot, github, atlassian, browser`。按 `category`：research 4 / office 3 / knowledge 3 / development 3 / business 2；按 `kind`：mcp 9 / native 5 / cli 1。

### 运行时身份与 MCP 插件过滤（`capabilities/runtime.py`）

- `installation_id(server_name, server)`：MCP server 配置里带 `capability.id`（Gateway 安装时写进去的）就用它，否则退化为 `uuid5(NAMESPACE_URL, f"deerflow:mcp:{server_name}")`——**名字派生、与进程无关**，所以同一份 `extensions_config.json` 在多个 Gateway 上算出一致的 id。
- `ambiguous_installation_ids(servers)`：统计被多个 server 声明成同一个 `capability.id` 的条目。歧义 id 必须**从"想要的集合"里剔除**而不是随便挑一个——否则用户勾选"装一个"会连带启用另一个同 id 的 server。
- `filter_mcp_plugins(tools, selected, config)`：非 MCP 工具原样保留；MCP 工具只有其所属 server 的 id 在 `selected` 里才保留，歧义 id 从 `wanted` 去掉。也就是 **`mcp_plugins` 是纯 deny-by-default 的白名单**，不是优先级提示。

### 内置业务 MCP provider（`capabilities/business.py`）

`dingtalk` / `wecom` / `hubspot` 三个 provider 是**随 harness 打包的 stdio MCP server**：`MODULE = "deerflow.capabilities.business"`，连接配置由 `connection_config(provider, configuration)` 生成——`{"type": "stdio", "command": sys.executable, "args": ["-I", "-m", MODULE, provider], "env": {...}, "enabled": True}`。`-I` 是隔离模式：启动的子解释器不读 `PYTHONPATH` / 用户 site，避免宿主环境污染 MCP server。

- 凭据只从 `CREDENTIALS` 表里取（`dingtalk: access_token/sign_secret`；`wecom: webhook_key`；`hubspot: access_token`），映射到固定环境变量名（`DEERFLOW_DINGTALK_ACCESS_TOKEN`、`DEERFLOW_DINGTALK_SIGN_SECRET`、`DEERFLOW_WECOM_WEBHOOK_KEY`、`DEERFLOW_HUBSPOT_ACCESS_TOKEN`）。
- 取值正则 `[A-Za-z0-9._~+/=-]{1,4096}`，字段集**必须精确等于**表里那一组，否则 `ValueError("Supply the required credentials only")`——多塞一个字段就拒，防止把任意环境变量捅进子进程。
- `is_bundled_connection(command, args, env)` 给 MCP 运行时一个**极窄的 allowlist 例外**：只有完全等于内置形状的命令才被认作"内置连接"并放行（普通 MCP server 的 stdio 命令通常需要操作者显式配置）。
- 客户端用 httpx 流式请求，20 s 超时、2 MiB 上限、**关闭重定向**（避免凭据被带去第三方域名）。

### Gateway 侧适配（`app/gateway/capabilities.py`，249 行）

`CapabilityAdapter` 是个结构化 Protocol（`list_installations` / `install`），registry 里注册了四个：`mcp`、`business`、`lark`、`skills`（`AdapterRegistry` 对重名抛 `ValueError(f"Adapter already registered: {name}")`）。

| adapter | `list_installations` | `install` |
|---|---|---|
| `mcp` | 读 `extensions_config.json` 的 MCP server，产出 `CapabilityInstallation`；歧义 id 渲染成 `ambiguous:<id>` + `selectable=False` + `health="ambiguous"` | 复用既有 MCP 创建逻辑，并写入 `capability: {id: uuid4, plugin_id, version}` 三元组 |
| `business` | 继承 `MCPAdapter`，只列 `plugin_id ∈ CREDENTIALS` 的 | 走 `connection_config()`，凭据校验同上 |
| `lark` | 飞书专用的展示条目 | 走飞书安装流程 |
| `skills` | 列当前用户可见的 skill，id 形如 `skill:<category>:<name>` | **故意不支持**：抛 422 `"Use the existing skill archive upload API"` |

**`MCPAdapter` 的两条硬纪律**：① 返回体**永不投影** URL / command / env / OAuth 细节，只给展示字段（`id, plugin_id, adapter, name, description, selectable, installed, enabled, version, scope, auth_status, health, reference, category, icon`）；② `icon` 只接受 `data:image/png;base64,` 开头且 ≤100 000 字符的内联 PNG——不接受远程 URL，避免把用户浏览器变成 SSRF 跳板。

**路由**（`app/gateway/routers/capabilities.py`，前缀 `/api/capabilities`，挂载点 `app/gateway/app.py:1344`）：

- `GET /catalog` —— 在 worker 线程里 `load_catalog()`（读盘），返回 15 条 manifest。
- `GET /installations/{adapter}?scope=deployment|user|all` —— `all` 只对 `mcp` / `business` 合并 deployment + user 两层；`can_manage = scope == "user" or is_admin_user`。
- `POST /installations` —— body `InstallRequest{plugin_id, name(≤128，默认空串), configuration, scope: deployment|user="deployment"}`。`deployment` scope 需要 admin（否则 400 `"Admin privileges required to install capabilities."`）；`user` scope **强制把 `user_id` 覆盖成请求里的调用者**（不能替别人装）；`plugin_id` 不存在 → 404 `"Plugin not found"`；user scope 下 adapter 不是 `mcp`/`business` 也需 admin（400 `"Admin privileges required to install this capability."`）。
- 没有安装适配器的能力（纯 setup 指南）→ 422 `"This capability only has a setup guide; no installation adapter is available"`（`AdapterRegistry.get`）。

> **域外提醒**：personal MCP 的 CRUD 路由在 `app/gateway/routers/personal_mcp.py`（本域未覆盖），但 2.2 把 `mcp_plugins` 的语义从"提示"改成了"白名单"（`capabilities/runtime.filter_mcp_plugins`），跨域断言请以那个函数为准。

## Skill mutation host service 🆕（2.2 新增：`skills/mutations/` + migration 0046）

`backend/packages/harness/deerflow/skills/mutations/`（15 个文件 / 2050 行）给**受信宿主插件**提供一条"受控修改现有用户 custom skill"的通道。它不是给 agent 用的：agent 走 `skill_manage`，宿主插件走这里的九步协议，两者的写路径最终共用同一批锁与闸门（`mutations/guard.py`）。权威叙述在 `docs/skill-evolution-host.md`（224 行）。

### 为什么需要它

插件想改用户的 skill，天然有四个坑：**并发**（用户同时在 Gateway 里编辑）、**所有权**（只能动自己那次安装的、用户自己的 custom skill）、**部分写入**（写一半崩了留下半新半旧的包）、**撤销**（改了之后要能回退）。这套服务把每个坑都做成了显式契约，而不是靠调用方自律。

### 准入条件（四条全满足才可用）

1. **durable DB**：SQLite 或 Postgres，且 `run_events.backend: db`（服务本身要写 `skill_mutation_*` 表；只看文件系统无法表达 PREPARED/APPLIED 状态）。
2. **单 POSIX 主机 + 本地文件系统**：`os.name == "posix"` 且拓扑是 `single_host_local`，否则 `HostCapabilityError("UNSUPPORTED_TOPOLOGY")`。原因写在 `mutations/topology.py` 里：CAS 发布依赖 `rename`/`mkdir` 的原子性，NFS 上不成立。SQLite 部署还要求**只有一个 Gateway**。
3. **静态扫描 + 已配置的扫描模型**：`skill_scan.enabled` 且能创建 chat model（`mutations/scanner.py`）。
4. **显式授权**：`config.yaml → plugins[].host_access.skill_mutations` 声明 `operations`（`stage`/`check`/`commit`/`revert` 的子集）、`trigger_agents`、`target_skills`、`topology`。

授权在 `deerflow/extensions/host_access.py`：`SkillMutationAccess(EvidenceAccess)` 携带上述四个字段，`BoundHostAccess.allows(operation, owner_id, name)` = `operation ∈ operations ∧ owner ∈ owners ∧ name ∈ target_skills`。**三元交集，缺一即拒**，且拒绝统一报 `HostCapabilityError("NOT_FOUND_OR_FORBIDDEN")`——不区分"不存在"和"没权限"，避免探测。

### 协议（`deerflow_extension_api/skill_mutations.py`，161 行）

`SkillMutationService` 是一个 10 方法的 Protocol：`read_skill` → `stage` → `get_proposal` → `read_proposal_bundle` → `check` → `commit` → `discard` / `revert` → `get_operation` / `find_operation`。

- `AssetRevision(incarnation_id, mutation_seq, content_digest)` 是**三要素版本**：光有内容 hash 不够（内容可能改回旧值），光有序列号也不够（换实例后序列号会重用）。
- `MutationCapabilities` 公布全部上限，探测用 `protocol_version = "skill-mutations-v1"`：`max_main_bytes` 131072、`max_package_bytes` 16777216、`max_package_files` 256、`max_sources` 20、`max_pending_proposals` 20、`max_model_scan_files` 32、`max_model_scan_bytes` 1048576、`max_model_scan_file_bytes` 131072、`max_concurrent_scans` 4、`max_owner_plugin_concurrent_scans` 2、`max_owner_plugin_scans_per_hour` 20、`check_timeout_seconds` 120、`proposal_ttl` 86400、`check_ttl` 900、`rollback_ttl` 2592000、`topology = "posix-single-host-local-filesystem"`。
- `Operation ∈ {stage, check, commit, discard, revert}`；`Proposal` / `BundleFile` / `ProposalBundle` / `HostCheckResult` / `AssessmentRef` 是不可变 DTO。

### 状态机与恢复

发布是 **CAS（compare-and-swap）**：`mutations/publication.py` 的 `assert_temporary_absent` + `publish_prepared` 先在临时路径准备好完整包，再一次性 `rename` 到目标，中途崩溃只会留下 PREPARED 残留。

- `PREPARED`：临时产物存在，目标未被替换 → 恢复动作是**清掉残留**（`mutations/recovery.py::SkillMutationRecovery`）。
- `APPLIED`：目标已替换 → 恢复动作是**把 owner 状态推到终态**，不是回滚。
- `NEEDS_REPAIR`：需要人工/管理员介入；**处于这个状态时不允许降级**（`docs/skill-evolution-host.md` 明确写 no downgrade）。
- 回滚窗口 `rollback_ttl = 30 天`（2592000 s）。`revert` 把内容退回上一个 revision，但 **`views=ERROR` 不等于可以回滚**——视图错误是投影问题，不是内容问题（文档专门点名这个误区）。

**扫描闸门（`mutations/scanner.py`，111 行）**：`CHECK_POLICY_VERSION = "skill-mutation-check-v1"`，模型文件预算 `MAX_MODEL_FILES=32` / `MAX_MODEL_BYTES=1 MiB` / `CHECK_TIMEOUT_SECONDS=120`。策略哈希 = `sha256(CHECK_POLICY_VERSION, PARSER_VERSION, skill_scan.enabled, moderation_model_name, 全部 model 配置（去掉 api_key）)`——**换了模型或改了扫描策略，旧的 check 结论就作废**（必须重新 check）。失败一律 fail-closed：`config.skill_evolution.security_fail_closed` 被**强制**置 `True`（不继承手动路径的 fail-open 开关），`ScanVerdict(decision, reason_code, policy_version)` 只有 `allow` 能 commit；`SCANNER_DISABLED` / `SCAN_LIMIT_EXCEEDED` / `SCANNER_INCOMPLETE` / `SCANNER_UNAVAILABLE` 全部是 `unavailable`（→ 不能 commit）。`reason_code` 只回代码，**不回模型/provider 内容**（异常路径注释原话：`Error details can include model/provider content. Return codes only.`）。

`ScanResult.available` 这个 2.2 新字段就是为这条链路加的：扫描器"不可用"（模型调用失败、输出不可解析、可执行内容无扫描器）与"明确 block"以前都只是 `block`，宿主服务无法区分"内容有问题"和"扫描器坏了"；现在前者 `available=False` → `SCANNER_UNAVAILABLE`，后者 `available=True` + `block` → `MODEL_SCAN_REJECTED`（`security_scanner.py:24-27,164-181`；消费点 `mutations/scanner.py:102-105`）。

### 关键实现模块

| 模块 | 作用 |
|---|---|
| `mutations/service.py`（608 行） | `HostSkillMutationService` 主实现；`capabilities` 属性把 binding 的 `operations` 投影出来；`_authorize` 做三元交集判定 |
| `mutations/guard.py`（186 行） | **锁与栅栏的唯一来源**：`managed_global_read` / `managed_read` / `managed_global_state_write` / `managed_name_writes(storage, names)` / `managed_writer` / `read_optional_text` / `owner_is_managed`。所有 storage、projection、export 的读写都嵌在这些 context manager 里，锁顺序固定 global → owner → name，避免死锁 |
| `mutations/enrollment.py`（65 行） | `require_unenrolled` 检查 owner 是否已被本功能接管；DB 用**只读 sqlite URI**（`mode=ro`）+ `NullPool`，**绝不创建库** |
| `mutations/assets.py`（148 行） | `capture_package` / `MAX_PACKAGE_BYTES`：包快照在内存里冻结 |
| `mutations/publication.py`（183 行） | 临时目录准备 + 原子发布 |
| `mutations/repository.py`（127 行） | revision 读写（`incarnation_id` / `mutation_seq` / `content_digest`） |
| `mutations/scan_budget.py`（38 行） | `reserve_scan` / `release_scan`：并发扫描与每小时配额 |
| `mutations/workers.py`（67 行） | `MutationWorkers`：把阻塞的扫描/发布 offload 出事件循环，`close()` 会 drain 在途工作 |
| `mutations/codec.py` / `history.py` / `validation.py` / `topology.py` | 序列化、history、`MAX_MAIN_BYTES` + `validate_candidate`、拓扑判定 |

### 数据模型（migration `0046_skill_mutations`）

`backend/packages/harness/deerflow/persistence/migrations/versions/0046_skill_mutations.py`：`revision = "0046_skill_mutations"`，`down_revision = "0045_completed_run_evidence"`，下一个 revision `0047_mcp_oauth_tokens` 修订它。

- `skill_mutation_assets`：主键 `target_ref`，唯一约束 `uq_skill_asset_owner_name`；列 `incarnation_id / mutation_seq / content_digest / enabled / deleted / mutating / operation_id`。
- `skill_mutation_operations`：操作流水（含 PREPARED/APPLIED 判定依据）。
- 还有 owner 状态表、`skill_mutation_proposals` 表、`SkillScanAttemptRow` 表（扫描配额的事实来源）。
- `_create_table` 能容忍 `create_all` 已经建过的同名表；形态不兼容时抛 `RuntimeError(f"Incompatible preexisting skill mutation table: {name}")`——**不静默复用**。

> 迁移本身的细节属于 persistence 域；这里只钉它解决的问题（三要素 revision 的持久化）与表名，便于交叉引用。

### 管理面路由（`app/gateway/routers/skill_mutations.py`，52 行）

前缀 `/api/skill-mutations`（挂载点 `app/gateway/app.py:1357`），**全部 admin-only**，且 `app.state.skill_mutation_host` / recovery 缺失时统一 503 `UNAVAILABLE`：

- `GET /operations` —— `limit` 1–100（默认 50）、`after_id` 为 32 位 hex；返回 `{items, has_more, next_cursor}`。
- `GET /operations/{operation_id}` —— id 必须 32 位 hex。
- `POST /operations/{operation_id}/recover` / `POST /owners/{owner_id}/recover` —— `OwnerId` 正则 `^[A-Za-z0-9_-]+$`、1–128 字符。
- 错误映射：`NOT_FOUND_OR_FORBIDDEN` / `NOT_FOUND` → 404；`NEEDS_REPAIR` / `REVISION_CONFLICT` → 409；其余 → 503。
- **没有 force-overwrite 端点**：冲突只能靠重新 `read_skill` 拿新 revision 再 `stage`，或由管理员 `recover`。

### 与 agent 侧 `skill_manage` 的关系

两者写的是**同一批文件、同一把名锁**（`managed_name_writes`），差别在准入：

| 维度 | `skill_manage`（agent） | `HostSkillMutationService`（插件） |
|---|---|---|
| 谁能调 | 当前 run 的 user | `plugins[].host_access.skill_mutations` 授权的插件 |
| 可改范围 | 自己 `custom/` 下的任意 skill（含新建/删文件） | 仅**已启用**的 user custom `SKILL.md` 的 **body + description**（P0） |
| 闸门 | 静态扫描 + LLM 三态 | 静态扫描 + LLM + policy 哈希 + CAS + check TTL |
| 撤销 | history + `POST /skills/custom/{name}/rollback` | `revert`（30 天窗口） |
| 并发 | `_SkillLock`（进程内跨 loop） | DB revision + 文件锁 |

## 自定义 skill 加载诊断 🆕（2.2）

用户写坏 `SKILL.md` 的 YAML 时，日志里的 yaml 异常串既带宿主路径又对用户毫无指导意义。2.2 新增一条**只服务管理面**的诊断通路，明确不进入 agent 的 catalog。

- `skills/diagnostics.py`（35 行）：`SkillLoadDiagnostic(package, path="SKILL.md", code="invalid_frontmatter", hint, line, column)`；`yaml_load_diagnostic(package, exc, source, line_offset)` 把 `yaml.YAMLError` 投影成稳定字段——**不序列化异常对象**（否则宿主路径与内部细节会漏出去）。
- `hint` 目前只有一个取值 `quote_colon_value`，且**只在** `exc.problem == "mapping values are not allowed here"`、"冒号后的值未加引号/不以块标量符号开头"、"错误列正好落在 `: ` 上"三条同时成立时才给——这就是最典型的 `description: foo: bar` 忘加引号。其它 YAML 错误只给行列号，**不猜**。
- 只有 `yaml.YAMLError` 会产生诊断；缺 frontmatter、frontmatter 非 mapping、非 UTF-8、读盘失败**都不算**诊断（那些是"文件不是 skill"或"环境问题"，不是用户可修的 YAML 错误）。
- 采集入口：`SkillStorage.load_custom_skill_diagnostics()`（基类默认 `[]`，`storage/skill_storage.py`）；user-scoped 实现**只扫调用者自己的 custom root**，先核对 `root.resolve()` 精确等于 `users/{uid}/skills/custom`，否则返回 `[]`；途中任何解析后跳出该目录的路径直接剪枝；**符号链接/外部包一律排除**（管理面无法在调用者的 custom root 之外确立所有权）。并发删除/重定向的包被 `except (OSError, RuntimeError): continue` 跳过——"包刚好不见了"不是 YAML 错误。
- 路由：`GET /api/skills/diagnostics/custom`（`app/gateway/routers/skills.py:672`），admin-only，响应头 `Cache-Control: no-store`（诊断随磁盘即时变化），失败 → 500 `"Failed to load custom skill diagnostics."`（不回传异常细节）。

## 容器路径 ↔ canonical skill 名注册表 🆕（2.2）

`skills/container_registry.py`（40 行）解决一个长期歧义：**skill 目录名和 frontmatter 里声明的 `Skill.name` 是两件独立的事**。沙盒里脚本拿到的是容器路径 `/mnt/skills/{category}/{dir}/SKILL.md`，而授权层、`/skill-name` 激活、`skill_context` 全都说**声明名**。

- `build_container_path_registry(storage)`：用 `load_skills(enabled_only=False)`（含禁用 skill，阻塞式扫描）建一个"归一化容器路径 → skill"的字典。
- `canonical_skill_name(registry, skill_md_path) -> str | None`：把任意形状的容器路径归一到同一 key 再查声明名。
- 纪律：**授权层永远说声明名**，容器路径只在边界处转换一次；不要在任何授权判定里直接比较目录名。

## 自定义 skill 存储的 2.2 加固

- **读取一律 `encoding="utf-8-sig"`**，写出一律 `encoding="utf-8"` + `newline=""`：BOM 在读取侧被剥掉，LF 在写出侧不被 Windows 改成 CRLF（`storage/local_skill_storage.py::read_custom_skill` / 写路径）。这与 `AGENTS.md` 的「Skill text encoding」纪律是同一条。
- **`walk_skill_directories(root)`**（`storage/skill_storage.py:23-45`）统一取代裸 `os.walk`/`rglob`：`os.walk(root, followlinks=True)` 之后用一条**只记当前分支**的 `ancestors` 栈（元素是 `(current_path, resolved)`）剪掉指回祖先目录的环——`dir_names.clear()` 后 `continue`，于是 `a -> ..` 这类自引用不会无限遍历。**故意只记当前分支**：两棵各自独立的外部 skill 树别名必须都能被发现，所以不能全局去重 resolved 路径。解析失败（`OSError`/`RuntimeError`，目录在扫描中被删或链接改了）同样 `dir_names.clear()` 跳过，不炸整次扫描。
- **`read_text_or_none(path)`**（`storage/skill_storage.py:48-58`）：`read_bytes().decode("utf-8")`，非 UTF-8 返回 `None` 而不是抛 `UnicodeDecodeError`。docstring 交代用途仅限 history 记录：支持文件可以是二进制（installer 只拒可执行二进制，不拒图片等资产），"没有可记录的旧文本"绝不能中断正在记录的那次变更。
- **`remove_custom_skill_file` 拒绝目录**：传进来的是目录时报错而不是 `rmtree`（`remove_file` 只能删文件）。
- **原子写失败清理**统一走 `cleanup_failed_atomic_write(tmp_path)`（`deerflow.utils.atomic_write`），不再各写各的 `unlink(missing_ok=True)`。
- **`_skill_projection_mutation(names=(name,))`**：所有 local storage 的变更只锁**受影响的 skill 名**，不再整 scope 排他，并发编辑不同 skill 不再互斥。
- **storage 工厂透传 `app_config`**：`_make_storage(skills_config, *, app_config=None, host_path=None, **kwargs)`（`skills/storage/__init__.py:58-68`）只在 `issubclass(cls, LocalSkillStorage)` 时把 `app_config` 塞进 `kwargs`，并且**始终**传 `container_path=skills_config.container_path`（`:66`）。`get_or_new_user_skill_storage` 与 `user_should_see_legacy_skills` 另用 `kwargs.setdefault("container_path", app_config.skills.container_path)`（`skills/storage/__init__.py:133,174`）兜底——容器根路径只有一个来源，不再各调用点硬编码。

## 内置 skill 归档安装的 2.2 变化（skills 侧摘要）

> 完整链路见 [`skill-package-intake.md`](skill-package-intake.md)；这里只列影响 skills 子系统断言的几条。

- `installer._scan_skill_file_or_raise(..., app_config=None)` 现在把 `app_config` **透传**给 `scan_skill_content`，SKILL.md、可执行文件、支持文件三条分支都走同一条。此前安装路径在某些分支上会丢掉 `app_config`，导致 `security_fail_closed` / kill switch 配置被静默忽略。
- **可执行 magic 嗅探容忍前导填充**：`executable_binary_magic(prefix)` 允许一定长度（<64 字节）的空白/NUL 填充再出现 magic，UTF-8 BOM 作为整体被跳过一次；连续 ≥64 字节填充直接判 `None`（不是可执行）。`EXEC_SNIFF_BYTES = 63 + max(magic len)` 就是按这个边界算出来的。
- **`CODE_SUFFIXES` 扩到 21 个**：`.bash .bat .cjs .cmd .hta .js .jse .mjs .php .pl .ps1 .psm1 .py .rb .sct .sh .ts .vbe .vbs .wsf .zsh`（2.1 是 12 个，缺 `.bat/.cmd/.hta/.jse/.php/.psm1/.sct/.vbe/.vbs/.wsf` 等 Windows 侧可执行类型）。新增 `is_scripts_member` 明确"成员位于 `scripts/` 下"这一独立判据。
- **`is_eval_fixture_path` 等价重写**（`skills/package_paths.py`）：语义不变（`evals/<x>/fixtures`），只是实现改写。
- `security_scanner.ScanResult` 新增 `available: bool = True`，见上文 mutation 一节。

## Per-Agent Skill 控制

Custom agent 的 `config.yaml`：
```yaml
skills: ["deep-research"]   # null=全部, []=禁用, ["a"]=指定
```

**Sandbox 文件系统层强制（#5077）**：lead custom Agent 的显式 `skills` 列表（含 `[]`）现在落到 sandbox projection——线程级视图 `threads/{thread_id}/skills_view/{public,custom,legacy,integrations}` 只物化「已启用 ∩ 白名单」的 skill，`skills=None` 保持共享零拷贝挂载直到该线程用过显式策略。策略重建先撤销全部旧类别再挂新策略，拒绝绝对符号链接和解析到包外的相对符号链接；视图内篡改通过源/视图元数据树摘要校验在下一次 acquire 时修复。subagent 的 `skills` 字段仍只限定发现与激活（并发委派的 subagent 共享 lead 线程 sandbox）。

## Skill 写入门与 `skill_manage`（skills 侧不变量）

`skill_manage` 工具面（参数、action 枚举、加载条件）见 [builtin-tools/C-agent-lifecycle.md](../builtin-tools/C-agent-lifecycle.md#skill_manage)；这里只钉 skills 子系统这侧的不变量与已发现的文档偏差。

**写入门顺序是固定的三段**（`tools/skill_manage_tool.py:131-215,240-330`）：

1. **静态 SkillScan candidate 扫描**（`enforce_static_scan`，命中 CRITICAL 即 `ValueError`）——发生在任何 LLM 调用**之前**（锚 `backend/tests/test_skill_manage_tool.py:255,296`）。候选树在**临时目录**里拼（`_scan_static_candidate_or_raise`），copytree 现有 custom skill 时包在 `managed_read(skill_storage)` 里；候选文件一律 `write_text(..., newline="")` 写——Windows 默认文本模式会把 LF 改写成 CRLF，扫描器看到的就不是实际发布的字节（`skill_manage_tool.py:156-172`）。
2. **LLM 审核** `scan_skill_content`：三态 `allow|warn|block`；`block` 直接拒绝；`executable=True` 的内容必须 `allow`（`_scan_or_raise`，`skill_manage_tool.py:131-140`）。in-graph 调用固定 `attach_tracing=False`（图根已挂载 tracing），返回 `{"decision", "reason"}` 记进 history（锚 `backend/tests/test_skill_manage_tool.py:391`）。
3. 原子写盘 + 历史 + 缓存刷新 + **跨进程失效标记**，四件事作为**一个 drained 单元**收敛（`_settle_skill_mutation`，`skill_manage_tool.py:190-215`）：`await_drained` 包住 `persist()` → `refresh_user_skills_system_prompt_cache_async(user_id)` → `publish_skills_cache_reset(user_id=user_id)`。理由写在 docstring 里：取消 `asyncio.to_thread` 只是放弃 await，**worker 仍会写完**，于是被取消的 run 会带着"写已落盘、本进程和同伴进程还在服务旧 skill 列表"的状态退出。标记写入是文件 IO，走 `to_thread`。发布失败抛 `SkillCacheResetPublishError`，消息明确写「变更**已经**生效，只是其它 Gateway 进程没被通知」——避免模型把成功当失败重试。

**candidate 的构成决定"能否绕过"**：`create/edit/patch` 扫的是"临时目录 + 覆盖后的 SKILL.md"；`write_file` 扫的是"**整棵现有 custom skill 树** + 目标文件"，所以新增脚本同样会触发既有文件里的 CRITICAL 规则。静态扫描在 worker 线程执行（`_to_thread`/`asyncio.to_thread`）。

**其他契约**：

- `patch`：`find` 不存在（0 次命中）→ 报错；给了 `expected_count` 时实际次数必须精确相等，替换次数取 `expected_count`，未给则只替换 **1** 次（`skill_manage_tool.py:279-281`，锚 `tests/test_skill_manage_tool.py:89`）。
- 锁粒度 `(user_id, skill_name)`，存在 `WeakValueDictionary` 里——跨用户不互相阻塞（`_get_lock`，`skill_manage_tool.py:97-110`）。
- `write_file` / `remove_file` 的 `path` 必须通过 `ensure_safe_support_path`（只允许 `references/templates/scripts/assets` 顶层目录，锚 `tests/test_skill_manage_tool.py:183`）。
- `write_file` 的可执行判定走共享的 `package_files.is_code_file(path, content[:8].encode(...))`——不再只看路径里有没有 `scripts/`，同一条规则覆盖 `.bash/.bat/.cmd/.js/.ts/.ps1/...` 等 21 个后缀，以及无后缀但首行 `#!` 的文件；命中才要求 LLM 决策为 allow（`skill_manage_tool.py:22,321`）。
- 历史记录字段固定：`action / author="agent" / thread_id / file_path / prev_content / new_content / scanner`；`delete` 与 `remove_file` 记 `scanner={"decision": "allow", "reason": "Deletion requested."}`（`_history_record`，`skill_manage_tool.py:114-123,298,339`）。
- 最后的分支把"未知 action"和"目标是 public/legacy 只读"统一成 `ValueError`。

**跨事件循环锁 🆕（2.2 重写，upstream #5846）**：`_SkillLock`（`skill_manage_tool.py:40-92`）替代了原来的 `asyncio.Lock`。原因是同步包装器 `make_sync_tool_wrapper` 每次 `tool.invoke()` 都起自己的 `asyncio.run` 循环，而 `asyncio.Lock` 绑定到创建它的那个循环——在 A 循环里等 B 循环持有的锁会永远挂住（waiter 卡死）。现在的实现：`threading.Lock` 保护 `_locked` + `deque[(Future, loop)]`，每个 waiter 停在自己的 `Future` 上（`asyncio.wrap_future`），在自己所属的 loop 上被唤醒，**等待期间不占执行器线程**；`_release()` 把锁**直接交给最老的 waiter**（FIFO handoff），后来者不能插队；waiter 被取消时若 `Future.cancel()` 失败（说明锁已交到它手上）必须继续 `_release()`，否则身后的调用者永久等待；已关闭的 loop 上的 waiter 被跳过。

**本文档早前一处措辞补充**：`skill_manage` 各变更分支调用的是 **per-user** 版本 `refresh_user_skills_system_prompt_cache_async(user_id)`（`tools/skill_manage_tool.py:20,203`；实现在 `agents/lead_agent/prompt.py:373`），而非无参的全局 `refresh_skills_system_prompt_cache_async()`（`prompt.py:347`）。两者都存在，别写混；而且 2.2 起**光刷本进程缓存不够**，必须再 `publish_skills_cache_reset(user_id=...)` 通知共享 home 卷上的其它 Gateway 进程。

**共享失效标记 `SharedResetMarker("skills-cache-reset")` 🆕（2.2）**（`agents/lead_agent/prompt.py:76-77,108-160`）：标记文件落在共享 extensions 配置旁边，每个进程各自记录已消费的标记值，看到更新的值就丢自己的 prompt 缓存。`SkillCacheResetPublishError` 是它的专用异常。这条通路与 Gateway 侧 `POST /api/skills/reload` 用的是**同一套机制**：reload 的 `scope` 字段区分 `shared_config`（已发布标记，多进程生效）与 `process`（只清了本进程缓存）（`app/gateway/routers/skills.py:598-644`）。

---

## Tool 系统

### `get_available_tools()` — 工具装配

调用位置：`_make_lead_agent()` 中。

### 装配顺序

1. Config-defined tools（`config.yaml` → `tools[]`，通过 `resolve_variable()` 动态加载）
2. MCP tools（懒初始化，mtime 缓存失效）
3. Built-in tools：`present_files`、`ask_clarification`、`view_image`（vision）、`setup_agent`（bootstrap）、`update_agent`（custom agent）、`tool_search`（deferred MCP）、`describe_skill`（deferred skill 模式）
4. Subagent tool：`task`（if `subagent_enabled`）
5. ACP agent tools：`invoke_acp_agent`

### 去重规则

按工具名称去重。优先级：Config-defined > MCP > Built-in。

### MCP 工具集成

Transport：stdio、SSE、HTTP。OAuth 支持 client_credentials + refresh_token。Deferred loading 通过 `tool_search` 工具按需发现。

### 内置工具详情

> 实现文件名按 v2.1.0 源码实测（`tools/builtins/` 下的模块名以 `_tool` 结尾，此前本表的文件名是旧称）。

| 工具 | 条件（注册点 `tools/tools.py` 为准） | 实现 |
|------|------|------|
| `present_files` | 始终（`BUILTIN_TOOLS`） | `tools/builtins/present_file_tool.py` |
| `ask_clarification` | 始终（`BUILTIN_TOOLS`；non_interactive 时从工具集移除） | `tools/builtins/clarification_tool.py` |
| `review_skill_package` | 始终（`BUILTIN_TOOLS`，skill 质量审查） | `tools/builtins/review_skill_package_tool.py` |
| `view_image` | 模型 `supports_vision` | `tools/builtins/view_image_tool.py` |
| `list_uploaded_files` | 有上传上下文（`include_upload_tool`） | `tools/builtins/list_uploaded_files_tool.py` |
| `list_background_tasks` / `cancel_background_task` | MCP task runtime 可用 | `tools/builtins/background_tasks_tool.py` |
| `task` | `subagent_enabled` | `tools/builtins/task_tool.py` |
| `batch_task` / `batch_status` / `cancel_batch` | `subagent_enabled` + batch runtime 可用 | `tools/builtins/batch_task_tool.py` |
| `invoke_acp_agent` | 配置了 ACP agent（`build_invoke_acp_agent_tool`） | `tools/builtins/invoke_acp_agent_tool.py` |
| `tool_search` | `tool_search.enabled`（deferred discovery） | `tools/builtins/tool_search.py` |
| `describe_skill` | `skills.deferred_discovery` | `skills/describe.py` |
| `skill_manage` | `skill_evolution.enabled` | `tools/skill_manage_tool.py` |
| `setup_agent` | bootstrap 模式（`lead_agent/agent.py` 追加） | `tools/builtins/setup_agent_tool.py` |
| `update_agent` | custom agent 模式（`lead_agent/agent.py` 追加） | `tools/builtins/update_agent_tool.py` |

## 故障排查

| 症状 | 可能原因 | 检查 |
|------|---------|------|
| Skill 不出现 | 未启用 | `extensions_config.json` → `skills.{name}.enabled: true` |
| Skill 不出现 | Agent 白名单 | custom agent `config.yaml` → `skills:` 包含该 skill |
| Skill 不出现（deferred 模式） | 索引未构建 | `skills.deferred_discovery: true` + skill 目录存在 `SKILL.md` |
| 修改后未生效 | 目录扫描本身不做缓存，但 prompt 层启用态缓存/段落 LRU 与 storage 单例可能持有旧视图 | 直接改磁盘后调 `POST /api/skills/reload`（admin-only；只清 prompt 缓存，不重建 storage 单例）；`load_skills()` 每次都重扫目录并重读 `extensions_config.json` |
| Secret 未注入 | 声明缺失 | `SKILL.md` frontmatter → `required-secrets: [NAME]` |
| Secret 未注入 | 调用方未传 | run request `context.secrets` 包含该 key |
| Secret 未注入（自主加载） | 被阻止 | `secrets-autonomous: false` 阻止了 in-context 绑定，用 `/skill-name` 显式激活 |
| /skill-name 不生效 | 语法错误 | 严格格式：`/skill-name task description`（斜杠+名称+空格+task+空格+描述） |
| /skill-name 不生效 | 保留命令 | `/new`、`/help` 等保留命令被拒绝 |

---
> **See also:** [Security: Input Sanitization & Secrets Redaction](../../enterprise-operations/security/03-guardrail.md) · [Middleware: SkillActivationMiddleware](../../internals/middleware/03-catalog.md) · [Testing Skills](../../testing/05-testing-skills-and-workflows.md)
