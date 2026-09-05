"""Audit-only finite logical oracle; no clinical matcher, model call, or ranking.

Run: python reference_semantics.py
Writes deterministic reference_semantics_results.json next to this script.
UNKNOWN facts share one Boolean variable wherever referenced. INCONSISTENT
facts are quarantined; they are never interpreted as FALSE or by explosion.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

TRUE, FALSE, UNKNOWN, INCONSISTENT = "true", "false", "unknown", "inconsistent"
STATES = {TRUE, FALSE, UNKNOWN, INCONSISTENT}


def lit(name: str, polarity: bool = True) -> dict:
    return {"op": "literal", "fact": name, "polarity": polarity}


def group(op: str, *members: dict, n: int | None = None) -> dict:
    result = {"op": op, "members": list(members)}
    if n is not None:
        result["n"] = n
    return result


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate(expr: dict) -> None:
    op = expr.get("op")
    if op == "literal":
        if set(expr) != {"op", "fact", "polarity"}:
            raise ValueError("Literal requires explicit fact identity and signed polarity")
        if not isinstance(expr["fact"], str) or not expr["fact"] or type(expr["polarity"]) is not bool:
            raise ValueError("Invalid signed literal")
        return
    if op not in {"all", "any", "at_least"}:
        raise ValueError("Unsupported logical operator; scores are not logical ASTs")
    expected = {"op", "members", "n"} if op == "at_least" else {"op", "members"}
    if set(expr) != expected or not isinstance(expr["members"], list) or not expr["members"]:
        raise ValueError("A logical group needs nonempty members and no ignored fields")
    for member in expr["members"]:
        validate(member)
    if op == "at_least":
        if type(expr["n"]) is not int or not 1 <= expr["n"] <= len(expr["members"]):
            raise ValueError("Invalid cardinality threshold")
        # Count clinically distinct criterion units. A duplicated extraction is
        # not another criterion; equivalence beyond identical ASTs is human work.
        if len({canonical(x) for x in expr["members"]}) != len(expr["members"]):
            raise ValueError("Duplicate counting unit in a cardinality group")


def leaves(expr: dict) -> set[str]:
    if expr["op"] == "literal":
        return {expr["fact"]}
    return set().union(*(leaves(x) for x in expr["members"]))


def evaluate_world(expr: dict, world: dict[str, bool]) -> bool:
    if expr["op"] == "literal":
        return world[expr["fact"]] == expr["polarity"]
    values = [evaluate_world(x, world) for x in expr["members"]]
    if expr["op"] == "all":
        return all(values)
    if expr["op"] == "any":
        return any(values)
    return sum(values) >= expr["n"]


def assignments(expr: dict, facts: dict[str, str]) -> list[dict[str, bool]] | None:
    names = sorted(leaves(expr))
    states = {name: facts.get(name, UNKNOWN) for name in names}
    if not all(state in STATES for state in states.values()):
        raise ValueError("Unsupported observation state")
    if INCONSISTENT in states.values():
        return None
    unknown = [name for name in names if states[name] == UNKNOWN]
    if len(unknown) > 16:
        raise ValueError("Audit oracle supports at most 16 unknown facts")
    known = {name: state == TRUE for name, state in states.items() if state != UNKNOWN}
    return [dict(known, **dict(zip(unknown, values)))
            for values in itertools.product((False, True), repeat=len(unknown))]


def evaluate(expr: dict, facts: dict[str, str]) -> str:
    validate(expr)
    worlds = assignments(expr, facts)
    if worlds is None:
        return INCONSISTENT
    values = {evaluate_world(expr, world) for world in worlds}
    return TRUE if values == {True} else FALSE if values == {False} else UNKNOWN


def count_bounds(expr: dict, facts: dict[str, str]) -> dict:
    """Marginal bounds plus exact feasible bounds, preserving shared leaves."""
    validate(expr)
    if expr["op"] != "at_least":
        raise ValueError("Count bounds require at_least")
    status = evaluate(expr, facts)
    if status == INCONSISTENT:
        return {"status": status, "marginal_bounds": None, "feasible_bounds": None}
    members = [evaluate(x, facts) for x in expr["members"]]
    lower = members.count(TRUE)
    upper = lower + members.count(UNKNOWN)
    counts = [sum(evaluate_world(x, world) for x in expr["members"])
              for world in assignments(expr, facts)]
    return {"status": status, "marginal_bounds": [lower, upper],
            "feasible_bounds": [min(counts), max(counts)]}


def rule_id(rule: dict) -> str:
    """Changing source, AST, scope, relation, or certification creates a new id."""
    return "sha256:" + hashlib.sha256(canonical(rule).encode()).hexdigest()


def infer(rule: dict, facts: dict[str, str]) -> dict:
    scope = evaluate(rule["scope"], facts)
    criteria = evaluate(rule["criteria"], facts)
    result = {"scope": scope, "criteria": criteria, "conclusion": "abstain"}
    if scope != TRUE:
        result["reason"] = "scope_not_verified_true"
        return result
    if criteria in {UNKNOWN, INCONSISTENT}:
        result["reason"] = "criteria_unknown_or_inconsistent"
        return result
    relation = rule["relation"]
    if relation not in {"necessary", "sufficient", "exclusion", "support_only"}:
        raise ValueError("Unknown relation")
    required = {"necessary": "certified_D_implies_G",
                "sufficient": "certified_G_implies_D",
                "exclusion": "certified_G_implies_not_D"}
    if relation == "support_only" or not rule.get("certifications", {}).get(required[relation], False):
        result["reason"] = "no_certified_hard_implication"
        return result
    if relation == "necessary" and criteria == FALSE:
        result.update(conclusion="not_D", reason="certified_necessary_group_not_met")
    elif relation == "sufficient" and criteria == TRUE:
        result.update(conclusion="D", reason="certified_sufficient_group_met")
    elif relation == "exclusion" and criteria == TRUE:
        result.update(conclusion="not_D", reason="certified_exclusion_group_met")
    else:
        result["reason"] = "implication_has_no_consequence_in_this_state"
    return result


def make_rule(relation: str, criteria: dict, certified: bool = True) -> dict:
    return {"source": {"kind": "synthetic", "document_version": "audit-example-1",
                       "span_id": "P-Q-D", "warning": "not a clinical guideline"},
            "scope": lit("A"), "criteria": criteria, "relation": relation,
            "certifications": {"certified_D_implies_G": certified,
                               "certified_G_implies_D": certified,
                               "certified_G_implies_not_D": certified}}


def main() -> None:
    checks = []

    def check(name, actual, expected):
        assert actual == expected, (name, actual, expected)
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": True})

    P, Q, R = lit("P"), lit("Q"), lit("R")
    check("negative_literal_respects_polarity", evaluate(lit("P", False), {"P": TRUE}), FALSE)
    check("missing_is_unknown", evaluate(P, {}), UNKNOWN)
    check("missing_negative_is_unknown", evaluate(lit("P", False), {}), UNKNOWN)
    check("conflict_is_not_false", evaluate(P, {"P": INCONSISTENT}), INCONSISTENT)
    check("all_differs_from_any", [evaluate(group(op, P, Q), {"P": TRUE, "Q": FALSE})
                                  for op in ("all", "any")], [FALSE, TRUE])
    check("nested_scope_preserved", evaluate(group("all", P, group("any", Q, R)),
                                            {"P": FALSE, "Q": TRUE, "R": TRUE}), FALSE)
    check("two_of_three_unknown", count_bounds(group("at_least", P, Q, R, n=2), {"P": TRUE}),
          {"status": UNKNOWN, "marginal_bounds": [1, 3], "feasible_bounds": [1, 3]})
    check("two_of_three_true", evaluate(group("at_least", P, Q, R, n=2), {"P": TRUE, "Q": TRUE}), TRUE)
    check("two_of_three_false", evaluate(group("at_least", P, Q, R, n=2), {"P": FALSE, "Q": FALSE}), FALSE)
    shared = group("at_least", P, lit("P", False), n=2)
    check("shared_leaf_bounds_preserved", count_bounds(shared, {}),
          {"status": FALSE, "marginal_bounds": [0, 2], "feasible_bounds": [1, 1]})
    shared_nested = group("all", group("any", P, Q), group("any", P, R))
    check("shared_leaf_remains_in_both_groups", evaluate(shared_nested, {"P": TRUE, "Q": FALSE, "R": FALSE}), TRUE)
    check("excluded_middle_supervaluation", evaluate(group("any", P, lit("P", False)), {}), TRUE)
    check("contradiction_supervaluation", evaluate(group("all", P, lit("P", False)), {}), FALSE)

    truth_rows = []
    for relation in ("necessary", "sufficient", "exclusion"):
        for state in (TRUE, FALSE, UNKNOWN, INCONSISTENT):
            result = infer(make_rule(relation, P), {"A": TRUE, "P": state})
            expected = "not_D" if ((relation == "necessary" and state == FALSE) or
                                    (relation == "exclusion" and state == TRUE)) else (
                       "D" if relation == "sufficient" and state == TRUE else "abstain")
            check(f"{relation}_{state}", result["conclusion"], expected)
            truth_rows.append({"relation": relation, "G": state, **result})
    check("uncertified_not_met_does_not_exclude", infer(make_rule("necessary", P, False),
                                                      {"A": TRUE, "P": FALSE})["conclusion"], "abstain")
    check("unknown_applicability_abstains", infer(make_rule("sufficient", P), {"P": TRUE})["conclusion"], "abstain")
    check("false_applicability_abstains", infer(make_rule("exclusion", P), {"A": FALSE, "P": TRUE})["conclusion"], "abstain")
    check("negative_literal_not_direction", infer(make_rule("exclusion", lit("P", False)),
                                               {"A": TRUE, "P": FALSE})["conclusion"], "not_D")
    check("not_met_nested_necessary", infer(make_rule("necessary", group("any", P, Q)),
                                          {"A": TRUE, "P": FALSE, "Q": FALSE})["conclusion"], "not_D")
    check("partial_failure_of_or_not_exclusion", infer(make_rule("necessary", group("any", P, Q)),
                                                    {"A": TRUE, "P": FALSE, "Q": TRUE})["conclusion"], "abstain")
    check("support_hit_not_confirmation", infer(make_rule("support_only", P), {"A": TRUE, "P": TRUE})["conclusion"], "abstain")
    for name, bad in (("duplicate_counting_unit_rejected", group("at_least", P, P, n=2)),
                      ("weighted_score_not_logical_threshold", {"op": "score", "members": [P], "weights": [-1]}),
                      ("ignored_fields_rejected", {**P, "threshold": 4})):
        try:
            validate(bad)
        except ValueError:
            check(name, True, True)
        else:
            check(name, False, True)
    base = make_rule("necessary", P)
    changed = {**base, "criteria": lit("P", False)}
    check("semantic_change_changes_rule_identity", rule_id(base) != rule_id(changed), True)
    check("same_source_and_ast_stable_identity", rule_id(base), rule_id(dict(reversed(list(base.items())))))

    # Countermodels, rather than successful examples, expose invalid reversals.
    countermodels = [
        {"claimed": "G=>D therefore not_G=>not_D", "valid_premise": "G=>D",
         "world": {"G": False, "D": True}, "premise_holds": True, "claim_holds": False},
        {"claimed": "D=>G therefore G=>D", "valid_premise": "D=>G",
         "world": {"G": True, "D": False}, "premise_holds": True, "claim_holds": False},
        {"claimed": "G=>not_D therefore not_G=>not_D", "valid_premise": "G=>not_D",
         "world": {"G": False, "D": True}, "premise_holds": True, "claim_holds": False},
    ]
    for row in countermodels:
        g, d = row["world"]["G"], row["world"]["D"]
        if row["valid_premise"] == "G=>D":
            premise, claim = (not g or d), (g or not d)
        elif row["valid_premise"] == "D=>G":
            premise, claim = (not d or g), (not g or d)
        else:
            premise, claim = (not g or not d), (g or not d)
        check(row["claimed"], [premise, claim], [True, False])

    output = {"prototype": "audit-only finite logical semantics; no clinical fact matcher",
              "all_passed": True, "check_count": len(checks), "checks": checks,
              "implication_truth_rows": truth_rows, "countermodels": countermodels,
              "limits": ["Explicit conflict quarantines the whole referenced expression.",
                         "At most 16 independent unknown leaves; exhaustive world enumeration.",
                         "No source extraction, numeric observation parsing, medical validation, or diagnosis ranking.",
                         "A certification flag represents human-approved source implication, not model confidence."]}
    target = Path(__file__).with_name("reference_semantics_results.json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": True, "check_count": len(checks), "output": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
