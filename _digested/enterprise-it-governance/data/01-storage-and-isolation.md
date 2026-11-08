---
title: "数据存储与隔离"
description: "per-user 目录布局、user_id 解析、物理隔离边界。"
topics: [governance, data]
---

# 数据存储与隔离

per-user 目录布局、user_id 解析、物理隔离边界。

## 数据治理

### Per-User 数据隔离

```
backend/.deer-flow/users/{user_id}/
    memory.json                 # 用户记忆（与 agent 对话提取的事实和偏好）
    threads/{thread_id}/
        user-data/
            workspace/          # Agent 工作文件
            uploads/            # 用户上传文件
            outputs/            # Agent 输出文件
    agents/{agent_name}/        # 自定义 agent 定义
        SOUL.md
        config.yaml
```

每个用户的数据物理隔离在不同的目录下。`user_id` 从 JWT 中解析，在 no-auth 模式下所有人共享 `default` user。

#### OpenAI Assistants API 兼容接口

Gateway 实现了 OpenAI Assistants API 兼容层，外部 OpenAI SDK 可以通过该接口与 DeerFlow 交互。对于这些外部请求，用户身份验证通过 JWT 进行，创建的 thread 和 run 仍然遵循 per-user 隔离规则。

