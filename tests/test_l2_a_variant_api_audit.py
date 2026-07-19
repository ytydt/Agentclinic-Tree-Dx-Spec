from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit_l2_a_variant_api as audit  # noqa: E402


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class FakeClient:
    temperature = 0.0

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call_module(self, module: str, _prompt: str, payload: dict) -> dict:
        self.calls.append((module, payload))
        units = payload["units"]
        if module.endswith("LeafQuality"):
            return {
                "assessments": [
                    {
                        "unit_id": row["unit_id"],
                        "is_specific_disease": row["leaf_label"] == "Disease A",
                        "is_parent_valid": row["leaf_label"] == "Disease A",
                        "rationale": "fake leaf review",
                    }
                    for row in units
                ]
            }
        if module.endswith("SemanticCluster"):
            return {
                "assignments": [
                    {
                        "unit_id": row["unit_id"],
                        "semantic_cluster_id": f"cluster-{index}",
                        "rationale": "fake cluster review",
                    }
                    for index, row in enumerate(units)
                ]
            }
        if module.endswith("GoldMatch"):
            return {
                "matches": [
                    {
                        "unit_id": row["unit_id"],
                        "matches_gold": row["leaf_label"] == "Disease A",
                        "rationale": "fake gold review",
                    }
                    for row in units
                ]
            }
        raise AssertionError(module)


def _args(tmp_path: Path, stage: str):
    args = audit.build_parser().parse_args([stage])
    output = tmp_path / "audit"
    args.ab_output = tmp_path / "ab"
    args.gold_fixture = tmp_path / "gold.json"
    args.calibration_fixture = tmp_path / "calibration.json"
    args.fixture = output / "tier0.json"
    args.tier1 = output / "tier1.json"
    args.tier2_chunks = output / "chunks"
    args.tier2_review_dir = args.tier2_chunks
    args.tier2_import = output / "tier2.json"
    args.adjudication = output / "adjudication.json"
    args.manual_queue = output / "manual-escalation-queue.json"
    args.corrections = output / "corrections.json"
    args.final = output / "final.json"
    args.cache = output / "cache.json"
    args.calibration_report = output / "calibration_report.json"
    args.model = audit.REQUIRED_MODEL
    args.provider_slug = "google"
    args.chunk_cases = 1
    args.calibration_threshold = 1.0
    args.calibration_min_units = 1
    return args


def _prepare_sources(args) -> tuple[str, str]:
    tree = {
        "branches": {
            "B1": {
                "id": "B1", "label": "Parent One", "level": 1,
                "children": ["B1.1"],
            },
            "B2": {
                "id": "B2", "label": "Parent Two", "level": 1,
                "children": ["B2.1"],
            },
            "B1.1": {
                "id": "B1.1", "label": "Disease A", "level": 2,
                "parent": "B1", "children": [],
            },
            "B2.1": {
                "id": "B2.1", "label": "Broad bucket", "level": 2,
                "parent": "B2", "children": [],
            },
        }
    }
    tree_hash = audit.stable_hash(tree)
    trace = {
        "arm": "A", "replicate": 1, "case_id": "case-1",
        "tree_hash": tree_hash, "tree": tree,
    }
    trace_path = (
        args.ab_output / "generation" / "traces" / "A"
        / "r01__case-1.json"
    )
    _write(trace_path, trace)
    manifest = {
        "schema_version": 1,
        "protocol_version": 1,
        "stage": "generate",
        "arms": ["A"],
        "replicates": 1,
        "tree_hashes": {"A/r01/case-1": tree_hash},
    }
    manifest["manifest_hash"] = audit.stable_hash(manifest)
    _write(args.ab_output / "generation" / "manifest.json", manifest)
    _write(args.gold_fixture, {
        "cases": [{
            "arm": "A",
            "replicate": 1,
            "case_id": "case-1",
            "gold_diagnosis": "Disease A",
            "acceptable_l2": ["B1.1"],
        }],
    })
    first = audit._unit_key("case-1", "Disease A", "Parent One")
    second = audit._unit_key("case-1", "Broad bucket", "Parent Two")
    _write(args.calibration_fixture, {
        "frozen": True,
        "units": [
            {
                "unit_id": first,
                "case_id": "case-1",
                "is_specific_disease": True,
                "is_parent_valid": True,
                "semantic_cluster_id": "disease-a",
            },
            {
                "unit_id": second,
                "case_id": "case-1",
                "is_specific_disease": False,
                "is_parent_valid": False,
                "semantic_cluster_id": "broad",
            },
        ],
    })
    return first, second


def _run_to_tier1(tmp_path: Path):
    args = _args(tmp_path, "tier0")
    unit_ids = _prepare_sources(args)
    audit.tier0(args)
    fake = FakeClient()
    audit.tier1(args, client=fake)
    return args, fake, unit_ids


def _complete_chunks(args, *, disagree_unit: str | None = None) -> None:
    tier1 = {
        row["unit_id"]: row
        for row in json.loads(args.tier1.read_text())["decisions"]
    }
    for path in args.tier2_chunks.glob("*.json"):
        if path.name == "manifest.json":
            continue
        chunk = json.loads(path.read_text())
        contract = chunk["contract"]
        decisions = []
        for request in chunk["requests"]:
            for unit in request["units"]:
                unit_id = unit["unit_id"]
                row = {
                    "unit_id": unit_id,
                    "rationale": "independent Cursor Grok 4.5 review",
                }
                for field in audit.CONTRACT_FIELDS[contract]:
                    value = tier1[unit_id][field]
                    if (
                        unit_id == disagree_unit
                        and field == "is_specific_disease"
                    ):
                        value = not value
                    row[field] = value
                decisions.append(row)
        chunk["review"] = {
            "status": "completed",
            "reviewer_model": audit.TIER2_MODEL,
            "execution": "cursor_subagent",
            "reviewer_run_id": f"test-run-{contract}",
            "decisions": decisions,
        }
        _write(path, chunk)


def test_tier0_builds_deterministic_units_and_detects_fixture_drift(tmp_path):
    args = _args(tmp_path, "tier0")
    first, second = _prepare_sources(args)

    result = audit.tier0(args)
    fixture = json.loads(args.fixture.read_text())

    assert result["units"] == 2
    assert {row["unit_id"] for row in fixture["units"]} == {first, second}
    assert fixture["deterministic_checks"]["gold_not_loaded_into_units"] is True
    assert all("gold" not in row for row in fixture["units"])
    audit.verify_sealed(fixture, label="test")
    fixture["units"][0]["leaf_label"] = "drifted"
    with pytest.raises(ValueError, match="fixture hash drift"):
        audit.verify_sealed(fixture, label="test")


def test_tier1_uses_three_isolated_contracts_and_call_provenance(tmp_path):
    args, fake, _unit_ids = _run_to_tier1(tmp_path)
    result = json.loads(args.tier1.read_text())

    assert len(fake.calls) == 3
    assert {call["contract"] for call in result["calls"]} == set(
        audit.CONTRACTS
    )
    assert all(len(call["call_hash"]) == 64 for call in result["calls"])
    assert result["model"] == audit.REQUIRED_MODEL
    assert result["provider_slug"] == "google"
    for module, payload in fake.calls:
        if not module.endswith("GoldMatch"):
            assert not audit._contains_gold_key(payload)
        else:
            assert payload["gold_diagnosis"] == "Disease A"


def test_tier1_requires_explicit_gemma_model_and_matching_provider(tmp_path):
    args = _args(tmp_path, "tier0")
    _prepare_sources(args)
    audit.tier0(args)
    args.provider_slug = None
    with pytest.raises(ValueError, match="explicit"):
        audit.tier1(args, client=FakeClient())
    args.provider_slug = "google"
    args.model = "google/gemma-3-27b-it"
    with pytest.raises(ValueError, match="gemma-4-31b"):
        audit.tier1(args, client=FakeClient())


def test_tier2_is_external_chunk_interchange_and_blind_except_goldmatch(
    tmp_path,
):
    args, _fake, _unit_ids = _run_to_tier1(tmp_path)

    audit.export_tier2_chunks(args)
    chunks = [
        json.loads(path.read_text())
        for path in args.tier2_chunks.glob("*.json")
        if path.name != "manifest.json"
    ]

    assert {chunk["contract"] for chunk in chunks} == set(audit.CONTRACTS)
    assert all(
        chunk["execution_mode"] == "external_cursor_subagent"
        for chunk in chunks
    )
    for chunk in chunks:
        if chunk["contract"] == "GoldMatch":
            assert chunk["gold_exposed"] is True
            assert audit._contains_gold_key(chunk["requests"])
        else:
            assert chunk["gold_exposed"] is False
            assert not audit._contains_gold_key(chunk["requests"])


def test_tier2_selection_skips_high_confidence_without_sentinel(tmp_path):
    args, _fake, _unit_ids = _run_to_tier1(tmp_path)
    fixture = json.loads(args.fixture.read_text())
    tier1 = json.loads(args.tier1.read_text())
    gold = audit._gold_by_case(args.gold_fixture)

    requests, summary = audit._tier2_requests(
        fixture, tier1, "LeafQuality", gold,
        confidence_threshold=0.85, sentinel_rate=0.0,
    )
    assert requests == []
    assert summary["selected_case_requests"] == 0

    tier1["decisions"][0]["confidence"]["LeafQuality"] = 0.5
    requests, summary = audit._tier2_requests(
        fixture, tier1, "LeafQuality", gold,
        confidence_threshold=0.85, sentinel_rate=0.0,
    )
    assert len(requests) == 1
    assert summary["low_confidence_case_requests"] == 1


def test_agreement_auto_accepts_and_disagreement_enters_manual_queue(tmp_path):
    args, _fake, (_first, second) = _run_to_tier1(tmp_path)
    audit.export_tier2_chunks(args)
    _complete_chunks(args, disagree_unit=second)
    audit.import_tier2_chunks(args)

    result = audit.adjudicate(args)
    queue = json.loads(args.manual_queue.read_text())
    adjudication = json.loads(args.adjudication.read_text())

    assert result["manual_escalations"] == 1
    assert result["research_only"] is True
    assert queue["items"] == [{
        "case_id": "case-1",
        "field": "is_specific_disease",
        "leaf_label": "Broad bucket",
        "parent_label": "Parent Two",
        "status": "pending_human",
        "tier1": False,
        "tier1_rationale": "fake leaf review",
        "tier2": True,
        "tier2_rationale": "independent Cursor Grok 4.5 review",
        "unit_id": second,
    }]
    states = [
        field
        for row in adjudication["decisions"]
        for field in row["fields"].values()
    ]
    assert sum(row["status"] == "manual_escalation" for row in states) == 1
    assert all(
        row["value"] is not None
        for row in states
        if row["status"] == "auto_accepted"
    )


def test_calibration_failure_downgrades_agreed_output_to_research_only(tmp_path):
    args = _args(tmp_path, "tier0")
    _prepare_sources(args)
    calibration = json.loads(args.calibration_fixture.read_text())
    calibration["units"][1]["is_specific_disease"] = True
    _write(args.calibration_fixture, calibration)
    audit.tier0(args)
    audit.tier1(args, client=FakeClient())
    audit.export_tier2_chunks(args)
    _complete_chunks(args)
    audit.import_tier2_chunks(args)

    result = audit.adjudicate(args)

    assert result["manual_escalations"] == 0
    assert result["research_only"] is True
    adjudication = json.loads(args.adjudication.read_text())
    calibration = adjudication["calibration"]
    assert calibration["downgrade"] == "research_only"
    assert calibration["fields"]["is_specific_disease"]["metric"] == "cohen_kappa"
    assert calibration["fields"]["semantic_duplicate"]["metric"] == "pairwise_f1"
    assert calibration["fields"]["gold_presence_sensitivity"]["threshold"] == 1.0
    assert calibration["fields"]["acceptable_id_macro_f1"]["threshold"] == 1.0


def test_tier3_applies_every_manual_correction_with_provenance(tmp_path):
    args, _fake, (_first, second) = _run_to_tier1(tmp_path)
    audit.export_tier2_chunks(args)
    _complete_chunks(args, disagree_unit=second)
    audit.import_tier2_chunks(args)
    audit.adjudicate(args)
    queue = json.loads(args.manual_queue.read_text())
    _write(args.corrections, {
        "manual_queue_hash": queue["fixture_hash"],
        "corrections": [{
            "unit_id": second,
            "field": "is_specific_disease",
            "tier1": False,
            "tier2": True,
            "value": False,
            "reviewer": "human-reviewer",
            "rationale": "Broad bucket is not a disease entity.",
        }],
    })

    result = audit.apply_corrections(args)
    final = json.loads(args.final.read_text())

    assert result["corrections"] == 1
    assert result["research_only"] is False
    corrected = next(
        row for row in final["decisions"] if row["unit_id"] == second
    )["fields"]["is_specific_disease"]
    assert corrected["status"] == "human_corrected"
    assert corrected["value"] is False
    assert corrected["tier3_provenance"]["reviewer"] == "human-reviewer"


def test_tier3_ai_proxy_resolves_value_but_keeps_research_only(tmp_path):
    args, _fake, (_first, second) = _run_to_tier1(tmp_path)
    audit.export_tier2_chunks(args)
    _complete_chunks(args, disagree_unit=second)
    audit.import_tier2_chunks(args)
    audit.adjudicate(args)
    queue = json.loads(args.manual_queue.read_text())
    _write(args.corrections, {
        "manual_queue_hash": queue["fixture_hash"],
        "corrections": [{
            "unit_id": second,
            "field": "is_specific_disease",
            "tier1": False,
            "tier2": True,
            "value": False,
            "reviewer": "gpt-5.6-sol",
            "reviewer_type": "ai_proxy",
            "rationale": "Broad bucket is not a disease entity.",
        }],
    })

    result = audit.apply_corrections(args)
    final = json.loads(args.final.read_text())
    corrected = next(
        row for row in final["decisions"] if row["unit_id"] == second
    )["fields"]["is_specific_disease"]

    assert result["proxy_corrections"] == 1
    assert result["human_signed_off"] is False
    assert result["research_only"] is True
    assert corrected["status"] == "tier3_proxy_corrected"
    assert corrected["value"] is False
    assert corrected["tier3_provenance"]["reviewer_type"] == "ai_proxy"

    args.calibration_min_units = 1
    args.calibration_threshold = 0.0
    calibration = audit.recalibrate_final(args)
    report = json.loads(args.calibration_report.read_text())
    assert calibration["human_signed_off"] is False
    assert calibration["passed"] is False
    assert report["proxy_review_present"] is True
    assert report["downgrade"] in {
        "pending_human_tier3_signoff", "research_only",
    }
