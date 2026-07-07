# SVG Figures

此目录包含 DeerFlow 架构的关键 SVG 图。每个 SVG 都是自包含的——在浏览器中打开即可渲染。

## 图列表

| 文件 | 所属 | 内容 |
|------|------|------|
| `concentric-rings.svg` | 01-logical | 四层同心圆总览：Access → Gateway → Harness → Core |
| `agent-loop.svg` | 01-logical | Agent Loop 核心循环：系统 prompt → LLM → tool → results，含 29 个中间件完整列表 |
| `skills-loading.svg` | 01-logical | Skills 加载链：SKILL.md → load_skills → prompt 注入 → LLM 选择 |
| `subagent-delegation.svg` | 01-logical | Sub-agent 委派模型：Lead Agent → Executor → 3 并行 subagent → 聚合 |
| `sandbox-paths.svg` | 01-logical | 虚拟路径映射表 + 多层安全防护机制 |
| `process-topology.svg` | 02-component | 进程拓扑图：Nginx/Gateway/Frontend/Provisioner 及端口/内部模块 |
| `dependency-graph.svg` | 02-component | Harness 内部依赖关系图：agents→sandbox/tools/skills→config→models/runtime/mcp |
| `gateway-lifespan.svg` | 03-startup | Gateway 启动流程：module load → create_app → lifespan 6 步 |
| `startup-sequence.svg` | 03-startup | 四种启动入口对比：make dev · docker-start · make gateway · DeerFlowClient |
| `request-lifecycle.svg` | 03-startup | 请求完整生命周期：HTTP → Nginx → Auth → stream_run → run_agent → make_lead_agent → Pregel → SSE |

## 颜色规范

| 颜色 | 含义 |
|------|------|
| 绿色系 `#E8F5E9` | Access layer / 外部入口 / 成功 |
| 蓝色系 `#E3F2FD` | Gateway / API 层 |
| 橙色系 `#FFF3E0` | Harness / 核心引擎 / 工具 |
| 紫色系 `#F3E5F5` | 基础设施 / 配置 / runtime |
| 红色系 `#FFEBEE` | 安全 / 边界 / 警告 |
| 灰色系 `#F5F5F5` | 存储 / 数据 |
| 青色系 `#E0F7FA` | 模型层 |
