---
title: "Skills 与 Tools 系统"
description: "SKILL.md 契约、存储/投影/导出、包摄入与 SkillScan，以及 skills/review 的确定性审查内核。"
type: index
topics: [skills, tools, review, scanner]
---

# Skills 与 Tools 系统

> **定位**：回答「一个 skill 从磁盘文件到进入模型上下文要过几道门」：SKILL.md 格式与 frontmatter 白名单、legacy/deferred 双加载、存储与投影、包摄入扫描，以及 `skills/review/` 的只读审查内核。给写 skill、接 SkillScan 或排查加载失败的人。
> **边界**：不覆盖内置工具全量清单与装配顺序（见 [builtin-tools](../builtin-tools/README.md)），不覆盖 MCP 工具目录与提升机制（见 [internals/mcp](../../internals/mcp/README.md)），skill review 的 CI 豁免与信任边界见 [test-strategy/08-upper-layer-apps.md](../../test-strategy/08-upper-layer-apps.md)。

## 阅读路径

1. **先看**：[skill-md-and-tool-assembly.md](skill-md-and-tool-assembly.md) — 主文档：SKILL.md 契约、双加载、slash 激活、存储/投影与 write gate。
2. **再看**：[skill-package-intake.md](skill-package-intake.md) — 包摄入边界：parser / installer、可执行嗅探与 SkillScan 规则表。
3. **深入**：[skill-review-core.md](skill-review-core.md) — `skills/review/` 的确定性内核：快照、facts、资源图与 readiness 报告。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [skill-md-and-tool-assembly.md](skill-md-and-tool-assembly.md) | SKILL.md 与 frontmatter 白名单、legacy/deferred 双加载、`skill:activate` 与 slash 激活、SkillStorage / projection、`skill_manage` 写入门禁、Tool 系统 | 深入 |
| [skill-package-intake.md](skill-package-intake.md) | `parser.py` / `installer.py` 边界、`.skill` 安装与失败清理、可执行嗅探、静态 + LLM 双层扫描、SkillScan 39 条规则 | 深入 |
| [skill-review-core.md](skill-review-core.md) | readers 快照契约、analyzer 分类与 completeness、资源图、eval manifest、package digest、readiness 与 CLI 退出码 | 深入 |

## 速览

- **双加载**：legacy 与 deferred 并存，deferred 经 `tool_search` 提升；激活要过 `skill:activate` 授权门，request-scoped secrets 随激活注入。
- **slash 激活**：10 个共享保留名，`/context compact` 是唯一例外；与内置命令同名的 skill 不进入注册表。
- **存储与投影**：SkillStorage 用 utf-8-sig 读取、walk 环剪、按名加锁；projection 按策略版本 2 物化，签名细到字节级线程视图，mutation guard 可嵌套。
- **写入门禁**：`skill_manage` 走跨 loop 的 `_SkillLock` + 共享缓存失效标记；`allowed-tools` 已降级为兼容元数据，不再等同于授权。
- **审查分层**：SkillScan 在安装前做静态 + LLM 双层扫描（39 条规则 + 上限常量 + 异常层级）；`skills/review/` 在只读快照上产出确定性 facts、资源图与 readiness 状态。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 2.2 的契约收紧（frontmatter 定界符、BOM、`optional` 必须为布尔）只写在正文，不回填旧结论。

## 相关目录

- [builtin-tools/](../builtin-tools/README.md) — `skill_manage` / `review_skill_package` / `tool_search` 的装载条件。
- [internals/mcp/](../../internals/mcp/README.md) — deferred 工具目录与 MCP 工具的提升机制。
- [test-strategy/](../../test-strategy/README.md) — SkillScan、waiver 与上层应用测试面。
- [concepts/](../README.md) — 概念总览与其它核心抽象。
