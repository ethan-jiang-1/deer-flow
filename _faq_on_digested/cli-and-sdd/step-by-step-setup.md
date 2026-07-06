# 一步步跟我做：在你的项目里跑起 DeerFlow

> 目标：在 `/Users/bowhead/ai_deerflow_wiki/` 里，不依赖 Docker，纯本地把 DeerFlow 跑起来。
> 你的 Python 3.13 — 没问题，deerflow-harness 要求 ≥3.12。

---

## 阶段零：为什么不需要 Docker

DeerFlow 默认沙箱就是本地的 `LocalSandboxProvider`。整个 Harness 是一个 Python 库——`import deerflow` 就能用。Web UI、Nginx、前端这些都不是必须的。

你需要跑起来的东西就一个：**Python 脚本里 `from deerflow.client import DeerFlowClient`**。不需要启动任何服务。

---

## 阶段一：安装依赖（5 分钟，一次性）

### 步骤 1：把 deerflow-harness 加入你的项目

```bash
cd /Users/bowhead/ai_deerflow_wiki

# 把本地的 deerflow-harness 作为依赖加进去
uv add /Users/bowhead/deer-flow/backend/packages/harness
```

这一步 uv 会：
- 把 `deerflow-harness` 写入 pyproject.toml 的 dependencies
- 解析并安装它的所有依赖（langchain、langgraph、openai 等几十个包）
- 更新 uv.lock

耗时取决于网络，耐心等完。

### 步骤 2：生成你自己的 config.yaml

```bash
# 从 deer-flow 仓库复制配置模板
cp /Users/bowhead/deer-flow/config.example.yaml config.yaml
```

这会得到一个带 `$VAR` 占位符的配置。你只需要配一个模型。

### 步骤 3：告诉 DeerFlow 技能目录在哪里

DeerFlow 需要 skills 目录。你不需要复制——直接指到 deer-flow 仓库的 skills：

```bash
# 方式 A：设环境变量（推荐，每次启动前 export 一下）
export DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills

# 方式 B：或者直接改 config.yaml 里的 skills.path
# （后面会说到）
```

### 步骤 4：配置 API Key

你有哪个就用哪个：

```bash
# DeepSeek（config.example.yaml 里默认就有 deepseek-v3 的配置）
export DEEPSEEK_API_KEY="sk-你的key"

# 或 OpenAI
export OPENAI_API_KEY="sk-你的key"
```

### 步骤 5：验证一切就绪

```bash
cd /Users/bowhead/ai_deerflow_wiki

DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills \
  uv run python -c "
from deerflow.config import get_app_config
c = get_app_config()
print(f'OK — {len(c.models)} 个模型')
for m in c.models:
    print(f'  {m.name} → {m.model}')
"
```

看到输出模型列表就表示配置正确。

---

## 阶段二：第一次对话（2 分钟）

### 实验 1：一行代码跟 agent 对话

```bash
cd /Users/bowhead/ai_deerflow_wiki

DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills \
  uv run python
```

```python
>>> from deerflow.client import DeerFlowClient
>>> client = DeerFlowClient()
>>>
>>> # 你的第一次 agent 对话
>>> print(client.chat("用一句话解释什么是 Python 的 GIL"))
```

如果你看到 agent 回复了——**DeerFlow 就在你自己的项目里跑起来了。**没有 Docker、没有 Nginx、没有 Web UI，就是一个 Python 库。

### 实验 2：流式输出

```python
# 继续在同一个 Python REPL 里
>>> for evt in client.stream("用 Python 写一个斐波那契数列函数"):
...     if evt.type == "messages-tuple" and evt.data.get("content"):
...         print(evt.data["content"], end="", flush=True)
... 
>>> print()
```

你会看到 agent 逐字输出，就像 ChatGPT 那样。

### 实验 3：搞懂 agent 的工作目录在哪里

在让 agent 写文件之前，先搞清楚一个重要问题：**agent 的工作目录到底在宿主机上哪儿？**

退出 Python REPL（Ctrl+D），重新开，这次加 `DEER_FLOW_HOME`：

```bash
cd /Users/bowhead/ai_deerflow_wiki

DEER_FLOW_HOME=/Users/bowhead/ai_deerflow_wiki/.deer-flow \
DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills \
  uv run python
```

> **`DEER_FLOW_HOME` 是什么？** 它就是 DeerFlow 所有运行时数据（对话记录、工作目录、agent 配置）的根。默认是 `deer-flow/backend/.deer-flow/`，但你是在自己项目里跑，应该指定到你自己的目录。

```python
>>> from deerflow.client import DeerFlowClient
>>> client = DeerFlowClient()

# 让 agent 看看自己的工作目录
>>> print(client.chat("ls /mnt/user-data/workspace"))
# 应该是空的——新项目嘛

# 让 agent 创建一个文件
>>> print(client.chat("在 workspace 里写一个 hello.txt，内容是 'Hello from my own project'"))
```

现在去宿主机上看：

```bash
ls /Users/bowhead/ai_deerflow_wiki/.deer-flow/users/default/threads/*/user-data/workspace/
# 应该能看到 hello.txt！

cat /Users/bowhead/ai_deerflow_wiki/.deer-flow/users/default/threads/*/user-data/workspace/hello.txt
# Hello from my own project
```

**这就通了。** Agent 在沙箱里写的 `/mnt/user-data/workspace/hello.txt`，就是宿主机上 `.deer-flow/.../workspace/hello.txt`。你的项目目录就是 agent 的数据根。

### 实验 4：让 agent 看更多东西

```python
# agent 有哪些工具？
>>> print(client.chat("列出 /mnt/skills/public/ 下的目录（只列第一层）"))

# agent 能读自己刚写的文件吗？
>>> print(client.chat("读 /mnt/user-data/workspace/hello.txt 的内容"))

# 让 agent 在 workspace 下建一个子目录结构
>>> print(client.chat(
...     "在 /mnt/user-data/workspace 下创建这样的目录结构：\n"
...     "knowledge/ — 知识库\n"
...     "workflows/ — 流程定义\n"
...     "data/ — 工作数据"
... ))
```

---

## 阶段三：把 agent 接到你的项目目录（5 分钟）

这是关键一步——你希望 agent 在你的 `/Users/bowhead/ai_deerflow_wiki/` 里干活。

### 步骤 1：编辑 config.yaml

```bash
vim /Users/bowhead/ai_deerflow_wiki/config.yaml
```

找到 `sandbox:` 部分，改成这样：

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: true          # 把 false 改成 true
  mounts:
    - host_path: /Users/bowhead/ai_deerflow_wiki
      container_path: /mnt/project
      read_only: false
```

### 步骤 2：先建好宿主目录结构

因为 mount 的 host_path 必须在 DeerFlow 初始化时存在（否则被静默跳过），我们先确保目录存在（你已经有了）：

```bash
ls /Users/bowhead/ai_deerflow_wiki/
# pyproject.toml  README.md  .venv  .git  ...
```

它已经存在了——没问题。

### 步骤 3：重启 Python REPL 让新配置生效

```bash
# 退出之前的 Python REPL（Ctrl+D），重新开
cd /Users/bowhead/ai_deerflow_wiki

DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills \
  uv run python
```

```python
>>> from deerflow.client import DeerFlowClient
>>> client = DeerFlowClient()

# 现在 agent 能看到你的项目了！
>>> print(client.chat("ls /mnt/project"))
# 应该列出 pyproject.toml, README.md, .venv 等
```

### 步骤 4：让 agent 在你的项目里写东西

```python
>>> # 创建一个 specs/ 目录，写一个简单的需求规范
>>> print(client.chat(
...     "在 /mnt/project 下创建 specs/ 目录，"
...     "写一个 hello.spec.md 文件，内容是：\n"
...     "## 需求\n创建一个 greet(name) 函数返回 Hello, {name}!"
... ))

>>> # 让 agent 按照规范写代码
>>> print(client.chat(
...     "读 /mnt/project/specs/hello.spec.md，"
...     "按照规范在 /mnt/project/src/ 下创建 hello.py，实现 greet 函数"
... ))
```

验证——agent 写的文件就在你的项目里：

```bash
cat /Users/bowhead/ai_deerflow_wiki/src/hello.py
cat /Users/bowhead/ai_deerflow_wiki/specs/hello.spec.md
```

**你在宿主机上 `vim` 改了文件，agent 下一次 `read_file` 就读到新内容。**没有缓存、没有同步延迟。

---

## 阶段四：开启 sub-agent 并行干活（5 分钟）

```python
# 新开 REPL，这次开 sub-agent
>>> from deerflow.client import DeerFlowClient
>>> client = DeerFlowClient(subagent_enabled=True, plan_mode=True)

>>> # 给一个明显适合并行处理的任务
>>> result = client.chat(
...     "帮我研究三个主题，每个写 150 字总结：\n"
...     "1) LangGraph 是什么\n"
...     "2) MCP 协议是什么\n"
...     "3) SKILL.md 标准是什么",
...     thread_id="research-1"
... )
>>> print(result)
```

agent 会自动分派 3 个 `general-purpose` sub-agent 并行跑。这就是你之前问的 "main agent 启动 3 个 sub-agent"——不需要任何额外配置，`subagent_enabled=True` 就够了。

---

## 阶段五：创建你自己的 Skill（5 分钟）

Skill 就是一段 Markdown 指令，告诉 agent "遇到某类任务时怎么做"。

### 步骤 1：写一个 SKILL.md

```bash
mkdir -p /Users/bowhead/deer-flow/skills/custom/project-manager

cat > /Users/bowhead/deer-flow/skills/custom/project-manager/SKILL.md << 'EOF'
---
name: project-manager
description: >-
  项目管理助手：在 /mnt/project 中创建规范文件、管理目录结构、
  生成 README 和变更日志。
allowed-tools:
  - read_file
  - write_file
  - bash
  - ls
---

# 项目管理助手

## 工作流
当用户说"初始化项目"或"创建项目结构"时：

1. 先用 `ls /mnt/project` 看当前项目有什么
2. 确保以下目录存在：specs/, src/, tests/, docs/
3. 如果 README.md 不存在或内容太少，补充它
4. 如果用户有新需求，在 specs/ 下创建对应的规范文件
5. 所有变更记录在 CHANGELOG.md 中

## 规范文件模板
```markdown
# {功能名}

## 需求
...

## 接口
...

## 测试要点
...
```
EOF
```

### 步骤 2：启用它

编辑 `/Users/bowhead/deer-flow/extensions_config.json`：

```json
{
  "skills": {
    "project-manager": { "enabled": true }
  }
}
```

如果该文件还不存在，就用上面的内容创建它。

### 步骤 3：测试

```bash
# 确保 extensions_config.json 在 deer-flow 项目根
ls /Users/bowhead/deer-flow/extensions_config.json

# 指定 DEER_FLOW_PROJECT_ROOT 让 DeerFlow 找到 extensions_config.json
cd /Users/bowhead/ai_deerflow_wiki

DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills \
  uv run python
```

```python
>>> from deerflow.client import DeerFlowClient
>>> client = DeerFlowClient()
>>>
>>> print(client.chat("用 project-manager skill 初始化 /mnt/project 的项目结构"))
```

agent 会根据你的 SKILL.md 指令，自动创建目录、写 README、建 CHANGELOG。

---

## 阶段六：next steps

跑通上面这些之后：

| 做什么 | 怎么开始 |
|--------|---------|
| **读懂了 SKILL.md 的行为了** | 改 `skills/custom/project-manager/SKILL.md`，加新步骤，reload 测试 |
| **在自己的项目里挂载** | 改 config.yaml 的 `sandbox.mounts` 指向你的真实项目 |
| **创建自定义 Agent** | 写一个 SOUL.md + config.yaml 放 `.deer-flow/users/default/agents/` 下 |
| **自动化脚本** | `from deerflow.client import DeerFlowClient` + 固定 thread_id |
| **多 turn 协作** | 同一个 thread_id 调多次 `client.chat()`，用 SQLite checkpointer |
| **Sub-agent 自定义** | 在 config.yaml 配 `subagents.custom_agents` |

---

## 三个必须记住的 Env Var

每次在 REPL 里用 DeerFlow 之前：

```bash
# 你的 API key（至少设一个）
export DEEPSEEK_API_KEY="sk-..."

# DeerFlow 数据根——运行时数据（对话、工作目录、agent 配置）放哪
export DEER_FLOW_HOME=/Users/bowhead/ai_deerflow_wiki/.deer-flow

# Skills 目录——指向 deer-flow 仓库
export DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills
```

可以把它们写到 `.env` 文件里（`ai_deerflow_wiki/.env`），uv run 会自动加载：
```bash
cat > /Users/bowhead/ai_deerflow_wiki/.env << 'EOF'
DEEPSEEK_API_KEY=sk-你的key
DEER_FLOW_HOME=/Users/bowhead/ai_deerflow_wiki/.deer-flow
DEER_FLOW_SKILLS_PATH=/Users/bowhead/deer-flow/skills
EOF
```

---

## 如果卡住了

| 症状 | 检查 |
|------|------|
| `ModuleNotFoundError: deerflow` | 确认 `uv add /Users/bowhead/deer-flow/backend/packages/harness` 执行成功 |
| `config.yaml not found` | 确认 `/Users/bowhead/ai_deerflow_wiki/config.yaml` 存在 |
| mount 不生效 | 确认 host_path 目录存在；重启 Python REPL（mount 在 provider 初始化时读取） |
| bash 不能用 | 确认 config.yaml 中 `allow_host_bash: true` |
| skill 不被加载 | 确认 `DEER_FLOW_SKILLS_PATH` 指向正确；确认 `extensions_config.json` 在 deer-flow 项目根且有 skill 的 enabled 条目 |
