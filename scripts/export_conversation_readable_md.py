"""Export agent transcript to human-readable Markdown.

Strips machine-oriented tags, internal reasoning stubs, and metadata fields.
Keeps substantive user queries and assistant replies (Chinese / Markdown).

Usage:
  python scripts/export_conversation_readable_md.py
  python scripts/export_conversation_readable_md.py -o CONVERSATION_EXPORT_d6e23c24.md
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import export_conversation_transcript as ect

SKIP_USER_PHRASES = (
    "Briefly inform the user about the task result",
    "If the available MCP tools",
    "Your conversation was summarized",
)

_TAG_RE = re.compile(
    r"<(?:user_query|timestamp|agent_skills|mcp_file_system|"
    r"agent_transcripts|system_reminder|committing-changes-with-git|"
    r"creating-pull-requests|open_and_recently_viewed_files)[^>]*>.*?"
    r"</(?:user_query|timestamp|agent_skills|mcp_file_system|"
    r"agent_transcripts|system_reminder|committing-changes-with-git|"
    r"creating-pull-requests|open_and_recently_viewed_files)>",
    re.DOTALL | re.IGNORECASE,
)
_SELF_CLOSE_TAG_RE = re.compile(
    r"<(?:user_query|timestamp|agent_skills|mcp_file_system|"
    r"system_reminder)[^>]*/>",
    re.IGNORECASE,
)
_BARE_TAG_RE = re.compile(
    r"</?(?:user_query|timestamp|agent_skills|mcp_file_system|"
    r"system_reminder|open_and_recently_viewed_files)[^>]*>",
    re.IGNORECASE,
)
_REDACTED_RE = re.compile(r"\[REDACTED\]", re.IGNORECASE)

# English-only internal reasoning (one-liner stubs, not user-facing prose)
_EN_THINKING = re.compile(
    r"^(?:I'm |I am |I'll |Let me |Now I |The user |I need to |I should |"
    r"I've |I will |Looking at |Checking |Reading |Searching |"
    r"Good, |Great, |OK, |Okay, |Wait, |Hmm, |Also |Next, |"
    r"First, |Since |Given |To do this|To verify|To check|"
    r"Smoke passes|Let me compile|Let me run|Let me check|"
    r"Let me read|Let me look|Let me find|Let me write|"
    r"Let me add|Let me update|Let me implement|Let me monitor|"
    r"Let me wait|Let me grep|Let me inspect|Let me document|"
    r"RareArena|Phase-B|Smoke test|All prior tests|Both items|"
    r"Two items|I'll parallel|I'll write|I'll create|I'll add|"
    r"I'll run|I'll compile|I'll grep|I'll read|I'll check|"
    r"I'll implement|I'll document|I'll monitor|I'll wait|"
    r"I'll launch|I'll fix|I'll harden|I'll wire|"
    r"Proceeding with|Starting with|Launching|Running|"
    r"Now wire|Now verify|Now let|Now the|Now implement|"
    r"CR source|LR fix|Gate arm|baseline arm|"
    r"This is |That is |It looks |It seems |"
    r"There is |There are |Here is |Here are )",
    re.IGNORECASE,
)

_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")


def strip_tags(text: str) -> str:
    t = _TAG_RE.sub("", text)
    t = _SELF_CLOSE_TAG_RE.sub("", t)
    t = _BARE_TAG_RE.sub("", t)
    t = _REDACTED_RE.sub("", t)
    # common system-injected blocks
    for marker in (
        "If the available MCP tools",
        "Your conversation was summarized",
        "Follow ALL user, tool, system",
        "IMPORTANT: This is a real environment",
        "When communicating with the user:",
    ):
        if marker in t:
            idx = t.find(marker)
            t = t[:idx].rstrip()
    return t.strip()


def clean_user(text: str) -> str:
    t = strip_tags(text)
    t = re.sub(r"\n{3,}", "\n\n", t)
    if any(s in t for s in SKIP_USER_PHRASES):
        return ""
    return t.strip()


def _cjk_score(text: str) -> int:
    return len(_HAS_CJK.findall(text))


def _pick_best_assistant(blocks: list[str]) -> str:
    """Prefer the block richest in Chinese / Markdown structure."""
    cleaned = [clean_assistant(b) for b in blocks if b]
    cleaned = [c for c in cleaned if c]
    if not cleaned:
        return ""
    return max(cleaned, key=lambda t: (_cjk_score(t), len(t)))


def _is_internal_paragraph(p: str) -> bool:
    p = p.strip()
    if not p:
        return True
    if p.startswith("> 🔧") or p.startswith("🔧"):
        return True
    if p.startswith("> ") and _EN_THINKING.match(p[2:]):
        return True
    # drop long English-only prose without markdown structure
    if not _HAS_CJK.search(p):
        has_md = any(c in p for c in "#|*`[]")
        if not has_md and len(p) > 40:
            return True
        if _EN_THINKING.match(p):
            return True
        if len(p) < 120 and not has_md:
            if re.match(r"^[A-Za-z0-9\s,.'\"():\-/\\]+$", p):
                return True
    return False


def clean_assistant(text: str) -> str:
    t = strip_tags(text)
    t = re.sub(r"\n{3,}", "\n\n", t)
    # drop tool-call summary lines
    lines: list[str] = []
    for line in t.splitlines():
        s = line.strip()
        if s.startswith("> 🔧") or s.startswith("🔧 `"):
            continue
        if s == "[REDACTED]" or s == "…":
            continue
        lines.append(line)
    t = "\n".join(lines).strip()

    # paragraph-level filter for mixed EN thinking + CN answer
    paras = re.split(r"\n\n+", t)
    kept: list[str] = []
    for p in paras:
        if _is_internal_paragraph(p):
            continue
        kept.append(p)
    return "\n\n".join(kept).strip()


def export_readable_md(out_path: Path) -> Path:
    src_json = ect.OUT_DIR / f"conversation_export_{ect.CONV_ID[:8]}_complete.json"
    if not src_json.exists():
        ect.export("complete")
    data = json.loads(src_json.read_text(encoding="utf-8"))
    pairs = data.get("qa_pairs") or []
    stats = data.get("meta", {}).get("statistics", {})

    lines: list[str] = [
        "# AgentClinic Tree-Dx 对话记录（人类可读版）",
        "",
        f"> 导出时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"> 共 **{len(pairs)}** 轮问答（源 transcript {stats.get('total_transcript_lines', '?')} 行）",
        "",
        "说明：已移除 XML 标签、系统注入块、工具调用中间步骤、英文内部推理片段，"
        "以及 transcript 行号等技术字段。保留用户提问与助手面向用户的实质性回复。",
        "",
        "---",
        "",
    ]

    for p in pairs:
        turn = p["turn"]
        user = clean_user(p["user"])
        blocks = p.get("assistant_all_blocks") or []
        if p.get("assistant"):
            blocks = blocks + [p["assistant"]]
        assistant = _pick_best_assistant(blocks)
        if not user:
            # system notification turn — skip unless assistant has real content
            if not assistant or _cjk_score(assistant) < 20:
                continue
            user = "（系统通知轮，无用户正文）"
        lines.extend([f"## 第 {turn} 轮", "", "### 用户", "", user, ""])
        if assistant:
            lines.extend(["### 助手", "", assistant, ""])
        else:
            lines.extend(["### 助手", "", "（该轮无保留的正文回复）", ""])
        lines.extend(["---", ""])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("CONVERSATION_EXPORT_d6e23c24_readable.md"),
        help="输出 Markdown 路径",
    )
    args = ap.parse_args()
    out = export_readable_md(args.output)
    n_lines = sum(1 for _ in out.open(encoding="utf-8"))
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB, {n_lines} lines, "
          f"{out.read_text(encoding='utf-8').count('## 第')} turns)")


if __name__ == "__main__":
    main()
