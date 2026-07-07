# 补充：本地文件系统和 Git 集成

> **问题：** 智能体需要强烈依赖本地文件系统——知识库、地图、Skills、甚至 Git 仓库全在宿主机上。要怎么处理？

---

## 核心机制：Custom Mounts（自定义挂载）

DeerFlow 的沙箱系统使用**虚拟路径**隔离 agent 和宿主机。Agent 看到的路径是 `/mnt/user-data/...`、`/mnt/skills/...`等虚拟路径，由沙箱层透明翻译为宿主机真实路径。

要让 agent 访问宿主机的任意目录（如你的知识库、Git 项目），用 `config.yaml` 中的 `sandbox.mounts`：

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: true          # 开启 bash（git 需要）
  mounts:
    - host_path: /Users/bowhead/my-knowledge-base
      container_path: /mnt/knowledge
      read_only: true            # 知识库只读，防止 agent 误改

    - host_path: /Users/bowhead/my-project
      container_path: /mnt/project
      read_only: false           # 项目目录可读写，agent 可以 git commit
```

配置后，agent 可以：
```bash
cd /mnt/knowledge && ls          # 浏览知识库
cd /mnt/project && git status    # 查看 git 状态
cd /mnt/project && git diff      # 查看改动
```

### 虚拟路径翻译机制

宿主机路径和沙箱虚拟路径之间有**多层防护**：

```
Agent 看到:                   宿主机实际路径:
/mnt/project/src/main.py  →  /Users/bowhead/my-project/src/main.py
/mnt/knowledge/README.md  →  /Users/bowhead/my-knowledge-base/README.md
/mnt/skills/public/...    →  /Users/bowhead/deer-flow/skills/public/...（只读）
/mnt/user-data/workspace/ →  backend/.deer-flow/users/default/threads/{tid}/user-data/workspace/
```

关键安全机制：
- **路径白名单** — agent 只能访问 `/mnt/user-data/`、`/mnt/skills/`、`/mnt/acp-workspace/` 和自定义 mount 路径。尝试访问 `/etc/passwd` 或其他宿主机路径直接 `PermissionError`
- **`..` 遍历拦截** — 任何包含 `..` 的路径都被拒绝
- **输出脱敏** — 即使宿主机路径意外泄漏到 stdout/stderr，也会被正则替换回虚拟路径，agent 永远看不到真实路径
- **只读执行** — `read_only: true` 的 mount 在沙箱层就拒绝写操作（`OSError: EROFS`）

### Git 集成方案

DeerFlow 没有内置 git 工具，git 操作全部通过 `bash` 工具执行。有三种做法：

#### 方案 1：Custom Mount 直连（最直接）

把宿主机的 Git 项目目录直接挂给 agent：

```yaml
sandbox:
  mounts:
    - host_path: /Users/bowhead/my-git-project
      container_path: /mnt/project
      read_only: false
```

Agent 在 `/mnt/project` 中直接操作 git——`git status`、`git diff`、`git add`、`git commit` 全部可用。改动直接反映在宿主机上，不需要同步。

> **前提**：本地模式需 `allow_host_bash: true`。Docker 模式下 bash 始终可用，且容器内置了 git。

#### 方案 2：Workspace 内 clone（适合远程仓库）

Agent 在 workspace 中 clone：

```bash
cd /mnt/user-data/workspace
git clone https://github.com/user/repo.git
cd repo
# ... 修改、提交 ...
```

宿主机对应路径：`backend/.deer-flow/users/default/threads/{tid}/user-data/workspace/repo/`。

#### 方案 3：宿主机预先准备

你在宿主机上提前把 repo clone 到某个线程的 workspace 目录，然后 agent 直接用：

```bash
# 你在宿主机上操作
cd backend/.deer-flow/users/default/threads/my-task/user-data/workspace/
git clone git@github.com:user/repo.git

# agent 在对话中直接用
cd /mnt/user-data/workspace/repo && git log
```

### Skills 也是文件系统的一部分

Skills 存放在 `skills/{public,custom}/`，在沙箱中挂载为 `/mnt/skills/`（只读）。你的自定义 Skills 放在 `skills/custom/` 下（gitignore），随项目一起管理：

```
skills/
├── public/           # 内置 skills（23 个，git 跟踪）
│   ├── bootstrap/
│   ├── deep-research/
│   └── ...
└── custom/           # 你的 skills（gitignore）
    ├── my-code-review/
    │   └── SKILL.md
    └── my-deploy/
        └── SKILL.md
```

如果你想把 skills 也纳入 Git 管理，直接把 `skills/custom/` 从 `.gitignore` 中移除即可。

### 推荐配置：纯本地、无 Docker、文件系统驱动的工作台

```yaml
# config.yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: true
  mounts:
    # 知识库——只读
    - host_path: /Users/bowhead/knowledge-base
      container_path: /mnt/knowledge
      read_only: true
    # 项目目录——可读写
    - host_path: /Users/bowhead/deer-flow
      container_path: /mnt/deerflow
      read_only: false
```

```python
# 在脚本中使用
from deerflow.client import DeerFlowClient

client = DeerFlowClient(
    plan_mode=True,
    subagent_enabled=True,
)

client.chat(
    "扫描 /mnt/knowledge 下的所有文档，"
    "在 /mnt/project 中创建一个索引文件 index.md，"
    "列出每个文档的路径、主题和关键标签。",
    thread_id="kb-indexing"
)
```

这个配置下：agent 看到的知识库、项目代码、Skills 全是宿主机上的真实文件。没有 Docker，没有容器边界，没有文件同步——agent 的每次读写就是一次本地文件系统调用。

### 关键源码位置

| 机制 | 文件 |
|------|------|
| Sandbox 接口（8 个操作） | `deerflow/sandbox/sandbox.py` |
| LocalSandboxProvider + PathMapping | `deerflow/sandbox/local/local_sandbox_provider.py` |
| 路径翻译（虚拟↔宿主机） | `deerflow/sandbox/local/local_sandbox.py` |
| 工具层路径校验 + 输出脱敏 | `deerflow/sandbox/tools.py` |
| bash 安全开关 | `deerflow/sandbox/security.py` |
| 自定义 mount 配置模型 | `deerflow/config/sandbox_config.py` |
| Skills 路径解析 | `deerflow/config/skills_config.py` |
| 宿主机目录布局 | `deerflow/config/paths.py` |
