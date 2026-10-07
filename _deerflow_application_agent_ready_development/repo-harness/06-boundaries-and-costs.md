# 边界与代价：这套机制不给什么

## 这页解决什么问题

搬走任何机制前先看它**没有**承诺什么。这页汇总 v2.1.0 可核验的负面事实——比正面清单更容易被误读，也更容易让应用仓付出真金白银的代价。

## 可核验的边界（全部对 v2.1.0）

**装载是 startup-only 的**。扩展 import 只发生在 Gateway 构建应用时；install/enable/disable/remove 与手改 `plugins:` 都要重启才生效（[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）。代价：没有热插拔；依赖扩展行为的应用升级流程必须包含重启步骤。

**没有插件沙箱**。扩展的构建钩子与运行时代码以 **Gateway 权限**执行；隔离包装隔离的是故障（fail-open、诊断），不是恶意（[AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)、[卷二·扩展信任边界](../sdlc-reference/10-extension-trust-boundaries.md)）。代价：面向不可信贡献者的场景需要你自己加层。

**宿主内部无兼容承诺**。`deerflow.*` 与 `app.*` 是宿主内部，扩展只能依赖 extension-api（[extensions quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/extensions/quick-start.mdx)）。代价：你 import 的每个框架都要自己声明；宿主升级可能移动内部符号。

**验证指导有代差**。v2.1.0 的示例与手册演示契约级包测试；真实装载组合（真 Loader、真 Gateway 装配后的行为证据）没有随包交付的现成模式（[示例 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md) 的测试口径即为边界）。代价：组合级证据要应用仓自建——装进 checkout、重启、观察一个宿主侧行为，是这个版本能写下的最低真实证据。

**安全响应未承诺时限**。[SECURITY.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/SECURITY.md) 只声明支持分支与报送入口，没有 SLA。代价：对安全时效有硬要求的应用仓要自己盯上游通告或承担审计。

**指南与手册是快照**。手册描述发布时行为；预算 CI 钉尺寸、示例测试钉可执行性，但内容正确性（编号、归属漂移）在门禁之外（见[指南预算与文档测试](./02-guidance-budgets-and-doc-tests.md)）。本语料的对策是钉死 tag 并登记重审触发——应用仓引用 DeerFlow 文档时同样应当钉版本。

## 应用仓的对策清单

| 边界 | 应用仓对策 |
|---|---|
| startup-only | 升级流程写明重启；变更窗口里没有"先装后看" |
| 无沙箱 | 只装可信来源；对外发布扩展时写清权限面 |
| 无内部兼容承诺 | 依赖面收敛到 extension-api + 少数显式声明的框架；升级宿主前重跑包测试 |
| 组合证据代差 | 自建安装验证＋宿主侧观察（装 → 重启 → 观察）作为发布前最后一道 |
| 无安全 SLA | 关注上游 releases；自己设置依赖升级节奏 |
| 文档是快照 | 引用文档钉版本号；升级时复核 |

## 证据入口

上列各文件（均对 tag 核验）；边界与对策的对应关系是**应用仓建议**层的归纳，不是 DeerFlow 官方指引。
