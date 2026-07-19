from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base_extract = _module("extract_cceg_claims", "scripts/extract_cceg_claims.py")
scope_mod = _module("cceg_unary_scope_test", "scripts/build_cceg_unary_scope.py")
unary_mod = _module("cceg_unary_extract_test", "scripts/extract_cceg_unary_claims.py")
validator_mod = _module("cceg_unary_validator_test", "scripts/validate_cceg_entailment.py")


class _ForbiddenAwareDict(dict):
    def get(self, key, default=None):
        if key in scope_mod.FORBIDDEN_KEYS:
            raise AssertionError(f"read forbidden field: {key}")
        return super().get(key, default)


def _query() -> dict:
    return {
        "query_id": "cceguq_1234567890abcdef",
        "case_id": "case-1",
        "candidate": {
            "name": "chronic myeloid leukemia",
            "aliases": ["CML"],
            "concepts": [],
        },
        "finding": {
            "surface": "BCR-ABL fusion",
            "event_type": "laboratory",
            "value_state": "present",
            "polarity": 1,
            "value": "",
            "aliases": ["Philadelphia chromosome"],
            "concepts": [{
                "system": "HPO",
                "code": "HP:0031519",
                "display": "BCR-ABL1 fusion",
                "provenance": "scope_fixture",
            }],
        },
        "document_family": "hematology",
        "family_held_out": False,
    }


def _chunk(
    content: str, *, chunk_id: str = "chunk-1", section: str = "Diagnosis",
) -> dict:
    return {
        "id": chunk_id,
        "source_id": "source-1",
        "article_id": "article-1",
        "source": "Guideline",
        "section_path": section,
        "chunk_type": "evaluation",
        "content": content,
        "url": "https://example.test/guideline",
        "corpus": "cpg",
    }


def _raw(quote: str) -> dict:
    return {
        "effect": "rule_in",
        "quote": quote,
        "strength": "explicit",
        "confidence": 0.95,
        "event_type": "laboratory",
        "value_state": "present",
        "polarity": 1,
        "value": None,
        "unit": None,
        "specimen": None,
        "normalization": {},
        "negation_scope_ok": True,
        "value_scope_ok": True,
    }


def test_real_scope_has_17_cases_and_is_label_blind():
    datasets = [
        (
            "talp_discrimination_cases",
            json.loads((ROOT / "data/eval/talp_discrimination_cases.json").read_text()),
        ),
        (
            "talp_medxpert_expansion_cases_v2",
            json.loads(
                (ROOT / "data/eval/talp_medxpert_expansion_cases_v2.json").read_text()),
        ),
    ]
    rows = scope_mod.build_scope(datasets)
    assert len({row["case_id"] for row in rows}) == 17
    assert len(rows) == 401
    assert all(row["unary_scope"] for row in rows)
    serialized = json.dumps(rows)
    assert not any(f'"{key}"' in serialized for key in scope_mod.FORBIDDEN_KEYS)


def test_scope_never_reads_supervision_fields():
    cases = []
    for index in range(17):
        cases.append({
            "id": f"case-{index}",
            "corpus": "test",
            "candidates": [
                _ForbiddenAwareDict(name="Disease", is_gold=True, role="gold"),
            ],
            "findings": [
                _ForbiddenAwareDict(
                    finding="high marker", role="rule_in_gold", favors="gold",
                    candidate_effects=[{"effect": "rule_in"}]),
            ],
        })
    rows = scope_mod.build_scope([("test", {"cases": cases})])
    assert len(rows) == 17
    assert rows[0]["finding"]["value_state"] == "elevated"


def test_alias_and_concept_rerank_prioritizes_diagnosis_section():
    query = _query()
    diagnosis = _chunk(
        "CML is characterized by BCR-ABL1 fusion.",
        chunk_id="diagnosis", section="Diagnostic evaluation")
    background = _chunk(
        "CML is characterized by BCR-ABL1 fusion.",
        chunk_id="background", section="Background")
    retriever = unary_mod.UnaryChunkRetriever([background, diagnosis], [query])
    assert [row["id"] for row in retriever.retrieve(query, 2)] == [
        "diagnosis", "background",
    ]


def test_unary_claim_has_exact_span_and_no_comparator_requirement():
    quote = "BCR-ABL fusion is characteristic of chronic myeloid leukemia."
    chunk = _chunk(f"Prefix. {quote} Suffix.")
    claim = unary_mod.materialize_claim(_raw(quote), _query(), chunk, "test-model")
    start, end = claim["provenance"]["quote_span"]
    assert chunk["content"][start:end] == quote
    assert claim["schema_version"] == 2
    assert claim["claim_type"] == "candidate_effect"
    assert claim["relation"] == "supports_candidate"
    assert claim["candidate_b"] is None
    assert claim["comparator"] == {
        "required": False,
        "has_support_excerpt": True,
        "has_contrast_excerpt": False,
        "contrast_candidates": [],
    }


def test_unary_cache_is_content_addressed_and_avoids_duplicate_calls(tmp_path):
    quote = "BCR-ABL fusion is characteristic of chronic myeloid leukemia."
    chunk = _chunk(quote)

    class StubLLM:
        calls = 0

        def call_module(self, module, prompt, payload):
            self.calls += 1
            assert module == "CCEGUnaryCandidateEffectExtractor"
            return {"claims": [_raw(quote)]}

    llm = StubLLM()
    first = unary_mod.extract_one(llm, _query(), chunk, "test-model", tmp_path)
    second = unary_mod.extract_one(llm, _query(), chunk, "test-model", tmp_path)
    assert first == second
    assert llm.calls == 1
    changed = {**chunk, "content": quote + " Additional content."}
    assert unary_mod._cache_key(_query(), chunk, "test-model") != (
        unary_mod._cache_key(_query(), changed, "test-model"))


def test_unary_l0_rejects_inexact_quote_without_losing_valid_sibling(tmp_path):
    quote = "BCR-ABL fusion is characteristic of chronic myeloid leukemia."

    class StubLLM:
        def call_module(self, module, prompt, payload):
            return {"claims": [_raw(quote), _raw("not an exact quote")]}

    accepted, rejected = unary_mod.extract_one(
        StubLLM(), _query(), _chunk(quote), "test-model", tmp_path)
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert "exact" in rejected[0]


def test_l1_validator_accepts_entailed_unary_without_contrast():
    quote = "BCR-ABL fusion is characteristic of chronic myeloid leukemia."
    claim = unary_mod.materialize_claim(
        _raw(quote), _query(), _chunk(quote), "test-model")
    updated = validator_mod.apply_verdict(claim, {
        "verdict": "entailed",
        "pair_binding_ok": True,
        "negation_scope_ok": True,
        "value_scope_ok": True,
        "has_support_excerpt": True,
        "has_contrast_excerpt": False,
    }, [])
    assert updated["extraction"]["entailment_status"] == "grounded"
    assert updated["claim_status"] == "pending_review"
    assert updated["comparator"]["has_contrast_excerpt"] is False


def test_resume_only_skips_completed_unary_queries(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        '{"event":"query_complete","query_id":"done","accepted":1}\n'
        '{"event":"query_failed","query_id":"retry"}\n')
    assert unary_mod._completed_queries(manifest) == {"done"}
