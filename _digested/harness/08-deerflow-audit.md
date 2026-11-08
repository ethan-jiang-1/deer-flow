---
title: "deer-flow 仓库 Agent-Friendly 审计报告（60 条实测）"
description: "按 07 篇 60 条清单对 deer-flow 本仓库的逐条实证审计：五维打分、加权总评 A-、Top 问题清单、亮点清单与整改路线图。全部证据来自只读命令实测，日期 2026-06。"
---

# deer-flow 仓库 Agent-Friendly 审计报告（60 条实测）

> 审计日期：2026-06。方法：按 [07 篇](07-audit-checklist.md)的「怎么查」栏在仓库根执行只读命令（`find`/`wc -l`/`grep`/读 Makefile 与 CI 配置），每条给证据。局限见文末「审计方法说明」。

> **v2.1.0 复核**（sync #7，`345f08be`）：本表所有行数、文件数、`AGENTS.md` 行号引用已按该 tag 重新核对；评分与结论未变（原审计为 2026-06 的 rc0 快照）。diff 增量类断言（`+N 行`）按本轮同步口径保留。

## 结论速览

**总评：A-（加权 126/148，85%）**。deer-flow 在指令文件体系、验证闭环、可执行环境三个维度接近范本级；主要失分在：缺集中式安全边界（Never/Ask-first）与远程操作 guardrails、深层 AGENTS.md 超行数预算、无量化模块大小规则。

### 五维得分表

| 维度 | 条数 | ✅ | ⚠️ | ❌ | 得分/满分 | 权重 | 加权 |
|------|------|----|----|----|-----------|------|------|
| ① 上下文供给/可发现性 | 16 | 11 | 5 | 0 | 27/32 | ×1.5 | 40.5/48 |
| ② 可验证性/反馈闭环 | 12 | 11 | 1 | 0 | 23/24 | ×1.5 | 34.5/36 |
| ③ 可执行环境 | 10 | 9 | 1 | 0 | 19/20 | ×1 | 19/20 |
| ④ 可修改性/局部性 | 12 | 8 | 3 | 1 | 19/24 | ×1 | 19/24 |
| ⑤ 安全护栏 | 10 | 4 | 5 | 1 | 13/20 | ×1 | 13/20 |
| **合计** | 60 | 43 | 15 | 2 | — | — | **126/148 = 85%（A-）** |

### Top 问题清单（按严重度）

| # | 问题 | 对应条目 | 整改建议 |
|---|------|----------|----------|
| P1 | 无远程操作 guardrails：没有"只推 fork / 禁 force push / AI 贡献披露"类规则 | #59 | 参照 [airflow AGENTS.md](https://github.com/apache/airflow/blob/main/AGENTS.md) 增加 Commits/PRs 区块；或用 agent hooks 硬禁 `push --force` |
| P2 | 缺集中 Boundaries 区块（Never / Ask first 两档） | #52/#53 | 在根 AGENTS.md 增加 "Boundaries" 节：Never（提交密钥、手改生成物、破坏性 git）+ Ask first（跨包重构、新依赖）；禁令附安全替代路径 |
| P3 | 深层 AGENTS.md 超预算：backend 397 行、extensions 380、runtime 364、agents/memory 302、scripts 269（另根 238 行） | #5 | 按 Claude Code `/doctor` 标准修剪"可从代码推导"的内容；专项细节下沉或转 skills |
| P4 | 无量化模块边界规则；已有 3061 行的 `runtime/runs/worker.py` 等巨文件 | #39/#40 | 参照 [codex AGENTS.md](https://github.com/openai/codex/blob/main/AGENTS.md)：模块 ≤500 LoC 目标、>800 LoC 新功能开新文件；巨文件列入拆分 backlog |
| P5 | 未使用 path-scoped rules 机制（无 `.claude/rules/`、`.cursor/rules/`） | #9/#10 | 把模块专属细则从嵌套 AGENTS.md 拆到 `paths:`/`globs:` 作用域规则，进一步省常驻上下文 |
| P6 | 仓库不携带共享 agent 强制层（`.claude/` 整体 gitignored，无版本化 hooks/permissions） | #51 | 可加版本化的 `.claude/settings.json`（deny 危险命令）供团队共享；注意与"settings.local 不入库"的既有约定区分 |

---

## 逐维详表（60 条实测）

评分：✅=2 ⚠️=1 ❌=0。证据为命令输出摘录或文件路径+行号。

### 维度一：上下文供给 / 可发现性（27/32）

| # | 条目 | 评分 | 证据 |
|---|------|------|------|
| 1 | 规范指令入口 | ✅ | 计数口径：`*AGENTS*.md` 共 **29 个** = 恰为 `AGENTS.md` 的 **28 个**（`scripts/check_agent_guidance.py` 自报 "28 AGENTS.md"）+ 变体 `backend/docs/GITHUB_AGENTS.md`；根 `AGENTS.md` 238 行 |
| 2 | 推荐章节覆盖 | ✅ | 根 AGENTS.md 章节：What is DeerFlow / Service Topology / Repository Map / **Commands** / Cross-Cutting Conventions（含安全注意）；backend/AGENTS.md 另有 Commands/Architecture/Code Style |
| 3 | 根文件=定位层 | ✅ | 根 AGENTS.md 自述 "monorepo orientation layer… read that module's guide"；`backend/AGENTS.md`、`frontend/AGENTS.md` 等 27 个非根文件承接深度（28 个 `AGENTS.md` 减去根） |
| 4 | 嵌套就近生效 | ✅ | 嵌套覆盖达模块级：`harness/deerflow/{agents,mcp,sandbox,skills,config,runtime,…}/AGENTS.md` 共 19 个（含 `agents/memory/`、`persistence/migrations/` 三层深度） |
| 5 | 单文件长度 | ⚠️ | `wc -l`：v2.1.0 实测超 200 行的共 **6 份**——根 238、backend 397、extensions 380、runtime 364、agents/memory 302、scripts 269（[Claude Code 建议 ≤200 行](https://code.claude.com/docs/en/memory#my-claude-md-is-too-large)）；按文件自身的 context 预算（`check_agent_guidance.py` 的 KiB 软/硬线）另见 [harness-engineering/01](../harness-engineering/01-agent-docs-system.md) |
| 6 | 无矛盾指令 | ⚠️ | 抽查根/backend/frontend/extensions 四文件的命令与格式规则未见冲突；**未做全 28 文件系统比对（受限）** |
| 7 | 不复述可推导内容 | ⚠️ | 根文件含 "Repository Map" ASCII 目录树——但为带注释的导航地图（服务端口、模块归属），属高信号；backend/AGENTS.md 的架构综述篇幅偏大，`/doctor` 口径下可修剪 |
| 8 | 指令具体可验证 | ✅ | 全是命令式："cd backend && make test"、"python -m pytest tests/path/to/test.py::test_func -q"、"根 PORT 值仅是 Docker ingress 配置" |
| 9 | path-scoped rules | ⚠️ | 无 `.claude/rules/`；**但** Claude Code 原生"子目录 AGENTS.md 读到时按需加载"部分达成同等效果（[memory docs](https://code.claude.com/docs/en/memory)） |
| 10 | Cursor 陷阱规避 | ⚠️ | 无 `.cursor/rules/`（N/A 裸 .md 风险）；Cursor 走 AGENTS.md 支持，功能可用但放弃 globs 作用域能力 |
| 11 | harness 兼容策略 | ✅ | `CLAUDE.md`（5 行）= 说明 + `@AGENTS.md` import，且明文 "Don't edit CLAUDE.md"；import 在工作目录内，无外部审批问题。Codex 口径：根 `AGENTS.md` 即其原生入口，✅ 成立 |
| 12 | 命名可 grep | ✅ | 抽样：`merge_skill_context`、`describe_skill`、`skill_activation`、`pnpm.py` 等语义化；`utils/` 偏泛（个别） |
| 13 | 无语义近似 distractor | ⚠️ | 术语使用一致（DeerFlow/harness/extension），但**无 airflow 式明文命名消歧规范**（对照其 "Dag vs DAG" 规则） |
| 14 | 结构化格式 | ✅ | 根文件 6 个 `##`（v2.1.0 实测）+ 全 bullet/表格；backend/frontend 同构 |
| 15 | 活文档 | ✅ | 根 AGENTS.md L220（v2.1.0；rc0 为 L221）"Documentation update policy — keep docs in sync with code… in the same change set" |
| 16 | import 可控 | ✅ | 唯一 import 为 `@AGENTS.md`（同目录）；`.gitignore` L45 排除 `.claude/`，个人设置不入库 |

### 维度二：可验证性 / 反馈闭环（23/24）

| # | 条目 | 评分 | 证据 |
|---|------|------|------|
| 17 | 命令文档化 | ✅ | 根 AGENTS.md "Commands" 节：setup/doctor/install/dev/stop/docker 全套 + per-module（`make test`/`lint`、`pnpm check`/`test`） |
| 18 | 单测入口 | ✅ | 根 AGENTS.md 明文：`python -m pytest tests/path/to/test.py::test_func -q`、`pnpm rstest run <pattern>` |
| 19 | 快速默认子集 | ✅ | `backend/Makefile` L21-23：`make test` = `pytest -m "not live" --ignore=tests/blocking_io tests/ -v`（离线子集）；`backend/tests/` 下 738 个 `test_*.py`（含 `blocking_io/`，顶层 690）——v2.1.0 实测 |
| 20 | 测试确定性 | ✅ | `pyproject.toml` L85 marker `"live: tests that call real external APIs and require explicit opt-in"`；`backend/tests/AGENTS.md` 明文要求"explicit synchronization such as threading.Event rather than sleep-based timing" |
| 21 | 外部依赖替身 | ✅ | `backend/tests/_replay_fixture.py`、`replay_provider.py` 存在；`frontend/tests/` 有 `e2e-record/`；CI 有 `replay-e2e.yml` |
| 22 | 测试布局镜像 | ✅ | `backend/tests/test_compose_default_bind_host.py` 等按 `test_<模块>.py` 平铺于 `tests/`；`tests/AGENTS.md` 就近说明不变量与边界 |
| 23 | 本地=CI 同源 | ✅ | CI 实测：`backend-unit-tests.yml` L116 `make test-shard SPLITS=4 GROUP=…`（与本地同一 target，`.test_durations` 基线共享）；`frontend-unit-tests.yml` L43 `make test`；lint-check.yml 跑 `pnpm format/lint/typecheck` |
| 24 | 格式检查归 CI | ✅ | 根 AGENTS.md L226-227（v2.1.0；rc0 为 L227-228）"run make format… **CI enforces ruff format --check**"；pre-commit 有 ruff/ruff-format/uv-lock-check/eslint/prettier 五钩子 |
| 25 | agent 知道哪些别跑 | ⚠️ | `test-live`/`test-blocking-io`/手动 e2e 分离清晰，但"完整套件先问用户"类升级规则**未成文**（对照 codex AGENTS.md） |
| 26 | flaky 出口 | ✅ | `live` marker 显式 opt-in（`DEER_FLOW_RUN_LIVE_TESTS=1`）；blocking_io 独立目录独立 target |
| 27 | 失败可行动 | ✅ | 未实跑测试（受限）；间接证据：`make doctor`/`support-bundle`、CI 收集诊断的既定模式、tests/AGENTS.md 对确定性断言的规范 |
| 28 | 约束测试钉子 | ✅ | `test_compose_default_bind_host.py` 钉"每个发布端口需显式 bind"；根 AGENTS.md L47 明文引用该测试（另有 L191-192 的单测示例）；`verify_versions.sh` + `verify-versions.yml` CI 钉版本 lockstep |

### 维度三：可执行环境（19/20）

| # | 条目 | 评分 | 证据 |
|---|------|------|------|
| 29 | setup 顺序显式 | ✅ | 根 AGENTS.md "Prerequisites before make dev"：`make config` → `make install` → `make dev` 三步成文 |
| 30 | 缺前置的失败模式 | ✅ | "Without `config.yaml` present, services fail to boot" 明文 |
| 31 | 模板/真实分离 | ✅ | `config.example.yaml`、`extensions_config.example.json` 入库；`.gitignore` L33/35 排除真实文件 |
| 32 | 就绪探测真实 | ✅ | 根 AGENTS.md：生产启动 "must surface Compose status and recent Gateway logs instead of claiming the stack is running"；`make up` 等 `/health` 探针 |
| 33 | 确定性包装器 | ✅ | 根 Makefile 39 个 target 统一入口；`scripts/pnpm.py` 吸收 Windows/POSix 差异（pnpm.cmd 优先序 + Corepack fallback） |
| 34 | 隐式全局状态 | ✅ | 运行时配置可经 Gateway API 编辑但有文档；本地编排 pin Next.js 3000 防止 `.env` 污染（根 AGENTS.md 明文）；未发现未文档化前置步骤 |
| 35 | 编码/平台 | ✅ | 根 AGENTS.md "Skill text encoding — must pass encoding='utf-8' rather than relying on the platform locale"；pnpm.py 跨平台 |
| 36 | 日志可定位 | ✅ | 根 AGENTS.md "Logs" 节：docker-logs、各终端 pane、浏览器 console/Gateway terminal 分工 |
| 37 | 版本 pin | ✅ | `uv.lock`/`pnpm-lock` 入库；pre-commit `uv-lock-check`；CI pinned pnpm 10.26.2（frontend-unit-tests.yml L35）；`verify-versions.yml` |
| 38 | 破坏性脚本辨识 | ⚠️ | `extension-remove`、`stop`、`down` 等在 `make help` 可见，但无统一 danger 标记约定 |

### 维度四：可修改性 / 局部性（19/24）

| # | 条目 | 评分 | 证据 |
|---|------|------|------|
| 39 | 深模块薄接口 | ⚠️ | 架构分层清晰（harness/app split、middleware chain），但存在巨文件：`runtime/runs/worker.py` **3061 行**、`e2b_sandbox_provider.py` 2892、`lark_cli.py` 2846、`sandbox/tools.py` 2789（`wc -l` top5 实测） |
| 40 | 模块大小规则 | ❌ | grep 根/backend/frontend AGENTS.md：**无**任何量化模块/文件大小规则（对照 codex "≤500 LoC, >800 split"） |
| 41 | API 冻结策略 | ⚠️ | `packages/extension-api/` 被根 AGENTS.md 定为 "public extension contract"，五类贡献点有 reference example；但无 temporal 式"public/internal 分界 + 禁改签名"明文 |
| 42 | 契约显式 | ✅ | `contracts/`：run_event_stream、subagent_status、slash_skill、skill_review 四组 JSON 契约；版本四源 lockstep + CI 阻断 |
| 43 | 生成物隔离 | ✅ | frontend/AGENTS.md L69-70/96："`ui/`、`ai-elements/` auto-generated, ESLint-ignored… **don't manually edit these**" |
| 44 | 命名空间消歧 | ✅ | 工具命名 `bash/web_fetch/glob/...` 与 portable 拼写映射表成文（`packages/harness/deerflow/skills/AGENTS.md` L4）；MCP/skills/extensions/integrations 边界清晰 |
| 45 | 高频操作聚合 | ✅ | `make setup`（交互式向导）、`make doctor`、`make support-bundle`（红acted 诊断 + AI issue 草稿一键生成）均为复合任务单入口 |
| 46 | 文档与代码同源 | ✅ | "Documentation update policy… in the same change set"；版本 lockstep 由脚本+CI 强制 |
| 47 | 组件复用路径 | ✅ | frontend/AGENTS.md 技术栈节 + Code Style 节指明组件来源与生成流程 |
| 48 | 涟漪可枚举 | ✅ | 仓库地图 + 模块归属 + contracts + "新发布端口需测试钉住"等显式关联 |
| 49 | 危险区前置成文 | ✅ | extensions/AGENTS.md 380 行专讲"扩展代码以 Gateway 权限执行"的信任边界；sandbox/AGENTS.md、middlewares/AGENTS.md 各覆盖其危险区 |
| 50 | 工具面数量 | ⚠️ | 根 Makefile 39 target（`^[a-zA-Z_][a-zA-Z0-9_-]*:` 实测）+ `scripts/` 下 35 个文件（`-maxdepth 1 -type f`，不含 `AGENTS.md`；另有 `scripts/wizard/` 子目录）≈ 74 个入口；有 `make help` 聚合，但超出"一屏可枚举" |

### 维度五：安全护栏（13/20）

| # | 条目 | 评分 | 证据 |
|---|------|------|------|
| 51 | 软/硬约束分离 | ⚠️ | 硬约束主要由 CI 承担（format check、verify-versions、skill-review-ci）；**仓库不带版本化 agent hooks/permissions**（`.claude/` 整体 gitignored，实测 `.claude/settings.local.json` 仅个人 allow 规则）——设计上可辩护，但团队共享强制层缺位 |
| 52 | 集中 Never 清单 | ⚠️ | 禁令散落："never commit them"（根 L185 config）、"Never commit upstream dataset text, credentials…"（backend L101）；**无集中 Boundaries 区块** |
| 53 | 禁令带替代路径 | ⚠️ | 多数禁令有上下文说明（如 extensions 信任源、skill UTF-8），但无 electron 禁 npx 式"禁 X→用 Y"标准格式 |
| 54 | 禁令就近 | ✅ | 模块专属规则在嵌套文件：skills 的 symlink/嵌套拒绝在 `skills/`、compose bind 规则在根、IM 通道规则在 `app/channels/` |
| 55 | 指令文件攻击面 | ✅ | `.claude/` gitignored（个人设置不入库）；skill 安装器拒绝嵌套 SKILL.md 与 symlink 逃逸（源码印证）；extensions 配置"deliberately kept out of the API-writable extensions_config.json"（根 AGENTS.md L76-77） |
| 56 | agent 环境限制成文 | ✅ | extensions 节："both build hooks and extension code execute with Gateway privileges, so only trusted operator sources belong in this path"；scheduled-task 非交互模式的凭证丢弃规则明文 |
| 57 | 凭证声明式注入 | ✅ | SKILL.md frontmatter `required-secrets`（`packages/harness/deerflow/skills/AGENTS.md` L23："name is both the lookup key and the env var name"） |
| 58 | 高危 human-in-the-loop | ⚠️ | 扩展变更需 Gateway 重启 + 仅信任源（软性门禁）；merge/discard 类操作有审批；但无成文的"高危操作清单+确认流程" |
| 59 | 远程操作 guardrails | ❌ | grep 三份主 AGENTS.md：**无** push/force-push/fork/AI 披露类规则（对照 airflow 的 "Push only to the user's fork… Never list an agent as a commit co-author"） |
| 60 | 安全模型文档化 | ⚠️ | `SECURITY.md` 存在；extensions/scheduled-task 的威胁模型在对应 AGENTS.md 内有成文；但无 airflow 式"漏洞/已知限制/加固机会"三分法总纲 |

---

## 亮点清单

| 亮点 | 证据 | 对应条目 |
|------|------|----------|
| **28 个分层 AGENTS.md 的三层体系**（根定位层 → backend/frontend → harness 模块级） | `find`/`git ls-files` 实测（恰为 `AGENTS.md` 者 28 个，另有 `backend/docs/GITHUB_AGENTS.md` 变体）；根文件自述 orientation layer | #1/#3/#4/#54 |
| **CLAUDE.md 薄 shim + "Don't edit" 明文** | 5 行文件，`@AGENTS.md` import | #11 |
| **CI 与本地同源的时长感知分片** | CI 直接跑 `make test-shard`，`.test_durations` 基线共享 | #23 |
| **离线默认子集 + 显式 flaky 出口** | `-m "not live"`、blocking_io 隔离、live 需 env opt-in | #19/#26 |
| **测试目录自带 AGENTS.md**（确定性断言规范：禁 sleep 阈值、teardown 不泄漏线程） | `backend/tests/AGENTS.md` | #20/#22 |
| **约束钉进测试而非只写文档** | `test_compose_default_bind_host.py`、`verify_versions.sh` | #28 |
| **readiness 不谎报** | "must surface Compose status… instead of claiming the stack is running" | #32 |
| **跨平台确定性包装器** | `scripts/pnpm.py`、根 Makefile 39 targets、`make help` | #33/#36 |
| **生成物隔离明文** | frontend/AGENTS.md "don't manually edit these" | #43 |
| **extensions 信任边界成文** | "execute with Gateway privileges… only trusted operator sources" | #49/#56 |
| **凭证声明式注入（required-secrets）** | SKILL.md frontmatter 协议 | #57 |

## 整改路线图

**Quick wins（半天内）**

1. 根 AGENTS.md 增加 "Boundaries" 节：Never（提交 config.yaml/密钥、手改 `ui/`/`ai-elements/`、破坏性 git）+ Ask first（跨包重构、新依赖、发版）——P2。
2. 增加 Commits/PRs 简节：只推 fork/分支保护说明、AI 贡献披露要求——P1。
3. backend/frontend AGENTS.md 各加一行"全量/集成套件先问再跑"的成本升级规则——#25。

**中期（1-2 周）**

4. 按 `/doctor` 口径修剪超 200 行的 6 份 AGENTS.md（v2.1.0 实测 397 / 380 / 364 / 302 / 269 / 238 行 = `backend/`、`extensions/`、`runtime/`、`agents/memory/`、`scripts/`、根；rc0 为 397/379/351/302/260/239，本轮 runtime +13、extensions +1、scripts +9、根 −1），可推导内容删、专项下沉——P3。
5. 引入模块大小规则并建巨文件清单（worker.py 3061 行等 top5 列入拆分 backlog）——P4。
6. 把 skills/extensions 等模块细则拆到 `.claude/rules/`（`paths:` 作用域），验证注入生效——P5。

**长期（按需）**

7. 评估提交版本化 `.claude/settings.json`（deny 高危命令）作为共享强制层——P6。
8. 命名消歧规范成文化（类比 airflow 的 Dag/DAG 条款）——#13。

## 审计方法说明

- **日期**：2026-06，单次只读扫描。
- **harness 口径**：Claude Code（CLAUDE.md shim → AGENTS.md，import 在工作目录内、无需外部审批）与 Codex（根 AGENTS.md 原生发现，238 行 < 32KiB 上限）两个入口均验证成立；未实际启动 agent 会话验证注入（**未验证/受限**，#6/#27 为抽查或间接证据）。
- **局限**：① 未做 28 个 AGENTS.md 的全量矛盾比对；② 未实跑测试套件验证 #27；③ Cursor/Gemini CLI 口径未实测（依赖文档行为推断）；④ `.claude/settings.local.json` 为审计会话自身产物，不计入仓库评分。
- 评分与依据的权威来源见 [07 篇](07-audit-checklist.md)各条目"依据"列。
