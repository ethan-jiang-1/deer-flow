---
title: "digest 一致性校验器"
description: "把「源码 → digest」的机械核对固化成可重复运行的脚本：文件行数、行号越界、死链、锚点、路径、环境变量、类名、module:Class、import、围栏。"
type: index
---

# digest 一致性校验器

`check_digest.py` 是 sync 的**机械层**：它不判断语义，只把"digest 里写死的、能从源码直接证伪的东西"逐条对账。语义层仍要靠人/agent 读源码（见 [SYNC.md](../SYNC.md) 的同步流程）。

## 用法

```bash
# 在仓库根运行；有问题时退出码 1
python3 _digest/_upstream-sync/tools/check_digest.py

# 连同"已声明例外"一起打印（外部库路径、示例占位符、diff 增量断言等）
python3 _digest/_upstream-sync/tools/check_digest.py -v

# 只跑某几项
python3 _digest/_upstream-sync/tools/check_digest.py --only path_exists,line_in_range
```

## 检查项

| 名称 | 查什么 |
|------|--------|
| `line_count` | `` `path`, N 行 `` 的文件长度断言（自动跳过 `+N 行`、`涨了 N 行`、`196 → 1549 行`、`第 93-100 行` 这类增量/区间写法，以及同名文件不唯一的情况） |
| `line_in_range` | `path:NNN` 是否超出文件长度 |
| `dead_link` | markdown 相对链接目标是否存在 |
| `anchor` | `file.md#section` 的目标小节是否存在（slug 保留 `_`，容忍中英文标点） |
| `path_exists` | 反引号里的路径式引用能否在源码树解析（支持裸文件名唯一匹配） |
| `env_var` | 形如环境变量的 `UPPER_CASE` 记号是否在源码/配置里出现（正则限定下划线分段 + 常见后缀，避免 mermaid 节点名误报） |
| `camel_symbol` | 反引号里的类名符号是否存在（`DeferredToolRegistry` 就是这样被抓出来的） |
| `module_class` | `deerflow.x.y:Class`：模块是否存在、类是否定义 |
| `import_stmt` | `from deerflow… import …`：模块与符号是否存在（示例代码照抄会不会报错） |
| `fence` | markdown 代码围栏是否成对 |

### 启发式检查（默认不跑，需 `--only` 显式调用）

| 名称 | 查什么 | 状态（sync #7 实测） |
|------|--------|---------------------|
| `line_symbol_strict` | 形如 `` `symbol` … `file.py:NN` `` 的紧邻引用，符号既不在 `[NN, MM]` 区间、又在文件别处 → 疑似 in-range 错行 | 21 处 → 逐条人工核对后**全部为误报**（文档常引用行区间、或一句里并列多个符号）；已支持区间与多引用跳过，降到 10 处，性质同上。仍建议每次 sync 跑一遍当作人工复核的提示 |
| `line_symbol` | 更松的版本（不要求符号紧邻引用） | 数量级过大（200+），只适合抽样，不建议全量跑 |

**结论**：`line_symbol*` 目前只作为**提示**，不进默认门禁。若要把它变成可判定的检查，需要先让文档统一"一处引用只对应一个符号"的写法。

## 使用前提与纪律

1. **先确认基线**：`ethan` 的源码应等于某个 upstream tag，例如
   `git diff v2.1.0 ethan -- . ':(exclude)_digest' ':(exclude)_faq_on_digested'` 必须为空。
2. 脚本**只读**，不会改文件；它报出的每一条都要人工判断是"文档错"还是"已声明例外"。
3. 新出现的"例外"要收敛成规则（改脚本里的 `EXTERNAL_*` / `PLACEHOLDER_*` / `IGNORE_*`），
   而不是每次忽略——否则噪声会把真问题埋掉。
4. **它抓不到的事**：语义错误、in-range 错行（行号合法但指向错误位置）、缺失内容。
   in-range 错行需要"行号处必须出现同句符号"的启发式 + 人工复核（见 UPDATE_PLAN 的遗留项）。
