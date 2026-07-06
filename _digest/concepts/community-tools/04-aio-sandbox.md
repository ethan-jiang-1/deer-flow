---
title: "AIO Sandbox：Docker/Apple Container/K3s 沙箱"
description: "`AioSandboxProvider` 是 Local sandbox 之外的容器化沙箱实现，提供真正的进程隔离。位于 `community/aio_sandbox/`。"
topics: [tools, community, external-integration]
---

# AIO Sandbox：Docker/Apple Container/K3s 沙箱

`AioSandboxProvider` 是 Local sandbox 之外的容器化沙箱实现，提供真正的进程隔离。位于 `community/aio_sandbox/`。

## 架构层级

```
┌──────────────────────────────────────────────────────────┐
│ AioSandboxProvider (aio_sandbox_provider.py)             │
│ ├─ Warm pool (released-but-running containers)           │
│ ├─ Idle eviction daemon (60s interval)                   │
│ ├─ Orphan reconciliation (process restart recovery)     │
│ └─ Cross-process container discovery                     │
├──────────────────────────────────────────────────────────┤
│ SandboxBackend (backend.py) — Abstract ABC              │
│ ├─ LocalContainerBackend (Docker/Apple Container)       │
│ └─ RemoteSandboxBackend (K3s Provisioner)               │
├──────────────────────────────────────────────────────────┤
│ AioSandbox (aio_sandbox.py) — HTTP client to container  │
│ └─ agent_sandbox Python package                          │
└──────────────────────────────────────────────────────────┘
```

## 容器运行时探测

`LocalContainerBackend._detect_runtime()`（`local_backend.py:215`）：

```
macOS?
├─ 尝试运行 container --version → Apple Container（macOS 优先）
└─ 失败 → Docker
其他平台？
└─ Docker
```

macOS 上自动优先使用 Apple Container（`container` CLI），fallback 到 Docker。

## 沙箱生命周期

```
1. ACQUIRE (ensure_sandbox_initialized)
   ├─ 检查 in-process cache (_sandboxes)
   ├─ 检查 warm pool (_warm_pool)
   ├─ 计算确定性 sandbox_id = sha256(thread_id)[:8]
   ├─ 跨进程文件锁 (fcntl.flock)
   ├─ Backend.discover(sandbox_id) — 检查是否已有同名容器在运行
   ├─ Backend.create(thread_id, sandbox_id, mounts)
   │   ├─ 分配空闲端口
   │   ├─ docker run --rm -d --security-opt seccomp=unconfined
   │   │          --name deer-flow-sandbox-{id} -p {port}:8080
   │   │          -v host:container {mounts} image
   │   └─ wait_for_sandbox_ready(url, timeout=60)
   └─ 注册到 _sandboxes, _thread_sandboxes, _last_activity

2. USE (每个 tool call)
   └─ AioSandbox HTTP client ↔ 容器内 agent_sandbox API
       ├─ shell.exec_command (threading.Lock 串行化)
       ├─ file.read_file / write_file / download_file
       ├─ file.find_files (glob) / search_in_file (grep)
       └─ file.list_path

3. RELEASE (after_agent)
   └─ 从 _sandboxes 移除 → 放入 warm pool
       (容器保持运行——下次 turn 快速 reclaim)

4. IDLE EVICTION (后台线程，60s 间隔)
   ├─ Active sandbox: 超过 idle_timeout (默认 600s) → destroy
   └─ Warm pool: 超过 idle_timeout → destroy

5. SHUTDOWN (atexit + SIGTERM/SIGINT/SIGHUP)
   └─ 销毁所有 active + warm pool 容器
```

## 确定性 Sandbox ID

```python
# aio_sandbox_provider.py:278
sandbox_id = hashlib.sha256(thread_id.encode()).hexdigest()[:8]
```

同一个 `thread_id` 在所有进程中产生相同的 `sandbox_id`。容器名称 = `{prefix}-{sandbox_id}`（如 `deer-flow-sandbox-a1b2c3d4`）。这使跨进程 discovery 成为可能——多 worker 部署中每个 worker 可以"发现"另一个 worker 创建的容器，而不需要共享状态。

## Warm Pool 设计

`release()` 不销毁容器——它把容器放入 warm pool：

```
Agent 第一次 turn → acquire → cold start (1-3s) → use → release → warm pool
Agent 第二次 turn → acquire → reclaim from warm pool (~0ms) → use → release → warm pool
Agent 空闲 10 分钟 → idle eviction → docker stop
```

这个设计基于 agent 的典型使用模式：用户连续发送多条消息，turn 之间有数秒到数分钟的间隔。Warm pool 避免了 Docker 的冷启动延迟（镜像已缓存时 1-3s，未缓存时更长）。

## 挂载体系

```
config.yaml mounts:
  /path/on/host → /home/user/shared (可配置)

thread mounts (自动):
  users/{user_id}/threads/{thread_id}/user-data/workspace → /mnt/user-data/workspace
  users/{user_id}/threads/{thread_id}/user-data/uploads   → /mnt/user-data/uploads
  users/{user_id}/threads/{thread_id}/user-data/outputs   → /mnt/user-data/outputs
  threads/{thread_id}/acp-workspace/                       → /mnt/acp-workspace

shared mounts (read-only):
  skills/public/ + skills/custom/                          → /mnt/skills
```

`uses_thread_data_mounts=True` 表示文件通过 bind mount 直接可见——gateway 写入的文件立即可被容器内 tool 访问，无需上传。

## K3s Provisioner 模式

当 `config.yaml` 设置 `sandbox.provisioner_url` 时，`RemoteSandboxBackend` 将所有操作委托给 provisioner HTTP API：

```
AioSandboxProvider
  └─ RemoteSandboxBackend
       ├─ POST   /api/sandboxes          → 创建 Pod + NodePort Service
       ├─ DELETE /api/sandboxes/{id}     → 删除 Pod + Service
       ├─ GET    /api/sandboxes/{id}     → 查询状态
       └─ GET    /api/sandboxes          → 列出所有

Provisioner (docker/provisioner/app.py)
  └─ namespace: deer-flow
     Pod: sandbox-{sandbox_id}
       ├─ image: all-in-one-sandbox
       ├─ CPU: 100m→1000m, Mem: 256Mi→1Gi
       ├─ privileged: false
       ├─ allow_privilege_escalation: true
       └─ readiness probe: /v1/sandbox (5s)
     Service: sandbox-{sandbox_id}-svc (NodePort)
```

K3s 模式提供了 Local/Docker 所没有的资源限制（CPU/Mem）和 Pod 级隔离，但注意 `allow_privilege_escalation: true` 允许 setuid 程序。

## 安全考量

| 维度 | Docker 模式 | K3s 模式 |
|------|-----------|---------|
| **seccomp** | `unconfined`（显式禁用，~300+ syscall 可用） | 默认 profile（~44 个高风险 syscall 过滤） |
| **提权** | Docker 默认 | `allow_privilege_escalation: true` |
| **网络出站** | 无限制 | 无 NetworkPolicy |
| **资源限制** | 无 CPU/Mem 限制 | 100m-1000m CPU, 256Mi-1Gi Mem |

### Docker seccomp=unconfined 的原因

`--security-opt seccomp=unconfined` 移除 Docker 默认的 seccomp profile（阻止 ~44 个高风险 syscall）。原因是某些 CLI 工具需要 `ptrace`、`mount` 等受限 syscall。这是一个安全权衡——如果不需要这些 syscall，可以在 Docker daemon 层重新启用默认 profile。

## 与 Local Sandbox 的关键差异

| 维度 | AIO Sandbox | Local Sandbox |
|------|-----------|-------------|
| **隔离** | 容器 namespace | 无（host 共享） |
| **工具执行** | HTTP API → 容器内 agent_sandbox | `subprocess.run()` 在 host |
| **allow_host_bash** | 总是 True（不是在 host 上） | 默认 False |
| **release()** | 放入 warm pool（容器保活） | no-op（实例留在 LRU cache） |
| **跨进程共享** | 确定性命名 + Docker discovery | 不支持 |
| **uses_thread_data_mounts** | True (LocalContainerBackend) | True |
