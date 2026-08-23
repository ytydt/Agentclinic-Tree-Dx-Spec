#!/usr/bin/env python3
"""MCR_EVIDENCE_SYMMETRY_GATE_V1: is the evidence skew an artefact of how it was written?

Design and pass/fail thresholds are fixed in
`results/MCR_EVIDENCE_SYMMETRY_GATE/PREREGISTRATION.md` and must not be edited here.

In the 63 selection-layer losses the correct candidate arrives at the comparator with
weaker evidence than the champion it lost to (fewer `for` spans in 48/63, an `against`
entry in 42/63).  The frozen pipeline writes that evidence inside the *same* stance call
that proposes the differential, where candidates compete for slots and are forbidden
from sharing support spans.  This gate re-derives the evidence for one candidate per
call, blind to its rival, and asks whether the paired asymmetry survives.

It deliberately does NOT re-run the selector: no new champion, no new clinical relation,
no endpoint claim.  126 online calls, zero panel adjudication.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "src", ROOT / "scripts" / "paper", ROOT / "analysis" / "backbone_v1",
          ROOT / "analysis" / "mechanism_v2"):
    sys.path.insert(0, str(p))

import baseline_common as bc  # noqa: E402
import mcr_selector_truncation as trunc  # noqa: E402
from agentclinic_tree_dx.aphhm_c import AphhmCPipeline, _norm  # noqa: E402
from analysis.mechanism_v2 import mcr_selection_layer_audit as audit  # noqa: E402
from analysis.mechanism_v2.clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402

PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts" / "aphhm_c_symmetric_candidate_evidence.txt"
)
PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
MODULE = "AphhmCSymmetricCandidateEvidence"
OUT = ROOT / "analysis" / "mechanism_v2" / "results" / "MCR_EVIDENCE_SYMMETRY_GATE"

# Frozen reference values, from MCR_SELECTION_LAYER_AUDIT (audit.json q2_evidence_skew).
FROZEN = {
    "n": 63,
    "correct_has_fewer_for": 48,
    "mean_for_gap": 1.56,
    "correct_against_champion_clean": 21,
}
# Preregistered thresholds.  Do not tune.
GATE = {
    "g_a_fewer_for_max": 38,
    "g_a_mean_gap_max": 0.60,
    "g_b_asym_against_max": 12,
    "g_c_verbatim_min": 0.90,
}


def verbatim(raw: Any, vignette: str) -> list[str]:
    """The runtime's own span filter, so counts are comparable with the frozen payload."""
    return AphhmCPipeline._verbatim(raw, _norm(vignette))


def build_pairs() -> list[dict]:
    """One record per selection-layer loss: the correct candidate and the champion."""
    ce = ClinicalEndpoint()
    cases, _ = audit.load_cohort(ce)
    vignettes: dict[tuple[str, str], str] = {}
    for log_ds, ds_name, sl in trunc.MCR_SLICES:
        for case in trunc.load_cases(log_ds, ds_name):
            cid = str(case.get("source_id") or case.get("case_id") or "")
            vignettes[(sl, cid)] = str(case.get("vignette") or "")

    pairs: list[dict] = []
    for c in cases:
        if c.champion_relation == COMPLETE or c.champion not in c.labels:
            continue
        ci, wi = c.complete_index, c.labels.index(c.champion)
        vig = vignettes.get((c.slice, c.case_id), "")
        if not vig:
            continue
        pairs.append({
            "slice": c.slice,
            "case_id": c.case_id,
            "is_dev": c.is_dev,
            "gold": c.gold,
            "vignette": vig,
            "correct": {
                "label": c.labels[ci],
                "position": ci,
                "frozen_for": len(c.seq[ci].get("support_spans") or []),
                "frozen_against": len(c.seq[ci].get("contradict_spans") or []),
            },
            "champion": {
                "label": c.labels[wi],
                "position": wi,
                "frozen_for": len(c.seq[wi].get("support_spans") or []),
                "frozen_against": len(c.seq[wi].get("contradict_spans") or []),
            },
        })
    return pairs


def run(pairs: list[dict], *, model: str, workers: int, out: Path, dry_run: bool) -> list[dict]:
    client = None
    if not dry_run:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        client = RobustLLMClient(
            model=model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
        )
    cached = bc.SimpleCachedLLM(client, out / "cache" / "symmetric_evidence.json", model)

    jobs = [(rec, side) for rec in pairs for side in ("correct", "champion")]

    def one(job: tuple[dict, str]) -> dict:
        rec, side = job
        label = rec[side]["label"]
        raw = cached.call(MODULE, PROMPT, {"vignette": rec["vignette"], "candidate": label})
        f_raw = list(raw.get("support_spans") or [])
        a_raw = list(raw.get("contradict_spans") or [])
        f_ok = verbatim(f_raw, rec["vignette"])
        a_ok = verbatim(a_raw, rec["vignette"])
        return {
            "slice": rec["slice"],
            "case_id": rec["case_id"],
            "is_dev": rec["is_dev"],
            "side": side,
            "label": label,
            "position": rec[side]["position"],
            "frozen_for": rec[side]["frozen_for"],
            "frozen_against": rec[side]["frozen_against"],
            "n_returned": len(f_raw) + len(a_raw),
            "n_verbatim": len(f_ok) + len(a_ok),
            "for": f_ok,
            "against": a_ok,
            "n_for": len(f_ok),
            "n_against": len(a_ok),
            "why": str(raw.get("why") or ""),
        }

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rows.append(fut.result())
            if i % 20 == 0 or i == len(jobs):
                print(f"  [{i}/{len(jobs)}] symmetric evidence", flush=True)

    rows.sort(key=lambda r: (r["slice"], int(r["case_id"]) if r["case_id"].isdigit() else 0,
                             r["side"]))
    out.mkdir(parents=True, exist_ok=True)
    (out / "spans.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return rows


def score(rows: list[dict]) -> dict:
    by_case: dict[tuple[str, str], dict[str, dict]] = {}
    for r in rows:
        by_case.setdefault((r["slice"], r["case_id"]), {})[r["side"]] = r
    paired = [v for v in by_case.values() if "correct" in v and "champion" in v]
    n = len(paired)
    if not n:
        return {"n": 0}

    def side_stat(key: str, field: str) -> float:
        return sum(v[key][field] for v in paired) / n

    fewer = sum(1 for v in paired if v["correct"]["n_for"] < v["champion"]["n_for"])
    equal = sum(1 for v in paired if v["correct"]["n_for"] == v["champion"]["n_for"])
    asym_against = sum(
        1 for v in paired if v["correct"]["n_against"] > 0 and v["champion"]["n_against"] == 0
    )
    gap = side_stat("champion", "n_for") - side_stat("correct", "n_for")
    returned = sum(v[s]["n_returned"] for v in paired for s in ("correct", "champion"))
    kept = sum(v[s]["n_verbatim"] for v in paired for s in ("correct", "champion"))
    fidelity = kept / returned if returned else 0.0

    g_a = fewer <= GATE["g_a_fewer_for_max"] and gap <= GATE["g_a_mean_gap_max"]
    g_b = asym_against <= GATE["g_b_asym_against_max"]
    g_c = fidelity >= GATE["g_c_verbatim_min"]
    verdict = "VOID" if not g_c else ("PASS" if (g_a or g_b) else "FAIL")

    res = {
        "n": n,
        "dev": sum(1 for v in paired if v["correct"]["is_dev"]),
        "holdout": sum(1 for v in paired if not v["correct"]["is_dev"]),
        "resampled": {
            "mean_for_correct": side_stat("correct", "n_for"),
            "mean_for_champion": side_stat("champion", "n_for"),
            "mean_for_gap": gap,
            "correct_has_fewer_for": fewer,
            "correct_has_equal_for": equal,
            "correct_has_more_for": n - fewer - equal,
            "mean_against_correct": side_stat("correct", "n_against"),
            "mean_against_champion": side_stat("champion", "n_against"),
            "correct_has_against": sum(1 for v in paired if v["correct"]["n_against"] > 0),
            "champion_has_against": sum(1 for v in paired if v["champion"]["n_against"] > 0),
            "correct_against_champion_clean": asym_against,
        },
        "frozen": {
            "mean_for_correct": side_stat("correct", "frozen_for"),
            "mean_for_champion": side_stat("champion", "frozen_for"),
            "correct_has_fewer_for": sum(
                1 for v in paired if v["correct"]["frozen_for"] < v["champion"]["frozen_for"]
            ),
            "correct_against_champion_clean": sum(
                1 for v in paired
                if v["correct"]["frozen_against"] > 0 and v["champion"]["frozen_against"] == 0
            ),
        },
        "fidelity": {"n_returned": returned, "n_verbatim": kept, "rate": fidelity},
        "gates": {
            "G_A_support_asymmetry": g_a,
            "G_B_against_asymmetry": g_b,
            "G_C_verbatim_fidelity": g_c,
            "thresholds": GATE,
        },
        "verdict": verdict,
    }
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-only", action="store_true", help="build the cohort, zero calls")
    ap.add_argument("--score-only", action="store_true", help="score an existing spans.jsonl")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--dry-run", action="store_true", help="cache only, never call out")
    args = ap.parse_args()

    pairs = build_pairs()
    print(f"cohort: {len(pairs)} losses "
          f"(dev {sum(1 for p in pairs if p['is_dev'])} / "
          f"holdout {sum(1 for p in pairs if not p['is_dev'])}), "
          f"{2 * len(pairs)} calls")
    if args.pairs_only:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "pairs.jsonl").write_text(
            "\n".join(json.dumps({k: v for k, v in p.items() if k != "vignette"},
                                 ensure_ascii=False) for p in pairs) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.out / 'pairs.jsonl'}")
        return 0

    if args.score_only:
        text = (args.out / "spans.jsonl").read_text(encoding="utf-8")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = run(pairs, model=args.model, workers=args.workers, out=args.out,
                   dry_run=args.dry_run)

    res = score(rows)
    (args.out / "gate.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    r, f = res["resampled"], res["frozen"]
    print(f"\npaired cases n={res['n']} (dev {res['dev']} / holdout {res['holdout']})")
    print(f"{'':<34}{'frozen':>10}{'symmetric':>12}")
    print(f"{'mean `for` — correct':<34}{f['mean_for_correct']:>10.2f}{r['mean_for_correct']:>12.2f}")
    print(f"{'mean `for` — champion':<34}{f['mean_for_champion']:>10.2f}"
          f"{r['mean_for_champion']:>12.2f}")
    print(f"{'mean gap (champion − correct)':<34}"
          f"{f['mean_for_champion'] - f['mean_for_correct']:>10.2f}{r['mean_for_gap']:>12.2f}")
    print(f"{'correct has fewer `for`':<34}{f['correct_has_fewer_for']:>10}"
          f"{r['correct_has_fewer_for']:>12}")
    print(f"{'correct has against, champion not':<34}"
          f"{f['correct_against_champion_clean']:>10}{r['correct_against_champion_clean']:>12}")
    print(f"\nverbatim fidelity {res['fidelity']['rate']:.3f} "
          f"({res['fidelity']['n_verbatim']}/{res['fidelity']['n_returned']} spans kept)")
    g = res["gates"]
    print(f"\nG-A support asymmetry  {'PASS' if g['G_A_support_asymmetry'] else 'fail'}"
          f"   (need fewer_for ≤ {GATE['g_a_fewer_for_max']} and gap ≤ "
          f"{GATE['g_a_mean_gap_max']})")
    print(f"G-B against asymmetry  {'PASS' if g['G_B_against_asymmetry'] else 'fail'}"
          f"   (need ≤ {GATE['g_b_asym_against_max']})")
    print(f"G-C verbatim fidelity  {'PASS' if g['G_C_verbatim_fidelity'] else 'fail'}"
          f"   (need ≥ {GATE['g_c_verbatim_min']})")
    print(f"\nVERDICT: {res['verdict']}")
    print(f"wrote {args.out / 'gate.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
