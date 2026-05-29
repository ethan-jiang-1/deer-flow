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

- [x] **2.1 处理 integration/02-configuration.md（465 行）** — 全量迁移到 configuration/04-config-reference.md，integration/02 缩减为 ~80 行接入视角摘要
- [x] **2.2 加交叉引用** — 5 对关键路径双向链接已添加
  - security/03 ↔ middleware/03-catalog（GuardrailMiddleware）
  - security/02 ↔ architecture/06（sandbox 三种实现）
  - middleware/03-catalog ↔ architecture/05（ThreadState、make_lead_agent）
  - it-ops/02 ↔ security/02（sandbox 治理 vs 安全视角）
  - agent-loop/00 ↔ middleware/01（loop 结构 vs hook 执行流）
- [x] **2.3 it-ops/README 跨目录索引加真实 markdown 链接**

### Phase 3：加深偏薄章节

- [x] **3.1 model-layer/02-streaming.md 扩展** — 从 96 行扩展到 220+ 行。补了 per-provider chunk 归一化完整分析：vLLM 多态 reasoning、MiniMax 双源 reasoning+`preserve_whitespace` 拼接、MindIE 15字符合成 chunk、Codex 内部 SSE 收集、DeepSeek/Gemini outbound 重注入、共同模式总结、provider 对比表
- [x] **3.2 it-ops/01~05 加深** — 每篇新增"设计决策分析"section，补 fail-closed 理由、6 层路径防护原理、per-thread 隔离权衡、硬编码审计列表博弈、bounded autonomy 设计哲学、CSRF double-submit 选择、token_version 机制、Docker seccomp 风险、行业沙箱对比
- [x] **3.3 model-layer/01-thinking-vision.md 扩展** — 新增 thinking 模式检测代码路径（factory.py 5 步流程图）、vision 启用链路 5 步 trace、vLLM 旧版兼容、Anthropic auto_thinking_budget、vision 三决策联动

### Phase 4：填充新 section — community-tools/

- [x] **4.1 community-tools/00-overview.md** — 9 集成全景图、reflection 加载机制、按名去重、provider 选择决策树
- [x] **4.2 community-tools/01-web-search.md** — 6 种 search provider 逐项对比（签名/认证/HTTP/返回格式/配置）、返回格式不一致性分析
- [x] **4.3 community-tools/02-web-fetch.md** — 4 种 fetch provider 的 URL→markdown 管线图、ReadabilityExtractor 共用机制、Async→Sync 包装原理
- [x] **4.4 community-tools/03-image-search.md** — DDG image search 签名+过滤参数、与 view_image tool 的对接链路
- [x] **4.5 community-tools/04-aio-sandbox.md** — AioSandboxProvider 完整生命周期（acquire→warm pool→idle eviction→shutdown）、确定性 sandbox ID 跨进程 discovery、容器运行时探测、K3s provisioner、Docker seccomp 风险

### Phase 5：填充新 section — frontend/

- [x] **5.1 frontend/00-overview.md** — 技术栈全景、目录结构、数据流 3 层架构
- [x] **5.2 frontend/01-stream-pipeline.md** — SSE → React 管线：useThreadStream、LangGraph SDK useStream、消息合并策略、token 追踪、4 套 streamdown 插件配置
- [x] **5.3 frontend/02-message-rendering.md** — 消息分组→分类渲染、thinking block 三源提取+防幻觉 HTML、tool call 卡片、artifact 预览、文件附件渲染
- [x] **5.4 frontend/03-state-management.md** — TanStack Query 查询/变更、LangGraph SDK 流式状态、localStorage useSyncExternalStore、4 个 React Context、组件本地状态
- [x] **5.5 frontend/04-workspace-layout.md** — ResizablePanelGroup 双面板、Welcome/Conversation 两种模式、Command Palette 快捷键、Theme CSS 变量、9 种自定义动画
- [x] **5.6 frontend/05-subagent-ui.md** — SubtaskContext 状态机、in_progress/completed/failed 三态渲染、Shimmer/ShineBorder/FlipDisplay 动画、parseSubtaskResult 防御式解析

### Phase 6：填充新 section — channels/

- [x] **6.1 channels/00-overview.md** — 7 平台架构全景、两种 stream 策略分裂、连接方式矩阵
- [x] **6.2 channels/01-message-bus.md** — MessageBus 双向 pub/sub、ChannelManager semaphore(5) 并发控制、4 层 config 合并
- [x] **6.3 channels/02-stream-strategies.md** — 增量流式（350ms throttle、Feishu card patching、WeCom reply_stream）vs 阻塞等待（runs.wait、artifact 分发）
- [x] **6.4 channels/03-thread-mapping.md** — ChannelStore JSON 原子写入、各平台 topic_id 语义、/new /bootstrap 等 6 命令、per-user session 层叠

### Phase 7：填充新 section — deployment/

- [x] **7.1 deployment/00-overview.md** — 4 种部署模式对比矩阵、进程拓扑、关键环境变量
- [x] **7.2 deployment/01-local-dev.md** — make dev 4 进程拓扑、hot reload 机制、常见问题诊断
- [x] **7.3 deployment/02-docker.md** — Docker Compose 5 服务拓扑、DooD 模式原理、生产 checklist
- [x] **7.4 deployment/03-nginx-and-k8s.md** — SSE proxy_buffering off 原理、rate limiting、K3s Provisioner Pod spec、RBAC 配置

### Phase 8：填充新 section — testing/

- [x] **8.1 testing/00-overview.md** — 测试金字塔、CI 强制边界、Gateway 一致性、E2E mock SSE 策略
- [x] **8.2 testing/01-harness-boundary.md** — AST import 扫描机制、豁免注释体系、CI 集成
- [x] **8.3 testing/02-gateway-conformance.md** — 双路径对比原理、消息/tool/chunk 一致性、序列化层 regression 检测
- [x] **8.4 testing/03-e2e-and-unit.md** — Vitest 消息处理/subtask/settings 测试、Playwright API mock + 关键场景、pytest provider 测试清单

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
├── community-tools/               # 外部工具集成（9 个 provider）
├── agent-loop/                    # Agent Loop 技术内核
├── frontend/                      # 前端架构（Next.js + React 19）
├── channels/                      # IM 通道系统（7 平台）
├── deployment/                    # 部署架构（4 种模式）
└── testing/                       # 测试策略（3 层体系）
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
