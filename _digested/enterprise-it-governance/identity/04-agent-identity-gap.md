---
title: "Agent 身份：缺失的一环"
description: "DeerFlow 没有 non-human identity 概念：lead agent、subagent、ACP agent、内部调用者的全部操作都归因到触发它的用户。附带三条可核实的机制证据与五个具体后果。"
topics: [governance, identity, nhi]
---

# Agent 身份：缺失的一环

DeerFlow 的认证是**人**的认证。Agent 本身没有独立身份——它在用户上下文里跑，
所有操作都记成「这个用户做的」。这是本卷最主要的治理缺口。

## 1. 事实：身份如何传播

### 1.1 单一用户上下文

用户身份通过 `packages/harness/deerflow/runtime/user_context.py:101` 的
`get_effective_user_id()` 提供。整个 Agent runtime 在同一个 user 上下文里执行——
lead agent 与其调用的所有工具、**所有 subagent** 共用它。

### 1.2 subagent 继承父任务的 user_id

`packages/harness/deerflow/subagents/batch_acceptance.py:38-40` 是证据：

```python
thread_id, user_id = batch["thread_id"], batch["user_id"]
...
context = {key: spec.get(key) for key in ("user_role", "oauth_provider", "oauth_id",
                                          "channel_user_id", "is_internal", "authz_attributes")}
```

subagent 的 `user_id` 来自父任务的批次数据，`user_role` / `authz_attributes`
等授权属性也一并继承。**没有任何字段标识「这是 subagent 做的」**。

### 1.3 沙箱路径也按用户划分

`batch_acceptance.py:18-20` 用 `user_id` 拼沙箱路径：

```python
"workspace_path": str(paths.sandbox_work_dir(thread_id, user_id=user_id)),
"uploads_path": str(paths.sandbox_uploads_dir(thread_id, user_id=user_id)),
"outputs_path": str(paths.sandbox_outputs_dir(thread_id, user_id=user_id)),
```

所以隔离的粒度是 `user × thread`，**没有 agent 维度**。
同一用户在同一个 thread 里的 lead agent 与 subagent 共享同一个工作目录。

### 1.4 内部调用者：只有一个合成身份

后台任务（IM channel worker、scheduler）用 `system_role="internal"` 的合成用户
（`app/gateway/internal_auth.py:17`、`:68`）：

```python
INTERNAL_SYSTEM_ROLE = "internal"
...
return SimpleNamespace(id=effective_id, system_role=INTERNAL_SYSTEM_ROLE)
```

它**不是真正的 RBAC 角色**——在路由授权时被显式剔除，退回 `default_role`
（`app/gateway/authz.py:300-308`）。若带了 owner 头（`X-DeerFlow-Owner-User-Id`），
则采用 owner 的身份；没有 owner 时保持 internal。

## 2. 五个具体后果

| # | 后果 | 机制原因 |
|---|---|---|
| 1 | **权限最小化做不到** | Agent 继承用户全部 13 个路由权限，任务实际只需其中几项 |
| 2 | **责任归属模糊** | LLM 自发决定删除文件时，审计记录显示是用户干的 |
| 3 | **多 agent 无区分** | lead / subagent / ACP agent 全部归因同一 user（`batch_acceptance.py:38`） |
| 4 | **无法按 agent 撤销** | 停用用户会连带停掉他所有 agent；但不能只停某一个 agent |
| 5 | **后台任务身份粗糙** | scheduler/IM 的 run 要么匿名 internal，要么借用 owner 身份 |

第 5 条特别值得注意：内部调用者如果带 owner 头，就**完全获得该 owner 的权限**；
不带则退到 `default_role`。两者都不是「这个后台任务自身被授予的最小权限」。

## 3. 现有的部分缓解

虽然无 NHI，但有几处机制**限制了** agent 的越权幅度：

| 机制 | 限制了什么 | 证据 |
|---|---|---|
| 沙箱路径隔离 | agent 只能碰 `user × thread` 的目录 | `batch_acceptance.py:18-20` |
| Guardrail | 可在工具调用层拦截特定工具 | `guardrails/middleware.py:171` |
| PAT 路由默认拒绝 | PAT 触发的 agent 只能打白名单路由 | `app/gateway/auth/pat.py:60` |
| 内部角色剔除 | internal 不是 RBAC 角色，无法借它提权 | `app/gateway/authz.py:300-308` |
| `runs:cancel` 条件下检查 | 只有 `runs:create` 的凭据不能靠 `multitask_strategy` 终止运行 | `app/gateway/authz.py:139` |

**这些是「限制」，不是「身份」**：它们约束 agent 能做什么，但不回答
「这个操作是哪个 agent 做的」。

## 4. 缺口（三态）

| 缺口 | 状态 | 边界 |
|---|---|---|
| Agent 独立身份（可认证的 NHI） | **无** | 无 agent 凭据、无 agent id 参与认证 |
| Agent 级权限 | **无** | 权限按 user 解析（`authz.py:278`），无 agent 维度 |
| Agent 归因的审计字段 | **无** | RunJournal 记 `user_role` / `policy_id`，但不记 agent 身份 |
| Agent 级撤销 | **无** | 只能停用户或停整个 thread |
| 临时授权（每次操作申请） | **无** | 无逐操作的授权申请/批准流（除工具级 approval） |
| Subagent 身份传递 | **部分** | 继承了 user_id 与授权属性，但无自身标识 |
| 后台任务的自主身份 | **部分** | 有 `internal` 合成角色，但要么匿名要么借用 owner |

## 5. 这是设计选择，不是遗漏

`system_role="internal"` 的处理方式（`authz.py:300-308` 注释明确说
"Align with Phase 1B's tool path"）表明这是**刻意的简化**：
统一按 owner 归因，可以让 IM channels、scheduler、subagents 复用同一套授权逻辑。

**代价**是所有衍生实体的操作不可区分。企业若需要区分，
只能在 Guardrail 或扩展层自行补充标识——框架不提供。

## 6. 与其他章节的关系

- 四条认证路径（无人/agent 的）：[01-authentication-model.md](01-authentication-model.md) §1
- 13 个权限按 user 解析：[../authorization/04-rbac-permissions.md](../authorization/04-rbac-permissions.md) §5
- 子代理并发与预算：[../execution/05-execution-limits.md](../execution/05-execution-limits.md)
- 授权设计的取舍记录：[06-design-decisions.md](06-design-decisions.md)
