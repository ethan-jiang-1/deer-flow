# 数据迁移链

## 什么时候读这里

应用持久化了数据、要跨版本升级时：DeerFlow 主仓怎么治理 schema 变更。对内嵌 DeerFlow 的应用仓，这页同时回答"DeerFlow 自己的迁移怎么影响我的部署"。

## 主仓机制

**每个 ORM 变更必须带 revision（成文标准）**：

> every ORM model change (new column, new table, new index) MUST ship as an alembic revision under `migrations/versions/`.
>
> — [migrations/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/persistence/migrations/AGENTS.md)

**启动即升级，不设手工命令（成文标准 + 运行时事实）**。Gateway 启动时自动 `alembic upgrade head`，常规生产升级不需要手工 Alembic 命令——仓库**刻意不提供** `make migrate` / `make migrate-stamp` 目标，防止"部署时忘了跑迁移"这类人为失误存在于流程中：

> There is no `make migrate` / `make migrate-stamp` target on purpose — routine upgrades execute at Gateway startup.
>
> — [migrations/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/persistence/migrations/AGENTS.md)

**只追加的修订链（成文标准，事故回写）**。新 revision 只能接在当前 head 之后，**不许插到已发布 revision 之前**——alembic 只从已 stamp 的版本向前走，插队的 revision 会被既有数据库当作已执行的祖先而永远不跑。这条规则后面跟着真实事故：`0023_run_change_seq` 插队导致既有库缺 schema，靠 `0025_repair_run_change_seq` 修复——事故本身已回写为修复 migration 与回归测试。

**未知状态拒绝启动（运行时事实）**。bootstrap 对数据库状态分类处理：空库建表并 stamp head；遗留库回填基线后升级；**未知 revision、空版本表或多版本行一律 fail-closed 拒绝启动**。确实需要离线修复的罕见情形，恢复文档要求停掉所有写入者、先备份、逐步核验确切 schema 形态再操作，且该恢复路径有回归测试钉住（[database-forward-revision-recovery.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/database-forward-revision-recovery.md)）。

**机器门禁**：迁移测试随单测套件执行（无独立 migration workflow）。**边界**：迁移正确性的完整证明依赖部署启动成功——"fail-closed"保证不会带病运行，但升级失败的恢复仍是 operator 责任。

## 应用仓适用边界

**对内嵌 DeerFlow 的应用仓**：宿主迁移由 `bootstrap_schema` 在持久化引擎初始化时执行；内嵌形态下是否在你部署中触发、何时触发，取决于你的存储与初始化配置——部署前按迁移指南核验自己的实际路径，不要假设"嵌入即自动升级"。你自己的表**不要**注册进宿主的 `Base.metadata`——扩展自有表要按 extensions 指南的约定用独立 `MetaData` + 表前缀 + 独立 alembic 链，否则宿主空库 `create_all` 会替没启用扩展的部署建出你的表。**可移用**："只追加 + 启动即升级 + 未知状态拒绝启动"三件套是应用仓自有数据同样值得采用的升级安全模型；事故回写成修复 migration + 回归测试的做法也一样。**需要自定**：多实例并发启动时用 Postgres advisory lock（主仓做法）或等效机制串行化升级。

## 证据入口

- [migrations/AGENTS.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/backend/packages/harness/deerflow/persistence/migrations/AGENTS.md)（Convention / Hybrid bootstrap / Authoring / Extension-owned tables 各节）
- [database-forward-revision-recovery.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/docs/database-forward-revision-recovery.md)（离线恢复的审计流程）
