# 扩展信任边界

## 什么时候读这里

评估"装第三方扩展/把我的扩展发给别人装"的风险时：DeerFlow v2.2.0 对扩展代码的信任假设是什么、哪些义务会传导到应用仓。这页与[卷一·新仓起步](../application-development-model/01-new-application-repository.md)的分发节互补——那里讲流程，这里讲**为什么**。

## 主仓机制

**装载是 operator 信任的代码执行，不是运行时隔离（运行时事实 + 成文标准）**。根指南写得直白：

> Restart Gateway after every mutation. Build hooks and extension code run with Gateway privileges; use only trusted operator sources.
>
> — [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md)

`plugins:` 列表刻意放在 operator 控制的 `config.yaml`、与 API 可写的 `extensions_config.json` 分离——原文给出理由 "This imports code"（[AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md)）。v2.2.0 的根指南在同一段还新增了 **extension-first evaluation** 规则：实现新功能前先评估能否以打包扩展的形式交付，只有 bug 修复与 agent loop / memory / 上下文压缩 / 认证的改动留在核心；钩子不够就"加一个通用钩子 + 一个用它的扩展"，不许把业务逻辑硬编码进核心。这意味着**扩展路径是被主仓主动推荐的分发面**——信任判断的频次只会上升，不会下降（**主仓要求**，只约束向 DeerFlow 提交的变更）。配套的来源规则（成文，[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）：远程直接引用限于 HTTPS、远程 Git 必须公共 Git-over-HTTPS、本地目录以快照装入、含内嵌凭据的来源 URL 拒收；SSH Git URL 拒收（Docker 构建器不转发主机 SSH 凭据）。用户手册 [operations 页](https://github.com/bytedance/deer-flow/blob/v2.2.0/frontend/src/content/en/harness/extensions/operations.mdx) 的 Accepted sources 表列出五种接受形式（包索引 requirement、钉定 commit 的公共 Git、HTTPS 直接引用、本地快照、回环 HTTP 带警告）——其中"版本锁定/pinned"是示例形式而非 manager 的强制规则。

**隔离的是故障，不是恶意（运行时事实）**。贡献的中间件被 `IsolatedMiddleware` 隔离包装：扩展失败发诊断并 fail open，不重复下游 model/tool 副作用——这是**故障隔离**；但它不改变"代码以 Gateway 权限执行"的事实（`agents/middlewares/skill_tool_policy_middleware.py` 一类的策略中间件在 v2.2.0 **已删除**，权限上限由 agent 组装与执行授权拥有，不是中间件在挡）。`--yes` 跳过的只是确认提示，语义是"automation that has already reviewed and trusted the source"。

**权限上限不在扩展手里（运行时事实，v2.2.0 语义变更）**。v2.1.0 曾由 `skills/tool_policy.py` 与 `SkillToolPolicyMiddleware` 在链路中过滤工具；v2.2.0 起这两者都已删除，`SKILL.md` 里的 `allowed-tools` 降级为**兼容性元数据**——原文三处一致："exported metadata only and never filters tools"（[agents 指南](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/packages/harness/deerflow/agents/AGENTS.md)）、"compatibility metadata … never restricts or grants"（[agents/lead_agent/prompt.py](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/packages/harness/deerflow/agents/lead_agent/prompt.py)）、"activation never filters, grants, or denies tools — Agent assembly/execution authorization owns the permission ceiling"（[middlewares 指南](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/packages/harness/deerflow/agents/middlewares/AGENTS.md)）。**读法**：写 `allowed-tools` 不会给你权限，也不会限制你——想在应用仓里靠它做权限收敛的，必须改用工具白名单 / tool groups / guardrails 这些实际生效的层面。

**运行时的另一道信任边界：guardrails 的 risk gate（运行时事实）**。扩展不是唯一的"外部判定者"——`config.yaml` 的 guardrails 支持网络 provider 在工具执行前判定风险：[GUARDRAILS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/docs/GUARDRAILS.md) 的 Option 4 是 TypeSafe（Jev）风险门（`model: jev-latest`、`threshold: 0.5`、`api_key_env: TYPESAFE_API_KEY`、超时与重试、状态缓存），同一页还给出"换一个端点做同一个门"的 OpenAI Decisions provider（`deerflow.guardrails.openai_decisions:OpenAIDecisionsGuardrailProvider`，`POST {base_url}/v1/decisions`，另有 `memory.prescreen` 与 `memory.signals` 两个同族 provider）。`fail_closed` 默认 `true`：provider 判定不了就拒绝，而不是放行。**读写法**：这层是"你的部署在信一个外部模型服务对你的工具调用下判断"，它与"你信扩展作者的代码"是两个独立决定，要分别评估。

**豁免只能来自 trusted base revision（机器门禁）**。公共技能审查的豁免清单按安全系统设计：每条豁免精确匹配一个当前 error finding、钉文件全量 SHA-256、带过期日期、blocker 级永不可豁免；**只有 trusted base revision 的 manifest 能压制当前 PR 的 finding**——PR head 上的清单改动只能验证、不能压制本 PR 的 finding，依赖豁免的变更需要两次合并（先落清单、再落变更）（[AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md)、[skill-review-waivers.v1.json](https://github.com/bytedance/deer-flow/blob/v2.2.0/.github/skill-review-waivers.v1.json)）。原则一句话：**任何"让我通过"的机制，都不能由被检查者当场书写**。

**Gateway run-context 信任边界（成文标准）**。server 产生的 run-context key 必须同时挡住 `body.context`（白名单合并）与自由形态 `body.config`（逐字复制）两个客户端可写入口；信任与目的地是两个独立轴（[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/AGENTS.md)）。

**边界**：[SECURITY.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/SECURITY.md) 只声明支持分支（main 承 2.x、main-1.x 承 1.x）与漏洞报送入口，**没有**响应时限或 SLA——不构成企业级漏洞响应流程的证据。扩展安全模型是来源信任（只装 trusted operator sources）+ operator 门禁，不是运行时隔离。

## 应用仓适用边界

**会传导的义务**：你 fork/部署 DeerFlow 并安装扩展时，"只装可信来源"的责任在你；你**发布**扩展给别人时，你的用户对你承担同样的信任假设——所以你的 README 应当写清你的扩展需要什么权限面（贡献类型、是否起线程、是否碰文件系统）。**可移用**："豁免只能来自可信基线"的设计适用于应用仓任何带豁免/白名单的检查（lint 豁免、依赖豁免都一样）；run-context 信任边界（两个客户端可写入口都要挡）适用于任何"服务端注入的 key 不能被客户端覆盖"的场景。**需要自建**：若应用仓面向不可信贡献者（公共技能市场类场景），需要主仓没有提供的额外隔离层——不要假设 DeerFlow 替你做了。

## 证据入口

- 根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md)（plugins 信任段、extension-first evaluation 与 skill 豁免段）与 [extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/packages/harness/deerflow/extensions/AGENTS.md)（来源规则、事务与 `IsolatedMiddleware`）
- [GUARDRAILS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/docs/GUARDRAILS.md)（TypeSafe / OpenAI Decisions 两个网络 provider 与 `fail_closed`）
- [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/AGENTS.md)（run-context trust boundary 节）、[SECURITY.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/SECURITY.md)
