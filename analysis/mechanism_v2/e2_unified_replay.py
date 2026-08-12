#!/usr/bin/env python3
"""Build the exhaustive 800-case five-endpoint E2 replay.

This module corrects two measurement errors in the historical analysis:

* ``chain_correct`` was a permissive substring/resolver projection, not the
  exact/frozen-synonym endpoint that later reports called ``strict``; and
* the first E2 root audit clinically adjudicated a stratified 400-case sample
  and design-weighted it to the 800-case mechanism universe.  It was not an
  exhaustive 800-case clinical census.

The replay therefore keeps five non-interchangeable binary columns:

``safe_exact``
    Exact or frozen-safe-synonym equivalence, recomputed from the champion.
``legacy_chain``
    The historical substring/resolver ``chain_correct`` value, retained only
    for backward compatibility and interface diagnosis.
``clinical_complete``
    Root-owned complete clinical equivalence to the requested reference.
``partial``
    Root-owned compatible parent/component/underspecified relation.  This is
    partial-only, not ``complete OR partial``.
``task``
    The frozen benchmark interface outcome.  DA uses the option mapper; MCR
    uses the cached official semantic diagnostic judge.

No online call is made.  ``freeze-audit`` writes blinded cards for the 400
cases absent from the original E2 clinical sample.  ``replay`` fails closed
until every frozen identity and non-safe candidate relation has a root code in
``e2_unified_root_decisions.py``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import (  # noqa: E402
    FrozenExactSynonymBridge,
    ROOT,
    file_sha256,
    normalize_label,
)
from analysis.mechanism_v2.e2_blinded_adjudication import (  # noqa: E402
    CHAIN_PATH,
    SCORED_PATH,
    _bool_cell,
    _load_case_universe,
    key_for,
    read_table,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


EXPERIMENT_ID = "E2-unified-800-replay"
DEFAULT_E2 = ROOT / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication"
DEFAULT_OUT = DEFAULT_E2 / "unified_800"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
ROOT_RELATIONS_PATH = DEFAULT_E2 / "root_audit/resolved_relations.jsonl"
ROOT_IDENTITIES_PATH = DEFAULT_E2 / "root_audit/resolved_identities.jsonl"
FROZEN_SAMPLE_PATH = DEFAULT_E2 / "design/selection.jsonl"

RELATION_CODE_MAP = {
    "C": "complete_equivalent",
    "P": "partial_parent_or_component",
    "X": "conflicting_subtype_or_scope",
    "M": "manifestation_or_related",
    "N": "not_equivalent",
    "U": "uncertain",
}
IDENTITY_CODE_MAP = {
    "Q": "unique_full_reference",
    "F": "family_only_not_full_specificity",
    "M": "multiple_complete_answers",
    "S": "unsupported_reference_specificity",
    "I": "insufficient_case_information",
    "U": "uncertain",
}
CORE_ARMS = (
    "collapse3c",
    "multistance",
    "lite",
    "forest",
    "impc",
    "e7",
    "v0",
    "B06",
    "B07",
)
RELATION_ORDER = (
    "complete_equivalent",
    "partial_parent_or_component",
    "conflicting_subtype_or_scope",
    "manifestation_or_related",
    "not_equivalent",
    "uncertain",
)
CONTRAST_PAIRS = (
    ("collapse3c", "multistance"),
    ("collapse3c", "forest"),
    ("collapse3c", "impc"),
    ("e7", "v0"),
    ("forest", "e7"),
    ("forest", "B06"),
    ("B06", "e7"),
    ("B07", "e7"),
    ("B07", "B06"),
    ("forest", "lite"),
)


def _root_codes() -> tuple[str, str]:
    try:
        from analysis.mechanism_v2.e2_unified_root_decisions import (  # type: ignore
            IDENTITY_DECISION_CODES,
            RELATION_DECISION_CODES,
        )
    except ImportError:
        return "", ""
    return str(IDENTITY_DECISION_CODES), str(RELATION_DECISION_CODES)


def _sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (dict, list, tuple))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def _audit_case_order(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            stable_seed(EXPERIMENT_ID, "blind-case", str(row["case_key"])),
            str(row["case_key"]),
        ),
    )


def _audit_candidate_order(case_key: str, rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            stable_seed(EXPERIMENT_ID, "blind-candidate", case_key, str(row["candidate_id"])),
            str(row["candidate_id"]),
        ),
    )


def freeze_audit(out: Path = DEFAULT_OUT) -> dict[str, Any]:
    """Freeze blinded cards for cases not clinically adjudicated in E2 v1."""
    universe, source_hashes = _load_case_universe()
    old_sample = {str(row["case_key"]) for row in read_jsonl(FROZEN_SAMPLE_PATH)}
    missing = [row for row in universe if str(row["case_key"]) not in old_sample]
    if len(universe) != 800 or len(old_sample) != 400 or len(missing) != 400:
        raise AssertionError("expected an 800 universe split into 400 old + 400 new cases")

    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    cards: list[dict[str, Any]] = []
    index: list[dict[str, Any]] = []
    relation_records = 0
    safe_records = 0
    for case_index, row in enumerate(_audit_case_order(missing), 1):
        case_key = str(row["case_key"])
        core_candidate_ids = {
            str(row["arm_map"][arm]["candidate_id"])
            for arm in CORE_ARMS
            if arm in row["arm_map"]
        }
        core_candidates = [
            candidate
            for candidate in row["candidate_registry"]
            if str(candidate["candidate_id"]) in core_candidate_ids
        ]
        candidates = []
        for candidate_index, candidate in enumerate(
            _audit_candidate_order(case_key, core_candidates), 1
        ):
            safe = bridge.equivalent(str(candidate["label"]), str(row["gold"]))
            blind_candidate_id = f"U{case_index:04d}C{candidate_index:02d}"
            if not safe:
                candidates.append(
                    {
                        "blind_candidate_id": blind_candidate_id,
                        "candidate_label": str(candidate["label"]),
                    }
                )
            index.append(
                {
                    "blind_candidate_id": blind_candidate_id,
                    "blind_case_id": f"U{case_index:04d}",
                    "case_key": case_key,
                    "candidate_id": str(candidate["candidate_id"]),
                    "candidate_label": str(candidate["label"]),
                    "safe_exact": safe,
                }
            )
            safe_records += int(safe)
            relation_records += int(not safe)
        cards.append(
            {
                "blind_case_id": f"U{case_index:04d}",
                "clinical_record": str(row["vignette"]),
                "reference_diagnosis": str(row["gold"]),
                "candidate_registry": candidates,
            }
        )

    out.mkdir(parents=True, exist_ok=True)
    audit = out / "root_audit"
    audit.mkdir(parents=True, exist_ok=True)
    write_jsonl(audit / "cards.jsonl", cards)
    write_jsonl(audit / "index.jsonl", index)
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "created_at_utc": _utcnow(),
        "universe_n": 800,
        "old_e2_cases_n": 400,
        "new_root_audit_cases_n": len(cards),
        "candidate_relations_n": len(index),
        "deterministic_safe_exact_relations_n": safe_records,
        "root_relation_codes_required_n": relation_records,
        "root_identity_codes_required_n": len(cards),
        "arm_scope": list(CORE_ARMS),
        "candidate_scope": "union of champions emitted by the nine full-800 arms only",
        "blind_contract": (
            "cards exclude case keys, family, slice, arm provenance, all historical endpoint flags, "
            "sampling strata and leaderboard position"
        ),
        "source_hashes": source_hashes,
        "bridge_sha256": bridge.sha256,
        "cards_sha256": file_sha256(audit / "cards.jsonl"),
        "index_sha256": file_sha256(audit / "index.jsonl"),
    }
    atomic_json(audit / "freeze_summary.json", summary)
    (audit / "ROOT_PROTOCOL.md").write_text(
        "# Exhaustive E2 root protocol\n\n"
        "The root auditor reads `cards.jsonl` without `index.jsonl`. Cases and candidates "
        "are deterministically shuffled. Codes are frozen before restoring case keys, arm "
        "provenance, legacy-chain, task, or prior leaderboard results.\n\n"
        "Identity codes: `Q` unique full reference; `F` family identifiable but full "
        "specificity not compelled; `M` multiple complete answers; `S` reference contains "
        "unsupported specificity; `I` insufficient case information; `U` genuinely "
        "uncertain.\n\n"
        "Relation codes: `C` complete equivalent; `P` compatible parent/component or "
        "underspecified object; `X` conflicting subtype/scope; `M` manifestation/related "
        "object; `N` different entity; `U` genuinely uncertain. Safe exact/frozen-synonym "
        "relations are deterministically `C` and do not consume a manual relation code.\n",
        encoding="utf-8",
    )
    return summary


def _decode_codes(raw: str, allowed: Mapping[str, str], n: int, label: str) -> list[str]:
    codes = "".join(raw.split()).upper()
    if len(codes) != n:
        raise AssertionError(f"{label} coverage {len(codes)}/{n}")
    invalid = sorted(set(codes) - set(allowed))
    if invalid:
        raise AssertionError(f"{label} invalid codes: {invalid}")
    return [allowed[code] for code in codes]


def _new_root_decisions(out: Path) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    cards = read_jsonl(out / "root_audit/cards.jsonl")
    index = read_jsonl(out / "root_audit/index.jsonl")
    identity_raw, relation_raw = _root_codes()
    identities = _decode_codes(identity_raw, IDENTITY_CODE_MAP, len(cards), "identity")
    manual_index = [row for row in index if not bool(row["safe_exact"])]
    relations = _decode_codes(relation_raw, RELATION_CODE_MAP, len(manual_index), "relation")
    identity_by_blind = {
        str(card["blind_case_id"]): value for card, value in zip(cards, identities)
    }
    by_blind_relation = {
        str(row["blind_candidate_id"]): value for row, value in zip(manual_index, relations)
    }
    case_by_blind = {
        str(row["blind_case_id"]): str(row["case_key"])
        for row in index
    }
    identity_by_case = {
        case_by_blind[blind_id]: value for blind_id, value in identity_by_blind.items()
    }
    relation_by_key: dict[tuple[str, str], str] = {}
    for row in index:
        relation = (
            "complete_equivalent"
            if bool(row["safe_exact"])
            else by_blind_relation[str(row["blind_candidate_id"])]
        )
        relation_by_key[(str(row["case_key"]), str(row["candidate_id"]))] = relation
    return identity_by_case, relation_by_key


def _old_root_decisions() -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    identities = {
        str(row["case_key"]): str(row["judgment"])
        for row in read_jsonl(ROOT_IDENTITIES_PATH)
    }
    relations = {
        (str(row["case_key"]), str(row["candidate_id"])): str(row["relation"])
        for row in read_jsonl(ROOT_RELATIONS_PATH)
    }
    return identities, relations


def _safe_match_kind(label: str, gold: str, bridge: FrozenExactSynonymBridge) -> str:
    if not bridge.equivalent(label, gold):
        return "none"
    return "normalized_exact" if normalize_label(label) == normalize_label(gold) else "frozen_safe_synonym"


def _arm_rows(universe: Sequence[Mapping[str, Any]], out: Path) -> list[dict[str, Any]]:
    old_identities, old_relations = _old_root_decisions()
    new_identities, new_relations = _new_root_decisions(out)
    identity = {**old_identities, **new_identities}
    relations = {**old_relations, **new_relations}
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)

    if len(identity) != 800:
        raise AssertionError(f"identity census coverage {len(identity)}/800")
    rows: list[dict[str, Any]] = []
    for case in sorted(universe, key=lambda row: str(row["case_key"])):
        case_key = str(case["case_key"])
        for arm in CORE_ARMS:
            mapping = case["arm_map"].get(arm)
            if not mapping:
                raise AssertionError(f"missing {arm} output for {case_key}")
            candidate_id = str(mapping["candidate_id"])
            relation = relations.get((case_key, candidate_id))
            if relation is None:
                raise AssertionError(f"missing root relation for {case_key}/{candidate_id}")
            safe_exact = bridge.equivalent(str(mapping["surface_label"]), str(case["gold"]))
            if safe_exact and relation != "complete_equivalent":
                raise AssertionError(f"safe identity contradicted by root relation: {case_key}/{arm}")
            rows.append(
                {
                    "schema_version": "e2-unified-five-endpoint-v1",
                    "case_key": case_key,
                    "benchmark_family": str(case["family"]),
                    "slice_id": str(case["slice_id"]),
                    "source_id": str(case["source_id"]),
                    "arm_id": arm,
                    "method_family": str(mapping["method_family"]),
                    "eligible": True,
                    "served": True,
                    "reference_diagnosis": str(case["gold"]),
                    "prediction_pre_projection": str(mapping["surface_label"]),
                    "output_cluster_id": candidate_id,
                    "reference_identifiability": identity[case_key],
                    "clinical_relation": relation,
                    "clinical_audit_source": (
                        "e2_v1_blinded_root_census_sample"
                        if case_key in old_identities
                        else "e2_v2_blinded_root_census_supplement"
                    ),
                    "clinical_audit_status": "root_adjudicated",
                    "e2_v1_sampled": case_key in old_identities,
                    "analysis_weight": 1.0,
                    "safe_exact": safe_exact,
                    "safe_exact_match_kind": _safe_match_kind(
                        str(mapping["surface_label"]), str(case["gold"]), bridge
                    ),
                    "legacy_chain": bool(mapping["strict_chain_correct"]),
                    "clinical_complete": relation == "complete_equivalent",
                    "partial": relation == "partial_parent_or_component",
                    "task": bool(mapping["task_correct"]),
                    "task_contract": (
                        "da_option_mapper" if case["family"] == "DA" else "mcr_cached_semantic_judge"
                    ),
                }
            )
    if len(rows) != 800 * len(CORE_ARMS):
        raise AssertionError("incomplete arm-by-case replay")
    return rows


def _validate_source_contract(
    universe: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], out: Path
) -> dict[str, Any]:
    if len(universe) != 800 or Counter(row["family"] for row in universe) != {"DA": 400, "MCR": 400}:
        raise AssertionError("unified replay requires exactly DA400 + MCR400")
    if len(rows) != 7200:
        raise AssertionError(f"expected 7200 case-arm rows, found {len(rows)}")
    unique = {(str(row["case_key"]), str(row["arm_id"])) for row in rows}
    if len(unique) != len(rows):
        raise AssertionError("duplicate case-arm replay key")
    arm_counts = Counter(str(row["arm_id"]) for row in rows)
    if arm_counts != {arm: 800 for arm in CORE_ARMS}:
        raise AssertionError(f"incomplete full-domain arms: {arm_counts}")
    family_arm = Counter((str(row["benchmark_family"]), str(row["arm_id"])) for row in rows)
    expected_family_arm = {(family, arm): 400 for family in ("DA", "MCR") for arm in CORE_ARMS}
    if family_arm != expected_family_arm:
        raise AssertionError("every arm must have DA400 and MCR400")

    chain = {key_for(row): row for row in read_table(CHAIN_PATH)}
    scored = {key_for(row): row for row in read_table(SCORED_PATH)}
    matrix_chain_mismatches = 0
    matrix_task_mismatches = 0
    case_by_key = {
        (str(case["dataset"]), str(case["slice"]), str(case["source_id"])): case
        for case in universe
    }
    for row in rows:
        case_key = str(row["case_key"])
        case = next(case for case in universe if str(case["case_key"]) == case_key)
        key = (str(case["dataset"]), str(case["slice"]), str(case["source_id"]))
        if key not in case_by_key or key not in chain or key not in scored:
            raise AssertionError(f"missing matrix source for {key}")
        arm = str(row["arm_id"])
        matrix_chain_mismatches += int(_bool_cell(chain[key][arm]) != bool(row["legacy_chain"]))
        matrix_task_mismatches += int(_bool_cell(scored[key][arm]) != bool(row["task"]))
    if matrix_chain_mismatches or matrix_task_mismatches:
        raise AssertionError(
            f"dual/matrix mismatch chain={matrix_chain_mismatches} task={matrix_task_mismatches}"
        )

    old_relations_n = len(read_jsonl(ROOT_RELATIONS_PATH))
    old_identities_n = len(read_jsonl(ROOT_IDENTITIES_PATH))
    new_cards = read_jsonl(out / "root_audit/cards.jsonl")
    new_index = read_jsonl(out / "root_audit/index.jsonl")
    expected_audit = (old_relations_n, old_identities_n, len(new_cards), len(new_index))
    if expected_audit != (1673, 400, 400, 1430):
        raise AssertionError(f"unexpected root audit coverage {expected_audit}")
    contradictions = sum(
        bool(row["safe_exact"]) and not bool(row["clinical_complete"]) for row in rows
    )
    overlaps = sum(bool(row["clinical_complete"]) and bool(row["partial"]) for row in rows)
    if contradictions or overlaps:
        raise AssertionError(f"endpoint contract contradiction={contradictions} overlap={overlaps}")

    safe_legacy = Counter(
        (bool(row["safe_exact"]), bool(row["legacy_chain"])) for row in rows
    )
    return {
        "schema_version": "e2-unified-five-endpoint-v1",
        "cases_n": len(universe),
        "case_arm_rows_n": len(rows),
        "arm_counts": dict(sorted(arm_counts.items())),
        "family_arm_counts": {
            f"{family}:{arm}": n for (family, arm), n in sorted(family_arm.items())
        },
        "old_e2_root_cases_n": old_identities_n,
        "old_e2_root_candidate_relations_n": old_relations_n,
        "supplemental_root_cases_n": len(new_cards),
        "supplemental_candidate_registry_n": len(new_index),
        "supplemental_manual_relation_codes_n": sum(
            not bool(row["safe_exact"]) for row in new_index
        ),
        "matrix_legacy_chain_mismatches_n": matrix_chain_mismatches,
        "matrix_task_mismatches_n": matrix_task_mismatches,
        "safe_exact_root_contradictions_n": contradictions,
        "complete_partial_overlap_n": overlaps,
        "safe_exact_by_legacy_chain": {
            f"safe_{int(safe)}_legacy_{int(legacy)}": safe_legacy[(safe, legacy)]
            for safe in (False, True)
            for legacy in (False, True)
        },
        "clinical_missing_n": 0,
        "task_semantics": {
            "DA": "option mapper",
            "MCR": "cached semantic diagnostic judge",
            "combined": "heterogeneous interface summary; not a homogeneous capability estimand",
        },
    }


def _rate(rows: Sequence[Mapping[str, Any]], endpoint: str) -> float:
    return sum(bool(row[endpoint]) for row in rows) / len(rows) if rows else math.nan


def _wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float | None]:
    if n == 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [centre - half, centre + half]


def _confusion(rows: Sequence[Mapping[str, Any]], predicted: str, truth: str) -> dict[str, Any]:
    tp = sum(bool(row[predicted]) and bool(row[truth]) for row in rows)
    fp = sum(bool(row[predicted]) and not bool(row[truth]) for row in rows)
    fn = sum(not bool(row[predicted]) and bool(row[truth]) for row in rows)
    tn = len(rows) - tp - fp - fn
    sensitivity = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    ppv = tp / (tp + fp) if tp + fp else None
    npv = tn / (tn + fn) if tn + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    balanced_accuracy = (
        (sensitivity + specificity) / 2
        if sensitivity is not None and specificity is not None
        else None
    )
    mcc_denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = (tp * tn - fp * fn) / mcc_denominator if mcc_denominator else None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "ppv": ppv,
        "npv": npv,
        "f1": f1,
        "balanced_accuracy": balanced_accuracy,
        "mcc": mcc,
    }


def _mcnemar_exact(left_only: int, right_only: int) -> float:
    n = left_only + right_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(left_only, right_only) + 1)) / (2**n)
    return min(1.0, 2 * tail)


def _paired_bootstrap(
    by_case: Mapping[str, tuple[bool, bool]], repetitions: int = 20000
) -> list[float]:
    keys = sorted(by_case)
    differences = [int(by_case[key][1]) - int(by_case[key][0]) for key in keys]
    counts = Counter(differences)
    probabilities = np.array([counts[-1], counts[0], counts[1]], dtype=float) / len(keys)
    rng = np.random.default_rng(stable_seed(EXPERIMENT_ID, "paired-bootstrap", *keys))
    draws = rng.multinomial(len(keys), probabilities, size=repetitions)
    effects = (draws[:, 2] - draws[:, 0]) / len(keys)
    return [float(value) for value in np.quantile(effects, [0.025, 0.975], method="nearest")]


def _stratified_paired_bootstrap(
    pairs_by_stratum: Mapping[str, Mapping[str, tuple[bool, bool]]],
    repetitions: int = 20000,
    namespace: str = "stratified-paired",
) -> list[float]:
    rng = np.random.default_rng(stable_seed(EXPERIMENT_ID, namespace, *sorted(pairs_by_stratum)))
    effects = np.zeros(repetitions, dtype=float)
    total_n = 0
    for stratum, pairs in sorted(pairs_by_stratum.items()):
        differences = [int(value[1]) - int(value[0]) for value in pairs.values()]
        counts = Counter(differences)
        n = len(differences)
        probabilities = np.array([counts[-1], counts[0], counts[1]], dtype=float) / n
        draws = rng.multinomial(n, probabilities, size=repetitions)
        effects += draws[:, 2] - draws[:, 0]
        total_n += n
    effects /= total_n
    return [float(value) for value in np.quantile(effects, [0.025, 0.975], method="nearest")]


def _holm_adjust(rows: Sequence[dict[str, Any]], p_key: str, out_key: str) -> None:
    order = sorted(range(len(rows)), key=lambda index: float(rows[index][p_key]))
    running = 0.0
    m = len(rows)
    for rank, index in enumerate(order):
        adjusted = min(1.0, (m - rank) * float(rows[index][p_key]))
        running = max(running, adjusted)
        rows[index][out_key] = running


def _transition_mechanism(left: str, right: str) -> str:
    if left == right:
        return "no_relation_change"
    if left == "partial_parent_or_component" and right == "complete_equivalent":
        return "specificity_rescue"
    if left not in {"complete_equivalent", "partial_parent_or_component"} and right == "complete_equivalent":
        return "object_rescue"
    if left == "complete_equivalent" and right == "partial_parent_or_component":
        return "scope_compression"
    if left == "complete_equivalent" and right != "complete_equivalent":
        return "catastrophic_substitution"
    if left == "partial_parent_or_component" and right not in {
        "complete_equivalent", "partial_parent_or_component"
    }:
        return "family_coverage_loss"
    if left not in {"complete_equivalent", "partial_parent_or_component"} and right == "partial_parent_or_component":
        return "family_coverage_rescue"
    return "wrong_object_exchange"


def _projection_decomposition(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "unit_warning": (
            "descriptive case-arm projection anatomy; the same case appears in nine arms and "
            "must not be treated as 7200 independent observations"
        ),
        "rows": [],
    }
    for scope in ("DA", "MCR"):
        for arm in (*CORE_ARMS, "MACRO_OUTPUT"):
            scoped = [
                row
                for row in rows
                if row["benchmark_family"] == scope
                and (arm == "MACRO_OUTPUT" or row["arm_id"] == arm)
            ]
            for proxy in ("safe_exact", "legacy_chain", "task"):
                confusion = _confusion(scoped, proxy, "clinical_complete")
                false_positive_relations = Counter(
                    str(row["clinical_relation"])
                    for row in scoped
                    if bool(row[proxy]) and not bool(row["clinical_complete"])
                )
                false_negative_relations = Counter(
                    str(row["clinical_relation"])
                    for row in scoped
                    if not bool(row[proxy]) and bool(row["clinical_complete"])
                )
                output["rows"].append(
                    {
                        "scope": scope,
                        "arm": arm,
                        "proxy": proxy,
                        "n": len(scoped),
                        **confusion,
                        "false_positive_relation_counts": dict(sorted(false_positive_relations.items())),
                        "false_negative_relation_counts": dict(sorted(false_negative_relations.items())),
                    }
                )
    return output


def _relation_transition_outputs(
    rows: Sequence[Mapping[str, Any]], out: Path
) -> list[dict[str, Any]]:
    row_map = {(str(row["case_key"]), str(row["arm_id"])): row for row in rows}
    case_keys = sorted({str(row["case_key"]) for row in rows})
    summary: list[dict[str, Any]] = []
    trajectories: list[dict[str, Any]] = []
    for left, right in CONTRAST_PAIRS:
        for scope in ("ALL", "DA", "MCR"):
            eligible = [
                key
                for key in case_keys
                if scope == "ALL" or row_map[(key, left)]["benchmark_family"] == scope
            ]
            matrix = Counter(
                (
                    str(row_map[(key, left)]["clinical_relation"]),
                    str(row_map[(key, right)]["clinical_relation"]),
                )
                for key in eligible
            )
            mechanisms = Counter(_transition_mechanism(a, b) for (a, b), n in matrix.items() for _ in range(n))
            summary.append(
                {
                    "left": left,
                    "right": right,
                    "scope": scope,
                    "n": len(eligible),
                    "transition_counts": {
                        f"{a} -> {b}": matrix[(a, b)] for a in RELATION_ORDER for b in RELATION_ORDER
                    },
                    "mechanism_counts": dict(sorted(mechanisms.items())),
                    "specificity_rescue_pp": 100 * mechanisms["specificity_rescue"] / len(eligible),
                    "object_rescue_pp": 100 * mechanisms["object_rescue"] / len(eligible),
                    "scope_compression_pp": 100 * mechanisms["scope_compression"] / len(eligible),
                    "catastrophic_substitution_pp": 100 * mechanisms["catastrophic_substitution"] / len(eligible),
                }
            )
        for key in case_keys:
            left_row, right_row = row_map[(key, left)], row_map[(key, right)]
            left_relation = str(left_row["clinical_relation"])
            right_relation = str(right_row["clinical_relation"])
            if left_relation == right_relation:
                continue
            trajectories.append(
                {
                    "case_key": key,
                    "benchmark_family": left_row["benchmark_family"],
                    "reference_identifiability": left_row["reference_identifiability"],
                    "reference_diagnosis": left_row["reference_diagnosis"],
                    "left_arm": left,
                    "left_prediction": left_row["prediction_pre_projection"],
                    "left_relation": left_relation,
                    "right_arm": right,
                    "right_prediction": right_row["prediction_pre_projection"],
                    "right_relation": right_relation,
                    "transition_mechanism": _transition_mechanism(left_relation, right_relation),
                }
            )
    write_jsonl(out / "trajectory_endpoint_transitions.jsonl", trajectories)
    return summary


def _identifiability_effect_modification(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    row_map = {(str(row["case_key"]), str(row["arm_id"])): row for row in rows}
    case_keys = sorted({str(row["case_key"]) for row in rows})
    output: list[dict[str, Any]] = []
    for left, right in CONTRAST_PAIRS:
        for scope in ("ALL", "DA", "MCR"):
            strata: dict[str, dict[str, tuple[bool, bool]]] = {
                "unique_full": {},
                "nonunique_full": {},
            }
            for key in case_keys:
                left_row, right_row = row_map[(key, left)], row_map[(key, right)]
                if scope != "ALL" and left_row["benchmark_family"] != scope:
                    continue
                stratum = (
                    "unique_full"
                    if left_row["reference_identifiability"] == "unique_full_reference"
                    else "nonunique_full"
                )
                strata[stratum][key] = (
                    bool(left_row["clinical_complete"]), bool(right_row["clinical_complete"])
                )
            deltas = {
                name: sum(int(b) - int(a) for a, b in pairs.values()) / len(pairs)
                for name, pairs in strata.items()
            }
            cis = {
                name: _paired_bootstrap(pairs, 20000)
                for name, pairs in strata.items()
            }
            output.append(
                {
                    "left": left,
                    "right": right,
                    "scope": scope,
                    "endpoint": "clinical_complete",
                    "unique_full_n": len(strata["unique_full"]),
                    "nonunique_full_n": len(strata["nonunique_full"]),
                    "unique_full_delta_right_minus_left": deltas["unique_full"],
                    "unique_full_ci95": cis["unique_full"],
                    "nonunique_full_delta_right_minus_left": deltas["nonunique_full"],
                    "nonunique_full_ci95": cis["nonunique_full"],
                    "interaction_delta_unique_minus_nonunique": (
                        deltas["unique_full"] - deltas["nonunique_full"]
                    ),
                }
            )
    return output


def _reference_identifiability_outputs(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    case_rows: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        case_rows.setdefault(str(row["case_key"]), row)
    identity_order = tuple(IDENTITY_CODE_MAP.values())
    census = []
    for scope in ("ALL", "DA", "MCR"):
        scoped = [
            row
            for row in case_rows.values()
            if scope == "ALL" or row["benchmark_family"] == scope
        ]
        counts = Counter(str(row["reference_identifiability"]) for row in scoped)
        census.append(
            {
                "scope": scope,
                "n": len(scoped),
                "identity_counts": {name: counts[name] for name in identity_order},
                "unique_full_n": counts["unique_full_reference"],
                "unique_full_rate": counts["unique_full_reference"] / len(scoped),
                "unique_full_wilson95": _wilson(counts["unique_full_reference"], len(scoped)),
            }
        )
    endpoint_strata = []
    for arm in CORE_ARMS:
        for scope in ("ALL", "DA", "MCR"):
            scoped = [
                row
                for row in rows
                if row["arm_id"] == arm
                and (scope == "ALL" or row["benchmark_family"] == scope)
            ]
            for identity in (*identity_order, "nonunique_full"):
                stratum = [
                    row
                    for row in scoped
                    if (
                        row["reference_identifiability"] == identity
                        if identity != "nonunique_full"
                        else row["reference_identifiability"] != "unique_full_reference"
                    )
                ]
                k = sum(bool(row["clinical_complete"]) for row in stratum)
                endpoint_strata.append(
                    {
                        "arm": arm,
                        "scope": scope,
                        "reference_identifiability": identity,
                        "n": len(stratum),
                        "clinical_complete_n": k,
                        "clinical_complete_rate": k / len(stratum) if stratum else None,
                        "clinical_complete_wilson95": _wilson(k, len(stratum)),
                    }
                )
    return {
        "case_census": census,
        "clinical_complete_by_arm_scope_identity": endpoint_strata,
        "interpretation": (
            "reference identifiability is a mandatory effect modifier; relation-to-recorded-reference "
            "and whether the record uniquely supports that reference are not collapsed into one label"
        ),
    }


def _rank_stability(rows: Sequence[Mapping[str, Any]], repetitions: int = 10000) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    row_map = {(str(row["case_key"]), str(row["arm_id"])): row for row in rows}
    case_meta = {
        str(row["case_key"]): (str(row["benchmark_family"]), str(row["slice_id"])) for row in rows
    }
    for family in ("DA", "MCR"):
        family_keys = sorted(key for key, (fam, _slice) in case_meta.items() if fam == family)
        by_slice: dict[str, list[str]] = defaultdict(list)
        for key in family_keys:
            by_slice[case_meta[key][1]].append(key)
        for endpoint in ("clinical_complete", "safe_exact", "legacy_chain", "task"):
            rng = np.random.default_rng(stable_seed(EXPERIMENT_ID, "rank", family, endpoint))
            totals = np.zeros((repetitions, len(CORE_ARMS)), dtype=float)
            for slice_id, keys in sorted(by_slice.items()):
                matrix = np.array(
                    [[int(bool(row_map[(key, arm)][endpoint])) for arm in CORE_ARMS] for key in keys],
                    dtype=float,
                )
                sampled = rng.integers(0, len(keys), size=(repetitions, len(keys)))
                totals += matrix[sampled].sum(axis=1)
            scores = totals / len(family_keys)
            greater = (scores[:, :, None] < scores[:, None, :]).sum(axis=2)
            ties = (scores[:, :, None] == scores[:, None, :]).sum(axis=2) - 1
            ranks = 1.0 + greater + 0.5 * ties
            maxima = scores.max(axis=1, keepdims=True)
            tied_first = scores == maxima
            unique_first = tied_first & (tied_first.sum(axis=1, keepdims=True) == 1)
            for index, arm in enumerate(CORE_ARMS):
                output.append(
                    {
                        "family": family,
                        "endpoint": endpoint,
                        "arm": arm,
                        "repetitions": repetitions,
                        "mean_rank": float(ranks[:, index].mean()),
                        "median_rank": float(np.median(ranks[:, index])),
                        "rank_interval95": [
                            float(value)
                            for value in np.quantile(ranks[:, index], [0.025, 0.975], method="nearest")
                        ],
                        "p_tied_for_first": float(tied_first[:, index].mean()),
                        "p_unique_first": float(unique_first[:, index].mean()),
                    }
                )
    return output


def build_replay(out: Path = DEFAULT_OUT) -> dict[str, Any]:
    universe, source_hashes = _load_case_universe()
    rows = _arm_rows(universe, out)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "five_endpoint_replay.jsonl", rows)
    validation = _validate_source_contract(universe, rows, out)
    atomic_json(out / "validation_summary.json", validation)

    endpoints = ("safe_exact", "legacy_chain", "clinical_complete", "partial", "task")
    leaderboard: list[dict[str, Any]] = []
    for arm in CORE_ARMS:
        arm_rows = [row for row in rows if row["arm_id"] == arm]
        for scope in ("ALL", "DA", "MCR"):
            scoped = arm_rows if scope == "ALL" else [row for row in arm_rows if row["benchmark_family"] == scope]
            item: dict[str, Any] = {"arm": arm, "scope": scope, "n": len(scoped)}
            for endpoint in endpoints:
                k = sum(bool(row[endpoint]) for row in scoped)
                item[f"{endpoint}_n"] = k
                item[f"{endpoint}_rate"] = k / len(scoped)
                item[f"{endpoint}_wilson95"] = _wilson(k, len(scoped))
            item["complete_or_partial_n"] = item["clinical_complete_n"] + item["partial_n"]
            item["complete_or_partial_rate"] = item["complete_or_partial_n"] / len(scoped)
            leaderboard.append(item)
    atomic_json(out / "leaderboard.json", leaderboard)
    _write_csv(out / "leaderboard.csv", leaderboard)

    calibration: dict[str, Any] = {
        "unit_warning": (
            "descriptive output-level calibration only: each case contributes nine arm outputs; "
            "do not treat 7200 rows as independent cases"
        ),
        "combined_task_warning": (
            "ALL task pools two different interface contracts and is retained only as a row-level "
            "diagnostic summary; DA and MCR are the interpretable task calibrations"
        ),
        "by_family": {},
        "by_family_arm": {},
    }
    for scope in ("ALL", "DA", "MCR"):
        scoped = rows if scope == "ALL" else [row for row in rows if row["benchmark_family"] == scope]
        calibration["by_family"][scope] = {
            proxy: _confusion(scoped, proxy, "clinical_complete")
            for proxy in ("safe_exact", "legacy_chain", "task")
        }
        calibration["by_family_arm"][scope] = {
            arm: {
                proxy: _confusion(
                    [row for row in scoped if row["arm_id"] == arm],
                    proxy,
                    "clinical_complete",
                )
                for proxy in ("safe_exact", "legacy_chain", "task")
            }
            for arm in CORE_ARMS
        }
    atomic_json(out / "endpoint_calibration.json", calibration)

    contrasts = []
    row_map = {(str(row["case_key"]), str(row["arm_id"])): row for row in rows}
    for endpoint in endpoints:
        for left, right in CONTRAST_PAIRS:
            for scope in ("ALL", "DA", "MCR"):
                if endpoint == "task" and scope == "ALL":
                    continue
                cases = sorted(
                    case["case_key"]
                    for case in universe
                    if scope == "ALL" or case["family"] == scope
                )
                pairs = {
                    key: (
                        bool(row_map[(key, left)][endpoint]),
                        bool(row_map[(key, right)][endpoint]),
                    )
                    for key in cases
                }
                pairs_by_slice: dict[str, dict[str, tuple[bool, bool]]] = defaultdict(dict)
                for key, value in pairs.items():
                    pairs_by_slice[str(row_map[(key, left)]["slice_id"])][key] = value
                left_only = sum(a and not b for a, b in pairs.values())
                right_only = sum(b and not a for a, b in pairs.values())
                contrasts.append(
                    {
                        "endpoint": endpoint,
                        "scope": scope,
                        "left": left,
                        "right": right,
                        "n": len(cases),
                        "left_only": left_only,
                        "right_only": right_only,
                        "delta_right_minus_left": (right_only - left_only) / len(cases),
                        "slice_stratified_case_bootstrap_ci95": _stratified_paired_bootstrap(
                            pairs_by_slice,
                            namespace=f"contrast:{endpoint}:{scope}:{left}:{right}",
                        ),
                        "exact_mcnemar_p": _mcnemar_exact(left_only, right_only),
                    }
                )
    for endpoint in endpoints:
        family = [row for row in contrasts if row["endpoint"] == endpoint]
        _holm_adjust(family, "exact_mcnemar_p", "holm_adjusted_p_within_endpoint_family")
        for row in family:
            row["endpoint_multiplicity_family_n"] = len(family)
    coherent_families = {
        "clinical_complete_overall_10": [
            row for row in contrasts if row["endpoint"] == "clinical_complete" and row["scope"] == "ALL"
        ],
        "safe_exact_overall_10": [
            row for row in contrasts if row["endpoint"] == "safe_exact" and row["scope"] == "ALL"
        ],
        "legacy_chain_overall_10": [
            row for row in contrasts if row["endpoint"] == "legacy_chain" and row["scope"] == "ALL"
        ],
        "da_option_mapper_10": [
            row for row in contrasts if row["endpoint"] == "task" and row["scope"] == "DA"
        ],
        "mcr_semantic_judge_10": [
            row for row in contrasts if row["endpoint"] == "task" and row["scope"] == "MCR"
        ],
    }
    for family_name, family_rows in coherent_families.items():
        _holm_adjust(family_rows, "exact_mcnemar_p", "coherent_family_holm_p")
        for row in family_rows:
            row["coherent_multiplicity_family"] = family_name
    atomic_json(out / "paired_contrasts.json", contrasts)
    _write_csv(out / "paired_contrasts.csv", contrasts)

    projection = _projection_decomposition(rows)
    atomic_json(out / "projection_error_decomposition.json", projection)
    _write_csv(out / "projection_error_decomposition.csv", projection["rows"])
    transitions = _relation_transition_outputs(rows, out)
    atomic_json(out / "relation_transition_matrices.json", transitions)
    _write_csv(out / "relation_transition_matrices.csv", transitions)
    identifiability = _identifiability_effect_modification(rows)
    atomic_json(out / "identifiability_effect_modification.json", identifiability)
    _write_csv(out / "identifiability_effect_modification.csv", identifiability)
    reference_identifiability = _reference_identifiability_outputs(rows)
    atomic_json(out / "reference_identifiability.json", reference_identifiability)
    _write_csv(
        out / "clinical_complete_by_identifiability.csv",
        reference_identifiability["clinical_complete_by_arm_scope_identity"],
    )
    rank_stability = _rank_stability(rows)
    atomic_json(out / "rank_stability.json", rank_stability)
    _write_csv(out / "rank_stability.csv", rank_stability)

    endpoint_contract = {
        "schema_version": "e2-unified-five-endpoint-v1",
        "primary_endpoint": "clinical_complete",
        "columns": {
            "safe_exact": "exact or frozen-safe-synonym identity; deterministic conservative lower bound",
            "legacy_chain": "historical bidirectional-substring/resolver chain_correct; diagnostic compatibility only",
            "clinical_complete": "root-adjudicated complete equivalence to the full requested reference object",
            "partial": "root-adjudicated compatible parent/component/underspecified object; mutually exclusive with complete",
            "task": "family-specific interface success: DA option mapper or MCR cached semantic diagnostic judge",
        },
        "derived_endpoint": {
            "complete_or_partial": "clinical_complete OR partial; secondary coverage sensitivity only"
        },
        "mandatory_stratifier": "reference_identifiability",
        "forbidden_interpretations": [
            "legacy_chain as strict or concept accuracy",
            "partial as complete diagnosis",
            "combined DA+MCR task as a homogeneous clinical estimand",
            "safe-exact as an unbiased absolute capability estimate",
        ],
    }
    atomic_json(out / "endpoint_contract.json", endpoint_contract)

    manifest = {
        "experiment_id": EXPERIMENT_ID,
        "created_at_utc": _utcnow(),
        "cases_n": 800,
        "families": {"DA": 400, "MCR": 400},
        "arms": list(CORE_ARMS),
        "arm_case_rows_n": len(rows),
        "endpoint_columns": list(endpoints),
        "endpoint_contract": {
            "primary_true_diagnostic_ability": "clinical_complete",
            "secondary_utility": "clinical_complete OR partial",
            "deterministic_lower_bound": "safe_exact",
            "legacy_diagnostic_only": "legacy_chain",
            "family_specific_interface": "task (DA option mapper; MCR cached semantic judge)",
        },
        "online_calls": 0,
        "source_hashes": source_hashes,
        "root_sources": {
            "old_relations_sha256": file_sha256(ROOT_RELATIONS_PATH),
            "old_identities_sha256": file_sha256(ROOT_IDENTITIES_PATH),
            "new_cards_sha256": file_sha256(out / "root_audit/cards.jsonl"),
            "new_index_sha256": file_sha256(out / "root_audit/index.jsonl"),
            "root_decision_codes_sha256": _sha256_json(_root_codes()),
        },
        "outputs": {
            name: file_sha256(out / name)
            for name in (
                "five_endpoint_replay.jsonl",
                "leaderboard.json",
                "leaderboard.csv",
                "endpoint_calibration.json",
                "paired_contrasts.json",
                "paired_contrasts.csv",
                "endpoint_contract.json",
                "validation_summary.json",
                "projection_error_decomposition.json",
                "projection_error_decomposition.csv",
                "relation_transition_matrices.json",
                "relation_transition_matrices.csv",
                "trajectory_endpoint_transitions.jsonl",
                "identifiability_effect_modification.json",
                "identifiability_effect_modification.csv",
                "reference_identifiability.json",
                "clinical_complete_by_identifiability.csv",
                "rank_stability.json",
                "rank_stability.csv",
            )
        },
    }
    atomic_json(out / "manifest.json", manifest)
    (out / "run.log").write_text(
        f"{manifest['created_at_utc']} replay complete cases=800 arms={len(CORE_ARMS)} "
        f"rows={len(rows)} online_calls=0\n",
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze-audit", "replay"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = freeze_audit(args.out) if args.command == "freeze-audit" else build_replay(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
