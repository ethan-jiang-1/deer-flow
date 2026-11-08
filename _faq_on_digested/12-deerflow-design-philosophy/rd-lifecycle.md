# 研发流程走查：DeerFlow 如何开发、验证和发布自己

前一篇文章走查的是"一次任务在运行时如何走到交付"；本文走查另一个正交的循环——**仓库自己如何被开发、验证、评审、发布和运维**。两者共用同一种思维（声明、执行、证据分开），但对象不同：前者治理 agent 的 run，后者治理工程师（以及参与开发的 agent）的 change。

> **读法约定**：每个环节标注证据等级——**成文标准**（AGENTS.md/模板/指南写明的要求）、**机器门禁**（CI workflow 或测试自动执行、能挡住合并或发布的检查）、**归纳**（从实现组合推出的取舍）、**边界**（仓库文件无法证明的部分）。仓库里没有 GitHub 分支保护、required checks、reviewer 批准的配置文件，这些只能算"不可从本仓核实"。

## 1. 范围对齐：非平凡变更先有 issue

PR 模板要求先写 trigger 与 pain，并明确建议："For non-trivial features, please open an issue/discussion first to align on scope before writing code."（**成文标准**）（`../../.github/pull_request_template.md` L4-12）这是模板里的引导语，没有 CI 检查 PR 是否挂了 issue——无 issue 的 PR 不会被机器拦下。（**边界**）

> 🔄 同步 #8（v2.2.0）：引证由 `5-12` 更正为 **L4-12**（首行是 `Fixes #`）。结论未变：`.github/workflows/` 下的 workflow 没有一条检查 PR 正文是否引用了 issue。

## 2. 设计先行：spec 拥有决策，plan 只负责排序

大型变更走 RFC → spec → implementation plan 三级，且分工写得很硬。Projects Phase 2 的 spec 自称 "Source of truth: This spec governs Phase 2 in full"，并带 revision pin（每个对现状的论断都钉在具体 commit 上核对过）。（`../../docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md:4-9`）

实现计划则明确降级自己："every design decision, error mapping, and review-gate is owned by the spec. This document sequences files, symbols, and verification only. Where the spec and code disagree, the spec's deviation register (§10) wins."（**成文标准**）（`../../docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md:1-18`）

设计文档自带三类后续可执行的章节：**Testing Strategy**（分层列出单测/集成/前端/mock E2E/真路径验收，scheduled-tasks spec 甚至写明 real-path validation "Required before claiming feature complete"）、**Documentation Updates Required**（代码落地时 README/AGENTS.md 必须同步更新）、**Code Review Checklist**（评审条目编号列出，如"harness persistence 不 import app\*"）。（`../../docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md:515-584`）实现按 slice 推进，每个 slice 收尾时重读 spec §15 检查单、跑 lint+test，并发测试被标为 "hard requirement, not optional polish"。（`../../docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md:103-112`）

**归纳**：这套分级不是流程装饰，而是把"决策放哪"变成产权问题——设计决策只有一份权威（spec），偏离要登记（deviation register），实现计划不允许私自重新设计。但它是**按项目成文的纪律**，不是全仓强制"所有改动先写 spec"的门禁。

## 3. 实现：TDD 是成文军规，红绿靠自报

backend 指南用大写 MUST 定死 TDD："Every new feature or bug fix MUST be accompanied by unit tests. No exceptions."，并要求改动前后都跑 `make test` + `make test-blocking-io`。（**成文标准**）（`../../backend/AGENTS.md` L208-220「Test-Driven Development (TDD) — MANDATORY」）根 AGENTS.md 把同一条提升为跨模块约定，同时规定文档同步策略（用户可见行为改 README、开发/架构改 AGENTS.md，**同一个 change set 内完成**）。（`../../AGENTS.md`「Cross-Cutting Conventions」第一条「Update `README.md` for user-facing changes and the relevant `AGENTS.md` for development/architecture changes **in the same change set**.」）

> 🔄 同步 #8（v2.2.0）：两处行号失效——`backend/AGENTS.md:243-256` 现在落在前端环境变量小节（TDD 原文在 **L208-220**），`AGENTS.md:222-227` 也不再指向那条约定。**引证纪律**：这类顶层指南的章节会随内容增补整体位移，引小节标题比引行号稳。

测试资产有命名与车道规则：禁止测试模块互相 import（共享夹具进 `_` 前缀 helper）；live 车道归属由 `pytest.mark.live` 标记决定，而"无凭证时优雅跳过"是**每个测试自己的守卫责任**——"A `_live` filename suffix without the marker is a bug"。（**成文标准**）（`../../backend/tests/AGENTS.md`）

> 🔄 同步 #8（v2.2.0）：具体行号 `5-8` 不再对应，改为整篇引用。

诚实边界在 PR 模板里写得最清楚：bug fix 应当"encoded as a failing test that goes red before the fix"，并要求作者自报 "Did it go red on `main` and green on this branch? (yes / no)"；写不起 red test 要解释替代方案。（**成文标准 + 自我声明**）（`../../.github/pull_request_template.md` L46-53「Bug fix verification」）**CI 只验证最终绿，不验证曾经红**——没有 workflow 会检出 main 重放新增测试。（**边界**）

## 4. PR 与评审：结构化的自我声明 + 信任分级自检

PR 模板把变更描述强制面向用户视角（"from a user's / caller's perspective, not as a code diff"），并要求勾选 Surface area 让评审者据此划范围；勾到 Agents/LangGraph 时还附带一条 prompt 信任自检：新 prompt 文本里每个数据源的信任级别是什么、该走哪个通道——模型可影响的内容必须走 untrusted 数据通道，**永远不许插值进框架持有的 system 文本**，即使做过中和也不行（"never interpolated into framework-owned system text, **even neutralized**"）。（**成文标准**）（`../../.github/pull_request_template.md` L15-36「What changed」+「Surface area」）

> 🔄 同步 #8（v2.2.0）：`15-35` → **L15-36**。这一条在 v2.2.0 有了被反向印证的实例：`prompt.py` L437-445 对 agent 可编辑的 `config.description` 做 `html.escape(...)`，注释里点名「the same class as the #4137 `<soul>`, #4097 memory, and #4128 skill render-site fixes」——**同一类渲染点越权问题已经被修了至少四次**，这正是模板要求逐项自检的原因。

AI 参与是显式披露项：用了什么工具、怎么用的，外加一句人的责任声明——"I've read and understand every line of this change and take responsibility for it — it's not unreviewed AI output." CONTRIBUTING 补充：不填 AI 披露的 PR "may be asked to fill it in before review"。（**成文标准**）（`../../.github/pull_request_template.md` L64-76「AI assistance」） （`../../CONTRIBUTING.md` L323-336「AI assistance disclosure」）

> 🔄 同步 #8（v2.2.0）：`CONTRIBUTING.md:320-333` → **L323-336**。措辞也值得注意：模板开头直接写「DeerFlow is an AI project — most PRs here use AI coding tools, and that's welcome. Disclosing it just helps reviewers calibrate how closely to read the diff.」——**披露被定位成"帮 reviewer 校准阅读强度"，不是"合规审查"**。

Validation 节要求写出**实际运行过的命令**，按改动面选择最低检查集。（`../../.github/pull_request_template.md` L58-62「Validation」）仓库内没有 CODEOWNERS 或 reviewer 批准的配置文件；人工评审是否被分支保护强制，**无法从仓库文件判定**。（**边界**）

## 5. CI 门禁：哪些检查真的是机器在挡

这是"声明"与"执行"分界最清楚的一层。逐个数实际 workflow：

| 门禁 | 机器行为 | 触发与例外 |
|---|---|---|
| 格式/lint | backend `make lint`（含 `ruff format --check`）+ 前置 `uv lock --check`；frontend format/lint/typecheck/build | push + PR（`../../.github/workflows/lint-check.yml` L54-82 backend job、L84 起 frontend job） |
| agent 文档预算 | `check_agent_guidance.py` 按 diff 基线检查 AGENTS.md 软/硬预算 | push + PR（`../../.github/workflows/lint-check.yml` L25-40） |
| label 声明 | `check_label_declarations.py` 保证 `triage.yml` 打的每个 label 都在 `labels.yml` 里声明过 | push + PR（`../../.github/workflows/lint-check.yml` L51-52） |
| 后端单测 | 默认离线套件按真实时长分 4 片并行（fail-fast 关闭），Postgres/Redis 作为 service 容器起 | 仅非 draft PR（`../../.github/workflows/backend-unit-tests.yml:48-116`） |
| 最小安装可收集 | 按文档贡献者路径 `uv sync --group dev` 后只做 `pytest --collect-only`，证明无 extras 也能收集全套 | 仅非 draft PR（`../../.github/workflows/backend-unit-tests.yml:17-46`） |
| blocking-I/O | `make test-blocking-io` 严格 Blockbuster 门 | **仅 `backend/**` 路径变更触发**（`../../.github/workflows/backend-blocking-io-tests.yml:3-13,47-49`） |
| 前端 E2E | Playwright | **仅 `frontend/**` 变更触发**（`../../.github/workflows/e2e-tests.yml:3-13`） |
| replay E2E | 前后端契约两层回放：backend golden SSE 序列 + 真前端渲染回放 turn | **契约两侧任一变更触发**，"a backend change can no longer pass without the frontend-facing checks running"（`../../.github/workflows/replay-e2e.yml:3-37`） |
| skill 审查 | SkillScan + 豁免清单（head 不能自授权豁免） | 仅技能相关路径（`../../.github/skill-review-waivers.v1.json`） |
| extension 打包 | 扩展包结构与依赖声明检查 | 仅扩展包相关路径（`../../.github/workflows/extension-package-check.yml`） |
| Windows live 策略 | 约束 live 车道在 Windows 上的行为 | 仅相关路径（`../../.github/workflows/backend-windows-live-policy.yml`） |

（**机器门禁**，均已核对 workflow 源）几个容易过度概括的点：**draft PR 会跳过主要测试 job**（backend unit 两个 job 都带 `if: github.event.pull_request.draft == false`，`backend-unit-tests.yml` L21/L49；e2e/replay/skill 同类）；"每个 PR 跑全部门"并不成立——blocking-I/O、E2E、replay、skill/extension 审查全部按路径分流；`make test-live` 从不进 CI。（`../../CONTRIBUTING.md` L355-358，live 套件明确标注 "explicit opt-in"）路径过滤本身是取舍：快，但跨边界改动（如改动被多方调用的公共工具）是否触发对应门禁，需要评审者自行判断覆盖面。（**边界**）

> 🔄 同步 #8（v2.2.0）：`lint-check.yml` 在 v2.2.0 多了 `label-declarations` job。另外 **replay E2E 的门禁形状值得逐字读**——它的设计注释直接把自己写成一条反例修复：「Triggered by changes on EITHER side of the contract so a backend change can no longer pass without the frontend-facing checks running.」（`replay-e2e.yml` L6-8；trigger 路径含 `frontend/**`、`backend/app/gateway/**`、`backend/packages/harness/**` 与 replay fixture）。**这是"路径过滤有盲区"这条边界被局部修掉的实例**：不靠 reviewer 判断，而是把两侧路径都列进 trigger。

## 6. 架构、文档、工具链也是被测契约

DeerFlow 把"本该靠 review 纪律维持的规矩"写成测试：

- **架构边界**：harness 永不 import app，由 AST 扫描测试执行，架构图上的箭头有红绿语义。（`../../backend/tests/test_harness_boundary.py`）
- **文档即测试**：`test_middleware_documentation.py` 直接 `exec()` 文档里的 middleware 示例并断言链顺序与 guard 清单不漂移。
- **AGENTS.md 预算**：给 agent 的指令文档按目录深度限软/硬预算，超线是 CI error 而非劝告。（`../../.github/workflows/lint-check.yml:13-39`）
- **CI 工具链钉住**：`test_ci_uv_version_pin.py` 强制 Dockerfile 与**所有** workflow 里的 uv 版本一致，升级 uv 必须是"一个显式、可评审的变更"，防止"CI 用新 uv 重写 lock 仍然全绿、生产镜像里的旧 uv 读不了 lock"。workflow 内注释写的是 "Must match backend/Dockerfile's UV_IMAGE tag; pinned by backend/tests/test_ci_uv_version_pin.py"——v2.2.0 里这句话出现在**至少四个** workflow 中（`lint-check.yml` L65、`backend-blocking-io-tests.yml` L40、`replay-e2e.yml` L61 与 L84、`skill-review-ci.yml` L92），说明新增一个跑 uv 的 workflow 就得同步这条 pin。

  > 🔄 同步 #8（v2.2.0）：旧引证 `backend-unit-tests.yml:37-38` / `lint-check.yml:54-55` 已漂移，真实位置见上（`lint-check.yml` 里那条在 **L65**）。这条原则本身也升级了——从"两个 workflow"变成"任何执行 `uv sync` 的 workflow"，覆盖面更宽，风险面也更大。

**归纳**：这一层的共同句式是"谁来监督监督者？——下一个测试"。规矩不依赖记忆或个人权威，而是每 PR 跑的红绿检查。但注意它们钉的是**结构与一致性**，不证明业务行为正确。

## 7. 发布：tag 驱动 + 版本门

发版 tag 驱动：维护者改版本源、更新 changelog、commit、打 `v*` tag，推送触发发布 workflow——**没有单独的 release 脚本替你做 bump**。版本号必须在**五处**完全一致：`backend/pyproject.toml`、`backend/packages/harness/pyproject.toml`、`frontend/package.json`、Helm Chart 的 `version` 与 `appVersion`；加上 tag 本身共六源。（`../../RELEASING.md` L9-21「Version sources」；L3-7 说明 tag 驱动）

> 🔄 同步 #8（v2.2.0）：旧版写"四处一致（backend pyproject、frontend package.json、Chart 的 version+appVersion），加 tag 共五源"——**漏了 `backend/packages/harness/pyproject.toml`**。正确是**五处版本源 + tag = 六源**。这个漏项很典型：split-package 仓库里 harness 是独立包，有自己的 `version`，`scripts/verify_versions.sh` 与 `uv.lock` 都会校验它。

`verify-versions.yml` 在 tag 上校验所有源等于 tag（`RELEASING.md` L150-170「Version gate」），container/chart 发布 job 显式 `needs: verify-versions`——任何一处漂移就**跳过全部镜像与 chart 发布**。（**机器门禁**）（`../../.github/workflows/verify-versions.yml`） （`../../.github/workflows/container.yaml`）

**版本门还有一个常被漏掉的校验**：`backend/uv.lock` 里也记着根包版本（PEP 440 形式），所以门禁跑的是 `uv lock --check` 而不是字符串比对。原文的理由值得照抄——「Without that check, a lock left on the previous version would pass the gate and then fail the backend image's `uv sync --locked`, **after the chart and the other images had already published**.」（`RELEASING.md` L158-162）。**这是"部分发布"这类最难恢复的失败模式被前置消掉的具体例子**。

nightly 构建刻意不走版本门（无 tag），也不碰 `latest` 标签，并且用 `APP_VERSION` build-arg 把 About 页版本改写成 `<base>-nightly.<YYYYMMDD>-<short_sha>`，让镜像自己说明它不是 release。（`RELEASING.md` L28-32、L104-122）

注意门禁的不对称：**发布门强于日常 PR 门**——普通 PR 的 CI 并不做完整生产部署/启动升级/回滚验收；real-path 现场验收只在个别 spec 里被要求（"Required before claiming feature complete"），且属于人工步骤，不是普遍 CI 门。（**边界**）（`../../docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md:553-563`）

## 8. 数据演进：只追加的迁移链 + 启动时升级 + fail-closed

每个 ORM 变更（新列/新表/新索引）**必须**以 alembic revision 交付；Gateway 启动自动 `upgrade head`，常规生产升级无需手工命令；revision 只能接在当前 head 之后，**不许插入已发布 revision 之前**——插入会被既有数据库当作"已执行的祖先"跳过，`0023_run_change_seq` 插队事故（#5516）就是靠 `0025_repair_run_change_seq` 修复的。（**成文标准，事故已回写为修复 migration + 回归测试**）（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:5`）

bootstrap 对数据库状态 fail-closed：未知 revision、空版本表、多版本行一律拒绝启动——hybrid bootstrap 的状态表 **6 行**，其中两行是「refuse startup」、一行是「fail closed and refuse to start」。（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md` L9-18 的 hybrid bootstrap 表）仓库刻意**不提供** `make migrate`/`make migrate-stamp` 目标——"There is no `make migrate` / `make migrate-stamp` target on purpose — routine upgrades execute at Gateway startup; the documented offline recovery is reserved for the audited out-of-tree schema."（同文件 **L107**）

确实需要离线修复时，恢复文档要求停掉所有写入者、先备份、逐步核验确切 schema 形态再操作，且该恢复路径本身有回归测试钉住。（`../../docs/database-forward-revision-recovery.md`，全文 79 行）

> 🔄 同步 #8（v2.2.0）：引证 `7-16` → **L9-18**，`91` → **L107**；`21-40`/`74-79` 的区间不再对应，建议整篇引用而不切行。v2.2.0 的 bootstrap 表还多了一行值得注意的「`0019_thread_incarnations` with all current ORM tables/columns → warn and skip migration」——**这是唯一不升级也不拒绝的分支**，判据是「表与列是否齐全」，而不是版本号是否最新。

迁移没有独立 CI workflow；迁移测试随单测套件执行。**归纳**：升级路径的安全模型是"前向兼容 + 启动即迁移 + 未知状态拒绝启动"，把"部署时忘了跑迁移"这类人为失误从流程里消掉，而不是要求人记住它。

## 9. 运维反馈与失败回写

- **运维侧**：`make support-bundle` 产出脱敏的 issue summary、AI 辅助填报草稿（草稿刻意不编造复现步骤）和 triage 信号，且明说不含 `.env`、原始对话和 workspace 文件。（`../../CONTRIBUTING.md:383-413`）
- **评审侧**：maintainer-orchestrator skill 的设计笔记把 agent 评审钉在**评论面**（comment-only，不碰代码/分支/发布），公开评论要求 confidence 与 severity **双轴同时达标**，低于门槛的发现进维护者私有通道；评审哲学原文是 "Evidence over a green check. CI status is a signal, not a verdict."（`../../docs/agents/maintainer-orchestrator-design.md:17-32`） （`../../docs/agents/maintainer-orchestrator-design.md:38-45`）
- **失败 → 机制**：uv 版本漂移风险变成 pin 测试；migration 插队事故变成 0025 修复 migration + 回归；AGENTS.md 膨胀变成预算 CI。**归纳**：DeerFlow 的跨会话工程学习不依赖个人记忆，而是把每次事故回写成可执行的规则/门禁/契约——学习发生在仓库，不在模型。

**边界**：这类回写有大量实例但**没有全仓强制的 postmortem/ADR 门禁**——"失败必须沉淀成机制"是文化惯性而非可检查的流程。

## 10. 企业应用框架的信任与兼容面

作为可被企业 fork/嵌入的框架，仓库还显式治理几条"应用框架特有"的边界：

- **扩展是 operator 信任的代码执行，不是插件沙箱**：`plugins:` 列表刻意放在 operator 控制的 `config.yaml` 而非 API 可写的 `extensions_config.json`；build hooks 与 extension 代码以 Gateway 权限执行，"only trusted operator sources belong in this path"。（**成文标准**）（`../../AGENTS.md:75-84`）
- **运行时上下文信任边界**：server 产生的 run-context key 必须同时挡住 `body.context`（白名单合并）与自由形态的 `body.config`（逐字复制）两个客户端可写入口；信任与目的地是两个独立轴。（**成文标准**）（`../../backend/AGENTS.md:232-239`）
- **配置前向兼容**：`config_version` 追踪 schema 变更，旧配置启动时得到升级指引而非静默失效；缺失 `config_version` 视为版本 0，改 schema 时要同步 bump `config.example.yaml` 里的它。（`../../backend/docs/CONFIGURATION.md` L107-116）

  > 🔄 同步 #8（v2.2.0）：引证 `50-61` → **L107-116**。数值也变了：`config_version` 从 45 涨到 **63**，`config.example.yaml` 顶层 section 从 38 涨到 **43**（新增 `blob_storage` / `knowledge_base` / `pii_redaction` / `tool_artifacts` / `deployment`，**无删除**）。

**边界**：`SECURITY.md` 只声明支持分支与报送入口（全文 12 行，v2.2.0 仍然是 12 行），没有响应时限或 SLA——不应当作具备企业级漏洞响应流程的证据。（`../../SECURITY.md`）

> 🔄 同步 #8（v2.2.0）**在这一节加一条新的信任面**：企业嵌入者最关心的往往不是「插件能不能跑」而是「多实例部署安不安全」。v2.2.0 把答案从文档变成**启动期硬门**——`deployment.multi_instance`（`config.example.yaml`；`reload_boundary.py` L84-87 注明「the gate never re-runs on config.yaml edits, so declaring or withdrawing a multi-instance topology needs a Gateway restart on every instance」）一旦声明，`_enforce_postgres_for_multi_worker` 会评估多类不安全组合并拒绝启动；租约三件套（`run_ownership`、`scheduler`、`channels.leader_lease`）缺一不可。**这是"能定的写成契约"再往前一步：把契约变成起不来。**

## 结论

把本文与前一篇放在一起，DeerFlow 研发理念的完整读法是**同一条原则在两个循环里的复用**：

> **声明的规则要区分等级——能机器执行的物化成门禁，能定的写成契约，定不了的保持诚实标注；证据永远高于状态灯。**

运行时把它用于 agent run（模型自述 ≠ 工具回执 ≠ 验收），研发流程把它用于 change（模板自报 ≠ CI 绿 ≠ 已验证），运维把它用于部署（tag ≠ 版本一致 ≠ 可回滚）。反过来，它的诚实边界也是同构的：red-on-main 靠自报、draft PR 跳过主门禁、路径过滤有覆盖盲区、人工批准与分支保护在仓库外、安全响应未承诺时限——这些缺口没有被藏起来，多数就写在模板和指南自己的措辞里。

**v2.2.0 的一个观察**：这一轮改善最多的不是"新增门禁"，而是**把已有的门禁补齐到它声称覆盖的范围**。三个例子——replay E2E 把 trigger 扩到契约两侧（修掉"后端改动可以绕过前端检查"）、uv 版本 pin 从两个 workflow 扩到所有跑 `uv sync` 的 workflow、版本门补上 `uv.lock` 的 `uv lock --check`（避免"部分发布"）。**这比加新门更符合这条原则：不是增加声明，而是让已有的声明真的被执行到它该管的边界。**

## 相关

- [任务交付路径：运行时视角](task-delivery-walkthrough.md) —— 同一套理念在 agent run 循环里的形态。
- 证据底稿：`_digested/overview/07-design-philosophy-evidence.md` 第 7-9 节（研发流程、发布与数据演进、质量契约的一手取证）。
