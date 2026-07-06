---
title: "策略执行"
description: "Agent 能做什么、不能做什么——这些边界不是靠 system prompt "劝" 出来的，而是靠**代码强制执行**的。"
topics: [governance, compliance, audit]
---

# 策略执行

Agent 能做什么、不能做什么——这些边界不是靠 system prompt "劝" 出来的，而是靠**代码强制执行**的。

DeerFlow 的策略执行分四层，从粗到细：

```
System Prompt 约束（概率性）
    ↓
GuardrailMiddleware（确定性：tool 级 allow/deny）
    ↓
SandboxAuditMiddleware（确定性：bash 参数级 block/warn）
    ↓
Execution Limits（确定性：循环检测、并发限制、超时）
```

## 第一层：Guardrails（Tool 级授权）

详见 `_digest/security/03-guardrail.md`。这里从 IT 管理视角总结关键点：

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

### 接入外部策略引擎

`GuardrailProvider` 是 protocol（不需要继承），任何 Python 类都行。把 `use` 指向你的实现即可接入外部 OAP 策略引擎。

**当前局限：** middleware 不填充 `thread_id` 和 `is_subagent`，provider 无法做 per-thread 或 per-agent 策略。如需这些信息，需要修改 middleware 代码。

## 第二层：SandboxAudit（Bash 参数级审计）

详见 `_digest/security/03-guardrail.md`。策略是**硬编码的 regex**，不可通过配置文件修改。

**IT 管理建议：** 如果你需要自定义高危命令列表，fork `sandbox_audit_middleware.py` 中的 `_HIGH_RISK_PATTERNS`。或者在 Guardrail provider 层实现参数级检测（provider 能拿到 `tool_input`）。

## 第三层：Execution Limits

### 循环检测

`LoopDetectionMiddleware` — 检测 agent 是否陷入了重复调用同一个 tool 的循环：

- **Soft block：** 检测到重复 pattern → 注入警告消息（延迟到 `wrap_model_call` 中注入以兼容 OpenAI/Moonshot message 配对校验）
- **Hard stop：** pattern 持续 → 清除 tool_calls → `should_continue` 路由到 END → agent 强制结束
- 可通过 `config.yaml` 中的 `loop_detection.enabled` 开关

### Subagent 并发限制

`SubagentLimitMiddleware` — 限制 lead agent 一次最多派发 3 个 subagent（`MAX_CONCURRENT_SUBAGENTS=3`，限幅 [2, 4]）：

```
LLM 产出 5 个 task tool_call → SubagentLimitMiddleware 截断到 3 个 → 多出的被静默丢弃
```

System prompt 里已经警告了 LLM："任何超出限制的调用会被静默丢弃——你会丢失那些工作。"Middleware 是 defense-in-depth。

### 超时控制

| 超时 | 默认值 | 机制 |
|------|--------|------|
| Subagent 执行 | 900s (15 min) | Thread future timeout + polling safety net |
| Subagent 轮询 | (timeout + 60) / 5 次 | task_tool 中 max_poll_count |

## Bounded Autonomy：DeerFlow 的自动/人工边界

业界最佳实践是把 agent 操作分成 observe/recommend/execute 三级。DeerFlow 目前的边界：

| 操作级别 | DeerFlow 行为 |
|---------|-------------|
| **Observe（读）** | Agent 可以自由读文件、ls、grep——无人工审批 |
| **Execute（写/删/运行）** | Agent 可以自由执行——除非被 Guardrail 或 SandboxAudit 拦截 |
| **高危操作** | Guardrail deny / SandboxAudit block——agent 收到 error，可以换个方法 |
| **人机交互** | `ask_clarification` tool → ClarificationMiddleware → Command(goto=END) → 等人回复 |

**关键区别：** DeerFlow 的 "人机交互" 是 agent 主动问问题（"你想用哪个文件？"），不是权限决策对话框（"agent 要删文件，允许吗？"）。如果你需要高危操作人工审批——目前需要自定义 Guardrail provider 来实现。

## 策略可配置性总览

| 策略 | 配置方式 | 热生效 |
|------|---------|--------|
| Guardrails allow/deny | `config.yaml` | 下一次 agent invocation |
| Guardrails fail_closed | `config.yaml` | 重启 |
| Guardrails provider | `config.yaml` | 重启 |
| SandboxAudit 高危命令 | 改代码 `_HIGH_RISK_PATTERNS` | 重启 |
| Loop detection | `config.yaml` | 下一次 agent invocation |
| Subagent 并发上限 | 代码 `max_concurrent_subagents` | 重启 |
| Subagent 超时 | `config.yaml` → `subagents.timeout_seconds` | 下一次 agent invocation |
| allow_host_bash | `config.yaml` | 重启 |

**核心发现：** 安全关键的配置变更（fail_closed、高危命令、并发上限）都需要重启。这意味着 "发现攻击模式→调整策略→生效" 有延迟窗口。在零信任部署中，考虑在 Guardrail provider（外部 OAP 引擎）层做热更新策略。

## 设计决策分析

### 为什么 Guardrails 默认 fail-closed？

```python
# guardrails/middleware.py:55
try:
    result = await self.provider.evaluate(request)
except Exception:
    if self.fail_closed:
        return ToolMessage(content="Guardrail denied: ...", tool_call_id=...)
```

Agent 场景中 `fail_closed` 是唯一正确的默认值。原因：
- LLM 本质上是不可预测的——安全层出现异常时，不应该放行一个没有人能预料到的 tool call
- Tool 的 blast radius 可能很大——一次 `bash` 调用的影响远大于一次 API 调用的影响
- `fail_closed` 的代价是可用性（一个合法的 tool call 被误拒），`fail_open` 的代价是安全性（一个危险的 tool call 被执行）。在 agent 上下文中，可用性问题可以通过重试解决，安全性问题不能

### 为什么 SandboxAudit 的高危命令列表不可配置？

见 [02-sandbox-governance.md](02-sandbox-governance.md) 设计决策分析。核心论点：不可配置 = 审计可证明 + 配置错误免疫。

### Bounded Autonomy 的设计哲学

DeerFlow 的 autonomy 模型是 **agent 主动、人被动**：

- Agent 自己决定做什么 tool call，不需要每步等批准
- 人通过 Guardrails 预定义边界（"你不能调 bash"）
- 人通过 SandboxAudit 预定义底线（"即使调了 bash，这些命令也不能执行"）
- 唯一的人机交互点是 agent **主动** 问问题（`ask_clarification`），不是人每步审批

这个设计反映了 DeerFlow 的定位：**研究和开发工具，不是生产级多租户平台**。在生产多租户场景中，你可能需要添加：
- 高危操作的人类审批流（"agent 要执行 `pip install`，允许吗？"）
- 基于风险等级的差异化策略（读文件不审批，写文件需要，删除需要双重确认）
- Time-bound 权限提升（"给你 5 分钟的 sudo 权限来完成这个任务"）

这些都不是 DeerFlow 的内建功能，但 Guardrail provider 的 protocol 设计允许你在外部实现。
