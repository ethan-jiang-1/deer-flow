# 配置与检查面

## 这页解决什么问题

部署侧的可定位性：配置从哪来、怎么升级、坏了怎么查。DeerFlow v2.2.0 把这件事拆成"示例配置 → 本地配置 → 版本升级 → 体检 → 报障包"五件，每件有明确的命令或文件归属；本页后半盘点 v2.2.0 新增的四个配置面，它们决定了应用仓部署时要额外声明什么。

## 机制（运行时事实，对 v2.2.0 核验）

**示例配置 → 本地配置**。仓库提供 `config.example.yaml` 与 `extensions_config.example.json`，复制为 gitignore 的 `config.yaml` / `extensions_config.json` 后生效；没有 `config.yaml` 服务起不来（根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md) 的 setup 顺序：`make config` → `make install` → `make dev`）。两文件分工固定：主配置归 operator（含 `plugins:` 装载清单），`extensions_config.json` 承载运行时可写的 MCP 与技能启用状态（[CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/docs/CONFIGURATION.md)）。

**配置版本升级**。`config.example.yaml` 带 `config_version` 追踪 schema 变化（v2.2.0 为 **63**，同一值也写进 Helm chart 的 `values.yaml`，chart 的 PR 校验会拦住"chart 内置版本落后于示例配置"的漂移——见[卷二·CI 门禁](../sdlc-reference/05-ci-gates.md)）；本地配置版本低于示例时启动给出升级警告，`make config-upgrade` 合并新字段并保留用户值（备份 `.bak`），`make test-config-version` 跑配置升级的集成测试套件。改配置 schema 的人有义务 bump 版本——旧配置得到的是**指引而非静默失效**（[CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/docs/CONFIGURATION.md)）。

**体检与报障**。`make doctor` 检查配置与系统要求；`make support-bundle` 生成脱敏的 troubleshooting 摘要、AI 辅助 issue 草稿（刻意不编造复现步骤）与可选证据 zip（不含 `.env`、原始对话与 workspace 文件），`triage.json` 提供机器可读的稳定信号（[CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/CONTRIBUTING.md)；根 AGENTS.md 不含 triage 内容）。

**这套面的设计句式**：部署侧的每个故障模式（配置缺失、schema 过期、环境不满足、报障信息不足）都有一个**具名的命令**接住它，而不是一条 FAQ 建议。

## v2.2.0 新增的四个部署配置面（运行时事实）

这四项都默认关闭或默认无需配置，但**一旦你的部署形态需要它们，它们就不是可选项**——启动门会拒绝配置不全的组合，而不是降级运行。

| 配置面 | 默认 | 什么时候必须动 | 启动门做什么 |
|---|---|---|---|
| `deployment.multi_instance` | `false`（或环境变量 `DEER_FLOW_MULTI_INSTANCE=1`） | 多个 Gateway 实例共享一个数据库（K8s `replicas > 1`） | 强制 `database.backend: postgres`、`run_events.backend: db`、`run_ownership.heartbeat_enabled: true` 与 Redis stream bridge；拒绝 `sandbox.ownership.type: memory`、进程内浏览器工具、以及"开了 scheduler 但没开 `scheduler.multi_instance`" |
| `blob_storage` | `enabled: false`、`backend: local_fs` | 需要把二进制大对象放到共享卷（NFS/EFS/ReadWriteMany PVC）时 | 后端私有配置逐字透传给后端；`local_fs` 的 `root` 为空时默认 `{runtime_home}/blobs` |
| `knowledge_base` | `enabled: false`、`scope_selection_enabled: false` | 启用只读知识检索能力时 | 连接与检索设置不在这一节，而在 `tools:` 下对应的 provider 条目（如 RAGFlow 的 `knowledge_search`）；`scope_selection_enabled` 只影响自定义 agent 会话里的选择器显示 |
| `DEER_FLOW_CREDENTIALS_KEY` | 单实例时自动生成 `{DEER_FLOW_HOME}/.credentials_key`（0600） | 声明了多实例，且启用了存凭据的功能（`channel_connections`、带 `refresh_token` OAuth 的 MCP server） | 多实例下缺这个键**拒绝启动**；键可以是用逗号分隔的轮换列表（首个加密、全部可解密），格式错误同样拒绝启动且不在报错里回显键值 |

三条值得写进应用仓部署文档的细节：① `DEER_FLOW_MULTI_INSTANCE` 把空串、`0`、`false`、`no`、`off` 视为"未声明"，任何其他值都算声明多实例——**拼错会 fail closed 而不是静默降级**；② `GET /health/ready` 每次探测都 ping Redis stream bridge，Redis 挂掉时返回 503（`stream_bridge: unreachable`），让编排器把这个实例摘掉而不是把无法发布的事件收进来；③ 丢了 `DEER_FLOW_CREDENTIALS_KEY` 会让已存凭据不可读——不可读值被当作缺失记日志，不会崩溃，但 Slack 之类会退回部署级 bot token，所以这个键要进备份清单（Helm chart 会把它生成进 Secret 并跨升级保留）。本地想在单机上验证跨实例行为，有 `make dev-multi` / `make dev-multi-check` / `make dev-multi-down` 三个目标（`scripts/dev_multi_instance.sh`）起一对 Gateway + 一次性的 Postgres/Redis 容器。

## 应用仓能借鉴什么

**可移用**：① 示例配置 + gitignore 本地配置的分离（用户改的东西和你要维护的东西分开）；② 版本字段 + 自动升级 + 备份（外加一个"高版本配置字段必须同步到 chart/模板"的漂移检查）——只要你的配置 schema 会演进，这就是最便宜的兼容机制；③ doctor 式体检命令（应用仓内嵌 DeerFlow 时，`make doctor` 检查的是 DeerFlow 侧要求，你的应用自己的前置条件要有自己的体检）；④ support-bundle 的脱敏纪律——**明确列出不含什么**与含什么同样重要。**需要自定**：应用仓的报障包要不要包含 DeerFlow 侧的 bundle（让用户两段都贴），取决于你的支持流程；建议至少在文档里写清报障时要贴哪几段。

## 证据入口

- 根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/AGENTS.md)（Commands: Root vs. Module 节：make config / doctor / support-bundle / test-config-version）
- [backend/docs/CONFIGURATION.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/docs/CONFIGURATION.md)（Config Versioning、Deployment topology (multi-instance)、Credentials encryption key、Agent Storage 各节）与 [backend/docs/blob-storage.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/docs/blob-storage.md)、[backend/docs/KNOWLEDGE.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/backend/docs/KNOWLEDGE.md)
- [CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.2.0/CONTRIBUTING.md)（Troubleshooting Bundle 节）
