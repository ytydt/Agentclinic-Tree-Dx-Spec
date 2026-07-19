"""Export the JSONL agent transcript into a readable Markdown file.

Usage: python scripts/export_conversation.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TRANSCRIPT = Path(
    "/home/wanghongyi/.cursor/projects/data2-wanghongyi-Agentclinic-Tree-Dx-Spec/"
    "agent-transcripts/f265f231-79f2-4da2-9182-e52dd3f46b53/"
    "f265f231-79f2-4da2-9182-e52dd3f46b53.jsonl"
)
OUT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/CONVERSATION_EXPORT.md")

# System-injected wrappers we want to strip from user messages so the export
# reads as the human's actual words.
_STRIP_BLOCKS = [
    r"<open_and_recently_viewed_files>.*?</open_and_recently_viewed_files>",
    r"<system_reminder>.*?</system_reminder>",
    r"<attached_files>.*?</attached_files>",
    r"<system_notification>.*?</system_notification>",
    r"<timestamp>.*?</timestamp>",
]


def clean_user_text(text: str) -> str:
    for pat in _STRIP_BLOCKS:
        text = re.sub(pat, "", text, flags=re.DOTALL)
    # unwrap <user_query>...</user_query>
    m = re.search(r"<user_query>(.*?)</user_query>", text, flags=re.DOTALL)
    if m:
        text = m.group(1)
    return text.strip()


def tool_summary(block: dict) -> str:
    name = block.get("name", "tool")
    inp = block.get("input", {}) or {}
    # Pick the most informative short field.
    for key in ("description", "explanation", "command", "query", "path",
                "target_notebook", "search_term", "url", "prompt"):
        if key in inp and isinstance(inp[key], str):
            val = inp[key].replace("\n", " ").strip()
            if len(val) > 140:
                val = val[:140] + "…"
            return f"`{name}` — {val}"
    return f"`{name}`"


def main() -> None:
    if not TRANSCRIPT.exists():
        raise SystemExit(f"Transcript not found: {TRANSCRIPT}")

    out: list[str] = []
    out.append("# 对话记录导出 (Conversation Export)\n")
    out.append(f"> 源转录: `{TRANSCRIPT.name}`\n")
    out.append(
        "> 说明: 工具调用以紧凑摘要呈现（系统未保存工具返回结果）；"
        "助手文本含其推理与回复。\n")

    user_turn = 0
    n_assistant_text = 0
    n_tool = 0

    with TRANSCRIPT.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = obj.get("role", "?")
            content = obj.get("message", {}).get("content", [])
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if not isinstance(content, list):
                continue

            if role == "user":
                texts = [
                    clean_user_text(b.get("text", ""))
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                texts = [t for t in texts if t]
                if not texts:
                    continue
                user_turn += 1
                out.append("\n---\n")
                out.append(f"\n## 👤 用户 #{user_turn}\n")
                for t in texts:
                    out.append(t + "\n")

            elif role == "assistant":
                parts: list[str] = []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        t = (b.get("text") or "").strip()
                        if t:
                            n_assistant_text += 1
                            parts.append(t)
                    elif b.get("type") == "tool_use":
                        n_tool += 1
                        parts.append(f"> 🔧 {tool_summary(b)}")
                if parts:
                    out.append("\n### 🤖 助手\n")
                    out.append("\n\n".join(parts) + "\n")

    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"Exported → {OUT}")
    print(f"  user turns: {user_turn}")
    print(f"  assistant text blocks: {n_assistant_text}")
    print(f"  tool calls: {n_tool}")
    print(f"  size: {OUT.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    main()
