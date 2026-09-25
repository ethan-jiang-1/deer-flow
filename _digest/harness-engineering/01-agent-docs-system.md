---
title: "Agent 文档体系"
description: "DeerFlow 如何为 coding agent 组织文档：分层 AGENTS.md、上下文预算强制、可执行文档测试，以及一个真实的编号漂移案例。"
topics: [agents-md, context-budget, documentation, ci]
---

# Agent 文档体系

Agent 读文档和人不同：不需要教程叙事，需要**精确契约、文件路径、不变量、测试锚点**；而且 agent 文档有自己的特有病症——**文档过长挤占 context window 并稀释指令密度**，以及**文档过期比没有更糟**（agent 会信）。DeerFlow 对这两个病各给了一个工程解。

## 1. 分层 AGENTS.md 网络（28 个文件）

> 计数口径：文件名恰为 `AGENTS.md` 的文件（v2.1.0 实测 28 个）；`backend/docs/GITHUB_AGENTS.md` 属同体系的变体命名，未计入。

```
AGENTS.md (root，14.5 KiB — 定位层：仓库地图 + 跨模块约定)
├── backend/AGENTS.md (27.8 KiB — 后端深度：harness/app 分层、中间件链、测试布局)
│   └── packages/harness/deerflow/AGENTS.md → 各子系统 AGENTS.md
│       ├── agents/middlewares/ (35.5 KiB) ├── sandbox/ (40.4 KiB)
│       ├── subagents/                     ├── mcp/
│       ├── skills/                        ├── memory/
│       ├── persistence/migrations/        ├── extensions/
│       └── tools/ tui/ tracing/ models/ config/ reflection/ runtime/ utils/
├── backend/app/{channels,gateway}/AGENTS.md
├── backend/tests/AGENTS.md          # 非常规位置：测试怎么写
├── frontend/AGENTS.md + frontend/src/AGENTS.md
└── scripts/AGENTS.md                # 非常规位置：编排脚本约定
```

> 体积口径：`check_agent_guidance.py` 用的是 **KiB**（常量写 `16 * 1024` 等），所以这里统一给 KiB。digest 早期版本用的是十进制 KB（14.9 / 28.4 / 36.3 / 41.3），与脚本口径的 14.5 / 27.8 / 35.5 / 40.4 KiB 是同一批文件的不同单位——**别拿十进制 KB 直接比 KiB 软线**：`backend/AGENTS.md` 的 28.4 KB 看着超 28，实际 27.75 KiB 仍在软线内。

写法风格是纯 agent 向的：每条 = 编号 + 触发条件 + 精确不变量 + 测试文件引用（如 `Tests: tests/test_models_authorization.py`）。测试引用是关键——给 agent 一个可执行的验证出口，而不是让它信文档。

## 2. 上下文预算强制（`scripts/check_agent_guidance.py`）

这是最"agent 特有"的设计：文档大小不是约定，是 **CI 门禁**（`.github/workflows/lint-check.yml` 两处调用）。

| 层级 | soft / hard 上限（脚本常量） | v2.1.0 实测（KiB） |
|------|------------------|----------|
| root `AGENTS.md` | 16 / 20 KiB | 14.5 KiB ✅ |
| module 层（`len(path.parts)==2`：`backend/`、`frontend/`、`scripts/`） | 28 / 32 KiB | backend 27.8 ✅、frontend 14.1 ✅、scripts 16.6 ✅ |
| local 层（子系统） | 40 / 48 KiB | 4 份超软线：`app/gateway` 42.6、`app/channels` 41.5、`runtime` 41.3、`sandbox` 40.4（均未过 hard 48）；其余 20 份在软线内 |
| 完整祖先链 | 80 / 96 KiB | 8 条链超 80 KiB（最高 `backend/.../` + `runtime` 95.9，逼近 96 硬线；`middlewares` 95.6、`sandbox` 95.0、`subagents` 94.7） |

口径要点：脚本按 `len(path.parts)==2` 判 module 层、其余非根为 local 层（所以 `backend/tests/AGENTS.md` 算 local，28/32 KiB 那档并不适用）；`>hard` 为 **error**、`>soft` 为 **warning**；两者都只在被检文件（或祖先链成员）出现在本次 diff 里时才触发——单独跑 `python scripts/check_agent_guidance.py` 却不改任何 AGENTS.md 时，输出就是"0 errors, 0 warnings"（本轮实测正是如此，尽管有 4 份超软线）。计数输出 "28 AGENTS.md" 也是脚本自报的口径。

接入点有三处：`.github/workflows/lint-check.yml:28`（PR：`--base-ref`/`--head-ref`）、`:36`（push：`--before`/`--after`）与本地 `make check-agent-guidance`（`Makefile:90-91`），CI 另加 `--github-annotations`。这套预算真的在咬人：#6 窗口有专门的 commit `#5146 reduce the size of AGENTS.md in sandbox`（`037658b0`）；v2.1.0 窗口也有 `#5761`/`#5769` 的"root AGENTS.md 精简 + 深层文档外移"——根文件在这次同步里净减 1 行（239→238），把 extensions 贡献类型的枚举压缩、并新增一行指向新的 extensions 用户手册路径。**给自己的 agent 文档做 context 预算并进 CI，这是本项目最值得抄的一条实践。**

## 3. 可执行文档测试（`backend/tests/test_middleware_documentation.py`）

文档里的代码示例直接被测试 **`exec()`**：

- `test_custom_middleware_example_uses_current_lifecycle_hooks` — 对 5 份文档（`backend/CONTRIBUTING.md` + `frontend/src/content/{en,zh}/harness/` 下的 `customization.mdx`/`middlewares.mdx`）各自 `exec()` 其中的自定义 middleware 示例，断言 API 没过期、hook 用法正确
- `test_middleware_order_includes_configured_extension_tail` — 断言文档描述的 middleware 顺序与实际链一致（含扩展尾部）
- `test_runtime_middleware_summary_includes_current_guards` — 断言运行时 guard 清单没漏

`test_middleware_documentation.py` 共 10 个测试，但**都不断言条目数**：验的是示例可执行与顺序/清单标记存在。

**文档一过期 CI 就红**。这把"保持文档同步"从美德变成了测试断言。

## 4. 残留风险：编号漂移案例（sync #6 实录）

本轮更新 digest 时发现的真实案例：`agents/middlewares/AGENTS.md` 的编号只到 **36**（v2.1.0 实测），而 digest 目录表（`_digest/internals/middleware/03-catalog.md`）按 `build_lead_runtime_middlewares()` 前 14 条 + `build_middlewares()` 后 23 条列到 **37**。两者都没错，差在**合并口径**：AGENTS.md 把 `ToolReceiptMiddleware` 与 `ToolErrorHandlingMiddleware` 合成同一条 #13（并继续把两个 `GuardrailMiddleware` 实例记作一行的 #9），digest 表则把它们拆成 #9/#14。真正的问题是**位置漂移**——新增的 `DeferredToolPromotionAuditMiddleware` 在 `lead_agent/agent.py:583-586` 实际插在 `SkillActivation`（AGENTS.md #15）与 `SkillToolPolicy`（AGENTS.md #16）之间，AGENTS.md 却没重排编号，把它排在 #25（digest 表则把它挪到 #17 并顺延其后所有编号）。所以同一个 middleware 在两份"权威"文件里编号不同，agent 按编号定位会定位到错的位置。

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
