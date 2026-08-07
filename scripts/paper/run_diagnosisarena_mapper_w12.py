#!/usr/bin/env python3
"""Run RelationAwareAnswerMapper on downstream Top-2 case results (workers=12).

Inputs (from run_diagnosisarena_downstream_top2.py):
  case_results/*.json with l2.final_ranking_ids / final_ranking_labels
  normalized_cases.json with source_options + gold_option

No tree regenerate; leaves are built from joint ranking rows.

Opt-in (default OFF):
  --synonym-bind-repair  Approach A empty-bind repair + re-rank after typed map
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

import diagnosisarena_adapter as da  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    leaf_rows_from_tree,
    load_offline_resolver,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
import mapper_bind_repair as mbr  # noqa: E402

DEFAULT_DOWNSTREAM = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "downstream_top2_w12_v1"
)
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
# Approach A harness hook (mapper-stage synonym bind); production default OFF.
DEFAULT_SYNONYM_BIND_REPAIR = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    da._atomic_json(path, payload)


def _split_case_text(case_text: str) -> tuple[str, str]:
    text = str(case_text or "")
    if "\nOptions:" in text:
        body, _opts = text.split("\nOptions:", 1)
        return body.strip(), "What is the most likely diagnosis?"
    return text.strip(), "What is the most likely diagnosis?"


def _tree_from_ranking_labels(
    ranking_labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Minimal branch dict so leaf_rows_from_tree can attach joint ranks."""
    branches: dict[str, dict[str, Any]] = {}
    for row in ranking_labels:
        leaf_id = str(row.get("id") or "")
        parent_id = str(row.get("parent") or "")
        label = str(row.get("label") or "").strip()
        if not leaf_id or not label:
            continue
        if parent_id and parent_id not in branches:
            branches[parent_id] = {
                "id": parent_id,
                "label": "",
                "level": 1,
                "parent": None,
                "children": [],
                "posterior": 0.0,
            }
        branches[leaf_id] = {
            "id": leaf_id,
            "label": label,
            "level": 2,
            "parent": parent_id or None,
            "children": [],
            "posterior": 0.0,
        }
        if parent_id and parent_id in branches:
            kids = list(branches[parent_id].get("children") or [])
            if leaf_id not in kids:
                kids.append(leaf_id)
            branches[parent_id]["children"] = kids
    return {"branches": branches}


def _map_one(payload: Mapping[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    case = dict(payload["case"])
    case_id = str(case["id"])
    out_path = Path(payload["out_path"])
    if payload.get("resume") and out_path.is_file():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if existing.get("status") == "OK":
            return existing
    try:
        result = json.loads(Path(payload["result_path"]).read_text(encoding="utf-8"))
        if result.get("status") != "OK":
            raise RuntimeError("upstream case status=%s" % result.get("status"))
        l2 = result.get("l2") or {}
        ranking_ids = list(l2.get("final_ranking_ids") or ())
        ranking_labels = list(l2.get("final_ranking_labels") or ())
        if not ranking_ids and ranking_labels:
            ranking_ids = [str(row.get("id")) for row in ranking_labels]
        tree = _tree_from_ranking_labels(ranking_labels)
        leaves = leaf_rows_from_tree(tree, ranking_ids)
        if not leaves:
            # Fallback: synthesize leaf rows directly from ranking labels.
            leaves = [
                {
                    "leaf_id": str(row.get("id") or ("L%d" % index)),
                    "leaf_label": str(row.get("label") or ""),
                    "parent_id": str(row.get("parent") or ""),
                    "parent_label": "",
                    "joint_rank": int(row.get("rank") or index),
                    "posterior": 0.0,
                }
                for index, row in enumerate(ranking_labels, start=1)
                if str(row.get("label") or "").strip()
            ]
        options = da.normalize_options(
            (case.get("annotation") or {}).get("source_options") or {}
        )
        if not options:
            raise RuntimeError("missing source_options")
        vignette, question = _split_case_text(str(case["case_text"]))

        llm = RobustLLMClient(
            model=payload["model"],
            call_timeout=float(payload["call_timeout"]),
            max_retries=5,
            timeout_retry_cap=2,
            temperature=0.0,
        )
        cache_path = Path(payload["cache_path"])
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cached = bfs_eval.CachedLLM(llm, cache_path, payload["model"])

        class _Adapter:
            def call_module(self, module, prompt, body):
                return cached.call(module, prompt, dict(body))

        retrievers = {}
        if payload["mapper_mode"] == "typed_llm_disagreement_rag":
            from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever

            for name, path in (
                ("rag_index", ROOT / "data" / "corpus" / "rag_index"),
                ("cpg_index", ROOT / "data" / "corpus" / "cpg_index"),
            ):
                retriever = RAGRetriever(path, device="cpu")
                if retriever.is_ready:
                    retrievers[name] = retriever

        mapper = RelationAwareAnswerMapper(
            resolver=load_offline_resolver(ROOT),
            llm=_Adapter(),
            relation_prompt=Path(payload["relation_prompt"]).read_text(encoding="utf-8"),
            critic_prompt=Path(payload["critic_prompt"]).read_text(encoding="utf-8"),
            retrievers=retrievers,
        )
        projection = mapper.map(
            case_id=case_id,
            vignette=vignette,
            question=question,
            options=options,
            leaves=leaves,
            mode=payload["mapper_mode"],
        )
        gold_letter = str(case.get("gold_option") or "").upper()
        synonym_meta: dict[str, Any] = {"enabled": False}
        if bool(payload.get("synonym_bind_repair")):
            scored = mbr.rescore_after_synonym_bind(
                {
                    "gold_letter": gold_letter,
                    "gold_option_text": options.get(gold_letter),
                    "projection": projection,
                },
                leaves,
                options,
                min_score=float(
                    payload.get("synonym_bind_min_score")
                    or mbr.DEFAULT_SYNONYM_BIND_MIN_SCORE
                ),
                bridge_path=payload.get("synonym_bind_bridge")
                or mbr.DEFAULT_BRIDGE_PATH,
            )
            projection = dict(scored.get("projection") or projection)
            gold_rank = scored.get("gold_best_rank")
            gold_option_rank = int(
                scored.get("gold_option_rank") or (len(options) + 1)
            )
            synonym_meta = {
                "enabled": True,
                "bind_repair_applied": bool(scored.get("bind_repair_applied")),
                "n_options_bind_repaired": int(
                    scored.get("n_options_bind_repaired") or 0
                ),
                "min_score": float(
                    payload.get("synonym_bind_min_score")
                    or mbr.DEFAULT_SYNONYM_BIND_MIN_SCORE
                ),
            }
            option_top1 = bool(scored.get("option_top1"))
            option_top2 = bool(scored.get("option_top2"))
            option_rr = float(scored.get("option_rr") or 0.0)
        else:
            option_maps = projection.get("option_maps") or {}
            gold_map = option_maps.get(gold_letter) or {}
            gold_rank = gold_map.get("best_rank")
            gold_option_rank = int(
                gold_map.get("option_rank") or (len(options) + 1)
            )
            option_top1 = bool(gold_rank is not None and gold_option_rank <= 1)
            option_top2 = bool(gold_rank is not None and gold_option_rank <= 2)
            option_rr = (
                1.0 / gold_option_rank if gold_rank is not None else 0.0
            )
        record = {
            "schema_version": 1,
            "status": "OK",
            "case_id": case_id,
            "mapper_mode": payload["mapper_mode"],
            "gold_letter": gold_letter,
            "gold_option_text": options.get(gold_letter),
            "gold_diagnosis": str(case.get("gold") or ""),
            "gold_best_rank": gold_rank,
            "gold_option_rank": gold_option_rank,
            "option_top1": option_top1,
            "option_top2": option_top2,
            "option_rr": option_rr,
            "n_leaves": len(leaves),
            "n_options": len(options),
            "joint_top1_label": (
                ranking_labels[0].get("label") if ranking_labels else None
            ),
            "joint_top2_label": (
                ranking_labels[1].get("label") if len(ranking_labels) > 1 else None
            ),
            "synonym_bind_repair": synonym_meta,
            "projection": projection,
            "duration_seconds": round(time.monotonic() - started, 3),
            "worker_pid": os.getpid(),
        }
    except Exception as exc:  # noqa: BLE001
        import traceback
        record = {
            "schema_version": 1,
            "status": "ERROR",
            "case_id": case_id,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc()[-2000:],
            "duration_seconds": round(time.monotonic() - started, 3),
            "option_top1": False,
            "option_top2": False,
        }
    _atomic_json(out_path, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downstream-dir", type=Path, default=DEFAULT_DOWNSTREAM)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument(
        "--mapper-mode",
        default="typed_llm",
        choices=[
            "deterministic_gold_blind",
            "typed_llm",
            "typed_llm_disagreement_rag",
        ],
    )
    parser.add_argument(
        "--synonym-bind-repair",
        action="store_true",
        default=DEFAULT_SYNONYM_BIND_REPAIR,
        help=(
            "Opt-in Approach A: after typed mapper, repair empty option→leaf "
            "binds via lexical/disease_name_bridge then re-rank (default off)."
        ),
    )
    parser.add_argument(
        "--synonym-bind-min-score",
        type=float,
        default=mbr.DEFAULT_SYNONYM_BIND_MIN_SCORE,
        help="Min lexical/bridge score for synonym bind-repair (default 0.70).",
    )
    parser.add_argument(
        "--synonym-bind-bridge",
        type=Path,
        default=mbr.DEFAULT_BRIDGE_PATH,
        help="Path to disease_name_bridge.json for synonym bind-repair.",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    down = Path(args.downstream_dir).expanduser().resolve()
    cases_path = down / "normalized_cases.json"
    results_dir = down / "case_results"
    if not cases_path.is_file() or not results_dir.is_dir():
        raise FileNotFoundError("missing downstream cases/results under %s" % down)

    cases = {
        str(case["id"]): case
        for case in json.loads(cases_path.read_text(encoding="utf-8")).get("cases") or ()
    }
    result_paths = sorted(
        path for path in results_dir.glob("*.json")
        if path.stem in cases
    )
    if not result_paths:
        raise RuntimeError("no overlapping case_results")

    mapper_dir = down / "mapper"
    proj_dir = mapper_dir / "projections"
    cache_dir = down / "cache" / "mapper"
    proj_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    relation_prompt = PROMPT_DIR / "answer_relation_mapper.txt"
    critic_prompt = PROMPT_DIR / "answer_relation_rag_critic.txt"
    synonym_on = bool(
        getattr(args, "synonym_bind_repair", DEFAULT_SYNONYM_BIND_REPAIR)
    )
    payloads = []
    for path in result_paths:
        case_id = path.stem
        payloads.append({
            "case": cases[case_id],
            "result_path": str(path),
            "out_path": str(proj_dir / ("%s.json" % case_id)),
            "cache_path": str(cache_dir / ("%s.json" % case_id)),
            "model": args.model,
            "call_timeout": args.call_timeout,
            "mapper_mode": args.mapper_mode,
            "relation_prompt": str(relation_prompt),
            "critic_prompt": str(critic_prompt),
            "resume": bool(args.resume),
            "synonym_bind_repair": synonym_on,
            "synonym_bind_min_score": float(args.synonym_bind_min_score),
            "synonym_bind_bridge": str(Path(args.synonym_bind_bridge).expanduser()),
        })

    workers = min(int(args.workers), len(payloads))
    print(
        "=== mapper workers=%d n=%d mode=%s synonym_bind=%s ==="
        % (workers, len(payloads), args.mapper_mode, synonym_on),
        flush=True,
    )
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_map_one, payload): payload["case"]["id"]
            for payload in payloads
        }
        done = 0
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = {
                    "case_id": case_id,
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "option_top1": False,
                    "option_top2": False,
                }
            records.append(row)
            done += 1
            print(
                "[mapper] %d/%d %s %s opt@1=%s opt@2=%s dur=%s"
                % (
                    done,
                    len(payloads),
                    case_id,
                    row.get("status"),
                    row.get("option_top1"),
                    row.get("option_top2"),
                    row.get("duration_seconds"),
                ),
                flush=True,
            )
    wall = time.monotonic() - started
    records.sort(key=lambda row: str(row.get("case_id") or ""))
    ok = [row for row in records if row.get("status") == "OK"]
    n_ok = len(ok)
    adjudication_rows = []
    for row in ok:
        case = cases[str(row["case_id"])]
        options = da.normalize_options(
            (case.get("annotation") or {}).get("source_options") or {}
        )
        option_maps = (row.get("projection") or {}).get("option_maps") or {}
        for letter, text in sorted(options.items()):
            mapped = option_maps.get(letter) or {}
            adjudication_rows.append({
                "case_id": row["case_id"],
                "option_letter": letter,
                "option_text": text,
                "mapper_mode": args.mapper_mode,
                "relation_type": mapped.get("relation_type", "unknown"),
                "best_rank": mapped.get("best_rank"),
                "option_rank": mapped.get("option_rank"),
                "confidence": mapped.get("confidence"),
                "rationale": mapped.get("rationale"),
                "is_gold_option": (
                    str(letter).upper() == str(case.get("gold_option") or "").upper()
                ),
                "review_status": "pending_human",
            })

    summary = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "phase": "mapper",
        "mapper_mode": args.mapper_mode,
        "synonym_bind_repair": synonym_on,
        "synonym_bind_min_score": float(args.synonym_bind_min_score),
        "workers": workers,
        "n_cases": len(records),
        "n_ok": n_ok,
        "n_error": len(records) - n_ok,
        "wall_seconds": round(wall, 3),
        "throughput_cases_per_hour": (
            round(len(records) / wall * 3600.0, 3) if wall > 0 else None
        ),
        "mean_case_seconds": (
            round(
                statistics.mean(
                    float(row["duration_seconds"])
                    for row in ok
                    if row.get("duration_seconds") is not None
                ),
                3,
            ) if ok else None
        ),
        "option_top1": (
            round(sum(bool(row.get("option_top1")) for row in ok) / n_ok, 4)
            if n_ok else None
        ),
        "option_top2": (
            round(sum(bool(row.get("option_top2")) for row in ok) / n_ok, 4)
            if n_ok else None
        ),
        "option_top1_count": sum(bool(row.get("option_top1")) for row in ok),
        "option_top2_count": sum(bool(row.get("option_top2")) for row in ok),
        "mean_option_rr": (
            round(
                statistics.mean(float(row.get("option_rr") or 0.0) for row in ok),
                4,
            ) if ok else None
        ),
        "downstream_dir": str(down.relative_to(ROOT)),
        "errors": [
            {"case_id": row.get("case_id"), "error": row.get("error")}
            for row in records if row.get("status") != "OK"
        ],
        "note": (
            "MCQ option @1/@2 via RelationAwareAnswerMapper on joint ranking "
            "leaves; gold_option from normalized_cases (evaluation only)."
            + (
                " synonym_bind_repair=ON (Approach A, opt-in)."
                if synonym_on else
                " synonym_bind_repair=OFF (default)."
            )
        ),
    }
    _atomic_json(mapper_dir / "records.json", {
        "records": records,
        "summary": summary,
    })
    _atomic_json(mapper_dir / "adjudication_blind_v1.json", {
        "schema_version": 1,
        "human_signed_off": False,
        "mapper_mode": args.mapper_mode,
        "rows": adjudication_rows,
    })
    _atomic_json(mapper_dir / "summary.json", summary)

    # Compact TSV
    lines = [
        "case_id\topt@1\topt@2\tgold_letter\tgold_option_rank\tgold_option\tjoint_top1\tjoint_top2"
    ]
    for row in records:
        lines.append("\t".join([
            str(row.get("case_id")),
            str(int(bool(row.get("option_top1")))),
            str(int(bool(row.get("option_top2")))),
            str(row.get("gold_letter") or ""),
            str(row.get("gold_option_rank") or ""),
            str(row.get("gold_option_text") or "").replace("\t", " "),
            str(row.get("joint_top1_label") or "").replace("\t", " "),
            str(row.get("joint_top2_label") or "").replace("\t", " "),
        ]))
    (mapper_dir / "mapper_results.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["n_error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
