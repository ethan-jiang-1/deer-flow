# SDLC Reference 目录

## 定位

参考层（reference）。**这里查的是"DeerFlow 眼里的 SDLC"的精确条款**——不是通用 SDLC 知识手册，而是 DeerFlow 主仓库对变更主线的立场落到条文与门禁的形态，面向两类读者：向主仓贡献变更的人核对条件与例外；独立应用仓的维护者判断哪些机制值得移用。

每条规则标明它的执行等级：**成文标准**（指南与模板写明）、**机器门禁**（CI workflow 或测试自动执行、能挡住合并或发布）、**仓库外不可核实**（如分支保护与人工批准，不在仓库文件里）。把指南要求当作已被 CI 强制，是读主仓制度时最容易犯的过度概括。

卷名 "SDLC Reference" 是本语料自己的视角命名——DeerFlow 仓库自身不使用 "SDLC" 一词（对 tag 核验为零命中）；本卷是对主仓可观察机制的综合表述，不是官方方法名。

## 主入口

从 [00-index.md](./00-index.md) 按问题选择页面。该页拥有组织立场与完整参考目录；本 `README.md` 只说明本卷职责。

## 直接内容

| 路径 | 职责 |
|---|---|
| [00-index.md](./00-index.md) | 组织立场、按生命周期的页面目录与使用方式 |
| [01-intent-and-scope.md](./01-intent-and-scope.md) 至 [10-extension-trust-boundaries.md](./10-extension-trust-boundaries.md) | 意图与范围、spec 权威、TDD 与测试套件、PR 表面与 AI 披露、CI 门禁矩阵、架构/文档/工具链契约、发版版本门、迁移链、运维反馈与失败回写、扩展信任边界 |

## 图文分工

正文拥有条款与例外，图只辅助表达。一张 SVG 说明变更主线与每阶段的门禁等级；由本卷自己的[图示清单](./figures/README.md)管理，不依赖相邻卷的图。本目录独立依据 DeerFlow v2.1.0 一手来源；[应用开发模型](../application-development-model/README.md)提供关系综合，[Development Harness](../repo-harness/README.md)说明仓库怎样帮助 coding agent 参与自身，都不是本卷的阅读前提。
