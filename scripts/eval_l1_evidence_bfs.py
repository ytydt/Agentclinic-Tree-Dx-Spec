#!/usr/bin/env python3
"""Dual-track evaluation for TALP L1 Evidence-BFS.

Track A uses the hand-curated L1 projection and a uniform prior to isolate
selection/allocation capability. Track B runs the same contracts on the frozen
recall_hints_gap shared L1 trees. No controller loop, L2 expansion, action
execution, termination, or answer mapping is invoked here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import random
import statistics
import sys
import time
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    L1EvidenceBFSPipeline,
    L1ObservedFact,
    PRESETS,
    assert_no_gold_leak,
    clean_contrastive_selection,
    clean_selected_fact_ids,
    stable_hash,
)
from agentclinic_tree_dx.adaptive_stopping import (  # noqa: E402
    EvidenceQuorumF4Policy,
)
from agentclinic_tree_dx.state import Branch, DiagnosticState  # noqa: E402

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_PROFILES = ("p5_headline", "g2ur")
DEFAULT_ARMS = (
    "B0", "B1", "B1a", "B1s", "B2", "B3", "B3x", "B4", "B5", "B6", "A",
)
DEFAULT_SHARED_TREE_DIR = (
    ROOT / "logs" / "branch_talp_composed" / "talp17_shared_tree_p5_g2ur"
    / "shared_trees"
)
DEFAULT_LEGACY_TRACE_DIR = (
    ROOT / "logs" / "branch_talp_composed" / "talp17_shared_tree_p5_g2ur"
    / "traces"
)
DEFAULT_ARM_OUTPUTS = {
    "p5_headline": ROOT / "logs" / "talp_discrim_p5kg_g0_s7r0_dv2_p5.json",
    "g2ur": ROOT / "logs" / "talp_discrim_p5kg_research_g2ur_s7r0_dv2_p5.json",
}
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
COMPOSED_SCRIPT = ROOT / "scripts" / "eval_branch_talp_composed.py"
PARTIAL_SCRIPT = ROOT / "scripts" / "eval_partial_flow_talp17.py"
TALP_SCRIPT = ROOT / "scripts" / "eval_talp_discrimination.py"


@dataclass(frozen=True)
class ArmSpec:
    arm: str
    preset: str
    max_rounds: int = 4
    facts_per_cycle: int = 2
    disable_ruleout: bool = False
    deduplicate: bool = True
    branch_proposal: bool = False
    legacy: bool = False
    stop_policy: str = ""


ARM_SPECS = {
    "B0": ArmSpec("B0", "e1q_legacy", legacy=True),
    "B1": ArmSpec("B1", "p5_single_direct"),
    "B1a": ArmSpec("B1a", "p5_anti_anchor_direct"),
    "B1s": ArmSpec("B1s", "p5_single_abstaining"),
    "B2": ArmSpec("B2", "bfs_sparse"),
    "B3": ArmSpec("B3", "bfs_sparse_dual_ro"),
    "B3x": ArmSpec(
        "B3x", "bfs_sparse_dual_ro", max_rounds=6, facts_per_cycle=3
    ),
    "B4": ArmSpec("B4", "bfs_sparse", disable_ruleout=True),
    "B5": ArmSpec("B5", "bfs_sparse", max_rounds=2),
    "B6": ArmSpec("B6", "bfs_sparse", deduplicate=False),
    "S5": ArmSpec(
        "S5", "p5_single_direct", stop_policy="evidence_quorum_f4",
    ),
    "A": ArmSpec(
        "A", "bfs_sparse_branch_proposal", branch_proposal=True
    ),
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _norm(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


class CachedLLM:
    def __init__(self, llm, cache_path: Path, model: str) -> None:
        self.llm = llm
        self.cache_path = cache_path
        self.model = model
        configured_temperature = getattr(llm, "temperature", None)
        self.temperature = (
            1.0
            if configured_temperature is None
            else float(configured_temperature)
        )
        try:
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}

    def call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict:
        key = stable_hash({
            "model": self.model,
            "temperature": self.temperature,
            "module": module,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "payload": payload,
        })
        if key not in self.cache:
            self.cache[key] = self.llm.call_module(module, prompt, dict(payload))
            _atomic_json(self.cache_path, self.cache)
        value = self.cache[key]
        if not isinstance(value, Mapping):
            raise ValueError(f"{module} returned non-object JSON")
        return dict(value)


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _runtime_functions(
    cached: CachedLLM,
    preset: str,
    talp,
    *,
    branch_proposal: bool = False,
    disable_ruleout: bool = False,
):
    config = PRESETS[preset]
    forced_select_prompt = _prompt("observed_evidence_selector.txt")
    abstain_select_prompt = _prompt("l1_evidence_selector.txt")
    contrastive_select_prompt = _prompt("l1_contrastive_evidence_selector.txt")
    anti_anchor_select_prompt = _prompt("l1_anti_anchor_evidence_selector.txt")
    branch_prompt = _prompt("l1_branch_evidence_proposer.txt")
    ro_select_prompt = _prompt("l1_ruleout_evidence_selector.txt")
    sparse_in_prompt = _prompt("l1_sparse_rule_in_allocator.txt")
    sparse_out_prompt = _prompt("l1_sparse_rule_out_allocator.txt")

    def _selection_view(payload: Mapping[str, Any]) -> dict[str, Any]:
        eligible = set(payload["eligible_fact_ids"])
        facts = [
            row for row in payload["fact_catalog_core"] if row["id"] in eligible
        ]
        return {
            "vignette": payload["case_context"],
            "case_context": payload["case_context"],
            "candidates": payload["candidates"],
            "available_findings": facts,
            "fact_catalog_core": payload["fact_catalog_core"],
            "selection_status_by_id": payload["selection_status_by_id"],
            "eligible_fact_ids": payload["eligible_fact_ids"],
            "max_selected_facts": payload.get("max_selected_facts", 2),
            "accounted_evidence_history": payload["accounted_evidence_history"],
            "discriminator_rules": payload.get("discriminator_rules") or [],
            "evidence_provenance": payload.get("evidence_provenance") or [],
        }

    def _validated_matrix_selector(
        *,
        module: str,
        prompt: str,
        view: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = cached.call(module, prompt, view)
        cleaned = clean_contrastive_selection(
            response,
            view["eligible_fact_ids"],
            [row["id"] for row in view["candidates"]],
            limit=int(view["max_selected_facts"]),
        )
        if cleaned["schema_valid"]:
            cleaned["repair_used"] = False
            return cleaned
        repair_view = {
            **view,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Preserve the clinical ranking if defensible, but return a "
                "complete candidate_effects matrix for every current candidate "
                "and satisfy the final JSON schema exactly."
            ),
        }
        assert_no_gold_leak(repair_view)
        repaired = clean_contrastive_selection(
            cached.call(f"{module}Repair", prompt, repair_view),
            view["eligible_fact_ids"],
            [row["id"] for row in view["candidates"]],
            limit=int(view["max_selected_facts"]),
        )
        repaired["repair_used"] = True
        return repaired

    def global_selector(payload):
        view = _selection_view(payload)
        if branch_proposal:
            return cached.call("L1BranchEvidenceProposer", branch_prompt, view)
        if config.selector_contract == "contrastive":
            return _validated_matrix_selector(
                module="L1ContrastiveEvidenceSelector",
                prompt=contrastive_select_prompt,
                view=view,
            )
        if config.selector_contract == "anti_anchor":
            return _validated_matrix_selector(
                module="L1AntiAnchorEvidenceSelector",
                prompt=anti_anchor_select_prompt,
                view=view,
            )
        if config.selector_contract == "p5_forced":
            response = cached.call(
                "ObservedEvidenceSelector", forced_select_prompt, view
            )
            eligible = set(view["eligible_fact_ids"])
            returned = [
                response.get("best_fact_id"),
                *(response.get("ranked_fact_ids") or []),
            ]
            if not any(str(value or "") in eligible for value in returned):
                repair_view = {
                    **view,
                    "schema_repair": (
                        "The previous response returned no currently eligible ID. "
                        "Return one or two exact IDs from eligible_fact_ids."
                    ),
                }
                response = cached.call(
                    "ObservedEvidenceSelectorRepair",
                    forced_select_prompt,
                    repair_view,
                )
                repaired = [
                    response.get("best_fact_id"),
                    *(response.get("ranked_fact_ids") or []),
                ]
                if not any(str(value or "") in eligible for value in repaired):
                    fallback_ids = list(view["eligible_fact_ids"])[:2]
                    response = {
                        "verdict": "select",
                        "best_fact_id": fallback_ids[0],
                        "ranked_fact_ids": fallback_ids,
                        "fallback": "deterministic_eligible_after_invalid_repair",
                    }
            return response
        return cached.call("L1EvidenceSelector", abstain_select_prompt, view)

    def ro_selector(payload):
        return cached.call(
            "L1RuleOutEvidenceSelector", ro_select_prompt, _selection_view(payload)
        )

    def _p5_payload(payload: Mapping[str, Any], *, axis: str) -> dict[str, Any]:
        candidates = [row["label"] for row in payload["candidates"]]
        output = {
            "vignette": payload["case_context"],
            "candidates": candidates,
            "finding": payload["selected_fact"]["text"],
        }
        if axis == "rule_in" and payload.get("discriminator_rules"):
            output["discriminator_rules"] = payload["discriminator_rules"]
        if axis == "rule_out" and payload.get("ruleout_rules"):
            output["ruleout_rules"] = payload["ruleout_rules"]
        return output

    def rule_in(payload):
        if config.allocation_contract == "p5_single":
            return cached.call(
                "DiscriminatorDirection",
                talp._DIRECTION_PROMPT,
                _p5_payload(payload, axis="rule_in"),
            )
        return cached.call("L1SparseRuleInAllocator", sparse_in_prompt, payload)

    def rule_out(payload):
        if disable_ruleout:
            if config.allocation_contract == "p5_single":
                return {"argues_against": "none", "why": "ablation"}
            return {"verdict": "none", "ranked_candidates": [], "why": "ablation"}
        if config.allocation_contract == "p5_single":
            return cached.call(
                "DiscriminatorRuleOut",
                talp._RULEOUT_PROMPT,
                _p5_payload(payload, axis="rule_out"),
            )
        return cached.call("L1SparseRuleOutAllocator", sparse_out_prompt, payload)

    return global_selector, rule_in, rule_out, ro_selector


def _value_from(item: Any) -> str:
    if isinstance(item, Mapping):
        return str(item.get("content") or item.get("text") or item.get("finding") or "")
    return str(getattr(item, "content", None) or item)


def _typed_parts(reference: Mapping[str, Any] | None) -> dict[str, str]:
    typed = dict((reference or {}).get("typed_finding") or {})
    concepts = typed.get("concepts") or []
    concept = "|".join(
        str(item.get("id") or item.get("label") or item)
        if isinstance(item, Mapping) else str(item)
        for item in concepts
    )
    temporal = typed.get("temporal") or {}
    if isinstance(temporal, Mapping):
        temporal = json.dumps(temporal, ensure_ascii=False, sort_keys=True)
    return {
        "concept": concept,
        "value_state": str(
            typed.get("value_state") or (reference or {}).get("value_state") or ""
        ),
        "polarity": str(
            typed.get("polarity") or (reference or {}).get("polarity") or ""
        ),
        "specimen": str(typed.get("specimen") or ""),
        "temporal_context": str(temporal or ""),
    }


def _facts_for_case(
    state: DiagnosticState,
    annotation: Mapping[str, Any],
    composed,
    *,
    deduplicate: bool,
) -> tuple[L1ObservedFact, ...]:
    findings = list(annotation.get("findings") or ())
    texts = [_value_from(item).strip() for item in state.static_evidence_items]
    texts.extend(
        str(row.get("finding") or "").strip()
        for row in findings if row.get("in_vignette")
    )
    output: list[L1ObservedFact] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        reference = composed._best_reference(text, findings)
        typed = _typed_parts(reference)
        provisional = L1ObservedFact("", text, **typed)
        if deduplicate and provisional.canonical_key in seen:
            continue
        seen.add(provisional.canonical_key)
        output.append(L1ObservedFact(f"F{len(output) + 1}", text, **typed))
        if len(output) >= 40:
            break
    return tuple(output)


def _manual_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    annotation = case["annotation"]
    candidates = list(annotation.get("candidates") or ())
    candidate_to_l1 = {
        _norm(candidate["name"]): str(candidate.get("l1_parent") or candidate["name"])
        for candidate in candidates
    }
    l1_labels: list[str] = []
    for candidate in candidates:
        label = str(candidate.get("l1_parent") or candidate["name"])
        if label not in l1_labels:
            l1_labels.append(label)
    gold_candidate = next(
        (candidate for candidate in candidates if candidate.get("is_gold")), None
    )
    annotated_l1_label = str(annotation.get("l1_label") or "")
    gold_l1 = str(
        (gold_candidate or {}).get("l1_parent")
        or annotated_l1_label
        or case["gold"]
    )
    if gold_l1 not in l1_labels:
        l1_labels.insert(0, gold_l1)
    label_to_id = {label: f"L{index + 1}" for index, label in enumerate(l1_labels)}
    findings = []
    for row in annotation.get("findings") or ():
        if not row.get("in_vignette"):
            continue
        role = str(row.get("role") or "")
        target_name = str(row.get("direction_target") or row.get("target") or "")
        target_l1 = candidate_to_l1.get(_norm(target_name), "")
        l1_role = role
        if role == "rule_out_distractor" and target_l1 == gold_l1:
            l1_role = "shared_nondiscriminating"
        findings.append({
            "finding": str(row.get("finding") or ""),
            "role": l1_role,
            "original_role": role,
            "decisive": bool(row.get("decisive")),
            "gold_l1": gold_l1,
            "target_l1": target_l1,
            "target_name": target_name,
        })
    return {
        "labels": l1_labels,
        "label_to_id": label_to_id,
        "gold_l1": gold_l1,
        "annotated_l1_label": annotated_l1_label,
        "label_agreement": (
            not annotated_l1_label or _norm(annotated_l1_label) == _norm(gold_l1)
        ),
        "gold_branch_id": label_to_id[gold_l1],
        "findings": findings,
    }


def _manual_state(case_id: str, projection: Mapping[str, Any]) -> DiagnosticState:
    labels = list(projection["labels"])
    state = DiagnosticState(case_id=case_id)
    state.branches = {
        f"L{index + 1}": Branch(
            id=f"L{index + 1}",
            label=label,
            parent="ROOT",
            level=1,
            status="live",
            prior=1 / len(labels),
            posterior=1 / len(labels),
            danger=0.0,
            actionability=0.0,
            explanatory_coverage=0.0,
        )
        for index, label in enumerate(labels)
    }
    state.frontier = list(state.branches)
    return state


def _reference_for_fact(
    text: str, projection: Mapping[str, Any], composed,
) -> Mapping[str, Any] | None:
    return composed._best_reference(text, list(projection["findings"]))


def _rank(rows: Sequence[Branch], index: int) -> int | None:
    if index < 0 or index >= len(rows):
        return None
    ordered = sorted(
        range(len(rows)), key=lambda i: (-rows[i].posterior, rows[i].id)
    )
    return ordered.index(index) + 1


def _manual_gold(state: DiagnosticState, projection: Mapping[str, Any]) -> dict[str, Any]:
    branch_id = projection["gold_branch_id"]
    rows = sorted(state.branches.values(), key=lambda branch: branch.id)
    index = next((i for i, branch in enumerate(rows) if branch.id == branch_id), -1)
    rank = _rank(rows, index)
    branch = rows[index] if rank is not None else None
    return {
        "exists": branch is not None,
        "branch_id": branch.id if branch else None,
        "label": branch.label if branch else None,
        "posterior": branch.posterior if branch else None,
        "rank": rank,
        "top1": rank == 1,
        "count": len(rows),
    }


def _dynamic_gold(
    state: DiagnosticState,
    case: Mapping[str, Any],
    judge: Callable[[str, list[str]], int],
    cache: dict[str, int],
    cache_path: Path,
) -> dict[str, Any]:
    rows = sorted(
        (branch for branch in state.branches.values() if branch.level == 1),
        key=lambda branch: branch.id,
    )
    labels = [branch.label for branch in rows]
    key = f"l1::{case['id']}::{stable_hash(labels)[:16]}"
    if key not in cache:
        cache[key] = int(judge(case["gold"], labels))
        _atomic_json(cache_path, cache)
    index = cache[key]
    rank = _rank(rows, index)
    branch = rows[index] if rank is not None else None
    return {
        "exists": branch is not None,
        "branch_id": branch.id if branch else None,
        "label": branch.label if branch else None,
        "posterior": branch.posterior if branch else None,
        "rank": rank,
        "top1": rank == 1,
        "count": len(rows),
    }


def _gold_trajectory(trace: Mapping[str, Any], branch_id: str | None):
    output = []
    for snapshot in trace.get("posterior_trajectory") or ():
        rows = list(snapshot.get("posteriors") or ())
        index = next(
            (i for i, row in enumerate(rows) if row.get("id") == branch_id), None
        )
        output.append({
            "round": snapshot.get("round"),
            "fact_id": snapshot.get("fact_id"),
            "exists": index is not None,
            "rank": index + 1 if index is not None else None,
            "top1": index == 0,
            "posterior": rows[index]["posterior"] if index is not None else None,
        })
    return output


def _track_a_metrics(
    trace: Mapping[str, Any],
    facts: Sequence[L1ObservedFact],
    projection: Mapping[str, Any],
    composed,
    *,
    gold_branch_id: str | None,
    target_resolver: Callable[[Mapping[str, Any]], str | None],
    depleted_false_select: bool | None,
) -> dict[str, Any]:
    fact_by_id = {fact.id: fact for fact in facts}
    selected = list(trace.get("selected_fact_ids") or ())
    rows = []
    for round_row in trace.get("rounds") or ():
        fact_id = round_row["fact_id"]
        reference = _reference_for_fact(
            fact_by_id[fact_id].text, projection, composed
        )
        role = str((reference or {}).get("role") or "")
        rule_in = list(round_row.get("rule_in_ranked") or ())
        rule_out = list(round_row.get("rule_out_ranked") or ())
        gold_id = gold_branch_id
        target_id = target_resolver(reference or {})
        if role == "rule_in_gold" and gold_id:
            target_rank = rule_in.index(gold_id) + 1 if gold_id in rule_in else None
            ok = target_rank is not None
            kind = "rulein"
        elif role == "rule_out_distractor" and target_id:
            target_rank = rule_out.index(target_id) + 1 if target_id in rule_out else None
            ok = target_rank is not None
            kind = "ruleout"
        elif role in {"shared_nondiscriminating", "parent_child_trap"}:
            target_rank = None
            ok = not rule_in and not rule_out
            kind = "shared"
        else:
            target_rank = None
            ok = None
            kind = "unscored"
        rows.append({
            "fact_id": fact_id,
            "finding": (reference or {}).get("finding"),
            "role": role or None,
            "kind": kind,
            "decisive": bool((reference or {}).get("decisive")),
            "target_rank": target_rank,
            "ok": ok,
            "rule_in_verdict": round_row.get("rule_in_verdict"),
            "rule_out_verdict": round_row.get("rule_out_verdict"),
        })
    references = [
        _reference_for_fact(fact_by_id[fact_id].text, projection, composed)
        for fact_id in selected
    ]
    ro_flags = [
        bool(reference and reference.get("role") == "rule_out_distractor")
        for reference in references
    ]
    valid_flags = [
        bool(reference and reference.get("role") in {
            "rule_in_gold", "rule_out_distractor",
        })
        for reference in references
    ]
    eligible_discriminators = any(
        row["role"] in {"rule_in_gold", "rule_out_distractor"}
        for row in projection["findings"]
    )
    first_queue = (
        (trace.get("selection_cycles") or [{}])[0].get("queue") or []
    )
    first_cycle = (trace.get("selection_cycles") or [{}])[0]
    global_refs = [
        _reference_for_fact(fact_by_id[fact_id].text, projection, composed)
        for fact_id in first_cycle.get("global_ids") or ()
        if fact_id in fact_by_id
    ]
    dedicated_refs = [
        _reference_for_fact(fact_by_id[fact_id].text, projection, composed)
        for fact_id in first_cycle.get("ruleout_ids") or ()
        if fact_id in fact_by_id
    ]
    global_ro = [
        bool(reference and reference.get("role") == "rule_out_distractor")
        for reference in global_refs
    ]
    dedicated_ro = [
        bool(reference and reference.get("role") == "rule_out_distractor")
        for reference in dedicated_refs
    ]
    displaced_refs = [
        _reference_for_fact(fact_by_id[fact_id].text, projection, composed)
        for fact_id in first_cycle.get("displaced_global_ids") or ()
        if fact_id in fact_by_id
    ]
    has_cross_l1_ruleout = any(
        row["role"] == "rule_out_distractor" for row in projection["findings"]
    )
    return {
        "select@1": bool(rows and rows[0]["decisive"]),
        "select@2": any(row["decisive"] for row in rows[:2]),
        "select_valid": any(valid_flags),
        "ro_select@1": bool(ro_flags and ro_flags[0]),
        "ro_select@2": any(ro_flags[:2]),
        "global_ro_select@1": bool(global_ro and global_ro[0]),
        "global_ro_select@2": any(global_ro[:2]),
        "dedicated_ro_select@1": bool(dedicated_ro and dedicated_ro[0]),
        "dedicated_ro_select@2": any(dedicated_ro[:2]),
        "dedicated_ro_select_valid": any(dedicated_ro),
        "has_cross_l1_ruleout": has_cross_l1_ruleout,
        "dedicated_ro_correct_abstain": bool(
            not has_cross_l1_ruleout and not first_cycle.get("ruleout_ids")
        ),
        "displacement_count": len(
            first_cycle.get("displaced_global_ids") or ()
        ),
        "displaced_valid_fact": any(
            reference and reference.get("role") in {
                "rule_in_gold", "rule_out_distractor",
            }
            for reference in displaced_refs
        ),
        "selector_false_abstain": bool(eligible_discriminators and not first_queue),
        "depleted_false_select": depleted_false_select,
        "candidate_order_rotation_stability": None,
        "direction_rows": rows,
    }


def _depleted_false_select(
    *,
    global_selector: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    preset: str,
    state: DiagnosticState,
    case_context: str,
    facts: Sequence[L1ObservedFact],
    blocks: Mapping[str, Mapping[str, Any]],
    projection: Mapping[str, Any],
    composed,
) -> bool | None:
    shared = []
    for fact in facts:
        reference = _reference_for_fact(fact.text, projection, composed)
        if reference and reference.get("role") in {
            "shared_nondiscriminating", "parent_child_trap",
        }:
            shared.append(fact)
    if not shared:
        return None
    shared_ids = [fact.id for fact in shared]
    rules = [
        item
        for fact_id in shared_ids
        for item in (
            (blocks.get(fact_id) or {}).get("select")
            if isinstance((blocks.get(fact_id) or {}).get("select"), list)
            else [(blocks.get(fact_id) or {}).get("select")]
        )
        if item
    ]
    payload = {
        "case_context": case_context,
        "candidates": [
            {"id": branch.id, "label": branch.label, "score": branch.posterior}
            for branch in state.branches.values() if branch.level == 1
        ],
        "fact_catalog_core": [fact.to_dict() for fact in shared],
        "selection_status_by_id": {fact.id: "eligible" for fact in shared},
        "eligible_fact_ids": shared_ids,
        "accounted_evidence_history": [],
        "discriminator_rules": rules,
        "evidence_provenance": [],
        "selection_goal": "global_discrimination",
    }
    raw = dict(global_selector(payload))
    selected = clean_selected_fact_ids(
        raw,
        shared_ids,
        limit=2,
        allow_abstain=PRESETS[preset].selector_abstains,
    )
    return bool(selected)


def _dynamic_target_resolver(
    state: DiagnosticState,
    *,
    case_id: str,
    family_judge: Callable[[str, list[str]], int],
    judge_cache: dict[str, int],
    judge_cache_path: Path,
) -> Callable[[Mapping[str, Any]], str | None]:
    rows = sorted(
        (branch for branch in state.branches.values() if branch.level == 1),
        key=lambda branch: branch.id,
    )
    labels = [branch.label for branch in rows]

    def resolve(reference: Mapping[str, Any]) -> str | None:
        target = str(
            reference.get("target_name") or reference.get("target_l1") or ""
        )
        if not target:
            return None
        key = f"l1target::{case_id}::{stable_hash(labels)[:16]}::{_norm(target)}"
        if key not in judge_cache:
            judge_cache[key] = int(family_judge(target, labels))
            _atomic_json(judge_cache_path, judge_cache)
        index = judge_cache[key]
        return rows[index].id if 0 <= index < len(rows) else None

    return resolve


def _compiler_hits(
    trace: Mapping[str, Any], blocks: Mapping[str, Mapping[str, Any]],
) -> int:
    return sum(
        int((blocks.get(fact_id) or {}).get("n_evidence") or 0)
        for fact_id in trace.get("selected_fact_ids") or ()
    )


def _load_legacy_record(
    profile: str,
    case_id: str,
    trace_dir: Path,
    *,
    fingerprint: str,
) -> dict[str, Any]:
    path = trace_dir / f"{profile}__{case_id}.json"
    row = json.loads(path.read_text(encoding="utf-8"))
    if row.get("status") != "OK":
        raise ValueError(f"legacy trace is not OK: {path}")
    return {
        "status": "OK",
        "schema_version": 1,
        "run_fingerprint": fingerprint,
        "track": "B",
        "arm": "B0",
        "preset": "e1q_legacy",
        "profile": profile,
        "prior_mode": "branch",
        "case_id": case_id,
        "shared_tree_hash": row.get("shared_tree_hash"),
        "gold": {
            "initial": row["gold"]["initial"]["l1"],
            "final": row["gold"]["final"]["l1"],
        },
        "gold_rounds": [
            {
                "round": 0,
                **row["gold"]["initial"]["l1"],
            },
            {
                "round": 2,
                **row["gold"]["final"]["l1"],
            },
        ],
        "metrics": row.get("talp_metrics") or {},
        "profile_rule_hits": row.get("profile_rule_hits", 0),
        "trace_source": str(path.relative_to(ROOT)),
        "answer_mapper_called": False,
    }


def _metric_block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    finals = [row["gold"]["final"] for row in rows]
    initials = [
        row["gold"].get("initial", row["gold"]["final"]) for row in rows
    ]
    ranks = [item["rank"] for item in finals if item.get("rank") is not None]
    direction_rows = [
        item
        for row in rows for item in row.get("metrics", {}).get("direction_rows", [])
        if item.get("ok") is not None
    ]
    by_kind = {}
    for kind in ("rulein", "ruleout", "shared"):
        kind_rows = [item for item in direction_rows if item["kind"] == kind]
        values = [bool(item["ok"]) for item in kind_rows]
        target_ranks = [
            item.get("target_rank") for item in kind_rows
            if kind in {"rulein", "ruleout"}
        ]
        verdict_key = (
            "rule_in_verdict" if kind == "rulein" else "rule_out_verdict"
        )
        by_kind[kind] = {
            "ok": sum(values), "n": len(values),
            "accuracy": sum(values) / len(values) if values else None,
            "target@1": (
                sum(rank == 1 for rank in target_ranks) / len(target_ranks)
                if target_ranks else None
            ),
            "target@3": (
                sum(rank is not None and rank <= 3 for rank in target_ranks)
                / len(target_ranks) if target_ranks else None
            ),
            "abstain_rate": (
                sum(item.get(verdict_key) == "none" for item in kind_rows)
                / len(kind_rows) if kind_rows and kind != "shared" else None
            ),
        }
    depleted = [
        bool(row.get("metrics", {}).get("depleted_false_select"))
        for row in rows
        if row.get("metrics", {}).get("depleted_false_select") is not None
    ]
    rank_changes = [
        initial["rank"] - final["rank"]
        for initial, final in zip(initials, finals)
        if initial.get("rank") is not None and final.get("rank") is not None
    ]
    starvation = [
        initial["rank"] > 1 and final["rank"] >= initial["rank"]
        for initial, final in zip(initials, finals)
        if initial.get("rank") is not None and final.get("rank") is not None
    ]
    trajectory_auc = []
    margins = []
    round_numbers = sorted({
        point.get("round")
        for row in rows for point in row.get("gold_rounds") or ()
        if point.get("round") is not None
    })
    probability_by_round = {}
    for row in rows:
        points = [
            point for point in row.get("gold_rounds") or ()
            if point.get("rank") is not None
        ]
        if points:
            trajectory_auc.append(
                statistics.mean(1 / point["rank"] for point in points)
            )
        snapshots = row.get("trace", {}).get("posterior_trajectory") or ()
        gold_id = row["gold"]["final"].get("branch_id")
        if snapshots and gold_id:
            final_snapshot = snapshots[-1].get("posteriors") or ()
            gold_score = next(
                (
                    float(item["posterior"]) for item in final_snapshot
                    if item.get("id") == gold_id
                ),
                None,
            )
            distractors = [
                float(item["posterior"]) for item in final_snapshot
                if item.get("id") != gold_id
            ]
            if gold_score is not None and distractors:
                margins.append(gold_score - max(distractors))
    for round_number in round_numbers:
        values = []
        for row in rows:
            point = next(
                (
                    item for item in row.get("gold_rounds") or ()
                    if item.get("round") == round_number
                ),
                None,
            )
            if point is not None:
                values.append(bool(point.get("top1")))
        if values:
            probability_by_round[str(round_number)] = statistics.mean(values)
    ro_eligible = [
        row for row in rows
        if row.get("metrics", {}).get("has_cross_l1_ruleout")
    ]
    ro_ineligible = [
        row for row in rows
        if not row.get("metrics", {}).get("has_cross_l1_ruleout")
    ]
    return {
        "cases": len(rows),
        "mean_facts": statistics.mean(
            len(row.get("trace", {}).get("selected_fact_ids") or ())
            for row in rows
        ),
        "existence_rate": sum(item.get("exists", False) for item in finals) / len(rows),
        "probability_at_1": sum(item.get("top1", False) for item in finals) / len(rows),
        "top3": sum(
            item.get("rank") is not None and item["rank"] <= 3 for item in finals
        ) / len(rows),
        "mrr": sum(1 / rank for rank in ranks) / len(rows),
        "mean_rank_when_present": statistics.mean(ranks) if ranks else None,
        "rank_improved_worsened_tied": {
            "improved": sum(value > 0 for value in rank_changes),
            "worsened": sum(value < 0 for value in rank_changes),
            "tied": sum(value == 0 for value in rank_changes),
        },
        "starvation_rate": statistics.mean(starvation) if starvation else None,
        "trajectory_mrr_auc": (
            statistics.mean(trajectory_auc) if trajectory_auc else None
        ),
        "gold_vs_top_distractor_margin": (
            statistics.mean(margins) if margins else None
        ),
        "probability_at_1_by_round": probability_by_round,
        "select@1": statistics.mean(
            bool(row.get("metrics", {}).get("select@1")) for row in rows
        ),
        "select@2": statistics.mean(
            bool(row.get("metrics", {}).get("select@2")) for row in rows
        ),
        "select_valid": statistics.mean(
            bool(row.get("metrics", {}).get("select_valid")) for row in rows
        ),
        "ro_select@1": statistics.mean(
            bool(row.get("metrics", {}).get("ro_select@1")) for row in rows
        ),
        "ro_select@2": statistics.mean(
            bool(row.get("metrics", {}).get("ro_select@2")) for row in rows
        ),
        "global_ro_select@1": statistics.mean(
            bool(row.get("metrics", {}).get("global_ro_select@1")) for row in rows
        ),
        "dedicated_ro_select@1": statistics.mean(
            bool(row.get("metrics", {}).get("dedicated_ro_select@1"))
            for row in rows
        ),
        "dedicated_ro_select_valid": statistics.mean(
            bool(row.get("metrics", {}).get("dedicated_ro_select_valid"))
            for row in rows
        ),
        "ro_eligible_cases": len(ro_eligible),
        "dedicated_ro_select_valid_on_eligible": (
            statistics.mean(
                bool(row.get("metrics", {}).get("dedicated_ro_select_valid"))
                for row in ro_eligible
            ) if ro_eligible else None
        ),
        "dedicated_ro_correct_abstain_on_ineligible": (
            statistics.mean(
                bool(row.get("metrics", {}).get("dedicated_ro_correct_abstain"))
                for row in ro_ineligible
            ) if ro_ineligible else None
        ),
        "displacement_count": sum(
            int(row.get("metrics", {}).get("displacement_count") or 0)
            for row in rows
        ),
        "displaced_valid_cases": sum(
            bool(row.get("metrics", {}).get("displaced_valid_fact"))
            for row in rows
        ),
        "selector_false_abstain": statistics.mean(
            bool(row.get("metrics", {}).get("selector_false_abstain"))
            for row in rows
        ),
        "depleted_false_select": (
            statistics.mean(depleted) if depleted else None
        ),
        "depleted_cases": len(depleted),
        "target_accuracy": by_kind,
        "profile_rule_hits": sum(int(row.get("profile_rule_hits") or 0) for row in rows),
    }


def _paired_bootstrap(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
    seed: int,
) -> dict[str, Any]:
    left = {row["case_id"]: row for row in baseline}
    right = {row["case_id"]: row for row in candidate}
    case_ids = sorted(set(left) & set(right))

    def value(row, metric):
        final = row["gold"]["final"]
        if metric == "top1":
            return float(bool(final.get("top1")))
        if metric == "mrr":
            rank = final.get("rank")
            return 1.0 / rank if rank else 0.0
        if metric == "rank_gain":
            rank = final.get("rank")
            return -float(rank) if rank else 0.0
        if metric == "facts_saved":
            return -float(
                len(row.get("trace", {}).get("selected_fact_ids") or ())
            )
        metric_key = {
            "select1": "select@1",
            "select_valid": "select_valid",
            "ro_select1": "ro_select@1",
        }[metric]
        return float(bool(row.get("metrics", {}).get(metric_key)))

    rng = random.Random(seed)
    output = {"cases": len(case_ids)}
    for metric in (
        "top1", "mrr", "rank_gain", "facts_saved",
        "select1", "select_valid", "ro_select1",
    ):
        deltas = [
            value(right[case_id], metric) - value(left[case_id], metric)
            for case_id in case_ids
        ]
        point = statistics.mean(deltas) if deltas else 0.0
        samples = []
        if case_ids:
            for _ in range(n_boot):
                drawn = [rng.choice(case_ids) for _ in case_ids]
                samples.append(statistics.mean(
                    value(right[case_id], metric) - value(left[case_id], metric)
                    for case_id in drawn
                ))
        samples.sort()
        lo = samples[int(0.025 * (len(samples) - 1))] if samples else None
        hi = samples[int(0.975 * (len(samples) - 1))] if samples else None
        output[metric] = {
            "delta": point,
            "ci95": [lo, hi],
            "resolved_positive": lo is not None and lo > 0,
        }
    return output


def _summarize(records: Sequence[Mapping[str, Any]], *, n_boot: int) -> dict[str, Any]:
    ok = [row for row in records if row.get("status") == "OK"]
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for row in ok:
        key = (
            row["track"], row["arm"], row["profile"], row.get("prior_mode", "uniform")
        )
        grouped.setdefault(key, []).append(row)
    by_group = {
        "::".join(key): _metric_block(rows) for key, rows in sorted(grouped.items())
    }
    paired = {}
    for track in ("A", "B"):
        for profile in DEFAULT_PROFILES:
            for prior in ("uniform", "branch"):
                comparisons = {
                    "B1": ("B1s", "B2", "B3", "B4", "B5", "S5", "A"),
                    "B0": ("B1", "B1s", "B2", "B3", "B4", "B5", "S5", "A"),
                }
                for baseline_arm, candidate_arms in comparisons.items():
                    baseline = grouped.get(
                        (track, baseline_arm, profile, prior), []
                    )
                    if not baseline:
                        continue
                    for arm in candidate_arms:
                        candidate = grouped.get((track, arm, profile, prior), [])
                        if candidate:
                            paired[
                                f"{track}::{profile}::{prior}::{arm}-{baseline_arm}"
                            ] = _paired_bootstrap(
                                baseline, candidate, n_boot=n_boot, seed=0
                            )
    gates = {}
    for profile in DEFAULT_PROFILES:
        comparison = paired.get(f"B::{profile}::branch::B2-B1")
        b1 = by_group.get(f"B::B1::{profile}::branch")
        b2 = by_group.get(f"B::B2::{profile}::branch")
        a1 = by_group.get(f"A::B1::{profile}::uniform")
        a2 = by_group.get(f"A::B2::{profile}::uniform")
        if comparison and b1 and b2:
            track_b_gate = {
                "existence_non_regression": (
                    b2["existence_rate"] >= b1["existence_rate"]
                ),
                "top3_non_regression": b2["top3"] >= b1["top3"],
                "mrr_non_regression": b2["mrr"] >= b1["mrr"],
                "resolved_top1_or_mean_rank": bool(
                    comparison["top1"]["resolved_positive"]
                    or comparison["rank_gain"]["resolved_positive"]
                ),
            }
            track_a_gate = {}
            if a1 and a2:
                for metric in ("select_valid",):
                    track_a_gate[f"{metric}_non_regression"] = (
                        a2[metric] >= a1[metric]
                    )
                for kind in ("rulein", "ruleout", "shared"):
                    left = a1["target_accuracy"][kind]["accuracy"]
                    right = a2["target_accuracy"][kind]["accuracy"]
                    track_a_gate[f"{kind}_non_regression"] = (
                        left is None or (right is not None and right >= left)
                    )
                track_a_gate["false_abstain_non_regression"] = (
                    a2["selector_false_abstain"]
                    <= a1["selector_false_abstain"]
                )
                track_a_gate["depleted_false_select_reduced"] = bool(
                    a1["depleted_false_select"] is not None
                    and a2["depleted_false_select"] is not None
                    and a2["depleted_false_select"]
                    < a1["depleted_false_select"]
                )
                track_a_gate["compiler_rules_nonempty"] = (
                    a2["profile_rule_hits"] > 0
                )
            gates[profile] = {
                "track_a": track_a_gate,
                "track_b": track_b_gate,
                "passed": (
                    all(track_b_gate.values())
                    and (not track_a_gate or all(track_a_gate.values()))
                ),
            }
            b3 = by_group.get(f"B::B3::{profile}::branch")
            a3 = by_group.get(f"A::B3::{profile}::uniform")
            if b3 and a3:
                b2_ruleout = a2["target_accuracy"]["ruleout"]["accuracy"] if a2 else None
                b3_ruleout = a3["target_accuracy"]["ruleout"]["accuracy"]
                gates[profile]["b3_dual_ruleout"] = {
                    "ro_select_valid_nonzero": (
                        a3["dedicated_ro_select_valid_on_eligible"] is not None
                        and a3["dedicated_ro_select_valid_on_eligible"] > 0
                    ),
                    "ruleout_or_ranking_improved": bool(
                        (
                            b2_ruleout is not None
                            and b3_ruleout is not None
                            and b3_ruleout > b2_ruleout
                        )
                        or b3["mrr"] > b2["mrr"]
                    ),
                }
                gates[profile]["b3_dual_ruleout"]["passed"] = all(
                    gates[profile]["b3_dual_ruleout"].values()
                )
        branch_cmp = paired.get(f"A::{profile}::uniform::A-B1")
        branch_base = by_group.get(f"A::B1::{profile}::uniform")
        branch_arm = by_group.get(f"A::A::{profile}::uniform")
        if branch_cmp and branch_base and branch_arm:
            gates.setdefault(profile, {})["branch_proposal"] = {
                "select1_resolved_superiority": branch_cmp["select1"][
                    "resolved_positive"
                ],
                "select_valid_non_regression": (
                    branch_arm["select_valid"] >= branch_base["select_valid"]
                ),
                "promoted": bool(
                    branch_cmp["select1"]["resolved_positive"]
                    and branch_arm["select_valid"] >= branch_base["select_valid"]
                ),
            }
    return {
        "completed": len(ok),
        "errors": len(records) - len(ok),
        "by_group": by_group,
        "paired_case_cluster_bootstrap": paired,
        "promotion_gates": gates,
    }


def run(args) -> dict[str, Any]:
    composed = _load_module("l1_bfs_composed", COMPOSED_SCRIPT)
    partial = _load_module("l1_bfs_partial", PARTIAL_SCRIPT)
    talp = _load_module("l1_bfs_talp", TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    profiles = tuple(item for item in args.profiles.split(",") if item)
    arms = tuple(item for item in args.arms.split(",") if item)
    tracks = tuple(item for item in args.tracks.split(",") if item)
    prior_modes = tuple(item for item in args.prior_modes.split(",") if item)
    if set(profiles) - set(DEFAULT_PROFILES):
        raise ValueError(f"unknown profiles: {profiles}")
    if set(arms) - set(ARM_SPECS):
        raise ValueError(f"unknown arms: {arms}")
    if set(tracks) - {"A", "B"}:
        raise ValueError(f"unknown tracks: {tracks}")
    if set(prior_modes) - {"uniform", "branch"}:
        raise ValueError(f"unknown prior modes: {prior_modes}")

    arm_paths = {
        "p5_headline": args.p5_arm_output,
        "g2ur": args.g2ur_arm_output,
    }
    frozen_arms = composed.FrozenOfflineArms(talp, arm_paths)
    projections = {case["id"]: _manual_projection(case) for case in cases}
    contract_audit = {
        "cases": len(cases),
        "label_agreement_cases": sum(
            projection["label_agreement"] for projection in projections.values()
        ),
        "track_a_cross_l1_eligible_cases": sum(
            len(projection["labels"]) >= 2 for projection in projections.values()
        ),
        "observed_cross_l1_ruleout_cases": sum(
            any(
                row["role"] == "rule_out_distractor"
                for row in projection["findings"]
            )
            for projection in projections.values()
        ),
        "observed_cross_l1_ruleout_findings": sum(
            row["role"] == "rule_out_distractor"
            for projection in projections.values()
            for row in projection["findings"]
        ),
    }
    identity = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "profiles": profiles,
        "arms": arms,
        "tracks": tracks,
        "prior_modes": prior_modes,
        "branch_mode": "recall_hints_gap",
        "shared_tree_dir": str(args.shared_tree_dir),
        "arm_outputs": {
            profile: {"path": str(path), "sha256": _sha256(path)}
            for profile, path in arm_paths.items()
        },
        "core_sha256": _sha256(
            ROOT / "src" / "agentclinic_tree_dx" / "l1_evidence_bfs.py"
        ),
        "prompt_sha256": {
            path.name: _sha256(path)
            for path in PROMPT_DIR.glob("l1_*txt")
        },
    }
    fingerprint = stable_hash(identity)
    run_dir = args.output_dir / args.tag
    trace_dir = run_dir / "traces"
    _atomic_json(run_dir / "manifest.json", {
        **identity,
        "run_fingerprint": fingerprint,
        "cases": [case["id"] for case in cases],
        "presets": {name: asdict(value) for name, value in PRESETS.items()},
        "l1_contract_audit": contract_audit,
        "offline_p5_compat_reference": {
            profile: frozen_arms.reference_metrics(profile) for profile in profiles
        },
    })

    from agentclinic_tree_dx.llm_client import RobustLLMClient
    llm = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cached = CachedLLM(llm, run_dir / "llm_cache.json", args.model)
    family_judge = composed._family_judge_factory(args.model)
    judge_cache_path = run_dir / "judge_cache.json"
    try:
        judge_cache = json.loads(judge_cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        judge_cache = {}
    records: list[dict[str, Any]] = []

    for case in cases:
        tree_payload = json.loads(
            (args.shared_tree_dir / f"{case['id']}.json").read_text(encoding="utf-8")
        )
        frozen_tree = composed._deserialize_state(tree_payload["state"])
        projection = projections[case["id"]]
        for track in tracks:
            if track == "A" and len(projection["labels"]) < 2:
                continue
            source_state = (
                _manual_state(case["id"], projection)
                if track == "A" else frozen_tree
            )
            for profile in profiles:
                for arm in arms:
                    spec = ARM_SPECS[arm]
                    if spec.legacy:
                        if track == "A":
                            continue
                        if "branch" not in prior_modes:
                            continue
                        trace_path = trace_dir / (
                            f"B__B0__{profile}__branch__{case['id']}.json"
                        )
                        if args.resume and trace_path.is_file():
                            record = json.loads(trace_path.read_text(encoding="utf-8"))
                        else:
                            record = _load_legacy_record(
                                profile,
                                case["id"],
                                args.legacy_trace_dir,
                                fingerprint=fingerprint,
                            )
                            _atomic_json(trace_path, record)
                        records.append(record)
                        continue
                    modes = ("uniform",) if track == "A" else prior_modes
                    for prior_mode in modes:
                        trace_path = trace_dir / (
                            f"{track}__{arm}__{profile}__{prior_mode}"
                            f"__{case['id']}.json"
                        )
                        if args.resume and trace_path.is_file():
                            existing = json.loads(trace_path.read_text(encoding="utf-8"))
                            if (
                                existing.get("status") == "OK"
                                and existing.get("run_fingerprint") == fingerprint
                            ):
                                records.append(existing)
                                continue
                        started = time.monotonic()
                        try:
                            facts = _facts_for_case(
                                frozen_tree,
                                case["annotation"],
                                composed,
                                deduplicate=spec.deduplicate,
                            )
                            blocks = frozen_arms.blocks(
                                profile, case["id"], facts
                            )
                            global_fn, in_fn, out_fn, ro_fn = _runtime_functions(
                                cached,
                                spec.preset,
                                talp,
                                branch_proposal=spec.branch_proposal,
                                disable_ruleout=spec.disable_ruleout,
                            )
                            pipeline = L1EvidenceBFSPipeline(
                                preset=spec.preset,
                                global_selector=global_fn,
                                rule_in_allocator=in_fn,
                                rule_out_allocator=out_fn,
                                ruleout_selector=(
                                    ro_fn
                                    if PRESETS[spec.preset].ruleout_selector == "dedicated"
                                    else None
                                ),
                                max_micro_rounds=spec.max_rounds,
                                facts_per_cycle=spec.facts_per_cycle,
                                enforce_canonical_dedup=spec.deduplicate,
                                stop_policy=(
                                    EvidenceQuorumF4Policy()
                                    if spec.stop_policy == "evidence_quorum_f4"
                                    else None
                                ),
                            )
                            depleted_false_select = _depleted_false_select(
                                global_selector=global_fn,
                                preset=spec.preset,
                                state=source_state,
                                case_context=case["case_text"],
                                facts=facts,
                                blocks=blocks,
                                projection=projection,
                                composed=composed,
                            )
                            initial = (
                                _manual_gold(source_state, projection)
                                if track == "A"
                                else _dynamic_gold(
                                    source_state, case, family_judge,
                                    judge_cache, judge_cache_path,
                                )
                            )
                            final_state, trace = pipeline.run(
                                source_state,
                                case_context=case["case_text"],
                                facts=facts,
                                compiler_master_blocks=blocks,
                                prior_mode=prior_mode,
                            )
                            final = (
                                _manual_gold(final_state, projection)
                                if track == "A"
                                else _dynamic_gold(
                                    final_state, case, family_judge,
                                    judge_cache, judge_cache_path,
                                )
                            )
                            if track == "A":
                                target_resolver = lambda reference: (
                                    projection["label_to_id"].get(
                                        str(reference.get("target_l1") or "")
                                    )
                                )
                            else:
                                target_resolver = _dynamic_target_resolver(
                                    final_state,
                                    case_id=case["id"],
                                    family_judge=family_judge,
                                    judge_cache=judge_cache,
                                    judge_cache_path=judge_cache_path,
                                )
                            metrics = _track_a_metrics(
                                trace,
                                facts,
                                projection,
                                composed,
                                gold_branch_id=final.get("branch_id"),
                                target_resolver=target_resolver,
                                depleted_false_select=depleted_false_select,
                            )
                            record = {
                                "status": "OK",
                                "schema_version": 1,
                                "run_fingerprint": fingerprint,
                                "track": track,
                                "arm": arm,
                                "preset": spec.preset,
                                "profile": profile,
                                "prior_mode": prior_mode,
                                "case_id": case["id"],
                                "shared_tree_hash": tree_payload.get("tree_hash"),
                                "duration_seconds": round(
                                    time.monotonic() - started, 3
                                ),
                                "gold": {"initial": initial, "final": final},
                                "gold_rounds": _gold_trajectory(
                                    trace, final.get("branch_id")
                                ),
                                "metrics": metrics,
                                "profile_rule_hits": _compiler_hits(trace, blocks),
                                "trace": trace,
                                "answer_mapper_called": False,
                            }
                        except Exception as exc:
                            record = {
                                "status": "ERROR",
                                "schema_version": 1,
                                "run_fingerprint": fingerprint,
                                "track": track,
                                "arm": arm,
                                "preset": spec.preset,
                                "profile": profile,
                                "prior_mode": prior_mode,
                                "case_id": case["id"],
                                "duration_seconds": round(
                                    time.monotonic() - started, 3
                                ),
                                "error": f"{type(exc).__name__}: {exc}",
                                "answer_mapper_called": False,
                            }
                        _atomic_json(trace_path, record)
                        records.append(record)
                        _atomic_json(
                            run_dir / "summary.json",
                            _summarize(records, n_boot=args.n_boot),
                        )
    summary = _summarize(records, n_boot=args.n_boot)
    summary["run_fingerprint"] = fingerprint
    _atomic_json(run_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--profiles", default=",".join(DEFAULT_PROFILES))
    parser.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    parser.add_argument("--tracks", default="A,B")
    parser.add_argument("--prior-modes", default="branch,uniform")
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="LLM decoding temperature; use 0 for variance-controlled reruns",
    )
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--tag", default="talp17_l1_evidence_bfs")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "logs" / "l1_evidence_bfs"
    )
    parser.add_argument(
        "--shared-tree-dir", type=Path, default=DEFAULT_SHARED_TREE_DIR
    )
    parser.add_argument(
        "--legacy-trace-dir", type=Path, default=DEFAULT_LEGACY_TRACE_DIR
    )
    parser.add_argument(
        "--p5-arm-output", type=Path, default=DEFAULT_ARM_OUTPUTS["p5_headline"]
    )
    parser.add_argument(
        "--g2ur-arm-output", type=Path, default=DEFAULT_ARM_OUTPUTS["g2ur"]
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
