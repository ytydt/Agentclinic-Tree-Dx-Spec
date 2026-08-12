#!/usr/bin/env python3
"""Root-owned clinical and manipulation audit for the E11 factorial."""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.e11_analysis import (  # noqa: E402
    PRIMARY_CONTRASTS,
    bootstrap_ci,
    exact_mcnemar,
    holm_adjust,
)
from analysis.mechanism_v2.e11_b07_factorial import ARMS, DEFAULT_OUT  # noqa: E402
from analysis.mechanism_v2.e11_semantic_screen import case_documents  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


ADJUDICATION_NAME = "root_adjudication.json"
SCREEN_RELATION_MAP = {
    "exact_equivalent": "complete_equivalent",
    "acceptable_clinical_variant": "complete_equivalent",
    "broader_or_narrower_not_equivalent": "partial_or_underspecified",
    "related_not_equivalent": "not_equivalent",
    "unrelated": "not_equivalent",
    "uncertain": "unresolved",
}
COMPLETE = frozenset({"complete_equivalent"})
COMPLETE_OR_PARTIAL = frozenset(
    {"complete_equivalent", "partial_or_underspecified"}
)


def _arm_rows(out: Path) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    expected: set[str] | None = None
    for arm in ARMS:
        rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        by_key = {str(row["case_key"]): row for row in rows}
        if len(rows) != 400 or len(by_key) != 400:
            raise AssertionError(f"{arm} does not contain 400 unique cases")
        if expected is None:
            expected = set(by_key)
        elif set(by_key) != expected:
            raise AssertionError(f"case-set mismatch for {arm}")
        indexed[arm] = by_key
    return indexed


def _screen_relation_map(row: Mapping[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in row.get("screen_response", {}).get("candidate_relations") or []:
        candidate_id = str(item.get("candidate_id") or "")
        relation = str(item.get("relation") or "")
        if candidate_id and relation in SCREEN_RELATION_MAP:
            output[candidate_id] = SCREEN_RELATION_MAP[relation]
    return output


def resolve_candidate_relations(
    screen_rows: Mapping[str, Mapping[str, Any]],
    adjudication: Mapping[str, Any],
) -> tuple[dict[tuple[str, str, int], str], dict[str, Any]]:
    """Resolve each arm/rank through root overrides or the proxy screen."""
    root_cases = dict(adjudication["cases"])
    failure_keys = {
        key
        for key, row in screen_rows.items()
        if not bool(row["component_success"]["candidate"])
    }
    declared_failures = set(adjudication["candidate_screen_failure_case_keys"])
    if failure_keys != declared_failures:
        raise AssertionError(
            f"candidate screen failure drift: actual={sorted(failure_keys)} "
            f"declared={sorted(declared_failures)}"
        )
    if not failure_keys.issubset(root_cases):
        raise AssertionError("every candidate-screen failure requires a root override")

    relations: dict[tuple[str, str, int], str] = {}
    source_counts: Counter[str] = Counter()
    disagreement_counts: Counter[str] = Counter()
    unresolved_cases: set[str] = set()
    for case_key, row in sorted(screen_rows.items()):
        registry = {
            str(candidate["candidate_id"]): candidate
            for candidate in row["candidate_registry"]
        }
        proxy = _screen_relation_map(row)
        if case_key in root_cases:
            resolved = {
                str(key): str(value)
                for key, value in root_cases[case_key]["candidate_relations"].items()
            }
            if set(resolved) != set(registry):
                raise AssertionError(
                    f"root candidate coverage mismatch for {case_key}: "
                    f"root={sorted(resolved)} registry={sorted(registry)}"
                )
            if not set(resolved.values()).issubset(COMPLETE_OR_PARTIAL | {"not_equivalent"}):
                raise AssertionError(f"invalid root relation in {case_key}")
            source = "root_manual"
            if bool(row["component_success"]["candidate"]):
                for candidate_id in registry:
                    if proxy.get(candidate_id) != resolved[candidate_id]:
                        disagreement_counts["root_vs_valid_proxy_candidate"] += 1
        else:
            if not bool(row["component_success"]["candidate"]):
                raise AssertionError(f"unresolved failed candidate screen: {case_key}")
            if set(proxy) != set(registry):
                raise AssertionError(f"valid proxy omitted candidates for {case_key}")
            resolved = proxy
            source = "heterogeneous_proxy"
        for candidate_id, candidate in registry.items():
            relation = resolved[candidate_id]
            if relation == "unresolved":
                unresolved_cases.add(case_key)
            for occurrence in candidate["occurrences"]:
                key = (
                    case_key,
                    str(occurrence["arm"]),
                    int(occurrence["rank"]),
                )
                if key in relations:
                    raise AssertionError(f"duplicate candidate occurrence: {key}")
                relations[key] = relation
                source_counts[source] += 1
    expected_positions = len(screen_rows) * len(ARMS) * 2
    if len(relations) != expected_positions:
        raise AssertionError(
            f"candidate occurrence coverage {len(relations)}/{expected_positions}"
        )
    return relations, {
        "position_source_counts": dict(sorted(source_counts.items())),
        "root_proxy_candidate_disagreements": dict(sorted(disagreement_counts.items())),
        "unresolved_proxy_case_keys": sorted(unresolved_cases),
    }


def _endpoint_maps(
    case_keys: Sequence[str],
    relations: Mapping[tuple[str, str, int], str],
    accepted: frozenset[str],
) -> dict[str, dict[str, dict[str, bool]]]:
    output: dict[str, dict[str, dict[str, bool]]] = {}
    for arm in ARMS:
        output[arm] = {}
        for case_key in case_keys:
            top1 = relations[(case_key, arm, 1)] in accepted
            top2 = top1 or relations[(case_key, arm, 2)] in accepted
            output[arm][case_key] = {"top1": top1, "top2": top2}
    return output


def binary_contrast(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    left: str,
    right: str,
    endpoint: str,
    label: str,
    *,
    case_keys: Sequence[str],
    repetitions: int,
    seed_scope: str,
) -> dict[str, Any]:
    counts: Counter[tuple[bool, bool]] = Counter()
    deltas: list[float] = []
    gain_keys: list[str] = []
    loss_keys: list[str] = []
    for case_key in sorted(case_keys):
        before = bool(endpoints[left][case_key][endpoint])
        after = bool(endpoints[right][case_key][endpoint])
        counts[(before, after)] += 1
        deltas.append(float(after) - float(before))
        if not before and after:
            gain_keys.append(case_key)
        elif before and not after:
            loss_keys.append(case_key)
    n = len(deltas)
    return {
        "label": label,
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "n": n,
        "both": counts[(True, True)],
        "left_only": counts[(True, False)],
        "right_only": counts[(False, True)],
        "neither": counts[(False, False)],
        "delta_right_minus_left": round(sum(deltas) / n, 6),
        "paired_bootstrap_delta_ci95": bootstrap_ci(
            deltas, f"E11-root/{seed_scope}/{label}/{endpoint}", repetitions
        ),
        "exact_mcnemar_p": exact_mcnemar(
            counts[(True, False)], counts[(False, True)]
        ),
        "gain_case_keys": gain_keys,
        "loss_case_keys": loss_keys,
    }


def _contrast_family(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    case_keys: Sequence[str],
    repetitions: int,
    scope: str,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for endpoint in ("top1", "top2"):
        records = [
            binary_contrast(
                endpoints, left, right, endpoint, label,
                case_keys=case_keys, repetitions=repetitions, seed_scope=scope,
            )
            for left, right, label in PRIMARY_CONTRASTS
        ]
        output[endpoint] = holm_adjust(records, "holm_adjusted_p_across_7")
    return output


def _arm_statistics(
    endpoints: Mapping[str, Mapping[str, Mapping[str, bool]]],
    case_keys: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        rows = (
            list(endpoints[arm].values())
            if case_keys is None
            else [endpoints[arm][case_key] for case_key in case_keys]
        )
        n = len(rows)
        top1 = sum(bool(row["top1"]) for row in rows)
        top2 = sum(bool(row["top2"]) for row in rows)
        output[arm] = {
            "n": n,
            "top1_n": top1,
            "top1_rate": round(top1 / n, 6),
            "top2_n": top2,
            "top2_rate": round(top2 / n, 6),
        }
    return output


def _retrieval_screen_analysis(
    out: Path,
    screen_rows: Mapping[str, Mapping[str, Any]],
    strict: Mapping[str, Mapping[str, Mapping[str, bool]]],
    clinical: Mapping[str, Mapping[str, Mapping[str, bool]]],
    repetitions: int,
) -> dict[str, Any]:
    valid = [
        row for row in screen_rows.values()
        if bool(row["component_success"]["retrieval"])
    ]
    valid_keys = sorted(str(row["case_key"]) for row in valid)
    bundle_counts: dict[str, Any] = {}
    chunk_counts: dict[str, Any] = {}
    prefixes = {"relevant": "R", "random": "N", "hard_negative": "H"}
    for bundle, prefix in prefixes.items():
        assessments = [
            next(
                item for item in row["screen_response"]["bundle_assessments"]
                if item["bundle"] == bundle
            )
            for row in valid
        ]
        bundle_counts[bundle] = {
            field: dict(sorted(Counter(str(item[field]) for item in assessments).items()))
            for field in (
                "reference_support", "generated_top1_support",
                "confirmation_pressure", "clinically_misleading",
            )
        }
        chunks = [
            item
            for row in valid
            for item in row["screen_response"]["chunk_assessments"]
            if str(item["chunk_id"]).startswith(prefix)
        ]
        chunk_counts[bundle] = {
            "n": len(chunks),
            **{
                field: dict(sorted(Counter(str(item[field]) for item in chunks).items()))
                for field in (
                    "relation_to_reference", "relation_to_generated_top1",
                    "vignette_applicability",
                )
            },
        }

    treatment_arms = {
        "relevant": "relevant_refine_off",
        "random": "random_refine_off",
        "hard_negative": "hard_negative_refine_off",
    }
    descriptive_contrasts: dict[str, Any] = {}
    for bundle, arm in treatment_arms.items():
        descriptive_contrasts[bundle] = {
            "strict": {
                endpoint: binary_contrast(
                    strict, "off_refine_off", arm, endpoint,
                    f"{bundle}_vs_off_retrieval_screen_valid",
                    case_keys=valid_keys, repetitions=repetitions,
                    seed_scope="retrieval-screen-strict",
                )
                for endpoint in ("top1", "top2")
            },
            "clinical_complete": {
                endpoint: binary_contrast(
                    clinical, "off_refine_off", arm, endpoint,
                    f"{bundle}_vs_off_retrieval_screen_valid",
                    case_keys=valid_keys, repetitions=repetitions,
                    seed_scope="retrieval-screen-clinical",
                )
                for endpoint in ("top1", "top2")
            },
        }

    retrieval_component = read_jsonl(
        out / "semantic_screen" / "retrieval" / "case_results.jsonl"
    )
    return {
        "n_valid_cases": len(valid),
        "n_failed_cases": len(screen_rows) - len(valid),
        "failure_reason_counts": dict(sorted(Counter(
            str(row["error"]) for row in retrieval_component if not row["success"]
        ).items())),
        "bundle_assessment_counts": bundle_counts,
        "chunk_assessment_counts": chunk_counts,
        "descriptive_treatment_contrasts_on_screen_valid_cases": descriptive_contrasts,
        "post_treatment_warning": (
            "The screen sees generated Top-1 and is a descriptive manipulation audit. "
            "Do not treat strata as randomized moderators or replace the ITA factorial."
        ),
    }


def _strict_endpoints(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> dict[str, dict[str, dict[str, bool]]]:
    return {
        arm: {
            key: {"top1": bool(row["gold_top1"]), "top2": bool(row["gold_top2"])}
            for key, row in rows.items()
        }
        for arm, rows in arms.items()
    }


def _manual_summary(
    adjudication: Mapping[str, Any],
    strict: Mapping[str, Mapping[str, Mapping[str, bool]]],
    clinical: Mapping[str, Mapping[str, Mapping[str, bool]]],
) -> dict[str, Any]:
    deep = list(adjudication["deep_review_case_keys"])
    mechanisms = Counter(
        code
        for case_key in adjudication["cases"]
        for code in adjudication["cases"][case_key]["mechanism_codes"]
    )
    resolution: dict[str, Any] = {}
    for endpoint in ("top1", "top2"):
        strict_discord = [
            key for key in deep
            if len({strict[arm][key][endpoint] for arm in ARMS}) > 1
        ]
        clinical_discord = [
            key for key in deep
            if len({clinical[arm][key][endpoint] for arm in ARMS}) > 1
        ]
        resolution[endpoint] = {
            "strict_discordant_deep_cases": strict_discord,
            "clinical_complete_discordant_deep_cases": clinical_discord,
            "strict_discordance_fully_resolved_n": len(set(strict_discord) - set(clinical_discord)),
        }
    return {
        "n_root_candidate_cases": len(adjudication["cases"]),
        "n_deep_trajectory_cases": len(deep),
        "n_candidate_screen_failure_cases": len(
            adjudication["candidate_screen_failure_case_keys"]
        ),
        "mechanism_code_counts": dict(sorted(mechanisms.items())),
        "strict_to_clinical_discordance": resolution,
    }


def build_analysis(out: Path, repetitions: int) -> dict[str, Any]:
    adjudication_path = out / ADJUDICATION_NAME
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    if file_sha256(out / "semantic_screen" / "screen_results.jsonl") != adjudication["source_screen_results_sha256"]:
        raise AssertionError("root adjudication screen hash mismatch")
    if file_sha256(out / "case_matrix.jsonl") != adjudication["source_case_matrix_sha256"]:
        raise AssertionError("root adjudication case-matrix hash mismatch")

    arms = _arm_rows(out)
    screen_list = read_jsonl(out / "semantic_screen" / "screen_results.jsonl")
    screen_rows = {str(row["case_key"]): row for row in screen_list}
    if len(screen_rows) != 400:
        raise AssertionError("screen must contain 400 unique cases")
    case_keys = sorted(screen_rows)
    relations, relation_provenance = resolve_candidate_relations(
        screen_rows, adjudication
    )
    strict = _strict_endpoints(arms)
    clinical = _endpoint_maps(case_keys, relations, COMPLETE)
    partial = _endpoint_maps(case_keys, relations, COMPLETE_OR_PARTIAL)
    clinical_contrasts = _contrast_family(
        clinical, case_keys, repetitions, "clinical-complete"
    )
    partial_contrasts = _contrast_family(
        partial, case_keys, repetitions, "complete-or-partial"
    )
    relevant_off_critical: set[str] = set()
    for endpoint in ("top1", "top2"):
        contrast = next(
            row for row in clinical_contrasts[endpoint]
            if row["label"] == "relevant_vs_off_without_refine"
        )
        relevant_off_critical.update(contrast["gain_case_keys"])
        relevant_off_critical.update(contrast["loss_case_keys"])
    deep_review = set(adjudication["deep_review_case_keys"])
    missed_critical = relevant_off_critical - deep_review
    if missed_critical:
        raise AssertionError(
            "root deep review omits clinical-complete relevant-vs-off "
            f"discordance: {sorted(missed_critical)}"
        )
    strata: dict[str, list[str]] = {
        "family_DA": sorted(
            key for key, row in screen_rows.items() if row["family"] == "DA"
        ),
        "family_MCR": sorted(
            key for key, row in screen_rows.items() if row["family"] == "MCR"
        ),
        "historical_gate_false": sorted(
            key for key, row in screen_rows.items()
            if not bool(row["historical_need_retrieval"])
        ),
        "historical_gate_true": sorted(
            key for key, row in screen_rows.items()
            if bool(row["historical_need_retrieval"])
        ),
    }

    candidate_component = read_jsonl(
        out / "semantic_screen" / "candidate" / "case_results.jsonl"
    )
    analysis = {
        "schema": "e11_root_clinical_analysis_v1",
        "experiment_id": "E11",
        "n_cases": len(case_keys),
        "bootstrap_repetitions": repetitions,
        "endpoint_scope": {
            "strict": "frozen exact/safe-synonym bridge; preregistered primary",
            "clinical_complete": (
                f"root overrides on {len(adjudication['cases'])} "
                "critical/failure cases plus heterogeneous proxy elsewhere"
            ),
            "complete_or_partial": "sensitivity endpoint that also accepts broader/underspecified disease-family labels",
        },
        "root_review_coverage": {
            "clinical_complete_relevant_vs_off_discordant_case_keys": sorted(
                relevant_off_critical
            ),
            "all_clinical_complete_relevant_vs_off_discordances_reviewed": True,
        },
        "relation_provenance": relation_provenance,
        "candidate_screen": {
            "n_success": sum(bool(row["success"]) for row in candidate_component),
            "n_failed": sum(not bool(row["success"]) for row in candidate_component),
            "failure_reason_counts": dict(sorted(Counter(
                str(row["error"]) for row in candidate_component if not row["success"]
            ).items())),
        },
        "strict_arm_statistics": _arm_statistics(strict),
        "clinical_complete_arm_statistics": _arm_statistics(clinical),
        "complete_or_partial_arm_statistics": _arm_statistics(partial),
        "clinical_complete_contrasts": clinical_contrasts,
        "complete_or_partial_contrasts": partial_contrasts,
        "clinical_complete_stratified": {
            name: {
                "n": len(keys),
                "arm_statistics": _arm_statistics(clinical, keys),
                "contrasts": _contrast_family(
                    clinical, keys, repetitions, f"clinical-complete/{name}"
                ),
            }
            for name, keys in strata.items()
        },
        "retrieval_screen_analysis": _retrieval_screen_analysis(
            out, screen_rows, strict, clinical, repetitions
        ),
        "manual_audit_summary": _manual_summary(
            adjudication, strict, clinical
        ),
        "interpretation_boundary": adjudication["interpretation_boundary"],
        "external_llm_role": "queue-expansion subcontractor only; root owns listed judgments and final interpretation",
    }
    atomic_json(out / "root_clinical_analysis.json", analysis)

    documents = {str(row["case_key"]): row for row in case_documents(out)}
    selected = sorted(adjudication["cases"])
    deep_set = set(adjudication["deep_review_case_keys"])
    failure_set = set(adjudication["candidate_screen_failure_case_keys"])
    queue: list[dict[str, Any]] = []
    for case_key in selected:
        queue.append({
            "case_key": case_key,
            "categories": sorted(
                (["endpoint_critical_deep_review"] if case_key in deep_set else [])
                + (["candidate_screen_failure"] if case_key in failure_set else [])
            ),
            "family": documents[case_key]["family"],
            "reference_diagnosis": documents[case_key]["reference_diagnosis"],
            "vignette": documents[case_key]["vignette"],
            "historical_need_retrieval": documents[case_key]["historical_need_retrieval"],
            "candidate_registry": screen_rows[case_key]["candidate_registry"],
            "retrieval_bundles": documents[case_key]["bundles"],
            "retrieved_chunks": documents[case_key]["chunks"],
            "screen_result": screen_rows[case_key],
            "arms": {arm: arms[arm][case_key] for arm in ARMS},
            "root_judgment": adjudication["cases"][case_key],
        })
    write_jsonl(out / "root_audit_queue.jsonl", queue)
    audit_summary = {
        **analysis["manual_audit_summary"],
        "queue_rows": len(queue),
        "queue_sha256": file_sha256(out / "root_audit_queue.jsonl"),
        "adjudication_sha256": file_sha256(adjudication_path),
        "root_clinical_analysis_sha256": file_sha256(out / "root_clinical_analysis.json"),
        "root_responsibility": True,
    }
    atomic_json(out / "root_audit_summary.json", audit_summary)
    (out / "manual_audit_run.log").write_text(
        "E11 root audit completed\n"
        f"root_candidate_cases={audit_summary['n_root_candidate_cases']}\n"
        f"deep_trajectory_cases={audit_summary['n_deep_trajectory_cases']}\n"
        f"candidate_screen_failures={audit_summary['n_candidate_screen_failure_cases']}\n"
        f"queue_sha256={audit_summary['queue_sha256']}\n"
        f"analysis_sha256={audit_summary['root_clinical_analysis_sha256']}\n",
        encoding="utf-8",
    )
    return analysis


def archive_outputs(out: Path) -> None:
    archive = out / "ROOT_AUDIT_ARTIFACTS.tar.gz"
    names = (
        ADJUDICATION_NAME,
        "root_audit_queue.jsonl",
        "root_audit_summary.json",
        "root_clinical_analysis.json",
        "manual_audit_run.log",
    )
    with tarfile.open(archive, "w:gz") as bundle:
        for name in names:
            bundle.add(out / name, arcname=name)
    digest = file_sha256(archive)
    (out / f"{archive.name}.sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    analysis = build_analysis(out, args.bootstrap_repetitions)
    archive_outputs(out)
    print(json.dumps({
        "n_cases": analysis["n_cases"],
        "root_cases": analysis["manual_audit_summary"]["n_root_candidate_cases"],
        "retrieval_screen_valid": analysis["retrieval_screen_analysis"]["n_valid_cases"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
