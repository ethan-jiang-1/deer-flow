# 执行记录：V2 从零搭建（已建成，258 测试通过）

> **这是实际执行过的记录，不是待办计划。** V2（`~/ai_deerflow_deep_research_v2`）已建成并验证。下面的步骤是真实操作 + 过程中踩的坑，将来重建/复现时照此执行。

## 最终目标结构（已达成）

```
~/ai_deerflow_deep_research_v2/
├── deep_research_harness/   ★ 你的应用（deep research runtime，src/deerflow_deep_research）
├── deerflow/                submodule → ethan-jiang-1/deer-flow @ ethan（框架 + 笔记 _digest/_faq）
├── openspec/                设计规格（openspec CLI 1.7.0）
├── _backlog/                任务账本
├── profiles/                应用配置档（normal/development/test/demo 的 config.yaml）
├── .claude/skills/          grillme 技能集（24 个）
├── .agents/skills/          Codex 技能（约定不同）
├── .codex/                  openspec 的 Codex 技能
├── .cursor/ + .trae/        openspec opsx 命令
├── .vscode/                 settings + launch
├── AGENTS.md / CLAUDE.md / README.md   应用是主角的地图
├── CONTEXT.md / CONTEXT-MAP.md
├── config.yaml / .env       （本地运行配置，gitignore，不进仓库）
└── skills-lock.json         （技能锁，供 npx skills update）
```

## 关键决策（用户拍板）

| 决策 | 值 | 原因 |
|------|-----|------|
| submodule 源 | **自己的 ethan 分支**（不是 bytedance 上游） | ethan 含框架 + 笔记 `_digest`/`_faq`，一次带齐 |
| 钉的 commit | ethan HEAD `9ef471e9` | harness 当前跑通的基座 |
| harness 目录名 | **`deep_research_harness`**（原名，不改） | 内部文档/Makefile/AGENTS 全引用这个名字 |
| 笔记位置 | **在 submodule 里**（`deerflow/_digest`） | 本就在 ethan 上，不另搞 wiki |
| openspec + grillme | 装进 V2 | 开发所需的两个工具链 |

## 执行步骤

### Phase 0：仓库 scaffold
```bash
mkdir ~/ai_deerflow_deep_research_v2 && cd ~/ai_deerflow_deep_research_v2
git init
# origin → ethan-jiang-1/ai_deerflow_deep_research_v2（已有 Initial commit + Python .gitignore + README）
```

### Phase 1：加 submodule（ethan 分支）
```bash
git submodule add git@github.com:ethan-jiang-1/deer-flow.git deerflow
cd deerflow && git fetch origin ethan && git checkout 9ef471e9   # ethan HEAD
cd .. && git add deerflow
```

### Phase 2：搬应用内容（复制，V1 保持原样当参考）
```bash
V1=~/ai_deerflow_deep_research
# 应用代码 → deep_research_harness/（保持原名！排除 venv/缓存）
rsync -a --exclude '.venv' --exclude '.pytest_cache' --exclude '.ruff_cache' \
  --exclude '.reports' --exclude '.deep-research-demo-runs' --exclude '__pycache__' \
  "$V1/deep_research_harness/" "$V2/deep_research_harness/"
# 规格 / 任务 / 上下文
cp -r "$V1/openspec" "$V2/openspec"
cp -r "$V1/_backlog" "$V2/_backlog"
cp "$V1/CONTEXT.md" "$V1/CONTEXT-MAP.md" "$V2/"
```

### Phase 3：装 openspec + grillme
```bash
openspec --version    # 全局 CLI 1.7.0，V1 的 openspec/ 直接搬来即用
# grillme：复制 promoted 技能（engineering + productivity）到项目 .claude/skills/
rsync -a ~/grillme-skills/skills/engineering/ ~/grillme-skills/skills/productivity/ "$V2/.claude/skills/"
```

### Phase 4：运行时接线（关键）
```bash
cd "$V2/deep_research_harness"
# 把 pyproject 里 [tool.uv.sources] 的框架路径从旧 vendored 改成 submodule：
#   deerflow-harness = { path = "../deerflow/backend/packages/harness", editable = true }
uv lock                      # 重新生成锁（229 包）
uv sync --extra operations --extra demo-tui
# 验证 import 指向 submodule 内：
.venv/bin/python -c "import deerflow; print(deerflow.__file__)"
#   → .../v2/deerflow/backend/packages/harness/deerflow/__init__.py
.venv/bin/python -m pytest tests/unit tests/domain -q    # → 258 passed
```

### Phase 5：写 agent 地图 + 拷工具配置
```bash
# AGENTS.md/CLAUDE.md/README（应用是主角，deerflow 只 leverage 不改）
# 工具配置：VSCode / Codex / Cursor / Trae / openspec 技能
cp -r "$V1/.vscode" "$V1/.agents" "$V1/.codex" "$V1/.cursor" "$V1/.trae" "$V2/"
cp "$V1/skills-lock.json" "$V2/"
```

### Phase 6：运行配置
```bash
cp "$V1/config.yaml" "$V2/config.yaml"   # 主模板（profiles 系统从这里复制）
cp "$V1/.env" "$V2/.env"                 # 密钥（config 里 $DEEPSEEK_API_KEY 解析）
# .gitignore 忽略 config.yaml / config.yaml.bak（和 V1 一致，本地配置不进仓库）
```

## 执行中踩的坑（都纠正了）

| 坑 | 发生 | 修正 |
|----|------|------|
| **harness 目录名改成了 `harness/`** | 内部文档全引用 `deep_research_harness/`，对不齐 | `git mv harness deep_research_harness` 改回原名 |
| **把框架 `skills/` 当应用拷了** | V1 根 `skills/` 是框架技能子集（还缺 skill-reviewer） | 删除；框架技能随 submodule 走 |
| **`.codex/` 误判为空** | `find -maxdepth 2` 没扫到深层，其实有 6 个 openspec 技能 | 补拷 |
| **`config.yaml` 放哪** | 靠 `local_profiles.py` 第 201 行确认：根 `config.yaml` 是主模板 | 放 V2 根 + gitignore |
| **笔记放 `reference/`**（旧计划设想） | 实际笔记在 submodule 的 `_digest` 里 | 不另建 reference/ |

## 验证（已完成）

- `import deerflow` → V2 内 submodule ✓
- `import deerflow_deep_research` → 应用包 ✓
- `pytest tests/unit tests/domain` → **258 passed** ✓
- 根目录 `ls` → 只有应用 + 配置层，无框架文件 ✓

## 未来维护

- **submodule 更新**：ethan 前进后，`git -C deerflow pull origin ethan && git submodule update`（V2 记录的指针也要更新）。
- **技能更新**：`.claude/skills/` 是复制方式（方式二）→ 手动 `npx skills@latest update`；想自动跟上游可改 symlink 方式（方式三）。
- **配置**：换场景用 `cd deep_research_harness && make profile-dev PROFILE=demo` 等 profiles 命令。
- **换机器**：`git clone --recurse-submodules` + 重建 `.env`/`config.yaml`（本地不提交）。
