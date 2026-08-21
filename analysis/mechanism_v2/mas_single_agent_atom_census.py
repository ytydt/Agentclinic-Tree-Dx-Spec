#!/usr/bin/env python3
"""Offline census for Forest, IMPC, Collapse3c, and MultiStance as MAS atoms.

The script never invokes a model or a network API.  It binds every consumed
trajectory to the requested Git commit, joins the frozen E2 root endpoint
replay, and reports proposal diversity, champion disagreement, correct-minority
risk, and primary-label candidate survival across the four atoms.  The original
three-atom census is retained as a nested diagnostic so the incremental effect
of adding MultiStance can be measured without changing its historical meaning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


DATASETS = {
    "diagnosisarena": ("DA_d2_seq100", 100),
    "diagnosisarena_heldout": ("DA_d2_heldout100", 100),
    "diagnosisarena_heldout200b": ("DA_d2_heldout200b", 200),
    "medcasereasoning": ("MCR_v1_seq100", 100),
    "medcasereasoning_200b": ("MCR_seq200b", 200),
    "medcasereasoning_v2": ("MCR_v2_seq100", 100),
}

ARMS = {
    "forest": "mosaic_forest_v1",
    "impc": "mosaic_impc_v1",
    "collapse3c": "aphhm_c_collapse3c_v1",
    "multistance": "aphhm_c_multistance_v1",
}
TRIAD_ARMS = ("forest", "impc", "collapse3c")
APHMM_ARMS = {"collapse3c", "multistance"}


def _norm(value: Any) -> str:
    text = str(value or "").casefold().replace("–", "-").replace("—", "-")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _git(args: list[str], repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8"
    )


def _mean(values: Iterable[float]) -> float:
    vals = list(values)
    return round(statistics.fmean(vals), 6) if vals else 0.0


def _primary_candidates(arm: str, raw: dict[str, Any]) -> list[str]:
    registry = raw.get("stages", {}).get("registry", [])
    key = "preferred_label" if arm in APHMM_ARMS else "preferred_name"
    return [str(item.get(key, "")).strip() for item in registry if item.get(key)]


def _frontier_candidates(arm: str, raw: dict[str, Any]) -> list[str]:
    stages = raw.get("stages", {})
    if arm not in APHMM_ARMS:
        return [
            str(item.get("preferred_name", "")).strip()
            for item in stages.get("frontier_final", [])
            if item.get("preferred_name")
        ]
    registry = {
        str(item.get("concept_id")): str(item.get("preferred_label", "")).strip()
        for item in stages.get("registry", [])
    }
    return [registry[cid] for cid in stages.get("frontier", []) if registry.get(cid)]


def _load_trajectories(repo: Path, commit: str) -> tuple[dict[tuple[str, str], dict], dict]:
    records: dict[tuple[str, str], dict] = {}
    consumed_paths: list[str] = []
    expected_paths: set[str] = set()
    for dataset, (slice_id, expected_n) in DATASETS.items():
        for arm, arm_dir in ARMS.items():
            root = repo / "logs" / "backbone_v1" / dataset / arm_dir / "case_stages"
            paths = sorted(root.glob("*.json"), key=lambda p: (len(p.stem), p.stem))
            if len(paths) != expected_n:
                raise ValueError(f"{dataset}/{arm}: expected {expected_n}, found {len(paths)}")
            for path in paths:
                rel = path.relative_to(repo).as_posix()
                expected_paths.add(rel)
                raw_bytes = path.read_bytes()
                raw = json.loads(raw_bytes)
                case_id = str(raw.get("source_id", path.stem))
                if case_id != path.stem:
                    raise ValueError(f"case id/path mismatch: {rel}")
                case_key = f"{slice_id}/{case_id}"
                key = (case_key, arm)
                if key in records:
                    raise ValueError(f"duplicate trajectory key: {key}")
                records[key] = {
                    "case_key": case_key,
                    "arm": arm,
                    "path": rel,
                    "git_blob_sha1": _git_blob_sha1(raw_bytes),
                    "champion": str(raw.get("champion", "")).strip(),
                    "champion_norm": _norm(raw.get("champion", "")),
                    "candidates": _primary_candidates(arm, raw),
                    "frontier": _frontier_candidates(arm, raw),
                    "llm_calls": int(raw.get("llm_calls", raw.get("metrics", {}).get("llm_calls", 0))),
                    "raw": raw,
                }
                consumed_paths.append(rel)

    tree_lines = _git(["ls-tree", "-r", commit, "--", "logs/backbone_v1"], repo).splitlines()
    tree_blobs: dict[str, str] = {}
    for line in tree_lines:
        meta, path = line.split("\t", 1)
        _mode, obj_type, sha = meta.split()
        if obj_type == "blob" and path in expected_paths:
            tree_blobs[path] = sha
    if set(tree_blobs) != expected_paths:
        missing = sorted(expected_paths - set(tree_blobs))
        raise ValueError(f"source commit is missing {len(missing)} expected trajectories")
    mismatches = [
        rec["path"]
        for rec in records.values()
        if tree_blobs[rec["path"]] != rec["git_blob_sha1"]
    ]
    if mismatches:
        raise ValueError(f"working-tree/Git blob mismatch in {len(mismatches)} trajectories")
    return records, {
        "files_verified": len(consumed_paths),
        "unique_paths": len(set(consumed_paths)),
        "source_tree_verified": True,
    }


def _load_endpoints(path: Path) -> dict[tuple[str, str], dict]:
    wanted = set(ARMS)
    rows: dict[tuple[str, str], dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        arm = str(row.get("arm_id"))
        if arm not in wanted:
            continue
        key = (str(row["case_key"]), arm)
        if key in rows:
            raise ValueError(f"duplicate E2 endpoint key: {key}")
        if row.get("clinical_audit_status") != "root_adjudicated":
            raise ValueError(f"non-root E2 row encountered: {key}")
        rows[key] = row
    expected_rows = 800 * len(ARMS)
    if len(rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} E2 atom rows, found {len(rows)}")
    return rows


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def _candidate_channel_summary(arm: str, records: list[dict]) -> dict:
    candidate_rows = []
    for rec in records:
        for item in rec["raw"].get("stages", {}).get("registry", []):
            candidate_rows.append(item)
    if arm == "forest":
        return {
            "candidate_rows_n": len(candidate_rows),
            "multi_view_candidates_n": sum(
                len(set(x.get("generator_views", []))) > 1 for x in candidate_rows
            ),
            "protected_candidates_n": sum(bool(x.get("protected_reason")) for x in candidate_rows),
            "with_support_n": sum(bool(x.get("supporting_evidence")) for x in candidate_rows),
            "with_against_n": sum(bool(x.get("contradicting_evidence")) for x in candidate_rows),
        }
    if arm == "impc":
        votes = Counter(int(x.get("agent_votes", 0)) for x in candidate_rows)
        views = Counter(len(set(x.get("generator_views", []))) for x in candidate_rows)
        return {
            "candidate_rows_n": len(candidate_rows),
            "generator_view_count_distribution": {str(k): views[k] for k in sorted(views)},
            "single_view_candidates_n": views.get(1, 0),
            "merge_occurrence_vote_distribution": {str(k): votes[k] for k in sorted(votes)},
            "merge_vote_exceeds_unique_view_count_n": sum(
                int(x.get("agent_votes", 0)) > len(set(x.get("generator_views", [])))
                for x in candidate_rows
            ),
            "with_support_n": sum(bool(x.get("supporting_evidence")) for x in candidate_rows),
            "with_against_n": sum(bool(x.get("contradicting_evidence")) for x in candidate_rows),
        }
    base = {
        "candidate_rows_n": len(candidate_rows),
        "multi_provenance_candidates_n": sum(
            len(set(x.get("recall_provenance", []))) > 1 for x in candidate_rows
        ),
        "with_support_fact_ids_n": sum(bool(x.get("support_fact_ids")) for x in candidate_rows),
        "with_support_spans_n": sum(bool(x.get("support_spans")) for x in candidate_rows),
        "with_against_spans_n": sum(bool(x.get("contradict_spans")) for x in candidate_rows),
        "with_against_fact_ids_n": sum(bool(x.get("against_fact_ids")) for x in candidate_rows),
    }
    if arm != "multistance":
        return base
    stance_counts = Counter()
    first_stance_counts = Counter()
    multi_stance = 0
    selector_finalist_rows = 0
    selector_cases_with_finalists = 0
    for rec in records:
        for item in rec["raw"].get("stages", {}).get("registry", []):
            stances = list(dict.fromkeys(str(x) for x in item.get("stances", []) if x))
            for stance in stances:
                stance_counts[stance] += 1
            if stances:
                first_stance_counts[stances[0]] += 1
            multi_stance += len(stances) > 1
        selector = rec["raw"].get("stages", {}).get("frontier_selector", {})
        finalists = selector.get("finalists") if isinstance(selector, dict) else None
        if isinstance(finalists, list):
            selector_cases_with_finalists += 1
            selector_finalist_rows += len(finalists)
    return {
        **base,
        "stance_candidate_memberships": dict(sorted(stance_counts.items())),
        "first_stance_group_assignment": dict(sorted(first_stance_counts.items())),
        "multi_stance_candidates_n": multi_stance,
        "selector_cases_with_finalists_n": selector_cases_with_finalists,
        "selector_finalist_rows_n": selector_finalist_rows,
    }


def _agreement_pattern(values: list[str]) -> str:
    multiplicities = sorted(Counter(values).values(), reverse=True)
    return "+".join(str(value) for value in multiplicities)


def _subset_census(
    cases: list[str],
    arms: tuple[str, ...],
    trajectories: dict[tuple[str, str], dict],
    endpoints: dict[tuple[str, str], dict],
) -> dict[str, Any]:
    unique_correct = Counter()
    majority_suppression_risk = Counter()
    complete_hist = Counter()
    agreement_patterns = Counter()
    oracle_complete = 0
    oracle_partial_or_complete = 0
    unique_cases: list[dict[str, Any]] = []
    by_family: dict[str, dict[str, Any]] = {
        family: {
            "cases_n": 0,
            "complete_hist": Counter(),
            "per_arm_complete": Counter(),
            "unique_correct": Counter(),
            "wrong_majority_same_cluster": 0,
            "all_wrong_same_cluster": 0,
            "unique_label_in_any_wrong_pool": 0,
            "unique_label_in_all_wrong_pools": 0,
            "oracle_complete": 0,
        }
        for family in ("DA", "MCR")
    }

    for case_key in cases:
        family = "DA" if case_key.startswith("DA_") else "MCR"
        family_stats = by_family[family]
        family_stats["cases_n"] += 1
        rows = {arm: endpoints[(case_key, arm)] for arm in arms}
        recs = {arm: trajectories[(case_key, arm)] for arm in arms}
        complete_arms = [arm for arm, row in rows.items() if bool(row["clinical_complete"])]
        complete_hist[len(complete_arms)] += 1
        family_stats["complete_hist"][len(complete_arms)] += 1
        for arm in complete_arms:
            family_stats["per_arm_complete"][arm] += 1
        oracle_complete += bool(complete_arms)
        family_stats["oracle_complete"] += bool(complete_arms)
        oracle_partial_or_complete += any(
            bool(row["clinical_complete"] or row["partial"]) for row in rows.values()
        )
        agreement_patterns[_agreement_pattern([recs[arm]["champion_norm"] for arm in arms])] += 1

        if len(complete_arms) != 1:
            continue
        correct_arm = complete_arms[0]
        unique_correct[correct_arm] += 1
        family_stats["unique_correct"][correct_arm] += 1
        wrong_arms = [arm for arm in arms if arm != correct_arm]
        cluster_counts = Counter(rows[arm]["output_cluster_id"] for arm in wrong_arms)
        modal_cluster_size = max(cluster_counts.values(), default=0)
        wrong_majority_same = modal_cluster_size >= (len(wrong_arms) // 2 + 1)
        all_wrong_same = modal_cluster_size == len(wrong_arms)
        if wrong_majority_same:
            majority_suppression_risk[correct_arm] += 1
            family_stats["wrong_majority_same_cluster"] += 1
        family_stats["all_wrong_same_cluster"] += all_wrong_same
        correct_label = recs[correct_arm]["champion_norm"]
        pool_presence = {
            arm: correct_label in {_norm(x) for x in recs[arm]["candidates"]}
            for arm in wrong_arms
        }
        family_stats["unique_label_in_any_wrong_pool"] += any(pool_presence.values())
        family_stats["unique_label_in_all_wrong_pools"] += all(pool_presence.values())
        unique_cases.append(
            {
                "case_key": case_key,
                "reference_diagnosis": rows[correct_arm]["reference_diagnosis"],
                "correct_atom": correct_arm,
                "wrong_atom_modal_output_cluster_size": modal_cluster_size,
                "wrong_atom_majority_same_output_cluster": wrong_majority_same,
                "all_wrong_atoms_same_output_cluster": all_wrong_same,
                "predictions": {arm: recs[arm]["champion"] for arm in arms},
                "relations": {arm: rows[arm]["clinical_relation"] for arm in arms},
                "correct_primary_label_in_wrong_atom_pool": pool_presence,
                "correct_label_present_in_any_wrong_pool": any(pool_presence.values()),
                "correct_label_present_in_all_wrong_pools": all(pool_presence.values()),
            }
        )

    best_single = max(
        sum(bool(endpoints[(case_key, arm)]["clinical_complete"]) for case_key in cases)
        for arm in arms
    )
    by_family_out = {}
    for family, stats in by_family.items():
        family_best = max(stats["per_arm_complete"].values(), default=0)
        by_family_out[family] = {
            "cases_n": stats["cases_n"],
            "per_arm_clinical_complete_n": {
                arm: stats["per_arm_complete"][arm] for arm in arms
            },
            "clinical_complete_atom_count": {
                str(k): stats["complete_hist"][k] for k in range(len(arms) + 1)
            },
            "oracle_any_complete_n": stats["oracle_complete"],
            "best_single_complete_n": family_best,
            "oracle_minus_best_single_n": stats["oracle_complete"] - family_best,
            "unique_correct_atom_n": {
                arm: stats["unique_correct"][arm] for arm in arms
            },
            "wrong_atom_majority_same_output_cluster_n": stats[
                "wrong_majority_same_cluster"
            ],
            "all_wrong_atoms_same_output_cluster_n": stats["all_wrong_same_cluster"],
            "unique_correct_with_label_in_any_wrong_pool_n": stats[
                "unique_label_in_any_wrong_pool"
            ],
            "unique_correct_with_label_in_all_wrong_pools_n": stats[
                "unique_label_in_all_wrong_pools"
            ],
        }
    return {
        "arms": list(arms),
        "exact_champion_agreement_pattern": dict(sorted(agreement_patterns.items())),
        "clinical_complete_atom_count": {
            str(k): complete_hist[k] for k in range(len(arms) + 1)
        },
        "oracle_any_complete_n": oracle_complete,
        "best_single_complete_n": best_single,
        "oracle_minus_best_single_n": oracle_complete - best_single,
        "oracle_any_complete_or_partial_n": oracle_partial_or_complete,
        "unique_correct_atom_n": {arm: unique_correct[arm] for arm in arms},
        "wrong_majority_consensus_suppression_risk_n": sum(
            majority_suppression_risk.values()
        ),
        "wrong_majority_consensus_suppression_risk_by_correct_atom": {
            arm: majority_suppression_risk[arm] for arm in arms
        },
        "unique_correct_with_label_in_any_wrong_pool_n": sum(
            item["correct_label_present_in_any_wrong_pool"] for item in unique_cases
        ),
        "unique_correct_with_label_in_all_wrong_pools_n": sum(
            item["correct_label_present_in_all_wrong_pools"] for item in unique_cases
        ),
        "by_benchmark_family": by_family_out,
        "unique_correct_cases": unique_cases,
    }


def build(repo: Path, commit: str, replay_path: Path) -> dict:
    """Build the four-atom census while retaining the historical triad estimand."""
    trajectories, verification = _load_trajectories(repo, commit)
    endpoints = _load_endpoints(replay_path)
    if set(trajectories) != set(endpoints):
        raise ValueError("trajectory and E2 atom keys do not match")

    cases = sorted({case_key for case_key, _arm in trajectories})
    arm_records = {
        arm: [trajectories[(case_key, arm)] for case_key in cases] for arm in ARMS
    }
    triad_raw = _subset_census(cases, TRIAD_ARMS, trajectories, endpoints)
    quartet_raw = _subset_census(cases, tuple(ARMS), trajectories, endpoints)

    triad_cases = triad_raw.pop("unique_correct_cases")
    quartet_cases = quartet_raw.pop("unique_correct_cases")
    triad_by_family = triad_raw.pop("by_benchmark_family")
    quartet_by_family = quartet_raw.pop("by_benchmark_family")
    quartet_raw["wrong_plurality_or_tie_suppression_risk_n"] = quartet_raw[
        "wrong_majority_consensus_suppression_risk_n"
    ]
    quartet_raw[
        "wrong_plurality_or_tie_suppression_risk_by_correct_atom"
    ] = quartet_raw["wrong_majority_consensus_suppression_risk_by_correct_atom"]
    for row in quartet_cases:
        row["wrong_atom_plurality_or_tie_same_output_cluster"] = row[
            "wrong_atom_majority_same_output_cluster"
        ]

    # Keep v3 aliases so historical consumers do not silently change the
    # original three-arm estimand when they adopt the four-arm artifact.
    triad = {
        **triad_raw,
        "exact_champion_agreement": {
            "all_exact_agree": triad_raw["exact_champion_agreement_pattern"].get("3", 0),
            "two_exact_agree": triad_raw["exact_champion_agreement_pattern"].get("2+1", 0),
            "all_exact_different": triad_raw["exact_champion_agreement_pattern"].get(
                "1+1+1", 0
            ),
        },
        "wrong_consensus_suppression_risk_n": triad_raw[
            "wrong_majority_consensus_suppression_risk_n"
        ],
        "wrong_consensus_suppression_risk_by_correct_atom": triad_raw[
            "wrong_majority_consensus_suppression_risk_by_correct_atom"
        ],
        "unique_correct_with_label_in_both_wrong_pools_n": triad_raw[
            "unique_correct_with_label_in_all_wrong_pools_n"
        ],
    }

    per_arm = {}
    for arm, records in arm_records.items():
        ep = [endpoints[(case_key, arm)] for case_key in cases]
        per_arm[arm] = {
            "cases_n": len(records),
            "safe_exact_n": sum(bool(row["safe_exact"]) for row in ep),
            "legacy_chain_n": sum(bool(row["legacy_chain"]) for row in ep),
            "task_n": sum(bool(row["task"]) for row in ep),
            "clinical_complete_n": sum(bool(row["clinical_complete"]) for row in ep),
            "compatible_partial_n": sum(bool(row["partial"]) for row in ep),
            "complete_or_partial_n": sum(
                bool(row["clinical_complete"] or row["partial"]) for row in ep
            ),
            "four_atom_unique_correct_atom_n": quartet_raw["unique_correct_atom_n"][arm],
            "four_atom_wrong_plurality_or_tie_suppression_risk_n": quartet_raw[
                "wrong_majority_consensus_suppression_risk_by_correct_atom"
            ][arm],
            "triad_unique_correct_atom_n": triad_raw["unique_correct_atom_n"].get(arm),
            "triad_wrong_consensus_suppression_risk_n": triad_raw[
                "wrong_majority_consensus_suppression_risk_by_correct_atom"
            ].get(arm),
            "mean_primary_candidates": _mean(len(rec["candidates"]) for rec in records),
            "mean_frontier_candidates": _mean(len(rec["frontier"]) for rec in records),
            "mean_llm_calls": _mean(rec["llm_calls"] for rec in records),
            "llm_call_distribution": {
                str(k): v
                for k, v in sorted(Counter(rec["llm_calls"] for rec in records).items())
            },
            "channel_structure": _candidate_channel_summary(arm, records),
        }

    pairwise = {}
    arm_names = list(ARMS)
    for i, left in enumerate(arm_names):
        for right in arm_names[i + 1 :]:
            stats = Counter()
            jaccards, union_sizes, intersection_sizes = [], [], []
            for case_key in cases:
                lrec, rrec = trajectories[(case_key, left)], trajectories[(case_key, right)]
                lrow, rrow = endpoints[(case_key, left)], endpoints[(case_key, right)]
                lset = {_norm(x) for x in lrec["candidates"] if _norm(x)}
                rset = {_norm(x) for x in rrec["candidates"] if _norm(x)}
                stats["exact_champion_agreement_n"] += (
                    lrec["champion_norm"] == rrec["champion_norm"]
                )
                stats["same_output_cluster_n"] += (
                    lrow["output_cluster_id"] == rrow["output_cluster_id"]
                )
                stats["left_champion_in_right_primary_pool_n"] += (
                    lrec["champion_norm"] in rset
                )
                stats["right_champion_in_left_primary_pool_n"] += (
                    rrec["champion_norm"] in lset
                )
                stats["both_complete_n"] += bool(
                    lrow["clinical_complete"] and rrow["clinical_complete"]
                )
                stats["left_only_complete_n"] += bool(
                    lrow["clinical_complete"] and not rrow["clinical_complete"]
                )
                stats["right_only_complete_n"] += bool(
                    rrow["clinical_complete"] and not lrow["clinical_complete"]
                )
                stats["neither_complete_n"] += bool(
                    not lrow["clinical_complete"] and not rrow["clinical_complete"]
                )
                jaccards.append(_jaccard(lset, rset))
                union_sizes.append(len(lset | rset))
                intersection_sizes.append(len(lset & rset))
            pairwise[f"{left}__{right}"] = {
                **dict(stats),
                "mean_primary_pool_jaccard": _mean(jaccards),
                "mean_primary_pool_union_n": _mean(union_sizes),
                "mean_primary_pool_intersection_n": _mean(intersection_sizes),
            }

    multistance_increment = Counter()
    multistance_only_cases = []
    collapse_commit_jaccards = []
    commit_new_over_collapse = []
    residual_new_over_collapse_and_commit = []
    multistance_span_stats = Counter()
    for case_key in cases:
        ms_rec = trajectories[(case_key, "multistance")]
        collapse_rec = trajectories[(case_key, "collapse3c")]
        ms_champion_stances = sorted(
            {
                str(stance)
                for item in ms_rec["raw"].get("stages", {}).get("registry", [])
                if _norm(item.get("preferred_label")) == ms_rec["champion_norm"]
                for stance in item.get("stances", [])
                if stance
            }
        )
        triad_any = any(
            bool(endpoints[(case_key, arm)]["clinical_complete"]) for arm in TRIAD_ARMS
        )
        multistance_complete = bool(endpoints[(case_key, "multistance")]["clinical_complete"])
        if triad_any and multistance_complete:
            multistance_increment["both_complete"] += 1
        elif triad_any:
            multistance_increment["triad_only_complete"] += 1
        elif multistance_complete:
            multistance_increment["multistance_only_complete"] += 1
            ms_label = ms_rec["champion_norm"]
            triad_pool_presence = {
                arm: ms_label
                in {_norm(candidate) for candidate in trajectories[(case_key, arm)]["candidates"]}
                for arm in TRIAD_ARMS
            }
            multistance_only_cases.append(
                {
                    "case_key": case_key,
                    "reference_diagnosis": endpoints[(case_key, "multistance")][
                        "reference_diagnosis"
                    ],
                    "multistance_prediction": ms_rec["champion"],
                    "multistance_champion_stances": ms_champion_stances,
                    "correct_label_in_triad_primary_pool": triad_pool_presence,
                    "correct_label_present_in_any_triad_primary_pool": any(
                        triad_pool_presence.values()
                    ),
                }
            )
        else:
            multistance_increment["neither_complete"] += 1

        collapse_row = endpoints[(case_key, "collapse3c")]
        ms_row = endpoints[(case_key, "multistance")]
        if ms_row["clinical_complete"] and not collapse_row["clinical_complete"]:
            multistance_increment["multistance_rescue_over_collapse"] += 1
            multistance_increment["rescue_champion_with_commit_provenance"] += (
                "commit" in ms_champion_stances
            )
            multistance_increment["rescue_champion_coverage_only"] += (
                ms_champion_stances == ["coverage"]
            )
            multistance_increment[
                "rescue_champion_present_in_collapse_primary_pool"
            ] += ms_rec["champion_norm"] in {
                _norm(candidate) for candidate in collapse_rec["candidates"]
            }
        if collapse_row["clinical_complete"] and not ms_row["clinical_complete"]:
            multistance_increment["multistance_loss_against_collapse"] += 1
            multistance_increment["loss_champion_with_commit_provenance"] += (
                "commit" in ms_champion_stances
            )
            multistance_increment[
                "correct_collapse_champion_present_in_multistance_primary_pool"
            ] += collapse_rec["champion_norm"] in {
                _norm(candidate) for candidate in ms_rec["candidates"]
            }
            multistance_increment[
                f"loss_relation__{ms_row['clinical_relation']}"
            ] += 1
        if collapse_row["output_cluster_id"] == ms_row["output_cluster_id"]:
            multistance_increment["collapse_multistance_same_output_cluster"] += 1
            if (
                not collapse_row["clinical_complete"]
                and not ms_row["clinical_complete"]
                and any(
                    endpoints[(case_key, arm)]["clinical_complete"]
                    for arm in ("forest", "impc")
                )
            ):
                multistance_increment[
                    "same_lineage_same_wrong_cluster_other_core_complete"
                ] += 1

        collapse_set = {
            _norm(candidate)
            for candidate in collapse_rec["candidates"]
            if _norm(candidate)
        }
        ms_registry = ms_rec["raw"].get("stages", {}).get("registry", [])
        span_rows = []
        for item in ms_registry:
            support_spans = [
                str(span) for span in item.get("support_spans", []) if span
            ]
            contradict_spans = [
                str(span) for span in item.get("contradict_spans", []) if span
            ]
            span_rows.append((support_spans, contradict_spans))
            multistance_span_stats["support_span_entries_n"] += len(support_spans)
            multistance_span_stats[
                "candidate_rows_same_exact_raw_span_in_support_and_against_n"
            ] += bool(set(support_spans) & set(contradict_spans))
            multistance_span_stats[
                "candidate_rows_same_normalized_span_in_support_and_against_n"
            ] += bool(
                {_norm(span) for span in support_spans}
                & {_norm(span) for span in contradict_spans}
            )
        for row_index, (support_spans, _) in enumerate(span_rows):
            other_support_exact = {
                span
                for other_index, (other_support, _) in enumerate(span_rows)
                if other_index != row_index
                for span in other_support
            }
            other_support_normalized = {
                _norm(span) for span in other_support_exact
            }
            multistance_span_stats[
                "support_entries_exact_raw_span_used_by_other_candidate_n"
            ] += sum(span in other_support_exact for span in support_spans)
            multistance_span_stats[
                "support_entries_normalized_span_used_by_other_candidate_n"
            ] += sum(
                _norm(span) in other_support_normalized for span in support_spans
            )
        commit_set = {
            _norm(item.get("preferred_label"))
            for item in ms_registry
            if "commit" in item.get("stances", []) and _norm(item.get("preferred_label"))
        }
        residual_set = {
            _norm(item.get("preferred_label"))
            for item in ms_registry
            if any(stance in {"coverage", "mechanism"} for stance in item.get("stances", []))
            and _norm(item.get("preferred_label"))
        }
        collapse_commit_jaccards.append(_jaccard(collapse_set, commit_set))
        commit_new_over_collapse.append(len(commit_set - collapse_set))
        residual_new_over_collapse_and_commit.append(
            len(residual_set - collapse_set - commit_set)
        )

    return {
        "schema_version": "mas-single-agent-atom-census-v4-multistance",
        "scope": "Offline observational census; no model/API calls and no new clinical adjudication.",
        "publication_contract": {
            "case_level_records_included": True,
            "case_level_scope": (
                "Cases in which exactly one atom is clinically complete, reported separately "
                "for the historical three-atom and four-atom sets."
            ),
            "case_level_diagnoses_included": True,
            "case_level_predictions_included": True,
            "case_level_clinical_relations_included": True,
            "raw_vignette_text_included": False,
            "authorization": (
                "The user explicitly authorized public release of dataset-derived outputs, "
                "including per-case consensus, on 2026-08-21."
            ),
        },
        "interpretation_contract": [
            "Oracle unions are upper-bound complementarity diagnostics, not achievable MAS scores.",
            "MultiStance shares its C1 fact substrate across three stance prompts; its stances are not independent votes.",
            "MultiStance is evaluated here as the historically served tournament champion; the proposed transfer exports its pre-tournament registry instead.",
            "Root labels adjudicate served champions, not every candidate in each registry.",
            "Cross-atom candidate presence uses normalized primary labels only; it is not a clinical synonym or ontology matcher.",
            "Wrong atoms sharing an E2 output cluster marks majority-suppression risk, not proof that a particular aggregator would vote that way.",
            "For the four-atom unique-correct subset, two or more of the three wrong arms sharing a cluster is a wrong-plurality or 2-2-tie risk, not necessarily an absolute majority of all four arms.",
        ],
        "provenance": {
            "source_commit": commit,
            "script_sha256": _sha256(Path(__file__).resolve()),
            "e2_replay_path": replay_path.relative_to(repo).as_posix(),
            "e2_replay_sha256": _sha256(replay_path),
            **verification,
        },
        "cases_n": len(cases),
        "case_arm_rows_n": len(trajectories),
        "per_arm": per_arm,
        "pairwise": pairwise,
        "by_benchmark_family": triad_by_family,
        "four_atom_by_benchmark_family": quartet_by_family,
        "triad": triad,
        "four_atom": quartet_raw,
        "multistance_incremental_over_triad": {
            **dict(multistance_increment),
            "multistance_only_complete_correct_label_in_any_triad_primary_pool_n": sum(
                row["correct_label_present_in_any_triad_primary_pool"]
                for row in multistance_only_cases
            ),
            "multistance_only_complete_correct_label_absent_from_all_triad_primary_pools_n": sum(
                not row["correct_label_present_in_any_triad_primary_pool"]
                for row in multistance_only_cases
            ),
            "multistance_only_complete_champion_with_commit_provenance_n": sum(
                "commit" in row["multistance_champion_stances"]
                for row in multistance_only_cases
            ),
            "mean_multistance_commit_pool_vs_collapse_pool_jaccard": _mean(
                collapse_commit_jaccards
            ),
            "mean_multistance_commit_labels_absent_from_collapse_pool_n": _mean(
                commit_new_over_collapse
            ),
            "mean_coverage_or_mechanism_labels_absent_from_collapse_and_commit_pools_n": _mean(
                residual_new_over_collapse_and_commit
            ),
            "span_reuse_diagnostic": dict(multistance_span_stats),
            "four_atom_oracle_minus_triad_oracle_n": (
                quartet_raw["oracle_any_complete_n"] - triad_raw["oracle_any_complete_n"]
            ),
        },
        "unique_correct_cases": triad_cases,
        "four_atom_unique_correct_cases": quartet_cases,
        "multistance_only_complete_cases": multistance_only_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--e2-replay",
        type=Path,
        default=Path(
            "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/"
            "unified_800/five_endpoint_replay.jsonl"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    replay = args.e2_replay if args.e2_replay.is_absolute() else repo / args.e2_replay
    output = args.output if args.output.is_absolute() else repo / args.output
    result = build(repo, args.source_commit, replay)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
