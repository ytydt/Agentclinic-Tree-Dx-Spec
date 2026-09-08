#!/usr/bin/env python3
"""Bounded counterexamples against unchanged production functions; no clinical repair.

The synthetic cases expose technical invariants, not estimates of 11-case clinical
error prevalence. Default deterministic flags isolate each mechanism. F3/F2 marker
probes state their enabled flag explicitly; no embedding/model/network is used.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ENGINE = REPO / "analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py"
spec = importlib.util.spec_from_file_location("identity_audit_engine", ENGINE)
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

def candidate(label, aliases=()):
    return {"label": label, "aliases": list(aliases), "gold_match": "none", "methods": []}

def finding(label, *, canonical=None, polarity="present", number=None, unit=None, **extra):
    return {"label": label, "canonical": label if canonical is None else canonical,
            "polarity": polarity, "value": {"number": number, "unit": unit}, **extra}

def assertion(subject="DiseaseX", predicate="fever", **extra):
    return {"subject": subject, "predicate": predicate, "relation": "feature_of",
            "polarity": "asserted", "modality": "typical", "context_type": "criteria",
            **extra}

def run(candidates, assertions, findings):
    task = {"case_key": "synthetic_identity", "gold": "not_clinically_adjudicated",
            "gold_labels_in_set": [], "candidates": candidates}
    return eng.run_case(copy.deepcopy(task), copy.deepcopy({"assertions": assertions, "findings": findings}))

def main():
    checks = []
    def add(rid, defect, observed, expected_current, invariant):
        passed = observed == expected_current
        checks.append({"id": rid, "defect_id": defect, "observed": observed,
                       "expected_current_behavior": expected_current,
                       "required_invariant_after_repair": invariant,
                       "probe_kind": "negative_control" if rid == "IDR13" else ("paired_mechanism_component" if rid in {"IDR05", "IDR15"} else "mechanism_probe"),
                       "current_behavior_reproduced": passed})
        assert passed, (rid, observed, expected_current)

    add("IDR01", "IDN-01", eng.norm("Carcinoma (lung)") == eng.norm("Carcinoma (kidney)"), True,
        "Parenthetical site qualifiers cannot be deleted before identity resolution.")
    add("IDR02", "IDN-01", eng.predicate_match("normal QT interval", "prolonged QT interval"), "containment",
        "Normality and abnormal direction remain constraints, not stopwords.")
    add("IDR03", "IDN-01", eng.predicate_match("with fever", "without fever"), "containment",
        "Surface negation must survive parsing into polarity; matching may not silently drop it.")

    cs = [candidate("Carcinoma"), candidate("Sarcomatoid carcinoma")]
    a = [assertion("Sarcomatoid carcinoma")]
    f = [finding("fever")]
    left, right = run(cs, a, f), run(list(reversed(cs)), a, f)
    add("IDR04", "IDN-02", [x["candidate"] for x in left["pairs"]], ["Carcinoma"], "All candidates are searched for exact/verified identity before broader fallback.")
    add("IDR05", "IDN-02", [x["candidate"] for x in right["pairs"]], ["Sarcomatoid carcinoma"], "Candidate permutations preserve binding target.")
    badalias = run([candidate("Hemangioma", ["Angiosarcoma"]), candidate("Angiosarcoma")], [assertion("Angiosarcoma")], f)
    add("IDR06", "IDN-03", badalias["pairs"][0]["candidate"], "Hemangioma", "An unvalidated alias cannot override canonical exact identity or merge benign/malignant concepts.")
    dup = run([candidate("DiseaseX"), candidate("diseasex")], [assertion("DiseaseX")], f)
    add("IDR07", "IDN-03", {r["label"]: r["n_assertions"] for r in dup["ranking"]}, {"DiseaseX": 1, "diseasex": 0}, "Safe format duplicate candidates share a single concept without empty ranked copies.")
    add("IDR08", "IDN-04", [eng.subject_match("Idiopathic pulmonary arterial hypertension", "Pulmonary hypertension"), eng.subject_match("Pulmonary hypertension", "Idiopathic pulmonary arterial hypertension")], ["containment", "containment"], "Equivalence and directed subsumption are separate relation types and proof policies.")
    eng.FIX_ORGANISM = True
    add("IDR09", "IDN-05", eng.subject_match("Brucella", "Brucellosis"), "med_stem", "Organism-causes-disease is not synonym identity; predicate role controls permissible transfer.")
    eng.FIX_ORGANISM = False

    # First finding has an exact label, but an earlier, weaker canonical match
    # prevents that label from being examined. A second exact candidate steals it.
    fs = [finding("specific fever", canonical="fever"), finding("other observation", canonical="specific fever")]
    got = run([candidate("DiseaseX")], [assertion(predicate="specific fever")], fs)
    add("IDR10", "IDN-06", got["pairs"][0]["finding"], "other observation", "Rank all representations of every finding; do not stop at its first canonical hit.")
    fa = finding("fever", polarity="absent", event_id="earlier")
    fp = finding("fever", polarity="present", event_id="later")
    outcomes = [run([candidate("DiseaseX")], [assertion()], order)["ranking"][0]["score"] for order in ([fa, fp], [fp, fa])]
    add("IDR11", "IDN-06", outcomes, [-0.4, 0.8], "Equal lexical matches require event/scope reconciliation or unresolved conflict; list order is not evidence.")
    add("IDR12", "IDN-07", eng.predicate_match("PECAM-1", "CD31"), "", "Verified marker synonym lookup should bridge this pair without equating diseases expressing it.")
    add("IDR13", "IDN-07", eng.predicate_match("CD31 positive", "CD31 negative"), "", "A negative marker observation must never satisfy a positive literal.")
    eng.FIX_MARKER = True
    add("IDR14", "IDN-07", eng.predicate_match("CD31 positive", "CD31 negative"), "marker", "F2 marker identity must be followed by explicit value/polarity evaluation, not treated as satisfied.")
    eng.FIX_MARKER = False
    add("IDR15", "IDN-08", list(eng.threshold_ok(assertion(threshold={"operator": ">", "value": 30, "unit": "mmHg"}), finding("different pressure", number=35, unit="mmHg"))), [True, "35.0mmhg > 30.0mmhg"], "Typed measurand, method, site, role and time are established before numeric comparison.")
    add("IDR16", "IDN-08", eng.threshold_ok(assertion(threshold={"operator": ">", "value": 30, "unit": "mmHg"}), finding("pressure", number=35))[0], True, "Missing dimensional units do not silently certify a dimensional comparison.")
    add("IDR17", "IDN-08", eng.threshold_ok(assertion(threshold={"operator": ">", "value": 1, "unit": "Mg"}), finding("mass", number=2, unit="mg"))[0], True, "2 mg > 1 Mg is false after UCUM conversion; case-sensitive units cannot be lowercased to identity.")
    add("IDR18", "IDN-08", eng.threshold_ok(assertion(threshold={"operator": ">", "value": 1}), finding("quantity", number="NaN"))[0], False, "Non-finite numeric values yield invalid/unknown, not clinical threshold violation.")
    try:
        eng.threshold_ok(assertion(threshold={"operator": "range", "value": 1, "value_high": "not_numeric"}), finding("quantity", number=2))
        err = None
    except Exception as exc:
        err = type(exc).__name__
    add("IDR19", "IDN-08", err, "ValueError", "Malformed upper range bounds return a structured invalid state rather than crashing a run.")

    ats = [assertion(threshold={"operator": ">", "value": 3}, modality="rare"), assertion(threshold={"operator": ">", "value": 10}, modality="obligatory")]
    out = run([candidate("DiseaseX")], ats, [finding("fever", number=5)])
    rev = run([candidate("DiseaseX")], list(reversed(ats)), [finding("fever", number=5)])
    add("IDR20", "IDN-09", [out["n_assertions_bound"], out["ranking"][0]["score"], rev["ranking"][0]["score"]], [1, 1.5, 0.5], "Different thresholds remain distinct rules; provenance and modality cannot be fused across rows.")
    eq = run([candidate("DiseaseX")], [assertion(predicate="fever"), assertion(predicate="presence of fever")], f)
    add("IDR21", "IDN-10", [eq["n_assertions_bound"], eq["ranking"][0]["score"]], [2, 1.6], "Equivalent surface predicates may share a semantic object; repeated textual support is not independent patient evidence.")
    fv = finding("serology", canonical="laboratory serology")
    fv["value"]["text"] = "Brucella positive"
    val = run([candidate("DiseaseX")], [assertion(predicate="Brucella")], [fv])
    add("IDR22", "IDN-11", val["join_stats"], {"matched": 0, "unmatched": 1}, "Typed observed result text must participate in binding; concatenate-to-label is not a sufficient repair.")
    wrong_kind = run([candidate("DiseaseX")], [assertion(predicate="neutrophils", predicate_kind="histopathology")], [finding("neutrophils", kind="lab", qualifiers={"site": "blood"})])
    add("IDR23", "IDN-12", wrong_kind["join_stats"], {"matched": 1, "unmatched": 0}, "Existing predicate_kind/kind and site metadata constrain admissible joins before lexical scoring.")
    payload = {"schema_version": 1, "production_file": str(ENGINE.relative_to(REPO)),
               "production_sha256": hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
               "scope": "23 synthetic technical checks including 1 explicit negative control and paired mechanism components, using unchanged production functions; not 23 independent errors or clinical prevalence/end-to-end efficacy",
               "flags": "production module defaults except isolated FIX_ORGANISM/FIX_MARKER probes; no gate/embedding/network",
               "checks": checks, "n_checks": len(checks), "all_passed": all(c["current_behavior_reproduced"] for c in checks)}
    (HERE / "identity_reproduction_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"n_checks": len(checks), "all_passed": payload["all_passed"]}))

if __name__ == "__main__":
    main()
