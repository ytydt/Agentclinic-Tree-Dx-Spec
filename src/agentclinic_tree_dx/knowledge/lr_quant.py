"""Qualitative→quantitative LR conversion for RAG-retrieved free text.

The unified LR cache already carries calibrated Sn / Sp / LR+ / LR- computed at
BUILD time from structured frequency tags (HPO / docLogica / Orphadata). That
conversion was never available at RETRIEVAL time, so cache-miss pairs only ever
produced ``LR+=None`` "context-only" snippets even when the snippet text clearly
states a frequency ("seen in ~80% of patients", "rarely associated with …").

This module ports the build-time calibration to retrieval time so RAG can emit a
numeric LR+ AND LR-.

Clinical-safety posture (per EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md B2.8 and
the 2026-05-27 safety review, which DEPRECATED a blanket "default frequency"
fallback as unsafe):
  - explicit numeric percentages are trusted most;
  - qualitative frequency adverbs map to a CONSERVATIVE Sn point estimate and are
    flagged ``confidence="rag_qualitative"`` so downstream Bayesian updating can
    attenuate them;
  - specificity is estimated from the finding's discriminating power, never
    fabricated as a fixed default that would inflate LR+.
"""

from __future__ import annotations

import re
from typing import Optional

# ── frequency-adverb → sensitivity point estimate ───────────────────────────
# Ordered most-specific phrase first. Values mirror the build-time frequency
# tables (HPO_FREQ_MAP / DOCLOGICA_FREQ_MAP / ORPHADATA_FREQ_MAP) collapsed to a
# single conservative scale.
_FREQ_PHRASES: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\b(?:pathognomonic|hallmark|invariabl(?:y|e)|in (?:virtually |almost )?all\b)", re.I), 0.95, "obligate"),
    (re.compile(r"\b(?:almost always|nearly always|characteristically|highly characteristic)\b", re.I), 0.90, "very_frequent"),
    (re.compile(r"\b(?:the majority of|most (?:patients|cases)|predominant(?:ly)?|usually|typically|commonly|frequently)\b", re.I), 0.70, "frequent"),
    (re.compile(r"\b(?:often|in many (?:patients|cases))\b", re.I), 0.60, "frequent_low"),
    (re.compile(r"\b(?:sometimes|may (?:be|occur|present)|can (?:be|occur)|occasionally|variably)\b", re.I), 0.30, "occasional"),
    (re.compile(r"\b(?:uncommon(?:ly)?|infrequent(?:ly)?|in a minority)\b", re.I), 0.12, "rare"),
    (re.compile(r"\b(?:rare(?:ly)?|seldom|unusual(?:ly)?)\b", re.I), 0.05, "very_rare"),
]

# explicit "in X%", "X% of patients", "up to X%", "(X-Y%)"
_PCT_RE = re.compile(r"(?:in|up to|approximately|~|about)?\s*(\d{1,3}(?:\.\d+)?)\s*%", re.I)
_PCT_RANGE_RE = re.compile(r"(\d{1,3})\s*[-–]\s*(\d{1,3})\s*%")

# §27.4 fix: the value group MUST be a well-formed number. The old `[\d.]+`
# greedily swallowed sentence punctuation — "the LR." → '.', "LR+ = 0.86." →
# '0.86.' — both of which crash float() (1119 failures / 503 case logs). Require
# at least one digit with an optional single decimal part.
_LR_RE = re.compile(r"(?:likelihood ratio|LR)\s*(\+|positive|-|negative)?\s*[:=]?\s*(\d+(?:\.\d+)?)", re.I)
# §13: the value group MUST be a well-formed number (same fix as _LR_RE). The
# old `[\d.]+` swallowed bare punctuation ("sensitivity of ." → '.'), crashing
# float() and — via the Annotator LR loop — dropping the whole turn's evidence.
_SN_RE = re.compile(r"sensitivit(?:y|ies)\s*(?:of|:|=|was|is)?\s*(\d+(?:\.\d+)?)\s*%?", re.I)
_SP_RE = re.compile(r"specificit(?:y|ies)\s*(?:of|:|=|was|is)?\s*(\d+(?:\.\d+)?)\s*%?", re.I)

# specificity heuristics (mirrors build_unified_cache.estimate_specificity)
_HIGH_SP_TERMS = {
    "basophilia", "auer rods", "philadelphia chromosome", "bcr-abl",
    "reed-sternberg", "kayser-fleischer", "necrolytic migratory erythema",
    "leukocyte alkaline phosphatase", "monoclonal", "schistocyte",
}
_LOW_SP_TERMS = {
    "fever", "pain", "fatigue", "headache", "nausea", "malaise", "weakness",
    "cough", "diarrhea", "vomiting", "weight loss", "anemia", "leukocytosis",
}
_DEFAULT_SP = 0.85


def estimate_specificity(finding: str) -> float:
    fl = (finding or "").lower()
    for t in _HIGH_SP_TERMS:
        if t in fl:
            return 0.95
    for t in _LOW_SP_TERMS:
        if t in fl:
            return 0.70
    return _DEFAULT_SP


# ── §26.5(1) LR detox: neutralise fabricated strong-exclusion entries ─────────
# Root cause (see §26.3): a low mention-frequency (Sn≈0.01 from "pct:1%") paired
# with the FABRICATED default specificity (0.85) manufactures LR+≈0.0667 — a 15×
# exclusion — for a NON-discriminative finding. The honest reading is "we don't
# know the LR", which must collapse toward neutral (1.0), never toward 0.
_DEMOGRAPHIC_RE = re.compile(
    r"(\b\d{1,3}\s*[- ]?year[s]?[- ]?old\b"          # "57-year-old"
    r"|^\s*age\b|^\s*age\s*(?:and|/|&)\s*gender\b|^\s*age/gender\b"
    r"|^\s*patient\s*(?:is|:)\b|^\s*gender\b|^\s*sex\b)",
    re.I,
)
_EXAM_NORMAL_RE = re.compile(
    r"(within normal limits|unremarkable|otherwise (?:healthy|well|normal)"
    r"|no (?:abnormalit|significant find)|physical (?:exam|appearance)[^a-z]*"
    r"(?:.*(?:normal|unremarkable|athletic|thin|well))?)",
    re.I,
)
# Clamp band: bound |LR| into [0.5, 2.0] (mild) when specificity was fabricated.
_DETOX_LR_LOW = 0.5
_DETOX_LR_HIGH = 2.0


def is_nondiscriminative_finding(finding: str) -> bool:
    """True for demographic / pure-normal-exam findings that should never carry
    a phenotypic LR (age, sex, "patient is a 57-year-old man", "within normal
    limits", "physical appearance: athletic young woman")."""
    f = (finding or "").strip()
    if not f:
        return True
    if _DEMOGRAPHIC_RE.search(f):
        return True
    # "physical exam: within normal limits" / "...unremarkable" style
    fl = f.lower()
    if ("physical exam" in fl or "physical appearance" in fl) and (
        "normal" in fl or "unremarkable" in fl or "athletic" in fl or "thin" in fl
    ):
        return True
    if "within normal limits" in fl or fl in ("unremarkable", "normal exam"):
        return True
    return False


def neutralize_entry(entry: Optional[dict]) -> Optional[dict]:
    """Return a detoxed copy of a secondary-cache LR entry (or None to DROP it).

    Policy (conservative, monotonic toward neutral — never invents support, and
    only SOFTENS manufactured exclusion):
      1. Demographic / normal-exam finding → DROP (return None): not a phenotype.
      2. Specificity was the FABRICATED default (0.85) AND the LR was derived
         single-sidedly (provenance ``pct:*`` / ``phrase:*``, NOT ``explicit:*``)
         → soften ONLY the EXCLUSION direction: raise ``lr_positive`` up to ≥0.5
         and cap ``lr_negative`` at ≤2.0. This targets the documented bug —
         a low mention-frequency (absence-of-mention misread as low sensitivity)
         paired with a guessed specificity manufacturing a strong rule-out. The
         SUPPORT direction (grounded in an actual high mention frequency) and all
         real Sn+Sp / explicit-LR / non-default-Sp entries are left untouched.
    """
    if not entry:
        return entry
    if is_nondiscriminative_finding(entry.get("finding", "")):
        return None

    prov = str(entry.get("provenance", ""))
    sp = entry.get("specificity")
    fabricated_sp = (sp is not None and abs(float(sp) - _DEFAULT_SP) < 1e-6
                     and not prov.startswith("explicit"))
    if not fabricated_sp:
        return entry

    out = dict(entry)
    changed = False
    lr_pos = out.get("lr_positive")
    if lr_pos is not None and float(lr_pos) < _DETOX_LR_LOW:
        out["lr_positive"] = _DETOX_LR_LOW
        changed = True
    lr_neg = out.get("lr_negative")
    if lr_neg is not None and float(lr_neg) > _DETOX_LR_HIGH:
        out["lr_negative"] = _DETOX_LR_HIGH
        changed = True
    if changed:
        out["confidence"] = "rag_qualitative"  # soften so updating attenuates it
        out["provenance"] = (prov + "+detox_clamped").lstrip("+")
    return out


def purify_entry(entry: Optional[dict]) -> Optional[dict]:
    """§27.6(1) — STRICTER than detox. Root cause (§27.5): 99.9% of the secondary
    cache is heuristic (only 0.13% explicit), and the ``pct`` channel grabs ANY
    percentage in the keyword-scoped snippet (often an unrelated mortality /
    prevalence / study-size figure), misreads it as the finding's sensitivity,
    and pairs it with the FABRICATED default Sp (0.85) → manufactured strong
    rule-outs (e.g. demographic ``age:57`` LR+=0.067). Detox only *softened* the
    exclusion direction, which perturbed a fragile balance and HURT (-13.3pp).

    Purify instead REMOVES the fabricated numeric signal entirely: an entry is
    kept as a numeric LR ONLY if it is genuinely grounded —
      • provenance ``explicit:*`` (reported Sn+Sp or LR in the text), OR
      • a non-default specificity (a real discriminating-power estimate).
    Otherwise the numeric LR is dropped (value→None = "remembered, no usable
    quantitative signal"); the snippet stays available as context-only. Also
    drops demographic / normal-exam findings outright (same as detox)."""
    if not entry:
        return entry
    if is_nondiscriminative_finding(entry.get("finding", "")):
        return None

    prov = str(entry.get("provenance", ""))
    sp = entry.get("specificity")
    grounded = prov.startswith("explicit") or (
        sp is not None and abs(float(sp) - _DEFAULT_SP) >= 1e-6
    )
    if grounded:
        return entry

    # Ungrounded heuristic LR (pct/phrase + fabricated default Sp): strip the
    # fabricated numbers, keep as context-only so it neither supports nor excludes.
    out = dict(entry)
    out["lr_positive"] = None
    out["lr_negative"] = None
    out["confidence"] = "context-only"
    out["provenance"] = (prov + "+purified_context").lstrip("+")
    return out


def compute_lr(sn: float, sp: float) -> tuple[Optional[float], Optional[float]]:
    """LR+ = Sn/(1-Sp), LR- = (1-Sn)/Sp. Returns (lr_pos, lr_neg)."""
    if sn is None or sp is None:
        return None, None
    sn = min(max(sn, 0.001), 0.999)
    sp = min(max(sp, 0.001), 0.999)
    lr_pos = round(sn / (1.0 - sp), 4)
    lr_neg = round((1.0 - sn) / sp, 4)
    return lr_pos, lr_neg


def _sensitivity_from_text(text: str, finding: str) -> tuple[Optional[float], str]:
    """Extract a sensitivity estimate from snippet text.

    Returns (sn, provenance). Numeric percentages win over adverbs. We only look
    at the sentence(s) that mention the finding (or its head noun) to avoid
    attributing an unrelated frequency to this finding.
    """
    fl = (finding or "").lower().strip()
    head = fl.split()[-1] if fl else ""
    # restrict to sentences mentioning the finding head noun when possible
    sentences = re.split(r"(?<=[.;])\s+", text)
    scope = [s for s in sentences if fl and (fl in s.lower() or (len(head) > 3 and head in s.lower()))]
    search_text = " ".join(scope) if scope else text

    rng = _PCT_RANGE_RE.search(search_text)
    if rng:
        lo, hi = float(rng.group(1)), float(rng.group(2))
        return (lo + hi) / 200.0, f"pct_range:{lo:.0f}-{hi:.0f}%"
    pct = _PCT_RE.search(search_text)
    if pct:
        v = float(pct.group(1))
        if 0 < v <= 100:
            return v / 100.0, f"pct:{v:.0f}%"
    for pat, sn, tag in _FREQ_PHRASES:
        if pat.search(search_text):
            return sn, f"phrase:{tag}"
    return None, ""


def quantify_snippet(
    text: str, finding: str, disease: str, *, article_id: str = "",
    title: str = "", score: float = 0.0,
) -> Optional[dict]:
    """Convert a single snippet to a numeric LR entry, or None.

    Tier A: explicit Sn/Sp or LR in text  → confidence ``rag_extracted``.
    Tier B: qualitative frequency adverb   → confidence ``rag_qualitative``.
    """
    if not text:
        return None

    sn_m = _SN_RE.search(text)
    sp_m = _SP_RE.search(text)
    lr_m = _LR_RE.search(text)

    sn = sp = lr_pos = lr_neg = None
    confidence = "rag_qualitative"
    provenance = ""

    # Tier A: explicit numerics (§13: coerce defensively — a malformed token
    # must degrade to "no value", never raise and drop the snippet).
    if sn_m:
        try:
            sn = float(sn_m.group(1))
            sn = sn / 100 if sn > 1 else sn
        except (TypeError, ValueError):
            sn = None
    if sp_m:
        try:
            sp = float(sp_m.group(1))
            sp = sp / 100 if sp > 1 else sp
        except (TypeError, ValueError):
            sp = None
    if sn is not None and sp is not None:
        lr_pos, lr_neg = compute_lr(sn, sp)
        confidence = "rag_extracted"
        provenance = "explicit:Sn+Sp"
    elif lr_m and lr_m.group(2):
        sign = (lr_m.group(1) or "").lower()
        try:
            val = float(lr_m.group(2))
        except (TypeError, ValueError):
            val = None  # §27.4: malformed numeric token → ignore, don't crash
        if val is not None:
            if sign in ("-", "negative"):
                lr_neg = round(val, 4)
            else:
                lr_pos = round(val, 4)
            confidence = "rag_extracted"
            provenance = "explicit:LR"

    # Tier B: qualitative frequency → Sn → LR (only if no explicit LR yet)
    if lr_pos is None and lr_neg is None:
        sn_q, prov = _sensitivity_from_text(text, finding)
        if sn_q is None:
            return None  # no usable quantitative signal → caller keeps context-only
        sn = sn_q
        sp = estimate_specificity(finding)
        lr_pos, lr_neg = compute_lr(sn, sp)
        confidence = "rag_extracted" if prov.startswith("pct") else "rag_qualitative"
        provenance = prov

    return {
        "finding": finding,
        "disease": disease,
        "sensitivity": round(sn, 4) if sn is not None else None,
        "specificity": round(sp, 4) if sp is not None else None,
        "lr_positive": lr_pos,
        "lr_negative": lr_neg,
        "source": f"RAG-quant:{article_id or 'corpus'}",
        "confidence": confidence,
        "provenance": provenance,
        "snippet_title": title,
        "snippet_score": score,
    }
