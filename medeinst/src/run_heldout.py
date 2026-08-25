"""Held-out DA200 + MCR200 DCI eval with memory off.

Default backbone is parent Set-B llama-3.3-70b. Live PubMed/OpenTargets search
counts as RAG → 25 workers; otherwise 50.

  PYTHONPATH=. python -m src.run_heldout --parent ..
  # default config: configs/heldout_open.yaml (DA keeps DCI audit, MCR keeps CoT@1)
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data import Case, load_heldout_corpus
from src.embed import active_mode, configure_embedding
from src.evaluate import baseline_accuracy
from src.llm import OpenAICompatLLM, load_parent_openrouter_keys
from src.model import ECRAgent, ModelConfig
from src.utils import diagnoses_match, load_yaml

LLAMA_33_70B = "meta-llama/llama-3.3-70b-instruct"
_WRITE_LOCK = threading.Lock()
_PROGRESS_LOCK = threading.Lock()


def default_workers(live_search: bool, override: int) -> int:
    if override > 0:
        return override
    return 25 if live_search else 50


def _ordered_diagnoses(diagnosis: str, dset: list[str], k: int = 2) -> list[str]:
    ordered: list[str] = []
    for name in [diagnosis, *dset]:
        text = str(name or "").strip()
        if not text:
            continue
        if any(text.casefold() == seen.casefold() for seen in ordered):
            continue
        ordered.append(text)
        if len(ordered) >= k:
            break
    while len(ordered) < k:
        ordered.append("")
    return ordered[:k]


def _prediction_row(case: Case, diagnosis: str, dset: list[str], n_llm_calls: int) -> dict[str, Any]:
    ordered = _ordered_diagnoses(diagnosis, dset, k=5)
    top2 = _ordered_diagnoses(diagnosis, dset, k=2)
    runtime_id = case.runtime_case_id or case.case_id
    return {
        "case_id": runtime_id,
        "source_id": case.case_id,
        "arm": "ecr_agent_dci_nomem",
        "replicate": 1,
        "list_k": 5,
        "ordered_diagnoses": ordered,
        "top2_diagnoses": top2,
        "slice": case.slice_name,
        "cost": {"n_llm_calls": n_llm_calls},
        "options_stripped": case.options_stripped,
    }


def _pred_path(out_dir: Path, case: Case) -> Path:
    sub = "da" if str(case.slice_name).startswith("d2_") else "mcr"
    path = out_dir / sub
    path.mkdir(parents=True, exist_ok=True)
    return path / "predictions.jsonl"


def _row_key(case: Case) -> str:
    return f"{case.slice_name}/{case.case_id}"


def _load_done(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.is_file():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("case_id") and row.get("slice"):
            done.add(f"{row['slice']}/{row['case_id']}")
    return done


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_slice: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_slice.setdefault(str(row.get("slice") or "unknown"), []).append(row)
    out: dict[str, Any] = {"n": len(rows), "slices": {}}
    n_ok = 0
    n_err = 0
    n_correct = 0
    for slice_name, items in by_slice.items():
        scored = [r for r in items if not r.get("error")]
        correct = sum(1 for r in scored if r.get("correct"))
        errors = sum(1 for r in items if r.get("error"))
        n_ok += len(scored)
        n_err += errors
        n_correct += correct
        out["slices"][slice_name] = {
            "n": len(items),
            "n_scored": len(scored),
            "n_error": errors,
            "n_correct": correct,
            "acc_base": baseline_accuracy(correct, len(scored)) if scored else None,
        }
    out["n_scored"] = n_ok
    out["n_error"] = n_err
    out["n_correct"] = n_correct
    out["acc_base"] = baseline_accuracy(n_correct, n_ok) if n_ok else None
    return out


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/heldout_open.yaml")
    parser.add_argument("--parent", default="..")
    parser.add_argument("--corpus", default="both", choices=("da", "mcr", "both"))
    parser.add_argument("--model", default=LLAMA_33_70B)
    parser.add_argument("--workers", type=int, default=0, help="0 = 50, or 25 when RAG/live-search")
    parser.add_argument("--limit", type=int, default=0, help="0 = all loaded cases")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--no-live-search", action="store_true")
    parser.add_argument("--memory", default="off", choices=("off",))
    parser.add_argument("--out-dir", default="")
    parser.add_argument(
        "--selector",
        default="",
        help="Override model.audit_mode: llm|argmax|cot_unless_margin|cot1|auto",
    )
    args = parser.parse_args()

    cfg_path = Path(args.config)
    raw = load_yaml(cfg_path) if cfg_path.is_file() else {}
    model_cfg = raw.get("model") or {}
    llm_cfg = raw.get("llm") or {}
    parent = Path(args.parent).resolve()

    keys = load_parent_openrouter_keys(parent)
    if not keys["OPENROUTER_API_KEY"] and not keys["OPENROUTER_API_KEY2"]:
        raise SystemExit("no OpenRouter key from env or parent llm_client.py")

    live_search = False if args.no_live_search else bool(
        model_cfg.get("live_search_pubmed", True) or model_cfg.get("live_search_opentargets", True)
    )
    workers = default_workers(live_search, args.workers)
    embedding = str(model_cfg.get("embedding", "medcpt"))
    configure_embedding(embedding)
    config = ModelConfig.from_mapping(
        model_cfg,
        live_search=False if args.no_live_search else None,
    )
    if args.selector:
        config.audit_mode = str(args.selector).strip().lower()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else Path("runs") / f"heldout_llama33_nomem_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "cases.jsonl"
    summary_path = out_dir / "summary.json"
    trace_path = out_dir / "llm_calls.jsonl"
    (out_dir / "da").mkdir(exist_ok=True)
    (out_dir / "mcr").mkdir(exist_ok=True)

    llm = OpenAICompatLLM(
        model=str(args.model or llm_cfg.get("base_model", LLAMA_33_70B)),
        temperature=float(llm_cfg.get("temperature", 0.0)),
        max_tokens=int(llm_cfg.get("max_tokens", 2048)),
        api_base=(llm_cfg.get("api_base") or None),
        parent_root=parent,
        trace_path=trace_path,
    )
    # Shared frozen agent: empty illness graphs + empty exemplar base (memory off).
    agent = ECRAgent(
        llm=llm,
        config=config,
        illness_graphs={},
        exemplar_base=[],
    )
    cases = load_heldout_corpus(parent, args.corpus)
    if args.offset or args.limit:
        end = args.offset + args.limit if args.limit else None
        cases = cases[args.offset : end]
    n_options_in_x = sum(1 for c in cases if "Options:" in c.x)
    n_mcq_stem_in_x = sum(
        1 for c in cases if "What is the most likely diagnosis?" in c.x
    )
    n_gold_substring_in_x = sum(
        1
        for c in cases
        if c.y_gt and str(c.y_gt).lower() in c.x.lower()
    )
    if n_options_in_x:
        raise SystemExit(
            f"option leak still present: Options: in {n_options_in_x} vignettes"
        )
    meta = {
        "created_at": stamp,
        "model": llm.model,
        "embedding": active_mode(),
        "memory": args.memory,
        "illness_graphs": 0,
        "exemplar_base": 0,
        "live_search_pubmed": config.live_search_pubmed,
        "live_search_opentargets": config.live_search_opentargets,
        "workers": workers,
        "corpus": args.corpus,
        "n_queued": len(cases),
        "parent": str(parent),
        "key_source": "parent_llm_client_or_env",
        "has_key1": bool(keys["OPENROUTER_API_KEY"]),
        "has_key2": bool(keys["OPENROUTER_API_KEY2"]),
        "options_stripped": True,
        "n_options_in_x": n_options_in_x,
        "n_mcq_stem_in_x": n_mcq_stem_in_x,
        "n_gold_substring_in_x": n_gold_substring_in_x,
        "trace_path": str(trace_path),
        "input_mode": "open_vignette_no_options",
        "audit_mode": config.audit_mode,
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    done = _load_done(jsonl_path)
    todo = [c for c in cases if _row_key(c) not in done]
    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "model": llm.model,
                "workers": workers,
                "live_search": live_search,
                "memory": "off",
                "options_stripped": True,
                "n_options_in_x": n_options_in_x,
                "n_gold_substring_in_x": n_gold_substring_in_x,
                "trace_path": str(trace_path),
                "n_total": len(cases),
                "n_resume_skip": len(cases) - len(todo),
                "n_todo": len(todo),
            },
            indent=2,
        ),
        flush=True,
    )

    finished = len(cases) - len(todo)
    t_run = time.time()

    def run_one(case: Case) -> dict[str, Any]:
        llm.reset_thread_calls()
        llm.set_case_context(case.case_id, case.slice_name)
        t0 = time.time()
        error = None
        diagnosis = ""
        dset: list[str] = []
        scores: dict[str, float] = {}
        try:
            # Do not call cgme_step / train.run_cgme. Graphs stay empty.
            result = agent.dci_pipeline(case.x, slice_name=case.slice_name)
            diagnosis = result.diagnosis
            dset = list(result.dset)
            scores = dict(result.scores)
        except Exception as exc:  # noqa: BLE001 — isolate one case from the pool
            error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        elapsed = round(time.time() - t0, 2)
        correct = (not error) and diagnoses_match(diagnosis, case.y_gt)
        row = {
            "case_id": case.case_id,
            "runtime_case_id": case.runtime_case_id,
            "slice": case.slice_name,
            "y_gt": case.y_gt,
            "diagnosis": diagnosis,
            "dset": dset,
            "scores": scores,
            "correct": bool(correct),
            "error": error,
            "n_llm_calls": llm.thread_calls(),
            "elapsed_s": elapsed,
            "memory": "off",
            "options_stripped": case.options_stripped,
            "options_in_x": "Options:" in case.x,
        }
        _append_jsonl(jsonl_path, row)
        _append_jsonl(
            _pred_path(out_dir, case),
            _prediction_row(case, diagnosis, dset, int(row["n_llm_calls"])),
        )
        return row

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(run_one, case): case for case in todo}
            for fut in as_completed(futs):
                case = futs[fut]
                try:
                    row = fut.result()
                except Exception as exc:  # noqa: BLE001
                    row = {
                        "case_id": case.case_id,
                        "runtime_case_id": case.runtime_case_id,
                        "slice": case.slice_name,
                        "y_gt": case.y_gt,
                        "diagnosis": "",
                        "dset": [],
                        "scores": {},
                        "correct": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "n_llm_calls": 0,
                        "elapsed_s": None,
                        "memory": "off",
                    }
                    _append_jsonl(jsonl_path, row)
                    _append_jsonl(
                        _pred_path(out_dir, case),
                        _prediction_row(case, "", [], 0),
                    )
                with _PROGRESS_LOCK:
                    finished += 1
                    n_done = finished
                status = "ERR" if row.get("error") else ("HIT" if row.get("correct") else "MISS")
                print(
                    f"[{n_done}/{len(cases)}] {status} {row['slice']}/{row['case_id']} "
                    f"pred={str(row.get('diagnosis') or '')[:80]!r} "
                    f"gold={str(row.get('y_gt') or '')[:80]!r} "
                    f"calls={row.get('n_llm_calls')} t={row.get('elapsed_s')}s "
                    f"err={row.get('error')}",
                    flush=True,
                )
    finally:
        rows = _read_jsonl(jsonl_path)
        summary = {
            **meta,
            "finished_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "elapsed_s": round(time.time() - t_run, 2),
            "n_llm_calls_total": llm.n_calls,
            **_summarize(rows),
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        print("wrote", summary_path, flush=True)


if __name__ == "__main__":
    main()
