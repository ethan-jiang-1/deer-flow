#!/usr/bin/env python3
"""Freshness gate: recompute high-risk facts and scan for known stale values.

Run from the repository root:
    python3 _digested/_upstream-sync/tools/check_freshness.py
"""
from __future__ import annotations

import ast
import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DOCS = os.path.join(ROOT, "_digested")


def read(path: str) -> str:
    return open(path, encoding="utf-8").read()


def count_glob(pattern: str) -> int:
    return len(glob.glob(os.path.join(ROOT, pattern)))


def count_dirs(pattern: str) -> int:
    return len([p for p in glob.glob(os.path.join(ROOT, pattern)) if os.path.isdir(p)])


def migrations() -> tuple[int, str]:
    files = sorted(glob.glob(os.path.join(
        ROOT, "backend/packages/harness/deerflow/persistence/migrations/versions/0*.py")))
    if not files:
        return 0, ""
    return len(files), os.path.splitext(os.path.basename(files[-1]))[0]


def orm_rows() -> int:
    path = os.path.join(ROOT, "backend/packages/harness/deerflow/persistence/models/__init__.py")
    tree = ast.parse(read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            return len(node.value.elts)
    return -1


def permissions() -> int:
    path = os.path.join(ROOT, "backend/app/gateway/authz.py")
    tree = ast.parse(read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_ALL_PERMISSIONS" for t in node.targets
        ):
            return len(node.value.elts)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_ALL_PERMISSIONS":
            return len(node.value.elts)
    return -1


def marker_count(marker: str) -> int:
    n = 0
    for p in glob.glob(os.path.join(ROOT, "backend/tests/**/*.py"), recursive=True):
        n += len(re.findall(
            rf"pytest\.mark\.{marker}\b|pytestmark\s*=.*\b{marker}\b",
            read(p),
        ))
    return n


def content_counts() -> tuple[int, int, int]:
    root_docs = len(glob.glob(os.path.join(ROOT, "docs/*.md")))
    backend_docs = len(glob.glob(os.path.join(ROOT, "backend/docs/*.md")))
    content = len(glob.glob(os.path.join(ROOT, "frontend/src/content/**/*.md"), recursive=True))
    content += len(glob.glob(os.path.join(ROOT, "frontend/src/content/**/*.mdx"), recursive=True))
    return root_docs, backend_docs, content


def manual_pages(name: str) -> int:
    return len(glob.glob(os.path.join(ROOT, f"frontend/src/content/en/harness/{name}/*.mdx")))


STALE = [
    "0001 → 0025",
    "22 个 Row",
    "22 张表",
    "9 个权限",
    "worker.py:233-247",
    "client.py:601",
    "进程内 dict，多 worker 共享同一 IP 可绕过",
    "7 个注册方法",
    "七种 provider 实现",
    "三份 contracts",
    "16 个 `test_tui",
    "2,921",
    "共享基础层 16",
    "lead-only 23",
    "end` SSE 事件携带累积用量",
]
SKIP_PARTS = ("/_upstream-sync/", "/PLAN.md", "/AUDIT-FIX-PLAN.md")

# High-risk facts: recomputed against source below. Kept in the checker so the
# gate has no separate mutable manifest.
SPEC = {
    "facts": {
        "migrations": {"value": 50, "head": "0048_extension_execution_leases"},
        "orm_rows": {"value": 38},
        "permissions": {"value": 13},
        "tui_tests": {"value": 19},
        "extension_tests": {"value": 31},
        "contracts": {"value": 9},
        "public_skills": {"value": 23},
        "extension_examples": {"value": 14},
        "frontend_core_dirs": {"value": 41},
        "docs_root": {"value": 11},
        "docs_backend": {"value": 47},
        "docs_content": {"value": 134},
        "manual_pages": {"extensions": 11, "subagents": 11, "checkpoints": 10},
    },
    "markers": {
        "asyncio": 3047,
        "no_auto_user": 83,
        "integration": 20,
        "allow_blocking_io": 11,
        "live": 12,
    },
}


def main() -> int:
    spec = SPEC
    facts = spec["facts"]
    problems: list[str] = []

    mcount, mhead = migrations()
    if mcount != facts["migrations"]["value"]:
        problems.append(f"migrations: expected {facts['migrations']['value']}, got {mcount}")
    if mhead != facts["migrations"]["head"]:
        problems.append(f"migration head: expected {facts['migrations']['head']}, got {mhead}")
    if orm_rows() != facts["orm_rows"]["value"]:
        problems.append(f"orm_rows: expected {facts['orm_rows']['value']}, got {orm_rows()}")
    if permissions() != facts["permissions"]["value"]:
        problems.append(f"permissions: expected {facts['permissions']['value']}, got {permissions()}")

    expected = {
        "tui_tests": count_glob("backend/tests/test_tui_*.py"),
        "extension_tests": count_glob("backend/tests/test_extension_*.py"),
        "contracts": count_glob("contracts/*.json"),
        "public_skills": count_dirs("skills/public/*/"),
        "extension_examples": count_dirs("examples/deerflow-extension-*/"),
        "frontend_core_dirs": count_dirs("frontend/src/core/*/"),
    }
    for key, actual in expected.items():
        if actual != facts[key]["value"]:
            problems.append(f"{key}: expected {facts[key]['value']}, got {actual}")

    docs_root, docs_backend, docs_content = content_counts()
    for key, actual in (("docs_root", docs_root), ("docs_backend", docs_backend), ("docs_content", docs_content)):
        if actual != facts[key]["value"]:
            problems.append(f"{key}: expected {facts[key]['value']}, got {actual}")

    for name, expected_count in facts["manual_pages"].items():
        actual = manual_pages(name)
        if actual != expected_count:
            problems.append(f"manual_pages.{name}: expected {expected_count}, got {actual}")

    for marker, expected_count in spec["markers"].items():
        actual = marker_count(marker)
        if actual != expected_count:
            problems.append(f"marker {marker}: expected {expected_count}, got {actual}")

    # Scan current-facing content for known stale strings.
    for dp, _dn, fn in os.walk(DOCS):
        for f in fn:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            if any(part in p for part in SKIP_PARTS):
                continue
            text = read(p)
            for pat in STALE:
                if pat in text:
                    problems.append(f"stale value {pat!r} in {os.path.relpath(p, ROOT)}")

    if problems:
        print(f"❌ freshness: {len(problems)} problem(s)")
        for p in problems[:80]:
            print(" -", p)
        return 1
    print("✅ freshness: facts match source; no known stale values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
