---
title: "沙箱系统"
description: "DeerFlow 的沙箱系统提供统一的执行环境抽象，Agent 不感知底层是本地文件系统还是 Docker 容器。现有 7 种实现（Local/AIO/Provisioner/BoxLite/E2B/Tenki/OpenSandbox）。"
topics: [sandbox, isolation, filesystem]
---

# 沙箱系统

DeerFlow 的沙箱系统提供统一的执行环境抽象，Agent 不感知底层是本地文件系统还是 Docker 容器。

> **交叉引用：** 七种沙箱的安全隔离对比见 [security/02-sandbox-isolation.md](../../operations/security/02-sandbox-isolation.md)。

## 抽象接口

```python
class Sandbox(ABC):
    _id: str                        # 沙箱标识

    @abstractmethod
    def execute_command(self, command: str) -> str: ...
    @abstractmethod
    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str: ...
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

> 🆕 `read_file` 新增可选 `start_line`/`end_line`（1-indexed, inclusive）行范围参数。`grep` 支持单文件搜索（`root_is_file` 分支），不再要求目录。

## Provider 模式

```python
class SandboxProvider:
    def acquire(thread_id: str | None) -> Sandbox: ...         # 同步获取
    async def acquire_async(thread_id: str | None) -> Sandbox: ... # 异步获取
    def get(thread_id: str | None) -> Sandbox | None: ...       # 获取已存在的
    def release(thread_id: str) -> None: ...                    # 释放
```

`acquire_async` 的存在意义：Docker 沙箱的创建、跨进程锁、就绪轮询都必须在 async 路径上，不能阻塞 event loop。

`get_sandbox_provider()` 有构造竞态保护：双线程同时 cold-start 时，loser 的 provider 调 `shutdown()` 避免泄漏（issue #3721）。

## 七种实现

所有实现共享 `WarmPoolLifecycleMixin`（`community/warm_pool_lifecycle.py`），提供 idle timeout、replicas 软上限、过期 warm entry 回收。AIO 把 active-idle 清理留在 provider 内，只把 warm-pool 过期委托给共享 mixin。

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

**🆕 跨实例 ownership store（#4206）**——多 Gateway 实例共享容器后端时，通过可插拔租约存储协调容器归属，`sandbox.ownership.type: memory | redis`（redis 时推断多实例）：

- **`own:` vs `del:` 双状态租约**：`del:` 标记正在销毁的容器，`take()` 对 `del:` 拒绝，关闭"检查→停止"竞态窗口（替代被删除的 per-sandbox `flock`）
- `take()` 用于 acquire 路径（无条件；同一 thread 下一 turn 可能落到另一实例），`claim()` 用于 adopt/reap 路径（仅当无主或已归自己）
- `renew()` 区分 `LAPSED`（租约缺失，重新建立）与 `LOST`（被 peer 持有，放弃）——防止 Redis 重启丢 key 后全集群驱逐
- `_held_teardown_lease` 心跳线程在容器 stop 期间持续刷新 `del:` 标记，最终 release 由心跳自身执行
- `_adoptable_after_grace`：需在完整 TTL 内持续无主才可 adoption，live owner 的续约会**重置** grace
- **lease renewal 独立于 idle checker**：`idle_timeout: 0`（"保持 warm VM 直到 shutdown"）时租约仍续
- 沙箱 ID 从 8 字符扩展到 **16 字符**（`sha256[:16]`），减少多租户碰撞
- `SandboxBeingDestroyedError`：acquire 遇到 peer 正在销毁的容器时抛出，调用者 drop 并冷启动
- Skills 挂载改用 **projection**（`skills_view/public`/`custom`/`legacy`/`integrations`），只挂 enabled skills
- Lark CLI 运行时挂载：`_get_lark_cli_runtime_mounts` + broker 探测
- Redis 自动推断：`stream_bridge.type=redis` 时 ownership 也推断为 redis

### 3. Provisioner 模式（K3s Pod）

AioSandboxProvider + `provisioner_url`。每个 sandbox → 一个 K3s Pod。适合生产。

### 4. BoxLiteProvider（Micro-VM 隔离）

```yaml
sandbox:
  use: deerflow.community.boxlite:BoxliteProvider
  image: python:3.12-slim
  replicas: 3
  idle_timeout: 600
```

KVM（Linux）/ Hypervisor.framework（macOS）micro-VM。私有 asyncio event loop（BoxLite 句柄是 loop-affine）。Warm pool 同 `(user, thread)` 回收。

### 5. E2BSandboxProvider（云端沙箱）

```yaml
sandbox:
  use: deerflow.community.e2b_sandbox:E2BSandboxProvider
```

e2b code-interpreter 云端沙箱。多进程发现（metadata 标记）。Output sync（释放时从 VM 回传 outputs/workspace 到 host）。

**🆕 本轮重构**：
- **容量控制**：`overflow_policy: wait | reject | burst`（默认 `wait`）、`acquire_timeout`（默认 30s）、`burst_limit`（burst 策略额外槽位）。容量耗尽抛 `SandboxCapacityExceededError`（含 `code`/`reason`/`replicas`/`retryable`/`retry_after_seconds` 结构化字段）
- **跨实例 ownership**：复用 AIO 的 `aio_sandbox/ownership/` 模块，redis 后端支持部署级容量共享（Lua 原子管理 VM + in-flight-create 条目，fail-closed）
- **远程对账**：`_reconcile_remote_sandboxes` 后台线程分页 listing + metadata 过滤，按 `(user_id, thread_id)` adopt，重复沙箱按 `created_at` 去重（canonical 保留，duplicate 经 grace 后 kill），支持 page/item/time 预算 + orphan TTL
- **acquire_async 专用 executor**：从 `asyncio.to_thread` 改为专属 `ThreadPoolExecutor`（4~32 worker），不消费默认 executor
- **Sandbox.list() 兼容**：统一处理旧 SDK 的 `SandboxInfo` 列表和新 SDK ≥2.x 的 `SandboxPaginator`

### 6. TenkiSandboxProvider（云端 Micro-VM）🆕

```yaml
sandbox:
  use: deerflow.community.tenki:TenkiSandboxProvider
  api_key: $TENKI_API_KEY      # 或 TENKI_AUTH_TOKEN 环境变量
  base_url: https://tenki.cloud
  image: my-base-image         # 可选
  project_id: proj_...          # 可选
  cpu_cores: 2                  # 可选
  replicas: 3                   # active+warm 上限
  idle_timeout: 600             # warm microVM 闲置终止
  max_duration: 14400           # 沙箱生命周期（默认 4h）
```

Tenki 云 micro-VM（tenki.cloud），与 BoxLite（本地微 VM）平行的**云端**方案。SDK **同步**调用（无 event-loop bridge，与 BoxLite 不同）；`_import_client()` 懒加载 `tenki-sandbox`（`deerflow-harness[tenki]` 可选 extra）。

- 文件传输用 Tenki 原生 `sandbox.fs` API（二进制安全、流式，无 base64/shell 跳板）；只有 `list_dir`/`glob`/`grep` 才 shell out 到 busybox `find`/`grep`（与 e2b 共享 `deerflow.sandbox.search` 解析层）
- 沙箱以非特权 `tenki` 用户运行；`/mnt/user-data` 前缀重映射到可写 HOME，bootstrap 时 best-effort `sudo` 符号链接
- Box ID 确定性派生：`sha256(user_id:thread_id)[:16]`；释放入 warm pool，同 scope 经 liveness 检查复用
- 终端 session 错误（`SessionTerminatedError` 等 + `ConnectionError`/`BrokenPipeError`/`EOFError`）经 `_invalidate_sandbox` 驱逐死微 VM
- 跨进程孤儿对账是 follow-up（目前单进程 warm pool）

### 7. OpenSandboxProvider（云端沙箱）🆕

```yaml
sandbox:
  use: deerflow.community.opensandbox:OpenSandboxProvider
  image: python:3.11           # 默认
  api_key: $OPEN_SANDBOX_API_KEY   # 或 OPEN_SANDBOX_API_KEY 环境变量
  domain: localhost:8080           # 或 OPEN_SANDBOX_DOMAIN 环境变量
  protocol: http
  request_timeout: 30
  ready_timeout: 30
  use_server_proxy: false          # Gateway 连得到管理服务但连不到沙箱 execd 时启用
  sandbox_timeout: 14400           # 远端生命周期（默认 4h）；0 = 仅显式清理（禁用 renew）
  bash_command_timeout: 600        # 默认命令超时
  replicas: 3                      # active+warm 上限
  idle_timeout: 600                # warm 秒数；0 禁用回收
  environment: { PYTHONUNBUFFERED: "1" }   # $VAR 从 Gateway 进程环境解析
```

[OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) 云端沙箱，经**同步** Python SDK 实现 `Sandbox`/`SandboxProvider` 契约。隔离模型为**远程云沙箱**：命令走 `execd` 端点、文件走原生 filesystem API，全在远端执行，host 不共享进程/文件系统（与 E2B 同级）。SDK 是可选依赖（`deerflow-harness[opensandbox]`，`opensandbox>=0.1.15,<0.2.0`），`_import_sdk()` 只在选中该 provider 时懒加载。`api_key`/`domain` 可省略（走环境变量）；配置了远程 HTTP 域会 warn 建议 HTTPS。

- 沙箱 ID 确定性派生 `sha256(user_id:thread_id)[:16]`；释放入 in-process warm pool，仅同 scope 经 `ping()`（跑 `true`）健康检查后复用
- 每个 remote 持有**独立 SDK 连接 transport**（`_new_connection_config` 每 remote 一份 base config，`SandboxSync.create()` 派生 transport、`destroy()` 关闭），避免活沙箱继承另一个沙箱的 transport
- 操作前 `renew(sandbox_timeout)`；命令用 `bash_command_timeout`，需要时延长 renew horizon；per-remote `_operation_lock` 序列化操作，防止短文件操作缩短长命令 horizon
- 文件传输走 OpenSandbox 原生 filesystem API；append 是 read-modify-write（SDK 0.1.x 无 append 原语）。`list_dir`/`glob`/`grep` shell out 到 portable `find`/`grep`，共享 `deerflow.sandbox.search` 解析层
- 路径必须绝对且无 `..`（`_resolve_path`）；artifact 下载额外限定在 `/mnt/user-data`（`_resolve_download_path`）
- 终端失败（command 路径 404/410、`SandboxUnhealthyException`、broken transport `BrokenPipeError`/`ConnectionError`/`EOFError`）经 `_invalidate_sandbox` 驱逐死 client，下次 acquire 冷启动；file-path 404 仍为普通缺文件错误
- `reset()` 把 active 客户 park 入 warm pool 交由 detached provider 清理；`shutdown()` 销毁 active + warm remote。跨进程发现/ownership 尚未实现（单进程 warm pool，follow-up）

### 环境变量擦洗

`env_policy.build_sandbox_env()` 在注入请求级密钥前从继承环境剥离敏感变量：

- 通配模式：`*KEY*`、`*SECRET*`、`*TOKEN*`、`*PASS*`、`*CREDENTIAL*`、`*DSN*`
- 精确名：`DATABASE_URL`、`REDIS_URL`、`GH_PAT`、`MYSQL_PWD`、`REDISCLI_AUTH`、`PGPASSFILE`、`PGSERVICEFILE`
- Benign 变量（`PATH`、`HOME`、`LANG`、`VIRTUAL_ENV`）保留

源码：`deerflow/sandbox/env_policy.py`

### 路径安全守卫

Segment-boundary regex 保护反向路径翻译和输出脱敏——防止路径中包含目标模式的子串被错误匹配。源码：`deerflow/sandbox/path_patterns.py`

## 孤儿回收（orphan reconciliation）🆕

Provider 启动时（及 AIO 定期 `_cleanup_idle_resources`）调用 `_reconcile_orphans()`：

1. `backend.list_running()` 枚举本地 Docker 容器（`deer-flow-sandbox-` 前缀过滤 + `docker inspect` 批量取端口/时间）
2. 对每个运行中的容器查 ownership store：
   - 已被 peer 持有 → 跳过
   - 无主但未过 recovery grace（一个完整 TTL）→ 推迟
   - 无主且 grace 已过 → `claim()` 成功后 adopt 入 warm pool
3. 对账用 `claim()`（非 `take()`），无主容器不会被销毁，只会被收养

E2B 侧是独立的远程对账线程（见上文 #5）。测试：`test_sandbox_orphan_reconciliation.py`（2845 行）覆盖 store 故障 fail-closed、grace 重置、LAPSED vs LOST、Redis 状态丢失恢复等。

## 沙箱中间件 🆕

`deerflow/sandbox/middleware.py` 的 `SandboxMiddleware` 管理 per-thread 沙箱生命周期：

- **lazy_init（默认）**：延迟到首次 tool call 才 `ensure_sandbox_initialized` 获取沙箱，而非 agent 启动时
- **fork-restored 保护**：`after_agent`/`aafter_agent` 用 `unwrap_sandbox()` 检测 `Overwrite` 包装（delta checkpoint 模式下 fork 恢复的 sandbox channel 值可能被包裹）。fork-restored 的沙箱只属于 parent thread，**不释放**，避免 evict parent 的 warm sandbox
- **wrap_tool_call**：检测 lazy init 后 sandbox_id 的新增，通过 `Command(update=...)` 持久化进 graph state（否则 LangGraph reducer 不会自动拾取 runtime.state 的本地修改）

## sandbox:execute 授权 🆕

每次沙箱获取都经过 `authorize_sandbox_execution`（`deerflow/authz/sandbox_authz.py`）——在 `provider.acquire` 之前做一次二进制 `authorize(principal, "sandbox", "execute", target="*")` 检查：

- **单一获取入口，无法绕过**：gate 落在 `ensure_sandbox_initialized` / `ensure_sandbox_initialized_async`（`tools.py`）和 `SandboxMiddleware.before_agent` / `abefore_agent`（`middleware.py`），无论哪个 sandbox 工具触发都一样；复用路径（state 已有 sandbox）跳过重复检查
- **deny → 友好 ToolMessage**：`SandboxAuthorizationError`（`sandbox/exceptions.py`）向上穿过工具执行，agent 的工具错误处理把它转成 `"sandbox execution is not permitted for your role"` 而不是让 run 崩掉（RFC §9）。eager 路径（`before_agent`）捕获 deny 后跳过获取，把拒绝推迟到首个触碰沙箱的工具调用，两条路径语义一致
- **fail_closed / fail_open**：provider 错误（`authorize()` 与 provider 解析）遵循 `authorization.fail_closed`；无 `config.yaml` 或 `authorization.enabled: false` 时 gate 是 no-op（`safe_app_config` 容忍缺失配置）
- **target 是哨兵 `*`**（"沙箱整体"）——沙箱是单一共享资源，不是 tools/models/skills 那样的命名目录；RBAC `allow: ["*"]` / `allow: true` 放行，`allow: []` / `allow: false` 拒绝
- 与 `apply_tool_authorization`（`tool_filter.py`）、`_authorize_model_name`（`lead_agent/agent.py`）共享同一 Principal/provider 身份来源
- 测试：`tests/test_sandbox_authorization.py`

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
| `read_file` | `sandbox/tools.py` | 文件读取，可选行范围（`start_line`/`end_line`） |
| `write_file` | `sandbox/tools.py` | 文件写入/追加，自动创建目录 |
| `str_replace` | `sandbox/tools.py` | 子串替换（单次或全局） |
| `glob` | `sandbox/tools.py` | 文件匹配 |
| `grep` | `sandbox/tools.py` | 文本搜索（支持单文件） |

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
