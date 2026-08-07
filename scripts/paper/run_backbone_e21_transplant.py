#!/usr/bin/env python3
"""E21: candidate-set transplant between AB02 and the backbone.

Every backbone selector tested so far (variants b/c/d/e/f/g/h) is at best
neutral against simply taking the first shortlist item, while AB02's evidence
scoring converts 0.47 -> 0.63 on the same lexical ruler. Either AB02's scoring
machinery is doing something the backbone's cannot, or AB02's *candidates* are
what carry the signal.

This runner separates the two by crossing candidate source with selector:

                      selector = first (0 calls)   selector = S4-b (1 call)
  cand = backbone       v0_s4a_k5   (0.36)          v0_s4b_k5   (0.36)
  cand = AB02 leaves    e21b                        e21a

If e21a lands near AB02's 0.63, the candidates carry everything and the
backbone's selector is adequate. If it stays near 0.45, the selector is the
binding constraint and AB02's per-branch evidence context is the missing piece.

Facts and prompts are held fixed at the backbone's (S1 key_facts,
``backbone_select_free.txt``) so the only thing that varies is the candidate set.

Writes only under logs/backbone_v1/diagnosisarena/<arm>/.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx.backbone import _read_prompt  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from run_backbone_v1 import score_da  # noqa: E402

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
SUBSET = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1"
AB02 = ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/annotate"
BB_REF = ROOT / "logs/backbone_v1/diagnosisarena/v0_s4b_k5/case_stages"
OUT_ROOT = ROOT / "logs/backbone_v1/diagnosisarena"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _ab02_leaves(source_id: str) -> list[str]:
    """AB02 level-2 leaves, ordered by posterior (its own decision set)."""
    path = AB02 / "shared_trees" / f"{source_id}.json"
    if not path.is_file():
        return []
    branches = json.loads(path.read_text(encoding="utf-8"))["state"]["branches"]
    rows = [
        v for v in (branches.values() if isinstance(branches, dict) else branches)
        if isinstance(v, dict) and v.get("level") == 2 and v.get("label")
    ]
    rows.sort(key=lambda v: -float(v.get("posterior") or 0.0))
    out: list[str] = []
    for v in rows:
        label = str(v["label"])
        if label.casefold() not in {x.casefold() for x in out}:
            out.append(label)
    return out


def _backbone_ref(source_id: str) -> dict[str, Any]:
    path = BB_REF / f"{source_id}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _select_s4b(cached, vignette: str, key_facts: list[str], shortlist: list[str]) -> tuple[str, dict]:
    raw = cached.call(
        "BackboneSelectFree",
        _read_prompt("backbone_select_free.txt"),
        {
            "vignette": vignette[:2000],
            "key_facts": list(key_facts),
            "shortlist": list(shortlist),
        },
    )
    raw = dict(raw) if isinstance(raw, dict) else {"raw": raw}
    champion = str(raw.get("champion") or "").strip()
    lowered = {x.casefold() for x in shortlist}
    if champion and champion.casefold() not in lowered:
        champion = next(
            (
                x for x in shortlist
                if champion.casefold() in x.casefold() or x.casefold() in champion.casefold()
            ),
            shortlist[0] if shortlist else "",
        )
    if not champion:
        champion = shortlist[0] if shortlist else ""
    return champion, raw


def run_arm(
    arm: str,
    *,
    candidates: str,
    selector: str,
    model: str,
    workers: int,
    dry_run: bool,
) -> Path:
    cases = bc.load_runtime_cases(dataset="diagnosisarena", subset_dir=SUBSET)
    out_dir = OUT_ROOT / arm
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "cache" / "llm_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = out_dir / "case_stages"
    stage_dir.mkdir(parents=True, exist_ok=True)

    client = None if dry_run else RobustLLMClient(
        model=model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
    )
    cached = bc.SimpleCachedLLM(client, cache_path, model)

    def one(case: dict) -> dict[str, Any]:
        source_id = str(case["source_id"])
        ref = _backbone_ref(source_id)
        key_facts = list(((ref.get("stages") or {}).get("s1") or {}).get("key_facts") or [])
        if candidates == "ab02":
            pool = _ab02_leaves(source_id)
        else:
            pool = list(((ref.get("stages") or {}).get("s3") or {}).get("shortlist") or [])
        calls = 0
        raw: dict[str, Any] = {}
        if not pool:
            champion = ""
        elif selector == "first":
            champion = pool[0]
        else:
            champion, raw = _select_s4b(cached, str(case.get("vignette") or ""), key_facts, pool)
            calls = 1
        ordered = [champion] + [x for x in pool if x.casefold() != champion.casefold()]
        ordered = [x for x in ordered if x]
        stages = {
            "candidates": pool,
            "n_candidates": len(pool),
            "key_facts": key_facts,
            "selector": selector,
            "champion": champion,
            "raw": raw,
        }
        _atomic_json(stage_dir / f"{source_id}.json", {"source_id": source_id, **stages})
        return {
            "arm": arm,
            "case_id": case["case_id"],
            "source_id": source_id,
            "dataset": "diagnosisarena",
            "list_k": len(ordered[:2]),
            "ordered_diagnoses": ordered,
            "top2_diagnoses": ordered[:2],
            "cost": {"llm_calls": calls, "retrieval_calls": 0},
            "config": {"candidates": candidates, "selector": selector},
        }

    preds: list[dict] = []
    errors: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool_ex:
        futures = {pool_ex.submit(one, c): c for c in cases}
        for i, fut in enumerate(as_completed(futures), 1):
            case = futures[fut]
            try:
                preds.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                errors.append({
                    "case_id": case["case_id"],
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace": traceback.format_exc()[-1500:],
                })
                print(f"  ERROR {case['case_id']}: {exc}", flush=True)
            if i % 20 == 0:
                print(f"  [{arm}] {i}/{len(cases)}", flush=True)

    preds.sort(key=lambda r: str(r["source_id"]))
    (out_dir / "predictions.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in preds), encoding="utf-8"
    )
    total = sum(int(r["cost"]["llm_calls"]) for r in preds)
    _atomic_json(out_dir / "summary.json", {
        "arm": arm,
        "dataset": "diagnosisarena",
        "n_predictions": len(preds),
        "n_errors": len(errors),
        "llm_calls_total": total,
        "llm_calls_mean": round(total / max(1, len(preds)), 2),
        "candidates": candidates,
        "selector": selector,
        "errors": errors,
        "finished_at": _utc(),
    })
    _atomic_json(out_dir / "manifest.json", {
        "arm": arm,
        "dataset": "diagnosisarena",
        "subset": str(SUBSET),
        "model": model,
        "candidate_source": candidates,
        "selector": selector,
        "facts_from": str(BB_REF),
        "prompt": "backbone_select_free.txt",
        "n_cases": len(cases),
    })
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--candidates", default="ab02", choices=("ab02", "backbone"))
    ap.add_argument("--selector", default="s4b", choices=("s4b", "first"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--score", action="store_true")
    args = ap.parse_args()

    out_dir = run_arm(
        args.arm,
        candidates=args.candidates,
        selector=args.selector,
        model=args.model,
        workers=int(args.workers),
        dry_run=bool(args.dry_run),
    )
    if args.score:
        score_da(out_dir, SUBSET, args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
