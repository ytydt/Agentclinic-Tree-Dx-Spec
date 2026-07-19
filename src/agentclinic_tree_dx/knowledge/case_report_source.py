"""Case-report retrieval layer serving branch creation (dual-entrance).

GRAPHRAG_MULTISOURCE_FEASIBILITY_RESEARCH.md §5/§7: CPG defines the MECE axis
and mandatory coverage, but the RECALL ceiling for long-tail / zebra diagnoses
(Pancoast, CML blast crisis, glucagonoma, peliosis) must be raised by
presentation→diagnosis sources — case reports and synthetic DDx datasets. This
module is that layer: it retrieves over the case-report index and nominates the
diseases those cases mapped their presentation to, projecting them onto the
branch-knowledge axis partition so BranchCreator gets a reachable node for the
rare gold.

Implementation: a thin specialization of ``GuidelineBranchSource`` — it reuses
the SAME dual-entrance (syndrome ∪ salient findings) + RRF + SNOMED-spotter
machinery, pointed at the case-report index instead of the CPG index. The only
addition is ``recall_for_branches``, which projects the recalled diseases onto
an axis-map partition for ``controller._build_branch_candidates``.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from .guideline_branch_source import GuidelineBranchSource, _GENERIC_NAMES

logger = logging.getLogger(__name__)

# Generic single-token clinical qualifiers / symptoms that appear as (or inside)
# diagnosis strings in the real corpora (findzebra diagnosis lists, DDXPlus
# fragments) but are NOT diseases — spotting them pollutes recall with noise
# like "progressive"/"fever"/"liver". Single-token vocab entries in this set are
# dropped; multi-token disease names ("progressive supranuclear palsy") are kept.
_GENERIC_SINGLE = _GENERIC_NAMES | {
    "progressive", "chronic", "acute", "recurrent", "systemic", "primary",
    "secondary", "idiopathic", "congenital", "acquired", "severe", "mild",
    "moderate", "bilateral", "unilateral", "diffuse", "focal", "generalized",
    "fever", "liver", "kidney", "renal", "cardiac", "pulmonary", "hepatic",
    "pain", "cough", "rash", "edema", "oedema", "anemia", "anaemia", "syncope",
    "seizure", "seizures", "headache", "weakness", "fatigue", "depression",
    "hypertension", "diabetes", "obesity", "alcoholic", "amyloid", "familial",
    "autoimmune", "inflammatory", "degenerative", "metabolic", "genetic",
}


def build_case_report_vocab(normalized_path: str | Path, *, min_len: int = 5,
                            max_len: int = 60) -> set[str]:
    """Collect the diagnosis + differential names from the normalized
    case-report corpus (case_reports.jsonl) as an extra spotting vocabulary.

    Case reports carry GROUND-TRUTH disease names that the SNOMED disorder
    vocabulary may miss (glucagonoma, "chronic myeloid leukemia in blast
    crisis", peliosis hepatis — the long-tail entities that motivated this
    source). Unioning them into the spotter vocab lets the case-report entrance
    recall those exact golds verbatim. Length-gated, and single-token generic
    qualifiers/symptoms are dropped so the spotter is not polluted by fragments
    like "progressive"/"fever" that occur as diagnosis strings in the raw data.
    Fail-open (returns {} if the file is missing/malformed)."""
    vocab: set[str] = set()
    p = Path(normalized_path)
    if not p.exists():
        return vocab
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                for nm in (rec.get("diagnoses") or []) + (rec.get("differentials") or []):
                    nm = re.sub(r"\s+", " ", str(nm).strip().lower())
                    if not (min_len <= len(nm) <= max_len):
                        continue
                    # drop single-token generic qualifiers / symptoms (noise);
                    # keep multi-token names and specific single-token diseases.
                    if " " not in nm and nm in _GENERIC_SINGLE:
                        continue
                    vocab.add(nm)
    except Exception:  # pragma: no cover - defensive
        return vocab
    return vocab


class CaseReportBranchSource(GuidelineBranchSource):
    """Dual-entrance recall over the case-report corpus, projected onto an axis
    partition. Constructor mirrors ``GuidelineBranchSource`` (retriever,
    disorder_vocab, resolver, ...) but raises the spotter n-gram cap so longer
    case-report diagnoses ("chronic myeloid leukemia in blast crisis") are
    matched whole."""

    def __init__(self, *args, **kwargs) -> None:
        # title_boost: multiplier for a disease spotted in the chunk TITLE
        # ("Case report: {confirmed dx}") vs one only in the differential list.
        # Promotes the diagnosis each retrieved case is ABOUT over common
        # co-occurring DDx entities, which frequency-summing otherwise buries.
        self._title_boost = float(kwargs.pop("title_boost", 2.5))
        super().__init__(*args, **kwargs)
        self._max_ngram = 7

    def _spot_weighted(self, title: str, content: str) -> dict[str, float]:
        """Up-weight the case's CONFIRMED diagnosis (in the title) over the
        diseases that merely appear in its differential list (content-only)."""
        out = {dz: 1.0 for dz in self._spot(content or "")}
        for dz in self._spot(title or ""):
            out[dz] = self._title_boost
        return out

    def recall(self, syndrome: str, *, top_k: Optional[int] = None,
               context: str = "",
               salient_findings: Optional[list[str]] = None,
               finding_entrance_weight: float = 1.0,
               rrf_k: int = 60,
               salient_gate: bool = False) -> dict[str, float]:
        """Dual-entrance recall specialised for the case-report corpus.

        Unlike the CPG-tuned parent (whose syndrome entrance uses the legacy
        colloquial/DDx-phrasing spotter), BOTH entrances here go through the
        score-filtered finding path: case-report chunks share a
        "Differential diagnosis includes: …" boilerplate, so an unfiltered
        syndrome query would spot every case's DDx at zero similarity. Running
        the syndrome as a score-filtered query keeps only genuinely matched
        cases, then the concrete salient findings (higher precision) are
        weighted-RRF-fused on top.

        ``rrf_k`` / ``salient_gate`` (D-fusion): see ``GuidelineBranchSource.recall``.
        The gate drops non-discriminative salient findings before the second
        entrance so a broad finding cannot dilute the syndrome ranking."""
        if self._r is None or not getattr(self._r, "is_ready", False):
            return {}
        syn_terms: list[str] = []
        if syndrome and syndrome.strip():
            syn_terms.append(syndrome.strip())
        if context and context.strip():
            syn_terms.append(context.strip()[:300])
        syn_scored = self._recall_from_findings(syn_terms, top_k=top_k) if syn_terms else {}
        sal = [s for s in (salient_findings or []) if s and str(s).strip()]
        if salient_gate and sal:
            sal = [s for s in sal if self._finding_is_discriminative(s)]
        if not sal:
            ranked = sorted(syn_scored.items(), key=lambda kv: kv[1], reverse=True)
            return dict(ranked[: self._max_candidates])
        find_scored = self._recall_from_findings(sal, top_k=top_k)
        fused = self._rrf_merge([syn_scored, find_scored], k=rrf_k,
                                weights=[1.0, finding_entrance_weight])
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        return dict(ranked[: self._max_candidates])

    # recall_for_branches is inherited from GuidelineBranchSource: it calls the
    # (polymorphic) self.recall above, so the case-report-tuned dual entrance is
    # projected onto axis domains with the same generic logic.
