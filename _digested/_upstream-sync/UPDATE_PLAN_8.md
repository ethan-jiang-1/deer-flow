---
title: "同步 #8 更新计划（v2.1.0 → v2.2.0）"
description: "从 58fc5bd5b 源码出发，把三个消化目录同步到 v2.2.0 的作战地图：测绘结果、分域清单、执行顺序、验收标准。"
type: plan
---

# 同步 #8 更新计划（v2.1.0 → v2.2.0）

## 0. 本轮的核心命题

**REPO 换了，三个消化目录必须跟着换。** 三个目录是对源码的「消化产物」——源码删了、改了、加了，
产物里的断言（路径、行号、类名、配置键、路由、命令、计数）就全部失效。

| 项目 | 值 |
|------|-----|
| 旧锚点 | `345f08be`（`v2.1.0`，2026-09-24） |
| 新锚点 | `58fc5bd5b`（`v2.2.0`，2026-11-04） |
| 跨度 | **1,239 commits / 1,068 PR**（v2.2.0-rc0 → 正式版 5 个收尾提交） |
| 变更文件 | **2,838** 个 |
| 待同步产物 | `_digested/` 219 篇 / 34,730 行；`_faq_on_digested/` 52 篇 / 6,856 行；`_deerflow_application_agent_ready_development/` 31 篇 / 1,345 行（+ `verify.mjs`） |

## 1. 测绘结果（本轮 baseline）

### 1.1 机械层基线：66 处问题

`python3 _digested/_upstream-sync/tools/check_digest.py` → exit 1：

| 类别 | 数量 | 说明 |
|------|------|------|
| `line_count` | 62 | 页面声称的源码行数与 2.2.0 实际不符（最多的是 `mcp/tools.py` 967→1498、`redis.py` 384→1068、`journal.py` 1300→1977） |
| `line_in_range` | 1 | `db-checkpointer-store-backends.md:752` 引用 `env.py:65`，但 `env.py` 只有 37 行——**该文件在 2.2 被重写** |
| `path_exists` | 3 | `skills/tool_policy.py`（**2.2 已删除**）、`deerflow/testing/models.py` ×2（`_faq` 里引用了不存在的路径） |

> 机械层只覆盖「可正则化」的断言。真正的量级在语义层。

### 1.2 源码结构性变化（决定「要加的加」）

**新增 harness 子包**（2.1.0 完全没有）：

| 子包 | 文件数 | 语义 | digest 现状 |
|------|--------|------|------------|
| `deerflow/capabilities/` | 5 | 能力目录与准入 | ❌ 无页 |
| `deerflow/knowledge/` | 5 | 检索 provider 抽象（RAGFlow 解耦 + WeKnora） | ❌ 无页（`concepts/community-tools/07-ragflow.md` 只覆盖老路径） |
| `deerflow/typesafe/` | 6 | TypeSafe 风险门/预筛 | ❌ 无页 |
| `deerflow/storage/` | 7 | 内容寻址 blob store | ❌ 无页 |
| `deerflow/openai_decisions/` | 2 | OpenAI 决策面 | ❌ 无页 |
| `deerflow/knowledge_scope.py` | 194 行 | 检索作用域（fail-closed allowlist） | ❌ 无页 |
| `deerflow/mcp_scope.py` | 95 行 | MCP 作用域 | ⚠️ `internals/mcp/` 未覆盖 |
| `deerflow/env.py` | 37 行 | 环境变量解析（重写） | ⚠️ `env.py:65` 死引用 |

**删除的源码**（决定「要删的删」）：

- `backend/packages/harness/deerflow/skills/tool_policy.py` — 整个模块删除
- `backend/packages/harness/deerflow/agents/middlewares/skill_tool_policy_middleware.py` — 中间件删除
- `backend/tests/test_skill_tool_policy_middleware.py` — 对应测试删除
- `backend/sitecustomize.py`；`frontend/src/components/ai-elements/*` 15 个组件（画布/canvas 系）
- 语义影响：`allowed-tools` **降级为兼容元数据**（不再隐藏/阻止工具），digest 里所有「tool policy 中间件」的描述都要改写而非改行号

**新增迁移**（决定 persistence 域的更新量）：2.1.0 有 27 个 → 2.2.0 有 **50** 个，新增 23 个
（`0026_mcp_task_lease_tokens` … `0048_extension_execution_leases`）。

**配置面**：`config.example.yaml` **+770 / −111 行**，新增/变更的配置段必须逐段落进
`internals/configuration/01-config-yaml.md`、`04-config-reference.md`、`getting-started/02-configuration.md`。

**Extension API**：`agent_runs.py`、`completed_run_evidence.py`、`host_capabilities.py`、
`model_invocation.py`、`plugins.py`、`settings.py`、`skill_mutations.py` 七个新模块；
`internals/harness-hooks/09-packaged-extensions.md` 需要重写扩展贡献契约。

**2.2 新增的扩展示例**（`examples/deerflow-extension-{bookmarks,agent-teams,workflows,knowledge-management,knowledge-platform,weknora,jev-*,report-sections,lightrag}`）
——上游已从「一个 sample」变成「一整套示例家族」，根 `AGENTS.md` 的 extension-first 段落也相应改写。

### 1.3 按域的变更密度（决定分片）

`backend/packages/harness/deerflow/` 下各子包变更文件数：
`agents 99`、`persistence 86`、`community 78`、`runtime 41`、`config 41`、`skills 37`、
`mcp 21`、`tools 19`、`extensions 19`、`utils 18`、`sandbox 18`、`models 16`、`subagents 12`、
`tui 9`、`authz 9`、`storage 7`、`typesafe 6`、`projects 5`、`knowledge 5`、`guardrails 5`、`capabilities 5`。

前端：`src/core 142`、`src/components 140`、`src/content 90`（**用户手册 en/zh 各 12 个新文件**）、`tests/unit 228`、`tests/e2e 67`。

## 2. 执行顺序（七个阶段）

每阶段都有**输入 / 动作 / 输出 / 验收**，前阶段不绿不进下一阶段。

### P0 — 测绘（本文件）✅
- 产出：本文件。
- 验收：变更地图可复现（命令写在 §5）。

### P1 — 机械层归零
- **输入**：`check_digest.py` 的 66 处。
- **动作**：先跑脚本拿全量列表；逐条判定三类——(a) 纯行数漂移 → 直接改数字；(b) 行号/路径失效 →
  回到 2.2.0 源码找新落点；(c) **源码已删除**（`tool_policy`）→ 不是改数字，而是重写该小节语义。
- **输出**：`check_digest.py` exit 0。
- **验收**：`python3 .../check_digest.py; echo $?` → 0。

### P2 — 第一遍扫描：diff → digest（分域，14 片）
按 §1.3 的密度把 `_digested/` 拆 14 片并行处理，每片的动作固定为「读该域的 `git diff v2.1.0 v2.2.0` → 对照现有页面 → 增/改/删」：

| # | 分片 | 对应 `_digested/` 目录 | 重点 |
|---|------|------------------------|------|
| 1 | runtime + persistence | `internals/runtime/`, `internals/persistence/` | stream bridge（Redis 384→1068）、journal 1300→1977、manager 2424→3150、23 个新迁移、blob store |
| 2 | middleware + agent-loop | `internals/middleware/`, `internals/agent-loop/`, `concepts/lead-agent/` | agents 99 文件改动、`skill_tool_policy` 中间件删除、middleware 工具进授权 |
| 3 | subagent + scheduler + goal | `concepts/subagent/`, `operations/scheduler.md`, `internals/runtime/goal-continuation.md` | goal 驱动工作流、`max_concurrent_runs_per_user`、结构化错误信封 |
| 4 | MCP | `internals/mcp/` | durable tasks 大改、session pool、`mcp_scope.py`、按用户连接 |
| 5 | skills + capabilities | `concepts/skills-tools/`, 新 `capabilities/` | `tool_policy` 删除后重写、`allowed-tools` 降级、`skill_mutations` |
| 6 | sandbox + tools | `concepts/sandbox/`, `concepts/builtin-tools/`, `operations/security/02` | 五个 provider 关停可重试、bash 硬超时、path guard 补漏 |
| 7 | memory + model-layer | `concepts/memory/`, `internals/model-layer/` | `cognitiveStyle`、词法排序、Markdown 容错、管理 API 按 agent 桶、模型目录加密 |
| 8 | channels | `operations/channels/`, `operations/integration/04` | QQ 频道、微信扫码、主动通知、leader lease、`channel_runtime_configs` |
| 9 | config + getting-started + TUI | `internals/configuration/`, `getting-started/` | config.example +770 行、`DEER_FLOW_*` 环境变量、多行编辑器 |
| 10 | gateway + API + uploads | `operations/app-layer/`, `operations/integration/02` | 权限路由、`/health/ready`、上传严格化 |
| 11 | security + authz + extensions | `operations/security/`, `internals/harness-hooks/`, `operations/it-ops/` | 凭据加密、fail-closed 默认、extension API 0.2.7、skill mutations |
| 12 | frontend | `frontend/` | `@` 引用、斜杠菜单精简、产物句柄、UE 大量改动、content 手册 |
| 13 | observability + testing + test-strategy | `observability/`, `testing/`, `test-strategy/` | `run.terminal`、per-LLM-call 遥测、四分片 CI、`skill-tests` job |
| 14 | overview + harness + graph/orchestration | `overview/`, `harness/`, `harness-engineering/`, `graph-engineering/`, `orchestration-ladder/` | 架构图/组件/启动流、LIMIT 与计数、编排原语是否新增 |

- **验收**：每片产出一份 `这一片改了什么` 的清单 + 实际改动；`check_digest.py` 仍为 0。

### P3 — 覆盖缺口补写（「源码有、digest 没有」）
新子系统必须**建页**，不靠零散追加：

- `internals/knowledge/`（检索 provider 抽象、统一引用证据、`knowledge_scope.py`）
- `internals/typesafe/`（风险门 + 预筛）
- `internals/storage/`（内容寻址 blob store）
- `internals/capabilities/`（能力目录与准入）
- `concepts/community-tools/09-weknora.md`（新 provider）
- `operations/multi-instance.md`（多实例：leader lease、Helm/compose、provisioner replicas、workflow `ExecutionFence`、`make dev-multi`）
- `operations/extensions-catalog.md`（bookmarks / agent-teams / workflows / knowledge-* 示例家族）
- `internals/mcp/02-scopes-and-per-user.md`（`mcp_scope.py`）

- **验收**：§1.2 表格里每个 ❌ 都有对应页；`_digested/README.md` 索引同步。

### P4 — 第二遍扫描：源码 → digest（反向核对）
从 2.2.0 源码模块清单出发，逐条反查断言，专找三类问题：

1. **新的**：源码有的机制，digest 没写（承接 P3 的遗漏）。
2. **变的**：digest 写了但源码已改（符号改名、配置键改名、路由改形状）。
3. **少的**：digest 描述了、源码已不存在（承接 `tool_policy` 这类删除）。

- 工具：`check_digest.py`（机械）+ 分域 agent（语义）。
- **验收**：每个分片提交「已核验断言数 / 修正数 / 新增数 / 删除数」四元组。

### P5 — `_faq_on_digested` 同步
52 篇问答式文档，重点是「答案里的代码路径与机制」是否还成立：

| FAQ | 2.2 影响 |
|-----|---------|
| 01/02/03 技能选择 | `tool_policy` 删除 → 精确技能选择机制变了（`allowed-tools` 降级） |
| 04 MCP | durable tasks / 按用户连接 / `mcp_scope` |
| 05 首跑流程 | 引用了不存在的 `deerflow/testing/models.py`（check_digest 已报） |
| 06 CLI/SDD | `--print/--json` 失败退出 1、多行编辑器、`debug.py` 171 行 |
| 07/08/09 图与中间件 | 中间件目录 37 → ? 需重新计数 |
| 10 配置灵活 | config.example +770 行 |
| 11 工作区组织 | 新 workspace 能力 |
| 12 设计哲学 | extension-first 段落改写 |
| 13 录制回放 | 路径失效 + 2.2 的 telemetry 增强 |

- **验收**：每篇逐个引用块核对完成；`answer.md` 里的链接全部可达。

### P6 — `_deerflow_application_agent_ready_development` 同步
31 篇 + `verify.mjs`（带测试 `verify.test.mjs`）：

- `application-development-model/` — 应用开发模型（扩展点是否变了）
- `repo-harness/` — guidance budgets / doc tests（上游 `scripts/check_agent_guidance*` 是否改了规则）
- `sdlc-reference/` — CI gates（`make test` 四分片、`skill-tests` job、`verify_versions.sh` 拒陈旧 `uv.lock`）、schema migrations（27→50）
- `_coverage/` — 语料维护规则
- **动作**：改内容后跑 `verify.mjs`（有测试的地方跑 `verify.test.mjs`）。
- **验收**：`node verify.mjs` 通过；`sdlc-reference` 的 gate 清单与 2.2.0 CI 一致。

### P7 — 收尾
1. `check_digest.py` → exit 0
2. 不变式自检：三目录之外与 `v2.2.0` 零差异
3. `SYNC.md` 锚点已是 #8（本计划已写），补充「影响的 digest」实际清单
4. `SYNC_LOG.md` #8 补「实际完成项」
5. 提交（一条 `docs(digest): sync #8 to v2.2.0 …`）
6. **推送仍需用户点头**（强推）

## 3. 硬规则（沿用 SYNC.md 铁律）

1. 三目录之内随便改，三目录之外**一个字节都不碰**（每次提交前跑 §5.4 自检）。
2. 不改上游源码来「迁就」digest——digest 跟着源码走，不是反过来。
3. 删源码对应的小节要**连带删上下文**（标题、索引、链接），不留悬空小节。
4. 行数/行号断言：改数字只是及格线，**必须顺带复核该小节描述的机制是否还成立**。
5. 每个分片改动后立即跑 `check_digest.py`，别攒到最后。

## 4. 风险与对策

| 风险 | 对策 |
|------|------|
| 1,239 commits 的语义变化无法穷尽 | 优先覆盖 2.2.0 Release 说明列出的 11 组 breaking changes + 13 个 Highlights（已提取到 SYNC_LOG #8），它们覆盖了 90% 的用户可见变化 |
| 分片 agent 改动互相冲突（同文件被两片改） | 先按「文件 → 唯一归属分片」切分；`internals/runtime/` 同时被 #1 和 #3 碰，约定 #1 负责 runtime 主体、#3 只改 `goal-continuation.md` |
| 行号大面积漂移，逐条修效率低 | 优先用 `check_digest.py` 批量定位；语义修正交给分片 agent |
| 改动量大导致一次提交难以审阅 | 按域分批提交（`docs(digest): sync #8 <域>`），最后合并说明 |

## 5. 复现命令

```bash
# 5.1 变更地图
git diff --name-status v2.1.0 v2.2.0 > /tmp/df22/all_changes.txt
git diff --name-only v2.1.0 v2.2.0 | awk -F/ '{print $1"/"$2"/"$3}' | sort | uniq -c | sort -rn

# 5.2 新增 / 删除
git diff --name-status v2.1.0 v2.2.0 | awk '$1=="A"{print $2}' | sort
git diff --name-status v2.1.0 v2.2.0 | awk '$1=="D"{print $2}' | sort

# 5.3 迁移链
git ls-tree -r --name-only v2.2.0 | grep -E 'persistence/migrations/versions/[0-9]{4}_'

# 5.4 不变式自检（必须 0）
git diff --name-only -z v2.2.0 ethan | tr '\0' '\n' \
  | grep -vE '^(_digested|_faq_on_digested|_deerflow_application_agent_ready_development)/' | grep -c .

# 5.5 机械校验（必须 exit 0）
python3 _digested/_upstream-sync/tools/check_digest.py
```
