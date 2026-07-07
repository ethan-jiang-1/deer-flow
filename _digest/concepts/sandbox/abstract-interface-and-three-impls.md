---
title: "沙箱系统"
description: "DeerFlow 的沙箱系统提供统一的执行环境抽象，Agent 不感知底层是本地文件系统还是 Docker 容器。"
topics: [sandbox, isolation, filesystem]
---

# 沙箱系统

DeerFlow 的沙箱系统提供统一的执行环境抽象，Agent 不感知底层是本地文件系统还是 Docker 容器。

> **交叉引用：** 五种沙箱的安全隔离对比见 [security/02-sandbox-isolation.md](../../operations/security/02-sandbox-isolation.md)。

## 抽象接口

```python
class Sandbox(ABC):
    _id: str                        # 沙箱标识

    @abstractmethod
    def execute_command(self, command: str) -> str: ...
    @abstractmethod
    def read_file(self, path: str) -> str: ...
    @abstractmethod
    def download_file(self, path: str) -> bytes: ...
    @abstractmethod
    def list_dir(self, path: str, max_depth=2) -> list[str]: ...
    @abstractmethod
    def write_file(self, path: str, content: str, append: bool = False) -> None: ...
    @abstractmethod
    def glob(self, path, pattern, *, include_dirs, max_results) -> tuple[list[str], bool]: ...
    @abstractmethod
    def grep(self, path, pattern, *, glob, literal, case_sensitive, max_results) -> tuple[list[GrepMatch], bool]: ...
```

## Provider 模式

```python
class SandboxProvider:
    def acquire(thread_id: str | None) -> Sandbox: ...         # 同步获取
    async def acquire_async(thread_id: str | None) -> Sandbox: ... # 异步获取
    def get(thread_id: str | None) -> Sandbox | None: ...       # 获取已存在的
    def release(thread_id: str) -> None: ...                    # 释放
```

`acquire_async` 的存在意义：Docker 沙箱的创建、跨进程锁、就绪轮询都必须在 async 路径上，不能阻塞 event loop。

## 五种实现

所有实现共享 `WarmPoolLifecycleMixin`（`community/warm_pool_lifecycle.py`），提供 idle timeout、replicas 软上限、过期 warm entry 回收。

### 1. LocalSandboxProvider（默认）

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: false
```

Per-thread 隔离、LRU 缓存（256）、虚拟路径映射。Host bash 默认关闭。

### 2. AioSandboxProvider（Docker 隔离）

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  replicas: 3
```

平台自适应（macOS Apple Container → Docker fallback）。Warm pool 持有释放的容器供快速重用。

### 3. Provisioner 模式（K3s Pod）

AioSandboxProvider + `provisioner_url`。每个 sandbox → 一个 K3s Pod。适合生产。

### 4. BoxLiteProvider（Micro-VM 隔离）🆕

```yaml
sandbox:
  use: deerflow.community.boxlite:BoxliteProvider
  image: python:3.12-slim
  replicas: 3
  idle_timeout: 600
```

KVM（Linux）/ Hypervisor.framework（macOS）micro-VM。私有 asyncio event loop（BoxLite 句柄是 loop-affine）。Warm pool 同 `(user, thread)` 回收。

### 5. E2BSandboxProvider（云端沙箱）🆕

```yaml
sandbox:
  use: deerflow.community.e2b_sandbox:E2BSandboxProvider
```

e2b code-interpreter 云端沙箱。多进程发现（metadata 标记）。Output sync（释放时从 VM 回传 outputs/workspace 到 host）。

### 环境变量擦洗 🆕

`env_policy.build_sandbox_env()` 在注入请求级密钥前从继承环境剥离敏感变量：

- 通配模式：`*KEY*`、`*SECRET*`、`*TOKEN*`、`*PASSWORD*`、`*CREDENTIAL*`、`*DSN*`
- 精确名：`DATABASE_URL`、`REDIS_URL`、`GH_PAT`、`GITHUB_PAT` 等连接串
- Benign 变量（`PATH`、`HOME`、`LANG`）保留

源码：`deerflow/sandbox/env_policy.py`

## Sandbox 检测

```python
def is_local_sandbox(sandbox_id: str) -> bool:
    return sandbox_id == "local" or sandbox_id.startswith("local:")
```

Agent/tool 路径用这个判断来决定是否需要虚拟路径转换。

## Sandbox Tools

| 工具 | 源文件 | 功能 |
|------|--------|------|
| `bash` | `sandbox/tools.py` | 执行命令，虚拟路径翻译 |
| `ls` | `sandbox/tools.py` | 目录列表（tree 格式，max 2 层） |
| `read_file` | `sandbox/tools.py` | 文件读取，可选行范围 |
| `write_file` | `sandbox/tools.py` | 文件写入/追加，自动创建目录 |
| `str_replace` | `sandbox/tools.py` | 子串替换（单次或全局） |
| `glob` | `sandbox/tools.py` | 文件匹配 |
| `grep` | `sandbox/tools.py` | 文本搜索 |

**`str_replace` 并发安全**：序列化 scope 为 `(sandbox.id, path)`，所以不同 sandbox 的同一虚拟路径不会在进程内竞争。

**防御层**：即使有 path mapping，`tools.py` 中的 `replace_virtual_path()` / `replace_virtual_paths_in_command()` 仍然作为第二层防御进行路径验证。

## Docker-out-of-Docker（DooD）

Docker 部署中，Gateway 容器通过挂载宿主机 `/var/run/docker.sock` 来启动沙箱容器：
- Gateway 容器内调用 Docker API → 宿主机 Docker daemon → 创建沙箱容器
- `host.docker.internal:host-gateway` 解决容器-宿主机网络通信

## 安全能力门控 (`sandbox/security.py`)

两个关键的安全门控函数，在工具注册和子 agent 创建前检查：

```mermaid
flowchart TD
    START[config.yaml sandbox.use] --> L{uses_local_sandbox_provider?}
    L -->|Yes| HB{allow_host_bash?}
    L -->|No (AIO/Docker/K3s)| PASS[host bash 允许]

    HB -->|true| PASS2[host bash 显式允许]
    HB -->|false| BLOCK[host bash 被阻止]
    BLOCK --> TOOLS[bash 工具从 agent toolset 中移除]
    BLOCK --> SUB[bash 子 agent 被禁用]
```

- **`uses_local_sandbox_provider()`** — 检测沙箱 provider 是否为 `LocalSandboxProvider`（零隔离）
- **`is_host_bash_allowed()`** — 如果在本地沙箱上未设置 `allow_host_bash: true` 则返回 `False`；AIO/Docker/K3s 返回 `True`（它们有容器隔离）
- 本地沙箱上的被阻止 bash 产生明确的错误消息，指出不安全的边界并建议切换到 AIO

---
> **See also:** [Security: Sandbox Isolation](../../operations/security/02-sandbox-isolation.md) · [Sandbox Governance](../../operations/it-ops/02-sandbox-governance.md) · [Env Policy (source)](../../../backend/packages/harness/deerflow/sandbox/env_policy.py)
