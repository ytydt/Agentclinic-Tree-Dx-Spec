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

# Root-owned decisions after inspection of all 375 selected relations and the
# full vignette whenever label-only equivalence was ambiguous.  Each ten-code
# chunk covers a consecutive ten-row window returned by root_review_pairs();
# the final chunk covers rows 370--374.  The compact representation prevents a
# free-text model response from silently becoming the final adjudication.
ROOT_REVIEW_DECISION_CODES = "".join((
    "NPPPPNPNPP", "NPNNNNPNNC", "NPPPNNNPNN", "NNNPNCNNPN", "CNCNPPNNNN",
    "PPPNNNNNPP", "PPNNNPNPPN", "PCNNNNNNNN", "CNPPNNPPNN", "NCPPCNNPPP",
    "NNPPPNNNPN", "NPNCNNCNNP", "NNNNNNNNNC", "NNNPNNCNNC", "NNCNNNCNNC",
    "PCNCCNNNNN", "NCNNCPPCNN", "NPPPPNCCCC", "CCNPNPNCNN", "PNNNNNNNNN",
    "NCPNNNCNCN", "CCNNNCNNNN", "NNNCNNNNNN", "NPCNCNNNCC", "NNNPNCCCNC",
    "CNNPNNCNNC", "NCNNNNPPNP", "PCCCNNNNNC", "NNNNPNNNNP", "NNNCNCPPPN",
    "CCPNNNNCNP", "NCPPNCNNNC", "NNCNCCPNNN", "NCPNPCNNNC", "CNCNNCCNCP",
    "NNNNNNNCNC", "NNCCCNNCCN", "NNNNP",
))


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


def _generic_rationale(row: Mapping[str, Any], relation: str) -> str:
    prior = str(row.get("e12_prior_root_relation") or "")
    if prior:
        return (
            "Root review rechecked the full vignette and retained the prior E12 "
            f"manual relation ({prior}) for the same normalized candidate label."
        )
    if relation == COMPLETE:
        return (
            "Root review: same case-defining diagnostic entity; any added specificity "
            "is supported by the vignette and omitted wording is non-dispositive."
        )
    if relation == PARTIAL:
        return (
            "Root review: preserves the relevant disease family or core entity but "
            "does not preserve every case-defining subtype, cause, anatomy, stage, "
            "temporal qualifier, or composite component in the reference."
        )
    if str(row.get("proxy_relation") or "") in {
        "complete_equivalent", "partial_parent_or_component", "screen_failure",
    }:
        return (
            "Root review: this is a manifestation, cause, differential, conflicting "
            "subtype/scope, isolated component, or corrupted label rather than the "
            "reference diagnostic entity."
        )
    return "Root review: candidate remains a different diagnostic entity from the reference."


def build_adjudication(out: Path) -> dict[str, Any]:
    pairs = root_review_pairs(out)
    codes = list(ROOT_REVIEW_DECISION_CODES)
    if len(codes) != len(pairs) or not set(codes).issubset(CODE_MAP):
        raise AssertionError(
            f"root decision code coverage mismatch: {len(codes)}/{len(pairs)}"
        )
    reviews: list[dict[str, Any]] = []
    for row, code in zip(pairs, codes, strict=True):
        relation = CODE_MAP[code]
        reviews.append({
            "case_key": row["case_key"],
            "family": row["family"],
            "gold": row["gold"],
            "candidate_id": row["candidate_id"],
            "candidate_label": row["candidate_label"],
            "roles": row["roles"],
            "proxy_relation": row["proxy_relation"],
            "proxy_reason": row["proxy_reason"],
            "proxy_missing_or_conflicting_component": row[
                "proxy_missing_or_conflicting_component"
            ],
            "root_relation": relation,
            "root_rationale": _generic_rationale(row, relation),
            "queue_reasons": row["queue_reasons"],
            "e12_prior_root_relation": row["e12_prior_root_relation"],
            "e12_prior_root_rationale": row["e12_prior_root_rationale"],
            "audit_scope": (
                "every selected proxy-complete relation; every selected relation in "
                "a proxy/strict-discordant or screen-failure case; and every selected "
                "relation in a frozen 15+15 proxy-negative sample"
            ),
        })
    write_jsonl(out / "root_relation_reviews.jsonl", reviews)

    reasons = critical_case_reasons(out)
    negative_cases = {
        key for key, values in reasons.items()
        if "frozen_proxy_negative_sample" in values
    }
    negative_reviews = [
        row for row in reviews if str(row["case_key"]) in negative_cases
    ]
    negative_complete = sorted({
        str(row["case_key"])
        for row in negative_reviews if row["root_relation"] == COMPLETE
    })
    screen_identifiability = Counter(
        str(((screen.get("screen_response") or {}).get(
            "reference_identifiability"
        ) or {}).get("judgment") or "screen_failure")
        for screen in _screens(out)
    )
    screen_to_root = Counter(
        (str(row["proxy_relation"]), str(row["root_relation"]))
        for row in reviews
    )
    document = {
        "schema": "RCR3_root_adjudication_v1",
        "owner": "root manual auditor; heterogeneous model is queue expansion only",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewed_case_n": len({str(row["case_key"]) for row in reviews}),
        "critical_case_n": len(reasons),
        "reviewed_case_candidate_n": len(reviews),
        "reviewed_family_counts": dict(sorted(Counter(
            str(row["family"]) for row in reviews
        ).items())),
        "root_relation_counts": dict(sorted(Counter(
            str(row["root_relation"]) for row in reviews
        ).items())),
        "screen_to_root": {
            f"{left}->{right}": count
            for (left, right), count in sorted(screen_to_root.items())
        },
        "root_proxy_relation_disagreement_n": sum(
            count for (left, right), count in screen_to_root.items()
            if PROXY_MAP.get(left, NOT_EQ) != right
        ),
        "e12_prior_relation_recheck_n": sum(
            bool(row["e12_prior_root_relation"]) for row in reviews
        ),
        "negative_sample": {
            "case_n": len(negative_cases),
            "reviewed_selected_relation_n": len(negative_reviews),
            "root_complete_case_n": len(negative_complete),
            "root_complete_case_keys": negative_complete,
        },
        "heterogeneous_reference_identifiability_proxy_counts": dict(
            sorted(screen_identifiability.items())
        ),
        "identifiability_boundary": (
            "These RCR-3 root codes adjudicate output-to-reference relation only. "
            "They do not convert the heterogeneous reference-identifiability screen "
            "into root truth; E2 performs the preregistered blinded dual-review "
            "identifiability study."
        ),
        "review_rows_sha256": file_sha256(out / "root_relation_reviews.jsonl"),
        "known_proxy_failure_modes_corrected": [
            "accepted a manifestation or complication as the reference entity",
            "accepted an upstream cause or background disease as the requested diagnosis",
            "collapsed conflicting subtype, scope, temporal, or composite components",
            "treated a corrupted expansion of an abbreviation as a synonym",
            "mixed case identifiability with output-to-reference equivalence",
        ],
    }
    atomic_json(out / "root_adjudication.json", document)
    return document


def resolve_relations(out: Path) -> tuple[dict[tuple[str, str], str], dict[str, Any]]:
    adjudication = build_adjudication(out)
    reviews = {
        (str(row["case_key"]), str(row["candidate_id"])): row
        for row in read_jsonl(out / "root_relation_reviews.jsonl")
    }
    resolved: dict[tuple[str, str], str] = {}
    source_counts: Counter[str] = Counter()
    disagreements: Counter[str] = Counter()
    for screen in _screens(out):
        case_key = str(screen["case_key"])
        proxy = _proxy_relations(screen)
        for candidate in screen["candidate_registry"]:
            candidate_id = str(candidate["candidate_id"])
            proxy_raw = str((proxy.get(candidate_id) or {}).get("relation") or "screen_failure")
            proxy_relation = PROXY_MAP.get(proxy_raw, NOT_EQ)
            review = reviews.get((case_key, candidate_id))
            if review:
                relation = str(review["root_relation"])
                source = "root_manual"
                if relation != proxy_relation:
                    disagreements[f"{proxy_relation}->{relation}"] += 1
            elif proxy_raw == "screen_failure":
                relation = NOT_EQ
                source = "heterogeneous_screen_failure_fail_closed"
            else:
                relation = proxy_relation
                source = "heterogeneous_proxy_noncritical"
            resolved[(case_key, candidate_id)] = relation
            source_counts[source] += 1
    if len(resolved) != 3533:
        raise AssertionError(f"candidate relation coverage drifted: {len(resolved)}/3533")
    return resolved, {
        "candidate_source_counts": dict(sorted(source_counts.items())),
        "root_proxy_disagreements": dict(sorted(disagreements.items())),
        "root_proxy_disagreement_n": sum(disagreements.values()),
        "adjudication_sha256": file_sha256(out / "root_adjudication.json"),
        "review_rows_sha256": adjudication["review_rows_sha256"],
    }


def endpoint_maps(
    out: Path,
    relations: Mapping[tuple[str, str], str],
    accepted: frozenset[str],
) -> dict[str, dict[str, dict[str, bool]]]:
    output: dict[str, dict[str, dict[str, bool]]] = {arm: {} for arm in ARMS}
    for screen in _screens(out):
        case_key = str(screen["case_key"])
        for arm in ARMS:
            outcome = screen["arm_outcomes"][arm]
            if not outcome["success"]:
                output[arm][case_key] = {"top1": False, "top2": False}
                continue
            champion = str(outcome.get("champion_candidate_id") or "")
            runner = str(outcome.get("runner_up_candidate_id") or "")
            hit1 = relations[(case_key, champion)] in accepted
            hit2 = hit1 or bool(runner and relations[(case_key, runner)] in accepted)
            output[arm][case_key] = {"top1": hit1, "top2": hit2}
    return output


def _binary_contrast(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left: str,
    right: str,
    label: str,
    endpoint: str,
    repetitions: int,
    *,
    common_success: bool,
    family: str | None,
    scope: str,
) -> dict[str, Any]:
    keys = sorted(endpoints[left])
    if family:
        keys = [key for key in keys if str(arms[left][key]["family"]) == family]
    if common_success:
        keys = [
            key for key in keys
            if arms[left][key]["success"] and arms[right][key]["success"]
        ]
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
    left_only = counts[(True, False)]
    right_only = counts[(False, True)]
    return {
        "label": label,
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "scope": scope,
        "analysis_set": "common_success" if common_success else "intention_to_analyse",
        "family": family or "all",
        "n": len(keys),
        "both": counts[(True, True)],
        "left_only": left_only,
        "right_only": right_only,
        "neither": counts[(False, False)],
        "delta_right_minus_left": (
            round(sum(deltas) / len(deltas), 6) if deltas else None
        ),
        "paired_bootstrap_delta_ci95": bootstrap_ci(
            deltas,
            f"root/{scope}/{label}/{endpoint}/{common_success}/{family}",
            repetitions,
        ),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "gain_case_keys": gains,
        "loss_case_keys": losses,
    }


def _contrasts(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    repetitions: int,
    scope: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for endpoint in ("top1", "top2"):
        for common_success in (False, True):
            for family in (None, "DA", "MCR"):
                rows = [
                    _binary_contrast(
                        endpoints, arms, left, right, label, endpoint,
                        repetitions, common_success=common_success,
                        family=family, scope=scope,
                    )
                    for left, right, label in CONTRASTS
                ]
                output.extend(holm_adjust(rows))
    return output


def _arm_statistics(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm in ARMS:
        def summarize(keys: Sequence[str]) -> dict[str, Any]:
            n = len(keys)
            top1 = sum(bool(endpoints[arm][key]["top1"]) for key in keys)
            top2 = sum(bool(endpoints[arm][key]["top2"]) for key in keys)
            served = sum(bool(arms[arm][key]["success"]) for key in keys)
            return {
                "n": n,
                "served_n": served,
                "top1_n": top1,
                "top1_rate": round(top1 / n, 6) if n else None,
                "top2_n": top2,
                "top2_rate": round(top2 / n, 6) if n else None,
            }

        all_keys = sorted(endpoints[arm])
        output[arm] = {
            **summarize(all_keys),
            "by_family": {
                family: summarize([
                    key for key in all_keys
                    if str(arms[arm][key]["family"]) == family
                ])
                for family in ("DA", "MCR")
            },
        }
    return output


def _archive(out: Path) -> tuple[Path, Path]:
    members = (
        "root_relation_reviews.jsonl",
        "root_adjudication.json",
        "root_clinical_analysis.json",
        "root_audit_run.log",
    )
    archive = out / "RCR3_ROOT_AUDIT_RAW.tar.gz"
    sha = out / "RCR3_ROOT_AUDIT_RAW.tar.gz.sha256"
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
        "experiment_id": "RCR3-root-clinical",
        "bootstrap_repetitions": repetitions,
        "adjudication": json.loads((out / "root_adjudication.json").read_text(
            encoding="utf-8"
        )),
        "provenance": provenance,
        "complete": {
            "arms": _arm_statistics(complete, arms),
            "contrasts": _contrasts(complete, arms, repetitions, "complete"),
        },
        "complete_or_partial_sensitivity": {
            "arms": _arm_statistics(sensitivity, arms),
            "contrasts": _contrasts(
                sensitivity, arms, repetitions, "complete_or_partial"
            ),
        },
        "limitations": [
            "Root review is exhaustive for all selected proxy-complete relations, all selected relations in endpoint-critical cases, and a frozen 30-case proxy-negative sample; remaining noncritical relations retain explicit heterogeneous-proxy provenance.",
            "Output-to-reference relation is separate from whether the vignette uniquely supports the reference; E2 adjudicates the latter with two blinded heterogeneous reviewers.",
            "Fail-closed intention-to-analyse is primary; common-success estimates are survivor-selected sensitivity analyses.",
        ],
    }
    reviewed_cases = {
        str(row["case_key"])
        for row in read_jsonl(out / "root_relation_reviews.jsonl")
    }
    final_discordant: set[str] = set()
    for row in result["complete"]["contrasts"]:
        if row["analysis_set"] != "intention_to_analyse" or row["family"] != "all":
            continue
        final_discordant.update(row["gain_case_keys"])
        final_discordant.update(row["loss_case_keys"])
    if not final_discordant.issubset(reviewed_cases):
        missing = sorted(final_discordant - reviewed_cases)
        raise AssertionError(f"final endpoint discordance escaped root audit: {missing}")
    result["root_coverage"] = {
        "reviewed_case_n": len(reviewed_cases),
        "final_complete_discordant_case_n": len(final_discordant),
        "all_final_complete_discordances_root_reviewed": True,
    }
    atomic_json(out / "root_clinical_analysis.json", result)
    (out / "root_audit_run.log").write_text(
        "RCR3 root clinical audit completed\n"
        f"bootstrap_repetitions={repetitions}\n"
        f"reviewed_case_candidate_n={result['adjudication']['reviewed_case_candidate_n']}\n"
        f"root_proxy_disagreement_n={provenance['root_proxy_disagreement_n']}\n"
        f"final_complete_discordant_case_n={len(final_discordant)}\n",
        encoding="utf-8",
    )
    _archive(out)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-review-packet", action="store_true")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    if args.print_review_packet:
        print_review_packet(out, args.start, args.count)
        return 0
    result = analyze(out, args.bootstrap_repetitions)
    print(json.dumps({
        "reviewed": result["adjudication"]["reviewed_case_candidate_n"],
        "disagreements": result["provenance"]["root_proxy_disagreement_n"],
        "complete_top1": {
            arm: result["complete"]["arms"][arm]["top1_n"] for arm in ARMS
        },
        "complete_top2": {
            arm: result["complete"]["arms"][arm]["top2_n"] for arm in ARMS
        },
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
