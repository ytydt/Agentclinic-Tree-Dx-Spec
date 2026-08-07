"""MedCaseReasoning formal metrics: single-trajectory Acc + Reasoning Recall."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .judges import LexicalJudge, LLMJudge


def score_mcr_case(
    projection: Mapping[str, Any],
    gold: Mapping[str, Any],
    judge: LexicalJudge | LLMJudge,
) -> dict[str, Any]:
    pred_dx = str(
        projection.get("pred_diagnosis")
        or ""
    ).strip()
    if not pred_dx:
        ddx = projection.get("pred_ddx") or []
        if ddx and isinstance(ddx[0], Mapping):
            pred_dx = str(ddx[0].get("label") or "").strip()
        elif ddx:
            pred_dx = str(ddx[0]).strip()
    gold_dx = str(gold.get("final_diagnosis") or "").strip()
    trace = str(projection.get("pred_reasoning_trace") or "")
    points = [str(x).strip() for x in (gold.get("reasoning_points") or []) if str(x).strip()]

    if isinstance(judge, LLMJudge):
        dx_hit = judge.mcr_diagnosis_correct(pred_dx, gold_dx) if pred_dx and gold_dx else False
        if points:
            recall, matching_dict = judge.reasoning_recall_coverage(points, trace)
            point_hits = [
                bool((matching_dict.get(str(i + 1)) or matching_dict.get(str(i)) or []))
                for i in range(len(points))
            ]
        else:
            recall, matching_dict, point_hits = 0.0, {}, []
    else:
        dx_hit = judge.diagnoses_equivalent(pred_dx, gold_dx) if pred_dx and gold_dx else False
        point_hits = [judge.reasoning_point_covered(p, trace) for p in points]
        recall = (sum(1 for h in point_hits if h) / len(points)) if points else 0.0
        matching_dict = {}

    return {
        "case_id": str(projection.get("case_id") or gold.get("case_id") or ""),
        "pred_diagnosis": pred_dx,
        "gold_diagnosis": gold_dx,
        "diagnostic_hit": bool(dx_hit),
        "reasoning_recall": float(recall),
        "n_reasoning_points": len(points),
        "n_reasoning_points_covered": int(sum(1 for h in point_hits if h)),
        "point_hits": point_hits,
        "matching_dict": matching_dict,
    }


def aggregate_mcr_scores(
    case_scores: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    n = len(case_scores)
    hits = sum(1 for c in case_scores if c.get("diagnostic_hit"))
    recalls = [float(c.get("reasoning_recall") or 0.0) for c in case_scores]
    return {
        "n_cases": n,
        # Protocol field name — NOT 10shot_accuracy
        "diagnostic_accuracy_single_trajectory": (hits / n) if n else 0.0,
        "n_diagnostic_hits": hits,
        "reasoning_recall_mean": (sum(recalls) / n) if n else 0.0,
        "sampling_protocol": "single_trajectory_v1",
        "note": (
            "Not MedCaseReasoning official 10-shot Acc; do not cross-compare "
            "with paper tables."
        ),
    }
