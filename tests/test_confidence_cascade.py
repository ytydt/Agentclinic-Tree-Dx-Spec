"""§25.2(#3) regression: confidence-gated cascade.

When ``_confidence_gated_cascade`` is enabled, a LOW-confidence Layer-2 cache hit
(HPO subsumption / context-only) must NOT short-circuit the Layer-3a RAG
fallback: RAG is allowed to override it with a higher-confidence numeric LR.

The default (OFF) path keeps the strict tier order — any cache hit blocks RAG —
so the low-confidence subsumption entry is returned unchanged.
"""

from agentclinic_tree_dx.knowledge.dx_feature_retriever import DxFeatureRetriever


class _FakeLR:
    """Returns a low-confidence (subsumption) cache hit for every query."""
    _disease_index: dict = {}

    def lookup_fuzzy(self, finding, disease, **kw):
        return {
            "finding": finding, "disease": disease,
            "lr_positive": 2.0, "lr_negative": 0.8,
            "source": "subsumption_upward:HP:0001873",
            "confidence": "subsumption_upward",
        }


class _FakeRAG:
    is_ready = True

    def search_for_disease(self, disease, finding, top_k=3):
        return [{"article_id": "A1", "content": "snippet", "title": "T1"}]

    def extract_lr_from_snippets(self, snippets, finding, disease):
        return {
            "finding": finding, "disease": disease,
            "lr_positive": 9.0, "lr_negative": 0.3,
            "source": "RAG", "confidence": "rag_numeric",
        }


def _retriever():
    return DxFeatureRetriever(lr_retriever=_FakeLR(), rag_retriever=_FakeRAG())


def test_legacy_off_low_conf_hit_blocks_rag():
    r = _retriever()
    assert r._confidence_gated_cascade is False
    out = r.get_lr_reference("renal mass", ["x disease"])
    entry = out["lr_data"]["x disease"]
    assert entry["confidence"] == "subsumption_upward"
    assert entry["lr_positive"] == 2.0  # RAG never consulted


def test_cascade_on_rag_overrides_low_conf_hit():
    r = _retriever()
    r._confidence_gated_cascade = True
    out = r.get_lr_reference("renal mass", ["x disease"])
    entry = out["lr_data"]["x disease"]
    assert entry["source"] == "RAG"
    assert entry["lr_positive"] == 9.0  # numeric RAG hit wins


def test_cascade_on_keeps_low_conf_when_rag_empty():
    # RAG returns snippets but no numeric LR → context-only must NOT downgrade
    # the existing subsumption entry.
    class _EmptyRAG(_FakeRAG):
        def extract_lr_from_snippets(self, snippets, finding, disease):
            return None

    r = DxFeatureRetriever(lr_retriever=_FakeLR(), rag_retriever=_EmptyRAG())
    r._confidence_gated_cascade = True
    out = r.get_lr_reference("renal mass", ["x disease"])
    entry = out["lr_data"]["x disease"]
    assert entry["confidence"] == "subsumption_upward"
    assert entry["lr_positive"] == 2.0
