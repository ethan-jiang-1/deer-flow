---
title: "内部服务认证"
description: "Gateway 与 IM channel 之间的内部调用凭据。"
topics: [governance, identity]
---

# 内部服务认证

Gateway 与 IM channel 之间的内部调用凭据。

| **内部服务** | Internal Gateway Token（`X-DeerFlow-Internal-Token`） | IM channels ↔ Gateway 等内部 HTTP 调用 |
### Internal Gateway Token
`backend/app/gateway/internal_auth.py` — Gateway 与其内部调用方（IM channels 等，同进程内通过 HTTP 回调 Gateway API）之间的内部认证（`internal_auth.py:1`）。Token 通过 header `X-DeerFlow-Internal-Token` 传递（`:13`），来自环境变量 `DEER_FLOW_INTERNAL_AUTH_TOKEN`，未设置时进程启动时随机生成（`:15`、`:19-23`）——所以**多 worker 部署必须显式设置同一个 env 值**才能共享；它不随 JWT 过期，内部服务调用因此不受会话过期影响。
