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

1. **Tool 执行** — agent 调 `view_image` tool，tool 读取文件（验证 JPEG/PNG/WebP，max 20MB，magic byte 检查），base64 编码，存入 `ThreadState.viewed_images`
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
