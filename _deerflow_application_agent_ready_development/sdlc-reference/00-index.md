# SDLC Reference · 精确机制与例外流程

## 什么时候读这里

这里是 SDLC Reference（软件开发生命周期的精确参考），面向需要核对 DeerFlow 主仓精确条件、门禁等级或少见流程的读者。各页支持按问题查找，不要求顺序通读。独立应用仓可以参考这些机制，但不因依赖 DeerFlow 就继承主仓的 PR 制度、CI 矩阵、发版流程或迁移治理。

本目录直接回答"具体由哪个文件执行""边界条件是什么""失败后怎样处理"。需要关系综合时可选读[应用开发模型](../application-development-model/README.md)。

## 组织立场

本卷从 DeerFlow v2.1.0 的一手指南、模板、workflows 与测试归纳出三条组织立场（综合表述，不是官方方法名）：

1. **声明与机器执行严格分层。** 成文标准（AGENTS.md、PR 模板、贡献指南）说明要求；机器门禁（lint workflow、分片单测、路径触发的专项检查、发版版本门）才真正阻断；二者之间还有一层"自我声明"（PR 表单里填写的验证结果与 AI 披露）。读任何一条规则先问它在哪一层。
2. **设计决策有唯一产权。** 大变更走 RFC/spec/plan 分级：spec 拥有全部设计决策并自带测试策略、文档清单与评审检查单；实现计划只负责排序文件与验证，无权重新设计；偏离登记在 spec 的 deviation register。
3. **证据高于状态灯。** 测试绿、CI 绿、merge、release 各自只证明其执行的断言；评审哲学要求读当前 diff 与证据本身，而不是沿绿灯放行。事故被回写成测试、门禁或契约，学习沉淀在仓库而非个人记忆。

## 参考目录

| 页面 | 适用问题 |
|---|---|
| [01-intent-and-scope.md](./01-intent-and-scope.md) | 意图从哪里进来；非平凡变更为什么先对齐范围 |
| [02-spec-and-plan.md](./02-spec-and-plan.md) | spec 与实现计划的产权分工；deviation register；切片推进 |
| [03-tdd-and-test-lanes.md](./03-tdd-and-test-lanes.md) | TDD 成文要求；offline/blocking-io/live 车道划分与 opt-in |
| [04-pr-surface-and-ai-disclosure.md](./04-pr-surface-and-ai-disclosure.md) | PR 模板的用户视角描述、信任自检、AI 披露与人的责任声明 |
| [05-ci-gates.md](./05-ci-gates.md) | 实际 workflow 矩阵：触发路径、draft 跳过、分片、安装路径证明 |
| [06-architecture-docs-contracts.md](./06-architecture-docs-contracts.md) | 架构边界测试、指南预算 CI、文档示例进测试、工具链版本钉住 |
| [07-release-and-version-gate.md](./07-release-and-version-gate.md) | tag 驱动发版；版本五源一致门禁；nightly 的例外 |
| [08-schema-migrations.md](./08-schema-migrations.md) | 只追加的迁移链；启动自动升级；fail-closed 与离线恢复 |
| [09-operational-feedback.md](./09-operational-feedback.md) | support bundle；agent 评审的边界；失败→机制的回写实例 |
| [10-extension-trust-boundaries.md](./10-extension-trust-boundaries.md) | 插件装载的 operator 信任边界；哪些义务会传导到应用仓 |

按生命周期找页：意图入口读 `01`；决定与实现读 `02`–`04`；门禁读 `05`–`06`；落地与发布读 `07`–`08`；运维与边界读 `09`–`10`。

## 使用方式

按问题进入一篇对应 reference；页面末尾的"证据入口"链接到 owning 指南、模板、workflow 或测试（全部钉定 v2.1.0）；需要判断主仓事实时以这些来源为准。各页的"适用边界"段落回答"应用仓能不能搬这条"，搬动时应说明自己的可观察结果与验证方式。
