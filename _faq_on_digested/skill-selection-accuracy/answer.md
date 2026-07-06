## DeerFlow 现状：纯 LLM 自主选择，零辅助

### 机制链路

```
skills/{public,custom}/**/SKILL.md
        │
        ▼
LocalSkillStorage.load_skills(enabled_only=True)
  → 递归扫描磁盘，解析 YAML frontmatter（name, description, license, allowed-tools）
  → 见 deerflow/skills/storage/local_skill_storage.py:63-74
        │
        ▼
get_skills_prompt_section()
  → 所有 enabled skill 的 (name, description, category, file_path) 
  → 不经任何过滤、排序、或相关性计算
  → 见 deerflow/agents/lead_agent/prompt.py:626-656
        │
        ▼
系统 prompt 的 <available_skills> 块
  → XML 格式注入：
    <skill>
        <name>my-skill</name>
        <description>This skill helps with X, Y, Z...</description>
        <location>/mnt/skills/public/my-skill/SKILL.md</location>
    </skill>
  → 见 deerflow/agents/lead_agent/prompt.py:594-623
        │
        ▼
LLM 阅读理解所有 skill 描述 → 自主决定调用 read_file 加载哪个
```

### 问题的根源

DeerFlow 的 skill 选取依赖**一个步骤**：LLM 在系统 prompt 中读所有 skill 的 name+description，然后自己判断该用哪个。

**没有任何辅助机制：**

| 缺失的能力 | 后果 |
|-----------|------|
| 无 relevance 排序 | LLM 看到的是等权列表，50 个 skill 全部平铺 |
| 无 keyword/trigger 匹配 | 不能根据用户 query 里的关键词预筛 |
| 无 embedding 语义搜索 | 不能做向量相似度排序 |
| 无 context budget 控制 | skill 再多也全部塞进 prompt，挤占 context window |
| 无 selection 反馈循环 | 选错了没有纠正机制 |

**当 skill 数量上去后，三个问题叠加：**

1. **Context 稀释** — 50 个 skill × 平均 100 tokens 描述 = ~5000 tokens。这些 tokens 挤占了模型真正用于推理的空间。LLM 的注意力被分散到不相关的 skill 上。
2. **描述歧义** — 多个 skill 描述相似时（比如 `python-testing` 和 `pytest-mocking`），LLM 容易选错。
3. **长尾遗忘** — 列表末尾的 skill 被选中的概率显著低于列表开头的 skill（位置偏差）。

### 唯一存在的筛选机制：agent-level skill whitelist

`get_skills_prompt_section()` 接受一个 `available_skills: set[str]` 参数：

```python
# prompt.py:648
if available_skills is not None and not any(
    skill.name in available_skills for skill in skills
):
    return ""
```

这个参数来自 `AgentConfig.skills`——每个 custom agent 可以配置 `skills: ["foo", "bar"]` 来只暴露部分 skill。但这需要**人工配置**，不是自动选择。而且 default agent 的 `skills` 是 `None`（= 所有 skill 可见）。

### tool_search 不适用于 skill

`deerflow/tools/builtins/tool_search.py` 的 `tool_search` 工具只对 **MCP deferred tools** 生效（通过 `DeferredToolRegistry` + `DeferredToolFilterMiddleware`）。Skills 不经过这个通道——skill 发现是通过 `read_file` 加载 SKILL.md，完全由 LLM 自主决定。

---

## Codex 的做法：3 层渐进 + context budget 硬限制

Codex（OpenAI 的 CLI agent）和 DeerFlow 用同一套 `SKILL.md` 标准 (`agentskills.io`)，但 skill 选取机制有本质差异。

### 三层渐进加载

| 层 | 加载内容 | 时机 | Token 消耗 |
|----|---------|------|-----------|
| L1 元数据 | name + description | Session 开始时全部加载 | ~100 tokens/skill |
| L2 指令 | SKILL.md 完整正文 | 当 skill 被触发时 | 推荐 <5k tokens |
| L3 资源 | 脚本、assets、引用文件 | 执行过程中按需加载 | 可变 |

### Context Budget 硬上限

Codex 的 skill 列表 **上限约为模型 context window 的 2%**（或 8000 字符）。超出预算时：

1. 先缩短每个 skill 的 description（截断）
2. 还不够 → 省略部分 skill（对用户显示警告）

这保证 skill 列表不会无限制膨胀。

### 两种触发方式

| 方式 | 机制 |
|------|------|
| **显式** | 用户输入 `$skill-name` 或 `/skills` 手动选择 |
| **隐式** | Codex 自动将用户任务描述与 skill description 做语义匹配 |

隐式匹配的核心是 `codex-rs/core/src/skills/render.rs` 中的 prompt 指令，告诉模型如何根据 description 选择 skill。关键设计：**依赖 description 的高信号密度**——描述要简短、包含明确的触发词、前置核心场景。

### `allow_implicit_invocation` 开关

每个 skill 可以配置是否允许被自动匹配调用。对于容易误触发的 skill（比如 `git-force-push`），可以设为 `false`，只能显式调用。

---

## 对比

| 维度 | DeerFlow | Codex |
|------|----------|-------|
| **选择方式** | LLM 全自主 | 语义匹配 + 显式调用 |
| **Context 控制** | 无上限，全量注入 | ~2% budget，截断/省略 |
| **加载策略** | 全量 + LLM 决定 read_file | 3 层渐进（metadata → body → resources） |
| **防误触** | 无 | `allow_implicit_invocation` 开关 |
| **筛选辅助** | agent whitelist（需人工配置） | 描述截断 + budget 优先 |
| **选择反馈** | 无 | 无（一样没有） |

---

## 改进方向（基于 DeerFlow 现有架构）

### 短期可做（不改变架构）

**1. 加 context budget 硬上限**

在 `get_skills_prompt_section()` 中，计算 skill 列表的 token 数，超出上限时截断：

```python
# 类似 Codex 的 2% 策略
MAX_SKILL_TOKENS = 2000  # 或 config.max_injection_tokens 复用

# 先按某种优先级排序（比如按用户使用频率）
# 再截断到 token 上限
```

这利用现有的 `max_injection_tokens` 概念（memory 已经在用）。

**2. 强化 skill description 写作规范**

DeerFlow 的 skill description 完全由 skill 作者控制。在 digest 或文档中给出规范：
- 前 50 字符必须包含最核心的触发词
- 使用动作词（"Use this when..."、"For X tasks..."）
- 不超过 200 字符（多余内容放在 SKILL.md body 中）

**3. 给每个 skill 加 `trigger_keywords` frontmatter**

扩展 `Skill` dataclass（`deerflow/skills/types.py:19-31`）和 parser（`deerflow/skills/parser.py:35-110`）：

```python
@dataclass
class Skill:
    name: str
    description: str
    trigger_keywords: list[str] | None = None  # 新增
    ...
```

然后在 `get_skills_prompt_section()` 中，用用户 query 的关键词与 `trigger_keywords` 做交集筛选，减少注入 prompt 的 skill 数量。

### 中期可做（加一个新机制）

**4. 做 skill search tool（类似 tool_search 但给 skill 用）**

参考 `deerflow/tools/builtins/tool_search.py` 的 `DeferredToolRegistry` + `tool_search` 模式：

- 注册一个 `skill_search` tool
- Skill 不在系统 prompt 中全量列出，只列出 high-priority 的
- Agent 需要时调用 `skill_search("deploy k8s")` 来搜索
- 后端做 keyword/regex 匹配（或加 embedding）

这利用现有的 `DeferredToolFilterMiddleware` 模式，不需要引入向量数据库。

### 长期可做（需外部依赖）

**5. Embedding 语义匹配**

- 启动时对所有 skill description 做 embedding
- 用户请求来时，用 query embedding 做 cosine similarity 排序
- 只注入 top-K 个 skill 到 prompt
- 或嵌入 `skill_search` tool 中作为后端

这个需要引入 embedding model + 向量存储，增加了部署复杂度。

---

## 结论

DeerFlow 当前的 skill 选取精度问题**不是 bug，是架构选择**。它把所有 skill 全部平铺给 LLM，完全信任 LLM 的判断力。这在 5-10 个 skill 时工作良好，到 50+ 时开始系统性退化。

Codex 的做法（budget 硬上限 + 渐进加载 + 显式/隐式双模式）是目前最成熟的参考。但 DeerFlow 已经有实现类似机制的基础设施——`tool_search` 的 deferred registry 模式可以直接套用到 skill 上。

最务实的改进路径：**加 context budget 上限 + 强化 description 写作规范 + 可选 keyword 预设筛选**——这三项都不用改架构，都利用现有基础设施。

---

## 相关 digest 笔记

- `_digest/harness-hooks/04-agent-middleware-hooks.md` — middleware 链中的 `DeferredToolFilterMiddleware` 如何做 deferred tool 的 schema stripping
- `_digest/harness-hooks/06-mcp-interceptors.md` — MCP tools 通过 `tool_search` 的延迟发现机制
- `_digest/middleware/03-catalog.md` — `DeferredToolFilterMiddleware` 的两阶段工作（wrap_model_call 隐藏 schema + wrap_tool_call 拒绝未 promote 的 tool）
- `_digest/harness-hooks/08-agent-self-modification.md` — `SkillEvolutionConfig` 控制 agent 能否创建/修改 skill

Sources:
- [Agent Skills – Codex (OpenAI Developers)](https://developers.openai.com/codex/skills)
- [OpenAI are quietly adopting skills - Simon Willison](https://simonwillison.net/2025/Dec/12/openai-skills/)
- [Skills在Claude Code, Codex, OpenClaw深度对比](http://mp.weixin.qq.com/s?__biz=MzUyNjY5ODI2Nw==&mid=2247483841&idx=1&sn=9bb8171fc1220c9d0de920ccedbf1fd9)
