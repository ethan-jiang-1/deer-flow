---



title: "工具级授权：Guardrail 层"
description: 'Tool 级授权，可插拔 provider，2.2.0 三个内置门同一协议。'
topics: [governance, authorization]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 工具级授权：Guardrail 层

Tool 级授权，可插拔 provider，2.2.0 三个内置门同一协议。

## 第一层：Guardrails（Tool 级授权）

详见 `_digested/enterprise-operations/security/03-guardrail.md`。这里从 IT 管理视角总结关键点：

### ⚠ 首先要知道：这一层默认不存在

`config.example.yaml` 里 guardrails 的**五种配置方式全部是注释掉的**
（`config.example.yaml:3271-3344`，从 `# --- Option 1` 到 `# --- Option 4b`）。

| 事实 | 含义 |
|---|---|
| 示例配置中 guardrails 整块被注释 | 复制示例文件后，**这一层不启用** |
| 没有 provider 就没有 Guardrail 判定 | 但 SandboxAudit 仍在链上，会 block 高危 bash（`tool_error_handling_middleware.py:489-491`） |
| 代码层 `fail_closed` 默认 `True`（`packages/harness/deerflow/guardrails/middleware.py:34`） | 但只在 provider 存在时才有意义 |

**这是评估顺序上的第一步**：先确认 `guardrails.enabled` 与 `provider.use` 是否配了，
再看下面这些能力。否则讨论的是「配了之后能做什么」。

### 可配置性

```yaml
# config.yaml
guardrails:
  enabled: true
  fail_closed: true             # provider 异常时 deny（安全优先）
  passport: null                 # OAP agent ID
  provider:
    use: "deerflow.guardrails.builtin:AllowlistProvider"
    config:
      allowed_tools: ["bash", "ls", "read_file", "write_file", "web_search"]
      # 或 denied_tools: ["bash", "write_file"]
```

### 策略执行链

```
Agent 请求调 tool → GuardrailMiddleware.wrap_tool_call
  → provider.evaluate(GuardrailRequest)
    → allow=True  → 放行，继续执行
    → allow=False → 返回 error ToolMessage("Guardrail denied: ...")
    → 异常       → fail_closed=True → 合成 deny
                 → fail_closed=False → 放行（记录 warning）
```

### 🆕 2.2.0：三个内置门，同一协议

v2.1 只有名单门。v2.2 增加两个**模型判定的风险门**，都实现同一个 `GuardrailProvider` 协议，在 `guardrails.provider.use` 位置上可互换：

| 门 | 判定 | 需要的运维输入 | 每调用成本 |
|----|------|--------------|-----------|
| `AllowlistProvider` | 名字在 `allowed_tools` / 不在 `denied_tools` | 一张工具清单 | 0（纯本地） |
| `TypeSafeGuardrailProvider` | Jev 对这次调用的风险概率 ≥ `threshold` | API key + **每个危险工具的探测范围** | 一次 HTTP（可缓存 300s） |
| `OpenAIDecisionsGuardrailProvider` | 同一问题走 OpenAI `/v1/decisions` 的 `predicate` | API key + 显式 `model`（**无默认**） | 同上 |

**IT 管理视角的三条要点：**

1. **`tools` 是探测范围，不是安全边界。** 只列 `["bash"]` 是冒烟配置，不是生产建议——操作可以挪到未探测的工具、MCP 工具或 subagent 上。要覆盖就得把**每个能造成副作用的工具**都列进去。
2. **风险门会把工具参数原样出网，且不做脱敏。** 参数里可能带用户内容、路径、shell 命令、密钥；`pii_redaction_middleware` 在这条路径上不生效。启用前必须把这条 egress 通道过一遍数据保护评审。
3. **失败方向由 `fail_closed` 决定，不是永远拒绝。** TypeSafe 不可达时，只有"被探测且缓存未命中"的调用受影响。`fail_closed: true` 下被阻断；`fail_closed: false` 下**合成 allow 并继续执行**，同时记 `allow_tool_call_after_provider_error` 事件（`guardrails/middleware.py:208-217`、`:258-266`）——不是静默降级，但确实放行。

**`allowed_tools` 与 `tools` 的分工**：前者答"这个工具能不能跑"，后者答"哪些调用要送去问模型"。前者先检查——表外工具即使在探测范围外也照样被拒，避免"不在探测范围"顺带赠送一个 allow。

### 接入外部策略引擎

`GuardrailProvider` 是 protocol（不需要继承），任何 Python 类都行。把 `use` 指向你的实现即可接入外部 OAP 策略引擎。

**middleware 填充的上下文字段**（`packages/harness/deerflow/guardrails/middleware.py:76` 的 `_build_request`）：`thread_id`（`:92`）、`is_subagent`（`:93`）、`user_id`、`user_role`、`oauth_provider`、`oauth_id`、`run_id`、`tool_call_id`、`channel_user_id`、`is_internal`、`authz_attributes`，🆕 `tool_provenance`、🆕 `tool_identity`。所以 provider **可以**做 per-thread / per-agent / per-user 策略——2.1 早期文档说"不填充 `thread_id` 和 `is_subagent`"已经不成立。

**仍然拿不到的**：`tool_identity` 是**对象引用**，只在进程内有效，不进入 `AuthzRequest`；它作为 `GuardrailRequest.tool_identity` 交给 provider，但不会序列化/转发（`guardrails/provider.py:33-36` 注释）。需要跨进程判定时只能用 `tool_provenance` 这个可序列化的来源标签。

