"""FindingNormalizer: map numeric lab descriptions to HPO phenotype terms.

Three-layer pipeline:
  Layer 1: Regex parsing to extract (test_name, value, unit)
  Layer 2: Structured lookup: alias → LOINC → reference range → direction → loinc2hpo → HPO
  Layer 3: RAG fallback (not implemented in this initial version)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_UNIT_CAPTURE = (
    r"[a-zA-Zμµ0-9/%°×^{}.]+"
    r"(?:/[a-zA-Zμµ0-9^{}.]+)*"
    r"(?:\s*(?:FEU|DDU))?"
)

PATTERNS = [
    re.compile(
        r"(?P<name>[A-Za-zβ][A-Za-z0-9β /\-]*?)\s*[:=]\s*"
        r"(?P<value>[\d,]+\.?\d*)\s*"
        rf"(?P<unit>{_UNIT_CAPTURE})?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<value>\d+\.?\d*)\s*%\s*"
        r"(?P<name>blasts?|basophils?|eosinophils?|neutrophils?|lymphocytes?|monocytes?|bands?|reticulocytes?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<name>[A-Za-zβ][A-Za-zβ \-]+?)\s+"
        r"(?:of|at|is|was|level)\s+"
        r"(?P<value>[\d,]+\.?\d*)\s*"
        rf"(?P<unit>{_UNIT_CAPTURE})?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:elevated|increased|high|low|decreased|reduced)\s+"
        r"(?P<name>[A-Za-z][A-Za-z \-]*?)\s*"
        r"\((?P<value>[\d,]+\.?\d*)\s*(?P<unit>[^\)]*?)?\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<name>[A-Za-zβ][A-Za-z0-9β /\-]*?)\s+"
        r"(?P<value>[\d,]+\.?\d*)\s*"
        rf"(?P<unit>{_UNIT_CAPTURE})",
        re.IGNORECASE,
    ),
]

_INLINE_REFERENCE_RE = re.compile(
    r"(?:reference\s*(?:range|interval|value|limit)?|"
    r"normal(?:\s*(?:range|value|limit))?|upper\s+limit\s+of\s+normal|uln)"
    r"\s*(?:is|of|:|=|,)?\s*"
    r"(?:"
    r"(?P<op><=?|>=?|≤|≥)\s*(?P<limit>-?[\d,]+(?:\.\d+)?)"
    r"|(?P<low>-?[\d,]+(?:\.\d+)?)\s*(?:-|–|—|to)\s*"
    r"(?P<high>-?[\d,]+(?:\.\d+)?)"
    r")\s*"
    rf"(?P<unit>{_UNIT_CAPTURE})?",
    re.IGNORECASE,
)

_SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

# Compound lab strings such as "Leukocyte count: 57,500/mm3 with 35% blasts"
# carry TWO independent findings. Split on connectors only when the segment to
# the right looks like another measurement (contains a digit), so prose like
# "weakness with burning pain" is NOT split.
_COMPOUND_SPLIT_RE = re.compile(
    r"\s+with\s+(?=[^,;]*\d)|;\s*|\s+and\s+(?=[^,;]*\d%)",
    re.IGNORECASE,
)

PERCENT_THRESHOLDS: dict[str, dict] = {
    "blasts": {"threshold_high": 5, "hpo_high": ("HP:0012234", "Elevated blast count")},
    "basophils": {"threshold_high": 2, "hpo_high": ("HP:0031807", "Basophilia")},
    "eosinophils": {"threshold_high": 5, "hpo_high": ("HP:0001880", "Eosinophilia")},
    "neutrophils": {
        "threshold_high": 70,
        "hpo_high": ("HP:0011897", "Neutrophilia"),
        "threshold_low": 40,
        "hpo_low": ("HP:0001875", "Neutropenia"),
    },
    "lymphocytes": {
        "threshold_high": 40,
        "hpo_high": ("HP:0001974", "Lymphocytosis"),
        "threshold_low": 20,
        "hpo_low": ("HP:0001888", "Lymphopenia"),
    },
    "monocytes": {"threshold_high": 8, "hpo_high": ("HP:0012311", "Monocytosis")},
    "reticulocytes": {"threshold_high": 2, "hpo_high": ("HP:0001923", "Reticulocytosis")},
}

# Vital signs are NOT covered by the LabQAR/loinc2hpo lab reference ranges
# (those are blood/chemistry assays only). Without these rules the embedding
# fallback mis-maps vitals (e.g. "Temperature 100°F" → "Cold skin temperature",
# "Pulse 120/min" → "Absent pulse"). Deterministic thresholds below.
VITAL_RULES: dict[str, dict] = {
    "temperature": {
        "names": ("temperature", "temp"),
        "high_f": 100.4, "low_f": 95.0,           # Fahrenheit thresholds
        "high_c": 38.0, "low_c": 35.0,            # Celsius thresholds
        "hpo_high": ("HP:0001945", "Fever"),
        "hpo_low": ("HP:0002045", "Hypothermia"),
    },
    "pulse": {
        "names": ("pulse", "heart rate", "hr"),
        "high": 100, "low": 60,
        "hpo_high": ("HP:0001649", "Tachycardia"),
        "hpo_low": ("HP:0001662", "Bradycardia"),
    },
    "respirations": {
        "names": ("respirations", "respiratory rate", "resp rate", "rr"),
        "high": 20, "low": 12,
        "hpo_high": ("HP:0002789", "Tachypnea"),
        "hpo_low": ("HP:0046507", "Bradypnea"),
    },
    "oxygen_saturation": {
        "names": ("oxygen saturation", "o2 saturation", "o2 sat", "spo2", "sao2"),
        "low": 92,
        "hpo_low": ("HP:0012418", "Hypoxemia"),
    },
}

_BP_RE = re.compile(
    r"(?:blood pressure|bp)?\s*[:=]?\s*(?P<sys>\d{2,3})\s*/\s*(?P<dia>\d{2,3})\s*(?:mm\s*hg)?",
    re.IGNORECASE,
)

_UNIT_NORMALIZE_MAP: dict[str, str] = {
    "u": "U",
    "iu": "U",
    "ul": "/μL",
    "µl": "/μL",
    "μl": "/μL",
    "/ul": "/μL",
    "/µl": "/μL",
    "/μl": "/μL",
    "/mcl": "/μL",
    "mcl": "/μL",
    "cells/ul": "/μL",
    "cells/µl": "/μL",
    "cells/μl": "/μL",
    "cells/mm3": "/μL",
    "/mm3": "/μL",
    "mm3": "/μL",
    "k/ul": "×10^3/μL",
    "k/μl": "×10^3/μL",
    "m/ul": "×10^6/μL",
    "m/μl": "×10^6/μL",
    "×10^9/l": "×10^9/L",
    "10^9/l": "×10^9/L",
    "×10^3/ul": "×10^3/μL",
    "×10^3/μl": "×10^3/μL",
    "×1000/ul": "×10^3/μL",
    "×1000/μl": "×10^3/μL",
    "10^3/ul": "×10^3/μL",
    "10^3/μl": "×10^3/μL",
    "×10^6/ul": "×10^6/μL",
    "×10^6/μl": "×10^6/μL",
    "×10^12/l": "×10^12/L",
    "g/dl": "g/dL",
    "mg/dl": "mg/dL",
    "meq/l": "mEq/L",
    "mmol/l": "mmol/L",
    "u/l": "U/L",
    "iu/l": "U/L",
    "u/ml": "U/mL",
    "iu/ml": "IU/mL",
    "ng/ml": "ng/mL",
    "ng/l": "ng/L",
    "pg/ml": "pg/mL",
    "miu/ml": "mIU/mL",
    "mu/ml": "mIU/mL",
    "kiu/l": "kIU/L",
    "μg/dl": "μg/dL",
    "µg/dl": "μg/dL",
    "ug/dl": "μg/dL",
    "mcg/dl": "μg/dL",
    "ng/dl": "ng/dL",
    "μg/l": "μg/L",
    "µg/l": "μg/L",
    "ug/l": "μg/L",
    "μmol/l": "μmol/L",
    "µmol/l": "μmol/L",
    "umol/l": "μmol/L",
    "nmol/l": "nmol/L",
    "pmol/l": "pmol/L",
    "mm/hr": "mm/hr",
    "mm/h": "mm/hr",
    "sec": "seconds",
    "secs": "seconds",
    "s": "seconds",
    "seconds": "seconds",
    "fl": "fL",
    "pg": "pg",
    "%": "%",
    "miu/l": "mIU/L",
    "uiu/ml": "mIU/L",
    "μiu/ml": "mIU/L",
    "mosm/kg": "mOsm/kg",
    "ml/min/1.73m2": "mL/min/1.73m2",
    "μg/ml": "μg/mL",
    "µg/ml": "μg/mL",
    "ug/ml": "μg/mL",
    "mg/l": "mg/L",
    "g/l": "g/L",
    "mg/24h": "mg/24h",
    "g/24h": "g/24h",
    "mmhg": "mmHg",
    "kpa": "kPa",
    "mosm/kgh2o": "mOsm/kg",
    "mosmol/kgh2o": "mOsm/kg",
    "{ph}": "{pH}",
    "{ratio}": "{ratio}",
}

_TEST_GROUP_MAP: dict[str, str] = {
    "Glucose_fasting": "Glucose",
    "Total_bilirubin": "Bilirubin",
    "Direct_bilirubin": "Bilirubin",
    "Indirect_bilirubin": "Bilirubin",
    "Total_cholesterol": "Cholesterol",
    "LDL": "Cholesterol",
    "HDL": "Cholesterol",
    "Cortisol_AM": "Cortisol",
    "Uric_acid": "Uric_acid",
    "Neutrophils_abs": "WBC",
    "Lymphocytes_abs": "WBC",
    "Monocytes_abs": "WBC",
    "Eosinophils_abs": "WBC",
    "Basophils_abs": "WBC",
    "Immunoglobulin_IgA": "Immunoglobulin",
    "Immunoglobulin_IgE": "Immunoglobulin",
    "Immunoglobulin_IgG": "Immunoglobulin",
    "Immunoglobulin_IgM": "Immunoglobulin",
    "Arterial_PCO2": "Blood_gas_pressure",
    "Arterial_PO2": "Blood_gas_pressure",
    "Troponin_I": "Troponin",
    "Troponin_T": "Troponin",
    "Troponin_I_hs": "Troponin_hs",
    "Troponin_T_hs": "Troponin_hs",
    "NT_proBNP": "BNP",
    "Complement_C3": "Complement",
    "Complement_C4": "Complement",
    "CA_125": "CA_marker",
    "CA_19_9": "CA_marker",
}


@dataclass
class LabParsed:
    test_name: str
    value: float
    unit: str
    original: str


@dataclass
class NormalizedFinding:
    original: str
    hpo_term: str | None
    hpo_id: str | None
    direction: str
    confidence: str
    source: str
    test_name: str | None = None
    value: float | None = None
    unit: str | None = None
    narrative: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    reference_unit: str | None = None
    reference_source: str | None = None
    # When direction == "N" (value in normal range), the abnormal phenotype(s)
    # this NORMAL result negates — i.e. the LR- rule-out targets. Empty for
    # abnormal/unknown findings. Used by the controller's LR- channel.
    negated_hpo_terms: list[str] = field(default_factory=list)


class FindingNormalizer:
    """将数值型化验描述正规化为 HPO 表型术语."""

    def __init__(
        self,
        lab_ranges_path: str | Path,
        loinc2hpo_path: str | Path,
        unit_conversions_path: str | Path | None = None,
    ) -> None:
        with open(lab_ranges_path, encoding="utf-8") as f:
            self._lab_ranges: dict = json.load(f)
        with open(loinc2hpo_path, encoding="utf-8") as f:
            self._loinc2hpo: dict = json.load(f)

        self._unit_conversions: dict[str, list[dict]] = {}
        if unit_conversions_path is not None:
            with open(unit_conversions_path, encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
            for entry in raw:
                self._unit_conversions[entry["test_group"]] = entry["conversions"]

        self._alias_map: dict[str, str] = {}
        for std_name, info in self._lab_ranges.items():
            self._alias_map[std_name.lower()] = std_name
            for alias in info.get("aliases", []):
                self._alias_map[alias.lower()] = std_name

    def normalize(
        self,
        finding: str,
        *,
        gender: str | None = None,
        age_years: float | None = None,
        specimen: str | None = None,
    ) -> NormalizedFinding | None:
        """主入口: 尝试将单条 finding 正规化. 返回 None 如果不是数值型描述.

        复合串（如 "Leukocyte count: 57,500/mm3 with 35% blasts"）返回其中
        **方向异常**（H/L）的首个分句结果；若无异常分句则返回首个可解析分句。
        需要全部分句结果时用 :meth:`normalize_multi`。
        """
        results = self.normalize_multi(
            finding, gender=gender, age_years=age_years, specimen=specimen
        )
        if not results:
            return None
        for r in results:
            if r.direction in ("H", "L") and r.hpo_term:
                return r
        return results[0]

    def normalize_multi(
        self,
        finding: str,
        *,
        gender: str | None = None,
        age_years: float | None = None,
        specimen: str | None = None,
    ) -> list[NormalizedFinding]:
        """将一条（可能复合的）finding 拆成多个原子化验并分别正规化.

        - 单一化验 → 单元素列表
        - 复合串 → 每个分句独立正规化（避免整串被错误正则吃掉，例如
          之前 "Leukocyte count: 57,500/mm3 with 35% blasts" 被误映射为
          Hyperkalemia）
        - 非数值描述 → 空列表
        """
        text = (finding or "").strip()
        if not text:
            return []
        clauses = self._split_compound(text)
        out: list[NormalizedFinding] = []
        seen: set[str] = set()
        for clause in clauses:
            res = self._try_vital(clause)
            if res is None:
                parsed = self._parse_lab(clause)
                if parsed is None:
                    continue
                res = self._classify(
                    parsed, gender=gender, age_years=age_years, specimen=specimen
                )
            if res is None:
                continue
            key = (res.hpo_term or res.test_name or clause).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(res)
        return out

    @staticmethod
    def _split_compound(text: str) -> list[str]:
        # Only split when ≥2 numeric measurements are present, else keep whole.
        if len(re.findall(r"\d", text)) < 2:
            return [text]
        parts = [p.strip() for p in _COMPOUND_SPLIT_RE.split(text) if p and p.strip()]
        return parts or [text]

    def normalize_batch(
        self,
        findings: list[str],
        *,
        gender: str | None = None,
        age_years: float | None = None,
        specimen: str | None = None,
    ) -> list[NormalizedFinding | None]:
        return [
            self.normalize(f, gender=gender, age_years=age_years, specimen=specimen)
            for f in findings
        ]

    def _parse_lab(self, text: str) -> LabParsed | None:
        """Layer 1: 正则提取 test_name + value + unit."""
        parse_text = self._prepare_lab_text(text)
        for pat in PATTERNS:
            m = pat.search(parse_text)
            if m is None:
                continue
            gd = m.groupdict()
            raw_name = gd.get("name", "").strip().rstrip(":")
            raw_value = gd.get("value", "")
            raw_unit = (gd.get("unit") or "").strip()

            if not raw_name or not raw_value:
                continue

            try:
                value = float(raw_value.replace(",", ""))
            except ValueError:
                continue

            if raw_unit:
                raw_unit = self._normalize_unit(raw_unit)

            # Percent differentials (blasts/basophils/…) are classified via
            # PERCENT_THRESHOLDS, not the lab alias map, so accept them even
            # when the name is absent from lab_reference_ranges.
            name_stem = raw_name.lower().strip().rstrip("s")
            is_percent = ("%" in (raw_unit or "") or "%" in text) and any(
                name_stem == k.rstrip("s") or name_stem.startswith(k.rstrip("s"))
                for k in PERCENT_THRESHOLDS
            )

            if is_percent or self._resolve_std_name(raw_name) is not None:
                return LabParsed(
                    test_name=raw_name.strip(),
                    value=value,
                    unit=raw_unit,
                    original=text,
                )
        return None

    @staticmethod
    def _prepare_lab_text(text: str) -> str:
        """Canonicalize typography without changing the preserved original."""
        prepared = text.translate(_SUPERSCRIPT_TRANSLATION)
        prepared = re.sub(r"(?i)mm\s+hg", "mmHg", prepared)
        prepared = re.sub(
            r"(?i)(?:x|×)\s*1000\s*/\s*([a-zμµ]+)",
            lambda m: f"×1000/{m.group(1)}",
            prepared,
        )
        # Case reports frequently flatten ×10⁹/L to either "× 10 9/L" or
        # "× 109/L". Both are restored to an unambiguous parser token.
        prepared = re.sub(
            r"(?i)(?:x|×)\s*10(?!\s*00\s*/)\s*\^?\s*([0-9]{1,2})(?![0-9])\s*/\s*([a-zμµ]+)",
            lambda m: f"×10^{m.group(1)}/{m.group(2)}",
            prepared,
        )
        return prepared

    def _extract_inline_reference(self, text: str, result_unit: str) -> dict | None:
        """Return a report-local interval explicitly printed beside a result."""
        prepared = self._prepare_lab_text(text)
        match = _INLINE_REFERENCE_RE.search(prepared)
        if match is None:
            return None

        def _number(value: str | None) -> float | None:
            return float(value.replace(",", "")) if value else None

        low = _number(match.group("low"))
        high = _number(match.group("high"))
        limit = _number(match.group("limit"))
        op = match.group("op")
        if limit is not None and op in {"<", "<=", "≤"}:
            high = limit
        elif limit is not None and op in {">", ">=", "≥"}:
            low = limit

        raw_unit = (match.group("unit") or result_unit or "").strip()
        return {
            "low": low,
            "high": high,
            "unit": self._normalize_unit(raw_unit) if raw_unit else "",
            "source": "case_local_reference",
            "reference_type": "report_local",
        }

    @staticmethod
    def _direction_narrative(std_name: str, direction: str) -> str:
        label = std_name.replace("_", " ").replace("-", " ")
        if direction == "H":
            return f"Increased {label}"
        if direction == "L":
            return f"Decreased {label}"
        if direction == "N":
            return f"{label} within the applicable reference interval"
        return f"{label} could not be interpreted"

    def _unknown_lab(
        self,
        parsed: LabParsed,
        std_name: str,
        source: str,
        narrative: str,
        ref: dict | None = None,
    ) -> NormalizedFinding:
        ref = ref or {}
        return NormalizedFinding(
            original=parsed.original,
            hpo_term=None,
            hpo_id=None,
            direction="unknown",
            confidence="low",
            source=source,
            test_name=std_name,
            value=parsed.value,
            unit=parsed.unit,
            narrative=narrative,
            reference_low=ref.get("low"),
            reference_high=ref.get("high"),
            reference_unit=ref.get("unit"),
            reference_source=ref.get("source"),
        )

    def _classify(
        self,
        parsed: LabParsed,
        *,
        gender: str | None = None,
        age_years: float | None = None,
        specimen: str | None = None,
    ) -> NormalizedFinding | None:
        """Layer 2: 结构化查表判断方向 + loinc2hpo 映射."""
        pct_result = self._try_percent_classification(parsed)
        if pct_result is not None:
            return pct_result

        std_name = self._resolve_std_name(parsed.test_name)
        if std_name is None:
            return self._unknown_lab(
                parsed,
                parsed.test_name,
                "alias_miss",
                "Laboratory test name was not found in the catalog",
            )

        info = self._lab_ranges[std_name]
        ref_ranges: list[dict] = info.get("reference_ranges", [])
        inline_ref = self._extract_inline_reference(parsed.original, parsed.unit)
        if inline_ref is not None:
            ref = inline_ref
        elif not ref_ranges:
            source = (
                "clinical_context_required"
                if info.get("requires_local_or_clinical_context")
                else "no_ref_range"
            )
            return self._unknown_lab(
                parsed,
                std_name,
                source,
                "No universal reference interval is safe for this test; use the reporting laboratory interval and required clinical context",
            )
        else:
            ref = self._pick_ref_range(
                ref_ranges,
                parsed_unit=parsed.unit,
                gender=gender,
                age_years=age_years,
                specimen=specimen,
            )
            if (
                ref is None
                and gender is None
                and age_years is None
                and specimen is None
            ):
                ref = self._pick_consensus_ref_range(std_name, ref_ranges, parsed)
            if ref is None:
                return self._unknown_lab(
                    parsed,
                    std_name,
                    "reference_context_required",
                    "Sex, age, specimen, phase, or assay context is required to select a reference interval",
                )

        value = parsed.value
        confidence = "high"

        ref_unit = self._normalize_unit(ref.get("unit", "")) if ref.get("unit") else ""
        parsed_unit = self._normalize_unit(parsed.unit) if parsed.unit else ""

        if parsed_unit and ref_unit and parsed_unit != ref_unit:
            converted = self._convert_unit(std_name, value, parsed_unit, ref_unit)
            if converted is not None:
                value = converted
            else:
                logger.debug(
                    "Unit mismatch for %s: got %s, expected %s, no conversion found",
                    std_name, parsed_unit, ref_unit,
                )
                return self._unknown_lab(
                    parsed,
                    std_name,
                    "unit_mismatch",
                    f"Unit {parsed_unit} is not compatible with reference unit {ref_unit}",
                    ref,
                )
        elif not parsed_unit and ref_unit:
            # Preserve historical support for unitless case-table values, but
            # make the assumption visible and lower confidence.
            confidence = "medium"

        if inline_ref is None and (
            info.get("prefer_local_reference")
            or ref.get("reference_type") in {
                "assay_specific_representative",
                "method_specific_decision_limit",
            }
        ):
            confidence = "medium"

        low = ref.get("low")
        high = ref.get("high")
        direction = self._determine_direction(value, low, high)

        loinc_codes = info.get("loinc_codes", [])
        scale = info.get("scale", "Qn")
        hpo_term, hpo_id = self._lookup_hpo(loinc_codes, scale, direction)
        narrative = hpo_term or self._direction_narrative(std_name, direction)

        negated: list[str] = []
        if direction == "N":
            # A normal value negates BOTH the high and low abnormal phenotypes.
            for d in ("H", "L"):
                t, _ = self._lookup_hpo(loinc_codes, scale, d)
                if t:
                    negated.append(t)

        return NormalizedFinding(
            original=parsed.original,
            hpo_term=hpo_term,
            hpo_id=hpo_id,
            direction=direction,
            confidence=confidence,
            source="case_local_reference+loinc2hpo" if inline_ref is not None else "loinc2hpo",
            test_name=std_name,
            value=parsed.value,
            unit=parsed.unit,
            narrative=narrative,
            reference_low=low,
            reference_high=high,
            reference_unit=ref_unit,
            reference_source=ref.get("source"),
            negated_hpo_terms=negated,
        )

    def _try_vital(self, text: str) -> NormalizedFinding | None:
        """Deterministic vital-sign → HPO classification (not in lab ranges)."""
        low = text.lower()

        # Blood pressure (two numbers): systolic/diastolic.
        if "blood pressure" in low or "bp" in low.split() or re.search(r"\b\d{2,3}\s*/\s*\d{2,3}\b", text):
            m = _BP_RE.search(text)
            if m:
                try:
                    sys_v = int(m.group("sys")); dia_v = int(m.group("dia"))
                except (TypeError, ValueError):
                    sys_v = dia_v = None
                if sys_v and dia_v and 50 <= sys_v <= 300 and 30 <= dia_v <= 200:
                    if sys_v >= 140 or dia_v >= 90:
                        return self._vital_finding(text, "HP:0000822", "Hypertension", "H")
                    if sys_v < 90 or dia_v < 60:
                        return self._vital_finding(text, "HP:0002615", "Hypotension", "L")
                    return self._vital_finding(text, None, None, "N",
                                               negated=["Hypertension", "Hypotension"])

        m = re.search(r"(?P<name>[A-Za-z][A-Za-z0-9 /]+?)\s*[:=]?\s*(?P<value>\d+\.?\d*)\s*(?P<unit>°?\s*[CFcf%]|/min|bpm|mmhg)?", text)
        if not m:
            return None
        name = m.group("name").strip().lower()
        try:
            value = float(m.group("value"))
        except (TypeError, ValueError):
            return None
        unit = (m.group("unit") or "").lower().replace(" ", "")

        name_toks = set(re.findall(r"[a-z]+", name))

        def _name_matches(names: tuple) -> bool:
            for n in names:
                if len(n) <= 3:  # abbreviation: require exact standalone token
                    if n in name_toks:
                        return True
                elif name == n or name.startswith(n) or n in name:
                    return True
            return False

        for rule in VITAL_RULES.values():
            if not _name_matches(rule["names"]):
                continue
            # Temperature: pick threshold by unit (default °F if value > 50).
            if "high_f" in rule:
                is_c = "c" in unit and "f" not in unit
                if not unit:
                    is_c = value < 50  # 38 → Celsius, 100 → Fahrenheit
                hi = rule["high_c"] if is_c else rule["high_f"]
                lo = rule["low_c"] if is_c else rule["low_f"]
            else:
                hi = rule.get("high"); lo = rule.get("low")
            if hi is not None and value > hi and rule.get("hpo_high"):
                return self._vital_finding(text, *rule["hpo_high"], "H")
            if lo is not None and value < lo and rule.get("hpo_low"):
                return self._vital_finding(text, *rule["hpo_low"], "L")
            neg = [t for t in (
                (rule.get("hpo_high") or (None, None))[1],
                (rule.get("hpo_low") or (None, None))[1],
            ) if t]
            return self._vital_finding(text, None, None, "N", negated=neg)
        return None

    @staticmethod
    def _vital_finding(text, hpo_id, hpo_term, direction, negated=None) -> NormalizedFinding:
        return NormalizedFinding(
            original=text, hpo_term=hpo_term, hpo_id=hpo_id,
            direction=direction, confidence="high", source="vital_rule",
            test_name=None, value=None, unit=None,
            negated_hpo_terms=list(negated or []),
        )

    def _try_percent_classification(self, parsed: LabParsed) -> NormalizedFinding | None:
        name_lower = parsed.test_name.lower().rstrip("s")
        is_pct = parsed.unit == "%" or "%" in parsed.original
        for key, thresholds in PERCENT_THRESHOLDS.items():
            key_stem = key.rstrip("s")
            if key_stem != name_lower and not (
                is_pct and (
                    name_lower.startswith(key_stem)
                    or key_stem.startswith(name_lower)
                )
            ):
                continue

            direction = "N"
            hpo_id, hpo_term = None, None

            th_high = thresholds.get("threshold_high")
            th_low = thresholds.get("threshold_low")

            if th_high is not None and parsed.value > th_high:
                direction = "H"
                hpo_id, hpo_term = thresholds["hpo_high"]
            elif th_low is not None and parsed.value < th_low:
                direction = "L"
                hpo_id, hpo_term = thresholds["hpo_low"]

            negated: list[str] = []
            if direction == "N":
                for k in ("hpo_high", "hpo_low"):
                    tup = thresholds.get(k)
                    if tup and tup[1]:
                        negated.append(tup[1])

            return NormalizedFinding(
                original=parsed.original,
                hpo_term=hpo_term,
                hpo_id=hpo_id,
                direction=direction,
                confidence="high",
                source="percent_threshold",
                negated_hpo_terms=negated,
                test_name=parsed.test_name,
                value=parsed.value,
                unit="%",
            )
        return None

    def _resolve_std_name(self, raw_name: str) -> str | None:
        key = raw_name.lower().strip()
        if key in self._alias_map:
            return self._alias_map[key]
        # Word-boundary aware fallback. A bare unbounded substring test caused
        # dangerous mis-maps (e.g. "leukocyte count" matched a short potassium
        # alias → "Hyperkalemia"). Require the alias to appear as a whole token
        # and to be at least 3 chars, or the raw name to be fully contained in
        # the alias.
        def _stem(toks: set[str]) -> set[str]:
            # crude singularisation so "leukocytes" == "leukocyte"
            return {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks}

        key_tokens = _stem(set(re.findall(r"[a-z0-9]+", key)))
        best: str | None = None
        best_len = 0
        for alias_key, std in self._alias_map.items():
            if len(alias_key) < 3:
                continue
            alias_tokens = _stem(set(re.findall(r"[a-z0-9]+", alias_key)))
            matched = False
            if alias_tokens and alias_tokens <= key_tokens:
                matched = True  # every alias token present as a token in name
            elif key in alias_key:
                matched = True  # name fully contained in a longer alias
            if matched and len(alias_key) > best_len:
                best, best_len = std, len(alias_key)
        return best

    def _normalize_unit(self, raw_unit: str) -> str:
        unit = self._prepare_lab_text(raw_unit or "").strip().strip(".,;()")
        if not unit:
            return ""
        unit = unit.replace("µ", "μ")
        suffix = ""
        suffix_match = re.search(r"(?i)\s+(FEU|DDU)$", unit)
        if suffix_match:
            suffix = " " + suffix_match.group(1).upper()
            unit = unit[: suffix_match.start()].strip()
        key = re.sub(r"\s+", "", unit).lower()
        normalized = _UNIT_NORMALIZE_MAP.get(key, unit)
        return normalized + suffix

    def _pick_ref_range(
        self,
        ranges: list[dict],
        *,
        parsed_unit: str = "",
        gender: str | None = None,
        age_years: float | None = None,
        specimen: str | None = None,
    ) -> dict | None:
        candidates = list(ranges)

        if specimen:
            specimen_key = specimen.casefold().strip()
            matched = [
                r
                for r in candidates
                if not r.get("specimen")
                or specimen_key in str(r["specimen"]).casefold()
                or str(r["specimen"]).casefold() in specimen_key
            ]
            if matched:
                candidates = matched

        normalized_gender = (gender or "").casefold().strip()
        normalized_gender = {"m": "male", "man": "male", "f": "female", "woman": "female"}.get(
            normalized_gender, normalized_gender
        )
        if normalized_gender:
            matched = [
                r
                for r in candidates
                if str(r.get("gender", "any")).casefold() in {"any", normalized_gender}
            ]
            if matched:
                exact = [
                    r for r in matched if str(r.get("gender", "any")).casefold() == normalized_gender
                ]
                candidates = exact or matched
        else:
            any_gender = [
                r for r in candidates if str(r.get("gender", "any")).casefold() == "any"
            ]
            if any_gender:
                candidates = any_gender

        if age_years is not None:
            matched = [
                r
                for r in candidates
                if (r.get("age_min") is None or age_years >= r["age_min"])
                and (r.get("age_max") is None or age_years <= r["age_max"])
            ]
            if matched:
                candidates = matched
        else:
            unstratified = [
                r for r in candidates if r.get("age_min") is None and r.get("age_max") is None
            ]
            if unstratified:
                candidates = unstratified

        unit = self._normalize_unit(parsed_unit) if parsed_unit else ""
        if unit:
            exact_unit = [
                r for r in candidates if self._normalize_unit(str(r.get("unit", ""))) == unit
            ]
            if exact_unit:
                candidates = exact_unit

        if not candidates:
            return None
        distinct = {
            (r.get("low"), r.get("high"), self._normalize_unit(str(r.get("unit", ""))))
            for r in candidates
        }
        # Never silently select male/female, cycle-phase, or assay-stratified
        # limits when the caller did not provide enough context.
        if len(distinct) > 1:
            return None
        return candidates[0]

    def _pick_consensus_ref_range(
        self, std_name: str, ranges: list[dict], parsed: LabParsed
    ) -> dict | None:
        """Use stratified ranges only when every stratum yields one direction.

        A hemoglobin of 7 g/dL is low for every adult sex stratum and can be
        safely normalized without sex metadata; 13 g/dL is ambiguous and must
        remain unknown. The same rule protects sex-specific hs-troponin limits.
        """
        directions: set[str] = set()
        observed_unit = self._normalize_unit(parsed.unit) if parsed.unit else ""
        for ref in ranges:
            target_unit = self._normalize_unit(str(ref.get("unit", "")))
            value = parsed.value
            if observed_unit and target_unit and observed_unit != target_unit:
                converted = self._convert_unit(
                    std_name, value, observed_unit, target_unit
                )
                if converted is None:
                    return None
                value = converted
            directions.add(
                self._determine_direction(value, ref.get("low"), ref.get("high"))
            )
        return ranges[0] if len(directions) == 1 else None

    def _convert_unit(
        self, std_name: str, value: float, from_unit: str, to_unit: str
    ) -> float | None:
        test_group = _TEST_GROUP_MAP.get(std_name, std_name)

        convs = self._unit_conversions.get(test_group, [])
        from_unit = self._normalize_unit(from_unit)
        to_unit = self._normalize_unit(to_unit)
        for conv in convs:
            conv_from = self._normalize_unit(conv["from"])
            conv_to = self._normalize_unit(conv["to"])
            if conv_from == from_unit and conv_to == to_unit:
                return value * conv["factor"]
            if conv_to == from_unit and conv_from == to_unit:
                return value / conv["factor"]

        return None

    @staticmethod
    def _determine_direction(value: float, low: float | None, high: float | None) -> str:
        if high is not None and value > high:
            return "H"
        if low is not None and value < low:
            return "L"
        return "N"

    def _lookup_hpo(
        self, loinc_codes: list[str], scale: str, direction: str
    ) -> tuple[str | None, str | None]:
        for code in loinc_codes:
            entry = self._loinc2hpo.get(code, {}).get(scale, {})
            mapping = entry.get(direction)
            if mapping is not None:
                return mapping.get("hpo_term"), mapping.get("hpo_id")
        if direction == "N":
            return None, None
        return None, None
