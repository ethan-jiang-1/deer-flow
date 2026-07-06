# DeerFlow 逻辑结构图

> 从概念层面展示 DeerFlow 的核心抽象和它们之间的关系。不涉及物理部署，只看"是什么、怎么连"。

---

## 总览：四层同心圆

```
                        ┌──────────────────────────────┐
                        │         Access Layer          │
                        │  Web UI · HTTP API · IM Ch    │
                        │  Python SDK (DeerFlowClient)  │
                        ├──────────────────────────────┤
                        │       Gateway (app.*)         │
                        │  REST routers · Auth · CSRF   │
                        │  LangGraph-compatible runtime │
                        │  IM Channel Service           │
                        ├──────────────────────────────┤
                        │    Harness (deerflow.*)       │
                        │  ┌─────────────────────────┐ │
                        │  │   Agent Graph (LangGraph)│ │
                        │  │   Middleware Chain (19)  │ │
                        │  │   Tools · Skills · MCP   │ │
                        │  │   Sandbox · Subagents    │ │
                        │  │   Memory · Tracing       │ │
                        │  └─────────────────────────┘ │
                        ├──────────────────────────────┤
                        │      Core Infrastructure      │
                        │  Checkpointer · RunManager    │
                        │  StreamBridge · Persistence   │
                        │  Model Factory · Config       │
                        └──────────────────────────────┘
```

---

## Agent Loop 核心循环

```
        ┌──────────────────────────────────────────────┐
        │              Agent Loop (per turn)            │
        │                                              │
        │  System Prompt                               │
        │  ┌──────────────────────────────────────┐    │
        │  │ <memory>  <available_skills>          │    │
        │  │ <available-deferred-tools>  SOUL.md   │    │
        │  │ <thread_data>  <uploaded_files>       │    │
        │  └──────────────────────────────────────┘    │
        │         │                                     │
        │         ▼                                     │
        │  ┌─────────────┐                             │
        │  │  LLM Call   │ ← thinking / vision /       │
        │  │  (model)    │   reasoning_effort           │
        │  └──────┬──────┘                             │
        │         │                                     │
        │    ┌────▼────┐                               │
        │    │ Tool    │  bash · read_file · write_file │
        │    │ Calls   │  ls · glob · grep · str_replace│
        │    │         │  task(subagent) · tool_search  │
        │    │         │  present_files · ask_clarify   │
        │    │         │  MCP tools · Community tools   │
        │    └────┬────┘                               │
        │         │                                     │
        │    ┌────▼────┐                               │
        │    │ Results │  ToolMessage → next LLM call   │
        │    └────┬────┘  或 END（无更多 tool calls）    │
        │         │                                     │
        │         ▼                                     │
        │   继续循环 或 结束 turn                        │
        └──────────────────────────────────────────────┘
```

---

## Middleware Chain（19 个中间件，按执行序）

```
每个 turn 的 LLM 调用和 Tool 执行被以下中间件包裹：

 1. ThreadDataMiddleware      — 创建 per-thread 目录
 2. UploadsMiddleware          — 追踪已上传文件
 3. SandboxMiddleware          — 获取/释放沙箱
 4. DanglingToolCallMiddleware — 补丁缺失的 ToolMessage
 5. LLMErrorHandlingMiddleware — 规范化 LLM 错误
 6. GuardrailMiddleware        — pre-tool-call 鉴权（可选）
 7. SandboxAuditMiddleware     — 安全审计日志
 8. ToolErrorHandlingMiddleware— 工具异常→ToolMessage
 9. SummarizationMiddleware    — 上下文压缩（可选）
10. TodoListMiddleware         — write_todos 任务跟踪（plan_mode）
11. TokenUsageMiddleware       — token 统计（可选）
12. TitleMiddleware            — 自动生成会话标题
13. MemoryMiddleware           — 排队异步更新记忆
14. ViewImageMiddleware        — vision 图片 base64 注入（可选）
15. DeferredToolFilterMdlwr    — MCP 工具延迟发现（可选）
16. SubagentLimitMiddleware    — 限制并行子 agent 数（可选）
17. LoopDetectionMiddleware    — 检测 tool-call 死循环
18. SafetyFinishReasonMdlwr    — 安全终止处理（可选）
19. ClarificationMiddleware    — 拦截 ask_clarification→interrupt（必须最后）

6 个 Hook 点：before_model → LLM → after_model → Tool Execute → after_tool → after_step
```

---

## Skills 加载与选择链

```
skills/{public,custom}/**/SKILL.md
        │
        ▼
LocalSkillStorage.load_skills()
  → os.walk() 扫描目录
  → parse_skill_file() 解析 YAML frontmatter
  → 过滤 enabled_only（来自 extensions_config.json）
        │
        ▼
get_skills_prompt_section()
  → 全量平铺 name + description → <available_skills> XML 块
  → 注入系统 prompt
        │
        ▼
LLM 自主判断 → read_file(SKILL.md) → 遵循指令
```

---

## Sub-agent 委派模型

```
Lead Agent
    │
    │  task("code-reviewer", "审查 X 文件")
    ▼
SubagentExecutor
    │
    ├─ 双线程池: _scheduler_pool (3) + _execution_pool (3)
    ├─ MAX_CONCURRENT_SUBAGENTS = 3
    ├─ 超时: 15 分钟
    │
    ├─→ Subagent 1 (独立 agent graph)
    ├─→ Subagent 2 (独立 agent graph)    ← 并行执行
    └─→ Subagent 3 (独立 agent graph)
    │
    ▼
结果聚合 → Lead Agent 下一 turn
```

---

## Sandbox 虚拟路径系统

```
Agent 看到的（虚拟）              宿主机实际路径
──────────────────────────      ──────────────────────────────────
/mnt/user-data/workspace/   →   {base}/users/{uid}/threads/{tid}/user-data/workspace/
/mnt/user-data/uploads/     →   {base}/users/{uid}/threads/{tid}/user-data/uploads/
/mnt/user-data/outputs/     →   {base}/users/{uid}/threads/{tid}/user-data/outputs/
/mnt/skills/ (只读)         →   {project}/skills/
/mnt/acp-workspace/ (只读)  →   {base}/users/{uid}/threads/{tid}/acp-workspace/
自定义 mounts               →   宿主机任意目录（config.yaml 配置）

安全层：
  validate_local_tool_path()  →  路径白名单（4 个前缀）
  _reject_path_traversal()    →  拒绝 ..
  mask_local_paths_in_output()→  脱敏宿主机路径
```

---

## Memory 系统

```
对话消息
    │
    ▼
MemoryMiddleware (过滤: 用户输入 + 最终 AI 回复)
    │
    ▼
MemoryQueue (debounce 30s, per-thread 去重)
    │
    ▼
MemoryUpdater (LLM-based 提取)
    │  提取: workContext, personalContext, topOfMind
    │  提取: facts (preference/knowledge/context/behavior/goal)
    │  去重: whitespace-normalized fact content
    │
    ▼
memory.json (原子写入: temp file + rename)
    │
    ▼
下一 turn 系统 prompt 注入 <memory> 块 (top 15 facts, max 2000 tokens)
```

---

## 关键源码索引

| 概念 | 源码 |
|------|------|
| Agent 创建入口 | `deerflow/agents/lead_agent/agent.py:make_lead_agent()` |
| Agent 循环 | `deerflow/agents/lead_agent/agent.py:_make_lead_agent()` |
| Middleware 组装 | `deerflow/agents/middlewares/tool_error_handling_middleware.py:_build_runtime_middlewares()` |
| Skills 加载 | `deerflow/skills/storage/local_skill_storage.py:load_skills()` |
| 工具组装 | `deerflow/tools/tools.py:get_available_tools()` |
| Sandbox 接口 | `deerflow/sandbox/sandbox.py:Sandbox` |
| Subagent 执行 | `deerflow/subagents/executor.py:SubagentExecutor` |
| Memory 更新 | `deerflow/agents/memory/updater.py` |
| ThreadState | `deerflow/agents/thread_state.py:ThreadState` |
| 系统 prompt | `deerflow/agents/lead_agent/prompt.py:apply_prompt_template()` |
