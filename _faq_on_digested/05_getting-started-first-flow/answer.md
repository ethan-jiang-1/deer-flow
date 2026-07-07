## 总览

DeerFlow 是一个开源 super-agent harness，基于 LangGraph，通过 Skills、自定义 Agent、Sub-agent 委派、MCP 工具四个层次来定义 agent 行为。

**快速上手路径**：`git clone` → `make config` → 配模型 → `make docker-start`（或 `make dev` 本地启动）→ 打开 `http://localhost:2026` → 跟 agent 聊几句。

**详细安装步骤**：见 [part-a-setup.md](part-a-setup.md)。

**搭建 Agent Flow**：见 [part-b-first-flow.md](part-b-first-flow.md)。

**补充问题**：
- [不依赖 Docker 可以跑吗？](no-docker.md) — 默认就是本地模式，零 Docker 完全可行
- [本地文件系统和 Git 集成](filesystem-and-git.md) — 用 custom mounts 让 agent 直接操作宿主机上的知识库、项目、Git 仓库
- [Agent 专属工作目录与文件系统约定](agent-workspace.md) — Agentic workflow 场景：给 agent 一个独立、持久的文件系统来放知识、数据、流程定义

---

## 快速参考卡

### 关键文件位置

| 文件 | 作用 |
|------|------|
| `config.yaml`（项目根） | 模型、工具、沙箱、子 agent、记忆、标题、总结等全配置 |
| `extensions_config.json`（项目根） | MCP 服务器连接 + Skills 启用/禁用状态 |
| `skills/public/` | 内置 Skills（git 跟踪） |
| `skills/custom/` | 自定义 Skills（gitignore） |
| `.deer-flow/users/{uid}/agents/{name}/` | 自定义 Agent 的 SOUL.md + config.yaml |
| `.deer-flow/users/{uid}/memory.json` | 用户记忆数据 |
| `.deer-flow/users/{uid}/threads/{tid}/` | 每个对话线程的 workspace/uploads/outputs |

### 常用命令

```bash
# === 服务管理（项目根目录）===
make docker-start      # Docker 启动（推荐）
make dev               # 本地启动
make stop              # 停止所有服务
make docker-logs       # Docker 日志

# === 配置 ===
make config            # 从 config.example.yaml 生成 config.yaml
make config-upgrade    # 合并新版 config schema 的缺失字段

# === 后端（backend/ 目录）===
make test              # 运行全部测试
make lint              # ruff 代码检查
make format            # ruff 格式化
```

### 推荐模型

DeerFlow 官方推荐：**Doubao-Seed-2.0-Code**、**DeepSeek V3.2**、**Kimi 2.5**。实际上任何 LangChain 兼容的 chat model 都能用（OpenAI、Anthropic、Ollama、vLLM、OpenAI 兼容网关等）。

### 最小化上手路径

1. `git clone` → `make config` → 配一个模型 → `make docker-start`（或 `make dev` 本地启动）
2. 在 Web 界面跟 agent 聊几句，确认通了
3. 写一个 `skills/custom/my-skill/SKILL.md`，聊一句测试它是否被加载
4. 如需要深度自动化，用 `DeerFlowClient` 在脚本中调用
5. 如需 agent 访问宿主机文件，配置 `sandbox.mounts` 自定义挂载（见 [filesystem-and-git.md](filesystem-and-git.md)）

---

## 相关 Digest 笔记

| 主题 | 路径 |
|------|------|
| 系统架构全景 | `_digest/architecture/` |
| Agent 循环执行流 | `_digest/agent-loop/` |
| Middleware 完整链（18 个 + 时序） | `_digest/middleware/03-catalog.md` |
| 配置系统（双文件 + 热加载边界） | `_digest/configuration/` |
| 模型层（factory + provider patches） | `_digest/model-layer/` |
| Gateway API 和应用层 | `_digest/app-layer/` |
| MCP 工具注入和缓存 | `_digest/configuration/02-extensions-json.md` |
| Sandbox（local vs Docker vs K8s） | `_digest/architecture/`（sandbox section） |

## 相关 FAQ

| 问题 | 路径 |
|------|------|
| Skill 太多了选不准怎么办？ | `_faq_on_digested/skill-selection-accuracy/` |
| 任务 MD 文件能指定用哪个 skill 吗？ | `_faq_on_digested/command-skill-linkage/` |
| 企业静默执行中如何精确选择 skill？ | `_faq_on_digested/precise-skill-selection/` |
| MCP 工具管理最佳实践？ | `_faq_on_digested/mcp-best-practices/` |
