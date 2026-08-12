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
import random
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
)
from analysis.mechanism_v2.e2_blinded_adjudication import (  # noqa: E402
    _load_case_universe,
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
        candidates = []
        for candidate_index, candidate in enumerate(
            _audit_candidate_order(case_key, row["candidate_registry"]), 1
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
                    "case_key": case_key,
                    "family": str(case["family"]),
                    "slice_id": str(case["slice_id"]),
                    "source_id": str(case["source_id"]),
                    "arm": arm,
                    "reference_diagnosis": str(case["gold"]),
                    "candidate_label": str(mapping["surface_label"]),
                    "reference_identifiability": identity[case_key],
                    "relation": relation,
                    "safe_exact": safe_exact,
                    "legacy_chain": bool(mapping["strict_chain_correct"]),
                    "clinical_complete": relation == "complete_equivalent",
                    "partial": relation == "partial_parent_or_component",
                    "task": bool(mapping["task_correct"]),
                }
            )
    if len(rows) != 800 * len(CORE_ARMS):
        raise AssertionError("incomplete arm-by-case replay")
    return rows


def _rate(rows: Sequence[Mapping[str, Any]], endpoint: str) -> float:
    return sum(bool(row[endpoint]) for row in rows) / len(rows) if rows else math.nan


def _wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n == 0:
        return [math.nan, math.nan]
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
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "ppv": ppv,
        "f1": f1,
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


def _holm_adjust(rows: Sequence[dict[str, Any]], p_key: str, out_key: str) -> None:
    order = sorted(range(len(rows)), key=lambda index: float(rows[index][p_key]))
    running = 0.0
    m = len(rows)
    for rank, index in enumerate(order):
        adjusted = min(1.0, (m - rank) * float(rows[index][p_key]))
        running = max(running, adjusted)
        rows[index][out_key] = running


def build_replay(out: Path = DEFAULT_OUT) -> dict[str, Any]:
    universe, source_hashes = _load_case_universe()
    rows = _arm_rows(universe, out)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "five_endpoint_replay.jsonl", rows)

    endpoints = ("safe_exact", "legacy_chain", "clinical_complete", "partial", "task")
    leaderboard: list[dict[str, Any]] = []
    for arm in CORE_ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        for scope in ("ALL", "DA", "MCR"):
            scoped = arm_rows if scope == "ALL" else [row for row in arm_rows if row["family"] == scope]
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
    with (out / "leaderboard.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[key for key in leaderboard[0] if not key.endswith("wilson95")],
        )
        writer.writeheader()
        writer.writerows(leaderboard)

    calibration: dict[str, Any] = {"by_family": {}}
    for scope in ("ALL", "DA", "MCR"):
        scoped = rows if scope == "ALL" else [row for row in rows if row["family"] == scope]
        calibration["by_family"][scope] = {
            proxy: _confusion(scoped, proxy, "clinical_complete")
            for proxy in ("safe_exact", "legacy_chain", "task")
        }
    atomic_json(out / "endpoint_calibration.json", calibration)

    contrasts = []
    contrast_pairs = (
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
    row_map = {(str(row["case_key"]), str(row["arm"])): row for row in rows}
    for endpoint in endpoints:
        for left, right in contrast_pairs:
            for scope in ("ALL", "DA", "MCR"):
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
                        "paired_bootstrap_ci95": _paired_bootstrap(pairs),
                        "exact_mcnemar_p": _mcnemar_exact(left_only, right_only),
                    }
                )
    for endpoint in endpoints:
        family = [row for row in contrasts if row["endpoint"] == endpoint]
        _holm_adjust(family, "exact_mcnemar_p", "holm_adjusted_p_across_30")
    atomic_json(out / "paired_contrasts.json", contrasts)

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
