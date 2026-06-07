# FAQ on Digested

基于 `_digest/` 消化后的知识，回答具体问题。每个问题一个子目录。

## 结构

```
_faq_on_digested/
├── README.md                  # 本文件
└── <question-slug>/           # 一个问题一个子目录
    └── README.md              # 答案 + 相关源码引用
```

## 规则

1. **答案必须引用 `_digest/` 下的笔记**作为知识基础
2. **答案必须引用源代码**的具体文件和行号作为证据
3. **不重复**已在 digest 中写过的内容——指向它而不是复制
4. 如果问题涉及 DeerFlow 之外的系统（如 Codex、Claude Code），标注来源

## 已答问题

| # | 问题 | 子目录 |
|---|------|--------|
| 1 | Skill 选取精度：skill 太多时 LLM 选择不准，DeerFlow 现状是什么？Codex 怎么解的？ | [skill-selection-accuracy/](skill-selection-accuracy/) |
| 2 | 任务 MD 文件能否精确指定 Skill？"长城任务"里写了用哪个 skill，能保证选中吗？ | [command-skill-linkage/](command-skill-linkage/) |
| 3 | 企业自主静默执行中如何精准选择 Skill？现有环境有什么可用积木？ | [precise-skill-selection/](precise-skill-selection/) |
