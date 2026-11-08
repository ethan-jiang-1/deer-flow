---
title: "Harness 工程评估"
description: "从 coding agent 的视角评估 DeerFlow 的 harness 工程质量：agent 文档体系、证据文化、测试工程，以及跨六轮同步的改善轨迹。"
topics: [harness, engineering, agent-docs, assessment]
---

# Harness 工程评估

> 这个目录回答一个问题：**如果把我（一个 coding agent）扔进 DeerFlow 仓库，我能不能高效、不出错地理解和修改它？**
>
> 评估基于 sync #1 → #8（`162fb214` → `58fc5bd5b`，2026-07-04 → 2026-11-04）的全程观察；v2.1.0（`345f08be`，2026-09-24）→ v2.2.0 这一窗口本身有 **1,239 commits**。

| 文件 | 内容 |
|------|------|
| [01-agent-docs-system.md](01-agent-docs-system.md) | Agent 文档体系：分层 AGENTS.md 网络、上下文预算 CI、可执行文档测试 |
| [02-engineering-evidence.md](02-engineering-evidence.md) | 工程证据文化：契约文档、实验包、基准测试、测试工程 |
| [03-feedback-loops.md](03-feedback-loops.md) | 反馈三环：失败是标记不是异常（DeerFlow 取证）、先账后投影、仓库级学习——含与 DSH 的根本分歧（模型级记忆是特性） |

## 一句话结论

**DeerFlow 是把"给 agent 写文档"当作工程问题来解的仓库，目前处于同类开源项目第一梯队**；最大的改善发生在 #4→#5 窗口（AGENTS.md 从 4 个爆发到 25 个）。v2.2.0 窗口给了一个更强的观察点：**预算门禁真的在多个 commit 上咬住了**——`#6759`（middlewares 链 98,441 > 98,304 越线）与 `#7522`（runtime 链 99,004 → 80,817）都是被 `AG002` 打红之后做的定向精简，而且两次都**没有调阈值**、只动文档。这说明这套机制不是装饰。残留风险仍是"文档内部编号漂移"——agent 信任的 AGENTS.md 自身也会过期，而现有机制对编号/顺序类漂移的防护不完整（实例见 [01](01-agent-docs-system.md) 的 middleware 编号案例）。

## 跨同步改善轨迹（coding agent 视角）

| 时间 | 事件 | AGENTS.md 数 | 阶段定性 |
|------|------|--------------|----------|
| 2026-01-14 | 首个 AGENTS.md（AIO sandbox provider，PR #1） | 1 | 孤例 |
| 2026-02-06 | root AGENTS.md（`78b61647`） | 2 | 孤例 |
| **2026-06-25（v2.0.0 发布日）** | `#3770` 宣布 "adopt AGENTS.md as source of truth"（CLAUDE.md 改为 @AGENTS.md 导入） | **2** | **宣言期：有承诺、无覆盖** |
| 2026-07～08 初 | #2/#3/#4 三轮大变更（931 files 等），文档没跟上 | 3→4 | 继续烂 |
| **2026-08-13** | **`#4799` "govern agent guidance size"：一个 PR 拆分 1289 行巨型 backend/AGENTS.md 为 ~20 个 per-directory 文件 + 上线 check_agent_guidance.py 预算 CI** | **4→25** | **转折点：治理开始** |
| 2026-09-06 | `#4945` test_middleware_documentation.py：文档示例进测试夹具 | 25 | 防腐化 |
| **2026-09-12（#6）** | tests/utils AGENTS.md；契约文档随 feature 交付成为默认 | 27 | 制度化 |
| **2026-09-24（#7 / upstream v2.1.0 `345f08be`）** | `#5535` 重写 runtime AGENTS.md（+13 行）；`#5769` 补 10 页 extensions 用户手册、并精修 root AGENTS.md（−1 行）；`#5761`/`#5769` 的深层文档外移 | **29** | **稳定期：文档随 feature 交付** |
| **2026-10-12** | `#6759` docs(agents): trim restated rationale to restore AG002 chain headroom —— `agents/middlewares` 祖先链在 `3f7a0769` 越过 96 KiB 硬线（98,441 > 98,304），该 push 没跑 lint-check，事后靠精简补救 | **43** | **门禁被真实触发（第一次）** |
| **2026-10-26** | `#7522` fix(ci): keep runtime guidance within the chain budget —— runtime 有效链从 **99,004 → 80,817** 字节，checkpoint 模式/replay/模块地图/terminal-ownership 细节整体搬进已有 reference 文档，AGENTS.md 只留不变量与链接 | **56** | **门禁被真实触发（第二次）** |
| **2026-11-04（#8 / upstream v2.2.0 `58fc5bd5b`）** | 新增 29 份 AGENTS.md，几乎全在新子系统：`examples/deerflow-extension-*`（6）、`community/*` provider（12）、`typesafe/`、`storage/`、`uploads/`、`agents/task_continuity/`、`frontend/src/core/{auth,memory}`、`browser-view/`、两个 public skill；老文档反而净缩（root 14.5→13.8 KiB，backend 27.8→24.0 KiB） | **58** | **规模期：预算把"加文档"逼成"加对文档"** |

> 计数口径：本表列 **`*AGENTS.md` 命名的文件**（含变体 `backend/docs/GITHUB_AGENTS.md`）；恰为 `AGENTS.md` 者比表中数少 1——v2.1.0 = 28 个恰名文件 + 1 个变体，v2.2.0 = 57 个恰名 + 1 个变体（[01](01-agent-docs-system.md) 用恰名口径，`scripts/check_agent_guidance.py` 自报 57）。`#4799` 的 25、`#6` 的 27 同样含变体，换算成恰名口径是 24 / 26。中间的 43 / 56 是在 `22ddb77f8`、`3d5107dc0` 两个 commit 上实测的恰名计数（+1 变体即 44 / 57）。

**转折点的精确答案：2026-08-13，PR #4799（v2.0.0 发布后 7 周）。** 你用正规 2.0 时文档糟糕完全符合事实——v2.0.0 的 tag 里只有 `backend/AGENTS.md` 和 `frontend/AGENTS.md` 两个文件，发布当天的 "source of truth" 承诺只是把 CLAUDE.md 改成了转发层，真正的 agent 文档网络是 7 周后那次"治理"PR 一次性建起来的。PR 标题用词 *govern*（治理）说明他们把 agent 文档膨胀当作治理问题来解，而不是写作问题。

关键转折是 **#5 窗口**：Agent 文档从"零星几个"变成"分层网络 + 强制预算 + 可执行验证"三件套。#6 巩固了这套体系（新增 `backend/tests/` 与 `packages/harness/deerflow/utils/` 两处 AGENTS.md；`scripts/`、`frontend/src/` 两处是 #4799 那一批就带的）。

## 总评分（满分 5）

| 维度 | 分 | 依据 |
|------|-----|------|
| Agent 文档覆盖 | 5 | 57 个分层 `AGENTS.md`（+1 变体）覆盖全部关键子系统，含 tests/scripts/community provider/扩展示例/skill 等非常规位置；v2.2.0 的 29 份新增几乎全是新子系统而非老文档膨胀 |
| 文档保鲜机制 | 4 | 预算 CI + 可执行示例是硬防护，且 v2.2.0 窗口内**真的两次触发并靠精简修复**（`#6759`、`#7522`），两次都没调阈值；扣分点仍是编号/顺序类漂移防护不完整，以及 `channels`/`scripts`/`frontend/src` 已贴硬线（余量 4 B ~ 686 B） |
| 证据文化 | 4.5 | 实验包可复现、诚实报告阴性结果（vector 未证明收益→不用 vector） |
| 测试工程 | 4.5 | 迁移级测试（50 revision / 31 测试文件）、blocking_io 分离、CI 4 分片、record/replay e2e；扣分在 v2.2.0 新增 revision 里仍有 5 个无独立迁移测试 |
| 人类文档 | 3 | docs site 双语跟随更新，但入门体验未质变（上游优先级明显在内部质量） |
