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
| 🗺️ 快速理解 DeerFlow 是什么 | [overview/](overview/) | `01-system-overview.md` → 同心圆架构；`01-logical-architecture.md` → 逻辑三图 |
| ⚡ 马上装起来跑 | [getting-started/](getting-started/) | `01-quick-start.md` → 最快上手；`04-python-sdk.md` → `DeerFlowClient` 入门 |
| 🧱 理解核心概念 | [concepts/](concepts/) | Agent、Skill、Tool、Sandbox、Sub-agent、Memory 六大模块 |
| 🛠️ 看怎么实际开发 | `_faq_on_digested/cli-and-sdd/` | CLI 实验、SDD 协作、Sub-agent 编排、Step-by-Step |
| 🔬 深入内部机制 | [internals/](internals/) | Agent Loop、Middleware Chain、Model Layer、Config、Runtime |
| 🧪 测试策略和方法 | [testing/](testing/) | 测试金字塔、FakeToolCallingModel、CI 门禁、Agent 测试最佳实践 |
| 🚀 部署和运维 | [operations/](operations/) | 安全、部署、追踪、IM 通道、IT 治理、API 参考 |
| 🎨 前端怎么做的 | [frontend/](frontend/) | Next.js 16、流式渲染、状态管理 |
| 🔄 跟上游同步 | [_upstream-sync/](_upstream-sync/) | 当前同步点、同步流程 |

## 目录结构

```
_digest/
├── README.md                # 本文件 — 开发者学习路径地图
├── _upstream-sync/          # 上游同步追踪
├── overview/                # 全景图 + 架构概览
├── getting-started/         # 安装、配置、首次运行
├── concepts/                # 核心概念详解
├── patterns/                # 开发模式（→ 详见 _faq_on_digested/）
├── internals/               # 内部机制深入
├── testing/                 # 测试策略 + 实践
├── operations/              # 安全、部署、运维
└── frontend/                # 前端架构
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
