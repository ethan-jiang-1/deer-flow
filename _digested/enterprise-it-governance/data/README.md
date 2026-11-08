---
title: "数据治理"
description: "数据放哪、谁能看、留多久、删得掉吗——合规评审绕不开的四问。"
type: index
topics: [governance, data, retention, pii]
---

# 数据治理

> **定位**：回答数据治理的四问——放哪、谁能看、留多久、删得掉吗。per-user 物理隔离是基础，企业真正会追问的是凭据怎么加密、丢了会怎样、PII 有没有主动扫描、保留期在哪配、知识库数据驻留在哪里。给合规评审与数据平台负责人看。
> **边界**：账号与用户身份见 [identity/](../identity/README.md)；条款映射见 [compliance/](../compliance/README.md)；备份与恢复的操作步骤见 [enterprise-operations/backup-and-monitoring.md](../../enterprise-operations/backup-and-monitoring.md)。

## 阅读路径

1. **先看**：[01-storage-and-isolation.md](01-storage-and-isolation.md) — 目录布局、`USER.md`、per-user skills 与隔离边界。
2. **再看**：[04-credentials.md](04-credentials.md) — 凭据加密、轮换与丢失后果。
3. **深入**：[06-retention-and-residency.md](06-retention-and-residency.md) — `trash_retention_days`、blob 与 knowledge 的保留期和驻留。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [01-storage-and-isolation.md](01-storage-and-isolation.md) | 数据存储与隔离：目录布局、USER.md、per-user skills | 概览 |
| [02-redaction.md](02-redaction.md) | 输出与错误脱敏：host 路径替换回虚拟路径 | 深入 |
| [03-upload-and-scanning.md](03-upload-and-scanning.md) | 文件上传控制矩阵与 Skills 安全扫描 | 深入 |
| [04-credentials.md](04-credentials.md) | 凭证管理：加密、轮换、丢失后果 | 深入 |
| [05-pii-redaction.md](05-pii-redaction.md) | PII 脱敏：默认关闭与 fail-open 边界 | 深入 |
| [06-retention-and-residency.md](06-retention-and-residency.md) | 保留期与数据驻留：trash、blob、knowledge | 概览 |

## 宪章与约定

- 本目录无独立宪章；父级卷宪章为 [../PLAN.md](../PLAN.md)。
- 写作纪律沿用 [根 README](../../README.md)：判断性段落附 `file:line`，基线 v2.2.0。
- 阅读约定：缺口按「无 / 有但不覆盖 / 部分闭合」三态标注，每处写明边界条件。

## 相关目录

- [企业 IT 治理总览](../README.md) — 八个治理面向与默认关闭项。
- [身份与接入](../identity/README.md) — per-user 隔离所依赖的身份解析。
- [合规对照](../compliance/README.md) — 数据主体权利与跨境传输怎么对上条款。
- [Enterprise Operations](../../enterprise-operations/README.md) — 备份、恢复与存储配置的操作面。
