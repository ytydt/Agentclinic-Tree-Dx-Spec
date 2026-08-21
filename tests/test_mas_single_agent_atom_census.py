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
            "mas-single-agent-atom-census-v4-multistance",
        )
        self.assertTrue(
            self.result["publication_contract"]["case_level_records_included"]
        )
        self.assertEqual(len(self.result["unique_correct_cases"]), 51)
        self.assertEqual(len(self.result["four_atom_unique_correct_cases"]), 38)
        self.assertTrue(
            all(
                set(row["predictions"]) == {"forest", "impc", "collapse3c"}
                and set(row["relations"]) == {"forest", "impc", "collapse3c"}
                for row in self.result["unique_correct_cases"]
            )
        )
        self.assertEqual(self.result["cases_n"], 800)
        self.assertEqual(self.result["case_arm_rows_n"], 3200)
        self.assertEqual(self.result["provenance"]["files_verified"], 3200)
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

        four_atom = self.result["four_atom"]
        self.assertEqual(four_atom["oracle_any_complete_n"], 165)
        self.assertEqual(four_atom["best_single_complete_n"], 122)
        self.assertEqual(four_atom["oracle_minus_best_single_n"], 43)
        self.assertEqual(
            four_atom["unique_correct_atom_n"],
            {"forest": 5, "impc": 8, "collapse3c": 15, "multistance": 10},
        )
        self.assertEqual(
            four_atom["wrong_plurality_or_tie_suppression_risk_n"], 29
        )
        self.assertEqual(
            self.result["per_arm"]["multistance"]
            ["four_atom_wrong_plurality_or_tie_suppression_risk_n"],
            7,
        )
        self.assertEqual(
            self.result["multistance_incremental_over_triad"]
            ["four_atom_oracle_minus_triad_oracle_n"],
            10,
        )

    def test_atom_channel_findings(self) -> None:
        per_arm = self.result["per_arm"]
        self.assertEqual(per_arm["forest"]["clinical_complete_n"], 107)
        self.assertEqual(per_arm["impc"]["clinical_complete_n"], 98)
        self.assertEqual(per_arm["collapse3c"]["clinical_complete_n"], 122)
        self.assertEqual(per_arm["multistance"]["clinical_complete_n"], 121)
        self.assertEqual(per_arm["multistance"]["safe_exact_n"], 69)
        self.assertEqual(per_arm["multistance"]["legacy_chain_n"], 181)
        self.assertEqual(per_arm["multistance"]["task_n"], 360)
        self.assertAlmostEqual(per_arm["multistance"]["mean_llm_calls"], 5.1725)
        self.assertEqual(
            per_arm["multistance"]["llm_call_distribution"], {"5": 662, "6": 138}
        )
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
        self.assertEqual(
            per_arm["multistance"]["channel_structure"]["multi_stance_candidates_n"],
            2511,
        )
        self.assertEqual(
            self.result["pairwise"]["collapse3c__multistance"]
            ["exact_champion_agreement_n"],
            546,
        )
        increment = self.result["multistance_incremental_over_triad"]
        self.assertEqual(increment["multistance_rescue_over_collapse"], 21)
        self.assertEqual(increment["multistance_loss_against_collapse"], 22)
        self.assertEqual(increment["rescue_champion_with_commit_provenance"], 20)
        self.assertEqual(increment["loss_champion_with_commit_provenance"], 22)
        self.assertEqual(
            increment["multistance_only_complete_champion_with_commit_provenance_n"],
            10,
        )
        span_reuse = increment["span_reuse_diagnostic"]
        self.assertEqual(span_reuse["support_span_entries_n"], 16204)
        self.assertEqual(
            span_reuse["support_entries_exact_raw_span_used_by_other_candidate_n"],
            13689,
        )
        self.assertEqual(
            span_reuse["support_entries_normalized_span_used_by_other_candidate_n"],
            13701,
        )
        self.assertEqual(
            span_reuse[
                "candidate_rows_same_exact_raw_span_in_support_and_against_n"
            ],
            240,
        )
        self.assertEqual(
            span_reuse[
                "candidate_rows_same_normalized_span_in_support_and_against_n"
            ],
            241,
        )


if __name__ == "__main__":
    unittest.main()
