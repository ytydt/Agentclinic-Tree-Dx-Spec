#!/usr/bin/env python3
"""R6 case covariates: deep_covariates + gold prevalence + modality demand."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import disagreement_census as dc
import r3_lib as r3
import r4_lib as r4
import r5_lib as r5
import r6_lib as r6
import trajectory_anatomy_lib as tal

OUT = r5.OUT / "mosaic_eval" / "r6_covariates.tsv"
OUT_JSON = r5.OUT / "mosaic_eval" / "r6_covariates_meta.json"

HISTO_RX = r3.HISTO_RX
IMAGING_RX = r3.IMAGING_RX
GENETICS_RX = re.compile(
    r"\b(genetic|mutation|variant|pathogenic|heterozygous|homozygous|"
    r"sequenc|PCR|FISH|karyotyp|BRCA|EGFR|KRIT1|PDGFRA|FIP1L1)\b",
    re.I,
)
PATHOLOGY_RX = re.compile(
    r"\b(histolog|biopsy|immunohisto|patholog|microscop|stain|"
    r"IHC|cytolog|frozen\s+section)\b",
    re.I,
)


def key_label(lab: str) -> str:
    return " ".join((lab or "").lower().split())


def build_prevalence() -> dict[str, int]:
    """Document frequency of proposed labels across CORPUS_ARMS (dev 400)."""
    from diag_slot_efficiency import CORPUS_ARMS, SLICES, load_arm

    prev: Counter = Counter()
    for log_ds in SLICES:
        for arm in CORPUS_ARMS:
            data = load_arm(log_ds, arm)
            for cid, info in data.items():
                seen = set()
                for lab in info.get("pool") or []:
                    k = key_label(lab)
                    if k and k not in seen:
                        prev[k] += 1
                        seen.add(k)
    return dict(prev)


def load_deep() -> dict[tuple[str, str, str], dict[str, str]]:
    path = r5.OUT / "deep_covariates" / "pooled.tsv"
    if not path.is_file():
        path = r5.OUT / "r4_covariates" / "features.tsv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return {
            (r["dataset"], r["slice"], r["case_id"]): r for r in csv.DictReader(fh)
        }


def load_vignette(dataset: str, slice_name: str, cid: str) -> str:
    # map slice to subset
    for table in (dc.DA_SLICES, dc.MCR_SLICES):
        if slice_name in table:
            subset = r5.ROOT / table[slice_name]["subset"]
            cases = tal.load_cases(
                str(subset.relative_to(r5.ROOT))
                if subset.is_relative_to(r5.ROOT)
                else str(subset)
            )
            # try several id forms
            for k in (cid, cid.zfill(3), cid.zfill(6), str(int(cid)) if cid.isdigit() else cid):
                if k in cases:
                    return str(cases[k].get("case_text") or cases[k].get("vignette") or "")
            # normalized_cases may key by full id
            for k, c in cases.items():
                if str(c.get("id") or k).endswith(cid) or str(k).endswith(cid):
                    return str(c.get("case_text") or "")
    return ""


def modality_demand(text: str) -> dict[str, Any]:
    return {
        "vig_has_pathology": int(bool(PATHOLOGY_RX.search(text or ""))),
        "vig_has_genetics": int(bool(GENETICS_RX.search(text or ""))),
        "vig_has_imaging": int(bool(IMAGING_RX.search(text or ""))),
        "vig_histo_hits": len(HISTO_RX.findall(text or "")),
        "pathology_or_genetics_needed": int(
            bool(PATHOLOGY_RX.search(text or "") or GENETICS_RX.search(text or ""))
        ),
    }


def main() -> int:
    gold = r5.load_gold()
    deep = load_deep()
    print("building prevalence…")
    prev = build_prevalence()
    # gold prevalence percentiles
    gold_prev_vals = []
    rows = []
    missing_deep = 0
    for (dkey, sl, cid), g in gold.items():
        base = dict(deep.get((dkey, sl, cid)) or {})
        if not base:
            missing_deep += 1
        gp = prev.get(key_label(g), 0)
        gold_prev_vals.append(gp)
        # vignette for modality (prefer cached deep fields if present)
        text = ""
        if not base.get("vig_chars"):
            try:
                text = load_vignette(dkey, sl, cid)
            except Exception:
                text = ""
        else:
            # still need text for genetics rx if not in deep
            try:
                text = load_vignette(dkey, sl, cid)
            except Exception:
                text = ""
        md = modality_demand(text)
        # near-gold crowd from deep or recompute for MCR
        n_near = base.get("n_option_near_pairs") or base.get("n_opts_near_gold") or ""
        max_j = base.get("max_distractor_gold_jaccard") or base.get("max_opt_gold_overlap") or ""
        row = {
            "dataset": dkey,
            "slice": sl,
            "case_id": cid,
            "gold": g,
            "gold_prevalence": gp,
            "gold_chars": base.get("gold_chars") or len(g),
            "gold_has_subtype": base.get("gold_has_subtype") or int(bool(r3.SUBTYPE_RX.search(g))),
            "gold_has_eponym": base.get("gold_has_eponym") or "",
            "gold_has_paren": base.get("gold_has_paren") or int("(" in g),
            "vig_chars": base.get("vig_chars") or len(text),
            "vig_words": base.get("vig_words") or len(text.split()),
            "vig_lab_dens": base.get("vig_lab_dens") or "",
            "vig_diff_dens": base.get("vig_diff_dens") or "",
            "vig_histo_dens": base.get("vig_histo_dens") or "",
            "vig_imaging_dens": base.get("vig_imaging_dens") or "",
            "n_option_near_pairs": n_near,
            "max_distractor_gold_jaccard": max_j,
            **md,
        }
        # keep useful deep extras
        for k in (
            "n_options",
            "has_pe_section",
            "has_tests_section",
            "journal_len",
            "title_len",
        ):
            if k in base:
                row[k] = base[k]
        rows.append(row)

    # percentile rank of gold prevalence
    sorted_prev = sorted(gold_prev_vals)
    def pct(v: int) -> float:
        if not sorted_prev:
            return 0.0
        # fraction strictly below
        lo = sum(1 for x in sorted_prev if x < v)
        return round(lo / len(sorted_prev), 4)

    for r in rows:
        r["gold_prevalence_pct"] = pct(int(r["gold_prevalence"]))
        r["gold_is_rare"] = int(r["gold_prevalence_pct"] <= 0.25)
        r["gold_is_common"] = int(r["gold_prevalence_pct"] >= 0.75)

    r4.write_tsv(OUT, rows)
    r6.write_json(
        OUT_JSON,
        {
            "n": len(rows),
            "missing_deep": missing_deep,
            "prevalence_labels": len(prev),
            "gold_prev_mean": round(sum(gold_prev_vals) / len(gold_prev_vals), 3)
            if gold_prev_vals
            else None,
            "pathology_or_genetics_rate": round(
                sum(int(r["pathology_or_genetics_needed"]) for r in rows) / len(rows), 4
            ),
        },
    )
    print(f"wrote {OUT} n={len(rows)} missing_deep={missing_deep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
