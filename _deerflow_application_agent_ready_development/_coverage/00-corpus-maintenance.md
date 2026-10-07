# 语料维护：基线、证据范围与重审

## 钉定基线

- **上游仓库**：`bytedance/deer-flow`
- **钉定版本**：release tag `v2.1.0`，指向 commit `345f08be`（"chroe(doc): update the release version to 2.1.0"；tag 对象 `f6e747be`）。外链一律使用 `https://github.com/bytedance/deer-flow/blob/v2.1.0/…` 形式。
- **钉定理由**：v2.1.0 是下游应用开发者实际安装的上游正式发布版本；钉 release tag 比钉研究分支更能代表"用了 DeerFlow 的人拿到的东西"。
- **托管位置说明**：本语料目前托管在一个包含 v2.1.0 为祖先的研究分支上（v2.1.0 是该分支 HEAD 的祖先，已用 `git merge-base --is-ancestor` 核验）。**工作树文件不等于钉定版本**：所有行号锚点必须对 tag 核验，不能直接引用工作树。

## 证据范围与排除项

**只采用** v2.1.0 上的：源码、`AGENTS.md` 指南网络、docs 站 harness 手册（`frontend/src/content/{en,zh}/harness/`）、`backend/packages/extension-api/` 公共契约、`examples/deerflow-extension-example/` 示例扩展、`backend/docs/`、根 README、`.github/`（PR 模板与 workflows）、`RELEASING.md`、迁移链与 `contracts/`。

**明确排除**（重要）：

1. **宿主分支在 v2.1.0 之后引入的内容不属于本语料的证据**——包括 `docs/testing/`（五级证据阶梯文档）、`backend/packages/harness/deerflow/testing/`（测试 kit）、`backend/tests/AGENTS.md` 的测试资产命名规则、extension 示例的后加改动。这些是 tag 之后移植进宿主分支的材料，v2.1.0 上不存在（已用 `git ls-tree v2.1.0` 逐项核验为空）。本语料的验证指导必须从 v2.1.0 实际交付的东西推导——示例扩展自带的测试、docs 站手册、主仓测试中对扩展面的覆盖——而不是引用这些后加材料。
2. 宿主仓库的 `_digest/`、`_faq_on_digested/` 等研究笔记不参与证据链。
3. 任何二手转述或仓库外材料。

**离线核对方法**：在有该 tag 的 DeerFlow checkout 中执行 `git show v2.1.0:<path>` 读取文件、`git ls-tree v2.1.0 <dir>` 列目录。引用行号时先 `git show` 再数行，不数工作树。

## 结构约束（由 verify.mjs 强制）

- Markdown 文件严格 UTF-8、LF 换行、恰好一个结尾换行；
- 相对链接必须在语料内可达，锚点必须命中目标文件的真实标题；
- 外链只允许钉定 `v2.1.0` 的 `bytedance/deer-flow` blob/tree/releases 地址；
- 含 Markdown 的目录必须有 README.md；
- SVG（若引入）必须有固有 width/height 与 `<title>`/`<desc>`。

## 重审触发路径

| 上游变化 | 需要做什么 |
|---|---|
| 新 release tag 发布 | 评估 re-pin：逐条复核正文结论与链接，不能只替换 URL；旧结论过时要改写并在本页登记 |
| extension-api 契约变化（贡献类型、placement、auth、run_evidence） | 复核应用开发模型卷的接入形态与契约页 |
| `AGENTS.md` 网络或 docs 站 harness 手册结构调整 | 复核开发 Harness 卷的现状清单（这类"现状清单"最容易在 re-pin 时漏改） |
| PR 模板、CI workflows、发版或迁移制度变化 | 复核 SDLC 参考卷对应页 |
| 示例扩展被移动或删除 | 复核新仓起步页的入口路径 |

## 历轮记录

### 2026-10-07 · 第 1 轮（建语料）

- 钉定基线 v2.1.0（`345f08be`），确认其为宿主分支祖先；确认 tag 后宿主分支改动清单（49 个文件，含移植的测试策略材料），登记上文排除项。
- 建立骨架：入口 README、三卷（`application-development-model/`、`sdlc-reference/`、`repo-harness/`）各自的 README 与入口页、`_coverage/` 维护层。
- 落地结构验证器 `verify.mjs` 与自测 `verify.test.mjs`（正例 + 四类负例），全部通过。
- 三卷正文页本轮未建：卷入口页登记了各卷规划页清单与取证入口，后续轮次按页补齐并对 tag 逐条核验锚点。

### 2026-10-07 · 第 2 轮（卷一正文两页）

- 核验 v2.1.0 与宿主分支的文件一致性：卷二全部源文件（PR 模板、7 个 workflow、RELEASING、CONTRIBUTING、SECURITY、migrations 指南、CONFIGURATION、maintainer-orchestrator 设计、3 份 spec/plan）在 tag 与工作树**完全一致**——第 3 轮起可直接复用宿主分支读取的锚点；仅根 `AGENTS.md`（+2 行）与 `backend/AGENTS.md`（+5 行）有偏移，引用这两文件时必须对 tag 重数行号。
- 建成卷一两页：`01-new-application-repository.md`（四种接入形态、最小入口、安装事务与分发来源、信任边界、四层决定清单）与 `02-terms-and-mental-models.md`（分层/执行/能力/装载/验证五组术语 + 常见误读）。
- 取证来源（全部对 tag 读取）：`examples/deerflow-extension-example/`（README/plugin.py/pyproject）、`frontend/src/content/en/harness/`（quick-start、integration-guide、skills、lead-agent、sandbox、extensions/quick-start）、`backend/packages/harness/deerflow/extensions/AGENTS.md`（tag 与工作树一致）。
- 关键精确事实登记：契约贡献类型**七种** vs 示例演示**五种**；v2.1.0 的示例测试口径为**契约级**（"harness and Gateway are not imported"），真实组合验证模式未随 v2.1.0 交付——正文已如实标注为该版本的诚实边界。

### 2026-10-07 · 第 3 轮（卷二十页全部建成）

- 写成 SDLC 参考卷全部十页：01 意图与范围、02 spec 产权、03 TDD 与车道、04 PR 表面与 AI 披露、05 CI 门禁矩阵、06 架构/文档/工具链契约、07 发版与版本门、08 迁移链、09 运维反馈与失败回写、10 扩展信任边界。
- 每页统一结构：什么时候读 → 主仓机制（blockquote 摘录 + 钉版文件级链接，标注成文标准/机器门禁/仓库外不可核实）→ 应用仓适用边界 → 证据入口。
- 证据复用核验：卷二全部源文件已在第 2 轮确认与 tag 一致，本轮零重锚；两份 AGENTS.md 的关键段落（TDD 军规、run-context 双入口、plugins 信任块、skill 豁免）与六个门禁文件（test_harness_boundary、check_agent_guidance、test_middleware_documentation、test_ci_uv_version_pin、skill-review-waivers、review_changed_public_skills）逐一对 tag 核验内容/存在性。
- 诚实边界登记：05 页明示路径分流/draft 跳过/live 不进 CI/required checks 仓库外不可见；07 页明示发布门强于 PR 门的不对称；09 页明示失败回写无门禁属文化惯性；10 页明示 SECURITY.md 无 SLA、隔离的是故障不是恶意。

### 2026-10-07 · 第 4 轮（卷三六页建成，语料主体完成）

- 写成开发 Harness 卷全部六页：01 参与路径（指南网络与 nearest-file 规则）、02 指南预算与文档测试（四档预算常量 + exec 示例 + 语义边界）、03 docs 站手册阶梯（三层结构 + 双语）、04 示例与契约（示例包/extension-api/contracts 三分）、05 配置与检查面（示例配置、config_version、doctor、support-bundle）、06 边界与代价（六条可核验负面事实 + 应用仓对策清单）。
- 本轮核验：`backend/AGENTS.md` nearest-file 规则在 tag 存在；`check_agent_guidance.py` 与宿主分支一致（四档预算常量对 tag 确认）；`zh/harness/` 双语镜像在 tag 存在；`contracts/` 七个 JSON 契约在 tag 列出；doctor/support-bundle 目标在 tag 根指南存在。
- 语料主体至此完成：三卷 18 页正文 + 三份卷索引 + 入口 README + 维护层 + 验证器。图示（SVG）暂未引入——验证器已含 SVG 规则，引入图时按规则补；此为登记在案的可选后续项，不阻塞语料可用性。

### 规划中的正文页（未建，建后在本表打钩并注明轮次）

- ~~应用开发模型卷：01 新仓起步（四种接入形态选择）、02 术语与心智模型~~（第 2 轮建成）；
- ~~SDLC 参考卷：01 意图与范围对齐 至 10 扩展信任边界 共十页~~（第 3 轮建成）；
- ~~开发 Harness 卷：01 新 agent 的参与路径 至 06 边界与代价 共六页~~（第 4 轮建成）。

可选后续项（不阻塞）：各卷 SVG 图示；re-pin 演练（上游发新版时逐条走重审触发路径）。
