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
    │  三种查询模式：
    │  - select:name1,name2  → 精确匹配，无结果上限
    │  - +keyword rest       → name 必须含 keyword，其余项 regex 排序（上限 5）
    │  - free text           → regex 搜 name+description（上限 5）
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
