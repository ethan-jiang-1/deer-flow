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
  type: NodePort
  ports:
  - port: 8080
```

### Gateway→Sandbox 通信

Gateway 通过 `DEER_FLOW_SANDBOX_HOST` 环境变量连接 sandbox：
- LocalContainerBackend: `DEER_FLOW_SANDBOX_HOST=host.docker.internal`
- RemoteSandboxBackend (K3s): sandbox URL = K3s Node IP + NodePort

### K3s 部署 Checklist

- [ ] 安装 K3s 集群 + 配置 kubeconfig
- [ ] 构建/推送 `all-in-one-sandbox` 镜像到集群可访问的 registry
- [ ] 配置 `sandbox.provisioner_url` → Provisioner 服务地址
- [ ] 配置 RBAC：Provisioner 需要 pods + services 的 CRUD 权限
- [ ] 配置 NetworkPolicy：限制 sandbox Pod 的出站流量
- [ ] 评估 `allowPrivilegeEscalation: true` 是否必要
- [ ] 配置 `DEER_FLOW_INTERNAL_AUTH_TOKEN`（多 worker 必须手动设置）
- [ ] PostgreSQL 高可用（外部 Postgres 或 Cloud SQL）
