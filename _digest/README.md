---
title: "DeerFlow 源码研究笔记 — 开发者知识库"
description: "## 从这里开始：按你的阶段选择"
type: index
---

# DeerFlow 源码研究笔记 — 开发者知识库

> **约束：绝不修改源代码。** `main` 分支跟踪 [bytedance/deer-flow](https://github.com/bytedance/deer-flow) 上游，`ethan` 分支承载所有研究内容。

## 从这里开始：按你的阶段选择

| 你想… | 去这里 | 重点文件 |
|--------|--------|---------|
| 🗺️ 快速理解 DeerFlow 是什么 | [overview/](overview/) | `01-system-overview.md` → 同心圆架构；`03-logical-architecture.md` → 逻辑三图 |
| ⚡ 马上装起来跑 | [getting-started/](getting-started/) | `01-quick-start.md` → 最快上手；`03-python-sdk.md` → `DeerFlowClient` 入门 |
| 🧱 理解核心概念 | [concepts/](concepts/) | Agent、Skill、Tool、Sandbox、Sub-agent、Memory 六大模块 |
| 🛠️ 看怎么实际开发 | `_faq_on_digested/06_cli-and-sdd/` | CLI 实验、SDD 协作、subagent 编排、Step-by-Step |
| 🔬 深入内部机制 | [internals/](internals/) | Agent Loop、Middleware Chain、Model Layer、Config、Runtime |
| 🧪 测试策略和方法 | [testing/](testing/) | 测试金字塔、FakeToolCallingModel、CI 门禁、Agent 测试最佳实践 |
| 🔭 诊断和观察 | [observability/](observability/) | 日志 + trace_id 关联、RunEvent 事件流、追踪、Console API、调试工具箱、上线清单 |
| 🚀 部署和运维 | [operations/](operations/) | 安全、部署、追踪、IM 通道、IT 治理、API 参考 |
| 🎨 前端怎么做的 | [frontend/](frontend/) | Next.js 16、流式渲染、状态管理 |
| 📐 Harness 工程评估 | [harness-engineering/](harness-engineering/) | coding agent 视角的工程质量评估、agent 文档体系、证据文化 |
| 🕸️ 图工程支持到哪儿 | [graph-engineering/](graph-engineering/) | 12 项三档支持度地图、部分支持边界、为什么没有任务 DAG、扩展路线、编排操作面与注入设计 |
| 🪜 编排原语阶梯 | [orchestration-ladder/](orchestration-ladder/) | 跨原语统一视角：完成语义与崩溃窗口、状态三分法、资源预算叠加（借鉴 DSH ladder 方法） |
| 🔄 跟上游同步 | [_upstream-sync/](_upstream-sync/) | 当前同步点、同步流程、机械校验器 `_digest/_upstream-sync/tools/check_digest.py` |

## 目录结构

```
_digest/
├── README.md                # 本文件 — 开发者学习路径地图
├── _upstream-sync/          # 上游同步追踪
├── overview/                # 全景图 + 架构概览
├── getting-started/         # 安装、配置、首次运行
├── concepts/                # 核心概念详解
├── internals/               # 内部机制深入
├── testing/                 # 测试策略 + 实践
├── observability/           # 诊断与观察（日志 / 事件流 / 追踪 / 控制台 / 调试）
├── operations/              # 安全、部署、运维
├── frontend/                # 前端架构
├── harness/                 # Agent 工程实践（AX/DX、可验证性、审计清单）
├── harness-engineering/     # harness 工程质量评估（coding agent 视角）
├── graph-engineering/       # 图工程支持度判定（固定元图 ✅ / 动态任务 DAG ❌）
└── orchestration-ladder/    # 编排原语阶梯（完成语义 / 状态三分法 / 资源预算）
```

## 文件命名约定

- `README.md` — 本目录的阅读指南
- `0X-*.md` — 按推荐阅读顺序编号
- `figures/` — SVG 图（在浏览器中打开渲染）
- 子目录按主题组织（如 `internals/agent-loop/`）

## 工作流

- `main` = 上游镜像，**禁止直接修改**
- `ethan` = 研究分支，所有笔记在这里
- 研究内容 → `_digest/`
- 问答内容 → `_faq_on_digested/`
- 同步上游 → 参考 `_upstream-sync/SYNC.md`

## ⏱ 时间预算

| 时间 | 读什么 | 得到什么 |
|------|--------|---------|
| 5 分钟 | `overview/01-system-overview.md` | 四层同心圆架构 + 进程拓扑 |
| 15 分钟 | + `overview/03-logical-architecture.md` + `overview/06-startup-flow.md` | Agent Loop 怎么跑、启动全流程 |
| 30 分钟 | + `concepts/lead-agent/` + `concepts/sandbox/` + `concepts/subagent/` | 三大核心抽象 |
| 60 分钟 | + `concepts/skills-tools/` + `concepts/memory/` + `internals/middleware/00-overview.md` | 全部核心概念 |

## 🤖 AI Agent 快速检索

```
# 按关键词查找
prompt injection  → operations/security/03-guardrail.md (InputSanitization)
request secrets   → concepts/skills-tools/skill-md-and-tool-assembly.md
goal continuation → internals/runtime/goal-continuation.md
custom middleware → internals/middleware/02-chain-assembly.md + 00-overview.md
TUI / CLI         → getting-started/06-tui.md
record replay     → testing/07-record-replay.md
trace_id / 日志关联 → observability/01-logging-and-trace-context.md
run 事件回放       → observability/02-run-events-and-journal.md
Console / 成本     → observability/04-console-and-cost.md
上线清单 / 告警     → observability/07-production-checklist.md
staleness review  → concepts/memory/extract-queue-persist-pipeline.md
BoxLite / E2B     → concepts/sandbox/abstract-interface-and-seven-impls.md
deferred MCP      → internals/middleware/03-catalog.md (#25 DeferredToolFilter)
deferred skills   → concepts/skills-tools/skill-md-and-tool-assembly.md
评估记分法说明    → harness/09-dsh-eval-harness.md (§0 自说明)
LX1 重放实证      → harness/09-dsh-eval-harness.md (§4.1)
graph engineering / dynamic workflow DAG 支持度 → graph-engineering/01-support-map.md
用 DeerFlow 编排 workflow（旋钮/配方）   → graph-engineering/07-orchestration-surface.md
给 DeerFlow 加编排逻辑（从哪儿进）     → graph-engineering/08-orchestration-extension-points.md
task_dag 注入怎么落                       → graph-engineering/09-task-dag-injection-design.md
"完成"到底指什么 / 崩溃后会不会重复投递  → orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md
哪些状态重启后会丢 / checkpoint 是事实还是投影 → orchestration-ladder/02-状态三分法-持久事实派生投影与内存权限.md
并发/总量限制怎么叠加、哪层先触发       → orchestration-ladder/03-资源预算与公平性-并发深度总量与容量边界.md
```
