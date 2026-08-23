#!/usr/bin/env python3
"""How much of the generation-side gap is recall and how much is knowledge?  Zero calls.

Collapse3c reaches a clinical-complete candidate in its pool for only 177/800
cases; the selector-side routes are all closed, so the question is what the
remaining 623 are made of.  Two structurally different answers demand different
mechanisms:

- **recall/portfolio**: some other configuration already produces the right
  candidate on this case, so the label is inside the model family's reach and the
  loss is in which candidates this arm happens to write down;
- **knowledge**: no configuration ever produced it, so no prompt or stance change
  reaches it and only external knowledge could.

`CEILING_POOL_CENSUS` already froze the material needed to separate them: an
occurrence ledger of 320,190 `(arm, case, candidate)` rows over 52 arms and all
800 cases, and a three-model panel judging 19,599 distinct `(case, label)`
relations, of which 815 are `complete_equivalent`.  The union over arms is
therefore computable at zero cost, and it is an upper bound on what any
generation-side prompt/stance/retrieval change can deliver.

Two exclusions keep the union honest:

- **The whole E5 group is dropped, not merely its synthetic candidate types.**
  E5 constructs selector payloads around the reference answer: it injects
  candidates typed `parent` / `sibling` / `synonym` / `component` / `unrelated` /
  `width_distractor`, and arms such as `remove_non_gold3` are built by deleting
  non-reference candidates.  Empirically all nine E5 arms reach a complete
  candidate on 100.00% of their cases, which is the signature of an oracle rather
  than a generator.  Dropping only the synthetic *candidate types* is not enough,
  because the surviving `base_option` rows still carry the guaranteed answer.
- **`actual_payload` / `effective_frontier` surfaces are not used for reach.**
  Reach is a property of what the arm *generated*, so it is read off the arm's own
  registry surface; the narrower surfaces are reported separately as the loss from
  registry to payload.

The panel only judged labels that some arm produced, so "no arm reaches it" means
"no label any of these 52 arms produced was judged complete".  That is the
strongest available bound and it is not the same as "the model cannot produce it".
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from clinical_endpoint import COMPLETE, PARTIAL, ClinicalEndpoint  # noqa: E402

LEDGER = (
    ROOT
    / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS/design/occurrence_ledger.jsonl"
)
# Authoritative identifiability tiering: E2's unified_800 covers all 800 cases.
# The ALL_ARM migration replay carries the same field but only on the 751 cases
# that have a reference row, which silently drops 49 cases.
IDENTIFIABILITY = (
    ROOT
    / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/unified_800/five_endpoint_replay.jsonl"
)
# Carries `reference_diagnosis` per case.
MIGRATION = (
    ROOT
    / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/final/five_endpoint_replay.jsonl"
)
# The only tier on which "the arm should have produced the exact reference" is a
# fair demand. The other tiers say the vignette does not determine the
# reference's specificity, so a miss there is a label property, not a recall bug.
FAIR_TIER = "unique_full_reference"
OUT_DIR = ROOT / "analysis/mechanism_v2/results/GEN_HEADROOM"

# Candidates the E5 builder constructed from the reference answer rather than
# generated.  Including them would make the union circular.
SYNTHETIC_TYPES = {
    "parent",
    "sibling",
    "synonym",
    "component",
    "unrelated",
    "width_distractor",
}
# Oracle group: every arm in it reaches a complete candidate on 100% of cases.
ORACLE_GROUPS = {"E5"}
REGISTRY_SURFACE = "raw_registry"
# The production family that the counterfactual line has been auditing.
FOCUS_ARM = "Collapse3c"


def _identifiability() -> tuple[dict[str, str], dict[str, str]]:
    """case_key -> (reference_identifiability, reference_diagnosis)."""
    tier: dict[str, str] = {}
    ref: dict[str, str] = {}
    for path, want_tier in ((IDENTIFIABILITY, True), (MIGRATION, False)):
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                ck = str(r.get("case_key") or "")
                if not ck:
                    continue
                if want_tier:
                    t = str(r.get("reference_identifiability") or "")
                    if t:
                        tier.setdefault(ck, t)
                d = str(r.get("reference_diagnosis") or "")
                if d:
                    ref.setdefault(ck, d)
    return tier, ref


def main() -> None:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    canon = clinical.bridge.canonical_key
    tier, _refs = _identifiability()

    # (case_key, arm) -> best relation seen on the arm's own registry surface
    reach: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    # narrower surfaces, to separate "generated it" from "showed it to the selector"
    reach_payload: dict[str, set[str]] = defaultdict(set)
    reach_frontier: dict[str, set[str]] = defaultdict(set)
    arm_group: dict[str, str] = {}
    dropped_synthetic = 0
    dropped_oracle = 0
    rows = 0
    judged = 0

    with LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            rows += 1
            if str(r.get("experiment_group") or "") in ORACLE_GROUPS:
                dropped_oracle += 1
                continue
            if str(r.get("candidate_type") or "") in SYNTHETIC_TYPES:
                dropped_synthetic += 1
                continue
            case = str(r.get("case_key") or "")
            arm = str(r.get("arm_id") or "")
            label = str(r.get("candidate_label") or "").strip()
            if not case or not arm or not label:
                continue
            arm_group[arm] = str(r.get("experiment_group") or "")
            rel = clinical._rel.get((case, canon(label)))
            if rel is None:
                continue
            judged += 1
            surface = str(r.get("surface") or "")
            if surface == REGISTRY_SURFACE:
                reach[case][arm].add(rel)
            elif surface == "actual_payload":
                reach_payload[case].add(rel)
            elif surface == "effective_frontier":
                reach_frontier[case].add(rel)

    all_cases = sorted(reach)
    genuine_arms = sorted(arm_group)

    def fam(case_key: str) -> str:
        return "da" if case_key.startswith("DA_") else "mcr"

    # ---- per-arm reach -------------------------------------------------
    per_arm: dict[str, dict[str, Any]] = {}
    for arm in genuine_arms:
        c = Counter()
        for case in all_cases:
            rels = reach[case].get(arm)
            if rels is None:
                continue  # arm never ran this case
            c[f"{fam(case)}_cases"] += 1
            if COMPLETE in rels:
                c[f"{fam(case)}_complete"] += 1
            if COMPLETE in rels or PARTIAL in rels:
                c[f"{fam(case)}_c_or_p"] += 1
        per_arm[arm] = {
            "group": arm_group[arm],
            "da_cases": c["da_cases"],
            "mcr_cases": c["mcr_cases"],
            "da_complete_reach": (
                round(c["da_complete"] / c["da_cases"], 4) if c["da_cases"] else None
            ),
            "mcr_complete_reach": (
                round(c["mcr_complete"] / c["mcr_cases"], 4) if c["mcr_cases"] else None
            ),
            "da_complete_n": c["da_complete"],
            "mcr_complete_n": c["mcr_complete"],
        }

    # ---- union and its decomposition -----------------------------------
    union: dict[str, dict[str, Any]] = {}
    n_arms_hist = defaultdict(Counter)
    focus_miss_but_union_hit: list[dict[str, Any]] = []
    for f in ("da", "mcr"):
        cases = [c for c in all_cases if fam(c) == f]
        u_complete, u_cp, focus_complete, both, gap, dead = 0, 0, 0, 0, 0, 0
        hist14_only = 0
        for case in cases:
            arms_hit = [a for a, rels in reach[case].items() if COMPLETE in rels]
            any_complete = bool(arms_hit)
            hist14_only += int(any(arm_group.get(a) == "HIST14" for a in arms_hit))
            any_cp = any(
                (COMPLETE in rels or PARTIAL in rels) for rels in reach[case].values()
            )
            focus_rels = reach[case].get(FOCUS_ARM) or set()
            focus_hit = COMPLETE in focus_rels
            u_complete += int(any_complete)
            u_cp += int(any_cp)
            focus_complete += int(focus_hit)
            if any_complete:
                n_arms_hist[f][len(arms_hit)] += 1
            if any_complete and focus_hit:
                both += 1
            elif any_complete and not focus_hit:
                gap += 1
                if len(focus_miss_but_union_hit) < 12:
                    focus_miss_but_union_hit.append(
                        {
                            "case_key": case,
                            "n_arms_reaching": len(arms_hit),
                            "arms": sorted(arms_hit)[:6],
                            "focus_best_relation": (
                                PARTIAL if PARTIAL in focus_rels else "none/wrong"
                            ),
                        }
                    )
            if not any_complete:
                dead += 1
        union[f] = {
            "cases": len(cases),
            "union_complete_reach_n": u_complete,
            "union_complete_reach": round(u_complete / len(cases), 4),
            "union_hist14_production_arms_only_n": hist14_only,
            "union_hist14_production_arms_only": round(hist14_only / len(cases), 4),
            "union_c_or_p_reach": round(u_cp / len(cases), 4),
            f"{FOCUS_ARM}_complete_reach_n": focus_complete,
            f"{FOCUS_ARM}_complete_reach": round(focus_complete / len(cases), 4),
            "recall_headroom_n": gap,
            "recall_headroom_share_of_cases": round(gap / len(cases), 4),
            "no_arm_reaches_n": dead,
            "no_arm_reaches_share": round(dead / len(cases), 4),
        }

    # ---- what the focus arm's misses are actually made of ---------------
    # The complete/not-complete boundary is the reliable one (A/B 0.9857).  The
    # partial-vs-manifestation split below sits on the *unreliable* fine boundary
    # (A/B fine 0.7210 < 0.80 required, and this is one of the two named
    # disagreement pairs), so it sizes a direction, not a deliverable.
    miss_shape: dict[str, Counter] = {"da": Counter(), "mcr": Counter()}
    # Does "the pool stopped at the parent" coincide with "the vignette only
    # supports the parent"?  If it does, sharpening is chasing a label property.
    parent_by_tier: dict[str, Counter] = {"da": Counter(), "mcr": Counter()}
    for case in all_cases:
        rels = reach[case].get(FOCUS_ARM)
        if rels is None or COMPLETE in rels:
            continue
        f = fam(case)
        miss_shape[f]["misses"] += 1
        if PARTIAL in rels:
            miss_shape[f]["has_parent_or_component"] += 1
            parent_by_tier[f][tier.get(case) or "no_reference_row"] += 1
        elif "manifestation_or_related" in rels:
            miss_shape[f]["only_manifestation_or_related"] += 1
        elif "conflicting_subtype_or_scope" in rels:
            miss_shape[f]["only_conflicting_subtype_or_scope"] += 1
        elif rels - {"uncertain"}:
            miss_shape[f]["only_not_equivalent"] += 1
        else:
            miss_shape[f]["nothing_usable"] += 1
        # is the same case rescued by some other arm?
        if any(COMPLETE in r for a, r in reach[case].items() if a != FOCUS_ARM):
            miss_shape[f]["another_arm_reaches_it"] += 1

    # ---- the same census restricted to the fair tier ---------------------
    fair: dict[str, Any] = {}
    for f in ("da", "mcr"):
        cases = [c for c in all_cases if fam(c) == f and tier.get(c) == FAIR_TIER]
        if not cases:
            continue
        focus_hit = sum(
            1 for c in cases if COMPLETE in (reach[c].get(FOCUS_ARM) or set())
        )
        union_hit = sum(
            1
            for c in cases
            if any(COMPLETE in rels for rels in reach[c].values())
        )
        gap = sum(
            1
            for c in cases
            if any(COMPLETE in rels for rels in reach[c].values())
            and COMPLETE not in (reach[c].get(FOCUS_ARM) or set())
        )
        fair[f] = {
            "cases_on_fair_tier": len(cases),
            f"{FOCUS_ARM}_complete_reach": round(focus_hit / len(cases), 4),
            f"{FOCUS_ARM}_complete_reach_n": focus_hit,
            "union_complete_reach": round(union_hit / len(cases), 4),
            "union_complete_reach_n": union_hit,
            "recall_headroom_n": gap,
            "no_arm_reaches_n": len(cases) - union_hit,
            "no_arm_reaches_share": round((len(cases) - union_hit) / len(cases), 4),
        }

    # ---- the intersection that a specialisation step would have to serve ----
    # (a) the arm missed, (b) it nonetheless holds a parent/component, (c) the
    # reference is uniquely identifiable from the vignette, (d) no other arm ever
    # produced the exact reference either.
    target: dict[str, Counter] = {"da": Counter(), "mcr": Counter()}
    target_examples: list[dict[str, Any]] = []
    for case in all_cases:
        rels = reach[case].get(FOCUS_ARM)
        if rels is None or COMPLETE in rels or PARTIAL not in rels:
            continue
        if tier.get(case) != FAIR_TIER:
            continue
        f = fam(case)
        target[f]["parent_and_fair_tier"] += 1
        if any(COMPLETE in r for a, r in reach[case].items() if a != FOCUS_ARM):
            target[f]["another_arm_already_names_it"] += 1
        else:
            target[f]["no_arm_names_it"] += 1
            if len(target_examples) < 10:
                target_examples.append(
                    {
                        "case_key": case,
                        "reference": _refs.get(case, ""),
                        "n_pool_candidates": len(
                            [
                                1
                                for _ in (reach[case].get(FOCUS_ARM) or set())
                            ]
                        ),
                    }
                )

    # ---- what a *deliverable* union would buy -----------------------------
    # Unioning all 43 arms is not a method, it is 43x the generation cost. The
    # question is what 2-3 production arms buy, greedily chosen, on the tier where
    # an exact hit is a fair demand. Note `MCR_SELECTION_LAYER_AUDIT` already
    # refuted *swapping* pools (net -13 cases); this sizes *adding* them, which is
    # a different operation with an untested prior.
    prod_arms = [a for a in genuine_arms if arm_group[a] == "HIST14"]
    greedy: dict[str, Any] = {}
    for f in ("da", "mcr"):
        cases = [c for c in all_cases if fam(c) == f and tier.get(c) == FAIR_TIER]
        if not cases:
            continue
        hit: dict[str, set[str]] = {
            a: {
                c
                for c in cases
                if COMPLETE in (reach[c].get(a) or set())
            }
            for a in prod_arms
        }
        # only arms that actually ran the whole tier are comparable
        ran = {
            a: len([c for c in cases if reach[c].get(a) is not None])
            for a in prod_arms
        }
        full = [a for a in prod_arms if ran[a] == len(cases)]
        chosen: list[dict[str, Any]] = []
        covered: set[str] = set()
        pool_arms = list(full)
        while pool_arms and len(chosen) < 4:
            best = max(pool_arms, key=lambda a: len(hit[a] - covered))
            add = len(hit[best] - covered)
            covered |= hit[best]
            chosen.append(
                {
                    "arm": best,
                    "marginal_new_cases": add,
                    "cumulative_n": len(covered),
                    "cumulative_reach": round(len(covered) / len(cases), 4),
                }
            )
            pool_arms.remove(best)
            if add == 0:
                break
        greedy[f] = {
            "cases_on_fair_tier": len(cases),
            "arms_that_ran_the_whole_tier": len(full),
            "greedy_sequence": chosen,
        }

    best_da = max(
        (v["da_complete_reach"] or 0, k) for k, v in per_arm.items() if v["da_cases"]
    )
    best_mcr = max(
        (v["mcr_complete_reach"] or 0, k) for k, v in per_arm.items() if v["mcr_cases"]
    )

    report: dict[str, Any] = {
        "schema_version": "gen-headroom-census-v1",
        "model_calls": 0,
        "ledger_rows": rows,
        "rows_dropped_oracle_group_e5": dropped_oracle,
        "rows_dropped_as_synthetic_type": dropped_synthetic,
        "rows_with_a_frozen_clinical_relation": judged,
        "arms": len(genuine_arms),
        "reach_surface": REGISTRY_SURFACE,
        "union": union,
        "best_single_arm": {
            "da": {"arm": best_da[1], "reach": best_da[0]},
            "mcr": {"arm": best_mcr[1], "reach": best_mcr[0]},
        },
        "arms_reaching_a_reachable_case": {
            f: dict(sorted(n_arms_hist[f].items())) for f in ("da", "mcr")
        },
        "focus_arm_miss_shape": {
            f: dict(sorted(miss_shape[f].items())) for f in ("da", "mcr")
        },
        "reference_identifiability_all_cases": {
            f: dict(
                Counter(
                    tier.get(c) or "no_reference_row"
                    for c in all_cases
                    if fam(c) == f
                ).most_common()
            )
            for f in ("da", "mcr")
        },
        "parent_in_pool_by_reference_tier": {
            f: dict(parent_by_tier[f].most_common()) for f in ("da", "mcr")
        },
        "restricted_to_fair_reference_tier": fair,
        "specialisation_target_set": {
            f: dict(sorted(target[f].items())) for f in ("da", "mcr")
        },
        "specialisation_target_examples": target_examples,
        "greedy_production_arm_union_on_fair_tier": greedy,
        "fine_boundary_caveat": (
            "partial_parent_or_component vs manifestation_or_related is one of the two "
            "pairs where the panel's fine taxonomy fails its gate (A/B fine exact "
            "0.7210 < 0.80). Only the complete/not-complete split is reliable (0.9857)."
        ),
        "per_arm": per_arm,
        "examples_union_hit_focus_miss": focus_miss_but_union_hit,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "headroom.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"ledger rows {rows}, synthetic dropped {dropped_synthetic}, judged {judged}")
    print(f"arms {len(genuine_arms)}, surface = {REGISTRY_SURFACE}\n")
    for f in ("da", "mcr"):
        u = union[f]
        print(f"=== {f.upper()}  n={u['cases']}")
        print(
            f"  {FOCUS_ARM:12s} 池内可达 complete : {u[FOCUS_ARM + '_complete_reach_n']:4d}"
            f"  ({u[FOCUS_ARM + '_complete_reach']:.4f})"
        )
        print(
            f"  {'并集(全真实臂)':12s} 池内可达 complete : {u['union_complete_reach_n']:4d}"
            f"  ({u['union_complete_reach']:.4f})"
        )
        print(
            f"  {'并集(仅HIST14)':12s} 池内可达 complete : "
            f"{u['union_hist14_production_arms_only_n']:4d}"
            f"  ({u['union_hist14_production_arms_only']:.4f})"
        )
        print(
            f"  {'召回头寸':12s} 并集可达而该臂不可达: {u['recall_headroom_n']:4d}"
            f"  ({u['recall_headroom_share_of_cases']:.4f})"
        )
        print(
            f"  {'无臂可达':12s}（知识天花板候选）  : {u['no_arm_reaches_n']:4d}"
            f"  ({u['no_arm_reaches_share']:.4f})"
        )
        print(f"  union C∪P 可达: {u['union_c_or_p_reach']:.4f}")
    print(f"\n最强单臂: DA {best_da[1]} {best_da[0]:.4f} | MCR {best_mcr[1]} {best_mcr[0]:.4f}")
    print(f"\n{FOCUS_ARM} 未命中病例的构成（精细边界不可靠，仅定方向）:")
    for f in ("da", "mcr"):
        m = miss_shape[f]
        tot = m["misses"] or 1
        print(f"  {f.upper()} misses={m['misses']}")
        for k in (
            "has_parent_or_component",
            "only_manifestation_or_related",
            "only_conflicting_subtype_or_scope",
            "only_not_equivalent",
            "nothing_usable",
            "another_arm_reaches_it",
        ):
            print(f"    {k:36s} {m[k]:4d}  ({m[k]/tot:.4f})")

    print("\n参考答案可识别性（全部病例）:")
    for f in ("da", "mcr"):
        c = Counter(
            tier.get(x) or "no_reference_row" for x in all_cases if fam(x) == f
        )
        print(f"  {f.upper()}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))

    print(f"\n{FOCUS_ARM} 「池内有父类/成分」的病例，按参考答案可识别性分:")
    for f in ("da", "mcr"):
        t = parent_by_tier[f]
        tot = sum(t.values()) or 1
        print(f"  {f.upper()} n={sum(t.values())}")
        for k, v in t.most_common():
            print(f"    {k:36s} {v:4d}  ({v/tot:.4f})")

    print(f"\n只在 {FAIR_TIER} 上重算（这是唯一可以公平要求命中的层）:")
    for f in ("da", "mcr"):
        if f not in fair:
            continue
        v = fair[f]
        print(
            f"  {f.upper()} n={v['cases_on_fair_tier']:3d} | "
            f"{FOCUS_ARM} {v[FOCUS_ARM + '_complete_reach']:.4f} | "
            f"并集 {v['union_complete_reach']:.4f} | "
            f"召回头寸 {v['recall_headroom_n']:3d} | "
            f"无臂可达 {v['no_arm_reaches_n']:3d} ({v['no_arm_reaches_share']:.4f})"
        )

    print("\n特异化机制的靶集（池内有父类 ∩ 参考可唯一识别）:")
    for f in ("da", "mcr"):
        t = target[f]
        print(
            f"  {f.upper()}: 靶集 {t['parent_and_fair_tier']:3d}"
            f" = 无任何臂命名 {t['no_arm_names_it']:3d}"
            f" + 已有别的臂命名 {t['another_arm_already_names_it']:3d}"
        )
    print("  样例（参考答案 = 需要被特异化到的目标）:")
    for e in target_examples[:8]:
        print(f"    {e['case_key']:28s} -> {e['reference']}")

    print("\n贪心并池（仅生产臂，仅公平层）——每加一个臂的边际新增:")
    for f in ("da", "mcr"):
        if f not in greedy:
            continue
        g = greedy[f]
        print(
            f"  {f.upper()} n={g['cases_on_fair_tier']}"
            f"（跑完整层的生产臂 {g['arms_that_ran_the_whole_tier']} 个）"
        )
        for i, s in enumerate(g["greedy_sequence"], 1):
            print(
                f"    +{i} {s['arm']:14s} 边际 {s['marginal_new_cases']:3d}"
                f" -> 累计 {s['cumulative_n']:3d} ({s['cumulative_reach']:.4f})"
            )

    print("\n可达病例被多少个臂命中（1 = 只有一个臂捞到）:")
    for f in ("da", "mcr"):
        h = dict(sorted(n_arms_hist[f].items()))
        tot = sum(h.values())
        lone = h.get(1, 0)
        print(f"  {f}: n={tot}, 仅 1 臂命中 {lone} ({lone/tot:.3f})" if tot else f"  {f}: 0")
        print(f"      {h}")


if __name__ == "__main__":
    main()
