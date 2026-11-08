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
migrations（数字前缀 ≠ 链顺序；按 down_revision 实际串法，head = 0025_repair_run_change_seq）:
  0019_projects → 0020_threads_meta_project_id → 0021_batch_acceptance
  → 0019_thread_incarnations → 0022_scheduled_occurrence_seq → 0023_run_change_seq
  → 0023_user_preferences → 0024_project_documents → 0025_repair_run_change_seq
  本子系统自己的两个建表 revision 是 0019_projects 与 0024_project_documents；
  0020_threads_meta_project_id 只加可空 threads_meta.project_id 列 + ix_threads_meta_project_id，
  故意不加外键（删项目时先清成员）
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
- **Trash**：restore 是数据库重指向（`stored_relpath` 相对 `users/{user_id}/projects/`，是内嵌 `sha256` 与行 `id` 的内容地址，**文件永不移动**，§10.6）；purge 在仓储的持续行锁事务内 unlink 原件 + `derived/converted.md`；`trash_retention_days`（默认 30）清扫兜底。`project_documents` 无 `project_id` 外键、无 `mime`/`is_text`/`version`/`deleted_by` 列（Phase-2 spec §6.1）

## `trash.py` — 保留期清扫 / purge 钩子 / 恢复

- **触发方式**：lazy（`GET /api/trash/documents`，作用于调用者本人）+ Gateway 启动一次（`user_id=None` ⇒ 遍历所有用户）；**无 daemon、无 scheduler**（`trash.py:281-289`）。
- `make_purge_file_remover(paths, *, user_id)` 返回 `remove_files` hook，在 purge 事务内**持续持有 document 行锁**时运行；`user_id=None`（startup sweep）逐行解析 owner（`trash.py:73-84`）。
- unlink 语义：删 `original` + `derived/converted.md`；`FileNotFoundError` 视为已删除；**其它 unlink 错误向上抛 → purge 事务回滚，该 trashed 行保持可重试**（`trash.py:53-71`）。空父目录 best-effort rmdir，但不删 `documents/` 本身。
- `run_trash_retention_sweep(..., now=None, include_reconciliation=True) -> SweepReport`：
  - expired 行走**与手动 purge 相同的 guarded purge**，并在锁内用 `retention_cutoff` + `expected_trashed_at` 复核：先 restore 再重新 trash 的行不会按旧到期时间被清（`trash.py:307-319`）；
  - 单行 purge 失败 → `purge_failures += 1` 后继续，不中断整轮（`trash.py:320-327`）；
  - `include_reconciliation=False` 跳过 O(rows + files) 的 row/storage 对账，让高频 lazy 触发保持廉价；保留期保证（到期行可被 purge）不受影响（`trash.py:290-306`）；
  - `_ORPHAN_GUARD = 24h`：**任何更年轻的东西永不回收/永不标记**，扫不到 in-flight 上传或刚写入的行（`trash.py:41-43`）；
  - storage 对账只删 `.staging/*` 与超过 24h 的**无引用**文件；被任何行（active 或 trashed，含 restore 后已重指向的行）引用的 namespace 整体受保护（`trash.py:172-245`）；
  - row 对账只 detect、**永不 delete**：超过 guard 且 original 缺失/size 不匹配的行进 `SweepReport.content_missing`（行是用户对文档的唯一记录，处置必须由用户先移入 trash）（`trash.py:259-278`）；
  - `SweepReport{purged, purge_failures, orphans_removed, staging_removed, content_missing[]}`（`trash.py:161-169`）。
- `restore_document(repo, paths, ...) -> (outcome, row)`：薄编排——只读 probe 记录被丢弃的 namespace，正确性检查全在仓储锁事务内（`check_document_content` 作为 `check_content` 传入）；`outcome == "merged"` 时 post-commit 删被丢弃 namespace，**best-effort**（失败 log + 交给 sweep）；返回值原样透传仓储的 `(outcome, row)`（`trash.py:98-132`）。
- `purge_all_trashed(repo, paths, *, user_id) -> int`（清空回收站）：**与年龄无关**（用户已确认要删的就是这些）；每行走同一 guarded purge，restore 赢了竞争的返回 `False` 被跳过；行之间**非原子**——某行 unlink 失败会回滚该行并向上抛，尚未访问的行保持 trashed 可重试（`trash.py:135-158`）。

## `documents.py` — shelf 落盘 / 转换 / 读取分类

- `validate_shelf_filename`：显示文件名独占一个路径分量（无 hash 前后缀），必须是裸的非空文件名；**拒绝**路径分隔符（不是剥离）、`.`/`..`、>255 UTF-8 字节；`ValueError ⇒ 400`（`documents.py:53-70`）。
- `shelf_relpath(project_id, sha256, document_id)` = `{project_id}/documents/{sha256[:2]}/{sha256}/{document_id}`（相对 `users/{user_id}/projects/`）；`stored_relpath` 内嵌内容 hash + 行自身 id，**行之间永不共享字节**，trash 后重传落在全新 namespace（`documents.py:73-75`）。
- `stage_document_bytes`：分块写入 `.staging/{uuid}` 并累计 sha256；`max_bytes` 复用 `uploads.max_file_size`（shelf 不新增同义 knob）；超限抛 `ShelfUploadTooLargeError`（route → 413）且**不留 staging 文件**（`documents.py:148-184`）。
- `add_staged_document`：**file-before-row**——在仓储单一事务（active project 行锁 → dedup select → insert）内把 staged 字节原子 rename 进该文档独占 namespace，之后行才存在；dedup 命中返回既有行 `(row, created=False)`（**第一个写入者的 name/provenance 胜出**，staged 副本丢弃）；project 缺失/外来/archived 返回 `None`（route → 404）（`documents.py:206-299`）。
- **插入抛错后的清理规则**：`insert_active` 自己 commit，失败可能发生在 **commit 之后**（尾随 refresh）——因此只有**可证明行不存在**时才删 namespace；probe 包含 trashed 行（trash 可恢复，删字节会毁掉可恢复文档）；行 live → 视为成功返回；liveness 无法判定 → 留给 reference-aware sweep（`documents.py:252-290`）。
- **转换（lazy，仅首次读）**：要求 `uploads.auto_convert_documents`；扩展名不在 `CONVERTIBLE_EXTENSIONS` → `"binary"`；已有 `derived/converted.md` → 直接返回。转换在**文档行锁内**执行，且锁后**重新校验** ownership/shelf membership/active 状态——先提交的 trash/purge 会让它按 `content_missing` 拒绝且不发布任何内容；temp file + 原子 `os.replace` 的发布也留在锁内，读者永远只看到完整的 `converted.md` 或什么都没有（`documents.py:335-372`）。
- `read_text_serving_path` 的分类顺序（决定三个拒绝 reason）：先做**共享内容完整性检查**（存在 + size 匹配 → `content_missing`），再看 derived；**可转换扩展名优先于文本启发式**（无 NUL 头的 ASCII85 PDF 绝不能当文本裸送）；真正的文本扩展名走采样头启发式（没有 `mime`/`is_text` 列是设计，§6.1）；否则 `binary`（`documents.py:375-403`）。
- 文本读取：`read_document_text_window` 用增量 UTF-8 解码（replacement-tolerant、跨 chunk 拆分的多字节序列安全）只解码 `[offset, offset+limit)` 所需部分，**不物化整串**；字符总数按 `(document_id, sha256)` 内容身份缓存在进程本地 256 项 LRU（行不可变、id 不复用 ⇒ purge 只产生孤儿条目，无需失效钩子）（`documents.py:406-477`）。
- `stage_document_copy_for_attach`：在**行锁内**把 live 文档的 original 拷到 `.staging/attach-{uuid}`，**锁在 caller 做 sandbox 分配/网络同步之前释放**；缺失/size 不一致抛 `ShelfContentMissingError`（→409）；`None`（缺失/外来/trashed/不在本 shelf）→404；staging 文件由 caller 负责 unlink（崩溃遗留由 sweep 的 24h guard 收）（`documents.py:518-567`）。
- `auto_convert_documents_enabled`：镜像 uploads router 的读法——畸形值**降级为 false 而非崩**，YAML 字符串布尔（`"1"/"true"/"yes"/"on"`）被识别（`documents.py:480-493`）。

## `tools.py` — 两个 shelf 工具的返回契约

只读工具 `list_project_documents` / `read_project_document`（`get_project_document_tools()`），注册条件是 run 携带 pinned `PROJECT_CONTEXT_KEY`；**subagent 永不获得**（`tools.py:1-16`）。

- **fail closed 而非空成功**：无 pinned project / 无 session factory → 明确的 JSON `error`（`_NO_PROJECT_CONTEXT_MESSAGE` / `_NO_STORE_MESSAGE`）；store 不可用绝不返回空列表（`tools.py:53-70`）。
- 工具从 pinned 快照取 `project_id`，但读的是 **live 行**：`read_project_document` 在 `repo.get(document_id)` 后要求 `row.project_id == pinned project_id`，否则统一返回"no longer on the shelf"（trashed/purged/外来/跨项目都归这一条）——**不服务过期内容、不跨项目读**（`tools.py:121-131`）。
- clamp：list `limit` ∈ [1,200]（默认 50）、`offset` ≥ 0 且上界 `1<<62`，返回 `{total, offset, next_offset, documents[]}`，仅在未取满时 `next_offset` 为 `None`；read `limit` ∈ [1,20000]（默认 8000），返回 `{name,total_chars,offset,returned_chars,truncated,content}`；`offset >= total_chars` 的越界页**不读任何字节**（`tools.py:36-39,83-88,100-158`）。
- 拒绝文案三分：`content_missing` / `conversion_disabled` / `binary`（后者引导 `attach-to-thread`），与 serving 分类一一对应（`tools.py:41-46,134-140`）。
- shelf 条目 name 与读出的 name 都过 `neutralize_untrusted_tags`；id 是服务端生成的内容地址，原样渲染以便直接喂回 `read_project_document`（同名文档靠 id 区分）（`tools.py:91-97,150`）。

## `context.py` — pin-then-render 的边界补充

- 只有 `status ∈ {active, archived}` 的项目可解析（archived 成员仍收 instructions + 只读 shelf）；其它情况 warn 后按 unassigned 处理；**membership 永不在这里写入**（`context.py:31-32,82-87`）。
- shelf 快照：`shelf_index_max_entries + 1` 行、`updated_at DESC, id ASC`、来自一次一致读；多出的一行只用于判断截断、**永不渲染**；工具随后读 live 行，允许与本次快照不同（`context.py:50-108`）。
- `<project>` 块：pinned `id`/`name` 恒带；instructions 过 `neutralize_untrusted_tags` 以防提前闭合 `</project>`；属性值转义 `&"<>`；instructions 为空只省略正文、保留身份（`context.py:132-152`）。
- `<documents>` 块：整个块（header/closing/entry/overflow note，含 id 与转义后的名字）都计入 UTF-8 字节上限；从 `len(lines)` 递减尝试直到放得下，**绝不发半行**；header 报精确的 `count`（shelf 总数）与 `shown`；被截断时必带可行动提示（"call list_project_documents"）；同一快照 + 上限恒渲染同一文本——这正是 journal `project_shelf_revision` 指纹哈希的内容（`context.py:155-241`）。
- 瞬态消息识别是**三重**的：保留 ID 前缀 + 服务端 marker + 本 producer 的 provenance（`ContentKind.MIDDLEWARE_INJECTION` / `dynamic_context_project`），因此用户消息绝不会因文本或 ID 前缀匹配被移除，伪造的 marker/ID 对也无法压制真块（admission 本就会剥离它们）（`context.py:38-47,244-281`）。
- 插入位置：优先"真正的本 run 用户消息之前"，用服务端 pre-run message-ID 集合识别（而不是"最后一个 HumanMessage"），对 run 内 tool loop 与 post-compaction 请求都稳定；没有保留 anchor 的 resumed/internal run 退回 leading SystemMessages 之后（`context.py:284-325`）。
- 解析失败（DB 错误 / thread 行不存在 / 仓储不可用）**只 warn、绝不 fail run**——组织性故障而非授权故障（`context.py:109-115`）。

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
