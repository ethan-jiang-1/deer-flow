---
title: "Test Strategy — DeerFlow 测试体系消化"
description: "DeerFlow 自己怎么测自己：测试思想与成文规矩、确定性 LLM 替身谱系、契约与跨栈 E2E、架构即测试的元治理、速度与隔离工程、前端与 TUI、持久化与恢复、上层应用测试面。"
topics: [testing, ci, quality-assurance, architecture]
---

# Test Strategy — DeerFlow 测试体系消化

DeerFlow 的测试不是一个"套件"，而是一套**被物化成可执行资产的纪律**：规矩写进 `AGENTS.md` 链并由测试钉住；LLM 被确定性地替换而非真实调用；文档、compose、Helm、CI 工具链版本全部当作可测契约；连门禁自身也有自测。这个目录把这套体系作为一个整体来消化——包括建在 DeerFlow 之上的上层应用（扩展/技能/MCP/渠道/下游应用）该怎么测。

## 与 `testing/` 的分工

| 目录 | 回答的问题 | 视角 |
|------|-----------|------|
| [`testing/`](../testing/README.md) | 你用 DeerFlow 开发 agent 应用时怎么测 | 开发者实操：可抄的模式、CI 模板、Fake 模型用法 |
| 本目录 `test-strategy/` | DeerFlow 作为系统怎么测自己 + 建在它之上的东西怎么测 | 体系研究：思想、分类学、机制如何咬合、工程约束、上层应用测试面 |

两份笔记引用同一批源码，但问题不同。想抄代码去 `testing/`；想理解这套体系为什么长这样、各层如何互相补位，读这里。

## 阅读路径

| 文件 | 内容 |
|------|------|
| `00-overview.md` | 全景矩阵：规模数字、四类 22 层测试地图、执行路由表、真 API 用例清单、每层"不证明什么"、体系已知缺口 |
| `01-doctrine.md` | 思想与成文规矩：TDD 强制、offline-first 三分法、确定性纪律、"真一切只换模型"、no-unpinned-invariant、scar-tissue 文化、设计文档自带测试策略 |
| `02-deterministic-llm.md` | LLM 替身谱系：FakeToolCallingModel → ReplayChatModel（内容寻址回放）→ Monocle trace → 手动录制层 |
| `03-contract-e2e.md` | 契约与跨栈：contracts 双端钉住、两层 replay E2E、anti-fake-green 论证、拒绝 fake tier |
| `04-enforcement-meta.md` | 架构即测试与元治理：harness 边界、compose/Helm/版本钉住、冒烟分层、CI pinning CI、AGENTS.md 预算门禁、豁免清单信任边界 |
| `05-speed-isolation.md` | 速度与隔离工程：时长基线分片、node/dom 成本分流、autouse 单例重置、hermetic 配置、bench 纪律 |
| `06-frontend-and-tui.md` | 前端与 TUI：rstest node/dom 分流、Playwright 四车道、mock 层工程化、几何断言、Textual pilot + 纯 reducer |
| `07-durable-and-recovery.md` | 持久化与恢复：两种不杀进程的崩溃模拟习语、run ownership / scheduled-task / MCP 长任务恢复面、迁移回滚契约 |
| `08-upper-layer-apps.md` | 上层应用测试面：扩展、技能（SkillScan+waiver）、MCP、IM 渠道、custom agents、下游应用三层金字塔——每层"你该怎么测" |

推荐顺序：`00` 先建地图 → `01` 看思想 → `02`/`03` 看两个核心机制 → `04`/`05` 看外围工程 → `06`-`08` 按需深入。**写 agent / 中间件 / 下游应用的人**：`02` + `08` 是你的最小阅读集。只想抄 replay 机制的人可以直接从 `02` 开始。

## 基线与口径

- 统计基于 `ethan` 分支工作树 @ `fb6334b2`（v2.1.0，2026-10）的文件系统枚举与 grep 计数，引用路径相对仓库根。
- 行号锚点以当期工作树为准；上游演进后以 `_digest/_upstream-sync/` 的同步流程复核（本目录已登记进 SYNC.md 的映射表）。
- 本文区分**硬事实**（能从源码/文档核对的陈述，带锚点）与**解释**（对设计意图的推断，标注"解释"）。推测性的内容一律不写；从测试实践归纳、但未成文的惯例会显式标注"实践中"。
- 所有锚点可被 `_digest/_upstream-sync/tools/check_digest.py` 机械校验（路径存在、行号在界内、链接可达、环境变量与类名可解析）。
