---
title: "测试模式参考"
description: "DeerFlow 测试代码中用到的所有可复用模式：FakeRedis、FrozenDatetime、Fake evaluator、Textual pilot、hermetic replay、guardrail-at-apply。"
topics: [testing, patterns, fixtures, mocking, deterministic]
---

# 测试模式参考

从 DeerFlow 的 **1,363** 个后端测试文件（`def test` 共 23,432 个）与 348 个前端单测文件中提取的所有可复用模式。按频率和通用性排列。

> **口径说明**：v2.1.0 的页面写"~290 个测试文件"，那是"提到过这几种模式的代表性文件数"，不是全量。v2.2.0 的实测口径是 `backend/tests/`（1271 个根 `test_*.py` + `blocking_io/` 89 + `monocle/` 3）+ 根 `tests/skills/` 21 个 .py；前端 348 个（`node` 202 + `dom` 146）。**下面的模式清单本身在 v2.2.0 有增补**（§11「v2.2.0 新增的三族模式」+ 原「何时用什么」顺延为 §12），因为规模翻倍后出现了一批新的高频手法。

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

## 11. v2.2.0 新增的三族模式

规模翻倍带来三类此前没有的高频手法，它们是 2.2.0 里 `test_mcp_task_service.py`（4847 行）与 `test_channels.py`（14345 行）能维持可读性的原因：

### 11.1 确定性竞态：`_repository_race_helpers.py`

`backend/tests/_repository_race_helpers.py`（61 行）用 `MissSelectSession` 把"先 select 后 write"的竞态变成**可复现的单线程事件**：让第一次 `select` 返回空（`_EmptyResult.scalar_one_or_none()` 恒为 `None`），于是必然走到"以为不存在 → INSERT → 撞唯一约束"的分支。

**解释**：这替代了 `threading.Barrier` 的一种最难写的用法——两个线程真的同时到达 select 与 insert 之间。`threading.Barrier` 在 CI 上会 flake（调度不保证），而这个 helper 把"到达那个交错点"变成**确定性**的。**取舍**：它证明的是"如果这个交错发生，代码怎么处理"，不证明"这个交错真的会发生"——后者需要真并发测试（如同族的 `test_multi_worker_run_ownership.py`）。

### 11.2 时间冻结：`_MutableDateTime`

`backend/tests/test_mcp_task_service.py:30` 的 `_MutableDateTime` 是 `FrozenDatetime` 的可变版本：`now()` 返回值由测试显式推进，所以租约过期、重试退避、通知预算这类"必须跨越若干时间片观察"的断言可以写成**线性的顺序代码**而不是 `sleep`。同族在 `test_scheduled_task_repository.py` 里体现为租约过期恢复（`test_lease_aware_recovery_preserves_live_peer_and_reclaims_expired_peer`，`:237`）。

### 11.3 语义替身的最小集：MCP service 的 9 个 Fake

`test_mcp_task_service.py:38-186` 住着 9 个窄接口替身：`FakeRepository`、`FailingApplyRepository`、`FailingCreateRepository`、`BlockingCreateRepository`、`DuplicateCreateRepository`、`DriftedThreadCreateRepository`、`FakeDriver`、`HangingDriver`、`BlockingCancelDriver`。命名规律是 **「失效模式 + 角色」**——每个替身只注入一种失效（写失败、读失败、卡住、重复、漂移线程），测试名再直接对应（`test_submit_cancels_remote_task_when_persistence_fails`、`test_run_once_releases_claim_when_driver_is_missing_or_fails`）。

**解释**：这是"替身不替换语义、只替换故障"的具体形态——`FakeDriver` 仍然走真实的 claim/release 流程，只是"远端调用"这一步被换成一个可编程返回值的对象。和 `01-doctrine.md` §5 的替身红线是同一条原则，只是在"故障注入"维度的展开。

### 11.4 后端镜像前端：`_readable_helpers.py`

`backend/tests/_readable_helpers.py`（40 行）是前端 e2e 工具 `raw-identifiers.ts`（导出 `expectNoRawIdentifiers`）的**后端孪生**：`RAW_IDENTIFIER_PATTERNS`（`:15`）逐条覆盖 UUID（`:16`）、`task-`/`task-run-` 前缀的裸 id（`:17`）、ISO 时间戳（`:18`）、5 字段 cron（`:19`）、内部枚举值（`:20`，如 `fresh_thread_per_run`/`reuse_thread`/`stop_scheduled_task`），并在 `:21` 的注释处起**后端专有追加**：不允许链接、不允许内部 snake_case 代码出现在用户可见文本里。**解释**：同一条产品规则（"用户界面上不出现原始标识符"）在两侧各自可执行，任一侧改了规则另一侧会红——这是"双端钉"在文本质量维度的实例。

### 11.5 认证可选绑定：`bind_current_user`

`backend/tests/_router_auth_helpers.py` 的 `_StubAuthMiddleware(..., bind_current_user: bool = False)` 与 `make_authed_test_app(..., bind_current_user=False)` 在 v2.2.0 新增了这个**显式 opt-in**。`_STUB_PERMISSIONS` 也扩到了 `MEMORY_READ/MEMORY_WRITE/AGENTS_READ/AGENTS_WRITE`。默认 `False` 意味着大多数 router 测试**拿不到 `current_user`**——需要用户上下文的测试必须显式打开。**解释**：这是"默认最难"原则在 fixture 层面的应用：加一个默认开着的便利开关会让权限相关的回归隐形（所有测试都有用户，谁也不会发现某条路由其实拿不到用户）；默认关则让"我确实依赖当前用户"成为一句自陈。详见 `test-strategy/09-test-infra-and-platform.md` §1。

## 12. 何时用什么

| 要测什么 | 用什么模式 |
|---------|-----------|
| Agent wiring（中间件链） | `@patch create_agent` + 列表断言 |
| Agent 图行为（tool call） | `FakeToolCallingModel` + real `create_agent` |
| Gateway e2e（shape drift） | Hermetic replay + golden JSON |
| LLM-based 功能（memory/goal） | Fake evaluator + guardrail-at-apply |
| Redis 集成 | `_FakeRedis` + `asyncio.Condition` |
| Router 端点 | `make_authed_test_app`（v2.2.0：需要用户时显式 `bind_current_user=True`） |
| 时间敏感计算 | `_FrozenDatetime` / 🆕 `_MutableDateTime`（需跨时间片推进时） |
| 并发安全 | `threading.Barrier`（真并发）；🆕 `MissSelectSession`（确定性交错点） |
| TUI | `_FakeClient` + Textual `pilot` |
| 文件系统安全 | 参数化 + 精确 `PermissionError` |
| 🆕 真 socket 传输语义 | `support/local_sockets.py` 的 `StalledWebSocketServer` / `LocalHttpServer` |
| 🆕 compose/Helm 配置 | `support/compose.py`（真 Compose 渲染）+ `support/nginx_conf.py` |
| 🆕 用户可见文本洁净 | 前端 `expectNoRawIdentifiers` / 后端 `_readable_helpers.py` |
| 🆕 故障注入 | 以「失效模式 + 角色」命名的窄接口 Fake（`Failing…Repository` / `Blocking…Driver` / `Drifted…Repository`） |
