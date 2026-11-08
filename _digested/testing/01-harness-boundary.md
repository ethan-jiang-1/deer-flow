---




title: "Harness/App 边界测试"
description: 'Harness/App 边界测试：架构、契约与源码锚点。'
topics: [testing, ci, quality-assurance]
verified_against: v2.2.0
last_verified: 2026-11-08
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

`backend/tests/support/detectors/blocking_io_runtime.py` — 使用 `blockbuster` 库在运行时拦截同步阻塞 IO：

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
- **用于回归测试** — `backend/tests/blocking_io/` 目录下的每个测试都被 blockbuster context 包裹

### 静态检测（AST 扫描）

`backend/tests/support/detectors/blocking_io_static.py` — AST 级别的阻塞 IO 候选扫描，不需要执行代码：

- 扫描 `Path` 方法调用（`open`、`read_text`、`write_bytes`、`mkdir`、`stat`、`unlink` 等 22 个方法）
- 扫描 `os.*` 阻塞调用（`listdir`、`makedirs`、`remove` 等）
- 扫描 `time.sleep`、`builtins.open`
- 跟踪函数调用链判断是否从 async 代码可达
- 输出 JSON 结果到 `.deer-flow/blocking-io-findings.json`，含 `priority`、`location`、`reason`、`code`

**priority 字段**：基于操作类型的确定性排序（如 `os.remove` > `Path.touch`），不是 bug 证据 — 仅辅助人工判断审查优先级。

两种检测互补：静态覆盖未测试路径，运行时验证实际执行路径。

## Blocking IO 回归锚点

`backend/tests/blocking_io/` 目录（**89 个文件**，v2.1.0 为 47）锁定的已知问题回归：

| 测试 | 锁定的修复 | 关联 issue |
|------|-----------|-----------|
| `test_skills_load.py` | `LocalSkillStorage.load_skills` 必须通过 `asyncio.to_thread` 卸载 | #1917 |
| `test_sqlite_lifespan.py` | SQLite 路径解析 + `ensure_sqlite_parent_dir` 不能在 event loop 上执行 | #1912 |

**v2.2.0 的 89 个文件已不是"两个已知问题"，而是一份模块清单**：agents / artifacts / auth / channels（buzz、dingtalk、discord、feishu、qq、wechat）/ extensions / knowledge（management + platform 两个扩展）/ mcp（router + oauth token store）/ persistence（bootstrap、sqlite engine、run journal callback）/ projects（documents、promotion、trash）/ sandbox（authorization、release、aio get）/ skills（8 个）/ subagent / uploads / web tools（URL 校验、search async ×3）。**解释**：这是本域最能说明"门禁如何从事件驱动长成制度"的证据——#1912 / #1917 之后的做法不是"修完就好"，而是每新增一个会碰磁盘或网络的模块，就顺手在 `blocking_io/` 里加一条**从真实调用点出发**的锚点。

### 元测试：gate smoke test（`backend/tests/blocking_io/test_gate_smoke.py`，4 个测试）

```python
async def test_gate_catches_unoffloaded_blocking_io_in_deerflow_module(tmp_path):
    from deerflow.runtime.store._sqlite_utils import ensure_sqlite_parent_dir
    db_file = tmp_path / "subdir" / "store.db"

    with pytest.raises(BlockingError):
        ensure_sqlite_parent_dir(str(db_file))  # 没有 asyncio.to_thread 包装
```

这个测试（`:27`）验证 gate 本身是工作的 — 如果它不再抛 `BlockingError`，说明 gate 配置出了问题（`scanned_modules` 配置错误、blockbuster 依赖被意外移除、conftest hookwrapper 失效）。它保护所有其他 blocking IO 测试免于静默失效。

🆕 **v2.2.0 新增第二条**（`:36`）——`test_gate_catches_hostname_resolution_on_the_loop`：Blockbuster 的默认规则集**包了 `socket.socket` 的方法，但没包模块级的 `socket.getaddrinfo`**，而 `deerflow.community.url_safety` 的 SSRF 守卫恰恰在 event loop 上调它解析主机名。项目因此自带一条规则（`backend/tests/support/detectors/blocking_io_runtime.py:27`）：

```python
_PROJECT_BLOCKING_RULES = (
    ("socket.getaddrinfo", BlockBusterFunction(None, "socket.getaddrinfo", scanned_modules=list(_SCANNED_MODULES))),
)

def _install_project_rules(bb: BlockBuster) -> None:   # :31
    for name, rule in _PROJECT_BLOCKING_RULES:
        bb.functions[name] = rule
```

这条测试钉住的是**"项目补的那条规则还生效"**，而不是上游库的行为——如果哪天有人重写 `detect_blocking_io_strict()` 时漏了 `_install_project_rules`，DNS 阻塞就会悄悄回到 event loop 上，而其他所有 blocking_io 测试照样绿。

另外两条：`:45` `test_gate_restores_blockbuster_patches_after_exceptions`（异常路径下 blockbuster 必须把 `os.stat` 等猴子补丁**还原**，否则一次失败会污染后续所有测试）、`:56` `test_allow_blocking_io_marker_opts_out_of_gate`（opt-out 真的生效）。**四条合起来才是完整的元测试**：抓得住 → 抓得住项目补的规则 → 退出后不污染 → 逃生门有效。

### 退出机制

```python
@pytest.mark.allow_blocking_io
async def test_allow_blocking_io_marker_opts_out_of_gate(tmp_path):
    ensure_sqlite_parent_dir(str(db_file))  # 不会触发 BlockingError
```

`@pytest.mark.allow_blocking_io` 标记禁用单个测试的 gate。用于测试那些确实需要同步 IO 的代码路径（如测试 setup 中的文件操作）。

## CI 集成

两个 gate 没有独立 step，都通过 workflow 里的 `make` 目标跑：

```yaml
# .github/workflows/backend-unit-tests.yml（job: backend-unit-tests，working-directory: backend）
# harness 边界测试是普通单测，随分片套件一起跑；matrix.shard = 1..4
- run: make test-shard SPLITS=4 GROUP=${{ matrix.shard }}

# .github/workflows/backend-blocking-io-tests.yml（job: backend-blocking-io，working-directory: backend）
- run: make test-blocking-io
```

- `make test-shard` = `uv run pytest -m "not live" --ignore=tests/blocking_io ... tests/`，所以 `backend/tests/test_harness_boundary.py` 是**分片单测的一部分**，没有专门的 "Check harness boundary" step。
- `make test-blocking-io` = `uv run pytest tests/blocking_io -q --tb=short`（`backend/Makefile:35`）。
- 触发面：unit tests 是 `push`（`main`/`*-dev`）+ 所有 PR；blocking IO 额外用 `paths: backend/**` + `.github/workflows/backend-blocking-io-tests.yml` 自身过滤（**只有后端或该 workflow 自身改动才跑**），并有 `timeout-minutes: 10` 与 `if: ... draft == false`（草稿 PR 不跑）。
- `detect-blocking-io` 是 `make detect-blocking-io` 的信息性命令，**不在 CI 中运行**（仅用于开发时手动审查）。
