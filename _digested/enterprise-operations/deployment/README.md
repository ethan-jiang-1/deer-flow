---
title: "Deployment — 部署架构"
description: "DeerFlow 支持 4 种部署模式：本地开发（`make dev`）、Docker 开发（`make docker-start`）、Docker 生产（`make up`）、K8s（Provisioner）。"
type: index
topics: [deployment, docker, nginx, k8s]
---

# Deployment — 部署架构

> **定位**：从个人开发机到生产多租户的 4 种部署模式：对比矩阵、进程拓扑、选型决策树，以及 Docker Compose / Nginx / K3s Provisioner 的落地细节。给负责环境搭建与上线的平台工程师看。
> **边界**：认证加固与信任边界见 [security/](../security/README.md)；集成方式的取舍见 [integration/](../integration/README.md)。

## 阅读路径

1. **先看**：[00-overview.md](00-overview.md) — 4 种模式对比矩阵、进程拓扑与选型决策树。
2. **再看**：[01-docker.md](01-docker.md) — 5 服务拓扑、网络配置、DooD 模式与生产检查清单。
3. **深入**：[02-nginx-and-k8s.md](02-nginx-and-k8s.md) — SSE 的 `proxy_buffering off`、速率限制、Provisioner Pod 规格与 RBAC。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [00-overview.md](00-overview.md) | 4 种部署模式对比与选型 | 概览 |
| [01-docker.md](01-docker.md) | Docker Compose：5 服务、网络、DooD、上线清单 | 深入 |
| [02-nginx-and-k8s.md](02-nginx-and-k8s.md) | Nginx 路由/SSE/限速 + K3s Provisioner | 深入 |
| [03-custom-sandbox-image.md](03-custom-sandbox-image.md) | 自定义 Sandbox 镜像：预装包、image 字段、运行时 pip install | 深入 |
| [04-multi-instance.md](04-multi-instance.md) | 多实例前置、启动门、Redis stream bridge、频道 leader lease 与 ExecutionFence | 深入 |

## 宪章与约定

- 本目录无独立宪章；写作纪律沿用 [根 README](../../README.md)。
- 结构以 `docker/`、`Makefile` 与 Gateway `app.py` 为准，机制描述附 `file:line`。

## 相关目录

- [Enterprise Operations 总览](../README.md) — 部署、通道、API 与运维全景。
- [安全与信任边界](../security/README.md) — 部署之后的加固与信任链。
- [Integration](../integration/README.md) — Docker 之外的接入方式。
- [App Layer](../app-layer/README.md) — Gateway 的 lifespan 与端口。
- [根 README](../../README.md) — 全库阅读地图与 README 约定。
- [企业 IT 治理卷](../../enterprise-it-governance/README.md) — 部署之后的控制点判断。
