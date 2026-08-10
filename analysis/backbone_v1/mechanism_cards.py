"""Mechanism cards with full S4 rationale/rejected + cluster codes (zero LLM).

Full coverage for critical layers; stratified quota for all_miss_but_recalled.

Usage:
  PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1 \\
    python3 analysis/backbone_v1/mechanism_cards.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import disagreement_census as dc  # noqa: E402
import r3_lib as r3  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

OUT = r3.OUT_ROOT / "mechanism_cards"
TAX = r3.OUT_ROOT / "failure_taxonomy" / "pooled.tsv"
ALIGN = r3.OUT_ROOT / "candidate_alignment" / "pooled.tsv"

ALL_MISS_PER_CODE = 4


def load_tsv(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    out = {}
    for row in csv.DictReader(path.open(encoding="utf-8")):
        out[(row["dataset"], row["slice"], row["case_id"])] = row
    return out


def stable_sample(rows: list[dict], k: int) -> list[dict]:
    if len(rows) <= k:
        return list(rows)

    def key(r):
        s = f"{r['dataset']}|{r['slice']}|{r['case_id']}"
        return hashlib.md5(s.encode()).hexdigest()

    return sorted(rows, key=key)[:k]


def select_rows(census: list[dict], tax: dict) -> list[dict]:
    selected: list[dict] = []
    seen = set()

    def add(r: dict) -> None:
        key = (r["dataset"], r["slice"], r["case_id"])
        if key in seen:
            return
        seen.add(key)
        selected.append(r)

    # full critical layers
    for layer in (
        "base_win_rank",
        "base_win_recall",
        "e7_win_rank",
        "e7_win_recall",
    ):
        for r in census:
            if r.get("layer") == layer:
                # strip mapper_rescue for e7_win on DA if flagged
                t = tax.get((r["dataset"], r["slice"], r["case_id"])) or {}
                if layer.startswith("e7_win") and r3.truthy(t.get("e7_mapper_rescue")):
                    # still include but mark — plan says strip after peeling; include with flag
                    add(r)
                else:
                    add(r)

    # APHHM win/lose
    for r in census:
        la = r.get("layer_aphhm") or ""
        if la in ("aphhm_win", "aphhm_lose"):
            add(r)

    # all_miss stratified by fail code
    by_code: dict[str, list] = defaultdict(list)
    for r in census:
        if r.get("layer") != "all_miss_but_recalled":
            continue
        t = tax.get((r["dataset"], r["slice"], r["case_id"])) or {}
        by_code[t.get("e7_fail_code") or "unknown"].append(r)
    for code, rs in by_code.items():
        for r in stable_sample(rs, ALL_MISS_PER_CODE):
            add(r)

    return selected


def write_card(
    row: dict[str, str],
    tax: dict,
    align: dict,
) -> Path:
    dataset, slice_name, cid = row["dataset"], row["slice"], row["case_id"]
    gold = row.get("gold") or ""
    key = (dataset, slice_name, cid)
    t = tax.get(key) or {}
    a = align.get(key) or {}
    spec = lib.slice_spec(dataset, slice_name)
    case = lib.load_cases(spec["subset"]).get(cid) or {}
    text = lib.vignette_text(case)
    opts = lib.da_options(case) if dataset == "da" else {}

    e7_dir = lib.run_dir(dataset, slice_name, "e7")
    bb = r3.extract_backbone(e7_dir, cid) if e7_dir else {}
    if bb:
        r3.fill_s2_rank(bb, gold)

    layer = row.get("layer") or row.get("layer_aphhm") or "other"
    fname = f"{dataset}_{slice_name}_{cid}.md"
    path = OUT / fname

    lines = [
        f"# {dataset.upper()} / {slice_name} / case {cid}",
        "",
        f"- **gold**: {gold}",
        f"- **layer**: `{layer}` · **layer_aphhm**: `{row.get('layer_aphhm') or ''}`",
        f"- **correct**: e7={row.get('e7_correct')} v0={row.get('v0_correct')} "
        f"B06={row.get('B06_correct')} B07={row.get('B07_correct')} "
        f"B01={row.get('B01_correct')} APHHM={row.get('APHHM_correct')}",
        f"- **e7_locus**: `{t.get('e7_locus')}` · **e7_fail_code**: `{t.get('e7_fail_code')}`",
        f"- **mapper_rescue**: {t.get('e7_mapper_rescue')}",
        f"- **alignment**: e7_s3_gold={a.get('e7_s3_gold')} e7_champ_cluster={a.get('e7_champ_cluster')} "
        f"B06_sup_gold={a.get('B06_sup_gold')} B07_diag_gold={a.get('B07_diag_gold')} "
        f"same_cluster_flip={a.get('aligned_same_cluster_rank_flip')} "
        f"true_entrance={a.get('aligned_true_entrance_gap')}",
        f"- **APHHM**: locus=`{t.get('APHHM_locus')}` code=`{t.get('APHHM_fail_code')}` "
        f"prune_e7_ok={t.get('aphhm_prune_e7_ok')}",
        "",
        "## Vignette",
        text[:1200] + ("…" if len(text) > 1200 else ""),
        "",
    ]
    if opts:
        lines.append("## Options")
        for k, v in opts.items():
            mark = " **←gold**" if gold and dc.match(v, gold) else ""
            lines.append(f"- {k}: {v}{mark}")
        lines.append("")

    lines += ["## Backbone e7", ""]
    if bb:
        lines.append(f"- S2 n={len(bb.get('s2') or [])} gold_rank={bb.get('s2_rank_gold')}")
        s2_cl = r3.count_clusters(bb.get("s2") or [], gold)
        lines.append(f"  - clusters: gold={s2_cl['gold']} near={s2_cl['near']} other={s2_cl['other']}")
        lines.append(f"- S3 shortlist ({len(bb.get('s3') or [])}):")
        for lab in bb.get("s3") or []:
            lines.append(f"  - [{r3.cluster_of(lab, gold)}] {lab}")
        for w in bb.get("s3_why") or []:
            lines.append(f"    - why_kept({w.get('label')}): {w.get('why_kept')}")
        lines.append(
            f"- S4 champion: **{bb.get('champion')}** "
            f"cluster={r3.cluster_of(bb.get('champion') or '', gold)} "
            f"jaccard={r3.token_jaccard(bb.get('champion') or '', gold):.2f}"
        )
        lines.append(f"- S4 rationale: {bb.get('rationale') or ''}")
        lines.append("- S4 rejected:")
        for r in bb.get("rejected") or []:
            lines.append(
                f"  - [{r3.cluster_of(r.get('label') or '', gold)}] "
                f"{r.get('label')}: {r.get('why')}"
            )
    else:
        lines.append("_missing stages_")
    lines.append("")

    # baselines
    for arm, extractor in (
        ("B06", r3.extract_b06),
        ("B07", r3.extract_b07),
        ("B01", r3.extract_b01),
    ):
        rd = lib.run_dir(dataset, slice_name, arm)
        lines.append(f"## {arm} (code=`{t.get(arm + '_fail_code')}` locus=`{t.get(arm + '_locus')}`)")
        if not rd or row.get(f"{arm}_correct") in ("", None) and arm == "B01":
            lines += ["_na_", ""]
            continue
        if not rd:
            lines += ["_missing_", ""]
            continue
        tr = r3.get_trace(rd, cid)
        preds = r3.get_preds(rd, cid)
        if arm == "B06":
            ex = extractor(tr, preds)
            lines.append(f"- supervisor: {ex.get('supervisor')}")
            lines.append(
                f"  clusters: {r3.count_clusters(ex.get('supervisor') or [], gold)}"
            )
            lines.append(f"- discussion labels (n={len(ex.get('discussion') or [])}): "
                         f"{(ex.get('discussion') or [])[:8]}")
            lines.append(f"- votes={ex.get('votes')} turns={ex.get('n_turns')}")
        elif arm == "B07":
            ex = extractor(tr, preds)
            lines.append(f"- draft: {ex.get('draft')}")
            lines.append(f"- diagnose: {ex.get('diagnose')}")
            lines.append(f"- queries: {ex.get('queries')}")
        else:
            ex = extractor(tr, preds)
            lines.append(f"- top2: {ex.get('top2')}")
            lines.append(f"- queries: {ex.get('queries')}")
            lines.append(f"- n_chunks={ex.get('n_chunks')}")
        lines.append("")

    aph = lib.run_dir(dataset, slice_name, "APHHM")
    lines.append("## APHHM")
    if aph and row.get("APHHM_correct") not in ("", None):
        ex = r3.extract_aphhm(aph, cid)
        lines.append(f"- tree_n={ex['tree_n']} final_n={ex['final_n']}")
        lines.append(f"- final: {ex.get('final')}")
        lines.append(
            f"- tree gold_cluster_n={r3.count_clusters(ex.get('leaves') or [], gold)['gold']} "
            f"final gold={r3.count_clusters(ex.get('final') or [], gold)['gold'] > 0}"
        )
    else:
        lines.append("_na_")
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    census = lib.load_census_rows()
    tax = load_tsv(TAX)
    align = load_tsv(ALIGN)
    selected = select_rows(census, tax)
    OUT.mkdir(parents=True, exist_ok=True)
    # clear old cards? keep and overwrite by name
    index_rows = []
    for r in selected:
        p = write_card(r, tax, align)
        t = tax.get((r["dataset"], r["slice"], r["case_id"])) or {}
        index_rows.append(
            {
                "dataset": r["dataset"],
                "slice": r["slice"],
                "case_id": r["case_id"],
                "layer": r.get("layer") or "",
                "layer_aphhm": r.get("layer_aphhm") or "",
                "gold": r.get("gold") or "",
                "e7_fail_code": t.get("e7_fail_code") or "",
                "e7_locus": t.get("e7_locus") or "",
                "file": p.name,
            }
        )
    r3.write_tsv(OUT / "tags.tsv", index_rows)

    # index.md
    by_layer: dict[str, list] = defaultdict(list)
    for ix in index_rows:
        key = ix["layer"] or ix["layer_aphhm"] or "other"
        by_layer[key].append(ix)
    lines = [f"# Mechanism cards (R3)", "", f"n_cards={len(index_rows)}", ""]
    for layer, items in sorted(by_layer.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"## {layer} (n={len(items)})")
        for ix in items:
            lines.append(
                f"- [{ix['dataset']}/{ix['slice']}/{ix['case_id']}]({ix['file']}) "
                f"e7=`{ix['e7_fail_code']}` gold={ix['gold'][:60]}"
            )
        lines.append("")
    (OUT / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"mechanism_cards n={len(index_rows)} -> {OUT}")
    for layer, items in sorted(by_layer.items(), key=lambda kv: -len(kv[1])):
        print(f"  {layer}: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
