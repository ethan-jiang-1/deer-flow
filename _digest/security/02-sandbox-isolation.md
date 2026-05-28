# 沙箱隔离

三种沙箱提供三种完全不同的隔离级别。Local 不是沙箱 — 是路径映射。

## 三维度对比

| 维度 | Local | Docker (AIO) | K3s (Provisioner) |
|------|-------|-------------|-------------------|
| **进程隔离** | 无 — `subprocess.run()` 直接在 host | Docker namespace | K8s Pod namespace |
| **文件隔离** | 路径映射 + `..` 遍历检查 | 容器 FS + bind mounts | 容器 FS + volumes |
| **Shell 执行** | `allow_host_bash` 控制 | 完全允许 | 完全允许 |
| **CPU 限制** | 无 | 无 | 100m req / 1000m limit |
| **内存限制** | 无 | 无 | 256Mi req / 1Gi limit |
| **存储限制** | 无 | 无 | 500Mi ephemeral-storage |
| **seccomp** | host 默认 | **`unconfined`（显式禁用）** | host 默认 |
| **特权模式** | N/A（已是 host） | 非特权 | `privileged: false` |
| **setuid** | N/A | Docker 默认 | **`allowPrivilegeEscalation: true`** |
| **网络出站** | 全通 | 全通（无限制） | 全通（无 NetworkPolicy） |
| **AppArmor/SELinux** | 无 | 无 | 无 |
| **只读 rootfs** | N/A | 未配置 | 未配置 |
| **no-new-privileges** | N/A | 未配置 | 未配置 |

---

## LocalSandbox — 零隔离

`deerflow/sandbox/local/local_sandbox.py:311` — `execute_command()` 就是 `subprocess.run()`，在 host 进程所在的操作系统和用户权限下直接执行。

### `allow_host_bash: false`（默认）

bash tool 直接返回错误，不执行任何命令。但 file 操作（read_file, write_file, ls, glob, grep）仍正常工作 — 在 host 文件系统上，通过路径映射限制在 thread 专属目录。

```python
# tools.py:1344
if not is_host_bash_allowed():
    return "Host bash execution is disabled for LocalSandboxProvider..."
```

### `allow_host_bash: true`

解锁完整 Shell。但 `validate_local_bash_command_paths()` 做了一层 **best-effort** 正则验证（`tools.py:930`），只允许 `/bin/`、`/usr/bin/`、虚拟路径等前缀。代码自己声明了：*"not a secure sandbox boundary"*。

---

## AioSandbox (Docker) — 容器隔离

`deerflow/community/aio_sandbox/` — 通过 `agent-sandbox` 库管理 Docker 容器，所有操作经容器内 HTTP API。

### Docker-out-of-Docker

Gateway 容器本身在 Docker 里时，通过挂载 host 的 `/var/run/docker.sock` 来创建沙箱容器：

```
Gateway 容器 → docker.sock → Host Docker Daemon → 沙箱容器
```

### 关键安全设置

`local_backend.py:508` — 容器启动参数：

```
docker run --rm -d -p <port>:8080 --security-opt seccomp=unconfined ...
```

**seccomp=unconfined 是最大的安全妥协。** Docker 默认的 seccomp profile 禁用了约 44 个系统调用（包括很多内核漏洞利用常用的）。显式设为 unconfined 是为了 AIO sandbox 功能完整性，但显著扩大了内核攻击面。

### LRU 淘汰 + 空闲回收

- `replicas: 3` soft cap — 活跃容器不杀，超出后最久未用的被 evict
- 空闲 600s 后容器被回收
- 后台线程每 60s 检查一次

---

## K3s (Provisioner) — 生产级

`docker/provisioner/app.py` — 独立的 FastAPI 服务，通过 K8s API 为每个 sandbox 创建 Pod + NodePort Service。

### 资源限制

```yaml
resources:
  requests:  {cpu: 100m, memory: 256Mi, ephemeral-storage: 500Mi}
  limits:    {cpu: 1000m, memory: 1Gi, ephemeral-storage: 500Mi}
```

这是唯一有资源限制的模式，适合生产。

### 安全缺口

```yaml
securityContext:
  privileged: false
  allowPrivilegeEscalation: true   # ← setuid 程序可用
```

未配置 `no-new-privileges`、`readOnlyRootFilesystem`、NetworkPolicy。

---

## 6 层路径防穿越

文件操作经过 6 层验证，任何一层失败都返回 `PermissionError`：

| 层 | 位置 | 机制 |
|----|------|------|
| ① `..` 拒绝 | `tools.py:615` | Normalize 后检查 `..` 段 |
| ② 虚拟路径族 | `tools.py:624` | 必须属于 `/mnt/user-data`/`/mnt/skills`/`/mnt/acp-workspace` |
| ③ mount read_only | `tools.py:624` | skills + acp-workspace 写操作直接拒绝 |
| ④ 解析后 containment | `tools.py:678` | `resolved_path.relative_to(thread_dir)` |
| ⑤ 沙箱层 containment | `local_sandbox.py:127` | `resolved_path.relative_to(local_root)` |
| ⑥ symlink 过滤 | `list_dir.py:42` / `search.py:186` | 越界 symlink 跳过 |

---

## 其他安全机制

**输出截断：**
- bash: middle-truncation, 20000 字符
- read_file: head-truncation, 50000 字符
- write_file: error 截断 2000 字符
- glob: max 200 results
- grep: max 100 results

**输出脱敏：** 在 local 模式下，所有命令输出中的 host 路径被正则替换回虚拟路径（`mask_local_paths_in_output`），防止 host 目录结构泄露给 LLM。

**文件操作加锁：** `str_replace` 和 `write_file` 对 `(sandbox_id, path)` 做细粒度锁，防止同一 sandbox 内并发写冲突。

**TOCTOU race：** `download_file` 在 `getsize()` 和 `read()` 之间有竞争窗口。代码明确接受（`local_sandbox.py:400`）— 因为这是 "controlled sandbox environment"。
