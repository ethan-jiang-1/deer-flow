---
title: "CI 与自动化测试"
description: "从本地实验到 CI 流水线：GitHub Actions 模板、@requires_llm 标记、环境隔离、Token 预算、决策矩阵。"
topics: [testing, ci, automation, github-actions, isolation]
---

# CI 与自动化测试

## DeerFlow 自己的 CI 是怎么跑的

源码：`.github/workflows/backend-unit-tests.yml`

```yaml
name: Unit Tests
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install uv
      - run: cd backend && uv sync --group dev
      - run: cd backend && make test
```

三条关键规则：
- **LLM 测试在 CI 中全部跳过**——`@requires_llm` 标记检查 `CI=true` 或缺少 `OPENAI_API_KEY`
- **只跑纯 Python 测试**——mock 一切，零外部依赖
- **阻塞 IO 门禁**——`make test-blocking-io` 在 `backend/**` 变更时触发

## 为你的 DeerFlow 应用搭 CI

### 最小可用的 workflow

```yaml
# .github/workflows/agent-tests.yml
name: Agent Tests
on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }

      - name: Install DeerFlow
        run: |
          git clone https://github.com/bytedance/deer-flow.git /tmp/deer-flow
          uv add deerflow-harness --path /tmp/deer-flow/backend/packages/harness

      - name: Run unit tests (no LLM)
        run: uv run pytest tests/ -m "not llm" -v

      - name: Run LLM tests (PR only, needs secret)
        if: github.event_name == 'pull_request'
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: uv run pytest tests/ -m "llm" -v
```

### @requires_llm 标记

```python
import os
import pytest

requires_llm = pytest.mark.skipif(
    os.getenv("CI", "").lower() in ("true", "1")
    or not os.getenv("DEEPSEEK_API_KEY"),
    reason="Needs LLM API key — skipped in CI or when key is unset"
)

@requires_llm
def test_agent_generates_report():
    client = DeerFlowClient()
    result = client.chat("生成项目报告", thread_id="ci-1")
    assert len(result) > 100
```

### pytest 标记注册

```ini
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "llm: tests that need a real LLM API call",
    "slow: tests that take > 10 seconds",
]
```

## 测试环境隔离

每个测试要有独立的文件系统和配置：

```python
@pytest.fixture
def isolated_deerflow(tmp_path, monkeypatch):
    """每个测试独立——不污染全局状态。"""
    # 1. 隔离数据目录
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path / "deer-data"))

    # 2. 重置所有单例缓存
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    monkeypatch.setattr("deerflow.sandbox.sandbox_provider._default_sandbox_provider", None)

    # 3. 注入纯内存配置（不读磁盘 config.yaml）
    config = AppConfig.model_validate({
        "models": [{
            "name": "test-model",
            "use": "langchain_openai:ChatOpenAI",
            "model": "gpt-4o",
            "api_key": os.getenv("OPENAI_API_KEY", "sk-test"),
        }],
        "sandbox": {
            "use": "deerflow.sandbox.local:LocalSandboxProvider",
            "allow_host_bash": False,
        },
    })
    monkeypatch.setattr("deerflow.client.get_app_config", lambda: config)

    # 4. 禁用非必要中间件（减少 LLM 调用和副作用）
    monkeypatch.setattr("deerflow.config.title_config._title_config",
                        TitleConfig(enabled=False))
    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.get_memory_config",
                        lambda: MemoryConfig(enabled=False))

    return tmp_path
```

## Token 预算和超时控制

```python
def test_agent_stays_within_budget():
    client = DeerFlowClient()

    total_tokens = 0
    for e in client.stream("简单回答：1+1=?", thread_id="budget-test"):
        if e.type == "end":
            total_tokens = e.data["usage"]["total_tokens"]

    assert total_tokens < 500  # 简单问题不该超过 500 token

def test_agent_completes_within_timeout():
    import signal, time

    start = time.time()
    client.chat("hello", thread_id="timeout-test")
    elapsed = time.time() - start
    assert elapsed < 30  # 简单回复 30 秒内
```

在 CI 中更严格：

```yaml
- name: Run agent with timeout
  timeout-minutes: 5
  run: uv run python ci_agent_task.py
```

## 分层 CI 策略

| 层 | 什么时候跑 | 跑什么 | 耗时 |
|----|----------|--------|------|
| L1 | 每个 commit | 纯 Python 单元测试（mock 一切） | < 30s |
| L2 | PR | `@requires_llm` 的核心行为测试 | < 5 min |
| L3 | Nightly | 完整 agent workflow e2e | < 30 min |
| L4 | 发版前 | 对抗测试、安全扫描、长对话 | < 2 hr |

## 决策矩阵：我该测什么

| 你写的是… | 最小该测的 | 最好也测的 |
|-----------|----------|----------|
| 一个 SKILL.md | prompt 里有没有 skill 名字 | agent 是否按 skill 步骤执行 |
| 一个自定义 SOUL.md | prompt 里有没有 SOUL 内容 | agent 的行为是否符合 SOUL 约束 |
| 一个自定义 sub-agent | 工具白名单是否生效 | 真实 LLM 下的任务完成度 |
| 一个 custom mount | agent 能否读写 mount 路径 | 路径安全边界（.. 遍历、宿主路径） |
| 一个 workflow | 中间件链顺序 | agent 的 tool call 序列 |
| 一个 CI 集成 | `@requires_llm` 正确跳过 | 真实 LLM 端到端 |

## 关键源码

| 内容 | 位置 |
|------|------|
| CI workflow | `.github/workflows/backend-unit-tests.yml` |
| 阻塞 IO workflow | `.github/workflows/backend-blocking-io-tests.yml` |
| Makefile test 目标 | `backend/Makefile` |
| conftest 全局 fixture | `backend/tests/conftest.py` |
| e2e 环境隔离 fixture | `backend/tests/test_client_e2e.py` — `e2e_env` |
| @requires_llm 标记 | `backend/tests/test_client_e2e.py` |
