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
| `config.yaml`（项目根） | 模型、工具、沙箱、子 agent、记忆、标题、总结等全配置（`config_version: 63`） |
| `extensions_config.json`（项目根） | MCP 服务器连接 + Skills 启用/禁用状态 |
| `skills/public/` | 内置 Skills（git 跟踪，v2.2.0 共 23 个） |
| `skills/custom/` | 自定义 Skills（gitignore） |
| `.deer-flow/users/{uid}/agents/{name}/` | 自定义 Agent 的 SOUL.md + config.yaml（**现行布局**） |
| `.deer-flow/users/{uid}/USER.md` | 用户画像（仅 `agents_api.enabled: true` 时可通过 `/user-profile` 路由读写） |
| `.deer-flow/users/{uid}/memory.json` | 用户记忆数据 |
| `.deer-flow/users/{uid}/skills/custom/` | 按用户隔离的自定义 Skills |
| `.deer-flow/users/{uid}/threads/{tid}/` | 每个对话线程的 workspace/uploads/outputs |
| `.deer-flow/memory.json`、`.deer-flow/agents/{name}/` | **legacy 只读回退**（v2.2.0 起不再写入，见下） |

> 🔄 同步 #8（v2.2.0）：工作区布局在 v2.2.0 定稿为 **`users/{user_id}/` 为唯一写入面**（`deerflow/config/paths.py:140-157` 的布局 docstring）。要点：
> - 顶层 `.deer-flow/memory.json`（`paths.py:195-197`）与顶层 `.deer-flow/agents/{name}/`（`paths.py:207-215` 的 `agents_dir()`）是 **legacy 共享布局**，现在只做**只读回退**——读的时候会兜底，写的时候不会碰。`FileAgentStore.delete()`（`deerflow/persistence/agents/file.py:168`）删到 legacy agent 会返回 `legacy` 并原地保留。
> - 新增 `users/{uid}/USER.md`（`paths.py:199-205` 的 `user_md_file()`）：**只是存取**，本版本没有任何代码把它注入 prompt——读写它是 `GET`/`PUT /api/agents/user-profile`（`backend/app/gateway/routers/agents.py:692` 的 `get_user_profile` 与 `:729` 的 `update_user_profile`），且受 `agents_api.enabled` 开关约束（默认 `false`，`config.example.yaml:2580`）。
> - 新增 `users/{uid}/skills/`（`paths.py:284-286` 的 `user_skills_dir()`，含 `:288` 的 `user_custom_skills_dir()`），挂在沙箱里的 `/mnt/skills/custom`；整合包 skill 走 `.deer-flow/integrations/skills/{provider}/`（`paths.py:297` 的 `integration_skills_dir()`）。
> - 记忆的 `memory.storage_path` 现在被当成**根目录**而非文件路径（`deerflow/config/memory_config.py:277-289` 会把旧的 `.json` 形式丢弃并 warn），per-user 落在 `{storage_path}/users/{uid}/memory.json`。
>
> 完整目录语义见 `_digested/internals/configuration/04-config-reference.md`。

### 常用命令

```bash
# === 服务管理（项目根目录）===
make docker-start      # Docker 启动（推荐）
make dev               # 本地启动（热重载）
make start             # 本地生产模式启动；SKIP_FRONTEND_BUILD=1 复用上次前端构建
make stop              # 停止所有服务
make docker-logs       # Docker 日志

# === 配置 ===
make config            # 从 config.example.yaml 生成 config.yaml
make config-upgrade    # 合并新版 config schema 的缺失字段（config_version 现为 63）

# === 终端 / 脚本（v2.2.0 新增）===
uv pip install 'deerflow-harness[tui]'
deerflow                       # 全屏 TUI（内嵌 client，不需要 Gateway）
deerflow --print "问题"         # 一次性回答（失败退出码 1）
deerflow --json "问题"          # 逐行 NDJSON 事件

# === 后端（backend/ 目录）===
make test              # 运行全部测试（分四个并行 shard）
make lint              # ruff 代码检查
make format            # ruff 格式化
```

> 🔄 同步 #8（v2.2.0）：`make config-upgrade` 的目标版本从 45 提到 **63**（`config.example.yaml:23`）。`make test` 现在是四个并行 shard，且默认排除 live 与 blocking-I/O 测试（严格阻塞 IO 套件单独用 `make test-blocking-io`）。新增的 `deerflow` 命令见 `_digested/getting-started/06-tui.md`。

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
| 系统架构全景 | `_digested/overview/` |
| Agent 循环执行流 | `_digested/internals/agent-loop/` |
| Middleware 完整链（39 个条目位 + 时序） | `_digested/internals/middleware/03-catalog.md` |
| 配置系统（双文件 + 热加载边界） | `_digested/internals/configuration/` |
| 模型层（factory + provider patches） | `_digested/internals/model-layer/` |
| Gateway API 和应用层 | `_digested/operations/app-layer/` |
| MCP 工具注入和缓存 | `_digested/internals/configuration/02-extensions-json.md` |
| Sandbox（local vs Docker vs K8s） | `_digested/concepts/sandbox/` |

> 🔄 同步 #6（v2.1.0-rc0）：Node.js 要求升级为 24+（#5063）；Gateway 新增 `GET /health/ready` 就绪探针；`DeerFlowClient` 支持多用户内嵌复用（#5206）与流式修复（#5408/#5479）；前端新增 Projects / Trash / Capability Center 页面；seven sandbox 实现不变。

> 🔄 同步 #8（v2.2.0）：本页随 v2.2.0 复核的要点——middleware 由 37 改记 **39 个条目位**；`config_version` 45 → **63**；工作区唯一写入面收敛到 `users/{user_id}/`（顶层 `memory.json` / `agents/` 变 legacy 只读回退）；skill 的 `allowed-tools` 降级为**兼容元数据**（上游 #6935 `0d73798be`，`skills/tool_policy.py` 已删除、`agents/middlewares/skill_tool_policy_middleware.py` 已删除）；新增可安装的 `deerflow` 终端命令。sandbox 实现集合未变（local / Docker / K8s provisioner 三选一）。

## 相关 FAQ

| 问题 | 路径 |
|------|------|
| Skill 太多了选不准怎么办？ | `_faq_on_digested/01_skill-selection-accuracy/` |
| 任务 MD 文件能指定用哪个 skill 吗？ | `_faq_on_digested/02_command-skill-linkage/` |
| 企业静默执行中如何精确选择 skill？ | `_faq_on_digested/03_precise-skill-selection/` |
| MCP 工具管理最佳实践？ | `_faq_on_digested/04_mcp-best-practices/` |
