---
title: "记忆系统"
description: "DeerFlow 提供持久化的用户记忆功能，跨对话保留上下文信息。"
topics: [memory, persistence, context-injection]
---

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

## Staleness Review 🆕

同一次 LLM 调用中（不增加 API 开销），检测并清理过期 fact：

1. `_select_stale_candidates()` 选超过 `staleness_age_days`（默认 90 天）的 fact，排除 `staleness_protected_categories`（默认 `["correction"]`）
2. 候选数 ≥ `staleness_min_candidates`（默认 3）时触发
3. LLM 逐条判断 KEEP 或 REMOVE
4. `_apply_updates` 硬性交叉校验：只删除 LLM 建议的 ∩ 实际候选的，保护类别和未过期 fact **永不被删除**
5. 上限 `staleness_max_removals_per_cycle`（默认 10），超额时保留最低置信度 fact

## Token Counting 🆕

两种策略，由 `memory.token_counting` 控制：

| 策略 | 说明 |
|------|------|
| `tiktoken`（默认） | `cl100k_base` 精确计数。编码懒加载+缓存。失败后 600s cooldown。网络受限环境可能阻塞首次加载 |
| `char` | 零网络依赖。CJK 感知估算：非 CJK `//4`，CJK `//2` |

## Guaranteed Categories 🆕

`guaranteed_categories`（默认 `["correction"]`）中的 fact 走独立 token 预算（`guaranteed_token_budget`，默认 500），放在 Facts 块最前面，不被普通 fact 挤出。

## Sync 更新路径修复 🆕

`_do_update_memory_sync` 使用独立 `ThreadPoolExecutor` + `model.invoke()`（同步 HTTP），避免触碰 lead agent 共享的 async httpx 连接池，消除跨 loop 连接复用 bug（issue #2615）。

## Upload Stripping 🆕

`_strip_upload_mentions_from_memory()` 从摘要和 fact 中删除关于上传文件的句子，防止 agent 在后续 session 中搜索不存在的文件。

## 新配置参数

```yaml
memory:
  token_counting: tiktoken              # tiktoken | char
  guaranteed_categories: [correction]   # 保证注入的 fact 类别
  guaranteed_token_budget: 500          # 保证类别的 token 上限
  staleness_review_enabled: true        # 开启过期清理
  staleness_age_days: 90                # 超过此天数才候选
  staleness_min_candidates: 3           # 至少这么多候选才触发
  staleness_max_removals_per_cycle: 10  # 每次最多删除数
  staleness_protected_categories: [correction]  # 永不过期类别
```

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

---
> **See also:** [MemoryConfig source](../../../backend/packages/harness/deerflow/config/memory_config.py) · [Testing staleness review](../../testing/08-testing-patterns-reference.md)
