# 扩展信任边界

## 什么时候读这里

评估"装第三方扩展/把我的扩展发给别人装"的风险时：DeerFlow v2.1.0 对扩展代码的信任假设是什么、哪些义务会传导到应用仓。这页与[新仓起步](../application-development-model/01-new-application-repository.md)的分发节互补——那里讲流程，这里讲**为什么**。

## 主仓机制

**装载是 operator 信任的代码执行，不是插件沙箱（运行时事实 + 成文标准）**。根指南写得直白：

> Every mutation requires a Gateway restart, and both build hooks and extension code execute with Gateway privileges, so only trusted operator sources belong in this path.
>
> — [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)

`plugins:` 列表刻意放在 operator 控制的 `config.yaml`、与 API 可写的 `extensions_config.json` 分离——因为那个列表会导致**代码被 import**（[AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)）。配套的来源规则：PyPI 版本锁定 requirement、钉定的公开 HTTPS Git URL、本地目录快照；SSH Git URL 拒收（Docker 构建器不转发主机 SSH 凭据）；含内嵌凭据的来源 URL 拒收（[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）。

**隔离的是故障，不是恶意（运行时事实）**。贡献的中间件被隔离包装：扩展失败发诊断并 fail-open，不重复下游副作用——这是**故障隔离**；但它不改变"代码以 Gateway 权限执行"的事实。`--yes` 跳过的只是确认提示，语义是"automation that has already reviewed and trusted the source"。

**豁免不能自授权（机器门禁）**。公共技能审查的豁免清单按安全系统设计：每条豁免精确匹配一个当前 error finding、钉文件全量 SHA-256、带过期日期、blocker 级永不可豁免；**只有 trusted base revision 的 manifest 能压制当前 PR 的 finding**——PR head 的清单不能为本 PR 自授权，依赖豁免的变更需要两次合并（先落清单、再落变更）（[AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)、[skill-review-waivers.v1.json](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/skill-review-waivers.v1.json)）。原则一句话：**任何"让我通过"的机制，都不能由被检查者当场书写**。

**运行时上下文的双入口信任边界（成文标准）**。server 产生的 run-context key 必须同时挡住 `body.context`（白名单合并）与自由形态 `body.config`（逐字复制）两个客户端可写入口；信任与目的地是两个独立轴（[backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)）。

**边界**：[SECURITY.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/SECURITY.md) 只声明支持分支（main 承 2.x、main-1.x 承 1.x）与漏洞报送入口，**没有**响应时限或 SLA——不构成企业级漏洞响应流程的证据。扩展安全模型是供应链信任 + operator 门禁，不是运行时隔离。

## 应用仓适用边界

**会传导的义务**：你 fork/部署 DeerFlow 并安装扩展时，"只装可信来源"的责任在你；你**发布**扩展给别人时，你的用户对你承担同样的信任假设——所以你的 README 应当写清你的扩展需要什么权限面（贡献类型、是否起线程、是否碰文件系统）。**可移用**："反自授权"豁免设计适用于应用仓任何带豁免/白名单的检查（lint 豁免、依赖豁免都一样）；双入口信任边界适用于任何"服务端注入的 key 不能被客户端覆盖"的场景。**需要自建**：若应用仓面向不可信贡献者（公共技能市场类场景），需要主仓没有提供的额外隔离层——不要假设 DeerFlow 替你做了。

## 证据入口

- 根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)（plugins 信任段与 skill 豁免段）与 [extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)（来源规则与事务）
- [backend/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/AGENTS.md)（run-context trust boundary 节）、[SECURITY.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/SECURITY.md)
