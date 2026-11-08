# Part A：从零到跑起来

## A.1 DeerFlow 是什么

DeerFlow（Deep Exploration and Efficient Research Flow）是字节跳动开源的 **super-agent harness**，MIT 协议。它不是一个特定任务的 AI 工具，而是一个 **agent 框架**：你定义 agent 的行为（Skills）、给它们工具（Sandbox/MCP）、配置模型，然后通过 Web/Curl/Python 与它们交互。

核心能力：

| 能力 | 说明 |
|------|------|
| **LangGraph Agent 引擎** | 基于 LangGraph 的 `create_agent` 构建，支持 checkpoint、streaming、interrupt |
| **Skills 系统** | `SKILL.md`（YAML frontmatter + Markdown）定义 agent 行为，兼容 agentskills.io 标准 |
| **MCP 工具集成** | 支持 stdio/SSE/HTTP 传输，带 deferred tool loading 和 tool_search |
| **Sandbox 执行** | 代码在隔离 Docker 容器或本地沙箱中运行，统一的 `/mnt/user-data` 虚拟路径 |
| **Sub-agent 委派** | `task()` 工具可委派子 agent 并行执行，默认 3 个并发（上限 64），每次 run 默认最多 6 次委派 |
| **持久记忆** | 基于文件/DB 的用户记忆系统，自动提取 fact 并注入系统 prompt |
| **39 个 Middleware** | 覆盖沙箱生命周期、错误处理、token 统计、loop 检测、guardrail、PII 脱敏、artifact 采集等 |
| **IM 频道** | 飞书/Slack/Telegram/DingTalk 可直接作为 agent 交互入口 |

> 🔄 同步 #6（v2.1.0-rc0）：middleware 数量 18 → 37（`_digested/internals/middleware/03-catalog.md`）。

> 🔄 同步 #8（v2.2.0）：middleware 口径再变——现在是 **39 个条目位**（`_digested/internals/middleware/03-catalog.md` 按 v2.2.0 重写：`_build_runtime_middlewares()` 产出前 16 条 + `build_middlewares()`（`deerflow/agents/lead_agent/agent.py:485`）追加 23 条）。v2.2.0 新增 `KnowledgeScopeMiddleware` / `ArtifactResolutionMiddleware` / `ArtifactCaptureMiddleware` / `PiiRedactionMiddleware` / `ModelContentCompatibilityMiddleware`，`SkillToolPolicyMiddleware` **已删除**；lead 链默认约 24 条、全开约 30 条。Sub-agent 数也一并订正：默认并发 3（`MAX_CONCURRENT_SUBAGENTS`，`deerflow/subagents/executor.py:2337`），合法上限 64，且有 `subagents.max_total_per_run`（默认 6）的**每次 run 总数**兜底。

技术栈：Python 3.12+ / Node.js 24+ / LangGraph / Next.js 16 / FastAPI / Nginx

> 🔄 同步 #6（v2.1.0-rc0）：Node.js 要求 22+ → 24+（#5063，CI 与开发环境同步升级）。

> 架构全景见 `_digested/overview/`，middleware 完整链见 `_digested/internals/middleware/03-catalog.md`。

## A.2 环境准备

**推荐配置**：4 vCPU / 8 GB RAM 起步。Docker 方式建议 8 vCPU / 16 GB RAM（镜像构建需要额外内存）。2 vCPU / 4 GB 环境经常启动失败或在正常负载下变得不响应。

**前提条件**：

| 方式 | 需要 |
|------|------|
| Docker（推荐） | Docker Desktop 或 Docker Engine + `docker` CLI |
| 本地开发 | Node.js 24+, pnpm 10+, uv (Python 包管理器), nginx |

## A.3 安装（Docker 方式，推荐）

```bash
# 1. 克隆
git clone https://github.com/bytedance/deer-flow.git
cd deer-flow

# 2. 生成 config.yaml
make config
# 从 config.example.yaml 复制，生成带 $VAR 占位符的配置文件

# 3. 初始化 Docker 环境（首次，需要几分钟）
make docker-init
# → 构建 gateway/web 两个镜像
# → 安装前端 pnpm 依赖
# → 安装后端 uv 依赖

# 4. 启动
make docker-start
```

启动后：

| 入口 | 地址 | 说明 |
|------|------|------|
| Web 界面 | `http://localhost:2026` | 聊天 + Agent/Settings 管理 |
| Gateway REST API | `http://localhost:2026/api/*` | 模型列表、Skills、MCP、上传等 |
| LangGraph 兼容 API | `http://localhost:2026/api/langgraph/*` | Thread/Run/Stream 标准端点 |

```bash
# 停止
make docker-stop

# 查看所有日志
make docker-logs

# 只看前端日志
make docker-logs-frontend

# 只看 gateway 日志
make docker-logs-gateway
```

> 服务架构（nginx 统一入口 2026，反代到 gateway:8001 和 web:3000）见 `_digested/overview/01-system-overview.md`。
>
> 🔄 同步 #6（v2.1.0-rc0）：生产启动除 `make docker-start` 外还支持本地 `make start`（`SKIP_FRONTEND_BUILD=1` 可复用上次前端构建，跳过重新打包）；Gateway 提供就绪探针 `GET /health/ready`（除进程存活外还探测持久化后端可达性），`make up` 会等待该探针通过才打印成功横幅。

## A.4 安装（本地开发方式）

```bash
git clone https://github.com/bytedance/deer-flow.git
cd deer-flow

make config        # 生成 config.yaml
make check         # 检查 Node.js/pnpm/uv/nginx 是否就绪
make install       # 安装全部依赖
make dev           # 启动全部服务（Gateway + Frontend + Nginx）
```

如果 `make check` 报缺依赖，按提示安装后再继续。

## A.5 配置模型

编辑项目根目录的 `config.yaml`。值以 `$` 开头会从环境变量解析。

> 🔄 同步 #6（v2.1.0-rc0）：`config.example.yaml` 的 `config_version` 现为 **45**；旧配置启动时 Gateway 会警告版本落后，用 `make config-upgrade` 合并缺失字段。

> 🔄 同步 #8（v2.2.0）：`config_version` 已到 **63**（`config.example.yaml:23`），模板本身从 3021 行涨到 **3680 行**。新增的顶层段有 `blob_storage`（`:2563`，默认 `enabled: false`）、`knowledge_base`（`:824`，默认关）、`agents_api`（`:2580`，默认 `enabled: false`，关着时 agent/USER.md 管理路由一律 403）、`tool_artifacts`（`:1461`）、`pii_redaction`（`:1537`）、`deployment`（`:2923`）、`typesafe`（`:3372` 起，注释示例），以及 `lead_prompt_overlay`（`:26` 起，注释示例）。升级流程不变：`make config-upgrade` 把你的 `config.yaml` 合并进新模板，别手抄。**重启生效字段**从 18 项增至 **27 项**（`deerflow/config/reload_boundary.py:45` 的 `STARTUP_ONLY_FIELDS`，新增 `deployment`、`projects.summary_*` 等）——改这些必须重启 Gateway，热加载不生效。`.env` 也换了装法：`DEER_FLOW_ENV_FILE` 选择器（`deerflow/env.py:10`）。详见 `_digested/internals/configuration/04-config-reference.md` 与 `_digested/getting-started/00-config-overview.md`。

**最小配置 — 只配一个 DeepSeek V3**：

```yaml
models:
  - name: deepseek-v3
    display_name: DeepSeek V3
    use: deerflow.models.patched_deepseek:PatchedChatDeepSeek
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1
```

然后设置环境变量：

```bash
export DEEPSEEK_API_KEY="sk-你的key"
```

**更多 provider 配置示例**：

```yaml
models:
  # OpenAI 原生
  - name: gpt-4o
    use: langchain_openai:ChatOpenAI
    model: gpt-4o
    api_key: $OPENAI_API_KEY

  # Anthropic Claude（支持 thinking）
  - name: claude-sonnet
    use: langchain_anthropic:ChatAnthropic
    model: claude-sonnet-4-20250514
    api_key: $ANTHROPIC_API_KEY
    supports_thinking: true

  # Ollama 本地模型
  - name: qwen3-local
    use: langchain_ollama:ChatOllama
    model: qwen3:latest
    base_url: http://localhost:11434

  # 火山引擎豆包（OpenAI 兼容网关）
  - name: doubao
    use: deerflow.models.patched_openai:PatchedChatOpenAI
    model: doubao-seed-2-0-code-250615
    api_key: $VOLCENGINE_API_KEY
    base_url: https://ark.cn-beijing.volces.com/api/v3

  # DeepSeek（支持 thinking）
  - name: deepseek-r1
    use: deerflow.models.patched_deepseek:PatchedChatDeepSeek
    model: deepseek-reasoner
    api_key: $DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1
    supports_thinking: true
```

**验证配置**：

```bash
cd backend
python -c "from deerflow.config import get_app_config; c = get_app_config(); print('模型数量:', len(c.models)); print('第一个:', c.models[0].name)"
```

> 模型配置的完整说明（thinking/vision/reasoning effort/热加载边界）见 `_digested/internals/configuration/01-config-yaml.md` 和 `_digested/internals/model-layer/`。

## A.6 首次体验

### 方式 1：Web 界面

打开 `http://localhost:2026`：

- **Chat** — 左侧对话列表，中间聊天区，底部输入框。直接输入 "你好，用 Python 写一个冒泡排序" 即可跟 agent 对话
- **Settings → Models** — 确认你的模型出现在列表中
- **Settings → Skills** — 看到所有内置和自定义 skill，可启用/禁用
- **Settings → MCP** — 管理 MCP 服务器连接
- **Agents** — 创建和管理自定义 agent（SOUL.md + config.yaml）

### 方式 2：curl（Gateway HTTP API）

```bash
# 创建一个对话线程
curl -X POST http://localhost:2026/api/threads/demo-1/runs/stream \
  -H "Content-Type: application/json" \
  -d '{"input": {"messages": [{"role": "user", "content": "用 Python 写一个快速排序"}]}}'

# 查看可用模型
curl http://localhost:2026/api/models | python -m json.tool

# 查看可用 Skills
curl http://localhost:2026/api/skills | python -m json.tool
```

> 完整 API 参考见 `_digested/enterprise-operations/app-layer/` 和 `backend/docs/API.md`。

### 方式 3：Python 嵌入式客户端

无需启动 HTTP 服务，直接在 Python 进程中调用：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()

# 同步对话 — 阻塞直到 agent 完成
reply = client.chat("用 Python 写一个二分查找", thread_id="demo-1")
print(reply)

# 流式对话 — 实时逐 chunk 输出
for event in client.stream("解释 LangGraph 的工作原理", thread_id="demo-2"):
    print(event)

# 管理 API
models = client.list_models()
skills = client.list_skills()
memory = client.get_memory()
print(f"{len(models['models'])} 个模型, {len(skills['skills'])} 个 skills")
```

> `DeerFlowClient` 的实现见 `deerflow/client.py:177`（`class DeerFlowClient`；`stream()` 在 `:859`、`chat()` 在 `:1314`，全文 2002 行），它与 Gateway 共享同一套底层模块（`make_lead_agent` → `create_agent` → middleware chain），不是二次包装。
>
> 🔄 同步 #6（v2.1.0-rc0）：原引用 `client.py:82` 已漂移（现 L145）；另 v2.1.0-rc0 起 `DeerFlowClient` 支持多用户内嵌复用（#5206，按 `(agent_name, user_id)` 缓存内部 agent）与流式修复（#5408/#5479），trace id 无条件下发（#5119）。

> 🔄 同步 #8（v2.2.0）：行号再漂移——类定义从 L145 → **L177**（`stream()` L859、`chat()` L1314）。另外**多了第四种体验方式**：可安装的 `deerflow` 终端命令（v2.2.0 新增）。有 TTY 时 `deerflow` 直接进全屏 TUI，脚本里用 `deerflow --print "问题"` / `deerflow --json "问题"`；`--print` 与 `--json` 互斥，run 失败退出码 1。它跑的是**内嵌** `DeerFlowClient`，不需要 Gateway/Nginx/Docker——和上面的 Python 内嵌方式同源，只是换了外壳。完整契约见 `_digested/getting-started/06-tui.md`。
>
> ```bash
> uv pip install 'deerflow-harness[tui]'    # textual 是可选依赖
> deerflow                                   # 全屏 TUI
> deerflow --print "用 Python 写一个二分查找"  # 一次性回答
> echo "解释 LangGraph" | deerflow --json     # 逐行 NDJSON 事件
> ```
