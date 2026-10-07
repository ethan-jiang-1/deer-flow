# DeerFlow 的设计理念：让智能体完成可交付的任务

## 核心结论

DeerFlow 不是只负责回答问题的研究代理，而是围绕任务执行组织起来的 super agent harness：模型决定下一步做什么，运行时为它提供工具、上下文和执行环境，并在交接、压缩、权限、资源与交付边界上施加约束。README 将方向概括为从 deep research 扩展到通用任务执行，并列出文件系统、记忆、技能、沙箱执行、规划与子代理等能力。（`../../README.md:939-949`）

只从运行时读这个仓库会漏掉另一半。DeerFlow 的理念实际上在**两个循环**里同时生效：一是运行时如何治理一次 agent run（模型决策与系统约束如何分工），二是仓库自己如何被研发、验证、评审、发布和运维（规矩如何变成可执行资产）。两个循环共用同一条元原则——**声明、执行、证据分开，证据高于状态灯**——前者用于 agent run，后者用于工程师和参与开发的 agent 的 change。

从当前实现归纳，这套取向可以概括为：**让模型保留处理开放问题的灵活性，同时把关键的执行边界、状态边界和可验证条件交给明确的运行时机制；研发侧则把能机器执行的纪律物化成 CI 门禁与契约测试，不能机器执行的保持诚实标注。**这是一组从代码和一手文档抽取的设计原则，不是项目声明过的官方口号。

## 运行时：五个相互支撑的原则

1. **面向行动和产物，而不止于生成回答。** Agent loop 在模型回答中包含工具调用时执行工具并继续，在没有工具调用时结束；沙箱文件、工具、子代理和可呈现产物让任务能够越过纯文本问答。（`../../_digest/overview/01-system-overview.md:19-45`） 对文件交付，`present_files` 将可见产物限定在当前线程的 outputs 目录，而不是把任意路径都当作已交付。（`../../backend/packages/harness/deerflow/tools/builtins/present_file_tool.py:33-80`）

2. **模型负责适应，运行时负责边界。** 模型可以选择工具和后续步骤；工具装配、中间件、能力授权、子代理并发/总量、循环检测、澄清中断、沙箱和文件边界则由运行时层控制。用户输入和远程内容也被视作不可信数据来处理。关键不是把每个任务写成预设流程，而是令开放式决策处于可配置、可拦截、可恢复的执行框架内。（`../../backend/packages/harness/deerflow/agents/lead_agent/agent.py:1190-1245`） [中间件链说明](../../backend/packages/harness/deerflow/agents/middlewares/AGENTS.md)

3. **直接路径优先，委派须有净收益。** 子代理不是复杂任务的默认答案。提示词要求先比较专业能力、上下文隔离或独立并行所带来的收益，与启动、重复发现、协调合成、状态冲突及副作用成本；并行任务须互相独立，随后每一批都要重新评估。（`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:425-449`） （`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:703-733`）

4. **上下文、知识和状态按用途分层。** Skill 支持先发现、按需载入；会话摘要和任务连续性处理线程内长期工作，memory 面向跨轮次持久信息，而不是把任务临时状态都变成用户画像。（`../../_digest/concepts/skills-tools/skill-md-and-tool-assembly.md:54-115`） （`../../_digest/internals/runtime/task-continuity.md:9-37`） Durable context 将框架权威规则与摘要、委派结果、技能引用等历史数据分开注入；后者明确是数据而非指令。（`../../backend/packages/harness/deerflow/agents/middlewares/durable_context_middleware.py:34-43`）

5. **完成状态和证据强度分开。** 执行结束不等于验收通过；工具回执证明调用发生，不证明论断正确；`UNVERIFIED` 表示证据缺失，不表示条件失败。可程序判定的条件由代码检查；不可判定的标准必须保持未验证。（`../../backend/packages/harness/deerflow/subagents/acceptance_checks.py:1-53`） （`../../backend/packages/harness/deerflow/tools/builtins/task_tool.py:715-733`）

## 研发侧：规矩变成可执行资产

作为企业应用框架，仓库对"自己如何被开发"同样有一套可从一手材料核实的理念，完整走查见[研发流程走查](rd-lifecycle.md)：

1. **声明的标准与机器执行的门禁严格分层。** TDD、文档同步、AI 披露写在 AGENTS.md 和 PR 模板里（成文标准）；lint、四分片单测、blocking-I/O 门、前后端契约回放 E2E 是 workflow 里真的会挡住合并的检查（机器门禁）；而 reviewer 批准、分支保护在仓库文件里不可见，不做断言。（`../../backend/AGENTS.md:243-256`） （`../../.github/pull_request_template.md:45-62`）

2. **大变更设计先行，决策产权唯一。** spec 自称 source of truth 并钉住 revision；实现计划明确"只排序文件与验证，不拥有设计决策"，偏离要进 deviation register；设计文档自带测试策略、文档更新清单和评审检查单。（`../../docs/superpowers/plans/2026-09-13-projects-mvp-phase2-implementation-plan.md:1-18`） （`../../docs/superpowers/specs/2026-07-01-scheduled-tasks-mvp-design.md:515-584`）

3. **架构、文档、工具链也是被测契约。** harness→app 的 import 防火墙是 AST 测试；AGENTS.md 有尺寸预算 CI；文档里的代码示例被测试直接 `exec()`；连 CI 里的 uv 版本都被测试钉住四个位置一致。（`../../backend/tests/test_harness_boundary.py`） （`../../.github/workflows/lint-check.yml:13-39,54-55`）

4. **发布门强于日常门。** 发版 tag 驱动，版本号四处一致由 verify 门卡住全部镜像与 chart 发布；数据演进走只追加的迁移链，Gateway 启动自动升级、未知状态拒绝启动，离线恢复是审计过的例外而非常规。（`../../RELEASING.md:3-24`） （`../../.github/workflows/container.yaml:3-16`） （`../../backend/packages/harness/deerflow/persistence/migrations/AGENTS.md:5,7-16`）

5. **失败回写成机制，学习发生在仓库。** 迁移插队事故变成修复 migration 加回归测试；工具链漂移风险变成 pin 测试；文档膨胀变成预算 CI。评审哲学的原文是 "Evidence over a green check. CI status is a signal, not a verdict."——与运行时"回执不等于论断正确"同构。（`../../docs/agents/maintainer-orchestrator-design.md:38-45`）

6. **扩展边界按 operator 信任设计，不伪装沙箱。** `plugins:` 刻意放在 operator 控制的配置而非 API 可写文件里；extension 代码以 Gateway 权限执行，文档直说只允许可信来源。（`../../AGENTS.md:75-84`）

## 它不等于什么

- **不是每种协作都等同于同一个计划图。** 项目的核心 agent loop 是模型调用—工具执行循环；goal 续跑、普通委派和持久 batch 等能力有各自的触发条件、状态和完成语义。（`../../_digest/overview/01-system-overview.md:19-63`） （`../../_digest/internals/runtime/goal-continuation.md:9-41`） （`../../_digest/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md:20-40`）
- **不是记忆越多越好。** Skill、对话摘要、线程内 task continuity、跨会话 memory 解决不同问题，有不同作用域、保留方式和可信度；任务笔记或摘要不能作为"操作已成功"的证据。（`../../_digest/internals/runtime/task-continuity.md:25-37`）
- **不是成功状态天然代表业务完成。** "已接受""已执行""下一轮模型可见""资源已释放""业务目标满足"是不同阶段；不同原语的持久化和恢复语义也不同。（`../../_digest/orchestration-ladder/01-完成语义与崩溃窗口-接受可见静止处置.md:11-40`）
- **不是 Harness 与 Gateway 混为一层。** Harness 包含可嵌入的 agent 运行能力；应用层负责 Gateway、HTTP/身份和 IM 等接入。依赖方向是 app 使用 harness，反向导入由测试禁止。（`../../_digest/overview/02-harness-app-boundary.md:11-61`）
- **不是所有成文标准都等于门禁。** TDD 的 red-on-main 靠 PR 自报，CI 只验证最终绿；draft PR 会跳过主要测试 job；blocking-I/O、E2E、replay E2E 按路径分流触发。"要求写了"与"机器挡了"必须分开读。（`../../.github/pull_request_template.md:45-53`） （`../../.github/workflows/backend-blocking-io-tests.yml:3-13`）
- **不是插件即沙箱。** 模块隔离是 import 边界；extension 代码与 build hooks 以 Gateway 权限执行，真正的控制面是 operator 信任与来源约束。（`../../AGENTS.md:75-84`）

## 实践中的设计判断

面对一个新能力，可以依次问：它属于模型应作出的任务决策，还是必须由运行时强制执行的规则？它的状态是当前请求、线程连续性、跨会话记忆，还是应用层持久任务？完成条件里哪些可由程序检查，哪些只能报告为未验证？如果需要委派，是否存在明确的专业、隔离或并行净收益，且输入输出和副作用所有权是否清晰？

在仓库一侧存在镜像的问题：这条规矩能变成 CI 门禁或契约测试吗？不能的话，它是成文标准还是文化惯例？它的例外（路径过滤、draft 跳过、仓库外配置）写清楚了吗？出过事故的话，回写成了机制还是只留在记忆里？

这些问题不是新增的规范清单，而是把现有代码中的职责边界转成可复用的推理方法。如何把一次任务沿这些边界走到交付，可看[任务交付路径](task-delivery-walkthrough.md)；仓库自己如何沿这条原则被开发与发布，可看[研发流程走查](rd-lifecycle.md)。

## 相关研究与源码

- [_digest/overview/07-design-philosophy-evidence.md](../../_digest/overview/07-design-philosophy-evidence.md)：本题的一手证据索引与解释边界（运行时第 1-6 节、研发流程与质量治理第 7-9 节）。
- [_digest/overview/01-system-overview.md](../../_digest/overview/01-system-overview.md)：Agent loop 与服务分层。
- [_digest/overview/02-harness-app-boundary.md](../../_digest/overview/02-harness-app-boundary.md)：Harness / App 依赖边界。
- [_digest/harness-engineering/01-agent-docs-system.md](../../_digest/harness-engineering/01-agent-docs-system.md)：AGENTS.md 治理体系（预算 CI、文档测试、编号漂移案例）。
- [_digest/harness-engineering/03-feedback-loops.md](../../_digest/harness-engineering/03-feedback-loops.md)：反馈三环——失败如何变成标记、落账与仓库级学习。
- [_digest/test-strategy/04-enforcement-meta.md](../../_digest/test-strategy/04-enforcement-meta.md)：架构即测试与元治理（注意其部分绝对化措辞需按 workflow 实况校正）。
- （`../../backend/packages/harness/deerflow/agents/lead_agent/prompt.py:425-523`）、（`../../backend/packages/harness/deerflow/subagents/acceptance_checks.py:1-53`）、（`../../backend/packages/harness/deerflow/agents/middlewares/durable_context_middleware.py:34-43`）：委派、验收和上下文信任边界。
