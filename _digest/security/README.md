# 安全与信任边界

一段用户 prompt 到 agent 执行 `rm -rf /` — 中间有多少层防护？

## 阅读顺序

| 文件 | 内容 |
|------|------|
| **00-overview.md** | 全景：纵深防御同心圆图、三条认证路径图、隔离对比表、已知缺陷 |
| **01-auth.md** | 认证授权：JWT + CSRF + Internal Token + 登录限流 + 权限模型 |
| **02-sandbox-isolation.md** | 沙箱隔离：三档对比(13维)、allow_host_bash、6层路径防穿越 |
| **03-guardrail.md** | Guardrail + 审计：可插拔授权、高危命令拦截、输出安全 |
| **04-trust-boundary.md** | 端到端信任链：14 层防护在代码中的位置和执行流 |

## 关键问题

- 三种沙箱差多少？→ `02-sandbox-isolation.md` 13 维对比表
- `allow_host_bash: false` 到底防了什么？→ `02-sandbox-isolation.md` LocalSandbox 节
- Guardrail 和 SandboxAudit 有什么区别？→ `03-guardrail.md`
- 从请求到执行经过多少层检查？→ `04-trust-boundary.md` 链路图
- 最大的安全短板是什么？→ `00-overview.md` 已知缺陷表
