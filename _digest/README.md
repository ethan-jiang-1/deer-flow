# DeerFlow 源码研究笔记

Upstream: [bytedance/deer-flow](https://github.com/bytedance/deer-flow)

## 目录结构

```
_digest/
  README.md          # 本文件
  architecture/      # 整体架构、设计模式、数据流分析
  modules/           # 各模块/包的源码阅读笔记
  notes/             # 零散发现、待深入的点、TODO
```

## 研究目标

- 理解 DeerFlow 的 super agent harness 设计
- 梳理 sub-agent、memory、sandbox、skill 等核心机制的实现
- 跟踪上游的变化，记录关键 commit/diff 的理解
