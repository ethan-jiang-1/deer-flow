---
title: "Test Strategy — DeerFlow 测试体系消化"
description: "DeerFlow 自己怎么测自己：测试思想、确定性 LLM 替身、契约与跨栈 E2E、元治理、速度隔离与上层应用测试面。"
type: index
topics: [testing, ci, quality-assurance, architecture]
---

# Test Strategy — DeerFlow 测试体系消化

> **定位**：DeerFlow 的测试不是一套「套件」，而是一套被物化成可执行资产的纪律——规矩写进 `AGENTS.md` 链并由测试钉住，LLM 被确定性替换，文档 / compose / Helm / CI 版本都当契约，连门禁自身也有自测。本目录把它作为整体来消化，并覆盖建在 DeerFlow 之上的上层应用怎么测。给要理解这套体系、或为上层应用定测试策略的人。
> **边界**：面向开发者实操的「用 DeerFlow 开发 agent 应用时怎么测」在 [testing](../testing/README.md)：想抄代码去那边，想理解体系为什么长这样、各层如何补位，读这里。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 全景矩阵：规模数字、四类 22 层测试地图、执行路由表、每层「不证明什么」与已知缺口。
2. **再看**：[01-doctrine.md](01-doctrine.md) — 思想与成文规矩：TDD 强制、offline-first 三分法、确定性纪律、`no-unpinned-invariant`、scar-tissue 文化。
3. **深入**：[02-deterministic-llm.md](02-deterministic-llm.md) — LLM 替身谱系：FakeToolCallingModel → ReplayChatModel → Monocle trace → 手动录制层。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 规模数字、四类 22 层测试地图、执行路由与真 API 用例清单 | 概览 |
| [01-doctrine.md](01-doctrine.md) | 测试思想与成文规矩（TDD、offline-first、确定性、scar-tissue） | 概览 |
| [02-deterministic-llm.md](02-deterministic-llm.md) | 确定性 LLM 替身谱系与「响亮失败」如何穿透中间件 | 深入 |
| [03-contract-e2e.md](03-contract-e2e.md) | 契约双端钉住、两层 replay E2E、anti-fake-green 论证 | 深入 |
| [04-enforcement-meta.md](04-enforcement-meta.md) | 架构即测试与元治理：边界、版本钉住、预算门禁、豁免信任边界 | 深入 |
| [05-speed-isolation.md](05-speed-isolation.md) | 时长基线分片、并行编排、node/dom 成本分流、autouse 重置 | 深入 |
| [06-frontend-and-tui.md](06-frontend-and-tui.md) | rstest 分流、Playwright 四车道、mock 层、几何断言、Textual pilot | 深入 |
| [07-durable-and-recovery.md](07-durable-and-recovery.md) | 崩溃模拟习语、run ownership / 定时任务 / MCP 恢复面、迁移回滚 | 深入 |
| [08-upper-layer-apps.md](08-upper-layer-apps.md) | 扩展、技能、MCP、IM 渠道、custom agents、下游应用三层金字塔 | 概览 |
| [09-test-infra-and-platform.md](09-test-infra-and-platform.md) | `support/` 助手、静态检测器、依赖治理、执行预算、跨平台 skip | 概览 |

## 速览

- **推荐顺序**：`00` 建地图 → `01` 看思想 → `02`/`03` 两个核心机制 → `04`/`05` 外围工程 → `06`–`09` 按需深入。
- **最小阅读集**：写 agent / 中间件 / 下游应用的人读 `02` + `08`；只想抄 replay 机制的人直接从 `02` 开始。
- **v2.2.0 增量三处**：`09` 新增 `support/` 五个助手、`04` 新增 label 声明门禁、`06`/`07`/`08` 的规模数字整体上修（后端测试文件 738 → 1,363，`def test` 14,405 → 23,432）。

## 宪章与约定

- 本目录宪章：[01-doctrine.md](01-doctrine.md) — 测试思想与成文规矩；正文各篇的断言以它为准。
- 统计口径：基于 `ethan` 工作树、对齐上游 **v2.2.0** 基线的文件枚举与 grep 计数，路径相对仓库根；v2.1.0 旧数（704 / 738 个后端测试文件、254 个前端测试文件、28 个 `AGENTS.md`）保留并标注版次。
- 行号锚点当期有效，上游演进后按 [_upstream-sync/SYNC.md](../_upstream-sync/SYNC.md) 复核（本目录已登记进映射表）；硬事实（带锚点）与解释（标注「解释」）分开写，未成文惯例标「实践中」。
- 所有锚点可被 [_upstream-sync/tools/check_digest.py](../_upstream-sync/tools/check_digest.py) 机械校验（路径存在、行号在界内、链接可达、环境变量与类名可解析）。

## 相关目录

- [testing/](../testing/README.md) — 开发者实操层：可抄的模式、CI 模板、Fake 模型用法。
- [frontend/](../frontend/README.md) — 前端测试所覆盖的 UI 架构与状态管理。
- [_upstream-sync/](../_upstream-sync/README.md) — 同步流程与机械校验器。
- [根 README](../README.md) — 全局阅读地图、时间预算与关键词检索。
