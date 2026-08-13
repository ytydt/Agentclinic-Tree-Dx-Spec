import tarfile

from analysis.mechanism_v2.common import ROOT, file_sha256
from analysis.mechanism_v2.e14x_final_analysis import assemble, package


def test_final_decision_disables_old_call4_gate() -> None:
    out = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"
    result = assemble(out)
    assert result["decision"]["call4_default"] == "disabled"
    assert result["decisive_counts"]["upstream_identical_pairs"] == 0
    assert result["decisive_counts"]["safe_exact_reference_discoveries"] == 0
    assert set(result["primary_conservative_gate"]["da_option_projection"]) >= {
        "lite_task_n",
        "adaptive_task_n",
        "not_pooled_with_safe_exact_or_clinical_endpoints",
    }

    def active_strict_keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if "strict" in key and key != "historical_strict_fields_mean":
                    yield key
                yield from active_strict_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from active_strict_keys(nested)

    assert list(active_strict_keys(result)) == []

    def active_unscoped_clinical_keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {
                    "clinically_complete_adaptive_n",
                    "clinically_complete_lite_n",
                    "clinical_direction",
                    "clinical_direction_counts",
                    "clinical_adaptive_equivalence",
                    "clinical_lite_equivalence",
                }:
                    yield key
                yield from active_unscoped_clinical_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from active_unscoped_clinical_keys(nested)

    assert list(active_unscoped_clinical_keys(result)) == []
    scope = result["root_manual_audit"]["targeted_root_review_scope_contract"]
    assert scope["reviewed_case_n"] == 56
    assert scope["full_case_census"] is False
    assert scope["capability_leaderboard_ingestion_allowed"] is False


def test_final_bundle_hash_and_members() -> None:
    out = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"
    archive = package(out)
    expected = (out / f"{archive.name}.sha256").read_text(encoding="utf-8").split()[0]
    assert expected == file_sha256(archive)
    with tarfile.open(archive, "r:gz") as stream:
        names = set(stream.getnames())
    assert {"REPORT.md", "analysis_summary.json", "manual_audit.jsonl"} <= names
