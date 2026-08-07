#!/usr/bin/env python3
"""Pre-compat joint middleware: schema, I/O, cache recovery, compat replay.

Artifact ``pre_compat_joint_v1`` stores the A3 joint-arbiter ranking *before*
``compat_parallel`` collapses it. Downstream ablations (AB07/AB10 on the
paper stored-compat config) must load this artifact — not ``final_ranking_*``
and not a posterior pool.

Recovery methods (priority):
  1. ``l2_llm_cache`` → ``ranked_candidate_ids`` aligned to ``gate.n_leaves``
  2. DA-style: when ``case_results`` has no granularity, treat stored
     ``final_ranking_*`` as already pre-compat (raw joint)
  3. Explicit empty joint (annotate had no arbiter ranking)

Label fill priority (historical fidelity):
  cache walk → post_compat survivors → current tree (last resort; ids may
  have been reused after writeback).

Never writes ``frozen/``. Default out dir: ``annotate/pre_compat_joint/``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = 1
ARTIFACT_NAME = "pre_compat_joint_v1"
DEFAULT_SUBDIR = "pre_compat_joint"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_annotate_dir(run_or_annotate: Path) -> Path:
    p = Path(run_or_annotate).expanduser().resolve()
    if (p / "annotate").is_dir():
        return p / "annotate"
    if (p / "case_results").is_dir() or (p / "shared_trees").is_dir():
        return p
    raise FileNotFoundError(f"cannot resolve annotate dir from {p}")


def labels_from_tree(
    tree_state: Mapping[str, Any],
    ranking_ids: Sequence[str],
) -> list[dict[str, Any]]:
    branches = tree_state.get("branches") or {}
    rows: list[dict[str, Any]] = []
    for i, lid in enumerate(ranking_ids, start=1):
        node = branches.get(str(lid)) or {}
        rows.append({
            "rank": i,
            "id": str(lid),
            "label": str(node.get("label") or ""),
            "parent": str(node.get("parent") or node.get("parent_id") or ""),
        })
    return rows


def load_tree_state(tree_path: Path) -> dict[str, Any]:
    doc = _read_json(tree_path)
    if isinstance(doc, Mapping):
        st = doc.get("state")
        if isinstance(st, Mapping):
            return dict(st)
        if "branches" in doc:
            return dict(doc)
    return {}


def _merge_label_meta(
    index: dict[str, dict[str, str]],
    bid: str,
    *,
    label: str = "",
    parent: str = "",
) -> None:
    bid = str(bid or "").strip()
    if not bid:
        return
    cur = index.setdefault(bid, {"label": "", "parent": ""})
    lab = str(label or "").strip()
    par = str(parent or "").strip()
    if lab and not cur["label"]:
        cur["label"] = lab
    if par and not cur["parent"]:
        cur["parent"] = par


def index_labels_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        _merge_label_meta(
            index,
            str(row.get("id") or ""),
            label=str(row.get("label") or row.get("name") or ""),
            parent=str(row.get("parent") or row.get("parent_id") or ""),
        )
    return index


def index_labels_from_cache(cache_doc: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Walk l2_llm_cache for ``{id, label}`` (and parent) branch-like objects.

    Needed when arbiter ranked a leaf later dropped from ``shared_trees``
    (cap/writeback); empty labels break ``fine_crowd_gate`` synonym clustering.
    """
    index: dict[str, dict[str, str]] = {}

    def walk(obj: Any) -> None:
        if isinstance(obj, Mapping):
            oid = obj.get("id")
            if oid is not None and (
                obj.get("label") is not None or obj.get("name") is not None
            ):
                _merge_label_meta(
                    index,
                    str(oid),
                    label=str(obj.get("label") or obj.get("name") or ""),
                    parent=str(obj.get("parent") or obj.get("parent_id") or ""),
                )
            for val in obj.values():
                walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(cache_doc or {})
    return index


def enrich_ranking_labels(
    ranking_ids: Sequence[str],
    *,
    tree_state: Optional[Mapping[str, Any]] = None,
    post_labels: Sequence[Mapping[str, Any]] = (),
    cache_doc: Optional[Mapping[str, Any]] = None,
    extra_index: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build ranking_labels for historical joint recovery.

    Priority (annotate-time fidelity): cache walk → post_compat → tree → extra.

    Current ``shared_trees`` may reuse leaf ids after writeback/cap with *new*
    diagnoses; tree-first fill breaks ``fine_crowd_gate`` synonym clustering.
    """
    sources: list[tuple[str, dict[str, dict[str, str]]]] = []
    if cache_doc is not None:
        sources.append(("cache_walk", index_labels_from_cache(cache_doc)))
    sources.append(("post_compat", index_labels_from_rows(post_labels)))
    sources.append(("tree", index_labels_from_rows(labels_from_tree(tree_state or {}, ranking_ids))))
    if extra_index:
        sources.append(("extra", {str(k): dict(v) for k, v in extra_index.items()}))

    fill_from = {name: 0 for name, _ in sources}
    fill_from["unfilled"] = 0
    rows: list[dict[str, Any]] = []

    for i, lid in enumerate(ranking_ids, start=1):
        bid = str(lid)
        label = ""
        parent = ""
        src_name = ""
        for name, src in sources:
            meta = src.get(bid) or {}
            lab = str(meta.get("label") or "").strip()
            if not lab:
                continue
            label = lab
            parent = str(meta.get("parent") or "").strip()
            src_name = name
            break
        if not parent:
            for _, src in sources:
                par = str((src.get(bid) or {}).get("parent") or "").strip()
                if par:
                    parent = par
                    break
        if src_name:
            fill_from[src_name] = int(fill_from[src_name]) + 1
        else:
            fill_from["unfilled"] = int(fill_from["unfilled"]) + 1
        rows.append({"rank": i, "id": bid, "label": label, "parent": parent})

    stats = {
        "n_ids": len(rows),
        "fill_from": fill_from,
        "n_empty_label": sum(1 for r in rows if not str(r.get("label") or "").strip()),
        "priority": [name for name, _ in sources],
    }
    return rows, stats

def extract_ranked_from_cache(cache_doc: Mapping[str, Any]) -> list[tuple[str, list[str]]]:
    """Return (cache_key, ranked_candidate_ids) for all arbiter-like entries."""
    out: list[tuple[str, list[str]]] = []
    for key, val in (cache_doc or {}).items():
        if not isinstance(val, Mapping):
            continue
        if "ranked_candidate_ids" in val:
            ids = [str(x) for x in (val.get("ranked_candidate_ids") or []) if str(x).strip()]
            out.append((str(key), ids))
            continue
        resp = val.get("response")
        if isinstance(resp, Mapping) and "ranked_candidate_ids" in resp:
            ids = [str(x) for x in (resp.get("ranked_candidate_ids") or []) if str(x).strip()]
            out.append((f"{key}.response", ids))
    return out


def select_pre_compat_ids(
    candidates: Sequence[tuple[str, list[str]]],
    *,
    n_leaves: Optional[int],
) -> tuple[list[str], dict[str, Any]]:
    """Pick one ranked list; prefer exact ``gate.n_leaves`` match."""
    meta: dict[str, Any] = {
        "n_arbiter_entries": len(candidates),
        "selected_by": None,
        "cache_key": None,
    }
    if not candidates:
        meta["selected_by"] = "empty"
        return [], meta
    if n_leaves is not None:
        matched = [(k, ids) for k, ids in candidates if len(ids) == int(n_leaves)]
        if len(matched) == 1:
            meta["selected_by"] = "gate.n_leaves_match"
            meta["cache_key"] = matched[0][0]
            return list(matched[0][1]), meta
        if len(matched) > 1:
            meta["selected_by"] = "gate.n_leaves_match_first"
            meta["cache_key"] = matched[0][0]
            meta["n_matched"] = len(matched)
            return list(matched[0][1]), meta
    if len(candidates) == 1:
        meta["selected_by"] = "single_entry"
        meta["cache_key"] = candidates[0][0]
        return list(candidates[0][1]), meta
    # fallback: longest non-empty
    best = max(candidates, key=lambda t: len(t[1]))
    meta["selected_by"] = "fallback_longest"
    meta["cache_key"] = best[0]
    return list(best[1]), meta


def build_artifact(
    *,
    case_id: str,
    source_annotate: str,
    pre_ids: Sequence[str],
    pre_labels: Sequence[Mapping[str, Any]],
    recovery: Mapping[str, Any],
    post_compat_ref: Optional[Mapping[str, Any]] = None,
    joint_arm: str = "A3-joint-primary",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": ARTIFACT_NAME,
        "case_id": str(case_id),
        "created_at": _utc(),
        "source_run": source_annotate,
        "joint_arm": joint_arm,
        "recovery": dict(recovery),
        "pre_compat": {
            "final_ranking_ids": [str(x) for x in pre_ids],
            "final_ranking_labels": [dict(r) for r in pre_labels],
            "n_leaves": len(pre_ids),
        },
        "post_compat_ref": dict(post_compat_ref or {}),
        "notes": (
            "Order is LLM joint-arbiter output at annotate time; "
            "not posterior sort. Use for AB07/AB10 on stored-compat config."
        ),
    }


def recover_case(
    annotate: Path,
    case_id: str,
) -> dict[str, Any]:
    """Recover one case's pre-compat joint artifact (does not write)."""
    cid = str(case_id)
    case_path = annotate / "case_results" / f"{cid}.json"
    tree_path = annotate / "shared_trees" / f"{cid}.json"
    cache_path = annotate / "cache" / cid / "l2_llm_cache.json"
    case = _read_json(case_path) if case_path.is_file() else {}
    l2 = (case.get("l2") or {}) if isinstance(case, Mapping) else {}
    gran = l2.get("granularity") or {}
    gate = gran.get("gate") or {}
    n_leaves = gate.get("n_leaves")
    post_ids = list(l2.get("final_ranking_ids") or [])
    post_labels = list(l2.get("final_ranking_labels") or [])
    joint_arm = str(l2.get("joint_arm") or "A3-joint-primary")
    post_ref = {
        "final_ranking_ids": post_ids,
        "final_ranking_labels": post_labels,
        "granularity_path": gran.get("path"),
        "compat_mode": gran.get("compat_mode") or gran.get("mode"),
        "gate": {
            "n_leaves": gate.get("n_leaves"),
            "triggered": gate.get("triggered"),
            "top1_id": gate.get("top1_id"),
            "top1_members": list(gate.get("top1_members") or ()),
        },
    }

    tree_state = load_tree_state(tree_path) if tree_path.is_file() else {}

    # Path A: no granularity → DA-style raw joint already in final_ranking
    if not gran.get("enabled") and not gran.get("compat_mode") and post_ids:
        # Heuristic: if granularity missing entirely
        if not gran:
            recovery = {
                "method": "case_results_raw_joint",
                "selected_by": "no_granularity_field",
                "n_arbiter_entries": 0,
            }
            labels, lab_stats = enrich_ranking_labels(
                post_ids,
                tree_state=tree_state,
                post_labels=post_labels,
            )
            recovery = {**recovery, "label_enrichment": lab_stats}
            return build_artifact(
                case_id=cid,
                source_annotate=str(annotate),
                pre_ids=post_ids,
                pre_labels=labels,
                recovery=recovery,
                post_compat_ref={
                    "final_ranking_ids": post_ids,
                    "note": "identical_to_pre_compat",
                },
                joint_arm=joint_arm,
            )

    # Path B: cache recovery
    if cache_path.is_file():
        cache = _read_json(cache_path)
        cache_map = cache if isinstance(cache, Mapping) else {}
        cands = extract_ranked_from_cache(cache_map)
        pre_ids, sel = select_pre_compat_ids(cands, n_leaves=n_leaves)
        # Empty joint is valid (cases 30/41)
        if not cands and int(n_leaves or 0) == 0 and not post_ids:
            recovery = {
                "method": "l2_llm_cache_ranked_candidate_ids",
                "selected_by": "empty_joint_consistent",
                "n_arbiter_entries": 0,
                "cache_path": str(cache_path),
            }
            return build_artifact(
                case_id=cid,
                source_annotate=str(annotate),
                pre_ids=[],
                pre_labels=[],
                recovery=recovery,
                post_compat_ref=post_ref,
                joint_arm=joint_arm,
            )
        if cands or pre_ids:
            labels, lab_stats = enrich_ranking_labels(
                pre_ids,
                tree_state=tree_state,
                post_labels=post_labels,
                cache_doc=cache_map,
            )
            recovery = {
                "method": "l2_llm_cache_ranked_candidate_ids",
                "cache_path": str(cache_path),
                "label_enrichment": lab_stats,
                **sel,
            }
            return build_artifact(
                case_id=cid,
                source_annotate=str(annotate),
                pre_ids=pre_ids,
                pre_labels=labels,
                recovery=recovery,
                post_compat_ref=post_ref,
                joint_arm=joint_arm,
            )

    # Path C: failed recovery
    recovery = {
        "method": "failed",
        "selected_by": "unrecoverable",
        "n_arbiter_entries": 0,
        "error": "no_cache_ranked_candidate_ids_and_not_raw_joint",
    }
    return build_artifact(
        case_id=cid,
        source_annotate=str(annotate),
        pre_ids=[],
        pre_labels=[],
        recovery=recovery,
        post_compat_ref=post_ref,
        joint_arm=joint_arm,
    )


def artifact_path(annotate: Path, case_id: str, subdir: str = DEFAULT_SUBDIR) -> Path:
    return Path(annotate) / subdir / f"{case_id}.json"


def save_artifact(annotate: Path, doc: Mapping[str, Any], subdir: str = DEFAULT_SUBDIR) -> Path:
    cid = str(doc.get("case_id") or "")
    path = artifact_path(annotate, cid, subdir=subdir)
    _write_json(path, doc)
    return path


def load_artifact(annotate: Path, case_id: str, subdir: str = DEFAULT_SUBDIR) -> dict[str, Any]:
    path = artifact_path(annotate, case_id, subdir=subdir)
    if not path.is_file():
        raise FileNotFoundError(path)
    return _read_json(path)


def pre_compat_ranking_labels(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    pre = artifact.get("pre_compat") or {}
    labels = list(pre.get("final_ranking_labels") or [])
    if labels:
        return [dict(r) for r in labels]
    ids = list(pre.get("final_ranking_ids") or [])
    return [{"rank": i, "id": str(x), "label": str(x), "parent": ""} for i, x in enumerate(ids, 1)]


def load_pre_compat_inputs(
    annotate: Path,
    case_id: str,
    *,
    subdir: str = DEFAULT_SUBDIR,
) -> Tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    """Public loader for AB07/AB10-style ablations on stored-compat config.

    Returns ``(ranking_ids, ranking_labels, artifact)``. Prefer this over
    ``case_results.l2.final_ranking_*`` (those are *post*-compat).
    """
    art = load_artifact(annotate, case_id, subdir=subdir)
    labels = pre_compat_ranking_labels(art)
    ids = [str(r.get("id")) for r in labels if r.get("id")]
    if not ids:
        ids = [str(x) for x in ((art.get("pre_compat") or {}).get("final_ranking_ids") or [])]
    return ids, labels, art


def replay_compat_parallel(
    artifact: Mapping[str, Any],
    *,
    case_doc: Optional[Mapping[str, Any]] = None,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    cache: Any = None,
    dry_run: bool = True,
    k: int = 5,
) -> dict[str, Any]:
    """Apply ``run_compat_parallel`` on recovered pre-compat list."""
    import merge_calib_compat as mcc

    labels = pre_compat_ranking_labels(artifact)
    case_for = {
        **dict(case_doc or {}),
        "l2": {
            **((case_doc or {}).get("l2") or {}),
            "final_ranking_labels": labels,
            "final_ranking_ids": [str(r.get("id")) for r in labels if r.get("id")],
        },
    }
    routed = mcc.run_compat_parallel(
        case=case_for,
        ranking_labels=labels,
        vignette=vignette,
        findings=list(findings),
        option_maps=None,
        gold_leaf_ids=[],
        cache=cache,
        dry_run=dry_run,
        k=k,
    )
    return routed


def verify_replay_against_stored(
    artifact: Mapping[str, Any],
    routed: Mapping[str, Any],
) -> dict[str, Any]:
    stored = list((artifact.get("post_compat_ref") or {}).get("final_ranking_ids") or [])
    replayed = [str(x) for x in (routed.get("ordered_ids") or [])]
    return {
        "stored": stored,
        "replayed": replayed,
        "exact_match": stored == replayed,
        "top1_match": (not stored and not replayed)
        or (bool(stored) and bool(replayed) and stored[0] == replayed[0]),
        "branch": routed.get("branch"),
        "stored_path": (artifact.get("post_compat_ref") or {}).get("granularity_path"),
    }
