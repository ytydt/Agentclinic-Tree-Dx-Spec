"""§25.2(#1) regression: HPO-exact concept match must outrank a sub-threshold
fuzzy token hit when the retrieval-priority fix is enabled, and the default
(OFF) path must reproduce the legacy ordering exactly.

Scenario: the patient finding and the CORRECT cache finding are surface-different
(low token overlap) but map to the SAME HPO id (= ontology synonym). A DECOY
cache entry for the same disease shares a generic token (≥0.35 Jaccard). Legacy
order returns the decoy (fuzzy best_entry shadows the sub-threshold HPO-exact);
the fix returns the HPO-exact entry.
"""

import pytest

from agentclinic_tree_dx.knowledge.lr_retriever import LRRetriever


class _FakeHPO:
    """Minimal HPOIndex stand-in: maps surface strings to HPO ids."""
    def __init__(self, mapping):
        self._m = mapping

    def resolve_fuzzy(self, text):
        return self._m.get((text or "").strip().lower())

    def is_ancestor_of(self, a, d):
        return False

    def subsumption_depth(self, a, d):
        return -1


def _build_retriever():
    r = LRRetriever()
    # Two cache entries for the SAME disease "x disease":
    #   - synonym: SAME HP id as the patient finding, but token-disjoint surface
    #     form (Jaccard 0 → sub-threshold via tokens).
    #   - decoy:   a SUPERSET of the patient's tokens (different HP id) → passes
    #     fuzzy via the substring/subset rule (score 0.8), so in the legacy order
    #     it becomes best_entry and shadows the HPO-exact synonym.
    r._cache = {
        "x disease||kidney tumor": {
            "finding": "kidney tumor", "disease": "x disease",
            "hpo_id": "HP:0001873", "lr_positive": 8.0, "lr_negative": 0.5,
            "source": "synonym",
        },
        "x disease||renal mass biopsy": {
            "finding": "renal mass biopsy", "disease": "x disease",
            "hpo_id": "HP:0009999", "lr_positive": 1.3, "lr_negative": 0.9,
            "source": "decoy",
        },
    }
    r._build_indices()
    r._hpo_index = _FakeHPO({
        "renal mass": "HP:0001873",        # patient finding
        "kidney tumor": "HP:0001873",      # cache synonym (same concept)
        "renal mass biopsy": "HP:0009999", # decoy (different concept)
    })
    return r


def test_legacy_off_returns_fuzzy_decoy():
    r = _build_retriever()
    assert r._hpo_exact_priority is False  # default
    # "renal mass" is a substring of "renal mass biopsy" → fuzzy 0.8 → best_entry;
    # the same-concept synonym "kidney tumor" (HP-exact) is demoted to a
    # sub-threshold fallback and shadowed.
    entry = r.lookup_fuzzy("renal mass", "x disease")
    assert entry is not None
    assert entry["source"] == "decoy"


def test_fix_on_returns_hpo_exact_synonym():
    r = _build_retriever()
    r._hpo_exact_priority = True
    entry = r.lookup_fuzzy("renal mass", "x disease")
    assert entry is not None
    assert entry["source"] == "synonym"
    assert entry["hpo_id"] == "HP:0001873"


def test_fix_is_noop_when_no_hpo_collision():
    # Patient finding whose HP id matches the decoy itself → the fix has nothing
    # better to surface; behaviour is unchanged vs legacy.
    r = _build_retriever()
    base = r.lookup_fuzzy("renal mass biopsy", "x disease")
    r._hpo_exact_priority = True
    fixed = r.lookup_fuzzy("renal mass biopsy", "x disease")
    assert base["source"] == fixed["source"] == "decoy"


def test_disease_candidate_scan_is_reused_across_findings(monkeypatch):
    import agentclinic_tree_dx.knowledge.lr_retriever as module

    r = _build_retriever()
    r._cache["other disease||fever"] = {
        "finding": "fever",
        "disease": "other disease",
        "lr_positive": 1.0,
        "source": "other",
    }
    r._build_indices()
    original = module._disease_match_score
    calls = 0

    def counted(query, candidate):
        nonlocal calls
        calls += 1
        return original(query, candidate)

    monkeypatch.setattr(module, "_disease_match_score", counted)
    first = r.lookup_fuzzy("renal mass", "x disease")
    first_calls = calls
    second = r.lookup_fuzzy("kidney tumor", "x disease")

    assert first is not None and second is not None
    assert first_calls > 0
    assert calls == first_calls
