"""Compose MCQ options with scoped L2 leaves and annotate like L2 competition."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from agentclinic_tree_dx.l1_evidence_bfs import assert_no_gold_leak
from agentclinic_tree_dx.updater import ordinal_update

ELIGIBLE_QUESTION_TARGETS = frozenset({
    "etiology_pathogen",
    "finding",
    "mechanism",
})
EFFECTS = frozenset({
    "strong_for", "moderate_for", "weak_for", "neutral",
    "weak_against", "moderate_against", "strong_against",
})
COMPOSITE_SEP = "::"


@dataclass
class SyntheticBranch:
    id: str
    label: str
    parent: str
    prior: float
    posterior: float


class L2ParentLookup:
    def __init__(self, l2_rows: Sequence[Mapping[str, Any]]) -> None:
        self.branches = {
            str(row["leaf_id"]): SimpleNamespace(
                id=str(row["leaf_id"]),
                label=str(row["leaf_label"]),
            )
            for row in l2_rows
        }


def composite_candidate_id(l2_id: str, letter: str) -> str:
    return "%s%s%s" % (str(l2_id), COMPOSITE_SEP, str(letter).upper())


def parse_composite_candidate_id(candidate_id: str) -> tuple[str, str]:
    l2_id, letter = str(candidate_id).rsplit(COMPOSITE_SEP, 1)
    return l2_id, letter.upper()


def format_composite_label(
    question_target: str,
    option_text: str,
    l2_label: str,
) -> str:
    option_text = str(option_text).strip()
    l2_label = str(l2_label).strip()
    if question_target == "etiology_pathogen":
        return "%s — etiologic agent of %s" % (option_text, l2_label)
    if question_target == "mechanism":
        return "%s — mechanism/pathway of %s" % (option_text, l2_label)
    if question_target == "finding":
        return "%s — manifestation consistent with %s" % (option_text, l2_label)
    return "%s — paired with %s" % (option_text, l2_label)


def l2_shortlist(
    leaves: Sequence[Mapping[str, Any]],
    ranking: Sequence[str] = (),
    *,
    max_l2: int = 8,
) -> list[dict[str, Any]]:
    leaf_by_id = {str(row["leaf_id"]): dict(row) for row in leaves}
    ordered_ids = [str(value) for value in ranking if str(value) in leaf_by_id]
    if not ordered_ids:
        ordered_ids = sorted(
            leaf_by_id,
            key=lambda leaf_id: (
                leaf_by_id[leaf_id].get("joint_rank") is None,
                leaf_by_id[leaf_id].get("joint_rank") or 10**9,
                -float(leaf_by_id[leaf_id].get("posterior") or 0.0),
                leaf_id,
            ),
        )
    output: list[dict[str, Any]] = []
    for leaf_id in ordered_ids:
        output.append(leaf_by_id[leaf_id])
        if len(output) >= max_l2:
            break
    return output


def _l2_masses(
    l2_rows: Sequence[Mapping[str, Any]],
    *,
    use_l2_mass: bool,
) -> dict[str, float]:
    if not use_l2_mass:
        return {str(row["leaf_id"]): 1.0 for row in l2_rows}
    raw = {
        str(row["leaf_id"]): max(float(row.get("posterior") or 0.0), 0.0)
        for row in l2_rows
    }
    if sum(raw.values()) <= 1e-12:
        raw = {
            str(row["leaf_id"]): 1.0 / max(int(row.get("joint_rank") or 999), 1)
            for row in l2_rows
        }
    return raw


def rescale_l3_scope(
    l2_rows: Sequence[Mapping[str, Any]],
    options: Mapping[str, str],
    question_target: str,
    *,
    use_l2_mass: bool = True,
) -> dict[str, SyntheticBranch]:
    letters = sorted(str(letter).upper() for letter in options)
    if not l2_rows or not letters:
        return {}
    masses = _l2_masses(l2_rows, use_l2_mass=use_l2_mass)
    total = sum(masses.values()) or 1.0
    branches: dict[str, SyntheticBranch] = {}
    for row in l2_rows:
        l2_id = str(row["leaf_id"])
        l2_mass = masses[l2_id] / total
        per_option = l2_mass / len(letters)
        for letter in letters:
            candidate_id = composite_candidate_id(l2_id, letter)
            branches[candidate_id] = SyntheticBranch(
                id=candidate_id,
                label=format_composite_label(
                    question_target,
                    options[letter],
                    str(row["leaf_label"]),
                ),
                parent=l2_id,
                prior=per_option,
                posterior=per_option,
            )
    return branches


def composite_candidate_rows(
    branches: Mapping[str, SyntheticBranch],
    l2_by_id: Mapping[str, Mapping[str, Any]],
    options: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for branch in branches.values():
        l2_id = str(branch.parent)
        _, letter = parse_composite_candidate_id(branch.id)
        rows.append({
            "id": branch.id,
            "label": branch.label,
            "parent_id": l2_id,
            "parent_label": str(l2_by_id[l2_id]["leaf_label"]),
            "prior": float(branch.posterior),
            "option_letter": letter,
            "option_text": str(options[letter]),
        })
    return sorted(rows, key=lambda row: (row["parent_id"], row["option_letter"]))


def clean_l3_annotation(
    response: Mapping[str, Any],
    selected_fact_ids: Sequence[str],
    candidate_ids: Sequence[str],
) -> dict[str, Any]:
    raw = response.get("per_fact_effects") or {}
    rejected: list[str] = []
    expected_facts = set(selected_fact_ids)
    expected_candidates = set(candidate_ids)
    if set(raw) != expected_facts:
        rejected.append("incomplete_fact_matrix")
    cleaned: dict[str, dict[str, str]] = {}
    for fact_id in selected_fact_ids:
        effects = raw.get(fact_id)
        if not isinstance(effects, Mapping):
            rejected.append("%s:not_object" % fact_id)
            continue
        if set(effects) != expected_candidates:
            rejected.append("%s:incomplete_candidate_matrix" % fact_id)
            continue
        invalid = [
            branch_id for branch_id, effect in effects.items()
            if str(effect) not in EFFECTS
        ]
        if invalid:
            rejected.append("%s:invalid_effects" % fact_id)
            continue
        cleaned[fact_id] = {
            str(branch_id): str(effect) for branch_id, effect in effects.items()
        }
    return {
        "schema_valid": not rejected and len(cleaned) == len(expected_facts),
        "per_fact_effects": cleaned,
        "fact_rationales": dict(response.get("fact_rationales") or {}),
        "rejected": rejected,
        "raw": dict(response),
    }


def apply_l3_annotation(
    branches: Mapping[str, SyntheticBranch],
    selected_facts: Sequence[Mapping[str, Any]],
    per_fact_effects: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    updated = {
        key: copy.deepcopy(value) for key, value in branches.items()
    }
    for fact in selected_facts:
        fact_id = str(fact["id"])
        posteriors = ordinal_update(
            updated,
            {"branch_effects": per_fact_effects[fact_id]},
            gate=True,
        )
        for branch_id, posterior in posteriors.items():
            updated[branch_id].prior = updated[branch_id].posterior
            updated[branch_id].posterior = posterior
    posterior_rows = sorted(
        (
            {
                "id": branch.id,
                "label": branch.label,
                "parent_id": branch.parent,
                "posterior": float(branch.posterior),
            }
            for branch in updated.values()
        ),
        key=lambda row: (-row["posterior"], row["id"]),
    )
    return posterior_rows


def aggregate_option_ranking(
    posterior_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    best: dict[str, float] = {}
    for row in posterior_rows:
        _, letter = parse_composite_candidate_id(str(row["id"]))
        best[letter] = max(best.get(letter, 0.0), float(row["posterior"]))
    ordered = sorted(best.items(), key=lambda item: (-item[1], item[0]))
    ranks = {letter: index for index, (letter, _) in enumerate(ordered, start=1)}
    return {
        "option_scores": best,
        "option_order": [letter for letter, _ in ordered],
        "option_ranks": ranks,
    }


def score_option_prediction(
    option_ranks: Mapping[str, int],
    gold_letter: str,
    *,
    n_options: int,
) -> dict[str, Any]:
    fallback = int(n_options) + 1
    if not option_ranks:
        rank = fallback
    else:
        rank = int(option_ranks.get(str(gold_letter).upper(), fallback))
    return {
        "gold_letter": str(gold_letter).upper(),
        "gold_option_rank": rank,
        "option_top1": rank <= 1,
        "option_top2": rank <= 2,
        "option_rr": 1.0 / rank if rank <= n_options else 0.0,
    }


def annotate_l3_scope(
    *,
    cache: Any,
    module: str,
    prompt: str,
    vignette: str,
    question: str,
    question_target: str,
    findings: Sequence[Mapping[str, Any]],
    selected_facts: Sequence[Mapping[str, Any]],
    branches: Mapping[str, SyntheticBranch],
    l2_by_id: Mapping[str, Mapping[str, Any]],
    options: Mapping[str, str],
) -> dict[str, Any]:
    candidates = composite_candidate_rows(branches, l2_by_id, options)
    payload = {
        "vignette": vignette,
        "question": question,
        "question_target": question_target,
        "available_findings": list(findings),
        "selected_evidence": list(selected_facts),
        "candidates": candidates,
    }
    assert_no_gold_leak(payload)
    response = cache.call(module, prompt, payload)
    cleaned = clean_l3_annotation(
        response,
        [str(row["id"]) for row in selected_facts],
        [str(row["id"]) for row in candidates],
    )
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return every selected fact and every candidate exactly once "
                "using only the allowed effect labels."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call("%sRepair" % module, prompt, repair_payload)
        cleaned = clean_l3_annotation(
            repaired,
            [str(row["id"]) for row in selected_facts],
            [str(row["id"]) for row in candidates],
        )
        repair_used = True
    if not cleaned["schema_valid"]:
        return {
            **cleaned,
            "repair_used": repair_used,
            "ranking": [],
            "posteriors": [],
            "candidates": candidates,
            "option_projection": aggregate_option_ranking([]),
        }
    posteriors = apply_l3_annotation(
        branches,
        selected_facts,
        cleaned["per_fact_effects"],
    )
    return {
        **cleaned,
        "repair_used": repair_used,
        "ranking": [str(row["id"]) for row in posteriors],
        "posteriors": posteriors,
        "candidates": candidates,
        "option_projection": aggregate_option_ranking(posteriors),
    }


def clean_option_champion_ranking(
    response: Mapping[str, Any],
    champion_letters: Sequence[str],
) -> dict[str, Any]:
    ranked = response.get("ranked_candidate_ids") or ()
    if isinstance(ranked, str):
        ranked = [ranked]
    ranked = [str(value).upper() for value in ranked]
    valid = (
        len(ranked) == len(champion_letters)
        and len(set(ranked)) == len(ranked)
        and set(ranked) == {str(value).upper() for value in champion_letters}
    )
    return {
        "schema_valid": valid,
        "ranking": ranked if valid else [],
        "why": dict(response.get("why") or {}),
        "raw": dict(response),
        "rejected": [] if valid else ["incomplete_champion_ranking"],
    }


def arbitrate_option_champions(
    *,
    cache: Any,
    module: str,
    prompt: str,
    vignette: str,
    question: str,
    question_target: str,
    findings: Sequence[Mapping[str, Any]],
    selected_facts: Sequence[Mapping[str, Any]],
    champions: Sequence[Mapping[str, Any]],
    include_l2_prior: bool,
) -> dict[str, Any]:
    rows = []
    for champion in champions:
        row = dict(champion)
        if not include_l2_prior:
            row.pop("l2_posterior", None)
        rows.append(row)
    payload = {
        "vignette": vignette,
        "question": question,
        "question_target": question_target,
        "available_findings": list(findings),
        "selected_evidence": list(selected_facts),
        "champions": rows,
    }
    assert_no_gold_leak(payload)
    response = cache.call(module, prompt, payload)
    letters = [str(row["option_letter"]) for row in champions]
    cleaned = clean_option_champion_ranking(response, letters)
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return every champion option letter exactly once, best first."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call("%sRepair" % module, prompt, repair_payload)
        cleaned = clean_option_champion_ranking(repaired, letters)
        repair_used = True
    if not cleaned["schema_valid"]:
        return {
            **cleaned,
            "repair_used": repair_used,
            "option_projection": aggregate_option_ranking([]),
        }
    ranks = {
        letter: index for index, letter in enumerate(cleaned["ranking"], start=1)
    }
    return {
        **cleaned,
        "repair_used": repair_used,
        "option_projection": {
            "option_scores": {
                letter: 1.0 / ranks[letter] for letter in cleaned["ranking"]
            },
            "option_order": list(cleaned["ranking"]),
            "option_ranks": ranks,
        },
    }
