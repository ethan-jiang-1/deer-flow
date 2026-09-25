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
        └─ 上游 tag v2.1.0-rc0（769589e8）← 锚点 #6（2026-09-21）
        │
        ├─ 10 commits later（release 收尾：版本号/CHANGELOG/CI/两本手册）
        │
        └─ 上游 tag v2.1.0（345f08be）← 锚点 #7（2026-09-21 之后，v2.1.0 正式版）
```

> ⚠️ **锚点 #7 的特殊之处**：`v2.1.0` tag 打在 release 分支 `2.1.x-dev` 上，**不是 `upstream/main` 的祖先**——
> 两者在 `v2.1.0-rc0`（锚点 #6）处分叉。main 在 rc0 之后另有 **189 个 commit**（2.2 开发线），
> 所以本次 `main` 镜像指向的是 **release tag**，而不是 `upstream/main`。下一次同步要同时处理这两条线。

## 核心约定

```
main   = 上游 bytedance/deer-flow 的镜像（一行不改）
ethan  = main + _digest/ + _faq_on_digested/（129 个 commit，274 个文件，全部在这两个目录）
```

> 计数口径：`git rev-list --count main..ethan` 与 `git ls-tree -r --name-only ethan -- _digest _faq_on_digested`；`git diff --name-only main ethan` 在 `_digest/`、`_faq_on_digested/` 之外应为空（每次同步后用这条自检）。

**`main` 的 HEAD 就是我们消化内容对应的上游代码版本。** 这个 hash 是唯一的锚点。

## 当前锚点

> 同步历史见 [SYNC_LOG.md](SYNC_LOG.md)

| 项目 | 值 |
|------|-----|
| **`main` HEAD（= 消化基准）** | `345f08be`（**tag `v2.1.0`**，release 分支 `2.1.x-dev`） |
| **旧锚点** | `769589e8`（tag `v2.1.0-rc0`，2026-09-21） |
| **日期** | 2026-09-24（tag 切出日期） |
| **上游变更规模** | 10 commits（90 files, +9,097 / −450） |
| **同步日志** | [SYNC_LOG.md](SYNC_LOG.md) #7 |
| **上游当前状态** | tag 与 `upstream/main` **已分叉**：`upstream/main` = `3a862780`，rc0 之后另有 **189 commits**（925 files, +94,219 / −4,795，2.2 线）；上游最新 tag 仍是 `v2.1.0` |
| **累积落后** | `162fb214` → `v2.1.0`（共 1,179 commits），[查看差异](https://github.com/bytedance/deer-flow/compare/162fb214...v2.1.0) |

## 未来同步时怎么看

```bash
# 0. 拉上游（含 tag）+ 自己的 fork
git fetch upstream --tags --prune && git fetch origin

# 1. 先判断锚点走哪条线：release 分支还是 main
git merge-base --is-ancestor v2.1.0 upstream/main && echo "tag 在 main 上" || echo "已分叉"
git log --oneline -1 upstream/2.1.x-dev          # release 线的最新提交
git rev-list --count v2.1.0..upstream/main       # main 线领先多少

# 2. 看多了什么（345f08be 是旧锚点，按上一步选定的新锚点替换）
git log --oneline 345f08be..<新锚点>
git diff --stat 345f08be..<新锚点>

# 3. 同步 main 镜像到新锚点（tag 用 reset --hard；main 分支用 merge --ff-only）
git checkout main && git reset --hard <新锚点>   # 或 git pull upstream main

# 4. 合并到 ethan（ethan 只加 _digest/ + _faq_on_digested/，源码应无冲突）
git checkout ethan && git merge main

# 5. 更新这个文件：把「当前锚点」改成新的 main HEAD，并记一条 SYNC_LOG.md

# 6. 跑机械校验（tools/check_digest.py，只读、有问题退出码 1）
python3 _digest/_upstream-sync/tools/check_digest.py
git diff <新锚点> ethan -- . ':(exclude)_digest' ':(exclude)_faq_on_digested'   # 必须为空
```

## 两遍扫描（sync 的固定套路）

单靠"跟着 diff 补文档"会漏掉**未被 diff 触碰但已过期**的内容——sync #7 的第二轮就是这么发现成片旧账的。所以每次 sync 固定跑两遍：

| 遍 | 做什么 | 工具/方法 |
|----|--------|-----------|
| **第一遍：diff → digest** | 拿 `<旧锚点>..<新锚点>` 的变更文件，按上面的影响表逐域核对、补写 | `git log/diff` + 人工/agent 读源码 |
| **第二遍：源码 → digest** | 从源码模块清单出发，反查 digest 的**每条断言**（行数/行号/路径/类名/变量/配置键/路由/命令），并找"源码有、digest 无"的覆盖缺口 | `tools/check_digest.py`（机械层）+ 分域 agent（语义层） |

第三类是"少的"：digest 描述了、源码已不存在（改名/删除/远古架构）——同样靠第二遍的正则与符号扫描 + 逐条读源码判定。

详见 [tools/README.md](tools/README.md)（脚本能力与已知盲区）。

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
