#!/usr/bin/env python3
"""CoreLift M1/M2 runner for the frozen DA400+MCR400 development slices."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.ceiling_closure_online import _normalize_quotation  # noqa: E402
from analysis.mechanism_v2.common import (  # noqa: E402
    DEVELOPMENT_SLICES,
    ROOT,
    FrozenExactSynonymBridge,
    clean_vignette,
    combined_file_sha256,
    file_sha256,
    load_normalized_cases,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    assert_target_blind,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    RunManifest,
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)

EXPERIMENT_ID = "SLOT_YIELD_BREAKTHROUGH_M1_M2"
SCHEMA = "corelift_preregistration_v2"
DEFAULT_SELECTOR_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_TYPE_MODEL = "google/gemini-2.5-flash"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/SLOT_YIELD_BREAKTHROUGH"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"

STAGE_KEYS = ("ax_syndrome", "ax_mechanism", "ax_modality")
VIEW_ROLES = {
    "ax_syndrome": "syndrome_anatomy",
    "ax_mechanism": "mechanism_etiology",
    "ax_modality": "definitive_modality",
}
A0_CONTROL = "A0_control"
A1_VIEWS = "A1_views"
A2_VIEWS_TYPED = "A2_views_typed"
A3_FULL = "A3_full"
B1_CORELIFT = "B1_corelift"
ARMS = (A0_CONTROL, A1_VIEWS, A2_VIEWS_TYPED, A3_FULL, B1_CORELIFT)
TYPED_ARMS = frozenset((A2_VIEWS_TYPED, A3_FULL, B1_CORELIFT))
FULL_ARMS = frozenset((A3_FULL, B1_CORELIFT))
MAX_MAIN_POOL = 11
MODIFIER_AXES = (
    "etiology",
    "anatomy",
    "subtype_histology",
    "complication",
    "scope_distribution",
    "temporal_evolution",
    "composite_component",
)
RELATION_BASES = ("distinct", "sibling_competitor", "uncertain")

# This model call is a treatment implementation, not a deterministic ontology
# or truth label. Deterministic post-processing treats uncertainty fail-open.
TYPE_COMPLETION_PROMPT = """Role: source-blind candidate admission and append-only completion implementer.

For EVERY candidate output candidate_id, admission (main|residual),
relation_basis (distinct|sibling_competitor|uncertain),
sibling_of_candidate_id, and reason. A candidate may be residual only when it
is a same-parent alternative to one specified, more evidence-supported
candidate in this registry. Put that retained candidate's ID in
sibling_of_candidate_id. Symmetric sibling pairs, unclear direction, or absent
case evidence are uncertain and remain main. Exact/frozen synonyms are already
merged. Never merge candidates.

You may also propose AT MOST ONE append-only completed child per main parent.
The parent remains. Use only literal patient facts and cite verbatim vignette
support_spans. modifier_axes may contain only: etiology, anatomy,
subtype_histology, complication, scope_distribution, temporal_evolution,
composite_component.

Return strict JSON only:
{"admissions":[{"candidate_id":"R#","admission":"main|residual",
"relation_basis":"distinct|sibling_competitor|uncertain",
"sibling_of_candidate_id":"R# or empty","reason":"brief"}],
"completions":[{"parent_candidate_id":"R#","completed_label":"label",
"modifier_axes":["allowed axis"],"support_spans":["verbatim quotation"],
"reason":"brief"}]}
Admissions cover every ID exactly once; completions may be empty. Do not use
answer options, invent patient facts, delete parents, or combine candidates.
"""

LITE_SELECTOR_PROMPT = """Role: source-blind compact clinical differential selector.
Choose exactly one supplied candidate ID using the clean vignette and
candidate-local evidence. Prefer specificity only when its qualifiers are
supported. Discount repeated observations; order and IDs are arbitrary.
Return strict JSON only:
{"champion_id":"R#","runner_up_id":"R# or empty","margin":"high|medium|low",
"decisive_items":["up to three supplied verbatim spans"],
"rationale":"brief contrast",
"rejected":[{"candidate_id":"R#","why":"brief"}]}
Use only supplied IDs. Never invent, rename, merge or compose a candidate.
No options, gold, source, old champion, rank, score or vote is supplied.
"""

PAIRWISE_INTEGRATOR_PROMPT = """Role: source-blind raw-span pairwise clinical evidence integrator.
Compare the strongest fixed candidates on the SAME raw vignette spans across
identity, cause, anatomy, time, polarity, subtype, complication, distribution
and composite completeness. Discount correlated restatements. Generator
assessments are explicitly non-raw opinions and may not masquerade as quotes.
Return strict JSON only:
{"champion_id":"R#","runner_up_id":"R# or empty","margin":"high|medium|low",
"decisive_items":["up to three supplied verbatim spans"],
"counterfactual_missing_items":["up to three missing/disconfirming items"],
"rationale":"brief pairwise contrast",
"rejected":[{"candidate_id":"R#","why":"brief"}]}
Use only supplied IDs. Never invent, rename, merge or compose a candidate.
Order is arbitrary; do not use source, champion, rank, score, vote or options.
"""

PROMPT_HASHES = {
    "type_completion": sha256_text(TYPE_COMPLETION_PROMPT),
    "lite_selector": sha256_text(LITE_SELECTOR_PROMPT),
    "pairwise_integrator": sha256_text(PAIRWISE_INTEGRATOR_PROMPT),
}
CALL_BUDGETS = {
    A0_CONTROL: {"incremental_online_calls": 1, "deployment_equivalent_calls": 2},
    A1_VIEWS: {"incremental_online_calls": 1, "deployment_equivalent_calls": 4},
    A2_VIEWS_TYPED: {"incremental_online_calls": 2, "deployment_equivalent_calls": 5},
    A3_FULL: {"incremental_online_calls": 2, "deployment_equivalent_calls": 5},
    B1_CORELIFT: {"incremental_online_calls": 2, "deployment_equivalent_calls": 5},
}
SOURCE_FILES = (
    Path(__file__).resolve(),
    ROOT / "analysis/mechanism_v2/common.py",
    ROOT / "analysis/mechanism_v2/online_runner.py",
    ROOT / "analysis/mechanism_v2/runtime_contract.py",
    ROOT / "analysis/mechanism_v2/e9_view_independence.py",
    ROOT / "analysis/mechanism_v2/e4_fixed_pool_crossover.py",
    ROOT / "analysis/mechanism_v2/ceiling_closure_online.py",
)


def _clean(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _span_text(value: Any) -> str:
    return str(value.get("text") or "") if isinstance(value, Mapping) else str(value or "")


def _literal_span(vignette: str, value: Any) -> dict[str, Any] | None:
    text = _span_text(value)
    if not text:
        return None
    try:
        return _normalize_quotation(vignette, {"text": text})
    except AssertionError:
        return None


def _dedupe_spans(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output, seen = [], set()
    for value in values:
        row = {"start": int(value["start"]), "end": int(value["end"]), "text": str(value["text"])}
        key = (row["start"], row["end"], row["text"])
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output


def _view_rows(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in raw.get("candidates") or []:
        if not isinstance(item, Mapping):
            continue
        label = _clean(item.get("name") or item.get("label"), 500)
        if normalize_label(label):
            rows.append(
                {
                    "label": label,
                    "support": list(item.get("support_spans") or []),
                    "contradict": list(item.get("contradict_spans") or []),
                    "why": _clean(item.get("why") or item.get("assessment"), 900),
                    "axis_node": _clean(item.get("axis_node"), 300),
                    "protected_reason": _clean(item.get("protected_reason"), 500),
                }
            )
    return rows


def anchor_view(case_key: str) -> str:
    return STAGE_KEYS[stable_seed("corelift-anchor-v1", case_key) % 3]


def build_registry(
    case_key: str,
    raw_views: Mapping[str, Mapping[str, Any]],
    vignette: str,
    bridge: FrozenExactSynonymBridge,
    *,
    view_keys: Sequence[str] = STAGE_KEYS,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for view_key in view_keys:
        for source in _view_rows(raw_views.get(view_key) or {}):
            concept_key = bridge.canonical_key(source["label"])
            if not concept_key:
                continue
            row = grouped.setdefault(
                concept_key,
                {"labels": [], "views": set(), "support": [], "contradict": [], "assessments": []},
            )
            row["labels"].append(source["label"])
            row["views"].add(view_key)
            for kind, target in (("support", "support"), ("contradict", "contradict")):
                for original in source[kind]:
                    literal = _literal_span(vignette, original)
                    if literal:
                        row[target].append(literal)
                    elif _span_text(original):
                        row["assessments"].append(
                            {"view_role": VIEW_ROLES[view_key], "kind": f"nonliteral_{kind}",
                             "assessment": _clean(_span_text(original), 900)}
                        )
            for kind in ("why", "axis_node", "protected_reason"):
                if source[kind]:
                    row["assessments"].append(
                        {"view_role": VIEW_ROLES[view_key], "kind": kind,
                         "assessment": source[kind]}
                    )
    keys = sorted(grouped, key=lambda key: (stable_seed("corelift-neutral-id-v1", case_key, key), key))
    output = []
    for index, key in enumerate(keys, 1):
        row, seen, assessments = grouped[key], set(), []
        counts = Counter(row["labels"])
        label = sorted(counts, key=lambda value: (-counts[value], len(normalize_label(value)), normalize_label(value)))[0]
        for item in row["assessments"]:
            identity = (item["view_role"], item["kind"], item["assessment"])
            if identity not in seen:
                seen.add(identity)
                assessments.append(item)
        output.append(
            {
                "candidate_id": f"R{index}", "concept_key": key, "label": label,
                "surface_labels": sorted(set(row["labels"]), key=normalize_label),
                "view_keys": sorted(row["views"], key=STAGE_KEYS.index),
                "view_count": len(row["views"]),
                "raw_support_spans": _dedupe_spans(row["support"])[:8],
                "raw_contradict_spans": _dedupe_spans(row["contradict"])[:6],
                "generator_assessments": assessments[:12],
                "candidate_kind": "parent", "parent_candidate_id": "", "modifier_axes": [],
            }
        )
    return output


def cap_main_pool(
    case_key: str, candidates: Sequence[Mapping[str, Any]], *, max_pool: int = MAX_MAIN_POOL
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(
        (dict(row) for row in candidates),
        key=lambda row: (
            -int(row.get("view_count") or 0), -len(row.get("raw_support_spans") or []),
            stable_seed("corelift-main-cap-v1", case_key, row["concept_key"]),
            str(row["concept_key"]),
        ),
    )
    return ordered[:max_pool], [{**row, "residual_reason": "main_pool_cap"} for row in ordered[max_pool:]]


def _payload_order(case_key: str, arm: str, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (stable_seed("corelift-payload-order-v1", case_key, arm, row["candidate_id"]),
                         str(row["candidate_id"])),
    )


def candidate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "candidate_id": str(row["candidate_id"]), "label": str(row["label"]),
        "raw_support_spans": list(row.get("raw_support_spans") or []),
        "raw_contradict_spans": list(row.get("raw_contradict_spans") or []),
        "generator_assessments": list(row.get("generator_assessments") or []),
    }
    if row.get("candidate_kind") == "completion":
        payload.update({"candidate_kind": "append_only_completion",
                        "parent_candidate_id": str(row["parent_candidate_id"]),
                        "modifier_axes": list(row.get("modifier_axes") or [])})
    return payload


def build_type_payload(job: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "case_id": str(job["case_key"]), "vignette": str(job["vignette"]),
        "candidates": [candidate_payload(row) for row in
                       _payload_order(str(job["case_key"]), "type_completion", job["union_registry"])],
    }
    assert_target_blind(payload)
    return payload


def validate_type_completion_response(response: Mapping[str, Any], candidate_ids: set[str]) -> str | None:
    admissions = response.get("admissions")
    if not isinstance(admissions, list) or any(not isinstance(row, Mapping) for row in admissions):
        return "admissions must be a list of objects"
    seen = [str(row.get("candidate_id") or "") for row in admissions]
    if len(seen) != len(candidate_ids) or set(seen) != candidate_ids or len(seen) != len(set(seen)):
        return "admissions must cover every candidate ID exactly once"
    for row in admissions:
        if str(row.get("admission")) not in {"main", "residual"}:
            return "invalid admission"
        if str(row.get("relation_basis")) not in RELATION_BASES:
            return "invalid relation_basis"
        sibling_of = str(row.get("sibling_of_candidate_id") or "")
        if sibling_of and (
            sibling_of not in candidate_ids
            or sibling_of == str(row.get("candidate_id") or "")
        ):
            return "invalid sibling_of_candidate_id"
    completions = response.get("completions")
    return None if isinstance(completions, list) else "completions must be a list"


def normalize_type_treatment(
    response: Mapping[str, Any],
    registry: Sequence[Mapping[str, Any]],
    vignette: str,
    bridge: FrozenExactSynonymBridge,
) -> dict[str, Any]:
    """Fail-open admissions and reject individual invalid completions."""
    by_id = {str(row["candidate_id"]): dict(row) for row in registry}
    error = validate_type_completion_response(response, set(by_id))
    if error:
        raise ValueError(error)
    model_admissions = {
        str(row["candidate_id"]): row for row in response["admissions"]
    }
    provisional_siblings = {
        candidate_id
        for candidate_id, row in model_admissions.items()
        if str(row["relation_basis"]) == "sibling_competitor"
        and str(row.get("admission")) == "residual"
    }
    admissions, main_ids, sibling_ids = [], [], []
    for model_row in response["admissions"]:
        candidate_id = str(model_row["candidate_id"])
        relation = str(model_row["relation_basis"])
        sibling_of = str(model_row.get("sibling_of_candidate_id") or "")
        directed_sibling = bool(
            candidate_id in provisional_siblings
            and sibling_of in by_id
            and sibling_of not in provisional_siblings
        )
        effective = "residual" if directed_sibling else "main"
        admissions.append(
            {
                "candidate_id": candidate_id,
                "model_admission": str(model_row["admission"]),
                "relation_basis": relation,
                "sibling_of_candidate_id": sibling_of,
                "effective_admission": effective,
                "reason": _clean(model_row.get("reason"), 900),
            }
        )
        (sibling_ids if effective == "residual" else main_ids).append(candidate_id)

    completions, rejections = [], []
    parent_keys = {
        candidate_id: bridge.canonical_key(str(row["label"]))
        for candidate_id, row in by_id.items()
    }
    seen_completion_parents: set[str] = set()
    for model_row in response.get("completions") or []:
        if not isinstance(model_row, Mapping):
            rejections.append(
                {"parent_candidate_id": "", "completed_label": "", "reason": "malformed_completion"}
            )
            continue
        parent_id = str(model_row.get("parent_candidate_id") or "")
        label = _clean(model_row.get("completed_label"), 500)
        raw_axes = model_row.get("modifier_axes")
        axes = [str(axis) for axis in raw_axes] if isinstance(raw_axes, list) else []
        rejection, spans = "", []
        if parent_id not in by_id:
            rejection = "unknown_parent_candidate_id"
        elif parent_id in seen_completion_parents:
            rejection = "duplicate_completion_for_parent"
        elif parent_id not in main_ids:
            rejection = "parent_not_effective_main"
        elif not label:
            rejection = "empty_completed_label"
        elif not isinstance(raw_axes, list) or len(axes) != len(set(axes)):
            rejection = "invalid_modifier_axes"
        elif set(axes) - set(MODIFIER_AXES):
            rejection = "unknown_modifier_axis"
        elif not axes:
            rejection = "no_modifier_axis"
        elif bridge.equivalent(str(by_id[parent_id]["label"]), label):
            rejection = "completion_equivalent_to_parent"
        elif any(
            other_id != parent_id
            and parent_keys[other_id]
            and bridge.canonical_key(label) == parent_keys[other_id]
            for other_id in by_id
        ):
            rejection = "completion_equivalent_to_other_candidate"
        elif not isinstance(model_row.get("support_spans"), list):
            rejection = "invalid_support_spans"
        elif not model_row.get("support_spans"):
            rejection = "no_support_span"
        else:
            for original in model_row["support_spans"]:
                literal = _literal_span(vignette, original)
                if literal is None:
                    rejection = "nonliteral_support_span"
                    break
                spans.append(literal)
        if rejection:
            rejections.append(
                {"parent_candidate_id": parent_id, "completed_label": label, "reason": rejection}
            )
        else:
            completions.append(
                {
                    "parent_candidate_id": parent_id,
                    "completed_label": label,
                    "modifier_axes": axes,
                    "support_spans": _dedupe_spans(spans),
                    "reason": _clean(model_row.get("reason"), 900),
                }
            )
        if parent_id:
            seen_completion_parents.add(parent_id)
    return {
        "admissions": sorted(admissions, key=lambda row: row["candidate_id"]),
        "main_candidate_ids": sorted(main_ids),
        "sibling_residual_ids": sorted(sibling_ids),
        "validated_completions": completions,
        "completion_rejections": rejections,
    }


def _completion_axis_rank(axes: Sequence[str]) -> int:
    # No frozen parent_tightening ontology axis exists. The two highest
    # executable priorities are composite/component and etiology.
    priority = {
        "composite_component": 0,
        "etiology": 1,
        "anatomy": 2,
        "subtype_histology": 3,
        "scope_distribution": 4,
        "complication": 5,
        "temporal_evolution": 6,
    }
    return min((priority[axis] for axis in axes), default=99)


def pool_for_arm(
    job: Mapping[str, Any],
    arm: str,
    type_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    case_key, residual = str(job["case_key"]), []
    pairs, completion_rejections = [], []
    available = list(job["anchor_registry"] if arm == A0_CONTROL else job["union_registry"])
    if arm in TYPED_ARMS:
        if not type_row or not type_row.get("success"):
            raise ValueError("successful frozen type-completion result required")
        treatment = dict(type_row.get("treatment") or {})
        main_ids = set(map(str, treatment.get("main_candidate_ids") or []))
        sibling_ids = set(map(str, treatment.get("sibling_residual_ids") or []))
        residual.extend(
            {**dict(row), "residual_reason": "explicit_sibling_competitor"}
            for row in available
            if str(row["candidate_id"]) in sibling_ids
        )
        available = [row for row in available if str(row["candidate_id"]) in main_ids]
    parents, capped = cap_main_pool(case_key, available)
    residual.extend(capped)
    frontier = list(parents)

    if arm == B1_CORELIFT:
        treatment = dict((type_row or {}).get("treatment") or {})
        completion_rejections = list(treatment.get("completion_rejections") or [])
        parent_ids, proposals = {str(row["candidate_id"]) for row in parents}, []
        for completion in treatment.get("validated_completions") or []:
            if str(completion["parent_candidate_id"]) not in parent_ids:
                residual.append(
                    {
                        "candidate_kind": "completion",
                        "parent_candidate_id": str(completion["parent_candidate_id"]),
                        "label": str(completion["completed_label"]),
                        "residual_reason": "parent_not_in_capped_main",
                    }
                )
            else:
                proposals.append(dict(completion))
        proposals.sort(
            key=lambda row: (
                -len(row.get("support_spans") or []),
                _completion_axis_rank(list(row.get("modifier_axes") or [])),
                stable_seed("corelift-completion-cap-v1", case_key,
                            row["parent_candidate_id"], normalize_label(row["completed_label"])),
            )
        )
        slots = max(0, MAX_MAIN_POOL - len(parents))
        for index, completion in enumerate(proposals[:slots], 1):
            parent_id, child_id = str(completion["parent_candidate_id"]), f"C{index}"
            frontier.append(
                {
                    "candidate_id": child_id,
                    "concept_key": f"completion:{parent_id}:{normalize_label(completion['completed_label'])}",
                    "label": str(completion["completed_label"]),
                    "surface_labels": [str(completion["completed_label"])],
                    "view_keys": [], "view_count": 0,
                    "raw_support_spans": list(completion["support_spans"]),
                    "raw_contradict_spans": [],
                    "generator_assessments": [
                        {"view_role": "type_completion_treatment", "kind": "completion_reason",
                         "assessment": str(completion.get("reason") or "")}
                    ],
                    "candidate_kind": "completion",
                    "parent_candidate_id": parent_id,
                    "modifier_axes": list(completion["modifier_axes"]),
                }
            )
            pairs.append({"parent_candidate_id": parent_id, "child_candidate_id": child_id})
        for completion in proposals[slots:]:
            residual.append(
                {
                    "candidate_kind": "completion",
                    "parent_candidate_id": str(completion["parent_candidate_id"]),
                    "label": str(completion["completed_label"]),
                    "modifier_axes": list(completion["modifier_axes"]),
                    "raw_support_spans": list(completion["support_spans"]),
                    "residual_reason": "main_pool_cap",
                }
            )
    ordered = _payload_order(case_key, arm, frontier)
    if len(ordered) > MAX_MAIN_POOL:
        raise AssertionError("main pool exceeds frozen cap")
    if arm == B1_CORELIFT:
        retained = {str(row["candidate_id"]) for row in ordered if row["candidate_kind"] == "parent"}
        if retained != {str(row["candidate_id"]) for row in parents}:
            raise AssertionError("append-only pool deleted a parent")
    return {
        "frontier": ordered,
        "residual": residual,
        "parent_child_pairs": pairs,
        "completion_rejections": completion_rejections,
    }


def make_selector_payload(
    job: Mapping[str, Any], arm: str, pool: Mapping[str, Any]
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": str(job["case_key"]),
        "vignette": str(job["vignette"]),
        "candidates": [candidate_payload(row) for row in pool["frontier"]],
    }
    if arm in {A1_VIEWS, A3_FULL, B1_CORELIFT}:
        payload["view_metadata"] = [
            {"view_role": VIEW_ROLES[key],
             "available": bool(job["view_status"][key]["usable_candidate_n"])}
            for key in STAGE_KEYS
        ]
    assert_target_blind(payload)
    return payload


def validate_selector_response(
    response: Mapping[str, Any],
    candidate_ids: set[str],
    vignette: str,
    *,
    full: bool,
) -> str | None:
    champion, runner = str(response.get("champion_id") or ""), str(response.get("runner_up_id") or "")
    if champion not in candidate_ids:
        return "champion_id is not a supplied candidate"
    if runner and (runner not in candidate_ids or runner == champion):
        return "runner_up_id is invalid"
    if str(response.get("margin") or "").lower() not in {"high", "medium", "low"}:
        return "margin must be high|medium|low"
    decisive = response.get("decisive_items")
    if not isinstance(decisive, list) or len(decisive) > 3:
        return "decisive_items must be a list of at most three"
    if any(_span_text(item) and _span_text(item) not in vignette for item in decisive):
        return "decisive item is not a verbatim vignette span"
    rejected = response.get("rejected")
    if not isinstance(rejected, list) or any(
        not isinstance(row, Mapping) or str(row.get("candidate_id") or "") not in candidate_ids
        for row in rejected
    ):
        return "rejected contains an unknown candidate"
    if full:
        missing = response.get("counterfactual_missing_items")
        if not isinstance(missing, list) or len(missing) > 3:
            return "counterfactual_missing_items must be a list of at most three"
    return None


def build_jobs(
    bridge: FrozenExactSynonymBridge,
) -> tuple[list[dict[str, Any]], list[Path], list[Path]]:
    """Build all six slices without loading gold/evaluator fields."""
    jobs, stage_paths, dataset_paths = [], [], []
    for spec in DEVELOPMENT_SLICES:
        cases = load_normalized_cases(spec.cases_json)
        dataset_paths.append(spec.cases_json)
        for source_id in sorted(
            cases, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value)
        ):
            stage_path = spec.stage_dir / f"{source_id}.json"
            if not stage_path.is_file():
                raise FileNotFoundError(stage_path)
            stages = (json.loads(stage_path.read_text(encoding="utf-8")).get("stages") or {})
            raw_views = {key: dict(stages.get(key) or {}) for key in STAGE_KEYS}
            vignette = clean_vignette(str(cases[source_id].get("case_text") or ""))[:9000]
            case_key, anchor = f"{spec.slice_id}/{source_id}", anchor_view(f"{spec.slice_id}/{source_id}")
            union = build_registry(case_key, raw_views, vignette, bridge)
            anchor_registry = build_registry(case_key, raw_views, vignette, bridge, view_keys=(anchor,))
            view_status = {
                key: {"present": bool(stages.get(key)), "usable_candidate_n": len(_view_rows(raw_views[key]))}
                for key in STAGE_KEYS
            }
            errors = []
            if not union:
                errors.append("all_frozen_views_empty")
            if not anchor_registry:
                errors.append("selected_anchor_view_empty")
            jobs.append(
                {
                    "case_key": case_key, "slice_id": spec.slice_id, "family": spec.family,
                    "source_id": source_id, "vignette": vignette, "anchor_key": anchor,
                    "raw_views": raw_views, "union_registry": union,
                    "anchor_registry": anchor_registry, "view_status": view_status,
                    "construction_errors": errors,
                    "stage_path": str(stage_path.relative_to(ROOT)),
                }
            )
            stage_paths.append(stage_path)
    jobs.sort(key=lambda row: row["case_key"])
    counts = Counter(job["family"] for job in jobs)
    if len(jobs) != 800 or counts != Counter({"DA": 400, "MCR": 400}):
        raise AssertionError(f"development join must be DA400+MCR400; got {counts}")
    if len({job["case_key"] for job in jobs}) != 800:
        raise AssertionError("case_key collision")
    return jobs, stage_paths, dataset_paths


def freeze_preregistration(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    stage_paths: Sequence[Path],
    dataset_paths: Sequence[Path],
    selector_model: str,
    type_model: str,
) -> dict[str, Any]:
    core = {
        "experiment_id": EXPERIMENT_ID,
        "schema": SCHEMA,
        "case_keys": [job["case_key"] for job in jobs],
        "arms": list(ARMS),
        "prompt_hashes": PROMPT_HASHES,
        "selector_model": selector_model,
        "type_completion_model": type_model,
        "thresholds": {
            "max_main_pool": MAX_MAIN_POOL,
            "max_completion_per_parent": 1,
            "explicit_sibling_only_residual": True,
            "verbatim_completion_support_required": True,
        },
        "modifier_axes": list(MODIFIER_AXES),
        "anchor_assignments": {job["case_key"]: job["anchor_key"] for job in jobs},
        "source_hashes": {
            str(path.relative_to(ROOT)): file_sha256(path) for path in SOURCE_FILES
        },
        "bridge_sha256": file_sha256(BRIDGE_PATH),
        "dataset_sources_sha256": combined_file_sha256(dataset_paths),
        "frozen_forest_stage_sha256": combined_file_sha256(stage_paths),
        "forest_stage_paths_sha256": canonical_sha256(
            [str(path.relative_to(ROOT)) for path in sorted(stage_paths)]
        ),
        "call_budgets": CALL_BUDGETS,
    }
    candidate = {
        **core,
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "family_counts": dict(Counter(job["family"] for job in jobs)),
        "development_not_confirmation": True,
        "type_completion_is_treatment_not_truth": True,
        "deterministic_sibling_ontology_available": False,
        "payload_withheld": [
            "gold/options", "source/model identity", "old champion", "rank/score/vote"
        ],
        "failure_policy": "ITA; every failed case retained without imputation",
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key, value in core.items():
            if frozen.get(key) != value:
                raise AssertionError(f"preregistration mismatch: {key}")
        return frozen
    atomic_json(path, candidate)
    return candidate


def write_construction(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    rows = []
    for job in jobs:
        a0, a0r = cap_main_pool(job["case_key"], job["anchor_registry"])
        a1, a1r = cap_main_pool(job["case_key"], job["union_registry"])
        rows.append(
            {
                "case_key": job["case_key"], "slice_id": job["slice_id"],
                "family": job["family"], "source_id": job["source_id"],
                "stage_path": job["stage_path"], "anchor_key": job["anchor_key"],
                "view_status": job["view_status"],
                "construction_errors": job["construction_errors"],
                "union_registry_n": len(job["union_registry"]),
                "anchor_registry_n": len(job["anchor_registry"]),
                "A0_frontier_ids": [row["candidate_id"] for row in a0],
                "A0_residual_ids": [row["candidate_id"] for row in a0r],
                "A1_frontier_ids": [row["candidate_id"] for row in a1],
                "A1_residual_ids": [row["candidate_id"] for row in a1r],
                "type_payload_sha256": canonical_sha256(build_type_payload(job)),
            }
        )
    write_jsonl(out / "construction_ledger.jsonl", rows)


def _case_file(directory: Path, case_key: str) -> Path:
    return directory / "case_files" / f"{canonical_sha256(case_key)[:24]}.json"


def _load_completed(
    directory: Path, jobs: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    completed = {}
    for job in jobs:
        path = _case_file(directory, job["case_key"])
        if path.is_file():
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("case_key") != job["case_key"]:
                raise AssertionError(f"case checkpoint mismatch: {path}")
            completed[job["case_key"]] = row
    return completed


def archive_failed_checkpoints(
    directory: Path, jobs: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Requeue explicit failures while preserving their first-pass artifacts."""
    archived: list[dict[str, Any]] = []
    archive_dir = directory / "retry_archive"
    for job in jobs:
        case_path = _case_file(directory, str(job["case_key"]))
        if not case_path.is_file():
            continue
        row = json.loads(case_path.read_text(encoding="utf-8"))
        if bool(row.get("success")):
            continue
        cache = row.get("cache_provenance") or {}
        cache_key = str(cache.get("cache_key") or row.get("cache_key") or "")
        retry_index = 1
        while (archive_dir / f"{case_path.stem}.retry{retry_index}.case.json").exists():
            retry_index += 1
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived_case = archive_dir / f"{case_path.stem}.retry{retry_index}.case.json"
        case_path.replace(archived_case)
        archived_cache = ""
        cache_path = directory / "cache" / f"{cache_key}.json" if cache_key else None
        if cache_path is not None and cache_path.is_file():
            target = archive_dir / f"{cache_key}.retry{retry_index}.cache.json"
            cache_path.replace(target)
            archived_cache = str(target)
        archived.append(
            {
                "case_key": str(job["case_key"]),
                "old_error": str(row.get("error") or ""),
                "cache_key": cache_key,
                "archived_case": str(archived_case),
                "archived_cache": archived_cache,
                "retry_index": retry_index,
            }
        )
    if archived:
        prior = read_jsonl(directory / "retry_ledger.jsonl")
        write_jsonl(directory / "retry_ledger.jsonl", prior + archived)
    return archived


def _write_case(directory: Path, row: Mapping[str, Any]) -> None:
    atomic_json(_case_file(directory, str(row["case_key"])), dict(row))


def _type_failure(job: Mapping[str, Any], error: str) -> dict[str, Any]:
    payload = build_type_payload(job)
    return {
        "case_key": job["case_key"], "slice_id": job["slice_id"],
        "family": job["family"], "source_id": job["source_id"],
        "success": False, "error": error, "response": {}, "treatment": {},
        "payload_sha256": canonical_sha256(payload),
        "cache_hit": False, "cache_key": "",
        "incremental_calls": 1, "deployment_equivalent_calls": 1,
    }


def run_type_completion(
    jobs: Sequence[Mapping[str, Any]],
    out: Path,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    directory = out / "type_completion"
    directory.mkdir(parents=True, exist_ok=True)
    completed = _load_completed(directory, jobs)
    pending = [job for job in jobs if job["case_key"] not in completed]
    caller = OnlineJSONCaller(
        out_dir=directory, model=model, telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        if not job["union_registry"]:
            return _type_failure(job, "all_frozen_views_empty")
        payload = build_type_payload(job)
        ids = {row["candidate_id"] for row in job["union_registry"]}
        outcome = caller.call(
            module="CoreLiftTypeCompletion", prompt=TYPE_COMPLETION_PROMPT, payload=payload,
            validator=lambda response: validate_type_completion_response(response, ids),
        )
        success, error, treatment = outcome.success, outcome.error, {}
        if success:
            try:
                treatment = normalize_type_treatment(
                    outcome.response, job["union_registry"], job["vignette"], bridge
                )
            except Exception as exc:
                success, error = False, f"{type(exc).__name__}: {exc}"
        return {
            "case_key": job["case_key"], "slice_id": job["slice_id"],
            "family": job["family"], "source_id": job["source_id"],
            "success": success, "error": error, "response": outcome.response,
            "treatment": treatment, "payload_sha256": outcome.payload_sha256,
            "cache_hit": outcome.cache_hit, "cache_key": outcome.cache_key,
            "incremental_calls": 1, "deployment_equivalent_calls": 1,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in pending}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = _type_failure(job, f"{type(exc).__name__}: {exc}")
            _write_case(directory, row)
            completed[job["case_key"]] = row
            if done % 25 == 0 or done == len(pending):
                print(f"type_completion={done}/{len(pending)}", flush=True)
    rows = [completed[job["case_key"]] for job in jobs]
    write_jsonl(directory / "case_results.jsonl", rows)
    atomic_json(
        directory / "telemetry_summary.json",
        aggregate_telemetry(read_jsonl(directory / "telemetry.jsonl")),
    )
    return rows


def result_row(
    job: Mapping[str, Any],
    arm: str,
    pool: Mapping[str, Any],
    payload: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    success: bool,
    error: str = "",
    cache_hit: bool = False,
    cache_key: str = "",
    payload_sha256: str = "",
) -> dict[str, Any]:
    by_id = {row["candidate_id"]: row["label"] for row in pool.get("frontier") or []}
    champion_id = str(response.get("champion_id") or "") if success else ""
    runner_id = str(response.get("runner_up_id") or "") if success else ""
    budget = CALL_BUDGETS[arm]
    return {
        "case_key": job["case_key"], "slice": job["slice_id"],
        "family": job["family"], "source_id": job["source_id"], "arm": arm,
        "success": success, "error": error,
        "champion_label": by_id.get(champion_id, ""),
        "runner_up_label": by_id.get(runner_id, ""),
        "champion_id": champion_id, "runner_up_id": runner_id,
        "candidate_pool": list(payload.get("candidates") or []),
        "frontier": list(pool.get("frontier") or []),
        "residual": list(pool.get("residual") or []),
        "response": dict(response),
        "payload_hash": payload_sha256 or canonical_sha256(payload),
        "cache_provenance": {"cache_hit": cache_hit, "cache_key": cache_key},
        "incremental_calls": budget["incremental_online_calls"],
        "deployment_equivalent_calls": budget["deployment_equivalent_calls"],
        "parent_child_pairs": list(pool.get("parent_child_pairs") or []),
        "completion_rejections": list(pool.get("completion_rejections") or []),
    }


def _arm_failure(
    job: Mapping[str, Any], arm: str, error: str, pool: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    pool = dict(pool or {"frontier": [], "residual": [], "parent_child_pairs": [],
                         "completion_rejections": []})
    payload = {"case_id": job["case_key"], "vignette": job["vignette"],
               "candidates": [candidate_payload(row) for row in pool["frontier"]]}
    assert_target_blind(payload)
    return result_row(job, arm, pool, payload, {}, success=False, error=error)


def run_arm(
    arm: str,
    jobs: Sequence[Mapping[str, Any]],
    out: Path,
    model: str,
    workers: int,
    *,
    call_timeout: int = 180,
    max_retries: int = 2,
    retry_failures: bool = False,
) -> list[dict[str, Any]]:
    directory = out / "arms" / arm
    directory.mkdir(parents=True, exist_ok=True)
    if retry_failures:
        archived = archive_failed_checkpoints(directory, jobs)
        print(f"arm={arm} retry_archived={len(archived)}", flush=True)
    completed = _load_completed(directory, jobs)
    pending = [job for job in jobs if job["case_key"] not in completed]
    type_by_case = {}
    if arm in TYPED_ARMS:
        type_by_case = {
            row["case_key"]: row
            for row in read_jsonl(out / "type_completion/case_results.jsonl")
        }
        if len(type_by_case) != len(jobs):
            raise AssertionError("typed arm requires complete type_completion results")
    caller = OnlineJSONCaller(
        out_dir=directory, model=model, telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0, call_timeout=call_timeout, max_retries=max_retries,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        try:
            pool = pool_for_arm(job, arm, type_by_case.get(job["case_key"]))
        except Exception as exc:
            return _arm_failure(job, arm, f"{type(exc).__name__}: {exc}")
        if not pool["frontier"]:
            return _arm_failure(job, arm, "empty_candidate_pool", pool)
        payload = make_selector_payload(job, arm, pool)
        full = arm in FULL_ARMS
        prompt = PAIRWISE_INTEGRATOR_PROMPT if full else LITE_SELECTOR_PROMPT
        ids = {row["candidate_id"] for row in pool["frontier"]}
        outcome = caller.call(
            module=f"CoreLift_{arm}", prompt=prompt, payload=payload,
            validator=lambda response: validate_selector_response(
                response, ids, job["vignette"], full=full
            ),
        )
        return result_row(
            job, arm, pool, payload, outcome.response, success=outcome.success,
            error=outcome.error, cache_hit=outcome.cache_hit,
            cache_key=outcome.cache_key, payload_sha256=outcome.payload_sha256,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in pending}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = _arm_failure(job, arm, f"{type(exc).__name__}: {exc}")
            _write_case(directory, row)
            completed[job["case_key"]] = row
            if done % 25 == 0 or done == len(pending):
                print(f"arm={arm} completed={done}/{len(pending)}", flush=True)
    rows = [completed[job["case_key"]] for job in jobs]
    write_jsonl(directory / "case_results.jsonl", rows)
    atomic_json(
        directory / "telemetry_summary.json",
        aggregate_telemetry(read_jsonl(directory / "telemetry.jsonl")),
    )
    return rows


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups = {}
    for group, group_rows in [("all", list(rows))] + [
        (family, [row for row in rows if row["family"] == family])
        for family in ("DA", "MCR")
    ]:
        arms = {}
        for arm in ARMS:
            arm_rows = [row for row in group_rows if row["arm"] == arm]
            widths = [len(row.get("frontier") or []) for row in arm_rows]
            served = sum(bool(row["success"]) for row in arm_rows)
            arms[arm] = {
                "n_intention": len(arm_rows),
                "n_served": served,
                "service_rate": round(served / len(arm_rows), 6) if arm_rows else None,
                "pool_width_mean": round(sum(widths) / len(widths), 6) if widths else None,
                "pool_width_distribution": dict(Counter(map(str, widths))),
                "incremental_calls": sum(int(row["incremental_calls"]) for row in arm_rows),
                "deployment_equivalent_calls": sum(
                    int(row["deployment_equivalent_calls"]) for row in arm_rows
                ),
            }
        groups[group] = {"arms": arms}
    return {
        "experiment_id": EXPERIMENT_ID,
        "n_cases": len({row["case_key"] for row in rows}),
        "n_conditions": len(rows),
        "groups": groups,
        "endpoint_note": "No gold endpoint is computed by this runner.",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def finalize(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    selector_model: str,
    type_model: str,
    workers: int,
) -> None:
    rows = []
    for arm in ARMS:
        arm_rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(arm_rows) != len(jobs):
            raise AssertionError(f"arm {arm} incomplete: {len(arm_rows)}/{len(jobs)}")
        rows.extend(arm_rows)
    rows.sort(key=lambda row: (row["case_key"], ARMS.index(row["arm"])))
    write_jsonl(out / "case_conditions.jsonl", rows)
    atomic_json(out / "summary.json", summarize(rows))

    prereg = json.loads((out / "preregistration.json").read_text(encoding="utf-8"))
    environment = json.loads((out / "environment.json").read_text(encoding="utf-8"))
    manifests = {}
    for arm in ARMS:
        prompt_name = "pairwise_integrator" if arm in FULL_ARMS else "lite_selector"
        prompt_hashes = {"selector": PROMPT_HASHES[prompt_name]}
        if arm in TYPED_ARMS:
            prompt_hashes["type_completion"] = PROMPT_HASHES["type_completion"]
        manifest = RunManifest(
            experiment_id=EXPERIMENT_ID,
            arm_id=arm,
            dataset="six frozen development slices; DA400+MCR400",
            model=selector_model,
            workers=workers,
            rag=False,
            source_commit=prereg["source_commit"],
            prompt_hashes=prompt_hashes,
            input_hash=prereg["frozen_forest_stage_sha256"],
            selection_freeze="preregistration case_keys + Forest stage hash",
            endpoint_contract="target-blind construction/selection; endpoint delegated",
            capabilities=dict(environment.get("capabilities") or {}),
        )
        document = dict(manifest.__dict__)
        document.update(CALL_BUDGETS[arm])
        document.update(
            {
                "per_case_budget": True,
                "frozen_view_calls_counted_for_deployment": 1 if arm == A0_CONTROL else 3,
                "shared_type_completion_model": type_model if arm in TYPED_ARMS else None,
                "shared_type_results_not_additive_across_typed_arms": arm in TYPED_ARMS,
            }
        )
        manifests[arm] = document
    manifests["type_completion"] = {
        "experiment_id": EXPERIMENT_ID,
        "model": type_model,
        "workers": workers,
        "prompt_hashes": {"type_completion": PROMPT_HASHES["type_completion"]},
        "incremental_online_calls": 1,
        "deployment_equivalent_calls": 1,
        "per_case_budget": True,
        "shared_across_arms": sorted(TYPED_ARMS),
    }
    atomic_json(out / "manifests.json", manifests)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--selector-model", default=DEFAULT_SELECTOR_MODEL)
    parser.add_argument("--type-model", default=DEFAULT_TYPE_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--call-timeout", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--type-completion", action="store_true")
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, stage_paths, dataset_paths = build_jobs(bridge)
    prereg = freeze_preregistration(
        out, jobs, stage_paths, dataset_paths, args.selector_model, args.type_model
    )
    construction_path = out / "construction_ledger.jsonl"
    if args.prepare_only:
        write_construction(out, jobs)
    elif not construction_path.is_file():
        raise FileNotFoundError(
            "frozen construction ledger is missing; run --prepare-only before online stages"
        )
    environment_path = out / "environment.json"
    if not environment_path.is_file():
        atomic_json(
            environment_path,
            {
                "capabilities": dependency_capabilities(),
                "selector_model": args.selector_model,
                "type_completion_model": args.type_model,
                "workers": workers,
                "reasoning_controls": {
                    "effort": os.environ.get("TREE_DX_REASONING_EFFORT"),
                    "max_tokens": os.environ.get("TREE_DX_REASONING_MAX_TOKENS"),
                    "exclude": os.environ.get("TREE_DX_REASONING_EXCLUDE"),
                },
                "preregistration_sha256": file_sha256(out / "preregistration.json"),
            },
        )
    if args.prepare_only:
        print(f"prepared={len(jobs)} forest_hash={prereg['frozen_forest_stage_sha256']}")
    if args.type_completion:
        rows = run_type_completion(jobs, out, args.type_model, workers, bridge)
        print(f"type_completion served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.arm:
        rows = run_arm(
            args.arm,
            jobs,
            out,
            args.selector_model,
            workers,
            call_timeout=args.call_timeout,
            max_retries=args.max_retries,
            retry_failures=args.retry_failures,
        )
        print(f"arm={args.arm} served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.finalize:
        finalize(out, jobs, args.selector_model, args.type_model, workers)
        print(f"finalized={len(jobs)} arms={len(ARMS)}")
    if not any((args.prepare_only, args.type_completion, args.arm, args.finalize)):
        raise SystemExit("select --prepare-only, --type-completion, --arm, or --finalize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
