---
title: "上游同步"
description: "追踪与 bytedance/deer-flow 上游的同步关系。锚点 commit + diff = 更新 digest 的源头。"
type: index
topics: [upstream-sync, release-anchor, digest]
---

# 上游同步

> **定位**：追踪 `ethan` 与 bytedance/deer-flow 上游的同步关系，回答「当前消化的是哪个上游版本、下次怎么同步、这轮改了什么」；给维护 digest 的人看。当前锚点 #8 / v2.2.0（`58fc5bd5b`，2026-11-08 同步）。
> **边界**：只记锚点、同步流程与更新计划，不重复 digest 正文；`ethan` 只在三个目录上区别于上游（`_digested/`、`_faq_on_digested/`、`_deerflow_application_agent_ready_development/`），同步是**重建**而非 merge（完整命令见 [SYNC.md](SYNC.md)）。

## 阅读路径

1. **先看**：[SYNC.md](SYNC.md) — 当前锚点、同步铁律、上游变更 → digest 影响速查表。
2. **再看**：[SYNC_LOG.md](SYNC_LOG.md) — 每次同步的流水账；#8 是 v2.1.0 → v2.2.0，1,239 commits。
3. **深入**：[UPDATE_PLAN_8.md](UPDATE_PLAN_8.md) — 最新一轮的测绘结果、分域清单、执行顺序与验收标准。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [SYNC.md](SYNC.md) | 当前锚点、重建流程、上游变更影响速查 | 概览 |
| [SYNC_LOG.md](SYNC_LOG.md) | 每轮同步的时间、锚点变化、变更摘要与 digest 更新 | 概览 |
| [UPDATE_PLAN.md](UPDATE_PLAN.md) | #1 计划：`162fb214` → `4915b5e`（323 commits） | 深入 |
| [UPDATE_PLAN_3.md](UPDATE_PLAN_3.md) | #3 计划：`4915b5e` → `cd34a1a5`（200 commits） | 深入 |
| [UPDATE_PLAN_4.md](UPDATE_PLAN_4.md) | #4 计划：`cd34a1a5` → `e5c62cab`（234 commits） | 深入 |
| [UPDATE_PLAN_5.md](UPDATE_PLAN_5.md) | #5 计划：`e5c62cab` → `431892e1`（108 commits） | 深入 |
| [UPDATE_PLAN_6.md](UPDATE_PLAN_6.md) | #6 计划：`431892e1` → v2.1.0-rc0 `769589e8`（304 commits） | 深入 |
| [UPDATE_PLAN_7.md](UPDATE_PLAN_7.md) | #7 计划：v2.1.0-rc0 → v2.1.0 `345f08be`（10 commits） | 深入 |
| [UPDATE_PLAN_8.md](UPDATE_PLAN_8.md) | #8 计划：v2.1.0 → v2.2.0，含机械层基线与验收判据 | 深入 |

## 宪章与约定

- 同步宪章：[SYNC.md](SYNC.md)（流程与铁律）、[SYNC_LOG.md](SYNC_LOG.md)（流水）、[UPDATE_PLAN.md](UPDATE_PLAN.md)（计划体例与首轮基线）。
- 历史计划归档：[UPDATE_PLAN_8.md](UPDATE_PLAN_8.md)（最新一轮）与 [UPDATE_PLAN_7.md](UPDATE_PLAN_7.md)（rc0 → v2.1.0）代表最近两轮；更早的 _3–_6 见上表。
- 机械校验：`tools/check_digest.py`（[tools/README.md](tools/README.md)）只做可证伪对账；语义层仍靠读源码。

## 相关目录

- [../README.md](../README.md) — 根索引，含三条分支纪律与研究内容分流。
- [tools/README.md](tools/README.md) — 同步的机械层：digest 一致性校验器。
