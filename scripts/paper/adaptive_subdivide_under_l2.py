#!/usr/bin/env python3
"""Offline AdaptiveSubdivideUnderL2: synthesize L3 children under coarse L2 leaves.

No tree store rewrite. Synthetic children replace the coarse parent in the
ranking; option_maps are remapped so each bound option points at its own L3.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping, Optional, Sequence

from adaptive_merge_siblings import _norm, labels_synonymish


def parse_options_from_case_text(case_text: str) -> dict[str, str]:
    """Parse 'Options:\\nA. ...\\nB. ...' blocks from DiagnosisArena vignettes."""
    text = case_text or ""
    if "\nOptions:" not in text and "\nOptions：" not in text:
        return {}
    block = text.split("\nOptions:", 1)[-1] if "\nOptions:" in text else text.split("\nOptions：", 1)[-1]
    out: dict[str, str] = {}
    for line in block.splitlines():
        m = re.match(r"^\s*([A-Da-d])[\.\:\)]\s*(.+?)\s*$", line.strip())
        if m:
            out[m.group(1).upper()] = m.group(2).strip()
    return out


def leaf_to_options(
    option_maps: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Map leaf_id -> sorted unique option letters that match it."""
    leaf_to_opts: dict[str, list[str]] = {}
    for opt_letter, mapped in (option_maps or {}).items():
        letter = str(opt_letter).upper()
        lids = list(
            mapped.get("matched_leaf_ids")
            or mapped.get("clone_leaf_ids")
            or ()
        )
        for lid in lids:
            s = str(lid)
            leaf_to_opts.setdefault(s, [])
            if letter not in leaf_to_opts[s]:
                leaf_to_opts[s].append(letter)
    for lid in leaf_to_opts:
        leaf_to_opts[lid] = sorted(set(leaf_to_opts[lid]))
    return leaf_to_opts


def options_are_clinically_distinct(
    letters: Sequence[str],
    options: Mapping[str, str],
) -> bool:
    """True if at least one bound pair is not synonymish (real split axis)."""
    texts = []
    for L in letters:
        t = str(options.get(L) or options.get(str(L).upper()) or "").strip()
        if t:
            texts.append(t)
    if len(texts) < 2:
        return False
    for i, a in enumerate(texts):
        for b in texts[i + 1 :]:
            if not labels_synonymish(a, b):
                return True
    return False


def detect_coarse_leaves(
    option_maps: Mapping[str, Any],
    *,
    require_gold_letter: Optional[str] = None,
    options: Optional[Mapping[str, str]] = None,
) -> list[str]:
    """Leaves matched by ≥2 options (optionally requiring gold letter among them)."""
    l2o = leaf_to_options(option_maps)
    gold = (require_gold_letter or "").upper() or None
    out: list[str] = []
    for lid, opts in l2o.items():
        if len(opts) < 2:
            continue
        if gold and gold not in opts:
            continue
        if options is not None and not options_are_clinically_distinct(opts, options):
            continue
        out.append(lid)
    return out


def detect_coarse_from_options_vs_labels(
    ranking_labels: Sequence[Mapping[str, Any]],
    options: Mapping[str, str],
    *,
    top_k: int = 5,
) -> list[tuple[str, list[str]]]:
    """Heuristic coarse without mapper: leaf label covers ≥2 distinct options."""
    hits: list[tuple[str, list[str]]] = []
    rows = list(ranking_labels)[: max(1, top_k)]
    for row in rows:
        lid = str(row.get("id") or "").strip()
        label = str(row.get("label") or "").strip()
        if not lid or not label:
            continue
        bound: list[str] = []
        for letter, text in options.items():
            if _option_covered_by_leaf(label, text):
                bound.append(str(letter).upper())
        bound = sorted(set(bound))
        if len(bound) >= 2 and options_are_clinically_distinct(bound, options):
            hits.append((lid, bound))
    return hits


def _option_covered_by_leaf(leaf_label: str, option_text: str) -> bool:
    """True if option looks like a specialization / synonym of the leaf."""
    nl, no = _norm(leaf_label), _norm(option_text)
    if not nl or not no:
        return False
    if labels_synonymish(leaf_label, option_text):
        return True
    # shared content words (≥2) with leaf being shorter / more general
    tl, to = set(nl.split()), set(no.split())
    inter = tl & to
    if len(inter) >= 2 and (nl in no or len(tl) <= len(to)):
        return True
    return False


def _vignette_overlap_score(
    label: str,
    vignette: str,
    *,
    parent_label: str = "",
) -> float:
    """Gold-blind specificity vs vignette; prefer tokens not in the coarse parent."""
    vt = set(_norm(vignette).split())
    lt = set(_norm(label).split())
    pt = set(_norm(parent_label).split()) if parent_label else set()
    if not lt:
        return 0.0
    stop = {
        "of", "the", "a", "an", "and", "or", "with", "without", "due", "to",
        "disease", "disorder", "syndrome", "malignant", "benign", "variant",
        "type", "induced", "associated", "melanoma", "carcinoma", "tumor",
        "tumour", "cancer", "infection",
    }
    lt = {t for t in lt if t not in stop and len(t) > 2}
    if not lt:
        return 0.0
    shared = lt & vt
    # Extra weight for tokens discriminative vs parent (subtype axes)
    novel = shared - pt
    return float(len(shared)) + 2.0 * float(len(novel)) + 0.01 * len(lt)


def synthesize_l3_children(
    parent_id: str,
    parent_label: str,
    bound_letters: Sequence[str],
    options: Mapping[str, str],
    *,
    axis_hint: str = "",
    vignette: str = "",
) -> list[dict[str, Any]]:
    """Create one synthetic L3 per bound option (rule-based; option text as label)."""
    children: list[dict[str, Any]] = []
    for letter in bound_letters:
        opt = str(options.get(letter) or options.get(letter.upper()) or "").strip()
        if not opt:
            opt = f"{parent_label} — option {letter}"
        label = opt
        if axis_hint and axis_hint.lower() not in label.lower():
            label = f"{opt} ({axis_hint})"
        children.append({
            "id": "",  # filled after vignette-aware sort
            "label": label,
            "parent": parent_id,
            "source_option": str(letter).upper(),
            "synthetic": True,
            "_score": _vignette_overlap_score(
                label, vignette, parent_label=parent_label
            ),
        })
    children.sort(
        key=lambda c: (-float(c.get("_score") or 0.0), str(c.get("source_option") or ""))
    )
    for i, kid in enumerate(children, start=1):
        kid["id"] = f"{parent_id}.L3{i}"
        kid.pop("_score", None)
    return children


def llm_refine_l3_labels(
    *,
    cache: Any,
    parent_label: str,
    options_bound: Mapping[str, str],
    vignette: str = "",
    dry_run: bool = False,
) -> Optional[dict[str, str]]:
    """Optional LLM pass: letter -> refined L3 label. Returns None on skip/fail."""
    if dry_run or cache is None or not options_bound:
        return None
    payload = {
        "parent_leaf": parent_label,
        "options": dict(options_bound),
        "instruction": (
            "Split the coarse parent into mutually exclusive clinical subtypes "
            "aligned 1:1 with the given options. Return JSON object mapping "
            "option letter to a short subtype label."
        ),
    }
    prompt = (
        "You refine hierarchical diagnosis leaves.\n"
        f"Vignette excerpt:\n{(vignette or '')[:1200]}\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Respond with ONLY a JSON object like {\"A\": \"...\", \"B\": \"...\"}."
    )
    try:
        raw = cache.complete(prompt, max_tokens=400)
    except Exception:
        return None
    text = str(raw or "").strip()
    if "```" in text:
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        obj = json.loads(text[start : end + 1])
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    out = {
        str(k).upper(): str(v).strip()
        for k, v in obj.items()
        if str(v).strip()
    }
    return out or None


def subdivide_ranking(
    ranking_labels: Sequence[Mapping[str, Any]],
    *,
    option_maps: Optional[Mapping[str, Any]] = None,
    options: Optional[Mapping[str, str]] = None,
    gold_letter: str = "",
    axis_hints: Optional[Mapping[str, str]] = None,
    cache: Any = None,
    vignette: str = "",
    dry_run: bool = True,
    top_k: int = 5,
) -> dict[str, Any]:
    """Replace coarse parents in ranking with synthetic L3 children; remap maps.

    Returns:
      ranking_labels, ordered_ids, option_maps (possibly remapped),
      subdivided_parents, children_by_parent, path_applied
    """
    options = dict(options or {})
    option_maps = dict(option_maps or {})
    axis_hints = dict(axis_hints or {})
    labels = [
        {
            "id": str(r.get("id") or "").strip(),
            "label": str(r.get("label") or "").strip(),
            "parent": str(r.get("parent") or "").strip(),
            "rank": int(r.get("rank") or 999),
            "synthetic": bool(r.get("synthetic")),
        }
        for r in ranking_labels
        if str(r.get("id") or "").strip()
    ]
    by_id = {r["id"]: r for r in labels}

    # Determine coarse parents + bound letters
    coarse_specs: list[tuple[str, list[str]]] = []
    if option_maps:
        l2o = leaf_to_options(option_maps)
        for lid in detect_coarse_leaves(
            option_maps, require_gold_letter=None, options=options or None
        ):
            # Prefer top-K parents
            if lid not in by_id:
                continue
            rank = by_id[lid]["rank"]
            if rank > top_k and lid not in {
                str(r["id"]) for r in labels[:top_k]
            }:
                # still allow if among top_k ids by position
                pos = next(
                    (i for i, r in enumerate(labels, start=1) if r["id"] == lid),
                    999,
                )
                if pos > top_k:
                    continue
            coarse_specs.append((lid, list(l2o.get(lid) or [])))
    if not coarse_specs and options:
        coarse_specs = detect_coarse_from_options_vs_labels(
            labels, options, top_k=top_k
        )

    if not coarse_specs:
        return {
            "ranking_labels": labels,
            "ordered_ids": [r["id"] for r in labels],
            "option_maps": option_maps,
            "subdivided_parents": [],
            "children_by_parent": {},
            "path_applied": False,
            "n_synthetic": 0,
        }

    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    letter_to_l3: dict[str, str] = {}
    new_rows: list[dict[str, Any]] = []
    subdivided: list[str] = []

    for row in labels:
        lid = row["id"]
        spec = next((s for s in coarse_specs if s[0] == lid), None)
        if spec is None:
            new_rows.append(row)
            continue
        parent_id, bound = spec
        bound = [b for b in bound if b in options or (option_maps and b in option_maps)]
        if len(bound) < 2:
            # fall back to all letters in options if maps empty of text
            if options:
                bound = sorted(options.keys())
            if len(bound) < 2:
                new_rows.append(row)
                continue
        opts_bound = {
            b: options.get(b)
            or options.get(b.upper())
            or (
                (option_maps.get(b) or {}).get("option_text")
                if option_maps
                else None
            )
            or b
            for b in bound
        }
        # fill missing option text from maps keys only
        opts_bound = {k: str(v or k) for k, v in opts_bound.items()}

        refined = llm_refine_l3_labels(
            cache=cache,
            parent_label=row["label"],
            options_bound=opts_bound,
            vignette=vignette,
            dry_run=dry_run,
        )
        kids = synthesize_l3_children(
            parent_id,
            row["label"],
            bound,
            opts_bound,
            axis_hint=axis_hints.get(parent_id, ""),
            vignette=vignette,
        )
        if refined:
            # Re-score after LLM labels, then re-id
            for kid in kids:
                letter = kid["source_option"]
                if letter in refined:
                    kid["label"] = refined[letter]
            kids.sort(
                key=lambda c: (
                    -_vignette_overlap_score(
                        str(c.get("label") or ""),
                        vignette,
                        parent_label=row["label"],
                    ),
                    str(c.get("source_option") or ""),
                )
            )
            for i, kid in enumerate(kids, start=1):
                kid["id"] = f"{parent_id}.L3{i}"
        children_by_parent[parent_id] = kids
        subdivided.append(parent_id)
        for kid in kids:
            letter_to_l3[kid["source_option"]] = kid["id"]
            new_rows.append({
                "id": kid["id"],
                "label": kid["label"],
                "parent": parent_id,
                "rank": 0,
                "synthetic": True,
                "source_option": kid["source_option"],
            })
        # Drop coarse parent from ranking once children exist (children carry maps).
        # Keeping it would dilute Top-K and can push gold L3 past @2.

    # re-number ranks
    for i, r in enumerate(new_rows, start=1):
        r["rank"] = i

    # Remap option_maps: options that were on subdivided parents → their L3
    new_maps: dict[str, Any] = {}
    if option_maps:
        for letter, mapped in option_maps.items():
            L = str(letter).upper()
            m = dict(mapped)
            lids = [
                str(x)
                for x in (
                    m.get("matched_leaf_ids") or m.get("clone_leaf_ids") or ()
                )
            ]
            if L in letter_to_l3 and any(x in children_by_parent for x in lids):
                # option was bound to a subdivided parent
                new_id = letter_to_l3[L]
                m["matched_leaf_ids"] = [new_id]
                m["clone_leaf_ids"] = [new_id]
                m["subdivided_from"] = lids
            elif L in letter_to_l3:
                # heuristic path: always remap letter if we created L3 for it
                parent_hit = any(
                    L == kid.get("source_option")
                    for kids in children_by_parent.values()
                    for kid in kids
                )
                if parent_hit:
                    new_id = letter_to_l3[L]
                    m["matched_leaf_ids"] = [new_id]
                    m["clone_leaf_ids"] = [new_id]
            new_maps[L] = m
    else:
        # synthesize minimal maps from letter_to_l3
        for letter, lid in letter_to_l3.items():
            new_maps[letter] = {
                "matched_leaf_ids": [lid],
                "clone_leaf_ids": [lid],
                "relation_type": "synthetic_l3",
            }

    return {
        "ranking_labels": new_rows,
        "ordered_ids": [r["id"] for r in new_rows],
        "option_maps": new_maps or option_maps,
        "subdivided_parents": subdivided,
        "children_by_parent": children_by_parent,
        "letter_to_l3": letter_to_l3,
        "path_applied": bool(subdivided),
        "n_synthetic": sum(len(v) for v in children_by_parent.values()),
    }


def apply_subdivide_to_mapper_row(
    mapper_row: Mapping[str, Any],
    sub_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a mapper-shaped dict with remapped option_maps for rematch."""
    proj = dict(mapper_row.get("projection") or {})
    new_maps = dict(sub_result.get("option_maps") or proj.get("option_maps") or {})
    # Ensure every original letter still present
    old_maps = proj.get("option_maps") or {}
    for letter, mapped in old_maps.items():
        L = str(letter).upper()
        if L not in new_maps:
            new_maps[L] = mapped
    return {
        **dict(mapper_row),
        "projection": {**proj, "option_maps": new_maps},
    }
