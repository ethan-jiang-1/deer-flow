---
title: "测试模式参考"
description: "DeerFlow 测试代码中用到的所有可复用模式：FakeRedis、FrozenDatetime、Fake evaluator、Textual pilot、hermetic replay、guardrail-at-apply。"
topics: [testing, patterns, fixtures, mocking, deterministic]
---

# 测试模式参考

从 DeerFlow 的 ~290 个测试文件中提取的所有可复用模式。按频率和通用性排列。

## 1. Fake LLM（最常用）

### FakeToolCallingModel — Agent 图测试

```python
class FakeToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self  # 空操作 — 输出由 responses=[] 预编程

def build_single_tool_call_model(*, tool_name, tool_args, tool_call_id, final_text):
    return FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[{"name": tool_name, "args": tool_args, "id": tool_call_id}]),
        AIMessage(content=final_text),
    ])
```

### _CapturingFakeModel — 记录 bind_tools

```python
class _ToolSearchPromotingModel(FakeToolCallingModel):
    bound_tools_per_turn = []
    def bind_tools(self, tools, **kwargs):
        self.bound_tools_per_turn.append([getattr(t, "name", str(t)) for t in tools])
        return self
```

### Fake evaluator — Goal 测试

```python
def _fake_satisfied_evaluator(*args, **kwargs):
    return GoalEvaluation(should_continue=False, blocker="none", reason="done", evidence_signature="sig")

monkeypatch.setattr(worker, "evaluate_goal_completion", _fake_satisfied_evaluator)
```

## 2. _FakeRedis — Redis 无服务器测试

```python
class _FakeRedis:
    def __init__(self):
        self.streams = defaultdict(list)
        self.conditions = defaultdict(asyncio.Condition)
        self.counters = defaultdict(int)

    async def xadd(self, name, fields, maxlen=None, **_):
        self.counters[name] += 1
        eid = f"{self.counters[name]}-0"
        async with self.conditions[name]:
            self.streams[name].append((eid, dict(fields)))
            if maxlen and len(self.streams[name]) > maxlen:
                del self.streams[name][:len(self.streams[name]) - maxlen]
            self.conditions[name].notify_all()
        return eid

    async def xread(self, streams, count=None, block=None):
        [(name, last_id)] = list(streams.items())
        timeout = None if block is None else block / 1000
        while True:
            async with self.conditions[name]:
                entries = [(e, f) for e, f in self.streams.get(name, []) if _stream_id_gt(e, last_id)]
                if entries:
                    return [(name, entries[:count] if count else entries)]
                if timeout is None: return []
                try: await asyncio.wait_for(self.conditions[name].wait(), timeout=timeout)
                except TimeoutError: return []
```

`asyncio.Condition` 实现阻塞 `XREAD` 语义。支持 pipeline（`_FakeRedisPipeline`）。覆盖：TTL、MAXLEN、重试、cleanup、reconnect replay。

## 3. _FrozenDatetime — 时间冻结

```python
class _FrozenDatetime(datetime):
    _frozen: datetime | None = None
    @classmethod
    def now(cls, tz=None):
        if cls._frozen is None: return super().now(tz)
        return cls._frozen if tz is None else cls._frozen.astimezone(tz)
```

固定在 UTC 正午，day-bucketing 和 active-run duration 确定性。

## 4. _FakeClient + Textual pilot — TUI 测试

```python
class _FakeClient:
    def stream(self, message, **kwargs):
        yield StreamEvent(type="messages-tuple", data={"type":"ai","content":"Hello","id":"m1"})
        yield StreamEvent(type="end", data={"usage":{"total_tokens":3}})

async def test_rendering():
    async with app.run_test() as pilot:
        await pilot.press("h", "i")
        await pilot.press("enter")
        await _wait_until(lambda: len(app.state.rows) > 0, pilot)
        assert "Hello" in str(app.state.rows)
```

## 5. make_authed_test_app — Router 认证旁路

```python
class _StubAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        user = self._user_factory()
        request.state.user = user
        request.state.auth = AuthContext(user=user, permissions=_STUB_PERMISSIONS)
        return await call_next(request)
```

`call_unwrapped(decorated, *args, **kwargs)` 走 `__wrapped__` 链绕过 `@require_permission`。

## 6. Hermetic replay — 确定性 Gateway e2e

```python
def prepare_hermetic_extras(home: Path) -> Path:
    (home / "skills" / "public").mkdir(parents=True)
    (home / "skills" / "custom").mkdir(parents=True)
    extensions = home / "extensions_config.json"
    extensions.write_text(json.dumps({"mcpServers": {}, "skills": {}}))
    return extensions
```

空 skills + 空 MCP + 禁用 memory/summarization = 跨 record/replay 的字节-相同 prompt。

## 7. Guardrail-at-apply — LLM 输出独立校验

Memory staleness review 中，LLM 建议删除的 fact 由 apply 层交叉校验：

```python
def _apply_updates(existing, updates, config):
    if stale_to_remove := updates.get("staleFactsToRemove"):
        allowed_ids = {f["id"] for f in _select_stale_candidates(existing, config)}
        stale_to_remove = [r for r in stale_to_remove if r["id"] in allowed_ids]
```

即使 `staleness_review_enabled=False`，guardrail 仍然运行。

## 8. threading.Barrier — 并发测试

```python
barrier = threading.Barrier(3)
def worker():
    barrier.wait()  # 三个线程同时进入
    sandbox.execute_command("ls")

threads = [threading.Thread(target=worker) for _ in range(3)]
for t in threads: t.start()
for t in threads: t.join()
# 断言：execute_command 的进入/退出从未交错
```

## 9. Fake E2B SDK — 云沙箱测试

```python
class FakeCommandsAPI:
    def run(self, cmd, **kwargs):
        return {"stdout": "output", "stderr": "", "exit_code": 0}
class FakeClient:
    @property
    def commands(self): return FakeCommandsAPI()
```

完整的 fake SDK（FakeCommandsAPI、FakeFilesAPI、FakeSandboxClass）覆盖 sandbox 创建、生命周期、错误恢复、文件操作、并发获取。

## 10. 测试隔离配方

```python
@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    monkeypatch.setattr("deerflow.sandbox.sandbox_provider._default_sandbox_provider", None)
    monkeypatch.setattr("deerflow.config.title_config._title_config", TitleConfig(enabled=False))
    monkeypatch.setattr("deerflow.config.memory_config._memory_config", MemoryConfig(enabled=False))
    config = AppConfig.model_validate({...})
    monkeypatch.setattr("deerflow.client.get_app_config", lambda: config)
    return tmp_path
```

## 11. 何时用什么

| 要测什么 | 用什么模式 |
|---------|-----------|
| Agent wiring（中间件链） | `@patch create_agent` + 列表断言 |
| Agent 图行为（tool call） | `FakeToolCallingModel` + real `create_agent` |
| Gateway e2e（shape drift） | Hermetic replay + golden JSON |
| LLM-based 功能（memory/goal） | Fake evaluator + guardrail-at-apply |
| Redis 集成 | `_FakeRedis` + `asyncio.Condition` |
| Router 端点 | `make_authed_test_app` |
| 时间敏感计算 | `_FrozenDatetime` |
| 并发安全 | `threading.Barrier` |
| TUI | `_FakeClient` + Textual `pilot` |
| 文件系统安全 | 参数化 + 精确 `PermissionError` |
