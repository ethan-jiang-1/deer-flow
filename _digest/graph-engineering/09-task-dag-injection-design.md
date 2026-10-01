---
title: "task_dag 注入设计 — 在全部运行时契约内的落地草图"
description: "把 04 的五个生长点变成可实施设计:分层架构(状态/决策/执行/门/预算)、三种交付形态、与 delta/full·回滚·压缩·流式的兼容矩阵、MVP 切片与验收判据。"
topics: [task-dag, injection, design, middleware, roadmap]
---

# 09 · task_dag 注入设计 — 在全部契约内的落地草图

> 2026-10-02 深挖成稿。前置:[04](04-extension-path.md) 的五个生长点与红线、[05](05-delegation-mechanics.md) 的机器解剖、[06](06-langgraph-capability-surface.md) 的能力面、[07](07-orchestration-surface.md) 的 API/配方、[08](08-orchestration-extension-points.md) 的入口地图。本文把它们收敛成**一个可以在 DeerFlow 现有契约内实施的设计**。

## 0. 设计原则(红线回扣,违反任何一条即回退)

1. **不现场编译新图**——元图保持两节点 + 钩子节点;不碰 `builder.add_node`;
2. **任务图是状态数据,不是拓扑**——`task_dag` 是 middleware 贡献的通道;改图 = 状态手术;
3. **不全量重排**——冻结已成功节点(reducer 终态不降级,照抄 `merge_delegations`),全局重规划预算 ≤2,耗尽转 HITL;
4. **不拆共享沙箱防线**——并行写文件的任务必须 per-node worktree,否则保留路由否决(只读/无副作用任务可并行);
5. **单写者纪律**——`replan_budget` 等无 reducer 字段只由 Gate/L2 钩子这一个写者更新。

## 1. 分层架构

```
┌─ 状态层 ─ TaskDagState 通道(TypedDict,reducer=终态不降级 merge)+ 预算通道(单写者)
├─ 决策层 ─ TaskDagMiddleware(before_model 注入 DAG 上下文 / after_model 观察结果)
│           + dag_dispatch 工具(读就绪集 → 提交执行层)
├─ 执行层 ─ 复用现有机器:durable batch submitter(持久)或 bound task tool(即时)
├─ 门层   ─ acceptance_verdict 消费者(全 SUCCESS 且验收通过 → 汇聚)
│           + interrupt_before / Command(resume)(预算耗尽 → HITL)
└─ 预算层 ─ 全局重规划计数(≤2)+ Kahn 无环校验(每次改图前)
```

## 2. 状态层(通道与 reducer)

- **贡献方式**:`AgentMiddleware.state_schema` 贡献(08 §2)——通道自动进图、进 checkpoint、经 state API 可读写、回滚/压缩保留(既有测试语义);
- **节点形态**(TypedDict,不用 Pydantic——过 checkpoint serde 与 `adapt_state_schema_for_mode`):
  `{id, title, dependencies: list[str], status: PENDING|READY|RUNNING|SUCCESS|FAILED, result_ref, retry_count, error_class?}`;
- **reducer**:照抄 `merge_delegations` 的语义骨架——append、同 id latest-wins、**终态(SUCCESS/FAILED)不可被非终态覆盖**、条目封顶;这是议题 07"冻结已成功节点"的代码级实现,DeerFlow 已有现成模板;
- **改图操作**(对应议题 07 三原子操作,本文自造词,非源码符号):INJECT_PRE_NODE(追加节点 + 接边)、SPLIT_AND_DEGRADE(替换节点为两个串行子节点)、ROLLBACK_AND_AMEND(经 accessor 变异图做通道 Overwrite 手术)——全部是**对未完成节点的状态手术**。

## 3. 决策层(middleware 钩子 + 派发工具)

- `before_model`:把 `task_dag` 的紧凑投影(节点状态 + 就绪集)注入模型请求(信噪比控制:只投影待决信息,不灌全图);
- `after_model`:观察子代理结果信封(状态/停机原因/验收判定)→ 更新对应节点状态;
- `dag_dispatch` 工具(或 wrap `task`):Kahn 计算入度=0 就绪集 → **按任务性质分流**:durable/可并行 → batch submitter;即时/顺序 → bound task;写文件类并行 → worktree 前缀或否决;
- **不新造执行引擎**——SubagentExecutor/FIFO/租约/重试预算全部复用(05 §3/§7)。

## 4. 门层与 HITL

- **验收消费者**(首个真正的 Gate):`after_model` 检查"就绪集空 ∧ 全 SUCCESS ∧ acceptance 通过"→ 写汇聚结论;任一 FAILED → 进 L2;
- **L2 预算**:`replan_budget` 单写者;每次切片前跑 Kahn 无环校验(失败拒绝改图);同类错误连续两次 → 熔断;
- **HITL**:预算耗尽 → 中间件返回 `jump_to="end"` 挂起,或编排客户端用 `interrupt_before` + `command:{resume: ...}` 原位续跑(07 R6)——**两条路径都是现成的**;
- **失败分类补齐**(信封缺的两个字段):`error_class` 推导自现有 `stop_reason` + acceptance 叶子类型(token/turn/loop → LOCAL_RETRY;tests_failed → SPLIT;file/依赖缺失 → INJECT_PRE)——**不需要新信封,是在消费者侧的映射**。

## 5. 交付形态(三选,可组合)

| 形态 | 组成 | 适用 |
|------|------|------|
| **A. Extension 包(推荐)** | ④ 注册 `middlewares`(placement:`@Prev(ClarificationMiddleware)`)+ `routers`(DAG 控制 API)+ `task_lifecycle`(观察者) | 多实例治理、发布升级、不动仓库 |
| **B. extra_middleware(SDK)** | ③ 直接注入 `create_deerflow_agent(extra_middleware=[...])` | 原型验证、单进程嵌入 |
| **C. 混合(⑥ 外部状态机)** | 通道贡献留在 ③;DAG 维护/派发/门决策由外部编排器经 state API(Overwrite 写通道)+ runs API 驱动 | 议题 03 的 outside-in 终局形态;DeerFlow 保持纯执行器 |

## 6. 兼容矩阵(与全部运行时契约的对表)

| 契约 | 兼容性 | 依据 |
|------|--------|------|
| checkpoint delta/full | ✅ 通道经 schema 适配链自动两模式;delta 下**通道手术在 head 线性替换内**不触发 fork 禁令 | 06 §3;runtime AGENTS.md |
| run 回滚 / 取消回滚 | ✅ RollbackPoint 捕获包含通道(全量物化);恢复即回到 pre-run DAG | AGENTS.md "capture preserves complete real pre-run state" |
| 上下文压缩 | ✅ 通道与 messages 无关;压缩只动 messages/summary_text | `context_compaction.py` |
| 流式/前端 | ◐ `values` 快照自动含通道;task_* 事件已有;DAG 视图需前端消费(自定义或 extension router 提供) | 07 §4 |
| 委派台账/限额 | ✅ dag 派发仍走 task/batch → 台账照记、限额照算(`max_total_per_run` 划界按 run) | 05 §2 |
| 验收/收据 | ✅ 全复用;verdict 从"证据"升格为"门输入" | 05 §6 |
| 共享沙箱 | ⚠ 唯一硬约束:并行写文件的节点必须 worktree 隔离(或否决)——设计里唯一的新增物理需求 | 05 §4 |
| 审计 | ✅ 改图 = 通道写 → checkpoint 历史 = DAG 版本史(这正是"重规划可审计"的实现) | 议题 07 对照 |

## 7. MVP 切片(每片独立可用,按序交付)

1. **S1 通道 + 台账联动**:贡献通道,`after_model` 把 delegations 信封同步成 DAG 节点状态(只读镜像)→ 立即获得"任务图可视化 + checkpoint 审计";
2. **S2 就绪集 + 派发**:`dag_dispatch` 读依赖边派发(batch 优先);写文件节点默认否决并行 → 依赖拓扑生效;
3. **S3 门 + 验收消费**:汇聚判定 + acceptance verdict 分支(FAILED → L2);
4. **S4 L2 切片 + 预算**:三原子操作 + Kahn 校验 + 预算熔断 → HITL(先 jump_to,后 interrupt/resume);
5. **S5 worktree 隔离**:并行写节点的物理隔离(唯一动沙箱层的一片)。

**验收判据**(回扣 01 地图):S1→#6 升 ◐✓(可审计);S2→#6/#7 升 ✅;S3→#8 升 ✅;S4→#11 升 ◐✓;全链→议题 09 终局的"数据图半边"在 DeerFlow 落地,而元图铁律(两节点 + 单节点变异图)全程未破。

> 与研究层的关系:本设计 = 研究层 [`harness_langgraph_ecosystem/03`](/Users/bowhead/ai_dev_sdlc_aidc/02_research/01_agent_engineering/graph_engineering/harness_langgraph_ecosystem/03-bytedance-deerflow.md) §3 注入方案的**契约内修正版**——其方向保留,五处细节已按 04 §批判性判读 重构(reducer 冻结、TypedDict、单写者、gate 用现 HITL 原语、worktree 约束)。
