---
title: "输出与错误脱敏"
description: "host 路径替换回虚拟路径，防止目录结构泄露。"
topics: [governance, data]
---

# 输出与错误脱敏

host 路径替换回虚拟路径，防止目录结构泄露。

### 输出脱敏

`mask_local_paths_in_output()` — 所有 sandbox 输出被正则扫描，host 路径替换回虚拟路径。覆盖：
- user-data（`/mnt/user-data/{workspace,uploads,outputs}`）
- skills（`/mnt/skills`）
- ACP workspace（代理到 `/mnt/acp-workspace/`）
- 自定义路径映射

防止 agent 输出中泄露 `~/.deer-flow/users/{user_id}/threads/{thread_id}/...` 这种目录结构。

### 错误信息脱敏

`tools.py` 中，Local 模式下 tool 异常消息中的 host 路径被替换回虚拟路径。

