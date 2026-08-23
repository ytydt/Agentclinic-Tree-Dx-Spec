#!/usr/bin/env python3
"""`SYMPTOM_CLUSTER_G1_RECALL_PRESERVATION` — the recall-preservation gate.

Executes the frozen contract in `results/SYMPTOM_CLUSTER_G1/PREREGISTRATION.md`.

    verify   G0' byte-exact payload reconstruction on the 67 dev cases  (0 calls)
    run      one intervened `c3:commit` call per case per arm           (67 each)
    score    retention, change rate, fabrication guard, §4.4 exit       (0 calls)

Only the `c3:commit` prompt changes. Everything upstream (`c1`, `facts`, `c2`,
`axis_contract`, `axis_guard`) and every other stance is reused from the frozen
log, which is what makes the gate cost 134 calls and zero panel.

The frozen run's cache is opened read-only; intervened arms write their own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "backbone_v1", ROOT / "scripts" / "paper"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import baseline_common as bc  # noqa: E402

from analysis.mechanism_v2.clinical_endpoint import ClinicalEndpoint  # noqa: E402

EXPERIMENT_ID = "SYMPTOM_CLUSTER_G1_RECALL_PRESERVATION"
OUT = ROOT / "analysis/mechanism_v2/results/SYMPTOM_CLUSTER_G1"
PROMPTS = ROOT / "src/agentclinic_tree_dx/prompts"

MODULE = "AphhmCBatchedConcepts"
MODEL = "meta-llama/llama-3.3-70b-instruct"
UNIQUE_BUDGET = 10
WORKERS = 25

# `mode=multistance` runs with `axis_mode=off`, so the payload carries no axis or
# family block. Verified byte-exact by the `verify` stage before any online call.
ARM_PROMPT = {
    "frozen": "aphhm_c_batched_concepts_commit.txt",
    "arm_A": "aphhm_c_batched_concepts_commit_cluster_a.txt",
    "arm_B": "aphhm_c_batched_concepts_commit_cluster_b.txt",
}
SLICE_DIR = {"mcr_v1": "medcasereasoning", "mcr_v2": "medcasereasoning_v2"}
SUBSET_OF_SLICE = {"mcr_v1": "mcr_val_seq100_v1", "mcr_v2": "mcr_val_seq100_v2"}

# §4.3, frozen in cohort.json: dev + c3:commit, n=992.
BASELINE_LEDGER_GROUPS = 2.1442
BASELINE_SPANS = 2.5897
BASELINE_REDUNDANCY = 0.3679
GATE_MIN_RETAINED = 61
GATE_MIN_CHANGE_RATE = 0.15


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_text(arm: str) -> str:
    return (PROMPTS / ARM_PROMPT[arm]).read_text(encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def frozen_run_dir(sl: str) -> Path:
    return ROOT / "logs/backbone_v1" / SLICE_DIR[sl] / "aphhm_c_multistance_v1"


def frozen_cache(sl: str) -> dict[str, Any]:
    return json.loads((frozen_run_dir(sl) / "cache" / "aphhm_c_llm.json").read_text())


def vignettes(sl: str) -> dict[str, str]:
    cases = bc.load_runtime_cases(
        subset_dir=ROOT / "data/benchmarks/medcasereasoning/subsets" / SUBSET_OF_SLICE[sl],
        dataset="medcasereasoning",
    )
    return {str(c["source_id"]): str(c["vignette"]) for c in cases}


def stages_of(sl: str, case_id: str) -> dict[str, Any]:
    path = frozen_run_dir(sl) / "case_stages" / f"{case_id}.json"
    return json.loads(path.read_text())


def build_payload(stages: Mapping[str, Any], vignette: str) -> dict[str, Any]:
    """The exact dict `_generate_concepts` handed to every stance."""
    guard = stages.get("axis_guard") or {}
    return {
        "vignette": vignette,
        "facts": [
            {
                "fact_id": f["fact_id"],
                "raw_span": f["raw_span"],
                "specificity": f["specificity"],
            }
            for f in (stages.get("facts") or [])
        ],
        "gap_obligation_fact_ids": guard.get("uncovered_high_specific_fact_ids") or [],
        "unique_budget": UNIQUE_BUDGET,
    }


def payload_key(prompt: str, payload: Mapping[str, Any]) -> str:
    return bc.stable_hash({"module": MODULE, "prompt": prompt, "payload": payload})


def commit_concepts(stages: Mapping[str, Any]) -> list[dict[str, Any]]:
    for st in ((stages.get("c3") or {}).get("stances") or []):
        if str(st.get("stance") or "") == "commit":
            return list(st.get("concepts") or [])
    return []


def load_cohort() -> list[dict[str, Any]]:
    return json.loads((OUT / "cohort.json").read_text())["dev"]


def case_context(row: Mapping[str, Any], vig_cache: dict[str, dict[str, str]]):
    sl, cid = row["slice"], row["case_id"]
    if sl not in vig_cache:
        vig_cache[sl] = vignettes(sl)
    doc = stages_of(sl, cid)
    stages = doc["stages"]
    vignette = vig_cache[sl][str(doc["source_id"])]
    return doc, stages, vignette


# --------------------------------------------------------------------------
# stage: verify (G0')
# --------------------------------------------------------------------------


def stage_verify(_: argparse.Namespace) -> int:
    """§2.1: prove the rebuilt payload is the one the frozen run actually sent.

    The frozen logs record only a call count, not payloads, so identity is
    established through the cache key: a hit on `stable_hash({module, prompt,
    payload})` in the frozen run's own cache can only happen if the payload is
    byte-identical, and the cached response is then compared to the recorded
    stage output.
    """
    cohort = load_cohort()
    prompt = prompt_text("frozen")
    vig_cache: dict[str, dict[str, str]] = {}
    caches = {sl: frozen_cache(sl) for sl in SLICE_DIR}
    rows: list[dict[str, Any]] = []

    for row in cohort:
        doc, stages, vignette = case_context(row, vig_cache)
        key = payload_key(prompt, build_payload(stages, vignette))
        cached = caches[row["slice"]].get(key)
        recorded = commit_concepts(stages)
        rows.append({
            "case_id": row["case_id"],
            "slice": row["slice"],
            "cache_hit": cached is not None,
            "output_identical": bool(
                cached is not None and (cached.get("concepts") or []) == recorded
            ),
            "n_concepts": len(recorded),
        })

    hits = sum(1 for r in rows if r["cache_hit"])
    ident = sum(1 for r in rows if r["output_identical"])
    result = {
        "experiment_id": EXPERIMENT_ID,
        "stage": "G0' payload fidelity",
        "created_at": utcnow(),
        "n_cases": len(rows),
        "cache_hit": hits,
        "output_identical": ident,
        "pass": len(rows) > 0 and ident == len(rows),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "mismatches": [r for r in rows if not r["output_identical"]],
        "cases": rows,
    }
    write_json(OUT / "verify.json", result)
    print(f"G0': n={len(rows)} cache_hit={hits} identical={ident} pass={result['pass']}")
    if not result["pass"]:
        print("ABORT: §2.1 requires byte-exact reconstruction before any online call.")
        return 1
    return 0


# --------------------------------------------------------------------------
# stage: run
# --------------------------------------------------------------------------


def stage_run(args: argparse.Namespace) -> int:
    verify = OUT / "verify.json"
    if not verify.is_file() or not json.loads(verify.read_text()).get("pass"):
        raise SystemExit("G0' has not passed; §2.1 forbids online calls until it does")

    arm = args.arm
    cohort = load_cohort()
    if args.limit:
        cohort = cohort[: args.limit]
    prompt = prompt_text(arm)
    vig_cache: dict[str, dict[str, str]] = {}

    from agentclinic_tree_dx.llm_client import RobustLLMClient

    client = RobustLLMClient(model=MODEL, temperature=0.0)
    llm = bc.SimpleCachedLLM(client, OUT / "runs" / arm / "cache.json", MODEL)

    jobs = []
    for row in cohort:
        doc, stages, vignette = case_context(row, vig_cache)
        jobs.append((row, build_payload(stages, vignette)))

    def one(job) -> dict[str, Any]:
        row, payload = job
        try:
            resp = llm.call(MODULE, prompt, payload)
            return {"case_id": row["case_id"], "slice": row["slice"],
                    "ok": True, "response": resp}
        except Exception as exc:  # noqa: BLE001
            return {"case_id": row["case_id"], "slice": row["slice"],
                    "ok": False, "error": repr(exc)[:400]}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(one, j) for j in jobs]
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda r: (r["slice"], r["case_id"]))
    served = sum(1 for r in results if r["ok"])
    name = "responses.json" if not args.limit else f"responses_smoke{args.limit}.json"
    write_json(OUT / "runs" / arm / name, {
        "experiment_id": EXPERIMENT_ID,
        "arm": arm,
        "created_at": utcnow(),
        "model": MODEL,
        "prompt_file": ARM_PROMPT[arm],
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "n": len(results),
        "n_served": served,
        "results": results,
    })
    print(f"{arm}: n={len(results)} served={served}")
    return 0


# --------------------------------------------------------------------------
# stage: score
# --------------------------------------------------------------------------


def evidence_stats(
    per_case: Sequence[tuple[Sequence[Mapping[str, Any]], Mapping[str, str]]],
) -> dict[str, Any]:
    """Ledger-derived vs self-reported evidence width (§4.3 fabrication guard).

    `fact_id` is numbered per case (`F01`, `F02`, ...), so each case must be
    looked up against its own ledger; merging the maps would silently collide.
    """
    ledger, spans, reported, redundant = [], [], [], 0
    unresolved = 0
    for concepts, group_of_fact in per_case:
        for c in concepts:
            fids = c.get("support_fact_ids") or []
            if not fids:
                continue
            resolved = [group_of_fact[f] for f in fids if group_of_fact.get(f)]
            unresolved += len(fids) - len(resolved)
            n_ledger = len(set(resolved))
            n_spans = len(c.get("support_spans") or [])
            ledger.append(n_ledger)
            spans.append(n_spans)
            redundant += int(n_spans > n_ledger)
            groups = c.get("observation_groups")
            if isinstance(groups, list) and groups:
                reported.append(len({str(g) for g in groups}))
    n = len(ledger)
    return {
        "n_candidates": n,
        "ledger_groups_mean": round(mean(ledger), 4) if n else None,
        "spans_mean": round(mean(spans), 4) if n else None,
        "redundancy_rate": round(redundant / n, 4) if n else None,
        "self_reported_groups_mean": round(mean(reported), 4) if reported else None,
        "n_with_self_report": len(reported),
        "support_fact_ids_not_in_ledger": unresolved,
    }


def stage_score(_: argparse.Namespace) -> int:
    cohort = load_cohort()
    ce = ClinicalEndpoint()
    ck = ce.bridge.canonical_key
    vig_cache: dict[str, dict[str, str]] = {}

    frozen_pairs: list[tuple[Sequence[Mapping[str, Any]], Mapping[str, str]]] = []
    group_maps: dict[str, dict[str, str]] = {}
    frozen_sets: dict[str, set[str]] = {}
    targets: dict[str, list[str]] = {}
    for row in cohort:
        cid = row["case_id"]
        _doc, stages, _v = case_context(row, vig_cache)
        group_maps[cid] = {
            f["fact_id"]: f.get("correlation_group") for f in (stages.get("facts") or [])
        }
        concepts = commit_concepts(stages)
        frozen_pairs.append((concepts, group_maps[cid]))
        frozen_sets[cid] = {ck(str(c.get("preferred_label") or "")) for c in concepts}
        targets[cid] = list(row["retention_targets"])

    out: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "created_at": utcnow(),
        "n_dev_cases": len(cohort),
        "baseline": {
            "ledger_groups_mean": BASELINE_LEDGER_GROUPS,
            "spans_mean": BASELINE_SPANS,
            "redundancy_rate": BASELINE_REDUNDANCY,
            "recomputed_on_gate_cases_only": evidence_stats(frozen_pairs),
        },
        "arms": {},
    }

    for arm in ("arm_A", "arm_B"):
        path = OUT / "runs" / arm / "responses.json"
        if not path.is_file():
            out["arms"][arm] = {"status": "not_run"}
            continue
        doc = json.loads(path.read_text())
        served, retained, retained_strict, changed = 0, 0, 0, 0
        pairs: list[tuple[Sequence[Mapping[str, Any]], Mapping[str, str]]] = []
        lost: list[str] = []
        for res in doc["results"]:
            cid = res["case_id"]
            if not res.get("ok"):
                continue
            served += 1
            concepts = (res.get("response") or {}).get("concepts") or []
            pairs.append((concepts, group_maps[cid]))
            strict = {ck(str(c.get("preferred_label") or "")) for c in concepts}
            wide = set(strict)
            for c in concepts:
                for a in (c.get("aliases") or []):
                    wide.add(ck(str(a)))
            tgt = {ck(t) for t in targets[cid]}
            if tgt & wide:
                retained += 1
            else:
                lost.append(cid)
            if tgt & strict:
                retained_strict += 1
            if strict != frozen_sets[cid]:
                changed += 1
        ev = evidence_stats(pairs)
        paired = out["baseline"]["recomputed_on_gate_cases_only"]["ledger_groups_mean"]
        inflation = (
            round(ev["self_reported_groups_mean"] - ev["ledger_groups_mean"], 4)
            if ev["self_reported_groups_mean"] is not None and ev["ledger_groups_mean"]
            else None
        )
        retention_rate = round(retained / served, 4) if served else 0.0
        change_rate = round(changed / served, 4) if served else 0.0
        ledger_rose = bool(
            ev["ledger_groups_mean"] is not None
            and ev["ledger_groups_mean"] > BASELINE_LEDGER_GROUPS
        )
        if retained < GATE_MIN_RETAINED:
            exit_row = "close_this_arm"
        elif change_rate < GATE_MIN_CHANGE_RATE or not ledger_rose:
            exit_row = "prompt_did_not_bite_one_rewrite_allowed"
        else:
            exit_row = "pass_to_M1"
        out["arms"][arm] = {
            "status": "run",
            "n_served": served,
            "retained": retained,
            "retained_min_required": GATE_MIN_RETAINED,
            "retention_rate": retention_rate,
            "retained_preferred_label_only": retained_strict,
            "lost_case_ids": sorted(lost),
            "change_rate": change_rate,
            "evidence": ev,
            # The frozen §4.3 criterion, kept verbatim on the record.
            "ledger_groups_rose_above_baseline": ledger_rose,
            # The same question on the paired denominator. §4.3's anchor was
            # computed over dev-wide commit candidates (n=992) while the arms are
            # only ever scored on the 67 gate cases (frozen n=331), so the frozen
            # criterion compares across denominators. Reported alongside rather
            # than substituted: retention closes both arms regardless, so this
            # cannot be a post-hoc threshold move.
            "ledger_groups_rose_vs_paired_gate_baseline": bool(
                ev["ledger_groups_mean"] is not None and paired is not None
                and ev["ledger_groups_mean"] > paired
            ),
            "paired_gate_baseline_ledger_groups": paired,
            "delta_vs_paired_gate_baseline": (
                round(ev["ledger_groups_mean"] - paired, 4)
                if ev["ledger_groups_mean"] is not None and paired is not None else None
            ),
            "self_report_inflation": inflation,
            "exit": exit_row,
            "exit_determined_by": "retention" if retained < GATE_MIN_RETAINED else "mechanism",
        }

    write_json(OUT / "gate.json", out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=EXPERIMENT_ID)
    sub = ap.add_subparsers(dest="stage", required=True)
    sub.add_parser("verify").set_defaults(fn=stage_verify)
    r = sub.add_parser("run")
    r.add_argument("--arm", required=True, choices=("arm_A", "arm_B"))
    r.add_argument("--limit", type=int, default=0)
    r.set_defaults(fn=stage_run)
    sub.add_parser("score").set_defaults(fn=stage_score)
    args = ap.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
