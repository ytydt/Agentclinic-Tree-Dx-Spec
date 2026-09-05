#!/usr/bin/env python3
"""Alternative path, stage A: excerpt natural-language rule sentences.

The seven-slot schema of ``run_trial_extraction.py`` forces the model to commit
to relation / polarity / modality on every clause; the case-74 census puts the
relation error rate at 0.74 on the diagnostic slots.  This extractor asks for
nothing but a verbatim copy of the sentence that states the rule.  Everything a
downstream engine would need to *reason* stays in the English text; the only
structure added is a threshold parsed by ``parse_threshold_from_quote`` on the
program side, as a supplementary annotation.

The payload is the passage plus its provenance only -- no focus hypothesis --
so identical passages retrieved for different hypotheses share one cache entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
CACHE = LEDGER / "trial_extraction_cache"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_assertions import parse_threshold_from_quote  # noqa: E402

KIND = "nl_rules_v1"

NL_RULE_PROMPT = """You copy decision rules out of one passage of a clinical reference.

Return strict JSON: {"rules": [ ... ]}. Each rule:
{
  "disease": "<the disease the rule is about, spelled as the passage spells it>",
  "sentence": "<the sentence from the passage, copied character for character>",
  "use": "diagnosis" | "treatment" | "prognosis" | "other"
}

A rule is any sentence that tells a reader how to recognise, confirm, grade or
rule out a named disease, or how to choose a treatment for it.

Hard requirements:
- "sentence" must be a contiguous span copied verbatim from the passage. Do not
  paraphrase, do not fix grammar, do not join two separate sentences.
- Copy the WHOLE sentence, including every "and", "or", "unless", "if",
  "without", "at least", "in the absence of" and every number and unit. Those
  words are the rule; a fragment is not.
- If one sentence carries rules for two diseases, emit it once per disease.
- "disease" must be a disease name that appears in the passage.
- A sentence that only names a test, a drug or an anatomical fact without
  saying anything about recognising or treating a disease is not a rule; leave
  it out.
- If the passage states no rule, return {"rules": []}.
- Do not add fields. Do not label the sentence as necessary, sufficient,
  typical or excluding -- copy the wording and let the reader judge.
"""


def cache_key(kind: str, payload: dict, model: str) -> str:
    blob = json.dumps([kind, payload, model], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


class Extractor:
    def __init__(self, model: str, workers: int) -> None:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        CACHE.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.workers = workers
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

    def call(self, kind: str, module: str, prompt: str, payload: dict) -> dict:
        key = cache_key(kind, payload, self.model)
        path = CACHE / f"{key}.json"
        if path.exists():
            with self._lock:
                self.stats["cached"] += 1
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — a half-written cache entry
                pass
        try:
            out = self.client().call_module(module, prompt, payload)
        except Exception as exc:  # noqa: BLE001 — keep the pool moving
            print(f"[nl_rules] failed ({exc}); caching empty", flush=True)
            out = {}
        if not isinstance(out, dict):
            out = {}
        with self._lock:
            self.stats["called"] += 1
            if not out:
                self.stats["empty"] += 1
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out


_WS = re.compile(r"\s+")


def _flat(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip().lower()


def _verbatim(sentence: str, passage: str) -> str:
    """'exact' | 'whitespace' | 'no' -- how literally the span was copied."""
    if not sentence:
        return "no"
    if sentence in passage:
        return "exact"
    if _flat(sentence) and _flat(sentence) in _flat(passage):
        return "whitespace"
    return "no"


def _disease_in_passage(name: str, passage: str) -> bool:
    if not name:
        return False
    pl = passage.lower()
    nl = name.lower().strip()
    if nl in pl:
        return True
    words = [w for w in re.findall(r"[a-z0-9]+", nl) if len(w) >= 4]
    return bool(words) and all(w in pl for w in words)


def postprocess(out: dict, passage: str, prov: dict) -> tuple[list[dict], Counter]:
    """Keep only rules that were really copied out of this passage."""
    tally: Counter = Counter()
    kept: list[dict] = []
    for r in out.get("rules") or []:
        if not isinstance(r, dict):
            tally["not_a_dict"] += 1
            continue
        sent = str(r.get("sentence") or "").strip()
        disease = str(r.get("disease") or "").strip()
        v = _verbatim(sent, passage)
        tally[f"verbatim_{v}"] += 1
        if v == "no":
            tally["dropped_not_verbatim"] += 1
            continue
        if not _disease_in_passage(disease, passage):
            tally["dropped_disease_absent"] += 1
            continue
        # "Diagnosis of Alzheimer Disease" is a section heading, not a rule; a
        # span that short cannot carry a condition either way.
        if len(sent.split()) < 6:
            tally["dropped_too_short"] += 1
            continue
        kept.append({
            "disease": disease,
            "sentence": sent,
            "use": str(r.get("use") or "other").lower(),
            "threshold": parse_threshold_from_quote(sent) or {},
            "verbatim": v,
            **prov,
        })
    tally["kept"] += len(kept)
    return kept, tally


def context_hint(section_path: str, title: str) -> str:
    blob = f"{section_path} {title}".lower()
    for needle, ctype in (
        ("differential diagnosis", "differential"),
        ("histopatholog", "histopathology"),
        ("evaluation", "criteria"),
        ("etiolog", "definition"),
        ("epidemiolog", "epidemiology"),
        ("treatment", "treatment"),
        ("prognos", "prognosis"),
        ("introduction", "definition"),
    ):
        if needle in blob:
            return ctype
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30all4")
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--max-passage-chars", type=int, default=6000)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-case", default="")
    ap.add_argument("--out", default="trial_nl_rules_k30all4.json")
    args = ap.parse_args()

    os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

    tasks = {t["case_key"] for t in json.loads((LEDGER / args.tasks).read_text("utf-8"))}
    retrieval = json.loads((LEDGER / f"trial_retrieval_{args.arm}.json").read_text("utf-8"))

    # One job per unique passage payload; remember which cases asked for it.
    jobs: dict[str, dict] = {}
    for rec in retrieval:
        if rec["case_key"] not in tasks:
            continue
        if args.only_case and rec["case_key"] != args.only_case:
            continue
        for label, bundle in rec["retrieved"].items():
            for p in bundle["passages"]:
                passage = p["text"][: args.max_passage_chars]
                payload = {
                    "source": p["source"],
                    "document_title": p["title"],
                    "section_path": p["section_path"],
                    "context_hint": context_hint(p["section_path"], p["title"]),
                    "passage": passage,
                }
                k = cache_key(KIND, payload, args.model)
                job = jobs.setdefault(k, {"payload": payload, "askers": set()})
                job["askers"].add((rec["case_key"], label))

    job_list = list(jobs.items())
    if args.limit:
        job_list = job_list[: args.limit]
    print(f"{len(job_list)} unique passage payloads", flush=True)

    ex = Extractor(args.model, args.workers)

    def do(item):
        key, job = item
        out = ex.call(KIND, "GuidelineRuleExcerpter", NL_RULE_PROMPT, job["payload"])
        return key, job, out

    tally: Counter = Counter()
    per_case: dict[str, list[dict]] = {c: [] for c in tasks}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (key, job, out) in enumerate(pool.map(do, job_list), 1):
            payload = job["payload"]
            passage = payload["passage"]
            prov = {
                "_source": payload["source"],
                "_title": payload["document_title"],
                "_section": payload["section_path"],
                "_passage_sha1": hashlib.sha1(passage.encode("utf-8")).hexdigest()[:16],
            }
            rules, t = postprocess(out, passage, prov)
            tally.update(t)
            for case_key, label in job["askers"]:
                if case_key not in per_case:
                    continue
                for r in rules:
                    per_case[case_key].append({**r, "_focus": label})
            if i % 100 == 0:
                print(f"  {i}/{len(job_list)} (cached={ex.stats['cached']} "
                      f"called={ex.stats['called']} empty={ex.stats['empty']} "
                      f"kept={tally['kept']})", flush=True)

    records = []
    for case_key in sorted(per_case):
        rules = per_case[case_key]
        uniq = {}
        for r in rules:
            uniq.setdefault((_flat(r["disease"]), _flat(r["sentence"])), r)
        records.append({
            "case_key": case_key,
            "n_rules_raw": len(rules),
            "n_rules_unique": len(uniq),
            "rules": rules,
        })
        print(f"  {case_key:24s} raw={len(rules):5d} unique={len(uniq):5d}", flush=True)

    out_path = LEDGER / args.out
    out_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    stats_path = LEDGER / (out_path.stem + "_stats.json")
    stats_path.write_text(json.dumps({
        "model": args.model,
        "arm": args.arm,
        "n_payloads": len(job_list),
        "llm": ex.stats,
        "postprocess": dict(tally),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}\nwrote {stats_path}")
    print(json.dumps(dict(tally), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
