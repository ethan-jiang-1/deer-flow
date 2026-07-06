# 补充：Agent 专属工作目录与文件系统约定

> **问题：** Agentic workflow 场景——agent 需要一个独立的文件系统，里头放它的知识、数据、流程定义等等。DeerFlow 能不能给 agent 指定一个专属的、持久的工作目录？怎么办？

---

## 直接回答

**DeerFlow 目前没有「agent 专属持久工作目录」这个一等公民概念。** 源码中只存在两种目录模式：

| 模式 | 路径 | 生命周期 | 内容 |
|------|------|---------|------|
| Agent 元数据目录 | `.deer-flow/users/{uid}/agents/{name}/` | 持久（手动删除） | 仅有 SOUL.md + config.yaml + memory.json |
| 线程工作目录 | `.deer-flow/users/{uid}/threads/{tid}/user-data/` | 线程删除时销毁 | workspace/ + uploads/ + outputs/ |

Agent 元数据目录**不是通用数据存储**——`setup_agent` 和 `update_agent` 工具只写入那两三个文件，`DELETE /api/agents/{name}` 会整个 `shutil.rmtree`。

---

## 三个可用的变通方案

### 方案 1：Custom Mount + 固定 thread_id（最推荐）

**核心思路**：用 `config.yaml` 的 `sandbox.mounts` 给 agent 挂一个宿主机的持久目录，同时用固定的 `thread_id` 保持对话连续性。

```yaml
# config.yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: true
  mounts:
    # Agent 的"知识宇宙"——持久、可读写
    - host_path: /Users/bowhead/agent-workspaces/code-reviewer
      container_path: /mnt/agent-home
      read_only: false
```

宿主机上预先建好目录结构：

```
/Users/bowhead/agent-workspaces/code-reviewer/
├── knowledge/          # 知识库：markdown 文档、技术规范、API 参考...
├── workflows/          # 流程定义：工作流描述、检查清单、模板...
├── data/               # 工作数据：中间产物、缓存...
├── outputs/            # 输出产物
└── README.md           # 给 agent 看的目录说明
```

在 Python 中使用：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient(
    agent_name="code-reviewer",
    plan_mode=True,
)

# 固定 thread_id = 持久对话 + 持久文件
client.chat(
    "你是 code-reviewer。你的工作目录在 /mnt/agent-home。"
    "先读 /mnt/agent-home/README.md 了解目录结构，"
    "然后读 /mnt/agent-home/knowledge/ 下的所有文档作为背景知识。"
    "之后扫描 /mnt/agent-home/workflows/ 找到当前应该执行的工作流。",
    thread_id="code-reviewer-main"  # 固定的！
)
```

**优点**：
- 目录完全由你控制，想放什么放什么
- 宿主机上可以直接编辑文件，agent 立即看到
- 持久化——线程删除不影响 custom mount
- agent 可以用 git 管理这个目录（`cd /mnt/agent-home && git add -A && git commit`）

**局限**：
- Custom mount 是**全局的**——所有 agent、所有线程看到的 `/mnt/agent-home` 是同一个目录
- 如果需要多个 agent 各有各的目录，要在 mount 下建子目录，靠 agent 自觉（无框架级隔离）
- host_path 必须在 provider 初始化时存在，否则 mount 被静默跳过
- 修改 mount 配置需要重启进程

### 方案 2：仅用固定 thread_id（最简单）

不配置 custom mount，仅利用 thread workspace 的持久性：

```python
client = DeerFlowClient()

# 用固定 thread_id，workspace 不会丢
client.chat("在 workspace 里建一个 knowledge/ 目录...", thread_id="agent-main")
# → 实际路径: .deer-flow/users/default/threads/agent-main/user-data/workspace/

# 下次对话，文件还在
client.chat("读 knowledge/ 的内容，继续工作", thread_id="agent-main")
```

**优点**：零配置。**局限**：workspace 在 `.deer-flow/` 深处，不方便宿主机直接操作；线程删除时全部丢失。

### 方案 3：Skills 即约定（最轻量）

把 workflow 定义写在 Skill 的 SKILL.md 里，数据放 custom mount：

```markdown
---
name: code-review-workflow
description: 代码审查工作流：读取 /mnt/agent-home/workflows/review.md 获取流程定义
allowed-tools: [read_file, write_file, bash, ls, glob, grep]
---

# 代码审查工作流

## 初始化
1. 读取 /mnt/agent-home/README.md 了解当前上下文
2. 读取 /mnt/agent-home/knowledge/ 下的所有 .md 文件作为知识背景

## 工作流
1. 读取 /mnt/agent-home/workflows/review.md 获取审查步骤
2. 按步骤执行，中间产物放 /mnt/agent-home/data/
3. 最终报告放 /mnt/agent-home/outputs/
```

这样 agent 的行为定义（Skill）和 agent 的数据（custom mount 里的文件）分离，各司其职。

---

## 源码级关键细节

### Custom Mount 是如何工作的

配置 `sandbox.mounts` 后，`LocalSandboxProvider._setup_path_mappings()`（`local_sandbox_provider.py:82-169`）在初始化时把每个 mount 转为 `PathMapping(container_path, local_path, read_only)`。这些 mapping 是**静态的、全局的**——所有线程的 sandbox 共享同一套。

路径解析用**最长前缀匹配**（`local_sandbox.py:114`），所以 `/mnt/agent-home/knowledge` 会优先匹配到 `/mnt/agent-home` 这个 mount。

### Mount 的约束

源码 `local_sandbox_provider.py:116-164`：

| 约束 | 违规后果 |
|------|---------|
| `host_path` 必须是绝对路径 | 静默跳过 + warning |
| `container_path` 必须以 `/` 开头 | 静默跳过 + warning |
| container_path 不能与 `/mnt/skills`、`/mnt/user-data`、`/mnt/acp-workspace` 冲突 | 静默跳过 + warning |
| `host_path` 必须在 provider 初始化时存在 | 静默跳过 + warning |
| 尾部斜杠 | 自动去除 |

### 路径安全校验也覆盖 custom mount

`validate_local_tool_path()`（`tools.py:624-675`）在做路径白名单检查时，会将 custom mount 路径纳入允许范围（`tools.py:669-673`）：

```python
if _is_custom_mount_path(path):
    mount = _get_custom_mount_for_path(path)
    if mount and mount.read_only and not read_only:
        raise PermissionError(...)
    return
```

所以 agent 通过 `read_file`/`write_file`/`ls` 等工具访问 `/mnt/agent-home/...` 时，框架会识别为 custom mount 路径并放行（同时尊重 `read_only` 标记）。

### thread_id 决定 workspace 路径

`Paths.sandbox_work_dir()`（`paths.py:191`）：

```
{base_dir}/users/{user_id}/threads/{thread_id}/user-data/workspace/
```

其中 `base_dir` 默认是 `{project_root}/.deer-flow`（`runtime_paths.py:23`）。用固定 `thread_id` 意味着固定 workspace 路径。

---

## 推荐实践：Agent Workflow 文件系统约定

综合以上，建议的目录约定：

```
/Users/bowhead/agent-workspaces/          ← 宿主机的 agent 工作空间根
└── {agent-name}/                           ← 每个 agent 一个子目录
    ├── README.md                           ← agent 启动时先读这个
    ├── knowledge/                          ← 知识库（只读）
    │   ├── domain.md
    │   └── api-reference.md
    ├── workflows/                          ← 流程定义
    │   ├── daily-review.md
    │   └── deploy-checklist.md
    ├── data/                               ← 工作数据（读写）
    │   └── ...
    └── outputs/                            ← 输出产物
        └── ...
```

`config.yaml`：

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: true
  mounts:
    - host_path: /Users/bowhead/agent-workspaces
      container_path: /mnt/agent-workspaces
      read_only: false
```

Skill 或 SOUL.md 中约定：

```
你的工作目录约定：
- /mnt/agent-workspaces/{your-name}/README.md — 先读
- /mnt/agent-workspaces/{your-name}/knowledge/ — 知识库
- /mnt/agent-workspaces/{your-name}/workflows/ — 流程
- /mnt/agent-workspaces/{your-name}/data/ — 数据
- /mnt/agent-workspaces/{your-name}/outputs/ — 输出
```

这样就给每个 agent 一个逻辑上独立、物理上持久、内容上自由的文件系统——虽然不是框架级的一等公民支持，但足够实用。

---

## 相关源码

| 机制 | 文件 |
|------|------|
| VolumeMountConfig 定义 | `deerflow/config/sandbox_config.py:4-10` |
| LocalSandboxProvider mount 转换 | `deerflow/sandbox/local/local_sandbox_provider.py:82-169` |
| PathMapping 解析（最长前缀匹配） | `deerflow/sandbox/local/local_sandbox.py:19-25, 114` |
| 工具层 custom mount 路径校验 | `deerflow/sandbox/tools.py:624-675, 164-191` |
| 工作目录路径定义 | `deerflow/config/paths.py:66-80, 191` |
| ThreadDataMiddleware（工作目录创建） | `deerflow/agents/middlewares/thread_data_middleware.py` |
| Agent 元数据目录 | `deerflow/config/paths.py:159-169` |
| DeerFlowClient thread_id 流 | `deerflow/client.py:206, 503, 585` |
| config.example.yaml mounts 注释 | `config.example.yaml:606-654` |
