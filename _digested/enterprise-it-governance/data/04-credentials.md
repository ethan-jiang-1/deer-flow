---
title: "凭证管理"
description: "凭据加密、轮换、丢失后果。"
topics: [governance, data]
---

# 凭证管理

凭据加密、轮换、丢失后果。

## 凭证管理

`deerflow/models/credential_loader.py` 自动从多个来源加载 LLM API 凭证：

| 来源 | 优先级 |
|------|--------|
| `config.yaml` 中的 `api_key: $ENV_VAR` | 环境变量 |
| `~/.claude/.credentials.json` | Claude Code CLI OAuth |
| `CLAUDE_CODE_OAUTH_TOKEN` | 环境变量 |
| `~/.codex/auth.json` | Codex CLI |

**安全考量：** 凭证以明文存在环境变量和文件中。在生产环境中，应该用 secret manager（如 Vault、AWS Secrets Manager）替代。`api_key: $VAR` 的 env var 解析在 AppConfig 是严格模式（缺了就报 ValueError），在 ExtensionsConfig 是宽松模式（缺了存空串）。

