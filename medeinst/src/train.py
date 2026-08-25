"""
Critic-Driven Graph & Memory Evolution (CGME).

Paper: https://arxiv.org/abs/2601.06636
§4.1 / Algorithm 2 lines 1–16

This is not SGD. The paper's "training" accumulates illness graphs G and
exemplar base M using a critic model Mcritic (GPT-5) for at most 3 rounds.
"""

from __future__ import annotations

from typing import Any, Iterable

from src.data import Case
from src.llm import LLMClient
from src.model import CausalGraph, ECRAgent, GraphEdge, GraphNode
from src.prompts import CRITIC_SYSTEM
from src.utils import diagnoses_match, parse_json_object


def merge_graphs(prev: CausalGraph | None, summary: CausalGraph) -> CausalGraph:
    """§4.1 — G_merged ← Merge(G_prev, G_summary).

    [PARTIALLY_SPECIFIED] merge operator beyond node/edge union is unstated
    (critic then 'refines' the merged graph). We union by node id + edge tuple.
    """
    merged = CausalGraph(disease=summary.disease)
    if prev is not None:
        for node in prev.nodes.values():
            merged.add_node(node)
        for edge in prev.edges:
            merged.add_edge(edge)
    for node in summary.nodes.values():
        merged.add_node(node)
    seen = {(e.src, e.dst, e.relation) for e in merged.edges}
    for edge in summary.edges:
        key = (edge.src, edge.dst, edge.relation)
        if key not in seen:
            merged.add_edge(edge)
            seen.add(key)
    return merged


def critic_feedback(
    critic: LLMClient,
    case: Case,
    predicted: str,
    graph_summary: dict[str, Any],
) -> str:
    """§4.1 — Mcritic provides corrective feedback when d_pred ≠ y_gt."""
    import json

    raw = critic.complete(
        CRITIC_SYSTEM,
        json.dumps(
            {
                "x": case.x,
                "y_gt": case.y_gt,
                "d_pred": predicted,
                "graph_summary": graph_summary,
            },
            ensure_ascii=False,
        ),
    )
    try:
        return str(parse_json_object(raw).get("feedback", raw))
    except ValueError:
        return raw


def cgme_step(
    agent: ECRAgent,
    case: Case,
    critic: LLMClient,
    max_rounds: int = 3,
) -> bool:
    """Algorithm 2 lines 2–16 for one training sample.

    Returns True if a correct diagnosis was stored into G and M.
    Line 15: if the loop ends without success, the sample is discarded.
    """
    feedback: str | None = None
    # §4.1: critic only when prediction diverges; still merge on first-hit success
    for t in range(max_rounds):
        result = agent.dci_pipeline(case.x, feedback=feedback)
        if diagnoses_match(result.diagnosis, case.y_gt):
            prev = agent.illness_graphs.get(case.y_gt)
            agent.illness_graphs[case.y_gt] = merge_graphs(prev, result.graph)
            agent.exemplar_base.append(
                {
                    "x": case.x,
                    "y_gt": case.y_gt,
                    "path": result.graph_summary,
                    "case_id": case.case_id,
                }
            )
            return True
        feedback = critic_feedback(critic, case, result.diagnosis, result.graph_summary)
        _ = t
    return False


def run_cgme(
    agent: ECRAgent,
    train_cases: Iterable[Case],
    critic: LLMClient,
    max_rounds: int = 3,
) -> dict[str, int]:
    """§4.1 — execute DCI on D_train with critic-orchestrated refinement."""
    stored = 0
    discarded = 0
    for case in train_cases:
        ok = cgme_step(agent, case, critic, max_rounds=max_rounds)
        if ok:
            stored += 1
        else:
            discarded += 1
    return {"stored": stored, "discarded": discarded}


# Silence unused import warnings for re-exported graph types used by callers.
_ = (GraphNode, GraphEdge)
