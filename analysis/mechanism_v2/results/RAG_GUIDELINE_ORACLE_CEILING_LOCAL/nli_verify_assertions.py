#!/usr/bin/env python3
"""F8: NLI entailment check on high-stakes guideline assertions.

Premise = assertion quote.  Hypothesis = a verbalization of the 7-tuple.
Only ``required_for`` / ``pathognomonic_for`` / ``sufficient_for`` / ``excludes``
are checked.  Non-entailment (neutral or contradiction) demotes or drops the
assertion the same way F7 does.  Results are cached under
``RAG_GUIDELINE_ORACLE_CEILING_LOCAL/nli_cache.json``.

If the MiniLM NLI model cannot be loaded, this module becomes a no-op and
logs once.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
CACHE_PATH = LEDGER / "nli_cache.json"
MODEL_ID = "cross-encoder/nli-MiniLM-L6-v2"
LOCAL_CANDIDATES = [
    Path("/data2/wanghongyi/models/nli-MiniLM-L6-v2"),
    Path("/data2/wanghongyi/models/cross-encoder-nli-MiniLM-L6-v2"),
]

HIGH_STAKES = {"required_for", "pathognomonic_for", "sufficient_for", "excludes"}

log = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None  # CrossEncoder | False (failed)
_cache: dict[str, str] | None = None
_skip_logged = False


def _cache_key(quote: str, subj: str, rel: str, pred: str) -> str:
    return json.dumps([quote, subj, rel, pred], ensure_ascii=False, sort_keys=True)


def _load_cache() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    if CACHE_PATH.exists():
        try:
            _cache = json.loads(CACHE_PATH.read_text("utf-8"))
        except Exception:
            _cache = {}
    else:
        _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def verbalize(a: dict) -> str:
    subj = (a.get("subject") or "").strip()
    pred = (a.get("predicate") or "").strip()
    rel = (a.get("relation") or "").strip().lower()
    pol = (a.get("polarity") or "asserted").strip().lower()
    if rel == "pathognomonic_for":
        hyp = f"{pred} is pathognomonic for {subj}"
    elif rel == "required_for":
        hyp = f"{pred} is required for the diagnosis of {subj}"
    elif rel == "sufficient_for":
        hyp = f"{pred} is sufficient for the diagnosis of {subj}"
    elif rel == "excludes":
        hyp = f"{pred} excludes {subj}"
    else:
        hyp = f"{pred} is a feature of {subj}"
    if pol == "negated":
        hyp = f"it is not the case that {hyp}"
    return hyp


def _get_model():
    """Lazy-load CrossEncoder; return False on permanent failure."""
    global _model, _skip_logged
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import CrossEncoder

            path = None
            for cand in LOCAL_CANDIDATES:
                if cand.exists():
                    path = str(cand)
                    break
            path = path or MODEL_ID
            _model = CrossEncoder(path)
            log.info("F8 NLI loaded from %s", path)
        except Exception as exc:  # noqa: BLE001 — graceful skip
            _model = False
            if not _skip_logged:
                log.warning("F8 NLI skipped (model unavailable): %s", exc)
                print(f"[F8] NLI skipped — model unavailable: {exc}", flush=True)
                _skip_logged = True
    return _model


def predict_label(premise: str, hypothesis: str) -> str:
    """Return 'entailment' | 'neutral' | 'contradiction' | 'skip'."""
    model = _get_model()
    if model is False:
        return "skip"
    # cross-encoder/nli-MiniLM-L6-v2: labels contradiction / entailment / neutral
    scores = model.predict([(premise, hypothesis)], apply_softmax=True)[0]
    labels = getattr(model, "labels", None) or ["contradiction", "entailment", "neutral"]
    # some ST versions expose .model.config.id2label
    if hasattr(model, "model") and hasattr(model.model, "config"):
        id2 = getattr(model.model.config, "id2label", None) or {}
        if id2:
            labels = [id2[i] for i in range(len(id2))]
    idx = int(scores.argmax())
    label = str(labels[idx]).lower()
    if "entail" in label:
        return "entailment"
    if "contradict" in label:
        return "contradiction"
    return "neutral"


def nli_check_one(a: dict) -> str:
    """Return cached or fresh NLI label for one assertion."""
    rel = (a.get("relation") or "").lower()
    if rel not in HIGH_STAKES:
        return "skip"
    quote = str(a.get("quote") or "").strip()
    if not quote:
        return "skip"
    subj = str(a.get("subject") or "")
    pred = str(a.get("predicate") or "")
    key = _cache_key(quote, subj, rel, pred)
    cache = _load_cache()
    if key in cache:
        return cache[key]
    hyp = verbalize(a)
    label = predict_label(quote, hyp)
    if label != "skip":
        with _lock:
            cache[key] = label
            _save_cache()
    return label


def nli_filter_assertions(assertions: list[dict]) -> list[dict]:
    """Demote/drop high-stakes assertions that are not entailed by their quote.

    - contradiction on pathognomonic/required/sufficient → demote to feature_of
      (or drop excludes)
    - neutral (not-entailment) → same demotion for pathognomonic/required/sufficient;
      drop excludes
    - entailment → keep
    - skip (no model / non-high-stakes) → keep unchanged
    """
    out: list[dict] = []
    for a in assertions:
        if not isinstance(a, dict):
            continue
        a = dict(a)
        rel = (a.get("relation") or "").lower()
        if rel not in HIGH_STAKES:
            out.append(a)
            continue
        label = nli_check_one(a)
        if label in ("entailment", "skip"):
            if label == "entailment":
                a["_nli"] = "entailment"
            out.append(a)
            continue
        # not-entailment
        a["_nli"] = label
        if rel == "excludes":
            a["_gate"] = ((a.get("_gate") + "+") if a.get("_gate") else "") + "F8_drop_excludes"
            continue  # drop
        a["relation"] = "feature_of"
        if (a.get("modality") or "").lower() == "obligatory":
            a["modality"] = "typical"
        a["_gate"] = ((a.get("_gate") + "+") if a.get("_gate") else "") + f"F8_demote_{label}"
        out.append(a)
    return out


def _self_test() -> None:
    # without model this must not crash
    a = {
        "subject": "Long QT Syndrome",
        "relation": "pathognomonic_for",
        "polarity": "asserted",
        "modality": "obligatory",
        "predicate": "prolonged QT interval",
        "quote": "a condition termed long QT syndrome",
    }
    out = nli_filter_assertions([a])
    assert len(out) == 1
    print("nli_verify self-test OK (model=",
          "loaded" if _get_model() is not False else "skipped", ")")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
