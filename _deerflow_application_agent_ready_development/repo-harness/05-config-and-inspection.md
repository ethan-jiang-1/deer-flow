# 配置与检查面

## 这页解决什么问题

部署侧的可定位性：配置从哪来、怎么升级、坏了怎么查。DeerFlow v2.1.0 把这件事拆成"示例配置 → 本地配置 → 版本升级 → 体检 → 报障包"五件，每件有明确的命令或文件归属。

## 机制（运行时事实，对 v2.1.0 核验）

**示例配置 → 本地配置**。仓库提供 `config.example.yaml` 与 `extensions_config.example.json`，复制为 gitignore 的 `config.yaml` / `extensions_config.json` 后生效；没有 `config.yaml` 服务起不来（根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md) 的 setup 顺序：`make config` → `make install` → `make dev`）。两文件分工固定：主配置归 operator（含 `plugins:` 装载清单），`extensions_config.json` 承载运行时可写的 MCP 与技能启用状态（[CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/docs/CONFIGURATION.md)）。

**配置版本升级**。`config.example.yaml` 带 `config_version` 追踪 schema 变化；示例版本高于本地配置时启动给出升级警告，`make config-upgrade` 合并新字段并保留用户值（备份 `.bak`）。改配置 schema 的人有义务 bump 版本——旧配置得到的是**指引而非静默失效**（[CONFIGURATION](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/docs/CONFIGURATION.md)）。

**体检与报障**。`make doctor` 检查配置与系统要求；`make support-bundle` 生成脱敏的 troubleshooting 摘要、AI 辅助 issue 草稿（刻意不编造复现步骤）与可选证据 zip（不含 `.env`、原始对话与 workspace 文件），`triage.json` 提供机器可读的稳定信号（[CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md)；根 AGENTS.md 不含 triage 内容）。

**这套面的设计句式**：部署侧的每个故障模式（配置缺失、schema 过期、环境不满足、报障信息不足）都有一个**具名的命令**接住它，而不是一条 FAQ 建议。

## 应用仓能借鉴什么

**可移用**：① 示例配置 + gitignore 本地配置的分离（用户改的东西和你要维护的东西分开）；② 版本字段 + 自动升级 + 备份——只要你的配置 schema 会演进，这就是最便宜的兼容机制；③ doctor 式体检命令（应用仓内嵌 DeerFlow 时，`make doctor` 检查的是 DeerFlow 侧要求，你的应用自己的前置条件要有自己的体检）；④ support-bundle 的脱敏纪律——**明确列出不含什么**与含什么同样重要。**需要自定**：应用仓的报障包要不要包含 DeerFlow 侧的 bundle（让用户两段都贴），取决于你的支持流程；建议至少在文档里写清报障时要贴哪几段。

## 证据入口

- 根 [AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/AGENTS.md)（Commands 节：make config / doctor / support-bundle）
- [backend/docs/CONFIGURATION.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/docs/CONFIGURATION.md)（Config Versioning 节）
- [CONTRIBUTING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/CONTRIBUTING.md)（Troubleshooting Bundle 节）
