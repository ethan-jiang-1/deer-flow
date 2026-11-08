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
/mnt/user-data/workspace/ →  .deer-flow/users/{uid}/threads/{tid}/user-data/workspace/
```

关键安全机制：
- **路径白名单** — agent 只能访问 `/mnt/user-data/`、`/mnt/skills/`、`/mnt/acp-workspace/` 和自定义 mount 路径。尝试访问 `/etc/passwd` 或其他宿主机路径直接 `PermissionError`（`Only paths under ... or configured mount paths are allowed`，`deerflow/sandbox/tools.py:1077`）
- **`..` 遍历拦截** — 任何包含 `..` 的路径都被拒绝（`Access denied: path traversal detected`，`tools.py:1016`，由 `_reject_path_traversal()` 统一处理）
- **输出脱敏** — 即使宿主机路径意外泄漏到 stdout/stderr，也会被正则替换回虚拟路径，agent 永远看不到真实路径
- **只读执行** — `read_only: true` 的 mount 在工具层就拒绝写操作（`PermissionError: Write access to read-only mount is not allowed: {path}`，`tools.py:1074`）；`/mnt/skills/*`、`/mnt/acp-workspace/*` 在本地沙箱里也只在 `read_only` 读取场景放行（`validate_local_tool_path()` 的 docstring，`tools.py:1019`）

> 🔄 同步 #8（v2.2.0）：原文写只读 mount 报 `OSError: EROFS`——**不准确**，本地沙箱的拦截发生在 `validate_local_tool_path()`（`deerflow/sandbox/tools.py:1019`）而非底层文件系统，抛的是 `PermissionError`，且信息里直接带上被拒路径。另外「虚拟路径↔宿主机路径」的翻译现在是**前缀精确匹配**（`deerflow/sandbox/local/local_sandbox.py:557` 的 `_find_path_mapping()`：`path == container_path or path.startswith(container_path + "/")`），所以 `/mnt/knowledge2` 不会误命中 `/mnt/knowledge` 的挂载。

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

宿主机对应路径：`{DEER_FLOW_HOME}/users/{uid}/threads/{tid}/user-data/workspace/repo/`（`deerflow/config/paths.py:365-371` 的 `sandbox_work_dir()`；`make dev` 下 `DEER_FLOW_HOME` 是 `backend/.deer-flow`，`backend/Makefile:1`）。

#### 方案 3：宿主机预先准备

你在宿主机上提前把 repo clone 到某个线程的 workspace 目录，然后 agent 直接用：

```bash
# 你在宿主机上操作
cd backend/.deer-flow/users/default/threads/my-task/user-data/workspace/   # make dev 的默认 DEER_FLOW_HOME
git clone git@github.com:user/repo.git

# agent 在对话中直接用
cd /mnt/user-data/workspace/repo && git log
```

### Skills 也是文件系统的一部分

Skills 存放在 `skills/{public,custom}/`，在沙箱中挂载为 `/mnt/skills/`（只读）。你的自定义 Skills 放在 `skills/custom/` 下（gitignore），随项目一起管理：

```
skills/
├── public/           # 内置 skills（23 个，git 跟踪）
│   ├── claude-to-deerflow/
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
| Sandbox 抽象基类 | `deerflow/sandbox/sandbox.py` |
| 本地路径映射表 | `deerflow/sandbox/local/local_sandbox_provider.py:122`（`_setup_path_mappings`）、`:334`（`_build_thread_path_mappings`） |
| LocalSandboxProvider + PathMapping | `deerflow/sandbox/local/local_sandbox_provider.py` |
| 路径翻译（虚拟↔宿主机） | `deerflow/sandbox/local/local_sandbox.py` |
| 工具层路径校验 + 输出脱敏 | `deerflow/sandbox/tools.py` |
| bash 安全开关 | `deerflow/sandbox/security.py` |
| 自定义 mount 配置模型 | `deerflow/config/sandbox_config.py` |
| Skills 路径解析 | `deerflow/config/skills_config.py` |
| 宿主机目录布局 | `deerflow/config/paths.py` |

> 🔄 同步 #6（v2.1.0-rc0）：核心结论不变，to 点补充——(1) 仓库 `skills/public/` 现为 23 个内置 skill；(2) 除项目级 `skills/custom/` 外，还支持 per-user 自定义 skill（存于 `.deer-flow/users/{uid}/` 下的 skills 目录，沙箱内同样挂到 `/mnt/skills/custom/`），custom mounts 机制本身未变。

> 🔄 同步 #8（v2.2.0）：本页四处订正（均已落实到上文）——① 只读 mount 的报错是 `PermissionError` 而非 `OSError: EROFS`（`deerflow/sandbox/tools.py:1074`）；② mount 前缀翻译是**精确前缀匹配**（`local_sandbox.py:557`），不是简单 `startswith`；③ 上表各处路径已去掉硬编码的 `backend/.deer-flow`，改为 `{DEER_FLOW_HOME}`——默认值是 `{project_root}/.deer-flow`（`deerflow/config/runtime_paths.py:22-27`），`make dev` 才钉在 `backend/.deer-flow`（`backend/Makefile:1`）；④ `skills/` 示例里的技能名换成了当前真实存在的（`claude-to-deerflow`），`skills/public/` 仍为 23 个内置 skill。custom mounts 的配置模型（`VolumeMountConfig`，`deerflow/config/sandbox_config.py:162`：`host_path` / `container_path` / `read_only`）未变。
