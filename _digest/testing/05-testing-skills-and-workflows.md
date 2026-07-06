---
title: "测试 Skills 和 Agent Workflow"
description: "怎么测一个 SKILL.md 被正确加载和执行、agent 在 workflow 中的行为序列、trajectory testing、单步评测。"
topics: [testing, skills, workflow, trajectory, evaluation]
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

| 文件 | 内容 |
|------|------|
| `tests/test_lead_agent_prompt.py` | prompt 注入测试（15 个） |
| `tests/test_lead_agent_skills.py` | skill 过滤测试（9 个） |
| `tests/test_subagent_prompt_security.py` | sub-agent prompt 安全 |
| `tests/test_deferred_tool_registry_promotion.py` | 图级别 tool_search 测试 |
| `tests/test_client_e2e.py` | 多轮对话 + 文件系统 e2e |
| `tests/conftest.py` | SkillStorage + TitleConfig 单例自动重置 |
