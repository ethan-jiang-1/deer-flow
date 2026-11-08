---

title: "前端功能面地图"
description: '把 frontend/src/core 的 41 个目录逐项映射到职责、关键入口与后端 owner digest 页，作为 00–06 深挖之前的架构导航。'
type: deep-dive
topics: [frontend, core-modules, feature-map, backend-contracts]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 前端功能面地图

> **定位**：`frontend/` 的 feature map——回答「哪个 `core` 目录负责什么、入口在哪、对应哪个后端 owner」。按 `frontend/src/core/` 目录逐项建索引，给要定位改动面、判断归属、或从 UI 追到 Gateway 契约的人。
> **边界**：不替代 [00-overview](00-overview.md) 的组件树、[01-stream-pipeline](01-stream-pipeline.md) 的 SSE 管线、[02-message-rendering](02-message-rendering.md) 的渲染、[03-state-management](03-state-management.md) 的状态层、[04-workspace-layout](04-workspace-layout.md) 的布局、[05-subagent-ui](05-subagent-ui.md) 的 subagent UI、[06-architecture](06-architecture.md) 的模块总览；也不覆盖后端实现。

## 阅读路径

1. **先定坐标**：[00-overview.md](00-overview.md) + [06-architecture.md](06-architecture.md)，建立页面/组件/`core` 的对应。
2. **再查归属**：本篇主表——按目录查职责、入口文件与后端 owner。
3. **后下钻**：流式/渲染/状态/布局进 01–04；后端机制进 owner 列指向的 `internals/` 或 `concepts/` 页。

## 读表约定

- **深度**：`D` = 本篇有短节，或 00–06 已有专章可直接下钻；`I` = 主表一行 + 入口/契约足够定位；`M` = 只记归属与本地证据，不展开行为。
- **41 个目录**：`ls frontend/src/core` 共 43 项，其中 `clipboard.ts`、`static-mode.ts` 是文件，不计入本表。
- **证据**：入口列链到源码文件/行；owner 列链到 digest 页；没有独立后端页的标 `—` 并注明原因，仍不确定的写「未核实」。

## 主表（41 个目录）

| 目录 | 职责 | 入口/关键文件 | 对应后端 owner（digest 页） | 深度 |
|---|---|---|---|---|
| `agents` | Agent 定义、工具组与导入导出的 API/hooks，受 `agents_api` 开关约束 | [`api.ts:45`](../../frontend/src/core/agents/api.ts):45 · [`feature-cache.ts:46`](../../frontend/src/core/agents/feature-cache.ts):46 | [app-layer/01-api-reference](../enterprise-operations/app-layer/01-api-reference.md) | I |
| `api` | LangGraph SDK 单例、带认证的 fetch、网关错误与 stream_mode 白名单 | [`api-client.ts:650`](../../frontend/src/core/api/api-client.ts):650 · [`stream-mode.ts:1`](../../frontend/src/core/api/stream-mode.ts):1 | [app-layer/01-api-reference](../enterprise-operations/app-layer/01-api-reference.md) | D |
| `artifacts` | artifact 内容加载/编辑、表格预览 Worker、ZIP 归档与草稿上下文 | [`loader.ts:50`](../../frontend/src/core/artifacts/loader.ts):50 · [`preview.ts:22`](../../frontend/src/core/artifacts/preview.ts):22 | [app-layer/00-overview](../enterprise-operations/app-layer/00-overview.md) | D |
| `auth` | 会话获取、SSR 门控、权限判定、登录/登出与静态/demo 用户 | [`AuthProvider.tsx:67`](../../frontend/src/core/auth/AuthProvider.tsx):67 · [`server.ts:15`](../../frontend/src/core/auth/server.ts):15 | [identity](../enterprise-it-governance/identity/README.md) | D |
| `background-tasks` | 线程内 MCP durable task 的列表/详情/取消与轮询 | [`api.ts:8`](../../frontend/src/core/background-tasks/api.ts):8 · [`hooks.ts:22`](../../frontend/src/core/background-tasks/hooks.ts):22 | [mcp/durable-tasks](../internals/mcp/durable-tasks.md) | I |
| `blog` | Nextra 页面树上的博客索引、标签与语言选择 | [`index.ts:260`](../../frontend/src/core/blog/index.ts):260 | —（Nextra 内容，无后端） | M |
| `capabilities` | 能力目录（plugin/MCP/Lark/skill）的目录、安装状态与安装动作 | [`hooks.ts:26`](../../frontend/src/core/capabilities/hooks.ts):26 | [capabilities](../internals/capabilities/README.md) | D |
| `channels` | IM provider/连接读取、连接与断开、绑定码、微信扫码登录 | [`api.ts:20`](../../frontend/src/core/channels/api.ts):20 · [`hooks.ts:18`](../../frontend/src/core/channels/hooks.ts):18 | [channels](../enterprise-operations/channels/README.md) | D |
| `citations` | 从消息 markdown 提取 citation、知识 source 锚点与 sanitize | [`sources.ts:135`](../../frontend/src/core/citations/sources.ts):135 | [knowledge](../internals/knowledge/README.md) | D |
| `config` | 从 env 解析 backend 与 LangGraph base URL（含 mock/SSR 回退） | [`index.ts:11`](../../frontend/src/core/config/index.ts):11 | [configuration](../internals/configuration/README.md) | I |
| `conversation-references` | 把附加会话引用写成可见消息 metadata（只读展示） | [`metadata.ts:31`](../../frontend/src/core/conversation-references/metadata.ts):31 | [app-layer/01-api-reference](../enterprise-operations/app-layer/01-api-reference.md) | I |
| `dom` | 可见性/减动效驱动的渲染活跃度观察 | [`render-activity.ts:9`](../../frontend/src/core/dom/render-activity.ts):9 | —（浏览器 API） | M |
| `extensions` | 插件清单/registry、surface 挂载、插件页面路由与 @ 提及 | [`registry.ts:162`](../../frontend/src/core/extensions/registry.ts):162 · [`pages.ts:5`](../../frontend/src/core/extensions/pages.ts):5 | [packaged-extensions](../internals/harness-hooks/09-packaged-extensions.md) | D |
| `features` | `/api/features` 开关读取与 fail-open/sticky 缓存 | [`api.ts:84`](../../frontend/src/core/features/api.ts):84 | [app-layer/01-api-reference](../enterprise-operations/app-layer/01-api-reference.md) | I |
| `i18n` | en-US/zh-CN 字典、context、cookie 与服务端 locale 检测 | [`context.tsx:26`](../../frontend/src/core/i18n/context.tsx):26 · [`locale.ts:1`](../../frontend/src/core/i18n/locale.ts):1 | —（前端本地；`locale` 偏好见 settings） | D |
| `input-polish` | 发送前草稿润色的单次请求封装 | [`api.ts:16`](../../frontend/src/core/input-polish/api.ts):16 | [configuration/04](../internals/configuration/04-config-reference.md) | D |
| `integrations` | Lark 托管集成的状态/安装/认证/配置 API 与缓存 | [`lark/api.ts:55`](../../frontend/src/core/integrations/lark/api.ts):55 | [integration](../enterprise-operations/integration/README.md) | I |
| `knowledge` | 知识 scope 快照、检索目录与来源展示类型 | [`scope-api.ts:36`](../../frontend/src/core/knowledge/scope-api.ts):36 · [`scope.ts:1`](../../frontend/src/core/knowledge/scope.ts):1 | [knowledge](../internals/knowledge/README.md) | D |
| `mcp` | MCP 配置（deployment/user）、server CRUD、表单解析与图标 | [`api.ts:32`](../../frontend/src/core/mcp/api.ts):32 · [`parse.ts:59`](../../frontend/src/core/mcp/parse.ts):59 | [mcp](../internals/mcp/README.md) | D |
| `memory` | 用户记忆读取/清理/facts CRUD、导入导出与归一化 | [`api.ts:84`](../../frontend/src/core/memory/api.ts):84 · [`hooks.ts:17`](../../frontend/src/core/memory/hooks.ts):17 | [memory](../concepts/memory/README.md) | D |
| `messages` | 消息派生：usage、outline、tool error、run duration、model control | [`derived-state.ts:89`](../../frontend/src/core/messages/derived-state.ts):89 · [`conversation-outline.ts:31`](../../frontend/src/core/messages/conversation-outline.ts):31 | —（前端派生；事件源见 01/03） | D |
| `models` | 模型列表/能力/收藏、managed models 管理面与选择控制 | [`api.ts:14`](../../frontend/src/core/models/api.ts):14 · [`control.ts:40`](../../frontend/src/core/models/control.ts):40 | [model-layer](../internals/model-layer/README.md) | I |
| `notification` | 浏览器 Notification 权限与按偏好展示 | [`hooks.ts:22`](../../frontend/src/core/notification/hooks.ts):22 | —（浏览器 Notification API） | M |
| `projects` | 项目 CRUD、文档/线程文件、composer 附件交接 | [`api.ts:103`](../../frontend/src/core/projects/api.ts):103 · [`composer-attach.ts:62`](../../frontend/src/core/projects/composer-attach.ts):62 | [projects](../concepts/projects/README.md) | D |
| `scheduled-tasks` | 定时任务 CRUD、运行历史、轮询与 cron/状态格式化 | [`api.ts:13`](../../frontend/src/core/scheduled-tasks/api.ts):13 · [`hooks.ts:70`](../../frontend/src/core/scheduled-tasks/hooks.ts):70 | [scheduler](../enterprise-operations/scheduler.md) | D |
| `settings` | localStorage 偏好、跨 tab store、账号偏好同步与 locale 同步 | [`store.ts:21`](../../frontend/src/core/settings/store.ts):21 · [`user-preferences.ts:63`](../../frontend/src/core/settings/user-preferences.ts):63 | [app-layer/00-overview](../enterprise-operations/app-layer/00-overview.md) | D |
| `sidecar` | 侧聊线程创建、引用上下文与打开状态 | [`api.ts:26`](../../frontend/src/core/sidecar/api.ts):26 · [`thread.ts:5`](../../frontend/src/core/sidecar/thread.ts):5 | —（复用 `/api/threads`；是否有 sidecar 专用后端处理未核实） | I |
| `skills` | skills 列表/启用/安装/上传/诊断、slash 解析与使用记录 | [`api.ts:151`](../../frontend/src/core/skills/api.ts):151 · [`slash.ts:38`](../../frontend/src/core/skills/slash.ts):38 | [skills-tools](../concepts/skills-tools/README.md) | D |
| `streamdown` | markdown 预处理、fence/mermaid/插件与安全子节点 | [`index.ts:1`](../../frontend/src/core/streamdown/index.ts):1 · [`preprocess.ts:105`](../../frontend/src/core/streamdown/preprocess.ts):105 | —（前端渲染） | D |
| `subagent-batches` | 线程内 subagent 批量执行记录与明细 | [`api.ts:12`](../../frontend/src/core/subagent-batches/api.ts):12 | [subagent](../concepts/subagent/README.md) | D |
| `subagents` | 自定义 subagent 注册表 CRUD | [`api.ts:27`](../../frontend/src/core/subagents/api.ts):27 | [subagent](../concepts/subagent/README.md) | D |
| `suggestions` | 建议配置读取与 composer 占位提示 | [`api.ts:12`](../../frontend/src/core/suggestions/api.ts):12 | [app-layer/01-api-reference](../enterprise-operations/app-layer/01-api-reference.md) | I |
| `tasks` | subtask 生命周期、呈现、步骤与 context | [`context.tsx:22`](../../frontend/src/core/tasks/context.tsx):22 · [`lifecycle.ts:19`](../../frontend/src/core/tasks/lifecycle.ts):19 | [subagent lifecycle](../concepts/subagent/dual-threadpool-and-lifecycle.md) | D |
| `threads` | thread 流式 hook、历史分页、排序、活动、导出与分支 | [`hooks.ts:1956`](../../frontend/src/core/threads/hooks.ts):1956 · [`stream-state.ts:109`](../../frontend/src/core/threads/stream-state.ts):109 | [runtime](../internals/runtime/README.md) | D |
| `todos` | plan mode 的 todo 类型 | [`types.ts:1`](../../frontend/src/core/todos/types.ts):1 | [plan-mode](../concepts/builtin-tools/F-plan-mode.md) | I |
| `tools` | 工具调用的人类可读解释（i18n） | [`utils.ts:7`](../../frontend/src/core/tools/utils.ts):7 | [builtin-tools](../concepts/builtin-tools/README.md) | M |
| `trash` | 回收站文档列表/恢复/清除/清空 | [`api.ts:67`](../../frontend/src/core/trash/api.ts):67 | [app-layer/01-api-reference](../enterprise-operations/app-layer/01-api-reference.md) | I |
| `uploads` | 线程上传、文件校验、限额与 prompt input 文件 | [`api.ts:126`](../../frontend/src/core/uploads/api.ts):126 | [upload-security](../enterprise-operations/app-layer/02-upload-security.md) | I |
| `utils` | uuid/JSON/日期/文本/markdown/文件通用函数 | [`files.tsx:171`](../../frontend/src/core/utils/files.tsx):171 · [`datetime.ts:17`](../../frontend/src/core/utils/datetime.ts):17 | —（前端通用函数） | M |
| `voice-input` | Web Speech API 封装、语言映射、重启与文本拼接 | [`speech-recognition.ts:78`](../../frontend/src/core/voice-input/speech-recognition.ts):78 | —（浏览器 Web Speech API） | D |
| `workspace-changes` | run 级文件变更读取、摘要与 badge 计算 | [`api.ts:6`](../../frontend/src/core/workspace-changes/api.ts):6 · [`summary.ts:10`](../../frontend/src/core/workspace-changes/summary.ts):10 | [workspace-changes](../concepts/workspace-changes.md) | I |

## 八个短节

### settings

入口是设置 dialog 的 `SettingsSection`（`components/workspace/settings/settings-dialog.tsx:94`，含 models/users/account/appearance/channels/memory/subagents/notification/about），逻辑入口是 `core/settings/index.ts:1` 导出的两个 hook。状态分两层：`store.ts:21` 的进程内外部 store 叠加 `localStorage["deerflow.local-settings"]`（`local.ts:22`），并监听 `storage` 事件做跨 tab 合并（`store.ts:103`）。账号级偏好由 `user-preferences.ts:63` 启动，`GET/PATCH /api/v1/auth/preferences`（`:74`）携带 `X-Expected-User-Id`，403/409 时停止重试以避免切号串写。它不保存 `config.yaml` 的服务端配置；偏好端点归 `../enterprise-operations/app-layer/00-overview.md`，配置字段的 owner 页是 `../internals/configuration/README.md`。

### memory

Memory 的 UI 入口在设置 dialog 的 `memory` 分区（`settings-dialog.tsx:153`），数据入口是 `core/memory/hooks.ts:17` 的 `useMemory` 与 `memory/api.ts:84` 起的读写函数。读是 `GET /api/memory`，写面覆盖 clear/delete/create/update 与 `/api/memory/export|import`（`memory/api.ts:84-140`），import 先经 `normalizeMemoryPayload`（`import-memory.ts:115`）校验再提交。前端把 `version`/`revision` 与 fact 列表当作后端快照，不在本地合并事实。后端机制 owner 是 `../concepts/memory/README.md`（抽取队列与持久化下钻）。

### skills

Skills 的主入口是 Capability Center 的 skills tab（`components/workspace/capabilities/capability-center.tsx:100`），核心是 `core/skills/hooks.ts:7` 的 `useSkills` 与 `api.ts:151` 的 `loadSkills`。启用、安装、上传、reload、诊断分别打到 `/api/skills/{name}`、`/api/skills/install`、`/install/upload`、`/reload`、`/diagnostics/custom`（`api.ts:124-228`），安装失败会解析 security findings 并抛 `SkillRequestError`（`api.ts:20`）。Composer 的 `/skill` 语法由 `slash.ts:38` 解析，消息侧的 skill 使用记录来自 `usage.ts:20` 的 metadata 读取。后端 owner 是 `../concepts/skills-tools/README.md`。

### MCP

入口同样在 Capability Center 的 plugins tab，`core/mcp/hooks.ts:22` 的 `useMCPConfig(scope)` 用 `deployment | user` 决定读 `/api/mcp/config` 还是 `/api/mcp/personal/config`（`api.ts:8`）。写路径按 server 粒度走 create/update/delete/state（`api.ts:83-120`），`parse.ts:59` 负责把表单值转成 server 定义，`types.ts:1` 只保留 enabled/description/presentation 等展示字段。查询 key 是 `[mcpConfig, scope, user.id]`（`hooks.ts:25`），变更后 invalidate `mcpConfig` 与 `capabilities`（`hooks.ts:48`）。后端 owner 是 `../internals/mcp/README.md`；个人连接与 OAuth 见同目录 `session-pool-oauth-cache-invalidation.md`。

### auth

服务端入口是 `core/auth/server.ts:15` 的 `getServerSideUser()`，它在 workspace layout 先跑一次并把 tagged `AuthResult` 交给 `AuthProvider`（`app/workspace/layout.tsx:22`）。客户端状态机在 `AuthProvider.tsx:67`：`user` + `authKnown` + `refreshUser`（`/api/v1/auth/me`，`:112`），logout 先清本地再 POST `/api/v1/auth/logout`（`:181`）。权限只做 UI 提示，`permissions.ts:23` 的 `hasPermission` 在列表缺失时放行，真正 enforcement 在 Gateway 的 `@require_permission` 与 `authz.py`。认证模式（session/disabled/static）由 `isAuthDisabledMode()`（`auth-disabled-user.ts:20`）与 `isStaticWebsiteOnly()`（`static-mode.ts:3`）在入口处分流，`gateway-config.ts:12` 只提供 internal gateway URL 与 trusted origins；后端 owner 是 `../enterprise-it-governance/identity/README.md`。

### channels

入口在设置 dialog 的 channels 分区（`settings-dialog.tsx:147`），核心 `core/channels/hooks.ts:18` 同时拉 providers 和 connections。`api.ts:20` 的 `/api/channels/providers` 与 `:36` 的 `/connections` 是读面，连接打 `/{provider}/connect`，运行时配置打 `/{provider}/runtime-config`，断开连接/断开 provider 分别 `DELETE /connections/{id}` 与 `DELETE /{provider}/runtime-config`（`api.ts:48-110`）。扫码登录是异步两段式：`/wechat/qr-login` 起会话（`api.ts:123`），`connect-poll.ts:32` 以 2s 间隔轮询，`provider-state.ts:20` 决定某个 provider 当前是否可连接/需补运行时配置。后端 owner 是 `../enterprise-operations/channels/README.md`。

### voice-input 与 input-polish

语音输入完全在前端：`voice-input/speech-recognition.ts:78` 取 `SpeechRecognition`/`webkitSpeechRecognition`，`:87` 把 locale 映射成识别语言，`:100` 只对 `no_speech`/无错误重启，`:144` 负责把分段 transcript 拼回输入框；组件入口是 `components/workspace/input-box.tsx:3670` 的 voice button。润色走网络：`input-polish/api.ts:16` 的 `polishInputDraft` POST `/api/input-polish`（`:20`），请求体只有 text/locale/thread_id。后端是**一次性 LLM 调用、不创建 run**，配置在 `input_polish`（`backend/packages/harness/deerflow/config/app_config.py:308`），端点契约见 `../enterprise-operations/app-layer/01-api-reference.md` 与 `../internals/configuration/04-config-reference.md`。两者都在 composer 内触发，但一个纯浏览器、一个过一次 Gateway。

### i18n

Locale 只有 `en-US`/`zh-CN`（`locale.ts:1`），Provider 在 workspace 与 artifact-view 两个 layout 各自挂载（`app/workspace/layout.tsx:63`、`app/artifacts/view/layout.tsx:28`）。`I18nProvider`（`context.tsx:26`）维护 context 与 `document.documentElement.lang`（`:44`），`useI18nContext`（`:57`）是读入口。首次加载用 cookie `locale`，无 cookie 则 `detectLocale()` 取浏览器语言（`locale.ts:44`）；切换时 `i18n/hooks.ts:13` 同时写 context 和 1 年 cookie（`cookies.ts:48`）。字典按 locale 动态 import（`translations.ts:4`），服务端用 `detectLocaleServer`/`getI18n`（`server.ts:6`）做 SSR；没有独立的 i18n 后端 API，账号 `locale` 偏好由 settings 的 preferences 会话顺带同步（`user-preferences.ts:39`）。

## 相关目录

- [00-overview.md](00-overview.md) — 技术栈、组件树与数据流总览。
- [01-stream-pipeline.md](01-stream-pipeline.md) — `useThreadStream` 与 SSE 事件到 React state 的管线。
- [02-message-rendering.md](02-message-rendering.md) — streamdown、thinking、tool call、citation、artifact 预览。
- [03-state-management.md](03-state-management.md) — TanStack Query、ThreadState、偏好与权限门控。
- [04-workspace-layout.md](04-workspace-layout.md) — 面板、Projects、命令面板与 Capability Center。
- [05-subagent-ui.md](05-subagent-ui.md) — TaskTracker、批量 subagent 与后台任务 UI。
- [06-architecture.md](06-architecture.md) — 技术栈全景、扩展运行时与已删除面。
- [internals/](../internals/README.md)、[concepts/](../concepts/README.md)、[enterprise-operations/](../enterprise-operations/README.md) — 表内 owner 页的上层索引。
- 具体下钻：[configuration](../internals/configuration/README.md)、[mcp](../internals/mcp/README.md)、[knowledge](../internals/knowledge/README.md)、[capabilities](../internals/capabilities/README.md)、[memory](../concepts/memory/README.md)、[skills-tools](../concepts/skills-tools/README.md)、[subagent](../concepts/subagent/README.md)、[projects](../concepts/projects/README.md)、[identity](../enterprise-it-governance/identity/README.md)、[channels](../enterprise-operations/channels/README.md)。
