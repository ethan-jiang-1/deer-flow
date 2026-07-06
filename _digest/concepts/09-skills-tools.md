# Skills 与 Tool 系统

## Skills 系统

Skills 是可复用、可组合的 Agent 能力模块。每个 Skill 是一个包含 `SKILL.md` 的目录。

### 目录结构

```
skills/
├── public/                          # 已提交到 Git（18 个）
│   ├── deep-research/
│   │   └── SKILL.md
│   ├── data-analysis/
│   │   └── SKILL.md
│   ├── chart-visualization/
│   │   └── SKILL.md
│   └── ...
└── custom/                          # gitignored，用户/Agent 安装
    └── my-custom-skill/
        └── SKILL.md
```

### SKILL.md 格式

```markdown
---
name: deep-research
description: Deep research on any topic
license: MIT
allowed-tools: [web_search, web_fetch, read_file, write_file]
---

# Deep Research Skill

Instructions for conducting deep research...
```

YAML frontmatter:
- `name` — 唯一标识，用于配置中引用
- `description` — 简述，显示在 UI
- `license` — 许可证
- `allowed-tools` — 工具白名单（可选，限制该 Skill 可用工具）
- `version`、`author`、`compatibility` — 可选元数据（安装时提供）

### 加载流程

```
LocalSkillStorage.load_skills()
    │  (在 asyncio.to_thread 中运行，避免阻塞 event loop)
    │  递归扫描 skills/{public,custom} 寻找 SKILL.md
    │
    ├── 解析 YAML frontmatter
    ├── 读取 extensions_config.json 的启用状态
    └── 返回 List[Skill]
```

**热加载**：`get_or_new_skill_storage()` 检测 `extensions_config.json` mtime 变化后重建 storage。

### 注入 Agent

```
apply_prompt_template()
    │
    ├── 过滤出 enabled skills
    ├── 应用 per-agent skill 过滤（custom agent 的 skills 白名单）
    └── 将 skill 名称、描述、container_path 嵌入 system prompt
```

### Per-Agent Skill 控制

Custom agent 的 `config.yaml`：
```yaml
# null 或不存在 → 继承所有全局启用的 skills（默认）
# [] → 禁用所有 skills
# ["deep-research", "data-analysis"] → 仅加载指定 skills
skills: ["deep-research"]
```

### Skill 自进化（Skill Evolution）

```yaml
skill_evolution:
  enabled: false
  moderation_model_name: null
```

默认禁用。启用后 Agent 可以通过工具在 `skills/custom/` 下创建/改进 Skill。
`moderation_model_name` 指定的模型用于安全扫描新/修改的 Skill。

### Skill 安装 API

`POST /api/skills/install` 接受 `.skill` ZIP 压缩包：
1. 解压到 `skills/custom/{name}/`
2. 添加启用状态到 `extensions_config.json`
3. 下次 skill storage reload 时生效

---

## Tool 系统

### `get_available_tools()` — 工具装配

调用位置：`_make_lead_agent()` 中。

```python
def get_available_tools(
    groups: list[str] | None = None,         # 工具分组过滤
    include_mcp: bool = True,                # 是否包含 MCP 工具
    model_name: str | None = None,           # 用于条件工具（如 view_image）
    subagent_enabled: bool = False,          # 是否加入 task 工具
) -> list[BaseTool]:
```

### 装配顺序

```
1. Config-defined tools (config.yaml → tools[])
    │  通过 resolve_variable(cfg.use, BaseTool) 动态加载
    │  支持任何 BaseTool 子类
    │
2. MCP tools (if include_mcp and servers enabled)
    │  懒初始化（首次使用时加载）
    │  mtime-based 缓存失效
    │  多 server 并行加载
    │
3. Built-in tools
    │  present_files      — 标记产出文件对用户可见
    │  ask_clarification  — 请求用户澄清
    │  view_image         — 读取图片为 base64 (仅 vision 模型)
    │  setup_agent        — Bootstrap: 创建自定义 Agent
    │  update_agent       — Custom agent: 自我更新
    │  tool_search        — 延迟 MCP 工具发现 (如果 tool_search.enabled)
    │
4. Subagent tool (if subagent_enabled)
    │  task — 委派任务给子 Agent
    │
5. ACP agent tools
    │  invoke_acp_agent — 调用外部 ACP agent
```

### 去重规则

按**工具名称**去重。如果同样的 name 出现在多个来源，优先级：
1. **Config-defined** 优先（最高优先级）
2. MCP
3. Built-in

### Config-Defined 工具

```yaml
tools:
  - name: web_search
    group: web                                # 工具分组
    use: deerflow.community.ddg_search.tools:web_search_tool
    max_results: 5
    # ... 其他 provider 特定参数
```

`use` 字段通过 `resolve_variable()` 或 `resolve_class()` 动态加载。

### 工具分组 (tool_groups)

```yaml
tool_groups:
  web: ~
  file:read: ~
  file:write: ~
  bash: ~
```

分组用于：
- 配置管理中组织工具
- Custom agent 的工具白名单可引用组

### 内置工具详情

| 工具 | 条件 | 实现 |
|------|------|------|
| `present_files` | 始终 | `tools/builtins/present_files.py` |
| `ask_clarification` | 始终 | `tools/builtins/ask_clarification.py` |
| `view_image` | vision 模型 | `tools/builtins/view_image.py` |
| `setup_agent` | bootstrap 模式 | `tools/builtins/setup_agent.py` |
| `update_agent` | custom agent 模式 | `tools/builtins/update_agent.py` |
| `tool_search` | `tool_search.enabled` | `tools/builtins/tool_search.py` |
| `task` | `subagent_enabled` | subagent 系统 |
| `invoke_acp_agent` | ACP 配置了 agent | ACP 系统 |

## MCP 工具集成

### 系统架构

```
extensions_config.json
    │  mcpServers: {name: {enabled, type, command, args, env, ...}}
    ▼
get_cached_mcp_tools()
    │  懒初始化：首次调用才启动 MCP 服务器
    │  mtime cache：文件变化 → 重建连接
    │  MultiServerMCPClient (langchain-mcp-adapters)
    ▼
tools list
    合并到 Agent 工具列表
```

### Transport 类型

| Type | 说明 |
|------|------|
| `stdio` | 启动子进程，通过 stdin/stdout 通信 |
| `sse` | HTTP SSE 连接 |
| `http` | HTTP 请求 |

### OAuth 支持 (SSE/HTTP)

SSE 和 HTTP transport 支持 OAuth token 端点：
- `client_credentials` grant
- `refresh_token` grant
- 自动 token refresh
- Authorization header 注入

### MCP Interceptors

```json
{
  "mcpInterceptors": [
    "my_package.mcp.auth:build_auth_interceptor"
  ]
}
```

在创建 MCP 连接时注入自定义认证逻辑。

### 延迟工具加载（Tool Search）

```yaml
tool_search:
  enabled: false
```

启用后：
- MCP 工具不从 LLM context 加载
- Agent 通过 `tool_search` 工具按需发现
- 减少大型 MCP server 的上下文占用
