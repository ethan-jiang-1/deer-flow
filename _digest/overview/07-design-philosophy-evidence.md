---
title: "DeerFlow 设计理念：当前仓库的一手证据"
description: "从产品定位、执行治理、上下文分层与完成证据，以及研发流程（SDLC）、发布与质量治理，理解 DeerFlow 的工程取舍。"
type: research
---

# DeerFlow 设计理念：当前仓库的一手证据

> **研究基线**：源码取证基于 `f31aefce993249ffbcf66deb156e5d716ec55669`；其后分支上的提交（至 `874ed006`）均为文档变更，不影响本文引用的运行时源码行号。本文研究该修订对应的仓库实现，不把研究分支上的新增机制自动归为官方上游宣言。只采用仓库一方 README、模块指南与源码；不借现有 digest 的解释替代一手证据。本文是结论的证据底稿，不是使用问答。
>
> **证据分层**：**明确主张**指 README 的产品定位或工程指南写明的原则；**机器门禁**指 CI workflow / 测试自动执行、能阻断合并或发布的检查；**实现归纳**指从当前代码组合推得的设计取舍；**边界**指当前机制不能证明、不能恢复、依赖配置或仓库文件无法核实的部分。引用均相对于本文位置，附行号。

## 1. 产品目标：从研究框架转向“让代理真的完成工作”的运行环境

**明确主张。** README 2.0 将自身称为 super agent harness：编排 sub-agent、memory、sandbox，并通过可扩展 skills 扩大任务范围；它明确说明 2.0 是重写而非沿用 v1 代码。（`../../README.md:1-17`）

其定位变化不是把研究功能删除，而是不再把研究当作产品能力上限：README 把数据流水线、幻灯片、仪表盘与内容自动化列作超出研究的用途，并把 harness 解释为让 agents 实际完成工作的基础设施。随后列出文件系统、memory、skills、sandbox-aware execution 和复杂任务的计划／委派能力。（`../../README.md:939-947`）

**实现归纳。** “通用”更接近**可组合执行环境**而非一种预置任务流程：lead factory 将运行时解析出的模型、最终工具集合、中间件、system prompt 和 thread state 交给 `create_agent`，并不在此硬编码固定的“研究→写报告”节点序列。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:1230-1245`）

**边界。** “几乎任何任务”是能力定位，不是成功保证。具体能执行什么仍取决于模型、启用工具、skill、sandbox 与权限；可判定验收条件只覆盖执行事实，不能证明任意产物正确。（`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:703-733`）

## 2. 模型决定下一步，工程层决定哪些动作可以发生

**实现归纳。** lead 的核心是由模型、工具和 middleware 构成的动态执行循环，不应将产品目标等同于固定业务 DAG。模型侧路由原则写在 prompt 中，运行条件由 factory 和 middleware 实现。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:1239-1245`） （`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:484-506`）

委派最能体现这个边界：prompt 要求**默认直接执行**，不能仅因任务复杂、多步骤、输出长或仓库大就委派；只有并行延迟、专门能力或上下文隔离收益明显超过启动、重复发现、综合和副作用成本时才委派。相互依赖的输出、重叠文件和共享可变状态是并行派发的否决条件。（`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:423-445`） （`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:474-503`）

当前组装还独立注册 skill 工具策略 middleware：skill 的“启用／可发现”只是元数据，只有 slash 显式激活或实际读取 skill 文件后才应用 `allowed-tools`；deferred schema 在 promotion 前被隐藏，promotion 又不代替 skill 的执行许可。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:565-599`） （`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:667-674`）

**边界。** 净收益判断是模型行为指引，不是测量真实收益的确定性优化器；skill 的 `allowed-tools` 被 README 限定为 best-effort behavioral scoping，而非硬安全边界，其他读取工具和有界 active context 的淘汰可能限制覆盖。（`../../README.md:974-978`） 因而“有 prompt 规则”不等于“存在强安全隔离”。

## 3. 能力知识、执行动作、文件产物与记忆不是同一种状态

| 角色 | 强证据 | 设计含义与限制 |
|---|---|---|
| **Skill：任务方法与按需知识** | README 定义 skill 为带 workflow、最佳实践及资源引用的 Markdown 能力模块，声明 progressive loading。（`../../README.md:962-966`）；slash activation 保持 base prompt metadata-only。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:565-577`） | skill 指导如何用工具，本身不是执行器；元数据可见不等于全文加载或执行许可。 |
| **Tool：实际执行接口** | `task` 是带输入／结果协议的 tool；其验收依赖共享 workspace 和记录过的 bash 执行。（`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:650-667`） （`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:715-749`） | 工具调用和结果形成动作证据；模型叙述不是工具执行事实。 |
| **Sandbox／文件：可操作与可交付的外部状态** | `present_files` 归一化当前 thread outputs 路径并拒绝目录外路径；它让文件在客户端可查看／下载。（`../../backend/packages/harness/deerflow/tools/builtins/present_file_tool.py:33-80`） （`../../backend/packages/harness/deerflow/tools/builtins/present_file_tool.py:83-103`） | 创建与呈现文件是不同动作；workspace 中间文件不自动成为用户交付，文件状态不等于对话消息。 |
| **Durable context：本线程执行连续性** | middleware 在 summarization 前捕获委派与已加载 skill，再将 summary、ledger、skills 等 channels 注入模型请求。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:601-622`） | 保留“做过什么／加载过什么”的投影，不依赖旧消息永久留在窗口；`durable` 不代表所有外部执行都可重启恢复。 |
| **Summarization：当前上下文容量管理** | 可按 tokens、messages、input fraction 触发，保留近期消息；manual compact 重用同一 middleware 写新 checkpoint。（`../../backend/AGENTS.md:362-376`） | 重整当前对话表示，不等于长期知识增加或任务成功判定。 |
| **Long-term memory：跨会话连续性** | README 明确跨 sessions 存储 profile、preferences、knowledge，强调本地控制。（`../../README.md:1587`）；factory 分开处理写入 middleware 与 tool-mode。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:643-654`） | 读取、写入、工具模式有独立策略，不应与线程 summary、文件产物或验收证据混同。 |

**实现归纳。** skill 告诉代理怎么做，tool 实际做，sandbox／outputs 保存可检查对象，summary 保持当前线程可推理，memory 保存跨会话相关信息。这些功能协同，但成功与持久化语义不互相替代。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:565-654`）

## 4. task、subagent、goal 与 workflow：不要把名称变成虚构的独立引擎

### 4.1 普通 task 是委派接口；subagent 是被执行的代理

`task` 直接接受 `prompt`、`subagent_type`、可选 criteria 与 `context_mode`，不是与 subagent 平级的另一个通用执行器。普通 task 等待 subagent 并直接返回，无需模型轮询；默认 isolated，snapshot 是派发时固定的父历史背景，仍保留子代理自身角色与工具限制。（`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:650-661`） （`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:511-536`）

**恢复边界。** 普通 subagent graph 明确 `checkpointer=False`，因此父线程保存结果投影不等于保存可恢复的子图执行。（`../../backend/packages/harness/deerflow/subagents/executor.py:1004-1014`）

`batch_task` 是另一种显式执行模式：返回 durable batch id，不消耗普通 task 的 per-run total；items 必须独立、自包含并使用稳定 key。不能从条目数量推断模式，也不能用反复普通 task 模拟它。（`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:456-473`）

### 4.2 “执行结束”与“任务验收”独立

当前 prompt 和工具协议拆开三个容易误读的结论：

- `completed` 仅说明执行结束，**不说明任务 accepted**；
- `UNVERIFIED` 是**证据不足**，不是条件失败；
- receipt citation `resolved` 说明对应调用发生，**不说明相邻论断正确**。

处理策略是保留可复用成果，对不成立条件定向修补，对缺证据条件补验证；预算用尽时交付确认结果并说明不确定性，而非整项无差别重来。（`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:517-523`） （`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:703-733`）

### 4.3 Goal 是有限续轮控制，不是任意后台工作恢复

Goal evaluator 是主 graph 外的独立模型调用，只依据 visible conversation evidence 判断 satisfaction；没有可见 assistant evidence 则返回 `missing_evidence`。它被要求不要假定文件、命令、测试或外部状态已经改变。（`../../backend/packages/harness/deerflow/runtime/goal.py:254-295`）

确定性续轮 gate 只允许未满足且 blocker 属于可续类别，并同时检查 continuation cap 与 no-progress cap；缺证据、等用户、外部等待不是无限自动重试理由。（`../../backend/packages/harness/deerflow/runtime/goal.py:41-49`） （`../../backend/packages/harness/deerflow/runtime/goal.py:332-342`）

**边界。** goal satisfaction 仍是有限可见证据上的模型判断，不是外部状态独立验证器。Gateway 活跃执行仍由进程拥有；README 对多 worker 部署提出数据库、Redis stream、heartbeat、DB event store 组合条件，dead-worker reconciliation 将 runs 标为 errors，而非保证从任意工具副作用位置继续。（`../../README.md:360-373`）

### 4.4 Workflow 首先是过程描述，不宜假设通用持久 DAG 产品

在已检查的 lead factory、task schema 和 prompt 中，workflow 表示 skill 操作方法或委派步骤；这些接口没有给出通用 workflow DAG schema、依赖节点调度或节点级重启承诺。**这是本文所查入口的支持范围判断，不是宣称仓库所有组件没有 graph 能力。** graph 组装、普通委派与显式 durable batch 各有机制，不能仅凭 workflow 一词合并为统一持久原语。（`../../README.md:964-966`） （`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:439-473`） （`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:1239-1245`）

## 5. 核心能力、应用表面与扩展契约分层

**明确工程规则。** backend 指南定义 harness 为可发布 agent framework，app 为 Gateway／渠道代码，要求 `app → deerflow` 单向依赖。（`../../backend/AGENTS.md:192-215`）

**可执行约束。** boundary test 用 AST 遍历 harness Python imports，禁止 `app` 与 `app.*`。这把“可嵌入且不依赖 Gateway”的取舍变成可自动检查的事实。（`../../backend/tests/test_harness_boundary.py:18-46`）

**当前仓库实现归纳。** extension-api 暴露窄 `HostPolicySnapshot`，而非整个 `AppConfig`；Protocol 方法与 optional fields 提供默认值，维持 additive compatibility。`TaskInfo` 把 lead／subagent execution 身份抽象为契约数据，而非 Gateway 对象。（`../../backend/packages/extension-api/deerflow_extension_api/contracts.py:1-7`） （`../../backend/packages/extension-api/deerflow_extension_api/contracts.py:28-46`） （`../../backend/packages/extension-api/deerflow_extension_api/contracts.py:49-87`）

**边界。** 模块隔离不等于进程隔离或插件沙箱。根指南说明 Python plugin 列表由 operator 管理并引入代码，build hooks 与 extension code 使用 Gateway 权限，变更需重启。“可扩展”不等于任意不可信代码可以安全执行。（`../../AGENTS.md:75-84`）

## 6. 测试基础设施：把“代理看见什么”转为可重复证据

**明确工程要求。** backend 将新增功能／修复必须附 unit tests、offline／blocking-I/O 验证写成强制规范；live API tests 独立且 opt-in。（`../../backend/AGENTS.md:243-274`）

**当前仓库实现归纳。** `ScriptedModel` 替换模型输出，而不是 loader、registry、composition 和真实 graph；记录每次 messages 与 `bind_tools` payload，可断言 middleware 实际改变了模型可见 prompt、消息或 schema，避免只检查内部对象已注册便声称行为成立。（`../../backend/packages/harness/deerflow/testing/models.py:1-14`） （`../../backend/packages/harness/deerflow/testing/models.py:29-78`） （`../../backend/packages/harness/deerflow/testing/models.py:81-118`）

它与 AST boundary test 分别检查**真实组合后的模型可见行为**和**架构依赖约束**，两者都不是产物语义正确性的完整保证。（`../../backend/packages/harness/deerflow/testing/models.py:43-47`） （`../../backend/tests/test_harness_boundary.py:37-46`）

**边界。** scripted model 不证明真实 provider、streaming tokenisation、retry 或 rate limit 行为，源码要求在模型依赖本身是被测行为时搭配 live lane。本文核对测试机制与断言源码，**未运行测试，也未声称整套测试通过**。（`../../backend/packages/harness/deerflow/testing/models.py:10-14`）

## 7. 研发流程（SDLC）：声明的标准与机器执行的门禁分开读

**明确主张（成文标准）。** 跨模块约定写明文档同步策略（用户可见行为改 README、开发/架构改 AGENTS.md，同一 change set 内完成）、TDD（backend 强制）、推送前格式化、版本源四处同步。（`../../AGENTS.md:222-240`） backend 指南将 TDD 定为大写军规："Every new feature or bug fix MUST be accompanied by unit tests. No exceptions."，并要求改动前后跑 `make test` 与 `make test-blocking-io`。（`../../backend/AGENTS.md:243-256`） 测试资产另有命名与车道规则：禁止测试模块互相 import；live 车道归属由 `pytest.mark.live` 决定，无凭证优雅跳过是测试自身的守卫责任。（`../../backend/tests/AGENTS.md:5-8`）

**大变更设计先行，决策产权唯一。** Projects Phase 2 spec 自称 source of truth 并钉 revision；实现计划明确降级自己："every design decision, error mapping, and review-gate is owned by the spec. This document sequences files, symbols, and verification only."，spec 与代码不一致时以 spec 的 deviation register 为准。（`../../docs/superpowers/specs/2026-09-12-projects-mvp-phase2-design.md:4-9`） （`../../docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md:1-18`） 设计文档自带可执行后续：Testing Strategy（分层到 real-path validation，"Required before claiming feature complete"）、Documentation Updates Required、Code Review Checklist；实现按 slice 推进并在每个 slice 收尾重读检查单，并发测试是 hard requirement。（`../../docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md:515-584`） （`../../docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md:103-112`） 这是按项目成文的纪律，不是"所有改动必须先有 spec"的通用门禁。（**边界**）

**PR 表面是结构化自我声明。** 模板要求变更描述面向用户视角、勾选 Surface area 划评审范围；勾到 Agents/LangGraph 时附带 prompt 信任自检（模型可影响的内容必须走 untrusted 数据通道，不许插值进框架 system 文本）；bug fix 应先红后绿并自报 "Did it go red on `main` and green on this branch?"；Validation 填实际运行过的命令；AI 披露三问加人的责任声明——"it's not unreviewed AI output"。（`../../.github/pull_request_template.md:5-12,15-35,45-62,64-75`） CONTRIBUTING 补充：忽略 AI 披露的 PR 可能被要求补全后才评审。（`../../CONTRIBUTING.md:320-333`）

**机器门禁（核对 workflow 源）。** 逐个数的实际执行情况：

| 门禁 | 机器行为 | 触发与例外 |
|---|---|---|
| lint | backend `make lint`（含 `ruff format --check`）+ `uv lock --check`；frontend format/lint/typecheck/build | push + PR（`../../.github/workflows/lint-check.yml:41-95`） |
| agent 文档预算 | `check_agent_guidance.py` 按深度限软/硬预算，超线为 error | push + PR（`../../.github/workflows/lint-check.yml:13-39`） |
| 后端单测 | 离线套件按真实时长 4 分片（fail-fast 关闭），Postgres/Redis service 容器 | **仅非 draft PR**（`../../.github/workflows/backend-unit-tests.yml:48-116`） |
| 最小安装可收集 | 按文档贡献者路径安装后仅 `--collect-only` | 仅非 draft PR（`../../.github/workflows/backend-unit-tests.yml:17-46`） |
| blocking-I/O | `make test-blocking-io` | **仅 `backend/**` 路径触发**（`../../.github/workflows/backend-blocking-io-tests.yml:3-13`） |
| 前端 E2E | Playwright | **仅 `frontend/**` 路径触发**（`../../.github/workflows/e2e-tests.yml:3-13`） |
| replay E2E | backend golden SSE + 真前端渲染两层回放 | **契约两侧任一变更触发**（`../../.github/workflows/replay-e2e.yml:3-37`） |
| skill 审查 | SkillScan + 豁免清单（head 不能自授权） | 仅技能相关路径（`../../.github/skill-review-waivers.v1.json`） |

**边界（本仓库无法证明的部分）。** ① CI 只验证测试最终绿，不验证新增测试曾在 main 红——red-on-main 是 PR 自报；（`../../.github/pull_request_template.md:45-53`） ② draft PR 跳过主要测试 job；③ "每 PR 跑全部门"不成立，多个门按路径分流；④ `make test-live` 从不进 CI；（`../../CONTRIBUTING.md:358-361`） ⑤ 仓库内无 CODEOWNERS / 分支保护 / required checks 配置，人工批准是否被强制不可从文件判定；⑥ 普通 PR 的 CI 不做完整生产部署/启动升级验收，real-path 现场验收是个别 spec 的人工要求。

**失败回写为机制（实现归纳）。** uv 工具链漂移风险被 `test_ci_uv_version_pin.py` 钉住（workflow 注释明示 "pinned by backend/tests/test_ci_uv_version_pin.py"，Dockerfile 与全部 `setup-uv` 步骤同版本）；（`../../.github/workflows/backend-unit-tests.yml:37-38`） （`../../.github/workflows/lint-check.yml:54-55`） AGENTS.md 膨胀被预算 CI 治理；迁移插队事故（#5516）被 `0025_repair_run_change_seq` 修复并加回归。评审哲学成文："Evidence over a green check. CI status is a signal, not a verdict."，且 agent 评审被钉在 comment-only 平面、confidence+severity 双轴门控。（`../../docs/agents/maintainer-orchestrator-design.md:17-32,38-45`） **边界**：回写有大量实例，但没有全仓强制的 postmortem/ADR 门禁，属文化惯性而非可检查流程。运维侧 `make support-bundle` 产出脱敏证据与 AI 填报草稿（草稿刻意不编造复现步骤）。（`../../CONTRIBUTING.md:383-413`）

## 8. 发布、数据演进与企业框架的质量契约

**发布门（机器门禁）。** 发版 tag 驱动，无 bump 脚本；版本须在四处完全一致加 tag 共五源。（`../../RELEASING.md:3-24`） `verify-versions.yml` 在 tag 上校验所有源等于 tag，container/chart 发布 job 显式 `needs: verify-versions`，漂移即跳过全部发布。（`../../.github/workflows/verify-versions.yml:12-27`） （`../../.github/workflows/container.yaml:3-16`） nightly 刻意不走版本门、不碰 `latest`。（`../../RELEASING.md:96-103`）

**数据演进（成文标准 + 事故回写）。** 每个 ORM 变更必须以 alembic revision 交付；Gateway 启动自动 `upgrade head`；revision 只能接 head 之后，不许插队——插队事故 #5516 即由 `0025_repair_run_change_seq` 修复。（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:5`） bootstrap 对未知 revision / 空版本表 / 多版本行 fail-closed 拒绝启动；（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:7-16`） 仓库刻意不提供 `make migrate`/`make migrate-stamp`——"routine upgrades execute at Gateway startup; the documented offline recovery is reserved for the audited out-of-tree schema"，（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:91`） 离线恢复要求停写入者、备份、核验确切 schema，且回归测试钉住该路径。（`../../docs/database-forward-revision-recovery.md:21-40,74-79`） 迁移无独立 workflow，随单测套件执行。**归纳**：升级安全模型是"前向兼容 + 启动即迁移 + 未知状态拒绝启动"，把人为失误从流程里消掉而非要求人记住。

**企业框架的信任与兼容面（明确主张）。** `plugins:` 列表刻意放在 operator 控制的 `config.yaml` 而非 API 可写的 `extensions_config.json`；build hooks 与 extension 代码以 Gateway 权限执行，"only trusted operator sources belong in this path"——可扩展 ≠ 插件沙箱。（`../../AGENTS.md:75-84`） server 产生的 run-context key 必须同时挡住 `body.context` 与自由形态 `body.config` 两个客户端可写入口，信任与目的地是独立轴。（`../../backend/AGENTS.md:232-239`） 配置 schema 以 `config_version` 前向兼容，旧配置得到升级指引而非静默失效。（`../../backend/docs/CONFIGURATION.md:50-61`） **边界**：`SECURITY.md` 仅声明支持分支与报送入口，无响应时限或 SLA，不构成企业级漏洞响应流程的证据。（`../../SECURITY.md:1-12`）

## 9. 结论与易误读边界

1. **执行基础设施，不是固定研究流水线。** 定位依据 README，组合依据 factory；通用能力不等于无限权限或成功保证。（`../../README.md:939-947`） （`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:1239-1245`）
2. **自治与治理并存。** 模型选路径和估算委派收益；工具激活策略与续轮准入独立管理。自然语言规则不等于确定性收益优化或硬安全隔离。（`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:477-503`） （`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:588-599`）
3. **连续性分层。** skill、summary、memory、文件各有职责；有 durable projection 不等于 one-shot 子执行可恢复。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:601-654`） （`../../backend/packages/harness/deerflow/subagents/executor.py:1007-1014`）
4. **不给证据过度授权。** execution ended、condition holds、receipt resolved 分别证明不同事实；缺证据应保留不确定性，不冒充通过，也不等同失败。（`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:703-733`）
5. **窄接口与可执行契约不意味着不可信插件隔离。** 单向 import、policy snapshot 和模型可见测试可以检查，插件权限仍按 operator 信任边界理解。（`../../backend/tests/test_harness_boundary.py:18-46`） （`../../backend/packages/extension-api/deerflow_extension_api/contracts.py:31-37`） （`../../AGENTS.md:75-84`）
6. **研发纪律按"声明—门禁—不可核实"三级分层。** TDD/文档同步/AI 披露是成文标准；lint、分片单测、blocking-I/O、契约回放、版本门是机器门禁；red-on-main、人工批准、分支保护靠自报或位于仓库外。把指南要求当作已被 CI 强制是本仓库最易犯的过度概括。（`../../backend/AGENTS.md:243-256`） （`../../.github/workflows/backend-unit-tests.yml:48-116`）
7. **两个循环共用一条元原则。** 运行时把"模型自述 ≠ 工具回执 ≠ 验收"用于 agent run；研发流程把"模板自报 ≠ CI 绿 ≠ 已验证"（"Evidence over a green check"）用于 change；发布把"tag ≠ 版本一致 ≠ 可回滚"用于部署。证据永远高于状态灯。（`../../docs/agents/maintainer-orchestrator-design.md:38-45`）
8. **失败沉淀为机制是惯例不是门禁。** 事故→测试/门禁/契约的回写有 uv pin、0025 修复、AGENTS.md 预算等多个实例，但无全仓强制的 postmortem/ADR 检查；学习发生在仓库，其一致性靠文化维持。（`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:5`） （`../../.github/workflows/lint-check.yml:13-39`）
