---
title: "REST API 端点文档"
description: "完整的 REST API 端点表，包括之前在 digest 中缺失的端点。"
topics: [gateway, api, rest]
---

# REST API 端点文档

## 端点总览

完整的 REST API 端点表，包括之前在 digest 中缺失的端点。

### 反馈系统 (`/api/threads/{id}/runs/{rid}/feedback`)

**新文档 — 之前在 digest 中未记录**

```mermaid
flowchart TD
    subgraph CRUD
        PUT -->|upsert| U[幂等: 创建或更新]
        POST -->|create| C[如果存在则 409]
        GET -->|list| L[按线程/运行列出]
        GET2[GET /stats] -->|aggregate| S[总计/正面/负面]
        DELETE -->|by-run| D[删除用户反馈]
        DELETE2[DELETE /{fid}] -->|specific| F[按 ID 删除]
    end

    subgraph 安全
        U --> O[owner_check + require_existing]
        C --> O
        DELETE --> O
        DELETE2 --> O
        GET --> READ[owner_check]
        GET2 --> READ
    end
```

**端点**：

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `PUT` | `/{thread_id}/runs/{run_id}/feedback` | 幂等性 upsert | `threads:write` + owner |
| `POST` | `/{thread_id}/runs/{run_id}/feedback` | 创建反馈 | `threads:write` + owner |
| `GET` | `/{thread_id}/runs/{run_id}/feedback` | 列出反馈 | `threads:read` + owner |
| `GET` | `/{thread_id}/runs/{run_id}/feedback/stats` | 聚合统计 | `threads:read` + owner |
| `DELETE` | `/{thread_id}/runs/{run_id}/feedback` | 删除用户反馈 | `threads:delete` + owner |
| `DELETE` | `/{thread_id}/runs/{run_id}/feedback/{fid}` | 按 ID 删除 | `threads:delete` + owner |

**请求/响应模型**：
```python
FeedbackCreateRequest:
    rating: int (1 or -1)
    comment: str | None
    message_id: str | None         # 可选：限定到特定消息

FeedbackUpsertRequest:
    rating: int (1 or -1)
    comment: str | None

FeedbackResponse:
    feedback_id, run_id, thread_id
    user_id, message_id, rating
    comment, created_at

FeedbackStatsResponse:
    run_id, total, positive, negative
```

**验证细节**：
- `rating` 必须在 `(1, -1)` 中
- 验证运行存在且属于指定线程（运行/线程交叉引用检查）
- Upsert 对每个用户的单个反馈是幂等的

### 建议系统 (`/api/threads/{id}/suggestions`)

**新文档 — 之前在 digest 中未记录**

```mermaid
flowchart TD
    REQ[POST /suggestions] --> VAL{验证消息}
    VAL -->|空| EMPTY[返回 []]
    VAL -->|有效| FMT[格式化对话]
    FMT --> MODEL[create_chat_model thinking_enabled=False]
    MODEL --> INVOKE[ainvoke system + user prompts]
    INVOKE --> EXTRACT[_extract_response_text]
    EXTRACT --> STRIP[_strip_markdown_code_fence]
    STRIP --> PARSE[_parse_json_string_list]
    PARSE -->|成功| CLEAN[清理: 替换换行符、修剪、限制 n]
    PARSE -->|失败| FAIL[静默降级: []]
    CLEAN --> RESP[SuggestionResponse]
```

**请求/响应**：
```json
// 请求
{
  "messages": [{"role": "user", "content": "..."}],
  "n": 3,
  "model_name": "optional"
}

// 响应
{
  "suggestions": ["问题 1?", "问题 2?", "问题 3?"]
}
```

**实现细节** (`suggestions.py`):
- SystemInstruction 要求精确 N 个问题的 JSON 数组（与用户相同的语言、<= 20 个单词/40 个中文字符）
- `_extract_response_text()` — 处理富块/列表内容（text + output_text 类型）
- `_strip_markdown_code_fence()` — 在解析前移除 ```json ... ```
- `_parse_json_string_list()` — 括号平衡的 JSON 提取，每项验证为 str
- 失败时**静默降级**（总是返回 `{suggestions: []}` 而不是错误）

### 自定义 Skill CRUD (`/api/skills/custom/{name}`)

**新文档 — 之前在 digest 中仅提及安装端点**

```mermaid
flowchart LR
    subgraph 创建
        INSTALL[POST /install .skill ZIP] --> SCAN[安全扫描]
    end

    subgraph 编辑
        READ[GET /{name}] --> CONTENT[内容]
        EDIT[PUT /{name}] --> SCAN2[安全扫描] --> SAVE[保存 + 历史]
        ROLL[POST /{name}/rollback] --> SCAN3[重新扫描] --> SAVE2[保存]
    end

    subgraph 历史
        HIST[GET /{name}/history] --> LIST[变更列表]
        DEL[DELETE /{name}] --> HIST2[保留历史]
    end
```

**安全扫描** (`skills/security_scanner.py`):
- LLM 驱动的内容筛查（allow/warn/block 决定）
- 从模型输出中提取 JSON（括号平衡解析器，具字符串感知能力）
- 保守的 fail-closed 回退（模型不可用时默认阻止）

### RunCreateRequest 完整模型

之前 digest 仅显示了 4 个基本字段。完整模型有 55+ 字段：

```python
class RunCreateRequest:
    # --- 流控制 ---
    interrupt_before: list[str] | Literal["*"] | None
    interrupt_after: list[str] | Literal["*"] | None
    stream_subgraphs: bool = False
    stream_resumable: bool = False

    # --- 断开连接行为 ---
    on_disconnect: DisconnectMode = "cancel"  # cancel | continue
    on_completion: Literal["delete", "keep"] = "keep"

    # --- 多任务策略 ---
    multitask_strategy: Literal["reject", "interrupt", "rollback", "enqueue"] = "reject"

    # --- 高级功能 ---
    after_seconds: int | None              # 延迟执行
    if_not_exists: Literal["create", "reject"] = "reject"
    feedback_keys: list[str] | None
    webhook: str | None
    checkpoint_id: str | None
    checkpoint: dict | None

    # --- 标准字段 ---
    assistant_id: str | None
    metadata: dict | None
    input: dict | None
    context: dict | None
    stream_mode: list[str] | None
    model_name: str | None
```

## 其他之前未记录的端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/agents/check?name=...` | 验证名称语法 + 可用性 |
| `GET` | `/api/user-profile` | 读取全局 `USER.md` |
| `PUT` | `/api/user-profile` | 覆盖全局 `USER.md` |
| `GET` | `/api/threads/{id}/token-usage` | 按模型 + 调用者的 token 聚合 |
| `GET` | `/api/threads/{id}/runs/{rid}/events` | 运行完整事件流（可按 `event_types` 过滤） |
| `GET` | `/api/channels/` | IM 通道状态 |
| `POST` | `/api/channels/{name}/restart` | 单通道重启 |
| `POST` | `/api/threads/{id}/history` | 检查点历史（游标分页） |
| `GET` | `/api/threads/{id}/messages` | 跨运行消息（反馈附加到最后一条 AI 响应） |
| `GET` | `/api/assistants/{id}/graph` | 图描述存根（SDK 兼容） |
| `GET` | `/api/assistants/{id}/schemas` | Schema 存根（SDK 兼容） |

## MCP 配置合并

`PUT /api/mcp/config` 实现 `_merge_preserving_secrets()`：

```
1. 从磁盘加载现有 extensions_config.json
2. 对用户提供的配置进行深度合并（保留掩码值 ***）
3. 保留 raw JSON 用于 mcpInterceptors 和未知键
4. 原子写入
```

这允许前端在往返传输中发送掩码值，而真实密钥保留在磁盘上。

---

## 新增端点 🆕

### Console (`/api/console`)

只读可观测性端点（需要 SQL backend）：

| 端点 | 说明 |
|------|------|
| `GET /stats` | 标题计数器：total_runs, active_runs, total_threads, total_agents, total_tokens, total_cost |
| `GET /runs` | 分页跨线程 run 列表，join thread 标题，含 per-run 成本 |
| `GET /usage` | 每日 token 用量序列（最多 90 天），per-model 分解 |

成本估算需要 `models[*].pricing` 块（`currency`, `input_per_million`, `output_per_million`, `input_cache_hit_per_million`）。Memory backend 返回 503。

### Goal (`/api/threads/{id}/goal`)

Thread goal 自动续跑：

- `GET /goal` — 读取活跃 goal
- `PUT /goal` — 设置 goal（可配 `max_continuations`，上限 8）
- `DELETE /goal` — 清除 goal

设置后，每个 visible assistant turn 后，非思考 evaluator 模型评估 goal 是否满足。`goal_not_met_yet` → 注入隐藏 HumanMessage 让 agent 继续工作。No-progress breaker 在连续 2 次无新证据时停止。

### Channel Connections (`/api/channels`)

用户拥有的 IM 频道绑定：

- `GET /providers` — 列出支持的 provider 及每个 provider 的就绪状态
- `GET /connections` — 列出当前用户的绑定
- `POST /{provider}/connect` — 发起绑定（返回一次性 connect code）
- `DELETE /connections/{id}` — 撤销绑定

支持 7 个 provider：Telegram（deep-link）、Slack、Discord、Feishu、DingTalk、WeChat、WeCom（binding code）。

### GitHub Webhooks (`/api/webhooks/github`)

`POST /` — 接收 GitHub App webhook 事件。HMAC 验证（`X-Hub-Signature-256`）。识别事件：`issues`、`issue_comment`、`pull_request`、`pull_request_review` 等。Per-agent binding 支持 `config.yaml` 中声明 `github:` 块。

### Scheduled Tasks

CRUD on scheduled task 定义（cron 或一次性），含 lease/status 列和执行追踪。
