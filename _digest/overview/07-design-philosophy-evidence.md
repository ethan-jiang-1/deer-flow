---
title: "DeerFlow 设计理念：当前仓库的一手证据"
description: "从产品定位、执行治理、上下文分层与完成证据，理解 DeerFlow 的工程取舍。"
type: research
---

# DeerFlow 设计理念：当前仓库的一手证据

> **研究基线**：当前 git HEAD 为 `f31aefce993249ffbcf66deb156e5d716ec55669`。本文研究该修订对应的仓库实现，不把研究分支上的新增机制自动归为官方上游宣言。只采用仓库一方 README、模块指南与源码；不借现有 digest 的解释替代一手证据。本文是结论的证据底稿，不是使用问答。
>
> **证据分层**：**明确主张**指 README 的产品定位或工程指南写明的原则；**实现归纳**指从当前代码组合推得的设计取舍；**边界**指当前机制不能证明、不能恢复或依赖配置的部分。引用均相对于本文位置，附行号。

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

## 7. 结论与易误读边界

1. **执行基础设施，不是固定研究流水线。** 定位依据 README，组合依据 factory；通用能力不等于无限权限或成功保证。（`../../README.md:939-947`） （`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:1239-1245`）
2. **自治与治理并存。** 模型选路径和估算委派收益；工具激活策略与续轮准入独立管理。自然语言规则不等于确定性收益优化或硬安全隔离。（`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:477-503`） （`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:588-599`）
3. **连续性分层。** skill、summary、memory、文件各有职责；有 durable projection 不等于 one-shot 子执行可恢复。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:601-654`） （`../../backend/packages/harness/deerflow/subagents/executor.py:1007-1014`）
4. **不给证据过度授权。** execution ended、condition holds、receipt resolved 分别证明不同事实；缺证据应保留不确定性，不冒充通过，也不等同失败。（`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:703-733`）
5. **窄接口与可执行契约不意味着不可信插件隔离。** 单向 import、policy snapshot 和模型可见测试可以检查，插件权限仍按 operator 信任边界理解。（`../../backend/tests/test_harness_boundary.py:18-46`） （`../../backend/packages/extension-api/deerflow_extension_api/contracts.py:31-37`） （`../../AGENTS.md:75-84`）
