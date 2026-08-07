#!/usr/bin/env python3
"""Smoke / full eval for TopKCalibration + offline AdaptiveMergeSiblings
+ AdaptiveSubdivideUnderL2 + AdaptiveDeepenOrMerge.

Does not re-run joint. Rematches existing mapper option_maps against new leaf
orders via answer_projection_mapper._rank_and_expand.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

import baseline_common as bc  # noqa: E402
import topk_calibration as calib  # noqa: E402
import adaptive_merge_siblings as merge  # noqa: E402
import adaptive_subdivide_under_l2 as subdivide  # noqa: E402
import adaptive_deepen_or_merge as deepen  # noqa: E402
import merge_calib_compat as compat  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import _rank_and_expand  # noqa: E402

PILOT_DIR = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1"
REMAIN_DIR = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate"
OUT_DIR = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_calibration_v1"
GRANULARITY_OUT_DIR = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_granularity_v1"
ANALYSIS = ROOT / "analysis/at1_gap_v1"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"

ARMS = (
    "ours",
    "support_rerank",
    "pair",
    "both",
    "both_l1fallback",
    "merge",
    "both_merge",
)

GRANULARITY_ARMS = (
    "ours",
    "both_l1fallback",
    "merge",
    "both_merge",
    "subdivide",
    "subdivide_calib",
    "deepen",
    "compat_parallel",
    "compat_serial_safe",
)

COMPAT_ARMS = (
    "ours",
    "both_l1fallback",
    "merge",
    "both_merge",
    "compat_parallel",
    "compat_serial_safe",
)

C1_ARMS = (
    "ours",                       # AB05
    "merge",                      # AB07
    "both_l1fallback",            # AB08
    "compat_serial_safe",         # AB09
    "compat_parallel",            # main recheck
    "compat_random_route",        # AB10
    "concept_id_merge",           # AB11
    "compat_parallel_no_l1_prior",  # AB20
)

C1_OUT_DIR = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_c1_v1"
RANDOM_ROUTE_SEED = 20260727


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _findings_for_case(fixture: Mapping[str, Any], case_id: str) -> list[dict]:
    for row in fixture.get("cases") or ():
        if str(row.get("case_id")) == str(case_id):
            return list(row.get("full_findings") or ())
    return []


def _vignette(case_meta: Mapping[str, Any], case_result: Mapping[str, Any]) -> str:
    text = str(case_meta.get("case_text") or case_result.get("case_text") or "")
    if "\nOptions:" in text:
        text = text.split("\nOptions:", 1)[0]
    return text.strip()


def _gold_leaf_ids(mapper_row: Mapping[str, Any]) -> list[str]:
    letter = str(mapper_row.get("gold_letter") or "").upper()
    om = ((mapper_row.get("projection") or {}).get("option_maps") or {}).get(letter) or {}
    ids = list(om.get("matched_leaf_ids") or om.get("clone_leaf_ids") or ())
    return [str(x) for x in ids if str(x).strip()]


def rematch_option_metrics(
    *,
    mapper_row: Mapping[str, Any],
    ordered_ids: Sequence[str],
    ranking_labels: Sequence[Mapping[str, Any]],
    gold_hit_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Recompute option ranks with new joint order; leaf set unchanged."""
    label_by_id = {
        str(r.get("id")): str(r.get("label") or "")
        for r in ranking_labels
        if r.get("id")
    }
    parent_by_id = {
        str(r.get("id")): str(r.get("parent") or "")
        for r in ranking_labels
        if r.get("id")
    }
    # include all labels that appear in maps even if not in ordered_ids
    all_ids = list(ordered_ids)
    for letter, mapped in ((mapper_row.get("projection") or {}).get("option_maps") or {}).items():
        for lid in (mapped.get("matched_leaf_ids") or mapped.get("clone_leaf_ids") or ()):
            s = str(lid)
            if s not in all_ids:
                all_ids.append(s)

    rank_pos = {lid: i for i, lid in enumerate(ordered_ids, start=1)}
    leaves = []
    for lid in all_ids:
        leaves.append({
            "leaf_id": lid,
            "leaf_label": label_by_id.get(lid, lid),
            "parent_id": parent_by_id.get(lid, ""),
            "parent_label": "",
            "joint_rank": rank_pos.get(lid),  # None if outside calibrated order
            "posterior": 0.0,
        })

    option_maps = (mapper_row.get("projection") or {}).get("option_maps") or {}
    # Prefer already-expanded clone_leaf_ids so rematch matches official mapper
    # without re-running resolver clone detection.
    mappings = {}
    for k, v in option_maps.items():
        expanded_ids = list(v.get("clone_leaf_ids") or v.get("matched_leaf_ids") or ())
        mappings[str(k).upper()] = {
            "matched_leaf_ids": expanded_ids,
            "relation_type": v.get("relation_type"),
        }
    clone_groups = [[lid] for lid in all_ids]
    expanded, ordered_letters = _rank_and_expand(
        mappings=mappings,
        leaves=leaves,
        clone_groups=clone_groups,
    )
    gold_letter = str(mapper_row.get("gold_letter") or "").upper()
    gold = expanded.get(gold_letter) or {}
    opt_rank = gold.get("option_rank")
    best_rank = gold.get("best_rank")

    # optional: treat synonym-cluster gold hits
    if gold_hit_ids is not None and best_rank is None:
        hit = set(str(x) for x in gold_hit_ids)
        for i, lid in enumerate(ordered_ids, start=1):
            if lid in hit:
                best_rank = i
                break
        if best_rank is not None:
            # recompute dense option_rank vs other options' best_rank
            others = [
                int(expanded[L]["best_rank"])
                for L in expanded
                if L != gold_letter and expanded[L].get("best_rank") is not None
            ]
            better = sum(1 for r in others if r < best_rank)
            opt_rank = better + 1

    if opt_rank is None or best_rank is None:
        return {
            "option_top1": False,
            "option_top2": False,
            "option_rr": 0.0,
            "option_rank": opt_rank,
            "best_rank": best_rank,
        }
    rr = 1.0 / int(opt_rank)
    return {
        "option_top1": int(opt_rank) <= 1,
        "option_top2": int(opt_rank) <= 2,
        "option_rr": rr,
        "option_rank": int(opt_rank),
        "best_rank": best_rank,
    }


def load_cohort(cohort: str) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    specs = []
    if cohort in {"pilot24", "all100"}:
        specs.append(("pilot24", PILOT_DIR))
    if cohort in {"remain76", "all100"}:
        specs.append(("remain76", REMAIN_DIR))

    cases_meta: dict[str, Any] = {}
    for path in (
        ROOT / "logs/diagnosisarena_d2_m01_v1/normalized_cases.json",
        PILOT_DIR / "normalized_cases.json",
        REMAIN_DIR / "normalized_cases.json",
    ):
        if path.is_file():
            doc = _load_json(path)
            for c in doc.get("cases") or ():
                cases_meta[str(c["id"])] = c

    for name, base in specs:
        man = _load_json(base / "stage_manifest.json")
        ids = [str(x) for x in (man.get("case_ids") or [])]
        if not ids:
            ids = [p.stem for p in sorted((base / "case_results").glob("*.json"))]
        fixture = _load_json(base / "finding_fixture_v1.json")
        for cid in ids:
            case = _load_json(base / "case_results" / f"{cid}.json")
            mapper = _load_json(base / "mapper" / "projections" / f"{cid}.json")
            packs.append({
                "case_id": cid,
                "cohort": name,
                "case": case,
                "mapper": mapper,
                "meta": cases_meta.get(cid) or {},
                "findings": _findings_for_case(fixture, cid),
            })
    return packs


def load_strata() -> dict[str, set[str]]:
    sets = _load_json(ANALYSIS / "case_sets.json")
    strata = {
        "set_a": set(sets.get("set_a_ours_at2_miss_at1") or ()),
        "fine_auto": set(sets.get("fine_candidates_in_A") or ()),
        "coarse_auto": set(sets.get("coarse_candidates_in_A") or ()),
    }
    coarse_pass: set[str] = set()
    fine_primary: set[str] = set()
    pure_rank: set[str] = set()
    audit_path = ANALYSIS / "granularity_audit_sheet.jsonl"
    if audit_path.is_file():
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cid = str(row.get("case_id"))
            v = row.get("verdict")
            if v == "coarse_leaf_multi_option":
                coarse_pass.add(cid)
            elif v == "fine_synonym_crowd":
                fine_primary.add(cid)
            elif v == "ranking_failure_rank2":
                pure_rank.add(cid)
    strata["coarse_agent_pass"] = coarse_pass
    strata["fine_primary"] = fine_primary
    strata["pure_ranking"] = pure_rank
    return strata


def _options_for_pack(pack: Mapping[str, Any]) -> dict[str, str]:
    meta = pack.get("meta") or {}
    case = pack.get("case") or {}
    text = str(meta.get("case_text") or case.get("case_text") or "")
    opts = subdivide.parse_options_from_case_text(text)
    if opts:
        return opts
    # fallback: option texts from mapper if present
    mapper = pack.get("mapper") or {}
    om = (mapper.get("projection") or {}).get("option_maps") or {}
    out: dict[str, str] = {}
    for letter, mapped in om.items():
        t = str(mapped.get("option_text") or mapped.get("option") or "").strip()
        if t:
            out[str(letter).upper()] = t
    return out


def run_arm_on_pack(
    pack: Mapping[str, Any],
    arm: str,
    *,
    cache: Any,
    dry_run: bool,
    k: int,
    alpha: float,
    beta: float,
    gamma: float,
    tau: float,
    use_gold_g2: bool = True,
    force_merge: Optional[bool] = None,
) -> dict[str, Any]:
    case = pack["case"]
    mapper = pack["mapper"]
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    gold_leaves = _gold_leaf_ids(mapper) if use_gold_g2 else []
    vignette = _vignette(pack["meta"], case)
    findings = pack["findings"]
    options = _options_for_pack(pack)
    gold_letter = str(mapper.get("gold_letter") or "").upper()
    om = (mapper.get("projection") or {}).get("option_maps") or {}

    gran_arms = {"subdivide", "subdivide_calib", "deepen"}
    compat_arms = {
        "compat_parallel",
        "compat_serial_safe",
        "compat_random_route",
        "compat_parallel_no_l1_prior",
        "concept_id_merge",
    }
    use_merge = arm in {"merge", "both_merge"}
    calib_arm = {
        "ours": "ours",
        "support_rerank": "support_rerank",
        "pair": "pair",
        "both": "both",
        "both_l1fallback": "both_l1fallback",
        "merge": "ours",
        "both_merge": "both_l1fallback",  # fair serial stack (was incorrectly "both")
        "subdivide": "ours",
        "subdivide_calib": "both_l1fallback",
        "deepen": "both_l1fallback",
        "compat_parallel": "ours",  # handled separately
        "compat_serial_safe": "ours",
        "compat_random_route": "ours",
        "compat_parallel_no_l1_prior": "ours",
        "concept_id_merge": "ours",
    }.get(arm)
    if calib_arm is None:
        raise ValueError(f"unknown arm: {arm}")

    merge_info = None
    route_meta: dict[str, Any] = {}
    work_labels = labels
    work_mapper = mapper
    gold_for_guard = list(gold_leaves)
    result: dict[str, Any]

    if arm in compat_arms:
        if arm == "compat_parallel":
            routed = compat.run_compat_parallel(
                case=case,
                ranking_labels=labels,
                vignette=vignette,
                findings=findings,
                option_maps=om,
                gold_leaf_ids=gold_for_guard,
                cache=cache,
                dry_run=dry_run,
                k=k,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                tau=tau,
            )
        elif arm == "compat_serial_safe":
            routed = compat.run_compat_serial_safe(
                case=case,
                ranking_labels=labels,
                vignette=vignette,
                findings=findings,
                option_maps=om,
                gold_leaf_ids=gold_for_guard,
                cache=cache,
                dry_run=dry_run,
                k=k,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                tau=tau,
            )
        elif arm == "compat_random_route":
            if force_merge is None:
                raise ValueError("compat_random_route requires force_merge mask")
            routed = compat.run_compat_random_route(
                case=case,
                ranking_labels=labels,
                vignette=vignette,
                findings=findings,
                option_maps=om,
                gold_leaf_ids=gold_for_guard,
                cache=cache,
                dry_run=dry_run,
                k=k,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                tau=tau,
                force_merge=bool(force_merge),
            )
        elif arm == "compat_parallel_no_l1_prior":
            routed = compat.run_compat_parallel_no_l1_prior(
                case=case,
                ranking_labels=labels,
                vignette=vignette,
                findings=findings,
                option_maps=om,
                gold_leaf_ids=gold_for_guard,
                cache=cache,
                dry_run=dry_run,
                k=k,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                tau=tau,
            )
        else:  # concept_id_merge
            routed = compat.run_concept_id_merge(
                case=case,
                ranking_labels=labels,
                vignette=vignette,
                findings=findings,
                option_maps=om,
                gold_leaf_ids=gold_for_guard,
                cache=cache,
                dry_run=dry_run,
                k=k,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                tau=tau,
            )
        work_labels = list(routed.get("ranking_labels") or labels)
        ordered = list(routed.get("ordered_ids") or ())
        merge_info = routed.get("merge_info")
        maps = routed.get("option_maps") or om
        work_mapper = {
            **mapper,
            "projection": {
                **(mapper.get("projection") or {}),
                "option_maps": maps,
            },
        }
        calib_meta = routed.get("calib") or {}
        n_clusters = (merge_info or {}).get("n_clusters")
        n_leaves = (merge_info or {}).get("n_leaves")
        pi_topk = None
        if merge_info and ordered:
            m2r = merge_info.get("member_to_rep") or {}
            reps = {m2r.get(str(x), str(x)) for x in ordered[:k]}
            pi_topk = len(reps)
        elif ordered:
            pi_topk = len(set(str(x) for x in ordered[:k]))
        route_meta = {
            "path": routed.get("branch") or routed.get("mode") or arm,
            "compat_mode": routed.get("mode"),
            "gate_triggered": (routed.get("gate") or {}).get("triggered"),
            "gate_empirical": routed.get("gate_empirical"),
            "gate_random": routed.get("gate_random"),
            "concept_key_coverage": routed.get("concept_key_coverage"),
            "n_clusters": n_clusters,
            "n_leaves": n_leaves,
            "pi_topk": pi_topk,
            "n_synthetic": None,
            "subdivided_parents": "",
            "merge_top1_repaired": calib_meta.get("merge_top1_repaired"),
        }
        result = {
            "reverted": bool(calib_meta.get("reverted")),
            "swapped": bool(calib_meta.get("swapped")),
            "pool_pre": calib_meta.get("pool_pre") or (),
            "pool_post": calib_meta.get("pool_post") or ordered[:k],
        }
        metrics = rematch_option_metrics(
            mapper_row=work_mapper,
            ordered_ids=ordered,
            ranking_labels=work_labels,
        )
    elif arm in gran_arms:
        if arm == "subdivide":
            route = deepen.route_case(
                labels,
                option_maps=om,
                options=options,
                gold_letter=gold_letter,
                vignette=vignette,
                cache=cache,
                dry_run=dry_run,
                top_k=k,
                force_path="subdivide",
            )
        elif arm == "subdivide_calib":
            route = deepen.route_case(
                labels,
                option_maps=om,
                options=options,
                gold_letter=gold_letter,
                vignette=vignette,
                cache=cache,
                dry_run=dry_run,
                top_k=k,
                force_path="subdivide",
            )
        else:  # deepen
            route = deepen.route_case(
                labels,
                option_maps=om,
                options=options,
                gold_letter=gold_letter,
                vignette=vignette,
                cache=cache,
                dry_run=dry_run,
                top_k=k,
                force_path="deepen",
            )
        route_meta = {
            "path": route.get("path"),
            "forbids_support_only": route.get("forbids_support_only"),
            "n_synthetic": (route.get("subdivide") or {}).get("n_synthetic"),
            "subdivided_parents": ",".join(
                (route.get("subdivide") or {}).get("subdivided_parents") or ()
            ),
        }
        merge_info = route.get("merge_info")
        work_labels = list(route["ranking_labels"])
        if route.get("option_maps"):
            work_mapper = {
                **mapper,
                "projection": {
                    **(mapper.get("projection") or {}),
                    "option_maps": route["option_maps"],
                },
            }
        # Remap gold leaves through letter_to_l3 when gold G2 enabled
        letter_to_l3 = (route.get("subdivide") or {}).get("letter_to_l3") or {}
        if use_gold_g2 and gold_letter and gold_letter in letter_to_l3:
            gold_for_guard = [letter_to_l3[gold_letter]]
        elif use_gold_g2 and merge_info:
            gold_for_guard = [
                merge_info["member_to_rep"].get(g, g) for g in gold_leaves
            ]
        case_for_calib = {
            **case,
            "l2": {
                **(case.get("l2") or {}),
                "final_ranking_labels": work_labels,
                "final_ranking_ids": [str(r["id"]) for r in work_labels],
            },
        }
        result = calib.calibrate_case(
            case=case_for_calib,
            vignette=vignette,
            findings=findings,
            gold_leaf_ids=gold_for_guard,
            arm=calib_arm,
            cache=cache,
            k=k,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            tau=tau,
            dry_run=dry_run,
        )
        ordered = result["ordered_ids"]
        metrics = rematch_option_metrics(
            mapper_row=work_mapper,
            ordered_ids=ordered,
            ranking_labels=work_labels,
        )
    elif use_merge:
        merge_info = merge.merge_ranking_ids(labels)
        # rewrite labels to representatives for calibration pool
        rep_labels = []
        for i, rep in enumerate(merge_info["representative_order"], start=1):
            # find original row
            src = next(
                (r for r in labels if str(r.get("id")) == rep),
                {"id": rep, "label": rep, "parent": ""},
            )
            rep_labels.append({
                "id": rep,
                "label": src.get("label"),
                "parent": src.get("parent"),
                "rank": i,
            })
        # synthetic case with merged ranking for calib
        case_for_calib = {
            **case,
            "l2": {
                **(case.get("l2") or {}),
                "final_ranking_labels": rep_labels,
                "final_ranking_ids": list(merge_info["representative_order"]),
            },
        }
        gold_for_guard = (
            [merge_info["member_to_rep"].get(g, g) for g in gold_leaves]
            if use_gold_g2
            else []
        )
        result = calib.calibrate_case(
            case=case_for_calib,
            vignette=vignette,
            findings=findings,
            gold_leaf_ids=gold_for_guard,
            arm=calib_arm,
            cache=cache,
            k=k,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            tau=tau,
            dry_run=dry_run,
        )
        ordered = result["ordered_ids"]
        # rebuild option maps projected to reps
        proj_maps = {}
        for letter, mapped in om.items():
            lids = [
                merge_info["member_to_rep"].get(str(x), str(x))
                for x in (mapped.get("matched_leaf_ids") or mapped.get("clone_leaf_ids") or ())
            ]
            proj_maps[letter] = {
                **mapped,
                "matched_leaf_ids": sorted(set(lids)),
                "clone_leaf_ids": sorted(set(lids)),
            }
        mapper_proj = {
            **mapper,
            "projection": {**(mapper.get("projection") or {}), "option_maps": proj_maps},
        }
        metrics = rematch_option_metrics(
            mapper_row=mapper_proj,
            ordered_ids=ordered,
            ranking_labels=rep_labels,
        )
    else:
        result = calib.calibrate_case(
            case=case,
            vignette=vignette,
            findings=findings,
            gold_leaf_ids=gold_leaves,
            arm=calib_arm,
            cache=cache,
            k=k,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            tau=tau,
            dry_run=dry_run,
        )
        ordered = result["ordered_ids"]
        metrics = rematch_option_metrics(
            mapper_row=mapper,
            ordered_ids=ordered,
            ranking_labels=labels,
        )

    official = {
        "option_top1": bool(mapper.get("option_top1")),
        "option_top2": bool(mapper.get("option_top2")),
        "option_rr": float(mapper.get("option_rr") or 0.0),
    }
    row = {
        "case_id": pack["case_id"],
        "cohort": pack["cohort"],
        "arm": arm,
        "opt1": int(metrics["option_top1"]),
        "opt2": int(metrics["option_top2"]),
        "rr": float(metrics["option_rr"]),
        "option_rank": metrics.get("option_rank"),
        "best_rank": metrics.get("best_rank"),
        "official_opt1": int(official["option_top1"]),
        "official_opt2": int(official["option_top2"]),
        "official_rr": official["option_rr"],
        "reverted": int(bool(result.get("reverted"))),
        "swapped": int(bool(result.get("swapped"))),
        "n_merge_clusters": (merge_info or {}).get("n_clusters"),
        "route_path": route_meta.get("path") or "",
        "n_synthetic": route_meta.get("n_synthetic"),
        "subdivided_parents": route_meta.get("subdivided_parents") or "",
        "gate_triggered": route_meta.get("gate_triggered"),
        "gate_empirical": route_meta.get("gate_empirical"),
        "gate_random": route_meta.get("gate_random"),
        "concept_key_coverage": route_meta.get("concept_key_coverage"),
        "pi_topk": route_meta.get("pi_topk"),
        "pool_pre": ",".join(result.get("pool_pre") or ()),
        "pool_post": ",".join(result.get("pool_post") or ()),
    }
    return row


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    return {
        "n": len(rows),
        "opt1": round(sum(int(r["opt1"]) for r in rows) / n, 4),
        "opt2": round(sum(int(r["opt2"]) for r in rows) / n, 4),
        "mrr": round(sum(float(r["rr"]) for r in rows) / n, 4),
        "reverted": sum(int(r["reverted"]) for r in rows),
        "swapped": sum(int(r["swapped"]) for r in rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", choices=["pilot24", "remain76", "all100"], default="pilot24")
    ap.add_argument("--arms", nargs="+", default=None)
    ap.add_argument(
        "--preset",
        choices=["calibration", "granularity", "compat", "c1"],
        default="calibration",
        help=(
            "calibration=TopK arms; granularity=merge/subdivide/deepen; "
            "compat=merge×calib parallel/serial_safe; "
            "c1=APHHM C1 projection ablations (AB05/07–11/20)"
        ),
    )
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=1.0)
    ap.add_argument("--gamma", type=float, default=0.5)
    ap.add_argument("--tau", type=float, default=0.5)
    ap.add_argument("--random-route-seed", type=int, default=RANDOM_ROUTE_SEED)
    ap.add_argument("--epsilon-at2", type=float, default=0.0,
                    help="Reject arm if @2 drops more than epsilon vs ours")
    ap.add_argument(
        "--no-gold-g2",
        action="store_true",
        help="Do not pass gold leaf ids into Top2 guard (harness-aligned)",
    )
    ap.add_argument(
        "--gold-g2",
        action="store_true",
        help="Force gold-aware G2 (oracle; for ablation only)",
    )
    args = ap.parse_args()

    if args.arms is None:
        if args.preset == "granularity":
            args.arms = list(GRANULARITY_ARMS)
        elif args.preset == "compat":
            args.arms = list(COMPAT_ARMS)
        elif args.preset == "c1":
            args.arms = list(C1_ARMS)
        else:
            args.arms = list(ARMS)
    if args.out_dir is None:
        if args.preset == "c1":
            args.out_dir = C1_OUT_DIR
        elif args.preset == "compat":
            args.out_dir = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1"
        elif args.preset == "granularity":
            args.out_dir = GRANULARITY_OUT_DIR
        else:
            args.out_dir = OUT_DIR
    # Default: calibration smoke uses gold G2 (legacy); granularity/compat/c1 = harness口径.
    if args.gold_g2:
        use_gold_g2 = True
    elif args.no_gold_g2:
        use_gold_g2 = False
    else:
        use_gold_g2 = args.preset == "calibration"

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "cache" / "topk_calibration_llm.json"
    cache = bc.SimpleCachedLLM(
        None if args.dry_run else __import__(
            "agentclinic_tree_dx.llm_client", fromlist=["RobustLLMClient"]
        ).RobustLLMClient(
            model=args.model,
            call_timeout=120,
            max_retries=4,
            timeout_retry_cap=2,
            temperature=0.0,
        ),
        cache_path,
        args.model,
    )

    packs = load_cohort(args.cohort)
    strata = load_strata()
    print(
        f"[{_utc()}] cohort={args.cohort} n={len(packs)} arms={args.arms} "
        f"dry_run={args.dry_run} use_gold_g2={use_gold_g2} preset={args.preset} "
        f"synonym_bind=OFF out_dir={out_dir}"
    )

    # AB10: build frequency-matched random gate mask (cohort-level)
    random_force_by_cid: dict[str, bool] = {}
    if "compat_random_route" in args.arms:
        empirical: list[bool] = []
        cids: list[str] = []
        for pack in packs:
            labels = list(
                ((pack["case"].get("l2") or {}).get("final_ranking_labels") or ())
            )
            gate = compat.fine_crowd_gate(labels)
            empirical.append(bool(gate.get("triggered")))
            cids.append(str(pack["case_id"]))
        random_mask = compat.assign_random_route_mask(
            empirical, seed=int(args.random_route_seed)
        )
        random_force_by_cid = {
            cid: bool(m) for cid, m in zip(cids, random_mask)
        }
        mask_doc = {
            "seed": int(args.random_route_seed),
            "n": len(cids),
            "n_empirical_true": int(sum(empirical)),
            "n_random_true": int(sum(random_mask)),
            "cases": [
                {
                    "case_id": cid,
                    "gate_empirical": bool(e),
                    "gate_random": bool(r),
                }
                for cid, e, r in zip(cids, empirical, random_mask)
            ],
        }
        (out_dir / f"random_route_mask_{args.cohort}.json").write_text(
            json.dumps(mask_doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"  AB10 mask: empirical_true={mask_doc['n_empirical_true']} "
            f"random_true={mask_doc['n_random_true']} seed={args.random_route_seed}"
        )

    all_rows: dict[str, list[dict[str, Any]]] = {a: [] for a in args.arms}
    t0 = time.time()

    def _job(pack, arm):
        fm = None
        if arm == "compat_random_route":
            fm = random_force_by_cid.get(str(pack["case_id"]))
        return run_arm_on_pack(
            pack, arm,
            cache=cache,
            dry_run=args.dry_run,
            k=args.k,
            alpha=args.alpha,
            beta=args.beta,
            gamma=args.gamma,
            tau=args.tau,
            use_gold_g2=use_gold_g2,
            force_merge=fm,
        )

    # Sequential per arm with thread pool over cases (shared cache is locked)
    for arm in args.arms:
        rows = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = {ex.submit(_job, pack, arm): pack["case_id"] for pack in packs}
            for fut in as_completed(futs):
                rows.append(fut.result())
        rows.sort(key=lambda r: (len(r["case_id"]), r["case_id"]))
        all_rows[arm] = rows
        path = out_dir / f"per_case_{arm}_{args.cohort}.tsv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  arm={arm} {summarize(rows)}")

    ours = summarize(all_rows.get("ours") or [])
    # sanity: ours rematch vs official
    if all_rows.get("ours"):
        mismatch = sum(
            1 for r in all_rows["ours"]
            if int(r["opt1"]) != int(r["official_opt1"])
            or int(r["opt2"]) != int(r["official_opt2"])
        )
    else:
        mismatch = None

    summaries = {}
    rejected = []
    for arm, rows in all_rows.items():
        s = summarize(rows)
        s["delta_opt1"] = round(s["opt1"] - ours["opt1"], 4) if ours["n"] else None
        s["delta_opt2"] = round(s["opt2"] - ours["opt2"], 4) if ours["n"] else None
        s["delta_mrr"] = round(s["mrr"] - ours["mrr"], 4) if ours["n"] else None
        # process metrics for C1
        gates = [r.get("gate_triggered") for r in rows if r.get("gate_triggered") is not None]
        if gates:
            s["gate_trigger_rate"] = round(sum(1 for g in gates if g) / len(gates), 4)
        pi_vals = [float(r["pi_topk"]) for r in rows if r.get("pi_topk") is not None]
        if pi_vals:
            s["mean_pi_topk"] = round(sum(pi_vals) / len(pi_vals), 4)
        cov = [
            float(r["concept_key_coverage"])
            for r in rows
            if r.get("concept_key_coverage") is not None
        ]
        if cov:
            s["mean_concept_key_coverage"] = round(sum(cov) / len(cov), 4)
        # stratified
        for name, ids in strata.items():
            sub = [r for r in rows if r["case_id"] in ids]
            if sub:
                s[f"strata_{name}"] = summarize(sub)
        drop = (ours["opt2"] - s["opt2"]) if ours["n"] else 0.0
        if arm != "ours" and drop > args.epsilon_at2 + 1e-12:
            s["status"] = "REJECTED"
            rejected.append(arm)
        else:
            s["status"] = "PASS"
        summaries[arm] = s

    payload = {
        "created_at": _utc(),
        "cohort": args.cohort,
        "preset": args.preset,
        "n": len(packs),
        "dry_run": args.dry_run,
        "use_gold_g2": use_gold_g2,
        "synonym_bind": False,
        "epsilon_at2": args.epsilon_at2,
        "random_route_seed": int(args.random_route_seed),
        "ours_rematch_vs_official_mismatch": mismatch,
        "elapsed_s": round(time.time() - t0, 2),
        "summaries": summaries,
        "rejected_arms": rejected,
    }
    (out_dir / f"summary_{args.cohort}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Guard violation log (G2 revert events)
    guard_path = out_dir / "guard_violations.jsonl"
    with guard_path.open("a", encoding="utf-8") as gf:
        for arm, rows in all_rows.items():
            for r in rows:
                if int(r.get("reverted") or 0) == 1:
                    gf.write(
                        json.dumps(
                            {
                                "cohort": args.cohort,
                                "arm": arm,
                                "case_id": r["case_id"],
                                "pool_pre": r.get("pool_pre"),
                                "pool_post": r.get("pool_post"),
                                "note": "G2 top2_set_guard reverted to pre-calibration Top-K order",
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

    # markdown summary
    lines = [
        f"# Calibration smoke summary ({args.cohort})",
        "",
        f"- created: {payload['created_at']}",
        f"- n={payload['n']} dry_run={args.dry_run} epsilon_at2={args.epsilon_at2}",
        f"- synonym_bind: OFF (main reporting standard)",
        f"- ours rematch vs official mismatches: {mismatch}",
        "",
        "| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status | reverted |",
        "|-----|---:|---:|----:|----:|----:|--------|---------:|",
    ]
    for arm in args.arms:
        s = summaries[arm]
        lines.append(
            f"| {arm} | {s['opt1']:.4f} | {s['opt2']:.4f} | {s['mrr']:.4f} | "
            f"{s.get('delta_opt1')} | {s.get('delta_opt2')} | {s['status']} | {s['reverted']} |"
        )
    lines.append("")
    (out_dir / f"summary_{args.cohort}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"rejected": rejected, "ours": ours, "mismatch": mismatch}, indent=2))


if __name__ == "__main__":
    main()
