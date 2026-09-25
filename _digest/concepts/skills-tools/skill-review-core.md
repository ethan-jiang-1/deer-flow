---
title: "Skill Review Core（skills/review/）"
description: "只读快照 → 确定性 facts → 报告/readiness 的完整契约：readers / analyzer / resource_graph / eval_schema / digest / renderer / cli / models。"
topics: [skills, review, contract]
---

# Skill Review Core

`backend/packages/harness/deerflow/skills/review/` 是 skill 质量审查的**确定性内核**：只读、不执行目标脚本、不装依赖、不联网、不 import `app.*`。三个 JSON 契约（`contracts/skill_review/`）依次对应三层管线，schema 版本常量定义在 `deerflow/skills/review/models.py:11-13`：`deerflow.skill-package-snapshot.v1` / `deerflow.skill-review.facts.v1` / `deerflow.skill-review.report.v1`。

```
readers.py  →  snapshot     （有界只读抓取，字节忠实）
analyzer.py →  facts        （确定性分析 + SkillScan 适配）
renderer.py →  report       （readiness / issues / recommendations）
```

> 本文只写契约与失败模式；waiver 机制、`review_skill_package` 工具的标签/artifact 语义见主文档 [`skill-md-and-tool-assembly.md`](skill-md-and-tool-assembly.md) 的 "Skill Review 质量门禁" 一节。

---

## 1. 快照读取 `readers.py`

| 入口 | 签名 | 语义 |
|------|------|------|
| `build_inline_snapshot` | `(content, *, name_hint=None, limits=DEFAULT_PACKAGE_LIMITS) -> snapshot` | 内联 SKILL.md 文本 → 单文件快照（`source="inline"`）；超 `max_file_bytes` 时截断并记 `file_too_large`（`readers.py:103-134`） |
| `LocalDirectoryReader` | `(root, *, subject=None, limits=DEFAULT).read()` | 本地目录抓取；不跟随逃逸符号链接（`readers.py:137-261`） |
| `ArchivePackageReader` | `(archive_path, *, limits=DEFAULT).read()` | `.skill` ZIP 抓取，**不安装、不解压到磁盘**（`readers.py:264-344`） |
| `InstalledSkillReader.from_target` | `(target, *, storage, limits=DEFAULT)` | 按 `skill://` 身份定位已安装 skill 后走目录读取（`readers.py:369-391`） |
| `parse_skill_uri` | `(target) -> (category, rel_path)` | 语法 `skill://<public\|custom\|legacy>/<relative-path>`；其它 category / 缺斜杠 / 穿越 / 绝对路径 → `ValueError`（`readers.py:394-402`） |

`skill://` 根解析（`readers.py:405-409`）：`custom` → `storage.get_user_custom_root()`；`legacy` → `<skills_root>/custom/`；其余 → `<skills_root>/<category>/`。注意合法 category **只有 public/custom/legacy**，不含 integrations（`readers.py:399`）。

### limits 与截断语义

- `PackageLimits(max_files=4096, max_file_bytes=64 MiB, max_total_bytes=512 MiB)`（`models.py:33-47`）。总量上限是 **512 MiB**，与导出路径的 100 MiB 不是同一个数。
- 目录读取：超文件数/总量 → `truncated=True` 并**立即返回**（后续文件不再读）；单文件超限 → 记一条 `kind="binary"`、`sha256=""`、`content=None` 的占位条目 + `file_too_large`，然后继续扫其它文件（`readers.py:190-212`）。
- 归档读取：成员先按文件名排序；成员数超 `max_files` 截断列表；单成员按**声明大小**先判，再以 1 MiB 分块读、在 `max_bytes+1` 处判实际解压超限（声明大小不可信，实际字节同样受限，锚 `backend/tests/test_skill_review_core.py:315,357`）；剩余总量为 0 时 break（`readers.py:285-325,352-366`）。
- 符号链接不跟随：记为 `kind="symlink"` 条目，`target` 是链接目标，`sha256` 是 target 字符串的哈希（`readers.py:224-246,326-329`）。
- 文本/二进制判定 `_decode_text`：只要（后缀不在 `_TEXT_EXTENSIONS` 白名单**且**数据含 NUL）**或** UTF-8 严格解码失败，就判 `kind="binary"`；否则 `kind="text"`。`_TEXT_EXTENSIONS` = `.md/.py/.sh/.json/.yaml/.toml/.ts/.js/.csv/.html/.css/.svg/.txt/.yml`（`readers.py:20-35,43-50`）。二进制条目保留原始字节到 `content_base64`——SkillScan 的包级规则（可执行 magic、嵌套归档、无法解码的脚本）需要真字节（`readers.py:53-67`）。
- 输出确定性：路径一律 `normalize_relative_path` 规范化（拒绝空/绝对/`..`/解析到根，`models.py:55-69`）；`files` 按 path 排序，`reader_errors` 按 `(path, code)` 排序（`readers.py:257-261,334-335`）。

### `reader_errors[].code` 全集（分析层用它推导 completeness）

`root_not_found`、`root_not_directory`、`too_many_files`、`stat_failed`、`total_size_exceeded`、`file_too_large`、`read_failed`、`path_escaped`、`invalid_archive_path`、`archive_member_read_failed`、`archive_read_failed`（`readers.py:159-332`）。

---

## 2. 确定性分析 `analyzer.py`

入口 `analyze_skill_package(snapshot, *, profile: "deerflow"|"agentskills" = "deerflow") -> facts`（`analyzer.py:28`）。纯函数、无 I/O。

severity 词表 `blocker | error | warning | info`（`models.py:15`），全局排序 rank `blocker=0 < error=1 < warning=2 < info=3`（`models.py:18-23`）。

### rule_id 分类

| 类别 | rule_id | severity |
|------|---------|----------|
| 结构 | `structure.missing-skill-md`、`structure.skill-md-not-text`、`structure.nested-skill-md` | blocker |
| 结构（frontmatter） | `structure.invalid-frontmatter`、`structure.missing-name`、`structure.missing-description` | blocker |
| 结构（frontmatter） | `structure.invalid-name`、`structure.description-too-long`、`structure.empty-body`、`structure.invalid-allowed-tools`、`structure.invalid-required-secrets`、`structure.invalid-secrets-autonomous` | error |
| 结构（frontmatter） | `structure.unknown-frontmatter-field` | warning |
| 包属性 | `package.symlink`、`package.nested-archive`、`package.hidden-sensitive-file` | warning |
| 资源图 | `resource.missing`、`resource.escaping-link`、`resource.unreferenced` | warning |
| eval | `eval.binary-manifest`、`eval.invalid-json` | warning |
| SkillScan | 继承 SkillScan 的 rule_id（见下） | 映射 |
| 便携 profile | `agentskills.description-length`（>200 字符）、`agentskills.name-length`（>64） | warning |

来源：`analyzer.py:40-110,149-303`。

判定细节（都是契约级）：

- `structure.nested-skill-md` 豁免 `evals/fixtures/**/SKILL.md`（`package_paths.is_eval_fixture_skill_md`），其余嵌套 `SKILL.md` 一律 blocker（`analyzer.py:62-71`）。
- frontmatter 白名单是 `frontmatter.ALLOWED_FRONTMATTER_PROPERTIES`；未知键只是 warning，而不是安装门的硬失败（`analyzer.py:164-175`）。非字符串 YAML 键在 `split_skill_markdown` 里已被 `str()` 化，因此表现为 unknown field 而不是崩溃（`frontmatter.py:58-63`，锚 `backend/tests/test_skill_review_core.py:68`）。
- name 必须 `[a-z0-9]+(?:-[a-z0-9]+)*` 且 ≤64（`analyzer.py:370-371`）；description 空白即 blocker，>1024 字符是 error（`analyzer.py:201-221`）。
- 注意：analyzer 的 1024 检查只看长度；安装/写入门 `skills/validation.py:77-80` 额外拒绝含 `<`/`>` 的描述。两者不是同一条规则，review 不会因为尖括号报错。

### SkillScan 适配 `_scan_with_skillscan`

- 把快照里除 `symlink` 与 eval-fixture `SKILL.md` 之外的**每个**文件按字节写进临时目录（文本用 `content`，二进制用 `content_base64`），再调 `scan_skill_dir`（`analyzer.py:306-324`）。
- 用 `open("xb")` 独占创建：重复归档成员或大小写折叠冲突会让扫描 fail-closed（抛 `ValueError` → `skillscan` 记入 `not_assessed`），而不是静默覆盖前一个文件（`analyzer.py:320-323`，锚 `tests/test_skill_review_core.py:237`）。
- 未截断快照里"没有字节"的条目同样抛错，避免静默跳过；只有已截断快照允许跳过超大条目（`analyzer.py:356-367`，锚 `tests/test_skill_review_core.py:258,269`）。
- 严重度映射 `SKILLSCAN_SEVERITY_MAP = {CRITICAL: blocker, HIGH: error, MEDIUM: warning, LOW: info}`（`models.py:25-30`）；原始 SkillScan 级别保留在 `finding["skillscan_severity"]`（`analyzer.py:339`）。
- SkillScan 抛任何异常都不中断 review：记 `analyzer_errors=[{"code": "skillscan_failed", "message": <异常类名>}]` 并把 `"skillscan"` 加入 `not_assessed`（`analyzer.py:112-116`）。SkillScan 自身的 `scanner_errors` 逐条变成 `skillscan.scanner-error`（warning，`analyzer.py:342-352`）。

### facts 顶层形状与 completeness

```
schema_version, subject{display_ref, source, category, declared_name, package_digest},
profile, completeness{package_enumerated, text_content_complete, truncated, not_assessed},
summary{blockers, errors, warnings, infos}, findings[], resources, evals,
reader_errors[], analyzer_errors[]
```

- `package_enumerated = 无 root_not_found`；`text_content_complete = not truncated`；`not_assessed` 去重排序，取值 `"skillscan"` / `"full_package"`（`analyzer.py:134-139`）。
- findings 统一排序键：`(severity rank, path, line(None→∞), rule_id, message)`（`models.py:101-111`）；`summary` 由 severity 计数得出（`models.py:114-125`）。

---

## 3. 资源图 `resource_graph.py`

`build_resource_graph(snapshot) -> (graph, findings)`（`resource_graph.py:18`）。

- 引用提取三种来源（`resource_graph.py:12-14,89-99`）：Markdown 图片/链接（去掉 `#anchor`）、反引号代码 span（仅当含 `/`）、`(references|scripts|templates|assets|evals)/...` 形态的路径 token。
- 解析规则 `_resolve_reference`（`102-115`）：URL scheme / `#` 开头 / 空 → 跳过；含 `://` → 跳过；绝对路径或 `..` 穿越 → `__ESCAPES__`；否则相对源文件目录规范化。
- 源文件为 eval fixture 时整条跳过（`26`）。
- findings：`resource.missing`（被引用但包内不存在）、`resource.escaping-link`、`resource.unreferenced`，全部 warning（`47-79`）。
- orphan 定义：`references|scripts|templates|assets|evals` 顶层目录下、未被任何 edge 指向的文件，扣除 `evals/evals.json`、`evals/trigger_eval_set.json` 与全部 fixture 路径（`42-45`）。
- graph 形状 `{nodes:[{path,kind}], edges:[{source,target}], orphans:[...]}`，全部排序确定（`81-85`）。测试锚点：`tests/test_skill_review_core.py:84,94,104`。

---

## 4. eval manifest `eval_schema.py`

`analyze_eval_manifests(snapshot) -> (aggregate, findings)`（`eval_schema.py:11`）。候选 = `evals/**.json`。

- aggregate 字段：`schema / valid / case_count / positive_trigger_cases / negative_trigger_cases / manifests`；无候选时为 `schema=None, valid=None`（`15-24`）。
- 四种 manifest 形态（`72-85`）：`versioned`（dict 且有 str `schema_version`，取 `cases` 列表）、`skill-creator-evals`（dict 且有 `evals` 列表）、`trigger-eval-list`（顶层 list）、`unknown`。多 schema 混合 → `"mixed"`（`66-67`）。
- case 统计只看 `should_trigger is True/False`（非 dict 跳过）（`88-105`）。
- 失败模式：非文本 manifest → `eval.binary-manifest`（warning）+ `valid=False`；JSON 语法错 → `eval.invalid-json`（warning，带 `line=exc.lineno`）+ `valid=False`（`30-57`）。`valid` 表示"全部可解析"，与形态无关。

---

## 5. 包 digest `digest.py`

`compute_package_digest(snapshot) -> "sha256:<hex>"`（`digest.py:11`）：

- 每个文件一条 record = `kind \0 path \0 size \0 sha256`（path 经 `normalize_relative_path`），**按字节序排序**后逐条以 8 字节大端长度前缀喂给 SHA-256（`13-33`）。
- 不含主机路径、不含遍历顺序 → 同一包在不同主机/不同枚举顺序下 digest 相同（`tests/test_skill_review_core.py:116`）。facts 的 `subject.package_digest` 与报告 `subject.package_digest` 都来自它。

---

## 6. 报告与 readiness 状态机 `renderer.py`

`readiness_from_facts(facts, *, scope=None) -> Readiness`（`renderer.py:43-51`），判定顺序固定：

1. `summary.blockers > 0` → `blocked`
2. `summary.errors > 0` → `revise`
3. `scope` 含 `"all"` 且 `completeness.not_assessed` 非空 → `revise`
4. 否则 → `publish_candidate`

`build_static_report(facts, *, scope=None, reviewer_model="deterministic-review-core", completed_at=None) -> report`（`renderer.py:54`）：

- `review.scope` 默认 `["all"]`；`completed_at` 默认 UTC 秒级 ISO8601（`Z` 后缀）；`review.facts_schema_version` 回填 facts 的 schema 版本（`88-100`）。
- `assurance` 恒为 `"static_only"`；另三个字面量 `trigger_checked / behavior_verified / regression_verified` 留给语义/运行时审查（`renderer.py:10-12,102`）。
- `issues` 只收录 severity ∈ `{blocker, error, warning}`，且做语义映射 `blocker→blocker`、`error→major`、其余 `→minor`，`confidence="high"`，id 形如 `deterministic.{n}.{rule_id}`（`64-78,171-176`）。
- `dimensions` 固定两条：`structure`（有 blocker→`blocker`；有 error/warning→`concern`；否则 `pass`）与 `evidence_quality`（`evals.case_count == 0` → `concern`）（`179-193`）。
- `evidence.facts_complete = not truncated`；`limitations` 依次来自 truncated、`reader_errors`、`analyzer_errors`；`runtime_runs / baseline / retained_artifacts` 恒为空（`80-111`）。
- `recommended_actions`：`publish_candidate` → `[]`；否则取前 **5** 条 finding 的 `"{rule_id}: {remediation}"`（`196-201`）。
- `render_report_markdown(report, facts=None, *, locale="en"|"zh")` 生成固定 7 段 Markdown；locale 只切标题与标签文案（`116-168`，中文标签锚 `tests/test_skill_review_core.py:410`）。

---

## 7. CLI `cli.py`（CI 门禁）

`main(argv=None) -> int`（`cli.py:15-46`）：

| 参数 | 取值 | 语义 |
|------|------|------|
| `target`（位置） | 目录或 `.skill` | 后缀 `.skill` → `ArchivePackageReader`，否则 `LocalDirectoryReader`（`38`） |
| `--profile` | `deerflow`（默认）/ `agentskills` | 传给 `analyze_skill_package` |
| `--format` | `json`（默认）/ `text` | JSON 走 `stable_json_dumps`（字节稳定、路径无关，`models.py:50-52`） |
| `--fail-on` | `never`（默认）/ `warning` / `error` / `blocker` | 任一 finding 的 rank ≤ 阈值 → 退出码 1 |
| `--fail-on-incomplete` | flag | `completeness.not_assessed` 非空 → 退出码 1（优先于 `--fail-on`） |
| `--max-files` / `--max-file-bytes` / `--max-total-bytes` | int | 覆盖 `DEFAULT_PACKAGE_LIMITS` |

退出码逻辑（`cli.py:64-73`）：`fail_on_incomplete` 命中 → 立即 1；`fail_on == "never"` → 0；否则逐条 finding 比较 rank。CI 建议 `--fail-on error --fail-on-incomplete`。锚点：`tests/test_skill_review_core.py:282,422,446`、`tests/test_review_changed_public_skills.py:285`。

---

## 8. 边界（review 不做什么）

- 只读：不执行 skill、不安装依赖、不联网；快照字节原样交给 SkillScan，不在 review 内重写。
- 模型可见载荷由 `tools/builtins/review_skill_package_tool.py` 组装：compact JSON（`stable_json_dumps` 后经 `neutralize_untrusted_tags` 中性化）+ `ToolMessage.artifact` 携带完整 payload（含 en/zh Markdown 渲染），语义 artifacts 上限 `_MAX_SEMANTIC_ARTIFACT_CHARS = 80_000`（`tools/builtins/review_skill_package_tool.py:23,53-80,146-158`）。
- 工具用 `review_subject_entry`（**不是** `skill_context_entry`）标注结果 → 审查不会激活被审 skill、不绑定其 `required-secrets`、不施加其 `allowed-tools`（`skills/AGENTS.md`，`review_skill_package_tool.py:65-80`）。
- 语义/行为验证、mutation、运行时实验不属于 review core（属 `skills/public/skill-reviewer` 与 `skill-creator`）。

## 测试锚点

| 关注点 | 测试 |
|--------|------|
| 三层 schema 校验、最小合法 skill | `backend/tests/test_skill_review_core.py:43-58` |
| digest 路径无关 | `test_skill_review_core.py:116` |
| SkillScan 适配 / HIGH→error / fixture 豁免 | `test_skill_review_core.py:129,142,155,207` |
| 快照字节忠实、重名 fail-closed | `test_skill_review_core.py:179,193,237,258,269` |
| 归档穿越/符号链接/解压上限 | `test_skill_review_core.py:294,315,357` |
| readiness / 中文渲染 / CLI 退出码 | `test_skill_review_core.py:282,410,422,446` |
| 资源图 | `test_skill_review_core.py:84,94,104` |

> **See also:** [Skills 与 Tool 系统](skill-md-and-tool-assembly.md)（SkillScan / export / projection 契约）· `contracts/skill_review/`（四个 JSON Schema）· `scripts/review_changed_public_skills.py`（CI 执行器）
