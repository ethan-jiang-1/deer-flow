#!/usr/bin/env python3
"""House-style SVG figure builder for _digested.

Design goals:
- one visual system: 1000px wide, PingFang SC, top title/subtitle, tinted cards;
- page-first: a figure is only written if its owning page already references it;
- no orphan files: check_figures.py verifies both directions.

Usage:
    python3 _digested/_upstream-sync/tools/figurekit.py --write
    python3 _digested/_upstream-sync/tools/figurekit.py --check
"""
from __future__ import annotations

import html
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DOCS = os.path.join(ROOT, "_digested")
W = 1000
INK = "#0f172a"
MUTED = "#475569"
LINE = "#64748b"
FONT = "PingFang SC, sans-serif"

PALETTES = [
    ("#e0f2fe", "#0284c7", "#0c4a6e", "#075985"),
    ("#dcfce7", "#16a34a", "#14532d", "#166534"),
    ("#fef9c3", "#ca8a04", "#713f12", "#854d0e"),
    ("#ede9fe", "#7c3aed", "#4c1d95", "#5b21b6"),
    ("#f1f5f9", "#334155", "#0f172a", "#475569"),
]


def esc(value) -> str:
    return html.escape(str(value))


def wrap(text: str, n: int) -> list[str]:
    """Word-aware wrap: keep Latin tokens whole; split Chinese per character."""
    import re
    lines: list[str] = []
    cur = ""
    for part in re.findall(r"\s+|[A-Za-z0-9_./:+-]+|[\u4e00-\u9fff]|[^\s]", str(text)):
        if part.isspace():
            if cur and not cur.endswith(" "):
                cur += " "
            continue
        if part in "·/;,:" and not cur.strip() and lines:
            lines[-1] = lines[-1].rstrip() + part
            continue
        if len(cur) + len(part) <= n:
            cur += part
            continue
        if cur.strip():
            lines.append(cur.rstrip())
            cur = ""
        # A single long token: break only as a last resort, at a separator if possible.
        if len(part) > n:
            rest = part
            while len(rest) > n:
                cut = max(rest.rfind("-", 0, n), rest.rfind("_", 0, n), rest.rfind("/", 0, n))
                if cut <= 0:
                    cut = n
                lines.append(rest[:cut + 1] if cut < len(rest) and rest[cut] in "-_/" else rest[:cut])
                rest = rest[cut + 1:] if cut < len(rest) and rest[cut] in "-_/" else rest[cut:]
            cur = rest
        else:
            cur = part
    if cur.strip():
        lines.append(cur.rstrip())
    # Clean up lines that start with punctuation after a break.
    for i in range(1, len(lines)):
        if lines[i] and lines[i][0] in "·/;,:":
            punct = lines[i][0]
            lines[i - 1] = lines[i - 1].rstrip() + (" " if punct == "·" else "") + punct
            lines[i] = lines[i][1:].lstrip()
    cleaned = [x.rstrip(" ·/;,：:") for x in lines if x.strip()]
    return cleaned or [""]


def frame(title: str, sub: str, body: str, height: int) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" font-family="{FONT}" data-house="v1">
  <title>{esc(title)}</title>
  <desc>{esc(sub)}</desc>
  <defs><marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="{LINE}"/></marker></defs>
  <rect width="{W}" height="{height}" fill="#ffffff"/>
  <text x="{W/2}" y="30" text-anchor="middle" font-size="19" font-weight="700" fill="{INK}">{esc(title)}</text>
  <text x="{W/2}" y="52" text-anchor="middle" font-size="12" fill="{MUTED}">{esc(sub)}</text>
{body}
</svg>
'''


def flow(nodes, title, sub):
    n = len(nodes)
    m, gap = 30, 18
    cw = (W - 2 * m - (n - 1) * gap) / n
    y, ch = 104, 158
    body = []
    xs = []
    for i, (label, detail) in enumerate(nodes):
        x = m + i * (cw + gap)
        xs.append(x)
        fill, stroke, strong, mid = PALETTES[i % len(PALETTES)]
        body.append(f'<rect x="{x:.1f}" y="{y}" width="{cw:.1f}" height="{ch}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        ty = y + 28
        for j, line in enumerate(wrap(label, 20)):
            body.append(f'<text x="{x+cw/2:.1f}" y="{ty+j*17}" text-anchor="middle" font-size="12" font-weight="700" fill="{strong}">{esc(line)}</text>')
        ty += 17 * len(wrap(label, 20)) + 8
        for j, line in enumerate(wrap(detail, 17)):
            body.append(f'<text x="{x+cw/2:.1f}" y="{ty+j*15}" text-anchor="middle" font-size="9.5" fill="{mid}">{esc(line)}</text>')
    for i in range(n - 1):
        body.append(f'<line x1="{xs[i]+cw+2:.1f}" y1="{y+ch/2}" x2="{xs[i+1]-4:.1f}" y2="{y+ch/2}" stroke="{LINE}" stroke-width="1.5" marker-end="url(#a)"/>')
    body.append(f'<text x="30" y="{y+ch+42}" font-size="10" fill="{MUTED}">读法：从左到右是主路径；分支与失败语义回到正文，不在图里堆细节。</text>')
    return frame(title, sub, "\n".join(body), y + ch + 60)


def layers(items, title, sub):
    n = len(items)
    x, w, h, gap, y0 = 150, 700, 64, 18, 96
    body = []
    for i, (label, detail) in enumerate(items):
        y = y0 + i * (h + gap)
        fill, stroke, strong, mid = PALETTES[i % len(PALETTES)]
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        body.append(f'<text x="{x+18}" y="{y+26}" font-size="13" font-weight="700" fill="{strong}">{esc(label)}</text>')
        body.append(f'<text x="{x+18}" y="{y+47}" font-size="10" fill="{mid}">{esc(detail)}</text>')
        if i < n - 1:
            body.append(f'<line x1="{x+w/2}" y1="{y+h+1}" x2="{x+w/2}" y2="{y+h+gap-4}" stroke="{LINE}" stroke-width="1.5" marker-end="url(#a)"/>')
    return frame(title, sub, "\n".join(body), y0 + n * (h + gap) + 10)


def matrix(headers, rows, title, sub):
    ncol, nrow = len(headers), len(rows)
    m, y0, hh, rh = 30, 96, 40, 58
    tw = W - 2 * m
    cw = tw / ncol
    body = [f'<rect x="{m}" y="{y0}" width="{tw}" height="{hh}" rx="8" fill="#334155"/>']
    for c, head in enumerate(headers):
        body.append(f'<text x="{m+c*cw+cw/2:.1f}" y="{y0+25}" text-anchor="middle" font-size="10" font-weight="700" fill="#ffffff">{esc(head)}</text>')
    for r, row in enumerate(rows):
        y = y0 + hh + r * rh
        fill = "#ffffff" if r % 2 == 0 else "#f8fafc"
        body.append(f'<rect x="{m}" y="{y}" width="{tw}" height="{rh}" fill="{fill}" stroke="#e2e8f0"/>')
        for c, val in enumerate(row):
            body.append(f'<text x="{m+c*cw+10:.1f}" y="{y+22}" font-size="9.5" font-weight="700" fill="{INK}">{esc(val)}</text>')
            if c:
                body.append(f'<line x1="{m+c*cw:.1f}" y1="{y}" x2="{m+c*cw:.1f}" y2="{y+rh}" stroke="#e2e8f0"/>')
    return frame(title, sub, "\n".join(body), y0 + hh + nrow * rh + 20)


def panels(cards, title, sub, cols=2):
    n = len(cards)
    rows = (n + cols - 1) // cols
    m, gap, cw, ch, y0 = 30, 18, (W - 60 - 18) / 2, 128, 96
    if cols == 3:
        cw = (W - 60 - 2 * 18) / 3
    body = []
    for i, (head, detail) in enumerate(cards):
        r, c = divmod(i, cols)
        x = m + c * (cw + gap)
        y = y0 + r * (ch + gap)
        fill, stroke, strong, mid = PALETTES[i % len(PALETTES)]
        body.append(f'<rect x="{x:.1f}" y="{y}" width="{cw:.1f}" height="{ch}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        body.append(f'<text x="{x+16:.1f}" y="{y+28}" font-size="12" font-weight="700" fill="{strong}">{esc(head)}</text>')
        for j, line in enumerate(wrap(detail, 34 if cols == 2 else 24)[:5]):
            body.append(f'<text x="{x+16:.1f}" y="{y+50+j*16}" font-size="9.5" fill="{mid}">{esc(line)}</text>')
    height = y0 + rows * (ch + gap) + 8
    return frame(title, sub, "\n".join(body), height)


def build(spec):
    kind = spec["kind"]
    if kind == "flow":
        return flow(spec["nodes"], spec["title"], spec["sub"])
    if kind == "layers":
        return layers(spec["items"], spec["title"], spec["sub"])
    if kind == "matrix":
        return matrix(spec["headers"], spec["rows"], spec["title"], spec["sub"])
    if kind == "panels":
        return panels(spec["cards"], spec["title"], spec["sub"], spec.get("cols", 2))
    raise ValueError(f"unknown kind {kind}")


FIGURES = [
    # frontend
    {"page": "_digested/frontend/01-stream-pipeline.md", "file": "figures/stream-pipeline.svg", "kind": "flow",
     "title": "SSE → React：一条 run 的渲染管线", "sub": "事件先归一化，再进渲染态；gap 只触发重连，不重放本地状态。",
     "alt": "SSE 事件经过 useStream、stream-state、streamdown 到 React 提交的管线",
     "nodes": [("Gateway SSE", "values / messages / updates / custom / end"), ("useStream", "SDK 订阅；terminal run 短路"), ("stream-state", "reduce + message-order + gap 恢复"), ("streamdown", "增量 markdown / thinking / tool call"), ("React commit", "MessageList / Artifact / Todo / Goal")]},
    {"page": "_digested/frontend/03-state-management.md", "file": "figures/state-layers.svg", "kind": "matrix",
     "title": "四层状态：谁拥有、活多久、从哪来", "sub": "不要把服务器状态塞进 localStorage，也不要把 UI 偏好塞进 Query cache。",
     "alt": "TanStack Query、ThreadState、localStorage、URL 四层状态的拥有者与生命周期",
     "headers": ["层", "拥有者", "生命周期", "事实源"],
     "rows": [["TanStack Query", "core hooks", "请求 / 缓存", "Gateway API"], ["ThreadState", "workspace context", "run / thread", "SSE values"], ["localStorage", "settings/local.ts", "浏览器", "用户偏好"], ["URL / search", "Next.js router", "页面", "可分享状态"]]},
    {"page": "_digested/frontend/04-workspace-layout.md", "file": "figures/workspace-layout.svg", "kind": "panels",
     "title": "工作区布局：三栏与右面板四态", "sub": "右面板同一时刻只开一个：sidecar > browser > artifacts > details。",
     "alt": "工作区侧栏、聊天区、右面板四态与路由页面",
     "cards": [("Sidebar", "Threads / Projects / Channels / Capability Center；活动轮询收在一处。"), ("Chat", "MessageList + composer；上传在发送时触发。"), ("Right panel", "sidecar / browser / artifacts / details；移动端改 Sheet。"), ("Route surfaces", "capabilities、extensions、projects、trash、scheduled-tasks 各自有页面。")]},
    {"page": "_digested/frontend/07-feature-map.md", "file": "figures/feature-map.svg", "kind": "panels", "cols": 3,
     "title": "41 个 core 目录的六个功能簇", "sub": "先按簇定位，再进逐目录表；不要从组件名猜 owner。",
     "alt": "frontend/src/core 的六个功能簇：运行时、工作区、能力、知识、任务、平台",
     "cards": [("运行时 / 流", "threads · messages · streamdown · api · background-tasks"), ("工作区 / 布局", "projects · trash · scheduled-tasks · settings · workspace-changes"), ("能力 / 扩展", "capabilities · extensions · skills · mcp · agents"), ("知识 / 引用", "knowledge · citations · conversation-references · artifacts"), ("任务 / 子代理", "tasks · subagents · subagent-batches · todos · tools"), ("平台面", "auth · i18n · uploads · channels · notifications · voice-input")]},
    # getting-started
    {"page": "_digested/getting-started/02-configuration.md", "file": "figures/config-layers.svg", "kind": "layers",
     "title": "配置的四层：谁覆盖谁、何时生效", "sub": "环境变量 > config.yaml > 默认值；extensions_config.json 是 API 可写面。",
     "alt": "环境变量、config.yaml、extensions_config.json 与运行时快照的覆盖关系",
     "items": [("环境变量", "AUTH_JWT_SECRET、DEER_FLOW_*；部署身份与密钥优先"), ("config.yaml", "operator 控制；模型、沙箱、scheduler、plugins"), ("extensions_config.json", "MCP / skills / middlewares；Gateway API 可写"), ("运行时快照", "restart-required 字段在 lifespan 读一次；热字段按请求读")]},
    {"page": "_digested/getting-started/04-local-dev.md", "file": "figures/local-dev-topology.svg", "kind": "flow",
     "title": "本地拓扑：一个入口，三个服务", "sub": "浏览器只认 2026；Gateway 与 Frontend 不直接暴露给用户。",
     "alt": "浏览器、Nginx、Gateway、Frontend 与可选 Redis 的本地拓扑",
     "nodes": [("Browser", "localhost:2026"), ("Nginx", "静态前端 + /api 反代 + SSE"), ("Gateway", "127.0.0.1:8001；/api/langgraph 重写"), ("Frontend", "127.0.0.1:3000；Next.js"), ("Redis (可选)", "多 worker / stream bridge 时才需要")]},
    # observability
    {"page": "_digested/observability/01-logging-and-trace-context.md", "file": "figures/trace-context-flow.svg", "kind": "flow",
     "title": "trace_id 的一条链：从请求到日志", "sub": "ContextVar 是唯一源；响应头、日志、run metadata 都是派生输出。",
     "alt": "请求经过 TraceMiddleware、ContextVar 到日志、响应头与 run metadata 的链路",
     "nodes": [("HTTP request", "X-Trace-Id 可选"), ("TraceMiddleware", "归一化 / 铸造；无条件回写头"), ("ContextVar", "request / ensure / bind"), ("Logs + headers", "logging.enhance 只控日志字段"), ("run metadata", "runtime context / checkpoint / Langfuse")]},
    {"page": "_digested/observability/02-run-events-and-journal.md", "file": "figures/event-pipeline.svg", "kind": "flow",
     "title": "RunEvent 管线：从回调到可消费事件", "sub": "RunJournal 负责标准化与刷盘；RunEventStore 是 append-only 事实。",
     "alt": "LangChain callbacks、RunJournal、RunEventStore、SSE/Console 与审计回放的管线",
     "nodes": [("LangChain callbacks", "chain / llm / tool / error"), ("RunJournal", "缓冲、分类、seq、evidence"), ("RunEventStore", "memory / db / jsonl"), ("SSE + Console", "实时流、历史、调试端点"), ("审计 / 回放", "thread 删除、subagent、workspace")]},
    # test-strategy
    {"page": "_digested/test-strategy/00-overview.md", "file": "figures/test-ladder.svg", "kind": "layers",
     "title": "测试阶梯：从静态边界到跨栈 E2E", "sub": "越往下越慢；能用上层证明的，不要下沉到 E2E。",
     "alt": "静态边界、单元、确定性 LLM、契约跨栈、门禁元治理五层测试阶梯",
     "items": [("静态 / 边界", "import 边界、blocking IO、版本锁步、文档契约"), ("单元 / 属性", "pytest / rstest / hypothesis；纯函数优先"), ("确定性 LLM", "FakeToolCallingModel / ReplayChatModel / Monocle"), ("契约 / 跨栈", "contracts JSON 双端、Gateway conformance、replay E2E"), ("门禁 / 元治理", "CI 分片、label 声明、waiver 信任边界")]},
    {"page": "_digested/test-strategy/02-deterministic-llm.md", "file": "figures/deterministic-llm.svg", "kind": "flow",
     "title": "确定性 LLM 替身谱系", "sub": "同一条断言尽量在更便宜、更确定的一层证明。",
     "alt": "FakeToolCallingModel、ReplayChatModel、Monocle trace、手动录制与 CI 的确定性 LLM 替身谱系",
     "nodes": [("FakeToolCallingModel", "脚本化 tool_calls；零 I/O"), ("ReplayChatModel", "归一化输入哈希 + caller-aware key"), ("Monocle traces", "真实 trace 的行为断言"), ("手动录制", "golden JSON；形状断言"), ("CI 分片", "offline-first；live 仅显式 opt-in")]},
    {"page": "_digested/test-strategy/03-contract-e2e.md", "file": "figures/contract-e2e.svg", "kind": "flow",
     "title": "契约防线：同一份 JSON，两端各钉一次", "sub": "mock E2E 的 fake-green 由 replay real-backend 兜底。",
     "alt": "contracts JSON 经 backend pytest、frontend rstest、replay E2E 到缺口登记的契约防线",
     "nodes": [("contracts/*.json", "slash / subagent / run event / goal / origin"), ("backend pytest", "Pydantic / 路由 / 事件形状"), ("frontend rstest", "类型 / reducer / UI 消费"), ("replay E2E", "真前端 + 真 Gateway + ReplayChatModel"), ("缺口", "不是每个 contract 都有双端测试")]},
    # testing
    {"page": "_digested/testing/01-harness-boundary.md", "file": "figures/harness-boundary.svg", "kind": "flow",
     "title": "Harness/App 边界：静态扫描怎么挡", "sub": "边界不是口头约定；import 图与 blocking IO 都有机器检查。",
     "alt": "源码树经 AST 扫描、blocking IO 检测、CI 分片到修复的边界检查链",
     "nodes": [("源码树", "backend/packages/harness vs app"), ("AST 扫描", "禁止 app.* from harness"), ("Blocking IO", "静态检测 + runtime Blockbuster"), ("CI 分片", "backend-blocking-io 硬失败"), ("修复", "移到 app 或注入依赖")]},
    {"page": "_digested/testing/07-record-replay.md", "file": "figures/replay-flow.svg", "kind": "flow",
     "title": "Record/Replay：录一次，回放多次", "sub": "哈希按归一化输入，不按调用序号；system prompt 不进 key。",
     "alt": "record、normalize、fixture、replay、assert 五步的录制回放流程",
     "nodes": [("record", "真模型 + 真 Gateway"), ("normalize", "UUID / 时间 / 临时路径 / system"), ("fixture", "golden JSON + SSE 形状"), ("replay", "零 API key；caller-aware key"), ("assert", "事件序列 / golden shape")]},
    # governance
    {"page": "_digested/enterprise-it-governance/00-overview.md", "file": "figures/default-off-risk.svg", "kind": "matrix",
     "title": "默认关闭的四项控制：风险不是「没有」，是「没开」", "sub": "安全评审先看这四项，不要只看代码里有没有。",
     "alt": "Guardrails、token_budget、pii_redaction、authorization 四项控制的默认状态与风险",
     "headers": ["控制", "示例默认", "不开的后果", "评审动作"],
     "rows": [["Guardrails", "关闭（整块注释）", "工具级授权不生效", "确认部署配置"], ["token_budget", "enabled:false", "无 per-run 金额/Token 上限", "开启并设阈值"], ["pii_redaction", "enabled:false", "工具结果/PII 不脱敏", "按数据分级开启"], ["authorization.enabled", "false → 全 13 权限", "所有登录用户全放行", "启用 provider/角色"]]},
    {"page": "_digested/enterprise-it-governance/audit/04-event-coverage.md", "file": "figures/evidence-chain.svg", "kind": "flow",
     "title": "证据链：一次工具调用留下什么", "sub": "审计不是日志堆积；每一层要有可关联的 id 与结构化事件。",
     "alt": "请求、授权决策、工具调用、沙箱与证据落库组成的证据链",
     "nodes": [("request", "trace_id / user / thread / run"), ("authz decision", "allow/deny + reason"), ("tool call", "name / args hash / result status"), ("sandbox", "mode / path / exit code"), ("evidence", "run event + journal + audit")]},
]

FIGURES += [
    {"page": "_digested/enterprise-it-governance/00-overview.md", "file": "figures/governance-overview.svg", "kind": "matrix",
     "title": "12 个管理维度 × DeerFlow 能力映射", "sub": "每一维只回答：有什么机制、缺什么；具体证据回正文。",
     "alt": "12 个管理维度的能力与缺口矩阵",
     "headers": ["维度", "DeerFlow 能力", "缺口"],
     "rows": [
        ["身份与访问", "JWT / CSRF / internal / PAT / per-user 隔离", "无 Agent 独立身份"],
        ["沙箱隔离", "7 模式 / 路径防穿透 / per-thread", "Local 共享宿主内核"],
        ["工具授权", "Guardrail + 三道门", "无 per-thread 配置"],
        ["命令审计", "SandboxAudit 高危 block / 中危 warn", "规则硬编码；只写日志"],
        ["执行限额", "循环检测 / 并发 / token_budget / recursion", "无货币预算；顶层预算默认关"],
        ["内容安全", "SafetyFinishReason 被动清除", "无主动输出扫描"],
        ["审计追溯", "SandboxAudit + RunJournal + tracing", "allow 决策不留痕"],
        ["成本归属", "usage + subagent 合并 + Console 计价", "无实时告警/跨用户视图"],
        ["可观测性", "SSE + heartbeat + tracing", "无集群仪表盘/异常检测"],
        ["数据治理", "per-user 存储 / 脱敏 / 配额 / PII", "PII 默认关；无分类标签"],
        ["可靠性", "LLM/Tool error handling", "无 SLO / error budget"],
        ["生命周期", "热加载 / skills 生命周期 / grant", "无灰度 / 无 kill switch"],
     ]},
    {"page": "_digested/enterprise-it-governance/00-overview.md", "file": "figures/defense-in-depth.svg", "kind": "layers",
     "title": "纵深防线：从请求到 Tool 执行的七层", "sub": "自上而下是防线顺序；每层只回答“拦什么、失败怎么办”。",
     "alt": "请求、认证、授权、工具中介、沙箱、OS 出口、审计七层防线",
     "items": [
        ("Edge / Nginx", "入口限速、TLS、SSE 反代；不是身份边界"),
        ("Auth / CSRF", "JWT / PAT / internal token / IM；失败 401/403"),
        ("Authorization", "RBAC / Guardrail / MCP scope；fail-closed 可配"),
        ("Tool mediation", "receipt / read-before-write / artifact resolve"),
        ("Sandbox isolation", "sandbox mode + 路径检查 + per-thread"),
        ("OS / egress", "网络策略、受控出口、资源限额"),
        ("Audit / evidence", "RunEvent + Journal + SandboxAudit；可回放"),
     ]},
]


def main() -> int:
    if "--write" not in sys.argv and "--check" not in sys.argv:
        print("usage: figurekit.py --write|--check")
        return 2
    missing_refs = []
    for spec in FIGURES:
        page = os.path.join(ROOT, spec["page"])
        ref = spec["file"]
        if not os.path.isfile(page):
            missing_refs.append(f"{spec['page']}: page missing")
            continue
        if ref not in open(page, encoding="utf-8").read():
            missing_refs.append(f"{spec['page']}: missing image ref {ref}")
    if missing_refs:
        print("❌ page-first guard: figures without page refs")
        for m in missing_refs:
            print(" -", m)
        return 1
    if "--check" in sys.argv:
        print(f"✅ figurekit: {len(FIGURES)} specs all have page refs")
        return 0
    for spec in FIGURES:
        page = os.path.join(ROOT, spec["page"])
        target = os.path.join(os.path.dirname(page), spec["file"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        svg = build(spec)
        open(target, "w", encoding="utf-8").write(svg)
        print("wrote", os.path.relpath(target, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
