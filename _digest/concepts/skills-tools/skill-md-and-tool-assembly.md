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
| `allowed-tools` | 工具白名单（可选） |
| `required-secrets` | 🆕 字符串或 `{name, optional}` 列表——skill 需要的请求级密钥 |
| `secrets-autonomous` | 🆕 `true`（默认）= agent 自主加载时绑定密钥；`false` = 仅显式 `/skill-name` 激活时绑定 |

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

## `/skill-name` 斜杠激活

文件：`deerflow/agents/middlewares/skill_activation_middleware.py`

`SkillActivationMiddleware` 检测用户消息中的 `/skill-name task` 语法：

1. `parse_slash_skill_reference()` 解析严格格式
2. 拒绝保留命令（`/new`、`/help`、`/bootstrap`、`/status`、`/models`、`/memory`、`/goal`）
3. 解析到的 skill 必须已启用且在 agent 白名单内
4. 注入 `SKILL.md` body 为隐藏 HumanMessage（`hide_from_ui: True`），插入到触发消息之前
5. 记录审计事件 `middleware:skill_activation`（name、category、path、content_hash——不含 body）

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
LocalSkillStorage.load_skills()
    │  (在 asyncio.to_thread 中运行，避免阻塞 event loop)
    │  递归扫描 skills/{public,custom} 寻找 SKILL.md
    │
    ├── 解析 YAML frontmatter（包含 required-secrets）
    ├── 读取 extensions_config.json 的启用状态
    └── 返回 List[Skill]
```

**热加载**：`get_or_new_skill_storage()` 检测 `extensions_config.json` 变化后重建 storage。

## ⚠️ Breaking Change：SKILL.md 即 Package Boundary

**2.1**：含有 `SKILL.md` 的目录现在是 runtime package boundary。该目录内的嵌套 `SKILL.md` 文件被视为 support data，不再注册为独立 skill。不寻常的自定义布局需将独立可加载 skill 移到不含自身 `SKILL.md` 的 namespace 目录下。

## ⚠️ Breaking Change：`/mnt/skills` 收归 managed enabled-only projection 🆕（#4178）

**2.1**：`/mnt/skills` 不再是 skills 目录的直接透传挂载，而是 `skills/projection.py` 物化的 **enabled-only 只读投影**——只有启用的 skill 才出现在 sandbox 视图里（public / custom / legacy / integrations 四个 scope，各 scope 独立 fail-closed：单个 scope 重建失败只清空该视图并自愈，不中止 Gateway 启动）。影响：

- **operator 配置的 mounts 指向 `/mnt/skills`（或其子路径）会被跳过并告警**（E2B：`Skipping e2b mount that conflicts with managed skills projection`）——托管投影与操作者挂载不再叠加
- 每个用户/线程的投影按全局 enable 状态重建；用户 projection **重读全局 enable 状态，跨 worker 生效**（启用/禁用即时反映到下一次 sandbox acquire）
- 关闭 skill 后 sandbox 文件系统视图同步消失，而不是"文件还在、只是不激活"

## 本地 skill 归档安装 🆕（#5039）

`POST /api/skills/install` 支持上传 `.skill` ZIP 归档安装到 `custom/`。Gateway 侧用有界 multipart 解析器流式落盘（`_BoundedSkillArchiveMultiPartParser` + 双重字节上限：单文件 100 MiB，含 multipart 开销的请求级上限），超限在 Starlette 写盘前中止以便及时关闭 spool 文件；nginx/helm 相应放宽了 body size（`test_nginx_langgraph_body_size.py` + chart 脚本 `scripts/check_chart_skill_upload_size.sh` pin）。归档内容仍过 SkillScan 静态扫描。

## 自定义 skill 包导出 🆕（#5332）

`skills/export.py`（harness）+ `app/gateway/skill_export.py` + `routers/skills.py`：把自定义 skill 打包成可分发的 ZIP，**全程只读快照**——导出不会激活或执行 skill。硬边界：4096 entries / 单文件 64 MiB / 总量与 ZIP 各 100 MiB / 路径 1024 字节 / 深度 32 / 60s deadline，持 projection 读锁；拒绝敏感文件（`.env`、`id_rsa`、`credentials.json` 等）、Windows 保留名、非 `[a-z0-9-]` 名称。**revision-bound preview**：请求携带 skill 内容的 SHA-256 revision，预览与下载都绑定该 revision——skill 在导出过程中被修改则整个导出失败，不会产出半新半旧的包。

## SKILL.md 空描述在写入门被拒 🆕（#4867）

`_validate_skill_frontmatter` 之前只在 description **truthy** 时应用规则，空白描述能过写入门但被 loader 拒绝——PUT 编辑端点先写盘再 404（原本可用的 skill 直接消失且无回滚），`.skill` 安装路径与 `skill_manage` 工具同样报告一个永远加载不出来的 skill。现在空白/纯空白 description 在写入门被拒（400 "Description cannot be empty"），rollback 恢复含空描述历史条目同样被拒且**磁盘保持原样**。

## `allowed-tools` portable 模式安全 token 化 🆕（#4984）

Portable Agent Skills 的标量语法是空白分隔、允许带括号命令模式（如 `Bash(tvly *)`）。解析器（`skills/parser.py::parse_allowed_tools`）现在把含空格的括号模式**保持为单个字面条目**，不再 `raw.split()` 碎片化；YAML 列表形式仍逐字保留大小写敏感的 MCP/运行时工具名。DeerFlow 当前策略只匹配**精确工具名**：`Bash(...)` 条目保持字面且不生效（不会宽化为 unrestricted shell），直到有显式的命令模式授权模型。

## SkillScan 静态分析 🆕

`packages/harness/deerflow/skills/skillscan/` — 加载时对 skill package 做确定性静态扫描：

- **Orchestrator** 协调多个 analyzer 并发分析
- **Network sink 检测**：识别 `requests`/`httpx` HTTP methods、`urllib` 等外泄路径
- **Environment access 检测**：识别 `os.environ` 读取（含 `from os import environ` 模式）
- **Subprocess shell 检测**：`os.system`/`os.popen`/`subprocess` 调用 `shell=True` 视为外泄路径；`shell=` 非字面量（变量/表达式/`**kwargs`）**fail-closed** 视为 shell=True（`_call_shell_may_be_true`，同步 #4 加固）
- **分级阻断**：`CRITICAL` 阻断安装，`WARNING` 放行但传给 LLM 扫描器
- **纯同步**：`scan_archive_preflight()` / `scan_skill_dir()` 可 offload 出 event loop
- `skill_scan.enabled` kill switch

## Skill Review 质量门禁 🆕

`packages/harness/deerflow/skills/review/` + `skills/public/skill-reviewer/`：
- **CLI**：`python -m deerflow.skills.review.cli --fail-on error` 用于 CI
- **内置 tool**：`review_skill_package` — 模型可见的是 compact JSON（tag 中性化），完整 payload 在 `ToolMessage.artifact`
- **CI 集成**：`.github/workflows/skill-review-ci.yml`

## Per-User Skill 隔离 🆕

Custom skill 按用户隔离存储，`SkillStorage` 按 `(app_config, user_id)` 缓存。Sandbox 挂载用户级 skill 目录。

## `allowed-tools` 修正 🆕

**2.1 修复**：`allowed-tools` 只对 slash-activated 或实际 loaded 的 lead-agent skill 生效。Passive enabled skill 不再意外限制全局 toolset。`task` 需显式声明才能委派 subagent。

## Per-Agent Skill 控制

Custom agent 的 `config.yaml`：
```yaml
skills: ["deep-research"]   # null=全部, []=禁用, ["a"]=指定
```

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

| 工具 | 条件 | 实现 |
|------|------|------|
| `present_files` | 始终 | `tools/builtins/present_files.py` |
| `ask_clarification` | 始终（non_interactive 时移除） | `tools/builtins/ask_clarification.py` |
| `view_image` | vision 模型 | `tools/builtins/view_image.py` |
| `setup_agent` | bootstrap 模式 | `tools/builtins/setup_agent.py` |
| `update_agent` | custom agent 模式 | `tools/builtins/update_agent.py` |
| `tool_search` | `tool_search.enabled` | `tools/builtins/tool_search.py` |
| `describe_skill` | `skills.deferred_discovery` | `skills/describe.py` |
| `task` | `subagent_enabled` | subagent 系统 |
| `invoke_acp_agent` | ACP 配置了 agent | ACP 系统 |

## 故障排查

| 症状 | 可能原因 | 检查 |
|------|---------|------|
| Skill 不出现 | 未启用 | `extensions_config.json` → `skills.{name}.enabled: true` |
| Skill 不出现 | Agent 白名单 | custom agent `config.yaml` → `skills:` 包含该 skill |
| Skill 不出现（deferred 模式） | 索引未构建 | `skills.deferred_discovery: true` + skill 目录存在 `SKILL.md` |
| 修改后未生效 | 热加载未触发 | 重启 Gateway 或等 mtime 检测（`get_or_new_skill_storage()`） |
| Secret 未注入 | 声明缺失 | `SKILL.md` frontmatter → `required-secrets: [NAME]` |
| Secret 未注入 | 调用方未传 | run request `context.secrets` 包含该 key |
| Secret 未注入（自主加载） | 被阻止 | `secrets-autonomous: false` 阻止了 in-context 绑定，用 `/skill-name` 显式激活 |
| /skill-name 不生效 | 语法错误 | 严格格式：`/skill-name task description`（斜杠+名称+空格+task+空格+描述） |
| /skill-name 不生效 | 保留命令 | `/new`、`/help` 等保留命令被拒绝 |

---
> **See also:** [Security: Input Sanitization & Secrets Redaction](../../operations/security/03-guardrail.md) · [Middleware: SkillActivationMiddleware](../../internals/middleware/03-catalog.md) · [Testing Skills](../../testing/05-testing-skills-and-workflows.md)
