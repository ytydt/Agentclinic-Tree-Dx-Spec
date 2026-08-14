import json
import subprocess
from pathlib import Path

import pytest

from analysis.mechanism_v2.ceiling_external_confirmation import (
    CaseRecord,
    ExposureRecord,
    _execution_reference,
    _git_state,
    audit_case_overlap,
    build_freeze,
    inspect_pinned_artifact,
    load_mcr_test_cases,
    mask_answer_cues,
    paired_sample_size,
    read_gate_result,
    scan_git_history,
)


def test_audit_output_is_not_misclassified_as_split_execution():
    assert not _execution_reference({
        "path": "analysis/mechanism_v2/results/CEILING_EXTERNAL_CONFIRMATION/scope_audit.json"
    })
    assert _execution_reference({"path": "analysis/mechanism_v2/results/E99/run.jsonl"})


def test_git_state_resolves_short_architecture_commit(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Audit Test"], cwd=tmp_path, check=True)
    (tmp_path / "x").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "x"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    state = _git_state(tmp_path, head[:9])
    assert state["architecture_commit"] == head
    assert state["passed"] is True


def test_scope_loader_is_outcome_ungated(tmp_path: Path):
    raw = tmp_path / "test.jsonl"
    raw.write_text(
        json.dumps({
            "Unnamed: 0": 9,
            "case_prompt": "A patient has fever and a new murmur.",
            "final_diagnosis": "infective endocarditis",
            "pmcid": "PMC12345",
            "doi": "https://doi.org/10.1000/ABC.1",
        }) + "\n",
        encoding="utf-8",
    )
    rows = load_mcr_test_cases(raw)
    assert [row.case_key for row in rows] == ["MCR_test/9"]
    assert rows[0].pmcid == "PMC12345"
    assert rows[0].doi == "10.1000/abc.1"


def test_cue_masking_removes_title_gold_and_conclusion():
    case = CaseRecord(
        "MCR_test/1",
        "1",
        "A report titled Zebra Syndrome Case. Final diagnosis was Zebra syndrome. What is most likely?",
        "Zebra syndrome",
        title="Zebra Syndrome Case",
    )
    masked = mask_answer_cues(case)
    assert "zebra syndrome" not in masked["masked_text"].casefold()
    assert set(masked["rules"]) >= {"source_title_literal", "gold_literal"}
    assert masked["unresolved"] == []


def test_overlap_detects_identifiers_exact_and_near():
    base = "patient has progressive weakness elevated creatine kinase and a characteristic muscle biopsy finding"
    cases = [
        CaseRecord("MCR_test/a", "a", base, "disease a", pmcid="PMC111"),
        CaseRecord("MCR_test/b", "b", base + " after several months", "disease b"),
        CaseRecord("MCR_test/c", "c", "entirely unrelated short clinical vignette", "disease c"),
    ]
    exposures = [
        ExposureRecord("dev.json", "x", base, pmcid="PMC111"),
    ]
    audit = audit_case_overlap(cases, exposures, near_threshold=0.70)
    assert audit["n_excluded"] == 2
    by_case = {row["case_key"]: set(row["match_kinds"]) for row in audit["matches"]}
    assert {"pmcid", "exact_text_hash"} <= by_case["MCR_test/a"]
    assert "near_text_sketch" in by_case["MCR_test/b"]
    assert "MCR_test/c" not in by_case


def test_paired_power_uses_discordance_and_missingness():
    plan = paired_sample_size(min_effect=0.05, discordance=0.12, missingness=0.10)
    assert plan["complete_pairs_required"] == 375
    assert plan["enrolled_cases_required"] == 416
    with pytest.raises(ValueError):
        paired_sample_size(min_effect=0.10, discordance=0.05)


def test_gate_reader_fails_closed(tmp_path: Path):
    passed = tmp_path / "passed.json"
    passed.write_text(json.dumps({"gates": {"static": {"status": "GO", "passed": True}}}), encoding="utf-8")
    assert read_gate_result(passed, "static")["passed"] is True

    conflicting = tmp_path / "conflicting.json"
    conflicting.write_text(json.dumps({"active": {"status": "GO", "passed": False}}), encoding="utf-8")
    result = read_gate_result(conflicting, "active")
    assert result["passed"] is False
    assert result["reason"] == "conflicting_gate_fields"
    assert read_gate_result(None, "static")["passed"] is False


def test_manifest_requires_cc_by_dataset_note_and_local_file(tmp_path: Path):
    raw = tmp_path / "test.jsonl"
    raw.write_text("{}\n", encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"artifacts": [{
        "dataset_id": "medcasereasoning",
        "relative_path": "raw/test-00000-of-00001.parquet",
        "sha256": digest,
        "bytes": raw.stat().st_size,
        "rows": 897,
        "revision": "frozen",
        "license_note": "Dataset CC BY 4.0; code MIT.",
    }]}), encoding="utf-8")
    assert inspect_pinned_artifact(tmp_path, manifest, raw)["passed"] is True

    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["artifacts"][0]["license_note"] = "HF card declares MIT"
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    result = inspect_pinned_artifact(tmp_path, manifest, raw)
    assert result["passed"] is False
    assert "license_note_mislabels_dataset_as_code_license" in result["reasons"]


def test_git_history_finds_identifier_in_deleted_log(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Audit Test"], cwd=tmp_path, check=True)
    log = tmp_path / "logs" / "old" / "case_results.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"case_text": "old exposed case", "pmcid": "PMC987654"}) + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "expose"], cwd=tmp_path, check=True)
    log.unlink()
    subprocess.run(["git", "add", "-u"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "remove"], cwd=tmp_path, check=True)

    hits, records, coverage = scan_git_history(tmp_path, {"MCR_test/1:pmcid": "PMC987654"})
    assert coverage["performed"] is True
    assert any(hit["needle"] == "MCR_test/1:pmcid" for hit in hits)
    assert any(record.pmcid == "PMC987654" for record in records)


def test_freeze_never_upgrades_same_dataset_to_source_external(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Audit Test"], cwd=tmp_path, check=True)
    raw = tmp_path / "test.jsonl"
    raw.write_text(json.dumps({
        "id": 1,
        "case_prompt": "A source-independent-looking but same-dataset case prompt.",
        "final_diagnosis": "example diagnosis",
        "pmcid": "PMC555555",
    }) + "\n", encoding="utf-8")
    import hashlib
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"artifacts": [{
        "dataset_id": "medcasereasoning",
        "relative_path": "raw/test-00000-of-00001.parquet",
        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "bytes": raw.stat().st_size,
        "rows": 897,
        "license_note": "Dataset CC BY 4.0; code MIT.",
    }]}), encoding="utf-8")
    gate = tmp_path / "static_gate.json"
    gate.write_text(json.dumps({"static": {"decision": "GO"}}), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "freeze inputs"], cwd=tmp_path, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()

    report = build_freeze(
        repo_root=tmp_path,
        raw_path=raw,
        manifest_path=manifest,
        static_gate=gate,
        architecture_commit=head,
        exposure_paths=[],
        include_git_history=False,
    )
    assert report["scientific_scope"]["label"] == "same-dataset independent-split confirmation"
    assert report["scientific_scope"]["source_external"] is False
    assert report["scientific_scope"]["time_external"] is False
    assert report["scientific_scope"]["chapter12_source_time_external_confirmation_closed"] is False
    assert report["entry_decision"]["decision"] == "NO_ENTRY"

    waived = build_freeze(
        repo_root=tmp_path,
        raw_path=raw,
        manifest_path=manifest,
        static_gate=gate,
        architecture_commit=head,
        exposure_paths=[],
        include_git_history=False,
        scope_waiver=True,
    )
    assert waived["entry_decision"]["decision"] == "NOT_EXECUTED_SCOPE_WAIVER"
    assert waived["entry_decision"]["allowed"] is False
    assert waived["entry_decision"]["underlying_decision_without_waiver"] == "NO_ENTRY"
    assert waived["entry_decision"]["underlying_no_entry_reasons"]
    assert waived["scientific_scope"]["chapter12_source_time_external_confirmation_closed"] is False
