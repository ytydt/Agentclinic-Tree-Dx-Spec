#!/usr/bin/env python3
"""Stage 4: walk each hand-audited assertion through the pipeline and record
the first stage at which it dies.

The 26 assertions are the ones a human used to separate gold from competitors,
so if the mechanical run fails, at least one of them must have been lost.  The
stages are checked in pipeline order, and the first failure is the attributed
cause:

  S0 candidate    no candidate hypothesis denotes the assertion's subject
  S1 retrieval    no retrieved passage carries the assertion
  S2 extraction   passage retrieved but no extracted assertion states it
  S3 relation     stated, but typed with a relation that cannot drive a rule
  S4 subject_bind extracted, but its subject did not bind to a candidate
  S5 finding      the discriminating finding is missing from the case side
  S6 join         both sides exist but the predicate did not join the finding
  S7 engine       everything present; the ranking still put a competitor first
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
from run_mechanical_engine import concept_match, norm  # noqa: E402

INCLUSION_RELATIONS = {"feature_of", "pathognomonic_for", "sufficient_for", "required_for",
                       "variant_of", "synonym_of", "caused_by", "associated_with"}
EXCLUSION_RELATIONS = {"excludes", "argues_against", "distinguishes_from", "required_for",
                       "feature_of"}

# The patient-side counterpart of each assertion.  The corpus-side predicate
# regex cannot be reused here: it is written to find the *rule* ("QTc > 480 ms"),
# whereas the case states the *measurement* ("QTc of 380 ms").  "" marks an
# assertion that is taxonomic and has no patient-side counterpart.
CASE_RE = {
    "522.a": r"intermittent|fluctuat|waxing|wanin",
    "522.b": r"visual\W{0,12}hallucinat|hallucinat\w*,? (and )?(auditory|visual)",
    "522.c": r"echopraxia|echolalia|mutism|negativism|waxy|staring|gaze|posturing",
    "773.a": r"foramen ovale|\bpfo\b|shunt|7\.34",
    "773.b": r"pulmonary artery\w* .{0,30}pressure|\d+/\d+ ?mm ?hg|\d+ ?mm ?hg",
    "773.c": r"patent foramen ovale|\bpfo\b|7\.34",
    "119.a": r"cornoid lamella|parakeratotic column",
    "119.b": r"porokeratos",
    "257.a": r"fusiform|passive extension|flexor sheath|tenderness|swelling",
    "257.b": r"web space|palm",
    "326.a": r"sheep|goat|unpasteuri|raw milk|stomach",
    "326.b": r"epidural|vertebra|spinal|spondyl|T9|T10",
    "326.c": r"gram[- ]negative",
    "475.a": "",
    "475.b": r"biceps|triceps|deltoid|denervation|electromyograph|\bemg\b",
    "49.a": r"appendectom|stump|surgical clip",
    "56.a": r"\bp63\b|\bp40\b",
    "56.b": r"cytokeratin|keratin",
    "74.a": r"normal wall thickness|no valvular|structurally normal|ejection fraction",
    "74.b": r"nois|exercis|emotional|startl|running|stress|exert",
    "74.c": r"qtc",
    "74.d": r"wall thickness",
    "91.a": r"\bcd31\b|fli-?1",
    "91.b": r"\bcd34\b|bcl-?2|stat6",
    "179.a": r"ivig|intravenous immunoglobulin",
    "179.b": r"sao2|oxygen saturation|saturation|platelet",
}


def matches(a: dict, s_re: re.Pattern, p_re: re.Pattern) -> bool:
    subj = str(a.get("subject") or "")
    pred = str(a.get("predicate") or "")
    quote = str(a.get("quote") or "")
    return bool(s_re.search(subj) or s_re.search(quote)) and \
        bool(p_re.search(pred) or p_re.search(quote))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30")
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11.json").read_text("utf-8"))}
    retrieval = {r["case_key"]: r for r in
                 json.loads((LEDGER / f"trial_retrieval_{args.arm}.json").read_text("utf-8"))}
    extraction = {e["case_key"]: e for e in
                  json.loads((LEDGER / f"trial_extraction_{args.arm}{args.suffix}.json").read_text("utf-8"))}
    engine = {e["case_key"]: e for e in
              json.loads((LEDGER / f"trial_engine_{args.arm}{args.suffix}.json").read_text("utf-8"))}

    rows = []
    for key, task in tasks.items():
        ret = {o["id"]: o for o in retrieval[key]["oracle"]}
        ext = extraction[key]["assertions"]
        findings = extraction[key]["findings"]
        eng = engine[key]

        for a in task["assertions"]:
            s_re = re.compile(a["subject_re"], re.I)
            p_re = re.compile(a["predicate_re"], re.I)

            owners = [c for c in task["candidates"]
                      if s_re.search(c["label"]) or any(s_re.search(x) for x in c.get("aliases") or [])]
            hits = [x for x in ext if matches(x, s_re, p_re)]
            rel_ok = [x for x in hits if (x.get("relation") or "") in
                      (EXCLUSION_RELATIONS if a["kind"] == "exclusion" else INCLUSION_RELATIONS)]

            bound = []
            for x in rel_ok or hits:
                for c in task["candidates"]:
                    if any(concept_match(x["subject"], n)
                           for n in [c["label"], *(c.get("aliases") or [])]):
                        bound.append((x, c["label"]))
                        break

            case_pat = CASE_RE.get(a["id"], "")
            c_re = re.compile(case_pat, re.I) if case_pat else None
            in_vignette = bool(c_re.search(task["vignette"])) if c_re else None
            fnd = [] if c_re is None else [
                f for f in findings
                if c_re.search(str(f.get("label") or "")) or c_re.search(str(f.get("canonical") or ""))
                or c_re.search(str(f.get("quote") or ""))]

            joined = []
            for x, lbl in bound:
                for f in fnd:
                    if concept_match(x["predicate"], f.get("canonical") or "") or \
                            concept_match(x["predicate"], f.get("label") or ""):
                        joined.append((x, lbl, f))
                        break

            if not owners:
                stage = "S0_candidate"
            elif not ret[a["id"]]["retrieved"]:
                stage = "S1_retrieval"
            elif not hits:
                stage = "S2_extraction"
            elif not rel_ok:
                stage = "S3_relation"
            elif not bound:
                stage = "S4_subject_bind"
            elif c_re is not None and not fnd:
                stage = "S5a_vignette_lacks_finding" if not in_vignette else "S5b_case_extractor_missed"
            elif not joined:
                stage = "S6_join"
            else:
                stage = "S7_engine"

            rows.append({
                "case": key, "id": a["id"], "kind": a["kind"],
                "subject": a["subject"], "predicate": a["predicate"],
                "stage_lost": stage,
                "n_candidate_owners": len(owners),
                "retrieved": ret[a["id"]]["retrieved"],
                "n_extracted_matches": len(hits),
                "relations_seen": sorted({x.get("relation") for x in hits})[:6],
                "n_relation_usable": len(rel_ok),
                "n_subject_bound": len(bound),
                "case_pattern": case_pat,
                "patient_fact_in_vignette": in_vignette,
                "n_case_findings_matching": len(fnd),
                "case_finding_labels": [f"{f.get('label')}[{f.get('polarity')}]" for f in fnd][:4],
                "n_joined": len(joined),
                "example_extracted": ({"subject": hits[0].get("subject"),
                                       "predicate": hits[0].get("predicate"),
                                       "relation": hits[0].get("relation"),
                                       "polarity": hits[0].get("polarity"),
                                       "modality": hits[0].get("modality"),
                                       "context": hits[0].get("context_type"),
                                       "quote": str(hits[0].get("quote"))[:160]} if hits else None),
            })

    path = LEDGER / f"trial_failure_trace_{args.arm}{args.suffix}.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    c = Counter(r["stage_lost"] for r in rows)
    print(f"arm={args.arm}  {len(rows)} hand-audited assertions\n")
    for stage in ["S0_candidate", "S1_retrieval", "S2_extraction", "S3_relation",
                  "S4_subject_bind", "S5a_vignette_lacks_finding",
                  "S5b_case_extractor_missed", "S6_join", "S7_engine"]:
        if c.get(stage):
            print(f"  {stage:16s} {c[stage]:2d}")
    print()
    for r in rows:
        print(f"  {r['id']:7s} {r['stage_lost']:16s} ext={r['n_extracted_matches']:3d} "
              f"rel_ok={r['n_relation_usable']:3d} bound={r['n_subject_bound']:3d} "
              f"vign={str(r['patient_fact_in_vignette'])[:5]:5s} find={r['n_case_findings_matching']} "
              f"join={r['n_joined']:3d}  {r['subject'][:32]}")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
