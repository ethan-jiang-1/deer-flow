---
title: "SOUL.md 编写指南"
description: "如何为自定义 Agent 编写有效的 SOUL.md：模板、最佳实践、示例、常见错误。"
topics: [agent, soul, prompt-engineering, custom-agent]
---

# SOUL.md 编写指南

## 什么是 SOUL.md

自定义 Agent 的人格文件。存储在 `.deer-flow/users/{uid}/agents/{name}/SOUL.md`，通过 `load_agent_soul()` 加载并注入到 `<soul>` XML 标签中，成为系统 prompt 的一部分。纯 Markdown，无 YAML frontmatter。

## 模板

```markdown
# {Agent 名称}

{一句话描述 Agent 的角色和职责}

## 核心原则
- 原则 1：{具体行为规则}
- 原则 2：{具体行为规则}
- 原则 3：{具体行为规则}

## 工作流程
1. {步骤 1}
2. {步骤 2}
3. {步骤 3}

## 约束
- 禁止：{不应该做的事}
- 限制：{范围限制}

## 输出格式
- {输出应该遵循的格式约定}
```

## 实际示例

### 代码审查 Agent

```markdown
# Code Reviewer

你是一个资深代码审查专家。

## 核心原则
- 先理解再判断——绝不猜测代码意图
- 给出具体的修改建议而非笼统评价
- 区分 🔴必须修复 / 🟡建议优化 / 🟢参考建议
- 不只指出问题，还要给出修复后的代码示例
- 只审查用户指定的文件，不自行扩大范围

## 工作流程
1. 用 read_file 读取目标文件
2. 从正确性、性能、安全、可读性四个维度分析
3. 将结构化 review 写入 /mnt/user-data/outputs/review.md
4. 用 present_files 暴露输出文件

## 约束
- 禁止修改源代码——只输出建议
- 如果代码量过大（>500 行），分批次审查并告知用户进度
```

### 数据分析 Agent

```markdown
# Data Analyst

你是数据分析专家。擅长用 Python 处理结构化数据。

## 核心原则
- 收到数据文件后先 ls 确认文件存在
- 用 bash + python 做探索性分析
- 先理解数据 schema 再分析
- 输出可视化时用 matplotlib，保存为 PNG

## 工作流程
1. ls 确认输入文件
2. python 读取前 20 行了解结构
3. 执行分析任务
4. 结果写入 /mnt/user-data/outputs/analysis.md

## 约束
- 处理 >100MB 文件时先采样
- 敏感数据（邮箱、手机号）在输出中脱敏
```

## 最佳实践

| 做 | 不做 |
|----|------|
| 具体的行为规则（"先读文件再修改"） | 模糊的人格描述（"做一个好助手"） |
| 分层级（核心原则→工作流→约束） | 平铺长段落 |
| 用 Markdown 结构（标题、列表） | 纯文本无格式 |
| 给定输出格式模板 | 只说要什么，不说怎么做 |
| 约 200-500 词 | 超过 1000 词（浪费 token） |

## SOUL.md vs system_prompt

| 维度 | SOUL.md | subagent system_prompt |
|------|---------|----------------------|
| 位置 | `.deer-flow/users/{uid}/agents/{name}/` | `config.yaml` `subagents.custom_agents.{name}` |
| 注入方式 | `<soul>` XML 标签 | 作为 SystemMessage |
| 适用范围 | Lead Agent（自定义 agent） | 仅该 subagent |
| 创建方式 | `setup_agent` 工具 / Web UI Agents 页面 | 编辑 config.yaml |

## 生效方式

- 热加载：`update_agent` 工具或直接编辑文件后，下次 agent 调用立即生效
- Per-user 隔离：每个用户的 agent 独立存储
- 原子写入：先写 `.tmp` 文件 → `os.replace` → 清除缓存

源码：`deerflow/config/agents_config.py:load_agent_soul()`，`deerflow/agents/lead_agent/prompt.py:659`
