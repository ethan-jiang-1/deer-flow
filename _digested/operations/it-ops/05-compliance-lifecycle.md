---
title: "合规与生命周期"
description: "数据怎么存的？用户数据隔离吗？Agent 生命周期怎么管？能不能满足 GDPR/SOC2 审计？"
topics: [governance, compliance, audit]
---

# 合规与生命周期

数据怎么存的？用户数据隔离吗？Agent 生命周期怎么管？能不能满足 GDPR/SOC2 审计？

## 数据治理

### Per-User 数据隔离

```
backend/.deer-flow/users/{user_id}/
    memory.json                 # 用户记忆（与 agent 对话提取的事实和偏好）
    threads/{thread_id}/
        user-data/
            workspace/          # Agent 工作文件
            uploads/            # 用户上传文件
            outputs/            # Agent 输出文件
    agents/{agent_name}/        # 自定义 agent 定义
        SOUL.md
        config.yaml
```

每个用户的数据物理隔离在不同的目录下。`user_id` 从 JWT 中解析，在 no-auth 模式下所有人共享 `default` user。

#### OpenAI Assistants API 兼容接口

Gateway 实现了 OpenAI Assistants API 兼容层，外部 OpenAI SDK 可以通过该接口与 DeerFlow 交互。对于这些外部请求，用户身份验证通过 JWT 进行，创建的 thread 和 run 仍然遵循 per-user 隔离规则。

### 输出脱敏

`mask_local_paths_in_output()` — 所有 sandbox 输出被正则扫描，host 路径替换回虚拟路径。覆盖：
- user-data（`/mnt/user-data/{workspace,uploads,outputs}`）
- skills（`/mnt/skills`）
- ACP workspace（代理到 `/mnt/acp-workspace/`）
- 自定义路径映射

防止 agent 输出中泄露 `~/.deer-flow/users/{user_id}/threads/{thread_id}/...` 这种目录结构。

### 错误信息脱敏

`tools.py` 中，Local 模式下 tool 异常消息中的 host 路径被替换回虚拟路径。

### 文件上传安全

| 控制 | 实现 |
|------|------|
| **类型白名单** | PDF, PPT, Excel, Word → 通过 `markitdown` 转换 |
| **目录拒绝** | 拒绝上传路径中包含目录的请求 |
| **去重** | 同名文件自动 `_N` 后缀去重 |
| **转换隔离** | 文档转换复用单个 worker |

### Skills 安全扫描

`deerflow/skills/security_scanner.py` — Agent 写 skill 文件时，先经过 LLM-based 安全检查再持久化。这是 defense-in-depth 的一环——防止 agent 生成恶意 skill 文件。

### 数据保留

当前无自动数据保留/清理策略。Thread 删除（`DELETE /api/threads/{id}`）会清理 LangGraph thread + 本地 thread 目录。Memory 没有自动过期机制。

## 合规考量

### GDPR 相关

| 要求 | DeerFlow 现状 | 差距 |
|------|-------------|------|
| **数据访问权** | Per-user 存储 → 技术上可导出 `users/{user_id}/` | 无内建导出工具 |
| **数据删除权** | `DELETE /api/threads/{id}` → 删除 thread 数据 | 无批量删除；memory 无自动过期 |
| **数据处理记录** | 审计日志 + tracing → 能追溯 agent 操作 | 日志非结构化，需手动解析 |
| **数据最小化** | 无数据分类标签；memory 提取全量对话事实 | 无敏感数据自动识别 |
| **跨境传输** | 取决于 LLM provider（API 调用→数据传输到 provider） | 使用海外 provider（Anthropic/OpenAI）时自动触发跨境 |

### SOC2 / ISO27001

| 控制域 | DeerFlow 能力 | 证据 |
|--------|-------------|------|
| **访问控制** | JWT + per-user isolation | `security/01-auth.md` |
| **审计日志** | SandboxAudit + RunJournal + tracing | `04-audit-observability.md` |
| **变更管理** | Config 版本控制（git）+ hot-reload | `configuration/` |
| **风险评估** | 沙箱隔离 + guardrail + 循环检测 | `00-overview.md` 12 维度矩阵 |
| **供应商管理** | LLM provider 依赖（Anthropic/OpenAI/等） | 需要自行评估各 provider 合规状态 |

**核心差距：** DeerFlow 有技术控制，但缺乏合规文档（SOC2 report、ISO27001 证书）。如果你的企业需要通过这些审计，DeerFlow 是**你可以纳入合规范围的基础设施组件**，但本身不出具合规证明。

### EU AI Act（2026 年 8 月生效）

DeerFlow 作为一个通用 Agent 框架，不属于高风险 AI 系统（不直接用于关键基础设施、执法、教育评分等）。但**你的 use case 可能是**。如果你用 DeerFlow 构建面向消费者的金融服务 agent，那它就在 EU AI Act 范围内。

需要评估的要素：
- Agent 自主性级别（DeerFlow 的 bounded autonomy → 可配置）
- 人工监督机制（ClarificationMiddleware 提供对话式交互，非权限审批）
- 透明性（模型回复的 AI 标签、用户被告知在与 AI 交互的程度）

## Agent 生命周期

### Agent 创建

| Agent 类型 | 创建方式 | 存储位置 |
|-----------|---------|---------|
| **Lead agent** | `langgraph.json` 注册 + `make_lead_agent()` | 代码 |
| **Custom agent** | `setup_agent` tool（bootstrap 模式） | `users/{user_id}/agents/{name}/` |
| **Subagent（内置）** | 代码（`bash_agent.py`, `general_purpose.py`） | 代码 |
| **Subagent（自定义）** | `config.yaml` → `subagents.custom_agents` | config.yaml |
| **ACP agent** | `config.yaml` → `acp_agents` | config.yaml |

### Agent 配置热更新

| 变更 | 生效方式 |
|------|---------|
| `config.yaml` 策略字段（model, tool, memory, prompt） | mtime 检测 → 下次请求 |
| `config.yaml` 基础设施字段（database, sandbox, channels） | **需要重启** |
| `extensions_config.json`（MCP, skills） | API 保存 + 立即生效 |
| Custom agent SOUL.md | `update_agent` tool → 下次交互 |
| Custom agent config.yaml | `update_agent` tool → 下次交互 |

### Agent 停用/删除

- **Thread 删除：** `DELETE /api/threads/{id}` 删除 LangGraph thread + 本地 thread 目录
- **Custom agent 删除：** 无 API——手动删除 `users/{user_id}/agents/{name}/` 目录
- **Skill 关闭：** `PUT /api/skills/{name}` → `enabled: false`

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
| **Kill Switch** | 只有 cooperative cancellation（`cancel_event` 在 astream 边界检查），无全局紧急终止 |

### 行业对标

Gartner 2026 年建议的六步 Agent 治理框架：
1. 建立治理策略 → DeerFlow：Guardrails `config.yaml` 可视为策略，但无策略版本管理
2. 建立集中式 Agent 清单 → DeerFlow：无
3. 定义 Agent 身份/权限/生命周期 → DeerFlow：Agent 无独立身份
4. 强化信息治理 → DeerFlow：per-user 数据隔离有，但无数据分类
5. 持续行为监控 → DeerFlow：tracing + 审计日志有，但无异常检测
6. 培养负责任的 AI 文化 → 非技术维度
