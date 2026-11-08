---
title: "两种流式策略：增量流式 vs 阻塞等待"
description: "DeerFlow 的 IM 通道有两个代码路径，由 `supports_streaming` 属性决定："
topics: [channels, im, messaging]
---

# 两种流式策略：增量流式 vs 阻塞等待

DeerFlow 的 IM 通道有两个代码路径，由 `supports_streaming` 属性决定：

```python
# manager.py:139-149 — 能力表只在拿不到 channel 实例时兜底
CHANNEL_CAPABILITIES = {
    "buzz":     {"supports_streaming": True},
    "dingtalk": {"supports_streaming": False},   # 实例属性实为 bool(card_template_id)
    "discord":  {"supports_streaming": False},
    "feishu":   {"supports_streaming": True},
    "github":   {"supports_streaming": False},
    "slack":    {"supports_streaming": False},
    "telegram": {"supports_streaming": True},
    "wechat":   {"supports_streaming": False},
    "wecom":    {"supports_streaming": True},
}
```

真实判定走 `ChannelManager._channel_supports_streaming()`（`manager.py:1278-1286`）：先取 channel 实例的 `supports_streaming` 属性（`base.py:73` 默认 `False`，`dingtalk.py:165` 返回 `bool(self._card_template_id)`），取不到实例才回退到上面的表。

## Strategy A: 增量流式（Feishu、WeCom、Telegram、DingTalk Card、**Buzz**）

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

        # 刷新门：距上次发布 ≥1.0s 或新增 ≥60 字符（OR 逻辑）
        if time_since_last_update >= 1.0 or new_chars >= 60:
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

`_merge_stream_text()`（`manager.py:700-715`）的合并逻辑：
- 如果新 chunk **严格更长且以现有文本开头** → 判定为累积快照，直接替换
- 其余一律当作 delta **追加**——包括「现有文本以 chunk 开头」和 `chunk == existing`（CJK 叠字如 `谢`+`谢`），因为 channel 只把 `messages-tuple` 的 delta 喂给这个函数，同内容 delta 仍代表一个新 token；`values` 快照走另一条分支

这处理了 LangGraph `messages-tuple` 模式中可能出现的累积重发问题。

### 节流

`STREAM_UPDATE_MIN_INTERVAL_SECONDS = 1.0`、`STREAM_UPDATE_MIN_CHARS = 60`（`manager.py:81-82`）——两个条件是 **OR**：距上次发布满 1.0s，或自上次发布以来新增 ≥60 字符就立刻刷新。防止高速 chunk 到达时频繁调用平台 API（大部分 IM 平台有频率限制）。

### 各平台实现

**飞书（Feishu）：**
- 第一条非 final 消息 → 创建 "running card"（`config.update_multi=true` 允许后续 patch）
- 后续非 final 消息 → PATCH 同一个 card
- `is_final=True` → 最终 PATCH + 添加 "DONE" emoji reaction

**WeCom（企业微信）：**
- 使用 `reply_stream()` WebSocket 命令 → 向同一个 `stream_id` 推送文本
- `is_final` 控制流是否结束
- 如果 thread 追踪丢失 → fallback 到 `send_message()`
- **20480 UTF-8 字节协议上限**（#5148）：WeCom bot 协议对消息内容按**字节**（非字符）封顶（`_WECOM_MAX_CONTENT_BYTES`）。流式回复按字符边界裁剪并附加截断标记——一条 stream 携带整个回复，不能中途换流；主动推送拆成**最多 10 条顺序 markdown 消息**，剩余尾部裁剪 + 标记终止。每聊天的发送锁把整个拆分批次端到端串行化（manager worker 并发运行，否则两个长推送到同一聊天会交错分块）；锁按引用计数回收，注册表不随 Gateway 生命周期增长

**Telegram：**
- 首条非 final 消息创建一条 bot 消息，后续用 `edit_message_text` **原地编辑**（`telegram.py:214-296`）
- 自有节流：私聊 1.0s（`STREAM_EDIT_MIN_INTERVAL_SECONDS`）、群聊 3.0s（`STREAM_EDIT_GROUP_MIN_INTERVAL_SECONDS`，群组被 Telegram 限制 20 条/分钟），限流时丢弃该次更新
- `is_final=True` → 优先 Rich Message 编辑，失败则 finalize/分割发送；in-flight 编辑消息表上限 256 条（`MAX_TRACKED_STREAM_MESSAGES`）

**DingTalk（钉钉）AI Card 模式：**
- 创建 interactive card → 通过 `PUT /v1.0/card/streaming` 推送更新
- Card 创建或 streaming API 失败时 → fallback 到 `sampleMarkdown`

**Buzz（Nostr）🆕：**
- 首条 kind-9 聊天事件，流式更新用 **kind-40003 原地编辑**（`e` tag 指向目标事件）——每条更新都是不可变公开 Nostr 事件
- 内容按 UTF-8 字节分块（`EDIT_MAX_BYTES=60000`，relay 64KB 编辑帽的余量）
- `send()` 拒绝发布带 `<memory>`/`<durable_context_data>`/`<system-reminder>` 隐藏包装的文本——Buzz 上泄露是永久的（原始事件留在 relay 上）。详见 [06-buzz.md](06-buzz.md)

## Strategy B: 阻塞等待（Slack、Discord、WeChat、DingTalk non-Card）

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
- **Discord：** 在 Discord thread 内回复，2000 字符处自动分割；**出站跨 loop await 有界**（#5227）——所有出站调用（`send`/`send_file`/频道解析）经 `_run_on_discord_loop` 调度到 Discord 客户端线程的 loop，普通发送 30s（`DISCORD_OUTBOUND_TIMEOUT_SECONDS`）、文件上传 120s（`DISCORD_UPLOAD_TIMEOUT_SECONDS`，无尺寸上限的 payload 要给慢上行 + 429 retry-after 留余量）；loop 缺失或未运行时立即 `RuntimeError` 快速失败——死客户端变成一条有日志的发送失败，而不是永久挂死的 ChannelManager worker；`is_running` 报告客户端线程存活（与 Feishu 相同），让 `ensure_channel_ready` 能在 `_run_client()` 因致命错误退出后重启频道
- **WeChat：** 直接发送消息 + 文件上传

## 策略对比

| 维度 | 增量流式 | 阻塞等待 |
|------|---------|---------|
| **首 token 延迟** | 低（~100ms 看到实时输出） | 高（Agent 完全完成后才看到） |
| **API 调用次数** | 每 1.0s 或每新增 60 字符一次 | 1 次 |
| **用户感知** | 看到 Agent "思考过程" | 只看到最终结果 |
| **平台要求** | 消息可编辑/替换 | 消息只需发送 |
| **代码复杂度** | 较高（累积、节流、补丁） | 较低（一次性发送） |
| **适用平台** | 飞书、WeCom、Telegram、钉钉（Card）、Buzz（Nostr）🆕 | Slack、Discord、微信、钉钉（无 Card 模板） |

阻塞等待在 Agent 执行 30 秒以上的任务时用户体验差——用户无法区分 "Agent 在思考" 和 "系统挂了"。增量流式通过持续更新让用户感知到 Agent 的进展。
