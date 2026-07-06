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
| `human` | User 消息 | MessageListItem → AIElementMessage (from="user") |
| `assistant` | AI 消息，有内容，无 tool_calls | MessageListItem → MarkdownContent |
| `assistant:processing` | AI 消息，有 reasoning 或 tool_calls | MessageGroup → ChainOfThought 展开面板 |
| `assistant:subagent` | AI 消息含 `task` tool_calls | SubtaskCard × N |
| `assistant:present-files` | AI 消息含 `present_files` tool_calls | ArtifactFileList + MarkdownContent |
| `assistant:clarification` | `ask_clarification` 返回的 ToolMessage | 内联 MarkdownContent |

内部消息（`summary`, `loop_warning`, `todo_reminder`, `todo_completion_reminder`）通过 `isHiddenFromUIMessage()` 隐藏。

## Thinking Block（可折叠推理面板）

`components/workspace/messages/message-list-item.tsx` — 当 AI 消息仅有 reasoning 没有 content 时：

```
Reasoning (motion 动画)
  ├─ ReasoningTrigger — "Thinking..." 标签 (BrainIcon + 动画省略号)
  └─ ReasoningContent (展开时)
       └─ Streamdown (reasoningPlugins: remark-gfm + remark-math + rehype-katex)
```

**注意：** reasoning content 使用 `reasoningPlugins`——不包含 `rehype-raw`。原因是 LLM 会在 thinking 中幻觉出 HTML 标签（如 DeepSeek 的 `<simd>`、`<schema>`），如果 `rehype-raw` 启用，这些标签会被当作真实 HTML 渲染（导致内容消失或布局错乱）。

### 思考内容的三源提取

```typescript
// core/messages/utils.ts
function extractReasoningContentFromMessage(message) {
  // 1. Anthropic 格式
  if (message.additional_kwargs?.reasoning_content) return ...

  // 2. Anthropic 网关格式
  if (message.content?.[0]?.thinking) return ...

  // 3. DeepSeek/R1 <think> 标签
  const match = /<think>(.*?)<\/think>/s.exec(message.content)
  // 流式安全：处理未闭合的 <think> 标签
}
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

## Artifact 预览

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

## Markdown 渲染详情

`MarkdownContent` 组件封装了 `MessageResponse`（Vercel AI SDK 的 streamdown 包装器）：

- **Link 自定义：** `<a>` 标签检测 `citation:` 前缀 → 渲染为 `CitationLink`（文献引用样式）。外部 URL → `target="_blank" rel="noopener noreferrer"`
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
