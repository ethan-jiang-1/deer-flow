---
title: "Record/Replay E2E 测试"
description: "ReplayChatModel 确定性 Gateway 测试：输入哈希匹配、volatile 字段归一化、caller-aware key、golden JSON。零 API key。"
topics: [testing, e2e, record-replay, deterministic]
---

# Record/Replay E2E 测试

DeerFlow 最先进的测试模式。录一次（需要 API key），永久回放（零 API key，毫秒级）。

## 架构：三文件协作

| 文件 | 用途 |
|------|------|
| `tests/_replay_fixture.py` | 共享 config builder + Gateway 驱动 + SSE 形状提取 |
| `tests/replay_provider.py` | `ReplayChatModel` — 416 行确定性 LLM |
| `tests/test_replay_golden.py` | Layer 1 replay：构造 Gateway → 断言 event 序列 |

## ReplayChatModel 核心机制

录下来的 trace 按**归一化输入哈希**索引，不按调用序号——因为 lead agent、TitleMiddleware、subagent 的模型调用交错发生。

### 1. 输入归一化（哈希前消除 volatile 字段）

```python
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-...-[0-9a-fA-F]{12}")
_ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
_PATH_RE = re.compile(r"(?:/private)?/(?:var/folders|tmp)/[^\s\"']*")
_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
```

### 2. System message 排除

System prompt 是实现细节——把它放进哈希会让每次 prompt 改动导致全部 fixture 失效：

```python
def _canonical_messages(messages: list[BaseMessage]) -> str:
    for message in messages:
        if message.type == "system":
            continue  # 排除
        if additional_kwargs.get("hide_from_ui"):
            continue  # 框架注入也排除
```

### 3. Caller-aware key

不同调用方（lead agent、title middleware、evaluator）可能对相同对话发出相同 LLM 调用。`hash_input_key` 把 caller identity 编入 key，防止竞争：

```python
def hash_input_key(conversation_hash: str, *, caller: str | None) -> str:
    payload = json.dumps({"caller": caller, "conversation_hash": conversation_hash})
    return hashlib.sha256(payload.encode()).hexdigest()
```

### 4. bind_tools 是空操作

Record 的 turn 已携带真实 `tool_calls`，不需要真实 schema binding：

```python
def bind_tools(self, tools, **kwargs):
    return self
```

## Golden JSON 格式

```json
{
  "scenario": "write_read_file",
  "mode": "ultra",
  "events": [
    {"event": "metadata", "keys": ["run_id", "thread_id"]},
    {"event": "values", "keys": ["artifacts", "messages", ...]},
    {"event": "end", "keys": null}
  ]
}
```

验证的是 **shape drift**（event 序列 + 每个 event 的顶层 key），不是 volatile 值。

## 如何录制/回放

```bash
# 录制（需要 API key）
DEERFLOW_WRITE_GOLDEN=1 uv run pytest tests/test_replay_golden.py

# 回放（零 key，毫秒级）
uv run pytest tests/test_replay_golden.py
```

## 缺陷检测能力

- System prompt 变更导致 agent 产生不同 tool call → hash miss → `replay_misses` 非空 → **CI 失败**
- 新增 ThreadState 字段 → `keys` 变化 → golden mismatch → **CI 失败**
- Middleware 顺序变更 → event 序列变化 → **CI 失败**
