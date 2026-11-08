---
title: "Guardrail 插件：Protocol 协议 + 策略模式 + fail_closed"
description: "- `deerflow/guardrails/provider.py` — `GuardrailProvider` Protocol + 数据类"
topics: [hooks, extension, plugin-system]
---

# Guardrail 插件：Protocol 协议 + 策略模式 + fail_closed

**核心文件：**
- `deerflow/guardrails/provider.py` — `GuardrailProvider` Protocol + 数据类
- `deerflow/guardrails/middleware.py:20` — `GuardrailMiddleware` 调用方
- `deerflow/guardrails/builtin.py` — 内置 `AllowlistProvider`
- `deerflow/config/guardrails_config.py` — 配置单例

Guardrail 是 DeerFlow 的 **pre-tool-call 授权系统**。每个 tool call 在执行前都要经过 Guardrail 审批。这是安全防护的最前线。

## Provider Protocol

```python
@runtime_checkable
class GuardrailProvider(Protocol):
    name: str

    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision: ...
    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision: ...
```

**不需要继承任何基类**——任何有 `name` 属性 + `evaluate`/`aevaluate` 方法的类都可以作为 guardrail provider。DeerFlow 用 `runtime_checkable` + `isinstance` 验证。

## 数据流

```
LLM → tool_call
        │
        ▼
GuardrailMiddleware.wrap_tool_call()
        │
        ├─ GuardrailRequest(
        │     tool_name="bash",
        │     tool_input={"command": "rm -rf /"},
        │     agent_id="lead-agent",
        │     thread_id="thread_xxx",
        │     is_subagent=False,
        │     timestamp="2025-01-..."
        │   )
        │
        ▼
provider.evaluate(request)
        │
        ▼
GuardrailDecision(
    allow=False,           # allow=True → 执行 tool
    reasons=[GuardrailReason(code="BLOCKED_PATTERN")],
    policy_id="allowlist-v1",
)
        │
        ├─ allow=True → handler(request) → tool 执行
        └─ allow=False → ToolMessage("Tool denied: ...") → tool 不执行
```

## 配置

```yaml
# config.yaml
guardrails:
  enabled: true
  fail_closed: true        # provider 异常 → deny（默认）；false → 放行
  passport: "my-passport-id"
  provider:
    use: "deerflow.guardrails.builtin:AllowlistProvider"
    config:
      allowed_tools: ["read_file", "ls", "bash"]
```

配置通过 `guardrails_config.py` 的单例模式传播：

```python
_guardrails_config: GuardrailsConfig | None = None

def get_guardrails_config() -> GuardrailsConfig:
    if _guardrails_config is None:
        _guardrails_config = GuardrailsConfig()  # 默认：enabled=False
    return _guardrails_config

def load_guardrails_config_from_dict(data: dict) -> GuardrailsConfig:
    global _guardrails_config
    _guardrails_config = GuardrailsConfig.model_validate(data)
    return _guardrails_config
```

## fail_closed vs fail_open

`GuardrailMiddleware` 中的异常处理 (`guardrails/middleware.py`):

```python
try:
    decision = await provider.aevaluate(request)
except Exception as e:
    if fail_closed:
        return ToolMessage("Tool denied: guardrail evaluation failed")
    else:
        # fail_open → 放行
        return handler(request)
```

**默认 `fail_closed=True`**。这是标准的安全实践——不确定时拒绝。

## 内置实现：AllowlistProvider

`deerflow/guardrails/builtin.py` 提供了一个最简单的 guardrail：按名白名单。

```python
class AllowlistProvider:
    name = "allowlist"

    def __init__(self, allowed_tools: list[str] | None = None, **kwargs):
        self._allowed = set(allowed_tools or [])
        ...

    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        if request.tool_name in self._allowed:
            return GuardrailDecision(allow=True)
        return GuardrailDecision(
            allow=False,
            reasons=[GuardrailReason(code="NOT_IN_ALLOWLIST")]
        )
```

## 如何写自定义 Guardrail Provider

```python
from deerflow.guardrails.provider import (
    GuardrailRequest, GuardrailDecision, GuardrailReason
)

class MyGuardrail:
    name = "my-guardrail"

    def __init__(self, blocked_patterns: list[str] | None = None, **kwargs):
        self._blocked = set(blocked_patterns or [])

    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        args_str = str(request.tool_input).lower()
        for pattern in self._blocked:
            if pattern in args_str:
                return GuardrailDecision(
                    allow=False,
                    reasons=[GuardrailReason(
                        code="BLOCKED_PATTERN",
                        message=f"Pattern '{pattern}' detected"
                    )]
                )
        return GuardrailDecision(allow=True)

    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        return self.evaluate(request)  # sync fallback
```

然后在 `config.yaml`：

```yaml
guardrails:
  enabled: true
  provider:
    use: "my_package.guardrails:MyGuardrail"
    config:
      blocked_patterns: ["DROP TABLE", "rm -rf"]
```

## Guardrail 的局限性

- **只能看到 LLM 原始 `tool_call["args"]`**，看不到 tool 内部路径翻译后的实际文件路径。SandboxAuditMiddleware 的审计是基于翻译后路径的。
- **不能修改 tool 参数**——只能 allow/deny。如果你需要修改参数（比如 sanitize），应该用 `wrap_tool_call` 的 `request.override()` 模式写一个 middleware。
- **对 subagent 不生效？** — Guardrail 在 subagent 链中是可选的（取决于 `build_subagent_runtime_middlewares()` 是否加了它），且 `is_subagent=True` 在 request 中传递。Provider 可以据此做不同决策。
