#!/usr/bin/env python3
"""Independent finite counterexamples for the stage/scope supplement.

This reads the author's synthetic fixtures and calls the finite checker with
separately constructed mutations and truth-table expectations. It neither edits
production code nor evaluates real patients, source fidelity, or a general FOL
theory. Results are deliberately distinct from the author's acceptance vectors.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ("validate_supplement.py", "supplemental_examples.json", "supplemental_vectors.json", "SEMANTIC_SUPPLEMENT.md")
T, F, U = "TRUE", "FALSE", "UNKNOWN"


def digest(name):
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


def main():
    before = {name: digest(name) for name in FILES}
    module = types.ModuleType("reviewed_supplement")
    module.__file__ = str(HERE / "validate_supplement.py")
    exec(compile((HERE / "validate_supplement.py").read_text(), module.__file__, "exec"), module.__dict__)
    examples = json.loads((HERE / "supplemental_examples.json").read_text())
    rules = {r["rule_id"]: r for r in examples["rules"]}
    branches = {b["branch_set_id"]: b for b in examples["branch_sets"]}
    rows = []

    def check(key, actual, expected):
        rows.append({"check_id": key, "actual": actual, "expected": expected, "passed": actual == expected})

    def reject(key, action):
        try:
            action()
        except ValueError as exc:
            rows.append({"check_id": key, "passed": True, "actual": {"rejected": True, "reason": str(exc)}, "expected": {"rejected": True}})
        else:
            rows.append({"check_id": key, "passed": False, "actual": {"rejected": False}, "expected": {"rejected": True}})

    def clone(rule_id="S_GUARDED_SUFFICIENT"):
        return copy.deepcopy(rules[rule_id])

    # Explicit, independently specified Kleene tables, not derived from the
    # checker's implementations of conjunction/disjunction/negation.
    assignments = list(itertools.product((T, F, U), repeat=2))
    and_expected = (T, F, U, F, F, F, U, F, U)
    or_expected = (T, T, T, T, F, U, T, U, U)
    for op, expected in (("and", and_expected), ("or", or_expected)):
        for i, ((left, right), wanted) in enumerate(zip(assignments, expected), 1):
            expr = {"op": op, "children": [{"op": "fact", "key": "A"}, {"op": "fact", "key": "B"}]}
            check(f"K3_{op}_{i}", module.truth(expr, {"A": left, "B": right}), wanted)
    for given, wanted in ((T, F), (F, T), (U, U)):
        check(f"K3_not_{given}", module.truth({"op": "not", "child": {"op": "fact", "key": "A"}}, {"A": given}), wanted)

    # All 27 scope/condition/action combinations for the three rigid effects.
    for effect in ("necessary_for_target", "sufficient_for_target", "sufficient_for_exclusion"):
        for scope, condition in itertools.product((T, F, U), repeat=2):
            rule = clone()
            rule["effect"]["kind"] = effect
            result = module.evaluate_rule(rule, {"G": scope, "C": condition})
            wanted = None
            if scope == T and ((effect == "necessary_for_target" and condition == F) or (effect == "sufficient_for_exclusion" and condition == T)):
                wanted = "EXCLUDE"
            if scope == T and effect == "sufficient_for_target" and condition == T:
                wanted = "CONFIRM"
            check(f"MATRIX_{effect}_{scope}_{condition}", result["action"], wanted)

    # Review and effect authority are independent of the truth of the condition.
    for effect, condition in (("necessary_for_target", F), ("sufficient_for_target", T), ("sufficient_for_exclusion", T)):
        for gate in ("classification", "scope_source", "effect"):
            rule = clone()
            rule["effect"]["kind"] = effect
            if gate == "classification":
                rule["classification_status"] = "unresolved"
            elif gate == "scope_source":
                rule["provenance"]["scope_source_status"] = "unresolved"
            else:
                rule["effect"]["fixture_effect_authorized"] = False
            check(f"GATE_{effect}_{gate}", module.evaluate_rule(rule, {"G": True, "C": condition})["action"], None)

    for target in ("test", "treatment", "workflow", "observation", "inference_action"):
        rule = clone()
        rule["target"]["type"] = target
        reject(f"TYPE_diagnostic_target_{target}", lambda r=rule: module.validate_rule(r))

    # The original literal UNKNOWN -> FALSE -> EXCLUDE counterexample.
    rule = clone()
    rule["effect"]["kind"] = "necessary_for_target"
    rule["condition"] = {"op": "eq", "key": "X.result", "value": "positive"}
    for missing in (None, U):
        result = module.evaluate_rule(rule, {"G": True, "X.result": missing})
        check(f"UNKNOWN_EQ_{missing}", [result["condition"], result["action"]], [U, None])
    reject("EQ_wrong_observation_type", lambda: module.evaluate_rule(rule, {"G": True, "X.result": 1}))

    # Recommendation/result state distinction and correct absence of disease
    # target. Having a positive result does not require an explicit order record.
    recommendation = clone("S_RECOMMEND_TEST")
    check("NO_DISEASE_TARGET_workflow", [recommendation["disease_context"], module.evaluate_rule(recommendation, {"symptom_C": True})["channel"]], [[], "workflow"])
    for state in ("recommended", "ordered", "in_progress", "completed"):
        result = module.evaluate_rule(rules["S_RESULT_DIAG"], {"test_X.request_state": state})
        check(f"STATE_no_result_{state}", result["action"], None)
    result = module.evaluate_rule(rules["S_RESULT_DIAG"], {"test_X.result_status": "final", "test_X.result_value": "positive"})
    check("STATE_real_result_without_order", result["action"], "CONFIRM")
    result = module.evaluate_rule(rules["S_RESULT_DIAG"], {"test_X.result_status": "final", "test_X.result_value": "negative"})
    check("STATE_sufficient_negative_not_exclude", result["action"], None)

    # An independently authorized diagnostic response is not erased just by a
    # treatment-stage annotation; a treatment recommendation is never a disease.
    response_facts = {"treatment_T.state": "completed", "response_R_observed": True, "response_time_window_valid": True}
    response = clone("S_RESPONSE_DIAG")
    response["care_process_stages"] = ["treatment"]
    check("CROSS_STAGE_authorized_response_retained", module.evaluate_rule(response, response_facts)["action"], "CONFIRM")
    for key in ("response_R_observed", "response_time_window_valid"):
        incomplete = dict(response_facts)
        incomplete.pop(key)
        check(f"CROSS_STAGE_missing_{key}", module.evaluate_rule(response, incomplete)["action"], None)
    check("PROHIBITION_is_workflow", module.evaluate_rule(rules["S_TREAT_PROHIBIT"], {"contraindication_C": True})["channel"], "workflow")

    # Eligibility direction must not silently mean iff.
    for effect, expected in (("eligibility_sufficient", ("ELIGIBLE", None, None)), ("eligibility_necessary", (None, "NOT_ELIGIBLE", None)), ("eligibility_complete_definition", ("ELIGIBLE", "NOT_ELIGIBLE", None))):
        for given, wanted in zip((T, F, U), expected):
            rule = clone("S_TREAT_ELIGIBILITY")
            rule["condition"] = {"op": "fact", "key": "C"}
            rule["effect"]["kind"] = effect
            rule["effect"]["complete_eligibility_basis_source_authorized"] = True
            check(f"ELIGIBILITY_{effect}_{given}", module.evaluate_rule(rule, {"C": given})["action"], wanted)
    rule = clone("S_TREAT_ELIGIBILITY")
    rule["effect"]["kind"] = "eligibility_complete_definition"
    rule["effect"]["complete_eligibility_basis_source_authorized"] = False
    reject("ELIGIBILITY_no_iff_authority", lambda: module.validate_rule(rule))

    for rule_id, facts in (("S_RECOMMEND_TEST", {"symptom_C": True}), ("S_TREAT_PROHIBIT", {"contraindication_C": True}), ("S_METHOD_PERMISSION", {"method_X_under_consideration": True}), ("S_TREAT_ELIGIBILITY", {"diagnosis_D_already_established": True, "eligibility_C": True})):
        rule = clone(rule_id)
        rule["effect"]["fixture_effect_authorized"] = False
        check(f"ALL_CHANNEL_AUTHORITY_{rule_id}", module.evaluate_rule(rule, facts)["action"], None)
    for malformed in ("false", "true", 0, 1, None):
        rule = clone()
        rule["effect"]["fixture_effect_authorized"] = malformed
        reject(f"AUTHORITY_strict_boolean_{malformed!r}", lambda r=rule: module.validate_rule(r))

    # Root authority cannot be borrowed through an unreviewed branch/guard.
    for mutation in ("classification", "source_complete", "guard"):
        branch = copy.deepcopy(branches["B_COLLECT_UNKNOWNS"])
        if mutation == "classification":
            branch["classification_status"] = "unresolved"
        elif mutation == "source_complete":
            branch["source_structure_complete"] = False
        else:
            branch["branches"][0]["guard_review_status"] = "unresolved"
        check(f"BRANCH_GATE_{mutation}", module.run_branch(branch, rules, {"guard_A": True, "guard_B": True, "marker_A": True, "marker_B": True})["admitted_actions"], [])
    for value in (F, U):
        branch = copy.deepcopy(branches["B_COLLECT_UNKNOWNS"])
        branch["parent_scope"] = {"op": "const", "value": value}
        check(f"BRANCH_parent_{value}", module.run_branch(branch, rules, {"guard_A": True, "guard_B": True, "marker_A": True, "marker_B": True})["admitted_actions"], [])

    priority = copy.deepcopy(branches["B_EXPLICIT_PRIORITY"])
    priority["priority_source_authorized"] = False
    reject("PRIORITY_direct_runtime_authority", lambda: module.run_branch(priority, rules, {"exception_guard": True, "general_guard": True, "marker_A": True}))
    priority = copy.deepcopy(branches["B_EXPLICIT_PRIORITY"])
    result = module.run_branch(priority, rules, {"exception_guard": U, "general_guard": True, "marker_A": True})
    check("PRIORITY_unknown_exception", result["admitted_actions"], [])
    reverse = copy.deepcopy(priority)
    reverse["branches"].reverse()
    facts = {"exception_guard": True, "general_guard": True, "marker_A": True, "marker_B": True}
    check("PRIORITY_array_permutation", module.route(priority, facts, rules)["selected"], module.route(reverse, facts, rules)["selected"])

    local = branches["B_PRIORITY_WITH_LOCAL_SCOPE"]
    facts = {"exception_guard": True, "general_guard": True, "patient.age_years_at_index": 40, "marker_A": False, "marker_B": True}
    check("PRIORITY_inapplicable_high_uses_low", module.route(local, facts, rules)["selected"], ["GENERAL"])
    facts.pop("patient.age_years_at_index")
    check("PRIORITY_unknown_high_local_scope_defers_low", module.run_branch(local, rules, facts)["admitted_actions"], [])
    # Array order cannot authorize override of an unrelated disease or activity.
    other = copy.deepcopy(rules)
    other[priority["branches"][1]["rule_ref"]]["target"]["id"] = "UNRELATED_DISEASE"
    reject("PRIORITY_cross_target_override_rejected", lambda: module.run_branch(priority, other, {"exception_guard": True, "general_guard": True}))

    for age, wanted in ((None, []), (40, ["ELSE"]), (11, ["CHILD"]), (70, ["ELDER"])):
        facts = {} if age is None else {"patient.age_years_at_index": age}
        check(f"ELSE_age_{age}", module.route(branches["B_AGE_ELSE"], facts, rules)["selected"], wanted)
    parent_false_else = copy.deepcopy(branches["B_AGE_ELSE"])
    parent_false_else["parent_scope"] = {"op": "const", "value": F}
    check("ELSE_parent_false_no_fallthrough", module.route(parent_false_else, {"patient.age_years_at_index": 40}, rules)["selected"], [])
    # Source "otherwise" must retain its original guard scope. Adding a local
    # hospital requirement to child criteria does not turn a child into an adult.
    else_rules = copy.deepcopy(rules)
    child = else_rules["S_CHILD_NECESSARY"]
    child["applicability"] = {"op": "and", "children": [child["applicability"], {"op": "fact", "key": "hospital_scope"}]}
    facts = {"patient.age_years_at_index": 10, "hospital_scope": False, "marker_A": True}
    result = module.run_branch(branches["B_AGE_ELSE"], else_rules, facts)
    check("ELSE_original_age_guard_not_local_scope_complement", result["admitted_actions"], [])
    facts = {"hospital_scope": False, "marker_A": True}
    result = module.run_branch(branches["B_AGE_ELSE"], else_rules, facts)
    check("ELSE_unknown_source_age_still_deferred", result["admitted_actions"], [])
    malformed_else = copy.deepcopy(branches["B_AGE_ELSE"])
    malformed_else.pop("else_guard")
    reject("ELSE_missing_source_guard_rejected", lambda: module.run_branch(malformed_else, rules, {"patient.age_years_at_index": 40, "marker_A": True}))
    uncovered = copy.deepcopy(branches["B_AGE_GAP"])
    uncovered["cardinality"] = "exactly_one"
    uncovered["coverage_status"] = "reviewed_exhaustive_fixture"
    check("COVERAGE_declared_exactly_one_gap", module.route(uncovered, {"patient.age_years_at_index": 40}, rules)["status"], "COVERAGE_CONFLICT")

    # Contradictions are keyed to the actual action target; different disease
    # statements are not considered globally mutually exclusive.
    conflict = module.run_branch(branches["B_ACTION_CONFLICT"], rules, {"guard_A": True, "guard_B": True, "marker_A": True, "marker_B": True})
    check("CONFLICT_opposing_same_target_blocked", [conflict["status"], conflict["admitted_actions"]], ["ACTION_CONFLICT", []])
    independent = copy.deepcopy(rules)
    independent[branches["B_ACTION_CONFLICT"]["branches"][1]["rule_ref"]]["target"]["id"] = "INDEPENDENT_DISEASE"
    coexist = module.run_branch(branches["B_ACTION_CONFLICT"], independent, {"guard_A": True, "guard_B": True, "marker_A": True, "marker_B": True})
    check("CONFLICT_distinct_targets_preserved", [coexist["status"], len(coexist["admitted_actions"])], ["NO_ACTION_CONFLICT", 2])
    for key in ("G", "C"):
        facts = {"G": True, "C": True}
        facts[key] = {"value": True, "conflict": True}
        result = module.evaluate_rule(rules["S_GUARDED_SUFFICIENT"], facts)
        check(f"CONFLICT_relevant_fact_{key}", [result["conflict"], result["action"]], [True, None])
    facts = {"G": True, "C": True, "unrelated": {"value": False, "conflict": True}}
    check("CONFLICT_unreferenced_fact_does_not_block", module.evaluate_rule(rules["S_GUARDED_SUFFICIENT"], facts)["action"], "CONFIRM")

    # Finite formula counterexamples make the scope/condition distinction clear.
    def atom(key):
        return {"op": "fact", "key": key}
    correct = {"op": "implies", "antecedent": {"op": "and", "children": [atom("G"), atom("D")]}, "consequent": atom("C")}
    wrong = {"op": "implies", "antecedent": atom("D"), "consequent": {"op": "and", "children": [atom("G"), atom("C")]}}
    facts = {"G": F, "D": T, "C": F}
    check("SCOPE_necessary_formula_counterexample", [module.truth(correct, facts), module.truth(wrong, facts)], [T, F])
    implication = {"op": "implies", "antecedent": atom("G"), "consequent": atom("C")}
    check("SCOPE_vacuity_not_a_diagnostic_action", [module.truth(implication, {"G": F, "C": F}), module.evaluate_rule(rules["S_GUARDED_SUFFICIENT"], {"G": F, "C": F})["action"]], [T, None])

    after = {name: digest(name) for name in FILES}
    check("INPUTS_stable_during_review", before, after)
    result = {
        "status": "passed" if all(row["passed"] for row in rows) else "failed",
        "reviewed_input_commit": "bbc036e8a6ec93583be915a4609fe86278ed062c",
        "checks": len(rows), "passed": sum(row["passed"] for row in rows),
        "author_vectors_separate_from_these_checks": len(json.loads((HERE / "supplemental_vectors.json").read_text())["vectors"]),
        "input_sha256": before,
        "historical_counterexamples": "review_initial_counterexamples.json",
        "clinical_use_authorized": False, "production_code_modified": False,
        "scope": "Finite independently constructed counterexamples and truth-table checks. No source fidelity, clinical efficacy, population accuracy, or general FOL proof.",
        "results": rows,
    }
    (HERE / "review_checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "checks", "passed", "author_vectors_separate_from_these_checks")}, ensure_ascii=False))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
