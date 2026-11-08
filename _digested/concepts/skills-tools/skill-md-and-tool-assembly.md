---
title: "Skills 与 Tool 系统"
description: "Skills 加载（legacy + deferred 双模式）、request-scoped secrets、slash 激活、Tool 装配链。"
topics: [skills, tools, prompt-engineering]
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
| `allowed-tools` | 工具白名单（可选）。标量形式支持可移植拼写（`Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`/`WebFetch`/`WebSearch` 映射到 `bash`/`read_file`/`write_file`/`str_replace`/`glob`/`grep`/`web_fetch`/`web_search`），未知名保持原样；分词器保留引号与括号模式（含空格/转义括号）内部完整，未闭合引号或括号直接报错（#4984） |
| `required-secrets` | 🆕 字符串或 `{name, optional}` 列表——skill 需要的请求级密钥 |
| `secrets-autonomous` | 🆕 `true`（默认）= agent 自主加载时绑定密钥；`false` = 仅显式 `/skill-name` 激活时绑定 |

**白名单全集（11 个键）**：`ALLOWED_FRONTMATTER_PROPERTIES = {name, description, license, allowed-tools, argument-hint, required-secrets, secrets-autonomous, metadata, compatibility, version, author}`（`deerflow/skills/frontmatter.py:15-27`）。上表 6 个之外还有 `argument-hint`、`metadata`、`compatibility`、`version`、`author`——它们能通过安装/写入门校验，但不参与运行时装配。未知键在安装/写入门是**硬失败**（`skills/validation.py:42-44`），在 review core 里只是 warning（`skills/review/analyzer.py:164-175`）。非字符串 YAML 键会被 `str()` 化后当成未知字段，而不是崩溃（`frontmatter.py:58-63`）。

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

- `build_skill_search_setup(skills, *, enabled, container_base_path=...) -> SkillSearchSetup(describe_skill_tool, skill_names)`：`enabled=False` 或 `skills` 为空 → `SkillSearchSetup(None, frozenset())`，agent **回退到 legacy 全量元数据 prompt**；否则用**过滤后的**列表建 `SkillCatalog`，`skill_names = catalog.names`（`describe.py:36-49,103-125`）。
- `build_describe_skill_tool(catalog, ...)` 是 `@tool` 闭包：无匹配返回文本 `"No skills matched: {query}"`，命中返回 markdown 块；返回值是 `Command` 包 `ToolMessage(name="describe_skill")`，**不写 graph state**（不同于会提升 deferred tool 的 `tool_search`）（`describe.py:52-100`）。
- 渲染时 name / description / allowed-tools / 容器路径全部做 HTML entity 转义——frontmatter 是不可信输入，不转义就能伪造框架标签（`describe.py:131-145`）。
- `get_skill_index_prompt_section(...)` 名字为空返回 `""`；否则按名排序渲染 `<skill_system>…<skill_index>…</skill_index>` 并附容器根路径（`describe.py:151-188`）。
- **catalog 查询边界**（`skills/catalog.py`）：`select:` 在截断之前解析，无长度/结果上限且保持 catalog 顺序；其它查询先截断到 `MAX_QUERY_CHARS=256` 字符；裸 `+`（无 required token）→ `[]`；单字符 ASCII term 按整词匹配，`a`/`I` 被忽略（其余单字符保留，如 C++/R）；词数上限 16；结果上限 5；同分稳定排序保留 catalog 顺序（`25-32,42-60,63-66,96-116,145-177`）。`SkillCatalog` 是 frozen dataclass 但**不能加 `slots=True`**：`names` / `_search_index` 是 `cached_property`，靠 `__dict__` 缓存（`119-143`）。

## `/skill-name` 斜杠激活

文件：`deerflow/agents/middlewares/skill_activation_middleware.py`

`SkillActivationMiddleware` 检测用户消息中的 `/skill-name task` 语法：

1. `parse_slash_skill_reference()` 解析严格格式
2. 拒绝保留命令（`/new`、`/help`、`/bootstrap`、`/status`、`/models`、`/memory`、`/goal`、`/agent`——最后者为 🆕）
3. 解析到的 skill 必须已启用且在 agent 白名单内
4. 注入 `SKILL.md` body 为隐藏 HumanMessage（`hide_from_ui: True`），插入到触发消息之前
5. 记录审计事件 `middleware:skill_activation`（name、category、path、content_hash——不含 body）

**跨语言契约**：保留名单与 skill 名语法由 `contracts/slash_skill_contract.json` 固定，后端解析器 `deerflow/skills/slash.py` 与前端展示解析器 `frontend/src/core/skills/slash.ts` 必须一致——否则 transcript 会为后端根本不会当作激活的文本渲染激活 chip。约定内容：`reserved_slash_skill_names` = `agent` / `bootstrap` / `goal` / `help` / `memory` / `models` / `new` / `status`（8 个保留控制命令）；`skill_name_pattern` = `^/([a-z0-9]+(?:-[a-z0-9]+)*)(?:\s+|$)`。两侧各有一份契约测试（`backend/tests/test_slash_skill_contract.py`、`frontend/tests/unit/core/skills/slash-contract.test.ts`）钉住 fixture。

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

**热加载纠偏 🆕（v2.1.0 源码）**：早前本文写的"`get_or_new_skill_storage()` 检测 `extensions_config.json` 变化后重建 storage"**不成立**——storage 不缓存 catalog，`load_skills()` 每次调用都重新扫描目录并重读 `ExtensionsConfig.from_file()`（`skills/storage/skill_storage.py:296-308`）；进程单例只按当前 `AppConfig` 身份失效/重建（`skills/storage/__init__.py:36-101`）。外部写入后的失效入口是 admin-only `POST /api/skills/reload`（`app/gateway/routers/skills.py:357-362`）→ `refresh_skills_system_prompt_cache_async()`：清的是 prompt 层按 `(config, user_id)` 的启用态缓存（上限 256）与 prompt 段落 LRU，**不重建 storage 单例**（`agents/lead_agent/prompt.py:238,195-213`）；单用户版本 `refresh_user_skills_system_prompt_cache_async(user_id)` 供 `skill_manage` 使用（`prompt.py:264-274`）。

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

- **`package_files.py` 是"哪些是代码 / 哪些字节是可执行"的唯一来源**——installer 的抽取 guard、export 的阻断规则、SkillScan 都 import 它，不得各自再写一份（模块 docstring，`package_files.py:1-5`）。契约：`CODE_SUFFIXES` 12 个后缀（`.bash .cjs .js .mjs .php .pl .ps1 .py .rb .sh .ts .zsh`）；`is_code_path` = 顶层目录为 `scripts/` **或**后缀命中；`is_code_file` 再加"无后缀且以 `#!` 开头"；`is_executable_binary_prefix` 用完整 magic（ELF、`MZ`、8 种 Mach-O，不用共享短前缀以免误判数据文件）（`package_files.py:11-45`）。锚点：`backend/tests/test_skillscan_native.py:382`（与安装器抽取 guard 一致）、`393`（截断 magic 不算可执行）。
- **`package_paths.py` 是 eval fixture 判定的唯一来源**：路径中出现 `evals` 且其后仍 ≥2 段时，`evals` 的下一段必须是 `fixtures`；`is_eval_fixture_skill_md` 在此基础上加"末段是 `SKILL.md`"（`package_paths.py:12-24`）。review 与 SkillScan 的豁免/收紧都以它为准。
- **`permissions.py`**：目录 → `0o555`、文件 → `0o444`（去掉 group/other 写位再或上只读位），符号链接直接跳过；`make_skill_tree_sandbox_readable` 递归整棵树（含隐藏路径），`make_skill_written_path_sandbox_readable(skill_root, target)` 只处理"根 → 目标"这一条路径且要求 target 已在 skill_root 内，否则抛 `ValueError`（`permissions.py:7-34`，锚 `backend/tests/test_skill_permissions.py:19,49`）。

## Projection 物化契约（`skills/projection.py`）

> 共享/线程投影的**行为变化**（enabled-only、按策略隔离）见下文「`/mnt/skills` 收归 managed enabled-only projection」一节；这里列的是它之下调用方必须知道的不变量。

- **常量**：manifest `version=1`、每个 scope 最多重建 `_MAX_REBUILD_ATTEMPTS=2` 次、线程策略版本 `_THREAD_PROJECTION_POLICY_VERSION=1`（`projection.py:35-37`）。清单落在 `<scope_root>/.projection-manifest.json`，含 `source_signature` + `view_signature`，用 mkstemp + `replace` 原子写（`380-409`）。
- **路径作用域**：全局 public 视图一份；user custom/legacy/integrations 每人一份；线程视图在 `users/{uid}/threads/{tid}/skills_view/{public,custom,legacy,integrations}`。线程投影要求 user-scoped storage，否则 `ValueError`（`50-84`）。`thread_skill_projection_exists()` 只看该线程 scope 根目录是否存在（`87-90`）。
- **锁**：每个 scope 一把进程内 `RLock` + `<parent>/.<name>.projection.lock` 的 POSIX `flock`（Windows 走 msvcrt）（`99-118`）。稳态新鲜度检查在锁外做；只有 stale/异常才进锁并**二次检查**（`683-721`）。
- **新鲜度 = 清单双读一致 + 双签名相等**：清单在计算前后必须逐字节一致（否则视为并发改写 → 重建）；`source_signature` 覆盖源目录树元数据 + `extensions_config`（user scope 另加 per-user states），`view_signature` 覆盖视图元数据（`412-424,441-455`）。
- **源签名只哈希目录元数据**（inode/mode/size/mtime_ns），刻意不读文件内容：换来每次 sandbox acquire 都能 O(files) 检查；代价是"inode+size+mtime 都不变的外部改写"不可见，直到下一次显式重建。代码路径内的写入不受影响——变更路径持锁重建，原子替换一定换 inode（`289-335`）。custom/legacy 类别根下第一层包目录符号链接会被跟随并将其 target 路径计入签名（`305-309,354-365`）。
- **线程策略重建先撤销再挂新**：清空四个类别 → 逐个填充，fail-closed。并发读者可能短暂看到更少的 skill，但绝不会看到被新策略撤销的 skill；类别根 inode 保持稳定以服务 live bind mount（`549-609`，锚 `tests/test_skill_projection.py:441`）。
- **零拷贝快路径**：`ensure_thread_skill_projection(storage, thread_id, allowed_skills)` 在 `allowed_skills is None` 且线程 scope 目录不存在时返回 `None`（继续用共享视图）；一旦线程有了 scope，后续无限制 run 也会把同一线程根重建为"全量启用"视图，避免切换 agent 后线程被意外限制（`612-649`，锚 `362,380`）。
- **谁负责修**：`ensure_skill_projections` 修 stale 的 public/user scope；`ensure_thread_skill_projection` 修线程 scope；启动期 `ensure_public_skill_projection` **只**处理全局 public（否则 readiness 会随租户数增长），失败时清空 public 视图、记 warning 并返回 `False`，等 sandbox acquire 自愈（`683-721,791-815`）。
- **读锁 `skill_projection_read_lock(storage, *, timeout=5.0, check=None)`**：非变更、有界；超时抛 `TimeoutError`；`check` 在每次等待前被调用（导出用它做取消/预算检查）。它取的正是 user projection 那把锁，非 user storage 退化为 `<skills_root>/custom` scope（`818-865`）。导出在它下面捕获与复核，且导出方**不重建**投影（`export.py:374`，锚 `tests/test_skill_export.py:285`）。
- **失败即清空**：任何 scope 重建异常都会先清空该 scope 的类别根 + 清单再抛（选择"看到少"而不是"看到旧/越权"）（`497-514,517-546,563-609,786-788`，锚 `tests/test_skill_projection.py:534,551`）。
- **写隔离靠拷贝**：投影一律 `shutil.copy2`，刻意不用 hardlink——LocalSandbox 的 bash 写会透传 inode，`PathMapping.read_only` 只约束 `write_file`/`update_file`，不约束 `execute_command`（`121-127`，锚 `109`）。
- **策略作用域符号链接 fail-closed**：绝对链接、解析到包外的相对链接、断链，都在任何 live 视图被改动之前抛错（`130-153`，锚 `262`）。
- 受管的 integrations 包是**全局安装**的，但其投影类别按用户分离（启用态是 per-user 的）（`517-546`，锚 `220`）。

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

## `allowed-tools` 修正 🆕

**2.1 修复**：`allowed-tools` 只对 slash-activated 或实际 loaded 的 lead-agent skill 生效。Passive enabled skill 不再意外限制全局 toolset。`task` 需显式声明才能委派 subagent。

**分词加固（#4984）**：可移植标量形式按状态机分词——引号内、转义字符、括号模式内的空格不切分；未闭合引号/未闭合括号/多余右括号直接报错（fail-closed），而非静默截断模式。

**策略装配边界（`skills/tool_policy.py`，补深）**：

- `ALWAYS_AVAILABLE_BUILTIN_TOOL_NAMES = {describe_skill, read_file, review_skill_package, tool_search}`：即使 active skill 声明了 `allowed-tools` 也保留这 4 个——它们是框架级的文件/审查/发现工作流，不扩展被激活 skill 的业务工具授权（`tool_policy.py:13-25`）。
- `allowed_tool_names_for_skills(skills) -> set | None`：**没有任何** loaded skill 声明 `allowed-tools` → 返回 `None`（legacy 全放行）；一旦有任一 skill 显式声明，未声明该字段的 skill **贡献 0 个工具**（`None` 与空元组都算"显式声明"，空列表另记一条 info 日志）——防止旧 skill 无意中取消别的 skill 的限制（`28-51`）。
- `filter_tools_by_skill_allowed_tools(tools, skills, *, always_allowed_tool_names=...)` 先取上面的并集，再并入 always-allowed 集合，最后按 `tool.name` 过滤（`54-65`）。`task` / `list_background_tasks` / `cancel_background_task` **不在** always-allowed 内，必须显式声明；`tool_search` 提升出来的业务工具仍受 active policy 约束（`tool_policy.py:13-17` + `tools/AGENTS.md`）。

## Per-Agent Skill 控制

Custom agent 的 `config.yaml`：
```yaml
skills: ["deep-research"]   # null=全部, []=禁用, ["a"]=指定
```

**Sandbox 文件系统层强制（#5077）**：lead custom Agent 的显式 `skills` 列表（含 `[]`）现在落到 sandbox projection——线程级视图 `threads/{thread_id}/skills_view/{public,custom,legacy,integrations}` 只物化「已启用 ∩ 白名单」的 skill，`skills=None` 保持共享零拷贝挂载直到该线程用过显式策略。策略重建先撤销全部旧类别再挂新策略，拒绝绝对符号链接和解析到包外的相对符号链接；视图内篡改通过源/视图元数据树摘要校验在下一次 acquire 时修复。subagent 的 `skills` 字段仍只限定发现与激活（并发委派的 subagent 共享 lead 线程 sandbox）。

## Skill 写入门与 `skill_manage`（skills 侧不变量）

`skill_manage` 工具面（参数、action 枚举、加载条件）见 [builtin-tools/C-agent-lifecycle.md](../builtin-tools/C-agent-lifecycle.md#skill_manage)；这里只钉 skills 子系统这侧的不变量与已发现的文档偏差。

**写入门顺序是固定的三段**（`tools/skill_manage_tool.py:89-108,142-259`）：

1. **静态 SkillScan candidate 扫描**（`enforce_static_scan`，命中 CRITICAL 即 `ValueError`）——发生在任何 LLM 调用**之前**（锚 `backend/tests/test_skill_manage_tool.py:255,296`）。
2. **LLM 审核** `scan_skill_content`：三态 `allow|warn|block`；`block` 直接拒绝；`executable=True` 的内容必须 `allow`（`skill_manage_tool.py:66-74`）。in-graph 调用固定 `attach_tracing=False`（图根已挂载 tracing）（`69`，锚 `backend/tests/test_skill_manage_tool.py:391`）。
3. 原子写盘 + 历史 + `refresh_user_skills_system_prompt_cache_async(user_id)`（`142-259`）。

**candidate 的构成决定"能否绕过"**：`create/edit/patch` 扫的是"临时目录 + 覆盖后的 SKILL.md"；`write_file` 扫的是"**整棵现有 custom skill 树** + 目标文件"，所以新增脚本同样会触发既有文件里的 CRITICAL 规则（`skill_manage_tool.py:89-101`）。扫描在 worker 线程执行（`_to_thread`/`asyncio.to_thread`）。

**其他契约**：

- `patch`：`find` 不存在（0 次命中）→ 报错；给了 `expected_count` 时实际次数必须精确相等，替换次数取 `expected_count`，未给则只替换 **1** 次（`179-203`，锚 `tests/test_skill_manage_tool.py:89`）。
- 锁粒度 `(user_id, skill_name)`，存在 `WeakValueDictionary` 里——跨用户不互相阻塞（`33-43`）。
- `write_file` / `remove_file` 的 `path` 必须通过 `ensure_safe_support_path`（只允许 `references/templates/scripts/assets` 顶层目录，锚 `tests/test_skill_manage_tool.py:183`）。
- `write_file` 的目标路径含 `scripts/` 才算 executable → 才要求 LLM 决策为 allow（`228-230`）。
- 历史记录字段固定：`action / author="agent" / thread_id / file_path / prev_content / new_content / scanner`；`delete` 与 `remove_file` 记 `scanner={"decision": "allow", "reason": "Deletion requested."}`（`54-63,205-252`）。
- 最后的分支把"未知 action"和"目标是 public/legacy 只读"统一成 `ValueError`（`254-259`）。

**本文档早前一处措辞补充**：`skill_manage` 各变更分支调用的是 **per-user** 版本 `refresh_user_skills_system_prompt_cache_async(user_id)`（`tools/skill_manage_tool.py:16,158,176,202,218,238,251`；实现在 `agents/lead_agent/prompt.py:264`），而非无参的全局 `refresh_skills_system_prompt_cache_async()`（`prompt.py:238`）。两者都存在，别写混。

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
> **See also:** [Security: Input Sanitization & Secrets Redaction](../../operations/security/03-guardrail.md) · [Middleware: SkillActivationMiddleware](../../internals/middleware/03-catalog.md) · [Testing Skills](../../testing/05-testing-skills-and-workflows.md)
