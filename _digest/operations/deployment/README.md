# Deployment — 部署架构

DeerFlow 支持 4 种部署模式：本地开发（`make dev`）、Docker 开发（`make docker-start`）、Docker 生产（`make up`）、K8s（Provisioner）。每种模式的进程拓扑、网络配置、热加载行为都不同。

**回答的核心问题**：4 种部署模式的进程拓扑有什么区别？Nginx 怎么路由？环境变量怎么跨服务传递？Provisioner 在 K8s 模式下做什么？

> **约束：不修改项目源代码。** 本 `_digest/` 下所有内容仅作研究记录。详见 [根 README](../README.md)。

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：4 种部署模式对比矩阵、进程拓扑图、选型决策树 |
| **01-local-dev.md** | `make dev` 深入：uvicorn hot reload、Next.js Turbopack、多进程管理 |
| **02-docker-deployment.md** | Docker Compose 结构：4 服务拓扑、网络配置、volume 挂载、DooD 模式 |
| **03-nginx-routing.md** | Nginx 配置详解：路由规则、CORS 策略、SSE 长连接配置 |
| **04-k8s-provisioner.md** | Provisioner 模式（port 8002）：K3s Pod 生命周期、沙箱调度 |

## 关键问题

- 4 种模式各适合什么场景？→ `00-overview.md` 对比矩阵
- `make dev` 的三个进程怎么协调启动？→ `01-local-dev.md`
- Docker 里 Gateway 怎么通过 DooD 启动沙箱容器？→ `02-docker-deployment.md`
- Nginx 的 7 条路由规则怎么设计的？→ `03-nginx-routing.md`
- Provisioner 怎么管理 K3s Pod 生命周期？→ `04-k8s-provisioner.md`

## 源文件索引

| 组件 | 路径 |
|------|------|
| Docker Compose (dev) | `docker/compose.dev.yaml` |
| Docker Compose (prod) | `docker/compose.yaml` |
| Nginx 配置 | `docker/nginx/nginx.conf` |
| Provisioner | `docker/provisioner/` |
| Makefile | `Makefile` |
| 环境变量模板 | `.env.example` |
| Gateway 启动 | `backend/app/gateway/app.py:lifespan()` |
