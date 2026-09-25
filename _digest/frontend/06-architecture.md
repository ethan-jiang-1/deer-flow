---
title: "前端架构"
description: "| 类别 | 技术 | 版本 |"
topics: [frontend, nextjs, react]
---

# 前端架构

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 框架 | Next.js | 16 |
| UI | React | 19 |
| 语言 | TypeScript | 5.8 |
| 样式 | Tailwind CSS | 4 |
| 包管理 | pnpm | 10.26 |
| 状态管理 | TanStack Query | ^5.90 |
| 流式渲染 | @langchain/langgraph-sdk | ^1.5.3 |
| 组件库 | Radix UI | 15+ 包 |
| 编辑器 | CodeMirror | — |
| 图表 | @xyflow/react | — |
| E2E | Playwright | — |
| 单元测试 | Rstest | 0.10 |

## 目录结构

```
frontend/src/
├── app/                           # Next.js App Router
│   ├── layout.tsx                 # Root layout (ThemeProvider + I18nProvider)
│   ├── page.tsx                   # 首页 Landing
│   ├── (auth)/login/              # 登录
│   ├── (auth)/setup/              # 首次管理员创建
│   ├── [lang]/docs/               # 文档 (Nextra)
│   ├── api/memory/                # Frontend API proxy
│   ├── blog/                      # MDX-based blog
│   ├── mock/                      # Demo mode mock API
│   └── workspace/                 # 主应用
│       ├── page.tsx               # 工作区入口
│       ├── workspace-content.tsx  # 工作区容器
│       ├── agents/                # Agent 管理
│       ├── agents/new/            # Agent 创建向导
│       └── agents/[agent_name]/chats/[thread_id]/
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
│   │   ├── messages/               # 消息渲染
│   │   ├── artifacts/              # 产物查看器
│   │   ├── citations/              # 引用展示
│   │   ├── settings/               # 设置面板
│   │   ├── agents/                 # Agent 管理 UI
│   │   └── chats/                  # 聊天 UI
│   └── landing/                    # Landing page sections
│
├── core/                          # 业务逻辑 (关键层)
│   ├── api/
│   │   └── api-client.ts         # LangGraph SDK Client 单例
│   ├── threads/
│   │   ├── hooks.ts              # useThreadStream — 核心流式 hook
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
│   └── tools/                   # 工具工具函数
│
├── content/                       # Nextra 内容源（en/zh：harness / application / introduction / reference / tutorials / posts）
│   └── {en,zh}/harness/           # Harness 手册（v2.1.0：subagents/ 11 页、extensions/ 10 页）
├── hooks/                        # use-mobile, use-global-shortcuts
├── lib/                          # cn() utility, IME handling
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
// core/api/api-client.ts
import { Client } from "@langchain/langgraph-sdk";

let client: Client | null = null;

export function getAPIClient(): Client {
  if (!client) {
    client = new Client({
      apiUrl: process.env.NEXT_PUBLIC_LANGGRAPH_BASE_URL || "/api/langgraph",
    });
  }
  return client;
}
```

所有后端通信通过这一个 `Client` singleton，由 `@langchain/langgraph-sdk` 提供。

### 流式对话循环

```
User types message
    │
    ▼
input-box.tsx 提交 → 调用 thread hooks
    │
    ▼
useThreadStream (core/threads/hooks.ts)
    │  使用 useStream from @langchain/langgraph-sdk/react
    │  订阅 SSE events: values, messages-tuple, custom, end
    │
    ├── values → 更新 ThreadState context
    │    (messages, artifacts, todos, title)
    │
    ├── messages-tuple → 增量渲染
    │    AI 文本: delta 拼接 (streamdown 流式 markdown 渲染)
    │    tool_call: 展示工具调用
    │    tool_result: 展示工具结果
    │
    ├── custom → 特殊事件处理
    │    task_started/running/completed → 子 Agent 状态更新
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

`app/mock/` 提供静态 demo 模式，所有后端 API 被 mock，用于展示型部署（如项目官网）。🆕 同步 #6：stub 响应构造统一到 `core/api/static-response.ts`（#5302），并支持独立 demo API + 运行时 GitHub stars（`app/github-stars/route.ts` + landing `star-counter.tsx`）。

## 🆕 同步 #6 架构要点

- **Dev bundler**：`pnpm dev` 走 `scripts/dev.mjs`，**Webpack 为跨平台默认**（Turbopack 的 PostCSS worker 泄漏 #5132 未在上游稳定修复），`DEER_FLOW_DEV_BUNDLER=turbo|webpack` 可覆盖，非法值直接报错
- **新 core 模块**：`core/projects/`（api/hooks/types + composer-attach 跨路由附件交接）、`core/trash/`、`core/conversation-references/`、`core/threads/message-order.ts` + `stream-state.ts`（排序/流状态纯函数化）、`core/settings/user-preferences*`（账号偏好同步）、`core/models/favorites*`（模型收藏）、`core/auth/permissions.ts`（Phase 4 权限门控）、`core/artifacts/delimited-preview*`（Worker 内 CSV/TSV 预览）
- **目录迁移**：能力管理从 `settings/` 迁到 `workspace/capabilities/`（`/workspace/capabilities` 页面）；`ai-elements/model-selector.tsx` 删除，改为 `workspace/model-picker-content.tsx`
- 依赖：next 16.2→16.3、新增 papaparse（表格预览）；测试 runner 为 rstest
