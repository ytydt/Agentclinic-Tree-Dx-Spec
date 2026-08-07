#!/usr/bin/env python3
"""Opt-in overlay: targeted L2 gapfill after Config A, before joint ranking.

Research arm default for production smoke: ``ALL_B_b1`` (hybrid protocol).
Default OFF in the standard harness; enable via ``--targeted-l2-gapfill``.
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import diagnosisarena_l2_pipeline as l2pipe  # noqa: E402
import eval_l2_branch_generation_ab as ab  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
import eval_l2_targeted_gapfill_hybrid as hybrid  # noqa: E402
from agentclinic_tree_dx.controller import AgentClinicTreeController  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import assert_no_gold_leak  # noqa: E402
from agentclinic_tree_dx.state import DiagnosticState  # noqa: E402

DEFAULT_ARM = "ALL_B_b1"
ARM_RE = re.compile(r"^(T|ALL)_([AB])_b([12])$")
SELECTOR_PROMPT = hybrid.SELECTOR_PROMPT


def parse_arm(arm: str) -> tuple[bool, str, int]:
    match = ARM_RE.match(str(arm or "").strip())
    if not match:
        raise ValueError(
            "targeted gapfill arm must match T|ALL _ A|B _ b1|b2, got %r" % arm
        )
    return match.group(1) == "T", match.group(2), int(match.group(3))


def _serialize_state(state: DiagnosticState) -> dict[str, Any]:
    return ab._serialise_state(state)


def apply_targeted_l2_gapfill(
    *,
    l2_state: DiagnosticState,
    cached_adapter: Any,
    cache_dir: Path,
    model: str,
    arm: str = DEFAULT_ARM,
    candidate_budget: int = 24,
    snippet_budget: int = 12,
    call_timeout: float = 240.0,
    temperature: float = 0.0,
) -> tuple[DiagnosticState, dict[str, Any]]:
    """Augment a post–Config-A state with hybrid-style targeted L2 additions.

    Builds a frozen B recall asset from the L1 seed (label-blind), runs the
    hybrid selector path for ``arm``, and returns a new DiagnosticState plus
    a compact audit. Does not open gold.
    """
    targeted, source, budget = parse_arm(arm)
    if source != "B":
        # Source A is live per-parent rebuild; smoke overlay standardises on B.
        raise ValueError(
            "pipeline overlay currently supports B-source arms only (got %s)" % arm
        )

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    c_tree = _serialize_state(l2_state)
    assert_no_gold_leak({"c_tree_labels": [
        str(b.get("label") or "") for b in (c_tree.get("branches") or {}).values()
    ]})

    seed = ab.strip_l2_seed(c_tree)
    seed_state = l2pipe.deserialize_state(seed)
    cfg_args = SimpleNamespace(
        model=model,
        temperature=temperature,
        call_timeout=call_timeout,
        candidate_budget=candidate_budget,
        snippet_budget=snippet_budget,
    )
    # Reuse the annotate LLM cache adapter when provided; also keep a dedicated
    # freeze cache for B-asset construction auditability.
    freeze_adapter = cached_adapter
    controller_freeze = AgentClinicTreeController(
        env=SimpleNamespace(ingest_external_context=lambda _value: None),
        llm=freeze_adapter,
        config=ab._controller_config("reuse_l1", cfg_args),
    )
    builder = getattr(controller_freeze, "build_l2_case_recall_asset", None)
    if not callable(builder):
        raise RuntimeError("controller.build_l2_case_recall_asset is required")
    asset = builder(seed_state)
    assert_no_gold_leak(asset)

    composed = competition.bfs._load_module(
        "targeted_gapfill_overlay",
        competition.bfs.COMPOSED_SCRIPT,
    )
    work_state = composed._deserialize_state(c_tree)
    controller_b = AgentClinicTreeController(
        env=SimpleNamespace(ingest_external_context=lambda _value: None),
        llm=cached_adapter,
        config=ab._controller_config("reuse_l1", cfg_args),
    )
    controller_b.freeze_l2_recall_asset(asset)

    trigger_probe = hybrid._shared_trigger_probe(
        controller=controller_b, state=work_state, tree=c_tree,
    )
    prompt = SELECTOR_PROMPT.read_text(encoding="utf-8")
    source_audits: dict[str, Any] = {}
    for parent_obj in sorted(
        (b for b in work_state.branches.values() if b.level == 1),
        key=lambda branch: branch.id,
    ):
        source_audits[parent_obj.id] = hybrid._prepare_parent_source(
            controller=controller_b,
            state=work_state,
            parent_obj=parent_obj,
            tree=c_tree,
            source="B",
            prompt=prompt,
            adapter=cached_adapter,
        )

    all_selected_names = sorted({
        str(candidate["disease"])
        for audit in source_audits.values()
        for candidate in audit.get("selected_candidates") or ()
    }, key=hybrid.canonical_disease)
    all_c_labels = [
        str(branch.get("label") or "")
        for branch in c_tree["branches"].values()
    ]
    global_uncovered, global_gap_status = hybrid._gap_uncovered(
        controller_b, all_selected_names, all_c_labels,
    )
    global_keys = {hybrid.canonical_disease(value) for value in global_uncovered}

    derived_tree, alloc_audit = hybrid.allocate_additions(
        tree=c_tree,
        parent_audits=source_audits,
        trigger_probe=trigger_probe,
        targeted=targeted,
        budget=budget,
        globally_uncovered=global_keys,
    )
    alloc_audit["targeted_only"] = targeted
    alloc_audit["source"] = source
    hybrid.validate_c_preserved(c_tree, derived_tree)
    hybrid._validate_tree_topology(derived_tree)

    new_state = l2pipe.deserialize_state(derived_tree)
    new_state.max_tree_depth = 2
    added = list(alloc_audit.get("added") or ())
    audit = {
        "enabled": True,
        "arm": arm,
        "targeted_only": targeted,
        "source": source,
        "budget": budget,
        "n_added": len(added),
        "added": added,
        "global_gap_status": global_gap_status,
        "n_global_uncovered": len(global_uncovered),
        "n_parents_probed": len(source_audits),
        "n_parents_triggered": sum(
            1 for row in trigger_probe.values() if row.get("targeted")
        ),
        "research_only": True,
        "protocol": "hybrid_overlay_v1",
    }
    return new_state, audit
