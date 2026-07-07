# FAQ on Digested

基于 `_digest/` 消化后的知识，回答具体问题。每个问题一个子目录。

## 目录规范

```
_faq_on_digested/
├── README.md                  # 本文件（规范定义）
└── <question-slug>/           # 一个问题一个子目录
    ├── question.md            # 必须：用户问了什么（标题 + blockquote）
    ├── answer.md              # 必须：回答（核心结论 + 分析）
    └── <detail>.md            # 可选：复杂回答的补充细节文件
```

### 文件约定

| 文件 | 必须？ | 内容 |
|------|--------|------|
| `question.md` | ✅ | `# Q{n}: {简短标题}` + blockquote 中的完整问题 |
| `answer.md` | ✅ | 回答主体：核心发现、分析、结论。末尾列出相关 digest 笔记和源码引用 |
| `*.md`（其他） | 可选 | 当 answer.md 过长时，将独立章节拆为 detail 文件。answer.md 末尾链接到它们 |

### 规则

1. **答案必须引用 `_digest/` 下的笔记**作为知识基础
2. **答案必须引用源代码**的具体文件和行号作为证据
3. **不重复**已在 digest 中写过的内容——指向它而不是复制
4. 如果问题涉及 DeerFlow 之外的系统（如 Codex、Claude Code），标注来源

## 已答问题

| # | 问题 | 子目录 |
|---|------|--------|
| 1 | Skill 选取精度 | [skill-selection-accuracy/](skill-selection-accuracy/) |
| 2 | 任务 MD 与 skill 联动 | [command-skill-linkage/](command-skill-linkage/) |
| 3 | 企业静默执行 skill 选择 | [precise-skill-selection/](precise-skill-selection/) |
| 4 | MCP 工具管理 | [mcp-best-practices/](mcp-best-practices/) |
| 5 | 入门指南 | [getting-started-first-flow/](getting-started-first-flow/) |
| 6 | CLI/SDD 协作 | [cli-and-sdd/](cli-and-sdd/) |
| 7 | Agent 图两个固定 Node | [graph-nodes/](graph-nodes/) |
| 8 | Middleware 就是 Node | [middleware-as-nodes/](middleware-as-nodes/) |
| 9 | 扩展 ThreadState | [custom-state-and-reducers/](custom-state-and-reducers/) |

## 配方（Recipe）

| 名称 | 文件 |
|------|------|
| 自动化代码审查 Bot | [automated-code-review-bot.md](automated-code-review-bot.md) |
