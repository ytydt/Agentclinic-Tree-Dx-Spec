#!/usr/bin/env python3
"""Score open Top-2 predictions via RelationAwareAnswerMapper (17-case contract)."""
from __future__ import annotations

import argparse
import copy
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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


class _LockedRetriever:
    """Serialize retriever search so shared FAISS/TF-IDF indices stay safe."""

    def __init__(self, inner: Any, lock: threading.Lock) -> None:
        self._inner = inner
        self._lock = lock

    def search(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return self._inner.search(*args, **kwargs)

    def search_for_disease(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return self._inner.search_for_disease(*args, **kwargs)

    def search_for_differential(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return self._inner.search_for_differential(*args, **kwargs)


class _ThreadLocalLLM:
    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._local = threading.local()

    def call_module(self, module: str, prompt: str, payload: Mapping[str, Any]) -> Any:
        client = getattr(self._local, "client", None)
        if client is None:
            client = self._factory()
            self._local.client = client
        return client.call_module(module, prompt, dict(payload))


def _fork_resolver(base: Any) -> Any:
    resolver = copy.copy(base)
    resolver._cache = {}
    return resolver


def build_mapper(
    *,
    mode: str,
    model: str,
    cache_path: Path,
    call_timeout: int = 240,
    dry_run: bool = False,
    workers: int = 1,
) -> RelationAwareAnswerMapper:
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    from baseline_common import SimpleCachedLLM

    workers = max(1, int(workers))
    resolver = load_offline_resolver(ROOT)
    client = None
    if not dry_run and mode != "deterministic_gold_blind":
        def _make_client() -> Any:
            return RobustLLMClient(
                model=model,
                call_timeout=call_timeout,
                max_retries=5,
                timeout_retry_cap=2,
                temperature=0.0,
            )

        client = _ThreadLocalLLM(_make_client) if workers > 1 else _make_client()
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
        elif workers > 1:
            lock = threading.Lock()
            retrievers = {
                name: _LockedRetriever(retriever, lock)
                for name, retriever in retrievers.items()
            }

    mapper = RelationAwareAnswerMapper(
        resolver=resolver if workers == 1 else _fork_resolver(resolver),
        llm=_Adapter() if mode != "deterministic_gold_blind" else None,
        relation_prompt=(PROMPT_DIR / "answer_relation_mapper.txt").read_text(
            encoding="utf-8",
        ),
        critic_prompt=(PROMPT_DIR / "answer_relation_rag_critic.txt").read_text(
            encoding="utf-8",
        ),
        retrievers=retrievers,
    )
    if workers == 1:
        return mapper

    local = threading.local()

    class _PerThreadMapper:
        def map(self, **kwargs: Any) -> dict[str, Any]:
            thread_mapper = getattr(local, "mapper", None)
            if thread_mapper is None:
                thread_mapper = RelationAwareAnswerMapper(
                    resolver=_fork_resolver(resolver),
                    llm=mapper.llm,
                    relation_prompt=mapper.relation_prompt,
                    critic_prompt=mapper.critic_prompt,
                    retrievers=mapper.retrievers,
                    confidence_threshold=mapper.confidence_threshold,
                    rag_top_k=mapper.rag_top_k,
                    rag_max_snippets=mapper.rag_max_snippets,
                    rag_max_chars=mapper.rag_max_chars,
                    strict_total_order=mapper.strict_total_order,
                )
                local.mapper = thread_mapper
            return thread_mapper.map(**kwargs)

    return _PerThreadMapper()  # type: ignore[return-value]


def score_predictions_dir(
    pred_dir: Path,
    cases: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    model: str,
    dry_run: bool = False,
    workers: int = 1,
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
    workers = max(1, int(workers))
    mapper = build_mapper(
        mode=mode,
        model=model,
        cache_path=pred_dir / "cache" / "mapper_llm.json",
        dry_run=dry_run or mode == "deterministic_gold_blind",
        workers=workers,
    )
    jobs: list[tuple[Mapping[str, Any], Sequence[str], str]] = []
    for row in rows:
        case = by_id.get(str(row["case_id"]))
        if case is None:
            continue
        top2 = row.get("top2_diagnoses") or []
        effective_mode = mode
        if dry_run and mode != "deterministic_gold_blind":
            effective_mode = "deterministic_gold_blind"
        jobs.append((case, top2, effective_mode))
    records = [None] * len(jobs)

    def _one(index: int) -> tuple[int, dict[str, Any]]:
        case, top2, effective_mode = jobs[index]
        return index, score_case_with_mapper(
            case=case,
            top2=top2,
            mapper=mapper,
            mode=effective_mode,
        )

    if workers == 1 or len(jobs) <= 1:
        for index in range(len(jobs)):
            _, record = _one(index)
            records[index] = record
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, index) for index in range(len(jobs))]
            for future in as_completed(futures):
                index, record = future.result()
                records[index] = record
    records = [record for record in records if record is not None]
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
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    cases = bc.load_runtime_cases(subset_dir=args.subset_dir, limit=args.limit)
    summary = score_predictions_dir(
        args.pred_dir,
        cases,
        mode=args.mapper_mode,
        model=args.model,
        dry_run=args.dry_run,
        workers=args.workers,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
