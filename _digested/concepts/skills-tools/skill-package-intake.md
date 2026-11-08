---
title: "Skill 包摄入：解析、安装与 SkillScan 规则表"
description: "`skills/parser.py` 的 frontmatter 解析边界、`skills/installer.py` 的 .skill 安装链路与失败清理、SkillScan 全量规则表/上限/异常类型。"
topics: [skills, installer, parser, skillscan, contract]
---

# Skill 包摄入：解析、安装与 SkillScan 规则表

主文档 [`skill-md-and-tool-assembly.md`](skill-md-and-tool-assembly.md) 已覆盖加载/投影/导出/写入门；本文补它没展开的三块：**frontmatter 解析边界（`parser.py`）**、**`.skill` 安装链路与失败清理（`installer.py` + storage）**、**SkillScan 规则表/上限/异常类型**。

---

## 1. `skills/parser.py` — frontmatter 解析边界

三个公开解析函数，全部在 `parse_skill_file()`（`:190-273`）里被消费。设计基调是**"字段级畸形降级、结构级畸形拒收"**。

### 1.1 `parse_allowed_tools(raw, skill_file) -> tuple[str, ...] | None`（`:106-134`）

| 输入 | 行为 |
|------|------|
| `None`（字段省略） | 返回 `None` |
| `str`（可移植标量形式） | 走状态机分词，**开启别名归一化**（`:118-120`） |
| `list` | 逐条 `strip()`，**不做别名归一化**（`normalize_tools=False`，`:123-124,133`），MCP/运行时工具名原样保留大小写 |
| 其它类型 | `ValueError`（`:121-122`） |
| 列表内含非字符串 | `ValueError`（`:128-129`） |
| 条目 strip 后为空 | `ValueError`（`:131-132`） |
| 显式空字符串 `""` | 分词结果为空 → 返回**空元组** `()`（非 `None`） |

**状态机 `_split_portable_allowed_tools`（`:32-77`）的 fail-closed 边界**：

- 只有 `depth == 0` 且在引号外的空白才切分（`:58-62`）；引号内、`(...)` 内的空格保持在同一 token。
- `\` 转义：反斜杠**本身与下一个字符都原样保留进 token**（`:45-48`），不做反转义——所以 `Bash\(x\)` 会带着反斜杠进入字面工具名（DeerFlow 只做精确名匹配，见 `tool_policy.py`）。
- `)` 在 `depth == 0` 时 → `ValueError "unmatched closing parenthesis"`（`:66-67`）。
- 结束时引号未闭合 → `ValueError "unclosed quote"`（`:71-72`）；`depth != 0` → `ValueError "unclosed parenthesized pattern"`（`:73-74`）。
- 最后一个 token 会被 flush（`:75-76`）。

**别名映射**（`_PORTABLE_TOOL_ALIASES`，`:13-22`，8 条）：`Bash→bash`、`Edit→str_replace`、`Glob→glob`、`Grep→grep`、`Read→read_file`、`WebFetch→web_fetch`、`WebSearch→web_search`、`Write→write_file`。`_normalize_unscoped_allowed_tool` 遇到**含 `(` 或 `)` 的条目直接原样返回**（`:25-29`）；未知名（含已知别名的小写拼法）保持原样。

**与安装门的关系**：`validation.py:82-85` 也调 `parse_allowed_tools`，把 `ValueError` 的宿主路径替换成字面 `SKILL.md` 后返回 400（`str(e).replace(str(skill_md), SKILL_MD_FILE)`）。而 `parse_skill_file`（`:243-247`）捕获同一异常后**记 error 日志并返回 `None`**——即"解析失败 ⇒ skill 直接不加载"，不是降级。

### 1.2 `parse_required_secrets(raw, skill_file) -> tuple[SecretRequirement, ...]`（`:137-171`）

- `None` → `()`；非 `list` → `ValueError`（`:147-150`）。
- 字符串条目 → `name=item.strip(), optional=False`（`:155-156`）。
- mapping 条目 → `name = str(item.get("name") or "").strip()`，`optional = bool(item.get("optional", False))`（`:157-159`）。
- 其它类型 → warning + 跳过（`:160-162`）。
- `name` 必须匹配 `^[A-Za-z_][A-Za-z0-9_]*$`（`_ENV_VAR_NAME_RE`，`:12`）；不匹配 → warning + 跳过（`:164-166`）。
- **重名静默去重、保留首次出现**（`:167-169`）。

⚠️ **安装门 / 加载器的校验不对称（契约级陷阱）**：`validation.py:87-89` 只检查 `required-secrets` 是 list，`validation.py:91-93` 只检查 `secrets-autonomous` 是 bool——**不校验条目名**。所以 `required-secrets: ["not a var"]` 能通过安装/写入门：`parse_skill_file` 的 `try/except ValueError` 只在"整个字段不是 list"时触发（`:249-253`），条目级畸形根本不抛，于是交给 `parse_required_secrets` 逐条 `warning` + 丢弃。净效果：**畸形条目会让该 secret 永久不生效，但 skill 照常加载**；排查时看 `logger.warning("Ignoring required-secrets entry with invalid env var name ...")`（`:165`）。

### 1.3 `parse_secrets_autonomous(raw, skill_file) -> bool`（`:174-187`）

`None` → `True`（默认允许自主绑定）；`bool` → 原值；**其它类型 → warning + `False`**（`:186-187`）。注释写明这是 fail-closed 到"更不易注入"的方向（`:179-180`），与 `validation.py:91-93`（畸形即 400 拒收）在**写入门更严、加载器更宽**上互补。

### 1.4 `parse_skill_file()` 的拒收面（`:190-273`）

返回 `None`（skill 不加载，不抛）的情形：文件不存在或 basename ≠ `SKILL.md`（`:202-203`）；无 `---` frontmatter（`:210-212`）；YAML 语法错（`:216-218`，日志带行号 + `mapping values are not allowed here` 的引号提示，`_format_yaml_error` `:80-103`）；frontmatter 非 dict（`:219-221`）；`name`/`description` 缺失、非字符串、或 strip 后为空（`:227-237`）；`allowed-tools`/`required-secrets` 的 `ValueError`（`:243-253`）。整体还有一层 `except Exception` → `logger.exception` + `None`（`:271-273`）。`relative_path` 省略时默认取 skill 目录名（`:263`）；`enabled=True` 只是占位，真实启用态来自 extensions config / per-user state（`:266`）。

---

## 2. `skills/installer.py` — `.skill` 安装链路

`installer.py`（329 行）是**纯业务逻辑、无 FastAPI 依赖**的共享安装实现（模块 docstring `:1-5`），Gateway 与 embedded client 都委托它。真正的编排在 storage 侧的两个 `ainstall_skill_from_archive`（`storage/local_skill_storage.py:119-149`、`storage/user_scoped_skill_storage.py:325-358`），installer 提供所有"危险步骤"。

```
storage.ainstall_skill_from_archive(archive_path)
  └─ asyncio.to_thread(_prepare_skill_archive)                      # worker 线程
       ① zipfile.ZipFile 打开（BadZipFile/IsADirectoryError → ValueError）   local:180-185
       ② scan_archive_preflight_or_raise(path, app_config=...)              local:188
       ③ safe_extract_skill_archive(zf, tmp_path)                           local:189
       ④ resolve_skill_dir_from_archive(tmp_path) → skill_dir               local:191
       ⑤ _validate_skill_frontmatter(skill_dir)                             local:193-195
       ⑥ skill_name 安全字符检查（/ \ ..）+ target.exists() → 409           local:196-201
  ├─ _scan_skill_archive_contents_or_raise(skill_dir, skill_name, ...)      local:132  # async LLM 扫描，留在 event loop
  └─ asyncio.to_thread(_commit_skill_install)                             # worker 线程
       projection 临界区内 staging copytree → _move_staged_skill_into_reserved_target
  finally: 清理 mkdtemp 抽取目录（best-effort + 5s 超时）                    local:136-143
```

### 2.1 归档预检与安全抽取

- **`scan_archive_preflight_or_raise(archive_path, *, app_config=None)`（`:256-266`）**：先查 `skill_scan_enabled(app_config)`，**关闭时直接 return（不扫描）**（`:257-258`）；否则调 `scan_archive_preflight()`，只在 `result["blocked"]` 为真（存在 CRITICAL）时抛 `SkillSecurityScanError(..., findings=仅 CRITICAL, skill_name=None)`（`:260-266`）。它是**解压前的第一道门**：只看 ZIP 成员元数据 + 限量 peek，不落盘。
- **`safe_extract_skill_archive()`（`:115-177`）** 是解压路径的独立防线，与 kill switch 无关、每次安装都生效：
  - 成员数先查：`len(infos) > max_entries`（默认 **4096**）在**任何逐成员工作之前** early-abort（`:138-146`）——注释特意点明"这是每次安装都走的路径，不能依赖可选的 SkillScan"。
  - 逐成员：`is_unsafe_zip_member` → `ValueError`（`:149-150`）；**符号链接条目只 warning 并 `continue`，不物化**（`:152-154`）；归一化后 `member_path.resolve().is_relative_to(dest_root)` 再查一次逃逸（`:156-159`）。
  - 写盘时**第一块就查可执行 magic**（`is_executable_binary_prefix`，ELF/PE/Mach-O）并抛 `ValueError`（`:169-170`）；累计字节数超 `max_total_size`（默认 **512 MiB**）抛错（`:172-175`）。
  - POSIX 上按 `external_attr >> 16 & 0o111` 还原 `0o755`/`0o644`（`:176-177`）。
- **`is_unsafe_zip_member`（`:51-82`）**：绝对路径（POSIX 或 `PureWindowsPath` 都查）、`..` 段、以及**任何位置的 `:`** 一律拒。冒号那条注释解释得很清楚：NTFS 上 `scripts/run.sh:hidden.txt` 会变成前一个路径组件的 Alternate Data Stream，对 `rglob`/`os.walk` 不可见，于是能绕过基于目录遍历的安全扫描。
- **`is_symlink_member`（`:85-88`）**：`external_attr >> 16` 的 `S_ISLNK`。
- **`resolve_skill_dir_from_archive`（`:96-112`）**：过滤 dotfile 与 `__MACOSX`（`should_ignore_archive_entry`，`:91-93`，判据是 `path.name.startswith(".") or path.name == "__MACOSX"`）；过滤后为空 → `ValueError("Skill archive is empty")`；**恰好一个目录** → 解包该目录作为 skill 根，否则以解压根为根。注意过滤只影响"根判定"，**抽取阶段仍会把 dotfile 写盘**。

### 2.2 内容扫描（静态 + LLM 双层）

- `_scan_static_skill_archive_or_raise`（`:273-279`）：`asyncio.to_thread(enforce_static_scan, ...)`；`StaticScanBlockedError` / `StaticScannerError` 都翻译成 `SkillSecurityScanError`（携带 `findings`/`skill_name`）。
- `_scan_skill_archive_contents_or_raise`（`:287-317`）：
  1. 先跑静态扫描拿 `static_findings`；
  2. 单独扫根 `SKILL.md`（`executable=False`）；
  3. 遍历 `sorted(skill_dir.rglob("*"))` 中的所有文件：**嵌套 `SKILL.md` 无条件硬失败**（`:298-299`，与 SkillScan 的 CRITICAL 规则对齐，但这里是"安装了也加载不出来"的直接拒收）；
  4. 代码文件（`_is_code_file`，`:198-207`：`package_files.is_code_path` 或"无后缀 + `#!`"）走 `executable=True`；`scripts/**` 与 `references|templates` 下的文本类支持文件（`_PROMPT_INPUT_SUFFIXES`，`:31-32,180-187`）走 `executable=False`。
- `_scan_skill_file_or_raise`（`:231-253`）：非 UTF-8 → `SkillSecurityScanError`；`scan_skill_content(..., static_findings=)` 的决策 `block` → 拒；`executable=True` 且决策 ≠ `allow` → 拒；决策不在 `{allow, warn}` → 拒（`:252-253`）。**静态 findings 按文件过滤后透传给 LLM 扫描器**（`_findings_for_file`，`:227-228`，`file` 为 `None` 的包级 finding 对所有文件可见）。

#### LLM 审核层 `skills/security_scanner.py` 的决策契约

`scan_skill_content(content, *, executable, location, app_config, static_findings, attach_tracing=True) -> ScanResult`（`:96-176`）是安装与 `skill_manage` 共用的第二层。注意它自己的 `ScanResult` 是 `@dataclass(slots=True)` 的 `(decision, reason)`（`:23-26`）——与 `skillscan/models.py:29-32` 的同名 `TypedDict` **是两个不同类型**，import 时别拿错。

- 提示词要求只输出一行 JSON `{"decision":"allow|warn|block","reason":"..."}`（`:116-124`）；`_extract_json_object`（`:38-81`）先剥一层代码围栏，失败再做**字符串感知的花括号配平**抽取。
- **失败姿态（写死，非配置）**：模型**答了但解析不出** → `block`（`:169-170`）；`executable=True` 且模型调用失败 → **无视配置** `block`（`:171-172`）。
- **可配置姿态**：模型调用失败且非 executable → `skill_evolution.security_fail_closed`（默认 `True`；配置不可得也按 `True`，`:29-35`）为真则 `block`，否则记 warning 并 `warn`（`:173-176`）。
- **`attach_tracing` 是调用方责任**：in-graph 唯一收口是 `tools/skill_manage_tool.py::_scan_or_raise`（传 `False`，图根已挂回调）；standalone 调用方（Gateway 路由、`installer.py`）保持默认 `True` 并自行 `inject_langfuse_metadata`（`:107-115,130-150`），与 `run_oneshot_llm` 同一模式。`moderation_model_name` 缺省时用 `create_chat_model()` 的默认模型（`:129-131`）。

### 2.3 原子落地与失败清理

- `_move_staged_skill_into_reserved_target(staging_target, target)`（`:210-224`）是"预留 + 提交 + 回滚"三段式：
  1. `target.mkdir(mode=0o700)` 抢占目标；`FileExistsError` → `SkillAlreadyExistsError`（`:214,220-221`）；
  2. 逐个 `shutil.move` 子项，然后 `make_skill_tree_sandbox_readable(target)`，最后置 `installed=True`（`:216-219`）；
  3. `finally` 中 **`reserved and not installed and target.exists()` → `shutil.rmtree(target)`**（`:222-224`）——半成品目录不会残留。
- 调用侧 `_commit_skill_install`（`local_skill_storage.py:205-214`）在 `_skill_projection_mutation()` 临界区内用 `TemporaryDirectory(prefix=".installing-{name}-", dir=custom_dir)` 做 staging → `copytree` → move；随后 `make_skill_written_path_sandbox_readable`。
- **抽取临时目录**由 `tempfile.mkdtemp()` 在 `_prepare_skill_archive` 之前创建（`local_skill_storage.py:128`），`finally` 里 `asyncio.wait_for(asyncio.to_thread(_cleanup_install_tmp, tmp), timeout=_INSTALL_TMP_CLEANUP_TIMEOUT_SECONDS)`（`:136-143`）；清理是 best-effort：`shutil.rmtree` 的 `OSError` 只 warning（`:151-157`），超时也只 warning（`:142-143`）。超时常量 `_INSTALL_TMP_CLEANUP_TIMEOUT_SECONDS = 5.0`（`local_skill_storage.py:26`）；user-scoped 版本内联同一个 `5.0`（`user_scoped_skill_storage.py:349`）。
- **提交前的任何失败都不会碰 `custom/`**：预检/抽取/扫描/校验/重名检查全部发生在 `_commit_skill_install` 之前，目标目录只在最后一步被 `mkdir`。
- **同步桥 `_run_async_install(coro)`（`:320-329`）**：默认 `asyncio.run(coro)`；若已有 running loop，则起一个 `ThreadPoolExecutor(max_workers=1)` 在其中 `asyncio.run`——`SkillStorage.install_skill_from_archive()` 这个同步包装（`skill_storage.py:200-204`）因此能从事件循环内调用而不炸。

### 2.4 错误类型与 HTTP 映射

| 异常 | 定义 | Gateway 映射 |
|------|------|------|
| `SkillAlreadyExistsError(ValueError)` | `installer.py:35-36` | 409（`app/gateway/routers/skills.py:249-250`） |
| `SkillSecurityScanError(ValueError)` | `installer.py:39-48`，带 `findings: list[StaticFinding]` + `skill_name` | 有 findings → 400 + `{message, skill_name, findings}`；否则 400（`skills.py:251-261`） |
| `FileNotFoundError` | storage 层（`local:173,183`） | 404（`skills.py:247-248`） |
| `ValueError` | 非 `.skill` 后缀 / 坏 ZIP / frontmatter 无效 / 名字非法 | 400（`skills.py:262-263`） |
| 其它 | — | 500（`skills.py:266-268`） |

`scan_archive_preflight_or_raise` 的 CRITICAL findings 经 `format_static_archive_findings()`（`:269-270`）排成 `rule_id (SEVERITY) at file: message` 串。

### 2.5 上传路由的临时文件清理（`app/gateway/routers/skills.py`）

`_install_skill_archive`（`:242-268`）是两条安装路由的共用收尾（成功时顺带 `refresh_user_skills_system_prompt_cache_async`，`:245`）。`POST /api/skills/install`（`:287-301`）先 `require_admin_user`，再把 thread 虚拟路径解析成宿主路径，404/400 由路径解析错误给出。

`POST /api/skills/install/upload`（`:304-353`）：
- admin-only（`:328`）；multipart 必需（否则 422，`:231-232`）；文件名必须以 `.skill` 结尾（400，`:339-340`）。
- 有界解析器 `_BoundedSkillArchiveMultiPartParser` + `_bounded_skill_archive_request_stream`：请求级上限 `_MAX_SKILL_ARCHIVE_UPLOAD_BYTES(100 MiB) + _MAX_SKILL_ARCHIVE_MULTIPART_OVERHEAD_BYTES(1 MiB)`，`Content-Length` 预检 + 流式累计双查（`:49-50,208-225`）；超限抛 `_SkillArchiveUploadTooLargeError` → 413（`:345-346`）。
- 落盘到 `NamedTemporaryFile(prefix="deerflow-skill-", suffix=".skill", delete=False)`（`:189`），**`finally` 中无论成败都 `unlink(missing_ok=True)` 并 `form.close()`**（`:349-353`）。

---

## 3. SkillScan 补深：规则表 / 上限 / 异常类型

主文档已给规则**计数**（39 条：CRITICAL 19 / HIGH 14 / MEDIUM 5 / LOW 1，`skillscan/orchestrator.py:46-93`）与检测语义。这里补全**规则表本体**、全部上限常量、异常层级，以及"两条入口 / 四层调用面"。

### 3.1 规则表（`RULES: dict[rule_id, RuleSpec]`，39 条）

`severity` 决定阻断与否：只有 `CRITICAL` 阻断（`_BLOCK_SEVERITY`，`:41`）。`package-nested-archive` 会在嵌套 ZIP 含可执行 magic 时**被就地升为 CRITICAL**（`_nested_archive_finding`，`:500-510`）。

| rule_id | severity | 触发 |
|---------|----------|------|
| `package-path-traversal` | CRITICAL | 归档成员路径含 `..` |
| `package-absolute-path` | CRITICAL | 成员路径绝对（POSIX 或 Windows 盘符） |
| `package-ads-stream-name` | CRITICAL | 成员路径含 `:`（NTFS ADS） |
| `package-symlink` | HIGH | 归档含符号链接条目 |
| `package-nested-skill-md` | CRITICAL | 包内出现嵌套 `SKILL.md`（eval fixture 豁免） |
| `package-oversized-total` | CRITICAL | 解压总量 > 512 MiB |
| `package-too-many-members` | CRITICAL | 成员数 > 4096（逐成员读取前 early-return） |
| `package-oversized-file` | CRITICAL | 单文件 > 64 MiB |
| `package-executable-binary` | CRITICAL | ELF/PE/Mach-O magic |
| `package-nested-archive` | HIGH（可升 CRITICAL） | 嵌套归档（后缀或 magic） |
| `package-hidden-sensitive-file` | HIGH | `.aws/credentials`、`.git/config`、`.env`、`.npmrc`、`.pypirc`、`.netrc` 等 |
| `package-undecodable-script` | HIGH | 代码文件非 NUL-free UTF-8（有损解码继续分析） |
| `package-git-directory` | MEDIUM | 路径含 `.git` 段 |
| `secret-private-key` | CRITICAL | `-----BEGIN … PRIVATE KEY-----` |
| `secret-cloud-token` | CRITICAL | AWS `AKIA/ASIA`、`gh[pousr]_`、`xox[baprs]-`、`sk-`（占位值豁免） |
| `secret-env-assignment` | HIGH | `token/password/api_key/secret/credential … = <非占位值>` |
| `declaration-prompt-override` | HIGH | SKILL.md 出现 "ignore/disregard … previous instructions"、"override … system/developer instructions" |
| `declaration-sensitive-capability` | HIGH | SKILL.md 声称 execute commands / credential access / network egress 等 |
| `declaration-sensitive-path` | HIGH | SKILL.md 引用 `~/.ssh`、`/etc/passwd`、`docker.sock`、`169.254.169.254` |
| `declaration-external-endpoint` | MEDIUM | SKILL.md 出现非本地 `http://` 端点 |
| `python-dynamic-exec` | CRITICAL | `eval` / `exec` / `compile(mode="exec")` |
| `python-shell-exec` | CRITICAL | `os.system`/`os.popen`，或 `subprocess.*` 且 `shell=` 无法证明为字面 `False`（fail-closed，`_call_shell_may_be_true`） |
| `python-sensitive-exfil` | CRITICAL | 同文件内敏感路径读取 × 网络 sink |
| `python-env-dump-exfil` | CRITICAL | 同文件内 `os.environ` 读取 × 网络 sink |
| `python-reverse-shell` | CRITICAL | `socket` + `dup2` + `subprocess` 三件套 |
| `python-dynamic-import` | HIGH | 非字面量动态 import |
| `python-subprocess` | HIGH | `subprocess.*` 但未命中 shell 规则 |
| `python-sensitive-path-read` | HIGH | 读取敏感路径 |
| `python-unsafe-deserialization` | MEDIUM | 不安全反序列化 |
| `shell-reverse-shell` | CRITICAL | `/dev/tcp/`、`nc -e` 等直接反向 shell |
| `shell-reverse-shell-heuristic` | HIGH | `bash -i`、`mkfifo` 等启发式 |
| `shell-sensitive-exfil` | CRITICAL | 敏感路径读取 + 外发命令 |
| `shell-curl-pipe-shell` | HIGH | `curl … \| sh` |
| `shell-destructive-command` | HIGH | `rm -rf /`、系统根目录、通配根（`_DESTRUCTIVE_RM_RE`，`:121-128`） |
| `shell-env-dump` | MEDIUM | 批量 dump 环境变量 |
| `network-cloud-metadata` | CRITICAL | 云元数据服务地址 |
| `resource-fork-bomb` | CRITICAL | `:(){ :\|:& };:` |
| `network-cleartext-http` | MEDIUM | 非本地明文 HTTP 端点 |
| `network-local-http` | LOW | 本地/私网 HTTP 端点（`localhost`/`127.0.0.1`/`0.0.0.0`/`::1`/`10.*`/`192.168.*`/`172.16-31.*`，`:462-468`） |

`RuleSpec` 是 `frozen dataclass`，字段 `rule_id/severity/message/remediation`（`skillscan/models.py:35-42`）；`RULES` 由 `_SPECS` 列表推导（`:93`）。**没有** category/analyzer 字段——类别与所属分析器编码在 `rule_id` 前缀（`models.py:1-8`）。

### 3.2 上限常量

| 常量 | 值 | 位置 |
|------|-----|------|
| `MAX_TOTAL_ARCHIVE_BYTES` | 512 MiB | `orchestrator.py:38` |
| `MAX_FILE_BYTES` | 64 MiB | `orchestrator.py:39` |
| `_NESTED_ZIP_PEEK_MEMBER_LIMIT` | 256 | `orchestrator.py:42` |
| `_MAX_ARCHIVE_MEMBERS` | 4096 | `orchestrator.py:43` |
| `_TEXT_PROBE_BYTES` | 4096 | `orchestrator.py:44` |
| `_PYTHON_CLIENT_ANALYSIS_BUDGET` | 100 000 | `orchestrator.py:798` |
| `_BLOCK_SEVERITY` | `"CRITICAL"` | `orchestrator.py:41` |
| 安装器抽取默认上限 | 512 MiB / 4096 成员 | `installer.py:118-119` |
| review 侧镜像 `PackageLimits` | 4096 / 64 MiB / 512 MiB | `skills/review/models.py:33-47` |

### 3.3 异常类型与调用面

```
skillscan/models.py
├── StaticScannerError(RuntimeError)        # :45-46  包边界无法评估（坏 ZIP、非目录）
└── StaticScanBlockedError(ValueError)      # :49-59  命中 CRITICAL；带 findings + skill_name

installer.py（面向 Gateway 的翻译层）
├── SkillSecurityScanError(ValueError)      # :39-48  统一包装上面两者 + LLM 扫描拒绝
└── SkillAlreadyExistsError(ValueError)     # :35-36
```

- `StaticScannerError` 的抛出点：`scan_archive_preflight` 的 `BadZipFile/OSError`（`:218-219`）、`scan_skill_dir` 的非目录（`:226-227`）。
- `StaticScanBlockedError` 只在 `enforce_static_scan` 命中 CRITICAL 时抛（`:166-171`），消息由 `format_static_findings` 拼装。
- `deerflow/skills/security_static_scanner.py`（25 行）是**兼容 re-export**：把 `SecurityFinding` 别名成 `StaticFinding`，并再导出 6 个函数与 2 个异常（`:3-25`）。新代码直接 import `deerflow.skills.skillscan`。
- **调用面**（权限/阻断层级从低到高）：`enforce_static_scan`（写入门：`skill_manage` / storage 安装的抽取后扫描）→ `scan_archive_preflight`（安装前只读元数据）→ `scan_skill_dir`（任意目录，被 review core 适配器复用）。三者都是**纯同步**函数，async 调用方自行 offload（模块 docstring `:3-5`）。
- 结果形状 `ScanResult = {findings, blocked, scanner_errors}`（`models.py:29-32`）；`blocked` 只由是否存在 `_BLOCK_SEVERITY` finding 决定（`_scan_result`，`:544-546`）。`scanner_errors` 是逐文件/逐成员的字符串（读取失败、analyzer 异常），**不阻断**，由 `enforce_static_scan` 记 warning（`:172-173`）。
- `_dedupe` 的键是 `(rule_id, file, line)`、保留首次出现（`:549-558`）；`secret-*` 的 `evidence` 一律替换为字面 `"[redacted]"`（`_redact_secret_evidence`，`:537-541`；在 `_finding` 中统一应用，`:474-475`）。

> **See also:** [Skills 与 Tool 系统](skill-md-and-tool-assembly.md)（加载/投影/导出/写入门）· [Skill Review Core](skill-review-core.md)（SkillScan 的只读适配层）· `skills/AGENTS.md`（SkillScan 与 installer 的权威纪律）
