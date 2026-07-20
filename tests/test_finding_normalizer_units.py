"""Safety and coverage tests for the expanded lab-reference catalog."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentclinic_tree_dx.knowledge.finding_normalizer import FindingNormalizer


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "knowledge_raw"


@pytest.fixture(scope="module")
def normalizer() -> FindingNormalizer:
    return FindingNormalizer(
        DATA / "lab_reference_ranges.json",
        DATA / "loinc2hpo_annotations.json",
        DATA / "unit_conversions.json",
    )


def test_si_bilirubin_is_converted_before_comparison(normalizer):
    normal = normalizer.normalize("Total bilirubin: 17 μmol/L")
    assert normal and normal.direction == "N"
    assert normal.reference_unit == "mg/dL"

    high = normalizer.normalize("Total bilirubin: 17 mg/dL")
    assert high and high.direction == "H" and high.hpo_term == "Hyperbilirubinemia"


@pytest.mark.parametrize(
    "unit", ["× 10^9/L", "× 109/L", "x10^9/L", "× 1000/µL"]
)
def test_scientific_count_unit_typography_is_supported(normalizer, unit):
    result = normalizer.normalize(f"WBC: 4.5 {unit}")
    assert result and result.direction == "N"


def test_incompatible_units_never_fall_through_to_raw_comparison(normalizer):
    result = normalizer.normalize("CA-125: 115.6 g/dL")
    assert result and result.direction == "unknown"
    assert result.source == "unit_mismatch"


def test_arterial_pressure_converts_kpa_to_mmhg(normalizer):
    result = normalizer.normalize("pCO2: 1.7 kPa")
    assert result and result.direction == "L"
    assert result.hpo_term == "Hypocapnia"


def test_d_dimer_preserves_feu_and_ddu_identity(normalizer):
    feu = normalizer.normalize("D-dimer: 0.7 μg/mL FEU")
    assert feu and feu.direction == "H"
    assert feu.reference_unit == "ng/mL FEU"

    ddu = normalizer.normalize("D-dimer: 0.7 μg/mL DDU")
    assert ddu and ddu.direction == "unknown" and ddu.source == "unit_mismatch"

    unqualified = normalizer.normalize("D-dimer: 0.7 μg/mL")
    assert unqualified and unqualified.direction == "unknown"


def test_high_sensitivity_troponin_requires_sex_or_local_limit(normalizer):
    ambiguous = normalizer.normalize("high-sensitivity troponin I: 16 ng/L")
    assert ambiguous and ambiguous.direction == "unknown"
    assert ambiguous.source == "reference_context_required"

    female = normalizer.normalize(
        "high-sensitivity troponin I: 16 ng/L", gender="female"
    )
    male = normalizer.normalize(
        "high-sensitivity troponin I: 16 ng/L", gender="male"
    )
    assert female and female.direction == "H"
    assert male and male.direction == "N"

    equivalent_unit = normalizer.normalize(
        "high-sensitivity troponin I: 0.016 ng/mL", gender="female"
    )
    assert equivalent_unit and equivalent_unit.direction == "H"


def test_conventional_troponin_i_uses_current_hpo_identifier(normalizer):
    result = normalizer.normalize("Troponin I: 0.10 ng/mL")
    assert result and result.direction == "H"
    assert result.hpo_id == "HP:0410173"
    assert "troponin I" in result.hpo_term


def test_free_and_total_thyroid_hormones_do_not_share_hpo_terms(normalizer):
    free_t3 = normalizer.normalize("Free T3: 9 pg/mL")
    free_t4 = normalizer.normalize("Free T4: 5 ng/dL")
    total_t3 = normalizer.normalize("Total T3: 300 ng/dL")

    assert free_t3 and free_t3.hpo_id == "HP:0011788"
    assert free_t4 and free_t4.hpo_id == "HP:0033077"
    assert total_t3 and total_t3.direction == "H"
    assert total_t3.hpo_id is None
    assert total_t3.narrative == "Increased Total T3"


def test_report_local_reference_overrides_static_or_context_only_data(normalizer):
    ca125 = normalizer.normalize("CA-125: 115.6 U/mL (normal <35 U/mL)")
    assert ca125 and ca125.direction == "H"
    assert ca125.reference_source == "case_local_reference"

    nt_probnp = normalizer.normalize(
        "NT-proBNP: 500 pg/mL (reference <300 pg/mL)"
    )
    assert nt_probnp and nt_probnp.direction == "H"
    assert nt_probnp.hpo_term == "Elevated circulating NT-proBNP concentration"


def test_method_specific_and_context_only_target_dataset_labs(normalizer):
    assert normalizer.normalize("Beta-D-glucan: 500 pg/mL").direction == "H"
    assert normalizer.normalize("Methylmalonic acid: 4.81 μmol/L").direction == "H"
    assert normalizer.normalize("Serum IgG4: 333 mg/dL").direction == "H"
    assert normalizer.normalize("Blood mercury level: 47 μg/L").direction == "H"

    for finding in (
        "IL-6: 74 pg/mL",
        "PSA: 4.2 ng/mL",
        "Anti-factor Xa activity: 0.22 IU/mL",
        "Total bile acid: 9.1 μmol/L",
    ):
        result = normalizer.normalize(finding)
        assert result and result.direction == "unknown"
        assert result.source == "clinical_context_required"


def test_24_hour_urine_protein_converts_grams_to_milligrams(normalizer):
    result = normalizer.normalize("Proteinuria: 2.61 g/24h")
    assert result and result.direction == "H"
    assert result.reference_unit == "mg/24h"


def test_additional_target_dataset_si_units(normalizer):
    assert normalizer.normalize("Total protein: 70 g/L").direction == "N"
    assert normalizer.normalize("Free T4: 20 pmol/L").direction == "N"
    assert normalizer.normalize("PTH: 7 pmol/L").direction == "H"


def test_stratified_ranges_use_consensus_only(normalizer):
    unequivocally_low = normalizer.normalize("Hemoglobin: 7.2 g/dL")
    assert unequivocally_low and unequivocally_low.direction == "L"

    ambiguous = normalizer.normalize("Hemoglobin: 13 g/dL")
    assert ambiguous and ambiguous.direction == "unknown"

    female = normalizer.normalize("Hemoglobin: 13 g/dL", gender="female")
    assert female and female.direction == "N"


def test_bnp_and_nt_probnp_are_distinct_catalog_entries(normalizer):
    bnp = normalizer.normalize("BNP: 120 pg/mL")
    nt_probnp = normalizer.normalize("NT-proBNP: 120 pg/mL")
    assert bnp and bnp.test_name == "BNP"
    assert nt_probnp and nt_probnp.test_name == "NT_proBNP"


def test_sources_cover_every_curated_extension_record():
    sources = json.loads((DATA / "lab_reference_sources.json").read_text(encoding="utf-8"))
    extension = json.loads(
        (DATA / "lab_reference_range_extensions.json").read_text(encoding="utf-8")
    )
    known = set(sources["sources"])
    used = {
        record["source"]
        for entry in extension["additions"].values()
        for kind in ("reference_ranges", "decision_limits")
        for record in entry.get(kind, [])
    }
    assert used <= known


def test_sources_cover_every_committed_range_and_decision_limit():
    sources = json.loads((DATA / "lab_reference_sources.json").read_text(encoding="utf-8"))
    catalog = json.loads((DATA / "lab_reference_ranges.json").read_text(encoding="utf-8"))
    known = set(sources["sources"])
    used = {
        record["source"]
        for entry in catalog.values()
        for kind in ("reference_ranges", "decision_limits")
        for record in entry.get(kind, [])
    }
    assert used <= known


def test_committed_runtime_json_is_reproducible():
    completed = subprocess.run(
        [sys.executable, "scripts/extend_lab_reference_data.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
