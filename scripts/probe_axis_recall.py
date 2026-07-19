"""§23.14 domain-level key-branch recall probe (deterministic, no LLM).

Uses data/knowledge_raw/syndrome_axis_map.json to:
  1. select the L1 classification axis for each case's root syndrome (Step 0),
  2. project the GOLD entity onto the syndrome's MECE single-axis L1 domain
     partition,
  3. report domain-level recall ("gold's L1 domain in the partition") and assert
     each matched syndrome is single-axis.

This encodes the §23.15 manual judgment into a reproducible table + checker so
the axis/level-aware recall claim is testable and the partitions are defined by
the SYNDROME (general clinical framework), not cherry-picked per gold.

Run:  python scripts/probe_axis_recall.py
"""
from __future__ import annotations
import csv, ast, json, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data" / "knowledge_raw"
TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")
DIAGNOSIS_CUES = ("most likely diagnosis", "most likely cause", "most likely underlying",
                  "which of the following is the most likely", "best explains",
                  "most consistent with", "underlying diagnosis", "responsible for",
                  "most likely responsible", "best describes")
IMAGE_CUES = ("figure", "shown in", "image", "photograph", "ecg as seen", "as shown")

# gold answers that are SIGNS/findings rather than disease entities → excluded
# from the KB domain-recall target (§23.14.5 degenerate case).
SIGN_GOLDS = {"diastolic murmur best heard along the right lower sternal border"}


def load_text_cases():
    cases, seen, out = [], set(), []
    with TSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try: opts = ast.literal_eval(row["options"])
            except Exception: opts = {}
            q = row["question"].strip()
            if not opts or not any(c in q.lower() for c in DIAGNOSIS_CUES):
                continue
            key = q[:120]
            if key in seen: continue
            seen.add(key)
            cases.append({"q": q, "ai": row.get("answer_idx", "").strip(),
                          "ans": row.get("answer", "").strip(),
                          "img": any(c in q.lower() for c in IMAGE_CUES)})
    for i, c in enumerate(cases):
        if not c["img"]:
            c["idx"] = i; out.append(c)
    return out


def match_syndrome(vignette: str, table: dict) -> dict:
    """Longest-keyword substring match; fallback = 'undifferentiated'."""
    vl = vignette.lower()
    best, best_len = None, -1
    for entry in table["syndromes"]:
        for kw in entry["syndrome_keywords"]:
            if kw and kw.lower() in vl and len(kw) > best_len:
                best, best_len = entry, len(kw)
    if best is None:
        best = next(e for e in table["syndromes"] if e["id"] == "undifferentiated")
    return best


def classify_into_domain(gold: str, domains: list) -> str | None:
    # Longest-keyword-wins (matches SyndromeAxisMap.project_entity) so generic
    # short keywords never out-grab a specific one in another domain.
    gl = gold.lower()
    best, best_len = None, -1
    for dom in domains:
        for kw in dom["member_keywords"]:
            k = kw.lower()
            if (k in gl or gl in k) and len(k) > best_len:
                best, best_len = dom["name"], len(k)
    return best


def main():
    table = json.loads((DATA / "syndrome_axis_map.json").read_text())
    cases = load_text_cases()

    print("=" * 100)
    print("§23.14 DOMAIN-LEVEL key-branch recall (deterministic, table-driven)")
    print("=" * 100)
    print(f"{'idx':>3} {'gold':>4} {'syndrome':>22} {'axis':>11}  {'recall':>6}  gold→domain")
    print("-" * 100)

    n_inscope = n_hit = 0
    axes_seen = {}
    for c in cases:
        if c["ans"].lower() in SIGN_GOLDS:
            print(f"{c['idx']:>3} {c['ai']:>4} {'(sign gold)':>22} {'—':>11}  {'EXCL':>6}  {c['ans'][:34]}")
            continue
        syn = match_syndrome(c["q"], table)
        axis = syn["axis"]
        dom = classify_into_domain(c["ans"], syn["domains"])
        hit = dom is not None
        n_inscope += 1; n_hit += hit
        axes_seen.setdefault(syn["id"], axis)
        flag = "HIT" if hit else "MISS"
        print(f"{c['idx']:>3} {c['ai']:>4} {syn['id']:>22} {axis:>11}  {flag:>6}  "
              f"{c['ans'][:24]:24} → {dom or '(no domain)'}")

    print("-" * 100)
    print(f"DOMAIN-level recall (in-scope): {n_hit}/{n_inscope} = {n_hit/n_inscope:.0%}")
    # single-axis invariant: each syndrome entry defines exactly ONE axis
    multi = [e["id"] for e in table["syndromes"] if isinstance(e.get("axis"), list)]
    print(f"single-axis invariant: {'OK (every syndrome → exactly one axis)' if not multi else 'VIOLATED: '+str(multi)}")
    print("=" * 100)


if __name__ == "__main__":
    raise SystemExit(main())
