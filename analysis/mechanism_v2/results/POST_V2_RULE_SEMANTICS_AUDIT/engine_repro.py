#!/usr/bin/env python3
"""Audit-only deterministic counterexamples against the checked-out engine.

No medical propositions, LLM calls, downloads, production changes, or gold-based
repairs. Synthetic signal names isolate schema/execution behavior. Successful
assertions below mean the *documented defect was reproduced*, not clinical
correctness. Exact lexical joins and in-memory provenance isolate the defects
from optional embeddings, corpus weights, and unavailable LFS artifacts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(SRC))
import run_mechanical_engine as eng
import gate_assertions as gate
import run_trial_extraction as extract

DEFAULTS = {
    "JOIN_MODE": "strict", "WEIGHT_SCHEME": "none", "USE_CRITERION_GROUPS": True,
    "DISCRIMINATIVE_ONLY": False, "CLOSED_WORLD": False, "FIX_MARKER": False,
    "FIX_EMBED_TAU": 0.0, "FIX_ORGANISM": False, "FIX_ENUM": False,
    "CORPUS_LR": None, "FIX_ANCHOR_EMBED": False, "GROUP_ALL_IS_REQUIRED": False,
    "FIX_QUOTE_GATE": False, "FIX_NLI": False, "RIGID_REQUIRED_ANY_MODALITY": False,
    "RIGID_SUFFICIENT_CONFIRMS": False, "RIGID_PATHO_READS_THRESHOLD": False,
    "RIGID_REQUIRED_CLOSED_WORLD": False, "NONCRITERION_INERT": False,
    "FINDING_POOL_BETA": 0.0, "LAYER3_DROP": set(),
}


def finding(label, polarity="present", number=None, unit=None, **kw):
    return dict(label=label, canonical=label, polarity=polarity,
                value={"number": number, "unit": unit}, **kw)


def assertion(predicate, relation="feature_of", polarity="asserted",
              gid=None, logic="all", n=None, subject="Index disease", **kw):
    out = dict(subject=subject, predicate=predicate, relation=relation,
               polarity=polarity, modality="obligatory", threshold={},
               context_type="criteria", quote=f"Synthetic source: {predicate}.",
               _source="synthetic", _title="Synthetic chapter", _section="Criteria",
               _focus=subject, criterion_group={"group_id": gid,
                  "logic": logic if gid else None, "n": n})
    out.update(kw)
    return out


def run(rows, facts, labels=None, **flags):
    for key, val in {**DEFAULTS, **flags}.items():
        setattr(eng, key, val)
    gate._PASSAGE_INDEX = {"by_key": {}, "by_sha": {}}
    labels = labels or ["Index disease", "Other disease"]
    task = dict(case_key="synthetic/audit", gold=labels[0],
                gold_labels_in_set=[labels[0]],
                candidates=[dict(label=x, aliases=[], gold_match=i == 0, methods=[])
                            for i, x in enumerate(labels)])
    return eng.run_case(task, dict(assertions=copy.deepcopy(rows), findings=copy.deepcopy(facts)))


def verdict(result, label="Index disease"):
    return next(x for x in result["ranking"] if x["label"] == label)


def brief(result):
    return {"top1": result["top1"], "n_assertions_bound": result["n_assertions_bound"],
            "ranking": [{k: v[k] for k in ("label", "score", "eliminated", "confirmed", "contributions")}
                        for v in result["ranking"]]}


def main():
    cases = []

    def add(identifier, expected, observed, evidence):
        cases.append(dict(id=identifier, expected_semantics=expected,
                          observed_defect=observed, evidence=evidence, reproduced=True))

    # A signed absent literal is true when the finding is explicitly absent.
    rows = [assertion("redsignal", "required_for", gid="g"),
            assertion("bluesignal", "required_for", polarity="negated", gid="g")]
    r = run(rows, [finding("redsignal"), finding("bluesignal", "absent")])
    assert verdict(r)["eliminated"]
    add("E01_group_signed_literal_inverted", "redsignal AND NOT bluesignal is satisfied.",
        "Negative member is treated as violated and the disease is eliminated.", brief(r))

    rows = [assertion("redsignal", "required_for", gid="g",
                      threshold={"operator": ">=", "value": 10}),
            assertion("bluesignal", "required_for", gid="g")]
    r = run(rows, [finding("redsignal", number=1), finding("bluesignal")])
    assert not verdict(r)["eliminated"] and verdict(r)["contributions"][0]["n_satisfied"] == 2
    add("E02_group_threshold_ignored", "redsignal >= 10 is false at 1; necessary all-group fails.",
        "Group counts both members satisfied and adds +1.", brief(r))

    for logic, n in [("any", None), ("at_least_n", 2)]:
        rows = [assertion(x, "required_for", gid="g", logic=logic, n=n)
                for x in ("redsignal", "bluesignal", "greensignal")]
        facts = [finding(x, "absent") for x in ("redsignal", "bluesignal", "greensignal")]
        r = run(rows, facts)
        assert not verdict(r)["eliminated"]
        add("E03_necessary_" + logic + "_no_veto", "Explicit false necessary group must register violation.",
            "No hard-rule path exists for this connective.", brief(r))

    rows = [assertion(x, "sufficient_for", gid="g") for x in ("redsignal", "bluesignal")]
    r = run(rows, [finding("redsignal"), finding("bluesignal")], RIGID_SUFFICIENT_CONFIRMS=True)
    assert not verdict(r)["confirmed"]
    add("E04_sufficient_group_no_confirmation", "Fully satisfied sufficient group produces confirmation.",
        "Even enabled sufficient confirmation is bypassed for grouped rows; only +1.", brief(r))

    r = run(rows, [finding("redsignal"), finding("bluesignal", "absent")], GROUP_ALL_IS_REQUIRED=True)
    assert verdict(r)["eliminated"]
    add("E05_f4b_inverts_sufficient_into_necessary", "Failure of a sufficient-only condition does not exclude.",
        "F4b makes every all-group necessary and eliminates on missing limb.", brief(r))

    rows = [assertion(x, "excludes", gid="g") for x in ("redsignal", "bluesignal")]
    r = run(rows, [finding("redsignal"), finding("bluesignal")])
    assert not verdict(r)["eliminated"] and verdict(r)["score"] > 0
    add("E06_satisfied_exclusion_group_rewards_subject", "Satisfied exclusion antecedent excludes its subject.",
        "Grouped excludes rows bypass exclusion and add positive evidence for their subject.", brief(r))

    a = assertion("redsignal", "required_for", threshold={"operator": ">=", "value": 3})
    b = assertion("redsignal", "required_for", threshold={"operator": ">=", "value": 10})
    r1 = run([a, b], [finding("redsignal", number=5)])
    r2 = run([b, a], [finding("redsignal", number=5)])
    assert not verdict(r1)["eliminated"] and verdict(r2)["eliminated"]
    add("E07_dedupe_destroys_threshold_and_order_invariance", "Different thresholds are distinct rules; order cannot choose truth.",
        "Dedup omits threshold/context/source and keeps the first, reversing veto on reordering.",
        {"low_first": brief(r1), "high_first": brief(r2)})

    rows = [assertion("redsignal", "sufficient_for", gid="g1"),
            assertion("bluesignal", "sufficient_for", gid="g1"),
            assertion("redsignal", "sufficient_for", gid="g2"),
            assertion("greensignal", "sufficient_for", gid="g2")]
    r = run(rows, [finding("redsignal", "absent"), finding("bluesignal", "absent"),
                   finding("greensignal")], RIGID_SUFFICIENT_CONFIRMS=True)
    assert verdict(r)["confirmed"] and r["n_assertions_bound"] == 3
    add("E08_dedupe_erodes_shared_group_to_false_atomic_confirmation",
        "Neither (red AND blue) nor (red AND green) is satisfied; no group can confirm.",
        "Shared red row lost; g2 becomes singleton and green alone confirms.", brief(r))

    rows = [assertion(x, gid="g1", _passage_sha1=sha)
            for sha, names in [("first", ("redsignal", "bluesignal")),
                               ("second", ("greensignal", "yellowsignal"))] for x in names]
    r = run(rows, [finding(x) for x in ("redsignal", "bluesignal", "greensignal", "yellowsignal")])
    groups = [x for x in verdict(r)["contributions"] if x["why"].startswith("group:")]
    assert len(groups) == 1 and groups[0]["n_members"] == 4
    add("E09_passage_local_group_ids_merge_across_passages", "Two passage-local g1 groups retain separate identities.",
        "Group key omits passage hash/source and merges 4 members into one group.", brief(r))

    rows = [assertion("redsignal", gid="g", logic="at_least_n", n=2),
            assertion("bluesignal", gid="g", logic="at_least_n", n=3),
            assertion("greensignal", gid="g", logic="at_least_n", n=3)]
    facts = [finding("redsignal"), finding("bluesignal"), finding("greensignal", "absent")]
    r1, r2 = run(rows, facts), run(rows[::-1], facts)
    assert verdict(r1)["score"] != verdict(r2)["score"]
    add("E10_group_contract_inconsistency_unchecked", "Mixed n values must invalidate a group rather than choose a member.",
        "First member supplies n/logic and input order changes score.", {"first_n2": brief(r1), "first_n3": brief(r2)})

    rows = [assertion("redsignal", subject="Bacterial infection")]
    r1 = run(rows, [finding("redsignal")], ["Infection", "Bacterial infection"])
    r2 = run(rows, [finding("redsignal")], ["Bacterial infection", "Infection"])
    assert r1["top1"] == "Infection" and r2["top1"] == "Bacterial infection"
    add("E11_subject_first_containment_beats_later_exact", "An exact named subject takes priority over a broader parent.",
        "First candidate with any lexical hit steals the assertion; order changes binding.",
        {"parent_first": brief(r1), "specific_first": brief(r2)})

    assert eng.predicate_match("normal ECG", "abnormal ECG")
    r = run([assertion("normal ECG", "required_for")], [finding("normal ECG", "normal")])
    assert verdict(r)["eliminated"]
    add("E12_normality_not_a_universal_false_value", "A finding satisfying 'normal ECG' is true, independent of token 'normal'.",
        "normal/abnormal are removed in join; finding polarity normal universally means violation.", brief(r))

    r = run([assertion("redsignal", "pathognomonic_for",
                       threshold={"operator": ">=", "value": 10, "unit": "mg/dL"})],
            [finding("redsignal", number=0.2, unit="mmol/L")], RIGID_PATHO_READS_THRESHOLD=True)
    assert verdict(r)["confirmed"]
    add("E13_unknown_numeric_comparison_confirms", "Unit mismatch is unknown and cannot establish a numeric antecedent.",
        "Even threshold-aware confirmation checks is not False, so unknown passes.", brief(r))

    r = run([assertion("redsignal", "excludes", modality="rare",
                       threshold={"operator": ">=", "value": 10})], [finding("redsignal", number=1)])
    assert verdict(r)["eliminated"]
    add("E14_excludes_ignores_threshold_and_modality", "Unsatisfied numeric antecedent must not trigger exclusion.",
        "Rare assertion with cutoff >=10 eliminates at value1 because present alone is used.", brief(r))

    r = run([assertion("redsignal", "argues_against", modality="rare")], [finding("redsignal")])
    assert verdict(r)["eliminated"]
    add("E15_argues_against_is_hard_exclusion", "Defeasible counterevidence is not a logical contradiction.",
        "argues_against and excludes have identical unconditional veto branch.", brief(r))

    r1 = run([assertion("redsignal")], [finding("redsignal")])
    r2 = run([assertion(p) for p in ("redsignal", "redsignal finding", "redsignal feature")], [finding("redsignal")])
    assert verdict(r2)["score"] == 3 * verdict(r1)["score"]
    add("E16_paraphrase_count_inflates_one_fact", "Synonymous assertions about one fact must not create three independent evidence units.",
        "Dedup uses full normalized predicate; lexical joins collapse synonyms only after dedup, giving +3 vs +1.",
        {"single": brief(r1), "paraphrases": brief(r2)})

    rows = [assertion(p, gid="g", logic="at_least_n", n=2)
            for p in ("redsignal", "redsignal finding")]
    r = run(rows, [finding("redsignal")])
    assert verdict(r)["contributions"][0]["n_satisfied"] == 2
    add("E17_cardinality_counts_rows_not_distinct_criteria", "One finding does not instantiate two independently required criteria by paraphrase.",
        "Two members bind to the same fact and satisfy an at_least_2 count.", brief(r))

    r1 = run([assertion("redsignal", context_type="table_row")], [finding("redsignal")])
    r2 = run([assertion(x, gid="g", context_type="table_row") for x in ("redsignal", "bluesignal")],
             [finding("redsignal"), finding("bluesignal")])
    assert verdict(r1)["score"] == 0 and verdict(r2)["score"] > 0
    add("E18_group_bypasses_soft_context_scoring_filter", "The same table-row context policy should hold whether rows are grouped.",
        "Standalone table rows inert; fully soft groups still add score.", {"standalone": brief(r1), "grouped": brief(r2)})

    a = assertion("redsignal", gid="g", logic="at_least_n", n=None)
    stats = Counter()
    extract.normalise_group(a, stats)
    assert a["criterion_group"]["logic"] == "any"
    add("E19_invalid_quantifier_silently_repaired_to_any", "Missing numeric threshold is unresolved, not one-of.",
        "normalise_group silently changes at_least_n with missing n to any.", {"after": a, "stats": dict(stats)})

    q = "At least 2 criteria include redsignal >= 10 and bluesignal <= 5."
    parsed = gate.parse_threshold_from_quote(q)
    assert parsed is None
    short_q = "redsignal >= 10 and bluesignal <= 5."
    assert gate.parse_threshold_from_quote(short_q) is None
    q2 = "redsignal has a measurement which is >= 10 and bluesignal <= 5."
    a = assertion("bluesignal", quote=q2)
    out = extract.postprocess_grounded({"mentioned_diseases": ["Index disease"], "assertions": [a]},
                                       "Index disease: " + q2)[0]
    assert out["threshold"]["value"] == 10 and out["threshold"]["operator"] == ">="
    add("E20_numeric_parse_not_bound_to_predicate", "Ignore lead-in count; each measurement owns its own cutoff.",
        "First bare number blocks later comparison; greedy prefix can consume the operator; first parsed comparison belongs to wrong measurement.",
        {"leading_count_quote": q, "leading_count_parsed": parsed,
         "short_quote": short_q, "short_quote_parsed": None, "second_measurement": out})

    a = assertion("normal redsignal", "excludes", polarity="negated", modality="typical",
                  quote="A normal redsignal is less than 10 ms.")
    out = gate.gate_one(a)
    assert out["relation"] == "required_for" and out["threshold"]["operator"] == ">"
    add("E21_gate_reference_range_creates_necessity_and_wrong_complement",
        "A normal reference range alone does not license disease necessity; complement of <10 is >=10.",
        "G2 promotes to obligatory required_for and uses >10, excluding boundary10.", out)

    rows = [assertion("redsignal", rel, quote="Index disease if and only if redsignal is present.")
            for rel in ("required_for", "pathognomonic_for")]
    out = gate._g1_drop_dual_patho(rows)
    assert {x["relation"] for x in out} == {"required_for", "feature_of"}
    add("E22_gate_rejects_valid_biconditional_by_schema", "A definitional biconditional can be necessary and sufficient.",
        "G1 unconditionally demotes the pathognomonic row sharing subject/quote prefix with necessity.", out)

    a = assertion("redsignal", "excludes", quote="This invented quote never occurs in the source.",
                  _passage="Index disease is described here without an exclusion rule.")
    out = gate.gate_one(a)
    assert out["relation"] == "excludes" and not out.get("_gate_drop")
    add("E23_quote_membership_not_validated_for_excludes", "An unalignable exclusion claim lacks evidence and must not be authorized.",
        "Gate accepts asserted excludes without quote membership or source exclusion cue.", out)

    rows = [assertion("redsignal", "required_for")]
    f_old, f_now = finding("redsignal", "absent", time="previous"), finding("redsignal", time="current")
    r1, r2 = run(rows, [f_old, f_now]), run(rows, [f_now, f_old])
    assert verdict(r1)["eliminated"] and not verdict(r2)["eliminated"]
    add("E24_tied_finding_joins_ignore_time_and_input_order", "Current and historical observations have separate scope; ordering is not temporal adjudication.",
        "Equal lexical match keeps first finding; rearranging history reverses veto.", {"past_first": brief(r1), "current_first": brief(r2)})

    # Only the group grouping rule is exercised; no pattern-matching or cue claim.
    rows = [assertion(x, "required_for", quote="Index disease requires redsignal and bluesignal and/or greensignal.")
            for x in ("redsignal", "bluesignal", "greensignal")]
    out = gate._merge_and_or_required(rows)
    assert all(x["criterion_group"]["logic"] == "any" for x in out)
    add("E25_gate_mixed_boolean_expression_flattened", "red AND (blue OR green) retains the mandatory red limb.",
        "Any 'and/or' in shared quote makes every matching required row one any group.", out)

    q = "Index disease redsignal is a typical feature. Separate condition is diagnosed by bluesignal."
    a = assertion("redsignal", "pathognomonic_for", quote="redsignal is a typical feature", _passage=q)
    out = gate.gate_one(a)
    assert out["relation"] == "pathognomonic_for"
    add("E26_gate_neighbour_cue_licenses_wrong_relation", "A sufficiency cue about another subject does not authorize this feature.",
        "Pathognomonic cue searches entire licensed neighbourhood without subject/predicate scope.", out)

    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, text=True,
                              capture_output=True, check=True).stdout.strip()
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [SRC / "run_mechanical_engine.py", SRC / "gate_assertions.py", SRC / "run_trial_extraction.py"]}
    output = dict(audit_kind="synthetic deterministic semantic counterexamples", revision=revision,
                  production_sha256=hashes, n_counterexamples=len(cases),
                  limitations=["Not prevalence estimates or clinical validation.",
                               "Flags isolate mechanisms; not an exact B1+S7 cohort replay.",
                               "All group tests use the same unmodified group evaluator as B1+S7.",
                               "Optional embeddings/LR/provenance loading disabled unless directly under test."],
                  cases=cases)
    path = HERE / "engine_repro_results.json"
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"n_counterexamples": len(cases), "all_reproduced": True,
                      "output": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
