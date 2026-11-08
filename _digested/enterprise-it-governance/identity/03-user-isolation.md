---
title: "用户隔离"
description: "每个用户的数据物理隔离在不同目录，user_id 从 JWT 解析。"
topics: [governance, identity]
---

# 用户隔离

每个用户的数据物理隔离在不同目录，user_id 从 JWT 解析。

## 用户隔离

### Per-User 存储

```
backend/.deer-flow/users/{user_id}/
    threads/{thread_id}/user-data/{workspace,uploads,outputs}/
    memory.json
    agents/{agent_name}/
```

每个用户的 thread、memory、custom agent 都在自己的目录下。迁移脚本 `scripts/migrate_user_isolation.py` 支持将 legacy 数据迁到 per-user 布局。

### user_id 解析

- 有 auth：从 JWT 中提取
- No-auth 模式：`user_id = "default"`（所有人共享）

### No-Auth 模式的风险

`DEER_FLOW_AUTH_DISABLED=1` 时（`app/gateway/auth_disabled.py:30-35`；匿名请求以合成 admin `default@test.local` 运行，且 `DEER_FLOW_ENV`/`ENVIRONMENT` 为 `prod`/`production` 时即使设了也会被忽略）：

| 风险 | 影响 |
|------|------|
| **所有人共享 `default` user** | thread、memory、sandbox workspace 全部混在一起 |
| **无操作溯源** | 审计日志无法区分是哪个真人触发的操作 |
| **无权限边界** | 任何人都能看到和操作所有 thread |
| **CSRF 保护可能关闭** | 取决于 gateway 配置 |

**IT 管理建议：** 在任何非本地开发环境中，必须启用认证。No-auth 模式只适用于个人单机使用。

