---
title: "案例研究：六个真实仓库的 agent 指引文件精读"
description: "精读 openai/codex、apache/airflow、electron/electron、temporalio/sdk-java、deer-flow 等真实开源项目的 AGENTS.md / CLAUDE.md，分析各自的取舍、亮点与缺陷，附仓库链接与原文摘录。"
---

# 案例研究：六个真实仓库的 agent 指引文件精读

> 原文均于 2026-06 抓取自各仓库 main 分支。每案例：定位 → 亮点 → 缺陷/取舍。引文为原文摘录（英文保留），中文为分析。

## 案例 1：openai/codex —— "把 harness 的环境事实写给 agent"

原文：[openai/codex `AGENTS.md`](https://github.com/openai/codex/blob/main/AGENTS.md)（codex-rs 子树，~300 行）。

**定位**：Rust monorepo 的工程规范 + 测试操作手册 + review 规则三合一。

**亮点**

1. **环境限制写成代码可见事实**："You operate in a sandbox where `CODEX_SANDBOX_NETWORK_DISABLED=1` will be set whenever you use the `shell` tool… It is often used to early exit out of tests that the author knew you would not be able to run given your sandbox limitations." —— 把 agent 的沙箱约束与测试代码的早退逻辑连起来，避免 agent"修好"这些早退。这是 01 篇"软硬边界"主题的最精妙实践。
2. **明确的验证路径与升级规则**："Do not run `cargo test` directly. Use `just test`… Run the test for the specific project that was changed… Once those pass, if any changes were made in common, core, or protocol, run the complete test suite… **do ask the user before running the complete test suite**."—— 项目级测试自主跑、全量先请示：成本分级授权的范本。
3. **反熵指令**："**resist adding code to codex-core**!" 并给出替代路径（新 crate）；"Target Rust modules under 500 LoC… If a file exceeds roughly 800 LoC, add new functionality in a new module"——把"模块边界"写成 agent 可执行的数量化规则。
4. **结构化 review 规则**（`## Code Review Rules`）配"safe path"写法："Do not filter treatment comparisons on post-exposure behavior… **Safe path:** build cohorts from assignment or exposure"——不仅说禁什么，还说正确做法（Codex 官方推荐的规则格式，见[文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md)）。
5. **模型上下文本身的工程规则**："No unbounded items — everything injected in the model context must have a bounded size and a hard cap… No items larger than 10K tokens… Highlight new individual items that can cross >1k tokens as P0." —— 在指令文件里治理模型上下文自身，把 context engineering 制度化。

**缺陷/取舍**

- 体量大（数百行），远超 Claude Code 的 200 行建议；它依赖 Codex 32KiB 上限与"单层拼接"模型，对其他 harness 未必友好（如嵌套 AGENTS.md 语义下根文件过长会常驻上下文）。
- 大量 Rust 特有 lint 细节（`argument_comment_lint`、RPITIT 形态）属于"可被 CI/linter 强制的内容"，按其自家"reserve formatting for CI"原则本可下沉。

## 案例 2：apache/airflow —— "命令生成器 + 架构边界 + 安全模型"

原文：[apache/airflow `AGENTS.md`](https://github.com/apache/airflow/blob/main/AGENTS.md)（~250 行）。

**亮点**

1. **命令区块机器可再生成**：`<!-- START generated-commands … allow auto update -->` 包裹的命令清单由脚本生成——指令文件与工具链同步由代码保证，防止文档漂移。
2. **单测入口齐全**："Run a single test: `uv run --project <PROJECT> pytest path/to/test.py::TestClass::test_method -xvs`"（原则：快速子集）。
3. **架构边界可执行**："Scheduler reads serialized Dags — **never runs user code**… Workers… **never access the metadata DB directly**. Each task receives a short-lived JWT token scoped to its task instance ID." —— 架构约束写成判断句，agent review 时可逐条核对。
4. **安全模型三分法**：区分"Actual vulnerabilities / Known limitations / Deployment hardening opportunities"，让 agent 做安全 review 时不会把设计选择误报为漏洞。
5. **命名规范直击 distractor 问题**："Write **Dag** (title case) in all prose. Keep the all-caps or lowercase spelling only when reproducing a literal code token — never rewrite these, even inside fenced code blocks"，甚至教 agent 反例引法："Anti-pattern quotes that show the wrong form to teach the rule itself"。这是对 [context rot](https://www.trychroma.com/research/context-rot) 中"语义近似干扰"的针对性防御。
6. **测试标准数量化**："Target exactly 100% coverage of **what the PR changes** — no more, no less"——避免 agent 为刷覆盖率乱测无关代码。
7. **显式 Boundaries 区块**：Ask first（大重构/新依赖/破坏性迁移）与 Never（提交密钥/手改生成物/破坏性 git 操作）两档——就是 01 篇"软硬约束"的清单化。

**缺陷/取舍**

- 同样偏长；命名、newsfragment 等细则部分适合下沉到 prek hook（其中部分确实已有 hook 兜底）。
- 依赖 `breeze` 包装器（"Never run pytest, python, or airflow commands directly on the host"）——对人是护城河，但要求 agent 必须先完成 breeze 安装，setup 路径较长（好在文档化了）。

## 案例 3：electron/electron —— "安全洁癖 + 工作流剧本"

原文：[electron/electron `CLAUDE.md`](https://github.com/electron/electron/blob/main/CLAUDE.md)（~300 行）。

**亮点**

1. **开篇即安全禁令且给出机制理由**："**Never use `npx`.** It is considered dangerous because it can silently fetch and execute arbitrary packages from the registry. Always run binaries through one of these safer mechanisms instead: 1. Preferred — spawn the executable directly from `node_modules/.bin/<tool>`…" —— 禁令 + 理由 + 更安全的替代路径三件套，agent 可立即照做。
2. **补丁工作流剧本化**：Chromium patches 的方向图（`patches/{target}/*.patch → [e sync --3] → target repo commits ← [e patches] ←`）、"Fix existing patches 99% of the time rather than creating new ones"、以及 CI 失败时"先取 `update-patches.patch` artifact 再本地 sync"的捷径——把最容易让 agent 走死路的流程写成了决策树。
3. **该跑与不该跑的边界**："Build your changes… **Test your changes (Leave the user to do this, don't run these commands unless asked)**"——明确哪些验证留给人类（Electron 全量测试重），与 codex 的分级授权同构。
4. **给 agent 的 API 使用守则**：cppgc/Oilpan 一节是完整的 GC 编程规则清单（"Destructors must not access other GC managed objects…"）——领域危险区前置成文。

**缺陷/取舍**

- 内容包含大量人类 onboarding 内容（目录结构、构建工具安装），按 Claude Code `/doctor` 的修剪标准属于"agent 可推导或低频"的信息；但 Electron 构建环境过于特殊，保留可辩护。
- 独用 CLAUDE.md 而非 AGENTS.md，其他 harness 需 fallback（[agents.md FAQ 的 symlink 建议](https://agents.md/)可解）。

## 案例 4：temporalio/sdk-java —— "短即是美德"

原文：[temporalio/sdk-java `AGENTS.md`](https://github.com/temporalio/sdk-java/blob/main/AGENTS.md)（~50 行）。

**亮点**

1. **极简且完整**：仓库布局（8 个模块一句话一个）→ 公共 API 冻结（"Avoid changing public API signatures. Anything under an `internal` directory is not part of the public API"）→ 格式/测试/构建命令（含单测 pattern：`./gradlew :temporal-sdk:test --offline --tests "<package.ClassName>"`）→ PR 四问（What/Why/Breaking/Server PR）→ review checklist。约 50 行覆盖了五维框架的全部必答题。
2. **把"快"写进命令**：`--offline` 出现在每个 gradle 命令里——确定性 + 速度内嵌于文档化命令本身。

**缺陷/取舍**

- 信息密度高但缺少"为什么"（如 Java 8 基线的原因）；适合小而稳定的 SDK 仓库，大型活跃 monorepo 照抄会不够。
- 对照组价值：证明 **AGENTS.md 不必长**——评估时应检查"必答项是否齐"，而非"是否详尽"。

## 案例 5：deer-flow（本仓库）—— "定位层 + 深度层 + 薄 shim"

原文：根 [`AGENTS.md`](../../AGENTS.md)、[`CLAUDE.md`](../../CLAUDE.md)、[`backend/AGENTS.md`](../../backend/AGENTS.md)。

**亮点**

1. **自认定位层**：根文件自称 "monorepo orientation layer… For anything inside a module, read that module's guide"——正是 [agents.md 嵌套优先机制](https://agents.md/)的用法；细节全部下沉 `backend/`、`frontend/`、甚至 `backend/packages/harness/deerflow/skills/AGENTS.md`（三层嵌套）。
2. **薄 shim 兼容**：`CLAUDE.md` 仅含 `@AGENTS.md` import + 说明，并明文"Don't edit CLAUDE.md"——官方推荐的[共享写法](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools)。
3. **边界约束配测试钉子**："Any new published port needs an explicit bind address; `backend/tests/test_compose_default_bind_host.py` pins this for every service" —— 指令与测试互为印证（见 [05 篇](05-verifiability-and-test-infra.md)）。
4. **反模式即文档**：对历史踩坑显式留痕（裸 `"${PORT}:2026"` 绑 0.0.0.0 是错的、`PORT` 只是 Docker ingress、ready 失败不得谎报成功）——符合 `/doctor` 修剪标准中应保留的 "pitfalls, rationale"。

**缺陷/取舍**

- 根文件已相当长（含 scheduled-task、skill-review-waivers 等专项注记），专项内容或可再下沉到对应模块指南；随业务演进需要持续修剪（agent 指引的维护成本是真实税负）。

## 案例 6（对照）：agents.md 规范示例 —— "教科书模板"

原文：[agents.md Examples](https://agents.md/)。

规范自带的示例把推荐章节压到三节：**Dev environment tips**（"Use `pnpm dlx turbo run where <project_name>` to jump to a package instead of scanning with `ls`"——教 agent 用确定性命令替代探索）、**Testing instructions**（含 `-t "<test name>"` 子集 pattern、"Add or update tests for the code you change, even if nobody asked"）、**PR instructions**（"Always run `pnpm lint` and `pnpm test` before committing"）。对照意义：这是"最小合格答案"——真实仓库（案例 1/2）在其上叠加了规模与领域复杂度，但骨架一致。

## 横向对比

| 仓库 | 长度 | 主打机制 | 最突出的取舍 |
|------|------|----------|--------------|
| [openai/codex](https://github.com/openai/codex/blob/main/AGENTS.md) | 长 | 环境事实 + 分级测试授权 + 上下文治理规则 | 偏长，依赖 32KiB 单层模型 |
| [apache/airflow](https://github.com/apache/airflow/blob/main/AGENTS.md) | 长 | 生成式命令区 + 架构边界 + 安全三分法 + 命名反 distractor | breeze 包装器抬高 setup 门槛 |
| [electron/electron](https://github.com/electron/electron/blob/main/CLAUDE.md) | 长 | 安全禁令三件套 + 工作流决策树 + 危险区前置 | 独用 CLAUDE.md；混入人类 onboarding |
| [temporalio/sdk-java](https://github.com/temporalio/sdk-java/blob/main/AGENTS.md) | 短 | 最小合格集合（布局/API 冻结/命令/checklist） | 缺"为什么"，只适合稳定仓库 |
| [deer-flow](../../AGENTS.md) | 中 | 定位层/深度层/薄 shim 三层 + 测试钉子 | 根文件需持续修剪 |
| [agents.md 示例](https://agents.md/) | 极短 | 三节模板（tips/testing/PR） | 教科书骨架，无领域内容 |

**共性结论**：六个样本没有一个在写"请写好代码"式空话；全部把篇幅花在**命令、边界、禁令、理由**上——与 [Codex 官方规则写作建议](https://learn.chatgpt.com/docs/agent-configuration/agents-md)（"keep rules concise, explain the behavior to flag and any safe path"）完全一致。

## 延伸阅读

- 机制层面这些文件如何被消费 → [03-harness-consumption-deep-dive.md](03-harness-consumption-deep-dive.md)
- 审计清单（用这些案例做锚点）→ [07-audit-checklist.md](07-audit-checklist.md)
