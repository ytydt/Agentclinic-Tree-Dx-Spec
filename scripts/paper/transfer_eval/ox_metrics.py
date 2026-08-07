"""Open-XDDx formal metrics: Diagnostic R/P/F1 + Interpretation Acc (+ optional NLG)."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .judges import LexicalJudge, LLMJudge
from .matching import (
    SetMatchResult,
    greedy_set_match,
    labels_from_pred_ddx,
    micro_aggregate,
)


def _interp_lists(
    pred_interp: Mapping[str, Sequence[str]],
    gold_interp: Mapping[str, Sequence[str]],
    edge_pred: str,
    edge_gold: str,
) -> tuple[list[str], list[str]]:
    pred_items = [str(x) for x in (pred_interp.get(edge_pred) or []) if str(x).strip()]
    gold_items = [str(x) for x in (gold_interp.get(edge_gold) or []) if str(x).strip()]
    return pred_items, gold_items


def interpretation_accuracy_on_edges(
    *,
    edges: Sequence[Mapping[str, Any]],
    pred_interpretation: Mapping[str, Sequence[str]],
    gold_interpretation: Mapping[str, Sequence[str]],
    judge: LexicalJudge | LLMJudge,
) -> dict[str, Any]:
    """Eq.2-style: correct interpretation items / total gold items on matched edges."""
    correct = 0
    total = 0
    per_edge: list[dict[str, Any]] = []
    for e in edges:
        pred_lab = str(e.get("pred_label") or "")
        gold_lab = str(e.get("gold_label") or "")
        pred_items, gold_items = _interp_lists(
            pred_interpretation, gold_interpretation, pred_lab, gold_lab
        )
        # Greedy item match gold→pred
        used_p: set[int] = set()
        edge_correct = 0
        for g in gold_items:
            total += 1
            hit = False
            for i, p in enumerate(pred_items):
                if i in used_p:
                    continue
                if judge.interpretation_item_match(p, g):
                    used_p.add(i)
                    hit = True
                    break
            if hit:
                correct += 1
                edge_correct += 1
        per_edge.append({
            "pred_label": pred_lab,
            "gold_label": gold_lab,
            "n_gold_items": len(gold_items),
            "n_pred_items": len(pred_items),
            "n_correct_items": edge_correct,
        })
    acc = (correct / total) if total else 0.0
    return {
        "interpretation_accuracy": acc,
        "n_correct_interpretations": correct,
        "n_total_interpretations": total,
        "per_edge": per_edge,
    }


def optional_bertscore(
    pred_texts: Sequence[str],
    gold_texts: Sequence[str],
) -> dict[str, Any]:
    """Compute BERTScore F1 if dependency present; else skip."""
    if not pred_texts or not gold_texts:
        return {"skipped": True, "reason": "empty_texts"}
    try:
        from bert_score import score as bert_score  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"skipped": True, "reason": "bert_score_unavailable", "detail": str(exc)}
    # Align lengths by truncating to min
    n = min(len(pred_texts), len(gold_texts))
    if n == 0:
        return {"skipped": True, "reason": "empty_after_align"}
    try:
        _p, _r, f1 = bert_score(
            list(pred_texts[:n]),
            list(gold_texts[:n]),
            lang="en",
            verbose=False,
        )
        vals = [float(x) for x in f1]
        return {
            "skipped": False,
            "n_pairs": n,
            "bertscore_f1_mean": sum(vals) / len(vals) if vals else 0.0,
        }
    except Exception as exc:  # noqa: BLE001
        return {"skipped": True, "reason": "bert_score_failed", "detail": str(exc)}


def score_ox_case(
    projection: Mapping[str, Any],
    gold: Mapping[str, Any],
    judge: LexicalJudge | LLMJudge,
    *,
    nlg_metrics: bool = False,
) -> dict[str, Any]:
    pred_labels = labels_from_pred_ddx(projection.get("pred_ddx") or [])
    gold_labels = [str(x) for x in (gold.get("ddx_set") or []) if str(x).strip()]
    if not gold_labels and isinstance(gold.get("interpretation"), Mapping):
        gold_labels = [str(k) for k in gold["interpretation"].keys()]

    score_fn = judge.diagnosis_match_score
    # LLM returns 0/1; threshold 0.5. Lexical uses 0.7 via leaf_match_score.
    threshold = 0.5 if isinstance(judge, LLMJudge) else judge.threshold
    match: SetMatchResult = greedy_set_match(
        pred_labels,
        gold_labels,
        score_fn=score_fn,
        threshold=threshold,
    )
    pred_interp = dict(projection.get("pred_interpretation") or {})
    gold_interp = dict(gold.get("interpretation") or {})
    interp = interpretation_accuracy_on_edges(
        edges=match.as_dict()["edges"],
        pred_interpretation=pred_interp,
        gold_interpretation=gold_interp,
        judge=judge,
    )
    out: dict[str, Any] = {
        "case_id": str(projection.get("case_id") or gold.get("case_id") or ""),
        "diagnostic": match.as_dict(),
        "interpretation": interp,
        "pred_ddx_labels": pred_labels,
        "gold_ddx_labels": gold_labels,
    }
    if nlg_metrics:
        pred_flat: list[str] = []
        gold_flat: list[str] = []
        for e in match.as_dict()["edges"]:
            pl = str(e["pred_label"])
            gl = str(e["gold_label"])
            for s in pred_interp.get(pl) or []:
                pred_flat.append(str(s))
            for s in gold_interp.get(gl) or []:
                gold_flat.append(str(s))
        # Pairwise bag: zip truncated
        n = min(len(pred_flat), len(gold_flat))
        out["nlg"] = optional_bertscore(pred_flat[:n], gold_flat[:n])
    return out


def aggregate_ox_scores(
    case_scores: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    matches = []
    from .matching import SetMatchResult, MatchEdge

    for cs in case_scores:
        d = cs.get("diagnostic") or {}
        edges = [
            MatchEdge(
                pred_idx=int(e["pred_idx"]),
                gold_idx=int(e["gold_idx"]),
                pred_label=str(e["pred_label"]),
                gold_label=str(e["gold_label"]),
                score=float(e.get("score") or 0.0),
            )
            for e in (d.get("edges") or [])
        ]
        matches.append(
            SetMatchResult(
                edges=edges,
                unmatched_pred=list(d.get("unmatched_pred") or []),
                unmatched_gold=list(d.get("unmatched_gold") or []),
                tp=int(d.get("tp") or 0),
                n_pred=int(d.get("n_pred") or 0),
                n_gold=int(d.get("n_gold") or 0),
            )
        )
    micro = micro_aggregate(matches)
    # Macro mean of per-case P/R/F1
    precs = [float((c.get("diagnostic") or {}).get("precision") or 0.0) for c in case_scores]
    recs = [float((c.get("diagnostic") or {}).get("recall") or 0.0) for c in case_scores]
    f1s = [float((c.get("diagnostic") or {}).get("f1") or 0.0) for c in case_scores]
    n = len(case_scores) or 1
    interp_correct = sum(
        int((c.get("interpretation") or {}).get("n_correct_interpretations") or 0)
        for c in case_scores
    )
    interp_total = sum(
        int((c.get("interpretation") or {}).get("n_total_interpretations") or 0)
        for c in case_scores
    )
    nlg_vals = [
        float((c.get("nlg") or {}).get("bertscore_f1_mean"))
        for c in case_scores
        if isinstance(c.get("nlg"), Mapping)
        and not (c.get("nlg") or {}).get("skipped")
        and (c.get("nlg") or {}).get("bertscore_f1_mean") is not None
    ]
    out: dict[str, Any] = {
        "n_cases": len(case_scores),
        "diagnostic_micro": micro,
        "diagnostic_macro": {
            "precision": sum(precs) / n,
            "recall": sum(recs) / n,
            "f1": sum(f1s) / n,
        },
        "interpretation_accuracy": (
            (interp_correct / interp_total) if interp_total else 0.0
        ),
        "interpretation_n_correct": interp_correct,
        "interpretation_n_total": interp_total,
    }
    if nlg_vals:
        out["bertscore_f1_mean"] = sum(nlg_vals) / len(nlg_vals)
    elif any(isinstance(c.get("nlg"), Mapping) for c in case_scores):
        # Preserve skip reason from first
        for c in case_scores:
            if isinstance(c.get("nlg"), Mapping):
                out["nlg"] = dict(c["nlg"])
                break
    return out
