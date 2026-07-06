---
title: "上游同步追踪"
description: "main 分支是上游镜像。main HEAD = 我们消化内容的基准代码版本。ethan 只加 _digest/ 和 _faq_on_digested/，不碰源码。"
type: index
---

# 上游同步追踪

## 核心约定

```
main   = 上游 bytedance/deer-flow 的镜像（一行不改）
ethan  = main + _digest/ + _faq_on_digested/（51 个 commit，186 个文件，全部在这两个目录）
```

**`main` 的 HEAD 就是我们消化内容对应的上游代码版本。** 这个 hash 是唯一的锚点。

## 当前锚点

| 项目 | 值 |
|------|-----|
| **`main` HEAD（= 消化基准）** | `162fb214` |
| **merge base（main ∩ ethan）** | `162fb214` |
| **日期** | 2026-07-04 |
| **该 commit 内容** | `fix(mcp): skip session pooling for HTTP/SSE transports (#3203)` |
| **ethan HEAD** | `e6d2768b` |
| **ethan 领先 main** | 51 commits（全在 `_digest/` + `_faq_on_digested/`） |
| **main 领先 ethan** | 0 commits（已完全同步） |

## 未来同步时怎么看

```bash
# 1. 拉上游最新到 main
git checkout main && git pull upstream main

# 2. 看多了什么（162fb214 是旧锚点，upstream/main 是新锚点）
git log 162fb214..upstream/main --oneline
git diff --stat 162fb214..upstream/main

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
