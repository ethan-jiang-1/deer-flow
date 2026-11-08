---
title: "自定义 Sandbox 镜像"
description: "如何构建和使用自定义 Docker sandbox 镜像：预装额外包、配置 image 字段、运行时 pip install、BoxLite 自定义。"
topics: [sandbox, docker, deployment, customization]
---

# 自定义 Sandbox 镜像

## 最简单方案：运行时安装

如果只是想要 pandas/numpy 等 Python 包，让 agent 在运行时安装——不需要构建镜像：

```python
client.chat("pip install pandas numpy && python -c 'import pandas; print(pandas.__version__)'")
```

AIO sandbox（Docker）有网络访问，bash 工具可以直接 `pip install`。缺点是每次新 sandbox 都要重新装。使用 warm pool（`replicas: 3`）可以跨 turn 保持安装状态。

## AIO Docker 镜像

AIO sandbox 使用 `agent-sandbox` 库与容器通信。配置中 `image` 字段指定镜像：

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  image: your-registry.com/deer-flow-custom:latest
  port: 8080
  replicas: 3
```

默认镜像：`enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest`

## 构建自定义镜像

继承官方镜像，添加额外包：

```dockerfile
FROM enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
RUN pip install pandas numpy scipy matplotlib
```

构建并推送：
```bash
docker build -t your-registry.com/deer-flow-custom:latest .
docker push your-registry.com/deer-flow-custom:latest
```

**镜像要求**：基于 `all-in-one-sandbox`（保留其 HTTP API、shell、git 等内置工具）。`agent-sandbox` 库通过 HTTP API（端口 8080）管理容器生命周期。不改变 API 接口即可兼容。

## BoxLite 自定义

BoxLite（micro-VM）也支持自定义镜像：

```yaml
sandbox:
  use: deerflow.community.boxlite:BoxliteProvider
  image: python:3.12-slim
  replicas: 3
  idle_timeout: 600
```

可以使用任何安装了 Python 3.12+ 的 Docker 镜像。

## warm pool 注意事项

- AIO/BoxLite 均使用 warm pool（`replicas: N`），释放的 sandbox 保持存活供下次使用
- 如果在镜像中安装了包，warm pool 会保留安装状态
- 运行时 `pip install` 也会被 warm pool 保留，直到超过 `idle_timeout`（默认 600s）

## 调试

如果镜像不工作：
- 确认镜像继承了 `all-in-one-sandbox` 且 HTTP API（:8080）正常
- 检查 Gateway 日志中的 sandbox 启动/健康检查消息
- 使用 `docker logs` 查看 sandbox 容器输出

源码：`deerflow/community/aio_sandbox/`，`deerflow/community/boxlite/`
