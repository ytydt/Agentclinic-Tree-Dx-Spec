"""Near-label dedupe helpers for APHHM-C shortlists and stance groups.

Looser than ConceptRegistry._same_as (exact/resolver only): uses substring and
token-Jaccard so parent/subtype and near-synonyms collapse before the selector
or group nomination sees them. Prefer the more specific / longer label.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, TypeVar

T = TypeVar("T")

_TOKEN = re.compile(r"[a-z0-9]+")


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall(_norm(s)))


def token_jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def near_labels(a: str, b: str, *, jaccard: float = 0.4) -> bool:
    """True if labels are exact-norm, substring, or token-near."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    if token_jaccard(a, b) >= jaccard:
        return True
    # shared informative stem (≥5 chars)
    stems_a = {t for t in _tokens(a) if len(t) >= 5}
    stems_b = {t for t in _tokens(b) if len(t) >= 5}
    if stems_a & stems_b and token_jaccard(a, b) >= 0.3:
        return True
    return False


def prefer_label(a: str, b: str) -> str:
    """Keep the more specific label (longer; prefer hyphenated/etiology frames)."""
    na, nb = _norm(a), _norm(b)
    if na in nb and na != nb:
        return b
    if nb in na and na != nb:
        return a
    score = lambda s: (len(_norm(s)), s.count("-"), s.count(" "))
    return a if score(a) >= score(b) else b


def dedupe_labels(
    labels: Sequence[str],
    *,
    jaccard: float = 0.4,
    protect: Optional[Iterable[str]] = None,
) -> list[str]:
    """Collapse near-duplicate labels left-to-right; keep preferred wording."""
    protect_n = {_norm(x) for x in (protect or []) if x}
    kept: list[str] = []
    for lab in labels:
        if not lab:
            continue
        merged = False
        for i, k in enumerate(kept):
            if near_labels(lab, k, jaccard=jaccard):
                # never drop a protected label
                if _norm(k) in protect_n and _norm(lab) not in protect_n:
                    pass
                elif _norm(lab) in protect_n and _norm(k) not in protect_n:
                    kept[i] = lab
                else:
                    kept[i] = prefer_label(k, lab)
                merged = True
                break
        if not merged:
            kept.append(lab)
    return kept


def dedupe_by_label(
    items: Sequence[T],
    label_of: Callable[[T], str],
    *,
    jaccard: float = 0.4,
) -> list[T]:
    """Collapse near-duplicate items; keep the preferred label's item."""
    kept: list[T] = []
    kept_labs: list[str] = []
    for item in items:
        lab = label_of(item)
        if not lab:
            continue
        merged = False
        for i, klab in enumerate(kept_labs):
            if near_labels(lab, klab, jaccard=jaccard):
                pref = prefer_label(klab, lab)
                if pref == lab:
                    kept[i] = item
                    kept_labs[i] = lab
                merged = True
                break
        if not merged:
            kept.append(item)
            kept_labs.append(lab)
    return kept


def dedupe_group_notes(
    groups: list[dict[str, Any]],
    *,
    jaccard: float = 0.4,
) -> list[dict[str, Any]]:
    """Within each stance group, collapse near-duplicate candidate notes."""
    out = []
    for g in groups:
        cands = list(g.get("candidates") or [])
        deduped = dedupe_by_label(
            cands, lambda c: str((c or {}).get("label") or ""), jaccard=jaccard
        )
        out.append({**g, "candidates": deduped})
    return out


def _span_set(note: Mapping[str, Any]) -> set[str]:
    spans = list(note.get("for") or note.get("support_spans") or [])
    return {_norm(str(s)) for s in spans if str(s or "").strip()}


def evidence_discriminability(note: Mapping[str, Any], others: Sequence[Mapping[str, Any]]) -> float:
    """1 - fraction of this note's for-spans that also appear on others."""
    mine = _span_set(note)
    if not mine:
        return 0.0
    shared = 0
    for s in mine:
        for o in others:
            if o is note:
                continue
            if s in _span_set(o):
                shared += 1
                break
    return 1.0 - shared / len(mine)


def x3_drop_near_siblings(
    labels: Sequence[str],
    gold: str,
    *,
    near_fn: Optional[Callable[[str, str], bool]] = None,
) -> list[str]:
    """Probe X3: drop near-gold non-gold siblings; always keep exact gold matches.

    ``near_fn(lab, gold)`` should be True for near-siblings. Defaults to ``near_labels``.
    """
    near = near_fn or (lambda a, b: near_labels(a, b))
    kept: list[str] = []
    for lab in labels:
        if not lab:
            continue
        if gold and _norm(lab) == _norm(gold):
            kept.append(lab)
            continue
        # exact/substring gold match kept (caller may use dc.match separately)
        if gold and (_norm(gold) in _norm(lab) or _norm(lab) in _norm(gold)):
            if len(_norm(lab)) >= 4 and len(_norm(gold)) >= 4:
                kept.append(lab)
                continue
        if gold and near(lab, gold):
            # drop near sibling that is not gold itself
            continue
        kept.append(lab)
    if gold and not any(_norm(x) == _norm(gold) or (_norm(gold) in _norm(x) or _norm(x) in _norm(gold)) for x in kept):
        # restore gold label if it was in the original list under near-match wording
        for lab in labels:
            if gold and near(lab, gold) and (
                _norm(lab) == _norm(gold) or _norm(gold) in _norm(lab) or _norm(lab) in _norm(gold)
            ):
                kept = [lab] + kept
                break
    return kept


def evidence_consistent_sibling_dedupe(
    notes: Sequence[Mapping[str, Any]],
    *,
    jaccard: float = 0.4,
    label_key: str = "label",
) -> list[dict[str, Any]]:
    """Production X3 approx (no gold): cluster near-labels; keep the member with
    highest evidence discriminability, then most for-spans, then longest label.

    Unlike ``dedupe_labels`` (prefer longer name), this keeps the candidate whose
    support spans are least shared with the rest of the shortlist.
    """
    items = [dict(n) for n in notes if str(n.get(label_key) or "").strip()]
    if not items:
        return []
    # Union-find style clusters
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if near_labels(str(items[i][label_key]), str(items[j][label_key]), jaccard=jaccard):
                union(i, j)
    clusters: dict[int, list[int]] = {}
    for i in range(len(items)):
        clusters.setdefault(find(i), []).append(i)

    kept: list[dict[str, Any]] = []
    for idxs in clusters.values():
        if len(idxs) == 1:
            kept.append(items[idxs[0]])
            continue
        # score each against all notes outside its own identity
        best = None
        best_key = None
        for i in idxs:
            others = [items[j] for j in range(len(items)) if j != i]
            disc = evidence_discriminability(items[i], others)
            n_for = len(_span_set(items[i]))
            key = (disc, n_for, len(_norm(str(items[i][label_key]))))
            if best_key is None or key > best_key:
                best_key = key
                best = items[i]
        if best is not None:
            kept.append(best)
    # preserve a stable order following first occurrence in input
    order = {_norm(str(n.get(label_key))): i for i, n in enumerate(items)}
    kept.sort(key=lambda n: order.get(_norm(str(n.get(label_key))), 10**9))
    return kept
