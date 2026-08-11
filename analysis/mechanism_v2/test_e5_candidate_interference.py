from analysis.mechanism_v2.common import FrozenExactSynonymBridge, ROOT
from analysis.mechanism_v2.e5_candidate_interference import (
    ADD_COMPONENT,
    ADD_PARENT,
    ADD_SIBLING,
    ADD_SYNONYM,
    ADD_UNRELATED,
    ARMS,
    BASE,
    RELATIONS,
    REMOVE,
    WIDTH6,
    WIDTH8,
    pool_for_arm,
    select_cases,
    validate_perturbation,
    validate_selector,
)


def _fixture():
    bridge = FrozenExactSynonymBridge(ROOT / "data/knowledge_raw/disease_name_bridge.json")
    job = select_cases(1, bridge)[0]
    rows = [
        {"relation": relation, "label": f"synthetic {relation} diagnosis", "valid": True, "rationale": "test"}
        for relation in RELATIONS
    ]
    width = [
        {"label": f"synthetic matched distractor {index}", "valid": True, "rationale": "test"}
        for index in range(4)
    ]
    perturbation = {"success": True, "response": {"perturbations": rows, "width_distractors": width}}
    return job, perturbation


def test_nested_and_single_intervention_pool_widths():
    job, perturbation = _fixture()
    expected = {
        BASE: 4,
        REMOVE: 3,
        ADD_PARENT: 5,
        ADD_SIBLING: 5,
        ADD_UNRELATED: 5,
        ADD_SYNONYM: 5,
        ADD_COMPONENT: 5,
        WIDTH6: 6,
        WIDTH8: 8,
    }
    for arm in ARMS:
        pool = pool_for_arm(job, perturbation, arm)
        assert len(pool) == expected[arm]
        assert sum(bool(row.get("audit_is_gold")) for row in pool) == 1
    base_ids = {row["candidate_id"] for row in pool_for_arm(job, perturbation, BASE)}
    assert base_ids < {row["candidate_id"] for row in pool_for_arm(job, perturbation, WIDTH6)}
    assert {row["candidate_id"] for row in pool_for_arm(job, perturbation, WIDTH6)} < {
        row["candidate_id"] for row in pool_for_arm(job, perturbation, WIDTH8)
    }


def test_validators_reject_missing_or_partial_contracts():
    job, perturbation = _fixture()
    assert validate_perturbation(perturbation["response"], job) is None
    assert validate_perturbation({"perturbations": []}, job)
    ids = {"B1", "B2", "B3"}
    valid = {
        "ranking": [
            {"candidate_id": "B1"},
            {"candidate_id": "B2"},
            {"candidate_id": "B3"},
        ],
        "champion_id": "B1",
        "runner_up_id": "B2",
        "top1_probability": 0.6,
        "margin": "low",
    }
    assert validate_selector(valid, ids) is None
    invalid = dict(valid, ranking=valid["ranking"][:-1])
    assert validate_selector(invalid, ids)


def test_base_arm_does_not_condition_on_perturbation_success():
    job, perturbation = _fixture()
    assert len(pool_for_arm(job, {"success": False, "response": {}}, BASE)) == 4
    for failed in (
        {"success": False, "response": {}},
        {"success": False, "response": perturbation["response"]},
    ):
        try:
            pool_for_arm(job, failed, ADD_PARENT)
        except AssertionError:
            pass
        else:
            raise AssertionError("typed add arm must fail closed without a successful frozen perturbation")
