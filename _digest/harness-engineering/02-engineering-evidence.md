---
title: "工程证据文化"
description: "DeerFlow 的契约文档、可复现实验包、基准测试与测试工程——以及它们对 coding agent 的实际价值。"
topics: [contract-docs, experiments, benchmark, testing]
---

# 工程证据文化

## 1. 契约文档（随 feature 交付，写成行为契约）

#6 窗口 docs/ 文件数 79 → 132，增量集中在**随 feature 交付的行为契约**，不是功能介绍：

| 文档 | 内容性质 |
|------|----------|
| `docs/task-continuity.md` | 存储路径、生命周期、retention 上限、回滚/分支行为、故障语义的精确契约 |
| `backend/docs/THREAD_LIFECYCLE.md` | thread 生命周期状态机 |
| `backend/docs/LOOP_DETECTION.md` | loop 检测的事件与状态契约 |
| `backend/docs/checkpoint-retention-contract.md` | checkpoint 哪些能删哪些不能删的可达性契约 |
| `docs/database-forward-revision-recovery.md` | 专门解释两个重复 0019 migration 的前向恢复 |

最后一份值得单独说：上游同时合入了两个 `0019_*` migration（版本号冲突），他们的处理是**写一篇文档解释为什么会发生、已部署库如何前向恢复**，而不是悄悄改名。对 agent 来说，这种"事故自解释"文档比十篇教程有价值。

RFC 体系（`backend/docs/rfc-*.md`）+ `docs/plans/` + `docs/pr-evidence/` 构成"设计→计划→证据"的完整链条。

## 2. 可复现实验包（诚实报告阴性结果）

`docs/experiments/task-continuity-20260912/`（50+ 文件）：完整协议、脚本、结果、对比图、验证记录。最有价值的是它的**阴性结论**：

> vector 检索 vs keyword 对比 net −5.0pp，CI [−15.0, +5.0]，McNemar p=0.625——未证明稳定收益，**所以生产实现只做 lexical 检索**。

文档明确声明"实验数字描述的是独立 replay 原型，不代表生产实现"——先划定证据边界再给结论。这种自我否定式写作对 agent 极友好：不需要反向工程"为什么不用 embedding"。

`backend/scripts/benchmark/` 有 5 个常驻基准（checkpoint / concurrency / context_snapshot / deermem_eviction / sandbox），每个带 README + 结果文件 + 发布值校验测试（如 `test_bench_deermem_eviction_published_results.py`）——**基准结果也是被测试锁定的**。

## 3. 测试工程

- **迁移级测试**：每个 migration 配一个 `test_migration_00XX_*.py`（0017-0022 六个迁移全配齐），另有持久化前向兼容测试（`test_persistence_forward_revision_compat.py`）
- **blocking_io 分离**：阻塞 I/O 测试独立成套（`make test-blocking-io`，#5105），默认套件不含——避免假阳性
- **CI 分片**：backend unit tests 并行 shards（#5137）+ `.test_durations` 时长档案
- **record/replay e2e**：外呼依赖录制回放（见 [testing/07-record-replay.md](../testing/07-record-replay.md)）
- **并发正确性实证**：OAuth 多 worker Postgres claim 用真实并发基准验证（#5026），不是只靠单测

## 4. 对 coding agent 的实际价值

1. **契约文档 = agent 的行为规范**：改 sandbox 时先读 `sandbox/AGENTS.md` + 相关 contract 文档，能直接拿到不变量清单，不需要从测试反推
2. **实验包 = 决策依据**：agent 被问到"为什么 X 不用 Y"时，答案在文档里且带统计证据
3. **测试锚点 = 验证出口**：每条契约都能落到具体测试文件，agent 修改后可立即自证
4. **事故文档 = 陷阱地图**：0019 冲突这类坑被主动写出来，agent 不会再踩

## 5. 残留差距

- 用户侧文档（README、docs site）仍是跟随式更新，入门体验与内部文档的密度差距在拉大
- 契约文档与 AGENTS.md 之间有内容重叠（如 task continuity 在 docs/ 和 AGENTS.md 双写），两处漂移风险需要人工纪律
- benchmark 结果文件里有大量生成物入库（jsonl/png），仓库噪声对 agent 检索有轻微干扰
