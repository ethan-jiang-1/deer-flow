---
title: "GitHub 集成"
description: "GitHub App webhook 接收、per-agent binding 配置、事件分发、安装 token 认证、gh CLI 集成。"
topics: [github, webhook, integration, agent-binding]
---

# GitHub 集成

DeerFlow 通过 GitHub App webhook 接收事件，根据 per-agent binding 配置分发给对应 agent，agent 通过 `gh` CLI（自动注入安装 token）与 GitHub 交互。

## 快速设置

```bash
# 1. 环境变量
export GITHUB_WEBHOOK_SECRET=<your-secret>     # HMAC 签名验证（未设则路由不挂载）
export GITHUB_APP_ID=123456                     # GitHub App ID
export GITHUB_APP_PRIVATE_KEY_PATH=/path/to/key.pem

# 2. config.yaml
channels:
  github:
    enabled: true
    default_mention_login: deerflow-bot

# 3. 创建 agent 绑定（见下方）
# 4. 重启 Gateway（凭据在启动时加载）
```

## Agent-Level 配置

每个自定义 agent 的 `config.yaml` 可声明 `github:` 块：

```yaml
# .deer-flow/users/default/agents/coder/config.yaml
name: coder
github:
  installation_id: 123456        # GitHub App installation ID
  bot_login: coder-bot           # Bot 登录名（不含 [bot]）
  recursion_limit: 250           # 覆盖默认值
  bindings:
    - repo: "owner/repo-name"
      triggers:
        pull_request:
          actions: ["opened"]    # 仅新建 PR（None = 任意 action）
        issue_comment:
          require_mention: true  # 需 @-mention 触发
        pull_request_review:
          {}
        issues:
          actions: ["opened", "reopened"]
```

## 触发规则

| 事件 | 默认 | 说明 |
|------|------|------|
| `pull_request` | `actions: ["opened"]` | 仅新建 PR |
| `issue_comment` | `require_mention: true` | 需 @-mention |
| `pull_request_review_comment` | `require_mention: true` | 需 @-mention |
| `issues` | 无默认 | 任意 action |
| `pull_request_review` | 无默认 | 任意 action |

Mention 优先级：`trigger.mention_login` > `github.bot_login` > `channels.github.default_mention_login` > `agent.name`。

## 事件→Agent 流程

```
GitHub webhook → POST /api/webhooks/github
  → HMAC 验证 (GITHUB_WEBHOOK_SECRET)
  → 提取 (repo, event_type)
  → Registry 查找匹配 agent
  → Per-agent 过滤: self-event gate, action, mention
  → 生成 prompt → InboundMessage → ChannelManager
  → create_run(agent_name, prompt, thread_id)
```

Registry 扫描 `.deer-flow/users/{uid}/agents/{name}/config.yaml`，按 `(repo, event)` 索引。mtime 缓存。

## 安装 Token 认证

两步认证流：
1. App JWT（RS256，TTL 9 分钟）→ 安装 token API
2. 安装 token（TTL 1 小时）→ 注入 `run_context["github_token"]`

Token 在 sandbox 中自动暴露为 `GH_TOKEN` / `GITHUB_TOKEN`，agent 直接用 `gh` CLI：
```bash
gh pr comment $PR_NUMBER --body "Review complete"
gh issue edit $ISSUE_NUMBER --title "Fixed"
```

## 线程隔离

每个 `(repo, PR#, agent_name)` 获得独立的 LangGraph 线程（UUID5 hash）。不同 agent 在同一 PR 上永远不共享状态。

## 出站行为

GitHub channel 是 **log-only**——不自动回帖。Agent 通过 `gh` CLI 主动发帖。这避免了多个 agent 绑定同一事件时重复回复。

## 安全

- Webhook HMAC-SHA256 签名验证（`GITHUB_WEBHOOK_SECRET`）
- 路由未挂载时返回 404（fail-closed 默认）
- 路由免 CSRF/auth（GitHub 不发送 cookie）
- 开发模式：`DEER_FLOW_ALLOW_UNVERIFIED_GITHUB_WEBHOOKS=1`
- `_is_self_event` gate 防止 agent 自己触发循环

## 调试

```bash
# 检查 webhook payload
curl -X POST localhost:8001/api/webhooks/github \
  -H "X-GitHub-Event: ping" -H "X-Hub-Signature-256: sha256=..." \
  -d '{"zen": "test"}'

# 查看 agent binding
cat .deer-flow/users/default/agents/*/config.yaml | grep -A10 "github:"

# 检查注册表日志
grep "github.*agent" gateway.log
```

源码：`app/gateway/github/`，`app/gateway/routers/github_webhooks.py`，`app/channels/github.py`

测试：10 个测试文件覆盖 HMAC、dispatch、registry、trigger、auth、token plumbing。
