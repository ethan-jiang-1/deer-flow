---
title: "前端架构全景"
description: "DeerFlow 前端是一个 Next.js 16 App Router + React 19 应用，通过 SSE 连接到 LangGraph Python 后端。"
topics: [frontend, nextjs, react]
---

# 前端架构全景

DeerFlow 前端是一个 Next.js 16 App Router + React 19 应用，通过 SSE 连接到 LangGraph Python 后端。

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| **框架** | Next.js (App Router) | 16.x |
| **UI** | React | 19.x |
| **样式** | Tailwind CSS | 4.x |
| **服务端状态** | TanStack Query | 5.x |
| **流式连接** | @langchain/langgraph-sdk | 1.5.x |
| **Markdown 渲染** | streamdown | 1.4.0 |
| **语法高亮** | shiki | 3.x |
| **面板拖拽** | react-resizable-panels | 4.x |
| **动画** | motion (framer-motion) + GSAP | 12.x / 3.x |
| **UI 原语** | Radix UI (20+ 组件) | various |
| **主题** | next-themes | 0.4.x |
| **测试** | Vitest + Playwright | 4.x / 1.x |
| **i18n** | 自建 (en-US + zh-CN) | — |

## 目录结构

```
frontend/src/
├── app/                    # Next.js App Router 页面 + layout
│   ├── layout.tsx          # RootLayout (ThemeProvider + I18nProvider)
│   ├── workspace/
│   │   ├── layout.tsx      # WorkspaceLayout (auth gate)
│   │   ├── workspace-content.tsx  # QueryClient + Sidebar + Toaster
│   │   └── chats/[thread_id]/
│   │       ├── page.tsx    # ChatPage — 核心页面
│   │       └── providers.tsx  # Subtasks + Artifacts + PromptInput providers
├── components/
│   ├── workspace/          # 工作区 UI
│   │   ├── chats/          # ChatBox, useThreadChat
│   │   ├── messages/       # MessageList, MessageListItem, MessageGroup
│   │   ├── artifacts/      # Artifact 预览面板
│   │   ├── input-box.tsx   # 输入框 (mode/model/reasoning-effort 选择器)
│   │   ├── workspace-sidebar.tsx
│   │   └── command-palette.tsx
│   ├── ai-elements/        # Vercel AI SDK 元素封装
│   ├── ui/                 # shadcn/ui 组件
│   └── theme-provider.tsx  # next-themes 包装
├── core/                   # 业务逻辑（无 JSX）
│   ├── api/                # LangGraph Client 单例 + CSRF fetcher
│   ├── threads/             # useThreadStream, useThreadHistory, types
│   ├── messages/            # getMessageGroups, content extraction, usage
│   ├── streamdown/          # remark/rehype 插件配置
│   ├── rehype/              # 自定义 rehype 插件（词级动画）
│   ├── settings/            # localStorage 偏好 (useSyncExternalStore)
│   ├── i18n/                # 国际化 (React context + 服务端检测)
│   ├── tasks/               # Subtask 状态管理 (React context)
│   ├── artifacts/           # Artifact 内容加载 + 预览
│   ├── uploads/             # 文件上传管线
│   ├── memory/              # 用户记忆 API
│   ├── models/              # 可用模型列表
│   ├── skills/              # Skill 安装管理
│   └── mcp/                 # MCP 集成
└── styles/
    └── globals.css          # Tailwind v4 @import + CSS 变量 + 自定义动画
```

## 数据流总览

```
LangGraph Server (Python)
      │ SSE (values, messages-tuple, events, custom)
      ▼
@langchain/langgraph-sdk Client (单例)
      │ 事件分发到回调
      ▼
useStream<AgentThreadState> (LangGraph SDK React)
      │ thread.messages[], thread.values, thread.isLoading
      ▼
useThreadStream() [core/threads/hooks.ts]
      │ mergeMessages(history, stream, optimistic)
      │ pendingUsageMessages (token 计数)
      │ onCustomEvent → subtask 更新, error toast
      ▼
ChatPage → ThreadContext.Provider → MessageList
      │ getMessageGroups() → 按类型分组
      ▼
MessageListItem / MessageGroup / SubtaskCard
      │ streamdown remark/rehype 管线
      ▼
DOM (词级 fade-in 动画)
```

## 状态管理三层

| 层 | 机制 | 数据 |
|----|------|------|
| **服务端状态** | TanStack Query | Thread 列表、runs、token usage、models、MCP config |
| **流式状态** | LangGraph SDK `useStream` | `thread.messages`, `thread.values`（artifacts, todos） |
| **本地状态** | `useSyncExternalStore` + localStorage | Model 选择、mode、notification 偏好 |
| **UI 上下文** | React Context (4 个) | Subtasks, Artifacts, PromptInput, i18n |
