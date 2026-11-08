---
title: "上游同步追踪"
description: "main 分支是上游镜像。main HEAD = 我们消化内容的基准代码版本。ethan 只加 _digested/ 和 _faq_on_digested/，不碰源码。"
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
        ├─ 1048 commits later（release 线：rc0 → 正式版，含 2.2 全部功能）
        │
        └─ 上游 tag v2.2.0（58fc5bd5b）← 锚点 #8（2026-11-04 发布，2026-11-08 同步）
```

> ⚠️ **从 #7 起，锚点一直是 release tag，不是 `upstream/main`**：`v2.1.0`、`v2.2.0` 都打在 release 分支
> （`2.1.x-dev` / `2.2.x-dev`）上，**不是 `upstream/main` 的祖先**。main 同时跑在更前面的开发线
> （`v2.2.0` 时 main 已是 `2.3.0-dev`，领先 142 commits）。所以 `main` 镜像指向的是 **release tag**，
> 不是 `upstream/main`。每次同步先判线，别默认跟 main。

## 核心约定（铁律，不容例外）

```
main   = 上游 bytedance/deer-flow 的镜像（一行不改，指向最新 release tag）
ethan  = main + 恰好三个目录：_digested/ + _faq_on_digested/ + _deerflow_application_agent_ready_development/
```

**`ethan` 独有的只有这三个目录，其余每个字节都与 `main`（= 锚点 tag）完全相同。** 这是这个 fork 的初心，
不是「大约如此」：任何落在三个目录之外的差异都是 bug，必须在同步时清掉，不许「顺手带过去」。

> ⚠️ 历史教训（#8 时踩过）：`ethan` 曾有 37 个文件（`backend/`、`docs/`、`examples/`、`AGENTS.md`）来自一个
> 自制的测试策略提交。核对时别只信「只有三个目录」这个前提——**永远先用下面的命令验证**，再决定怎么做。
> 用 `-z` 输出，否则含空格/中文的文件名会被加引号转义，前缀匹配会误报。

```bash
# 唯一权威自检：三目录之外的差异必须为空
git diff --name-only -z v2.2.0<锚点> ethan \
  | tr '\0' '\n' | grep -vE '^(_digested|_faq_on_digested|_deerflow_application_agent_ready_development)/' \
  | grep -c .          # 必须输出 0
```

**`main` 的 HEAD 就是我们消化内容对应的上游代码版本。** 这个 hash 是唯一的锚点。

## 当前锚点

> 同步历史见 [SYNC_LOG.md](SYNC_LOG.md)

| 项目 | 值 |
|------|-----|
| **`main` HEAD（= 消化基准）** | `58fc5bd5b`（**tag `v2.2.0`**，release 分支 `2.2.x-dev` 的 HEAD） |
| **旧锚点** | `345f08be`（tag `v2.1.0`，2026-09-24） |
| **日期** | 2026-11-04（tag 发布）/ 2026-11-08（同步） |
| **上游变更规模** | 1,239 commits（1,068 个 PR，v2.1.0 → v2.2.0） |
| **同步日志** | [SYNC_LOG.md](SYNC_LOG.md) #8 |
| **上游当前状态** | tag 与 `upstream/main` **已分叉**：`upstream/main` = `c69e9ef0b`（`2.3.0-dev`，v2.2.0 之后另有 142 commits）；上游最新 tag 仍是 `v2.2.0`（release 线无后续补丁） |
| **累积落后** | `162fb214` → `v2.2.0`，[查看差异](https://github.com/bytedance/deer-flow/compare/162fb214...v2.2.0) |
| **`ethan` 形态** | `v2.2.0` + 三个目录，**1 条提交**（`5d441b9a7`），三目录之外零差异 |

## 未来同步时怎么做（照抄即可，不用再讨论）

**核心一步不是 merge，而是重建。** `ethan` 有上百个历史提交，`git merge` 会把那些提交里的源码差异全部放大成冲突；
而我们的目标态永远简单——「新 tag + 三个目录」。所以直接构造目标态，然后一条提交：

```bash
TAG=v2.2.0                      # ← 换成新 release tag
NEW=$(git rev-parse "$TAG^{}")  # ← 目标 commit（annotated tag 要解引用）
OLD=$(git rev-parse main)       # ← 旧锚点

# 0. 拉上游（含 tag）+ 自己的 fork
git fetch upstream --tags --prune && git fetch origin

# 1. 判线 + 确认新 tag 存在（别假设有新版，先看）
git ls-remote --tags upstream | grep -v '\^{}$' | awk -F/ '{print $3}' | sort -V | tail -5
git merge-base --is-ancestor "$TAG" upstream/main && echo "tag 在 main 上" || echo "已分叉（正常）"
git log --oneline -1 "upstream/$(echo $TAG | sed 's/^v//; s/\([0-9]*\.[0-9]*\)\..*/\1.x/')-dev" 2>/dev/null
git rev-list --count "$TAG"..upstream/main       # main 线领先多少（2.3 开发线进度）

# 2. 安全网（两步都做：分支可 checkout，tag 抗误删）
git branch -f "ethan-backup-$(date +%F)" ethan
git tag -f "pre-${TAG#v}-ethan" ethan

# 3. 校验旧 ethan 是否干净（三目录之外必须为 0；不为 0 就停下来报告，别硬带）
git diff --name-only -z "$OLD" ethan \
  | tr '\0' '\n' | grep -vE '^(_digested|_faq_on_digested|_deerflow_application_agent_ready_development)/' \
  | grep -c .

# 4. main 镜像 → 新 tag
git checkout main && git reset --hard "$NEW"

# 5. ethan 重建：从新 tag 开一条线，然后把三个目录「继承」过来
git checkout -B ethan main
git checkout "ethan-backup-$(date +%F)" -- \
  _digested _faq_on_digested _deerflow_application_agent_ready_development

# 6. 提交前自检（必须 0），然后一条提交
git diff --name-only -z "$NEW" ethan \
  | tr '\0' '\n' | grep -vE '^(_digested|_faq_on_digested|_deerflow_application_agent_ready_development)/' \
  | grep -c .
git commit -m "chore(sync): move ethan to upstream $TAG (anchor #N)"

# 7. 提交后再验一次 + 记录
git rev-list --count "$NEW"..ethan                # 必须 1（除非额外加了三目录内的修正提交）
git diff --name-only -z "$NEW" ethan | tr '\0' '\n' \
  | grep -vE '^(_digested|_faq_on_digested|_deerflow_application_agent_ready_development)/' | grep -c .   # 必须 0
# 更新本文件「当前锚点」+ 记 SYNC_LOG.md #N + 写 UPDATE_PLAN_N.md
# 然后跑两遍扫描（下一节）
```

**几条硬规矩**：

1. **不要 `git merge`，不要 cherry-pick**。重建比合并简单、可预测、零冲突。
2. **三目录整目录继承**（`git checkout <backup> -- <dir>`），不要挑文件，不要改内容——内容更新是「两遍扫描」阶段的事，
   别混进同步提交里（否则同步提交不再可审计）。
3. **发现三目录之外的差异时**：先停下报告，不要擅自删除或迁移用户的改动。由人决定是归档、丢弃还是加进允许区。
4. **`origin` 推送要人点头**：`main`/`ethan` 都是强推，先做完第 6 步自检再问。
5. **无新 tag 就如实说「没有新版本」**，不要因为 main 在动就把 main 当锚点（除非用户明确要开发线）。
6. 文件名含空格/中文很常见，**所有 diff 校验都用 `-z` + `tr '\0' '\n'`**，否则引号转义会导致前缀匹配误报。
7. **源码删了，digest 不能装作还在**。发现「digest 原样描述一个已删除的机制」时，两件事都要做：
   ① 改写正文为「已删除（版本/PR）+ 现行语义」，② 把该路径登记进 `tools/check_digest.py` 的 `DELETED_SOURCE_PATHS`。
   登记后，引用该路径的**同一行必须带删除标记**（「已删除」「移除」「~~」等），否则校验器报错并指出删除版本。
   只做 ① 会让下一个人重新踩坑，只做 ② 会留下一堆无解释的例外。

## 三遍扫描（sync 的固定套路）

单靠"跟着 diff 补文档"会漏掉**未被 diff 触碰但已过期**的内容——sync #7 的第二轮就是这么发现成片旧账的。所以每次 sync 固定跑三遍：

| 遍 | 做什么 | 工具/方法 |
|----|--------|-----------|
| **第一遍：diff → digest** | 拿 `<旧锚点>..<新锚点>` 的变更文件，按上面的影响表逐域核对、补写 | `git log/diff` + 人工/agent 读源码 |
| **第二遍：源码 → digest** | 从源码模块清单出发，反查 digest 的**每条断言**（行数/行号/路径/类名/变量/配置键/路由/命令），并找"源码有、digest 无"的覆盖缺口 | `tools/check_digest.py`（机械层）+ 分域 agent（语义层） |
| **第三遍：事实重算** | 从源码/配置/目录重算高风险事实（迁移数/head、ORM 行数、权限数、测试数、契约数、手册页数），并扫描已知旧值；同时校验 README 六段、front matter、根阅读路径、surface owner，以及页面 ↔ SVG 双向绑定/孤儿图 | `tools/check_freshness.py`、`tools/check_structure.py`、`tools/check_coverage.py`、`tools/check_figures.py`；一键 `tools/check_all.py` |

第三类是"少的"：digest 描述了、源码已不存在（改名/删除/远古架构）——同样靠第二遍的正则与符号扫描 + 逐条读源码判定；第三遍负责防止"数字对了但语义已漂"。

**处置「已删除机制」的三档口径**（sync #8 起固定）：

| 情形 | 怎么写 | 例 |
|------|--------|-----|
| 机制整体消失，无替代 | 删掉整段，在页面顶部的「同步注记」里留一行说明 | — |
| 机制消失但**语义被别的机制继承** | 写成「已删除（版本/PR）+ 现行语义在 X」，并指出新的所有权 | `allowed-tools` → 权限上限归 agent 组装/执行授权 |
| 机制**从来不是上游的**（fork 自造） | 明确写「上游从未存在」，并把依赖它的论证降级为历史记录 | `deerflow.testing` / `docs/testing/` |


详见 [tools/README.md](tools/README.md)（脚本能力与已知盲区）。

## 上游变更 → 影响哪些 digest

| 上游改了 | 需要复查的 digest |
|---------|------------------|
| `backend/.../agents/` | `concepts/lead-agent/`, `internals/middleware/`, `internals/agent-loop/` |
| `backend/.../sandbox/` | `concepts/sandbox/`, `enterprise-operations/security/` |
| `backend/.../subagents/` | `concepts/subagent/` |
| `backend/.../skills/` | `concepts/skills-tools/` |
| `backend/.../tools/` | `concepts/builtin-tools/` |
| `backend/.../mcp/` | `internals/mcp/` |
| `backend/.../models/` | `internals/model-layer/` |
| `backend/.../config/` | `internals/configuration/`, `getting-started/` |
| `backend/.../memory/` | `concepts/memory/` |
| `backend/.../runtime/` | `internals/runtime/` |
| `backend/.../client.py` | `getting-started/` |
| `backend/app/gateway/` | `enterprise-operations/app-layer/` |
| `backend/app/channels/` | `enterprise-operations/channels/` |
| `frontend/` | `frontend/` |
| `config.example.yaml` | `internals/configuration/`, `getting-started/` |
| `backend/tests/` | `testing/`, `test-strategy/` |
| `backend/docs/`（REPLAY_E2E / BLOCKING_IO_DETECTION 等） | `test-strategy/` |
| `contracts/` | `test-strategy/` |
| `scripts/`（detect_* / check_agent_guidance / verify_versions） | `test-strategy/` |
| `.github/workflows/` | `testing/`, `test-strategy/` |
| `docker/` | `enterprise-operations/deployment/` |
| `extensions/sources/`, `examples/deerflow-extension-*` | `internals/harness-hooks/`（扩展平台）、`test-strategy/` |
| `frontend/src/content/`（用户手册 en/zh） | 对应 `_digested/` 主题页 + `frontend/` |
| 迁移文件（`backend/app/...migrations/versions/`） | `internals/persistence/` |
