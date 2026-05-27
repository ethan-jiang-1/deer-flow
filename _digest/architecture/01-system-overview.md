# 系统全景

## 整体架构图

```
                      Port 2026
                          │
                    ┌─────┴─────┐
                    │   Nginx    │  (alpine, 反向代理)
                    └─────┬─────┘
                          │
            ┌─────────────┼─────────────┐
            │             │             │
      ┌─────┴─────┐ ┌────┴─────┐ ┌─────┴──────┐
      │ Frontend  │ │ Gateway  │ │Provisioner │ (可选)
      │ Next.js   │ │ FastAPI  │ │  K3s sandbox│
      │ :3000     │ │ :8001    │ │   :8002    │
      └───────────┘ └────┬─────┘ └────────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         ┌────┴────┐ ┌──┴───┐ ┌───┴────┐
         │LangGraph│ │Agent │ │Channels│
         │ Runtime │ │      │ │  (IM)  │
         └─────────┘ └──────┘ └────────┘
```

## 四个进程

| 进程 | 端口 | 技术 | 角色 |
|------|------|------|------|
| **Nginx** | 2026 | nginx:alpine | 反向代理、统一入口、路由分发 |
| **Frontend** | 3000 | Next.js 16 + React 19 | Web UI |
| **Gateway** | 8001 | FastAPI + Uvicorn | REST API + Agent Runtime |
| **Provisioner** | 8002 | Python | K3s 沙箱管理（可选） |

## Gateway 是核心

Gateway 承载了两个角色：

1. **HTTP API** — 15 个路由模块提供 REST 接口
2. **Agent Runtime** — 嵌入 LangGraph-compatible agent runtime（不依赖独立 LangGraph Server）

Nginx 将 `/api/langgraph/*` 路由到 Gateway，然后 Gateway 用自己的 Runtime 处理，无需外部 LangGraph Server。

## langgraph.json — Agent 注册中心

```json
{
  "graphs": {
    "lead_agent": "deerflow.agents:make_lead_agent"
  },
  "auth": {
    "path": "./app/gateway/langgraph_auth.py:auth"
  },
  "checkpointer": {
    "path": "./packages/harness/deerflow/runtime/checkpointer/async_provider.py:make_checkpointer"
  }
}
```

三件事：
- **graph 注册**：`lead_agent` 是唯一图，工厂函数 `make_lead_agent`
- **auth**：LangGraph 兼容的认证层，复用 Gateway 用户体系
- **checkpointer**：异步 checkpointer，支持 memory/sqlite/postgres

## 组件关系

```
Frontend ──(LangGraph SDK)──► Gateway API ──► Lead Agent
                                               │
                          ┌─────────────────────┼─────────────────────┐
                          │        │           │          │          │
                     Sandbox   Subagents    Memory     Skills      Tools
                          │        │           │          │          │
                     Local/AIO  general-   memory.json  SKILL.md  MCP/builtins
                                purpose
                                /bash
```

## 目录结构映射

```
deer-flow/
├── config.yaml              # 主配置
├── extensions_config.json   # MCP + Skills 启停状态
├── skills/{public,custom}/  # Skill 定义
│
├── backend/
│   ├── langgraph.json       # Agent 注册
│   ├── packages/harness/deerflow/   # ← Harness 层
│   │   ├── agents/          # Lead agent + middlewares + memory
│   │   ├── runtime/         # RunManager + checkpointer + stream bridge
│   │   ├── sandbox/         # 沙箱抽象 + local 实现
│   │   ├── subagents/       # 子 Agent 系统
│   │   ├── tools/           # 工具装配 + builtins
│   │   ├── models/          # 模型工厂
│   │   ├── mcp/             # MCP 集成
│   │   ├── skills/          # Skill 加载
│   │   ├── config/          # 配置系统 (29 个文件)
│   │   ├── community/       # Tavily/Jina/Firecrawl/DDG/AioSandbox
│   │   ├── persistence/     # ORM + 数据库引擎
│   │   ├── guardrails/      # 工具鉴权
│   │   ├── tracing/         # LangSmith + Langfuse
│   │   ├── reflection/      # 动态加载
│   │   └── client.py        # DeerFlowClient
│   │
│   └── app/                 # ← App 层
│       ├── gateway/         # FastAPI + 15 routers + auth
│       └── channels/        # 7 个 IM 平台集成
│
└── frontend/
    └── src/
        ├── app/             # Next.js App Router pages
        ├── components/      # UI 组件（workspace/landing/ui）
        └── core/            # 业务逻辑（threads/api/settings/memory...）
```

## 技术栈

| 层 | 关键依赖 |
|----|----------|
| Agent 框架 | LangGraph >= 1.1.9, LangChain >= 1.2.15 |
| 模型 Provider | langchain-openai, langchain-anthropic, langchain-deepseek, langchain-google-genai |
| 沙箱 | agent-sandbox >= 0.0.19（AIO）, agent-client-protocol >= 0.4.0（ACP） |
| MCP | langchain-mcp-adapters >= 0.2.2 |
| 持久化 | SQLAlchemy 2.0 async, aiosqlite, alembic, duckdb |
| 可观测 | langfuse >= 3.4.1, LangSmith |
| API | FastAPI, uvicorn, sse-starlette |
| IM | lark-oapi, slack-sdk, python-telegram-bot, dingtalk-stream |
| 前端 | Next.js 16, React 19, Tailwind CSS 4, pnpm |
