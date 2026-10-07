# 意图与范围对齐

## 什么时候读这里

一笔变更开始之前：意图从哪里进来、为什么要先对齐范围、DeerFlow 主仓把哪些对齐动作写成了要求。应用仓维护者读这页是为了决定自己的意图入口——不一定要照抄主仓形式，但要回答同样的问题。

## 主仓机制

**成文标准（PR 模板）**。每笔 PR 从关联 issue 开始（`Fixes #…`），并要求写清两件事：trigger（bug、需要的 feature、技术债还是生产问题）与 pain being addressed（用户可见问题或解锁了什么）。非平凡 feature 明确要求先开 issue/discussion 对齐范围：

> For non-trivial features, please open an issue/discussion first to align on scope before writing code.
>
> — [pull_request_template.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/pull_request_template.md)

**成文标准（issue 表单）**。意图入口的表单面在仓库内：[bug-report.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/ISSUE_TEMPLATE/bug-report.yml) 要求先勾选"搜索过已有 issue"（必填）与"可在最新 main 复现"，复现步骤与日志为必填；[feature-request.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/ISSUE_TEMPLATE/feature-request.yml) 的导语与 PR 模板同一立场——非平凡 feature 先开 Discussion 对齐范围再写代码；[config.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/ISSUE_TEMPLATE/config.yml) 关闭空白 issue，并把三类流量各导各的入口：使用问题→Discussions Q&A、半成形想法→Discussions ideas、安全漏洞→security policy（不开公开 issue）。

**成文标准（贡献指南）**。CONTRIBUTING 给出常规序列：建 feature 分支 → 改动 → 格式化 → 测试 → 提交 → PR（[CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md)）。

**机器门禁**：无。没有 CI 检查 PR 是否挂了 issue、是否先经过讨论——这一层靠模板引导与评审把关。

**仓库外不可核实**：表单只是引导——多少 issue/PR 真的先经过 discussion 对齐，只能从 git 历史抽查，不是制度保证。

## 为什么这条值得抄

意图入口决定后面所有环节能对齐什么。模板的措辞值得注意：它要求描述**用户视角的结果**而不是实现方案（见 [PR 表面与 AI 披露](./04-pr-surface-and-ai-disclosure.md)），这让评审可以判断外部行为而不被预先指定的函数名限制。范围对齐失败的代价在主仓用真金白银换过——大变更走 RFC/spec 分级（见 [spec 与实现计划](./02-spec-and-plan.md)），正是给"范围没对齐就写码"这个失败模式加的闸。

## 应用仓适用边界

**可移用**："先开 issue/discussion"的原则、"trigger + pain"的意图描述格式、"非平凡先对齐"的分级、issue 表单的三路分流（使用问题、想法、安全漏洞各有各的入口，漏洞不开公开 issue）。**需要自定**：你的意图载体（issue、工单、任务清单都行），但入口要能表达**用户可观察的结果**——触发条件、用户看到什么、失败时的行为、怎样算完成。

## 证据入口

- [pull_request_template.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/pull_request_template.md)（tag 与宿主分支一致）
- [CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md) Development Workflow 节
