#!/usr/bin/env python3
"""Is the pmc_oa criteria loss a true loss, or flattened structure?

The distinction decides who fixes it.  If the members are gone from the BioC,
only a JATS re-fetch can bring them back and that needs the network.  If the
members are present but the list structure was flattened, the input side is
already at its ceiling and the remedy belongs to the extractor -- the same
conclusion S28 reached for textbooks.

BioC passage offsets settle it locally.  Passages tile the source document
contiguously, normally +1 apart, with small gaps where inline citation markers
were stripped.  A large gap immediately after an enumeration announcement means
BioC emitted nothing for text that existed in the source: a true loss.  A
contiguous offset means the following passages are the members, and failing to
bind them is a structural problem, not a missing one.

Every announcement is classified into exactly one outcome.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
sys.path.insert(0, str(ROOT / "scripts"))
from pmc_oa_ddx_common import (  # noqa: E402
    LIST_MARKER_RE, MAX_ITEM_CHARS, MAX_RUN, MIN_RUN,
    QUOTE_OPEN_RE, find_criteria_runs,
)

OUT = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/pmc_loss_kind_audit.json"
DUMP = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/pmc_loss_kind_sample.md"

NOUNS = (r"following|criteri\w*|abnormalit\w*|features?|findings?|"
         r"manifestations?|signs?|symptoms?|elements?|components?|"
         r"includ\w*|compris\w*|consists?")
# the announcement, wherever it sits in the passage
ANNOUNCE_ANY = re.compile(rf"(?:{NOUNS})[^.]{{0,25}}:", re.I)
ANNOUNCE_END = re.compile(rf"(?:{NOUNS})[^.]{{0,25}}:\s*$", re.I)
# members written as prose after the colon
SERIES = re.compile(r";|,\s+(?:and|or)\s+|\u2022|\n")
STUDY_CRITERIA = re.compile(
    r"\b(?:stud(?:y|ies)|article|paper|manuscript|publication|record|report|"
    r"abstract|literature|review|trial|citation)s?\b[^.]{0,60}\b"
    r"(?:includ|exclud|select|eligib|screen|retriev|search)|"
    r"\b(?:inclusion|exclusion|eligibility)\s+criteri|"
    r"\b(?:peer.?reviewed|full.?text|english.language|grey literature|"
    r"conference abstract|case report)s?\b", re.I)

# gaps below this are citation-marker removal, not dropped content
GAP_OK = 40


def why_rejected(texts: list[str], i: int) -> str:
    """Reproduce find_criteria_runs' decision and name the blocking condition."""
    marked = None
    members = 0
    budget = 0
    for j in range(i + 1, min(i + 1 + MAX_RUN, len(texts))):
        s = texts[j]
        if not s:  # a section heading, masked out by the caller
            return "heading_after_one_member" if members else "heading_immediately"
        if len(s) > MAX_ITEM_CHARS:
            return "next_too_long" if members == 0 else "run_ended_long"
        if QUOTE_OPEN_RE.match(s):
            return "next_is_quote" if members == 0 else "run_ended_quote"
        has_marker = bool(LIST_MARKER_RE.match(s))
        if marked is None:
            marked = has_marker
        elif marked and not has_marker:
            return "marker_break"
        if members and len(s) > max(180, int(2.0 * budget / members)):
            return "size_break"
        members += 1
        budget += len(s)
    return "hit_max_run"


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    files = sorted(glob.glob(str(ROOT / "data/cpg/raw/pmc_oa/*.json")))
    if limit:
        files = files[:limit]

    out = Counter()
    reasons = Counter()
    gaps: list[int] = []
    all_gaps: list[int] = []
    samples: dict[str, list[str]] = defaultdict(list)

    for fi, f in enumerate(files):
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        coll = payload[0] if isinstance(payload, list) else payload
        for doc in coll.get("documents") or []:
            seq = []  # (type, text, offset)
            for ps in doc.get("passages") or []:
                inf = ps.get("infons") or {}
                pt = str(inf.get("type") or "")
                txt = (ps.get("text") or "").strip()
                if not txt or pt.startswith("ref"):
                    continue
                seq.append((pt, txt, int(ps.get("offset") or 0)))
            if not seq:
                continue

            # a section title terminates any enumeration: the members cannot be
            # on the far side of a heading.  Keeping titles in the sequence but
            # marking them keeps the offsets honest while letting the run logic
            # stop at the boundary.
            is_title = [pt.startswith("title") for pt, _, _ in seq]
            texts = ["" if h else t for h, (_, t, _) in zip(is_title, seq)]
            runs = find_criteria_runs(texts)

            for i, (pt, txt, off) in enumerate(seq):
                if is_title[i] or not ANNOUNCE_ANY.search(txt):
                    continue
                out["announcements"] += 1
                if STUDY_CRITERIA.search(txt):
                    out["_study_criteria"] += 1

                # (1) the announcement is mid-passage: the members are already
                # in this passage, rendered as prose
                if not ANNOUNCE_END.search(txt):
                    tail = txt[ANNOUNCE_ANY.search(txt).end():]
                    if len(tail) > 30 and SERIES.search(tail):
                        out["inline_prose"] += 1
                        if len(samples["inline_prose"]) < 8:
                            samples["inline_prose"].append(txt[:240])
                        continue
                    out["inline_short_tail"] += 1
                    continue

                # (2) colon-terminated: where did the members go?
                if i + 1 >= len(seq):
                    out["end_of_document"] += 1
                    continue
                gap = seq[i + 1][2] - (off + len(txt))
                all_gaps.append(gap)

                if gap > GAP_OK:
                    out["true_loss_offset_gap"] += 1
                    gaps.append(gap)
                    if len(samples["true_loss_offset_gap"]) < 8:
                        samples["true_loss_offset_gap"].append(
                            f"gap={gap} | {txt[-160:]} || next: {seq[i+1][1][:110]}")
                    continue

                if i in runs:
                    out["recovered_by_adjacency"] += 1
                    continue

                if is_title[i + 1]:
                    out["ends_at_section_boundary"] += 1
                    if len(samples["ends_at_section_boundary"]) < 8:
                        samples["ends_at_section_boundary"].append(
                            f"{txt[-140:]} || next heading: {seq[i+1][1][:80]}")
                    continue

                nxt_type = seq[i + 1][0]
                if nxt_type in {"table", "table_caption", "fig_caption",
                                "table_title_caption", "fig_title_caption"}:
                    out["members_in_table_or_fig"] += 1
                    continue

                r = why_rejected(texts, i)
                out["present_but_unbound"] += 1
                reasons[r] += 1
                # how long would the members have to be allowed to be?
                nxt = seq[i + 1][1]
                for cap in (400, 600, 900, 1400, 2500):
                    if len(nxt) <= cap:
                        out[f"_would_fit_{cap}"] += 1
                if len(samples[f"unbound_{r}"]) < 5:
                    samples[f"unbound_{r}"].append(
                        f"{txt[-140:]} || next: {seq[i+1][1][:130]}")

        if fi % 1500 == 0 and fi:
            print(f"  {fi}/{len(files)}", flush=True)

    n = out["announcements"]
    dangling = (out["true_loss_offset_gap"] + out["recovered_by_adjacency"]
                + out["members_in_table_or_fig"] + out["present_but_unbound"]
                + out["end_of_document"] + out["ends_at_section_boundary"])

    def row(k, v, base):
        print(f"  {k:<32}{v:>7}  {v/base:6.1%}")

    print(f"\nannouncements found: {n}")
    print(f"  of which the review's own study criteria: "
          f"{out['_study_criteria']} ({out['_study_criteria']/n:.1%})")

    print("\nwhere the members are (all announcements)")
    row("inline prose, same passage", out["inline_prose"], n)
    row("announcement w/ short tail", out["inline_short_tail"], n)
    row("colon-terminated (dangling)", dangling, n)

    print(f"\nthe {dangling} dangling ones, resolved")
    row("recovered by adjacency", out["recovered_by_adjacency"], dangling)
    row("present but unbound", out["present_but_unbound"], dangling)
    row("ends at a section heading", out["ends_at_section_boundary"], dangling)
    row("members in a table/figure", out["members_in_table_or_fig"], dangling)
    row("TRUE LOSS (offset gap)", out["true_loss_offset_gap"], dangling)
    row("end of document", out["end_of_document"], dangling)

    if reasons:
        print("\nwhy the present-but-unbound ones were rejected")
        tot = sum(reasons.values())
        for k, v in reasons.most_common():
            print(f"    {k:<24}{v:>6}  {v/tot:6.1%}")
        print("\n  first member would fit under a longer item cap")
        for cap in (400, 600, 900, 1400, 2500):
            v = out[f"_would_fit_{cap}"]
            print(f"    <= {cap:<6}{v:>6}  {v/tot:6.1%}")

    if all_gaps:
        all_gaps.sort()
        print(f"\noffset gap after a dangling announcement: "
              f"median {all_gaps[len(all_gaps)//2]}, "
              f"p90 {all_gaps[int(len(all_gaps)*0.9)]}, "
              f"max {all_gaps[-1]}")

    OUT.write_text(json.dumps({
        "counts": dict(out), "reject_reasons": dict(reasons),
        "dangling": dangling, "gap_threshold": GAP_OK,
    }, indent=2), encoding="utf-8")
    with DUMP.open("w", encoding="utf-8") as fh:
        fh.write("# pmc_oa 判据成员去向：真缺失 vs 结构损坏\n")
        for k, rows in samples.items():
            fh.write(f"\n## {k}\n\n")
            for r in rows:
                fh.write(f"- {r}\n")
    print(f"\nwrote {OUT.name}, {DUMP.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
