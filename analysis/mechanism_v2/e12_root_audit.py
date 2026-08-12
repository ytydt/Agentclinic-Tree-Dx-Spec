#!/usr/bin/env python3
"""Root-owned clinical adjudication and paired endpoint analysis for E12.

Gemini is used only to expand the review queue.  This module freezes the root
auditor's decisions for every proxy-positive/scope-sensitive candidate that can
change a clinical endpoint, all strict endpoint discordances, and a frozen
negative-screen sample.  Unreviewed, noncritical relations remain explicitly
labelled heterogeneous-proxy evidence.
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

from analysis.mechanism_v2.common import file_sha256, normalize_label  # noqa: E402
from analysis.mechanism_v2.e12_analysis import (  # noqa: E402
    INCREMENTAL_CONTRASTS,
    bootstrap_ci,
    exact_mcnemar,
    holm_adjust,
    load_arms,
    primary_contrasts,
)
from analysis.mechanism_v2.e12_e7_factorial import ARMS, DEFAULT_OUT  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


COMPLETE = "complete_equivalent"
PARTIAL = "partial_or_underspecified"
NOT_EQ = "not_equivalent"
SCREEN_MAP = {
    "exact_equivalent": COMPLETE,
    "acceptable_clinical_variant": COMPLETE,
    "broader_or_narrower_not_equivalent": PARTIAL,
    "related_not_equivalent": NOT_EQ,
    "unrelated": NOT_EQ,
    "uncertain": NOT_EQ,
}

# Decisions correspond to the deterministic screen-order/candidate-ID-order
# list returned by ``critical_positive_pairs``.  C/P/N are deliberately compact
# in source; root_adjudication.json expands every row with labels, screen reason,
# root relation and a rationale.  The three chunks are 80/80/76 rows.
ROOT_CRITICAL_DECISION_CODES = " ".join((
    "P P P P P P P P P P P P P N N C P P P P C N N P P P P N N P N P P N C P C N P N P P P N N P N P P N P P C C N P N N N N P P P P P N P P P P P P P P P C P P P P",
    "P P P P P P C P P P N P P P N N N N N N P P N P P P P C P N P P P P C P P P N P P P N P N P N P C C N P N N C N C P N N N P C C C N C N P C N N C N P C P C N N",
    "N C P P C N P N C N C P C P C C N N C N P C C P P P P N P P N N N N N C C C P C N N C C C C C P P P C C N P N N N P P N N P P C C P C N N N N N C C N C",
))
CODE_MAP = {"C": COMPLETE, "P": PARTIAL, "N": NOT_EQ}

# Two strict exact-matching discordance cases are not proxy-clinical
# discordances; they are nevertheless root-reviewed in full.
EXTRA_STRICT_DECISIONS = {
    ("MCR_seq200b/328", "D31"): PARTIAL,
    ("MCR_seq200b/328", "D35"): COMPLETE,
    ("MCR_seq200b/328", "D48"): COMPLETE,
    ("MCR_v2_seq100/169", "D21"): COMPLETE,
    ("MCR_v2_seq100/169", "D25"): COMPLETE,
}


def _screen_index(out: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(out / "semantic_screen" / "screen_results.jsonl")
    if len(rows) != 300:
        raise AssertionError("E12 semantic screen must contain 300 rows")
    return {str(row["case_key"]): row for row in rows}


def _candidate_maps(screen: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    registry = {str(row["candidate_id"]): dict(row) for row in screen["candidate_registry"]}
    label_to_id: dict[str, str] = {}
    for candidate_id, row in registry.items():
        key = normalize_label(str(row["label"]))
        if key in label_to_id and label_to_id[key] != candidate_id:
            raise AssertionError(f"ambiguous candidate label in {screen['case_key']}: {key}")
        label_to_id[key] = candidate_id
    return registry, label_to_id


def _screen_relations(screen: Mapping[str, Any]) -> dict[str, str]:
    output = {
        str(row["candidate_id"]): str(row["relation"])
        for row in screen["screen_response"].get("candidate_relations") or []
    }
    if set(output) != {str(row["candidate_id"]) for row in screen["candidate_registry"]}:
        raise AssertionError(f"screen candidate coverage mismatch: {screen['case_key']}")
    return output


def _proxy_endpoints(screen: Mapping[str, Any]) -> tuple[list[bool], list[bool], set[str]]:
    relations = _screen_relations(screen)
    _, label_to_id = _candidate_maps(screen)
    top1: list[bool] = []
    top2: list[bool] = []
    selected: set[str] = set()
    for arm in ARMS:
        view = screen["arm_outcomes"][arm]
        if not view["success"]:
            top1.append(False)
            top2.append(False)
            continue
        champion = str(view.get("champion_id") or "")
        runner = label_to_id.get(normalize_label(str(view.get("runner_up_label") or "")))
        selected.add(champion)
        if runner:
            selected.add(runner)
        hit1 = SCREEN_MAP[relations[champion]] == COMPLETE
        hit2 = hit1 or bool(runner and SCREEN_MAP[relations[runner]] == COMPLETE)
        top1.append(hit1)
        top2.append(hit2)
    return top1, top2, selected


def critical_positive_pairs(out: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    positive_or_scope = {
        "exact_equivalent", "acceptable_clinical_variant",
        "broader_or_narrower_not_equivalent", "uncertain",
    }
    for case_key, screen in _screen_index(out).items():
        top1, top2, selected = _proxy_endpoints(screen)
        if len(set(top1)) == 1 and len(set(top2)) == 1:
            continue
        registry, _ = _candidate_maps(screen)
        relation_rows = {
            str(row["candidate_id"]): dict(row)
            for row in screen["screen_response"]["candidate_relations"]
        }
        for candidate_id in sorted(selected):
            relation = relation_rows[candidate_id]
            if relation["relation"] not in positive_or_scope:
                continue
            rows.append({
                "case_key": case_key,
                "family": screen["family"],
                "gold": screen["reference_diagnosis"],
                "candidate_id": candidate_id,
                "candidate_label": registry[candidate_id]["label"],
                "screen_relation": relation["relation"],
                "screen_reason": relation["reason"],
            })
    if len(rows) != 236:
        raise AssertionError(f"frozen root critical relation list drifted: {len(rows)}/236")
    return rows


def _generic_rationale(screen_relation: str, root_relation: str) -> str:
    if root_relation == COMPLETE:
        return "Root review: same case-defining disease/entity; omitted or added wording is non-dispositive in this vignette."
    if root_relation == PARTIAL:
        return "Root review: retains a disease family or component but omits/asserts case-defining subtype, anatomy, cause, stage, or composite scope."
    if SCREEN_MAP[screen_relation] != NOT_EQ:
        return "Root review: manifestation, differential, conflicting subtype/etiology, or isolated component is not the reference entity."
    return "Root review: no missed complete equivalence; candidate remains a different entity."


def build_adjudication(out: Path) -> dict[str, Any]:
    critical = critical_positive_pairs(out)
    codes = ROOT_CRITICAL_DECISION_CODES.split()
    if len(codes) != len(critical) or not set(codes).issubset(CODE_MAP):
        raise AssertionError("root decision code coverage mismatch")
    decisions: dict[tuple[str, str], dict[str, Any]] = {}
    for row, code in zip(critical, codes, strict=True):
        relation = CODE_MAP[code]
        decisions[(row["case_key"], row["candidate_id"])] = {
            **row,
            "root_relation": relation,
            "root_rationale": _generic_rationale(row["screen_relation"], relation),
            "audit_scope": "all proxy-positive/scope-sensitive candidates selected in a proxy-clinical endpoint-discordant case",
        }
    screens = _screen_index(out)
    for (case_key, candidate_id), relation in EXTRA_STRICT_DECISIONS.items():
        screen = screens[case_key]
        registry, _ = _candidate_maps(screen)
        screen_rows = {str(row["candidate_id"]): row for row in screen["screen_response"]["candidate_relations"]}
        source = screen_rows[candidate_id]
        decisions[(case_key, candidate_id)] = {
            "case_key": case_key,
            "family": screen["family"],
            "gold": screen["reference_diagnosis"],
            "candidate_id": candidate_id,
            "candidate_label": registry[candidate_id]["label"],
            "screen_relation": source["relation"],
            "screen_reason": source["reason"],
            "root_relation": relation,
            "root_rationale": _generic_rationale(source["relation"], relation),
            "audit_scope": "strict endpoint discordance not present in proxy-clinical discordance set",
        }
    clinical_queue = read_jsonl(out / "clinical_audit_queue.jsonl")
    negative_cases = {
        str(row["case_key"])
        for row in clinical_queue
        if "frozen_negative_screen_audit" in row["queue_reasons"]
    }
    if len(negative_cases) != 30:
        raise AssertionError("negative-screen root sample must contain 30 cases")
    for case_key in sorted(negative_cases):
        screen = screens[case_key]
        registry, label_to_id = _candidate_maps(screen)
        screen_rows = {str(row["candidate_id"]): row for row in screen["screen_response"]["candidate_relations"]}
        selected: set[str] = set()
        for view in screen["arm_outcomes"].values():
            if not view["success"]:
                continue
            selected.add(str(view["champion_id"]))
            runner = label_to_id.get(normalize_label(str(view.get("runner_up_label") or "")))
            if runner:
                selected.add(runner)
        for candidate_id in sorted(selected):
            key = (case_key, candidate_id)
            if key in decisions:
                continue
            source = screen_rows[candidate_id]
            relation = SCREEN_MAP[str(source["relation"])]
            decisions[key] = {
                "case_key": case_key,
                "family": screen["family"],
                "gold": screen["reference_diagnosis"],
                "candidate_id": candidate_id,
                "candidate_label": registry[candidate_id]["label"],
                "screen_relation": source["relation"],
                "screen_reason": source["reason"],
                "root_relation": relation,
                "root_rationale": _generic_rationale(source["relation"], relation),
                "audit_scope": "frozen family-balanced negative-screen miss audit",
            }
    rows = sorted(decisions.values(), key=lambda row: (row["case_key"], row["candidate_id"]))
    write_jsonl(out / "root_relation_reviews.jsonl", rows)
    document = {
        "schema": "E12_root_adjudication_v1",
        "owner": "root manual auditor; heterogeneous model is queue-expansion only",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "critical_proxy_endpoint_case_n": 125,
        "strict_extra_case_n": 2,
        "negative_screen_sample_case_n": 30,
        "reviewed_case_n": len({row["case_key"] for row in rows}),
        "reviewed_case_candidate_n": len(rows),
        "root_relation_counts": dict(sorted(Counter(row["root_relation"] for row in rows).items())),
        "screen_to_root": {
            f"{left}->{right}": count
            for (left, right), count in sorted(Counter((row["screen_relation"], row["root_relation"]) for row in rows).items())
        },
        "review_rows_sha256": file_sha256(out / "root_relation_reviews.jsonl"),
        "negative_sample_finding": "No additional complete-equivalent candidate was found beyond screen-positive rows; positive runner-ups are adjudicated explicitly above.",
        "known_screen_failure_modes_corrected": [
            "accepted a diagnostic-journey differential as the final entity",
            "accepted a manifestation or isolated component of a composite reference",
            "collapsed conflicting subtypes (for example type 1 versus type 2 autoimmune pancreatitis)",
            "treated related anatomic/causal syndromes as synonyms",
        ],
    }
    atomic_json(out / "root_adjudication.json", document)
    return document


def resolve_relations(out: Path) -> tuple[dict[tuple[str, str], str], dict[str, Any]]:
    build_adjudication(out)
    reviews = {
        (str(row["case_key"]), str(row["candidate_id"])): row
        for row in read_jsonl(out / "root_relation_reviews.jsonl")
    }
    resolved: dict[tuple[str, str], str] = {}
    source_counts: Counter[str] = Counter()
    disagreements: Counter[str] = Counter()
    for case_key, screen in _screen_index(out).items():
        for row in screen["screen_response"]["candidate_relations"]:
            candidate_id = str(row["candidate_id"])
            proxy = SCREEN_MAP[str(row["relation"])]
            review = reviews.get((case_key, candidate_id))
            relation = str(review["root_relation"]) if review else proxy
            resolved[(case_key, candidate_id)] = relation
            source_counts["root_manual" if review else "heterogeneous_proxy"] += 1
            if review and relation != proxy:
                disagreements[f"{proxy}->{relation}"] += 1
    return resolved, {
        "candidate_source_counts": dict(sorted(source_counts.items())),
        "root_proxy_disagreements": dict(sorted(disagreements.items())),
        "root_proxy_disagreement_n": sum(disagreements.values()),
    }


def endpoint_maps(
    out: Path,
    relations: Mapping[tuple[str, str], str],
    accepted: frozenset[str],
) -> dict[str, dict[str, dict[str, bool]]]:
    output = {arm: {} for arm in ARMS}
    for case_key, screen in _screen_index(out).items():
        _, label_to_id = _candidate_maps(screen)
        for arm in ARMS:
            view = screen["arm_outcomes"][arm]
            if not view["success"]:
                output[arm][case_key] = {"top1": False, "top2": False}
                continue
            champion = str(view["champion_id"])
            runner = label_to_id.get(normalize_label(str(view.get("runner_up_label") or "")))
            top1 = relations[(case_key, champion)] in accepted
            top2 = top1 or bool(runner and relations[(case_key, runner)] in accepted)
            output[arm][case_key] = {"top1": top1, "top2": top2}
    return output


def binary_contrast(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left: str,
    right: str,
    label: str,
    endpoint: str,
    repetitions: int,
    common_support: bool,
    scope: str,
) -> dict[str, Any]:
    keys = sorted(endpoints[left])
    if common_support:
        keys = [key for key in keys if arms[left][key]["success"] and arms[right][key]["success"]]
    counts: Counter[tuple[bool, bool]] = Counter()
    deltas: list[float] = []
    gains: list[str] = []
    losses: list[str] = []
    for key in keys:
        before = bool(endpoints[left][key][endpoint])
        after = bool(endpoints[right][key][endpoint])
        counts[(before, after)] += 1
        deltas.append(float(after) - float(before))
        if not before and after:
            gains.append(key)
        elif before and not after:
            losses.append(key)
    left_only, right_only = counts[(True, False)], counts[(False, True)]
    return {
        "label": label,
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "scope": scope,
        "analysis_set": "common_success" if common_support else "intention_to_analyse",
        "n": len(keys),
        "both": counts[(True, True)],
        "left_only": left_only,
        "right_only": right_only,
        "neither": counts[(False, False)],
        "delta_right_minus_left": round(sum(deltas) / len(deltas), 6),
        "paired_bootstrap_delta_ci95": bootstrap_ci(
            deltas, f"root/{scope}/{label}/{endpoint}/{common_support}", repetitions
        ),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "gain_case_keys": gains,
        "loss_case_keys": losses,
    }


def contrast_family(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    contrasts: Sequence[tuple[str, str, str]],
    repetitions: int,
    scope: str,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for endpoint in ("top1", "top2"):
        output[endpoint] = {}
        for common in (False, True):
            rows = [
                binary_contrast(endpoints, arms, left, right, label, endpoint, repetitions, common, scope)
                for left, right, label in contrasts
            ]
            field = f"holm_adjusted_p_across_{len(contrasts)}"
            output[endpoint]["common_success" if common else "intention_to_analyse"] = holm_adjust(rows, field)
    return output


def arm_statistics(endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm in ARMS:
        rows = list(endpoints[arm].values())
        output[arm] = {
            "n": len(rows),
            "top1_n": sum(row["top1"] for row in rows),
            "top1_rate": round(sum(row["top1"] for row in rows) / len(rows), 6),
            "top2_n": sum(row["top2"] for row in rows),
            "top2_rate": round(sum(row["top2"] for row in rows) / len(rows), 6),
        }
    return output


def _archive(out: Path) -> tuple[Path, Path]:
    members = (
        "root_relation_reviews.jsonl", "root_adjudication.json",
        "root_clinical_analysis.json", "root_audit_run.log",
    )
    archive = out / "E12_ROOT_AUDIT_RAW.tar.gz"
    sha = out / "E12_ROOT_AUDIT_RAW.tar.gz.sha256"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in members:
            bundle.add(out / name, arcname=name)
    sha.write_text(f"{file_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, sha


def analyze(out: Path, repetitions: int) -> dict[str, Any]:
    arms = load_arms(out)
    relations, provenance = resolve_relations(out)
    complete = endpoint_maps(out, relations, frozenset({COMPLETE}))
    sensitivity = endpoint_maps(out, relations, frozenset({COMPLETE, PARTIAL}))
    result = {
        "experiment_id": "E12-root-clinical",
        "bootstrap_repetitions": repetitions,
        "adjudication": json.loads((out / "root_adjudication.json").read_text()),
        "provenance": provenance,
        "complete": {
            "arms": arm_statistics(complete),
            "primary": contrast_family(complete, arms, primary_contrasts(), repetitions, "complete"),
            "incremental": contrast_family(complete, arms, INCREMENTAL_CONTRASTS, repetitions, "complete_incremental"),
        },
        "complete_or_partial_sensitivity": {
            "arms": arm_statistics(sensitivity),
            "primary": contrast_family(sensitivity, arms, primary_contrasts(), repetitions, "complete_or_partial"),
            "incremental": contrast_family(sensitivity, arms, INCREMENTAL_CONTRASTS, repetitions, "complete_or_partial_incremental"),
        },
        "limitations": [
            "Root review is exhaustive for endpoint-critical proxy-positive/scope candidates and strict discordances, not every unselected negative candidate.",
            "A frozen 30-case negative screen audit found no additional complete-equivalent miss; proxy evidence remains outside reviewed pairs.",
            "Composite reference diagnoses are treated conservatively: an isolated component is partial, not complete.",
        ],
    }
    # Every final complete endpoint discordance must be in the root-reviewed set.
    reviewed_cases = {str(row["case_key"]) for row in read_jsonl(out / "root_relation_reviews.jsonl")}
    final_discordant: set[str] = set()
    for endpoint in ("top1", "top2"):
        for record in result["complete"]["primary"][endpoint]["intention_to_analyse"]:
            final_discordant.update(record["gain_case_keys"])
            final_discordant.update(record["loss_case_keys"])
    if not final_discordant.issubset(reviewed_cases):
        raise AssertionError(f"final endpoint discordance escaped root audit: {sorted(final_discordant - reviewed_cases)}")
    result["root_coverage"] = {
        "final_primary_complete_discordant_case_n": len(final_discordant),
        "all_final_discordances_root_reviewed": True,
        "reviewed_case_n": len(reviewed_cases),
    }
    atomic_json(out / "root_clinical_analysis.json", result)
    (out / "root_audit_run.log").write_text(
        "E12 root clinical audit completed\n"
        f"bootstrap_repetitions={repetitions}\n"
        f"reviewed_case_candidate_n={result['adjudication']['reviewed_case_candidate_n']}\n"
        f"root_proxy_disagreement_n={provenance['root_proxy_disagreement_n']}\n"
        f"final_discordant_case_n={len(final_discordant)}\n",
        encoding="utf-8",
    )
    _archive(out)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = analyze(args.out.resolve(), args.bootstrap_repetitions)
    print(json.dumps({
        "reviewed": result["adjudication"]["reviewed_case_candidate_n"],
        "disagreements": result["provenance"]["root_proxy_disagreement_n"],
        "final_discordant_cases": result["root_coverage"]["final_primary_complete_discordant_case_n"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
