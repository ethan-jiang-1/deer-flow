---
title: "Thinking & Vision"
description: "两个 LLM 新能力，两套完全不同的启用机制。Thinking 在 model 层解决（修改传给 provider 的参数），Vision 在 middleware 层解决（在 model 调用前注入图片数据）。"
topics: [models, llm, provider-factory]
---

# Thinking & Vision

两个 LLM 新能力，两套完全不同的启用机制。Thinking 在 model 层解决（修改传给 provider 的参数），Vision 在 middleware 层解决（在 model 调用前注入图片数据）。

## Thinking Mode

### 三种配置模式

`create_chat_model()` 通过检测 `when_thinking_enabled` 的 shape 来自动判断用哪种模式：

| 模式 | 检测条件 | 示例 provider | enable 做什么 | disable 做什么 |
|------|---------|-------------|-------------|-------------|
| **Anthropic 原生** | `when_thinking_enabled.thinking.type` 存在 | `ChatAnthropic` | 传 `thinking={"type": "enabled", "budget_tokens": N}` | 传 `thinking={"type": "disabled"}` |
| **OpenAI 网关** | `when_thinking_enabled.extra_body.thinking.type` 存在 | Gemini via OpenAI gateway | 传 `extra_body.thinking.type="enabled"` | 传 `extra_body.thinking.type="disabled"` + `reasoning_effort="minimal"` |
| **vLLM** | `when_thinking_enabled.extra_body.chat_template_kwargs` 含 `thinking`/`enable_thinking` | vLLM Qwen | 传 `chat_template_kwargs.enable_thinking=true` | 传 `chat_template_kwargs.enable_thinking=false` |

### config.yaml 配置示例

```yaml
models:
  # Anthropic 原生 thinking
  - name: claude-sonnet-4-6
    use: langchain_anthropic:ChatAnthropic
    model: claude-sonnet-4-6-20250514
    api_key: $ANTHROPIC_API_KEY
    supports_thinking: true
    when_thinking_enabled:
      thinking:
        type: enabled
        budget_tokens: 12000

  # vLLM Qwen thinking
  - name: qwen-vllm
    use: deerflow.models.vllm_provider:VllmChatModel
    model: qwen3-235b
    base_url: http://vllm:8000/v1
    api_key: unused
    supports_thinking: true
    when_thinking_enabled:
      extra_body:
        chat_template_kwargs:
          enable_thinking: true

  # OpenAI gateway (Gemini thinking)
  - name: gemini-gateway
    use: deerflow.models.patched_openai:PatchedChatOpenAI
    model: gemini-2.5-pro
    base_url: https://gateway.example.com/v1
    supports_thinking: true
    when_thinking_enabled:
      extra_body:
        thinking:
          type: enabled
```

### 运行时开关

```python
# 开启 thinking
model = create_chat_model("claude-sonnet-4-6", thinking_enabled=True)

# 关闭 thinking — factory 自动检测模式并注入 disable 参数
model = create_chat_model("claude-sonnet-4-6", thinking_enabled=False)
```

`thinking_enabled` 由 agent runtime config 传入，来自前端 toggle 或 API 参数。它和 `supports_thinking` 是两层校验：`supports_thinking` 是模型能力声明（config.yaml 静态配置），`thinking_enabled` 是运行时开关（用户可以随时关掉）。

### `thinking` 快捷方式

```yaml
# 等价于 when_thinking_enabled.thinking
thinking:
  type: enabled
  budget_tokens: 12000
```

factory 会把 `thinking` 字段 merge 到 `when_thinking_enabled.thinking`，两个同时存在时 `thinking` 的值优先（更深层 merge 覆盖）。

### reasoning_effort

`reasoning_effort` 是一个独立的参数，透传给 provider。不是所有模型都支持 — `supports_reasoning_effort: false` 时 factory 会把它从 kwargs 里 strip 掉。Codex provider 把 thinking + reasoning_effort 映射为 `none/low/medium/high/xhigh` 五档。

## Vision

### 启用链路

```
config.yaml                    middleware                     model 调用前
supports_vision: true  →  ViewImageMiddleware 加入链  →  before_model 注入 base64 图片
                      →  view_image tool 加入 toolset
```

不是所有模型都能看图。`supports_vision: true` 是前提条件。启用后的完整流程：

1. **Tool 执行** — agent 调 `view_image` tool，tool 读取文件（验证 JPEG/PNG/WebP，max 20 MiB，magic byte 检查），base64 编码，存入 `ThreadState.viewed_images`
2. **Middleware 注入** — `ViewImageMiddleware.before_model` 在下一次 model 调用前，把 `viewed_images` 中的图片转为 `HumanMessage` 的 `image_url` content block（base64 data URI）
3. **Model 调用** — LLM 收到的 messages 里包含图片数据，像正常的多模态请求一样处理
4. **状态清理** — `merge_viewed_images` reducer 合并/清理已处理图片

### 路径限制

`view_image_tool` 只允许读三个虚拟路径：
- `/mnt/user-data/workspace/**`
- `/mnt/user-data/uploads/**`
- `/mnt/user-data/outputs/**`

防止 agent 通过 `view_image` 读取系统文件。

### RuntimeFeatures 开关

```python
class RuntimeFeatures:
    vision: bool | AgentMiddleware = False  # 默认关
```

SDK 路径通过 `RuntimeFeatures.vision` 控制是否启用 ViewImageMiddleware。Lead agent 路径通过 `model_config.supports_vision` 自动判断。

## 跨 Provider 的 reasoning 内容保持

这 4 个 patch 类只做一件事：**确保 reasoning/thinking 内容在多 turn 对话中不丢失**：

```
Turn 1: User asks → Model thinks (reasoning_content/thought_signature) → Tool call
Turn 2: 上一轮的 reasoning 字段必须出现在 AIMessage 里 → 否则 API 400
```

- **PatchedDeepSeek** — `additional_kwargs.reasoning_content` 必须在下轮请求的 assistant message 中回传
- **PatchedOpenAI (Gemini)** — `additional_kwargs.thought_signature` 必须在下轮回传
- **VllmChatModel** — assistant message 的 `reasoning` 字段必须保留
- **PatchedMiniMax** — `reasoning_details` + inline `<think>` 标签都要解析

这些都不是 DeerFlow 发明的需求——是各家 provider API 的硬性约束。patch 类的作用就是自动处理这些约束，使用者不需要知道。

## Thinking 模式检测的代码路径

`create_chat_model()`（`factory.py:50`）中 thinking 配置的解析流程：

```
create_chat_model(name, thinking_enabled=None)
  │
  ├─ 1. 加载 model config from config.yaml
  │
  ├─ 2. thinking_enabled is None?
  │     └─ 从 config["thinking_enabled"] 读取（默认 False）
  │
  ├─ 3. 如果 model_config.supports_thinking is False:
  │     └─ thinking_enabled 强制为 False（即使前端 toggle 打开）
  │
  ├─ 4. 模式检测（通过 when_thinking_enabled 的 shape）:
  │     │
  │     ├─ when_thinking_enabled.thinking.type 存在?
  │     │   → Anthropic 原生模式
  │     │   → 直接设置 model.thinking = {"type": "enabled"/"disabled", ...}
  │     │
  │     ├─ when_thinking_enabled.extra_body.thinking.type 存在?
  │     │   → OpenAI 网关模式
  │     │   → 设置 model.extra_body.thinking.type
  │     │   → disable 时额外设 reasoning_effort="minimal"
  │     │
  │     ├─ when_thinking_enabled.extra_body.chat_template_kwargs 含 thinking/enable_thinking?
  │     │   → vLLM 模式
  │     │   → _normalize_vllm_chat_template_kwargs() 做旧版兼容转换
  │     │   → 设置 model.extra_body.chat_template_kwargs.enable_thinking
  │     │
  │     └─ 全不匹配?
  │         → 仅设置 reasoning_effort（通用降级）
  │
  └─ 5. reasoning_effort 处理:
        ├─ supports_reasoning_effort is False? → 从 kwargs 中 strip
        └─ Codex provider? → 映射为 none/low/medium/high/xhigh 五档
```

### Anthropic 模式的 auto_thinking_budget

Claude provider（`claude_provider.py:250`）有一个自动 thinking budget 计算：当 `thinking_enabled=True` 且未显式指定 `budget_tokens` 时，自动分配 `max_tokens` 的 80% 给 thinking。这是基于 Anthropic 的建议——thinking 需要足够的 token 预算才能有效。

```python
# claude_provider.py:261
thinking_budget = int(max_tokens * 0.8) if max_tokens else None
```

### vLLM 旧版兼容

`_normalize_vllm_chat_template_kwargs()`（`vllm_provider.py:39`）处理 vLLM 0.19.0 之前的配置格式——`chat_template_kwargs.thinking` → `chat_template_kwargs.enable_thinking`。在 `_get_request_payload` 被调用时执行转换，不影响 config.yaml 中的声明。

## Vision 启用链路的代码级 trace

```
用户上传图片 / Agent 调 view_image tool
  │
  ├─ Step 1: RuntimeFeatures 判断是否启用
  │     lead agent 路径: model_config.supports_vision → 自动决定
  │     SDK 路径: RuntimeFeatures.vision → 显式控制
  │     如果 vision=False → ViewImageMiddleware 根本不加入链
  │
  ├─ Step 2: view_image tool 执行 (sandbox/tools.py)
  │     ├─ 路径校验: 限定在 /mnt/user-data/{workspace,uploads,outputs}
  │     ├─ 文件类型校验: magic bytes 检查 JPEG/PNG/WebP
  │     ├─ 大小上限: 20 MiB
  │     ├─ base64 编码
  │     └─ 写入 ThreadState.viewed_images (merge_viewed_images reducer)
  │
  ├─ Step 3: ViewImageMiddleware.before_model (deerflow/agents/middlewares/)
  │     ├─ 从 ThreadState 读取 viewed_images
  │     ├─ 构造 HumanMessage:
  │     │     content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]
  │     └─ 注入到 messages 列表（在 system prompt 之后，最后一条 user message 之前）
  │
  ├─ Step 4: Model 调用
  │     └─ LLM 收到带 image_url content block 的多模态消息
  │
  └─ Step 5: 状态清理
        └─ merge_viewed_images reducer: 已处理图片被移除，防止重复注入
```

### Vision 与 model 配置的关系

`supports_vision: true` 是三个独立决策的前置条件：
1. `view_image` tool 是否加入 toolset
2. `ViewImageMiddleware` 是否加入 middleware 链
3. 前端是否显示图片上传 UI

如果 `supports_vision: false`（默认），三者全关——即使前端传了图片也不会被处理。
