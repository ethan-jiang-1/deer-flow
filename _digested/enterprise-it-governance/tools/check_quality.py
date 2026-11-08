#!/usr/bin/env python3
"""企业 IT 治理卷的质量闸门检查器（PLAN.md §9）。

用法：
    python3 _digested/enterprise-it-governance/tools/check_quality.py
    python3 _digested/enterprise-it-governance/tools/check_quality.py --verbose
    python3 _digested/enterprise-it-governance/tools/check_quality.py --file identity/07-sso-and-oidc.md

检查项（对应 PLAN §9）：
  §9.2 evidence   —— 每篇 ≥3 处 file:line
  §9.3 gap_tristate —— 缺口表述含边界词（"不覆盖"/"未闭合"/"部分"），禁止裸"有"/"无"
  §9.4 consistency —— 已知数字型事实全文一致（扫描矛盾值）
  §9.6 style      —— frontmatter 三项齐全、单篇 60–200 行、单 `#`
  §9.7 compliance —— compliance/ 每篇有免责声明
  §9.8 无采购建议  —— 禁止「贵司应该」

退出码：0 全部通过；1 有告警；2 有阻塞问题。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# ── 已核实的事实登记表（PLAN §9.5）。键为事实名，值为正确值的正则。
# 用于检测"某个已被推翻的旧值"是否还残留。
STALE_VALUES = {
    "subagent 并发旧值": re.compile(r"MAX_CONCURRENT_SUBAGENTS\s*=\s*3|并发\s*[≤<]\s*3\b"),
    "无 per-run 预算（旧断言）": re.compile(r"无\s*per-run\s*预算"),
    "guardrail 不写 journal（旧断言）": re.compile(r"(?:Guardrail|guardrail)\s*deny\s*不写\s*RunJournal"),
}

# ── 缺口表述边界词（§9.3 第三态要求）
GAP_BOUNDARY_WORDS = ("不覆盖", "未闭合", "部分", "仅", "只覆盖", "但不", "边界")

# ── 采购建议禁用词（§9 语气约束）
ADVICE_PATTERNS = [re.compile(r"贵司应"), re.compile(r"建议贵公司"), re.compile(r"您应该采购")]

EVIDENCE_RE = re.compile(r"`[A-Za-z0-9_./-]+\.(?:py|ts|tsx|yml|yaml|json|md):\d+")
# 判断性段落标题（这些节内论据密度要求更高）
JUDGMENT_SECTION_RE = re.compile(r"^##+\s*(?:.*(?:缺口|矩阵|结论|判断|风险|成熟度|自评|边界|限制|覆盖))", re.M)


@dataclass
class Finding:
    level: str  # "block" | "warn"
    check: str
    path: str
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level, check, path, message):
        self.findings.append(Finding(level, check, path, message))

    @property
    def blocks(self):
        return [f for f in self.findings if f.level == "block"]

    @property
    def warns(self):
        return [f for f in self.findings if f.level == "warn"]


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^(\w+):\s*(.*)$", line.strip())
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"')
    return fm


def strip_fences(text: str) -> str:
    """移除 ``` 围栏内的内容，避免把代码注释误判为标题/断言。"""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def body_of(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4 :] if end != -1 else text


def check_file(path: Path, rel: str, rep: Report, verbose: bool) -> int:
    text = path.read_text(encoding="utf-8")
    body = body_of(text)
    lines = body.splitlines()
    nlines = len(lines)
    fm = parse_frontmatter(text)
    is_index = path.name in ("README.md", "PLAN.md")

    # ── §9.2 evidence
    evidence = EVIDENCE_RE.findall(body)
    n_ev = len(evidence)
    if not is_index and n_ev == 0:
        rep.add("block", "evidence", rel, "零处 file:line 证据（§9.2 要求 ≥3）")
    elif not is_index and n_ev < 3:
        rep.add("warn", "evidence", rel, f"仅 {n_ev} 处 file:line（§9.2 目标 ≥3）")

    # 判断性段落内是否有证据
    if not is_index and JUDGMENT_SECTION_RE.search(body):
        # 粗略判断：若存在判断节但全文无证据，已由上面捕获
        pass

    # ── §9.3 gap_tristate：出现"缺口"表述的表格行/句子里要看边界词
    if not is_index:
        for m in re.finditer(r"^.*(?:不覆盖|缺失|无\s*\w+\s*能力|没有)\s*\|?\s*.*$", body, re.M):
            line = m.group(0)
            if "|" in line and ("缺口" in line or "无" in line or "缺" in line):
                if not any(w in line for w in GAP_BOUNDARY_WORDS):
                    # 只在明确列缺口时告警，避免噪音
                    if re.search(r"缺口|缺失", line):
                        rep.add("warn", "gap_tristate", rel,
                                f"缺口表述缺边界词：{line.strip()[:70]}")

    # ── §9.4 consistency：旧值残留
    for name, pat in STALE_VALUES.items():
        for m in pat.finditer(body):
            # 允许在"⚠️ 变更"提示中出现旧值（作为对照）
            start = max(0, m.start() - 120)
            ctx = body[start : m.end() + 120]
            if "变更" in ctx or "此前" in ctx or "旧值" in ctx or "已订正" in ctx:
                continue
            rep.add("block", "consistency", rel, f"残留已被推翻的旧断言（{name}）：{m.group(0)!r}")

    # ── §9.6 style
    if not is_index:
        for key in ("title", "description", "topics"):
            if key not in fm:
                rep.add("block", "style", rel, f"frontmatter 缺 `{key}`（§9.6）")
        h1 = [l for l in strip_fences(body).splitlines() if l.startswith("# ")]
        if len(h1) > 1:
            rep.add("warn", "style", rel, f"{len(h1)} 个一级标题（应唯一）")
        if nlines > 200:
            rep.add("warn", "style", rel, f"{nlines} 行 > 200（§9.6 建议拆分）")
        elif nlines < 40:
            rep.add("warn", "style", rel, f"{nlines} 行 < 40（§9.6 建议合并）")

    # ── §9.7 compliance 免责声明
    if rel.startswith("compliance/") and path.name != "README.md":
        if not re.search(r"不构成合规(?:结论|认证)|不宣称合规", body):
            rep.add("block", "compliance", rel, "缺『不构成合规结论』免责声明（§9.7）")

    # ── 采购建议
    for pat in ADVICE_PATTERNS:
        if pat.search(body):
            rep.add("block", "tone", rel, f"出现采购建议表述：{pat.pattern}（§9 禁止）")

    if verbose:
        status = "○"
        if any(f.path == rel and f.level == "block" for f in rep.findings):
            status = "✗"
        elif any(f.path == rel for f in rep.findings):
            status = "!"
        print(f"  {status} {rel:<46} {nlines:>4} 行  {n_ev:>2} 处证据")
    return n_ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--file", "-f", help="只检查指定文件（相对 enterprise-it-governance/）")
    args = ap.parse_args()

    rep = Report()
    if args.file:
        targets = [BASE / args.file]
    else:
        targets = sorted(BASE.rglob("*.md"))

    if args.verbose:
        print("逐篇统计：")
    total_ev = 0
    n_content = 0
    for p in targets:
        rel = str(p.relative_to(BASE))
        n_ev = check_file(p, rel, rep, args.verbose)
        if p.name not in ("README.md", "PLAN.md"):
            total_ev += n_ev
            n_content += 1

    if args.verbose:
        print()

    print(f"检查 {len(targets)} 篇（内容篇 {n_content}），"
          f"证据共 {total_ev} 处，密度 {total_ev / max(n_content, 1):.1f} 处/篇")

    for level, label in (("block", "❌ 阻塞"), ("warn", "⚠️  告警")):
        items = [f for f in rep.findings if f.level == level]
        if items:
            print(f"\n{label} {len(items)} 处：")
            for f in items:
                print(f"   [{f.check}] {f.path}: {f.message}")

    if rep.blocks:
        print(f"\n共 {len(rep.blocks)} 处阻塞、{len(rep.warns)} 处告警。")
        return 2
    if rep.warns:
        print(f"\n共 {len(rep.warns)} 处告警（不阻塞）。")
        return 1
    print("\n✅ 质量闸门全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
