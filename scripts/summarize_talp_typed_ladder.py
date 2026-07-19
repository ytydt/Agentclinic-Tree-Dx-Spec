#!/usr/bin/env python3
"""Summarize completed typed ladder arms with case-cluster paired bootstrap."""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVALID_ARMS = {"multi_ontology_payload"}  # pre-fix SELECT gold-context leakage
FAMILY_CONFIG = {
    "typed": ("talp_discrim_typed_*_s*r0.json", "fixture_v2",
              "talp_typed_ladder_summary.json"),
    "p5typed": ("talp_discrim_p5typed_*_s*r0_dv2_p5.json", "fixture_v2",
                "talp_p5_typed_ladder_summary.json"),
    # P5KG outputs may carry an additional suffix after r0 (for example a
    # fixture/compiler version). Keep that suffix out of the arm name.
    "p5kg": ("talp_discrim_p5kg_*_s*r0*.json", "g0",
             "talp_p5kg_ladder_summary.json"),
    "p5kg_research": (
        "talp_discrim_p5kg_research_*_s*r0*.json", "g0",
        "talp_p5kg_research_ladder_summary.json"),
}


def _load_ci():
    spec = importlib.util.spec_from_file_location("talp_ci_mod", ROOT / "scripts/talp_ci.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_files(log_dir: Path, family: str) -> dict[str, list[Path]]:
    """Discover per-seed files and group them by ladder arm."""
    pattern, _, _ = FAMILY_CONFIG[family]
    grouped: dict[str, list[Path]] = {}
    prefix = f"talp_discrim_{family}_"
    for path in sorted(log_dir.glob(pattern)):
        name = path.name[len(prefix):] if path.name.startswith(prefix) else path.name
        arm = name.split("_s", 1)[0]
        if family == "p5kg" and arm.startswith("research_"):
            continue
        if arm in INVALID_ARMS:
            continue
        grouped.setdefault(arm, []).append(path)
    if family == "p5kg_research":
        # Reuse the frozen G0/G1 observations without copying or retagging them.
        for arm in ("g0", "g1"):
            baseline_paths = sorted(
                log_dir.glob(f"talp_discrim_p5kg_{arm}_s*r0*.json"))
            if baseline_paths:
                grouped[arm] = baseline_paths
    return grouped


def summarize_family(
    grouped: dict[str, list[Path]],
    *,
    family: str,
    baseline: str,
    n_boot: int,
) -> dict:
    """Summarize arms and paired deltas with case-cluster resampling."""
    ci = _load_ci()
    rows = {arm: ci._load_rows([str(p) for p in paths])
            for arm, paths in grouped.items()}
    result = {
        "family": family, "baseline": baseline,
        "arms": {}, "paired_delta": {}}
    rng = random.Random(0)
    for arm, arm_rows in rows.items():
        result["arms"][arm] = {
            "sampling": {
                "case_clusters": len(ci._clusters(arm_rows)),
                "seed_case_rows": len(arm_rows),
                "files": len(grouped[arm]),
            },
        }
        for metric_name, metric in ci.METRICS.items():
            rate, num, den = ci._rate(arm_rows, metric)
            lo, hi = ci._ci(ci._bootstrap(arm_rows, metric, n_boot, rng))
            result["arms"][arm][metric_name] = {
                "rate": rate, "num": num, "den": den, "ci": [lo, hi]}
    baseline_rows = rows.get(baseline, [])
    baseline_groups = ci._clusters(baseline_rows)
    for arm, arm_rows in rows.items():
        if arm == baseline or not baseline_rows:
            continue
        groups = ci._clusters(arm_rows)
        ids = sorted(set(baseline_groups) & set(groups))
        result["paired_delta"][arm] = {}
        if not ids:
            result["paired_delta"][arm]["error"] = "no shared case IDs"
            continue
        for metric_name, metric in ci.METRICS.items():
            base_rate, _, _ = ci._rate(baseline_rows, metric)
            arm_rate, _, _ = ci._rate(arm_rows, metric)
            samples = []
            for _ in range(n_boot):
                sampled = [ids[rng.randrange(len(ids))] for _ in ids]
                a = [r for cid in sampled for r in baseline_groups[cid]]
                b = [r for cid in sampled for r in groups[cid]]
                ra, _, da = ci._rate(a, metric)
                rb, _, db = ci._rate(b, metric)
                if da and db:
                    samples.append(rb - ra)
            lo, hi = ci._ci(samples)
            result["paired_delta"][arm][metric_name] = {
                "delta": arm_rate - base_rate, "ci": [lo, hi],
                "resolved": lo > 0 or hi < 0,
            }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--family", default="typed", choices=FAMILY_CONFIG)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--log-dir", type=Path, default=ROOT / "logs")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    _, default_baseline, default_output = FAMILY_CONFIG[args.family]
    baseline = args.baseline or default_baseline
    args.out = args.out or args.log_dir / default_output
    grouped = discover_files(args.log_dir, args.family)
    result = summarize_family(
        grouped, family=args.family, baseline=baseline, n_boot=args.n_boot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"arms={len(grouped)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
