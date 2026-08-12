import tarfile

from analysis.mechanism_v2.common import ROOT, file_sha256
from analysis.mechanism_v2.e14x_final_analysis import assemble, package


def test_final_decision_disables_old_call4_gate() -> None:
    out = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"
    result = assemble(out)
    assert result["decision"]["call4_default"] == "disabled"
    assert result["decisive_counts"]["upstream_identical_pairs"] == 0
    assert result["decisive_counts"]["strict_reference_discoveries"] == 0


def test_final_bundle_hash_and_members() -> None:
    out = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"
    archive = package(out)
    expected = (out / f"{archive.name}.sha256").read_text(encoding="utf-8").split()[0]
    assert expected == file_sha256(archive)
    with tarfile.open(archive, "r:gz") as stream:
        names = set(stream.getnames())
    assert {"REPORT.md", "analysis_summary.json", "manual_audit.jsonl"} <= names

