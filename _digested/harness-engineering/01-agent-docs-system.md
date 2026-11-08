---



title: "Agent 文档体系"
description: 'DeerFlow 如何为 coding agent 组织文档：分层 AGENTS.md、上下文预算强制、可执行文档测试，以及一个真实的编号漂移案例。'
topics: [agents-md, context-budget, documentation, ci]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# Agent 文档体系

Agent 读文档和人不同：不需要教程叙事，需要**精确契约、文件路径、不变量、测试锚点**；而且 agent 文档有自己的特有病症——**文档过长挤占 context window 并稀释指令密度**，以及**文档过期比没有更糟**（agent 会信）。DeerFlow 对这两个病各给了一个工程解。

## 1. 分层 AGENTS.md 网络（57 个文件）

> 计数口径：文件名恰为 `AGENTS.md` 的文件（v2.2.0 实测 57 个；v2.1.0 为 28 个）；`backend/docs/GITHUB_AGENTS.md` 属同体系的变体命名，未计入（计入则 58 份）。`scripts/check_agent_guidance.py` 自报的也是 57。

```
AGENTS.md (root，13.8 KiB — 定位层：仓库地图 + 跨模块约定)
├── backend/AGENTS.md (24.0 KiB — 后端深度：harness/app 分层、中间件链、测试布局)
│   └── packages/harness/deerflow/AGENTS.md (12.3 KiB) → 各子系统 AGENTS.md
│       ├── sandbox/ (45.6) ├── mcp/ (43.9) ├── subagents/ (40.2)
│       ├── agents/middlewares/ (38.5) ├── skills/ (38.4)
│       ├── agents/memory/ (37.8) ├── extensions/ (37.7)
│       ├── persistence/migrations/ (31.6) ├── runtime/ (30.7)
│       ├── models/ (26.3) ├── config/ (26.0) ├── tools/ (24.3)
│       ├── utils/ (13.3) ├── persistence/ (12.7) ├── storage/ (6.7)
│       ├── agents/ (6.3) ├── tracing/ (5.8) ├── typesafe/ (5.0)
│       ├── uploads/ (3.9) ├── agents/task_continuity/ (2.6)
│       ├── community/{aio_sandbox,e2b_sandbox,ragflow,tavily,groundroute,
│       │   opensandbox,jina_ai,brave,ddg_search,serper,infoquest,image_search}/ (0.7–8.9)
│       └── reflection/ (0.2 —— 最小的一份) ├── tui/ (8.4)
├── backend/app/{channels,gateway}/AGENTS.md (48.0 / 47.6) + gateway/routers/ (5.8)
├── backend/tests/AGENTS.md (30.0)   # 非常规位置：测试怎么写
├── backend/docs/GITHUB_AGENTS.md (20.1)  # 变体命名
├── frontend/AGENTS.md (31.6) + frontend/src/AGENTS.md (47.9)
│   └── src/{core/auth,core/memory,components/workspace/browser-view}/AGENTS.md (0.3–1.4)
├── frontend/tests/e2e/AGENTS.md (0.7)
├── scripts/AGENTS.md (32.0)         # 非常规位置：编排脚本约定
├── examples/deerflow-extension-{workflows,agent-teams,knowledge-management,
│   knowledge-platform,weknora,lightrag}/AGENTS.md (1.2–7.0)  ← v2.2.0 新增的扩展族
└── skills/public/{data-analysis,video-generation}/AGENTS.md (0.6–2.6)  ← v2.2.0 新增
```

v2.2.0 的 29 份增量几乎全部落在**新子系统**上：扩展族（`examples/deerflow-extension-*` 6 份）、社区搜索/沙箱 provider（`community/*` 12 份）、`typesafe/`、`storage/`、`uploads/`、`agents/task_continuity/`、`frontend/src/core/{auth,memory}`、`browser-view/`、两个 public skill——而不是把老文档写长。老文档反而在缩：root 14.5→13.8 KiB、backend 27.8→24.0 KiB、middlewares 35.5→38.5 KiB（唯一明显变长的老文件，因为要记 v2.2.0 新增的 3 条中间件）。

> 体积口径：`check_agent_guidance.py` 用的是 **KiB**（常量写 `16 * 1024` 等），所以这里统一给 KiB。digest 早期版本用的是十进制 KB，与脚本口径的 KiB 是同一批文件的不同单位——**别拿十进制 KB 直接比 KiB 软线**。

写法风格是纯 agent 向的：每条 = 编号 + 触发条件 + 精确不变量 + 测试文件引用（如 `Tests: tests/test_models_authorization.py`）。测试引用是关键——给 agent 一个可执行的验证出口，而不是让它信文档。

## 2. 上下文预算强制（`scripts/check_agent_guidance.py`）

这是最"agent 特有"的设计：文档大小不是约定，是 **CI 门禁**（`.github/workflows/lint-check.yml` 两处调用）。

| 层级 | soft / hard 上限（脚本常量） | v2.2.0 实测 |
|------|------------------|----------|
| root `AGENTS.md` | 16 / 20 KiB（`ROOT_SOFT`/`ROOT_HARD`，`:13`-`:14`） | 13.8 KiB ✅ |
| module 层（`len(path.parts)==2`：`backend/`、`frontend/`、`scripts/`） | 28 / 32 KiB（`MODULE_SOFT`/`MODULE_HARD`，`:15`-`:16`） | backend 24.0 ✅、frontend 31.6 ✅（离 32 只剩 362 B）、scripts 32.0 ✅（只剩 8 B） |
| local 层（子系统） | 40 / 48 KiB（`LOCAL_SOFT`/`LOCAL_HARD`，`:17`-`:18`） | **6 份超软线**：`channels` 48.0（离 48 硬线只差 4 B）、`frontend/src` 47.9、`gateway` 47.6、`sandbox` 45.6、`mcp` 43.9、`subagents` 40.2 |
| 完整祖先链（`AG002`） | 80 / 96 KiB（`CHAIN_SOFT`/`CHAIN_HARD`，`:19`-`:20`） | 按 v2.1.0→v2.2.0 diff 口径实测 **20 条链超 80 KiB**，其中 **0 条过 96 硬线**；最高 `sandbox` 98,067 B、`middlewares` 97,198 B、`migrations` 96,689 B（三者都还在 98,304 之下） |

口径要点：

- 脚本按 `len(path.parts)==2` 判 module 层、其余非根为 local 层（所以 `backend/tests/AGENTS.md` 算 local，28/32 KiB 那档并不适用）。
- `AG001` 管单文件、`AG002` 管**有效祖先链合计**——这才是真正喂给 agent 的字节数，两层分开判的目的就是不许"把预算挪到上一层"。
- 升级判据不对称：`>hard` **且相对基线有增长**才是 error；`>hard` 但没长大只报 warning；`>soft` 只在被检文件（或链成员）出现在本次 diff 里时才报 warning。（`scripts/check_agent_guidance.py:97`-`:124` 的 `_budget_finding()`）
- 因此单独跑 `python3 scripts/check_agent_guidance.py`（不带 ref）时输出就是 `57 AGENTS.md, 0 errors, 0 warnings`——**没有 diff 就没有 relevant_change，warning 全体静默**。真正在 CI 里跑的是带 ref 的形式。

接入点有三处：`.github/workflows/lint-check.yml:28`（PR：`--base-ref`/`--head-ref`）、`:36`（push：`--before`/`--after`）与本地 `make check-agent-guidance`（`Makefile:100`-`101`），CI 另加 `--github-annotations`。用 v2.2.0 自己的 diff 口径跑一遍是 **0 errors、24 warnings**（20 条 AG002 + 4 条 AG001：`channels`/`sandbox`/`mcp`/`subagents`，加 `frontend`、`frontend/src`、`scripts` 三份 module 层里超软线的两份）——**这说明这套预算在 v2.2.0 已经踩到临界**：`channels` 与 `scripts` 都只剩个位数到几百字节的余量，下一次任何实质扩写都会直接变 error 阻断合并。

这套预算真的在咬人：#6 窗口有专门的 commit `#5146 reduce the size of AGENTS.md in sandbox`（`037658b0`）；v2.1.0 窗口有 `#5761`/`#5769` 的"root AGENTS.md 精简 + 深层文档外移"；v2.2.0 窗口则把老文档继续压薄（root −0.7 KiB、backend −3.8 KiB）而把新增内容全部塞进新的 scoped 文档。`backend/tests/AGENTS.md:7`-`8` 甚至把这条规则写成了硬要求：新增 scoped `AGENTS.md` 必须在同一个 change 里更新 `test_agent_guidance_check.py` 的 `EXPECTED_GUIDANCE_PATHS`——`test_repository_has_the_approved_scoped_guidance_shape()`（`:158`-`:161`）断言工作区里**恰好**是这 56 条清单（不含变体命名的 `backend/docs/GITHUB_AGENTS.md`），**文档清单本身被测试钉住**，多写一份或漏登记都能让 CI 红。**给自己的 agent 文档做 context 预算并进 CI，这是本项目最值得抄的一条实践。**

## 3. 可执行文档测试（`backend/tests/test_middleware_documentation.py`）

文档里的代码示例直接被测试 **`exec()`**：

- `test_custom_middleware_example_uses_current_lifecycle_hooks` — 对 5 份文档（`backend/CONTRIBUTING.md` + `frontend/src/content/{en,zh}/harness/` 下的 `customization.mdx`/`middlewares.mdx`）各自 `exec()` 其中的自定义 middleware 示例，断言 API 没过期、hook 用法正确
- `test_middleware_order_includes_configured_extension_tail` — 断言文档描述的 middleware 顺序与实际链一致（含扩展尾部）
- `test_runtime_middleware_summary_includes_current_guards` — 断言运行时 guard 清单没漏

`test_middleware_documentation.py` 共 10 个测试，但**都不断言条目数**：验的是示例可执行与顺序/清单标记存在。

**文档一过期 CI 就红**。这把"保持文档同步"从美德变成了测试断言。

## 4. 残留风险：编号漂移案例

### 第一个实例：编号口径分歧（sync #6 / v2.1.0 实录）

`agents/middlewares/AGENTS.md` 的编号在 v2.1.0 只到 **36**，而 digest 目录表（`_digested/internals/middleware/03-catalog.md`）按 `build_lead_runtime_middlewares()` 前 14 条 + `build_middlewares()` 后 23 条列到 **37**。两者都没错，差在**合并口径**：AGENTS.md 把 `ToolReceiptMiddleware` 与 `ToolErrorHandlingMiddleware` 合成同一条 #15（v2.1.0 是 #13），并把两个 `GuardrailMiddleware` 实例记作一行的 #11（v2.1.0 #9）。真正的问题是**位置漂移**——`DeferredToolPromotionAuditMiddleware` 在 `lead_agent/agent.py` 里紧跟 `SkillActivationMiddleware` 之后 `append`（v2.1.0 `:583`-`586`，v2.2.0 `:603`），AGENTS.md 却没重排编号，把它排在 #27（v2.1.0 #25）。所以同一个 middleware 在两份"权威"文件里编号不同，agent 按编号定位会定位到错的位置。

### v2.2.0 更新：条目涨到 39，合并口径不变

v2.2.0 的 `middlewares/AGENTS.md` 编号到 **39**（`AGENTS.md:60`-`176`，`39. **ClarificationMiddleware**` 在 `:176`），v2.1.0 是 36。**合并口径没有变**——`#11` 仍是"至多两个 Guardrail 实例一行"、`#15` 仍是"`ToolReceiptMiddleware + ToolErrorHandlingMiddleware` 一行"，所以编号 ≠ 链上实例数。相对 v2.1.0 的净增 3 条来自三处新增：`KnowledgeScopeMiddleware`（排第 2，紧跟 `InputSanitization`；这条**在 `_build_runtime_middlewares` 内部**，不是 lead-only）、`PiiRedactionMiddleware`（`pii_redaction.enabled`，#3190）、`ArtifactCaptureMiddleware`；同时删掉了 `skill_tool_policy_middleware.py`（已删除，−529 行，#6935）与 `skills/tool_policy.py`（已删除）。**编号漂移问题没被修好，只是分母大了**：`DeferredToolPromotionAuditMiddleware` 依然排在 #27 而实际位置在 #18 `SkillActivation` 之后。

**为什么现有防护没拦住**：可执行测试（`test_middleware_documentation.py`，10 个测试）验证的是"示例代码能跑"和"顺序/清单标记存在"，不验证"编号连续性"或"条目数"；预算检查验证的是"大小"，不验证"正确性"。AGENTS.md 与代码的中间地带（编号、条目合并口径）仍是真空。

**给 agent 的操作准则**（也是本 digest 各文件遵循的）：**当 AGENTS.md 与代码冲突时，信代码，并以测试文件为仲裁**。读 AGENTS.md 拿地图，读代码拿事实。

### 第二个实例：行号漂移（sync #7 / v2.1.0 实录）

v2.1.0 窗口对根 `AGENTS.md` 只做了两处编辑（压缩 extensions 贡献类型枚举 + 新增一行用户手册路径），净减 1 行 —— 但**其后所有行号整体 -1**：digest 里引用的 `L221`（Documentation update policy）变成 `L220`，`L227-228`（format 检查）变成 `L226-227`；同一轮 `#5535` 也让 `runtime/AGENTS.md` 涨了 13 行。

**行号引用和编号引用一样脆**。本 digest 的应对是：引用 AGENTS.md 时同时给出**内容锚点**（引文原文/小节名）与行号，行号只作辅助；校验时先在目标版本里 grep 引文，再核对行号。凡是只写 `AGENTS.md Lxxx` 而没有引文的引用，下一轮同步必然要重新定位。

## 5. 值得抄的清单

1. 分层 AGENTS.md + root 只做定位不做细节（渐进式上下文加载）
2. agent 文档 context 预算 + CI 门禁（soft/hard 两档）
3. 文档示例进测试夹具（exec + 断言行为）
4. 每条契约附测试文件引用（给 agent 验证出口）
5. 子系统深度文档（middleware/sandbox 的 AGENTS.md 达到"可独立重建该子系统心智模型"的密度）
