---
title: "同步日志"
description: "每次同步的记录：时间、锚点变化、变更摘要、影响的 digest 更新。"
type: index
---

# 同步日志

---

## #7 — 2026-09-24（同步，锚点 = 正式版 tag）

| 项目 | 值 |
|------|-----|
| **操作** | 同步（v2.1.0-rc0 → v2.1.0，release 收尾窗口） |
| **旧锚点** | `769589e8`（tag `v2.1.0-rc0`） |
| **新锚点** | `345f08be`（**tag `v2.1.0`**，打在 release 分支 `2.1.x-dev` 上） |
| **上游新增 commits** | 10（相对 rc0） |
| **变更规模** | 90 files, +9,097 / −450 |
| **提交构成** | 3 fix（persistence / threads / frontend）+ 2 docs（subagents / extensions 用户手册）+ 1 chore(ci) + 4 chore(doc)（1 个版本号 bump：`pyproject.toml` / `uv.lock` / `Chart.yaml` / `package.json`；3 个 CHANGELOG en/zh） |
| **时间跨度** | 2026-09-18 → 2026-09-24 |
| **⚠️ 分叉警告** | `v2.1.0` **不是 `upstream/main` 的祖先**：两者在 rc0 处分叉，main 线另有 **189 commits**（925 files, +94,219 / −4,795，2.2 开发线，最新 `3a862780`）。本次 `main` 镜像指向 release tag；main 线留作下次同步（相当于一次"预支"了 #6 备注里预告的"正式版小同步"） |
| **代码层实质变更** | ① **`0025_repair_run_change_seq`**（#5517 / 修 #5516）：`0023_run_change_seq` 曾被插到已发布的 `0023_user_preferences` 之前，stamp 在 0023 及之后的库把它当"已应用祖先"而**永不执行**，永久缺 `run_change_clock` 表/`runs.change_seq` 列/游标索引，首次 bump clock 的写操作（如线程删除）报 `no such table`；0025 幂等重放 0023 的 guarded DDL，downgrade 故意 no-op；`RunChangeClockRow`/`UserPreferenceRow` 补进 ORM 注册表。② **线程删除清理**（#5535）：`DELETE /api/threads/{id}` 在 durable `delete` reservation 内依次清理文件系统数据 → checkpoints → 历史 run 行（**只删 `operation_kind="run"`**，保住保护本次请求的 reservation）→ run events → feedback → `threads_meta`，全部 best-effort，owner 只解析一次。③ **事件存储变更串行域**（#5535）：`put`/`put_batch`/`put_if_absent`/`delete_by_thread`/`delete_by_run` 共享每线程锁 + PG 事务级 advisory lock；删除签名统一 owner-scoped（三态 `user_id`，memory/JSONL 接受并忽略）。④ **CI**（#5765）：6 个 workflow 的 push 触发改为 `*-dev` 通配，`skill-review-ci` 显式钉 `2.1.x-dev`。⑤ **frontend**（#5682 / 修 #5681）：Projects 侧栏嵌套 `SidebarMenu` 加 `w-auto`，修复 kebab 被 16/32px 溢出裁掉。⑥ **文档**：#5761 subagents 单文件 → 11 页手册、#5769 extensions 10 页手册，root `AGENTS.md` 净减 1 行并新增手册路径。 |
| **影响的 digest** | `internals/persistence/db-checkpointer-store-backends.md`（迁移链 0001→0025、模型注册、两个 `delete_by_thread`、新增 #7 小节）、`internals/runtime/{README,01-run-manager,05-run-ownership-and-rollback}.md`（reservation + 删除清理 + 不 bump clock）、`observability/02-run-events-and-journal.md`（mutation fence + 删除签名）、`operations/app-layer/{00-overview,01-api-reference}.md` + `operations/integration/02-api-reference.md`（DELETE 契约）、`testing/06-ci-and-automation.md`（`*-dev` 触发）、`frontend/{04-workspace-layout,06-architecture,README}.md`（kebab 约束 + content 手册）、`harness-engineering/01-agent-docs-system.md`（AGENTS 计数/预算/行号漂移案例）、`harness/08-deerflow-audit.md`（根 AGENTS 行号引用校正）、`internals/harness-hooks/09-packaged-extensions.md`（贡献类型措辞漂移 + run evidence 脱敏口径）、`_faq_on_digested/`（14 处基线标注 rc0→v2.1.0 + README 追加 #7 说明） |
| **备注** | 本轮首次出现「tag 与 main 分叉」，同步流程本身被改写成先判分支（见 SYNC.md）。用户要求：`_digest/` 与 `_faq_on_digested/` 是源码消化的产物，源码增删改都要反映——本轮因此连**文档侧**漂移（上游 AGENTS.md 措辞、行号位移、AGENTS 数量/大小）也一并校正。更新计划见 UPDATE_PLAN_7.md。 |

### #7 第二轮：源码 → digest 反向核对（同日追加）

第一轮跟着 diff 走，第二轮**从 v2.1.0 源码出发**独立扫描，专找"新的 / 变的 / 少的"三类问题（10 路并行 + 机械脚本：路径存在性、文件行数、`file:line` 越界、死链、环境变量名、CamelCase 类名、依赖版本 pin、重复文档）。

主要发现（都是 **rc0 甚至更早**的遗留漂移，与 v2.1.0 的 10 个 commit 无因果关系）：

- **旧符号**：`DeferredToolRegistry`→`DeferredToolCatalog`；`InMemoryStreamBridge`→`MemoryStreamBridge`；`_build_middlewares`→`build_middlewares`（含 3 张 SVG）；`deerflow/auth/internal_token.py`→`app/gateway/internal_auth.py`；`langgraph_runtime.py`→`deps.py::langgraph_runtime()`。
- **不存在的变量**：`DEER_FLOW_AUTH_ENABLED`（真值：认证默认开启，`DEER_FLOW_AUTH_DISABLED=1` 才关闭）；compose 文档的 `DATABASE_BACKEND`/`POSTGRES_URI`（真值 `database.backend` + `database.postgres_url`）。
- **远古架构**：`operations/deployment/01-docker.md` 整篇（`langgraph` 服务 + postgres 服务 + `:8000`）按 `docker/docker-compose.yaml` 重写；`operations/integration/03-docker.md` 同类；`getting-started/04-local-dev.md` 的 4 进程拓扑（实为 3 服务）；`testing/06` 的 workflow 样例。
- **计数过期**：ORM 表 6→**22**、middleware 18/19→**37**、测试文件 704/194→**738**、workflow 6→**16**、IM 平台 7→**8 + GitHub**、仓库行数十余处（`runs/manager.py` 655→**2424**、`journal.py` 572→**1300**…）。
- **覆盖缺口已补写**：`contracts/run_event_stream_contract.json` → observability 新增「冻结契约」小节（并把 `known_gaps` 6 条写全）；`contracts/{slash_skill,subagent_status,skill_review}`；persistence 的 `create_thread_operation_atomic`/`reserve_checkpoint_write` 落点；runtime 读取契约分页边界；middleware hook 表按 AST 重建（删除不存在的 `after_tool`）。
- **方法论结论**：跟随 diff 的同步会漏掉"未被 diff 触碰但已过期"的内容，**必须保留"源码→digest"这个方向的独立扫描**；机械脚本能覆盖的维度现已归零或只剩已声明例外。详见 UPDATE_PLAN_7.md「第二轮」。

**第三批：按"源码有、digest 没有"补写覆盖缺口**（不跟 diff，从模块清单出发；新建 4 篇 + 追加十余处）：

- 新建：`internals/persistence/checkpoint-dual-mode-and-history-cache.md`（full/delta 表示、进程冻结、fail-closed 门、`CachedHistorySaver`、state schema 适配）、`concepts/skills-tools/skill-review-core.md`（`skills/review/` 三管线与三个 JSON 契约）、`concepts/memory/manager-contract-and-backend-clients.md`（MemoryManager ABC / `get_memory_tools` / summarization hook / 5 个后端 client 的初始化与失败模式）、`concepts/skills-tools/README.md`（目录索引）。
- 追加：Store 工厂、`postgres_schema` 双驱动固定、**Redis StreamBridge + `StreamGap`**（旧后端表本身写错）、对外 stream mode 词表、MiMo/StepFun 适配器 + `assistant_payload_replay`、`STARTUP_ONLY_FIELDS` 18 条单一来源、宿主侧组装投影/通知循环/anchors/run-evidence cursor scope、7 个缺失配置段（`llm_call`/`run_ownership`/`dedupe_storage`/`agent_storage`/`skill_scan`/`suggestions`/`input_polish`）、手动压缩宿主契约、scheduler 投影与领域异常、四类仓储契约（scheduled / channel connections + cipher / PAT / subagent batch）、tracing 三模块、extension-api `placement`/`state`/`runtime_bridge`、异常→HTTP 映射表、SQL 版 channel↔thread 映射。
- **源码现状发现（非文档错误，按事实记录）**：`ChannelCredentialCipher` 已实现、`channel_credentials` 表已建，但生产构造点不传 `cipher` → 生产路径 `get_credentials()` 恒 `None`、`store_credentials()` 抛 `RuntimeError`（"已建表、已实现、尚未接线"）；已写入 `operations/channels/05-user-connections.md` 与 `operations/security/05-production-auth-setup.md`。

---

## #6 — 2026-09-21（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `431892e1` |
| **新锚点** | `769589e8`（**tag `v2.1.0-rc0`**，2026-09-17 切割） |
| **上游新增 commits** | 304 |
| **变更规模** | 1214 files, +187,495 / -9,772 lines（历史最大同步） |
| **时间跨度** | 2026-08-25 → 2026-09-17 |
| **提交构成** | 71 feat / 192 fix / 15 test / 12 docs / 6 chore / 4 perf / 1 eval |
| **config** | config_version 36 → **45**；migrations **0017–0024**（PAT / OAuth identity / projects×2 / thread_incarnations / batch_acceptance / scheduled_occurrence_seq / user_preferences+run_change_seq / project_documents） |
| **主要变更领域** | **projects**（全新子系统 MVP Phase 1+2：项目工作区 + instructions + document shelf + promotion + trash + `<project>`/`<documents>` 上下文注入）、**subagents**（RFC #4651 layer 2 完成：acceptance checklist +1396 行 / report contract / citation verification / batch item acceptance / parent context snapshots）、**sandbox**（网络 egress 三模式 + 人工审批 + sandbox-network-proxy 容器、identity 共享、Tenki project_id 移除 breaking）、**auth**（Personal Access Tokens + authz Phase 4 + login 限流可配 + /health/ready）、**threads**（archive/trash、idempotent runs、paginated run history、conversation references + read_conversation 工具）、**搜索 provider ×4**（Tencent WSA / Serply / Sofya / recency filters）+ LightRAG、**上下文成本工程**（write payload elision、read_file 行边界续读）、**模型层**（RPM request admission、模型收藏、GLM-5.3-Flash workaround）、**scheduler**（interval 类型 + custom agent + cron preview）、**artifacts**（zip 下载 + CSV/TSV 表格预览）、**frontend**（158 files：capability center 迁出 Settings、Projects、trash、conversation outline、user preferences 跨浏览器同步）、**可观测性**（trace id 无条件下发 breaking、loop detection/promotions/tool-progress 持久化）、**skills**（本地归档安装、包导出、`/mnt/skills` 保留 breaking）、**task_continuity**（opt-in 新子系统） |
| **影响的 digest** | concepts/lead-agent、concepts/subagent、concepts/sandbox、concepts/memory、concepts/community-tools、concepts/skills-tools、concepts/builtin-tools、concepts/workspace-changes、internals/agent-loop、internals/middleware、internals/mcp、internals/configuration、internals/model-layer、internals/persistence、internals/runtime、internals/harness-hooks、observability、operations/app-layer、operations/security、operations/scheduler、operations/channels、operations/tracing、operations/deployment、testing、frontend/、getting-started、overview |
| **备注** | 首个带版本号的锚点（v2.1.0-rc0）。四个新子系统：Projects、Trash/Archive、Conversation References、Sandbox egress control。无单点大重构，但新增面极广（71 feat）。更新计划见 UPDATE_PLAN_6.md。tag 之后 main 还有 ~66 fix，正式版 v2.1.0 发布后可做一次小同步。 |

---

## #3 — 2026-07-20（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `4915b5e` |
| **新锚点** | `cd34a1a5` |
| **上游新增 commits** | 200 |
| **harness 变更** | ~450 files, +4,464 / -1,641 lines（memory 重构最大） |
| **前端变更** | 88 files, +6,235 / -1,098 lines |
| **config.example.yaml** | +282 / -61 lines |
| **主要变更领域** | **memory**（pluggable backends + DeerMem 重构 + consolidation + staleness review + tool mode + template externalization，Breaking Changes）、**security**（4 CVE + 全链路 HTML 转义 + prompt injection 中性化 + SkillScan exfil 检测 + security_fail_closed + MindIE breakout 防护）、**middleware**（+5 新：TokenBudget, DelegationLedger, DurableContext, MCPRouting, ToolOutputSynopsis）、**skills**（SkillScan Phase 1 + review quality gate + per-user isolation）、**subagents**（delegation ledger + total cap + step persistence）、**sandbox**（E2B + BoxLite 正式加入 + warm pool）、**auth/authz**（OIDC/SSO + AuthorizationProvider protocol + principal context）、**frontend**（voice dictation + branching + citation panel + composer polish + slash chips）、**Monocle**（agent observability + trace-based tests）、**MCP**（routing hints + auto-promote + per-server timeout）、**Helm chart**（first-class K8s）、**community tools**（GroundRoute, Crawl4AI, Browserless, Brave image_search） |
| **影响的 digest** | concepts/memory、operations/security、internals/middleware、concepts/skills-tools、concepts/subagent、concepts/sandbox、operations/security/01-auth、internals/configuration、internals/mcp、operations/app-layer、frontend/、operations/deployment、operations/tracing、concepts/community-tools、overview/ |
| **备注** | 200 commits 指向 2.1.0 里程碑。Memory 系统是从单体到可插拔架构的 breaking change（storage_path 语义变更、config 结构重构、API 返回结构变更）。安全从 guardrail 拦截升级为全链路 defense-in-depth。更新计划见 UPDATE_PLAN_3.md。 |

---

## #4 — 2026-08-08（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `cd34a1a5` |
| **新锚点** | `e5c62cab` |
| **上游新增 commits** | 234 |
| **变更规模** | 931 files, +141,080 / -9,322 lines |
| **时间跨度** | 2026-07-20 → 2026-08-07 |
| **提交构成** | 142 fix / 46 feat / 11 build / 6 perf / 4 test / 3 docs |
| **主要变更领域** | **sandbox**（E2B/AIO provider 大改 + orphan reconciliation + 新 **Tenki** provider）、**memory**（新 **OpenViking** backend + storage.py 重构 + markdown 存储）、**channels**（新 **Buzz** 频道 + Nostr + **Lark CLI/broker** 集成）、**runtime**（worker 重构 + multi-worker run ownership + rollback）、**authz**（pluggable authorization 落地，新 `authz/` 子包 + RFC）、**persistence**（storage rewrite 计划）、**community**（新 **browser_automation** 工具）、**workspace_changes**（全新子系统）、**frontend**（257 files 大改） |
| **影响的 digest** | concepts/sandbox、concepts/memory、concepts/community-tools、operations/channels、operations/integration、internals/runtime、operations/security/01-auth、internals/configuration、concepts/skills-tools、concepts/builtin-tools、frontend/、operations/deployment、getting-started/06-tui、operations/security/03-guardrail、concepts/subagent |
| **备注** | 以修复为主（142 fix），无 #3 那样的 breaking 重构，但新增 **6 个全新子系统**：Buzz 频道、Lark CLI、OpenViking memory backend、Tenki sandbox、Browser Automation、Workspace Changes。E2B/AIO sandbox 的代码量最大（+4000+ 行）。更新计划见 UPDATE_PLAN_4.md。 |

---

## #5 — 2026-08-25（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `e5c62cab` |
| **新锚点** | `431892e1` |
| **上游新增 commits** | 108 |
| **变更规模** | 601 files, +66,827 / -4,637 lines |
| **时间跨度** | 2026-08-08 → 2026-08-25 |
| **提交构成** | 22 feat / 65 fix / 1 perf / 9 docs / 4 build / 3 test |
| **config** | config_version 33 → **36**（config.example.yaml +244/-33，extensions_config.example.json +25） |
| **主要变更领域** | **subagents**（unified capacity + durable batch execution + managed subagents + delegation scopes + isolated date-only context）、**MCP**（durable task 完整落地：task_tool_caller + tasks/driver+ordinary+runtime + persistence/migrations 0011-0013 + gateway router + 通知/chat UI + per-user credential injection + interceptors + OpenViking tools）、**sandbox**（新 **OpenSandbox** provider，第 7 实现 + sandbox:execute 授权落地）、**memory**（新 **Honcho** 后端，第 5 个 + hybrid fact eviction）、**extensions**（packaged 管理：CLI + gateway contribution points + extension-api 5 个新模块 + 参考示例包）、**tool receipts**（确定性模型可见收据 ledger，RFC #4651 layer 1，middleware 35→36）、**threads**（branched conversations）、**knowledge**（新 **RAGFlow** 只读检索）、**MiniMax Code**（原生 ACP agent）、**scheduler**（recursion_limit 可配置 + busy 入队 + 多实例恢复）、**frontend**（68 files：分支会话树 + subagent batches + background tasks） |
| **影响的 digest** | concepts/subagent、internals/mcp、concepts/sandbox、operations/security、concepts/memory、concepts/community-tools、internals/middleware、internals/harness-hooks、operations/app-layer、internals/runtime、internals/configuration、getting-started、operations/channels、operations/scheduler、concepts/builtin-tools、frontend |
| **备注** | 无 breaking 重构，以 fix 为主（65 fix）+ 六个方向能力落地。最大新增：MCP durable task 子系统、subagent batch 子系统、extensions packaged 管理、OpenSandbox、Honcho、RAGFlow。更新计划见 UPDATE_PLAN_5.md。 |

---

## #2 — 2026-07-07（同步）

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | `162fb214` |
| **新锚点** | `4915b5e` |
| **上游新增 commits** | 323 |
| **harness 变更** | 222 files, +26,161 / -2,126 lines |
| **前端变更** | 308 files, +30,943 / -2,219 lines |
| **config.example.yaml** | +734 / -51 lines |
| **主要变更领域** | middleware（5→29 个，加了 24 个新中间件）、skills（deferred discovery、request-scoped secrets、slash activation）、sandbox（BoxLite、E2B、warm pool）、subagents（turn-budget cap、step capture、checkpointer isolation）、TUI（全新 `deerflow` 终端）、Gateway（console、trace correlation、Redis stream bridge、Alembic migrations）、memory（staleness review、token counting）、channels（GitHub webhook、user-owned connections）、testing（record/replay e2e） |
| **影响的 digest** | concepts/lead-agent、concepts/sandbox、concepts/subagent、concepts/memory、concepts/skills-tools、internals/middleware、internals/agent-loop、internals/model-layer、internals/harness-hooks、internals/configuration、internals/runtime、testing/、operations/security、operations/app-layer、operations/channels、frontend/ |
| **备注** | 这是 323 个 commit 的大版本跳跃（从 2.0-m1 → 2.1-dev）。中间件链从 19 增长到 29 个，需要全面重写相关 digest。TUI 和 deferred skill discovery 是全新子系统。 |

---

## #1 — 2026-07-06（初始锚定）

| 项目 | 值 |
|------|-----|
| **操作** | 初始锚定——记录 digest 内容对应的上游版本 |
| **锚点 commit** | `162fb214` |
| **commit 内容** | `fix(mcp): skip session pooling for HTTP/SSE transports (#3203)` |
| **上游当时 HEAD** | `fd41fdb`（已领先） |
| **落后上游** | [compare/162fb214...main](https://github.com/bytedance/deer-flow/compare/162fb214...main) |
| **digest 更新** | 无（首次锚定，digest 内容基于此版本） |

---

## 模板（下次同步时复制填写）

```
## #N — YYYY-MM-DD

| 项目 | 值 |
|------|-----|
| **操作** | 同步 |
| **旧锚点** | <OLD_COMMIT> |
| **新锚点** | <NEW_COMMIT> |
| **上游新增 commits** | N |
| **变更文件** | <git diff --stat 摘要> |
| **影响的 digest** | <哪些目录被更新> |
| **备注** | |
```
