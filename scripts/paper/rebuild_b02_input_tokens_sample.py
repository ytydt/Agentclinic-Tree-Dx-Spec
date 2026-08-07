#!/usr/bin/env python3
"""Precise B02 input-token reconstruction for a small case sample.

Looks up real KB chunk text via trace ``served_access_ids`` + corpus
``metadata.jsonl``, rebuilds each ``call_module`` message (system prompt +
payload JSON), and compares against the ``snippet_chars`` char-proxy used in
``estimate_b02_m00_token_gap.py``.
"""
from __future__ import annotations

import argparse
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
        return len(ENC.encode(text)) if text else 0

    TOK = "tiktoken_cl100k_base"
except Exception:  # pragma: no cover

    def ntok(text: str) -> int:
        return max(0, (len(text) + 3) // 4)

    TOK = "char_div4_fallback"

from baseline_arms import (  # type: ignore
    FLAT_CANDIDATE_EXPAND_PROMPT,
    FLAT_CANDIDATE_PROMPT,
    FLAT_EVIDENCE_MATRIX_PROMPT,
    FLAT_RERANK_PROMPT,
    _adapt_prompt_for_k,
)
from baseline_common import load_runtime_cases  # type: ignore

ASPECTS = [
    "less common differentials",
    "infectious and inflammatory alternatives",
    "neoplastic and paraneoplastic alternatives",
    "toxic metabolic and endocrine alternatives",
    "vascular and structural alternatives",
]


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def load_meta_index(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            cid = str(row.get("id") or "")
            if cid:
                out[cid] = row
    return out


def parse_access_id(aid: str) -> tuple[str, str]:
    # live::{source}::{chunk_id}
    if not str(aid).startswith("live::"):
        raise ValueError(f"unexpected access_id: {aid}")
    rest = str(aid)[len("live::") :]
    src, _, cid = rest.partition("::")
    return src, cid


def rebuild_chunks(
    access_ids: list[str],
    *,
    rag: dict[str, dict],
    cpg: dict[str, dict],
    max_chunk_chars: int,
    queries: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    miss: list[str] = []
    for aid in access_ids:
        src, cid = parse_access_id(aid)
        meta = rag.get(cid) if src == "rag_index" else cpg.get(cid)
        if meta is None:
            miss.append(aid)
            continue
        text = str(meta.get("content") or "")[: max(1, max_chunk_chars)]
        chunks.append(
            {
                "access_id": aid,
                "source": f"production:{src}",
                "title": str(meta.get("title") or ""),
                "text": text,
                "source_chunk_id": cid,
                "retrieval_queries": list(queries),
                "rrf_score": 0.0,
                "raw_scores": [],
            }
        )
    audit = {
        "n_access_ids": len(access_ids),
        "n_resolved": len(chunks),
        "n_miss": len(miss),
        "miss": miss[:10],
        "text_chars": sum(len(c["text"]) for c in chunks),
        "payload_json_chars": len(dumps(chunks)),
    }
    return chunks, audit


def message_tokens(prompt: str, module: str, payload: dict) -> dict[str, int]:
    user = (
        f"Module: {module}\n"
        "Return strict JSON only, no markdown.\n"
        f"Payload:\n{dumps(payload)}"
    )
    sys_t = ntok(prompt)
    user_t = ntok(user)
    return {
        "system_tokens": sys_t,
        "user_tokens": user_t,
        "input_tokens": sys_t + user_t,
        "user_chars": len(user),
        "payload_chars": len(dumps(payload)),
    }


def proxy_input_tokens(
    *,
    prompt: str,
    module: str,
    vignette: str,
    queries: list[str],
    snippet_chars: int,
    extra: dict[str, Any] | None = None,
) -> int:
    payload = {
        "vignette": vignette,
        "knowledge_chunks": "K" * int(snippet_chars),
        "search_queries": queries,
    }
    if extra:
        payload.update(extra)
    # match estimate_b02_m00_token_gap.py (runtime_payload fields omitted there too,
    # except we keep vignette); include case_id/question for tighter compare optional.
    return message_tokens(prompt, module, payload)["input_tokens"]


def precise_case(
    *,
    case: dict[str, Any],
    pred: dict[str, Any],
    trace_wrap: dict[str, Any],
    rag: dict[str, dict],
    cpg: dict[str, dict],
) -> dict[str, Any]:
    tr = trace_wrap.get("trace") or {}
    cost = pred.get("cost") or {}
    ret = tr.get("retrieval") or {}
    list_k = int(pred.get("list_k") or tr.get("list_k") or 2)
    vignette = str(case.get("vignette") or "")
    queries = list(ret.get("queries") or tr.get("queries") or [])
    max_chunk_chars = int(ret.get("max_chunk_chars") or 1600)
    access_ids = list(ret.get("served_access_ids") or [])
    chunks, chunk_audit = rebuild_chunks(
        access_ids,
        rag=rag,
        cpg=cpg,
        max_chunk_chars=max_chunk_chars,
        queries=queries,
    )
    snippet_chars = int(cost.get("snippet_chars") or 0)
    llm_calls = int(cost.get("llm_calls") or 0)

    base = {
        "case_id": case["case_id"],
        "vignette": vignette,
        "question": case.get("question") or "What is the most likely diagnosis?",
        "knowledge_chunks": chunks,
        "search_queries": queries,
    }

    cand_batches = list(tr.get("candidate_batches") or [])
    evidence = list(tr.get("evidence_rounds_raw") or [])
    rerank = tr.get("rerank_raw") or {}
    final_candidates = list(tr.get("candidates") or [])

    calls: list[dict[str, Any]] = []
    candidates: list[str] = []
    out_tok = 0
    precise_in = 0
    proxy_in = 0
    fill_i = 0

    def add(
        *,
        module: str,
        prompt: str,
        payload: dict[str, Any],
        proxy_extra: dict[str, Any] | None,
        raw_out: Any,
        kind: str,
    ) -> None:
        nonlocal precise_in, proxy_in, out_tok
        mt = message_tokens(prompt, module, payload)
        # proxy mirrors estimate script: vignette + K*snippet + queries (+extra)
        p_extra = dict(proxy_extra or {})
        # estimate script did not include case_id/question; keep same for ratio
        px = proxy_input_tokens(
            prompt=prompt,
            module=module,
            vignette=vignette,
            queries=queries,
            snippet_chars=snippet_chars,
            extra=p_extra,
        )
        ot = ntok(dumps(raw_out))
        precise_in += mt["input_tokens"]
        proxy_in += px
        out_tok += ot
        # KB share within this call's user payload
        kb_chars = len(dumps(chunks))
        pay_chars = mt["payload_chars"]
        calls.append(
            {
                "kind": kind,
                "module": module,
                "precise_input_tokens": mt["input_tokens"],
                "proxy_input_tokens": px,
                "output_tokens": ot,
                "kb_payload_chars": kb_chars,
                "full_payload_chars": pay_chars,
                "kb_payload_frac": (kb_chars / pay_chars) if pay_chars else None,
            }
        )

    for i, batch in enumerate(cand_batches):
        batch_tag = str(batch.get("batch") or "")
        ask = max(1, len(batch.get("parsed") or []) or 8)
        raw = batch.get("raw")
        if i == 0 and not batch_tag.startswith("fill"):
            prompt = FLAT_CANDIDATE_PROMPT.replace("__K__", str(ask))
            module = "PaperB02FlatCandidates"
            payload = dict(base)
            proxy_extra = None
        else:
            if batch_tag.startswith("fill") or (
                isinstance(batch.get("batch"), str) and "fill" in str(batch.get("batch"))
            ):
                aspect = ASPECTS[fill_i % 5]
                prompt = (
                    FLAT_CANDIDATE_EXPAND_PROMPT.replace("__K__", str(ask)).replace(
                        "__EXISTING__", "; ".join(candidates[:40]) or "(none)"
                    )
                    + f"\nFocus aspect: {aspect}. Prefer diseases not already listed."
                )
                module = f"PaperB02FlatCandidatesExpandFill_{fill_i}"
                payload = {
                    **base,
                    "existing_candidates": list(candidates),
                    "focus_aspect": aspect,
                }
                proxy_extra = {
                    "existing_candidates": list(candidates),
                    "focus_aspect": aspect,
                }
                fill_i += 1
            else:
                prompt = FLAT_CANDIDATE_EXPAND_PROMPT.replace("__K__", str(ask)).replace(
                    "__EXISTING__", "; ".join(candidates[:40])
                )
                module = "PaperB02FlatCandidatesExpand"
                payload = {**base, "existing_candidates": list(candidates)}
                proxy_extra = {"existing_candidates": list(candidates)}
        add(
            module=module,
            prompt=prompt,
            payload=payload,
            proxy_extra=proxy_extra,
            raw_out=raw,
            kind="candidate",
        )
        for name in batch.get("parsed") or []:
            if str(name).casefold() not in {c.casefold() for c in candidates}:
                candidates.append(str(name))

    # Prefer final candidates from trace if longer/more authoritative
    if final_candidates:
        candidates = list(final_candidates)

    for ei, ev in enumerate(evidence):
        # pad vs matrix: estimate script treated all as evidence prompt
        module = (
            "PaperB02FlatEvidenceMatrix"
            if ei < len(evidence)
            else "PaperB02FlatEvidenceMatrixPad"
        )
        # Cannot perfectly distinguish pad; use same prompt (identical text)
        add(
            module="PaperB02FlatEvidenceMatrix",
            prompt=FLAT_EVIDENCE_MATRIX_PROMPT,
            payload={**base, "candidates": candidates},
            proxy_extra={"candidates": candidates},
            raw_out=ev,
            kind="evidence",
        )
        # apply reorder if present
        ranked = []
        if isinstance(ev, dict):
            ranked = ev.get("ranked_candidates") or []
        if ranked:
            pool = {c.casefold(): c for c in candidates}
            front: list[str] = []
            seen: set[str] = set()
            for name in ranked:
                key = str(name).casefold()
                if key in pool and key not in seen:
                    front.append(pool[key])
                    seen.add(key)
            for name in candidates:
                key = name.casefold()
                if key not in seen:
                    front.append(name)
                    seen.add(key)
            candidates = front

    if rerank is not None:
        add(
            module="PaperB02FlatRerank",
            prompt=_adapt_prompt_for_k(FLAT_RERANK_PROMPT, list_k),
            payload={**base, "candidates": candidates},
            proxy_extra={"candidates": candidates},
            raw_out=rerank,
            kind="rerank",
        )

    accounted = len(calls)
    # burn remaining as evidence pads (same as estimate script)
    for _ in range(max(0, llm_calls - accounted)):
        add(
            module="PaperB02FlatEvidenceMatrixPad",
            prompt=FLAT_EVIDENCE_MATRIX_PROMPT,
            payload={**base, "candidates": candidates, "pad_round": accounted},
            proxy_extra={"candidates": candidates, "pad_round": accounted},
            raw_out={},
            kind="evidence_pad",
        )

    ratio = (precise_in / proxy_in) if proxy_in else None
    kb_fracs = [c["kb_payload_frac"] for c in calls if c.get("kb_payload_frac") is not None]
    return {
        "case_id": case["case_id"],
        "source_id": case.get("source_id"),
        "list_k": list_k,
        "llm_calls": llm_calls,
        "n_calls_reconstructed": len(calls),
        "snippet_chars_logged": snippet_chars,
        "chunk_audit": chunk_audit,
        "precise_input_tokens": precise_in,
        "proxy_input_tokens": proxy_in,
        "precise_over_proxy": ratio,
        "output_tokens": out_tok,
        "precise_total_tokens": precise_in + out_tok,
        "mean_kb_payload_frac": mean(kb_fracs) if kb_fracs else None,
        "vignette_chars": len(vignette),
        "calls": calls,
    }


DATASETS = {
    "diagnosisarena": {
        "pred_dir": ROOT
        / "runs/paper_v1/diagnosisarena_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01",
        "subset": ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
    },
    "open_xddx": {
        "pred_dir": ROOT
        / "runs/paper_v1/open_xddx_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01",
        "subset": ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1",
    },
    "medcasereasoning": {
        "pred_dir": ROOT
        / "runs/paper_v1/medcasereasoning_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01",
        "subset": ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
    },
}


def load_pred_trace(pred_dir: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    preds = {
        json.loads(l)["case_id"]: json.loads(l)
        for l in (pred_dir / "predictions.jsonl").read_text().splitlines()
        if l.strip()
    }
    traces = {
        json.loads(l)["case_id"]: json.loads(l)
        for l in (pred_dir / "trace.jsonl").read_text().splitlines()
        if l.strip()
    }
    return preds, traces


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-dataset", type=int, default=5)
    ap.add_argument(
        "--datasets",
        default="diagnosisarena,open_xddx,medcasereasoning",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT
        / "analysis/transfer_metrics_v1/b02_input_rebuild_sample_v1.json",
    )
    args = ap.parse_args()

    print("Loading corpus metadata indexes...", flush=True)
    rag = load_meta_index(ROOT / "data/corpus/rag_index/metadata.jsonl")
    cpg = load_meta_index(ROOT / "data/corpus/cpg_index/metadata.jsonl")
    print(f"  rag={len(rag)} cpg={len(cpg)}", flush=True)

    report: dict[str, Any] = {
        "schema_version": 1,
        "tokenizer": TOK,
        "per_dataset": args.per_dataset,
        "method": (
            "Rebuild B02 call_module inputs with real knowledge_chunks looked up "
            "from served_access_ids → corpus metadata.jsonl (content[:max_chunk_chars]). "
            "Compare to snippet_chars char-proxy from estimate_b02_m00_token_gap.py."
        ),
        "datasets": {},
    }

    for ds in [x.strip() for x in args.datasets.split(",") if x.strip()]:
        cfg = DATASETS[ds]
        print(f"=== {ds} ===", flush=True)
        cases = {
            c["case_id"]: c
            for c in load_runtime_cases(subset_dir=cfg["subset"], dataset=ds)
        }
        preds, traces = load_pred_trace(cfg["pred_dir"])
        # stable sample: first N by case_id sort
        ids = sorted(set(preds) & set(traces) & set(cases))[: args.per_dataset]
        rows = []
        for cid in ids:
            row = precise_case(
                case=cases[cid],
                pred=preds[cid],
                trace_wrap=traces[cid],
                rag=rag,
                cpg=cpg,
            )
            rows.append(row)
            print(
                f"  {cid}: precise_in={row['precise_input_tokens']} "
                f"proxy_in={row['proxy_input_tokens']} "
                f"ratio={row['precise_over_proxy']:.3f} "
                f"kb_frac={row['mean_kb_payload_frac']:.3f} "
                f"chunk_miss={row['chunk_audit']['n_miss']} "
                f"text_chars={row['chunk_audit']['text_chars']} "
                f"logged_snippet={row['snippet_chars_logged']}",
                flush=True,
            )

        ratios = [r["precise_over_proxy"] for r in rows if r.get("precise_over_proxy")]
        kb_fracs = [
            r["mean_kb_payload_frac"] for r in rows if r.get("mean_kb_payload_frac") is not None
        ]
        char_ratios = []
        for r in rows:
            logged = r["snippet_chars_logged"] or 0
            got = r["chunk_audit"]["text_chars"] or 0
            if logged:
                char_ratios.append(got / logged)

        report["datasets"][ds] = {
            "n": len(rows),
            "case_ids": ids,
            "mean_precise_input_tokens": mean(r["precise_input_tokens"] for r in rows),
            "mean_proxy_input_tokens": mean(r["proxy_input_tokens"] for r in rows),
            "mean_precise_over_proxy": mean(ratios) if ratios else None,
            "min_precise_over_proxy": min(ratios) if ratios else None,
            "max_precise_over_proxy": max(ratios) if ratios else None,
            "mean_kb_payload_frac": mean(kb_fracs) if kb_fracs else None,
            "mean_chunk_text_over_logged_snippet": mean(char_ratios) if char_ratios else None,
            "mean_output_tokens": mean(r["output_tokens"] for r in rows),
            "mean_precise_total_tokens": mean(r["precise_total_tokens"] for r in rows),
            "cases": rows,
        }

    # overall
    all_ratios = []
    all_kb = []
    for block in report["datasets"].values():
        for r in block["cases"]:
            if r.get("precise_over_proxy"):
                all_ratios.append(r["precise_over_proxy"])
            if r.get("mean_kb_payload_frac") is not None:
                all_kb.append(r["mean_kb_payload_frac"])
    report["overall"] = {
        "n_cases": sum(b["n"] for b in report["datasets"].values()),
        "mean_precise_over_proxy": mean(all_ratios) if all_ratios else None,
        "mean_kb_payload_frac": mean(all_kb) if all_kb else None,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = args.out.with_suffix(".md")
    lines = [
        "# B02 输入 token：少量病例精确重建校准",
        "",
        f"Tokenizer：`{TOK}`  ·  每集抽样 **{args.per_dataset}** 例",
        "",
        "## 做法",
        "",
        "1. 从 trace 读取 `served_access_ids` / `queries` / 各步 LLM raw；",
        "2. 在 `rag_index` / `cpg_index` 的 `metadata.jsonl` 中按 chunk id 取回正文，截断 `max_chunk_chars`；",
        "3. 按 `call_module` 格式重建每次调用的 system+user（含真实 `knowledge_chunks` 对象列表）；",
        "4. 与 `snippet_chars` 字符代理估计对比。",
        "",
        "## 结果",
        "",
        "| 数据集 | n | mean precise in | mean proxy in | precise/proxy | mean KB payload 占比 | chunk正文/logged snippet |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for ds, b in report["datasets"].items():
        lines.append(
            "| {ds} | {n} | {p:.0f} | {x:.0f} | **{r:.3f}** | {k:.1%} | {c:.3f} |".format(
                ds=ds,
                n=b["n"],
                p=b["mean_precise_input_tokens"],
                x=b["mean_proxy_input_tokens"],
                r=b["mean_precise_over_proxy"],
                k=b["mean_kb_payload_frac"] or 0,
                c=b["mean_chunk_text_over_logged_snippet"] or 0,
            )
        )
    ov = report["overall"]
    lines += [
        "",
        f"总体：n={ov['n_cases']}，mean precise/proxy=**{(ov['mean_precise_over_proxy'] or 0):.3f}**，"
        f"mean KB payload 占比=**{(ov['mean_kb_payload_frac'] or 0):.1%}**。",
        "",
        "## 解读",
        "",
        "- **上下文重发送**：已按每次 LLM 调用计入完整 vignette + chunks。",
        "- **KB chunks**：已用真实正文计入；在 payload 中通常占大部分字符。",
        "- 若 precise/proxy ≈ 1，说明全库 `snippet_chars` 代理可用；若系统性偏离，可用该比值校准全量估计。",
        "",
        f"JSON：[`{args.out.name}`]({args.out.name})",
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", args.out)
    print("WROTE", md)
    print(
        "OVERALL precise/proxy=",
        ov["mean_precise_over_proxy"],
        "kb_frac=",
        ov["mean_kb_payload_frac"],
    )


if __name__ == "__main__":
    main()
