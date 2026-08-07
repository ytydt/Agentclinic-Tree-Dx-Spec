#!/usr/bin/env python3
"""DiagnosisArena: downstream to Top-2 on frozen VP/tree/P5 (no mapper).

Stages merged freeze artifacts from stress_p5_compile_v2, then runs with
case-level concurrency (default 12):

  L1 BFS (p5_anti_anchor_direct + injected p5_headline) → F6 prefix
  → Config A L2 generation → A3-joint-primary ranking

Human @1/@2 adjudication is offline against case gold labels (no AnswerMapper).

Usage:
  PYTHONPATH=src:scripts/paper:scripts \\
    TREE_DX_DIRECT_POST_OUTPUT_CAP=8192 \\
    python3 -u scripts/paper/run_diagnosisarena_downstream_top2.py \\
      --workers 12
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import diagnosisarena_adapter as da  # noqa: E402
import diagnosisarena_l2_pipeline as l2pipe  # noqa: E402
import eval_branch_talp_composed as composed  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
import eval_l2_branch_generation_ab as l2_ab  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
import topk_calibration as topk_calib  # noqa: E402
import l1_family_calibration as l1_family_calib  # noqa: E402
import adaptive_deepen_or_merge as deepen_or_merge  # noqa: E402
import adaptive_subdivide_under_l2 as subdivide_l2  # noqa: E402
import merge_calib_compat as merge_calib_compat  # noqa: E402
import mapper_bind_repair as mapper_bind_repair  # noqa: E402
import targeted_l2_gapfill_overlay as targeted_gapfill  # noqa: E402
import c3_l1_axis  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    load_offline_resolver,
)
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    L1EvidenceBFSPipeline,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

DEFAULT_CALIBRATION_ARM = "both_l1fallback"
DEFAULT_GRANULARITY_MODE = "compat"
DEFAULT_L1_CALIB = "off"
DEFAULT_LEAF_INJECT_BIND_REPAIR = False
DEFAULT_TARGETED_L2_GAPFILL = False
DEFAULT_TARGETED_L2_GAPFILL_ARM = targeted_gapfill.DEFAULT_ARM

DEFAULT_CASES_JSON = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "normalized_cases.json"
)
DEFAULT_FREEZE = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "vignette_parser_probe_v3"
    / "vignette_parser_frozen_v3.json"
)
DEFAULT_STRESS_ROOT = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "stress_p5_compile_v2"
)
DEFAULT_OUT = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "downstream_top2_w12_v1"
)
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
TALP_SCRIPT = ROOT / "scripts" / "eval_talp_discrimination.py"
FIXED_L1_BUDGET = 6
DEFAULT_L2_LOCAL_EVIDENCE_BUDGET = 4
DEFAULT_L2_BETWEEN_EVIDENCE_BUDGET = 2
DEFAULT_L2_CANDIDATE_MAX = 6
DEFAULT_FORCE_EMIT = False
DEFAULT_FORCE_EMIT_MAX = 3
COHORTS = ("cohort_w06", "cohort_w12")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    da._atomic_json(path, payload)


def _rel_or_abs(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _collect_frozen_trees_and_p5(
    *,
    freeze_root: Path | None,
    stress_root: Path | None,
    freeze: Mapping[str, Any],
    tree_dir: Path,
    p5_audit_dir: Path,
) -> tuple[list[str], dict[str, list], str]:
    """Load trees+P5 from flat freeze_root or legacy cohort stress_root."""
    disc_audit: dict[str, list] = {}
    case_ids: list[str] = []
    source_note = ""

    if freeze_root is not None:
        root = Path(freeze_root).expanduser().resolve()
        src_trees = root / "shared_trees"
        arm_path = root / "p5_headline_frozen.json"
        if not src_trees.is_dir() or not arm_path.is_file():
            raise FileNotFoundError(
                "freeze-root requires shared_trees/ and p5_headline_frozen.json "
                "under %s" % root
            )
        arm = json.loads(arm_path.read_text(encoding="utf-8"))
        disc_audit = {
            str(cid): list(rules)
            for cid, rules in (arm.get("disc_audit") or {}).items()
        }
        for path in sorted(src_trees.glob("*.json")):
            if path.name == "summary.json":
                continue
            case_id = path.stem
            if case_id not in freeze:
                raise RuntimeError("VP freeze missing %s" % case_id)
            target = tree_dir / path.name
            if not target.exists() or target.read_bytes() != path.read_bytes():
                target.write_bytes(path.read_bytes())
            src_audit = root / "p5_audit" / path.name
            if src_audit.is_file():
                dest = p5_audit_dir / path.name
                if not dest.exists() or dest.read_bytes() != src_audit.read_bytes():
                    dest.write_bytes(src_audit.read_bytes())
            else:
                _atomic_json(p5_audit_dir / path.name, {
                    "case_id": case_id,
                    "stage": "p5",
                    "rules": disc_audit.get(case_id) or [],
                })
            case_ids.append(case_id)
        return case_ids, disc_audit, _rel_or_abs(root)

    stress = Path(stress_root).expanduser().resolve()
    for cohort in COHORTS:
        cohort_trees = stress / cohort / "shared_trees"
        cohort_arm = json.loads(
            (stress / cohort / "p5_headline_frozen.json").read_text(encoding="utf-8")
        )
        disc_audit.update({
            str(cid): list(rules)
            for cid, rules in (cohort_arm.get("disc_audit") or {}).items()
        })
        for path in sorted(cohort_trees.glob("*.json")):
            if path.name == "summary.json":
                continue
            case_id = path.stem
            if case_id not in freeze:
                raise RuntimeError("freeze missing %s" % case_id)
            target = tree_dir / path.name
            if not target.exists() or target.read_bytes() != path.read_bytes():
                target.write_bytes(path.read_bytes())
            _atomic_json(p5_audit_dir / ("%s.json" % case_id), {
                "case_id": case_id,
                "stage": "p5",
                "rules": disc_audit.get(case_id) or [],
            })
            case_ids.append(case_id)
    return case_ids, disc_audit, _rel_or_abs(stress)


def stage_assets(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    tree_dir = out / "shared_trees"
    p5_audit_dir = out / "p5_audit"
    tree_dir.mkdir(parents=True, exist_ok=True)
    p5_audit_dir.mkdir(parents=True, exist_ok=True)

    freeze_path = Path(args.vignette_freeze).expanduser().resolve()
    freeze = da.load_vignette_parser_freeze(freeze_path)
    freeze_root = getattr(args, "freeze_root", None)
    case_ids, disc_audit, source_note = _collect_frozen_trees_and_p5(
        freeze_root=Path(freeze_root) if freeze_root else None,
        stress_root=None if freeze_root else args.stress_root,
        freeze=freeze,
        tree_dir=tree_dir,
        p5_audit_dir=p5_audit_dir,
    )

    case_ids = sorted(set(case_ids), key=lambda x: (len(x), x))
    if getattr(args, "cases", None):
        wanted = {
            token.strip()
            for token in str(args.cases).split(",")
            if token.strip()
        }
        if wanted:
            missing = sorted(wanted - set(case_ids))
            if missing:
                raise RuntimeError("requested cases missing from freeze: %s" % missing)
            case_ids = [cid for cid in case_ids if cid in wanted]
            disc_audit = {cid: disc_audit[cid] for cid in case_ids if cid in disc_audit}

    arm_path = out / "p5_headline_frozen.json"
    _atomic_json(arm_path, {
        "summary": {
            "tag": "diagnosisarena_d2_p5_headline",
            "stage": "p5",
            "n_cases": len(disc_audit),
            "merged_from": source_note,
            "compiled_at": _utc_now(),
        },
        "disc_audit": disc_audit,
        "audit_summary": {},
        "case_normalized": {},
        "key_audit": {},
        "entry_audit": {},
        "rows": [],
    })

    # Finding fixture from VP freeze (same as M01 build-findings).
    cases_doc = json.loads(Path(args.cases_json).read_text(encoding="utf-8"))
    cases = [
        case for case in cases_doc.get("cases") or ()
        if str(case["id"]) in set(case_ids)
    ]
    cases.sort(key=lambda c: case_ids.index(str(c["id"])))
    _atomic_json(out / "normalized_cases.json", {
        **cases_doc,
        "cases": cases,
        "n_cases": len(cases),
        "subset_note": "staged freeze cases for downstream top2",
    })

    fixture_rows = []
    for case in cases:
        frozen = freeze[str(case["id"])]
        findings = da.findings_catalog_from_frozen_case(frozen)
        fixture_rows.append({
            "case_id": str(case["id"]),
            "full_findings": findings,
            "full_catalog_hash": stable_hash(findings),
            "filtered_fact_ids": [row["id"] for row in findings],
            "filter_runs": [],
            "source": "vignette_parser_freeze_v3",
        })
    fixture_path = out / "finding_fixture_v1.json"
    _atomic_json(fixture_path, {
        "asset_kind": "diagnosisarena_auto_finding_catalogs",
        "schema_version": 1,
        "created_at": _utc_now(),
        "evidence_source": "vignette_parser_freeze_v3",
        "cases": fixture_rows,
    })

    summary = {
        "phase": "stage",
        "n_cases": len(case_ids),
        "case_ids": case_ids,
        "tree_dir": str(tree_dir.relative_to(ROOT)),
        "p5_arm": str(arm_path.relative_to(ROOT)),
        "fixture": str(fixture_path.relative_to(ROOT)),
        "mean_p5_rules": (
            round(statistics.mean(len(v) for v in disc_audit.values()), 2)
            if disc_audit else None
        ),
        "mean_findings": (
            round(statistics.mean(len(r["full_findings"]) for r in fixture_rows), 2)
            if fixture_rows else None
        ),
    }
    _atomic_json(out / "stage_manifest.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def _apply_l1_posteriors(state, l1_rows: Sequence[Mapping[str, Any]]) -> None:
    by_id = {
        str(row["id"]): float(row["posterior"])
        for row in l1_rows
    }
    for branch_id, branch in state.branches.items():
        if int(getattr(branch, "level", 0) or 0) != 1:
            continue
        if branch_id in by_id:
            branch.posterior = by_id[branch_id]


def _ranking_labels(state, ranking_ids: Sequence[str]) -> list[dict[str, Any]]:
    rows = []
    for index, branch_id in enumerate(ranking_ids, start=1):
        branch = state.branches.get(str(branch_id))
        rows.append({
            "rank": index,
            "id": str(branch_id),
            "label": str(getattr(branch, "label", "") or ""),
            "parent": str(getattr(branch, "parent", "") or ""),
        })
    return rows


def _human_judge_row(
    *,
    gold: str,
    ranking_labels: Sequence[Mapping[str, Any]],
    resolver,
) -> dict[str, Any]:
    """Heuristic prefill for human adjudication (agent reviews afterward)."""
    def _hit(label: str) -> bool:
        return bool(l2pipe._label_match(label, gold, resolver))

    top1 = ranking_labels[0]["label"] if ranking_labels else ""
    top2 = ranking_labels[1]["label"] if len(ranking_labels) > 1 else ""
    at1 = _hit(top1) if top1 else False
    at2 = at1 or (_hit(top2) if top2 else False)
    return {
        "gold": gold,
        "top1_label": top1,
        "top2_label": top2,
        "at1": at1,
        "at2": at2,
        "judge": "agent_label_match_v1",
        "notes": "",
    }


def _run_one_case(payload: Mapping[str, Any]) -> dict[str, Any]:
    case = dict(payload["case"])
    case_id = str(case["id"])
    started = time.monotonic()
    out_path = Path(payload["out_path"])
    fingerprint = payload["fingerprint"]
    if out_path.is_file() and payload.get("resume"):
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if (
            existing.get("status") == "OK"
            and existing.get("run_fingerprint") == fingerprint
        ):
            return existing

    try:
        tree = json.loads(Path(payload["tree_path"]).read_text(encoding="utf-8"))
        axis_mode = str(payload.get("l1_axis_mode") or "adaptive").strip().lower()
        if axis_mode not in {"", "adaptive", "m00", "default"}:
            tree = c3_l1_axis.apply_l1_axis_to_tree_doc(
                tree,
                axis_mode,
                case_id=case_id,
                max_l1=int(payload.get("fixed_l1_budget") or FIXED_L1_BUDGET),
                keep_leaves=bool(payload.get("reuse_l2_leaves", False)),
            )
        state = composed._deserialize_state(tree["state"])
        state.case_id = case_id
        state.max_tree_depth = 2

        fixture_case = payload["fixture_case"]
        findings = list(fixture_case["full_findings"])
        facts = competition.auto_matrix._facts(findings)

        talp = bfs_eval._load_module(
            "da_down_talp_%s" % case_id.replace(".", "_"),
            TALP_SCRIPT,
        )
        frozen_arms = composed.FrozenOfflineArms(
            talp, {"p5_headline": Path(payload["p5_arm"])},
        )
        blocks = frozen_arms.blocks("p5_headline", case_id, facts)

        llm = RobustLLMClient(
            model=payload["model"],
            call_timeout=float(payload["call_timeout"]),
            max_retries=5,
            timeout_retry_cap=2,
            temperature=0.0,
        )
        cache_dir = Path(payload["cache_dir"])
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = bfs_eval.CachedLLM(
            llm, cache_dir / "bfs_llm_cache.json", payload["model"],
        )
        l1_preset = str(
            payload.get("l1_bfs_preset") or "p5_anti_anchor_direct"
        ).strip()
        inject_compiler = bool(payload.get("inject_compiler_rules", True))
        selector, rule_in, rule_out, _ = bfs_eval._runtime_functions(
            cached, l1_preset, talp,
        )
        # L1 evidence freeze prefix (default F6; OX locked budget uses 4).
        l1_budget = int(
            payload.get("fixed_l1_budget")
            or payload.get("l1_evidence_budget")
            or FIXED_L1_BUDGET
        )
        l1_budget = max(1, l1_budget)
        n_l1 = sum(
            1 for b in state.branches.values() if int(getattr(b, "level", 0) or 0) == 1
        )
        # C3 AB02 flat: single L1 pool — skip contrastive L1-BFS (needs ≥2 families).
        if axis_mode in {"flat", "no_l1"} or n_l1 < 2:
            final_state = copy.deepcopy(state)
            for branch in final_state.branches.values():
                if int(getattr(branch, "level", 0) or 0) == 1:
                    branch.prior = 1.0
                    branch.posterior = 1.0
            selected_prefix = list(facts)[:l1_budget]
            posteriors = [
                {
                    "id": branch.id,
                    "label": branch.label,
                    "posterior": float(branch.posterior or 1.0),
                }
                for branch in final_state.branches.values()
                if int(getattr(branch, "level", 0) or 0) == 1
            ]
            # Synthetic trajectory so prefix_snapshot(budget) works.
            traj = []
            for r in range(0, l1_budget + 1):
                traj.append({
                    "round": r,
                    "fact_id": (
                        selected_prefix[r - 1].id if r > 0 else None
                    ),
                    "posteriors": posteriors,
                })
            trace = {
                "selected_fact_ids": [f.id for f in selected_prefix],
                "stop_reason": "flat_single_l1_no_bfs",
                "posterior_trajectory": traj,
                "rounds": [],
                "selection_cycles": [],
                "l1_axis_mode": axis_mode or "flat",
            }
        else:
            final_state, trace = L1EvidenceBFSPipeline(
                preset=l1_preset,
                global_selector=selector,
                rule_in_allocator=rule_in,
                rule_out_allocator=rule_out,
                max_micro_rounds=30,
                facts_per_cycle=2,
                enforce_canonical_dedup=True,
            ).run(
                copy.deepcopy(state),
                case_context=str(case["case_text"]),
                facts=facts,
                compiler_master_blocks=blocks if inject_compiler else {},
                prior_mode="branch",
            )
        snapshot = competition.prefix_snapshot(trace, l1_budget)
        actual_round = int(snapshot["round"])
        selected_ids = list(trace.get("selected_fact_ids") or ())[:actual_round]
        fact_by_id = {str(fact.id): fact for fact in facts}
        selected_facts = []
        for fact_id in selected_ids:
            fact = fact_by_id[fact_id]
            selected_facts.append({
                "id": fact.id,
                "text": fact.text,
            })
        # Also keep fixture-shaped findings for joint.
        finding_by_text = {
            " ".join(str(row.get("text") or "").lower().split()): row
            for row in findings
        }
        between_budget = int(
            payload.get("l2_between_evidence_budget")
            or DEFAULT_L2_BETWEEN_EVIDENCE_BUDGET
        )
        f2_facts = []
        for row in selected_facts[: max(1, between_budget)]:
            key = " ".join(str(row["text"]).lower().split())
            matched = finding_by_text.get(key)
            f2_facts.append(matched or {
                "id": row["id"],
                "text": row["text"],
                "source_id": row["id"],
            })

        l1_rows = list(snapshot["posteriors"])
        l1_calib_arm = str(
            payload.get("l1_calib") or DEFAULT_L1_CALIB
        ).strip().lower()
        l1_calib_meta: dict[str, Any] = {
            "arm": l1_calib_arm,
            "enabled": False,
            "skipped_gate": False,
            "swapped": False,
        }
        if l1_calib_arm and l1_calib_arm not in {"off", "ours", "none", ""}:
            vignette_for_l1 = str(case.get("case_text") or "")
            if "\nOptions:" in vignette_for_l1:
                vignette_for_l1 = vignette_for_l1.split("\nOptions:", 1)[0].strip()
            l1_cache = bfs_eval.CachedLLM(
                llm,
                cache_dir / "l1_family_calib_llm_cache.json",
                payload["model"],
            )
            l1_cal = l1_family_calib.calibrate_l1_families(
                l1_rows,
                vignette_for_l1,
                findings,
                arm=l1_calib_arm,
                cache=l1_cache,
                dry_run=bool(payload.get("calibration_dry_run")),
            )
            l1_rows = list(l1_cal.get("ordered_rows") or l1_rows)
            l1_calib_meta = {
                "arm": l1_cal.get("arm"),
                "enabled": True,
                "skipped_gate": bool(l1_cal.get("skipped_gate")),
                "swapped": bool(l1_cal.get("swapped")),
                "meta": l1_cal.get("meta") or {},
            }
        elif l1_calib_arm in {"ours"}:
            l1_calib_meta = {
                "arm": "ours",
                "enabled": True,
                "skipped_gate": False,
                "swapped": False,
            }

        bfs_serialized = composed._serialize_state(final_state, {})
        # Overlay F6 posteriors onto the BFS state before Config A L2.
        f6_state = composed._deserialize_state(bfs_serialized)
        _apply_l1_posteriors(f6_state, l1_rows)
        f6_serialized = composed._serialize_state(f6_state, {})

        l2_cached = l2_ab.CachedModuleAdapter(
            bfs_eval.CachedLLM(
                llm, cache_dir / "l2_llm_cache.json", payload["model"],
            )
        )
        force_emit = bool(payload.get("l2_gap_force_emit_uncovered", DEFAULT_FORCE_EMIT))
        force_emit_max = int(
            payload.get("l2_gap_force_emit_max", DEFAULT_FORCE_EMIT_MAX) or 3
        )
        local_budget = int(
            payload.get("l2_local_evidence_budget", DEFAULT_L2_LOCAL_EVIDENCE_BUDGET)
            or DEFAULT_L2_LOCAL_EVIDENCE_BUDGET
        )
        cand_max = int(
            payload.get("l2_candidate_max_per_live_family", DEFAULT_L2_CANDIDATE_MAX)
            or DEFAULT_L2_CANDIDATE_MAX
        )
        tree_sem_dedupe = not bool(payload.get("no_tree_semantic_dedupe", False))
        if axis_mode in {"flat", "no_l1"}:
            # Preserve total leaf budget under a single L1 parent.
            cand_max = int(
                payload.get("l2_candidate_max_per_live_family", DEFAULT_L2_CANDIDATE_MAX)
                or DEFAULT_L2_CANDIDATE_MAX
            )
            flat_cap = c3_l1_axis.flat_l2_budget(
                fixed_l1_budget=int(payload.get("fixed_l1_budget") or FIXED_L1_BUDGET),
                per_family=cand_max,
            )
            # cand_max used later for posterior cap; lift for flat.
            payload = dict(payload)
            payload["l2_candidate_max_per_live_family"] = flat_cap
            cand_max = flat_cap
        l2_state, l2_gen = l2pipe.run_config_a_l2_generation(
            serialized_state=f6_serialized,
            cached_adapter=l2_cached,
            candidate_budget=24 if axis_mode not in {"flat", "no_l1"} else max(24, cand_max),
            snippet_budget=12,
            force_emit_uncovered=force_emit,
            force_emit_max=force_emit_max,
            tree_semantic_dedupe=tree_sem_dedupe,
        )
        l2_gen = dict(l2_gen)
        l2_gen["l1_axis_mode"] = axis_mode or "adaptive"
        l2_gen["tree_semantic_dedupe"] = tree_sem_dedupe
        # Opt-in research overlay: targeted L2 gapfill after Config A.
        gapfill_meta: dict[str, Any] = {"enabled": False}
        if bool(payload.get("targeted_l2_gapfill")):
            gapfill_arm = str(
                payload.get("targeted_l2_gapfill_arm")
                or DEFAULT_TARGETED_L2_GAPFILL_ARM
            )
            l2_state, gapfill_meta = targeted_gapfill.apply_targeted_l2_gapfill(
                l2_state=l2_state,
                cached_adapter=l2_cached,
                cache_dir=cache_dir / "targeted_gapfill",
                model=str(payload["model"]),
                arm=gapfill_arm,
                call_timeout=float(payload["call_timeout"]),
            )
        joint_payload = l2pipe.run_joint_primary(
            case_text=str(case["case_text"]),
            state=l2_state,
            findings=findings,
            f2_facts=f2_facts,
            cache=l2_cached.cached,
            local_evidence_budget=local_budget,
            between_evidence_budget=between_budget,
            scope_mode=str(payload.get("score_scope_mode") or "per_family"),
        )
        # Live posterior writeback: local annotator scores → leaf posteriors,
        # then per-family candidate cap (affects emitted-leaf pool order).
        pre_leaf_scores = {
            bid: {
                "posterior": float(getattr(b, "posterior", 0.0) or 0.0),
                "prior": float(getattr(b, "prior", 0.0) or 0.0),
                "label": str(getattr(b, "label", "") or ""),
                "parent_id": str(getattr(b, "parent", "") or ""),
            }
            for bid, b in l2_state.branches.items()
            if int(getattr(b, "level", 0) or 0) == 2
        }
        local_outputs = (
            (joint_payload.get("dynamic_assets") or {}).get("local_outputs") or {}
        )
        computed_map: dict[str, float] = {}
        for out in local_outputs.values():
            for p in (out.get("posteriors") or []):
                pid = str(p.get("id") or "")
                if pid:
                    computed_map[pid] = float(p.get("posterior") or 0.0)
        wb_mode = str(payload.get("writeback_mode") or "normal").strip().lower()
        posterior_meta = l2pipe.apply_live_posteriors_and_cap(
            l2_state,
            l1_rows=l1_rows,
            local_outputs=local_outputs,
            l2_candidate_max=cand_max,
            writeback_mode=wb_mode,
            shuffle_seed=int(payload.get("writeback_shuffle_seed") or 20260731),
        )
        leaf_score_fidelity = []
        for bid, pre in pre_leaf_scores.items():
            branch = l2_state.branches.get(bid)
            post = float(getattr(branch, "posterior", 0.0) or 0.0) if branch else 0.0
            computed = computed_map.get(bid)
            parent_id = pre["parent_id"]
            parent = l2_state.branches.get(parent_id)
            kids = list(getattr(parent, "children", None) or []) if parent else []
            capped_out = bool(kids) and bid not in {str(x) for x in kids}
            leaf_score_fidelity.append(
                {
                    "leaf_id": bid,
                    "label": pre["label"],
                    "parent_id": parent_id,
                    "pre_posterior": pre["posterior"],
                    "computed_posterior": computed,
                    "post_posterior": post,
                    "written_back": (
                        computed is not None
                        and abs(post - float(computed)) < 1e-9
                        and wb_mode == "normal"
                    ),
                    "capped_out": capped_out,
                }
            )
        posterior_meta = {
            **posterior_meta,
            "n_fidelity_leaves": len(leaf_score_fidelity),
            "fraction_score_changed": (
                sum(
                    1
                    for r in leaf_score_fidelity
                    if abs(float(r["post_posterior"]) - float(r["pre_posterior"])) > 1e-9
                )
                / max(1, len(leaf_score_fidelity))
            ),
        }
        tree_write_meta = {"written": False}
        if bool(payload.get("write_annotated_trees", True)):
            try:
                tree_out = Path(payload["tree_path"])
                tree_out.parent.mkdir(parents=True, exist_ok=True)
                serialized = composed._serialize_state(l2_state, {})
                doc = {
                    "state": serialized,
                    "live_reannotated": True,
                    "l1_evidence_budget": l1_budget,
                    "l2_local_evidence_budget": local_budget,
                    "l2_between_evidence_budget": between_budget,
                    "l2_candidate_max_per_live_family": cand_max,
                    "l2_gap_force_emit_uncovered": force_emit,
                    "posterior_writeback": posterior_meta,
                }
                tree_out.write_text(
                    json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                tree_write_meta = {"written": True, "path": str(tree_out)}
            except Exception as exc:  # noqa: BLE001
                tree_write_meta = {
                    "written": False,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
        ranking_ids = list(joint_payload.get("final_ranking") or ())
        ranking_labels = _ranking_labels(l2_state, ranking_ids)
        # Persist pre-compat joint BEFORE granularity/compat overwrites rankings.
        pre_compat_ids = list(ranking_ids)
        pre_compat_labels = [dict(r) for r in ranking_labels]

        vignette = str(case.get("case_text") or "")
        if "\nOptions:" in vignette:
            vignette_body = vignette.split("\nOptions:", 1)[0].strip()
        else:
            vignette_body = vignette.strip()

        # Granularity / merge×calib compat before (or instead of) TopKCalibration.
        granularity_mode = str(
            payload.get("granularity_mode") or DEFAULT_GRANULARITY_MODE
        ).strip().lower()
        granularity_meta: dict[str, Any] = {
            "mode": granularity_mode,
            "enabled": False,
            "path": "calibrate_only",
        }
        label_by_id = {
            str(r.get("id")): dict(r) for r in ranking_labels if r.get("id")
        }
        skip_followon_calib = False
        if granularity_mode == "compat":
            options = subdivide_l2.parse_options_from_case_text(
                str(case.get("case_text") or "")
            )
            gran_cache = bfs_eval.CachedLLM(
                llm,
                cache_dir / "granularity_llm_cache.json",
                payload["model"],
            )
            case_for_compat = {
                "l1": {"l1_posteriors": l1_rows},
                "l2": {
                    "final_ranking_ids": ranking_ids,
                    "final_ranking_labels": ranking_labels,
                },
            }
            routed = merge_calib_compat.run_compat_parallel(
                case=case_for_compat,
                ranking_labels=ranking_labels,
                vignette=vignette_body,
                findings=findings,
                option_maps=None,
                gold_leaf_ids=[],
                cache=gran_cache,
                dry_run=bool(payload.get("calibration_dry_run")),
                k=int(payload.get("calibration_k") or 5),
            )
            ranking_labels = list(routed.get("ranking_labels") or ranking_labels)
            ranking_ids = list(routed.get("ordered_ids") or ranking_ids)
            for r in ranking_labels:
                if r.get("id"):
                    label_by_id[str(r["id"])] = dict(r)
            calib_meta = routed.get("calib") or {}
            granularity_meta = {
                "mode": "compat",
                "enabled": True,
                "path": routed.get("branch"),
                "compat_mode": routed.get("mode"),
                "gate": routed.get("gate"),
                "merge_top1_repaired": calib_meta.get("merge_top1_repaired"),
            }
            # compat already applied merge-only XOR both_l1fallback
            skip_followon_calib = True
            calibration_meta = {
                "arm": calib_meta.get("arm") or (
                    "ours" if routed.get("branch") == "merge_only" else "both_l1fallback"
                ),
                "enabled": routed.get("branch") == "calib_only",
                "reverted": bool(calib_meta.get("reverted")),
                "swapped": bool(calib_meta.get("swapped")),
                "via": "merge_calib_compat.parallel",
            }
        elif granularity_mode in {"merge", "deepen"}:
            options = subdivide_l2.parse_options_from_case_text(
                str(case.get("case_text") or "")
            )
            gran_cache = bfs_eval.CachedLLM(
                llm,
                cache_dir / "granularity_llm_cache.json",
                payload["model"],
            )
            routed = deepen_or_merge.route_case(
                ranking_labels,
                options=options,
                vignette=str(case.get("case_text") or ""),
                cache=gran_cache,
                dry_run=bool(payload.get("calibration_dry_run")),
                top_k=int(payload.get("calibration_k") or 5),
                force_path=granularity_mode,
            )
            ranking_labels = list(routed.get("ranking_labels") or ranking_labels)
            ranking_ids = list(routed.get("ordered_ids") or ranking_ids)
            for r in ranking_labels:
                if r.get("id"):
                    label_by_id[str(r["id"])] = dict(r)
            granularity_meta = {
                "mode": granularity_mode,
                "enabled": True,
                "path": routed.get("path"),
                "fine": routed.get("fine"),
                "coarse": {
                    "triggered": (routed.get("coarse") or {}).get("triggered"),
                    "coarse_leaf_ids": (routed.get("coarse") or {}).get(
                        "coarse_leaf_ids"
                    ),
                },
                "n_synthetic": (routed.get("subdivide") or {}).get("n_synthetic"),
                "forbids_support_only": routed.get("forbids_support_only"),
            }

        # Default harness: TopKCalibration after A3 joint (+ optional granularity),
        # before mapper. Gold leaf ids are unknown here.
        # Skipped when granularity_mode=compat (already applied XOR calib).
        calibration_arm = str(
            payload.get("calibration_arm") or DEFAULT_CALIBRATION_ARM
        ).strip().lower()
        if not skip_followon_calib:
            calibration_meta = {
                "arm": "ours",
                "enabled": False,
                "reverted": False,
                "swapped": False,
            }
        if (
            not skip_followon_calib
            and calibration_arm
            and calibration_arm not in {"ours", "off", "none", ""}
        ):
            calib_cache = bfs_eval.CachedLLM(
                llm,
                cache_dir / "topk_calibration_llm_cache.json",
                payload["model"],
            )
            case_for_calib = {
                "l1": {"l1_posteriors": l1_rows},
                "l2": {
                    "final_ranking_ids": ranking_ids,
                    "final_ranking_labels": ranking_labels,
                },
            }
            calib_result = topk_calib.calibrate_case(
                case=case_for_calib,
                vignette=vignette_body,
                findings=findings,
                gold_leaf_ids=[],
                arm=calibration_arm,
                cache=calib_cache,
                k=int(payload.get("calibration_k") or 5),
                dry_run=bool(payload.get("calibration_dry_run")),
            )
            ranking_ids = list(calib_result.get("ordered_ids") or ranking_ids)
            # Preserve synthetic L3 labels; fall back to tree state for others.
            rebuilt = []
            for idx, lid in enumerate(ranking_ids, start=1):
                if lid in label_by_id:
                    row = dict(label_by_id[lid])
                    row["rank"] = idx
                    rebuilt.append(row)
                else:
                    from_state = _ranking_labels(l2_state, [lid])
                    if from_state:
                        row = dict(from_state[0])
                        row["rank"] = idx
                        rebuilt.append(row)
                    else:
                        rebuilt.append({
                            "id": lid,
                            "label": lid,
                            "parent": "",
                            "rank": idx,
                        })
            ranking_labels = rebuilt
            calibration_meta = {
                "arm": calib_result.get("arm"),
                "enabled": True,
                "reverted": bool(calib_result.get("reverted")),
                "swapped": bool(calib_result.get("swapped")),
                "pool_pre": list(calib_result.get("pool_pre") or ()),
                "pool_post": list(calib_result.get("pool_post") or ()),
                "counts": calib_result.get("counts") or {},
                "scores": calib_result.get("scores") or {},
            }

        # Opt-in R2 harness hook: after compat/calib, inject full-tree leaves
        # into final ranking so mapper can see gold-near leaves (default off).
        leaf_inject_meta: dict[str, Any] = {"enabled": False}
        if bool(payload.get("leaf_inject_bind_repair")):
            tree_state: dict[str, Any] = {}
            if isinstance(tree, Mapping):
                raw_state = tree.get("state")
                tree_state = raw_state if isinstance(raw_state, dict) else dict(tree)
            injected = mapper_bind_repair.apply_leaf_inject_to_ranking(
                case={"l2": {}},
                tree_state=tree_state,
                ranking_labels=ranking_labels,
                ranking_ids=ranking_ids,
            )
            ranking_labels = list(injected["ranking_labels"])
            ranking_ids = list(injected["ranking_ids"])
            for r in ranking_labels:
                if r.get("id"):
                    label_by_id[str(r["id"])] = dict(r)
            leaf_inject_meta = {
                "enabled": True,
                "n_before": injected.get("n_before"),
                "n_after": injected.get("n_after"),
                "n_injected_extra": injected.get("n_injected_extra"),
                "policy": "preserve_joint_then_posterior",
            }

        resolver = load_offline_resolver(ROOT)
        gold_l2 = l2pipe.build_gold_l2(
            gold_label=str(case["gold"]),
            state=l2_state,
            resolver=resolver,
        )
        auto_metrics = l2pipe.score_l2(
            ranking=ranking_ids,
            gold=gold_l2,
            scope_ids=joint_payload.get("scope_ids") or (),
            schema_valid=bool(
                (joint_payload.get("arbiter") or {}).get("schema_valid")
            ),
            champion_ids=joint_payload.get("champion_ids") or (),
        )
        human = _human_judge_row(
            gold=str(case["gold"]),
            ranking_labels=ranking_labels,
            resolver=resolver,
        )
        record = {
            "schema_version": 1,
            "status": "OK",
            "case_id": case_id,
            "run_fingerprint": fingerprint,
            "duration_seconds": round(time.monotonic() - started, 3),
            "gold": str(case["gold"]),
            "l1": {
                "preset": l1_preset,
                "compiler_rules_injected": inject_compiler,
                "selected_budget": l1_budget,
                "actual_round": actual_round,
                "selected_fact_ids": selected_ids,
                "n_selected": len(selected_ids),
                "l1_posteriors": l1_rows,
                "stop_reason": trace.get("stop_reason"),
                "l1_calib": l1_calib_meta,
            },
            "l2": {
                "generation": {
                    "config_a": l2_gen.get("config_a"),
                    "l1_expansion_rate": (l2_gen.get("expansion") or {}).get(
                        "l1_expansion_rate"
                    ),
                    "targeted_l2_gapfill": gapfill_meta,
                },
                "joint_arm": joint_payload.get("arm"),
                "final_ranking_ids": ranking_ids,
                "final_ranking_labels": ranking_labels,
                "gold_l2": gold_l2,
                "auto_metrics": auto_metrics,
                "schema_valid": bool(
                    (joint_payload.get("arbiter") or {}).get("schema_valid")
                ),
                "topk_calibration": calibration_meta,
                "granularity": granularity_meta,
                "leaf_inject_bind_repair": leaf_inject_meta,
                "targeted_l2_gapfill": gapfill_meta,
                "local_evidence_budget": local_budget,
                "between_evidence_budget": between_budget,
                "l2_candidate_max_per_live_family": cand_max,
                "posterior_writeback": posterior_meta,
                "leaf_score_fidelity": leaf_score_fidelity,
                "annotated_tree_write": tree_write_meta,
            },
            "human_adjudication": human,
            "answer_mapper_called": False,
            "worker_pid": os.getpid(),
        }
        # Sidecar: pre-compat joint middleware for C1/C2 ablations (never touches frozen/).
        try:
            import pre_compat_joint as _pcj  # local import: scripts/paper on sys.path

            gate = (granularity_meta.get("gate") or {}) if isinstance(granularity_meta, dict) else {}
            art = _pcj.build_artifact(
                case_id=case_id,
                source_annotate=str(Path(payload.get("output_dir") or out_path.parent.parent)),
                pre_ids=pre_compat_ids,
                pre_labels=pre_compat_labels,
                recovery={
                    "method": "annotate_live_capture",
                    "selected_by": "pre_compat_before_granularity",
                    "n_arbiter_entries": 1,
                },
                post_compat_ref={
                    "final_ranking_ids": list(ranking_ids),
                    "final_ranking_labels": [dict(r) for r in ranking_labels],
                    "granularity_path": granularity_meta.get("path"),
                    "compat_mode": granularity_meta.get("compat_mode")
                    or granularity_meta.get("mode"),
                    "gate": {
                        "n_leaves": gate.get("n_leaves"),
                        "triggered": gate.get("triggered"),
                        "top1_id": gate.get("top1_id"),
                        "top1_members": list(gate.get("top1_members") or ()),
                    },
                },
                joint_arm=str(joint_payload.get("arm") or "A3-joint-primary"),
            )
            side_dir = Path(out_path).parent.parent / _pcj.DEFAULT_SUBDIR
            # out_path is …/case_results/<id>.json → parent.parent = annotate root
            if Path(out_path).parent.name == "case_results":
                side_dir = Path(out_path).parent.parent / _pcj.DEFAULT_SUBDIR
            else:
                side_dir = Path(out_path).parent / _pcj.DEFAULT_SUBDIR
            side_dir.mkdir(parents=True, exist_ok=True)
            _atomic_json(side_dir / f"{case_id}.json", art)
        except Exception as _pcj_exc:  # noqa: BLE001
            # Non-fatal: case_results remains authoritative for main metrics.
            record.setdefault("warnings", [])
            if isinstance(record.get("warnings"), list):
                record["warnings"].append(
                    "pre_compat_joint_write_failed: %s: %s"
                    % (type(_pcj_exc).__name__, _pcj_exc)
                )
    except Exception as exc:  # noqa: BLE001
        import traceback
        record = {
            "schema_version": 1,
            "status": "ERROR",
            "case_id": case_id,
            "run_fingerprint": fingerprint,
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc()[-2500:],
            "answer_mapper_called": False,
        }
    _atomic_json(out_path, record)
    return record


def run_downstream(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.output_dir).expanduser().resolve()
    stage = json.loads((out / "stage_manifest.json").read_text(encoding="utf-8"))
    case_ids = list(stage["case_ids"])
    if getattr(args, "cases", None):
        wanted = {
            token.strip()
            for token in str(args.cases).split(",")
            if token.strip()
        }
        if wanted:
            missing = sorted(wanted - set(case_ids))
            if missing:
                raise RuntimeError(
                    "requested cases missing from stage_manifest: %s" % missing
                )
            case_ids = [cid for cid in case_ids if cid in wanted]
    cases_doc = json.loads((out / "normalized_cases.json").read_text(encoding="utf-8"))
    cases = [c for c in cases_doc["cases"] if str(c["id"]) in set(case_ids)]
    _, fixture_cases = competition._fixture_cases(out / "finding_fixture_v1.json")

    l1_preset = str(
        getattr(args, "l1_bfs_preset", None) or "p5_anti_anchor_direct"
    ).strip()
    inject_compiler = not bool(getattr(args, "no_inject_compiler_rules", False))
    fingerprint = stable_hash({
        "phase": "downstream-top2",
        "preset": l1_preset,
        "inject_compiler_rules": inject_compiler,
        "fixed_l1_budget": int(
            getattr(args, "fixed_l1_budget", FIXED_L1_BUDGET) or FIXED_L1_BUDGET
        ),
        "l2_local_evidence_budget": int(
            getattr(args, "l2_local_evidence_budget", DEFAULT_L2_LOCAL_EVIDENCE_BUDGET)
            or DEFAULT_L2_LOCAL_EVIDENCE_BUDGET
        ),
        "l2_between_evidence_budget": int(
            getattr(
                args,
                "l2_between_evidence_budget",
                DEFAULT_L2_BETWEEN_EVIDENCE_BUDGET,
            )
            or DEFAULT_L2_BETWEEN_EVIDENCE_BUDGET
        ),
        "l2_candidate_max_per_live_family": int(
            getattr(args, "l2_candidate_max_per_live_family", DEFAULT_L2_CANDIDATE_MAX)
            or DEFAULT_L2_CANDIDATE_MAX
        ),
        "l2_gap_force_emit_uncovered": bool(
            getattr(args, "l2_gap_force_emit_uncovered", DEFAULT_FORCE_EMIT)
        ),
        "l2_gap_force_emit_max": int(
            getattr(args, "l2_gap_force_emit_max", DEFAULT_FORCE_EMIT_MAX)
            or DEFAULT_FORCE_EMIT_MAX
        ),
        "write_annotated_trees": bool(
            getattr(args, "write_annotated_trees", True)
        ),
        "writeback_mode": str(
            getattr(args, "writeback_mode", "normal") or "normal"
        ),
        "writeback_shuffle_seed": int(
            getattr(args, "writeback_shuffle_seed", 20260731) or 20260731
        ),
        "score_scope_mode": str(
            getattr(args, "score_scope_mode", "per_family") or "per_family"
        ),
        "joint_arm": "A3-joint-primary",
        "calibration_arm": str(
            getattr(args, "calibration_arm", DEFAULT_CALIBRATION_ARM)
        ),
        "granularity_mode": str(
            getattr(args, "granularity_mode", DEFAULT_GRANULARITY_MODE)
        ),
        "l1_calib": str(getattr(args, "l1_calib", DEFAULT_L1_CALIB)),
        "targeted_l2_gapfill": bool(
            getattr(args, "targeted_l2_gapfill", DEFAULT_TARGETED_L2_GAPFILL)
        ),
        "targeted_l2_gapfill_arm": str(
            getattr(
                args,
                "targeted_l2_gapfill_arm",
                DEFAULT_TARGETED_L2_GAPFILL_ARM,
            )
        ),
        "l1_axis_mode": str(getattr(args, "l1_axis_mode", "adaptive") or "adaptive"),
        "no_tree_semantic_dedupe": bool(
            getattr(args, "no_tree_semantic_dedupe", False)
        ),
        "reuse_l2_leaves": bool(getattr(args, "reuse_l2_leaves", False)),
        "case_ids": case_ids,
        "p5_arm": stage["p5_arm"],
        "fixture": stage["fixture"],
        "model": args.model,
        "output_cap": os.environ.get("TREE_DX_DIRECT_POST_OUTPUT_CAP"),
    })

    case_dir = out / "case_results"
    case_dir.mkdir(parents=True, exist_ok=True)
    cache_root = out / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)

    payloads = []
    for case in cases:
        cid = str(case["id"])
        payloads.append({
            "case": case,
            "tree_path": str(out / "shared_trees" / ("%s.json" % cid)),
            "p5_arm": str(out / "p5_headline_frozen.json"),
            "fixture_case": fixture_cases[cid],
            "out_path": str(case_dir / ("%s.json" % cid)),
            "cache_dir": str(cache_root / cid),
            "fingerprint": fingerprint,
            "model": args.model,
            "call_timeout": args.call_timeout,
            "resume": bool(args.resume),
            "calibration_arm": str(
                getattr(args, "calibration_arm", DEFAULT_CALIBRATION_ARM)
            ),
            "calibration_k": int(getattr(args, "calibration_k", 5) or 5),
            "calibration_dry_run": bool(
                getattr(args, "calibration_dry_run", False)
            ),
            "granularity_mode": str(
                getattr(args, "granularity_mode", DEFAULT_GRANULARITY_MODE)
            ),
            "l1_calib": str(getattr(args, "l1_calib", DEFAULT_L1_CALIB)),
            "leaf_inject_bind_repair": bool(
                getattr(
                    args,
                    "leaf_inject_bind_repair",
                    DEFAULT_LEAF_INJECT_BIND_REPAIR,
                )
            ),
            "targeted_l2_gapfill": bool(
                getattr(
                    args,
                    "targeted_l2_gapfill",
                    DEFAULT_TARGETED_L2_GAPFILL,
                )
            ),
            "targeted_l2_gapfill_arm": str(
                getattr(
                    args,
                    "targeted_l2_gapfill_arm",
                    DEFAULT_TARGETED_L2_GAPFILL_ARM,
                )
            ),
            "fixed_l1_budget": int(
                getattr(args, "fixed_l1_budget", FIXED_L1_BUDGET) or FIXED_L1_BUDGET
            ),
            "l2_local_evidence_budget": int(
                getattr(
                    args,
                    "l2_local_evidence_budget",
                    DEFAULT_L2_LOCAL_EVIDENCE_BUDGET,
                )
                or DEFAULT_L2_LOCAL_EVIDENCE_BUDGET
            ),
            "l2_between_evidence_budget": int(
                getattr(
                    args,
                    "l2_between_evidence_budget",
                    DEFAULT_L2_BETWEEN_EVIDENCE_BUDGET,
                )
                or DEFAULT_L2_BETWEEN_EVIDENCE_BUDGET
            ),
            "l2_candidate_max_per_live_family": int(
                getattr(
                    args,
                    "l2_candidate_max_per_live_family",
                    DEFAULT_L2_CANDIDATE_MAX,
                )
                or DEFAULT_L2_CANDIDATE_MAX
            ),
            "l2_gap_force_emit_uncovered": bool(
                getattr(args, "l2_gap_force_emit_uncovered", DEFAULT_FORCE_EMIT)
            ),
            "l2_gap_force_emit_max": int(
                getattr(args, "l2_gap_force_emit_max", DEFAULT_FORCE_EMIT_MAX)
                or DEFAULT_FORCE_EMIT_MAX
            ),
            "write_annotated_trees": bool(
                getattr(args, "write_annotated_trees", True)
            ),
            "writeback_mode": str(
                getattr(args, "writeback_mode", "normal") or "normal"
            ),
            "writeback_shuffle_seed": int(
                getattr(args, "writeback_shuffle_seed", 20260731) or 20260731
            ),
            "score_scope_mode": str(
                getattr(args, "score_scope_mode", "per_family") or "per_family"
            ),
            "l1_bfs_preset": l1_preset,
            "inject_compiler_rules": inject_compiler,
            "l1_axis_mode": str(
                getattr(args, "l1_axis_mode", "adaptive") or "adaptive"
            ),
            "no_tree_semantic_dedupe": bool(
                getattr(args, "no_tree_semantic_dedupe", False)
            ),
            "reuse_l2_leaves": bool(getattr(args, "reuse_l2_leaves", False)),
        })

    workers = min(int(args.workers), len(payloads))
    print(
        "\n=== downstream top2 workers=%d n=%d ===" % (workers, len(payloads)),
        flush=True,
    )
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_run_one_case, payload): payload["case"]["id"]
            for payload in payloads
        }
        done = 0
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = {
                    "case_id": case_id,
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            records.append(row)
            done += 1
            print(
                "[downstream] %d/%d %s %s at1=%s at2=%s dur=%s"
                % (
                    done,
                    len(payloads),
                    case_id,
                    row.get("status"),
                    (row.get("human_adjudication") or {}).get("at1"),
                    (row.get("human_adjudication") or {}).get("at2"),
                    row.get("duration_seconds"),
                ),
                flush=True,
            )
    wall = time.monotonic() - started
    records.sort(key=lambda row: str(row.get("case_id") or ""))
    ok = [row for row in records if row.get("status") == "OK"]
    n_ok = len(ok)
    at1 = sum(1 for row in ok if (row.get("human_adjudication") or {}).get("at1"))
    at2 = sum(1 for row in ok if (row.get("human_adjudication") or {}).get("at2"))
    durs = [
        float(row["duration_seconds"])
        for row in ok
        if row.get("duration_seconds") is not None
    ]
    summary = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "phase": "downstream-top2",
        "workers": workers,
        "n_cases": len(records),
        "n_ok": n_ok,
        "n_error": len(records) - n_ok,
        "wall_seconds": round(wall, 3),
        "throughput_cases_per_hour": (
            round(len(records) / wall * 3600.0, 3) if wall > 0 else None
        ),
        "mean_case_seconds": (
            round(sum(durs) / len(durs), 3) if durs else None
        ),
        "max_case_seconds": round(max(durs), 3) if durs else None,
        "performance": {
            "judge": "agent_label_match_v1",
            "at1": at1,
            "at2": at2,
            "at1_rate": round(at1 / n_ok, 4) if n_ok else None,
            "at2_rate": round(at2 / n_ok, 4) if n_ok else None,
            "note": (
                "No AnswerMapper; agent semantic label-match vs gold. "
                "Review adjudication_sheet.json for disagreements."
            ),
        },
        "fixed_l1_budget": FIXED_L1_BUDGET,
        "joint_arm": "A3-joint-primary",
        "calibration_arm": str(
            getattr(args, "calibration_arm", DEFAULT_CALIBRATION_ARM)
        ),
        "granularity_mode": str(
            getattr(args, "granularity_mode", DEFAULT_GRANULARITY_MODE)
        ),
        "l1_calib": str(getattr(args, "l1_calib", DEFAULT_L1_CALIB)),
        "targeted_l2_gapfill": bool(
            getattr(args, "targeted_l2_gapfill", DEFAULT_TARGETED_L2_GAPFILL)
        ),
        "targeted_l2_gapfill_arm": str(
            getattr(
                args,
                "targeted_l2_gapfill_arm",
                DEFAULT_TARGETED_L2_GAPFILL_ARM,
            )
        ),
        "run_fingerprint": fingerprint,
        "errors": [
            {"case_id": row.get("case_id"), "error": row.get("error")}
            for row in records if row.get("status") != "OK"
        ],
    }
    _atomic_json(out / "downstream_summary.json", summary)
    sheet = {
        "asset_kind": "diagnosisarena_top2_adjudication_v1",
        "human_signed_off": False,
        "mapper_used": False,
        "rows": [
            {
                "case_id": row.get("case_id"),
                "status": row.get("status"),
                "gold": row.get("gold") or (row.get("human_adjudication") or {}).get("gold"),
                "top1": (row.get("human_adjudication") or {}).get("top1_label"),
                "top2": (row.get("human_adjudication") or {}).get("top2_label"),
                "at1": (row.get("human_adjudication") or {}).get("at1"),
                "at2": (row.get("human_adjudication") or {}).get("at2"),
                "ranking": (row.get("l2") or {}).get("final_ranking_labels"),
                "review_status": "pending_human",
                "review_notes": "",
            }
            for row in records
        ],
    }
    _atomic_json(out / "adjudication_sheet.json", sheet)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-json", type=Path, default=DEFAULT_CASES_JSON)
    parser.add_argument("--vignette-freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--stress-root", type=Path, default=DEFAULT_STRESS_ROOT)
    parser.add_argument(
        "--freeze-root",
        type=Path,
        default=None,
        help=(
            "Flat freeze dir with shared_trees/ + p5_headline_frozen.json "
            "(preferred over --stress-root cohort layout)"
        ),
    )
    parser.add_argument(
        "--cases",
        default="",
        help="Optional comma-separated subset of staged case ids",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--skip-stage",
        action="store_true",
        help="Reuse existing staged trees/P5/fixture under --output-dir",
    )
    parser.add_argument(
        "--calibration-arm",
        default=DEFAULT_CALIBRATION_ARM,
        choices=[
            "ours",
            "off",
            "none",
            "support_rerank",
            "pair",
            "both",
            "both_l1fallback",
            "l1fallback",
        ],
        help=(
            "TopKCalibration arm after A3 joint (default: both_l1fallback). "
            "Use ours/off/none to disable."
        ),
    )
    parser.add_argument(
        "--calibration-k",
        type=int,
        default=5,
        help="Closed Top-K pool size for calibration",
    )
    parser.add_argument(
        "--calibration-dry-run",
        action="store_true",
        help="Skip calibration LLM calls (heuristic/joint-logit only)",
    )
    parser.add_argument(
        "--granularity-mode",
        default=DEFAULT_GRANULARITY_MODE,
        choices=["off", "merge", "deepen", "compat"],
        help=(
            "Post-joint granularity: compat=merge×calib parallel select (default); "
            "deepen/merge=AdaptiveDeepenOrMerge; off=calibration only"
        ),
    )
    parser.add_argument(
        "--l1-calib",
        default=DEFAULT_L1_CALIB,
        choices=["off", "ours", "support", "pair", "b12"],
        help=(
            "Optional L1 family calib after F6 freeze (default off). "
            "b12=SupportRerank→Pair; does not change L2 leaf calib default."
        ),
    )
    parser.add_argument(
        "--leaf-inject-bind-repair",
        action="store_true",
        default=DEFAULT_LEAF_INJECT_BIND_REPAIR,
        help=(
            "Opt-in R2 hook after compat/calib: inject full shared-tree leaves "
            "into final_ranking before mapper (default off)."
        ),
    )
    parser.add_argument(
        "--targeted-l2-gapfill",
        action="store_true",
        default=DEFAULT_TARGETED_L2_GAPFILL,
        help=(
            "Opt-in research overlay after Config A: targeted L2 gapfill "
            "(hybrid ALL_B_b1 by default) before joint ranking (default off)."
        ),
    )
    parser.add_argument(
        "--targeted-l2-gapfill-arm",
        default=DEFAULT_TARGETED_L2_GAPFILL_ARM,
        help="Hybrid arm for --targeted-l2-gapfill (default ALL_B_b1; B-source only).",
    )
    parser.add_argument(
        "--fixed-l1-budget",
        type=int,
        default=FIXED_L1_BUDGET,
        help="L1 evidence freeze prefix Fn (default 6; OX locked uses 4).",
    )
    parser.add_argument(
        "--l2-local-evidence-budget",
        type=int,
        default=DEFAULT_L2_LOCAL_EVIDENCE_BUDGET,
        help="Per-family local evidence stop_after (default 4).",
    )
    parser.add_argument(
        "--l2-between-evidence-budget",
        type=int,
        default=DEFAULT_L2_BETWEEN_EVIDENCE_BUDGET,
        help="Between-family evidence stop_after (default 2).",
    )
    parser.add_argument(
        "--l2-candidate-max-per-live-family",
        type=int,
        default=DEFAULT_L2_CANDIDATE_MAX,
        help="Max L2 children kept per L1 after live posterior writeback.",
    )
    parser.add_argument(
        "--l2-gap-force-emit-uncovered",
        action="store_true",
        default=DEFAULT_FORCE_EMIT,
        help="Opt-in emit_v1: force-append uncovered ddx∩gap leaves (default off).",
    )
    parser.add_argument(
        "--l2-gap-force-emit-max",
        type=int,
        default=DEFAULT_FORCE_EMIT_MAX,
        help="Max force-emitted leaves per parent (default 3).",
    )
    parser.add_argument(
        "--write-annotated-trees",
        action="store_true",
        default=True,
        help="Write live-reannotated trees back to shared_trees (default on).",
    )
    parser.add_argument(
        "--no-write-annotated-trees",
        action="store_false",
        dest="write_annotated_trees",
        help="Disable shared_trees writeback after joint.",
    )
    parser.add_argument(
        "--writeback-mode",
        default="normal",
        choices=["normal", "placebo_refresh", "shuffled"],
        help=(
            "T1-07: normal | placebo_refresh (cap with new scores, restore old) "
            "| shuffled (permute new scores before cap)."
        ),
    )
    parser.add_argument(
        "--writeback-shuffle-seed",
        type=int,
        default=20260731,
        help="RNG seed for writeback_mode=shuffled.",
    )
    parser.add_argument(
        "--score-scope-mode",
        default="per_family",
        choices=["per_family", "global"],
        help="T1-07 AB31: global = flat recomputation (one annotator scope).",
    )
    parser.add_argument(
        "--l1-bfs-preset",
        default="p5_anti_anchor_direct",
        help=(
            "L1EvidenceBFSPipeline preset "
            "(default p5_anti_anchor_direct; AB21 uses p5_contrastive_direct)."
        ),
    )
    parser.add_argument(
        "--no-inject-compiler-rules",
        action="store_true",
        help="AB22: do not inject P5 compiler_master_blocks into L1 BFS.",
    )
    parser.add_argument(
        "--l1-axis-mode",
        default="adaptive",
        choices=["adaptive", "fixed_icd", "random", "flat"],
        help="C3: L1 axis transform before Config A (default adaptive=M00).",
    )
    parser.add_argument(
        "--no-tree-semantic-dedupe",
        action="store_true",
        help="C3: disable synonym de-dupe guidance in L2RecallCreator (keep exact-string).",
    )
    parser.add_argument(
        "--reuse-l2-leaves",
        action="store_true",
        help="C3: when remapping L1, keep existing L2 leaves (default: strip+regen).",
    )
    args = parser.parse_args()
    args.output_dir = Path(args.output_dir).expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_stage:
        stage_assets(args)
    elif not (args.output_dir / "stage_manifest.json").is_file():
        raise FileNotFoundError("missing stage_manifest.json; run without --skip-stage")

    summary = run_downstream(args)
    return 0 if summary.get("n_error", 1) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
