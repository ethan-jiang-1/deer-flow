# 从零搭建：新建一个干净 repo

> **这是参考手册，不是已执行的步骤。** 本 FAQ 只记录方案，不会动任何仓库。动手时按此执行，先备份。
>
> 目标 repo 名字先用 `deerflow-research/` 占位，你定夺后全局替换。

## Phase 0：清单——从哪个旧仓搬什么

| 内容 | 从哪搬 | 去向 |
|------|--------|------|
| 你的应用代码 | `ai_deerflow_deep_research/deep_research_harness/` | `harness/` |
| 设计规格 | `ai_deerflow_deep_research/openspec/` | `openspec/` |
| 技能 | `ai_deerflow_deep_research/skills/` | `skills/` |
| 任务 | `ai_deerflow_deep_research/_backlog/` | `_backlog/` |
| 笔记 | `deer-flow/_digest/` + `_faq_on_digested/`（**最新版**） | `reference/_digest/` + `reference/_faq_on_digested/` |
| 运行时 | `ai_deerflow_deep_research/backend/`（对应 4915b5e） | **不搬文件，改用 submodule** |

> 旧仓全部保持原样当参考，一个都不删。

## Phase 1：建仓 + 加 submodule

```bash
mkdir deerflow-research && cd deerflow-research
git init

# 加 deer-flow 为 submodule，钉在你现在跑得通的版本（4915b5e）
git submodule add https://github.com/bytedance/deer-flow.git deerflow
cd deerflow && git checkout 4915b5e && cd ..
# 写清钉的版本，方便将来换
echo "deerflow pinned @ 4915b5e (harness 当前跑通的版本)" >> deerflow/README 2>/dev/null || true
```

**【验证点】** `ls deerflow/backend/packages/harness` 存在；`git submodule status` 显示钉在 4915b5e。

> 为什么钉 4915b5e 而不是 e5c62cab：你的 harness 现在 editable 装的就是这份（5 个代表文件比对一致）。钉它 = 行为零变化。将来想升级到 e5c62cab 是另一次有意动作。

## Phase 2：搬入你的内容

```bash
# 你的应用代码 → harness/
cp -r ../ai_deerflow_deep_research/deep_research_harness ./harness
# 删掉 harness 里带过来的 venv / 缓存（不该进 git）
rm -rf harness/.venv harness/.pytest_cache harness/.ruff_cache harness/src_fake

# 规格 / 技能 / 任务
cp -r ../ai_deerflow_deep_research/openspec ./openspec
cp -r ../ai_deerflow_deep_research/skills ./skills
cp -r ../ai_deerflow_deep_research/_backlog ./_backlog

# 笔记（取最新版，来自 deer-flow 而非过期的 wiki）
mkdir -p reference
cp -r ../deer-flow/_digest ./reference/_digest
cp -r ../deer-flow/_faq_on_digested ./reference/_faq_on_digested

# 笔记里写明版本差
cat > reference/README.md <<'EOF'
本 reference 是对 DeerFlow 的研究笔记。
- 笔记锚点：e5c62cab（digest sync #4）
- 运行时：deerflow/ submodule @ 4915b5e
- 两者差一个大版本，已知、暂不对齐。
EOF
```

## Phase 3：接线——让 harness 照跑

关键：**复刻现在的 editable 机制，只是路径换到 submodule**。

```bash
cd harness
uv sync          # 或 python -m venv .venv && .venv/bin/pip install -e .
# 把 deerflow-harness editable 装到 submodule 源码上：
#   方案 A：直接装
.venv/bin/pip install -e ../deerflow/backend/packages/harness
#   方案 B：pyproject 里写路径依赖，让 uv 自己解析
#   dependencies = ["deerflow-harness @ file://../deerflow/backend/packages/harness", ...]
```

**【验证点】import 必须指向 submodule：**
```bash
.venv/bin/python -c "import deerflow; print(deerflow.__file__)"
# → 期望输出 deerflow-research/deerflow/backend/packages/harness/deerflow/__init__.py
```

**【验证点】跑通一次：**
```bash
.venv/bin/python -m pytest tests/ -x -q     # 或你惯用的 demo/run 命令
```

如果 harness 需要 gateway：在 `deerflow/backend` 里 `uv sync && uv run uvicorn app.gateway.app:app`，再把启动命令收进 `scripts/`。

## Phase 4：写 AGENTS.md + README（防迷糊的临门一脚）

```bash
# AGENTS.md 全文见 answer.md 的模板；README 一句话 + 怎么跑
cat > README.md <<'EOF'
# deerflow-research

跑在 DeerFlow 之上的 deep research runtime。根目录刻意很小：
- harness/   ← 你的应用
- deerflow/  ← 锁定的外部依赖（submodule @ 4915b5e），别动
- reference/ ← DeerFlow 研究笔记，只读
EOF
```

**【验证点】agent 视角**：删掉你的记忆重新开一个 session，读 AGENTS.md 后让它"总结这个 repo"，它应该三句话内说出"重点在 harness、deerflow 是依赖、reference 是笔记"——而不是去数框架文件。

## Phase 5：收尾核对

| 检查 | 期望 |
|------|------|
| 根目录 `ls` | 只有 AGENTS/README/deerflow/harness/openspec/skills/_backlog/reference/scripts |
| `git submodule status` | deerflow @ 4915b5e |
| harness `import deerflow` | 指向 submodule 内，不是仓库外 |
| harness 测试 / demo | 跑通（行为与现在一致） |
| 笔记 | 在 `reference/`，来自最新版（非过期 wiki） |
| 旧仓 | 全部原样保留，当参考 |

## 风险与注意

- **submodule 换机器**：`git clone --recurse-submodules` 才能带上 deerflow；忘了会缺运行时。在 README 写明这一步。
- **版本差是刻意的**：运行时 4915b5e ≠ 笔记 e5c62cab，已在 `reference/README.md` 记录。将来升级 = 换 submodule commit + 重跑测试，一次有意动作。
- **不要从过期 wiki 搬笔记**：`deer-flow/_digest`（ethan 分支）才是 sync #4 后的最新版。
