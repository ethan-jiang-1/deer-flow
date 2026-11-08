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

**铁律**：`ethan` 只在三个目录上区别于上游——`_digested/`、`_faq_on_digested/`、
`_deerflow_application_agent_ready_development/`；其余与 `main`（= 最新 release tag）逐字节相同。
同步是**重建**，不是 merge——完整可照抄的命令见 [SYNC.md](SYNC.md)「未来同步时怎么做」。

```bash
# 1. 看当前锚在哪 / 有没有新版本
grep "main HEAD" SYNC.md
git fetch upstream --tags --prune && git fetch origin
git ls-remote --tags upstream | grep -v '\^{}$' | awk -F/ '{print $3}' | sort -V | tail -5

# 2. 判线（release tag 不是 upstream/main 的祖先 = 常态）
git merge-base --is-ancestor v2.2.0 upstream/main && echo "tag 在 main 上" || echo "已分叉"
git rev-list --count v2.2.0..upstream/main      # main（2.3 开发线）领先多少

# 3. 同步 = 备份 → main reset 到 tag → ethan 重建 → 三目录继承 → 一条提交
#    完整命令见 SYNC.md；不要用 git merge

# 4. 自检：三目录之外必须 0（用 -z；文件名含空格/中文时引号转义会误报）
git diff --name-only -z v2.2.0 ethan | tr '\0' '\n' \
  | grep -vE '^(_digested|_faq_on_digested|_deerflow_application_agent_ready_development)/' | grep -c .

# 5. 看改了哪些文件（旧锚点..新锚点）→ 对照影响表更新 digest → 记 SYNC_LOG.md
git diff --stat 345f08be..58fc5bd5b
```
