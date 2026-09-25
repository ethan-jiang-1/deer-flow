---
title: "DSH 镜片下的 deer-flow：28 维红绿结果"
description: "用 deepseek-harness 仓库 _eval_harness 的评估协议（覆盖面×约束力两轴、封顶规则、红绿判定、成熟度档）给 deer-flow v2.1.0 打分：开发侧 10 红 / 7 绿、MG1；运行时侧 6 红 / 5 绿、MG1；两侧达标线均未达。根因一句话：机制覆盖面强、约束力弱——成文规则普遍没有配套的机器检查，模型可见面不落盘。含切片走查、gap 清单与施工顺序。"
topics: [harness, evaluation, deerflow, dsh, audit]
---

# DSH 镜片下的 deer-flow：28 维红绿结果

> **这是什么。** 拿 DSH 仓库 `_misc/_eval_harness` 那套评估协议当镜片，给 **deer-flow 本身**打分：开发 Harness 十七维（评仓库）+ 运行时 Harness 十一维（评 agent 产品）。本文只给**结果**——每个维度合格还是不合格、证据在哪、gap 怎么排；评估方法自身的机制只在 §0 用三十秒讲清读懂分数所需的最小集合，细节见附录 A。
>
> **评估对象与口径。** deer-flow `v2.1.0`（345f08be）源码工作树。`_digest/` 与 `_faq_on_digested/` 是我们自己叠上去的消化层，**不计入被评估对象**——评的是 upstream 交给参与者的那个仓库。
>
> **证据纪律（借用它的铁律）。** 每个档位都有 `file:line` 证据；跑不了的（五个活体实验、CI/PR 历史、GitHub 分支保护设置）按协议标**证据受限**，不据缺失扣分，也不断言缺失。运行时侧全部档位是"静态证据 + 测试存在性"下的**预判档**（实验未亲跑），见附录 C。
>
> 全文配图：[deerflow-dsh-scorecard](figures/deerflow-dsh-scorecard.svg)（28 维红绿仪表盘）。

---

## 目录

- [0 · 三十秒读懂记分法](#0--三十秒读懂记分法)
- [1 · 结论先行](#1--结论先行)
- [2 · 开发侧：10 红 / 7 绿](#2--开发侧10-红--7-绿)
- [3 · 切片走查：#5517 的六步](#3--切片走查5517-的六步)
- [4 · 运行时侧：6 红 / 5 绿](#4--运行时侧6-红--5-绿)
- [5 · 成熟度档与达标线](#5--成熟度档与达标线)
- [6 · Gap 清单与施工顺序](#6--gap-清单与施工顺序)
- [7 · 与我们 08 篇审计的分歧](#7--与我们-08-篇审计的分歧)
- [附录 A · 方法论速览](#附录-a--方法论速览)
- [附录 B · 验证记录](#附录-b--验证记录)
- [附录 C · 证据受限清单](#附录-c--证据受限清单)

---

## 0 · 三十秒读懂记分法

每一维记**两个档**：**覆盖面 coverage**（这一维有没有家：0 没有 / 1 零散 / 2 成体系 / 3 有 owner 与维护触发条件）× **约束力 enforcement**（靠什么成立：0 口传 / 1 写在 prose 里违反不会失败 / 2 有检查会红 / 3 机器强制且被证明过会失败）。**红 = 任一轴 ≤ 1，绿 = 两轴 ≥ 2**——所以"写下来了但拦不住"记红，这是这套镜片最锋利的地方。另有封顶规则（命中可观察条件即压上限，如"存在'改了 A 必须同时改 B'的耦合却没有同步机制 → 约束力封顶 1"）。成熟度档 MG 累积：MG1 有文档 → MG2 可核对 → MG3 可自证。

## 1 · 结论先行

| | 开发侧（评仓库） | 运行时侧（评产品） |
|---|---|---|
| 红绿 | **10 红 / 7 绿** | **6 红 / 5 绿** |
| 成熟度档 | **MG1 有文档**（距 MG2 差一维） | **MG1**（MG2 被 RT2+RT7 卡住——同一缺口的两半） |
| 达标线 | 未达（需 MG2 + 最痛三维约束力 3） | 未达（需 MG2：RT2/RT7/RT9 约束力 ≥ 2） |
| 最痛三维 | **EV2 负例控制、KN2 归属、CP2 正确路径** | **RT2 会话事实源、RT7 模型可见面、RT1 组合与启动** |

**一句话诊断**：deer-flow 的强项是**机制的覆盖面**——预算门禁、版本 lockstep、可替换后端、多入口投影、fail-closed 授权，全都有真实实现；短板集中在**约束力**——大量规则停在"写在 AGENTS.md 里、违反不会失败"的档位，**EV2 负例控制是 0/0**（没有任何"检查必须被证明会失败"的成文要求与实践），**模型可见面不落盘**（system prompt 与可见工具清单进请求但不进记录）。按 DSH 的立场（agent 信 gate 不信 prose），这正是"看起来什么都有、实际全靠自觉"的典型形态——尽管它是这个形态里相当好的一个。

**两侧共同的结构性发现**：所有红的维度几乎都是同一个病——**有供给、无拦截**。这不是 17 个独立问题，是一类问题（见 §6 的施工顺序：先修 EV2，再让其余检查化）。

## 2 · 开发侧：10 红 / 7 绿

| 维 | 覆盖面 | 约束力 | 判定 | 证据（一句话） |
|---|---|---|---|---|
| KN1 入口链 | 2 | 2 | 🟢 | 定位层根 `AGENTS.md`（238 行）+ 嵌套模块指南 + KiB 预算门禁接进 CI（`lint-check.yml:28,36`、`Makefile:91`） |
| KN2 归属 | 2 | 1 | 🔴 | 家基本单一，但**描述层漂移已发生 ≥3 处**且无同步检查（见下） |
| KN3 决策记录 | 2 | 1 | 🔴 | `docs/plans/` 有带日期的 RFC 与实现计划（如 `2026-07-10-pluggable-authorization-rfc.md`）；无状态区分、无归档纪律、无模板检查 |
| KN4 分类学 | 2 | 1 | 🔴 | 根 `AGENTS.md` 的 Repository Map 逐目录职责 + 模块指南；无"放错地方"的结构检查 |
| CP1 意图入口 | 2 | 1 | 🔴 | issue/PR 模板齐全（`pull_request_template.md` 有 Why/What/Surface area）；验收可观察性不强制、无检查 |
| CP2 正确路径 | 2 | 1 | 🔴 | `make config/install/dev/test/extension-*` paved 全套 + `examples/deerflow-extension-example`；无"绕过入口改核心"的结构检查 |
| CP3 流程固化 | 1 | 1 | 🔴 | 文档多为参考型；带触发条件的任务流程文档不成体系 |
| CP4 执行与授权 | 2 | 2 | 🟢 | 16 个 workflow 中 11 个声明最小权限 `permissions:`（`lint-check.yml` `contents: read`）；webhook 签名验证；内部 token；5 个发布类 workflow 未声明（依赖平台默认） |
| EV1 反馈分层 | 2 | 2 | 🟢 | 六类具名检查：ruff / 单测 / blocking-io（含 `detect_blocking_io_static.py`）/ e2e / replay-e2e / frontend lint+typecheck+unit；live 以 `-m "not live"` 排除；每层"不能单独证明什么"未成文 |
| EV2 负例控制 | 0 | 0 | 🔴 | **成文要求 0 命中**（grep `AGENTS.md`/`CONTRIBUTING.md`/`docs/` 无 negative control / 负例 / proven to fail）；无任何检查被证明过会失败的记录 |
| EV3 闭环完整性 | 2 | 1 | 🔴 | 更新政策成文（`AGENTS.md:220-222` "in the same change set"）且切片 #5517 实证同批交付；无检查强制（缺文档不会红） |
| EV4 评审与批准 | 2 | 1 ⚠️ | 🔴 | PR 模板的 Surface area 勾选是好实践；批准条件不成文；分支保护与评审历史不可见 → 证据受限 |
| ST1 静与动 | 2 | 2 | 🟢 | `config.yaml` 单一可写家（example 复制、gitignored）；compose 契约被 `test_compose_default_bind_host.py` 钉住；派生物不入库 |
| ST2 披露与隔离 | 2 | 2 | 🟢 | 常驻 KiB 预算门禁（`check_agent_guidance.py`，CI 强制）+ 嵌套 AGENTS.md 就近生效；摘要层/委派收窄在产品侧（RT7） |
| ST3 运行时查询 | 1 | 2 | 🔴 | `make doctor` 是真诊断（`doctor.py`：Python/Node/pnpm/uv/nginx + 配置存在/版本/可加载/模型/API key 九项），但**没有 dump 最终生效配置的命令**——答得出"能不能加载"，答不出"实际生效的是什么" |
| MT1 防漂移 | 2 | 2 | 🟢 | 结构检查成群：`check_agent_guidance` / `check_config_version.sh` / `check_chart_*.sh` / `verify-versions.yml` / `detect_blocking_io_static` / compose 钉子；复核触发条件未见成文 |
| MT2 发布与版本 | 3 | 2 | 🟢 | `RELEASING.md` 成文序列 + 四源版本 lockstep（pyproject/package.json/Chart version+appVersion）+ `scripts/verify_versions.sh` + tag 触发 CI 阻断发布——"忘了 bump 硬失败"的教科书实现；回退路径弱成文 |

### 2.1 绿的七维：deer-flow 的机制覆盖面是真的

- **KN1/ST2（同一枚硬币的两面）**：指令文件体系是 deer-flow 最强的供给面——根文件只做定位、模块细节下沉、`CLAUDE.md` 是薄 shim、**KiB 预算由 `scripts/check_agent_guidance.py` 硬门禁**（16/20、28/32、40/48、80/96 KiB 软/硬对），接在 `lint-check.yml` 与根 `Makefile` 里。按 DSH 的标准这是覆盖面 2 + 约束力 2（门禁会红；未做过负例控制所以不到 3）。
- **MT2**：版本 lockstep 是全套 17 维里唯一拿到覆盖面 3 的——发布序列、兼容边界（stabilize 中的 API 有明示）、迁移接管不可逆产物，且全部被 CI 硬失败钉住。
- **EV1**：反馈分层的层数与分工是真实的（连 blocking-I/O 都有独立 workflow + 静态检测器 + `.test_durations` 分片）；差的只是"每层不能单独证明什么"的成文。
- **CP4/ST1/MT1**：权限最小化声明、单一配置可写家、结构检查群——都是"有检查会红"的实档。

### 2.2 红的十维：三个簇

**簇一：描述层与现实的漂移（KN2、KN4、KN3）**——家是有的，但漂了没人发现。**实证（本轮同步 #7 中逐一核实）**：

| 漂移实例 | 两端 |
|---|---|
| 根 `AGENTS.md` 与 `backend/AGENTS.md` 都声称 `make config` 会复制 `extensions_config.json` | 实际 `scripts/configure.py:24-45` 只产 `config.yaml`/`.env`/`frontend/.env`；`extensions_config.json` 由 `scripts/docker.sh:388-395` 仅在 Docker 路径补建 |
| `backend/docs/TUI.md:28` 称 `--resume` 只按 id | `tui/session.py:37-64` 的 `resolve_ref` 也接受标题 |
| `backend/docs/TUI.md:85` slash 命令清单 | 缺 `/resume`（`tui/command_registry.py:44` 有） |
| `skills/skill_storage.py:197` docstring | 引用不存在的 `installer.ainstall_skill_from_archive` |

DSH 的封顶规则直接命中："存在'改了 A 必须同时改 B'的耦合却没有同步机制 → 覆盖面封顶 2、约束力封顶 1"。AGENTS.md 的描述与脚本行为之间，没有任何检查会发现它们分叉——**而这些文件恰恰是每个新 agent 会话的必读入口**。

**簇二：成文政策无检查（CP1、CP2、CP3、EV3、EV4）**——政策写得不错（文档更新政策、PR 模板的 Surface area、paved 命令），全部停在 EL1（违反不会发生任何事）。DSH 对这个形态有一句判词："用流程文档替代检查，等于把一条会失败的规则降级成一条会被人略过的建议。"

**簇三：查询与验证的缺口（ST3、EV2）**——ST3 答"能不能加载"不答"生效的是什么"；EV2 是全套的根：**没有任何机制证明"检查会失败"**，所以其它维度的"有检查"（EV1 的六层、MT1 的检查群）在 DSH 眼里都只能是约束力 2 的"看起来在拦"。

## 3 · 切片走查：#5517 的六步

被走查变更：`a2f72717 fix(persistence): repair run-change clock schema skipped by the 0023 insertion`（v2.1.0 十个提交之一；选它因为它是真实 bug 修复、带迁移、不碰核心架构）。

| 步 | 观察到的 | 证据状态 |
|---|---|---|
| 1 核对现场 | 提交信息完整记录问题链：0023 链序插错 → 已 stamp 的库永远不执行 → 首次线程删除炸 `no such table: run_change_clock`（#5516） | 能指出文件 |
| 2 判定窄 diff | 窄 diff = 0025 修复迁移 + ORM 注册两行 + `test_migration_0025` + `test_migration_0024` + **同 commit 更新 `migrations/AGENTS.md`** | 能指出文件 |
| 3 改 owner 面 | 修在源头（新迁移 + 模型注册），无第二份拷贝需要动 | 能指出文件 |
| 4 最小匹配证据 | `test_0025_repairs_schema_skipped_by_the_0023_insertion` 断言升级后表/列/索引齐全、健康库上 no-op——是行为测试不是快照 | 能指出文件；**红灯对照未跑**（本机 venv 不可用）→ 证据受限 |
| 5 沉淀 | 修复取舍写在 0025 的 downgrade 注释里（刻意 no-op，理由完整：避免重建 #5516 的洞）；`migrations/AGENTS.md` 同步 | 能指出文件 |
| 6 只报告跑过的 | PR 描述 vs CI 记录不可见 | 证据受限 |

五问补充：① 用户可观察结果 = 线程删除不再炸（提交信息引用 #5516）✓；② 从任务描述能找到 owner（bug → persistence/migrations）✓；③ 持久取舍记在 0025 注释 ✓✓；④ 会失败的证据 = test_0025（红灯对照未亲跑）；⑤ 全程无"靠猜"条目。

**这一笔是 deer-flow 的高光样本**：实现 + 回归测试 + 文档同批交付（EV3 的覆盖面 2 是真的），修复取舍留了书面理由（KN3 的好形态长这样）。它证明红维缺的不是意愿，是**让好实践变成默认的机制**。

## 4 · 运行时侧：6 红 / 5 绿

**适用性判定**：AQ1 是（Gateway 自带 runs 生命周期、journal、中间件链、工具管线——循环骨架由 LangGraph 提供，harness 层自实现）；AQ2 是（v2.1.0 活跃维护）；AQ3 是（packaged extensions / MCP / community tools / custom agents 四条第三方扩展面）。**形态 = 产品 + 平台 + 多入口**（Web / REST / LangGraph 兼容层 / 9 个 IM 通道 / TUI），全量评估。

| 维 | 覆盖面 | 约束力 | 判定 | 证据（一句话） |
|---|---|---|---|---|
| RT1 组合与启动 | 1 | 2 | 🔴 | 配置分层与优先级明确（`app_config.py:384-411`：显式 > `DEER_FLOW_CONFIG_PATH` > 项目根），坏组合**启动即拒**（`bootstrap.py:695` "refusing to start"；scheduler 组合约束 `backend/AGENTS.md:20`；`$VAR` 未设直接 raise，`app_config.py:576-581`）；但**没有 dump 最终生效配置的命令**——doctor 只做健康检查、CLI 无 config 子命令、Gateway 无 GET /api/config、support-bundle 只 dump 脱敏原文（封顶命中："没有 dump → 覆盖面 1"） |
| RT2 会话事实源 | 1 | 1 | 🔴 | journal 记录首条人类输入 + AI 响应全文 + 工具结果全文 + 中间件决策（`journal.py:430-445,512-524,655-660`），只追加 ✓、压缩不删记录 ✓、有 debug/audit 事件端点（`thread_runs.py:1710-1744`）；但 **system prompt 与可见工具清单进请求而不进记录**（memory/project 上下文只存 SHA-256 指纹，`journal.py:1054-1061` "a fingerprint can verify a candidate text but cannot reconstruct it"）——封顶命中："存在任何进入模型请求但不进记录的内容 → 两轴 1" |
| RT3 格式世代 | 2 | 2 | 🟢 | 版本链 + bootstrap 钉死（`alembic_version` 单行强制）；**读到比本构建更新的 revision 时拒绝启动并说明**（`bootstrap.py:695` RuntimeError，不是"文件损坏"）——RT3 约束力 3 的核心判据 DeerFlow 已具备；唯一前向例外 0019 是显式审查过的（`bootstrap.py:129` + schema floor 校验）；注记：25 个迁移全部带 downgrade 路径（双向工具在，单向纪律靠注释） |
| RT4 循环与终结边界 | 3 | 2 | 🟢 | 终态封闭集合（queued/launching/running/success/failed/interrupted）；取消是 durable 语义 + `cancel_stuck_once_tasks`；重启后过期 claim 回队列重新竞争、**不自动续跑**（`backend/AGENTS.md:23`）——"空闲 ≠ 完成"有显式区分 |
| RT5 能力 seam | 3 | 2 | 🟢 | **全卡最强**：模型（9 自研适配器 + LangChain provider，`use:` 类路径换后端）、sandbox（local/AIO/remote/K3s…）、存储（memory/sqlite/postgres）、memory（5 后端）——多项能力有两个真实实现、消费者零改动、纯配置切换 |
| RT6 扩展点与拦截 | 3 | 1 | 🔴 | 贡献面成体系（middleware 37 / packaged extensions 七类贡献点 / MCP / skills / community tools），placement 语义（MODEL_LOGICAL vs TOOL_RAW 等"拦得住什么"）有明文；**无结构检查拦"绕过扩展点直改核心"** |
| RT7 模型可见面 | 1 | 1 | 🔴 | agent 构建时显式组装 system prompt + 工具清单（`agent.py:1207-1228`），每步经 middleware 重组（deferred schema 过滤、skill policy 收窄），工具顺序确定（config 声明序 + 授权过滤保序 `enforcement.py:22`）；但**组装结果默认不落盘**——assembly descriptor 只存哈希且"无 observer 时整个跳过"（`agent.py:875-877`、`assembly_descriptor.py:495`）——与 RT2 是同一缺口的两半 |
| RT8 入口与协议投影 | 2 | 2 | 🟢 | 9 个 IM 通道 + TUI + LangGraph 兼容层 + Web 全部驱动同一 Gateway runs 语义（channels manager → `runs.create`）；`contracts/` 有冻结契约与双端契约测试；SSE 与人读输出分离 |
| RT9 工具执行与授权 | 2 | 2 | 🟢 | **先记录后执行**（`guardrails/middleware.py:169-216`：evaluate → 记 outcome/journal → 才 `handler(request)`）；**判定后参数不改写**（原样传递；模型可见的 payload 消隐只在 wrap_model_call 且 journal/state 留原件）；`fail_closed=True` 默认（`authorization_config.py:30`；注记：`authorization.enabled` 默认 False——授权层是显式 opt-in，开启即 fail-closed，与"判不了就放行"不同）；异常归一成 `status="error"` 的 ToolMessage 而非空结果（`tool_error_handling_middleware.py:129-155`）；授权集中在两层（组装期 Layer 1 + 执行期单一 GuardrailMiddleware） |
| RT10 可执行治理 | 1 | 2 | 🔴 | 检查很多（CI 16 workflow + 脚本群）但**散装**：Makefile / scripts / workflows 三处各自为政，无统一注册处（封顶命中："检查散在多个脚本里 → 覆盖面 1"）；架构规则大量只在 AGENTS.md |
| RT11 客户端组装纪律 | 2 | 1 | 🔴 | 状态从服务端派生（React Query，28 处 useQuery / 46 处 useMutation，`hooks.ts:1500-1612` 经 queryClient 维护一致性）；**未发现界面层直写业务数据**（localStorage 仅存草稿/设置/收藏等 UI 关注点，乐观消息按服务端身份对账 `hooks.ts:1298-1340`）；但无模块边界的机器检查 |

**运行时侧的红聚成两类**：**「说不清」排障面**（RT1 生效配置、RT2 请求重建、RT7 可见面落盘——共同后果是"出问题时无法只靠记录说清它当时看到了什么"）；**「边界靠约定」治理面**（RT6/RT10/RT11——绕过声明的边界没有东西会拦）。而绿的那五维——RT3/RT4/RT5/RT8/RT9——是 deer-flow 作为 agent 产品的架构底子：世代单向、状态机封闭、后端可换、入口共语义、授权 fail-closed 且先记录后执行，这五样在同类系统里并不常见。

## 5 · 成熟度档与达标线

**开发侧 = MG1 有文档**。MG1 成立（17 维中 14 维覆盖面 ≥ 2，多数 ✓）；**MG2 差一维**：MG2 要求快诊六维（KN1、KN2、CP2、EV1、EV3、ST1）里至少四个约束力 ≥ 2，实际只有三个（KN1 ✓、EV1 ✓、ST1 ✓；KN2/CP2/EV3 都是 1）。达标线（MG2 + 最痛三维约束力 3）未达——最痛三维里 EV2 是 0/0。

**运行时侧 = MG1**。MG1 成立（11 维中 7 维覆盖面 ≥ 2）；**MG2 被 RT2+RT7 卡死**：MG2 要求 RT2/RT7/RT9 约束力 ≥ 2，RT2 与 RT7 都是 1/1——而且是同一个结构缺口（组装给模型的东西不落盘）。达标线（至少 MG2）未达。

按 DSH 的收工线语义翻译成人话：**deer-flow 是一个"机制齐全的 MG1"**——离"可核对"只差把成文规则接上检查（开发侧三个约束力 1 → 2），离"可重建"只差把模型可见面落盘（运行时侧一维）。

## 6 · Gap 清单与施工顺序

按 DSH 的 21 号文档排序（痛点优先 + 前置维先做 + 一轮一到三维）：

| # | 维 | 症状（具体） | 后果 | 严重度 |
|---|---|---|---|---|
| 1 | EV2 | 无任何"检查必须被证明会失败"的成文要求与实践；`AGENTS.md`/`CONTRIBUTING` 0 命中 | 其它所有维度的"有检查"都可能是假检查；"CI 全绿"与"没人信"同时成立 | 高（前置维，压一切） |
| 2 | KN2 | AGENTS/TUI.md/docstring 与脚本行为漂移 ≥3 处实证；无同步机制 | 每个新 agent 会话的必读入口里有错描述——误导成本按会话数计 | 高（前置维） |
| 3 | RT2+RT7 | system prompt 与可见工具清单进请求、不进记录（journal 只存 SHA-256 指纹；assembly descriptor 只存哈希且无 observer 时跳过） | 出问题时无法只靠记录说清"它当时看到了什么"；LX1 回放只能重建一半（对话能重建，请求不能） | 高（运行时前置维，两维同一缺口） |
| 4 | CP2 | "能配置却改核心"无人拦（无结构检查） | 每个新功能都可能绕过 paved road 重新发明接法 | 中 |
| 5 | EV3 | 文档更新政策成文但缺文档不会红 | 切片 #5517 是好样本，但靠自觉维持 | 中 |
| 6 | ST3/RT1 | 无 dump 最终生效配置的命令（doctor 只答"能不能加载"） | "以为开着实际没装"只能翻日志；多配置层叠加后无人说得清生效值 | 中 |
| 7 | RT10 | 检查散装无统一注册处；架构规则大量只在 prose | 加规则 ≠ 加检查；绿灯数量与保护效果脱钩 | 中 |
| 8 | CP1/EV4/KN3/KN4/CP3/RT6/RT11 | 成文/模板存在、无强制、漂移靠人 | 同类问题的低烈度版本 | 低 |

**施工顺序（借它的"最便宜的三刀"逻辑，落到 deer-flow）**：

1. **第 1 轮（EV2，前置维，一个脚本的成本）**：挑三条最容易被违反的规则各配一个 `exit non-zero` 检查并**各做一次负例控制**（引入违规 → 看红 → 还原 → 看绿）。候选：①AGENTS.md 描述的命令行为 vs 脚本实际（对 `make config` 一类声明做 smoke 对照）；②根入口文件超预算（已有门禁，补一次负例控制即可升约束力 3）；③compose 默认 bind host（已有测试，同样补负例控制）。
2. **第 2 轮（KN2，半天到两天）**：建"事实 → home"对照表，先覆盖最容易漂的五类（命令行为、配置键、端点、环境变量、行号引用），把 §2.2 簇一的三处漂移修掉；同批把 AGENTS 描述-脚本一致性并进第 1 轮的检查。
3. **第 3 轮（RT7 + RT2 同批，运行时前置维——它们是同一件事的两半）**：把每次组装给模型的 system prompt + 可见工具清单做请求快照落盘（journal 新事件类型或独立 store；fingerprint 已验证候选文本的设计保留），让 LX1 变成可跑的实验——这一维做完，运行时侧 MG2 立刻成立。
4. 之后按压力触发排 ST3/RT1（dump 命令）、RT10（检查注册处）、CP2/EV3（检查化）。

## 7 · 与我们 08 篇审计的分歧

同一个仓库，两套镜片给出 **A-（126/148）** 与 **MG1（10 红/7 绿）**。分歧不在事实，在计分口径：

- 08 篇把"成文且内容正确"计 ✅（2 分）——回答的是"**对 agent 友好吗**"（供给面）；DSH 把"成文但拦不住"记约束力 1 → 红——回答的是"**可以被信任吗**"（约束面）。
- 最典型的分叉：08 给指令文件体系近满分；DSH 给 KN2 红，因为我们手里有漂移实证。08 没有负例控制这个维度；DSH 的 EV2 直接 0/0。
- 两个结论都对，且互补：**deer-flow 对 agent 的友好度是范本级，但它的好实践大部分靠自觉维持**。真要把 A- 升成"可自证"，缺的正是 DSH 镜片照出来的那一类东西——检查的检查。

---

## 附录 A · 方法论速览

（只收录读懂本文所需的最小集合；完整机制见 `_misc/_eval_harness` 六份文档——`01/02` 开发侧、`11/12` 运行时侧、`21/22` 缺口→计划。）

| 机制 | 一句话 |
|---|---|
| 两轴 | 覆盖面（有没有家）× 约束力（靠什么成立），各 0–3；红 = 任一轴 ≤ 1 |
| 封顶 | 命中可观察条件即压上限，不看其它证据（88 + 66 条，见附录 B 验证） |
| 证据四级 EL0–EL3 | 口传 / prose / 可核对 / 机器强制且**证明过会红**——从不失败的检查 ≈ 不存在的检查 |
| 铁律 | 只有当场做过的才算证据；"文档里写了"两轴封顶 1；**不用被评估对象自己的文档当证据** |
| 三层 | 静态清点 → 垂直切片（六步 + 红灯对照）→ 反证（抽检检查/规则/链接/"应该失败"） |
| 证据受限 | agent 看不到的历史（PR/CI/平台设置）不扣分也不断言缺失，列"需要人回答的问题" |
| 活体实验 LX1–LX5 | 回放 / 换后端 / 加能力 / 坏配置 / 取消与失败——**必须真的跑**（本文未跑，见附录 C） |
| MG 档 | 开发：MG1 有文档 → MG2 可核对 → MG3 可自证；运行时：MG0 单次可跑 → MG3 可扩展可信任 |
| 前置维 | 开发：KN1/KN2/EV1/EV2/EV3；运行时：RT2/RT7/RT9——它们的失败让其它维度的收益归零 |

代表性封顶五条：指不出唯一 home → 覆盖面 1；检查说不出最近一次为红 → 约束力 1；归属表右列是"参考某文档" → 覆盖面 1；加一条策略规则要改多个文件 → 两轴 1；手工维护的第二份清单无 freshness 检查 → 覆盖面 1。

## 附录 B · 验证记录

**对方法论文档本身**（评估前先验证镜片）：

| 断言 | 验证方式 | 结果 |
|---|---|---|
| `_audit.mjs` 自审通过 | `node _misc/_eval_harness/_audit.mjs` 实跑 | 全部通过，退出码 0 |
| 封顶计数 88/66 | 附录逐行脚本点数 + `_audit.mjs` 计数检查，两次独立核对 | 一致（02 逐维 7/7/7/5·4/4/8/5·4/5/4/5·4/5/4·5/5；12 逐维 6/6/6/7/6/8/5/6/6/5/5） |
| 例证分布 | grep 例证段标头 | 02 十七卡中 7 卡有 DSH 例证段 |
| 来源溯源 | 抽检 README 来源表 3 处（IG 表 / 六步切片 / DSH 引文） | 全部对上；DSH 引文逐字一致 |
| KN1 例证事实 | 钉版 commit 词数实测 | 根 AGENTS.md 1,949 词 ≤ 1,950，`verify-doc-budgets` 存在且接线 |

**对 deer-flow 的取证**（本文各档位的证据来源）：

| 证据 | 来源 |
|---|---|
| AGENTS.md 定位层 + 预算门禁接线 | `AGENTS.md`（238 行）、`scripts/check_agent_guidance.py`、`.github/workflows/lint-check.yml:28,36`、`Makefile:91` |
| KN2 漂移四实例 | `scripts/configure.py:24-45` vs 根/`backend/AGENTS.md`；`backend/docs/TUI.md:28,85` vs `tui/session.py:37-64`、`command_registry.py:44`；`skill_storage.py:197` |
| EV2 缺位 | grep `negative control\|负例\|proven to fail` 于 `AGENTS.md`/`backend/AGENTS.md`/`CONTRIBUTING.md`/`docs/AGENTS.md`：0 命中 |
| CI 权限声明 | 16 个 workflow 中 11 个含 `permissions:`；`lint-check.yml` 为 `contents: read` |
| 反馈分层 | `lint-check` / `backend-unit-tests` / `backend-blocking-io-tests` / `e2e-tests` / `replay-e2e` / `frontend-unit-tests` 六个 workflow + `scripts/detect_blocking_io_static.py` |
| ST3 缺 dump | `scripts/doctor.py` 检查项清单（Python/Node/pnpm/uv/nginx/config 九项，无 effective dump） |
| fail-closed 默认 | `config/authorization_config.py:30`、`config/guardrails_config.py:22`（均 `default=True`） |
| 迁移单向性 | `0025_repair_run_change_seq.py` downgrade 为带书面理由的 no-op；27 个迁移文件含 downgrade 路径 |
| 切片 #5517 | `git show a2f72717 --stat` 与 `test_migration_0025_repair_run_change_seq.py`（5 用例） |
| 启动拒绝坏组合 | `backend/AGENTS.md:20`（scheduler 组合约束 "otherwise startup rejects the configuration"） |
| RT1 无生效配置 dump | `doctor.py:734-774`（仅健康检查）、CLI 无 config 子命令（`tui/cli.py:48-90`）、Gateway 路由全集无 dump（`app.py:882-976`）、`support_bundle.py:233-235`（脱敏原文非生效值） |
| RT2 可见面不落盘 | `journal.py:1054-1061`（fingerprint 明言不能重建）、`journal.py:1033-1039`（仅 tool_promotion 记工具名）、`thread_runs.py:1276-1277`（非活跃 run 的 stream join 返回 409，不从 journal 回放） |
| RT7 组装结果不落盘 | `agent.py:875-877`（无 observer 整个跳过）、`assembly_descriptor.py:495`（只存 canonical_hash） |
| RT3 版本过新拒绝启动 | `bootstrap.py:695`（RuntimeError "refusing to start"，非报损坏）、`bootstrap.py:129`（0019 前向例外 + schema floor 校验） |
| RT9 管线语义 | `guardrails/middleware.py:169-216`（evaluate → 记 outcome → 才 handler）、`:216/266`（参数原样传递）、`tool_error_handling_middleware.py:129-155`（异常 → status="error" 的 ToolMessage） |
| RT11 前端派生 | `hooks.ts:9-11,1500-1612`（React Query + queryClient 失效）、localStorage 清单全为 UI 关注点、`hooks.ts:1298-1340`（乐观消息按服务端身份对账） |

## 附录 C · 证据受限清单

以下证据本报告拿不到，按协议标注、不据缺失扣分。**运行时侧全部档位因此是预判档**（静态源码 + 测试存在性，实验未亲跑）：

| 拿不到的 | 影响哪维哪轴 | 若拿到会怎样 |
|---|---|---|
| LX1–LX5 五个活体实验（本机 venv 不可用） | 运行时侧全部 | RT2/RT7 的静态结论已定（落盘**不存在**，非"没找到"）；跑通 LX1 是 §6 第 3 轮修复后的**验收方式**，不是改档依据 |
| 切片红灯对照（回滚实现跑测试） | EV2 / EV3 的约束力 | test_0025 若真红 → EV3 约束力可记 2 |
| CI 历史（各检查最近一次为红是什么回归） | EV2 约束力、MT1 约束力 3 | 有记录的检查可升约束力 3 |
| PR 评审历史（最近 10 笔的批准过程） | EV4 覆盖面/约束力 | 若评审有实质内容，EV4 可能转绿 |
| GitHub 分支保护 / 环境审批设置 | CP4 约束力 3、EV4 | 若发布 job 有环境保护 → CP4 约束力可升 3 |
| 多数使用者的真实配置漂移历史 | KN2 覆盖面 3 | — |
