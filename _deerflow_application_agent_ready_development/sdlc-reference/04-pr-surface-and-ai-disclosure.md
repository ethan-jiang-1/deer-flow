# PR 表面与 AI 披露

## 什么时候读这里

提交变更前：PR 描述要写什么、AI 参与怎么披露、哪些自检是 DeerFlow 主仓显式要求的。这页也回答应用仓最常问的问题——"我的仓要不要 AI 披露"。

## 主仓机制

**用户视角的变更描述（成文标准）**。模板要求从用户/调用方视角描述，不是 diff 复述：

> Describe the change from a user's / caller's perspective, not as a code diff.
>
> — [pull_request_template.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/pull_request_template.md)

**Surface area 勾选（成文标准）**。逐项勾选改动面（前端 UI / 后端 API / Agents·LangGraph / Sandbox / Skills / 依赖 / 默认行为变化 / 仅文档测试 CI），评审者据此划评审范围。勾到 Agents/LangGraph 时附带一条 prompt 信任自检：新 prompt 文本里每个数据源的信任级别是什么、该走哪个通道——模型可影响的值必须走 untrusted、经清洗的数据通道，**不许插值进框架持有的 system 文本**。

**Validation 写实际运行过的命令（成文标准 + 自我声明）**。按改动面列最低检查集（backend `make lint && make test`、frontend format/lint/typecheck/build/test、改了前端还要 E2E），并要求填**实际运行**的命令与结果。

**AI 披露三项（成文标准）**。DeerFlow 自认是 AI 项目、欢迎 AI 辅助贡献，但每个 PR 必须填全三项——用了什么工具、怎么用的，并勾选：

> I've read and understand every line of this change and take responsibility for it — it's not unreviewed AI output.
>
> — [pull_request_template.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/pull_request_template.md)

CONTRIBUTING 补充执行方式：披露帮**评审者校准阅读强度**；忽略这一节的 PR "may be asked to fill it in before review"（[CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md)）。

**机器门禁**：无——PR 表单是 GitHub 模板，不填也能开 PR；约束靠评审拒绝。**仓库外不可核实**：模板要求与实际评审执行之间的差距无法从文件判定。

## 应用仓适用边界

**可移用（几乎全套，且对 AI 参与度高的应用仓尤其值）**：用户视角描述、Surface area 勾选、Validation 自报、AI 披露三项（工具、用法、人的责任确认）。这套表单的底层逻辑是**给评审者分级信任的信息**——AI 披露不是合规仪式，是让"这段代码该按什么强度读"变成显式信号。**需要自定**：勾选项按你的改动面重列（如 extension 包仓：契约面 / 宿主组合 / 配置 / 文档）；责任声明按你的团队署名规则改写。**应用仓建议**：prompt 信任自检值得原样搬——只要你的应用有 system prompt，"模型可影响的值不进框架文本"就是你的信任边界。

## 证据入口

- [pull_request_template.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/pull_request_template.md)（Why / Surface area / Bug fix verification / Validation / AI assistance 各节）
- [CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md) AI assistance disclosure 节
