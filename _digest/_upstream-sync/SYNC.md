---
title: "上游同步追踪"
description: "main 分支是上游镜像。main HEAD = 我们消化内容的基准代码版本。ethan 只加 _digest/ 和 _faq_on_digested/，不碰源码。"
type: index
---

# 上游同步追踪

## 这个目录是干什么的

我们 fork 了 [bytedance/deer-flow](https://github.com/bytedance/deer-flow)，在 `ethan` 分支上分析源码、写 digest。上游不会等我们——它持续在往前跑。

**这个目录只做一件事**：记住我们分析的是上游哪个版本的代码。知道了这个锚点，下次 sync 时跑一下 diff，就知道上游改了哪些文件，也就知道了更新 digest 的源头在哪里。

```
上游 commit 162fb214  ← 初始锚点（2026-07-04）
        │
        ├─ 323 commits later...
        │
        └─ 上游 commit 4915b5e  ← 锚点 #2（2026-07-07，已同步）
        │
        ├─ 200 commits later...
        │
        └─ 上游 commit cd34a1a5  ← 锚点 #3（2026-07-20，已同步）
        │
        ├─ 234 commits later...
        │
        └─ 上游 commit e5c62cab  ← 锚点 #4（2026-08-08，已同步）
        │
        ├─ 108 commits later...
        │
        └─ 上游 commit 431892e1  ← 锚点 #5（2026-08-25，已同步）
        │
        ├─ 304 commits later...
        │
        └─ 上游 tag v2.1.0-rc0（769589e8）← 锚点 #6（2026-09-21，本次同步，首个带版本号的锚点）
```

## 核心约定

```
main   = 上游 bytedance/deer-flow 的镜像（一行不改）
ethan  = main + _digest/ + _faq_on_digested/（103 个 commit，247 个文件，全部在这两个目录）
```

**`main` 的 HEAD 就是我们消化内容对应的上游代码版本。** 这个 hash 是唯一的锚点。

## 当前锚点

> 同步历史见 [SYNC_LOG.md](SYNC_LOG.md)

| 项目 | 值 |
|------|-----|
| **`main` HEAD（= 消化基准）** | `769589e8`（**tag `v2.1.0-rc0`**） |
| **旧锚点** | `431892e1`（2026-08-25） |
| **日期** | 2026-09-21 |
| **上游变更规模** | 304 commits |
| **同步日志** | [SYNC_LOG.md](SYNC_LOG.md) #6 |
| **上游当前状态** | tag 之后 main 还有 ~66 commits（发正式版 v2.1.0 前的修复期）；下次可同步到正式版 tag |
| **累积落后** | `162fb214` → `v2.1.0-rc0`（共 1169 commits），[查看差异](https://github.com/bytedance/deer-flow/compare/162fb214...v2.1.0-rc0) |

## 未来同步时怎么看

```bash
# 1. 拉上游最新到 main
git checkout main && git pull upstream main

# 2. 看多了什么（431892e1 是旧锚点，upstream/main 是新锚点）
git log 431892e1..upstream/main --oneline
git diff --stat 431892e1..upstream/main

# 3. 合并到 ethan
git checkout ethan && git merge main

# 4. 更新这个文件：把「当前锚点」改成新的 main HEAD
```

## 上游变更 → 影响哪些 digest

| 上游改了 | 需要复查的 digest |
|---------|------------------|
| `backend/.../agents/` | `concepts/lead-agent/`, `internals/middleware/`, `internals/agent-loop/` |
| `backend/.../sandbox/` | `concepts/sandbox/`, `operations/security/` |
| `backend/.../subagents/` | `concepts/subagent/` |
| `backend/.../skills/` | `concepts/skills-tools/` |
| `backend/.../tools/` | `concepts/builtin-tools/` |
| `backend/.../mcp/` | `internals/mcp/` |
| `backend/.../models/` | `internals/model-layer/` |
| `backend/.../config/` | `internals/configuration/`, `getting-started/` |
| `backend/.../memory/` | `concepts/memory/` |
| `backend/.../runtime/` | `internals/runtime/` |
| `backend/.../client.py` | `getting-started/` |
| `backend/app/gateway/` | `operations/app-layer/` |
| `backend/app/channels/` | `operations/channels/` |
| `frontend/` | `frontend/` |
| `config.example.yaml` | `internals/configuration/`, `getting-started/` |
| `.github/workflows/` | `testing/` |
| `docker/` | `operations/deployment/` |
