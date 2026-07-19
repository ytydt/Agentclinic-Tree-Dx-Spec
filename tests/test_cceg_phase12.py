from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scope_mod = _module("cceg_scope_test", "scripts/build_cceg_pilot_scope.py")
extract_mod = _module("extract_cceg_claims", "scripts/extract_cceg_claims.py")
entail_mod = _module("cceg_entail_test", "scripts/validate_cceg_entailment.py")
sample_mod = _module("cceg_sample_test", "scripts/sample_cceg_gold_audit.py")
score_mod = _module("cceg_score_test", "scripts/score_cceg_gold_audit.py")
membership_extract_mod = _module(
    "cceg_membership_extract_test",
    "scripts/extract_case_report_membership_claims.py")


class _ForbiddenAwareDict(dict):
    def get(self, key, default=None):
        if key in {"role", "favors", "candidate_effects", "is_gold"}:
            raise AssertionError(f"scope read forbidden field: {key}")
        return super().get(key, default)


def _family_config() -> dict:
    return {
        "families": [
            {
                "family": f"family_{i}",
                "case_ids": ["case"] if i == 0 else [],
                "family_split": "held_out" if i == 5 else "build",
                "held_out": i == 5,
            }
            for i in range(6)
        ]
    }


def _query() -> dict:
    return {
        "query_id": "ccegq_1234567890abcdef",
        "candidate_a": "alpha disease",
        "candidate_b": "beta disease",
        "finding": {"surface": "marker X", "value": ""},
        "document_family": "family_0",
        "family_split": "build",
        "family_held_out": False,
    }


def _raw_claim(quote: str) -> dict:
    return {
        "claim_type": "direction",
        "relation": "supports_a",
        "quote": quote,
        "strength": "explicit",
        "confidence": 0.9,
        "event_type": "laboratory",
        "value_state": "present",
        "polarity": 1,
        "value": None,
        "unit": None,
        "specimen": None,
        "normalization": {},
        "enumeration_only": False,
        "pair_binding_ok": True,
        "negation_scope_ok": True,
        "value_scope_ok": True,
        "has_support_excerpt": True,
        "has_contrast_excerpt": True,
        "recommended_test": None,
    }


def _chunk(content: str, *, corpus: str = "cpg") -> dict:
    return {
        "id": "chunk-1",
        "source_id": "source-1",
        "article_id": "article-1",
        "source": "Guideline",
        "section_path": "Diagnosis",
        "chunk_type": "evaluation",
        "content": content,
        "url": "https://example.test/cpg",
        "corpus": corpus,
    }


def _claim() -> tuple[dict, dict]:
    quote = "Marker X supports alpha disease rather than beta disease."
    chunk = _chunk(quote)
    claim = extract_mod.materialize_claim(
        _raw_claim(quote), _query(), chunk, "test-model")
    return claim, chunk


def test_scope_is_label_blind_and_uses_all_unordered_pairs():
    dataset = {
        "cases": [{
            "id": "case",
            "candidates": [
                _ForbiddenAwareDict(name="Gamma", is_gold=True),
                _ForbiddenAwareDict(name="Alpha", role="gold"),
                _ForbiddenAwareDict(name="Beta", candidate_effects={}),
            ],
            "findings": [
                _ForbiddenAwareDict(
                    finding="marker", value="high", role="rule_in_gold",
                    favors="gold"),
            ],
        }]
    }
    rows = scope_mod.build_scope(dataset, _family_config())
    assert len(rows) == 3
    assert {
        (row["candidate_a"], row["candidate_b"]) for row in rows
    } == {("Alpha", "Beta"), ("Alpha", "Gamma"), ("Beta", "Gamma")}
    assert all(row["finding"] == {"surface": "marker", "value": "high"} for row in rows)


def test_real_family_registry_has_six_to_eight_families_and_heldout():
    config = json.loads(
        (ROOT / "data/eval/cceg_pilot_families.json").read_text())
    assert 6 <= len(config["families"]) <= 8
    assert any(row["held_out"] for row in config["families"])
    assert config["policy"]["forbidden_scope_inputs"]


def test_quote_hydration_requires_unique_exact_substring_and_span():
    content = "prefix exact quote suffix"
    assert extract_mod.hydrate_quote(content, "exact quote") == (7, 18)
    with pytest.raises(ValueError, match="exact"):
        extract_mod.hydrate_quote(content, "Exact quote")
    with pytest.raises(ValueError, match="ambiguous"):
        extract_mod.hydrate_quote("same / same", "same")


def test_materialized_cpg_claim_is_raw_unreviewed_and_schema_valid():
    claim, chunk = _claim()
    start, end = claim["provenance"]["quote_span"]
    assert chunk["content"][start:end] == claim["provenance"]["quote"]
    assert claim["claim_status"] == "raw"
    assert claim["extraction"]["entailment_status"] == "unvalidated"
    assert claim["review"] == {
        "status": "unreviewed", "reviewer_ids": [], "adjudication": None,
    }
    assert claim["split"]["document_split"] == extract_mod.document_split(chunk)


def test_source_document_split_is_stable_and_independent_of_family_split():
    chunk = _chunk("source text")
    assert extract_mod.document_split(chunk) == extract_mod.document_split({
        **chunk, "content": "changed chunk text",
    })
    query = {**_query(), "family_split": "held_out", "family_held_out": True}
    claim = extract_mod.materialize_claim(
        _raw_claim("source text"), query, chunk, "test-model")
    assert claim["split"]["family_held_out"] is True
    assert claim["split"]["document_split"] == extract_mod.document_split(chunk)


def test_case_report_cannot_materialize_direction():
    quote = "Marker X supports alpha disease rather than beta disease."
    with pytest.raises(ValueError, match="case reports"):
        extract_mod.materialize_claim(
            _raw_claim(quote), _query(),
            _chunk(quote, corpus="case_reports"), "test-model")


def test_case_report_enumeration_extracts_membership_without_direction():
    chunk = {
        **_chunk(
            "Presentation: cough. Differential diagnosis includes: "
            "alpha disease; unrelated disease.",
            corpus="case_report"),
        "wiki_links": ["alpha disease", "unrelated disease"],
        "syndrome_anchor": "cough",
    }
    claims = membership_extract_mod.extract_claims([chunk], [_query()])
    assert len(claims) == 1
    assert claims[0]["claim_type"] == "membership"
    assert claims[0]["relation"] == "member_of"
    assert claims[0]["audit"]["enumeration_only"] is True
    assert claims[0]["allowed_consumers"] == ["audit"]


def test_pair_retrieval_is_deterministic_and_rewards_both_candidates():
    query = _query()
    chunks = [
        _chunk("alpha disease and beta disease are separated by marker X"),
        {
            **_chunk("alpha disease only"),
            "id": "chunk-2",
        },
    ]
    ranked = extract_mod.retrieve_pair_chunks(query, reversed(chunks), top_k=2)
    assert [row["id"] for row in ranked] == ["chunk-1", "chunk-2"]


def test_extraction_cache_prevents_duplicate_llm_call(tmp_path):
    quote = "Marker X supports alpha disease rather than beta disease."
    chunk = _chunk(quote)

    class StubLLM:
        calls = 0

        def call_module(self, module, prompt, payload):
            self.calls += 1
            assert module == "CCEGPairClaimExtractor"
            assert payload["pair"] == {
                "candidate_a": "alpha disease",
                "candidate_b": "beta disease",
            }
            return {"claims": [_raw_claim(quote)]}

    llm = StubLLM()
    first = extract_mod.extract_one(llm, _query(), chunk, "test-model", tmp_path)
    second = extract_mod.extract_one(llm, _query(), chunk, "test-model", tmp_path)
    assert first == second
    assert llm.calls == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_extraction_cache_key_changes_when_chunk_content_changes():
    chunk = _chunk("first")
    changed = {**chunk, "content": "second"}
    assert extract_mod._cache_key(_query(), chunk, "model") != (
        extract_mod._cache_key(_query(), changed, "model"))


def test_resume_manifest_only_skips_successful_queries(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        '{"event":"query_complete","query_id":"done"}\n'
        '{"event":"query_failed","query_id":"retry"}\n')
    assert extract_mod._completed_queries(manifest) == {"done"}


def test_l0_hydration_rejects_wrong_stored_span():
    claim, chunk = _claim()
    assert entail_mod.hydrate_claim(claim, chunk) == []
    claim["provenance"]["quote_span"] = [0, 2]
    assert any("quote_span" in error for error in entail_mod.hydrate_claim(claim, chunk))


def test_conflict_or_non_entailment_never_becomes_grounded():
    claim, _ = _claim()
    conflict = entail_mod.apply_verdict(
        claim, {"verdict": "conflict"}, [])
    assert conflict["extraction"]["entailment_status"] == "conflict"
    assert conflict["claim_status"] == "rejected"
    rejected = entail_mod.apply_verdict(
        claim, {"verdict": "not_entailed"}, [])
    assert rejected["extraction"]["entailment_status"] == "rejected"
    assert rejected["claim_status"] == "rejected"


def test_entailed_claim_waits_for_humans_and_does_not_forge_signatures():
    claim, _ = _claim()
    response = {
        "verdict": "entailed",
        "pair_binding_ok": True,
        "negation_scope_ok": True,
        "value_scope_ok": True,
        "has_support_excerpt": True,
        "has_contrast_excerpt": True,
    }
    updated = entail_mod.apply_verdict(claim, response, [])
    assert updated["extraction"]["entailment_status"] == "grounded"
    assert updated["claim_status"] == "pending_review"
    assert updated["review"]["reviewer_ids"] == []
    assert updated["review"]["status"] == "unreviewed"


def test_deterministic_comparator_probes_are_stable_and_detect_conflicts():
    probes = json.loads(
        (ROOT / "data/eval/cceg_comparator_probes.json").read_text())
    assert probes["deterministic"] is True
    ids = [probe["id"] for probe in probes["probes"]]
    assert ids == sorted(ids) or len(ids) == len(set(ids))
    claim, _ = _claim()
    claim["finding"]["surface"] = "BCR-ABL"
    claim["finding"]["value_state"] = "present"
    claim["provenance"]["quote"] = (
        "The absence of BCR-ABL argues against chronic myeloid leukemia.")
    assert entail_mod.deterministic_conflict(claim)


def test_audit_packet_is_unsigned_and_unsigned_batch_is_blocked():
    claim, _ = _claim()
    claim["extraction"]["entailment_status"] = "grounded"
    packet = sample_mod.make_packet([claim], 1)
    assert packet["status"] == "UNSIGNED"
    assert all(not row["reviewer_id"] for row in packet["batch_signoffs"])
    with pytest.raises(score_mod.UnsignedBatchError):
        score_mod.score_packet(packet)


def test_signed_dual_audit_scores_kappa_precision_and_gate():
    claim, _ = _claim()
    claim["extraction"]["entailment_status"] = "grounded"
    packet = sample_mod.make_packet([claim], 1)
    packet["batch_signoffs"] = [
        {
            "reviewer_id": "clinician-a",
            "signed_at": "2026-07-12T00:00:00+00:00",
            "attestation": score_mod.ATTESTATION,
        },
        {
            "reviewer_id": "clinician-b",
            "signed_at": "2026-07-12T00:01:00+00:00",
            "attestation": score_mod.ATTESTATION,
        },
    ]
    packet["items"][0]["reviews"] = [
        {"reviewer_id": "clinician-a", "label": "accept", "reason": "entailed"},
        {"reviewer_id": "clinician-b", "label": "accept", "reason": "entailed"},
    ]
    report = score_mod.score_packet(packet)
    assert report["cohen_kappa"] == 1.0
    assert report["precision"] == 1.0
    assert report["publishable"]
    finalized = score_mod.apply_human_decisions([claim], report)
    assert finalized[0]["claim_status"] == "grounded"
    assert finalized[0]["review"]["status"] == "accepted"
    assert "p5_soft" in finalized[0]["allowed_consumers"]


def test_audit_sample_always_includes_all_direction_and_common_claims():
    claims = []
    for index, claim_type in enumerate(("direction", "common", "membership")):
        claim, _ = _claim()
        claim["claim_id"] = f"claim-{index}"
        claim["claim_type"] = claim_type
        claims.append(claim)
    selected = sample_mod.deterministic_sample(claims, size=1)
    assert {row["claim_type"] for row in selected} == {"direction", "common"}


def test_prompt_hashes_are_real_sha256_and_independent():
    assert len(extract_mod.PROMPT_SHA256) == 64
    assert len(entail_mod.PROMPT_SHA256) == 64
    assert extract_mod.PROMPT_SHA256 != entail_mod.PROMPT_SHA256
