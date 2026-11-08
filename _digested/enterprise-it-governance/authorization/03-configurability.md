---
title: "策略可配置性总览"
description: "哪些策略能在 config.yaml 里改、哪些写死在代码里，以及各自的热生效行为。核心事实：三项安全关键配置需要重启才生效。"
topics: [governance, authorization]
---

# 策略可配置性总览

「能不能配」和「改了什么时候生效」是两个问题。
本页把两件事放在一起，因为运维时它们必须一起考虑。

## 1. 配置矩阵

| 策略 | 配置方式 | 热生效 |
|---|---|---|
| Guardrails allow/deny | `config.yaml` | 下一次 agent invocation |
| Guardrails `fail_closed` | `config.yaml` | 下一次 agent invocation |
| Guardrails provider | `config.yaml` | 下一次 agent invocation |
| SandboxAudit 高危命令 | **改代码**（`sandbox_audit_middleware.py` 的正则族） | **重启** |
| Loop detection | `config.yaml` | 下一次 agent invocation |
| Subagent 执行并发 | `config.yaml` 的 `subagent_runtime.max_running`（默认 3） | **启动快照/重启** |
| Subagent 超时 | `config.yaml` | 下一次 agent invocation |
| `allow_host_bash` | `config.yaml` | **重启** |

### 1.1 矩阵里的关键结论

**真正需要重启的是三类**：

| 项 | 为什么重要 |
|---|---|
| SandboxAudit 高危命令 | 决定哪些命令被阻断；规则硬编码，只能改代码 |
| `allow_host_bash` | sandbox 启动期选项 |
| `subagent_runtime.max_running` | 启动快照，热改对已创建的 controller 无效 |

`fail_closed` 与 provider 不在重启清单里——它们在下一次 agent invocation
重新装配（`tool_error_handling_middleware.py:467-487`）。
这意味着「**发现新的攻击模式 → 调整 SandboxAudit 规则 → 生效**」才需要重启窗口；
纯配置层的 allow/deny、fail_closed、provider 不需要。

## 2. `fail_closed` 的默认值

`packages/harness/deerflow/guardrails/middleware.py:34`：

```python
def __init__(self, provider: GuardrailProvider, *, fail_closed: bool = True, passport: str | None = None):
```

**默认 `True`**——provider 抛错时拒绝，而不是放行。

### 2.1 实际实现

`guardrails/middleware.py:193-196`：

```python
except GraphBubbleUp:
    # Preserve LangGraph control-flow signals (interrupt/pause/resume).
    raise
except Exception:
    logger.exception("Guardrail provider error (sync)")
    if self.fail_closed:
        decision = GuardrailDecision(allow=False, reasons=[GuardrailReason(code="oap.evaluator_error", ...)])
```

| 细节 | 说明 |
|---|---|
| `GraphBubbleUp` 先被单独捕获并**重抛** | 中断/暂停/恢复的控制流信号不被当成 provider 故障 |
| 其余异常按 `fail_closed` 处理 | 默认拒绝 |
| 拒绝原因码 | `oap.evaluator_error`——**可以据此区分「策略拒绝」与「provider 故障」** |

**第三个细节很实用**：审计时看到 `oap.evaluator_error` 就知道不是策略判定，
而是 provider 挂了。这两种情况的处置完全不同。

### 2.2 为什么默认拒绝

| 取向 | 代价 |
|---|---|
| `fail_closed=True`（默认） | 可用性——合法的 tool call 被误拒，可通过重试解决 |
| `fail_open=True` | 安全性——危险的 tool call 被执行，无法撤销 |

在 agent 场景下，重试是廉价的，越权执行不是。

## 3. 为什么 SandboxAudit 的命令规则不可配

### 3.1 事实

在 `config.example.yaml` 与 `config` 模块下搜索 `sandbox_audit`：**零命中**。
规则全部在 `sandbox_audit_middleware.py:27-60` 的正则族里。

### 3.2 两侧的取舍

| 取向 | 好处 | 代价 |
|---|---|---|
| **不可配**（现状） | 「这份部署拦了什么」可从版本号确定 | 新攻击模式只能等发版 |
| 可配 | 能快速响应 | 「这份部署拦了什么」取决于本地文件 |

第一列的好处常被忽略：**审计可证明**。
如果规则可配，那么「你们拦了 `curl | bash` 吗」这个问题就没有确定答案，
只能现场查配置。

### 3.3 已知的规则盲区

`sandbox_audit_middleware.py:49-51` 自己承认一处局限：

> A flag taking its value as the next word (`-o pipefail`, `--rcfile f`) can hide
> either form; its value is indistinguishable from a script argument in this
> heuristic (**a documented gap**).

不可配 + 有已知盲区 = 这个盲区在某个版本之前一直都在。

## 4. 设计取向：预定义边界，非逐步审批

DeerFlow 的自治模型可以概括为四行：

| 谁做什么 | 机制 |
|---|---|
| Agent 自己决定调什么工具 | 无需每步批准 |
| 人预定义「不能调什么」 | Guardrails |
| 人预定义「即使调了也不能执行什么」 | SandboxAudit |
| 唯一的人机交互点 | agent **主动**问（`ask_clarification`） |

**这个模型缺什么**：没有「执行前必须经人确认」的一步。
展开见 [02-bounded-autonomy.md](02-bounded-autonomy.md) §3。

## 5. 缺口的边界条件

| 缺口 | 状态 | 边界 |
|---|---|---|
| 安全策略热更新 | **部分** | Guardrails allow/deny、fail_closed、provider 下一次 invocation 生效；SandboxAudit（改代码）、`allow_host_bash`、`subagent_runtime` 需重启 |
| SandboxAudit 规则可配 | **无** | 设计上不可配，换取可证明性 |
| 规则盲区的运行时披露 | **无** | 盲区只写在代码注释里（`:49-51`） |
| 配置改动的生效确认 | **无** | 无「当前生效配置」查询端点 |
| provider 故障与策略拒绝的区分 | **有但不覆盖** | 有 `oap.evaluator_error` 原因码，但需自行解析 journal |
| per-tenant 差异化策略 | **无** | 配置是全局的 |

**第四行值得展开**：改完 `fail_closed` 重启后，
没有任何端点能确认「现在生效的是新值还是旧值」。
只能从启动日志或行为推断。

## 6. 与其他章节的关系

- Guardrail 全貌：[01-guardrail-layer.md](01-guardrail-layer.md)
- 自治边界：[02-bounded-autonomy.md](02-bounded-autonomy.md)
- 命令审计细节：[../audit/02-sandbox-audit.md](../audit/02-sandbox-audit.md)
- 生命周期与变更管理：[../lifecycle/02-change-control.md](../lifecycle/02-change-control.md)
