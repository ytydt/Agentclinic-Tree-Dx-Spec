#!/usr/bin/env python3
"""Finite synthetic contract checker; neither production engine nor clinical validator.

Only the operators and explicit policies used by supplemental_vectors.json exist
here. Missing observations remain UNKNOWN. No model, source extraction, medical
ontology, general theorem prover, actual orders, or production code is invoked.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
T, F, U = "TRUE", "FALSE", "UNKNOWN"
STAGES = {"screening", "diagnosis", "investigation", "treatment", "monitoring", "follow_up", "prevention", "rehabilitation"}
DIAGNOSTIC_EFFECTS = {"sufficient_for_target", "necessary_for_target", "sufficient_for_exclusion", "defeasible_support"}
ACTION_TYPES = {"test", "treatment", "procedure", "workflow", "referral_service"}
ALLOWED = {
    "diagnostic_inference": DIAGNOSTIC_EFFECTS,
    "recommend_action": {"recommend", "not_recommended", "prohibit", "propose_diagnosis"},
    "action_eligibility": {"eligibility_complete_definition", "eligibility_sufficient", "eligibility_necessary"},
    "inference_permission": {"not_allowed_to_exclude"},
    "evidence_description": {"record_observation"},
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def conj(values):
    return F if F in values else U if U in values else T


def disj(values):
    return T if T in values else U if U in values else F


def negate(value):
    return {T: F, F: T, U: U}[value]


def observation(facts, key):
    value = facts.get(key)
    if isinstance(value, dict):
        require(set(value) <= {"value", "conflict"} and "value" in value, "unsupported observation record")
        require(type(value.get("conflict", False)) is bool, "conflict flag must be Boolean")
        value = value["value"]
    return None if value == U else value


def has_conflict(expr, facts):
    if "key" in expr:
        supplied = facts.get(expr["key"])
        return isinstance(supplied, dict) and supplied.get("conflict") is True
    return any(has_conflict(child, facts) for child in expr.get("children", [])) or any(
        has_conflict(expr[key], facts) for key in ("child", "antecedent", "consequent") if key in expr
    )


def validate_expression(expr):
    require(isinstance(expr, dict), "expression must be object")
    require(not ({"effect", "relation", "target"} & expr.keys()), "leaf/node may not carry root effect")
    op = expr.get("op")
    if op == "const":
        require(expr.get("value") in {T, F, U}, "invalid truth constant")
    elif op == "fact":
        require(isinstance(expr.get("key"), str) and expr["key"], "fact key missing")
    elif op == "eq":
        require(isinstance(expr.get("key"), str) and "value" in expr and expr["value"] is not None, "invalid exact-state comparison")
    elif op == "compare":
        require(isinstance(expr.get("key"), str), "comparison key missing")
        require(expr.get("comparator") in {"lt", "le", "gt", "ge", "eq"}, "invalid comparator")
        require(type(expr.get("value")) in {int, float} and math.isfinite(expr["value"]), "threshold must be finite numeric")
    elif op in {"and", "or"}:
        require(isinstance(expr.get("children"), list) and expr["children"], "empty source conjunction/disjunction rejected")
        for child in expr["children"]:
            validate_expression(child)
    elif op == "not":
        validate_expression(expr.get("child"))
    elif op == "implies":
        validate_expression(expr.get("antecedent"))
        validate_expression(expr.get("consequent"))
    else:
        raise ValueError(f"unsupported expression operator: {op}")


def truth(expr, facts):
    """K3 over supplied finite facts; equality never treats missing as negative."""
    op = expr["op"]
    if op == "const":
        return expr["value"]
    if op == "fact":
        value = observation(facts, expr["key"])
        if value is None:
            return U
        require(type(value) is bool or isinstance(value, str) and value in {T, F, U}, "Boolean fact has wrong type")
        return T if value is True or value == T else F if value is False or value == F else U
    if op == "eq":
        value = observation(facts, expr["key"])
        if value is None:
            return U
        require(type(value) is type(expr["value"]), "exact-state observation type mismatch")
        return T if value == expr["value"] else F
    if op == "compare":
        value = observation(facts, expr["key"])
        if value is None:
            return U
        require(type(value) in {int, float} and math.isfinite(value), "observation must be finite numeric")
        other = expr["value"]
        result = {"lt": value < other, "le": value <= other, "gt": value > other, "ge": value >= other, "eq": value == other}[expr["comparator"]]
        return T if result else F
    if op in {"and", "or"}:
        values = [truth(child, facts) for child in expr["children"]]
        return conj(values) if op == "and" else disj(values)
    if op == "not":
        return negate(truth(expr["child"], facts))
    if op == "implies":
        return disj([negate(truth(expr["antecedent"], facts)), truth(expr["consequent"], facts)])
    raise ValueError("unsupported expression")


def validate_rule(rule):
    for key in ("rule_id", "care_process_stages", "semantic_intent", "target", "effect", "applicability", "condition", "disease_context", "disease_context_status", "classification_status", "provenance", "clinical_use_authorized"):
        require(key in rule, f"missing field {key}")
    require(rule["clinical_use_authorized"] is False, "fixtures cannot authorize clinical use")
    require(rule["provenance"].get("source_kind") == "synthetic", "fixture source must be synthetic")
    require(rule["provenance"].get("scope_source_status") in {"complete_fixture", "unresolved"}, "scope source status missing")
    require(rule["care_process_stages"] and set(rule["care_process_stages"]) <= STAGES, "unknown or empty care stage")
    require(rule["classification_status"] in {"reviewed_fixture", "unresolved"}, "invalid classification status")
    intent, effect, target = rule["semantic_intent"], rule["effect"]["kind"], rule["target"]
    require(intent in ALLOWED and effect in ALLOWED[intent], "intent/effect mismatch")
    require(type(rule["effect"].get("fixture_effect_authorized")) is bool, "effect authority must be Boolean")
    require(target.get("type") and target.get("id"), "target unresolved")
    if intent == "diagnostic_inference":
        require(target["type"] == "disease", "diagnostic effect needs disease target")
    elif effect == "propose_diagnosis":
        require(target["type"] == "disease", "proposed diagnosis needs disease target")
    elif intent == "inference_permission":
        require(target["type"] == "inference_action", "permission needs inference target")
    elif intent == "evidence_description":
        require(target["type"] == "observation", "description needs observation target")
    else:
        require(target["type"] in ACTION_TYPES, "workflow action has invalid target type")
    if effect == "eligibility_complete_definition":
        require(rule["effect"].get("complete_eligibility_basis_source_authorized") is True, "eligibility equivalence needs complete source basis")
    if rule["disease_context_status"] == "not_mentioned":
        require(rule["disease_context"] == [], "not-mentioned disease context must be empty")
    else:
        require(rule["disease_context_status"] in {"resolved", "unresolved"}, "invalid disease context status")
    validate_expression(rule["applicability"])
    validate_expression(rule["condition"])


def evaluate_rule(rule, facts):
    validate_rule(rule)
    scope = truth(rule["applicability"], facts)
    result = {"status": None, "scope": scope, "condition": "NOT_EVALUATED", "channel": "none", "action": None, "conflict": False}
    if rule["classification_status"] != "reviewed_fixture":
        return dict(result, status="QUARANTINED_CLASSIFICATION")
    if rule["provenance"]["scope_source_status"] != "complete_fixture":
        return dict(result, status="QUARANTINED_SOURCE_SCOPE")
    if has_conflict(rule["applicability"], facts):
        return dict(result, status="DEFER_SCOPE_CONFLICT", conflict=True)
    if scope == F:
        return dict(result, status="NOT_APPLICABLE")
    if scope == U:
        return dict(result, status="DEFER_SCOPE")
    condition = truth(rule["condition"], facts)
    result["condition"] = condition
    if has_conflict(rule["condition"], facts):
        return dict(result, status="DEFER_EVIDENCE_CONFLICT", conflict=True)
    if condition == U:
        return dict(result, status="NEEDS_EVIDENCE")
    effect = rule["effect"]["kind"]
    if rule["semantic_intent"] == "diagnostic_inference":
        action = None
        if effect == "necessary_for_target" and condition == F:
            action = "EXCLUDE"
        elif effect == "sufficient_for_target" and condition == T:
            action = "CONFIRM"
        elif effect == "sufficient_for_exclusion" and condition == T:
            action = "EXCLUDE"
        elif effect == "defeasible_support" and condition == T:
            action = "SOFT_SUPPORT"
        if action:
            if not rule["effect"].get("fixture_effect_authorized", False):
                return dict(result, status="UNAUTHORIZED_EFFECT")
            return dict(result, status="FIRED", channel="diagnostic", action=action)
        return dict(result, status="NOT_TRIGGERED")
    if not rule["effect"].get("fixture_effect_authorized", False):
        return dict(result, status="UNAUTHORIZED_EFFECT")
    if effect == "eligibility_complete_definition":
        return dict(result, status="DECIDED", channel="workflow", action="ELIGIBLE" if condition == T else "NOT_ELIGIBLE")
    if effect == "eligibility_sufficient":
        return dict(result, status="DECIDED", channel="workflow", action="ELIGIBLE") if condition == T else dict(result, status="NOT_TRIGGERED")
    if effect == "eligibility_necessary":
        return dict(result, status="DECIDED", channel="workflow", action="NOT_ELIGIBLE") if condition == F else dict(result, status="NOT_TRIGGERED")
    if condition == F:
        return dict(result, status="NOT_TRIGGERED")
    if effect == "not_allowed_to_exclude":
        return dict(result, status="FIRED", channel="permission", action="LIMIT_EXCLUSION_METHOD")
    if effect == "record_observation":
        return dict(result, status="FIRED", channel="observation", action="RECORD_SUPPLIED_OBSERVATION")
    action = {"recommend": "PROPOSE", "not_recommended": "NOT_RECOMMENDED", "prohibit": "PROHIBIT", "propose_diagnosis": "PROPOSE_DIAGNOSIS"}[effect]
    return dict(result, status="FIRED", channel="workflow", action=action)


def validate_branch_set(branch_set, rules):
    require(branch_set.get("clinical_use_authorized") is False, "branch fixture cannot authorize clinical use")
    require(branch_set.get("policy") in {"exclusive", "all_applicable", "source_priority"}, "unsupported branch policy")
    require(branch_set.get("classification_status") in {"reviewed_fixture", "unresolved"}, "branch classification status missing")
    require(type(branch_set.get("source_structure_complete")) is bool, "branch source completeness missing")
    require(branch_set.get("cardinality") in {"at_most_one", "exactly_one", "any_number"}, "branch cardinality missing")
    require((branch_set["cardinality"] == "any_number") == (branch_set["policy"] == "all_applicable"), "branch cardinality/policy mismatch")
    if branch_set["cardinality"] == "exactly_one":
        require(branch_set.get("coverage_status") == "reviewed_exhaustive_fixture", "exactly-one policy needs reviewed exhaustive coverage")
    validate_expression(branch_set["parent_scope"])
    ids = []
    for branch in branch_set["branches"]:
        ids.append(branch["branch_id"])
        validate_expression(branch["guard"])
        require(branch["rule_ref"] in rules, "unresolved branch rule reference")
        require(branch.get("guard_review_status") in {"reviewed_fixture", "unresolved"}, "branch guard review missing")
    require(len(ids) == len(set(ids)) and ids, "invalid branch identities")
    if branch_set.get("else_rule_ref"):
        require(branch_set["else_rule_ref"] in rules, "unresolved else rule")
        require(branch_set["policy"] == "exclusive", "fixture else only supports explicit exclusive selection")
        require(branch_set.get("else_source_authorized") is True, "else not source-authorized")
        require(branch_set.get("coverage_status") == "reviewed_exhaustive_fixture", "else coverage unresolved")
        require(branch_set.get("else_guard_review_status") in {"reviewed_fixture", "unresolved"}, "else guard review missing")
        validate_expression(branch_set.get("else_guard"))
    if branch_set["policy"] == "source_priority":
        require(branch_set.get("priority_source_authorized") is True, "priority not source-authorized")
        order = branch_set.get("source_declared_order", [])
        require(len(order) == len(ids) and set(order) == set(ids), "source-declared priority order missing")
        domain = branch_set.get("override_domain", {})
        require(domain.get("effect_family") == "diagnostic_decision", "unsupported override domain")
        for branch in branch_set["branches"]:
            rule = rules[branch["rule_ref"]]
            require(rule["target"] == {"type": domain.get("target_type"), "id": domain.get("target_id")}, "priority target outside override domain")
            require(rule["semantic_intent"] == "diagnostic_inference", "priority effect outside override domain")


def route(branch_set, facts, rules):
    """Route on complete effective scopes, retaining unknowns and source gates.

    Source review/coverage is stipulated fixture metadata, not inferred here.
    """
    validate_branch_set(branch_set, rules)
    parent = truth(branch_set["parent_scope"], facts)
    result = {"status": None, "selected": [], "pending": [], "parent_scope": parent}
    if branch_set["classification_status"] != "reviewed_fixture" or not branch_set["source_structure_complete"] or any(b["guard_review_status"] != "reviewed_fixture" for b in branch_set["branches"]):
        return dict(result, status="QUARANTINED_BRANCH")
    for branch in branch_set["branches"]:
        root = rules[branch["rule_ref"]]
        validate_rule(root)
        if root["classification_status"] != "reviewed_fixture" or root["provenance"]["scope_source_status"] != "complete_fixture":
            return dict(result, status="QUARANTINED_BRANCH")
    if branch_set.get("else_rule_ref"):
        root = rules[branch_set["else_rule_ref"]]
        validate_rule(root)
        if branch_set["else_guard_review_status"] != "reviewed_fixture" or root["classification_status"] != "reviewed_fixture" or root["provenance"]["scope_source_status"] != "complete_fixture":
            return dict(result, status="QUARANTINED_BRANCH")
    if has_conflict(branch_set["parent_scope"], facts):
        return dict(result, status="DEFER_SCOPE_CONFLICT")
    if parent != T:
        return dict(result, status="NOT_APPLICABLE" if parent == F else "DEFER_SCOPE")
    effective = [(b, {"op": "and", "children": [branch_set["parent_scope"], b["guard"], rules[b["rule_ref"]]["applicability"]]}) for b in branch_set["branches"]]
    if branch_set.get("else_rule_ref"):
        effective.append(({"branch_id": "ELSE", "rule_ref": branch_set["else_rule_ref"]}, {"op": "and", "children": [branch_set["parent_scope"], branch_set["else_guard"], rules[branch_set["else_rule_ref"]]["applicability"]]}))
    states = [(b, truth(expr, facts)) for b, expr in effective]
    if any(has_conflict(expr, facts) for _, expr in effective):
        return dict(result, status="DEFER_BRANCH_CONFLICT")
    selected = [b["branch_id"] for b, value in states if value == T]
    pending = [b["branch_id"] for b, value in states if value == U]
    result["pending"] = pending
    policy = branch_set["policy"]
    if policy == "source_priority":
        by_id = {branch["branch_id"]: (branch, value) for branch, value in states}
        for branch, value in [by_id[key] for key in branch_set["source_declared_order"]]:
            if value == U:
                return dict(result, status="DEFER_PRIORITY")
            if value == T:
                return dict(result, status="SELECTED", selected=[branch["branch_id"]])
    elif policy == "exclusive":
        if len(selected) > 1:
            return dict(result, status="BRANCH_CONFLICT")
        if pending:
            return dict(result, status="DEFER_BRANCH")
        if selected:
            return dict(result, status="SELECTED_ELSE" if selected == ["ELSE"] else "SELECTED", selected=selected)
    else:
        if selected or pending:
            return dict(result, status="PARTIAL" if pending else "SELECTED", selected=selected)
    if branch_set["cardinality"] == "exactly_one" and branch_set.get("coverage_status") == "reviewed_exhaustive_fixture":
        return dict(result, status="COVERAGE_CONFLICT")
    return dict(result, status="NO_APPLICABLE_BRANCH")


def run_branch(branch_set, rules, facts):
    routed = route(branch_set, facts, rules)
    executions = {}
    proposals = []
    for branch_id in routed["selected"]:
        if branch_id == "ELSE":
            ref = branch_set["else_rule_ref"]
            guard = branch_set["else_guard"]
        else:
            branch = next(b for b in branch_set["branches"] if b["branch_id"] == branch_id)
            ref, guard = branch["rule_ref"], branch["guard"]
        rule = copy.deepcopy(rules[ref])
        rule["applicability"] = {"op": "and", "children": [branch_set["parent_scope"], guard, rule["applicability"]]}
        executions[branch_id] = evaluate_rule(rule, facts)
        if executions[branch_id]["action"]:
            proposals.append({"branch_id": branch_id, "target": rule["target"], "channel": executions[branch_id]["channel"], "action": executions[branch_id]["action"]})
    conflicts, blocked = [], set()
    opposites = [{"CONFIRM", "EXCLUDE"}, {"PROPOSE", "PROHIBIT"}, {"ELIGIBLE", "NOT_ELIGIBLE"}]
    for i, left in enumerate(proposals):
        for j, right in enumerate(proposals[i+1:], i+1):
            if left["target"] == right["target"] and left["channel"] == right["channel"] and {left["action"], right["action"]} in opposites:
                conflicts.append({"target": left["target"], "branches": [left["branch_id"], right["branch_id"]], "actions": [left["action"], right["action"]]})
                blocked.update([i, j])
    return {"route": routed, "executions": executions, "status": "ACTION_CONFLICT" if conflicts else "NO_ACTION_CONFLICT", "conflicts": conflicts, "admitted_actions": [p for i,p in enumerate(proposals) if i not in blocked]}


def patch_copy(obj, changes):
    obj = copy.deepcopy(obj)
    for path, value in changes.items():
        keys = path.split(".")
        cursor = obj
        for key in keys[:-1]:
            cursor = cursor[key]
        if value == "__DELETE__":
            del cursor[keys[-1]]
        else:
            cursor[keys[-1]] = value
    return obj


def check_expected(actual, expected, path="result"):
    if isinstance(expected, dict):
        require(isinstance(actual, dict), f"{path}: expected object")
        for key, value in expected.items():
            require(key in actual, f"{path}: missing {key}")
            check_expected(actual[key], value, f"{path}.{key}")
    else:
        require(actual == expected, f"{path}: {actual!r} != {expected!r}")


def main():
    examples = json.loads((HERE / "supplemental_examples.json").read_text())
    vectors = json.loads((HERE / "supplemental_vectors.json").read_text())["vectors"]
    require(examples["logic_profile_id"] == "strong_kleene_3_stage_scope_fixture_v1", "wrong fixture profile")
    rules = {r["rule_id"]: r for r in examples["rules"]}
    branches = {b["branch_set_id"]: b for b in examples["branch_sets"]}
    require(len(rules) == len(examples["rules"]), "duplicate rule identity")
    require(len(branches) == len(examples["branch_sets"]), "duplicate branch identity")
    for rule in rules.values():
        validate_rule(rule)
    for branch_set in branches.values():
        validate_branch_set(branch_set, rules)
    require(len({v["vector_id"] for v in vectors}) == len(vectors), "duplicate vector id")
    rows = []
    for vector in vectors:
        kind = vector["kind"]
        if kind == "rule":
            actual = evaluate_rule(patch_copy(rules[vector["rule_id"]], vector.get("patch", {})), vector["facts"])
        elif kind == "branch":
            actual = route(patch_copy(branches[vector["branch_set_id"]], vector.get("patch", {})), vector["facts"], rules)
        elif kind == "branch_run":
            actual = run_branch(patch_copy(branches[vector["branch_set_id"]], vector.get("patch", {})), rules, vector["facts"])
        elif kind == "expression":
            validate_expression(vector["expression"])
            actual = {"truth": truth(vector["expression"], vector["facts"])}
        elif kind in {"reject_rule", "reject_branch", "reject_branch_run"}:
            try:
                if kind == "reject_rule":
                    validate_rule(patch_copy(rules[vector["rule_id"]], vector["patch"]))
                elif kind == "reject_branch":
                    validate_branch_set(patch_copy(branches[vector["branch_set_id"]], vector["patch"]), rules)
                else:
                    run_branch(patch_copy(branches[vector["branch_set_id"]], vector["patch"]), rules, vector["facts"])
            except ValueError as exc:
                actual = {"rejected": True, "reason": str(exc)}
            else:
                actual = {"rejected": False}
        else:
            raise ValueError(f"unknown vector kind {kind}")
        check_expected(actual, vector["expected"], vector["vector_id"])
        rows.append({"vector_id": vector["vector_id"], "category": vector["category"], "passed": True, "actual": actual})
    report = {
        "status": "passed", "logic_profile_id": examples["logic_profile_id"],
        "rules": len(rules), "branch_sets": len(branches), "vectors": len(rows),
        "clinical_use_authorized": False, "production_code_modified": False,
        "validation_limit": "Finite synthetic shape/typing/three-valued execution checks only; not general FOL/source fidelity/medical efficacy validation.",
        "file_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ("supplemental_examples.json", "supplemental_vectors.json", "validate_supplement.py", "SEMANTIC_SUPPLEMENT.md")},
        "results": rows,
    }
    (HERE / "supplement_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "rules", "branch_sets", "vectors", "clinical_use_authorized")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
