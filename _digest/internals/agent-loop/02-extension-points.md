---
title: "扩展点：从内到外怎么往里加东西"
description: "前面两篇讲了 loop 的结构和 middleware 的设计。这篇回答实际问题：**我想扩展 DeerFlow，应该从哪个层面加东西？**"
topics: [agent-loop, langgraph, execution-model]
---

# 扩展点：从内到外怎么往里加东西

前面两篇讲了 loop 的结构和 middleware 的设计。这篇回答实际问题：**我想扩展 DeerFlow，应该从哪个层面加东西？**

## 三层扩展模型

```
                     ┌─────────────────────┐
                     │   Level 3: 通道层    │  ← 加协议、加平台
                     │  (IM channels, API) │
                     └─────────┬───────────┘
                               │
                     ┌─────────▼───────────┐
                     │   Level 2: Agent 层  │  ← 加 middleware、加 subagent
                     │  (middleware 链,     │
                     │   subagent 类型)     │
                     └─────────┬───────────┘
                               │
                     ┌─────────▼───────────┐
                     │   Level 1: Tool 层   │  ← 加 tool、加 skill
                     │  (tools, MCP,       │
                     │   community tools)  │
                     └─────────┬───────────┘
                               │
                     ┌─────────▼───────────┐
                     │   Level 0: 模型层    │  ← 加 provider、调参数
                     │  (LLM providers,    │
                     │   thinking, vision)  │
                     └─────────────────────┘
```

从下往上，扩展的"影响半径"越来越大：
- **Level 0（模型层）**：只影响"LLM 怎么回答"，不影响 loop 行为
- **Level 1（Tool 层）**：影响"agent 能做什么"，仍然在标准 loop 框架内
- **Level 2（Agent 层）**：影响"agent loop 的行为方式"，需要理解 middleware 机制
- **Level 3（通道层）**：影响"用户怎么跟 agent 交互"，在 loop 外面

## Level 0：换模型/加模型

最浅的扩展。DeerFlow 的模型系统通过 `config.yaml` 声明式配置，运行时通过 `create_chat_model()` 反射加载：

```yaml
models:
  - name: my-custom-model
    provider: openai
    model: gpt-4o
    supports_thinking: false
    supports_vision: true
    max_tokens: 4096
```

如果要加一个全新的 provider（不是 OpenAI 兼容的），需要：

1. 实现一个 LangChain `BaseChatModel` 子类
2. 在 `config.yaml` 中配置 `use: mypackage.module:MyChatModel`
3. `create_chat_model()` 通过 `resolve_class()` 动态加载

**对 agent loop 的影响：零。** loop 不关心模型是什么——它只看到 `BaseChatModel` 接口。

## Level 1：加 Tool

这是最常见的扩展。三种方式：

### 方式 A：内置 tool（Python 函数）

```python
# 写一个函数，加上 @tool 装饰器
from langchain.tools import tool

@tool
def my_calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    return str(eval(expression))
```

然后在 `get_available_tools()` 中注册，或在 `config.yaml` 中声明 tool group。

**对 loop 的影响：** tool 在 tools node 内被调用。middleware 的 `wrap_tool_call` 会包装它（sandbox 路径转换、错误处理等）。如果 tool 抛异常，`ToolErrorHandlingMiddleware` 把它转成 ToolMessage 而不是让整个 run 崩溃。

### 方式 B：MCP Server（进程级集成）

```json
// extensions_config.json
{
  "mcpServers": {
    "my-server": {
      "enabled": true,
      "type": "stdio",
      "command": "python",
      "args": ["-m", "my_mcp_server"]
    }
  }
}
```

MCP tools 通过 `langchain-mcp-adapters` 自动发现和转换。tool 列表按 mtime 缓存，改了配置文件自动失效。

**对 loop 的影响：** MCP tool 对 loop 来说跟内置 tool 一样。关键区别是 MCP tool 可能是异步的（stdio/SSE/HTTP transport），在 subagent 的 persistent daemon loop 上也能正常跑。

### 方式 C：Skill（带 prompt 的 tool 集合）

Skill 不是单纯的 tool——它是一组 tool + 一段 system prompt（`SKILL.md`）。当 skill 被激活时，它的 prompt 注入到 agent 的上下文中，它的 allowed-tools 白名单限制模型能调哪些 tools。

```
skill 加载流程:
  skills/public/my-skill/SKILL.md
    ↓ load_skills() 解析 YAML frontmatter
    ↓ 提取 name, description, allowed-tools
    ↓
  agent 创建时:
    ↓ filter_tools_by_skill_allowed_tools(tools, skills)
    ↓ 只保留 allowed-tools 交集内的 tool
    ↓ skill prompt 注入 system prompt
    ↓
  agent loop 执行时:
    ↓ skill prompt 作为上下文指导模型行为
    ↓ 模型只能调用 skill 允许的 tool
```

**对 loop 的影响：** Skill 不改变 loop 结构，只是限制可用 tool 集合 + 添加行为引导。这是一种**约束型扩展**——不能做更多事，而是把能做的事控制在某个领域内。

### Subagent 里的 skill 加载

Subagent 加载 skill 的方式跟 lead agent 不同——subagent 的 skill 作为**对话内容**而不是 system prompt 注入：

```python
# lead agent: skill 在 system prompt 里
system_prompt = "... <skills>skill content</skills> ..."

# subagent: skill 作为 SystemMessage 插入 message list
messages = [
    SystemMessage(content="skill content"),
    HumanMessage(content=task),
]
```

这是为了兼容 Codex 的 skill 模式，也让 subagent 的 skill 可以跟 agent 本身的 system prompt 分开管理。

## Level 2：加 Middleware

这是最强大的扩展方式，也最需要理解 loop 机制。在这写一个自定义 middleware 的完整流程：

### 第一步：继承 AgentMiddleware

```python
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

class MyMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        # 修改传给 LLM 的消息
        modified = request.override(
            messages=[*request.messages, HumanMessage(content="extra context")]
        )
        # 调用下一层
        response = handler(modified)
        # 修改 LLM 的返回（可选）
        return response
```

### 第二步：选择定位方式

DeerFlow 提供了 `@Next` / `@Prev` 定位装饰器：

```python
from deerflow.agents.features import Next
from deerflow.agents.middlewares import LoopDetectionMiddleware

@Next(LoopDetectionMiddleware)
class MyMiddleware(AgentMiddleware):
    ...
```

这意味着你的 middleware 会被插入到 `LoopDetectionMiddleware` **之后**。也可以传实例到 `extra_middleware` 参数配合 `@Prev`。

### 第三步：注入到链中

- **Lead agent 路径**：通过 `_build_middlewares()` 的 `custom_middlewares` 参数
- **SDK 路径**：通过 `create_deerflow_agent(features=RuntimeFeatures(...))` 传递自定义实例

### Middleware 扩展的注意事项

1. **`wrap_model_call` 的实现要调 `handler(request)`**——不调就是跳过 LLM，调了就是继续洋葱链。忘了调用会导致 LLM 永远不执行。
2. **`after_model` 是反向执行的**——你的 hook 会在"后面的" middleware 之后执行
3. **不要在 `after_model` 里插入消息**（除非你确定 tool_calls 配对已经完成）
4. **middleware 实例是 per-agent 的**——如果同一个进程有多个 agent，每个有自己的 middleware 实例

## Level 2.5：加 Subagent 类型

Subagent 是 Level 2 的一个特殊情况——它不只是加 middleware，而是定义一个**全新的 agent 配置**。

内置两种 subagent：
- `general-purpose`: 除了 `task` 以外的所有 tools
- `bash`: 只有 sandbox tools（bash, ls, read, write, str_replace）

注册新的 subagent 类型需要两个步骤：

### 1. 定义 SubagentConfig

```python
from deerflow.subagents.config import SubagentConfig

my_agent = SubagentConfig(
    name="my-agent",
    description="Specialized agent for X",
    system_prompt="You are an expert at X...",
    tools=["tool_a", "tool_b"],           # allowlist
    disallowed_tools=["dangerous_tool"],   # denylist
    skills=["my-skill"],                   # 加载哪些 skills
    model="inherit",                       # 或指定具体 model name
    max_turns=15,
    timeout_seconds=300,
)
```

### 2. 注册

```python
from deerflow.subagents.registry import register_subagent
register_subagent(my_agent)
```

注册后，lead agent 的系统 prompt 中会自动出现这个 subagent type，模型可以通过 `task(subagent_type="my-agent", ...)` 调用它。

**对 loop 的影响：** Subagent 有自己的独立 agent loop（见 [[00-loop-anatomy]] Layer 3），有自己的 middleware 链（基础设施的 6-7 个）。它的 loop 不受主 agent 的 middleware 影响，只在 cancel/timing 上受主 agent 控制。

## Level 3：加通道（外部接口）

通道层（IM Channels、REST API、Embedded Client）完全在 agent loop 外面。它们是 loop 的**消费者**：

```
Feishu/Slack/Telegram/DingTalk
  → Channel Manager
    → message_bus.publish_inbound()
      → dispatch_loop
        → client.runs.stream() / client.runs.wait()
          → Gateway API
            → run_agent() → agent.astream() → SSE stream
```

三种消费模式的差异：

| 模式 | 使用场景 | 消费方式 |
|------|---------|---------|
| SSE Stream (Feishu) | 需要增量 UI 更新 | `runs.stream(["values", "messages-tuple"])` → 逐 chunk 更新 |
| Block & Wait (Slack/Telegram) | 消息平台只关心最终结果 | `runs.wait()` → 等 run 结束取最终消息 |
| Embedded Client | Python SDK 直接调用 | `DeerFlowClient.stream()` → yield StreamEvent |

**加一个新通道的步骤：**
1. 实现 `base.py` 中的 `Channel` 抽象类
2. 在 `config.yaml` 的 `channels` 段配置
3. `ChannelManager` 自动发现并启动

对 agent loop 的影响：零。通道只是 listen 和 publish 的适配层。

## 扩展决策速查表

| 我想... | 用哪个 Level | 具体怎么做 |
|---------|-------------|-----------|
| agent 能在 new API 上搜索 | Level 1 | 加 Community Tool / MCP Server |
| agent 在特定领域更专业 | Level 1 | 写一个 Skill (SKILL.md + allowed-tools) |
| 控制 agent 在 loop 的某一步做什么 | Level 2 | 写 Middleware + @Next/@Prev 定位 |
| 创建一个专门做某事的子 agent | Level 2.5 | 定义 SubagentConfig + register |
| 支持新的聊天平台 | Level 3 | 实现 Channel 抽象类 |
| 换成公司的内部模型 | Level 0 | 实现 BaseChatModel 子类 + config.yaml |
| agent 遇到某个 tool 的错误不要崩溃 | Level 2 | ToolErrorHandlingMiddleware 已经做了，配置即可 |
| 限制 agent 最多调 N 次 tool | Level 2 | LoopDetection 已经做了，调 config 参数 |
| 在模型调用前自动注入一段提示 | Level 2 | DynamicContextMiddleware 的模式，或自己写 |

## 一个具体例子：从零加一个 "日志审计 middleware"

假设需求：每次 tool 执行后，把 tool name + args + result 写到审计日志。

```python
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest

class AuditLoggingMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request: ToolCallRequest, handler):
        # 执行前记录
        logger.info(f"AUDIT: tool={request.tool_call['name']}, args={request.tool_call['args']}")
        
        # 执行 tool
        result = handler(request)
        
        # 执行后记录结果（截断以防太长）
        result_preview = str(result)[:500]
        logger.info(f"AUDIT: result={result_preview}")
        
        return result
```

然后注入：

```python
# 情境: 想在 GuardrailMiddleware 之后、SandboxAuditMiddleware 之前
from deerflow.agents.features import Next
from deerflow.agents.middlewares.guardrails.middleware import GuardrailMiddleware

@Next(GuardrailMiddleware)
class AuditLoggingMiddleware(AgentMiddleware):
    ...
```

传给 `_build_middlewares()` 的 `custom_middlewares` 参数即可。

这就是 DeerFlow 扩展体系的完整图景：**四层扩展，从改配置到写 middleware，从 tool 到 subagent，每一层都有明确的接口和定位规则**。
