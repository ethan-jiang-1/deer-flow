---
title: "Channel→Thread ID 持久化与命令系统"
description: "## ChannelStore — 文件级持久化"
topics: [channels, im, messaging]
---

# Channel→Thread ID 持久化与命令系统

## ChannelStore — 文件级持久化

`app/channels/store.py` — JSON 文件存储，将平台会话映射到 DeerFlow thread：

### 存储结构

```
{base_dir}/channels/store.json

{
  "<channel_name>:<chat_id>": {
    "thread_id": "<uuid>",
    "user_id": "<platform_user_id>",
    "created_at": 1700000000.0,
    "updated_at": 1700000000.0
  },
  "<channel_name>:<chat_id>:<topic_id>": {
    "thread_id": "<uuid>",
    ...
  }
}
```

### Key 格式

- **根会话：** `"{channel}:{chat_id}"` — 适用于不支持多线程的平台（Telegram、WeChat）
- **主题会话：** `"{channel}:{chat_id}:{topic_id}"` — 适用于有 thread 概念的平台（Slack、飞书、Discord）

### 原子写入

```python
with tempfile.NamedTemporaryFile(dir=base_dir, delete=False) as tmp:
    json.dump(data, tmp)
os.replace(tmp.name, store_path)  # 原子操作——写入要么完全成功，要么完全不影响旧文件
```

使用 `tempfile.NamedTemporaryFile` + `os.replace()` 确保 crash-safe——即使在写入中途崩溃，旧文件也保持完整。

## 各平台 topic_id 语义

不同平台对 "对话线程" 有不同的概念，DeerFlow 适配了每种：

| 平台 | topic_id | 含义 |
|------|---------|------|
| **Feishu** | 回复时 = `root_id`（原消息），新消息时 = `msg_id` | 同一 thread 的所有回复共享一个 DeerFlow thread |
| **WeCom** | `user_id` | 每个用户一个持久 thread（更像 DM 模式） |
| **Slack** | `thread_ts` | Slack thread = DeerFlow thread（1:1 映射） |
| **Telegram** | `None` | 整个 Telegram chat 共享一个 DeerFlow thread |
| **Discord** | Discord thread ID | 自维护独立的 thread 映射 JSON 文件 |
| **WeChat** | `None` | 整个 chat 共享一个 DeerFlow thread |
| **DingTalk** | 取决于会话类型 | 群聊 vs 单聊行为不同 |

### Thread 创建流程

```
收到消息
  │
  ├─ store.get_thread_id(channel, chat_id, topic_id)
  │     ├─ 找到 → 使用已有 thread
  │     └─ None → 创建新 thread
  │           ├─ client.threads.create(metadata={"channel": ..., "chat_id": ...})
  │           └─ store.set_thread_id(channel, chat_id, topic_id, thread_id, user_id)
  │
  └─ _handle_chat(msg, thread_id)
```

创建时在 thread metadata 中记录 channel 信息——方便调试时反向查找。

## 命令系统

`app/channels/commands.py` 定义了已知命令集：

```python
KNOWN_COMMANDS = {
    "/bootstrap",  # 创建 custom agent
    "/new",        # 开始新对话（创建新 thread）
    "/status",     # 查询当前 session 状态
    "/models",     # 列出可用模型
    "/memory",     # 查询/管理用户记忆
    "/help",       # 显示帮助
}
```

命令由 `_handle_command()` 处理：
- `/new` → 创建新 thread + 更新 store 映射
- 其余 → 转发到 Gateway API → Agent 处理（命令本身是特殊的 Agent 交互）

## Session 配置层叠

ChannelManager 的 `_resolve_run_params(channel_name, user_id)` 通过 4 层合并决定 Agent 的参数：

```yaml
# config.yaml 示例
channels:
  default_session:              # 层 2: 全局默认
    assistant_id: lead_agent
    config:
      recursion_limit: 500
    context:
      thinking_enabled: false

  feishu:
    enabled: true
    session:                    # 层 3: per-channel
      context:
        thinking_enabled: true  # 飞书覆盖全局默认

    session:
      users:                    # 层 4: per-user
        "ou_xxx":               # 特定用户的飞书 ID
          assistant_id: data-analyst  # 该用户的所有消息发给 data-analyst agent
          context:
            thinking_enabled: false  # 该用户不需要 thinking
```

合并结果（最外层覆盖内层）：
```
DEFAULT (hardcoded) < default_session < channels.feishu.session < channels.feishu.session.users.ou_xxx
```

这个设计允许细粒度的 per-user Agent 路由——组织中的不同成员可以与不同的 Agent 交互，使用不同的模型和参数。
