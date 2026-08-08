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

---
> **See also:** [runtime/05-run-ownership-and-rollback.md](../internals/runtime/05-run-ownership-and-rollback.md)（delivery receipt 联动）
