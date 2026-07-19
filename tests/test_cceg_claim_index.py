from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

from agentclinic_tree_dx.knowledge.cceg_claim_index import CCEGClaimIndex

ROOT = Path(__file__).resolve().parents[1]


def grounded_claim(
    claim_id: str = "cceg_0123456789ab",
    candidate_a: str = "primary hyperparathyroidism",
    candidate_b: str = "malignancy-associated hypercalcemia",
) -> dict:
    quote = "Elevated PTH supports A whereas it argues against B."
    return {
        "schema_version": 1, "claim_id": claim_id, "claim_type": "direction",
        "candidate_a": {"name": candidate_a, "id": None,
                        "id_provenance": None, "l1_parent": "PTH-mediated"},
        "candidate_b": {"name": candidate_b, "id": None,
                        "id_provenance": None, "l1_parent": "non-PTH-mediated"},
        "finding": {
            "surface": "elevated parathyroid hormone", "event_type": "laboratory",
            "concepts": [{"system": "HPO", "code": "HP:1",
                          "display": "Elevated PTH", "provenance": "fixture",
                          "confidence": 1.0}],
            "polarity": 1, "value_state": "elevated", "value": None,
            "unit": None, "specimen": "serum",
            "temporal": {"onset": None, "duration": None,
                         "relation": None, "anchor": None},
            "context": {"fasting": "yes"}, "abstained": False,
        },
        "relation": "supports_a", "recommended_test": None,
        "strength": "explicit", "source_class": "cpg_prose",
        "allowed_consumers": ["audit", "p3_soft", "p5_soft"],
        "comparator": {"required": True, "has_support_excerpt": True,
                       "has_contrast_excerpt": True,
                       "contrast_candidates": [candidate_b]},
        "provenance": {
            "source_id": "src", "chunk_id": f"chunk:{claim_id}",
            "article_id": "article", "section": "evaluation",
            "chunk_type": "evaluation", "quote": quote,
            "quote_span": [0, len(quote)], "url": "https://example.test",
            "evidence_grade": None,
        },
        "extraction": {
            "pipeline": "fixture", "model": "fixture", "prompt_sha256": "a" * 64,
            "confidence": 1.0, "entailment_status": "grounded",
            "normalization_abstained": False, "normalization_reason": None,
        },
        "audit": {"enumeration_only": False, "pair_binding_ok": True,
                  "negation_scope_ok": True, "value_scope_ok": True},
        "review": {"status": "accepted", "reviewer_ids": ["a", "b"],
                   "adjudication": None},
        "split": {"document_family": "fixture", "document_split": "build",
                  "family_held_out": False, "pilot_scope": True},
        "claim_status": "grounded",
    }


def test_grounded_only_and_canonical_pair_preserves_direction():
    valid = grounded_claim()
    raw = deepcopy(valid)
    raw["claim_id"] = "cceg_abcdefabcdef"
    raw["claim_status"] = "pending_review"
    raw["extraction"]["entailment_status"] = "unvalidated"
    raw["review"]["status"] = "unreviewed"
    index = CCEGClaimIndex([valid, raw])
    assert len(index.claims) == 1
    hit = index.lookup(
        "malignancy-associated hypercalcemia",
        "primary hyperparathyroidism",
        {"surface": "elevated parathyroid hormone", "value_state": "elevated"},
    )[0]
    assert hit["relation"] == "supports_b"
    excerpt = index.evidence_excerpts(
        "malignancy-associated hypercalcemia",
        "primary hyperparathyroidism",
    )[0]
    assert excerpt["relation"] == "supports_b"
    assert excerpt["candidate"] == "malignancy-associated hypercalcemia"


def test_surface_concept_value_and_context_matching():
    index = CCEGClaimIndex([grounded_claim()])
    assert index.lookup("primary hyperparathyroidism",
                        "malignancy-associated hypercalcemia",
                        {"concepts": [{"system": "HPO", "code": "HP:1"}],
                         "value_state": "elevated",
                         "context": {"fasting": "yes"}})
    assert not index.lookup("primary hyperparathyroidism",
                            "malignancy-associated hypercalcemia",
                            {"surface": "elevated parathyroid hormone",
                             "value_state": "normal"})
    excerpt = index.evidence_excerpts(
        "primary hyperparathyroidism", "malignancy-associated hypercalcemia")[0]
    assert {"id", "candidate", "source", "text", "claim_id"} <= excerpt.keys()


def test_builder_refuses_overwrite_and_writes_manifest(tmp_path):
    source = tmp_path / "claims.jsonl"
    source.write_text(json.dumps(grounded_claim()) + "\n")
    spec = importlib.util.spec_from_file_location(
        "build_cceg_claim_index_test", ROOT / "scripts/build_cceg_claim_index.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    output = tmp_path / "index"
    manifest = module.build_index(source, output)
    assert manifest["policy"] == "schema-valid-and-grounded-only"
    try:
        module.build_index(source, output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("builder overwrote an existing artifact")
