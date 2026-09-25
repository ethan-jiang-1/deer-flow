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
│ ├─ Cross-process container discovery                     │
│ └─ Cross-instance ownership store (ownership/, #4206) 🆕 │
│       ├─ memory | redis 租约存储（factory.py 解析）       │
│       └─ 心跳续租 + 孤儿收养（claim() 而非 take()）      │
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
   ├─ 计算确定性 sandbox_id = sha256(user_id:thread_id)[:16]
   ├─ 发布 ownership（take() 转移归属，acquire 路径无条件）
   ├─ Backend.discover(sandbox_id) — 检查是否已有同名容器在运行
   ├─ Backend.create(thread_id, sandbox_id, mounts)
   │   ├─ 分配空闲端口
   │   ├─ docker run --rm -d --security-opt seccomp=unconfined
   │   │          --name deer-flow-sandbox-{id} -p {port}:8080
   │   │          -v host:container {mounts} image
   │   └─ wait_for_sandbox_ready(url, timeout=60)
   └─ 注册到 _sandboxes, _thread_sandboxes, _last_activity
       （多实例时 ownership 发布/回收在后台线程离 loop 刷新）

2. USE (每个 tool call)
   └─ AioSandbox HTTP client ↔ 容器内 agent_sandbox API
       ├─ shell.exec_command (threading.Lock 串行化)
       ├─ file.read_file / write_file / download_file
       ├─ file.find_files (glob) / search_in_file (grep)
       └─ file.list_path

3. RELEASE (after_agent)
   └─ 从 _sandboxes 移除 → 放入 warm pool
       (容器保持运行——下次 turn 快速 reclaim)

4. IDLE EVICTION (后台线程，60s 间隔) 🆕 委托给共享 WarmPoolLifecycleMixin
   ├─ Active sandbox: 超过 idle_timeout (默认 600s) → destroy（provider 内）
   └─ Warm pool: 超过 idle_timeout → destroy（mixin 统一）
       （租约续期独立于 idle checker——idle_timeout: 0 时租约仍续）

5. SHUTDOWN (atexit + SIGTERM/SIGINT/SIGHUP)
   └─ 销毁所有 active + warm pool 容器（仅销毁本实例持有租约的 ID）
```

## 确定性 Sandbox ID

```python
# aio_sandbox_provider.py:757（sync #4 重构）
sandbox_id = hashlib.sha256(f"{user_id}:{thread_id}".encode()).hexdigest()[:16]
```

**sync #4 变更**：从 `sha256(thread_id)[:8]`（8 字符）改为 `sha256(user_id:thread_id)[:16]`（16 字符）。包含 `user_id` 防止 default-bucket 沙箱被 auth/channel run（应挂 user-scoped bucket）复用。混合版本 rollout 期间旧 8 字符容器不按新 16 字符身份复用——它们正常走孤儿清理，首次新版本 acquire 冷启动。

同一个 `(user_id, thread_id)` 在所有进程中产生相同的 `sandbox_id`。容器名称 = `{prefix}-{sandbox_id}`（如 `deer-flow-sandbox-a1b2c3d4`）。这使跨进程 discovery 成为可能——多 worker 部署中每个 worker 可以"发现"另一个 worker 创建的容器。跨进程协调现在由 **ownership store** 负责（见下），不再是文件锁。

## Warm Pool 设计

`release()` 不销毁容器——它把容器放入 warm pool：

```
Agent 第一次 turn → acquire → cold start (1-3s) → use → release → warm pool
Agent 第二次 turn → acquire → reclaim from warm pool (~0ms) → use → release → warm pool
Agent 空闲 10 分钟 → idle eviction → docker stop
```

这个设计基于 agent 的典型使用模式：用户连续发送多条消息，turn 之间有数秒到数分钟的间隔。Warm pool 避免了 Docker 的冷启动延迟（镜像已缓存时 1-3s，未缓存时更长）。

## 跨实例 Ownership Store（sync #4，issue #4206）🆕

多 Gateway 实例共享同一容器后端时，用可插拔租约存储协调容器归属（`aio_sandbox/ownership/`，`sandbox.ownership.type: memory | redis`）。**逐沙箱 `fcntl.flock` 守卫已被它替代并删除**——旧文件锁只覆盖同主机，Redis 让协调真正跨实例。

核心语义（完整设计见 [six-impls.md](../sandbox/abstract-interface-and-seven-impls.md) 的 Ownership 节）：

| 概念 | 说明 |
|------|------|
| `take()` vs `claim()` | `take()` = acquire 路径**无条件**转移归属（同一 thread 下一 turn 可能落到另一实例）；`claim()` = adopt/reap 路径，仅当无主或已归自己 |
| `own:` vs `del:` 双状态 | `del:` 标记正在销毁的容器；`take()` 对 `del:` 拒绝，关闭"检查→停止"竞态窗口 |
| `renew()` LAPSED vs LOST | LAPSED=租约缺失重新建立；LOST=被 peer 持有放弃——防止 Redis 重启丢 key 后全集群驱逐 |
| fail-closed 双向 | 发布失败→沙箱不发放（刚建的容器销毁而非泄漏）；reap 时 store 不可答→视为 peer-owned，绝不把活容器当孤儿 |

**租约续期独立于 idle checker**：`_start_lease_renewal` 是独立 daemon 线程（TTL = `renewal_interval_seconds × ttl_multiplier`）——`idle_timeout: 0`（"保持 warm VM 直到 shutdown"，文档化配置）时旧代码让所有租约过期，现在不会。Redis 自动推断：`stream_bridge` 已是 redis 时 ownership 也推断为 redis（多实例部署的既有配置零改动）。

## 孤儿回收（orphan reconciliation）🆕

provider 启动时 + AIO 定期 `_cleanup_idle_resources` 调 `_reconcile_orphans()`：分页列出容器 → 对每个运行中的容器查 ownership store → **无主且 grace 已过** → `claim()` 成功后 adopt 入 warm pool。对账用 `claim()` 而非 `take()`——无主容器不会被销毁，只会被收养。测试 `test_sandbox_orphan_reconciliation.py`（3028 行 / 90 个 test 函数，v2.1.0 实测）覆盖 store 故障 fail-closed、grace 重置、LAPSED vs LOST、Redis 状态丢失恢复等。

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
| **跨进程共享** | 确定性命名 + Docker discovery + **ownership store**（redis） | 不支持 |
| **uses_thread_data_mounts** | True (LocalContainerBackend) | True |

## 相关

- Ownership store 完整设计（`own:`/`del:` 租约、renew 语义、孤儿对账）→ [concepts/sandbox/abstract-interface-and-seven-impls.md](../sandbox/abstract-interface-and-seven-impls.md)
- 7 种沙箱实现对比 → [concepts/sandbox/abstract-interface-and-seven-impls.md](../sandbox/abstract-interface-and-seven-impls.md)
- 沙箱安全隔离（seccomp/提权/网络）→ [operations/security/02-sandbox-isolation.md](../../operations/security/02-sandbox-isolation.md)
