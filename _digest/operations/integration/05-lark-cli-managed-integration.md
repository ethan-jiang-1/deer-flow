---
title: "Lark CLI 托管集成（安装事务 / 凭据切换 / Pattern A-B）"
description: "把官方 lark-cli 技能包与沙箱运行时托管给 DeerFlow：全局只读技能包、每用户凭据树事务、sandbox_runtime_mode 四态与 broker 边界。"
topics: [integration, lark-cli, sandbox, broker]
---

# Lark CLI 托管集成（安装事务 / 凭据切换 / Pattern A-B）

> 本文只写**契约级**内容，不抄实现细节。源码真值（tag `v2.1.0`，345f08be）：
> `backend/packages/harness/deerflow/integrations/lark_cli.py`（2846 行，下文记 `lark_cli.py`）、
> `backend/packages/harness/deerflow/integrations/lark_broker.py`（457 行，下文记 `lark_broker.py`）。
> IM 通道侧的 Feishu 聊天机器人是另一件事，见 [04-im-channels.md](04-im-channels.md)；
> Pattern A/B 的简版概述在 [operations/channels/00-overview.md](../channels/00-overview.md) 的「Lark CLI 托管集成」。

## 0. 组件与落点

| 组件 | 源码/资产 | 契约 |
|------|-----------|------|
| 托管安装器 | `lark_cli.py` | 全局只读技能包 + 每用户凭据 + 沙箱运行时 + 配置/授权流程 |
| 凭据 broker | `lark_broker.py` | Pattern B：loopback 上的命令代理 + 沙箱 shim（纯 stdlib） |
| init 镜像（Pattern A） | `docker/lark-cli-init/` | 构建期下载校验二进制，运行期拷进共享 emptyDir |
| broker 镜像（Pattern B） | `docker/lark-cli-broker/` | 一个镜像两种模式：`serve` / `install-shim` |
| 远端沙箱侧 | `docker/provisioner/app.py` | 把 binary/凭据放到 init container/sidecar，报告 capabilities |
| 本地 AIO 侧 | `community/aio_sandbox/aio_sandbox_provider.py` | Gateway 下载运行时并按挂载表 bind-mount |
| 每调用注入 | `sandbox/tools.py:2088-2115` | 只对含 `lark-cli` 字样的 bash 命令注入环境覆盖 |
| HTTP 面 | `app/gateway/routers/integrations.py` | 7 个 `/api/integrations/lark/*` 端点（见 [02-api-reference.md](02-api-reference.md)） |

关键路径常量集中在 `lark_cli.py:114-126`：

- 技能包（全局，所有用户共享一份只读 pack）：`{integration_skills_dir}/lark-cli`（`lark_cli.py:270-276`；manifest 文件 `.deerflow-lark-cli-manifest.json`，`:114`）。
- 每用户凭据：`users/{user_id}/integrations/lark-cli/{config,data}`（`lark_cli.py:297-306`）。
- Gateway 自管 CLI：`{base_dir}/integrations/lark-cli/gateway-cli`（`:1153-1155`）。
- 本地 AIO 的运行时源目录：`{base_dir}/integrations/lark-cli/sandbox-cli`（`:1158-1160`）。
- 沙箱内固定容器路径（`:115-118`）：`/mnt/integrations/lark-cli/{config, config/locks, data, runtime}`。
- Flow 代际文件：每用户 `.deerflow-lark-cli-flow.json`（`:121`、`:1375-1376`）。

## 1. 安装事务与版本标记

### 1.1 安装是「全局只读包」，版本跟 Gateway 运行时 CLI 走

- 技能包只有一份，装在共享目录，不按用户分（`lark_cli.py:270-276`；测试 `test_install_lark_integration_installs_one_readonly_pack_for_all_users`）。安装后整树 `make_skill_tree_sandbox_readable()`（`:2712`）。
- 技能清单固定 27 个 `lark-*`（`lark_cli.py:146-174`），宁可缺一个就整体失败（`:2795-2798`）。
- 版本解析链（`install_lark_integration`，`:1820-1856`）：
  1. 先 `_ensure_managed_gateway_lark_cli()`（`:2120-2141`）：查 GitHub `releases/latest`（`:2548-2570`），与现有 CLI 版本不同才用 `npm install --prefix <gateway-cli> @larksuite/cli@<ver>` 装（`:2144-2188`）；npm/GitHub 不可达但已有可用 CLI 时保留旧 CLI 并只记 warning（`:2134-2141`）。
  2. 用**实际运行时 CLI 的版本**作为技能包版本并下载该版本源码包（`:1836-1839`）；只有 CLI 版本不可解析时才退到 `FALLBACK_LARK_CLI_VERSION="v1.0.65"`（`:96`、`:1778-1789`）。
  3. 本地 AIO（非远端 provisioner）再 `_ensure_managed_sandbox_lark_cli()` 下载同版本 Linux 运行时（`:1853-1856`、`:1407-1464`）。
- `sandbox.use` 含 `aio_sandbox` 才算 AIO（`_uses_aio_sandbox`，`:1871-1876`）；`sandbox.provisioner_url` 非空才算远端 provisioner（`_uses_remote_provisioner`，`:1888-1890`）。
- `_install_managed_gateway_lark_cli` 故意**不带** `--ignore-scripts`（`:2155-2161`）：postinstall 要拉平台二进制；代价是管理员触发的安装会以 Gateway 权限执行官方包及其依赖的安装脚本。

### 1.2 完整性：不 pin 归档字节哈希，改 pin 内容哈希

- 下载源固定为官方 GitHub host + HTTPS，版本只能来自运行时 CLI 或 fallback（模块 docstring `:20-28`；`_lark_archive_url` `:2599-2603`）。
- 每个归档成员过结构防护：zip-slip / symlink / 可执行二进制前缀 / 解压总量上限（`:2735-2767`，`LARK_CLI_MAX_ARCHIVE_BYTES` / `LARK_CLI_MAX_EXTRACTED_BYTES`，`:111-112`）。
- 归档成员名支持 `.../skills/<name>/...` 与 `<name>/...` 两种根（`:2770-2792`）；归档根 `cli-X.Y.Z/` 会被用来推断版本（`:2658-2672`）。
- 每个技能目录的 `SKILL.md` 必须能解析且声明名与目录名一致（`:2795-2806`）。
- manifest 记录的是**注入 DeerFlow guidance 之后**的整树内容 SHA-256（`_content_sha256` `:2636-2655`，调用点 `:2710`），因此重装能审计出「有效内容变了」而不管 GitHub 重打包是否改字节（`:1859-1862` 的 `content_changed`）。
- 本地 AIO 运行时同样有独立校验：`bin/lark-cli` + `linux-{amd64,arm64}/lark-cli` 必须存在、可执行、且整树无 symlink（`:1269-1282`）；下载走官方 release asset + `checksums.txt` SHA-256 比对（`:1434-1442`）。`DEER_FLOW_LARK_CLI_SANDBOX_RUNTIME_DIR` 可预置气隙目录（`:102`、`:1428-1432`）。
- `DEER_FLOW_LARK_CLI_SKILLS_ARCHIVE` 可预置源码包路径（`:101`、`:1826-1834`）。

### 1.3 替换是原子的，且有回滚

- 锁：`integration_skills_dir/.lark-cli.install.lock`，`flock` + 进程内 `threading.Lock` 双层（`:1296-1315`、`:2685-2689`）。
- 流程（`:2692-2732`）：临时目录 staging → 解压/校验/注入 guidance/算内容哈希/写 manifest/放宽沙箱可读 → 旧目录 `rename` 成备份 → staging `rename` 成正式 → 删备份。
- 异常时若正式目录不存在则把备份改回来（`:2727-2730`）；备份删除失败**不算**安装失败（`:2720-2725`，测试 `test_install_lark_integration_succeeds_when_backup_cleanup_fails`）。
- 本地 AIO 运行时替换同样 staging→备份→rename→失败还原（`:1419-1464`），并有自己的 `.sandbox-cli.install.lock`。

### 1.4 guidance 注入与「version marker」约定

- 注入点是 `lark-shared/SKILL.md`（`_append_deerflow_lark_shared_guidance`，`:2809-2833`）。当前 marker 常量：`<!-- deerflow-lark-cli-auth-guidance-v3 -->`；legacy 列表含 v1/v2（`:142-143`）。
- 判定语义：
  - 正文里已有**当前** marker → 直接返回，不重写（`:2812-2813`）。
  - 命中 legacy marker → 从该 marker 处截断，再追加当前版本块（`:2814-2817`）。
  - 都没有 → 追加。
- 因此「guidance 文本变更」的正确做法是**把 marker 加版本号**（v3→v4）并把旧 marker 放进 legacy 列表；改正文却不 bump marker，重装时不会刷新已安装文本。此约定只由常量与调用点承载，当前树内没有断言 marker 升级行为的测试。
- 重装刷新链路：重装 → 内容哈希变化 → status/manifest 反映新版本 → `install_lark_integration` 消息补充 "Skill content changed since the previous install."（`:1858-1868`）。gateway 侧成功后路由还会 `refresh_skills_system_prompt_cache_async()`（`routers/integrations.py:274`）。

### 1.5 没有卸载路径（当前 tag 的真实缺口）

全树没有 `uninstall` 实现或端点：`lark_cli.py` / `lark_broker.py` / `routers/integrations.py` 均无对应函数（grep 无命中）。所谓「卸载」只能由管理员手工删除 `{integration_skills_dir}/lark-cli` 与用户凭据目录。这不是本文的推测，而是源码缺失；若需要契约化卸载，必须先补源码。

## 2. 每用户凭据树与事务性切换

### 2.1 目录硬化契约

- 树根、`config`、`config/locks`、`data` 全部建为 `0700` 目录，文件 `0600`（`ensure_lark_cli_credential_tree`，`:309-332`；`_harden_posix_credential_tree`，`:386-390`）。
- 任何 symlink / Windows reparse point 在**下降前**就被拒（`:417-454`）。
- Windows 走**句柄相对**遍历（`:335-368`、`:1029-1076`）：先按名打开可信 base，之后所有子项/新建都相对已打开的父句柄（`RootDirectory`），枚举/加 ACL/下降都绑定到句柄而非路径名；拒绝 reparse point 与硬链接文件（`:1046-1051`）；用 `_Windows_EXCLUSIVE_SHARE` 避免 ACL 提前传播到未校验子项（`:519-522`）。
- 硬化有独立锁域（`_lark_hardening_lock`），与凭据锁分开以免自死锁（`:1323-1348`）。
- CLI 可能写出新的明文 token，所以 `config init` 与每个 OAuth 命令结束后都在 `finally` 里重新硬化整树（`:2347-2348`、`:2460-2464`）。

### 2.2 切换事务的顺序就是契约（先清 data，再 config init）

`_replace_lark_app_credentials_locked`（`:2366-2373`）是唯一顺序来源：

1. `ensure_lark_cli_credential_tree()`；
2. 进入 `_lark_credential_transaction()`：把 `config`/`data` 完整拷进凭据根下的私有快照目录 `.switching-lark-app-*`（`:2386-2408`；快照位置刻意落在已硬化的根内，防路径交换把快照重定向到外部）；
3. `_clear_directory_contents(data)` —— **先清旧 OAuth data**；
4. `_save_lark_app_config_with_cli()` → `lark-cli config init --app-id … --app-secret-stdin --brand …`（`:2318-2336`）；
5. `_revoke_lark_auth_from_snapshot(snapshot)` —— 用**快照里的旧 config+data** 跑 `lark-cli auth logout --json`，撤销旧 app 的远端令牌（`:2418-2438`）；
6. 任何一步抛异常 → `_restore_lark_credential_tree()` 把 `config`/`data` 整体恢复成快照（`:2411-2415`）并重新硬化。

**为什么不能反过来（先 init 再清）**：Linux 上 `lark-cli config init` 会把新 app secret 写进 **data 目录下的文件型 keychain**；若之后才清 data 目录，`config.json` 会留下悬空的 keychain 引用。这一因果在 `deerflow/AGENTS.md`「Managed Lark CLI credentials」段落里明确写出，并与 #4820 的历史修复一致（旧实现「先写新凭据再清目录」会把刚写入的 app_id/app_secret 一并清掉）。

### 2.3 校验新凭据用「一次性临时树」，不碰现网

`_validate_lark_app_credentials_with_cli`（`:2351-2363`）在系统临时区建私有目录（先建边界再写内容，`:370-383`），把 `config`/`data` 指到那里跑一次 `config init`——即用官方 CLI 的 live tenant-token 探测验真；失败不污染当前凭据。`set_lark_app_credentials` 在校验通过后才进锁与代际推进（`:2002-2036`）。

### 2.4 Flow 代际（generation）防止过期完成

- 每次 config/auth 起点写 `.deerflow-lark-cli-flow.json`（原子替换 + `0600`，`:1379-1390`），返回 `generation`。
- 完成端点必须带同一 generation，不符抛 `LarkFlowSupersededError`（`:1399-1404`）→ 路由 409（`routers/integrations.py:323-324`、`:371-372`、`:396-397`）。
- 直接切换 app 会推进代际（`:2023`），因此不会让进行中的旧流程继续生效。

## 3. `sandbox_runtime_mode` 四态与探测契约

`_resolve_sandbox_runtime_readiness`（`lark_cli.py:1615-1659`）是四态唯一权威；`get_lark_integration_status`（`:1717-1753`）把它投影成 `sandbox_runtime_mode` / `sandbox_runtime_ready` / `sandbox_runtime_detail`，HTTP 字段见 `routers/integrations.py:84-86`。

| mode | 触发条件 | ready 判据 | 失败 detail |
|------|----------|-----------|-------------|
| `none` | 非 AIO（`sandbox.use` 不含 `aio_sandbox`） | 恒 `False` | "Sandbox does not run lark-cli in this configuration."（`:1636-1637`） |
| `gateway-download` | AIO 且无 `provisioner_url` | `_validate_lark_cli_sandbox_runtime(sandbox-cli)` 通过（`:1653-1659`） | "The managed sandbox lark-cli runtime is not installed." |
| `init-container` | AIO 且有 `provisioner_url` | provisioner capabilities 报 `lark_cli_init_image=true`（`:1649-1650`） | 不可达 / 未配置镜像（`:1643-1651`） |
| `broker` | 同上，但 capabilities 报 `lark_cli_broker_image=true` | `True`（`:1647-1648`） | — |

- `probe=False` 时远端路径不联网，直接返回 `("init-container", False, None)`（`:1640-1641`）；Settings 状态路由传 `check_runtime=True`（`routers/integrations.py:262`）。
- **broker 压过 init-container**：两个镜像都配置时选 `broker`（`:1645-1650`）。

### 3.1 Gateway → provisioner 探测契约

`_probe_provisioner_capabilities`（`:1893-1919`）：

- `GET {provisioner_url}/api/capabilities`；`sandbox.provisioner_api_key` 非空则带 `X-API-Key`；
- 响应只取两个布尔键：`lark_cli_init_image`、`lark_cli_broker_image`（`:1914-1917`）；
- 默认 timeout `5.0s`（用户在看 Settings 页），不可达/非 dict 一律返回 `None`（`:1918-1919`）。
- provisioner 侧同一组键由 `GET /api/capabilities` 返回（`docker/provisioner/app.py:1180-1187`），值来自 `LARK_CLI_INIT_IMAGE` / `LARK_CLI_BROKER_IMAGE` 两个环境变量（`app.py:68`、`:77`；compose 透传见 `docker/docker-compose.yaml:181-186`，dev 见 `docker-compose-dev.yaml:74-77`）。

### 3.2 bash 热路径的 broker 探测

`sandbox_lark_broker_active`（`:1678-1714`）只在每次含 `lark-cli` 的 bash 调用前被问一次，因此有独立预算：

- 条件：AIO + 有 `provisioner_url` + capabilities 的 `lark_cli_broker_image`（`:1709-1711`）；
- 超时 `1.5s`（`:1672`）；结果缓存：正 `60s` / 负 `300s`（`:1662-1667`）；缓存读写有锁（`:1675`、`:1700-1706`、`:1712-1713`）；
- 任一环节异常/取不到 config → `False`（`:1691-1697`）。

### 3.3 fail-open / fail-closed 清单

| 场景 | 行为 | 依据 |
|------|------|------|
| provisioner 探测失败 | 状态报「未就绪」（fail-closed），broker 判定为 False → 退回 Pattern A 挂载（fail-safe，不丢鉴权） | `:1643-1644`、`:1711` |
| 取不到 app config | `sandbox_lark_broker_active` 返回 False | `:1691-1697` |
| 构造 bash 的 lark 环境覆盖失败 | 记 warning，命令**不带**托管鉴权继续跑（不注入到错误身份） | `sandbox/tools.py:2108-2115` |
| 管理员判定（仅用于 host path 脱敏） | 非管理员/判定异常一律当非管理员（fail-closed） | `routers/integrations.py:41-51`、`:182-207` |
| 状态路由内部异常 | 500，绝不谎报 ready | `routers/integrations.py:264-266` |
| broker 传输失败 | shim 非 0 退出（默认 127），broker 异常返回结构化 500 | `lark_broker.py:140-175`、`:356-368` |

## 4. Pattern A / Pattern B 边界与沙箱安全约束

### 4.1 Pattern A：二进制可直接调用 + 凭据目录挂进沙箱

- 远端：`LARK_CLI_INIT_IMAGE` 配置后 provisioner 加 `lark-cli-runtime` emptyDir + init container，运行期把 `/opt/lark-cli/.` 拷进去（`docker/lark-cli-init/entrypoint.sh`、`docker/lark-cli-init/README.md`）；运行期目录布局与 Gateway 写法逐字节一致（`build-runtime.sh` 里 launcher 与 `LARK_CLI_SANDBOX_LAUNCHER_SCRIPT` 相同，`lark_cli.py:131-140`，测试 `test_init_image_launcher_matches_python_constant`）。
- 本地 AIO：Gateway 自己下载到 `sandbox-cli` 并 bind-mount（`:1407-1464`、`aio_sandbox_provider.py:1235-1246`）。
- **凭据仍在沙箱内**。本地 AIO 的三条挂载（`aio_sandbox_provider.py:1226-1246`）：
  - `config` → `/mnt/integrations/lark-cli/config`，**只读**（长期 `appSecret`）；
  - `config/locks` → `/mnt/integrations/lark-cli/config/locks`，**可写**（新版 `lark-cli` 的协调文件）；
  - `data` → `/mnt/integrations/lark-cli/data`，**可写**（可刷新的 OAuth token）。
  - 仅当本地 `sandbox-cli` 目录存在时才追加 `runtime` 只读挂载。
- 因此 Pattern A 的定性是**防篡改，不防读取**：任意沙箱进程都能读 `config`/`data`（README.md:1040-1049 的 `<Sandbox trust boundary>`；`aio_sandbox_provider.py:1221-1222`）。

### 4.2 Pattern B：凭据文件不出现在沙箱

- 同一镜像两种模式，按第一个参数分派（`lark_broker.py:439-453`、`docker/lark-cli-broker/entrypoint.sh`）：
  - `serve`（默认 CMD）→ 在 `127.0.0.1:8788` 跑 broker HTTP 服务，凭据指向 sidecar 专属 `/var/lark/{config,data}`（`docker/lark-cli-broker/Dockerfile` 的 `ENV`）；
  - `install-shim <dest>` → 把 launcher + shim + `.deerflow-lark-cli-runtime.json`（`kind: "shim"`）写进共享 emptyDir，默认 `/mnt/integrations/lark-cli/runtime`（`lark_broker.py:394-424`、`:443`）。
- 沙箱内 `bin/lark-cli` 是 `/bin/sh` launcher，负责解析 Python 3 再 exec `bin/lark-cli-shim.py`（`:90-115`）；解析不到 Python 时**大声失败** exit 127 并提示设置 `DEERFLOW_LARK_BROKER_PYTHON`，而不是 ENOEXEC（`:99-109`、`:86`）。shim body 与 launcher 都来自进程内常量，镜像副本不会漂移（模块注释 `:82-85`、`:394-408`）。
- 沙箱只多拿 `runtime` 只读挂载 + `DEERFLOW_LARK_BROKER_URL` 环境变量；`config`/`data` 挂载被 provisioner 移到 sidecar（`docker/provisioner/app.py:289-320`、`:890-955`、`:980-985`）。远端 payload 里 Gateway **仍然会转发**这三个挂载，只是由 provisioner 决定落到 sidecar（`community/aio_sandbox/remote_backend.py:85-126`）。
- 边界：broker 只可能出现在「AIO + 远端 provisioner」组合；本地 AIO 永远是 gateway-download（`sandbox_lark_broker_active` 条件，`:1709-1711`）。两种场景都由技能包已安装驱动（`aio_sandbox_provider.py:1168-1197`：`_lark_integration_active` → `lark_skills_installed`）。

### 4.3 Broker 环回 wire 契约

| 项 | 值 | 依据 |
|----|----|------|
| 地址/端口 | `127.0.0.1:8788`（固定，沙箱与 sidecar 共享 Pod 网络命名空间） | `lark_broker.py:39-40`、`:36-38` |
| 执行 | `POST /v1/exec`，body `{"args": [...], "stdin_b64": "..."}` → `{exit_code, stdout_b64, stderr_b64, truncated}` | `:42`、`:333-380` |
| 健康 | `GET /v1/health` → `{"ok": true}` | `:43`、`:327-331` |
| 注入环境 | broker 自己注入 `LARKSUITE_CLI_CONFIG_DIR/DATA_DIR/...`，客户端无法覆盖 | `:210-221`、`:274` |
| Shell 注入 | argv 列表 + `shell=False`，沙箱参数不可能变成第二条命令 | `:263-283` |
| 上限 | 请求 1 MiB / 输出 4 MiB / 子进程 120s / 并发 8 / 每连接 socket 30s | `:46-55`、`:294-297`、`:306-313` |
| 退出码语义 | 126 = 被 denylist 拒绝；124 = 超时；127 = broker 里找不到二进制 | `:270-287` |
| 传输失败 | shim 非 0 退出（默认 127），绝不伪装成功 | `:118-122`、`:140-175` |
| 可选 denylist | `DEERFLOW_LARK_BROKER_DENY_SUBCOMMANDS`（逗号分隔命令前缀，按前导非 flag token 匹配，`config --json show` 也能被 `config show` 拦住） | `:57-58`、`:224-252`、`:202-208` |
| 能力缺口 | **cwd 不转发**：broker 在 sidecar 的工作目录运行，看不到沙箱文件系统；按沙箱相对路径读写文件的子命令在 broker 模式不可用，绝对路径也指 sidecar | `:124-129`、`docker/lark-cli-broker/README.md` |

### 4.4 哪些路径/凭据进容器（安全约束汇总）

- 进沙箱（Pattern A）：`config`(RO) / `config/locks`(RW) / `data`(RW)，以及 `runtime`(RO)。
- 进沙箱（Pattern B）：仅 `runtime`(RO) + `DEERFLOW_LARK_BROKER_URL` env；shim 与 launcher 由 init container 现场写。
- 只进 sidecar（Pattern B）：`/var/lark/config`(RO) / `/var/lark/config/locks`(RW) / `/var/lark/data`(RW)（`docker/provisioner/app.py:890-955`）。
- Gateway 侧写口令的路径从不进容器：`appSecret` 由 `config init --app-secret-stdin` 写入每用户 `config`（`:2318-2336`，Gateway 上执行）。
- broker sidecar 的 securityContext 是 `privileged=False, allow_privilege_escalation=False`（`docker/provisioner/app.py:948-951`）；init 容器另有独立 `secure` 上下文（`app.py:859`）。注意主沙箱容器本身是 `allow_privilege_escalation=True`（`app.py:1054-1055`），不在同一条约束里。
- 沙箱从共享 emptyDir 只读拿到 launcher/shim；真实二进制只存在于 sidecar 镜像的 `/opt/lark-cli`（`docker/lark-cli-broker/Dockerfile` 的 `DEERFLOW_LARK_BROKER_CLI=/opt/lark-cli/bin/lark-cli`、`lark_broker.py:394-408`）。

## 5. 配置 env overlay 契约

`lark_cli_env_overlay(user_id, *, sandbox_paths=False, broker=False)`（`:1479-1513`）：

| 分支 | 注入内容 |
|------|----------|
| `broker=True` | 仅 `PATH`（`/mnt/integrations/lark-cli/runtime/bin:...`）+ `DEERFLOW_LARK_BROKER_URL`；**不含** `LARKSUITE_CLI_CONFIG_DIR/DATA_DIR`（`:1491-1495`） |
| `sandbox_paths=True` | `LARKSUITE_CLI_CONFIG_DIR=/mnt/integrations/lark-cli/config`、`DATA_DIR=/mnt/integrations/lark-cli/data`、两个 notifier 关闭、容器 PATH（`:1496-1498`、`:1511-1512`） |
| 默认（Gateway 本机） | 每用户 config/data 绝对路径 + notifier 关闭；若存在自管 CLI，则把其 `node_modules/.bin` 前置到 PATH（`:1499-1510`） |

调用侧：`sandbox/tools.py:2091-2115` 只在命令匹配 `(?<![A-Za-z0-9_.-])lark-cli(?![A-Za-z0-9_.-])` 且沙箱非 local 时注入；`broker = sandbox_paths and sandbox_lark_broker_active()`（`tools.py:2104-2106`）。

## 6. HTTP 面（集成视角）

7 个端点：`GET /lark/status`（非管理员脱敏 host path）、`POST /lark/install`（管理员）、`POST /lark/config/{start,complete,credentials}`、`POST /lark/auth/{start,complete}`（`routers/integrations.py:259-404`）。异常→状态码映射见 [02-api-reference.md](02-api-reference.md) 的「集成视角：异常 → HTTP 摘要」。
授权流程契约要点：

- `auth/start` 默认最小登录（`auth login --no-wait --json`），可选 `domains` / 精确 `scope` / `recommend`，可复用父流程 generation（`:2039-2081`）。
- `auth/complete` 的 `wait_timeout_seconds` 被夹在 `5..45`（`:107-109`、`:2096-2097`），完成时做一次 **live verify**；`probe_lark_auth(verify=False)` 只读本地 token，`authenticated` 但 `verified=False`（`:1546-1612`）。状态枚举：`unavailable` / `not_configured` / `not_authorized` / `error` / `authenticated`。

## 7. 运维要点

- 镜像 tag 应编码 lark-cli 版本，与上游独立升级；CI 由 `.github/workflows/lark-cli-images.yaml` 发布 `ghcr.io/<owner>/deer-flow-lark-cli-{init,broker}:<lark-cli-version>`（推 `lark-cli-v*` tag 或手动输入版本）。构建 context 是**仓库根**（broker 模块在 `backend/` 下）：`docker build -f docker/lark-cli-broker/Dockerfile .`。
- 启用开关只在 provisioner 侧：`LARK_CLI_INIT_IMAGE`（Pattern A）、`LARK_CLI_BROKER_IMAGE`（Pattern B，两者都设时 broker 生效）；不设即特性关闭、行为不变。Gateway 不需要为远端模式预下载运行时（`lark_cli.py:1853` 只在本地 AIO 分支下载）。
- 排障面：`GET /api/integrations/lark/status` 的 `sandbox_runtime_mode/ready/detail`、`runtime_version_mismatch`（manifest 版本 vs 运行时 CLI 版本的数字核比较，任一侧未知则不算 mismatch，`:1756-1775`）、`latest_available_version`（GitHub 查询失败返回 None，1h TTL，不阻塞 UI，`:2573-2596`）。
- 气隙：`DEER_FLOW_LARK_CLI_SKILLS_ARCHIVE`（技能包）与 `DEER_FLOW_LARK_CLI_SANDBOX_RUNTIME_DIR`（本地 AIO 运行时）。

## 8. 已知的文档级观察（非契约，供后续核实）

- `install_shim` 写入的 `.deerflow-lark-cli-runtime.json` 带 `kind: "shim"`（`lark_broker.py:421-423`），其 docstring 称「运行时校验器据此知道 `linux-*` 二进制刻意缺席」，但在本 tag 的树内 `kind` 只有写入方、没有读取方（`lark_cli.py:1420` 只读 `version`）。若要依赖 `kind` 做校验，需先补消费者。
- guidance marker 的 bump 纪律（§1.4）无测试保护。（`operations/channels/00-overview.md` 的源码索引曾把 `lark_cli.py` 记为 1724 行——真值 **2846** 行，已在同一轮同步中修正。）
