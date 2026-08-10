#!/usr/bin/env python3
"""Extract per-(arm,case) internal mechanism variables for deep arms."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import r4_lib as r4
import r5_lib as r5
import r6_lib as r6
import trajectory_anatomy_lib as tal
import disagreement_census as dc

OUT = r5.OUT / "mosaic_eval" / "r6_mechvars.tsv"
OUT_JSON = r5.OUT / "mosaic_eval" / "r6_mechvars_summary.json"

DEEP = list(r6.DEEP_ARMS)


def vignette_map() -> dict[tuple[str, str, str], str]:
    out = {}
    for log_ds, dkey, sl in r5.SLICES:
        for table in (dc.DA_SLICES, dc.MCR_SLICES):
            if sl not in table:
                continue
            subset = r5.ROOT / table[sl]["subset"]
            try:
                rel = str(subset.relative_to(r5.ROOT))
            except ValueError:
                rel = str(subset)
            try:
                cases = tal.load_cases(rel)
            except Exception:
                continue
            for k, c in cases.items():
                cid = str(c.get("id") or k)
                # normalize to source_id style used in gold
                if "__" in cid:
                    cid = cid.split("__")[-1].lstrip("0") or "0"
                else:
                    cid = cid.lstrip("0") or cid
                text = str(c.get("case_text") or c.get("vignette") or "")
                out[(dkey, sl, cid)] = text
                # also store zero-stripped variants
                if cid.isdigit():
                    out[(dkey, sl, str(int(cid)))] = text
    return out


def flatten(rec: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested ledger dict for TSV."""
    out = {}
    for k, v in rec.items():
        if k == "ledger" and isinstance(v, dict):
            out["n_ledger_cells"] = v.get("n_ledger_cells")
            out["gold_veto_n"] = len(v.get("gold_vetoes") or [])
            out["gold_score_ledger"] = v.get("gold_score")
            out["champ_score_ledger"] = v.get("champ_score")
            out["gold_comp_evidence"] = v.get("gold_comp_evidence")
            out["champ_comp_evidence"] = v.get("champ_comp_evidence")
            out["gold_comp_axis_bias"] = v.get("gold_comp_axis_bias")
            out["champ_comp_axis_bias"] = v.get("champ_comp_axis_bias")
            out["gold_comp_n_admitted"] = v.get("gold_comp_n_admitted")
            out["champ_comp_n_admitted"] = v.get("champ_comp_n_admitted")
            vc = v.get("veto_counts") or {}
            for vr, cnt in vc.items():
                out[f"veto_{vr}"] = cnt
            out["ledger_final_inversion"] = v.get("ledger_final_inversion")
            out["unexplained_disappearance"] = v.get("unexplained_disappearance")
            out["verifier_reason"] = v.get("verifier_reason")
        elif isinstance(v, (list, dict)):
            out[k] = str(v)[:500]
        else:
            out[k] = v
    return out


def main() -> int:
    gold = r5.load_gold()
    print("loading vignettes…")
    vig = vignette_map()
    rows = []
    for log_ds, dkey, sl in r5.SLICES:
        for arm in DEEP:
            if arm in r5.DEV_ONLY and sl.endswith("200b"):
                continue
            if r5.run_dir(log_ds, arm) is None:
                continue
            cids = [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]
            print(f"  {log_ds} {arm} n={len(cids)}")
            for cid in cids:
                g = gold[(dkey, sl, cid)]
                text = vig.get((dkey, sl, cid)) or vig.get(
                    (dkey, sl, str(int(cid)) if cid.isdigit() else cid)
                ) or ""
                rec = r6.extract_mechvars(log_ds, arm, cid, g, text)
                flat = flatten(rec)
                flat.update(
                    {"dataset": dkey, "slice": sl, "case_id": cid, "gold": g}
                )
                rows.append(flat)
    r4.write_tsv(OUT, rows)

    # summaries
    summary: dict[str, Any] = {}
    for arm in DEEP:
        rs = [r for r in rows if r["arm"] == arm and r.get("raw_available")]
        def mean(key):
            xs = [
                float(r[key])
                for r in rs
                if r.get(key) not in ("", None) and str(r.get(key)) not in ("None",)
            ]
            return round(sum(xs) / len(xs), 4) if xs else None

        block = {
            "n": len(rs),
            "chain": mean("chain_correct"),
            "gold_disc": mean("gold_disc"),
            "champ_disc": mean("champ_disc"),
            "gold_span_verbatim_rate": mean("gold_span_verbatim_rate"),
            "top_margin": mean("top_margin"),
            "unexplained_n": mean("unexplained_n"),
            "generator_jaccard": mean("generator_jaccard"),
            "score_gap": mean("score_gap_champ_minus_gold"),
            "gold_rejected_rate": mean("gold_rejected")
            if any(r.get("gold_rejected") not in ("", None) for r in rs)
            else None,
            "pool_has_gold": mean("pool_has_gold"),
            "n_facts": mean("n_facts"),
            "has_pathology_fact": mean("has_pathology_fact"),
        }
        # decision_loss subset disc
        dl = [
            r
            for r in rs
            if r.get("pool_has_gold") in (1, "1")
            and r.get("chain_correct") in (0, "0")
        ]
        block["decision_loss_n"] = len(dl)
        block["decision_loss_gold_disc"] = (
            round(
                sum(float(r["gold_disc"]) for r in dl if r.get("gold_disc") not in ("", None))
                / max(1, sum(1 for r in dl if r.get("gold_disc") not in ("", None))),
                4,
            )
            if dl
            else None
        )
        if arm in ("multistance",):
            from collections import Counter

            block["ms_loss_round"] = dict(
                Counter(r.get("ms_loss_round") or "na" for r in rs)
            )
        if arm == "aphhm_c_v1":
            block["mean_ledger_cells"] = mean("n_ledger_cells")
            block["gold_veto_rate"] = mean("gold_veto_n")
        summary[arm] = block
        print(arm, block)
    r6.write_json(OUT_JSON, summary)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
