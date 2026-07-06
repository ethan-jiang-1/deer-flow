---
title: "Python SDK — DeerFlowClient"
description: "`DeerFlowClient` 提供嵌入式 Python 访问，不需要 HTTP 服务。源码：`backend/packages/harness/deerflow/client.py`。"
topics: [setup, configuration, quickstart]
---

# Python SDK — DeerFlowClient

`DeerFlowClient` 提供嵌入式 Python 访问，不需要 HTTP 服务。源码：`backend/packages/harness/deerflow/client.py`。

## 安装

```bash
cd backend
uv sync
# 或安装为包
pip install -e packages/harness/
```

## 基本用法

```python
from deerflow.client import DeerFlowClient

# 初始化
client = DeerFlowClient(
    config_path=None,          # None = 自动查找 config.yaml
    checkpointer=None,         # None = 使用 config.yaml 中配置的 checkpointer
    model_name=None,           # None = 使用默认模型
    thinking_enabled=True,     # 扩展思考
    subagent_enabled=False,    # 子 Agent 委托
    plan_mode=False,           # 计划模式
    agent_name=None,           # 自定义 Agent 名称
    available_skills=None,     # 限制可用 Skills，None = 全部启用
    middlewares=None,          # 自定义中间件
    environment=None,          # "production" | "staging" 用于 tracing
)
```

### 同步对话

```python
response = client.chat("帮我分析一下这个项目", thread_id="my-thread")
print(response)
# -> "我来帮你分析这个项目..."

# 多轮对话（需要 checkpointer）
client2 = DeerFlowClient(checkpointer=my_checkpointer)
client2.chat("你好", thread_id="thread-1")
client2.chat("上次我们聊了什么？", thread_id="thread-1")
```

### 流式

```python
for event in client.stream("写一首诗", thread_id="thread-2"):
    print(event)
    # event.type: "values" | "messages-tuple" | "custom" | "end"
    # event.data: dict
```

**StreamEvent 类型语义**：

| type | data 内容 | 说明 |
|------|-----------|------|
| `values` | ThreadState 全量快照 | title, messages, artifacts, todos |
| `messages-tuple` | 增量消息 | AI 文本是 delta（按 id 拼接），tool_call/tool_result 各发一次 |
| `custom` | 自定义事件 | 从 StreamWriter 转发 |
| `end` | `{"usage": {"input_tokens": N, "output_tokens": M}}` | 流结束，累计用量按 message id 去重 |

**注意**：AI 文本 content 已通过 `messages-tuple` 增量发送后，`values` 事件不会重新合成 AI 文本，避免重复。

## Gateway 等价方法

Client 方法签名与 Gateway API 响应一一对应，使用时无需关心底层是 HTTP 还是本地调用。

### Models

```python
models = client.list_models()
# -> {"models": [{"name": "deepseek", "display_name": "DeepSeek", ...}]}

model = client.get_model("deepseek")
# -> {"name": "deepseek", "display_name": "DeepSeek", ...}
```

### MCP

```python
config = client.get_mcp_config()
# -> {"mcp_servers": {...}, "mcp_interceptors": [...]}

client.update_mcp_config({
    "github": {
        "enabled": True,
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "ghp_xxx"}
    }
})
# 自动使缓存的 Agent 失效
```

### Skills

```python
skills = client.list_skills()
# -> {"skills": [{"name": "deep-research", "enabled": True, ...}]}

skill = client.get_skill("deep-research")

client.update_skill("deep-research", enabled=False)

client.install_skill("/path/to/my-skill.skill")
```

### Memory

```python
memory = client.get_memory()
# -> {"userContext": {...}, "history": {...}, "facts": [...]}

client.reload_memory()          # 强制从文件重新加载

status = client.get_memory_status()
config = client.get_memory_config()
```

### Uploads

```python
from pathlib import Path

# 接受本地 Path 对象（不同于 Gateway 的 HTTP UploadFile）
result = client.upload_files("thread-1", [
    Path("/home/user/report.pdf"),
    Path("/home/user/data.csv"),
])
# -> {"success": True, "files": [{"filename": "report.pdf", ...}, ...]}

files = client.list_uploads("thread-1")
# -> {"files": [...], "count": 2}

client.delete_upload("thread-1", "report.pdf")
```

**与 Gateway 的区别**：
- 上传接受 `Path` 而非 `UploadFile`
- 目录路径在上传前被拒绝
- 文档转换在单 worker 中复用

### Artifacts

```python
data, mime_type = client.get_artifact("thread-1", "outputs/chart.png")
# data: bytes
# mime_type: "image/png"
```

与 Gateway 返回 `(bytes, mime_type)` 而非 HTTP Response。

## Agent 生命周期

```python
# 强制重建 Agent（长时进程中记忆/Skill 变更后）
client.reset_agent()
```

Agent 在首次 `chat()`/`stream()` 时惰性创建，之后缓存。系统 prompt（date, memory, skills context）在创建时生成并缓存到配置 key 变化为止。

## 多轮对话与 Checkpointer

没有 checkpointer 时，每次 `chat()`/`stream()` 是无状态的。`thread_id` 仅用于文件隔离（uploads/artifacts）。

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
client = DeerFlowClient(checkpointer=checkpointer)

client.chat("我叫张三", thread_id="t1")
client.chat("我叫什么名字？", thread_id="t1")  # -> "张三"
```

## 与 Gateway 共享配置

Client 和 Gateway API 读取相同的 config.yaml 和 extensions_config.json。在同一个进程中，它们共享：
- 同一个 `get_app_config()` 缓存
- 同一个 `get_or_new_skill_storage()` 实例
- 同一个数据目录（`.deer-flow/`）

这意味着先用 Gateway API 改了 MCP 配置，Client 下一次调用时自动感知到文件 mtime 变化并生效。

## Gateway 一致性测试

`tests/test_client.py` 中 `TestGatewayConformance` 验证每个 dict-returning 的 client 方法输出能通过对应 Gateway Pydantic response model 解析。如果 Gateway 加了必填字段而 Client 没同步，CI 会报 `ValidationError`。这保证了两种接入方式的结果格式一致。
