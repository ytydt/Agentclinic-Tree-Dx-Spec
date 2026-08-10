#!/usr/bin/env python3
"""I5: cross-arm candidate transplant into e7 S4-b (B06 supervisor / APHHM leaves).

Separates candidate quality from final-selection quality.
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
import disagreement_census as dc  # noqa: E402
from agentclinic_tree_dx.backbone import BackbonePipeline, _read_prompt  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"


def b06_candidates(run_dir: Path, cid: str) -> list[str]:
    traces = dc.load_traces(run_dir)
    tr = traces.get(cid)
    if not tr:
        return []
    out: list[str] = []
    sup = tr.get("supervisor") or {}
    for x in sup.get("top2_diagnoses") or []:
        lab = str(x.get("diagnosis") if isinstance(x, dict) else x)
        if lab and lab.casefold() not in {o.casefold() for o in out}:
            out.append(lab)
    for turn in tr.get("discussion") or []:
        if not isinstance(turn, dict):
            continue
        for key, block in turn.items():
            if not isinstance(block, dict):
                continue
            for x in block.get("top2_diagnoses") or block.get("ranked_diagnoses") or []:
                lab = str(x.get("diagnosis") if isinstance(x, dict) else x)
                if lab and lab.casefold() not in {o.casefold() for o in out}:
                    out.append(lab)
    return out[:5]


def aphhm_leaves(ann_dir: Path, cid: str) -> list[str]:
    tree = ann_dir / "shared_trees" / f"{cid}.json"
    if not tree.is_file():
        return []
    doc = json.loads(tree.read_text(encoding="utf-8"))
    branches = (doc.get("state") or {}).get("branches") or {}
    rows = [
        v
        for v in (branches.values() if isinstance(branches, dict) else branches)
        if isinstance(v, dict) and int(v.get("level") or -1) == 2 and v.get("label")
    ]
    rows.sort(key=lambda v: -float(v.get("posterior") or 0.0))
    out = []
    for v in rows:
        lab = str(v["label"])
        if lab.casefold() not in {x.casefold() for x in out}:
            out.append(lab)
    return out[:8]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--slice", required=True, help="census slice name e.g. d2_seq100")
    ap.add_argument("--cand-source", choices=("b06", "aphhm"), required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    args = ap.parse_args()

    slices = dc.DA_SLICES if args.dataset.startswith("da") or "diagnosis" in args.dataset else dc.MCR_SLICES
    # allow both census slice names and dataset keys
    if args.slice in dc.DA_SLICES:
        spec = dc.DA_SLICES[args.slice]
        ds_out = {
            "d2_seq100": "diagnosisarena",
            "d2_heldout100": "diagnosisarena_heldout",
            "d2_heldout200b": "diagnosisarena_heldout200b",
        }[args.slice]
        subset = ROOT / spec["subset"]
        e7 = ROOT / spec["e7"]
        b06 = ROOT / spec["B06"] if spec.get("B06") else None
        aph = ROOT / spec["APHHM"] if spec.get("APHHM") else None
        ds_runtime = "diagnosisarena"
    else:
        spec = dc.MCR_SLICES[args.slice]
        ds_out = {
            "mcr_v1": "medcasereasoning",
            "mcr_v2": "medcasereasoning_v2",
            "mcr_200b": "medcasereasoning_200b",
        }[args.slice]
        subset = ROOT / spec["subset"]
        e7 = ROOT / spec["e7"]
        b06 = ROOT / spec["B06"] if spec.get("B06") else None
        aph = ROOT / spec["APHHM"] if spec.get("APHHM") else None
        ds_runtime = "medcasereasoning"

    out_dir = OUT_ROOT / ds_out / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)
    cache_path = out_dir / "cache" / "backbone_llm.json"
    cache_path.parent.mkdir(exist_ok=True)

    cases = bc.load_runtime_cases(
        dataset=ds_runtime,
        subset_dir=subset,
        case_ids=list(args.case_id or []),
        limit=int(args.limit or 0),
    )
    from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

    client = RobustLLMClient(
        model=args.model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
    )
    cached = bc.SimpleCachedLLM(client, cache_path, args.model)
    pipe = BackbonePipeline(
        cached, select_variant="b", max_k=5, entrance="llm_ddx", s2_k=3, s2_mode="complement"
    )

    def one(case: dict) -> dict:
        cid = str(case["source_id"])
        stage_path = out_dir / "case_stages" / f"{cid}.json"
        if stage_path.is_file():
            return json.loads(stage_path.read_text())
        prior = json.loads((e7 / "case_stages" / f"{cid}.json").read_text())
        stages = dict(prior.get("stages") or {})
        if args.cand_source == "b06":
            cands = b06_candidates(b06, cid) if b06 else []
        else:
            cands = aphhm_leaves(aph, cid) if aph else []
        if not cands:
            # fall back to e7 s3
            cands = list((stages.get("s3") or {}).get("shortlist") or [])
        s3 = dict(stages.get("s3") or {})
        s3["shortlist"] = cands[:5]
        s3["transplant_source"] = args.cand_source
        stages["s3"] = s3
        stages.pop("s4", None)
        result = pipe.run(
            case_id=str(case["case_id"]),
            vignette=str(case["vignette"]),
            question=str(case.get("question") or "What is the most likely diagnosis?"),
            reuse_stages={"s1": stages.get("s1"), "s2": stages.get("s2"), "s3": s3, "s3_max_k": 5},
        )
        doc = {
            "case_id": case["case_id"],
            "source_id": cid,
            "champion": result.champion,
            "ordered_diagnoses": list(result.ordered_diagnoses),
            "llm_calls": result.llm_calls,
            "stages": result.stages,
            "transplant_source": args.cand_source,
            "transplant_cands": cands,
        }
        stage_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return doc

    preds = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(one, c): c for c in cases}
        for i, fut in enumerate(as_completed(futs), 1):
            doc = fut.result()
            preds.append(
                {
                    "arm": args.arm,
                    "case_id": doc["case_id"],
                    "source_id": doc["source_id"],
                    "dataset": ds_out,
                    "list_k": 2,
                    "ordered_diagnoses": doc.get("ordered_diagnoses") or [],
                    "top2_diagnoses": (doc.get("ordered_diagnoses") or [])[:2],
                    "cost": {"llm_calls": doc.get("llm_calls") or 0},
                }
            )
            if i % 25 == 0:
                print(f"[i5] {i}/{len(cases)}")

    with (out_dir / "predictions.jsonl").open("w") as f:
        for p in sorted(preds, key=lambda x: int(x["source_id"]) if str(x["source_id"]).isdigit() else x["source_id"]):
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"wrote {len(preds)} preds → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
