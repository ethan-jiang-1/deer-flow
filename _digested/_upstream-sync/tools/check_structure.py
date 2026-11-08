#!/usr/bin/env python3
"""Structure gate for _digested: README contract, front matter, root map.

Run from the repository root:
    python3 _digested/_upstream-sync/tools/check_structure.py
Exit 0 = all good; 1 = violations.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DOCS = os.path.join(ROOT, "_digested")
REQUIRED = ("## 阅读路径", "## 本篇目", "## 宪章与约定", "## 相关目录")
TOP_DIRS = (
    "_upstream-sync", "concepts", "enterprise-it-governance", "enterprise-operations",
    "frontend", "getting-started", "graph-engineering", "harness", "harness-engineering",
    "internals", "observability", "orchestration-ladder", "overview", "test-strategy", "testing",
)


def read(path: str) -> str:
    return open(path, encoding="utf-8").read()


def front_matter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end > 0 else ""


def field(fm: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}:\s*(.*)$", fm, re.M)
    return m.group(1).strip() if m else ""


def main() -> int:
    errors: list[str] = []
    readmes: list[str] = []
    content: list[str] = []
    for dp, _dn, fn in os.walk(DOCS):
        for f in fn:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            (readmes if f == "README.md" else content).append(p)

    # README contract + 本篇目 coverage
    for p in readmes:
        rel = os.path.relpath(p, ROOT)
        t = read(p)
        fm = front_matter(t)
        if field(fm, "type") != "index":
            errors.append(f"{rel}: type is not index")
        for sec in REQUIRED:
            if sec not in t:
                errors.append(f"{rel}: missing {sec}")
        sec = t.split("## 本篇目", 1)[-1].split("\n## ", 1)[0] if "## 本篇目" in t else ""
        for f in os.listdir(os.path.dirname(p)):
            if f.endswith(".md") and f != "README.md" and f not in sec:
                errors.append(f"{rel}: 本篇目 does not list {f}")

    # content front matter + verified baseline (meta dir excluded)
    for p in content:
        rel = os.path.relpath(p, ROOT)
        if "/_upstream-sync/" in p or rel.endswith(("PLAN.md", "AUDIT-FIX-PLAN.md")):
            continue
        ref = read(p)
        fm = front_matter(ref)
        if not fm:
            errors.append(f"{rel}: missing front matter")
            continue
        desc = field(fm, "description").strip()
        if not desc:
            errors.append(f"{rel}: empty description")
        else:
            if desc[0] in "\"'":
                desc = desc[1:-1].strip() if len(desc) >= 2 and desc[-1] == desc[0] else desc
            if not desc or desc[0] in "#|-*`":
                errors.append(f"{rel}: description looks like markdown/body text")
        if field(fm, "verified_against") != "v2.2.0":
            errors.append(f"{rel}: verified_against is not v2.2.0")


    # root reading path covers all top-level dirs
    root = read(os.path.join(DOCS, "README.md"))
    if "## 阅读路径" in root:
        sec = root.split("## 阅读路径", 1)[1].split("\n## ", 1)[0]
        for d in TOP_DIRS:
            if not re.search(rf"\]\({re.escape(d)}/", sec):
                errors.append(f"_digested/README.md: reading path misses {d}/")
    else:
        errors.append("_digested/README.md: missing 阅读路径")

    if errors:
        print(f"❌ structure: {len(errors)} problem(s)")
        for e in errors:
            print(" -", e)
        return 1
    print(f"✅ structure: {len(readmes)} READMEs, {len(content)} content pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
