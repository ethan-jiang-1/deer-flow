# 记忆系统

DeerFlow 提供持久化的用户记忆功能，跨对话保留上下文信息。

## 系统组件

```
MemoryMiddleware (after_step)
    │  过滤消息 → 用户输入 + 最终 AI 回复
    │  捕获 user_id via get_effective_user_id()
    │  入队更新
    ▼
MemoryQueue (debounced)
    │  30s debounce
    │  per-thread 去重
    │  批量化处理
    ▼
MemoryUpdater (LLM-based)
    │  调用 LLM 提取事实和上下文更新
    │  使用 MEMORY_UPDATE_PROMPT
    │  应用更新到 memory.json
    ▼
memory.json
    per-user 文件存储
    atomic write (temp file + rename)
```

## 数据结构

```json
{
  "userContext": {
    "workContext": "Software engineer...",
    "personalContext": "Lives in Beijing...",
    "topOfMind": "Currently learning Rust..."
  },
  "history": {
    "recentMonths": "...",
    "earlierContext": "...",
    "longTermBackground": "..."
  },
  "facts": [
    {
      "id": "f_abc123",
      "content": "Prefers Chinese language",
      "category": "preference",
      "confidence": 0.95,
      "createdAt": "2025-01-15T...",
      "source": "conversation"
    }
  ]
}
```

### Fact 类别

| Category | 含义 | 示例 |
|----------|------|------|
| `preference` | 用户偏好 | "喜欢中文回复" |
| `knowledge` | 用户知识 | "熟悉 Python" |
| `context` | 上下文 | "在字节工作" |
| `behavior` | 行为模式 | "经常在晚上使用" |
| `goal` | 目标 | "想学 Rust" |

## Per-User 隔离

```
.deer-flow/users/
├── {user_id}/
│   ├── memory.json                    # 通用记忆
│   └── agents/
│       └── {agent_name}/
│           └── memory.json            # Per-agent 记忆（可选）
└── default/                           # 无 auth 模式
    └── memory.json
```

- 文件存储路径由 `config.yaml` → `memory.storage_path` 控制
- 绝对路径 → 不使用 per-user 隔离
- 相对路径 → 相对于 `{base_dir}/users/{user_id}/`
- Per-agent memory 通过 `MemoryMiddleware(agent_name=...)` 支持

## 配置参数

```yaml
memory:
  enabled: true
  storage_path: memory.json          # 相对路径 → per-user；绝对路径 → 共享
  debounce_seconds: 30               # 更新去抖时间
  model_name: null                   # null = 使用默认模型进行事实提取
  max_facts: 100                     # 最多存储事实数
  fact_confidence_threshold: 0.7     # 最低置信度
  injection_enabled: true            # 是否注入 system prompt
  max_injection_tokens: 2000         # 注入的最大 token 数
```

## Memory 注入

当下一次对话开始时，`DynamicContextMiddleware` 将 top 15 facts + user context 注入 system prompt：

```
<system-reminder>
  <memory>
    User Context: ...
    Recent Facts:
    - ...
  </memory>
</system-reminder>
```

注入上限 `max_injection_tokens`（默认 2000）。

## 事实去重与原子写入

- **去重**：提取的新 fact 与已有 fact 的 content 比较（trim 前后空格后），重复的不追加
- **原子写入**：先写 temp file → `os.replace()` 到目标文件 → 使缓存失效
- **并发安全**：进程内同一用户同一 agent 的读写被 `MemoryQueue` 的去抖机制序列化

## 用户隔离迁移

从 legacy 共享布局迁移到 per-user 布局：
```bash
PYTHONPATH=. python scripts/migrate_user_isolation.py
# --dry-run  预览
# --user-id USER_ID  指定归属用户（默认 default）
```

Legacy 布局（`{base_dir}/memory.json`）仍作为只读 fallback。

## API 接口

| 操作 | endpoint |
|------|----------|
| 获取记忆 | `GET /api/memory` |
| 强制重载 | `POST /api/memory/reload` |
| 清空记忆 | `DELETE /api/memory` |
| 创建 Fact | `POST /api/memory/facts` |
| 删除 Fact | `DELETE /api/memory/facts/{id}` |
| 更新 Fact | `PATCH /api/memory/facts/{id}` |
| 导出 | `GET /api/memory/export` |
| 导入 | `POST /api/memory/import` |
| 配置 | `GET /api/memory/config` |
| 状态 | `GET /api/memory/status` |
