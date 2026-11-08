---
title: "文件上传与 Skills 扫描"
description: "上传安全控制矩阵、Skills 安全扫描。"
topics: [governance, data]
---

# 文件上传与 Skills 扫描

上传安全控制矩阵、Skills 安全扫描。

### 文件上传安全

| 控制 | 实现 |
|------|------|
| **类型白名单** | PDF, PPT, Excel, Word → 通过 `markitdown` 转换 |
| **目录拒绝** | 拒绝上传路径中包含目录的请求 |
| **去重** | 同名文件自动 `_N` 后缀去重 |
| **转换隔离** | 文档转换复用单个 worker |

### Skills 安全扫描

`deerflow/skills/security_scanner.py` — Agent 写 skill 文件时，先经过 LLM-based 安全检查再持久化。这是 defense-in-depth 的一环——防止 agent 生成恶意 skill 文件。

### 数据保留

当前无自动数据保留/清理策略。Thread 删除（`DELETE /api/threads/{id}`）会清理 LangGraph thread + 本地 thread 目录。Memory 没有自动过期机制。

