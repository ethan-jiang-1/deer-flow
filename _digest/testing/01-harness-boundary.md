# Harness/App 边界测试

`backend/tests/test_harness_boundary.py` — CI 强制执行两层的 import 边界。

## 为什么需要这个测试

DeerFlow 采用 Harness/App 两层架构：
- **Harness（`backend/packages/harness/`）：** 框架层，可独立发布和测试
- **App（`backend/app/`）：** 应用层，依赖 Harness

这个边界的存在是为了：
1. Harness 可以作为独立包发布（`deerflow` 在 PyPI 上）
2. App 层代码不需要被 fork 用户保留（用户可以替换整个 App 层）
3. CI 可以单独测试 Harness 而不启动整个应用

边界规则：**Harness 不能 import App 的任何东西。**

## AST 分析机制

测试使用 Python 的 `ast` 模块静态分析 import 语句（不执行代码）：

```python
def test_no_app_imports_in_harness():
    harness_dir = Path("backend/packages/harness")
    for py_file in harness_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app."), \
                        f"{py_file}: imports app module '{alias.name}'"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith("app."), \
                        f"{py_file}: imports from app module '{node.module}'"
```

## 豁免机制

少量 Harness 文件需要引用 App 层（如测试辅助代码、shared test fixtures）：

```python
# harness-boundary: allow
from app.channels.test_helpers import mock_inbound_message
```

AST 扫描会检查 `# harness-boundary: allow` 注释——带有此注释的 `import app.` 语句被跳过。

CI 流程中对豁免数量设置上限——防止豁免泛滥。

## CI 集成

在 GitHub Actions（或等效 CI）中：

```yaml
- name: Check harness boundary
  run: |
    pytest backend/tests/test_harness_boundary.py -v
    # 如果有新的非豁免 app import → CI 红
```

## 测试覆盖范围

| 检查项 | 说明 |
|--------|------|
| `import app.X` | Harness 文件 import app 包 |
| `from app.X import Y` | Harness 文件从 app 包导入 |
| 循环依赖 | Harness 内部 import 方向错误 |
| 豁免审计 | 豁免数量、豁免文件的合理性 |

这个测试的存在意味着：任何开发者在 Harness 中写了 `from app.xxx import yyy`，在 PR 阶段就会失败——防止边界腐蚀。
