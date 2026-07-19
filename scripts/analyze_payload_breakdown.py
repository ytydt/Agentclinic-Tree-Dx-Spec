#!/usr/bin/env python3
"""Decompose the LLM USER payload of each module call in a per-case log.

Reports, per module call: system-prompt tokens, user-payload tokens, and a
per-top-level-key token breakdown of the user JSON (so we can see which parts
are bloated / low information density).
"""
import json
import re
import sys
from pathlib import Path

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    def ntok(s: str) -> int:
        return len(_ENC.encode(s))
except Exception:
    def ntok(s: str) -> int:
        return max(1, len(s) // 4)


def parse_blocks(text: str):
    """Yield (module, system, user, response) tuples."""
    # Each block starts with ">>> Module: NAME"
    parts = re.split(r"^\[.*?\] >>> Module: (.+)$", text, flags=re.M)
    # parts[0] is preamble; then alternating name, body
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1]
        sys_m = re.search(r"SYSTEM PROMPT:\n(.*?)(?:\nUSER MESSAGE:|\nRAW LLM RESPONSE:|\Z)", body, re.S)
        usr_m = re.search(r"USER MESSAGE:\n(.*?)(?:\nRAW LLM RESPONSE:|\Z)", body, re.S)
        rsp_m = re.search(r"RAW LLM RESPONSE:\n(.*?)\Z", body, re.S)
        yield (
            name,
            (sys_m.group(1) if sys_m else ""),
            (usr_m.group(1) if usr_m else ""),
            (rsp_m.group(1) if rsp_m else ""),
        )


def _extract_payload_json(user_text: str):
    """User msg looks like '... Payload: {json...}'. Return the parsed dict."""
    idx = user_text.find("Payload:")
    blob = user_text[idx + len("Payload:"):] if idx >= 0 else user_text
    blob = blob.strip()
    # Find first '{' and try to json-decode the maximal prefix.
    start = blob.find("{")
    if start < 0:
        return None
    blob = blob[start:]
    dec = json.JSONDecoder()
    try:
        obj, _end = dec.raw_decode(blob)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _flatten_state(obj: dict):
    """If payload has a nested 'state' dict, merge its keys (prefixed) so we see
    the real heavy sub-fields like branches / static_evidence_items."""
    out = {}
    for k, v in obj.items():
        if k == "state" and isinstance(v, dict):
            for sk, sv in v.items():
                out[f"state.{sk}"] = sv
        else:
            out[k] = v
    return out


def key_breakdown(user_text: str):
    obj = _extract_payload_json(user_text)
    if obj is None:
        return None
    obj = _flatten_state(obj)
    out = {}
    for k, v in obj.items():
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        out[k] = ntok(s)
    return out


def main():
    path = Path(sys.argv[1])
    text = path.read_text(errors="replace")
    blocks = list(parse_blocks(text))
    # Find the largest user payload per module name
    biggest = {}
    for name, sysm, usr, rsp in blocks:
        ut = ntok(usr)
        if name not in biggest or ut > biggest[name][0]:
            biggest[name] = (ut, ntok(sysm), usr)

    print(f"FILE: {path.name}  (blocks={len(blocks)})\n")
    print(f"{'MODULE':28s} {'sys_tok':>8s} {'user_tok':>9s} {'total':>8s}")
    print("-" * 60)
    for name, (ut, st, _usr) in sorted(biggest.items(), key=lambda x: -x[1][0]):
        print(f"{name:28s} {st:8d} {ut:9d} {st+ut:8d}")

    # Detailed breakdown for the top-2 heaviest modules
    print("\n=== Per-key breakdown of heaviest USER payloads ===")
    for name, (ut, st, usr) in sorted(biggest.items(), key=lambda x: -x[1][0])[:4]:
        bd = key_breakdown(usr)
        print(f"\n--- {name}  (user_tok={ut}, sys_tok={st}) ---")
        if bd is None:
            print("  (user payload not pure JSON; head 200 chars)")
            print("  " + usr.strip()[:200].replace("\n", " "))
            continue
        for k, t in sorted(bd.items(), key=lambda x: -x[1]):
            pct = 100.0 * t / max(1, ut)
            print(f"  {k:34s} {t:7d} tok  {pct:5.1f}%")


if __name__ == "__main__":
    main()
