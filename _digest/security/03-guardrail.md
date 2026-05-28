# Guardrail 与审计

Tool 执行前有两层保护：Guardrail（可插拔授权）和 SandboxAudit（bash 命令模式匹配）。

## Guardrail 系统

`deerflow/guardrails/middleware.py` — 在 middleware 链第 6 位，包裹每个 `wrap_tool_call` / `awrap_tool_call`。

### 执行流

```
LLM 产出 tool_call
  → GuardrailMiddleware.wrap_tool_call(request)
    → 构建 GuardrailRequest(tool_name, tool_input=tool_call["args"], ...)
    → provider.evaluate(gr)
      ├── 异常(GraphBubbleUp) → re-raise（保留 LangGraph 控制流）
      ├── 异常(其他) → fail_closed=默认 deny / fail_closed=False=放行
      ├── decision.allow=False → 返回错误 ToolMessage
      └── decision.allow=True → handler(request) 继续执行
```

**注意：** Guardrail 收到的是 LLM 产出的 `tool_call["args"]`（原始 dict），不是 tool 内部经过参数校验和路径解析后的实际入参。这意味着 guardrail provider 无法审计 tool 内部的路径翻译结果。

### GuardrailProvider 协议

`deerflow/guardrails/provider.py:40` — 任意实现了 `name`、`evaluate`、`aevaluate` 的类都可用：

```python
class GuardrailProvider(Protocol):
    name: str
    def evaluate(self, gr: GuardrailRequest) -> GuardrailDecision: ...
    async def aevaluate(self, gr: GuardrailRequest) -> GuardrailDecision: ...
```

### AllowlistProvider（内置）

`deerflow/guardrails/builtin.py:6` — 零依赖白/黑名单：

```yaml
# config.yaml
guardrails:
  enabled: true
  fail_closed: true
  provider:
    use: "deerflow.guardrails.builtin:AllowlistProvider"
    config:
      allowed_tools: ["bash", "ls", "read_file", "write_file"]
```

规则：
- 设了 `allowed_tools` → 不在白名单的 tool 全拒绝
- 设了 `denied_tools` → 在黑名单的 tool 拒绝
- 两者都不设 → 全放行

### OAP 兼容

`GuardrailDecision` 和 `GuardrailReason` 使用 `oap.*` 前缀的错误码（`oap.tool_not_allowed`, `oap.allowed`），与外部 OAP policy engine 兼容。但 DeerFlow 本身不绑定 OAP 实现 — 用户需要自己提供。

---

## SandboxAuditMiddleware

`deerflow/agents/middlewares/sandbox_audit_middleware.py` — 在 middleware 链第 7 位，**只审计 bash 命令**。

### 审计流程

```
bash tool 执行
  → 输入清洗: 拒绝空命令 · 拒绝 >10,000 字符 · 拒绝 null byte
  → 全命令 regex 扫描 (_HIGH_RISK_PATTERNS)
  → 子命令切分扫描 (按 && / || / ; 分割)
    → 高危命中 → block（返回错误 ToolMessage）
    → 中危命中 → warn（在结果后附加警告）
    → 无命中 → pass
  → 写审计日志 logger.info("[SandboxAudit]")
```

### 高危模式（block）

`rm -rf /` 变体 · `dd if=` · `mkfs` · `cat /etc/shadow` · 重定向到 `/etc/` · pipe 到 `sh`/`bash` · command substitution 中用 `curl`/`wget`/`python`/`base64` · `base64 -d |` 管道 · 覆盖 `/usr/bin/`/`/bin/`/`/sbin/` · 覆盖 shell 启动文件 · `/proc/*/environ` 泄露 · `LD_PRELOAD`/`LD_LIBRARY_PATH` 注入 · `/dev/tcp/` 网络 · fork bomb

### 中危模式（warn，不拦截）

`chmod 777` · `pip install` · `apt-get install` · `sudo`/`su` · `PATH=` 修改

### 覆盖盲区

- **只覆盖 bash** — `read_file`、`write_file`、`str_replace`、`ls`、`glob`、`grep` 完全没有内容审计
- **看到的是 LLM 原文** — 审核的是 LLM 请求的原始命令，不是沙箱层路径解析后的实际 command。在 local 模式下，`cd` 前缀已被工具层注入，audit 中间件看到的命令已包含 `cd /mnt/user-data/workspace && ...` 前缀，但 **路径参数中的虚拟路径尚未翻译为 host 实际路径**

---

## Tool 层安全

### 输出截断

防止 LLM 上下文被过大输出撑爆：

| 操作 | 截断方式 | 上限 |
|------|---------|------|
| bash | middle (head + tail) | 20,000 |
| read_file | head | 50,000 |
| ls | head | 20,000 |
| glob | hard cap | 200 |
| grep | hard cap | 100 |

### 错误信息脱敏

`tools.py:425` — 在 local 模式下，错误消息中的 host 路径被替换回虚拟路径，防止泄露 `~/.deer-flow/users/{user_id}/threads/{thread_id}/...` 这类目录结构。

### 路径脱敏

`mask_local_paths_in_output` (`tools.py:541`) — 所有 sandbox 操作输出都被正则扫描，host 路径替换回虚拟路径。覆盖 user-data、skills、ACP workspace、custom mount 等所有映射。

### 文件操作并发控制

`deerflow/sandbox/file_operation_lock.py` — `str_replace` 和 `write_file` 对 `(sandbox_id, path)` 获取 lock，防止同一 sandbox 内两个操作竞争写同一文件。使用 `WeakValueDictionary` 防内存泄漏。
