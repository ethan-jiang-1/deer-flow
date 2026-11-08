---
title: "企业安全评审控制清单：85 项逐条对照"
description: '把企业 Agent 安全评审会问的控制项拆成 85 条，每条给 DeerFlow 的落点、默认状态、证据与必须由企业补的部分。'
topics: [security, enterprise, checklist, audit, agent-identity, dlp]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 企业安全评审控制清单：85 项逐条对照

> **用途**：这是一份可以直接贴进 RFP / 安全问卷 / 上线评审表的控制清单。85 项里 ✅ 13、🟡 38、❌ 34（按 v2.2.0 默认配置）；每行只回答三件事：**DeerFlow 有没有、默认开不开、证据在哪**；最后一列写企业必须自己补的部分。
>
> **状态口径**：✅ = 有且可执行（可能仍需配置）；🟡 = 有原语，但不完整、默认关或只覆盖部分路径；❌ = 没有，或只有文档没有实现。
>
> **边界**：本清单按 v2.2.0 **默认配置**评估；开启 `authorization`、`guardrails`、`pii_redaction`、`network.mode` 等配置会改变部分状态，备注列已注明。它不是合规结论，也不替代渗透测试与审计。

---

## A. 身份与接入（9）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| A1 | 企业 IdP 对接（OIDC/SSO） | 🟡 | `app/gateway/auth/session_cookie.py`、`routers/auth.py`；支持通用 OIDC（含 Keycloak） | 无 SAML；如 IdP 只支持 SAML，需前置代理或换 IdP |
| A2 | 多因素认证（MFA/WebAuthn） | ❌ | 代码内无 TOTP/WebAuthn/2FA | 由 IdP 强制 MFA；或前置认证网关 |
| A3 | SCIM 自动开通/停用 | ❌ | 无 SCIM 端点；账号靠注册/API | 用 IdP + 脚本/API 做生命周期；离职停用要另行编排 |
| A4 | 会话撤销与设备管理 | 🟡 | `jwt.py` 的 `token_version` 在改密时递增；JWT 默认 7 天 | 无 per-device 撤销、无会话列表；缩短 TTL + 外部会话管理 |
| A5 | CSRF 防护 | ✅ | `csrf_middleware.py` double-submit + 常量时间比较 + 登录 Origin 校验 | 反代要正确透传 Cookie/Origin |
| A6 | 登录限流 / 锁定 | ✅ | 默认 `throttle_storage: auto`，sqlite/postgres 下写共享表；参数可配 | `memory` 后端会退化为 per-worker；多副本要确认 DB |
| A7 | 注册策略 | 🟡 | `auth.local.allow_registration` 默认 **true** | 生产必须设 false；否则任何人可自助注册 |
| A8 | PAT 作用域与路由白名单 | ✅ | `auth/pat.py`：SHA-256 digest、scope ∩ effective permissions、默认拒绝路由；PAT 永不带 admin | 仍需按最小权限签发；PAT 撤销不回溯已建立的 run |
| A9 | API 限流 / 防滥用 | 🟡 | 登录限流 + LLM 并发上限 + subagent 并发；无全局 per-user API 限流 | Nginx/网关加 `limit_req`；按用户/租户配额 |

## B. Agent 身份与权限（6）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| B1 | Agent 独立身份（NHI） | ❌ | Agent 在用户上下文里跑；`get_effective_user_id()` 是唯一身份 | 用「专用服务账号 + 受限 PAT」做近似，但不是真 NHI |
| B2 | 每 Agent 最小权限 | ❌ | RBAC 按 user 解析；没有 per-agent role/scope | 给不同 agent 配不同服务账号；或自定义 AuthorizationProvider |
| B3 | 委托 / on-behalf-of 链 | 🟡 | 用户身份随 run 传播；无 token exchange、无委托链签名 | 审计上无法区分 user 与 agent 的主动行为 |
| B4 | Agent 级撤销 | ❌ | 只能停用户、停 thread、cancel run | 需要平台层「禁用某个 agent」的开关 |
| B5 | Subagent 身份 | ❌ | `subagents/batch_acceptance.py` 继承父任务 `user_id` 与授权属性 | 审计只能看到父 run；无法按 subagent 追责 |
| B6 | 后台任务身份 | 🟡 | `internal_auth.py` 合成 `internal` 角色，或借 owner 身份 | 没有「后台任务自身的最小权限」；owner 头等于 owner 权限 |

## C. 授权与工具（9）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| C1 | 路由级 RBAC | 🟡 | `authz.py` 13 个 `resource:action`；`authorization.enabled` 默认 **false** → 全放行 | 生产必须启用并配角色；默认配置等于没有 |
| C2 | 工具 allowlist / denylist | 🟡 | `guardrails/builtin.py`；`guardrails.enabled` 默认 **false** | 启用后仍要覆盖所有危险工具；`tools` 收窄会漏 |
| C3 | 风险概率门 | 🟡 | `guardrails/typesafe.py`、`openai_decisions.py`；fail-closed、缓存、状态预检 | 参数 JSON 会出网（不脱敏）；需与数据保护对齐 |
| C4 | 插件 action 授权 | 🟡 | `authz/plugin_authz.py`、`routers/plugins.py`；读 body 前鉴权 | 仅 `authorization.enabled=true` 时生效；`plugin_page` 尚未 gate |
| C5 | MCP 作用域与归属 | 🟡 | `mcp_scope.py`、`mcp/personal_access.py`；个人 MCP 需管理员权限（公共网络） | 部署级 MCP 仍按 operator 信任；server 本身不被审计 |
| C6 | 沙箱执行授权 | 🟡 | `authz/sandbox_authz.py`；`sandbox:execute` 检查，复用前重查 | 仅 authorization 开启时生效 |
| C7 | 技能可见性授权 | 🟡 | `authz/skill_filter.py`；Layer 1 过滤 + 线程级投影 | provider 要自定义；默认无按角色技能策略 |
| C8 | 默认拒绝 | ❌ | authorization 关闭 → 13 权限全放行；guardrails 关闭 → 工具全放行 | 生产基线必须显式开启；当前无官方 hardened preset |
| C9 | per-thread / per-user 策略 | 🟡 | GuardrailRequest 带 `thread_id/user_id/user_role`；无开箱配置项 | 自定义 provider 可做；不要期待配置开关 |

## D. 人工审批（4）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| D1 | 高危工具强制审批 | ❌ | 核心无「等人批准才能执行」状态机；`ask_clarification` 由模型自主触发 | 外接审批流；自定义 Guardrail 拒绝后走工单，但结果无法回灌 |
| D2 | 风险分级审批 | ❌ | 无按工具/参数/金额/数据等级路由的审批策略 | 平台层实现；或扩展 workflow 的 checkpoint |
| D3 | 审批留痕 | ❌ | clarification 不产生结构化审批事件 | 审批记录必须落到外部系统，并与 run_id 关联 |
| D4 | 超时/拒绝语义 | 🟡 | 沙箱出网域名审批有 TTL（30–3600s）和 deny/prompt | 仅域名；不适用于文件写入/命令执行 |

## E. 沙箱与执行（10）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| E1 | Local 模式隔离 | ❌ | `local_sandbox.py` 直接 `subprocess.run()`；`allow_host_bash` 默认 false | 只适合单用户开发；不可用于不可信用户 |
| E2 | Docker cap-drop / no-new-privileges | ✅ | `aio_sandbox/local_backend.py:1978-1995`：`--cap-drop=ALL` + 5 caps + `no-new-privileges` | 仍要限制镜像来源与挂载 |
| E3 | Docker seccomp | 🟡 | 默认 `seccomp=unconfined`；可用 `DEER_FLOW_SANDBOX_SECCOMP_PROFILE` 或 `..._UNCONFINED=0` 收紧 | 默认是弱配置；企业应提供 Chromium 兼容 profile |
| E4 | 容器非 root | 🟡 | 默认不传 `--user`；`DEER_FLOW_SANDBOX_CONTAINER_USER` 可配 | 镜像用户未固定；必须显式指定并验证挂载权限 |
| E5 | K8s Pod 安全上下文 | 🟡 | `privileged: false`，但 `allowPrivilegeEscalation: true`；无 `runAsNonRoot`/`readOnlyRootFilesystem` | 用 Pod Security Admission / OPA 强制 |
| E6 | K8s NetworkPolicy | ❌ | Provisioner 创建的 sandbox Pod 无 NetworkPolicy | 集群层自建默认拒绝 + 白名单 |
| E7 | 资源限额 | 🟡 | Docker 2 CPU/2G/pids 512；K8s requests/limits；Local 无 cgroup；磁盘无配额 | 生产要加 PVC/磁盘配额与 namespace quota |
| E8 | 路径防护 | ✅ | 6 层：`..` 拒绝、虚拟路径族、read_only、resolved containment、sandbox containment、symlink 过滤 | 关注 TOCTOU 与并发写；已有细粒度锁 |
| E9 | Docker socket / DooD 暴露 | 🟡 | 默认 compose 不挂；`docker-compose.dood.yaml` 挂 `/var/run/docker.sock`，等于 host root | 生产用 provisioner/rootless/socket proxy；不要给插件 |
| E10 | Provisioner RBAC 范围 | 🟡 | 可 get/list/watch/create/delete 命名空间内所有 Pod/Service；不能按 label 限权 | 专用 namespace + OPA/Kyverno；最小权限 |

## F. 数据保护（10）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| F1 | 密钥/凭据脱敏 | ✅ | `secret_context.py`：trace/checkpoint/API/journal 剥离；`env_policy` 洗 sandbox env | 仍要防止业务代码把密钥写进文件 |
| F2 | PII 脱敏 | 🟡 | `pii_redaction` 默认 **false**；5 类；用户消息 + 远程工具结果 | 本地工具输出/assistant 消息不覆盖；错误时 fail-open |
| F3 | 数据分类 / DLP | ❌ | 无标签、无策略引擎、无字段级 masking | 接企业 DLP 网关；在 prompt 前做分类脱敏 |
| F4 | 输出敏感信息扫描 | ❌ | 无主动输出 DLP；只有 provider `content_filter` 被动处理 | 外挂输出审核；或自定义 middleware |
| F5 | 记忆保留 / 导出 | 🟡 | per-user memory；无 TTL、无导出端点；项目回收站 30 天 | 企业要定义保留期与删除流程 |
| F6 | 静态加密 | 🟡 | MCP OAuth token 可加密（需 `DEER_FLOW_CREDENTIALS_KEY`）；IM 凭据 cipher 尚未接线 | DB/磁盘加密、KMS、密钥轮换由部署方负责 |
| F7 | 数据驻留 | 🟡 | 可自托管；模型/MCP/web 出口决定数据去向 | 选境内模型/私网 MCP；用 egress allowlist |
| F8 | 上传恶意文件扫描 | ❌ | 有大小/类型/配额；无 AV/沙箱 detonation | 上传网关加 AV；不要把上传直接喂给模型 |
| F9 | 数据保留 / 删除 / 导出 | 🟡 | thread 可删；memory/uploads 无 TTL；无导出端点；事件删除会把 seal 置 partial | 定义保留期/DSR 流程；外接导出与法务保留 |
| F10 | 日志/trace 中的 prompt/PII | 🟡 | secrets redaction 覆盖 trace/checkpoint；PII 脱敏是 model-bound，日志/trace 不保证 | 关闭或脱敏 trace；日志接入前做 DLP |

## G. 内容信任 / 提示注入（8）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| G1 | 输入标签转义 | ✅ | `input_sanitization_middleware.py`；覆盖整个会话，不只最后一轮 | 挡结构注入，不挡语义说服 |
| G2 | 工具结果中性化 | ✅ | `tool_result_sanitization_middleware.py`；首方网络工具 + MCP 结果 | 本地工具输出按信任处理，不中性化 |
| G3 | 输出 HTML 转义 | ✅ | memory/SOUL/subagent/摘要/web capture 等进入 prompt 的 untrusted 文本 | 不是输出内容审核 |
| G4 | 语义注入检测 | ❌ | 无语义分类器；无 prompt-injection 模型 | 外挂检测；或用风险门对 tool_call 做二次判定 |
| G5 | MCP 工具描述信任 | ❌ | `mcp/tools.py` 只校验工具名；`tool.description` 原样进 prompt | 只接可信 MCP；对描述做审核/固定版本 |
| G6 | 记忆投毒防护 | 🟡 | `memory.prescreen`（TypeSafe 可选）；memory facts 转义标签 | prescreen 默认未启用；语义投毒仍可写入 |
| G7 | RAG / 知识库 ACL | 🟡 | `knowledge_scope.py`、检索期 scope 过滤 | 向量库 ACL 是否继承源权限取决于接入；跨租户未验证 |
| G8 | 内容安全 / 审核 | ❌ | 无内置内容审核；`SafetyFinishReasonMiddleware` 只处理 provider 的 content_filter | 外挂审核服务；输入/输出双通道 |

## H. 审计与响应（7）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| H1 | Run 生命周期事件 | ✅ | `runtime/journal.py`；run.start/end/terminal + middleware 事件 | 需要 DB/外部存储；内存模式重启即丢 |
| H2 | Guardrail 决策 | 🟡 | `guardrails/middleware.py` 落 `middleware:guardrail`；**只记 deny / fail-open，不记正常 allow** | 要证明「被允许」需自己做 allow 事件 |
| H3 | Sandbox 命令审计 | 🟡 | `sandbox_audit_middleware.py` 结构化 JSON；**只写 gateway.log，不落库** | 日志采集到 SIEM；补文件写入/网络事件 |
| H4 | 防篡改 / 不可否认 | ❌ | 事件有 `content_sha256`，但无链/HMAC；有库写权限者可改；删除会把 seal 置 partial | WORM 存储、外部时间戳、签名由企业补 |
| H5 | SIEM / eDiscovery 导出 | ❌ | 无 OTLP/SIEM 导出、无按用户/agent 的证据包 | 采集日志 + RunEvent；自建导出 |
| H6 | 行为异常检测 | ❌ | 有 loop/tool progress/token budget，无 UEBA/异常行为模型 | SIEM/UEBA 离线规则；关注工具序列异常 |
| H7 | Kill switch | 🟡 | cancel run/thread；无全局「停掉所有 agent」 | 网关层禁用路由/停 worker；feature flag |

## I. 供应链与扩展（10）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| I1 | Skill 静态扫描 | 🟡 | `skills/skillscan/`：网络 sink、env 读取、dataflow；CRITICAL block | 启发式；混淆代码可绕过；不能当证明 |
| I2 | Skill 发布审查 | ✅ | `skills/public/skill-reviewer/` + CI `scripts/review_changed_public_skills.py` | 只覆盖 public skill；custom skill 仍要自审 |
| I3 | 插件逐项授权 | ✅ | `extensions/host_access.py`、`authz/plugin_targets.py`；grant 重启绑定、无通配 | 插件代码仍与 Gateway 同进程 |
| I4 | 插件沙箱 | ❌ | 插件在 Gateway 进程内执行，拥有 Gateway 权限 | 只装可信插件；高敏场景用独立 Gateway/租户 |
| I5 | MCP stdio 启动白名单 | ✅ | `routers/mcp.py::_validate_mcp_update_request`：`npx/uvx` allowlist、拒绝 exec args/env | 这是 defense-in-depth，不是信任边界；admin ≈ 代码执行 |
| I6 | MCP server 审核 | 🟡 | 部署级 server 由 operator 配置；HTTP/SSE 做 header/凭据校验 | 不审计 server 本身；版本固定与来源审核由企业做 |
| I7 | SBOM / 签名 / SLSA | ❌ | 仓库内未见相关流水线 | 自建 SBOM、cosign、私有 registry、依赖扫描 |
| I8 | 依赖漏洞扫描 | ❌ | CI 无 Dependabot/Trivy/pip-audit 类流水线 | 接入 SCA；把 `uv.lock`/`pnpm-lock` 纳入扫描 |
| I9 | 模型供应链 / 行为漂移 | 🟡 | `models:` 配置、model name allowlist；无模型卡/版本固定/升级 eval | pin 模型版本；升级前跑 eval；要 provider DPA/变更通知 |
| I10 | 安全测试 / 红队报告 | ❌ | 有测试与 CVE 修复；无公开渗透测试/红队报告 | 上线前自做红队；要求第三方报告 |

## J. 多租户、运营与合规（12）

| # | 控制项 | 状态 | DeerFlow 落点 / 证据 | 企业需补 / 备注 |
|---|--------|------|----------------------|------------------|
| J1 | 多租户隔离 | ❌ | 单部署单租户；隔离粒度 `user × thread`；无 org/workspace/tenant | 要 SaaS 多租户需自建上层；单租户自托管反而更简单 |
| J2 | IM 用户身份 | ❌ | IM 消息共享 `"default"` user_id | 需 per-IM-user 映射；否则所有 IM 用户同一身份 |
| J3 | 租户配额 / 计费隔离 | ❌ | 有 token usage、并发上限；无租户配额/货币预算 | 平台层做配额与计费；token budget 只是 per-run |
| J4 | 漏洞披露流程 | 🟡 | `SECURITY.md`：GitHub Security 报告；无 SLA、无 PGP | 企业要与维护方约定响应时限；或买商业支持 |
| J5 | 补丁 / 版本支持 | 🟡 | 无正式 release；main/1.x 两分支；版本锁步有 CI | 自建镜像与补丁流程；订阅安全公告 |
| J6 | 备份 / 恢复 | 🟡 | 有备份文档与 DB/PVC 说明；无内置备份任务 | 用 K8s CronJob/云备份；定期演练恢复 |
| J7 | 事件响应 / 演练 | ❌ | 无 IR runbook、无 kill switch 演练、无公开渗透测试报告 | 企业自建 IR；与平台层联动 |
| J8 | 合规证据 / 证书 | ❌ | 无 SOC 2 / ISO 27001 / ISO 42001 证书；只有合规映射文档 | 自托管由企业取证；要证书选商业平台 |
| J9 | 等保 / 生成式 AI 备案 | ❌ | 无内置等保/备案材料；内容安全需外挂 | 按部署地域与业务形态单独办理 |
| J10 | Agent 清单 / 责任人 / 用途 | ❌ | 有自定义 agent 配置与 thread，但无 agent registry、owner、purpose、last-used | 建 CMDB/Agent registry；与 IdP 责任人绑定 |
| J11 | AI 交互披露 / 生成内容标识 | ❌ | 无「你在与 AI 交互」提示、无生成内容水印/标识 | 按 EU AI Act/中国标识办法加 UI 标识与水印 |
| J12 | 风险评估 / DPIA | ❌ | 有合规映射文档；无内置风险评估模板/流程 | 用 NIST AI RMF/ISO 42001 做 DPIA；把 agent 纳入风险登记册 |

---

## 怎么用这张表

1. **先筛 ❌**：B1/B2/B4、D1/D2/D3、E6、F3/F4/F8、G4/G5/G8、H4/H5/H6、I4/I7/I8、J1/J2/J8 是「没有就是没有」的项，靠配置补不出来。
2. **再筛「默认关」**：C1/C2/F2、`token_budget`、`network.mode` 都是「有但默认不生效」。评审时要求部署方出示实际配置，不要看代码里有没有。
3. **最后看「有但不完整」**：A1/A4、C4/C5/C6/C7、E3/E4/E5/E7、F2/F5/F6、G6/G7、H2/H3、I1/I6——这些是最容易被销售话术模糊掉的部分，逐条要证据。
4. **不要把 ✅ 当「绝对安全」**：✅ 只表示「这个控制存在且可执行」，不表示「配置正确」「没有被绕过」「经过渗透测试」。

> 配套分析见 [07-enterprise-readiness.md](07-enterprise-readiness.md)：为什么这些缺口存在、企业平台怎么做、三种卖法与责任边界。

---

## 附：NIST AI RMF 四功能对照

| 功能 | 企业要求 | DeerFlow 能提供 | 缺口 |
|------|----------|------------------|------|
| **Govern** | AI 政策、角色与责任、Agent 台账、第三方风险管理 | 配置/代码可审计；插件 grant 有归属 | 无 agent registry/责任人、无策略引擎、无第三方风险台账 |
| **Map** | 场景与影响评估、数据分类、风险登记 | 威胁模型文档、数据流文档、控制清单 | 无数据分类标签、无风险登记册、无 DPIA 模板 |
| **Measure** | 评测、红队、监控、指标 | RunJournal、tracing、guardrail 决策、221 个安全测试文件 | 无模型/Agent 评测集、无行为漂移监测、无红队报告 |
| **Manage** | 响应、恢复、沟通、持续改进 | cancel run/thread、备份文档、配置热加载 | 无 IR runbook、无全局 kill switch、无恢复演练 |

> 这张表只做「功能 → 机制」映射，不构成 NIST 合规结论。NIST AI RMF 是自愿性框架；正式评估仍需企业风险、法务与审计共同完成。
