---


title: "public skills 目录：23 个内置技能包的地图"
description: '把 skills/public/ 下 23 个已提交技能包按职责逐行编目，给出入口、测试与相关机制页，供选型、复用和二次开发时快速定位。'
type: deep-dive
topics: [skills, public-skills, skill-packages, catalog]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# public skills 目录：23 个内置技能包的地图

> **定位**：`skills/public/` 下 23 个已提交技能包的目录，回答「哪个包负责什么、入口在哪、有没有测试、机制细节去哪看」。
> **边界**：不替代 [README](README.md) 对 SKILL.md 契约、双加载、存储/投影与审查链的机制说明；不覆盖 `skills/custom/`（gitignored）和 `.deer-flow/integrations/skills/{provider}/` 托管集成包。包摄入与 SkillScan 见 [skill-package-intake.md](skill-package-intake.md)，review core 见 [skill-review-core.md](skill-review-core.md)。

## 23 个包

> 每个包都以 `SKILL.md` 为入口，表内再补该包的脚本与资源。「测试」列未带 `backend/` 前缀的文件均在仓库根 `tests/skills/`。

| 包 | 职责一句话 | 入口（SKILL.md / scripts） | 有测试？ | 相关机制页 |
|---|---|---|---|---|
| `academic-paper-review` | 单篇论文的结构化同行评审：方法、贡献、定位与可执行修改建议 | `SKILL.md` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `bootstrap` | 通过一次引导对话创建或更新个性化 `SOUL.md` | `SKILL.md`；`references/conversation-guide.md`、`templates/SOUL.template.md` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `chart-visualization` | 26 种图表选型 + 参数提取，Node 脚本出图 | `SKILL.md`；`scripts/generate.js`、`references/*.md` | 有 · `test_chart_visualization.py` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `claude-to-deerflow` | 用 HTTP API 驱动远端 DeerFlow：会话、状态、记忆、上传 | `SKILL.md`；`scripts/chat.sh`、`scripts/status.sh` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `code-documentation` | 生成 README、API 参考、架构文档与 changelog | `SKILL.md` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `consulting-analysis` | 两阶段咨询报告：分析框架 → 数据到位后的成稿 | `SKILL.md` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `data-analysis` | 用 DuckDB 查询 Excel/CSV，导出 CSV/JSON/Markdown | `SKILL.md`；`scripts/analyze.py` | 有 · 5 个 `test_data_analysis_*.py` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `deep-research` | 多角度网络研究方法论，替代单次 WebSearch | `SKILL.md` | 无 | [web_search](../community-tools/01-web-search.md) |
| `find-skills` | 搜索并安装开放生态里的 agent skills | `SKILL.md`；`scripts/install-skill.sh` | 无 | [包摄入](skill-package-intake.md) |
| `frontend-design` | 产出有设计感、避免通用「AI 味」的前端界面 | `SKILL.md`；`LICENSE.txt` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `github-deep-research` | 多轮 GitHub 仓库深研，输出带 Mermaid 的 Markdown 报告 | `SKILL.md`；`scripts/github_api.py`、`assets/report_template.md` | 有 · 2 个 `test_github_*.py` | [web_fetch](../community-tools/02-web-fetch.md) |
| `image-generation` | 结构化 prompt + 参考图生成图片 | `SKILL.md`；`skills/public/image-generation/scripts/generate.py`、`templates/` | 有 · `test_image_generation.py` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `music-generation` | 调 MiniMax 生成歌曲/配乐（可带歌词） | `SKILL.md`；`skills/public/music-generation/scripts/generate.py` | 有 · `test_music_generation.py` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `newsletter-generation` | 策展多源内容 + 原创评论，产出 newsletter | `SKILL.md` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `podcast-generation` | 文本转双主持对话并合成播客音频 | `SKILL.md`；`skills/public/podcast-generation/scripts/generate.py`、`templates/tech-explainer.md` | 有 · 2 个 `test_podcast_*.py` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `ppt-generation` | 逐页生成图片并组装 PPTX | `SKILL.md`；`skills/public/ppt-generation/scripts/generate.py` | 有 · 2 个 `test_ppt_*.py` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `skill-creator` | 创建/改进/评测/打包 skill，含 description 优化与 benchmark | `SKILL.md`；`scripts/`（9 个）、`references/`、`agents/`、`eval-viewer/` | 有 · 3 个 `test_skill_creator_*.py`；backend `test_skill_creator_quick_validate.py` | [review core](skill-review-core.md)、[摄入](skill-package-intake.md) |
| `skill-reviewer` | 只读评审 skill 包的 readiness、触发、安全、资源与证据 | `SKILL.md`；`references/`、`evals/evals.json` | 有 · `backend/tests/test_skill_reviewer_public_skill.py` + evals | [review core](skill-review-core.md) |
| `surprise-me` | 动态发现并组合其它 enabled skill，制造「惊喜」体验 | `SKILL.md` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `systematic-literature-review` | 跨多篇论文的 arXiv 系统综述（APA/IEEE/BibTeX） | `SKILL.md`；`scripts/arxiv_search.py`、`templates/`、`evals/` | 无脚本测试；`evals/` 2 个 JSON | [review core](skill-review-core.md) |
| `vercel-deploy` | 打包并部署到 Vercel，返回 preview 与 claim URL | `SKILL.md`；`scripts/deploy.sh` | 有 · `backend/tests/test_skills_bundled.py::test_vercel_deploy_commands_use_the_mounted_script_path` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `video-generation` | 结构化 prompt / 参考图生成视频 | `SKILL.md`；`skills/public/video-generation/scripts/generate.py` | 有 · 3 个 `test_video_*.py` | [SKILL.md 契约](skill-md-and-tool-assembly.md) |
| `web-design-guidelines` | 抓取最新 Web Interface Guidelines 并审查 UI 代码 | `SKILL.md` | 无 | [SKILL.md 契约](skill-md-and-tool-assembly.md) |

> 所有 23 包的 frontmatter 都由 `backend/tests/test_skills_bundled.py` 参数化校验（含 name 必须等于目录名）；表中「无」指没有专属脚本/评测测试，不等于没有加载面校验。

## 阅读路径

1. **先看**：[README](README.md) — 先把 SKILL.md 契约、legacy/deferred 双加载、`/skill-name` 激活与存储/投影机制过一遍，再决定读哪个包。
2. **再看**：按需求从主表挑 1–2 个包，读其 `SKILL.md` frontmatter 的 `description` 判断触发边界；研究类看 `deep-research` / `github-deep-research`，生成类看 `image-generation` / `podcast-generation`，工程类看 `skill-creator` / `skill-reviewer`。
3. **深入**：动手改脚本前对照 `tests/skills/` 的离线用例（`skill_loader.py` 按路径加载 `generate.py`、mock `requests`）；要做包级质量门禁则进 [skill-review-core.md](skill-review-core.md) 与 [skill-package-intake.md](skill-package-intake.md)。

## 相关目录

- [concepts/skills-tools/](README.md) — 本目录：SKILL.md、摄入/扫描与 review core 的机制页。
- [builtin-tools/](../builtin-tools/README.md) — 28 个内置 tool 的装配与条件加载，和 skill 的 `allowed-tools` 元数据相邻。
- [community-tools/](../community-tools/README.md) — `web_search` / `web_fetch` / 知识库等 provider，研究类 skill 的底层工具面。
- [internals/mcp/](../../internals/mcp/README.md) — MCP 工具目录与 deferred 提升，决定 skill 能看到哪些工具。
- [testing/05](../../testing/05-testing-skills-and-workflows.md) — 怎么测 skill 加载、脚本与 agent workflow。
- [skills/public/](../../../skills/public/) — 23 个包的源码与各自资源文件。
