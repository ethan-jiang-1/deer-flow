#!/usr/bin/env python3
"""校验文档里的 `file.py:NNN` 锚点是否真的存在且指向合理内容。

用法：
    python3 tools/verify_anchors.py                    # 全部篇目
    python3 tools/verify_anchors.py identity/08-pat.md # 单篇
    python3 tools/verify_anchors.py --quiet            # 只报错误

只做「行号存在性」校验（文件存在、行号在范围内），不做语义校验。
语义校验仍需人工抽查——但这一步能挡掉绝大多数手误。
`--strict-lines` 额外提示锚点落在空行/纯注释行的情况（只警告，不影响退出码）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPO = BASE.parent.parent  # _digested -> repo root

# 只校验能定位到仓库文件的锚点：形如 `path/file.py:123` 或 `path/file.py:12-34`
ANCHOR_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|ts|tsx|yml|yaml|json|md|mjs|sh)):(\d+)(?:-(\d+))?`")

# 允许的路径前缀别名：文档里常写 pat.py 而非 app/gateway/auth/pat.py
SEARCH_ROOTS = ("backend", "frontend", "scripts", "contracts", "docker")
# 绝不进入的目录（虚拟环境、依赖、构建产物、缓存）
EXCLUDE_DIRS = frozenset({".venv", "node_modules", "__pycache__", ".git", "dist",
                          "build", ".next", ".turbo", ".mypy_cache", ".ruff_cache",
                          "site-packages", ".pytest_cache"})


def resolve(rel_path: str) -> list[Path]:
    """把文档里的短路径解析成仓库里的真实文件。

    文档常用 `pat.py:201` / `app/gateway/auth/pat.py:3` 这类简写，
    因此依次尝试：原样 → backend/ 下 → backend/app/ 下 → 全仓 rglob。
    """
    p = Path(rel_path)
    if p.is_absolute():
        return [p] if p.exists() else []

    direct = [REPO / p, REPO / "backend" / p, REPO / "backend" / "app" / p]
    hits = [c for c in direct if c.is_file()]
    if hits:
        return hits

    # 裸文件名或部分路径：按各源码根 rglob
    name = p.name
    found: list[Path] = []
    for root in SEARCH_ROOTS:
        r = REPO / root
        if not r.is_dir():
            continue
        for c in r.rglob(name):
            if any(part in EXCLUDE_DIRS for part in c.parts):
                continue
            if c.is_file() and c.relative_to(REPO).as_posix().endswith(rel_path):
                found.append(c)
        if found:
            break
    return found[:10]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.add_argument("--strict-lines", action="store_true", help="提示锚点落在空行/纯注释行")
    args = ap.parse_args()

    targets = [BASE / f for f in args.files] if args.files else sorted(BASE.rglob("*.md"))
    errors, warnings, checked = [], [], 0

    for md in targets:
        rel_md = str(md.relative_to(BASE))
        text = md.read_text(encoding="utf-8")
        for m in ANCHOR_RE.finditer(text):
            path_s, start_s, end_s = m.group(1), m.group(2), m.group(3)
            start = int(start_s)
            end = int(end_s) if end_s else start
            checked += 1
            resolved = resolve(path_s)
            if not resolved:
                errors.append((rel_md, m.group(0), f"文件不存在：{path_s}"))
                continue
            f = resolved[0]
            try:
                n = sum(1 for _ in f.open(encoding="utf-8", errors="replace"))
            except OSError as e:
                errors.append((rel_md, m.group(0), f"读取失败：{e}"))
                continue
            if start < 1 or end > n:
                errors.append((rel_md, m.group(0), f"行号越界（文件仅 {n} 行）"))
            elif start > end:
                errors.append((rel_md, m.group(0), f"起点 {start} > 终点 {end}"))
            elif not args.quiet and f.stat().st_size == 0:
                warnings.append((rel_md, m.group(0), "目标文件为空"))
            if args.strict_lines:
                try:
                    with f.open(encoding="utf-8", errors="replace") as fh:
                        for _ in range(start):
                            target_line = fh.readline()
                    stripped = target_line.strip()
                    if not stripped or stripped.startswith("#"):
                        warnings.append((rel_md, m.group(0), "指向空行或纯注释行（需人工确认语义）"))
                except OSError:
                    pass

    print(f"校验 {len(targets)} 篇，{checked} 个锚点")
    for md, anchor, msg in errors:
        print(f"  ❌ {md}: {anchor} —— {msg}")
    for md, anchor, msg in warnings:
        print(f"  ⚠️  {md}: {anchor} —— {msg}")
    if errors:
        print(f"\n共 {len(errors)} 个错误。")
        return 1
    print("\n✅ 全部锚点存在且在范围内。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
