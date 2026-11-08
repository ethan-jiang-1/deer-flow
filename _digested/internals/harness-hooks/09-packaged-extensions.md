---
title: "打包扩展（packaged extensions）：贡献点、CLI 管理与信任边界"
description: "- `deerflow/extensions/` — 宿主侧加载/注册/中间件注入/钩子接线；`deerflow-extension-api` — 第三方扩展的公开契约"
topics: [extension, plugin-system, contribution-points]
---

# 打包扩展（packaged extensions）：贡献点、CLI 管理与信任边界

DeerFlow 的扩展机制分两半：宿主侧实现（`deerflow/extensions/`，加载、注册、接线）和公开契约包（`deerflow-extension-api`，`import: deerflow_extension_api.*`，第三方扩展的独立依赖）。第三方 Python 包暴露一个 `install(registry, config)` 函数，从 `config.yaml` 的 startup-only 顶层 `plugins:` 列表按序加载。

> 权威事实来源：`backend/packages/harness/deerflow/extensions/AGENTS.md`（管理模型）、`backend/packages/extension-api/deerflow_extension_api/`（公开契约）、`examples/deerflow-extension-example/`（五种贡献的完整示例）。用户向手册（upstream v2.1.0 起）：`frontend/src/content/{en,zh}/harness/extensions/`（10 页，root `AGENTS.md` 明文指向它）。

## 概念定位：三块扩展面，三种信任等级

| 配置面 | 文件 | 谁能改 | 内容 |
|--------|------|--------|------|
| `plugins:` | `config.yaml`（顶层） | **仅 operator**（文件只读挂载） | 打包 Python 扩展入口点，**会导致代码被 import** |
| `extensions:` | `extensions_config.json` | Gateway HTTP API 可写 | MCP servers + skills 状态 + config 声明的 middleware |
| `extensions.middlewares` | `extensions_config.json` | operator | `AgentMiddleware` 类路径**或 🆕 `{class, kwargs}` 对象**（lead + subagent runtime） |

关键分离：`plugins:` 必须留在 `config.yaml`，因为那一行列表 `module.path:install` 会在启动时被 import——这是**代码执行边界**，绝不能放进 Gateway 可重写的 `extensions_config.json`。打包扩展用 PEP 621 entry point：

```toml
[project.entry-points."deerflow.extensions"]
example = "deerflow_extension_example:install"
```

`install` 的签名是 `install(registry: ExtensionRegistry, config: Mapping[str, Any]) -> None`，`config` 来自该 plugin 的私有 `config` 块、原样传入（浅拷贝）。

## 加载模型（`extensions/loader.py`）

`config.yaml` 里每条 `plugins:` 记录是一个 `ExtensionSpec`（Pydantic，`extra="forbid"`）：

```python
class ExtensionSpec(BaseModel):
    enabled: bool = True      # false = 不 import、不注册
    name: str | None          # operator 可见的稳定名（manager 记录）
    package: str | None       # manager 记录的 PyPI 发行名
    use: str                  # 入口点，如 "my_extension:install"
    config: dict[str, Any]    # 扩展私有配置，原样传 install()
    required: bool = False    # true = 加载失败中止 Gateway 启动
    table_prefix: str | None  # 扩展自有 MetaData/migration 的表名前缀
```

`load_extensions(specs)` 按 config 列表顺序逐个处理，核心流程：

1. `resolve_variable(spec.use)` 解析入口点（与 guardrail/tool 同一套反射加载，见 [03-reflection-loading.md](03-reflection-loading.md)）。
2. 读 `install.__deerflow_api__` 版本标记（`@extension(api="0.2.0")` 装饰器盖章），与宿主 `API_VERSION` 做 semver 兼容判断：pre-1.0 要求同 major.minor 且 host >= declared；不可解析的版本直接拒绝。
3. `registry.mark()` 快照各 bucket 长度 → 在 `registry.attributed_to(spec.use)` 作用域内调 `install(registry, _frozen_config(config))`。
4. `install()` 中途抛异常 → `registry.rollback_to(mark)` **位置式回滚**（不是按 source 删，因为两个 spec 可能共享同一个 `use`、不同 config）。
5. 默认 **fail-open**：坏扩展带着 diagnostic 被跳过，Gateway 仍启动；`required: true` 翻转成 **fail-closed**（`ExtensionLoadError` 中止启动）。

`table_prefix` 无条件注册（即使 disabled 或后续失败）到 alembic 的 `_env_filters`，避免 `alembic revision --autogenerate` 对着 live DB 提议 drop 掉扩展自有的表；与 host 表名冲突则**始终**中止启动。

## 贡献点（registry surface）

`ExtensionRegistry` 是写接口（`deerflow_extension_api.contracts.ExtensionRegistry`），宿主实现额外携带 attribution / rollback / build。`build()` 产出不可变的 `LoadedExtensions`（`extensions/registry.py`），所有 entry 都带 source 字符串以便 diagnostic 和 provenance 指名道姓。

公开契约暴露 **7 个注册方法**（示例包演示其中 5 个核心种类；agent-assembly 与 context-compaction 两个 observer 由后续 commit 补进契约）：

### 1. Middleware（`registry.middlewares(...)`）

`MiddlewareContributor.contribute_middlewares(app_store, ctx) -> Sequence[MiddlewarePlacement]`。声明 **scope**（`AgentScope.LEAD/SUBAGENT/BOTH`）、**稳定顺序**、**语义定位**（`Placement.MODEL_LOGICAL` / `MODEL_PHYSICAL` / `TOOL_VISIBLE` / `TOOL_RAW` / `STANDARD`）——而不是脆弱的列表下标。`extensions/stack.py` 是唯一最终组装点（不要在共享 base builder 里注入，lead builder 之后还会追加 middleware）；`extensions/ordering.py` 校验宿主排序不变量。贡献的 middleware 被 `IsolatedMiddleware` 包裹：扩展故障发 diagnostic 并 fail-open，不重复下游 model/tool 副作用。

### 2. Task lifecycle（`registry.task_lifecycle(...)`）

`TaskLifecycleContributor.on_task_start(app_store, task_store, info: TaskInfo)` / `on_task_stop(..., outcome: TaskOutcome)`。`TaskInfo` 描述一次 lead 或 subagent 执行（`task_id/run_id/thread_id/kind/parent_task_id/agent_name/resumed`），`TaskOutcome` 保守取值 `completed/aborted/failed`。lead worker 在 run 开始后 await `on_task_start`，在 completion 持久化后、发 stream end 前 await `on_task_stop`；带父 `run_id` 的 subagent 用同一对 start/stop 包裹。

### 3. System-model observers（`registry.system_model_observer(...)`）

`SystemModelCallObserver.on_system_model_call(app_store, task_store, kind, request, result)`。覆盖**不经过 middleware model-call 包装**的 DeerFlow 自有模型调用：`goal`（目标评估）、`memory`（记忆提取）、`title`（标题生成）、`summarization`（摘要）。`request.messages` 构造时归一化为 tuple（goal/memory 传 list、title/summarization 传单条 prompt 字符串），快照因此真正不可变。

### 4. Gateway-lifetime services（`registry.service(...)`）

`ExtensionService.start(deps: ExtensionRuntimeDeps)` / `stop()`。`ExtensionRuntimeDeps` 是宿主能力投影：`app_store`、`policy`（`HostPolicySnapshot`，token budget + `max_subagents_per_run` 的窄投影，见 `extensions/policy.py::project_host_policy`）、`session_factory`。启动顺序：持久化引擎 + session factory 就绪后按注册顺序 start；shutdown 在 run/subagent drain 之后、store/checkpointer/engine teardown 之前逆序 stop，每个 stop 有独立有界超时。

### 5. FastAPI routers（`registry.routers(...)`）

`routers(Sequence[Any])` —— router 类型保持 `Any`，让契约包**零框架依赖**。router 在 `install()` 期间急切构造，宿主在**所有 host 路由之后**才 mount，所以 host 处理器总是赢。宿主动态检测“确定阴影”（同方法下 route 覆盖前一个 host/extension route）并**原子拒绝**整个 router；host 的 auth/CSRF 豁免路径被保留，贡献的 `Mount`、WebSocket 路由、startup/shutdown 钩子、自定义 lifespan 都被拒绝（生命周期资源要用 `ExtensionService`）。贡献路由**强制 session 认证**，用 `deerflow_extension_api.auth` 区分普通用户 vs 管理员（见下）。

### （补充）Agent-assembly + context-compaction observers

- `registry.agent_assembly_observer(...)`：`AgentAssemblyObserver.on_agent_assembled(app_store, descriptor: AgentAssemblyDescriptor)`，在 agent 构造结束**同步**通知。descriptor 捕获已解析模型、prompt hash、授权过滤后的 tool 列表、组装好的 middleware 栈（含 policy）、deferred tool 名、启用 skills、有效 policies；其 `fingerprint` 对 tools/skills 排序但保留 middleware 顺序，并刻意排除 `build` 与 `requested_model`。
- `registry.context_compaction_observer(...)`：`ContextCompactionObserver.on_context_compacted(...)`，在 `DeerFlowSummarizationMiddleware` 仍能描述“哪些消息变成了这份摘要”的那一刻上报 `CompactionEvent`（source content hashes → output content hash + 计数）。事件以 `canonical_hash(message.content)` 键控。

### Task store

lead run 与 subagent 只有在注册了 middleware / task-lifecycle / system-model / compaction 观察时，才分配一个 `ExtensionData` task store（`needs_task_store` 预计算标志）；service 与 router 是 app-scoped，不分配。middleware 与 system-call 现场经 `EXTENSION_TASK_STORE_KEY` / `task_store_from_runtime()` 取回 live store，lifecycle contributor 直接收到同一 store。每个 task 解析一次不可变扩展快照，并把同一对象绑定到 task-store 分配、钩子、同步 agent 构造，避免并发单例替换混入两代扩展。

### 🆕 宿主侧组装投影（`agents/assembly_descriptor.py`，510 行）

`registry.agent_assembly_observer` 收到的 `AgentAssemblyDescriptor` 不是宿主随便攒的 dict——它由 `agents/assembly_descriptor.py::build_assembly_descriptor()` 从**只有工厂知道的**信息投影出来（"哪个 model 在 runtime override 之后活下来、渲染后的 prompt 到底写了什么、授权过滤后剩哪些 tool、middleware 栈最终顺序"）。两条规则写在模块 docstring 里：

1. **Declared beats probed**：实现了 `release_policy_parameters()` 的 middleware **自己拥有**行为身份；探私有属性只是没实现者的回退，并会被标记为"猜测"，让读者能区分契约与推测。
2. **Hash, do not copy**：prompt / tool description / 参数 schema 一律降成 hash。descriptor 是**身份**，不是 agent 载荷的第二份拷贝。

公开投影函数（`__all__` 恰好 4 个）：

| 函数 | 产出 | 关键行为 |
|------|------|----------|
| `describe_model_identity(value)` | `dict[str, str]` | 只取 `_MODEL_IDENTITY_FIELDS`；`_MODEL_METADATA_FIELDS`（`name`/`display_name`/`description`/`use`/`context_window`/`pricing`）是**纯展示元数据**，改名/改描述**不能**看起来像行为变化（`use` 另行以 `provider` 暴露） |
| `describe_tool(tool)` | `ToolDescriptor` | tool schema 只做 `_tool_schema()`（hash 而不是拷贝）；来源用 `_tool_source()` 区分，MCP 工具经 `tools/mcp_metadata.is_mcp_tool/get_mcp_source` 标注 |
| `describe_middleware(middleware)` | `MiddlewareDescriptor` | 先 `_unwrap_middleware()` 穿过隔离包装；有 `release_policy_parameters()` 就用声明值，否则探 `_MIDDLEWARE_PUBLIC_FIELDS`（含 `max_concurrent`/`fail_closed`/`_catalog_hash` 等），长文本字段走 `_MIDDLEWARE_HASHED_TEXT_FIELDS`（`summary_prompt`/`system_prompt`/`tool_description`）hash |
| `build_assembly_descriptor(**kwargs)` | `AgentAssemblyDescriptor` | 见下 |

`build_assembly_descriptor()` 的输入是组装期现场（`namespace`/`agent_name`/`requested_model`/`effective_model`/`model_config`/`model_overrides`/`thinking_enabled`/`reasoning_effort`/`rendered_base_prompt`/`prompt_template_id`/`tools`/`middlewares`/`deferred_names`/`enabled_skills`/`effective_policies`），产出里几个非显然点：

- **middleware 自带的 tool 折进来**：`assembled_tools = tools + [m.tools for m in middlewares]`——模型看到的 tool 集与 middleware 拥有的 tool 是同一回事。
- **skill catalog 只哈希、不逐字段列出**：每个 skill 取 `name`/`description`/排序后的 `allowed_tools`/`content_hash`/`secrets_autonomous`/排序后的 `required_secrets`，整体 `canonical_hash(sorted(catalog, key=name))` 进 `effective_policies["skill_catalog_hash"]`——改 skill 正文会改指纹，而 descriptor 保持小。
- `effective_policies` 会被补上 `prompt_template_id`（默认 `"deerflow-lead-agent-v1"`）与 `skill_catalog_hash`；`base_prompt_hash = canonical_hash(rendered_base_prompt)`；`build = _build_identity()`（包版本等）。
- `fingerprint` 的排除项（见前文"（补充）"）：对 tools/skills **排序**但**保留 middleware 顺序**，并刻意排除 `build` 与 `requested_model`——后者是"调用方想要什么"，不是"实际装配出什么"。

**消费方 ABI**：`agents/lead_agent/agent.py` 提供两个入口——`make_lead_agent(config)`（`langgraph.json` 声明的 **graph-only** ABI，签名与裸图返回类型都不能改）与 `assemble_lead_agent(config, *, app_config=None) -> LeadAgentAssembly(graph, descriptor)`。`LeadAgentAssembly` 是 2 字段 dataclass，`descriptor` **故意宽松类型**（该模块在 LangGraph Server 启动期被 import，不能把扩展契约包拖进那条 import 路径）。`unwrap_agent_graph(agent_result)` 与 dataclass 放在一起，"什么算 assembly、哪个属性放 graph"只有一个答案；它用**类型检查**而不是 duck-typing `.graph`，所以第三方/测试工厂返回裸图仍然合法（`runtime/runs/worker.py` 就这么用）。

### 🆕 通知循环（`extensions/notify.py`，500 行）

所有 extension 回调都经这一个 fail-open 派发层，规则是"**扩展故障不能弄坏宿主**"：

| 入口 | 同步/异步 | 失败语义 |
|------|-----------|----------|
| `notify_agent_assembled(descriptor)` | **同步**（agent 构造是同步的，没有 loop 可派发） | 逐 observer try/except，按注册顺序；坏 observer 不能阻止 agent 被构建 |
| `notify_task_start` / `notify_task_stop` | async | `_notify_each_on_extension_loop()` |
| `notify_system_model_call` / `observe_system_model_call` | async | 同上；`observe_system_model_call` 包住真实调用，**成功/异常/CancelledError 三条终态路径都上报**（`SystemModelResult.error` / `response` / `duration_ms`） |
| `dispatch_system_model_observation(coro, what)` | **fire-and-forget**（同步调用点用） | 提交到注册 loop |
| `notify_context_compacted(event)` | fire-and-forget | compaction 缝合点在 summarization middleware 的 `before_model`；同步半边没有 loop，异步半边不能因 observer 延迟阻塞 model-call 轮次 |

loop 生命周期（`set_extension_notify_loop(loop)` / `reset_extension_notify_loop()` / `suspend_extension_system_observations()`）：

- `_notify_loop` 是**进程级**绑定，指向"拥有扩展资源的那个 loop"；若当前 loop 就是它（或未绑定）直接 await，否则 `asyncio.run_coroutine_threadsafe` 跨 loop 派发。loop 未注册/未运行时，awaited 钩子**丢一次并记 warning**，fire-and-forget 观察只记一次 warning（`_warned_no_loop` 抑制刷屏）。
- **每个 task 一个有界预算**：`_notify_each` 用一个共享 deadline 串行调用所有 contributor，超时对尚未 await 的 coroutine 调 `close()`（避免 "coroutine was never awaited" 噪声）。
- **`CancelledError` 的区分**：若抛出方是宿主正在取消的任务（`_host_is_cancelling()` 看 `current_task().cancelling() > 0`）就**原样传播**；否则视为 observer 自己的 bug——记日志、继续通知后继者、绝不把图构造变成延迟中断。
- **shutdown 顺序**：先 `suspend_extension_system_observations()`（**拒绝新的** detached 观察，但已排队的 awaited 钩子继续 drain），再等 in-flight drain，最后 `reset_extension_notify_loop()`；`reset` 会清 `_pending_dispatches`。

task 身份/结果的分类函数（客户端语义，与 worker 的 task store 分配对齐）：

| 函数 | 规则 |
|------|------|
| `lead_task_id(run_id)` | 就是 `run_id`（**含 continuation**——同一 run 的续跑共享 task id） |
| `lead_task_outcome(*, aborted, succeeded)` | aborted → `ABORTED`；否则 succeeded → `COMPLETED`；否则 `FAILED`（保守） |
| `subagent_task_outcome(*, cancelled, succeeded)` | 同理的 subagent 版本 |

### 🆕 语义定位 → 具体下标（`extensions/anchors.py`，120 行）

`Placement.MODEL_LOGICAL/MODEL_PHYSICAL/TOOL_VISIBLE/TOOL_RAW/STANDARD` 只是**语义**声明；把它翻译成宿主 stack 的具体插入下标，是 `anchors.py` 的唯一职责——模块 docstring 明说："**这是唯一知道 DeerFlow middleware 栈形状的模块**。重构 stack 就要更新这里的 anchor 表；只声明自己需要观察什么的扩展不受影响。"

- `AnchorRule(types=..., side=...)`，`side ∈ {outer, inner, outer_last, inner_last, inner_last_after, start, end}`：`outer`/`inner` 相对**第一个**类型匹配的 middleware，`outer_last`/`inner_last` 用**最后一个**匹配项，`start`/`end` 是两端。
- 便捷构造器 `outer_of(...)` / `inner_of(...)` / `outer_of_last(...)` / `inner_of_last(...)` / `inner_of_last_after(...)` / `outermost(...)` 生成 `AnchorRule`；一个 `Placement` 对应一组按顺序尝试的规则（前一条找不到就用下一条），构成 `PlacementAnchor`。
- `injection.py::inject_middlewares(middlewares, anchors, scope, ctx, extensions, ...)` 执行插入，返回 `(合并后的 stack, 最终下标 → 扩展 source 的 provenance map, diagnostics)`——**provenance 用"最终下标"键控**，所以后续插入不会让映射失效。
- 定位失败/顺序冲突走 `extensions/ordering.py`（`OrderingConstraint` / `assert_ordering` / `core_ordering_constraints`）在**组装末尾**统一校验——不能在共享 base builder 里校验，因为 lead builder 之后还会追加 middleware，先校验的约束可能被后来的贡献反向破坏。
- 插入的 middleware 被 `IsolatedMiddleware` 包裹（`extensions/isolation.py`，`graph_safe_middleware_name`），扩展故障只发 diagnostic 并 fail-open。

## CLI 管理命令（`extensions/cli.py`）

由现有 `deerflow` console script 分派到 `deerflow extensions` 子命令，只暴露六个表面：

```text
deerflow extensions install <source> [--yes] [--required]
deerflow extensions upgrade <source> [--yes]
deerflow extensions list
deerflow extensions enable <name>
deerflow extensions disable <name>
deerflow extensions remove <name>
```

- `install` 接受本地目录、PyPI requirement、或 Git URL；非交互式确认需 `--yes`；`--required` 记录 `required: true`（否则默认 `false`）。
- 🆕 **`upgrade`（#5347，in-place upgrade）**：替换托管本地快照或重 pin 已装 requirement，**不再绕道 remove**——旧路径会丢掉 `plugins[].config` 私有配置。upgrade 保留私有 `config`、`required` 与 `enabled`；失败回滚以 staging_root 为键，快照 rename 失败不会 rmtree 活树；git 源重 pin 通过 `[tool.uv.sources]` 识别既有 plugin 记录（避免 uv 已切 revision 后 fail-closed）；对未安装的裸 `git+` URL 拒绝升级（不会退化成 install）。
- `NAME` 同时解析 entry-point 名、发行名、或 `module:install` 值。
- 根 `make extension-*` 是便捷包装，从 `backend/` 执行——本地源要用绝对 `SOURCE=`。
- 每个 mutation（install/upgrade/enable/disable/remove/config 编辑）都**需要 Gateway 重启**，因为 plugin 加载是 startup-only。

## Manager 事务与锁（`extensions/manager.py`）

`ExtensionManager` 独占包/配置事务。install 运行受控的 `uv add --project <backend> --group extensions --no-workspace --no-sync -- <source>`，更新专用 `[dependency-groups].extensions` 列表与 `uv.lock`，发现恰好一个打包 entry point，然后插入或“收养”一条托管 `plugins:` 记录（`name/package/use/enabled/required/config`）。新记录写 `required: false`；收养已有手写记录则保留 operator 原选的 `required`。

- **enable/disable** 只改宿主级 `enabled` 标志，保留私有配置。
- **remove** 跑 `uv remove --group extensions`、删 plugin 记录、删托管 source 快照。
- **失败回滚**：install/remove 失败恢复 `pyproject.toml` + `uv.lock` 并重新同步；并发外部编辑被保留并 raise（`remove` 此时只把 plugin 置为禁用）。
- **锁纪律**：同一 checkout 的所有 install/remove/enable/disable mutation 持有跨进程 `.deer-flow/extension-manager.lock`；`remove` 先停用 config 再改包声明。
- **本地目录 = 快照，不是 editable link**：校验源后复制到 `backend/extensions/sources/<distribution>/`，忽略 Git 元数据/venv/cache/字节码，拒绝符号链接、路径逃逸的发行名、疑似凭证文件。
- **源形式约束**：远程 direct reference 仅 HTTPS；远程 Git 必须 public Git-over-HTTPS（loopback HTTP 允许给本地工具）；SSH Git URL 与 SCP 简写（`git@host:org/repo.git`）被拒（stock Docker builder 不转发宿主 SSH 凭证）；相对路径与本地 wheel 走托管目录快照；`file://` 与本地 wheel 被拒（无法在 Docker build context 内复现）。含内嵌凭证的 URL 被拒。
- **锁定审计**：每次 `uv add/remove` 后审计新 lock，任何 stock 镜像 build 无法复现的本地引用（绝对路径 / `file:` / 项目根之外的相对路径）都会失败整笔事务并回滚。
- **uv 版本固定**：`backend/Dockerfile` 的 `UV_IMAGE` 是唯一事实来源，compose 与 CI 都 pin 同一版本；host uv 过旧则在 mutation 前失败。

## 信任边界：为什么只能 operator 装

🆕 **config 声明中间件的 constructor kwargs（#5312）**：`extensions.middlewares` 条目可以是类路径字符串（保持零参构造），也可以是 `{class, kwargs}` 对象。未知字段与空白 class path 在 **config 校验时**失败；构造函数报错仍在 agent 创建时失败。kwargs 在 config 加载时校验为 **JSON 类型**（YAML 时间戳被字符串化、NaN 等非 JSON 值被拒），保证构造函数与 `to_file_dict()` 的 `json.dump` 看到相同类型。

Python build hook 和扩展运行时代码都以 **Gateway 权限**执行。所以：

- 装扩展要求 CLI 确认（或显式 `--yes`），只接受可信 operator 源。
- `plugins:` 列表留在 operator 控制的 `config.yaml`（生产里 `:ro` 挂载），绝不经 HTTP 写入。
- 这些校验挡住的是常见打包事故，**不是恶意代码**——恶意代码一旦进入，导入即执行。
- `required: true` 会把后续任何加载失败（坏 wheel、缺原生库、删掉的快照）变成 Gateway 启动中止，只能靠 shell 恢复，所以它是 `install --required` 的显式 opt-in，而非托管默认。

## extension-api 契约（`packages/extension-api/`）

公开包 `deerflow-extension-api`（import 前缀 `deerflow_extension_api`）**绝不 import `deerflow`、不带框架依赖**；扩展自己声明 FastAPI/LangChain/LangGraph 依赖，因此可独立于宿主发布。当前 `API_VERSION = "0.2.1"`（`deerflow_extension_api/__init__.py:80`；参考示例里 `@extension(api="0.2.0")` 是示例声明的兼容基线，不是宿主版本）。pre-1.0：minor 可能 breaking，patch additive。

公开契约模块一览（核心 registry 在更早的 `contracts.py`）：

| 模块 | 内容 |
|------|------|
| `assembly.py` | `AgentAssemblyDescriptor` + `AgentAssemblyObserver`（组装后同步观察，含 `fingerprint`） |
| `auth.py` | `resolve_principal(request)` / `require_admin(request)`：贡献路由的中性身份投影（`ExtensionPrincipal`：user_id/is_admin/is_internal/roles），fail-closed |
| `compaction.py` | `CompactionEvent` + `ContextCompactionObserver`（lossy 上下文变换的唯一可描述时刻） |
| `provenance.py` | 消息生产者盖章：`provenance_kwargs` / `read_provenance` / `ContentKind`，键名 `deerflow_*` 为 server-owned，host 从未信输入剥离 |
| `release.py` | `ReleasePolicyProvider.release_policy_parameters()` + `canonical_json`/`canonical_hash`/`collect_release_policies`（middleware 自报行为参数，供指纹比对） |
| 🆕 `run_evidence.py`（#5405） | 只读 run evidence 契约：`RunEvidenceReader` Protocol（`list_changed_runs` cursor 增量发现 / `list_run_events` 按 thread 内单调 `seq` 前翻页 / `get_run_status`）、frozen 视图 `RunStatusView` / `RunEventView` / `RunPage` / `RunEventPage`、`InvalidRunEvidenceCursor`。宿主绑定 scope，不暴露写路径；不支持运行 evidence 的 host 直接省略该 reader。增量消费规则：只有自身输出持久化后才保存 `next_cursor`，复用输入 cursor 合法（可能重放），空页 = 已追平，无删除 tombstone，消失的 run 以 `get_run_status(...) is None` 判定。**宿主侧实现**是 `extensions/run_evidence.py::StoreRunEvidenceReader`：cursor 是 base64url 的 `{"q": change_seq, "r": run_id, "s": <scope 指纹>, "v": 1}`，解码时校验 scope 指纹（scope 的 sha256 前 16 hex），**scope 不匹配的 cursor 直接抛 `InvalidRunEvidenceCursor`**——所以 A 用户的 cursor 不能拿来推进 B 用户的 reader；读出的 metadata 经 `runtime/secret_context.redact_metadata_secrets` 处理 |

### 三个"更早的既有模块"的精确契约（v2.1.0 实测）

前面只列了名字，这里补上它们的**契约**（都是扩展包与宿主之间的公共接口，写扩展时直接用）：

**`placement.py`（70 行）——语义定位，不是结构位置**

扩展声明的是"我要保证什么"，而不是"把我放在第几层"：一个 middleware 在列表里只占一个下标，但那个下标**只对它所实现的 hook 轴有意义**——所以"outermost"在 model 轴与 tool 轴上是两件事。声明方式 = 轴 + 端点：

| `Placement` | 轴 | 保证 |
|-------------|----|------|
| `MODEL_LOGICAL` | model 外端 | 在 retry/错误处理之外；**每次逻辑决策触发一次**，不管宿主在底层重试几次 |
| `MODEL_PHYSICAL` | model 内端 | 在所有请求变换 middleware 之内；**每次物理 provider 调用触发一次**，重试会再次进入 |
| `TOOL_VISIBLE` | tool 外端 | 在截断/净化/错误包装之外，看到的是**模型最终看到的内容** |
| `TOOL_RAW` | tool 内端 | 紧邻真实 callable 边界，拿到**未经任何处理的原始返回** |
| `STANDARD` | — | 无前后处理要求；与其他 `STANDARD` 贡献者之间的相对顺序**不保证** |

配套：`MiddlewarePlacement(middleware, placement, scope=AgentScope.BOTH, order=0)` 是注入单元；`AgentBuildContext(scope, agent_name, model_name, policy)` 是扩展在 `install()` 时能看到的构建上下文；`AgentScope` 是 `Flag`（`LEAD` / `SUBAGENT` / `BOTH`）。`middleware` 字段类型是 `Any`（保持该模块 import 轻量），**类型校验由宿主在注入时做**。宿主侧把语义定位翻译成具体下标（`extensions/anchors.py`），并在组装末尾校验 ordering。

**`state.py`（57 行）——按类型键控的 per-scope 私存**

`ExtensionData` 是宿主给每个 scope（app / task）创建的实例，**按类型（而不是字符串键）索引**，所以独立扩展不会撞键；scope 结束就整体丢弃。这正是"扩展永远不需要 stale-handle 检查"的原因：每次回调都拿到**当前 scope 的** store，而不是自己捕获一个。API：`scope_id` 属性、`get(typ)`、`get_or_init(typ, init)`（`init` 在**持锁**状态下执行，可组合本 store 内其它状态，但重量级懒加载应放在"被存的对象"内部）、`set(value)`（按 `type(value)` 存）、`remove(typ)`。内部用 `RLock`。

**`runtime_bridge.py`（25 行）——扩展怎么在 graph 内取回 task store**

middleware 跑在 agent graph 里，只能经 `request.runtime` 触达宿主状态；宿主把 task store 挂在**宿主自有 key** `EXTENSION_TASK_STORE_KEY = "__deerflow_extension_task_store"` 下，扩展用 `task_store_from_runtime(runtime)` 取回来（runtime.context 不是 Mapping、或 key 不是 `ExtensionData` 时返回 `None`——即"当前没有活跃 task"）。契约要点：**扩展必须把自己的对象放进这个 store，而不是直接往 runtime context 写 key**，否则两个扩展会在 runtime-context 键上冲突。

（`contracts.py` 的 `ExtensionRegistry` / `ExtensionInstall` / `@extension` 见上表「贡献点（registry surface）」一节。）


## 与已有笔记的关系

- 🆕 v2.1.0 的两处**文档侧**事实（代码契约未变，仅 AGENTS.md 措辞/说明被校正，读代码可得同一结论）：
  - **贡献类型的措辞漂移**：根 `AGENTS.md` 的正文把打包扩展贡献写成 4 组——"middleware, lifecycle observers, Gateway services, and FastAPI HTTP routers"（v2.1.0 `#5769` 改写，删掉了旧句尾"…and FastAPI HTTP routers; the reference extension demonstrates all five"），而同一文件仓库树注释仍写 "five extension contribution kinds"。**三方事实**（用代码核实）：`ExtensionRegistry` 公开契约暴露 **7 个注册方法**（`contracts.py:192-217`：middlewares / task_lifecycle / system_model_observer / agent_assembly_observer / context_compaction_observer / service / routers），而 `examples/deerflow-extension-example/` 只注册其中 **5 个**（middleware / task lifecycle / system-model observer / service / router——缺 agent-assembly 与 context-compaction observer，见本文件「贡献点（registry surface）」一节）。所以"正文 4 组 / 树注释 5 种 / 契约 7 个"是**三套分类粒度**，不是能力增减；根文件那句"five"是特指示例包，不是契约总数。
  - **run evidence 的脱敏口径澄清**：`extensions/AGENTS.md` 由"metadata is secret-redacted"改为"metadata 只移除 legacy `auth_token` key（不存在其它脱敏）"，并写明 event content 原样返回、status 取自权威 run store；reader 把固定 scope **显式**传给事件读取（含全局 `None`），ambient 请求身份无法改变可见性；content/redacted metadata 是深拷贝快照——DTO 字段 frozen，但嵌套容器仍可局部修改而不触及宿主。
- 参考实现：`examples/deerflow-extension-example/` 一个包演示 `ExtensionRegistry` 7 个注册方法里的 5 个（middleware 计 tool call、task lifecycle 折入 app scope、system-model observer 计数、service 绑 `ExtensionRuntimeDeps`、router `GET /api/extension-example/stats`）；未演示 `agent_assembly_observer` 与 `context_compaction_observer`。
- Gateway 接线（`create_app()` 加载 plugins、`app.state.extensions`、贡献路由最后 mount、principal resolver、通知 loop）见 [../../operations/app-layer/00-overview.md](../../operations/app-layer/00-overview.md)。
- 配置面的 `plugins:` / `scheduler.recursion_limit` / `mcp_tasks` 见 [../configuration/04-config-reference.md](../configuration/04-config-reference.md)。
- middleware 的 6 种 hook 点与 `@Next`/`@Prev` 定位见 [04-agent-middleware-hooks.md](04-agent-middleware-hooks.md)。
