#!/usr/bin/env python3
"""Run every _digested gate in one shot.

    python3 _digested/_upstream-sync/tools/check_all.py
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = [
    os.path.join(HERE, "check_digest.py"),
    os.path.join(HERE, "check_structure.py"),
    os.path.join(HERE, "check_freshness.py"),
    os.path.join(HERE, "check_coverage.py"),
]


def main() -> int:
    failed = []
    for tool in TOOLS:
        print(f"\n== {os.path.basename(tool)} ==")
        code = subprocess.call([sys.executable, tool])
        if code != 0:
            failed.append(os.path.basename(tool))
    print("\n== summary ==")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("ALL GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
