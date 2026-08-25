---
title: "Digest 更新计划 #5"
description: "基于 upstream e5c62cab → 431892e1 的 108 commits 变更，逐目录规划 digest 更新内容和优先级。"
type: index
---

# Digest 更新计划 #5

> 基准：`e5c62cab` → `431892e1`（108 commits），2026-08-25
> 变更规模：601 files, +66,827 / -4,637 lines（比 #4 的 931 files 小）
> 提交构成：22 feat / 65 fix / 1 perf / 9 docs / 4 build / 3 test
> 时间跨度：2026-08-08 → 2026-08-25
> config_version：33 → **36**（config.example.yaml +244/-33，extensions_config.example.json +25）

## 一句话总结

这轮没有 #3/#4 那样的 breaking 重构，是"修修补补 + 六个方向的能力落地"：
- **MCP 持久化任务**（durable task runtime → ordinary driver → 通知 + Chat UI）完整落地，成为一等公民
- **Subagent 批量执行**（unified capacity + durable batch execution + managed subagents + delegation scopes）
- **新 provider/后端**：OpenSandbox（sandbox 第 7 实现）、Honcho（memory 第 5 后端）、RAGFlow（knowledge 检索）、MiniMax Code（ACP agent）
- **Extensions 升级**：packaged extension 管理（CLI + gateway contribution points + 5 类 contribution）
- **Tool receipts**：模型可见的确定性工具收据 ledger（RFC #4651 layer 1）
- **Threads 分支会话**（branched conversations）+ 大量 fix

## ▶ 步步为营执行清单

| 步 | 文件 | 做什么 |
|----|------|--------|
| 1 | `concepts/subagent/dual-threadpool-and-lifecycle.md` + `README.md` | 🔴 更新：subagent 批量执行（capacity + batch_runtime + batch tools）、managed subagents + delegation scopes、isolated date-only context、turn 复用 tool-call-id 隔离 |
| 2 | `internals/mcp/` | 🔴 更新+新增：durable task 子系统（task_tool_caller / tasks/ driver+ordinary+runtime / persistence+migrations / gateway router）、per-user credential injection、interceptors、OpenViking tools 集成 |
| 3 | `concepts/sandbox/abstract-interface-and-six-impls.md` | 🔴 更新+改名：6→7 实现（+OpenSandbox），sandbox:execute 授权落地（authz/outcome + sandbox_authz） |
| 4 | `concepts/memory/extract-queue-persist-pipeline.md` | 🟡 更新：4→5 后端（+Honcho），hybrid fact eviction（deermem/core/eviction.py），mem0 超时校验 |
| 5 | `concepts/community-tools/` | 🟡 更新+新增：+RAGFlow（knowledge 检索工具）、+OpenSandbox（provider 文档）、MiniMax Code ACP agent |
| 6 | `internals/harness-hooks/` + `internals/middleware/03-catalog.md` | 🟡 更新：ToolReceiptMiddleware（35→36）+ tool_transform_meta、extensions 5 类 contribution（assembly/auth/compaction/provenance/release） |
| 7 | `operations/app-layer/` + `internals/runtime/` | 🟡 更新：gateway contribution points + packaged extension 管理（CLI + manager）、新增 routers（subagents/subagent_batches/mcp_tasks）、threads 分支会话、LangGraph Studio 兼容 |
| 8 | `internals/configuration/` + `getting-started/` | 🟡 更新：config_version 33→36，新配置段（mcp_tasks/subagent_batches/verification）、memory.honcho、scheduler.recursion_limit |
| 9 | `operations/channels/` | 🟢 更新：Buzz seen-events 去重（buzz_seen_events.py）、Lark 凭据切换、Telegram/Discord/WeCom/Feishu 生命周期修复 |
| 10 | `operations/scheduler.md` | 🟢 更新：recursion_limit 可配置、busy 任务入队、多实例恢复、并发预算 |
| 11 | `frontend/` 全部文件 | 🟢 更新：68 files（分支会话树、subagent batches UI、background tasks、integrations、streamdown 修复） |
| 12 | `concepts/builtin-tools/` | 🟢 验证：batch_task_tool + background_tasks_tool 新 builtin、tool receipts、read_file 二进制 |
| 13 | ⚪ 新子系统 digest | ⚪ 新增：knowledge/RAGFlow、managed subagents、OpenSandbox（并入 sandbox/community 即可，不必单独立档） |
| 14 | 🔢 数字审计 | grep 全 digest 修复旧数字（middleware 35→36、sandbox 6→7、memory 4→5、config_version 33→36） |
| 15 | 🔗 交叉引用检查 | 确保所有链接可达 |
| 16 | 🚶 开发者旅程走查 | 模拟完整阅读路径 |

---

## 详细变更分析

### 1. Subagents — 批量执行 + 受管子代理（最大新能力）

| commit | 内容 |
|--------|------|
| `ff0a6768` | feat(subagents): unified capacity and durable batch execution (#4998) |
| `1aa813dd` | feat: managed subagents and delegation scopes (#4887) |
| `e4a7a047` | feat(subagents): isolated date-only context (#4797) |
| `88252e9b` | fix(subagents): isolate background tasks from reused tool call IDs (#4758) |

**新文件**：
- `backend/app/subagent_batches/`（service）、`gateway/routers/subagent_batches.py`、`config/subagent_batches_config.py`
- `harness/deerflow/subagents/`：`capacity.py`、`batch_runtime.py`、`batch_service.py`、`runtime.py`
- `persistence/subagent_batches/`（model+sql）、migration `0016_subagent_batches.py`
- `tools/builtins/batch_task_tool.py` + `background_tasks_tool.py`
- `persistence/managed_subagents/`（base/file/model/sql）、migration `0014_managed_subagents.py`
- `gateway/routers/subagents.py`、`config/subagent_runtime_config.py`

**要点**：subagent 从"每轮现跑"升级为支持**统一容量预算**（capacity）+ **持久化批量执行**（batch：批量任务可挂起/恢复、独立 store）；新增**受管子代理**（managed subagents，可持久化注册、作用域授权 delegation scopes）。

### 2. MCP — 持久化任务完整落地

| commit | 内容 |
|--------|------|
| `e9387394` | feat(mcp): durable task runtime foundation (#4665) |
| `47b258eb` | feat(mcp): ordinary durable task driver (#4690) |
| `5ffc2d3e` | feat(mcp): complete durable task notifications and chat UI (#4833) |
| `7e95bef2` | feat(mcp): per-user credential injection for shared MCP servers (#4868) |
| `a263af28` | feat(mcp): OpenViking tools integration (#4745) |
| `308948aa` `b36504ed` `15802c37` | 任务取消/凭据/错误修复 |

**新文件**：`app/mcp_tasks/`（errors/service）、`gateway/routers/mcp_tasks.py`、`harness/mcp/tasks/`（driver/ordinary/runtime/models）、`harness/mcp/task_tool_caller.py`、`harness/mcp/user_scoped_auth.py`、`harness/mcp/interceptors.py`、`persistence/mcp_tasks/`、migrations `0011-0013`、`config/mcp_tasks_config.py`

### 3. Sandbox — OpenSandbox + 授权

| commit | 内容 |
|--------|------|
| `917fe595` | feat(sandbox): add OpenSandbox provider (#4877) |
| `cc6a2657` | feat(authz): enforce sandbox:execute authorization at sandbox acquisition (#4063 Phase 3) (#4911) |
| `1c219b68` `336cd3ac` `38440949` `69c9a202` `5b523bc9` `30a36bd4` | E2B/MSYS/时序/上传资源修复 |

**新文件**：`community/opensandbox/`（provider/sandbox）、`authz/outcome.py`、`authz/sandbox_authz.py`、`config/verification_config.py`

### 4. Memory — Honcho 后端 + eviction

| commit | 内容 |
|--------|------|
| `6cbf20fd` | feat(memory): Honcho backend (user-model memory provider) (#4730) |
| `5ffaa09f` | feat(memory): hybrid fact eviction policy (#4789) |
| `f0276c9f` `3a967d4f` `ae099c11` | Honcho/mem0 超时与作用域修复 |

**新文件**：`agents/memory/backends/honcho/`（client/config/honcho_manager）、`deermem/core/eviction.py`

### 5. Extensions — packaged 管理 + gateway contribution points

| commit | 内容 |
|--------|------|
| `c542185a` | feat(extensions): gateway contribution points and packaged extension management (#4780) |
| `13f0a7f2` | feat(extensions): out-of-tree extension observe what the agent did (#4863) |
| `7389331e` | feat(extensions): observe task lifecycle and system model calls (#4684) |

**新文件**：`harness/extensions/`（cli/gateway/manager/notify）、`extension-api/` 新增 5 个模块（assembly/auth/compaction/provenance/release）、`examples/deerflow-extension-example/`、`scripts/check_agent_guidance.py`、`backend/AGENTS.md` 扩展指南

### 6. Tool receipts — 模型可见确定性收据

| commit | 内容 |
|--------|------|
| `4e35f0d1` | feat(harness): deterministic tool receipts with model-visible ledger (RFC #4651, layer 1) (#4659) |

**新文件**：`agents/middlewares/tool_receipt.py`、`tool_receipt_middleware.py`、`tool_transform_meta.py`、`message_utils.py`（middleware 35→36）

### 7. Threads / Gateway / Runtime

| commit | 内容 |
|--------|------|
| `943d148e` | feat(threads): distinguish branched conversations (#4983) |
| `e8410ceb` | fix(gateway): preserve exact history attribution beyond event page limits (#4953) |
| `432c09f6` `a181c339` | Studio 兼容（langgraph_studio.py + request_path.py） |
| `cff8b74e` `5d520e44` | harness/gateway 生命周期修复 |

### 8. 其他值得注意的

- **Knowledge/RAGFlow**（`431892e1`）：`community/ragflow/`（client/formatting/tools），只读 RAG 检索
- **MiniMax Code**（`062ba9dd`）：原生 ACP agent 集成
- **Scheduler**（`613b90b0` `645ca08f` `82836370` `1dd6ba1a`）：recursion_limit 可配置、busy 入队、多实例恢复、并发预算
- **Channels**（`556a1787` `74d9e6c2` `e401ae2d` `e5bf3ccf` `38ff4477` `df01102d`）：Buzz seen-events、Lark 凭据切换、生命周期修复
- **Frontend**：68 files（分支会话树、subagent batches、background tasks、model load error、streamdown sanitization）

---

## 变更→digest 映射速查

| 上游改了 | digest |
|---------|--------|
| `harness/.../subagents/` + `app/subagent_batches/` | `concepts/subagent/` |
| `harness/.../mcp/` + `app/mcp_tasks/` | `internals/mcp/` |
| `harness/.../sandbox/` + `community/opensandbox/` + `authz/` | `concepts/sandbox/`, `operations/security/` |
| `harness/.../memory/backends/honcho/` + `deermem/eviction.py` | `concepts/memory/` |
| `harness/.../community/ragflow/` + `opensandbox/` | `concepts/community-tools/` |
| `harness/.../middlewares/`（tool_receipt） | `internals/middleware/03-catalog.md`, `internals/harness-hooks/` |
| `harness/.../extensions/` + `extension-api/` | `internals/harness-hooks/`, `operations/app-layer/`, `getting-started/` |
| `app/gateway/`（routers + threads + studio） | `operations/app-layer/`, `internals/runtime/` |
| `config.example.yaml`（v36） | `internals/configuration/`, `getting-started/` |
| `app/channels/` | `operations/channels/` |
| `app/scheduler/` | `operations/scheduler.md` |
| `frontend/` | `frontend/` |
| `tools/builtins/`（batch_task_tool） | `concepts/builtin-tools/` |
