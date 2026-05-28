# 安全与信任边界

一段用户 prompt 到 agent 执行 `rm -rf /` — 中间有多少层防护？

## 阅读顺序

1. **Auth** — JWT/OAuth 用户认证、CSRF 防跨站、internal gateway token 组件间信任
2. **Sandbox Isolation** — Local（无隔离）→ Docker（容器隔离）→ K3s（Pod 隔离），安全边界逐级提升
3. **Guardrail** — Tool 执行前授权检查，可插拔 provider
4. **Trust Boundary** — 端到端梳理：user → gateway → agent → tool → sandbox 的信任链

## 关键问题

- `allow_host_bash: false` 到底防了什么，怎么绕过去？
- Docker-out-of-Docker 模式下，Gateway 容器挂宿主 docker.sock 的风险面多大？
- Guardrail 在 middleware 链的哪个位置？拦截的是 tool_call 还是 tool 执行结果？
- CSRF + internal auth 是怎么保证 IM channel worker 不被伪造请求攻击的？
