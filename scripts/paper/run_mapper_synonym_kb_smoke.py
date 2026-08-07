#!/usr/bin/env python3
"""compat_parallel frozen ranking → typed_llm vs typed_llm_synonym_kb.

Uses downstream case_results leaf shortlists (already compat-routed). No leaf
inject. Synonym arm attaches SynonymGranularityRetriever (disease_name_bridge)
and runs a symmetric per-option RAG critic.

Gold-blind: options treated symmetrically; gold used only for scoring.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
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
import run_at1_calibration_smoke as at1  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    leaf_rows_from_tree,
    load_offline_resolver,
)
from agentclinic_tree_dx.knowledge.synonym_granularity_retriever import (  # noqa: E402
    SynonymGranularityRetriever,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

PILOT_DOWN = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1"
REMAIN_DOWN = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate"
)
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
BRIDGE = ROOT / "data" / "knowledge_raw" / "disease_name_bridge.json"
OUT = ROOT / "analysis" / "l1_recall_failure_v1" / "smoke_synonym_kb"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"

ARMS = ("typed_llm", "typed_llm_synonym_kb")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _split_case_text(case_text: str) -> tuple[str, str]:
    text = str(case_text or "")
    if "\nOptions:" in text:
        body, _ = text.split("\nOptions:", 1)
        return body.strip(), "What is the most likely diagnosis?"
    return text.strip(), "What is the most likely diagnosis?"


def _tree_from_ranking_labels(
    ranking_labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
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
                "posterior": float(row.get("posterior") or 0.0),
            }
        branches[leaf_id] = {
            "id": leaf_id,
            "label": label,
            "level": 2,
            "parent": parent_id or None,
            "children": [],
            "posterior": float(row.get("posterior") or 0.0),
        }
        if parent_id and parent_id in branches:
            kids = list(branches[parent_id].get("children") or [])
            if leaf_id not in kids:
                kids.append(leaf_id)
            branches[parent_id]["children"] = kids
    return {"branches": branches}


def _downstream_for(cid: str, cohort: str) -> Path:
    if cohort == "pilot24":
        return PILOT_DOWN
    # remain / all100
    if (REMAIN_DOWN / "case_results" / ("%s.json" % cid)).is_file():
        return REMAIN_DOWN
    return PILOT_DOWN


def _load_case_bundle(cid: str, cohort: str) -> dict[str, Any]:
    down = _downstream_for(cid, cohort)
    result = json.loads(
        (down / "case_results" / ("%s.json" % cid)).read_text(encoding="utf-8")
    )
    cases_path = down / "normalized_cases.json"
    if not cases_path.is_file():
        cases_path = PILOT_DOWN / "normalized_cases.json"
    cases = {
        str(c["id"]): c
        for c in (json.loads(cases_path.read_text(encoding="utf-8")).get("cases") or ())
    }
    # remain may use different cases file
    if cid not in cases and REMAIN_DOWN.joinpath("normalized_cases.json").is_file():
        cases.update({
            str(c["id"]): c
            for c in (
                json.loads(
                    (REMAIN_DOWN / "normalized_cases.json").read_text(encoding="utf-8")
                ).get("cases")
                or ()
            )
        })
    meta = cases.get(cid) or {}
    return {"result": result, "meta": meta, "downstream": down}


def _leaves_from_result(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    l2 = result.get("l2") or {}
    ranking_ids = list(l2.get("final_ranking_ids") or ())
    ranking_labels = list(l2.get("final_ranking_labels") or ())
    if not ranking_ids and ranking_labels:
        ranking_ids = [str(row.get("id")) for row in ranking_labels]
    tree = _tree_from_ranking_labels(ranking_labels)
    leaves = leaf_rows_from_tree(tree, ranking_ids)
    if leaves:
        return leaves
    return [
        {
            "leaf_id": str(row.get("id") or ("L%d" % index)),
            "leaf_label": str(row.get("label") or ""),
            "parent_id": str(row.get("parent") or ""),
            "parent_label": "",
            "joint_rank": int(row.get("rank") or index),
            "posterior": float(row.get("posterior") or 0.0),
        }
        for index, row in enumerate(ranking_labels, start=1)
        if str(row.get("label") or "").strip()
    ]


def _options(meta: Mapping[str, Any]) -> dict[str, str]:
    opts = da.normalize_options(
        ((meta.get("annotation") or {}).get("source_options") or {})
    )
    return {str(k).upper(): str(v) for k, v in opts.items()}


def eval_one(payload: Mapping[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    cid = str(payload["case_id"])
    arm = str(payload["arm"])
    out_path = Path(payload["out_path"])
    if payload.get("resume") and out_path.is_file():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if existing.get("status") == "OK":
            return existing
    try:
        bundle = _load_case_bundle(cid, str(payload["cohort"]))
        result = bundle["result"]
        meta = bundle["meta"]
        if result.get("status") != "OK":
            raise RuntimeError("upstream status=%s" % result.get("status"))
        leaves = _leaves_from_result(result)
        options = _options(meta)
        if not options:
            raise RuntimeError("missing options")
        vignette, question = _split_case_text(str(meta.get("case_text") or ""))
        gold_letter = str(meta.get("gold_option") or "").upper()

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

        retrievers: dict[str, Any] = {}
        mode = arm
        if arm == "typed_llm_synonym_kb":
            syn = SynonymGranularityRetriever(BRIDGE)
            if not syn.is_ready:
                raise RuntimeError("synonym bridge not ready: %s" % BRIDGE)
            retrievers["synonym_bridge"] = syn

        mapper = RelationAwareAnswerMapper(
            resolver=load_offline_resolver(ROOT),
            llm=_Adapter(),
            relation_prompt=Path(payload["relation_prompt"]).read_text(encoding="utf-8"),
            critic_prompt=Path(payload["critic_prompt"]).read_text(encoding="utf-8"),
            retrievers=retrievers,
            rag_top_k=8,
            rag_max_snippets=12,
        )
        projection = mapper.map(
            case_id=cid,
            vignette=vignette,
            question=question,
            options=options,
            leaves=leaves,
            mode=mode,
        )
        gold_map = (projection.get("option_maps") or {}).get(gold_letter) or {}
        gold_rank = gold_map.get("best_rank")
        gold_option_rank = int(gold_map.get("option_rank") or (len(options) + 1))
        matched = bool(gold_map.get("matched"))
        rel = str(gold_map.get("relation_type") or "")
        record = {
            "status": "OK",
            "case_id": cid,
            "cohort": payload["cohort"],
            "arm": arm,
            "n_leaves": len(leaves),
            "gold_letter": gold_letter,
            "gold_option_rank": gold_option_rank,
            "option_top1": int(bool(gold_rank is not None and gold_option_rank <= 1)),
            "option_top2": int(bool(gold_rank is not None and gold_option_rank <= 2)),
            "option_rr": (1.0 / gold_option_rank) if gold_rank is not None else 0.0,
            "gold_matched": int(matched),
            "gold_relation": rel,
            "n_disputes": len((projection.get("audit") or {}).get("disputes") or ()),
            "n_rag_snippets": len(
                ((projection.get("audit") or {}).get("rag") or {}).get("snippets") or ()
            ),
            "duration_seconds": round(time.monotonic() - started, 3),
            "projection": projection,
        }
    except Exception as exc:  # noqa: BLE001
        import traceback

        record = {
            "status": "ERROR",
            "case_id": cid,
            "cohort": payload.get("cohort"),
            "arm": arm,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc()[-2000:],
            "option_top1": 0,
            "option_top2": 0,
            "option_rr": 0.0,
            "gold_matched": 0,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def summarize_arm(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("status") == "OK"]
    return {
        "n": len(rows),
        "n_ok": len(ok),
        "n_error": len(rows) - len(ok),
        "opt1": mean([float(r["option_top1"]) for r in ok]) if ok else 0.0,
        "opt2": mean([float(r["option_top2"]) for r in ok]) if ok else 0.0,
        "mrr": mean([float(r["option_rr"]) for r in ok]) if ok else 0.0,
        "gold_matched_rate": (
            mean([float(r.get("gold_matched") or 0) for r in ok]) if ok else 0.0
        ),
        "mean_n_leaves": mean([float(r.get("n_leaves") or 0) for r in ok]) if ok else 0.0,
        "mean_rag_snippets": (
            mean([float(r.get("n_rag_snippets") or 0) for r in ok]) if ok else 0.0
        ),
    }


def write_report(out: Path, summary: Mapping[str, Any]) -> None:
    base = summary["arms"]["typed_llm"]
    syn = summary["arms"]["typed_llm_synonym_kb"]
    d1 = float(syn["opt1"]) - float(base["opt1"])
    d2 = float(syn["opt2"]) - float(base["opt2"])
    # Gate: do not hurt @2 much; prefer @1 gain or matched gain without @2 harm
    opt2_ok = d2 >= -0.01 - 1e-12
    improves = d1 > 1e-12 or (
        float(syn["gold_matched_rate"]) > float(base["gold_matched_rate"]) + 1e-12
        and opt2_ok
    )
    passed = opt2_ok and improves and int(syn["n_error"]) == 0 and int(base["n_error"]) == 0
    lines = [
        "# Mapper synonym/granularity KB smoke (compat leaves)",
        "",
        "**generated**: `%s`" % summary["generated_at"],
        "**cohort**: `%s`" % summary["cohort"],
        "**protocol**: frozen compat `final_ranking` → typed_llm vs typed_llm_synonym_kb",
        "**KB**: `disease_name_bridge` via SynonymGranularityRetriever (symmetric)",
        "**leaf inject**: off",
        "",
        "## Main table",
        "",
        "| arm | @1 | @2 | MRR | gold_matched | mean_leaves | mean_snippets |",
        "|-----|---:|---:|----:|-------------:|------------:|--------------:|",
        "| typed_llm (baseline) | %.3f | %.3f | %.3f | %.3f | %.2f | %.2f |"
        % (
            base["opt1"],
            base["opt2"],
            base["mrr"],
            base["gold_matched_rate"],
            base["mean_n_leaves"],
            base["mean_rag_snippets"],
        ),
        "| **typed_llm_synonym_kb** | **%.3f** | **%.3f** | **%.3f** | **%.3f** | %.2f | %.2f |"
        % (
            syn["opt1"],
            syn["opt2"],
            syn["mrr"],
            syn["gold_matched_rate"],
            syn["mean_n_leaves"],
            syn["mean_rag_snippets"],
        ),
        "",
        "## Gate (Pilot claim)",
        "",
        "- decision: **%s**" % ("PASS" if passed else "REJECT"),
        "- Δ@1=%+.3f Δ@2=%+.3f" % (d1, d2),
        "- opt2 guard (Δ≥-0.01): %s" % ("OK" if opt2_ok else "FAIL"),
        "- production_default: **off**",
        "",
        "## Notes",
        "",
        "- Baseline rematch on frozen official projections is NOT this table;",
        "  both arms re-run mapper on the same compat leaf shortlist.",
        "- Do not mix rematch / typed tables (I5).",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    summary = dict(summary)
    summary["gate"] = {
        "decision": "PASS" if passed else "REJECT",
        "delta_opt1": d1,
        "delta_opt2": d2,
        "opt2_guard_ok": opt2_ok,
        "claim_allowed": passed,
        "production_default": "off",
    }
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", choices=("pilot24", "all100", "remain76"), default="pilot24")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--call-timeout", type=float, default=240.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument(
        "--arms",
        default="typed_llm,typed_llm_synonym_kb",
        help="comma list",
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    packs = at1.load_cohort(args.cohort)
    arms = [a.strip() for a in str(args.arms).split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            raise SystemExit("unknown arm %s" % a)

    relation_prompt = (PROMPT_DIR / "answer_relation_mapper.txt").read_text(encoding="utf-8")
    critic_prompt = (PROMPT_DIR / "answer_relation_rag_critic.txt").read_text(encoding="utf-8")

    jobs: list[dict[str, Any]] = []
    for pack in packs:
        cid = str(pack["case_id"])
        cohort = str(pack["cohort"])
        for arm in arms:
            jobs.append({
                "case_id": cid,
                "cohort": cohort,
                "arm": arm,
                "model": args.model,
                "call_timeout": args.call_timeout,
                "resume": args.resume,
                "relation_prompt": str(PROMPT_DIR / "answer_relation_mapper.txt"),
                "critic_prompt": str(PROMPT_DIR / "answer_relation_rag_critic.txt"),
                "cache_path": str(
                    out / "cache" / arm / ("mapper_%s.json" % cid)
                ),
                "out_path": str(out / "projections" / arm / ("%s.json" % cid)),
            })

    print(
        "synonym-kb cohort=%s n_cases=%d arms=%s workers=%d"
        % (args.cohort, len(packs), arms, args.workers),
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    w = max(1, min(args.workers, len(jobs)))
    if w == 1:
        for job in jobs:
            row = eval_one(job)
            rows.append(row)
            print(
                "  %s %s @1=%s matched=%s"
                % (row.get("case_id"), row.get("arm"), row.get("option_top1"), row.get("gold_matched")),
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=w) as ex:
            futs = {ex.submit(eval_one, j): j for j in jobs}
            for fut in as_completed(futs):
                row = fut.result()
                rows.append(row)
                print(
                    "  %s %s @1=%s matched=%s"
                    % (
                        row.get("case_id"),
                        row.get("arm"),
                        row.get("option_top1"),
                        row.get("gold_matched"),
                    ),
                    flush=True,
                )

    # flatten metrics without huge projection
    flat = []
    for r in rows:
        flat.append({k: v for k, v in r.items() if k not in {"projection", "traceback"}})
    fields: list[str] = []
    seen: set[str] = set()
    for r in flat:
        for k in r:
            if k not in seen:
                fields.append(k)
                seen.add(k)
    tsv = out / ("metrics_%s.tsv" % args.cohort)
    with tsv.open("w", encoding="utf-8", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        wri.writeheader()
        wri.writerows(flat)

    arm_summaries = {
        arm: summarize_arm([r for r in flat if r.get("arm") == arm]) for arm in arms
    }
    payload: dict[str, Any] = {
        "generated_at": _utc(),
        "cohort": args.cohort,
        "model": args.model,
        "protocol": "compat_frozen_ranking_mapper_synonym_kb_ab",
        "bridge": str(BRIDGE.relative_to(ROOT)),
        "arms": arm_summaries,
        "production_default": "off",
    }
    if set(arms) >= {"typed_llm", "typed_llm_synonym_kb"}:
        payload = write_report(out, payload)
    (out / ("summary_%s.json" % args.cohort)).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
