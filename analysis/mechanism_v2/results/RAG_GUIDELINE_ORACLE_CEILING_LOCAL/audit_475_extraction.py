#!/usr/bin/env python3
"""Classify logical defects in LLM-extracted assertions for case 475.

This is an extraction-time audit: a seven-tuple is tagged as defective when it
already misrepresents its own quote, before the engine joins or scores it.
Join/application errors are counted separately and are not the object here.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402

KEY = "MCR_seq200b/475"

HEDGE = re.compile(
    r"\b(may|might|can|could|often|usually|typically|sometimes|some patients|"
    r"in some|relies on|support the use|generally|possible|suggests?)\b",
    re.I,
)
BOILER = re.compile(
    r"index of suspicion|clinical (assessment|judgment|diagnosis)|"
    r"^(imaging|laboratory|diagnosis|evaluation|examination)$|"
    r"high index|careful history",
    re.I,
)
ABILITY = re.compile(r"\b(ability|able to|can still|still be able)\b", re.I)
INABILITY_Q = re.compile(r"\b(unable|inability|cannot|can not|not be able)\b", re.I)
VARIANT = re.compile(r"\b(this variant|this form|this subtype|this type)\b", re.I)
COMPARE = re.compile(r"\bmore (sensitive|specific) than\b", re.I)
DIFF_CUE = re.compile(
    r"\b(differential|mimic|distinguish|rather than|as opposed to|"
    r"should be differentiated|includes flexor tendon)\b",
    re.I,
)
SPARED = re.compile(
    r"no deficit should be expected|still be able|may still be able|"
    r"ain (is )?spared|not expected in the ain",
    re.I,
)


def uniq_key(a: dict) -> tuple:
    return (
        eng.norm(a.get("subject")),
        (a.get("relation") or "").lower(),
        (a.get("polarity") or "asserted").lower(),
        (a.get("modality") or "").lower(),
        eng.norm(a.get("predicate")),
        (a.get("quote") or "")[:80],
    )


def tags(a: dict) -> list[str]:
    """Return extraction-time defect tags. Empty = no heuristic fire."""
    pred = str(a.get("predicate") or "")
    quote = str(a.get("quote") or "")
    rel = (a.get("relation") or "").lower()
    mod = (a.get("modality") or "").lower()
    pol = (a.get("polarity") or "asserted").lower()
    ctx = (a.get("context_type") or "").lower()
    subj = str(a.get("subject") or "")
    out = []

    if rel in eng.RELATION_IS_CONTEXT:
        out.append("E4_relation_slot")

    if rel == "required_for" and BOILER.search(pred):
        out.append("E7_boilerplate")
        out.append("E4_relation_slot")
    if BOILER.search(pred) and rel in {"feature_of", "required_for", "sufficient_for"}:
        if "E7_boilerplate" not in out:
            out.append("E7_boilerplate")

    if mod == "obligatory" and HEDGE.search(quote):
        out.append("E3_modality_inflation")

    if VARIANT.search(quote) and rel == "required_for":
        out.append("E5_scope_collapse")

    if COMPARE.search(quote) and rel in {"sufficient_for", "required_for", "feature_of"}:
        out.append("E4_relation_slot")
        out.append("E6_context_strip")

    if ABILITY.search(pred) and not INABILITY_Q.search(pred):
        if INABILITY_Q.search(quote) or re.search(r"still be able|may still", quote, re.I):
            out.append("E2_polarity_invert")
        if SPARED.search(quote):
            out.append("E6_context_strip")

    if SPARED.search(quote) and rel in {"excludes", "feature_of"}:
        out.append("E6_context_strip")
        if "E2_polarity_invert" not in out and rel == "excludes":
            out.append("E2_polarity_invert")

    if rel == "feature_of" and DIFF_CUE.search(quote) and ctx in {"differential", "definition", ""}:
        # a contrast sentence emitted as a positive feature of the subject
        if "mimic" in quote.lower() or "differential" in quote.lower():
            out.append("E8_diff_as_feature")

    if rel == "distinguishes_from" and re.search(r"\btendon\b", pred, re.I) and not a.get("comparator"):
        out.append("E4_relation_slot")

    # hypernym subject: "Neuropathy" / "Mononeuropathy" for a named syndrome in the quote
    if re.search(r"^(neuropathy|mononeuropathy|nerve damage)$", eng.norm(subj)):
        if re.search(
            r"brachial neuritis|parsonage|amyotroph|radial|ulnar|median|ain|"
            r"interosseous|plexitis",
            quote,
            re.I,
        ) and not re.search(r"brachial neuritis|parsonage|amyotroph", subj, re.I):
            out.append("E1_subject_misattr")

    # CTS/APB/thenar attributed to AIN
    if re.search(r"anterior interosseous", subj, re.I):
        if re.search(r"\b(CTS|carpal tunnel|APB|thenar)\b", quote, re.I) and re.search(
            r"thenar|APB|opposition", pred, re.I
        ):
            out.append("E1_subject_misattr")
            out.append("E6_context_strip")

    cg = a.get("criterion_group") or {}
    if cg.get("group_id") and cg.get("logic") == "any":
        if re.search(r"\b(foot|dorsum|patellar|stapedial|auditory)\b", pred, re.I):
            out.append("E9_spurious_group")

    # generic predicate that cannot be a diagnostic rule
    if eng.norm(pred) in {
        "imaging", "laboratory", "diagnosis", "evaluation", "weakness",
        "pain", "sensory symptoms", "motor deficits", "sensory deficits",
        "laboratory tests", "nerve conduction",
    } and rel in {"feature_of", "required_for", "sufficient_for"}:
        out.append("E7_vacuous_predicate")

    return sorted(set(out))


def main() -> int:
    rec = next(
        r for r in json.loads((LEDGER / "trial_extraction_k30all4clean_groups.json").read_text())
        if r["case_key"] == KEY
    )
    assertions = [a for a in rec["assertions"] if isinstance(a, dict)]
    print(f"raw assertions: {len(assertions)}")

    seen = {}
    for a in assertions:
        seen.setdefault(uniq_key(a), a)
    uniq = list(seen.values())
    print(f"unique (subj,rel,pol,mod,pred,quote80): {len(uniq)}")

    by_tag = Counter()
    n_any = 0
    examples = defaultdict(list)
    for a in uniq:
        t = tags(a)
        if t:
            n_any += 1
            for x in t:
                by_tag[x] += 1
                if len(examples[x]) < 4:
                    examples[x].append(a)

    print(f"unique with ≥1 heuristic defect: {n_any}/{len(uniq)} "
          f"= {n_any/len(uniq):.1%}")
    print("\nby tag (unique assertions, overlapping):")
    for k, v in by_tag.most_common():
        print(f"  {v:5d}  {k}")

    # focus-conditioned vs other-disease
    from collections import Counter as C
    print("\n_focus histogram (raw):")
    for k, v in C(str(a.get("_focus")) for a in assertions).most_common():
        print(f"  {v:5d}  {k}")

    print("\nrelation histogram (unique):")
    for k, v in C((a.get("relation") or "").lower() for a in uniq).most_common(15):
        print(f"  {v:5d}  {k}")

    print("\nmodality × obligatory among required_for (unique):")
    req = [a for a in uniq if (a.get("relation") or "").lower() == "required_for"]
    print(f"  required_for n={len(req)}")
    for k, v in C((a.get("modality") or "") for a in req).most_common():
        print(f"    {v:4d}  {k}")
    hedge_obl = sum(1 for a in req if (a.get("modality") or "").lower() == "obligatory" and HEDGE.search(str(a.get("quote") or "")))
    print(f"  obligatory required_for whose quote is hedged: {hedge_obl}/{sum(1 for a in req if (a.get('modality') or '').lower()=='obligatory')}")

    print("\n=== examples per tag ===")
    for tag, xs in examples.items():
        print(f"\n## {tag}")
        for a in xs:
            print(f"  {a.get('subject')!s:42s} -[{a.get('relation')}/{a.get('polarity')}/{a.get('modality')}]→ {str(a.get('predicate'))[:60]}")
            print(f"    quote: {str(a.get('quote') or '')[:180]}")
            print(f"    title: {str(a.get('_title'))[:70]}  focus={a.get('_focus')}")

    # How many unique assertions are 'clean' by heuristic, with a real clinical predicate
    clean = [a for a in uniq if not tags(a)]
    print(f"\nclean unique (no heuristic): {len(clean)}")
    # sample clean AIN / NA
    for label in ("interosseous", "amyotroph", "parsonage"):
        hit = [a for a in clean if re.search(label, str(a.get("subject")), re.I)]
        print(f"  clean subject~{label}: {len(hit)}")

    out = {
        "n_raw": len(assertions),
        "n_unique": len(uniq),
        "n_unique_defective_heuristic": n_any,
        "by_tag": dict(by_tag),
        "n_required_for": len(req),
        "n_required_obligatory_hedged": hedge_obl,
    }
    (LEDGER / "case475_extraction_defect_heuristic.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )
    print("wrote", LEDGER / "case475_extraction_defect_heuristic.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
