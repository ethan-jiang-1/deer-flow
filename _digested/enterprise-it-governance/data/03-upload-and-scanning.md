---



title: "文件上传与 Skills 扫描"
description: '上传的三项配额、7 类转换白名单、同名去重与原子落盘；Skills 的双层扫描（LLM 语义 + 静态规则）与 fail-closed 语义。'
topics: [governance, data, upload]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 文件上传与 Skills 扫描

两条不同的入口，两套不同的控制：用户上传走**配额 + 白名单**，
Agent 生成 skill 走**内容扫描**。

## 1. 上传配额（三项，均可配）

`app/gateway/routers/uploads.py:70-72` 给出默认值：

| 限制 | 默认 | 配置键 |
|---|---|---|
| 文件数 | **10** | `max_files`（旧键 `max_file_count`） |
| 单文件大小 | **50 MB** | `max_file_size`（旧键 `max_single_file_size`） |
| 单次总量 | **100 MB** | `max_total_size` |

解析逻辑在 `uploads.py:179-184` 的 `_get_upload_limits`，
三项都支持 legacy key 回退——所以老配置不会静默失效。

**企业含义**：这三项是**全局**默认值，不是 per-user 配额。
一个用户可以反复上传到磁盘满，只要每次不超过 100 MB。

## 2. 转换白名单（7 类）

`packages/harness/deerflow/utils/file_conversion.py:34-42`：

```python
CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".ppt", ".pptx", ".xls", ".xlsx", ".doc", ".docx",
}
```

共 7 项（PPT/Excel/Word 各两种格式 + PDF）。非白名单文件**不做转换**，
但仍可上传（作为普通文件放进 uploads）。

### 2.1 转换不是「上传才做」

转换由 `convert_file_to_markdown` 在需要时触发，
`file_conversion.py:44-48` 有一处重要说明：

> If pymupdf4llm produces fewer characters *per page* than this threshold,
> the PDF is likely image-based or encrypted — fall back to MarkItDown.
> Rationale: normal text PDFs yield 200-2000 chars/page.

**含义**：PDF 先走 `pymupdf4llm`，低产出时回落 `MarkItDown`。
两条转换路径意味着**两条解析器的攻击面**——扫描型 PDF 是最常见的恶意载体。

## 3. 落盘的安全细节

`uploads.py` 有一组 `_pure_destination` / `_prepare_upload_destination` /
`_link_staged_no_overwrite` / `_commit_upload_temp_no_overwrite`（`:198`、`:221`、`:241`、`:291`）：

| 机制 | 防御的问题 |
|---|---|
| `_pure_destination` | 文件名里的路径分隔符（`../`） |
| staged temp + `_link_staged_no_overwrite` | **TOCTOU**：先写临时文件再原子链接 |
| `_commit_upload_temp_no_overwrite` | 并发同名覆盖 |
| `_cleanup_uploaded_paths` | 失败时清理半成品 |

**`no_overwrite` 系列函数名是刻意的**：上传不覆盖已有文件，
同名冲突走去重而不是替换。

## 4. Skills 扫描：两层，且 fail-closed

原文只说「LLM-based 安全检查」，实际是**两层**：

| 层 | 实现 | 作用 |
|---|---|---|
| 静态规则 | `skills/security_static_scanner.py` | 确定性的模式匹配（危险命令、可疑路径等） |
| LLM 语义 | `skills/security_scanner.py:97` `scan_skill_content` | 语义判断，输出 allow/warn/block |

### 4.1 决策协议

`security_scanner.py:120-124` 要求模型返回严格 JSON：

```
"Classify the content as allow, warn, or block."
'{"decision":"allow|warn|block","reason":"..."}'
```

| 返回值 | 处理 |
|---|---|
| `allow` / `warn` / `block` | 按决策执行（`security_scanner.py:165`） |
| 无法解析 | **`block`**，理由 "Security scan produced unparseable output; manual review required."（`security_scanner.py:175`） |

**这是 fail-closed**：模型输出格式错误时不是放行，而是阻断并转人工。

### 4.2 静态发现会作为上下文喂给 LLM

`security_scanner.py:85` 的 `_format_static_findings_context`：
静态扫描的结果被格式化后作为 LLM 判定的输入。所以两层不是并列，而是
**静态结果增强语义判断**。

### 4.3 fail_closed 可配

`security_scanner.py:30` 的 `_resolve_fail_closed(app_config)` 说明
「扫描器不可用时是否阻断」是个配置项。

| 配置 | 扫描器故障时 |
|---|---|
| `fail_closed: true` | 阻断写入 |
| `fail_closed: false` | 放行（仅告警） |

**两条边界**：`fail_closed: false` 仍会 block **可执行文件**（`security_scanner.py:176-177`）；
配置键是 `skill_evolution.security_fail_closed`。静态层可被 `skill_scan.enabled: false` 关闭
（`config.example.yaml:2182-2187`），关闭后仍有归档安全检查与 LLM 层；
分析器内部错误只 warn（`skills/skillscan/orchestrator.py:239-240`）。

## 5. 数据保留（与 06 对齐）

当前只有**项目回收站**的 `trash_retention_days`（启动 + 列表惰性清扫），
没有 thread/memory/上传的自动过期：

| 操作 | 清理范围 |
|---|---|
| `DELETE /api/threads/{id}` | LangGraph thread + 本地 thread 目录 + runs + run 事件（并置证据 `partial`） |
| 删除用户 | 使 PAT 失效（`pat.py:224-228`）；文件目录需自行清理 |
| memory 过期 | **无**——没有 TTL 或自动归档 |

详见 [06-retention-and-residency.md](06-retention-and-residency.md)。

## 6. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| 病毒/恶意文件扫描 | **无** | 无 ClamAV 类集成；白名单只限扩展名，不限内容 |
| per-user 上传配额 | **无** | 三项配额是全局默认（`uploads.py:70-72`） |
| 上传文件的内容类型校验 | **部分** | 扩展名白名单 + 转换器解析失败即报错；无 magic-bytes 校验 |
| skill 扫描的规则可配 | **部分** | LLM 提示词硬编码在 `security_scanner.py:120-124` |
| 扫描事件审计 | **无** | `block` 决策无结构化事件上报 |
| 保留期自动清理 | **无** | 见 §5 |

## 7. 与其他章节的关系

- 存储布局与隔离：[01-storage-and-isolation.md](01-storage-and-isolation.md)
- PII 脱敏（默认关闭）：[05-pii-redaction.md](05-pii-redaction.md)
- 保留期与数据驻留：[06-retention-and-residency.md](06-retention-and-residency.md)
- Skill 扫描的插件侧契约：`_digested/internals/skills/`
