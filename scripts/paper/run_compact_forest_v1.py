#!/usr/bin/env python3
"""CompactForest v1 / v1.1: endogenous multi-axis pool in ≤2–3 LLM calls.

Call budget:
  [optional --with-facts] MosaicKeyFacts — decisive spans + rare_hooks
  1) MosaicBatchedAxes — single call emitting syndrome/mechanism/modality views
  2) AphhmC candev frontier selector
Optional (--x3-evidence): evidence-consistent sibling dedupe before selector (0 LLM).

Does NOT reuse pre-run forest stages.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx import near_dedup as nd  # noqa: E402
from agentclinic_tree_dx.backbone import _read_prompt  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from agentclinic_tree_dx.mosaic import (  # noqa: E402
    EvidenceFact,
    GlobalConceptRegistry,
    MosaicPipeline,
)
from run_backbone_v1 import SUBSETS  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def build_pool_from_batched(raw: Mapping[str, Any], mosaic: MosaicPipeline) -> tuple[GlobalConceptRegistry, dict, dict]:
    registry = GlobalConceptRegistry(resolver=mosaic.resolver)
    evidence: dict[str, EvidenceFact] = {}
    # shared key evidence
    for span in _as_list(raw.get("key_evidence_spans")):
        span = str(span or "").strip()
        if not span:
            continue
        eid = f"KE{len(evidence)+1:03d}"
        evidence[eid] = EvidenceFact(evidence_id=eid, raw_span=span, source_view="batched")
    name_sets: list[set[str]] = []
    views = _as_list(raw.get("views"))
    if not views:
        # tolerate flat candidates with view field
        views = [{"view": "batched", "candidates": _as_list(raw.get("candidates"))}]
    for vi, view_block in enumerate(views):
        if not isinstance(view_block, dict):
            continue
        view = str(view_block.get("view") or f"view{vi}")
        block = {
            "candidates": _as_list(view_block.get("candidates")),
            "key_evidence_spans": [],
        }
        names = {
            str(x.get("name") or "")
            for x in block["candidates"]
            if isinstance(x, dict)
        }
        name_sets.append(names)
        mosaic._ingest_generator(
            registry=registry,
            evidence=evidence,
            raw=block,
            view=view,
            eid_prefix=view.upper()[:4] or f"V{vi}",
        )
    registry.score()
    frontier = registry.two_lane_frontier(mosaic.main_k, mosaic.protected_k)
    state = mosaic._diagnose_state(registry, evidence, frontier, name_sets)
    stages = {
        "mode": "compact_forest_v1",
        "batched_axes": raw,
        "state_after_axes": state,
        "registry": [c.__dict__ if hasattr(c, "__dict__") else c for c in []],  # filled below
    }
    # serialize concepts for notes
    reg_docs = []
    for c in registry.concepts.values():
        if getattr(c, "status", "live") not in ("live", None, ""):
            # CandidateConcept uses status live
            pass
        reg_docs.append(
            {
                "concept_id": c.concept_id,
                "preferred_name": c.preferred_name,
                "preferred_label": c.preferred_name,
                "generator_views": list(c.generator_views),
                "axis_nodes": list(c.axis_nodes),
                "supporting_evidence": list(c.supporting_evidence),
                "contradicting_evidence": list(c.contradicting_evidence),
                "support_spans": [
                    evidence[e].raw_span for e in c.supporting_evidence if e in evidence
                ],
                "contradict_spans": [
                    evidence[e].raw_span for e in c.contradicting_evidence if e in evidence
                ],
                "score_logit": getattr(c, "score_logit", None),
                "protected_reason": c.protected_reason,
                "status": c.status,
            }
        )
    stages["registry"] = reg_docs
    stages["evidence"] = [
        {"evidence_id": e.evidence_id, "raw_span": e.raw_span, "source_view": e.source_view}
        for e in evidence.values()
    ]
    stages["frontier"] = [
        {
            "preferred_name": c.preferred_name,
            "preferred_label": c.preferred_name,
            "support_spans": [
                evidence[e].raw_span for e in c.supporting_evidence if e in evidence
            ],
            "contradict_spans": [
                evidence[e].raw_span for e in c.contradicting_evidence if e in evidence
            ],
            "score_logit": getattr(c, "score_logit", None),
        }
        for c in frontier
    ]
    return registry, evidence, stages


def notes_from_stages(stages: dict, max_n: int = 10) -> tuple[list[str], list[dict]]:
    """Build selector shortlist: prefer scored live registry (disease-like), then frontier."""
    NON_DX = {
        "histopathology",
        "histopathological examination",
        "immunohistochemistry",
        "genetic testing",
        "mri",
        "ct",
        "biopsy",
        "inflammation",
        "abnormal angiogenesis",
    }

    def _ok(lab: str) -> bool:
        n = lab.strip().lower()
        if not n or len(n) < 4:
            return False
        if n in NON_DX:
            return False
        # bare gene / single token all-caps-ish
        if n.isupper() and len(n.split()) == 1 and len(n) <= 8:
            return False
        return True

    reg_notes = []
    for c in stages.get("registry") or []:
        lab = str(c.get("preferred_label") or c.get("preferred_name") or "").strip()
        if not lab or not _ok(lab):
            continue
        if c.get("status") not in (None, "", "live", "active"):
            continue
        reg_notes.append(
            {
                "label": lab,
                "for": list(c.get("support_spans") or [])[:4],
                "against": list(c.get("contradict_spans") or [])[:3],
                "score": c.get("score_logit"),
            }
        )
    reg_notes.sort(
        key=lambda n: (-(n["score"] if n["score"] is not None else float("-inf")), n["label"])
    )
    if reg_notes:
        short = [n["label"] for n in reg_notes[:max_n]]
        return short, reg_notes[:max_n]

    frontier = stages.get("frontier") or []
    notes = []
    short = []
    for c in frontier:
        lab = str(c.get("preferred_label") or c.get("preferred_name") or "").strip()
        if not lab or not _ok(lab):
            continue
        short.append(lab)
        notes.append(
            {
                "label": lab,
                "for": list(c.get("support_spans") or [])[:4],
                "against": list(c.get("contradict_spans") or [])[:3],
                "score": c.get("score_logit"),
            }
        )
    return short[:max_n], notes[:max_n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()))
    ap.add_argument("--arm", default="compact_forest_v1")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument(
        "--x3-evidence",
        action="store_true",
        help="evidence-consistent sibling dedupe before selector (no gold)",
    )
    ap.add_argument(
        "--x3-oracle-gold",
        action="store_true",
        help="drop near-gold non-gold siblings using case gold (eval-only)",
    )
    ap.add_argument(
        "--with-facts",
        action="store_true",
        help="3-call mode: MosaicKeyFacts then BatchedAxes then selector",
    )
    ap.add_argument(
        "--shortlist-k",
        type=int,
        default=8,
        help="max candidates passed to selector (default 8)",
    )
    args = ap.parse_args()

    ds_key = args.dataset
    subset = SUBSETS[ds_key]
    if ds_key.startswith("medcasereasoning"):
        ds_name, out_ds = "medcasereasoning", ds_key
    elif ds_key.startswith("diagnosisarena_heldout"):
        ds_name, out_ds = "diagnosisarena", ds_key
    else:
        ds_name, out_ds = "diagnosisarena", "diagnosisarena"

    out_dir = OUT_ROOT / out_ds / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)

    cases = bc.load_runtime_cases(
        dataset=ds_name,
        subset_dir=subset,
        case_ids=list(args.case_id or []),
        limit=int(args.limit or 0),
    )
    client = RobustLLMClient(
        model=args.model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
    )
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "compact_v1_llm.json", args.model)
    # helper mosaic for ingest/score/diagnose only (no run)
    mosaic = MosaicPipeline(cached, mode="forest", max_calls=4)
    prompt_facts = _read_prompt("mosaic_key_facts.txt")
    prompt_axes = _read_prompt("mosaic_batched_axes.txt")
    prompt_sel = (PROMPT_DIR / "aphhm_c_frontier_selector_candev.txt").read_text(encoding="utf-8")
    shortlist_k = max(4, int(args.shortlist_k))
    budget = (
        "1 key_facts + 1 batched_axes + 1 aphhm_selector"
        if args.with_facts
        else "1 batched_axes + 1 aphhm_selector"
    )

    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "arm": args.arm,
                "dataset": out_ds,
                "n_cases": len(cases),
                "budget": budget,
                "with_facts": bool(args.with_facts),
                "shortlist_k": shortlist_k,
                "x3_evidence": bool(args.x3_evidence),
                "x3_oracle_gold": bool(args.x3_oracle_gold),
                "created_at": _utc(),
                "schema_version": "compact_forest_v1_1",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def one(case: Mapping[str, Any]) -> dict[str, Any]:
        cid = str(case.get("source_id") or case.get("case_id") or "")
        vignette = str(case.get("vignette") or "")
        gold = str(case.get("_gold_text") or case.get("gold") or "").strip()
        llm_calls = 0
        facts_raw: dict[str, Any] = {}
        axes_payload: dict[str, Any] = {"vignette": vignette[:6000]}
        if args.with_facts:
            facts_raw = cached.call(
                "MosaicKeyFacts",
                prompt_facts,
                {"vignette": vignette[:6000]},
            ) or {}
            llm_calls += 1
            axes_payload["key_facts"] = list(facts_raw.get("facts") or [])[:10]
            axes_payload["rare_hooks"] = list(facts_raw.get("rare_hooks") or [])[:8]
        raw = cached.call("MosaicBatchedAxes", prompt_axes, axes_payload)
        llm_calls += 1
        _, _, stages = build_pool_from_batched(raw or {}, mosaic)
        stages["vignette_chars"] = len(vignette)
        if facts_raw:
            stages["key_facts"] = facts_raw
        short, notes = notes_from_stages(stages, max_n=shortlist_k)
        x3_meta = {}
        if args.x3_oracle_gold and gold:
            before = list(short)
            short = nd.x3_drop_near_siblings(short, gold)
            by = {n["label"]: n for n in notes}
            notes = [by.get(s, {"label": s, "for": [], "against": []}) for s in short]
            x3_meta = {"mode": "oracle_gold", "before": len(before), "after": len(short)}
        elif args.x3_evidence:
            before = len(notes)
            notes = nd.evidence_consistent_sibling_dedupe(notes)
            short = [n["label"] for n in notes]
            x3_meta = {"mode": "evidence", "before": before, "after": len(short)}

        raw_sel = cached.call(
            "AphhmCFrontierSelector",
            prompt_sel,
            {
                "vignette": vignette[:6000],
                "shortlist": short[:shortlist_k],
                "candidate_notes": notes[:shortlist_k],
            },
        )
        llm_calls += 1
        champ = str((raw_sel or {}).get("champion") or "").strip()
        if champ not in short and short:
            champ = next((x for x in short if x.lower() == champ.lower()), short[0])
        ordered = [champ] + [x for x in short if x != champ][:4] if short else []
        state = stages.get("state_after_axes") or {}
        out_doc = {
            "source_id": cid,
            "case_id": case.get("case_id"),
            "champion": champ,
            "ordered_diagnoses": ordered,
            "llm_calls": llm_calls,
            "stages": {
                **stages,
                "frontier_selector": raw_sel,
                "selector_family": "aphhm_c_candev",
                "x3": x3_meta,
                "mode": "compact_forest_v1_1",
            },
            "metrics": {
                "llm_calls": llm_calls,
                "top_margin": state.get("top_margin"),
                "unexplained_n": (
                    len(state.get("unexplained_specific_evidence") or [])
                    if isinstance(state.get("unexplained_specific_evidence"), list)
                    else state.get("unexplained_specific_evidence")
                ),
                "pool_n": len(stages.get("registry") or []),
            },
        }
        (out_dir / "case_stages" / f"{cid}.json").write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return {
            "source_id": cid,
            "ordered_diagnoses": ordered,
            "champion": champ,
            "cost": {"llm_calls": llm_calls},
            "top_margin": state.get("top_margin"),
            "pool_n": len(stages.get("registry") or []),
        }

    preds = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(one, c) for c in cases]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            preds.append(r)
            if i % 25 == 0 or i == len(cases):
                print(
                    f"  [{i}/{len(cases)}] {r.get('source_id')} -> {r.get('champion')} "
                    f"margin={r.get('top_margin')}"
                )
    (out_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in preds) + "\n", encoding="utf-8"
    )
    print(json.dumps({"arm": args.arm, "n": len(preds), "out": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
