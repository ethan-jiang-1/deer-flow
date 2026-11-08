---
title: "sandbox"
description: "统一沙箱抽象 + 7 种 provider 实现；执行租约、受控出口（审批制 egress）、共享身份派生与 acquire 序列化、sandbox:execute 授权门控。2.2.0 增量：可重试的 shutdown、隔离记录（quarantine）、投机式 prewarm、bash 硬超时 124、路径起点边界与统一文件/下载契约。"
type: index
---

# sandbox

沙箱系统提供统一的执行环境抽象，Agent 不感知底层是本地文件系统还是容器/远端 VM。核心机制详见
[abstract-interface-and-seven-impls.md](abstract-interface-and-seven-impls.md)（文件名沿用历史，正文已同步 v2.2.0：接口、七实现与安全机制全部覆盖）。

## 主题索引

- **抽象接口**：`Sandbox` + `SandboxProvider`（acquire/get/release）；per-call `env` 密钥注入；`execute_command_in_scope`/`release_command_scope` 增量钩子；list_dir/glob/grep 失败语义（失败 → `OSError`/`FileNotFoundError`，绝不伪装成空结果，#5264/#5380）。
- **七种实现**：Local / AIO(Docker) / Provisioner(K3s) / BoxLite / E2B / Tenki / OpenSandbox，共享 `WarmPoolLifecycleMixin` warm-pool 生命周期。
- **跨实例 ownership**（#4206）：`sandbox.ownership.type: memory|redis` 的 `own:`/`del:` 双状态租约——回答"谁 reap"，`LAPSED` vs `LOST` 续约语义、orphan 对账 grace。
- **执行租约**（#5128）：进程内 `SandboxLeaseManager` holder 计数，最后持有者才 release；fork-restored 子执行与上传同步为非释放型持有者；重复取消的 reconcile 排水；lease/scope 上下文 ID 服务端所有。
- **受控出口**（#5152）：`sandbox.network`（`open|isolated|allowlist` + `prompt|deny` 审批），每沙箱一个 ICC-disabled network-proxy sidecar（`docker/sandbox-network-proxy/` + `community/aio_sandbox/network_proxy.py`）。
- **共享组件**（RFC #4741，#5089）：`identity.py` 的 `derive_sandbox_scope_token`（keyword-only、SHA-256/16-hex 兼容性契约）+ `acquire_serialization.py` 的有界 per-key 锁表与专用 bounded executor；`path_patterns.py` 的段边界/尾部匹配契约（含不污染全局 `re` 缓存的动态根扫描器）。
- **远端输出契约**（#5376/#5380）：`remote_list_dir.py`/`remote_search.py` 的"状态标记在 head 之后、SIGPIPE=成功截断、失败绝不伪装成空结果（`OSError` vs `FileNotFoundError`）"；`search.py` 的忽略清单/二进制/大小/行频限/root-relative glob 作用域。
- **授权门控**（`sandbox:execute`）：acquire **与复用**前的二进制 authz 检查（#5006 复用重查），deny → 友好 ToolMessage。
- **周边**：env 擦洗（`env_policy.py`）、路径安全（`path_patterns.py`，2.2.0 补齐**路径起点**边界 #7582）、孤儿对账、沙箱中间件（lazy init、fork-restored 保护）、本地容器硬化与端口绑定（#4986）。
- 🆕 **可重试的 shutdown**（2.2.0）：AIO / E2B / BoxLite / OpenSandbox / Local 五个 provider 统一「要么全清干净并关闭，要么复位成未关闭并抛出让调用方重试」。AIO 用 `_cleanup_retry_ids` 累积失败 id，E2B 用 `_shutdown_cleanup_pending`、BoxLite 用 `_loop_cleanup_pending` 放行重试。
- 🆕 **隔离记录 `quarantine.py`**（2.2.0，160 行）：`SandboxQuarantine` 把「残留旧代容器」写成本地标记（`{base}/sandbox-quarantine/`，键为 `sha256(...)[:16]`），`retire()` / `retire_replaced_generations()` 决定何时真正删除；`SandboxPolicyReplacementDeferredError` 拒绝在不安全时替换策略。
- 🆕 **投机式 prewarm `prewarm.py`**（2.2.0，232 行）：只有 `sandbox.prewarm: true` 且 provider 是 `AioSandboxProvider` 时启用；`should_prewarm_sandbox` 只认最后一条用户消息里的**代码围栏 / 路径 / 命令行 / traceback** 四类信号（URL 先剔除）；预算 `sandbox.prewarm_max_concurrent`（默认 1），**真实工具获取永不排在它后面**，任何失败静默降级。
- 🆕 **bash 硬超时 = `Exit Code: 124`**（2.2.0）：`LocalSandbox.execute_command` 超时后同时打人类提示和 coreutils 约定的 124，避免部分输出被当成成功；配套 `_run_posix_command` 用 daemon drain 线程 + 有界 pipe capture（不能用 `communicate()`，后台进程会握住管道）。
- 🆕 **统一文件契约**（2.2.0）：`read_file_contract.py`（55 行）集中 `READ_FILE_*` 标记、`count_file_lines`（`count("\n")` 而非 `splitlines()`）与 `split_file_lines`；`download.py`（39 行）给出 `DEFAULT_DOWNLOAD_LIMIT`=100 MiB / `MAX_IMAGE_BYTES`=20 MiB 与 `download_limit`（调用方只能收紧不能放宽）、`read_download_stream`（首次超预算即 `EFBIG`、不再消费后续块）。

→ Back to [parent README](../README.md)
