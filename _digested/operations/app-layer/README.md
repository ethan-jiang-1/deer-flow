---
title: "App Layer — 应用层"
description: "| 文件 | 内容 |"
type: index
---

# App Layer — 应用层

> 同步基线：**v2.2.0**（`58fc5bd5b`，上一基线 v2.1.0 = `345f08be`）。

## 文件索引

| 文件 | 内容 |
|------|------|
| [00-overview.md](00-overview.md) | 网关架构全景、lifespan 启动流程、配置热重载边界、认证系统（13 个权限 + 3 个非装饰器授权入口）；`/health` 与 `/health/ready` 探针、41 个 router / 221 条端点的挂载顺序、Projects 项目工作区、thread 归档、artifact ZIP 归档、skill 导出、运行幂等/SSE join 语义、扩展升级。**文末「🆕 v2.2.0 Gateway 变更总览」**集中记录新增的 10 组 HTTP 面、持久化写统一排空、run origin 与 SSE 响应头、知识 scope 准入、定时任务编码错误契约（33 个 UI code / 15 个 agent-only code） |
| [01-api-reference.md](01-api-reference.md) | 完整 REST API 端点文档：§1 221 条端点穷举（逐条 `file:line` + 鉴权 + 成功码）与 v2.2.0 新增端点组、§2 「领域异常 → HTTP 映射」穷举（400/401/403/404/405/409/412/413/415/416/422/429/500/501/502/503/504）、§3 四层中间件、§4 端点 × 可达状态码矩阵、§5 专题（反馈、建议、自定义 Skill CRUD、`RunCreateRequest`、MCP 合并语义） |
| [02-upload-security.md](02-upload-security.md) | 上传安全管道 — v2.2.0 语义：预留名/Windows 不兼容段拒绝、`exclusive=` 与 POSIX `O_EXCL` 无覆盖提交、staging → `os.link` 两级提交、sandbox 可写许可、copy 发布与伴生文件归属、staging 清扫；HTTP 413/400 状态归属见 01 §2.8 |
| [03-agent-package.md](03-agent-package.md) | 🆕 v2.2.0 Agent 包导入/导出 — `deerflow.custom-agent` v1 交换文档（`AgentPackage`/`AgentPackageAgent` 的 `extra="forbid"`）、可移植字段全表（13 字段 + SOUL，排除 `github`/memory/会话/凭据）、四道门（`agents:read\|write` → `agents_api.enabled` → 名字正则 → 模型存在）、owner-scoped 且 create-only（409 绝不覆盖，file/SQL store 底层兜住竞态）、`?name=` 改名、`_persist_new_agent` 经 `run_drained_write` 排空；端点与状态码矩阵见 01 §1/§4（`:44`、`:45`、`:945`、`:946`） |
