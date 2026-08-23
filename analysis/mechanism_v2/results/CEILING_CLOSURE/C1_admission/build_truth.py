#!/usr/bin/env python3
"""Project the C0 model-panel census onto C1's candidate IDs.

The census universe is keyed by ``(case_key, normalized label)`` and already
includes the E4 fixed union pools that C1 draws from, but it numbers candidates
in its own ``C###`` namespace while C1 uses the E4 ``D#`` namespace.  This joins
the two on the preregistered key and emits the per-candidate relation ledger the
admission analyser consumes.

The join reads only case keys and candidate labels.  It never reads an arm, a
selector response or a Top-1 outcome, so it cannot be tuned to a result.  A
candidate with no census row, or one the panel left ``uncertain``, becomes ``U``
and is therefore not clinical-complete, never silently dropped.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analysis.mechanism_v2.common import file_sha256, normalize_label  # noqa: E402
from analysis.mechanism_v2.online_runner import canonical_sha256, read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

C1 = ROOT / "analysis/mechanism_v2/results/CEILING_CLOSURE/C1_admission"
CENSUS = ROOT / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS"
PANEL = CENSUS / "panel/three_model_adjudicated_panel.jsonl"

RELATION_MAP = {
    "complete_equivalent": "C",
    "partial_parent_or_component": "P",
    "conflicting_subtype_or_scope": "X",
    "manifestation_or_related": "M",
    "not_equivalent": "N",
    "uncertain": "U",
}


def build() -> dict:
    panel = read_jsonl(PANEL)
    by_key: dict[tuple[str, str], str] = {}
    collisions = 0
    for row in panel:
        key = (str(row["case_key"]), str(row.get("normalized_label") or ""))
        relation = RELATION_MAP.get(str(row.get("final_relation") or ""), "U")
        if key in by_key and by_key[key] != relation:
            # Two census rows for one normalized label must not silently pick a
            # winner; the ambiguity resolves to uncertain.
            collisions += 1
            by_key[key] = "U"
        else:
            by_key.setdefault(key, relation)

    cases = read_jsonl(C1 / "freeze/cases.jsonl")
    rows: list[dict] = []
    matched = 0
    for case in cases:
        case_key = str(case["case_key"])
        for candidate in case["proposal_union"]:
            label = str(candidate.get("label") or "")
            key = (case_key, normalize_label(label))
            relation = by_key.get(key)
            if relation is None:
                relation = "U"
            else:
                matched += 1
            rows.append(
                {
                    "case_key": case_key,
                    "candidate_id": str(candidate["candidate_id"]),
                    "candidate_label": label,
                    "normalized_label": key[1],
                    "adjudicated_relation": relation,
                    "matched_census_row": by_key.get(key) is not None,
                }
            )
    rows.sort(key=lambda row: (row["case_key"], row["candidate_id"]))
    truth_path = C1 / "truth/admission_truth.jsonl"
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(truth_path, rows)

    distribution: dict[str, int] = {}
    for row in rows:
        distribution[row["adjudicated_relation"]] = distribution.get(row["adjudicated_relation"], 0) + 1
    manifest = {
        "schema": "ceiling_closure_c1_truth_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "product": "admission_truth",
        "truth_provenance": "three_model_adjudicated_panel_sensitivity",
        "join_key": "(case_key, normalized label) per preregistration 3.1",
        "row_n": len(rows),
        "matched_census_rows": matched,
        "unmatched_to_uncertain": len(rows) - matched,
        "normalized_label_collisions_to_uncertain": collisions,
        "relation_distribution": dict(sorted(distribution.items())),
        "truth_file_sha256": file_sha256(truth_path),
        "truth_rows_sha256": canonical_sha256(rows),
        "input_files": [
            {"path": str(PANEL.relative_to(ROOT)), "sha256": file_sha256(PANEL)},
            {
                "path": str((C1 / "freeze/cases.jsonl").relative_to(ROOT)),
                "sha256": file_sha256(C1 / "freeze/cases.jsonl"),
            },
        ],
        "caveat": (
            "C0 is NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY. Only the "
            "complete/not-complete boundary met its reliability gate "
            "(0.9857 exact, AC1 0.9843); the five-way fine taxonomy did not "
            "(0.7210 exact against 0.80). This ledger is therefore usable for "
            "the clinical-complete endpoint and not for fine-relation claims."
        ),
    }
    atomic_json(C1 / "truth/admission_truth.manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True))
