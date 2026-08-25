"""
MedEinst evaluation metrics.

Paper: https://arxiv.org/abs/2601.06636
§3.5 — Baseline Accuracy, Robust Accuracy, Bias Trap Rate
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from src.data import Case
from src.utils import diagnoses_match


Predictor = Callable[[str], str]


@dataclass
class MetricReport:
    """§3.5 metrics. Pair metrics are None when the corpus has no traps."""

    n_total: int
    n_correct_control: int
    acc_base: float
    acc_rob: float | None
    r_bias: float | None
    unpaired: bool


def baseline_accuracy(n_correct_control: int, n_total: int) -> float:
    """§3.5 Acc_base = |S_correct_control| / N_total."""
    if n_total == 0:
        return 0.0
    return n_correct_control / n_total


def robust_accuracy(n_robust: int, n_total: int) -> float:
    """§3.5 Acc_rob = (1/N) Σ I(f(x^c)=ygt ∧ f(x^t)=ybias)."""
    if n_total == 0:
        return 0.0
    return n_robust / n_total


def bias_trap_rate(n_trapped: int, n_correct_control: int) -> float:
    """§3.5 R_bias = (1/|S_correct_control|) Σ_{i∈S} I(f(x^t)=ygt).

    Trap = model still emits the *control* label on the trap narrative.
    """
    if n_correct_control == 0:
        return 0.0
    return n_trapped / n_correct_control


def evaluate_cases(cases: Sequence[Case], predict: Predictor) -> MetricReport:
    """Run f on each case. MCR400 is unpaired → Acc_rob and R_bias are None."""
    n_total = len(cases)
    n_correct_control = 0
    n_robust = 0
    n_trapped = 0
    any_pair = False
    for case in cases:
        if case.is_pair and case.x_c is not None and case.x_t is not None and case.y_bias is not None:
            any_pair = True
            pred_c = predict(case.x_c)
            pred_t = predict(case.x_t)
            control_ok = diagnoses_match(pred_c, case.y_gt)
            if control_ok:
                n_correct_control += 1
                if diagnoses_match(pred_t, case.y_bias):
                    n_robust += 1
                if diagnoses_match(pred_t, case.y_gt):
                    n_trapped += 1
        else:
            pred = predict(case.x)
            if diagnoses_match(pred, case.y_gt):
                n_correct_control += 1
    acc_base = baseline_accuracy(n_correct_control, n_total)
    if any_pair:
        return MetricReport(
            n_total=n_total,
            n_correct_control=n_correct_control,
            acc_base=acc_base,
            acc_rob=robust_accuracy(n_robust, n_total),
            r_bias=bias_trap_rate(n_trapped, n_correct_control),
            unpaired=False,
        )
    return MetricReport(
        n_total=n_total,
        n_correct_control=n_correct_control,
        acc_base=acc_base,
        acc_rob=None,
        r_bias=None,
        unpaired=True,
    )


def evaluate_agent(cases: Iterable[Case], agent_predict: Predictor) -> MetricReport:
    return evaluate_cases(list(cases), agent_predict)
