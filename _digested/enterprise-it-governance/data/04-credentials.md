---
title: "凭证管理"
description: '三类凭据、两种存放形态：env/config 里是明文，落库的走 Fernet 加密（DEER_FLOW_CREDENTIALS_KEY）。密钥轮转与丢失的实际后果。'
topics: [governance, data, credentials]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 凭证管理

「凭据存哪、怎么加密、丢了怎样」三个问题有三个不同的答案，
混在一起谈是评审时最常见的错误。

## 1. 三类凭据，两种形态

| 类别 | 例子 | 存放形态 |
|---|---|---|
| **LLM API 凭据** | `api_key: $OPENAI_API_KEY` | env/config → **明文** |
| **CLI 凭据** | Claude Code OAuth、Codex `auth.json` | 本地文件 → **明文**（由 CLI 自己管理） |
| **通道/集成凭据** | IM channel token、MCP OAuth | 关系库 → **Fernet 加密** |

## 2. LLM 凭据的加载链

`packages/harness/deerflow/models/credential_loader.py:1-9` 的模块 docstring 列出策略：

> Implements two credential strategies:
>   1. Claude Code OAuth token from explicit env vars or an exported credentials file
>      - Supports `$CLAUDE_CODE_OAUTH_TOKEN`, `$CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`,
>        and `$ANTHROPIC_AUTH_TOKEN`
>   2. Codex CLI token from `~/.codex/auth.json`

| 源 | 位置 | 证据 |
|---|---|---|
| Claude Code 凭据文件 | `~/.claude/.credentials.json` | `credential_loader.py:143` |
| Claude OAuth env | `CLAUDE_CODE_OAUTH_TOKEN` 等三个 | `credential_loader.py:7` |
| Codex | `~/.codex/auth.json` | `credential_loader.py:9` |

### 2.1 文件描述符传递

`credential_loader.py:101` 的 `_read_secret_from_file_descriptor` 支持
从 **fd** 读密钥（`$CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`）。

**这是比 env 更强的形态**：`/proc/<pid>/environ` 可被同用户进程读取，
而 fd 不会出现在进程环境里。容器编排（Docker/K8s secrets 挂成 fd）倾向这种方式。

## 3. 落库凭据的加密

这一层原文没写，但是企业最关心的部分。

`packages/harness/deerflow/config/credentials_key.py:1-19` 的模块 docstring 是权威说明：

| 项 | 行为 |
|---|---|
| 密钥来源 | 环境变量优先 `DEER_FLOW_CREDENTIALS_KEY`（逗号分隔的 Fernet key，32 随机字节的 urlsafe base64）；未设时走下行文件回退 |
| 加密方式 | 第一个 key 加密，**所有** key 都能解密 |
| 轮转步骤 | "prepend a new key, re-encrypt with `CredentialsCipher.rotate_text`, then drop the old key" |
| 与 JWT 的关系 | **从不**从 `AUTH_JWT_SECRET` 或其他 secret 派生 |
| 未设 env 时 | 单实例会生成 `{base_dir}/.credentials_key`（独占创建，`0600`），同一 runtime home 的 uvicorn worker 收敛到同一 key；声明的 multi_instance + 凭据消费者则拒绝启动（`deps.py:333-377`） |
| 密文格式 | `fernet:v2:<Fernet token>`；`fernet:v1:` 与裸 token 是旧格式，仍可解密 |
| **密钥丢失** | 用它加密的所有值不可读，消费方当作「缺失」处理 —— 有回退，恢复路径**未闭合** |

### 3.1 多实例的强制检查

`credentials_key.py:10-13`：

> Instances that do not share a runtime home cannot rely on that file; the Gateway
> **refuses** a declared multi-instance deployment whose enabled features store
> credentials without the variable (`app.gateway.deps._enforce_credentials_key`).

**这是硬闸门**：声明了 `deployment.multi_instance: true`，且启用了需要存凭据的功能
（IM channel 等），但没设 `DEER_FLOW_CREDENTIALS_KEY` → **拒绝启动**。

理由很直接：各 Pod 各自的 `.credentials_key` 互不相同，
A Pod 加密的值 B Pod 解不开。

### 3.2 轮转的正确顺序

| 步骤 | 动作 | 出错后果 |
|---|---|---|
| 1 | 把新 key **前置**到 env 列表 | 无影响（旧 key 仍在） |
| 2 | 调 `rotate_text` 重新加密旧值 | 部分已迁移 |
| 3 | 移除旧 key | **若第 2 步没做完，剩余旧值不可读** |

`credentials_key.py:15-16` 的警告要当真：

> Losing the key makes every value encrypted with it unreadable; consumers treat
> such values as missing rather than failing.

「当作缺失」意味着**功能不可用，但进程不一定退出**——消费方会记 ERROR 日志
（`runtime_config_store.py:372-374`、`:382`；`oauth_store.py:169-173`），
比硬失败更难排查，但不是完全静默。

## 4. 明文的那一部分

env/config 与 CLI 文件里的凭据是**明文**：

| 风险 | 说明 |
|---|---|
| `printenv` / 崩溃转储 | env 值可被同用户读取 |
| `config.yaml` 权限 | 文件权限决定谁能看 |
| CLI 凭据文件 | `~/.claude/.credentials.json`、`~/.codex/auth.json` 由对应 CLI 管理权限 |

**这是设计上的取舍**：env 注入是容器编排最通用的凭据传递方式，
代价是进程可见。要更强只能用 fd 或外部 secret manager。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| Secret manager 集成 | **无** | 无 Vault/AWS SM 原生支持；只能由编排层注入 env |
| 落库凭据的自动轮转 | **部分** | 有 Fernet 多 key 与 `rotate_text`；**无**定时任务触发轮转 |
| 密钥丢失的恢复 | **无** | 无恢复路径，只能重新录入所有凭据 |
| 凭据使用审计 | **无** | 无「哪个凭据在何时被用于哪次调用」的事件 |
| env 凭据的启动校验 | **部分** | `AppConfig` 的 `$VAR` 解析是严格模式（缺失即 `ValueError`）；`ExtensionsConfig` 是宽松模式（缺失存空串） |
| 前端可见的凭据状态 | **部分** | 有「已配置/未配置」状态，但不显示指纹或末次使用时间 |

**第 5 条的两个模式差异值得注意**：同一个 `$VAR` 语法在 AppConfig 里缺了就启动失败，
在 ExtensionsConfig 里缺了变成空串。所以「我把 key 删了」在两个配置里表现不同。

## 6. 与其他章节的关系

- 存储与隔离：[01-storage-and-isolation.md](01-storage-and-isolation.md)
- 多实例闸门：[../cost/04-multi-instance.md](../cost/04-multi-instance.md) §2
- PAT（另一种凭据，只存摘要）：[../identity/08-pat.md](../identity/08-pat.md)
- 内部服务 token：[../identity/02-internal-token.md](../identity/02-internal-token.md)
