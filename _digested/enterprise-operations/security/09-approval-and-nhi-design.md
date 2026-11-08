---
title: "P0 缺口的最小设计：审批闸门与 Agent 身份"
description: '不写代码，只给接口、状态机、事件与验收标准：如何给 DeerFlow 补上强制审批和 NHI。'
topics: [security, approval, agent-identity, design, enterprise]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# P0 缺口的最小设计：审批闸门与 Agent 身份

> **这是设计草案，不改变现状。** 目的不是提交实现，而是把「补什么、补在哪、怎么验收」说到企业评审能点头的程度。代码位置只用于说明接入点，不代表已经实现。

## 0. 为什么先设计这两件

07 的 P0 有四件：没有 NHI、没有强制审批、审计不能出证据包、四个控制默认关。后两件是「导出/配置」问题，前两件是**结构性缺口**：它们决定 agent 能不能被追责、高危动作能不能被拦住。没有这两件，审计导出做得再好，也只能证明「某个用户身份做了某事」，不能证明「哪个 agent 在什么授权下做了什么」。

这两件不需要把 DeerFlow 改成平台，但需要动 principal、authz、middleware 和事件模型，所以先把接口和状态机定清楚。

---

## 1. Approval Gate：执行前的确定性暂停

### 1.1 现状与边界

| 现有机制 | 能做到 | 做不到 |
|----------|--------|--------|
| `ask_clarification` | 模型主动问用户 | **模型可以选择不问**；不是授权 |
| 沙箱出网域名审批 | 域名级、带 TTL 的人工放行 | 只管网络域名，不管 bash/写文件/插件 action |
| `GuardrailMiddleware` | allow / deny 的即时判定 | 没有「pending」状态；deny 后无法等人批准再执行 |

所以企业要的不是「再做一个审批 UI」，而是一个**执行前必须经过的决策点**：策略说「这个动作要人批」，run 就停下来，直到有人批/拒/超时。

### 1.2 目标与非目标

| 目标 | 非目标 |
|------|--------|
| 策略驱动：按工具、参数、风险、角色决定要不要批 | 不做通用 BPM/工单系统 |
| fail-closed：没有审批人、超时、存储错误 → 拒绝 | 不自动放行「看起来安全」的请求 |
| one-shot：一次批准只对一次调用有效 | 不做长期授权/白名单 |
| 参数绑定：批准后参数变了就失效 | 不把审批结果交给模型解释 |
| 可审计：请求、决定、超时都进 RunJournal/SIEM | 不在第一版做多级会签/移动端推送 |
| 可恢复：进程重启后 pending 还在 | 不做跨租户审批路由 |

### 1.3 状态机

```
tool_call
  → guardrail.allow
  → approval.evaluate
      ├─ auto_allow → 执行
      ├─ deny       → 返回拒绝 ToolMessage
      └─ require    → 创建 ApprovalRequest(status=pending)
                        ├─ granted  → 参数 digest 一致且未过期 → 执行
                        ├─ denied   → 拒绝
                        ├─ expired  → 拒绝
                        └─ cancelled（run 被取消）→ 拒绝/丢弃
```

**关键规则**：

1. `pending` 不是「等模型再问一次」，而是 run 的持久状态；进程重启后仍能恢复。
2. 批准后必须校验 `args_digest`；参数变了就重新走审批，不能复用旧批准。
3. 任何异常（存储不可用、审批人解析失败、超时）都走 deny，不允许 fail-open。
4. 一次批准只对 `tool_call_id` + `args_digest` 有效；不做「本 run 内一直有效」。

### 1.4 接口草图（不是实现）

```python
class ApprovalRequest:
    approval_id: str
    run_id: str
    thread_id: str
    tool_call_id: str
    tool_name: str
    args_digest: str          # canonical JSON 的 SHA-256
    args_preview: str         # 脱敏后的人类可读摘要，不进模型上下文
    risk: str                 # low / medium / high
    requested_by: str         # user_id
    agent_id: str | None      # NHI 落地后必填
    approver_scope: str       # owner / role:admin / channel:...
    expires_at: datetime
    status: str               # pending / granted / denied / expired / cancelled

class ApprovalDecision:
    approval_id: str
    outcome: str              # granted / denied / expired / cancelled
    decided_by: str | None
    reason: str | None
    decided_at: datetime

class ApprovalGate(Protocol):
    def evaluate(self, ctx: ToolCallContext) -> str: ...   # auto_allow / deny / require
    def request(self, ctx: ToolCallContext) -> ApprovalRequest: ...
    def resolve(self, approval_id: str, decision: ApprovalDecision) -> None: ...
```

### 1.5 接入点

- **位置**：`GuardrailMiddleware` 之后、tool handler 之前。guardrail 先做「允不允许」，approval 再做「要不要人批」；两者不合并，避免把策略和流程耦在一起。
- **暂停方式**：优先用持久化 pending + run 状态机（重启可恢复）；不要用 `time.sleep` 或阻塞 event loop。若用 LangGraph interrupt，必须保证 interrupt 值可重放、可幂等。
- **恢复方式**：审批完成后由 Gateway 触发 resume；resume 时重新校验 run 状态、用户权限、工具参数 digest。
- **存储**：SQLite/Postgres 一张 `approval_requests` 表；`(tool_call_id, args_digest)` 唯一；状态变更用条件 UPDATE，避免重复决定。

### 1.6 事件与审计

| 事件 | 关键字段 |
|------|----------|
| `approval.requested` | approval_id, run_id, thread_id, tool_name, args_digest, risk, requested_by, approver_scope, expires_at |
| `approval.granted` | approval_id, decided_by, decided_at, reason |
| `approval.denied` | approval_id, decided_by, decided_at, reason |
| `approval.expired` | approval_id, expired_at |
| `approval.cancelled` | approval_id, cancelled_by, reason |

落点建议：RunJournal 增加 `middleware:approval` 事件；`args_preview` 只进审计，不进模型 prompt；`args_digest` 用于重放与一致性校验。

### 1.7 策略示例

| 风险 | 例子 | 默认动作 |
|------|------|----------|
| low | `read_file`、`ls`、`glob`、`grep`、`web_search` | auto_allow（仍受 guardrail/RBAC） |
| medium | `write_file`、`str_replace`、`web_fetch` | 首次 require，可按目录/域名收窄 |
| high | `bash`、插件 action、外部写操作、支付/发信类工具 | require + 指定角色/owner |
| critical | 删除、批量导出、权限变更 | require + 双人/管理员（第一版可只做单人） |

审批人解析顺序建议：thread owner → 配置的角色 → 渠道管理员；**不允许模型选择审批人**。超时默认 15 分钟，可按工具配置。

### 1.8 开放问题

- 多租户/多级会签：第一版不做，但 `approver_scope` 要留扩展位。
- 审批结果回灌：IM 卡片、Web UI、API 三种入口要共用同一个 `resolve()`。
- 幂等：同一 `tool_call_id` 重复请求要返回同一个 pending，不重复通知。
- 误批：批准后参数变更必须失效；建议在 resume 时再算一次 digest。

### 1.9 验收标准

1. 配置 `require` 的工具调用会停在 pending，不执行 handler。
2. 批准且参数未变 → 执行一次；重复批准 → 不重复执行。
3. 拒绝/超时/存储异常 → 工具不执行，返回可解释的拒绝消息。
4. 批准后改参数 → 旧批准失效，重新审批。
5. 进程重启后 pending 仍可查、可批、可超时；事件完整。

---

## 2. Agent Identity（NHI）：从「用户代理」到「可追责的行动者」

### 2.1 现状

- 整个 runtime 只有一个 `get_effective_user_id()`（`runtime/user_context.py:101`）。
- subagent 直接继承父任务的 `user_id` 与授权属性（`subagents/batch_acceptance.py:38`）。
- 没有 agent 凭据、没有 per-agent scope、没有按 agent 撤销；审计只能记到用户。
- `host_access` 明确说自己是「归属 + 防误用」，不是沙箱（`extensions/host_access.py:1`）。

### 2.2 两条路线

| 路线 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A. 轻量** | principal 增加 `agent_id` + `agent_scopes`；不新增凭据 | 改动小；审计能区分 agent；可按 agent 收窄工具 | 不是真认证；agent_id 由宿主注入，防不了宿主内伪造 |
| **B. 完整 NHI** | agent 有独立身份 + 短期 token/capability；Gateway 签发/校验/撤销 | 可认证、可撤销、可跨进程/外部工具 | 改动大；要动 principal、authz、工具边界、密钥管理 |

**建议先做 B-lite**：保留用户身份作为 owner，但给每次 run 一个 **agent identity + 受限 scope + 短期签名 token**；in-process 工具用 principal 校验，外部 MCP/HTTP 工具带 token。这样既能追责，又不用一步到位做完整 OAuth。

### 2.3 身份模型

```text
AgentIdentity
  agent_id            # 稳定 ID（内置 agent 用名字，自定义 agent 用 UUID）
  owner_user_id       # 谁对它负责
  role                # 继承/收窄自 owner
  scopes              # tool:bash, sandbox:execute, mcp:github, plugin:acme/report
  token_version       # 撤销用
  run_id              # 本次 run
  parent_agent_id     # subagent 指向父 agent
  expires_at          # 短期
```

**委派规则**：`effective_scopes = owner_scopes ∩ agent_scopes ∩ parent_scopes`；只能收窄，不能扩权。subagent 的 scopes 必须是父 agent 的子集；插件/外部工具不能借 agent 身份拿到比 owner 更大的权限。

### 2.4 签发、校验、撤销

| 阶段 | 动作 |
|------|------|
| 签发 | run admission 时由 Gateway 生成 identity；token 用 Gateway 私钥签，TTL 与 run 绑定（建议 15 分钟，可续） |
| 校验 | 工具调用前校验签名、`aud`（run/thread）、`exp`、`token_version`；in-process 工具用 principal，外部工具用 bearer |
| 撤销 | 按 `agent_id` 递增 `token_version`；新调用立即失败；已准入的 run 走 cancel/approval 兜底 |
| 审计 | 所有事件带 `agent_id`、`parent_agent_id`、`owner_user_id`；token 不进 prompt/trace |

### 2.5 与现有代码的映射

| 现有位置 | 需要加什么 |
|----------|------------|
| `runtime/user_context.py:101` | 增加 `agent_id` / `parent_agent_id` 的 ContextVar；`get_effective_user_id()` 保留 owner 语义 |
| `authz/principal.py` | `Principal` 增加 `agent_id`、`agent_scopes`；`build_principal_from_context` 从 run context 读 |
| `authz/provider.py` | `AuthzRequest` 已支持 resource/action/target；把 `tool:<name>`、`sandbox:execute`、`mcp:<server>` 作为 target |
| `subagents/batch_acceptance.py:38` | 不再只复制 `user_id`；生成 child identity，scopes 取子集 |
| `guardrails/middleware.py` | `GuardrailRequest` 已带 `user_id/thread_id/is_subagent`；加 `agent_id`、`agent_scopes` |
| `runtime/journal.py` | 事件字段加 `agent_id`、`parent_agent_id`；`approval.*` 同表 |
| `auth/pat.py` | 不复用 PAT 作为 agent token；PAT 是人的程序化凭据，agent token 是 run 级短期凭据 |

### 2.6 事件

| 事件 | 关键字段 |
|------|----------|
| `agent.identity.issued` | agent_id, owner_user_id, run_id, scopes, expires_at, token_version |
| `agent.identity.revoked` | agent_id, token_version, revoked_by, reason |
| `agent.delegated` | parent_agent_id, child_agent_id, parent_scopes, child_scopes |

### 2.7 风险与非目标

- **token 泄露**：短期 + audience 绑定 + 不进 prompt/trace；外部工具只拿到最小 scope。
- **confused deputy**：agent token 不能代替用户做未授权操作；`effective_scopes` 三方取交。
- **重放**：`jti` + `run_id` + 短期 TTL；审批/工具调用都要幂等。
- **非目标**：不做 agent 的 OAuth 授权服务器、不做跨租户 agent 联邦、不做长期 agent 凭据。

### 2.8 验收标准

1. 同一用户的两个 agent 调用同一工具，审计能区分 `agent_id`；一个被撤销不影响另一个。
2. agent A 的 scopes 不含 `tool:bash` 时，调用 bash 被拒绝（即使 owner 有权限）。
3. subagent 不能拿到父 agent 没有的 scope；越权请求 fail-closed。
4. 外部 MCP/HTTP 工具收到的是 run 级短期 token，不是用户 JWT/PAT。
5. 撤销后新调用立即失败；已准入 run 可被 cancel/审批拦截。

---

## 3. 落地顺序与边界

1. **先做 Approval Gate**：它只依赖现有 user/guardrail/tool_call 上下文，改动面小，能先解决「高危动作没人批」。
2. **再做 NHI B-lite**：它要动 principal 和 authz，放在审批之后，避免同时改两条安全边界。
3. **审计导出与默认配置**并行做：它们不阻塞前两件，但决定企业评审能不能过。

> 这两件都不是「加一个 middleware」就完事：审批要状态机和恢复，NHI 要 principal 和 token 生命周期。但如果只做一半（比如审批只做 UI、NHI 只加日志字段），企业评审会很快看出来——所以先把接口、事件、验收标准定清楚，比先写代码更重要。

---

> **See also:** [07-enterprise-readiness.md](07-enterprise-readiness.md)（P0/P1 差距与 20 问） · [08-control-checklist.md](08-control-checklist.md)（85 项控制与证据索引） · [01-auth.md](01-auth.md)（现有认证/RBAC） · [03-guardrail.md](03-guardrail.md)（Guardrail 接入点） · [enterprise-it-governance/authorization/02-bounded-autonomy.md](../../enterprise-it-governance/authorization/02-bounded-autonomy.md)（为什么 clarification 不是审批）
