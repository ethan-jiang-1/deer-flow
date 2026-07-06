---
title: "Harness/App 边界测试"
description: "`backend/tests/test_harness_boundary.py` — CI 强制执行两层 import 边界。"
topics: [testing, ci, quality-assurance]
---

# Harness/App 边界测试

`backend/tests/test_harness_boundary.py` — CI 强制执行两层 import 边界。

## 为什么需要这个测试

DeerFlow 采用 Harness/App 两层架构：
- **Harness**（`backend/packages/harness/deerflow/`）：框架层，可独立发布为 `deerflow-harness` 包
- **App**（`backend/app/`）：应用层，依赖 Harness

边界规则：**Harness 不能 import App 的任何东西。** 任何开发者在 Harness 中写了 `from app.xxx import yyy`，PR 阶段就会 CI 失败。

## AST 扫描实现

```python
HARNESS_ROOT = Path(__file__).parent.parent / "packages" / "harness" / "deerflow"
BANNED_PREFIXES = ("app.",)

def _collect_imports(filepath: Path) -> list[tuple[int, str]]:
    """返回 (行号, 模块路径) """
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                results.append((node.lineno, node.module))
    return results

def test_harness_does_not_import_app():
    violations = []
    for py_file in sorted(HARNESS_ROOT.rglob("*.py")):
        for lineno, module in _collect_imports(py_file):
            if any(module == prefix.rstrip(".") or module.startswith(prefix)
                   for prefix in BANNED_PREFIXES):
                violations.append(f"  {py_file}:{lineno}  imports {module}")
    assert not violations, \
        "Harness layer must not import from app layer:\n" + "\n".join(violations)
```

关键设计决策：
- **静态分析，不执行代码** — 使用 `ast.parse()` 而非 import 机制，不受运行时状态影响
- **`SyntaxError` 静默跳过** — 语法错误的文件不阻塞扫描（可能是有意为之的 Python 版本门控）
- **`rglob("*.py")` 全覆盖** — 扫描所有 Python 文件，包括 `__init__.py`、测试文件、脚本
- **排序输出** — `sorted()` 确保 CI 输出确定性，方便逐行对比

## 对比：无豁免机制

与 CLAUDE.md 描述不同，当前 `test_harness_boundary.py` **没有 `# harness-boundary: allow` 豁免注释机制**。代码中无豁免逻辑 — 任何 `import app.` 或 `from app.` 在 Harness 目录下都会被标记为违规。这比豁免机制更严格，也更简单。

## Blocking IO 双层检测体系

除了 import 边界，DeerFlow 还有两套 blocking IO 检测工具：

### 运行时检测（Blockbuster）

`tests/support/detectors/blocking_io_runtime.py` — 使用 `blockbuster` 库在运行时拦截同步阻塞 IO：

```python
_SCANNED_MODULES = ("app", "deerflow")

@contextmanager
def detect_blocking_io_strict() -> Iterator[BlockBuster]:
    bb = BlockBuster(scanned_modules=list(_SCANNED_MODULES))
    bb.activate()
    try:
        yield bb
    finally:
        bb.deactivate()
```

- **`scanned_modules=("app", "deerflow")`** — 只在业务代码栈中检测，pytest/langchain/第三方库不在范围内
- **范围精确** — 仅当调用栈经过 `app.*` 或 `deerflow.*` 时 `BlockingError` 才会触发
- **用于回归测试** — `tests/blocking_io/` 目录下的每个测试都被 blockbuster context 包裹

### 静态检测（AST 扫描）

`tests/support/detectors/blocking_io_static.py` — AST 级别的阻塞 IO 候选扫描，不需要执行代码：

- 扫描 `Path` 方法调用（`open`、`read_text`、`write_bytes`、`mkdir`、`stat`、`unlink` 等 22 个方法）
- 扫描 `os.*` 阻塞调用（`listdir`、`makedirs`、`remove` 等）
- 扫描 `time.sleep`、`builtins.open`
- 跟踪函数调用链判断是否从 async 代码可达
- 输出 JSON 结果到 `.deer-flow/blocking-io-findings.json`，含 `priority`、`location`、`reason`、`code`

**priority 字段**：基于操作类型的确定性排序（如 `os.remove` > `Path.touch`），不是 bug 证据 — 仅辅助人工判断审查优先级。

两种检测互补：静态覆盖未测试路径，运行时验证实际执行路径。

## Blocking IO 回归锚点

`tests/blocking_io/` 目录锁定了两个已知问题的回归：

| 测试 | 锁定的修复 | 关联 issue |
|------|-----------|-----------|
| `test_skills_load.py` | `LocalSkillStorage.load_skills` 必须通过 `asyncio.to_thread` 卸载 | #1917 |
| `test_sqlite_lifespan.py` | SQLite 路径解析 + `ensure_sqlite_parent_dir` 不能在 event loop 上执行 | #1912 |

### 元测试：gate smoke test

```python
async def test_gate_catches_unoffloaded_blocking_io_in_deerflow_module(tmp_path):
    from deerflow.runtime.store._sqlite_utils import ensure_sqlite_parent_dir
    db_file = tmp_path / "subdir" / "store.db"

    with pytest.raises(BlockingError):
        ensure_sqlite_parent_dir(str(db_file))  # 没有 asyncio.to_thread 包装
```

这个测试验证 gate 本身是工作的 — 如果它不再抛 `BlockingError`，说明 gate 配置出了问题（`scanned_modules` 配置错误、blockbuster 依赖被意外移除、conftest hookwrapper 失效）。它保护所有其他 blocking IO 测试免于静默失效。

### 退出机制

```python
@pytest.mark.allow_blocking_io
async def test_allow_blocking_io_marker_opts_out_of_gate(tmp_path):
    ensure_sqlite_parent_dir(str(db_file))  # 不会触发 BlockingError
```

`@pytest.mark.allow_blocking_io` 标记禁用单个测试的 gate。用于测试那些确实需要同步 IO 的代码路径（如测试 setup 中的文件操作）。

## CI 集成

```yaml
# .github/workflows/backend-unit-tests.yml
- name: Check harness boundary
  run: pytest backend/tests/test_harness_boundary.py -v

# .github/workflows/backend-blocking-io-tests.yml  
- name: Blocking IO runtime gate
  run: pytest backend/tests/blocking_io/ -v
```

两个 gate 都在 PR 时硬失败。`detect-blocking-io` 是 `make detect-blocking-io` 的信息性命令，**不在 CI 中运行**（仅用于开发时手动审查）。
