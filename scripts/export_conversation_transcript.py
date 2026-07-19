"""Export Cursor agent transcript JSONL to frontend-safe JSON.

Modes:
  --scope thread   L3370+ snippet/RAG sub-thread (default for *_full.json)
  --scope complete Entire session from line 1 (for *_complete.json)

Usage:
  python scripts/export_conversation_transcript.py --scope complete
  python scripts/export_conversation_transcript.py --scope thread
  python scripts/export_conversation_transcript.py --to-md data/cpg/eval/conversation_export_d6e23c24_complete.json
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CONV_ID = "d6e23c24-82b3-4786-a36b-03356b21f410"
TRANSCRIPT = Path(
    "/home/wanghongyi/.cursor/projects/data2-wanghongyi-Agentclinic-Tree-Dx-Spec/"
    f"agent-transcripts/{CONV_ID}/{CONV_ID}.jsonl"
)
OUT_DIR = Path("data/cpg/eval")

THREAD_MARKERS = (
    "snippet_on_topic()的过滤标准",
    "≤24 条短摘要",
    "24条短摘要",
)

SKIP_USER = (
    "If the available MCP tools",
    "Your conversation was summarized",
    "<agent_skills",
    "<mcp_file_system",
)


def user_query(text: str) -> str | None:
    m = re.search(r"<user_query>\s*(.*?)\s*</user_query>", text, re.DOTALL)
    q = (m.group(1) if m else text).strip()
    q = re.sub(r"<timestamp>.*?</timestamp>\s*", "", q, flags=re.DOTALL).strip()
    if any(s in q for s in SKIP_USER):
        return None
    return q or None


def assistant_text(obj: dict) -> str:
    msg = obj.get("message") or {}
    parts = msg.get("content") or [] if isinstance(msg, dict) else []
    return "\n".join(
        p.get("text", "")
        for p in parts
        if isinstance(p, dict) and p.get("type") == "text"
    )


def clean_assistant(t: str) -> str:
    t = t.strip()
    t = re.sub(r"\n\[REDACTED\]\s*$", "", t)
    t = re.sub(r"^\[REDACTED\]\s*", "", t)
    return t.strip()


def is_substantive_assistant(t: str) -> bool:
    t = clean_assistant(t)
    if not t:
        return False
    return len(t) >= 80 or "##" in t or "**" in t


def find_thread_start(events: list[dict]) -> int:
    for e in events:
        if e["role"] != "user":
            continue
        raw = e["raw"]
        content = raw.get("message", {}).get("content", [])
        if not content:
            continue
        q = user_query(content[0].get("text", ""))
        if q and any(k in q for k in THREAD_MARKERS):
            return e["line"]
    return 1


def load_events() -> list[dict]:
    events: list[dict] = []
    with TRANSCRIPT.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            events.append({
                "line": line_no,
                "role": o.get("role"),
                "raw": o,
                "text": assistant_text(o) if o.get("role") == "assistant" else "",
            })
    return events


def pair_qa(thread: list[dict]) -> list[dict]:
    pairs: list[dict] = []
    current_q: str | None = None
    current_user_line: int | None = None
    assistant_chunks: list[str] = []

    def flush_pair() -> None:
        nonlocal current_q, current_user_line, assistant_chunks
        if current_q is None:
            return
        blocks = [clean_assistant(t) for t in assistant_chunks]
        blocks = [t for t in blocks if is_substantive_assistant(t)]
        best = max(blocks, key=len) if blocks else ""
        pairs.append({
            "turn": len(pairs) + 1,
            "user": current_q,
            "assistant": best,
            "assistant_all_blocks": blocks,
            "user_source_line": current_user_line,
        })
        current_q = None
        current_user_line = None
        assistant_chunks = []

    for e in thread:
        if e["role"] == "user":
            raw_msg = e["raw"]["message"]["content"][0]["text"]
            q = user_query(raw_msg)
            if q is None:
                continue
            if current_q == q:
                continue
            if current_q is not None and current_q != q:
                flush_pair()
            if current_q is None:
                current_q = q
                current_user_line = e["line"]
        elif e["role"] == "assistant" and current_q is not None:
            assistant_chunks.append(e["text"])

    flush_pair()
    return pairs


def build_messages(pairs: list[dict]) -> list[dict]:
    messages: list[dict] = []
    for p in pairs:
        messages.append({
            "turn": p["turn"],
            "role": "user",
            "content": p["user"],
            "source_line": p["user_source_line"],
        })
        if p["assistant"]:
            messages.append({
                "turn": p["turn"],
                "role": "assistant",
                "content": p["assistant"],
                "all_blocks": p["assistant_all_blocks"],
            })
    return messages


def export(scope: str) -> tuple[Path, Path]:
    if not TRANSCRIPT.exists():
        raise SystemExit(f"Transcript not found: {TRANSCRIPT}")

    events = load_events()
    start = 1 if scope == "complete" else find_thread_start(events)
    thread = [e for e in events if e["line"] >= start]

    if scope == "complete":
        out_json = OUT_DIR / f"conversation_export_{CONV_ID[:8]}_complete.json"
        out_jsonl = OUT_DIR / f"conversation_export_{CONV_ID[:8]}_complete.jsonl"
        scope_label = "full_session"
    else:
        out_json = OUT_DIR / f"conversation_export_{CONV_ID[:8]}_full.json"
        out_jsonl = OUT_DIR / f"conversation_export_{CONV_ID[:8]}_thread.jsonl"
        scope_label = "thread_L3370+"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for e in thread:
            f.write(json.dumps(e["raw"], ensure_ascii=False) + "\n")

    pairs = pair_qa(thread)
    messages = build_messages(pairs)
    raw_events = [{"line": e["line"], "role": e["role"], "object": e["raw"]} for e in thread]

    export_doc = {
        "meta": {
            "conversation_id": CONV_ID,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "2.3",
            "scope": scope_label,
            "language": "zh-CN",
            "source_transcript": str(TRANSCRIPT),
            "companion_jsonl": str(out_jsonl),
            "thread_start_line": start,
            "statistics": {
                "total_transcript_lines": len(events),
                "exported_events": len(thread),
                "qa_pairs": len(pairs),
                "messages_chronological": len(messages),
            },
            "usage": {
                "messages_chronological": "推荐前端渲染：按轮次 user/assistant 交替，assistant 为完整正文",
                "raw_events": "导出范围内全部原始 JSON 对象（与 companion jsonl 等价）",
                "companion_jsonl": "原始 JSONL，一行一事件，适合流式解析",
                "qa_pairs": "去重后的 Q&A；assistant 取该轮最长实质性 Markdown 块",
            },
            "related_exports": {
                "thread_json": "data/cpg/eval/conversation_export_d6e23c24_full.json",
                "thread_dialogue_md": "data/cpg/eval/conversation_export_d6e23c24_dialogue.md",
                "complete_json": "data/cpg/eval/conversation_export_d6e23c24_complete.json",
            },
            "redaction_note": (
                "Transcript 中部分事件含 [REDACTED]（Cursor 对 tool 步骤脱敏）；"
                "最终回答正文已保留在 messages_chronological。"
            ),
        },
        "messages_chronological": messages,
        "qa_pairs": pairs,
        "raw_events": raw_events,
    }

    with out_json.open("w", encoding="utf-8") as f:
        json.dump(export_doc, f, ensure_ascii=False, indent=2)

    json.loads(out_json.read_text("utf-8"))
    return out_json, out_jsonl


def json_to_dialogue_md(src_json: Path, out_md: Path | None = None) -> Path:
    """Render messages_chronological from export JSON as readable Markdown."""
    data = json.loads(src_json.read_text(encoding="utf-8"))
    meta = data["meta"]
    msgs = data["messages_chronological"]
    scope = meta.get("scope", "unknown")
    stats = meta.get("statistics", {})
    qa_pairs = stats.get("qa_pairs", len(data.get("qa_pairs", [])))

    if out_md is None:
        stem = src_json.stem
        if stem.endswith("_complete"):
            out_md = src_json.with_name(stem.replace("_complete", "_complete_dialogue") + ".md")
        elif stem.endswith("_full"):
            out_md = src_json.with_name(stem.replace("_full", "_dialogue") + ".md")
        else:
            out_md = src_json.with_suffix(".md")

    if scope == "full_session":
        title = f"对话导出：全会话（transcript L1+，{qa_pairs} 轮）"
    elif scope == "thread_L3370+":
        title = "对话导出：RAG / snippet / 闭包 / 召回（transcript L3370+）"
    else:
        title = f"对话导出（{scope}）"

    lines: list[str] = [
        f"# {title}",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        f"| conversation_id | `{meta['conversation_id']}` |",
        f"| scope | **{scope}** |",
        f"| transcript 起始行 | **{meta['thread_start_line']}** |",
        f"| 导出时间 | {meta['exported_at']} |",
        f"| 轮次数 | {qa_pairs} |",
        f"| 源 JSON | `{src_json}` |",
        "",
        f"> 本文档由 `{src_json.name}` 的 `messages_chronological` 整理而成，保留 assistant 完整 Markdown 正文。",
        "> 原始 transcript 中 tool 中间步骤含 `[REDACTED]` 脱敏，已省略。",
        "",
        "---",
        "",
    ]

    current_turn: int | None = None
    for m in msgs:
        turn = m["turn"]
        role = m["role"]
        content = m["content"].strip()
        if turn != current_turn:
            if current_turn is not None:
                lines.extend(["", "---", ""])
            current_turn = turn
            src = m.get("source_line")
            hdr = f"## 第 {turn} 轮"
            if src:
                hdr += f"（transcript L{src}）"
            lines.extend([hdr, ""])
        if role == "user":
            lines.extend(["### 用户", "", content, ""])
        else:
            lines.extend(["### 助手", ""])
            if content:
                lines.extend([content, ""])
            else:
                lines.extend(["*（该轮 assistant 正文为空或未写入 transcript）*", ""])

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    return out_md


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=("complete", "thread"),
        default=None,
        help="complete=全会话; thread=L3370+ 子线程",
    )
    parser.add_argument(
        "--to-md",
        metavar="JSON",
        type=Path,
        help="将已有 export JSON 转为可读 Markdown（不重新导出 JSON）",
    )
    parser.add_argument(
        "--md-out",
        metavar="MD",
        type=Path,
        default=None,
        help="--to-md 输出路径（默认由 JSON 文件名推断）",
    )
    parser.add_argument(
        "--with-md",
        action="store_true",
        help="导出 JSON 后同时生成 Markdown",
    )
    args = parser.parse_args()

    if args.to_md:
        out_md = json_to_dialogue_md(args.to_md, args.md_out)
        print(f"MD:    {out_md} ({out_md.stat().st_size / 1024:.0f} KB, {sum(1 for _ in out_md.open())} lines)")
        return

    if args.scope is None:
        args.scope = "complete"

    out_json, out_jsonl = export(args.scope)
    data = json.loads(out_json.read_text("utf-8"))
    stats = data["meta"]["statistics"]
    print(f"JSON:  {out_json} ({out_json.stat().st_size / 1024:.0f} KB)")
    print(f"JSONL: {out_jsonl} ({out_jsonl.stat().st_size / 1024:.0f} KB)")
    print(f"scope={data['meta']['scope']} start_line={data['meta']['thread_start_line']}")
    print(f"events={stats['exported_events']} qa_pairs={stats['qa_pairs']} messages={stats['messages_chronological']}")
    for p in data["qa_pairs"][:3]:
        print(f"  T{p['turn']} L{p['user_source_line']} | {p['user'][:50]}…")
    if len(data["qa_pairs"]) > 3:
        print("  …")
        for p in data["qa_pairs"][-2:]:
            print(f"  T{p['turn']} L{p['user_source_line']} | {p['user'][:50]}…")

    if args.with_md:
        out_md = json_to_dialogue_md(out_json, args.md_out)
        print(f"MD:    {out_md} ({out_md.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
