import json
import unittest
from pathlib import Path

from analysis.mechanism_v2.mas_single_agent_atom_census import build


SOURCE_COMMIT = "c39a19d738676f2838994727608291398802e9a1"


class MasSingleAgentAtomCensusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[1]
        cls.replay = (
            cls.repo
            / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/"
            "unified_800/five_endpoint_replay.jsonl"
        )
        cls.artifact = (
            cls.repo
            / "analysis/mechanism_v2/results/MAS_SINGLE_AGENT_ATOM_RESEARCH/"
            "backbone_atom_census.json"
        )
        cls.result = build(cls.repo, SOURCE_COMMIT, cls.replay)

    def test_committed_artifact_is_exact_rebuild(self) -> None:
        expected = json.loads(self.artifact.read_text(encoding="utf-8"))
        self.assertEqual(self.result, expected)

    def test_census_contract_and_key_mechanism_counts(self) -> None:
        self.assertEqual(
            self.result["schema_version"],
            "mas-single-agent-atom-census-v2-public-aggregate",
        )
        self.assertFalse(
            self.result["publication_contract"]["case_level_records_included"]
        )
        self.assertNotIn("unique_correct_cases", self.result)
        self.assertEqual(self.result["cases_n"], 800)
        self.assertEqual(self.result["case_arm_rows_n"], 2400)
        self.assertEqual(self.result["provenance"]["files_verified"], 2400)
        self.assertTrue(self.result["provenance"]["source_tree_verified"])

        triad = self.result["triad"]
        self.assertEqual(triad["oracle_any_complete_n"], 155)
        self.assertEqual(triad["best_single_complete_n"], 122)
        self.assertEqual(triad["oracle_minus_best_single_n"], 33)
        self.assertEqual(triad["wrong_consensus_suppression_risk_n"], 27)
        self.assertEqual(triad["unique_correct_with_label_in_any_wrong_pool_n"], 18)
        self.assertEqual(triad["unique_correct_with_label_in_both_wrong_pools_n"], 8)

        self.assertEqual(
            self.result["by_benchmark_family"]["DA"]["oracle_minus_best_single_n"],
            11,
        )
        self.assertEqual(
            self.result["by_benchmark_family"]["MCR"]["oracle_minus_best_single_n"],
            22,
        )

    def test_atom_channel_findings(self) -> None:
        per_arm = self.result["per_arm"]
        self.assertEqual(per_arm["forest"]["clinical_complete_n"], 107)
        self.assertEqual(per_arm["impc"]["clinical_complete_n"], 98)
        self.assertEqual(per_arm["collapse3c"]["clinical_complete_n"], 122)
        self.assertEqual(
            per_arm["impc"]["channel_structure"][
                "merge_vote_exceeds_unique_view_count_n"
            ],
            127,
        )
        self.assertEqual(
            per_arm["collapse3c"]["channel_structure"]["with_against_fact_ids_n"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
