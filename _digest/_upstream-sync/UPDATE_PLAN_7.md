---
title: "Digest 更新计划 #7"
description: "基于 upstream v2.1.0-rc0 (769589e8) → v2.1.0 (345f08be) 的 10 commits，逐文件规划 digest 更新与校正项。"
type: index
---

# Digest 更新计划 #7

> 基准：`769589e8`（v2.1.0-rc0）→ `345f08be`（**v2.1.0**，10 commits），2026-09-24
> 变更规模：90 files, +9,097 / −450
> 提交构成：3 fix / 2 docs / 1 chore(ci) / 4 chore(doc)
> ⚠️ 特性：tag 打在 release 分支 `2.1.x-dev`，**与 `upstream/main` 已分叉**（main 另有 189 commits 待下次处理）

## 一句话总结

发布收尾窗口，**没有新子系统**：4 个代码层实质变更（0025 修复型迁移、线程删除全量清理、事件存储变更串行域、CI `*-dev` 触发）+ 1 个前端布局修复 + 2 本用户手册改版 + root `AGENTS.md` 精简。digest 侧的重点因此不是"增"，而是**校正既有描述**：迁移链 head、删除语义、行号引用、AGENTS 计数与预算实测值。

## ▶ 执行清单（全部完成）

| 步 | 文件 | 做什么 | 状态 |
|----|------|--------|------|
| 1 | `internals/persistence/db-checkpointer-store-backends.md` | 迁移链 0001→**0025**；新增 0025 修复型迁移小节（#5516 的"插队"失败模式与迁移纪律）；ORM 表补 `UserPreference`/`RunChangeClock`、模型注册段落点名两个新注册 Row；两仓库新增 `delete_by_thread()` 行与 #7 小节；校正行数/方法数（353→906 行、12→25 方法；220→280 行、9→11 方法） | ✅ |
| 2 | `internals/runtime/README.md` | 新增 sync #7 要点（mutation fence / 删除清理 / 0025） | ✅ |
| 3 | `internals/runtime/01-run-manager.md` | change_seq 段补"删除不 bump clock"与 0025 说明 | ✅ |
| 4 | `internals/runtime/05-run-ownership-and-rollback.md` | 新增"线程操作 reservation 与删除清理"：`operation_kind` 谱系、共享唯一约束、release/lease 语义、DELETE 七步表、**清理 ≠ 防复活**边界 | ✅ |
| 5 | `observability/02-run-events-and-journal.md` | 新增"变更串行域与删除签名"：进程内每线程锁 / PG advisory lock / SQLite / JSONL；owner-scoped 三态删除签名；legacy 第三方实现兼容；seq 归零语义 | ✅ |
| 6 | `operations/app-layer/{00-overview,01-api-reference}.md`、`operations/integration/02-api-reference.md` | DELETE `/api/threads/{id}` 的清理顺序、reservation、owner 解析一次、best-effort 边界 | ✅ |
| 7 | `testing/06-ci-and-automation.md` | 新增 `*-dev` 通配小节 + skill-review-ci 显式钉 `2.1.x-dev` 的例外说明 | ✅ |
| 8 | `frontend/{04-workspace-layout,06-architecture,README}.md` | 嵌套 `SidebarMenu` 的 `w-auto` 宽度约束（#5681/#5682）与可迁移经验；`src/content` 手册（subagents 11 页 / extensions 10 页、`asIndexPage`、锚点迁移） | ✅ |
| 9 | `harness-engineering/01-agent-docs-system.md` | AGENTS 文件数 28（口径说明）；预算实测 14.9/28.4/36.3/41.3 KB；新增"行号漂移"第二案例（root AGENTS 净减 1 行 → 其后所有行号 -1） | ✅ |
| 10 | `harness/08-deerflow-audit.md` | 根 AGENTS 行号引用校正：L221→**L220**、L227-228→**L226-227**、L213→**L47**、L79→**L77**；`##` 数 7→6；深层四份行数 397/379/351/302→397/380/364/302 | ✅ |
| 11 | `internals/harness-hooks/09-packaged-extensions.md` | 贡献类型措辞漂移（4 组 vs 五种，代码契约未变）；run evidence 脱敏口径澄清；新增用户手册路径 | ✅ |
| 12 | `_faq_on_digested/` | 14 处基线标注 `v2.1.0-rc0` → `v2.1.0`（均属"当前基线/行号出处"类）；README 追加 sync #7 说明；历史同步标记全部保留 | ✅ |
| 13 | `_upstream-sync/` | `SYNC.md` 锚点 #7 + 分叉警告 + 改写后的同步流程；`SYNC_LOG.md` #7；本文件 | ✅ |
| 14 | 数字审计 | 全量 grep `rc0` / `769589e8`（107 处）；迁移 0024→0025；行数/方法数/AGENTS 计数逐一实测 | ✅ |

## 数字审计结果

- **rc0 标注**：107 处（`_faq_on_digested` 61 + `_digest` 46）→ 其中 14 处属"断言当前基线"的 (b) 类，改为 `v2.1.0`；93 处为 `🔄 同步 #6` 历史记录或 `🆕/breaking/起` 的引入版本事实，原样保留。
- **行号影响**：FAQ 引用的源码文件与本次实质改动清单**交集为 0**，故行号全部继续有效（只改版本标注）。
- **迁移链**：head `0024_project_documents` → **`0025_repair_run_change_seq`**；ORM 注册表 +`RunChangeClockRow` +`UserPreferenceRow`。
- **仓库行数**：`persistence/run/sql.py` 868→**906**（方法 24→25）；`persistence/feedback/sql.py` 255→**280**（方法 10→11）。
- **AGENTS.md**：仓库内文件名恰为 `AGENTS.md` 者 28 个（另有 `backend/docs/GITHUB_AGENTS.md` 变体）；root **239→238 行**、`extensions/` 379→**380**、`runtime/` 351→**364**、`persistence/migrations/` 166→**167**。
- **CI**：6 个 workflow 改 `*-dev` 通配，`skill-review-ci` 由 `2.0.x-dev` → **`2.1.x-dev`**（不是 `*-dev`）。

## 遗留

- `upstream/main` 的 **189 commits**（2.2 线，最新 `3a862780`）未消化，留待 sync #8；`SYNC.md` 已记录"先判断 tag 与 main 是否分叉"的新流程。
- `_digest/harness/08-deerflow-audit.md` 中其余引用（frontend/AGENTS.md、skills/AGENTS.md 等）本轮未逐一复核行号——本次改动不涉及那些文件，但同类行号脆弱性已在该文档与 `harness-engineering/01-agent-docs-system.md` 中写明。

---

## 第二轮：源码 → digest 反向核对（用户要求"再扫一遍"）

第一轮是**跟着 `v2.1.0-rc0..v2.1.0` 的 diff 补文档**；第二轮改成**从 v2.1.0 源码出发**核对 digest，专门找三类问题：

- **新的**：源码里有、digest 里没有的契约 → 找位置补进去；
- **变的**：语义/名称/数字变了 → 改正；
- **少的**：digest 里描述、源码已不存在 → 删除或改写。

方法：7 路并行（persistence / runtime·app-layer / frontend / CI·版本·部署 / AGENTS 文档体系 / middleware / FAQ）+ 3 路补充（覆盖缺口 / 已删除项 / 配置·路由·命令）+ 机械脚本（路径存在性、文件行数、`file:line` 越界、死链、环境变量名、CamelCase 类名、依赖版本 pin、重复文档、SVG 数字）。

### 结果分类

| 类别 | 数量级 | 代表 |
|------|--------|------|
| 旧名/旧符号（源码已改名） | 20+ 处 | `DeferredToolRegistry`→`DeferredToolCatalog`（FAQ 8 + digest 2）；`InMemoryStreamBridge`→`MemoryStreamBridge`；`_build_middlewares`→`build_middlewares`（10 处 + 3 SVG）；`deerflow/auth/internal_token.py`→`app/gateway/internal_auth.py`；`langgraph_runtime.py`→`deps.py::langgraph_runtime()` |
| 不存在的变量/配置键 | 6 处 | `DEER_FLOW_AUTH_ENABLED`（真值：认证默认开，`DEER_FLOW_AUTH_DISABLED=1` 关闭）；`DATABASE_BACKEND`/`POSTGRES_URI`（真值 `database.backend` + `database.postgres_url`） |
| 远古架构残留 | 3 篇重写 | `operations/deployment/01-docker.md`（`langgraph`/postgres 服务、`:8000`）；`operations/integration/03-docker.md`（同类）；`getting-started/04-local-dev.md`（4 进程 → 3 服务） |
| 计数过期 | 20+ 处 | ORM 表 6→**22**；middleware 18/19→**37**；测试文件 704/194→**738**；workflow 6→**16**；IM 平台 7→**8 + GitHub**；仓库行数十余处（如 `manager.py` 655→**2424**、`journal.py` 572→**1300**） |
| 行号漂移 | 25+ 处 | FAQ 11、middleware 2、harness 2、根 AGENTS 2、persistence 7、observability 若干 |
| 覆盖缺口（新增补写） | 6+ 处 | `contracts/run_event_stream_contract.json` → observability 新增"冻结契约"小节 + 用契约 `known_gaps` 重写缺口表；`contracts/{slash_skill,subagent_status,skill_review}` → concepts；persistence 的 `create_thread_operation_atomic`/`reserve_checkpoint_write` 落点；runtime 读取契约分页边界；middleware hook 表按 AST 重建 |
| 重复文档 | 1 组 | `operations/integration/` 与 `operations/{app-layer,deployment,channels}` 重叠（docker/api/channels）→ 收敛为"权威一份 + 引用" |
| 单位/口径错误 | 3 处 | AGENTS 预算 KB vs **KiB**（backend 27.75 KiB 实际**未**超 28 KiB 软线）；"29 个 AGENTS.md"需声明口径（恰名 28 + 变体 1）；middleware "37" 需声明构成（35 类 + 2 槽位） |
| 新增测试/文档面 | — | 补 `test_migration_0025_repair_run_change_seq.py` 等测试锚点；CI 三个从未提及的 workflow（container/chart/lark-cli-images） |

### 结论

- 这些**绝大多数不是 v2.1.0 引入的**，而是 rc0 甚至更早遗留的漂移（v2.1.0 只有 10 个 commit，与它们不相干）——说明"跟随 diff 同步"会天然漏掉**未被 diff 触碰但已过期**的内容，**必须保留"源码→digest"这个方向的独立扫描**。
- 机械脚本可覆盖的维度（路径/行数/越界/死链/变量/类名/版本 pin）已全部归零或只剩已声明的例外；语义层结论由各分路源码证据支撑。
- 仍无法机械验证的两项：`testing/09` 的"3451 个测试 / 约 12 个真实 LLM"（口径需 CI 同构环境重测）与 `harness/08` 的评分总分（需整轮重算）——已在对应文档标注，留给下一轮。

---

## 第三批：覆盖缺口补写（"新的要给它找位置"）

第二轮末尾产出了一份**符号级缺口清单**（源码有、digest 0 命中）。第三批按"每条都要读源码 + 只写非琐碎契约 + 优先追加进已有文档"的原则补齐：

| 领域 | 落点 | 内容 |
|------|------|------|
| checkpoint 表示 | **新建** `internals/persistence/checkpoint-dual-mode-and-history-cache.md` | full/delta 双模式、进程冻结、元数据 `absence = full`、fail-closed 门、delta 历史缓存（不可变键/memory·redis 后端）、`CachedHistorySaver`、mode 适配 state schema |
| Store / schema | `internals/persistence/db-checkpointer-store-backends.md` | Store 工厂 4 入口；`postgres_schema` 双驱动固定（options 合并、`%20`、小写 plain id） |
| stream | `internals/runtime/{02-stream-bridge,README}.md` | **Redis StreamBridge + `StreamGap`**（修正原后端表）、对外 stream mode 词表（`messages-tuple→messages` 唯一映射、无静默 fallback）、心跳校验 |
| model-layer | `internals/model-layer/{00-overview,README}.md` | MiMo / StepFun 两个自研适配器（9 类 / 11 路由，旧口径 7/9）+ 共享 `assistant_payload_replay`（签名匹配、绝不回卷） |
| config | `internals/configuration/{04-config-reference,05-summarization-deep-dive}.md`、`internals/harness-hooks/02-singleton-propagation.md` | 7 个缺失段（`llm_call`/`run_ownership`/`dedupe_storage`/`agent_storage`/`skill_scan`/`suggestions`/`input_polish`）+ 4 个 checkpoint 子配置；手动压缩宿主契约；`STARTUP_ONLY_FIELDS` 18 条单一来源 |
| extensions | `internals/harness-hooks/09-packaged-extensions.md` | 宿主侧组装投影、通知循环、语义定位→下标 anchors、run-evidence cursor scope；`placement`/`state`/`runtime_bridge` 三模块精确契约 |
| skills | **新建** `concepts/skills-tools/skill-review-core.md`（+ 目录 README） | `skills/review/` 三管线与三个 JSON 契约、SkillScan 适配、失败模式 |
| memory | **新建** `concepts/memory/manager-contract-and-backend-clients.md` | MemoryManager ABC 分层/不变量/读失败策略、`get_memory_tools` 工具面、summarization hook、5 个后端 client 初始化与失败模式 |
| persistence 仓储 | `operations/scheduler.md`、`operations/channels/05-user-connections.md`、`operations/security/01-auth.md`、`concepts/subagent/dual-threadpool-and-lifecycle.md` | scheduled 父投影/领域异常/预算原语；channel 连接仓储 + 凭据 cipher；PAT 仓储；subagent batch 仓储 API 契约 |
| 其它 | `operations/app-layer/01-api-reference.md`、`operations/channels/03-thread-mapping.md`、`observability/03-tracing-providers.md` | 领域异常→HTTP 映射表（含 502/503 两个少见业务码）；SQL 版 channel↔thread 映射；tracing 三模块代码级契约 |

### 第三批的源码现状发现
- `ChannelCredentialCipher` **未接线**：类已实现、表已建，但生产构造点传不传 `cipher` 决定行为——当前生产路径 `get_credentials()` 恒 `None`、`store_credentials()` 抛 `RuntimeError`。按事实记入 `channels/05` 与 `security/05`，不作意图推断。

### 仍未做（明确留档）
- 路由器异常映射的**逐端点**覆盖（本轮只集中了散落的状态码）；`integrations/lark_cli.py`（2846 行）与 `lark_broker.py`（457 行）的完整契约；`utils/*` 工具集；`tui/*` 细节；`skills/{skillscan,storage,projection,permissions,package_files}` 的逐模块契约（本轮补了 review 内核，其余按"是否非琐碎"判断后暂缓）。
- 全仓 **in-range 错行**审计（行号合法但指向错误位置）：机械越界扫描抓不到，本轮只修了已知几处；建议下一轮用"行号处必须出现同句符号"的启发式 + 人工复核做一次专项。

---

## 第四批：把"仍未做"清单清空

第三批列出的遗留项在这一批全部落地（新建 4 篇 + 追加/重写 12 个文件）：

| 领域 | 落点 | 内容 |
|------|------|------|
| Lark CLI 托管集成 | **新建** `operations/integration/05-lark-cli-managed-integration.md`（233 行） | 安装事务与 guidance version marker、每用户凭据树事务切换（**先清 data 再 `config init`**，任务书里的顺序说反了）、`sandbox_runtime_mode` 四态 + capabilities/probe、Pattern A/B 边界、broker wire 契约、fail-open/closed 清单；并记录"无卸载入口""`kind:"shim"` 无消费者"两个上游缺口 |
| 路由异常映射 | `operations/app-layer/01-api-reference.md`（351 → **1211 行**） | AST 导出 **180/180** 端点全表 + **417 条 `raise`** 按码穷举（400…504，含 409 五类语义、410 全仓零用）；§3 修正中间件顺序错误（`Trace → CORS? → CSRF → Auth` ⇒ 无 session 无 CSRF 的 POST 是 **403 不是 401**）；`02-upload-security.md` 修 3 处源码漂移 + 413 三个来源 |
| TUI / 环境变量 | `getting-started/{06-tui,05-environment,02-configuration,01-quick-start,04-local-dev,03-python-sdk,00-config-overview,README}.md` | TUI 四模式（不是三种）+ 18 条 slash 命令全表 + 8 键位 + 持久化/输入历史/流式 reduce 契约 + 8 行降级表；env 表补齐 ~35 个变量并修正 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL`/LangSmith 别名；修 `make dev` 漏 `check.py`、backend `make test` 排除集、`make config` **不生成** `extensions_config.json`、`get_memory()` 形状（`userContext` 是编造的）等硬错误 |
| 共享 utils | **新建** `internals/shared-utils-contract.md` | `custom_events` 双发不变量、`file_io`/`assembly_io` 专用池与 ContextVar 复制、消息身份与原人消息 deepcopy、`thread_id` 规则、端口预订单例、图外 `oneshot_llm`、outline/think-block 解析边界 |
| skills 摄入链 | **新建** `concepts/skills-tools/skill-package-intake.md`；`skill-review-core.md` | `parser.py` 分词/别名/降级（含"安装门通过但 secret 永不生效"的不对称）、`installer.py` 全链路 + 失败清理 + 错误→HTTP、**SkillScan 全量 39 条规则表** + 上限常量 + 异常层级 |
| 测试数字 | `testing/09` | 738 文件 / 约 14.4k `def test_`（AST 实测）；真实外部服务用例可数：client_live 19 + policy 11 + real_llm 1 + aio 3 |

### 校验器固化
`_upstream-sync/tools/check_digest.py`（+ `README.md`）把这一路的机械检查做成可重复运行的脚本：行数断言 / 行号越界 / 死链 / 锚点 / 路径 / 环境变量 / 类名 / `module:Class` / import / 围栏，共 10 项进默认门禁；另有两个 in-range 错行启发式（`line_symbol`、`line_symbol_strict`）默认不跑、只作人工复核提示（sync #7 实测 21 → 10 处，逐条核对**全部为误报**：文档常引用行区间或一句并列多个符号）。

### 本轮仍未做（明确留档）
- `harness/08` 的**评分**未按 v2.1.0 重算（只重核事实行数与行号；评分是 2026-06 的 rc0 快照，文档已标明）。
- in-range 错行只做到"启发式 + 抽样人工复核"；批量判定需要先统一文档的引用写法。
- 上游源码树内的文档/注释问题（`AGENTS.md` 的 `make config` 描述、`backend/docs/TUI.md` 两处、`skill_storage.py` docstring、`lark_broker` 的 `kind` 消费者、`noop_manager` 注释、同名 `ScanResult`）——`ethan` 只加 `_digest/`+`_faq_on_digested/`，已在 `SYNC_LOG.md` 列表留档，交上游处理。

