from analysis.mechanism_v2.e8_analysis import bootstrap_delta, strip_time


def test_strip_time_preserves_other_fields():
    row = {"event_id": "N1", "observation": "x", "time_anchor": "now", "episode_id": "E"}
    assert strip_time(row) == {"event_id": "N1", "observation": "x"}


def test_bootstrap_delta_is_deterministic():
    pairs = [({"gold_top1": False}, {"gold_top1": True})] * 3
    assert bootstrap_delta(pairs, "x", replicates=100) == [1.0, 1.0]
