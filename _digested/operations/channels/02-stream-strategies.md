---
title: "两种流式策略：增量流式 vs 阻塞等待"
description: "DeerFlow 的 IM 通道有两个代码路径，由 `supports_streaming` 属性决定，能力表在 `app/channels/capabilities.py`，真实判定优先问通道实例。"
topics: [channels, im, messaging]
---

# 两种流式策略：增量流式 vs 阻塞等待

DeerFlow 的 IM 通道有两个代码路径，由 `supports_streaming` 属性决定：

```python
# app/channels/capabilities.py:20-31 — 能力表只在拿不到 channel 实例时兜底
CHANNEL_CAPABILITIES: dict[str, dict[str, bool]] = {
    "buzz":     {"supports_streaming": True,  ...},
    "dingtalk": {"supports_streaming": False, ...},   # 实例属性实为 bool(card_template_id)
    "discord":  {"supports_streaming": False, ...},
    "feishu":   {"supports_streaming": True,  ...},
    "github":   {"supports_streaming": False, ...},
    "qq":       {"supports_streaming": False, ...},   # v2.2.0 新增
    "slack":    {"supports_streaming": False, ...},
    "telegram": {"supports_streaming": True,  ...},
    "wechat":   {"supports_streaming": False, ...},
    "wecom":    {"supports_streaming": True,  ...},
}
```

除流式外，每项还带 `proactive_notifications` / `proactive_group_notifications` 两个布尔位（见下节「主动推送能力门」）。表共 **10 项**（9 个 IM + GitHub）；v2.1.0 时这张表内联在 `manager.py`，v2.2.0 抽出到独立模块（`manager.py:31` 导入）。

真实判定走 `ChannelManager._channel_supports_streaming()`（`manager.py:1707-1716`）：先取 channel 实例的 `supports_streaming` 属性（`base.py:154-155` 默认 `False`，`dingtalk.py:216-217` 返回 `bool(self._card_template_id)`），取不到实例才回退到上面的表。

## 主动推送能力门 🆕

同一张表还是「这个 provider 能否接收定时任务推送」的唯一事实来源：

| 辅助函数 | 位置 | 消费者 |
|----------|------|--------|
| `supports_proactive_notifications()` | `capabilities.py:34` | `channel_connections.py:489`（`/providers` 的 `proactive_notifications` 字段，Settings 页据此标注每张 provider 卡） |
| `supports_proactive_group_notifications()` | `capabilities.py:40` | `channel_connections.py:490,679`、`routers/scheduled_tasks.py:138`、`scheduler/notification_delivery.py:254` |

群通知只对 `supports_proactive_group_notifications` 为真的 provider 放开：`POST /api/channels/{provider}/connect` 带 `group_name` 时，不支持者直接 `422`（`channel_connections.py:679`）。实际投递侧还要再过一层目的地校验（`notification_groups.py`：Feishu 群 shape、QQ `<app_id>:group:<group_openid>`）。

## Strategy A: 增量流式（Feishu、WeCom、Telegram、DingTalk Card、Buzz）

### 执行流

```python
async def _handle_streaming_chat(self, msg, thread_id, params):
    stream = client.runs.stream(
        thread_id,
        assistant_id,
        input={"messages": [HumanMessage(content=msg.text)]},
        stream_mode=list(STREAM_MODES),        # ["messages-tuple", "values"]  manager.py:109
        on_disconnect=CHANNEL_RUN_ON_DISCONNECT,  # "continue"                manager.py:123
        ...
    )
    async for chunk in stream:
        # 事件名可能是 "messages-tuple" 或 "messages"（MESSAGE_STREAM_EVENTS，manager.py:110）
        text = _merge_stream_text(...)          # messages-tuple: 逐 token delta
        full_text = _extract_response_text(...) # values: 完整快照

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

`on_disconnect="continue"`（`manager.py:123`）是 IM 的硬要求：manager 把 `runs.stream`/`runs.wait` 请求挂在整条 run 上，这个请求会随 Gateway 实例一起死（leader 交接、滚动重启、崩溃）。默认的 `cancel` 会把 run 本身取消；`continue` 让它跑完并持久化线程状态——IM 回复随传输丢了，但用户仍能在 Web UI 里找到答案。`runs.create`（fire-and-forget）不需要该策略：它的请求在 run 挂起时就返回了。

### 文本累积

`_merge_stream_text()`（`manager.py:1003-1018`）的合并逻辑：
- 如果新 chunk **严格更长且以现有文本开头** → 判定为累积快照，直接替换
- 其余一律当作 delta **追加**——包括「现有文本以 chunk 开头」和 `chunk == existing`（CJK 叠字如 `谢`+`谢`），因为 channel 只把 `messages-tuple` 的 delta 喂给这个函数，同内容 delta 仍代表一个新 token；`values` 快照走另一条分支

这处理了 LangGraph `messages-tuple` 模式中可能出现的累积重发问题。

### 节流

`STREAM_UPDATE_MIN_INTERVAL_SECONDS = 1.0`（`manager.py:104`）、`STREAM_UPDATE_MIN_CHARS = 60`（`manager.py:105`）——两个条件是 **OR**：距上次发布满 1.0s，或自上次发布以来新增 ≥60 字符就立刻刷新。防止高速 chunk 到达时频繁调用平台 API（大部分 IM 平台有频率限制）。

### 各平台实现

**飞书（Feishu）：**
- 第一条非 final 消息 → 创建 "running card"（`config.update_multi=true` 允许后续 patch）
- 后续非 final 消息 → PATCH 同一个 card
- `is_final=True` → 最终 PATCH + 添加 "DONE" emoji reaction
- **澄清按钮卡片** 🆕（`feishu_card_interaction.py`，283 行）：`channels.feishu.card_interaction_enabled` 默认 `false`，开启后选项式澄清渲染成可点击卡片。约束：`MAX_CARD_OPTIONS = 4`（`feishu_card_interaction.py`）、`PENDING_CARD_TTL_SECONDS = 30*60`；`PendingCardEntry`（`:44`）、`ClarificationCardRequest`（`:62`）、`build_button_card()`（`:124`）、`PendingCardRegistry`（`:153`）。注册表是**进程内**的——多实例部署下卡片点击只对收到它的那个实例有效，无法处理即 fail closed。点击路径：SDK loop 上的同步回调 `_on_card_action()` 先校验、回 toast，再走 `_resolve_card_click()` 先注入隐藏的 human-input 响应（`HUMAN_INPUT_RESPONSE_METADATA_KEY`）再放行入站；`/new` 替换线程时 `on_thread_replaced()` 退休该线程的待答卡片。**运维要求**：需在飞书控制台「回调配置」页单独订阅 `card.action.trigger`（与事件订阅不是一处）并发布新版本。
- **SDK 线程有界关闭** 🆕：`stop()` 先请 lark-oapi 私有 loop 关 socket（受 close timeout 限制）再 join 线程；`shutdown_private_loop()`（`base.py`）以 1.0s drain 超时取消 SDK 遗留任务（ping/receive loop），拒绝结束的任务随 loop 一起放弃而不是被 join。

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

**Buzz（Nostr）：**
- 首条 kind-9 聊天事件，流式更新用 **kind-40003 原地编辑**（`e` tag 指向目标事件）——每条更新都是不可变公开 Nostr 事件
- 内容按 UTF-8 字节分块（`EDIT_MAX_BYTES = 60_000`，`buzz.py:66`，relay 64KB 编辑帽的余量；切分函数 `_chunk_text()` 在 `buzz.py:194`）
- `send()` 拒绝发布带 `<memory>`/`<durable_context_data>`/`<system-reminder>` 隐藏包装的文本——Buzz 上泄露是永久的（原始事件留在 relay 上）。详见 [06-buzz.md](06-buzz.md)

## Strategy B: 阻塞等待（Slack、Discord、WeChat、QQ、DingTalk non-Card）

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

即使用户在等待期间发了新消息（这很常见——Agent 可能执行 30 秒），提取器也能正确定位到本轮对话的响应。

### Artifact 分发

`_extract_artifacts()` 扫描最后一条 HumanMessage 之后的 `present_files` tool call：
- 只取本轮产出的 artifact（不重复发送之前的文件）
- `_resolve_attachments()` 将虚拟路径（`/mnt/user-data/outputs/report.pdf`）解析为实际文件系统路径
- 安全检查：只接受 `/mnt/user-data/outputs/` 下的路径

### 各平台实现

- **Slack：** 在 thread 内回复，markdown → Slack mrkdwn 格式转换
- **Discord：** 在 Discord thread 内回复，2000 字符处自动分割；**出站跨 loop await 有界**（#5227）——所有出站调用（`send`/`send_file`/频道解析）经 `_run_on_discord_loop` 调度到 Discord 客户端线程的 loop，普通发送 30s（`DISCORD_OUTBOUND_TIMEOUT_SECONDS`）、文件上传 120s（`DISCORD_UPLOAD_TIMEOUT_SECONDS`，无尺寸上限的 payload 要给慢上行 + 429 retry-after 留余量）；loop 缺失或未运行时立即 `RuntimeError` 快速失败——死客户端变成一条有日志的发送失败，而不是永久挂死的 ChannelManager worker；`is_running` 报告客户端线程存活（与 Feishu 相同），让 `ensure_channel_ready` 能在 `_run_client()` 因致命错误退出后重启频道
- **WeChat：** 直接发送消息 + 文件上传
- **QQ 🆕：** C2C 私聊与群 @ 提及两条时端；单条文本上限 `MAX_TEXT_BYTES = 4000`，超长按截断标记切分；回复条数上限 C2C `C2C_MAX_REPLIES = 4` / 群 `GROUP_MAX_REPLIES = 5`；自带 2048 条入站缓存（`MAX_CACHED_MESSAGES`）与 64 条入站缓冲（`INBOUND_BUFFER_SIZE`）

## 附件投递失败反馈 🆕

附件发送失败不再是静默丢弃。`base.py` 提供共享反馈：

- `attachment_delivery_text(msg, failed, *, unsupported=False)`：生成不含宿主路径、不含 provider 错误原文的文案（中/英双语，按 `msg.metadata["locale"]` 或首行是否含 CJK 判定）；`unsupported=True` 给出「当前渠道不支持发送附件」。
- `Channel._send_attachment_feedback()`：在**同一会话**内回一条纯文本反馈，并剥掉 `pending_clarification` / `human_input_request` 两个 metadata 键——绝不重投文件、绝不改走主动推送；反馈本身再失败只记日志。

## interaction_mode：非交互通道的澄清闸门 🆕

`ChannelRunPolicy.interaction_mode`（`run_policy.py:22,112`）取 `"interactive" | "webhook" | "scheduled" | "autonomous"` 之一，`__post_init__` 校验非法值（`run_policy.py:120-122`）。`ChannelManager._apply_channel_policy()`（`manager.py:2235-2272`）把策略落到 `run_context`：

```python
if policy.interaction_mode is not None:
    run_context["interaction_mode"] = policy.interaction_mode
    if policy.interaction_mode != "interactive":
        run_context["disable_clarification"] = True       # 让 ClarificationMiddleware 不阻塞
elif not policy.is_interactive:
    run_context["disable_clarification"] = True           # 旧字段的回退路径
```

`disable_clarification` 的必要性：`ClarificationMiddleware` 会为一个"等用户同步回复"的 webhook run 死等，而那条回复只会作为**之后另一次**投递到达。GitHub 的策略就是典型：`app/gateway/github/run_policy.py:103` 里 `is_interactive=False, interaction_mode="webhook", default_recursion_limit=250`。

同一次调用还会执行 `credentials_provider`（例如 GitHub 注入可 mint 安装 token 的回调，让 `bash_tool` 每次调用都能拿到新鲜 token，不需要担心 1h TTL）；**凭据失败不丢弃投递**——只记 warning，run 继续（只读好过无响应）。

## 策略对比

| 维度 | 增量流式 | 阻塞等待 |
|------|---------|---------|
| **首 token 延迟** | 低（~100ms 看到实时输出） | 高（Agent 完全完成后才看到） |
| **API 调用次数** | 每 1.0s 或每新增 60 字符一次 | 1 次 |
| **用户感知** | 看到 Agent "思考过程" | 只看到最终结果 |
| **平台要求** | 消息可编辑/替换 | 消息只需发送 |
| **代码复杂度** | 较高（累积、节流、补丁） | 较低（一次性发送） |
| **适用平台** | 飞书、WeCom、Telegram、钉钉（Card）、Buzz（Nostr） | Slack、Discord、微信、QQ 🆕、钉钉（无 Card 模板） |

阻塞等待在 Agent 执行 30 秒以上的任务时用户体验差——用户无法区分 "Agent 在思考" 和 "系统挂了"。增量流式通过持续更新让用户感知到 Agent 的进展。
