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
| `config.yaml` | 主配置（2900+ 行） | `make config` 从 `config.example.yaml` 生成 |
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
config_version: 45
```

用于检测配置过期。改 schema 时上游会升这个数字。`make config-upgrade` 把新字段合并到已有 `config.yaml`。

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

可插拔鉴权（AuthorizationProvider + 内置 RBAC）详见 [operations/security/01-auth.md](../../operations/security/01-auth.md)。配置可热更新。

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

**迁移**：`database.backend` 为 sqlite/postgres 时，Gateway 启动会在 `init_engine` 里自动跑 `persistence/bootstrap.py::bootstrap_schema()`（空库 `create_all` + `stamp head`；legacy 库只回填 baseline 表再 `upgrade head`；已版本化库直接 `upgrade head`），日常升级不需要手工执行 alembic。revision 从 `0001_baseline` 串到当前 head **`0025_repair_run_change_seq`**（`persistence/migrations/versions/`）；未知 revision、空版本表或多行版本表会拒绝启动。见 [internals/persistence/db-checkpointer-store-backends.md](../persistence/db-checkpointer-store-backends.md)。

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

详见 [operations/integration/04-im-channels.md](../../operations/integration/04-im-channels.md)。

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

`heartbeat_enabled=true` 是 `scheduler.multi_instance=true` 的前置条件之一（另两个：共享 Postgres、`run_events.backend=db`），否则启动直接拒绝该组合。scheduler digest 里的租约回收/接管语义见 [../../operations/scheduler.md](../../operations/scheduler.md)。restart-required。

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

## 配置热加载备忘

**真值来源是代码**：`config/reload_boundary.py::STARTUP_ONLY_FIELDS`（18 条）是热加载边界的**单一来源**，且被 `test_reload_boundary` 双向钉住——注册过的字段在 schema 里必须带 `startup-only:` 前缀，带该前缀的字段必须在注册表里。下面这张表是它的可读镜像（字段级理由见 [../harness-hooks/02-singleton-propagation.md](../harness-hooks/02-singleton-propagation.md)）：

| 需重启（`STARTUP_ONLY_FIELDS`） | 无需重启（`get_app_config()` 每次请求重读） |
|--------------------------------|------------------------------------------|
| `plugins`（`load_extensions()` 只在 `create_app()` 跑一次） | `models`（列表 / 参数）· `summarization` · `title` · `memory` |
| `database`（engine + 连接池，`langgraph_runtime()` 启动时建一次） | `tools[*]` · `tool_groups` · `tool_search` · `tool_output` · `tool_progress` |
| `checkpointer` · `run_events` · `stream_bridge` | `subagents.*` · `subagent_runtime`（见右栏例外说明） · `authorization` |
| `sandbox` · `skills.container_path` | `guardrails` · `verification` · `read_before_write` · `safety_finish_reason` |
| `log_level` · `logging`（`configure_logging()` 只在 startup 跑） | `loop_detection` · `token_budget` · `token_usage` · `circuit_breaker` |
| `channels` · `channel_connections` | system prompt（每次构建 agent 重新生成） |
| `scheduler`（`recursion_limit` **除外**，每次 dispatch 重读） | `projects` · `suggestions` · `input_polish` · `title` 等 per-run 字段 |
| `mcp_tasks` · `subagent_batches` · `run_ownership` · `dedupe_storage` | `skills.*`（**除** `container_path`）· `auth.local` 限流（逐次登录 live-read） |
| `agent_storage`（与 `database.backend` 的匹配在 startup 校验一次） | `database.checkpoint_graph_cache.accessor_graph_max` · `database.checkpoint_cache.*`（delta 缓存两处刻意可热改） |
| `llm_call.max_concurrent_calls`（首次 LLM run 冻结；该字段**不在**注册表里，靠自身 schema 文档声明） | `llm_call.*` 其余字段（重试/退避）· `extensions.middlewares`（下次 agent 构建） |

**两个反直觉点**：

1. `database` 整段被登记为 restart-required（理由是 engine/连接池），但 `database.checkpoint_graph_cache.accessor_graph_max` 与 `database.checkpoint_cache.*` 是**刻意的例外**——前者在每次淘汰检查时从新 `AppConfig` 重读，后者是纯性能、跨进程都可不同、从不被冻结。
2. `checkpointer.*` 变化时 `_apply_singleton_configs()` 会 `reset_checkpointer()` + `reset_store()`，但这**不是完整热重载**：已开始的 run 在 run 起点拿到 checkpointer/store，感知不到中途 reset；只有新 run 用新的。

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
