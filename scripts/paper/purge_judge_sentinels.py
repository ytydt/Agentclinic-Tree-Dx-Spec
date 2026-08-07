#!/usr/bin/env python3
"""Remove exhausted-retry sentinels from second-judge caches and the case
scores derived from them, so the affected cases are re-requested instead of
being carried as a zero-coverage verdict.

Usage: purge_judge_sentinels.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "[Unable to generate"

TARGETS = [
    ROOT
    / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate"
    / "official_eval_llm_compat_rr_dsv4f",
]
TARGETS += sorted(
    (ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1").glob(
        "*/replicate_01/annotate/official_eval_llm_rr_dsv4f"
    )
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes")
    args = ap.parse_args()

    grand = {"caches": 0, "entries": 0, "scores": 0}
    for eval_dir in TARGETS:
        cache_path = eval_dir / "judge_cache.json"
        if not cache_path.is_file():
            continue
        cache = json.loads(cache_path.read_text())
        bad_keys = [
            k
            for k, v in cache.items()
            if isinstance(v, dict) and str(v.get("text", "")).startswith(SENTINEL)
        ]
        if not bad_keys:
            continue

        # A sentinel can corrupt either endpoint of a case, and the stored score
        # does not record which verdict it came from. Drop every score in an
        # affected directory and let the run rebuild them: the surviving cache
        # entries are replayed without a new call, so only the purged prompts
        # are re-requested.
        scores_dir = eval_dir / "case_scores"
        bad_scores = sorted(scores_dir.glob("*.json"))

        label = eval_dir.relative_to(ROOT)
        print(
            "%-96s sentinels=%3d  scores_to_drop=%3d"
            % (str(label), len(bad_keys), len(bad_scores))
        )
        grand["caches"] += 1
        grand["entries"] += len(bad_keys)
        grand["scores"] += len(bad_scores)

        if not args.apply:
            continue

        shutil.copy2(cache_path, cache_path.with_suffix(".json.presentinel"))
        for k in bad_keys:
            cache.pop(k, None)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
        for path in bad_scores:
            path.unlink()

    print(
        "\n%s caches=%d sentinel_entries=%d case_scores_dropped=%d"
        % (
            "[applied]" if args.apply else "[dry-run]",
            grand["caches"],
            grand["entries"],
            grand["scores"],
        )
    )


if __name__ == "__main__":
    main()
