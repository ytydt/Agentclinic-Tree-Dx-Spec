#!/usr/bin/env python3
"""Score open Top-2 predictions via RelationAwareAnswerMapper (17-case contract)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    load_offline_resolver,
)
import baseline_common as bc  # noqa: E402

PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"


def top2_to_synthetic_leaves(
    top2: Sequence[str],
    *,
    prefix: str = "pred",
) -> list[dict[str, Any]]:
    """Wrap ordered free-text diagnoses as mapper leaf rows."""
    leaves: list[dict[str, Any]] = []
    for index, label in enumerate(top2, start=1):
        text = str(label or "").strip()
        if not text:
            continue
        leaves.append({
            "leaf_id": f"{prefix}_{index}",
            "leaf_label": text,
            "parent_id": "",
            "parent_label": "",
            "joint_rank": index,
            "posterior": float(max(0.0, 2.0 - index)),
        })
    return leaves


def score_case_with_mapper(
    *,
    case: Mapping[str, Any],
    top2: Sequence[str],
    mapper: RelationAwareAnswerMapper,
    mode: str = "deterministic_gold_blind",
) -> dict[str, Any]:
    leaves = top2_to_synthetic_leaves(top2)
    options = case["options"]
    projection = mapper.map(
        case_id=str(case["case_id"]),
        vignette=str(case["vignette"]),
        question=str(case.get("question") or "What is the most likely diagnosis?"),
        options=options,
        leaves=leaves,
        mode=mode,
    )
    gold_letter = str(case.get("_gold_letter") or "").upper()
    gold_map = (projection.get("option_maps") or {}).get(gold_letter) or {}
    gold_rank = gold_map.get("best_rank")
    option_rank = int(gold_map.get("option_rank") or (len(options) + 1))
    matched = gold_rank is not None
    return {
        "case_id": case["case_id"],
        "source_id": case.get("source_id"),
        "gold_letter": gold_letter,
        "top2_diagnoses": list(top2)[:2],
        "option_top1": bool(matched and option_rank <= 1),
        "option_top2": bool(matched and option_rank <= 2),
        "option_rr": (1.0 / option_rank) if matched else 0.0,
        "option_rank": option_rank if matched else None,
        "projection": projection,
    }


def build_mapper(
    *,
    mode: str,
    model: str,
    cache_path: Path,
    call_timeout: int = 240,
    dry_run: bool = False,
) -> RelationAwareAnswerMapper:
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    import baseline_common as bc_mod
    from baseline_common import SimpleCachedLLM

    resolver = load_offline_resolver(ROOT)
    client = None
    if not dry_run and mode != "deterministic_gold_blind":
        client = RobustLLMClient(
            model=model,
            call_timeout=call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=0.0,
        )
    cached = SimpleCachedLLM(client, cache_path, model)

    class _Adapter:
        def call_module(self, module, prompt, payload):
            return cached.call(module, prompt, dict(payload))

    retrievers = None
    if mode == "typed_llm_disagreement_rag" and not dry_run:
        from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever

        rag_index = ROOT / "data" / "corpus" / "rag_index"
        cpg_index = ROOT / "data" / "corpus" / "cpg_index"
        retrievers = {}
        if rag_index.is_dir():
            retrievers["rag_index"] = RAGRetriever(str(rag_index), device="cpu")
        if cpg_index.is_dir():
            retrievers["cpg_index"] = RAGRetriever(str(cpg_index), device="cpu")
        if not retrievers:
            retrievers = None

    return RelationAwareAnswerMapper(
        resolver=resolver,
        llm=_Adapter() if mode != "deterministic_gold_blind" else None,
        relation_prompt=(PROMPT_DIR / "answer_relation_mapper.txt").read_text(
            encoding="utf-8",
        ),
        critic_prompt=(PROMPT_DIR / "answer_relation_rag_critic.txt").read_text(
            encoding="utf-8",
        ),
        retrievers=retrievers,
    )


def score_predictions_dir(
    pred_dir: Path,
    cases: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    model: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    predictions_path = pred_dir / "predictions.jsonl"
    if not predictions_path.is_file():
        raise FileNotFoundError(predictions_path)
    by_id = {str(case["case_id"]): case for case in cases}
    rows = [
        json.loads(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    mapper = build_mapper(
        mode=mode,
        model=model,
        cache_path=pred_dir / "cache" / "mapper_llm.json",
        dry_run=dry_run or mode == "deterministic_gold_blind",
    )
    records: list[dict[str, Any]] = []
    for row in rows:
        case = by_id.get(str(row["case_id"]))
        if case is None:
            continue
        top2 = row.get("top2_diagnoses") or []
        effective_mode = mode
        if dry_run and mode != "deterministic_gold_blind":
            effective_mode = "deterministic_gold_blind"
        records.append(
            score_case_with_mapper(
                case=case,
                top2=top2,
                mapper=mapper,
                mode=effective_mode,
            )
        )
    summary = {
        "n": len(records),
        "mapper_mode": mode if not dry_run else "deterministic_gold_blind",
        "option_top1": (
            round(sum(bool(r["option_top1"]) for r in records) / len(records), 4)
            if records else None
        ),
        "option_top2": (
            round(sum(bool(r["option_top2"]) for r in records) / len(records), 4)
            if records else None
        ),
        "mrr2": (
            round(sum(float(r["option_rr"]) for r in records) / len(records), 4)
            if records else None
        ),
    }
    out = pred_dir / "mapper"
    out.mkdir(parents=True, exist_ok=True)
    bc.atomic_json(out / "records.json", {"summary": summary, "records": records})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pred-dir", type=Path, required=True)
    parser.add_argument("--subset-dir", type=Path, default=bc.DEFAULT_SUBSET)
    parser.add_argument(
        "--mapper-mode",
        default="deterministic_gold_blind",
        choices=(
            "deterministic_gold_blind",
            "typed_llm",
            "typed_llm_disagreement_rag",
        ),
    )
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cases = bc.load_runtime_cases(subset_dir=args.subset_dir, limit=args.limit)
    summary = score_predictions_dir(
        args.pred_dir,
        cases,
        mode=args.mapper_mode,
        model=args.model,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
