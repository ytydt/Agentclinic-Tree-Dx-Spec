from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_a_variant_generation as harness  # noqa: E402


def _branch(
    branch_id: str,
    label: str,
    parent: str,
    level: int,
    *,
    children=None,
    posterior: float = 0.0,
) -> dict:
    return {
        "id": branch_id,
        "label": label,
        "parent": parent,
        "level": level,
        "children": list(children or []),
        "posterior": posterior,
        "prior": 0.0,
        "explanatory_coverage": 0.0,
        "evidence_for": [],
        "level_role": "family" if level == 1 else "specific_disease",
        "classification_axis": "mechanism",
    }


def _tree(*, many: bool = False) -> dict:
    b1_labels = [
        "Alpha disease",
        "Alpha syndrome",
        "Beta",
        "Gamma",
        "Delta",
        "Epsilon",
        "Wrong child",
    ] if many else ["Alpha disease", "Beta"]
    branches = {
        "B1": _branch(
            "B1", "Parent One", "ROOT", 1,
            children=[f"B1.{index}" for index in range(1, len(b1_labels) + 1)],
            posterior=0.7,
        ),
        "B2": _branch(
            "B2", "Parent Two", "ROOT", 1,
            children=["B2.1"], posterior=0.3,
        ),
        "B2.1": _branch("B2.1", "Zeta", "B2", 2),
    }
    for index, label in enumerate(b1_labels, start=1):
        branches[f"B1.{index}"] = _branch(
            f"B1.{index}", label, "B1", 2,
        )
    return {
        "case_id": "case-1",
        "case_summary": "Label-blind clinical vignette.",
        "branches": branches,
        "frontier": ["B1", "B2"],
        "static_evidence_items": [
            {"id": "e1", "content": "A discriminating observed finding."},
        ],
        "static_question": "",
    }


def _trace(arm: str, tree: dict, *, recall=True) -> dict:
    trace = {
        "status": "OK",
        "arm": arm,
        "replicate": 1,
        "case_id": "case-1",
        "identity": {
            "arm": arm,
            "replicate": 1,
            "cache_namespace": f"{arm}/r01",
        },
        "seed_hash": "seed",
        "tree": copy.deepcopy(tree),
        "tree_hash": harness.stable_hash(tree),
        "recall_audit": [],
        "calls": {
            "requested": 0,
            "model": 0,
            "cache_hits": 0,
            "retrieval": 0,
            "mapping": 0,
        },
    }
    if recall:
        trace["recall_audit"] = [
            {
                "parent_id": "B1",
                "candidates": [
                    {"disease": "Recall Alpha", "rrf_score": 0.4},
                    {"disease": "Recall Beta", "rrf_score": 0.3},
                ],
                "knowledge_fragments": [
                    {"id": "f1", "content": "Evidence fragment", "source": "cpg"},
                ],
                "retrieval_calls": 1 if arm == "A" else 0,
            },
            {
                "parent_id": "B2",
                "candidates": [
                    {"disease": "Recall Zeta", "rrf_score": 0.5},
                ],
                "knowledge_fragments": [],
                "retrieval_calls": 1 if arm == "A" else 0,
            },
        ]
        trace["calls"]["retrieval"] = 2 if arm == "A" else 0
    return trace


class _RoutingFake:
    backend_kind = "unit-test-fake"

    def __init__(self):
        self.calls = []

    def call_module(self, module, prompt, payload):
        self.calls.append((module, prompt, copy.deepcopy(payload)))
        if module == "L2A1LocalParentGate":
            return {
                "decision": (
                    "reject"
                    if payload["candidate"]["label"] == "Wrong child"
                    else "accept"
                )
            }
        if module == "L2A2SemanticDedupe":
            rows = payload["candidates"]
            alpha = [
                row["candidate_id"] for row in rows
                if row["label"] in {"Alpha disease", "Alpha syndrome"}
            ]
            clusters = [{"cluster_id": "alpha", "member_ids": alpha}]
            clusters.extend({
                "cluster_id": f"c-{row['candidate_id']}",
                "member_ids": [row["candidate_id"]],
            } for row in rows if row["candidate_id"] not in alpha)
            return {"clusters": clusters}
        if module == "L2A3EvidenceRerank":
            return {
                "ranked_candidate_ids": [
                    row["candidate_id"]
                    for row in reversed(payload["candidates"])
                ]
            }
        if module == "L2A7GlobalAssignment":
            return {
                "assignments": [
                    {
                        "candidate_id": row["candidate_id"],
                        "parent_id": (
                            "B2" if row["candidate_id"] == "B1.1"
                            else row["current_parent_id"]
                        ),
                    }
                    for row in payload["candidates"]
                ]
            }
        if module in {"L2A6CStyleGenerator", "L2A8SiblingContrastGenerator"}:
            return {
                "leaves": [
                    {
                        "label": row["disease"],
                        "candidate_id": row["candidate_id"],
                    }
                    for row in payload["recall_candidates"][:2]
                ]
            }
        if module == "L2A9A10PoolGenerator":
            sample = int(payload["sample_index"])
            output = []
            for row in payload["parent_inputs"]:
                parent_id = row["parent"]["id"]
                leaves = [{"label": f"Common {parent_id}"}]
                if sample <= 3:
                    leaves.append({"label": f"Majority {parent_id}"})
                leaves.append({"label": f"Unique {sample} {parent_id}"})
                output.append({"parent_id": parent_id, "leaves": leaves})
            return {"parents": output}
        if module == "L2A10NBestSelector":
            return {"sample_index": 3}
        raise AssertionError(module)


def _cache(client=None, *, temperature=0.0, path=None):
    return harness.EffectivePayloadCache(
        client or _RoutingFake(),
        path=path,
        model="fake",
        temperature=temperature,
    )


def test_protocol_loads_all_registered_arms_and_freezes_a1_a10(tmp_path):
    path = tmp_path / "protocol.json"
    path.write_text(
        json.dumps(harness.BUILTIN_PROTOCOL),
        encoding="utf-8",
    )

    protocol = harness.load_protocol(path)

    assert set(protocol["arms"]) == {f"A{index}" for index in range(1, 18)}
    assert protocol["arms"]["A4"]["order"] == ["A1", "A2", "A3"]
    assert protocol["arms"]["A5"]["stage"] == "downstream"
    assert protocol["arms"]["A9"]["pool_size"] == 5
    assert protocol["arms"]["A10"]["temperature"] == 0.3
    assert protocol["protocol_hash"]

    broken = copy.deepcopy(harness.BUILTIN_PROTOCOL)
    broken["arms"]["A3"]["top_k"] = 5
    with pytest.raises(ValueError, match="top_k=4"):
        harness.validate_protocol(broken)


def test_effective_cache_uses_payload_and_tree_not_arm_name(tmp_path):
    client = _RoutingFake()
    cache = _cache(client, path=tmp_path / "cache.json")
    payload = {
        "case_context": "case",
        "current_parent": {"id": "B1", "label": "Parent"},
        "candidate": {
            "candidate_id": "B1.1",
            "label": "Alpha",
            "current_parent_id": "B1",
        },
    }

    cache.call(
        "L2A1LocalParentGate", harness.LOCAL_GATE_PROMPT,
        payload, tree_hash="tree-one",
    )
    cache.call(
        "L2A1LocalParentGate", harness.LOCAL_GATE_PROMPT,
        payload, tree_hash="tree-one",
    )
    cache.call(
        "L2A1LocalParentGate", harness.LOCAL_GATE_PROMPT,
        payload, tree_hash="tree-two",
    )

    assert cache.audit() == {"requested": 3, "model": 2, "cache_hits": 1}
    assert len(client.calls) == 2
    assert {
        "effective_payload_sha256", "tree_sha256", "transport", "cache_key",
    }.issubset(cache.call_log[0])
    assert "arm" not in cache.call_log[0]
    with pytest.raises(ValueError, match="gold"):
        cache.call(
            "L2A1LocalParentGate", harness.LOCAL_GATE_PROMPT,
            {"gold_diagnosis": "Alpha"}, tree_hash="tree",
        )


def test_a1_is_local_only_and_rejects_failed_candidates():
    client = _RoutingFake()
    tree = _tree(many=True)

    output, audit = harness.apply_local_parent_gate(tree, _cache(client))

    assert "Wrong child" not in {
        row["label"] for row in harness.l2_leaves(output)
    }
    assert tree == _tree(many=True)
    assert audit["stage"] == "A1-local-parent-gate"
    gate_payloads = [
        payload for module, _prompt, payload in client.calls
        if module == "L2A1LocalParentGate"
    ]
    assert gate_payloads
    assert all("current_parent" in payload for payload in gate_payloads)
    assert all("parents" not in payload for payload in gate_payloads)
    assert all("sibling_parents" not in payload for payload in gate_payloads)


def test_a2_semantic_dedupes_globally_and_caps_each_parent_at_five():
    output, audit = harness.apply_semantic_dedupe_cap(
        _tree(many=True), _cache(), cap=5,
    )

    labels = [row["label"] for row in harness.l2_leaves(output)]
    assert len({"Alpha disease", "Alpha syndrome"} & set(labels)) == 1
    assert all(
        len(parent["children"]) <= 5
        for parent in harness.l1_parents(output)
    )
    assert any(
        row["reason"] == "semantic_duplicate"
        for row in audit["rejections"]
    )
    assert any(
        row["reason"] == "parent_cap"
        for row in audit["rejections"]
    )
    harness.validate_tree(output, parent_cap=5)


def test_a3_reranks_with_evidence_and_keeps_top_four():
    output, audit = harness.apply_evidence_rerank(
        _tree(many=True), _cache(), top_k=4,
    )

    assert len(output["branches"]["B1"]["children"]) == 4
    assert [
        output["branches"][branch_id]["label"]
        for branch_id in output["branches"]["B1"]["children"]
    ] == ["Wrong child", "Epsilon", "Delta", "Gamma"]
    assert audit["schema"]["B1"] == "valid"
    assert audit["top_k"] == 4


def test_a4_applies_a1_then_a2_then_a3_with_continuous_lineage():
    output, lineage = harness.apply_a4_sequence(
        _tree(many=True), _cache(),
    )

    assert [row["stage"] for row in lineage] == [
        "A1-local-parent-gate",
        "A2-semantic-dedupe-cap5",
        "A3-evidence-rerank-top4",
    ]
    assert lineage[0]["output_tree_hash"] == lineage[1]["input_tree_hash"]
    assert lineage[1]["output_tree_hash"] == lineage[2]["input_tree_hash"]
    assert len(output["branches"]["B1"]["children"]) <= 4
    assert "Wrong child" not in {
        row["label"] for row in harness.l2_leaves(output)
    }


def test_a6_and_a8_expose_distinct_generation_payloads_and_stable_ids():
    c_tree = _tree()
    a_trace = _trace("A", _tree())
    client = _RoutingFake()
    cache = _cache(client)

    a6, audit6 = harness.generate_from_a_recall(
        c_tree, a_trace, cache, sibling_contrast=False,
    )
    a8, audit8 = harness.generate_from_a_recall(
        c_tree, a_trace, cache, sibling_contrast=True,
    )
    again, _ = harness.generate_from_a_recall(
        c_tree, a_trace, _cache(_RoutingFake()), sibling_contrast=True,
    )

    assert audit6["interface"] == "A-recall+C-generate"
    assert audit6["sibling_contrast"] is False
    assert audit8["sibling_contrast"] is True
    assert harness.stable_hash(a8) == harness.stable_hash(again)
    assert all(
        branch_id.startswith(f"{branch['parent']}.v")
        for branch_id, branch in a6["branches"].items()
        if branch["level"] == 2
    )
    a6_payloads = [
        payload for module, _prompt, payload in client.calls
        if module == "L2A6CStyleGenerator"
    ]
    a8_payloads = [
        payload for module, _prompt, payload in client.calls
        if module == "L2A8SiblingContrastGenerator"
    ]
    assert all("sibling_parents" not in row for row in a6_payloads)
    assert all("sibling_parents" in row for row in a8_payloads)


def test_a7_global_assignment_can_move_leaf_and_records_lineage():
    output, audit = harness.apply_global_assignment(_tree(), _cache())

    moved = next(
        row for row in audit["parent_movements"]
        if row["source_id"] == "B1.1"
    )
    assert moved["from_parent_id"] == "B1"
    assert moved["to_parent_id"] == "B2"
    assert moved["output_id"] != "B1.1"
    assert output["branches"][moved["output_id"]]["parent"] == "B2"
    harness.validate_tree(output)


def test_a9_a10_share_exact_pool_and_save_matched_first_sample():
    c_trace = _trace("C", _tree(), recall=False)
    a_trace = _trace("A", _tree())
    client = _RoutingFake()
    protocol = harness.load_protocol()
    base_cache = _cache(client)
    pool_cache = _cache(
        client, temperature=harness.POOL_TEMPERATURE,
    )

    records = harness.run_case_variants(
        c_trace=c_trace,
        a_trace=a_trace,
        protocol=protocol,
        base_cache=base_cache,
        pool_cache=pool_cache,
        arms=("A9", "A10"),
        backend="unit-test-fake",
        model="fake",
    )

    assert (
        records["A9"]["shared_pool"]["pool_hash"]
        == records["A10"]["shared_pool"]["pool_hash"]
    )
    assert records["A9"]["shared_pool"]["shared_pool_id"] == harness.SHARED_POOL_ID
    assert records["A9"]["arm_slug"] == "a9-stability-consensus"
    assert records["A10"]["arm_slug"] == "a10-n-best-tree-selection"
    assert records["A9"]["identity"]["arm_id"] == "A9"
    assert len(records["A9"]["shared_pool"]["sample_tree_hashes"]) == 5
    assert records["A9"]["matched_first_sample"]["sample_index"] == 1
    assert (
        records["A9"]["matched_first_sample"]["tree_hash"]
        == records["A9"]["shared_pool"]["sample_tree_hashes"][0]
    )
    assert records["A10"]["transform_lineage"][0][
        "selected_sample_index"
    ] == 3
    assert sum(
        module == "L2A9A10PoolGenerator"
        for module, _prompt, _payload in client.calls
    ) == 5
    assert sum(
        module == "L2A10NBestSelector"
        for module, _prompt, _payload in client.calls
    ) == 1
    a9_labels = {row["label"] for row in harness.l2_leaves(records["A9"]["tree"])}
    assert {"Common B1", "Majority B1"}.issubset(a9_labels)
    assert not any(label.startswith("Unique") for label in a9_labels)
    harness.validate_variant_trace(records["A9"])
    harness.validate_variant_trace(records["A10"])


def test_trace_validation_rejects_tree_and_lineage_drift():
    c_trace = _trace("C", _tree(), recall=False)
    a_trace = _trace("A", _tree())
    tree = _tree()
    trace = harness.make_trace(
        arm="A-raw",
        c_trace=c_trace,
        a_trace=a_trace,
        tree=tree,
        lineage=[harness._stage_audit("replay", tree, tree)],
        protocol_hash="protocol",
        backend="unit-test-fake",
        model="fake",
    )
    harness.validate_variant_trace(trace)

    drift = copy.deepcopy(trace)
    drift["tree"]["branches"]["B1"]["label"] = "changed"
    with pytest.raises(ValueError, match="tree hash"):
        harness.validate_variant_trace(drift)

    discontinuous = copy.deepcopy(trace)
    discontinuous["transform_lineage"].append(
        harness._stage_audit("other", tree, tree),
    )
    discontinuous["transform_lineage"][1]["input_tree_hash"] = "wrong"
    with pytest.raises(ValueError, match="discontinuous"):
        harness.validate_variant_trace(discontinuous)


def test_deterministic_cli_is_explicitly_non_model_and_a5_is_excluded():
    args = harness.parse_args(["generate"])

    assert args.backend == "deterministic"
    assert harness.POOL_SIZE == 5
    assert harness.POOL_TEMPERATURE == 0.3
    assert "A5" not in harness.GENERATION_ARMS
    assert harness.ARM_SPECS["A5"]["stage"] == "downstream"
    fake = harness.DeterministicFakeClient()
    assert fake.backend_kind == "deterministic-test-double"


def test_generate_refuses_to_overwrite_real_model_traces(tmp_path, monkeypatch):
    case_id = "case-1"
    ab_root = tmp_path / "ab"
    out_root = tmp_path / "out"
    for arm in ("C", "A"):
        path = (
            ab_root / "generation" / "traces" / arm
            / f"r01__{case_id}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = _tree()
        path.write_text(
            json.dumps(_trace(arm, tree)),
            encoding="utf-8",
        )
    (ab_root / "generation").mkdir(parents=True, exist_ok=True)
    (ab_root / "generation" / "manifest.json").write_text(
        json.dumps({
            "replicates": 1,
            "manifest_hash": "src",
            "tree_hashes": {
                f"C/r01/{case_id}": harness.stable_hash(_tree()),
                f"A/r01/{case_id}": harness.stable_hash(_tree()),
            },
        }),
        encoding="utf-8",
    )
    existing_path = (
        out_root / "generation" / "traces" / "A-raw"
        / f"r01__{case_id}.json"
    )
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text(
        json.dumps({
            "status": "OK",
            "arm": "A-raw",
            "identity": {"arm": "A-raw"},
            "result_provenance": {"real_model_result": True},
        }),
        encoding="utf-8",
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(
        json.dumps(harness.BUILTIN_PROTOCOL),
        encoding="utf-8",
    )
    args = harness.parse_args([
        "generate",
        "--protocol", str(protocol_path),
        "--ab-output-dir", str(ab_root),
        "--output-dir", str(out_root),
        "--arms", "A-raw",
        "--replicates", "1",
        "--backend", "deterministic",
    ])
    with pytest.raises(FileExistsError, match="real model trace"):
        harness.generate(args)
