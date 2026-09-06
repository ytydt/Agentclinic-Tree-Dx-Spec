#!/usr/bin/env python3
"""Check DESIGN fixtures only; NOT a production rule engine or FOL verifier.

The tiny finite-model evaluator checks stated examples under their supplied fact
assignments. It does not parse guidelines, verify source entailment, resolve
clinical entities, perform inference, or certify a medical decision.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALUES = {"true", "false", "unknown"}
BOOLEAN_OPS = {"literal", "atom", "and", "or", "not", "implies", "forall", "exists", "countDistinct", "numeric_compare", "temporal_compare"}
EFFECTS = {"sufficient_for_target", "necessary_for_target", "sufficient_for_exclusion", "defeasible_support", "signed_score", "not_allowed_to_exclude"}
PROFILE_ID = "strong_kleene_3_with_conflict_v1"


class ContractError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ContractError(code)


def outcome(value, conflict="none", **extra):
    return {"value": value, "conflict": conflict, **extra}


def joined_conflict(results):
    return "present" if any(r["conflict"] != "none" for r in results) else "none"


def validate_expr(node, bound=frozenset(), score_allowed=False):
    require(isinstance(node, dict), "node_not_object")
    require(not ({"relation", "target", "effect"} & node.keys()), "leaf_or_group_has_independent_effect")
    op = node.get("op")
    require(op in BOOLEAN_OPS or (op == "signed_score" and score_allowed), "unsupported_or_misplaced_operator")
    for arg in node.get("args", []):
        if isinstance(arg, str) and arg.startswith("$"):
            require(arg[1:].split(".")[0] in bound, "unbound_variable")
    if op == "literal":
        require(node.get("value") in VALUES, "invalid_truth_value")
    elif op == "atom":
        require(bool(node.get("predicate")), "missing_predicate")
    elif op in {"and", "or"}:
        require(len(node.get("children", [])) >= 2, "boolean_group_needs_two_children")
        for child in node["children"]:
            validate_expr(child, bound)
    elif op == "not":
        validate_expr(node["child"], bound)
    elif op == "implies":
        validate_expr(node["antecedent"], bound)
        validate_expr(node["consequent"], bound)
    elif op in {"forall", "exists", "countDistinct"}:
        require(bool(node.get("domain_id")), "missing_quantifier_domain")
        var = node.get("var")
        require(bool(var) and var not in bound, "missing_or_shadowed_variable")
        validate_expr(node["body"], bound | {var})
        if op == "countDistinct":
            require(bool(node.get("distinct_by")), "missing_distinct_identity")
            require(node.get("comparison") in {"at_least", "at_most", "exactly"}, "invalid_count_comparison")
            require(isinstance(node.get("threshold"), int) and node["threshold"] >= 0, "invalid_count_threshold")
    elif op == "numeric_compare":
        require(all(k in node for k in ("subject", "metric_id", "unit", "comparison", "threshold")), "incomplete_numeric_identity")
        require(node["comparison"] in {"lt", "le", "eq", "ge", "gt"}, "invalid_numeric_comparison")
    elif op == "temporal_compare":
        require(node.get("comparison") == "before_within_days", "unsupported_temporal_comparison")
        require(all(k in node for k in ("subject", "left_event", "right_event", "maximum_days")), "incomplete_temporal_identity")
    elif op == "signed_score":
        require(node.get("terms"), "empty_score")
        ids = [t["feature_id"] for t in node["terms"]]
        require(len(ids) == len(set(ids)), "duplicate_score_feature")
        for term in node["terms"]:
            require(isinstance(term["weight"], (int, float)), "non_numeric_score_weight")
            validate_expr(term["condition"], bound)


def validate_rule(rule):
    required = {"rule_id", "clinical_status", "target", "effect", "applicability", "condition", "provenance", "completeness", "authority", "semantic_context"}
    require(required <= rule.keys(), "missing_rule_field")
    require(rule["clinical_status"] == "synthetic_fixture_not_a_clinical_standard", "fixture_claims_clinical_standard")
    require(rule["authority"].get("clinical_use_authorized") is False, "fixture_authorizes_clinical_use")
    semantics = rule["semantic_context"]
    require(semantics.get("logic_profile_id") == PROFILE_ID, "unsupported_fixture_logic_profile")
    require(all(semantics.get(k) for k in ("symbol_signature_id", "background_theory_id", "domain_completeness_assumption", "observation_completeness_assumption", "conflict_policy_id")), "missing_semantic_context")
    require(rule["effect"].get("kind") in EFFECTS, "invalid_effect")
    require(bool(rule["target"].get("concept_id")), "missing_target")
    require(bool(rule["provenance"].get("anchors")), "missing_source_anchor")
    validate_expr(rule["applicability"]["condition"])
    is_score = rule["effect"]["kind"] == "signed_score"
    validate_expr(rule["condition"], score_allowed=is_score)
    require((rule["condition"]["op"] == "signed_score") == is_score, "score_effect_type_mismatch")
    c = rule["completeness"]
    require(all(k in c for k in ("source_window_complete", "criterion_members_complete", "logical_scope_resolved", "target_resolved")), "incomplete_completeness_record")
    require(set(c.get("emitted_member_ids", [])) <= set(c.get("expected_member_ids", [])), "unexpected_criterion_member")
    if c["criterion_members_complete"]:
        require(set(c.get("emitted_member_ids", [])) == set(c.get("expected_member_ids", [])), "false_member_completeness_claim")


def resolve(arg, env):
    if not isinstance(arg, str) or not arg.startswith("$"):
        return arg
    parts = arg[1:].split(".")
    value = env[parts[0]]
    if len(parts) == 1:
        return value["id"]
    for key in parts[1:]:
        value = value[key]
    return value


def combine(op, results):
    vals = [r["value"] for r in results]
    if op == "and":
        value = "false" if "false" in vals else "unknown" if "unknown" in vals else "true"
    else:
        value = "true" if "true" in vals else "unknown" if "unknown" in vals else "false"
    return outcome(value, joined_conflict(results))


def eval_expr(node, context, env=None):
    env = {} if env is None else env
    op = node["op"]
    if op == "literal":
        return outcome(node["value"])
    if op == "atom":
        args = [resolve(a, env) for a in node.get("args", [])]
        qualifiers = node.get("qualifiers", {})
        facts = [f for f in context.get("facts", []) if f["predicate"] == node["predicate"] and f.get("args", []) == args and all(f.get("qualifiers", {}).get(k) == v for k, v in qualifiers.items())]
        signs = {f["sign"] for f in facts}
        if signs == {"positive", "negative"}:
            return outcome("unknown", "present")
        return outcome("true" if signs == {"positive"} else "false" if signs == {"negative"} else "unknown")
    if op in {"and", "or"}:
        return combine(op, [eval_expr(c, context, env) for c in node["children"]])
    if op == "not":
        r = eval_expr(node["child"], context, env)
        return outcome({"true": "false", "false": "true", "unknown": "unknown"}[r["value"]], r["conflict"])
    if op == "implies":
        return eval_expr({"op": "or", "children": [{"op": "not", "child": node["antecedent"]}, node["consequent"]]}, context, env)
    if op in {"forall", "exists", "countDistinct"}:
        domain = context["domains"][node["domain_id"]]
        members = domain["members"]
        results = [eval_expr(node["body"], context, {**env, node["var"]: member}) for member in members]
        if op in {"forall", "exists"}:
            if not domain["complete"]:
                results.append(outcome("unknown"))
            return combine("and" if op == "forall" else "or", results)
        # Count criterion/category/domain-member identities, NOT evidence rows.
        # A shared observation may provide multiple independently asserted features.
        unique = {}
        for member, result in zip(members, results):
            key = member[node["distinct_by"]]
            if key in unique:
                require(unique[key] == result, "inconsistent_duplicate_member_assignment")
            unique[key] = result
        counted = list(unique.values())
        lower = sum(r["value"] == "true" for r in counted)
        upper = lower + sum(r["value"] == "unknown" for r in counted) if domain["complete"] else math.inf
        k = node["threshold"]
        cmp = node["comparison"]
        if cmp == "at_least":
            value = "true" if lower >= k else "false" if upper < k else "unknown"
        elif cmp == "at_most":
            value = "false" if lower > k else "true" if upper <= k else "unknown"
        else:
            value = "true" if lower == upper == k else "false" if k < lower or k > upper else "unknown"
        return outcome(value, joined_conflict(counted), lower=lower, upper=None if math.isinf(upper) else upper)
    if op == "numeric_compare":
        measurements = [m for m in context.get("measurements", []) if m["subject"] == node["subject"] and m["metric_id"] == node["metric_id"] and all(m.get("qualifiers", {}).get(k) == v for k, v in node.get("qualifiers", {}).items())]
        factors = {("mmHg", "kPa"): 0.133322, ("kPa", "mmHg"): 1 / 0.133322}
        converted = []
        for m in measurements:
            factor = 1 if m["unit"] == node["unit"] else factors.get((m["unit"], node["unit"]))
            if factor is not None:
                converted.append(m["value"] * factor)
        if not converted:
            return outcome("unknown")
        comparisons = {"lt": lambda a, b: a < b, "le": lambda a, b: a <= b, "eq": lambda a, b: a == b, "ge": lambda a, b: a >= b, "gt": lambda a, b: a > b}
        answers = {comparisons[node["comparison"]](v, node["threshold"]) for v in converted}
        if len(answers) > 1:
            return outcome("unknown", "present")
        return outcome("true" if True in answers else "false")
    if op == "temporal_compare":
        def times(event):
            return {x["day"] for x in context.get("events", []) if x["subject"] == node["subject"] and x["event_id"] == event}
        left, right = times(node["left_event"]), times(node["right_event"])
        if not left or not right:
            return outcome("unknown")
        answers = {0 < r - l <= node["maximum_days"] for l in left for r in right}
        return outcome("unknown", "present") if len(answers) > 1 else outcome("true" if True in answers else "false")
    if op == "signed_score":
        lower = upper = 0
        results = []
        for term in node["terms"]:
            r = eval_expr(term["condition"], context, env)
            results.append(r)
            w = term["weight"]
            if r["value"] == "true":
                lower += w
                upper += w
            elif r["value"] == "unknown":
                lower += min(0, w)
                upper += max(0, w)
        return outcome(lower if lower == upper else "unknown", joined_conflict(results), lower=lower, upper=upper)
    raise ContractError("unsupported_operator")


def eval_rule(rule, context, overrides=None):
    rule = copy.deepcopy(rule)
    for section, values in (overrides or {}).items():
        rule[section].update(values)
    # Overrides simulate missing runtime prerequisites, not production authority.
    result = eval_expr(rule["condition"], context)
    scope = eval_expr(rule["applicability"]["condition"], context)
    result = {**result, "action": "none"}
    c = rule["completeness"]
    if not all(c[k] for k in ("source_window_complete", "criterion_members_complete", "logical_scope_resolved", "target_resolved")):
        return {**result, "preview_value": result["value"], "value": "unknown", "reason": "incomplete_rule_contract"}
    if scope["value"] != "true" or scope["conflict"] != "none":
        return {**result, "reason": "scope_not_established"}
    if result["conflict"] != "none":
        return {**result, "reason": "unresolved_conflict"}
    effect = rule["effect"]["kind"]
    if effect == "not_allowed_to_exclude":
        return {**result, "action": "deny_exclusion_permission" if result["value"] == "true" else "none", "reason": "inference_policy_not_disease_truth"}
    if effect == "signed_score":
        return {**result, "action": "emit_score_interval", "reason": "score_is_not_a_diagnostic_effect"}
    proposed = "none"
    if result["value"] == "true":
        proposed = {"sufficient_for_target": "confirm", "sufficient_for_exclusion": "exclude", "defeasible_support": "bounded_support"}.get(effect, "none")
    elif result["value"] == "false" and effect == "necessary_for_target" and context.get("false_is_decisive", False):
        proposed = "exclude"
    if proposed in {"confirm", "exclude"} and not rule["authority"]["fixture_hard_effect_authorized"]:
        return {**result, "reason": "hard_effect_not_authorized"}
    # Fixture caller already resolved this permission for the CURRENT target,
    # evidence/method, action and scope. This is not a global clinical policy flag
    # and the checker does not implement that applicability-resolution layer.
    if proposed == "exclude" and context.get("exclusion_permission", "allowed") != "allowed":
        return {**result, "reason": "exclusion_permission_denied"}
    return {**result, "action": proposed, "reason": "root_semantics_only"}


def main():
    bundle = json.loads((HERE / "ir_examples.json").read_text())
    vectors = json.loads((HERE / "acceptance_vectors.json").read_text())
    require(bundle["production_ready"] is False, "fixture_claims_production_ready")
    require(bundle["logic_profile_id"] == vectors["logic_profile_id"] == PROFILE_ID, "fixture_profile_mismatch")
    rules = {r["rule_id"]: r for r in bundle["rules"]}
    require(len(rules) == len(bundle["rules"]), "duplicate_rule_id")
    for rule in rules.values():
        validate_rule(rule)
    derived_checks = 0
    for rule in rules.values():
        derivation = rule.get("derivation")
        if not derivation:
            continue
        require(derivation["parent_rule_id"] in rules, "missing_derivation_parent")
        parent = rules[derivation["parent_rule_id"]]
        require(derivation["proof_rule"] == "consequent_conjunction_elimination", "unsupported_fixture_derivation")
        require(parent["effect"]["kind"] == rule["effect"]["kind"] == "necessary_for_target", "invalid_necessary_projection")
        require(parent["condition"]["op"] == "and" and rule["condition"] in parent["condition"]["children"], "derived_condition_not_parent_conjunct")
        for field in ("target", "applicability", "provenance", "completeness", "authority", "semantic_context"):
            require(rule[field] == parent[field], "derived_rule_dropped_parent_contract")
        derived_checks += 1
    ids = [v["id"] for v in vectors["vectors"]]
    require(len(ids) == len(set(ids)), "duplicate_vector_id")
    for v in vectors["vectors"]:
        if v["mode"] == "invalid_structure":
            try:
                validate_expr(v["expression"], score_allowed=True)
            except ContractError as exc:
                require(str(exc) == v["expected_error"], f"{v['id']}: wrong rejection {exc}")
            else:
                raise ContractError(f"{v['id']}: invalid structure accepted")
            continue
        if v["mode"] == "rule":
            actual = eval_rule(rules[v["rule_id"]], v["context"], v.get("overrides"))
        else:
            validate_expr(v["expression"], score_allowed=True)
            actual = eval_expr(v["expression"], v["context"])
        for key, expected in v["expected"].items():
            require(actual.get(key) == expected, f"{v['id']} {key}: expected {expected!r}, got {actual.get(key)!r}")
    print(json.dumps({"status": "passed", "rule_examples": len(rules), "acceptance_vectors": len(ids), "logic_profile_id": PROFILE_ID, "syntactic_derived_rule_checks": derived_checks, "scope": "design schema and finite synthetic assignments only; not source fidelity, full FOL, general transformation certificates, clinical safety, or production execution"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
