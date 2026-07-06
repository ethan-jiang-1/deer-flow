# 一步步跟我做：从零到 DeerFlow 跑起来

> 这是一个实操指南。每一步都有可复制的命令，跟着做就行。你的机器：macOS，Docker Desktop 已装但没启动，Python 3.13 已装。

---

## 阶段一：安装与启动（~15 分钟）

### 步骤 1：启动 Docker Desktop

```bash
# 打开 Docker Desktop（会在菜单栏出现鲸鱼图标）
open -a Docker

# 等待 Docker 就绪（约 30 秒），验证：
docker info --format '{{.ServerVersion}}'
# 应该输出类似 28.0.1 的版本号
```

### 步骤 2：生成配置文件

```bash
cd /Users/bowhead/deer-flow
make config
# 输出：Copied config.example.yaml to config.yaml
```

### 步骤 3：配置模型

```bash
# 编辑 config.yaml — 找到 models: 部分
# 确认至少有一个可用的模型。用你手上有的 API key：
```

你至少需要一个模型。选一个你有的 API key：

**如果你有 DeepSeek API key：**
```bash
export DEEPSEEK_API_KEY="sk-你的key"
```

**如果你有 OpenAI API key：**
```bash
export OPENAI_API_KEY="sk-你的key"
```

config.yaml 中 models 默认已经配了 deepseek-v3 和 gpt-4o，变量的 `$` 前缀会自动从环境变量读取。**不需要改 config.yaml**，只需要 export 环境变量。

验证配置加载正确：
```bash
cd backend && PYTHONPATH=. uv run python -c "
from deerflow.config import get_app_config
c = get_app_config()
print(f'模型数量: {len(c.models)}')
for m in c.models:
    print(f'  - {m.name} ({m.model})')
"
# 应该列出至少一个模型
```

### 步骤 4：初始化 Docker 环境

```bash
cd /Users/bowhead/deer-flow
make docker-init
```

这一步会：
- 构建 gateway 和 web 两个 Docker 镜像（首次 ~5 分钟）
- 安装前端 pnpm 依赖
- 安装后端 uv 依赖

看到 `docker-init completed successfully` 就表示成了。

### 步骤 5：启动服务

```bash
make docker-start
```

Docker Compose 会启动 3-4 个容器：
- **nginx** (port 2026) — 统一入口
- **gateway** (port 8001) — FastAPI + Agent 运行时
- **frontend** (port 3000) — Next.js
- **provisioner** (port 8002) — 可选的 K3s 管理器（本地模式不会启动）

等待约 30 秒，验证：

```bash
# 健康检查
curl -s http://localhost:2026/api/health | python -m json.tool
# 应该返回 {"status": "ok"}

# 检查模型
curl -s http://localhost:2026/api/models | python -m json.tool | head -10
```

### 步骤 6：打开 Web UI

浏览器访问：**http://localhost:2026**

你会看到 DeerFlow 的聊天界面。在底部输入框输入：

```
你好，请用 Python 写一个冒泡排序
```

如果 agent 回复了代码——**恭喜，DeerFlow 跑起来了。**

---

## 阶段二：命令行实验（~20 分钟）

### 实验 1：Python REPL

开一个新终端：

```bash
cd /Users/bowhead/deer-flow/backend
PYTHONPATH=. uv run python
```

```python
>>> from deerflow.client import DeerFlowClient
>>> client = DeerFlowClient()

# 一问一答
>>> print(client.chat("用一句话解释什么是 Docker"))

# 流式输出 — 逐 token 打印
>>> for e in client.stream("列出当前工作目录下的文件"):
...     if e.type == "messages-tuple" and e.data.get("content"):
...         print(e.data["content"], end="", flush=True)
... 
>>> print()  # 换行

# 看看有哪些模型
>>> models = client.list_models()
>>> for m in models["models"]:
...     print(m["name"], "-", m.get("display_name", ""))

# 看看有哪些 skills
>>> skills = client.list_skills()
>>> print(f"共 {len(skills['skills'])} 个 skills")
```

### 实验 2：debug.py REPL

```bash
# 新终端
cd /Users/bowhead/deer-flow/backend
PYTHONPATH=. uv run python debug.py
```

```
==================================================
Lead Agent Debug Mode
Type 'quit' or 'exit' to stop
Logs: debug.log
==================================================

You: 用 Python 写一个二分查找

Agent: 当然，这里是二分查找的 Python 实现...

You: 给这个函数加上类型注解

Agent: ...
```

`debug.py` 用 `prompt_toolkit`，支持 ↑↓ 箭头键历史、Ctrl-R 搜索。日志全进 `debug.log`，终端保持干净。

### 实验 3：修改 debug.py 探索参数

编辑 `backend/debug.py` 第 93-100 行：

```python
config = {
    "configurable": {
        "thread_id": "debug-thread-001",
        "thinking_enabled": True,     # 改为 False 看看区别
        "is_plan_mode": True,         # True = agent 会用 write_todos 规划
        # "model_name": "deepseek-v3",  # 取消注释来指定模型（如果你的 config 里有多个）
    }
}
```

改完重新运行 `debug.py`，观察 plan_mode 的行为差异。

### 实验 4：试用 Agent 环境

在 `debug.py` 或 Python REPL 中：

```python
# 看看 agent 的工作目录里有什么
client.chat("ls /mnt/user-data/workspace")

# 让 agent 创建文件
client.chat("在 workspace 里创建一个 hello.txt，内容是 'Hello DeerFlow'")

# 让 agent 读回来
client.chat("读 /mnt/user-data/workspace/hello.txt 的内容")

# 让 agent 列出所有 skills
client.chat("列出 /mnt/skills/ 下的所有目录")
```

---

## 阶段三：挂载你的项目目录（~10 分钟）

这是最关键的一步——让 agent 能直接看到你的项目文件。

### 步骤 1：准备一个测试项目目录

```bash
mkdir -p /Users/bowhead/deer-flow-test-project
cat > /Users/bowhead/deer-flow-test-project/README.md << 'EOF'
# 测试项目

## 目录说明
- specs/ — 规范文件
- src/ — 源代码
EOF

mkdir -p /Users/bowhead/deer-flow-test-project/specs
mkdir -p /Users/bowhead/deer-flow-test-project/src

cat > /Users/bowhead/deer-flow-test-project/specs/hello.spec.md << 'EOF'
# Hello Service 规范

## 需求
创建一个 Python 模块 `hello.py`，提供 `greet(name)` 函数，
返回 "Hello, {name}!"。
EOF
```

### 步骤 2：配置 custom mount

编辑 `/Users/bowhead/deer-flow/config.yaml`，找到 `sandbox:` 部分，加上 mounts：

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: true          # 改为 true — agent 需要 bash
  mounts:
    - host_path: /Users/bowhead/deer-flow-test-project
      container_path: /mnt/project
      read_only: false
```

**重启服务**（mount 需要重启才能生效）：

```bash
make docker-stop
make docker-start
```

### 步骤 3：让 agent 读你的项目

在 Web UI 或 `debug.py` 中：

```
你：读 /mnt/project/README.md 了解项目结构，
    然后读 /mnt/project/specs/hello.spec.md，
    按照规范在 /mnt/project/src/hello.py 中实现 greet 函数。
```

Agent 会：
1. 读 README.md
2. 读 hello.spec.md
3. 写 src/hello.py

验证：
```bash
cat /Users/bowhead/deer-flow-test-project/src/hello.py
# 应该能看到 agent 生成的代码
```

你可以在宿主机上直接编辑文件，然后让 agent 看变化：
```bash
echo "# 新增需求" >> /Users/bowhead/deer-flow-test-project/specs/hello.spec.md
```
然后告诉 agent "我更新了规范，请重新实现"——它会读新内容。

---

## 阶段四：启动你的第一个 Sub-agent 工作流（~15 分钟）

### 步骤 1：Enable sub-agent

在 Python REPL 中：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient(
    subagent_enabled=True,   # ← 关键
    plan_mode=True,          # 让 agent 先做计划
)

# 给一个明显适合并行处理的任务
result = client.chat(
    "帮我研究三个编程语言，每个出 200 字总结：\n"
    "1) Rust 的核心特性\n"
    "2) Go 的核心特性\n"
    "3) Zig 的核心特性\n"
    "然后做一个对比总结。",
    thread_id="lang-research"
)
print(result)
```

观察：agent 应该自动分派 3 个 `general-purpose` sub-agent 并行研究，最后汇总。

### 步骤 2：用 Web UI 同时观察

打开 http://localhost:2026，在 Python 脚本跑的同时（用同一个 thread_id），可以在 Web UI 中看到 sub-agent 的执行过程（`task_started`、`task_running`、`task_completed` 事件）。

### 步骤 3：创建自定义 sub-agent（可选）

编辑 `config.yaml`，在 `subagents:` 下添加：

```yaml
subagents:
  enabled: true
  custom_agents:
    code-writer:
      description: "代码实现专家：按规范编写 Python 代码"
      system_prompt: |
        你是代码实现专家。遵循以下原则：
        1. 先读规范文件，理解需求
        2. 编写清晰、有类型注解的 Python 代码
        3. 添加 docstring
      tools: [read_file, write_file, bash, ls]
```

重启后，Main Agent 就可以调 `task("code-writer", "实现 hello 模块")`。

---

## 阶段五：之后的探索方向

跑通上面这些之后，你的下一步可以是：

| 优先级 | 做什么 | 怎么做 |
|--------|--------|--------|
| 1 | **深入文件系统** | 在你自己的真实项目中挂载目录，让 agent 读你的代码、写 spec、跑 git diff |
| 2 | **创建 Skill** | `mkdir -p skills/custom/my-skill && vim skills/custom/my-skill/SKILL.md`，在 Settings 中启用 |
| 3 | **创建自定义 Agent** | 在 Web UI Agents 页面创建，配上 SOUL.md + config.yaml |
| 4 | **写自动化脚本** | 用 `DeerFlowClient` 写 Python 脚本，固定 thread_id + SQLite checkpointer，每次运行自动执行任务 |
| 5 | **探索 MCP 工具** | 在 `extensions_config.json` 中添加 MCP server（如 GitHub MCP），扩展 agent 能力 |
| 6 | **自定义 sub-agent** | 在 config.yaml 中定义专用 sub-agent，配上专用的 tools、skills、system_prompt |

---

## 常用命令速查

```bash
# 服务管理
make docker-start        # 启动
make docker-stop         # 停止
make docker-logs         # 查看日志
make docker-logs-gateway # 只看 Gateway 日志

# 配置
make config              # 生成 config.yaml
make config-upgrade      # 合并新版 schema 字段

# Python REPL
cd backend && PYTHONPATH=. uv run python
cd backend && PYTHONPATH=. uv run python debug.py

# 查看资源
curl http://localhost:2026/api/models | python -m json.tool
curl http://localhost:2026/api/skills | python -m json.tool
```

## 如果遇到问题

| 问题 | 解决 |
|------|------|
| Docker daemon 连不上 | `open -a Docker`，等鲸鱼图标稳定 |
| Gateway 返回 401 | 需要设 `DEER_FLOW_INTERNAL_AUTH_TOKEN` 或用 session cookie |
| config.yaml 找不到 | 确认文件在 `/Users/bowhead/deer-flow/config.yaml` |
| 模型不工作 | 检查 API key 环境变量是否 export 了；`echo $DEEPSEEK_API_KEY` |
| mount 不生效 | 需要 `make docker-stop && make docker-start` 重启 |
| bash 不能执行 | 确认 `config.yaml` 中 `allow_host_bash: true` |
