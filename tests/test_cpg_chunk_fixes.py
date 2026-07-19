"""Tests for CPG chunk gating and WikEM/PMC chunk fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cpg_chunk_gate import snippet_on_topic
from wikem_common import build_chunks_from_page, classify_section, is_index_hub_title
from pmc_oa_ddx_common import should_keep_chunk


def test_snippet_on_topic_accepts_chunk_type():
    assert snippet_on_topic(
        title="Abdominal pain > RUQ Pain",
        content="...",
        syndrome_tokens={"abdominal", "pain"},
        chunk_type="differential",
    )


def test_snippet_on_topic_accepts_syndrome_entry():
    assert snippet_on_topic(
        title="Abdominal pain > Clinical Features",
        content="nausea vomiting",
        syndrome_tokens={"abdominal", "pain"},
        entry_type="syndrome_entry",
        syndrome_anchor="Abdominal pain",
    )


def test_wikem_geriatrics_elderly_section():
    assert classify_section("Elderly", page_title="Abdominal pain (geriatrics)") == "differential"
    html_path = ROOT / "data/cpg/raw/wikem/abdominal-pain-geriatrics.html"
    if not html_path.exists():
        pytest.skip("geriatrics fixture not downloaded")
    html = html_path.read_text(encoding="utf-8")
    sec_path = html_path.with_suffix(".sections.json")
    sections = json.loads(sec_path.read_text()) if sec_path.exists() else []
    _, chunks, links = build_chunks_from_page(
        page_title="Abdominal pain (geriatrics)",
        html=html,
        sections=sections,
        source_id="wikem_syndrome__abdominal-pain-geriatrics",
        url="https://wikem.org/wiki/Abdominal_pain_(geriatrics)",
    )
    assert len(chunks) >= 1
    assert any(c["chunk_type"] == "differential" for c in chunks)
    assert len(links) >= 3


def test_wikem_index_hub_filter():
    assert is_index_hub_title("Diagnoses by body part (main)")
    assert not is_index_hub_title("Abdominal pain")


def test_pmc_keep_under_ddx_tree():
    stack = ["Introduction", "Differential Diagnosis", "Biliary disease"]
    text = "Acute cholecystitis accounts for 21% of cases in elderly patients."
    assert should_keep_chunk(
        "Biliary disease",
        text,
        "paragraph",
        section_stack=stack,
        article_title="Approach to abdominal pain",
    )


def test_merck_prose_not_split_into_entries():
    from merck_manual_common import is_entry_title

    line = "Dietary proteins are broken down into peptides and amino acids."
    nxt = "Proteins are required for tissue maintenance."
    assert not is_entry_title(line, nxt, approach=False)


def test_merck_approach_entry_title():
    from merck_manual_common import is_entry_title

    line = "Chronic and Recurrent Abdominal Pain"
    nxt = "Chronic abdominal pain (CAP) persists for more than 3 mo."
    assert is_entry_title(line, nxt, approach=True)
