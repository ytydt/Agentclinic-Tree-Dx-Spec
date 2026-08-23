"""Offline slot-yield diagnostic on the frozen C0 pool census.

Decomposes every frozen arm into complete-object exposure and conditional
conversion, using only the binary complete/not-complete boundary of the C0
three-model panel. That boundary is the one panel surface that passed its
reliability gate (raw agreement 0.9857, Gwet AC1 0.9843 over 19,599 frozen
relations); the five-way fine taxonomy did not and is never read here.

Provenance: model-panel sensitivity labels, not human-root truth. E2 root
relations and frozen safe-exact identities are already folded into the panel's
`final_relation` by the census overrides.

No provider call is made. Every number is a deterministic function of the
frozen census ledgers.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

CENSUS = Path("analysis/mechanism_v2/results/CEILING_POOL_CENSUS")
PANEL = CENSUS / "panel/three_model_adjudicated_panel.jsonl"
OCCURRENCES = CENSUS / "design/occurrence_ledger.jsonl"
E2_REPLAY = Path(
    "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication"
    "/unified_800/five_endpoint_replay.jsonl"
)

# E5 injected the reference into every pool by construction, so its exposure is
# not an achievable generation capability and must never enter a union.
GOLD_INJECTED_GROUPS = frozenset({"E5"})

# Comparators already established as weak controls by their owning experiments
# (E4 evidence-count control; the legacy APHHM-C deterministic ordinal ranker).
# Excluding them is post hoc and is reported as a labelled sensitivity only.
WEAK_COMPARATORS = frozenset({"evidence_count_control", "APHHM-C"})

COMPLETE = "complete_equivalent"
PARTIAL = "partial_parent_or_component"


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


class Census:
    """Frozen per-arm pools joined to the binary complete boundary."""

    def __init__(self, root: Path = Path(".")) -> None:
        self.family: dict[str, str] = {}
        self.pool: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self.served: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.exposed: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.converted: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.case_relations: dict[str, set[str]] = defaultdict(set)
        self.exposing_arms: dict[str, set[tuple[str, str]]] = defaultdict(set)

        relation = {
            row["relation_id"]: row["final_relation"]
            for row in read_jsonl(root / PANEL)
        }
        for row in read_jsonl(root / OCCURRENCES):
            if not row.get("served"):
                continue
            arm = (row["experiment_group"], row["arm_id"])
            case = row["case_key"]
            self.family[case] = row["benchmark_family"]
            self.pool[(arm[0], arm[1], case)].add(row["normalized_label"])
            self.served[arm].add(case)
            label = relation.get(row["relation_id"])
            if arm[0] not in GOLD_INJECTED_GROUPS:
                self.case_relations[case].add(label)
            if label != COMPLETE:
                continue
            self.exposed[arm].add(case)
            if arm[0] not in GOLD_INJECTED_GROUPS:
                self.exposing_arms[case].add(arm)
            if row.get("is_top1"):
                self.converted[arm].add(case)

        self.identifiability = {
            row["case_key"]: row["reference_identifiability"]
            for row in read_jsonl(root / E2_REPLAY)
        }

    def cases(self, family: str) -> set[str]:
        return {case for case, fam in self.family.items() if fam == family}

    def mean_pool(self, arm: tuple[str, str], cases: Iterable[str]) -> float:
        sizes = [len(self.pool[(arm[0], arm[1], case)]) for case in cases]
        return statistics.mean(sizes) if sizes else 0.0


def arm_table(census: Census, family: str, min_served: int = 100) -> list[dict[str, Any]]:
    """Per-arm exposure / conversion / pool size for one benchmark family."""
    rows: list[dict[str, Any]] = []
    for arm in sorted(census.served):
        cases = {c for c in census.served[arm] if census.family[c] == family}
        if len(cases) < min_served:
            continue
        exposed = census.exposed[arm] & cases
        converted = census.converted[arm] & cases
        rows.append(
            {
                "arm_id": arm[1],
                "conversion": len(converted) / len(exposed) if exposed else None,
                "experiment_group": arm[0],
                "exposure_rate": len(exposed) / len(cases),
                "gold_injected": arm[0] in GOLD_INJECTED_GROUPS,
                "mean_pool_size": census.mean_pool(arm, cases),
                "n_complete_top1": len(converted),
                "n_exposed": len(exposed),
                "n_served": len(cases),
                "top1_complete_rate": len(converted) / len(cases),
            }
        )
    return rows


def weighted_slope(points: list[tuple[float, float, int]]) -> dict[str, float]:
    """Exposure-weighted least squares of conversion on pool size."""
    xs = [x for x, _, _ in points]
    ys = [y for _, y, _ in points]
    ws = [w for _, _, w in points]
    total = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / total
    my = sum(w * y for w, y in zip(ws, ys)) / total
    denominator = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    slope = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / denominator
    return {"intercept": my - slope * mx, "n_arms": len(xs), "slope_per_candidate": slope}


def conversion_fits(census: Census, family: str) -> dict[str, Any]:
    """Conversion-vs-width fits under progressively cleaner identification."""
    table = [row for row in arm_table(census, family) if not row["gold_injected"]]
    usable = [row for row in table if row["n_exposed"] >= 10]

    def fit(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        points = [
            (row["mean_pool_size"], row["conversion"], row["n_exposed"]) for row in rows
        ]
        if len({x for x, _, _ in points}) < 2:
            return None
        return weighted_slope(points)

    return {
        "all_natural_arms": fit(usable),
        "excluding_weak_comparators_post_hoc": fit(
            [row for row in usable if row["arm_id"] not in WEAK_COMPARATORS]
        ),
        "within_e12_pool_ladder": fit(
            [row for row in usable if row["experiment_group"] == "E12"]
        ),
    }


def break_even(intercept: float, slope: float, pool: float, exposure: float) -> float:
    """Exposure gain per added slot required for a net-positive complete rate.

    complete(p) = E(p) * C(p). Requiring d(complete)/dp > 0 gives
    E'(p) > E(p) * (-C'(p)) / C(p).
    """
    conversion = intercept + slope * pool
    return exposure * (-slope) / conversion


def union_dose_response(
    census: Census,
    family: str,
    group: str = "HIST14",
    draws: int = 400,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Mean union exposure and deduplicated pool size against pooled-arm count."""
    cases = sorted(census.cases(family))
    arms = [
        arm
        for arm in census.served
        if arm[0] == group and len(census.served[arm]) >= 395
    ]
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for k in range(1, len(arms) + 1):
        exposures: list[float] = []
        sizes: list[float] = []
        for _ in range(draws):
            subset = rng.sample(arms, k)
            union = set().union(*[census.exposed[a] & set(cases) for a in subset])
            exposures.append(len(union) / len(cases))
            sample = rng.sample(cases, min(60, len(cases)))
            sizes.append(
                statistics.mean(
                    len(set().union(*[census.pool[(a[0], a[1], c)] for a in subset]))
                    for c in sample
                )
            )
        rows.append(
            {
                "mean_union_exposure": statistics.mean(exposures),
                "mean_union_pool_size": statistics.mean(sizes),
                "n_arms_pooled": k,
            }
        )
    for previous, current in zip(rows, rows[1:]):
        added = current["mean_union_pool_size"] - previous["mean_union_pool_size"]
        gained = current["mean_union_exposure"] - previous["mean_union_exposure"]
        current["marginal_exposure_pp_per_slot"] = (
            gained * 100 / added if added > 0 else None
        )
    return rows


def headroom(census: Census, family: str) -> dict[str, Any]:
    """Union ceiling and the addressable completion gap for one family."""
    cases = census.cases(family)
    union = {c for c in cases if census.exposing_arms[c]}
    grid: dict[str, Counter] = defaultdict(Counter)
    for case in cases:
        relations = census.case_relations[case]
        if COMPLETE in relations:
            state = "complete_ever_exposed"
        elif PARTIAL in relations:
            state = "partial_never_complete"
        else:
            state = "neither"
        grid[census.identifiability.get(case, "unmapped")][state] += 1
    robustness = Counter(len(census.exposing_arms[c]) for c in union)
    unique_full = grid.get("unique_full_reference", Counter())
    return {
        "addressable_completion_gap": unique_full["partial_never_complete"],
        "addressable_completion_gap_rate": (
            unique_full["partial_never_complete"] / len(cases)
        ),
        "by_identifiability": {k: dict(v) for k, v in sorted(grid.items())},
        "exposed_by_ge_4_arms": sum(v for k, v in robustness.items() if k >= 4),
        "exposed_by_one_arm_only": robustness.get(1, 0),
        "n_cases": len(cases),
        "union_complete_exposure": len(union),
        "union_complete_exposure_rate": len(union) / len(cases),
    }


def build(root: Path = Path(".")) -> dict[str, Any]:
    census = Census(root)
    report: dict[str, Any] = {
        "endpoint": "binary complete-equivalence boundary of the C0 three-model panel",
        "gold_injected_groups_excluded_from_unions": sorted(GOLD_INJECTED_GROUPS),
        "families": {},
        "schema": "slot-yield-diagnostic-v1",
        "truth_provenance": "model_panel_sensitivity_not_root",
    }
    for family in ("DA", "MCR"):
        fits = conversion_fits(census, family)
        clean = fits["excluding_weak_comparators_post_hoc"]
        family_report: dict[str, Any] = {
            "arms": arm_table(census, family),
            "conversion_vs_width_fits": fits,
            "headroom": headroom(census, family),
            "union_dose_response": union_dose_response(census, family),
        }
        if clean is not None:
            reference = max(
                (
                    row
                    for row in family_report["arms"]
                    if not row["gold_injected"] and row["n_served"] >= 200
                ),
                key=lambda row: row["exposure_rate"],
            )
            family_report["break_even_exposure_pp_per_slot"] = {
                "at_arm": reference["arm_id"],
                "exposure_rate": reference["exposure_rate"],
                "pool_size": reference["mean_pool_size"],
                "required_pp_per_slot": break_even(
                    clean["intercept"],
                    clean["slope_per_candidate"],
                    reference["mean_pool_size"],
                    reference["exposure_rate"] * 100,
                ),
            }
        report["families"][family] = family_report
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path("."), type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build(args.root)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
