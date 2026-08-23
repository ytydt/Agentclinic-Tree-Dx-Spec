#!/usr/bin/env python3
"""MCR_EVIDENCE_REASSIGNMENT_V1: de-bias the per-candidate evidence, then re-select.

Design, arms, budget, gates and predictions are fixed in
`results/MCR_EVIDENCE_REASSIGNMENT/PREREGISTRATION.md`.  Nothing here may be tuned
against observed results.

The frozen pipeline writes each candidate's `support_spans` / `contradict_spans` inside
the same stance call that proposes the differential, where candidates compete for slots.
`MCR_EVIDENCE_SYMMETRY_GATE_V1` showed that this inflates whichever candidate the call
emits first (champion `for` spans 3.84 -> 2.81 under blind per-candidate re-derivation,
concentrated on payload position 0: -1.25 there vs -0.53 elsewhere).  This experiment
substitutes the de-biased evidence and asks whether the comparator changes its mind.

Because the inflation is entangled with payload position, and because the comparator
follows position 0 on 77.8% of cases, the arms form a 2x2 over
{frozen, symmetric} evidence x {generation order, seeded shuffle}:

    frozen        frozen evidence,    generation order   (baseline, zero calls via G1)
    sym_evidence  symmetric evidence, generation order   (the only deployable arm)
    shuffle_only  frozen evidence,    shuffled           (position control)
    sym_shuffle   symmetric evidence, shuffled           (evidence effect, no position)

Evidence calls are keyed on {vignette, candidate} alone, so the two symmetric arms share
one set of them.  Champions are always copied from the registry shortlist, whose 3500
labels are 100% covered by the frozen clinical panel, so scoring costs zero adjudication.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import comb
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "scripts" / "paper", ROOT / "analysis" / "backbone_v1",
           ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import baseline_common as bc  # noqa: E402
import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402
import mcr_selector_truncation as trunc  # noqa: E402
import mcr_evidence_symmetry_gate as gate  # noqa: E402
from analysis.mechanism_v2 import mcr_selection_layer_audit as audit  # noqa: E402
from analysis.mechanism_v2.clinical_endpoint import (  # noqa: E402
    COMPLETE,
    ClinicalEndpoint,
    TaskEndpoint,
)

OUT = ROOT / "analysis" / "mechanism_v2" / "results" / "MCR_EVIDENCE_REASSIGNMENT"
RUNS = OUT / "runs"
GATE_CACHE = (
    ROOT / "analysis" / "mechanism_v2" / "results" / "MCR_EVIDENCE_SYMMETRY_GATE"
    / "cache" / "symmetric_evidence.json"
)
DEV = ("mcr_v1", "mcr_v2")
N_FULL_SLICE = 400

# evidence source, payload order
ARMS: dict[str, dict[str, str]] = {
    "frozen": {"evidence": "frozen", "order": "gen"},
    "sym_evidence": {"evidence": "symmetric", "order": "gen"},
    "shuffle_only": {"evidence": "frozen", "order": "shuffle"},
    "sym_shuffle": {"evidence": "symmetric", "order": "shuffle"},
}
ONLINE_ARMS = ("sym_evidence", "shuffle_only", "sym_shuffle")


# --- cohort -----------------------------------------------------------------
def load_cohort(stage: str = "all") -> list[dict]:
    """The 167 pool-reachable MCR cases, with payload order and vignette attached."""
    ce = ClinicalEndpoint()
    cases, _ = audit.load_cohort(ce)
    vignettes: dict[tuple[str, str], str] = {}
    log_of: dict[str, str] = {}
    for log_ds, ds_name, sl in trunc.MCR_SLICES:
        log_of[sl] = log_ds
        for case in trunc.load_cases(log_ds, ds_name):
            cid = str(case.get("source_id") or case.get("case_id") or "")
            vignettes[(sl, cid)] = str(case.get("vignette") or "")

    out: list[dict] = []
    for c in cases:
        vig = vignettes.get((c.slice, c.case_id), "")
        if not vig:
            continue
        is_dev = c.slice in DEV
        if stage == "dev" and not is_dev:
            continue
        if stage == "holdout" and is_dev:
            continue
        out.append({
            "slice": c.slice,
            "case_id": c.case_id,
            "log_ds": log_of[c.slice],
            "is_dev": is_dev,
            "gold": c.gold,
            "vignette": vig,
            "candidates": c.seq,
        })
    out.sort(key=lambda r: (r["slice"], int(r["case_id"]) if r["case_id"].isdigit() else 0))
    return out


# --- payload ----------------------------------------------------------------
def shuffled_order(rec: Mapping[str, Any]) -> list[int]:
    """Deterministic per-case permutation, recorded in the output for replay."""
    seed = int(bc.stable_hash({"slice": rec["slice"], "case_id": rec["case_id"]})[:8], 16)
    idx = list(range(len(rec["candidates"])))
    random.Random(seed).shuffle(idx)
    return idx


def build_payload(
    rec: Mapping[str, Any],
    *,
    evidence: str,
    order: str,
    spans: Optional[Mapping[tuple[str, str, str], dict]] = None,
) -> tuple[dict, list[int]]:
    """Rebuild the selector payload.  `evidence='frozen'`, `order='gen'` reproduces the
    frozen payload byte for byte (asserted by G1)."""
    idx = list(range(len(rec["candidates"]))) if order == "gen" else shuffled_order(rec)
    cands = [rec["candidates"][i] for i in idx]

    def note(c: Mapping[str, Any]) -> dict:
        label = str(c.get("preferred_label") or "")
        if evidence == "frozen":
            f, a = list(c.get("support_spans") or []), list(c.get("contradict_spans") or [])
        else:
            got = (spans or {}).get((rec["slice"], rec["case_id"], label)) or {}
            f, a = list(got.get("for") or []), list(got.get("against") or [])
        return {"label": label, "for": f[:4], "against": a[:3]}

    groups: dict[str, list[dict]] = {}
    for c in cands:
        stances = [str(s) for s in (c.get("stances") or []) if str(s)]
        entry = dict(note(c))
        if len(stances) > 1:
            entry["also_found_by"] = stances[1:]
        groups.setdefault(stances[0] if stances else "unassigned", []).append(entry)
    payload = {
        "vignette": str(rec["vignette"]),
        "shortlist": [str(c.get("preferred_label") or "") for c in cands],
        "groups": [{"group": g, "candidates": v} for g, v in groups.items()],
    }
    return payload, idx


# --- G1: the frozen cell must be an identity, and cost nothing --------------
def verify_g1(cohort: Sequence[Mapping[str, Any]]) -> dict:
    """Frozen evidence + generation order reproduces the frozen selector response."""
    res = {"n": 0, "payload_matches_truncation_builder": 0, "cache_hit": 0,
           "output_identical": 0, "mismatch": []}
    caches = {sl: trunc.frozen_cache(log) for log, _, sl in trunc.MCR_SLICES}
    for rec in cohort:
        doc = trunc.load_doc(rec["log_ds"], rec["case_id"])
        stages = doc.get("stages") or {}
        if not stages.get("frontier_selector"):
            continue
        res["n"] += 1
        mine, _ = build_payload(rec, evidence="frozen", order="gen")
        theirs = trunc.build_payload(stages, rec["vignette"])
        if mine == theirs:
            res["payload_matches_truncation_builder"] += 1
        else:
            res["mismatch"].append({"slice": rec["slice"], "case": rec["case_id"],
                                    "why": "builder_differs"})
            continue
        key = trunc.payload_key(mine)
        cache = caches[rec["slice"]]
        if key not in cache:
            res["mismatch"].append({"slice": rec["slice"], "case": rec["case_id"],
                                    "why": "cache_miss"})
            continue
        res["cache_hit"] += 1
        if cache[key] == stages["frontier_selector"]:
            res["output_identical"] += 1
        else:
            res["mismatch"].append({"slice": rec["slice"], "case": rec["case_id"],
                                    "why": "output_differs"})
    res["pass"] = res["n"] > 0 and res["output_identical"] == res["n"]
    return res


# --- symmetric evidence -----------------------------------------------------
def seed_cache(path: Path) -> int:
    """Reuse the gate's 126 evidence calls: identical module, prompt and payload keys."""
    if path.is_file() or not GATE_CACHE.is_file():
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    seeded = json.loads(GATE_CACHE.read_text(encoding="utf-8"))
    path.write_text(json.dumps(seeded, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(seeded)


def derive_spans(
    cohort: Sequence[Mapping[str, Any]], *, model: str, workers: int, dry_run: bool
) -> dict[tuple[str, str, str], dict]:
    """One blind call per (case, candidate).  Order-independent, so both symmetric arms
    share these."""
    cache_path = RUNS / "cache" / "symmetric_evidence.json"
    n_seeded = seed_cache(cache_path)
    if n_seeded:
        print(f"  seeded evidence cache with {n_seeded} entries from the symmetry gate")

    client = None
    if not dry_run:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        client = RobustLLMClient(
            model=model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
        )
    cached = bc.SimpleCachedLLM(client, cache_path, model)

    jobs: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for rec in cohort:
        for c in rec["candidates"]:
            label = str(c.get("preferred_label") or "")
            k = (rec["slice"], rec["case_id"], label)
            if label and k not in seen:
                seen.add(k)
                jobs.append((rec["slice"], rec["case_id"], label, rec["vignette"]))

    def one(job: tuple[str, str, str, str]) -> tuple[tuple[str, str, str], dict]:
        sl, cid, label, vig = job
        raw = cached.call(gate.MODULE, gate.PROMPT, {"vignette": vig, "candidate": label})
        return (sl, cid, label), {
            "for": gate.verbatim(raw.get("support_spans"), vig),
            "against": gate.verbatim(raw.get("contradict_spans"), vig),
            "n_returned": len(list(raw.get("support_spans") or []))
            + len(list(raw.get("contradict_spans") or [])),
            "why": str(raw.get("why") or ""),
        }

    spans: dict[tuple[str, str, str], dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            k, v = fut.result()
            spans[k] = v
            if i % 50 == 0 or i == len(jobs):
                print(f"  [{i}/{len(jobs)}] symmetric evidence", flush=True)

    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "spans.jsonl").write_text(
        "\n".join(
            json.dumps({"slice": k[0], "case_id": k[1], "label": k[2], **v}, ensure_ascii=False)
            for k, v in sorted(spans.items())
        ) + "\n",
        encoding="utf-8",
    )
    return spans


# --- arm execution ----------------------------------------------------------
def run_arm(
    arm: str,
    cohort: Sequence[Mapping[str, Any]],
    spans: Optional[Mapping[tuple[str, str, str], dict]],
    *,
    model: str,
    workers: int,
    dry_run: bool,
) -> dict:
    spec = ARMS[arm]
    out_dir = RUNS / arm
    out_dir.mkdir(parents=True, exist_ok=True)

    client = None
    if not dry_run:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        client = RobustLLMClient(
            model=model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
        )
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "selector.json", model)
    frozen_caches = {sl: trunc.frozen_cache(log) for log, _, sl in trunc.MCR_SLICES}

    def one(rec: Mapping[str, Any]) -> dict:
        payload, idx = build_payload(
            rec, evidence=spec["evidence"], order=spec["order"], spans=spans
        )
        shortlist = list(payload["shortlist"])
        key = trunc.payload_key(payload)
        fc = frozen_caches[rec["slice"]]
        source = "frozen_cache" if key in fc else "online"
        raw = dict(fc[key]) if key in fc else cached.call(trunc.MODULE, trunc.PROMPT, payload)
        champ = trunc.champion_of(raw, shortlist)
        entries = [e for g in payload["groups"] for e in g["candidates"]]
        return {
            "slice": rec["slice"],
            "case_id": rec["case_id"],
            "arm": arm,
            "champion": champ,
            "shortlist": shortlist,
            "n_candidates": len(shortlist),
            "n_groups": len(payload["groups"]),
            "champion_in_slate": champ in shortlist,
            "champion_position": shortlist.index(champ) if champ in shortlist else -1,
            "order": idx,
            "mean_for": round(
                sum(len(e.get("for") or []) for e in entries) / max(len(entries), 1), 4),
            "mean_against": round(
                sum(len(e.get("against") or []) for e in entries) / max(len(entries), 1), 4),
            "raw": raw,
            "source": source,
        }

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, r) for r in cohort]
        for i, fut in enumerate(as_completed(futs), 1):
            rows.append(fut.result())
            if i % 25 == 0 or i == len(cohort):
                print(f"  [{i}/{len(cohort)}] {arm}", flush=True)

    rows.sort(key=lambda r: (r["slice"], int(r["case_id"]) if r["case_id"].isdigit() else 0))
    existing = {}
    p = out_dir / "predictions.jsonl"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                existing[(r["slice"], r["case_id"])] = r
    for r in rows:
        existing[(r["slice"], r["case_id"])] = r
    merged = sorted(existing.values(),
                    key=lambda r: (r["slice"], int(r["case_id"]) if r["case_id"].isdigit() else 0))
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in merged) + "\n",
                 encoding="utf-8")
    return {
        "arm": arm,
        "n_this_stage": len(rows),
        "n_total": len(merged),
        "online_calls": sum(1 for r in rows if r["source"] == "online"),
        "frozen_cache_hits": sum(1 for r in rows if r["source"] == "frozen_cache"),
        "champion_in_slate": sum(1 for r in rows if r["champion_in_slate"]),
        "mean_for": round(sum(r["mean_for"] for r in rows) / max(len(rows), 1), 4),
    }


# --- scoring ----------------------------------------------------------------
def mcnemar(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    b = sum(1 for a, c in pairs if a and not c)
    c_ = sum(1 for a, c in pairs if c and not a)
    n = b + c_
    if n == 0:
        return {"base_only": 0, "test_only": 0, "n_discordant": 0, "p_two_sided": 1.0}
    k = min(b, c_)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
    return {"base_only": b, "test_only": c_, "n_discordant": n,
            "p_two_sided": round(min(1.0, 2 * tail), 5)}


def holm(named: list[tuple[str, float]]) -> dict[str, float]:
    order = sorted(named, key=lambda x: x[1])
    m = len(order)
    out: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(order):
        running = max(running, min(1.0, (m - i) * p))
        out[name] = round(running, 5)
    return out


def frozen_rows(cohort: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for rec in cohort:
        doc = trunc.load_doc(rec["log_ds"], rec["case_id"])
        payload, _ = build_payload(rec, evidence="frozen", order="gen")
        shortlist = list(payload["shortlist"])
        champ = str(doc.get("champion") or "")
        out[(rec["slice"], rec["case_id"])] = {
            "slice": rec["slice"], "case_id": rec["case_id"], "arm": "frozen",
            "champion": champ, "shortlist": shortlist, "n_candidates": len(shortlist),
            "champion_in_slate": champ in shortlist,
            "champion_position": shortlist.index(champ) if champ in shortlist else -1,
            "mean_for": round(sum(len(e.get("for") or []) for g in payload["groups"]
                                  for e in g["candidates"]) / max(len(shortlist), 1), 4),
            "source": "frozen_log",
        }
    return out


def score(cohort: Sequence[Mapping[str, Any]], ce: ClinicalEndpoint, te: TaskEndpoint) -> dict:
    rows: dict[str, dict[tuple[str, str], dict]] = {"frozen": frozen_rows(cohort)}
    for arm in ONLINE_ARMS:
        p = RUNS / arm / "predictions.jsonl"
        if not p.is_file():
            continue
        rows[arm] = {
            (r["slice"], r["case_id"]): r
            for r in (json.loads(x) for x in p.read_text().splitlines() if x.strip())
        }
    present = [a for a in ("frozen",) + ONLINE_ARMS if a in rows]
    keys = sorted(set.intersection(*[set(rows[a]) for a in present]),
                  key=lambda k: (k[0], int(k[1]) if k[1].isdigit() else 0))
    gold = r5.load_gold()

    comp: dict[str, dict] = {a: {} for a in present}
    cop: dict[str, dict] = {a: {} for a in present}
    legacy: dict[str, dict] = {a: {} for a in present}
    task: dict[str, dict] = {a: {} for a in present}
    per: dict[str, Any] = {}

    for arm in present:
        rel_counts: Counter = Counter()
        for k in keys:
            sl, cid = k
            champ = rows[arm][k]["champion"]
            rel = ce.relation("mcr", sl, cid, champ)
            rel_counts[str(rel)] += 1
            comp[arm][k] = rel == COMPLETE
            cop[arm][k] = ce.is_complete_or_partial("mcr", sl, cid, champ)
            g = gold.get(("mcr", sl, cid), "")
            legacy[arm][k] = bool(dc.match(champ, g)) if g else False
            task[arm][k] = te.correct("mcr", sl, cid, champ)
        n = len(keys)
        c = sum(1 for k in keys if comp[arm][k])
        per[arm] = {
            "n": n,
            "clinical_complete": c,
            "conditional_conversion": round(c / max(n, 1), 4),
            "implied_full_slice_rate": round(c / N_FULL_SLICE, 4),
            "complete_or_partial": sum(1 for k in keys if cop[arm][k]),
            "legacy_dc_match": sum(1 for k in keys if legacy[arm][k]),
            "task_judged": sum(1 for k in keys if task[arm][k] is not None),
            "task_correct": sum(1 for k in keys if task[arm][k] is True),
            "mean_for_in_payload": round(
                sum(rows[arm][k]["mean_for"] for k in keys) / max(n, 1), 3),
            "unjudged_champions": sum(
                1 for k in keys if ce.relation("mcr", k[0], k[1], rows[arm][k]["champion"]) is None),
            "champion_in_slate": sum(1 for k in keys if rows[arm][k]["champion_in_slate"]),
            "agreement_with_frozen": round(
                sum(1 for k in keys
                    if rows[arm][k]["champion"] == rows["frozen"][k]["champion"]) / max(n, 1), 4),
            "picked_payload_position0": sum(
                1 for k in keys if rows[arm][k]["champion_position"] == 0),
            "champion_relations": dict(rel_counts.most_common()),
        }
        for name in ("dev", "holdout"):
            sub = [k for k in keys if (k[0] in DEV) == (name == "dev")]
            per[arm][f"{name}_complete"] = f"{sum(1 for k in sub if comp[arm][k])}/{len(sub)}"

    def pair(base: str, test: str, table: dict) -> dict:
        ks = [k for k in keys if table[base][k] is not None and table[test][k] is not None]
        res = mcnemar([(bool(table[base][k]), bool(table[test][k])) for k in ks])
        res["n_paired"] = len(ks)
        res["delta_cases"] = res["test_only"] - res["base_only"]
        res["delta_pp_full_slice"] = round(100 * res["delta_cases"] / N_FULL_SLICE, 2)
        return res

    wanted = [("sym_evidence", "frozen"), ("shuffle_only", "frozen"),
              ("sym_shuffle", "frozen"), ("sym_shuffle", "shuffle_only")]
    contrasts = {f"{t}_minus_{b}": pair(b, t, comp)
                 for t, b in wanted if t in present and b in present}
    family = [(f"{t}_minus_{b}", contrasts[f"{t}_minus_{b}"]["p_two_sided"])
              for t, b in wanted[:3] if f"{t}_minus_{b}" in contrasts]
    guard = {f"{t}_minus_{b}": pair(b, t, cop)
             for t, b in wanted if t in present and b in present}
    secondary = {
        ep: {f"{t}_minus_{b}": pair(b, t, tbl)
             for t, b in wanted if t in present and b in present}
        for ep, tbl in (("legacy_dc_match", legacy), ("task", task))
    }

    interaction = None
    if {"sym_evidence", "sym_shuffle", "shuffle_only"} <= set(present):
        interaction = {
            "sym_evidence_minus_frozen": contrasts["sym_evidence_minus_frozen"]["delta_cases"],
            "sym_shuffle_minus_shuffle_only":
                contrasts["sym_shuffle_minus_shuffle_only"]["delta_cases"],
        }
        interaction["evidence_x_position"] = (
            interaction["sym_shuffle_minus_shuffle_only"]
            - interaction["sym_evidence_minus_frozen"]
        )

    futility = None
    if "sym_evidence" in present:
        d = contrasts["sym_evidence_minus_frozen"]["delta_cases"]
        changed = 1 - per["sym_evidence"]["agreement_with_frozen"]
        futility = {
            "delta_cases": d,
            "champion_change_rate": round(changed, 4),
            "stop": bool(d <= 0 and changed < 0.15),
            "rule": "stop iff delta <= 0 AND champion change rate < 15%",
        }

    return {
        "cohort": {"n": len(keys), "dev": sum(1 for k in keys if k[0] in DEV),
                   "holdout": sum(1 for k in keys if k[0] not in DEV)},
        "arms_present": present,
        "per_arm": per,
        "primary_endpoint": "clinical_complete_top1",
        "contrasts": contrasts,
        "holm_main_family": holm(family) if family else {},
        "coprimary_guard_complete_or_partial": guard,
        "secondary_contrasts": secondary,
        "interaction": interaction,
        "dev_futility": futility,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--g1", action="store_true", help="fidelity gate, zero calls")
    ap.add_argument("--stage", choices=("dev", "holdout", "all"))
    ap.add_argument("--arm", choices=sorted(ARMS), help="run a single arm of the stage")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.g1:
        cohort = load_cohort("all")
        res = verify_g1(cohort)
        print(json.dumps({k: v for k, v in res.items() if k != "mismatch"}, indent=2))
        if res["mismatch"]:
            print(f"\nmismatches ({len(res['mismatch'])}), first 10:")
            for m in res["mismatch"][:10]:
                print("  ", m)
        print("\nG1:", "PASS" if res["pass"] else "FAIL")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "g1.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
        return 0 if res["pass"] else 1

    if args.stage:
        cohort = load_cohort(args.stage)
        n_cand = sum(len(r["candidates"]) for r in cohort)
        arms = (args.arm,) if args.arm else ONLINE_ARMS
        print(f"stage={args.stage}  cases={len(cohort)}  candidates={n_cand}  arms={list(arms)}")
        spans = None
        if any(ARMS[a]["evidence"] == "symmetric" for a in arms):
            spans = derive_spans(cohort, model=args.model, workers=args.workers,
                                 dry_run=args.dry_run)
        summaries = {}
        for arm in arms:
            summaries[arm] = run_arm(arm, cohort, spans, model=args.model,
                                     workers=args.workers, dry_run=args.dry_run)
            print(json.dumps(summaries[arm], indent=2))
        RUNS.mkdir(parents=True, exist_ok=True)
        (RUNS / f"summary_{args.stage}.json").write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    if args.score:
        cohort = load_cohort("all")
        res = score(cohort, ClinicalEndpoint(), TaskEndpoint())
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "score.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
        c = res["cohort"]
        print(f"cohort n={c['n']} (dev {c['dev']} / holdout {c['holdout']})\n")
        print(f"{'arm':<14}{'complete':>9}{'cond':>8}{'C∪P':>6}{'legacy':>8}{'task':>10}"
              f"{'for/cand':>10}{'pos0':>6}{'agree':>7}")
        for arm in res["arms_present"]:
            a = res["per_arm"][arm]
            print(f"{arm:<14}{a['clinical_complete']:>9}{a['conditional_conversion']:>8.3f}"
                  f"{a['complete_or_partial']:>6}{a['legacy_dc_match']:>8}"
                  f"{str(a['task_correct']) + '/' + str(a['task_judged']):>10}"
                  f"{a['mean_for_in_payload']:>10.2f}{a['picked_payload_position0']:>6}"
                  f"{a['agreement_with_frozen']:>7.3f}")
        print("\nprimary: clinical-complete top-1, paired exact McNemar")
        for name, k in res["contrasts"].items():
            adj = res["holm_main_family"].get(name)
            tag = f"  holm={adj}" if adj is not None else ""
            print(f"  {name:<34} base_only={k['base_only']:>3} test_only={k['test_only']:>3}"
                  f"  Δ={k['delta_cases']:>+4}  p={k['p_two_sided']}{tag}")
        print("\nco-primary guard: complete ∪ partial")
        for name, k in res["coprimary_guard_complete_or_partial"].items():
            print(f"  {name:<34} Δ={k['delta_cases']:>+4}  p={k['p_two_sided']}")
        if res["interaction"]:
            i = res["interaction"]
            print(f"\ninteraction evidence x position = {i['evidence_x_position']:+d}"
                  f"  (sym_shuffle−shuffle_only {i['sym_shuffle_minus_shuffle_only']:+d} "
                  f"vs sym_evidence−frozen {i['sym_evidence_minus_frozen']:+d})")
        if res["dev_futility"]:
            f = res["dev_futility"]
            print(f"\ndev futility: Δ={f['delta_cases']:+d}, "
                  f"champion change {f['champion_change_rate']:.1%} -> "
                  f"{'STOP' if f['stop'] else 'continue'}")
        print(f"\nwrote {OUT / 'score.json'}")
        return 0

    ap.error("pass --g1, --stage, or --score")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
