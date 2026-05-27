# 沙箱系统

DeerFlow 的沙箱系统提供统一的执行环境抽象，Agent 不感知底层是本地文件系统还是 Docker 容器。

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

## 三种实现

### 1. LocalSandboxProvider（默认）

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: false
```

**Per-thread 隔离**：
- `acquire(thread_id)` → 创建 `LocalSandbox`，id = `local:{thread_id}`
- `acquire()` / `acquire(None)` → 返回 legacy 单例 `local`
- 每个 thread 有独立的路径映射

**LRU 缓存**：
- 最多 256 个 per-thread sandbox
- `threading.Lock` 保护

**路径映射**：

| Agent 看到的虚拟路径 | 实际 host 路径 |
|---|---|
| `/mnt/user-data/workspace` | `.deer-flow/users/{user_id}/threads/{thread_id}/user-data/workspace` |
| `/mnt/user-data/uploads` | `.deer-flow/users/{user_id}/threads/{thread_id}/user-data/uploads` |
| `/mnt/user-data/outputs` | `.deer-flow/users/{user_id}/threads/{thread_id}/user-data/outputs` |
| `/mnt/skills` | `skills/`（项目目录下） |
| `/mnt/acp-workspace` | `.deer-flow/users/{user_id}/threads/{thread_id}/acp-workspace` |

**Host bash 安全**：
- 默认 `allow_host_bash: false`
- 因为 LocalSandboxProvider 不是安全隔离边界，bash 默认关闭
- 仅在完全信任的单用户本地工作流中开启

**输出截断**：
```
bash_output_max_chars: 20000       # middle-truncation (head + tail)
read_file_output_max_chars: 50000  # head-truncation
ls_output_max_chars: 20000         # head-truncation
```

### 2. AioSandboxProvider（Docker 隔离）

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  image: enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
  port: 8080
  replicas: 3                        # 最多 3 个并发容器
  container_prefix: deer-flow-sandbox
  mounts:
    - host_path: /path/on/host
      container_path: /home/user/shared
      read_only: false
  environment:                       # 注入容器环境变量
    NODE_ENV: production
    API_KEY: $MY_API_KEY             # $VAR 从 host 解析
```

**平台自适应**：
- macOS：先探测 Apple Container（`apple-virtualization.framework`），不可用再 fallback Docker
- 其他平台：Docker
- 通过 `agent-sandbox >= 0.0.19` 库实现

**LRU 淘汰**：
- replicas: 3 → 最多创建 3 个容器
- 超出后最久未使用的被 evict（释放为新 sandbox 腾空间）

**虚拟路径一致性**：
- Skills 目录自动挂载到 `skills.container_path`（默认 `/mnt/skills`）
- User-data 目录通过 volume mount 传入容器同一虚拟路径
- **Agent 不感知 local 还是 AIO** — 两者接受相同的 `/mnt/user-data/...` 路径

### 3. Provisioner 模式（K3s Pod）

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  provisioner_url: http://provisioner:8002
```

- 每个 `sandbox_id` → 一个 K3s Pod
- Provisioner 管理 Pod 生命周期
- 适合生产（强隔离、可扩展）

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
