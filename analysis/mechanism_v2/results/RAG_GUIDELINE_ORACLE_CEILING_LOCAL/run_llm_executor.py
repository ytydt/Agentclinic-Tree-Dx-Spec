#!/usr/bin/env python3
"""Alternative path, stage B: an LLM instead of the mechanical rule engine.

Five rule representations are fed to the same executor prompt, on the same 11
cases, with the same candidate sets and the same patient evidence the
mechanical engine sees:

  none        no rules at all -- the parametric-knowledge control.  Without it
              a good score on the other arms cannot be credited to the rules.
  tuple       the seven slots as the mechanical engine consumes them
              (relation / polarity / modality / threshold), quote withheld.
  tuple_quote the seven slots plus the quote they were extracted from.
  nl_quote    the extracted quote alone, slots discarded -- the cheap version
              of the alternative path, reusing the existing extraction.
  nl_rule     the verbatim rule sentences from ``extract_nl_rules.py``.

Candidate order is shuffled per repetition so a position-biased ranker cannot
score by accident, and every repetition is a distinct cache entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
CACHE = LEDGER / "trial_extraction_cache"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
from run_trial_extraction import strip_options  # noqa: E402

KIND = "llm_executor_v1"

EXECUTOR_PROMPT = """You are the decision engine of a diagnostic pipeline.

You are given one patient, a closed list of candidate diagnoses, and the
reference material that was retrieved for each candidate. Rank the candidates.

Return strict JSON:
{"ranking": [{"candidate": "<label copied exactly from the candidate list>",
              "verdict": "supported" | "neutral" | "ruled_out",
              "why": "<one sentence naming the patient fact and the reference
                      material you used>"}]}

Rules of the task:
- Rank EVERY candidate exactly once, best first. Copy the labels exactly.
- Judge a candidate on the patient facts and the material listed under it.
- Mark a candidate "ruled_out" only when a patient fact contradicts a
  requirement in that candidate's material, or matches an exclusion in it.
- Reference material may be incomplete, off-topic or wrong. If it does not
  decide the case, say neutral rather than inventing a decision from it.
- If a candidate has no material, judge it on the patient facts.
- Return JSON only.
"""


# ---------------------------------------------------------------- LLM plumbing


def cache_key(kind: str, payload: dict, model: str) -> str:
    blob = json.dumps([kind, payload, model], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


class Caller:
    def __init__(self, model: str) -> None:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        CACHE.mkdir(parents=True, exist_ok=True)
        self.model = model
        self._local = threading.local()
        self._client_cls = RobustLLMClient
        self.stats = {"cached": 0, "called": 0, "empty": 0}
        self._lock = threading.Lock()

    def client(self):
        c = getattr(self._local, "client", None)
        if c is None:
            c = self._client_cls(model=self.model, temperature=0.0, max_retries=2)
            self._local.client = c
        return c

    def call(self, payload: dict) -> dict:
        key = cache_key(KIND, payload, self.model)
        path = CACHE / f"{key}.json"
        if path.exists():
            with self._lock:
                self.stats["cached"] += 1
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        try:
            out = self.client().call_module("DiagnosticRuleExecutor", EXECUTOR_PROMPT, payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[executor] failed ({exc})", flush=True)
            out = {}
        if not isinstance(out, dict):
            out = {}
        with self._lock:
            self.stats["called"] += 1
            if not out:
                self.stats["empty"] += 1
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out


# ------------------------------------------------------------ rule assembly

_WS = re.compile(r"\s+")


def _flat(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip().lower()


def bind_to_candidates(items: list[dict], candidates: list[dict],
                       subject_field: str) -> tuple[dict[str, list[dict]], int]:
    """Same subject matcher the mechanical engine uses, so binding is not a
    confound between the two engines."""
    bound: dict[str, list[dict]] = defaultdict(list)
    unbound = 0
    for it in items:
        subj = str(it.get(subject_field) or "")
        hit = None
        for cand in candidates:
            for name in [cand["label"], *(cand.get("aliases") or [])]:
                if eng.subject_match(subj, name):
                    hit = cand["label"]
                    break
            if hit:
                break
        if hit is None:
            unbound += 1
            continue
        bound[hit].append(it)
    return bound, unbound


def _threshold_str(th: dict | None) -> str:
    th = th or {}
    op, val, unit = th.get("operator"), th.get("value"), th.get("unit") or ""
    if not op or val is None:
        return ""
    if op == "range" and th.get("value_high") is not None:
        return f"{val}-{th['value_high']} {unit}".strip()
    return f"{op} {val} {unit}".strip()


def render_rules(mode: str, bound: dict[str, list[dict]], label: str,
                 cap: int) -> tuple[list[str], int]:
    """Dedupe, rank by how often the corpus repeats the rule, cap, render."""
    items = bound.get(label) or []
    seen: dict[tuple, dict] = {}
    for it in items:
        if mode in {"tuple", "tuple_quote"}:
            key = (_flat(it.get("predicate")), it.get("relation"),
                   it.get("polarity"), it.get("modality"))
            if mode == "tuple_quote":
                key = key + (_flat(it.get("quote")),)
        elif mode == "nl_quote":
            key = (_flat(it.get("quote")),)
        else:
            key = (_flat(it.get("sentence")),)
        prev = seen.get(key)
        if prev is None:
            it = dict(it)
            it["_support"] = 1
            seen[key] = it
        else:
            prev["_support"] += 1
    ordered = sorted(seen.values(), key=lambda a: -a["_support"])
    truncated = max(0, len(ordered) - cap)
    lines = []
    for it in ordered[:cap]:
        n = it["_support"]
        if mode in {"tuple", "tuple_quote"}:
            th = _threshold_str(it.get("threshold"))
            cg = it.get("criterion_group") or {}
            bits = [f"relation={it.get('relation')}", f"polarity={it.get('polarity')}",
                    f"modality={it.get('modality')}"]
            if th:
                bits.append(f"threshold={th}")
            if cg.get("group_id") and cg.get("logic"):
                bits.append(f"group={cg['logic']}/{cg.get('n') or '?'}:{cg['group_id']}")
            line = f"- {it.get('subject')} | {it.get('predicate')} [{', '.join(bits)}] (x{n})"
            if mode == "tuple_quote":
                line += f'\n    source: "{(it.get("quote") or "").strip()}"'
        elif mode == "nl_quote":
            th = _threshold_str(it.get("threshold"))
            line = f'- "{(it.get("quote") or "").strip()}" (x{n})'
            if th:
                line += f"  [threshold: {th}]"
        else:
            th = _threshold_str(it.get("threshold"))
            line = f'- "{(it.get("sentence") or "").strip()}" (x{n})'
            if th:
                line += f"  [threshold: {th}]"
            if (it.get("use") or "") not in {"diagnosis", "other", ""}:
                line += f"  [{it['use']}]"
        lines.append(line)
    return lines, truncated


def render_patient(mode: str, task: dict, findings: list[dict]) -> str:
    if mode == "vignette":
        return strip_options(task["vignette"])
    lines = []
    for f in findings:
        if not isinstance(f, dict) or not f.get("label"):
            continue
        val = f.get("value") or {}
        num = val.get("number")
        v = ""
        if num is not None:
            v = f" = {num}{(' ' + val['unit']) if val.get('unit') else ''}"
        elif val.get("text"):
            v = f" = {val['text']}"
        lines.append(f"- {f['label']} ({f.get('kind') or 'other'}): "
                     f"{f.get('polarity') or 'present'}{v}")
    return "\n".join(lines)


# ------------------------------------------------------------------- scoring


def parse_ranking(out: dict, presented: list[str]) -> tuple[list[str], dict[str, str]]:
    """Recover a full permutation; anything the model dropped keeps its
    presented order at the tail, so a truncated answer is penalised but not
    scored as random."""
    by_norm = {eng.norm(c): c for c in presented}
    ranked: list[str] = []
    verdicts: dict[str, str] = {}
    for row in out.get("ranking") or []:
        if isinstance(row, str):
            row = {"candidate": row}
        if not isinstance(row, dict):
            continue
        name = str(row.get("candidate") or "").strip()
        hit = by_norm.get(eng.norm(name))
        if hit is None:
            for c in presented:
                if eng.subject_match(name, c):
                    hit = c
                    break
        if hit is None or hit in ranked:
            continue
        ranked.append(hit)
        verdicts[hit] = str(row.get("verdict") or "neutral").lower()
    for c in presented:
        if c not in ranked:
            ranked.append(c)
    return ranked, verdicts


def metrics(results: list[dict], boot: int = 4000, seed: int = 0) -> dict:
    ranks = [r["gold_rank"] for r in results]
    rr = [1.0 / r if r else 0.0 for r in ranks]
    rnd = random.Random(seed)
    n = len(results)
    boots = sorted(sum(rr[rnd.randrange(n)] for _ in range(n)) / n for _ in range(boot))
    return {
        "n": n,
        "top1": sum(1 for r in results if r["top1_is_gold"]),
        "top3": sum(1 for r in results if (r["gold_rank"] or 99) <= 3),
        "mrr": round(sum(rr) / n, 4),
        "mrr_ci": [round(boots[int(0.025 * boot)], 4), round(boots[int(0.975 * boot)], 4)],
        "median_rank": sorted(r or 99 for r in ranks)[n // 2],
        "gold_eliminated": sum(1 for r in results if r["gold_ruled_out"]),
        "empty_answers": sum(1 for r in results if r["n_ranked_by_model"] == 0),
        "per_case": {r["case_key"]: r["gold_rank"] for r in results},
        "top1_labels": {r["case_key"]: r["top1"] for r in results},
    }


# ---------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    ap.add_argument("--extraction", default="trial_extraction_k30all4clean_groups.json")
    ap.add_argument("--nl-rules", default="trial_nl_rules_k30all4.json")
    ap.add_argument("--rules", default="none,tuple,tuple_quote,nl_quote,nl_rule")
    ap.add_argument("--patient", default="findings", choices=["findings", "vignette"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--cap", type=int, default=40, help="rules shown per candidate")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=11)
    ap.add_argument("--fixed-order", action="store_true",
                    help="present the candidates in the same order in every "
                         "repetition; the spread that survives is decoding noise "
                         "rather than position sensitivity")
    ap.add_argument("--quote-gate", action="store_true",
                    help="apply the F7 gate to the tuple arms, matching cell C1")
    ap.add_argument("--out", default="llm_executor_results.json")
    args = ap.parse_args()

    os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

    tasks = {t["case_key"]: t
             for t in json.loads((LEDGER / args.tasks).read_text("utf-8"))}
    ext = {e["case_key"]: e
           for e in json.loads((LEDGER / args.extraction).read_text("utf-8"))}
    modes = [m.strip() for m in args.rules.split(",") if m.strip()]

    nl = {}
    if "nl_rule" in modes:
        p = LEDGER / args.nl_rules
        if not p.exists():
            print(f"missing {p}; dropping nl_rule arm", flush=True)
            modes = [m for m in modes if m != "nl_rule"]
        else:
            nl = {e["case_key"]: e for e in json.loads(p.read_text("utf-8"))}

    caller = Caller(args.model)
    jobs = []
    for mode in modes:
        for rep in range(args.reps):
            for key, task in tasks.items():
                jobs.append((mode, rep, key, task))

    def build(mode: str, rep: int, key: str, task: dict) -> tuple[dict, dict]:
        e = ext[key]
        assertions = [a for a in e["assertions"] if isinstance(a, dict)]
        if args.quote_gate and mode in {"tuple", "tuple_quote"}:
            from gate_assertions import gate_assertions
            assertions = gate_assertions(assertions, apply_nli=False)
        candidates = task["candidates"]
        presented = [c["label"] for c in candidates]
        random.Random(1000 if args.fixed_order else 1000 + rep).shuffle(presented)

        blocks, truncated, n_rules = [], 0, 0
        if mode != "none":
            if mode == "nl_rule":
                bound, _ = bind_to_candidates(nl[key]["rules"], candidates, "disease")
            else:
                bound, _ = bind_to_candidates(assertions, candidates, "subject")
            by_label = {}
            for label in presented:
                lines, tr = render_rules(mode, bound, label, args.cap)
                truncated += tr
                n_rules += len(lines)
                by_label[label] = lines
            for label in presented:
                lines = by_label[label]
                body = "\n".join(lines) if lines else "  (no material retrieved)"
                blocks.append(f"### {label}\n{body}")

        payload = {
            "patient": render_patient(args.patient, task, e["findings"]),
            "candidates": presented,
            "reference_material": "\n\n".join(blocks) if blocks else
                                  "(none provided -- judge on the patient facts)",
            "repetition": rep,
        }
        meta = {"n_rules_shown": n_rules, "n_rules_truncated": truncated,
                "presented": presented}
        return payload, meta

    def do(job):
        mode, rep, key, task = job
        payload, meta = build(mode, rep, key, task)
        out = caller.call(payload)
        ranked, verdicts = parse_ranking(out, meta["presented"])
        gold_labels = set(task["gold_labels_in_set"])
        top1 = ranked[0] if ranked else ""
        gold_rank = next((i + 1 for i, c in enumerate(ranked) if c in gold_labels), None)
        return {
            "mode": mode, "rep": rep, "case_key": key,
            "gold": task["gold"],
            "n_candidates": len(meta["presented"]),
            "n_rules_shown": meta["n_rules_shown"],
            "n_rules_truncated": meta["n_rules_truncated"],
            "n_ranked_by_model": len(verdicts),
            "top1": top1,
            "top1_is_gold": top1 in gold_labels,
            "top1_verdict": verdicts.get(top1, ""),
            "gold_rank": gold_rank,
            "gold_verdict": next((verdicts.get(c) for c in ranked if c in gold_labels), None),
            "gold_ruled_out": any(verdicts.get(c) == "ruled_out"
                                  for c in ranked if c in gold_labels),
            "ranking": ranked,
            "verdicts": verdicts,
        }

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, r in enumerate(pool.map(do, jobs), 1):
            rows.append(r)
            if i % 11 == 0:
                print(f"  {i}/{len(jobs)} (cached={caller.stats['cached']} "
                      f"called={caller.stats['called']} empty={caller.stats['empty']})",
                      flush=True)

    summary: dict = {"model": args.model, "patient": args.patient, "cap": args.cap,
                     "reps": args.reps, "quote_gate": args.quote_gate, "arms": {}}
    for mode in modes:
        per_rep = []
        for rep in range(args.reps):
            sub = [r for r in rows if r["mode"] == mode and r["rep"] == rep]
            if sub:
                per_rep.append(metrics(sub))
        pooled = [r for r in rows if r["mode"] == mode]
        summary["arms"][mode] = {
            "per_rep": per_rep,
            "top1_mean": round(sum(m["top1"] for m in per_rep) / max(len(per_rep), 1), 2),
            "top3_mean": round(sum(m["top3"] for m in per_rep) / max(len(per_rep), 1), 2),
            "mrr_mean": round(sum(m["mrr"] for m in per_rep) / max(len(per_rep), 1), 4),
            "top1_range": [min((m["top1"] for m in per_rep), default=0),
                           max((m["top1"] for m in per_rep), default=0)],
            "gold_eliminated_mean": round(
                sum(m["gold_eliminated"] for m in per_rep) / max(len(per_rep), 1), 2),
            "rules_shown_mean": round(
                sum(r["n_rules_shown"] for r in pooled) / max(len(pooled), 1), 1),
            "rules_truncated_mean": round(
                sum(r["n_rules_truncated"] for r in pooled) / max(len(pooled), 1), 1),
            "gold_top1_rate_by_case": {
                k: round(sum(1 for r in pooled if r["case_key"] == k and r["top1_is_gold"])
                         / max(sum(1 for r in pooled if r["case_key"] == k), 1), 2)
                for k in tasks
            },
        }
        a = summary["arms"][mode]
        print(f"{mode:12s} top1={a['top1_mean']:.2f}/11 {a['top1_range']} "
              f"top3={a['top3_mean']:.2f} MRR={a['mrr_mean']:.3f} "
              f"elim_gold={a['gold_eliminated_mean']:.2f} "
              f"rules/case={a['rules_shown_mean']:.0f}", flush=True)

    out_path = LEDGER / args.out
    out_path.write_text(json.dumps({"summary": summary, "rows": rows},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
