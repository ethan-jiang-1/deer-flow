---
title: "工作区布局：Drag 面板、响应式、Command Palette"
description: "## 顶层 Shell"
topics: [frontend, nextjs, react]
---

# 工作区布局：Drag 面板、响应式、Command Palette

## 顶层 Shell

`app/workspace/workspace-content.tsx`（Server Component）：

```
QueryClientProvider
  SidebarProvider (cookie 持久化 open state)
    WorkspaceSidebar (shadcn/ui Sidebar, collapsible="icon")
      ├─ WorkspaceHeader (brand + "New Chat" 按钮)
      ├─ WorkspaceNavChatList (聊天导航)
      ├─ RecentChatList (sidebar 展开时显示)
      ├─ WorkspaceNavMenu (settings 等，在 footer)
      └─ SidebarRail (拖拽手柄)
    SidebarInset
      {children} — ChatPage
  CommandPalette
  Toaster (sonner, top-center)
```

## ChatBox — 可拖拽双面板

`components/workspace/chats/chat-box.tsx` — 使用 `react-resizable-panels` v4：

```
ResizablePanelGroup (direction="horizontal")
  ├─ ResizablePanel (id="chat", defaultSize=100)
  │     {children} — MessageList + InputBox
  ├─ ResizableHandle (不可见/禁用当 artifact panel 关闭时)
  └─ ResizablePanel (id="artifacts", defaultSize=0)
        Artifact 详情查看器 (CodeEditor / Markdown 预览)
```

两种布局模式：
- **CLOSE_MODE**: `{ chat: 100, artifacts: 0 }`
- **OPEN_MODE**: `{ chat: 60, artifacts: 40 }`

通过 `ArtifactsContext.open` 自动切换。Artifact 面板使用 CSS transition 做滑入/滑出动画。

## ChatPage — 两种视图模式

`app/workspace/chats/[thread_id]/page.tsx`：

### Welcome Mode（新对话或空 thread）

```
┌──────────────────────────────────┐
│          (透明 header)           │
│                                  │
│          <Welcome />             │  ← 品牌 hero 区域
│       (Logo + Tagline)           │
│                                  │
│   ┌──────────────────────────┐   │
│   │       InputBox           │   │  ← 绝对居中垂直对齐
│   │  (mode/model 选择器)      │   │     -translate-y-[calc(50vh-96px)]
│   └──────────────────────────┘   │     --container-width-sm
│                                  │
└──────────────────────────────────┘
```

### Conversation Mode（有消息后）

```
┌──────────────────────────────────┐
│ Sticky Header (backdrop-blur)    │
│ ├─ ThreadTitle                   │
│ ├─ TokenUsageIndicator           │
│ ├─ ExportTrigger                 │
│ └─ ArtifactTrigger               │
├──────────────────────────────────┤
│                                  │
│ MessageList                      │
│ ├─ LoadMoreHistoryIndicator      │  ← IntersectionObserver 上滚加载
│ ├─ Conversation                  │
│ │   ├─ MessageListItem × N       │
│ │   ├─ MessageGroup × N          │
│ │   ├─ SubtaskCard × N           │
│ │   └─ StreamingIndicator        │  ← thread.isLoading 时显示
│ └─ (use-stick-to-bottom)         │  ← 自动滚到底部
│                                  │
├──────────────────────────────────┤
│ InputBox (fixed bottom)           │
│ --container-width-md             │
└──────────────────────────────────┘
```

## Command Palette

`components/workspace/command-palette.tsx` — 基于 shadcn/ui `CommandDialog`（底层 `cmdk`）：

全局快捷键：
| 快捷键 | 操作 |
|--------|------|
| `Cmd+K` | 打开/关闭 Palette |
| `Cmd+Shift+N` | New Chat |
| `Cmd+,` | Settings |
| `Cmd+/` | 键盘快捷键帮助对话框 |
| `Cmd+B` | 切换 Sidebar |

## 主题系统

`next-themes` 的 `ThemeProvider`（`attribute="class"`, `enableSystem`, `disableTransitionOnChange`）：

- **Light 主题：** 暖白色背景 (`oklch(0.9855 ...)`)，黑色 primary
- **Dark 主题：** 深色背景 (`oklch(0.24 ...)`)，白色 primary，轻字重 (`300`)
- Landing page (`"/"`) 强制 dark 主题

CSS 变量通过 `@theme inline` 定义（Tailwind v4 语法）：
- 颜色：`--background`, `--foreground`, `--card`, `--popover`, `--primary`, `--secondary`, `--muted`, `--accent`, `--destructive`, `--border`, `--input`, `--ring`
- Sidebar：`--sidebar`, `--sidebar-foreground`, `--sidebar-primary`, `--sidebar-accent`, `--sidebar-border`, `--sidebar-ring`
- Chart：`--chart-1` 到 `--chart-5`

## 自定义动画

在 `globals.css` 中定义：

| 动画 | 用途 |
|------|------|
| `fade-in` | 词级 text 出现 |
| `fade-in-up` | 消息/组件入场 |
| `skeleton-entrance` | 骨架屏加载 |
| `suggestion-in` | 跟随建议 |
| `shine` | Subtask card shimmer 动画 |
| `ambilight` | Subtask card 活跃光晕 |
| `bouncing` | 省略号跳动 |
| `aurora` | Landing page 背景渐变 |
| `wave` | Landing page 波浪 |

## 响应式

Tailwind v4 的 responsive utilities（`sm:`, `md:`, `lg:`）用于：
- Container 宽度：`--container-width-xs`(72) / `sm`(144) / `md`(204) / `lg`(256)
- Sidebar collapse：窄屏自动图标模式（`collapsible="icon"`）
- Artifact 面板：小屏上全宽显示
