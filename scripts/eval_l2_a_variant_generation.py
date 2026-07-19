#!/usr/bin/env python3
"""Label-blind A1--A10 L2 generation/transform harness.

The harness replays the frozen C/A traces produced by
``eval_l2_branch_generation_ab.py``.  A1/A2/A3/A4/A7 are transforms of the
frozen A tree, A6/A8 expose regeneration interfaces, and A9/A10 share one
N=5, temperature=0.3 generation pool.  A5 is registered but intentionally
deferred to the downstream harness.

The default deterministic backend is a test double.  Its manifests are
explicitly marked as non-model, research-only output.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")

import eval_l2_branch_generation_ab as ab  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)


SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
POOL_SIZE = 5
POOL_TEMPERATURE = 0.3
SHARED_POOL_ID = "a9-a10-n5-t03"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_AB_OUTPUT = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_OUTPUT = ROOT / "logs" / "l2_a_variant_matrix_v1"
DEFAULT_PROTOCOL_PATH = (
    ROOT / "eval_fixtures" / "l2_a_variant_protocol_v1.json"
)

ARM_SPECS: dict[str, dict[str, Any]] = {
    "A1": {"slug": "a1-local-parent-gate", "stage": "generation"},
    "A2": {
        "slug": "a2-semantic-dedupe-cap",
        "stage": "generation",
        "parent_cap": 5,
    },
    "A3": {
        "slug": "a3-evidence-rerank",
        "stage": "generation",
        "top_k": 4,
    },
    "A4": {
        "slug": "a4-gated-deduped-reranked",
        "stage": "generation",
        "order": ["A1", "A2", "A3"],
    },
    "A5": {"slug": "a5-raw-global-arbiter", "stage": "downstream"},
    "A6": {"slug": "a6-a-recall-c-generate", "stage": "generation"},
    "A7": {"slug": "a7-global-parent-assignment", "stage": "generation"},
    "A8": {"slug": "a8-sibling-contrastive-generation", "stage": "generation"},
    "A9": {
        "slug": "a9-stability-consensus",
        "stage": "generation",
        "pool_size": POOL_SIZE,
        "temperature": POOL_TEMPERATURE,
        "shared_pool_id": SHARED_POOL_ID,
    },
    "A10": {
        "slug": "a10-n-best-tree-selection",
        "stage": "generation",
        "pool_size": POOL_SIZE,
        "temperature": POOL_TEMPERATURE,
        "shared_pool_id": SHARED_POOL_ID,
    },
}
CONTROL_ARMS = ("C-prod", "A-raw")
GENERATION_ARMS = (
    *CONTROL_ARMS,
    "A1", "A2", "A3", "A4", "A6", "A7", "A8", "A9", "A10",
)

BUILTIN_PROTOCOL: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "asset_kind": "l2_a_variant_protocol",
    "name": "A1-A17 variant matrix",
    "controls": {
        "C-prod": {"source": "frozen-C"},
        "A-raw": {"source": "frozen-A"},
    },
    "arms": {
        **copy.deepcopy(ARM_SPECS),
        **{
            f"A{index}": {
                "slug": slug,
                "stage": "downstream",
            }
            for index, slug in (
                (11, "a11-core-shadow"),
                (12, "a12-evidence-support-gate"),
                (13, "a13-counterfactual-prune"),
                (14, "a14-dynamic-f4"),
                (15, "a15-multi-champion"),
                (16, "a16-gated-global-leaf-arbiter"),
                (17, "a17-prior-calibration"),
            )
        },
    },
}

LOCAL_GATE_PROMPT = """Decide only whether the candidate disease belongs under
the supplied current parent. Do not compare with other parents. Return strict
JSON: {"decision":"accept"|"reject","reason":"short"}."""

SEMANTIC_DEDUPE_PROMPT = """Cluster clinically synonymous candidate leaves
within this one tree. Return strict JSON:
{"clusters":[{"cluster_id":"stable label","member_ids":["allowed id", ...]}]}.
Every member_id must come from the payload; omit uncertain merges."""

EVIDENCE_RERANK_PROMPT = """Rank the supplied candidate IDs by support from the
case evidence. Return strict JSON: {"ranked_candidate_ids":[...]} using only
allowed IDs, without duplicates."""

GLOBAL_ASSIGNMENT_PROMPT = """Jointly assign each candidate to the single best
supplied parent, or reject it. Return strict JSON:
{"assignments":[{"candidate_id":"id","parent_id":"allowed id or REJECT"}]}."""

A6_GENERATION_PROMPT = """Generate concrete disease leaves for the supplied
parent using the case evidence and A-recall candidates. Follow the C-style
compact leaf budget. Return strict JSON:
{"leaves":[{"label":"disease","candidate_id":"optional source id"}]}."""

SIBLING_CONTRAST_PROMPT = """Generate concrete disease leaves for the current
parent. Contrast it against the supplied sibling parents and avoid leaves that
fit a sibling better. Return strict JSON:
{"leaves":[{"label":"disease","candidate_id":"optional source id"}]}."""

POOL_GENERATION_PROMPT = """Generate one complete L2 leaf proposal for every
supplied L1 parent using case evidence, A recall, and sibling contrast. Return
strict JSON: {"parents":[{"parent_id":"allowed id","leaves":[{"label":"disease",
"candidate_id":"optional source id"}]}]}."""

NBEST_PROMPT = """Select the strongest complete tree proposal using only case
evidence and the closed tree summaries. Return strict JSON:
{"sample_index":1} where sample_index is one supplied integer."""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    ab._atomic_json(path, payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normal(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def canonical_label(value: Any) -> str:
    """Conservative deterministic key; semantic merges require a client."""
    return " ".join(re.findall(r"[a-z0-9]+", _normal(value)))


def _normalise_arm_rows(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, Mapping):
        return {
            str(arm): copy.deepcopy(dict(spec))
            for arm, spec in value.items()
            if isinstance(spec, Mapping)
        }
    if isinstance(value, list):
        output = {}
        for raw in value:
            if not isinstance(raw, Mapping):
                raise ValueError("protocol arm rows must be objects")
            arm = str(raw.get("id") or raw.get("arm") or "")
            if not arm:
                raise ValueError("protocol arm row is missing id")
            output[arm] = copy.deepcopy(dict(raw))
        return output
    raise ValueError("protocol arms must be an object or array")


def validate_protocol(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the A registry without mutating its source."""
    doc = copy.deepcopy(dict(protocol))
    if int(doc.get("protocol_version") or 0) != PROTOCOL_VERSION:
        raise ValueError("unsupported A-variant protocol version")
    arms = _normalise_arm_rows(doc.get("arms"))
    missing = [f"A{index}" for index in range(1, 18) if f"A{index}" not in arms]
    if missing:
        raise ValueError(f"protocol is missing registered arms: {missing}")
    for arm, expected in ARM_SPECS.items():
        actual = arms[arm]
        if str(actual.get("slug") or "") != expected["slug"]:
            raise ValueError(f"{arm}: protocol slug mismatch")
        if (
            actual.get("stage") is not None
            and str(actual.get("stage")) != expected["stage"]
        ):
            raise ValueError(f"{arm}: protocol stage mismatch")
    parameters = {
        arm: (
            dict(row.get("parameters") or {})
            if isinstance(row.get("parameters"), Mapping)
            else row
        )
        for arm, row in arms.items()
    }
    if int(
        parameters["A2"].get(
            "final_leaf_cap_per_parent",
            parameters["A2"].get("parent_cap"),
        ) or 0
    ) != 5:
        raise ValueError("A2 must freeze parent_cap=5")
    if int(
        parameters["A3"].get(
            "top_k_per_parent",
            parameters["A3"].get("top_k"),
        ) or 0
    ) != 4:
        raise ValueError("A3 must freeze top_k=4")
    if list(
        parameters["A4"].get(
            "components",
            parameters["A4"].get("order"),
        ) or ()
    ) != ["A1", "A2", "A3"]:
        raise ValueError("A4 must freeze order A1 -> A2 -> A3")
    for arm in ("A9", "A10"):
        if int(parameters[arm].get("pool_size") or 0) != POOL_SIZE:
            raise ValueError(f"{arm} must freeze N=5")
        if float(parameters[arm].get("temperature", -1)) != POOL_TEMPERATURE:
            raise ValueError(f"{arm} must freeze temperature=0.3")
        pool_id = str(
            parameters[arm].get("shared_pool_id") or SHARED_POOL_ID
        )
        if pool_id != SHARED_POOL_ID:
            raise ValueError(f"{arm} must freeze shared_pool_id={SHARED_POOL_ID}")
    if str(
        parameters["A9"].get("shared_pool_id") or SHARED_POOL_ID
    ) != str(
        parameters["A10"].get("shared_pool_id") or SHARED_POOL_ID
    ):
        raise ValueError("A9/A10 must share one shared_pool_id")
    doc["arms"] = arms
    controls = doc.get("controls") or {}
    doc["controls"] = _normalise_arm_rows(controls)
    return doc


def load_protocol(path: Path | None = None) -> dict[str, Any]:
    """Load the frozen JSON protocol, falling back only when it is absent."""
    if path is None and DEFAULT_PROTOCOL_PATH.is_file():
        path = DEFAULT_PROTOCOL_PATH
    source = _read_json(path) if path is not None else BUILTIN_PROTOCOL
    doc = validate_protocol(source)
    if path is not None and doc.get("frozen") is True:
        for binding in (doc.get("source_bindings") or {}).values():
            if not isinstance(binding, Mapping) or not binding.get("path"):
                continue
            bound_path = ROOT / str(binding["path"])
            if not bound_path.is_file():
                raise ValueError(f"protocol source binding is missing: {bound_path}")
            declared = str(binding.get("sha256") or "")
            if declared and _sha256(bound_path) != declared:
                raise ValueError(
                    f"protocol source binding hash mismatch: {binding['path']}"
                )
    protocol_hash = _sha256(path) if path is not None else stable_hash(doc)
    doc["protocol_hash"] = protocol_hash
    doc["protocol_sha256"] = protocol_hash
    doc["protocol_source"] = (
        str(path.resolve()) if path is not None else "builtin"
    )
    return doc


def _branches(tree: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    branches = tree.get("branches")
    if not isinstance(branches, Mapping):
        raise ValueError("tree branches must be an object")
    return branches  # type: ignore[return-value]


def l1_parents(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            copy.deepcopy(dict(branch))
            for branch in _branches(tree).values()
            if isinstance(branch, Mapping) and int(branch.get("level") or 0) == 1
        ),
        key=lambda row: str(row.get("id") or ""),
    )


def l2_leaves(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            copy.deepcopy(dict(branch))
            for branch in _branches(tree).values()
            if isinstance(branch, Mapping) and int(branch.get("level") or 0) == 2
        ),
        key=lambda row: (
            str(row.get("parent") or ""),
            str(row.get("id") or ""),
        ),
    )


def validate_tree(tree: Mapping[str, Any], *, parent_cap: int | None = None) -> None:
    """Validate key/id identity, L1/L2 ownership, and optional final cap."""
    branches = _branches(tree)
    referenced: set[str] = set()
    for branch_id, branch in branches.items():
        if not isinstance(branch, Mapping):
            raise ValueError(f"branch is not an object: {branch_id}")
        if str(branch.get("id") or "") != str(branch_id):
            raise ValueError(f"branch key/id mismatch: {branch_id}")
        if int(branch.get("level") or 0) != 1:
            continue
        children = [str(value) for value in branch.get("children") or ()]
        if len(children) != len(set(children)):
            raise ValueError(f"duplicate child IDs: {branch_id}")
        if parent_cap is not None and len(children) > parent_cap:
            raise ValueError(f"parent cap exceeded: {branch_id}")
        for child_id in children:
            child = branches.get(child_id)
            if not isinstance(child, Mapping):
                raise ValueError(f"missing child: {child_id}")
            if int(child.get("level") or 0) != 2:
                raise ValueError(f"child is not L2: {child_id}")
            if str(child.get("parent") or "") != str(branch_id):
                raise ValueError(f"invalid parent backlink: {child_id}")
            referenced.add(child_id)
    for branch_id, branch in branches.items():
        if not isinstance(branch, Mapping) or int(branch.get("level") or 0) != 2:
            continue
        parent_id = str(branch.get("parent") or "")
        parent = branches.get(parent_id)
        if not isinstance(parent, Mapping) or int(parent.get("level") or 0) != 1:
            raise ValueError(f"missing L1 parent: {branch_id}")
        if str(branch_id) not in referenced:
            raise ValueError(f"orphan L2 leaf: {branch_id}")


def case_evidence(tree: Mapping[str, Any]) -> dict[str, Any]:
    items = []
    for index, raw in enumerate(tree.get("static_evidence_items") or ()):
        if isinstance(raw, Mapping):
            item = {
                key: value
                for key, value in raw.items()
                if key in {"id", "content", "text", "concept", "polarity", "value"}
            }
        else:
            item = {"id": f"e{index + 1}", "content": str(raw)}
        items.append(item)
    payload = {
        "case_context": str(tree.get("case_summary") or "")[:5000],
        "evidence": items[:40],
    }
    assert_no_gold_leak(payload)
    return payload


def _leaf_row(leaf: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": str(leaf.get("id") or ""),
        "label": str(leaf.get("label") or ""),
        "current_parent_id": str(leaf.get("parent") or ""),
        "level_role": str(leaf.get("level_role") or ""),
    }


def _parent_row(parent: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(parent.get("id") or ""),
        "label": str(parent.get("label") or ""),
        "classification_axis": str(parent.get("classification_axis") or ""),
    }


def stable_leaf_id(
    parent_id: str,
    label: str,
    source_identity: str,
    reserved: set[str],
) -> str:
    """Create an order-independent parent-namespaced generated ID."""
    digest = stable_hash({
        "parent_id": parent_id,
        "label": canonical_label(label),
        "source_identity": source_identity,
    })
    width = 10
    while True:
        candidate = f"{parent_id}.v{digest[:width]}"
        if candidate not in reserved:
            return candidate
        width += 2
        if width > len(digest):
            raise RuntimeError("stable leaf ID collision")


def _new_leaf(
    branch_id: str,
    parent: Mapping[str, Any],
    label: str,
    *,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if source is not None:
        leaf = copy.deepcopy(dict(source))
        leaf.update({
            "id": branch_id,
            "label": label,
            "parent": str(parent["id"]),
            "level": 2,
            "children": [],
        })
        return leaf
    return {
        "id": branch_id,
        "label": label,
        "parent": str(parent["id"]),
        "level": 2,
        "status": "live",
        "prior": 0.0,
        "posterior": 0.0,
        "danger": 0.0,
        "actionability": 0.0,
        "explanatory_coverage": 0.0,
        "expand_score": 0.0,
        "evidence_for": [],
        "evidence_against": [],
        "unresolved_questions": [],
        "children": [],
        "closure_reason": "",
        "reopen_triggers": [],
        "askable_discriminators": [],
        "requestable_discriminators": [],
        "turn_cost_to_refine": 0.0,
        "diagnosis_commitment_gain": 0.0,
        "interrupt_relevance": 0.0,
        "level_role": "specific_disease",
        "classification_axis": str(
            parent.get("classification_axis") or "other"
        ),
        "representative_diseases": [label],
    }


def _rebuild_l2(
    tree: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Rebuild L2 while preserving IDs for leaves that stay under their parent."""
    output = copy.deepcopy(dict(tree))
    branches: MutableMapping[str, Any] = output["branches"]
    source = {
        str(branch_id): copy.deepcopy(dict(branch))
        for branch_id, branch in list(branches.items())
        if isinstance(branch, Mapping) and int(branch.get("level") or 0) == 2
    }
    for branch_id in source:
        branches.pop(branch_id, None)
    for parent in branches.values():
        if isinstance(parent, MutableMapping) and int(parent.get("level") or 0) == 1:
            parent["children"] = []
    reserved = set(str(value) for value in branches)
    movements = []
    for index, row in enumerate(rows):
        parent_id = str(row["parent_id"])
        parent = branches.get(parent_id)
        if not isinstance(parent, Mapping) or int(parent.get("level") or 0) != 1:
            raise ValueError(f"unknown target parent: {parent_id}")
        label = str(row["label"]).strip()
        if not label:
            raise ValueError("empty generated leaf label")
        source_id = str(row.get("source_id") or "")
        source_leaf = source.get(source_id)
        if (
            source_leaf is not None
            and str(source_leaf.get("parent") or "") == parent_id
            and source_id not in reserved
        ):
            branch_id = source_id
        else:
            identity = str(
                row.get("identity")
                or source_id
                or f"{canonical_label(label)}:{index}"
            )
            branch_id = stable_leaf_id(parent_id, label, identity, reserved)
        reserved.add(branch_id)
        branches[branch_id] = _new_leaf(
            branch_id, parent, label, source=source_leaf,
        )
        branches[parent_id]["children"].append(branch_id)
        movements.append({
            "source_id": source_id,
            "output_id": branch_id,
            "from_parent_id": (
                str(source_leaf.get("parent") or "") if source_leaf else ""
            ),
            "to_parent_id": parent_id,
        })
    validate_tree(output)
    return output, movements


def _stage_audit(
    stage: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    **details: Any,
) -> dict[str, Any]:
    before_ids = {str(row["id"]) for row in l2_leaves(before)}
    after_ids = {str(row["id"]) for row in l2_leaves(after)}
    return {
        "stage": stage,
        "input_tree_hash": stable_hash(before),
        "output_tree_hash": stable_hash(after),
        "active_ids": sorted(after_ids),
        "pruned_ids": sorted(before_ids - after_ids),
        **details,
    }


class EffectivePayloadCache:
    """Persistent cache keyed by effective payload hash and input tree hash."""

    def __init__(
        self,
        client: Any,
        *,
        path: Path | None = None,
        model: str = "",
        temperature: float = 0.0,
        transport: str = "",
    ) -> None:
        self.client = client
        self.path = path
        self.model = model or str(getattr(client, "model", "") or "")
        self.temperature = float(temperature)
        self.transport = transport or str(
            getattr(client, "backend_kind", "") or "RobustLLMClient"
        )
        self.cache: dict[str, Any] = (
            dict(_read_json(path).get("entries") or {})
            if path is not None and path.is_file()
            else {}
        )
        self.requested = 0
        self.model_calls = 0
        self.cache_hits = 0
        self.call_log: list[dict[str, Any]] = []

    def _save(self) -> None:
        if self.path is not None:
            _atomic_json(self.path, {
                "schema_version": SCHEMA_VERSION,
                "entries": self.cache,
            })

    def call(
        self,
        module: str,
        prompt: str,
        payload: Mapping[str, Any],
        *,
        tree_hash: str,
    ) -> dict[str, Any]:
        assert_no_gold_leak(payload)
        effective_payload_hash = stable_hash(payload)
        identity = {
            "module": module,
            "prompt_sha256": stable_hash(prompt),
            "effective_payload_sha256": effective_payload_hash,
            "tree_sha256": str(tree_hash),
            "model": self.model,
            "temperature": self.temperature,
            "transport": self.transport,
        }
        cache_key = stable_hash(identity)
        self.requested += 1
        hit = cache_key in self.cache
        if hit:
            self.cache_hits += 1
            result = self.cache[cache_key]
        else:
            result = self.client.call_module(module, prompt, payload)
            if not isinstance(result, Mapping):
                raise ValueError(f"{module}: client result must be an object")
            result = copy.deepcopy(dict(result))
            self.cache[cache_key] = result
            self.model_calls += 1
            self._save()
        self.call_log.append({
            **identity,
            "cache_key": cache_key,
            "cache_hit": hit,
        })
        return copy.deepcopy(dict(result))

    def audit(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "model": self.model_calls,
            "cache_hits": self.cache_hits,
        }


class DeterministicFakeClient:
    """Explicit offline test double; never represents a real model result."""

    backend_kind = "deterministic-test-double"

    def call_module(
        self, module: str, _prompt: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if module == "L2A1LocalParentGate":
            return {"decision": "accept", "reason": "deterministic passthrough"}
        if module == "L2A18ParentSafeGate":
            return {
                "decision": "valid",
                "confidence": "high",
                "task_adherence": True,
                "parent_axis_cited": True,
                "reason": "deterministic parent-safe passthrough",
            }
        if module == "L2A2SemanticDedupe":
            groups: dict[str, list[str]] = {}
            for row in payload.get("candidates") or ():
                groups.setdefault(canonical_label(row["label"]), []).append(
                    str(row["candidate_id"])
                )
            return {
                "clusters": [
                    {"cluster_id": key, "member_ids": ids}
                    for key, ids in sorted(groups.items())
                ]
            }
        if module in {"L2A3EvidenceRerank", "L2A19BudgetSafeRerank"}:
            return {
                "ranked_candidate_ids": [
                    str(row["candidate_id"])
                    for row in payload.get("candidates") or ()
                ]
            }
        if module == "L2A7GlobalAssignment":
            return {
                "assignments": [
                    {
                        "candidate_id": str(row["candidate_id"]),
                        "parent_id": str(row["current_parent_id"]),
                    }
                    for row in payload.get("candidates") or ()
                ]
            }
        if module in {"L2A6CStyleGenerator", "L2A8SiblingContrastGenerator"}:
            return {"leaves": self._candidate_leaves(payload)}
        if module == "L2A9A10PoolGenerator":
            return {
                "parents": [
                    {
                        "parent_id": str(row["parent"]["id"]),
                        "leaves": self._candidate_leaves(row),
                    }
                    for row in payload.get("parent_inputs") or ()
                ]
            }
        if module == "L2A10NBestSelector":
            indices = [
                int(row["sample_index"]) for row in payload.get("samples") or ()
            ]
            return {"sample_index": min(indices) if indices else 1}
        raise ValueError(f"deterministic client has no module: {module}")

    @staticmethod
    def _candidate_leaves(payload: Mapping[str, Any]) -> list[dict[str, str]]:
        output = []
        seen = set()
        for index, row in enumerate(payload.get("recall_candidates") or ()):
            label = str(row.get("disease") or row.get("label") or "").strip()
            key = canonical_label(label)
            if not label or key in seen:
                continue
            seen.add(key)
            output.append({
                "label": label,
                "candidate_id": str(
                    row.get("candidate_id") or f"recall-{index + 1}"
                ),
            })
            if len(output) == 4:
                break
        if not output:
            for row in payload.get("existing_candidates") or ():
                label = str(row.get("label") or "").strip()
                key = canonical_label(label)
                if label and key not in seen:
                    seen.add(key)
                    output.append({
                        "label": label,
                        "candidate_id": str(row.get("candidate_id") or ""),
                    })
                if len(output) == 4:
                    break
        return output


def _call_slice(cache: EffectivePayloadCache) -> int:
    return len(cache.call_log)


def _calls_since(
    cache: EffectivePayloadCache, start: int,
) -> list[dict[str, Any]]:
    return copy.deepcopy(cache.call_log[start:])


def apply_local_parent_gate(
    tree: Mapping[str, Any],
    cache: EffectivePayloadCache,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = copy.deepcopy(dict(tree))
    branches = _branches(before)
    accepted = []
    decisions = []
    start = _call_slice(cache)
    input_hash = stable_hash(before)
    evidence = case_evidence(before)
    for leaf in l2_leaves(before):
        parent = branches[str(leaf["parent"])]
        payload = {
            **evidence,
            "current_parent": _parent_row(parent),
            "candidate": _leaf_row(leaf),
        }
        result = cache.call(
            "L2A1LocalParentGate", LOCAL_GATE_PROMPT, payload,
            tree_hash=input_hash,
        )
        value = result.get("decision", result.get("accept"))
        keep = (
            value is True
            or str(value or "").strip().casefold() == "accept"
        )
        decisions.append({
            "candidate_id": str(leaf["id"]),
            "decision": "accept" if keep else "reject",
            "reason": str(result.get("reason") or ""),
        })
        if keep:
            accepted.append({
                "source_id": str(leaf["id"]),
                "parent_id": str(leaf["parent"]),
                "label": str(leaf["label"]),
            })
    output, movements = _rebuild_l2(before, accepted)
    return output, _stage_audit(
        "A1-local-parent-gate", before, output,
        decisions=decisions,
        parent_movements=movements,
        calls=_calls_since(cache, start),
    )


def _leaf_quality(
    leaf: Mapping[str, Any],
    parent: Mapping[str, Any],
) -> tuple[float, float, str]:
    evidence_count = len(leaf.get("evidence_for") or ())
    leaf_score = (
        float(leaf.get("posterior") or 0.0)
        + float(leaf.get("explanatory_coverage") or 0.0)
        + 0.01 * evidence_count
    )
    return (
        leaf_score,
        float(parent.get("posterior") or 0.0),
        str(leaf.get("id") or ""),
    )


def _semantic_clusters(
    tree: Mapping[str, Any],
    cache: EffectivePayloadCache | None,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
    leaves = l2_leaves(tree)
    fallback = {
        str(row["id"]): canonical_label(row.get("label"))
        for row in leaves
    }
    if cache is None:
        return fallback, {"schema": "normalization_only"}, []
    payload = {
        "case_context": str(tree.get("case_summary") or "")[:5000],
        "candidates": [_leaf_row(row) for row in leaves],
    }
    start = _call_slice(cache)
    result = cache.call(
        "L2A2SemanticDedupe", SEMANTIC_DEDUPE_PROMPT, payload,
        tree_hash=stable_hash(tree),
    )
    allowed = set(fallback)
    assigned: dict[str, str] = {}
    valid = isinstance(result.get("clusters"), list)
    if valid:
        for raw in result["clusters"]:
            if not isinstance(raw, Mapping):
                valid = False
                break
            cluster_id = str(raw.get("cluster_id") or "").strip()
            members = raw.get("member_ids")
            if (
                not cluster_id
                or not isinstance(members, list)
                or any(str(value) not in allowed for value in members)
                or any(str(value) in assigned for value in members)
            ):
                valid = False
                break
            for value in members:
                assigned[str(value)] = cluster_id
    if not valid:
        return fallback, {"schema": "failed_normalization_only"}, _calls_since(
            cache, start,
        )
    for branch_id, key in fallback.items():
        assigned.setdefault(branch_id, key)
    return assigned, {"schema": "valid"}, _calls_since(cache, start)


def apply_semantic_dedupe_cap(
    tree: Mapping[str, Any],
    cache: EffectivePayloadCache | None = None,
    *,
    cap: int = 5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if cap != 5:
        raise ValueError("A2 protocol freezes cap=5")
    before = copy.deepcopy(dict(tree))
    branches = _branches(before)
    clusters, schema, calls = _semantic_clusters(before, cache)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for leaf in l2_leaves(before):
        grouped.setdefault(clusters[str(leaf["id"])], []).append(leaf)
    winners = []
    duplicate_rejections = []
    for cluster_id, members in sorted(grouped.items()):
        members.sort(
            key=lambda row: (
                -_leaf_quality(row, branches[str(row["parent"])])[0],
                -_leaf_quality(row, branches[str(row["parent"])])[1],
                _leaf_quality(row, branches[str(row["parent"])])[2],
            )
        )
        winner = members[0]
        winners.append((cluster_id, winner))
        for row in members[1:]:
            duplicate_rejections.append({
                "candidate_id": str(row["id"]),
                "cluster_id": cluster_id,
                "winner_id": str(winner["id"]),
                "reason": "semantic_duplicate",
            })
    by_parent: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for item in winners:
        by_parent.setdefault(str(item[1]["parent"]), []).append(item)
    selected = []
    cap_rejections = []
    for parent_id, rows in sorted(by_parent.items()):
        rows.sort(
            key=lambda item: (
                -_leaf_quality(item[1], branches[parent_id])[0],
                str(item[1]["id"]),
            )
        )
        for cluster_id, leaf in rows[:cap]:
            selected.append({
                "source_id": str(leaf["id"]),
                "parent_id": parent_id,
                "label": str(leaf["label"]),
                "identity": cluster_id,
            })
        for cluster_id, leaf in rows[cap:]:
            cap_rejections.append({
                "candidate_id": str(leaf["id"]),
                "cluster_id": cluster_id,
                "reason": "parent_cap",
            })
    output, movements = _rebuild_l2(before, selected)
    validate_tree(output, parent_cap=cap)
    return output, _stage_audit(
        "A2-semantic-dedupe-cap5", before, output,
        semantic_schema=schema,
        semantic_clusters=clusters,
        rejections=duplicate_rejections + cap_rejections,
        parent_movements=movements,
        calls=calls,
        parent_cap=cap,
    )


def apply_evidence_rerank(
    tree: Mapping[str, Any],
    cache: EffectivePayloadCache,
    *,
    top_k: int = 4,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if top_k != 4:
        raise ValueError("A3 protocol freezes top_k=4")
    before = copy.deepcopy(dict(tree))
    branches = _branches(before)
    evidence = case_evidence(before)
    selected = []
    rankings = {}
    schema_rows = {}
    start = _call_slice(cache)
    input_hash = stable_hash(before)
    leaves_by_parent: dict[str, list[dict[str, Any]]] = {}
    for leaf in l2_leaves(before):
        leaves_by_parent.setdefault(str(leaf["parent"]), []).append(leaf)
    for parent in l1_parents(before):
        parent_id = str(parent["id"])
        leaves = leaves_by_parent.get(parent_id, [])
        if not leaves:
            rankings[parent_id] = []
            schema_rows[parent_id] = "not_applicable"
            continue
        allowed = {str(row["id"]): row for row in leaves}
        payload = {
            **evidence,
            "parent": _parent_row(parent),
            "candidates": [_leaf_row(row) for row in leaves],
            "top_k": top_k,
        }
        result = cache.call(
            "L2A3EvidenceRerank", EVIDENCE_RERANK_PROMPT, payload,
            tree_hash=input_hash,
        )
        ranked = result.get("ranked_candidate_ids")
        valid = (
            isinstance(ranked, list)
            and len(ranked) == len(set(str(value) for value in ranked))
            and all(str(value) in allowed for value in ranked)
        )
        if valid:
            order = [str(value) for value in ranked]
            order.extend(sorted(set(allowed) - set(order)))
            schema_rows[parent_id] = "valid"
        else:
            # Fail closed: preserve the source order instead of inventing a rank.
            order = [str(row["id"]) for row in leaves]
            schema_rows[parent_id] = "failed_source_order"
        rankings[parent_id] = order[:top_k]
        for branch_id in order[:top_k]:
            leaf = allowed[branch_id]
            selected.append({
                "source_id": branch_id,
                "parent_id": parent_id,
                "label": str(leaf["label"]),
            })
    output, movements = _rebuild_l2(before, selected)
    validate_tree(output, parent_cap=top_k)
    return output, _stage_audit(
        "A3-evidence-rerank-top4", before, output,
        rankings=rankings,
        schema=schema_rows,
        parent_movements=movements,
        calls=_calls_since(cache, start),
        top_k=top_k,
    )


def apply_a4_sequence(
    tree: Mapping[str, Any],
    cache: EffectivePayloadCache,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current, a1 = apply_local_parent_gate(tree, cache)
    current, a2 = apply_semantic_dedupe_cap(current, cache, cap=5)
    current, a3 = apply_evidence_rerank(current, cache, top_k=4)
    return current, [a1, a2, a3]


def apply_global_assignment(
    tree: Mapping[str, Any],
    cache: EffectivePayloadCache,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = copy.deepcopy(dict(tree))
    leaves = l2_leaves(before)
    parents = l1_parents(before)
    allowed_candidates = {str(row["id"]): row for row in leaves}
    allowed_parents = {str(row["id"]) for row in parents}
    payload = {
        **case_evidence(before),
        "parents": [_parent_row(row) for row in parents],
        "candidates": [_leaf_row(row) for row in leaves],
    }
    start = _call_slice(cache)
    result = cache.call(
        "L2A7GlobalAssignment", GLOBAL_ASSIGNMENT_PROMPT, payload,
        tree_hash=stable_hash(before),
    )
    raw = result.get("assignments")
    valid = isinstance(raw, list)
    assigned: dict[str, str] = {}
    if valid:
        for row in raw:
            if not isinstance(row, Mapping):
                valid = False
                break
            candidate_id = str(row.get("candidate_id") or "")
            parent_id = str(row.get("parent_id") or "")
            if (
                candidate_id not in allowed_candidates
                or candidate_id in assigned
                or (parent_id not in allowed_parents and parent_id != "REJECT")
            ):
                valid = False
                break
            assigned[candidate_id] = parent_id
    if not valid:
        assigned = {}
    selected = []
    decisions = []
    for candidate_id, leaf in sorted(allowed_candidates.items()):
        parent_id = assigned.get(candidate_id, "REJECT")
        decisions.append({
            "candidate_id": candidate_id,
            "from_parent_id": str(leaf["parent"]),
            "parent_id": parent_id,
        })
        if parent_id != "REJECT":
            selected.append({
                "source_id": candidate_id,
                "parent_id": parent_id,
                "label": str(leaf["label"]),
            })
    output, movements = _rebuild_l2(before, selected)
    return output, _stage_audit(
        "A7-global-parent-assignment", before, output,
        schema="valid" if valid else "failed_closed",
        assignments=decisions,
        parent_movements=movements,
        calls=_calls_since(cache, start),
    )


def _recall_by_parent(a_trace: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output = {}
    for raw in a_trace.get("recall_audit") or ():
        if not isinstance(raw, Mapping):
            continue
        parent_id = str(raw.get("parent_id") or "")
        if not parent_id:
            continue
        output[parent_id] = {
            "recall_candidates": [
                {
                    "candidate_id": f"{parent_id}:recall:{index:02d}",
                    "disease": str(row.get("disease") or ""),
                    "rrf_score": float(
                        row.get("rrf_score") or row.get("rrf") or 0.0
                    ),
                    "source_rank": copy.deepcopy(row.get("source_rank") or {}),
                }
                for index, row in enumerate(raw.get("candidates") or (), start=1)
                if isinstance(row, Mapping) and str(row.get("disease") or "").strip()
            ][:24],
            "knowledge_fragments": [
                {
                    "id": str(row.get("id") or ""),
                    "title": str(row.get("title") or ""),
                    "content": str(row.get("content") or "")[:1200],
                    "source": str(row.get("source") or ""),
                }
                for row in raw.get("knowledge_fragments") or ()
                if isinstance(row, Mapping)
            ][:12],
        }
    return output


def _parse_generated_leaves(
    result: Mapping[str, Any],
    *,
    cap: int = 5,
) -> tuple[list[dict[str, str]], str]:
    raw = result.get("leaves")
    if not isinstance(raw, list):
        return [], "failed_closed"
    output = []
    seen = set()
    for index, value in enumerate(raw):
        if isinstance(value, Mapping):
            label = str(value.get("label") or "").strip()
            source_id = str(value.get("candidate_id") or "")
        else:
            label = str(value).strip()
            source_id = ""
        key = canonical_label(label)
        if not label or not key:
            return [], "failed_closed"
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "label": label,
            "source_id": source_id,
            "identity": source_id or f"{key}:{index}",
        })
        if len(output) == cap:
            break
    return output, "valid"


def generate_from_a_recall(
    c_tree: Mapping[str, Any],
    a_trace: Mapping[str, Any],
    cache: EffectivePayloadCache,
    *,
    sibling_contrast: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A6/A8 regeneration interface starting from the frozen C L1 scaffold."""
    before = copy.deepcopy(dict(c_tree))
    recalls = _recall_by_parent(a_trace)
    a_leaves: dict[str, list[dict[str, Any]]] = {}
    for leaf in l2_leaves(a_trace["tree"]):
        a_leaves.setdefault(str(leaf["parent"]), []).append(_leaf_row(leaf))
    parents = l1_parents(before)
    evidence = case_evidence(before)
    selected = []
    schemas = {}
    start = _call_slice(cache)
    input_hash = stable_hash(before)
    for parent in parents:
        parent_id = str(parent["id"])
        source = recalls.get(parent_id, {})
        payload = {
            **evidence,
            "parent": _parent_row(parent),
            "recall_candidates": source.get("recall_candidates") or [],
            "knowledge_fragments": source.get("knowledge_fragments") or [],
            "existing_candidates": a_leaves.get(parent_id, []),
            "leaf_cap": 5,
        }
        if sibling_contrast:
            payload["sibling_parents"] = [
                _parent_row(row)
                for row in parents
                if str(row["id"]) != parent_id
            ]
        module = (
            "L2A8SiblingContrastGenerator"
            if sibling_contrast else "L2A6CStyleGenerator"
        )
        prompt = SIBLING_CONTRAST_PROMPT if sibling_contrast else A6_GENERATION_PROMPT
        result = cache.call(module, prompt, payload, tree_hash=input_hash)
        leaves, schema = _parse_generated_leaves(result)
        schemas[parent_id] = schema
        for row in leaves:
            selected.append({
                **row,
                "parent_id": parent_id,
            })
    output, movements = _rebuild_l2(before, selected)
    validate_tree(output, parent_cap=5)
    stage = (
        "A8-sibling-contrastive-generation"
        if sibling_contrast else "A6-a-recall-c-generate"
    )
    return output, _stage_audit(
        stage, before, output,
        schema=schemas,
        parent_movements=movements,
        calls=_calls_since(cache, start),
        interface="A-recall+C-generate",
        sibling_contrast=sibling_contrast,
    )


def _pool_parent_inputs(
    c_tree: Mapping[str, Any],
    a_trace: Mapping[str, Any],
) -> list[dict[str, Any]]:
    recalls = _recall_by_parent(a_trace)
    existing: dict[str, list[dict[str, Any]]] = {}
    for leaf in l2_leaves(a_trace["tree"]):
        existing.setdefault(str(leaf["parent"]), []).append(_leaf_row(leaf))
    parents = l1_parents(c_tree)
    return [
        {
            "parent": _parent_row(parent),
            "sibling_parents": [
                _parent_row(other)
                for other in parents
                if str(other["id"]) != str(parent["id"])
            ],
            "recall_candidates": (
                recalls.get(str(parent["id"]), {}).get("recall_candidates") or []
            ),
            "knowledge_fragments": (
                recalls.get(str(parent["id"]), {}).get("knowledge_fragments") or []
            ),
            "existing_candidates": existing.get(str(parent["id"]), []),
            "leaf_cap": 5,
        }
        for parent in parents
    ]


def generate_shared_pool(
    c_tree: Mapping[str, Any],
    a_trace: Mapping[str, Any],
    cache: EffectivePayloadCache,
    *,
    n: int = POOL_SIZE,
    temperature: float = POOL_TEMPERATURE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if n != POOL_SIZE or float(temperature) != POOL_TEMPERATURE:
        raise ValueError("A9/A10 protocol freezes N=5 and temperature=0.3")
    if float(cache.temperature) != POOL_TEMPERATURE:
        raise ValueError("shared pool cache/client must use temperature=0.3")
    before = copy.deepcopy(dict(c_tree))
    parent_inputs = _pool_parent_inputs(before, a_trace)
    allowed_parents = {str(row["id"]) for row in l1_parents(before)}
    samples = []
    sample_audits = []
    start = _call_slice(cache)
    input_hash = stable_hash(before)
    for sample_index in range(1, n + 1):
        payload = {
            **case_evidence(before),
            "parent_inputs": parent_inputs,
            "sample_index": sample_index,
            "sampling": {"n": n, "temperature": temperature},
        }
        result = cache.call(
            "L2A9A10PoolGenerator", POOL_GENERATION_PROMPT, payload,
            tree_hash=input_hash,
        )
        raw_parents = result.get("parents")
        valid = isinstance(raw_parents, list)
        selected = []
        seen_parents = set()
        parent_schema = {}
        if valid:
            for raw in raw_parents:
                if not isinstance(raw, Mapping):
                    valid = False
                    break
                parent_id = str(raw.get("parent_id") or "")
                if parent_id not in allowed_parents or parent_id in seen_parents:
                    valid = False
                    break
                seen_parents.add(parent_id)
                leaves, schema = _parse_generated_leaves(
                    {"leaves": raw.get("leaves")},
                )
                parent_schema[parent_id] = schema
                if schema != "valid":
                    valid = False
                    break
                for row in leaves:
                    selected.append({
                        **row,
                        "parent_id": parent_id,
                        "identity": (
                            row["source_id"]
                            or f"{canonical_label(row['label'])}:pool"
                        ),
                    })
        if not valid:
            selected = []
        tree, movements = _rebuild_l2(before, selected)
        validate_tree(tree, parent_cap=5)
        samples.append(tree)
        sample_audits.append({
            "sample_index": sample_index,
            "schema": "valid" if valid else "failed_closed",
            "parent_schema": parent_schema,
            "tree_hash": stable_hash(tree),
            "parent_movements": movements,
        })
    pool_identity = {
        "shared_pool_id": SHARED_POOL_ID,
        "n": n,
        "temperature": temperature,
        "input_tree_hash": input_hash,
        "sample_tree_hashes": [stable_hash(tree) for tree in samples],
    }
    return samples, {
        "pool_hash": stable_hash(pool_identity),
        **pool_identity,
        "samples": sample_audits,
        "calls": _calls_since(cache, start),
    }


def build_stability_consensus(
    c_tree: Mapping[str, Any],
    samples: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(samples) != POOL_SIZE:
        raise ValueError("A9 consensus requires exactly five samples")
    threshold = math.ceil(len(samples) / 2)
    observations: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
    for sample_index, tree in enumerate(samples, start=1):
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for leaf in l2_leaves(tree):
            by_parent.setdefault(str(leaf["parent"]), []).append(leaf)
        for parent_id, leaves in by_parent.items():
            seen = set()
            for rank, leaf in enumerate(leaves, start=1):
                key = canonical_label(leaf["label"])
                if key in seen:
                    continue
                seen.add(key)
                observations.setdefault((parent_id, key), []).append(
                    (sample_index, rank, str(leaf["label"]))
                )
    selected = []
    consensus_rows = []
    for (parent_id, key), rows in sorted(observations.items()):
        support = len(rows)
        if support < threshold:
            continue
        label = sorted(
            (row[2] for row in rows),
            key=lambda value: (len(value), canonical_label(value), value),
        )[0]
        mean_rank = sum(row[1] for row in rows) / support
        consensus_rows.append({
            "parent_id": parent_id,
            "canonical_label": key,
            "label": label,
            "support": support,
            "mean_rank": mean_rank,
        })
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in consensus_rows:
        by_parent.setdefault(str(row["parent_id"]), []).append(row)
    for parent_id, rows in sorted(by_parent.items()):
        rows.sort(key=lambda row: (
            -int(row["support"]),
            float(row["mean_rank"]),
            str(row["canonical_label"]),
        ))
        for row in rows[:5]:
            selected.append({
                "parent_id": parent_id,
                "label": str(row["label"]),
                "identity": f"consensus:{row['canonical_label']}",
            })
    output, movements = _rebuild_l2(c_tree, selected)
    validate_tree(output, parent_cap=5)
    return output, _stage_audit(
        "A9-stability-consensus", c_tree, output,
        threshold=threshold,
        consensus=consensus_rows,
        parent_movements=movements,
    )


def select_nbest_tree(
    c_tree: Mapping[str, Any],
    samples: Sequence[Mapping[str, Any]],
    cache: EffectivePayloadCache,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(samples) != POOL_SIZE:
        raise ValueError("A10 selection requires exactly five samples")
    payload = {
        **case_evidence(c_tree),
        "samples": [
            {
                "sample_index": index,
                "tree_hash": stable_hash(tree),
                "leaves": [
                    {
                        "id": str(row["id"]),
                        "label": str(row["label"]),
                        "parent_id": str(row["parent"]),
                    }
                    for row in l2_leaves(tree)
                ],
            }
            for index, tree in enumerate(samples, start=1)
        ],
    }
    start = _call_slice(cache)
    result = cache.call(
        "L2A10NBestSelector", NBEST_PROMPT, payload,
        tree_hash=stable_hash(c_tree),
    )
    try:
        selected_index = int(result.get("sample_index"))
    except (TypeError, ValueError):
        selected_index = 1
    schema = "valid"
    if selected_index not in range(1, len(samples) + 1):
        selected_index = 1
        schema = "failed_matched_first"
    output = copy.deepcopy(dict(samples[selected_index - 1]))
    return output, _stage_audit(
        "A10-n-best-tree-selection", c_tree, output,
        selected_sample_index=selected_index,
        schema=schema,
        calls=_calls_since(cache, start),
    )


def _source_trace_path(
    ab_output: Path, arm: str, replicate: int, case_id: str,
) -> Path:
    return (
        ab_output / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _trace_path(
    output: Path, arm: str, replicate: int, case_id: str,
) -> Path:
    return (
        output / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _arm_prompt_hash(arm: str) -> str:
    prompts = {
        "A1": [LOCAL_GATE_PROMPT],
        "A2": [SEMANTIC_DEDUPE_PROMPT],
        "A3": [EVIDENCE_RERANK_PROMPT],
        "A4": [
            LOCAL_GATE_PROMPT,
            SEMANTIC_DEDUPE_PROMPT,
            EVIDENCE_RERANK_PROMPT,
        ],
        "A6": [A6_GENERATION_PROMPT],
        "A7": [GLOBAL_ASSIGNMENT_PROMPT],
        "A8": [SIBLING_CONTRAST_PROMPT],
        "A9": [POOL_GENERATION_PROMPT],
        "A10": [POOL_GENERATION_PROMPT, NBEST_PROMPT],
    }
    return stable_hash(prompts.get(arm, []))


def _arm_slug(arm: str, arm_spec: Mapping[str, Any] | None = None) -> str:
    if isinstance(arm_spec, Mapping) and arm_spec.get("slug"):
        return str(arm_spec["slug"])
    if arm in ARM_SPECS:
        return str(ARM_SPECS[arm]["slug"])
    return {
        "C-prod": "c-prod",
        "A-raw": "a-raw",
    }.get(arm, arm.lower())


def _trace_identity(
    *,
    arm: str,
    arm_slug: str,
    protocol_hash: str,
    arm_spec_hash: str,
    c_trace: Mapping[str, Any],
    a_trace: Mapping[str, Any],
    backend: str,
    model: str,
) -> dict[str, Any]:
    temperature = POOL_TEMPERATURE if arm in {"A9", "A10"} else 0.0
    return {
        "protocol_version": PROTOCOL_VERSION,
        "protocol_hash": protocol_hash,
        "protocol_sha256": protocol_hash,
        "arm": arm,
        "arm_id": arm,
        "arm_slug": arm_slug,
        "case_id": str(a_trace["case_id"]),
        "replicate": int(a_trace["replicate"]),
        "seed_hash": str(a_trace.get("seed_hash") or ""),
        "source_c_tree_hash": str(c_trace["tree_hash"]),
        "source_a_tree_hash": str(a_trace["tree_hash"]),
        "source_candidate_asset_hash": stable_hash(
            a_trace.get("recall_audit") or []
        ),
        "arm_spec_hash": arm_spec_hash,
        "backend": backend,
        "model": model,
        "temperature": temperature,
        "transport": (
            "RobustLLMClient" if backend == "llm"
            else "deterministic-test-double"
        ),
        "prompt_sha256": _arm_prompt_hash(arm),
        "code_sha256": _sha256(Path(__file__)),
        "harness_sha256": _sha256(Path(__file__)),
    }


def make_trace(
    *,
    arm: str,
    c_trace: Mapping[str, Any],
    a_trace: Mapping[str, Any],
    tree: Mapping[str, Any],
    lineage: Sequence[Mapping[str, Any]],
    protocol_hash: str,
    arm_spec: Mapping[str, Any] | None = None,
    arm_spec_hash: str | None = None,
    backend: str,
    model: str,
    matched_first_sample: Mapping[str, Any] | None = None,
    shared_pool: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_spec = dict(
        arm_spec
        or ARM_SPECS.get(arm)
        or {"slug": _arm_slug(arm), "stage": "control"}
    )
    slug = _arm_slug(arm, resolved_spec)
    record = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "status": "OK",
        "arm": arm,
        "arm_id": arm,
        "arm_slug": slug,
        "case_id": str(a_trace["case_id"]),
        "replicate": int(a_trace["replicate"]),
        "identity": _trace_identity(
            arm=arm,
            arm_slug=slug,
            protocol_hash=protocol_hash,
            arm_spec_hash=arm_spec_hash or stable_hash(resolved_spec),
            c_trace=c_trace,
            a_trace=a_trace,
            backend=backend,
            model=model,
        ),
        "source_traces": {
            "C": {
                "tree_hash": str(c_trace["tree_hash"]),
                "seed_hash": str(c_trace.get("seed_hash") or ""),
            },
            "A": {
                "tree_hash": str(a_trace["tree_hash"]),
                "seed_hash": str(a_trace.get("seed_hash") or ""),
            },
        },
        "tree": copy.deepcopy(dict(tree)),
        "tree_hash": stable_hash(tree),
        "recall_audit": copy.deepcopy(list(a_trace.get("recall_audit") or ())),
        "transform_lineage": copy.deepcopy(list(lineage)),
        "matched_first_sample": copy.deepcopy(matched_first_sample),
        "shared_pool": copy.deepcopy(shared_pool),
        "result_provenance": {
            "backend": backend,
            "real_model_result": backend == "llm",
            "deterministic_test_double": backend != "llm",
            "promotion_eligible": False,
        },
    }
    validate_variant_trace(record)
    return record


def validate_variant_trace(trace: Mapping[str, Any]) -> None:
    tree = trace.get("tree")
    if not isinstance(tree, Mapping):
        raise ValueError("variant trace has no tree")
    if stable_hash(tree) != str(trace.get("tree_hash") or ""):
        raise ValueError("variant tree hash mismatch")
    validate_tree(tree)
    identity = trace.get("identity") or {}
    for key in ("arm", "case_id", "replicate"):
        if str(identity.get(key)) != str(trace.get(key)):
            raise ValueError(f"trace identity mismatch: {key}")
    if str(trace.get("arm_id") or identity.get("arm_id") or "") != str(trace.get("arm")):
        raise ValueError("trace arm_id mismatch")
    if not str(trace.get("arm_slug") or identity.get("arm_slug") or ""):
        raise ValueError("trace lacks arm_slug")
    if str(identity.get("arm_slug") or "") != str(trace.get("arm_slug") or ""):
        raise ValueError("trace identity arm_slug mismatch")
    lineage = trace.get("transform_lineage")
    if not isinstance(lineage, list) or not lineage:
        raise ValueError("trace has no transform lineage")
    if str(lineage[-1].get("output_tree_hash") or "") != str(trace["tree_hash"]):
        raise ValueError("lineage does not end at trace tree hash")
    for previous, current in zip(lineage, lineage[1:]):
        if previous.get("output_tree_hash") != current.get("input_tree_hash"):
            raise ValueError("transform lineage is discontinuous")
    matched = trace.get("matched_first_sample")
    pool = trace.get("shared_pool")
    if trace.get("arm") in {"A9", "A10"}:
        if not isinstance(matched, Mapping) or int(matched.get("sample_index") or 0) != 1:
            raise ValueError("A9/A10 trace lacks matched first sample")
        if not isinstance(pool, Mapping):
            raise ValueError("A9/A10 trace lacks shared pool identity")
        if str(pool.get("shared_pool_id") or "") != SHARED_POOL_ID:
            raise ValueError("A9/A10 shared_pool_id mismatch")
        hashes = list(pool.get("sample_tree_hashes") or ())
        if len(hashes) != POOL_SIZE or matched.get("tree_hash") != hashes[0]:
            raise ValueError("matched first sample is not pool sample one")


def _replay_stage(name: str, tree: Mapping[str, Any]) -> dict[str, Any]:
    return _stage_audit(name, tree, tree, source_replay=True)


def run_case_variants(
    *,
    c_trace: Mapping[str, Any],
    a_trace: Mapping[str, Any],
    protocol: Mapping[str, Any],
    base_cache: EffectivePayloadCache,
    pool_cache: EffectivePayloadCache,
    arms: Sequence[str] = GENERATION_ARMS,
    backend: str,
    model: str,
) -> dict[str, dict[str, Any]]:
    """Run requested controls/variants for one frozen case/replicate pair."""
    ab.validate_generation_trace(c_trace)
    ab.validate_generation_trace(a_trace)
    if c_trace["case_id"] != a_trace["case_id"]:
        raise ValueError("C/A case mismatch")
    if int(c_trace["replicate"]) != int(a_trace["replicate"]):
        raise ValueError("C/A replicate mismatch")
    protocol_hash = str(protocol["protocol_hash"])
    c_tree = copy.deepcopy(c_trace["tree"])
    a_tree = copy.deepcopy(a_trace["tree"])
    validate_tree(c_tree)
    validate_tree(a_tree)
    requested = tuple(dict.fromkeys(str(arm) for arm in arms))
    unknown = set(requested) - set(GENERATION_ARMS)
    if unknown:
        raise ValueError(f"unsupported generation arms: {sorted(unknown)}")
    built: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    if "C-prod" in requested:
        built["C-prod"] = (c_tree, [_replay_stage("C-prod-replay", c_tree)])
    if "A-raw" in requested:
        built["A-raw"] = (a_tree, [_replay_stage("A-raw-replay", a_tree)])
    if "A1" in requested:
        tree, audit = apply_local_parent_gate(a_tree, base_cache)
        built["A1"] = (tree, [audit])
    if "A2" in requested:
        tree, audit = apply_semantic_dedupe_cap(a_tree, base_cache, cap=5)
        built["A2"] = (tree, [audit])
    if "A3" in requested:
        tree, audit = apply_evidence_rerank(a_tree, base_cache, top_k=4)
        built["A3"] = (tree, [audit])
    if "A4" in requested:
        tree, lineage = apply_a4_sequence(a_tree, base_cache)
        built["A4"] = (tree, lineage)
    if "A6" in requested:
        tree, audit = generate_from_a_recall(
            c_tree, a_trace, base_cache, sibling_contrast=False,
        )
        built["A6"] = (tree, [audit])
    if "A7" in requested:
        tree, audit = apply_global_assignment(a_tree, base_cache)
        built["A7"] = (tree, [audit])
    if "A8" in requested:
        tree, audit = generate_from_a_recall(
            c_tree, a_trace, base_cache, sibling_contrast=True,
        )
        built["A8"] = (tree, [audit])
    pool = None
    pool_audit = None
    if {"A9", "A10"} & set(requested):
        pool, pool_audit = generate_shared_pool(
            c_tree, a_trace, pool_cache,
            n=POOL_SIZE, temperature=POOL_TEMPERATURE,
        )
    if "A9" in requested:
        assert pool is not None and pool_audit is not None
        tree, audit = build_stability_consensus(c_tree, pool)
        audit["shared_pool_hash"] = pool_audit["pool_hash"]
        built["A9"] = (tree, [audit])
    if "A10" in requested:
        assert pool is not None and pool_audit is not None
        tree, audit = select_nbest_tree(c_tree, pool, pool_cache)
        audit["shared_pool_hash"] = pool_audit["pool_hash"]
        built["A10"] = (tree, [audit])
    matched = (
        {
            "sample_index": 1,
            "tree_hash": stable_hash(pool[0]),
            "tree": copy.deepcopy(pool[0]),
        }
        if pool is not None else None
    )
    output = {}
    for arm in requested:
        tree, lineage = built[arm]
        arm_spec = (
            (protocol.get("arms") or {}).get(arm)
            or (protocol.get("controls") or {}).get(arm)
            or ARM_SPECS.get(arm)
            or {"slug": arm}
        )
        output[arm] = make_trace(
            arm=arm,
            c_trace=c_trace,
            a_trace=a_trace,
            tree=tree,
            lineage=lineage,
            protocol_hash=protocol_hash,
            arm_spec=arm_spec if isinstance(arm_spec, Mapping) else None,
            arm_spec_hash=stable_hash(arm_spec),
            backend=backend,
            model=model,
            matched_first_sample=(matched if arm in {"A9", "A10"} else None),
            shared_pool=(
                {
                    key: copy.deepcopy(value)
                    for key, value in pool_audit.items()
                    if key != "samples"
                }
                if arm in {"A9", "A10"} and pool_audit is not None
                else None
            ),
        )
    if "A9" in output and "A10" in output:
        if (
            output["A9"]["shared_pool"]["pool_hash"]
            != output["A10"]["shared_pool"]["pool_hash"]
        ):
            raise RuntimeError("A9/A10 did not share one pool")
    return output


def _source_cases(
    ab_output: Path,
    *,
    case_filter: str = "",
    limit: int = 0,
) -> tuple[dict[str, Any], list[str]]:
    manifest = _read_json(ab_output / "generation" / "manifest.json")
    cases = sorted({
        str(key).rsplit("/", 1)[-1]
        for key in manifest.get("tree_hashes") or {}
    })
    if case_filter:
        requested = {
            value.strip() for value in case_filter.split(",") if value.strip()
        }
        missing = requested - set(cases)
        if missing:
            raise ValueError(f"unknown case filter: {sorted(missing)}")
        cases = [case_id for case_id in cases if case_id in requested]
    if limit:
        cases = cases[:limit]
    return manifest, cases


def _new_llm_client(model: str, temperature: float, timeout: float) -> Any:
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    return RobustLLMClient(
        model=model,
        temperature=temperature,
        call_timeout=timeout,
        max_retries=5,
        timeout_retry_cap=2,
    )


def _clients(args: argparse.Namespace) -> tuple[Any, Any, str]:
    if args.backend == "deterministic":
        fake = DeterministicFakeClient()
        return fake, fake, fake.backend_kind
    return (
        _new_llm_client(args.model, 0.0, args.call_timeout),
        _new_llm_client(args.model, POOL_TEMPERATURE, args.call_timeout),
        "llm",
    )


def _generate_pair(
    args: argparse.Namespace,
    protocol: Mapping[str, Any],
    arms: Sequence[str],
    replicate: int,
    case_id: str,
) -> list[dict[str, Any]]:
    base_client, pool_client, backend_kind = _clients(args)
    c_trace = _read_json(_source_trace_path(
        args.ab_output_dir, "C", replicate, case_id,
    ))
    a_trace = _read_json(_source_trace_path(
        args.ab_output_dir, "A", replicate, case_id,
    ))
    cache_root = (
        args.output_dir / "cache" / "generation"
        / f"r{replicate:02d}" / case_id
    )
    transport = (
        "RobustLLMClient" if backend_kind == "llm"
        else "deterministic-test-double"
    )
    base_cache = EffectivePayloadCache(
        base_client,
        path=cache_root / "base.json",
        model=args.model if backend_kind == "llm" else backend_kind,
        temperature=0.0,
        transport=transport,
    )
    pool_cache = EffectivePayloadCache(
        pool_client,
        path=cache_root / "pool.json",
        model=args.model if backend_kind == "llm" else backend_kind,
        temperature=POOL_TEMPERATURE,
        transport=transport,
    )
    generated = run_case_variants(
        c_trace=c_trace,
        a_trace=a_trace,
        protocol=protocol,
        base_cache=base_cache,
        pool_cache=pool_cache,
        arms=arms,
        backend=backend_kind,
        model=args.model if backend_kind == "llm" else backend_kind,
    )
    records = []
    for arm, record in generated.items():
        path = _trace_path(args.output_dir, arm, replicate, case_id)
        if path.is_file():
            existing = _read_json(path)
            if args.resume and existing.get("identity") == record["identity"]:
                validate_variant_trace(existing)
                records.append(existing)
                continue
            provenance = existing.get("result_provenance") or {}
            if provenance.get("real_model_result"):
                raise FileExistsError(
                    f"refusing to overwrite real model trace: {path}"
                )
        _atomic_json(path, record)
        records.append(record)
    return records


def generate(args: argparse.Namespace) -> dict[str, Any]:
    protocol = load_protocol(args.protocol)
    source_manifest, cases = _source_cases(
        args.ab_output_dir,
        case_filter=args.case_filter,
        limit=args.limit,
    )
    if int(source_manifest.get("replicates") or 0) < args.replicates:
        raise ValueError("source manifest has fewer replicates than requested")
    arms = tuple(
        value.strip() for value in args.arms.split(",") if value.strip()
    )
    unknown = set(arms) - set(GENERATION_ARMS)
    if unknown:
        raise ValueError(f"unknown generation arms: {sorted(unknown)}")
    backend_kind = (
        "llm" if args.backend == "llm" else "deterministic-test-double"
    )
    records: list[dict[str, Any]] = []
    work = [
        (replicate, case_id)
        for replicate in range(1, args.replicates + 1)
        for case_id in cases
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _generate_pair,
                args,
                protocol,
                arms,
                replicate,
                case_id,
            ): (replicate, case_id)
            for replicate, case_id in work
        }
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(
        key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"])
        )
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "generate",
        "study_design": "development_replay",
        "protocol_hash": protocol["protocol_hash"],
        "protocol_sha256": protocol["protocol_sha256"],
        "protocol_source": protocol["protocol_source"],
        "source_generation_manifest_hash": source_manifest.get("manifest_hash"),
        "code_sha256": _sha256(Path(__file__)),
        "prompt_sha256": {
            arm: _arm_prompt_hash(arm) for arm in arms
        },
        "arms": list(arms),
        "case_ids": cases,
        "replicates": args.replicates,
        "record_count": len(records),
        "backend": backend_kind,
        "model": args.model if backend_kind == "llm" else None,
        "temperature": {
            "default": 0.0,
            "shared_a9_a10_pool": POOL_TEMPERATURE,
        },
        "transport": (
            "RobustLLMClient" if backend_kind == "llm"
            else "deterministic-test-double"
        ),
        "real_model_results": backend_kind == "llm",
        "deterministic_test_double": backend_kind != "llm",
        "promotion_eligible": False,
        "tree_hashes": {
            f"{row['arm']}/r{int(row['replicate']):02d}/{row['case_id']}":
                row["tree_hash"]
            for row in records
        },
        "cache_policy": (
            "effective payload hash + input tree hash + prompt/model/temperature/"
            "transport; arm name is excluded"
        ),
        "shared_pool_policy": (
            f"A9/A10 share {SHARED_POOL_ID} N=5 temperature=0.3 per case/replicate"
        ),
        "overwrite_policy": "real_model_result traces are never overwritten",
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    _atomic_json(args.output_dir / "generation" / "manifest.json", manifest)
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("validate-protocol", "generate"))
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--ab-output-dir", type=Path, default=DEFAULT_AB_OUTPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--arms", default=",".join(GENERATION_ARMS),
        help="comma-separated generation arms; A5 is downstream-only",
    )
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--backend", choices=("deterministic", "llm"), default="deterministic",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.replicates < 1:
        parser.error("--replicates must be >= 1")
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.stage == "validate-protocol":
        protocol = load_protocol(args.protocol)
        result = {
            "status": "OK",
            "protocol_hash": protocol["protocol_hash"],
            "protocol_source": protocol["protocol_source"],
            "registered_arms": sorted(protocol["arms"]),
        }
    else:
        result = generate(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
