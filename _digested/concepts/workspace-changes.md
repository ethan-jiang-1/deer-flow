---
title: "Workspace Changes — Agent 文件改动追踪"
description: "记录 agent 每次 run 对 workspace/outputs 目录的文件改动，支持 diff 审查。"
topics: [workspace, changes, diff, artifacts, frontend]
---

# Workspace Changes — Agent 文件改动追踪

> 同步 #4（e5c62cab）全新子系统。回答："这个 agent 运行到底改了我的哪些文件？"

## 定位

`packages/harness/deerflow/workspace_changes/` 记录每个 run 前后对 thread 拥有的 `workspace` + `outputs` 目录的文件改动，并在前端展示为"change review"卡片。

## 模块结构（6 文件）

| 文件 | 职责 |
|------|------|
| `types.py` | 数据类型（change 分类、diff 元数据） |
| `scanner.py` | 目录快照扫描 + 变更检测 |
| `diff.py` | 文本 diff 生成（大小受限） |
| `recorder.py` | 快照文本缓存生命周期（roots 解析、mkdtemp、rmtree offload） |
| `api.py` | 外部 API 入口 |
| `__init__.py` | 包导出 |

## 工作机制

```
run 开始前 → pre-run 快照（workspace + outputs）
run 结束后 → post-run 快照 → 对比 → 有变化则写 workspace_changes event (category=workspace)
```

- **扫描 offload**：`runtime/runs/worker.py` 用 `asyncio.to_thread` 执行文件系统扫描，不阻塞 event loop（blocking-io 锚点：`test_workspace_changes_recorder.py`）
- **Uploads 排除**：上传目录不计入改动
- **Text diff 受限**：文本 diff 有大小上限；二进制/大文件/敏感路径只持久化 metadata（不存全文）
- **内部 process-feedback 排除**：`EXCLUDED_DIR_NAMES` 排除 `BROWSER_FRAMES_DIRNAME`（浏览器瞬时截图）和 `TOOL_RESULTS_DIRNAME`（tool-output budget 中间件的外部化子目录）——这些是进程反馈，不是 agent 产出的 artifact
- **delivery receipt 联动**：run 交付验证用同一快照推导候选 artifact（见 [runtime/05-run-ownership-and-rollback.md](../internals/runtime/05-run-ownership-and-rollback.md)）

## API 与前端

- **Gateway 端点**：`GET /api/threads/{id}/runs/{rid}/workspace-changes` — 文件改动摘要 + 可选 diffs
- **前端**：每个 run 渲染一张 workspace-change 卡片（`fix: render one workspace-change card per run` #4559）

## 分类语义

- 符号链接替换文件 vs 删除是**不同分类**（`fix(workspace-changes): classify a symlink replacing a file distinctly from deleted` #4170）

## 数据模型与上限（`types.py`）

- 状态机：`WorkspaceChangeStatus = created | modified | deleted | symlink_created`；不可用原因 `DiffUnavailableReason = binary | large | sensitive | truncated | symlink`（`types.py:14-15`）。
- `WorkspaceChangeLimits`（不可变默认值，`types.py:18-27`）：`max_files=200`（结果最多列出的 change 数）、`max_scanned_files=2000`（扫描上限，超出即 `truncated`）、`max_file_bytes_for_diff=256 KiB`（超过则不 sha256、不读文本，reason=`large`）、`max_total_diff_bytes=1 MiB`（整次结果的 diff 总预算）。
- `FileSnapshot`/`WorkspaceFileChange` 的关键不变量：**只有 size ≤ limit 的文件才有 sha256**；`text`/`text_path` 二选一（给了缓存目录就写文件，否则内联）；sensitive/binary/large/symlink 都通过 `content_unavailable_reason` 标注（`types.py:40-85`）。
- `WorkspaceChangeSummary` 六项计数 + `truncated`；`WorkspaceChangeResult.has_changes()` 把 additions/deletions 也算"有变化"（文件计数为 0 但行数变化也不会漏记）；`to_dict()` 固定 `version: 1`（`types.py:87-117`）。

## 快照扫描契约（`scanner.py`）

- `EXCLUDED_DIR_NAMES` 是**进程反馈 vs 用户产物**的边界：`.git/.hg/.svn/.cache`、`MCP_INTERNAL_DIRNAME`（stdio MCP 子进程的临时/调试文件）、`.next/.venv/__pycache__/build/dist/node_modules`，外加共享常量 `BROWSER_FRAMES_DIRNAME`（浏览器瞬时进度截图）与 `TOOL_RESULTS_DIRNAME`（tool-output budget 中间件外部化目录）。后两者不排除的话，只外部化一次 tool 输出就会让交付验证报"产出未呈现"而整轮失败。**自定义 `tool_output.storage_subdir` 只能经 `extra_excluded_dir_names` 传入**，且必须是单段目录名（`os.walk` 每层只给单段，`cache/tool-results` 这类嵌套值永远匹配不上；ToolOutputConfig 强制单段契约）（`scanner.py:19-46,117-129`）。
- 敏感路径：`is_sensitive_workspace_path(path)` 大小写折叠后按 basename / 整路径 / **任一路径段**逐一 `fnmatch` 匹配 `SENSITIVE_PATH_PATTERNS`（`.env`、`.env.*`、`*api_key*`、`*apikey*`、`*.key`、`*.pem`、`*credential*`、`*password*`、`*private_key*`、`*secret*`、`*token*`）；命中即 metadata-only：**不读内容、不算 sha256**，reason=`sensitive`（`scanner.py:80-107,198-213`）。
- **符号链接永不跟随**：目录 walk `followlinks=False` 且跳过 symlink 目录；symlink 文件用 `lstat()` 记 metadata、`readlink()` 记目标，绝不 stat/读取目标（目标可指向宿主任意位置），reason=`symlink`、`sha256=None`。Windows 上 `_normalize_symlink_target` 去掉扩展长度前缀（仅 drive-letter 形式；`\\?\UNC\` 转普通 UNC；volume-GUID/device 路径保持原样；POSIX 完全不动——反斜杠在 Linux 是合法文件名字节）（`scanner.py:138-160,262-323`）。
- 分类顺序是**敏感 → 二进制 → 过大 → 才读文本**：二进制 = 扩展名清单（图片/Office/压缩/视频等）或采样判定（含 NUL 即二进制；UTF-16 BOM 且可解码则不算；UTF-8 可解码则不算，否则算）；sha256 仅当 size ≤ 256 KiB；文本解码接受 `utf-8-sig`/`utf-8`/带 BOM 的 `utf-16`；文本缓存在调用方给的 `mkdtemp` 目录，文件名是 `sha256(virtual_path)`（`scanner.py:48-95,215-259,326-378`）。
- `max_scanned_files` 到顶立即返回当前快照并置 `truncated=True`——**扫描截断是结果级信号，不是错误**（`scanner.py:140-147`）。

## 差异与 diff 契约（`diff.py`）

- `compare_snapshots` 遍历两份快照的路径并集；**相同判定**优先 sha256（双方都有时），否则 `(size, mtime_ns)`——没算 sha256 的大文件也能识别"改了"（`diff.py:24,142-145`）。
- 状态判定顺序：`after` 是 symlink 而 `before` 不是 → `symlink_created`（含"symlink 替换普通文件"：路径仍存活只是形态变了，绝不能报 deleted）；`before` 缺 → `created`；`after` 缺 → `deleted`；否则 `modified`（`diff.py:122-139`）。
- 结果截断：超过 `max_files` 的 change 仍计入 summary，但不再进 `files` 并置 `truncated=True`；diff 超预算（`remaining_bytes`）时 **diff 置空** + `diff_unavailable_reason="truncated"` + `diff_truncated=True`，additions/deletions 仍保留（`diff.py:46-84,167-180`）。
- additions/deletions 逐行计数时**按位置跳过 unified diff 的前两行文件头**（不能用前缀判断：`-- get users` 这类内容行会以 `--- ` 开头而被误丢）（`diff.py:208-221`）。
- `get_changed_output_paths` 只返回 `root == "outputs"` 的**非 symlink** 已创建/已修改文件，供 run 交付验证推导候选 artifact（`diff.py:112-119`）。

## 两阶段扫描与取消（`recorder.py`）

- `capture_workspace_snapshot` 在 worker 里解析 thread 的 `workspace` + `outputs` 根并 `mkdtemp` 文本缓存；**after 扫描是两阶段的**：先用 `include_text=False` 的 metadata 扫描 + `get_changed_paths` 求出变化集合，再只对 `text_paths=changed_paths` 做 `include_text=True` 的文本扫描——未变化文件绝不读内容（`recorder.py:43-49,189-217`）。
- `record_workspace_changes` 只在 `has_changes()` 时写 event，否则返回 `None`；event `content` 是 `"{n} files changed +{additions} -{deletions}"`，payload 放在 `metadata[WORKSPACE_CHANGES_METADATA_KEY]`；`finally` 删除 before 快照的文本缓存（`recorder.py:218-239`）。
- **取消语义**（核对：本节此前在 digest 中缺失，此处补上）：
  - `_prepare_capture` 的 handoff 被 shield，取消若发生在 `mkdtemp` 之后、拿到路径之前，孤儿目录不能丢——回收放在独立 task（`_reclaim_prepare_and_cleanup`）里，重复取消只能打断 `await`、打不断 task，必须排空到清理完成再重新抛出（`recorder.py:64-77,134-154`）。
  - **文本扫描必须排空**：worker 可能仍在读写文本缓存，立即删除会与扫描竞争；`_drain_scan_and_cleanup` 用 shield 循环等 scan 结束，`_consume_cancelled_scan_outcome` 消费/记录晚到的失败（避免未取回异常告警），然后才删缓存（`recorder.py:93-124,168-182`）。
  - **metadata 扫描（`include_text=False`）没有缓存资源要保护**：立刻取消、让 worker 继续跑，用 done callback 消费/记录其最终结果，不为一次全量 workspace 扫描延迟取消（`recorder.py:173-175`）。
  - 非取消的异常路径同样删缓存后重抛（`recorder.py:183-186`）。
- 回归锚点：`tests/blocking_io/test_workspace_changes_cancellation.py`（覆盖 metadata 取消与文本缓存排空/清理）。

## 事件读取契约（`api.py`）

- `get_workspace_changes_response` 取该 run 最近的事件（`event_types=[WORKSPACE_CHANGES_EVENT_TYPE]`、`limit=10`，用最后一条）；无事件或 payload 非 dict → `available: false` 的空响应（`version:1`、空 summary、`files: []`、`limits: {}`）（`api.py:7-58`）。
- payload 提取优先 `event.metadata[workspace_changes]`，退回 `event.content`（dict 时）（`api.py:61-68`）。
- `include_files=False` ⇒ `files: []`（summary 仍给）；`include_diff=False` ⇒ 每个文件的 `diff` 置空但保留其余字段（`api.py:42-47,71-76`）。

## uploads 链路（同步 #6 更新）

> 同步 #6（431892e1 → 769589e8，v2.1.0-rc0）对上传落盘 / 文档 outline / 上传工具链路的一轮变更。

- 🆕 **统一上传摄取入口** `app/gateway/upload_ingestion.py`（Projects Phase 2 Slice C 引入，随 #5443 落地）：own 整条"文件落入 thread uploads 目录"的流水线——staging、`claim_unique_filename`、大小校验、`uploads.auto_convert_documents` 可选转换、sandbox 可读权限、非挂载式 provider 通过 authorized sandbox request lease 同步原始 + 派生文件。两个调用方共享同一管线：
  - 普通 uploads 端点（`routers/uploads.py`）——薄适配器，行为零变化；
  - 项目 document shelf 附加路由（`routers/project_documents.py`）——同一生命周期。
  - 拒绝 `sandbox:execute` 时保留宿主侧上传、不分配 sandbox；`UnsafeFilenameError` 的 display filename 无法 normalize/claim 时按普通行为跳过该文件。
- 🆕 **去重文件名保持 255 字节上限**（#5059）：`normalize_filename` 限制 255 UTF-8 字节，但 `claim_unique_filename` 追加 `_N` 后缀时不复检预算——最长文件名发生重名时会生成 257 字节的名字，写路径再次 normalize 时 `ValueError`，Gateway 上传路由把它落进通用 handler，整个请求 500 且同批已写文件全部回滚（包括无关文件）。修复：追加 dedupe 标签会超限时在 UTF-8 code point 边界截断 stem；能放下的名字保持历史 `_N` 形状。同一 helper 也服务 Feishu/DingTalk 渠道下载与客户端附件 staging。
- 🆕 **document outline 修复 ×3**（均在 `harness/deerflow/utils/file_outline.py`，即 uploads 文档 outline 与前端 conversation outline 共用的提取器）：
  1. 有界 outline + preview 文本（#5323）——outline 与 preview 受文本预算约束（`test_file_outline_text_budget.py`），超大文档不再生成无界文本；
  2. 合法 ATX 标题识别（#5316）——严格校验 ATX 标题语法（`test_file_outline_atx.py`），避免把普通文本当标题；
  3. 排除 fenced code block（#5281）——``` / ~~~ 围栏内的 `#` 行不再被误认为标题。
- 🆕 **`list_uploaded_files` 支持名称/扩展名过滤**（#5341）：内建工具新增过滤参数（`list_uploaded_files_tool.py` +70 行），可在大量上传文件中按文件名与扩展名收窄结果；`backend/docs/FILE_UPLOAD.md` 同步更新。
- 🆕 **structured upload error details 前端格式化**（#5071）：`frontend/src/core/uploads/api.ts` 解析并展示后端返回的结构化上传错误详情（含 e2e + unit 测试），上传失败不再只给一条笼统报错。

---
> **See also:** [runtime/05-run-ownership-and-rollback.md](../internals/runtime/05-run-ownership-and-rollback.md)（delivery receipt 联动）
