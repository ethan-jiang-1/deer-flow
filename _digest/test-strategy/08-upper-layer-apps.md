---
title: "上层应用测试面"
description: "建在 DeerFlow 之上的东西怎么测：Python 扩展、技能、MCP 集成、IM 渠道、custom agents、下游 agent 应用——每层已有什么资产、你该怎么测。"
topics: [testing, extensions, skills, mcp, channels]
---

# 上层应用测试面

DeerFlow 是**平台**——测试面必须延伸到嫁接在它之上的东西。本仓库实际存在六类上层应用，每类的测试资产与车道不同：

| 上层应用 | 形态 | 你交付什么 |
|---|---|---|
| Python 扩展 | `config.yaml` `plugins:` 列表加载的包 | 七种贡献物：middleware / task-lifecycle / system-model observer / agent-assembly observer / context-compaction observer / Gateway service / eager router |
| 技能 | `skills/public|custom/<name>/SKILL.md` + 脚本 | prompt 资产 + 可执行脚本 |
| MCP 集成 | `extensions_config.json` 的 MCP server | 外部工具/长任务 |
| IM 渠道 | `app/channels/` | 飞书/Slack/Telegram/DingTalk/Discord/WeCom/Buzz/GitHub 桥接 |
| Custom agents | Gateway agents router + 注册表 | 预制子代理 |
| 下游 agent 应用 | import `deerflow-harness` / 内嵌 `DeerFlowClient` / 调 Gateway API | 完整应用（TUI 即参考样例） |

## 二、Python 扩展：宿主合同面 + 示例包模板

**合同事实**：`backend/packages/harness/deerflow/extensions/AGENTS.md:144` —公共包 `packages/extension-api/` 的 registry contract 暴露 **seven contribution kinds**（middleware contributors, task-lifecycle contributors, system-model-call observers, agent-assembly observers, context-compaction observers, Gateway-lifetime services, and eager routers）。Middleware 贡献要声明 lead/subagent scope、稳定顺序和**语义位置**而非脆弱的列表索引。

**宿主侧已有什么**（全部离线、进 backend-unit CI）：20 个 `test_extension_*.py` 覆盖注入/隔离/顺序/位置保证/栈装配/任务生命周期/子代理生命周期/系统模型调用/路由 principal，加 `test_extension_api_contracts|state|surface.py`（合同面本身）、`test_gateway_extension_service_lifecycle.py`（服务生命周期）、`test_extension_manager.py`（管理器事务——临时 Git 仓库、**空 hook 目录**；`extensions/AGENTS.md` 明文 "They must not run developer or CI Git hooks"）。

**你该怎么测自己的扩展**——`examples/deerflow-extension-example/` 就是官方模板：

- `tests/test_plugin.py:27` 的 **FakeRegistry**（实现全部七种注册方法的桩）验证 `install()` 注册的贡献物与路由路径；`:69` `test_install_registers_all_five_contribution_kinds` 钉住示例包声明的五类贡献物（宿主合同共七类，示例只取其五）；
- 端到端测试用 httpx **`ASGITransport`**（`tests/test_plugin.py:140`）驱动真实 FastAPI app 里的 contributed router，断言 contributed Gateway service 的生命周期状态与聚合行为；
- `tests/test_entry_point.py`：PEP 621 入口点组 `deerflow.extensions` 恰好暴露声明的 entry point 且可 load；
- 运行方式完全隔离（README 原文，`README.md:42`）："The tests use only the public contract plus this package's declared dependencies; the DeerFlow harness and Gateway application are not imported."——命令是 `uv run --no-project pytest -q`。

**已知缺口**（照抄者必须知道）：示例包测试**不进任何 CI workflow**；`extensions/AGENTS.md` 也没有明文"扩展必须带测试"——目前靠宿主侧合同测试兜底 + 示例包作为模板。

## 三、技能：一个产物，四个测试面

技能是最特殊的"上层产物"——它既是 prompt 资产（部署进沙箱给 agent 读）又是可执行代码（各技能自带的生成脚本，如 `skills/public/image-generation/scripts/generate.py`），所以测试面被拆成四层：

1. **harness 技能系统**（进 CI）：37 个 `test_skill*.py` / `test_skills*.py`——loader/parser/reload/catalog/permissions/projection/metadata 注入，含 SkillScan 静态分析器自身的单测（`test_skillscan_native.py`，其中代表性漏报被**刻意钉住不许修复**——`test_python_declared_false_negatives_stay_unreported`，漏报边界本身是契约）；
2. **生成脚本单测**（**不进 CI**，手动）：根 `tests/skills/` 5 个文件——`tests/skills/skill_loader.py` 用 `importlib.util.spec_from_file_location` 按路径加载各 `generate.py`（技能不是包），`FakeResp` 打桩 `requests`，API key 全是 dummy 字符串。测试放**仓库根而非 skill 目录**的原因是设计文档的明文要求（`docs/superpowers/specs/2026-06-08-minimax-generation-providers-design.md:144`）："测试目录：仓库根 `tests/skills/`（**不放进会部署到沙箱的 skill 目录**）"——测试代码不能进入 agent 的运行时视野；
3. **确定性质量评审**（进 CI，`skill-review-ci.yml` 阻塞 PR）：`scripts/review_changed_public_skills.py` 只评审**有变更**的技能包（git diff pathspec），subprocess 调 `python -m deerflow.skills.review.cli`（确定性 analyzer，零 LLM）；产出 facts 走 `contracts/skill_review/` 的 schema；
4. **评审器自身的 evals**：`skills/public/skill-reviewer/evals/evals.json` 6 个 fixture 用例（publish-candidate / needs-revision / blocked / prompt-injection / zh-output / partial-package），每例声明期望 readiness 与 `forbidden_tool_actions` 等硬约束。SKILL.md 的两条纪律被测试钉住（`backend/tests/test_skill_reviewer_public_skill.py:23`）："Always inspect the target through `review_skill_package`"（SKILL.md:38）、"Do not claim a higher assurance level than the evidence proves."（SKILL.md:90）——对"评审智能"这个概率性对象，也建立了确定性的评测夹具。

**Waiver 信任边界**（豁免机制按安全系统设计，根 `AGENTS.md` + `scripts/AGENTS.md`）：

- 每条豁免**精确匹配一个当前 error finding**（package/source/rule/path/line/evidence 逐字段），钉住文件全量 SHA-256（另可预批准未来的全量 hash），带过期日期；
- **blocker 级 finding 永不可豁免**（`scripts/skill_review_waivers.py:211` 第一行 `if finding.get("severity") != "error": return None`）；
- **只有 trusted base revision 的 manifest 能压制当前 PR 的 finding**（`scripts/AGENTS.md` 原文："cannot self-authorize a finding in the same pull request"）——PR head 的 manifest 会被解析校验，但不能为本 PR 自授权；依赖豁免的变更需要**两次 merge**（先落 manifest、进 trusted base，再落技能变更）；
- 被豁免的错误仍按原严重度打印在 CI 输出里——豁免是"带理由的例外"，不是"消音器"。

**反自证原则的完整落地**：任何"让我通过"的机制，都不能由被检查者当场书写。

## 四、MCP 集成：协议契约 + 恢复语义测试

`backend/packages/harness/deerflow/mcp/AGENTS.md:4` 定义协议中立的 `McpTaskDriver` 契约与 `TaskSnapshot` 状态机；投递重试、死信预算、取消围栏等恢复语义的测试盘点见 `07-durable-and-recovery.md` §三。

**值得单列的一例**（`mcp/AGENTS.md:30`）：`test_mcp_context_headers.py::test_adapter_tool_receives_the_runtime_langgraph_injects` ——"pins the injection rule against an upstream rename by disabling the ambient fallback and driving a real adapter tool through a real graph"。凡"我们假设了上游框架行为"的边界，用真组件过真图钉住，mock 掉它就等于把假设变成不可检验的。

**你该怎么测自己的 MCP server**：配置面测试用 `backend/tests/test_mcp_task_runtime_config.py` / `test_mcp_task_toolset_config.py` 做模板；长任务行为用 FakeDriver 模式模拟远端状态机迁移；真实 server 的连通验证留给手动/`integration` 车道。

## 五、IM 渠道：全离线打桩的三种范式

渠道测试全部离线：`test_channels.py`（11167 行 / 352 个测试，全仓最大测试文件）、`test_dingtalk_channel.py`（120 测试）、`test_buzz_channel.py`（99 测试）。

- **mock 消息对象**（DingTalk）：`unittest.mock.AsyncMock/MagicMock` 构造 mock 消息，进程内 `MessageBus`，每例新开 event loop；
- **真实密码学 + 假网络**（Buzz/Nostr）：`pytest.importorskip("coincurve")`（可选依赖缺失自动跳过），fixture 用**真实密钥对签名事件**（`test_buzz_channel.py:26` 注释原文："every fixture author is now a real keypair whose events are signed"），relay URL 是假的 `wss://buzz.example.com`（`:42`）——签名语义是真的（替身不可替换被测语义），网络是假的（贵的与不确定的被替身替换）；
- **桩基类**（连接绑定）：`_StubChannel`（`backend/tests/test_additional_channel_connections.py:13`）只为测基类 helper。

渠道的阻塞 IO 另有独立锚点（`backend/tests/blocking_io/test_channel_outbound_files.py`，docstring："Feishu, Telegram, and WeCom send attachments from async channel handlers…"），由 `backend-blocking-io-tests.yml` hard-fail 执行——外发附件的 open/read/hash 必须离开事件循环。

## 六、Custom agents 与跨栈契约

- Custom agent 的注册表/路由/display_name 有专门测试（`backend/tests/test_agent_display_name.py` 对控制字符做参数化拒绝，display_name 预算按 code point 而非 UTF-16 单元计算）；
- **跨语言契约双端钉住**：三份契约 JSON 每份都有后端 pytest 与前端 rstest 各读一次——表与机制见 `03-contract-e2e.md` §1。

## 七、下游 agent 应用：三层金字塔与参考样例

消费 DeerFlow 有三种姿势，官方用同一个 client 的三层测试文件把它们钉成金字塔（`backend/tests/test_client_e2e.py:1` docstring 原文）：

> "Top:    test_client_live.py  — real LLM, needs API key
>  Middle: test_client_e2e.py   — real LLM + real modules  ← THIS FILE
>  Bottom: test_client.py       — unit tests, mock everything"

> "Core principle: use the real LLM from config.yaml, let config, middleware chain, tool registration, file I/O, and event serialization all run for real. Only DEER_FLOW_HOME is redirected to tmp_path for filesystem isolation."

- **底层**（`test_client.py`，189 个测试，进 CI）：全打桩 + `TestGatewayConformance`——把 `DeerFlowClient` 返回的 dict 交给 Gateway 对应 Pydantic 模型解析，缺字段即 `ValidationError`（SDK 路径 ↔ Gateway 契约对齐，不起真进程）；
- **中层**（`test_client_e2e.py`，43 个测试，真模块 + 真 LLM）：`requires_llm` skipif 门在 CI/无 key 时跳过——**文件管理子集不需要 LLM，CI 里也真跑**；
- **顶层**（`test_client_live.py`，19 个测试，live 三重门）：可产生 API 费用与本地沙箱副作用。

**TUI 是"下游应用"的参考样例**：它是 `DeerFlowClient` 之上的 UI shell，不 fork agent 行为（同一 config、同一 `DEER_FLOW_HOME`、同一 checkpointer），16 个 `test_tui_*.py` 全部进 backend-unit CI（pyproject 里 textual 的注释原文："kept in the dev group so the terminal workbench can be run and tested locally / in CI"）。**你基于 harness 包或 client 构建自己的 agent 应用时，TUI 的测试分档（纯层直接单测 + pilot 测 App 层 + persistence round-trip）就是官方背书的模板**，拆解见 `06-frontend-and-tui.md` §三；更实操的模式集（FakeToolCallingModel、interrupt_before 轨迹截停、prompt 注入断言、middleware 测试模板）见 `_digest/testing/04-agent-test-patterns.md` 与 `_digest/testing/05-testing-skills-and-workflows.md`。

## 八、上层应用测试资产总表（硬事实）

| 层 | 测试资产 | 离线/在线 | 门禁位置 |
|---|---|---|---|
| Python 扩展（宿主合同面） | `test_extension_*.py` 20 文件 + `test_gateway_extension_service_lifecycle.py` | 离线（FakeRegistry/FakeRuntime） | backend-unit（4 分片） |
| 示例扩展包 | `examples/deerflow-extension-example/tests/`（FakeRegistry + ASGITransport） | 离线 | **无 CI（手动）** |
| 技能系统（harness） | `test_skill*` 37 文件 | 离线 | backend-unit |
| 技能生成脚本 | 根 `tests/skills/`（importlib + FakeResp） | 离线（dummy key） | **无 CI（手动）** |
| 技能质量评审 + waiver | `review_changed_public_skills.py` + `skill_review_waivers.py` + manifest | 离线（确定性 analyzer） | skill-review-ci（阻塞；blocker 不可豁免） |
| 评审器自身 | `test_skill_reviewer_public_skill.py` + evals manifest 6 fixture | 离线 | backend-unit |
| MCP 工具/会话/凭证 | `test_mcp_*` 文件群（含 1 例真 adapter 过真图） | 离线 | backend-unit |
| MCP 长任务 | `test_mcp_task_service.py` 36 async 例 + 12 外围文件 | 离线（Fake 驱动） | backend-unit |
| IM 渠道 | `test_*channel*` 文件群（channels 352 / DingTalk 120 / Buzz 99 例） | 离线（mock/真密钥假 relay） | backend-unit |
| 渠道阻塞 IO | `blocking_io/test_channel_*.py` | 离线（Blockbuster） | backend-blocking-io（hard-fail） |
| DeerFlowClient | `test_client.py` 189 例（含 Pydantic 合同） | 离线 | backend-unit |
| DeerFlowClient e2e/live | `test_client_e2e.py` 43 例 / `test_client_live.py` 19 例 | 混合 / 在线 | 文件管理子集进 CI；live 手动 |
| SSE 跨栈契约 | `test_replay_golden.py` + e2e-real-backend 4 spec | 离线（无 key 无网络） | replay-e2e（双侧触发） |
| 跨语言契约 JSON | 三份 contracts + 双端测试 | 离线 | backend-unit + frontend-unit |
| TUI | 16 个 `test_tui_*.py` | 离线 | backend-unit |
| 沙箱真镜像 | `test_aio_sandbox_local_backend.py`（`-m live`，`repo@sha256`） | 在线（真 Docker） | sandbox-image-smoke（paths 触发） |
| 真服务集成 | `@pytest.mark.integration`（Redis/Postgres） | 在线（CI service 容器） | backend-unit（显式 env 注入防静默跳过） |

## 九、给上层应用开发者的落道建议

| 你在建的东西 | 必写的测试 | 车道 |
|---|---|---|
| 一个 middleware/observer/service/router 扩展 | FakeRegistry 注册断言 + ASGITransport 端到端（照抄 example 包）+ 语义位置声明 | 独立 pytest（目前无 CI，建议自带并文档化运行命令） |
| 一个 public 技能 | SkillScan 零 finding（或合规 waiver 两段合并）+ 生成脚本打桩单测（放仓库根 `tests/skills/`，不放技能目录） | skill-review CI 会阻塞你；脚本测试手动跑 |
| 一个 MCP server 接入 | 配置面测试 + FakeDriver 状态迁移 + 长 URL/大 payload 边界 | backend-unit |
| 一个新 IM 渠道 | mock 消息对象 + 进程内 MessageBus + 渠道文件 IO 的 blocking-io anchor | backend-unit + blocking-io |
| 一个下游 agent 应用（harness/client） | 三层金字塔：全打桩单测（含 Gateway Conformance）→ 真模块 e2e（requires_llm 门）→ live 冒烟（三重门） | 自带 CI，live 部分手动 |
| 改前后端共享的协议 | contracts JSON 双端钉 + replay golden 重生成（`DEERFLOW_WRITE_GOLDEN=1`）+ e2e-real-backend | replay-e2e 双侧触发 |

**两条铁律贯穿所有上层**：① 你的测试不得进入 agent 的运行时视野（测试代码不部署进沙箱/技能目录——`tests/skills/` 放仓库根即为此）；② 你的产物质量门禁不得自我授权（waiver 只认 trusted base）。
