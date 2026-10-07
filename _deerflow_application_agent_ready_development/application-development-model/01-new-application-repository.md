# 新仓起步：从空应用仓到第一次可验证的变更

## 这页解决什么问题

你刚建了一个独立应用仓，打算构建在 DeerFlow 上。第一个决定不是"写什么代码"，而是**选哪种接入形态**——它决定了入口、依赖、分发方式、验证路径和信任边界。本页按 v2.1.0 的实际机制把四种形态的最小入口、安装验证与四层决定讲清楚。

本页区分四类陈述：**运行时事实**对 v2.1.0 可核验；**主仓要求**只约束向 DeerFlow 主仓提交的变更；**应用仓建议**是本语料归纳；**仓库自定**由应用仓自己决定。

## 第一步：选择接入形态

| 形态 | 适合什么 | 入口 | 用户拿到什么 |
|---|---|---|---|
| **内嵌 harness** | 把 agent 嵌进你自己的后端/API/自动化系统 | `create_deerflow_agent()` 或 `DeerFlowClient` | 你的应用本身 |
| **extension 包** | 给一个已部署的 DeerFlow 实例贡献运行时能力（中间件、观察者、服务、路由） | PEP 621 入口点 `deerflow.extensions` | 经 extension manager 安装的包 |
| **skill** | 教 agent 做某类工作的方法与资料，不改运行时 | `SKILL.md` 能力包 | 技能目录（内置公共技能或用户自建） |
| **MCP server** | 接入外部工具，不写 Python | `extensions_config.json` 的 `mcpServers` 配置 | 配置声明的外部工具面 |

四者不互斥：一个应用可以同时内嵌 harness 并贡献 skill。选择的依据是"你要改变的是宿主进程的组合、模型的行为方法，还是只是工具面"。

## 四种形态的最小入口

### 内嵌 harness：从 factory 或 client 开始

最快的理解路径是直接用代码创建 agent：

```python
from deerflow.agents import create_deerflow_agent
agent = create_deerflow_agent(model)
```

`create_deerflow_agent()` 返回带 DeerFlow 默认中间件链的编译后 LangGraph agent，可继续传 `tools`、`system_prompt`、`features`、`extra_middleware`、`plan_mode`、`checkpointer` 定制（[harness quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/quick-start.mdx)）。

要线程式会话、模型/技能/记忆管理、文件上传等更完整的嵌入接口时，改用 `DeerFlowClient`：

```python
from deerflow.client import DeerFlowClient
from deerflow.config import load_config

load_config()  # 读 config.yaml 或 DEER_FLOW_CONFIG_PATH
client = DeerFlowClient()
```

> The client is thread-safe and designed to be instantiated once and reused across requests.
>
> — [integration-guide](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/integration-guide.mdx)

**运行时事实**：client 提供 `astream`/`ainvoke`、按 `thread_id` 隔离会话、可按 `agent_name` 切换命名 agent 配置；嵌入别的进程时用 `DEER_FLOW_CONFIG_PATH` 或 `load_config(config_path=…)` 显式指定配置路径；也可以直接组合底层 LangGraph 图（`make_lead_agent`）或把 Gateway 挂载为子应用——这些模式都在 [integration-guide](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/integration-guide.mdx) 有可抄的代码。**应用仓建议**：内嵌形态下你的仓就是治理主体——线程隔离、checkpoint 持久化和配置路径都由你的应用决定，不要指望 DeerFlow 替你管理部署。

### extension 包：一个正常的 Python 包，建在 checkout 之外

> An extension is a normal Python package. Create it **outside** the DeerFlow checkout.
>
> — [extensions quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/extensions/quick-start.mdx)

`pyproject.toml` 三件事：声明契约版本区间（`deerflow-extension-api>=0.2,<0.3`）、声明你 import 的每一个框架（契约包刻意零依赖）、声明**恰好一个** `deerflow.extensions` 组的入口点。入口点名（如 `hello`）就是 `enable`/`disable`/`remove` 接受的 operator 面向名。完整可抄的 `hello` 示例（计耗时并告警的中间件）在 [extensions quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/extensions/quick-start.mdx)；覆盖全部贡献维度的独立示例包在 [examples/deerflow-extension-example](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md)。

> Never import `deerflow.*` or `app.*`: those are host internals with no compatibility promise.
>
> — [extensions quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/extensions/quick-start.mdx)

**运行时事实**：契约注册面暴露**七种**贡献类型——middleware、task-lifecycle、system-model-call 观察、agent-assembly 观察、context-compaction 观察、Gateway-lifetime 服务与 eager 路由（[extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)）；示例包演示其中五种。中间件贡献声明 lead/subagent 作用域、稳定顺序与语义 placement（如 `MODEL_LOGICAL`、`TOOL_VISIBLE`），而不是脆弱的列表下标。前置条件：Python 3.12+、uv 0.8.0+（manager 拒绝更旧的 uv）。

**主仓要求（不随使用继承）**：装扩展是 operator 动作，不是 web UI 能做的；需要跑 Gateway 的机器的 shell 权限。

### skill：一个目录加一份权威 SKILL.md

每个 skill 是 `skills/public/`（随仓提交）或 `skills/custom/`（用户自建）下的子目录；`SKILL.md` 是权威定义，由 `skills/parser.py` 解析出名称、描述、分类、指令与工具依赖（[skills 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/skills.mdx)）。

> Skills are loaded on demand — they inject their content when a task calls for them and stay out of the context otherwise.
>
> — [skills 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/skills.mdx)

**应用仓建议**：skill 适合承载"怎么做某类工作"的方法与资料，不承载运行时能力；要拦截调用、暴露服务或路由时用 extension。技能内容随对话注入，属于模型可见数据——敏感操作不要依赖技能文本当访问控制。

### MCP server：配置声明的外部工具

MCP server 与技能启用状态放在 `extensions_config.json`，与主配置 `config.yaml` 分离；`mcpServers.<server>.routing` 可加软性工具偏好提示，软硬路由的边界见 [CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/docs/CONFIGURATION.md)。**应用仓建议**：MCP 适合把现成工具面接进来；要改变 agent 内部组合时仍需 extension。

## 先建立什么：第一个垂直切片

无论形态，应用仓的第一笔完整交付应同时包含：

1. **可运行的入口**——上面的最小入口之一，能在干净环境复现；
2. **声明的依赖**——extension 形态下每个被 import 的框架都要显式声明（契约包零依赖是刻意的）；
3. **包级测试**——extension 形态下，示例包的测试只用公共契约加自身依赖：
   > The tests use only the public contract plus this package's declared dependencies; the DeerFlow harness and Gateway application are not imported.
   >
   > — [示例扩展 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md)
4. **安装验证**——extension 形态下必须装进一个真实 checkout 并重启后观察行为（见下）；
5. **面向用户的说明**——入口名、贡献了什么、怎么开关。

**测试的诚实边界（运行时事实）**：v2.1.0 的示例与手册只演示契约级包测试；真实装载组合（真 Loader、真 Gateway 装配后的行为证据）在这个版本没有随包交付的现成模式。**应用仓建议**：不要把"包测试绿"当作组合成立——在装进 checkout 并重启后，至少观察一个可检查的宿主侧行为（示例的做法是贡献一条 `GET /api/extension-example/stats` 路由再 curl 它）。

## 安装与分发（extension 形态）

接受信任提示后，extension manager 依次：把可部署快照复制到 `backend/extensions/sources/<包名>/`；把快照加进 `backend/pyproject.toml` 的 `extensions` 依赖组并更新 `backend/uv.lock`；安装锁定环境；在所选 `config.yaml` 写入并启用 startup-only 的 `plugins:` 条目（[示例 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md)）。

**运行时事实**：

- 装载只发生在 Gateway 构建应用时——install/enable/disable/remove 与手改 `plugins:` 都要**重启**才生效；
- 来源三种：PyPI 版本锁定 requirement、钉定的公开 HTTPS Git URL、本地目录快照；SSH Git URL 被拒（Docker 构建器不转发主机 SSH 凭据）；
- `--yes` 仅供已审查并信任来源的自动化使用——构建钩子与运行时代码以 Gateway 权限执行；
- `--required` 把后续装载失败变成 Gateway 启动中止，除非应用缺了这个扩展就是错的，否则别开。

**应用仓建议**：把"operator 信任"写进你自己的发布文档——谁能装、装什么来源、装完怎么验证，这三问在 DeerFlow 侧没有替你回答。

## 四层决定清单

| 层 | DeerFlow v2.1.0 给了什么 | 你的仓要决定什么 |
|---|---|---|
| 运行时接口 | 契约七种贡献类型 / factory 与 client API / SKILL.md 格式 / MCP 配置 | 你的公开接口、错误合同、配置面 |
| 仓库结构 | 示例包布局（`__init__.py` + 实现模块 + `tests/`） | 独立仓或 monorepo、测试放哪、文档放哪 |
| 分发形态 | extension manager 事务、skill 目录、依赖引入 | 发布到哪、版本区间、兼容承诺、升级路径 |
| 治理规则 | 主仓规则可参考（见 [SDLC Reference](../sdlc-reference/00-index.md)） | 你的 review、CI、发布与安全审批 |

## 证据入口

- [harness quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/quick-start.mdx) 与 [integration-guide](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/integration-guide.mdx)：内嵌形态入口。
- [extensions quick-start](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/extensions/quick-start.mdx) 与 [extensions 指南](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/extensions/AGENTS.md)：extension 形态入口与契约面。
- [示例扩展 README](https://github.com/bytedance/deer-flow/blob/v2.1.0/examples/deerflow-extension-example/README.md)：安装事务、分发来源、信任边界与包测试口径。
- [skills 手册](https://github.com/bytedance/deer-flow/blob/v2.1.0/frontend/src/content/en/harness/skills.mdx) 与 [CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/docs/CONFIGURATION.md)：skill 与 MCP 形态。

术语不熟时查[术语与心智模型](./02-terms-and-mental-models.md)。
