---
title: "resolve_variable — 动态加载"
description: 'DeerFlow 的核心 slogan 之一是"换模型/换 tool 不改代码"。实现这个的基础设施是 reflection 系统：resolve_variable() 和 resolve_class()。'
topics: [configuration, hot-reload, yaml-config]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# resolve_variable — 动态加载

DeerFlow 的核心 slogan 之一是"换模型/换 tool 不改代码"。实现这个的基础设施是 reflection 系统：`resolve_variable()` 和 `resolve_class()`。

## resolve_variable()

位于 `deerflow/reflection/resolvers.py:25`（PEP 695 泛型写法，函数签名带 `[T]` 类型参数）：

```python
def resolve_variable[T](variable_path, expected_type: type[T] | tuple[type, ...] | None = None) -> T:
    # "deerflow.sandbox.tools:bash_tool" → import deerflow.sandbox.tools, get bash_tool
    module_path, variable_name = variable_path.rsplit(":", 1)
    module = import_module(module_path)          # resolvers.py:79
    variable = getattr(module, variable_name)    # resolvers.py:90
    if expected_type is not None and not isinstance(variable, expected_type):
        raise ValueError(...)                    # resolvers.py:95-98
    return variable
```

`rsplit(":", 1)` 只切**最后一个**冒号 —— module path 中可以有多个点（如 `langchain_openai:ChatOpenAI`），但冒号只能有一个。

**🆕 路径形状校验**（`resolvers.py:67-76`）：切分之后立刻拒绝五种"看着像路径其实不是"的输入，统一报同一句 `... doesn't look like a variable path. Example: parent_package_name.sub_package_name.module_name:variable_name`：

| 形状 | 如果不拦，会发生什么 |
|---|---|
| 空 module 或空 variable（尾冒号） | 报 "Module json does not define a  attribute/class"，属性名是空的 |
| module 里多一个冒号 | 冒号留在 module 部分，被当成缺依赖，给出 `uv add json:loads` 这种不可用的提示 |
| 前导点（相对导入） | `import_module` 抛 `TypeError` 而非 `ImportError`，所有 catch `ImportError` 的 loader 都直接崩 |
| 尾随点 | 落到缺依赖分支，宣传一个名为 `json.` 的发行包 |
| 任意半边含空白（`"json :loads"`、`"json:attr\n"`） | 同上，宣传 `json ` 这种不可见的包名 |

**类型检查是可选的**：不传 `expected_type`（默认 `None`）则跳过类型校验；也可以传类型元组。Tool 加载传 `BaseTool`，Model 加载传 `type`（再由 `resolve_class` 做 isclass + issubclass 检查）。

### 安装提示

`ModuleNotFoundError` 时，`resolvers.py:3` 有一个映射表（值是**单个字符串**，不是元组）：

```python
MODULE_TO_PACKAGE_HINTS = {
    "langchain_google_genai": "langchain-google-genai",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_openai": "langchain-openai",
    "langchain_deepseek": "langchain-deepseek",
}
```

`_build_missing_dependency_hint()` (`resolvers.py:11`) 的查找顺序是：先按 **module 根**查表（这样 `google` 这种**传递依赖**缺失时仍能给出正确的 provider 包名），再按 `err.name` 查表，最后才 fallback 规则 `_` → `-`。错误消息形如：

```
Could not import module langchain_google_genai. Missing dependency 'langchain_google_genai'.
Install it with `uv add langchain-google-genai` (or `pip install langchain-google-genai`), then restart DeerFlow.
```

非"缺模块"类的 `ImportError`（模块在、但内部 import 失败）不走提示，原样保留错误信息（`resolvers.py:87`）。属性不存在时报 `Module <path> does not define a <name> attribute/class`（`resolvers.py:93`）。

---

## resolve_class()

`resolve_class()` (`resolvers.py:103`) 是对 `resolve_variable()` 的封装：

```python
def resolve_class[T](class_path: str, base_class: type[T] | None = None) -> type[T]:
    model_class = resolve_variable(class_path, expected_type=type)   # resolvers.py:117
    if not isinstance(model_class, type):                            # 冗余但保留的二次确认
        raise ValueError(f"{class_path} is not a valid class")
    if base_class is not None and not issubclass(model_class, base_class):
        raise ValueError(f"{class_path} is not a subclass of {base_class.__name__}")
    return model_class
```

Model factory 用它加载 provider 类：

```python
# factory.py:570
model_class = resolve_class(model_config.use, BaseChatModel)
# "langchain_openai:ChatOpenAI" → ChatOpenAI 类
```

---

## 在 Tool 装配中的使用

`get_available_tools()` (`tools/tools.py:103`) 先对 `config.yaml` 的 `tools[]` 做**四道过滤**，再逐个动态加载：

```python
config = app_config or get_app_config()
tool_configs = [t for t in config.tools if groups is None or t.group in groups]
# ① scheduler 工具只能由 host grant 装配，YAML 注册无效（tools.py:147）
tool_configs = [t for t in tool_configs if t.use not in {"...scheduled_tasks:schedule_task", "...:stop_scheduled_task"}]
if not include_conversation_reader:
    tool_configs = [t for t in tool_configs if t.use != CONVERSATION_TOOL_USE]     # ②
if not knowledge_base.enabled:
    tool_configs = [t for t in tool_configs if t.group != "knowledge"]              # ③ tools.py:155-157
if not is_host_bash_allowed(config):
    tool_configs = [t for t in tool_configs if not _is_host_bash_tool(t)]           # ④
loaded_tools_raw = [(cfg, resolve_variable(cfg.use, BaseTool)) for cfg in tool_configs]   # tools.py:163
```

③ 是 v2.2.0 新增的 knowledge 门控：`knowledge` 组是**整组 opt-in**，provider 连接与检索参数留在各自的 tool 条目上，通用的 `knowledge_base.enabled` 只管这一组要不要暴露。

加载后立刻做名称一致性检查（`tools.py:169-176`）：`cfg.name` 与 tool 对象自己的 `.name` 不一致时只 **warning**，绑定用的是 tool 的 `.name`。这是 issue #1803 的根因——模型 schema 里一个名字、运行时路由器认另一个名字，于是报 "not a valid tool"。

Tool 装配顺序（在 `tools/tools.py:163` 之后依次追加，去重在 `tools.py:344-349`）：

```
① config.yaml 定义的 tools（上车四道过滤 + resolve_variable 动态加载）
② builtin tools（present_files, ask_clarification 等 BUILTIN_TOOLS）
   + 条件追加：scheduler 工具（需 host grant）、MCP 长任务工具、list_uploaded_files、
     skill_manage（skill_evolution.enabled）、subagent 工具（subagent_enabled）、
     batch 工具（batch runtime 可用）、view_image（模型 supports_vision）等
③ MCP tools（每次装配都用 ExtensionsConfig.from_file() 重读磁盘，再取 mtime 缓存）
④ ACP agents（invoke_acp_agent）
→ 按 name 去重（先到先得，ordinary-first）
```

---

## 在 Model Factory 中的使用

`create_chat_model()` (`models/factory.py:536`)：

```
① 从 AppConfig.models 找到 ModelConfig（按 name 匹配）
② resolve_class(model_config.use, BaseChatModel) → provider 类（factory.py:570）
③ 把 ModelConfig dump 成 dict，排除 meta field
④ 剩余字段（包括 extra="allow" 的 api_key, base_url, temperature）当 kwargs 传给 provider
⑤ 处理 thinking_enabled / reasoning effort
⑥ 如果有 vLLM/Codex/MindIE 特殊处理，在此应用
```

🆕 **meta field 集合变大了**（`factory.py:20-45` 附近）。除了 `use` / `name` / `supports_thinking` / `supports_vision` / `supports_reasoning_effort`，v2.2.0 还要排除：

- `reasoning` —— 声明式 reasoning 契约（issue #5073），由 `deerflow.models.reasoning` 消费，**不是** provider 参数；
- `request_admission` —— DeerFlow 自己的请求准入控制，同样不能透传给 provider；
- `aliases` 等选择用的元数据。

之所以重要：这些字段一旦漏排，会作为未知 kwargs 直接塞进 `ChatOpenAI(...)` 之类的构造函数，报的是 provider 侧的类型错误，完全看不出根因在 DeerFlow 的配置层。

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

## Thinking / Reasoning 跨 Provider 处理

v2.2.0 把"这个模型能不能思考、怎么关、怎么传档位"从**散在工厂里的 if 分支**收敛成一个声明式契约，实现在 `deerflow/models/reasoning.py`。

### 契约解析（`resolve_reasoning_contract`，`reasoning.py:105`）

只有 YAML 里写了 **mapping 形态**的 `reasoning:` 才算声明契约（`source="contract"`），否则退回 legacy 布尔量（`source="legacy"`，`supports_thinking` → `optional`，`supports_reasoning_effort` → 通用档位集合）。

```python
ReasoningContract(
    thinking=...,            # unsupported | optional | required
    effort=EffortContract(values, default, aliases, path, strict=True) | None,
    on_disable_request=...,  # keep_enabled | reject
    dialect=...,             # auto | openai_extra_body | anthropic | vllm_chat_template | ollama | none
    history=...,             # preserve | clear | None
)
```

注意 `isinstance(declared, ReasoningCapabilities)` 这个判定用了具体的类而不是 duck typing——它同时被 subagent 描述符构建器和测试里的 `SimpleNamespace`/mock 调用，所以"只有真配置对象才算契约"是有意为之。

### 请求求解（`resolve_reasoning_request`，`reasoning.py:142`）

输入是"调用方想要什么"（`thinking_enabled` + `reasoning_effort`），输出 `ResolvedReasoning(thinking_enabled, reasoning_effort, adjustments)`：

| 契约 | 调用方 | 结果 | adjustment |
|---|---|---|---|
| `thinking: unsupported` | 要开 | 强制关 | `thinking_unsupported` |
| `thinking: required` | 要关 + `on_disable_request: reject` | **抛 `ReasoningPolicyError`** | — |
| `thinking: required` | 要关 + `keep_enabled` | 强制开 | `thinking_forced_on` |
| `thinking: optional` | 任意 | 照办 | — |
| 无 `effort` 契约 | 给了档位 | 丢弃 | `effort_unsupported` |
| `effort` 是 legacy（`strict=False`） | 给了档位 | 原样透传 | — |
| `effort` 有 `aliases` | 给的是通用名 | 映射成 provider 值 | `effort_aliased` |
| 给了不在 `values` 里的档位 | — | 回落到 `default` | `effort_unsupported_value` |

`adjustments` 是给调用方记日志用的：契约到底改动了请求的哪一处，一眼可见，不需要反推。

### 关闭 thinking 的三种 provider 方言

`dialect` 决定关掉 thinking 时改哪个 payload 字段（`auto` 由 provider 类推断）：

```python
# OpenAI-compatible gateway
extra_body["thinking"]["type"] = "disabled"          # + reasoning_effort = "minimal"
# vLLM/Qwen
extra_body["chat_template_kwargs"]["enable_thinking"] = False
# LangChain Anthropic
kwargs["thinking"]["type"] = "disabled"
```

用户仍然**不需要**在 config 里写任何 provider 相关的关闭逻辑；但 v2.2.0 起如果他写了 `reasoning:` 契约，DeerFlow 会按契约**先裁决请求**（可能直接拒绝 `thinking: false`），再落到对应方言上——而不是先按方言拼 payload 再被 provider 报错。

### 🆕 与 legacy 布尔量的互斥校验

`ModelConfig` 的校验器（`model_config.py:206-232`）保证两种写法不能自相矛盾：

- `reasoning.thinking: required` **不能**与 `when_thinking_disabled` 共存（永远开不了，那段配置是死代码）；
- `reasoning.thinking: unsupported` **不能**与 `when_thinking_enabled` 或 thinking 快捷字段共存；
- `supports_thinking` 与 `reasoning.thinking` 矛盾时直接失败（报错点明"丢掉 legacy 标志或修正契约"）；
- 声明了自定义 `reasoning.effort.path` 时，profile 或 thinking 模板里**残留的 `reasoning_effort` 键会被拒绝**——自定义 path 是唯一的档位序列化路径，两份写法会争同一个 payload 槽位。

`reasoning` 写成布尔值或电平字符串（Ollama 的 `true`/`false`、gpt-oss 的 `low|medium|high`）时**不是**契约，仍是原生 provider 参数原样透传。
