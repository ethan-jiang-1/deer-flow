# DeerFlow 源码研究笔记

> **核心规则：绝不碰源代码。本目录 `_digest/` 是唯一可以修改的地方。**

## 为什么不碰源代码

1. 本项目是 [bytedance/deer-flow](https://github.com/bytedance/deer-flow) 的 fork，`main` 分支的唯一职责是**跟踪上游**
2. 上游更新频繁，`main` 必须保持干净才能无冲突地 `git pull`
3. 所有研究笔记、个人理解、集成实验记录都在 `_digest/` 下，在 `ethan` 分支上独立演进
4. `ethan` 分支永远不会 merge 回 `main`，它只是一个研究工作台

**`main` = 上游镜像，`ethan` + `_digest/` = 学习空间。**

---

## 推进计划

### Phase 1：消除内部矛盾

- [x] **1.1 统一中间件数量** — 以 middleware/03-catalog.md（逐源码核实，19 个）为准，修正以下文件中的 "20"：
  - `architecture/README.md`
  - `architecture/01-system-overview.md:112`
  - `architecture/03-request-flow.md:29`
  - `architecture/04-middleware-chain.md`（编号 1-20 → 0-19）
  - `security/03-guardrail.md:46`
  - `agent-loop/README.md`（核心结论第 2 条）
- [x] **1.2 淘汰 architecture/04-middleware-chain.md** — 它和 middleware/ section 描述同一件事但用了不兼容的模型（名字对不上、5 阶段 vs 6 hook）。改为一行废弃声明 + 指向 middleware/ 的链接
- [x] **1.3 统一防御层数** — security/00 说 7 层，security/04 说 14 层。在 security/00 中标注"粗粒度 7 层 / 细粒度 14 层"，两处互相引用
- [x] **1.4 修正 agent-loop/ 中的 20 → 19** — README 和 00-loop-anatomy.md 各有一处 "20 个 middleware"

### Phase 2：结构修复

- [ ] **2.1 处理 integration/02-configuration.md（465 行）** — 太长且在错误位置。两种方案：a) 拆分到 configuration/ 下作为 04-config-reference.md，integration/02 缩减为百行内的接入视角摘要；b) 直接标为"配置参考详见 configuration/ section"，大幅精简
- [ ] **2.2 加交叉引用** — 至少在以下关键路径上加双向链接：
  - security/03 ↔ middleware/03-catalog（GuardrailMiddleware）
  - security/02 ↔ architecture/06（sandbox 三种实现）
  - middleware/03-catalog ↔ architecture/05（ThreadState、make_lead_agent）
  - it-ops/02 ↔ security/02（sandbox 治理 vs 安全视角）
  - agent-loop/00 ↔ middleware/01（loop 结构 vs hook 执行流）
- [ ] **2.3 it-ops/README 跨目录索引加真实 markdown 链接** — 目前是纯文本表格，改成 `[security/01-auth.md](../security/01-auth.md)` 格式

### Phase 3：加深偏薄章节

- [ ] **3.1 model-layer/02-streaming.md 扩展** — 从 96 行扩展到 200+ 行。补 per-provider chunk 归一化的完整分析：vLLM reasoning 字段保留、MiniMax `<think>` 标签解析、MindIE tool+stream 降级、Codex Responses API SSE 格式
- [ ] **3.2 it-ops/01~05 加深** — 每篇从 58-148 行扩展到 150-200 行。从 checklist 风格转为"为什么这样设计"的深层分析
- [ ] **3.3 model-layer/01-thinking-vision.md 扩展** — 三种 thinking 配置模式的实际代码路径、vision 启用链路的完整 trace

### Phase 4：填充新 section — community-tools/

- [ ] **4.1 community-tools/00-overview.md** — 9 个集成的全景图、tool 装配流程中的位置、provider 选择决策树
- [ ] **4.2 community-tools/01-web-search.md** — 6 种 search provider 对比（DDG/Tavily/Serper/Exa/Firecrawl/InfoQuest）、参数差异、返回格式
- [ ] **4.3 community-tools/02-web-fetch.md** — 4 种 fetch provider 的 URL→markdown 管线（Jina/Exa/InfoQuest/Firecrawl）
- [ ] **4.4 community-tools/03-image-search.md** — DDG/InfoQuest 图片搜索、与 vision model 的对接
- [ ] **4.5 community-tools/04-aio-sandbox.md** — AioSandboxProvider 深入：Docker 容器管理、Apple Container 探测、LRU 淘汰、K3s provisioner

### Phase 5：填充新 section — frontend/

- [ ] **5.1 frontend/00-overview.md** — 技术栈全景、组件树、数据流图
- [ ] **5.2 frontend/01-stream-pipeline.md** — SSE → React 管线：useThreadStream、LangGraph stream_mode 映射、增量渲染
- [ ] **5.3 frontend/02-message-rendering.md** — streamdown 流式 markdown、thinking block、tool call 卡片、artifact 预览
- [ ] **5.4 frontend/03-state-management.md** — TanStack Query 缓存、ThreadState context、localStorage 偏好
- [ ] **5.5 frontend/04-workspace-layout.md** — Drag 面板、响应式、command palette
- [ ] **5.6 frontend/05-subagent-ui.md** — TaskTracker context 状态机

### Phase 6：填充新 section — channels/

- [ ] **6.1 channels/00-overview.md** — 7 平台架构全景、两种 stream 策略分裂
- [ ] **6.2 channels/01-message-bus.md** — MessageBus pub/sub、ChannelManager dispatch loop
- [ ] **6.3 channels/02-stream-strategies.md** — 增量流式（Feishu/DingTalk）vs 阻塞等待（Slack/Telegram）
- [ ] **6.4 channels/03-thread-mapping.md** — Channel→Thread ID 持久化、命令系统、per-platform 细节

### Phase 7：填充新 section — deployment/

- [ ] **7.1 deployment/00-overview.md** — 4 种部署模式对比矩阵、进程拓扑
- [ ] **7.2 deployment/01-local-dev.md** — `make dev`：uvicorn hot reload、Turbopack、多进程管理
- [ ] **7.3 deployment/02-docker.md** — Docker Compose 4 服务、网络配置、DooD 模式
- [ ] **7.4 deployment/03-nginx-and-k8s.md** — Nginx 路由规则、K8s Provisioner 模式

### Phase 8：填充新 section — testing/

- [ ] **8.1 testing/00-overview.md** — 测试金字塔、框架选型、CI 流程
- [ ] **8.2 testing/01-harness-boundary.md** — test_harness_boundary.py 的 AST 分析 + CI 强制执行
- [ ] **8.3 testing/02-gateway-conformance.md** — TestGatewayConformance：SDK/Gateway 格式一致性
- [ ] **8.4 testing/03-e2e-and-unit.md** — Playwright E2E + Vitest 单元测试模式

---

## 目标目录结构

```
_digest/
├── README.md                      # 本文件（推进计划 + checklist）
├── architecture/                  # 内部设计（04 需淘汰）
├── integration/                   # 接入指南（02 需处理）
├── configuration/                 # 配置与扩展
├── security/                      # 安全边界（防御层数需统一）
├── middleware/                    # Agent 中间件体系（质量最高）
├── model-layer/                   # LLM 抽象（streaming 需加深）
├── it-ops/                        # IT 治理（展开篇需加深）
├── builtin-tools/                 # 内置工具全量清单
├── community-tools/               # [新建] 外部工具集成
├── agent-loop/                    # Agent Loop 技术内核
├── frontend/                      # [新建] 前端架构
├── channels/                      # [新建] IM 通道系统
├── deployment/                    # [新建] 部署架构
└── testing/                       # [新建] 测试策略
```

## 工作流

- 切到 `ethan` 分支工作：`git checkout ethan`
- 研究过程中发现值得记录的内容 → 写入 `_digest/` 对应目录
- 定期回到 `main` 拉上游：`git checkout main && git pull upstream main`
- 需要时把上游的新变更 merge 到 `ethan`：`git checkout ethan && git merge main`

## 上游信息

- 仓库：https://github.com/bytedance/deer-flow
- 协议：MIT
- 技术栈：Python 3.12+ / Node.js 22+ / LangGraph / Next.js 16
