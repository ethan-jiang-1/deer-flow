---
title: "新建一个干净 repo：deer-flow 作 submodule 钉死，你的 harness 是重点"
description: "Coding Agent 会被根目录大量框架文件搞迷糊 → 从零建一个新 repo：deerflow 用 submodule 钉在当前跑得通的版本（4915b5e），harness/openspec/skills/backlog/笔记全部进来，AGENTS.md 划清边界。"
---

# 新建一个干净 repo：deer-flow 作 submodule，你的 harness 是重点

## 一句话结论

**从零建一个新 repo。** deer-flow 用 **submodule** 钉死在里面（钉在**你当前跑得通的版本 ~4915b5e**），你的 harness 是根目录的主角，digest/FAQ 笔记进根目录的 `reference/`。用 `AGENTS.md` 告诉 Coding Agent：**重点在 harness，deerflow 是锁定的外部依赖别碰。**

## 为什么这么做（两个约束一起解决）

1. **你的 harness 必须跑在 deer-flow 里**——deer-flow 源码必须物理在 repo 里，这个 repo 离开它跑不起来。
2. **根目录大量框架文件会让 Coding Agent 迷糊**——它一进来读根目录，被几千个框架文件淹没，不知道你要它干什么。

**submodule 同时解决两者**：deer-flow 源码确实在（能跑），但树里只显示为一个**钉死的版本链接** `deerflow @ 4915b5e`。Coding Agent 见到 submodule 会当作外部项目边界，天然不去深挖。

| 形式 | 能不能跑 | agent 会不会迷糊 |
|------|---------|----------------|
| vendored 整树拷贝（现状） | ✅ | ❌ 根目录一大片框架文件 |
| **submodule** | ✅ deer-flow 完整在 `deerflow/` | ✅ 根目录只有一行 `deerflow @ <commit>` |
| git 依赖不进屋 | ❌ 跑不起来 | — |

## 新 repo 的结构

```
deerflow-research/               ← 全新 repo（名字待定，干净根目录）
├── AGENTS.md                    ← ★ 给 coding agent 的地图（核心武器）
├── CLAUDE.md                    ← Claude Code 入口（`@AGENTS.md`，同 deer-flow 惯例）
├── README.md                    ← 一句话 + 怎么把整套跑起来
├── deerflow/                    ← git submodule → bytedance/deer-flow @ 4915b5e
│   └── (backend/packages/harness + backend/app gateway ... 全在里面，agent 不碰)
├── harness/                     ← ★ 你的应用（跑在 deerflow 里的 deep research runtime）
│   ├── pyproject.toml
│   └── src/deerflow_deep_research/   (graph / runtime / agents / engine / domain)
├── openspec/                    ← 设计规格（specs 20+ / changes / governance / policies）
├── skills/                      ← 技能
├── _backlog/                    ← 任务（bugs / learning / plans / todos / _done）
├── reference/                   ← ★ 笔记：_digest/ + _faq_on_digested/（只读参考）
└── scripts/                     ← 起服务脚本（装 deerflow + 起 gateway + 加载 harness）
```

根目录就这些。没有 backend/、frontend/、docker/、venv——**你关心的和 agent 该看到的完全一致。**

## AGENTS.md：防迷糊的核心

新 repo 和旧仓的本质区别就在这个文件。agent 一进来就读它，边界立刻清楚：

```markdown
# AGENTS.md（示意）

- 本仓 = 跑在 DeerFlow 之上的 deep research 应用。
- **你的工作范围**：harness/、openspec/、skills/、tests/。
- **deerflow/ 是锁定的外部依赖（submodule @ 4915b5e）**，提供运行环境；
  不要探索/修改它的源码，你只需要它的 API 面。
- **reference/ 是对 DeerFlow 内部的研究笔记**，用于理解，不是我们的代码。
- 运行方式见 scripts/ 与 README。
- 根目录刻意很小：如果你在翻 deerflow 内部才能解决任务，停下来重新界定范围。
```

## 它怎么跑（和现在完全一致）

现状：harness 的 `import deerflow` 走 editable 安装，`.pth` 指向 vendored `backend/packages/harness`。

新 repo：**同一份代码，同一个机制，只是路径换到 submodule 里**——

```bash
# 在 harness/ 的 venv 里，把 deerflow-harness editable 装到 submodule 的源码上
pip install -e ../deerflow/backend/packages/harness
# 或 harness/pyproject.toml 声明路径依赖，uv sync 解决
```

submodule 钉 `4915b5e` = 你现在 vendored 的那份（5 个跨区域代表文件已精确比对一致）。**代码一字不变，行为零变化，跑法和现在一模一样。**

## 两个已定的决策 + 一个已知的版本差

| 决策 | 你的选择 | 含义 |
|------|---------|------|
| submodule 钉哪个 commit | **钉现在能跑的 ~4915b5e** | 不动运行时，harness 照跑 |
| 笔记放哪 | **根目录 `reference/`** | 一处放全，AGENTS.md 声明它不是代码 |

**已知版本差（写进 reference/README 即可，不解决）**：运行时钉在 **4915b5e**，而 digest 笔记描述的是 **e5c62cab**——笔记比代码新一个大版本。将来想对齐再做一次有意升级（换 submodule commit + 重跑测试），现在不用管。

## 什么时候不需要做

只有一种情况不值得建新 repo：**你一个人、永远不换机器、不让其他 agent 进仓干活**。否则"干净根目录 + AGENTS.md 划界"值得做——尤其你已经开始担心 agent 迷糊，说明它已经发生了。

## 细节

- [从零搭建步骤（建仓 → submodule → 搬内容 → 接线 → 验证）](migration-steps.md)

## 相关

- digest：[`_upstream-sync/SYNC.md`](../../_digest/_upstream-sync/SYNC.md) —— 锚点机制（4915b5e / e5c62cab 都是这里记录的锚点）
- digest：[`_upstream-sync/SYNC_LOG.md`](../../_digest/_upstream-sync/SYNC_LOG.md) —— 版本差的来龙去脉
- 证据：`_editable_impl_deerflow_harness.pth` 指向 vendored `backend/packages/harness`；vendored 的 5 个代表文件精确匹配 `4915b5e`；`deep_research_harness/pyproject.toml` 声明 `deerflow-harness>=2.1.0,<2.2`
- 注：git submodule、editable 安装、AGENTS.md 划界属通用工程实践，非 DeerFlow 特性
