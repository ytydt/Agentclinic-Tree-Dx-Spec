from analysis.mechanism_v2.common import FrozenExactSynonymBridge
from analysis.mechanism_v2.e10_mac_factorial import (
    BRIDGE_PATH,
    _doctor_validator,
    _supervisor_validator,
    concept_registry,
    doctor_mechanisms,
    rrf_keys,
)


def _doctor(name, values, success=True):
    return {
        "doctor_name": name,
        "success": success,
        "ranked_diagnoses": values,
        "commentary": "",
    }


def test_validators_fail_closed():
    assert _doctor_validator({"ranked_diagnoses": ["A", "B"]}) is None
    assert _doctor_validator({"ranked_diagnoses": ["A", "A"]})
    validate = _supervisor_validator({"D1", "D2"})
    assert validate({"top2_candidate_ids": ["D1", "D2"]}) is None
    assert validate({"top2_candidate_ids": ["D1", "D3"]})


def test_registry_rrf_and_mechanisms_share_identity():
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    doctors = [
        _doctor("A", ["asthma", "pneumonia"]),
        _doctor("B", ["Asthma", "bronchitis"]),
        _doctor("C", ["pneumonia", "asthma"]),
    ]
    registry, key_to_id, id_to_key = concept_registry("case/1", doctors, bridge)
    keys, scores = rrf_keys(doctors, bridge)
    assert len(registry) == 3
    assert set(key_to_id) == set(id_to_key.values())
    assert keys[0] == bridge.canonical_key("asthma")
    assert scores[keys[0]] > scores[bridge.canonical_key("bronchitis")]
    mechanism = doctor_mechanisms(doctors, bridge)
    assert mechanism["union_concept_n"] == 3
    assert mechanism["new_concepts_by_doctor"] == [2, 1, 0]
    assert mechanism["later_top1_echo_count"] == 2
