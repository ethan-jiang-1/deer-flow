---
title: "反射加载：`resolve_variable` / `resolve_class` 动态模块系统"
description: "**核心文件：** `deerflow/reflection/resolvers.py:25-95`"
topics: [hooks, extension, plugin-system]
---

# 反射加载：`resolve_variable` / `resolve_class` 动态模块系统

**核心文件：** `deerflow/reflection/resolvers.py:25-95`

DeerFlow 的所有扩展点（model、tool、sandbox provider、guardrail provider、MCP interceptor、memory storage）都通过同一个反射机制加载：用户在 YAML/JSON 中写一个 Python 路径字符串，DeerFlow 动态 import 并校验类型。

## `resolve_variable()` — 通用反射加载

```python
def resolve_variable[T](variable_path: str, expected_type: type[T] | None = None) -> T:
    # 1. 切分路径
    module_path, variable_name = variable_path.rsplit(":", 1)
    # 2. import 模块
    module = import_module(module_path)
    # 3. 取变量
    variable = getattr(module, variable_name)
    # 4. 类型校验（可选）
    if expected_type is not None:
        if not isinstance(variable, expected_type):
            raise ValueError(...)
    return variable
```

路径格式：`"package.module:variable_name"`。例如：
- `"langchain_openai:ChatOpenAI"` — 一个类
- `"deerflow.sandbox.local:LocalSandboxProvider"` — 一个实例
- `"deerflow.guardrails.builtin:AllowlistProvider"` — 一个类

## `resolve_class()` — 带继承校验的类加载

```python
def resolve_class[T](class_path: str, base_class: type[T] | None = None) -> type[T]:
    model_class = resolve_variable(class_path, expected_type=type)  # 先确认是类
    if base_class is not None and not issubclass(model_class, base_class):
        raise ValueError(f"{class_path} is not a subclass of {base_class.__name__}")
    return model_class
```

## 缺失依赖时的友好提示

如果 import 失败是因为包没有安装，`resolve_variable` 会构建一个可操作的提示：

```python
MODULE_TO_PACKAGE_HINTS = {
    "langchain_google_genai": "langchain-google-genai",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_openai": "langchain-openai",
    "langchain_deepseek": "langchain-deepseek",
}

# 错误消息示例：
# "Could not import module langchain_google_genai. Missing dependency 'google'.
#  Install it with `uv add langchain-google-genai`, then restart DeerFlow."
```

## 使用这个机制的扩展点

| 扩展类型 | 配置位置 | 加载函数 | 校验类型 |
|----------|----------|----------|----------|
| Chat model | `config.yaml` → `models[].use` | `resolve_variable()` | — |
| Tool | `config.yaml` → `tools[].use` | `resolve_variable()` | — |
| Sandbox provider | `config.yaml` → `sandbox.use` | `resolve_variable()` | `SandboxProvider` |
| Guardrail provider | `config.yaml` → `guardrails.provider.use` | `resolve_variable()` | `GuardrailProvider` |
| Memory storage | `config.yaml` → `memory.storage_class` | `resolve_class()` | `MemoryStorage` |
| MCP interceptor | `extensions_config.json` → `mcpInterceptors[]` | `resolve_variable()` | `callable` |
| Subagent | `config.yaml` → `subagents.agents[].use` | `resolve_variable()` | — |
| ACP agent launcher | `config.yaml` → `acp_agents[].launcher` | `resolve_variable()` | — |

## 设计含义

**用户不需要写 Python 来注册插件。** 只需要：
1. 安装包（`uv add langchain-google-genai`）
2. 在 config 里写一行 class path（`use: "langchain_google_genai:ChatGoogleGenerativeAI"`）
3. DeerFlow 在下次 reload 时自动 import 并使用

**常见错误模式：**
- `rsplit(":", 1)` 确保只切最后一个冒号 → 支持 Windows 路径里的 `C:\...`
- ModuleNotFoundError 被转为含安装提示的 ImportError
- 类型校验在 import 之后，在调用之前 → 提前发现配置错误
