---
title: "Projects — 项目工作区"
description: "v2.1.0-rc0 全新子系统：把 threads 组织进项目，注入 instructions 与 document shelf。"
topics: [projects, threads, context]
---

# Projects — 项目工作区（v2.1.0-rc0 🆕）

**一句话**：用户项目把 threads 按名字 + 自由格式 instructions 分组；成员线程在每次 run 时收到 request-scoped 的 `<project>` 块与有界 `<documents>` shelf 索引——**不进 system prompt、不进持久历史**。

分两个 Phase 落地：

| Phase | commit | 内容 |
|-------|--------|------|
| MVP Phase 1 | `5951c89b` (#5265) | 项目工作区：scoped chats + thread membership |
| MVP Phase 2 | `a58ab484` (#5443) | instructions、document shelf、promotion、trash |

## 代码地图

```
backend/packages/harness/deerflow/projects/
├── context.py     # run-start 解析钉快照 + 纯渲染（<project>/<documents> 块）
├── documents.py   # shelf 文档：staging 上传、路径解析、SHA-256 完整性
├── tools.py       # 2 个只读 shelf 工具（经 pinned 身份查 live 行）
└── trash.py       # 回收站：restore（DB 重指向）/ purge（行锁 unlink）/ 保留期清扫

backend/packages/harness/deerflow/persistence/projects/   # model + sql
backend/app/gateway/routers/projects.py                   # /api/projects CRUD
backend/app/gateway/routers/project_documents.py          # shelf CRUD + promotion
backend/app/gateway/routers/project_thread_files.py
backend/app/gateway/routers/trash.py                      # /api/trash
migrations: 0019_projects / 0019_thread_incarnations / 0020_threads_meta_project_id / 0024_project_documents
```

## 核心机制：pin-then-render

```
run admission
  └─ resolve_project_context()  一次异步解析（§7.1）
       ├─ threads_meta.project_id → project 行（owner-scoped，ContextVar 取用户）
       └─ 有界 shelf 快照：active 计数 + 前 N+1 行（updated_at DESC，id ASC）
            （多读一行只为判断截断，永不渲染）
  └─ 快照钉到 runtime context 的 PROJECT_CONTEXT_KEY
model request 组装（DynamicContextMiddleware）
  └─ 纯渲染（§7.2）：零 DB/文件 IO、零 memory 依赖、零历史比对
       └─ transient user message（marker + provenance 双重识别）插入请求
```

| 语义 | 说明 |
|------|------|
| **latest-only** | 每次 run 渲染当次快照；旧内容不进持久历史，下次 run 自然刷新 |
| **钉身份不钉数据** | 快照固定"哪个项目"；shelf 工具运行时查 **live 行**——文档被删报 "no longer on the shelf" 错误而非过期内容 |
| **fail-open** | 解析失败只 warn 不 fail run——这是组织性故障不是授权故障 |
| **归档保留** | `archived` 项目成员仍收 instructions + 只读 shelf（§7.1） |

## 上下文注入边界

- `<project>` 块：pinned `id`/`name` 恒带；instructions 经 `neutralize_untrusted_tags` 处理后渲染
- `<documents>` 索引（仅 shelf 非空）：受 `shelf_index_max_entries`（1-500，默认 50）+ `shelf_index_max_bytes`（512-65536，默认 4096）双界——CJK 文档名下字节界通常先触顶
- instructions 超限**写入时 422 拒绝**，从不静默截断（UTF-8 字节计，`instructions_max_bytes` 默认 8192）
- 渲染事件记录 `project_context_revision` / `project_shelf_revision`（渲染块 sha256 指纹）
- prompt.md 告知模型：request 中的 `<project>` 块是唯一生效来源，历史里提到的旧设置一律忽略

## Shelf 工具（只读）

两个工具注册条件 = run 带有 pinned `PROJECT_CONTEXT_KEY`（§10.11）：

- 非项目 run 不支付 schema token、看不到工具
- 项目 run 即使 instructions/shelf 全空也保留（保证一致性）
- 调用时读 pinned key + `resolve_runtime_user_id`，缺失即工具错误（fail closed）
- shelf 是**用户策展**的——没有 agent 发起的 shelf 写入（§7.3）

## Document Shelf 与 Trash

- 上传走有界 staging（`stage_document_bytes`，超限 `ShelfUploadTooLargeError`），SHA-256 完整性检查
- **Promotion**：`POST /documents/from-thread` 把线程产物晋升为 shelf 文档；`attach-to-thread` 反向附加
- **Trash**：restore 是数据库重指向（`stored_relpath` 为 projects-root 相对，**文件永不移动**，§10.6）；purge 在仓储的持续行锁事务内 unlink 原件 + `derived/converted.md`；`trash_retention_days`（默认 30）清扫兜底

## 配置（`config.yaml -> projects:`）

```yaml
projects:
  instructions_max_bytes: 8192     # 256-262144，UTF-8 字节
  shelf_index_max_entries: 50      # 1-500
  shelf_index_max_bytes: 4096      # 512-65536
  trash_retention_days: 30         # 1-3650
```

## 设计文档

`docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md`（606 行，含 §7 上下文 / §8 trash / §10-12 安全与边界）。上下文注入对 lead-agent 侧的影响见 [lead-agent/factory-and-threadstate.md](../lead-agent/factory-and-threadstate.md)；Gateway 路由见 [operations/app-layer](../../operations/app-layer/00-overview.md)。
