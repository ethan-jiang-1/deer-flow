---
title: "config.yaml 全段参考"
description: "DeerFlow 有两个配置文件，都放在项目根目录。"
topics: [configuration, hot-reload, yaml-config]
---

# config.yaml 全段参考

> 迁移自 `integration/02-configuration.md`。本文是 `config.yaml` + `extensions_config.json` 的字段级参考手册。
> 配置系统的设计原理见 [00-overview.md](../../getting-started/00-config-overview.md)，动态加载机制见 [03-dynamic-loading.md](03-dynamic-loading.md)。

DeerFlow 有两个配置文件，都放在项目根目录。

## 配置文件概览

| 文件 | 用途 | 生成方式 |
|------|------|----------|
| `config.yaml` | 主配置（1100+ 行） | `make config` 从 `config.example.yaml` 生成 |
| `extensions_config.json` | 扩展配置 | 从 `extensions_config.example.json` 复制 |

配置解析优先级：
1. 显式代码传参
2. 环境变量 `DEER_FLOW_CONFIG_PATH` / `DEER_FLOW_EXTENSIONS_CONFIG_PATH`
3. 当前目录 `./config.yaml`
4. 父目录 `../config.yaml`（项目根，**推荐**）

环境变量替换：配置值中以 `$` 开头的会被解析为环境变量，如 `api_key: $OPENAI_API_KEY`。

---

# config.yaml

## 配置版本

```yaml
config_version: 19
```

用于检测配置过期。改 schema 时上游会升这个数字。`make config-upgrade` 把新字段合并到已有 `config.yaml`。

## Logging

```yaml
log_level: info   # debug | info | warning | error
```

## Token Usage

```yaml
token_usage:
  enabled: true    # 是否记录每次模型调用的 token 消耗
```

## Models（模型配置）

必填的核心段。配置可用的 LLM 模型列表。

```yaml
models:
  - name: my-model              # 内部标识符（URI-safe，仅用于配置引用）
    display_name: My Model      # UI 显示名
    use: langchain_openai:ChatOpenAI  # 类路径，通过 reflection 加载
    model: gpt-4                # provider 模型 ID
    api_key: $OPENAI_API_KEY    # 环境变量
    timeout: 600.0
    max_retries: 2
    max_tokens: 4096
    temperature: 0.7
    supports_thinking: false    # 支持扩展思考
    supports_vision: false      # 支持图片输入
    supports_reasoning_effort: false
    use_responses_api: false    # 使用 OpenAI Responses API（OpenAI 专用）
    output_version: null
    when_thinking_enabled:      # 开启思考时的覆盖参数
      extra_body:
        thinking:
          type: enabled
    when_thinking_disabled:     # 关闭思考时的覆盖参数
      extra_body:
        thinking:
          type: disabled
```

### `use` 支持的 provider 类路径

| Provider | `use` 值 |
|----------|----------|
| OpenAI | `langchain_openai:ChatOpenAI` |
| Anthropic | `langchain_anthropic:ChatAnthropic` |
| DeepSeek | `deerflow.models.patched_deepseek:PatchedChatDeepSeek` |
| Google Gemini | `langchain_google_genai:ChatGoogleGenerativeAI` |
| Ollama | `langchain_ollama:ChatOllama`（推荐，支持 thinking 透传） |
| vLLM | `deerflow.models.vllm_provider:VllmChatModel` |
| MiniMax | `deerflow.models.minimax:PatchedChatMiniMax` |
| MindIE | `deerflow.models.mindie:ChatMindIE` |
| Novita | `langchain_openai:ChatOpenAI`（OpenAI 兼容） |

**Ollama 重要提示**：如果用 `langchain_openai:ChatOpenAI` 连 Ollama，thinking/reasoning_content 不会正确返回。必须用 `langchain_ollama:ChatOllama`，它走原生 `/api/chat` 路径。

### 模型热加载

模型列表支持热加载——修改 `config.yaml` 后下一个请求生效，无需重启。

## Tool Groups & Tools

### 工具分组

```yaml
tool_groups:
  web: ~       # web_search, web_fetch, image_search 的归属
  file:read: ~ # ls, read_file, glob, grep
  file:write: ~ # write_file, str_replace
  bash: ~      # bash
```

### 内置工具配置

| 工具 | `use` 路径 | 备注 |
|------|-----------|------|
| `web_search` | `deerflow.community.ddg_search.tools:web_search_tool` | DuckDuckGo，免费，默认 |
| `web_search` | `deerflow.community.serper.tools:web_search_tool` | Google Search，需 `SERPER_API_KEY` |
| `web_search` | `deerflow.community.tavily.tools:web_search_tool` | Tavily，需 `TAVILY_API_KEY` |
| `web_search` | `deerflow.community.infoquest.tools:web_search_tool` | InfoQuest，需 `INFOQUEST_API_KEY` |
| `web_search` | `deerflow.community.exa.tools:web_search_tool` | Exa，需 `EXA_API_KEY` |
| `web_search` | `deerflow.community.firecrawl.tools:web_search_tool` | Firecrawl，需 `FIRECRAWL_API_KEY` |
| `web_fetch` | `deerflow.community.jina_ai.tools:web_fetch_tool` | Jina AI，默认，免费 |
| `web_fetch` | `deerflow.community.exa.tools:web_fetch_tool` | Exa |
| `web_fetch` | `deerflow.community.infoquest.tools:web_fetch_tool` | InfoQuest |
| `web_fetch` | `deerflow.community.firecrawl.tools:web_fetch_tool` | Firecrawl |
| `image_search` | `deerflow.community.image_search.tools:image_search_tool` | DuckDuckGo 图片搜索 |
| `image_search` | `deerflow.community.infoquest.tools:image_search_tool` | InfoQuest 图片搜索 |
| `ls` | `deerflow.sandbox.tools:ls_tool` | 目录列表 |
| `read_file` | `deerflow.sandbox.tools:read_file_tool` | 文件读取 |
| `glob` | `deerflow.sandbox.tools:glob_tool` | 文件匹配 |
| `grep` | `deerflow.sandbox.tools:grep_tool` | 文本搜索 |
| `write_file` | `deerflow.sandbox.tools:write_file_tool` | 文件写入 |
| `str_replace` | `deerflow.sandbox.tools:str_replace_tool` | 文件替换 |
| `bash` | `deerflow.sandbox.tools:bash_tool` | 命令执行 |

### web_search 只能有一个

虽然列出多个 provider，但实际只能启用一个 `web_search`。工具按名称去重，config.yaml 中先列出的优先。要换 provider，注释掉当前的，取消注释目标。

## Tool Search（延迟 MCP 工具加载）

```yaml
tool_search:
  enabled: false   # 开启后 MCP 工具不在初始上下文，通过 tool_search 按需发现
```

## Loop Detection（循环检测）

```yaml
loop_detection:
  enabled: true
  warn_threshold: 3         # 连续相同调用 >=3 次时警告
  hard_limit: 5             # >=5 次强停
  window_size: 20
  max_tracked_threads: 100
  tool_freq_warn: 30        # 单工具频次警告
  tool_freq_hard_limit: 50  # 单工具频次强停
  # tool_freq_overrides:    # 按工具覆盖阈值
  #   bash:
  #     warn: 150
  #     hard_limit: 300
```

## Safety Finish Reason

```yaml
safety_finish_reason:
  enabled: true     # 拦截 provider 安全终止（content_filter/refusal/SAFETY）
```

当 provider 返回 `finish_reason='content_filter'` 但仍有 `tool_calls` 时，这些 tool_calls 可能是不完整/不可靠的，该中间件会阻止执行。

## Uploads

```yaml
uploads:
  max_files: 10
  max_file_size: 52428800     # 50 MiB
  max_total_size: 104857600   # 100 MiB
  auto_convert_documents: false  # 自动转换 Office/PDF 为 markdown
  pdf_converter: auto             # auto | pymupdf4llm | markitdown
```

**安全提醒**：`auto_convert_documents` 在 Gateway 主机端解析文档，开启后存在 parser 风险。仅在完全可信来源下开启。

## Sandbox（沙箱）

### 本地沙箱（默认）

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: false  # 主机 bash，默认关闭
  bash_output_max_chars: 20000
  read_file_output_max_chars: 50000
  ls_output_max_chars: 20000
  # mounts:                    # 可选：额外挂载目录
  #   - host_path: /home/user/my-project
  #     container_path: /mnt/my-project
  #     read_only: true
```

### AIO 沙箱（Docker 隔离）

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  # image: enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
  # port: 8080
  # replicas: 3
  # mounts:
  #   - host_path: /path/on/host
  #     container_path: /home/user/shared
  #     read_only: false
  # environment:
  #   NODE_ENV: production
```

macOS 上自动优先用 Apple Container，fallback 到 Docker。

### Provisioner 模式（K3s）

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  provisioner_url: http://provisioner:8002
```

## Subagents（子 Agent）

```yaml
subagents:
  timeout_seconds: 900      # 默认超时 15 分钟
  # max_turns: 120          # 全局最大轮次
  agents:
    general-purpose:
      timeout_seconds: 1800  # 复杂任务 30 分钟
      max_turns: 160
      # model: qwen3:32b     # 指定模型（默认继承主 Agent）
      # skills: ["web-search", "data-analysis"]
    bash:
      timeout_seconds: 300
      max_turns: 80
  custom_agents:
    analysis:
      description: "Data analysis specialist"
      system_prompt: "You are a data analysis subagent..."
      tools: ["bash", "read_file", "write_file"]
      skills: ["data-analysis"]
      model: inherit          # inherit | 具体模型名
      max_turns: 80
      timeout_seconds: 600
```

## ACP Agents（外部 Agent 协议）

```yaml
acp_agents:
  claude_code:
    command: npx
    args: ["-y", "@zed-industries/claude-agent-acp"]
    description: Claude Code for implementation
    model: null
    # auto_approve_permissions: false
    # env:
    #   ANTHROPIC_API_KEY: $ANTHROPIC_API_KEY
  codex:
    command: npx
    args: ["-y", "@zed-industries/codex-acp"]
    description: Codex CLI for repository tasks
```

ACP agent 通过 `invoke_acp_agent` 工具调用。每个 ACP agent 使用 per-thread workspace (`acp-workspace/`)。

## Skills

```yaml
skills:
  # path: /absolute/path/to/skills    # 覆盖 Skill 路径
  container_path: /mnt/skills         # 沙箱中的虚拟路径
```

Skill 位于 `skills/public/`(已提交) 和 `skills/custom/`(gitignored)。启停状态在 `extensions_config.json`。

## Title Generation

```yaml
title:
  enabled: true
  max_words: 6
  max_chars: 60
  model_name: null     # null = 使用默认模型
```

## Summarization（上下文摘要）

```yaml
summarization:
  enabled: true
  model_name: null     # 推荐低成本模型如 gpt-4o-mini
  trigger:
    - type: tokens
      value: 32000     # token 达到 32000 时触发
    # - type: messages
    #   value: 50
    # - type: fraction
    #   value: 0.8      # 模型最大输入的 80%
  keep:
    type: messages
    value: 10           # 保留最近 10 条消息
  trim_tokens_to_summarize: 15564
  summary_prompt: null
  preserve_recent_skill_count: 5       # 保留最近加载的 Skill
  preserve_recent_skill_tokens: 25000
  preserve_recent_skill_tokens_per_skill: 5000
```

## Memory（用户记忆）

```yaml
memory:
  enabled: true
  storage_path: memory.json   # 相对于 backend/ 目录
  debounce_seconds: 30        # 更新去抖间隔
  model_name: null
  max_facts: 100
  fact_confidence_threshold: 0.7
  injection_enabled: true     # 是否注入 system prompt
  max_injection_tokens: 2000
```

## Database（数据库/持久化）

```yaml
database:
  backend: sqlite            # memory | sqlite | postgres
  sqlite_dir: .deer-flow/data
```

三个选项：
- **memory** — 进程内，无持久化，重启丢失
- **sqlite**（默认） — 单机，WAL 模式
- **postgres** — 多 worker 生产，需安装 `[postgres]` extra

**注意**：`database.*`、`checkpointer.*` 等基础设施字段改后需重启才生效（见 `CLAUDE.md` 热加载表）。

## Run Events

```yaml
run_events:
  backend: memory        # memory | db | jsonl
  max_trace_content: 10240
  track_token_usage: true
```

## Agents API

```yaml
agents_api:
  enabled: false   # 自定义 Agent SOUL.md 管理 API，仅可信管理边界内开启
```

## Skill Self-Evolution

```yaml
skill_evolution:
  enabled: false    # 允许 Agent 自主创建/改进 skills/custom 下的 skill
  moderation_model_name: null
```

## Guardrails（工具调用鉴权）

三种方式：

**1. AllowlistProvider（内置，零依赖）**
```yaml
guardrails:
  enabled: true
  provider:
    use: deerflow.guardrails.builtin:AllowlistProvider
    config:
      denied_tools: ["bash", "write_file"]
```

**2. OAP 协议**
```yaml
# guardrails:
#   enabled: true
#   provider:
#     use: aport_guardrails.providers.generic:OAPGuardrailProvider
```

**3. 自定义 Provider**
```yaml
# guardrails:
#   enabled: true
#   provider:
#     use: my_package:MyGuardrailProvider
#     config:
#       key: value
```

## Circuit Breaker（熔断）

```yaml
circuit_breaker:
  failure_threshold: 5       # 连续失败 >=5 次熔断
  recovery_timeout_sec: 60   # 60s 后尝试恢复
```

默认关闭。

## IM Channels

详见 [../integration/07-im-channels.md](../../operations/integration/04-im-channels.md)。

---

## 配置热加载备忘

| 无需重启 | 需重启 |
|----------|--------|
| models（模型列表/参数） | database.backend |
| summarization | checkpointer |
| title | run_events |
| memory | stream_bridge |
| subagents | sandbox.use |
| tools | log_level |
| agent system prompt | channels 凭证 |
| guardrails | |

---

# extensions_config.json

```json
{
  "mcpInterceptors": ["my_package.mcp.auth:build_auth_interceptor"],
  "mcpServers": {
    "github": {
      "enabled": false,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "$GITHUB_TOKEN" },
      "description": "GitHub MCP server for repository operations"
    },
    "postgres": {
      "enabled": false,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
      "description": "PostgreSQL database access"
    }
  },
  "skills": {
    "deep-research": { "enabled": true },
    "data-analysis": { "enabled": false }
  }
}
```

- `mcpInterceptors`：MCP 认证拦截器，在创建 MCP 连接时注入 auth header
- `mcpServers`：MCP 服务器配置，type 可为 `stdio` / `sse` / `http`
  - SSE/HTTP 支持 OAuth（client_credentials、refresh_token 自动刷新）
- `skills`：Skill 的启用/禁用状态
  - Key 为 Skill 名称（与 `SKILL.md` frontmatter 中 `name` 一致）
  - 运行时通过 `POST /api/skills/install` 安装 .skill zip 会自动追加

两个文件都支持通过 Gateway API 运行时修改（`PUT /api/mcp/config`、`PUT /api/skills/{name}`）。
