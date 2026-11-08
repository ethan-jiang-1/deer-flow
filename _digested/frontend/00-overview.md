---
title: "前端架构全景"
description: 'DeerFlow 前端是一个 Next.js 16 App Router + React 19 应用，通过 SSE 连接到 LangGraph Python 后端。'
topics: [frontend, nextjs, react]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 前端架构全景

DeerFlow 前端是一个 Next.js 16 App Router + React 19 应用，通过 SSE 连接到 LangGraph Python 后端。

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| **框架** | Next.js (App Router) | ^16.4.1 |
| **UI** | React | ^19.0.0 |
| **样式** | Tailwind CSS | 4.x |
| **服务端状态** | TanStack Query | 5.x |
| **流式连接** | @langchain/langgraph-sdk | ^1.5.3 |
| **Markdown 渲染** | streamdown | 2.5.0 |
| **语法高亮** | shiki | 3.x |
| **面板拖拽** | react-resizable-panels | ^4.4.1 |
| **动画** | motion (framer-motion) + GSAP | 12.x / 3.x |
| **UI 原语** | Radix UI (20+ 组件) + 🆕 @headlessui/react ^2.2.9（Lark 插件设置） | various |
| **主题** | next-themes | 0.4.x |
| **表单/校验** | 🆕 zod | ^4.6.6（2.1.0 为 ^3.24.2，插件清单校验随之迁移） |
| **二维码** | 🆕 qrcode.react | 4.2.0（IM 渠道扫码绑定） |
| **文档搜索** | 🆕 Pagefind | 1.5.2（dev 依赖，构建期生成索引） |
| **测试** | Rstest + Playwright（+ happy-dom ^21） | 0.10.x / ^1.62.1 |
| **i18n** | 自建 (en-US + zh-CN) | — |

已移除依赖（2.2.0）：`@xyflow/react`、`hast`、`tokenlens`、`@types/gsap`。`package.json` 新增脚本 `catalog:sync`（`scripts/sync-capability-catalog.mjs`）与 `search:index`（`scripts/build-search-index.mjs`），且 `build` 变成 `next build && pnpm run search:index`；`preview` 变成 `pnpm run build && next start`。

## 目录结构

```
frontend/src/
├── app/                    # Next.js App Router 页面 + layout
│   ├── layout.tsx          # RootLayout (ThemeProvider + I18nProvider)
│   ├── workspace/
│   │   ├── layout.tsx      # WorkspaceLayout（force-dynamic + 认证分支）
│   │   ├── workspace-content.tsx  # QueryClient → 偏好边界 → SidebarProvider → Sidebar + Toaster
│   │   ├── agents/[agent_name]/chats/[thread_id]/page.tsx  # ChatPage — 核心页面（🆕 知识库 scope 选择器 + 欢迎页布局）
│   │   ├── chats/page.tsx + chats/[thread_id]/  # 会话列表（🆕 来源图标/未读点/渠道徽章）与单会话页
│   │   ├── capabilities/page.tsx  # Capability Center（🆕 三 tab：plugins / skills / extensions）
│   │   ├── extensions/[namespace]/[surface_id]/page.tsx  # 🆕 插件页面（server component → PluginPage）
│   │   ├── projects/[id]/page.tsx # 项目详情（threads + documents 双 tab）
│   │   ├── trash/page.tsx  # 回收站（projects/trash 恢复与彻底删除）
│   │   └── scheduled-tasks/page.tsx # 定时任务：🆕 list-first 重写 + run 历史
│   ├── [lang]/docs/        # 🆕 Nextra 文档站（Pagefind 搜索，见 06）
│   └── artifacts/view/     # 独立 artifact 查看路由
├── components/
│   ├── workspace/          # 工作区 UI
│   │   ├── chats/          # ChatBox（🆕 四态右面板）, useThreadChat, use-mark-open-thread-read
│   │   ├── messages/       # MessageList, MessageListItem, MessageGroup, conversation-outline, tool-call-details,
│   │   │                   # 🆕 message-reasoning / message-details-* / knowledge-scope-summary /
│   │   │                   #    scheduled-task-card, scheduled-task-event-line, scheduled-run-prompt / run-duration
│   │   ├── citations/      # 🆕 citation-link / knowledge-source / artifact-link / citation-sources-panel
│   │   ├── changes/        # 🆕 workspace-change-badge / workspace-change-panel
│   │   ├── scheduled-tasks/ # 🆕 任务列表、详情、表单、运行历史行、续期/删除对话框
│   │   ├── browser-view/   # 🆕 浏览器实时画面（WS + binary JPEG 帧）
│   │   ├── mentions/       # 🆕 inline-references（@ 引用 token）
│   │   ├── artifacts/      # 重构后的 Artifact 预览（file-preview / table-preview / standalone viewer）
│   │   ├── projects/       # 项目 documents/threads section
│   │   ├── capabilities/   # Capability Center：skill-gallery, plugin-gallery, extension-gallery, plugin-catalog
│   │   ├── trash/          # trash-view 回收站
│   │   ├── conversation-references/ # composer 会话引用（picker / chip / 按钮）
│   │   ├── knowledge-scope-selector.tsx  # 🆕 知识库 scope 对话框
│   │   ├── plugin-page.tsx / plugin-surfaces.tsx  # 🆕 扩展插件挂载点与 API 绑定
│   │   ├── input-box.tsx   # 输入框 (mode/model/reasoning-effort 选择器, 🆕 @ 引用、/goal、/compact、语音)
│   │   ├── workspace-sidebar.tsx / workspace-sidebar-frame.tsx
│   │   └── command-palette.tsx
│   ├── ai-elements/        # Vercel AI SDK 元素封装（🆕 已删除 14 个：canvas/checkpoint/connection/context/controls/edge/image/node/open-in-chat/panel/plan/sources/toolbar/web-preview）
│   ├── ui/                 # shadcn/ui 组件
│   └── theme-provider.tsx  # next-themes 包装
├── core/                   # 业务逻辑（无 JSX）
│   ├── api/                # LangGraph Client 单例 + CSRF fetcher
│   ├── threads/             # useThreadStream, useThreadHistory, types, thread-branch-tree（分支 lineage）
│   │                        # message-order.ts（deerflow_seq 可信排序）+ stream-state.ts（渲染态 patch 合并）
│   │                        # 🆕 activity.ts（未读轮询）/ origin.ts（thread 来源）/ token-usage.ts
│   ├── projects/            # 🆕 Projects 客户端（api/hooks/types + composer-attach 跨路由附件交接）
│   ├── trash/               # 🆕 回收站 api/hooks（分页列表 / restore / purge / empty）
│   ├── conversation-references/ # 🆕 会话引用 metadata（display-only，权限在 Gateway）
│   ├── messages/            # getMessageGroups, content extraction, usage
│   ├── knowledge/           # 🆕 scope 快照（knowledge_scope）+ 检索目录 API + ragflow 证据
│   ├── citations/           # 🆕 普通检索源（RetrievalSource）读取与 id 解析
│   ├── capabilities/        # 🆕 Capability catalog / installations / install（`/api/capabilities/*`）
│   ├── extensions/          # 🆕 扩展清单、插件页面路由、surface 挂载、@ 提及
│   ├── channels/            # 🆕 IM 渠道绑定（设置页 + 扫码）
│   ├── workspace-changes/   # 🆕 run 级文件变更（summary + api）
│   ├── features/            # 🆕 `GET /api/features` 特性开关（knowledge_base / thread_activity / scheduled_tasks…）
│   ├── subagents/           # 🆕 managed subagent 注册表（列表/创建/更新）
│   ├── sidecar/             # 🆕 侧聊（quoted follow-up）上下文
│   ├── voice-input/         # 🆕 Web Speech 识别封装
│   ├── input-polish/        # 🆕 `POST /api/input-polish` 草稿润色
│   ├── dom/                 # 🆕 render-activity（IntersectionObserver 暂停动画）
│   ├── streamdown/          # remark/rehype 插件配置（无独立 rehype/ 目录，见 01）
│   ├── settings/            # localStorage 偏好 (useSyncExternalStore)
│   ├── i18n/                # 国际化 (React context + 服务端检测)
│   ├── tasks/               # Subtask 状态管理 (React context)
│   ├── subagent-batches/    # 🆕 持久化 subagent 批量执行（查询/控制/JSONL 导出）
│   ├── background-tasks/    # 🆕 MCP 持久化后台任务（查询/取消/详情）
│   ├── artifacts/           # Artifact 内容加载 + 预览
│   ├── uploads/             # 文件上传管线
│   ├── memory/              # 用户记忆 API
│   ├── models/              # 可用模型列表 + 🆕 favorites-store（按 user 隔离的模型收藏）
│   ├── skills/              # Skill 安装管理 + 🆕 export.ts（skill 包导出）
│   ├── settings/            # localStorage 偏好 (useSyncExternalStore)
│   │                        # 🆕 user-preferences.ts + preferences-sync.ts（账号偏好跨浏览器同步）
│   └── mcp/                 # MCP 集成 + 🆕 parse.ts（粘贴 mcpServers 定义的严格解析）
└── styles/
    └── globals.css          # Tailwind v4 @import + CSS 变量 + 自定义动画
```

## 数据流总览

```
LangGraph Server (Python)  ← Gateway 内嵌 runtime
      │ SSE（values / messages-tuple / updates / custom / debug…）
      │ ❗ stream mode 走白名单 sanitize，见 core/api/stream-mode.ts
      ▼
@langchain/langgraph-sdk Client (单例; run 创建走 maxRetries:0 的 StreamRecoveryClient)
      │ 事件分发到回调
      ▼
useStream<AgentThreadState>（reconnectOnMount / fetchStateHistory.limit=1 / throttle:true）
      │ thread.messages[], thread.values, thread.isLoading
      ▼
useThreadStream() [core/threads/hooks.ts:1956]
      │ mergeMessages → core/threads/message-order.ts（deerflow_seq 可信排序）
      │ pendingUsageMessages (token 计数) + ContextUsageBadge（context_usage）
      │ onCustomEvent → stream_replay_gap 恢复 / subtask 更新 / error toast
      ▼
ChatPage → ThreadContext.Provider → KnowledgeSourcesProvider → MessageList
      │ getMessageGroups() → 按类型分组（7 类 + scheduled-task）
      ▼
MessageListItem / MessageGroup / SubtaskCard / ScheduledTaskCard
      │ streamdown remark/rehype 管线 + 链接分流（知识引用 / citation / artifact / 不安全链接）
      ▼
DOM（词级 fade-in 动画）
```

## 🆕 2.1 新功能

| 功能 | 说明 |
|------|------|
| **Voice dictation** | 语音输入（`speech-recognition`） |
| **Branching** | Assistant turn 分支 + side conversations（quoted follow-up） |
| **Citation panel** | Citation sources evidence panel |
| **Workspace change review** | Agent run 的文件变更审查 |
| **Composer polish** | 输入润色 + prompt-history recall（arrow keys） |
| **Slash-skill chips** | Slash activation 渲染为 inline chips |
| **Per-thread drafts** | 恢复每个 thread 的 composer 草稿 |
| **Thinking duration chip** | "thought for N seconds" 显示 |
| **About page version** | 显示真实项目版本 |
| **Regenerate** | 重新生成最新回答 |

### 🆕 同步 #4 新增（e5c62cab）

| 功能 | 说明 |
|------|------|
| **Browser Live** | 浏览器会话实时画面推送到 Custom Agent 聊天（JPEG 帧 + WebSocket） |
| **Edit & rerun** | 编辑最新用户轮次并重跑（`edit-regenerate` 协议） |
| **Inline artifact editing** | 文本 artifact 面板内直接编辑（原子替换 + SHA 校验） |
| **Real-time context usage** | 实时显示上下文窗口用量百分比 |
| **Clarification 表单** | human-input card 结构化表单字段（`fields` v2 协议） |
| **Chat replies during clarification** | 澄清等待期间允许继续发消息 |
| **Pin recent chats** | 固定最近会话 |
| **Per-agent model settings** | 每个 custom agent 独立的 model/生成参数 |
| **Suggestions count** | 配置 follow-up 建议数量 |

### 🆕 同步 #5 新增（431892e1）

| 功能 | 说明 |
|------|------|
| **分支会话树** | Recent chats 用 `thread-branch-tree.ts` 投影分支 lineage，`└─`/`├─` 缩进 + 父标题，坏 parent 保持顶层 |
| **Subagent 批量执行 UI** | `core/subagent-batches/` + `ThreadSubagentBatches`：进度轮询、pause/resume/cancel、retry、JSONL 导出、只读历史模式 |
| **后台任务** | `core/background-tasks/` + `ThreadBackgroundTasks`：MCP 持久化任务列表/详情/取消，capability 门控 |
| **Model-load error banner** | `model-load-error-banner.tsx` 观察共享 `useModels` 查询（不主动启动），失败时显示带 Retry 的 alert |

### 🆕 同步 #6 新增（769589e8，v2.1.0-rc0）

| 功能 | 说明 |
|------|------|
| **Capability Center** | 能力管理迁出 Settings（`/workspace/capabilities`，#5468）：skill-gallery / plugin-gallery / mcp-plugin-manager / skill-export-dialog；`settings/skill-settings-page`、`tool-settings-page` 删除，`integrations-settings-page` 迁移为 `capabilities/lark-plugin-settings` |
| **Projects UI** | `/workspace/projects/[id]`（threads + documents tab）、`projects-section` 侧栏分组、`move-to-project-menu`、composer 附件跨路由交接（`core/projects/composer-attach.ts`，sessionStorage pending list） |
| **Trash / Archive** | `/workspace/trash` 回收站（分页、restore、purge、empty）、`thread-delete-dialog` 删除确认、chats 页 Archived tab + `useThreadArchiveAction` |
| **Conversation references** | composer 引用其他会话（#5465）：picker/chip + run context `conversation_references`；消息上的 metadata 仅作展示，不授予权限 |
| **Conversation outline** | 长对话大纲导航（#5025）：按 human turn 抽章节（≥5 turn 启用），虚拟列表锚点跳转 |
| **Model favorites** | 用户级模型收藏（#5441）：`favorites-store.ts`（按 userId 隔离）+ `model-picker-content.tsx`（旧 `ai-elements/model-selector` 删除） |
| **User preferences 同步** | 账号偏好跨浏览器持久化（#5397，migration 0023）：server 端 GET/PUT + outbox 式本地重试 |
| **Threads 排序/流状态重构** | `core/threads/hooks.ts` 大改（+1225 行）：`message-order.ts` 纯函数排序（`deerflow_seq` server 序，earliest-seq-wins）、`stream-state.ts` 渲染态 patch 合并（title/artifacts/todos/goal） |
| **Artifacts 查看重构** | CSV/TSV 有界表格预览（papaparse + web worker，#5284）、独立 `/artifacts/view` 路由、markdown 在新窗口渲染（#5056）、zip 打包下载（#5117） |
| **Scheduled tasks 增强** | run 历史分页浏览（#5363）、duplicate 任务（#5064）、interval 调度类型（#5291）、固定 custom agent（#5288） |

### 🆕 同步 #8 新增（v2.2.0，1239 commits）

| 功能 | 说明 |
|------|------|
| **知识库 scope** | 每次对话可选 `all / selected / disabled` 与具体数据集·文档，存进 run context 的 `knowledge_scope` 快照（`core/knowledge/scope.ts`，上限 100 数据集 / 1000 文档 / 64 KiB）；composer 的 `KnowledgeScopeSelector` 只在 `GET /api/features → knowledge_base.scope_selection_enabled` 为真时出现 |
| **知识引用** | 正文 `[citation:…]` 指向 `#knowledge-source-<id>` 锚点 → `KnowledgeCitationLink` 徽章 + 证据弹窗；证据只从 `knowledge_search`/`task` 工具的 artifact（`version 1`, `provider: ragflow`）读取 → 02 |
| **流重连加固** | `stream_replay_gap` 事件触发 `recoverStreamReplayGaps()`（≤5 次）；新 tab 接手活跃 run（1s/2s 重试，共 3 次）；`isInactiveRunStreamError` / `isRunNotCancellableError` 分类 409 → 01 |
| **Composer 语义收敛** | `/` 菜单只剩 `/goal` 与 `/compact`；`@` 内联引用（skill / file / conversation / extension，最多 16 个 skill）；IME 组合期 Enter 守卫 → 01 / 03 |
| **定时任务重写** | list-first 页面 + 任务详情/运行历史/停止条件/次数上限（`renew-limits-dialog`）、聊天内 `ScheduledTaskCard` 与生命周期事件行（`task_stopped/task_paused/task_finished`）、`GET /api/threads/{id}/scheduled-task-events` → 03 / 04 |
| **Capability Center 三 tab** | plugins / skills / extensions；个人目录与平台目录分离、`?plugin=` 深链、插件清单 `PluginManifest`（`schema_version 1`，`kind: mcp/cli/native`）→ 04 / 06 |
| **扩展插件页面** | `/workspace/extensions/{namespace}/{surface_id}` 由 server component 解参后渲染 `PluginPage`，surface 在 Shadow DOM 内挂载（样式隔离，不是权限边界）；找不到时给 reload + 跳回 extensions tab |
| **会话可见性** | thread 来源（`deerflow_origin`: extension / github / im_channel / mcp_notification / schedule）、未读点 + 15s `thread-activity` 轮询、打开即精确到"看到的消息"。`POST /api/threads/{id}/read` 带去抖 |
| **message details 面板** | 右侧第四种面板：从 tool call / 消息里选中任意详情，Esc 关闭、标题聚焦、按选中 id 重挂内容 → 02 / 04 |
| **浏览器视图** | WS `/api/threads/{id}/browser/stream?frame_format=binary`；rAF 合帧 + blob URL 回收、10s 握手超时、指数退避重连（800ms→10s，最多 6 次） |
| **workspace-changes 徽章** | run 级文件变更徽章锚定在该 run 最后一条 assistant 气泡（#4555），点开看 unified diff → 02 |
| **文档站搜索** | Pagefind 双语索引（`search:index` 脚本），`DocsHtmlLang` 在切语言时销毁并重建索引，`⌘K` 只归 Nextra 一个实例 → 06 |
| **删除面** | `components/ai-elements/` 14 个模块（canvas/checkpoint/connection/context/controls/edge/image/node/open-in-chat/panel/plan/sources/toolbar/web-preview）、`thread-scheduled-tasks-link.tsx` 与认证代理策略模块 `proxy-policy.ts`（原 `core/auth/`）均已删除 |

## 状态管理三层

| 层 | 机制 | 数据 |
|----|------|------|
| **服务端状态** | TanStack Query | Thread 列表、runs、token usage、models、MCP config；🆕 thread activity、capability catalog/installations、knowledge catalog、scheduled-task runs、workspace changes |
| **流式状态** | LangGraph SDK `useStream` | `thread.messages`, `thread.values`（artifacts, todos） |
| **本地状态** | `useSyncExternalStore` + localStorage | Model 选择、mode、notification 偏好 |
| **UI 上下文** | React Context（核心 4 个 + Auth/Sidebar/Thread 等） | Subtasks, Artifacts, PromptInput, i18n；`createContext` 还出现在 `core/auth/AuthProvider.tsx`、`core/tasks/context.tsx`、`ui/sidebar.tsx`、`workspace/messages/context.ts`、`sidecar/context.tsx`、`browser-view/context.tsx`、`thread-delete-dialog.tsx` 等处 |
