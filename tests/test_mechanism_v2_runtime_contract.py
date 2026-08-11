from analysis.mechanism_v2.runtime_contract import (
    aggregate_telemetry,
    stable_seed,
    validate_workers,
)


def test_stable_seed_is_process_independent():
    assert stable_seed("E5", "case-1", "sibling") == stable_seed(
        "E5", "case-1", "sibling"
    )
    assert stable_seed("E5", "case-1", "sibling") != stable_seed(
        "E5", "case-1", "parent"
    )


def test_worker_contract_enforces_user_caps():
    assert validate_workers(50, rag=False) == 50
    assert validate_workers(25, rag=True) == 25
    for workers, rag in ((51, False), (26, True), (0, False)):
        try:
            validate_workers(workers, rag=rag)
        except ValueError:
            pass
        else:
            raise AssertionError((workers, rag))


def test_telemetry_aggregation_separates_semantic_and_physical_calls():
    summary = aggregate_telemetry(
        [
            {
                "semantic_calls": 1,
                "physical_attempts": 2,
                "input_tokens": 10,
                "output_tokens": 3,
                "latency_seconds": 1.5,
                "success": True,
                "providers": ["a"],
                "transports": ["stdlib_openrouter"],
            },
            {
                "semantic_calls": 1,
                "physical_attempts": 1,
                "input_tokens": 8,
                "output_tokens": 2,
                "latency_seconds": 1.0,
                "success": False,
                "providers": ["b"],
                "transports": ["openai_sdk"],
            },
        ]
    )
    assert summary["semantic_calls"] == 2
    assert summary["physical_attempts"] == 3
    assert summary["failed_semantic_calls"] == 1
    assert summary["providers"] == ["a", "b"]
