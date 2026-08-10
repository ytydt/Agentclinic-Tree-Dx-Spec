#!/usr/bin/env python3
"""R6 selector-only causal probes (X1–X5).

Reuses case_stages pools and re-runs only the final selector call.

Probes:
  X1 cross   — swap generator pool × selector prompt family
  X1b        — like X1 but shortlist ordered by score_logit
  X2 disc    — keep only high-discriminability spans
  X3 siblings— drop near-gold non-gold siblings from shortlist
  X3f        — X3 then restore a fixed canonical order (alpha)
  X4 order   — permute shortlist order (seeded)
  X5 quota   — equalise for/against span counts between gold and champ
  X5d        — disc-weighted quota (trim lowest-disc spans first)
  X5s        — force gold & champ to share the intersection of for-spans
  Xrej       — blank gold's reject-why text in notes (MOSAIC only; soft)


Usage:
  PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1 \\
    python3 scripts/paper/run_r6_probe.py \\
      --dataset diagnosisarena --probe x1_forest_pool_aphhm_sel \\
      --pool-from logs/backbone_v1/diagnosisarena/mosaic_forest_v1 \\
      --selector-family aphhm_c --workers 32
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import baseline_common as bc  # noqa: E402
import disagreement_census as dc  # noqa: E402
import r3_lib as r3  # noqa: E402
import r6_lib as r6  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from run_backbone_v1 import SUBSETS  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"


def _read(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def load_stage(d: Path, cid: str) -> dict:
    p = d / "case_stages" / f"{cid}.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    for alt in (cid.lstrip("0") or "0", str(int(cid)) if cid.isdigit() else cid):
        p2 = d / "case_stages" / f"{alt}.json"
        if p2.is_file():
            return json.loads(p2.read_text(encoding="utf-8"))
    return {}


def _resolve_spans(doc: dict, items: list[Any]) -> list[str]:
    """Map MOSAIC evidence_id tokens to raw_span when present."""
    stages = doc.get("stages") or {}
    id2 = {
        str(e.get("evidence_id")): str(e.get("raw_span") or "")
        for e in (stages.get("evidence") or [])
        if isinstance(e, dict) and e.get("evidence_id")
    }
    out: list[str] = []
    for x in items or []:
        s = str(x or "").strip()
        if not s:
            continue
        if s in id2 and id2[s]:
            out.append(id2[s])
        else:
            out.append(s)
    return out


def extract_notes(doc: dict) -> list[dict[str, Any]]:
    stages = doc.get("stages") or {}
    notes = []
    for c in stages.get("registry") or stages.get("frontier_final") or []:
        lab = str(c.get("preferred_label") or c.get("preferred_name") or "").strip()
        if not lab:
            continue
        raw_for = list(
            c.get("support_spans") or c.get("supporting_evidence") or []
        )[:6]
        raw_against = list(
            c.get("contradict_spans") or c.get("contradicting_evidence") or []
        )[:4]
        notes.append(
            {
                "label": lab,
                "for": _resolve_spans(doc, raw_for),
                "against": _resolve_spans(doc, raw_against),
                "score": c.get("score_logit", c.get("score")),
            }
        )
    return notes


def shortlist_from(
    doc: dict, notes: list[dict], max_n: int = 6, *, prefer_score_order: bool = False
) -> list[str]:
    stages = doc.get("stages") or {}
    if prefer_score_order:
        scored = sorted(
            notes,
            key=lambda n: (
                -(n["score"] if n["score"] is not None else float("-inf")),
                n["label"],
            ),
        )
        labs = [n["label"] for n in scored if n["label"]]
        if labs:
            return labs[:max_n]
    ordered = [str(x) for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]
    if ordered:
        return ordered[:max_n]
    frontier = stages.get("frontier") or []
    if frontier and isinstance(frontier[0], str):
        id_lab = {
            c.get("concept_id"): str(
                c.get("preferred_label") or c.get("preferred_name") or ""
            )
            for c in (stages.get("registry") or [])
        }
        labs = [id_lab[i] for i in frontier if i in id_lab and id_lab[i]]
        if labs:
            return labs[:max_n]
    # sorted by score if present
    scored = sorted(
        notes, key=lambda n: (-(n["score"] or 0) if n["score"] is not None else 0)
    )
    return [n["label"] for n in scored[:max_n]]


def apply_probe(
    probe: str,
    short: list[str],
    notes: list[dict],
    gold: str,
    champ: str,
    seed: int = 0,
) -> tuple[list[str], list[dict]]:
    by = {_norm(n["label"]): dict(n) for n in notes}
    short = list(short)
    notes_out = [by.get(_norm(s), {"label": s, "for": [], "against": []}) for s in short]

    if probe.startswith("x1"):
        # width-matched as-is
        return short[:6], notes_out[:6]

    if probe == "x2_disc":
        # recompute disc within current notes; drop spans shared with others
        for n in notes_out:
            spans = n.get("for") or []
            others = set()
            for m in notes_out:
                if m is n:
                    continue
                for s in m.get("for") or []:
                    others.add(_norm(s))
            n["for"] = [s for s in spans if _norm(s) not in others][:4]
        return short, notes_out

    if probe == "x3_siblings" or probe.startswith("x3"):
        kept = []
        for lab in short:
            if gold and dc.match(lab, gold):
                kept.append(lab)
                continue
            if gold and r3.near_gold(lab, gold):
                continue  # drop sibling
            kept.append(lab)
        if gold and not any(dc.match(x, gold) for x in kept):
            # ensure gold stays if it was present
            if any(dc.match(x, gold) for x in short):
                kept = [next(x for x in short if dc.match(x, gold))] + kept
        if probe in ("x3f", "x3_fixed_order"):
            # stable alphabetical order after sibling removal (controls X4 confound)
            g_lab = next((x for x in kept if gold and dc.match(x, gold)), None)
            rest = sorted([x for x in kept if x != g_lab], key=lambda s: s.lower())
            kept = ([g_lab] + rest) if g_lab else rest
        notes_out = [by.get(_norm(s), {"label": s, "for": [], "against": []}) for s in kept]
        return kept, notes_out

    if probe.startswith("x4_order"):
        rng = random.Random(seed)
        perm = list(short)
        rng.shuffle(perm)
        notes_out = [by.get(_norm(s), {"label": s, "for": [], "against": []}) for s in perm]
        return perm, notes_out

    if probe == "x5_quota":
        # equalise for/against counts between gold and current champ (or top note)
        g = next((n for n in notes_out if gold and dc.match(n["label"], gold)), None)
        c = next((n for n in notes_out if champ and dc.match(n["label"], champ)), None)
        if g and c:
            # truncate the longer for-list to the shorter length
            n_for = min(len(g.get("for") or []), len(c.get("for") or []))
            n_ag = min(len(g.get("against") or []), len(c.get("against") or []))
            g["for"] = list(g.get("for") or [])[:n_for]
            c["for"] = list(c.get("for") or [])[:n_for]
            g["against"] = list(g.get("against") or [])[:n_ag]
            c["against"] = list(c.get("against") or [])[:n_ag]
        return short, notes_out

    if probe in ("x5d", "x5_disc_quota"):
        # drop lowest-uniqueness spans until gold/champ for-counts match
        def uniqueness(span: str, owner: dict) -> float:
            sn = _norm(span)
            if not sn:
                return 0.0
            others = 0
            for m in notes_out:
                if m is owner:
                    continue
                if any(_norm(s) == sn for s in (m.get("for") or [])):
                    others += 1
            return 1.0 / (1 + others)

        g = next((n for n in notes_out if gold and dc.match(n["label"], gold)), None)
        c = next((n for n in notes_out if champ and dc.match(n["label"], champ)), None)
        if g and c:
            target = min(len(g.get("for") or []), len(c.get("for") or []))
            for n in (g, c):
                spans = list(n.get("for") or [])
                spans.sort(key=lambda s: -uniqueness(s, n))
                n["for"] = spans[:target]
        return short, notes_out

    if probe in ("x5s", "x5_shared_decisive"):
        g = next((n for n in notes_out if gold and dc.match(n["label"], gold)), None)
        c = next((n for n in notes_out if champ and dc.match(n["label"], champ)), None)
        if g and c:
            gset = {_norm(s): s for s in (g.get("for") or [])}
            cset = {_norm(s): s for s in (c.get("for") or [])}
            inter = [gset[k] for k in gset if k in cset]
            if inter:
                g["for"] = list(inter)[:4]
                c["for"] = list(inter)[:4]
            else:
                # no overlap: give both the union truncated equally
                union = list(dict.fromkeys(list(g.get("for") or []) + list(c.get("for") or [])))[:4]
                g["for"] = list(union)
                c["for"] = list(union)
        return short, notes_out

    if probe in ("xrej", "x_reject_blank"):
        # Soft probe: strip against spans on gold (proxy for neutralizing reject cues)
        for n in notes_out:
            if gold and dc.match(n["label"], gold):
                n["against"] = []
        return short, notes_out

    return short, notes_out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()))
    ap.add_argument("--probe", required=True)
    ap.add_argument("--pool-from", type=Path, required=True)
    ap.add_argument("--selector-family", choices=("mosaic", "aphhm_c"), required=True)
    ap.add_argument("--out-arm", default="")
    ap.add_argument("--order-seed", type=int, default=0)
    ap.add_argument(
        "--prefer-score-order",
        action="store_true",
        help="X1b: order shortlist by score_logit / score instead of ordered_diagnoses",
    )
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    args = ap.parse_args()

    out_arm = args.out_arm or f"r6_{args.probe}"
    out_dir = OUT_ROOT / args.dataset / out_arm
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)

    ds_name = "medcasereasoning" if args.dataset.startswith("medcase") else "diagnosisarena"
    cases = bc.load_runtime_cases(
        dataset=ds_name,
        subset_dir=SUBSETS[args.dataset],
        case_ids=list(args.case_id or []),
        limit=int(args.limit or 0),
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=240,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "probe_llm.json", args.model)
    prompt = (
        _read("mosaic_selector.txt")
        if args.selector_family == "mosaic"
        else _read("aphhm_c_frontier_selector_candev.txt")
    )
    role = (
        "MosaicEvidenceSelector"
        if args.selector_family == "mosaic"
        else "AphhmCFrontierSelector"
    )
    pool = Path(args.pool_from)

    def one(case: dict) -> dict[str, Any]:
        cid = str(case.get("source_id") or "")
        gold = str(case.get("_gold_text") or "").strip()
        vignette = str(case.get("vignette") or "")
        doc = load_stage(pool, cid)
        if not doc and cid.isdigit():
            doc = load_stage(pool, str(int(cid)))
        if not doc:
            return {"source_id": cid, "error": "no_stage", "champion": "", "gold": gold}
        notes = extract_notes(doc)
        prefer_score = bool(args.prefer_score_order) or args.probe.startswith("x1b")
        short = shortlist_from(doc, notes, prefer_score_order=prefer_score)
        champ0 = str(doc.get("champion") or (short[0] if short else ""))
        short, notes2 = apply_probe(
            args.probe, short, notes, gold, champ0, seed=args.order_seed + hash(cid) % 10000
        )
        if not short:
            return {"source_id": cid, "error": "empty_short", "champion": "", "gold": gold}
        raw = cached.call(
            role,
            prompt,
            {
                "vignette": vignette[:6000],
                "shortlist": short,
                "candidate_notes": notes2,
            },
        )
        champ = str((raw or {}).get("champion") or "").strip()
        if champ not in short:
            champ = next((x for x in short if _norm(x) == _norm(champ)), short[0])
        hit = bool(champ and gold and dc.match(champ, gold))
        out_doc = {
            "source_id": cid,
            "case_id": case.get("case_id"),
            "champion": champ,
            "ordered_diagnoses": [champ] + [x for x in short if x != champ][:4],
            "gold": gold,
            "probe": args.probe,
            "selector_family": args.selector_family,
            "pool_from": str(pool),
            "shortlist": short,
            "selector": raw,
            "stages": {
                "mode": f"probe_{args.probe}",
                "registry": [
                    {
                        "preferred_label": n["label"],
                        "preferred_name": n["label"],
                        "support_spans": n.get("for"),
                        "contradict_spans": n.get("against"),
                        "supporting_evidence": n.get("for"),
                        "contradicting_evidence": n.get("against"),
                        "status": "active",
                    }
                    for n in notes2
                ],
                "selector" if args.selector_family == "mosaic" else "frontier_selector": raw,
            },
            "llm_calls": 1,
        }
        (out_dir / "case_stages" / f"{cid}.json").write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return {"source_id": cid, "champion": champ, "gold": gold, "hit": hit}

    preds = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(one, c) for c in cases]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            preds.append(r)
            if i % 25 == 0:
                print(f"  [{i}/{len(cases)}] {r.get('source_id')} -> {r.get('champion')}")
    n_hit = sum(1 for p in preds if p.get("hit"))
    summary = {
        "probe": args.probe,
        "out_arm": out_arm,
        "pool_from": str(pool),
        "selector_family": args.selector_family,
        "n": len(preds),
        "chain_hit": round(n_hit / len(preds), 4) if preds else None,
    }
    (out_dir / "probe_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
