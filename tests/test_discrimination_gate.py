"""§13 discrimination gate regression: non-discriminative turns must not bleed a
broad correct family via renormalization; discriminative turns are unchanged.

Root cause (documented in RESIDUAL_MISS_ROOTCAUSE_AND_MECE.md §13): softmax-style
renormalization lets a lone ``weak_for`` on a distractor dilute every other family
each turn, so a broad correct family that is merely ``neutral`` decays
monotonically even when nothing argues against it. The gate freezes fully-mild
turns. Default OFF must be byte-identical to the legacy update.
"""

import math

from agentclinic_tree_dx.updater import (
    ordinal_update, bayesian_lr_update, calculator_update)
from agentclinic_tree_dx.state import Branch


def _mk(labels_priors):
    d = {}
    for i, (lab, p) in enumerate(labels_priors):
        d[f"b{i}"] = Branch(
            id=f"b{i}", label=lab, parent="ROOT", level=1, status="live",
            prior=p, posterior=p, danger=0, actionability=0,
            explanatory_coverage=0, level_role="family", classification_axis="",
            representative_diseases=[], askable_discriminators=[],
            requestable_discriminators=[], turn_cost_to_refine=0,
            diagnosis_commitment_gain=0, interrupt_relevance=0)
    return d


_INIT = [("GOLD", 0.30), ("A", 0.25), ("B", 0.20), ("C", 0.15), ("Other", 0.10)]


def test_default_off_is_legacy_ordinal():
    br = _mk(_INIT)
    eff = {"branch_effects": {"b0": "neutral", "b1": "weak_for"}}
    assert ordinal_update(br, eff) == ordinal_update(br, eff, gate=False)


def test_gate_freezes_weak_only_turn():
    br = _mk(_INIT)
    eff = {"branch_effects": {"b0": "neutral", "b1": "weak_for", "b2": "weak_against"}}
    post = ordinal_update(br, eff, gate=True)
    # gold (and everyone) unchanged — mild turn is non-discriminative
    for bid, b in br.items():
        assert math.isclose(post[bid], b.posterior, abs_tol=1e-9)


def test_gate_lets_discriminative_turn_through():
    br = _mk(_INIT)
    eff = {"branch_effects": {"b1": "strong_for"}}  # one strong label → real turn
    gated = ordinal_update(br, eff, gate=True)
    ungated = ordinal_update(br, eff, gate=False)
    assert gated == ungated
    assert gated["b1"] > br["b1"].posterior     # distractor rose
    assert gated["b0"] < br["b0"].posterior     # gold diluted by a REAL update


def test_gate_stops_monotonic_decay_over_turns():
    br = _mk(_INIT)
    dist = ["b1", "b2", "b3"]
    for t in range(5):
        eff = {"branch_effects": {k: "neutral" for k in br}}
        eff["branch_effects"][dist[t % 3]] = "weak_for"
        post = ordinal_update(br, eff, gate=True)
        for bid, b in br.items():
            b.prior, b.posterior = b.posterior, post[bid]
    assert math.isclose(br["b0"].posterior, 0.30, abs_tol=1e-9)


def test_bayesian_gate_freezes_all_mild_lrs():
    br = _mk(_INIT)
    branch_lr = {"b0": 1.0, "b1": 1.3, "b2": 0.8}  # all within [1/1.5, 1.5]
    post = bayesian_lr_update(br, branch_lr, gate=True)
    for bid, b in br.items():
        assert math.isclose(post[bid], b.posterior, abs_tol=1e-9)


def test_bayesian_gate_passes_strong_lr():
    br = _mk(_INIT)
    branch_lr = {"b1": 4.0}  # outside band → discriminative
    gated = bayesian_lr_update(br, branch_lr, gate=True)
    ungated = bayesian_lr_update(br, branch_lr, gate=False)
    assert gated == ungated
    assert gated["b1"] > br["b1"].posterior


def test_calculator_update_forwards_gate():
    br = _mk(_INIT)
    ann = {"branch_lr": {"b0": 1.1, "b1": 0.9}}  # mild → frozen under gate
    post = calculator_update(br, ann, gate=True)
    for bid, b in br.items():
        assert math.isclose(post[bid], b.posterior, abs_tol=1e-9)
