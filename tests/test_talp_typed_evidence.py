from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from agentclinic_tree_dx.knowledge.clinical_concept_router import (
    ClinicalConceptRouter, ConceptRef)
from agentclinic_tree_dx.knowledge.compound_finding import (
    SyndromeResolver, atomize, represent)
from agentclinic_tree_dx.knowledge.pathogen_attribution_index import (
    PathogenAttributionIndex, PathogenEdge)

ROOT = Path(__file__).resolve().parents[1]


def _eval_module():
    spec = importlib.util.spec_from_file_location(
        "talp_eval_typed_test", ROOT / "scripts/eval_talp_discrimination.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v2_fixture_is_candidate_conditioned_and_auditable():
    payload = json.loads(
        (ROOT / "data/eval/talp_medxpert_expansion_cases_v2.json").read_text())
    spec = importlib.util.spec_from_file_location(
        "fixture_audit", ROOT / "scripts/audit_talp_fixture_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.audit(payload)
    assert report["errors"] == []
    assert report["task_counts"]["organism_attribution"] == 3
    assert all(f["candidate_effects"] for c in payload["cases"] for f in c["findings"])


def test_typed_router_classifies_without_fabricating_ids():
    ref = ConceptRef("SNOMED_CT", "123", "blood culture", "test")
    router = ClinicalConceptRouter({"SNOMED_CT": {"blood culture positive": ref}})
    finding = router.route("blood culture positive", "multi")
    assert finding.event_type == "culture"
    assert finding.fhir_resource == "Observation"
    assert finding.concepts == [ref]
    unknown = router.route("MRI shows a target sign after two weeks", "multi")
    assert unknown.event_type == "imaging"
    assert unknown.temporal.relation == "after"
    assert unknown.abstained


def test_compound_atomic_and_syndrome_modes_are_candidate_blind():
    assert [a.text for a in atomize(
        "drooling with tripod positioning and abrupt high fever"
    )] == ["drooling", "tripod positioning", "abrupt high fever"]
    resolver = SyndromeResolver({"horner syndrome with ptosis": [{
        "concept_id": "24380001", "label": "Horner syndrome",
        "system": "SNOMED_CT", "provenance": "licensed test asset",
        "entailed": True,
    }]})
    dual = represent("Horner syndrome with ptosis", "dual", resolver)
    assert dual.syndrome and dual.syndrome.entailed
    negative = represent("fever and ankle pain", "syndrome", resolver)
    assert negative.abstained and negative.syndrome is None


def test_pathogen_index_resolves_culture_and_abstains_on_vignette():
    edge = PathogenEdge(
        syndrome="epiglottitis", organism_id="NCBITaxon:1313",
        organism="Streptococcus pneumoniae", relation="culture_confirms",
        source="CORPUS_ASSERTION", provenance="https://example.test/source",
        strength="decisive")
    index = PathogenAttributionIndex([edge])
    resolved = index.attribute(
        "epiglottitis", culture_result="grew Streptococcus pneumoniae")
    assert resolved.organism_id == "NCBITaxon:1313"
    abstained = index.attribute("epiglottitis", vignette_only=True)
    assert abstained.decision == "abstain"
    assert abstained.organism_id is None


def test_pathogen_index_accepts_culture_plus_causative_edge():
    edge = PathogenEdge(
        syndrome="urinary tract infection", organism_id="NCBITaxon:562",
        organism="Escherichia coli", relation="causative_agent",
        source="PATHOPHENODB", provenance="https://doi.org/example",
        strength="moderate")
    result = PathogenAttributionIndex([edge]).attribute(
        "urinary tract infection",
        culture_result="urine culture isolated Escherichia coli")
    assert result.decision == "resolved"
    assert result.organism_id == "NCBITaxon:562"


def test_pathophenodb_reified_edge_parser(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "pathopheno_builder",
        ROOT / "scripts/build_pathophenodb_pathogen_edges.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rdf = tmp_path / "mini.nt"
    rdf.write_text(
        '<http://x/DOID_1> <http://semanticscience.org/resource/SIO_000255> '
        '<http://x/a1> .\n'
        '<http://x/a1> <http://purl.obolibrary.org/obo/RO_0002558> '
        '<http://purl.obolibrary.org/obo/ECO_0000203> .\n'
        '<http://x/a1> <http://purl.obolibrary.org/obo/RO_0002556> '
        '<http://purl.obolibrary.org/obo/NCBITaxon_562> .\n'
        '<http://x/DOID_1> <http://www.w3.org/2000/01/rdf-schema#label> '
        '"urinary tract infection" .\n'
        '<http://purl.obolibrary.org/obo/NCBITaxon_562> '
        '<http://www.w3.org/2000/01/rdf-schema#label> "E. coli" .\n')
    payload = module.parse(rdf)
    assert payload["_audit"]["resolved_edges"] == 1
    assert payload["edges"][0]["organism_id"] == "NCBITaxon:562"
    assert payload["edges"][0]["strength"] == "moderate"


def test_p5_ladder_uses_isolated_stage_outputs():
    spec = importlib.util.spec_from_file_location(
        "p5_ladder", ROOT / "scripts/run_talp_typed_ab_ladder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    outputs = module._expected_outputs(
        "p5typed_fixture_v2", "7,11,13", "p5")
    assert len(outputs) == 3
    assert outputs[0].name == (
        "talp_discrim_p5typed_fixture_v2_s7r0_dv2_p5.json")
    typed_entry = dict(module.ARM_FLAGS)["typed_entry"]
    assert "--entry-gate=typed_uncertain" in typed_entry
    assert not any("p5ccv" in flag for flag in typed_entry)


def test_p5_disc_cache_signature_tracks_inputs_and_assets(tmp_path):
    module = _eval_module()
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"asset":"v1"}')
    args = SimpleNamespace(
        p5_asset_manifest=manifest, disc_model=None, model="answer-model")
    ds = {"cases": [{
        "id": "c1",
        "candidates": [{"name": "A"}, {"name": "B"}],
        "findings": [{"finding": "fever", "hpo": "HP:0001945"}],
    }]}
    cfg = module._cfg_for_stage("p5")
    first = module._disc_cache_signature(args, ds, cfg)
    cfg.entry_gate = "typed_uncertain"
    assert module._disc_cache_signature(args, ds, cfg) != first
    cfg.entry_gate = "legacy"
    manifest.write_text('{"asset":"v2"}')
    assert module._disc_cache_signature(args, ds, cfg) != first


def test_select_alias_and_entry_gate_preserve_decisive_findings():
    module = _eval_module()
    references = [{"finding": "leukocyte alkaline phosphatase",
                   "select_aliases": ["LAP score"]}]
    assert module.judge_match(object(), "LAP score", references) == 0

    class KB:
        @staticmethod
        def favored(_finding, candidates, _hpo):
            return "", {c: {"mention": 0} for c in candidates}

    case = {
        "candidates": [{"name": "A"}, {"name": "B"}],
        "findings": [
            {"finding": "decisive lab", "decisive": True,
             "typed_finding": {"abstained": True, "event_type": "laboratory"}},
            {"finding": "shared symptom", "decisive": False},
        ],
    }
    selected, audit = module._entry_findings(KB(), case, "typed_uncertain")
    assert selected[0]["finding"] == "decisive lab"
    assert audit["decisive_missed"] == []


def test_typed_select_context_never_leaks_additional_gold():
    module = _eval_module()
    typed = {"event_type": "laboratory", "concepts": [], "temporal": {}}
    case = {"findings": [
        {"finding": "known symptom", "in_vignette": True, "typed_finding": typed},
        {"finding": "decisive missing test", "in_vignette": False,
         "decisive": True, "typed_finding": typed},
    ]}
    assert [x["finding"] for x in module._typed_select_context(case)] == [
        "known symptom"]
