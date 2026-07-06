---
title: "两种流式策略：增量流式 vs 阻塞等待"
description: "DeerFlow 的 IM 通道有两个代码路径，由 `supports_streaming` 属性决定："
topics: [channels, im, messaging]
---

# 两种流式策略：增量流式 vs 阻塞等待

DeerFlow 的 IM 通道有两个代码路径，由 `supports_streaming` 属性决定：

```python
# manager.py:40-48
STREAMING_CHANNELS = {
    "feishu": True,
    "wecom": True,
    "dingtalk": True,  # only when card_template_id configured
}
```

## Strategy A: 增量流式（Feishu、WeCom、DingTalk Card）

### 执行流

```python
async def _handle_streaming_chat(self, msg, thread_id, params):
    stream = client.runs.stream(
        thread_id,
        assistant_id,
        input={"messages": [HumanMessage(content=msg.text)]},
        stream_mode=["messages-tuple", "values"],
        config=params["config"],
    )
    async for chunk in stream:
        # messages-tuple: text delta per message-id
        text = _accumulate_stream_text(chunk)
        # values: 完整快照
        full_text = _extract_response_text(chunk)

        # 350ms 最小更新间隔
        if time_since_last_update >= 0.35:
            await bus.publish_outbound(OutboundMessage(
                text=text, is_final=False, ...
            ))

    # Stream 结束
    await bus.publish_outbound(OutboundMessage(
        text=final_text, is_final=True,
        artifacts=extracted_artifacts, ...
    ))
```

### 文本累积

`_accumulate_stream_text()` 的合并逻辑：
- 如果累积快照以现有文本开头 → 用累积快照（delta 有重叠）
- 如果现有文本以累积快照开头 → 保持现有（delta 被包含）
- 否则 → 拼接（新的独立 delta）

这处理了 LangGraph `messages-tuple` 模式中可能出现的重复/重叠的 chunk 问题。

### 节流

`STREAM_UPDATE_MIN_INTERVAL_SECONDS = 0.35` — 两次消息更新之间最少间隔 350ms。防止高速 chunk 到达时频繁调用平台 API（大部分 IM 平台有频率限制）。

### 各平台实现

**飞书（Feishu）：**
- 第一条非 final 消息 → 创建 "running card"（`config.update_multi=true` 允许后续 patch）
- 后续非 final 消息 → PATCH 同一个 card
- `is_final=True` → 最终 PATCH + 添加 "DONE" emoji reaction

**WeCom（企业微信）：**
- 使用 `reply_stream()` WebSocket 命令 → 向同一个 `stream_id` 推送文本
- `is_final` 控制流是否结束
- 如果 thread 追踪丢失 → fallback 到 `send_message()`

**DingTalk（钉钉）AI Card 模式：**
- 创建 interactive card → 通过 `PUT /v1.0/card/streaming` 推送更新
- Card 创建或 streaming API 失败时 → fallback 到 `sampleMarkdown`

## Strategy B: 阻塞等待（Slack、Telegram、Discord、WeChat、DingTalk non-Card）

### 执行流

```python
async def _handle_chat(self, msg, thread_id, params):
    # 阻塞等待 Agent 完成所有 turn
    state = await client.runs.wait(thread_id, ...)

    # 提取最终文本
    text = _extract_response_text(state)
    # 提取产出的 artifacts
    artifacts = _extract_artifacts(state)
    # 解析虚拟路径 → 主机路径
    attachments = _resolve_attachments(artifacts)

    # 一次性发送
    await bus.publish_outbound(OutboundMessage(
        text=text, is_final=True,
        artifacts=artifacts, attachments=attachments,
    ))
```

### 响应文本提取

`_extract_response_text()` 的提取逻辑：
1. 从最后一条 HumanMessage 往后遍历
2. 取最后一条 AIMessage 的文本内容
3. 如果是 `ask_clarification` 中断 → 返回 clarification 内容（Agent 在问用户问题）

即使用户在等待期间发了新消息（这很常见——Agnet 可能执行 30 秒），提取器也能正确定位到本轮对话的响应。

### Artifact 分发

`_extract_artifacts()` 扫描最后一条 HumanMessage 之后的 `present_files` tool call：
- 只取本轮产出的 artifact（不重复发送之前的文件）
- `_resolve_attachments()` 将虚拟路径（`/mnt/user-data/outputs/report.pdf`）解析为实际文件系统路径
- 安全检查：只接受 `/mnt/user-data/outputs/` 下的路径

### 各平台实现

- **Slack：** 在 thread 内回复，markdown → Slack mrkdwn 格式转换
- **Telegram：** 回复消息（threaded reply），长消息自动分割
- **Discord：** 在 Discord thread 内回复，2000 字符处自动分割
- **WeChat：** 直接发送消息 + 文件上传

## 策略对比

| 维度 | 增量流式 | 阻塞等待 |
|------|---------|---------|
| **首 token 延迟** | 低（~100ms 看到实时输出） | 高（Agent 完全完成后才看到） |
| **API 调用次数** | 每次 350ms 间隔一次 | 1 次 |
| **用户感知** | 看到 Agent "思考过程" | 只看到最终结果 |
| **平台要求** | 消息可编辑/替换 | 消息只需发送 |
| **代码复杂度** | 较高（累积、节流、补丁） | 较低（一次性发送） |
| **适用平台** | 飞书、WeCom、钉钉 | Slack、Telegram、Discord、微信 |

阻塞等待在 Agent 执行 30 秒以上的任务时用户体验差——用户无法区分 "Agent 在思考" 和 "系统挂了"。增量流式通过持续更新让用户感知到 Agent 的进展。
