---
title: "resolve_variable — 动态加载"
description: "DeerFlow 的核心 slogan 之一是"换模型/换 tool 不改代码"。实现这个的基础设施是 reflection 系统：`resolve_variable()` 和 `resolve_class()`。"
topics: [configuration, hot-reload, yaml-config]
---

# resolve_variable — 动态加载

DeerFlow 的核心 slogan 之一是"换模型/换 tool 不改代码"。实现这个的基础设施是 reflection 系统：`resolve_variable()` 和 `resolve_class()`。

## resolve_variable()

位于 `deerflow/reflection/resolvers.py:25`：

```python
def resolve_variable(variable_path: str, expected_type: type | None = None):
    # "deerflow.sandbox.tools:bash_tool" → import deerflow.sandbox.tools, get bash_tool
    module_path, variable_name = variable_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    var = getattr(module, variable_name)

    if expected_type is not None:
        if not isinstance(var, expected_type):
            raise TypeError(f"Expected {expected_type}, got {type(var)}")

    return var
```

`rsplit(":", 1)` 只切**最后一个**冒号 — module path 中可以有多个（如 `langchain_openai:ChatOpenAI`）。

**类型检查是可选的**：不传 `expected_type=None` 则跳过类型校验。Tool 加载传 `BaseTool`，Model 加载传 `type`（检查 isclass + issubclass）。

### 安装提示

`ModuleNotFoundError` 时，`resolvers.py:11` 有一个映射表：

```python
MODULE_TO_PACKAGE_HINTS = {
    "langchain_google_genai": ("langchain-google-genai",),
    "langchain_anthropic": ("langchain-anthropic",),
    "langchain_openai": ("langchain-openai",),
    "langchain_deepseek": ("langchain-deepseek",),
}
```

未知 module 用 fallback 规则：`_` → `-`。错误消息变成：

```
Failed to import module 'langchain_google_genai'.
You may need to install it: uv add langchain-google-genai
```

---

## resolve_class()

`resolve_class()` (`resolvers.py:73`) 是对 `resolve_variable()` 的封装：

```python
def resolve_class(class_path: str, base_class: type | None = None):
    cls = resolve_variable(class_path, expected_type=type)
    if base_class is not None and not issubclass(cls, base_class):
        raise TypeError(...)
    return cls
```

Model factory 用它加载 provider 类：

```python
# factory.py:78
model_cls = resolve_class(model_config.use, BaseChatModel)
# "langchain_openai:ChatOpenAI" → ChatOpenAI 类
```

---

## 在 Tool 装配中的使用

`get_available_tools()` (`tools/tools.py:73`) 对 `config.yaml` 中的每个 tool 调用：

```python
for cfg in tool_configs:
    tool = resolve_variable(cfg.use, BaseTool)
    if cfg.name != tool.name:
        logger.warning(f"Config name '{cfg.name}' != resolved '{tool.name}'")
```

Tool 装配顺序（`tools.py:208`）：

```
① config.yaml 定义的 tools（resolve_variable 动态加载）
② builtin tools（present_files, ask_clarification, view_image, task, skill_manage）
③ MCP tools（从 extensions_config.json 配置的 server 加载）
④ ACP agents（invoke_acp_agent）
→ 按 name 去重（先到先得）
```

---

## 在 Model Factory 中的使用

`create_chat_model()` (`models/factory.py:50`)：

```
① 从 AppConfig.models 找到 ModelConfig（按 name 匹配）
② resolve_class(model_config.use, BaseChatModel) → provider 类
③ 把 ModelConfig dump 成 dict，排除 meta field（use, name, supports_thinking 等）
④ 剩余字段（包括 extra="allow" 的 api_key, base_url, temperature）当 kwargs 传给 provider
⑤ 处理 thinking_enabled：合并 when_thinking_enabled / when_thinking_disabled 覆盖
⑥ 如果有 vLLM/Codex/MindIE 特殊处理，在此应用
```

### extra="allow" 透传

`ModelConfig` 的 `model_config = ConfigDict(extra="allow")` 是关键 — 用户可以在 YAML 里写任意 provider 字段：

```yaml
models:
  - name: my-gpt
    use: langchain_openai:ChatOpenAI
    model: gpt-4
    api_key: $OPENAI_API_KEY         # ← 被 extra="allow" 保留
    base_url: $AZURE_ENDPOINT        # ← 被保留
    temperature: 0.7                 # ← 被保留
    max_tokens: 4096                 # ← 被保留
```

这些字段在 `model_settings_from_config` 构建时自动变成 provider 构造函数的 kwargs，不需要框架显式支持每个 provider 的参数。

---

## Thinking 跨 Provider 处理

`create_chat_model()` 的 thinking 逻辑 (`factory.py:94-128`) 分三层：

**开启 thinking：**
```python
if thinking_enabled:
    if not model_config.supports_thinking:
        raise ValueError(...)
    kwargs.update(model_config.when_thinking_enabled or {})
```

**关闭 thinking — 三种 provider 的差异：**

```python
# OpenAI-compatible gateway (factory.py:111-116)
extra_body["thinking"]["type"] = "disabled"
kwargs["reasoning_effort"] = "minimal"

# vLLM/Qwen (factory.py:117-122)
extra_body["chat_template_kwargs"]["enable_thinking"] = False

# LangChain Anthropic (factory.py:123-125)
kwargs["thinking"]["type"] = "disabled"
```

这三个分支自动判断，用户不需要在 config 里写任何 provider 相关的 thinking 关闭逻辑。
