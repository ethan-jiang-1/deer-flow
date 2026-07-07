# DeerFlow 全部 29 个 Middleware 一览

## 怎么读这张表

- **#**：在 middleware 链中的位置（也是执行顺序）
- **层**：共享基础层 = lead agent 和 sub agent 都加载；Lead-only = 仅主 agent 加载
- **Hook**：这个 middleware 覆写了哪个 hook（决定它变成哪种 node 或拦截器）
- **可选？**：✅ = 有配置开关/条件触发，可能不在链上；❌ = 始终加载
- **你常用？**：★★★★★ = 你写 agentic workflow 时几乎一定会接触到；★ = 很少直接接触

---

## 共享基础层（lead + sub agent 都加载）

| # | Middleware | Hook | 一句话 | 典型场景 | 可选？ | 你常用？ |
|---|-----------|------|--------|---------|--------|---------|
| 1 | **InputSanitizationMiddleware** | `wrap_model_call` | 转义消息中的 `<system>` 等 XML tag，防止注入 | 所有场景——排第一，给后续 middleware 提供安全的消息 | ❌ | ★★★ |
| 2 | **ToolOutputBudgetMiddleware** | `after_model` | 截断过大的 tool 输出，防止撑爆上下文 | 工具返回了大量数据（如 `cat` 了一个 10MB 文件） | ❌ | ★★★ |
| 3 | **ThreadDataMiddleware** | `before_agent` | 创建线程隔离目录（workspace/uploads/outputs） | 每个新线程启动时分配文件沙箱 | ❌ | ★★★ |
| 4 | **UploadsMiddleware** | `before_agent` | 检测新上传的文件，注入给 agent | 用户上传了 PDF/图片，agent 需要知道 | ❌ | ★★★ |
| 5 | **SandboxMiddleware** | `before_agent` | 获取 sandbox，存 `sandbox_id` 到 state | 每个线程需要执行 bash/文件操作 | ❌ | ★★★★★ |
| 6 | **DanglingToolCallMiddleware** | `after_model` | 补充缺失的 ToolMessage（用户中断导致） | 用户在 agent 执行工具时点了 stop | ❌ | ★★ |
| 7 | **LLMErrorHandlingMiddleware** | `wrap_model_call` | LLM API 出错时指数退避重试 + 断路器 | API quota 耗尽、网络抖动、服务繁忙 | ❌ | ★★★★★ |
| 8 | **GuardrailMiddleware** | `wrap_tool_call` | 工具执行前做授权检查，拒了返回 error | 限制某些 tool 只能在特定条件下调用 | ✅ `guardrails.enabled` | ★★ |
| 9 | **SandboxAuditMiddleware** | `wrap_tool_call` | 审计沙箱操作，记录安全日志 | 需要追踪谁在沙箱里执行了什么命令 | ❌ | ★★ |
| 10 | **ReadBeforeWriteMiddleware** | `wrap_tool_call` | 写文件前检查是否读过——防止盲目覆盖 | agent 想编辑一个文件但没先读它 | ✅ `read_before_write.enabled` | ★★★ |
| 11 | **ToolProgressMiddleware** | `wrap_tool_call` | 检测工具停滞（反复调用无新结果），分级警告→阻断 | agent 反复搜同一个东西、反复读同一个文件没进展 | ✅ `tool_progress.enabled` | ★★★ |
| 12 | **ToolErrorHandlingMiddleware** | `wrap_tool_call` | **核心**：捕获所有工具异常 → error ToolMessage，不崩溃 | 任何工具调用失败的兜底 | ❌ | ★★★★★ |

> 共享基础层总结：**12 个 middleware。sub agent 也加载其中大部分（通过 `build_subagent_runtime_middlewares`），所以子任务同样享有错误处理、沙箱审计等能力。**

---

## Lead-only 层（仅主 agent 加载）

| # | Middleware | Hook | 一句话 | 典型场景 | 可选？ | 你常用？ |
|---|-----------|------|--------|---------|--------|---------|
| 13 | **DynamicContextMiddleware** | `before_model` | 注入当前日期 + 可选记忆到首条 HumanMessage | 让 LLM 知道"今天是 2026-07-07"，保持 system prompt 可缓存 | ❌ | ★★★ |
| 14 | **SkillActivationMiddleware** | `before_model` | 检测 `/skill-name task` 语法，加载对应 SKILL.md | 用户输入 `/code-review 检查这个 PR` | ❌ | ★★★★ |
| 15 | **DurableContextMiddleware** | `after_model` | 从消息中提取持久上下文（子任务结果、skill 引用），防 summarization 丢数据 | 子任务完成的结果需要在多轮后仍可见 | ❌ | ★★★ |
| 16 | **SummarizationMiddleware** | `after_model` | 上下文过长时自动压缩旧消息为摘要 | 长时间对话，token 接近上限 | ✅ `summarization.enabled` | ★★★★ |
| 17 | **TodoListMiddleware** | `after_model` | Plan mode 的任务追踪，提供 `write_todos` 工具 | agent 说"这个任务分 5 步"，然后一步步执行 | ✅ `is_plan_mode` | ★★★★ |
| 18 | **TokenUsageMiddleware** | `after_model` | 记录每轮 token 消耗，子 agent 用量也归并进来 | 想看每个 run 花了多少 token、多少钱 | ✅ `token_usage.enabled` | ★★ |
| 19 | **TitleMiddleware** | `after_model` | 第一次对话后自动生成线程标题 | 聊天列表里显示"修复登录 Bug"而不是"新对话" | ❌ | ★★★ |
| 20 | **MemoryMiddleware** | `after_model` | 把对话推入记忆队列，后台异步更新用户记忆 | agent 记住"用户喜欢简洁回答" | ❌ | ★★★★ |
| 21 | **ViewImageMiddleware** | `before_model` | 把用户上传图片转 base64 注入给模型 | 用户发了一张截图问"这个错误怎么修" | 模型支持 vision 时加载 | ★★★ |
| 22 | **DeferredToolFilterMiddleware** | `before_model` | 延迟 MCP 工具 schema 加载，模型通过 `tool_search` 按需获取 | MCP server 有 100+ 个 tool，不想全塞进 prompt | ✅ `tool_search.enabled` | ★★ |
| 23 | **SystemMessageCoalescingMiddleware** | `wrap_model_call` | 合并多条 SystemMessage 为一条——兼容严格后端 | vLLM/SGLang/Anthropic 不允许非首位的 system message | ❌ | ★ |
| 24 | **SubagentLimitMiddleware** | `after_model` | 截断超量的 `task` 调用，防止并发子 agent 太多 | agent 一次调了 10 个 `task`，限制为 3 个 | ✅ `subagent_enabled` | ★★★ |
| 25 | **LoopDetectionMiddleware** | `after_model` | 检测重复工具调用模式，强制终止循环 | agent 反复调同一个 bash 命令没进展 | ✅ `loop_detection.enabled` | ★★★★ |
| 26 | **TokenBudgetMiddleware** | `after_model` | 强制 token 预算上限，超了就停 | 不想一次 run 花太多钱 | ✅ `token_budget.enabled` | ★★ |
| 27 | **Custom middlewares 槽位** | 任意 | 你的自定义 middleware 插在这里 | 你写的业务逻辑 | ✅ 传了才有 | ★★★★★ |
| 28 | **SafetyFinishReasonMiddleware** | `after_model` | 检测模型安全拦截（`finish_reason=content_filter`），阻止工具执行 | 用户输入被 LLM 的安全过滤器拦截了 | ✅ `safety_finish_reason.enabled` | ★ |
| 29 | **ClarificationMiddleware** | `after_model` | 拦截 `ask_clarification`，设 `jump_to="end"` 直接终止 | agent 需要反问用户"你指的是哪个文件？" | ❌ | ★★★★ |

---

## 按 Hook 类型归类

### `wrap_model_call`（洋葱拦截器，在 model node 内部）
1. InputSanitizationMiddleware
7. LLMErrorHandlingMiddleware
23. SystemMessageCoalescingMiddleware

### `wrap_tool_call`（洋葱拦截器，在 ToolNode 内部）
8. GuardrailMiddleware
9. SandboxAuditMiddleware
10. ReadBeforeWriteMiddleware
11. ToolProgressMiddleware
12. ToolErrorHandlingMiddleware

### `before_agent`（图启动时执行一次）
3. ThreadDataMiddleware
4. UploadsMiddleware
5. SandboxMiddleware

### `before_model`（每次 LLM 调用前执行）
13. DynamicContextMiddleware
14. SkillActivationMiddleware
21. ViewImageMiddleware
22. DeferredToolFilterMiddleware

### `after_model`（每次 LLM 调用后执行——反向顺序！）
2. ToolOutputBudgetMiddleware
6. DanglingToolCallMiddleware
15. DurableContextMiddleware
16. SummarizationMiddleware
17. TodoListMiddleware
18. TokenUsageMiddleware
19. TitleMiddleware
20. MemoryMiddleware
24. SubagentLimitMiddleware
25. LoopDetectionMiddleware
26. TokenBudgetMiddleware
28. SafetyFinishReasonMiddleware
29. ClarificationMiddleware

> **after_model 共 13 个，是最大的一类。** 因为它们都在同一个反向链上，ClarificationMiddleware（#29，最后加）最先执行，ToolOutputBudgetMiddleware（#2，最前加）最后执行。

---

## 按"你写 agentic workflow 会不会接触到"分类

### 每天都在打交道（★★★★★）
| Middleware | 为什么 |
|-----------|--------|
| SandboxMiddleware | 没有它就没有文件系统、没有 bash |
| LLMErrorHandlingMiddleware | LLM 调用不出错全靠它 |
| ToolErrorHandlingMiddleware | 工具失败不崩全靠它 |
| Custom middlewares 槽位 | 你的业务逻辑就写在这 |

### 经常感知到它的存在（★★★★）
| Middleware | 为什么 |
|-----------|--------|
| SkillActivationMiddleware | `/skill-name` 激活你的 skill |
| SummarizationMiddleware | 长对话不爆 token 全靠它 |
| TodoListMiddleware | plan mode 的任务追踪 |
| MemoryMiddleware | 记住用户偏好 |
| LoopDetectionMiddleware | agent 死循环时救你 |
| ClarificationMiddleware | agent 反问用户时触发 |

### 偶尔需要了解（★★★）
| Middleware | 为什么 |
|-----------|--------|
| InputSanitizationMiddleware | 安全基础，但一般不直接接触 |
| ToolOutputBudgetMiddleware | 工具输出被截断时你会看到 |
| ThreadDataMiddleware | 文件路径都靠它 |
| UploadsMiddleware | 用户上传文件时触发 |
| ReadBeforeWriteMiddleware | 写文件被拒时你会注意到 |
| ToolProgressMiddleware | 工具被阻断时你会看到 |
| DynamicContextMiddleware | 日期注入，一般不直接接触 |
| DurableContextMiddleware | 子任务结果持久化 |
| TitleMiddleware | 自动标题 |
| ViewImageMiddleware | 图片理解 |
| SubagentLimitMiddleware | 并发子 agent 过多时触发 |

### 很少直接接触（★★）
| Middleware | 为什么 |
|-----------|--------|
| DanglingToolCallMiddleware | 用户中断的边界情况 |
| GuardrailMiddleware | 安全审计，默认不开启 |
| SandboxAuditMiddleware | 安全日志，后台运行 |
| TokenUsageMiddleware | token 统计 |
| DeferredToolFilterMiddleware | MCP 延迟加载 |
| TokenBudgetMiddleware | 预算控制 |

### 几乎不接触（★）
| Middleware | 为什么 |
|-----------|--------|
| SystemMessageCoalescingMiddleware | 兼容层，完全透明 |
| SafetyFinishReasonMiddleware | 安全拦截，很少触发 |
