#!/usr/bin/env python3
"""Frozen staged evaluator for the CoreLift five-arm development experiment.

The evaluator is deliberately separate from the runner.  It freezes blinded
clinical/task cards, reuses byte-auditable prior endpoint decisions, runs only
the missing model judgments, and joins benchmark answers offline.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    FrozenExactSynonymBridge,
    clean_vignette,
    file_sha256,
    normalize_label,
)
from analysis.mechanism_v2.endpoint_migration import (  # noqa: E402
    CLINICAL_PROMPT,
    RELATIONS,
    load_case_metadata,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    atomic_json,
    stable_seed,
    validate_workers,
)


EXPERIMENT_ID = "corelift-evaluation-v1"
DEFAULT_SOURCE = (
    ROOT
    / "analysis/mechanism_v2/results/SLOT_YIELD_BREAKTHROUGH/case_conditions.jsonl"
)
DEFAULT_OUT = DEFAULT_SOURCE.parent / "evaluation"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
C0_ROOT = ROOT / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS"
MIGRATION_ROOT = ROOT / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION"
TASK_MODEL = "google/gemini-2.5-flash"
CLINICAL_REVIEWERS = {
    "reviewer_a": "google/gemini-2.5-flash",
    "reviewer_b": "anthropic/claude-sonnet-4.6",
    "reviewer_c": "openai/gpt-5.6-sol",
}
MODIFIER_REVIEWERS = {
    "modifier_a": "anthropic/claude-sonnet-4.6",
    "modifier_b": "openai/gpt-5.6-sol",
}
COMPATIBLE_RELATIONS = frozenset(
    {"complete_equivalent", "partial_parent_or_component"}
)
ARMS = ("A0_control", "A1_views", "A2_views_typed", "A3_full", "B1_corelift")
CONTRASTS = (
    ("A0_control", "A1_views", "A1-A0"),
    ("A1_views", "A2_views_typed", "A2-A1"),
    ("A2_views_typed", "A3_full", "A3-A2"),
    ("A0_control", "A3_full", "A3-A0"),
    ("A3_full", "B1_corelift", "B1-A3"),
)
MCR_PROMPT7 = (
    "Is our predicted diagnosis correct (y/n)?\n"
    "Predicted diagnosis: {predicted_diagnosis}, True diagnosis: "
    "{actual_diagnosis}\nAnswer [y/n].\n"
    'Return strict JSON as {"answer":"y|n","reason":"brief reason"}.'
)
MODIFIER_PROMPT = r"""You are an independent binary modifier-support reviewer.
The diagnostic system and experimental arm are hidden. For every modifier,
decide whether (1) its quoted support_span occurs literally in the supplied
vignette and (2) that span clinically supports the modifier as a reasonable
part of the completed diagnosis label. Do not infer unobserved patient facts.
Return strict JSON and cover every modifier_id exactly once:
{"judgments":[{"modifier_id":"M001","supported":true,
"reason":"brief vignette-grounded reason"}]}"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frozen_prompt_hashes() -> dict[str, str]:
    return {
        "clinical_sha256": hashlib.sha256(
            CLINICAL_PROMPT.encode("utf-8")
        ).hexdigest(),
        "mcr_prompt7_sha256": hashlib.sha256(
            MCR_PROMPT7.encode("utf-8")
        ).hexdigest(),
        "modifier_sha256": hashlib.sha256(
            MODIFIER_PROMPT.encode("utf-8")
        ).hexdigest(),
        "da_relation_mapper": file_sha256(
            ROOT / "src/agentclinic_tree_dx/prompts/answer_relation_mapper.txt"
        ),
        "da_strict_total_order": file_sha256(
            ROOT
            / "src/agentclinic_tree_dx/prompts/answer_option_strict_total_order.txt"
        ),
    }


def _surface(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _stable_id(namespace: str, *parts: Any, length: int = 24) -> str:
    raw = "\0".join([namespace, *(str(part) for part in parts)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def relation_key(
    case_key: str, label: str, bridge: FrozenExactSynonymBridge
) -> tuple[str, str]:
    """Clinical reuse key: case identity plus frozen canonical prediction."""
    return str(case_key), bridge.canonical_key(_surface(label))


def task_key(
    family: str, case_key: str, prediction: str, bridge: FrozenExactSynonymBridge
) -> tuple[str, str, str]:
    """Strict semantic task key; family and case can never be dropped."""
    return (
        str(family).upper(),
        str(case_key),
        bridge.canonical_key(_surface(prediction)),
    )


def _labels_from_pool(row: Mapping[str, Any]) -> list[str]:
    """Read candidate labels from all frozen runner interface variants."""
    raw: Any = None
    for key in ("candidate_pool", "frontier", "main_frontier"):
        if row.get(key) is not None:
            raw = row[key]
            break
    if isinstance(raw, Mapping):
        raw = (
            raw.get("candidates")
            or raw.get("items")
            or raw.get("frontier")
            or list(raw.values())
        )
    labels: list[str] = []
    for item in raw or []:
        if isinstance(item, Mapping):
            label = next(
                (
                    item.get(key)
                    for key in (
                        "label",
                        "candidate_label",
                        "diagnosis",
                        "name",
                        "completed_label",
                    )
                    if item.get(key)
                ),
                "",
            )
        else:
            label = item
        surface = _surface(label)
        if surface and normalize_label(surface) not in {
            normalize_label(existing) for existing in labels
        }:
            labels.append(surface)
    champion = _surface(
        row.get("champion_label")
        or row.get("prediction")
        or row.get("top1_diagnosis")
    )
    if champion and normalize_label(champion) not in {
        normalize_label(label) for label in labels
    }:
        labels.append(champion)
    return labels


def _options(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        return {
            str(letter).upper(): _surface(text)
            for letter, text in value.items()
            if _surface(text)
        }
    output: dict[str, str] = {}
    for index, item in enumerate(value or []):
        if isinstance(item, Mapping):
            letter = str(
                item.get("letter") or item.get("option") or chr(65 + index)
            ).upper()
            text = item.get("text") or item.get("label") or item.get("value")
        else:
            letter, text = chr(65 + index), item
        if _surface(text):
            output[letter] = _surface(text)
    return output


def _case_metadata(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Prefer runner-carried metadata, then join the frozen 800-case universe."""
    try:
        frozen = load_case_metadata()
    except Exception:
        frozen = {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_key = str(row["case_key"])
        base = dict(frozen.get(case_key) or {})
        family = str(row.get("family") or base.get("family") or "").upper()
        vignette = (
            row.get("clean_vignette")
            or row.get("vignette")
            or row.get("clinical_record")
            or base.get("vignette")
        )
        gold = (
            row.get("reference_diagnosis")
            or row.get("gold_diagnosis")
            or row.get("gold")
            or base.get("gold")
        )
        options = _options(row.get("source_options") or base.get("source_options"))
        gold_option = _surface(
            row.get("gold_option")
            or row.get("gold_letter")
            or base.get("gold_option")
        ).upper()
        metadata = {
            "case_key": case_key,
            "family": family,
            "vignette": clean_vignette(str(vignette or "")),
            "reference_diagnosis": _surface(gold),
            "source_options": options,
            "gold_option": gold_option,
        }
        if not family or not metadata["vignette"] or not metadata["reference_diagnosis"]:
            raise AssertionError(f"incomplete case metadata: {case_key}")
        if family == "DA" and (not options or gold_option not in options):
            raise AssertionError(f"incomplete DA option metadata: {case_key}")
        prior = result.get(case_key)
        if prior is not None and prior != metadata:
            raise AssertionError(f"conflicting metadata across arms: {case_key}")
        result[case_key] = metadata
    return result


def _consumed_relation_boundaries(relation: str) -> tuple[bool, bool]:
    """The only relation facts an endpoint reads: complete, and C-union-P."""
    return relation == "complete_equivalent", relation in COMPATIBLE_RELATIONS


def _merge_unique(
    index: dict[tuple[str, str], dict[str, Any]],
    key: tuple[str, str],
    decision: Mapping[str, Any],
    *,
    boundary_conflicts: dict[tuple[str, str], dict[str, Any]],
) -> None:
    prior = index.get(key)
    if prior is None:
        index[key] = dict(decision)
        return
    prior_relation = str(prior["relation"])
    new_relation = str(decision["relation"])
    if prior_relation == new_relation:
        return
    if _consumed_relation_boundaries(prior_relation) != _consumed_relation_boundaries(
        new_relation
    ):
        boundary_conflicts[key] = {
            "case_key": key[0],
            "canonical_prediction": key[1],
            "relations": sorted({prior_relation, new_relation}),
            "sources": sorted(
                {
                    str(prior.get("reuse_source") or ""),
                    str(decision.get("reuse_source") or ""),
                }
            ),
        }
        return
    # Fine-label-only divergence. The five-way taxonomy missed its C0 agreement
    # gate (0.7210 < 0.80) while both boundaries an endpoint reads still agree,
    # so the first source is kept and the divergence is carried as provenance.
    divergences = prior.setdefault("fine_label_divergence", [])
    if new_relation not in divergences:
        divergences.append(new_relation)


def load_clinical_reuse(
    bridge: FrozenExactSynonymBridge,
    *,
    c0_root: Path = C0_ROOT,
    migration_root: Path = MIGRATION_ROOT,
    audit: dict[str, Any] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Load C0 panel+occurrence decisions and migration final replay.

    Frozen sources that disagree on a boundary an endpoint reads are dropped so
    the online panel re-adjudicates them; fine-label-only divergence is kept.
    """
    result: dict[tuple[str, str], dict[str, Any]] = {}
    boundary_conflicts: dict[tuple[str, str], dict[str, Any]] = {}
    occurrence_ids = {
        str(row["relation_id"])
        for row in read_jsonl(Path(c0_root) / "design/occurrence_ledger.jsonl")
        if row.get("relation_id")
    }
    for row in read_jsonl(
        Path(c0_root) / "panel/three_model_adjudicated_panel.jsonl"
    ):
        relation_id = str(row.get("relation_id") or "")
        if relation_id not in occurrence_ids:
            continue
        label = _surface(row.get("candidate_label"))
        if not label:
            continue
        key = relation_key(str(row["case_key"]), label, bridge)
        _merge_unique(
            result,
            key,
            {
                "relation": str(
                    row.get("final_relation")
                    or row.get("model_panel_relation")
                    or "uncertain"
                ),
                "reuse_source": "c0_three_model_panel_with_occurrence_ledger",
                "reuse_relation_id": relation_id,
                "truth_tier": str(row.get("truth_tier") or "model_panel_sensitivity"),
                "matched_surface": label,
            },
            boundary_conflicts=boundary_conflicts,
        )
    migration_path = Path(migration_root) / "final/five_endpoint_replay.jsonl"
    for row in read_jsonl(migration_path):
        if not row.get("served") or not row.get("clinical_relation"):
            continue
        label = _surface(row.get("prediction_pre_projection"))
        key = relation_key(str(row["case_key"]), label, bridge)
        _merge_unique(
            result,
            key,
            {
                "relation": str(row["clinical_relation"]),
                "reuse_source": "all_arm_endpoint_migration_final_replay",
                "reuse_relation_id": str(row.get("relation_id") or ""),
                "truth_tier": "model_panel_sensitivity_not_human_root",
                "matched_surface": label,
            },
            boundary_conflicts=boundary_conflicts,
        )
    for key in boundary_conflicts:
        result.pop(key, None)
    if audit is not None:
        audit["clinical_boundary_conflicts"] = sorted(
            boundary_conflicts.values(),
            key=lambda row: (row["case_key"], row["canonical_prediction"]),
        )
        audit["n_clinical_boundary_conflicts"] = len(boundary_conflicts)
        audit["n_clinical_fine_label_divergent"] = sum(
            1 for row in result.values() if row.get("fine_label_divergence")
        )
    return result


def load_task_reuse(
    bridge: FrozenExactSynonymBridge,
    *,
    migration_root: Path = MIGRATION_ROOT,
    audit: dict[str, Any] | None = None,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Join migration cards, private index, and task results under strict keys.

    A key whose frozen results disagree on the official task outcome is dropped
    so the official task model re-scores it online.
    """
    root = Path(migration_root)
    cards = {
        str(row["blind_task_id"]): row
        for row in read_jsonl(root / "design/blinded_task_cards.jsonl")
    }
    results = {
        str(row["task_id"]): row
        for row in read_jsonl(root / "task_evaluator/task_results.jsonl")
        if row.get("success")
    }
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    conflicts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index_row in read_jsonl(root / "design/task_index.jsonl"):
        task_id = str(index_row["task_id"])
        result = results.get(task_id)
        card = cards.get(str(index_row["blind_task_id"]))
        if result is None or card is None:
            continue
        candidate = next(
            (
                item
                for item in card.get("candidate_registry") or []
                if str(item.get("candidate_id")) == str(index_row["candidate_id"])
            ),
            None,
        )
        if candidate is None:
            raise AssertionError(f"migration task candidate missing: {task_id}")
        prediction = _surface(candidate.get("label"))
        family = str(index_row["benchmark_family"]).upper()
        key = task_key(family, str(index_row["case_key"]), prediction, bridge)
        record = {
            **dict(result),
            "reuse_source": "all_arm_endpoint_migration_task_evaluator",
            "reuse_task_id": task_id,
            "matched_prediction": prediction,
            "match_rule": "exact_or_frozen_synonym_equivalent",
        }
        prior = output.get(key)
        if prior is not None and (
            bool(prior["task_correct"]) != bool(record["task_correct"])
            or str(prior.get("mapped_option")) != str(record.get("mapped_option"))
        ):
            conflicts[key] = {
                "family": key[0],
                "case_key": key[1],
                "canonical_prediction": key[2],
                "task_correct": sorted(
                    {bool(prior["task_correct"]), bool(record["task_correct"])}
                ),
                "mapped_option": sorted(
                    {
                        str(prior.get("mapped_option") or ""),
                        str(record.get("mapped_option") or ""),
                    }
                ),
            }
            continue
        output.setdefault(key, record)
    for key in conflicts:
        output.pop(key, None)
    if audit is not None:
        audit["task_outcome_conflicts"] = sorted(
            conflicts.values(),
            key=lambda row: (
                row["family"],
                row["case_key"],
                row["canonical_prediction"],
            ),
        )
        audit["n_task_outcome_conflicts"] = len(conflicts)
    return output


def _accepted_completions(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Best-effort compatibility reader for runner completion outputs."""
    containers: list[Any] = [row]
    for key in ("type_completion", "completion", "completion_result", "response"):
        if isinstance(row.get(key), Mapping):
            containers.append(row[key])
    raw: list[Any] = []
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        for key in (
            "accepted_completions",
            "accepted_completion",
            "completions",
            "completion_candidates",
        ):
            value = container.get(key)
            if isinstance(value, list):
                raw.extend(value)
            elif isinstance(value, Mapping):
                raw.append(value)
    frontier = row.get("frontier") or row.get("main_frontier") or []
    if isinstance(frontier, list):
        parent_labels = {
            str(item.get("candidate_id") or ""): _surface(item.get("label"))
            for item in frontier
            if isinstance(item, Mapping)
            and str(item.get("candidate_kind") or "parent") == "parent"
        }
        for item in frontier:
            if not isinstance(item, Mapping) or str(item.get("candidate_kind")) != "completion":
                continue
            axes = [str(axis) for axis in item.get("modifier_axes") or []]
            spans = item.get("raw_support_spans") or []
            raw.append(
                {
                    "accepted": True,
                    "completed_label": item.get("label"),
                    "parent_label": parent_labels.get(
                        str(item.get("parent_candidate_id") or ""), ""
                    ),
                    "modifiers": [
                        {
                            "axis": "|".join(axes),
                            "modifier": item.get("label"),
                            "support_span": (
                                span.get("text") if isinstance(span, Mapping) else span
                            ),
                        }
                        for span in spans
                    ],
                }
            )
    output: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        accepted = item.get("accepted")
        status = str(item.get("status") or "").lower()
        if accepted is False or (status and status not in {"accepted", "success", "kept"}):
            continue
        label = _surface(
            item.get("completed_label")
            or item.get("label")
            or item.get("candidate_label")
        )
        if not label:
            continue
        parent = _surface(
            item.get("parent_label")
            or item.get("source_label")
            or item.get("base_label")
        )
        modifiers: list[dict[str, str]] = []
        modifier_raw = item.get("modifiers") or item.get("modifier_support") or []
        if not modifier_raw and item.get("modifier_axes") and item.get("support_spans"):
            axes = [str(axis) for axis in item.get("modifier_axes") or []]
            modifier_raw = [
                {
                    "axis": "|".join(axes),
                    "modifier": label,
                    "support_span": (
                        span.get("text") if isinstance(span, Mapping) else span
                    ),
                }
                for span in item.get("support_spans") or []
            ]
        if isinstance(modifier_raw, Mapping):
            modifier_raw = [
                {"axis": axis, **(dict(value) if isinstance(value, Mapping) else {"modifier": value})}
                for axis, value in modifier_raw.items()
            ]
        for modifier in modifier_raw:
            if not isinstance(modifier, Mapping):
                continue
            value = _surface(
                modifier.get("modifier")
                or modifier.get("value")
                or modifier.get("label")
            )
            span = str(
                modifier.get("support_span")
                or modifier.get("span")
                or modifier.get("quote")
                or ""
            ).strip()
            if value or span:
                modifiers.append(
                    {
                        "axis": _surface(modifier.get("axis") or modifier.get("type")),
                        "modifier": value,
                        "support_span": span,
                    }
                )
        output.append(
            {
                "completed_label": label,
                "parent_label": parent,
                "modifiers": modifiers,
            }
        )
    unique: dict[str, dict[str, Any]] = {}
    for item in output:
        unique.setdefault(normalize_label(item["completed_label"]), item)
    return list(unique.values())


def _runner_modifier_gate(source: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Read an already-produced runner gate without reinterpreting its result."""
    candidates = (
        source.parent / "modifier_gate/summary.json",
        source.parent / "type_completion/modifier_gate_summary.json",
        source.parent / "modifier_gate_summary.json",
    )
    documents: list[dict[str, Any]] = []
    for path in candidates:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, Mapping):
                documents.append({**dict(value), "source_path": str(path)})
    for row in rows:
        for container in (
            row.get("modifier_gate"),
            (row.get("type_completion") or {}).get("modifier_gate")
            if isinstance(row.get("type_completion"), Mapping)
            else None,
        ):
            if isinstance(container, Mapping) and "gate_pass" in container:
                documents.append(
                    {
                        **dict(container),
                        "source_path": f"{source}#case_key={row.get('case_key')}",
                    }
                )
    if not documents:
        return None
    required = {
        "gate_pass",
        "literal_closure",
        "raw_agreement",
        "gwet_ac1",
        "hallucination_rate",
        "service_rate",
    }
    canonical: dict[str, Any] | None = None
    sources: list[str] = []
    for document in documents:
        if not required <= set(document):
            continue
        current = {key: document[key] for key in sorted(required)}
        if canonical is not None and current != canonical:
            raise AssertionError("conflicting runner modifier-gate summaries")
        canonical = current
        sources.append(str(document["source_path"]))
    if canonical is None:
        return None
    return {
        **canonical,
        "provenance": "runner_frozen_modifier_gate",
        "source_paths": sorted(set(sources)),
    }


def _ordered(
    namespace: str, case_key: str, rows: Iterable[Mapping[str, Any]], key: str
) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            stable_seed(namespace, case_key, str(row[key])),
            str(row[key]),
        ),
    )


def build_da_online_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    """Public helper used to audit that DA gold never enters online payloads."""
    payload = {
        "blind_task_id": str(card["blind_task_id"]),
        "clinical_record": str(card["clinical_record"]),
        "source_options": dict(card["source_options"]),
        "candidate_registry": [dict(row) for row in card["candidate_registry"]],
    }
    forbidden = {"gold", "gold_option", "gold_letter", "right_option"}
    if any(str(key).lower() in forbidden for key in payload):
        raise AssertionError("DA online payload contains gold")
    return payload


def prepare(source: Path, out: Path) -> dict[str, Any]:
    source, out = Path(source).resolve(), Path(out).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    rows = read_jsonl(source)
    if not rows:
        raise AssertionError("CoreLift source is empty")
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    metadata = _case_metadata(rows)
    # Re-entry must fail before any design artifact is touched.
    prereg_path = out / "design/preregistration.json"
    if prereg_path.is_file():
        previous = json.loads(prereg_path.read_text(encoding="utf-8"))
        early_contract = {
            "source_path": str(source),
            "source_sha256": file_sha256(source),
            "case_keys": sorted(metadata),
            "arms_observed": sorted(
                {
                    str(row.get("arm") or row.get("arm_id") or "")
                    for row in rows
                }
            ),
            "prompts": _frozen_prompt_hashes(),
            "models": {
                "task": TASK_MODEL,
                "clinical_reviewers": CLINICAL_REVIEWERS,
                "modifier_reviewers": MODIFIER_REVIEWERS,
            },
        }
        for key, value in early_contract.items():
            if previous.get(key) != value:
                raise AssertionError(
                    f"frozen preregistration drift in {key}; refusing mutation"
                )
    reuse_audit: dict[str, Any] = {}
    clinical_reuse = load_clinical_reuse(bridge, audit=reuse_audit)
    task_reuse = load_task_reuse(bridge, audit=reuse_audit)
    design = out / "design"
    design.mkdir(parents=True, exist_ok=True)

    normalized_rows: list[dict[str, Any]] = []
    relation_surfaces: dict[tuple[str, str], str] = {}
    relation_links: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    task_surfaces: dict[tuple[str, str, str], str] = {}
    for source_row in rows:
        row = dict(source_row)
        case_key = str(row["case_key"])
        family = str(row.get("family") or metadata[case_key]["family"]).upper()
        arm = str(row.get("arm") or row.get("arm_id") or "")
        if not arm:
            raise AssertionError(f"row missing arm: {case_key}")
        success = bool(row.get("success"))
        champion = _surface(
            row.get("champion_label")
            or row.get("prediction")
            or row.get("top1_diagnosis")
        )
        served = bool(success and champion)
        labels = _labels_from_pool(row) if served else []
        row_id = _stable_id("corelift-row-v1", case_key, arm)
        completions = _accepted_completions(row)
        normalized = {
            **row,
            "row_id": row_id,
            "case_key": case_key,
            "family": family,
            "arm": arm,
            "success": success,
            "served": served,
            "champion_label": champion,
            "main_pool_labels": labels,
            "main_pool_width": len(labels),
            "source_option_n": (
                len(metadata[case_key]["source_options"]) if family == "DA" else None
            ),
            "accepted_completions": completions,
        }
        if served:
            champion_key = relation_key(case_key, champion, bridge)
            normalized["champion_relation_key"] = list(champion_key)
            normalized["task_key"] = list(task_key(family, case_key, champion, bridge))
            task_surfaces.setdefault(tuple(normalized["task_key"]), champion)
            for label in labels:
                key = relation_key(case_key, label, bridge)
                prior = relation_surfaces.get(key)
                if prior is None or (len(label), label) < (len(prior), prior):
                    relation_surfaces[key] = label
                relation_links[key].append(
                    {"row_id": row_id, "arm": arm, "label": label}
                )
        normalized_rows.append(normalized)

    matrix = Counter(
        (str(row["family"]), str(row["arm"])) for row in normalized_rows
    )
    if (
        len(normalized_rows) != 4_000
        or len(metadata) != 800
        or set(matrix) != {
            (family, arm) for family in ("DA", "MCR") for arm in ARMS
        }
        or any(count != 400 for count in matrix.values())
        or any(
            Counter(
                str(row["arm"])
                for row in normalized_rows
                if str(row["case_key"]) == case_key
            )
            != Counter(ARMS)
            for case_key in metadata
        )
    ):
        raise AssertionError(
            "CoreLift source must be a rectangular 800-case x 5-arm matrix "
            "with n=400 per family/arm"
        )

    relation_index: list[dict[str, Any]] = []
    novel_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key, label in sorted(relation_surfaces.items()):
        case_key, canonical = key
        reuse = clinical_reuse.get(key)
        if reuse is None and bridge.equivalent(
            label, metadata[case_key]["reference_diagnosis"]
        ):
            reuse = {
                "relation": "complete_equivalent",
                "reuse_source": "deterministic_frozen_safe_exact",
                "reuse_relation_id": "",
                "truth_tier": "deterministic_exact",
                "matched_surface": metadata[case_key]["reference_diagnosis"],
            }
        relation_id = _stable_id("corelift-relation-v1", case_key, canonical)
        item = {
            "relation_id": relation_id,
            "case_key": case_key,
            "canonical_prediction": canonical,
            "candidate_label": label,
            "status": "reused" if reuse else "novel",
            "relation": reuse.get("relation") if reuse else None,
            "reuse_provenance": dict(reuse) if reuse else None,
            "occurrences": relation_links[key],
        }
        relation_index.append(item)
        if reuse is None:
            novel_by_case[case_key].append(item)

    clinical_cards: list[dict[str, Any]] = []
    clinical_private_index: list[dict[str, Any]] = []
    for number, case_key in enumerate(sorted(novel_by_case), 1):
        blind_case_id = f"CLC{number:04d}"
        ordered = _ordered(
            "corelift-clinical-order-v1",
            case_key,
            novel_by_case[case_key],
            "relation_id",
        )
        registry: list[dict[str, str]] = []
        for candidate_number, item in enumerate(ordered, 1):
            candidate_id = f"C{candidate_number:03d}"
            registry.append(
                {"candidate_id": candidate_id, "label": item["candidate_label"]}
            )
            clinical_private_index.append(
                {
                    "blind_case_id": blind_case_id,
                    "candidate_id": candidate_id,
                    "relation_id": item["relation_id"],
                }
            )
        clinical_cards.append(
            {
                "blind_case_id": blind_case_id,
                "clinical_record": metadata[case_key]["vignette"],
                "reference_diagnosis": metadata[case_key]["reference_diagnosis"],
                "candidate_registry": registry,
            }
        )

    task_index: list[dict[str, Any]] = []
    fresh_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    task_reuse_rows: list[dict[str, Any]] = []
    for key, prediction in sorted(task_surfaces.items()):
        family, case_key, canonical = key
        task_id = _stable_id("corelift-task-v1", family, case_key, canonical)
        reused = task_reuse.get(key)
        index_row = {
            "task_id": task_id,
            "family": family,
            "case_key": case_key,
            "canonical_prediction": canonical,
            "prediction": prediction,
            "status": "reused" if reused else "fresh",
            # Private isolated index only; never copied into the DA card.
            "gold_option": metadata[case_key]["gold_option"] if family == "DA" else "",
        }
        task_index.append(index_row)
        if reused:
            task_reuse_rows.append(
                {
                    **dict(reused),
                    "task_id": task_id,
                    "family": family,
                    "prediction": prediction,
                }
            )
        else:
            fresh_by_case[case_key].append(index_row)

    task_cards: list[dict[str, Any]] = []
    task_card_index: list[dict[str, str]] = []
    for number, case_key in enumerate(sorted(fresh_by_case), 1):
        blind_task_id = f"CLT{number:04d}"
        ordered = _ordered(
            "corelift-task-order-v1", case_key, fresh_by_case[case_key], "task_id"
        )
        registry = []
        for candidate_number, item in enumerate(ordered, 1):
            candidate_id = f"T{candidate_number:03d}"
            registry.append({"candidate_id": candidate_id, "label": item["prediction"]})
            task_card_index.append(
                {
                    "blind_task_id": blind_task_id,
                    "candidate_id": candidate_id,
                    "task_id": item["task_id"],
                }
            )
        family = metadata[case_key]["family"]
        card: dict[str, Any] = {
            "blind_task_id": blind_task_id,
            "family": family,
            "candidate_registry": registry,
        }
        if family == "DA":
            card["clinical_record"] = metadata[case_key]["vignette"]
            card["source_options"] = metadata[case_key]["source_options"]
            build_da_online_payload(card)
        else:
            card["actual_diagnosis"] = metadata[case_key]["reference_diagnosis"]
        task_cards.append(card)

    modifier_cards: list[dict[str, Any]] = []
    modifier_index: list[dict[str, str]] = []
    completion_counter = 0
    for row in normalized_rows:
        vignette = metadata[row["case_key"]]["vignette"]
        for completion in row["accepted_completions"]:
            completion_counter += 1
            completion_id = _stable_id(
                "corelift-completion-v1",
                row["case_key"],
                row["arm"],
                completion["completed_label"],
            )
            modifiers = []
            for number, modifier in enumerate(completion["modifiers"], 1):
                modifier_id = f"M{number:03d}"
                span = modifier["support_span"]
                modifiers.append(
                    {
                        "modifier_id": modifier_id,
                        **modifier,
                        "literal_span_closed": bool(span and span in vignette),
                    }
                )
                modifier_index.append(
                    {
                        "completion_id": completion_id,
                        "modifier_id": modifier_id,
                        "row_id": row["row_id"],
                    }
                )
            if modifiers:
                modifier_cards.append(
                    {
                        "blind_completion_id": f"CLM{completion_counter:05d}",
                        "completion_id": completion_id,
                        "clinical_record": vignette,
                        "parent_label": completion["parent_label"],
                        "completed_label": completion["completed_label"],
                        "modifiers": modifiers,
                    }
                )

    write_jsonl(design / "intention_ledger.jsonl", normalized_rows)
    write_jsonl(design / "relation_index.jsonl", relation_index)
    write_jsonl(design / "blinded_clinical_cards.jsonl", clinical_cards)
    write_jsonl(design / "clinical_private_index.jsonl", clinical_private_index)
    write_jsonl(design / "task_index.jsonl", task_index)
    write_jsonl(design / "blinded_task_cards.jsonl", task_cards)
    write_jsonl(design / "task_card_index.jsonl", task_card_index)
    write_jsonl(design / "reused_task_results.jsonl", task_reuse_rows)
    write_jsonl(design / "modifier_cards.jsonl", modifier_cards)
    write_jsonl(design / "modifier_private_index.jsonl", modifier_index)
    runner_gate = _runner_modifier_gate(source, rows)
    if runner_gate is not None:
        atomic_json(design / "runner_modifier_gate_summary.json", runner_gate)
    reuse_audit["schema_version"] = "corelift-reuse-audit-v1"
    reuse_audit["policy"] = (
        "Frozen reuse is dropped when two sources disagree on a boundary an "
        "endpoint reads (complete, or complete-or-compatible-partial) or on the "
        "official task outcome; such keys are re-adjudicated online. "
        "Fine-label-only divergence is retained as provenance because the "
        "five-way taxonomy missed its C0 agreement gate."
    )
    atomic_json(design / "frozen_reuse_audit.json", reuse_audit)

    prereg = {
        "schema_version": "corelift-preregistration-v1",
        "experiment_id": EXPERIMENT_ID,
        "source_path": str(source),
        "source_sha256": file_sha256(source),
        "case_keys": sorted(metadata),
        "arms_observed": sorted({str(row["arm"]) for row in normalized_rows}),
        "prompts": _frozen_prompt_hashes(),
        "models": {
            "task": TASK_MODEL,
            "clinical_reviewers": CLINICAL_REVIEWERS,
            "modifier_reviewers": MODIFIER_REVIEWERS,
        },
        "endpoints": [
            "DA Acc@N/option accuracy",
            "MCR Prompt-7 Acc",
            "clinical_complete",
            "complete_or_compatible_partial",
            "pool_complete_exposure",
            "pool_complete_or_partial_exposure",
            "conditional_conversion",
        ],
        "contrasts": [list(row) for row in CONTRASTS],
        "multiplicity": (
            "Holm separately within benchmark family x endpoint; "
            "DA and MCR official task are never pooled"
        ),
        "failure_policy": "ITA failures retained as zero",
        "gate_thresholds": {
            "literal_closure": 1.0,
            "raw_agreement": 0.85,
            "gwet_ac1": 0.70,
            "hallucination_max": 0.10,
            "service_min": 0.95,
        },
        "development_not_confirmation": True,
    }
    if prereg_path.is_file():
        previous = json.loads(prereg_path.read_text(encoding="utf-8"))
        if previous != prereg:
            raise AssertionError("frozen preregistration drift; refusing overwrite")
    else:
        atomic_json(prereg_path, prereg)
    protocol = (
        "# CoreLift evaluation protocol\n\n"
        "Frozen development-set evaluation. Clinical decisions are a three-model "
        "panel sensitivity, not human-root truth. DA option projection and MCR "
        "Prompt-7 are distinct official task endpoints and are never pooled. "
        "Failures remain zero in the intended denominator. B1 clinical-confirmatory "
        "inference is withheld if the modifier gate fails; official B1 task results "
        "remain reportable.\n"
    )
    protocol_path = design / "PROTOCOL.md"
    if protocol_path.is_file() and protocol_path.read_text(encoding="utf-8") != protocol:
        raise AssertionError("frozen protocol drift; refusing overwrite")
    protocol_path.write_text(protocol, encoding="utf-8")
    summary = {
        "schema_version": "corelift-prepare-v1",
        "created_at_utc": utcnow(),
        "source_sha256": prereg["source_sha256"],
        "n_rows": len(normalized_rows),
        "n_cases": len(metadata),
        "n_relations": len(relation_index),
        "n_relations_reused": sum(row["status"] == "reused" for row in relation_index),
        "n_relations_novel": sum(row["status"] == "novel" for row in relation_index),
        "n_task_semantics": len(task_index),
        "n_task_reused": len(task_reuse_rows),
        "n_task_fresh": len(task_index) - len(task_reuse_rows),
        "n_modifier_cards": len(modifier_cards),
        "n_clinical_boundary_conflicts": reuse_audit["n_clinical_boundary_conflicts"],
        "n_clinical_fine_label_divergent": reuse_audit[
            "n_clinical_fine_label_divergent"
        ],
        "n_task_outcome_conflicts": reuse_audit["n_task_outcome_conflicts"],
    }
    atomic_json(design / "prepare_summary.json", summary)
    return summary


def _validate_relation_response(
    response: Mapping[str, Any], allowed: set[str]
) -> str | None:
    rows = response.get("candidate_relations")
    if not isinstance(rows, list):
        return "candidate_relations must be a list"
    identifiers = [str(row.get("candidate_id") or "") for row in rows if isinstance(row, Mapping)]
    if len(identifiers) != len(allowed) or set(identifiers) != allowed:
        return "candidate_relations must cover every candidate exactly once"
    for row in rows:
        if str(row.get("relation")) not in RELATIONS:
            return "invalid clinical relation"
        if not _surface(row.get("reason")):
            return "clinical reason required"
    return None


def run_reviewer(
    out: Path, reviewer_id: str, model: str, workers: int, *, cache_only: bool = False
) -> dict[str, Any]:
    expected_model = CLINICAL_REVIEWERS.get(reviewer_id)
    if expected_model is None or model != expected_model:
        raise AssertionError(
            f"{reviewer_id} must use frozen clinical model {expected_model!r}"
        )
    cards = read_jsonl(Path(out) / "design/blinded_clinical_cards.jsonl")
    directory = Path(out) / "reviewers" / reviewer_id
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )

    def one(card: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "blind_case_id": card["blind_case_id"],
            "clinical_record": card["clinical_record"],
            "reference_diagnosis": card["reference_diagnosis"],
            "candidate_registry": card["candidate_registry"],
        }
        allowed = {str(row["candidate_id"]) for row in card["candidate_registry"]}
        try:
            outcome = caller.call(
                module=f"CoreLiftClinical_{reviewer_id}",
                prompt=CLINICAL_PROMPT,
                payload=payload,
                validator=lambda value: _validate_relation_response(value, allowed),
                cache_only=cache_only,
            )
            return {
                "blind_case_id": card["blind_case_id"],
                "success": outcome.success,
                "error": outcome.error,
                "review": outcome.response,
                "cache_hit": outcome.cache_hit,
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        except Exception as exc:
            return {
                "blind_case_id": card["blind_case_id"],
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "review": {},
                "cache_hit": False,
                "cache_key": "",
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=validate_workers(workers, rag=False)) as pool:
        futures = [pool.submit(one, card) for card in cards]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: str(row["blind_case_id"]))
    write_jsonl(directory / "reviews.jsonl", results)
    summary = {
        "reviewer_id": reviewer_id,
        "model": model,
        "n_cards": len(cards),
        "n_success": sum(bool(row["success"]) for row in results),
        "n_failure": sum(not bool(row["success"]) for row in results),
    }
    atomic_json(directory / "summary.json", summary)
    return summary


def majority_relation(votes: Sequence[str]) -> tuple[str, str]:
    counts = Counter(str(vote) for vote in votes if str(vote) in RELATIONS)
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    if ordered and ordered[0][1] >= 2:
        return ordered[0][0], "unanimous" if ordered[0][1] == 3 else "majority"
    return "uncertain", "unresolved"


def agreement_gwet_ac1(ratings: Sequence[Sequence[bool]]) -> dict[str, Any]:
    """Multi-rater binary raw pair agreement and Gwet AC1."""
    valid = [list(map(bool, row)) for row in ratings if len(row) >= 2]
    if not valid:
        return {"n_items": 0, "raw_agreement": None, "gwet_ac1": None}
    agreements = [
        sum(a == b for index, a in enumerate(row) for b in row[index + 1 :])
        / math.comb(len(row), 2)
        for row in valid
    ]
    observed = sum(agreements) / len(agreements)
    total_ratings = sum(len(row) for row in valid)
    prevalence = sum(sum(row) for row in valid) / total_ratings
    chance = 2 * prevalence * (1 - prevalence)
    ac1 = (observed - chance) / (1 - chance) if chance < 1 else 1.0
    return {
        "n_items": len(valid),
        "raw_agreement": observed,
        "gwet_ac1": ac1,
        "positive_prevalence": prevalence,
    }


def compile_panel(
    out: Path, reviewer_ids: Sequence[str] = tuple(CLINICAL_REVIEWERS)
) -> dict[str, Any]:
    out = Path(out)
    private = {
        (str(row["blind_case_id"]), str(row["candidate_id"])): str(row["relation_id"])
        for row in read_jsonl(out / "design/clinical_private_index.jsonl")
    }
    votes: dict[str, list[str]] = defaultdict(list)
    for reviewer_id in reviewer_ids:
        summary_path = out / "reviewers" / reviewer_id / "summary.json"
        run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if run_summary.get("model") != CLINICAL_REVIEWERS.get(reviewer_id):
            raise AssertionError(f"frozen reviewer model drift: {reviewer_id}")
        rows = read_jsonl(out / "reviewers" / reviewer_id / "reviews.jsonl")
        if any(not row.get("success") for row in rows):
            raise AssertionError(f"incomplete reviewer: {reviewer_id}")
        for case in rows:
            for decision in case["review"]["candidate_relations"]:
                key = (str(case["blind_case_id"]), str(decision["candidate_id"]))
                if key not in private:
                    raise AssertionError(f"review candidate absent from index: {key}")
                votes[private[key]].append(str(decision["relation"]))
    expected = {
        str(row["relation_id"])
        for row in read_jsonl(out / "design/relation_index.jsonl")
        if row["status"] == "novel"
    }
    if set(votes) != expected or any(len(value) != 3 for value in votes.values()):
        raise AssertionError("three-reviewer clinical panel coverage incomplete")
    panel = []
    binary_ratings = []
    for relation_id in sorted(expected):
        relation, status = majority_relation(votes[relation_id])
        binary_ratings.append(
            [vote == "complete_equivalent" for vote in votes[relation_id]]
        )
        panel.append(
            {
                "relation_id": relation_id,
                "reviewer_votes": votes[relation_id],
                "vote_counts": dict(sorted(Counter(votes[relation_id]).items())),
                "relation": relation,
                "panel_status": status,
                "provenance": "three_model_panel_sensitivity_not_human_root",
            }
        )
    directory = out / "panel"
    write_jsonl(directory / "panel_decisions.jsonl", panel)
    summary = {
        "reviewers": list(reviewer_ids),
        "n_relations": len(panel),
        "n_unresolved": sum(row["panel_status"] == "unresolved" for row in panel),
        "complete_boundary_agreement": agreement_gwet_ac1(binary_ratings),
        "truth_warning": "model-panel sensitivity; not human-root",
    }
    atomic_json(directory / "summary.json", summary)
    return summary


class _MapperAdapter:
    def __init__(self, caller: OnlineJSONCaller, cache_only: bool) -> None:
        self.caller, self.cache_only = caller, cache_only
        self.calls: list[dict[str, Any]] = []

    def call_module(
        self, module: str, prompt: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        outcome = self.caller.call(
            module=f"CoreLiftTask_{module}",
            prompt=prompt,
            payload=dict(payload),
            cache_only=self.cache_only,
        )
        self.calls.append(
            {
                "module": module,
                "cache_key": outcome.cache_key,
                "cache_hit": outcome.cache_hit,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        )
        if not outcome.success:
            raise ValueError(outcome.error)
        return outcome.response


@contextmanager
def _call_scope(adapter: _MapperAdapter) -> Iterable[list[dict[str, Any]]]:
    adapter.calls.clear()
    try:
        yield adapter.calls
    finally:
        adapter.calls.clear()


def _validate_mcr(response: Mapping[str, Any]) -> str | None:
    if str(response.get("answer") or "").lower() not in {"y", "n"}:
        return "answer must be y or n"
    if not _surface(response.get("reason")):
        return "reason required"
    return None


def run_task(
    out: Path,
    model: str = TASK_MODEL,
    workers: int = 50,
    *,
    cache_only: bool = False,
) -> dict[str, Any]:
    """Run fresh DA mapper and exact frozen MCR Prompt-7; join DA gold offline."""
    if model != TASK_MODEL:
        raise AssertionError(f"official task model must remain {TASK_MODEL}")
    from agentclinic_tree_dx.answer_projection_mapper import (
        RelationAwareAnswerMapper,
        load_offline_resolver,
    )

    out = Path(out)
    cards = read_jsonl(out / "design/blinded_task_cards.jsonl")
    links = read_jsonl(out / "design/task_card_index.jsonl")
    link_by_pair = {
        (str(row["blind_task_id"]), str(row["candidate_id"])): str(row["task_id"])
        for row in links
    }
    task_specs: list[dict[str, Any]] = []
    for card in cards:
        for candidate in card["candidate_registry"]:
            task_specs.append(
                {
                    "task_id": link_by_pair[
                        (str(card["blind_task_id"]), str(candidate["candidate_id"]))
                    ],
                    "family": str(card["family"]),
                    "prediction": str(candidate["label"]),
                    "card": card,
                }
            )
    directory = out / "task_evaluator"
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )
    relation_prompt = (
        ROOT / "src/agentclinic_tree_dx/prompts/answer_relation_mapper.txt"
    ).read_text(encoding="utf-8")
    strict_prompt = (
        ROOT / "src/agentclinic_tree_dx/prompts/answer_option_strict_total_order.txt"
    ).read_text(encoding="utf-8")
    base_resolver = load_offline_resolver(ROOT)

    def mapper_pair() -> tuple[Any, Any, _MapperAdapter]:
        resolver = copy.copy(base_resolver)
        resolver._source_keys = {}
        resolver._source_tokens = {}
        resolver._cache = {}
        deterministic = RelationAwareAnswerMapper(resolver=resolver)
        adapter = _MapperAdapter(caller, cache_only)
        typed = RelationAwareAnswerMapper(
            resolver=resolver,
            llm=adapter,
            relation_prompt=relation_prompt,
            strict_order_prompt=strict_prompt,
            strict_total_order=True,
        )
        return deterministic, typed, adapter

    def one(spec: Mapping[str, Any]) -> dict[str, Any]:
        family, prediction = str(spec["family"]), str(spec["prediction"])
        try:
            if family == "MCR":
                payload = {
                    "predicted_diagnosis": prediction,
                    "actual_diagnosis": str(spec["card"]["actual_diagnosis"]),
                }
                outcome = caller.call(
                    module="CoreLiftTask_MCRPrompt7JSONEnvelopeV1",
                    prompt=MCR_PROMPT7,
                    payload=payload,
                    validator=_validate_mcr,
                    cache_only=cache_only,
                )
                return {
                    "task_id": spec["task_id"],
                    "family": family,
                    "success": outcome.success,
                    "task_correct": (
                        str(outcome.response.get("answer")).lower() == "y"
                        if outcome.success
                        else False
                    ),
                    "mapped_option": None,
                    "method": "mcr_prompt7_json_envelope_v1",
                    "projection_sha256": canonical_sha256(outcome.response),
                    "call_provenance": [{"cache_key": outcome.cache_key}],
                    "error": outcome.error,
                }
            payload = build_da_online_payload(spec["card"])
            options = {
                str(letter).upper(): str(text)
                for letter, text in payload["source_options"].items()
            }
            leaves = [
                {
                    "leaf_id": "pred_1",
                    "leaf_label": prediction,
                    "parent_id": "",
                    "parent_label": "",
                    "joint_rank": 1,
                    "posterior": 1.0,
                }
            ]
            deterministic, typed, adapter = mapper_pair()
            provenance: list[dict[str, Any]] = []
            with _call_scope(adapter) as calls:
                projection = deterministic.map(
                    case_id=str(spec["task_id"]),
                    vignette=str(payload["clinical_record"]),
                    question="What is the most likely diagnosis?",
                    options=options,
                    leaves=leaves,
                    mode="deterministic_gold_blind",
                )
                matched = [
                    str(letter).upper()
                    for letter, item in projection["option_maps"].items()
                    if item.get("best_rank") is not None or bool(item.get("matched"))
                ]
                if len(matched) == 1:
                    mapped, method = matched[0], "da_relation_mapper_deterministic_unique_v1"
                else:
                    projection = typed.map(
                        case_id=str(spec["task_id"]),
                        vignette=str(payload["clinical_record"]),
                        question="What is the most likely diagnosis?",
                        options=options,
                        leaves=leaves,
                        mode="typed_llm",
                    )
                    order = list(projection.get("option_order") or [])
                    mapped = str(order[0]).upper() if order else "NONE"
                    method = "da_relation_mapper_typed_strict_total_order_v1"
                provenance = [dict(row) for row in calls]
            return {
                "task_id": spec["task_id"],
                "family": family,
                "success": True,
                "task_correct": None,
                "mapped_option": mapped,
                "method": method,
                "projection_sha256": canonical_sha256(projection),
                "call_provenance": provenance,
                "error": "",
            }
        except Exception as exc:
            return {
                "task_id": spec["task_id"],
                "family": family,
                "success": False,
                "task_correct": False,
                "mapped_option": None,
                "method": "",
                "projection_sha256": "",
                "call_provenance": [],
                "error": f"{type(exc).__name__}: {exc}",
            }

    fresh: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=validate_workers(workers, rag=False)) as pool:
        futures = [pool.submit(one, spec) for spec in task_specs]
        for future in as_completed(futures):
            fresh.append(future.result())
    gold = {
        str(row["task_id"]): str(row["gold_option"]).upper()
        for row in read_jsonl(out / "design/task_index.jsonl")
        if row["family"] == "DA"
    }
    for row in fresh:
        if row["family"] == "DA" and row["success"]:
            row["task_correct"] = row["mapped_option"] == gold[row["task_id"]]
            row["gold_join_stage"] = "offline_after_projection"
    combined = read_jsonl(out / "design/reused_task_results.jsonl") + fresh
    combined.sort(key=lambda row: str(row["task_id"]))
    write_jsonl(directory / "task_results.jsonl", combined)
    summary = {
        "model": model,
        "n_tasks": len(combined),
        "n_reused": len(combined) - len(fresh),
        "n_fresh": len(fresh),
        "n_success": sum(bool(row["success"]) for row in combined),
        "da_gold_join_stage": "offline_after_projection",
        "mcr_prompt_sha256": hashlib.sha256(MCR_PROMPT7.encode()).hexdigest(),
    }
    atomic_json(directory / "summary.json", summary)
    return summary


def _validate_modifier(
    response: Mapping[str, Any], allowed: set[str]
) -> str | None:
    rows = response.get("judgments")
    if not isinstance(rows, list):
        return "judgments must be a list"
    ids = [str(row.get("modifier_id") or "") for row in rows if isinstance(row, Mapping)]
    if len(ids) != len(allowed) or set(ids) != allowed:
        return "judgments must cover every modifier exactly once"
    if any(not isinstance(row.get("supported"), bool) for row in rows):
        return "supported must be boolean"
    return None


def run_modifier_reviewer(
    out: Path, reviewer_id: str, model: str, workers: int, *, cache_only: bool = False
) -> dict[str, Any]:
    expected_model = MODIFIER_REVIEWERS.get(reviewer_id)
    if expected_model is None or model != expected_model:
        raise AssertionError(
            f"{reviewer_id} must use frozen modifier model {expected_model!r}"
        )
    cards = read_jsonl(Path(out) / "design/modifier_cards.jsonl")
    directory = Path(out) / "modifier_reviewers" / reviewer_id
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )

    def one(card: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "blind_completion_id": card["blind_completion_id"],
            "clinical_record": card["clinical_record"],
            "parent_label": card["parent_label"],
            "completed_label": card["completed_label"],
            "modifiers": [
                {
                    "modifier_id": row["modifier_id"],
                    "axis": row["axis"],
                    "modifier": row["modifier"],
                    "support_span": row["support_span"],
                }
                for row in card["modifiers"]
            ],
        }
        allowed = {str(row["modifier_id"]) for row in card["modifiers"]}
        try:
            outcome = caller.call(
                module=f"CoreLiftModifierGate_{reviewer_id}",
                prompt=MODIFIER_PROMPT,
                payload=payload,
                validator=lambda value: _validate_modifier(value, allowed),
                cache_only=cache_only,
            )
            return {
                "blind_completion_id": card["blind_completion_id"],
                "success": outcome.success,
                "review": outcome.response,
                "error": outcome.error,
                "cache_key": outcome.cache_key,
            }
        except Exception as exc:
            return {
                "blind_completion_id": card["blind_completion_id"],
                "success": False,
                "review": {},
                "error": f"{type(exc).__name__}: {exc}",
                "cache_key": "",
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=validate_workers(workers, rag=False)) as pool:
        futures = [pool.submit(one, card) for card in cards]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: str(row["blind_completion_id"]))
    write_jsonl(directory / "reviews.jsonl", results)
    summary = {
        "reviewer_id": reviewer_id,
        "model": model,
        "n_cards": len(cards),
        "n_success": sum(bool(row["success"]) for row in results),
    }
    atomic_json(directory / "summary.json", summary)
    return summary


def compile_modifier_gate(
    out: Path, reviewer_ids: Sequence[str] = tuple(MODIFIER_REVIEWERS)
) -> dict[str, Any]:
    out = Path(out)
    runner_gate_path = out / "design/runner_modifier_gate_summary.json"
    if runner_gate_path.is_file():
        summary = json.loads(runner_gate_path.read_text(encoding="utf-8"))
        summary["reused_without_new_calls"] = True
        atomic_json(out / "modifier_gate/summary.json", summary)
        return summary
    cards = read_jsonl(out / "design/modifier_cards.jsonl")
    card_by_blind = {str(row["blind_completion_id"]): row for row in cards}
    votes: dict[tuple[str, str], list[bool]] = defaultdict(list)
    successful_cards: dict[str, set[str]] = defaultdict(set)
    for reviewer_id in reviewer_ids:
        summary_path = out / "modifier_reviewers" / reviewer_id / "summary.json"
        run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if run_summary.get("model") != MODIFIER_REVIEWERS.get(reviewer_id):
            raise AssertionError(f"frozen modifier model drift: {reviewer_id}")
        for row in read_jsonl(
            out / "modifier_reviewers" / reviewer_id / "reviews.jsonl"
        ):
            if not row.get("success"):
                continue
            blind_id = str(row["blind_completion_id"])
            successful_cards[reviewer_id].add(blind_id)
            for judgment in row["review"]["judgments"]:
                votes[(blind_id, str(judgment["modifier_id"]))].append(
                    bool(judgment["supported"])
                )
    expected = [
        (str(card["blind_completion_id"]), str(modifier["modifier_id"]))
        for card in cards
        for modifier in card["modifiers"]
    ]
    ratings = [votes.get(key, []) for key in expected if len(votes.get(key, [])) == 2]
    agreement = agreement_gwet_ac1(ratings)
    accepted = [
        completion
        for row in read_jsonl(out / "design/intention_ledger.jsonl")
        for completion in row.get("accepted_completions") or []
    ]
    without_modifiers = sum(not completion.get("modifiers") for completion in accepted)
    literal_n = sum(
        bool(modifier["literal_span_closed"])
        for card in cards
        for modifier in card["modifiers"]
    )
    total = len(expected)
    service_n = len(ratings)
    unsupported = sum(not all(row) for row in ratings)
    metrics = {
        "n_accepted_completions": len(accepted),
        "n_accepted_completions_without_modifiers": without_modifiers,
        "n_modifiers": total,
        "n_two_reviewer_served": service_n,
        "literal_closure": literal_n / total if total else 0.0,
        "service_rate": service_n / total if total else 0.0,
        "raw_agreement": agreement["raw_agreement"],
        "gwet_ac1": agreement["gwet_ac1"],
        "hallucination_rate": unsupported / service_n if service_n else 1.0,
    }
    thresholds = {
        "literal_closure": (
            metrics["literal_closure"] == 1.0 and without_modifiers == 0
        ),
        "raw_agreement": float(metrics["raw_agreement"] or 0) >= 0.85,
        "gwet_ac1": float(metrics["gwet_ac1"] or 0) >= 0.70,
        "hallucination_rate": metrics["hallucination_rate"] <= 0.10,
        "service_rate": metrics["service_rate"] >= 0.95,
    }
    summary = {
        **metrics,
        "threshold_pass": thresholds,
        "gate_pass": all(thresholds.values()),
        "failure_policy": (
            "B1 official task remains reported; B1 clinical-complete confirmatory "
            "interpretation and B1-vs-A3 clinical contrast are withheld on failure"
        ),
    }
    directory = out / "modifier_gate"
    atomic_json(directory / "summary.json", summary)
    write_jsonl(
        directory / "modifier_decisions.jsonl",
        [
            {
                "blind_completion_id": blind,
                "modifier_id": modifier,
                "reviewer_support": votes.get((blind, modifier), []),
                "panel_supported": (
                    all(votes[(blind, modifier)])
                    if len(votes.get((blind, modifier), [])) == 2
                    else None
                ),
            }
            for blind, modifier in expected
        ],
    )
    return summary


def exact_mcnemar(left_only: int, right_only: int) -> float:
    n = left_only + right_only
    if not n:
        return 1.0
    tail = sum(math.comb(n, index) for index in range(min(left_only, right_only) + 1))
    return min(1.0, 2 * tail / (2**n))


def holm_adjust(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows]
    order = sorted(
        range(len(output)),
        key=lambda index: (
            float(output[index]["exact_mcnemar_p"]),
            str(output[index].get("contrast") or ""),
        ),
    )
    prior = 0.0
    for rank, index in enumerate(order):
        value = min(
            1.0,
            (len(output) - rank) * float(output[index]["exact_mcnemar_p"]),
        )
        prior = max(prior, value)
        output[index]["holm_adjusted_p"] = prior
    return output


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list, tuple))
                    else value
                    for key, value in row.items()
                }
            )


def _arm_alias(observed: Iterable[str], target: str) -> str | None:
    observed = list(observed)
    if target in observed:
        return target
    prefix = target.split("_", 1)[0]
    matches = [arm for arm in observed if arm == prefix or arm.startswith(prefix + "_")]
    return matches[0] if len(matches) == 1 else None


def _transition_typology(
    rows: Sequence[Mapping[str, Any]],
    bridge: FrozenExactSynonymBridge,
    left_arm: str,
    right_arm: str,
) -> dict[str, Any]:
    by_key = {(str(row["case_key"]), str(row["arm"])): row for row in rows}
    cases = sorted(
        {key for key, arm in by_key if arm == left_arm}
        & {key for key, arm in by_key if arm == right_arm}
    )
    counts = Counter()
    ledger = []
    for case_key in cases:
        left, right = by_key[(case_key, left_arm)], by_key[(case_key, right_arm)]
        before, after = bool(left["clinical_complete"]), bool(right["clinical_complete"])
        if before == after:
            continue
        if not before and after:
            right_key = bridge.canonical_key(str(right["champion_label"]))
            specificity = any(
                bridge.canonical_key(str(item.get("completed_label"))) == right_key
                and item.get("parent_label")
                and bridge.equivalent(
                    str(item["parent_label"]), str(left["champion_label"])
                )
                for item in right.get("accepted_completions") or []
            )
            category = "specificity_rescue" if specificity else "object_rescue"
        elif right["complete_or_compatible_partial"]:
            category = "scope_compression"
        else:
            category = "catastrophic_substitution"
        counts[category] += 1
        ledger.append({"case_key": case_key, "transition_class": category})
    net = (
        counts["specificity_rescue"]
        + counts["object_rescue"]
        - counts["scope_compression"]
        - counts["catastrophic_substitution"]
    )
    return {
        "left_arm": left_arm,
        "right_arm": right_arm,
        "counts": dict(counts),
        "complete_net_n": net,
        "closure_identity": (
            "specificity_rescue + object_rescue - scope_compression - "
            "catastrophic_substitution"
        ),
        "ledger": ledger,
    }


def _verify_freeze(source: Path, out: Path) -> dict[str, Any]:
    prereg = json.loads((out / "design/preregistration.json").read_text(encoding="utf-8"))
    if file_sha256(source.resolve()) != prereg["source_sha256"]:
        raise AssertionError("source bytes changed after prepare")
    rows = read_jsonl(source)
    case_keys = sorted({str(row["case_key"]) for row in rows})
    if case_keys != prereg["case_keys"]:
        raise AssertionError("source case keys changed after prepare")
    expected = _frozen_prompt_hashes()
    if prereg["prompts"] != expected:
        raise AssertionError("frozen prompt hash drift")
    if prereg["models"]["task"] != TASK_MODEL:
        raise AssertionError("frozen task model drift")
    return prereg


def _usage_value(row: Mapping[str, Any], *keys: str) -> int | None:
    containers = [
        row,
        row.get("telemetry"),
        row.get("usage"),
        row.get("runner_summary"),
    ]
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        for key in keys:
            if container.get(key) is not None:
                return int(container[key])
    return None


def _endpoint_stats(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = []
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["family"]), str(row["arm"]))].append(row)
    for (family, arm), group in sorted(grouped.items()):
        n = len(group)
        served = [row for row in group if row["served"]]
        complete_exposed_n = sum(bool(row["pool_complete_exposure"]) for row in group)
        call_values = [
            value
            for row in group
            if (value := _usage_value(row, "semantic_calls", "calls")) is not None
        ]
        input_values = [
            value
            for row in group
            if (value := _usage_value(row, "input_tokens", "prompt_tokens"))
            is not None
        ]
        output_values = [
            value
            for row in group
            if (value := _usage_value(row, "output_tokens", "completion_tokens"))
            is not None
        ]
        option_counts = sorted(
            {
                int(row["source_option_n"])
                for row in group
                if row.get("source_option_n") is not None
            }
        )
        record = {
            "family": family,
            "arm": arm,
            "ita_n": n,
            "served_n": len(served),
            "service_rate": len(served) / n if n else None,
            "official_task_name": (
                "DA Acc@N/option accuracy"
                if family == "DA"
                else "MCR Prompt-7 Acc"
            ),
            "source_option_n_values": option_counts,
            "official_task_n": sum(bool(row["official_task"]) for row in group),
            "official_task_rate_ita": sum(bool(row["official_task"]) for row in group)
            / n,
            "clinical_complete_n": sum(bool(row["clinical_complete"]) for row in group),
            "clinical_complete_rate_ita": sum(
                bool(row["clinical_complete"]) for row in group
            )
            / n,
            "complete_or_compatible_partial_n": sum(
                bool(row["complete_or_compatible_partial"]) for row in group
            ),
            "complete_or_compatible_partial_rate_ita": sum(
                bool(row["complete_or_compatible_partial"]) for row in group
            )
            / n,
            "pool_complete_exposure_n": complete_exposed_n,
            "pool_complete_exposure_rate": complete_exposed_n / n,
            "pool_complete_or_partial_exposure_n": sum(
                bool(row["pool_complete_or_partial_exposure"]) for row in group
            ),
            "pool_complete_or_partial_exposure_rate": sum(
                bool(row["pool_complete_or_partial_exposure"]) for row in group
            )
            / n,
            "conditional_complete_conversion": (
                sum(bool(row["clinical_complete"]) for row in group)
                / complete_exposed_n
                if complete_exposed_n
                else None
            ),
            "mean_main_pool_width": sum(
                float(row.get("main_pool_width") or 0) for row in group
            )
            / n,
            "runner_calls": sum(call_values) if call_values else None,
            "runner_input_tokens": sum(input_values) if input_values else None,
            "runner_output_tokens": sum(output_values) if output_values else None,
            "runner_usage_row_coverage": {
                "calls": len(call_values),
                "input_tokens": len(input_values),
                "output_tokens": len(output_values),
                "ita_n": n,
            },
            "confirmatory_withheld_gate_failure": any(
                bool(row.get("confirmatory_withheld_gate_failure")) for row in group
            ),
        }
        records.append(record)
    return records


def _paired_records(
    rows: Sequence[Mapping[str, Any]], gate_pass: bool
) -> list[dict[str, Any]]:
    by_key = {(str(row["case_key"]), str(row["arm"])): row for row in rows}
    observed_arms = {str(row["arm"]) for row in rows}
    output: list[dict[str, Any]] = []
    endpoints = (
        ("official_task", "official_task"),
        ("clinical_complete", "clinical_complete"),
        (
            "complete_or_compatible_partial",
            "complete_or_compatible_partial",
        ),
    )
    for family in ("DA", "MCR"):
        family_cases = {
            str(row["case_key"]) for row in rows if str(row["family"]) == family
        }
        for left_target, right_target, label in CONTRASTS:
            left = _arm_alias(observed_arms, left_target)
            right = _arm_alias(observed_arms, right_target)
            if left is None or right is None:
                continue
            case_keys = sorted(
                case
                for case in family_cases
                if (case, left) in by_key and (case, right) in by_key
            )
            for endpoint, endpoint_name in endpoints:
                if (
                    label == "B1-A3"
                    and endpoint != "official_task"
                    and not gate_pass
                ):
                    output.append(
                        {
                            "family": family,
                            "contrast": label,
                            "left_arm": left,
                            "right_arm": right,
                            "endpoint": endpoint_name,
                            "analysis_scope": "ITA",
                            "status": "confirmatory_withheld_gate_failure",
                            "holm_family": f"{family}/{endpoint_name}",
                        }
                    )
                    continue
                pairs = [
                    (
                        bool(by_key[(case, left)][endpoint]),
                        bool(by_key[(case, right)][endpoint]),
                    )
                    for case in case_keys
                ]
                counts = Counter(pairs)
                n = len(pairs)
                output.append(
                    {
                        "family": family,
                        "contrast": label,
                        "left_arm": left,
                        "right_arm": right,
                        "endpoint": endpoint_name,
                        "analysis_scope": "ITA",
                        "status": "evaluated",
                        "n": n,
                        "both": counts[(True, True)],
                        "left_only": counts[(True, False)],
                        "right_only": counts[(False, True)],
                        "neither": counts[(False, False)],
                        "delta_right_minus_left": (
                            counts[(False, True)] - counts[(True, False)]
                        )
                        / n
                        if n
                        else None,
                        "exact_mcnemar_p": exact_mcnemar(
                            counts[(True, False)], counts[(False, True)]
                        ),
                        "holm_family": f"{family}/{endpoint_name}",
                    }
                )
                common = [
                    case
                    for case in case_keys
                    if by_key[(case, left)]["served"]
                    and by_key[(case, right)]["served"]
                ]
                common_counts = Counter(
                    (
                        bool(by_key[(case, left)][endpoint]),
                        bool(by_key[(case, right)][endpoint]),
                    )
                    for case in common
                )
                output.append(
                    {
                        "family": family,
                        "contrast": label,
                        "left_arm": left,
                        "right_arm": right,
                        "endpoint": endpoint_name,
                        "analysis_scope": "common_served_sensitivity",
                        "status": "sensitivity_only",
                        "n": len(common),
                        "both": common_counts[(True, True)],
                        "left_only": common_counts[(True, False)],
                        "right_only": common_counts[(False, True)],
                        "neither": common_counts[(False, False)],
                        "delta_right_minus_left": (
                            common_counts[(False, True)]
                            - common_counts[(True, False)]
                        )
                        / len(common)
                        if common
                        else None,
                        "exact_mcnemar_p": exact_mcnemar(
                            common_counts[(True, False)],
                            common_counts[(False, True)],
                        ),
                        "holm_family": None,
                    }
                )
    adjusted: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in output:
        if row["analysis_scope"] == "ITA" and row["status"] == "evaluated":
            groups[str(row["holm_family"])].append(row)
        else:
            adjusted.append(row)
    for family_rows in groups.values():
        adjusted.extend(holm_adjust(family_rows))
    return sorted(
        adjusted,
        key=lambda row: (
            str(row["family"]),
            str(row["endpoint"]),
            str(row["analysis_scope"]),
            str(row["contrast"]),
        ),
    )


def finalize(source: Path, out: Path) -> dict[str, Any]:
    source, out = Path(source).resolve(), Path(out).resolve()
    prereg = _verify_freeze(source, out)
    frozen_rows = read_jsonl(out / "design/intention_ledger.jsonl")
    relations: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(out / "design/relation_index.jsonl"):
        if row["status"] == "reused":
            relations[str(row["relation_id"])] = {
                "relation": str(row["relation"]),
                "provenance": row["reuse_provenance"],
            }
    for row in read_jsonl(out / "panel/panel_decisions.jsonl"):
        relations[str(row["relation_id"])] = {
            "relation": str(row["relation"]),
            "provenance": {
                "reuse_source": row["provenance"],
                "panel_status": row["panel_status"],
            },
        }
    expected_relations = read_jsonl(out / "design/relation_index.jsonl")
    if len(relations) != len(expected_relations):
        raise AssertionError("clinical relation census incomplete")
    relation_id_by_key = {
        (str(row["case_key"]), str(row["canonical_prediction"])): str(
            row["relation_id"]
        )
        for row in expected_relations
    }
    task_rows = {
        str(row["task_id"]): row
        for row in read_jsonl(out / "task_evaluator/task_results.jsonl")
    }
    task_index = read_jsonl(out / "design/task_index.jsonl")
    if set(task_rows) != {str(row["task_id"]) for row in task_index}:
        raise AssertionError("official task census incomplete")
    task_id_by_key = {
        (
            str(row["family"]),
            str(row["case_key"]),
            str(row["canonical_prediction"]),
        ): str(row["task_id"])
        for row in task_index
    }
    gate_path = out / "modifier_gate/summary.json"
    gate = (
        json.loads(gate_path.read_text(encoding="utf-8"))
        if gate_path.is_file()
        else {"gate_pass": False, "status": "modifier_gate_missing"}
    )
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    final_rows: list[dict[str, Any]] = []
    for frozen in frozen_rows:
        row = dict(frozen)
        if row["served"]:
            pool_relations = []
            pool_provenance = []
            for label in row["main_pool_labels"]:
                key = relation_key(row["case_key"], label, bridge)
                relation_id = relation_id_by_key[key]
                decision = relations[relation_id]
                pool_relations.append(str(decision["relation"]))
                pool_provenance.append(
                    {
                        "label": label,
                        "relation_id": relation_id,
                        **dict(decision["provenance"]),
                    }
                )
            champion_key = relation_key(
                row["case_key"], row["champion_label"], bridge
            )
            champion_id = relation_id_by_key[champion_key]
            champion_relation = str(relations[champion_id]["relation"])
            tkey = task_key(
                row["family"], row["case_key"], row["champion_label"], bridge
            )
            task = task_rows[task_id_by_key[tkey]]
            row.update(
                {
                    "clinical_relation": champion_relation,
                    "clinical_relation_id": champion_id,
                    "clinical_provenance": relations[champion_id]["provenance"],
                    "clinical_complete": champion_relation
                    == "complete_equivalent",
                    "complete_or_compatible_partial": champion_relation
                    in COMPATIBLE_RELATIONS,
                    "pool_complete_exposure": "complete_equivalent"
                    in pool_relations,
                    "pool_complete_or_partial_exposure": any(
                        relation in COMPATIBLE_RELATIONS
                        for relation in pool_relations
                    ),
                    "pool_relation_provenance": pool_provenance,
                    "official_task": bool(
                        task.get("success") and task.get("task_correct")
                    ),
                    "official_task_evaluable": bool(task.get("success")),
                    "mapped_option": task.get("mapped_option"),
                    "task_method": task.get("method")
                    or task.get("task_projection"),
                    "task_projection_sha256": task.get("projection_sha256"),
                    "task_reuse_provenance": task.get("reuse_source"),
                }
            )
        else:
            row.update(
                {
                    "clinical_relation": None,
                    "clinical_relation_id": None,
                    "clinical_provenance": {"source": "ita_failure"},
                    "clinical_complete": False,
                    "complete_or_compatible_partial": False,
                    "pool_complete_exposure": False,
                    "pool_complete_or_partial_exposure": False,
                    "pool_relation_provenance": [],
                    "official_task": False,
                    "official_task_evaluable": True,
                    "mapped_option": None,
                    "task_method": "ita_failure",
                    "task_projection_sha256": "",
                    "task_reuse_provenance": None,
                }
            )
        is_b1 = _arm_alias({str(row["arm"])}, "B1_corelift") is not None
        row["confirmatory_withheld_gate_failure"] = bool(
            is_b1 and not gate.get("gate_pass")
        )
        final_rows.append(row)

    final_dir = out / "final"
    write_jsonl(final_dir / "case_endpoints.jsonl", final_rows)
    stats = _endpoint_stats(final_rows)
    atomic_json(final_dir / "arm_statistics.json", {"records": stats})
    _write_csv(final_dir / "arm_statistics.csv", stats)
    contrasts = _paired_records(final_rows, bool(gate.get("gate_pass")))
    atomic_json(final_dir / "paired_contrasts.json", {"records": contrasts})
    _write_csv(final_dir / "paired_contrasts.csv", contrasts)
    observed = {str(row["arm"]) for row in final_rows}
    a3 = _arm_alias(observed, "A3_full")
    b1 = _arm_alias(observed, "B1_corelift")
    transitions = (
        _transition_typology(final_rows, bridge, a3, b1)
        if a3 is not None and b1 is not None
        else {"status": "A3_or_B1_absent"}
    )
    summary = {
        "schema_version": "corelift-final-v1",
        "created_at_utc": utcnow(),
        "development_not_confirmation": True,
        "n_rows": len(final_rows),
        "n_cases": len({str(row["case_key"]) for row in final_rows}),
        "modifier_gate": gate,
        "b1_clinical_confirmatory_withheld": not bool(gate.get("gate_pass")),
        "official_task_retained_when_gate_fails": True,
        "clinical_truth_tier": "model_panel_sensitivity_not_human_root",
        "official_task_estimands": {
            "DA": "DA Acc@N/option accuracy; N is source option count",
            "MCR": "MCR Prompt-7 Acc",
            "pooled": False,
        },
        "multiplicity": prereg["multiplicity"],
        "complete_transition_closure": transitions,
        "failure_policy": "ITA failures retained as zero",
    }
    atomic_json(final_dir / "summary.json", summary)
    report = render_report(stats, contrasts, summary)
    (out / "REPORT.md").write_text(report, encoding="utf-8")
    write_manifest(out)
    return summary


def render_report(
    stats: Sequence[Mapping[str, Any]],
    contrasts: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> str:
    lines = [
        "# CoreLift frozen endpoint evaluation",
        "",
        "## Interpretation contract",
        "",
        "This is a **development-not-confirmation** analysis of the repeatedly used "
        "800-case development set. Clinical completeness is a blinded three-model "
        "panel sensitivity and **not human-root truth**. Official task performance "
        "and clinical-complete are different estimands.",
        "",
        "DA reports **DA Acc@N / option accuracy** after gold-blind top-1 "
        "diagnosis→source-option projection. MCR reports frozen **Prompt-7 Acc**. "
        "DA and MCR are never pooled.",
        "",
        "## Arm endpoints (ITA)",
        "",
        "| Family | Arm | Service | Official task | Clinical complete | C∪P | Complete exposure | C∪P exposure | Conditional conversion | Mean width |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stats:
        pct = lambda value: "—" if value is None else f"{100 * float(value):.2f}%"
        lines.append(
            f"| {row['family']} | `{row['arm']}` | {pct(row['service_rate'])} | "
            f"{pct(row['official_task_rate_ita'])} | "
            f"{pct(row['clinical_complete_rate_ita'])} | "
            f"{pct(row['complete_or_compatible_partial_rate_ita'])} | "
            f"{pct(row['pool_complete_exposure_rate'])} | "
            f"{pct(row['pool_complete_or_partial_exposure_rate'])} | "
            f"{pct(row['conditional_complete_conversion'])} | "
            f"{float(row['mean_main_pool_width']):.2f} |"
        )
    gate = summary["modifier_gate"]
    transition = summary.get("complete_transition_closure") or {}
    transition_counts = transition.get("counts") or {}
    lines.extend(
        [
            "",
            "## M2/B1 modifier gate",
            "",
            f"Gate pass: **{bool(gate.get('gate_pass'))}**. Literal closure="
            f"{gate.get('literal_closure')}, raw agreement={gate.get('raw_agreement')}, "
            f"Gwet AC1={gate.get('gwet_ac1')}, hallucination="
            f"{gate.get('hallucination_rate')}, service={gate.get('service_rate')}.",
            "",
            "On gate failure, B1 official DA/MCR task results remain reported. "
            "B1 clinical-complete is marked "
            "`confirmatory_withheld_gate_failure=true`, and B1-vs-A3 clinical "
            "confirmatory contrasts are not executed or interpreted.",
            "",
            "## Complete transition closure definitions",
            "",
            "- `specificity_rescue`: B1 becomes complete through an accepted completion "
            "whose parent matches the A3 champion.",
            "- `object_rescue`: B1 becomes complete through a different/new diagnostic object.",
            "- `scope_compression`: A3 complete is lost but B1 remains C∪P.",
            "- `catastrophic_substitution`: A3 complete is lost and B1 is outside C∪P.",
            "",
            "The signed closure is specificity rescue + object rescue − scope "
            "compression − catastrophic substitution.",
            "",
            "Observed A3→B1 discordant counts: "
            f"specificity rescue={transition_counts.get('specificity_rescue', 0)}, "
            f"object rescue={transition_counts.get('object_rescue', 0)}, "
            f"scope compression={transition_counts.get('scope_compression', 0)}, "
            "catastrophic substitution="
            f"{transition_counts.get('catastrophic_substitution', 0)}; "
            f"signed complete net={transition.get('complete_net_n', '—')}.",
            "",
            "## Paired inference",
            "",
            "Primary contrasts use case-level exact McNemar on the full ITA denominator. "
            "Holm is applied separately within each benchmark family and endpoint; "
            "common-served results are sensitivity analyses only.",
            "",
            f"Evaluated contrast records: {sum(row.get('status') == 'evaluated' for row in contrasts)}; "
            f"withheld records: {sum(row.get('status') == 'confirmatory_withheld_gate_failure' for row in contrasts)}.",
            "",
        ]
    )
    return "\n".join(lines)


def write_manifest(out: Path) -> dict[str, Any]:
    out = Path(out)
    manifest_path = out / "artifact_manifest.json"
    files = [
        path
        for path in sorted(out.rglob("*"))
        if path.is_file()
        and path != manifest_path
        and "/cache/" not in path.as_posix()
    ]
    manifest = {
        "schema_version": "corelift-evaluation-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "files": [
            {
                "path": str(path.relative_to(out)),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in files
        ],
    }
    manifest["file_count"] = len(manifest["files"])
    atomic_json(manifest_path, manifest)
    return manifest


def _parse_assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected reviewer_id=model")
    reviewer_id, model = value.split("=", 1)
    if not reviewer_id.strip() or not model.strip():
        raise argparse.ArgumentTypeError("expected nonempty reviewer_id=model")
    return reviewer_id.strip(), model.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-task", action="store_true")
    parser.add_argument("--reviewer", action="append", type=_parse_assignment, default=[])
    parser.add_argument("--compile-panel", action="store_true")
    parser.add_argument(
        "--modifier-reviewer", action="append", type=_parse_assignment, default=[]
    )
    parser.add_argument("--compile-modifier-gate", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args(argv)
    actions = (
        int(args.prepare_only)
        + int(args.run_task)
        + len(args.reviewer)
        + int(args.compile_panel)
        + len(args.modifier_reviewer)
        + int(args.compile_modifier_gate)
        + int(args.finalize)
    )
    if actions != 1:
        parser.error("select exactly one staged action (and one reviewer per command)")
    out = args.out.resolve()
    if args.prepare_only:
        result = prepare(args.source, out)
    elif args.run_task:
        result = run_task(
            out, TASK_MODEL, args.workers, cache_only=args.cache_only
        )
    elif args.reviewer:
        reviewer_id, model = args.reviewer[0]
        result = run_reviewer(
            out,
            reviewer_id,
            model,
            args.workers,
            cache_only=args.cache_only,
        )
    elif args.compile_panel:
        result = compile_panel(out)
    elif args.modifier_reviewer:
        reviewer_id, model = args.modifier_reviewer[0]
        result = run_modifier_reviewer(
            out,
            reviewer_id,
            model,
            args.workers,
            cache_only=args.cache_only,
        )
    elif args.compile_modifier_gate:
        result = compile_modifier_gate(out)
    else:
        result = finalize(args.source, out)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
