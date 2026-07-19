"""§31.13 — KB-derived axis/domain partition (BranchCreator automation mode).

``KBAxisMap`` is a drop-in replacement for ``SyndromeAxisMap`` that derives the
syndrome → L1-axis → MECE-domain partition **from external knowledge bases at
runtime**, instead of the hand-authored ``syndrome_axis_map.json``:

  1. seed         : the chief presenting finding(s)/syndrome cues recognised in
                    the vignette (matched against the differential-recall tables'
                    keywords + the LR-cache finding vocabulary).
  2. recall       : candidate disease entities for the seed, drawn from the
                    DIFFERENTIAL-oriented tables (``mechanism_to_disease.json``
                    family_expansions + ``diagnostic_markers.json`` target
                    diseases), supplemented by the LR cache. §31.13 feasibility:
                    the rich LR/SNOMED/HPOA KBs do NOT cleanly map a presenting
                    SIGN to its common-disease differential, so recall leans on
                    the existing (smaller) differential tables while the axis,
                    domain partition, projection and split are automated below.
  3. axis select  : group candidates by each SNOMED CT *defining attribute*
                    (finding_site=anatomy, pathological_process=mechanism,
                     due_to/causative_agent=etiology, associated_morphology),
                    score each grouping for MECE quality, pick the single best
                    axis.
  4. domains      : each attribute-value group becomes an L1 domain; the disease
                    names + attribute value become ``member_keywords`` (so the
                    inherited ``project_entity`` routes a gold entity to its
                    domain).
  5. split        : within a domain, diseases whose seed-finding LR direction
                    *opposes* the group majority are emitted as ``split_variants``
                    (drives ``enable_phase_subaxis`` automatically).

Because ``match()`` returns an entry with the SAME shape the hand map uses
(``domains[].member_keywords`` / ``split_variants``), the inherited
``domain_names`` / ``project_entity`` / ``_partition`` work unchanged, and the
downstream ``_build_branch_candidates`` → ``_enforce_mandatory_branches`` /
``_populate_lookup_entities`` contract is byte-compatible. All optimisation flags
keep working.

Pure / deterministic given the same KB snapshot: identical input → identical
output. No LLM, no network.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .syndrome_axis import SyndromeAxisMap

logger = logging.getLogger(__name__)

# SNOMED defining-attribute → human-readable classification axis label.
_AXIS_ATTRS: dict[str, str] = {
    "finding_site": "anatomy",
    "pathological_process": "mechanism",
    "associated_morphology": "morphology",
    "due_to": "etiology",
    "causative_agent": "etiology",
    "occurrence": "temporal",
}
# attributes that share one axis bucket (etiology = due_to ∪ causative_agent)
_AXIS_BUCKETS: dict[str, list[str]] = {
    "anatomy": ["finding_site"],
    "mechanism": ["pathological_process"],
    "morphology": ["associated_morphology"],
    "etiology": ["due_to", "causative_agent"],
    "temporal": ["occurrence"],
}

_STOP = {
    "of", "the", "a", "an", "and", "or", "with", "due", "to", "non", "type",
    "disorder", "disease", "syndrome", "finding", "structure", "entire",
    "primary", "secondary", "acute", "chronic", "left", "right", "bilateral",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) > 2 and t not in _STOP}


class KBAxisMap(SyndromeAxisMap):
    """KB-derived axis map. Overrides only ``match`` (+ caches); reuses the
    inherited ``domain_names`` / ``project_entity`` / ``_partition`` statics."""

    def __init__(
        self,
        lr_cache: dict,
        snomed_concepts: dict,
        snomed_term_index: dict,
        snomed_relations: list,
        *,
        mechanism_to_disease: dict | None = None,
        diagnostic_markers: list | None = None,
        fallback_axis: str = "mechanism",
        max_candidates: int = 40,
        min_domains: int = 2,
        max_domains: int = 6,
    ) -> None:
        super().__init__([], fallback_axis=fallback_axis)
        self._max_candidates = max_candidates
        self._min_domains = min_domains
        self._max_domains = max_domains
        self._cache: dict[str, dict] = {}

        # ── differential-recall tables (syndrome cue → candidate diseases) ───
        # mechanism_to_disease family_expansions: [{any_keywords:[...], entities:[...]}]
        self._fam: list[tuple[list[str], list[str]]] = []
        for fx in ((mechanism_to_disease or {}).get("family_expansions", []) or []):
            kws = [str(k).lower() for k in (fx.get("any_keywords") or [])]
            ents = [str(e).lower() for e in (fx.get("entities") or [])]
            if kws and ents:
                self._fam.append((kws, ents))
        # diagnostic markers: [{terms:[...], target_diseases:[...]}]
        self._markers: list[tuple[list[str], list[str]]] = []
        for m in (diagnostic_markers or []):
            terms = [str(t).lower() for t in (m.get("terms") or [])]
            tds = [str(t).lower() for t in (m.get("target_diseases") or [])]
            if terms and tds:
                self._markers.append((terms, tds))

        # ── finding → {disease: lr_positive} recall index (from LR cache) ─────
        self._finding_diseases: dict[str, dict[str, float]] = defaultdict(dict)
        self._finding_vocab: list[str] = []
        for entry in lr_cache.values():
            f = str(entry.get("finding", "")).strip().lower()
            d = str(entry.get("disease", "")).strip().lower()
            if not f or not d:
                continue
            try:
                lrp = float(entry.get("lr_positive") or 0.0)
            except (TypeError, ValueError):
                lrp = 0.0
            # keep the most informative (farthest from 1) LR per (finding,disease)
            prev = self._finding_diseases[f].get(d)
            if prev is None or abs(lrp - 1.0) > abs(prev - 1.0):
                self._finding_diseases[f][d] = lrp
        # longest findings first so specific phrases win the substring scan
        self._finding_vocab = sorted(self._finding_diseases, key=len, reverse=True)

        # ── SNOMED resolution + axis-attribute lookup ────────────────────────
        self._concepts = snomed_concepts
        self._term_index = snomed_term_index
        self._rel_by_src: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._isa_parents: dict[str, list[str]] = defaultdict(list)
        for r in snomed_relations:
            t = r.get("type")
            if t in _AXIS_ATTRS:
                self._rel_by_src[r["src"]].append((t, r["dst"]))
            elif t == "is_a":
                self._isa_parents[r["src"]].append(r["dst"])
        logger.info("KBAxisMap ready: %d findings, %d SNOMED concepts",
                    len(self._finding_vocab), len(self._concepts))

    # ----------------------------------------------------------------- loaders
    @classmethod
    def from_files(
        cls,
        lr_cache_json: str | Path,
        snomed_concepts_json: str | Path,
        snomed_term_index_json: str | Path,
        snomed_relations_json: str | Path,
        mechanism_to_disease_json: str | Path | None = None,
        diagnostic_markers_json: str | Path | None = None,
        **kw,
    ) -> "KBAxisMap":
        def _load(p, default=None):
            if p is None or not Path(p).exists():
                return default
            return json.loads(Path(p).read_text(encoding="utf-8"))
        m2d = _load(mechanism_to_disease_json, {})
        dm_raw = _load(diagnostic_markers_json, {})
        # diagnostic_markers.json: {"entries": [{hpo_term, disease, ...}]} →
        # group by hpo_term to {terms:[hpo_term], target_diseases:[diseases]}.
        markers: list[dict] = []
        entries = dm_raw.get("entries", []) if isinstance(dm_raw, dict) else dm_raw
        by_term: dict[str, list[str]] = defaultdict(list)
        if isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict) and e.get("hpo_term") and e.get("disease"):
                    by_term[str(e["hpo_term"]).lower()].append(str(e["disease"]))
        markers = [{"terms": [t], "target_diseases": ds} for t, ds in by_term.items()]
        return cls(
            _load(lr_cache_json, {}), _load(snomed_concepts_json, {}),
            _load(snomed_term_index_json, {}), _load(snomed_relations_json, []),
            mechanism_to_disease=m2d, diagnostic_markers=markers, **kw,
        )

    # ------------------------------------------------------------- SNOMED axis
    def _concept_name(self, cid: str) -> str:
        c = self._concepts.get(cid)
        return (c.get("preferred") if c else "") or cid

    def _resolve(self, disease: str) -> Optional[str]:
        """disease name → best SNOMED concept id (prefer a 'disorder' that
        actually carries axis relations)."""
        ids = self._term_index.get((disease or "").strip().lower(), [])
        best, best_score = None, -1
        for cid in ids:
            c = self._concepts.get(cid) or {}
            rels = self._rel_by_src.get(cid, [])
            score = len(rels) + (5 if c.get("tag") == "disorder" else 0)
            if score > best_score:
                best, best_score = cid, score
        return best

    def _axis_values(self, disease: str) -> dict[str, list[str]]:
        """disease → {axis_bucket: [attribute value names]} via SNOMED."""
        cid = self._resolve(disease)
        if cid is None:
            return {}
        out: dict[str, list[str]] = defaultdict(list)
        for t, dst in self._rel_by_src.get(cid, []):
            axis = _AXIS_ATTRS.get(t)
            if not axis:
                continue
            # §31.13 feasibility: body-structure (finding_site) targets are
            # absent from the disorder/finding concept export → unnameable. Only
            # keep attribute values whose concept NAME resolves, so an axis with
            # unreadable values (anatomy) scores ~0 and is never selected.
            if dst in self._concepts:
                out[axis].append(self._concept_name(dst))
        return out

    def _ancestors(self, cid: str, max_depth: int = 5) -> set[str]:
        """is_a ancestors of a concept (bounded depth), for taxonomy grouping."""
        seen: set[str] = set()
        frontier = [(cid, 0)]
        while frontier:
            c, depth = frontier.pop()
            if depth >= max_depth:
                continue
            for p in self._isa_parents.get(c, []):
                if p not in seen:
                    seen.add(p)
                    frontier.append((p, depth + 1))
        return seen

    def _taxonomy_groups(self, cand: list[str]) -> dict[str, list[str]]:
        """Group candidates by a shared is_a ancestor concept, choosing ancestors
        that cover ≥2 candidates and are not over-generic. Produces clinically
        meaningful SUPER-FAMILIES (e.g. myeloid vs lymphoid neoplasm) at a level
        the per-disease morphology attribute cannot."""
        _GENERIC = {"clinical", "body", "system", "general", "structure",
                    "neoplasm", "tumor", "tumour", "mass", "lesion", "process",
                    "morphology", "abnormality", "abnormal", "anatomical"}
        anc_cov: dict[str, set[str]] = defaultdict(set)
        cid_of = {d: self._resolve(d) for d in cand}
        for d, cid in cid_of.items():
            if cid is None:
                continue
            for a in self._ancestors(cid):
                toks = _tokens(self._concept_name(a))
                if not toks or toks <= _GENERIC:
                    continue
                anc_cov[a].add(d)
        n = len(cand)
        # keep ancestors covering 2..70% of candidates (discriminative, not the
        # near-universal root); prefer the SMALLEST (most specific) per disease.
        usable = {a: s for a, s in anc_cov.items()
                  if 2 <= len(s) <= max(2, int(0.7 * n))}
        if not usable:
            return {}
        # MECE assignment: each disease → its most specific usable ancestor.
        assign: dict[str, str] = {}
        for d in cand:
            covering = [a for a, s in usable.items() if d in s]
            if not covering:
                continue
            best = min(covering, key=lambda a: (len(usable[a]), self._concept_name(a)))
            assign[d] = best
        groups: dict[str, list[str]] = defaultdict(list)
        for d, a in assign.items():
            groups[self._concept_name(a)].append(d)
        # cap to the largest max_domains groups
        top = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
        return {k: sorted(v) for k, v in top[: self._max_domains] if k}

    # ------------------------------------------------------------------ recall
    def _seed_findings(self, text: str) -> list[str]:
        """Recognise LR-cache findings appearing in the vignette (for the
        opposite-direction split signal)."""
        tl = (text or "").lower()
        seeds = []
        for f in self._finding_vocab:
            if len(f) >= 4 and f in tl:
                seeds.append(f)
                if len(seeds) >= 8:
                    break
        return seeds

    def _recall(self, text: str, seeds: list[str]) -> dict[str, float]:
        """Recall candidate diseases for the vignette from the differential
        tables (family_expansions + diagnostic markers), then attach a signed
        LR direction from the LR cache (for the split step). Returns
        {disease: lr_positive_on_best_seed (1.0 if unknown)}."""
        tl = (text or "").lower()
        cand: set[str] = set()
        # (1) mechanism_to_disease family expansions: any keyword present → entities
        for kws, ents in self._fam:
            if any(k in tl for k in kws):
                cand.update(ents)
        # (2) diagnostic markers: any term present → target diseases
        for terms, tds in self._markers:
            if any(t in tl for t in terms):
                cand.update(tds)
        # (3) supplement with LR-cache sign→disease (weak; same-sign findings)
        for f in seeds:
            cand.update(self._finding_diseases.get(f, {}).keys())
        # attach LR direction from the seed findings
        out: dict[str, float] = {}
        for d in cand:
            lrp = 1.0
            for f in seeds:
                v = self._finding_diseases.get(f, {}).get(d)
                if v is not None and abs(v - 1.0) > abs(lrp - 1.0):
                    lrp = v
            out[d] = lrp
        # rank: diseases with a known (informative) direction first
        ranked = sorted(out.items(), key=lambda kv: abs(kv[1] - 1.0), reverse=True)
        return dict(ranked[: self._max_candidates])

    # ------------------------------------------------------------- axis scoring
    def _score_axis(self, axis: str, groups: dict[str, list[str]],
                    n_cand: int) -> float:
        """MECE quality: assigned-coverage × balance, penalise too few/many
        groups."""
        assigned = sum(len(v) for v in groups.values())
        n_groups = len(groups)
        if n_groups < self._min_domains or assigned == 0:
            return 0.0
        coverage = assigned / max(1, n_cand)
        # balance: 1 when groups are evenly sized, →0 when one group dominates
        sizes = sorted((len(v) for v in groups.values()), reverse=True)
        balance = 1.0 - (sizes[0] / assigned)  # 0 if a single group holds all
        group_pen = 1.0 if n_groups <= self._max_domains else self._max_domains / n_groups
        return coverage * (0.4 + 0.6 * balance) * group_pen

    # --------------------------------------------------------------- core match
    def match(self, text: str) -> dict:  # type: ignore[override]
        key = (text or "")[:400]
        if key in self._cache:
            return self._cache[key]
        entry = self._build_entry(text)
        self._cache[key] = entry
        return entry

    def _build_entry(self, text: str) -> dict:
        seeds = self._seed_findings(text)
        cand = self._recall(text, seeds)
        return self._partition_candidates(cand, seeds)

    def partition_from_candidates(self, candidates, seeds: list[str] | None = None) -> dict:
        """§31.13.6 oracle-recall hook: build the axis/domain entry from a GIVEN
        candidate disease set (instead of automated recall), so the SNOMED
        partition + axis quality can be evaluated in ISOLATION from recall.
        ``candidates`` may be a list of names or a {name: lr} dict."""
        if isinstance(candidates, dict):
            cand = {str(k).lower(): float(v) for k, v in candidates.items()}
        else:
            cand = {str(c).lower(): 1.0 for c in candidates}
        return self._partition_candidates(cand, seeds or [])

    def _partition_candidates(self, cand: dict[str, float], seeds: list[str]) -> dict:
        if len(cand) < self._min_domains:
            return self._fallback_entry

        # group candidates by each axis bucket, pick the best-scoring axis
        per_axis: dict[str, dict[str, list[str]]] = {}
        for d in cand:
            av = self._axis_values(d)
            for axis, values in av.items():
                if not values:
                    continue
                # one disease → its first (primary) value on this axis
                val = values[0]
                per_axis.setdefault(axis, defaultdict(list))[val].append(d)
        # taxonomy (is_a ancestor) axis — yields clinically meaningful
        # super-families at the right granularity where morphology degenerates.
        tax = self._taxonomy_groups(list(cand))
        if tax:
            per_axis["taxonomy"] = tax
        best_axis, best_groups, best_score = None, None, 0.0
        for axis, groups in per_axis.items():
            s = self._score_axis(axis, groups, len(cand))
            # prefer taxonomy on ties — it groups at the clinical family level
            if axis == "taxonomy":
                s *= 1.15
            if s > best_score:
                best_axis, best_groups, best_score = axis, groups, s
        if not best_axis or not best_groups:
            return self._fallback_entry

        # cap to the top max_domains groups by size
        groups_sorted = sorted(best_groups.items(), key=lambda kv: len(kv[1]),
                               reverse=True)[: self._max_domains]
        domains = []
        for val, diseases in groups_sorted:
            kws = sorted({val.lower()} | {d for d in diseases}
                         | _tokens(val))
            dom = {"name": f"{val} ({best_axis})", "member_keywords": kws,
                   "_entities": diseases}
            variants = self._split_variants(diseases, cand, best_axis, val)
            if variants:
                dom["split_variants"] = variants
            domains.append(dom)

        tag = (seeds[0] if seeds else "diff")[:40]
        entry = {
            "id": f"auto::{tag}",
            "axis": best_axis,
            "axis_rationale": (f"KB-derived (§31.13): {len(cand)} candidates "
                               f"recalled from differential tables partitioned by "
                               f"SNOMED {_AXIS_BUCKETS.get(best_axis, [best_axis])[0]} "
                               f"(MECE score {best_score:.2f})."),
            "domains": domains,
            "syndrome_keywords": seeds,
        }
        logger.info("KBAxisMap: tag=%s axis=%s domains=%d cand=%d score=%.2f",
                    tag, best_axis, len(domains), len(cand), best_score)
        return entry

    def _split_variants(self, diseases: list[str], cand: dict[str, float],
                        axis: str, val: str) -> list[dict]:
        """Within a domain, split diseases whose seed-finding LR direction
        opposes the group majority (opposite-direction sub-axis)."""
        dirs = {d: (1 if cand.get(d, 1.0) > 1.0 else -1 if cand.get(d, 1.0) < 1.0
                    else 0) for d in diseases}
        nz = [v for v in dirs.values() if v != 0]
        if len(set(nz)) < 2:
            return []  # all same direction (or unknown) → no split needed
        majority = 1 if sum(1 for v in nz if v > 0) >= sum(1 for v in nz if v < 0) else -1
        minority = [d for d, v in dirs.items() if v != 0 and v != majority]
        if not minority:
            return []
        kws = sorted({d for d in minority} | _tokens(val))
        return [{"name": f"{val} — opposite-direction subset ({axis})",
                 "member_keywords": kws, "_entities": minority}]
