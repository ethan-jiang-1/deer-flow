---
title: "治理卷审计修复计划"
description: "针对 2026-11-08 全面审计发现的 BLOCKER/MAJOR/MINOR，按事实、结构、搬迁、工具链四条工作流逐项修复，并给出可执行的验收矩阵。"
topics: [governance, plan, audit]
---

# 治理卷审计修复计划

> **状态**：已执行（2026-11-08）。修复结果与验收数据见 [PLAN.md](PLAN.md) §10；
> 下列复选框保留为逐项底稿，未勾选项为后续可选改进，不阻塞本轮验收。
> **日期**：2026-11-08
> **基线**：`ethan @ a0661c083`（审计后工作区干净）
> **审计输入**：本轮 8 域并发审计 + 结构/工具/历史横切，去重后约 11 个 BLOCKER、35+ MAJOR、60+ MINOR。

## 0. 目标

把 `_digested/enterprise-it-governance/` 从“证据密度高但事实层不可靠的强草稿”修到
“**每条缺口结论都能被源码反证检查、每个入口页与文件树一致、每张指路都能落到真实章节**”，
再允许冻结。

具体四件事：

1. **事实层归零**：所有 BLOCKER 与 MAJOR 的假事实、错默认值、错能力边界修掉；MINOR 的锚点偏移与措辞一并清理。
2. **入口层同步**：8 个域 README 的“本篇目/规划中”与文件树一致；卷根篇数、编号冲突、孤图修复。
3. **搬迁层自洽**：`observability/07`、`orchestration-ladder/03` 的指路与 PLAN 的 §3/§4.3/§4.7 全部对齐真实落点。
4. **保障层可信**：`check_quality.py` 真正覆盖它声称的检查；不能覆盖的就降级声明，不再用“456 锚点全绿”冒充“语义正确”。

## 1. 不变量

| 约束 | 说明 |
|---|---|
| 只改三目录 | `_digested/`、`_faq_on_digested/`、`_deerflow_application_agent_ready_development/`。不得改 `backend/`/`frontend/`/`config.example.yaml` 等源码。 |
| 源码只读 | 所有修复以 v2.2.0 源码为真值；修复过程只读源码、只改文档。 |
| 不 force-push | 修复完成并全量验收前不推送；`origin/ethan` 保持现状。 |
| `b56fe3f81` 不恢复 | `main` 是上游镜像，按仓库 `_digested/README.md` 约定不得直接改 `main`。保留精确 revert；在 PLAN §7.x 记录“待上游化”的后续项，不为了性能破坏三目录铁律。 |
| 三态纪律 | 缺口一律写“无 / 有但不覆盖 / 部分闭合”，禁止裸“有/无”。 |
| 单一事实源 | 数字型事实只在 §9.5 登记表定义一次；正文引用相对链接或复述同一值，不另立新值。 |

## 2. 修复原则

1. **先反证，再落笔**：每条“无/不覆盖/部分”先用 `grep` + 打开源码确认；确认不了就降级为“未核实”，不写绝对化。
2. **能力清单优先于缺口清单**：先列“已有机制 + 默认状态 + 边界”，再写“缺什么”。
3. **锚点指向断言本身**：引用行必须落在支撑句子的那几行；引用原话必须带行号。
4. **入口页最后写**：正文定稿后再回填 README，避免二次漂移。
5. **每批可回滚**：按工作流分批提交，每批独立跑闸门。

## 3. 工作流与清单

### WS0 基线与记录

- [ ] 记录修复前基线：`check_quality.py` exit 0 / `verify_anchors.py` 456 / 三目录 0 / 工作区干净
- [ ] 在 `PLAN.md` §10 或本文件追加“审计修复记录”，逐批记录改了什么、验了什么

### WS1 事实修复（P0）

#### WS1.1 成本与限额（cost/）

- [ ] `cost/03:120` “一次派发 64 个 → 不挡” 改为“默认截到 min(max_running=3, remaining_total=6)”
- [ ] `cost/03:94` “并发 = max_total_per_run” 改为并发=`subagent_runtime.max_running`（默认 3），总量=`max_total_per_run`（默认 6）
- [ ] `cost/03:119` “≥200k 会触发” 补“顶层 token_budget 默认关闭；开启后”
- [ ] `cost/03:31` “出厂不做任何 token 限制” 改为“顶层不做；子代理 token_budget 默认开启（2M/1M）”
- [ ] `cost/01:87/96-99` “无单价表/无换算/无视图” 改为“有 `models[*].pricing` + Console 事后计价/单用户聚合；缺货币预算执行、跨用户/集群视图、运维告警”
- [ ] `cost/01:104-105` “数据留了计算没做” 改为“cache_read_tokens 已参与 cache-aware 计价”
- [ ] `cost/01:75-76` “统计到的是零” 改为“缺 usage 记为 null + missing_usage_calls”
- [ ] `cost/01:14` “TokenUsageMiddleware 标注 usage_metadata” 改为“读取 provider usage、合并子代理用量”
- [ ] `cost/02:51/57` 迁移数 51→50；`migrate_user_isolation.py` 归到 `backend/scripts/`
- [ ] `cost/02:72` credentials key 绝对化改为“单实例自动生成；multi_instance + 凭据消费者才拒绝启动”
- [ ] `cost/02:73` 登录限速 N 倍改为“默认 auto→db 共享；仅 memory 才 N 倍”
- [ ] `cost/02:82/85/95-96` mtime→内容签名；guardrails 热加载；断路器作用域；去重
- [ ] `cost/03:136-139` hard stop 留痕改为“有 `runs.stop_reason`，无 journal 事件/告警”
- [ ] `cost/03` 修两个 `## 2.` 与两个 `### 2.1`
- [ ] `cost/03:65/118` recursion_limit 补“调度 run 默认 1000”
- [ ] `cost/04` 补第 8 条启动拒绝规则（channel leader lease），与 `deps.py` 编号一致
- [ ] `cost/05:55/77` `§3.3`→`§1.3`；`:76` 静默截断边界；`:29` batch_task 例外；`:48-55` 补 scheduler 默认
- [ ] `cost/README:12` “max_total_per_run + token_budget” 拆成“派发计数上限 + token 预算”
- [ ] `cost/README:23-29` 03/04/05 移出“规划中”

#### WS1.2 身份与接入（identity/）

- [ ] `identity/01:20`、`08:143` PAT 过期：支持 `expires_in_days` 1–365，缺省不过期
- [ ] `identity/08:14` 重画 `pat-layers.svg`：只列 9 个 scope（threads/runs/projects），删 agents/models/skills/runs:write
- [ ] `identity/08:111-120` 路由枚举补全 runs 子树、trash、project documents
- [ ] `identity/07:83/87/97-98` sso_failed：只有部分错误重定向；state 错误 403、discovery 502、缺参 400
- [ ] `identity/07:130` admin_emails 只在首次建号生效，不重授/不降级
- [ ] `identity/07:165` 账号与 provider 有绑定（provider, oauth_id）唯一索引；同邮箱第二个 IdP 是 409
- [ ] `identity/07:119` 删掉不存在的“邀请制”路径，改为“管理员无法预建 SSO 账号”
- [ ] `identity/09:116` 锁禁可 live 调低提前释放；`auth.local` 4 个键
- [ ] `identity/README:20/27-34` 三条→四条；07–10 移出“规划中”
- [ ] `identity/01:76` 11→13 权限
- [ ] `identity/07:50/52/53/57/94-95/107-110` 配置契约与锚点修正
- [ ] `identity/07:28` 删“此前一处未提”，改指 `enterprise-operations/security/01-auth.md`
- [ ] `identity/08:72/122` disabled 行为；“新路由自动不可见”改为“不匹配既有 pattern 才默认拒绝”
- [ ] `identity/09:20/92/115`、`10:27-31` 锚点/函数职责修正
- [ ] `identity/07:70/98`、`10:115` 去祈使句
- [ ] `identity/02:144` §4→§1；`01:49` 与 `08 §2.3` 去重
- [ ] `identity/03:72-73/95-101/119`、`04:82/96`、`05:16-18`、`02:144` 等 MAJOR/MINOR 修正

#### WS1.3 授权（authorization/）

- [ ] `authorization/04:57/130/133` 内置 `RbacAuthorizationProvider` + roles 可配
- [ ] `authorization/04:134` `/auth/me` 返回 `permissions`
- [ ] `authorization/README:12/24-29` 11→13；04/05 移出“规划中”
- [ ] `authorization/03:17-18/21/27-36/126` 热加载/重启矩阵与 subagent 并发
- [ ] `authorization/01:23/69` 去掉“所有工具直接执行”“从不 allow”
- [ ] `authorization/02:92/103/112` per-thread/per-user 绝对化改为“无开箱配置项，provider 可实现”
- [ ] `authorization/05` 8+ 处锚点、`05:176` MCP 细粒度、`05:144` admin 降级
- [ ] `authorization/03:85`、`01:18`、`01:13`、`01:79`、`04:33/57/69/84`、`05:15/82/177` 修正

#### WS1.4 执行（execution/）

- [ ] `execution/02:74/76` bash 路径：第 5 层只校验文件工具参数，`cat /etc/passwd`/`..` 不被它挡
- [ ] `execution/01:17` 锚点改到 `aio_sandbox_provider.py:348-368`；配置键 `sandbox.provisioner_url`
- [ ] `execution/01:23/29-30` 七模式/三档图对齐（或改图/改表述）
- [ ] `execution/03/04` AIO 默认 2 CPU/2G/pids 512；三态改写
- [ ] `execution/04:18/24/55-67` 出站网络只覆盖 AIO 本地 Docker，默认 Local 无策略
- [ ] `execution/05:53-54` 900→1800；轮询 372
- [ ] `execution/05:37-41/44` 指到 cost/05 §1，不再指错
- [ ] `execution/02:16/38-39/62-63`、`03:30-32/76-77/96`、`05:28/30-31/47/58`、`04:19`、`README:22-23` 修正

#### WS1.5 数据（data/）

- [ ] `data/06:73/115`、`03:115` “run 事件不随删”改为“随 thread 删除并置 evidence partial”
- [ ] `data/01:60-69` 删掉 OpenAI Assistants 兼容层的能力虚构
- [ ] `data/06:30-49/111` “只在启动清扫”改为“启动 + GET /api/trash/documents 惰性清扫；无周期定时器”
- [ ] `data/01` 补 USER.md、per-user skills、`{project_root}/.deer-flow` 根
- [ ] `data/06` 补 `blob_storage` / `knowledge_base` 驻留边界
- [ ] `data/03:111/130` “无自动保留”与 06 对齐（部分）
- [ ] `data/05 §4` 六行证据列错位修正
- [ ] `data/05` 补 fail-open 边界（`pii_redaction_middleware.py:396-402`）
- [ ] `data/02:94/98-100` 映射方向写反：本用户段被替换、他用户绝对路径原样泄露
- [ ] `data/02:33-39/35/74-77`、`03:68-75/104-107`、`04:17/52/87`、`01:46-52/81/91`、`06:46-47`、`05:88`、`README` 修正

#### WS1.6 审计（audit/）

- [ ] `audit/01:17/30` SandboxAudit 改为结构化 JSON
- [ ] `audit/01:110` 去“能证明未被篡改”；改“能发现摘要不一致，不能抗有库写权限的篡改”
- [ ] `audit/03:28` 删“六个方法=全部”，补 `run.*`/`llm.*`/`subagent.*`/`workspace_changes`
- [ ] `audit/03:45/106/112`、`02-sandbox:173` 文件工具走 `llm.tool.result`，不是无审计
- [ ] `audit/03:46` MCP 也走 `on_tool_end`
- [ ] `audit/01:49`、`03:119` subagent 盲区改为“无决策字段，但拒绝文本可见”
- [ ] `audit/01:13-20` 三层表改为实际层数；run 生命周期机制改对
- [ ] `audit/01:43`、`03:37` fail-open allow 例外
- [ ] `audit/02-observability:16-23/23/67/99/82-89/100` SSE 事件名、end 载荷、Monocle OTel、console 聚合、Redis 续传
- [ ] `audit/02-sandbox:140-144/169` 截断边界
- [x] `audit/README` 补 sandbox-audit、event-coverage；重编号为 03/04（02 重复前缀已消除）
- [ ] `audit/01:48/57/59/60/111/115/34`、`03:17/24/40/91/106`、`02:27`、`02-sandbox:42/55-63/155`、`01:19/66/36` 修正
- [ ] `PLAN:487` guardrail 6→12 字段

#### WS1.7 生命周期与合规（lifecycle/、compliance/）

- [ ] `lifecycle/01:56-57` guardrails fail_closed/provider、allow_host_bash 不是重启绑定；补真正重启项
- [ ] `lifecycle/02:44`、`01:90` 自定义 agent 删除 API 存在但 `agents_api.enabled` 默认 false
- [ ] `lifecycle/03:36/63-64`、`01:110` 有 `list_all()` 与 AgentRow id，缺的是运行实例视图/管理员聚合端点
- [ ] `lifecycle/README:12` “版本闸门”改为“版本告警，不阻断”
- [ ] `lifecycle/02:22` “七步流”按协议 4 操作 + 集成流程改写
- [ ] `lifecycle/01:106` kill switch 改为“无全局 agent kill switch；有 per-channel/per-integration 开关”，删 grep 零命中
- [ ] `lifecycle/03:16` 64 表述与 §9.5 对齐
- [ ] `lifecycle/01:93` thread 删除与项目回收站 30 天区分
- [ ] `lifecycle/02:32/37/39`、`01:37-38` 锚点修正
- [ ] `compliance/01:54` 删法律分类结论
- [ ] `compliance/02:50` run 事件删除；`:85` 脱敏范围；`:104/139` 惰性清扫
- [ ] `compliance/03:35/57` disabled 立即拒权，状态改“是”
- [ ] `compliance/04:94` `tool_progress`→`loop_detection`
- [ ] `compliance/01` 补“控制项→机制→证据→状态”四列映射；`02` 扩到 ≥60 行

### WS2 结构与导航（P1）

- [ ] 8 个域 README：已交付页从“规划中”移到“本篇目”，补链接
- [x] `audit/README` 补 sandbox-audit；重编号 02-observability / 03-sandbox-audit / 04-event-coverage
- [ ] 卷根 `README.md` cost 5→6；与文件树核对全表
- [ ] `00-overview.md` “全部结论都附 file:line” 降级为“判断性段落附证据”
- [ ] `enterprise-operations/README.md` 标题与目录名对齐（`Operations`→`Enterprise Operations`）
- [ ] 三张孤儿 SVG：`defense-in-depth.svg`、`governance-overview.svg` 重新嵌入 00-overview/README；`execution-layers.svg` 嵌入 execution/01 或删除

### WS3 搬迁与 PLAN 自洽（P1）

- [ ] `orchestration-ladder/03:195` 指路 → `cost/05 §2`
- [ ] `PLAN` §3.6/§4.4/§4.7/task 5 的 `cost/03` → `cost/05`；任务 5 说明“后拆到 cost/05”
- [ ] `PLAN` §4.3 vs §4.7 落点统一：guardrail deny、操作完整性、终态原子性、实时成本告警
- [ ] `PLAN` §0.1 的“≤3→64”改为与 §4.7.x/§9.5 一致
- [ ] `PLAN` §9.5 6 字段→12 字段；`§3.6` 8 条→实际 8 条（补 channel leader lease）
- [ ] `PLAN` §9“全部检查”改为真实覆盖范围；补 §10 修复记录
- [ ] `observability/07` 指路表与真实落点复核（实时成本告警→cost/03）
- [ ] 检查搬迁后原文件无残留正文/重复叙述

### WS4 跨卷同步（P1）

- [ ] `enterprise-operations/security/01-auth.md:172/183` 6→13 权限，补 runs/projects
- [ ] `_digested/enterprise-operations/security/05-production-auth-setup.md:76` 6→13
- [ ] `_digested/enterprise-operations/security/01-auth.md` 三条→四条认证路径（或明确计数口径）
- [ ] 全库 grep `6 个权限`/`11 个权限`/`三条.*认证路径` 清零

### WS5 工具链与保障（P2）

- [ ] `check_quality.py`：`AUDIT-FIX-PLAN.md` 视为 index；README 文件覆盖检查；章节编号唯一；数字登记（13/3/4/64/6/1800/30/7）；`无 X` 断言的 grep 反证（可选 warn）
- [ ] `check_quality.py`：把判断段落正则对应的死代码改成真实检查，或删除并改声明
- [ ] `verify_anchors.py`：至少加“锚点行非空/非纯注释”提示；保持存在性定位
- [ ] `check_digest.py`：把 `--only line_symbol_strict` 写进 PLAN §9 的语义抽查步骤；不默认开启
- [ ] `PLAN` §9/§6 的验收命令更新，新增 `AUDIT-FIX-PLAN.md` 的说明

### WS6 全量验收与提交（P0/P1 完成后）

- [ ] `python3 _digested/_upstream-sync/tools/check_digest.py` exit 0
- [ ] `python3 _digested/enterprise-it-governance/tools/check_quality.py` exit 0
- [ ] `python3 _digested/enterprise-it-governance/tools/verify_anchors.py` exit 0
- [ ] 三目录铁律输出 `0`；`git diff v2.2.0 HEAD -- backend/` 为空
- [ ] 逐篇 ≥3 锚点；所有“无”类断言有 grep/源码反证
- [ ] 8 个 README 文件覆盖检查 0 漏
- [ ] 13 张 SVG 全部被引用（或删除）
- [ ] 按 WS 分批提交，commit message 记录“修了哪些域、对齐了哪些源码事实”
- [ ] 更新 `PLAN.md` §10 修复记录与 `AUDIT-FIX-PLAN.md` 勾选状态

## 4. 验收矩阵

| 项 | 命令/方法 | 通过标准 |
|---|---|---|
| 断链/行号/路径 | `check_digest.py` | exit 0 |
| 质量闸门 | `check_quality.py` | exit 0，0 block |
| 锚点存在性 | `verify_anchors.py` | exit 0 |
| 三目录 | `git diff --name-only -z v2.2.0 HEAD \| ...` | `0` |
| 源码未改 | `git diff v2.2.0 HEAD -- backend/ frontend/ config.example.yaml` | 空 |
| 入口覆盖 | 新增脚本/检查 | 每个域 README 列出全部 md |
| 数字一致 | 新增脚本/检查 | §9.5 所有值全文唯一 |
| 语义抽查 | `check_digest.py --only line_symbol_strict` | 0 确定问题（启发式误报人工判） |

## 5. 提交策略

| 批次 | 内容 | 提交信息前缀 |
|---|---|---|
| F1 | cost + identity + authorization 事实 | `docs(governance-fix): 事实层 A — 成本/身份/授权` |
| F2 | execution + data + audit 事实 | `docs(governance-fix): 事实层 B — 执行/数据/审计` |
| F3 | lifecycle + compliance + 跨卷同步 | `docs(governance-fix): 事实层 C — 生命周期/合规/跨卷` |
| F4 | README/编号/篇数/SVG/搬迁/PLAN | `docs(governance-fix): 结构与导航` |
| F5 | 工具链 + 验收记录 | `docs(governance-fix): 闸门与验收` |

## 6. 风险与回退

| 风险 | 缓解 |
|---|---|
| 批量编辑引入新漂移 | 每批后跑三道闸门；逐条 grep 复核 |
| 把“有”改“无”又改过头 | 每处改动附源码行；不确定时保留“未核实”并标记 |
| README 二次漂移 | 正文定稿后再回填；最后用脚本核对 |
| 新增文件改变篇数指标 | 更新 `check_quality.py` 的 index 判定与 PLAN 指标 |
| 工具检查误报 | 新检查先 warn，稳定后再 block |

## 7. 完成定义

- [ ] 全部 WS1–WS5 勾选完成
- [ ] 三道闸门 exit 0；三目录 0；源码零 diff
- [ ] 审计报告中的 BLOCKER/MAJOR 逐条有“已修”记录（本文件或 PLAN §10）
- [ ] 8 个 README 与文件树一致；13 张 SVG 无孤儿
- [ ] `PLAN.md` §9/§9.5/§4.7 与正文、工具、真实落点一致
- [ ] 工作区干净；提交信息可追溯
