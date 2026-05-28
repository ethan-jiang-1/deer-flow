# LLM 抽象层

怎么做到换模型不改代码？thinking/vision 这些新能力怎么统一抽象？

## 阅读顺序

1. **Model Factory** — `create_chat_model()` 入口，reflection 动态加载 provider，8+ provider 支持
2. **Thinking & Vision** — thinking mode 跨 provider 差异处理、vision 能力检测、per-model 覆盖配置
3. **Streaming** — chunk 归一化、SSE 事件模型、StreamBridge 路由

## 关键问题

- `config.yaml` 里换一个 `model.use` class path 就能切 provider？
- vLLM 的 `chat_template_kwargs.enable_thinking` 和 OpenAI/Anthropic 的 thinking 模式有什么不同？
- streaming 的 token delta 是怎么在不同 provider 之间统一成前端期望格式的？
