# DeerFlow 架构分析

> 内部设计、数据流、核心抽象。总入口，细节在各子文件。

## 导航

| 文件 | 内容 |
|------|------|
| [01-system-overview.md](01-system-overview.md) | 系统全景：进程、端口、组件关系、langgraph.json |
| [02-harness-app-boundary.md](02-harness-app-boundary.md) | 两层分层：Harness/App 边界、CI 执行、导入规则 |
| [03-request-flow.md](03-request-flow.md) | 请求数据流：API → Gateway → Agent → Graph → SSE 完整链路 |
| [04-middleware-chain.md](04-middleware-chain.md) | Middleware 链：20 个中间件逐一剖析 |
| [05-lead-agent.md](05-lead-agent.md) | Lead Agent：工厂函数、ThreadState、system prompt |
| [06-sandbox.md](06-sandbox.md) | 沙箱系统：抽象接口、Local/AIO/Provisioner 三种实现 |
| [07-subagent.md](07-subagent.md) | 子 Agent：执行器、双线程池、生命周期 |
| [08-memory.md](08-memory.md) | 记忆系统：提取、队列、存储、per-user 隔离 |
| [09-skills-tools.md](09-skills-tools.md) | Skills 与 Tool 系统：加载、注入、装配、MCP |
| [10-persistence.md](10-persistence.md) | 持久化与流式：DB/Checkpointer/RunEvents、SSE 协议 |
| [11-frontend.md](11-frontend.md) | 前端架构：Next.js 层、core 模块、流式数据流 |

## 关键设计原则

- **两层拆分**：Harness 是纯框架（可独立发布），App 是 HTTP/IM 应用层
- **Middleware 链**：所有横切关注点通过 LangChain Middleware 实现，最大程度复用
- **LangGraph 嵌入**：不依赖外部 LangGraph Server 进程，在 Gateway 内嵌 Runtime
- **Sandbox 抽象**：统一的虚拟路径体系，Agent 不感知本地/Docker 差异
- **配置驱动**：模型/工具/沙箱/Skill 都是运行时通过 config 解析，热加载
