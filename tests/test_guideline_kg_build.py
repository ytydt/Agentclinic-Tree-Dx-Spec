"""Integration tests for the guideline-KG deterministic build contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_guideline_diagnostic_kg import build  # noqa: E402
from agentclinic_tree_dx.knowledge.guideline_kg_schema import (  # noqa: E402
    DocumentVersion,
    Passage,
    Section,
    SourceWork,
    record_to_dict,
    validate_graph,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_internal_graph_preserves_context_passages_but_gate_controls_extraction(
    tmp_path: Path,
) -> None:
    work = SourceWork(
        title="Test guideline",
        publisher="Test",
        canonical_url="urn:test:guideline",
        source_family="test",
    )
    version = DocumentVersion(
        source_work_id=work.id,
        version_label="v1",
        content_sha256="0" * 64,
    )
    diagnosis = Section(
        document_version_id=version.id,
        heading="Diagnosis",
        section_path=("Disease", "Diagnosis"),
        ordinal=1,
        section_type="diagnostic",
    )
    treatment = Section(
        document_version_id=version.id,
        heading="Treatment",
        section_path=("Disease", "Treatment"),
        ordinal=2,
        section_type="context",
    )
    diagnostic_passage = Passage(
        section_id=diagnosis.id,
        ordinal=1,
        text="Diagnosis is based on the following findings.",
        extensions={
            "admitted": True,
            "admission_reasons": ["chunk_type:evaluation"],
            "metadata": {"chunk_type": "evaluation", "source": "Test"},
        },
    )
    context_passage = Passage(
        section_id=treatment.id,
        ordinal=2,
        text="Offer oral therapy once daily.",
        extensions={
            "admitted": True,
            "admission_reasons": ["context_closure"],
            "metadata": {
                "chunk_type": "recommendation",
                "section_path": "Disease > Treatment",
                "source": "Test",
            },
        },
    )
    passage_dir = tmp_path / "passages"
    passage_dir.mkdir()
    _write_jsonl(passage_dir / "source_works.jsonl", [record_to_dict(work)])
    _write_jsonl(passage_dir / "document_versions.jsonl", [record_to_dict(version)])
    _write_jsonl(
        passage_dir / "sections.jsonl",
        [record_to_dict(diagnosis), record_to_dict(treatment)],
    )
    _write_jsonl(
        passage_dir / "passages.jsonl",
        [record_to_dict(diagnostic_passage), record_to_dict(context_passage)],
    )

    output = tmp_path / "build"
    manifest = build(argparse.Namespace(
        passages=passage_dir,
        skip_input_validation=False,
        source=None,
        include_unadmitted=False,
        limit=None,
        source_context="all",
        disease_aliases=tmp_path / "missing_aliases.json",
        output_dir=output,
        residual_priority=4,
    ))
    records = _read_jsonl(output / "graph.internal.jsonl")
    assert validate_graph(records) == []
    assert manifest["statistics"]["passages_processed"] == 1
    assert manifest["source_passages_available"] == 2
    assert manifest["source_passages_preserved"] == 2
    assert {
        row["id"] for row in records if row["record_type"] == "Passage"
    } == {diagnostic_passage.id, context_passage.id}


def test_public_assertion_projection_is_explicitly_nonranking(
    tmp_path: Path,
) -> None:
    work = SourceWork(
        title="Projection test",
        publisher="Test",
        canonical_url="urn:test:projection",
        source_family="test",
    )
    version = DocumentVersion(
        source_work_id=work.id,
        version_label="v1",
        content_sha256="1" * 64,
    )
    section = Section(
        document_version_id=version.id,
        heading="Diagnosis",
        section_path=("Example disease", "Diagnosis"),
        ordinal=1,
        section_type="diagnostic",
    )
    passage = Passage(
        section_id=section.id,
        ordinal=1,
        text="Example disease is characterized by a reproducible finding.",
        extensions={
            "admitted": True,
            "admission_reasons": ["chunk_type:evaluation"],
            "entry_title": "Example disease",
            "chunk_type": "evaluation",
            "section_path": ["Example disease", "Diagnosis"],
            "source": "Test",
            "metadata": {
                "chunk_type": "evaluation",
                "entry_title": "Example disease",
                "section_path": ["Example disease", "Diagnosis"],
                "source": "Test",
            },
        },
    )
    passage_dir = tmp_path / "passages"
    passage_dir.mkdir()
    _write_jsonl(passage_dir / "source_works.jsonl", [record_to_dict(work)])
    _write_jsonl(passage_dir / "document_versions.jsonl", [record_to_dict(version)])
    _write_jsonl(passage_dir / "sections.jsonl", [record_to_dict(section)])
    _write_jsonl(passage_dir / "passages.jsonl", [record_to_dict(passage)])

    output = tmp_path / "build"
    build(argparse.Namespace(
        passages=passage_dir,
        skip_input_validation=False,
        source=None,
        include_unadmitted=False,
        limit=None,
        source_context="all",
        disease_aliases=tmp_path / "missing_aliases.json",
        output_dir=output,
        residual_priority=4,
    ))
    assertions = [
        row for row in _read_jsonl(output / "graph.public.jsonl")
        if row["record_type"] == "DiagnosticAssertion"
    ]
    assert len(assertions) == 1
    assert assertions[0]["review_status"] == "unreviewed"
    assert assertions[0]["qualifiers"]["ranking_eligible"] is False
    assert assertions[0]["release_profile"] == (
        "pointer_only_unreviewed_nonranking_v2"
    )
