---
title: "数据治理"
description: "数据放哪、谁能看、留多久、删得掉吗——合规评审绕不开的四问。"
type: index
topics: [governance]
---

# 数据治理

数据放哪、谁能看、留多久、删得掉吗——合规评审绕不开的四问。

per-user 物理隔离是基础，但企业真正会追问的是：凭据怎么加密、丢了会怎样、PII 有没有主动扫描、保留期在哪配、知识库数据驻留在哪里。这些问题的答案分散在不同模块。

> **约束：不修改项目源代码。** 本 `_digested/` 下所有内容仅作研究记录。详见 [根 README](../../README.md)。

## 本篇目

| 文件 | 主题 | 内容 |
|------|------|------|
| [01-storage-and-isolation.md](01-storage-and-isolation.md) | **数据存储与隔离** | 目录布局、USER.md、per-user skills |
| [02-redaction.md](02-redaction.md) | **输出与错误脱敏** | host 路径替换回虚拟路径 |
| [03-upload-and-scanning.md](03-upload-and-scanning.md) | **文件上传与 Skills 扫描** | 上传控制矩阵、Skills 安全扫描 |
| [04-credentials.md](04-credentials.md) | **凭证管理** | 加密、轮换、丢失后果 |

## 规划中

| 文件 | 主题 | 内容 |
|------|------|------|
| 05-pii-redaction.md | PII 脱敏 | pii_redaction_middleware |
| 06-retention-and-residency.md | 保留期与数据驻留 | trash_retention_days、blob、knowledge |

---

← 返回 [企业 IT 治理总览](../README.md) · 机制细节见 [enterprise-operations/](../../enterprise-operations/README.md)
