from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v2.json"


def _protocol() -> dict:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_protocol_v2_namespace_and_bindings():
    protocol = _protocol()
    assert protocol["protocol_version"] == 2
    assert protocol["protocol_namespace"] == "l2-a-variant-v2"
    assert protocol["frozen"] is True
    for binding in protocol["source_bindings"].values():
        if "path" not in binding or "sha256" not in binding:
            continue
        path = ROOT / binding["path"]
        if path.is_file():
            assert _sha256(path) == binding["sha256"]


def test_protocol_v2_matrix_and_gates():
    protocol = _protocol()
    assert protocol["matrix"]["headline_arms"] == [
        "C-prod-v2",
        "A-raw-v2",
        "A4-v2-ref",
        "A4+A14-v2-ref",
        "A18-parent-safe",
        "A19-budget-safe",
        "A20-generation-v2",
        "A21-generation-v2+F4",
        "A22-adaptive-local-rescue",
    ]
    assert protocol["endpoints"]["primary"]["id"] == "resilient_legacy_actual_top2"
    assert protocol["candidate_pool_semantics"]["cap_after_dedupe_hard_drop_rate_must_be"] == 0.0
    assert protocol["development"]["entry_gate"]["hard_all_required"][
        "cap_after_dedupe_hard_drop_rate"
    ] == 0.0
    assert protocol["technical_resilience"]["applies_to_all_arms"] is True
    assert protocol["endpoint_policy"]["unified_direct_role"] == "mechanistic_only"
