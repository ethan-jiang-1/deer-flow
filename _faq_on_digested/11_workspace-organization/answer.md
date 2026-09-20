---
title: "新建干净 repo：deer-flow 作 submodule，应用是主角"
description: "Coding Agent 被根目录框架文件淹没 → 建 V2（~/ai_deerflow_deep_research_v2）：deerflow 用 submodule 钉在自己的 ethan 分支，deep_research_harness 是根目录主角，笔记随 submodule，AGENTS.md 划界。已建成，258 测试通过。"
---

# 新建干净 repo：deer-flow 作 submodule，应用是主角

## 一句话结论

**已建成 `~/ai_deerflow_deep_research_v2`。** deer-flow 用 **submodule 钉在自己的 ethan 分支**（含框架 + 笔记），你的应用 `deep_research_harness/` 是根目录主角。用 `AGENTS.md` 告诉 Coding Agent：**应用是主角，deerflow 是锁定的外部依赖只 leverage 不改。** 258 个测试通过。

## 为什么这么做（两个约束一起解决）

1. **你的应用必须跑在 deer-flow 里**——deer-flow 源码必须物理在 repo 里，这个 repo 离开它跑不起来。
2. **根目录大量框架文件会让 Coding Agent 迷糊**——它一进来读根目录，被几千个框架文件淹没，分不清重点。

**submodule 同时解决两者**：deer-flow 源码确实在（能跑），但树里只显示为一个**钉死的版本链接** `deerflow @ <commit>`。Coding Agent 见到 submodule 会当作外部项目边界，天然不去深挖。

| 形式 | 能不能跑 | agent 会不会迷糊 |
|------|---------|----------------|
| vendored 整树拷贝（V1 现状） | ✅ | ❌ 根目录一大片框架文件 |
| **submodule（V2）** | ✅ deer-flow 完整在 `deerflow/` | ✅ 根目录只有一行 `deerflow @ <commit>` |

## 最终结构（已达成）

```
~/ai_deerflow_deep_research_v2/
├── deep_research_harness/   ★ 你的应用（deep research runtime，src/deerflow_deep_research）
├── deerflow/                submodule → ethan-jiang-1/deer-flow @ ethan（框架 + 笔记 _digest/_faq）
├── openspec/                设计规格（openspec CLI 1.7.0）
├── _backlog/                任务账本
├── profiles/                应用配置档（normal/development/test/demo）
├── AGENTS.md / CLAUDE.md / README.md   应用是主角的地图
├── CONTEXT.md / CONTEXT-MAP.md
├── config.yaml / .env       （本地运行配置，gitignore）
└── 工具配置层：.claude/skills(grillme) · .agents/skills(Codex) · .codex(openspec) · .cursor/.trae · .vscode
```

**核心差异（vs V1）**：V1 里框架（backend/、frontend/、docker/…几十项）和应用平级混在根目录；V2 里框架**全部收进 `deerflow/` 一个子目录**，应用独占根目录。

## AGENTS.md：防迷糊的核心

新 repo 和旧仓的本质区别就在这个文件。agent 一进来就读它，边界立刻清楚：

```markdown
# AGENTS.md（V2 实际内容摘要）
- 本仓 = 跑在 DeerFlow 之上的 deep research 应用。
- **你的工作范围**：deep_research_harness/、openspec/、_backlog/。
- **deerflow/ 是锁定的外部依赖（submodule @ ethan）**，提供运行环境；
  不要探索/修改它的源码，只 import 它的 API。
- 需要理解框架 → 看 `deerflow/_digest/`（研究笔记，只读）。
- 根目录刻意很小：如果你在翻框架内部才能解决任务，停下来重新界定范围。
```

## 它怎么跑（已验证）

```bash
cd ~/ai_deerflow_deep_research_v2/deep_research_harness
uv sync --extra operations --extra demo-tui    # 建 venv（框架走 submodule editable）
.venv/bin/python -c "import deerflow; print(deerflow.__file__)"
#   → .../v2/deerflow/backend/packages/harness/deerflow/__init__.py  ✓ 指向 submodule 内
.venv/bin/python -m pytest tests/unit tests/domain -q    # → 258 passed ✓
```

运行时接线：`deep_research_harness/pyproject.toml` 的 `[tool.uv.sources]` 把 `deerflow-harness` 指向 `../deerflow/backend/packages/harness`（submodule），`uv lock` 重新生成。

## 关键决策（用户拍板）

| 决策 | 值 | 含义 |
|------|-----|------|
| submodule 源 | **自己的 ethan 分支** | 一次带齐框架 + 笔记，不拆 wiki |
| 钉的 commit | ethan HEAD `9ef471e9` | 应用当前跑通的基座 |
| harness 目录名 | **`deep_research_harness`**（原名） | 内部文档全引用它，不能改 |
| 笔记位置 | **在 submodule 里**（`deerflow/_digest`） | 本就在 ethan 上 |
| openspec + grillme | 装进 V2 | 开发工具链 |

## 什么时候不需要做

只有一种情况不值得建：**你一个人、永远不换机器、不让其他 agent 进仓干活**。否则"干净根目录 + AGENTS.md 划界"值得做——尤其你已经开始担心 agent 迷糊，说明它已经发生了。

## 细节

- [执行记录（实际步骤 + 踩的坑 + 验证）](migration-steps.md)

## 相关

- digest：[`_upstream-sync/SYNC.md`](../../_digest/_upstream-sync/SYNC.md) —— 锚点机制（ethan 分支承载框架 + 笔记）
- digest：[`_upstream-sync/SYNC_LOG.md`](../../_digest/_upstream-sync/SYNC_LOG.md) —— 版本差的来龙去脉
- 证据：`deep_research_harness/pyproject.toml` 的 `[tool.uv.sources]`（editable → submodule）；`uv.lock`；258 测试
- 注：git submodule、editable 安装、AGENTS.md 划界属通用工程实践，非 DeerFlow 特性

> 🔄 同步 #6（v2.1.0-rc0）：ethan 分支已前进到 769589e8（已合并 upstream v2.1.0-rc0，含 Node.js 24+ 要求、config_version 45、Projects/Trash/Capability Center 新前端等）。文中 `9ef471e9` 是建仓时钉的 commit，属历史事实、保持不改；如需升级基座，按「未来维护」一节更新 submodule 指针即可。
