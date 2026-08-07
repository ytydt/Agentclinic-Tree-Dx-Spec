#!/usr/bin/env python3
"""T1-03 stage hazards + T1-05 counterfactual repair upper bounds (CRV).

Gold-survival funnel on the deployed MCR / OX / DA trees:

  S1  gold in some L1 family
  S2  gold among L2 leaves
  S3  gold survives per-family cap (posterior>0 and in parent.children)
  S4  gold in arbiter top-5          (pre_compat_joint)
  S5  gold survives compat route    (case_results final_ranking_labels)
  S6  gold in emitted top-K         (eval_projection)
  S7  judge credits a hit           (case_scores / judge cache)

h_s = (N_{s-1} - N_s) / N_{s-1} with Wilson CI.

CRV (deterministic stages only): for each stage, force gold through that
stage and propagate with the observed downstream path; report Acc@1 gain.

Zero LLM calls (lexical gold match via leaf_match_score ≥ 0.7).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from mapper_bind_repair import leaf_match_score  # noqa: E402
from transfer_eval import io_gold  # noqa: E402

OUT_DIR = ROOT / "analysis" / "tier1_1a_v1"
MATCH_THR = 0.7

COHORTS = {
    "mcr_v1": {
        "run": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1",
        "parquet": ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet",
        "dataset": "medcasereasoning",
        "proj": "eval_projection_compat",
        "scores": "official_eval_llm_compat",
    },
    "ox_hot": {
        "run": ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1",
        "parquet": ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet",
        "dataset": "open_xddx",
        "proj": "eval_projection_closed_live_mac",
        "scores": "official_eval_llm_closed_live_mac",
    },
    "da_compat": {
        "run": ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1",
        "parquet": None,  # DA gold from case fixtures / option text
        "dataset": "diagnosisarena",
        "proj": None,
        "scores": None,
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def wilson_ci(k: int, n: int, z: float = 1.96) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def label_hit(lab: str, gold: str) -> bool:
    if not lab or not gold:
        return False
    try:
        return float(leaf_match_score(lab, gold)) >= MATCH_THR
    except Exception:
        return lab.strip().lower() == gold.strip().lower()


def any_hit(labels: Sequence[str], gold: str) -> bool:
    return any(label_hit(str(x), gold) for x in labels if str(x).strip())


def load_tree(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def gold_labels_from_map(gold_map: Mapping[str, Any], cid: str, dataset: str) -> list[str]:
    g = gold_map.get(cid) or gold_map.get(str(cid))
    if g is None:
        return []
    if isinstance(g, Mapping):
        if dataset == "open_xddx":
            labs = list(g.get("ddx_set") or g.get("gold_ddx_labels") or [])
            if labs:
                return [str(x).strip() for x in labs if str(x).strip()]
            pg = str(g.get("proxy_gold") or g.get("final_diagnosis") or "").strip()
            return [pg] if pg else []
        fd = str(g.get("final_diagnosis") or "").strip()
        return [fd] if fd else []
    s = str(g).strip()
    return [s] if s else []


def any_gold_hit(labels: Sequence[str], golds: Sequence[str]) -> bool:
    return any(label_hit(str(lab), g) for lab in labels if str(lab).strip() for g in golds)


def stage_flags_for_case(
    *,
    cid: str,
    golds: Sequence[str],
    ann: Path,
    proj_subdir: Optional[str],
    scores_subdir: Optional[str],
) -> dict[str, Any]:
    tree_p = ann / "shared_trees" / f"{cid}.json"
    if not tree_p.is_file():
        return {"ok": False, "reason": "no_tree"}
    doc = load_tree(tree_p)
    br = (doc.get("state") or {}).get("branches") or {}
    l1 = {
        k: v
        for k, v in br.items()
        if int(v.get("level") or 0) == 1
        or (not str(v.get("parent") or "").strip() and int(v.get("level") or 0) != 2)
    }
    l2 = {k: v for k, v in br.items() if int(v.get("level") or 0) == 2}

    s1 = any(
        any_gold_hit([str(v.get("label") or "")], golds) for v in l1.values()
    )
    gold_leaves = [
        (k, v)
        for k, v in l2.items()
        if any_gold_hit([str(v.get("label") or "")], golds)
    ]
    s2 = bool(gold_leaves)
    if s2:
        s1 = True

    s3 = False
    for lid, leaf in gold_leaves:
        post = float(leaf.get("posterior") or 0.0)
        parent_id = str(leaf.get("parent") or "")
        parent = br.get(parent_id) or {}
        kids = [str(x) for x in (parent.get("children") or [])]
        if post > 0 and (not kids or lid in kids):
            s3 = True
            break
        if post > 0 and not kids:
            s3 = True
            break

    s4 = False
    pc = ann / "pre_compat_joint" / f"{cid}.json"
    if pc.is_file():
        pdoc = json.loads(pc.read_text(encoding="utf-8"))
        labs = list(
            (pdoc.get("pre_compat") or {}).get("final_ranking_labels")
            or pdoc.get("final_ranking_labels")
            or []
        )
        flat = []
        for x in labs:
            if isinstance(x, Mapping):
                flat.append(str(x.get("label") or ""))
            else:
                flat.append(str(x))
        s4 = any_gold_hit(flat, golds)
    else:
        # OX hot runs often omit pre_compat_joint; fall back to any arbiter-side
        # ranking dump on case_results (pre_compat labels, else final_ranking).
        cr = ann / "case_results" / f"{cid}.json"
        if cr.is_file():
            cdoc = json.loads(cr.read_text(encoding="utf-8"))
            l2 = cdoc.get("l2") or {}
            labs = (
                l2.get("pre_compat_final_ranking_labels")
                or l2.get("joint_final_ranking_labels")
                or l2.get("final_ranking_labels")
                or []
            )
            flat = [
                str(x.get("label") if isinstance(x, Mapping) else x) for x in labs
            ]
            s4 = any_gold_hit(flat, golds)

    s5 = False
    cr = ann / "case_results" / f"{cid}.json"
    if cr.is_file():
        cdoc = json.loads(cr.read_text(encoding="utf-8"))
        labs = (cdoc.get("l2") or {}).get("final_ranking_labels") or []
        flat = [str(x.get("label") if isinstance(x, Mapping) else x) for x in labs]
        s5 = any_gold_hit(flat, golds)

    s6 = False
    if proj_subdir:
        pp = ann / proj_subdir / f"{cid}.json"
        if not pp.is_file():
            # OX closed_live may use different subdir naming
            for alt in ann.glob(f"eval_projection*/{cid}.json"):
                pp = alt
                break
        if pp.is_file():
            pdoc = json.loads(pp.read_text(encoding="utf-8"))
            rows = pdoc.get("pred_ddx") or []
            flat = [str(r.get("label") or "") for r in rows]
            pd = str(pdoc.get("pred_diagnosis") or "").strip()
            s6 = any_gold_hit(flat + ([pd] if pd else []), golds)

    s7 = False
    if scores_subdir:
        sp = ann / scores_subdir / "case_scores" / f"{cid}.json"
        if sp.is_file():
            sdoc = json.loads(sp.read_text(encoding="utf-8"))
            if "diagnostic_hit" in sdoc:
                s7 = bool(sdoc.get("diagnostic_hit"))
            elif "diagnostic" in sdoc and isinstance(sdoc["diagnostic"], Mapping):
                # OX micro: credit if any gold matched (tp>0)
                s7 = int(sdoc["diagnostic"].get("tp") or 0) > 0
            elif "option_top1" in sdoc:
                s7 = bool(sdoc.get("option_top1"))
            else:
                s7 = s6

    raw = {
        "s1_l1": s1,
        "s2_leaf": s2,
        "s3_cap": s3,
        "s4_arbiter": s4,
        "s5_compat": s5,
        "s6_emitted": s6,
        "s7_credited": s7,
    }
    nested = {}
    alive = True
    order = [
        "s1_l1",
        "s2_leaf",
        "s3_cap",
        "s4_arbiter",
        "s5_compat",
        "s6_emitted",
        "s7_credited",
    ]
    for key in order:
        alive = alive and bool(raw[key])
        nested[key] = alive
    return {"ok": True, "raw": raw, "nested": nested, "golds": list(golds)}


def hazards_from_flags(rows: list[dict[str, Any]]) -> dict[str, Any]:
    order = [
        "s1_l1",
        "s2_leaf",
        "s3_cap",
        "s4_arbiter",
        "s5_compat",
        "s6_emitted",
        "s7_credited",
    ]
    n0 = len(rows)
    # N_s = count nested True at stage s; N_0 = n0 (all cases enter)
    Ns = [n0]
    for key in order:
        Ns.append(sum(1 for r in rows if r["nested"][key]))
    stages = []
    labels = [
        "enter→L1",
        "L1→leaf",
        "leaf→cap",
        "cap→arbiter",
        "arbiter→compat",
        "compat→emitted",
        "emitted→credited",
    ]
    for i, lab in enumerate(labels):
        prev, cur = Ns[i], Ns[i + 1]
        dropped = prev - cur
        h = (dropped / prev) if prev else 0.0
        stages.append(
            {
                "stage": lab,
                "key": order[i],
                "N_prev": prev,
                "N_cur": cur,
                "dropped": dropped,
                "hazard": h,
                "hazard_wilson95": wilson_ci(dropped, prev) if prev else [0.0, 0.0],
                "survival": (cur / n0) if n0 else 0.0,
            }
        )
    return {"n_cases": n0, "N": Ns, "stages": stages}


def crv_deterministic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Upper-bound Acc@1 gain if we could force gold through a stage.

    Observed Acc@1 proxy = nested s7 (or s6 if no judge).
    For each stage s, among cases that fail at s but would have succeeded
    earlier, the oracle upper bound is: set nested[s]=True and keep observed
    downstream success rate conditional on reaching s among cases that
    actually reached s. Simpler reportable CRV:
      CRV_s = (n_fail_at_s / n) * P(credit | reached s)
    i.e. if all failures at s were repaired and then followed the success
    rate of cases that actually passed s.
    """
    order = [
        "s1_l1",
        "s2_leaf",
        "s3_cap",
        "s4_arbiter",
        "s5_compat",
        "s6_emitted",
        "s7_credited",
    ]
    n = len(rows)
    if n == 0:
        return {}
    observed = sum(1 for r in rows if r["nested"]["s7_credited"]) / n
    # Prefer s7; if all False due to missing scores, use s6
    if observed == 0 and any(r["nested"]["s6_emitted"] for r in rows):
        credit_key = "s6_emitted"
        observed = sum(1 for r in rows if r["nested"][credit_key]) / n
    else:
        credit_key = "s7_credited"

    out = {"observed_credit_rate": observed, "credit_key": credit_key, "stages": {}}
    # Deterministic stages: cap, compat, emitted (arbiter/judge are stochastic)
    det = {"s3_cap", "s5_compat", "s6_emitted"}
    for i, key in enumerate(order):
        # fail at this stage: nested[prev] True (or i==0 enter) and nested[key] False
        if i == 0:
            fail_ids = [r for r in rows if not r["nested"][key]]
            reached_prev = rows
        else:
            prev = order[i - 1]
            fail_ids = [
                r for r in rows if r["nested"][prev] and not r["nested"][key]
            ]
            reached_prev = [r for r in rows if r["nested"][prev]]
        passed = [r for r in rows if r["nested"][key]]
        p_credit_given_pass = (
            sum(1 for r in passed if r["nested"][credit_key]) / len(passed)
            if passed
            else 0.0
        )
        crv = (len(fail_ids) / n) * p_credit_given_pass
        out["stages"][key] = {
            "n_fail_at_stage": len(fail_ids),
            "n_reached_prev": len(reached_prev),
            "n_passed": len(passed),
            "p_credit_given_pass": p_credit_given_pass,
            "crv_acc_upper": crv,
            "deterministic": key in det,
            "note": (
                "oracle upper bound under observed conditional credit rate"
                if key in det
                else "stochastic stage — upper bound only under strong assumptions"
            ),
        }
    return out


def run_cohort(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    run = Path(cfg["run"])
    ann = run / "annotate" if (run / "annotate").is_dir() else run
    trees = ann / "shared_trees"
    if not trees.is_dir():
        return {"cohort": name, "ok": False, "reason": f"no trees at {trees}"}

    ids = sorted(p.stem for p in trees.glob("*.json"))
    gold_map: dict[str, Any] = {}
    if cfg.get("parquet") and Path(cfg["parquet"]).is_file():
        try:
            gold_map = io_gold.load_gold(
                cfg["dataset"], Path(cfg["parquet"]), case_ids=ids
            )
        except Exception as exc:  # noqa: BLE001
            return {"cohort": name, "ok": False, "reason": f"gold load: {exc}"}

    rows = []
    missing_gold = 0
    for cid in ids:
        golds = gold_labels_from_map(gold_map, cid, cfg["dataset"])
        if not golds and cfg["dataset"] == "diagnosisarena":
            cr = ann / "case_results" / f"{cid}.json"
            if cr.is_file():
                cdoc = json.loads(cr.read_text(encoding="utf-8"))
                g = str(
                    cdoc.get("gold_diagnosis")
                    or cdoc.get("final_diagnosis")
                    or ""
                ).strip()
                if g:
                    golds = [g]
        if not golds:
            missing_gold += 1
            continue
        flags = stage_flags_for_case(
            cid=cid,
            golds=golds,
            ann=ann,
            proj_subdir=cfg.get("proj"),
            scores_subdir=cfg.get("scores"),
        )
        if flags.get("ok"):
            rows.append(flags)

    haz = hazards_from_flags(rows)
    crv = crv_deterministic(rows)
    return {
        "cohort": name,
        "ok": True,
        "n_trees": len(ids),
        "n_scored": len(rows),
        "n_missing_gold": missing_gold,
        "match_threshold": MATCH_THR,
        "hazards": haz,
        "crv": crv,
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# T1-03 Stage hazards + T1-05 CRV",
        "",
        f"Created: {report['created_at']}",
        f"Lexical match threshold: {MATCH_THR}",
        "",
    ]
    for c in report["cohorts"]:
        lines.append(f"## {c['cohort']}")
        if not c.get("ok"):
            lines.append(f"FAILED: {c.get('reason')}")
            lines.append("")
            continue
        lines.append(f"n_scored={c['n_scored']} / trees={c['n_trees']}")
        lines.append("")
        lines.append("| stage | N_prev | N_cur | dropped | h | Wilson95 | survival |")
        lines.append("|---|---:|---:|---:|---:|---|---:|")
        for s in c["hazards"]["stages"]:
            w = s["hazard_wilson95"]
            lines.append(
                f"| {s['stage']} | {s['N_prev']} | {s['N_cur']} | {s['dropped']} | "
                f"{s['hazard']:.3f} | [{w[0]:.3f},{w[1]:.3f}] | {s['survival']:.3f} |"
            )
        lines.append("")
        lines.append("### CRV (Acc upper bound if stage repaired)")
        lines.append("")
        crv = c.get("crv") or {}
        lines.append(
            f"Observed credit rate ({crv.get('credit_key')}): "
            f"{crv.get('observed_credit_rate')}"
        )
        lines.append("")
        lines.append("| stage | n_fail | p(credit\\|pass) | CRV | deterministic? |")
        lines.append("|---|---:|---:|---:|---|")
        for key, stg in (crv.get("stages") or {}).items():
            lines.append(
                f"| {key} | {stg['n_fail_at_stage']} | {stg['p_credit_given_pass']:.3f} | "
                f"{stg['crv_acc_upper']:.3f} | {stg['deterministic']} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument(
        "--cohorts",
        default="mcr_v1,ox_hot",
        help="Comma-separated cohort keys (da_compat optional)",
    )
    args = ap.parse_args()
    keys = [x.strip() for x in args.cohorts.split(",") if x.strip()]
    cohorts = []
    for k in keys:
        if k not in COHORTS:
            print(f"[hazard] unknown cohort {k}", flush=True)
            continue
        print(f"[hazard] {k} ...", flush=True)
        cohorts.append(run_cohort(k, COHORTS[k]))

    report = {
        "schema_version": "tier1_stage_hazard_v1",
        "created_at": _utc(),
        "cohorts": cohorts,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    jp = args.out_dir / "stage_hazard_crv.json"
    jp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out_dir / "stage_hazard_crv.md").write_text(render_md(report), encoding="utf-8")
    print(f"[hazard] wrote {jp}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
