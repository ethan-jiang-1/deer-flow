---
title: "支持度地图 — 12 项三档判定"
description: "以研究层四大支柱 + 议题 09 两分 + 两层自愈为标尺,逐项判定 DeerFlow 的支持档位,附源码锚点。"
topics: [graph, dag, assessment]
---

# 01 · 支持度地图 — 12 项三档判定

> 判定标尺 = 研究层四大支柱(确定性控制面 / 物理沙箱 / 渐进装配 / 动态拓扑)+ 议题 09 的"固定元图 / 数据 DAG"两分 + 两层自愈(L1/L2)。
> 三档含义:✅ 完整支持 / ◐ 部分支持 / ❌ 缺席。逐项都给源码锚点,可回溯。
> **v2(2026-10-02 深挖修订)**:#7/#8/#9/#10/#11 五行经逐文件深读修正——修订理由见 [05](05-delegation-mechanics.md) / [06](06-langgraph-capability-surface.md),变更以 ⬆ 标注。

## 地图

| # | 研究层标尺(能力) | 档位 | 源码事实 | 锚点 |
|---|---|---|---|---|
| 1 | 固定元图(静态编译、确定性控制面) | ✅ 极小形态 | 唯一的图是 `create_agent()` 编译的 model↔tools 循环:**2 个固定节点** + 编译期展开的 middleware 钩子节点(子代理链编译出 7-8 个循环节点)。另有第二张图:`build_state_mutation_graph` 的**单 no-op 节点变异图**,复用 checkpoint 机制做整体状态替换(回滚/压缩/线性化),不派发任何节点 | [_faq_on_digested/07](../../_faq_on_digested/07_graph-nodes/answer.md) 铁律节;`agents/factory.py`;`runtime/checkpoint_state.py`;`subagents/turn_budget.py`(把编译节点数当成本模型) |
| 2 | 检查点持久化与恢复 | ✅ | langgraph-checkpoint sqlite/postgres,delta/full 双 channel mode(delta 存储 O(N));手工 compaction 与 run admission 共享同一 checkpoint 写边界;`checkpoint_patches.py` 对上游缺陷打修正补丁 | `runtime/checkpoint_state.py`;runtime AGENTS.md |
| 3 | 物理沙箱隔离 | ✅ 超配 | Local/Docker/K8s/BoxLite/E2B/Tenki/OpenSandbox 七实现;网络策略、挂载上传预算、取消语义齐备。**隔离单位 = thread**(见 #7) | `sandbox/`;[concepts/sandbox/](../concepts/sandbox/README.md) |
| 4 | 渐进式工具/技能装配 | ✅ | Skill Registry + deferred discovery + DeferredToolFilter + `skill_context` channel + `promoted` 通道(catalog-hash 作用域,防目录漂移后误暴露工具) | `skills/`;middleware catalog #25;`thread_state.py::merge_promoted` |
| 5 | L1 局部自愈(节点内微循环) | ✅ | 子代理三护栏轴:turn(`GraphRecursionError` 捕获)/ token(1M-2M 预算,0.7 预警 1.0 硬停,**剥 tool_calls 优雅收尾而非崩溃**)/ loop(重复调用检测);`consume_stop_reason` duck-type 扩展点;lead 侧 ToolErrorHandling + LoopDetection + goal continuation(默认 8 轮) | `subagents/turn_budget.py`、`token_budget.py`;middleware #5/#12 |
| 6 | **动态任务分解(Task DAG as data)** | ◐ 弱 | 分解真实存在,但以**涌现形式**活在模型上下文里:`task` 工具调用流;`todos` 扁平清单**无依赖边**;`delegations` 只是台账(同 id latest-wins、终态不降级、50 条封顶)。**没有**可校验、可切片、可重放的 task_dag 结构 | `tools/builtins/task_tool.py`;`agents/thread_state.py`;[05 §1](05-delegation-mechanics.md) |
| 7 | Fan-out 并发派发 | ◐ | `task` 后台执行(SubagentExecutor + registry + 轮询/取消/超时,持久隔离事件环 + FIFO 准入默认 3),并发上限 = SubagentLimitMiddleware,总量 = delegations 台账按 run 划界;批次走 durable batch。**子代理共享 lead 线程沙箱**(lease 生命周期 #5128,AIO 每子代理独立 shell session)——worker 级写冲突靠**路由策略硬否决**(输出依赖/状态重叠禁并行),不靠物理隔离。⬆ | [05 §1/§4](05-delegation-mechanics.md);`subagents/AGENTS.md` |
| 8 | 工件契约与验收门禁 | ◐ | **状态信封是结构化的**:`subagent_status`(5 值)+ `stop_reason`(3 值护栏分类)+ `result_brief`/`result_sha256` + token_usage + tool_receipts + receipt_verdict(引用核验)+ acceptance_verdict(确定性验收:`file:`/`tests_passed:` 对抗性 shell 匹配,不可证明即 UNVERIFIED)。缺的是 Schema 化**任务间**交付契约与门禁分支。⬆ | `subagents/status_contract.py`;`acceptance_checks.py`;`contracts/subagent_status_contract.json`;[05 §5/§6](05-delegation-mechanics.md) |
| 9 | Session 外外部状态机 | ◐ run 级 | scheduler 持久队列(queued/launching/running + lease fencing + 崩溃恢复)、MCP durable task、subagent durable batch(item 租约/重试预算/取消栅栏)。**run 级有完整事务语义**:开跑前捕获 RollbackPoint(全量状态 + pending_writes),取消回滚 / 编辑重放失败恢复 pre-run 快照。⬆ 但恢复单位仍是 run/thread,不是任务图执行位 | backend AGENTS.md scheduler 节;runtime AGENTS.md Run rollback 节;[05 §7](05-delegation-mechanics.md) |
| 10 | HITL 门禁(图级 interrupt/resume) | ◐ 原语齐备 | **`interrupt_before`/`interrupt_after` 是 Gateway API 字段**(`run_models.py:48`,支持 `["*"]`)→ worker → `agent.interrupt_before_nodes`;**`Command(resume=...)` 同样在请求路径**(`services.py:1571`)——LangGraph Platform 式 HITL 原语对**端到端可达**。⬆ 但:产品层无人调用(内置 HITL 是 `ask_clarification` → `Command(goto=END)` + `human_input` artifact,对话回合级);`interrupt()` 函数原语零处使用;resume 重新进入 model↔tools 循环,不是任务位置 | [06 §1/§2](06-langgraph-capability-surface.md);`clarification_middleware.py:516` |
| 11 | **L2 拓扑自愈(改图 / 子图切片 / 重规划预算)** | ❌ | 全库无 replan / 拓扑校验 / 切片操作。⬆ 修正表述:**失败信封不是"弱契约"**——状态信封结构化完整(见 #8),缺的是**重规划语义**:`failure_classification` 分类学与 `suggested_replanning_action` 不存在;"重规划" = lead agent 读信封后在自己的对话上下文里自发再派任务——不可审计、无预算、无熔断结构 | [05 §5](05-delegation-mechanics.md);grep `replan\|dag\|topolog` 仅命中注释 |
| 12 | 黑板状态机(全局共享状态 + 版本快照) | ❌ 有替代物 | 无跨节点黑板;全局状态 = 对话 messages + 通道(`artifacts` 去重合并、`task_notes`、`summary_text`)。隔离靠每子代理独立 checkpoint namespace + 共享线程沙箱,不是共享黑板 | `stream_subgraphs` 命名空间(#4399);`thread_state.py` |

## 源码锚点速查

| 论断 | 位置 |
|---|---|
| 两固定节点 + middleware 钩子节点;Send 仅用于节点内并行(langchain factory 内,deerflow 代码 0 处调用 Send) | `_faq_on_digested/07_graph-nodes/answer.md`(铁律节、§3.1);`langchain/agents/factory.py:1734`;grep `\bSend(` |
| 直接构建 StateGraph 的仅两处:主元图(经 create_agent)+ 单节点变异图 | `runtime/checkpoint_state.py::build_state_mutation_graph`;`agents/factory.py` |
| 图级 interrupt 原语对已暴露:`interrupt_before/after` API 字段 + `Command(resume=)` 请求路径;`interrupt()` 函数原语零处 | `app/gateway/run_models.py:48`;`services.py:1571,1725`;`worker.py:1229-1231`;grep `interrupt(` |
| `Command(goto=END)` 唯一使用:clarification 短路(带 human_input artifact) | `clarification_middleware.py:516` |
| delta 模式结构性禁 fork(worker 线性化 resume) | runtime AGENTS.md;`runtime/runs/worker.py::_linearize_delta_checkpoint_resume`(#4458) |
| 状态信封 + 台账 reducer(终态不降级) | `subagents/status_contract.py`;`thread_state.py::merge_delegations` |
| 子代理共享线程沙箱 lease + 三护栏轴 + 一次性图(checkpointer=False) | `subagents/AGENTS.md`(#5128 / Guardrail caps / Checkpointer isolation 节) |
| 全库无 dag/planner/拓扑校验/replan | `grep -ri "\bdag\b\|topolog\|replan" packages/harness/deerflow app` → 仅 middleware 注释 |
