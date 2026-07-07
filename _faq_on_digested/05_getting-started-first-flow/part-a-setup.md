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
| **Sub-agent 委派** | `task()` 工具可委派子 agent 并行执行，最多 3 个并发 |
| **持久记忆** | 基于文件/DB 的用户记忆系统，自动提取 fact 并注入系统 prompt |
| **18 个 Middleware** | 覆盖沙箱生命周期、错误处理、token 统计、loop 检测、guardrail 等 |
| **IM 频道** | 飞书/Slack/Telegram/DingTalk 可直接作为 agent 交互入口 |

技术栈：Python 3.12+ / Node.js 22+ / LangGraph / Next.js 16 / FastAPI / Nginx

> 架构全景见 `_digest/architecture/`，middleware 完整链见 `_digest/middleware/03-catalog.md`。

## A.2 环境准备

**推荐配置**：4 vCPU / 8 GB RAM 起步。Docker 方式建议 8 vCPU / 16 GB RAM（镜像构建需要额外内存）。2 vCPU / 4 GB 环境经常启动失败或在正常负载下变得不响应。

**前提条件**：

| 方式 | 需要 |
|------|------|
| Docker（推荐） | Docker Desktop 或 Docker Engine + `docker` CLI |
| 本地开发 | Node.js 22+, pnpm 10+, uv (Python 包管理器), nginx |

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

> 服务架构（nginx 统一入口 2026，反代到 gateway:8001 和 web:3000）见 `_digest/architecture/01-system-overview.md`。

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

> 模型配置的完整说明（thinking/vision/reasoning effort/热加载边界）见 `_digest/configuration/01-config-yaml.md` 和 `_digest/model-layer/`。

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

> 完整 API 参考见 `_digest/app-layer/` 和 `backend/docs/API.md`。

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

> `DeerFlowClient` 的实现见 `deerflow/client.py:82`，它与 Gateway 共享同一套底层模块（`make_lead_agent` → `create_agent` → middleware chain），不是二次包装。
