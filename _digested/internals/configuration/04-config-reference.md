---



title: "config.yaml 全段参考"
description: 'DeerFlow 有两个配置文件，都放在项目根目录。'
topics: [configuration, hot-reload, yaml-config]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# config.yaml 全段参考

> 迁移自 `integration/02-configuration.md`。本文是 `config.yaml` + `extensions_config.json` 的字段级参考手册。
> 配置系统的设计原理见 [00-overview.md](../../getting-started/00-config-overview.md)，动态加载机制见 [03-dynamic-loading.md](03-dynamic-loading.md)。

DeerFlow 有两个配置文件，都放在项目根目录。

## 配置文件概览

| 文件 | 用途 | 生成方式 |
|------|------|----------|
| `config.yaml` | 主配置（模板 `config.example.yaml` = **3680 行**） | `make config` 从 `config.example.yaml` 生成（**不**生成 `extensions_config.json`；Docker 路径由 `scripts/docker.sh:388-395` 补建） |
| `extensions_config.json` | 扩展配置 | 从 `extensions_config.example.json` 复制 |

配置解析优先级（真值 `AppConfig.resolve_config_path()`，`config/app_config.py:448`）：

1. 显式代码传参 `config_path`
2. 环境变量 `DEER_FLOW_CONFIG_PATH`（**设了但文件不存在 → `FileNotFoundError`，不回落搜索**）
3. `project_root()/config.yaml`（最常用）；`project_root()` = `DEER_FLOW_PROJECT_ROOT`（必须是存在的目录，否则 `ValueError`）否则 `cwd`（`config/runtime_paths.py:7-16`）
4. legacy 探测：`backend/config.yaml` → `repo_root/config.yaml`（`_legacy_config_candidates`，`config/app_config.py:193-197`）

> 旧版本文里"当前目录 → 父目录"的两级说法**已删除**——现在的语义是"一个 `project_root()` + 两个 legacy 候选"，与 `extensions_config.json` 的搜索路径不是同一条链。

环境变量替换：配置值中以 `$` 开头的会被解析为环境变量，如 `api_key: $OPENAI_API_KEY`；缺失时 AppConfig **报错**、ExtensionsConfig 存空串。

🆕 **`.env` 的加载由 `DEER_FLOW_ENV_FILE` 决定**（`deerflow/env.py:10` 的 `load_selected_env_file()`）：设了该变量就只读那一个文件（且与 `PYTHON_DOTENV_DISABLED` 同时设置会直接 `ValueError`），没设则回落 `load_dotenv()` 的自动发现。它在这三处被调用：`config/app_config.py:67-70`、`app/gateway/auth/config.py:58-64`、`backend/debug.py:23`。

---

# config.yaml

## 配置版本

```yaml
config_version: 63     # config.example.yaml:23
```

用于检测配置过期。改 schema 时上游会升这个数字（v2.1.0 是 45，v2.2.0 是 63）。

- 不匹配时 `AppConfig._check_config_version()`（`config/app_config.py:599`）发 **warning**（`config/app_config.py:636-640`）而**不是**错误：DeerFlow 仍会启动，缺失的新字段取默认值。
- `make config-upgrade` 把新字段合并到已有 `config.yaml`。
- 🆕 v46 起带**语义迁移**：`knowledge_base.enabled` 按旧字段的存在与否回填，使老配置升级后保持原来的工具可见性。

## Logging

```yaml
log_level: info   # debug | info | warning | error
```

> 🔄 Sync #6：trace id 现在**无条件下发**——每个 HTTP 响应都带 `X-Trace-Id`。`logging.enhance.enabled` 只控制**日志格式**（日志记录是否带 `trace_id` 字段及格式），默认关闭。

## Recursion Limit 🔄 Sync #6

```yaml
recursion_limit: 100        # 🆕 可配置的默认值（原来硬编码 100）
max_recursion_limit: 1000   # 硬上限，钳制配置值与客户端值
```

客户端可以在请求里覆盖 `recursion_limit`，非法/非正数回退到 `recursion_limit` 配置值；任何超过 `max_recursion_limit` 的值（无论来自配置还是客户端）都被钳制下来。

另：`DEER_FLOW_DATE_TIMEZONE` 环境变量（🆕）可指定注入 agent 的会话日期所用 IANA 时区（如 `Asia/Shanghai`）；它不是 config schema 字段，由 date-context 中间件运行时读取，容器里设了即生效，无需挂载 config.yaml。

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
    use_previous_response_id: false  # 🆕 Responses API：只发新 turn + previous_response_id，不重放全量历史
    request_admission:          # 🆕 每-模型请求节奏（RPM 共享配额，默认关闭）
      requests_per_minute: 60
      group: shared-provider-account  # 可选；默认为模型配置名；共享 group 要求设置完全一致
      max_wait_seconds: 300
      max_queue_size: 256
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
| OpenAI（DeerFlow 补丁版） | `deerflow.models.patched_openai:PatchedChatOpenAI` |
| Anthropic | `langchain_anthropic:ChatAnthropic` |
| Claude（订阅凭据） | `deerflow.models.claude_provider:ClaudeChatModel` |
| Codex（订阅凭据） | `deerflow.models.openai_codex_provider:CodexChatModel` |
| DeepSeek | `deerflow.models.patched_deepseek:PatchedChatDeepSeek` |
| Google Gemini | `langchain_google_genai:ChatGoogleGenerativeAI` |
| Ollama | `langchain_ollama:ChatOllama`（推荐，支持 thinking 透传） |
| vLLM | `deerflow.models.vllm_provider:VllmChatModel` |
| MiniMax | `deerflow.models.patched_minimax:PatchedChatMiniMax` |
| MindIE | `deerflow.models.mindie_provider:MindIEChatModel` |
| Xiaomi MiMo | `deerflow.models.patched_mimo:PatchedChatMiMo` |
| StepFun（阶跃星辰） | `deerflow.models.patched_stepfun:PatchedChatStepFun` |
| Novita | `langchain_openai:ChatOpenAI`（OpenAI 兼容） |

（`deerflow/models/` 下共 9 个自研适配器类：`claude_provider` / `openai_codex_provider` / `patched_openai` / `patched_deepseek` / `patched_minimax` / `patched_mimo` / `patched_stepfun` / `vllm_provider` / `mindie_provider`；OpenAI/Anthropic/Gemini/Ollama 直接复用 LangChain provider。）

**Ollama 重要提示**：如果用 `langchain_openai:ChatOpenAI` 连 Ollama，thinking/reasoning_content 不会正确返回。必须用 `langchain_ollama:ChatOllama`，它走原生 `/api/chat` 路径。

### `request_admission`（RPM 准入）🆕

每个模型条目内可选配置进程内 RPM 排队（不是 TPM，也不是集群级配额）。同 `group` 的模型共享配额，设置必须完全一致；修改后需重启。上游示例还带一个 GLM-5.3-Flash workaround 配置（`deerflow.models.patched_deepseek:PatchedChatDeepSeek` + `extra_body.thinking: {type: enabled, clear_thinking: true}` + `supports_reasoning_effort: false`）——该模型不能关 thinking、只接受 low/high/max effort，所以强制 thinking 开启并抑制通用 effort 透传。

### `use_previous_response_id` 🆕

OpenAI Responses API 模型可开（默认 false）：请求只带最新 turn + `previous_response_id`，链式上下文仍按 input token 计费；且客户端侧历史改写（如 blocked-write payload elision）只在重放历史时生效。

### 模型热加载

模型列表支持热加载——修改 `config.yaml` 后下一个请求生效，无需重启。

## Extensions.middlewares（config 声明的中间件）🔄 Sync #6

```yaml
# extensions:
#   middlewares:
#     - my_company.deerflow_middlewares:DomainGuardMiddleware   # 零参类路径
#     - class: my_company.deerflow_middlewares:LatencyStampingMiddleware
#       kwargs:
#         header: X-DeerFlow-Latency                            # 🆕 构造参数
```

条目可以是类路径，或 🆕 `{class, kwargs}` 形式传构造参数（kwargs 值必须是 JSON 类型；YAML 日期/时间戳会被转成 ISO 字符串）。构造异常在 agent 创建时报错并带底层异常。该列表同时作用于 lead 与 subagent 运行时；留空时 `extensions_config.json` 仍是这个 fixed-slot 列表的真相源。

## Tool Groups & Tools

### 工具分组

```yaml
tool_groups:
  - name: web         # web_search, web_fetch, image_search 的归属
  - name: file:read   # ls, read_file, glob, grep
  - name: file:write  # write_file, str_replace
  - name: bash        # bash
  - name: browser
  - name: knowledge
```

### 内置工具配置

| 工具 | `use` 路径 | 备注 |
|------|-----------|------|
| `web_search` | `deerflow.community.ddg_search.tools:web_search_tool` | DuckDuckGo，免费，默认 |
| `web_search` | `deerflow.community.serper.tools:web_search_tool` | Google Search，需 `SERPER_API_KEY` |
| `web_search` | `deerflow.community.serply.tools:web_search_tool` | 🆕 Google Search/News/Scholar，需 `SERPLY_API_KEY`，支持 `vertical`/`gl`/`hl` |
| `web_search` | `deerflow.community.sofya.tools:web_search_tool` | 🆕 返回结果页正文，需 `SOFYA_API_KEY`，支持 `search_depth` |
| `web_search` | `deerflow.community.tencent_wsa.tools:web_search_tool` | 🆕 腾讯云 WSA，需 `TENCENTCLOUD_WSA_APIKEY` |
| `web_search` | `deerflow.community.tavily.tools:web_search_tool` | Tavily，需 `TAVILY_API_KEY` |
| `web_search` | `deerflow.community.infoquest.tools:web_search_tool` | InfoQuest，需 `INFOQUEST_API_KEY` |
| `web_search` | `deerflow.community.exa.tools:web_search_tool` | Exa，需 `EXA_API_KEY` |
| `web_search` | `deerflow.community.firecrawl.tools:web_search_tool` | Firecrawl，需 `FIRECRAWL_API_KEY`；🆕 自托管可设 `base_url` 免 key |
| `web_fetch` | `deerflow.community.jina_ai.tools:web_fetch_tool` | Jina AI，默认，免费 |
| `web_fetch` | `deerflow.community.sofya.tools:web_fetch_tool` | 🆕 返回 markdown，支持 PDF/DOCX |
| `web_fetch` | `deerflow.community.exa.tools:web_fetch_tool` | Exa |
| `web_fetch` | `deerflow.community.infoquest.tools:web_fetch_tool` | InfoQuest |
| `web_fetch` | `deerflow.community.firecrawl.tools:web_fetch_tool` | Firecrawl；🆕 自托管可设 `base_url` |
| `knowledge_search` | `deerflow.community.lightrag.tools:knowledge_search_tool` | 🆕 LightRAG（与 RAGFlow 同工具的第二 provider，二选一），需 v1.4.9+，`mode: naive/local/global/hybrid/mix` |
| `read_conversation` | `deerflow.tools.conversation:read_conversation` | 🆕 读取被显式引用的会话（Gateway API only，opt-in，run 需提交 `conversation_references`） |
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

## Tool Output & read_before_write（上下文成本工程）🔄 Sync #6

```yaml
tool_output:
  enabled: true
  elide_superseded_writes: true    # 🆕 同一路径被后续 read/write/str_replace 覆盖后，
                                   #    模型请求中旧 write_file 的 content 换成占位符
  superseded_write_min_chars: 2000 # 🆕 只剔除 ≥ 该字符数的 content（0 = 全剔除）
  keep_recent_writes: 1            # 🆕 最近 N 次成功 write_file 永不剔除（0 = 不保留）

read_before_write:
  enabled: true
  elide_blocked_payloads: true     # 🆕 被拦截调用（write content / str_replace old_str/new_str）
  elide_min_chars: 2000            #    在后续模型请求中替换为占位符（0 = 全剔除）
```

两者都只改**模型可见的请求**：存储历史、receipts、run journal 保留原始参数。字符数按 character 计（CJK 每字符成本是 ASCII 的 3-4 倍）。

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

### sandbox.network（出网管控）🆕

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  network:
    mode: allowlist              # open | isolated | allowlist（默认 open）
    allow_domains: [pypi.org, files.pythonhosted.org, registry.npmjs.org, github.com]
    approval: prompt             # deny | prompt（被拒公共域名可在 Human Input 卡片审批）
    temporary_grant_ttl: 300     # 30-3600 秒
    proxy_image: ghcr.io/bytedance/deer-flow-sandbox-network-proxy:latest
```

仅适用于本地管理的 Docker 沙箱：需要 Docker Engine 28+，**不支持 Apple Container 与 provisioner 模式**。`isolated` 拒绝一切出网；私有/回环/链路本地/多播/云 metadata 地址始终被拒。

### Provisioner 模式（K3s）

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  provisioner_url: http://provisioner:8002
```

### Tenki 沙箱（云端 Micro-VM）🆕

```yaml
sandbox:
  use: deerflow.community.tenki:TenkiSandboxProvider
  api_key: $TENKI_API_KEY     # 或 TENKI_AUTH_TOKEN 环境变量
  base_url: https://tenki.cloud
  # image: my-base-image
  # workspace_id: ws_...
  # ⚠️ Breaking (Sync #6)：`project_id` 已移除 — Tenki 1.x 删除了 projects，
  #    作用域只看 workspace。残留 project_id 被忽略并启动告警；
  #    账户有多个 workspace 时需显式设 workspace_id。
  # cpu_cores: 2
  # memory_mb: 2048
  replicas: 3                 # active + warm microVM 上限
  idle_timeout: 600           # warm microVM 闲置终止；0 禁用
  max_duration: 14400         # 沙箱生命周期（默认 4h）
  # sticky: false
  # home_dir: /home/tenki
  # environment: { ... }
```

Tenki 云 micro-VM（第 6 个沙箱 provider）。SDK 同步调用，懒加载（`deerflow-harness[tenki]` extra）。详见 [concepts/sandbox/abstract-interface-and-seven-impls.md](../../concepts/sandbox/abstract-interface-and-seven-impls.md)。

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

### subagent_runtime（进程级准入容量）🆕

```yaml
subagent_runtime:
  max_running: 3               # 进程内同时执行的 subagent 上限
  max_queued: 64               # 异步等待队列上限（排队不占执行线程）
  admission_policy: queue      # queue | reject（满员时排队或拒绝）
  queue_timeout_seconds: 300   # 排队超时
```

普通 `task` 调用与 durable batch **共享**这份进程级容量。字段为 restart-required（Gateway lifespan 启动时捕获）。

### subagent_batches（持久化原生 subagent 批）🆕

```yaml
subagent_batches:
  enabled: false               # 默认关闭：开启会显著增加模型用量，且需要 database.backend sqlite/postgres
  poll_interval_seconds: 1
  lease_seconds: 120
  max_items_per_batch: 5000
  default_max_live_items: 100
  max_live_items_per_batch: 1000
  default_max_running_items: 3
  max_running_items_per_batch: 64
  max_attempts: 3
  max_result_chars: 100000
  result_preview_max_chars: 2000
```

三个上限刻意分离：`total`（一批持久化的全部 item）、`live`（同一时刻 pending/queued/running 的准入量）、`running`（一批里真正占执行槽的 item）。字段为 restart-required。

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
  # path: /absolute/path/to/skills    # 覆盖 Skill 路径（也可用 DEER_FLOW_SKILLS_PATH 环境变量）
  container_path: /mnt/skills         # 沙箱中的虚拟路径（restart-required）
  deferred_discovery: false           # true = 系统提示只留 <skill_index> 名称，详情靠 describe_skill 工具按需取
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
    #   value: 0.8      # 模型最大输入的 80%（从 summary 模型声明的 context_window 解析；
    #                   # 第三方 OpenAI 兼容模型无内置 profile，缺 context_window 时
    #                   # 该 fraction 条款会被丢弃并告警，其余绝对阈值继续生效）
  keep:
    type: messages
    value: 10           # 保留最近 10 条消息
  trim_tokens_to_summarize: 15564
  summary_prompt: null
  # 旧 preserve_recent_skill_count / _tokens / _tokens_per_skill 已废弃（config.example.yaml
  # 明确标注 "no longer used"）；skill 保留改由 durable skill-reference channel 承担：
  skill_file_read_tool_names: [read_file, read, view, cat]   # set [] 关闭该捕获
```

## Memory（用户记忆）🔄 2.1 重构

```yaml
memory:
  enabled: true
  injection_enabled: true
  mode: middleware              # middleware（被动注入）| tool（模型主动调用工具）
  manager_class: deermem        # deermem | mem0 | noop | openviking | honcho | <custom>
  shutdown_flush_timeout_seconds: 30
  backend_config:               # 🆕 后端私有配置（替代旧的平铺字段）
    storage_path: ""            # 空 = runtime_home()；DIRECTORY（不是文件！）
    max_facts: 100
    fact_confidence_threshold: 0.7
    max_injection_tokens: 2000
    debounce_seconds: 30
    token_counting: tiktoken    # tiktoken | char
    guaranteed_categories: [correction]
    guaranteed_token_budget: 500
    # Staleness review
    staleness_review_enabled: true
    staleness_age_days: 90
    staleness_min_candidates: 3
    staleness_max_removals_per_cycle: 10
    staleness_protected_categories: [correction]
    staleness_max_lifetime_multiplier: 20.0
    staleness_max_extension_days: 3650
    # Consolidation
    consolidation_enabled: true
    consolidation_min_facts: 8
    consolidation_max_groups_per_cycle: 3
    consolidation_max_sources: 8
    # LLM
    model:
      model: null               # null = app default
      provider: openai
      api_key: null
      base_url: null
      temperature: null
```

> ⚠️ **Breaking Change (2.1)**：旧的平铺字段（`storage_path`, `max_facts`, `debounce_seconds` 等放在 `memory:` 下）已废弃。启动时自动迁移到 `backend_config` 并发出 warning。`storage_path` 从 FILE 路径变为 DIRECTORY 路径。

### Honcho（第 5 个 memory 后端）🆕

`manager_class: honcho` 走远程 HTTP adapter，用 Honcho 服务端 deriver 构建 user-model 记忆表示，**无本地 LLM 调用**（区别于 deermem 的本地提取）。每个 user id 一个隔离 workspace：

```yaml
memory:
  enabled: true
  manager_class: honcho
  mode: middleware        # middleware（被动注入）| tool（模型主动调用 memory_search）
  backend_config:
    base_url: http://localhost:8000
    # api_key: $HONCHO_API_KEY          # hosted Honcho；plain-http + api_key 需 allow_insecure_http: true
    workspace_prefix: deerflow-u-       # 每个 user id 一个隔离 workspace
    # workspace_overrides: {}           # 特定 user id → 自定义 workspace
    # user_peer_overrides: {}           # 特定 user id → 自定义 peer 名
    assistant_peer: deerflow
```

后端注册表位于 `deerflow/agents/memory/backends/`（`deermem`/`honcho`/`mem0`/`noop`/`openviking`），每个子目录暴露 `MANAGER_CLASS`。`manager_class` 可以是这些注册名之一，也可以是一个 `MemoryManager` 子类的 dotted import path。

## Projects（项目工作区）🆕

```yaml
projects:
  instructions_max_bytes: 8192       # 项目 instructions UTF-8 字节上限（256-262144）
  shelf_index_max_entries: 50        # <documents> 索引每次 run 渲染的条目上限（1-500）
  shelf_index_max_bytes: 4096        # <documents> 索引渲染的 UTF-8 字节上限（512-65536）
  trash_retention_days: 30           # 回收站文档保留天数（1-3650）
```

Member thread 每次 run 收到请求级 `<project>` / `<documents>` 块，由 run 准入时 pin 的快照渲染，不进 system prompt 也不进持久化历史。超限 instructions 写入时直接 422，不会截断。

## task_continuity（任务笔记与压缩消息召回）🆕

```yaml
task_continuity:
  enabled: false                     # opt-in
  max_batches: 32
  max_records_per_batch: 256
  max_record_chars: 16000
```

可选的任务笔记 + 对已压缩（summarized）消息的关键词召回，详见上游 `docs/task-continuity.md`。

## Stream Bridge（心跳间隔）🔄 Sync #6

`stream_bridge`（memory / redis 两种 backend）均支持 `heartbeat_interval_seconds: 15`（上限 86400）：SSE、wait 及内部 stream 消费者的空闲心跳间隔。redis 模式下每个 SSE 客户端阻塞在 `XREAD ... BLOCK <heartbeat_interval>`，并发客户端多时调小可减少挂起的 redis 连接。

## Authorization（授权）🆕

```yaml
authorization:
  enabled: false                    # 默认关闭（向后兼容）
  fail_closed: true                 # provider 异常/未知身份 → deny
  default_role: user                # user_role 为 None 时回退
  provider:
    use: deerflow.authz.rbac:RbacAuthorizationProvider
    config:
      roles:
        admin:
          tools: {allow: "*"}
          routes: {allow: "*"}
        user:
          tools: {allow: "*", deny: ["update_agent"]}
          routes: {allow: "*"}
        guest:
          tools: {allow: ["web_search", "read_file"]}
          routes: {allow: ["threads:read", "runs:read"]}
```

可插拔鉴权（AuthorizationProvider + 内置 RBAC）详见 [enterprise-operations/security/01-auth.md](../../enterprise-operations/security/01-auth.md)。配置可热更新。

### auth.local（登录限流）🔄 Sync #6

```yaml
auth:
  local:
    # max_login_attempts: 5     # 每 client IP 失败上限（最低 2）
    # lockout_seconds: 300      # 锁定时长
```

按 client IP 的进程内登录节流，默认保持历史硬编码策略（5 次 / 5 分钟）。**live-read**：改配置无需重启 Gateway——调低 `lockout_seconds` 立即释放活跃锁；调高只延长未过期锁，不会复活已过期锁。共享出口 IP（公司 NAT）场景可调高 `max_login_attempts`。

## Database（数据库/持久化）

```yaml
database:
  backend: sqlite            # memory | sqlite | postgres
  sqlite_dir: .deer-flow/data
  postgres_url: $DATABASE_URL
  postgres_schema: ""        # 空=服务端默认 search_path；只允许小写 plain identifier
  checkpoint_channel_mode: full   # full | delta（restart-required）
  checkpoint_delta:
    snapshot_frequency: 10   # delta 快照节奏（restart-required）
  checkpoint_graph_cache:
    accessor_graph_max: 64   # Gateway accessor 图缓存上限（唯一热重载的 checkpoint_* 项）
  checkpoint_cache:          # delta 模式专有；纯性能，跨进程可不同
    type: memory             # memory | redis（sync/TUI 路径拒绝 redis）
    max_entries: 128         # 0 = 关闭缓存
    redis_url: null          # 缺省回落 DEER_FLOW_CHECKPOINT_CACHE_REDIS_URL → REDIS_URL → redis://localhost:6379/0
    ttl_seconds: 86400       # 泄漏兜底，不是正确性机制；0 = 显式不过期
    key_prefix: ""           # 缺省 = ckpt-hist:v1:<部署身份 hash>
```

**checkpoint_channel_mode（🆕 v2.1.0 起的一等配置）**：`full` 存整快照 `channel_values`；`delta` 对累积 channel（`messages`）改用 LangGraph `DeltaChannel`（哨兵 blob + 每步 writes，每 `snapshot_frequency` 步落一次全量快照）。模式与节奏**都被编译进图的 channel 表**，所以：restart-required、共享同一 checkpoint 库的所有进程必须同值、迁移方向只有 `full → delta`。legacy 扁平键 `checkpoint_delta_snapshot_frequency` 会被自动搬到 `checkpoint_delta.snapshot_frequency`（不搬的话旧 YAML 会**静默**退回新默认节奏）。完整契约（进程冻结、`deerflow_checkpoint_channel_mode` 元数据标记、full 进程读 delta thread 的 fail-closed 报错、`CheckpointStateAccessor`、delta 历史缓存后端）见 [../persistence/checkpoint-dual-mode-and-history-cache.md](../persistence/checkpoint-dual-mode-and-history-cache.md)。

三个选项：
- **memory** — 进程内，无持久化，重启丢失
- **sqlite**（默认） — 单机，WAL 模式
- **postgres** — 多 worker 生产，需安装 `[postgres]` extra

**注意**：`database.*`、`checkpointer.*` 等基础设施字段改后需重启才生效（见 `CLAUDE.md` 热加载表）。

**迁移**：`database.backend` 为 sqlite/postgres 时，Gateway 启动会在 `init_engine` 里自动跑 `persistence/bootstrap.py::bootstrap_schema()`（空库 `create_all` + `stamp head`；legacy 库只回填 baseline 表再 `upgrade head`；已版本化库直接 `upgrade head`），日常升级不需要手工执行 alembic。revision 从 `0001_baseline` 串到当前 head **`0048_extension_execution_leases`**（50 个 revision，`persistence/migrations/versions/`）；未知 revision、空版本表或多行版本表会拒绝启动。见 [internals/persistence/db-checkpointer-store-backends.md](../persistence/db-checkpointer-store-backends.md)。

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

详见 [enterprise-operations/integration/04-im-channels.md](../../enterprise-operations/integration/04-im-channels.md)。

## Verification（tool 结果确定性收据）🆕

```yaml
verification:
  receipts_enabled: true                # 把确定性收据盖章到 tool 结果并注入模型上下文
  receipts_render_mode: "delegation_only"  # 只在处理 subagent 结果时渲染 lead-chain ledger
  judge_enabled: false                  # 验收标准 judge，默认关闭（保留给 acceptance-criteria review）
  judge_model_name: null
```

收据让最终报告能引用实际执行过的动作。`receipts_render_mode=delegation_only` 下，subagent chain 始终渲染，lead 链只在处理 subagent 结果时渲染。

## Scheduler（后台定时任务）🆕

```yaml
scheduler:
  enabled: false               # 后台 poller 主开关
  multi_instance: false        # 跨 Gateway 实例的 lease 感知恢复（需共享 Postgres + run ownership + db run_events）
  poll_interval_seconds: 5
  lease_seconds: 120           # claim lease；崩溃进程的任务此后可被回收
  max_concurrent_runs: 3       # 全局 launching/running 上限（multi-instance 下为共享 global cap）
  queue_timeout_seconds: 3600
  min_once_delay_seconds: 60
  recursion_limit: 1000        # 定时 run 的 LangGraph super-step 上限（匹配 web UI，被 max_recursion_limit 钳制）
```

poller 字段（`enabled`/`multi_instance`/`poll_interval_seconds`/`lease_seconds`/`max_concurrent_runs`/`min_once_delay_seconds`）为 restart-required。**例外**：`recursion_limit` 在每次 dispatch 时从 `get_app_config()` 读取，改 YAML 后下一个定时 run 即生效，无需重启 poller。调度类型现为 🔄 一次性 + cron + interval；`min_once_delay_seconds` 同时是一次性 `run_at` 与 interval `every_seconds` 的下限。

## mcp_tasks（长时 MCP 任务持久化）🆕

```yaml
mcp_tasks:
  enabled: false               # 后台状态 poller 主开关
  poll_interval_seconds: 5
  lease_seconds: 120
  max_concurrent_polls: 8
  max_poll_backoff_seconds: 300
  input_required_poll_interval_seconds: 60
  tracking_degraded_after_errors: 3
  max_result_bytes: 65536
  result_preview_max_chars: 2000
```

持久化运行时承载普通 MCP submit/status/cancel 工具集；`task_toolsets` 按 server 在 `extensions_config.json` 里配置。所有字段 restart-required（Gateway lifespan 启动时捕获）。

## llm_call（LLM 并发与重试整形）🆕

```yaml
llm_call:
  max_concurrent_calls: 0        # 进程内同时在飞的 LLM 调用上限；0 = 不限制（默认）
  retry_max_attempts: 3          # 可重试暂态错误的最大尝试次数（1 = 不重试）
  retry_base_delay_ms: 1000      # decorrelated-jitter 退避基数
  retry_cap_delay_ms: 8000       # 单次退避硬上限
  burst_retry_base_delay_ms: 5000  # provider 突发限流（limit_burst_rate）429 的退避基数
```

- 与 `circuit_breaker`（处理**已失败**的 provider）、`models[].request_admission`（per-model RPM）正交：这一节管的是"同时跑多少、退避怎么走"。限并发等于压住请求速率的**斜率**，而 provider 的突发速率限制正是打在斜率上的。
- **`max_concurrent_calls` 是 startup-only**：上限在第一次 LLM run 时被捕获并冻结到进程生命周期——一个进程级、跨 loop 的限制器如果在运行时可变，会引入缩容/配置新鲜度竞态。改它必须重启 Gateway；`llm_call.*` 的其它字段仍热重载。
- **进程内、不是集群级**：`GATEWAY_WORKERS > 1` 时实际总上限是 `max_concurrent_calls × worker 数`（多节点再乘）。要真正的集群级斜率上限，得配一个 nginx `limit_req`。

## run_ownership（多 worker run 租约）

```yaml
run_ownership:
  lease_seconds: ...        # run lease 时长
  grace_seconds: ...        # 租约宽限（回收过期 lease、判定孤儿 run 用）
  heartbeat_enabled: false  # 是否启用心跳续租
```

`heartbeat_enabled=true` 是 `scheduler.multi_instance=true` 的前置条件之一（另两个：共享 Postgres、`run_events.backend=db`），否则启动直接拒绝该组合。scheduler digest 里的租约回收/接管语义见 [../../enterprise-operations/scheduler.md](../../enterprise-operations/scheduler.md)。restart-required。

## dedupe_storage（入站 webhook 去重存储）🆕

```yaml
dedupe_storage:
  backend: auto     # auto | memory | postgres
```

ChannelManager 的入站去重状态放哪（issue #4120 的跨 pod 去重）：

| 值 | 行为 |
|----|------|
| `auto`（默认） | `database.backend=postgres` 时用共享 Postgres 应用库；否则进程内 memory（单 pod） |
| `memory` | 强制进程内 store——**per-pod，不跨副本共享**；`GATEWAY_WORKERS>1` 时会记 warning（跨 pod 重投不会被去重） |
| `postgres` | 用应用库跨 pod 共享；但 `database.backend != postgres` 时**降级**回 memory 并记 warning |

解析逻辑在 `app/channels/dedupe_store.py`，每种降级都有明确日志。

## agent_storage（自定义 Agent SOUL 存哪）🆕

```yaml
agent_storage:
  backend: file     # file | db
```

`file` = 每个自定义 agent 一个 SOUL 文件；`db` = 走 `persistence/agents/` 的 `agents` 表（`AgentRow`，`migration 0006_agents`）。两条实现路径分别是 `persistence/agents/file.py::FileAgentStore` 与 `sql.py::SqlAgentStore`，入口是 `get_agent_store()` / `make_agent_store()`。

## skill_scan（原生技能安全扫描）🆕

```yaml
skill_scan:
  enabled: ...
```

`skills/skillscan/` 的原生确定性扫描开关（`SkillScanConfig`）。它与 skill-reviewer skill 的 `review_skill_package` 路径不是同一套：前者是 harness 侧静态规则扫描（`SecurityFinding`/`ScanResult`/`RuleSpec`），后者是技能质量审查契约。

## suggestions（回复后追问建议）🆕

```yaml
suggestions:
  enabled: true           # 是否在 AI 回复末尾生成 follow-up 追问建议
  max_suggestions: ...
```

前端通过 `POST /api/threads/{thread_id}/suggestions` 生成、`GET /api/suggestions/config` 读配置（没有 `GET /api/suggestions` 这个端点）。

## input_polish（发送前润色）🆕

```yaml
input_polish:
  enabled: true       # composer 的 pre-send 润色
  max_chars: 4000     # 草稿字符上限（≥1）
  model_name: null    # 可选模型覆盖；缺省用默认模型
```

`POST /api/input-polish` 是一次性 LLM 调用，**不创建 run**，也不写 thread 状态。

---

## 🆕 blob_storage（内容寻址对象存储）

```yaml
blob_storage:                  # config.example.yaml:2563
  enabled: false               # 总开关；producer 迁移未完成前是惰性的
  backend: local_fs            # storage/backends/<name>/ 目录名，或 BlobStore 子类的点分导入路径
  backend_config: {}           # 原样交给后端；local_fs 读 `root`，空则 {runtime_home}/blobs
```

**为什么是内容寻址**：内容按 `sha256` 寻址，所以写入天然幂等、相同字节自动去重成一个对象、读取时校验摘要。这是 `tool_artifacts` 之类"同一份大产物被多次引用"场景的地基。

- 后端解析与 memory 后端**同构**：`backend` 名字匹配 `storage/backends/<name>/` 下暴露 `STORE_CLASS` 的目录（如 `local_fs`），或给一个点分导入路径。工厂在 `get_blob_store()` 时解析并**快速失败**——blob 是持久状态，一个拼错的后端名绝不能悄悄把存储位置换掉。
- 多实例部署要把 `backend_config.root` 指向共享卷（NFS / EFS / ReadWriteMany PVC）。
- **自愈**：`get_blob_storage_config()`（`config/blob_storage_config.py:61`）发现 `_app_config` 已被设置时会主动调 `get_app_config()` 重新取，避免"配置对象已建但 blob 单例还是空"的窗口。
- 单例注入在 `_apply_singleton_configs()`（`config/app_config.py:548`，blob_storage 分支在 `:556`）里随每次 reload 一起刷新。
- 契约与两个已登记 producer、迁移顺序见 `backend/docs/blob-storage.md`。

## 🆕 knowledge_base（知识库能力门控）

```yaml
knowledge_base:                # config.example.yaml:824
  enabled: false               # knowledge 组的整组开关
  scope_selection_enabled: false
```

```python
class KnowledgeBaseConfig(BaseModel):        # config/knowledge_base_config.py
    model_config = ConfigDict(validate_default=True)
    enabled: bool = False
    scope_selection_enabled: bool = False
```

两个字段的分工是刻意分开的：

- `enabled` 控制 `group: knowledge` 的**工具是否出现在 agent 的工具表里**。`get_available_tools()` 在 `knowledge_base.enabled` 为假时把整组过滤掉（`tools/tools.py:155-157`）。provider 的连接与检索参数**不在**这一段，它们留在各自 `tools[]` 条目上（例如 `use: deerflow.community.ragflow.tools:knowledge_search_tool` 的 `base_url` / `datasets` / `page_size`）。
- `scope_selection_enabled` 只影响**自定义 agent 聊天**：它决定要不要显示知识范围选择器，且**仅当**实际生效的 `knowledge_search` provider 是内置 RAGFlow 工具时才生效（`/api/features` 的 `knowledge_base` 字段由 `app/gateway/routers/features.py` 的 `_knowledge_scope_selection_enabled` 计算）。

`enabled` 是热加载字段：tool 列表每次装配都重读，改完不用重启。config_version 升到 45 时这条语义被回填迁移，见"配置版本"一节。

## 🆕 typesafe（Jev 客户端默认值）

```yaml
typesafe:                      # config.example.yaml:3347
  api_key_env: TYPESAFE_API_KEY   # 默认；存 key 的环境变量名
  # api_key: <explicit key>       # 与 api_key_env 二选一（同层内 api_key 优先）
  base_url: https://api.typesafe.ai   # 默认；只允许 http(s)，不得带 query/fragment/内嵌凭据
  model: jev-latest               # 默认；生产建议钉死版本
  timeout: 5.0                    # 单请求超时（秒）
  deadline_seconds: 10.0          # 整次评估预算（秒）
  max_attempts: 2                 # 含首次；只对 429/529 与传输错误重试
  retry_backoff: 0.5              # 指数退避的基准秒数
```

这是 TypeSafe 所有消费者的**共享默认层**：guardrail 风险闸（`guardrails.provider.config`）以及将来的 memory 预筛与信号分类。优先级恒为 **消费者自己的 `config` > `typesafe` 块 > 内置默认**。

刻意**不**放在这里的东西：失败策略（闸门出错即拒，memory 路径继续跑）、缓存设置、阈值、问题内容——那些属于各消费者自己，两个阈值不同的消费者仍可共享一次请求，各自发布自己的策略身份。

校验时机是**构建消费者时**，不是首次调用时：

| 情况 | 结果 |
|------|------|
| `base_url` 非 http(s) / 带 query / 带 fragment / 内嵌凭据 | 配置错误 |
| key 前后有空白（典型：从文件挂载的 secret 带换行） | 配置错误 |
| key 含不可打印字符 | 配置错误 |
| 数值写成 `true` 之类（严格校验） | 报错而不是静默读成 `1` |

`TYPESAFE_API_KEY` 这个默认变量名定义在 `typesafe/connection.py` 的 `DEFAULT_API_KEY_ENV`，单例读取走 `config/typesafe_config.py` 的 `get_typesafe_config()`（`:55`），注入点在 `_apply_singleton_configs()` 的 `:561`。

## 🆕 deployment（多实例拓扑声明）

```yaml
deployment:                    # config.example.yaml:2923
  multi_instance: false        # restart required；每个实例必须一致
```

**为什么需要显式声明**：`GATEWAY_WORKERS` / `WEB_CONCURRENCY` 只数**一个进程树内**的 uvicorn worker。Kubernetes  Deployment `replicas: 3`（每 Pod 一个 worker）对启动安全闸门**完全不可见**——每个 Pod 都能通过全部检查，然后它的启动期孤儿回收会在每次滚动更新时把别的 Pod 的**无租约 run 全部写成 crashed**。

`multi_instance: true`（或环境变量 `DEER_FLOW_MULTI_INSTANCE=1`，值集合 `{"", "0", "false", "no", "off"}` 视为假，判定在 `config/deployment_config.py:26` 附近）时，启动闸门**要求**：

| 必需 | 说明 |
|------|------|
| `database.backend: postgres` | 共享库 |
| `run_events.backend: db` | 事件必须落库 |
| `run_ownership.heartbeat_enabled: true` | 要有租约心跳 |
| Redis stream bridge | 跨 worker 的事件桥 |

并**拒绝**：显式 `sandbox.ownership.type: memory`、进程内 browser 工具、`scheduler.enabled: true` 而 `scheduler.multi_instance` 未开、以及除 GitHub 外有 IM 通道启用时 `channels.leader_lease.enabled: false`。

这段被登记为 `startup-only`（`config/reload_boundary.py` 的 `deployment` 条目）：`langgraph_runtime()` 只在启动时评估一次，声明或撤回多实例拓扑要在**每个实例**上重启。

## 🆕 pii_redaction / tool_artifacts

```yaml
pii_redaction: ...             # config.example.yaml:1537 —— 出站 PII 脱敏规则
tool_artifacts: ...            # config.example.yaml:1461 —— 大工具产物外置成 artifact 引用
```

`tool_artifacts` 把超出内联预算的工具结果搬到 artifact 存储里，模型看到的是引用而不是正文；它与 `blob_storage` 同属"内容外置"这一条线。`pii_redaction` 是独立的一层，在模型调用**之前**按规则脱敏。两者都是热加载字段（每次装配/每次调用重读），完整字段见 `config.example.yaml` 对应行段的注释与 `backend/docs/CONFIGURATION.md`。

## 🆕 agents_api / lead_prompt_overlay

```yaml
agents_api:                    # config.example.yaml:2580
  enabled: false               # 自定义 Agent 的 SOUL/USER.md 管理 API
```

`agents_api.enabled` 控制 HTTP Gateway 是否暴露自定义 agent 的 SOUL / USER.md 管理端点。**除非 Gateway 位于可信的已认证管理员边界之后，否则保持关闭**——这些端点改写的是 agent 的人格定义。

`lead_prompt_overlay` 是**运营方字面量**的 lead-agent system prompt 前后缀（`config.example.yaml:26`）：

```yaml
lead_prompt_overlay:
  prepend: "Apply our organization-wide writing conventions."
  append: "End reports with a concise decision summary."
```

`PromptOverlay`（`config/prompt_overlay.py:6`）是 `extra="forbid"`、两个字段都 `strict=True` 的模型，`apply()` 用空行把 `prepend` / 原 prompt / `append` 串起来，空串会被跳过。同一机制的另外两个落点写在同一处注释里：`subagents.agents.<name>.prompt_overlay.{prepend,append}` 与 DeerMem 的 `memory.backend_config.{prompt_prepend,prompt_append}`。它不改引擎的 system prompt 常量，只在装配时包裹，因此**每次构建 agent 都重读 → 热生效**。

---

## 配置热加载备忘

**真值来源是代码**：`config/reload_boundary.py::STARTUP_ONLY_FIELDS`（`config/reload_boundary.py:45`，共 **27** 条）是热加载边界的**单一来源**，且被 `test_reload_boundary` 双向钉住——注册过的字段在 schema 里必须带 `startup-only:` 前缀，带该前缀的字段必须在注册表里。下面这张表是它的可读镜像（字段级理由见 [../harness-hooks/02-singleton-propagation.md](../harness-hooks/02-singleton-propagation.md)）：

| 需重启（`STARTUP_ONLY_FIELDS`） | 无需重启（`get_app_config()` 每次请求重读） |
|--------------------------------|------------------------------------------|
| `plugins`（`load_extensions()` 只在 `create_app()` 跑一次） | `models`（列表 / 参数）· `summarization` · `title` · `memory` |
| `database`（engine + 连接池，`langgraph_runtime()` 启动时建一次） | `tools[*]` · `tool_groups` · `tool_search` · `tool_output` · `tool_progress` |
| `checkpointer` · `run_events` · `stream_bridge` | `subagents.*` · `subagent_runtime`（见右栏例外说明） · `authorization` |
| `sandbox` · `skills.container_path` | `guardrails` · `verification` · `read_before_write` · `safety_finish_reason` |
| `log_level` · `logging`（`configure_logging()` 只在 startup 跑） | `loop_detection` · `token_budget` · `token_usage` · `circuit_breaker` |
| `channels` · `channel_connections` | system prompt（每次构建 agent 重新生成） |
| `scheduler`（`recursion_limit` **除外**，每次 dispatch 重读） | `projects` · `suggestions` · `input_polish` · `title` 等 per-run 字段 |
| `mcp_tasks` · `subagent_batches` · `run_ownership` · `dedupe_storage` | `skills.*`（**除** `container_path`）· `auth.local.max_login_attempts` / `lockout_seconds`（逐次登录 live-read） |
| 🆕 `channels.leader_lease`（多进程启动闸门 + `ChannelService` 构造时捕获） | 🆕 `knowledge_base.enabled`（每次装配 tool 列表时读） |
| 🆕 `deployment`（`langgraph_runtime()` 的多进程安全闸门只评一次） | 🆕 `tool_artifacts` · `pii_redaction` · `agents_api` · `skill_evolution` |
| 🆕 `auth.local.throttle_storage`（登录限流存储启动时解析一次） | 🆕 `blob_storage`（`_apply_singleton_configs` + 自愈） |
| 🆕 `projects.summaries_enabled` / `summary_max_bytes` / `summary_model_name` / `summary_concurrency` / `summary_queue_size` / `summary_timeout_seconds` | `projects` 其余字段（工作区路径 / 开关） |
| `agent_storage`（与 `database.backend` 的匹配在 startup 校验一次） | `database.checkpoint_graph_cache.accessor_graph_max` · `database.checkpoint_cache.*`（delta 缓存两处刻意可热改） |
| `llm_call.max_concurrent_calls`（首次 LLM run 冻结；该字段**不在**注册表里，靠自身 schema 文档声明） | `llm_call.*` 其余字段（重试/退避）· `extensions.middlewares`（下次 agent 构建） |

**三个反直觉点**：

1. `database` 整段被登记为 restart-required（理由是 engine/连接池），但 `database.checkpoint_graph_cache.accessor_graph_max` 与 `database.checkpoint_cache.*` 是**刻意的例外**——前者在每次淘汰检查时从新 `AppConfig` 重读，后者是纯性能、跨进程都可不同、从不被冻结。
2. `checkpointer.*` 变化时 `_apply_singleton_configs()`（`config/app_config.py:548`）会 `reset_checkpointer()` + `reset_store()`，但这**不是完整热重载**：已开始的 run 在 run 起点拿到 checkpointer/store，感知不到中途 reset；只有新 run 用新的。
3. 🆕 `scheduler` 整段要重启，**唯独 `scheduler.recursion_limit` 例外**——`launch_scheduled_thread_run` 每次 dispatch 都从 `get_app_config()` 重读，改 YAML 下一次定时运行就生效（注册表理由文本写死在 `config/reload_boundary.py:81-83`）。同理 `auth.local.throttle_storage` 要重启，但 `auth.local.max_login_attempts` / `lockout_seconds` 仍逐次 live-read。

---

# extensions_config.json

```json
{
  "middlewares": [
    "my_company.deerflow_middlewares:DomainGuardMiddleware",
    { "class": "my_company.deerflow_middlewares:LatencyStampingMiddleware",
      "kwargs": { "header": "X-DeerFlow-Latency" } }
  ],
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

- `middlewares`：`AgentMiddleware` 条目（class path 或 `{class, kwargs}`），作用于 lead 与 subagent 运行时；`config.yaml -> extensions.middlewares` 可覆盖同名字段（replace-per-field）
- `mcpInterceptors`：自定义 MCP tool 拦截器 class path 列表（字符串或字符串数组）。不在 `ExtensionsConfig` schema 里，经 `extra="allow"` 落在 `model_extra`，由 `mcp/interceptors.py:47-53` 解析并追加到内置 OAuth/user-scoped/context-headers 拦截器之后
- `mcpServers`：MCP 服务器配置，type 可为 `stdio` / `sse` / `http`
  - SSE/HTTP 支持 OAuth（client_credentials、refresh_token 自动刷新）
- `skills`：Skill 的启用/禁用状态
  - Key 为 Skill 名称（与 `SKILL.md` frontmatter 中 `name` 一致）
  - 运行时通过 `POST /api/skills/install` 安装 .skill zip 会自动追加

两个文件都支持通过 Gateway API 运行时修改（`PUT /api/mcp/config`、`PUT /api/skills/{name}`）。

---

## 附：v2.2.0 补充子键（25 个）

以下子键在 v2.2.0 的 `config.example.yaml` 中存在，但未在前文逐段展开；默认值与行号以该文件为准。

| 键 | 默认值 | 作用 | `config.example.yaml` |
|---|---|---|---|
| `logging.enhance.format` | `text` | trace 增强日志格式（`text` / `json`） | `:55` |
| `token_budget.max_input_tokens` | `null` | 可选的输入侧单独上限；null 表示只受总预算约束 | `:108` |
| `token_budget.max_output_tokens` | `null` | 可选的输出侧单独上限 | `:109` |
| `token_budget.hard_stop_threshold` | `1.0` | 达到预算的该比例即强制停止 | `:111` |
| `tool_search.auto_promote_top_k` | `3` | 自动晋升 deferred tool 的 top-k | `:1400` |
| `tool_output.externalize_min_chars` | `12000` | 超过该字符数的 tool 结果外置到磁盘 | `:1423` |
| `tool_output.preview_head_chars` | `2000` | 外置结果预览头部字符数 | `:1426` |
| `tool_output.preview_tail_chars` | `1000` | 外置结果预览尾部字符数 | `:1427` |
| `tool_output.fallback_max_chars` | `30000` | 无法外置时的兜底截断上限 | `:1428` |
| `tool_output.fallback_head_chars` | `8000` | 兜底截断保留的头部字符数 | `:1429` |
| `tool_output.fallback_tail_chars` | `3000` | 兜底截断保留的尾部字符数 | `:1430` |
| `tool_output.storage_subdir` | `.tool-results` | 外置结果在 thread 数据目录下的子目录 | `:1431` |
| `tool_output.exempt_tools` | `["read_file","read_file_tool"]` | 永不外置的工具名 | `:1432` |
| `tool_artifacts.detect_refs_in_text` | `true` | 从文本中检测 artifact 引用 | `:1467` |
| `tool_artifacts.inject_model_context` | `true` | 把 artifact handle/元数据注入模型上下文 | `:1469` |
| `tool_artifacts.resolve_handles_in_args` | `true` | 执行前置解析 tool-call 参数里的 artifact handle | `:1471` |
| `projects.search_max_chars_per_document` | `1000000` | 单项目文档进入检索上下文的最大字符数 | `:1646` |
| `projects.search_max_total_chars` | `8000000` | 项目文档检索的总字符上限 | `:1647` |
| `sandbox.prewarm` | `false` | 是否为 AIO 沙箱做投机式预热 | `:1723` |
| `sandbox.prewarm_max_concurrent` | `1` | 预热并发上限 | `:1727` |
| `sandbox.bash_command_timeout` | `600` | bash 命令硬超时（秒） | `:1763` |
| `skill_evolution.security_fail_closed` | `true` | 审核模型不可用时是否 fail-closed（阻止写入） | `:2590` |
| `database.pool_recycle` | `300` | 连接池 recycle 秒数 | `:2738` |
| `database.command_timeout` | `30` | 数据库命令超时（秒） | `:2741` |
| `scheduler.max_concurrent_runs_per_user` | `2` | 每个 owner 的调度 run 并发上限（0=关闭） | `:2869` |
