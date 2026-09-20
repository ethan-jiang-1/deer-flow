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
