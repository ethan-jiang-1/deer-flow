#!/usr/bin/env python3
"""Coverage gate: every declared surface has an existing, indexed owner page.

Run from the repository root:
    python3 _digested/_upstream-sync/tools/check_coverage.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DOCS = os.path.join(ROOT, "_digested")

# Surface -> canonical owner. Kept in the checker so the gate has no separate
# mutable manifest.
SURFACES = [
    {"id": "backend-harness-core", "owner": "internals/README.md", "priority": "P0"},
    {"id": "backend-concepts", "owner": "concepts/README.md", "priority": "P0"},
    {"id": "backend-app-api", "owner": "enterprise-operations/app-layer/01-api-reference.md", "priority": "P0"},
    {"id": "frontend-architecture", "owner": "frontend/06-architecture.md", "priority": "P0"},
    {"id": "frontend-feature-map", "owner": "frontend/07-feature-map.md", "priority": "P0"},
    {"id": "extensions-contract", "owner": "internals/harness-hooks/09-packaged-extensions.md", "priority": "P0"},
    {"id": "extensions-examples", "owner": "internals/harness-hooks/10-extension-examples.md", "priority": "P0"},
    {"id": "skills-mechanism", "owner": "concepts/skills-tools/skill-md-and-tool-assembly.md", "priority": "P1"},
    {"id": "skills-catalog", "owner": "concepts/skills-tools/00-catalog.md", "priority": "P1"},
    {"id": "authz", "owner": "internals/authz/README.md", "priority": "P0"},
    {"id": "sandbox", "owner": "concepts/sandbox/README.md", "priority": "P0"},
    {"id": "middleware", "owner": "internals/middleware/03-catalog.md", "priority": "P0"},
    {"id": "persistence", "owner": "internals/persistence/db-checkpointer-store-backends.md", "priority": "P0"},
    {"id": "config-reference", "owner": "internals/configuration/04-config-reference.md", "priority": "P0"},
    {"id": "multi-instance", "owner": "enterprise-operations/deployment/04-multi-instance.md", "priority": "P1"},
    {"id": "mcp", "owner": "internals/mcp/README.md", "priority": "P0"},
    {"id": "mcp-scope", "owner": "internals/mcp/02-scopes-and-per-user.md", "priority": "P1"},
    {"id": "tracing", "owner": "observability/01-logging-and-trace-context.md", "priority": "P0"},
    {"id": "testing", "owner": "testing/README.md", "priority": "P0"},
    {"id": "test-strategy", "owner": "test-strategy/README.md", "priority": "P0"},
    {"id": "governance", "owner": "enterprise-it-governance/README.md", "priority": "P0"},
    {"id": "backup", "owner": "enterprise-operations/backup-and-monitoring.md", "priority": "P0"},
    {"id": "docs-map", "owner": "overview/08-upstream-docs-map.md", "priority": "P1"},
    {"id": "extension-boundary", "owner": "enterprise-operations/security/06-extension-boundary.md", "priority": "P1"},
]


def read(path: str) -> str:
    return open(path, encoding="utf-8").read()


def parent_readme(owner_rel: str) -> str:
    owner = os.path.join(DOCS, owner_rel)
    if os.path.basename(owner) == "README.md":
        parent = os.path.dirname(os.path.dirname(owner))
    else:
        parent = os.path.dirname(owner)
    return os.path.join(parent, "README.md")


def main() -> int:
    spec = {"surfaces": SURFACES, "accepted_gaps": []}
    errors: list[str] = []
    accepted = {g["id"]: g for g in spec.get("accepted_gaps", [])}
    for surface in spec["surfaces"]:
        sid, owner_rel, priority = surface["id"], surface["owner"], surface["priority"]
        owner = os.path.join(DOCS, owner_rel)
        if not os.path.isfile(owner):
            if sid in accepted:
                continue
            errors.append(f"{sid} ({priority}): owner missing: {owner_rel}")
            continue
        pread = parent_readme(owner_rel)
        if not os.path.isfile(pread):
            errors.append(f"{sid}: parent README missing for {owner_rel}")
            continue
        text = read(pread)
        name = os.path.basename(owner_rel)
        if name == "README.md":
            needle = os.path.basename(os.path.dirname(owner_rel)) + "/"
        else:
            needle = name
        if needle not in text:
            errors.append(f"{sid}: {os.path.relpath(pread, DOCS)} does not index {needle}")
    if errors:
        print(f"❌ coverage: {len(errors)} problem(s)")
        for e in errors:
            print(" -", e)
        return 1
    print(f"✅ coverage: {len(spec['surfaces'])} surfaces have indexed owners")
    return 0


if __name__ == "__main__":
    sys.exit(main())
