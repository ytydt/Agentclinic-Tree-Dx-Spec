"""Deep trajectory cards with side-by-side stage alignment (zero LLM calls).

Samples disagreement layers more aggressively than R1 shallow cards.
Writes case_cards_deep/*.md + index.md + tags.tsv.

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 analysis/backbone_v1/deep_trajectory_cards.py
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
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

LOCI = ROOT / "analysis" / "backbone_v1" / "trajectory_loci"
FEAT = ROOT / "analysis" / "backbone_v1" / "trajectory_features"
OUT = ROOT / "analysis" / "backbone_v1" / "case_cards_deep"

SEED = 11
# take all of small layers; sample larger ones
LAYER_CAP = {
    "e7_win_recall": 99,
    "e7_win_rank": 99,
    "base_win_recall": 20,
    "base_win_rank": 24,
    "all_miss_but_recalled": 24,
    "aphhm_win": 20,
    "aphhm_lose": 24,
}


def stable_sample(rows: list[dict], k: int) -> list[dict]:
    if len(rows) <= k:
        return list(rows)
    keyed = sorted(
        rows,
        key=lambda r: hashlib.md5(
            f"{r['dataset']}:{r['slice']}:{r['case_id']}".encode()
        ).hexdigest(),
    )
    rng = random.Random(SEED)
    rng.shuffle(keyed)
    return keyed[:k]


def load_joined() -> list[dict[str, str]]:
    loci = { (r["dataset"], r["slice"], r["case_id"]): r for r in csv.DictReader((LOCI/"pooled.tsv").open()) }
    feats = { (r["dataset"], r["slice"], r["case_id"]): r for r in csv.DictReader((FEAT/"pooled.tsv").open()) }
    census = lib.load_census_rows()
    out = []
    for r in census:
        key = (r["dataset"], r["slice"], r["case_id"])
        merged = dict(r)
        merged.update(loci.get(key) or {})
        merged.update({f"feat_{k}": v for k, v in (feats.get(key) or {}).items() if k not in merged})
        out.append(merged)
    return out


def vignette_snip(dataset: str, slice_name: str, cid: str, n: int = 500) -> str:
    cases = lib.load_cases(lib.slice_spec(dataset, slice_name)["subset"])
    text = lib.vignette_text(cases.get(cid) or {})
    text = text.replace("\n", " ").strip()
    return text[:n] + ("..." if len(text) > n else "")


def options_blurb(dataset: str, slice_name: str, cid: str) -> str:
    if dataset != "da":
        return ""
    cases = lib.load_cases(lib.slice_spec(dataset, slice_name)["subset"])
    opts = lib.da_options(cases.get(cid) or {})
    if not opts:
        return ""
    return "\n".join(f"  - {k}: {v}" for k, v in sorted(opts.items()))


def e7_deep(run_dir: Path, cid: str, gold: str) -> str:
    doc = dc.load_backbone_stage(run_dir, cid)
    if not doc:
        return "_missing case_stages_"
    st = doc.get("stages") or {}
    s1 = st.get("s1") or {}
    key_facts = s1.get("key_facts") or s1.get("salient_findings") or []
    if isinstance(key_facts, list):
        kf = "; ".join(str(x)[:80] for x in key_facts[:8])
    else:
        kf = str(key_facts)[:300]
    s2 = st.get("s2") or {}
    diffs = [str(x) for x in (s2.get("differentials") or [])]
    per_call = s2.get("per_call") or []
    lines = [
        f"- S1 key_facts: {kf}",
        f"- S2 mode={s2.get('s2_mode')} k={s2.get('s2_k')} pool_n={len(diffs)} "
        f"gold_in_s2={dc.any_match(diffs, gold)}",
    ]
    if per_call:
        for i, call in enumerate(per_call, 1):
            if isinstance(call, dict):
                cands = call.get("differentials") or call.get("diagnoses") or call.get("raw") or []
                if isinstance(cands, dict):
                    cands = cands.get("differentials") or list(cands.values())
                labels = [str(x) for x in (cands if isinstance(cands, list) else [cands])][:8]
                hit = dc.any_match(labels, gold)
                lines.append(f"  - call{i} n={len(labels)} gold={hit}: {', '.join(labels[:5])}")
            else:
                lines.append(f"  - call{i}: {str(call)[:120]}")
    else:
        hits = [d for d in diffs if dc.match(d, gold)]
        lines.append(f"  - pool gold matches: {hits[:5]}")
        lines.append(f"  - pool head: {', '.join(diffs[:8])}")
    s3 = [str(x) for x in ((st.get("s3") or {}).get("shortlist") or [])]
    lines.append(
        f"- S3 shortlist n={len(s3)} gold={dc.any_match(s3, gold)}: {', '.join(s3)}"
    )
    champ = str((st.get("s4") or {}).get("champion") or doc.get("champion") or "")
    lines.append(f"- S4 champion: **{champ}** gold={dc.match(champ, gold) if champ else None}")
    raw4 = (st.get("s4") or {}).get("raw")
    if raw4:
        lines.append(f"- S4 raw (trunc): {json.dumps(raw4, ensure_ascii=False)[:280]}")
    return "\n".join(lines)


def b06_deep(tr: dict, gold: str) -> str:
    disc = tr.get("discussion") or []
    lines = [f"- discussion_turns={len(disc)}"]
    for i, turn in enumerate(disc):
        text = json.dumps(turn, ensure_ascii=False) if not isinstance(turn, str) else turn
        mention = lib.text_mentions_gold(text, gold)
        # try extract diagnosis field
        diag = ""
        if isinstance(turn, dict):
            diag = str(turn.get("diagnosis") or turn.get("proposed") or "")[:80]
            comment = str(turn.get("commentary") or turn.get("content") or "")[:160]
        else:
            comment = text[:160]
        lines.append(f"  - turn{i} gold_mention={mention} diag={diag}")
        lines.append(f"    {comment}")
    sup = tr.get("supervisor") or {}
    top2 = lib.extract_labels(sup.get("top2_diagnoses") or [])
    lines.append(f"- supervisor votes={sup.get('votes')} top2={top2} gold={dc.any_match(top2, gold)}")
    return "\n".join(lines)


def b07_deep(tr: dict, gold: str) -> str:
    draft = lib.extract_labels(tr.get("draft") or [])
    refine = tr.get("refine")
    refine_l = lib.extract_labels(refine) if refine else []
    diag = lib.extract_labels(((tr.get("diagnose") or {}) if isinstance(tr.get("diagnose"), dict) else {}).get("top2_diagnoses") or [])
    queries = tr.get("queries") or []
    lines = [
        f"- draft={draft} gold={dc.any_match(draft, gold)}",
        f"- has_refine={bool(refine)} refine={refine_l[:5]} gold={dc.any_match(refine_l, gold) if refine_l else None}",
        f"- queries({len(queries)}): {queries[:4]}",
        f"- diagnose={diag} gold={dc.any_match(diag, gold)}",
    ]
    return "\n".join(lines)


def b01_deep(tr: dict, gold: str) -> str:
    ret = tr.get("retrieval") or {}
    queries = ret.get("queries") or []
    chunks = ret.get("served_chunks") or ret.get("chunks") or []
    nch = chunks if isinstance(chunks, int) else len(chunks or [])
    hit = False
    sample = ""
    if isinstance(chunks, list) and chunks:
        for ch in chunks[:5]:
            text = str(ch.get("text") if isinstance(ch, dict) else ch)
            if lib.text_mentions_gold(text, gold):
                hit = True
                sample = text[:160]
                break
        if not sample:
            sample = str(chunks[0].get("text") if isinstance(chunks[0], dict) else chunks[0])[:160]
    top2 = tr.get("top2") or tr.get("ordered") or []
    lines = [
        f"- queries={queries}",
        f"- n_chunks={nch} rag_gold_mention={hit}",
        f"- chunk_sample: {sample}",
        f"- top2={top2} gold={dc.any_match([str(x) for x in top2], gold)}",
    ]
    return "\n".join(lines)


def aphhm_deep(annotate: Path, cid: str, gold: str) -> str:
    af = dc.aphhm_features(annotate, cid, gold)
    cr = annotate / "case_results" / f"{cid}.json"
    final = []
    if cr.is_file():
        doc = json.loads(cr.read_text())
        final = [str(x.get("label")) for x in ((doc.get("l2") or {}).get("final_ranking_labels") or [])]
    # find gold leaf
    gold_leaf = None
    tree = annotate / "shared_trees" / f"{cid}.json"
    if tree.is_file():
        state = json.loads(tree.read_text())
        br = state.get("branches") or (state.get("state") or {}).get("branches") or {}
        items = list(br.values()) if isinstance(br, dict) else list(br)
        for b in items:
            if int(b.get("level") or 0) == 2 and dc.match(str(b.get("label") or ""), gold):
                gold_leaf = f"{b.get('id')}:{b.get('label')} parent={b.get('parent')}"
                break
    return "\n".join([
        f"- tree_n={af.get('tree_n')} tree_recall={af.get('tree_recall')}",
        f"- gold_leaf={gold_leaf}",
        f"- final_n={af.get('final_n')} final_recall={af.get('final_recall')} ranking={final}",
        f"- human_at1={af.get('human_at1')} fail_mode={af.get('fail_mode')}",
    ])


def primary_locus(row: dict) -> str:
    layer = row.get("layer") or ""
    if layer.startswith("base_win"):
        # which baseline saved
        for a in ("B06", "B07", "B01"):
            if str(row.get(f"{a}_correct")).lower() in ("1", "true"):
                return f"e7={row.get('e7_locus')}; {a}={row.get(f'{a}_locus')}"
        return f"e7={row.get('e7_locus')}"
    if layer.startswith("e7_win"):
        return f"e7={row.get('e7_locus')}; B06={row.get('B06_locus')}; B07={row.get('B07_locus')}"
    if layer == "all_miss_but_recalled":
        return f"e7={row.get('e7_locus')}; recalled_but_none_correct"
    if "aphhm" in (row.get("layer_aphhm") or ""):
        return f"APHHM={row.get('APHHM_locus')}"
    return row.get("e7_locus") or ""


def causal_line(row: dict) -> str:
    layer = row.get("layer") or row.get("layer_aphhm") or ""
    e7l = row.get("e7_locus") or ""
    mapper = str(row.get("feat_e7_mapper_rescue") or row.get("e7_mapper_rescue") or "").lower() in ("1", "true")
    if mapper and row.get("dataset") == "da" and "e7_win" in layer:
        return "DA mapper_rescue: e7 S4 未命中金标但 option@1 仍对——不可记入口/终裁优势。"
    if e7l == "s2_hit_s3_drop":
        return "骨干 S2 已召回，S3 短表丢掉金标。"
    if e7l == "s3_hit_s4_miss":
        return "骨干 S3 含金标，S4 终裁选错。"
    if e7l == "s2_miss" and layer.startswith("base_win_recall"):
        return "骨干入口完全未召回；基线直接给出金标/近义。"
    if layer == "all_miss_but_recalled":
        return "至少一臂召回金标但无人 Acc@1——排序/裁决天花板。"
    if row.get("APHHM_locus") == "tree_hit_final_drop":
        return "APHHM 树含金标叶，final_ranking 剪掉。"
    return f"layer={layer}; primary loci above."


def write_card(row: dict) -> Path:
    dataset, slice_name, cid = row["dataset"], row["slice"], row["case_id"]
    gold = row.get("gold") or ""
    layer = row.get("layer") or row.get("layer_aphhm") or "other"
    fname = f"{dataset}_{slice_name}_{cid}.md"
    path = OUT / fname
    opts = options_blurb(dataset, slice_name, cid)
    cov = (
        f"vig_words={row.get('feat_vig_words') or row.get('vig_words')}; "
        f"gold_words={row.get('feat_gold_words') or row.get('gold_words')}; "
        f"eponym={row.get('feat_gold_has_eponym') or row.get('gold_has_eponym')}; "
        f"subtype={row.get('feat_gold_has_subtype') or row.get('gold_has_subtype')}; "
        f"e7_s2_rank={row.get('feat_e7_s2_gold_rank') or row.get('e7_s2_gold_rank')}; "
        f"mapper_rescue={row.get('feat_e7_mapper_rescue') or row.get('e7_mapper_rescue')}"
    )
    lines = [
        f"# {dataset.upper()} / {slice_name} / case {cid}",
        "",
        f"- **gold**: {gold}",
        f"- **layer**: `{layer}`",
        f"- **correct**: e7={row.get('e7_correct')} v0={row.get('v0_correct')} "
        f"B06={row.get('B06_correct')} B07={row.get('B07_correct')} "
        f"B01={row.get('B01_correct')} APHHM={row.get('APHHM_correct')}",
        f"- **loci**: e7=`{row.get('e7_locus')}` B06=`{row.get('B06_locus')}` "
        f"B07=`{row.get('B07_locus')}` B01=`{row.get('B01_locus')}` APHHM=`{row.get('APHHM_locus')}`",
        f"- **primary_locus**: {primary_locus(row)}",
        f"- **covariates**: {cov}",
        f"- **causal**: {causal_line(row)}",
        "",
        "## Vignette (trunc)",
        vignette_snip(dataset, slice_name, cid),
        "",
    ]
    if opts:
        lines += ["## Options", opts, ""]

    e7 = lib.run_dir(dataset, slice_name, "e7")
    lines += ["## Backbone e7", e7_deep(e7, cid, gold) if e7 else "_missing_", ""]
    v0 = lib.run_dir(dataset, slice_name, "v0")
    if v0:
        lines += ["## Backbone v0 (compact)", e7_deep(v0, cid, gold), ""]

    for arm, deep_fn in (("B06", b06_deep), ("B07", b07_deep), ("B01", b01_deep)):
        rd = lib.run_dir(dataset, slice_name, arm)
        if not rd:
            continue
        tr = dc.load_traces(rd).get(cid) or {}
        lines += [f"## Baseline {arm}", deep_fn(tr, gold), ""]

    aph = lib.run_dir(dataset, slice_name, "APHHM")
    if aph:
        lines += ["## APHHM", aphhm_deep(aph, cid, gold), ""]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    if not (LOCI / "pooled.tsv").is_file() or not (FEAT / "pooled.tsv").is_file():
        raise SystemExit("run trajectory_covariates.py and trajectory_locus.py first")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_joined()
    selected: list[dict] = []
    # disagreement layers
    by_layer = defaultdict(list)
    for r in rows:
        layer = r.get("layer") or ""
        if layer:
            by_layer[layer].append(r)
        la = r.get("layer_aphhm") or ""
        if la in ("aphhm_win", "aphhm_lose"):
            by_layer[la].append(r)
    for layer, rs in by_layer.items():
        # split by dataset for balance
        for ds in ("da", "mcr"):
            sub = [r for r in rs if r["dataset"] == ds]
            cap = LAYER_CAP.get(layer, 8)
            # half-ish per dataset when both exist
            k = max(cap // 2, 4) if layer.startswith("all_miss") or layer.startswith("base_win") else cap
            if layer.startswith("e7_win"):
                k = len(sub)  # take all
            if layer.startswith("aphhm"):
                k = min(len(sub), LAYER_CAP.get(layer, 12))
            selected.extend(stable_sample(sub, k))
    # dedupe
    seen = set()
    uniq = []
    for r in selected:
        key = (r["dataset"], r["slice"], r["case_id"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    tags_rows = []
    index_lines = [f"# Deep trajectory cards", "", f"n_cards={len(uniq)}", ""]
    by = defaultdict(list)
    for r in uniq:
        path = write_card(r)
        layer = r.get("layer") or r.get("layer_aphhm") or "other"
        by[layer].append(r)
        tags_rows.append({
            "file": path.name,
            "dataset": r["dataset"],
            "slice": r["slice"],
            "case_id": r["case_id"],
            "gold": r.get("gold"),
            "layer": layer,
            "e7_locus": r.get("e7_locus"),
            "B06_locus": r.get("B06_locus"),
            "B07_locus": r.get("B07_locus"),
            "B01_locus": r.get("B01_locus"),
            "APHHM_locus": r.get("APHHM_locus"),
            "mapper_rescue": r.get("feat_e7_mapper_rescue") or r.get("e7_mapper_rescue"),
            "causal": causal_line(r),
        })
    for layer, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        index_lines.append(f"## {layer} (n={len(rs)})")
        for r in rs:
            fname = f"{r['dataset']}_{r['slice']}_{r['case_id']}.md"
            index_lines.append(
                f"- [{r['dataset']}/{r['slice']}/{r['case_id']}]({fname}) "
                f"e7=`{r.get('e7_locus')}` gold={str(r.get('gold') or '')[:60]}"
            )
        index_lines.append("")
    (OUT / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    with (OUT / "tags.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tags_rows[0].keys()))
        w.writeheader()
        w.writerows(tags_rows)
    print(f"Wrote {len(uniq)} deep cards → {OUT}")
    for layer, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"  {layer}: {len(rs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
