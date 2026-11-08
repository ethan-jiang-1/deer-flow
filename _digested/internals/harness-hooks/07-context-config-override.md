---
title: "ContextVar 运行时配置覆盖：push/pop 栈 + 测试注入"
description: "**核心文件：** `deerflow/config/app_config.py:336-337, 442-456`"
topics: [hooks, extension, plugin-system]
---

# ContextVar 运行时配置覆盖：push/pop 栈 + 测试注入

**核心文件：** `deerflow/config/app_config.py:336-337, 442-456`

`_app_config` 是进程级全局单例。但有时需要**在某个执行上下文中临时覆盖配置**——比如测试注入 mock config、或者 per-request 的特殊设置。DeerFlow 用 ContextVar 实现了一个配置覆盖栈。

## 两个 ContextVar

```python
# 当前上下文要使用的配置（覆盖全局单例）
_current_app_config: ContextVar[AppConfig | None] = ContextVar(
    "deerflow_current_app_config", default=None
)

# 嵌套上下文的栈（支持 push/pop）
_current_app_config_stack: ContextVar[tuple[AppConfig | None, ...]] = ContextVar(
    "deerflow_current_app_config_stack", default=()
)
```

## 优先级

`get_app_config()` 中的检测顺序体现了优先级：

```python
def get_app_config() -> AppConfig:
    # 1. ContextVar 覆盖（最高优先级）
    runtime_override = _current_app_config.get()
    if runtime_override is not None:
        return runtime_override

    # 2. 测试注入的自定义 config
    if _app_config is not None and _app_config_is_custom:
        return _app_config

    # 3. mtime/路径检测 → 重载
    ...
```

**ContextVar > custom_override > file-based singleton**

## push/pop 用于嵌套上下文

```python
def push_current_app_config(config: AppConfig) -> None:
    """保存当前值到栈顶，然后设置新值"""
    stack = _current_app_config_stack.get()
    _current_app_config_stack.set(stack + (_current_app_config.get(),))
    _current_app_config.set(config)

def pop_current_app_config() -> None:
    """恢复栈顶的旧值"""
    stack = _current_app_config_stack.get()
    if not stack:
        _current_app_config.set(None)
        return
    previous = stack[-1]
    _current_app_config_stack.set(stack[:-1])
    _current_app_config.set(previous)
```

用法：

```python
# 在某个上下文中临时使用不同配置
push_current_app_config(test_config)
try:
    result = run_agent(...)
finally:
    pop_current_app_config()
```

这与 Python 的 `contextlib.contextmanager` 模式一致。但 DeerFlow 目前没有提供 `@contextmanager` 装饰器版本——调用方需要手动 try/finally。

## 测试注入：`set_app_config()`

```python
def set_app_config(config: AppConfig) -> None:
    """注入自定义 config（用于测试）"""
    global _app_config, _app_config_is_custom
    _app_config = config
    _app_config_is_custom = True
```

调用后，`get_app_config()` 会跳过 mtime 检测，直接返回注入的 config。测试结束时调用 `reset_app_config()` 清理。

## 多租户隔离

DeerFlow 的用户隔离通过 `deerflow/runtime/user_context.py` 中的 `get_effective_user_id()` 实现，不通过 ContextVar config 覆盖。

```python
# user_context.py
_current_user_id: ContextVar[str] = ContextVar("deerflow_user_id", default=DEFAULT_USER_ID)

def get_effective_user_id() -> str:
    return _current_user_id.get()
```

Gateway auth middleware 在请求处理开始时设置这个 ContextVar，后续所有的 middleware、tool call、memory 更新都通过它路由到正确的用户目录。

```
HTTP request
  │
  ├─ Auth middleware → set_current_user_id("user-123")
  │
  ├─ ThreadDataMiddleware → get_effective_user_id() → user-123
  │    → 计算 thread 路径: .deer-flow/users/user-123/threads/xxx/
  │
  ├─ MemoryMiddleware → get_effective_user_id() → user-123
  │    → memory 文件: .deer-flow/users/user-123/memory.json
  │
  └─ update_agent_tool → resolve_runtime_user_id(runtime) → user-123
       → agent 写回: .deer-flow/users/user-123/agents/my-agent/
```

## 实际场景

### 场景 1：测试隔离

```python
# test 中
config = AppConfig.model_validate({...})
set_app_config(config)
try:
    result = some_function_that_calls_get_app_config()
    assert result.models[0].name == "test-model"
finally:
    reset_app_config()
```

### 场景 2：per-run 配置覆盖

```python
# 某个 run 需要临时改 model（但不影响其他 run）
override_config = get_app_config().model_copy(deep=True)
override_config.models[0].max_tokens = 8000
push_current_app_config(override_config)
try:
    await agent_run(...)
finally:
    pop_current_app_config()
```

### 场景 3：no-auth 模式

```python
# 没有 auth middleware 设置 user_id 时
get_effective_user_id()  # → "default"（DEFAULT_USER_ID 常量）
```

所有文件路径回退到 `{base_dir}/users/default/...`。
