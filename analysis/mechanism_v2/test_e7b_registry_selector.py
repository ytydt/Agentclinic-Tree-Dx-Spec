import json

from analysis.mechanism_v2.common import FrozenExactSynonymBridge, clean_vignette
from analysis.mechanism_v2.e7_registry_replay import ARM_TYPED, Concept
from analysis.mechanism_v2.e7b_registry_selector import (
    _paired_exact,
    load_e7a_rows,
    make_blinded_payload,
    reevaluate_surface_endpoints,
    select_cases,
    validate_selector_response,
)


def _concept(cid, name):
    concept = Concept(concept_id=cid, preferred_name=name)
    concept.support_spans = [f"support for {name}"]
    concept.contradict_spans = [f"against {name}"]
    concept.score_logit = 99.0
    concept.generator_views = ["hidden_view"]
    return concept


def test_clean_vignette_removes_options_block():
    assert clean_vignette("Clinical text\n\nOptions:\nA. gold\nB. distractor") == "Clinical text"


def test_frozen_e7b_selection_is_299_affected_plus_101_controls():
    selected = select_cases(load_e7a_rows(), n_controls=101)
    counts = {name: sum(row["selection_stratum"] == name for row in selected) for name in ("unsafe_fold", "control")}
    assert counts == {"unsafe_fold": 299, "control": 101}


def test_blinded_payload_hides_arm_score_view_and_gold():
    concepts = [_concept("C1", "Septic arthritis"), _concept("C2", "Pseudoseptic arthritis")]
    payload, neutral = make_blinded_payload(
        case_key="slice/1",
        vignette="clean text",
        arm=ARM_TYPED,
        concepts=concepts,
        relations=[{"source": "C2", "target": "C1", "evidence": "surface_containment"}],
    )
    blob = json.dumps(payload).lower()
    assert "typed" not in blob
    assert "score" not in blob
    assert "hidden_view" not in blob
    assert "gold" not in blob
    assert set(neutral) == {"D1", "D2"}
    assert payload["non_equivalence_relations"]


def test_selector_schema_validation():
    ids = {"D1", "D2"}
    assert validate_selector_response(
        {"champion_id": "D1", "runner_up_id": "D2", "margin": "low"}, ids
    ) is None
    assert "champion_id" in validate_selector_response(
        {"champion_id": "D9", "runner_up_id": "", "margin": "low"}, ids
    )


def test_exact_mcnemar_uses_stdlib_equivalent_two_sided_tail():
    rows = []
    for index in range(10):
        rows.extend(
            [
                {
                    "case_key": str(index),
                    "arm": "left",
                    "success": True,
                    "gold_top1": index == 0,
                    "champion_label": f"left-{index}",
                },
                {
                    "case_key": str(index),
                    "arm": "right",
                    "success": True,
                    "gold_top1": index != 0,
                    "champion_label": f"right-{index}",
                },
            ]
        )
    result = _paired_exact(rows, "left", "right")
    assert result["left_only_gold_top1"] == 1
    assert result["right_only_gold_top1"] == 9
    assert result["exact_mcnemar_p"] == 0.021484375


def test_surface_endpoint_does_not_credit_hidden_merged_gold_member(tmp_path):
    bridge_path = tmp_path / "bridge.json"
    bridge_path.write_text("{}", encoding="utf-8")
    bridge = FrozenExactSynonymBridge(bridge_path)
    updated = reevaluate_surface_endpoints(
        {
            "gold": "Sarcoidosis",
            "champion_label": "Cardiac sarcoidosis",
            "candidates": [
                {"label": "Cardiac sarcoidosis"},
                {"label": "Sarcoidosis"},
            ],
            # Historical values credited a hidden member of a merged concept.
            "gold_exposure_hit": True,
            "gold_top1": True,
        },
        bridge,
    )
    assert updated["gold_exposure_hit"] is True
    assert updated["gold_top1"] is False
    assert updated["gold_member_top1"] is True
    assert updated["registry_credit_leak"] is True
