#!/usr/bin/env python3
"""Post-hoc token gap estimate: M00 (cache outputs) vs B02 (reconstructed I/O).

No official token ledger (I05 deferred). Method:
- tokenizer: tiktoken cl100k_base (fallback len//4)
- M00: each *llm_cache.json entry value = 1 completion; input unavailable
- B02: output from trace LLM payloads; input ≈ system prompt + user wrapper
  with knowledge_chunks proxied by cost.snippet_chars
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

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

from baseline_arms import (  # type: ignore
    FLAT_CANDIDATE_EXPAND_PROMPT,
    FLAT_CANDIDATE_PROMPT,
    FLAT_EVIDENCE_MATRIX_PROMPT,
    FLAT_RERANK_PROMPT,
)
from baseline_common import load_runtime_cases  # type: ignore

PROMPT_CAND = FLAT_CANDIDATE_PROMPT.replace("__K__", "8")
PROMPT_EXPAND = FLAT_CANDIDATE_EXPAND_PROMPT.replace("__K__", "8").replace(
    "__EXISTING__", "x" * 200
)
PROMPT_EV = FLAT_EVIDENCE_MATRIX_PROMPT
PROMPT_RR = FLAT_RERANK_PROMPT


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def load_vignettes(subset_dir: Path, dataset: str) -> dict[str, str]:
    """Map case_id / source_id -> vignette via the same loader as baselines."""
    cases = load_runtime_cases(subset_dir=subset_dir, dataset=dataset)
    out: dict[str, str] = {}
    for c in cases:
        vig = str(c.get("vignette") or "")
        cid = str(c.get("case_id") or "")
        sid = str(c.get("source_id") or "")
        if cid:
            out[cid] = vig
        if sid:
            out[sid] = vig
            out[str(sid).lstrip("0") or sid] = vig
    return out


def m00_from_caches(cache_roots: list[Path]) -> list[dict]:
    rows = []
    for root in cache_roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name == "mapper":
                continue
            files = list(d.glob("*llm_cache.json"))
            if not files:
                continue
            entries = 0
            out_tok = 0
            out_chars = 0
            by_file: dict[str, Any] = {}
            for f in files:
                obj = json.loads(f.read_text())
                if not isinstance(obj, dict):
                    continue
                ft = 0
                fe = 0
                for v in obj.values():
                    s = dumps(v)
                    fe += 1
                    ft += ntok(s)
                    out_chars += len(s)
                entries += fe
                out_tok += ft
                by_file[f.name] = {"entries": fe, "out_tokens": ft}
            rows.append(
                {
                    "source_id": d.name,
                    "llm_calls_proxy": entries,
                    "output_tokens_est": out_tok,
                    "output_chars": out_chars,
                    "by_file": by_file,
                }
            )
    return rows


def b02_from_run(
    pred_dir: Path, vignettes: dict[str, str], dataset_prefix: str
) -> list[dict]:
    pred_path = pred_dir / "predictions.jsonl"
    trace_path = pred_dir / "trace.jsonl"
    preds = {
        json.loads(l)["case_id"]: json.loads(l)
        for l in pred_path.read_text().splitlines()
        if l.strip()
    }
    traces: dict[str, Any] = {}
    for line in trace_path.read_text().splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        traces[t["case_id"]] = t

    rows = []
    for cid, pred in preds.items():
        cost = pred.get("cost") or {}
        tr = (traces.get(cid) or {}).get("trace") or {}
        sid = str(pred.get("source_id") or "")
        vig = (
            vignettes.get(cid)
            or vignettes.get(sid)
            or vignettes.get(str(sid).lstrip("0") or sid)
            or ""
        )
        snippet_chars = int(cost.get("snippet_chars") or 0)
        llm_calls = int(cost.get("llm_calls") or 0)
        cand_batches = tr.get("candidate_batches") or []
        evidence = tr.get("evidence_rounds_raw") or []
        rerank = tr.get("rerank_raw") or {}
        candidates = tr.get("candidates") or []
        queries = tr.get("queries") or []

        out_tok = 0
        for b in cand_batches:
            out_tok += ntok(dumps(b.get("raw")))
        for e in evidence:
            out_tok += ntok(dumps(e))
        out_tok += ntok(dumps(rerank))

        know_proxy = "K" * snippet_chars
        base_payload = {
            "vignette": vig,
            "knowledge_chunks": know_proxy,
            "search_queries": queries,
        }
        n_cand = len(cand_batches)
        n_ev = len(evidence)
        n_rr = 1 if rerank else 0
        accounted = n_cand + n_ev + n_rr
        in_tok = 0

        def add_call(prompt: str, payload: dict) -> None:
            nonlocal in_tok
            user = (
                "Module: X\nReturn strict JSON only, no markdown.\n"
                f"Payload:\n{dumps(payload)}"
            )
            in_tok += ntok(prompt) + ntok(user)

        for i, b in enumerate(cand_batches):
            if i == 0 and not str(b.get("batch", "")).startswith("fill"):
                add_call(PROMPT_CAND, dict(base_payload))
            else:
                add_call(
                    PROMPT_EXPAND,
                    {**base_payload, "existing_candidates": candidates},
                )
        for _ in evidence:
            add_call(PROMPT_EV, {**base_payload, "candidates": candidates})
        if n_rr:
            add_call(PROMPT_RR, {**base_payload, "candidates": candidates})
        for _ in range(max(0, llm_calls - accounted)):
            add_call(PROMPT_EV, {**base_payload, "candidates": candidates})

        rows.append(
            {
                "case_id": cid,
                "source_id": sid,
                "llm_calls": llm_calls,
                "snippet_chars": snippet_chars,
                "output_tokens_est": out_tok,
                "input_tokens_est": in_tok,
                "total_tokens_est": in_tok + out_tok,
                "trace_accounted_calls": accounted,
                "vignette_chars": len(vig),
            }
        )
    return rows


def agg(rows: list[dict], keys: list[str]) -> dict:
    out: dict[str, Any] = {"n": len(rows)}
    for k in keys:
        vals = [float(r[k]) for r in rows if r.get(k) is not None]
        out[f"mean_{k}"] = mean(vals) if vals else None
        out[f"sum_{k}"] = sum(vals) if vals else None
    return out


def schedule_mean_llm(path: Path) -> float | None:
    if not path.is_file():
        return None
    vals = []
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if "_meta" in r:
            continue
        vals.append(float(r["llm_calls"]))
    return mean(vals) if vals else None


DATASETS = {
    "diagnosisarena": {
        "m00_caches": [
            ROOT
            / "logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1/cache",
            ROOT
            / "logs/diagnosisarena_d2_m01_v1/remain76_compat_b12_live_v1/cache",
        ],
        "b02_matched": ROOT
        / "runs/paper_v1/diagnosisarena_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01",
        "b02_native": ROOT
        / "runs/paper_v1/diagnosisarena_fixed_v1/B02-flat-matched-rerank/replicate_01",
        "subset": ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
        "prefix": "diagnosisarena__",
        "schedule": ROOT
        / "configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl",
    },
    "open_xddx": {
        "m00_caches": [
            ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1/annotate/cache",
        ],
        "b02_matched": ROOT
        / "runs/paper_v1/open_xddx_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01",
        "b02_native": ROOT
        / "runs/paper_v1/open_xddx_ox_seq100_v1/B02-flat-matched-rerank/replicate_01",
        "subset": ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1",
        "prefix": "open_xddx__",
        "schedule": ROOT
        / "configs/paper_experiments/paper_v1_budget_schedule_open_xddx.jsonl",
    },
    "medcasereasoning": {
        "m00_caches": [
            ROOT
            / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/cache",
        ],
        "b02_matched": ROOT
        / "runs/paper_v1/medcasereasoning_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01",
        "b02_native": ROOT
        / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B02-flat-matched-rerank/replicate_01",
        "subset": ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
        "prefix": "medcasereasoning__",
        "schedule": ROOT
        / "configs/paper_experiments/paper_v1_budget_schedule_medcasereasoning.jsonl",
    },
}


def main() -> None:
    report: dict[str, Any] = {
        "schema_version": 1,
        "tokenizer": TOK_METHOD,
        "caveats": [
            "No official token ledger (I05 deferred).",
            "M00 input tokens unavailable (cache stores outputs only); output = tiktoken(json(cache_value)).",
            "M00 llm_calls_proxy = number of cache entries (may include retries / multi-module).",
            "B02 input uses snippet_chars as knowledge_chunks body proxy; vignette from load_runtime_cases.",
            "B02 matched was aligned to structural_proxy_v1 call caps, NOT to M00 actual cache entry counts.",
            "m00_total_tokens_proj applies B02 matched input/output ratio to M00 outputs (sensitivity only).",
        ],
        "datasets": {},
    }

    for ds, cfg in DATASETS.items():
        print(f"=== {ds} ===", flush=True)
        vig = load_vignettes(cfg["subset"], dataset=ds)
        print(
            f"  vignettes={len(vig)} mean_chars={mean(len(v) for v in vig.values()) if vig else 0:.0f}",
            flush=True,
        )
        m00 = m00_from_caches(cfg["m00_caches"])
        b02m = (
            b02_from_run(cfg["b02_matched"], vig, cfg["prefix"])
            if cfg["b02_matched"].is_dir()
            else []
        )
        b02n = (
            b02_from_run(cfg["b02_native"], vig, cfg["prefix"])
            if (cfg["b02_native"].is_dir() and (cfg["b02_native"] / "predictions.jsonl").is_file())
            else []
        )

        a_m00 = agg(m00, ["llm_calls_proxy", "output_tokens_est", "output_chars"])
        a_b02m = agg(
            b02m,
            [
                "llm_calls",
                "input_tokens_est",
                "output_tokens_est",
                "total_tokens_est",
                "snippet_chars",
                "vignette_chars",
            ],
        )
        a_b02n = (
            agg(
                b02n,
                ["llm_calls", "input_tokens_est", "output_tokens_est", "total_tokens_est"],
            )
            if b02n
            else None
        )

        io_ratio = None
        if a_b02m.get("mean_output_tokens_est") and a_b02m["mean_output_tokens_est"] > 0:
            io_ratio = a_b02m["mean_input_tokens_est"] / a_b02m["mean_output_tokens_est"]
        m00_total_proj = None
        if io_ratio is not None and a_m00.get("mean_output_tokens_est") is not None:
            m00_total_proj = a_m00["mean_output_tokens_est"] * (1.0 + io_ratio)

        sched_llm = schedule_mean_llm(cfg["schedule"])
        gap = {
            "mean_llm_calls_m00_cache_vs_b02_matched": (
                (a_m00["mean_llm_calls_proxy"] - a_b02m["mean_llm_calls"])
                if a_m00.get("mean_llm_calls_proxy") is not None
                and a_b02m.get("mean_llm_calls") is not None
                else None
            ),
            "ratio_llm_calls_m00_over_b02_matched": (
                a_m00["mean_llm_calls_proxy"] / a_b02m["mean_llm_calls"]
                if a_m00.get("mean_llm_calls_proxy") and a_b02m.get("mean_llm_calls")
                else None
            ),
            "mean_output_tokens_m00_minus_b02_matched": (
                a_m00["mean_output_tokens_est"] - a_b02m["mean_output_tokens_est"]
                if a_m00.get("mean_output_tokens_est") is not None
                and a_b02m.get("mean_output_tokens_est") is not None
                else None
            ),
            "ratio_output_tokens_m00_over_b02_matched": (
                a_m00["mean_output_tokens_est"] / a_b02m["mean_output_tokens_est"]
                if a_m00.get("mean_output_tokens_est")
                and a_b02m.get("mean_output_tokens_est")
                else None
            ),
            "mean_total_tokens_proj_m00_minus_b02_matched": (
                m00_total_proj - a_b02m["mean_total_tokens_est"]
                if m00_total_proj is not None
                and a_b02m.get("mean_total_tokens_est") is not None
                else None
            ),
            "ratio_total_tokens_proj_m00_over_b02_matched": (
                m00_total_proj / a_b02m["mean_total_tokens_est"]
                if m00_total_proj and a_b02m.get("mean_total_tokens_est")
                else None
            ),
            "structural_schedule_mean_llm_calls": sched_llm,
            "b02_matched_vs_schedule_llm_calls": (
                a_b02m["mean_llm_calls"] - sched_llm if sched_llm is not None else None
            ),
        }

        report["datasets"][ds] = {
            "m00": a_m00,
            "b02_matched": a_b02m,
            "b02_native": a_b02n,
            "b02_io_ratio_input_over_output": io_ratio,
            "m00_total_tokens_proj_mean": m00_total_proj,
            "gaps": gap,
            "paths": {
                "m00_caches": [str(p) for p in cfg["m00_caches"]],
                "b02_matched": str(cfg["b02_matched"]),
                "b02_native": str(cfg["b02_native"]),
            },
        }
        print(
            json.dumps(
                {
                    "mean_vig": a_b02m.get("mean_vignette_chars"),
                    "mean_b02_total": a_b02m.get("mean_total_tokens_est"),
                    "mean_m00_out": a_m00.get("mean_output_tokens_est"),
                    "ratio_calls": gap.get("ratio_llm_calls_m00_over_b02_matched"),
                    "ratio_out_tok": gap.get("ratio_output_tokens_m00_over_b02_matched"),
                },
                indent=2,
            ),
            flush=True,
        )

    out_json = ROOT / "analysis/transfer_metrics_v1/b02_vs_m00_token_gap_v1.json"
    out_md = ROOT / "analysis/transfer_metrics_v1/b02_vs_m00_token_gap_v1.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# B02 vs 主方法 token 差距（事后估计）",
        "",
        f"Tokenizer：`{TOK_METHOD}`  ·  无正式 token ledger（I05 deferred）",
        "",
        "## 方法边界",
        "",
        "- **当前预算匹配是 call/结构代理**，不是 token；B02 matched 与 structural schedule 的 llm_calls 对齐（G5）。",
        "- **M00 无 input 落盘**：仅对 `*llm_cache.json` 的输出 JSON 做 tiktoken；`llm_calls_proxy` = cache entry 数。",
        "- **B02**：输出取自 `trace`；输入按 `call_module` 格式重建（system prompt + payload），`knowledge_chunks` 用 `snippet_chars` 代理。",
        "- **总 token 投影**：`M00_total ≈ M00_out × (1 + B02_in/B02_out)`，仅作量级敏感性，非官方账本。",
        "",
        "## 主结果（每例均值，n=100）",
        "",
        "| 数据集 | M00 calls‡ | B02 matched calls | calls 比 | M00 out tok | B02 matched out tok | out 比 | B02 matched total tok† | M00 total 投影† | total 比† |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ds, block in report["datasets"].items():
        g = block["gaps"]
        lines.append(
            "| {ds} | {m00c:.1f} | {b02c:.2f} | **{rc:.1f}×** | {m00o:.0f} | {b02o:.0f} | **{ro:.1f}×** | {b02t:.0f} | {m00t:.0f} | **{rt:.1f}×** |".format(
                ds=ds,
                m00c=block["m00"]["mean_llm_calls_proxy"],
                b02c=block["b02_matched"]["mean_llm_calls"],
                rc=g["ratio_llm_calls_m00_over_b02_matched"],
                m00o=block["m00"]["mean_output_tokens_est"],
                b02o=block["b02_matched"]["mean_output_tokens_est"],
                ro=g["ratio_output_tokens_m00_over_b02_matched"],
                b02t=block["b02_matched"]["mean_total_tokens_est"],
                m00t=block["m00_total_tokens_proj_mean"],
                rt=g["ratio_total_tokens_proj_m00_over_b02_matched"],
            )
        )
    lines += [
        "",
        "‡ cache entry 代理；† B02 total = 重建 in+out；M00 total = 输出 × (1+B02 I/O 比)。",
        "",
        "## 与 structural schedule 对照",
        "",
        "| 数据集 | schedule mean llm_calls | B02 matched mean | Δ |",
        "|---|---:|---:|---:|",
    ]
    for ds, block in report["datasets"].items():
        g = block["gaps"]
        lines.append(
            f"| {ds} | {g['structural_schedule_mean_llm_calls']:.2f} | "
            f"{block['b02_matched']['mean_llm_calls']:.2f} | {g['b02_matched_vs_schedule_llm_calls']:.2f} |"
        )
    lines += [
        "",
        "## B02 native vs matched（参考）",
        "",
        "| 数据集 | native total tok† | matched total tok† | matched/native |",
        "|---|---:|---:|---:|",
    ]
    for ds, block in report["datasets"].items():
        nat = block.get("b02_native") or {}
        if not nat:
            continue
        nt = nat["mean_total_tokens_est"]
        mt = block["b02_matched"]["mean_total_tokens_est"]
        lines.append(
            f"| {ds} | {nt:.0f} | {mt:.0f} | {mt/nt:.1f}× |" if nt else f"| {ds} | — | {mt:.0f} | — |"
        )
    lines += [
        "",
        "## 解读",
        "",
        "1. **Call 匹配成功、真实算力未匹配**：B02 matched 与结构 schedule 的 llm_calls 完全对齐，但相对主方法实际 cache 调用约 **7–10× 更少**。",
        "2. **输出 token**：主方法 completion 约 **5–9×** 于 B02 matched（可直接估的硬指标）。",
        "3. **因此当前 G5「等预算」不能写成「等 token」**；若论文要严格 compute-matched，需补主方法 token/call ledger 后重配 B02。",
        "",
        f"JSON：[`{out_json.name}`]({out_json.name})  ·  脚本：`scripts/paper/estimate_b02_m00_token_gap.py`",
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", out_json)
    print("WROTE", out_md)


if __name__ == "__main__":
    main()
