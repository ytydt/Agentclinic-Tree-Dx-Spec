"""Regression tests for the three knowledge-coverage improvements:

  1. Mechanism/morphology → canonical-disease normalisation (DiseaseNameResolver).
  2. RAG-time qualitative→quantitative LR conversion (lr_quant).
  3. Secondary (tier-2) RAG-LR cache (SecondaryLRCache).
  4. AnswerMapper cause-priority rule (prompt contract).
"""

from __future__ import annotations

import json
from pathlib import Path

from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver
from agentclinic_tree_dx.knowledge.lr_quant import quantify_snippet, compute_lr
from agentclinic_tree_dx.knowledge.secondary_lr_cache import SecondaryLRCache

_REPO = Path(__file__).resolve().parents[1]
_MECH = _REPO / "data" / "knowledge_raw" / "mechanism_to_disease.json"


# ── 1. disease entity normalisation ─────────────────────────────────────────
def _resolver_with_mech() -> DiseaseNameResolver:
    r = DiseaseNameResolver()
    r.load_mechanism_map(_MECH)
    r.register_source("lr", [
        "primary hyperparathyroidism", "insulinoma", "glucagonoma",
        "type 1 diabetes mellitus", "cushing's syndrome", "pancoast tumor",
    ])
    return r


def test_mechanism_canonicalisation():
    r = _resolver_with_mech()
    assert r.canonicalize_entity("Increased parathyroid hormone") == "primary hyperparathyroidism"
    assert r.canonicalize_entity("Beta cell tumor") == "insulinoma"
    assert r.canonicalize_entity("Alpha cell tumor") == "glucagonoma"
    # unmapped label passes through (lower-cased / normalised)
    assert r.canonicalize_entity("Malignancy") == "malignancy"


def test_mechanism_resolves_to_source_key():
    r = _resolver_with_mech()
    assert r.resolve("Increased parathyroid hormone", "lr") == "primary hyperparathyroidism"
    assert r.resolve("Beta cell tumor", "lr") == "insulinoma"
    assert r.resolve("Apical lung tumor", "lr") == "pancoast tumor"


def test_mechanism_map_is_loadable_and_nonempty():
    data = json.loads(_MECH.read_text())
    assert isinstance(data.get("exact"), dict) and len(data["exact"]) >= 20


# ── 2. RAG qualitative→quantitative conversion ──────────────────────────────
def test_compute_lr_basic():
    lr_pos, lr_neg = compute_lr(0.8, 0.95)
    assert round(lr_pos, 1) == 16.0
    assert 0.0 < lr_neg < 1.0


def test_quantify_explicit_sn_sp():
    e = quantify_snippet("Sensitivity was 80% and specificity was 95%.", "x", "d")
    assert e["confidence"] == "rag_extracted"
    assert e["lr_positive"] is not None and e["lr_negative"] is not None


def test_quantify_qualitative_frequent():
    e = quantify_snippet(
        "Basophilia is seen in the majority of patients with CML.",
        "basophilia", "chronic myeloid leukemia",
    )
    assert e["confidence"] == "rag_qualitative"
    assert e["lr_positive"] > 1.0  # frequent + specific → supportive
    assert e["lr_negative"] is not None  # LR- now computed (was hardcoded None)


def test_quantify_rare_gives_lr_below_one():
    e = quantify_snippet("Splenomegaly is rarely associated.", "splenomegaly", "d")
    assert e["lr_positive"] < 1.0


def test_quantify_percentage_is_extracted_tier():
    e = quantify_snippet("Occurs in up to 30% of cases.", "hypercalcemia", "d")
    assert e["provenance"].startswith("pct")
    assert e["confidence"] == "rag_extracted"


def test_quantify_no_signal_returns_none():
    assert quantify_snippet("This sentence has no frequency information.", "foo", "d") is None


# ── 3. secondary LR cache ───────────────────────────────────────────────────
def test_secondary_cache_put_get_persist(tmp_path):
    p = tmp_path / "sec.json"
    c = SecondaryLRCache(p, flush_every=1)
    entry = {"lr_positive": 4.0, "lr_negative": 0.5, "source": "RAG-quant"}
    c.put("hypercalcemia", "primary hyperparathyroidism", entry)
    c.put("foo", "bar", None)  # memoised miss
    c.flush()
    assert p.exists()

    c2 = SecondaryLRCache(p)
    assert c2.contains("hypercalcemia", "primary hyperparathyroidism")
    assert c2.get("hypercalcemia", "primary hyperparathyroidism")["lr_positive"] == 4.0
    # memoised miss is "present but null" — distinguishable via contains()
    assert c2.contains("foo", "bar")
    assert c2.get("foo", "bar") is None
    assert not c2.contains("never", "seen")


# ── 4. AnswerMapper cause-priority contract ─────────────────────────────────
def test_answer_mapper_prompt_has_cause_priority():
    prompt = (_REPO / "src" / "agentclinic_tree_dx" / "prompts" / "answer_mapper.txt").read_text()
    assert "CAUSAL PRECEDENCE" in prompt
    assert "UPSTREAM" in prompt or "upstream" in prompt
