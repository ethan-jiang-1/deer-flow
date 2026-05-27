# DeerFlow 集成指南

## 三种接入方式

### 1. HTTP API（REST + SSE）

Gateway 是 FastAPI 应用，默认端口 8001，通过 Nginx 统一在 2026 端口暴露。

```bash
# 启动服务
make dev          # 本地开发，hot-reload
make start        # 生产模式
make up           # Docker 生产部署
```

统一入口：`http://localhost:2026`
API 文档：`http://localhost:8001/docs`（Swagger）

### 2. Python SDK（嵌入式）

直接 `pip install deerflow-harness`（源码在 `backend/packages/harness/`），无需 HTTP 服务：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient(
    config_path="config.yaml",
    thinking_enabled=True,
    subagent_enabled=False,
)

# 对话
response = client.chat("分析一下这个项目", thread_id="my-thread")

# 流式
for event in client.stream("分析一下", thread_id="my-thread"):
    print(event)

# 管理 API
models = client.list_models()
skills = client.list_skills()
memory = client.get_memory()
```

`DeerFlowClient` 的方法签名与 Gateway API 一一对应。

### 3. Node.js/TypeScript

前端用的方式：`@langchain/langgraph-sdk` 直接连 Gateway。
```ts
import { Client } from "@langchain/langgraph-sdk";
const client = new Client({ apiUrl: "http://localhost:8001" });
```

### 4. Docker

生产部署：`docker-compose.yaml` 管理 4 个服务（nginx、frontend、gateway、provisioner），端口 2026。

---

## 配置文件

项目启动需要两个配置文件：

| 文件 | 作用 |
|------|------|
| `config.yaml` | 主配置：模型、工具、沙箱、Agent、记忆、IM 频道等 |
| `extensions_config.json` | 扩展配置：MCP 服务器、Skill 启用状态 |

生成方式：
```bash
make config        # 从 config.example.yaml 生成 config.yaml
make config-upgrade  # 合并新字段到已有 config.yaml
```

### config.yaml 核心段

| 段 | 说明 |
|----|------|
| `models` | LLM 模型列表，支持 OpenAI/Anthropic/DeepSeek/Gemini/MiniMax/vLLM |
| `tools` | 可配置工具，web_search、web_fetch、bash、文件操作等 |
| `sandbox` | 沙箱：local（默认）或 aio_sandbox（Docker 隔离） |
| `subagents` | 子 Agent 超时、自定义 Agent 定义 |
| `skills` | Skill 路径配置 |
| `summarization` | 上下文摘要，默认 32000 token 触发 |
| `memory` | 用户记忆，文件存储 |
| `database` | sqlite（默认）或 postgres |
| `channels` | IM 集成：Feishu/Slack/Telegram/WeChat/DingTalk/Discord |
| `guardrails` | 工具调用鉴权 |
| `circuit_breaker` | LLM 熔断（默认关闭） |

---

## 环境变量

详见 `.env.example`。按类别：

| 类别 | 关键变量 |
|------|----------|
| 模型 API Key | `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `VOLCENGINE_API_KEY` 等 |
| 搜索 API Key | `SERPER_API_KEY`, `TAVILY_API_KEY`, `JINA_API_KEY` 等 |
| IM 通道 | `FEISHU_APP_ID`, `SLACK_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN` 等 |
| 可观测 | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` |
| 数据库 | `DATABASE_URL`（postgres 模式） |
| Gateway | `GATEWAY_HOST`, `GATEWAY_PORT`, `GATEWAY_ENABLE_DOCS` |
| 内部 | `DEER_FLOW_INTERNAL_AUTH_TOKEN`, `DEER_FLOW_CONFIG_PATH`, `DEER_FLOW_HOME` |

---

## API 端点总览

基础路径：`http://localhost:8001`

| 前缀 | 说明 |
|------|------|
| `/api/models` | 模型列表与详情 |
| `/api/threads/{id}/runs` | 对话运行：创建、流式、取消、消息、事件 |
| `/api/threads/{id}` | 线程管理：创建、删除、状态、搜索 |
| `/api/runs` | 无状态运行 |
| `/api/memory` | 用户记忆 CRUD、导入导出 |
| `/api/skills` | Skill 列表、安装、启停 |
| `/api/mcp` | MCP 服务器配置 |
| `/api/agents` | 自定义 Agent CRUD、用户档案 |
| `/api/v1/auth` | 认证：登录、注册、OAuth |
| `/api/threads/{id}/artifacts` | 产物文件服务 |
| `/api/threads/{id}/uploads` | 文件上传 |
| `/api/feedback` | 对话反馈 |
| `/health` | 健康检查 |

### 核心端点用法

**创建线程并流式对话：**
```
POST /api/threads/{id}/runs/stream
Body: { "input": {"messages": [{"role": "user", "content": "..."}]} }
Response: SSE (text/event-stream)
  event: values     -> AgentThreadState 全量快照
  event: messages-tuple -> 增量消息 delta
  event: custom     -> 自定义事件
  event: end        -> 流结束
```

**后台运行 + 轮询：**
```
POST /api/threads/{id}/runs        -> 201 { "run_id": "..." }
GET  /api/threads/{id}/runs/{rid}  -> 运行状态
GET  /api/threads/{id}/runs/{rid}/join -> SSE 加入
```
