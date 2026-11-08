---
title: "Guardrail 与安全防御 — 全链路 Defense-in-Depth"
description: 'DeerFlow 2.2 的安全模型从 guardrail 拦截升级为全链路 defense-in-depth：input sanitization → output sanitization → static exfil 检测 → framework tag 阻断 → 可插拔风险门（Allowlist / TypeSafe Jev / OpenAI Decisions）fail-closed → secrets redaction。'
topics: [security, guardrail, prompt-injection, defense-in-depth, CVE, sanitization, typesafe, openai-decisions]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Guardrail 与安全防御 — 全链路 Defense-in-Depth

> **2.1.0 里程碑 | 安全模型质变**：4 CVE 修复 + 全链路 HTML 转义 + SkillScan 静态外泄检测 + `skill_evolution.security_fail_closed`（skill 写入侧的 moderation 降级开关）+ forged framework tag 阻断。从"guardrail 拦截危险 tool"升级为"任意 untrusted content 进入 prompt 前都被中性化"。
>
> **🆕 2.2.0 增量 | guardrail 从"名单"变成"风险门"**：新增两个**模型判定的执行前风险门** —— `TypeSafeGuardrailProvider`（Jev `noul` 问题）与 `OpenAIDecisionsGuardrailProvider`（OpenAI `/v1/decisions` `predicate` 问题，issue #7005）。两者共用一份传输层 `deerflow.typesafe`，共用同一套 gate 语义（严格 JSON 预检、字符数边界、阈值方向、缓存、fail-closed），**只在线上协议上不同**。同时 Layer 2 的工具豁免从"按名字豁免"改为"按对象身份豁免"。

## 🆕 2.2.0 三道工具级风险门（同一协议，三种实现）

v2.1 只有 `AllowlistProvider`——名字在白名单里就放行，安全属性完全来自运维维护的那张表。v2.2 增加两个**在放行前再问一次模型**的门。三者都实现同一个 `GuardrailProvider` 协议，因此在 `guardrails.provider.use` 位置上可互换；middleware、fail-closed 语义、审计落点全部不变。

| | `AllowlistProvider` | `TypeSafeGuardrailProvider` | `OpenAIDecisionsGuardrailProvider` |
|---|---|---|---|
| 类路径 | `deerflow.guardrails.builtin:AllowlistProvider` | `deerflow.guardrails.typesafe:TypeSafeGuardrailProvider` | `deerflow.guardrails.openai_decisions:OpenAIDecisionsGuardrailProvider` |
| 判定依据 | `allowed_tools` / `denied_tools` 名单 | 一处 `noul` 问题 `risky_tool_call` 的概率 ≥ `threshold` | 一处 `predicate` 问题，同一问题换一种问法 |
| 需要网络 | 否 | 是（`POST /v1/systemone`） | 是（`POST /v1/decisions`） |
| 默认 endpoint | — | `https://api.typesafe.ai`（`typesafe/connection.py:43`） | `https://api.openai.com`（`openai_decisions/client.py:56`） |
| 默认 key 环境变量 | — | `TYPESAFE_API_KEY`（`typesafe/connection.py:44`） | `OPENAI_API_KEY`（`openai_decisions/client.py:57`） |
| 默认 model | — | `jev-latest`（`typesafe/connection.py:45`） | **无默认，必须显式配** |
| `policy_id` | `allowlist` | `deerflow.guardrails.typesafe` v`1.1.0`（`typesafe.py:136-137`） | `deerflow.guardrails.openai_decisions` 独立命名（`openai_decisions.py:63`） |
| 判定失败 | 名单 miss = deny | 见下"错误即拒绝" | 同左，**refusal 也算判定失败** |

### 共用的 gate 语义（`guardrails/typesafe.py`，464 行）

`OpenAIDecisionsGuardrailProvider` 是 `TypeSafeGuardrailProvider` 的**子类**，只覆写 3 个 seam（`_resolve_connection`、`_build_client`、`_state`）与一组类属性（`name`/`policy_id`/`policy_version`/`code_prefix`/`provider_name`/`error_class`）。`openai_decisions.py:7-9` 解释了为什么不复制：

> "Everything that makes this a *gate* is inherited … Two copies of a security boundary drift apart, and the copy the primary suite does not exercise is the one that goes quiet."

留在基类、两个门都一样的五件东西：

1. **strict-JSON 预检**（`typesafe.py` 模块 docstring 第一条）：`state` 用 `json.dumps` 且**不带 `default=`、`allow_nan=False`、只允许字符串 key**。序列化不了的参数（bytes、非字符串 key、`NaN`/`Infinity`、UTF-8 编不出来的 lone surrogate）、以及超过 `max_state_chars`（默认 4000，**字符数**而非字节数）的参数文本，一律**本地拒绝**（`typesafe.state_unusable`，不发请求）——**不截断后发出去**，任何判定都不基于前缀。这是"模型看见的内容 = 判定覆盖的内容"的唯一保证；截断后发的话，攻击者只要把危险参数推到 4000 字符之后就绕过了。**本地拒绝是 guardrail 决策**，所以 `fail_closed: false` 也不能把它变成"未评估就放行"。
   为什么是字符数而不是字节数：一个 CJK 字符占三字节，换成字节上限会直接把这条回退边界移走（`backend/docs/GUARDRAILS.md` 原文理由）。代价是真的——长 heredoc、内联脚本、大 `write_file` 正文会撞上限，这些拒绝会记进部署的误报率；调高 `max_state_chars` 就是让更多数据离开进程。
2. **阈值方向**：概率 **≥** `threshold` 才拒（`threshold` 默认 0.5，必须落在 [0,1]，非有限值直接拒）。
3. **错误即拒绝**：`TypeSafeGuardrailError`（`typesafe.py:83`）承载共享的四类原因 `deadline` / `transport` / `http_status` / `invalid_response`；**本门自己那个问题的答案坏了也归 `invalid_response`**（envelope 可用、这个答案不可用、gate 没有判定）。middleware 把该异常映射到 `guardrails.fail_closed`，**绝不在这里降级成 allow**。错误消息只报状态码或出错字段的**类型**——不回显响应体、HTTP reason phrase 或工具参数，因为畸形/敌意响应可以控制或回显它们。
4. **缓存**：`cache_size` 默认 256、`cache_ttl_seconds` 默认 300；任一 ≤ 0 即禁用缓存（`typesafe.py:381`）。
5. **`allowed_tools` 是硬权限表，不是评估豁免**（模块 docstring）：表外工具**本地拒绝**（`typesafe.tool_not_allowed`，不构建 state、不发请求、不写缓存），表内工具**仍须通过风险门**。且 `allowed_tools: []`（空列表）表示"任何工具都不许跑"，`null` 表示"没有配置这张表"——用真值判断会把前者折叠成后者而**失败开放**，`_tool_names()` 因此必须区分 `None` 与 `[]`。**它先于 `tools` 检查**：表外工具即使在探测范围外也照样被拒——否则"不在探测范围"会顺带赠送一个 allow。

### `tools` 是探测范围，不是安全边界

`tools: ["bash"]` 只决定**哪些工具的调用会被送去评估**，`config.example.yaml:3301` 把这一点写成警告：它是**冒烟测试范围，不是生产建议**——操作可以挪到一个未被探测的工具、一个 MCP 工具、或一个 subagent 上，风险门就完全看不到它。正确做法是**把每个能完成危险工作的工具都放进** `tools`，而不是把范围收窄到一两个。

风险门**不做脱敏**（`backend/docs/GUARDRAILS.md` 明写）：送出去的是工具名 + 完整参数 JSON（`state.tool_call`），参数里可能带用户内容、文件路径、shell 命令甚至密钥，`pii_redaction_middleware` 在这条路径上**不生效**。启用前应先把这条出网通道与数据保护负责人对齐。

### 失败面（启用 TypeSafe 后）

TypeSafe 不可达时，**只有"被探测且缓存未命中"的调用**受影响（`fail_closed: true` 下被阻断）；未探测的工具和缓存命中照常工作。每一次失败都抛异常，**从不静默降级成 allow**。

### 时间预算是预算，不是保证

共享 client 的 async 路径用 `asyncio.timeout` 真正取消在途请求；**sync 路径无法抢占阻塞调用**，因此它在拿到响应头之后、读 body 周围、解析之后再各查一次 deadline，**迟到的结果直接丢弃**。`MAX_RESPONSE_BYTES = 64 * 1024`（`typesafe/client.py:76`）约束响应体上限，body **永不被解码成无界对象**。

另两条纪律（同一 docstring）：**client 的生命期恰好一次评估**——`transport_factory` 是工厂不是实例，client 随自身关闭；**凭据永不进日志**。

### OpenAI Decisions 的三处结构性差异

`openai_decisions/client.py` 的模块 docstring 明确"这个模块拥有线协议，别的什么都不拥有"（阈值、评分标准、缓存、失败方向留在各 adapter）：

| 差异 | Jev | OpenAI Decisions |
|------|-----|------------------|
| `input` | `state` 映射（形状由消费者自定） | **文本**——就是 state digest 已经标识的那份 canonical JSON，字节相同，不是第二次序列化 |
| 问题类型 | `noul`，带 `criteria.true` / `criteria.false` | `predicate`，**没有 criteria 字段**，评分标准折进 `instructions` |
| 拒答 | HTTP 失败 | `{"type": "refusal"}` 是**答案**，转成 question 级 `QuestionError` → `invalid_response` → gate 拒绝 |

第二条值得展开：`predicate` 若把 criteria 丢一半，判定边界就移动了，而 adapter 还在 policy identity 里报告同一份 `criteria`——所以宁可用 `predicate_instructions()` 把两条 criteria 拼进指令文本，也不静默丢。

### 连接配置的解析优先级

`resolve_connection()`（`typesafe/connection.py:111`）按文档化优先级解析：**本 provider 自己的 `guardrails.provider.config`** → **顶层 `typesafe:` 块** → **内置默认值**。于是老部署的 `guardrails.provider.config` 原样可用，而有多个 TypeSafe 消费者的部署可以只维护一个顶层块。`MODE_OFF = "off"`（`typesafe/connection.py:69`）提供显式关闭档。

内存侧的三个消费者槽位（`memory.prescreen.use`、`memory.signal_classification.use`、`guardrails.provider.use`）共用同一套 backend，但它们**各自保留自己的阈值/缓存/失败方向**——`config/memory_config.py:80` 的 `use` 字段注释即写 `deerflow.agents.memory.prescreen.typesafe:TypeSafeMemoryPrescreen`，换成 `...prescreen.openai_decisions:...` 只换线协议，语义不动。

### `tool_identity`：从"按名字豁免"到"按对象身份豁免"

`authz/adapter.py` 的豁免参数在 2.2.0 从 `infrastructure_tool_names: Iterable[str]` 改成 **`infrastructure_tools: Iterable[object]`**：受信基础设施工具的豁免现在绑定在 **tool 对象身份**上（`request.tool_identity is tool`），而不是 tool 名字上。名字是可伪造表面——一个插件或 MCP server 只要把工具叫成 `read_file`，旧逻辑就把它当成受信基础设施工具。

配套地，`GuardrailRequest` 增加两个字段（`guardrails/middleware.py:104-105`）：

| 新字段 | 来源 | 说明 |
|--------|------|------|
| `tool_provenance` | `tool_provenance_context`（`middleware.py:85` 的**局部 import**）+ `getattr(request, "tool", None)`（`:87`） | 工具来源（首方 / MCP / 插件），让 provider 按来源而非按名字决定策略 |
| `tool_identity` | 同一个 tool 对象 | "这是不是那个受信实例"；**永不序列化、永不转发**给远端（`guardrails/provider.py:33-36` 注释） |

`tool_provenance_context` 走局部 import 是因为 `guardrails/middleware.py` 在很冷的 import 路径上——提到模块级会把一条新的依赖链拽进 middleware 的 import 时间。

### 审计落点（两个门一致）

**不新增审计通道**：拒绝照常经 `GuardrailMiddleware` 进 run journal；**allow 决策仍然不落库**。原因消息里带的字段足够**重放那次阈值比较**——`probability`、`threshold`、`model`、`state_digest`（`typesafe.py:372`）。服务端返回的 `model` 是响应内容，因此只有在符合保守 token 形状时才原样记录，否则记 digest 而不是把任意字符串回显进消息（`recordable_model`）。

## Defense-in-Depth 全景图

```
                         ┌──────────────────────────┐
用户输入 ─────────────────►│ InputSanitization        │ 第 1 道防线
                         │ (XML tag 转义 + 边界标定)  │
                         └──────────┬───────────────┘
                                    │
                         ┌──────────▼───────────────┐
                         │ Forged Framework Tag 阻断 │ 第 2 道防线
                         │ (伪造 </tool_response> 等) │
                         └──────────┬───────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
     ┌────────▼────────┐  ┌────────▼────────┐  ┌─────────▼────────┐
     │ Guardrail       │  │ SandboxAudit    │  │ SkillScan Static │ 第 3-5 道防线
     │ (tool 级授权)    │  │ (bash 参数审计)  │  │ (外泄静态检测)    │
     └────────┬────────┘  └────────┬────────┘  └─────────┬────────┘
              │                    │                      │
              │  🆕 2.2 授权层拆成三道串联的门：
              │     Layer 1 filter_resources  → 候选收窄（只能收窄，不能扩充）
              │     Layer 2 authorize         → 执行裁决
              │     风险门 Allowlist / TypeSafe / OpenAI Decisions → 执行前再问一次模型
              └────────────────────┼──────────────────────┘
                                   │
                         ┌─────────▼────────────┐
                         │ ToolResultSanitization│ 第 6 道防线
                         │ (远程内容 tag 中性化)  │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ Output HTML Escaping  │ 第 7 道防线
                         │ (全量 prompt block 转义)│
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ Secrets Redaction     │ 第 8 道防线
                         │ (trace/checkpoint/API) │
                         └──────────────────────┘
```

## CVE 修复记录（2.1.0）

| CVE | 类型 | 修复 |
|-----|------|------|
| **CVE-2026-33128** | 安全漏洞 | 未公开细节 |
| **CVE-2026-35209** | 安全漏洞 | 未公开细节 |
| **CVE-2026-49476** | 安全漏洞 | 未公开细节 |
| **CVE-2026-49477** | 安全漏洞 | 未公开细节 |

---

## 第 1 道防线：InputSanitizationMiddleware

**位置**：Middleware 链第 1 位（最外层 `wrap_model_call`）

### 做什么

1. **XML tag 转义**：用户输入中的 `<system>`、`<instruction>`、`<role>`、`<memory>` 等标签转为 HTML 实体（`&lt;system&gt;` 等），防止攻击者在用户输入中注入伪造的 framework 指令
2. **边界标定**：用 `--- BEGIN USER INPUT ---` / `--- END USER INPUT ---` 包裹真实用户输入
3. **原始内容保存**：未经洗改的文本保留在 `additional_kwargs[ORIGINAL_USER_CONTENT_KEY]`，供 slash activation 和 regeneration 使用

### 关键实现细节

- `additional_kwargs.original_user_content` 是 **server-owned provenance**：Gateway 在非内部 run 请求时剥离调用者提供的值
- 可信 IM 调用可能携带其在添加 transport/file context 之前捕获的字符串
- 只在 `wrap_model_call` 操作，**不修改 checkpoint**

---

## 第 2 道防线：Forged Framework Tag 阻断

InputSanitizationMiddleware 同时阻断用户输入中的**伪造 framework 标签**：

- `</tool_response>` — 防止攻击者伪造 tool 响应结束标记（影响 MindIE 等 provider）
- 其他 framework 内部标签

这些标签如果进入 prompt 可能让下游 parser 误判内容边界，导致 prompt injection 或更严重的安全后果。

---

## 第 3-4 道防线：Guardrail + SandboxAudit

### GuardrailMiddleware

**位置**：Middleware 链（runtime base 部分）

Tool 级别的可插拔授权系统：

```
LLM 产出 tool_call
  → GuardrailMiddleware.wrap_tool_call(request)
    → 构建 GuardrailRequest(tool_name, tool_input=tool_call["args"])
    → provider.evaluate(gr)
      ├─ decision.allow=True  → handler(request) 继续执行
      └─ decision.allow=False → 返回错误 ToolMessage
```

**GuardrailProvider 协议**（`deerflow/guardrails/provider.py`）：

```python
class GuardrailProvider(Protocol):
    name: str
    def evaluate(self, gr: GuardrailRequest) -> GuardrailDecision: ...
    async def aevaluate(self, gr: GuardrailRequest) -> GuardrailDecision: ...
```

**GuardrailRequest 字段**（🆕 2.1 增强）：

| 字段 | 说明 |
|------|------|
| `tool_name` | LLM 请求的 tool 名 |
| `tool_input` | LLM 产出的原始参数（dict） |
| `agent_id` | `guardrails.passport` 的值 |
| `thread_id` | **2.1 新增**：当前 thread ID |
| `is_subagent` | **2.1 新增**：是否来自 subagent |
| `timestamp` | UTC ISO 时间戳 |
| `user_id` | **2.1 新增**：authenticated user ID |
| `authz_attributes` | **2.1 新增**：authorization principal context |
| 🆕 `tool_provenance` | **2.2 新增**：工具来源（首方 / MCP / 插件），让 provider 按来源而非名字决策 |
| 🆕 `tool_identity` | **2.2 新增**：tool 对象本身，供对象身份豁免；永不序列化/转发 |

**GuardrailDecision**：

| 字段 | 说明 |
|------|------|
| `allow` | `True` = 放行，`False` = 阻断 |
| `reasons` | 结构化原因列表 |
| `policy_id` | 可选策略标识 |
| `metadata` | 任意元数据 |

### Fail-Closed vs Fail-Open

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `fail_closed: true`（默认，`config/guardrails_config.py:22`） | provider 异常 → 合成 deny | 安全优先（生产） |
| `fail_closed: false` | provider 异常 → 放行 | 可用性优先（开发） |

### `security_fail_closed` 归属修正（2.2.0 澄清）

这个选项**不在 `guardrails:` 下**，而在 `skill_evolution:` 下（`config/skill_evolution_config.py:15`），管的是 **agent 写 skill** 时 moderation model 不可用的降级行为：

- `true`（默认）：moderation 不可用 → 拒绝所有 skill 写入
- `false`：非可执行内容带告警放行，**可执行内容始终阻断**

`GuardrailsConfig`（`config/guardrails_config.py`）只有 `enabled`（默认 `false`）/ `fail_closed`（默认 `true`）/ `passport` / `provider` 四个字段——把 `security_fail_closed` 写进 `guardrails:` 不会报错也不会生效。tool 级风险门与 skill 写入审查是两条独立路径，风险门见上文「2.2.0 三道工具级风险门」。

### AllowlistProvider（内置）

零依赖白/黑名单：

```yaml
guardrails:
  enabled: true
  fail_closed: true
  provider:
    use: "deerflow.guardrails.builtin:AllowlistProvider"
    config:
      allowed_tools: ["bash", "ls", "read_file", "write_file"]
      denied_tools: ["str_replace"]
```

### SandboxAuditMiddleware

只审计 bash 命令，硬编码 regex pattern：

**高危模式（block）**：`rm -rf /` 变体、`dd if=`、`mkfs`、`/etc/shadow`、pipe 到 `sh`/`bash`、`LD_PRELOAD`、`/dev/tcp/` 网络、fork bomb 等

**中危模式（warn）**：`chmod 777`、`pip install`、`sudo`、`PATH=` 修改

---

## 第 5 道防线：SkillScan 静态外泄检测 🆕

`packages/harness/deerflow/skills/skillscan/` — 加载时静态分析 skill package，检测潜在的外泄路径：

### 检测能力

| 检测器 | 检测内容 |
|--------|---------|
| **Network Sinks** | `requests.get/post/put/delete`、`httpx.get/post`、`urllib.request.urlopen` — 检测 skill 是否向外部发送数据 |
| **Environment Access** | `os.environ` 读取（包括 `from os import environ` 模式） — 检测 skill 是否读取宿主环境变量 |
| **Dataflow Analysis** | Instance/dataflow 网络客户端追踪 — 检测构造的 HTTP 客户端是否可能外泄数据 |

### 安全扫描流水线

```
Skill archive / directory
  → scan_archive_preflight() / scan_skill_dir()  [纯同步，offload 出 event loop]
    → orchestrator 协调多个 analyzer
      → 每个 analyzer 输出 structured findings (rule_id, severity, file, line, message, remediation)
        → enforce_static_scan() 应用阻断策略
          ├─ CRITICAL → block（拒绝安装）
          └─ WARNING → pass（记录但放行，传给 LLM 扫描器）
```

### Rule ID 体系（前缀即 analyzer）

- `package-*` — Package 结构问题（path-traversal、absolute-path、ads-stream-name、symlink、nested-skill-md）
- `secret-*` — 密钥泄露（private-key、cloud-token、env-assignment）
- `network-*` / `resource-*` — 网络外泄检测（cloud-metadata、cleartext-http、local-http）
- `python-*` — Python 代码分析
- `shell-*` — Shell 脚本分析
- `declaration-*` — Skill 声明分析

---

## 第 6 道防线：ToolResultSanitizationMiddleware 🆕

**位置**：Middleware 链第 3 位（`ToolOutputBudgetMiddleware` 之后）

中性化**远程内容** tool 结果中的 injection 标签：

| 覆盖的 tool | 风险 |
|------------|------|
| `web_fetch` | 抓取的页面可能包含 `<system-reminder>` 等伪造标签 |
| `web_search` | 搜索结果摘要可能包含注入内容 |
| `image_search` | 图片描述可能包含注入内容 |
| `web_capture` | 页面截图附带的文本可能包含注入内容 |

**策略**：名称-based allowlist——只有这些已知的远程内容 tool 被中性化。Local tool（bash/read_file）输出不受影响（信任 sandbox 内的内容）。

**🆕 MCP 结果纳入同一信任边界（#4839）**：MCP 来源的 tool（以 `deerflow_mcp` metadata 标签识别，`deerflow.tools.mcp_metadata.is_mcp_tool`）的结果也经过同一个 `neutralize_untrusted_tags`——MCP server 一律按第三方远程代码对待，结果默认 untrusted，与工具叫什么名字无关。对 MCP 做名字启发式（匹配 fetch/search 等子串）被有意避免：那会同时误伤合法的*本地*工具输出（如 `file_search` 结果）。

---

## 第 7 道防线：全链路 Output HTML Escaping 🆕

**这是 2.1 最大规模的安全加固**——所有进入 prompt 的 untrusted 内容都要 HTML 转义：

| 转义对象 | 进入的 prompt block | 说明 |
|---------|-------------------|------|
| **Memory facts** | `<memory>` → injection prompt | `html.escape(fact.content)` |
| **Memory context summaries** | injection prompt | 防止 fact 内容伪造 memory 标签 |
| **SOUL.md** | `<soul>` prompt block | 自定义 agent 的描述不能伪造 soul 标签 |
| **Subagent 描述** | `<subagent_system>` block | subagent 返回的结果不能注入 |
| **Summarization input** | summarization prompt | 被压缩的对话历史中的标签被转义 |
| **Web capture 结果** | tool 输出 | 页面内容中的注入标签被中性化 |
| **MindIE tool-response** | `</tool_response>` breakout | MindIE provider 的特殊防护 |
| **MEMORY_UPDATE_PROMPT** | conversation block | memory updater 看到的对话历史 |

**原则**：任何不是 DeerFlow 自身生成的、进入 LLM prompt 的文本，都经过 HTML 转义——防止攻击者通过用户输入、网页内容、文件内容等渠道注入伪造的 framework 控制标签。

---

## 第 8 道防线：Secrets Redaction

`secret_context.REDACTED_CONTEXT_KEYS` 确保 secret-bearing context key 从以下路径中剥离：

- **Trace**（LangSmith/Langfuse/Monocle 永远不看到 secret 值）
- **Checkpoint**（secrets 在 `runtime.context`，不在 graph state）
- **持久化 run record**（`runs.kwargs_json` 和 `RunResponse.kwargs` 被 `redact_config_secrets()` 处理）
- **API 响应**
- **Journal/审计日志**（只记录 secret **名称**，不记录值）

### Environment Scrubbing

`env_policy.build_sandbox_env()` 在向 sandbox 进程注入请求级密钥之前剥离宿主机敏感环境变量：

- **通配**：`*KEY*`、`*SECRET*`、`*TOKEN*`、`*PASS*`、`*CREDENTIAL*`、`*DSN*`
- **精确名**：`DATABASE_URL`、`REDIS_URL`、`GH_PAT`、`MYSQL_PWD`、`REDISCLI_AUTH`、`PGPASSFILE`、`PGSERVICEFILE`
- Benign 变量（`PATH`、`HOME`、`LANG`、`VIRTUAL_ENV`）保留

### 🆕 MCP 凭据的 header 值合法性拒绝（#5066）

`mcp/headers.py::illegal_header_value_reason`：解析为 HTTP header 值会失败的凭据（换行、首尾空白、非 ASCII）一律**拒绝执行该 tool call**，与 `on_missing` 设置无关。理由：h11 在换行/首尾空白场景会把**完整值**渲染进异常消息，而 `ToolErrorHandlingMiddleware` 会把 tool 错误复制进 model 可见消息——不拦就会把 secret 落进 prompt、checkpoint 和 trace（httpx 对非 ASCII 的报错较早、只点名字符）。覆盖三条凭据来源：`user_auth`（per-user）、`headers_from_context`（per-request）、OAuth token；拒绝消息不回显凭据值。

### 🆕 Skill toggle 不再持久化 resolved secrets（#5357）

Gateway skill toggle（及其他 runtime 写方）改为 **raw 读-合并-写**（`read_raw_extensions_config` / `set_raw_skill_enabled` + `validate_raw_extensions_config` 后写回），绝不把 `ExtensionsConfig` 模型序列化回盘——模型加载时 `$VAR` 占位符已被解析成明文 secrets，序列化会同时把明文写入 `extensions_config.json` 并永久抹掉 `$VAR` 引用。

---

## 补充防线

### NTFS ADS Smuggling 修复

Skill archive 解压时拒绝 zip 成员名中的冒号（`:`）——防止 NTFS Alternate Data Stream  smuggling 攻击。

### Archive Entry Count Cap

`safe_extract_skill_archive()` 限制 archive 条目数，防止 zip bomb。

### 🆕 Custom Agent 技能 allowlist 的 sandbox 层强制（#5077）

`skills/projection.py`：声明了显式 `skills` allowlist（含 `[]`）的 lead custom agent，其 sandbox 挂载的是 enable 公开/用户可见技能 ∩ allowlist 的**线程级投影**（`users/{user_id}/threads/{thread_id}/skills_view/...`），而非共享零拷贝挂载——被策略排除的技能包在文件系统层就不可见，不只是提示词层面的约束。重建时按 manifest 签名先撤销旧分类再加新策略，投影副本拒绝绝对 symlink 与解析到包外的相对 symlink（防止被允许的包链接回被排除的源）；文件拷贝进视图使 sandbox 内写入无法污染规范 skill inode。subagent 的技能列表仍只约束发现与激活（并发的 subagent 共享 lead 线程 sandbox）。

### 🆕 Artifact 服务安全：主动内容强制附件 + PUT outputs 封锁

- **XML/HTML 附件化（#5353）**：`gateway/routers/artifacts.py` 的 `ACTIVE_CONTENT_MIME_TYPES`（`text/html`、`application/xhtml+xml`、`image/svg+xml`、`text/xml`、`application/xml`、`text/xsl`，外加任意 `+xml` 子类型——XHTML/SVG 都算）与 `.skill` 成员一律以 `Content-Disposition: attachment` 下发，即使浏览器同源打开也无法内联执行脚本，堵住"用户上传 HTML/SVG artifact → 同源 XSS"路径
- **PUT 封锁在 outputs 内（#5321）**：artifact 编辑路由的路径先过 `normalize_outputs_virtual_path`（先折叠 `..` 再做前缀检查），再由 `resolve_outputs_confined_path` 对**解析后的 host 路径**复检 resolved outputs root（与 IM 频道附件投递共享同一条规则）——percent-encoded `..` 或攻击者在 `outputs/` 预埋的 symlink 都不能把编辑重定向到同级 `uploads/` 文件；原子替换保留既有 POSIX 权限处理。该规则与并发安全共用 `reserve_artifact_write`（artifact_write 线程操作预留）

### ReadBeforeWriteMiddleware

`read_before_write.enabled`（默认 on）：`write_file` 和 `str_replace` 必须先 `read_file` 取得内容 hash mark，防止并发编辑冲突和未经检查的覆写。

**🆕 Blocked payload elision（#5329）**：`elide_blocked_payloads`（默认 true）+ `elide_min_chars`（默认 2000 字符，按 Python 字符数计）把被 gate 阻断调用的死参数（`write_file.content`、`str_replace.old_str/new_str`）在 **model-bound request** 中替换为短占位符——blocked 调用从未执行、重读后必然重发，原 payload 只会在后续每轮模型调用里白白占用上下文。**只改请求副本**：state、Receipts、run journal 保留原始参数。

跨 provider 的重写必须经共享辅助 `agents/middlewares/tool_call_args.py::rewrite_messages_tool_call_args`：一条 AIMessage 的参数在**最多四个 surface** 上各有一份——`tool_calls` 结构化列表、`additional_kwargs["tool_calls"]` 原始 provider payload、content blocks（Anthropic `tool_use` 的 `input`+`partial_json`、OpenAI Responses `function_call` 按 `call_id` 匹配）、`tool_call_chunks`——只改一个 surface 会漏（`langchain_openai` 的 Responses 输入构造器甚至优先读 content block 的 `extras.arguments`）。重写命中时还会丢弃 `resp_` response id，使 OpenAI `use_previous_response_id` 回退为全量重放重写后的历史（服务端存储的旧对话无法编辑，续链会把原始参数带回来）。

---

## 局限与已知缺口

| 缺口 | 说明 |
|------|------|
| **ToolResultSanitization 不清洗本地 tool 输出** | 有意为之（信任 sandbox 内容）；MCP 结果已通过 `deerflow_mcp` 标签纳入覆盖（#4839），残余缺口仅剩 extension/社区工具若既非首方网络工具又非 MCP 来源 |
| **Output 层无主动内容扫描** | `SafetyFinishReasonMiddleware` 只在 provider 返回 `content_filter` 时反应——不主动扫描 agent 输出中的 PII/密钥 |
| **审计日志不落库** | SandboxAudit 是结构化 JSON（`json.dumps`），但只写 `gateway.log`、不落 DB；接 SIEM 需日志采集 |
| **SkillScan 是 best-effort** | 静态分析不能捕获所有动态行为；obfuscated 代码可以绕过 |
| 🆕 **风险门只覆盖 `tools` 列出的工具** | 未探测的工具、MCP 工具、subagent 里的调用都是绕过路径；`tools` 收窄过猛等于没开 |
| 🆕 **风险门会把参数原样出网** | 送的是工具名 + 完整参数 JSON，**不脱敏**；这是新增的 egress 通道，需与数据保护对齐 |
| 🆕 **`plugin_page` 声明页面尚未 gate** | resource 与 `afilter_plugin_pages` 已就绪，但 `plugin_pages` policy key 与 Gateway 调用点未落地，见 [06-extension-boundary.md](06-extension-boundary.md) |
| 🆕 **`require_plugin_management` 的 `PermissionError` 未被 Gateway 翻译** | 插件路由若让它逃逸，客户端看到 500 而不是 403 |

---

## 配置速查

```yaml
guardrails:
  enabled: true                    # 默认 false（GuardrailsConfig.enabled）
  fail_closed: true                # 默认 true：provider 报错 → 合成 deny
  provider:
    # 三选一。Option 3 名单门：
    use: "deerflow.guardrails.builtin:AllowlistProvider"
    config:
      allowed_tools: [bash, ls, read_file, write_file]
      denied_tools: [str_replace]

    # 🆕 Option 4：TypeSafe (Jev) 风险门（网络）
    # use: deerflow.guardrails.typesafe:TypeSafeGuardrailProvider
    # config:
    #   model: jev-latest          # 建议 pin 精确版本，让跨版本判定可追溯
    #   threshold: 0.5             # 概率 ≥ 此值即拒；需用线上评测校准
    #   tools: ["bash"]            # 冒烟范围，不是生产建议：操作可以挪到未探测的 tool
    #   allowed_tools: [bash, read_file]   # 硬权限表：表外本地拒、表内仍须过风险门；[] = 全拒
    #   max_state_chars: 4000      # 参数 JSON 的字符数上限；超限本地拒，不截断
    #   cache_size: 256
    #   cache_ttl_seconds: 300

    # 🆕 Option 4b：同一风险门走 OpenAI Decisions（/v1/decisions predicate）
    # use: deerflow.guardrails.openai_decisions:OpenAIDecisionsGuardrailProvider
    # config:
    #   model: <必填>              # 此 backend 无默认 model，避免批次发往没人选过的模型
    #   api_key_env: OPENAI_API_KEY
    #   threshold: 0.5

# 🆕 所有 TypeSafe 消费者的共享传输配置（guardrail + memory prescreen + signal classification）
# 优先级：消费者自己的 config > 此块 > 内置默认
# typesafe:
#   api_key_env: TYPESAFE_API_KEY   # 默认；优先于 api_key
#   base_url: https://api.typesafe.ai
#   model: jev-latest
#   timeout: 5.0                    # 单请求超时
#   deadline_seconds: 10.0          # 整次评估预算（含读 body 与解析）
#   max_attempts: 2                 # 含首次；仅 429/529 与传输错误重试
#   retry_backoff: 0.5

# Input sanitization（默认 on，middleware 链内置）
# Tool result sanitization（默认 on，middleware 链内置；首方网络工具按名 + MCP 工具按 deerflow_mcp 标签）

read_before_write:
  enabled: true
  elide_blocked_payloads: true   # blocked 调用的死参数在 model-bound request 中替换为占位符
  elide_min_chars: 2000          # 只 elide ≥2000 字符的 payload 字段（字符数，非 token）

skill_scan:
  enabled: true                   # SkillScan 开关（config/skill_scan_config.py）

# ⚠️ security_fail_closed 属于 skill_evolution，不是 guardrails
skill_evolution:
  enabled: false
  moderation_model_name: null     # null = 用默认 chat model
  security_fail_closed: true      # 默认 true：moderation model 不可用时拒绝所有 skill 写入；
                                  # false 时非可执行内容带告警放行，可执行内容始终阻断
```

> **常见误置**：把 `security_fail_closed` 写在 `guardrails:` 下**不会生效**——`GuardrailsConfig`（`config/guardrails_config.py`）只有 `enabled` / `fail_closed` / `passport` / `provider` 四个字段，这个键的真实归属是 `SkillEvolutionConfig`（`config/skill_evolution_config.py:15`），管的是 **agent 改 skill** 时的 moderation 降级行为，与 tool 级风险门是两条不同的路径。

---
> **See also:** [middleware/03-catalog.md](../../internals/middleware/03-catalog.md) · [sandbox isolation](02-sandbox-isolation.md) · [auth](01-auth.md) · [extension boundary](06-extension-boundary.md)
