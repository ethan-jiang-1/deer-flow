---
title: "本地开发：make dev"
description: "`make dev` 启动 4 个独立进程，用于个人开发环境。"
topics: [setup, configuration, quickstart]
---

# 本地开发：make dev

`make dev` 启动 4 个独立进程，用于个人开发环境。

## 进程拓扑

```
make dev
  ├─ uvicorn backend.gateway:app
  │     --host 0.0.0.0 --port 2026 --reload
  │     Watches: backend/app/gateway/
  │
  ├─ langgraph dev
  │     --port 8123
  │     Watches: backend/packages/harness/
  │
  ├─ pnpm dev (frontend/)
  │     Turbopack --port 3000
  │     HMR: React components + styles
  │
  └─ (optional) AIO sandbox containers
        docker run ... all-in-one-sandbox
```

## 本地开发特点

- **Hot Reload：** Gateway（uvicorn `--reload`）、LangGraph（`langgraph dev` 内置）、Frontend（Turbopack HMR）——三人热重载
- **Local Sandbox：** 默认使用 `LocalSandboxProvider`——所有 bash/文件操作在 host 上执行，通过虚拟路径映射隔离
- **SQLite：** 单文件数据库，路径 `.deer-flow/data/`
- **No Auth：** 默认关闭认证（`DEER_FLOW_AUTH_ENABLED=false`），`user_id = "default"`
- **Memory Stream Bridge：** 单进程内存 pub/sub，无需 Redis

## 前置条件

```bash
# Python 3.12+
uv sync --group dev

# Node.js 22+
pnpm install

# config.yaml
make config    # 从 config.example.yaml 生成

# 启动
make dev
```

## 访问地址

| 服务 | URL |
|------|-----|
| Gateway API | `http://localhost:2026/api/` |
| API Docs | `http://localhost:2026/docs` |
| LangGraph Server | `http://localhost:8123` |
| Frontend | `http://localhost:3000` |
| Health Check | `http://localhost:2026/health` |

## 常见问题

- **config_version mismatch：** 上游更新了配置 schema → 运行 `make config-upgrade` 合并新字段
- **LangGraph 连接失败：** 确认 `langgraph dev` 在运行 → 检查 `langgraph.json` 中的 graph 注册
- **Frontend 白屏：** 检查 `NEXT_PUBLIC_LANGGRAPH_BASE_URL`（默认 `/api/langgraph`，通过 nginx proxy 到 LangGraph）
- **Import 错误：** 运行 `uv sync` 重新安装依赖——harness 包通过 editable install 挂在虚拟环境中
