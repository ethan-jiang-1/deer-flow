# 示例扩展与公共契约

## 这页解决什么问题

应用开发者能对照抄的两类"可执行样板"：一个完整跑得通的示例包，和一套机器可读的公共契约。它们合起来回答"扩展到底能依赖什么"。

## 机制（运行时事实，对 v2.1.0 树核验）

**示例包：五种贡献维度的最小实现**。[examples/deerflow-extension-example](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md) 是独立 Python 包，覆盖五种贡献（中间件计数、task 生命周期归并、system-model 观察、Gateway 服务、eager 路由），刻意保持每件实现"deliberately small"。它示范三件事：契约级包测试怎么写（只用公共契约加自身依赖，不 import harness 与 Gateway）、安装事务长什么样（快照 → 依赖组 → lock → `plugins:` 条目 → 重启）、以及**分发自包含**（Docker 构建包含本地快照，生产容器不在网络上解析依赖）。

**extension-api：零依赖的公共契约包**。[backend/packages/extension-api/](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/extension-api/deerflow_extension_api/contracts.py) 按模块分面：`contracts`（注册与贡献类型）、`placement`（语义位置）、`assembly`（组装描述）、`auth`（principal 解析）、`provenance`（消息生产者声明）、`release` / `state` / `compaction` / `run_evidence` / `runtime_bridge`。它刻意不依赖任何框架——扩展声明自己 import 的一切，且：

> Never import `deerflow.*` or `app.*`: those are host internals with no compatibility promise.
>
> — [extensions quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/extensions/quick-start.mdx)

**contracts/：跨组件 JSON 契约**。仓库根的 [contracts/](https://github.com/bytedance/deer-flow/blob/v2.1.0/contracts/subagent_status_contract.json) 收纳跨语言/跨栈的机器可读契约：`subagent_status_contract.json`（子代理状态枚举）、`slash_skill_contract.json`（slash 技能）、`run_event_stream_contract.json`（run 事件流）、`skill_review/` 四个 schema（评审事实、报告、包快照、豁免清单）。契约消费者（前端、外部工具）对照 schema 校验，而不是解析实现。

**三者分工**：示例包回答"怎么写"，extension-api 回答"能 import 什么"，contracts/ 回答"跨组件约定什么"。误读：把示例当契约上限（示例演示五种贡献类型，契约注册面是七种——见[术语页](../application-development-model/02-terms.md)）。

## 应用仓能借鉴什么

**可移用**：① 给每种接入形态一个**跑得通的最小示例**，并让它的测试就是你想让用户抄的测试；② 公开契约与宿主内部严格分离，且对内部代码明说"无兼容承诺"——这比含糊的"内部使用"诚实；③ 跨组件约定落成 schema 文件而不是散在代码注释里。**应用仓建议**：extension 包仓最便宜的高杠杆动作是让自己的 README 达到示例包的标准：入口声明、测试口径、安装事务、信任边界四段俱全。

## 证据入口

- [示例包 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md) 与 `plugin.py`、`pyproject.toml`
- [extension-api 包](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/extension-api/deerflow_extension_api/contracts.py)（模块清单对 tag 核验）
- [contracts/ 目录](https://github.com/bytedance/deer-flow/blob/v2.1.0/contracts/subagent_status_contract.json)（七个 JSON 文件对 tag 核验）
