# 配置与扩展系统

DeerFlow 暴露了哪些挂载点？怎么把自定义的东西挂上去？

## 阅读顺序

1. **Config System** — config.yaml 分层、热加载、优先级链、env var 解析、config_version 升级
2. **MCP** — 多 server（stdio/SSE/HTTP）、OAuth token 刷新、缓存失效
3. **Skills** — SKILL.md 格式、加载/安装/启用、自定义 skill
4. **Custom Tools & Agents** — Tool 注册流程、community tools、ACP agent 协议

## 关键问题

- 修改 config.yaml 后哪些字段实时生效，哪些必须重启？
- MCP server 的 tool 是怎么注入到 Agent Loop 的？
- Skills 的 allowed-tools 白名单在什么阶段执行？
- ACP agent 和 subagent 的区别是什么？
