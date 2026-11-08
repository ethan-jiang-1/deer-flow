---
title: "digest 一致性校验器"
description: "把「源码 → digest」的机械核对固化成可重复运行的脚本：文件行数、行号越界、死链、锚点、路径、环境变量、类名、module:Class、import、围栏。"
type: index
topics: [digest, validation, tooling]
---

# digest 一致性校验器

> **定位**：`check_digest.py` 是 sync 的**机械层**——把「源码 → digest」里可证伪的断言（行数、行号、死链、锚点、路径、环境变量、类名、`module:Class`、import、围栏）固化成可重复运行的只读脚本；给执行同步或修改 digest 的人自查。
> **边界**：不判断语义，也不替代读源码；语义层与同步流程见 [../SYNC.md](../SYNC.md)，最新一轮的验收与遗留项见 [../UPDATE_PLAN_8.md](../UPDATE_PLAN_8.md)。

## 阅读路径

1. **先看**：[check_digest.py](check_digest.py) — 从文件头 docstring 与 `--only` 列表看十项检查的边界。
2. **再看**：[../SYNC.md](../SYNC.md) — 机械层在「重建同步」流程中的位置与门禁含义。
3. **深入**：[../UPDATE_PLAN_8.md](../UPDATE_PLAN_8.md) — 最新同步的验收判据，以及「脚本抓不到的事」清单。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [check_digest.py](check_digest.py) | 十项机械检查 + 两项启发式；默认只读、有问题时退出码 1 | 深入 |

本目录没有其他 `.md` 正文页；检查项、启发式与使用纪律见下方「宪章与约定」。

## 宪章与约定

- 先确认基线：`ethan` 源码应等于某个 upstream tag（如 v2.2.0），否则校验结果无法解释。
- 检查项分三组：默认机械检查（行数 / 行号 / 死链 / 锚点 / 路径 / 环境变量 / 类名 / `module:Class` / import / 围栏）、需 `--only` 的启发式（`line_symbol_strict` / `line_symbol`）、声明式例外。
- 运行：`python3 _digested/_upstream-sync/tools/check_digest.py`；`-v` 打印已声明例外；`--only path_exists,line_in_range` 只跑指定项。
- 只读：脚本不改文件；每条命中都要人工判断是「文档错」还是「已声明例外」，新例外收敛进 `EXTERNAL_*` / `PLACEHOLDER_*` / `IGNORE_*`，不要每次忽略。
- `line_symbol*` 只是提示、不进默认门禁；它抓不到语义错误与 in-range 错行（行号合法但指向错误位置）。
- 本目录无独立宪章；写作纪律沿用 [根 README](../README.md)。

## 相关目录

- [../README.md](../README.md) — 上游同步索引：锚点、流程与更新计划。
- [../SYNC.md](../SYNC.md) — 完整同步命令与「三目录之外必须 0 差异」铁律。
- [../UPDATE_PLAN_8.md](../UPDATE_PLAN_8.md) — 最新一轮计划、基线问题与验收标准。
