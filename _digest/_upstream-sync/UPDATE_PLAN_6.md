---
title: "Digest 更新计划 #6"
description: "基于 upstream 431892e1 → v2.1.0-rc0 (769589e8) 的 304 commits 变更，逐目录规划 digest 更新内容和优先级。"
type: index
---

# Digest 更新计划 #6

> 基准：`431892e1` → `769589e8`（**v2.1.0-rc0**，304 commits），2026-09-21
> 变更规模：1214 files, +187,495 / -9,772 lines（历史上最大的一次同步）
> 提交构成：71 feat / 192 fix / 15 test / 12 docs / 6 chore / 4 perf / 1 eval
> 时间跨度：2026-08-25 → 2026-09-17
> config_version：36 → **45**（config.example.yaml +339/-33 行 diff）
> migrations：**0017–0024**（PAT / OAuth identity / projects×2 / thread_incarnations / batch_acceptance / scheduled_occurrence_seq / user_preferences+run_change_seq / project_documents）

## 一句话总结

这是 v2.1.0 的 release candidate 切割点，**四个新子系统 + 一个 RFC 落地完成**：

- **Projects**（MVP Phase 1+2）：项目工作区（scoped chats + thread 归属 + instructions + document shelf + promotion + trash），带独立 harness 子包、4 个新 router、3 个 migration、前端整套 UI 和 `projects:` 配置段
- **RFC #4651 layer 2 完成**：subagent delegation 的确定性验收清单（acceptance_checks.py +1396）、报告契约、receipt 引用验证、batch item acceptance
- **Trash / Archive**：会话回收站 + 归档恢复（routers/trash.py、前端 trash-view、thread archive）
- **Conversation References**：composer 引用其他会话 + `read_conversation` 工具 + 截断消息 offset 续读
- **Sandbox 网络 egress 控制**：open / isolated / allowlist 三模式 + 人工审批 + 独立 sandbox-network-proxy 容器

外加：PAT 认证、4 个新搜索 provider、LightRAG、artifacts zip/表格预览、模型收藏与 RPM 准入、上下文成本工程（write payload elision）、task_continuity。

## ▶ 步步为营执行清单

| 步 | 文件 | 做什么 |
|----|------|--------|
| 1 | `concepts/lead-agent/` | 🔴 更新：Projects 上下文注入（request-scoped `<project>`/`<documents>` 块，pinned snapshot）、conversation references 注入、custom agent Unicode 显示名 + 可关 memory、attachment-only 标题 |
| 2 | `internals/agent-loop/` + `internals/middleware/03-catalog.md` | 🔴 更新：write_file superseded/blocked payload elision（#5374/#5329，`tool_output.elide_superseded_writes`）、receipt citation verification、loop detection 事件持久化、tool-progress phase 持久化；核对 middleware 数量是否变化 |
| 3 | `concepts/subagent/` | 🔴 更新：RFC #4651 layer 2（acceptance checklist / report contract / citation verification / batch item acceptance）、parent context snapshots（#5367）、historical upload discovery（#5170） |
| 4 | `concepts/sandbox/abstract-interface-and-seven-impls.md` | 🔴 更新：网络 egress 三模式 + approval + sandbox-network-proxy 容器（#5152）、sandbox identity 共享 + acquire serialization（#5089）、read_file 行边界续读、E2B mount upload 结构化结果、Tenki `project_id` 移除（breaking） |
| 5 | `operations/app-layer/` | 🔴 更新+新增：新 routers（projects / project_documents / project_thread_files / trash / user_preferences / auth PAT）、`/health/ready`、idempotent thread runs、paginated run history、artifact_archive（zip）、upload_ingestion、conversation_access/reader |
| 6 | `operations/security/` | 🔴 更新：**Personal Access Tokens**（auth/pat.py + migration 0017）、authz Phase 4（/auth/me effective permissions、thread-delete/run-cancel gating）、sandbox egress、login rate-limit 可配置 |
| 7 | `frontend/` 全部文件 | 🔴 更新：capability center 迁出 Settings（mcp-plugin-manager / skill-gallery / plugin-gallery / skill-export）、Projects UI、trash、conversation references picker、model favorites、conversation outline、user preferences 跨浏览器同步（0023）、虚拟消息列表。158 src files +15,619 |
| 8 | `internals/configuration/` + `getting-started/` | 🔴 更新：config_version 36→45；新段：`projects:`、`task_continuity:`、`sandbox.network:`、`request_admission`、`recursion_limit` 可配默认值、`heartbeat_interval_seconds`、`elide_superseded_writes`、auth.local 限流；新工具示例：read_conversation / LightRAG / Serply / Sofya / Tencent WSA |
| 9 | `internals/mcp/` | 🟡 更新：Settings 页管理 MCP servers（#5022）、request-scoped secrets → HTTP/SSE headers（#5010）、Parallel Search server（#5028）+ Parallel UA 标识、session pool 修复 |
| 10 | `concepts/community-tools/` | 🟡 更新+新增：01-web-search（+Serply / Sofya / Tencent WSA / recency filters / Firecrawl self-host）、02-web-fetch（+Sofya / Firecrawl self-host）、07-ragflow 旁加 **LightRAG**（#5209，同一 knowledge_search 工具的第二 provider） |
| 11 | `internals/model-layer/` | 🟡 更新：模型收藏、RPM request admission（共享 group 配额排队）、GLM-5.3-Flash thinking workaround（#5074）、`use_previous_response_id`、`context_window` 驱动 fraction summarization trigger |
| 12 | `internals/runtime/` | 🟡 更新：thread incarnations（migration 0019）、run change_seq（0023）、scheduled occurrence seq（0022）、user_preferences（0023）、trace id 无条件下发（breaking，#5119）、gateway 内存回收 perf |
| 13 | `concepts/memory/` | 🟡 更新：确定性近重复 fact gate（#5254）、custom agent 禁用 memory（#5167） |
| 14 | `operations/scheduler.md` | 🟡 更新：interval 调度类型（#5291）、任务可固定 custom agent（#5288）、cron 下次执行预览（#5381）、run history 分页 + 状态过滤、重复任务（#5064） |
| 15 | `concepts/builtin-tools/` | 🟡 更新：`read_conversation` 工具（D-task-toolsearch）、list_uploaded_files 过滤、tools OpenAI 兼容图像生成（#5389） |
| 16 | `internals/harness-hooks/09-packaged-extensions.md` | 🟢 更新：in-place upgrade 保留私有配置（#5347）、config 中间件 constructor kwargs（#5312）、incremental run evidence reader（#5405） |
| 17 | `operations/channels/` | 🟢 更新：会话级 custom agent 选择（#5168）、WeCom/SK `allowed_media_hosts`、Buzz/Discord 修复 |
| 18 | `concepts/skills-tools/` | 🟢 更新：本地 skill 归档安装（#5039）、skill 包导出 + revision-bound preview（#5332）、deferred discovery 按 agent intent 排序（#5369）、`/mnt/skills` 保留路径（breaking #4178） |
| 19 | ⚪ 新 digest | ⚪ 评估：Projects 子系统（体量足够单独立档：`concepts/projects/`）；task_continuity 可并入 lead-agent/记忆相关文档 |
| 20 | 🔢 数字审计 | grep 全 digest 修复旧数字：config_version 36→45、migrations 0016→0024、middleware 数量、sandbox 7 实现（不变但接口变化）、搜索 provider 数 |
| 21 | 🔗 交叉引用检查 | 确保所有链接可达（含新增 projects/trash 页面引用） |
| 22 | 🚶 开发者旅程走查 | 模拟完整阅读路径 |
| 23 | `internals/persistence/` | 🔴 更新（查漏补充）：migrations 0017–0024 的**主记录地**、events store 修复×4（JSONL/DB lock 生命周期、cancellation 排空、Unicode 分隔符）、`docs/database-forward-revision-recovery.md` 对应的 forward revision 兼容 |
| 24 | `observability/` + `operations/tracing/` | 🔴 更新（查漏补充）：**trace id 无条件下发**（每个 HTTP 响应带 `X-Trace-Id`，breaking，`logging.enhanced` 只管日志格式）、`deerflow_trace_id` metadata 被覆盖改用请求头、worker trace binding（#5119 相关）、loop detection / deferred promotions / tool-progress phases 三类事件持久化 |
| 25 | `operations/deployment/` + `testing/` | 🟡 更新（查漏补充）：nginx 60s 超时修复（model-bound /api/threads，#5505）、helm chart（configmap-nginx / gateway-deployment / values）、docker compose、`make start SKIP_FRONTEND_BUILD=1`（#5053）、CI 后端测试分片（#5137）、**node 22→24**（#5063）、skill-review waivers 机制（`.github/skill-review-waivers.v1.json` + `scripts/skill_review_waivers.py`，两段式合并流程）、sandbox-image-smoke workflow、`backend/.test_durations` |
| 26 | `getting-started/`（03-python-sdk / 04-local-dev / 06-tui）+ `overview/` | 🟡 更新（查漏补充）：DeerFlowClient 修复×3（AI message 追加文本 #5479、流式 tool call 完整 args 一次性发出 #5408、embedded agent 按生效用户隔离 #5206）、TUI transcript 滚动位置（#4975）、doctor/ollama extra 探测、依赖变化（**tenki 包改名** tenki-sandbox→tenki、ollama extra、next 16.2→16.3、xmldom 升级）、README/CHANGELOG/ARCHITECTURE 大改 |
| 27 | `concepts/workspace-changes.md` + uploads 链路 | 🟢 更新（查漏补充）：`app/gateway/upload_ingestion.py` 新增、去重文件名 255 字节上限（#5059）、document outline 修复×3（有界预览 #5323、ATX 标题 #5316、排除 fenced code #5281）、`list_uploaded_files` 名称/扩展名过滤（#5341） |

---

## 详细变更分析

### 1. Projects — 全新子系统（本轮最大）

| commit | 内容 |
|--------|------|
| `5951c89b` | feat(projects): project workspaces with scoped chats and thread membership (#5265) |
| `a58ab484` | feat(projects): MVP Phase 2 — instructions, document shelf, promotion, trash (#5443) |

- harness 新子包 `deerflow/projects/`；migrations `0019_projects` / `0019_thread_incarnations` / `0020_threads_meta_project_id` / `0024_project_documents`
- gateway 新 routers：`projects.py` / `project_documents.py` / `project_thread_files.py` / `trash.py`
- 成员线程收到 request-scoped `<project>` instructions 块（run admission 时 pin 的快照渲染，不进 system prompt / 持久历史）；document shelf 渲染有界 `<documents>` 索引
- config 新段 `projects:`（instructions_max_bytes 8192 / shelf_index_max_entries 50 / shelf_index_max_bytes 4096 / trash_retention_days 30）
- 前端：projects 页面、move-to-project、project documents/threads section、composer 附加

### 2. Subagent RFC #4651 layer 2 — delegation 验收落地

| commit | 内容 |
|--------|------|
| `22b0456e` | subagent report contract and delegation acceptance criteria (#5090) |
| `a06a6fed` | deterministic acceptance checklist for subagent delegations (#5109) |
| `3b592c20` | subagent receipt citation verification (#5076) |
| `0b3dadbc` | acceptance checks to durable batch items (#5289)（migration 0021） |
| `6d5d7bb1` | opt-in parent context snapshots (#5367) |
| `fb28ed01` | historical upload discovery (#5170) |

新文件：`subagents/acceptance_checks.py`（+1396 行）、`subagents/report_contract.py`。

### 3. Sandbox — 网络 egress + 身份共享

| commit | 内容 |
|--------|------|
| `0f7d8709` | controlled egress with approvals (#5152) |
| `bb75f8d7` | share sandbox identity derivation and acquire serialization (#5089) |
| `e5977320` | structured mount upload result on E2B (#4884) |
| `0dd233af` | E2B mount upload deadline configurable (#4876) |

- `sandbox.network.mode: open | isolated | allowlist` + `approval: deny|prompt` + `temporary_grant_ttl` + 独立 `sandbox-network-proxy` Docker 容器（需 Docker Engine 28+，不支持 Apple Container / provisioner）
- 新 `sandbox/identity.py`、`sandbox/acquire_serialization.py`；人工审批通过 Human Input card
- read_file 截断落在行边界并标注 `next start_line`
- breaking：Tenki `project_id` 配置移除（Tenki 1.x 删除 projects 概念）

### 4. Auth — PAT + Phase 4 authz

| commit | 内容 |
|--------|------|
| `bf740ffa` | personal access tokens (#5041)（`gateway/auth/pat.py` + migration 0017） |
| `c55f2424` | effective route permissions on GET /auth/me (#5228) |
| `ec0ac474` | gate thread-delete and run-cancel UI on permissions (#5294) |
| `08b27aef` | login rate-limit parameters configurable (#5110) |
| `4791e94a` | /health/ready readiness probe (#5166) |

### 5. 搜索 / Knowledge provider 扩容

| commit | 内容 |
|--------|------|
| `846c7165` | Tencent Cloud WSA provider (#5057) |
| `4dbfe37f` | Serply web search tool (#5023) |
| `23bd7604` | Sofya web search provider (#5239) |
| `8c8c5ac2` | native recency filters (#5099) |
| `aec7d738` | LightRAG read-only retrieval (#5209) |
| `90359344` | optional Parallel Search MCP server (#5028) |

Firecrawl 支持 self-host `base_url`（web_search + web_fetch 都可以免云 key）。Sofya 也提供 web_fetch。

### 6. 上下文成本工程（write payload elision）

| commit | 内容 |
|--------|------|
| `cf556fa9` | elide superseded write_file payloads from model-bound requests (#5374) |
| `3f0b6ecc` | elide blocked write payloads (#5329) |
| `4ad55f59` | continue reading a cut message by offset (#5434) |

- `tool_output.elide_superseded_writes / superseded_write_min_chars / keep_recent_writes`；`read_before_write.elide_blocked_payloads / elide_min_chars`
- 只改 model-bound 请求，stored history / receipts / journal 保留原文
- read_file 截断可从标注行续读

### 7. Threads / 会话管理

- archive & restore（#5236）+ trash（前端 trash-view，routers/trash.py）
- idempotent thread runs（#5258）、paginated thread run history（#5283）
- conversation references：composer 引用其他会话（#5465/#5463）+ `read_conversation` 工具（opt-in，Gateway API only）+ capability 上报
- thread incarnations（expand-phase 存储，migration 0019）
- renamed title 全端同步（#5045）

### 8. 模型层

- user model favorites（#5441，前端 favorites-store）
- RPM request admission：`request_admission.requests_per_minute / group / max_wait_seconds / max_queue_size`（#5432）
- GLM-5.3-Flash thinking workaround（#5074，`PatchedChatDeepSeek` profile）
- `use_previous_response_id`（OpenAI responses API 增量发送）
- fraction summarization trigger 现在从模型 `context_window` 解析阈值

### 9. Scheduler / Observability / Extensions / Skills / Memory / Channels

- Scheduler：interval 类型（#5291）、pin custom agent（#5288）、cron preview（#5381）、run history 分页+状态过滤（#5363/#5384）、duplicate（#5064）、occurrence seq migration 0022
- Observability：loop detection 事件持久化（#5127）、deferred tool promotions 持久化（#5183）、tool-progress phase transitions（#5214）、trace id 无条件下发（breaking #5119）
- Extensions：run evidence reader（#5405）、in-place upgrade（#5347）、constructor kwargs（#5312）
- Skills：local archive install（#5039）、package export（#5332）、OpenAI 兼容图像生成（#5389）、intent ranking（#5369）、`/mnt/skills` 保留（breaking #4178）
- Memory：near-duplicate fact gate（#5254）、agent 级禁用（#5167）
- Channels：per-conversation custom agent（#5168）、`allowed_media_hosts`（WeCom/SK）
- 新 `task_continuity` 子系统（#5382，opt-in，docs/task-continuity.md + docs/experiments/task-continuity-20260912/ 完整实验）

---

## 变更→digest 映射速查

| 上游改了 | digest |
|---------|--------|
| `harness/projects/` + `app/gateway/routers/projects*` | `concepts/projects/`（新）、`concepts/lead-agent/`、`operations/app-layer/` |
| `harness/subagents/`（acceptance_checks/report_contract） | `concepts/subagent/` |
| `harness/sandbox/` + `docker/sandbox-network-proxy/` | `concepts/sandbox/`、`operations/security/` |
| `app/gateway/auth/pat.py` + authz | `operations/security/` |
| `app/gateway/routers/{trash,user_preferences,health}` | `operations/app-layer/` |
| `harness/mcp/`（headers/context_headers/Parallel） | `internals/mcp/` |
| `community/{serply,sofya,tencent_wsa,lightrag}/` | `concepts/community-tools/` |
| `agents/middlewares/`（elision/receipt_verification/loop_detection） | `internals/middleware/`、`internals/agent-loop/` |
| `models/`（admission/favorites/GLM workaround） | `internals/model-layer/` |
| `runtime/`（incarnations/change_seq/trace） | `internals/runtime/` |
| `persistence/`（migrations 0017–0024、events store） | `internals/persistence/` |
| trace 中间件 + events 持久化 | `observability/`、`operations/tracing/` |
| `docker/ deploy/ Makefile scripts/ nginx` | `operations/deployment/` |
| `.github/workflows/ skill-review-waivers` | `testing/` |
| `client.py` + `tui/` | `getting-started/03-python-sdk`、`getting-started/06-tui` |
| `uploads/`（outline/ingestion/255 字节） | `concepts/workspace-changes.md`、`operations/app-layer/` |
| `README CHANGELOG ARCHITECTURE docs/` | `overview/` |
| `config.example.yaml`（v45） | `internals/configuration/`、`getting-started/` |

---

## 完整性审计（2026-09-21 查漏）

本计划经过一轮系统性查漏后定稿，方法与结论：

1. **feat 逐条对账**：71 个 feat commits 全部映射到执行清单步骤（含 SKIP_FRONTEND_BUILD、tool details debug、cron preview 等小 feat）。
2. **scope 分布对账**：25 个 commit scope 全部落点——`sandbox(30) frontend(29) agents(19) gateway(15) mcp(14) skills(12) subagents(11) runtime(10) models(9) channels(8) scripts(7) ci(6) uploads(4) scheduler(4) memory(4) events(4) harness(3) extensions(3) client(3) authz(3) auth(3) tools(2) tui(1) deps(3) eval(1)`。
3. **digest 目录对账**：对照 `_digest/` 实际 31 个目录逐一检查覆盖，第 23–27 步为查漏补充（此前遗漏 `internals/persistence`、`observability`、`operations/tracing`、`operations/deployment`、`testing`、`overview`、`concepts/workspace-changes` 的落点）。
4. **顶层/infra 对账**：Makefile、docker/、deploy/helm/、.github/、scripts/、backend/pyproject.toml（依赖变化）、backend/docs/（API/CONFIGURATION/MCP_SERVER/RUN_EVENT_STREAM 大改 → app-layer/configuration/mcp 步骤覆盖）均已入表。
5. **breaking 对账**：本轮 4 个 breaking（trace id 无条件下发、`/mnt/skills` 保留、Tenki project_id 移除、recursion limit 不再硬编码 100）+ 租约内的 E2B replicas 语义收紧，分别落在步骤 4/18/24/8。
6. **数字锚点**：config_version 36→45、migrations 0016→0024、版本号 2.1.0-rc0，供步骤 20 数字审计 grep。
| `frontend/`（projects/capabilities/trash/references） | `frontend/` |
| `app/scheduler/` | `operations/scheduler.md` |
| `app/channels/`（allowed_media_hosts） | `operations/channels/` |
| `skills/`（archives/export/mnt 保留） | `concepts/skills-tools/` |
| `persistence/migrations 0017–0024` | `internals/runtime/`、`operations/app-layer/` |
