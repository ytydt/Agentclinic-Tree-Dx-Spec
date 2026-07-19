"""Tests for manifest CPG chunking (NICE / society guidelines)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cpg_manifest_common import (
    chunk_manifest_row,
    is_browser_gate_text,
    is_hub_text,
    manifest_has_bot_gate,
    parse_nice_html,
    should_skip_manifest_row,
)


def test_skip_wikem_and_index_pages():
    assert should_skip_manifest_row({"id": "wikem_x", "source": "WikEM", "status": "ok"})[0]
    assert should_skip_manifest_row(
        {"id": "idsa_az", "source": "IDSA", "status": "ok", "title": "A-Z Guideline Listing"}
    )[0]


def test_nice_recommendations_html_chunks():
    html_path = ROOT / "data/cpg/raw/nice/nice-ddx-ng96-recommendations.html"
    if not html_path.exists():
        return
    html = html_path.read_text(encoding="utf-8")
    row = {
        "id": "nice_ddx__ng96__recommendations",
        "source": "NICE",
        "title": "Recommendations | Care and support of people growing older with learning disabilities | Guidance | NICE",
        "status": "ok",
        "url": "https://www.nice.org.uk/guidance/ng96/chapter/Recommendations",
        "parent_id": "nice_guidance_ng96",
    }
    chunks = parse_nice_html(html, row, max_tokens=400)
    assert len(chunks) >= 10
    assert all("1.1." in c["content"] or "Ensure" in c["content"] for c in chunks[:3])
    assert chunks[0]["chunk_type"] in {"recommendation", "evaluation", "background"}
    assert "You are here" not in chunks[0]["content"]


def test_idsa_index_hub_filtered():
    text_path = ROOT / "data/cpg/text/idsa/idsa-child-blastomycosis.txt"
    if not text_path.exists():
        return
    row = {
        "id": "idsa_child__blastomycosis",
        "source": "IDSA",
        "title": "IDSA 2008 Clinical Practice Guideline Update for the Management of Blastomycosis",
        "status": "ok",
        "access": "public_html",
        "raw_path": "data/cpg/raw/idsa/idsa-child-blastomycosis.html",
        "text_path": "data/cpg/text/idsa/idsa-child-blastomycosis.txt",
    }
    chunks = chunk_manifest_row(row, ROOT, max_tokens=320)
    assert len(chunks) >= 1
    blob = " ".join(c["content"] for c in chunks[:5])
    assert "Skip to nav" not in blob
    assert "blastomyc" in blob.lower()


def test_manifest_row_json_roundtrip_fields():
    row = {
        "id": "nice_ddx__cg95__recommendations",
        "source": "NICE",
        "title": "Recommendations | Chest pain of recent onset | Guidance | NICE",
        "status": "ok",
        "access": "public_html",
        "parent_id": "nice_guidance_cg95",
        "raw_path": "data/cpg/raw/nice/nice-ddx-cg95-recommendations.html",
    }
    raw = ROOT / row["raw_path"]
    if not raw.exists():
        return
    chunks = chunk_manifest_row(row, ROOT, max_tokens=320)
    assert chunks
    c = chunks[0]
    assert c["manifest_id"] == row["id"]
    assert c["entry_type"] in {"syndrome_entry", "disease_entry"}
    assert c["content_tier"] == "full_text"


def test_browser_gate_text_detected():
    gate = (
        "Checking your browser - reCAPTCHA\n"
        "Checking your browser before accessing pubmed.ncbi.nlm.nih.gov ...\n"
        "Click here if you are not automatically redirected after 5 seconds.\n"
    )
    assert is_browser_gate_text(gate)
    assert not is_browser_gate_text("Patients with chest pain should be evaluated for ACS.")


def test_browser_gate_manifest_row_skipped():
    row = {
        "id": "aan_pm__19398680",
        "source": "AAN",
        "title": "Practice parameter update",
        "status": "ok",
        "access": "public_html",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3475193/",
        "text_path": "data/cpg/text/aan/aan-pm-19398680.txt",
        "raw_path": "data/cpg/raw/aan/aan-pm-19398680.html",
    }
    tp = ROOT / row["text_path"]
    if not tp.exists():
        return
    assert manifest_has_bot_gate(row, ROOT)
    assert chunk_manifest_row(row, ROOT, max_tokens=320) == []
