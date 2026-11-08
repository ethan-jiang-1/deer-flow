---



title: "Bounded Autonomy：自动 / 人工边界"
description: 'DeerFlow 的边界形态是「预定义 + 事后拦截」，不是「执行前审批」。三个操作级别的实际行为，以及 ask_clarification 为什么不能当权限对话框。'
topics: [governance, authorization]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Bounded Autonomy：自动 / 人工边界

DeerFlow 的自治模型是：**agent 自己决定做什么，人预先划边界**。
理解这句话的具体含义，比套用任何分级框架都重要。

## 1. 三个操作级别的实际行为

按「读 / 写 / 高危」三级看实际发生了什么：

| 操作级别 | DeerFlow 行为 | 人工介入点 |
|---|---|---|
| **读取**（`ls`、`read_file`、`grep`） | 自由执行 | 无审批 |
| **执行/写入**（`bash`、`write_file`、`rm`） | 自由执行，除非被拦 | 无审批 |
| **被判定高危的操作** | Guardrail deny 或 SandboxAudit block | **自动判定**，非人工 |

**三行的共同点**：没有任何一行是「等某个人点同意」。
第三行的拦截是**规则命中**，不是**人工裁决**。

## 2. 拦截的两条路径

### 2.1 Guardrail（工具级）

`packages/harness/deerflow/guardrails/middleware.py:34`：

```python
def __init__(self, provider: GuardrailProvider, *, fail_closed: bool = True, passport: str | None = None):
```

| 特征 | 事实 |
|---|---|
| 判定方 | 可插拔的 `GuardrailProvider` |
| 默认策略 | `fail_closed=True`（provider 异常即拒绝） |
| 粒度 | 工具调用 |
| 是否等人 | **否** |

详见 [01-guardrail-layer.md](01-guardrail-layer.md)。

### 2.2 SandboxAudit（命令级）

`sandbox_audit_middleware.py:458-460`：
高危命令**处理器不被调用**，返回错误 `ToolMessage`。

| 特征 | 事实 |
|---|---|
| 判定方 | 代码内硬编码的正则族 |
| 可配置 | **不可**（见 [03-configurability.md](03-configurability.md)） |
| 粒度 | 单条 bash 命令 |
| 是否等人 | **否** |

详见 [../audit/03-sandbox-audit.md](../audit/03-sandbox-audit.md)。

## 3. `ask_clarification` 不是权限对话框

这是最容易被误认的一点。

`clarification_middleware.py:75-92` 的 docstring：
模型调用 `ask_clarification` 时中断执行、展示问题、等用户回答。

| 维度 | `ask_clarification` | 权限审批对话框（如果有） |
|---|---|---|
| 谁触发 | **模型自己**决定 | 策略强制 |
| 会不会问 | **不一定**——模型可以不问直接做 | 一定 |
| 问什么 | 「你想用哪个文件？」 | 「要删文件，允许吗？」 |
| 回答者 | 终端用户 | 授权审批人 |
| 是否留审批记录 | 无 | 有 |

**关键是第一行**：没有机制强制模型在危险操作前调用它。
所以它提供的是**对话澄清**，不是**执行授权**。

### 3.1 为什么这个区别重要

如果把 `ask_clarification` 当成审批闸门，会得到一个错误的安全假设：
「重要操作都会先问我」。实际上模型可以一次也不问。

展开讨论见 [../compliance/04-eu-ai-act.md](../compliance/04-eu-ai-act.md) §3。

## 4. 边界是「预先划好」的

| 谁定义边界 | 通过什么 |
|---|---|
| 运营方 | `config.yaml` 的 guardrails 段 |
| 运营方 | 外部 provider 的策略内容 |
| 框架（不可改） | SandboxAudit 的正则族 |
| **用户** | **不直接设策略**；但 per-user 的 personal MCP、授权属性会进入 provider 判定（见 [05-mcp-scope.md](05-mcp-scope.md)） |

**最后一行值得注意**：没有**开箱即用**的「per-thread 策略」「per-user 策略」配置项，
边界按部署定义。但 provider 接口能拿到 `thread_id` / `user_id` / `user_role`
（`01-guardrail-layer.md` §2），自定义 provider 可以在判定里使用这些维度——
所以准确说法是「无配置项，有扩展点」，不是「不可能」。

## 5. 能力与缺口的准确表述

| 能力 | 状态 |
|---|---|
| 工具级实时拦截 | **有**（Guardrail） |
| 命令级实时阻断 | **有**（SandboxAudit） |
| 会话中向用户求助 | **有**（clarification） |
| **执行前强制人工审批** | **无** |
| per-thread / per-user 策略 | **部分**——无开箱配置项，provider 接口可做 |
| 按风险分级的差异化审批 | **无** |

## 6. 缺口的边界条件

| 缺口 | 状态 | 边界 |
|---|---|---|
| 强制人工审批闸门 | **无** | 无「等人批准才能执行」的状态机 |
| 模型是否求助的可控性 | **无** | 模型自主决定，无强制触发 |
| 用户自设边界 | **部分** | 无全局用户策略；per-user 的 personal MCP 等局部开关由用户配置（见 [05](05-mcp-scope.md)） |
| 审批留痕 | **无** | clarification 不产生结构化审批事件 |
| 时效性授权 | **无** | 无「给 5 分钟临时权限」的机制 |

## 7. 与其他章节的关系

- Guardrail 机制：[01-guardrail-layer.md](01-guardrail-layer.md)
- 哪些可配：[03-configurability.md](03-configurability.md)
- AI Act 的监督要求：[../compliance/04-eu-ai-act.md](../compliance/04-eu-ai-act.md)
- 命令审计：[../audit/03-sandbox-audit.md](../audit/03-sandbox-audit.md)
