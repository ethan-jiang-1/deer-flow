# 实现精准 Skill 选择的三条路径

全部基于已有积木。

## 路径 A：扩展 Gateway context key（最小改动，最大效果）

**利用的积木：** `_CONTEXT_CONFIGURABLE_KEYS` + `_get_runtime_config()` + `_available_skill_names()`

在 `_CONTEXT_CONFIGURABLE_KEYS` 中加 `"skills"`，在 `_make_lead_agent()` 中读它，把它传入 `_available_skill_names()`。然后调用方可以：

```
POST /api/threads/{id}/runs/stream
{
  "input": {...},
  "context": {
    "agent_name": "my-agent",
    "skills": ["k8s-deploy", "python-testing"]
  }
}
```

**优势：** 任何能调 HTTP 的系统都可以精准指定 skill。外部编排器、CI/CD、甚至前端页面都可以。

**代码改动量：** ~5 行。`services.py` 加 1 个 key，`agent.py` 加 3-4 行读 cfg + 优先使用逻辑。

## 路径 B：Embedded Client 路径增强（已有能力 + 加动态切换）

**利用的积木：** `DeerFlowClient.available_skills`（已存在但只在 `__init__`）

让 `available_skills` 变成 `chat()`/`stream()` 的 per-call 参数而不是 `__init__` 参数。当前 `chat()` 已支持 per-call 覆盖 `model_name`, `thinking_enabled`, `subagent_enabled` 等（client.py 的 docstring 已文档化），加 `available_skills` 是同一模式。

**优势：** 同一 client 实例可以执行不同 skill 集合的多个任务，不需要创建多个 instance。

**代码改动量：** ~15 行。在 `chat()`/`stream()` 签名中加参数，在 `_ensure_agent()` 的 config key 和 `apply_prompt_template` 调用中使用 per-call 值而不是 instance 值。

## 路径 C：Skill Deferred Registry 模式（中长期方案）

**利用的积木：** `DeferredToolRegistry` + ContextVar 隔离 + `skill_search` tool

创建 `DeferredSkillRegistry`，类似 `DeferredToolRegistry`：
- Session 开始：所有 skill 的 SKILL.md body 不注入 prompt，只注入 name+description
- 外部系统（或 LLM）调用 `skill_search("k8s deploy")` → promote 匹配 skill
- 已 promote 的 skill 的完整 instructions 被注入到后续 prompt
- ContextVar 保证 per-request 隔离

**优势：** 支持"自主静默执行"中由外部系统（或 LLM）按需加载 skill。同时解决了 Q1 的 context budget 问题。

**代码改动量：** ~200 行。新的 registry 类 + prompt 生成逻辑调整 + middleware 或 prompt template 修改。

---

## 一个具体场景的演练

假设你的"长城任务"是这样运作的：

1. CI/CD 触发一个部署任务
2. 需要用到 `k8s-deploy`, `python-testing`, `db-migration` 三个 skill
3. 必须保证这三个 skill 被加载——不能依赖 LLM 自己去想

### 现在就能做到的（路径 A 组合）：

```bash
# CI/CD 脚本直接调 Gateway API
curl -X POST http://localhost:8001/api/threads/task-001/runs/wait \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "messages": [{
        "role": "human",
        "content": "执行长城任务：部署 v2.3.1 到生产环境..."
      }]
    },
    "context": {
      "agent_name": "deploy-agent",
      "skills": ["k8s-deploy", "python-testing", "db-migration"]
    }
  }'
```

前提是路径 A 的 5 行改动已完成。

### 现在就能做到的（不改变代码，利用 agent config）：

1. 预先创建 agent config：

```yaml
# agents/deploy-agent/config.yaml
name: deploy-agent
skills: [k8s-deploy, python-testing, db-migration]
```

2. 调 API：

```bash
curl -X POST .../runs/wait -d '{
  "input": {...},
  "context": {"agent_name": "deploy-agent"}
}'
```

**这种方式不需要任何代码改动。** 缺点是需要为每种 skill 组合预先创建 agent。

### 现在就能做到的（利用 Embedded Client）：

```python
# Python 脚本，直接在进程中执行
from deerflow import DeerFlowClient

client = DeerFlowClient(
    available_skills=["k8s-deploy", "python-testing", "db-migration"],
    agent_name="deploy-agent",
)
result = client.chat(
    "执行长城任务：部署 v2.3.1...",
    thread_id="task-001",
)
```

**这种方式也不需要任何代码改动。** 缺点是你必须在 Python 进程中运行。
