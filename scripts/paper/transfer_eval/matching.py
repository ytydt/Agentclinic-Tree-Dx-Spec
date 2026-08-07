"""Set matching for multi-label DDx (greedy one-to-one)."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

_PAPER = Path(__file__).resolve().parents[1]
if str(_PAPER) not in sys.path:
    sys.path.insert(0, str(_PAPER))

from mapper_bind_repair import leaf_match_score  # noqa: E402

MatchFn = Callable[[str, str], float]

DEFAULT_LEXICAL_THRESHOLD = 0.7


@dataclass
class MatchEdge:
    pred_idx: int
    gold_idx: int
    pred_label: str
    gold_label: str
    score: float


@dataclass
class SetMatchResult:
    edges: list[MatchEdge] = field(default_factory=list)
    unmatched_pred: list[int] = field(default_factory=list)
    unmatched_gold: list[int] = field(default_factory=list)
    tp: int = 0
    n_pred: int = 0
    n_gold: int = 0

    @property
    def recall(self) -> float:
        return (self.tp / self.n_gold) if self.n_gold else 0.0

    @property
    def precision(self) -> float:
        return (self.tp / self.n_pred) if self.n_pred else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "n_pred": self.n_pred,
            "n_gold": self.n_gold,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "correct_over_total_pred": self.precision,
            "correct_over_total_gold": self.recall,
            "edges": [
                {
                    "pred_idx": e.pred_idx,
                    "gold_idx": e.gold_idx,
                    "pred_label": e.pred_label,
                    "gold_label": e.gold_label,
                    "score": e.score,
                }
                for e in self.edges
            ],
            "unmatched_pred": list(self.unmatched_pred),
            "unmatched_gold": list(self.unmatched_gold),
        }


def greedy_set_match(
    pred_labels: Sequence[str],
    gold_labels: Sequence[str],
    *,
    score_fn: MatchFn | None = None,
    threshold: float = DEFAULT_LEXICAL_THRESHOLD,
) -> SetMatchResult:
    """Greedy one-to-one: repeatedly take highest score ≥ threshold."""
    preds = [str(x).strip() for x in pred_labels if str(x).strip()]
    golds = [str(x).strip() for x in gold_labels if str(x).strip()]
    scorer = score_fn or leaf_match_score
    pairs: list[tuple[float, int, int]] = []
    for i, p in enumerate(preds):
        for j, g in enumerate(golds):
            s = float(scorer(p, g))
            if s >= threshold:
                pairs.append((s, i, j))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_p: set[int] = set()
    used_g: set[int] = set()
    edges: list[MatchEdge] = []
    for s, i, j in pairs:
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        edges.append(
            MatchEdge(
                pred_idx=i,
                gold_idx=j,
                pred_label=preds[i],
                gold_label=golds[j],
                score=s,
            )
        )
    return SetMatchResult(
        edges=edges,
        unmatched_pred=[i for i in range(len(preds)) if i not in used_p],
        unmatched_gold=[j for j in range(len(golds)) if j not in used_g],
        tp=len(edges),
        n_pred=len(preds),
        n_gold=len(golds),
    )


def micro_aggregate(results: Sequence[SetMatchResult]) -> dict[str, float]:
    tp = sum(r.tp for r in results)
    n_pred = sum(r.n_pred for r in results)
    n_gold = sum(r.n_gold for r in results)
    precision = (tp / n_pred) if n_pred else 0.0
    recall = (tp / n_gold) if n_gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "tp": float(tp),
        "total_pred": float(n_pred),
        "total_gold": float(n_gold),
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1,
        "correct_over_total_pred": precision,
        "correct_over_total_gold": recall,
    }


def labels_from_pred_ddx(pred_ddx: Sequence[Mapping[str, Any] | str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in pred_ddx:
        if isinstance(row, Mapping):
            lab = str(row.get("label") or row.get("leaf_label") or "").strip()
        else:
            lab = str(row).strip()
        if not lab:
            continue
        key = lab.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(lab)
    return out
