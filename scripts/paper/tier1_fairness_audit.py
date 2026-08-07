#!/usr/bin/env python3
"""T1-04 fairness / budget audit table (post-hoc token estimates).

Builds a unified table across M00 (APHHM) and flat baselines:
  llm_calls, retrieval_docs, snippet_chars,
  input_tokens_est, output_tokens_est (POST-HOC, not official ledger),
  context_tokens_est, n_dev_cases, n_tune_knobs.

M00 tokens: sum output sizes from annotate/cache/*/l2_llm_cache.json;
input estimated as len(json.dumps(response))*0 (unavailable) OR
proxy from schedule + estimate_b02_m00_token_gap when present.

Baselines: predictions.jsonl cost fields + optional re-estimate.

Zero LLM calls.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "analysis" / "tier1_1a_v1"

try:
    import tiktoken

    ENC = tiktoken.get_encoding("cl100k_base")

    def ntok(text: str) -> int:
        if not text:
            return 0
        return len(ENC.encode(text))

    TOK_METHOD = "tiktoken_cl100k_base"
except Exception:  # pragma: no cover

    def ntok(text: str) -> int:
        return max(0, (len(text) + 3) // 4)

    TOK_METHOD = "char_div4_fallback"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def m00_cache_stats(cache_root: Path) -> dict[str, Any]:
    """Per-case LLM call counts + output token estimates from l2 caches."""
    rows = []
    if not cache_root.is_dir():
        return {"n_cases": 0, "rows": []}
    for case_dir in sorted(p for p in cache_root.iterdir() if p.is_dir()):
        fp = case_dir / "l2_llm_cache.json"
        if not fp.is_file():
            continue
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        out_toks = 0
        for v in doc.values():
            text = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            out_toks += ntok(text)
        rows.append(
            {
                "case_id": case_dir.name,
                "llm_calls": len(doc),
                "output_tokens_est": out_toks,
                # Input unavailable from response-only cache.
                "input_tokens_est": None,
            }
        )
    return {
        "n_cases": len(rows),
        "mean_llm_calls": mean([r["llm_calls"] for r in rows]) if rows else None,
        "mean_output_tokens_est": mean([r["output_tokens_est"] for r in rows])
        if rows
        else None,
        "rows": rows,
    }


def baseline_cost_stats(pred_jsonl: Path) -> dict[str, Any]:
    if not pred_jsonl.is_file():
        return {"n_cases": 0}
    rows = []
    with pred_jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except Exception:
                continue
            cost = doc.get("cost") or {}
            rows.append(
                {
                    "case_id": str(doc.get("case_id") or ""),
                    "llm_calls": int(cost.get("llm_calls") or 0),
                    "retrieval_calls": int(cost.get("retrieval_calls") or 0),
                    "retrieval_snippets": int(cost.get("retrieval_snippets") or 0),
                    "snippet_chars": int(cost.get("snippet_chars") or 0),
                    "input_tokens_est": cost.get("input_tokens_est"),
                    "output_tokens_est": cost.get("output_tokens_est"),
                    "latency_s": cost.get("latency_s"),
                }
            )
    if not rows:
        return {"n_cases": 0}

    def _m(key: str):
        xs = [r[key] for r in rows if r.get(key) is not None]
        xs2 = [float(x) for x in xs if x is not None]
        return mean(xs2) if xs2 else None

    return {
        "n_cases": len(rows),
        "mean_llm_calls": _m("llm_calls"),
        "mean_retrieval_calls": _m("retrieval_calls"),
        "mean_retrieval_snippets": _m("retrieval_snippets"),
        "mean_snippet_chars": _m("snippet_chars"),
        "mean_input_tokens_est": _m("input_tokens_est"),
        "mean_output_tokens_est": _m("output_tokens_est"),
        "mean_latency_s": _m("latency_s"),
    }


def load_budget_schedule(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    calls = []
    ret = []
    snips = []
    cands = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            calls.append(int(doc.get("llm_calls") or 0))
            ret.append(int(doc.get("retrieval_calls") or 0))
            snips.append(int(doc.get("retrieval_snippets") or 0))
            cands.append(int(doc.get("unique_candidates") or 0))
    return {
        "n": len(calls),
        "mean_llm_calls_proxy": mean(calls) if calls else None,
        "mean_retrieval_calls": mean(ret) if ret else None,
        "mean_retrieval_snippets": mean(snips) if snips else None,
        "mean_unique_candidates": mean(cands) if cands else None,
    }


def existing_token_gap() -> dict[str, Any]:
    p = ROOT / "analysis" / "transfer_metrics_v1" / "b02_vs_m00_token_gap_v1.json"
    if not p.is_file():
        # alternate locations
        for cand in ROOT.glob("**/b02_vs_m00_token_gap*.json"):
            p = cand
            break
        else:
            return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    # M00 arms
    m00_specs = {
        "mcr_m00": ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/cache",
        "ox_m00_hot": ROOT
        / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/annotate/cache",
        "ra_m00": ROOT
        / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1/annotate/cache",
    }
    schedules = {
        "mcr": ROOT
        / "configs/paper_experiments/paper_v1_budget_schedule_medcasereasoning.jsonl",
        "ox": ROOT
        / "configs/paper_experiments/paper_v1_budget_schedule_open_xddx.jsonl",
        "da": ROOT
        / "configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl",
    }

    baseline_roots = {
        "mcr": ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1",
        "da": ROOT / "runs/paper_v1",  # DA baselines may be top-level arm dirs
        "ra": ROOT / "runs/paper_v1/rarearena_ra_rdc_seq100_v1",
    }
    baseline_arms = [
        "B00-direct-cot",
        "B01-cot-rag",
        "B02-flat-compute-matched",
        "B02-flat-compute-matched-sc10",
        "B04-dual-inf",
        "B05-mdagents",
        "B06-mac-single-vendor",
        "B07-meddxagent-complete",
        "B12-sc-cot-5",
    ]

    table: list[dict[str, Any]] = []

    for name, cache in m00_specs.items():
        st = m00_cache_stats(cache)
        sched_key = "mcr" if name.startswith("mcr") else ("ox" if "ox" in name else "ra")
        sched = load_budget_schedule(schedules.get(sched_key, Path("/")))
        table.append(
            {
                "system": name,
                "kind": "APHHM",
                "n_cases": st["n_cases"],
                "mean_llm_calls": st["mean_llm_calls"],
                "mean_llm_calls_proxy_schedule": sched.get("mean_llm_calls_proxy"),
                "mean_retrieval_snippets": sched.get("mean_retrieval_snippets"),
                "mean_unique_candidates": sched.get("mean_unique_candidates"),
                "mean_output_tokens_est": st["mean_output_tokens_est"],
                "mean_input_tokens_est": None,
                "input_token_note": "unavailable from response-only l2_llm_cache; see token_gap file",
                "n_dev_cases": 0,
                "n_tune_knobs": 4,  # F, local, between, cap (locked grid)
                "token_method": TOK_METHOD,
            }
        )

    # Baselines on MCR + RA
    for ds, root in (("mcr", baseline_roots["mcr"]), ("ra", baseline_roots["ra"])):
        if not root.is_dir():
            continue
        for arm in baseline_arms:
            pred = root / arm / "replicate_01" / "predictions.jsonl"
            if not pred.is_file():
                continue
            st = baseline_cost_stats(pred)
            table.append(
                {
                    "system": f"{ds}:{arm}",
                    "kind": "baseline",
                    "n_cases": st.get("n_cases"),
                    "mean_llm_calls": st.get("mean_llm_calls"),
                    "mean_retrieval_calls": st.get("mean_retrieval_calls"),
                    "mean_retrieval_snippets": st.get("mean_retrieval_snippets"),
                    "mean_snippet_chars": st.get("mean_snippet_chars"),
                    "mean_input_tokens_est": st.get("mean_input_tokens_est"),
                    "mean_output_tokens_est": st.get("mean_output_tokens_est"),
                    "mean_latency_s": st.get("mean_latency_s"),
                    "n_dev_cases": 0,
                    "n_tune_knobs": 0,
                    "token_method": "predictions.jsonl cost fields (often 0)",
                }
            )

    gap = existing_token_gap()
    report = {
        "schema_version": "tier1_fairness_audit_v1",
        "created_at": _utc(),
        "disclaimer": (
            "Token columns are POST-HOC estimates, not an official ledger "
            "(PAPER I05 deferred). M00 input tokens are not recoverable from "
            "response-only caches; use schedule proxies + any prior gap file."
        ),
        "token_method": TOK_METHOD,
        "existing_token_gap_file": bool(gap),
        "existing_token_gap_summary": {
            k: gap.get(k)
            for k in list(gap)[:12]
            if not isinstance(gap.get(k), (list, dict))
        }
        if gap
        else {},
        "table": table,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jp = OUT_DIR / "fairness_audit.json"
    jp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# T1-04 Fairness / budget audit",
        "",
        f"Created: {report['created_at']}",
        "",
        f"**Disclaimer:** {report['disclaimer']}",
        "",
        f"Tokenizer: `{TOK_METHOD}`",
        "",
        "| system | kind | n | calls | retr_snips | out_tok_est | in_tok_est | knobs |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in table:
        lines.append(
            f"| {r['system']} | {r['kind']} | {r.get('n_cases')} | "
            f"{_fmt(r.get('mean_llm_calls'))} | "
            f"{_fmt(r.get('mean_retrieval_snippets'))} | "
            f"{_fmt(r.get('mean_output_tokens_est'))} | "
            f"{_fmt(r.get('mean_input_tokens_est'))} | "
            f"{r.get('n_tune_knobs')} |"
        )
    (OUT_DIR / "fairness_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[fairness] wrote {jp} rows={len(table)}", flush=True)
    return 0


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.1f}"
    return str(x)


if __name__ == "__main__":
    raise SystemExit(main())
