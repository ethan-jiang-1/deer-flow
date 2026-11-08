---



title: "Agent 生命周期"
description: '五类 agent 的创建方式与存储位置、配置热更新的两条路径（mtime 签名 vs 必须重启），以及「没有版本管理」这一实际含义。'
topics: [governance, lifecycle]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Agent 生命周期

「上线、改配置、下架」这三件事在企业里有明确的流程要求。
本页讲 DeerFlow 实际提供了什么。

## 1. 五类 agent 及其存储

| Agent 类型 | 创建方式 | 存储位置 |
|-----------|---------|---------|
| **Lead agent** | `make_lead_agent()`（`agents/lead_agent/agent.py:834`，便捷入口在 `agents/__init__.py:20`） | 代码 |
| **Custom agent** | `setup_agent` tool（`tools/builtins/setup_agent_tool.py:58`） | `users/{user_id}/agents/{name}/` |
| **Subagent（内置）** | 代码（`bash_agent.py`、`general_purpose.py`） | 代码 |
| **Subagent（自定义）** | `config.yaml` → `subagents.custom_agents` | `config.yaml` |
| **ACP agent** | `config.yaml` → `acp_agents` | `config.yaml` |

### 1.1 存储位置的含义

| 存在哪里 | 谁能改 | 变更如何留痕 |
|---|---|---|
| 代码 | 开发者（走发版） | git |
| `users/{user_id}/agents/` | **终端用户自己**（经 `update_agent` tool） | **无** |
| `config.yaml` | 运营方 | **无**（除非自己把文件纳管） |

**第二行值得单独看**：custom agent 由用户创建、用户修改，落在该用户目录下。
这意味着「agent 定义」不是只有运营方能改的东西。

## 2. 配置热更新：两条路径

### 2.1 可热更新的（内容签名）

`config/app_config.py:756` 有一条 mtime 快速路径；
`config/file_signature.py:55` 的返回值才是完整签名 `(mtime, size, sha256)`：

```python
return (stat_result.st_mtime, stat_result.st_size, digest.hexdigest())
```

| 变更 | 生效方式 |
|------|---------|
| `config.yaml` 策略字段（model / tool / memory / prompt） | mtime 检测 → **下次请求** |
| `extensions_config.json`（MCP / skills） | API 保存 + 立即生效 |
| Custom agent `SOUL.md` | `update_agent` tool（`tools/builtins/update_agent_tool.py:78`）→ 下次交互 |
| Custom agent `config.yaml` | 同上 |

### 2.2 必须重启的

| 变更 | 生效方式 |
|------|---------|
| `config.yaml` 基础设施字段（database / sandbox / channels） | **需要重启** |
| `allow_host_bash` | **需要重启** |
| `subagent_runtime.max_running` | **启动快照**（热改对已创建 controller 无效） |
| SandboxAudit 规则 | 改代码 + 重启 |

> `guardrails.fail_closed` / `provider` **不在**这张表里：它们在下一次 agent
> invocation 重新装配（`tool_error_handling_middleware.py:467-487`），不需要重启。

展开与取舍见 [02-change-control.md](02-change-control.md)。

### 2.3 内容签名的一个实际后果

签名看 **mtime + size + 内容摘要**。这意味着：

| 场景 | 是否触发重载 |
|---|---|
| 内容真的改了 | 是 |
| 用 `touch` 改了 mtime、内容不变 | **是**（mtime 变了） |
| 同一秒内改两次 | 取决于文件系统时间精度 |

实际影响不大，但值得知道：**改动检测不是基于 diff，而是基于文件签名**。

## 3. 「没有版本管理」的实际含义

| 企业通常期望的 | DeerFlow 提供 |
|---|---|
| 每个 agent 定义有版本号 | **无** |
| 能回滚到上一版 agent 定义 | **无**（只能靠外部 git / 备份） |
| 能查「谁在什么时候改了 agent」 | **无** |
| 能对比两个版本的差异 | **无** |
| 能在版本间灰度 | **无** |

**这四项缺失是同一个根因**：agent 定义是**文件**，不是**带版本的实体**。
框架不记录变更历史，所以版本能力只能由外部（git、备份系统）提供。

## 4. 下架与删除

| 动作 | 机制 | 残留 |
|---|---|---|
| 删除 custom agent | `DELETE /api/agents/{name}`（`agents.py:765-825`）；`agents_api.enabled` 默认 `false` | 删 config/SOUL/memory；无回收站 |
| 停用用户 | `disabled` + `token_version` | 用户数据保留 |
| 删除用户 | PAT 立即失效（`pat.py:224-228`） | **`users/{id}/` 目录需手工清理** |
| 删除 thread | `delete_thread_data`（`routers/threads.py:758`） | thread 立即删；**项目文档**回收站另有 30 天 TTL（不同对象） |

**第三行是最容易漏的**：删用户后账号确实用不了了，
但该用户的 agent 定义、记忆、thread 数据仍在磁盘上。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| agent 定义的版本管理 | **无** | 定义是文件，无版本实体 |
| 变更审计（谁改了什么） | **无** | `update_agent` 不产生结构化事件 |
| 版本回滚 | **无** | 依赖外部 git / 备份 |
| 灰度发布 | **无** | 配置全量生效 |
| kill switch | **无全局 agent 开关** | per-channel 开关存在：`channels.github.enabled` 是 operator kill-switch（`github_webhooks.py:303`、`channels/service.py:1144`）；没有「一键停掉所有 agent/run」的全局开关 |
| 用户级 agent 的集中治理 | **部分** | `AgentRow` 有 UUID/id/user_id 索引、`list_all()` 可列全部 owner（`persistence/agents/base.py:106-110`）；缺的是运行实例视图与管理员 HTTP 聚合端点 |
| 删除用户后的文件残留清理 | **无** | 只有账号层失效，目录需手工处理 |

**第一行与第六行是同一件事的两面**：没有版本实体，也就没有集中视图。
运营方无法回答「现在这个部署里一共存在多少个 agent 定义、分别是谁建的」。

## 6. 与其他章节的关系

- 变更管理与生效路径：[02-change-control.md](02-change-control.md)
- Agent 膨胀问题：[03-agent-sprawl.md](03-agent-sprawl.md)
- 身份与越权：[../identity/04-agent-identity-gap.md](../identity/04-agent-identity-gap.md)
- 策略可配置性：[../authorization/03-configurability.md](../authorization/03-configurability.md)
