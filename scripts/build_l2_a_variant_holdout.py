#!/usr/bin/env python3
"""Build or block the sealed L2 A-variant holdout cohort.

This builder audits in-repo and declared external case pools, excludes every
case used for the TALP17 development set or historical scheme selection, and
either:

* seals ``eval_fixtures/l2_a_variant_holdout_v1.json`` with 80–190 legal cases
  (no algorithm outputs), or
* writes a frozen, hash-sealed blocked fixture/manifest with
  ``promotion_eligible=false`` when the legal pool is below the minimum.

It also prepares a C-prod vs frozen-development-winner execution interface that
refuses to run until both the holdout is sealed with enough cases and a
development winner artifact is frozen. Confirmatory runs are never fabricated.
"""
from __future__ import annotations

import argparse
import ast
import copy
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402

PROTOCOL_PATH = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v1.json"
DEFAULT_FIXTURE = ROOT / "eval_fixtures" / "l2_a_variant_holdout_v1.json"
DEFAULT_BLOCKED_MANIFEST = (
    ROOT / "logs" / "l2_a_variant_holdout_v1" / "blocked_manifest.json"
)
DEFAULT_EXECUTION_INTERFACE = (
    ROOT / "logs" / "l2_a_variant_holdout_v1" / "execution_interface.json"
)
DEFAULT_WINNER_PATH = (
    ROOT / "eval_fixtures" / "l2_a_variant_frozen_development_winner_v1.json"
)

MEDBULLETS_TSV = Path(
    "/home/wanghongyi/LLM-Structured-Data-main/"
    "som/MMLU/test/medbullets_hard_test.tsv"
)
MEDXPERT_TSV = Path(
    "/home/wanghongyi/LLM-Structured-Data-main/"
    "som/MMLU/test/medxpertqar_hard_test.tsv"
)

SCHEMA_VERSION = 1
FIXTURE_ID = "l2_a_variant_holdout_v1"
MIN_CASES = 80
PREFERRED_RANGE = (150, 190)
STRATIFICATION_AXES = (
    "case_source",
    "syndrome_type",
    "parent_complexity",
    "rare_disease_fraction",
)
HOLDOUT_ARMS = ("C-prod", "frozen_development_winner")

ALGORITHM_OUTPUT_KEYS = frozenset({
    "tree",
    "trees",
    "tree_hash",
    "branches",
    "frontier",
    "recall_audit",
    "trace",
    "traces",
    "generation",
    "downstream",
    "ranking",
    "posteriors",
    "actual_top1",
    "actual_top2",
    "leaf_clean_rate",
    "model_response",
    "calls",
})

DIAGNOSIS_CUES = (
    "most likely diagnosis",
    "most likely cause",
    "most likely underlying",
    "which of the following is the most likely",
    "best explains",
    "most consistent with",
    "underlying diagnosis",
    "responsible for",
    "most likely responsible",
    "best describes",
)
VIGNETTE_RE = re.compile(
    r"\b(\d{1,3}[- ]?(year|yo|y/o)|year-old|man|woman|male|female|"
    r"boy|girl|infant|patient)\b",
    re.I,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def seal_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(dict(payload))
    output.pop("fixture_hash", None)
    output["fixture_hash"] = stable_hash(output)
    return output


def verify_sealed(payload: Mapping[str, Any], *, label: str) -> None:
    expected = str(payload.get("fixture_hash") or "")
    if not expected:
        raise ValueError(f"{label}: missing fixture_hash")
    unsigned = dict(payload)
    unsigned.pop("fixture_hash", None)
    if stable_hash(unsigned) != expected:
        raise ValueError(f"{label}: fixture hash drift")


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    doc = _read_json(path)
    holdout = doc.get("holdout") or {}
    development = doc.get("development") or {}
    if not development.get("case_ids"):
        raise ValueError("protocol missing development.case_ids")
    if holdout.get("fixture_path") != "eval_fixtures/l2_a_variant_holdout_v1.json":
        raise ValueError("protocol holdout fixture path drift")
    return doc


def development_case_ids(protocol: Mapping[str, Any]) -> list[str]:
    return [str(x) for x in protocol["development"]["case_ids"]]


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def content_fingerprint(
    *,
    vignette: str = "",
    gold: str = "",
    gold_option: str = "",
) -> str:
    return stable_hash({
        "vignette": _normalize_text(vignette),
        "gold": _normalize_text(gold),
        "gold_option": _normalize_text(gold_option),
    })


def _contains_algorithm_outputs(value: Any) -> list[str]:
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                key_s = str(key)
                child_path = f"{path}.{key_s}" if path else key_s
                if key_s in ALGORITHM_OUTPUT_KEYS:
                    hits.append(child_path)
                walk(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node[:50]):
                walk(child, f"{path}[{index}]")

    walk(value, "")
    return hits


def _load_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _parse_options(raw: str) -> dict[str, str]:
    try:
        value = ast.literal_eval(raw)
    except Exception:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _is_diagnosis_question(question: str) -> bool:
    lowered = question.casefold()
    return any(cue in lowered for cue in DIAGNOSIS_CUES)


def _looks_like_vignette(question: str) -> bool:
    return bool(VIGNETTE_RE.search(question or "")) and len(question or "") >= 80


def _candidate(
    *,
    case_id: str,
    case_source: str,
    source_path: str,
    source_index: int | None,
    vignette: str,
    gold: str,
    gold_option: str,
    syndrome_type: str | None = None,
    parent_complexity: str | None = None,
    rare_disease_fraction: float | None = None,
    calibration_status: str | None = None,
    notes: Sequence[str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "case_id": case_id,
        "case_source": case_source,
        "source_path": source_path,
        "source_index": source_index,
        "vignette": vignette,
        "gold": gold,
        "gold_option": gold_option,
        "syndrome_type": syndrome_type,
        "parent_complexity": parent_complexity,
        "rare_disease_fraction": rare_disease_fraction,
        "calibration_status": calibration_status,
        "content_fingerprint": content_fingerprint(
            vignette=vignette, gold=gold, gold_option=gold_option,
        ),
        "notes": list(notes or []),
    }
    if extra:
        payload["extra"] = dict(extra)
    return payload


def collect_development_fingerprints(
    protocol: Mapping[str, Any],
) -> dict[str, str]:
    """Fingerprint development cases from assembled TALP17 assets."""
    import importlib.util

    harness_path = ROOT / "scripts" / "eval_partial_flow_talp17.py"
    spec = importlib.util.spec_from_file_location(
        "talp17_holdout_audit", harness_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {harness_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assembled = module.assemble_cases()
    out: dict[str, str] = {}
    for case in assembled:
        case_id = str(case["id"])
        out[case_id] = content_fingerprint(
            vignette=str(case.get("case_text") or ""),
            gold=str(case.get("gold") or ""),
            gold_option=str(case.get("gold_option") or ""),
        )
    expected = set(development_case_ids(protocol))
    if set(out) != expected:
        raise ValueError(
            "development fingerprint set drift: "
            f"missing={sorted(expected - set(out))} "
            f"extra={sorted(set(out) - expected)}"
        )
    return out


def inventory_candidate_pools() -> dict[str, Any]:
    """Enumerate raw candidate pools before legality filters."""
    pools: dict[str, Any] = {}

    mb_rows = _load_tsv(MEDBULLETS_TSV)
    mb_dx: list[dict[str, Any]] = []
    seen_q: set[str] = set()
    for index, row in enumerate(mb_rows):
        question = str(row.get("question") or "").strip()
        options = _parse_options(str(row.get("options") or ""))
        if not options or not _is_diagnosis_question(question):
            continue
        key = question[:120]
        if key in seen_q:
            continue
        seen_q.add(key)
        answer = str(row.get("answer") or "").strip()
        mb_dx.append(
            _candidate(
                case_id=f"mb_raw_{index:03d}",
                case_source="medbullets_hard_test",
                source_path=str(MEDBULLETS_TSV),
                source_index=index,
                vignette=question,
                gold=answer,
                gold_option=answer,
                notes=["raw_tsv_diagnosis_cue"],
            )
        )
    pools["medbullets_hard_diagnosis"] = {
        "source_path": str(MEDBULLETS_TSV),
        "source_exists": MEDBULLETS_TSV.exists(),
        "raw_row_count": len(mb_rows),
        "candidate_count": len(mb_dx),
        "candidates": mb_dx,
    }

    mx_rows = _load_tsv(MEDXPERT_TSV)
    mx_cands: list[dict[str, Any]] = []
    for index, row in enumerate(mx_rows):
        question = str(row.get("question") or "").strip()
        options = _parse_options(str(row.get("options") or ""))
        answer = str(row.get("answer") or "").strip()
        if not options or not answer:
            continue
        mx_cands.append(
            _candidate(
                case_id=f"mxh{index:03d}",
                case_source="medxpertqar_hard",
                source_path=str(MEDXPERT_TSV),
                source_index=index,
                vignette=question,
                gold=answer,
                gold_option=answer,
                notes=[
                    "raw_tsv",
                    "vignette_like" if _looks_like_vignette(question)
                    else "vignette_weak",
                ],
            )
        )
    pools["medxpertqar_hard"] = {
        "source_path": str(MEDXPERT_TSV),
        "source_exists": MEDXPERT_TSV.exists(),
        "raw_row_count": len(mx_rows),
        "candidate_count": len(mx_cands),
        "candidates": mx_cands,
    }

    curated: list[dict[str, Any]] = []
    curated_paths = [
        ROOT / "data" / "eval" / "talp_discrimination_cases.json",
        ROOT / "data" / "eval" / "talp_medxpert_expansion_cases.draft.json",
        ROOT / "data" / "eval" / "talp_medxpert_expansion_cases.json",
        ROOT / "data" / "eval" / "talp_medxpert_expansion_cases_v2.json",
        ROOT / "data" / "eval" / "lr_coverage_cases.json",
        ROOT / "data" / "eval" / "lr_discrimination_matrix.json",
        ROOT / "data" / "cpg" / "eval" / "branch_recall_eval_set.json",
        ROOT / "data" / "cpg" / "eval" / "branch_recall_eval_set_hard.json",
    ]
    for path in curated_paths:
        if not path.exists():
            continue
        doc = _read_json(path)
        cases = doc.get("cases") if isinstance(doc, Mapping) else None
        if not isinstance(cases, list):
            continue
        for case in cases:
            if not isinstance(case, Mapping):
                continue
            case_id = str(case.get("id") or case.get("case_id") or "")
            vignette = str(
                case.get("vignette")
                or case.get("case_text")
                or case.get("question")
                or case.get("q")
                or ""
            )
            gold = str(case.get("gold") or case.get("answer") or "")
            gold_option = str(
                case.get("gold_option") or case.get("answer") or gold
            )
            curated.append(
                _candidate(
                    case_id=case_id or f"curated_{len(curated):04d}",
                    case_source=str(
                        case.get("corpus")
                        or case.get("source")
                        or path.stem
                    ),
                    source_path=_relative(path),
                    source_index=case.get("case_idx", case.get("source_index")),
                    vignette=vignette,
                    gold=gold,
                    gold_option=gold_option,
                    syndrome_type=(
                        str(case["l1_label"]) if case.get("l1_label") else None
                    ),
                    calibration_status=(
                        str(case["calibration_status"])
                        if case.get("calibration_status") is not None
                        else None
                    ),
                    notes=["in_repo_curated_json"],
                    extra={
                        "has_candidates": isinstance(case.get("candidates"), list),
                        "has_findings": isinstance(case.get("findings"), list),
                    },
                )
            )
        excluded = doc.get("excluded_cases") if isinstance(doc, Mapping) else None
        if isinstance(excluded, list):
            for case in excluded:
                if not isinstance(case, Mapping):
                    continue
                case_id = str(case.get("id") or "")
                curated.append(
                    _candidate(
                        case_id=case_id or f"excluded_{len(curated):04d}",
                        case_source="medxpertqar_hard_excluded",
                        source_path=_relative(path),
                        source_index=case.get("case_idx"),
                        vignette=str(case.get("vignette") or ""),
                        gold=str(case.get("source_answer") or case.get("gold") or ""),
                        gold_option=str(
                            case.get("source_answer") or case.get("gold_option") or ""
                        ),
                        notes=[
                            "explicitly_excluded_from_talp_expansion",
                            str(case.get("reason") or "excluded"),
                        ],
                    )
                )
    pools["in_repo_curated_eval_json"] = {
        "candidate_count": len(curated),
        "candidates": curated,
    }

    case_reports = ROOT / "data" / "case_reports" / "case_reports.jsonl"
    report_count = 0
    report_sources: Counter[str] = Counter()
    if case_reports.exists():
        with case_reports.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                report_count += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                report_sources[str(row.get("source") or "?")] += 1
    pools["case_reports_corpus"] = {
        "source_path": _relative(case_reports) if case_reports.exists() else None,
        "source_exists": case_reports.exists(),
        "row_count": report_count,
        "sources": dict(report_sources.most_common()),
        "candidate_count": 0,
        "candidates": [],
        "notes": [
            "retrieval_corpus_not_mcq_talp_cases",
            "lacks_options_gold_calibration_for_l2_holdout",
        ],
    }

    return pools


def _historical_scheme_selection_ids() -> set[str]:
    """Case IDs repeatedly used for TALP/L1/L2 scheme selection."""
    ids: set[str] = set()
    manifests = [
        ROOT / "logs" / "partial_flow_talp17" / "talp17_p5_g2ur_partial_20260712"
        / "manifest.json",
        ROOT / "logs" / "branch_talp_composed" / "talp17_shared_tree_p5_g2ur"
        / "manifest.json",
        ROOT / "logs" / "l2_branch_generation_ab_v1" / "generation" / "manifest.json",
        ROOT / "logs" / "l2_competition_strategies_v1" / "l1_frozen" / "manifest.json",
        ROOT / "logs" / "naive_cot_hierarchy_baselines_v1" / "manifest.json",
        ROOT / "logs" / "naive_cot_rag_ablation_v1" / "manifest.json",
    ]
    for path in manifests:
        if not path.exists():
            continue
        doc = _read_json(path)
        for key in ("case_ids", "cases"):
            value = doc.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        ids.add(item)
                    elif isinstance(item, Mapping) and item.get("case_id"):
                        ids.add(str(item["case_id"]))
                    elif isinstance(item, Mapping) and item.get("id"):
                        ids.add(str(item["id"]))
    # MedXpert indices selected for draft/expansion are scheme-selection contaminated.
    for idx in (11, 14, 36, 42, 45, 46, 55, 68, 75, 98):
        ids.add(f"mxh{idx:03d}")
    return ids


def _medbullets_historical_contamination(
    mb_candidates: Sequence[Mapping[str, Any]],
) -> set[str]:
    """All MedBullets diagnosis-cue cases appear in historical conc eval logs."""
    contaminated = {str(c["case_id"]) for c in mb_candidates}
    # Also mark by content fingerprint via answer overlap with logged answers.
    return contaminated


def evaluate_legality(
    pools: Mapping[str, Any],
    *,
    development_ids: Sequence[str],
    development_fps: Mapping[str, str],
) -> dict[str, Any]:
    dev_ids = set(development_ids)
    dev_fps = set(development_fps.values())
    historical_ids = _historical_scheme_selection_ids()
    mb_contaminated = _medbullets_historical_contamination(
        pools.get("medbullets_hard_diagnosis", {}).get("candidates") or [],
    )

    exclusions: list[dict[str, Any]] = []
    legal: list[dict[str, Any]] = []
    seen_fps: set[str] = set()
    reason_counts: Counter[str] = Counter()

    def exclude(case: Mapping[str, Any], reasons: Sequence[str]) -> None:
        row = {
            "case_id": case.get("case_id"),
            "case_source": case.get("case_source"),
            "source_path": case.get("source_path"),
            "source_index": case.get("source_index"),
            "reasons": list(reasons),
        }
        exclusions.append(row)
        for reason in reasons:
            reason_counts[reason] += 1

    all_candidates: list[dict[str, Any]] = []
    for pool_name, pool in pools.items():
        for case in pool.get("candidates") or []:
            enriched = dict(case)
            enriched["pool"] = pool_name
            all_candidates.append(enriched)

    for case in all_candidates:
        reasons: list[str] = []
        case_id = str(case.get("case_id") or "")
        fp = str(case.get("content_fingerprint") or "")
        vignette = str(case.get("vignette") or "")
        gold = str(case.get("gold") or "")
        gold_option = str(case.get("gold_option") or "")

        if case_id in dev_ids:
            reasons.append("development_case_id")
        if fp and fp in dev_fps:
            reasons.append("development_content_fingerprint_overlap")
        if case_id in historical_ids:
            reasons.append("historical_scheme_selection_case_id")
        if case_id in mb_contaminated or case.get("pool") == "medbullets_hard_diagnosis":
            reasons.append("medbullets_hard_full_diagnosis_pool_historically_run")
        if not vignette.strip():
            reasons.append("missing_vignette")
        if not (gold.strip() or gold_option.strip()):
            reasons.append("missing_gold")
        if case.get("pool") == "medxpertqar_hard":
            reasons.append("uncalibrated_raw_tsv_not_talp_legal")
            if "vignette_weak" in (case.get("notes") or []):
                reasons.append("weak_or_non_vignette_stem")
        if case.get("pool") == "in_repo_curated_eval_json":
            cal = case.get("calibration_status")
            if cal in {None, "draft"}:
                reasons.append("curated_but_not_holdout_ready_calibration")
            if not vignette.strip():
                reasons.append("curated_annotation_without_vignette")
            if "explicitly_excluded_from_talp_expansion" in (case.get("notes") or []):
                reasons.append("explicit_talp_expansion_exclusion")
        # Stratification readiness for confirmatory sealing.
        if case.get("syndrome_type") in {None, ""}:
            reasons.append("missing_syndrome_type_stratum")
        if case.get("parent_complexity") in {None, ""}:
            reasons.append("missing_parent_complexity_stratum")
        if case.get("rare_disease_fraction") is None:
            reasons.append("missing_rare_disease_fraction_stratum")
        if fp and fp in seen_fps:
            reasons.append("duplicate_content_fingerprint")

        # Legal holdout case must clear every gate.
        fatal = [
            r for r in reasons
            if r not in {
                # keep all current reasons fatal; listed for clarity
            }
        ]
        if fatal:
            exclude(case, fatal)
            continue
        seen_fps.add(fp)
        legal.append(case)

    # Case-report corpus is never legal as-is.
    report_pool = pools.get("case_reports_corpus") or {}
    if int(report_pool.get("row_count") or 0) > 0:
        exclude(
            {
                "case_id": "case_reports_corpus",
                "case_source": "case_reports",
                "source_path": report_pool.get("source_path"),
                "source_index": None,
            },
            list(report_pool.get("notes") or ["retrieval_corpus_not_mcq_talp_cases"]),
        )
        reason_counts["retrieval_corpus_not_mcq_talp_cases"] += int(
            report_pool.get("row_count") or 0
        )

    overlap_ids = sorted(dev_ids & {str(c.get("case_id")) for c in legal})
    return {
        "scanned_candidate_count": len(all_candidates),
        "legal_candidates": legal,
        "legal_candidate_count": len(legal),
        "exclusions": exclusions,
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "development_overlap_case_ids": overlap_ids,
        "development_overlap_count": len(overlap_ids),
        "historical_scheme_selection_case_id_count": len(historical_ids),
    }


def stratified_select(
    legal: Sequence[Mapping[str, Any]],
    *,
    target_min: int = MIN_CASES,
    target_max: int = PREFERRED_RANGE[1],
) -> dict[str, Any]:
    """Deterministic stratified selection placeholder.

    With zero legal cases this returns an empty selection. When legal cases
    exist, selection is stable by (case_source, syndrome_type,
    parent_complexity, rare_disease_bin, case_id).
    """
    if not legal:
        return {
            "selected": [],
            "selected_count": 0,
            "strata_counts": {},
            "target_min": target_min,
            "target_max": target_max,
        }

    def rare_bin(value: Any) -> str:
        if value is None:
            return "unknown"
        frac = float(value)
        if frac < 0.25:
            return "lt_0.25"
        if frac < 0.5:
            return "0.25_0.5"
        if frac < 0.75:
            return "0.5_0.75"
        return "gte_0.75"

    ordered = sorted(
        legal,
        key=lambda row: (
            str(row.get("case_source") or ""),
            str(row.get("syndrome_type") or ""),
            str(row.get("parent_complexity") or ""),
            rare_bin(row.get("rare_disease_fraction")),
            str(row.get("case_id") or ""),
        ),
    )
    selected = list(ordered[:target_max])
    strata = Counter(
        (
            str(row.get("case_source") or "unknown"),
            str(row.get("syndrome_type") or "unknown"),
            str(row.get("parent_complexity") or "unknown"),
            rare_bin(row.get("rare_disease_fraction")),
        )
        for row in selected
    )
    return {
        "selected": selected,
        "selected_count": len(selected),
        "strata_counts": {
            "|".join(key): count for key, count in sorted(strata.items())
        },
        "target_min": target_min,
        "target_max": target_max,
    }


def _strip_algorithm_outputs_from_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Holdout case payload: inputs/labels/strata only."""
    return {
        "case_id": case["case_id"],
        "case_source": case.get("case_source"),
        "source_path": case.get("source_path"),
        "source_index": case.get("source_index"),
        "vignette": case.get("vignette"),
        "gold": case.get("gold"),
        "gold_option": case.get("gold_option"),
        "strata": {
            "case_source": case.get("case_source"),
            "syndrome_type": case.get("syndrome_type"),
            "parent_complexity": case.get("parent_complexity"),
            "rare_disease_fraction": case.get("rare_disease_fraction"),
        },
        "calibration_status": case.get("calibration_status"),
        "content_fingerprint": case.get("content_fingerprint"),
    }


def build_execution_interface(
    *,
    holdout_status: str,
    case_count: int,
    winner_path: Path = DEFAULT_WINNER_PATH,
) -> dict[str, Any]:
    winner_exists = winner_path.exists()
    winner_frozen = False
    winner_id = None
    if winner_exists:
        winner_doc = _read_json(winner_path)
        winner_frozen = bool(winner_doc.get("frozen") is True)
        winner_id = winner_doc.get("winner_arm") or winner_doc.get("arm")
        if winner_doc.get("fixture_hash"):
            verify_sealed(winner_doc, label="frozen development winner")

    ready = (
        holdout_status == "sealed"
        and case_count >= MIN_CASES
        and winner_frozen
        and bool(winner_id)
    )
    blockers: list[str] = []
    if holdout_status != "sealed":
        blockers.append("holdout_not_sealed_with_legal_cases")
    if case_count < MIN_CASES:
        blockers.append(f"holdout_case_count_below_min:{case_count}<{MIN_CASES}")
    if not winner_frozen:
        blockers.append("frozen_development_winner_missing_or_unfrozen")
    if winner_frozen and not winner_id:
        blockers.append("frozen_development_winner_missing_arm_id")

    return {
        "schema_version": SCHEMA_VERSION,
        "interface_id": "l2_a_variant_holdout_c_vs_winner_v1",
        "arms": list(HOLDOUT_ARMS),
        "replicates_per_case": 3,
        "study_design": "confirmatory_holdout",
        "ready_to_execute": ready,
        "promotion_eligible": False,
        "pre_run_forbidden_until_ready": True,
        "blockers": blockers,
        "winner_fixture_path": _relative(winner_path),
        "winner_arm": winner_id,
        "winner_frozen": winner_frozen,
        "holdout_status": holdout_status,
        "holdout_case_count": case_count,
        "execution_plan": {
            "stage_order": [
                "validate_holdout_fixture",
                "validate_frozen_development_winner",
                "generate_C-prod_and_frozen_development_winner",
                "downstream_replay",
                "confirmatory_closed_testing",
            ],
            "forbidden_actions_until_ready": [
                "generate",
                "downstream",
                "evaluate",
                "promotion_verdict",
            ],
        },
    }


def assert_execution_ready(interface: Mapping[str, Any]) -> None:
    if interface.get("ready_to_execute") is True:
        return
    blockers = interface.get("blockers") or []
    raise RuntimeError(
        "holdout confirmatory execution is not ready: "
        + ", ".join(map(str, blockers))
    )


def build_holdout_document(
    *,
    protocol: Mapping[str, Any],
    pools: Mapping[str, Any],
    legality: Mapping[str, Any],
    selection: Mapping[str, Any],
    builder_code_sha256: str,
) -> dict[str, Any]:
    legal_count = int(legality["legal_candidate_count"])
    selected = list(selection.get("selected") or [])
    selected_count = len(selected)
    enough = selected_count >= MIN_CASES
    status = "sealed" if enough else "blocked"

    pool_summary = {
        name: {
            "source_path": pool.get("source_path"),
            "source_exists": pool.get("source_exists"),
            "raw_row_count": pool.get("raw_row_count"),
            "row_count": pool.get("row_count"),
            "candidate_count": pool.get("candidate_count"),
            "notes": pool.get("notes"),
            "sources": pool.get("sources"),
        }
        for name, pool in pools.items()
    }

    cases = [_strip_algorithm_outputs_from_case(case) for case in selected] if enough else []
    case_ids = [str(case["case_id"]) for case in cases]
    algo_hits = _contains_algorithm_outputs({"cases": cases})

    blockers: list[str] = []
    if not enough:
        blockers.extend([
            f"legal_candidate_count_below_min:{legal_count}<{MIN_CASES}",
            "refusing_to_fabricate_holdout_cases",
            "refusing_to_run_confirmatory_results",
        ])
    if int(legality["development_overlap_count"]) != 0:
        blockers.append("development_overlap_nonzero")
    if algo_hits:
        blockers.append("algorithm_outputs_detected_in_cases")

    gap = max(0, MIN_CASES - legal_count)
    preferred_gap = max(0, PREFERRED_RANGE[0] - legal_count)

    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": FIXTURE_ID,
        "frozen": True,
        "status": status,
        "cohort_role": "holdout",
        "promotion_eligible": False,
        "protocol_binding": {
            "protocol_path": _relative(PROTOCOL_PATH),
            "protocol_sha256": (
                _sha256_file(PROTOCOL_PATH) if PROTOCOL_PATH.exists() else None
            ),
            "development_case_ids": development_case_ids(protocol),
            "holdout_spec": protocol.get("holdout"),
        },
        "sample_size_rule": {
            "min_cases_required": MIN_CASES,
            "preferred_case_range": list(PREFERRED_RANGE),
            "replicates_do_not_increase_external_sample_size": True,
        },
        "stratification_axes": list(STRATIFICATION_AXES),
        "case_count": selected_count if enough else 0,
        "case_ids": case_ids,
        "cases": cases,
        "available_legal_candidates": legal_count,
        "gap_to_minimum": gap,
        "gap_to_preferred_lower_bound": preferred_gap,
        "development_overlap_count": int(legality["development_overlap_count"]),
        "development_overlap_case_ids": list(
            legality["development_overlap_case_ids"]
        ),
        "deduplicate_before_sealing": True,
        "algorithm_outputs_present": bool(algo_hits),
        "algorithm_output_paths_detected": algo_hits,
        "candidate_pool_audit": pool_summary,
        "legality_audit": {
            "scanned_candidate_count": legality["scanned_candidate_count"],
            "legal_candidate_count": legal_count,
            "exclusion_reason_counts": legality["exclusion_reason_counts"],
            "historical_scheme_selection_case_id_count": legality[
                "historical_scheme_selection_case_id_count"
            ],
            "exclusion_count": len(legality["exclusions"]),
        },
        "exclusions": legality["exclusions"],
        "selection": {
            "selected_count": selected_count if enough else 0,
            "strata_counts": selection.get("strata_counts") if enough else {},
            "target_min": selection.get("target_min"),
            "target_max": selection.get("target_max"),
        },
        "blockers": blockers,
        "builder": {
            "script": "scripts/build_l2_a_variant_holdout.py",
            "code_sha256": builder_code_sha256,
            "reproducible": True,
        },
        "arms": list(HOLDOUT_ARMS),
        "notes": [
            "Holdout cases must exclude the 17 development/scheme-selection cases.",
            "Raw MedXpert/MedBullets TSV rows are inventoried but not legal until "
            "TALP-grade calibration, strata, and contamination clearance exist.",
            "Confirmatory execution requires a separately frozen development winner.",
        ],
    }
    return seal_payload(doc)


def build_blocked_manifest(holdout_doc: Mapping[str, Any]) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": "l2_a_variant_holdout_v1_blocked",
        "frozen": True,
        "status": holdout_doc.get("status"),
        "promotion_eligible": False,
        "fixture_id": holdout_doc.get("fixture_id"),
        "fixture_hash": holdout_doc.get("fixture_hash"),
        "available_legal_candidates": holdout_doc.get("available_legal_candidates"),
        "gap_to_minimum": holdout_doc.get("gap_to_minimum"),
        "gap_to_preferred_lower_bound": holdout_doc.get(
            "gap_to_preferred_lower_bound"
        ),
        "min_cases_required": MIN_CASES,
        "preferred_case_range": list(PREFERRED_RANGE),
        "development_overlap_count": holdout_doc.get("development_overlap_count"),
        "development_overlap_case_ids": holdout_doc.get(
            "development_overlap_case_ids"
        ),
        "candidate_pool_audit": holdout_doc.get("candidate_pool_audit"),
        "legality_audit": holdout_doc.get("legality_audit"),
        "blockers": holdout_doc.get("blockers"),
        "exclusion_reason_counts": (
            (holdout_doc.get("legality_audit") or {}).get("exclusion_reason_counts")
        ),
    }
    return seal_payload(manifest)


def run_build(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    blocked_manifest_path: Path = DEFAULT_BLOCKED_MANIFEST,
    execution_interface_path: Path = DEFAULT_EXECUTION_INTERFACE,
    winner_path: Path = DEFAULT_WINNER_PATH,
    protocol_path: Path = PROTOCOL_PATH,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    dev_ids = development_case_ids(protocol)
    dev_fps = collect_development_fingerprints(protocol)
    pools = inventory_candidate_pools()
    legality = evaluate_legality(
        pools, development_ids=dev_ids, development_fps=dev_fps,
    )
    selection = stratified_select(legality["legal_candidates"])
    builder_sha = _sha256_file(Path(__file__))
    holdout_doc = build_holdout_document(
        protocol=protocol,
        pools=pools,
        legality=legality,
        selection=selection,
        builder_code_sha256=builder_sha,
    )
    verify_sealed(holdout_doc, label="holdout fixture")
    if holdout_doc["development_overlap_count"] != 0:
        raise ValueError("refusing to write holdout with development overlap")
    if holdout_doc["algorithm_outputs_present"]:
        raise ValueError("refusing to write holdout containing algorithm outputs")

    _atomic_json(fixture_path, holdout_doc)

    interface = build_execution_interface(
        holdout_status=str(holdout_doc["status"]),
        case_count=int(holdout_doc["case_count"]),
        winner_path=winner_path,
    )
    interface = seal_payload(interface)
    verify_sealed(interface, label="execution interface")
    _atomic_json(execution_interface_path, interface)

    blocked_manifest = None
    if holdout_doc["status"] == "blocked":
        blocked_manifest = build_blocked_manifest(holdout_doc)
        verify_sealed(blocked_manifest, label="blocked manifest")
        _atomic_json(blocked_manifest_path, blocked_manifest)

    return {
        "status": holdout_doc["status"],
        "promotion_eligible": False,
        "fixture_path": _relative(fixture_path),
        "fixture_hash": holdout_doc["fixture_hash"],
        "case_count": holdout_doc["case_count"],
        "available_legal_candidates": holdout_doc["available_legal_candidates"],
        "gap_to_minimum": holdout_doc["gap_to_minimum"],
        "development_overlap_count": holdout_doc["development_overlap_count"],
        "execution_interface_path": _relative(execution_interface_path),
        "execution_ready": interface["ready_to_execute"],
        "blocked_manifest_path": (
            _relative(blocked_manifest_path) if blocked_manifest else None
        ),
        "blocked_manifest_hash": (
            blocked_manifest.get("fixture_hash") if blocked_manifest else None
        ),
    }


def prepare_execution_only(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    execution_interface_path: Path = DEFAULT_EXECUTION_INTERFACE,
    winner_path: Path = DEFAULT_WINNER_PATH,
) -> dict[str, Any]:
    """Refresh the C vs winner interface without running confirmatory jobs."""
    if not fixture_path.exists():
        raise FileNotFoundError(f"missing holdout fixture: {fixture_path}")
    holdout_doc = _read_json(fixture_path)
    verify_sealed(holdout_doc, label="holdout fixture")
    interface = build_execution_interface(
        holdout_status=str(holdout_doc.get("status")),
        case_count=int(holdout_doc.get("case_count") or 0),
        winner_path=winner_path,
    )
    interface = seal_payload(interface)
    verify_sealed(interface, label="execution interface")
    _atomic_json(execution_interface_path, interface)
    # Hard gate: never silently execute.
    try:
        assert_execution_ready(interface)
        ready = True
    except RuntimeError:
        ready = False
    return {
        "status": "prepared",
        "ready_to_execute": ready,
        "promotion_eligible": False,
        "execution_interface_path": _relative(execution_interface_path),
        "blockers": interface.get("blockers"),
        "arms": interface.get("arms"),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=("build", "prepare-execution", "validate"),
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--blocked-manifest", type=Path, default=DEFAULT_BLOCKED_MANIFEST,
    )
    parser.add_argument(
        "--execution-interface",
        type=Path,
        default=DEFAULT_EXECUTION_INTERFACE,
    )
    parser.add_argument("--winner", type=Path, default=DEFAULT_WINNER_PATH)
    return parser.parse_args(argv)


def validate_fixture(path: Path) -> dict[str, Any]:
    doc = _read_json(path)
    verify_sealed(doc, label="holdout fixture")
    if doc.get("frozen") is not True:
        raise ValueError("holdout fixture must set frozen=true")
    if doc.get("promotion_eligible") is not False:
        raise ValueError("holdout fixture must set promotion_eligible=false until confirmed")
    if doc.get("development_overlap_count") != 0:
        raise ValueError("development overlap must be 0")
    if doc.get("algorithm_outputs_present"):
        raise ValueError("algorithm outputs forbidden in holdout fixture")
    if doc.get("status") == "sealed" and int(doc.get("case_count") or 0) < MIN_CASES:
        raise ValueError("sealed holdout below minimum case count")
    if doc.get("status") == "blocked" and int(doc.get("case_count") or 0) != 0:
        raise ValueError("blocked holdout must not invent cases")
    return {
        "status": "OK",
        "fixture_status": doc.get("status"),
        "fixture_hash": doc.get("fixture_hash"),
        "case_count": doc.get("case_count"),
        "available_legal_candidates": doc.get("available_legal_candidates"),
        "promotion_eligible": doc.get("promotion_eligible"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.stage == "build":
        result = run_build(
            fixture_path=args.fixture,
            blocked_manifest_path=args.blocked_manifest,
            execution_interface_path=args.execution_interface,
            winner_path=args.winner,
            protocol_path=args.protocol,
        )
    elif args.stage == "prepare-execution":
        result = prepare_execution_only(
            fixture_path=args.fixture,
            execution_interface_path=args.execution_interface,
            winner_path=args.winner,
        )
    else:
        result = validate_fixture(args.fixture)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
