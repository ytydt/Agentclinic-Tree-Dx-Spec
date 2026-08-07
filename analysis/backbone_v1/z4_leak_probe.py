#!/usr/bin/env python3
"""Z4: quantify the MCQ-option leak in the pipeline's ``case_summary``.

``env.get_case_summary()`` returns ``vignette + Question + Options``. The
controller feeds that to ``_llm_ddx_entities``; ``baseline_common`` strips it
("do not inject MCQ options into arms"). On MCR the options are synthesised with
the gold diagnosis always in position A.

Three conditions for the SAME S2 prompt and the SAME S1 anchor:
  a_body    stripped vignette (what the backbone and the baselines see)
  b_summary pipeline case_summary with the Options block removed
  c_leak    pipeline case_summary verbatim (what M00 / AB02 see)

Usage:
  PYTHONPATH=src:scripts:scripts/paper python3 analysis/backbone_v1/z4_leak_probe.py
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from mapper_bind_repair import leaf_match_score  # noqa: E402

from agentclinic_tree_dx.backbone import _as_str_list, _read_prompt  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

MODEL = "meta-llama/llama-3.3-70b-instruct"
OUT = ROOT / "analysis/backbone_v1/z4_leak_probe.json"
OPT_RE = re.compile(r"\n\s*(?:Question:.*?)?\n?\s*Options:.*$", re.S)

DATASETS = {
    "medcasereasoning": dict(
        subset=ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
        trees=ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_v1/annotate/shared_trees",
        stages=ROOT / "logs/backbone_v1/medcasereasoning/v0_s4b_k5/case_stages",
        scores=ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_v1/annotate/official_eval_llm_compat/case_scores",
    ),
    "diagnosisarena": dict(
        subset=ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
        trees=ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/annotate/shared_trees",
        stages=ROOT / "logs/backbone_v1/diagnosisarena/v0_s4b_k5/case_stages",
        scores=None,
    ),
}


def gold_map(ds: str, cfg: dict) -> dict[str, str]:
    if cfg["scores"] is not None:
        out = {}
        for f in Path(cfg["scores"]).glob("*.json"):
            r = json.loads(f.read_text())
            out[str(r["case_id"])] = str(r["gold_diagnosis"])
        return out
    cases = bc.load_runtime_cases(dataset=ds, subset_dir=cfg["subset"])
    return {str(c["source_id"]): str(c["_gold_text"]) for c in cases}


def main() -> int:
    prompt = _read_prompt("backbone_wide_ddx.txt")
    client = RobustLLMClient(
        model=MODEL, call_timeout=240, max_retries=5,
        timeout_retry_cap=2, temperature=0.0,
    )
    report: dict = {}
    for ds, cfg in DATASETS.items():
        gold = gold_map(ds, cfg)
        cases = bc.load_runtime_cases(dataset=ds, subset_dir=cfg["subset"])
        body = {str(c["source_id"]): c["vignette"] for c in cases}
        anchor = {}
        for f in Path(cfg["stages"]).glob("*.json"):
            d = json.loads(f.read_text())
            s1 = d["stages"]["s1"]
            anchor[str(d["source_id"])] = (
                s1.get("syndrome_frame") or "",
                list(s1.get("salient_findings") or []),
            )
        summary = {}
        for f in Path(cfg["trees"]).glob("*.json"):
            st = json.loads(f.read_text())["state"]
            summary[f.stem] = str(st.get("case_summary") or "")

        sids = sorted(set(gold) & set(body) & set(anchor) & set(summary))
        cache = ROOT / f"logs/backbone_v1/z4_leak_probe/{ds}.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        llm = bc.SimpleCachedLLM(client, cache, MODEL)

        arms = {
            "a_body": lambda s: body[s],
            "b_summary_stripped": lambda s: OPT_RE.sub("", summary[s]).strip(),
            "c_summary_leak": lambda s: summary[s],
        }
        rows: dict[str, dict[str, list[str]]] = {a: {} for a in arms}

        def task(item):
            arm, sid = item
            syn, sal = anchor[sid]
            got = llm.call(f"Z4_{arm}", prompt, {
                "presenting_syndrome": syn,
                "salient_findings": sal,
                "context": arms[arm](sid)[:1500],
            })
            return arm, sid, _as_str_list((got or {}).get("differentials"))

        jobs = [(a, s) for a in arms for s in sids]
        with ThreadPoolExecutor(max_workers=20) as pool:
            futs = [pool.submit(task, j) for j in jobs]
            done = 0
            for fut in as_completed(futs):
                try:
                    arm, sid, lst = fut.result()
                    rows[arm][sid] = lst
                except Exception as exc:
                    print(f"  ERROR {exc}", flush=True)
                done += 1
                if done % 50 == 0:
                    print(f"  [{ds}] {done}/{len(jobs)}", flush=True)

        def cov(g, xs):
            return any(leaf_match_score(g, x) >= 0.7 for x in xs)

        res = {}
        print(f"\n=== {ds} (n={len(sids)}) ===")
        print(f"{'条件':26} {'|列表|':>6} {'覆盖':>6} {'首项':>6} {'金标准逐字出现在context':>10}")
        for arm in arms:
            r = rows[arm]
            n = len(r)
            if not n:
                continue
            c = sum(cov(gold[s], r[s]) for s in r)
            f0 = sum(
                bool(r[s]) and leaf_match_score(gold[s], r[s][0]) >= 0.7 for s in r
            )
            ln = sum(len(r[s]) for s in r) / n
            leak = sum(
                1 for s in r
                if gold[s].lower() in arms[arm](s)[:1500].lower()
            )
            res[arm] = {
                "n": n, "coverage": c / n, "first": f0 / n,
                "mean_len": ln, "gold_verbatim_in_context": leak / n,
            }
            print(f"{arm:26} {ln:6.1f} {c/n:6.3f} {f0/n:6.3f} {leak/n:10.0%}")
        report[ds] = {"n": len(sids), "arms": res}

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
