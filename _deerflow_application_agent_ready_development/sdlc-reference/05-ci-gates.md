# CI 门禁矩阵

## 什么时候读这里

判断"这条规则是真的会被机器挡住，还是只写在指南里"：逐个 workflow 数 DeerFlow 主仓 v2.1.0 实际执行的门禁、触发条件与例外。应用仓抄 CI 前先抄这张表的**结构**——门禁要写清触发路径与跳过条件，不能只写"有 CI"。

## 主仓机制（全部为机器门禁，对 workflow 源核验）

| 门禁 | 机器行为 | 触发 | 例外 |
|---|---|---|---|
| Lint | backend `make lint`（ruff check + format check）+ `uv lock --check`；frontend format/lint/typecheck/build | push 与全部 PR | 无 draft 跳过 |
| 指南预算 | `scripts/check_agent_guidance.py` 按 diff 基线检查 AGENTS.md 尺寸预算 | push 与全部 PR | 无 |
| 后端单测 | 默认离线套件按真实时长分 **4 片**并行（fail-fast 关闭），Postgres/Redis 作为 service 容器；另有一个 job 按文档贡献者路径安装后仅做 `--collect-only`，证明最小安装也能收集全套 | 非 draft PR | **draft PR 跳过** |
| blocking-I/O | `make test-blocking-io` 严格阻塞检测 | 仅 `backend/**` 路径变更 | draft 跳过 |
| 前端 E2E | Playwright | 仅 `frontend/**` 路径变更 | draft 跳过 |
| replay E2E | 前后端契约两层回放：backend golden SSE 序列 + 真前端渲染回放 | **契约两侧任一变更触发**（frontend / Gateway / harness / 回放夹具） | draft 跳过 |
| skill 审查 | SkillScan 确定性审查 + 豁免清单校验 | 仅技能相关路径变更 | draft 跳过 |
| 版本门 | tag 上校验版本五源一致，失败跳过全部发布 | 仅 `v*` tag | 见[发版与版本门](./07-release-and-version-gate.md) |

来源：[backend-unit-tests.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/backend-unit-tests.yml)、[lint-check.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/lint-check.yml)、[backend-blocking-io-tests.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/backend-blocking-io-tests.yml)、[e2e-tests.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/e2e-tests.yml)、[replay-e2e.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/replay-e2e.yml)。

**容易被忽略的设计**：

1. **replay E2E 的双端触发**——workflow 头注释写明动机："Triggered by changes on EITHER side of the contract so a backend change can no longer pass without the frontend-facing checks running."契约的门禁必须让契约的**双方**都触发它。
2. **分片按真实时长**——用 `.test_durations` 基线平衡分片，每个测试恰好跑一次；fail-fast 关掉，失败分片报告自己的测试而不连坐同伴。
3. **最小安装收集 job**——证明"按文档装依赖"的路径不坏，防止 optional 依赖悄悄变成必需。

**边界（诚实读法）**：① "每 PR 跑全部门"不成立——多个门按路径分流，跨边界改动是否触发对应门禁要评审者自行判断；② draft PR 跳过主测试 job，标 ready 时才补跑；③ `make test-live` 从不进 CI；④ 分支保护把哪些 workflow 设为 required 在仓库文件里**不可见**——本表只回答"什么会跑"，不回答"什么挡住合并"。

## 应用仓适用边界

**可移用**：路径分流本身（省 CI 时间）+ "契约双端触发"原则 + 分片思路。**必须自建**：你的 required checks 清单要显式写进仓库设置并记录在案（这正是主仓"仓库外不可核实"给应用仓的教训——别让同样的问题在你这里也查不到）。**应用仓建议**：应用仓的契约面通常是"你的包 ↔ DeerFlow 契约版本"——升级契约版本区间的 PR 应当触发你的全量包测试，等价于主仓的双端触发。

## 证据入口

上表八个 workflow 文件（全部钉 v2.1.0；CONTRIBUTING 的 PR Regression Checks 节是这些 workflow 的文档面）。
