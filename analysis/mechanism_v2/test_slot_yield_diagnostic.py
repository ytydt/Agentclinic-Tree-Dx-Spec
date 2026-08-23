from analysis.mechanism_v2.slot_yield_diagnostic import (
    break_even,
    weighted_slope,
)


def test_weighted_slope_recovers_an_exact_line_and_weights_by_exposure():
    points = [(4.0, 0.70, 10), (8.0, 0.60, 10), (12.0, 0.50, 10)]
    fit = weighted_slope(points)
    assert abs(fit["slope_per_candidate"] + 0.025) < 1e-12
    assert abs(fit["intercept"] - 0.80) < 1e-12
    assert fit["n_arms"] == 3

    # A high-exposure arm must dominate a low-exposure outlier.
    dominated = weighted_slope(points + [(4.0, 0.20, 1)])
    heavy = weighted_slope(points + [(4.0, 0.20, 1000)])
    assert abs(dominated["slope_per_candidate"] + 0.025) < abs(
        heavy["slope_per_candidate"] + 0.025
    )


def test_break_even_threshold_scales_with_exposure_and_vanishes_at_zero_slope():
    # With no conversion penalty any positive exposure gain is net-positive.
    assert break_even(0.639, 0.0, pool=9.0, exposure=42.5) == 0.0

    # MCR working point: conversion 71.1% - 0.74pp/candidate at pool 9.02.
    threshold = break_even(0.711, -0.0074, pool=9.02, exposure=42.5)
    assert 0.48 < threshold < 0.50

    # The requirement is proportional to how much exposure is already at risk.
    doubled = break_even(0.711, -0.0074, pool=9.02, exposure=85.0)
    assert abs(doubled - 2 * threshold) < 1e-12
