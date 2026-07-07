# MCP 工具管理：五种机制详解

## 机制 1：`tool_search` 延迟加载（Deferred Tool Loading）

DeerFlow 的"最佳推荐"——但不默认开启。完整生命周期见 [answer.md](answer.md)。

配置：
```yaml
# config.yaml
tool_search:
  enabled: true
```

## 机制 2：MCP Server 级别的 `enabled` 开关

最粗粒度但最确定。通过 `extensions_config.json` 控制：
```json
{"mcpServers": {"github": {"enabled": true}, "postgres": {"enabled": false}}}
```

可通过 Gateway API `PUT /api/mcp/config` 运行时修改。

## 机制 3：Subagent Tool Allowlist/Denylist

**对 MCP 工具生效。** 在 `config.yaml` 的 subagent 配置中指定：
```yaml
subagents:
  custom_agents:
    github-agent:
      tools: [github_create_issue, github_search_repositories, bash, read_file]
```
内置子 agent：`general-purpose`（全部）、`bash`（仅 sandbox 工具）。

## 机制 4：Skill `allowed-tools`

在 SKILL.md 的 YAML frontmatter 中声明：
```markdown
---
name: github-workflows
allowed-tools: [github_create_issue, read_file, write_file]
---
```
当 skill 被精确加载时，自动过滤工具集。

## 机制 5：`tool_groups`（⚠️ 不对 MCP 生效）

`config.yaml` 中 `tool_groups` 和 `AgentConfig.tool_groups` 只过滤 `config.yaml` 的 `tools:` 部分，**不作用于 MCP 工具**。这是最容易踩的坑。
