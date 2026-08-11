import time
from concurrent.futures import ThreadPoolExecutor

from analysis.mechanism_v2.online_runner import OnlineJSONCaller, assert_target_blind


class FakeClient:
    def __init__(self):
        self.calls = 0

    def configure_telemetry(self, path):
        self.telemetry_path = path

    def call_module(self, module, prompt, payload):
        self.calls += 1
        return {"champion_id": "D1"}


def test_online_caller_caches_validated_response(tmp_path):
    fake = FakeClient()
    caller = OnlineJSONCaller(
        out_dir=tmp_path,
        model="test-model",
        telemetry_path=tmp_path / "telemetry.jsonl",
        client_factory=lambda: fake,
    )
    kwargs = {
        "module": "test",
        "prompt": "return json",
        "payload": {"case_id": "c1", "vignette": "text"},
        "validator": lambda row: None if row.get("champion_id") == "D1" else "bad",
    }
    first = caller.call(**kwargs)
    second = caller.call(**kwargs)
    assert first.success and not first.cache_hit
    assert second.success and second.cache_hit
    assert fake.calls == 1


def test_online_caller_fails_closed_on_gold_key(tmp_path):
    caller = OnlineJSONCaller(
        out_dir=tmp_path,
        model="test-model",
        telemetry_path=tmp_path / "telemetry.jsonl",
        client_factory=FakeClient,
    )
    try:
        caller.call(
            module="test",
            prompt="return json",
            payload={"case_id": "c1", "gold": "forbidden"},
        )
    except AssertionError as exc:
        assert "target leak" in str(exc)
    else:
        raise AssertionError("gold-bearing payload must be rejected")


def test_target_blind_allows_candidate_labels_but_not_target_fields():
    assert_target_blind({"candidates": [{"label": "Disease A"}]})


def test_online_caller_single_flights_identical_concurrent_payloads(tmp_path):
    class SlowFakeClient(FakeClient):
        def call_module(self, module, prompt, payload):
            time.sleep(0.05)
            return super().call_module(module, prompt, payload)

    fake = SlowFakeClient()
    caller = OnlineJSONCaller(
        out_dir=tmp_path,
        model="test-model",
        telemetry_path=tmp_path / "telemetry.jsonl",
        client_factory=lambda: fake,
    )
    kwargs = {
        "module": "same",
        "prompt": "same",
        "payload": {"case_id": "same", "vignette": "same"},
        "validator": lambda row: None,
    }
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda _: caller.call(**kwargs), range(6)))
    assert fake.calls == 1
    assert sum(not outcome.cache_hit for outcome in outcomes) == 1
    assert sum(outcome.cache_hit for outcome in outcomes) == 5


def test_cache_only_fails_closed_instead_of_calling_model(tmp_path):
    fake = FakeClient()
    caller = OnlineJSONCaller(
        out_dir=tmp_path,
        model="test-model",
        telemetry_path=tmp_path / "telemetry.jsonl",
        client_factory=lambda: fake,
    )
    try:
        caller.call(
            module="missing",
            prompt="missing",
            payload={"case_id": "missing"},
            cache_only=True,
        )
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("cache-only reconstruction must fail closed on a miss")
    assert fake.calls == 0
