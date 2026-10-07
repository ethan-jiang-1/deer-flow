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
- SVG 必须有固有 width/height 与 `<title>`/`<desc>`（当前语料共五张 SVG，分属三卷 figures/ 目录）。

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

### 2026-10-07 · 第 5 轮（系统性 review 修复 + 术语原生性审计 + 图示）

**Review 修复**（结构性/自洽性问题）：
- 补齐卷一结构性缺口：00-index 承诺的闭环步骤 3-6 原无归属页，新增 `03-delivery-and-acceptance.md`（完整 slice、三层证据、安装形态验证、交付记录与常见失败模式）；00-index 闭环六步逐条接通页面归属。
- 清理建仓期过时措辞：四层表中两处"取证中"、"正文页将…逐条落地"、"（预告）"等将来时承诺全部改为已成事实与页面链接。
- 修正三处精度问题：卷三 05 配置复制句语病；卷二 06"四处同步"改为与测试 docstring 对齐的表述；卷二 08"嵌入即继承迁移行为"的过强声明改为条件表述（bootstrap 在引擎初始化执行已核验，嵌入形态是否触发取决于存储配置）；卷一 01 补 integration-guide 示例的"文档是快照"警示（其 Gateway 挂载导入路径与仓库实际布局不一致）与 skill 分发形态说明。

**术语原生性审计**（去 DSH 概念，用 DeerFlow 原生词）：
- `02-terms-and-mental-models.md` 改名 `02-terms.md`（原文件名与 DSH 语料页同名）。
- "事实 owner / owner（人）"→"单一事实源（source of truth）／权威归属／维护者"——DeerFlow 原生 owner 一律是数据行归属/操作员语义（owner-scoped、operator-controlled），"事实的权威维护位置"是外来概念；原生对应词全部有出处：spec 自称 source of truth、实现计划原话 "owned by the spec"、SKILL.md 手册原话 "authoritative definition"。
- "语义评审"→"评审"（DeerFlow 无此命名阶段）；"垂直切片"→"slice"（实现计划原生用词，"Documentation (land with owning slice)"）；"产权"→"权威/所有权"；"铺路路径"→"现成的官方路径"；"定义外部结果"→"从用户可观察的结果定义变更"（锚定 PR 模板 "from a user's / caller's perspective"）；DSH 原句式"能加载≠有证据≠能安装≠已批准"改为语料自己的"能 import、包测试绿、扩展装上了、宿主侧行为被观察到，是四件不同的事"。
- 审计方法：grep 全语料 owner/语义评审/垂直切片/产权/铺路/验收四分/决定记录/外部结果，逐条替换或重锚；历史轮次记录保留原貌。

**图示**（图文并茂，帮助不熟悉 DeerFlow 技术思考的读者）：
- 新增五张 SVG：卷一三张（development-loop 开发闭环、integration-forms 四形态选择、acceptance-evidence 证据层级）、卷二一张（change-gate-levels 变更主线×门禁等级）、卷三一张（guidance-network 指南网络分层与预算）。
- 每卷 `figures/README.md` 图示清单（归属页 + 更新时机）；各卷 README 增"图文分工"节；验证器自测新增 SVG 负例（删 `<title>` 须被 svg-a11y 拒绝）。
- 图中文字同步完成术语原生性替换。

### 2026-10-07 · 第 6 轮（全量复核：原生性 + 事实精度 + 自洽性）

对 v2.1.0 逐条复核三卷全部事实性陈述（`git show v2.1.0:<path>` 直读 tag），修复三类问题：

**事实精度修复**（正文与 tag 不符）：
- 卷一 01/术语页：修正技能分发面的过强否定——v2.1.0 **有**运行时技能归档安装（`POST /api/skills/install`、admin-only `/install/upload`、安全扫描、依赖首次加载时装、启用/停用即时生效）；它与 extension manager 事务的区别是不动 `plugins:`/lock、无需重启、入口是 Gateway API。术语页新增"技能归档安装"词条；integration-forms 图示同步改。
- 卷一 01/02：示例包"覆盖全部贡献维度"的措辞改为"演示五种贡献"——示例 README 自述 all five，契约注册面是七种，原措辞正是术语页警告的"把示例当契约上限"误读。
- 卷一 02 术语页：内置工具条目误把 web search/fetch/渲染截屏归为内置——tools 手册的原生四分类是 built-in / community / MCP / skill 自带工具，已按原分类改写。
- 卷一 01：quick-start 的"装扩展是 operator 动作、需 shell 权限"是**运行时前提**（随使用传导），原标签"主仓要求（不随使用继承）"是类目错误，已改标运行时事实并并入前置条件句。
- 卷三 03：extensions/ 手册实为十页（index + 九个主题页）、subagents/ 实为十一页（index + 十个主题页）；原"九页"漏计 index 且两处口径不一，已统一为"index 加 N 个主题页"。
- 卷三 04：extension-api 模块清单漏 `provenance`（消息生产者声明），已补齐（现共十个模块）。
- 卷二 05：门禁矩阵漏 frontend-unit-tests.yml（前端单测）与 chart.yaml 的 PR 校验 job（含"不跳 draft"例外）；skill 审查行补 workflow 名（skill-review-ci.yml）；来源行从五个补全为十个 workflow；边界注⑤列全其余非主线 workflow；CONTRIBUTING PR Regression Checks 只文档化三个 workflow 的事实已如实标注。
- 卷二 06：uv 版本钉住测试保持一致的实为**四处**（Dockerfile `UV_IMAGE`、两份 compose 默认、全部 CI `setup-uv` 步骤），原文漏 compose。
- 卷二 08：扩展自有表约定的出处是迁移指南"Extension-owned tables"节（非 extensions 指南），且原生约定是私有 `MetaData` + 表前缀（`ExtensionSpec.table_prefix`）让宿主 alembic 忽略，并无"独立 alembic 链"的说法，已按原文改写。
- 卷一 03：curl 观察示例补 README 原有的认证提醒（路由走 Gateway 常规认证）。

**自洽性修复**：
- "四件不同的事"（卷一 00-index）与"三层证据"（卷一 03）在 acceptance-evidence 图示里口径混乱（原题"证据的四个层级"与本节"三层证据"冲突，④ 混入"用户确认"）：图与正文统一为——能 import（不是行为证据）+ 三层证据链（包测试绿/扩展装上了/宿主侧行为被观察到），00-index 与 03 的桥接句同步改。
- 卷号（卷一/卷二/卷三）在跨卷引用中使用但从未定义，入口 README 三卷表已加显式卷号列。
- 卷二 04："AI 披露三问 + 责任声明"改为与模板一致的"AI 披露三项"（工具、用法、人的责任确认——模板原话 "Please fill all three"）。
- 卷二 09：agent 评审禁做清单改为与设计文档一致（不写代码、不管理分支、不关闭/打标 artifact、不发版；原文"合并"系改写失真）。
- 卷二 07："无 bump 脚本"标题与同页 bump_version.sh helper 自相矛盾，改为贴 RELEASING 原文（"no separate release script that bumps versions"，helper 只改齐不决策）。
- 卷三 guidance-network 图示模块层补 scripts/AGENTS.md（与 02 页"backend/frontend/scripts"口径一致）。
- 卷二 00-index 残留的"owning 指南"改"权威指南"（第 5 轮术语审计的漏网措辞）；结构约束节的"SVG（若引入）"改为现势描述（语料已有五张 SVG）。

**维护记录修复**：第 5 轮记录"卷三张"为笔误（三张图属卷一），已更正为"卷一三张"。

本轮核验方法：全部引用路径对 `git cat-file -e v2.1.0:<path>` 验存在；引文对 `git show` 直读核对；目录页数/模块清单/workflow 清单对 `git ls-tree v2.1.0` 重数。结构验证器与自测本轮全部通过。

### 2026-10-07 · 第 7 轮（全语料独立一致性扫描）

第 6 轮修复后，对全部 26 个 Markdown、5 张 SVG 与验证器做一轮独立的全语料内部一致性扫描（新开上下文逐文件通读，不对照 git，专查自洽性），修复其发现的残留问题：

- **卷一 00-index:5 开篇句**仍是第 6 轮统一前的旧措辞（"测试绿/用户验收"作四件事之第四件）——与同页第 20 行、卷一 03 与 acceptance-evidence 图冲突，已改为 canonical 四件事表述；同页"内嵌 client"→"内嵌 harness"、"四级声明"→"四类陈述"、"[卷入口 README]"→"[语料入口 README]"。
- **"安装验证"双口径**：术语页与卷一 01、卷三 06 把第三层"宿主侧观察"并进安装验证定义，与卷一 03/图 ③ 的窄定义（装入＋重启＋确认列表，不证明行为）冲突；三处统一为窄定义＋"与宿主侧观察共同构成最低真实证据"。术语页读法提醒"两个证据层级"改"三层证据"。
- **卷一 03 步数算术**："后四步…前三步"=7≠6（第 3 步实为本页 §1 所有），改"前两步"。
- **接入形态命名漂移**：根 README"内嵌 `DeerFlowClient`"与 development-loop 图"内嵌 client"统一为"内嵌 harness"；development-loop 图步骤④⑥框标题改为 00-index 的步骤名（测试分层对应证据分层/用证据交付）。
- **卷号约定补齐**：卷二 03/10、卷三 02/06 的四处裸跨卷引用补"卷一·/卷二·"前缀；根 README 四类陈述中"运行时事实"定义扩为"接口、实际行为与仓库内容"（卷三对仓库内容事实也用此标签）。
- **change-gate-levels 图**：图例第四项把"仓库外不可核实"（灰块，阶段行中不存在）与"文化惯性"（虚线琥珀）混为一谈，改为四个等级各自的图例＋"仓库外不可核实"单独注释行；PR 表面阶段标"成文标准＋自我声明"、运维反馈标"文化惯性（失败回写）"，与卷二 04/09 的分级对齐。
- **acceptance-evidence 图**：①"证明：入口点可解析、包能装"删"包能装"（与③"分发物可安装"分层混淆），desc 同步。
- **验证器自测枚举**：根 README 与 verify.test.mjs 头注释补第 5 类负例（SVG 缺无障碍标题，第 5 轮已加）。
- **卷二 01**顿号后多余半角空格；**卷二 02**"运行时事实的例外"类目错误改"偏离的登记（成文标准）"；**卷二 05**边界②改"测试 job（lint 与 chart 校验不设 draft 条件）"；**规划表**补登卷一 03（第 5 轮增补）。

本轮方法：独立读者视角逐文件通读＋计数核对（贡献类型 7/5、workflow 10、版本源 5/bump 4、extensions 10 页、subagents 11 页、extension-api 10 模块、contracts 7 JSON、预算 4 档等全部对上）。验证器与自测通过。

### 2026-10-07 · 第 8 轮（术语原生性专项：剔除非 DeerFlow 词汇）

以"每个作为术语使用的词要么是 v2.1.0 原生、要么明确是本语料自己的综合框架"为准绳，逐词扫描并替换外来/杜撰词汇（每个替换词先对 tag 源核验其原生性）：

**外来术语替换**（原词在 v2.1.0 证据源中不存在）：
- **"车道"→"套件"**（test lanes 借自通用测试话语；原生词是 suite——根指南 "Default backend suite"）。文件改名 `03-tdd-and-test-lanes.md` → `03-tdd-and-test-suites.md`，标题改"TDD 与测试套件"，全语料 8 处引用同步；卷三 development-loop 图的步骤④归属页同步。
- **"军规"→"MANDATORY 全大写强制"**（"军规"是中文开发者文化词；原生措辞是 "TDD — MANDATORY"/"MUST"/"No exceptions"），卷二 03 三处。
- **"rules as code"**（外部运动名）→ 删除，用本页自己的原生描述（"把本该靠 review 纪律维持的规矩写成会红会绿的测试"）。
- **"状态灯"→"绿勾"**（对应原生引文 "Evidence over a green check"）。
- **"供应链信任"→"来源信任（只装 trusted operator sources）"**（锚回原生短语）。
- **"评审哲学"→"评审原则"**（原生节名 "Principles that shape the review"）。
- **"贡献维度"→"贡献类型"**（原生词 contribution kinds，与语料其余部分统一）。
- **"硬闸"→"发布链的第一道强制门"**（去掉借喻，贴合 verify-versions 依赖链事实）。
- **"插件沙箱/无插件沙箱"→"扩展代码不在沙箱里执行"**：DeerFlow 原生的"沙箱"是工具沙箱；"插件沙箱"暗示存在一个不存在的原生概念。卷三 06 标题与对策行、卷二 00/10、卷一 00 共五处统一，并补 `IsolatedMiddleware` 原生类名（隔离包装的原生出处）。
- **"agent-ready"**（agent 工具圈流行语）正文删用，改为"对维护者与 coding agent 同样可参与、可验证"（coding agent 是原生词）；语料标题保留作制品名。
- **"posting bar"→"when it posts"**（证据入口的节名改为与设计文档标题一致）。

**杜撰"引文"修正**（引号内容在 tag 源中不存在）：
- 卷三 04：示例包"deliberately small"为杜撰引文——README 原文是 "compact, standalone Python package" 与 "all five small contribution implementations"，已改为引用真实原词。
- 卷三 03：harness quick-start"十分钟跑通"为杜撰——该页没有时间承诺（extensions quick-start 是 fifteen minutes、subagents 是 five minutes），改为原生句 "the fastest way to understand"（model setup → agent creation → streaming a response）。

**原生性增强**：卷三 README 对目录名 `repo-harness` 补与原生术语 harness（`backend/packages/harness/` 的 agent 框架包）的区分说明，明示卷名是语料自己的视角命名。

本轮核验：lane/budget/append-only/deliberately small/minute/principal/IsolatedMiddleware/marker 等候选词逐一对 `git grep v2.1.0` 核验（budget/principal/IsolatedMiddleware/marker 原生，予以保留并锚定）。结构验证器与自测通过。

### 规划中的正文页（未建，建后在本表打钩并注明轮次）

- ~~应用开发模型卷：01 新仓起步（四种接入形态选择）、02 术语与心智模型~~（第 2 轮建成）；
- ~~应用开发模型卷：03 交付与验收~~（第 5 轮增补，超出原规划——补齐 00-index 闭环步骤 3-6 的归属页）；
- ~~SDLC 参考卷：01 意图与范围对齐 至 10 扩展信任边界 共十页~~（第 3 轮建成）；
- ~~开发 Harness 卷：01 新 agent 的参与路径 至 06 边界与代价 共六页~~（第 4 轮建成）。

可选后续项（不阻塞）：re-pin 演练（上游发新版时逐条走重审触发路径）。SVG 图示已于第 5 轮落地。
