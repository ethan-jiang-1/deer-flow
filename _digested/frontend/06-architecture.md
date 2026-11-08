---
title: "前端架构"
description: "| 类别 | 技术 | 版本 |"
topics: [frontend, nextjs, react]
---

# 前端架构

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 框架 | Next.js | ^16.4.1 |
| UI | React | ^19.0.0 |
| 语言 | TypeScript | 5.8 |
| 样式 | Tailwind CSS | 4 |
| 包管理 | pnpm | 10.26 |
| 状态管理 | TanStack Query | ^5.90 |
| 流式渲染 | @langchain/langgraph-sdk | ^1.5.3 |
| 组件库 | Radix UI | 15+ 包（🆕 另有 @headlessui/react ^2.2.9，仅 Lark 插件设置用） |
| 编辑器 | CodeMirror | — |
| 图表 | 🆕 无图布局库（`@xyflow/react` 已在 2.2.0 移除，已删除） | — |
| 校验 | 🆕 zod | ^4.6.6 |
| 文档搜索 | 🆕 Pagefind | 1.5.2（dev） |
| E2E | Playwright | ^1.62.1 |
| 单元测试 | Rstest（DOM 环境 happy-dom） | 0.10 |

2.2.0 依赖增减：新增 `@headlessui/react`、`qrcode.react` 4.2.0、`pagefind`；移除 `@xyflow/react`、`hast`、`tokenlens`、`@types/gsap`。`next` 16.2→16.4，`zod` 3→4（插件清单等 schema 校验随之迁移），Playwright 升到 1.62。脚本新增 `catalog:sync` 与 `search:index`，`build` 变为 `next build && pnpm run search:index`。

## 目录结构

```
frontend/src/
├── app/                           # Next.js App Router
│   ├── layout.tsx                 # Root layout (ThemeProvider + I18nProvider)
│   ├── page.tsx                   # 首页 Landing
│   ├── (auth)/login/              # 登录
│   ├── (auth)/setup/              # 首次管理员创建
│   ├── [lang]/docs/               # 文档 (Nextra + Pagefind 搜索)
│   ├── api/memory/                # Frontend API proxy
│   ├── blog/                      # MDX-based blog
│   ├── mock/                      # Demo mode mock API
│   ├── artifacts/view/            # 🆕 独立 artifact 查看路由
│   └── workspace/                 # 主应用
│       ├── page.tsx               # 工作区入口
│       ├── layout.tsx             # 🆕 force-dynamic + 认证分支
│       ├── workspace-content.tsx  # 工作区容器
│       ├── agents/                # Agent 管理 + agents/new 创建向导
│       ├── agents/[agent_name]/chats/[thread_id]/  # 核心会话页
│       ├── chats/                 # 会话列表 + chats/[thread_id]
│       ├── capabilities/          # Capability Center（plugins / skills / extensions）
│       ├── extensions/[namespace]/[surface_id]/  # 🆕 扩展插件页面
│       ├── projects/[id]/、trash/、scheduled-tasks/
│
├── components/
│   ├── ui/                        # Shadcn UI 生成的基元组件
│   ├── ai-elements/              # Vercel AI SDK 生成的 AI 组件
│   ├── workspace/                 # 工作区组件
│   │   ├── workspace-container.tsx  # 可drag面板布局
│   │   ├── workspace-sidebar.tsx    # 侧栏导航
│   │   ├── workspace-nav-chat-list.tsx  # 对话列表
│   │   ├── input-box.tsx           # 输入框 (文件/模型/plan toggle)
│   │   ├── todo-list.tsx           # 计划任务显示
│   │   ├── command-palette.tsx     # 键盘命令面板
│   │   ├── streaming-indicator.tsx # 流式状态指示
│   │   ├── token-usage-indicator.tsx # Token 消耗
│   │   ├── messages/               # 消息渲染（🆕 message-reasoning / message-details-* / scheduled-*）
│   │   ├── artifacts/              # 产物查看器
│   │   ├── citations/              # 🆕 引用：citation-link / knowledge-source / artifact-link / sources-panel
│   │   ├── changes/                # 🆕 workspace 变更徽章与 diff 面板
│   │   ├── scheduled-tasks/        # 🆕 任务列表/详情/表单/运行历史
│   │   ├── browser-view/           # 🆕 浏览器实时画面（WS + binary JPEG 帧）
│   │   ├── mentions/               # 🆕 composer 内联 @ 引用
│   │   ├── channels/               # 🆕 IM 渠道绑定（含微信扫码）
│   │   ├── settings/               # 设置面板（含 🆕 subagents / channels 分区）
│   │   ├── agents/                 # Agent 管理 UI
│   │   └── chats/                  # 聊天 UI（ChatBox 四态右面板）
│   ├── landing/                    # Landing page sections
│   ├── docs/                       # 🆕 DocsHtmlLang（Pagefind 索引按语言重建）
│
├── core/                          # 业务逻辑 (关键层)
│   ├── api/
│   │   ├── api-client.ts         # LangGraph SDK Client 单例（mock/default 双实例 + CSRF 注入 + 重连客户端）
│   │   └── stream-mode.ts        # 🆕 stream mode 白名单与 sanitize
│   ├── threads/
│   │   ├── hooks.ts              # useThreadStream — 核心流式 hook
│   │   ├── message-order.ts / stream-state.ts   # 合并排序与渲染态 patch
│   │   ├── activity.ts / origin.ts / token-usage.ts  # 🆕 未读轮询 / 会话来源 / token 用量
│   │   └── ...                   # 线程 CRUD、状态、导出
│   ├── agents/                   # Agent 管理 hooks + types
│   ├── settings/
│   │   └── store.ts              # localStorage 用户偏好
│   ├── memory/                   # Memory management
│   ├── skills/                   # Skills management
│   ├── mcp/                     # MCP management
│   ├── models/                  # Model listing/types
│   ├── messages/                # 消息处理、usage 计算
│   ├── artifacts/               # Artifact 加载、缓存、预览
│   ├── uploads/                 # 文件上传管理
│   ├── tasks/                   # Subagent task 跟踪上下文
│   ├── todos/                   # Todo 类型 (plan mode)
│   ├── streamdown/              # Markdown-to-React 流式渲染
│   ├── auth/                    # JWT/OAuth/proxy 认证
│   ├── config/                  # 环境配置解析
│   ├── i18n/                    # en-US / zh-CN
│   ├── notifications/           # 通知 hooks
│   ├── utils/                   # 日期、文件、markdown 工具
│   ├── tools/                   # 工具工具函数
│   ├── knowledge/               # 🆕 知识库 scope 快照 + 检索目录 + ragflow 证据
│   ├── citations/               # 🆕 检索源读取
│   ├── capabilities/            # 🆕 能力目录/安装
│   ├── extensions/              # 🆕 扩展清单、插件页面、surface 挂载、@ 提及
│   ├── channels/                # 🆕 IM 渠道
│   ├── features/                # 🆕 /api/features 开关
│   ├── workspace-changes/       # 🆕 run 级文件变更
│   ├── subagents/               # 🆕 子智能体注册表
│   ├── sidecar/                 # 🆕 侧聊
│   ├── voice-input/             # 🆕 语音输入
│   ├── input-polish/            # 🆕 输入润色
│   └── dom/                     # 🆕 渲染活跃度观察
│
├── content/                       # Nextra 内容源（en/zh：harness / application / introduction / reference / tutorials / posts）
│   └── {en,zh}/harness/           # Harness 手册（subagents/ 11 页、extensions/ 11 页、checkpoints/ 11 页）
├── hooks/                        # use-mobile, use-global-shortcuts
├── lib/                          # cn() utility, ime.ts（IME 组合期判定）
├── server/                       # Server-side utilities
├── styles/                       # Global CSS (Tailwind v4)
└── typings/                      # .md/.mdx type declarations
```

## Harness 内容手册（`frontend/src/content`，v2.1.0）

`frontend/src/content/{en,zh}/` 是 Nextra 文档站的双语内容源（页面由 `app/[lang]/docs/[[...mdxPath]]` 渲染），按 `harness/`、`application/`、`introduction/`、`reference/`、`tutorials/`、`posts/` 分目录。`harness/` 下除单页 `.mdx` 外还有两个多章手册目录，每语言各带一份 `_meta.ts` 定义侧栏标题与顺序：

| 目录 | 页数 | 用途 / 章节 |
|------|------|-------------|
| `harness/subagents/` | 11（`index` + 10 章） | 子 Agent 用户手册：`quick-start`、`catalog`、`delegation`、`results`、`limits`、`sandbox`、`observability`、`troubleshooting`、`developers`、`reference` |
| `harness/extensions/` | 10（`index` + 9 章） | 扩展包开发者手册：`quick-start`、`runtime`、`middleware`、`observers`、`services-and-routes`、`run-evidence`、`operations`、`troubleshooting`、`reference` |

v2.1.0 前 `subagents` 是单文件 `subagents.mdx`；改为目录后 `index.mdx` 用 `asIndexPage: true` 充当章节首页（`/docs/harness/subagents` 链接不变，`configuration.mdx` / `tools.mdx` / `sandbox.mdx` 仍指向该目录路径，因此 `_meta.ts` 不列 `index`，否则 Nextra `_meta` 校验失败、所有 docs 页面返回 500 —— 见 `d818a083` commit body）；en/zh 的 `middlewares.mdx` 各有一个锚点改指 `.../subagents/limits#…`（en `#runaway-guards`、zh `#失控行为防护`，zh 用本地化标题锚点）。`extensions` 为 v2.1.0 新增目录，harness 的 `_meta.ts` 同时新增 `extensions` 条目（en `"Extensions"` / zh `"扩展包"`）。

## 关键数据流

### API Client 单例

```typescript
// core/api/api-client.ts:649
const _clients = new Map<string, LangGraphClient>();

export function getAPIClient(isMock?: boolean): LangGraphClient {
  const cacheKey = isMock ? "mock" : "default";   // 两个缓存槽，不是全局单例
  let client = _clients.get(cacheKey);
  if (!client) { /* 构造 + 注入 onRequest: injectCsrfHeader + run 流客户端包装 */ }
  return client;
}
```

关键点（2.2.0）：

- **两个实例**：mock 与真实客户端分别缓存，mock 走静态 demo 数据；静态站点模式下 `createStaticClient()`（`:611`）返回不发网请求的桩客户端
- **CSRF**：`onRequest` 钩子在每个**状态改变**请求前从 `csrf_token` cookie 现读现注入 `X-CSRF-Token`（不在构造时烘焙进 `defaultHeaders`，因此登录/登出/改密后的 cookie 轮换自动生效）；与 `fetcher.ts::fetchWithAuth` 共用 `readCsrfCookie` / `isStateChangingMethod`
- **run 创建不走 SDK 重试**：`runCreationClient` 用 `maxRetries: 0`，错误交给 `StreamRecoveryClient`（`:463`）判定；`joinStream` 在加入前用 `TERMINAL_RUN_STATUSES = {success, error, timeout, interrupted}` 短路——已终止的 run 重连要么 409，要么在流桥回收后永久阻塞（把 `isLoading` 钉成 true）
- **stream mode 白名单**：`core/api/stream-mode.ts` 的 `SUPPORTED_RUN_STREAM_MODES` 只放行 `values / messages-tuple / updates / debug / tasks / checkpoints / custom`，`sanitizeRunStreamOptions()` 丢弃请求的 `streamResumable` 并拒绝不支持的模式（一次性 warn）；聊天路径另有 `forceChatRunStreamOptions()`（`messages-tuple + updates + custom`）

所有后端通信都经过这两个 `Client` 实例，由 `@langchain/langgraph-sdk` 提供；REST 侧统一走 `getBackendBaseURL()` + `fetchWithAuth`。

### 流式对话循环

```
User types message
    │
    ▼
input-box.tsx 提交 → 调用 thread hooks
    │
    ▼
useThreadStream (core/threads/hooks.ts:1956)
    │  使用 useStream from @langchain/langgraph-sdk/react
    │  选项：reconnectOnMount / fetchStateHistory{limit:1} / throttle:true
    │  订阅 SSE events: values, messages-tuple, updates, custom, end
    │
    ├── values → 渲染态 patch（title / artifacts / tool_artifacts / todos / goal）
    │    core/threads/stream-state.ts::reduceThreadStateUpdates
    │
    ├── messages-tuple → 增量渲染
    │    AI 文本: delta 拼接 (streamdown 流式 markdown 渲染)
    │    tool_call: 展示工具调用
    │    tool_result: 展示工具结果
    │
    ├── custom → 特殊事件处理
    │    task_started/running/completed → 子 Agent 状态更新
    │
    ├── custom: stream_replay_gap → 丢弃本地流状态并按 run_id 重连（≤5 次）
    │
    └── end → 流结束，累计 token usage
```

### Thread State 管理

```typescript
// React Context 传递 thread state
WorkspaceContainer
├── useThread(id) — TanStack Query cache
├── useThreadStream(id) — 流式 hook
└── children
    ├── Sidebar — 对话列表
    ├── Chat View — 消息列表
    └── Input Box — 输入区
```

### 用户偏好持久化

```typescript
// core/settings/store.ts
// localStorage based
interface Settings {
  modelName: string;
  thinkingEnabled: boolean;
  planMode: boolean;
  subagentEnabled: boolean;
  theme: "light" | "dark";
  language: "en-US" | "zh-CN";
}
```

## 组件交互

### 输入框状态

- Composer busy-state: 谁管理输入框在提交后的 loading 状态
- Pre-submit upload: 文件在选择后立即上传（不等提交），`UploadsMiddleware` 注入到对话上下文
- WebSocket lifecycle: `useThreadStream` hook 管理

### 消息渲染

```
<MessageList>
  ├── <UserMessage>
  │     └── content (markdown)
  ├── <AIMessage>
  │     ├── content → streamdown (流式 markdown 到 React)
  │     ├── tool_calls → <ToolCallCard>
  │     └── thinking → <ThinkingBlock>
  └── <ToolResultMessage>
        └── <ArtifactPreview> (if applicable)
```

### 子 Agent 任务显示

```
<TaskTracker (React Context)>
  ├── task_started → 添加 TaskCard
  ├── task_running → 更新进度
  ├── task_completed → 展示结果
  ├── task_failed → 展示错误
  └── task_timed_out → 展示超时
```

## 响应式设计

- Mobile: `use-mobile` hook 检测，可折叠侧栏
- Desktop: 可 drag resize 的面板布局 (`workspace-container.tsx`)

## Demo / Mock 模式

`app/mock/` 提供静态 demo 模式，所有后端 API 被 mock，用于展示型部署（如项目官网）。同步 #6：stub 响应构造统一到 `core/api/static-response.ts`（#5302），并支持独立 demo API + 运行时 GitHub stars（`app/github-stars/route.ts` + landing `star-counter.tsx`）。

🆕 2.2.0 的静态产物构建：`frontend/Makefile::build-static` = `NEXT_CONFIG_BUILD_OUTPUT=standalone SKIP_ENV_VALIDATION=1 NEXT_PUBLIC_STATIC_WEBSITE_ONLY=true pnpm build`，然后拷贝 `.next/static` 与 `public`。`NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"` 时：知识库 scope 选择器不渲染、artifact 面板自动选中首个 artifact、`isManageCapability` 一律为假（目录只读）。

## 🆕 同步 #6 架构要点

- **Dev bundler**：`pnpm dev` 走 `scripts/dev.mjs`，**Webpack 为跨平台默认**（Turbopack 的 PostCSS worker 泄漏 #5132 未在上游稳定修复），`DEER_FLOW_DEV_BUNDLER=turbo|webpack` 可覆盖，非法值直接报错
- **新 core 模块**：`core/projects/`（api/hooks/types + composer-attach 跨路由附件交接）、`core/trash/`、`core/conversation-references/`、`core/threads/message-order.ts` + `stream-state.ts`（排序/流状态纯函数化）、`core/settings/user-preferences*`（账号偏好同步）、`core/models/favorites*`（模型收藏）、`core/auth/permissions.ts`（Phase 4 权限门控）、`core/artifacts/delimited-preview*`（Worker 内 CSV/TSV 预览）
- **目录迁移**：能力管理从 `settings/` 迁到 `workspace/capabilities/`（`/workspace/capabilities` 页面）；`ai-elements/model-selector.tsx` 删除，改为 `workspace/model-picker-content.tsx`
- 依赖：next 16.2→16.3、新增 papaparse（表格预览）；测试 runner 为 rstest

## 🆕 2.2.0 架构要点

### 扩展运行时（`core/extensions/`）

前端扩展第一次成为一等公民：扩展通过 `FrontendExtension` 清单声明**导航页面**（`slot: "page"` + `navigation`）与**服务**，由 Gateway 的 `/api/extensions/frontend` 下发给浏览器。

| 文件 | 职责 |
|------|------|
| `catalog.ts` | 内建发现元数据（`extensionCatalog`）：agentTeams `community.agent-teams`、bookmarks `community.bookmarks`、context `community.jev-context`、classify `community.jev-classify`、retrieval `example.retrieval`、workflows、reportSections、knowledgeManagement、knowledgePlatform… |
| `pages.ts` | `pluginPagePath(namespace, surfaceId)` → `/workspace/extensions/{namespace}/{surfaceId}`；`pluginPageTitle` 按 locale 前缀取 zh/en 标题；`pluginPages()` 只取 `slot === "page"` |
| `surfaces.ts` | `mountSurface()` 在 **Shadow DOM** 内挂载插件 UI：样式隔离（不是权限边界）、`AbortController` 取消、dispose 兜底 |
| `registry.ts` | 图标解析（`extensionIcon`），导航与页面统一使用 |
| `hooks.ts` | `useFrontendExtensions()`，query key 带 `user?.id` |
| `use-mentions.ts` | `useExtensionMentions(query, threadId)`，条件：`viewer_id === userId` 且 `settings.enabled` 且 `mentionProviders.length > 0` |

页面层：`components/workspace/plugin-page.tsx` 的 `PluginPage({namespace, surfaceId})` 找不到对应 surface 时给 "reload + 查看全部"（跳 `/workspace/capabilities?tab=extensions`）；`plugin-surfaces.tsx` 负责 `useFrontendExtensions`/`useFrontendServices`、`bindFrontendServices` 与 `openConversation`。路由 `app/workspace/extensions/[namespace]/[surface_id]/page.tsx` 是 server component，解出 params 后渲染 client 侧 `PluginPage`。

### 文档站搜索（Pagefind）

`scripts/build-search-index.mjs` 在 `next build` 之后运行：扫 `.next/server/app` 下的 HTML，按 `/{lang}/` 路由前缀把 `lang` 属性的 `en`→`en-US`、`zh`→`zh-CN` 重写（根 layout 只有一个固定 `lang`，不改写的话 Pagefind 会把中文页当英文切词），输出到 `public/_pagefind`。

`components/docs/docs-html-lang.tsx::DocsHtmlLang` 在切换语言时**删除 `window.pagefind` 并 `destroy()`**，强制按新语言重建索引；`app/[lang]/docs/layout.tsx` 把 Nextra 的 `<Search>` 放进自定义 Header 并传 `searchOptions={{ filters: { lang } }}`，同时给 Nextra Layout 传 `search={null}` —— 否则两个搜索实例会抢同一个 ⌘K。页面里另有 `<span hidden data-pagefind-filter={`lang:${lang}`}>` 供过滤器使用。

### 已删除（2.2.0）

| 已删除模块 | 现行替代 |
|-----------|---------|
| `components/ai-elements/{canvas,checkpoint,connection,context,controls,edge,image,node,open-in-chat,panel,plan,sources,toolbar,web-preview}.tsx`（14 个） | 消息/工具渲染改由 `components/workspace/messages/` 与 `components/workspace/citations/` 承担；画布类需求交给扩展 surface |
| 聊天头部原定时任务入口组件 `thread-scheduled-tasks-link.tsx`（已删除） | 定时任务入口改为聊天内 `ScheduledTaskCard` + `/workspace/scheduled-tasks` 页面 |
| 认证代理策略模块 `proxy-policy.ts`（已删除，原在 `core/auth/`） | 代理策略移到 Gateway（nginx + 后端），前端只保留 `core/auth/` 的会话与权限（`permissions.ts`） |
