"""
Evidence-based causal graph score.

Paper: https://arxiv.org/abs/2601.06636
§4.2.3 — S(d) = w_m N_match(d) − w_c N_conf(d) − w_s N_shadow(d)

Extra terms (w_support, w_ruleout, pivot bonus, generic downweight, Absent
as conflict, normalize) are [UNSPECIFIED] in the paper. They exist so the
open-diagnosis held-out can grid-search weights with no new LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from src.utils import normalize_diagnosis


class _Edge(Protocol):
    src: str
    dst: str
    relation: str


class _Graph(Protocol):
    edges: Iterable[_Edge]

    def nodes_touching_disease(self, disease: str) -> set[str]:
        ...


# Exact normalized k-node contents that are shared symptoms, not discriminators.
# From the no-leak held-out k-node frequency table (Fever 94, …).
GENERIC_KNODE_EXACT: frozenset[str] = frozenset(
    {
        "fever",
        "hypertension",
        "lymphadenopathy",
        "thrombocytopenia",
        "weight loss",
        "shortness of breath",
        "dyspnea",
        "elevated c-reactive protein",
        "elevated crp",
        "cough",
        "abdominal pain",
        "leukocytosis",
        "splenomegaly",
        "chest pain",
        "eosinophilia",
        "anemia",
        "pancytopenia",
        "fatigue",
        "malaise",
        "nausea",
        "vomiting",
        "headache",
        "edema",
        "tachycardia",
        "tachypnea",
        "hypoxia",
        "rash",
        "pruritus",
        "myalgia",
        "arthralgia",
        "night sweats",
        "chills",
    }
)


@dataclass
class RelationCounts:
    n_match: int = 0
    n_conf: int = 0
    n_shadow: int = 0
    n_support: int = 0
    n_ruleout: int = 0
    n_match_pivot: int = 0
    n_match_general: int = 0
    n_match_generic: int = 0
    n_match_absent: int = 0
    n_match_absent_pivot: int = 0
    n_k: int = 0
    n_pivot: int = 0


@dataclass
class ScoreWeights:
    """Paper terms plus held-out-tuned extras. Defaults = paper 1/1/1 only."""

    w_match: float = 1.0
    w_conflict: float = 1.0
    w_shadow: float = 1.0
    w_support: float = 0.0
    w_ruleout: float = 0.0
    w_pivot: float = 0.0
    generic_match_scale: float = 1.0
    absent_match_as_conflict: bool = False
    normalize: str = "none"  # none | n_k | n_scored
    disqualify_absent_pivot: bool = False
    override_margin: float = 0.0
    tie_break: str = "cot1"  # cot1 | name
    audit_mode: str = "llm"  # llm | argmax | cot_unless_margin


def is_generic_knode(content: str) -> bool:
    return normalize_diagnosis(content) in GENERIC_KNODE_EXACT


def _soft_overlap(a: str, b: str) -> bool:
    na, nb = normalize_diagnosis(a), normalize_diagnosis(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 6 and len(nb) >= 6 and (na in nb or nb in na):
        return True
    return False


def _iter_nodes_edges(graph: Any, disease: str) -> tuple[list[Any], list[Any], set[str] | None]:
    if isinstance(graph, Mapping):
        blob = graph.get(disease) if disease in graph else None
        if blob is None:
            key = normalize_diagnosis(disease)
            for name, value in graph.items():
                if normalize_diagnosis(str(name)) == key:
                    blob = value
                    break
        if not isinstance(blob, Mapping):
            return [], [], None
        return list(blob.get("nodes") or []), list(blob.get("edges") or []), None
    nodes = list(graph.nodes.values()) if hasattr(graph, "nodes") else []
    edges = list(graph.edges) if hasattr(graph, "edges") else []
    related = None
    if hasattr(graph, "nodes_touching_disease"):
        related = graph.nodes_touching_disease(disease)
    return nodes, edges, related


def count_relations_detailed(graph: Any, disease: str) -> RelationCounts:
    """Per-candidate edge/node features used by S(d) and the zero-call tuner."""
    nodes, edges, related = _iter_nodes_edges(graph, disease)
    by_id: dict[str, dict[str, str]] = {}
    absent: list[str] = []
    counts = RelationCounts()
    for node in nodes:
        if isinstance(node, Mapping):
            nid = str(node.get("id") or "")
            kind = str(node.get("kind") or "")
            content = str(node.get("content") or "")
            ktype = str(node.get("ktype") or "")
            status = str(node.get("status") or "")
        else:
            nid = str(getattr(node, "id", "") or "")
            kind = str(getattr(node, "kind", "") or "")
            content = str(getattr(node, "content", "") or "")
            ktype = str(getattr(node, "ktype", "") or "")
            status = str(getattr(node, "status", "") or "")
        if not nid:
            continue
        by_id[nid] = {"kind": kind, "content": content, "ktype": ktype, "status": status}
        if kind == "knowledge":
            counts.n_k += 1
            if ktype == "Pivot":
                counts.n_pivot += 1
        if kind == "patient" and status == "Absent" and content:
            absent.append(content)

    for edge in edges:
        if isinstance(edge, Mapping):
            src = str(edge.get("src") or "")
            dst = str(edge.get("dst") or "")
            relation = str(edge.get("relation") or "")
        else:
            src = str(getattr(edge, "src", "") or "")
            dst = str(getattr(edge, "dst", "") or "")
            relation = str(getattr(edge, "relation", "") or "")
        if related is not None and src not in related and dst not in related:
            continue
        if relation == "matching":
            counts.n_match += 1
            kn = None
            for nid in (src, dst):
                info = by_id.get(nid)
                if info and info["kind"] == "knowledge":
                    kn = info
                    break
            if kn:
                if kn["ktype"] == "Pivot":
                    counts.n_match_pivot += 1
                elif kn["ktype"] == "General":
                    counts.n_match_general += 1
                if is_generic_knode(kn["content"]):
                    counts.n_match_generic += 1
                if any(_soft_overlap(kn["content"], a) for a in absent):
                    counts.n_match_absent += 1
                    if kn["ktype"] == "Pivot":
                        counts.n_match_absent_pivot += 1
        elif relation == "conflict":
            counts.n_conf += 1
        elif relation == "penalty":
            counts.n_shadow += 1
        elif relation == "support":
            counts.n_support += 1
        elif relation == "rule out":
            counts.n_ruleout += 1
    return counts


def count_relations(graph: _Graph, disease: str) -> tuple[int, int, int]:
    """Count matching / conflict / penalty edges incident to candidate d.

    §4.2.3 — "Nmatch(d), Nconf(d), and Nshadow(d) count edges with matching,
    conflict, and penalty relations, respectively."
    """
    c = count_relations_detailed(graph, disease)
    return c.n_match, c.n_conf, c.n_shadow


def score_from_counts(counts: RelationCounts, weights: ScoreWeights) -> float:
    n_match = float(counts.n_match)
    n_conf = float(counts.n_conf)
    if weights.absent_match_as_conflict:
        n_match -= counts.n_match_absent
        n_conf += counts.n_match_absent
    n_match -= (1.0 - float(weights.generic_match_scale)) * counts.n_match_generic
    if weights.disqualify_absent_pivot and counts.n_match_absent_pivot > 0:
        return -1e9
    score = (
        weights.w_match * n_match
        - weights.w_conflict * n_conf
        - weights.w_shadow * counts.n_shadow
        + weights.w_support * counts.n_support
        - weights.w_ruleout * counts.n_ruleout
        + weights.w_pivot * counts.n_match_pivot
    )
    if weights.normalize == "n_k" and counts.n_k > 0:
        score /= float(counts.n_k)
    elif weights.normalize == "n_scored":
        denom = counts.n_match + counts.n_conf + counts.n_shadow
        score /= float(denom or 1)
    return float(score)


def evidence_score(
    graph: _Graph,
    disease: str,
    w_m: float = 1.0,
    w_c: float = 1.0,
    w_s: float = 1.0,
    weights: ScoreWeights | None = None,
) -> float:
    """§4.2.3 — S(d) = w_m N_match(d) − w_c N_conf(d) − w_s N_shadow(d).

    [UNSPECIFIED] w_m, w_c, w_s values; extra terms in ScoreWeights.
    """
    cfg = weights or ScoreWeights(w_match=w_m, w_conflict=w_c, w_shadow=w_s)
    return score_from_counts(count_relations_detailed(graph, disease), cfg)


def _score_of(scores: Mapping[str, float], name: str) -> float:
    if name in scores:
        return float(scores[name])
    key = normalize_diagnosis(name)
    for cand, value in scores.items():
        if normalize_diagnosis(cand) == key:
            return float(value)
    return float("-inf")


def pick_diagnosis(
    dset: list[str],
    scores: Mapping[str, float],
    *,
    cot1: str = "",
    override_margin: float = 0.0,
    tie_break: str = "cot1",
) -> str:
    """Deterministic audit: argmax S(d), keep CoT@1 unless margin is large enough.

    [UNSPECIFIED] paper uses an LLM judge (Table A9). This selector is the
    zero-call repair: the held-out autopsy showed the judge follows argmax S
    on override, and those overrides harmed MCR.
    """
    names = [str(n).strip() for n in dset if str(n).strip()]
    if not names:
        return ""
    cot = (cot1 or names[0]).strip() or names[0]

    def better(a: str, b: str) -> str:
        sa, sb = _score_of(scores, a), _score_of(scores, b)
        if sa > sb + 1e-12:
            return a
        if sb > sa + 1e-12:
            return b
        if tie_break == "cot1":
            if normalize_diagnosis(a) == normalize_diagnosis(cot):
                return a
            if normalize_diagnosis(b) == normalize_diagnosis(cot):
                return b
        return a if a <= b else b

    best = names[0]
    for name in names[1:]:
        best = better(best, name)
    if _score_of(scores, best) + 1e-12 < _score_of(scores, cot) + float(override_margin):
        return cot
    return best
