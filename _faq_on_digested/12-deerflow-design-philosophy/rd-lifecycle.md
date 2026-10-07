# 研发流程走查：DeerFlow 如何开发、验证和发布自己

前一篇文章走查的是"一次任务在运行时如何走到交付"；本文走查另一个正交的循环——**仓库自己如何被开发、验证、评审、发布和运维**。两者共用同一种思维（声明、执行、证据分开），但对象不同：前者治理 agent 的 run，后者治理工程师（以及参与开发的 agent）的 change。

> **读法约定**：每个环节标注证据等级——**成文标准**（AGENTS.md/模板/指南写明的要求）、**机器门禁**（CI workflow 或测试自动执行、能挡住合并或发布的检查）、**归纳**（从实现组合推出的取舍）、**边界**（仓库文件无法证明的部分）。仓库里没有 GitHub 分支保护、required checks、reviewer 批准的配置文件，这些只能算"不可从本仓核实"。

## 1. 范围对齐：非平凡变更先有 issue

PR 模板要求先写 trigger 与 pain，并明确建议："For non-trivial features, please open an issue/discussion first to align on scope before writing code."（**成文标准**）（`../../.github/pull_request_template.md:5-12`）这是模板里的引导语，没有 CI 检查 PR 是否挂了 issue——无 issue 的 PR 不会被机器拦下。（**边界**）

## 2. 设计先行：spec 拥有决策，plan 只负责排序

大型变更走 RFC → spec → implementation plan 三级，且分工写得很硬。Projects Phase 2 的 spec 自称 "Source of truth: This spec governs Phase 2 in full"，并带 revision pin（每个对现状的论断都钉在具体 commit 上核对过）。（`../../docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md:4-9`）

实现计划则明确降级自己："every design decision, error mapping, and review-gate is owned by the spec. This document sequences files, symbols, and verification only. Where the spec and code disagree, the spec's deviation register (§10) wins."（**成文标准**）（`../../docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md:1-18`）

设计文档自带三类后续可执行的章节：**Testing Strategy**（分层列出单测/集成/前端/mock E2E/真路径验收，scheduled-tasks spec 甚至写明 real-path validation "Required before claiming feature complete"）、**Documentation Updates Required**（代码落地时 README/AGENTS.md 必须同步更新）、**Code Review Checklist**（评审条目编号列出，如"harness persistence 不 import app\*"）。（`../../docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md:515-584`）实现按 slice 推进，每个 slice 收尾时重读 spec §15 检查单、跑 lint+test，并发测试被标为 "hard requirement, not optional polish"。（`../../docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md:103-112`）

**归纳**：这套分级不是流程装饰，而是把"决策放哪"变成产权问题——设计决策只有一份权威（spec），偏离要登记（deviation register），实现计划不允许私自重新设计。但它是**按项目成文的纪律**，不是全仓强制"所有改动先写 spec"的门禁。

## 3. 实现：TDD 是成文军规，红绿靠自报

backend 指南用大写 MUST 定死 TDD："Every new feature or bug fix MUST be accompanied by unit tests. No exceptions."，并要求改动前后都跑 `make test` + `make test-blocking-io`。（**成文标准**）（`../../backend/AGENTS.md:243-256`）根 AGENTS.md 把同一条提升为跨模块约定，同时规定文档同步策略（用户可见行为改 README、开发/架构改 AGENTS.md，**同一个 change set 内完成**）。（`../../AGENTS.md:222-227`）

测试资产有命名与车道规则：禁止测试模块互相 import（共享夹具进 `_` 前缀 helper）；live 车道归属由 `pytest.mark.live` 标记决定，而"无凭证时优雅跳过"是**每个测试自己的守卫责任**——"A `_live` filename suffix without the marker is a bug"。（**成文标准**）（`../../backend/tests/AGENTS.md:5-8`）

诚实边界在 PR 模板里写得最清楚：bug fix 应当"encoded as a failing test that goes red before the fix"，并要求作者自报 "Did it go red on `main` and green on this branch? (yes / no)"；写不起 red test 要解释替代方案。（**成文标准 + 自我声明**）（`../../.github/pull_request_template.md:45-53`）**CI 只验证最终绿，不验证曾经红**——没有 workflow 会检出 main 重放新增测试。（**边界**）

## 4. PR 与评审：结构化的自我声明 + 信任分级自检

PR 模板把变更描述强制面向用户视角（"from a user's / caller's perspective, not as a code diff"），并要求勾选 Surface area 让评审者据此划范围；勾到 Agents/LangGraph 时还附带一条 prompt 信任自检：新 prompt 文本里每个数据源的信任级别是什么、该走哪个通道——模型可影响的内容必须走 untrusted 数据通道，**永远不许插值进框架持有的 system 文本**。（**成文标准**）（`../../.github/pull_request_template.md:15-35`）

AI 参与是显式披露项：用了什么工具、怎么用的，外加一句人的责任声明——"I've read and understand every line of this change and take responsibility for it — it's not unreviewed AI output." CONTRIBUTING 补充：不填 AI 披露的 PR "may be asked to fill it in before review"。（**成文标准**）（`../../.github/pull_request_template.md:64-75`） （`../../CONTRIBUTING.md:320-333`）

Validation 节要求写出**实际运行过的命令**，按改动面选择最低检查集。（`../../.github/pull_request_template.md:56-62`）仓库内没有 CODEOWNERS 或 reviewer 批准的配置文件；人工评审是否被分支保护强制，**无法从仓库文件判定**。（**边界**）

## 5. CI 门禁：哪些检查真的是机器在挡

这是"声明"与"执行"分界最清楚的一层。逐个数实际 workflow：

| 门禁 | 机器行为 | 触发与例外 |
|---|---|---|
| 格式/lint | backend `make lint`（含 `ruff format --check`）+ 前置 `uv lock --check`；frontend format/lint/typecheck/build | push + PR（`../../.github/workflows/lint-check.yml:41-68`） |
| agent 文档预算 | `check_agent_guidance.py` 按 diff 基线检查 AGENTS.md 软/硬预算 | push + PR（`../../.github/workflows/lint-check.yml:13-39`） |
| 后端单测 | 默认离线套件按真实时长分 4 片并行（fail-fast 关闭），Postgres/Redis 作为 service 容器起 | 仅非 draft PR（`../../.github/workflows/backend-unit-tests.yml:48-116`） |
| 最小安装可收集 | 按文档贡献者路径 `uv sync --group dev` 后只做 `pytest --collect-only`，证明无 extras 也能收集全套 | 仅非 draft PR（`../../.github/workflows/backend-unit-tests.yml:17-46`） |
| blocking-I/O | `make test-blocking-io` 严格 Blockbuster 门 | **仅 `backend/**` 路径变更触发**（`../../.github/workflows/backend-blocking-io-tests.yml:3-13,47-49`） |
| 前端 E2E | Playwright | **仅 `frontend/**` 变更触发**（`../../.github/workflows/e2e-tests.yml:3-13`） |
| replay E2E | 前后端契约两层回放：backend golden SSE 序列 + 真前端渲染回放 turn | **契约两侧任一变更触发**，"a backend change can no longer pass without the frontend-facing checks running"（`../../.github/workflows/replay-e2e.yml:3-37`） |
| skill 审查 | SkillScan + 豁免清单（head 不能自授权豁免） | 仅技能相关路径（`../../.github/skill-review-waivers.v1.json`） |

（**机器门禁**，均已核对 workflow 源）几个容易过度概括的点：**draft PR 会跳过主要测试 job**（unit/e2e/replay/skill 都有 draft guard）；"每个 PR 跑全部门"并不成立——blocking-I/O、E2E、replay、skill 审查全部按路径分流；`make test-live` 从不进 CI。（`../../CONTRIBUTING.md:358-361`）路径过滤本身是取舍：快，但跨边界改动（如改动被多方调用的公共工具）是否触发对应门禁，需要评审者自行判断覆盖面。（**边界**）

## 6. 架构、文档、工具链也是被测契约

DeerFlow 把"本该靠 review 纪律维持的规矩"写成测试：

- **架构边界**：harness 永不 import app，由 AST 扫描测试执行，架构图上的箭头有红绿语义。（`../../backend/tests/test_harness_boundary.py`）
- **文档即测试**：`test_middleware_documentation.py` 直接 `exec()` 文档里的 middleware 示例并断言链顺序与 guard 清单不漂移。
- **AGENTS.md 预算**：给 agent 的指令文档按目录深度限软/硬预算，超线是 CI error 而非劝告。（`../../.github/workflows/lint-check.yml:13-39`）
- **CI 工具链钉住**：`test_ci_uv_version_pin.py` 强制 Dockerfile、两个 workflow 里的 uv 版本一致，升级 uv 必须是"一个显式、可评审的变更"，防止"CI 用新 uv 重写 lock 仍然全绿、生产镜像里的旧 uv 读不了 lock"。（workflow 内注释明说 "pinned by backend/tests/test_ci_uv_version_pin.py"）（`../../.github/workflows/backend-unit-tests.yml:37-38`） （`../../.github/workflows/lint-check.yml:54-55`）

**归纳**：这一层的共同句式是"谁来监督监督者？——下一个测试"。规矩不依赖记忆或个人权威，而是每 PR 跑的红绿检查。但注意它们钉的是**结构与一致性**，不证明业务行为正确。

## 7. 发布：tag 驱动 + 版本门

发版没有脚本 bump 版本：维护者改版本源、更新 changelog、commit、打 `v*` tag，推送触发发布 workflow。版本号必须在**四处**完全一致（backend pyproject、frontend package.json、Helm Chart 的 version+appVersion），加 tag 本身共五源。（`../../RELEASING.md:3-24`）`verify-versions.yml` 在 tag 上校验所有源等于 tag，container/chart 发布 job 显式 `needs: verify-versions`——任何一处漂移就**跳过全部镜像与 chart 发布**。（**机器门禁**）（`../../.github/workflows/verify-versions.yml:12-27`） （`../../.github/workflows/container.yaml:3-16`）nightly 构建刻意不走版本门（无 tag），也不碰 `latest` 标签。（`../../RELEASING.md:96-103`）

注意门禁的不对称：**发布门强于日常 PR 门**——普通 PR 的 CI 并不做完整生产部署/启动升级/回滚验收；real-path 现场验收只在个别 spec 里被要求（"Required before claiming feature complete"），且属于人工步骤，不是普遍 CI 门。（**边界**）（`../../docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md:553-563`）

## 8. 数据演进：只追加的迁移链 + 启动时升级 + fail-closed

每个 ORM 变更（新列/新表/新索引）**必须**以 alembic revision 交付；Gateway 启动自动 `upgrade head`，常规生产升级无需手工命令；revision 只能接在当前 head 之后，**不许插入已发布 revision 之前**——插入会被既有数据库当作"已执行的祖先"跳过，`0023_run_change_seq` 插队事故（#5516）就是靠 `0025_repair_run_change_seq` 修复的。（**成文标准，事故已回写为修复 migration + 回归测试**）（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:5`）

bootstrap 对数据库状态 fail-closed：未知 revision、空版本表、多版本行一律拒绝启动。（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:7-16`）仓库刻意**不提供** `make migrate`/`make migrate-stamp` 目标——"routine upgrades execute at Gateway startup; the documented offline recovery is reserved for the audited out-of-tree schema"。（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:91`）确实需要离线修复时，恢复文档要求停掉所有写入者、先备份、逐步核验确切 schema 形态再操作，且该恢复路径本身有回归测试钉住。（`../../docs/database-forward-revision-recovery.md:21-40`） （`../../docs/database-forward-revision-recovery.md:74-79`）

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
- **配置前向兼容**：`config_version` 追踪 schema 变更，旧配置启动时得到升级指引而非静默失效。（`../../backend/docs/CONFIGURATION.md:50-61`）

**边界**：`SECURITY.md` 只声明支持分支与报送入口（12 行），没有响应时限或 SLA——不应当作具备企业级漏洞响应流程的证据。（`../../SECURITY.md:1-12`）

## 结论

把本文与前一篇放在一起，DeerFlow 研发理念的完整读法是**同一条原则在两个循环里的复用**：

> **声明的规则要区分等级——能机器执行的物化成门禁，能定的写成契约，定不了的保持诚实标注；证据永远高于状态灯。**

运行时把它用于 agent run（模型自述 ≠ 工具回执 ≠ 验收），研发流程把它用于 change（模板自报 ≠ CI 绿 ≠ 已验证），运维把它用于部署（tag ≠ 版本一致 ≠ 可回滚）。反过来，它的诚实边界也是同构的：red-on-main 靠自报、draft PR 跳过主门禁、路径过滤有覆盖盲区、人工批准与分支保护在仓库外、安全响应未承诺时限——这些缺口没有被藏起来，多数就写在模板和指南自己的措辞里。

## 相关

- [任务交付路径：运行时视角](task-delivery-walkthrough.md) —— 同一套理念在 agent run 循环里的形态。
- 证据底稿：`_digest/overview/07-design-philosophy-evidence.md` 第 7-9 节（研发流程、发布与数据演进、质量契约的一手取证）。
