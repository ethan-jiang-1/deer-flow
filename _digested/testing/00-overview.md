---
title: "测试策略全景"
description: "DeerFlow 有四层测试体系：边界测试（CI 强制执行）、Gateway 一致性测试、E2E + 单元测试、门禁与契约层。2.1 引入 Monocle Test Tools 与 skill review CI，2.2 把规模翻倍并补齐 Windows/扩展包两条 CI 车道。"
topics: [testing, ci, quality-assurance]
---

# 测试策略全景

DeerFlow 有四层测试体系：边界测试（CI 强制执行）、Gateway 一致性测试、E2E + 单元测试，以及底下的门禁与跨语言契约层。2.1 引入了 Monocle Test Tools（trace-based behavioral tests）与 skill review CI；**2.2.0 把这套体系的规模翻了一倍多**（后端测试函数 14,405 → 23,432，测试文件 738 → 1363，Playwright spec 52 → 93），并新增了两条 CI 车道：Windows live 门策略、扩展包打包检查。

## 测试金字塔

```
          ┌────────┐
          │  E2E   │  Playwright 93 spec / 384 test（mock 85 + auth 3 + 真后端 4 + 录制 1）
          │ (384)  │
          ├────────┤
          │  Gate  │  TestGatewayConformance — SDK/Gateway 格式一致性（11 方法）
          │  (11)  │
          ├────────┤
          │  Unit  │  Rstest 348 文件（node 202 / dom 146）+ pytest 23,432 个 def test
          │(23k+)  │
          ├────────┤
          │ Bound  │  test_harness_boundary.py — CI-enforced import rules（1 个 AST 扫描）
          │  (1)   │
          └────────┘
```

> **解释（口径）**：金字塔的宽度数字是 v2.2.0 实测，不是估算——后端用 `grep -c '^\s*\(async \)\?def test'` 全树统计，前端用文件名后缀分类，Playwright 用 `^\s*test(` 统计。相比 v2.1.0 页面里的 `~15 / ~11 / 100+`，量级差了两个数量级；这不是"多了两个数量级的新层"，而是旧数字用的是示意性的粗略口径。

## CI 强制边界：test_harness_boundary.py

`backend/tests/test_harness_boundary.py` — DeerFlow 最重要的测试基础设施：

### 目的

强制执行 Harness/App 两层架构的 import 边界：
- **Harness 层**（`backend/packages/harness/`）：框架代码，不依赖 App
- **App 层**（`backend/app/`）：应用代码，可以依赖 Harness

### 机制

使用 AST 分析扫描 import 语句（`backend/tests/test_harness_boundary.py:37` 单函数 `test_harness_does_not_import_app`，整个文件只有这一个断言点）：
1. `HARNESS_ROOT.rglob("*.py")` — 遍历 `backend/packages/harness/deerflow/` 下全部 Python 文件；
2. `_collect_imports()`（`:20`）解析 AST，把 `ast.Import` 与 `ast.ImportFrom` 的模块路径连同行号收集成 `(lineno, module)`；
3. 任一模块等于 `app` 或以 `app.` 开头（`BANNED_PREFIXES = ("app.",)`，`:18`）即计入 `violations`；
4. 失败消息逐条列出 `文件:行号 imports 模块`——**报错本身就带定位**，不需要人去搜。

### 豁免机制：**没有**

v2.1.0 的页面写的"通过注释标记 `# harness-boundary: allow`"这条机制**在上游并不存在**——`backend/tests/test_harness_boundary.py` 全文没有任何 marker 解析、也没有 `harness-boundary` 字样的例外处理。真实语义是**零豁免**：harness 包不得 import app，一行都不行；真需要共用的东西，正确的解法是把它下沉进 `packages/harness/`（例如 `deerflow_extension_api` 这个公共契约包）。

**解释**：这条门禁之所以敢零豁免，正是因为它约束的是一个**单向依赖**——harness 是发布出去的框架包，反向依赖 app 在语义上就是错的。零豁免让它从"可协商的规矩"变成"编译期错误般的存在"。相比之下，同样属于架构门禁的 `AGENTS.md` 尺寸预算（`04-enforcement-meta.md` §4）就必须有棘轮豁免，因为它约束的是"存量已经超了"的灰度现实。

## Gateway 一致性测试

`backend/tests/test_client.py::TestGatewayConformance` — 验证 SDK 路径和 Gateway 路径的结果格式一致（`test_client_live.py` 只有 `TestLive*` 系列的真实 API 测试，不含 conformance）：

### 测试原理

不是真的同时跑两条路径（那样要起 Gateway），而是**用 Gateway 的 Pydantic response model 解析 `DeerFlowClient` 返回的 dict**：
1. **SDK 路径：** 在 Python 进程里直接调 `DeerFlowClient` 的方法
2. **Gateway 契约：** 把返回的 dict 交给对应的 Gateway Pydantic response model 解析

字段缺失或类型不符时 Pydantic 抛 `ValidationError`，CI 因此能抓到 drift。

### 覆盖范围（v2.2.0：类在 `test_client.py:4256`，11 个测试方法）

v2.1.0 的页面说"`test_client.py:3540` 起"已经过期——类定义实际在 `:4256`，首个方法 `test_list_models` 在 `:4264`。11 个方法逐个点名它们钉住的 Gateway 面：

| 行号 | 方法 | 钉住的契约 |
|---|---|---|
| `:4264` | `test_list_models` | `GET /api/models` 的列表形状（含默认模型、provider 分组） |
| `:4285` | `test_get_model` | `GET /api/models/{name}` 单模型详情 |
| `:4304` | `test_list_skills` | `GET /api/skills` 列表 |
| `:4319` | `test_get_skill` | `GET /api/skills/{name}` 详情 |
| `:4334` | `test_install_skill` | `POST /api/skills/install` 的安装结果形状 |
| `:4356` | `test_get_mcp_config` | `GET /api/mcp/config` |
| `:4377` | `test_update_mcp_config` | `PATCH /api/mcp/config` 后的回读一致性 |
| `:4403` | `test_upload_files` | `POST /api/threads/{id}/uploads` 的返回形状 |
| `:4418` | `test_goal_methods` | v2.2.0 新增：thread goal 的读/写/清方法（对应 `contracts/thread_goal_contract.json`） |
| `:4430` | `test_get_memory_config` | `GET /api/memory/config` |
| `:4445` | `test_get_memory_status` | `GET /api/memory/status` |

底下的通用断言仍是四条：消息格式一致性（AIMessage、ToolMessage 的 content 和 metadata）、tool call arguments 一致性、streaming chunk 一致（数量、顺序、内容）、token usage 数据传递。**解释**：`test_goal_methods` 的加入说明了这个类的定位——它不是"核心聊天路径的 conformance"，而是"**每加一个 Gateway 能力，就在 SDK 侧补一条同形状断言**"的登记簿。

## E2E 测试（Playwright）

`frontend/tests/e2e/` — 基于 Playwright 的完整用户流程测试：

### 测试模式

- 使用 Playwright 的 `page.route()` 拦截 API 调用
- Mock SSE 流（模拟 LangGraph 的 stream events）
- 验证 UI 响应——消息渲染、tool call 卡片、thinking block 展开/折叠、artifact 面板

### 关键测试场景

- 发送消息 → 流式响应渲染
- Tool call 展示（web_search, read_file, bash）
- 文件上传 + artifact 预览
- Subagent dispatch + SubtaskCard 状态转换
- Dark/Light 主题切换
- i18n 切换 (en-US ↔ zh-CN)
- 🆕 2.2：scheduled tasks 工作区（`/workspace/scheduled-tasks`）的创建/编辑/队列态，v2.2.0 新增 `scheduled-fixtures.ts` 共享夹具
- 🆕 2.2：knowledge 引用源（`knowledge_sources.v1.json`）与 thread goal 流式卡片

**规模与分片（v2.2.0）**：`frontend/tests/e2e/` 85 个 spec / 369 个 `test(`；CI 在 v2.2.0 改为 **4 分片**（`--shard=${{ matrix.shard }}/4 --workers=1`），且**只有 shard 1 跑 auth 恢复路径**（`if: ${{ !cancelled() && matrix.shard == 1 }}`），报告按分片存成独立 artifact `playwright-report-<n>`。这条 `!cancelled()` 是刻意的——即使别的 shard 红了，auth 路径仍要跑完产出证据。详见 `06-ci-and-automation.md`。

## 单元测试

### Frontend (Rstest)

`frontend/tests/unit/` — 镜像 `src/` 结构：

| 区域 | 测试内容 |
|------|---------|
| `core/messages/` | `getMessageGroups()` 分组逻辑、`extractReasoningContentFromMessage()` 三源提取、`parseSubtaskResult()` 状态解析 |
| `core/threads/` | 消息合并策略、token usage 基线追踪 |
| `core/settings/` | localStorage 序列化、useSyncExternalStore 订阅 |
| `core/i18n/` | 翻译 key 覆盖率、locale 切换 |

### Backend (pytest)

`backend/tests/` — per-module 单元测试：

| 文件 | 覆盖 |
|------|------|
| `test_vllm_provider.py` | vLLM reasoning 字段提取、chat template 兼容、thinking 开关 |
| `test_patched_minimax.py` | MiniMax reasoning_split、<think> 剥离、streaming delta 拼接 |
| `test_patched_deepseek.py` | DeepSeek reasoning_content outbound 重注入、多轮保持 |
| `test_mindie_provider.py` | MindIE tool+stream 降级、XML 解析、message 格式修复 |
| `test_codex_provider.py` | Codex SSE 解析、response 合并、message 格式转换 |
| `test_patched_openai.py` | Gemini thought_signature 保留 |
| `test_claude_provider_prompt_caching.py` | prompt cache breakpoint ≤4 上限、候选位置选择 |
| `test_claude_provider_oauth_billing.py` | OAuth billing block 注入、metadata.user_id、cache_control 剥离 |

### Runner 配置

- **Frontend：** Rstest（`@rstest/core` 0.10.x，`pnpm test` → `rstest`），`rstest.config.ts` 分两个 project——`node`（202 个文件，纯逻辑）与 `dom`（146 个文件，`*.dom.test.*`，happy-dom）
- **Backend：** pytest，`pyproject.toml` 的 `[tool.pytest.ini_options]`（`:86-92`）只注册 4 个 marker，无 addopts/testpaths
- **CI：** GitHub Actions；本地 `make test` **在 v2.2.0 也变成了 `-j4` 四片并行**（`TEST_JOBS ?= 4`），不再是单进程全量

> `make test` 默认 `--ignore=tests/blocking_io`（只跑离线套件）；阻塞 IO 严格套件单独跑 `make test-blocking-io`。后端单测在 CI 里按 duration-aware 4 分片（`make test-shard` + `backend/.test_durations` 时长基线，v2.2.0 已涨到 32,395 行）；Node CI 版本 24（#5063）；skill review CI 有 waivers 机制与 v2.2.0 新增的 `skill-tests` job——详见 `06-ci-and-automation.md` 与 `test-strategy/05-speed-isolation.md` §1。
