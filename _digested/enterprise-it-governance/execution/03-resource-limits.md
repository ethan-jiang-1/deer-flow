---
title: "资源管控与隔离"
description: "CPU/内存/磁盘限制，per-thread 隔离。"
topics: [governance, execution]
---

# 资源管控与隔离

CPU/内存/磁盘限制，per-thread 隔离。

## 资源管控

| 资源 | 限制 | 位置 |
|------|------|------|
| **Sandbox 实例数** | Local: LRU cache 256 个 per-thread sandbox | `sandbox/local/` |
| **bash 输出** | middle truncation 20,000 字符 | `tools.py` |
| **read_file 输出** | head 50,000 字符 | `tools.py` |
| **ls 输出** | head 20,000 字符 | `tools.py` |
| **命令长度** | 拒绝 >10,000 字符的 bash 命令 | `sandbox_audit_middleware.py` |
| **null byte** | 拒绝含 null byte 的命令 | `sandbox_audit_middleware.py` |

## Per-Thread 隔离

每个 thread 有自己的 sandbox 实例。在 Local 模式下：

```
thread_1 → sandbox_id="local:thread_1" → workspace at users/alice/threads/t1/workspace
thread_2 → sandbox_id="local:thread_2" → workspace at users/alice/threads/t2/workspace
```

两个 thread 之间无法通过 sandbox 读写对方的文件。文件操作锁 `(sandbox_id, path)` 粒度确保同一 sandbox 内并发写同一文件时有互斥。

