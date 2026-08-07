"""Offline mapper bind-repair + v2 leaf→parent protocol (L1 gold recall Track B).

Pure functions; no LLM. Does not mutate production mapper defaults.

Harness opt-in (default OFF elsewhere):
  - ``apply_synonym_bind_repair_to_mapper`` / ``rescore_after_synonym_bind``
    → Approach A empty-bind repair on ranking shortlist (mapper stage).
  - ``apply_leaf_inject_to_ranking`` → R2 full-tree leaf inject (annotate stage).
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# Default bridge KB for Approach A synonym bind (harness opt-in).
DEFAULT_BRIDGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "knowledge_raw"
    / "disease_name_bridge.json"
)
DEFAULT_SYNONYM_BIND_MIN_SCORE = 0.70

# Process-local cache: avoid re-parsing ~19MB disease_name_bridge per case.
_BRIDGE_CACHE: dict[str, Any] = {}


def _get_bridge(bridge_path: Any) -> Any:
    """Load SynonymGranularityRetriever once per absolute path (or None)."""
    if bridge_path is None:
        return None
    from pathlib import Path as _Path

    key = str(_Path(bridge_path).expanduser().resolve())
    if key in _BRIDGE_CACHE:
        return _BRIDGE_CACHE[key]
    try:
        from agentclinic_tree_dx.knowledge.synonym_granularity_retriever import (
            SynonymGranularityRetriever,
        )

        bridge = SynonymGranularityRetriever(_Path(key))
        bridge = bridge if bridge.is_ready else None
    except Exception:  # noqa: BLE001
        bridge = None
    _BRIDGE_CACHE[key] = bridge
    return bridge


# ---------------------------------------------------------------------------
# String similarity (aligned with audit_l1_rank_gap)
# ---------------------------------------------------------------------------


def norm_label(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return " ".join(s.split())


def labels_synonymish(a: str, b: str) -> bool:
    na, nb = norm_label(a), norm_label(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter >= max(2, min(len(ta), len(tb)) // 2)


def leaf_match_score(option_text: str, leaf_label: str) -> float:
    """Higher is better. 1.0 = exact norm; 0.85 = synonymish; 0 = no match."""
    na, nb = norm_label(option_text), norm_label(leaf_label)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    if labels_synonymish(option_text, leaf_label):
        ta, tb = set(na.split()), set(nb.split())
        inter = len(ta & tb)
        union = len(ta | tb) or 1
        return 0.7 + 0.2 * (inter / union)
    return 0.0


# ---------------------------------------------------------------------------
# Leaf collection
# ---------------------------------------------------------------------------


def _l1_ancestor(branch_id: str) -> str:
    return str(branch_id).split(".", 1)[0]


def leaves_from_ranking(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in (case.get("l2") or {}).get("final_ranking_labels") or ():
        lid = str(row.get("id") or "")
        if not lid:
            continue
        parent = str(row.get("parent") or "") or _l1_ancestor(lid)
        out.append({
            "leaf_id": lid,
            "leaf_label": str(row.get("label") or ""),
            "parent_id": parent,
            "parent_label": "",
            "source": "ranking",
        })
    return out


def leaves_from_tree_state(tree_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    branches = tree_state.get("branches") or {}
    if not isinstance(branches, Mapping):
        return []
    out: list[dict[str, Any]] = []
    for leaf_id, node in sorted(branches.items()):
        if not isinstance(node, Mapping):
            continue
        children = node.get("children")
        # Prefer explicit empty children; also treat as leaf if no other id is child
        has_kids = bool(children)
        if not has_kids:
            prefix = str(leaf_id) + "."
            has_kids = any(str(k).startswith(prefix) for k in branches)
        if has_kids:
            continue
        label = str(node.get("label") or node.get("name") or "").strip()
        if not label:
            continue
        parent_id = str(node.get("parent") or "") or _l1_ancestor(str(leaf_id))
        parent = branches.get(parent_id) or {}
        out.append({
            "leaf_id": str(leaf_id),
            "leaf_label": label,
            "parent_id": parent_id,
            "parent_label": str(
                parent.get("label") or parent.get("name") or ""
            ).strip(),
            "source": "tree",
        })
    return out


def collect_tree_leaves(
    case: Mapping[str, Any],
    tree_state: Optional[Mapping[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Prefer ranking rows; merge tree leaves so unbound gold leaves are visible."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in leaves_from_ranking(case):
        by_id[row["leaf_id"]] = row
    if tree_state:
        for row in leaves_from_tree_state(tree_state):
            existing = by_id.get(row["leaf_id"])
            if existing is None:
                by_id[row["leaf_id"]] = row
            else:
                # Fill missing parent/label from tree
                if not existing.get("parent_id"):
                    existing["parent_id"] = row["parent_id"]
                if not existing.get("leaf_label"):
                    existing["leaf_label"] = row["leaf_label"]
                if not existing.get("parent_label"):
                    existing["parent_label"] = row.get("parent_label") or ""
    return [by_id[k] for k in sorted(by_id)]


def find_matching_leaves(
    text: str,
    leaves: Sequence[Mapping[str, Any]],
    *,
    min_score: float = 0.7,
) -> list[tuple[float, dict[str, Any]]]:
    hits: list[tuple[float, dict[str, Any]]] = []
    for row in leaves:
        score = leaf_match_score(text, str(row.get("leaf_label") or ""))
        if score >= min_score:
            hits.append((score, dict(row)))
    hits.sort(key=lambda x: (-x[0], str(x[1].get("leaf_id") or "")))
    return hits


# ---------------------------------------------------------------------------
# R2: bind repair
# ---------------------------------------------------------------------------


def repair_option_map(
    om: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    option_text: str,
    *,
    min_score: float = 0.7,
) -> dict[str, Any]:
    """Return a repaired copy of one option_map row."""
    out = dict(om)
    existing = [
        str(x) for x in (out.get("matched_leaf_ids") or ()) if str(x).strip()
    ]
    if existing:
        out["matched_leaf_ids"] = existing
        out["matched"] = True
        out["bind_repair_applied"] = False
        out["bind_repair_rule"] = ""
        return out

    relation = str(out.get("relation_type") or "").lower()
    hits = find_matching_leaves(option_text, leaves, min_score=min_score)
    if not hits:
        out["matched_leaf_ids"] = []
        out["matched"] = bool(out.get("matched"))
        out["bind_repair_applied"] = False
        out["bind_repair_rule"] = ""
        return out

    best_ids = [str(h[1]["leaf_id"]) for h in hits if h[0] >= hits[0][0] - 1e-9]
    # Keep top-scoring group only (all tied with best)
    best_score = hits[0][0]
    best_ids = [str(h[1]["leaf_id"]) for h in hits if abs(h[0] - best_score) < 1e-9]

    if relation in {"equivalent", "related", "subtype_of", "supertype_of"}:
        rule = "bind_repair_equiv"
        new_relation = relation if relation != "unknown" else "related"
    else:
        # unrelated / unknown / empty — only bind near leaves
        rule = "bind_repair_near_leaf"
        new_relation = "related"

    out["matched_leaf_ids"] = sorted(set(best_ids))
    out["clone_leaf_ids"] = list(out.get("clone_leaf_ids") or ())
    out["matched"] = True
    out["relation_type"] = new_relation
    out["repair_override"] = {
        "prior_relation": relation,
        "best_score": best_score,
        "leaf_labels": [str(h[1].get("leaf_label") or "") for h in hits[:3]],
    }
    out["source"] = rule
    out["bind_repair_applied"] = True
    out["bind_repair_rule"] = rule
    return out


def apply_bind_repair_to_mapper(
    mapper_doc: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    *,
    min_score: float = 0.7,
    only_gold: bool = False,
    options: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Deep-copy mapper projection and repair option_maps (default: all options).

    ``options`` (letter→text) enables gold-blind repair for non-gold letters.
    """
    doc = copy.deepcopy(dict(mapper_doc))
    proj = dict(doc.get("projection") or {})
    maps = dict(proj.get("option_maps") or {})
    gold_letter = str(doc.get("gold_letter") or "").upper()
    opt_texts = {
        str(k).upper(): str(v)
        for k, v in (options or {}).items()
        if str(v).strip()
    }
    repaired_any = False
    n_repaired = 0
    for letter, row in list(maps.items()):
        L = str(letter).upper()
        if only_gold and L != gold_letter:
            continue
        option_text = opt_texts.get(L, "")
        if not option_text and L == gold_letter:
            option_text = str(
                doc.get("gold_option_text")
                or doc.get("gold_diagnosis")
                or ""
            )
        if not option_text:
            option_text = str(
                (row if isinstance(row, Mapping) else {}).get("option_text")
                or (row if isinstance(row, Mapping) else {}).get("label")
                or ""
            )
        new_row = repair_option_map(
            row if isinstance(row, Mapping) else {},
            leaves,
            option_text,
            min_score=min_score,
        )
        if new_row.get("bind_repair_applied"):
            repaired_any = True
            n_repaired += 1
        maps[L] = new_row
    proj["option_maps"] = maps
    doc["projection"] = proj
    doc["bind_repair_applied"] = repaired_any
    doc["n_options_bind_repaired"] = n_repaired
    return doc


def apply_synonym_bind_repair_to_mapper(
    mapper_doc: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    options: Mapping[str, str],
    *,
    min_score: float = 0.70,
    bridge_path: Optional[Any] = None,
) -> dict[str, Any]:
    """Gold-blind synonym/granularity bind-repair then ready for rematch.

    Uses lexical ``leaf_match_score`` plus optional disease_name_bridge boosts.
    Does **not** re-run typed LLM. Prefer ``leaves`` = compat ranking shortlist
    so repaired IDs keep ``joint_rank`` under rematch.
    """
    boosted_leaves = list(leaves)
    # Optional bridge boost (cached load; pair_match_score only — not RAG self-chunks).
    bridge = _get_bridge(bridge_path)

    def _boosted_find(text: str, leaf_rows: Sequence[Mapping[str, Any]], ms: float):
        """Score option↔leaf; bridge boost uses pair score only (not self-chunks).

        ``search_option_leaves`` returns syn:leaf/syn:option chunks at score=1.0
        whenever a surface resolves in the bridge. Taking hits[0] would bind
        every empty option to any known disease name (e.g. MVH→Kaposi). Use
        ``pair_match_score`` so only true synonym/granularity links boost.
        """
        hits: list[tuple[float, dict[str, Any]]] = []
        for row in leaf_rows:
            lab = str(row.get("leaf_label") or "")
            score = leaf_match_score(text, lab)
            if bridge is not None:
                try:
                    pair_score = float(bridge.pair_match_score(text, lab))
                except Exception:  # noqa: BLE001
                    pair_score = 0.0
                score = max(score, min(1.0, pair_score))
            if score >= ms:
                hits.append((score, dict(row)))
        hits.sort(key=lambda x: (-x[0], str(x[1].get("leaf_id") or "")))
        return hits

    doc = copy.deepcopy(dict(mapper_doc))
    proj = dict(doc.get("projection") or {})
    maps = dict(proj.get("option_maps") or {})
    opt_texts = {str(k).upper(): str(v) for k, v in options.items() if str(v).strip()}
    repaired_any = False
    n_repaired = 0
    for letter, row in list(maps.items()):
        L = str(letter).upper()
        option_text = opt_texts.get(L, "")
        if not option_text:
            continue
        out = dict(row) if isinstance(row, Mapping) else {}
        existing = [
            str(x) for x in (out.get("matched_leaf_ids") or ()) if str(x).strip()
        ]
        if existing:
            out["matched_leaf_ids"] = existing
            out["matched"] = True
            out["bind_repair_applied"] = False
            out["bind_repair_rule"] = ""
            maps[L] = out
            continue
        hits = _boosted_find(option_text, boosted_leaves, min_score)
        if not hits:
            out["bind_repair_applied"] = False
            out["bind_repair_rule"] = ""
            maps[L] = out
            continue
        best_score = hits[0][0]
        best_ids = [
            str(h[1]["leaf_id"]) for h in hits if abs(h[0] - best_score) < 1e-9
        ]
        relation = str(out.get("relation_type") or "").lower()
        if relation in {"equivalent", "related", "subtype_of", "supertype_of"}:
            rule = "synonym_bind_repair_equiv"
            new_relation = relation if relation != "unknown" else "related"
        else:
            rule = "synonym_bind_repair_near_leaf"
            new_relation = "related"
        out["matched_leaf_ids"] = sorted(set(best_ids))
        out["clone_leaf_ids"] = list(out.get("clone_leaf_ids") or ())
        out["matched"] = True
        out["relation_type"] = new_relation
        out["repair_override"] = {
            "prior_relation": relation,
            "best_score": best_score,
            "leaf_labels": [str(h[1].get("leaf_label") or "") for h in hits[:3]],
        }
        out["source"] = rule
        out["bind_repair_applied"] = True
        out["bind_repair_rule"] = rule
        maps[L] = out
        repaired_any = True
        n_repaired += 1
    proj["option_maps"] = maps
    doc["projection"] = proj
    doc["bind_repair_applied"] = repaired_any
    doc["n_options_bind_repaired"] = n_repaired
    doc["synonym_bind_repair"] = True
    return doc


def gold_option_text(case: Mapping[str, Any], mapper: Mapping[str, Any]) -> str:
    return " ".join(
        [
            str(mapper.get("gold_option_text") or ""),
            str(mapper.get("gold_diagnosis") or ""),
            str(case.get("gold") or ""),
        ]
    ).strip()


def gold_leaf_ids_from_mapper(mapper: Mapping[str, Any]) -> list[str]:
    letter = str(mapper.get("gold_letter") or "").upper()
    om = ((mapper.get("projection") or {}).get("option_maps") or {}).get(letter) or {}
    ids = list(om.get("matched_leaf_ids") or ()) + list(om.get("clone_leaf_ids") or ())
    return sorted({str(x) for x in ids if str(x).strip()})


# ---------------------------------------------------------------------------
# Acceptable parents: v1 / v2
# ---------------------------------------------------------------------------


def acceptable_parents_v1(
    case: Mapping[str, Any],
    mapper: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """v1_auto_parent with leaf parent lookup from full leaf catalogue."""
    by_id = {str(r.get("leaf_id")): r for r in leaves if r.get("leaf_id")}
    leaf_ids = gold_leaf_ids_from_mapper(mapper)
    parents: set[str] = set()
    sources: list[str] = []
    for lid in leaf_ids:
        row = by_id.get(lid)
        if row and row.get("parent_id"):
            parents.add(str(row["parent_id"]))
            sources.append("mapper_leaf_parent")
        else:
            # id-shaped fallback
            anc = _l1_ancestor(lid)
            if anc:
                parents.add(anc)
                sources.append("mapper_leaf_parent")
    if not parents:
        gold_text = gold_option_text(case, mapper)
        for row in (case.get("l1") or {}).get("l1_posteriors") or ():
            if labels_synonymish(str(row.get("label") or ""), gold_text):
                parents.add(str(row.get("id") or ""))
                sources.append("label_synonym")
    return {
        "acceptable_parent_ids": sorted(p for p in parents if p),
        "gold_leaf_ids": leaf_ids,
        "parent_source": ",".join(sorted(set(sources))) if sources else "none",
        "protocol": "v1_auto_parent",
    }


def acceptable_parents_v2(
    case: Mapping[str, Any],
    mapper: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    *,
    min_score: float = 0.7,
) -> dict[str, Any]:
    """v2_leaf_parent: gold text ↔ all tree leaves → L1 ancestors (ignores mapper bind)."""
    gold_text = gold_option_text(case, mapper)
    hits = find_matching_leaves(gold_text, leaves, min_score=min_score)
    parents: set[str] = set()
    matched_leaves: list[str] = []
    for _score, row in hits:
        lid = str(row.get("leaf_id") or "")
        matched_leaves.append(lid)
        pid = str(row.get("parent_id") or "") or _l1_ancestor(lid)
        if pid:
            parents.add(pid)
    sources = ["leaf_synonym"] if parents else []
    return {
        "acceptable_parent_ids": sorted(parents),
        "gold_leaf_ids": sorted(set(matched_leaves)),
        "parent_source": ",".join(sources) if sources else "none",
        "protocol": "v2_leaf_parent",
    }


def l1_ids_on_tree(
    case: Mapping[str, Any],
    tree_state: Optional[Mapping[str, Any]] = None,
) -> set[str]:
    ids: set[str] = set()
    for row in (case.get("l1") or {}).get("l1_posteriors") or ():
        if row.get("id"):
            ids.add(str(row["id"]))
    if tree_state:
        branches = tree_state.get("branches") or {}
        for bid in branches:
            if re.fullmatch(r"B\d+", str(bid)):
                ids.add(str(bid))
    return ids


def recall_funnel_bucket(
    *,
    auto_coverage: bool,
    tree_parent_present: bool,
    parent_in_l1_set: bool,
    parent_source: str,
) -> str:
    """MAPPER_UNBIND → TREE_PARENT_ABSENT → PARENT_NOT_IN_L1_SET → L1_PRESENT_OK."""
    if auto_coverage and parent_source != "none":
        return "L1_PRESENT_OK"
    if tree_parent_present and parent_in_l1_set and not auto_coverage:
        return "MAPPER_UNBIND"
    if not tree_parent_present:
        return "TREE_PARENT_ABSENT"
    if tree_parent_present and not parent_in_l1_set:
        return "PARENT_NOT_IN_L1_SET"
    if auto_coverage:
        return "L1_PRESENT_OK"
    return "MAPPER_UNBIND"


# ---------------------------------------------------------------------------
# Live upstream injection (标注前): full tree leaves + rescore
# ---------------------------------------------------------------------------


def _ranking_leaf_labels(
    ranking: Sequence[Mapping[str, Any]],
    tree_by_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    labels: list[str] = []
    for row in ranking:
        lid = str(row.get("id") or "")
        lab = str(row.get("label") or "")
        if not lab and lid and lid in tree_by_id:
            lab = str(tree_by_id[lid].get("leaf_label") or "")
        if lab:
            labels.append(lab)
    return labels


def _extra_match_score(
    leaf_label: str,
    *,
    option_texts: Sequence[str],
    ranking_labels: Sequence[str],
) -> float:
    """Gold-blind: max score vs all MCQ options, or synonymish vs ranking leaves."""
    best = 0.0
    for opt in option_texts:
        best = max(best, leaf_match_score(str(opt), leaf_label))
    for rlab in ranking_labels:
        if labels_synonymish(rlab, leaf_label):
            best = max(best, 0.70)
        best = max(best, leaf_match_score(rlab, leaf_label))
    return best


def build_injected_leaves(
    case: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    mode: str = "preserve_joint_then_posterior",
    options: Optional[Mapping[str, str]] = None,
    max_extra: int = 5,
    min_score: float = 0.70,
) -> list[dict[str, Any]]:
    """Build mapper leaf catalogue with joint_rank for live annotation rematch.

    Modes:
      - preserve_joint_then_posterior: keep final_ranking order (1..k), then
        append remaining tree leaves by descending posterior (k+1..).
      - posterior_only: rank all tree leaves by descending posterior.
      - restricted_option_synonym: keep ranking leaves, inject at most
        ``max_extra`` non-ranking tree leaves that match MCQ option text
        (or ranking leaf labels) with score >= ``min_score`` (gold-blind).
    """
    ranking = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    tree_leaves = leaves_from_tree_state(tree_state)
    # Prefer tree labels when IDs collide with ranking (ranking can drift).
    tree_by_id = {str(r["leaf_id"]): dict(r) for r in tree_leaves}
    ranked_ids: list[str] = []
    for row in ranking:
        lid = str(row.get("id") or "")
        if lid and lid not in ranked_ids:
            ranked_ids.append(lid)

    if mode == "posterior_only":
        ordered = sorted(
            tree_leaves,
            key=lambda r: (
                -float(
                    (tree_state.get("branches") or {})
                    .get(r["leaf_id"], {})
                    .get("posterior")
                    or 0.0
                ),
                str(r["leaf_id"]),
            ),
        )
        out: list[dict[str, Any]] = []
        for i, row in enumerate(ordered, start=1):
            item = dict(row)
            item["joint_rank"] = i
            item["posterior"] = float(
                (tree_state.get("branches") or {})
                .get(row["leaf_id"], {})
                .get("posterior")
                or 0.0
            )
            item["injected"] = True
            out.append(item)
        return out

    # shared: preserve ranking joint order first
    out = []
    seen: set[str] = set()
    for i, lid in enumerate(ranked_ids, start=1):
        base = tree_by_id.get(lid) or {
            "leaf_id": lid,
            "leaf_label": next(
                (str(r.get("label") or "") for r in ranking if str(r.get("id")) == lid),
                lid,
            ),
            "parent_id": next(
                (
                    str(r.get("parent") or "")
                    for r in ranking
                    if str(r.get("id")) == lid
                ),
                _l1_ancestor(lid),
            ),
            "parent_label": "",
            "source": "ranking",
        }
        item = dict(base)
        item["joint_rank"] = i
        item["posterior"] = float(
            (tree_state.get("branches") or {}).get(lid, {}).get("posterior") or 0.0
        )
        item["injected"] = False
        out.append(item)
        seen.add(lid)

    extras = [r for r in tree_leaves if str(r["leaf_id"]) not in seen]

    if mode == "restricted_option_synonym":
        option_texts = [str(v) for v in (options or {}).values() if str(v).strip()]
        rank_labs = _ranking_leaf_labels(ranking, tree_by_id)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in extras:
            lab = str(row.get("leaf_label") or "")
            sc = _extra_match_score(
                lab, option_texts=option_texts, ranking_labels=rank_labs
            )
            if sc + 1e-12 >= float(min_score):
                scored.append((sc, row))
        scored.sort(key=lambda t: (-t[0], str(t[1]["leaf_id"])))
        cap = max(0, int(max_extra))
        chosen = [row for _, row in scored[:cap]]
        base_rank = len(out)
        for j, row in enumerate(chosen, start=1):
            item = dict(row)
            item["joint_rank"] = base_rank + j
            item["posterior"] = float(
                (tree_state.get("branches") or {})
                .get(row["leaf_id"], {})
                .get("posterior")
                or 0.0
            )
            item["injected"] = True
            item["inject_score"] = _extra_match_score(
                str(row.get("leaf_label") or ""),
                option_texts=option_texts,
                ranking_labels=rank_labs,
            )
            out.append(item)
        return out

    # default: preserve joint then posterior (full-tree dump)
    extras.sort(
        key=lambda r: (
            -float(
                (tree_state.get("branches") or {})
                .get(r["leaf_id"], {})
                .get("posterior")
                or 0.0
            ),
            str(r["leaf_id"]),
        ),
    )
    base_rank = len(out)
    for j, row in enumerate(extras, start=1):
        item = dict(row)
        item["joint_rank"] = base_rank + j
        item["posterior"] = float(
            (tree_state.get("branches") or {})
            .get(row["leaf_id"], {})
            .get("posterior")
            or 0.0
        )
        item["injected"] = True
        out.append(item)
    return out


def injected_leaves_as_ranking_labels(
    leaves: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Convert injected leaf catalogue to downstream `final_ranking_labels` rows."""
    rows: list[dict[str, Any]] = []
    for leaf in leaves:
        lid = str(leaf.get("leaf_id") or "")
        if not lid:
            continue
        rows.append({
            "id": lid,
            "label": str(leaf.get("leaf_label") or ""),
            "parent": str(leaf.get("parent_id") or _l1_ancestor(lid)),
            "rank": int(leaf.get("joint_rank") or len(rows) + 1),
            "injected": bool(leaf.get("injected")),
            "posterior": float(leaf.get("posterior") or 0.0),
        })
    rows.sort(key=lambda r: int(r["rank"]))
    return rows


def apply_leaf_inject_to_ranking(
    case: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    ranking_ids: Sequence[str],
    *,
    mode: str = "preserve_joint_then_posterior",
    options: Optional[Mapping[str, str]] = None,
    max_extra: int = 5,
    min_score: float = 0.70,
) -> dict[str, Any]:
    """Harness hook: after compat/joint, expand ranking with tree leaves."""
    patched = {
        **dict(case),
        "l2": {
            **(case.get("l2") or {}),
            "final_ranking_labels": list(ranking_labels),
            "final_ranking_ids": list(ranking_ids),
        },
    }
    injected = build_injected_leaves(
        patched,
        tree_state,
        mode=mode,
        options=options,
        max_extra=max_extra,
        min_score=min_score,
    )
    new_labels = injected_leaves_as_ranking_labels(injected)
    new_ids = [str(r["id"]) for r in new_labels]
    return {
        "ranking_labels": new_labels,
        "ranking_ids": new_ids,
        "n_before": len(list(ranking_ids)),
        "n_after": len(new_ids),
        "n_injected_extra": sum(1 for r in injected if r.get("injected")),
        "inject_mode": mode,
    }


def rescore_projection_live(
    mapper_doc: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    options: Mapping[str, str],
    *,
    apply_repair: bool = True,
    min_score: float = 0.7,
) -> dict[str, Any]:
    """标注前动态注入后的正式重打分：可选 bind-repair → `_rank_and_expand`.

    Does not call LLM. Uses official projection maps as the starting typed
    relations, repairs empty binds against the (injected) leaf catalogue, then
    re-ranks options with the production ranking primitive.
    """
    # Local import keeps paper scripts usable without src on path until live.
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: WPS433
        _rank_and_expand,
    )

    doc = copy.deepcopy(dict(mapper_doc))
    proj = dict(doc.get("projection") or {})
    maps_in = dict(proj.get("option_maps") or {})
    leaf_ids = {str(r.get("leaf_id")) for r in leaves if r.get("leaf_id")}

    mappings: dict[str, dict[str, Any]] = {}
    n_repaired = 0
    for letter, text in sorted(options.items()):
        L = str(letter).upper()
        row = dict(maps_in.get(L) or {})
        if apply_repair:
            repaired = repair_option_map(
                row, leaves, str(text), min_score=min_score,
            )
            if repaired.get("bind_repair_applied"):
                n_repaired += 1
            row = repaired
        # Drop leaf ids not in injected catalogue
        matched = [
            str(x) for x in (row.get("matched_leaf_ids") or ())
            if str(x) in leaf_ids
        ]
        mappings[L] = {
            **row,
            "matched_leaf_ids": matched,
            "relation_type": row.get("relation_type") or "unknown",
        }

    clone_groups = [[str(r["leaf_id"])] for r in leaves if r.get("leaf_id")]
    option_maps, option_order = _rank_and_expand(
        mappings=mappings,
        leaves=leaves,
        clone_groups=clone_groups,
    )
    gold_letter = str(doc.get("gold_letter") or "").upper()
    gold = option_maps.get(gold_letter) or {}
    gold_rank = gold.get("best_rank")
    gold_option_rank = int(gold.get("option_rank") or (len(options) + 1))
    doc["projection"] = {
        **proj,
        "option_maps": option_maps,
        "option_order": option_order,
        "live_inject": True,
        "n_leaves_injected": len(leaves),
        "n_bind_repaired": n_repaired,
    }
    doc["gold_best_rank"] = gold_rank
    doc["gold_option_rank"] = gold_option_rank
    doc["option_top1"] = bool(gold_rank is not None and gold_option_rank <= 1)
    doc["option_top2"] = bool(gold_rank is not None and gold_option_rank <= 2)
    doc["option_rr"] = (1.0 / gold_option_rank) if gold_rank is not None else 0.0
    doc["bind_repair_applied"] = n_repaired > 0
    doc["live_n_repaired"] = n_repaired
    return doc


def rescore_after_synonym_bind(
    mapper_doc: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    options: Mapping[str, str],
    *,
    min_score: float = DEFAULT_SYNONYM_BIND_MIN_SCORE,
    bridge_path: Optional[Any] = None,
) -> dict[str, Any]:
    """Harness Approach A: synonym/bridge bind-repair → `_rank_and_expand`.

    Intended call site: mapper stage after typed ``projection`` is built.
    Does **not** re-run LLM. Prefer ``leaves`` = final ranking shortlist so
    repaired IDs keep ``joint_rank``. Production default remains off via CLI.
    """
    import sys

    root = Path(__file__).resolve().parents[2]
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: WPS433
        _rank_and_expand,
    )

    bridge = bridge_path if bridge_path is not None else DEFAULT_BRIDGE_PATH
    repaired = apply_synonym_bind_repair_to_mapper(
        mapper_doc,
        leaves,
        options,
        min_score=min_score,
        bridge_path=bridge,
    )
    proj = dict(repaired.get("projection") or {})
    maps_in = dict(proj.get("option_maps") or {})
    mappings: dict[str, dict[str, Any]] = {}
    for letter, text in sorted(
        {str(k).upper(): str(v) for k, v in options.items()}.items()
    ):
        row = dict(maps_in.get(letter) or {})
        expanded_ids = list(
            row.get("clone_leaf_ids") or row.get("matched_leaf_ids") or ()
        )
        mappings[letter] = {
            **row,
            "matched_leaf_ids": [str(x) for x in expanded_ids if str(x).strip()],
            "relation_type": row.get("relation_type") or "unknown",
        }
    # Include any option letters present in maps but missing from options text.
    for letter, row0 in maps_in.items():
        L = str(letter).upper()
        if L in mappings:
            continue
        row = dict(row0 or {})
        expanded_ids = list(
            row.get("clone_leaf_ids") or row.get("matched_leaf_ids") or ()
        )
        mappings[L] = {
            **row,
            "matched_leaf_ids": [str(x) for x in expanded_ids if str(x).strip()],
            "relation_type": row.get("relation_type") or "unknown",
        }

    leaf_rows = []
    for r in leaves:
        lid = str(r.get("leaf_id") or "")
        if not lid:
            continue
        leaf_rows.append({
            "leaf_id": lid,
            "leaf_label": str(r.get("leaf_label") or ""),
            "parent_id": str(r.get("parent_id") or ""),
            "parent_label": str(r.get("parent_label") or ""),
            "joint_rank": r.get("joint_rank"),
            "posterior": float(r.get("posterior") or 0.0),
        })
    clone_groups = [[str(r["leaf_id"])] for r in leaf_rows]
    option_maps, option_order = _rank_and_expand(
        mappings=mappings,
        leaves=leaf_rows,
        clone_groups=clone_groups,
    )
    gold_letter = str(repaired.get("gold_letter") or "").upper()
    gold = option_maps.get(gold_letter) or {}
    gold_rank = gold.get("best_rank")
    n_opts = max(len(options), len(option_maps), 1)
    gold_option_rank = int(gold.get("option_rank") or (n_opts + 1))
    doc = dict(repaired)
    doc["projection"] = {
        **proj,
        "option_maps": option_maps,
        "option_order": option_order,
        "synonym_bind_repair": True,
        "n_options_bind_repaired": int(repaired.get("n_options_bind_repaired") or 0),
    }
    doc["gold_best_rank"] = gold_rank
    doc["gold_option_rank"] = gold_option_rank
    doc["option_top1"] = bool(gold_rank is not None and gold_option_rank <= 1)
    doc["option_top2"] = bool(gold_rank is not None and gold_option_rank <= 2)
    doc["option_rr"] = (1.0 / gold_option_rank) if gold_rank is not None else 0.0
    doc["synonym_bind_repair"] = True
    return doc
