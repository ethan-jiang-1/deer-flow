---
title: "Guardrail 与安全防御 — 全链路 Defense-in-Depth"
description: "DeerFlow 2.1 的安全模型从 guardrail 拦截升级为全链路 defense-in-depth：input sanitization → output sanitization → static exfil 检测 → framework tag 阻断 → moderation fail-closed → secrets redaction。"
topics: [security, guardrail, prompt-injection, defense-in-depth, CVE, sanitization]
---

# Guardrail 与安全防御 — 全链路 Defense-in-Depth

> **2.1.0 里程碑 | 安全模型质变**：4 CVE 修复 + 全链路 HTML 转义 + SkillScan 静态外泄检测 + `security_fail_closed` + forged framework tag 阻断。从"guardrail 拦截危险 tool"升级为"任意 untrusted content 进入 prompt 前都被中性化"。

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
| `fail_closed: true`（默认） | provider 异常 → 合成 deny | 安全优先（生产） |
| `fail_closed: false` | provider 异常 → 放行 | 可用性优先（开发） |

### 🆕 `security_fail_closed` for Moderation Model

**新增**：当 moderation model 不可用时，`security_fail_closed` 选项控制行为——设为 `true` 则拒绝所有 tool 调用，防止未经审查的操作通过。

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

---

## 补充防线

### NTFS ADS Smuggling 修复

Skill archive 解压时拒绝 zip 成员名中的冒号（`:`）——防止 NTFS Alternate Data Stream  smuggling 攻击。

### Archive Entry Count Cap

`safe_extract_skill_archive()` 限制 archive 条目数，防止 zip bomb。

### ReadBeforeWriteMiddleware

`read_before_write.enabled`（默认 on）：`write_file` 和 `str_replace` 必须先 `read_file` 取得内容 hash mark，防止并发编辑冲突和未经检查的覆写。

---

## 局限与已知缺口

| 缺口 | 说明 |
|------|------|
| **ToolResultSanitization 仅 name-based** | MCP 远程内容 tool 注册为其他名称时（如 `fetch_url`）不被覆盖 |
| **Output 层无主动内容扫描** | `SafetyFinishReasonMiddleware` 只在 provider 返回 `content_filter` 时反应——不主动扫描 agent 输出中的 PII/密钥 |
| **审计日志非结构化** | SandboxAudit 的日志是 `logger.info()` 文本，不是结构化 JSON |
| **SkillScan 是 best-effort** | 静态分析不能捕获所有动态行为；obfuscated 代码可以绕过 |

---

## 配置速查

```yaml
guardrails:
  enabled: true
  fail_closed: true
  security_fail_closed: false    # 🆕 moderation model 挂掉时拒绝
  provider:
    use: "deerflow.guardrails.builtin:AllowlistProvider"
    config:
      allowed_tools: [bash, ls, read_file, write_file]

# Input sanitization（默认 on，middleware 链内置）
# Tool result sanitization（默认 on，middleware 链内置）

skill_scan:
  enabled: true                   # 🆕 SkillScan 开关
```

---
> **See also:** [middleware/03-catalog.md](../../internals/middleware/03-catalog.md) · [sandbox isolation](02-sandbox-isolation.md) · [auth](01-auth.md)
