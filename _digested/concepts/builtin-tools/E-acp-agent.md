---
title: "E. 外部 Agent 集成"
description: "## invoke_acp_agent"
topics: [tools, builtin, sandbox-tools]
---

# E. 外部 Agent 集成

---

## invoke_acp_agent

**源码**: `packages/harness/deerflow/tools/builtins/invoke_acp_agent_tool.py:139`
**加载条件**: `config.yaml` 的 `acp_agents` 段有至少一个配置
**Tool Name**: `invoke_acp_agent`

### 用途

调用符合 ACP（Agent Communication Protocol，`agent-client-protocol >= 0.4.0`）标准的外部 Agent。相当于把 DeerFlow 作为"主 Agent"，把 Claude Code CLI、Codex CLI 等作为"子 Agent"来调度。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent` | `str` | 配置的 ACP Agent 名称 |
| `prompt` | `str` | 发给外部 Agent 的自包含任务描述 |

### 配置示例

```yaml
# config.yaml
acp_agents:
  mcode:
    # MiniMax Code 原生说 ACP，无需任何 adapter 包。
    # 安装：npm install --global @minimax-ai/code，然后 mcode login
    command: mcode
    args: ["acp"]
    description: "MiniMax Code for implementation, refactoring, debugging, and repository tasks"
    # auto_approve_permissions: false  # 仅对需要 mcode 改文件/跑命令的可信任务开启
    # timeout_seconds: 1800            # 超时 abort + kill 子进程（默认 30 分钟）
  claude:
    command: npx
    args:
      - "-y"
      - "@anthropic-agent/sdk"
    description: "Claude Code agent for complex coding tasks"
    auto_approve_permissions: true  # 自动 approve ACP 权限弹窗
  codex:
    command: npx
    args:
      - "-y"
      - "@openai/codex-acp"
    description: "Codex CLI for code generation"
    # model: gpt-5  # 可选，覆盖默认模型
    # env:           # 可选，环境变量（$VAR 引用宿主机变量）
    #   OPENAI_API_KEY: $OPENAI_API_KEY
```

> **MiniMax Code（`mcode`）是原生 ACP agent**（上游 #4846）：`command: mcode` + `args: ["acp"]` 直接说 ACP，不需要像 Claude Code / Codex 那样再套一个 ACP adapter 包。Gateway 进程必须在 `PATH` 上有**已认证**的 `mcode`（`npm install --global @minimax-ai/code` + `mcode login`；Docker 部署要在 Gateway 容器/镜像里装好并认证）。

### 执行流程

```
1. LLM 调用 invoke_acp_agent(agent="claude", prompt="...")
          │
2. 创建 _CollectingClient（收集流式文本输出）
          │
3. 构建 MCP servers payload（透传 DeerFlow 的 MCP 配置）
          │
4. spawn_agent_process(cmd, *args, env, cwd)
          │
5. conn.initialize() → conn.new_session(cwd, mcp_servers, model?)
          │
6. conn.prompt(session_id, prompt=[text_block(prompt)])
          │
7. 等待 _CollectingClient 收集完所有流式文本
          │
8. 返回 collected_text 或错误信息
```

### 工作区隔离

每个 thread 有独立工作区：

```python
# invoke_acp_agent_tool.py:20-50
def _get_work_dir(thread_id):
    # {base_dir}/users/{user_id}/threads/{thread_id}/acp-workspace/
    return work_dir
```

- 并发 session 互不干扰
- 外部 Agent 完成后的输出文件在 `/mnt/acp-workspace/`（read-only）
- 本地沙箱：路径翻译；Docker 沙箱：volume 挂载

### MCP 透传

DeerFlow 把启用的 MCP server 配置转成 ACP wire format 发给外部 Agent：

```python
mcp_servers = _build_acp_mcp_servers()
# ext_config → [{name, type, command/url, args, env, headers}, ...]
```

如果 MCP 配置不合法，Warning 后继续（不带 MCP server）。

### 权限处理

`_build_permission_response(options, auto_approve)`：
- `auto_approve=True` → 选第一个 `allow_once` 或 `allow_always` 选项
- `auto_approve=False` → 一律 `cancelled`，外部 Agent 需要自己处理权限

### 错误诊断

当 ACP 命令在 PATH 上找不到时，根据 command 名给出具体建议：

```
# mcode 找不到（agent == "mcode"）
"Error invoking ACP agent 'mcode': Command 'mcode' was not found on PATH.
 Install it with `npm install --global @minimax-ai/code`, run `mcode login`,
 and restart DeerFlow so it inherits the updated PATH.
 If the Gateway runs in Docker, ensure `mcode` is installed and authenticated
 inside the Gateway container/image."

# codex-acp 找不到，但 codex 在 PATH 上
"Error invoking ACP agent 'codex': Command 'codex-acp' was not found on PATH.
 The installed `codex` CLI does not speak ACP directly.
 Install a Codex ACP adapter (for example `npx @openai/codex-acp`)
 or update `acp_agents.codex.command` and `args` in config.yaml."
```

### Tool Description 生成

`build_invoke_acp_agent_tool()` 从配置的 agents 动态生成 description：

```python
description = (
    "Invoke an external ACP-compatible agent and return its final response.\n\n"
    "Available agents:\n"
    "- claude: Claude Code agent for complex coding tasks\n"
    "- codex: Codex CLI for code generation\n\n"
    "IMPORTANT: ACP agents operate in their own independent workspace. ..."
)
```

这样 LLM 知道有哪些 agent 可用，不需要硬编码名称。

### 注意事项

- ACP launcher 必须是真正的 ACP 适配器，普通的 `codex` 二进制不兼容
- **MiniMax Code（`mcode`）例外**：`command: mcode` + `args: ["acp"]` 原生说 ACP，无需 adapter；Gateway 进程需有已认证的 `mcode`
- `_CollectingClient.session_update()` 只收集 `session_update == "agent_message_chunk"` 的 `TextContentBlock` 文本——thought chunk 保持内部，**不**拼进返回给模型的 tool 结果
- 使用 per-thread workspace，给外部 Agent 的 prompt 应该是自包含的任务描述，不要引用 `/mnt/user-data` 路径
