"""Structured age/sex → incidence PRIOR modifier.

Age and sex are EPIDEMIOLOGY, not findings: they belong in the pre-test
probability (prior), not the finding→LR (likelihood) path. Routing
"55-year-old man" through the LR cache produced spurious signals; this module
instead adjusts each branch's prior by a curated, bounded age/sex incidence
multiplier (``data/knowledge_raw/age_sex_incidence.json``) and renormalizes.

Design notes
------------
* Multipliers are RELATIVE weights (1.0 = neutral) seeded from standard
  epidemiology (SEER age-specific incidence, textbook onset distributions).
* A branch is matched to a specific-disease override first, else to a coarse
  category, by keyword substring on the (resolved) branch label. No match →
  neutral (multiplier 1.0), so coverage gaps never distort priors.
* Sex mismatch (e.g. prostate cancer in a female) yields a near-zero
  multiplier, which is clinically correct and a strong, safe signal.
* Strictly additive: when disabled or no age is parseable, priors are
  unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# Ordered (lo, hi, key) age bands, hi inclusive.
_BANDS: list[tuple[int, int, str]] = [
    (0, 1, "0-1"),
    (2, 12, "2-12"),
    (13, 18, "13-18"),
    (19, 40, "19-40"),
    (41, 60, "41-60"),
    (61, 200, "61-200"),
]

_AGE_RE = re.compile(
    r"\b(\d{1,3})[\s-]*(?:year|yr|y/o|yo)s?[\s-]*old\b"
    r"|\bage\s*[:=]?\s*(\d{1,3})\b",
    re.IGNORECASE,
)
_MONTH_RE = re.compile(r"\b(\d{1,2})[\s-]*month[\s-]*old\b", re.IGNORECASE)
_SEX_RE = re.compile(
    r"\b(?:(man|male|boy|gentleman|m)|(woman|female|girl|lady|f))\b",
    re.IGNORECASE,
)


def parse_age_sex(text: str) -> tuple[Optional[int], Optional[str]]:
    """Best-effort extraction of (age_years, sex) from free text.

    Months are floored to year 0 (infant) so the youngest band applies.
    Returns (None, None) components when not found.
    """
    age: Optional[int] = None
    sex: Optional[str] = None
    if not text:
        return None, None
    m = _AGE_RE.search(text)
    if m:
        val = m.group(1) or m.group(2)
        try:
            age = int(val)
        except (TypeError, ValueError):
            age = None
    if age is None and _MONTH_RE.search(text):
        age = 0
    sm = _SEX_RE.search(text)
    if sm:
        sex = "male" if sm.group(1) else "female"
    return age, sex


def _band_for(age: int) -> Optional[str]:
    for lo, hi, key in _BANDS:
        if lo <= age <= hi:
            return key
    return None


class PriorModifier:
    """Applies age/sex incidence multipliers to branch priors."""

    def __init__(self, clamp: tuple[float, float] = (0.05, 4.0)) -> None:
        self._categories: dict[str, dict] = {}
        self._diseases: dict[str, dict] = {}
        self._clamp = clamp
        self.loaded = False

    def load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._categories = data.get("categories", {}) or {}
        self._diseases = data.get("diseases", {}) or {}
        clamp = (data.get("metadata", {}) or {}).get("clamp")
        if isinstance(clamp, list) and len(clamp) == 2:
            self._clamp = (float(clamp[0]), float(clamp[1]))
        self.loaded = bool(self._categories or self._diseases)

    def _match_entry(self, label: str) -> Optional[dict]:
        """Specific-disease override first, then coarse category."""
        low = (label or "").lower()
        if not low:
            return None
        for entry in self._diseases.values():
            for kw in entry.get("keywords", []):
                if _kw_hit(kw, low):
                    return entry
        for entry in self._categories.values():
            for kw in entry.get("keywords", []):
                if _kw_hit(kw, low):
                    return entry
        return None

    def multiplier(self, label: str, age: Optional[int], sex: Optional[str]) -> float:
        """Combined age×sex multiplier for ``label`` (1.0 when no match/age)."""
        if age is None:
            mult = 1.0
        else:
            entry = self._match_entry(label)
            if entry is None:
                return 1.0
            band = _band_for(age)
            bands = entry.get("age_bands", {}) or {}
            mult = float(bands.get(band, 1.0)) if band else 1.0
            skew = entry.get("sex_skew", {}) or {}
            if sex and skew:
                mult *= float(skew.get(sex, 1.0))
        lo, hi = self._clamp
        return max(lo, min(hi, mult))

    def apply(
        self,
        branches: dict,
        age: Optional[int],
        sex: Optional[str],
    ) -> dict[str, dict]:
        """Multiply each branch's prior/posterior by its age/sex multiplier and
        renormalize so the total prior mass is preserved.

        Mutates ``branches`` in place (each value must have ``.label``,
        ``.prior``, ``.posterior``). Returns a per-branch trace for logging.
        """
        if not self.loaded or age is None or not branches:
            return {}
        trace: dict[str, dict] = {}
        total_before = sum(max(0.0, getattr(b, "prior", 0.0)) for b in branches.values())
        new_priors: dict[str, float] = {}
        for bid, b in branches.items():
            mult = self.multiplier(getattr(b, "label", ""), age, sex)
            new_priors[bid] = max(0.0, getattr(b, "prior", 0.0)) * mult
            if abs(mult - 1.0) > 1e-6:
                trace[bid] = {
                    "label": getattr(b, "label", ""),
                    "multiplier": round(mult, 3),
                    "prior_before": round(getattr(b, "prior", 0.0), 4),
                }
        total_after = sum(new_priors.values())
        if total_after <= 0:
            return {}
        scale = (total_before / total_after) if total_before > 0 else 1.0
        for bid, b in branches.items():
            adj = new_priors[bid] * scale
            b.prior = adj
            b.posterior = adj
            if bid in trace:
                trace[bid]["prior_after"] = round(adj, 4)
        return trace


# §21.13.4 Bug1 fix: a negation prefix immediately before a keyword reverses
# its clinical meaning (e.g. "Non-malignant Leukocytosis" must NOT hit the
# 'malignan' cancer keyword). Suppress the hit when one of these precedes it.
_NEG_PREFIX_RE = re.compile(r"\b(?:non|not|without|no|benign|reactive)[\s\-]*$", re.I)


def _kw_hit(keyword: str, text_low: str) -> bool:
    """Whole-token-ish substring match. Short keywords (<=4 chars, e.g. 'cml',
    'all', 'aml') must match as a standalone token to avoid false hits inside
    longer words.

    §21.13.4 Bug1: a hit is suppressed when a negation/benign prefix
    ("non-", "not", "without", "benign", "reactive") immediately precedes the
    keyword, so a benign/reactive process is not put on a malignancy curve.
    """
    kw = keyword.lower().strip()
    if not kw:
        return False

    def _negated_at(start: int) -> bool:
        return _NEG_PREFIX_RE.search(text_low[:start]) is not None

    if len(kw) <= 4 and " " not in kw:
        for m in re.finditer(rf"\b{re.escape(kw)}\b", text_low):
            if not _negated_at(m.start()):
                return True
        return False
    idx = text_low.find(kw)
    while idx != -1:
        if not _negated_at(idx):
            return True
        idx = text_low.find(kw, idx + 1)
    return False
