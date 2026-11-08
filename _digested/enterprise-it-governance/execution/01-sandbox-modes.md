---
title: "七种沙箱模式"
description: "从 Local 路径映射到 K8s Provisioner，三种隔离级别。"
topics: [governance, execution]
---

# 七种沙箱模式

从 Local 路径映射到 K8s Provisioner，三种隔离级别。

## 七种沙箱模式

| 模式 | `sandbox.use` | 隔离级别 | 适用场景 |
|------|--------------|---------|---------|
| **Local** | `deerflow.sandbox.local:LocalSandboxProvider` | 无进程隔离，共享 host 内核 | 个人开发、信任环境 |
| **Docker (AioSandbox)** | `deerflow.community.aio_sandbox:AioSandboxProvider` | 容器隔离 | 团队部署 |
| **K3s (Provisioner)** | 同 `AioSandboxProvider` + `sandbox.config.provisioner_url`（`aio_sandbox_provider.py:257-269` 据此选用 `RemoteSandboxBackend`，不是独立 provider 类） | Pod 隔离 | 多租户、高安全需求 |
| **BoxLite** | `deerflow.community.boxlite:BoxliteProvider` | Micro-VM（自有内核） | 单机强隔离、OCI 镜像 |
| **E2B** | `deerflow.community.e2b_sandbox:E2BSandboxProvider` | 云端远程沙箱 | 免运维、弹性 |
| **Tenki** | `deerflow.community.tenki:TenkiSandboxProvider` | 云端 Micro-VM | 免运维、强隔离 |
| **OpenSandbox** | `deerflow.community.opensandbox:OpenSandboxProvider` | 云端远程沙箱 | 免运维、可自托管域 |

> 表中 7 行对应 7 种运行模式，但只有 6 个 provider 类——Provisioner 是 AIO provider 配置 `provisioner_url` 后的一种模式。详见 [concepts/sandbox/abstract-interface-and-seven-impls.md](../../concepts/sandbox/abstract-interface-and-seven-impls.md)。

### 七种模式归入三档

![三种隔离级别](figures/sandbox-modes-compare.svg)

图中的 Local / Provisioner / Remote 三档是按**隔离边界画在哪一层**归类：
进程内、容器/命名空间、网络之外。七种 provider 都落在这三档里。

**Local 模式的默认行为与特殊风险：**

`sandbox.allow_host_bash` 默认 **`false`**（`config.example.yaml:1720`）。
框架自己的注释写得比任何二手描述都直接（`config.example.yaml:1717-1719`）：

> Host bash execution is disabled by default because LocalSandboxProvider is
> **not a secure isolation boundary for shell access**. Enable only for fully
> trusted, single-user local workflows.

所以 Local 模式下 bash **默认不执行**。一旦把它打开，agent 的命令就**直接在 host 上跑**，
隔离只能依赖虚拟路径翻译——路径翻译若出 bug，agent 就能碰到系统文件。

**审计视角的含义**：`allow_host_bash: true` 是一个需要单独的评审动作的开关，
不是「顺手打开让 agent 好用点」的配置项。

