---
title: "上游同步"
description: "追踪与 bytedance/deer-flow 上游的同步关系。锚点 commit + diff = 更新 digest 的源头。"
type: index
---

# 上游同步

我们 fork 了 upstream，在 `ethan` 分支上消化源码写 digest。upstream 不会等——它一直在跑。这个目录用来追踪同步关系。

## 文件

| 文件 | 作用 |
|------|------|
| [SYNC.md](SYNC.md) | 当前锚点、操作流程、上游变更→digest 影响速查表 |
| [SYNC_LOG.md](SYNC_LOG.md) | 每次同步的流水账 |

## 快速使用

```bash
# 1. 看当前锚在哪
grep "main HEAD" SYNC.md

# 2. 拉上游，看距离
git fetch upstream main
git log 162fb214..upstream/main --oneline

# 3. 看改了哪些文件
git diff --stat 162fb214..upstream/main

# 4. 对照 SYNC.md 里的影响表 → 更新对应 digest → 记到 SYNC_LOG.md
```
