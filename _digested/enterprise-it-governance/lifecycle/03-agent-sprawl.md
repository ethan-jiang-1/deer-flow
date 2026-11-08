---
title: "Agent 蔓延风险"
description: "四条增殖路径、五项缺失的控制，以及为什么「没有 agent 清单」是这一卷最根本的治理缺口。"
topics: [governance, lifecycle]
---

# Agent 蔓延风险

Agent 蔓延（sprawl）指一个部署里 agent 定义与实例的数量脱离运营方掌控。
这不是理论风险——四条增殖路径里有三条不需要运维参与。

## 1. 四条增殖路径

| 路径 | 谁触发 | 是否可数 |
|---|---|---|
| **Subagent dispatch** | lead agent 自主决定 | 单次 run 内可数（执行并发默认 3；响应级上限 `MAX_CONCURRENT_SUBAGENT_CALLS = 64`，`subagents_config.py:17`；总数由 `max_total_per_run` 兜底，`:179`） |
| **Custom agent 创建** | **终端用户**（`setup_agent` tool） | 需遍历用户目录才知道 |
| **ACP agent 调用** | agent 自主决定 | 受 `acp_agents` 配置数量限制 |
| **Skills** | 用户在 settings 页自行开启 | 公共 skills 现为 **23** 个 |

### 1.1 为什么「谁触发」这一列最关键

前三条路径中，第 2、3 条都不需要运维介入。
尤其第 2 条：**用户可以自己创建 agent 定义**，落在 `users/{user_id}/agents/{name}/`。

| 想回答的问题 | 需要什么 | 有无 |
|---|---|---|
| 这个部署里有多少个 agent 定义？ | `AgentRow` + `list_all()`（`persistence/agents/base.py:106-110`） | **有服务端方法，无 HTTP 端点** |
| 昨天新建了哪些？ | `created_at` 列（`model.py:31-38`） | **有字段，无查询接口** |
| 谁建的？ | `user_id` 索引 | **有字段，无聚合视图** |

## 2. 五项缺失的控制

| 风险 | 现状 |
|------|------|
| **Agent 清单** | **有持久化清单，缺运行实例视图**。`AgentRow` 有 UUID/id/user_id/created_at，`list_all()` 可列全部 owner（`persistence/agents/base.py:106-110`、`sql.py:137-142`）；缺的是运行实例视图与管理员 HTTP 聚合端点，不是索引能力 |
| **Shadow agent 检测** | **无**。经 SDK 自建的 agent 不进 Gateway，Gateway 看不到 |
| **权限衰减** | **无**。subagent 继承 lead agent 的 sandbox 与 thread_data，拥有与 lead 相同的访问权 |
| **全局紧急终止** | **部分**。有 cooperative cancellation（`cancel_event` 在 astream 边界检查）；`ExecutionFence`（`deerflow_extension_api/agent_runs.py:22`）用单调递增 epoch + 行锁，接管时推进 epoch 使旧持有者的 admission/cancel 失效 |
| **插件能力扩散** | `host_access` 按重启授予且有启动期校验，但无「临时提权」或「按请求收窄」 |

### 2.1 `ExecutionFence` 的边界要说准

`ExecutionFence`（`agent_runs.py:22`）确实是一个比 cooperative cancel 更强的机制：

| 它围住的 | 它**不**围住的 |
|---|---|
| 新的 admission（`start(...)`，`:111`） | 已经发生的**外部副作用** |
| cancellation（`cancel(...)`，`:143`） | 已发出的 HTTP 请求、已写入的外部系统 |

**换句话说**：它能保证「接管之后旧的执行者不能再开始或取消新动作」，
但不能撤销「接管之前已经做出去的事」。这两者在事故处理中的含义完全不同。

## 3. 根因：agent 不是带身份的实体

| 企业通常假设的 | DeerFlow 实际 |
|---|---|
| agent 是一个注册对象 | agent 是**文件**（`users/{id}/agents/{name}/`）或**配置条目** |
| agent 有独立身份凭据 | **无**——agent 用用户身份运行（见 [../identity/04-agent-identity-gap.md](../identity/04-agent-identity-gap.md)） |
| agent 有生命周期状态 | 只有「目录在不在」 |
| agent 能被吊销 | 只能删目录 / 删用户 |

**四行是同一个根因的四种表现**。「没有清单」不是漏做了一个功能——
是因为对象本身没有身份，也就无从建索引。

## 4. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| Agent 清单 / registry | **无** | 用户自建 agent 只能靠遍历目录发现 |
| 创建事件审计 | **无** | `setup_agent` 不产生结构化创建事件 |
| Shadow agent 检测 | **无** | SDK 自建 agent 不经 Gateway |
| 权限衰减 | **无** | subagent 与 lead 同权 |
| 全局紧急终止 | **部分** | `ExecutionFence` 围 admission/cancel，不围外部副作用 |
| 临时提权 / 按请求收窄 | **无** | `host_access` 只能重启改配置 |
| 运行中实例的可观测清单 | **无** | 无跨 run 的实例视图 |

## 5. 与其他章节的关系

- Agent 身份缺失：[../identity/04-agent-identity-gap.md](../identity/04-agent-identity-gap.md)
- Agent 生命周期与存储：[01-agent-lifecycle.md](01-agent-lifecycle.md)
- Subagent 并发与限额：[../cost/03-budgets-and-limits.md](../cost/03-budgets-and-limits.md)
- 执行限额：[../execution/05-execution-limits.md](../execution/05-execution-limits.md)
