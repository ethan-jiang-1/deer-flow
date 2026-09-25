#!/usr/bin/env python3
"""Digest 一致性校验器 —— 把"源码 → digest"的机械核对固化成可重复运行的脚本。

用法（在仓库根运行）::

    python3 _digest/_upstream-sync/tools/check_digest.py          # 只报问题，有问题则退出码 1
    python3 _digest/_upstream-sync/tools/check_digest.py -v       # 连同已声明例外一起打印
    python3 _digest/_upstream-sync/tools/check_digest.py --only path,line_in_range

设计约定
--------
* **只读**：脚本不修改任何文件；它只报告，人工/agent 再决定怎么改。
* **基线是当前工作区源码**。`ethan` 分支的源码应当等于某个 upstream tag；跑之前先确认
  `git diff <tag> -- . ':(exclude)_digest' ':(exclude)_faq_on_digested'` 为空。
* 每条检查都区分"确定的问题"与"已声明例外"（外部库路径、示例占位符、历史同步记录等），
  后者只影响 `-v` 输出，不影响退出码。

九项检查
--------
1. `line_count`     —— `` `path`, N 行 `` 的文件长度断言 vs 实际（排除 `+N 行` 这类 diff 增量）。
2. `line_in_range`  —— `path:NNN` 的行号是否超出文件长度。
3. `dead_link`      —— markdown 相对链接目标是否存在。
4. `anchor`         —— `file.md#anchor` 的目标小节是否存在（容忍中英文标点）。
5. `path_exists`    —— 反引号里的路径式引用能否在源码树解析（含裸文件名唯一匹配）。
6. `env_var`        —— digest 里出现的 `UPPER_CASE` 变量是否在源码/配置里出现。
7. `camel_symbol`   —— 反引号里的 CamelCase 类名是否在源码里出现（发现的 `DeferredToolRegistry` 类问题）。
8. `module_class`   —— `deerflow.x.y:Class` 形式：模块是否存在、类是否定义。
9. `import_stmt`    —— `from deerflow… import …` / `from app… import …`：模块与符号是否存在。
10. `fence`         —— markdown 代码围栏奇偶（成对）。
"""

from __future__ import annotations

import argparse
import ast
import glob
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

DOC_GLOBS = ("_digest/**/*.md", "_faq_on_digested/**/*.md")
EXCLUDE_PARTS = ("/_upstream-sync/",)

# 源码树里可用于解析路径/模块的前缀（按优先级）
PATH_PREFIXES = (
    "",
    "backend/packages/harness/deerflow/",
    "backend/packages/extension-api/",
    "backend/app/",
    "backend/",
    "frontend/src/",
    "frontend/",
    "skills/",
    "scripts/",
    "docker/",
)
MODULE_BASES = ("backend/packages/harness", "backend/packages/extension-api", "backend")

# 只在源码树里查找的扩展名
SOURCE_EXTS = (".py", ".ts", ".tsx", ".yml", ".yaml", ".json", ".sh", ".toml", ".mdx", ".md")

# 外部/示例占位符：这些"解析不到"是预期的
PLACEHOLDER_PREFIXES = ("path/to", "some/", "your/", "example/", "my_", "app.xxx", "evals/", "workspace/", "repo_root/")
EXTERNAL_PATH_HINTS = (
    "langchain/", "langgraph/", "pregel/", "airflow/", "tests/cli/", "tests/",
    "deep_research_harness/", "backend/config.yaml", "scripts/run.sh", "scripts/chat.sh",
    "ai-elements/model-selector", "evals/evals.json", "workspace/results.json",
    # 沙箱运行时目录（由 install-shim 生成），不是仓库文件
    "bin/lark-cli",
)

# import 示例里的占位模块（教学用途，不是真实路径）
PLACEHOLDER_MODULE_HINTS = ("my_provider", "my_middleware", "app.xxx", "deerflow_middlewares", "my_company")

EXTERNAL_VAR_PREFIXES = (
    "LANG", "OPEN", "ANTHROPIC", "DEEP", "GEMINI", "QWEN", "MOONSHOT", "GLM", "KIMI",
    "VOLC", "ARK", "FEISHU", "WECOM", "DINGTALK", "TELEGRAM", "DISCORD", "SLACK",
    "NOSTR", "BUZZ", "LARK", "NEXT", "TURBO", "WEBPACK", "VITE", "TAVILY", "SEAR",
    "JINA", "RAG", "LIGHT", "HONCHO", "OPENVIKING", "BOX", "TENKI", "BROWSERLESS",
    "CRAWL", "GROUND", "INFOQUEST", "SERP", "SOFYA", "FIRECRAWL", "BRAVE", "DUCKDUCK",
    "CHROMA", "CURSOR", "MERMAID", "PLAYWRIGHT", "AWS", "GCP", "AZURE", "GITHUB_",
    "SLACK_", "CODEX_", "CLAUDE_", "TEAM_", "MY_", "PROD_", "MISSING_", "MAX_",
    "ALICE_", "SIEM", "SOAR", "SOC", "ISO", "RPITIT", "GSAP", "UUID", "JSON", "HTTP",
)

EXTERNAL_CLASS_PREFIXES = (
    "Lang", "Open", "Deep", "Claude", "Codex", "Gemini", "Qwen", "Mini", "Moonshot",
    "GLM", "Kimi", "Volc", "Ark", "Feishu", "WeCom", "DingTalk", "Telegram", "Discord",
    "Slack", "Nostr", "Buzz", "Lark", "Next", "Turbo", "Webpack", "Vite", "Anthropic",
    "Tavily", "Sear", "Jina", "RAG", "Light", "Honcho", "OpenViking", "Box", "Tenki",
    "Browserless", "Crawl", "Ground", "InfoQuest", "Serp", "Sofya", "Firecrawl",
    "Brave", "DuckDuck", "Chroma", "Airflow", "Cursor", "Mermaid", "Playwright",
    "FastAPI", "SQLAlchemy", "Pydantic", "Kubernetes", "Docker", "Postgre", "SQLite",
    "Redis", "Markdown", "Java", "TypeScript", "GitHub", "WebSocket", "OpenAPI",
    "OAuth", "Context", "Tool", "Agent", "Run", "Thread", "Stream", "Memory", "Skill",
    "Deferred", "Command", "Message", "Injected", "Provider", "Ephemeral", "Private",
    "AIMessage", "HumanMessage", "State", "Store", "Base", "Todo", "Title", "View",
    "Upload", "Sandbox", "Guardrail", "Loop", "Mcp", "MCP", "Token", "Delegation",
    "Durable", "Monocle", "LangSmith", "Singleton", "Json", "SafeJson", "Nginx",
    "WeChat", "Wecom", "Pre", "Post", "Session", "User", "File", "Worktree",
    "Instruction", "Cwd", "Stop", "Subagent", "Configured", "InMemory", "Notion",
    "Graph", "Channel", "Extension", "Admission", "Redact", "Secret",
)

LINE_COUNT_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|ts|tsx|yml|yaml|json|md|mdx|sh|toml))`([^\n`]{0,20}?)(\d{2,6})\s*行")
LINE_RANGE_RE = re.compile(r"第\s*\d+\s*[-–~]\s*\d+\s*行|L\d+\s*[-–~]\s*L?\d+")
DELTA_HINTS = ("大改", "净增", "净 +", "本轮", "涨了", "新增", "减少了", "去掉", "→", "->", "曾", "记为", "旧文档", "此前")
LINE_REF_RE = re.compile(r"`?([A-Za-z0-9_./-]+\.(?:py|ts|tsx|yml|yaml))`?:(\d{1,5})")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
ANCHOR_RE = re.compile(r"\[[^\]]*\]\(([^)\s]*#[^)\s]+)\)")
PATH_TOK_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|ts|tsx|yml|yaml|json|mdx|sh|toml))`")
ENV_RE = re.compile(r"\b((?:DEER_FLOW|GATEWAY|AUTH|BETTER_AUTH|LANGSMITH|LANGFUSE|MONOCLE|DATABASE|POSTGRES|PROVISIONER|SANDBOX|DEERFLOW)[A-Z0-9_]*|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_(?:KEY|TOKEN|SECRET|URL|URI|ID|HOST|PATH|DIR|PORT|ENABLED|DISABLED|TRACING|HOME|ROOT|IMAGE|VERSION|ENDPOINT|BASE|ACCOUNT|WEBHOOK|PASSWORD|DSN|REGION|BUCKET|QUEUE|WORKERS|TIMEOUT|LIMIT|MODE))\b")
CAMEL_RE = re.compile(r"`([A-Z][A-Za-z0-9_]{6,})`")
MODCLASS_RE = re.compile(r"\b((?:deerflow|app)(?:\.[a-z_][a-z0-9_]*)+):([A-Z][A-Za-z0-9_]*)")
IMPORT_RE = re.compile(r"from\s+((?:deerflow|app)(?:\.[a-z_][a-z0-9_]*)+)\s+import\s+([A-Za-z_][A-Za-z0-9_,\s]*)")

# `symbol` … `file.py:NN`（符号紧邻引用，最多跨 8 个非括号字符）
STRICT_REF_RE = re.compile(r"`([a-z_][a-z0-9_]{5,})`[^\n]{0,8}?`([A-Za-z0-9_./-]+\.py)`?:(\d{1,5})")

# 明确忽略的"看起来像但确实不是"的记号
IGNORE_ENV = {
    "SYNC_LOG", "PR_NUMBER", "ISSUE_NUMBER", "ISSUES_FOUND", "GITHUB_REF_NAME",
    "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "CUSTOM_OPENAI_BASE", "PROD_DB_URL",
    "PROD_OPENAI_KEY", "MAX_SKILL_TOKENS", "MISSING_VAR", "MY_CLIENT_ID",
    "MY_PROVIDER_API_KEY", "AZURE_ENDPOINT", "TEAM_GUIDE", "CODEX_HOME",
    "CODEX_SANDBOX_NETWORK_DISABLED", "SPAWN", "PASS2", "CACHE2", "TOOLS2", "TOOLS3",
    "JSON1", "JSON2", "JSON3", "STREAMING_CHANNELS", "BLOCKED_PATTERN",
    "NOT_IN_ALLOWLIST", "IMPLEMENTED", "TUPLE", "STRIP", "ELSE", "FSTAT", "LSTAT",
    "DIALECT", "STATS", "LBRID", "UUID4", "WSGI", "BILLING", "CLOSE_MODE", "OPEN_MODE",
    "BACKUP_DIR", "TAG_VERSION", "EXPECTED_COUNT",
}
IGNORE_CLASSES = {
    "OBSERVABILITY", "STANDARD", "PLACEMENT", "IMPLEMENTED", "SESSIONSTART",
    "PRETOOLUSE", "POSTTOOLUSE", "USERPROMPTSUBMIT", "SUBAGENTSTART",
    "RequestValidationError", "HTTPException", "ValidationError",
}

# line_symbol 启发式里忽略的通用词（不是"该行应该定义的符号"）
IGNORE_SYMBOLS = {
    "context", "runtime", "request", "config", "state", "value", "values", "messages",
    "message", "content", "metadata", "payload", "schema", "client", "server", "version",
    "default", "response", "thread_id", "run_id", "user_id", "trace_id", "session_id",
    "group", "action", "method", "path", "types", "events", "tools", "model", "models",
    "agent", "agents", "skills", "memory", "sandbox", "router", "status", "error",
}

PUNCT = "`*_[]()（）:：.,，。、/?!？!;；'\"“”‘’"
# 误报率高的启发式检查：默认不跑，只允许 --only 显式调用
HEURISTIC_CHECKS = {"line_symbol", "line_symbol_strict"}
# 注意：`_` 在 GitHub slug 里保留，因此 slug() 使用单独的标点表
SLUG_PUNCT = "`*[]()（）:：.,，。、/?!？!;；'\"“”‘’—–"


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT)


def docs() -> list[str]:
    out: list[str] = []
    for pattern in DOC_GLOBS:
        out += glob.glob(os.path.join(ROOT, pattern), recursive=True)
    return sorted(p for p in out if not any(x in p for x in EXCLUDE_PARTS))


def build_indexes():
    """basename -> [paths] for source files, plus a concatenated corpus for symbol checks."""
    index: dict[str, list[str]] = defaultdict(list)
    corpus: list[str] = []
    for base in ("backend", "frontend", "scripts", "docker", "deploy", "skills", "contracts", "docs"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, base)):
            if any(x in dirpath for x in ("/node_modules", "/.git", "/.next", "/.venv", "__pycache__", "/dist")):
                continue
            for name in filenames:
                if not name.endswith(SOURCE_EXTS):
                    continue
                full = os.path.join(dirpath, name)
                index[name].append(full)
                try:
                    corpus.append(open(full, encoding="utf-8", errors="ignore").read())
                except OSError:
                    pass
    for name in ("config.example.yaml", "extensions_config.example.json", "AGENTS.md", "README.md", "Makefile", ".env.example"):
        full = os.path.join(ROOT, name)
        if os.path.isfile(full):
            corpus.append(open(full, encoding="utf-8", errors="ignore").read())
    return index, "\n".join(corpus)


def resolve_path(token: str, index: dict[str, list[str]]) -> str | None:
    p = token.lstrip("./")
    for prefix in PATH_PREFIXES:
        if os.path.exists(os.path.join(ROOT, prefix + p)):
            return prefix + p
    candidates = index.get(os.path.basename(p), [])
    if len(candidates) == 1:
        return rel(candidates[0])
    suffix = [c for c in candidates if c.endswith("/" + p)]
    return rel(suffix[0]) if len(suffix) == 1 else None


def resolve_module(mod: str) -> str | None:
    p = mod.replace(".", "/")
    for base in MODULE_BASES:
        for candidate in (os.path.join(ROOT, base, p + ".py"), os.path.join(ROOT, base, p, "__init__.py")):
            if os.path.isfile(candidate):
                return candidate
    return None


def is_placeholder(token: str) -> bool:
    return token.startswith(PLACEHOLDER_PREFIXES) or any(h in token for h in EXTERNAL_PATH_HINTS)


def slug(heading: str) -> str:
    text = heading.strip().lower()
    for ch in SLUG_PUNCT:
        text = text.replace(ch, "")
    return text.replace(" ", "-")


def check_all(verbose: bool, only: set[str] | None) -> list[tuple[str, str]]:
    """Return [(check_name, message)] for real problems only."""
    index, corpus = build_indexes()
    findings: list[tuple[str, str]] = []
    exceptions: list[tuple[str, str]] = []

    def enabled(name: str) -> bool:
        # 两个启发式检查误报率高（文档常写行区间/一句多符号），默认不跑，只允许 --only 显式调用
        if only is None and name in HEURISTIC_CHECKS:
            return False
        return only is None or name in only

    for doc in docs():
        rel_doc = rel(doc)
        try:
            text = open(doc, encoding="utf-8").read()
        except OSError:
            continue
        lines = text.splitlines()

        # 10. fences
        if enabled("fence"):
            fences = sum(1 for ln in lines if ln.startswith("```"))
            if fences % 2:
                findings.append(("fence", f"{rel_doc}: 代码围栏数为奇数（{fences}）"))

        # 1 + 2: line count / line range
        for no, line in enumerate(lines, 1):
            if enabled("line_count"):
                for m in LINE_COUNT_RE.finditer(line):
                    token, between, claimed = m.group(1), m.group(2), int(m.group(3))
                    # 跳过 diff 增量（+N 行 / 大改 / 涨了）与行号区间（第 93-100 行）
                    if "+" in between or any(h in line for h in DELTA_HINTS) or LINE_RANGE_RE.search(line):
                        exceptions.append(("line_count", f"{rel_doc}:{no} 跳过增量/区间断言: {m.group(0)[:60]}"))
                        continue
                    # 裸文件名有歧义时跳过（同名的 storage.py 可能指不同模块）
                    if "/" not in token and len(index.get(token, [])) != 1:
                        exceptions.append(("line_count", f"{rel_doc}:{no} 同名文件不唯一，跳过: {token}"))
                        continue
                    target = resolve_path(token, index)
                    if not target:
                        continue
                    actual = sum(1 for _ in open(os.path.join(ROOT, target), encoding="utf-8"))
                    if actual != claimed:
                        findings.append(("line_count", f"{rel_doc}:{no} {target} 声称 {claimed} 行，实际 {actual}"))
            if enabled("line_in_range"):
                for m in LINE_REF_RE.finditer(line):
                    token, n = m.group(1), int(m.group(2))
                    target = resolve_path(token, index)
                    if not target:
                        continue
                    total = sum(1 for _ in open(os.path.join(ROOT, target), encoding="utf-8"))
                    if n > total:
                        findings.append(("line_in_range", f"{rel_doc}:{no} {target}:{n} 超出文件长度 {total}"))

            # 启发式（严格版）：形如 `symbol` ... `file.py:NN` 的紧邻引用，
            # 若符号既不在该行附近、又在文件别处 → 疑似 in-range 错行。
            # 文档常写行区间（`:A-B`）或一句多个符号，因此这里对区间做整体搜索，
            # 并在同一句出现同文件多个引用时跳过（配对歧义）。
            if enabled("line_symbol_strict"):
                for m in STRICT_REF_RE.finditer(line):
                    sym, token, n = m.group(1), m.group(2), int(m.group(3))
                    target = resolve_path(token, index)
                    if not target or sym in IGNORE_SYMBOLS:
                        continue
                    same_file_refs = sum(1 for mm in LINE_REF_RE.finditer(line) if mm.group(1) == token)
                    if same_file_refs > 1:
                        continue
                    tail = line[m.end():m.end() + 8]
                    end = n
                    rm = re.match(r"\s*[-–~]\s*(\d{1,5})", tail)
                    if rm:
                        end = int(rm.group(1))
                    src_lines = open(os.path.join(ROOT, target), encoding="utf-8", errors="ignore").read().splitlines()
                    if n > len(src_lines):
                        continue
                    end = min(end, len(src_lines))
                    whole = "\n".join(src_lines)
                    if sym not in whole:
                        continue  # 由 camel_symbol / 语义检查负责
                    window = "\n".join(src_lines[max(0, n - 4):min(len(src_lines), end + 2)])
                    if sym in window:
                        continue
                    findings.append(("line_symbol_strict", f"{rel_doc}:{no} `{sym}` 引用 {target}:{n}-{end}，但该符号不在此处（需人工判断）"))

            # 启发式：行号合法但指向错误位置（默认不跑，--only line_symbol 专项审计）
            if enabled("line_symbol"):
                for m in LINE_REF_RE.finditer(line):
                    token, n = m.group(1), int(m.group(2))
                    target = resolve_path(token, index)
                    if not target:
                        continue
                    src_lines = open(os.path.join(ROOT, target), encoding="utf-8", errors="ignore").read().splitlines()
                    if n > len(src_lines):
                        continue
                    window = "\n".join(src_lines[max(0, n - 2):n + 1])
                    named = [
                        s for s in (mm.group(1) for mm in CAMEL_RE.finditer(line))
                        if s not in ("L%s" % n,)
                    ] + [
                        s for s in re.findall(r"`([a-z_][a-z0-9_]{5,})`", line)
                    ]
                    named = [s for s in named if s not in IGNORE_SYMBOLS]
                    if not named:
                        continue
                    whole = "\n".join(src_lines)
                    if any(s in window for s in named):
                        continue
                    if all(s not in whole for s in named):
                        continue  # 全文件都没有 → 由 camel_symbol/其它检查负责
                    findings.append(("line_symbol", f"{rel_doc}:{no} {target}:{n} 附近未出现同句符号 {','.join(named[:3])}（需人工判断）"))

            if enabled("dead_link"):
                for m in LINK_RE.finditer(line):
                    t = m.group(1)
                    if t.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    target = os.path.normpath(os.path.join(os.path.dirname(doc), t.split("#")[0]))
                    if t.split("#")[0] and not os.path.exists(target):
                        findings.append(("dead_link", f"{rel_doc}:{no} -> {t}"))

            if enabled("anchor"):
                for m in ANCHOR_RE.finditer(line):
                    t = m.group(1)
                    path, anchor = t.split("#", 1)
                    target = os.path.normpath(os.path.join(os.path.dirname(doc), path)) if path else doc
                    if not os.path.isfile(target):
                        continue
                    heads = [slug(h) for h in re.findall(r"^#+\s+(.+)$", open(target, encoding="utf-8").read(), re.M)]
                    if anchor not in heads:
                        findings.append(("anchor", f"{rel_doc}:{no} -> {t} 目标小节不存在"))

            if enabled("path_exists"):
                for m in PATH_TOK_RE.finditer(line):
                    token = m.group(1)
                    if "/" not in token or is_placeholder(token):
                        exceptions.append(("path_exists", f"{rel_doc}:{no} 已声明例外: {token}"))
                        continue
                    if not resolve_path(token, index):
                        findings.append(("path_exists", f"{rel_doc}:{no} -> {token}"))

            if enabled("env_var"):
                for m in ENV_RE.finditer(line):
                    var = m.group(1)
                    if var in corpus or var in IGNORE_ENV or var.startswith(EXTERNAL_VAR_PREFIXES):
                        continue
                    findings.append(("env_var", f"{rel_doc}:{no} -> {var}"))

            if enabled("camel_symbol"):
                for m in CAMEL_RE.finditer(line):
                    sym = m.group(1)
                    if sym in corpus or sym in IGNORE_CLASSES or sym.startswith(EXTERNAL_CLASS_PREFIXES):
                        continue
                    findings.append(("camel_symbol", f"{rel_doc}:{no} -> {sym}"))

            if enabled("module_class"):
                for m in MODCLASS_RE.finditer(line):
                    mod, cls = m.group(1), m.group(2)
                    target = resolve_module(mod)
                    if not target:
                        findings.append(("module_class", f"{rel_doc}:{no} -> {mod}:{cls}（模块不存在）"))
                    elif cls not in open(target, encoding="utf-8").read():
                        findings.append(("module_class", f"{rel_doc}:{no} -> {mod}:{cls}（类未定义）"))

            if enabled("import_stmt"):
                for m in IMPORT_RE.finditer(line):
                    mod, syms = m.group(1), m.group(2)
                    if any(h in mod for h in PLACEHOLDER_MODULE_HINTS):
                        exceptions.append(("import_stmt", f"{rel_doc}:{no} 占位模块，跳过: {mod}"))
                        continue
                    target = resolve_module(mod)
                    if not target:
                        findings.append(("import_stmt", f"{rel_doc}:{no} -> from {mod} import …（模块不存在）"))
                        continue
                    src = open(target, encoding="utf-8").read()
                    for sym in (s.strip() for s in syms.split(",") if s.strip()):
                        if sym not in src:
                            findings.append(("import_stmt", f"{rel_doc}:{no} -> {mod} 缺符号 {sym}"))

    if verbose:
        for name, msg in exceptions:
            print(f"[{name}] 例外 {msg}")
        print(f"（已声明例外 {len(exceptions)} 条，未计入退出码）\n")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest 一致性校验器")
    parser.add_argument("-v", "--verbose", action="store_true", help="同时打印已声明例外")
    parser.add_argument("--only", default="", help="只跑指定检查，逗号分隔")
    args = parser.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    findings = check_all(args.verbose, only)
    if not findings:
        print("✅ 全部检查通过（无问题）")
        return 0

    grouped: dict[str, list[str]] = defaultdict(list)
    for name, msg in findings:
        grouped[name].append(msg)
    total = 0
    for name in sorted(grouped):
        print(f"❌ [{name}] {len(grouped[name])} 处")
        for msg in grouped[name]:
            print(f"   - {msg}")
        total += len(grouped[name])
    print(f"\n共 {total} 处问题。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
