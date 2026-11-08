---
title: "测试 Skills 和 Agent Workflow"
description: '怎么测一个 SKILL.md 被正确加载和执行、agent 在 workflow 中的行为序列、trajectory testing、单步评测。'
topics: [testing, skills, workflow, trajectory, evaluation]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 测试 Skills 和 Agent Workflow

## 测试一个 Skill 是否被正确加载

### 方式 A：验证 prompt 中是否包含 skill 信息

```python
def test_skill_appears_in_prompt(monkeypatch):
    skill = Skill(
        name="my-skill", description="Does X when asked",
        skill_dir=Path("/tmp/my-skill"),
        skill_file=Path("/tmp/my-skill/SKILL.md"),
        relative_path=Path("my-skill"), category="custom",
        allowed_tools=["read_file", "bash"], enabled=True,
    )
    monkeypatch.setattr(prompt_module, "_get_enabled_skills", lambda: [skill])

    prompt = apply_prompt_template()
    assert "my-skill" in prompt
    assert "Does X when asked" in prompt
```

### 方式 B：验证 skill registry 行为

```python
def test_skill_filtering_respects_enabled_only():
    storage = LocalSkillStorage(host_path=tmp_path)
    # enabled_only=True → 只返回 extensions_config.json 中 enabled 的 skill
    skills = storage.load_skills(enabled_only=True)
    assert all(s.enabled for s in skills)

def test_bash_subagent_hidden_when_host_bash_disabled(monkeypatch):
    monkeypatch.setattr(registry_module, "is_host_bash_allowed", lambda: False)
    names = get_available_subagent_names()
    assert "bash" not in names
    assert names == ["general-purpose"]
```

## 测试 Agent 的行为序列（Trajectory Testing）

不只看最终回答——验证 agent **走过了正确的路**。

### interrupt_before：在工具执行前截停

来自 LangChain 官方推荐模式：

```python
from langgraph.graph import interrupt_before

def test_agent_selects_correct_tool():
    graph = create_agent(model, tools, middleware, system_prompt)
    compiled = graph.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["tools"],  # ← 停在这里，不真正执行
    )

    result = compiled.invoke(
        {"messages": [HumanMessage(content="列出 workspace 的文件")]},
        config={"configurable": {"thread_id": "1"}},
    )

    # 检查 agent 决定调哪个工具——不消耗 token 执行它
    last_msg = result["messages"][-1]
    tool_names = [tc["name"] for tc in last_msg.tool_calls]
    assert "ls" in tool_names
```

这个模式有巨大优势：50% 的生产测试可以用它，快、便宜、只测决策点。

### 流式事件事后检查 trajectory

```python
def test_agent_workflow_sequence():
    """验证 agent 执行了正确的步骤序列：读规范 → 实现 → 测试"""
    events = list(client.stream(
        "按 /mnt/project/specs/hello.spec.md 实现 hello 模块",
        thread_id="wf-test-1"
    ))

    tool_sequence = []
    for e in events:
        if e.type == "messages-tuple":
            if e.data.get("tool_calls"):
                tool_sequence.extend(tc["name"] for tc in e.data["tool_calls"])

    # 验证步骤顺序：先读文件，再写文件，最后跑测试
    assert tool_sequence.index("read_file") < tool_sequence.index("write_file")
```

### AgentEvals：轨迹匹配库

如果要做更正式的 trajectory testing：

```python
from agentevals.trajectory import create_trajectory_evaluator

evaluator = create_trajectory_evaluator(
    match_mode="unordered",  # 工具调用顺序无关
    # 也可用: "strict" (严格顺序), "subset" (只允许这些工具), "superset" (至少这些)
)

result = evaluator(actual_trajectory, reference_trajectory)
assert result["match"] is True
```

`pip install agentevals`（LangChain 开源，轻量）。

## 测试 Agent 在 Workflow 中的条件分支

```python
def test_agent_asks_clarification_when_ambiguous():
    config = {"configurable": {"thread_id": "2"}}

    # Turn 1: 给一个模糊需求
    result = graph.invoke(
        {"messages": [HumanMessage(content="帮我部署")]},
        config=config,
    )

    # Agent 应该反问
    last = result["messages"][-1]
    tool_names = [tc["name"] for tc in (last.tool_calls or [])]
    assert "ask_clarification" in tool_names or "部署" in str(last.content)
    # 不强制断言内容——LLM 输出不可精确预测
```

## 测试 Skill 对 Prompt 内容的影响

```python
def test_skill_allowed_tools_restrict_agent():
    """Skill 声明 allowed-tools: [read_file, write_file]。Agent 不应看到 bash。"""
    skill = _make_skill("code-reviewer", allowed_tools=["read_file", "write_file"])

    @patch("deerflow.agents.factory.create_agent")
    def verify(mock_create):
        create_deerflow_agent(model, features=RuntimeFeatures(sandbox=True))
        tools = [t.name for t in mock_create.call_args[1]["tools"]]
        assert "bash" not in tools  # skill 的 allowed-tools 过滤了 bash
        assert "read_file" in tools
```

## 多轮对话 + 条件逻辑

```python
def test_multi_turn_with_checkpointer():
    checkpointer = MemorySaver()
    graph = create_agent(model, tools, middleware).compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "t-multi"}}

    # Turn 1
    r1 = graph.invoke(
        {"messages": [HumanMessage(content="记住数字 42")]}, config=config
    )
    # Turn 2 — 同一个 thread_id，有记忆
    r2 = graph.invoke(
        {"messages": [HumanMessage(content="我刚才说的数字是多少？")]}, config=config
    )

    assert "42" in r2["messages"][-1].content
```

## 决策：什么该测，怎么测

| 要测的东西 | 方法 | 需要 LLM？ |
|-----------|------|-----------|
| Skill 是否出现在 prompt 中 | monkeypatch + 字符串断言 | 否 |
| Skill registry 是否正确过滤 | monkeypatch + 列表断言 | 否 |
| Agent 选了正确的工具 | `interrupt_before=["tools"]` | 是（但跳过执行） |
| Agent 的工具调用顺序 | 流式事件事后分析 | 是 |
| 中间件链顺序 | `@patch create_agent` + 列表断言 | 否 |
| Prompt 内容是否正确 | monkeypatch + 字符串断言 | 否 |
| 多轮对话记忆 | MemorySaver + 同一 thread_id | 是 |
| 文件系统安全 | 参数化 + 精确 PermissionError | 否 |
| Sub-agent 事件发射 | mock executor + 事件列表断言 | 否 |

## 关键源码

计数为 v2.2.0 实测 `def test` 数。

| 文件 | 内容 |
|------|------|
| `backend/tests/test_lead_agent_prompt.py` | prompt 注入测试（**33** 个 `def test_`，v2.1.0 为 29） |
| `backend/tests/test_lead_agent_skills.py` | skill 过滤测试（**20** 个 `def test_`） |
| `backend/tests/test_subagent_prompt_security.py` | sub-agent prompt 安全（9 个 `def test_`） |
| `backend/tests/test_deferred_promotion_integration.py` | 图级别 tool_search 测试（真跑 `create_agent`：turn 1 隐藏 MCP 工具 → `tool_search` 提升 → turn 2 schema 绑定） |
| `backend/tests/test_deferred_tool_promotion_real_llm.py` | 同一 hide/promote 回路的真实 LLM 版（`:42` 的 skipif 明写 `os.getenv("ONEAPI_E2E") != "1"`，所以要 `ONEAPI_E2E=1 OPENAI_API_KEY=... OPENAI_API_BASE=...` 才跑；docstring 原话 "Skipped unless ``ONEAPI_E2E=1`` is set so this doesn't burn credits on every run"） |
| `backend/tests/test_client_e2e.py` | 多轮对话 + 文件系统 e2e |
| `backend/tests/conftest.py` | SkillStorage + TitleConfig 单例自动重置 |

## 🆕 v2.2.0：skill 相关测试的规模与两道门

| 指纹 | v2.1.0 | v2.2.0 |
|---|---|---|
| `backend/tests/test_skill*.py` / `test_skills*.py` | 37 | **86** |
| `tests/skills/*.py`（仓库根，公开技能脚本回归） | 5 | **21** |
| `backend/tests/blocking_io/test_skill*.py` | — | **10**（export / manage_tool / mutation_host / custom_router / install / listing_router / load / reload / router / update_router） |
| `test_extension_*.py` | 20 | **31** |

**第一道门（原有）**：`skills/public/skill-reviewer/` 内置的只读评审器通过 harness 工具 `review_skill_package`（实现 `tools/builtins/review_skill_package_tool.py`）评审技能包（契约在 `contracts/skill_review/` 的 4 个 schema），CI 侧由 `scripts/review_changed_public_skills.py` 执行；waiver 只能来自 trusted base revision，blocker 永不可豁免。

**第二道门（2.2 新增）**：`skill-review-ci.yml` 里的 `skill-tests` job——单独 checkout 一个 job、单独装依赖，跑 `tests/skills/` 的 21 个文件。要点四条：

1. 装完依赖先做一次**依赖探针**：`import duckdb, openpyxl, requests`——这三个是技能脚本的可选依赖，缺了它们测试会大面积 skip 而不是失败，探针把"静默 skip"变成"装机失败"；
2. `uv run --locked python -m pytest ../tests/skills -q -rs`：`-rs` 把 skip 原因打到输出里，同样是防静默；`--locked` 保证不悄悄重解依赖；
3. `PYTHONDONTWRITEBYTECODE: "1"`（job 级 env）：技能脚本会被 `importlib.util.spec_from_file_location` 按路径加载，不写 `.pyc` 免得污染被检查的目录——workflow 注释原话 "Test imports must not leave .pyc files in the reviewed skill packages."；
4. `timeout-minutes: 10` + `if: ... draft == false`（与 backend 各 job 同构）；
5. 这个 job **独立于 package review**——根 `AGENTS.md` 的 TDD 段原文："Public skill script regressions live in `tests/skills/` and run in Skill Review CI independently of package review."

**解释**：`tests/skills/` 从"不进 CI 的手动套件"变成"独立 CI job"，是这个域里最典型的 v2.2 变化——不是新增了测试，而是**把已有的测试从"没人跑"挪到"每个 PR 都跑"**。技能脚本是会部署到沙箱里被 agent 执行的代码，它的回归成本比普通代码更高。
