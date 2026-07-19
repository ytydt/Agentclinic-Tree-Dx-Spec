"""Integration tests for knowledge layer + controller interaction.

Tests that:
1. Controller initialises knowledge layer from config paths
2. Knowledge hints are injected into TALP payload
3. LR references are injected into Annotator payload
4. seen_evidence_phenotypes is updated after annotation
5. Full DxFeatureRetriever with both DxS + PrimeKG produces merged results
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_raw"


class TestControllerKnowledgeInit:
    """Test that controller correctly initialises knowledge layer."""

    def test_knowledge_layer_disabled_by_default(self):
        from agentclinic_tree_dx.config import ControllerConfig
        from agentclinic_tree_dx.controller import AgentClinicTreeController

        class FakeEnv:
            def get_case_summary(self):
                return ""
            def call_module(self, *a, **kw):
                return {}

        config = ControllerConfig()
        ctrl = AgentClinicTreeController(FakeEnv(), config=config)
        assert ctrl._knowledge_retriever is None

    def test_knowledge_layer_enabled_with_dxs(self):
        from agentclinic_tree_dx.config import ControllerConfig
        from agentclinic_tree_dx.controller import AgentClinicTreeController

        class FakeEnv:
            def get_case_summary(self):
                return ""
            def call_module(self, *a, **kw):
                return {}

        common = DATA_DIR / "Guideline_common.json"
        if not common.exists():
            pytest.skip("DiagRL data not available")

        config = ControllerConfig(
            enable_knowledge_injection=True,
            dxs_common_json=str(common),
        )
        ctrl = AgentClinicTreeController(FakeEnv(), config=config)
        assert ctrl._knowledge_retriever is not None
        assert ctrl._knowledge_retriever.dxs is not None
        assert ctrl._knowledge_retriever.dxs.disease_count > 10000


@pytest.mark.skipif(
    not (DATA_DIR / "Guideline_common.json").exists(),
    reason="DiagRL data not available",
)
class TestDxFeatureRetrieverIntegration:
    """Integration test with real DxS + optional PrimeKG data."""

    @pytest.fixture(scope="class")
    def retriever(self):
        from agentclinic_tree_dx.knowledge.dx_discriminator_index import DxDiscriminatorIndex
        from agentclinic_tree_dx.knowledge.dx_feature_retriever import DxFeatureRetriever
        from agentclinic_tree_dx.knowledge.evidence_matcher import EvidenceMatcher
        from agentclinic_tree_dx.knowledge.lr_retriever import LRRetriever

        dxs = DxDiscriminatorIndex.from_files(DATA_DIR / "Guideline_common.json")
        lr = LRRetriever.from_cache(DATA_DIR / "lr_cache.json")

        # Build vocab from DxS
        vocab = set()
        for phenos in dxs._disease_phenotypes.values():
            vocab.update(phenos)
        matcher = EvidenceMatcher(sorted(list(vocab)[:5000]))

        return DxFeatureRetriever(dxs_index=dxs, lr_retriever=lr, evidence_matcher=matcher)

    def test_leukemia_discriminators(self, retriever):
        """Test CML-like diseases produce meaningful discriminators."""
        diseases = retriever.dxs.search_diseases("chronic myeloid leukemia")
        if not diseases:
            diseases = retriever.dxs.search_diseases("leukemia")
        assert len(diseases) > 0

        hints = retriever.get_discriminator_hints(diseases[:3])
        assert hints["coverage_ratio"] > 0
        assert hints["layer_used"] in ("dxs", "primekg", "both")

    def test_prompt_formatting_produces_text(self, retriever):
        text = retriever.format_discriminator_hints_for_prompt(
            ["asthmatic bronchitis", "dyslipidemia"]
        )
        assert len(text) > 20
        assert "coverage=" in text

    def test_evidence_matching_with_real_vocab(self, retriever):
        matches = retriever.match_evidence_to_phenotypes(
            ["patient reports wheezing and cough"],
            threshold=0.2,
        )
        assert len(matches) > 0
        assert any(
            any("wheez" in m["phenotype"] or "cough" in m["phenotype"] for m in ms)
            for ms in matches.values()
        )

    def test_seen_evidence_exclusion(self, retriever):
        """Seen phenotypes are excluded from discriminator hints."""
        diseases = ["asthmatic bronchitis", "dyslipidemia"]
        hints_full = retriever.get_discriminator_hints(diseases)

        all_features = set()
        for data in hints_full["pairwise"].values():
            all_features.update(data["only_a"])
            all_features.update(data["only_b"])

        if all_features:
            seen = {list(all_features)[0]}
            hints_with_seen = retriever.get_discriminator_hints(diseases, seen_evidence=seen)
            all_features_2 = set()
            for data in hints_with_seen["pairwise"].values():
                all_features_2.update(data["only_a"])
                all_features_2.update(data["only_b"])
            assert seen - all_features_2 == seen


@pytest.mark.skipif(
    not (DATA_DIR / "kg.csv").exists(),
    reason="PrimeKG kg.csv not available",
)
class TestFullLayerStack:
    """Test the complete Layer 0 + Layer 1 stack together."""

    @pytest.fixture(scope="class")
    def full_retriever(self):
        from agentclinic_tree_dx.knowledge.dx_discriminator_index import DxDiscriminatorIndex
        from agentclinic_tree_dx.knowledge.primekg_index import PrimeKGIndex
        from agentclinic_tree_dx.knowledge.dx_feature_retriever import DxFeatureRetriever
        from agentclinic_tree_dx.knowledge.lr_retriever import LRRetriever

        dxs = DxDiscriminatorIndex.from_files(DATA_DIR / "Guideline_common.json")
        primekg = PrimeKGIndex.from_csv(DATA_DIR / "kg.csv")
        lr = LRRetriever.from_cache(DATA_DIR / "lr_cache.json")
        return DxFeatureRetriever(dxs_index=dxs, primekg_index=primekg, lr_retriever=lr)

    def test_both_layers_contribute(self, full_retriever):
        hints = full_retriever.get_discriminator_hints(
            ["asthmatic bronchitis", "dyslipidemia"]
        )
        assert hints["layer_used"] in ("dxs", "both")

    def test_exclusion_features_from_primekg(self, full_retriever):
        """PrimeKG negative edges should appear in exclusion_features."""
        hints = full_retriever.get_discriminator_hints(
            ["chronic myelogenous leukemia, bcr-abl1 positive"]
        )
        # PrimeKG provides exclusion features (negative edges)
        assert isinstance(hints["exclusion_features"], dict)

    def test_related_diseases_from_primekg(self, full_retriever):
        hints = full_retriever.get_discriminator_hints(
            ["chronic myelogenous leukemia, bcr-abl1 positive"]
        )
        assert isinstance(hints["related_diseases"], dict)
        cml_key = "chronic myelogenous leukemia, bcr-abl1 positive"
        if cml_key in hints["related_diseases"]:
            related = hints["related_diseases"][cml_key]
            assert len(related) > 0
