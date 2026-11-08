# Part B：搭建第一个 Agent Flow

DeerFlow 没有可视化 DAG 编辑器。"Agent Flow" 通过 **四个层次** 来定义，从轻到重：

```
Skills (SKILL.md)          ← 最轻量：Markdown 里的行为指令，agent 读取并遵循
    ↓
自定义 Agent (SOUL.md + config.yaml)  ← 中等：固定人格 + 工具权限 + 模型绑定
    ↓
Sub-agent 委派 (config.yaml subagents) ← 高级：父 agent 把任务发给专用子 agent 并行执行
    ↓
MCP 工具扩展 (extensions_config.json)  ← 插件：连接外部工具服务器增加能力
```

四个层次可以组合使用。

## B.1 Skills — 最轻量，推荐入门

Skill 就是一个 Markdown 文件，告诉 agent "遇到某类任务时应该怎么做"。没有可执行代码——它就是一段会被注入系统 prompt 的指令文本。

**创建你的第一个 Skill**：

```bash
mkdir -p skills/custom/my-first-skill
```

`skills/custom/my-first-skill/SKILL.md`：

```markdown
---
name: my-first-skill
description: >-
  代码分析助手：读取代码文件，输出结构化 review 报告。
---

# 代码分析助手

当用户要求分析代码时，按以下步骤执行：

## 流程

1. 用 `read_file` 读取目标文件
2. 从以下维度分析：
   - 正确性：是否有明显的 bug 或逻辑错误？
   - 性能：是否有不必要的循环、重复 IO、大对象创建？
   - 安全：是否有命令注入、路径遍历、密钥泄露风险？
   - 可读性：命名是否清晰？函数是否过长？
3. 将分析结果写入 `/mnt/user-data/outputs/code-review.md`
4. 调用 `present_files` 把输出文件路径暴露给用户

## 输出格式

```markdown
# Code Review: {文件名}

## 必须修复
...

## 建议优化
...

## 安全问题
...
```
```

> 🔄 同步 #8（v2.2.0）：原示例 frontmatter 里的 `allowed-tools: [read_file, bash, write_file]` 在这里**删掉**了。v2.2.0（上游 #6935，commit `0d73798be`）把 `allowed-tools` 降级为**兼容元数据**：仍会解析、校验、展示（`describe_skill` 输出前缀 `Allowed tools (compatibility metadata, not enforced):`），也会进 skill catalog 指纹，但**从不**授予或收窄工具集。原来的强制逻辑所在文件已删除（v2.1.0 的 `skills/tool_policy.py` 已删除、`agents/middlewares/skill_tool_policy_middleware.py` 已删除）。要限制工具请走 `authorization`（Layer 1 能力过滤 + Layer 2 `GuardrailAuthorizationAdapter`）、`disallowed_tools`，或自定义 agent 的 `tool_groups`。详见 `_digested/concepts/skills-tools/skill-md-and-tool-assembly.md`。

**启用 Skill**：

在 Web 界面 Settings → Skills 中找到 `my-first-skill`，点启用。或者直接编辑 `extensions_config.json`：

```json
{
  "skills": {
    "my-first-skill": { "enabled": true }
  }
}
```

**使用**：

在聊天中输入 "帮我审查 backend/app/gateway/app.py"，agent 会：
1. 在系统 prompt 的 `<available_skills>` 块中看到你的 skill
2. 判断这个 skill 与当前任务相关
3. 调用 `read_file` 读取 SKILL.md 的内容
4. 遵循其中的步骤指令执行

> Skill 选择机制是纯 LLM 驱动的，所有 enabled skill 的 name+description 会平铺注入系统 prompt。当 skill 数量超过 50 时选择精度会下降。详见 `_faq_on_digested/01_skill-selection-accuracy/`。精确选择方案见 `_faq_on_digested/03_precise-skill-selection/`。

## B.2 自定义 Agent — 固定人格 + 工具权限

每个 Agent 有独立的 `SOUL.md`（人格/价值观/行为规范）和 `config.yaml`（模型绑定/工具白名单/Skill 白名单）。

Agent 数据存放在 `.deer-flow/users/{user_id}/agents/{name}/`，可通过 Web 界面 Agent 管理页创建，也可以手动创建：

```bash
mkdir -p .deer-flow/users/default/agents/code-reviewer
```

`.deer-flow/users/default/agents/code-reviewer/SOUL.md`：

```markdown
# Code Reviewer

你是一个资深代码审查专家。你的原则：

1. **先理解，再判断** — 绝不猜测代码意图，必要时要求澄清
2. **具体 > 笼统** — "第 42 行有 SQL 注入风险" 优于 "存在安全问题"
3. **分级输出** — 🔴 必须修复 / 🟡 建议优化 / 🟢 参考建议
4. **给出修复代码** — 不只指出问题，还要给出修改后的代码
5. **控制范围** — 只审查用户指定的文件或目录，不蔓延
```

`.deer-flow/users/default/agents/code-reviewer/config.yaml`：

```yaml
name: code-reviewer
description: 专业代码审查 agent
model: deepseek-v3
tool_groups:
  - file:read
  - file:write
  - bash
skills:
  - my-first-skill
```

在 Python 中使用：

```python
from deerflow.client import DeerFlowClient

# 指定 agent_name，DeerFlow 会自动加载对应 SOUL.md 和 config.yaml
client = DeerFlowClient(agent_name="code-reviewer")

# 这个对话中，agent 的人格、工具集、skill 白名单都由上面的配置决定
reply = client.chat("审查 deerflow/sandbox/tools.py", thread_id="review-1")
print(reply)
```

在 HTTP Gateway 中使用：

```bash
curl -X POST http://localhost:2026/api/threads/review-2/runs/stream \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "messages": [{"role": "user", "content": "审查 sandbox/tools.py"}]
    },
    "context": {"agent_name": "code-reviewer"}
  }'
```

> Agent 配置加载见 `deerflow/config/agents_config.py:332`（`load_agent_config`），SOUL.md 注入系统 prompt 见 `deerflow/agents/lead_agent/prompt.py:1029`（`get_agent_soul()`，渲染为 `<soul>` 块）。
>
> 🔄 同步 #6（v2.1.0-rc0）：原引用 `agents_config.py:80-126`、`prompt.py:659-664` 已漂移，符号仍在，行号按当前源码更新。

> 🔄 同步 #8（v2.2.0）：**上面那段 `config.yaml` 改了**。v2.2.0 的 `AgentConfig`（`deerflow/config/agents_config.py:206`）里**没有 `tools:` 字段**——逐工具白名单请改用 `tool_groups`（`:211`）。它的其它字段是 `display_name` / `description` / `model` / `tool_groups` / `skills`（`:222`，注释原文：「`allowed-tools` is compatibility metadata only and never restricts tools」）/ `mcp_plugins`（`:225`，`None` = 继承全部，`[]` = 一个都不给）/ `knowledge_scope`（`:229`）/ `allowed_subagents`（`:233`，`None` = 全部，`[]` = 无）/ `model_settings` / `thinking_enabled` 等。可用的 `tool_groups` 在 `config.example.yaml:831` 起的 `tool_groups:` 段里定义（内置 `web` / `file:read` / `file:write` / `bash` / `browser` / `knowledge`）。
>
> 另外两点：① HTTP 那条路径要先开 `agents_api.enabled: true`（默认 `false`，`config.example.yaml:2580`），否则 agent 管理路由一律 403——不过 `context.agent_name` 走 run 端点不受这个开关限制，开关只挡住「通过 HTTP 管理 SOUL.md/USER.md」；② `load_agent_config` 现在会经 `deerflow.persistence.agents.get_agent_store()` 读，文件后端**先读 per-user 目录、再回落 legacy 顶层 `agents/`**（legacy 只读）。

## B.3 Sub-agent 委派 — 并行多 agent 协作

在 `config.yaml` 中注册子 agent，Lead Agent 可以通过 `task()` 工具把任务分发给它们并行执行：

```yaml
# config.yaml（config.example.yaml 里 subagents: 整段默认是注释状态）
subagents:
  custom_agents:
    code-reviewer:
      description: 审查代码，输出结构化 review
      model: deepseek-v3
      tools: [read_file, write_file, bash, ls, str_replace, present_files]
      skills: [my-first-skill]

    test-writer:
      description: 为指定的 Python 文件生成 pytest 单元测试
      model: deepseek-v3
      tools: [read_file, write_file, bash, ls]
```

> 🔄 同步 #8（v2.2.0）：注意这里的 `tools:` **仍然有效**——sub-agent 用的是另一套结构 `CustomSubagentConfig`（`deerflow/config/subagents_config.py:124`），它的 `tools` 是真正的工具白名单（`None` = 继承父级全部），和自定义 agent 的 `tool_groups` 不是一回事，别混。同时 `subagents.enabled` 总开关**已删除**，写了也不生效；启用委派仍靠请求侧 `subagent_enabled`。

使用示例：

```python
client = DeerFlowClient(subagent_enabled=True)

result = client.chat(
    "帮我做三件事：\n"
    "1. 审查 deerflow/sandbox/tools.py\n"
    "2. 审查 deerflow/models/factory.py\n"
    "3. 为这两个文件生成单元测试",
    thread_id="multi-task-1"
)
```

执行流程：

```
User Message
    │
    ▼
Lead Agent（plan_mode = 拆解为 todo items）
    │
    ├─→ task("code-reviewer", "审查 sandbox/tools.py")   ┐
    ├─→ task("code-reviewer", "审查 models/factory.py")  │ 默认 3 个并发
    └─→ task("test-writer", "为 tools.py 写测试")        ┘
    │
    ▼
Lead Agent 汇总子 agent 结果 → 生成最终回复
```

> 子 agent 执行引擎见 `deerflow/subagents/executor.py:890`（`SubagentExecutor`），并发上限 `MAX_CONCURRENT_SUBAGENTS = 3`（`executor.py:2337`），内置 sub-agent 默认超时 **30 分钟**（`subagents.timeout_seconds` 默认 1800，`deerflow/config/subagents_config.py:171`）。

> 🔄 同步 #8（v2.2.0）：原文写「超时 15 分钟」——**默认值已是 1800 秒**。自定义 sub-agent 的 `timeout_seconds` 默认仍是 900 秒（`subagents_config.py:152`），内置的走全局 1800 秒。另外 v2.2.0 多了几层闸门，别把它们搞混：① 单次 run 的委派总数上限 `subagents.max_total_per_run`，默认 **6**（`subagents_config.py:13`）；② 进程级容量 `subagent_runtime`（`config.example.yaml:1994`：`max_running: 3` / `max_queued: 64` / `admission_policy: queue` / `queue_timeout_seconds: 300`），超出排队而不是报错；③ 并发上限合法范围是 [1, 64]（`subagents_config.py:16-17`），会被 `max_running` 二次压住。

## B.4 MCP 工具扩展 — 接入外部能力

MCP（Model Context Protocol）服务器可以为 agent 增加各种能力——文件系统操作、GitHub 操作、数据库查询等。

在 `extensions_config.json` 中配置：

```json
{
  "mcpServers": {
    "filesystem": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-filesystem", "/path/to/allowed/dir"],
      "description": "访问本地文件系统"
    },
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@anthropic-ai/github-mcp-server"],
      "description": "GitHub 操作：PR、Issue、仓库管理"
    }
  }
}
```

MCP 工具会被自动发现并绑定到 agent 上。如果工具太多担心噪声，可以启用 **deferred tool loading**：

```yaml
# config.yaml
tool_search:
  enabled: true      # 启用后 MCP tool schema 不会直接暴露
```

> 🔄 同步 #8（v2.2.0）：原文写的 `mode: keyword      # exact | keyword | text` 这个子键**在 v2.2.0 的 `config.example.yaml` 里已不存在**（`tool_search:` 在 `config.example.yaml:1395`，只有 `enabled: false` 和 `auto_promote_top_k: 3` 两项）。所以上面那行 `mode:` 已从示例里删掉；即便写了也**别指望它切换检索模式**（以你本地 `config.yaml` 的校验行为为准）。现行机制是：`enabled: true` 后 MCP tool schema 不直接进模型可见列表，`auto_promote_top_k`（1..5）控制每次模型调用前自动提升多少个匹配的 deferred schema。其余发现靠 agent 主动调 `tool_search`。详见 `_faq_on_digested/04_mcp-best-practices/`。

## B.5 完整示例：代码审查 Flow

把上述四层组合起来：

```python
from deerflow.client import DeerFlowClient

# 1. 创建客户端
client = DeerFlowClient(
    agent_name="code-reviewer",   # 使用自定义 Agent（B.2）
    model_name="deepseek-v3",
    subagent_enabled=True,        # 开启子 agent 委派（B.3）
    plan_mode=True,               # 开启 TodoList 自动任务规划
)

# 2. 上传待审查文件
client.upload_files("review-session-1", [
    "backend/packages/harness/deerflow/sandbox/tools.py",
    "backend/packages/harness/deerflow/models/factory.py",
])

# 3. 发起审查任务
result = client.chat(
    "审查我刚上传的所有 Python 文件。"
    "重点关注安全问题（命令注入、路径遍历、密钥泄露）。"
    "每个文件出一个独立的 review 报告，放在 outputs/ 目录下。",
    thread_id="review-session-1"
)

print(result)
```

这条消息触发的完整链路：

```
用户消息
    │
    ▼
[MemoryMiddleware] — 注入用户记忆到系统 prompt
    │
    ▼
[ClarificationMiddleware] — 如有歧义先澄清（本例无）
    │
    ▼
[TodoListMiddleware (plan_mode)] — LLM 拆解为 3 个 todo：
    1. 审查 sandbox/tools.py → task("code-reviewer", ...)
    2. 审查 models/factory.py → task("code-reviewer", ...)
    3. 汇总结果 + 写报告 → write_file
    │
    ▼
[SandboxMiddleware] — 获取 per-thread 沙箱
    │
    ▼
Agent 循环（agent loop, 最多 N 轮）:
    每一轮：LLM 调用 → tool 执行 → 结果注入 → 下一轮
    子 agent 通过 task() 工具并行执行（SubagentExecutor）
    │
    ▼
[SummarizationMiddleware] — 如需上下文压缩
    │
    ▼
[TitleMiddleware] — 自动生成会话标题
    │
    ▼
[MemoryMiddleware] — 排队异步更新记忆
    │
    ▼
Stream → SSE → 前端实时显示 / DeerFlowClient 逐 event 返回
```

> Agent loop 的完整执行流（包括 graph.astream 的 3 个 stream_mode、39 个 middleware 的 hook 时序）见 `_digested/internals/agent-loop/`。
>
> 🔄 同步 #6（v2.1.0-rc0）：middleware 数量 18 → 37（前 14 个共享层来自 `build_lead_runtime_middlewares()`，后 23 个来自 `build_middlewares()`，见 `_digested/internals/middleware/03-catalog.md`）。

> 🔄 同步 #8（v2.2.0）：上面那张时序图是**示意**，不是 v2.2.0 的真实位置。真实链路是两阶段组装：`_build_runtime_middlewares()`（`deerflow/agents/middlewares/tool_error_handling_middleware.py:347`，经 `build_lead_runtime_middlewares` 导出）先产出前 **16** 条，再由 `build_middlewares()`（`deerflow/agents/lead_agent/agent.py:485`）追加 **23** 条，合计 **39 个条目位**。v2.2.0 新增的几条会影响这张图的阅读：`ArtifactResolutionMiddleware` / `ArtifactCaptureMiddleware`（artifact 生命周期）、`PiiRedactionMiddleware`（`config.example.yaml:1537` 的 `pii_redaction`）、`KnowledgeScopeMiddleware`、`ModelContentCompatibilityMiddleware`；`SkillToolPolicyMiddleware` **已删除**。要按真实顺序读，请看 `_digested/internals/middleware/03-catalog.md` 的分组表，别照这张图逐条对。
