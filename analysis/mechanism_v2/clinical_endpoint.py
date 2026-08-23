#!/usr/bin/env python3
"""A second ruler: the frozen clinical-complete relation, keyed by (case, label).

Every mechanism analysis in this directory has so far been scored with
`dc.match` (legacy chain), whose PPV against clinical completeness is 0.5648.
The clinical judgements needed to do better already exist and are **not** tied
to any arm: two frozen sources key a five-way relation on
`(case_key, canonical_label)`, so any arm that answered a label already judged
on that case can be re-scored with zero LLM calls.

Sources (both frozen, both read-only here):

- `CEILING_POOL_CENSUS/panel/three_model_adjudicated_panel.jsonl` — C0's blinded
  three-model panel over pool candidates, restricted to the occurrence ledger.
- `ALL_ARM_ENDPOINT_MIGRATION/final/five_endpoint_replay.jsonl` — the all-arm
  endpoint migration replay.

Key construction reuses `FrozenExactSynonymBridge` and the same
`relation_key(case_key, label, bridge)` semantics as the archived
`corelift_evaluate.py`, so a lookup here means the same thing it meant there.

Reliability, which every caller must carry: on the E2 hidden sentinels
(n=2601) the three-model panel scores exact accuracy 0.7082 and Gwet AC1 0.6544
on the five-way relation; only the degenerate `safe_exact` binary reaches 1.000.
The `complete_equivalent` / `partial_parent_or_component` boundary is precisely
the hard one. This is **model-panel sensitivity, not human root truth**, and the
800 cases are a repeatedly used development set: development, not confirmation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src", _ROOT / "analysis" / "backbone_v1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from analysis.mechanism_v2.common import FrozenExactSynonymBridge  # noqa: E402

PANEL = (
    _ROOT
    / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS/panel/three_model_adjudicated_panel.jsonl"
)
OCCURRENCE = (
    _ROOT
    / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS/design/occurrence_ledger.jsonl"
)
MIGRATION = (
    _ROOT
    / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/final/five_endpoint_replay.jsonl"
)
BRIDGE = _ROOT / "data/knowledge_raw/disease_name_bridge.json"

# `(r5 dataset key, r5 slice)` -> the `case_key` prefix used by both sources.
CASE_KEY_PREFIX = {
    ("da", "d2_seq100"): "DA_d2_seq100",
    ("da", "d2_heldout100"): "DA_d2_heldout100",
    ("da", "d2_heldout200b"): "DA_d2_heldout200b",
    ("mcr", "mcr_v1"): "MCR_v1_seq100",
    ("mcr", "mcr_v2"): "MCR_v2_seq100",
    ("mcr", "mcr_200b"): "MCR_seq200b",
}

COMPLETE = "complete_equivalent"
PARTIAL = "partial_parent_or_component"
# The remaining three plus `uncertain` are neither complete nor compatible.
WRONG = ("conflicting_subtype_or_scope", "not_equivalent", "manifestation_or_related")
RELATIONS = (COMPLETE, PARTIAL) + WRONG + ("uncertain",)


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


class ClinicalEndpoint:
    """Frozen `(case_key, canonical label)` -> five-way clinical relation."""

    def __init__(
        self,
        *,
        strict_sources: bool = True,
        panel: Path = PANEL,
        occurrence_ledger: Path = OCCURRENCE,
        migration: Path = MIGRATION,
        bridge: Path = BRIDGE,
    ) -> None:
        self.bridge = FrozenExactSynonymBridge(bridge)
        self._rel: dict[tuple[str, str], str] = {}
        self._src: dict[tuple[str, str], str] = {}
        self.conflicts: list[dict[str, str]] = []
        self.n_from: dict[str, int] = {}

        occurrence = {
            str(r["relation_id"])
            for r in _read_jsonl(occurrence_ledger)
            if r.get("relation_id")
        }
        # C0 panel first: it is the adjudicated source. The migration replay
        # then fills labels C0 never enumerated.
        self._ingest(
            panel,
            label_field="candidate_label",
            relation_fields=("final_relation", "model_panel_relation"),
            source="c0_three_model_panel",
            keep=lambda r: (not occurrence) or str(r.get("relation_id") or "") in occurrence,
        )
        self._ingest(
            migration,
            label_field="prediction_pre_projection",
            relation_fields=("clinical_relation",),
            source="all_arm_endpoint_migration",
            keep=lambda r: bool(r.get("served")),
        )
        if strict_sources and not self._rel:
            raise RuntimeError("no frozen clinical relations loaded")

    def _ingest(
        self,
        path: Path,
        *,
        label_field: str,
        relation_fields: tuple[str, ...],
        source: str,
        keep: Any,
    ) -> None:
        n = 0
        for row in _read_jsonl(path):
            if not keep(row):
                continue
            label = str(row.get(label_field) or "").strip()
            rel = ""
            for f in relation_fields:
                rel = str(row.get(f) or "").strip()
                if rel:
                    break
            case_key = str(row.get("case_key") or "")
            if not label or not rel or not case_key:
                continue
            key = (case_key, self.bridge.canonical_key(label))
            prior = self._rel.get(key)
            if prior is None:
                self._rel[key] = rel
                self._src[key] = source
                n += 1
            elif prior != rel:
                # Two frozen sources disagreeing on a boundary an endpoint reads
                # is not something to average. Drop it and report it, matching
                # `corelift_evaluate.load_clinical_reuse`.
                self.conflicts.append(
                    {
                        "case_key": key[0],
                        "label": key[1],
                        "kept": prior,
                        "dropped": rel,
                        "source": source,
                    }
                )
        self.n_from[source] = n

    def drop_conflicts(self) -> None:
        for c in self.conflicts:
            self._rel.pop((c["case_key"], c["label"]), None)

    # --- lookup -------------------------------------------------------
    def case_key(self, dkey: str, sl: str, cid: str) -> Optional[str]:
        pre = CASE_KEY_PREFIX.get((dkey, sl))
        return f"{pre}/{cid}" if pre else None

    def relation(self, dkey: str, sl: str, cid: str, label: str) -> Optional[str]:
        ck = self.case_key(dkey, sl, cid)
        if not ck or not str(label or "").strip():
            return None
        return self._rel.get((ck, self.bridge.canonical_key(str(label))))

    def is_complete(self, dkey: str, sl: str, cid: str, label: str) -> bool:
        return self.relation(dkey, sl, cid, label) == COMPLETE

    def is_complete_or_partial(self, dkey: str, sl: str, cid: str, label: str) -> bool:
        return self.relation(dkey, sl, cid, label) in (COMPLETE, PARTIAL)

    def any_complete(
        self, dkey: str, sl: str, cid: str, labels: Iterable[str]
    ) -> bool:
        return any(self.is_complete(dkey, sl, cid, x) for x in labels)

    def coverage(
        self, dkey: str, sl: str, cid: str, labels: Iterable[str]
    ) -> tuple[int, int]:
        labels = [x for x in labels if str(x or "").strip()]
        got = sum(1 for x in labels if self.relation(dkey, sl, cid, x) is not None)
        return got, len(labels)

    def audit(self) -> dict[str, Any]:
        return {
            "n_relations": len(self._rel),
            "n_from_source": dict(self.n_from),
            "n_cross_source_conflicts": len(self.conflicts),
            "bridge_sha256": self.bridge.sha256,
            "reliability": {
                "e2_hidden_sentinels_n": 2601,
                "three_model_panel_exact_accuracy": 0.7082,
                "three_model_panel_gwet_ac1": 0.6544,
                "safe_exact_binary_exact_accuracy": 1.0,
                "truth_tier": "model_panel_sensitivity_not_human_root",
                "cohort": "800-case development set; development not confirmation",
            },
        }


TASK_CARDS = (
    _ROOT / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/design/blinded_task_cards.jsonl"
)
TASK_INDEX = (
    _ROOT / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/design/task_index.jsonl"
)
TASK_RESULTS = (
    _ROOT
    / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/task_evaluator/task_results.jsonl"
)


class TaskEndpoint:
    """Frozen `(family, case_key, canonical label)` -> official task correctness.

    DA is option accuracy after gold-blind top-1 -> source-option projection;
    MCR is the frozen Prompt-7 judgement. Like the clinical relation these are
    keyed by case and label rather than by arm, so archived arms can be re-scored
    without calls -- but **coverage is partial and arm-dependent** (roughly
    0.66-0.82 of champions), because a `(case, label)` pair only has a verdict if
    it entered the CoreLift migration's task index. Never compare raw rates
    across arms: restrict to commonly-judged cases and pair them.
    """

    def __init__(
        self,
        *,
        cards: Path = TASK_CARDS,
        index: Path = TASK_INDEX,
        results: Path = TASK_RESULTS,
        bridge: Path = BRIDGE,
    ) -> None:
        self.bridge = FrozenExactSynonymBridge(bridge)
        card_by_id = {str(r["blind_task_id"]): r for r in _read_jsonl(cards)}
        res_by_id = {
            str(r["task_id"]): r for r in _read_jsonl(results) if r.get("success")
        }
        self._task: dict[tuple[str, str, str], bool] = {}
        conflicts: set[tuple[str, str, str]] = set()
        for row in _read_jsonl(index):
            res = res_by_id.get(str(row.get("task_id")))
            card = card_by_id.get(str(row.get("blind_task_id")))
            if res is None or card is None:
                continue
            cand = next(
                (
                    c
                    for c in (card.get("candidate_registry") or [])
                    if str(c.get("candidate_id")) == str(row.get("candidate_id"))
                ),
                None,
            )
            label = str((cand or {}).get("label") or "").strip()
            if not label:
                continue
            key = (
                str(row["benchmark_family"]).upper(),
                str(row["case_key"]),
                self.bridge.canonical_key(label),
            )
            value = bool(res.get("task_correct"))
            if key in self._task and self._task[key] != value:
                conflicts.add(key)
            self._task.setdefault(key, value)
        for key in conflicts:
            self._task.pop(key, None)
        self.n_conflicts = len(conflicts)

    def correct(self, dkey: str, sl: str, cid: str, label: str) -> Optional[bool]:
        pre = CASE_KEY_PREFIX.get((dkey, sl))
        if not pre or not str(label or "").strip():
            return None
        return self._task.get(
            (dkey.upper(), f"{pre}/{cid}", self.bridge.canonical_key(str(label)))
        )

    def audit(self) -> dict[str, Any]:
        return {
            "n_task_verdicts": len(self._task),
            "n_conflicts_dropped": self.n_conflicts,
            "coverage_warning": (
                "partial and arm-dependent (~0.66-0.82 of champions); "
                "never compare raw rates across arms"
            ),
        }


if __name__ == "__main__":
    print(json.dumps(ClinicalEndpoint().audit(), indent=2, ensure_ascii=False))
    print(json.dumps(TaskEndpoint().audit(), indent=2, ensure_ascii=False))
