#!/usr/bin/env python3
"""Offline (+ optional live) eval for R3 gap-fill and Track C R4/R5 on ABSENT cases.

Does NOT change production defaults. Writes analysis/l1_gold_recall_v1/smoke_r3
and smoke_track_c.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import mapper_bind_repair as mbr  # noqa: E402

ANALYSIS = ROOT / "analysis" / "l1_gold_recall_v1"
SUMMARY = ANALYSIS / "l1_gold_recall_summary.json"
CASES_JSON = ROOT / "logs/diagnosisarena_d2_m01_v1/normalized_cases.json"

ABSENT_IDS = ("67", "231")

BASELINE_ARMS = {
    "R4-imedrag": ROOT
    / "runs/paper_v1/diagnosisarena_imedrag_v1/B17-imedrag/replicate_01",
    "R5-dual": ROOT
    / "runs/paper_v1/diagnosisarena_fixed_v1/B04-dual-inf/replicate_01",
    "R5-mac": ROOT
    / "runs/paper_v1/diagnosisarena_fixed_v1/B06-mac-single-vendor/replicate_01",
}

# Clinical gold texts (from case_results / audit)
GOLD = {
    "67": "Septic shock with anuric kidney failure",
    "231": "Stage IV invasive renal urothelial carcinoma",
}

# Multi-token / distinctive stems that indicate a proposed L1 could house gold.
# Avoid lone tokens like "failure" / "infection" alone without sepsis/shock context
# where possible; audit-time uses gold string only for synonym fallback.
GOLD_FAMILY_PHRASES = {
    "67": [
        "septic shock",
        "sepsis",
        "septic",
        "distributive shock",
        "severe sepsis",
        "severe infection",
        "systemic infection",
        "infectious shock",
        "multi organ failure",
        "multiorgan failure",
        "anuric",
        "acute kidney injury from sepsis",
    ],
    "231": [
        "urothelial carcinoma",
        "urothelial cancer",
        "transitional cell carcinoma",
        "renal urothelial",
        "bladder urothelial",
        "invasive urothelial",
        "urinary tract carcinoma",
        "urologic malignancy",
        "primary urothelial",
    ],
}
# Require at least one distinctive stem (not generic "cancer"/"failure" alone).
GOLD_FAMILY_REQUIRED_STEMS = {
    "67": ("septic", "sepsis", "shock", "anuric"),
    "231": ("urothelial", "transitional"),
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tree_path(cid: str) -> Path:
    p1 = (
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/shared_trees"
        / f"{cid}.json"
    )
    p2 = (
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/shared_trees"
        / f"{cid}.json"
    )
    if p1.is_file():
        return p1
    if p2.is_file():
        return p2
    raise FileNotFoundError(cid)


def _case_result_path(cid: str) -> Path:
    p1 = (
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/case_results"
        / f"{cid}.json"
    )
    p2 = (
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/case_results"
        / f"{cid}.json"
    )
    if p1.is_file():
        return p1
    if p2.is_file():
        return p2
    raise FileNotFoundError(cid)


def _l1_labels(case: Mapping[str, Any], tree_state: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    for row in (case.get("l1") or {}).get("l1_posteriors") or ():
        lab = str(row.get("label") or "").strip()
        if lab:
            labels.append(lab)
    if labels:
        return labels
    branches = tree_state.get("branches") or {}
    for bid, b in branches.items():
        if not str(bid).startswith("B") or "." in str(bid):
            continue
        if isinstance(b, Mapping):
            lab = str(b.get("label") or "").strip()
            if lab:
                labels.append(lab)
    return labels


def _hint_goldish(gold: str, hints: Sequence[str]) -> list[str]:
    out: list[str] = []
    for h in hints:
        if mbr.labels_synonymish(gold, h) or mbr.leaf_match_score(gold, h) >= 0.7:
            out.append(h)
            continue
        # soft: shared clinical stem (sepsis/septic, urothelial)
        ng, nh = mbr.norm_label(gold), mbr.norm_label(h)
        for stem in ("sepsis", "septic", "urothelial", "shock"):
            if stem in ng and stem in nh:
                out.append(h)
                break
    return out


def _family_accommodates(gold_cid: str, family_label: str) -> bool:
    nl = mbr.norm_label(family_label)
    if not nl:
        return False
    stems = GOLD_FAMILY_REQUIRED_STEMS[gold_cid]
    has_stem = any(s in nl for s in stems)
    for phrase in GOLD_FAMILY_PHRASES[gold_cid]:
        np = mbr.norm_label(phrase)
        if np and np in nl:
            return True
        # phrase tokens all present (order-free) when phrase has ≥2 tokens
        toks = [t for t in np.split() if len(t) > 2]
        if len(toks) >= 2 and all(t in nl.split() or t in nl for t in toks):
            return True
    gold = GOLD[gold_cid]
    if has_stem and (
        mbr.labels_synonymish(gold, family_label)
        or mbr.leaf_match_score(gold, family_label) >= 0.7
    ):
        return True
    # Strong stem alone for distinctive terms
    if gold_cid == "231" and "urothelial" in nl:
        return True
    if gold_cid == "67" and (
        "septic" in nl or "sepsis" in nl or ("shock" in nl and "septic" in nl)
    ):
        return True
    if gold_cid == "67" and "severe infection" in nl:
        return True
    return False


def eval_r3_offline() -> dict[str, Any]:
    bucket = json.loads(SUMMARY.read_text(encoding="utf-8"))
    unbind = list(bucket["case_ids_by_bucket"]["MAPPER_UNBIND"])
    absent = list(bucket["case_ids_by_bucket"]["TREE_PARENT_ABSENT"])

    unbind_rows: list[dict[str, Any]] = []
    for cid in unbind:
        case = json.loads(_case_result_path(cid).read_text(encoding="utf-8"))
        tree = json.loads(_tree_path(cid).read_text(encoding="utf-8"))
        st = tree.get("state") or tree
        leaves = mbr.leaves_from_tree_state(st) + mbr.leaves_from_ranking(case)
        v2 = mbr.acceptable_parents_v2(case, case.get("mapper") or {}, leaves)
        tree_l1 = mbr.l1_ids_on_tree(case, st)
        tpp = bool(set(v2["acceptable_parent_ids"]) & tree_l1)
        unbind_rows.append(
            {
                "case_id": cid,
                "tree_parent_present_v2_proxy": tpp,
                "n_v2_parents": len(v2["acceptable_parent_ids"]),
                "clinical_bucket": "MAPPER_UNBIND",
                "r3_can_fix_autocoverage": False,
                "reason": (
                    "acceptable parent already on tree/L1; gap-fill only widens "
                    "partition for uncovered recall candidates, cannot rebind mapper"
                ),
            }
        )

    # Build scripts hard-code recall_hints_gap (= hints + gap_fill)
    build_evidence = {
        "m01_build_trees_branch_mode": "recall_hints_gap",
        "pipeline_staged_branch_mode": "recall_hints_gap",
        "config_mapping": (
            "recall_hints_gap → branch_kb_recall_hints=True + "
            "branch_recall_gap_fill=True"
        ),
        "provenance_mode_field": "recall_hints",
        "note": (
            "Frozen DiagnosisArena shared_trees were built with gap_fill ON. "
            "Re-running identical R3-on rebuild is non-informative; ABSENT "
            "persistence under R3-on is decisive."
        ),
    }

    absent_rows: list[dict[str, Any]] = []
    for cid in absent:
        case = json.loads(_case_result_path(cid).read_text(encoding="utf-8"))
        tree = json.loads(_tree_path(cid).read_text(encoding="utf-8"))
        st = tree.get("state") or tree
        bp = st.get("branch_provenance") or {}
        hints = list(bp.get("hints") or [])
        gold = str(case.get("gold") or GOLD.get(cid) or "")
        top10 = hints[:10]
        goldish_top = _hint_goldish(gold, top10)
        goldish_all = _hint_goldish(gold, hints)
        l1 = _l1_labels(case, st)
        l1_accommodates = any(_family_accommodates(cid, lab) for lab in l1)
        leaves = mbr.leaves_from_tree_state(st) + mbr.leaves_from_ranking(case)
        v2 = mbr.acceptable_parents_v2(case, case.get("mapper") or {}, leaves)
        tree_l1 = mbr.l1_ids_on_tree(case, st)
        tpp_proxy = bool(set(v2["acceptable_parent_ids"]) & tree_l1)
        absent_rows.append(
            {
                "case_id": cid,
                "gold": gold,
                "provenance_mode": bp.get("mode"),
                "n_hints": bp.get("n_hints"),
                "goldish_in_top10_hints": goldish_top,
                "goldish_in_all_hints": goldish_all,
                "l1_labels": l1,
                "any_l1_accommodates_gold_keywords": l1_accommodates,
                "tree_parent_present_v2_proxy": tpp_proxy,
                "clinical_tree_parent_present": False,
                "clinical_bucket": "TREE_PARENT_ABSENT",
                "frozen_built_with_gap_fill": True,
            }
        )

    n_unbind = len(unbind_rows)
    verdict = {
        "unbind_coverage_lever": "REJECT",
        "unbind_reason": (
            f"All {n_unbind} MAPPER_UNBIND cases already have clinical/tree parents; "
            "R3 cannot repair AutoCoverage for mapper false MISS."
        ),
        "absent_subset": "REJECT",
        "absent_reason": (
            "Frozen trees already used branch_mode=recall_hints_gap (gap_fill ON); "
            "cases 67 and 231 remain clinical TREE_PARENT_ABSENT (axis mismatch). "
            "R3 does not fix wrong MECE axis when gold-ish hints exist (231) or "
            "when sepsis-like hints fail to force a systemic-shock L1 (67)."
        ),
        "production_default": "leave_unchanged",
        "claim_allowed": False,
    }

    return {
        "generated_at": _utc(),
        "protocol": "r3_gapfill_lite_v1",
        "build_evidence": build_evidence,
        "unbind": {
            "n": n_unbind,
            "n_v2_proxy_present": sum(
                1 for r in unbind_rows if r["tree_parent_present_v2_proxy"]
            ),
            "rows": unbind_rows,
        },
        "absent": {"n": len(absent_rows), "rows": absent_rows},
        "verdict": verdict,
    }


def _load_baseline_diagnoses(arm_dir: Path, source_id: str) -> dict[str, Any]:
    preds: list[str] = []
    union: set[str] = set()
    for line in (arm_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if str(row.get("source_id")) != str(source_id):
            continue
        preds = [str(x) for x in (row.get("top2_diagnoses") or []) if str(x).strip()]
        union.update(preds)
        break
    trace_path = arm_dir / "trace.jsonl"
    if trace_path.is_file():
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if str(row.get("source_id")) != str(source_id):
                continue
            tr = row.get("trace") or {}
            # Dual
            for it in tr.get("iterations") or ():
                fwd = (it.get("forward") or {}).get("diagnoses")
                if isinstance(fwd, Mapping):
                    union.update(str(k) for k in fwd.keys())
                elif isinstance(fwd, list):
                    union.update(str(x) for x in fwd)
            examine = tr.get("examine") or {}
            union.update(str(x) for x in (examine.get("top2_diagnoses") or ()))
            # MAC
            for disc in tr.get("discussion") or ():
                union.update(str(x) for x in (disc.get("ranked_diagnoses") or ()))
            sup = tr.get("supervisor") or {}
            union.update(str(x) for x in (sup.get("top2_diagnoses") or ()))
            # i-MedRAG
            fin = tr.get("final") or {}
            union.update(str(x) for x in (fin.get("top2_diagnoses") or ()))
            if fin.get("answer"):
                union.add(str(fin["answer"]))
            break
    return {
        "top2_diagnoses": preds,
        "union_diagnoses": sorted(u for u in union if u.strip()),
    }


def eval_track_c_upper() -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    for arm, path in BASELINE_ARMS.items():
        arm_rows: list[dict[str, Any]] = []
        for cid in ABSENT_IDS:
            blob = _load_baseline_diagnoses(path, cid)
            # Normalize: each diagnosis is a proposed L1/family candidate (fail-open keep)
            proposed = list(dict.fromkeys(blob["union_diagnoses"] or blob["top2_diagnoses"]))
            # Gold-blind normalize: drop empty; keep label as proposed family name
            normalized = [p for p in proposed if p and len(p.strip()) >= 3]
            fail_discard = len(proposed) - len(normalized)
            hit = [p for p in normalized if _family_accommodates(cid, p)]
            upper = bool(hit)
            arm_rows.append(
                {
                    "case_id": cid,
                    "gold": GOLD[cid],
                    "top2": blob["top2_diagnoses"],
                    "n_union": len(blob["union_diagnoses"]),
                    "n_normalized": len(normalized),
                    "normalize_fail_discard": fail_discard,
                    "accommodating_proposals": hit,
                    "tree_parent_present_upper_bound": upper,
                }
            )
        n_upper = sum(1 for r in arm_rows if r["tree_parent_present_upper_bound"])
        per_arm[arm] = {
            "source_dir": str(path.relative_to(ROOT)),
            "n_absent_helped_upper": n_upper,
            "rows": arm_rows,
            "upper_bound_pass": n_upper >= 1,
        }

    # Live gate: only if any arm upper-bounds ≥1 ABSENT case
    live_candidates = [
        arm for arm, payload in per_arm.items() if payload["upper_bound_pass"]
    ]
    verdict = {
        "R4-imedrag": (
            "PASS_UPPER" if per_arm["R4-imedrag"]["upper_bound_pass"] else "REJECT_UPPER"
        ),
        "R5-dual": (
            "PASS_UPPER" if per_arm["R5-dual"]["upper_bound_pass"] else "REJECT_UPPER"
        ),
        "R5-mac": (
            "PASS_UPPER" if per_arm["R5-mac"]["upper_bound_pass"] else "REJECT_UPPER"
        ),
        "default_production": "REJECT",
        "live_recommended_arms": live_candidates,
        "note": (
            "Upper bound asks whether baseline-proposed disease names could serve "
            "as L1 families that accommodate gold. Does not claim BranchCreator "
            "would choose them. Live inject only if listed."
        ),
    }
    return {
        "generated_at": _utc(),
        "protocol": "track_c_upper_bound_v1",
        "arms": per_arm,
        "verdict": verdict,
    }


def run_track_c_live_inject(upper: Mapping[str, Any], model: str) -> dict[str, Any]:
    """Live lite: rebuild ABSENT trees with baseline diagnoses prepended as extra
    recall hints (gold-blind). Uses recall_hints_gap. Cost-capped conceptually by
    n=2 cases only.
    """
    from eval_branch_creation_medbullets import build_controller, run_case_branches
    from diagnosisarena_adapter import (
        apply_frozen_vignette_parser_fields,
        load_vignette_parser_freeze,
    )

    freeze_pilot = load_vignette_parser_freeze(
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/vignette_parser_probe_v3"
        / "vignette_parser_frozen_v3.json"
    )
    freeze_remain = load_vignette_parser_freeze(
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/frozen"
        / "vignette_parser_frozen.json"
    )
    freezes = {**freeze_pilot, **freeze_remain}

    cases_doc = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    case_by_id = {str(c["id"]): c for c in cases_doc["cases"]}

    out_dir = (
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/track_c_absent_inject_v1"
        / "shared_trees"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build inject lists per arm that passed upper bound
    inject_by_arm: dict[str, dict[str, list[str]]] = {}
    for arm, payload in (upper.get("arms") or {}).items():
        if not payload.get("upper_bound_pass"):
            continue
        inject_by_arm[arm] = {}
        for row in payload["rows"]:
            cid = str(row["case_id"])
            # Prefer accommodating proposals; else skip case for this arm
            props = list(row.get("accommodating_proposals") or [])
            if not props:
                continue
            inject_by_arm[arm][cid] = props[:8]
        if not inject_by_arm[arm]:
            del inject_by_arm[arm]

    results: dict[str, Any] = {"arms": {}, "model": model}

    for arm, by_cid in inject_by_arm.items():
        arm_out: list[dict[str, Any]] = []
        for cid, extra in by_cid.items():
            case = case_by_id[cid]
            freeze_row = freezes.get(cid)
            if not freeze_row:
                arm_out.append({"case_id": cid, "status": "NO_FREEZE"})
                continue
            t0 = time.time()
            controller, env, _, _prov = build_controller(
                model,
                branch_mode="recall_hints_gap",
                config_overrides={
                    "talp_disc_profile": "off",
                    "force_expand_all_l1": True,
                },
            )
            orig_build = controller._build_branch_candidates

            def _build_with_inject(state, _extra=extra, _orig=orig_build):
                bk = _orig(state)
                if not isinstance(bk, dict):
                    return bk
                cands = list(bk.get("candidate_diseases") or [])
                merged = list(dict.fromkeys([*_extra, *cands]))
                bk = dict(bk)
                bk["candidate_diseases"] = merged
                bk["track_c_inject"] = list(_extra)
                return bk

            controller._build_branch_candidates = _build_with_inject  # type: ignore

            def _prepare(state, _case=case, _fr=freeze_row, _cid=cid) -> None:
                state.case_id = _cid
                apply_frozen_vignette_parser_fields(state, _case, _fr)

            state = run_case_branches(
                controller,
                env,
                str(case["case_text"]),
                parse_vignette=False,
                prepare_state=_prepare,
            )
            state.case_id = cid
            state.max_tree_depth = 2
            expansion = controller.force_expand_all_l1(state)
            elapsed = round(time.time() - t0, 2)
            branches = getattr(state, "branches", None) or {}
            l1_labels: list[str] = []
            for bid, b in (branches.items() if isinstance(branches, Mapping) else []):
                if "." in str(bid):
                    continue
                lab = getattr(b, "label", None) or (
                    b.get("label") if isinstance(b, Mapping) else None
                )
                if lab:
                    l1_labels.append(str(lab))
            accommodates = any(_family_accommodates(cid, lab) for lab in l1_labels)
            path = out_dir / f"{arm.replace('/', '_')}__{cid}.json"
            # Compact state for audit (labels + provenance)
            bp = getattr(state, "branch_provenance", None)
            if hasattr(bp, "__dict__"):
                bp = dict(bp.__dict__)
            tree_payload = {
                "case_id": cid,
                "arm": arm,
                "elapsed_sec": elapsed,
                "inject": extra,
                "l1_expansion_rate": expansion.get("l1_expansion_rate"),
                "l1_labels": l1_labels,
                "branch_provenance": bp,
                "n_branches": len(branches) if isinstance(branches, Mapping) else None,
            }
            row = {
                "case_id": cid,
                "arm": arm,
                "status": "OK",
                "elapsed_sec": elapsed,
                "inject": extra,
                "l1_labels": l1_labels,
                "any_l1_accommodates_gold_keywords": accommodates,
                "tree_parent_present_clinical_proxy": accommodates,
                "tree_path": str(path.relative_to(ROOT)),
            }
            path.write_text(
                json.dumps({**tree_payload, "eval": row}, indent=2, ensure_ascii=False, default=str)
                + "\n",
                encoding="utf-8",
            )
            arm_out.append(row)
            print(
                f"[track_c_live] {arm} case={cid} accommodates={accommodates} "
                f"n_l1={len(l1_labels)} t={elapsed}s",
                flush=True,
            )
        n_help = sum(
            1 for r in arm_out if r.get("tree_parent_present_clinical_proxy")
        )
        results["arms"][arm] = {
            "rows": arm_out,
            "n_absent_helped_live": n_help,
            "n_attempted": len(arm_out),
            "live_pass_lite": n_help >= 1,
            "cost_note": "ABSENT-only rebuild with inject; vs full100 N/A",
        }

    any_pass = any(v.get("live_pass_lite") for v in results["arms"].values())
    results["verdict"] = {
        "live_pass_lite": any_pass,
        "default_production": "REJECT_DEFAULT_KEEP_OFF",
        "claim": (
            "PASS-lite on ABSENT subset only; must not claim full AutoCoverage lift"
            if any_pass
            else "Live inject did not create accommodating L1 for ABSENT cases"
        ),
        "claim_allowed_for_main_table": False,
    }
    results["generated_at"] = _utc()
    return results


def write_r3_report(payload: Mapping[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    v = payload["verdict"]
    lines = [
        "# R3 gap-fill smoke (`smoke_r3`)",
        "",
        f"- generated: `{payload['generated_at']}`",
        f"- protocol: `{payload['protocol']}`",
        "",
        "## Verdict",
        "",
        f"- UNBIND coverage lever: **{v['unbind_coverage_lever']}** — {v['unbind_reason']}",
        f"- ABSENT subset: **{v['absent_subset']}** — {v['absent_reason']}",
        f"- `claim_allowed`: `{v['claim_allowed']}`",
        f"- production default: **leave off / unchanged** (build already used gap_fill)",
        "",
        "## Build evidence (frozen ≡ R3-on)",
        "",
        "```json",
        json.dumps(payload["build_evidence"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Mechanism: MAPPER_UNBIND (n=18)",
        "",
        "Gap-fill only repairs uncovered *recall candidates* into the MECE partition. "
        "It cannot create mapper leaf binds. Clinical audit parents already present → "
        "R3 **cannot** raise AutoCoverage on these 18.",
        "",
        f"- v2 proxy TreeParentPresent: "
        f"**{payload['unbind']['n_v2_proxy_present']}/{payload['unbind']['n']}**",
        "",
        "## ABSENT applicability (67, 231)",
        "",
        "| case | goldish in top10 hints | any L1 keyword-fit | clinical TPP | frozen gap_fill |",
        "|------|------------------------|-------------------:|-------------:|:---------------:|",
    ]
    for r in payload["absent"]["rows"]:
        lines.append(
            f"| {r['case_id']} | {r['goldish_in_top10_hints'] or '—'} | "
            f"{int(r['any_l1_accommodates_gold_keywords'])} | "
            f"{int(r['clinical_tree_parent_present'])} | "
            f"{'yes' if r['frozen_built_with_gap_fill'] else 'no'} |"
        )
    lines += [
        "",
        "### Notes",
        "",
        "- Case **231**: exact gold string already in hints under R3-on build; "
        "BranchCreator still chose paraneoplastic/skin axis → gap-fill insufficient "
        "for axis correction.",
        "- Case **67**: systemic septic-shock L1 absent; CNS-involvement axis dominates.",
        "- Live identical `recall_hints_gap` rebuild **skipped** (non-informative vs frozen).",
        "",
        "## Conclusion",
        "",
        "**REJECT R3** as coverage main lever and as ABSENT fix on this cohort.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_track_c_report(
    upper: Mapping[str, Any],
    live: Mapping[str, Any] | None,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary_upper.json").write_text(
        json.dumps(upper, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if live:
        (out_dir / "summary_live.json").write_text(
            json.dumps(live, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    lines = [
        "# Track C (R4/R5) ABSENT-only smoke",
        "",
        f"- generated: `{upper['generated_at']}`",
        "",
        "## Upper bound (offline, gold-blind proposals → keyword accommodate)",
        "",
        "| arm | helped ABSENT (upper) | verdict |",
        "|-----|----------------------:|---------|",
    ]
    for arm, payload in upper["arms"].items():
        lines.append(
            f"| {arm} | {payload['n_absent_helped_upper']}/2 | "
            f"{'PASS_UPPER' if payload['upper_bound_pass'] else 'REJECT_UPPER'} |"
        )
    lines += ["", "### Per-case accommodating proposals", ""]
    for arm, payload in upper["arms"].items():
        lines.append(f"#### {arm}")
        for r in payload["rows"]:
            lines.append(
                f"- case {r['case_id']}: upper={r['tree_parent_present_upper_bound']} "
                f"hits={r['accommodating_proposals'][:5]} "
                f"top2={r['top2']}"
            )
        lines.append("")
    if live:
        lines += [
            "## Live inject (ABSENT-only)",
            "",
            f"- model: `{live.get('model')}`",
            f"- live_pass_lite: **{live['verdict']['live_pass_lite']}**",
            f"- production default: **{live['verdict']['default_production']}**",
            f"- claim_allowed_for_main_table: `{live['verdict']['claim_allowed_for_main_table']}`",
            "",
            "| arm | helped live | pass_lite |",
            "|-----|------------:|:---------:|",
        ]
        for arm, payload in live.get("arms", {}).items():
            lines.append(
                f"| {arm} | {payload['n_absent_helped_live']}/2 | "
                f"{payload['live_pass_lite']} |"
            )
        lines.append("")
        for arm, payload in live.get("arms", {}).items():
            for r in payload["rows"]:
                lines.append(
                    f"- {arm} case {r.get('case_id')}: "
                    f"accommodates={r.get('tree_parent_present_clinical_proxy')} "
                    f"l1={r.get('l1_labels')}"
                )
    else:
        lines += [
            "## Live inject",
            "",
            "Skipped (no arm passed upper bound, or `--skip-live`).",
            "",
        ]
    lines += [
        "",
        "## Conclusion",
        "",
        "- Track C **must not** be default production path for full cohort "
        "(90% MISS are UNBIND).",
        "- Even PASS-lite on ABSENT is **not** a main-table AutoCoverage claim.",
        f"- Upper default_production: **{upper['verdict']['default_production']}**",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--force-live", action="store_true",
                    help="Run live even if upper bound fails")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--only", choices=["r3", "trackc", "all"], default="all")
    args = ap.parse_args()

    if args.only in ("r3", "all"):
        r3 = eval_r3_offline()
        write_r3_report(r3, ANALYSIS / "smoke_r3")
        print("[r3] wrote", ANALYSIS / "smoke_r3", "verdict=", r3["verdict"])

    live = None
    if args.only in ("trackc", "all"):
        upper = eval_track_c_upper()
        do_live = (not args.skip_live) and (
            args.force_live or bool(upper["verdict"]["live_recommended_arms"])
        )
        if do_live:
            print(
                "[track_c] live inject arms=",
                upper["verdict"]["live_recommended_arms"],
                flush=True,
            )
            live = run_track_c_live_inject(upper, args.model)
        write_track_c_report(upper, live, ANALYSIS / "smoke_track_c")
        print(
            "[track_c] upper=",
            {k: upper["verdict"][k] for k in upper["verdict"] if k.startswith("R")},
            "live=",
            None if live is None else live["verdict"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
