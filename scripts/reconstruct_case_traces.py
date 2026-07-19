"""Reconstruct per-case module-call traces from the (concurrent, interleaved)
LLM call log by matching a unique vignette phrase in each call's USER MESSAGE.

Output: logs/anatomy/case_<idx>.json  — ordered list of module calls with the
key parsed fields needed for root-cause anatomy (root label, branch labels +
roles, evidence/LR annotations, answer-option mapping + chosen answer).
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "logs/medbullets_conc_20260604_171145.log")
OUT = Path("logs/anatomy"); OUT.mkdir(parents=True, exist_ok=True)

# unique phrase per case index
PHRASE = {
    9:  "sodium docusate",
    13: "papules and plaques",
    17: "20/100 in both eyes",
    18: "fitness show",
    22: "trouble focusing",
    23: "returned from a cruise",
    1:  "dropped his cup of tea",
    14: "tricuspid stenosis",
    24: "previously diagnosed acute sinusitis",
}

text = LOG.read_text(encoding="utf-8", errors="replace")
# split into entries on the module header, keep header
parts = re.split(r"(?=\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] >>> Module: )", text)

SEC = "-" * 70
def section(block: str, name: str) -> str:
    # returns text between "name:\n" and next SEC line
    m = re.search(re.escape(name) + r":\n(.*?)\n" + re.escape(SEC), block, re.S)
    return m.group(1) if m else ""

records = []
for blk in parts:
    mh = re.match(r"\[([\d :-]+)\] >>> Module: (\w+)", blk)
    if not mh:
        continue
    ts, module = mh.group(1), mh.group(2)
    user = section(blk, "USER MESSAGE")
    parsed_raw = ""
    mp = re.search(r"PARSED RESULT:\n(.*?)\n={80}", blk, re.S)
    if mp:
        parsed_raw = mp.group(1)
    try:
        parsed = json.loads(parsed_raw)
    except Exception:
        parsed = parsed_raw[:400]
    records.append(dict(ts=ts, module=module, user=user, parsed=parsed))

print(f"parsed {len(records)} log entries")

def slim(module, parsed):
    """Keep only fields useful for anatomy per module."""
    if not isinstance(parsed, dict):
        return parsed
    keep = {
        "RootSelector": ["root_label", "label", "time_course", "severity",
                          "excluded_candidates", "confidence", "supporting_facts"],
        "BranchCreator": ["branches", "raw_branches"],
        "SubBranchCreator": ["sub_branches"],
        "EvidenceAnnotator": ["evidence_items", "annotations", "likelihood_ratios",
                              "branch_links", "items"],
        "TemporaryAnalyticLeafPlanner": ["candidate_leaves_ranked", "selected"],
        "PostUpdateStateReviser": ["branch_decisions"],
        "AnswerMapper": None,  # keep all
        "TerminationJudge": ["ready_to_stop", "reason"],
    }
    if module not in keep or keep[module] is None:
        return parsed
    return {k: parsed[k] for k in keep[module] if k in parsed}

for idx, phrase in PHRASE.items():
    hits = [r for r in records if phrase in r["user"]]
    trace = [dict(ts=r["ts"], module=r["module"], parsed=slim(r["module"], r["parsed"]))
             for r in hits]
    (OUT / f"case_{idx}.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    mods = [r["module"] for r in hits]
    from collections import Counter
    print(f"case {idx:<3} phrase={phrase!r:35} entries={len(hits):<3} {dict(Counter(mods))}")
