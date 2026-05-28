# DeerFlow 源码研究笔记

> **核心规则：绝不碰源代码。本目录 `_digest/` 是唯一可以修改的地方。**

## 为什么不碰源代码

1. 本项目是 [bytedance/deer-flow](https://github.com/bytedance/deer-flow) 的 fork，`main` 分支的唯一职责是**跟踪上游**
2. 上游更新频繁，`main` 必须保持干净才能无冲突地 `git pull`
3. 所有研究笔记、个人理解、集成实验记录都在 `_digest/` 下，在 `ethan` 分支上独立演进
4. `ethan` 分支永远不会 merge 回 `main`，它只是一个研究工作台

**`main` = 上游镜像，`ethan` + `_digest/` = 学习空间。**

---

## `_digest` 自身质量审查 (2026-05-28)

### 严重问题：内部自相矛盾

#### 1. 中间件数量：19 还是 20？

这是整个 _digest 最严重的矛盾——两个 section 各说各的：

| 说 "20 个" 的地方 | 说 "19 个" 的地方 |
|---|---|
| `architecture/README.md` — "20 个 Middleware、5 个阶段" | `middleware/README.md` — "19 个 middleware，6 种 hook 点" |
| `architecture/01-system-overview.md:112` — "构建 20 个 middleware" | `middleware/00-overview.md:3` — "19 个 middleware" |
| `architecture/03-request-flow.md:29` — "build 20 middlewares" | `middleware/02-chain-assembly.md:70` — "19 个 middleware" |
| `architecture/04-middleware-chain.md` — 编号 1-20 | `middleware/03-catalog.md:3` — "19 个 middleware" |
| `security/03-guardrail.md:46` — "Middleware 链（共 20 个）" | `middleware/04-claude-code-comparison.md:31` — "19 个内置" |

**architecture/ section 和 middleware/ section 描述的不是同一套东西吗？为什么差一个？谁对谁错？** 如果这是一个研究项目，这个问题必须搞清楚。

#### 2. architecture/04 的 middleware 模型与 middleware/ 的完全不一致

`architecture/04-middleware-chain.md` 的 mermaid 图里出现了这些 middleware：
`SkillsPolicy`、`MemoryRead`、`ArtifactInject`、`PromptCaching`、`DateContext`、`ToolAuth`、`ToolResultValidation`

**这些名字在 middleware/03-catalog.md 的真实目录中根本不存在。** 它们是架构层的抽象/简化，但与实际代码对不上。

另外：
- architecture/04 说 "5 个阶段"（Runtime / before_model / after_model / after_tool / after_step）
- middleware/ 说 "6 种 hook 点"（before_agent / before_model / wrap_model_call / after_model / wrap_tool_call / after_step）

两套模型是**同一个人在不同时间写的**，没有统一过。

#### 3. 防御层数：7 层还是 14 层？

- `security/00-overview.md` — "7 层：Auth → Permissions → Guardrail → SandboxAudit → Tool 校验 → Sandbox 隔离 → OS"
- `security/04-trust-boundary.md` — "14 层防护"

同一个 security/ section 内就自相矛盾。只是粒度不同的两种计数方式，但读到的人会困惑。

### 结构性问题

#### 4. Section 之间几乎没有交叉引用

48 个 md 文件中，跨 section 的 markdown 链接不到 10 处。每个 section 基本是信息孤岛。

`it-ops/README.md` 有一个 "跨目录索引" 表描述了整合关系，但**它是纯文本，没有可点击的链接**。比如：

```
| `security/01-auth.md` | `01-access-control.md` |
```

这里写的是 "被整合到"，但如果读者在 it-ops/01 中看到某个点想深入了解，没有链接可以点回 security/01。

#### 5. architecture/04 和 middleware/ 是重复内容

两个 section 都在描述同一件事（中间件链），但用不同的模型、不同的名字、不同的数量。`architecture/04-middleware-chain.md` 应该要么被 middleware/ 替代并标注为废弃，要么与 middleware/ 的内容统一。

#### 6. integration/02-configuration.md 过长且位置不对

465 行，是整个 _digest 最长的单篇。它详述了 config.yaml 的所有段，但 `configuration/` section 的总篇幅才 126-152 行每篇。配置参考应该放在 configuration/，integration/ 应该只需要链接过去。

### 深浅不一

#### 7. 各 section 深度差异悬殊

| Section | 单篇行数范围 | 评价 |
|---------|-------------|------|
| middleware/ | 199-245 | 深度一致，质量高 |
| architecture/ | 128-340 | 有深有浅，subagent 340 行偏重 |
| security/ | 76-273 | guardrail 273 行很详细，但 overview 只有 76 行 |
| configuration/ | 126-152 | 均衡但偏浅 |
| integration/ | 123-465 | 严重不均衡 |
| it-ops/ | 58-148 | **整体偏浅**，部分像提纲而非分析 |
| model-layer/ | 76-132 | **偏浅**，streaming 只有 96 行 |

#### 8. it-ops/ 的形式像 checklist，不是 deep dive

`it-ops/02-sandbox-governance.md`（82 行）和 `it-ops/03-policy-enforcement.md`（112 行）写得像安全评估的 checklist，缺少 middleware/ 或 security/ 中那种 "为什么会这样设计" 的深层分析。

但 `it-ops/00-overview.md` 的 12 维度成熟度模型是全 _digest 最有价值的内容之一。形成了鲜明反差——overview 很惊艳，展开篇却浅了。

#### 9. model-layer/ 太薄

96 行的 streaming、132 行的 thinking/vision——这两个都是值得深挖的话题。streaming 涉及到 per-provider chunk 归一化（5 个 provider 各有各的 hack），这个复杂度不是 96 行能讲清楚的。

### 图表覆盖不均

| Section | SVG 数量 |
|---------|---------|
| architecture/ | 8 |
| middleware/ | 4 |
| security/ | 4 |
| configuration/ | 2 |
| it-ops/ | 2 |
| model-layer/ | 1 |
| integration/ | 1 |

IT-ops 的 defense-in-depth.svg 和 it-governance-overview.svg 是重复 security/ 里的图（security-defense-in-depth.svg 说的是同一件事）。

### 做得好的地方

- **middleware/ section 整体质量最高**：批判性分析（00）、hugo 点详解（01）、对比分析（04）都是好内容
- **每个 section 的 README 有阅读顺序 + 关键问题表**：这个 UX 模式很一致，值得保持
- **架构图的清晰度**：SVG 图本身质量高
- **it-ops/00 的行业对标和成熟度模型**：作为一个研究项目，把 DeerFlow 放在 Gartner/Deloitte/EU AI Act 的语境里讨论，给出了超出代码本身的价值

---

## 建议后续工作

### 立即修复（消除内部矛盾）

1. **确定中间件确切数量**：以 middleware/03-catalog.md 为 anchor，统一所有引用
2. **淘汰或重写 architecture/04**：它和 middleware/ section 说的是同一件事但用不同模型，要么标为废弃指向 middleware/，要么与 middleware/ 的内容对齐
3. **统一防御层数表述**：决定用 7 层（粗粒度）还是 N 层（细粒度），全文统一
4. **给 it-ops/README 的跨目录索引加上真实 markdown 链接**

### 结构优化（打破信息孤岛）

5. **在 section 之间加交叉引用**：security/ 提到 sandbox 时链接到 architecture/06-sandbox.md；middleware/ 提到 guardrail 时链接到 security/03-guardrail.md
6. **拆分 integration/02-configuration.md**：配置参考归 configuration/，integration/ 只保留接入视角的配置说明
7. **it-ops/ 每篇补充深度**：目前 58-148 行的篇幅不足以支撑 "IT 治理" 这个标题承诺的深度

### 填补空白

8. **新建 `frontend/` section**：目前 architecture/11-frontend.md 是唯一的涉前端的文章，但浅尝辄止。需要一个独立 section 深入前端的状态管理、stream 管线、组件树
9. **新建 `channels/` section**：7 个 IM 平台的对接是一个有相当复杂度的子系统（消息总线、dispatch loop、per-platform stream 策略），目前 integration/07-im-channels.md 覆盖了一些但不够深
10. **新建 `deployment/` section**：本地 dev / Docker dev / Docker prod / K8s 四种部署模式的技术分析
11. **新建 `testing/` section**：测试策略、blocking_io 门控设计、harness boundary test 机制
12. **✅ 新建 `agent-loop/` section**（2026-05-28）：agent loop 的技术内核——谁在循环、middleware 怎么嵌入 loop、从哪些点往外扩。这是之前 research dimensions 里缺失的 "core"

---

## 研究维度

| 维度 | 回答的问题 | 状态 |
|------|-----------|------|
| **Architecture** | 内部怎么设计的？核是什么，外围怎么挂？ | 11 篇 + 8 图（但有自相矛盾） |
| **Integration** | 怎么接入使用？API / SDK / Docker / IM？ | 8 篇 + 1 图 |
| **Configuration** | 两套配置文件、热加载、动态模块加载 | 4 篇 + 2 图 |
| **Middleware** | Agent Loop 的多层中间件，多种 hook 点 | 5 篇 + 4 图（质量最高） |
| **Security** | 从 prompt 到 `rm -rf /` 之间的防护 | 5 篇 + 4 图 |
| **Model Layer** | 换模型不改代码？thinking/vision 怎么统一？ | 3 篇 + 1 图（偏薄） |
| **IT/Ops** | IT 管理者视角的治理与风险 | 6 篇 + 2 图（overview 惊艳，展开偏浅） |
| **Frontend** | 前端架构、状态管理、Stream 管线 | **缺失**（仅 architecture/11 简略提及） |
| **Channels** | IM 平台对接的内部设计 | **缺失** |
| **Deployment** | 本地/Docker/K8s 部署模式 | **缺失** |
| **Agent Loop** | agent loop 的技术内核：谁循环、middleware 怎么嵌入、怎么外扩 | **新建** 3 篇（2026-05-28） |
| **Testing** | 测试策略、blocking_io 门控、e2e mock | **缺失** |

## 目标目录结构

```
_digest/
├── README.md                      # 本文件
├── architecture/                  # 内部设计（需与 middleware/ 统一）
├── integration/                   # 接入指南
├── configuration/                 # 配置与扩展
├── security/                      # 安全边界
├── middleware/                    # Agent 中间件体系（质量最高）
├── model-layer/                   # LLM 抽象（需加深）
├── it-ops/                        # IT 治理（需加深展开篇）
├── agent-loop/                    # Agent Loop 技术内核（新建）
├── frontend/                      # [待建] 前端架构
├── channels/                      # [待建] IM 通道系统
├── deployment/                    # [待建] 部署架构
└── testing/                       # [待建] 测试策略
```

## 工作流

- 切到 `ethan` 分支工作：`git checkout ethan`
- 研究过程中发现值得记录的内容 → 写入 `_digest/` 对应目录
- 定期回到 `main` 拉上游：`git checkout main && git pull upstream main`
- 需要时把上游的新变更 merge 到 `ethan`：`git checkout ethan && git merge main`

## 上游信息

- 仓库：https://github.com/bytedance/deer-flow
- 协议：MIT
- 技术栈：Python 3.12+ / Node.js 22+ / LangGraph / Next.js 16
