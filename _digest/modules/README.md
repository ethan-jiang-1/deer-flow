# 模块源码阅读笔记

逐包分析 DeerFlow 各子系统的实现细节。

## 待深入

- [ ] `deerflow.agents.lead_agent` — Lead Agent 工厂 + 系统 prompt
- [ ] `deerflow.agents.middlewares` — 18 个中间件逐一分析
- [ ] `deerflow.runtime` — Run 生命周期管理
- [ ] `deerflow.subagents` — 子 Agent 注册、调度、执行
- [ ] `deerflow.sandbox` — 沙箱抽象与本地实现
- [ ] `deerflow.tools` — 工具装配与内置工具
- [ ] `deerflow.mcp` — MCP 协议集成
- [ ] `deerflow.skills` — Skill 系统
- [ ] `deerflow.models` — 模型工厂与多 provider 适配
- [ ] `deerflow.config` — 配置系统
- [ ] `deerflow.persistence` — 数据库/ORM 层
- [ ] `deerflow.client` — 嵌入式 Python SDK
- [ ] `app.gateway` — FastAPI 应用层
- [ ] `app.channels` — IM 集成
- [ ] `frontend/src/core` — 前端业务逻辑
