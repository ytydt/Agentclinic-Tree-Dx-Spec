"""§25.2(#2) regression: finding-match guards.

When ``_match_guards`` is enabled, ``LRRetriever.lookup_fuzzy`` must:
  - reject a candidate whose NEGATION polarity conflicts with the patient
    finding ("exertional chest pain" must not match "no chest pain"),
  - reject a candidate whose LATERALITY conflicts ("left" vs "right"),
  - raise the pure-token acceptance bar to 0.5 (a 0.43-Jaccard hit that the
    legacy path accepts at ≥0.35 is dropped).

The default (OFF) path must reproduce the legacy permissive behaviour exactly.
"""

from agentclinic_tree_dx.knowledge.lr_retriever import (
    LRRetriever,
    _match_guard_conflict,
)


def _retriever(cache: dict) -> LRRetriever:
    r = LRRetriever()
    r._cache = cache
    r._build_indices()
    r._hpo_index = None  # isolate from HPO-based tiers
    return r


# ── unit: the conflict predicate ──────────────────────────────────────────────

def test_negation_conflict_predicate():
    assert _match_guard_conflict("exertional chest pain", "no chest pain") is True
    assert _match_guard_conflict("no chest pain", "absent chest pain") is False
    assert _match_guard_conflict("chest pain", "chest pain") is False


def test_laterality_conflict_predicate():
    assert _match_guard_conflict("left hemiparesis", "right hemiparesis") is True
    assert _match_guard_conflict("acute left hemiparesis", "acute left weakness") is False
    # only one side specified → no conflict (cannot prove disagreement)
    assert _match_guard_conflict("hemiparesis", "left hemiparesis") is False


# ── lookup_fuzzy: negation guard ──────────────────────────────────────────────

def _negation_cache():
    return {
        "d||no chest pain": {
            "finding": "no chest pain", "disease": "d",
            "lr_positive": 0.4, "lr_negative": 1.0, "source": "neg",
        },
    }


def test_negation_legacy_accepts_off():
    r = _retriever(_negation_cache())
    assert r._match_guards is False
    entry = r.lookup_fuzzy("exertional chest pain", "d")
    assert entry is not None and entry["source"] == "neg"


def test_negation_guard_rejects_on():
    r = _retriever(_negation_cache())
    r._match_guards = True
    assert r.lookup_fuzzy("exertional chest pain", "d") is None


# ── lookup_fuzzy: laterality guard ────────────────────────────────────────────

def _laterality_cache():
    return {
        "d||acute right hemiparesis": {
            "finding": "acute right hemiparesis", "disease": "d",
            "lr_positive": 3.0, "lr_negative": 0.6, "source": "rt",
        },
    }


def test_laterality_legacy_accepts_off():
    r = _retriever(_laterality_cache())
    entry = r.lookup_fuzzy("acute left hemiparesis", "d")
    assert entry is not None and entry["source"] == "rt"


def test_laterality_guard_rejects_on():
    r = _retriever(_laterality_cache())
    r._match_guards = True
    assert r.lookup_fuzzy("acute left hemiparesis", "d") is None


# ── lookup_fuzzy: pure-token bar (0.35 → 0.5) ─────────────────────────────────

def _weak_token_cache():
    # patient {alpha,beta,gamma,delta} vs cache {alpha,beta,gamma,eps,zeta,eta,th}
    # Jaccard = 3 / (4+7-3) = 3/8 = 0.375 → ≥0.35 (legacy) but <0.5 (guarded).
    # No subset (patient has 'delta' absent from cache), no negation/laterality.
    return {
        "d||alpha beta gamma eps zeta eta th": {
            "finding": "alpha beta gamma eps zeta eta th", "disease": "d",
            "lr_positive": 2.0, "lr_negative": 0.7, "source": "weak",
        },
    }


def test_weak_token_legacy_accepts_off():
    r = _retriever(_weak_token_cache())
    entry = r.lookup_fuzzy("alpha beta gamma delta", "d")
    assert entry is not None and entry["source"] == "weak"


def test_weak_token_bar_rejects_on():
    r = _retriever(_weak_token_cache())
    r._match_guards = True
    assert r.lookup_fuzzy("alpha beta gamma delta", "d") is None
