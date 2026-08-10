"""Shared extractors for Trajectory R3 (zero LLM)."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc
import trajectory_anatomy_lib as lib

ROOT = dc.ROOT
OUT_ROOT = ROOT / "analysis" / "backbone_v1"

SUBTYPE_RX = lib.SUBTYPE_RX
BROADER_RX = re.compile(
    r"\b(broader|more\s+general|umbrella|category|includes|encompass|"
    r"specific(?:ally)?|subtype|variant|narrower|less\s+specific|"
    r"not\s+commonly|more\s+characteristic)\b",
    re.I,
)
HISTO_RX = re.compile(
    r"\b(histolog|biopsy|immunohisto|patholog|microscop|stain|"
    r"epitheli|fronds?|keratin|atypia|mitotic)\b",
    re.I,
)
IMAGING_RX = re.compile(
    r"\b(MRI|CT|PET|ultrasound|echo|x-?ray|radiograph|imaging|"
    r"tomograph|angiograph)\b",
    re.I,
)
COURSE_RX = re.compile(
    r"\b(days?|weeks?|months?|years?|acute|chronic|progressive|"
    r"sudden|gradual|history)\b",
    re.I,
)


def token_jaccard(a: str, b: str) -> float:
    ta = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", a or "") if len(t) > 2}
    tb = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", b or "") if len(t) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def near_gold(label: str, gold: str) -> bool:
    """Near-miss: high lexical overlap / substring, but not a hard match."""
    if not label or not gold:
        return False
    if dc.match(label, gold):
        return False
    a, b = label.lower(), gold.lower()
    if a in b or b in a:
        return True
    if token_jaccard(label, gold) >= 0.4:
        return True
    # shared distinctive stem (≥5 chars) after dropping stopwords
    stop = {"with", "and", "the", "type", "due", "from", "of", "in"}
    ta = {t for t in re.findall(r"[A-Za-z0-9]+", a) if len(t) >= 5 and t not in stop}
    tb = {t for t in re.findall(r"[A-Za-z0-9]+", b) if len(t) >= 5 and t not in stop}
    return bool(ta & tb)


def cluster_of(label: str, gold: str) -> str:
    if not label:
        return "empty"
    if gold and dc.match(label, gold):
        return "gold"
    if gold and near_gold(label, gold):
        return "near"
    return "other"


def count_clusters(labels: list[str], gold: str) -> dict[str, int]:
    c = {"gold": 0, "near": 0, "other": 0, "empty": 0}
    for x in labels:
        c[cluster_of(x, gold)] = c.get(cluster_of(x, gold), 0) + 1
    return c


def load_loci_map() -> dict[tuple[str, str, str], dict[str, str]]:
    path = OUT_ROOT / "trajectory_loci" / "pooled.tsv"
    out: dict[tuple[str, str, str], dict[str, str]] = {}
    if not path.is_file():
        return out
    for row in csv.DictReader(path.open(encoding="utf-8")):
        key = (row["dataset"], row["slice"], row["case_id"])
        out[key] = row
    return out


def extract_backbone(run_dir: Path, cid: str) -> dict[str, Any]:
    doc = dc.load_backbone_stage(run_dir, cid)
    empty: dict[str, Any] = {
        "s2": [],
        "s3": [],
        "s3_why": [],
        "champion": "",
        "rejected": [],
        "rationale": "",
        "s2_rank_gold": None,
    }
    if not doc:
        return empty
    st = doc.get("stages") or {}
    s2 = [str(x) for x in ((st.get("s2") or {}).get("differentials") or [])]
    s3_raw = (st.get("s3") or {}).get("raw") or {}
    short = [str(x) for x in ((st.get("s3") or {}).get("shortlist") or [])]
    why = []
    for item in s3_raw.get("shortlist") or []:
        if isinstance(item, dict):
            why.append(
                {
                    "label": str(item.get("label") or ""),
                    "why_kept": str(item.get("why_kept") or ""),
                }
            )
    s4 = st.get("s4") or {}
    raw = s4.get("raw") if isinstance(s4.get("raw"), dict) else {}
    champ = str(s4.get("champion") or raw.get("champion") or doc.get("champion") or "")
    rejected = []
    for item in raw.get("rejected") or []:
        if isinstance(item, dict):
            rejected.append(
                {"label": str(item.get("label") or ""), "why": str(item.get("why") or "")}
            )
        else:
            rejected.append({"label": str(item), "why": ""})
    return {
        "s2": s2,
        "s3": short,
        "s3_why": why,
        "champion": champ,
        "rejected": rejected,
        "rationale": str(raw.get("rationale") or ""),
        "s2_rank_gold": None,  # filled by caller with gold
    }


def fill_s2_rank(bb: dict[str, Any], gold: str) -> None:
    if not gold:
        bb["s2_rank_gold"] = None
        return
    for i, d in enumerate(bb.get("s2") or [], 1):
        if dc.match(d, gold):
            bb["s2_rank_gold"] = i
            return
    bb["s2_rank_gold"] = None


def extract_b06(trace: Optional[dict], preds: list[str]) -> dict[str, Any]:
    tr = trace or {}
    disc_labels: list[str] = []
    for turn in tr.get("discussion") or []:
        if isinstance(turn, dict):
            disc_labels.extend(lib.extract_labels(turn.get("ranked_diagnoses") or []))
    sup = tr.get("supervisor") or {}
    top2 = lib.extract_labels(sup.get("top2_diagnoses") or preds)
    return {
        "discussion": disc_labels,
        "supervisor": top2,
        "votes": sup.get("votes") if isinstance(sup, dict) else None,
        "n_turns": len(tr.get("discussion") or []),
    }


def extract_b07(trace: Optional[dict], preds: list[str]) -> dict[str, Any]:
    tr = trace or {}
    draft = lib.extract_labels(tr.get("draft") or [])
    refine = tr.get("refine")
    refine_labels = lib.extract_labels(refine) if refine else []
    if not refine_labels and isinstance(refine, list):
        refine_labels = [str(x) for x in refine]
    diag = tr.get("diagnose") if isinstance(tr.get("diagnose"), dict) else {}
    diagnose = lib.extract_labels((diag or {}).get("top2_diagnoses") or preds)
    return {
        "draft": draft,
        "refine": refine_labels,
        "diagnose": diagnose,
        "has_refine": bool(refine),
        "queries": list((tr.get("queries") or [])[:8]),
    }


def extract_b01(trace: Optional[dict], preds: list[str]) -> dict[str, Any]:
    tr = trace or {}
    ret = tr.get("retrieval") or {}
    queries = list(ret.get("queries") or tr.get("queries") or [])[:8]
    top2 = lib.extract_labels(
        (tr.get("raw") or {}).get("top2_diagnoses")
        if isinstance(tr.get("raw"), dict)
        else None
    ) or list(preds)
    chunks = ret.get("served_chunks")
    n_chunks = chunks if isinstance(chunks, int) else (len(chunks) if chunks else 0)
    return {"queries": [str(q) for q in queries], "top2": top2, "n_chunks": n_chunks}


def extract_aphhm(annotate_dir: Path, cid: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "leaves": [],
        "final": [],
        "gold_leaf": "",
        "tree_n": 0,
        "final_n": 0,
    }
    cr = annotate_dir / "case_results" / f"{cid}.json"
    if not cr.is_file():
        return out
    doc = json.loads(cr.read_text())
    l2 = doc.get("l2") or {}
    final = [
        str(x.get("label") or "")
        for x in (l2.get("final_ranking_labels") or [])
        if isinstance(x, dict)
    ]
    out["final"] = final
    out["final_n"] = len(final)
    tree = annotate_dir / "shared_trees" / f"{cid}.json"
    leaves: list[str] = []
    if tree.is_file():
        state = json.loads(tree.read_text())
        br = state.get("branches") or (state.get("state") or {}).get("branches") or {}
        if isinstance(br, dict):
            br = list(br.values())
        leaves = [
            str(b.get("label") or "")
            for b in br
            if int(b.get("level") or 0) == 2 and b.get("label")
        ]
    out["leaves"] = leaves
    out["tree_n"] = len(leaves)
    am = l2.get("auto_metrics") or {}
    # try gold leaf from final ranking ids / acceptable
    for x in l2.get("final_ranking_labels") or []:
        if isinstance(x, dict) and x.get("id"):
            pass
    out["gold_leaf"] = str(am.get("unique_path_top1") or "")
    return out


_TRACE_CACHE: dict[str, dict[str, dict]] = {}
_PRED_CACHE: dict[str, dict[str, list]] = {}


def get_trace(run_dir: Path, cid: str) -> Optional[dict]:
    key = str(run_dir)
    if key not in _TRACE_CACHE:
        _TRACE_CACHE[key] = dc.load_traces(run_dir)
    return _TRACE_CACHE[key].get(cid)


def get_preds(run_dir: Path, cid: str) -> list[str]:
    key = str(run_dir)
    if key not in _PRED_CACHE:
        _PRED_CACHE[key] = dc.load_jsonl_preds(run_dir)
    raw = _PRED_CACHE[key]
    if cid in raw:
        return list(raw[cid])
    for k, v in raw.items():
        tail = k.split("__")[-1] if "__" in k else k
        try:
            if str(int(tail)) == cid:
                return list(v)
        except ValueError:
            if k.endswith(cid):
                return list(v)
    return []


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = {}
            for k, v in r.items():
                if isinstance(v, (list, dict)):
                    flat[k] = json.dumps(v, ensure_ascii=False)
                elif isinstance(v, bool):
                    flat[k] = int(v)
                else:
                    flat[k] = v
            w.writerow(flat)


def truthy(x: Any) -> bool:
    return str(x).lower() in ("1", "true", "yes")


def vignette_buckets(text: str) -> dict[str, Any]:
    words = max(len(text.split()), 1)
    return {
        "vig_histo_dens": 100 * len(HISTO_RX.findall(text)) / words,
        "vig_imaging_dens": 100 * len(IMAGING_RX.findall(text)) / words,
        "vig_course_dens": 100 * len(COURSE_RX.findall(text)) / words,
        "vig_histo_hits": len(HISTO_RX.findall(text)),
        "vig_imaging_hits": len(IMAGING_RX.findall(text)),
    }


def option_near_pairs(options: dict[str, str], gold: str) -> dict[str, Any]:
    labels = list(options.values())
    if len(labels) < 2:
        return {
            "n_option_near_pairs": 0,
            "max_distractor_gold_jaccard": 0.0,
            "champion_option_echo": None,
        }
    near_pairs = 0
    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            if dc.match(a, b) or near_gold(a, b) or token_jaccard(a, b) >= 0.4:
                near_pairs += 1
    distractors = [x for x in labels if not (gold and dc.match(x, gold))]
    max_dj = max((token_jaccard(x, gold) for x in distractors), default=0.0)
    return {
        "n_option_near_pairs": near_pairs,
        "max_distractor_gold_jaccard": round(max_dj, 3),
    }
