#!/usr/bin/env python3
"""Audit the DA strict-total-order endpoint before it is allowed into the paper.

Checks, in order of severity:

1. Caliber homogeneity: the block-2 table compares rematch ablations against a
   *live* M00 anchor. Recompute every contrast under a single caliber.
2. Paired significance: exact McNemar / sign test on per-case strict@1, since
   the reported deltas (0.01--0.07) sit near the noise floor at n=100.
3. Information content of the LLM tie-breaker: compare LLM strict@1 against the
   closed-form expectation of *uniform random* tie-breaking on the same
   projections. If the LLM is at chance, the endpoint reduces to a deterministic
   tie-mass discount and the LLM call is not load-bearing. Stratify by payload
   status before reading any deficit -- the 2026-07-29 revision found the raw
   per-arm deficits confounded with check 5.
4. Tie-mass decomposition per arm (how much of legacy option@1 is tie credit).

Outputs runs/paper_v1/da_strict_order_endpoint_audit.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
STRICT = ROOT / "runs/paper_v1/da_strict_order_v1"
OUT = ROOT / "runs/paper_v1/da_strict_order_endpoint_audit.json"

from block2_equivalence_bounds import paired_bounds  # noqa: E402


# --------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------
def _binom_two_sided(b: int, c: int) -> float:
    """Exact two-sided sign test on discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def _paired_ci(b: int, c: int, n: int) -> dict[str, Any]:
    """Exact conditional McNemar CI for the paired risk difference (b-c)/n."""
    bounds = paired_bounds(b, c, max(1, n))
    return {
        "lo": bounds["ci95_low"],
        "hi": bounds["ci95_high"],
        "method": "exact_conditional_mcnemar",
    }


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------
def _norm_cid(raw: Any) -> str:
    """Baselines key cases as ``diagnosisarena__000003``, our arms as ``3``."""
    s = str(raw or "").strip()
    if "__" in s:
        s = s.rsplit("__", 1)[1]
    return str(int(s)) if s.isdigit() else s


def _records(path: Path) -> dict[str, dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("records") or []
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        cid = _norm_cid(r.get("source_id") or r.get("case_id"))
        if cid:
            out[cid] = r
    return out


def _strict_hits(recs: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return {cid: int(bool(r.get("option_top1"))) for cid, r in recs.items()}


def paired(a: Mapping[str, int], b: Mapping[str, int], *, name: str) -> dict[str, Any]:
    keys = sorted(set(a) & set(b))
    bb = sum(1 for k in keys if a[k] and not b[k])
    cc = sum(1 for k in keys if b[k] and not a[k])
    n = len(keys)
    return {
        "contrast": name,
        "n_paired": n,
        "acc_a": round(sum(a[k] for k in keys) / max(1, n), 4),
        "acc_b": round(sum(b[k] for k in keys) / max(1, n), 4),
        "delta": round((bb - cc) / max(1, n), 4),
        "b_a_only": bb,
        "c_b_only": cc,
        "p_two_sided": round(_binom_two_sided(bb, cc), 4),
        "ci95_delta": _paired_ci(bb, cc, max(1, n)),
    }


# --------------------------------------------------------------------------
# tie-breaker information content
# --------------------------------------------------------------------------
def _poisson_binomial_p(hits: int, probs: Sequence[float]) -> float:
    """Two-sided p for ``hits`` successes under independent Bernoulli ``probs``.

    Exact via DP, which the normal approximation cannot be trusted for here: the
    per-case success probabilities ``1/width`` are heterogeneous and several arms
    have fewer than 40 tied cases.
    """
    if not probs:
        return 1.0
    pmf = [1.0]
    for p in probs:
        nxt = [0.0] * (len(pmf) + 1)
        for k, v in enumerate(pmf):
            nxt[k] += v * (1.0 - p)
            nxt[k + 1] += v * p
        pmf = nxt
    obs = pmf[hits] if 0 <= hits < len(pmf) else 0.0
    # Two-sided by the method of small likelihood: sum all outcomes no more
    # probable than the observed one.
    tol = 1e-12
    return min(1.0, sum(v for v in pmf if v <= obs + tol))


def tie_break_information(arm_dir: Path) -> dict[str, Any]:
    """Does the LLM tie-breaker beat the closed-form ``1/width`` expectation?

    Restricted to the sub-population the old ``option@1`` scored as a free hit:
    the pre-strict dense ranks put gold inside a *tied rank-1 set* whose members
    are all matched. There, uniform random tie-breaking scores ``1/width``; the
    LLM scores 1 iff it lifted gold to strict position 1. Any gap between the
    two is the information the tie-breaker adds.

    Read the deficits only through ``by_payload_stratum``. The arms whose case
    payload degenerated (see ``payload_symmetry``) carry most of the negative
    signal, so per-arm deficits are confounded with that defect rather than
    evidence about the tie-breaker itself.
    """
    rec_path = arm_dir / "records.json"
    if not rec_path.is_file():
        return {}
    recs = _records(rec_path)
    n_total = len(recs) or 1
    llm_hits = 0
    n_tied1 = 0
    tied1_llm_hits = 0
    tied1_random_expect = 0.0
    widths: list[int] = []
    for rec in recs.values():
        if rec.get("option_top1"):
            llm_hits += 1
        om = ((rec.get("projection") or {}).get("option_maps")) or {}
        gold = str(rec.get("gold_letter") or "").upper()
        meta = rec.get("strict_total_order") or {}
        tied = (meta.get("tie_ranks") or {}).get("1") or []
        tied = [str(x).upper() for x in tied]
        if gold not in tied or len(tied) < 2:
            continue
        # Require every tie member to be matched, so the matched-before-unmatched
        # reshuffle cannot itself decide the winner.
        if any(
            (om.get(L) or {}).get("matched_gate_partition") != "matched"
            for L in tied
        ):
            continue
        n_tied1 += 1
        widths.append(len(tied))
        tied1_random_expect += 1.0 / len(tied)
        if rec.get("option_top1"):
            tied1_llm_hits += 1
    denom = max(1, n_tied1)
    probs = [1.0 / w for w in widths]
    return {
        "n": len(recs),
        "llm_strict_at1": round(llm_hits / n_total, 4),
        "tie_widths": widths,
        "tied_rank1_subpopulation": {
            "n_cases": n_tied1,
            "mean_tie_width": round(sum(widths) / denom, 3) if widths else None,
            "llm_accuracy": round(tied1_llm_hits / denom, 4),
            "random_tiebreak_accuracy": round(tied1_random_expect / denom, 4),
            "llm_minus_random": round(
                (tied1_llm_hits - tied1_random_expect) / denom, 4
            ),
            "llm_hits": tied1_llm_hits,
            "random_expected_hits": round(tied1_random_expect, 2),
            "p_two_sided_exact": round(
                _poisson_binomial_p(tied1_llm_hits, probs), 4
            ),
        },
        "share_of_strict_at1_from_tied_rank1": round(
            tied1_llm_hits / max(1, llm_hits), 4
        ),
    }


# Arms whose DA cases failed to resolve, so the tie-breaker saw bare option
# letters and an empty vignette. See ``payload_symmetry``.
DEGRADED_PAYLOAD_ARMS = {"B00", "B07", "B02-matched-rerank"}


def _tie_breaker_section(per_arm: dict[str, Any]) -> dict[str, Any]:
    """Stratify the tie-break deficits by payload status and attach the verdict.

    The 2026-07-29 revision downgraded this section's claim from "the tie-breaker
    is worse than random" to "it shows no measurable gain over 1/width". Callers
    must read ``by_payload_stratum``, not the per-arm deltas.
    """
    def agg(names: Sequence[str]) -> dict[str, Any]:
        hits = 0
        probs: list[float] = []
        for name in names:
            sub = per_arm[name]["tied_rank1_subpopulation"]
            hits += sub["llm_hits"]
            probs.extend(1.0 / w for w in per_arm[name]["tie_widths"])
        n = len(probs)
        if not n:
            return {}
        exp = sum(probs)
        return {
            "n_arms": len(names),
            "n_tied_cases": n,
            "llm_hits": hits,
            "random_expected_hits": round(exp, 2),
            "delta": round((hits - exp) / n, 4),
            "p_two_sided_exact": round(_poisson_binomial_p(hits, probs), 4),
        }

    for name, rec in per_arm.items():
        rec["payload_status"] = (
            "degenerate_options_and_empty_vignette"
            if name in DEGRADED_PAYLOAD_ARMS
            else "complete"
        )
    degraded = sorted(n for n in per_arm if n in DEGRADED_PAYLOAD_ARMS)
    complete = sorted(n for n in per_arm if n not in DEGRADED_PAYLOAD_ARMS)
    return {
        "_verdict": {
            "revised": "2026-07-29",
            "current_claim": (
                "no measurable gain over the closed-form 1/width tie-break; the "
                "module is redundant against the section-4 endpoint, not harmful"
            ),
            "retracted_claim": (
                "the tie-breaker performs worse than uniform random on the only "
                "decision it makes"
            ),
            "retraction_grounds": [
                "The three largest negative deltas all come from arms whose option "
                "texts and vignette were degenerate, so the effect is collinear "
                "with that implementation defect rather than evidence about the "
                "tie-breaker.",
                "Only B00 clears p<0.05 on its own, and it is one of those arms. "
                "The payload-complete stratum leaves a marginal deficit that is "
                "uncorrected for 14 comparisons, while the headline arm M00_live "
                "sits at -0.009.",
                "The across-arm sign test treats arms sharing the same 100 cases "
                "and heavily overlapping tie groups as independent observations.",
                "Task difficulty cannot by itself produce below-chance results "
                "because the 1/width null is matched case by case: difficulty "
                "drives a ranker toward uninformative (=chance), not "
                "anti-informative (<chance). Genuine below-chance would require "
                "anti-correlation with gold via adversarial near-miss distractors, "
                "which would be an interpretable granularity-bias finding rather "
                "than metric invalidity, and is not established at this n.",
            ],
            "disposition_unchanged": (
                "LLM strict@1 stays deprecated; the decisive ground is "
                "payload_symmetry, this section is supporting only"
            ),
            "open_item": (
                "_apply_total_order has a competition_fallback path but records.json "
                "does not persist the method field, so LLM-output errors cannot be "
                "separated from deterministic fallback after a parse failure"
            ),
        },
        "by_payload_stratum": {
            "degenerate": agg(degraded),
            "complete": agg(complete),
        },
        "per_arm": per_arm,
    }


# --------------------------------------------------------------------------
# deterministic tie-discounted endpoint (no LLM)
# --------------------------------------------------------------------------
def _dense_gold_profile(rec: Mapping[str, Any]) -> tuple[bool, int, int]:
    """(gold_matched, gold_dense_rank, tie_width_at_that_rank) from ``best_rank``.

    ``best_rank`` (best leaf joint rank an option projects onto) survives the
    strict step, so the pre-strict dense option ranking can be rebuilt for every
    arm -- including the block-2 rematch arms, whose stored ``gold_option_rank``
    still refers to the pre-compat mapper row.
    """
    om = ((rec.get("projection") or {}).get("option_maps")) or {}
    gold = str(rec.get("gold_letter") or "").upper()
    matched = {
        L: r for L, r in om.items()
        if (r.get("matched_gate_partition") == "matched")
        or (r.get("best_rank") is not None)
    }
    if gold not in matched:
        return False, -1, 0
    br = {L: r.get("best_rank") for L, r in matched.items()}
    if any(v is None for v in br.values()):
        br = {L: (v if v is not None else 10 ** 9) for L, v in br.items()}
    g = int(br[gold])
    rank = 1 + sum(1 for v in br.values() if int(v) < g)
    width = sum(1 for v in br.values() if int(v) == g)
    return True, rank, width


def deterministic_endpoints(arm_dir: Path) -> dict[str, Any]:
    """option@1 / tie-discounted / ties-are-misses, all closed-form."""
    rec_path = arm_dir / "records.json"
    if not rec_path.is_file():
        return {}
    recs = _records(rec_path)
    n = len(recs) or 1
    legacy = disc = alone = 0.0
    n_abstain = n_tied = 0
    widths: list[int] = []
    for rec in recs.values():
        matched, rank, width = _dense_gold_profile(rec)
        if not matched:
            n_abstain += 1
            continue
        if rank != 1:
            continue
        legacy += 1.0
        disc += 1.0 / width
        if width == 1:
            alone += 1.0
        else:
            n_tied += 1
            widths.append(width)
    return {
        "n": len(recs),
        "legacy_option_at1": round(legacy / n, 4),
        "tie_discounted_at1": round(disc / n, 4),
        "ties_are_misses_at1": round(alone / n, 4),
        "n_gold_unmatched": n_abstain,
        "n_gold_in_tied_rank1": n_tied,
        "mean_tie_width_when_hit": (
            round(sum(widths) / len(widths), 3) if widths else None
        ),
        "tie_credit_share_of_legacy": (
            round((legacy - alone) / legacy, 4) if legacy else None
        ),
    }


def _credit_map(arm_dir: Path) -> dict[str, float]:
    """Per-case tie-discounted credit (1 / tie width at dense rank 1, else 0)."""
    rec_path = arm_dir / "records.json"
    if not rec_path.is_file():
        return {}
    out: dict[str, float] = {}
    for cid, rec in _records(rec_path).items():
        matched, rank, width = _dense_gold_profile(rec)
        out[cid] = 1.0 / width if (matched and rank == 1 and width) else 0.0
    return out


def paired_bootstrap(
    a: Mapping[str, float],
    b: Mapping[str, float],
    *,
    name: str,
    n_boot: int = 5000,
    seed: int = 20260729,
) -> dict[str, Any]:
    """Paired case bootstrap on the continuous tie-discounted credit."""
    import random

    keys = sorted(set(a) & set(b))
    n = len(keys)
    if n == 0:
        return {"contrast": name, "n_paired": 0}
    diffs = [a[k] - b[k] for k in keys]
    point = sum(diffs) / n
    if all(abs(v) < 1e-12 for v in diffs):
        return {
            "contrast": name,
            "n_paired": n,
            "mean_a": round(sum(a[k] for k in keys) / n, 4),
            "mean_b": round(sum(b[k] for k in keys) / n, 4),
            "delta": 0.0,
            "ci95": [0.0, 0.0],
            "p_two_sided_addone": 1.0,
            "note": "identical per-case credit on every case (structural identity)",
            "n_boot": 0,
            "seed": seed,
        }
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        boots.append(
            sum(diffs[rng.randrange(n)] for _ in range(n)) / n
        )
    boots.sort()
    lo = boots[int(0.025 * n_boot)]
    hi = boots[int(0.975 * n_boot) - 1]
    n_le = sum(1 for v in boots if v <= 0.0)
    p = 2.0 * min(n_le + 1, n_boot - n_le + 1) / (n_boot + 1)
    return {
        "contrast": name,
        "n_paired": n,
        "mean_a": round(sum(a[k] for k in keys) / n, 4),
        "mean_b": round(sum(b[k] for k in keys) / n, 4),
        "delta": round(point, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "p_two_sided_addone": round(min(1.0, p), 5),
        "n_boot": n_boot,
        "seed": seed,
    }


def main() -> int:
    out: dict[str, Any] = {
        # v2 (2026-07-29): tie_breaker_information gained _verdict /
        # by_payload_stratum and moved its per-arm rows under "per_arm".
        "schema_version": 2,
        "purpose": (
            "Gatekeeping audit for the DA strict-total-order endpoint: caliber "
            "homogeneity, paired significance, payload symmetry (decisive), and "
            "whether the LLM tie-breaker carries information beyond the "
            "closed-form 1/width expectation (supporting; the earlier "
            "'worse than random' claim was retracted 2026-07-29)."
        ),
    }

    main_arms = STRICT / "arms"
    b2_arms = STRICT / "block2_c1/arms"

    # ---- 1. caliber homogeneity for block 2 -----------------------------
    rematch_m00 = _strict_hits(_records(b2_arms / "M00/records.json"))
    live_m00 = _strict_hits(_records(main_arms / "M00_live_compat_b12/records.json"))
    precompat_m00 = _strict_hits(_records(main_arms / "M00_precompat/records.json"))
    paper_rematch = _strict_hits(
        _records(main_arms / "M00_paper_rematch_071/records.json")
    )

    out["m00_variants"] = {
        "rematch_block2": round(sum(rematch_m00.values()) / max(1, len(rematch_m00)), 4),
        "paper_rematch_main": round(
            sum(paper_rematch.values()) / max(1, len(paper_rematch)), 4
        ),
        "live_compat_b12": round(sum(live_m00.values()) / max(1, len(live_m00)), 4),
        "precompat_native": round(
            sum(precompat_m00.values()) / max(1, len(precompat_m00)), 4
        ),
    }
    out["rematch_vs_live_confound"] = paired(
        live_m00, rematch_m00, name="M00 live - M00 rematch (same operator!)"
    )

    b2_ids = ["AB05", "AB07", "AB08", "AB09", "AB10", "AB11", "AB20"]
    rows = []
    for ab in b2_ids:
        p = b2_arms / ab / "records.json"
        if not p.is_file():
            continue
        hits = _strict_hits(_records(p))
        rows.append({
            "arm": ab,
            "vs_rematch_m00_same_caliber": paired(
                rematch_m00, hits, name=f"M00(rematch) - {ab}(rematch)"
            ),
            "vs_live_m00_mixed_caliber": paired(
                live_m00, hits, name=f"M00(live) - {ab}(rematch)"
            ),
        })
    out["block2_paired"] = rows

    # ---- 2. tie-breaker information content ----------------------------
    info = {}
    for name in (
        "M00_live_compat_b12", "M00_paper_rematch_071", "M00_precompat",
        "AB01", "AB03", "AB21", "AB22", "B02-matched-rerank", "B07", "B00",
    ):
        d = main_arms / name
        if d.is_dir():
            got = tie_break_information(d)
            if got:
                info[name] = got
    for ab in b2_ids:
        d = b2_arms / ab
        if d.is_dir():
            got = tie_break_information(d)
            if got:
                info[f"block2/{ab}"] = got
    out["tie_breaker_information"] = _tie_breaker_section(info)

    # ---- 3. deterministic tie-discounted endpoints ---------------------
    det: dict[str, Any] = {}
    for d in sorted(main_arms.iterdir()) if main_arms.is_dir() else []:
        if d.is_dir():
            got = deterministic_endpoints(d)
            if got:
                det[d.name] = got
    for ab in b2_ids:
        got = deterministic_endpoints(b2_arms / ab)
        if got:
            det[f"block2/{ab}"] = got
    out["deterministic_endpoints"] = det

    # ---- 3b. paired tests under the deterministic caliber --------------
    live_credit = _credit_map(main_arms / "M00_live_compat_b12")
    rematch_credit = _credit_map(b2_arms / "M00")
    tests: list[dict[str, Any]] = []
    for base in ("B07", "B04", "B17", "B02-matched-rerank", "B02-cm-sc10", "B00"):
        d = main_arms / base
        if d.is_dir():
            tests.append(
                paired_bootstrap(
                    live_credit, _credit_map(d),
                    name=f"M00 live - {base} (headline, tie-discounted)",
                )
            )
    for ab in ("AB01", "AB03"):
        d = main_arms / ab
        if d.is_dir():
            tests.append(
                paired_bootstrap(
                    live_credit, _credit_map(d),
                    name=f"M00 live - {ab} (block 1, tie-discounted)",
                )
            )
    for ab in b2_ids:
        tests.append(
            paired_bootstrap(
                rematch_credit, _credit_map(b2_arms / ab),
                name=f"M00 rematch - {ab} (block 2, same caliber, tie-discounted)",
            )
        )
    out["deterministic_paired_tests"] = tests

    # ---- 4. payload symmetry check ------------------------------------
    out["payload_symmetry"] = {
        "issue": (
            "process_records_arm resolves DA cases from "
            "data/benchmarks/diagnosisarena/normalized_cases.json, which does "
            "not exist. Every baseline arm therefore called the tie-breaker with "
            "an empty vignette and option letters carrying no text, while our "
            "arms supplied full vignette + option texts + labelled leaves."
        ),
        "affected": "all B* baseline arms in da_strict_order_v1/arms",
        "consequence": (
            "LLM strict@1 for baselines is not comparable to ours; the widened "
            "headline margin under this endpoint is partly a payload artifact."
        ),
    }

    OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
