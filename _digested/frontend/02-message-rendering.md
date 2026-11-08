---
title: "消息渲染：Streamdown、Thinking Block、Tool Call 卡片"
description: "消息从原始 LangGraph `Message[]` 到 DOM 经过分组、分类、逐类型渲染的完整链路。"
topics: [frontend, nextjs, react]
---

# 消息渲染：Streamdown、Thinking Block、Tool Call 卡片

消息从原始 LangGraph `Message[]` 到 DOM 经过分组、分类、逐类型渲染的完整链路。

## 消息分组

`getMessageGroups()`（`core/messages/utils.ts`）将每条 LangGraph Message 分入以下类型：

| 组类型 | 条件 | 渲染方式 |
|--------|------|---------|
| `human` | User 消息；🆕 带 `deerflow_scheduled_origin` 时附 `scheduledOrigin` | MessageListItem → AIElementMessage (from="user")；🆕 定时任务的自动 prompt 由 `ScheduledRunPrompt` 渲染；🆕 尾部挂 `KnowledgeScopeSummary`（`data-testid="message-knowledge-scope"`） |
| `assistant` | AI 消息，有内容，无 tool_calls，且不是"流式中尚未定型的部分回答" | MessageListItem → MarkdownContent |
| `assistant:processing` | AI 消息，有 reasoning 或 tool_calls（连续的中间消息**累积进同一个** processing 组）；🆕 无主的 orphan tool 消息也兜底开一个 | MessageGroup → ChainOfThought 展开面板 |
| `assistant:subagent` | AI 消息含 `task` tool_calls | SubtaskCard × N |
| `assistant:present-files` | AI 消息含 `present_files` tool_calls | ArtifactFileList + MarkdownContent |
| `assistant:clarification` | `ask_clarification` 返回的 ToolMessage（`isClarificationToolMessage()`，`utils.ts:1087`） | 内联 MarkdownContent；step 同时留在前一个 processing 组里，保 tool-call 关联 |
| 🆕 `assistant:scheduled-task` | 定时任务工具的 ToolMessage（`scheduleCardResultOf()`，`utils.ts:109`） | 独立 `ScheduledTaskCard`：同一轮里同一 task 只保留最后一次结果 |

内部消息（`summary`, `loop_warning`, `todo_reminder`, `todo_completion_reminder`）通过 `isHiddenFromUIMessage()` 隐藏；`hide_from_ui: true` 与"只有 `<slash_skill_activation>` 标记的空 human"同样不渲染。

两条容易踩的分组约束：

- **有内容又有 reasoning 的 AI 消息只进 `assistant` 气泡**（气泡内部的 `Reasoning` 已经渲染同一段 reasoning）；只有 reasoning、无内容的中间步才留在 processing 组，否则 ChainOfThought 面板会把同一段 thinking 画第二遍（#3868）
- **还没定型的"部分回答"留在 processing 组**：provider 可能在同一 message 上继续追加 tool-call chunk，若立刻当气泡渲染，tool call 到达时文字会从气泡跳进步骤面板（#4304）

## Thinking Block（可折叠推理面板）

`components/workspace/messages/message-reasoning.tsx` 的 `MessageReasoning` —— AI 消息带 reasoning 时（reasoning 与正文可以同时存在）：

```
Reasoning (motion 动画, defaultOpen=false)
  ├─ ReasoningTrigger — 流式中：Shimmer 文案；结束后：RunDurationLabel + 可选 token 数
  └─ ReasoningContent (展开时)
       └─ SafeReasoningContent (reasoningPlugins: remark-gfm + remark-math + rehype-katex)
```

开合策略：`isLoading` 期间强制展开；`hasStreamed` ref 只在本组件**真正流过式**之后才为真——只有这种情况下 `isLoading` 变 false 才会在 1 秒后自动收起；历史消息挂载时 `isLoading` 恒为 false，不会折叠用户已经展开的内容。

**注意：** reasoning content 使用 `reasoningPlugins`——不包含 `rehype-raw`。原因是 LLM 会在 thinking 中幻觉出 HTML 标签（如 DeepSeek 的 `<simd>`、`<schema>`），如果 `rehype-raw` 启用，这些标签会被当作真实 HTML 渲染（导致内容消失或布局错乱）。

### 思考内容的三源提取

```typescript
// core/messages/utils.ts:978 extractReasoningContentFromMessage
// 1. Anthropic 格式
if (message.additional_kwargs?.reasoning_content) return ...

// 2. Anthropic 网关格式
if (message.content?.[0]?.thinking) return ...

// 3. 内联 XML think 标签 → splitInlineReasoningFromAIMessage()（utils.ts:933）
//    结果按 message 对象缓存在 WeakMap 里，键是内容字符串本身（内容重写即重算）
```

在流式场景中，`</think>` 标签可能尚未到达——解析器只需知道 `<think>` 之后的所有内容都可能属于 reasoning。

## Tool Call 卡片

`MessageGroup` 组件将 `assistant:processing` 消息渲染为 ChainOfThought 面板：

```
ChainOfThought (collapsible)
  ├─ Header: "Searching..." / "Reading files..." / "Executing..."
  ├─ Reasoning (如果有): MarkdownContent
  └─ Tool call steps:
       ├─ web_search → Query 参数显示
       ├─ image_search → Query 参数显示
       ├─ web_fetch → URL 显示
       ├─ ls → 目录路径显示
       ├─ read_file → 文件路径显示
       ├─ write_file → 文件路径显示
       ├─ bash → 命令显示
       ├─ ask_clarification → 问题显示
       ├─ write_todos → Todo 列表预览
       └─ generic → Tool 名称 + JSON args
```

每个 tool call 有两个状态：
- **执行中**（streaming）：shimmer 动画 + 参数预览
- **完成**：Tool 返回结果（缩略显示，可展开完整结果）

### 🆕 Details 展开（同步 #6）

`MessageGroup` 每个 tool call 新增 "Details" 按钮（`messages/tool-call-details.tsx`），展开后有界显示完整 payload：tool name、call id、args、tool result，各带复制按钮。序列化由 `core/messages/tool-detail-preview.ts::formatToolDetail()` 负责：

- **总预算 12,000 UTF-16 码元**（`TOOL_PREVIEW_LIMIT`），JSON 节点数上限 + 深度上限 6，WeakSet 防环
- 截断绝不切在代理对中间（高代理项检查回退一个码元），并**为完整 JSON token 预留空间**（先界定输入再 escape，因为 escape 会放大每个字符）
- 返回 `{ text, truncated }`，UI 明示"已截断"

### 🆕 Conversation Outline（同步 #6）

长对话导航（#5025）：`core/messages/conversation-outline.ts::buildConversationChapters()` 把每个 `human` group 抽成一个章节（标题取 user 消息文本，空白归一化、截断到 48 字符）。`CONVERSATION_OUTLINE_MIN_TURNS = 5`——少于 5 个 turn 不显示大纲。UI 端 `messages/conversation-outline.tsx` 渲染章节列表，点击经虚拟消息列表的锚点跳转（跳转前先解除 bottom lock，见 01-stream-pipeline.md）。

## Artifact 预览（同步 #6 重构）

当 `present_files` tool 被调用或 agent 产出 artifact 文件时：

```
ArtifactFileList
  └─ ArtifactFileCard × N
       ├─ 文件类型图标 (image/code/document)
       ├─ 文件名 + 大小
       └─ 点击 → 打开 Artifact 面板 (右侧可拖拽面板)
            ├─ CodeEditor (@uiw/react-codemirror, shiki 语法高亮)
            └─ Markdown/HTML 预览
```

`ArtifactsContext` 管理 artifact 选择状态：
- `selectedArtifact: string | null` — 当前在右侧面板中查看的文件
- `open: boolean` — 右侧面板是否打开
- 选择自动触发 `ChatBox` 的 `ResizablePanelGroup` 从 CLOSE_MODE 切换到 OPEN_MODE

### 本轮新增的三个查看面

| 面 | 入口 | 说明 |
|----|------|------|
| **独立查看路由** | `/artifacts/view?...`（`app/artifacts/view/`） | `artifact-viewer.tsx` 是共享的 standalone reader：Markdown 渲染 + 有界 CSV/TSV 表格预览；`artifact-file-detail.tsx` 的 "在新窗口打开" 走 `window.open`（#5056），`core/artifacts/viewer.ts` 导出 `ARTIFACT_VIEWER_ROUTE` |
| **表格预览** | `artifact-table-preview.tsx` | CSV/TSV delimited 预览（`getTabularDelimiter()` 按语言判定分隔符）：解析在 **Web Worker** 中运行（`core/artifacts/delimited-preview.worker.ts` + `use-delimited-preview.ts`），`delimited-preview.ts` 用 papaparse 只解析有界样本（`DELIMITED_RECORD_LIMIT` / `DELIMITED_COLUMN_LIMIT`），引号感知的记录分隔符探测即使在截断前缀上也能工作；超出上限显示 truncated 提示 + "加载完整内容" |
| **zip 打包下载** | `artifact-file-list.tsx` | 按 run 打包下载（#5117）：`core/messages/artifact-archive.ts::getArtifactArchiveCandidatesByGroupIndex()` 找出每个 run 的最后一个 `assistant:present-files` group 作为下载入口，`core/artifacts/api.ts` 请求 `artifacts-{runId}.zip`，manifest 走 `["artifact-archive-manifest", threadId, runId]` 查询 |

## 🆕 2.2.0：知识引用（knowledge citations）

普通网页引用是"模型写 `[citation:标题]` 加外链 → `CitationLink` 徽章 + hover 卡"；2.2.0 增加了一条**本地知识库证据**链路，形态不同：正文里形如 `[citation:…]` 且 href 指向 `knowledge-source-<id>` 片段锚点的链接只是一个同文档锚点，真正的证据在 tool artifact 里。

```
tool message.artifact.knowledge_sources (version 1, provider: "ragflow")
  → core/knowledge/sources.ts::collectKnowledgeSources(messages)   # 只认原生 tool
  → KnowledgeSourcesProvider（message-list.tsx 包住整个列表）
  → KnowledgeCitationLink / KnowledgeSourcesPanel 按 id 查表
```

| 层 | 位置 | 关键约束 |
|----|------|---------|
| 证据来源 | `collectKnowledgeSources()`（`core/knowledge/sources.ts`） | 只读 `message.type === "tool"` 且 `name ∈ {knowledge_search, task}` 的 `artifact.knowledge_sources`；**绝不**相信模型或人类写进消息 metadata 的"证据" |
| 结构校验 | 同上 | `version === 1`、`provider === "ragflow"`、`id` 匹配 `/^[a-f0-9]{32}-[1-9][0-9]{0,2}$/`、每条 sources 最多取 100 条、`document_name`/`dataset_name` ≤1024 字符、`text` ≤200,000 字符、`pages` ≤100 个且为 1..1,000,000 的整数 |
| 重复证据 | 同上 | 流重放可能重复记录；同一 id 只保留第一条，绝不静默覆盖 |
| 锚点解析 | `knowledgeSourceId()` | 接受 `#knowledge-source-<id>` 与 sanitize 加前缀后的 `#user-content-knowledge-source-<id>`（防 DOM clobbering 的前缀） |
| 正文徽章 | `KnowledgeCitationLink`（`citations/knowledge-source.tsx`） | `BookOpenTextIcon` + 文字，`aria-label` 指向 `citations.viewKnowledgeSource(document)`；找不到证据时降级成灰色 span + `sourceUnavailable` 提示 |
| 证据弹窗 | `SourceDialog` | 文档名 / 数据集名 / 页码 / 摘录 blockquote，`truncated` 为真时明示"摘录已截断" |
| 底部 Sources | `KnowledgeSourcesPanel`（`message-list-item.tsx:666`） | `citedKnowledgeSources(markdown, sources)` 只列**该条消息正文真正引用过**的证据（先 `maskCitationCode()` 屏蔽代码块里的伪引用），按首次出现顺序去重；`<details>` 折叠，max-h-80 滚动 |
| 路由分流 | `createMarkdownLinkComponent()`（`messages/markdown-link.tsx`） | 先把 `#knowledge-source-` / `#knowledge-` 分流到知识引用，再执行 `isSafeHref()` 检查（顺序有意：prompt 注入的伪 citation 链接（脚本协议）必须被拦），最后才处理普通 citation 与 artifact 链接 |

普通网页引用的另一半在 `core/citations/sources.ts`：`RetrievalSource` 与 `createKnowledgeSourceReader()`（per-message `WeakMap` 缓存，SDK message 对象不可变，缓存不持有历史）。

## 🆕 2.2.0：workspace 变更徽章

`WorkspaceChangeBadge`（`components/workspace/changes/workspace-change-badge.tsx`）挂在该 run 的**最后一条 assistant 气泡**下面，显示 `N files changed +X -Y`，点开走 Sheet 看 unified diff。

- **数据**：`GET /api/threads/{threadId}/runs/{runId}/workspace-changes?include_files=&include_diff=`（`core/workspace-changes/api.ts`）；徽章只请求 `include_files=true, include_diff=false`，完整 diff 在面板打开时才拉
- **锚点**：`core/messages/workspace-change-anchor.ts::getWorkspaceChangeAnchorGroupIndices()` 为每个 `(threadId, runId)` 只挑**一个** UI 位置——卡片只由 `(threadId, runId)` 决定，一个 run 又可能在多条终止 assistant 气泡里结束（模型输出过中间答案且没带 tool call），不锚定就会重复渲染（#4555）
- **只认 `assistant` 组**：`MessageListItem` 只被 `MessageList` 用于 `human`/`assistant` 组，锚到 `assistant:processing` 组会挑到一个永不渲染的位置、卡片静默消失——所以它故意不与 `getRunDurationDisplaysByGroupIndex`（接受任意类型的 run 末组）统一
- **可用性**：`data.available` 为假或无 `runId` 时整块不渲染（不是显示"0 files"）
- **行分类**：`getWorkspaceChangeLineClass()` 只把 `+++ `/`--- ` 当文件头（裸 `+++`/`---` 前缀会误伤以这些字符开头的内容行）

## Markdown 渲染详情

`MarkdownContent` 组件封装了 `MessageResponse`（Vercel AI SDK 的 streamdown 包装器）：

- **Link 自定义：** `<a>` 标签按顺序判定——① `#knowledge-source-…`/`#knowledge-…` → `KnowledgeCitationLink`；② `isSafeHref()` 不通过 → `UnsafeLink`（保留可见文字但不出链接，防 prompt 注入的脚本协议链接）；③ 普通 citation（href 是外链且子文本带 `citation:` 前缀）→ `CitationLink`（文献引用样式）；④ `/mnt/` 与消息列表内的相对 artifact 路径 → 按 `MessageArtifactPathsContext` 解析成 artifact URL 新窗口打开。外部 URL → `target="_blank" rel="noopener noreferrer"`
- **Image 自定义：** `<img>` 的 artifact URL（`/mnt/user-data/outputs/...`）解析为 artifact blob URL
- **Math：** 通过 `remark-math`（`$...$` 行内 + `$$...$$` 块级）+ `rehype-katex` 渲染
- **GFM：** 表格、删除线、任务列表、autolink（仅在 AI 消息中；用户消息关闭 autolink）
- **Shiki 语法高亮：** `CodeEditor` 组件用于代码块（`CodeBlock`），Shiki 3.x 提供 token 级高亮

## 文件附件渲染

用户上传的文件在消息中以 `RichFileCard` 形式显示：
- 文件类型图标 (PDF/Image/Code/Generic)
- 文件名 + 可读大小
- 图片文件显示缩略图预览
- 上传中状态：`Task` 组件 + Loader + "Uploading..." 文本
- 上传完成 → `element=task` 自动移除

消息中的上传信息存储在 `additional_kwargs.uploaded_files` 中，从流式 AI 消息中提取。
