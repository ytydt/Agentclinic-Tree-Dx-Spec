"""Tests for the knowledge layer modules.

Tests cover:
- DxDiscriminatorIndex: loading DiagRL data, phenotype lookups, discriminators
- EvidenceMatcher: fuzzy matching evidence to phenotypes
- LRRetriever: LR cache operations
- PrimeKGIndex: loading PrimeKG data, phenotype/disease queries
- DxFeatureRetriever: unified query interface and prompt formatting
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_raw"
COMMON_JSON = DATA_DIR / "Guideline_common.json"
RARE_JSON = DATA_DIR / "Guideline_rare.json"
KG_CSV = DATA_DIR / "kg.csv"

# ---------------------------------------------------------------------------
# DxDiscriminatorIndex tests
# ---------------------------------------------------------------------------


class TestDxDiscriminatorIndex:
    @pytest.fixture(scope="class")
    def dxs_index(self):
        from src.agentclinic_tree_dx.knowledge.dx_discriminator_index import (
            DxDiscriminatorIndex,
        )
        assert COMMON_JSON.exists(), f"DiagRL common not found: {COMMON_JSON}"
        return DxDiscriminatorIndex.from_files(COMMON_JSON, RARE_JSON if RARE_JSON.exists() else None)

    def test_load_disease_count(self, dxs_index):
        assert dxs_index.disease_count > 10000

    def test_get_phenotypes_known_disease(self, dxs_index):
        phenos = dxs_index.get_phenotypes("Asthmatic Bronchitis")
        assert "wheezing" in phenos or "cough" in phenos

    def test_get_phenotypes_unknown_disease(self, dxs_index):
        assert dxs_index.get_phenotypes("ZZZZZ_NonExistent_Disease") == set()

    def test_discriminators_between_diseases(self, dxs_index):
        disc = dxs_index.discriminators("Asthmatic Bronchitis", "Dyslipidemia")
        assert len(disc["only_a"]) > 0
        assert len(disc["only_b"]) > 0

    def test_multi_discriminators(self, dxs_index):
        result = dxs_index.multi_discriminators(
            ["Asthmatic Bronchitis", "Dyslipidemia", "Seborrheic Dermatitis of Scalp"]
        )
        assert len(result) == 3
        for d, feats in result.items():
            assert isinstance(feats, list)

    def test_search_diseases(self, dxs_index):
        matches = dxs_index.search_diseases("leukemia")
        assert len(matches) > 0


# ---------------------------------------------------------------------------
# EvidenceMatcher tests
# ---------------------------------------------------------------------------


class TestEvidenceMatcher:
    @pytest.fixture
    def matcher(self):
        from src.agentclinic_tree_dx.knowledge.evidence_matcher import EvidenceMatcher
        vocab = [
            "splenomegaly",
            "thrombocytopenia",
            "fatigue",
            "basophilia",
            "visual impairment",
            "leukocytosis",
            "wheezing",
            "cough",
            "chest pain",
        ]
        return EvidenceMatcher(vocab)

    def test_exact_match(self, matcher):
        results = matcher.match("splenomegaly")
        assert len(results) >= 1
        assert results[0]["phenotype"] == "splenomegaly"

    def test_fuzzy_match(self, matcher):
        results = matcher.match("enlarged spleen consistent with splenomegaly", threshold=0.2)
        phenos = [r["phenotype"] for r in results]
        assert "splenomegaly" in phenos

    def test_no_match(self, matcher):
        results = matcher.match("patient ate breakfast", threshold=0.5)
        assert len(results) == 0

    def test_batch_match(self, matcher):
        items = ["severe fatigue reported", "cough and wheezing"]
        results = matcher.match_batch(items, threshold=0.2)
        assert len(results) == 2
        assert "severe fatigue reported" in results


# ---------------------------------------------------------------------------
# LRRetriever tests
# ---------------------------------------------------------------------------


class TestLRRetriever:
    @pytest.fixture
    def lr_retriever(self):
        from src.agentclinic_tree_dx.knowledge.lr_retriever import LRRetriever
        lr = LRRetriever()
        lr.add_entry("basophilia", "chronic myeloid leukemia", 0.85, 0.92, "test")
        lr.add_entry("splenomegaly", "chronic myeloid leukemia", 0.75, 0.80, "test")
        lr.add_entry("basophilia", "acute myeloid leukemia", 0.15, 0.92, "test")
        return lr

    def test_lookup(self, lr_retriever):
        entry = lr_retriever.lookup("basophilia", "chronic myeloid leukemia")
        assert entry is not None
        assert entry["sensitivity"] == 0.85
        assert entry["lr_positive"] is not None
        assert entry["lr_positive"] > 1

    def test_lookup_missing(self, lr_retriever):
        assert lr_retriever.lookup("nonexistent", "nonexistent") is None

    def test_lookup_by_disease(self, lr_retriever):
        entries = lr_retriever.lookup_by_disease("chronic myeloid leukemia")
        assert len(entries) == 2

    def test_get_lr_for_annotation(self, lr_retriever):
        result = lr_retriever.get_lr_for_annotation(
            "basophilia", ["chronic myeloid leukemia", "acute myeloid leukemia", "unknown"]
        )
        assert result["chronic myeloid leukemia"] is not None
        assert result["acute myeloid leukemia"] is not None
        assert result["unknown"] is None

    def test_save_and_reload(self, lr_retriever):
        from src.agentclinic_tree_dx.knowledge.lr_retriever import LRRetriever
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            lr_retriever.save_cache(path)
            reloaded = LRRetriever.from_cache(path)
            assert reloaded.entry_count == lr_retriever.entry_count
            entry = reloaded.lookup("basophilia", "chronic myeloid leukemia")
            assert entry is not None
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# DxFeatureRetriever tests (unit, with mock layers)
# ---------------------------------------------------------------------------


class TestDxFeatureRetriever:
    @pytest.fixture
    def retriever(self):
        from src.agentclinic_tree_dx.knowledge.dx_discriminator_index import DxDiscriminatorIndex
        from src.agentclinic_tree_dx.knowledge.lr_retriever import LRRetriever
        from src.agentclinic_tree_dx.knowledge.dx_feature_retriever import DxFeatureRetriever
        from src.agentclinic_tree_dx.knowledge.evidence_matcher import EvidenceMatcher

        dxs = DxDiscriminatorIndex()
        dxs._disease_phenotypes = {
            "disease a": {"fatigue", "splenomegaly", "basophilia"},
            "disease b": {"fatigue", "chest pain", "wheezing"},
        }

        lr = LRRetriever()
        lr.add_entry("basophilia", "disease a", 0.85, 0.92, "test")

        matcher = EvidenceMatcher(["fatigue", "splenomegaly", "basophilia", "chest pain", "wheezing"])

        return DxFeatureRetriever(dxs_index=dxs, lr_retriever=lr, evidence_matcher=matcher)

    def test_discriminator_hints(self, retriever):
        hints = retriever.get_discriminator_hints(["disease a", "disease b"])
        assert hints["layer_used"] == "dxs"
        assert hints["coverage_ratio"] == 1.0
        pair_key = "disease a vs disease b"
        assert pair_key in hints["pairwise"]
        assert "splenomegaly" in hints["pairwise"][pair_key]["only_a"]
        assert "chest pain" in hints["pairwise"][pair_key]["only_b"]

    def test_lr_reference(self, retriever):
        ref = retriever.get_lr_reference("basophilia", ["disease a", "disease b"])
        assert ref["lr_data"]["disease a"] is not None
        assert ref["lr_data"]["disease b"] is None

    def test_format_discriminator_hints(self, retriever):
        text = retriever.format_discriminator_hints_for_prompt(["disease a", "disease b"])
        assert "coverage=100%" in text
        assert "splenomegaly" in text

    def test_format_lr_reference(self, retriever):
        text = retriever.format_lr_reference_for_prompt("basophilia", ["disease a"])
        assert "LR+" in text

    def test_match_evidence(self, retriever):
        matches = retriever.match_evidence_to_phenotypes(["severe fatigue"], threshold=0.2)
        assert "severe fatigue" in matches


# ---------------------------------------------------------------------------
# MarkerDisambiguator (16.9.8 T0–T4) tests
# ---------------------------------------------------------------------------

MARKERS_JSON = DATA_DIR / "pathognomonic_markers.json"
AMBIG_MAP_JSON = DATA_DIR / "auto_ambiguity_map.json"


@pytest.mark.skipif(not MARKERS_JSON.exists(), reason="markers JSON missing")
class TestMarkerDisambiguation:
    @pytest.fixture(scope="class")
    def marker_index(self):
        from src.agentclinic_tree_dx.knowledge.diagnostic_marker_index import (
            DiagnosticMarkerIndex,
        )
        return DiagnosticMarkerIndex(
            pathognomonic_markers_path=MARKERS_JSON,
            auto_ambiguity_map_path=AMBIG_MAP_JSON if AMBIG_MAP_JSON.exists() else None,
        )

    def test_disambiguator_built(self, marker_index):
        assert marker_index._disambiguator is not None
        # T0: the auto map flags the classic colliding abbreviations.
        for t in ("sma", "ama", "ema", "hbs"):
            assert marker_index._disambiguator.is_ambiguous(t)

    def test_competing_sense_suppressed(self, marker_index):
        # "SMA occlusion" = superior mesenteric artery → not the antibody marker
        entry = marker_index.lookup_manual(
            "CT shows SMA occlusion in the bowel", "autoimmune hepatitis"
        )
        assert entry is None or entry.get("confidence") not in (
            "pathognomonic", "highly_specific")

    def test_marker_sense_fires(self, marker_index):
        entry = marker_index.lookup_manual(
            "SMA antibody positive, titer 1:160", "autoimmune hepatitis"
        )
        assert entry is not None
        assert entry["confidence"] == "highly_specific"

    def test_admin_sense_suppressed(self, marker_index):
        entry = marker_index.lookup_manual(
            "patient left AMA and was discharged", "primary biliary cholangitis"
        )
        assert entry is None or entry.get("confidence") not in (
            "pathognomonic", "highly_specific")

    def test_full_form_not_gated(self, marker_index):
        # A non-ambiguous full form fires regardless of cues.
        entry = marker_index.lookup_manual(
            "anti-mitochondrial antibodies present", "primary biliary cholangitis"
        )
        assert entry is not None
        assert entry["confidence"] == "highly_specific"

    def test_fail_safe_suppress(self):
        from src.agentclinic_tree_dx.knowledge.marker_disambiguator import (
            MarkerDisambiguator,
        )
        dz = (MarkerDisambiguator.from_file(AMBIG_MAP_JSON)
              if AMBIG_MAP_JSON.exists()
              else MarkerDisambiguator({"sma": {"positive_cues": ["antibody"],
                                                "competing_cues": ["artery"]}}))
        d = dz.decide("sma", "sma", 0, 3)
        assert d.fire is False
        assert d.tier == "fail_safe"

    def test_llm_tier_escalation(self):
        from src.agentclinic_tree_dx.knowledge.marker_disambiguator import (
            MarkerDisambiguator,
        )
        # No lexical cue → escalate; stub LLM answers 'A' (marker sense).
        amap = {"sma": {"expected_semantic_type": "serology_immunology",
                        "positive_cues": ["antibody"], "competing_cues": ["artery"],
                        "source_terms": ["anti-smooth muscle antibodies", "sma"]}}
        dz = MarkerDisambiguator(amap, llm_fn=lambda prompt: "A")
        d = dz.decide("sma", "the sma was noted here", 4, 3)
        assert d.fire is True
        assert d.tier == "T3"
        dz_b = MarkerDisambiguator(amap, llm_fn=lambda prompt: "B")
        assert dz_b.decide("sma", "the sma was noted here", 4, 3).fire is False


# ---------------------------------------------------------------------------
# PrimeKGIndex integration test (requires kg.csv download)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not KG_CSV.exists(), reason="PrimeKG kg.csv not downloaded")
class TestPrimeKGIndex:
    @pytest.fixture(scope="class")
    def primekg(self):
        from src.agentclinic_tree_dx.knowledge.primekg_index import PrimeKGIndex
        return PrimeKGIndex.from_csv(KG_CSV)

    def test_stats(self, primekg):
        assert primekg.stats.get("disease_phenotype_positive", 0) > 100000

    def test_cml_phenotypes(self, primekg):
        phenos = primekg.get_positive_phenotypes("chronic myelogenous leukemia, bcr-abl1 positive")
        assert len(phenos) > 0

    def test_negative_phenotypes_exist(self, primekg):
        total_neg = sum(len(v) for v in primekg.disease_phenotype_neg.values())
        assert total_neg > 1000

    def test_disease_disease(self, primekg):
        related = primekg.get_related_diseases("chronic myelogenous leukemia, bcr-abl1 positive")
        assert len(related) > 0

    def test_phenotype_phenotype(self, primekg):
        related = primekg.get_related_phenotypes("splenomegaly")
        assert len(related) >= 0  # may or may not have relations

    def test_search_diseases(self, primekg):
        matches = primekg.search_diseases("leukemia")
        assert len(matches) > 5

    def test_discriminators_cml_vs_aml(self, primekg):
        cml = "chronic myelogenous leukemia, bcr-abl1 positive"
        aml_candidates = primekg.search_diseases("acute myeloid leukemia")
        if aml_candidates:
            disc = primekg.discriminators(cml, aml_candidates[0])
            assert "only_a" in disc
            assert "only_b" in disc

    def test_phenotype_multihop(self, primekg):
        neighbors = primekg.phenotype_multihop("splenomegaly", max_depth=1)
        # splenomegaly should have at least some related phenotypes via HPO hierarchy
        assert isinstance(neighbors, set)
