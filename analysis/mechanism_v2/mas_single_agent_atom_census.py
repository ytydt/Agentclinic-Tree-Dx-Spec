#!/usr/bin/env python3
"""Offline census for Forest, IMPC, and Collapse3c as MAS agent atoms.

The script never invokes a model or a network API.  It binds every consumed
trajectory to the requested Git commit, joins the frozen E2 root endpoint
replay, and reports proposal diversity, champion disagreement, correct-minority
risk, and primary-label candidate survival across the three atoms.
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
}


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
    key = "preferred_label" if arm == "collapse3c" else "preferred_name"
    return [str(item.get(key, "")).strip() for item in registry if item.get(key)]


def _frontier_candidates(arm: str, raw: dict[str, Any]) -> list[str]:
    stages = raw.get("stages", {})
    if arm != "collapse3c":
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
    if len(rows) != 2400:
        raise ValueError(f"expected 2400 E2 atom rows, found {len(rows)}")
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
    return {
        "candidate_rows_n": len(candidate_rows),
        "multi_provenance_candidates_n": sum(
            len(set(x.get("recall_provenance", []))) > 1 for x in candidate_rows
        ),
        "with_support_fact_ids_n": sum(bool(x.get("support_fact_ids")) for x in candidate_rows),
        "with_support_spans_n": sum(bool(x.get("support_spans")) for x in candidate_rows),
        "with_against_spans_n": sum(bool(x.get("contradict_spans")) for x in candidate_rows),
        "with_against_fact_ids_n": sum(bool(x.get("against_fact_ids")) for x in candidate_rows),
    }


def build(repo: Path, commit: str, replay_path: Path) -> dict:
    trajectories, verification = _load_trajectories(repo, commit)
    endpoints = _load_endpoints(replay_path)
    if set(trajectories) != set(endpoints):
        raise ValueError("trajectory and E2 atom keys do not match")

    cases = sorted({case_key for case_key, _arm in trajectories})
    arm_records = {
        arm: [trajectories[(case_key, arm)] for case_key in cases] for arm in ARMS
    }
    per_arm = {}
    unique_correct = Counter()
    minority_risk = Counter()
    unique_label_in_any_wrong_pool = 0
    unique_label_in_both_wrong_pools = 0
    complete_hist = Counter()
    agreement_hist = Counter()
    oracle_complete = 0
    oracle_partial_or_complete = 0
    by_family: dict[str, dict[str, Any]] = {
        family: {
            "cases_n": 0,
            "complete_hist": Counter(),
            "per_arm_complete": Counter(),
            "unique_correct": Counter(),
            "wrong_pair_same_cluster": 0,
            "unique_label_in_any_wrong_pool": 0,
            "unique_label_in_both_wrong_pools": 0,
            "oracle_complete": 0,
        }
        for family in ("DA", "MCR")
    }

    for case_key in cases:
        family = "DA" if case_key.startswith("DA_") else "MCR"
        family_stats = by_family[family]
        family_stats["cases_n"] += 1
        rows = {arm: endpoints[(case_key, arm)] for arm in ARMS}
        recs = {arm: trajectories[(case_key, arm)] for arm in ARMS}
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

        champions = [recs[arm]["champion_norm"] for arm in ARMS]
        distinct = len(set(champions))
        agreement_hist[{1: "all_exact_agree", 2: "two_exact_agree", 3: "all_exact_different"}[distinct]] += 1

        if len(complete_arms) == 1:
            correct_arm = complete_arms[0]
            unique_correct[correct_arm] += 1
            family_stats["unique_correct"][correct_arm] += 1
            wrong_arms = [arm for arm in ARMS if arm != correct_arm]
            wrong_same_cluster = (
                rows[wrong_arms[0]]["output_cluster_id"]
                == rows[wrong_arms[1]]["output_cluster_id"]
            )
            if wrong_same_cluster:
                minority_risk[correct_arm] += 1
                family_stats["wrong_pair_same_cluster"] += 1
            correct_label = recs[correct_arm]["champion_norm"]
            pool_presence = {
                arm: correct_label in {_norm(x) for x in recs[arm]["candidates"]}
                for arm in wrong_arms
            }
            in_any_wrong_pool = any(pool_presence.values())
            in_both_wrong_pools = all(pool_presence.values())
            unique_label_in_any_wrong_pool += in_any_wrong_pool
            unique_label_in_both_wrong_pools += in_both_wrong_pools
            family_stats["unique_label_in_any_wrong_pool"] += in_any_wrong_pool
            family_stats["unique_label_in_both_wrong_pools"] += in_both_wrong_pools

    for arm, records in arm_records.items():
        ep = [endpoints[(case_key, arm)] for case_key in cases]
        per_arm[arm] = {
            "cases_n": len(records),
            "clinical_complete_n": sum(bool(row["clinical_complete"]) for row in ep),
            "compatible_partial_n": sum(bool(row["partial"]) for row in ep),
            "complete_or_partial_n": sum(
                bool(row["clinical_complete"] or row["partial"]) for row in ep
            ),
            "unique_correct_atom_n": unique_correct[arm],
            "wrong_consensus_suppression_risk_n": minority_risk[arm],
            "mean_primary_candidates": _mean(len(rec["candidates"]) for rec in records),
            "mean_frontier_candidates": _mean(len(rec["frontier"]) for rec in records),
            "mean_llm_calls": _mean(rec["llm_calls"] for rec in records),
            "channel_structure": _candidate_channel_summary(arm, records),
        }

    pairwise = {}
    arm_names = list(ARMS)
    for i, left in enumerate(arm_names):
        for right in arm_names[i + 1 :]:
            stats = Counter()
            jaccards = []
            union_sizes = []
            intersection_sizes = []
            for case_key in cases:
                lrec, rrec = trajectories[(case_key, left)], trajectories[(case_key, right)]
                lrow, rrow = endpoints[(case_key, left)], endpoints[(case_key, right)]
                lset = {_norm(x) for x in lrec["candidates"] if _norm(x)}
                rset = {_norm(x) for x in rrec["candidates"] if _norm(x)}
                stats["exact_champion_agreement_n"] += lrec["champion_norm"] == rrec["champion_norm"]
                stats["left_champion_in_right_primary_pool_n"] += lrec["champion_norm"] in rset
                stats["right_champion_in_left_primary_pool_n"] += rrec["champion_norm"] in lset
                stats["both_complete_n"] += bool(lrow["clinical_complete"] and rrow["clinical_complete"])
                stats["left_only_complete_n"] += bool(lrow["clinical_complete"] and not rrow["clinical_complete"])
                stats["right_only_complete_n"] += bool(rrow["clinical_complete"] and not lrow["clinical_complete"])
                stats["neither_complete_n"] += bool(not lrow["clinical_complete"] and not rrow["clinical_complete"])
                jaccards.append(_jaccard(lset, rset))
                union_sizes.append(len(lset | rset))
                intersection_sizes.append(len(lset & rset))
            pairwise[f"{left}__{right}"] = {
                **dict(stats),
                "mean_primary_pool_jaccard": _mean(jaccards),
                "mean_primary_pool_union_n": _mean(union_sizes),
                "mean_primary_pool_intersection_n": _mean(intersection_sizes),
            }

    best_single = max(value["clinical_complete_n"] for value in per_arm.values())
    by_family_out = {}
    for family, stats in by_family.items():
        family_best = max(stats["per_arm_complete"].values(), default=0)
        by_family_out[family] = {
            "cases_n": stats["cases_n"],
            "per_arm_clinical_complete_n": {
                arm: stats["per_arm_complete"][arm] for arm in ARMS
            },
            "clinical_complete_atom_count": {
                str(k): stats["complete_hist"][k] for k in range(4)
            },
            "oracle_any_complete_n": stats["oracle_complete"],
            "best_single_complete_n": family_best,
            "oracle_minus_best_single_n": stats["oracle_complete"] - family_best,
            "unique_correct_atom_n": {
                arm: stats["unique_correct"][arm] for arm in ARMS
            },
            "two_wrong_atoms_same_output_cluster_n": stats["wrong_pair_same_cluster"],
            "unique_correct_with_label_in_any_wrong_pool_n": stats[
                "unique_label_in_any_wrong_pool"
            ],
            "unique_correct_with_label_in_both_wrong_pools_n": stats[
                "unique_label_in_both_wrong_pools"
            ],
        }
    return {
        "schema_version": "mas-single-agent-atom-census-v2-public-aggregate",
        "scope": "Offline observational census; no model/API calls and no new clinical adjudication.",
        "publication_contract": {
            "case_level_records_included": False,
            "case_level_diagnoses_included": False,
            "case_level_predictions_included": False,
            "reason": "Public artifact contains aggregate mechanism counts only; exact values remain reproducible from the frozen source tree and script.",
        },
        "interpretation_contract": [
            "The three-arm oracle union is an upper-bound complementarity diagnostic, not an achievable MAS score.",
            "Root labels adjudicate served champions, not every candidate in each registry.",
            "Cross-atom candidate presence uses normalized primary labels only; it is not a clinical synonym or ontology matcher.",
            "Two wrong atoms sharing an E2 output cluster marks majority-suppression risk, not proof that a particular aggregator would vote that way.",
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
        "by_benchmark_family": by_family_out,
        "triad": {
            "exact_champion_agreement": dict(agreement_hist),
            "clinical_complete_atom_count": {str(k): complete_hist[k] for k in range(4)},
            "oracle_any_complete_n": oracle_complete,
            "best_single_complete_n": best_single,
            "oracle_minus_best_single_n": oracle_complete - best_single,
            "oracle_any_complete_or_partial_n": oracle_partial_or_complete,
            "unique_correct_atom_n": dict(unique_correct),
            "wrong_consensus_suppression_risk_n": sum(minority_risk.values()),
            "wrong_consensus_suppression_risk_by_correct_atom": dict(minority_risk),
            "unique_correct_with_label_in_any_wrong_pool_n": unique_label_in_any_wrong_pool,
            "unique_correct_with_label_in_both_wrong_pools_n": unique_label_in_both_wrong_pools,
        },
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
