#!/usr/bin/env python3
"""C3 L1 axis transforms for AB01/AB02/AB03 (no per-case LLM axis selection).

Modes:
  adaptive   — no-op (M00 BranchCreator axis)
  fixed_icd  — pre-frozen ICD chapter / specialty families; leaf→family map
  random     — case-independent equal partition into K buckets (K from M00)
  flat       — single virtual L1; total candidate budget preserved upstream
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

ROOT = Path(__file__).resolve().parents[2]

# Pre-frozen ICD-10 chapter / specialty families (AB01). Order is stable.
FIXED_ICD_FAMILIES: list[dict[str, str]] = [
    {"id": "ICD_A", "label": "Infectious and parasitic diseases", "chapter": "A"},
    {"id": "ICD_C", "label": "Neoplasms", "chapter": "C"},
    {"id": "ICD_D", "label": "Blood and immune disorders", "chapter": "D"},
    {"id": "ICD_E", "label": "Endocrine, nutritional and metabolic", "chapter": "E"},
    {"id": "ICD_F", "label": "Mental and behavioral disorders", "chapter": "F"},
    {"id": "ICD_G", "label": "Nervous system disorders", "chapter": "G"},
    {"id": "ICD_H", "label": "Eye / ear disorders", "chapter": "H"},
    {"id": "ICD_I", "label": "Circulatory system diseases", "chapter": "I"},
    {"id": "ICD_J", "label": "Respiratory system diseases", "chapter": "J"},
    {"id": "ICD_K", "label": "Digestive system diseases", "chapter": "K"},
    {"id": "ICD_L", "label": "Skin and subcutaneous diseases", "chapter": "L"},
    {"id": "ICD_M", "label": "Musculoskeletal and connective tissue", "chapter": "M"},
    {"id": "ICD_N", "label": "Genitourinary system diseases", "chapter": "N"},
    {"id": "ICD_O", "label": "Pregnancy, childbirth and puerperium", "chapter": "O"},
    {"id": "ICD_P", "label": "Perinatal conditions", "chapter": "P"},
    {"id": "ICD_Q", "label": "Congenital malformations", "chapter": "Q"},
    {"id": "ICD_R", "label": "Symptoms / signs / abnormal findings", "chapter": "R"},
    {"id": "ICD_S", "label": "Injury, poisoning and external causes", "chapter": "S"},
    {"id": "ICD_Z", "label": "Factors influencing health status", "chapter": "Z"},
    {"id": "ICD_OTH", "label": "Other / unclassified specialty family", "chapter": "X"},
]

# Keyword fallback when Guideline ICD lookup misses (deterministic).
_KEYWORD_CHAPTER: list[tuple[str, str]] = [
    (r"infect|sepsis|bacter|viral|fungal|parasit|abscess|pneumonia|tubercul|hiv|hepatitis", "A"),
    (r"cancer|carcinoma|lymphoma|leukemia|sarcoma|melanoma|neoplasm|tumor|tumour|metast", "C"),
    (r"anemi|haemophil|hemophil|thrombocyt|neutropen|coagul|sickle", "D"),
    (r"diabet|thyroid|adrenal|cushing|addison|obesity|gout|porphyr|metabol", "E"),
    (r"depress|schizophren|bipolar|anxiety|psychos|autism|dementia", "F"),
    (r"epilep|stroke|parkinson|alzheimer|migraine|neuropath|myasthen|meningit|encephal", "G"),
    (r"glaucoma|cataract|retina|otitis|hearing|uveitis", "H"),
    (r"myocard|infarct|angina|heart failure|arrhythm|hypertens|vascul|aort|endocard|pericard", "I"),
    (r"asthma|copd|bronchit|emphysema|pleur|respirat|pulmonary", "J"),
    (r"colitis|crohn|cirrhos|pancreat|gastrit|ulcer|cholecyst|hepatit|bowel|ibd", "K"),
    (r"psoriasis|eczema|dermatit|cellulitis|urticaria|pemphig", "L"),
    (r"arthritis|lupus|myositis|osteopor|fracture|spondyl|rheumat", "M"),
    (r"nephrit|ckd|renal|prostat|cystitis|uti|kidney|glomerul", "N"),
    (r"pregnan|eclampsia|preeclamp|postpartum|obstetric", "O"),
    (r"congenital|malform|atresia|dysplasia", "Q"),
    (r"poison|overdose|trauma|burn|fracture|injury", "S"),
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _case_seed(case_id: str, seed_base: int = 20260728) -> int:
    digest = hashlib.sha256(str(case_id).encode("utf-8")).hexdigest()
    return int(seed_base) ^ int(digest[:8], 16)


@lru_cache(maxsize=1)
def _guideline_icd_index() -> dict[str, str]:
    """Map normalized disease name → ICD chapter letter."""
    out: dict[str, str] = {}
    for name in ("Guideline_common.json", "Guideline_rare.json"):
        path = ROOT / "data" / "knowledge_raw" / name
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(doc, dict):
            continue
        for disease, row in doc.items():
            if not isinstance(row, dict):
                continue
            code = str(row.get("icd_code") or "").strip().upper()
            if not code:
                continue
            letter = code[0]
            if letter.isalpha():
                out[_norm(str(disease))] = letter
    return out


def icd_chapter_for_label(label: str) -> str:
    key = _norm(label)
    hit = _guideline_icd_index().get(key)
    if hit:
        return hit
    # substring soft match against guideline keys (bounded)
    for gkey, letter in _guideline_icd_index().items():
        if len(gkey) >= 6 and (gkey in key or key in gkey):
            return letter
    for pattern, letter in _KEYWORD_CHAPTER:
        if re.search(pattern, key):
            return letter
    return "X"


def _chapter_to_family(chapter: str) -> dict[str, str]:
    ch = (chapter or "X").upper()[:1]
    for fam in FIXED_ICD_FAMILIES:
        if fam["chapter"] == ch:
            return fam
    # C/D neoplasm/blood split: codes starting with C → neoplasms; D often blood
    if ch == "C":
        return FIXED_ICD_FAMILIES[1]
    return FIXED_ICD_FAMILIES[-1]


def _l1_l2(branches: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    l1: list[dict] = []
    l2: list[dict] = []
    for row in branches.values():
        if not isinstance(row, dict):
            continue
        level = int(row.get("level") or 0)
        item = dict(row)
        if level == 1:
            l1.append(item)
        elif level == 2:
            l2.append(item)
    l1.sort(key=lambda r: str(r.get("id") or ""))
    l2.sort(key=lambda r: str(r.get("id") or ""))
    return l1, l2


def _make_l1(fid: str, label: str, prior: float = 0.0) -> dict[str, Any]:
    return {
        "id": fid,
        "label": label,
        "parent": "ROOT",
        "level": 1,
        "level_role": "family",
        "status": "live",
        "prior": float(prior),
        "posterior": float(prior),
        "danger": 0.0,
        "actionability": 0.0,
        "explanatory_coverage": 0.0,
        "expand_score": 0.0,
        "classification_axis": "fixed_specialty",
        "representative_diseases": [],
        "askable_discriminators": [],
        "requestable_discriminators": [],
        "evidence_for": [],
        "evidence_against": [],
        "unresolved_questions": [],
        "reopen_triggers": [],
        "children": [],
        "closure_reason": "",
        "diagnosis_commitment_gain": 0.0,
        "interrupt_relevance": 0.0,
        "turn_cost_to_refine": 1.0,
    }


def _renumber_l2(
    leaves: Sequence[Mapping[str, Any]],
    parent_id: str,
    start_index: int = 1,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, leaf in enumerate(leaves, start=start_index):
        row = dict(leaf)
        row["id"] = f"{parent_id}.{i}"
        row["parent"] = parent_id
        row["parent_id"] = parent_id
        row["level"] = 2
        row["status"] = row.get("status") or "live"
        out.append(row)
    return out


def _truncate_families(
    family_to_leaves: dict[str, list[dict[str, Any]]],
    family_meta: dict[str, dict[str, str]],
    *,
    max_l1: int,
    require_leaves: bool = True,
) -> list[str]:
    ranked = sorted(
        family_to_leaves.keys(),
        key=lambda fid: (-len(family_to_leaves[fid]), family_meta[fid]["label"]),
    )
    keep = ranked[: max(1, int(max_l1))]
    # spill truncated families into Other
    if len(ranked) > len(keep):
        other_id = "ICD_OTH"
        if other_id not in keep:
            if len(keep) >= int(max_l1):
                keep[-1] = other_id
            else:
                keep.append(other_id)
        for fid in ranked:
            if fid in keep and fid != other_id:
                continue
            family_to_leaves.setdefault(other_id, []).extend(family_to_leaves.get(fid, []))
            if fid != other_id:
                family_to_leaves.pop(fid, None)
        family_meta.setdefault(
            other_id,
            {"id": other_id, "label": "Other / unclassified specialty family", "chapter": "X"},
        )
    if require_leaves:
        return [fid for fid in keep if family_to_leaves.get(fid)]
    # keep_leaves=False path: empty families are intentional Config-A seeds
    return list(keep)


def apply_fixed_icd(
    branches: Mapping[str, Any],
    *,
    max_l1: int = 6,
    keep_leaves: bool = False,
) -> dict[str, Any]:
    _l1, l2 = _l1_l2(branches)
    family_to_leaves: dict[str, list[dict[str, Any]]] = {}
    family_meta: dict[str, dict[str, str]] = {
        f["id"]: f for f in FIXED_ICD_FAMILIES
    }
    if keep_leaves and l2:
        for leaf in l2:
            fam = _chapter_to_family(icd_chapter_for_label(str(leaf.get("label") or "")))
            family_to_leaves.setdefault(fam["id"], []).append(dict(leaf))
    else:
        # Seed empty families from a stable specialty shortlist (budget-truncated).
        # Config A will expand L2 under these parents.
        shortlist = [
            "ICD_A", "ICD_C", "ICD_I", "ICD_J", "ICD_K", "ICD_G",
            "ICD_E", "ICD_N", "ICD_M", "ICD_L",
        ][: max(1, int(max_l1))]
        for fid in shortlist:
            family_to_leaves[fid] = []
    keep = _truncate_families(
        family_to_leaves,
        family_meta,
        max_l1=max_l1,
        require_leaves=bool(keep_leaves),
    )
    n = max(1, len(keep))
    prior = 1.0 / n
    new_branches: dict[str, Any] = {}
    for fid in keep:
        meta = family_meta[fid]
        parent = _make_l1(fid, meta["label"], prior=prior)
        if keep_leaves:
            kids = _renumber_l2(family_to_leaves.get(fid) or [], fid)
            parent["children"] = [row["id"] for row in kids]
            new_branches[fid] = parent
            for row in kids:
                new_branches[row["id"]] = row
        else:
            new_branches[fid] = parent
    return new_branches


def apply_random(
    branches: Mapping[str, Any],
    *,
    case_id: str,
    max_l1: int = 6,
    keep_leaves: bool = False,
    seed_base: int = 20260728,
) -> dict[str, Any]:
    l1, l2 = _l1_l2(branches)
    k = min(max(1, len(l1) or int(max_l1)), int(max_l1))
    rng = random.Random(_case_seed(case_id, seed_base))
    if keep_leaves and l2:
        leaves = [dict(x) for x in l2]
        rng.shuffle(leaves)
        buckets: list[list[dict[str, Any]]] = [[] for _ in range(k)]
        for i, leaf in enumerate(leaves):
            buckets[i % k].append(leaf)
    else:
        buckets = [[] for _ in range(k)]
    prior = 1.0 / k
    new_branches: dict[str, Any] = {}
    for i in range(k):
        fid = f"R{i + 1}"
        parent = _make_l1(
            fid,
            f"Random partition family {i + 1}",
            prior=prior,
        )
        if keep_leaves:
            kids = _renumber_l2(buckets[i], fid)
            parent["children"] = [row["id"] for row in kids]
            new_branches[fid] = parent
            for row in kids:
                new_branches[row["id"]] = row
        else:
            new_branches[fid] = parent
    return new_branches


def apply_flat(
    branches: Mapping[str, Any],
    *,
    keep_leaves: bool = False,
) -> dict[str, Any]:
    _l1, l2 = _l1_l2(branches)
    parent = _make_l1("FLAT", "Flat candidate pool (no L1 hierarchy)", prior=1.0)
    new_branches: dict[str, Any] = {}
    if keep_leaves and l2:
        kids = _renumber_l2([dict(x) for x in l2], "FLAT")
        parent["children"] = [row["id"] for row in kids]
        new_branches["FLAT"] = parent
        for row in kids:
            new_branches[row["id"]] = row
    else:
        new_branches["FLAT"] = parent
    return new_branches


def transform_branches(
    branches: Mapping[str, Any],
    mode: str,
    *,
    case_id: str,
    max_l1: int = 6,
    keep_leaves: bool = False,
    seed_base: int = 20260728,
) -> dict[str, Any]:
    mode_n = (mode or "adaptive").strip().lower()
    if mode_n in {"", "adaptive", "m00", "default"}:
        return {k: dict(v) if isinstance(v, dict) else v for k, v in branches.items()}
    if mode_n in {"fixed_icd", "fixed", "icd"}:
        return apply_fixed_icd(branches, max_l1=max_l1, keep_leaves=keep_leaves)
    if mode_n in {"random", "rand"}:
        return apply_random(
            branches,
            case_id=case_id,
            max_l1=max_l1,
            keep_leaves=keep_leaves,
            seed_base=seed_base,
        )
    if mode_n in {"flat", "no_l1"}:
        return apply_flat(branches, keep_leaves=keep_leaves)
    raise ValueError(f"unknown l1_axis_mode: {mode}")


def apply_l1_axis_to_state(
    state: MutableMapping[str, Any],
    mode: str,
    *,
    case_id: str,
    max_l1: int = 6,
    keep_leaves: bool = False,
    seed_base: int = 20260728,
) -> dict[str, Any]:
    branches = state.get("branches") or {}
    if not isinstance(branches, dict):
        raise TypeError("state.branches must be a dict")
    new_br = transform_branches(
        branches,
        mode,
        case_id=case_id,
        max_l1=max_l1,
        keep_leaves=keep_leaves,
        seed_base=seed_base,
    )
    state = dict(state)
    state["branches"] = new_br
    l1_ids = [bid for bid, b in new_br.items() if int((b or {}).get("level") or 0) == 1]
    l2_ids = [bid for bid, b in new_br.items() if int((b or {}).get("level") or 0) == 2]
    state["frontier"] = l2_ids or l1_ids
    prov = dict(state.get("branch_provenance") or {})
    prov["c3_l1_axis"] = {
        "mode": (mode or "adaptive").strip().lower(),
        "case_id": str(case_id),
        "max_l1": int(max_l1),
        "keep_leaves": bool(keep_leaves),
        "n_l1": len(l1_ids),
        "n_l2": len(l2_ids),
        "seed_base": int(seed_base),
    }
    state["branch_provenance"] = prov
    return state


def apply_l1_axis_to_tree_doc(
    tree_doc: Mapping[str, Any],
    mode: str,
    *,
    case_id: str | None = None,
    max_l1: int = 6,
    keep_leaves: bool = False,
    seed_base: int = 20260728,
) -> dict[str, Any]:
    doc = dict(tree_doc)
    state = dict(doc.get("state") or {})
    cid = str(case_id or state.get("case_id") or "")
    doc["state"] = apply_l1_axis_to_state(
        state,
        mode,
        case_id=cid,
        max_l1=max_l1,
        keep_leaves=keep_leaves,
        seed_base=seed_base,
    )
    meta = dict(doc.get("c3_meta") or {})
    meta["l1_axis_mode"] = (mode or "adaptive").strip().lower()
    meta["keep_leaves"] = bool(keep_leaves)
    meta["max_l1"] = int(max_l1)
    doc["c3_meta"] = meta
    # Invalidate reuse fingerprint for transformed trees.
    if (mode or "adaptive").strip().lower() not in {"", "adaptive", "m00", "default"}:
        doc["run_fingerprint"] = f"c3_l1_axis:{meta['l1_axis_mode']}:{cid}"
    return doc


def rewrite_tree_dir(
    tree_dir: Path,
    mode: str,
    *,
    case_ids: Sequence[str] | None = None,
    max_l1: int = 6,
    keep_leaves: bool = False,
    seed_base: int = 20260728,
) -> dict[str, Any]:
    tree_dir = Path(tree_dir)
    ids = list(case_ids) if case_ids is not None else [
        p.stem for p in sorted(tree_dir.glob("*.json")) if p.stem != "summary"
    ]
    n_ok = 0
    for cid in ids:
        path = tree_dir / f"{cid}.json"
        if not path.is_file():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        out = apply_l1_axis_to_tree_doc(
            doc,
            mode,
            case_id=str(cid),
            max_l1=max_l1,
            keep_leaves=keep_leaves,
            seed_base=seed_base,
        )
        path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        n_ok += 1
    return {
        "tree_dir": str(tree_dir),
        "mode": mode,
        "n_rewritten": n_ok,
        "keep_leaves": bool(keep_leaves),
        "max_l1": int(max_l1),
    }


def equal_bucket_count(n_items: int, k: int) -> list[int]:
    """Helper for tests: sizes of equal-ish partition."""
    k = max(1, int(k))
    base, rem = divmod(max(0, int(n_items)), k)
    return [base + (1 if i < rem else 0) for i in range(k)]


def flat_l2_budget(*, fixed_l1_budget: int, per_family: int) -> int:
    """Preserve total leaf budget when collapsing to a single L1."""
    return max(1, int(fixed_l1_budget) * int(per_family))
