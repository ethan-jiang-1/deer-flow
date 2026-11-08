---
title: "skills-tools"
description: "Skills 系统：SKILL.md 契约、存储/投影/导出、SkillScan 与 review core。"
type: index
---

# skills-tools

→ Back to [parent README](../README.md)

| 文件 | 内容 |
|------|------|
| [`skill-md-and-tool-assembly.md`](skill-md-and-tool-assembly.md) | 主文档：SKILL.md 格式与 frontmatter 白名单（含 2.2 定界符收紧/BOM）、legacy/deferred 双加载与 `skill:activate` 授权门、slash 激活（10 个保留名 + `/context compact` 例外）、request-scoped secrets、SkillStorage 存储契约（utf-8-sig / walk 环剪 / 按名锁）、projection 物化契约（策略版本 2、字节级线程视图签名、mutation guard 嵌套）、🆕 `capabilities/` 能力目录与 Gateway 适配、🆕 skill mutation host service 与 migration 0046、🆕 自定义 skill 加载诊断与容器路径注册表、SkillScan 契约、custom skill 导出契约、write gate 与 `skill_manage`（跨 loop `_SkillLock` + 共享缓存失效标记）、allowed-tools 降级为兼容元数据、Tool 系统与故障排查 |
| [`skill-package-intake.md`](skill-package-intake.md) | 包摄入边界：`parser.py` 的 allowed-tools 分词/别名与 required-secrets 降级规则（2.2 起 `optional` 必须为布尔）、`installer.py` 的 `.skill` 安装链路与失败清理（`app_config` 透传扫描器）、可执行 magic 前导填充嗅探与 21 个代码后缀、静态 + LLM 双层扫描的决策契约、SkillScan 全量 39 条规则表 + 上限常量 + 异常层级 + 调用面 |
| [`skill-review-core.md`](skill-review-core.md) | `skills/review/` 确定性审查内核：readers 快照契约与 limits、analyzer 的 rule_id/severity 分类与 completeness、资源图、eval manifest 形态、package digest、readiness 状态机与报告字段、CLI 退出码 |
