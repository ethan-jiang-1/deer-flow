#!/usr/bin/env python3
"""Figure gate: page refs <-> SVG files must be a bijection, and house style holds.

Run from the repository root:
    python3 _digested/_upstream-sync/tools/check_figures.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DOCS = os.path.join(ROOT, "_digested")


def load_kit():
    path = os.path.join(ROOT, "_digested/_upstream-sync/tools/figurekit.py")
    spec = importlib.util.spec_from_file_location("figurekit", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    kit = load_kit()
    errors: list[str] = []
    refs: dict[str, set[str]] = {}
    pages: list[str] = []
    for dp, _dn, fn in os.walk(DOCS):
        for f in fn:
            if not f.endswith(".md"):
                continue
            page = os.path.join(dp, f)
            if "/_upstream-sync/" in page:
                continue
            text = open(page, encoding="utf-8").read()
            # Ignore figure syntax inside fenced/inline code examples.
            text = re.sub(r"```.*?```", "", text, flags=re.S)
            text = re.sub(r"`[^`]*`", "", text)
            for m in re.finditer(r"!\[[^\]]*\]\(([^)\s]+\.(?:svg|png|jpe?g|webp|gif))", text):
                target = m.group(1).strip()
                if target.startswith(("http://", "https://", "data:")):
                    continue
                resolved = os.path.normpath(os.path.join(os.path.dirname(page), target))
                refs.setdefault(resolved, set()).add(page)
                pages.append(page)
                if not os.path.isfile(resolved):
                    errors.append(f"{os.path.relpath(page, ROOT)}: missing image {target}")

    svg_files: list[str] = []
    for dp, _dn, fn in os.walk(DOCS):
        if os.path.basename(dp) != "figures":
            continue
        for f in fn:
            if f.endswith(".svg"):
                svg_files.append(os.path.join(dp, f))
    for svg in svg_files:
        if svg not in refs:
            errors.append(f"{os.path.relpath(svg, ROOT)}: orphan SVG (no page ref)")
        try:
            tree = ET.parse(svg)
        except Exception as exc:
            errors.append(f"{os.path.relpath(svg, ROOT)}: invalid XML: {exc}")
            continue
        root = tree.getroot()
        house = svg in {os.path.join(ROOT, s["page"].rsplit("/", 1)[0], s["file"]) for s in kit.FIGURES}
        if house or "/enterprise-it-governance/" in svg:
            if root.find("{http://www.w3.org/2000/svg}title") is None:
                errors.append(f"{os.path.relpath(svg, ROOT)}: missing <title>")
            if root.find("{http://www.w3.org/2000/svg}desc") is None:
                errors.append(f"{os.path.relpath(svg, ROOT)}: missing <desc>")
        if "/enterprise-it-governance/" in svg:
            text = open(svg, encoding="utf-8").read()
            if 'data-house="v1"' not in text:
                errors.append(f"{os.path.relpath(svg, ROOT)}: governance figure missing data-house=v1")
            m = re.search(r'viewBox="0 0 (\d+) (\d+)"', text)
            if not m or int(m.group(1)) not in (980, 1000):
                errors.append(f"{os.path.relpath(svg, ROOT)}: governance figure width is not 980/1000")
            if 'font-family="PingFang SC, sans-serif"' not in text:
                errors.append(f"{os.path.relpath(svg, ROOT)}: governance figure non-house font")

    # New figures must carry the house marker and house canvas/font.
    for spec in kit.FIGURES:
        page = os.path.join(ROOT, spec["page"])
        svg = os.path.join(os.path.dirname(page), spec["file"])
        if not os.path.isfile(svg):
            continue
        text = open(svg, encoding="utf-8").read()
        if 'data-house="v1"' not in text:
            errors.append(f"{os.path.relpath(svg, ROOT)}: missing data-house=v1")
        m = re.search(r'viewBox="0 0 (\d+) (\d+)"', text)
        if not m or int(m.group(1)) != 1000:
            errors.append(f"{os.path.relpath(svg, ROOT)}: house width is not 1000")
        if 'font-family="PingFang SC, sans-serif"' not in text:
            errors.append(f"{os.path.relpath(svg, ROOT)}: non-house font-family")
        page_text = open(page, encoding="utf-8").read()
        marker = f"]({spec['file']})"
        pos = page_text.find(marker)
        if pos < 0:
            errors.append(f"{spec['page']}: missing image reference")
        else:
            alt_start = page_text.rfind("![", 0, pos)
            alt = page_text[alt_start + 2:pos] if alt_start >= 0 else ""
            if not alt.strip():
                errors.append(f"{spec['page']}: empty image alt text")
            if "图读法" not in page_text[pos:pos + 400]:
                errors.append(f"{spec['page']}: missing 图读法 caption")

    if errors:
        print(f"❌ figures: {len(errors)} problem(s)")
        for e in errors[:100]:
            print(" -", e)
        return 1
    print(f"✅ figures: {len(refs)} image refs, {len(svg_files)} SVG files, no orphans")
    return 0


if __name__ == "__main__":
    sys.exit(main())
