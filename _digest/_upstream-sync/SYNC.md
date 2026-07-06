---
title: "上游同步追踪"
description: "记录与 bytedance/deer-flow 上游的对齐位置、同步操作流程、变更对 digest 的影响映射。"
type: index
---

# 上游同步追踪

## 当前同步点

| 项目 | 值 |
|------|-----|
| **上游仓库** | [bytedance/deer-flow](https://github.com/bytedance/deer-flow) |
| **对齐的上游 commit** | `162fb214` |
| **日期** | 2026-07-04 |
| **内容** | `fix(mcp): skip session pooling for HTTP/SSE transports (#3203)` |
| **ethan 分支 HEAD** | `0607b312` |
| **标记日期** | 2026-07-06 |

## 同步操作

### 1. 查看与上游的距离

```bash
git fetch upstream main
echo "上游领先: $(git log 162fb214..upstream/main --oneline | wc -l) commits"
git log 162fb214..upstream/main --oneline
```

> 如果 `git fetch upstream` 失败，浏览器打开：
> `https://github.com/bytedance/deer-flow/compare/162fb214...main`

### 2. 看改了什么文件

```bash
git diff --stat 162fb214..upstream/main
```

### 3. 合并

```bash
git checkout main && git pull upstream main
git checkout ethan && git merge main
```

---

## 上游变更 → Digest 影响速查

| 上游改动路径 | 影响的 digest 目录 |
|-------------|-------------------|
| `backend/.../agents/lead_agent/` | `overview/`, `concepts/lead-agent/` |
| `backend/.../agents/middlewares/` | `internals/middleware/`, `internals/agent-loop/` |
| `backend/.../sandbox/` | `concepts/sandbox/`, `operations/security/` |
| `backend/.../subagents/` | `concepts/subagent/` |
| `backend/.../skills/` | `concepts/skills-tools/` |
| `backend/.../tools/` | `concepts/builtin-tools/` |
| `backend/.../mcp/` | `internals/mcp/` |
| `backend/.../models/` | `internals/model-layer/` |
| `backend/.../config/` | `internals/configuration/` |
| `backend/.../memory/` | `concepts/memory/` |
| `backend/.../runtime/` | `internals/runtime/` |
| `backend/.../client.py` | `getting-started/` |
| `backend/app/gateway/` | `operations/app-layer/` |
| `backend/app/channels/` | `operations/channels/` |
| `frontend/` | `frontend/` |
| `config.example.yaml` | `internals/configuration/`, `getting-started/` |
| `.github/workflows/` | `testing/` |
| `docker/` | `operations/deployment/` |

## 最近上游历史

`162fb214` 之前的 15 个 commit（最近→最远）：

```
162fb214 fix(mcp): skip session pooling for HTTP/SSE transports
92905e9e fix(todo): reuse thread state schema
da41701f Add static blocking IO inventory
e0280194 chore: add a pull request template
b00749a8 fix(auth): share internal gateway token across workers
e344be8d feat(tests): add Blockbuster runtime gate for event-loop blocking IO
f68bcb77 fix(frontend): guard message copy clipboard access
11dd5b06 fix(frontend): strip unclosed <think> tags from streaming AI content
f9b70713 fix(sandbox): add group/other read permissions to uploaded files
8785658a fix(agents): preserve todos state across node updates
0fb05825 fix(runtime): make run creation persistence atomic
66d6a6a4 fix: harden run finalization persistence
f0bae286 fix(middleware): handle repeated tool call ids
2eeb5979 fix(runs): expose active progress counters
914d6a4f docs: add provider safety termination post
```

## 同步后更新 Digest 的流程

1. `git log <旧>..<新> --oneline` 看新增 commit
2. `git diff --stat <旧>..<新>` 看文件改动
3. 对照「影响速查」标记受影响的 digest 目录
4. 读上游 diff → 对比 digest → 更新或追加
5. 更新本文件的「当前同步点」
