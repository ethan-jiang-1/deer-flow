---
title: "Nginx 路由 + K3s Provisioner"
description: "## Nginx 路由规则"
topics: [deployment, docker, kubernetes]
---

# Nginx 路由 + K3s Provisioner

## Nginx 路由规则

生产的 Nginx 配置负责将请求路由到 Gatewat 和 LangGraph Server：

### SSE 流的关键配置

```nginx
location /api/ {
    proxy_pass http://gateway:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;

    # 文件上传
    client_max_body_size 100m;
}

location /api/langgraph/ {
    proxy_pass http://langgraph:8123;

    # SSE 流式响应 — 必须禁用缓冲
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;    # Agent 执行可超过 60s
    proxy_send_timeout 600s;

    # 长连接
    proxy_http_version 1.1;
    proxy_set_header Connection '';
}
```

### 为什么 `proxy_buffering off` 是必需的

SSE（Server-Sent Events）逐 chunk 推送数据。Nginx 默认开启 `proxy_buffering` 时，会先收集上游响应到缓冲区，再一次性发给客户端——导致：
- 前端收不到增量更新（全部缓存后一起发送）
- `Last-Event-ID` 重连机制失效
- 超时 disconnect（Nginx 认为上游"没有响应"）

### Rate Limiting

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

location /api/auth/login {
    limit_req zone=login burst=3 nodelay;  # 登录限流
}

location /api/ {
    limit_req zone=api burst=20 nodelay;    # 通用 API 限流
}
```

## K3s Provisioner 模式

生产多租户环境使用 K3s Provisioner，每个 Agent thread 获得独立 Pod：

### 架构

```
                          ┌──────────────────┐
                          │   K3s Cluster     │
┌─────────┐   ┌─────────┐ │  ┌────────────┐  │
│  Nginx  │→  │ Gateway │→│  │ Provisioner│  │
│ (:2026) │   │ (:8000) │ │  │  (:8002)   │  │
└─────────┘   └─────────┘ │  └────────────┘  │
                          │        │         │
                          │        ▼         │
                          │  ┌────────────┐  │
                          │  │ sandbox-abc│  │
                          │  │ (Pod)      │  │
                          │  ├────────────┤  │
                          │  │ sandbox-def│  │
                          │  │ (Pod)      │  │
                          │  ├────────────┤  │
                          │  │ ...        │  │
                          │  └────────────┘  │
                          └──────────────────┘
```

### Provisioner API

`docker/provisioner/app.py` — FastAPI 服务：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/sandboxes` | POST | 创建 Pod + NodePort Service |
| `/api/sandboxes` | GET | 列出所有 sandbox |
| `/api/sandboxes/{id}` | GET | 查询 sandbox 状态 |
| `/api/sandboxes/{id}` | DELETE | 删除 Pod + Service |

### Pod Spec

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sandbox-{sandbox_id}
  namespace: deer-flow
spec:
  containers:
  - name: sandbox
    image: all-in-one-sandbox:latest
    ports:
    - containerPort: 8080
    resources:
      requests: { cpu: 100m, memory: 256Mi }
      limits: { cpu: 1000m, memory: 1Gi, ephemeral-storage: 500Mi }
    securityContext:
      privileged: false
      allowPrivilegeEscalation: true
    readinessProbe:
      httpGet: { path: /v1/sandbox, port: 8080 }
      initialDelaySeconds: 5
      periodSeconds: 5
    livenessProbe:
      httpGet: { path: /v1/sandbox, port: 8080 }
      initialDelaySeconds: 10
      periodSeconds: 10
    volumeMounts:
    - name: user-data
      mountPath: /mnt/user-data
      subPath: {user_id}/{thread_id}/
    - name: skills
      mountPath: /mnt/skills
      readOnly: true
---
apiVersion: v1
kind: Service
metadata:
  name: sandbox-{sandbox_id}-svc
  namespace: deer-flow
spec:
  type: ClusterIP          # 🆕 2.1 默认 ClusterIP（旧版 NodePort）
  ports:
  - port: 8080
```

> ⚠️ **2.1 变更**：sandbox Service 默认从 `NodePort` 改为 `ClusterIP`——sandbox 仅集群内可达（`http://sandbox-<id>-svc.<ns>.svc.cluster.local`）。如需保留旧行为（外部可达），设 `provisioner.sandboxServiceType: NodePort` + `provisioner.nodeHost`。现有 chart 升级时自动 flip NodePort→ClusterIP。

### Gateway→Sandbox 通信

Gateway 通过 `DEER_FLOW_SANDBOX_HOST` 环境变量连接 sandbox：
- LocalContainerBackend: `DEER_FLOW_SANDBOX_HOST=host.docker.internal`
- RemoteSandboxBackend (K3s): sandbox URL = K3s Service DNS（ClusterIP 模式）或 Node IP + NodePort（NodePort 模式）

### K3s 部署 Checklist

- [ ] 安装 K3s 集群 + 配置 kubeconfig
- [ ] 构建/推送 `all-in-one-sandbox` 镜像到集群可访问的 registry
- [ ] 配置 `sandbox.provisioner_url` → Provisioner 服务地址
- [ ] 配置 RBAC：Provisioner 需要 pods + services 的 CRUD 权限
- [ ] 配置 NetworkPolicy：限制 sandbox Pod 的出站流量
- [ ] 评估 `allowPrivilegeEscalation: true` 是否必要
- [ ] 配置 `DEER_FLOW_INTERNAL_AUTH_TOKEN`（多 worker 必须手动设置）
- [ ] PostgreSQL 高可用（外部 Postgres 或 Cloud SQL）

## 🆕 First-Class Helm Chart

2.1 引入了正式的 Helm chart（`deer-flow/`），支持 Kubernetes 一键部署：

- **Chart 发布**：GitHub Container Registry `charts/` namespace prefix
- **Sandbox Service**：默认 `ClusterIP`（仅集群内可达），可选 `NodePort`
- **Provisioner**：ClusterIP Services + scoped per-skill PVC mounts + 可配置 sandbox container port
- **Gateway**：Helm chart 中配置 `terminationGracePeriodSeconds`（需大于 `shutdown_flush_timeout_seconds`）

## 🆕 同步 #6（v2.1.0-rc0）中的 nginx / Helm 变更

### nginx 60s 模型请求超时修复（#5505）

`/api/threads` 下 model-bound 端点会把响应挂起等模型：`/compact`、`/suggestions` 等一次模型调用，`/runs/wait` 等整个 run。nginx 默认 60s `proxy_read_timeout` 会在工作中途 504（compaction 实际仍会 commit，被 wait 的 run 则被取消）。修复在 `docker/nginx/nginx.conf`、`docker/nginx/nginx.local.conf` 和 Helm `configmap-nginx.yaml` 三处同步：

```nginx
location /api/threads {
    ...
    proxy_read_timeout 600s;   # 🆕 默认 60s 会 504 model-bound 请求
}
```

同一批变更还新增了本地 `.skill` 归档上传的专用 location（`/api/skills/install/upload`，admin-only）：`client_max_body_size 101M` + `proxy_request_buffering off` + `proxy_read_timeout 600s`（skill 校验会串行跑多次 LLM 调用）。

### Helm chart 同步变更（`deploy/helm/deer-flow/`）

- **`templates/configmap-nginx.yaml`**：与上面 nginx.conf 相同的两处 location（600s 线程读超时 + 101M skill 上传）。
- **`templates/gateway-deployment.yaml`**：readinessProbe 从 `/health` 改为 `/health/ready`（一个端点 3s deadline 内并发跑两个探针），`timeoutSeconds: 5` 必须大于该 3s 端点 bound，否则 K8s 以 1s 默认值掐掉慢但健康的响应。
- **`values.yaml`**：默认 `ingress.annotations` 不再为空——`proxy-body-size: 101m`、`proxy-request-buffering: off`、`proxy-read-timeout: 600`，与 skill 上传/长请求对齐；内嵌 `config:` 示例升到 `config_version: 45` 并补 `recursion_limit` / LightRAG 检索示例。若自定义 `ingress.annotations`，需保留等价的 size/streaming/timeout 设置。
- **CI 校验**：`.github/workflows/chart.yaml` 新增 `scripts/check_chart_skill_upload_size.sh` 步骤，防止渲染出的 Ingress 与 Gateway 上传要求漂移。

### Compose 健康检查同步

`docker/docker-compose.yaml` 的 gateway healthcheck 也从 `/health`（timeout=3）改为 `/health/ready`（timeout=5，须高于端点 3s deadline）。

