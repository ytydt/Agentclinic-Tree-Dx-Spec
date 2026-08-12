from analysis.mechanism_v2.e14x_manual_adjudication import MANUAL, run
from analysis.mechanism_v2.common import ROOT


def test_all_frozen_manual_cases_are_covered() -> None:
    assert len(MANUAL) == 56
    assert MANUAL["MCR_v2_seq100/213"]["observed_gate_utility"] == "repair"
    assert MANUAL["MCR_v2_seq100/233"]["clinical_adaptive_equivalence"] == "yes"


def test_root_manual_summary_matches_expected_queue() -> None:
    out = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"
    if not (out / "manual_audit_queue.jsonl").exists():
        return
    summary = run(out)
    assert summary["manual_case_n"] == 56
    assert summary["triggered_champion_flip_n"] == 34
    assert sum(summary["triggered_champion_flips"]["observed_gate_utility_counts"].values()) == 34

