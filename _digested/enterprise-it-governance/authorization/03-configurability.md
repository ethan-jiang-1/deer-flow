---
title: "策略可配置性总览"
description: "哪些策略可配置、哪些硬编码，以及为什么。"
topics: [governance, authorization]
---

# 策略可配置性总览

哪些策略可配置、哪些硬编码，以及为什么。

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

见 [../execution/README.md](../execution/README.md) 设计决策分析。核心论点：不可配置 = 审计可证明 + 配置错误免疫。

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
