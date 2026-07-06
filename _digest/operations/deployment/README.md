---
title: "Deployment — 部署架构"
description: "DeerFlow 支持 4 种部署模式：本地开发（`make dev`）、Docker 开发（`make docker-start`）、Docker 生产（`make up`）、K8s（Provisioner）。"
type: index
---

# Deployment — 部署架构

DeerFlow 支持 4 种部署模式：本地开发（`make dev`）、Docker 开发（`make docker-start`）、Docker 生产（`make up`）、K8s（Provisioner）。

## 文件索引

| 文件 | 内容 |
|------|------|
| `00-overview.md` | 全景：4 种部署模式对比矩阵、进程拓扑图、选型决策树 |
| `01-docker.md` | Docker Compose 结构：5 服务拓扑、网络配置、DooD 模式、生产检查清单 |
| `02-nginx-and-k8s.md` | Nginx SSE 配置（proxy_buffering off）、速率限制、K3s Provisioner Pod 规格、RBAC |

## 关键问题

- 4 种模式各适合什么场景？→ `00-overview.md` 对比矩阵
- Docker 里 Gateway 怎么通过 DooD 启动沙箱容器？→ `01-docker.md`
- Nginx 的路由规则怎么设计的？→ `02-nginx-and-k8s.md`
- 本地开发 `make dev` 的进程拓扑？→ `_digest/getting-started/04-local-dev.md`

## 源文件索引

| 组件 | 路径 |
|------|------|
| Docker Compose (dev) | `docker/compose.dev.yaml` |
| Docker Compose (prod) | `docker/compose.yaml` |
| Nginx 配置 | `docker/nginx/nginx.conf` |
| Provisioner | `docker/provisioner/` |
| Makefile | `Makefile` |
| Gateway 启动 | `backend/app/gateway/app.py:lifespan()` |
