#!/usr/bin/env python3
"""Root-owned clinical relation adjudication for RCR-3.

The heterogeneous reviewer only expands the queue.  Root review covers every
selected proxy-complete relation, every selected relation in a proxy/strict
endpoint-discordant case, the schema-failure case, and a frozen 15+15
family-balanced proxy-negative sample.  Remaining noncritical relations retain
an explicit proxy source and are never described as manually reviewed.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import (  # noqa: E402
    file_sha256,
    normalize_label,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.rcr3_analysis import (  # noqa: E402
    CONTRASTS,
    bootstrap_ci,
    exact_mcnemar,
    holm_adjust,
    load_arms,
)
from analysis.mechanism_v2.rcr3_end_to_end import (  # noqa: E402
    ARMS,
    DEFAULT_OUT,
)
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


COMPLETE = "complete_equivalent"
PARTIAL = "partial_or_underspecified"
NOT_EQ = "not_equivalent"
CODE_MAP = {"C": COMPLETE, "P": PARTIAL, "N": NOT_EQ}
PROXY_MAP = {
    "complete_equivalent": COMPLETE,
    "partial_parent_or_component": PARTIAL,
    "conflicting_subtype_or_scope": NOT_EQ,
    "manifestation_or_related": NOT_EQ,
    "not_equivalent": NOT_EQ,
    "uncertain": NOT_EQ,
}

# Filled only after the deterministic review packet is inspected by the root
# auditor.  Code order is the order returned by root_review_pairs().
ROOT_REVIEW_DECISION_CODES = ""


def _screens(out: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(out / "semantic_screen" / "screen_results.jsonl")
    if len(rows) != 300:
        raise AssertionError("RCR3 root audit requires 300 screen result rows")
    return rows


def _candidate_map(screen: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["candidate_id"]): dict(row)
        for row in screen["candidate_registry"]
    }


def _proxy_relations(screen: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = (screen.get("screen_response") or {}).get("candidate_relations")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("candidate_id")): dict(row)
        for row in rows if isinstance(row, Mapping)
    }


def _selected_ids(screen: Mapping[str, Any]) -> set[str]:
    selected: set[str] = set()
    for outcome in screen["arm_outcomes"].values():
        if not outcome["success"]:
            continue
        for key in ("champion_candidate_id", "runner_up_candidate_id"):
            candidate_id = str(outcome.get(key) or "")
            if candidate_id:
                selected.add(candidate_id)
    return selected


def _roles(screen: Mapping[str, Any], candidate_id: str) -> list[str]:
    output: list[str] = []
    for arm, outcome in screen["arm_outcomes"].items():
        if not outcome["success"]:
            continue
        if str(outcome.get("champion_candidate_id") or "") == candidate_id:
            output.append(f"{arm}:top1")
        if str(outcome.get("runner_up_candidate_id") or "") == candidate_id:
            output.append(f"{arm}:top2")
    return output


def _proxy_endpoint(screen: Mapping[str, Any], endpoint: str) -> list[bool]:
    relation = {
        candidate_id: str(row.get("relation") or "")
        for candidate_id, row in _proxy_relations(screen).items()
    }
    output: list[bool] = []
    for arm in ARMS:
        outcome = screen["arm_outcomes"][arm]
        if not screen["success"] or not outcome["success"]:
            output.append(False)
            continue
        champion = str(outcome.get("champion_candidate_id") or "")
        runner = str(outcome.get("runner_up_candidate_id") or "")
        hit1 = relation.get(champion) == "complete_equivalent"
        output.append(hit1 if endpoint == "top1" else hit1 or relation.get(runner) == "complete_equivalent")
    return output


def critical_case_reasons(out: Path) -> dict[str, set[str]]:
    rows = _screens(out)
    reasons: defaultdict[str, set[str]] = defaultdict(set)
    for screen in rows:
        key = str(screen["case_key"])
        if not screen["success"]:
            reasons[key].add("heterogeneous_screen_failure")
            continue
        if len(set(_proxy_endpoint(screen, "top1"))) > 1:
            reasons[key].add("proxy_complete_top1_discordance")
        if len(set(_proxy_endpoint(screen, "top2"))) > 1:
            reasons[key].add("proxy_complete_top2_discordance")
    for row in read_jsonl(out / "strict_contrasts.jsonl"):
        if (
            row["analysis_set"] == "intention_to_analyse"
            and row["family"] == "all"
            and row["endpoint"] in {"strict_top1", "strict_top2"}
        ):
            for key in row["gain_case_keys"] + row["loss_case_keys"]:
                reasons[str(key)].add(f"strict_{row['endpoint']}_discordance")
    for family in ("DA", "MCR"):
        pool: list[str] = []
        for screen in rows:
            key = str(screen["case_key"])
            if str(screen["family"]) != family or not screen["success"] or key in reasons:
                continue
            relation = {
                candidate_id: str(row.get("relation") or "")
                for candidate_id, row in _proxy_relations(screen).items()
            }
            selected = _selected_ids(screen)
            if selected and all(relation.get(candidate_id) != "complete_equivalent" for candidate_id in selected):
                pool.append(key)
        chosen = sorted(
            pool,
            key=lambda key: (stable_seed("RCR3-root-negative-v1", family, key), key),
        )[:15]
        if len(chosen) != 15:
            raise AssertionError(f"{family}: negative sample underfilled")
        for key in chosen:
            reasons[key].add("frozen_proxy_negative_sample")
    if len(reasons) != 98:
        raise AssertionError(f"frozen RCR3 critical case set drifted: {len(reasons)}/98")
    return reasons


def _e12_prior_reviews(out: Path) -> dict[tuple[str, str], dict[str, Any]]:
    path = out.parent / "E12_e7_factorial" / "root_relation_reviews.jsonl"
    output: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.is_file():
        return output
    for row in read_jsonl(path):
        output[(str(row["case_key"]), normalize_label(str(row["candidate_label"])))] = row
    return output


def root_review_pairs(out: Path) -> list[dict[str, Any]]:
    reasons = critical_case_reasons(out)
    priors = _e12_prior_reviews(out)
    pairs: list[dict[str, Any]] = []
    for screen in _screens(out):
        key = str(screen["case_key"])
        candidates = _candidate_map(screen)
        proxy = _proxy_relations(screen)
        for candidate_id in sorted(_selected_ids(screen)):
            relation = str((proxy.get(candidate_id) or {}).get("relation") or "screen_failure")
            if key not in reasons and relation != "complete_equivalent":
                continue
            candidate = candidates[candidate_id]
            label = str(candidate["label"])
            prior = priors.get((key, normalize_label(label)))
            pairs.append({
                "case_key": key,
                "family": screen["family"],
                "gold": screen["reference_diagnosis"],
                "candidate_id": candidate_id,
                "candidate_label": label,
                "roles": _roles(screen, candidate_id),
                "proxy_relation": relation,
                "proxy_reason": str((proxy.get(candidate_id) or {}).get("reason") or ""),
                "proxy_missing_or_conflicting_component": str(
                    (proxy.get(candidate_id) or {}).get("missing_or_conflicting_component") or ""
                ),
                "queue_reasons": sorted(reasons.get(key) or []),
                "e12_prior_root_relation": str((prior or {}).get("root_relation") or ""),
                "e12_prior_root_rationale": str((prior or {}).get("root_rationale") or ""),
                "vignette": screen["vignette"],
                "reference_identifiability_proxy": (
                    (screen.get("screen_response") or {}).get("reference_identifiability") or {}
                ),
            })
    pairs.sort(key=lambda row: (str(row["case_key"]), str(row["candidate_id"])))
    if len(pairs) != 375 or len({(row["case_key"], row["candidate_id"]) for row in pairs}) != 375:
        raise AssertionError(f"frozen root review relation set drifted: {len(pairs)}/375")
    return pairs


def print_review_packet(out: Path, start: int, count: int) -> None:
    rows = root_review_pairs(out)
    selected = rows[start:start + count]
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        grouped[str(row["case_key"])].append(row)
    for case_key, case_rows in grouped.items():
        first = case_rows[0]
        print("=" * 100)
        print(f"INDEX {rows.index(first)} CASE {case_key} FAMILY {first['family']}")
        print(f"GOLD: {first['gold']}")
        print("QUEUE:", ", ".join(first["queue_reasons"]) or "all-selected proxy-complete")
        print("IDENT:", json.dumps(first["reference_identifiability_proxy"], ensure_ascii=False, sort_keys=True))
        for row in case_rows:
            print(
                f"[{rows.index(row):03d}] {row['candidate_id']} {row['candidate_label']} | "
                f"proxy={row['proxy_relation']} | roles={','.join(row['roles'])} | "
                f"E12={row['e12_prior_root_relation'] or '-'}"
            )
            print("  PROXY:", row["proxy_reason"])
            if row["proxy_missing_or_conflicting_component"]:
                print("  MISS:", row["proxy_missing_or_conflicting_component"])
        print("VIGNETTE:", first["vignette"])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-review-packet", action="store_true")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    if args.print_review_packet:
        print_review_packet(out, args.start, args.count)
        return 0
    raise SystemExit("root decision codes are not frozen; use --print-review-packet")


if __name__ == "__main__":
    raise SystemExit(main())
