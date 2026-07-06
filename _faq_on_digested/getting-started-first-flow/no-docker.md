# 补充：不依赖 Docker 可以跑吗？

> **问题：** DeerFlow 是不是必须借助 Docker？没有 Docker 就不行吗？

---

## 答案：不需要 Docker，完全可以本地运行

DeerFlow 的**默认沙箱就是本地模式**，不需要 Docker。

### 默认配置

`config.example.yaml` 的默认值（`make config` 会复制这个）：

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
```

`LocalSandboxProvider` 是纯本地实现——文件读写、目录列表、glob、grep 全部直接在宿主机上执行，不经过任何容器。`make dev` 启动的三个进程（Gateway :8001、Frontend :3000、Nginx :2026）也都是本地进程。

### 甚至可以只跑后端

```bash
cd backend && make gateway
# → 只有 Gateway API，端口 8001
# → 包含完整的 REST API + Agent 运行时
# → 没有 Nginx，没有前端
```

或者更极端的——**完全不走服务**，直接在 Python 脚本里用：

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()
reply = client.chat("用 Python 写个 hello world", thread_id="demo")
print(reply)
```

`DeerFlowClient` 是纯进程内调用，零 HTTP，零服务依赖。它和 Gateway 共享同一套 `deerflow.*` 模块。

### 不用 Docker 的代价

本地模式唯一的功能损失是 **bash 工具默认关闭**（出于安全考虑）：

```yaml
sandbox:
  allow_host_bash: false   # 默认值，bash 不可用
```

设为 `true` 即可开启，但会有安全警告——bash 命令将直接在宿主机上以你的用户身份执行。DeerFlow 明确说明这只适用于**完全可信的单用户本地工作流**。

其他工具（`read_file`、`write_file`、`ls`、`glob`、`grep`、`str_replace`）在本地模式下完全正常工作，不受影响。

### Docker vs 本地 对比

| 维度 | 本地 (LocalSandboxProvider) | Docker (AioSandboxProvider) |
|------|---------------------------|----------------------------|
| **安装** | 零额外依赖 | 需要 Docker/Apple Container |
| **bash** | 默认关闭，开启后直接跑在宿主机 | 始终开启，跑在隔离容器内 |
| **隔离** | 无—进程即用户，路径校验是 regex 级别 | 容器隔离（cgroups/namespace/network） |
| **延迟** | 近零（直接文件系统调用） | 冷启动 ~数秒，热启动复用 warm pool |
| **git/pip/npm** | 需 `allow_host_bash: true` | 容器内置，直接可用 |
| **并发** | 无限（LRU 上限 256） | 受 `replicas` 限制（默认 3） |
| **包安装** | 污染宿主机 Python 环境 | 容器内隔离环境 |

### 结论

**DeerFlow 完全支持零 Docker 运行。** 默认配置就是本地的。只要不显式把 `sandbox.use` 切换到 `AioSandboxProvider`，就不会有任何 Docker 依赖。

最小化无 Docker 上手路径：
```bash
git clone ... && cd deer-flow
make config       # 得到默认 LocalSandboxProvider 的配置
make install      # 安装依赖
make dev          # 启动（或 cd backend && make gateway 只跑后端）
```
