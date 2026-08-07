"""Stratified case-trajectory cards from disagreement_census TSVs.

Samples cases by layer (e7_win_recall / e7_win_rank / base_win_* /
all_miss_but_recalled / aphhm_*), fills trajectory summaries from
case_stages / trace.jsonl / APHHM case_results, and writes markdown cards
plus a tags.tsv with auto-suggested mechanism labels.

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 analysis/backbone_v1/case_trajectory_cards.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
CENSUS = ROOT / "analysis" / "backbone_v1" / "disagreement_census"
OUT_CARDS = ROOT / "analysis" / "backbone_v1" / "case_cards"
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc  # noqa: E402

# per (dataset, layer) sample size
PER_CELL = 6
APHHM_PER = 6
SEED = 7

MECH_VOCAB = (
    "entrance_breadth",
    "kb_or_rag_hit",
    "multiagent_vote",
    "s3_s4_ranking",
    "aphhm_prune_loss",
    "mapper_rescue",
    "near_synonym_judge",
    "hard_miss",
)


def stable_sample(rows: list[dict], k: int, seed: int) -> list[dict]:
    if len(rows) <= k:
        return list(rows)
    rng = random.Random(seed)
    # deterministic shuffle by case key
    keyed = sorted(
        rows,
        key=lambda r: hashlib.md5(
            f"{r['dataset']}:{r['slice']}:{r['case_id']}".encode()
        ).hexdigest(),
    )
    rng.shuffle(keyed)
    return keyed[:k]


def slice_spec(dataset: str, slice_name: str) -> dict:
    if dataset == "da":
        return dc.DA_SLICES[slice_name]
    return dc.MCR_SLICES[slice_name]


def load_trace_for(run_dir: Path, cid: str) -> Optional[dict]:
    traces = dc.load_traces(run_dir)
    return traces.get(cid)


def backbone_trace_blurb(run_dir: Path, cid: str, gold: str) -> str:
    doc = dc.load_backbone_stage(run_dir, cid)
    if not doc:
        return "_missing case_stages_"
    st = doc.get("stages") or {}
    s2 = st.get("s2") or {}
    diffs = [str(x) for x in (s2.get("differentials") or [])]
    s3 = [str(x) for x in ((st.get("s3") or {}).get("shortlist") or [])]
    champ = str((st.get("s4") or {}).get("champion") or doc.get("champion") or "")
    mode = s2.get("s2_mode")
    k = s2.get("s2_k")
    s2_hit = dc.any_match(diffs, gold) if gold else None
    s3_hit = dc.any_match(s3, gold) if gold else None
    s4_hit = dc.match(champ, gold) if (champ and gold) else None
    lines = [
        f"- S2 pool n={len(diffs)} mode={mode} k={k}; gold_in_s2={s2_hit}",
        f"- S3 shortlist ({len(s3)}): {', '.join(s3[:5])}{'...' if len(s3)>5 else ''}; gold_in_s3={s3_hit}",
        f"- S4 champion: **{champ}**; gold_match={s4_hit}",
    ]
    if s2_hit and diffs:
        # show matching differential labels
        hits = [d for d in diffs if dc.match(d, gold)]
        lines.append(f"- S2 gold matches: {', '.join(hits[:5])}")
    return "\n".join(lines)


def baseline_trace_blurb(arm: str, run_dir: Path, cid: str, gold: str, pred: str) -> str:
    tr = load_trace_for(run_dir, cid) or {}
    lines = [f"- pred: {pred}"]
    if arm == "B06":
        sup = tr.get("supervisor") or {}
        top2 = sup.get("top2_diagnoses") or []
        votes = sup.get("votes")
        disc = tr.get("discussion") or []
        lines.append(f"- method=MAC; discussion_turns={len(disc)}; votes={votes}")
        if top2:
            labels = [
                t.get("diagnosis") if isinstance(t, dict) else str(t) for t in top2[:2]
            ]
            lines.append(f"- supervisor top2: {labels}")
    elif arm == "B07":
        lines.append(
            f"- method=MEDDx; queries={len(tr.get('queries') or [])}; "
            f"has_refine={bool(tr.get('refine'))}; draft_n={len(tr.get('draft') or [])}"
        )
        diag = (tr.get("diagnose") or {}).get("top2_diagnoses") or []
        if diag:
            labels = [
                t.get("diagnosis") if isinstance(t, dict) else str(t) for t in diag[:2]
            ]
            lines.append(f"- diagnose top2: {labels}")
    elif arm == "B01":
        ret = tr.get("retrieval") or {}
        chunks = ret.get("served_chunks") or ret.get("chunks") or []
        nch = chunks if isinstance(chunks, int) else len(chunks or [])
        lines.append(f"- method=CoT-RAG; retrieval_chunks={nch}")
        lines.append(f"- top2 raw: {tr.get('top2') or tr.get('ordered')}")
    # cand recall
    cands = []
    preds = dc.load_jsonl_preds(run_dir)
    cands = preds.get(cid) or preds.get(dc._norm_cid_from_pred_key(cid)) or []
    if not cands and pred:
        cands = [p.strip() for p in pred.split(";") if p.strip()]
    lines.append(f"- cand_recall={dc.any_match(cands, gold) if gold else None}")
    return "\n".join(lines)


def aphhm_trace_blurb(annotate_dir: Path, cid: str, gold: str) -> str:
    af = dc.aphhm_features(annotate_dir, cid, gold)
    cr = annotate_dir / "case_results" / f"{cid}.json"
    final = []
    if cr.is_file():
        doc = json.loads(cr.read_text())
        final = [
            str(x.get("label"))
            for x in ((doc.get("l2") or {}).get("final_ranking_labels") or [])
        ]
    lines = [
        f"- tree_n={af['tree_n']} tree_recall={af['tree_recall']}",
        f"- final_n={af['final_n']} final_recall={af['final_recall']} "
        f"fail_mode={af['fail_mode']}",
        f"- final_ranking: {', '.join(final[:5])}",
    ]
    if af.get("human_at1") is not None:
        lines.append(f"- human_adjudication.at1={af['human_at1']}")
    return "\n".join(lines)


def suggest_tags(row: dict, dataset: str) -> list[str]:
    tags: list[str] = []
    layer = row.get("layer") or ""
    layer_a = row.get("layer_aphhm") or ""
    if layer == "e7_win_recall":
        # e7 s2 larger?
        try:
            if int(row.get("e7_s2_n") or 0) > int(row.get("v0_s2_n") or 0):
                tags.append("entrance_breadth")
        except ValueError:
            tags.append("entrance_breadth")
    if layer in ("e7_win_rank", "base_win_rank"):
        tags.append("s3_s4_ranking")
    if layer == "base_win_recall":
        tags.append("multiagent_vote")
        if row.get("B01_correct") == "1":
            tags.append("kb_or_rag_hit")
    if layer == "all_miss_but_recalled":
        tags.append("s3_s4_ranking")
        tags.append("hard_miss")
    if layer_a == "aphhm_lose" and row.get("APHHM_fail_mode") == "prune_loss":
        tags.append("aphhm_prune_loss")
    if dataset == "da" and layer in ("e7_win_rank", "base_win_rank", "e7_win_recall", "base_win_recall"):
        # DA exclusive correct with no cand recall on winner → mapper rescue
        if row.get("e7_win_vs_base") == "1" and row.get("e7_recall") == "0":
            tags.append("mapper_rescue")
        if row.get("base_win_vs_e7") == "1":
            if row.get("B06_recall") == "0" and row.get("B07_recall") == "0":
                tags.append("mapper_rescue")
    if dataset == "mcr" and layer in ("e7_win_rank", "base_win_rank"):
        tags.append("near_synonym_judge")
    # unique preserve order
    seen = set()
    out = []
    for t in tags:
        if t in MECH_VOCAB and t not in seen:
            out.append(t)
            seen.add(t)
    return out or ["hard_miss"]


def render_card(row: dict, tags: list[str]) -> str:
    dataset = row["dataset"]
    sl = row["slice"]
    cid = row["case_id"]
    gold = row.get("gold") or ""
    spec = slice_spec(dataset, sl)
    lines = [
        f"# {dataset.upper()} / {sl} / case {cid}",
        "",
        f"- **gold**: {gold}",
        f"- **layer**: `{row.get('layer') or ''}`  aphhm_layer=`{row.get('layer_aphhm') or ''}`",
        f"- **correct**: e7={row.get('e7_correct')} v0={row.get('v0_correct')} "
        f"B06={row.get('B06_correct')} B07={row.get('B07_correct')} "
        f"B01={row.get('B01_correct')} APHHM={row.get('APHHM_correct')}",
        f"- **recall**: e7={row.get('e7_recall')} v0={row.get('v0_recall')} "
        f"B06={row.get('B06_recall')} B07={row.get('B07_recall')}",
        f"- **auto_tags**: {', '.join(tags)}",
        f"- **manual_tag**: _(fill)_",
        f"- **one_liner**: _(fill)_",
        "",
        "## Backbone e7",
        backbone_trace_blurb(dc.ROOT / spec["e7"], cid, gold),
        "",
        "## Backbone v0",
        backbone_trace_blurb(dc.ROOT / spec["v0"], cid, gold),
        "",
    ]
    if spec.get("B06"):
        lines += [
            "## Baseline B06 MAC",
            baseline_trace_blurb(
                "B06", dc.ROOT / spec["B06"], cid, gold, row.get("B06_pred") or ""
            ),
            "",
        ]
    if spec.get("B07"):
        lines += [
            "## Baseline B07 MEDDx",
            baseline_trace_blurb(
                "B07", dc.ROOT / spec["B07"], cid, gold, row.get("B07_pred") or ""
            ),
            "",
        ]
    if spec.get("B01") and row.get("B01_correct") != "":
        lines += [
            "## Baseline B01 CoT-RAG",
            baseline_trace_blurb(
                "B01", dc.ROOT / spec["B01"], cid, gold, row.get("B01_pred") or ""
            ),
            "",
        ]
    if spec.get("APHHM") and row.get("APHHM_correct") != "":
        lines += [
            "## APHHM",
            aphhm_trace_blurb(dc.ROOT / spec["APHHM"], cid, gold),
            "",
        ]
    lines += [
        "## Notes",
        "- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; "
        "APHHM=`typed_llm` (do not over-read DA exclusive hits).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUT_CARDS.mkdir(parents=True, exist_ok=True)
    pooled = list(csv.DictReader((CENSUS / "pooled_cells.tsv").open(encoding="utf-8")))

    # group by dataset × layer
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    aphhm_buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in pooled:
        if r.get("layer"):
            buckets[(r["dataset"], r["layer"])].append(r)
        if r.get("layer_aphhm"):
            aphhm_buckets[(r["dataset"], r["layer_aphhm"])].append(r)

    selected: list[tuple[dict, list[str]]] = []
    index_rows: list[dict[str, Any]] = []

    print("=== sampling ===")
    for (ds, layer), rows in sorted(buckets.items()):
        take = stable_sample(rows, PER_CELL, SEED)
        print(f"  {ds:3s} {layer:24s} pool={len(rows):3d} take={len(take)}")
        for r in take:
            tags = suggest_tags(r, ds)
            selected.append((r, tags))

    for (ds, layer), rows in sorted(aphhm_buckets.items()):
        take = stable_sample(rows, APHHM_PER, SEED + 1)
        print(f"  {ds:3s} {layer:24s} pool={len(rows):3d} take={len(take)} (aphhm)")
        for r in take:
            # avoid dup cards
            key = (r["dataset"], r["slice"], r["case_id"])
            if any(
                (x["dataset"], x["slice"], x["case_id"]) == key for x, _ in selected
            ):
                continue
            tags = suggest_tags(r, ds)
            selected.append((r, tags))

    # write cards
    for r, tags in selected:
        fname = f"{r['dataset']}_{r['slice']}_{r['case_id']}.md"
        (OUT_CARDS / fname).write_text(render_card(r, tags), encoding="utf-8")
        index_rows.append(
            {
                "file": fname,
                "dataset": r["dataset"],
                "slice": r["slice"],
                "case_id": r["case_id"],
                "gold": r.get("gold") or "",
                "layer": r.get("layer") or "",
                "layer_aphhm": r.get("layer_aphhm") or "",
                "e7_correct": r.get("e7_correct"),
                "B06_correct": r.get("B06_correct"),
                "B07_correct": r.get("B07_correct"),
                "APHHM_correct": r.get("APHHM_correct"),
                "auto_tags": "|".join(tags),
                "manual_tag": "",
                "one_liner": "",
            }
        )

    tags_path = OUT_CARDS / "tags.tsv"
    with tags_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(index_rows[0].keys()) if index_rows else [])
        if index_rows:
            w.writeheader()
            w.writerows(index_rows)

    # index md
    by_layer: dict[str, list] = defaultdict(list)
    for r, tags in selected:
        key = r.get("layer") or r.get("layer_aphhm") or "other"
        by_layer[key].append((r, tags))
    idx = ["# Case trajectory cards index", "", f"n_cards={len(selected)}", ""]
    for layer, items in sorted(by_layer.items()):
        idx.append(f"## {layer} (n={len(items)})")
        for r, tags in items:
            idx.append(
                f"- [{r['dataset']}/{r['slice']}/{r['case_id']}]({r['dataset']}_{r['slice']}_{r['case_id']}.md) "
                f"tags=`{'|'.join(tags)}` gold={r.get('gold','')[:60]}"
            )
        idx.append("")
    (OUT_CARDS / "README.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print(f"\nWrote {len(selected)} cards → {OUT_CARDS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
