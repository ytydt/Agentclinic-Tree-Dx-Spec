#!/usr/bin/env python3
"""Score the 2x2 of {one-sentence prompt, passage-scoped prompt} x {old, v2 index}.

Reports per arm the three quantities the 2x2 was run to separate:

  * how often a criterion group forms at all,
  * how far each group reaches -- one sentence, several sentences, several
    lines -- which is what the prompt change was supposed to move,
  * the logic mix, which is what the corpus repair was supposed to move.

The span classifier is the one from audit_group_span.py, kept here so a single
command prints all four arms side by side.

    python measure_2x2_groups.py
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

ARMS = [
    ("old prompt / old index", "trial_extraction_x2_oldidxclean_groups.json",
     "trial_retrieval_x2_oldidx.json"),
    ("new prompt / old index", "trial_extraction_x2_oldidxclean_groups_free.json",
     "trial_retrieval_x2_oldidx.json"),
    ("old prompt / v2 index", "trial_extraction_x2_v2idxclean_groups.json",
     "trial_retrieval_x2_v2idx.json"),
    ("new prompt / v2 index", "trial_extraction_x2_v2idxclean_groups_free.json",
     "trial_retrieval_x2_v2idx.json"),
]

SENT_END = re.compile(r"[.!?]['\")\]]?\s")
WS = re.compile(r"\s+")


def real(v) -> bool:
    return isinstance(v, str) and v.strip().lower() not in {"", "null", "none"}


def prepare(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapse a passage, keeping where each source line landed.

    The model normalises whitespace when it quotes, so a quote never contains a
    newline (11 of 34,332 in the old-prompt arm).  Asking whether the quote has
    a newline therefore always answers no, whatever the prompt says.  Locating
    the quote back in the passage and asking which source line it fell on is
    the instrument that can actually move.
    """
    parts, norm, starts = text.split("\n"), [], []
    pos = 0
    for ln in parts:
        starts.append(pos)
        c = WS.sub(" ", ln).strip()
        norm.append(c)
        pos += len(c) + 1
    return " ".join(norm), starts


def line_of(starts: list[int], p: int) -> int:
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= p:
            lo = mid
        else:
            hi = mid - 1
    return lo


def span_of(quotes: list[str], norm: str, starts: list[int]) -> str:
    """How far the members of one group reach in the passage they came from."""
    uniq = [q for q in dict.fromkeys(WS.sub(" ", q).strip() for q in quotes if q.strip())]
    if not uniq:
        return "no_quote"
    hits = [(norm.index(q), norm.index(q) + len(q)) for q in uniq if q in norm]
    if not hits:
        return "unlocatable"
    if len(uniq) == 1:
        return "one_quote"
    lines = {line_of(starts, s) for s, _ in hits} | {line_of(starts, e - 1) for _, e in hits}
    if len(lines) > 1:
        return "cross_line"
    lo, hi = min(s for s, _ in hits), max(e for _, e in hits)
    return "cross_sentence" if SENT_END.search(norm[lo:hi]) else "same_sentence"


def load_passages(retrieval: str) -> dict[str, list[tuple[str, list[int]]]]:
    """case_key -> the prepared passages that were fed to the extractor."""
    data = json.loads((LEDGER / retrieval).read_text(encoding="utf-8"))
    out: dict[str, list] = {}
    for entry in data:
        seen, rows = set(), []
        for bundle in entry["retrieved"].values():
            for p in bundle["passages"]:
                if p["gid"] in seen:
                    continue
                seen.add(p["gid"])
                rows.append(prepare(p["text"]))
        out[entry["case_key"]] = rows
    return out


def locate(quotes: list[str], rows: list[tuple[str, list[int]]]):
    """The passage that contains the most of this group's quotes."""
    uniq = [q for q in dict.fromkeys(WS.sub(" ", q).strip() for q in quotes if q.strip())]
    if not uniq:
        return None
    best, best_n = None, 0
    for norm, starts in rows:
        n = sum(1 for q in uniq if q in norm)
        if n > best_n:
            best, best_n = (norm, starts), n
            if n == len(uniq):
                break
    return best


def score(path: Path, retrieval: str) -> dict | None:
    if not path.exists():
        return None
    pas = load_passages(retrieval)
    data = json.loads(path.read_text(encoding="utf-8"))
    groups: dict[tuple, list] = {}
    n_assert = 0
    for entry in data:
        for a in entry.get("assertions") or []:
            if not isinstance(a, dict):
                continue
            n_assert += 1
            cg = a.get("criterion_group") or {}
            gid = cg.get("group_id")
            if not real(gid) and not isinstance(gid, (int, float)):
                continue
            key = (entry["case_key"], a.get("_source"), a.get("_title"),
                   a.get("_section"), a.get("_focus"), str(gid))
            groups.setdefault(key, []).append(a)

    multi = {k: v for k, v in groups.items() if len(v) >= 2}
    spans: Counter = Counter()
    for k, v in multi.items():
        quotes = [str(m.get("quote") or "") for m in v]
        hit = locate(quotes, pas.get(k[0], []))
        spans[span_of(quotes, *hit) if hit else "unlocatable"] += 1
    logic = Counter()
    for v in multi.values():
        lg = (v[0].get("criterion_group") or {}).get("logic")
        logic[lg if real(lg) else "none"] += 1
    return {
        "assertions": n_assert,
        "groups_any": len(groups),
        "groups_multi": len(multi),
        "members": sum(len(v) for v in multi.values()),
        "spans": spans,
        "logic": logic,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    args = ap.parse_args()

    rows = []
    for name, fn, retr in ARMS:
        s = score(LEDGER / fn, retr)
        if s is None:
            print(f"[missing] {name}  ({fn})")
            continue
        rows.append((name, s))

    if not rows:
        return 1

    print(f"{'arm':<24}{'assertions':>11}{'groups>=2':>11}{'members':>9}"
          f"{'members/assert':>16}")
    for name, s in rows:
        print(f"{name:<24}{s['assertions']:>11}{s['groups_multi']:>11}"
              f"{s['members']:>9}{s['members'] / max(s['assertions'], 1):>15.2%}")

    keys = ("one_quote", "same_sentence", "cross_sentence", "cross_line",
            "unlocatable")
    print(f"\n{'arm':<24}" + "".join(f"{k:>16}" for k in keys))
    for name, s in rows:
        tot = max(s["groups_multi"], 1)
        cells = "".join(f"{s['spans'].get(k, 0):>8}{s['spans'].get(k, 0) / tot:>8.1%}"
                        for k in keys)
        print(f"{name:<24}{cells}")

    print(f"\n{'arm':<24}" + "".join(f"{k:>14}" for k in
                                     ("all", "any", "at_least_n", "none")))
    for name, s in rows:
        tot = max(s["groups_multi"], 1)
        cells = "".join(f"{s['logic'].get(k, 0):>6} {s['logic'].get(k, 0) / tot:>6.1%}"
                        for k in ("all", "any", "at_least_n", "none"))
        print(f"{name:<24}{cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
