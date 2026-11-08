---
title: "Skill 包摄入：解析、安装与 SkillScan 规则表"
description: "`skills/parser.py` 的 frontmatter 解析边界、`skills/installer.py` 的 .skill 安装链路与失败清理、SkillScan 全量规则表/上限/异常类型。"
topics: [skills, installer, parser, skillscan, contract]
---

# Skill 包摄入：解析、安装与 SkillScan 规则表

主文档 [`skill-md-and-tool-assembly.md`](skill-md-and-tool-assembly.md) 已覆盖加载/投影/导出/写入门；本文补它没展开的三块：**frontmatter 解析边界（`parser.py`）**、**`.skill` 安装链路与失败清理（`installer.py` + storage）**、**SkillScan 规则表/上限/异常类型**。

---

## 1. `skills/parser.py` — frontmatter 解析边界

三个公开解析函数，全部在 `parse_skill_file()`（`parser.py:211-298`）里被消费。设计基调是**"字段级畸形降级、结构级畸形拒收"**。

### 1.1 `parse_allowed_tools(raw, skill_file) -> tuple[str, ...] | None`（`parser.py:108-136`）

| 输入 | 行为 |
|------|------|
| `None`（字段省略） | 返回 `None` |
| `str`（可移植标量形式） | 走状态机分词，**开启别名归一化**（`parser.py:120-122`） |
| `list` | 逐条 `strip()`，**不做别名归一化**（`normalize_tools=False`，`parser.py:125-126,135`），MCP/运行时工具名原样保留大小写 |
| 其它类型 | `ValueError`（`parser.py:123-124`） |
| 列表内含非字符串 | `ValueError`（`parser.py:130-131`） |
| 条目 strip 后为空 | `ValueError`（`parser.py:133-134`） |
| 显式空字符串 `""` | 分词结果为空 → 返回**空元组** `()`（非 `None`） |

**状态机 `_split_portable_allowed_tools`（`parser.py:34-79`）的 fail-closed 边界**：

- 只有 `depth == 0` 且在引号外的空白才切分（`parser.py:60-64`）；引号内、`(...)` 内的空格保持在同一 token。
- `\` 转义：反斜杠**本身与下一个字符都原样保留进 token**（`parser.py:47-50`），不做反转义——所以 `Bash\(x\)` 会带着反斜杠进入字面工具名。⚠️ 2.2 起 「DeerFlow 只做精确名匹配」这件事**已经没有执行点了**：`skills/tool_policy.py` 在 2.2 **已删除**，`allowed-tools` 降级为兼容元数据，解析结果只用于展示（`describe_skill` 输出与 skill index），详见主文档的 allowed-tools 专节。
- `)` 在 `depth == 0` 时 → `ValueError "unmatched closing parenthesis"`（`parser.py:68-69`）。
- 结束时引号未闭合 → `ValueError "unclosed quote"`（`parser.py:73-74`）；`depth != 0` → `ValueError "unclosed parenthesized pattern"`（`parser.py:75-76`）。
- 最后一个 token 会被 flush（`parser.py:77-78`）。

**别名映射**（`_PORTABLE_TOOL_ALIASES`，`parser.py:15-24`，8 条）：`Bash→bash`、`Edit→str_replace`、`Glob→glob`、`Grep→grep`、`Read→read_file`、`WebFetch→web_fetch`、`WebSearch→web_search`、`Write→write_file`。`_normalize_unscoped_allowed_tool` 遇到**含 `(` 或 `)` 的条目直接原样返回**（`parser.py:27-32`）；未知名（含已知别名的小写拼法）保持原样。

**与安装门的关系**：`validation.py:82-85` 也调 `parse_allowed_tools`，把 `ValueError` 的宿主路径替换成字面 `SKILL.md` 后返回 400（`str(e).replace(str(skill_md), SKILL_MD_FILE)`）。而 `parse_skill_file`（`parser.py:263-267`）捕获同一异常后**记 error 日志并返回 `None`**——即"解析失败 ⇒ skill 直接不加载"，不是降级。

### 1.2 `parse_required_secrets(raw, skill_file) -> tuple[SecretRequirement, ...]`（`:137-171`）

- `None` → `()`；非 `list` → `ValueError`（`parser.py:153-155`）。
- 字符串条目 → `name=item.strip(), optional=False`（`parser.py:158-159`）。
- mapping 条目 → `name = str(item.get("name") or "").strip()`；`optional` **只在字面量是 `bool` 时采用**，其它类型（`"false"`、`1`、`None`…）记 warning 后按 `False` 处理（`parser.py:160-171`）。
- 其它类型 → warning + 跳过（`parser.py:172-174`）。
- `name` 必须匹配 `^[A-Za-z_][A-Za-z0-9_]*$`（`_ENV_VAR_NAME_RE`，`parser.py:14`）；不匹配 → warning + 跳过（`parser.py:176-178`）。
- **重名合并到首次出现的位置，但只要其中任一声明是 required，最终就是 required 🆕（2.2，#5738）**：`positions` 表记住首次下标，后到的 `optional: false` 会把已插入条目的 `optional` 改回 `False`（`parser.py:179-185`）。旧行为是"保留首次出现"——先写的 `optional: true` 会把后写的 required 声明吃掉，skill 静默地在缺 secret 的情况下继续跑。

⚠️ **2.2 收窄后的不对称（契约级陷阱，别再照 2.1 写）**：`validation.py:87-93` 现在检查两件事——`required-secrets` 必须是 list；**mapping 条目的 `optional` 必须是布尔**，否则 400（无 name 时消息为 `"required-secrets entry without a name has an optional field that must be a boolean"`，有 name 时为 `"required-secrets entry {name!r} optional must be a boolean"`）。review core 同步新增 `structure.invalid-required-secrets-optional`（severity=error，`review/analyzer.py:262-272`）。**仍然不校验的是条目名**：`required-secrets: ["not a var"]` 照样能过安装/写入门——`parse_skill_file` 的 `try/except ValueError` 只在"整个字段不是 list"时触发（`parser.py:269-273`），条目级畸形不抛，交给 `parse_required_secrets` 逐条 `warning` + 丢弃。净效果：**畸形条目名会让该 secret 永久不生效，但 skill 照常加载**；排查时看 `logger.warning("Ignoring required-secrets entry with invalid env var name ...")`（`parser.py:177`）。

**`optional` 的读取方向处处 fail-closed 🆕**：`parse_required_secrets` 用 `isinstance(raw_optional, bool)` 判定；`export.py:306-330` 的 manifest 生成改用 `secret.get("optional") is True`（注释原话「Only a literal boolean `true` is optional: the same fail-closed read as parse_required_secrets」），并且重名时**首个占位、required 胜出**，与解析器镜像。

### 1.3 `parse_secrets_autonomous(raw, skill_file) -> bool`（`parser.py:195-209`）

`None` → `True`（默认允许自主绑定）；`bool` → 原值；**其它类型 → warning + `False`**（`parser.py:207-209`）。注释写明这是 fail-closed 到"更不易注入"的方向（`parser.py:200-202`），与 `validation.py:96-98`（畸形即 400 拒收）在**写入门更严、加载器更宽**上互补。

### 1.4 `parse_skill_file()` 的拒收面（`parser.py:211-298`）

返回 `None`（skill 不加载，不抛）的情形：文件不存在或 basename ≠ `SKILL.md`（`parser.py:223-224`）；无 `---` frontmatter（`parser.py:231-233`）；YAML 语法错（`parser.py:237-243`，日志带行号 + `mapping values are not allowed here` 的引号提示，`_format_yaml_error` `parser.py:82-106`）；frontmatter 非 dict（`parser.py:244-246`）；`name`/`description` 缺失、非字符串、或 strip 后为空（`parser.py:251-262`）；`allowed-tools`/`required-secrets` 的 `ValueError`（`parser.py:263-274`）。整体还有一层 `except Exception` → `logger.exception` + `None`（`parser.py:296-298`）。`relative_path` 省略时默认取 skill 目录名（`parser.py:288`）；`enabled=True` 只是占位，真实启用态来自 extensions config / per-user state（`parser.py:291`）。

**诊断旁路 🆕（2.2）**：`parse_skill_file(..., diagnostics=[] | None)` 新增关键字参数——传了 sink 时，**只有** `yaml.YAMLError` 会被投影成 `SkillLoadDiagnostic` 追加进去（`yaml_load_diagnostic(..., line_offset=content.count("\n", 0, front_matter_match.start(1)))`，`parser.py:237-242`）。缺 frontmatter / 非 mapping / 非 UTF-8 / 读盘失败**不产生**诊断。该 sink 只服务管理面（`GET /api/skills/diagnostics/custom`），调用方必须先自行授权路径；机制详见主文档的诊断专节。

---

## 2. `skills/installer.py` — `.skill` 安装链路

`installer.py`（331 行）是**纯业务逻辑、无 FastAPI 依赖**的共享安装实现（模块 docstring `installer.py:1-5`），Gateway 与 embedded client 都委托它。真正的编排在 storage 侧的两个 `ainstall_skill_from_archive`（`storage/local_skill_storage.py:129-159`；user-scoped 变体同形），installer 提供所有"危险步骤"。

```
storage.ainstall_skill_from_archive(archive_path)                          # local_skill_storage.py:129-159
  └─ asyncio.to_thread(_prepare_skill_archive)                            # worker 线程  local:169-209
       ① 后缀必须是 .skill / 必须是文件，否则 ValueError                      local:182-185
       ② zipfile.ZipFile 打开（BadZipFile/IsADirectoryError → ValueError）     local:190-196
       ③ scan_archive_preflight_or_raise(path, app_config=...)                local:199
       ④ safe_extract_skill_archive(zf, tmp_path)                             local:200
       ⑤ resolve_skill_dir_from_archive(tmp_path) → skill_dir                 local:202
       ⑥ _validate_skill_frontmatter(skill_dir) → (ok, msg, skill_name)       local:204-206
       ⑦ skill_name 安全字符检查（/ \ ..）+ target.exists() → 409            local:207-212
  ├─ _scan_skill_archive_contents_or_raise(skill_dir, skill_name, ...)        local:142  # async LLM 扫描，留在 event loop
  └─ asyncio.to_thread(_commit_skill_install)                               # worker 线程  local:214-224
       _skill_projection_mutation(names=(skill_name,)) 内：临时 staging 目录 copytree
         → _move_staged_skill_into_reserved_target → make_skill_written_path_sandbox_readable
  finally: 清理 mkdtemp 抽取目录（best-effort + 超时告警）                      local:146-153
```

### 2.1 归档预检与安全抽取

- **`scan_archive_preflight_or_raise(archive_path, *, app_config=None)`（`installer.py:256-266`）**：先查 `skill_scan_enabled(app_config)`，**关闭时直接 return（不扫描）**（`:257-258`）；否则调 `scan_archive_preflight()`，只在 `result["blocked"]` 为真（存在 CRITICAL）时抛 `SkillSecurityScanError(..., findings=仅 CRITICAL, skill_name=None)`（`:260-266`）。它是**解压前的第一道门**：只看 ZIP 成员元数据 + 限量 peek，不落盘。
- **`safe_extract_skill_archive()`（`installer.py:115-177`）** 是解压路径的独立防线，与 kill switch 无关、每次安装都生效：
  - 成员数先查：`len(infos) > max_entries`（默认 **4096**）在**任何逐成员工作之前** early-abort（`installer.py:138-146`）——注释特意点明"这是每次安装都走的路径，不能依赖可选的 SkillScan"。
  - 逐成员：`is_unsafe_zip_member` → `ValueError`（`installer.py:149-150`）；**符号链接条目只 warning 并 `continue`，不物化**（`installer.py:152-154`）；归一化后 `member_path.resolve().is_relative_to(dest_root)` 再查一次逃逸（`installer.py:156-159`）。
  - 写盘时**第一块就查可执行 magic**（`is_executable_binary_prefix`，ELF/PE/Mach-O）并抛 `ValueError`（`installer.py:169-170`）——2.2 起 sniff 窗口是 `EXEC_SNIFF_BYTES = 63 + max(magic len)`，且**容忍前导填充**（见 2.4）；累计字节数超 `max_total_size`（默认 **512 MiB**）抛错（`installer.py:172-175`）。
  - POSIX 上按 `external_attr >> 16 & 0o111` 还原 `0o755`/`0o644`（`installer.py:176-177`）。
- **`is_unsafe_zip_member`（`installer.py:51-82`）**：绝对路径（POSIX 或 `PureWindowsPath` 都查）、`..` 段、以及**任何位置的 `:`** 一律拒。冒号那条注释解释得很清楚：NTFS 上 `scripts/run.sh:hidden.txt` 会变成前一个路径组件的 Alternate Data Stream，对 `rglob`/`os.walk` 不可见，于是能绕过基于目录遍历的安全扫描。
- **`is_symlink_member`（`installer.py:85-88`）**：`external_attr >> 16` 的 `S_ISLNK`。
- **`resolve_skill_dir_from_archive`（`installer.py:96-112`）**：过滤 dotfile 与 `__MACOSX`（`should_ignore_archive_entry`，`installer.py:91-93`，判据是 `path.name.startswith(".") or path.name == "__MACOSX"`）；过滤后为空 → `ValueError("Skill archive is empty")`；**恰好一个目录** → 解包该目录作为 skill 根，否则以解压根为根。注意过滤只影响"根判定"，**抽取阶段仍会把 dotfile 写盘**。

### 2.2 内容扫描（静态 + LLM 双层）

- `_scan_static_skill_archive_or_raise`（`installer.py:273-279`）：`asyncio.to_thread(enforce_static_scan, skill_dir, skill_name=..., app_config=app_config)`；`StaticScanBlockedError` / `StaticScannerError` 都翻译成 `SkillSecurityScanError`（携带 `findings`/`skill_name`）。
- `_scan_skill_archive_contents_or_raise`（`installer.py:287-319`）：
  1. 先跑静态扫描拿 `static_findings`；
  2. 单独扫根 `SKILL.md`（`executable=False`）；
  3. 遍历 `_collect_scannable_files(skill_dir)`（`sorted(skill_dir.rglob("*"))`，阻塞调用在 worker 线程里跑，`installer.py:282-284,291`）中的所有文件：**嵌套 `SKILL.md` 无条件硬失败**（`installer.py:297-298`，与 SkillScan 的 CRITICAL 规则对齐，但这里是"安装了也加载不出来"的直接拒收）；
  4. 代码文件（`_is_code_file`，`installer.py:198-207`：`package_files.is_code_path` 或"无后缀 + `#!`"，shebang 嗅探单独 offload）走 `executable=True`；`scripts/**`（`_is_script_support_file`）与 `references|templates` 下的文本类支持文件（`_PROMPT_INPUT_SUFFIXES`，`installer.py:32,180-187`）走 `executable=False`。
  5. **`app_config` 全程透传 🆕（2.2）**：静态扫描、SKILL.md、可执行文件、支持文件四条分支都带 `app_config=app_config` 进 `scan_skill_content`。2.1 只传了其中一部分，于是安装路径上的 `skill_evolution.security_fail_closed` / kill switch 在某些分支被静默忽略。
- `_scan_skill_file_or_raise(skill_dir, path, skill_name, *, executable, static_findings=None, app_config=None)`（`installer.py:231-253`）：非 UTF-8 → `SkillSecurityScanError`；`scan_skill_content(..., static_findings=)` 的决策 `block` → 拒；`executable=True` 且决策 ≠ `allow` → 拒；决策不在 `{allow, warn}` → 拒（`installer.py:252-253`）。**静态 findings 按文件过滤后透传给 LLM 扫描器**（`_findings_for_file`，`installer.py:227-228`，`file` 为 `None` 的包级 finding 对所有文件可见）。

#### LLM 审核层 `skills/security_scanner.py` 的决策契约

`scan_skill_content(content, *, executable, location, app_config, static_findings, attach_tracing=True, redact_diagnostics=False) -> ScanResult`（`security_scanner.py:97-181`）是安装与 `skill_manage` 共用的第二层。注意它自己的 `ScanResult` 是 `(decision, reason, available=True)` 的 dataclass（`security_scanner.py:23-27`）——与 `skillscan/models.py:29-32` 的同名 `TypedDict` **是两个不同类型**，import 时别拿错。

**`available` 与 `redact_diagnostics` 都是 2.2 新增 🆕**：

- `available: bool = True`——所有"扫描器不可用"的分支（模型调用异常、输出不可解析、可执行内容无扫描器）现在同时置 `available=False`，把"内容是坏的"（`block` + `available=True`）与"扫描器坏了"（`available=False`）区分开。消费方是宿主 mutation 服务的 `mutations/scanner.py:102-105`：`available=False` → `ScanVerdict("unavailable", "SCANNER_UNAVAILABLE")`，后者永远不能 commit。手动路径（`skill_manage` / installer）不看这个字段，行为不变。
- `redact_diagnostics=False`——为真时日志**不再打印原始模型输出前 200 字符**（`logger.warning("Security scan produced unparseable output")`）且异常日志不带 `exc_info`（`exc_info=not redact_diagnostics`）。宿主服务传 `True`：那里的内容可能包含用户 skill 正文或 provider 报文，不能进日志。

- 提示词要求只输出一行 JSON `{"decision":"allow|warn|block","reason":"..."}`（`:116-124`）；`_extract_json_object`（`:38-81`）先剥一层代码围栏，失败再做**字符串感知的花括号配平**抽取。
- **失败姿态（写死，非配置）**：模型**答了但解析不出** → `block`（`security_scanner.py:164-170`）；`executable=True` 且模型调用失败 → **无视配置** `block`（`:171-172`）。两者都带 `available=False`。
- **可配置姿态**：模型调用失败且非 executable → `skill_evolution.security_fail_closed`（默认 `True`；配置不可得也按 `True`，`security_scanner.py:30-36`）为真则 `block`，否则记 warning 并 `warn`（`:173-181`）。两条都带 `available=False`。
- **`attach_tracing` 是调用方责任**：in-graph 唯一收口是 `tools/skill_manage_tool.py::_scan_or_raise`（传 `False`，图根已挂回调）；standalone 调用方（Gateway 路由、`installer.py`）保持默认 `True` 并自行 `inject_langfuse_metadata`（`security_scanner.py:107-117`），与 `run_oneshot_llm` 同一模式。`moderation_model_name` 缺省时用 `create_chat_model()` 的默认模型（`:130-134`）。

### 2.3 原子落地与失败清理

- `_move_staged_skill_into_reserved_target(staging_target, target)`（`installer.py:210-226`）是"预留 + 提交 + 回滚"三段式：
  1. `target.mkdir(mode=0o700)` 抢占目标；`FileExistsError` → `SkillAlreadyExistsError`（`installer.py:214,220-221`）；
  2. 逐个 `shutil.move` 子项，然后 `make_skill_tree_sandbox_readable(target)`，最后置 `installed=True`（`installer.py:216-219`）；
  3. `finally` 中 **`reserved and not installed and target.exists()` → `shutil.rmtree(target)`**（`installer.py:222-224`）——半成品目录不会残留。
- 调用侧 `_commit_skill_install`（`local_skill_storage.py:214-224`）在 `self._skill_projection_mutation(names=(skill_name,))` 临界区内用 `TemporaryDirectory(prefix=f".installing-{skill_name}-", dir=custom_dir)` 做 staging → `copytree` → move；随后 `make_skill_written_path_sandbox_readable(custom_dir, target)`。🆕 2.2 起这把锁是**按 skill 名**的（`_skill_projection_mutation` 把 `names` 透传成 `skill_projection_mutation(..., mutation_names=names)`），安装一个新 skill 不再阻塞同用户对其它 skill 的编辑。
- **抽取临时目录**由 `tempfile.mkdtemp()` 在 `_prepare_skill_archive` 之前创建（`local_skill_storage.py:138`），`finally` 里 `asyncio.wait_for(asyncio.to_thread(_cleanup_install_tmp, tmp), timeout=_INSTALL_TMP_CLEANUP_TIMEOUT_SECONDS)`（`local_skill_storage.py:146-153`）；清理是 best-effort：`shutil.rmtree` 的 `OSError` 只 warning（`:162-168`），超时也只 warning（`:152-153`）。超时常量 `_INSTALL_TMP_CLEANUP_TIMEOUT_SECONDS = 5.0`（`local_skill_storage.py:26`）；user-scoped 版本内联同一个 `5.0`。
- **提交前的任何失败都不会碰 `custom/`**：预检/抽取/扫描/校验/重名检查全部发生在 `_commit_skill_install` 之前，目标目录只在最后一步被 `mkdir`。
- **同步桥 `_run_async_install(coro)`（`installer.py:322-331`）**：默认 `asyncio.run(coro)`；若已有 running loop，则起一个 `ThreadPoolExecutor(max_workers=1)` 在其中 `asyncio.run`——`SkillStorage.install_skill_from_archive()` 这个同步包装因此能从事件循环内调用而不炸。

### 2.4 错误类型与 HTTP 映射

| 异常 | 定义 | Gateway 映射 |
|------|------|------|
| `SkillAlreadyExistsError(ValueError)` | `installer.py:35-36` | 409 |
| `SkillSecurityScanError(ValueError)` | `installer.py:39-48`，带 `findings: list[StaticFinding]` + `skill_name` | 有 findings → 400 + `{message, skill_name, findings}`；否则 400 |
| `FileNotFoundError` | storage 层（`local_skill_storage.py:182-184,191-192`） | 404 |
| `ValueError` | 非 `.skill` 后缀 / 坏 ZIP / frontmatter 无效 / 名字非法 | 400 |
| 其它 | — | 500 |

> 行号随 `routers/skills.py` 的 2.2 改动整体位移，本表只保留异常类型与状态码（这部分语义未变）。精确行号见主文档的路由清单。

`scan_archive_preflight_or_raise` 的 CRITICAL findings 经 `format_static_archive_findings()`（`installer.py:269-270`）排成 `rule_id (SEVERITY) at file: message` 串。

### 2.5 上传路由的临时文件清理（`app/gateway/routers/skills.py`）

`_install_skill_archive` 是两条安装路由的共用收尾（成功时顺带 `refresh_user_skills_system_prompt_cache_async`，并在 2.2 追加 `publish_skills_cache_reset` 让其它 Gateway 进程同步失效）。`POST /api/skills/install`（`app/gateway/routers/skills.py:526`）先 `require_admin_user`，再把 thread 虚拟路径解析成宿主路径，404/400 由路径解析错误给出。

`POST /api/skills/install/upload`（`app/gateway/routers/skills.py:543`）：
- admin-only；multipart 必需（否则 422）；文件名必须以 `.skill` 结尾（400）。
- 有界解析器 `_BoundedSkillArchiveMultiPartParser` + `_bounded_skill_archive_request_stream`：请求级上限 `_MAX_SKILL_ARCHIVE_UPLOAD_BYTES`(100 MiB) + `_MAX_SKILL_ARCHIVE_MULTIPART_OVERHEAD_BYTES`(1 MiB)，`Content-Length` 预检 + 流式累计双查；超限抛 `_SkillArchiveUploadTooLargeError` → 413。
- 落盘到 `NamedTemporaryFile(prefix="deerflow-skill-", suffix=".skill", delete=False)`，**`finally` 中无论成败都 `unlink(missing_ok=True)` 并 `form.close()`**。

---

## 3. SkillScan 补深：规则表 / 上限 / 异常类型

主文档已给规则**计数**（39 条：CRITICAL 19 / HIGH 14 / MEDIUM 5 / LOW 1，`skillscan/orchestrator.py:50-96`）与检测语义。这里补全**规则表本体**、全部上限常量、异常层级，以及"两条入口 / 四层调用面"。

### 3.1 规则表（`RULES: dict[rule_id, RuleSpec]`，39 条）

`severity` 决定阻断与否：只有 `CRITICAL` 阻断（`_BLOCK_SEVERITY`，`skillscan/orchestrator.py:45`）。`package-nested-archive` 会在嵌套 ZIP 含可执行 magic 时**被就地升为 CRITICAL**（`_nested_archive_finding`，`orchestrator.py:1284-1294`；peek 上限 `_NESTED_ZIP_PEEK_MEMBER_LIMIT=256` 成员）；2.2 起这个 peek 用 `EXEC_SNIFF_BYTES` 读头，因此**带前导填充/地址头伪装的可执行成员**同样能被认出来（见 2.4 的 sniff 说明）。

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
| `shell-destructive-command` | HIGH | `rm -rf /`、系统根目录、通配根（`_DESTRUCTIVE_RM_RE`，`orchestrator.py:163-171`） |
| `shell-env-dump` | MEDIUM | 批量 dump 环境变量 |
| `network-cloud-metadata` | CRITICAL | 云元数据服务地址 |
| `resource-fork-bomb` | CRITICAL | `:(){ :\|:& };:` |
| `network-cleartext-http` | MEDIUM | 非本地明文 HTTP 端点 |
| `network-local-http` | LOW | 本地/私网 HTTP 端点（`_LOCAL_HTTP_HOSTS` = `localhost`/`127.0.0.1`/`0.0.0.0`/`::1`，`orchestrator.py:147`；私网段由 `_EXTERNAL_HTTP_RE` 的 host 判定分流） |

`RuleSpec` 是 `frozen dataclass`，字段 `rule_id/severity/message/remediation`（`skillscan/models.py:36-42`）；`RULES` 由 `_SPECS` 列表推导（`orchestrator.py:97`）。**没有** category/analyzer 字段——类别与所属分析器编码在 `rule_id` 前缀（`models.py:1-8`）。

### 3.2 上限常量

| 常量 | 值 | 位置 |
|------|-----|------|
| `MAX_TOTAL_ARCHIVE_BYTES` | 512 MiB | `orchestrator.py:42` |
| `MAX_FILE_BYTES` | 64 MiB | `orchestrator.py:43` |
| `_BLOCK_SEVERITY` | `"CRITICAL"` | `orchestrator.py:45` |
| `_NESTED_ZIP_PEEK_MEMBER_LIMIT` | 256 | `orchestrator.py:46` |
| `_MAX_ARCHIVE_MEMBERS` | 4096 | `orchestrator.py:47` |
| `_TEXT_PROBE_BYTES` | 4096 | `orchestrator.py:48` |
| `_PYTHON_CLIENT_ANALYSIS_BUDGET` | 100 000 | `orchestrator.py:1594` |
| 安装器抽取默认上限 | 512 MiB / 4096 成员 | `installer.py:115-120` |
| review 侧镜像 `PackageLimits` | 4096 / 64 MiB / 512 MiB | `skills/review/models.py:33-47` |
| 🆕 `EXEC_SNIFF_BYTES` | `(_EXEC_SNIFF_LIMIT - 1) + max(magic len)` | `skills/package_files.py:62` |
| 🆕 `_EXEC_SNIFF_LIMIT` | 64（前导填充跑满即判非可执行） | `skills/package_files.py:20` |
| 🆕 mutation 扫描预算 | 32 文件 / 1 MiB 总量 / 120 s | `skills/mutations/scanner.py:20-22` |
| 🆕 mutation 主文件上限 `MAX_MAIN_BYTES` | 128 KiB | `skills/mutations/validation.py:12` |

### 3.3 异常类型与调用面

```
skillscan/models.py
├── StaticScannerError(RuntimeError)        # :45-46  包边界无法评估（坏 ZIP、非目录）
└── StaticScanBlockedError(ValueError)      # :49-59  命中 CRITICAL；带 findings + skill_name

installer.py（面向 Gateway 的翻译层）
├── SkillSecurityScanError(ValueError)      # :39-48  统一包装上面两者 + LLM 扫描拒绝
└── SkillAlreadyExistsError(ValueError)     # :35-36
```

- `StaticScannerError` 的抛出点：`scan_archive_preflight` 的 `BadZipFile/OSError`（`orchestrator.py:247-290`）、`scan_skill_dir` 的非目录（`orchestrator.py:291-337`）。
- `StaticScanBlockedError` 只在 `enforce_static_scan` 命中 CRITICAL 时抛（`orchestrator.py:222-245`，构造点 `:231-237`），消息由 `format_static_findings`（`:212-220`）拼装。
- `deerflow/skills/security_static_scanner.py`（25 行）是**兼容 re-export**：把 `SecurityFinding` 别名成 `StaticFinding`，并再导出 6 个函数与 2 个异常（`:3-25`）。新代码直接 import `deerflow.skills.skillscan`。
- **调用面**（权限/阻断层级从低到高）：`enforce_static_scan`（写入门：`skill_manage` / storage 安装的抽取后扫描）→ `scan_archive_preflight`（安装前只读元数据）→ `scan_skill_dir`（任意目录，被 review core 适配器复用）。三者都是**纯同步**函数，async 调用方自行 offload（模块 docstring `orchestrator.py:3-5`）。
- 结果形状 `ScanResult = {findings, blocked, scanner_errors}`（`models.py:29-32`）；`blocked` 只由是否存在 `_BLOCK_SEVERITY` finding 决定（`_scan_result`，`orchestrator.py:1328-1330`）。`scanner_errors` 是逐文件/逐成员的字符串（读取失败、analyzer 异常），**不阻断**，由 `enforce_static_scan` 记 warning（`orchestrator.py:238-239`）。
- `_dedupe` 的键是 `(rule_id, file, line)`、保留首次出现（`orchestrator.py:1333-1342`）；`secret-*` 的 `evidence` 一律替换为字面 `"[redacted]"`（`_redact_secret_evidence`，`orchestrator.py:1321-1326`，注释解释**连前缀都不留**——`value[:6]` 也会把真 token 字节带进会流向 Gateway 响应与 LLM 上下文的 findings；统一在 `_finding` 中应用，`orchestrator.py:1256-1259`）。

> **See also:** [Skills 与 Tool 系统](skill-md-and-tool-assembly.md)（加载/投影/导出/写入门）· [Skill Review Core](skill-review-core.md)（SkillScan 的只读适配层）· `skills/AGENTS.md`（SkillScan 与 installer 的权威纪律）
