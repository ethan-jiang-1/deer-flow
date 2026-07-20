---
title: "Digest 更新计划 #3"
description: "基于 upstream 4915b5e → cd34a1a5 的 200 commits 变更，逐目录规划 digest 更新内容和优先级。"
type: index
---

# Digest 更新计划 #3

> 基准：`4915b5e4` → `cd34a1a5`（200 commits），2026-07-20
> 变更规模：594 files, +67,322 / -6,767 lines
> 指向 2.1.0 里程碑

## ▶ 步步为营执行清单

| 步 | 文件 | 做什么 |
|----|------|--------|
| 1 | `concepts/memory/extract-queue-persist-pipeline.md` | 🔴 重写：pluggable backends, memory.mode, consolidation, staleness, tool sets |
| 2 | `operations/security/03-guardrail.md` | 🔴 重写：4 CVE, 全链路 HTML 转义, SkillScan exfil, security_fail_closed |
| 3 | `internals/middleware/03-catalog.md` | 🔴 重写：+5 新中间件（TokenBudget, DelegationLedger, DurableContext, MCPRouting, ToolOutputSynopsis） |
| 4 | `internals/middleware/02-chain-assembly.md` | 🟡 更新：declarative layered builder, ThreadData 顺序变更 |
| 5 | `concepts/skills-tools/skill-md-and-tool-assembly.md` | 🟡 更新：SkillScan phase 1, deferred discovery, skill review gate, per-user isolation |
| 6 | `concepts/subagent/dual-threadpool-and-lifecycle.md` | 🟡 更新：delegation ledger, total cap, step persistence, token budget 共享 |
| 7 | `concepts/sandbox/abstract-interface-and-five-impls.md` | 🟡 重命名+更新：3→5 实现（+E2B +BoxLite），warm pool, env scrubbing |
| 8 | `operations/security/01-auth.md` | 🟡 更新：OIDC/SSO, AuthorizationProvider, principal context, keep-me-signed-in |
| 9 | `internals/configuration/01-config-yaml.md` | 🟡 更新：memory 段重构, authz 新段, memory.mode |
| 10 | `internals/configuration/04-config-reference.md` | 🟡 更新：新字段列表 |
| 11 | `internals/runtime/goal-continuation.md` | 🟢 验证+更新：continuation_count 修复 |
| 12 | `internals/mcp/session-pool-oauth-cache-invalidation.md` | 🟡 更新：routing hints, auto-promote deferred tools, per-server timeout |
| 13 | `operations/app-layer/00-overview.md` | 🟡 更新：auth routers, memory tool routes, monocle |
| 14 | `operations/app-layer/01-api-reference.md` | 🟡 更新：新端点（OIDC, memory tools, monocle） |
| 15 | `frontend/` 全部文件 | 🟡 更新：voice dictation, branching, citation panel, composer polish, slash chips |
| 16 | `overview/01-system-overview.md` | 🟢 验证数字 |
| 17 | `internals/agent-loop/` 全部文件 | 🟢 验证数字和 middleware 名称 |
| 18 | `operations/deployment/02-nginx-and-k8s.md` | 🟡 更新：Helm chart |
| 19 | `testing/` 全部文件 | 🟢 验证：Monocle Test Tools, skill review CI |
| 20 | `operations/tracing/` | 🟡 更新：Monocle observability |
| 21 | `concepts/community-tools/` | 🟡 更新：GroundRoute, Crawl4AI, Browserless, Brave image_search |
| 22 | 🔢 数字审计 | grep 全 digest 修复旧数字 |
| 23 | 🔗 交叉引用检查 | 确保所有链接可达 |
| 24 | 🚶 开发者旅程走查 | 模拟完整阅读路径 |

---

## 优先级说明

| 级别 | 含义 |
|------|------|
| 🔴 P0 | **必须重写**——旧内容已严重过期，不更新会误导 |
| 🟡 P1 | **需要更新**——核心内容有新增或变更 |
| 🟢 P2 | **需要验证**——内容可能仍然正确，需对比确认 |
| ⚪ P3 | **建议补充**——全新子系统，值得添加但非紧急 |

---

## 🔴 P0：必须重写（3 个领域）

### 1. `concepts/memory/` — Memory 系统大重构（Breaking Changes）

**变化**：这是本轮最大的变更。Memory 从写死的 DeerMem 变成可插拔后端架构。

| 关键变更 | 细节 |
|---------|------|
| **Pluggable backends** | `memory.manager_class` 选择后端（默认 `deermem`，新增 `noop`）。DeerMem 代码从平铺结构迁移到 `backends/deermem/` 子包。 |
| **`memory.mode`** | 新增 `middleware`（被动注入，旧行为）vs `tool`（模型主动调用 `memory_search`/`add`/`update`/`delete` 工具） |
| **Memory consolidation** | 合成碎片化 fact（`consolidation.yaml` prompt） |
| **Staleness review** | LLM 给每个 fact 分配 `expected_valid_days` + `staleFactsToExtend`，同一次调用中检测过期 fact |
| **Template externalization** | Memory prompts 外置为 YAML 模板（`fact_extraction.yaml`, `staleness_review.yaml`, `consolidation.yaml`, `memory_update.chat.yaml`） |
| **Config 重构** | 所有 DeerMem 私有字段从 `memory.*` 迁移到 `memory.backend_config.*`；`/memory/config` API 返回结构变更 |
| **Breaking: storage_path** | 从 FILE 路径变为 DIRECTORY 路径；per-user memory 在 `{storage_path}/users/{uid}/memory.json` |
| **Memory injection identity** | 记录每个 run 的 effective memory identity |

| 文件 | 行动 |
|------|------|
| `extract-queue-persist-pipeline.md` | 🔴 **重写**：标题可能改为 memory-architecture.md，覆盖 backend 抽象、DeerMem/Noop 两种实现、middleware vs tool 双模式、consolidation + staleness 流程、template externalization、config 结构 |

### 2. `operations/security/` — 安全加固（17+ security commits, 4 CVE）

**变化**：安全模型发生了质变——从"guardrail 拦截危险内容"扩展到"全链路 tag 中性化 + prompt injection 防御 + 静态外泄检测"。

| 关键变更 | 细节 |
|---------|------|
| **4 CVE 修复** | CVE-2026-33128, CVE-2026-35209, CVE-2026-49476, CVE-2026-49477 |
| **全链路 HTML 转义** | memory facts → injection prompt、SOUL.md → `<soul>` block、subagent 描述 → `<subagent_system>` block、summarization input blocks、web_capture 结果、tool 结果、MindIE tool-response breakout、conversation block in MEMORY_UPDATE_PROMPT |
| **Prompt injection 标签中性化** | web_capture 结果、remote tool 结果中的注入标签 |
| **Forged framework tag 阻断** | Input guardrail 阻断伪造的 `</tool_response>` 等框架标签 |
| **SkillScan exfil 检测** | 静态分析检测通过 instance/dataflow network clients 的数据外泄（`requests`/`httpx` HTTP methods、`os.environ` from-import 模式） |
| **`security_fail_closed`** | Moderation model 挂掉时拒绝而非放行 |
| **NTFS ADS smuggling** | 拒绝 zip 成员名中的冒号 |
| **Sandbox env scrubbing** | 擦洗 `MYSQL_PWD`、`REDISCLI_AUTH`、`*_PASS`、`PGPASSFILE` |
| **Guardrail context** | `GuardrailRequest` 暴露 authenticated runtime context；security interventions 持久化为 run events |

| 文件 | 行动 |
|------|------|
| `03-guardrail.md` | 🔴 **重写**：从 "3 层 guard" 扩展为 "全链路 defense-in-depth"——input sanitization、output sanitization、static exfil detection、framework tag blocking、moderation fail-closed、secrets redaction |

### 3. `internals/middleware/` — Middleware 链更新

**变化**：新增 5 个中间件，多个已有中间件有重要更新。

| 新增中间件 | 作用 |
|-----------|------|
| **TokenBudgetMiddleware** | 跨 lead agent + subagents 的共享 token 预算 |
| **DelegationLedger** | 防重复委托 + 总委托数上限 |
| **DurableContextMiddleware** | Persistent context across summarization（system messages, memory, tool state 不丢） |
| **MCPRoutingMiddleware** | MCP routing hints 引导模型到正确的 MCP server |
| **ToolOutputSynopsisMiddleware** | 超大 tool output 的结构化摘要替代原始输出 |

| 已有中间件更新 | 变化 |
|---------------|------|
| **LoopDetectionMiddleware** | 窗口化 tool-frequency counter（长 run 不误触发） |
| **InputSanitizationMiddleware** | Forged framework tag 阻断 |
| **SummarizationMiddleware** | Durable context 支持 |
| **ThreadDataMiddleware** | 顺序提前到 Uploads 之前 |
| **SkillActivationMiddleware** | 每个 run 只激活一次 slash skill |
| **ToolErrorHandlingMiddleware** | Dangling tool call 修复 + malformed tool-call id 恢复 |

| 文件 | 行动 |
|------|------|
| `03-catalog.md` | 🔴 **重写**：添加 5 个新中间件，更新已有中间件描述 |
| `02-chain-assembly.md` | 🟡 **更新**：declarative layered builder、ThreadData 顺序变更、两阶段组装是否有变化 |

---

## 🟡 P1：需要更新（11 个领域）

### 4. `concepts/skills-tools/` — Skills 系统升级

**变化**：
- **SkillScan Phase 1**（`skillscan/` 子包）：加载时静态分析——orchestrator 协调多 analyzer，检测 outbound network sinks、`os.environ` 访问
- **Deferred discovery**：`describe_skill` tool 让模型按需获取 skill schema（而非全量注入 system prompt）
- **Skill review quality gate**：CI 中 `skill-reviewer` skill + `review_skill_package` tool + contracts
- **Per-user custom skill isolation**：sandbox 挂载用户级 skill
- **`allowed-tools` 逻辑修正**：只对 slash-activated 或实际 load 的 lead-agent skill 生效
- **NTFS ADS fix**：zip 成员名拒绝冒号
- **Slash activation**：每个 run 只激活一次

| 文件 | 行动 |
|------|------|
| `skill-md-and-tool-assembly.md` | 🟡 更新：加入 SkillScan、deferred discovery、review gate、allowed-tools 修正 |
| 新增 `skillscan-static-analysis.md` | ⚪ P3：SkillScan 架构、analyzer 类型、exfil 检测模式 |
| 新增 `deferred-discovery.md` | ⚪ P3：describe_skill vs legacy 全量注入 |

### 5. `concepts/subagent/` — Subagent 系统

**变化**：
- **DelegationLedger**：系统维护的委托账本，防止对同一 in-flight task 重复委托
- **Total delegation cap**：`MAX_DELEGATIONS` 限制每个 run 的总委托数
- **Step persistence**：subagent step history 持久化并显示在 thread 中
- **TokenBudgetMiddleware**：lead + subagent 共享 token 预算
- **Subagent 卡片增强**：显示 effective model 和 token usage
- **MAX_TURNS_REACHED**：turn-budget cap 新状态
- **Inherit summarization**：subagent 继承 summarization middleware

| 文件 | 行动 |
|------|------|
| `dual-threadpool-and-lifecycle.md` | 🟡 更新：添加 delegation ledger、total cap、step persistence、token budget 共享、MAX_TURNS_REACHED |

### 6. `concepts/sandbox/` — Sandbox 系统

**变化**：
- 现在有 **5 种实现**（文件名还叫 "three-impls"）：Local, AIO, BoxLite (micro-VM), E2B, Provisioner
- BoxLite 带 warm pool + benchmark-driven reclaim tuning
- E2B client lifecycle 重构
- Env scrubbing 增强（`MYSQL_PWD`, `REDISCLI_AUTH`, `*_PASS`, `PGPASSFILE`）
- Path pattern guards（segment-boundary regex for reverse path-translation, output-masking）

| 文件 | 行动 |
|------|------|
| `abstract-interface-and-five-impls.md` | 🟡 **重命名 + 更新**：改名为 `abstract-interface-and-five-impls.md`，添加 BoxLite 和 E2B，warm pool lifecycle，env scrubbing |

### 7. `operations/security/01-auth.md` — Auth 体系

**变化**：
- **OIDC/SSO**：Generic OIDC authentication with Keycloak support
- **AuthorizationProvider**：Pluggable protocol + config scaffolding (Phase 0)
- **Principal context propagation**：4 种 HTTP identity sources（browser session, OIDC, IM channel, trusted header）
- **"Keep me signed in"**：session cookie 持久化选项
- **CSRF middleware** 更新

| 文件 | 行动 |
|------|------|
| `01-auth.md` | 🟡 更新：OIDC flow、AuthorizationProvider 架构、principal identity sources |
| 可能新增 `02-authorization.md` | ⚪ P3：AuthorizationProvider protocol 详解 |

### 8. `internals/configuration/` — 配置系统

**变化**：
- Memory 段重构：`memory.backend_config.*` 替代旧的 `memory.*` flat fields
- 新增 `authz` 配置段
- 新增 `memory.mode` 字段
- Config version 可能有变化

| 文件 | 行动 |
|------|------|
| `01-config-yaml.md` | 🟡 更新：memory 段新结构、authz 段、memory.mode |
| `04-config-reference.md` | 🟡 更新：字段列表同步 |

### 9. `internals/mcp/` — MCP 增强

**变化**：
- **Routing hints**：MCP routing hints 引导模型到正确的 server
- **Auto-promote deferred MCP tools**：从 routing hints 自动提升
- **Per-server `tool_call_timeout`**：每个 MCP server 独立超时
- **Session pool singleton 生命周期同步**
- **OAuth priming**：per-server fail-soft + 持久化 rotated refresh_token
- **Cache invalidation**：基于 content digest（非 mtime）

| 文件 | 行动 |
|------|------|
| `session-pool-oauth-cache-invalidation.md` | 🟡 更新：routing hints, per-server timeout, auto-promote |

### 10. `operations/app-layer/` — Gateway API

**变化**：
- 新增 OIDC auth routes
- 新增 memory tool routes（`/memory/tools/*`）
- Monocle tracing/trace middleware
- Configurable `X-Trace-Id` header
- Goal module updates

| 文件 | 行动 |
|------|------|
| `00-overview.md` | 🟡 添加 auth routes, memory tool routes, monocle |
| `01-api-reference.md` | 🟡 添加新端点 |

### 11. `frontend/` — 前端新功能

**变化**（88 files, +6,235 / -1,098）：
- Voice dictation input
- Branching（assistant turn 分支）+ side conversations
- Citation sources evidence panel
- Workspace change review for agent runs
- Composer input polishing + prompt-history recall
- Slash-skill activation inline chips
- Per-thread composer drafts
- Real project version on About page
- "Thought for N seconds" thinking-duration chip
- Feature-gate agents UI behind `agents_api` flag

| 文件 | 行动 |
|------|------|
| `00-overview.md` | 🟡 更新功能列表 |
| `01-stream-pipeline.md` | 🟢 验证：branching 对 streaming 的影响 |
| `02-message-rendering.md` | 🟡 更新：citation panel, workspace change review, slash chips |
| `03-state-management.md` | 🟡 更新：per-thread drafts, branching state |
| `04-workspace-layout.md` | 🟡 更新：新面板 |
| `05-subagent-ui.md` | 🟢 验证 |

### 12. `operations/deployment/` — K8s 部署

**变化**：First-class Helm chart for Kubernetes deployment

| 文件 | 行动 |
|------|------|
| `02-nginx-and-k8s.md` | 🟡 添加 Helm chart 部署说明 |

### 13. `operations/tracing/` — Monocle 可观测性

**变化**：Agent observability with Monocle（替代/补充 Langfuse/LangSmith）

| 文件 | 行动 |
|------|------|
| `langsmith-langfuse-dual-provider.md` | 🟡 更新：添加 Monocle 作为第三个 provider |

### 14. `concepts/community-tools/` — 社区工具扩展

**变化**：新增 search/fetch engines——GroundRoute, Crawl4AI (`web_fetch`), fastCRW, Browserless `web_capture`, Brave `image_search`

| 文件 | 行动 |
|------|------|
| `02-web-fetch.md` | 🟡 添加 Crawl4AI, Browserless providers |
| `03-image-search.md` | 🟡 添加 Brave provider |
| `00-overview.md` | 🟡 更新 provider 列表 |

---

## 🟢 P2：需要验证（4 个领域）

### 15. `overview/` — 数字更新

| 数字 | 旧值 | 新值 | 搜索 pattern |
|------|------|------|-------------|
| Middleware 数量 | 29 | 34（+TokenBudget, +DelegationLedger, +DurableContext, +MCPRouting, +ToolOutputSynopsis） | `grep -r "29.*middleware\|middleware.*29"` |
| Sandbox 实现数 | 5 | 5（已是 5，但文件名还叫 three-impls） | `grep -r "three.*impl\|3.*impl"` |
| Memory 模式 | 1（middleware） | 2（middleware + tool） | 更新 `concepts/memory/` |

| 文件 | 行动 |
|------|------|
| `01-system-overview.md` | 🟢 更新 middleware 数量 29→34 |
| 其他 overview 文件 | 🟢 检查数字 |

### 16. `internals/agent-loop/` — 验证

| 文件 | 行动 |
|------|------|
| `00-loop-anatomy.md` | 🟢 更新中间件数量引用 |
| `03-code-trace.md` | 🟢 更新 middleware 名称和顺序 |

### 17. `testing/` — 验证

**变化**：Monocle Test Tools, skill review CI (`skill-review-ci.yml`), new tests for new middlewares

| 文件 | 行动 |
|------|------|
| `06-ci-and-automation.md` | 🟢 添加 skill review CI |
| `07-record-replay.md` | 🟢 可能需要添加 Monocle test tools |

### 18. `internals/runtime/` — 验证

**变化**：Goal continuation 修复（continuation_count double-bump bug）、manual context compaction

| 文件 | 行动 |
|------|------|
| `goal-continuation.md` | 🟢 验证 continuation_count 逻辑 |

---

## ⚪ P3：建议补充（6 个新主题）

| 子系统 | 建议文件 | 内容 |
|--------|---------|------|
| **AuthorizationProvider** | `operations/security/02-authorization.md` | Pluggable authz protocol、principal resolution、adapter pattern |
| **SkillScan 静态分析** | `concepts/skills-tools/skillscan-static-analysis.md` | Orchestrator + analyzer 架构、exfil 检测模式、安全扫描 |
| **Delegation Ledger** | `concepts/subagent/delegation-ledger.md` | 委托去重、total cap、ledger 生命周期 |
| **Memory Tool Mode** | `concepts/memory/memory-tool-mode.md` | `memory_search`/`add`/`update`/`delete` 工具、tool vs middleware 对比 |
| **Monocle 可观测性** | `operations/tracing/monocle-observability.md` | Monocle agent observability、trace-based behavioral tests |
| **Helm Chart 部署** | `operations/deployment/03-helm-chart.md` | First-class Helm chart、values 配置、ClusterIP sandbox |

---

## 执行顺序建议

1. 🔴 **concepts/memory/** — 影响面最大，breaking changes，先做
2. 🔴 **operations/security/** — 安全模型质变，4 CVE + 全链路转义
3. 🔴 **internals/middleware/** — 5 个新中间件
4. 🟡 **concepts/skills-tools/** — SkillScan + deferred discovery
5. 🟡 **concepts/subagent/** — Delegation ledger + step persistence
6. 🟡 **concepts/sandbox/** — E2B + BoxLite + 重命名
7. 🟡 **operations/security/01-auth.md** — OIDC + AuthorizationProvider
8. 🟡 **internals/configuration/** — Memory 段重构
9. 🟡 **internals/mcp/** — Routing hints + timeout
10. 🟡 **operations/app-layer/** — 新 routes
11. 🟡 **frontend/** — 新功能
12. 🟡 **operations/deployment/, operations/tracing/, concepts/community-tools/** — 补充更新
13. 🟢 验证 overview/、agent-loop/、testing/、runtime/
14. 🔢 全量 grep 数字审计
15. 🔗 交叉引用检查
16. ⚪ 新增子系统文件
17. 🚶 开发者旅程走查

预计工作量：🔴 3 文件重写 + 🟡 17 文件更新 + 🟢 6 文件验证 + ⚪ 6 新文件 = 约 32 个文件的变更。

---

## 数字一致性审计

全 digest 范围内需要统一的数字：

| 数字 | 旧值 | 新值 | 搜索 pattern |
|------|------|------|-------------|
| Middleware 数量 | 29 | 34 | `grep -r "29.*middleware\|middleware.*29" _digest/` |
| Sandbox 实现数 | 5 | 5 | 文件名 three→five |
| Memory 模式 | 1 | 2（middleware + tool） | 新增概念 |
| Auth 方式 | ~2 | +OIDC/SSO | 更新 security/ |
| Tracing provider | 2 | 3（+Monocle） | 更新 operations/tracing/ |
| Config 段数 | ~35 | ~37（+authz, +memory.backend_config 重构） | grep 验证 |

---

## 开发者旅程连贯性

```
overview/01-system-overview.md       → middleware 数字 34？sandbox 5？
concepts/memory/                     → pluggable backends, tool mode, consolidation 已说明？
concepts/sandbox/                    → 5 种实现，文件名已改？
concepts/subagent/                   → delegation ledger, step persistence 已说明？
concepts/skills-tools/               → SkillScan, deferred discovery 已说明？
internals/middleware/03-catalog.md   → 34 个完整目录
internals/middleware/02-chain-assembly.md → layered builder 已说明？
operations/security/03-guardrail.md  → 全链路 defense-in-depth
operations/security/01-auth.md       → OIDC, AuthorizationProvider
operations/tracing/                  → Monocle 已添加
operations/deployment/               → Helm chart 已添加
frontend/                            → 新功能已更新
```

---

## Part 2：质量保证 — 自洽性检查

### 交叉引用完整性

| 引用关系 | 检查点 |
|---------|--------|
| `overview/01-system-overview.md` → middleware 数量 | 改为 34 |
| `internals/agent-loop/` → middleware 数量 | 改为 34 |
| `internals/agent-loop/03-code-trace.md` → middleware 名称 | 添加 5 个新名称 |
| `concepts/sandbox/` → 文件名 | three → five |
| `operations/security/02-sandbox-isolation.md` → sandbox 数量 | 确认 5 |
| 所有 README.md 中引用 middleware 数量的地方 | grep `29` → 改为 `34` |

### 内容矛盾检测

| 旧内容断言 | 新代码现实 | 风险 |
|-----------|-----------|------|
| "Memory 是 extract→queue→persist 三阶段" | 现在是 pluggable backend + tool mode + consolidation + staleness | 🔴 旧断言不再成立 |
| "Guard 有三层" | 现在是全链路 defense-in-depth（input + output + static + framework tags + fail-closed） | 🔴 需要重写 |
| "中间件共 29 个" | 现在是 34 个 | 🔴 全 digest 散布此数字 |
| "Sandbox 有 3 种实现"（文件名） | 现在有 5 种 | 🟡 文件名要改 |
| "Skills 在 system prompt 中注入" | deferred discovery 模式下只有名字列表 + describe_skill | 🟡 补充 |
| "MCP session pool 是单例" | 需要同步生命周期 | 🟢 补充 |
| "Auth 只有 API key + OAuth" | 新增 OIDC/SSO + AuthorizationProvider | 🟡 更新 |
