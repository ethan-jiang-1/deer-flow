# 与上游同步

> 当前 `main` 分支跟踪 [bytedance/deer-flow](https://github.com/bytedance/deer-flow) 上游。
> `ethan` 分支承载所有 `_digest/` 和 `_faq_on_digested/` 研究笔记。
> **`ethan` 永远不会 merge 回 `main`。**

---

## 当前同步点

| 项目 | 值 |
|------|-----|
| **上游仓库** | `bytedance/deer-flow` |
| **Fork** | `ethan-jiang-1/deer-flow` (origin) |
| **main 最新 commit** | `162fb214` |
| **merge base** | `162fb214`（main == ethan 的共同祖先） |
| **同步日期** | 2026-07-06 |
| **上游领先** | 0 commits（当前已同步） |

`main` 最近 10 个上游 commit：

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
```

---

## 同步流程

### 什么时候同步

- 想看看上游有什么新东西时
- 准备基于最新上游代码更新 digest 内容时

### 步骤

```bash
# 1. 切到 main，拉上游
git checkout main
git pull origin main    # 或如果配了 upstream: git pull upstream main

# 2. 看看多了什么
git log 162fb214..main --oneline
# （把 162fb214 替换成上一轮记录的 merge base）

# 3. 判断哪些变更影响 _digest/ 覆盖的领域
#    - middleware 变更 → 检查 middleware/ 相关笔记
#    - sandbox 变更 → 检查 sandbox 相关笔记
#    - config 变更 → 检查 configuration/ 相关笔记
#    ...

# 4. 合并到 ethan
git checkout ethan
git merge main

# 5. 更新本文件的「当前同步点」
```

### 影响的 digest 领域速查

| 上游变更路径 | 可能影响的 digest 目录 |
|-------------|----------------------|
| `backend/packages/harness/deerflow/agents/` | `agent-loop/`, `middleware/`, `architecture/05` |
| `backend/packages/harness/deerflow/sandbox/` | `architecture/06`, `security/02` |
| `backend/packages/harness/deerflow/subagents/` | `architecture/07` |
| `backend/packages/harness/deerflow/skills/` | `architecture/09` |
| `backend/packages/harness/deerflow/tools/` | `builtin-tools/`, `architecture/09` |
| `backend/packages/harness/deerflow/mcp/` | `architecture/12`, `configuration/02` |
| `backend/packages/harness/deerflow/models/` | `model-layer/` |
| `backend/packages/harness/deerflow/config/` | `configuration/`, `harness-hooks/` |
| `backend/packages/harness/deerflow/memory/` | `architecture/08` |
| `backend/packages/harness/deerflow/runtime/` | `runtime/` |
| `backend/app/gateway/` | `app-layer/` |
| `frontend/` | `frontend/`, `architecture/11` |
| `.github/workflows/` | `testing/`, `deployment/` |
| `config.example.yaml` | `configuration/`, `integration/` |

---

## 工作流规则

- `main` = 上游镜像，**绝不直接在上面改代码**
- `ethan` + `_digest/` + `_faq_on_digested/` = 学习空间
- 新发现写入 `_digest/` 或 `_faq_on_digested/`
- 定期回到 `main` 拉上游，合并到 `ethan`
