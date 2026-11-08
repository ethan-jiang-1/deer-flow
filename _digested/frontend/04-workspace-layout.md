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

> **同步 #6**：最外层新增 `UserPreferencesBoundary`（账号偏好同步，见 03-state-management.md）。

### 🆕 新增工作区路由（同步 #6）

| 路由 | 内容 |
|------|------|
| `/workspace/capabilities` | 🆕 Capability Center（#5468）：Plugins / Skills 双 tab + 搜索框；skill-gallery / plugin-gallery / mcp-plugin-manager / skill-export-dialog / lark-plugin-settings（原 `settings/integrations-settings-page` 迁移改名）都归入 `components/workspace/capabilities/`。**Settings 里的 skill/tool 设置页删除**（`skill-settings-page.tsx`、`tool-settings-page.tsx` 已删，settings-dialog 瘦身） |
| `/workspace/projects/[id]` | 🆕 项目详情页：Threads / Documents 双 tab（`projects/project-threads-section.tsx` + `project-documents-section.tsx`）；`move-to-project-menu.tsx`（会话移动菜单）与 `projects-section.tsx`（sidebar 分组）把项目接进现有导航 |
| `/workspace/trash` | 🆕 回收站：`trash-view.tsx` 分页列表 + 恢复/彻底删除/清空；配合 `thread-delete-dialog.tsx`（权限门控见 03） |
| `/workspace/chats` | 会话总览改为 Active / **Archived** 双 tab（`useThreadArchiveAction` + `thread-archive-status.tsx`） |

项目文档附件走跨路由交接：项目页 Documents tab 附加成功后，`core/projects/composer-attach.ts` 把**已完成的上传结果**（绝不在途上传）暂存 sessionStorage（`deerflow.project-attachment.{threadId}` pending list），跳转到目标线程后 composer 显示为已上传附件，发送或显式移除才清除。

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
│ ├─ ThreadArchiveStatus (归档徽标 + 恢复按钮) │
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

## Projects — 项目工作区（同步 #6）

项目是 thread 之上的新组织维度：thread 通过 `metadata.deerflow_project_id` 归属项目，chat 在项目作用域内创建。

| 组件 | 路径 | 职责 |
|------|------|------|
| 侧边栏项目分组 | `components/workspace/projects-section.tsx` | 可折叠项目组，每组内用 `flattenThreadBranches` 投影成员 thread（与 flat 模式共用 `ThreadSidebarItem`）；标签行提供 **group/flat 显示切换**、新建项目对话框与回收站入口（`projects-trash-link` → `/workspace/trash`） |
| 项目详情页 | `app/workspace/projects/[id]/page.tsx` | header（归档徽标 / New Chat）+ `ProjectThreadsSection`（无限分页成员列表）+ 设置区（重命名/归档/恢复/删除确认对话框）；404 有专门 not-found 态 |
| 移动菜单 | `components/workspace/move-to-project-menu.tsx` | thread 行菜单里把会话移入/移出项目，基于 `projectIdOfThread` 显示当前位置 |
| 作用域新建 | `/workspace/chats/new?project=…` | 聊天页的 project pre-create 在 composer `onPrepareThread` 中先执行——goal 端点会自行物化缺失的 thread 行，未分配行会让幂等 create 返回无项目归属的 thread |

项目详情页的 "New Chat" 链接为 `/workspace/chats/new?project={id}`（未归档项目才显示）。

`GroupedProjectList` 只对已抓取的 infinite thread pages 做**客户端分组**，不额外发请求：`partitionableThreads` 以 `threadListModel.displayedThreads` 为输入，并在路径活跃 thread 超出展示上限时把它追加进来（否则该活跃会话在 flat 列表和项目组里都不显示）；传给各组的 `recentThreadId` 是全局最新 `threadListModel.threads[0]`（与 flat 模式一致），不是各项目组自己的首个 thread；`ArchivedProjectsGroup` 初始折叠。静态 demo 模式（`isStaticWebsiteOnly()`）下整个 section（含新建按钮与显示模式切换）返回 `null`。

### 嵌套 SidebarMenu 的宽度约束（v2.1.0，#5681 → #5682）

grouped 模式用嵌套 `SidebarMenu` 缩进项目内的 thread 行，但 `SidebarMenu` 原语默认带 `w-full`（`cn("flex w-full min-w-0 flex-col gap-1", className)`）：`ml-4`（16px）+ 100% 宽会让容器比侧栏宽 16px，绝对定位的行内 kebab（`right-1`）随之落到可视区外被裁掉；Archived 组（`ArchivedProjectsGroup` 内再套一层 `ProjectThreadGroup`）溢出 32px，kebab 完全不可见。

| 位置 | 修复前 | 修复后 |
|------|--------|--------|
| `ProjectThreadGroup` 的缩进 menu | `border-sidebar-border ml-4 border-l pl-2` | `border-sidebar-border ml-4 w-auto border-l pl-2` |
| `ArchivedProjectsGroup` 的缩进 menu | 同上 | 同上 |
| 根 `SidebarMenu` | 原语默认 `w-full` | 不变 |

`className` 经 `cn()`（tailwind-merge）解析，`w-auto` 覆盖原语的 `w-full`，块级 flex 容器改为「填满剩余宽度 − margin」。回归测试 `frontend/tests/unit/components/workspace/projects-section-nested-menu.dom.test.tsx`（165 行）从预置 query cache 渲染 grouped 模式并展开 Archived 组，断言每个缩进菜单有 `w-auto`、无 `w-full`，根菜单仍为 `w-full`（happy-dom 无布局引擎，故在 class 层面钉住）。

> **可迁移经验**：在定宽容器（侧栏）里给布局原语加横向 margin 时，要同时改掉它的默认宽度（`w-full` → `w-auto`）；`w-full + margin` 必然横向溢出，而绝对定位的尾部操作按钮（kebab）是最先被裁掉的元素。

## Thread 列表虚拟化（同步 #6）

`thread-list-virtualizer.tsx`（`@tanstack/react-virtual`）：侧边栏行、`/workspace/chats` 行、项目页行共用一个最小行模型（只需稳定 `thread_id`），**≥ 60 行才启用虚拟化**；`recent-chat-list.tsx` 用 IntersectionObserver 哨兵触发 `useInfiniteThreads.fetchNextPage()` 无限滚动。列表刷新需用 `calculateScrollMargin` 补偿 root/scroll parent 偏移。

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
