---
title: "Channel→Thread ID 持久化与命令系统"
description: "ChannelStore 协议与两种实现（SQL 表 / 历史 JSON）、跨实例绑定收敛、用户连接映射，以及 IM 命令系统。"
topics: [channels, im, messaging]
---

# Channel→Thread ID 持久化与命令系统

## ChannelStore — 协议 + 两种实现

`app/channels/store.py`（436 行）把"平台会话 → DeerFlow thread"的映射抽象成 `ChannelStore` 协议（`store.py:60`），有两个实现。v2.1.0 只有文件版；v2.2.0 引入 SQL 版并保留 JSON 版作为 `database.backend: memory` 与一次性导入的来源。

### `ChannelStore` 协议（`store.py:60-80`）

```python
class ChannelStore(Protocol):
    async def get_thread_id(self, channel_name, chat_id, topic_id=None) -> str | None: ...
    async def set_thread_id(self, channel_name, chat_id, thread_id, *, topic_id=None, user_id="") -> None: ...
    async def claim_thread_id(self, channel_name, chat_id, thread_id, *, topic_id=None, user_id="") -> str: ...  # 🆕
    async def remove(self, channel_name, chat_id, topic_id=None) -> bool: ...
    async def list_entries(self, channel_name=None) -> list[dict[str, Any]]: ...
```

`claim_thread_id()` 是 v2.2.0 新增的**插入-若缺**语义：绑定已存在就返回既有的 thread，不存在才写入并返回传入的 thread。它是跨实例收敛的关键（见下）。

### 实现一：`SqlChannelStore`（`store.py:243`）

绑定落在应用数据库的 **`channel_thread_bindings`** 表（`deerflow/persistence/channel_thread_bindings/model.py`）。共享同一数据库的所有 Gateway 副本看到同一份绑定——在副本 A 建立的会话，下一条消息落到副本 B 时仍进同一个 thread。

- 行形状与 JSON 条目 **1:1**，使一次性导入无损：`created_at` / `updated_at` 仍是 epoch 秒，`user_id` 是 manager 记录的平台发送者 id（未知时 `""`，绝不是 NULL），`channel_name` / `chat_id` / `topic_id` 三列是旧版 `list_entries()` 从键里解析出的分量。查询始终走主键 `key`（`binding_key()`，`model.py:39`）。列长上限：channel 64、chat 255、topic 255、thread 64、user 255（`model.py:29-34`）。
- 仓储方法：`get_thread_id`（`sql.py:89`）、`upsert`（`:93`）、`claim`（`:104`）、`delete`（`:112`）、`delete_prefix`（`:118`）、`list`（`:126`）、`count`（`:134`）、`insert_missing`（`:138`）。
- **一次性导入** `import_legacy_json()`（`store.py:276`）：`ChannelService.start()` 调一次。若 `store.json` 存在且表为空，逐条以 `ON CONFLICT DO NOTHING` 插入（两个副本同时启动也不会重复或互相覆盖），然后把文件改名为 `store.json.migrated`（`MIGRATED_SUFFIX = ".migrated"`，`store.py:57`）；表非空则**保留文件不动**（表是事实来源，操作者可能还想留档）；文件损坏则保留并报告；缺失是 no-op。格式非法或超列的条目被跳过并计数告警。
- 因为是 async 引擎，协议本身设计成 async，SQL 实现直接在 async engine 上跑，绝不阻塞 Gateway 事件循环。

### 实现二：`JsonChannelStore`（`store.py:91`）

历史单文件 `{base_dir}/channels/store.json`，进程内只加载一次，每次变更整体原子重写：

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

原子写入：

```python
with tempfile.NamedTemporaryFile(dir=base_dir, delete=False) as tmp:
    json.dump(data, tmp)
os.replace(tmp.name, store_path)  # 原子操作——写入要么完全成功，要么完全不影响旧文件
```

`tempfile.NamedTemporaryFile` + `os.replace()` 确保 crash-safe——即使在写入中途崩溃，旧文件也保持完整。文件 I/O 全部经 `asyncio.to_thread` 离线程（由 `tests/blocking_io/test_channel_thread_binding_store.py` 锚定）。**多进程下这是不安全实现**：每个进程各加载一份，副本间互不可见，并发写会互相覆盖——所以它只保留给 `memory` 后端。

读同步（#5083，v2.1.0 内容仍有效）：`get_thread_id()` 与 `list_entries()` 也在锁内读取——此前只有写路径持锁，多线程通道（独立 thread + event loop）下读-写并发可能读到撕裂的 dict 状态；`list_entries()` 改为锁内快照拷贝后再解析，避免迭代中被并发修改。

### 选择逻辑

`resolve_channel_store(app_config, *, session_factory=..., path=None)`（`store.py:403`）：

| `database.backend` | 结果 |
|--------------------|------|
| `memory`（或没有配置） | `JsonChannelStore` |
| `sqlite` / `postgres` 且持久化引擎已初始化 | `SqlChannelStore` |
| `sqlite` / `postgres` 但引擎未初始化 | 回退 `JsonChannelStore` + **warning**（裸 `ChannelService`、无 Gateway lifespan 的测试场景） |

`ChannelService` 构造时按此解析并注入（`service.py:237`），同时把它作为 `channel_store` 传给每个通道实例（`service.py:781`）。

### 新建会话的跨实例收敛 🆕

`ChannelManager` 取 thread 的路径（`manager.py:3187-3203`）：

1. `_lookup_thread_id(msg)`（`manager.py:2812`）→ `connection_identity.lookup_thread_id()`；
2. 未命中则按 `(channel_name, chat_id, topic_id)` 拿**进程内 per-conversation 创建锁** `_thread_create_locks.hold(key)`，锁内**再查一次**（并发消息可能已经建好）；
3. 仍未命中才 `_create_first_thread()`（`manager.py:3061`）：先建 Gateway thread，再 `_claim_thread_id()`（`manager.py:2835`）插入-若缺。

如果 claim 返回的 thread 与刚建的不同，说明另一个实例/另一条任务先绑定了——本实例**采纳胜者的 thread**，并在自己刚 mint 出 thread（而非通道指定 id）时把它删掉（`_delete_unbound_thread()`，`manager.py:3090`），避免留下无人引用的空 thread、也避免覆盖绑定把会话劈成两半。

### 各平台 topic_id 语义

不同平台对 "对话线程" 有不同的概念，DeerFlow 适配了每种：

| 平台 | topic_id | 含义 |
|------|---------|------|
| **Feishu** | 回复时 = `root_id`（原消息），新消息时 = `msg_id` | 同一 thread 的所有回复共享一个 DeerFlow thread |
| **WeCom** | `user_id` | 每个用户一个持久 thread（更像 DM 模式） |
| **Slack** | `thread_ts` | Slack thread = DeerFlow thread（1:1 映射） |
| **Telegram** | `None` | 整个 Telegram chat 共享一个 DeerFlow thread |
| **Discord** | Discord thread ID | 自维护独立的 thread 映射 JSON 文件 |
| **WeChat** | `None` | 整个 chat 共享一个 DeerFlow thread |
| **QQ** 🆕 | `None`（C2C）/ 群 `group_openid` 维度 | C2C 整个会话共享；群内按群维度共享 |
| **DingTalk** | 取决于会话类型 | 群聊 vs 单聊行为不同 |

另有 `CHAT_SCOPED_WORKSPACE_CHANNELS = frozenset({"telegram", "feishu", "wechat"})`（`manager.py:265` 一带）标记"工作区即聊天"的通道，其 `workspace_id` 与 `chat_id` 同源。

### Thread 创建流程

```
收到消息
  │
  ├─ _lookup_thread_id(msg)   → connection_identity.lookup_thread_id()
  │     ├─ 找到 → 使用已有 thread
  │     └─ None → 进程内 per-conversation 锁 + 复查
  │           └─ 仍 None → client.threads.create(metadata={"channel": ..., "chat_id": ...})
  │                 └─ store.claim_thread_id(...)   # 插入-若缺
  │                       ├─ 返回本 thread → 采用
  │                       └─ 返回别人的 thread → 采纳 + 删除自己多建的
  └─ _handle_chat(msg, thread_id)
```

创建时在 thread metadata 中记录 channel 信息——方便调试时反向查找。已有 IM thread 的源信息由 `_update_thread_channel_metadata()`（`manager.py:3204`）**最佳努力补写**一次（metadata 对一条 thread 是常量，manager 生命周期内 `_channel_metadata_synced` 去重，避免每条入站都 PATCH）。

**未解析 ≠ 未命中** 🆕：store 查询超时或出错（`StoreLookupUnresolved`）不能当成"没有绑定"，否则会为一个其实已有映射的会话新开 thread。Feishu 的实现最完整（`feishu.py` 头部注释）：查询预算按消息**到达时刻**起算（不是到达其 chat 队列头时刻），命中的消息延后到 Gateway loop 重试并按退避加重试，直到数据库自身的命令预算用尽才丢弃；每个延后的消息在路由前就持有 bus 入站预留，所以延后积压被 `inbound_queue_maxsize` 同样约束（无法准入就丢弃并告警，绝不排队）。

### SQL 版映射（`ChannelConnectionRepository`，用户连接场景）

上面两条是**无连接归属**的全局回退映射。当 channel 以"用户连接"形态运行时（消息带 `connection_id` + `owner_user_id`），映射落在另一张表 **`channel_conversations`**（`persistence/channel_connections/model.py:100`），由 `ChannelConnectionRepository`（`persistence/channel_connections/sql.py:58`）读写——这是有意的设计区分：那些行属于用户自己的连接。

| 方法 | 位置 | 契约 |
|------|------|------|
| `set_thread_id(*, connection_id, owner_user_id, provider, external_conversation_id, thread_id, external_topic_id=None)` | `sql.py:555` | upsert：按 `(connection_id, external_conversation_id, external_topic_id or "")` 查行；不存在则 insert，存在则更新 `thread_id` + `owner_user_id` + `provider`（**owner 可转移**）。竞态下后写的 INSERT 违反 `uq_channel_conversation_connection_external`（`model.py:119`）时回滚改走 update。用于 `/new` 之类的**重绑定** |
| `claim_thread_id(...)` | `sql.py:606` | 插入-若缺：`INSERT ... ON CONFLICT DO NOTHING` 让先写者胜出，同事务内的 SELECT 返回胜出的行（Postgres READ COMMITTED 读到对端已提交行；SQLite 串行化写入）。用于**首次绑定** |
| `get_thread_id(connection_id, external_conversation_id, external_topic_id?)` | `sql.py:654` | 返回该外部会话当前绑定的 `thread_id`，无则 `None` |

`ChannelManager._lookup_thread_id()` / `_store_thread_id()`（`manager.py:2815`）/ `_claim_thread_id()`（`manager.py:2835`）都先看 `msg.connection_id and msg.owner_user_id and self._connection_repo is not None`：满足就走连接仓储，否则走 `self.store`。差异：全局映射按 `(channel, chat_id, topic_id)` 索引，连接映射按**连接**索引——同一个 IM 会话在不同用户连接下是不同 thread，这是"用户各自绑定自己的 IM 账号"的必然结果（用户连接形态见 [05-user-connections.md](05-user-connections.md)）。

## 命令系统

`app/channels/commands.py`（91 行）定义了已知命令集：

```python
KNOWN_CHANNEL_COMMANDS: frozenset[str] = frozenset(
    {
        "/agent",      # 列出/切换会话的 custom agent
        "/bootstrap",  # 创建 custom agent
        "/goal",       # 设置/查看目标（v2.2.0 起文案由 goal_status.py 生成）
        "/new",        # 开始新对话（创建新 thread）
        "/status",     # 查询当前 session 状态
        "/models",     # 列出可用模型
        "/model",      # 🆕 v2.2.0：查看/切换模型
        "/memory",     # 查询/管理用户记忆
        "/help",       # 显示帮助
    }
)
```

命令集是**唯一事实来源**：各通道解析器（如 Feishu）与 manager 都从这里取，增删命令只需改这一处。同一文件里还有 `_is_leading_mention_token()`（`commands.py:26`）——只在消息**开头**剥掉 `@_user_1` / `@bot` / `<@U123>` 这类传输噪声，使 `@bot /connect <code>` 仍能绑定，以及 `extract_connect_code()`（`commands.py:67`）从文本里抽绑定码。

命令由 `_handle_command()`（`manager.py:3714` 一带）处理：
- `/new` → 创建新 thread + 更新 store 映射（连接形态走 `set_thread_id` 重绑定），并通知已启动通道 `on_thread_replaced(old_thread_id)`（`manager.py:1705`，Feishu 借此退休该线程的待答卡片）
- `/agent list` → 只读当前生效 owner 的 custom agents（上限 50 个、描述截断 120 字符）；`/agent use <name>` → 在同一 owner bucket 校验后**创建新 thread** 并把选择持久化进 thread metadata；`/agent use lead_agent` 回到默认 agent
- `/goal` → v2.2.0 🆕 文案统一由 `goal_status.py`（125 行）生成，语义对齐 Web 端 `describeGoalBar`：进行中的 goal 压过已达成记录；run 在飞时不显示上一轮留下的 stand-down；空闲时依次显示 stand-down、暂停的自动续跑、普通已设目标。停止原因是宿主写的代码（`contracts/thread_goal_contract.json`），用定时通知文案表表述，**从不**把评测器原话或 provider 错误发出去。
- 其余 → 转发到 Gateway API → Agent 处理（命令本身是特殊的 Agent 交互）

**绑定身份闸门**：`require_bound_identity` 开启（`channel_connections.enabled` 且 `require_bound_identity: true`）时，未绑定用户的命令被拒绝，拒绝文案由 `_get_bound_identity_rejection()`（`manager.py:2745` 一带）产出；拒绝回复本身也是出站消息（带 `connection_id` / `owner_user_id`，走该连接自己的凭据）。

**回复语言** 🆕：`/connect` 与 `/goal` 这类**宿主自撰**文案走 `reply_locale.py`（107 行）——按"绑定者 Web UI 语言 > `channel_connections.notification_locale` > en-US"取语言（`resolve_reply_locale()`），`ReplyLocaleResolver`（`reply_locale.py:47`）由 `ChannelService` 构造一次注入 manager 与每个通道（`service.py:241-243`）；`connect_reply_text()` 按语言与平台名（中文平台名不带空格，拉丁名保留空格）套模板。无 owner 的回复（无效/过期绑定码）用配置默认值。**Agent 输出永不翻译**。

### 会话级 custom agent 选择（#5168，v2.1.0 引入，v2.2.0 仍适用）

Agent 选择是**conversation-scoped** 的：`/agent use <name>` 开新对话并固定该 custom agent，**已有对话绝不在中途切换 agent**。实现要点（`manager.py`）：

- 双 metadata 键：`channel_agent_name`（channel 重启键，manager 热路径缓存、重启后 reload 再路由恢复的 turn）+ **canonical `agent_name`**（Web 的标准路由 metadata，使 Web 端 thread-search 把该 thread 路由到 `/workspace/agents/<name>/chats/<thread_id>`，IM 创建的 thread 在 Web 里继续由同一 custom agent 接管）。`lead_agent` 刻意不写 canonical 键，保持普通 chat 路由。
- 显式选择会在 run context 顶层 + RunnableConfig 的 `context`/`configurable` 三个 carrier 里同时归一化 `agent_name`（重置时三处清除）——Gateway 的兼容合并用 `setdefault` 保留旧值，不先归一化会被 channel 默认值悄悄盖掉。
- 读回走 `_load_thread_agent()`（`manager.py:2853`，进程内缓存 `_thread_agent_names` 上限 `IN_PROCESS_CACHE_MAX_ENTRIES`）。
- 选择跨 Gateway 重启存活，跨 IM/Web 客户端一致。

## Session 配置层叠

ChannelManager 的 `_resolve_run_params(channel_name, user_id)` 通过 4 层合并决定 Agent 的参数：

```yaml
# config.yaml 示例
channels:
  session:                       # 层 2: 全局默认
    assistant_id: lead_agent
    config:
      recursion_limit: 500
    context:
      thinking_enabled: false

  feishu:
    enabled: true
    session:                     # 层 3: per-channel
      context:
        thinking_enabled: true   # 飞书覆盖全局默认
      users:                     # 层 4: per-user
        "ou_xxx":                # 特定用户的飞书 ID
          assistant_id: data-analyst    # 该用户的所有消息发给 data-analyst agent
          context:
            thinking_enabled: false     # 该用户不需要 thinking
```

合并结果（最外层覆盖内层）：
```
DEFAULT (hardcoded) < channels.session < channels.feishu.session < channels.feishu.session.users.ou_xxx
```

`ChannelService` 构造时把 `channels.session` 作为 `default_session`、把各 provider 自己的 `session` 作为 `channel_sessions` 传给 manager（`service.py:246-248`）；`_resolve_session_layer()`（`manager.py:1718`）负责取出 channel 层与 user 层。消息级还可有覆盖（GitHub webhook fan-out 一条 repo 绑多个 agent），走 `_resolve_message_assistant_id()`（`manager.py:1724`）。

这个设计允许细粒度的 per-user Agent 路由——组织中的不同成员可以与不同的 Agent 交互，使用不同的模型和参数。
