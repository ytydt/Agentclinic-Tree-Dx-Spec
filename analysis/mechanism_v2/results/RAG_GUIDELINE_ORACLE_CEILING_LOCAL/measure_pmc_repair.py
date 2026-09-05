#!/usr/bin/env python3
"""Size the three offline pmc_oa repairs before implementing them.

(1) min_len floor      -- passages should_keep_chunk drops purely on length
(2) list adjacency     -- short passages that follow an enumeration announcement
(3) table flattening   -- table chunks whose rows were joined into a single line

Run from the repo root; reads only data/cpg/raw/pmc_oa/*.json.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from pmc_oa_ddx_common import should_keep_chunk  # noqa: E402

ANNOUNCE = re.compile(
    r"(following|criteri\w*|abnormalit\w*|features?|findings?|manifestations?|"
    r"signs?|symptoms?|elements?|components?|includ\w*|compris\w*|consists?)"
    r"[^.]{0,25}:\s*$", re.I)
QUOTE = re.compile(r"^[\u201c\u0022\u2018]")


def main() -> int:
    files = sorted(glob.glob("data/cpg/raw/pmc_oa/*.json"))
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if limit:
        files = files[:limit]
    c = Counter()

    for f in files:
        try:
            payload = json.load(open(f, encoding="utf-8"))
        except Exception:
            c["unparsable"] += 1
            continue
        coll = payload[0] if isinstance(payload, list) else payload
        for doc in coll.get("documents") or []:
            title = ""
            stack: list[str] = []
            seq = []  # (ptype, text, stack snapshot)
            for ps in doc.get("passages") or []:
                inf = ps.get("infons") or {}
                pt = str(inf.get("type") or "")
                txt = (ps.get("text") or "").strip()
                if not txt:
                    continue
                if pt.startswith("title"):
                    lvl = int(re.sub(r"\D", "", pt) or "1")
                    while len(stack) >= lvl:
                        stack.pop()
                    stack.append(txt)
                    continue
                if pt in {"front", "abstract"}:
                    if pt == "front" and not title:
                        title = txt
                    continue
                seq.append((pt, txt, list(stack), inf))

            for i, (pt, txt, stack, inf) in enumerate(seq):
                last = stack[-1] if stack else ""
                kept = should_keep_chunk(last, txt, pt, section_stack=stack,
                                         article_title=title)
                c["passages"] += 1
                if kept:
                    c["kept"] += 1
                else:
                    # would it have been kept if length were not the blocker?
                    padded = txt + " x" * 60
                    if should_keep_chunk(last, padded, pt, section_stack=stack,
                                         article_title=title):
                        c["dropped_on_length_only"] += 1
                        # is it a plausible list item under an announcement?
                        for j in range(i - 1, max(i - 12, -1), -1):
                            prev = seq[j][1]
                            if ANNOUNCE.search(prev):
                                c["dropped_length_under_announce"] += 1
                                break
                            if len(prev) > 400:
                                break

                if pt == "table":
                    c["table_passages"] += 1
                    if "\n" not in txt:
                        c["table_single_line"] += 1
                    if (inf.get("xml") or "").strip():
                        c["table_has_xml"] += 1

                if ANNOUNCE.search(txt):
                    c["announce_leadin"] += 1
                    run = 0
                    for j in range(i + 1, min(i + 15, len(seq))):
                        s = seq[j][1]
                        if len(s) > 400 or QUOTE.match(s):
                            break
                        run += 1
                    if run >= 2:
                        c["announce_with_run"] += 1
                        c["announce_run_items"] += run

    print(f"files scanned: {len(files)}")
    for k, v in c.most_common():
        print(f"  {k:<32}{v:>9}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
