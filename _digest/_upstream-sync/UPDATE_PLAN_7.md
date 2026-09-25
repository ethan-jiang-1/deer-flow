---
title: "Digest 更新计划 #7"
description: "基于 upstream v2.1.0-rc0 (769589e8) → v2.1.0 (345f08be) 的 10 commits，逐文件规划 digest 更新与校正项。"
type: index
---

# Digest 更新计划 #7

> 基准：`769589e8`（v2.1.0-rc0）→ `345f08be`（**v2.1.0**，10 commits），2026-09-24
> 变更规模：90 files, +9,097 / −450
> 提交构成：3 fix / 2 docs / 1 chore(ci) / 4 chore(doc)
> ⚠️ 特性：tag 打在 release 分支 `2.1.x-dev`，**与 `upstream/main` 已分叉**（main 另有 189 commits 待下次处理）

## 一句话总结

发布收尾窗口，**没有新子系统**：4 个代码层实质变更（0025 修复型迁移、线程删除全量清理、事件存储变更串行域、CI `*-dev` 触发）+ 1 个前端布局修复 + 2 本用户手册改版 + root `AGENTS.md` 精简。digest 侧的重点因此不是"增"，而是**校正既有描述**：迁移链 head、删除语义、行号引用、AGENTS 计数与预算实测值。

## ▶ 执行清单（全部完成）

| 步 | 文件 | 做什么 | 状态 |
|----|------|--------|------|
| 1 | `internals/persistence/db-checkpointer-store-backends.md` | 迁移链 0001→**0025**；新增 0025 修复型迁移小节（#5516 的"插队"失败模式与迁移纪律）；ORM 表补 `UserPreference`/`RunChangeClock`、模型注册段落点名两个新注册 Row；两仓库新增 `delete_by_thread()` 行与 #7 小节；校正行数/方法数（353→906 行、12→25 方法；220→280 行、9→11 方法） | ✅ |
| 2 | `internals/runtime/README.md` | 新增 sync #7 要点（mutation fence / 删除清理 / 0025） | ✅ |
| 3 | `internals/runtime/01-run-manager.md` | change_seq 段补"删除不 bump clock"与 0025 说明 | ✅ |
| 4 | `internals/runtime/05-run-ownership-and-rollback.md` | 新增"线程操作 reservation 与删除清理"：`operation_kind` 谱系、共享唯一约束、release/lease 语义、DELETE 七步表、**清理 ≠ 防复活**边界 | ✅ |
| 5 | `observability/02-run-events-and-journal.md` | 新增"变更串行域与删除签名"：进程内每线程锁 / PG advisory lock / SQLite / JSONL；owner-scoped 三态删除签名；legacy 第三方实现兼容；seq 归零语义 | ✅ |
| 6 | `operations/app-layer/{00-overview,01-api-reference}.md`、`operations/integration/02-api-reference.md` | DELETE `/api/threads/{id}` 的清理顺序、reservation、owner 解析一次、best-effort 边界 | ✅ |
| 7 | `testing/06-ci-and-automation.md` | 新增 `*-dev` 通配小节 + skill-review-ci 显式钉 `2.1.x-dev` 的例外说明 | ✅ |
| 8 | `frontend/{04-workspace-layout,06-architecture,README}.md` | 嵌套 `SidebarMenu` 的 `w-auto` 宽度约束（#5681/#5682）与可迁移经验；`src/content` 手册（subagents 11 页 / extensions 10 页、`asIndexPage`、锚点迁移） | ✅ |
| 9 | `harness-engineering/01-agent-docs-system.md` | AGENTS 文件数 28（口径说明）；预算实测 14.9/28.4/36.3/41.3 KB；新增"行号漂移"第二案例（root AGENTS 净减 1 行 → 其后所有行号 -1） | ✅ |
| 10 | `harness/08-deerflow-audit.md` | 根 AGENTS 行号引用校正：L221→**L220**、L227-228→**L226-227**、L213→**L47**、L79→**L77**；`##` 数 7→6；深层四份行数 397/379/351/302→397/380/364/302 | ✅ |
| 11 | `internals/harness-hooks/09-packaged-extensions.md` | 贡献类型措辞漂移（4 组 vs 五种，代码契约未变）；run evidence 脱敏口径澄清；新增用户手册路径 | ✅ |
| 12 | `_faq_on_digested/` | 14 处基线标注 `v2.1.0-rc0` → `v2.1.0`（均属"当前基线/行号出处"类）；README 追加 sync #7 说明；历史同步标记全部保留 | ✅ |
| 13 | `_upstream-sync/` | `SYNC.md` 锚点 #7 + 分叉警告 + 改写后的同步流程；`SYNC_LOG.md` #7；本文件 | ✅ |
| 14 | 数字审计 | 全量 grep `rc0` / `769589e8`（107 处）；迁移 0024→0025；行数/方法数/AGENTS 计数逐一实测 | ✅ |

## 数字审计结果

- **rc0 标注**：107 处（`_faq_on_digested` 61 + `_digest` 46）→ 其中 14 处属"断言当前基线"的 (b) 类，改为 `v2.1.0`；93 处为 `🔄 同步 #6` 历史记录或 `🆕/breaking/起` 的引入版本事实，原样保留。
- **行号影响**：FAQ 引用的源码文件与本次实质改动清单**交集为 0**，故行号全部继续有效（只改版本标注）。
- **迁移链**：head `0024_project_documents` → **`0025_repair_run_change_seq`**；ORM 注册表 +`RunChangeClockRow` +`UserPreferenceRow`。
- **仓库行数**：`persistence/run/sql.py` 868→**906**（方法 24→25）；`persistence/feedback/sql.py` 255→**280**（方法 10→11）。
- **AGENTS.md**：仓库内文件名恰为 `AGENTS.md` 者 28 个（另有 `backend/docs/GITHUB_AGENTS.md` 变体）；root **239→238 行**、`extensions/` 379→**380**、`runtime/` 351→**364**、`persistence/migrations/` 166→**167**。
- **CI**：6 个 workflow 改 `*-dev` 通配，`skill-review-ci` 由 `2.0.x-dev` → **`2.1.x-dev`**（不是 `*-dev`）。

## 遗留

- `upstream/main` 的 **189 commits**（2.2 线，最新 `3a862780`）未消化，留待 sync #8；`SYNC.md` 已记录"先判断 tag 与 main 是否分叉"的新流程。
- `_digest/harness/08-deerflow-audit.md` 中其余引用（frontend/AGENTS.md、skills/AGENTS.md 等）本轮未逐一复核行号——本次改动不涉及那些文件，但同类行号脆弱性已在该文档与 `harness-engineering/01-agent-docs-system.md` 中写明。
