"""Unit tests for E7 registry semantics (stdlib unittest, no pytest required)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analysis.mechanism_v2.common import FrozenExactSynonymBridge
from analysis.mechanism_v2.e7_registry_replay import (
    ARM_EXACT,
    ARM_LEGACY,
    ARM_TYPED,
    Occurrence,
    build_registry,
    cross_identity_evidence_transfers,
    unsafe_merge_pairs,
)


class RegistryReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.bridge_path = Path(self.temp.name) / "bridge.json"
        self.bridge_path.write_text(
            json.dumps(
                {
                    "by_alias": {
                        "sle": "systemic lupus erythematosus",
                        "systemic lupus erythematosus": "systemic lupus erythematosus",
                        "arvc": "arrhythmogenic right ventricular cardiomyopathy",
                        "arrhythmogenic right ventricular cardiomyopathy": "arrhythmogenic right ventricular cardiomyopathy",
                    },
                    "by_canonical": {
                        "systemic lupus erythematosus": {
                            "aliases": ["SLE"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.bridge = FrozenExactSynonymBridge(self.bridge_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def occurrence(ordinal: int, name: str, span: str) -> Occurrence:
        return Occurrence(
            occurrence_id=f"O{ordinal:03d}",
            name=name,
            view=f"v{ordinal}",
            ordinal=ordinal,
            support_spans=(span,),
            contradict_spans=(),
            axis_node="axis",
            protected_reason="",
        )

    def test_substring_folds_scope_but_safe_registry_does_not(self) -> None:
        occurrences = [
            self.occurrence(1, "cutaneous metastasis", "skin lesion"),
            self.occurrence(
                2, "cutaneous metastasis of breast carcinoma", "GATA3 positive"
            ),
        ]
        legacy = build_registry(
            occurrences, arm=ARM_LEGACY, bridge=self.bridge
        )
        exact = build_registry(occurrences, arm=ARM_EXACT, bridge=self.bridge)
        typed = build_registry(occurrences, arm=ARM_TYPED, bridge=self.bridge)
        self.assertEqual(len(legacy.concepts), 1)
        self.assertEqual(len(exact.concepts), 2)
        self.assertEqual(len(typed.concepts), 2)
        self.assertEqual(len(unsafe_merge_pairs(legacy, self.bridge)), 1)
        self.assertEqual(len(typed.relations), 1)
        self.assertEqual(
            typed.relations[0]["relation"], "non_equivalent_lexical_relation"
        )
        self.assertEqual(typed.relations[0]["clinical_direction"], "unresolved")
        self.assertEqual(
            sum(
                row["foreign_support_spans_n"]
                for row in cross_identity_evidence_transfers(legacy, self.bridge)
            ),
            2,
        )

    def test_exact_frozen_alias_merges(self) -> None:
        occurrences = [
            self.occurrence(1, "SLE", "malar rash"),
            self.occurrence(2, "systemic lupus erythematosus", "anti-dsDNA"),
        ]
        exact = build_registry(occurrences, arm=ARM_EXACT, bridge=self.bridge)
        self.assertEqual(len(exact.concepts), 1)
        self.assertEqual(unsafe_merge_pairs(exact, self.bridge), [])

    def test_explicit_parenthetical_initialism_is_safe_equivalence(self) -> None:
        self.assertTrue(
            self.bridge.equivalent(
                "Systemic lupus erythematosus",
                "Systemic lupus erythematosus (SLE)",
            )
        )
        self.assertTrue(
            self.bridge.equivalent(
                "Arrhythmogenic right ventricular cardiomyopathy",
                "Arrhythmogenic right ventricular cardiomyopathy (ARVC)",
            )
        )
        self.assertFalse(
            self.bridge.equivalent(
                "Follicular lymphoma", "Follicular lymphoma (stage IVB)"
            )
        )

    def test_typed_relations_do_not_transfer_evidence(self) -> None:
        occurrences = [
            self.occurrence(1, "pneumonia", "fever"),
            self.occurrence(2, "organizing pneumonia", "reverse halo"),
        ]
        typed = build_registry(occurrences, arm=ARM_TYPED, bridge=self.bridge)
        self.assertEqual(len(typed.concepts), 2)
        self.assertEqual(cross_identity_evidence_transfers(typed, self.bridge), [])
        supports = {c.preferred_name: c.support_spans for c in typed.concepts}
        self.assertEqual(supports["pneumonia"], ["fever"])
        self.assertEqual(supports["organizing pneumonia"], ["reverse halo"])

    def test_legacy_exact_preferred_index_precedes_substring_scan(self) -> None:
        occurrences = [
            self.occurrence(1, "Discoid lupus erythematosus", "d1"),
            self.occurrence(2, "Cutaneous lupus erythematosus", "c1"),
            self.occurrence(3, "lupus erythematosus", "broad"),
            self.occurrence(4, "cutaneous lupus erythematosus", "c2"),
        ]
        legacy = build_registry(occurrences, arm=ARM_LEGACY, bridge=self.bridge)
        self.assertEqual(len(legacy.concepts), 2)
        self.assertEqual(
            legacy.concepts[0].member_names,
            ["Discoid lupus erythematosus", "lupus erythematosus"],
        )
        self.assertEqual(
            legacy.concepts[1].member_names,
            ["Cutaneous lupus erythematosus", "cutaneous lupus erythematosus"],
        )


if __name__ == "__main__":
    unittest.main()
