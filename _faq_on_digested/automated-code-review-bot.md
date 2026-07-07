---
title: "Recipe: 自动化代码审查 Bot"
description: "端到端构建指南：GitHub webhook → Agent 审查 → 跑测试 → 发评论 → 审批 → Slack 通知。"
---

# Recipe: 自动化代码审查 Bot

六步搭一个完整的 PR 自动化审查系统。

## 架构

```
GitHub PR opened → webhook → DeerFlow agent
  ├─ read_diff (git diff)
  ├─ run_tests (bash: make test)
  ├─ review_code (SOUL.md 驱动的审查)
  ├─ post_comment (gh pr comment)
  ├─ approve_if_pass (gh pr review --approve)
  └─ notify_slack (curl webhook)
```

## Step 1: GitHub App + 环境变量

创建 GitHub App → 安装到仓库 → 设置 webhook URL 为 `https://<host>/api/webhooks/github`

```bash
export GITHUB_WEBHOOK_SECRET=<secret>
export GITHUB_APP_ID=<id>
export GITHUB_APP_PRIVATE_KEY_PATH=/path/to/key.pem
```

## Step 2: 创建 Agent

```bash
mkdir -p .deer-flow/users/default/agents/code-reviewer
```

`.deer-flow/users/default/agents/code-reviewer/config.yaml`:
```yaml
name: code-reviewer
model: claude-sonnet-4
github:
  installation_id: 123456
  bot_login: reviewer-bot
  bindings:
    - repo: "owner/repo-name"
      triggers:
        pull_request:
          actions: [opened, synchronize]
```

`.deer-flow/users/default/agents/code-reviewer/SOUL.md`:
```markdown
# Code Reviewer

## Workflow
1. Run `gh pr diff $PR_NUMBER` to get code changes
2. Run `make test` to execute test suite
3. Review each changed file for correctness, security, performance
4. Post review comment via `gh pr comment $PR_NUMBER --body "..."` 
5. If all tests pass: `gh pr review $PR_NUMBER --approve`
6. Post Slack notification: `curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"Review complete: #$PR_NUMBER"}'`

## Review Format
- 🔴 Must Fix / 🟡 Suggested / 🟢 Reference
- Categorize: correctness, security, performance, readability
```

## Step 3: 配置 sub-agent（可选）

```yaml
subagents:
  custom_agents:
    test-runner:
      description: "Runs the project test suite"
      tools: [bash, read_file]
      system_prompt: "Run make test or pytest. Report pass/fail and any failures."
```

## Step 4: Slack 通知

```bash
# 创建 Slack Incoming Webhook
# https://my.slack.com/services/new/incoming-webhook/
# 将 URL 存为环境变量或 skill secret
```

Agent 在 SOUL.md 最后执行：
```bash
curl -X POST $SLACK_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"text":"PR #$PR_NUMBER review complete: $TESTS_PASSED tests, $ISSUES_FOUND issues found"}'
```

## Step 5: 开启 channel

```yaml
# config.yaml
channels:
  github:
    enabled: true
    default_mention_login: reviewer-bot
```

## Step 6: 监控

```bash
# 查看审查统计
curl http://localhost:8001/api/console/stats
# → {total_runs, active_runs, failed_runs, total_tokens}

# 查看具体 run
curl "http://localhost:8001/api/console/runs?limit=20"
```

## 关联文档

- 完整 GitHub 配置: `_digest/operations/github-integration.md`
- SOUL.md 编写: `_digest/concepts/lead-agent/02-soul-md-guide.md`
- Sub-agent 配置: `_digest/concepts/subagent/dual-threadpool-and-lifecycle.md`
- 备份监控: `_digest/operations/backup-and-monitoring.md`
