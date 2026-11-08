---
title: "Agent 蔓延风险"
description: "蔓延面、缺失的控制、行业对标。"
topics: [governance, lifecycle]
---

# Agent 蔓延风险

蔓延面、缺失的控制、行业对标。

## Agent 蔓延风险

### 当前的蔓延面

DeerFlow 的 agent 可以通过以下方式增殖：

1. **Subagent dispatch** — lead agent 决定派发多少个 subagent（受 `MAX_CONCURRENT_SUBAGENTS=3` 限制）
2. **Custom agent 创建** — `setup_agent` tool 可以创建新的 agent 定义
3. **ACP agent** — 通过 `invoke_acp_agent` 调用外部 agent（数量取决于 `config.yaml` 中 `acp_agents` 的数量）
4. **Skills** — 20+ 内置 skills + 用户安装的 skills

### 缺失的控制

| 风险 | 现状 |
|------|------|
| **Agent 发现** | 无集中式 agent inventory——subagent 类型在代码/config 中，但运行中的 agent 实例没有注册表 |
| **Shadow Agent** | 无检测机制——如果用户通过 SDK 自建 agent，Gateway 看不到 |
| **权限继承链** | Subagent 继承 lead agent 的 sandbox 和 thread_data——但无权限衰减（subagent 拥有和 lead agent 相同的访问权） |
| **Kill Switch** | 只有 cooperative cancellation（`cancel_event` 在 astream 边界检查），无全局紧急终止。🆕 2.2.0 增加了 `ExecutionFence`（`deerflow_extension_api/agent_runs.py:25`）——单调递增 epoch + 行锁，接管时推进 epoch 使旧持有者的 admission/cancel 失效；但它**只围住新的 admission 与 cancellation，不围外部副作用** |
| 🆕 **插件能力扩散** | `host_access` 按重启授予且有启动期校验，但没有"临时提权"或"按请求收窄"的机制——要么重启改配置，要么不动 |

### 行业对标

Gartner 2026 年建议的六步 Agent 治理框架：
1. 建立治理策略 → DeerFlow：Guardrails `config.yaml` 可视为策略，但无策略版本管理
2. 建立集中式 Agent 清单 → DeerFlow：无
3. 定义 Agent 身份/权限/生命周期 → DeerFlow：Agent 无独立身份
4. 强化信息治理 → DeerFlow：per-user 数据隔离有，但无数据分类
5. 持续行为监控 → DeerFlow：tracing + 审计日志有，但无异常检测
6. 培养负责任的 AI 文化 → 非技术维度
