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
  workspace_id: ws_...         # 可选；账号只有一个 workspace 时可省
  cpu_cores: 2                  # 可选
  replicas: 3                   # active+warm 上限
  idle_timeout: 600             # warm microVM 闲置终止
  max_duration: 14400           # 沙箱生命周期（默认 4h）
```

> ⚠️ **breaking（v2.1.0-rc0）**：`project_id` 配置已移除——Tenki 1.x 删除了 projects 概念，scope 现在只由 workspace 决定。账号有多个 workspace 时设 `workspace_id`；遗留的 `project_id` 被忽略并在启动时告警。依赖也从 `tenki-sandbox` 改名为 `tenki`（#5087）。

Tenki 云 micro-VM（tenki.cloud），与 BoxLite（本地微 VM）平行的**云端**方案。SDK **同步**调用（无 event-loop bridge，与 BoxLite 不同）；`_import_client()` 懒加载 `tenki` 包（`deerflow-harness[tenki]` 可选 extra）。

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

`env_policy.build_sandbox_env()` 在注入请求级密钥前从继承环境剥离敏感变量（默认擦洗，不是 opt-in）：

- 通配模式（对**大写后的变量名**做 `fnmatchcase`）：`*KEY*`、`*SECRET*`、`*TOKEN*`、`*PASS*`、`*CREDENTIAL*`、`*DSN*`（`env_policy.py:24-46`）
- 精确名（无法安全通配的）：`DATABASE_URL`、`DATABASE_URI`、`REDIS_URL`、`MONGODB_URI`、`MONGO_URL`、`AMQP_URL`、`RABBITMQ_URL`、`POSTGRES_URL`、`POSTGRESQL_URL`、`MYSQL_URL`、`CLICKHOUSE_URL`、`CONNECTION_STRING`、`CONN_STR`、`GH_PAT`、`GITHUB_PAT`、`MYSQL_PWD`、`REDISCLI_AUTH`、`REDIS_AUTH`、`PGSERVICEFILE`、`SSH_AUTH_SOCK`（`env_policy.py:66-96`）
- 有意保留的边界语义：`*PASS*` 顺带命中 `GIT_ASKPASS`/`SSH_ASKPASS`/`SUDO_ASKPASS`（凭证*指针*，同一泄漏类）与 `COMPASS_*`/`BYPASS_*`（fail-safe 方向）；`PWD`/`OLDPWD` 因不含 `PASS` 子串而保留；`SSH_AUTH_SOCK` 也是指针类，无通配可用故必须精确列名（`env_policy.py:28-46,87-94`）
- `is_blocked_env_name()` 是唯一判定入口；**注入胜出**：`build_sandbox_env(injected)` 先擦洗继承环境再 `update(injected)`，被声明为 required-secret 的注入值即使是通配名也会进入子进程（`env_policy.py:99-120`）
- Benign 变量（`PATH`、`HOME`、`LANG`、`VIRTUAL_ENV`、`PYTHONPATH` 等）不含上述 token，自然保留

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

E2B 侧是独立的远程对账线程（见上文 #5）。测试：`test_sandbox_orphan_reconciliation.py`（3028 行 / 90 个 test 函数，v2.1.0 实测）覆盖 store 故障 fail-closed、grace 重置、LAPSED vs LOST、Redis 状态丢失恢复等。

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
| `read_file` | `sandbox/tools.py` | 文件读取，可选行范围（`start_line`/`end_line`）。🆕 v2.1.0-rc0：预算允许时截断落在**行边界**，截断标记标注下一 `start_line`——agent 可精确翻页长文件（配合 read offset 续读） |
| `write_file` | `sandbox/tools.py` | 文件写入/追加，自动创建目录 |
| `str_replace` | `sandbox/tools.py` | 子串替换（单次或全局） |
| `glob` | `sandbox/tools.py` | 文件匹配 |
| `grep` | `sandbox/tools.py` | 文本搜索（支持单文件） |

**`str_replace` 并发安全**：序列化 scope 为 `(sandbox.id, path)`，所以不同 sandbox 的同一虚拟路径不会在进程内竞争。

**防御层**：即使有 path mapping，`tools.py` 中的 `replace_virtual_path()` / `replace_virtual_paths_in_command()` 仍然作为第二层防御进行路径验证。

### 工具面补充契约（`tools.py`，核对内置工具文档后仍缺失的部分）

- **`write_file` 单次写入上限 80 KB**（`tools.py:95-96`，实现 `tools.py:2616-2672`）：非 append 调用在 UTF-8 字节上受限，超限返回带修复指引的 `Error:`（提示改用 `str_replace` 或分段 append），**`append=True` 不受限**。可用 `DEERFLOW_WRITE_FILE_MAX_BYTES` 覆盖，`0` 完全关闭该保护（调高有 streaming 超时风险，issue #3189）。
- **bash 输出密钥脱敏**（`tools.py:1751-1785`）：注入的请求级 secret 值在返回前被替换为 `[redacted]`；只处理长度 ≥ 8 的值，且按长度降序替换，避免子串部分泄漏，也避免短值（区域码/PIN）破坏无关输出。这是 skill 专属的第五条泄漏面（bash 直接回传 stdout）。
- **bash 截断保留退出标记**（`tools.py:1787-1797`）：中间截断（头尾各 50%）必须保住末尾的权威退出标记（本地 `Exit Code: N`、远端 `Command exited with code N`）；配置上限低于 32 会被抬到 32，否则截断会破坏它本要度量的失败证据。
- 其余工具面（`ls`/`glob`/`grep`/`read_file`/`str_replace` 参数与上限、`(sandbox_id, path)` 文件锁、`Error:` 约定）见 [builtin-tools/B-sandbox-filesystem.md](../builtin-tools/B-sandbox-filesystem.md)（注意该文档源码行号停留在旧版本，仅语义有效）。

## 共享组件契约（RFC #4741 / #5089 / #5128）🆕

七种 provider 之上有一层**与具体后端无关**的共享组件：跨实例 ownership store 回答"**哪个 Gateway 实例可以 reap**"，下面这层回答"**同一 Gateway 内哪些并发执行还在用这个 client / 这个 scope**"，以及身份派生、路径匹配、远端搜索输出等可复用契约。

### 执行租约 `lease.py`（#5128）

进程内 `SandboxLeaseManager`，按 `(user_id, thread_id)` 串行化生命周期迁移，holder 计数决定何时真正 `release`：

- **回答的问题与 ownership store 正交**：ownership 决定跨实例"谁负责这个容器"；lease 决定进程内"还有几个并发执行（lead、subagent、Gateway request、channel upload）在用 provider 的 active client"。**只有最后一个 holder 才被允许调用 `SandboxProvider.release`**（`lease.py:1-8`）。
- **metadata 锁与生命周期锁分离**：`_metadata_lock`（`RLock`）只保护绑定表，provider I/O 不在它里面做；`_serializer`（`AcquireSerializer[(user_id, thread_id)]`）串行化慢迁移，避免无关线程互相阻塞（`lease.py:143-159`）。
- **owner 语义**：执行拿一个 ephemeral owner（`ensure_sandbox_lease_owner` 生成 `agent:<uuid>` 并写进可变 runtime context；`sandbox_lease_owner` 只读不创建，供直接工具调用者用）（`lease.py:634-659`）。owner **不得跨 thread 身份迁移**（`_bind_locked` 抛 `RuntimeError`）；同一 owner 的 sandbox 绑定是**单调**的——普通 owner 后续遇到 fork-restored 视图不会丢掉 park 责任，borrower 后续做正常 acquire 会被升级为普通 owner（`lease.py:193-229`）。
- **`release_on_last=False` = borrower**：fork-restored 子执行与上传同步用它——它们 fence 住 client 并负责自己的 command-scope 清理，但**自己不请求 park**；此前普通 owner 的 park 请求被记入 `_release_pending_by_sandbox`，推迟到**所有** holder 都退出后才由最后退出者执行（`lease.py:165-191,352-402`）。
- **陈旧绑定回退**：`_active_owner_binding` 会先查 `provider.get(binding.sandbox_id)`；checkpoint 里留了 id 但本地 client 已消失时，该绑定按陈旧处理并**不请求 release**，让后续 acquire 重建而不是沿用不可用的 id（`lease.py:244-277`）。
- **原子组合操作**：`acquire`（幂等 for one owner）/ `reuse_or_acquire`(持久化的 live id 优先，否则冷启动，且"fork 借用的 live client"与"新 acquire 的替代品"可分别设置 `release_on_last`/`acquire_release_on_last`) / `retain`（挂到继承或 checkpoint 的 id 上），同步与异步各一份，全部在 serializer 临界区内完成"查活 + 绑定"（`lease.py:404-544`）。
- **`release` 先释放 command scope 再 park**：拿到绑定后调 `sandbox.release_command_scope(owner_id)`，`finally` 里仅当这是最后一个 holder 时才 `provider.release(binding.sandbox_id)`（`lease.py:546-567`）。
- **取消不可中断生命周期清理**：`run_sync_lifecycle_operation` 用 `asyncio.shield` + `_drain_task_after_cancellation` 等阻塞 worker 真正结束；重复取消被记住、只在 worker 终止后重新抛出，晚到的 worker 失败只 log，不替换调用者的 cancellation。async acquire 在取消后要 drain 结果并对"无人认领的 acquire"做 rollback（仍持 serializer 时检查 owner 表，无 owner 才 `provider.release`）（`lease.py:38-74,300-350,569-585`）。
- **manager 注册按 provider 对象身份**：`id(provider)` + 身份复核（不用 hash/eq），provider 不要求可哈希；注册表持有强引用直到 `discard_sandbox_lease_manager`，`close()` 停掉 serializer worker（`lease.py:598-631`）。`binding_for(owner_id)` 仅供诊断/测试（`lease.py:587-591`）。
- **外层生命周期栅栏**：`release_sandbox_execution_lease(_async)` 在 lead/embedded 执行的最外层 fence 做幂等 release；provider 懒导入，从不触碰沙箱的 run 在终结清理时不会初始化 provider（`lease.py:662-698`）。
- **lease/scope 上下文 ID 是服务端所有**：`SANDBOX_LEASE_OWNER_CONTEXT_KEY` / `SANDBOX_COMMAND_SCOPE_CONTEXT_KEY` 被 Gateway 与 worker 从客户端输入中擦除，只有内部 subagent 路径会分配 task ID；`sandbox_command_scope()` 读 subagent 的可选 shell-session scope（`lease.py:28-35,654-659`）。
- 子 agent owner 同时充当 `sandbox_command_scope_id`（`subagents/executor.py:1564` 把 `context["sandbox_command_scope_id"]` 设为 lease owner id；`sandbox/tools.py:1699` 用 `sandbox_command_scope()` 读取）：AIO 每个 scope 一个持久 shell session，scope 内命令串行、不同 subagent 各用独立服务端 session 因而可并发；`release_command_scope(scope_id)` 在 scope 释放时清理该 session（`community/aio_sandbox/aio_sandbox.py:270-355`）。

### 获取串行化 `acquire_serialization.py`

`AcquireSerializer[KeyT]` —— **有界、带引用计数**的 per-key `threading.Lock` 表 + 专用有界 executor：

- **key 由 provider 选择**，serializer 不解释它：AIO/E2B 用 `(user_id, thread_id)`（E2B 追加 `skills_root`），BoxLite/Tenki/OpenSandbox 用派生 sandbox id；`thread_id=None` 的随机 UUID acquire 绕过串行化（模块 docstring `acquire_serialization.py:1-12`）。
- **锁表有界增长**：`_checkout` 建/取 entry 并 `refs += 1`（holders+waiters）；`_checkin` 在 `refs == 0` 且锁未持有才把 entry 从表里删掉（`acquire_serialization.py:204-219`）。`close()` **幂等**，拒绝新 holder 并 `shutdown(wait=False, cancel_futures=True)`；**已在临界区内的调用不会被作废**，其退出仍会解锁并回收 entry（`:192-202`）。关闭后 `_checkout`/排队提交抛 `RuntimeError("AcquireSerializer is closed")`。
- **同步 `hold(key)` / 异步 `hold_async(key)`** 是唯一入口。异步路径把阻塞的 `threading.Lock.acquire` 放到**专用 bounded executor**（默认 `min(32, cpu+4)` worker，`DEFAULT_MAX_WORKERS`），既不用默认 executor 也不阻塞 event loop（`:26,98-110,138-190`）。
- **取消时的所有权交接**（`_AsyncAcquire`）：worker 抢到锁后发现 awaiter 已 `abandon`，会自己释放锁并 checkin；executor 关闭取消排队任务时由 `worker_done` 回调回收，**不依赖被取消的 event loop 再跑一次 done callback**（`:35-95,154-180`）。
- **`run_on_executor()` 显式复制 ContextVars**：`asyncio.to_thread` 会复制，裸 `loop.run_in_executor` 不会；用它把整个同步 acquire（内部含 `hold()`）搬到该 executor 时，请求级 ContextVar（如 `request_trace_context` 绑定的 trace id）在 worker 线程里仍可见（`:112-136`）。

### 作用域令牌 `identity.py`

- `derive_sandbox_scope_token(*, user_id, thread_id)` 返回 **16 位小写 hex**：`sha256(f"{user_id}:{thread_id}").hexdigest()[:16]`（`identity.py:26-38`）。AIO/E2B/BoxLite/Tenki/OpenSandbox 靠它定位既有容器/VM，因此**分隔符、编码、摘要、大小写、截断长度任一改动都是破坏性迁移**（既有远端资源会找不到而被冷启动，`identity.py:1-13`）。
- **keyword-only 是刻意的**：被替代的各 provider helper 签名是 `(thread_id, user_id)` 位置序（正好相反）且两者都是 `str`，keyword-only 消除迁移中的静默实参顺序错误（`identity.py:29-32`）。
- `user_id` 的解析（effective-user 查询、`""` 替代、原样透传）**留在各 provider 私有**，本模块只钉住"解析后的字符串发生什么"；`is_sandbox_scope_token()` 只校验形状（截断哈希不可逆）（`identity.py:9-12,41-43`）。`SANDBOX_ID_VERSION = 1` 是版本常量（`identity.py:20`）。

### 宿主路径→虚拟路径匹配 `path_patterns.py`

`LocalSandbox` 与 `sandbox.tools` 两处都要把宿主机路径改写成虚拟路径喂给模型，规则只保留一份：

- **段边界 lookahead**：`_SEGMENT_BOUNDARY = (?=/|$|[^\w./-])`——mount 根只在真实路径段边界处匹配，`.../skills` 不会命中同前缀的 `.../skills-extra`；`$` 是必需的（输出恰好以 mount 根结尾时否则会原样泄漏宿主路径）（`path_patterns.py:31-42`）。
- **路径尾**：`_PATH_TAIL` 用 `[/\\]` 兼容 Windows 分隔符，遇空白/shell 标点停止；`:` 也终止尾部——否则 `$PATH`/`$PYTHONPATH` 这类冒号拼接列表会把后续每个条目都带进同一次匹配（`;` 本就终止）。路径内部的 `:` 只会缩短匹配，其余原样复制（`path_patterns.py:44-56`）。
- **`normalize_mask_tail()`** 是唯一的拼接规则：去掉前导分隔符并把反斜杠转成正斜杠（虚拟路径恒为 POSIX），避免匹配逻辑之外再出现第二份拼接实现（`path_patterns.py:59-68`）。
- **`separator_agnostic`**：base 内部任一分隔符都接受，用于 base 以 `\` 记录、输出却是 `/` 的场景（`tools` 的 `_path_variants` 与 Windows 上 `LocalSandbox` 的正向解析正好互逆）（`path_patterns.py:71-92`）。
- **高频动态根不编译正则**：`replace_output_path_matches()` 用手写扫描器实现同一"边界 + 尾部"契约，避免为每个 thread 根编译正则、把已驱逐 sandbox 的根留在 Python 全局 `re` 缓存里（`path_patterns.py:95-153`）。历史上边界规则复制两份导致 #4035/#4053 漂移，本模块即为此而存在（`path_patterns.py:14-17`）。

### 远端目录/搜索输出契约（`remote_list_dir.py` / `remote_search.py`）

远端 provider 在 `sh -lc` 下用 `find ... | head` / `grep ... | head`。POSIX `sh` **没有 pipefail**、搜索的 stderr 被丢弃，所以管道状态其实是 `head` 的：搜索根缺失、`find`/`grep` 二进制缺失（127）、树不可读都会"什么都没打印且 exit 0"，与真正的"无匹配"无法区分（#5376/#5380）。两个模块用同一技术修复：

- **命令先查根存在，再把搜索命令自己的状态记到状态文件、在 bounded 输出之后再打印标记，且脚本永远 exit 0**（让"对非零退出抛异常的 SDK"仍能返回标记，标记本身是唯一判据）：`remote_list_dir.py:27-45`、`remote_search.py:48-62`。
- **截断即成功**：`head` 提前关管道会以 SIGPIPE(141) 杀掉搜索，这是成功的截断而非错误——`grep` 的完整状态集是 `(0 匹配, 1 无匹配, 141)`，`find` 是 `(0, 141)`（`remote_search.py:29-34`、`remote_list_dir.py:21-24`）。
- **失败绝不伪装成空结果**：标记缺失（例如状态文件丢失、127 被 `rm` 吞掉）→ `OSError`，**不是** `FileNotFoundError`；只有真正"根缺失"才 `FileNotFoundError`。`remote_list_dir` 的 `find` 状态 1 一律视为"遍历不完整"的 `OSError`（即使已经打印了条目，也不许据此推断路径缺失）（`remote_list_dir.py:60-94`、`remote_search.py:76-96`）。`grep` 2 / `find` 1 会给出"结果可能不完整，请缩小搜索路径"的错误文案。
- **`limit` 的契约**：命令只多放行**一行**作为截断信号（`head -n limit+1`），解析器报告 `truncated = len(lines) > limit`；调用方还会在 Python 侧继续过滤（忽略目录、glob 作用域），所以"返回少于 `max_results`"**不证明搜索完整**，恰好 `limit` 行才算完整（`remote_search.py:14-18,48-62,93`）。
- **按 `\n` 切分、不做 strip**：Linux 文件名里可以合法包含 `\v`/`\f`/`\x1c-\x1e`/`\x85`，所以不能用 `splitlines()`；尾部空白可能属于文件名，`remote_list_dir` 明确不 strip（#4980）（`remote_list_dir.py:60-63`、`remote_search.py:76-78`）。

### 共享搜索语义 `search.py`

本地 glob/grep 与远端（e2b/Tenki/OpenSandbox）的搜索结果解析共用这一层：

- **忽略清单**：`IGNORE_PATTERNS`（VCS、`node_modules`、`__pycache__`、虚拟环境、构建产物、`*.log`/`*.tmp`/`.upload-*.part`、各类缓存目录……）。命中按**名字**判定，`should_ignore_path` 对路径的每个段判定；实现把大部分字面名预编译成 set、少量 glob 合成一个正则，避免每次目录项约 50 次 `fnmatch`（`search.py:7-58,71-90`）。
- **glob 作用域是 root-relative 的**：`path_matches(pattern, rel_path)` 对相对路径做 `PurePosixPath.match`，`**/` 前缀再兜一次裸匹配；远端 `grep(glob=...)` 与 `glob()` 共用它，**不按 basename 单独匹配**（`search.py:93-99`）。
- **搜索硬约束**：单文件 > 1 MB 跳过；二进制（采样 8 KB 含 `\0`，读失败也算二进制）跳过；目录树中**跳过符号链接文件**，并要求 resolve 后仍在根内（防逃逸）；比 `DEFAULT_LINE_SUMMARY_LENGTH × 10` 还长的行整行跳过（防 minified/无换行文件上的 ReDoS）；读取用 `errors="replace"`；单文件 `OSError` 只跳过该文件、不中断整轮（`search.py:60-61,102-114,155-225`）。

### `Overwrite` 包装解包 `overwrite.py`

`unwrap_sandbox(sandbox) -> (value, fork_restored)`：delta checkpoint 模式下 rollback restore 会经状态变更图做 replace 式写入，fork 恢复的 sandbox channel 值可能仍是 `langgraph.types.Overwrite`；直接读 `sandbox["sandbox_id"]`/`.get()` 会崩，必须先解包。**返回值里的 `fork_restored=True` 是所有权信号**：被包装的形式重放的是 parent thread 的 sandbox 状态，调用者不得把它当作本次 run 拥有（例如去 release 它）（`overwrite.py:6-21`）。消费方：`sandbox/middleware.py:174,199,424-460`（fork-restored 只持有不释放）、`sandbox/tools.py:1382,1407,1541`、`agents/middlewares/view_image_middleware.py:191-194`、`subagents/executor.py:462-465`。

### 同路径文件锁 `file_operation_lock.py`

`get_file_operation_lock(sandbox, path)` 返回 `(sandbox.id or f"instance:{id(sandbox)}", path)` 粒度的 `threading.Lock`，不同 sandbox 的同名虚拟路径不互锁。锁表是 `WeakValueDictionary` + 独立 guard，长进程里锁在无人引用后自动移除，不会无界增长（`file_operation_lock.py:6-27`）。这是**进程内**串行化，不是跨进程/跨实例锁。

## 网络 Egress 控制 🆕（v2.1.0-rc0，#5152）

针对**本地管理的 Docker sandbox**（AIO 模式）的出站流量策略：

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  network:
    mode: allowlist            # open（默认，行为不变）| isolated（全禁）| allowlist
    allow_domains: [pypi.org, registry.npmjs.org]
    approval: prompt           # deny | prompt——被拒公共域可经 Human Input 卡片临时批准
    temporary_grant_ttl: 300   # 30-3600 秒
    proxy_image: ghcr.io/bytedance/deer-flow-sandbox-network-proxy:latest
```

- **实现**：独立 sidecar 容器 `docker/sandbox-network-proxy/` 做 DNS + 流量门控；sandbox 容器的出站经 proxy 路由
- **限制**：需要 **Docker Engine 28+**；不支持 Apple Container 与 provisioner 模式
- **始终拒绝**：私有、loopback、link-local、多播、云 metadata 地址（SSRF 防线）
- 人工审批通过 Human Input 卡片完成，授权带 TTL 自动过期

## Sandbox 身份共享与获取串行化 🆕（#5089）

- `sandbox/identity.py`：`sha256(user_id:thread_id)[:16]` 派生逻辑从各 provider 抽出为**单一实现**（此前 AIO/E2B/Tenki/OpenSandbox 各自为政）
- `sandbox/acquire_serialization.py`：acquire 路径统一串行化，消除多 provider 的并发获取竞态（leases + keyed lock，见 `tests/test_sandbox_leases.py`）

## 其他 v2.1.0-rc0 变更

- **E2B structured mount upload result**（#4884）：挂载上传返回结构化结果而非静默；`mount_upload_deadline` 可配置（#4876）
- **E2B replicas 收紧为进程本地容量**（breaking 边缘）：不再隐式跨进程共享预算
- **AIO Apple Container 切换保护**：macOS 上同前缀仍有受管 Docker 容器待对账时保持 Docker，不急着切 Apple Container
- **`MAX_SHELL_SESSIONS`**：AIO semver 镜像默认 10；`subagent_runtime.max_running + 1` 放不下时自动注入所需值（显式值必须 ≥ max_running+1）
- **远程 `list_dir`/`glob` 保留文件名尾部空白**（#4980）；Windows 命令执行加上边界（#4946）；本地 Docker sandbox 容器与端口绑定加固（#4986）
- **隐式 session 探测命令包 subshell**，防止 wedge shell 卡死 acquire（#5546，rc0 后 main，正式版随行）

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
