"""Fine-grained failure loci for every arm on every census case (zero LLM calls).

Backbone: s2_miss / s2_hit_s3_drop / s3_hit_s4_miss / s4_hit_judge_miss / ok
B06: agents_miss / agents_hit_supervisor_drop / supervisor_ok
B07: draft_miss / draft_hit_refine_drop / refine_hit_diagnose_drop / diagnose_ok
B01: rag_miss / rag_hit_gen_miss / gen_ok
APHHM: tree_miss / tree_hit_final_drop / final_ok / final_hit_judge_miss

Writes trajectory_loci/{da,mcr,pooled}.tsv + cross_tabs.json

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 analysis/backbone_v1/trajectory_locus.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

OUT = ROOT / "analysis" / "backbone_v1" / "trajectory_loci"


def backbone_locus(run_dir: Path, cid: str, gold: str, correct: bool) -> dict[str, Any]:
    bf = dc.backbone_features(run_dir, cid, gold)
    s2 = bf.get("s2_recall")
    s3 = bf.get("s3_recall")
    s4 = bf.get("s4_hit")
    if s2 is False:
        locus = "s2_miss"
    elif s3 is False:
        locus = "s2_hit_s3_drop"
    elif s4 is False:
        locus = "s3_hit_s4_miss"
    elif s4 is True and not correct:
        locus = "s4_hit_judge_miss"
    elif s4 is True and correct:
        locus = "ok"
    else:
        locus = "unknown"
    return {
        "locus": locus,
        "s2_recall": s2,
        "s3_recall": s3,
        "s4_hit": s4,
        "s2_n": bf.get("s2_n"),
        "s3_n": bf.get("s3_n"),
        "champion": bf.get("s4_champion"),
    }


def b06_locus(trace: Optional[dict], cands: list[str], gold: str, correct: bool) -> dict[str, Any]:
    tr = trace or {}
    disc = tr.get("discussion") or []
    agents_hit = False
    first_turn = None
    for i, turn in enumerate(disc):
        text = json_dumps_safe(turn)
        if lib.text_mentions_gold(text, gold):
            agents_hit = True
            first_turn = i
            break
    if not agents_hit:
        agents_hit = dc.any_match(cands, gold)
    sup = tr.get("supervisor") or {}
    top2 = lib.extract_labels(sup.get("top2_diagnoses") or cands)
    if not top2:
        top2 = list(cands)
    sup_hit = dc.any_match(top2, gold) if gold else False
    # Terminal-first: scored output is supervisor/cands.
    if correct and (sup_hit or dc.any_match(cands, gold)):
        locus = "supervisor_ok"
    elif correct and not sup_hit:
        locus = "supervisor_miss_but_scored_ok"  # mapper/judge near-synonym
    elif not agents_hit:
        locus = "agents_miss"
    elif not sup_hit:
        locus = "agents_hit_supervisor_drop"
    else:
        locus = "supervisor_hit_judge_miss"
    return {
        "locus": locus,
        "agents_hit": agents_hit,
        "supervisor_hit": sup_hit,
        "gold_first_discussion_turn": first_turn,
        "discussion_turns": len(disc),
        "votes": (sup.get("votes") if isinstance(sup, dict) else None),
    }


def b07_locus(trace: Optional[dict], cands: list[str], gold: str, correct: bool) -> dict[str, Any]:
    tr = trace or {}
    draft = lib.extract_labels(tr.get("draft") or [])
    refine = tr.get("refine")
    refine_labels = lib.extract_labels(refine) if refine else []
    # refine may be a list of strings or structured
    if not refine_labels and isinstance(refine, list):
        refine_labels = [str(x) for x in refine]
    diag = (tr.get("diagnose") or {}) if isinstance(tr.get("diagnose"), dict) else {}
    diagnose = lib.extract_labels(diag.get("top2_diagnoses") or cands)
    draft_hit = dc.any_match(draft, gold) if gold else False
    if not refine:
        refine_hit = draft_hit
    elif refine_labels:
        refine_hit = dc.any_match(refine_labels, gold) if gold else False
    else:
        refine_hit = False
    diag_hit = dc.any_match(diagnose, gold) if gold else False
    # Terminal-first locus (diagnose is the scored output); intermediates as secondary tags.
    if diag_hit and correct:
        locus = "diagnose_ok"
    elif correct and not diag_hit:
        locus = "diagnose_miss_but_scored_ok"
    elif diag_hit and not correct:
        locus = "diagnose_hit_judge_miss"
    elif (draft_hit or refine_hit) and not diag_hit:
        if draft_hit and refine and not refine_hit:
            locus = "draft_hit_refine_drop"
        else:
            locus = "refine_hit_diagnose_drop"
    elif not draft_hit and not refine_hit and not diag_hit:
        locus = "draft_miss"
    else:
        locus = "draft_miss"
    # annotate whether diagnose recovered after refine drop
    recovered_after_refine_drop = bool(
        draft_hit and refine and (not refine_hit) and diag_hit
    )
    return {
        "locus": locus,
        "draft_hit": draft_hit,
        "refine_hit": refine_hit,
        "diagnose_hit": diag_hit,
        "has_refine": bool(refine),
        "recovered_after_refine_drop": recovered_after_refine_drop,
        "draft": draft[:5],
        "diagnose": diagnose[:3],
    }


def b01_locus(trace: Optional[dict], cands: list[str], gold: str, correct: bool) -> dict[str, Any]:
    tr = trace or {}
    ret = tr.get("retrieval") or {}
    chunks = ret.get("served_chunks") or ret.get("chunks") or ret.get("candidate_chunks") or []
    rag_hit = False
    if isinstance(chunks, int):
        # only know count; fall back to query text
        queries = ret.get("queries") or []
        rag_hit = any(lib.text_mentions_gold(str(q), gold) for q in queries)
    elif isinstance(chunks, (list, tuple)):
        for ch in chunks:
            text = str(ch.get("text") if isinstance(ch, dict) else ch)
            if lib.text_mentions_gold(text, gold):
                rag_hit = True
                break
        if not rag_hit:
            queries = ret.get("queries") or []
            rag_hit = any(lib.text_mentions_gold(str(q), gold) for q in queries)
    gen_hit = dc.any_match(cands, gold) if gold else False
    if not rag_hit and not gen_hit:
        locus = "rag_miss"
    elif rag_hit and not gen_hit:
        locus = "rag_hit_gen_miss"
    elif gen_hit and correct:
        locus = "gen_ok"
    elif gen_hit and not correct:
        locus = "gen_hit_judge_miss"
    else:
        # gen_hit without rag — still gen_ok path
        locus = "gen_ok" if correct else "rag_miss_gen_ok_wrong"
        if gen_hit and not rag_hit:
            locus = "gen_ok_no_rag" if correct else "gen_hit_judge_miss"
    return {
        "locus": locus,
        "rag_hit": rag_hit,
        "gen_hit": gen_hit,
        "n_queries": len(ret.get("queries") or []),
        "n_chunks": chunks if isinstance(chunks, int) else len(chunks or []),
    }


def aphhm_locus(annotate_dir: Path, cid: str, gold: str, correct: Optional[bool]) -> dict[str, Any]:
    af = dc.aphhm_features(annotate_dir, cid, gold)
    tree = af.get("tree_recall")
    final = af.get("final_recall")
    if tree is False:
        locus = "tree_miss"
    elif final is False:
        locus = "tree_hit_final_drop"
    elif final is True and correct is False:
        locus = "final_hit_judge_miss"
    elif final is True and correct is True:
        locus = "final_ok"
    elif final is True:
        locus = "final_ok"
    else:
        locus = "unknown"
    # leaf path if tree hit
    gold_leaf = None
    gold_parent = None
    tree_path = annotate_dir / "shared_trees" / f"{cid}.json"
    if tree_path.is_file() and gold:
        state = json.loads(tree_path.read_text())
        br = state.get("branches") or (state.get("state") or {}).get("branches") or {}
        if isinstance(br, dict):
            items = list(br.values())
            by_id = {str(b.get("id")): b for b in items}
        else:
            items = list(br)
            by_id = {str(b.get("id")): b for b in items}
        for b in items:
            if int(b.get("level") or 0) != 2:
                continue
            if dc.match(str(b.get("label") or ""), gold):
                gold_leaf = str(b.get("label"))
                pid = str(b.get("parent") or b.get("parent_id") or "")
                parent = by_id.get(pid) or {}
                gold_parent = str(parent.get("label") or pid)
                break
    return {
        "locus": locus,
        "tree_recall": tree,
        "final_recall": final,
        "tree_n": af.get("tree_n"),
        "final_n": af.get("final_n"),
        "gold_leaf": gold_leaf,
        "gold_parent": gold_parent,
        "human_at1": af.get("human_at1"),
    }


def json_dumps_safe(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except TypeError:
        return str(obj)


def _truthy(x: Any) -> bool:
    return str(x).lower() in ("1", "true", "yes")


def build_row(row: dict[str, str]) -> dict[str, Any]:
    dataset, slice_name, cid = row["dataset"], row["slice"], row["case_id"]
    gold = row.get("gold") or ""
    out: dict[str, Any] = {
        "dataset": dataset,
        "slice": slice_name,
        "case_id": cid,
        "gold": gold,
        "layer": row.get("layer") or "",
        "layer_aphhm": row.get("layer_aphhm") or "",
    }
    # backbone
    for arm in ("e7", "v0"):
        rd = lib.run_dir(dataset, slice_name, arm)
        correct = _truthy(row.get(f"{arm}_correct"))
        if rd:
            loc = backbone_locus(rd, cid, gold, correct)
        else:
            loc = {"locus": "missing"}
        out[f"{arm}_locus"] = loc["locus"]
        out[f"{arm}_correct"] = int(correct)
        for k, v in loc.items():
            if k != "locus":
                out[f"{arm}_{k}"] = v

    # baselines
    for arm, fn in (("B06", b06_locus), ("B07", b07_locus), ("B01", b01_locus)):
        rd = lib.run_dir(dataset, slice_name, arm)
        correct = _truthy(row.get(f"{arm}_correct"))
        out[f"{arm}_correct"] = int(correct) if row.get(f"{arm}_correct") not in ("", None) else None
        if not rd:
            out[f"{arm}_locus"] = "missing" if arm != "B01" or dataset == "mcr" else "na"
            continue
        traces = getattr(build_row, "_trace_cache", {})
        cache_key = str(rd)
        if cache_key not in traces:
            traces[cache_key] = dc.load_traces(rd)
            build_row._trace_cache = traces  # type: ignore[attr-defined]
        tr = traces[cache_key].get(cid)
        preds = getattr(build_row, "_pred_cache", {})
        if cache_key not in preds:
            preds[cache_key] = dc.load_jsonl_preds(rd)
            build_row._pred_cache = preds  # type: ignore[attr-defined]
        raw_preds = preds[cache_key]
        cands = raw_preds.get(cid) or []
        if not cands:
            # try prefixed keys
            for k, v in raw_preds.items():
                if dc._norm_cid_from_pred_key(k) == cid:
                    cands = v
                    break
        loc = fn(tr, cands, gold, correct)
        out[f"{arm}_locus"] = loc["locus"]
        for k, v in loc.items():
            if k == "locus":
                continue
            if isinstance(v, (list, dict)):
                out[f"{arm}_{k}"] = json_dumps_safe(v)
            else:
                out[f"{arm}_{k}"] = v

    # APHHM
    rd = lib.run_dir(dataset, slice_name, "APHHM")
    if rd:
        correct_raw = row.get("APHHM_correct")
        correct = _truthy(correct_raw) if correct_raw not in ("", None) else None
        # APHHM annotate dir is the path itself in registry
        loc = aphhm_locus(rd, cid, gold, correct)
        out["APHHM_locus"] = loc["locus"]
        out["APHHM_correct"] = (
            int(correct) if correct is not None else None
        )
        for k, v in loc.items():
            if k != "locus":
                out[f"APHHM_{k}"] = v
    else:
        out["APHHM_locus"] = "na"
        out["APHHM_correct"] = None
    return out


def cross_tabs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ds in ("da", "mcr", "pooled"):
        rs = rows if ds == "pooled" else [r for r in rows if r["dataset"] == ds]
        # e7 × B06 / B07 / B01
        for base in ("B06", "B07", "B01"):
            key = f"{ds}__e7_x_{base}"
            ct: dict[str, Counter] = defaultdict(Counter)
            for r in rs:
                el = r.get("e7_locus") or "missing"
                bl = r.get(f"{base}_locus") or "missing"
                if bl in ("na",):
                    continue
                ct[el][bl] += 1
            out[key] = {a: dict(b) for a, b in ct.items()}
        # by layer: locus distribution
        by_layer: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        for r in rs:
            layer = r.get("layer") or layer_bucket(r)
            for arm in ("e7", "v0", "B06", "B07", "B01", "APHHM"):
                loc = r.get(f"{arm}_locus")
                if loc and loc not in ("na", "missing"):
                    by_layer[layer][arm][loc] += 1
        out[f"{ds}__by_layer"] = {
            layer: {arm: dict(c) for arm, c in arms.items()}
            for layer, arms in by_layer.items()
        }
        # overall locus counts
        overall = {}
        for arm in ("e7", "v0", "B06", "B07", "B01", "APHHM"):
            overall[arm] = dict(Counter(r.get(f"{arm}_locus") for r in rs if r.get(f"{arm}_locus") not in (None, "na")))
        out[f"{ds}__overall"] = overall
    return out


def layer_bucket(r: dict[str, Any]) -> str:
    e7 = r.get("e7_correct") == 1
    base = (r.get("B06_correct") == 1) or (r.get("B07_correct") == 1)
    if e7 and base:
        return "both_correct"
    if (not e7) and (not base):
        return "both_wrong"
    return "other"


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    census = lib.load_census_rows()
    print(f"census={len(census)}")
    rows = [build_row(r) for r in census]
    OUT.mkdir(parents=True, exist_ok=True)
    write_tsv(OUT / "da.tsv", [r for r in rows if r["dataset"] == "da"])
    write_tsv(OUT / "mcr.tsv", [r for r in rows if r["dataset"] == "mcr"])
    write_tsv(OUT / "pooled.tsv", rows)
    tabs = cross_tabs(rows)
    (OUT / "cross_tabs.json").write_text(
        json.dumps(tabs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for ds in ("da", "mcr", "pooled"):
        print(f"\n=== {ds} e7 loci ===")
        print(tabs[f"{ds}__overall"].get("e7"))
        print(f"  B06:", tabs[f"{ds}__overall"].get("B06"))
        print(f"  B07:", tabs[f"{ds}__overall"].get("B07"))
        if ds != "da":
            print(f"  B01:", tabs[f"{ds}__overall"].get("B01"))
        print(f"  APHHM:", tabs[f"{ds}__overall"].get("APHHM"))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
