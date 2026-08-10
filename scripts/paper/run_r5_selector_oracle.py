#!/usr/bin/env python3
"""R5 selector-oracle interventions (J1 / J2 / J3).

Reuses an existing case_stages artifact, injects gold into the decision
shortlist, and re-runs ONLY the final selector call. Works for APHHM-C and
MOSAIC because both selectors take {vignette, shortlist, candidate_notes}.

Interventions:
  J1 bare   — gold label only, empty for/against
  J2 fair   — one extra call writes honest support/contradict spans for gold
  J3 unmerge — restore a merge-swallowed gold label into the shortlist (J1-style)

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 scripts/paper/run_r5_selector_oracle.py \\
      --reuse-from logs/backbone_v1/diagnosisarena/aphhm_c_collapse3c_v1 \\
      --dataset diagnosisarena --out-arm r5_j1_collapse3c --intervention j1 \\
      --workers 32
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from run_backbone_v1 import SUBSETS  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"

EVIDENCE_PROMPT = """Role: GoldEvidenceWriter

Given a vignette and a candidate diagnosis label, quote VERBATIM spans from the
vignette that support the diagnosis and spans that argue against it. Spans must
be exact substrings of the vignette. If nothing argues against it, return an
empty against list.

Return strict JSON only:
{
  "for": ["verbatim span", "..."],
  "against": ["verbatim span", "..."]
}
"""


def _read(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def load_stage(reuse: Path, cid: str) -> dict[str, Any]:
    p = reuse / "case_stages" / f"{cid}.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    for alt in (cid.lstrip("0") or "0", cid.zfill(3)):
        p2 = reuse / "case_stages" / f"{alt}.json"
        if p2.is_file():
            return json.loads(p2.read_text(encoding="utf-8"))
    return {}


def detect_family(doc: dict) -> str:
    mode = str((doc.get("stages") or {}).get("mode") or "")
    if mode in ("lite", "forest", "impc", "adaptive4", "adaptive4v2") or "ax_" in str(
        (doc.get("stages") or {}).keys()
    ):
        return "mosaic"
    if (doc.get("stages") or {}).get("registry") is not None:
        # aphhm_c registry uses preferred_label
        reg = (doc.get("stages") or {}).get("registry") or []
        if reg and "preferred_label" in (reg[0] or {}):
            return "aphhm_c"
        if reg and "preferred_name" in (reg[0] or {}):
            return "mosaic"
    return "aphhm_c"


def extract_notes(doc: dict, family: str) -> list[dict[str, Any]]:
    stages = doc.get("stages") or {}
    notes = []
    if family == "aphhm_c":
        for c in stages.get("registry") or []:
            lab = str(c.get("preferred_label") or "").strip()
            if not lab:
                continue
            notes.append(
                {
                    "label": lab,
                    "for": list(c.get("support_spans") or [])[:4],
                    "against": list(c.get("contradict_spans") or [])[:3],
                }
            )
    else:
        for c in stages.get("registry") or stages.get("frontier_final") or []:
            lab = str(c.get("preferred_name") or c.get("preferred_label") or "").strip()
            if not lab:
                continue
            notes.append(
                {
                    "label": lab,
                    "for": list(c.get("supporting_evidence") or c.get("support_spans") or [])[:4],
                    "against": list(
                        c.get("contradicting_evidence") or c.get("contradict_spans") or []
                    )[:3],
                }
            )
    return notes


def shortlist_of(doc: dict, family: str, notes: list[dict]) -> list[str]:
    stages = doc.get("stages") or {}
    if family == "aphhm_c":
        # prefer frontier ids
        frontier = stages.get("frontier") or []
        id_lab = {
            c.get("concept_id"): str(c.get("preferred_label") or "")
            for c in (stages.get("registry") or [])
        }
        if frontier:
            return [id_lab[i] for i in frontier if i in id_lab and id_lab[i]]
    ordered = [str(x) for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]
    if ordered:
        return ordered
    return [n["label"] for n in notes]


def inject(shortlist: list[str], gold: str) -> list[str]:
    out = [gold] + [x for x in shortlist if _norm(x) != _norm(gold)]
    return out[: max(6, len(shortlist) + 1)]


def merged_away_labels(doc: dict, gold: str) -> list[str]:
    """Labels from merge events that match gold but are not active."""
    import disagreement_census as dc

    stages = doc.get("stages") or {}
    active = {
        str(c.get("preferred_label") or c.get("preferred_name") or "")
        for c in (stages.get("registry") or [])
    }
    found = []
    for e in stages.get("events") or []:
        lab = str(e.get("label") or e.get("name") or e.get("from") or "")
        if lab and dc.match(lab, gold) and lab not in active:
            found.append(lab)
    for m in stages.get("merge_audit") or []:
        # child id — resolve via registry history not always available; skip if no label
        pass
    return list(dict.fromkeys(found))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse-from", type=Path, required=True)
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()))
    ap.add_argument("--out-arm", required=True)
    ap.add_argument("--intervention", choices=("j1", "j2", "j3"), default="j1")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    args = ap.parse_args()

    reuse = Path(args.reuse_from)
    out_dir = OUT_ROOT / args.dataset / args.out_arm
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
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "oracle_llm.json", args.model)

    sel_prompt_c = _read("aphhm_c_frontier_selector_candev.txt")
    sel_prompt_m = _read("mosaic_selector.txt")

    def one(case: dict) -> dict[str, Any]:
        cid = str(case.get("source_id") or "")
        if not cid and "__" in str(case.get("case_id") or ""):
            cid = str(case["case_id"]).split("__")[-1].lstrip("0") or "0"
        gold = str(
            case.get("_gold_text")
            or case.get("gold_diagnosis")
            or case.get("gold")
            or ""
        ).strip()
        vignette = str(case.get("vignette") or case.get("text") or "")
        doc = load_stage(reuse, cid)
        if not doc and str(cid).isdigit():
            doc = load_stage(reuse, str(int(cid)))
        if not doc:
            return {"case_id": case.get("case_id"), "source_id": cid, "error": "no_stage", "champion": "", "gold": gold}
        family = detect_family(doc)
        notes = extract_notes(doc, family)
        short = shortlist_of(doc, family, notes)
        if args.intervention == "j3":
            restored = merged_away_labels(doc, gold)
            if not restored and not any(_norm(x) == _norm(gold) for x in short):
                # still inject gold label
                pass
            for lab in restored:
                if not any(_norm(x) == _norm(lab) for x in short):
                    short = [lab] + short
        short = inject(short, gold)
        # notes for shortlist
        by_lab = {_norm(n["label"]): n for n in notes}
        new_notes = []
        for lab in short:
            if _norm(lab) in by_lab:
                new_notes.append(by_lab[_norm(lab)])
            elif _norm(lab) == _norm(gold):
                entry = {"label": gold, "for": [], "against": []}
                if args.intervention == "j2":
                    ev = cached.call(
                        "GoldEvidenceWriter",
                        EVIDENCE_PROMPT,
                        {"vignette": vignette[:6000], "label": gold},
                    )
                    if isinstance(ev, dict):
                        # filter verbatim
                        hay = vignette.lower()
                        entry["for"] = [
                            s for s in (ev.get("for") or []) if isinstance(s, str) and s.lower() in hay
                        ][:4]
                        entry["against"] = [
                            s
                            for s in (ev.get("against") or [])
                            if isinstance(s, str) and s.lower() in hay
                        ][:3]
                new_notes.append(entry)
            else:
                new_notes.append({"label": lab, "for": [], "against": []})

        prompt = sel_prompt_m if family == "mosaic" else sel_prompt_c
        role = "MosaicEvidenceSelector" if family == "mosaic" else "AphhmCFrontierSelector"
        raw = cached.call(
            role,
            prompt,
            {"vignette": vignette[:6000], "shortlist": short, "candidate_notes": new_notes},
        )
        champ = str((raw or {}).get("champion") or "").strip()
        if champ not in short:
            champ = next((x for x in short if _norm(x) == _norm(champ)), short[0] if short else "")
        import disagreement_census as dc

        hit = bool(champ and gold and dc.match(champ, gold))
        out_doc = {
            "case_id": case.get("case_id"),
            "source_id": cid,
            "champion": champ,
            "ordered_diagnoses": [champ] + [x for x in short if x != champ][:4],
            "gold": gold,
            "intervention": args.intervention,
            "family": family,
            "oracle_injected": True,
            "shortlist": short,
            "selector": raw,
            "stages": {
                "mode": f"oracle_{args.intervention}",
                "reuse_from": str(reuse),
                "frontier_selector" if family == "aphhm_c" else "selector": raw,
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
                    for n in new_notes
                ],
            },
            "llm_calls": 1 + (1 if args.intervention == "j2" else 0),
        }
        (out_dir / "case_stages" / f"{cid}.json").write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return {
            "case_id": case.get("case_id"),
            "source_id": cid,
            "champion": champ,
            "gold": gold,
            "hit": hit,
        }

    preds = []
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(one, c): c for c in cases}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result()
                preds.append(r)
                if i % 20 == 0:
                    print(f"  [{i}/{len(cases)}] {r.get('source_id')} -> {r.get('champion')}")
            except Exception as e:
                errors.append({"error": str(e)})
                print("ERR", e)

    # rough hit rate using exact norm match; downstream uses dc.match
    n_hit = sum(1 for p in preds if p.get("hit"))
    summary = {
        "arm": args.out_arm,
        "intervention": args.intervention,
        "reuse_from": str(reuse),
        "n": len(preds),
        "exact_norm_hit": round(n_hit / len(preds), 4) if preds else None,
        "errors": len(errors),
    }
    (out_dir / "oracle_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as fh:
        for p in preds:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
