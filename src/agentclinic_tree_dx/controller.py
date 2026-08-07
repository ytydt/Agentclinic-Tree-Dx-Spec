from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path

from .action_bundler import build_bundle
from .config import ControllerConfig
from .prompting import load_module_prompt
from .state import (
    Branch,
    CandidateLeaf,
    DeliberationState,
    EvidenceItem,
    DiagnosticState,
    RootNode,
    TerminationState,
)
from .update_router import choose_update_method
from .updater import calculator_update, ordinal_update, rule_based_update
from .tools.calculator_router import naive_calculator_router
from .tools.knowledge_router import naive_knowledge_router

_logger = logging.getLogger(__name__)


# ── Demographics / negation detection (finding-LR hygiene) ──────────────────
# Age & sex are EPIDEMIOLOGY (they shift the PRIOR), not findings with an LR.
# Routing "55-year-old man" through the finding→LR path produced spurious
# signals; we detect & exclude such facts so the structured age/sex prior
# (PriorModifier) handles them instead.
_DEMOGRAPHIC_RE = re.compile(
    r"^\s*(?:a\s+)?\d{1,3}[\s-]*(?:year|yr|yo|y/o|month|week|day)s?[\s-]*old\b"
    r"|^\s*(?:age|sex|gender|race|ethnicity)\s*[:=]"
    r"|^\s*\d{1,3}\s*(?:m|f|male|female)\s*$",
    re.IGNORECASE,
)

# Free-text negation / "within normal limits" statements. These are PERTINENT
# NEGATIVES: literature (PMC3427763; AAFP 2009) shows they legitimately lower
# the posterior of branches that (near-)always produce the named abnormality
# (LR- channel). We route the NEGATED phenotype to the rule-out path instead
# of mis-scoring it as a PRESENT finding.
_NEGATION_RE = re.compile(
    r"\b(?:no(?:\s+evidence\s+of|\s+sign[s]?\s+of)?|without|absent|absence\s+of|"
    r"negative\s+for|denies|free\s+of|non-tender|nontender|unremarkable|"
    r"within\s+normal\s+limits|wnl)\b",
    re.IGNORECASE,
)
# Generic "<system> exam (is) unremarkable / within normal limits": the system
# itself names the negated abnormality family. Curated, high-Sn systems only.
_NORMAL_SYSTEM_NEGATES: dict[str, list[str]] = {
    "cardiopulmonary": ["Heart murmur", "Abnormal lung auscultation", "Respiratory distress"],
    "cardiac": ["Heart murmur", "Arrhythmia"],
    "cardiovascular": ["Heart murmur", "Arrhythmia"],
    "pulmonary": ["Abnormal lung auscultation", "Respiratory distress"],
    "respiratory": ["Abnormal lung auscultation", "Respiratory distress"],
    "lung": ["Abnormal lung auscultation"],
    "abdominal": ["Abdominal tenderness", "Hepatomegaly", "Splenomegaly", "Abdominal mass"],
    "abdomen": ["Abdominal tenderness", "Hepatomegaly", "Splenomegaly"],
    "neurologic": ["Focal neurologic deficit", "Abnormal reflex"],
    "neurological": ["Focal neurologic deficit", "Abnormal reflex"],
    "lymph": ["Lymphadenopathy"],
    "lymphatic": ["Lymphadenopathy"],
    "skin": ["Abnormality of the skin"],
    "dermatologic": ["Abnormality of the skin"],
}


def _is_demographic_fact(text: str) -> bool:
    return bool(_DEMOGRAPHIC_RE.search(text or ""))


_REP_DISEASE_DIRECTIVE = (
    "\n\nADDITIONAL REQUIRED FIELD (knowledge-lookup only): add to EACH branch a\n"
    '"representative_diseases" array of 1-4 SPECIFIC, CANONICAL disease entities the\n'
    "broad family covers, named as for a textbook/PubMed lookup (e.g. family\n"
    '"Myeloid Neoplasm with Increased Blasts" → ["acute myeloid leukemia",\n'
    '"myelodysplastic syndrome with excess blasts", "CML blast crisis"]). These are\n'
    "used ONLY for knowledge lookup; the branch LABEL must still stay broad. Put the\n"
    "single most likely specific entity FIRST. Use real disease names, not compound\n"
    "phrases. This field is ADDITIVE — do not change any other field or your branch\n"
    "structure because of it."
)


_BRANCH_KNOWLEDGE_DIRECTIVE = (
    "\n\n═══ KB-ANCHORED PARTITION (Mode A — FOLLOW WHEN PAYLOAD HAS "
    "'branch_knowledge') ═══\n"
    "The payload field 'branch_knowledge' provides a knowledge-derived L1 frame:\n"
    "  - l1_classification_axis : the SINGLE axis all your Level-1 siblings MUST\n"
    "    share (do not mix axes at L1).\n"
    "  - mandatory_coverage     : the MECE list of L1 domains you MUST cover. Emit\n"
    "    one Level-1 branch per domain (you may MERGE two only if truly the same\n"
    "    axis bucket, and may ADD an extra domain if clinically required). Do NOT\n"
    "    drop a mandatory domain.\n"
    "  - candidate_entities_by_domain : SPECIFIC diseases that live UNDER each\n"
    "    domain. These are for sub-branch refinement (L2/L3) ONLY — NEVER use a\n"
    "    specific entity as an L1 label. Keep L1 labels at the domain/family\n"
    "    granularity named in mandatory_coverage.\n"
    "Set each branch's classification_axis to l1_classification_axis. This frame\n"
    "is ADDITIVE: keep the normal JSON schema; just ensure coverage + single axis."
)

# §32 recall-hints directive: the payload carries a FLAT candidate_diseases list
# (retrieval hints), NOT a partition. The LLM owns the single-axis MECE partition;
# the hints only widen its recall so a long-tail gold is not missed.
_BRANCH_RECALL_HINTS_DIRECTIVE = (
    "\n\n═══ RETRIEVAL CANDIDATE HINTS (§32 — FOLLOW WHEN PAYLOAD HAS "
    "'candidate_diseases') ═══\n"
    "'branch_knowledge.candidate_diseases' is a ranked list of SPECIFIC diseases "
    "surfaced by multi-source retrieval (case reports + guidelines + a differential "
    "LLM), INCLUDING rare/long-tail causes. These are HINTS, not labels and not a "
    "partition:\n"
    "  - YOU design the single-axis MECE Level-1 family partition yourself (obey "
    "the MANDATORY SINGLE-AXIS RULE above). Do NOT emit any specific disease as an "
    "L1 label.\n"
    "  - Use the hints ONLY to make your partition COMPLETE: ensure that every "
    "plausible candidate has a reachable Level-1 family (if a plausible hint fits "
    "none of your families, widen a family or add one so it is covered by mechanism/"
    "category — never by name).\n"
    "  - Ignore hints that are implausible for this presentation. Keep 5-9 broad "
    "families + optional residual OTHER.\n"
    "  - If 'branch_knowledge.uncovered_candidates' is present, your PREVIOUS "
    "partition left those plausible diseases with NO home family. Revise the "
    "partition so EACH has a reachable Level-1 family — widen an existing family "
    "or add ONE more — while keeping the SAME single axis and MECE (do not add a "
    "disease-named branch; use a broader mechanism/category family)."
)


def _clean_representative_diseases(raw) -> list[str]:
    """Normalise a BranchCreator ``representative_diseases`` field into a short,
    de-duplicated list of specific disease strings. Tolerant of None / str /
    list; drops empties and the placeholder text from the prompt template."""
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        s = str(item).strip()
        low = s.lower()
        if not s or low in seen:
            continue
        if "specific disease" in low or "specific entity" in low:  # template placeholder
            continue
        seen.add(low)
        out.append(s)
    return out[:4]


def _extract_negated_phenotype(text: str) -> str | None:
    """If ``text`` is a pertinent-negative statement, return the negated
    abnormality phrase (e.g. "no lymphadenopathy" → "lymphadenopathy"); else
    None. Conservative: only fires on explicit negation cues."""
    t = (text or "").strip()
    if not _NEGATION_RE.search(t):
        return None
    low = t.lower()
    # Generic "<system> ... within normal limits / unremarkable".
    if re.search(r"within\s+normal\s+limits|unremarkable|\bwnl\b", low):
        for system in _NORMAL_SYSTEM_NEGATES:
            if system in low:
                return f"__system__:{system}"
    # Explicit "no/without/negative for <phenotype>".
    m = re.search(
        r"\b(?:no\s+evidence\s+of|no\s+sign[s]?\s+of|negative\s+for|"
        r"without|absence\s+of|free\s+of|no)\s+([a-z][a-z \-/]{2,40})",
        low,
    )
    if m:
        phrase = m.group(1).strip(" .,-/")
        # Drop trailing filler.
        phrase = re.split(r"\b(?:and|or|but|with|on|in|at|is|are|was|were)\b", phrase)[0].strip()
        if len(phrase) >= 3:
            return phrase
    return None


class LLMProtocolError(Exception):
    """Raised when an LLM module keeps violating its output contract after the
    configured number of retries. Carries enough context for the harness to log
    the failure and skip the case for later investigation."""

    def __init__(self, module_name: str, reason: str, last_result=None):
        self.module_name = module_name
        self.reason = reason
        self.last_result = last_result
        super().__init__(
            f"[{module_name}] protocol violation after retries: {reason}"
        )


# ── Output-contract validators ────────────────────────────────────────────────
# Each returns (ok: bool, reason: str). They check ONLY the structural contract
# the controller relies on for non-crashing parsing — not clinical correctness.

def _clean_salient_findings(items, *, limit: int = 8) -> list[str]:
    """Normalise the RootSelector ``salient_findings`` list: coerce to short,
    de-duplicated, non-empty strings. These are the concrete second-entrance
    retrieval terms — kept short (single findings, not sentences) so each is a
    focused query. Fail-open: returns [] on any malformed input."""
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(items, (list, tuple)):
        return out
    for it in items:
        s = str(it).strip()
        if not s:
            continue
        # keep it a *finding*, not a paragraph: cap at ~12 words
        if len(s.split()) > 12:
            s = " ".join(s.split()[:12])
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _validate_root_selector(result: dict, *, max_words: int = 40):
    if not isinstance(result, dict):
        return False, "response is not a JSON object"
    label = result.get("root_label") or result.get("label")
    if not label or not isinstance(label, str) or not label.strip():
        return False, "missing/empty 'root_label'"
    n = len(label.split())
    if n > max_words:
        return False, (f"'root_label' is {n} words (> {max_words}); it must be a "
                       f"concise syndrome frame, not an enumeration of findings")
    return True, ""


def _validate_branch_creator(result: dict):
    if not isinstance(result, dict):
        return False, "response is not a JSON object"
    raw = result.get("branches", None)
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list) or not raw:
        return False, "missing/empty 'branches' list"
    for i, b in enumerate(raw):
        if not isinstance(b, dict):
            return False, f"branch[{i}] is not an object"
        if not b.get("id"):
            return False, f"branch[{i}] missing required 'id'"
        if not b.get("label"):
            return False, f"branch[{i}] missing required 'label'"
    return True, ""


def _validate_talp(result: dict):
    if not isinstance(result, dict):
        return False, "response is not a JSON object"
    leaves = result.get("candidate_leaves_ranked", None)
    if not isinstance(leaves, list):
        return False, "missing 'candidate_leaves_ranked' list"
    # Empty list is allowed (a turn may legitimately propose no new leaves), but
    # every leaf present MUST carry the keys the controller indexes into.
    for i, x in enumerate(leaves):
        if not isinstance(x, dict):
            return False, f"candidate_leaves_ranked[{i}] is not an object"
        for k in ("branch_id", "type", "content"):
            if k not in x or x.get(k) in (None, ""):
                return False, f"candidate_leaves_ranked[{i}] missing required '{k}'"
        if "score" not in x:
            return False, f"candidate_leaves_ranked[{i}] missing required 'score'"
    return True, ""


def _validate_answer_mapper(result: dict):
    if not isinstance(result, dict):
        return False, "response is not a JSON object"
    if not (result.get("final_answer") or "").strip():
        return False, "missing/empty 'final_answer'"
    return True, ""


def _validate_termination(result: dict):
    if not isinstance(result, dict):
        return False, "response is not a JSON object"
    if "ready_to_stop" not in result:
        return False, "missing required 'ready_to_stop'"
    return True, ""


def _validate_post_update_reviser(result: dict):
    if not isinstance(result, dict):
        return False, "response is not a JSON object"
    decisions = result.get("branch_decisions", None)
    if not isinstance(decisions, list):
        return False, "missing 'branch_decisions' list"
    for i, d in enumerate(decisions):
        if not isinstance(d, dict) or not d.get("branch_id"):
            return False, f"branch_decisions[{i}] missing required 'branch_id'"
        if not d.get("decision"):
            return False, f"branch_decisions[{i}] missing required 'decision'"
    return True, ""


def _validate_subbranch(result: dict):
    if not isinstance(result, dict):
        return False, "response is not a JSON object"
    # No expansion is a valid outcome; only validate items that ARE present.
    if not result.get("needs_expansion", True):
        return True, ""
    subs = result.get("sub_branches", None)
    if not isinstance(subs, list):
        return False, "missing 'sub_branches' list while needs_expansion is true"
    for i, b in enumerate(subs):
        if not isinstance(b, dict) or not b.get("id") or not b.get("label"):
            return False, f"sub_branches[{i}] missing required 'id'/'label'"
    return True, ""


class AgentClinicTreeController:
    def __init__(self, env, llm=None, calculator_router=None, knowledge_router=None, config=None):
        self.env = env
        self.llm = llm
        self.calculator_router = calculator_router or naive_calculator_router
        self.knowledge_router = knowledge_router or naive_knowledge_router
        self.config = config or ControllerConfig()
        self._l2_mode = str(getattr(
            self.config, "l2_branch_generation_mode", "none"
        ) or "none").strip().lower()
        if self._l2_mode not in {"none", "per_parent", "reuse_l1"}:
            raise ValueError(
                "l2_branch_generation_mode must be one of: "
                "none, per_parent, reuse_l1"
            )
        if int(getattr(self.config, "l2_recall_candidate_budget", 24)) < 1:
            raise ValueError("l2_recall_candidate_budget must be >= 1")
        if int(getattr(self.config, "l2_recall_snippet_budget", 12)) < 1:
            raise ValueError("l2_recall_snippet_budget must be >= 1")
        # L2-only operational state. It is deliberately kept off DiagnosticState
        # projections so existing L1 prompt payloads remain unchanged.
        self._l2_frozen_recall_asset: dict | None = None
        self._l2_reuse_assignment_cache: dict[str, list[dict]] | None = None
        self._l2_reuse_fragment_cache: dict[str, list[dict]] | None = None
        self._l2_reuse_assignment_case: str | None = None
        self._l2_recall_audit: list[dict] = []
        self._l2_reuse_mapping_calls: int = 0
        self._l2_parent_retrieval_calls: int = 0
        self._knowledge_retriever = None
        self._prior_modifier = None
        self._patient_age_sex: tuple[int | None, str | None] = (None, None)
        disc_profile = str(getattr(
            self.config, "talp_disc_profile", "p5_headline"
        ) or "off").strip().lower()
        p5_has_assets = disc_profile == "p5_headline" and any((
            self.config.dxs_common_json,
            self.config.dxs_rare_json,
            self.config.primekg_csv,
            self.config.lr_cache_json,
            self.config.pathognomonic_markers_json,
            self.config.diagnostic_markers_json,
        ))
        if self.config.enable_knowledge_injection or p5_has_assets:
            self._knowledge_retriever = self._init_knowledge_layer()
        self._disc_audit_lock = threading.Lock()
        self._discrimination_runtime = self._init_discrimination_runtime()
        # §23.14 (Mode A): syndrome→axis table for KB-anchored branch generation.
        # Loaded only when enabled; otherwise stays None and the branch path is
        # byte-identical to the legacy pure-LLM behaviour.
        self._syndrome_axis_map = None
        if self.config.enable_branch_knowledge:
            self._syndrome_axis_map = self._init_syndrome_axis_map()
        # Dual-entrance case-report branch source (long-tail recall augmentation).
        # Only built when branch knowledge is on AND the flag is set; otherwise
        # None and branch anchoring is byte-identical to the CPG-only path.
        self._case_report_source = None
        if ((self.config.enable_branch_knowledge
             or self._l2_mode in {"per_parent", "reuse_l1"})
                and getattr(self.config, "enable_case_report_branch_source", False)):
            self._case_report_source = self._init_case_report_source()
        # Step-3 CPG dual-entrance source (syndrome ∪ salient over CPG/StatPearls).
        # Only built when branch knowledge is on AND the flag is set; otherwise
        # None and the CPG main path stays marker/taxonomy-only.
        self._cpg_branch_source = None
        if ((self.config.enable_branch_knowledge
             or self._l2_mode in {"per_parent", "reuse_l1"})
                and getattr(self.config, "enable_cpg_branch_source", False)):
            self._cpg_branch_source = self._init_cpg_branch_source()
        # §32 recall-hints mode reuses the SAME entrance sources but bypasses the
        # axis_map projection (the sources are already built above from their own
        # enable flags — no extra construction needed here).

    @staticmethod
    def _normalise_l2_recall_asset(asset) -> dict:
        """Validate and freeze a serialisable recall-asset envelope.

        Gold/answer-bearing fields are rejected rather than silently ignored.
        Records may be strings or mappings with ``disease``/``entity``/
        ``diagnosis``, ``source_rank`` and ``provenance``. Structured knowledge
        fragments are retained under ``knowledge_fragments``.
        """
        forbidden = {"gold", "gold_diagnosis", "gold_label", "answer",
                     "correct_answer", "target_diagnosis"}
        envelope: dict = {}
        if isinstance(asset, dict):
            bad = forbidden.intersection(str(k).strip().lower() for k in asset)
            if bad:
                raise ValueError(
                    "L2 recall asset must not contain gold/answer fields: "
                    + ", ".join(sorted(bad))
                )
            envelope = {
                str(key): value for key, value in asset.items()
                if key not in {
                    "candidates", "recall_candidates", "candidate_diseases",
                    "knowledge_fragments", "fragments",
                }
            }
            raw_candidates = (
                asset.get("candidates") or asset.get("recall_candidates")
                or asset.get("candidate_diseases") or []
            )
            raw_fragments = (
                asset.get("knowledge_fragments") or asset.get("fragments") or []
            )
        else:
            raw_candidates = asset
            raw_fragments = []
        if not isinstance(raw_candidates, (list, tuple)):
            raise TypeError("L2 recall asset must be a list or candidate mapping")

        out: list[dict] = []
        by_key: dict[str, dict] = {}
        for rank, raw in enumerate(raw_candidates, start=1):
            if isinstance(raw, str):
                disease = raw.strip()
                row = {"disease": disease}
            elif isinstance(raw, dict):
                bad = forbidden.intersection(
                    str(k).strip().lower() for k in raw
                )
                if bad:
                    raise ValueError(
                        "L2 recall candidate must not contain gold/answer fields: "
                        + ", ".join(sorted(bad))
                    )
                disease = str(
                    raw.get("disease") or raw.get("entity")
                    or raw.get("diagnosis") or raw.get("name") or ""
                ).strip()
                row = {
                    "disease": disease,
                    "rrf_score": raw.get("rrf_score", raw.get("score", 0.0)),
                    "source_rank": raw.get("source_rank", {}),
                    "provenance": raw.get("provenance", []),
                }
            else:
                continue
            if not disease:
                continue
            key = disease.casefold()
            if key in by_key:
                existing = by_key[key]
                for prov in row.get("provenance", []) or []:
                    if prov not in existing.setdefault("provenance", []):
                        existing["provenance"].append(prov)
                for source, source_rank in (
                    row.get("source_rank", {}) or {}
                ).items():
                    existing.setdefault("source_rank", {}).setdefault(
                        str(source), source_rank
                    )
                continue
            row.setdefault("rrf_score", 0.0)
            row.setdefault("source_rank", {})
            row.setdefault("provenance", [])
            row["asset_rank"] = rank
            # Round-trip now so callers cannot mutate the frozen controller copy
            # and every audit/payload remains JSON serialisable.
            safe = json.loads(json.dumps(row, default=str))
            by_key[key] = safe
            out.append(safe)
        fragments: list[dict] = []
        seen_fragments: set[str] = set()
        if isinstance(raw_fragments, (list, tuple)):
            for index, raw in enumerate(raw_fragments):
                if not isinstance(raw, dict):
                    continue
                source = str(raw.get("source", "")).strip()
                title = str(raw.get("title", "")).strip()
                content = str(raw.get("content", "")).strip()
                fragment_id = str(
                    raw.get("id") or raw.get("chunk_id")
                    or f"{source}::{index}"
                ).strip()
                if not content:
                    continue
                key = fragment_id or f"{source}|{title}|{content[:80]}"
                if key in seen_fragments:
                    continue
                seen_fragments.add(key)
                fragments.append({
                    "source": source,
                    "title": title,
                    "content": content,
                    "id": fragment_id,
                })
        safe_envelope = json.loads(json.dumps(envelope, default=str))
        safe_envelope["candidates"] = out
        safe_envelope["knowledge_fragments"] = fragments
        return safe_envelope

    def freeze_l2_recall_asset(self, asset) -> dict:
        """Freeze the complete case-level asset used by ``reuse_l1`` mode."""
        frozen = self._normalise_l2_recall_asset(asset)
        self._l2_frozen_recall_asset = frozen
        self._l2_reuse_assignment_cache = None
        self._l2_reuse_fragment_cache = None
        self._l2_reuse_assignment_case = None
        return json.loads(json.dumps(frozen))

    # Friendly setter alias for integrations that do not use "freeze" wording.
    set_l2_recall_asset = freeze_l2_recall_asset

    def get_l2_recall_audit(self) -> list[dict]:
        """Return an isolated, JSON-serialisable copy of the L2 recall audit."""
        return json.loads(json.dumps(self._l2_recall_audit, default=str))

    @staticmethod
    def _resolve_disc_path(path: str | None) -> str:
        """Resolve profile defaults from the repository, preserving absolutes."""
        if not path:
            return ""
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return str(candidate)
        return str(Path(__file__).resolve().parents[2] / candidate)

    def _init_discrimination_runtime(self):
        """Build the selected production profile; P5 asset absence fails open."""
        from .discrimination import (
            DiscriminationRuntime,
            config_for_profile,
            validate_manifest,
        )

        profile = str(getattr(
            self.config, "talp_disc_profile", "p5_headline"
        ) or "off").strip().lower()
        if profile == "off":
            return None
        if profile not in {"p5_headline", "g2ur"}:
            raise ValueError(
                "talp_disc_profile must be one of: off, p5_headline, g2ur"
            )

        if profile == "p5_headline":
            manifest = self._resolve_disc_path(
                getattr(self.config, "talp_disc_p5_manifest", None)
            )
            if manifest and Path(manifest).is_file():
                validation = validate_manifest(
                    manifest,
                    verify_assets=bool(getattr(
                        self.config, "talp_disc_verify_manifest_assets", False
                    )),
                    root=Path(__file__).resolve().parents[2],
                )
                validation.require_valid()
            elif manifest:
                # The production default names the frozen asset set, but unit
                # fixtures and minimal installs need not ship it.
                _logger.warning(
                    "P5 discrimination manifest missing; continuing fail-open: %s",
                    manifest,
                )
            cfg = config_for_profile("p5_headline", p5kg_manifest=manifest)
            return DiscriminationRuntime(
                "p5_headline",
                config=cfg,
                legacy_provider=self._legacy_discrimination_evidence,
                cache_path=self._resolve_disc_path(getattr(
                    self.config, "talp_disc_cache_path", None
                )),
            )

        claims = self._resolve_disc_path(
            getattr(self.config, "talp_disc_research_claims", None)
        )
        manifest = self._resolve_disc_path(
            getattr(self.config, "talp_disc_research_manifest", None)
        )
        cfg = config_for_profile(
            "g2ur",
            research_claims=claims,
            p5kg_research_manifest=manifest,
        )
        return DiscriminationRuntime(
            "g2ur",
            config=cfg,
            verify_manifest_assets=bool(getattr(
                self.config, "talp_disc_verify_manifest_assets", False
            )),
            manifest_root=str(Path(__file__).resolve().parents[2]),
            cache_path=self._resolve_disc_path(getattr(
                self.config, "talp_disc_cache_path", None
            )),
        )

    def _legacy_discrimination_evidence(self, finding, candidates, _disc_cfg):
        """Adapt DxFeatureRetriever LR evidence to the profile runtime contract."""
        if self._knowledge_retriever is None:
            return []
        try:
            reference = self._knowledge_retriever.get_lr_reference(
                finding, candidates, fast=True
            )
        except Exception as exc:
            _logger.warning(
                "P5 discrimination evidence failed for %r: %s", finding, exc
            )
            return []

        rows = []
        for candidate, entry in (reference.get("lr_data") or {}).items():
            if not isinstance(entry, dict):
                continue
            signal = self._kb_entry_to_signal(entry)
            if signal is None:
                continue
            effect = (
                "argues_against_candidate"
                if "against" in signal[0]
                else "supports_candidate"
            )
            source = str(entry.get("source") or reference.get("source") or "legacy")
            rows.append({
                "chunk_id": "",
                "claim_id": "",
                "source": source,
                "candidate": candidate,
                "candidate_effect": effect,
                "text": str(entry.get("note") or "")[:400],
                "score": float(signal[2]),
                "provenance": [{
                    "provider": "DxFeatureRetriever",
                    "source": source,
                    "finding": finding,
                    "lr_positive": signal[1],
                    "confidence": entry.get("confidence"),
                }],
            })
        return rows

    def _init_knowledge_layer(self):
        """Lazily initialise the DxFeatureRetriever from config paths."""
        from .knowledge.dx_feature_retriever import DxFeatureRetriever
        from .knowledge.dx_discriminator_index import DxDiscriminatorIndex
        from .knowledge.primekg_index import PrimeKGIndex
        from .knowledge.lr_retriever import LRRetriever
        from .knowledge.evidence_matcher import EvidenceMatcher
        from .knowledge.disease_name_resolver import DiseaseNameResolver

        dxs = None
        primekg = None
        lr = None
        matcher = None

        if self.config.dxs_common_json:
            try:
                dxs = DxDiscriminatorIndex.from_files(
                    self.config.dxs_common_json,
                    self.config.dxs_rare_json,
                )
            except Exception as e:
                _logger.warning("Failed to load DxS index: %s", e)

        if self.config.primekg_csv:
            try:
                primekg = PrimeKGIndex.from_csv(self.config.primekg_csv)
            except Exception as e:
                _logger.warning("Failed to load PrimeKG: %s", e)

        if self.config.lr_cache_json:
            try:
                lr = LRRetriever.from_cache(self.config.lr_cache_json)
                # §25.2(#1): opt-in retrieval-priority fix (gated; default OFF).
                lr._hpo_exact_priority = getattr(
                    self.config, "enable_hpo_exact_priority", False)
                # §25.2(#2): opt-in finding-match guards (gated; default OFF).
                lr._match_guards = getattr(
                    self.config, "enable_finding_match_guards", False)
            except Exception as e:
                _logger.warning("Failed to load LR cache: %s", e)

        # Build phenotype vocabulary from both layers for EvidenceMatcher
        vocab: set[str] = set()
        if dxs:
            for phenos in dxs._disease_phenotypes.values():
                vocab.update(phenos)
        if primekg:
            for phenos in primekg.disease_phenotype_pos.values():
                vocab.update(phenos)
        emb_index = None
        if lr and lr._embedding_index and lr._embedding_index.is_ready:
            emb_index = lr._embedding_index
        if vocab:
            matcher = EvidenceMatcher(sorted(vocab), embedding_index=emb_index)
            _logger.info("EvidenceMatcher vocabulary: %d phenotypes (embedding=%s)",
                         len(vocab), "yes" if emb_index else "no")

        # Disease name resolver with UMLS CUI bridging
        resolver = DiseaseNameResolver()
        if self.config.doclogica_cache_json:
            try:
                resolver.load_umls_from_doclogica(self.config.doclogica_cache_json)
            except Exception as e:
                _logger.warning("Failed to load UMLS from docLogica: %s", e)
        bridge_path = Path(self.config.lr_cache_json).parent / "disease_name_bridge.json" if self.config.lr_cache_json else None
        if bridge_path and bridge_path.exists():
            try:
                resolver.load_bridge(bridge_path)
            except Exception as e:
                _logger.warning("Failed to load disease name bridge: %s", e)
        # Mechanism / morphology → canonical-disease normalisation (closes the
        # structural "disease hole" where options phrased as a mechanism — e.g.
        # "Increased parathyroid hormone", "Beta cell tumor" — have no entry in
        # the disease-keyed cache).
        mech_path = self.config.mechanism_to_disease_json
        if not mech_path and self.config.lr_cache_json:
            cand = Path(self.config.lr_cache_json).parent / "mechanism_to_disease.json"
            mech_path = str(cand) if cand.exists() else None
        if mech_path and Path(mech_path).exists():
            try:
                resolver.load_mechanism_map(mech_path)
            except Exception as e:
                _logger.warning("Failed to load mechanism→disease map: %s", e)

        # Structured age/sex → incidence PRIOR modifier (epidemiology shifts the
        # prior, not the likelihood). Auto-discovered next to lr_cache_json.
        self._prior_modifier = None
        self._patient_age_sex: tuple[int | None, str | None] = (None, None)
        if self.config.enable_age_prior:
            try:
                from .knowledge.prior_modifier import PriorModifier
                ap_path = self.config.age_sex_incidence_json
                if not ap_path and self.config.lr_cache_json:
                    cand = Path(self.config.lr_cache_json).parent / "age_sex_incidence.json"
                    ap_path = str(cand) if cand.exists() else None
                if ap_path and Path(ap_path).exists():
                    pm = PriorModifier()
                    pm.load(ap_path)
                    if pm.loaded:
                        self._prior_modifier = pm
            except Exception as e:
                _logger.warning("Failed to load age/sex prior modifier: %s", e)

        # ChainDiscoverer LLM callback (Phase 3c RAG)
        chain_fn = None
        if self.config.enable_chain_discoverer and self.llm is not None:
            chain_fn = self._make_chain_discoverer_fn()

        # Layer 3a: StatPearls/Textbooks FAISS RAG
        rag = None
        if self.config.rag_index_dir:
            try:
                from .knowledge.rag_retriever import RAGRetriever
                rag = RAGRetriever(self.config.rag_index_dir)
                if not rag.is_ready:
                    rag = None
                elif getattr(self.config, "enable_lr_clean", False):
                    # §27.6(1): purify (strip ungrounded heuristic LR) at live RAG.
                    rag._lr_purify = True
                elif getattr(self.config, "enable_lr_detox", False):
                    # §26.5(1): neutralise fabricated LRs at the live RAG path.
                    rag._lr_detox = True
            except Exception as e:
                _logger.warning("Failed to load RAG index: %s", e)

        # Layer 3b: PubMed E-utilities
        pubmed = None
        if self.config.enable_pubmed_fallback:
            try:
                from .knowledge.pubmed_retriever import PubMedRetriever
                pubmed = PubMedRetriever(
                    api_key=self.config.pubmed_api_key,
                )
            except Exception as e:
                _logger.warning("Failed to init PubMed retriever: %s", e)

        # B3: Pathognomonic / diagnostic marker index
        diagnostic_markers = None
        if self.config.pathognomonic_markers_json or self.config.diagnostic_markers_json:
            try:
                from .knowledge.diagnostic_marker_index import DiagnosticMarkerIndex
                diagnostic_markers = DiagnosticMarkerIndex(
                    pathognomonic_markers_path=self.config.pathognomonic_markers_json,
                    diagnostic_markers_path=self.config.diagnostic_markers_json,
                    primekg_index=primekg,
                    auto_ambiguity_map_path=self.config.auto_ambiguity_map_json,
                    embedding_index=emb_index,  # 16.9.8 T1b (lazy; rare branch)
                )
            except Exception as e:
                _logger.warning("Failed to load diagnostic markers: %s", e)

        # B1: Lab value normalizer
        finding_normalizer = None
        if self.config.lab_reference_ranges_json and self.config.loinc2hpo_json:
            try:
                from .knowledge.finding_normalizer import FindingNormalizer
                finding_normalizer = FindingNormalizer(
                    lab_ranges_path=self.config.lab_reference_ranges_json,
                    loinc2hpo_path=self.config.loinc2hpo_json,
                    unit_conversions_path=self.config.unit_conversions_json,
                )
            except Exception as e:
                _logger.warning("Failed to load FindingNormalizer: %s", e)

        # SNOMED CT layer: synonym bridging (+ optional syndrome-chain relations)
        snomed = None
        if self.config.snomed_concepts_json and self.config.snomed_term_index_json:
            try:
                from .knowledge.snomed_index import SnomedIndex
                snomed = SnomedIndex.from_files(
                    self.config.snomed_concepts_json,
                    self.config.snomed_term_index_json,
                    self.config.snomed_relations_json,
                )
            except Exception as e:
                _logger.warning("Failed to load SnomedIndex: %s", e)

        # Tier-2 LR cache: persistent memoization of RAG-quantified LRs (kept
        # separate from the curated primary cache). Only meaningful when RAG
        # fallback is active.
        secondary_lr_cache = None
        # §30: explicit kill-switch — force every RAG LR to be RE-COMPUTED from
        # raw data (no tier-2 read, no write). Removes stale cross-generation
        # cache entries (computed under older/buggy code) that would otherwise
        # bypass the fixed quantification path, so a fix's true effect is
        # measured. Defaults ON (cache enabled) for normal runs.
        if self.config.enable_lr_rag_fallback and getattr(
                self.config, "enable_secondary_lr_cache", True):
            try:
                from .knowledge.secondary_lr_cache import SecondaryLRCache
                sc_path = self.config.secondary_lr_cache_json
                if not sc_path and self.config.lr_cache_json:
                    sc_path = str(Path(self.config.lr_cache_json).parent / "rag_lr_secondary_cache.json")
                ns = getattr(self.config, "secondary_lr_cache_namespace", "") or ""
                if sc_path and ns:
                    # §30 per-experiment isolation: a WRITABLE per-arm cache
                    # derived from the BASE path. It deliberately BYPASSES the
                    # shared read-only .clean/.detox artifacts (those are global);
                    # the arm's clean/detox transforms still apply LIVE at write
                    # time, so each arm is fully independent and only its own reps
                    # share. Seeded empty → arm recomputes under its own config.
                    base = str(sc_path)
                    sc_path = (base[:-5] + f".ns_{ns}.json") if base.endswith(".json") else base + f".ns_{ns}.json"
                    _logger.info("§30 cache namespace=%r → isolated per-arm cache %s", ns, sc_path)
                else:
                    # §27.6(1): prefer the cleaned secondary cache when clean is on
                    # (takes precedence over detox); else §26.5(1) detox cache.
                    if sc_path and getattr(self.config, "enable_lr_clean", False):
                        clean_path = str(sc_path)[:-5] + ".clean.json" if str(sc_path).endswith(".json") else str(sc_path) + ".clean.json"
                        if Path(clean_path).exists():
                            sc_path = clean_path
                            _logger.info("LR clean ON: using purified secondary cache %s", sc_path)
                    elif sc_path and getattr(self.config, "enable_lr_detox", False):
                        detox_path = str(Path(sc_path).with_suffix(".detox.json"))
                        if Path(detox_path).exists():
                            sc_path = detox_path
                            _logger.info("LR detox ON: using detoxed secondary cache %s", sc_path)
                if sc_path:
                    secondary_lr_cache = SecondaryLRCache(sc_path)
                    # §30: only register write-back flush for a WRITABLE cache;
                    # read-only offline artifacts (*.clean/*.detox) must not be
                    # written by concurrent eval.
                    if not getattr(secondary_lr_cache, "read_only", False):
                        import atexit
                        atexit.register(secondary_lr_cache.flush)
            except Exception as e:
                _logger.warning("Failed to init SecondaryLRCache: %s", e)
        elif self.config.enable_lr_rag_fallback:
            _logger.info("§30: secondary LR cache DISABLED — RAG LRs recomputed "
                         "from raw data every time (no tier-2 read/write).")

        retriever = DxFeatureRetriever(
            dxs_index=dxs,
            primekg_index=primekg,
            lr_retriever=lr,
            evidence_matcher=matcher,
            name_resolver=resolver,
            chain_discoverer_fn=chain_fn,
            rag_retriever=rag,
            pubmed_retriever=pubmed,
            diagnostic_marker_index=diagnostic_markers,
            finding_normalizer=finding_normalizer,
            snomed_index=snomed if self.config.enable_snomed_synonym_bridge else None,
            secondary_lr_cache=secondary_lr_cache,
        )
        # §25.2(#3): opt-in confidence-gated cascade (gated; default OFF).
        retriever._confidence_gated_cascade = getattr(
            self.config, "enable_confidence_gated_cascade", False)
        _logger.info(
            "Knowledge layer initialised: DxS=%s, PrimeKG=%s, LR=%s, "
            "UMLS=%s, ChainDiscoverer=%s, RAG=%s, PubMed=%s, DiagMarkers=%s, LabNorm=%s",
            dxs is not None, primekg is not None, lr is not None,
            self.config.doclogica_cache_json is not None,
            chain_fn is not None,
            rag is not None,
            pubmed is not None,
            diagnostic_markers is not None,
            finding_normalizer is not None,
        )
        return retriever

    def _make_chain_discoverer_fn(self):
        """Create a callback that invokes the ChainDiscoverer LLM module."""
        def chain_discoverer(payload):
            prompt_text = load_module_prompt("ChainDiscoverer")
            return self.llm.call_module("ChainDiscoverer", prompt_text, payload)
        return chain_discoverer

    def _in_patch_mode(self) -> bool:
        return self.config.execution_mode == "agentclinic_physician_patch"

    def _in_sdbench_mode(self) -> bool:
        return self.config.execution_mode == "sdbench_patch"

    def _in_static_qa_mode(self) -> bool:
        return self.config.execution_mode == "static_diagnosis_qa"

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, state: DiagnosticState):
        partial_mode = bool(getattr(self.config, "partial_flow", False))
        partial_turns: list[dict] = []
        partial_tree_snapshots: dict[str, dict] = {}
        l1_expansion_audit: dict = {}
        if state.max_turn_budget is None:
            state.max_turn_budget = self.config.max_turn_budget
        # Sync depth ceiling into state so LLM prompts can reference it
        state.max_tree_depth = self.config.max_tree_depth

        while True:
            state.timestep += 1
            state.case_summary = self.env.get_case_summary()

            if self._in_static_qa_mode() and state.timestep == 1:
                self.parse_static_vignette(state)
                state.mode_policy = {
                    "benchmark_purity": True,
                    "allow_external_knowledge": self.config.allow_external_knowledge,
                }

            # A. Safety screen
            state.interrupt = self.safety_screen(state)
            if state.interrupt.active:
                self.execute_emergent_actions(state)
                if self.env.patient_still_unstable():
                    continue

            # B. Root selection / revision
            root_needs_revision = state.root_revision_needed
            if state.root is None or root_needs_revision:
                state.root = self.select_root(state)
                state.root_revision_needed = False

            # C. Branch maintenance (Level-1 only)
            if not state.branches or root_needs_revision or self.env.root_changed_materially(state):
                state.branches, state.frontier = self.create_branches(state)

            # Mode-specific deliberation
            if self._in_sdbench_mode():
                self.initialize_sdbench_top3(state)
                state.deliberation = self.run_deliberation(state)
            # Static QA deliberation is disabled pending redesign
            # (see STATIC_QA_DELIBERATION_DESIGN.md).
            # if self._in_static_qa_mode():
            #     state.deliberation = self.run_static_qa_deliberation(state)

            # D-pre. Just-in-Time expansion (§15.1): expand before leaf planning when
            # action selection at parent level would be ambiguous without child detail.
            self.check_just_in_time_expansion(state)
            self.recompute_parent_posteriors(state)

            # D. Candidate generation (TemporaryLeafPlanner)
            candidate_leaves, selected_action = self.plan_temporary_leaves(state)
            state.candidate_leaves = candidate_leaves
            self.update_estimated_remaining_value(state)

            # Mode-specific action override
            if self._in_sdbench_mode() and state.deliberation.consensus_action:
                selected_action = state.deliberation.consensus_action
            # Static QA consensus override disabled (deliberation loop off)
            # if self._in_static_qa_mode() and state.deliberation.consensus_action:
            #     selected_action = state.deliberation.consensus_action

            # D'. Build action bundle (FrontierCoverageBundler)
            bundle, branch_coverage = build_bundle(candidate_leaves, state, self.config)
            # Fallback when bundle is empty: use top candidate or selected_action
            if not bundle:
                if candidate_leaves:
                    bundle = [candidate_leaves[0]]
                elif selected_action:
                    bundle = [_action_dict_to_leaf(selected_action)]
                else:
                    # §30: no candidate action could be generated this turn — the
                    # pipeline recovers with a generic probe but this is a
                    # DEGRADED reasoning path; record it so the final answer is
                    # flagged low-trust rather than silently scored as clean.
                    self._note_program_fault(
                        state, f"empty_bundle_fallback@t{state.timestep}")
                    from .state import CandidateLeaf as _CL
                    fallback_bid = state.frontier[0] if state.frontier else "unknown"
                    bundle = [_CL(
                        leaf_id="fallback::probe",
                        branch_id=fallback_bid,
                        leaf_type="ANALYZE_VIGNETTE",
                        content="Summarize all available evidence and identify which branch best fits.",
                        expected_information_gain=0.3,
                        expected_cost=0.0,
                        expected_delay=0.0,
                        safety_value=0.0,
                        action_separation_value=0.0,
                        total_score=0.3,
                        target_branches={bid: "neutral" for bid in state.frontier},
                        primary_function="differentiate",
                    )]

            # E'. Execute action bundle
            bundle_results = self.execute_action_bundle(state, bundle)

            # F'. Batch evidence annotation
            annotation = self.annotate_evidence_bundle(state, bundle_results)
            # Store branch coverage audit alongside the bundle's primary record
            if state.actions_taken:
                state.actions_taken[-len(bundle)]["branch_coverage"] = branch_coverage

            # Harness-only partial trace checkpoint.  Turn 2 intentionally ends
            # here: the annotation is preserved, but it must not influence
            # probabilities or trigger termination/final answer mapping.
            if (
                partial_mode
                and getattr(self.config, "stop_after_evidence", False)
                and state.timestep >= max(1, int(getattr(self.config, "max_timesteps", 2)))
            ):
                partial_turns.append(
                    self._partial_turn_summary(state, annotation, "post_evidence")
                )
                partial_tree_snapshots[f"after_turn_{state.timestep}_evidence"] = (
                    self._partial_tree_snapshot(state)
                )
                return self._build_partial_trace(
                    state,
                    partial_turns,
                    partial_tree_snapshots,
                    l1_expansion_audit,
                    "max_timesteps_post_evidence",
                )

            # G. Probability update
            # G-pre. Correlated evidence grouper: prevent double-counting when
            # multiple bundle actions produce aligned strong effects on the same branch.
            annotation = self.group_correlated_evidence(annotation, bundle)
            update_method = choose_update_method(annotation)
            self.apply_probability_update(state, annotation, update_method)

            # H. Recompute parent posteriors after update
            self.recompute_parent_posteriors(state)

            # I. Branch-state revision
            self.revise_branch_states(state)

            # ★ J. Structural expansion (ExpansionGate + SubBranchCreator)
            if (
                partial_mode
                and state.timestep == 1
                and getattr(self.config, "force_expand_all_l1", False)
            ):
                l1_expansion_audit = self.force_expand_all_l1(state)
            else:
                self.run_expansion_gate(state)
            self.recompute_parent_posteriors(state)
            self.update_frontier_after_expansion(state)

            # Deterministic reopen overrides
            self._apply_reopen_overrides(state, annotation)

            self.record_differential_history(state)

            # J'. Turn budget accounting
            self.account_turn_budget(state, bundle)

            # Partial mode owns its stopping policy.  In particular, readiness
            # and termination are never allowed to aggregate after turn 1.
            if partial_mode:
                partial_turns.append(
                    self._partial_turn_summary(state, annotation, "turn_complete")
                )
                partial_tree_snapshots[f"after_turn_{state.timestep}"] = (
                    self._partial_tree_snapshot(state)
                )
                if state.timestep >= max(
                    1, int(getattr(self.config, "max_timesteps", 2))
                ):
                    return self._build_partial_trace(
                        state,
                        partial_turns,
                        partial_tree_snapshots,
                        l1_expansion_audit,
                        "max_timesteps",
                    )
                continue

            # K. Termination checks
            if (
                (self._in_patch_mode() or self._in_sdbench_mode() or self._in_static_qa_mode())
                and self.check_diagnosis_readiness(state)
            ):
                state.latest_action_type = "DIAGNOSIS_READY"
                state.benchmark_output_ready = True
                return self.final_aggregate(state)

            state.termination = self.check_termination(state)
            if state.termination.ready_to_stop:
                return self.final_aggregate(state)

            if (
                (self._in_patch_mode() or self._in_sdbench_mode() or self._in_static_qa_mode())
                and state.max_turn_budget
                and state.turn_budget_used >= state.max_turn_budget
            ):
                state.termination = TerminationState(True, "info_exhaustion", "turn budget reached")
                return self.final_aggregate(state)

    def _partial_turn_summary(
        self, state: DiagnosticState, annotation: dict, checkpoint: str
    ) -> dict:
        """Build the bounded action/annotation summary used by harness traces."""
        actions = [
            {
                "action_type": record.get("action_type", ""),
                "content": record.get("content", ""),
                "result_summary": record.get("result_summary", ""),
            }
            for record in state.actions_taken
            if record.get("timestep") == state.timestep
        ]
        return {
            "timestep": state.timestep,
            "checkpoint": checkpoint,
            "actions": actions,
            "annotation": {
                "result_summary": annotation.get("result_summary", ""),
                "major_update": bool(annotation.get("major_update", False)),
                "branch_effects": dict(annotation.get("branch_effects", {})),
                "contradiction_detected": bool(
                    annotation.get("contradiction_detected", False)
                ),
                "reopen_candidates": list(annotation.get("reopen_candidates", [])),
            },
        }

    @staticmethod
    def _partial_tree_snapshot(state: DiagnosticState) -> dict:
        """Return a compact, structured L1/L2-only tree snapshot."""
        levels: dict[str, list[dict]] = {"l1": [], "l2": []}
        for branch in sorted(
            state.branches.values(), key=lambda item: (item.level, item.id)
        ):
            if branch.level not in (1, 2):
                continue
            levels[f"l{branch.level}"].append({
                "id": branch.id,
                "label": branch.label,
                "parent": branch.parent,
                "level": branch.level,
                "status": branch.status,
                "prior": branch.prior,
                "posterior": branch.posterior,
                "children": list(branch.children),
            })
        return levels

    def _build_partial_trace(
        self,
        state: DiagnosticState,
        turns: list[dict],
        tree_snapshots: dict[str, dict],
        expansion_audit: dict,
        stop_reason: str,
    ) -> dict:
        """Assemble a non-final, auditable partial-controller result."""
        return {
            "trace_type": "partial_controller",
            "partial": True,
            "stop_reason": stop_reason,
            "timesteps_completed": state.timestep,
            "turns": turns,
            "tree_snapshots": tree_snapshots,
            "l1_tree": self._partial_tree_snapshot(state)["l1"],
            "l2_tree": self._partial_tree_snapshot(state)["l2"],
            "l1_expansion_audit": expansion_audit,
            "discrimination_audit": list(state.discrimination_audit),
            "answer_mapper_called": False,
        }

    # ------------------------------------------------------------------
    # LLM module dispatch
    # ------------------------------------------------------------------

    def _note_program_fault(self, state, reason: str) -> None:
        """§30: record a RECOVERED program-level degradation on the per-case
        state so the final answer can be flagged low-trust. Genuine (unrecovered)
        program errors are NOT routed here — they propagate to the harness and
        are recorded ERR/PROTO (excluded from scoring). Knowledge-coverage misses
        are NOT faults (they fail-open by design)."""
        try:
            state.program_faults.append(reason)
            _logger.warning("§30 program fault (recovered, answer flagged "
                            "low-trust): %s", reason)
        except Exception:  # pragma: no cover - never let fault-tracking crash a run
            pass

    def _call_module(self, module_name: str, payload, *, validator=None):
        """Dispatch an LLM module call.

        When `validator` is given, the response is checked against its output
        contract. On violation the call is retried (up to
        `config.max_protocol_retries` extra attempts) with a corrective reminder
        injected into the payload; if it still fails, an LLMProtocolError is
        raised so the run aborts cleanly and the harness can record + skip the
        case for later investigation (rather than crashing on a KeyError).
        """
        if self.llm is None:
            return self.env.call_module(module_name, payload)

        prompt_text = load_module_prompt(module_name)
        # C3 AB04/AB06: drop synonym/variant de-dupe guidance in L2RecallCreator
        # while retaining exact-string de-dupe in `_dedupe_l2_subbranches`.
        if (
            module_name == "L2RecallCreator"
            and not getattr(self.config, "tree_semantic_dedupe", True)
        ):
            prompt_text = prompt_text.replace(
                "- De-duplicate synonyms and spelling variants; emit each disease once.\n",
                "- Exact-string duplicates only; do not merge clinical synonyms or "
                "spelling variants that differ as written.\n",
            )
        # §21.10.3: the `representative_diseases` field (Fix A) is gated OUT of the
        # static BranchCreator/SubBranchCreator prompts so the clean baseline is
        # reproducible. Inject the directive ONLY when Fix A is enabled, so asking
        # the LLM for it (which deterministically perturbs branch generation, 5/9→2/9)
        # is strictly opt-in.
        if (module_name in ("BranchCreator", "SubBranchCreator")
                and getattr(self.config, "enable_representative_disease_lr", False)):
            prompt_text = prompt_text + _REP_DISEASE_DIRECTIVE
        # §23.14 (Mode A): inject the KB-anchoring directive ONLY when the payload
        # actually carries a branch_knowledge block, so the OFF path (no block) is
        # byte-identical to the legacy prompt.
        if (module_name == "BranchCreator"
                and isinstance(payload, dict) and payload.get("branch_knowledge")):
            bk = payload["branch_knowledge"]
            # §32: recall-hints block (flat candidate_diseases, no partition) gets
            # the additive hints directive; the legacy coupled block (mandatory_
            # coverage) gets the partition-anchoring directive.
            if isinstance(bk, dict) and bk.get("recall_hints_mode"):
                prompt_text = prompt_text + _BRANCH_RECALL_HINTS_DIRECTIVE
            else:
                prompt_text = prompt_text + _BRANCH_KNOWLEDGE_DIRECTIVE
        if validator is None:
            return self.llm.call_module(module_name, prompt_text, payload)

        attempts = max(0, self.config.max_protocol_retries) + 1
        last_result = None
        last_reason = ""
        call_payload = payload
        for attempt in range(attempts):
            result = self.llm.call_module(module_name, prompt_text, call_payload)
            last_result = result
            ok, reason = validator(result)
            if ok:
                return result
            last_reason = reason
            _logger.warning(
                "Module %s violated output contract (attempt %d/%d): %s",
                module_name, attempt + 1, attempts, reason,
            )
            # Inject a corrective reminder (visible to the model via the payload
            # JSON) so the retry has a chance to comply.
            call_payload = dict(payload)
            call_payload["__protocol_correction__"] = (
                f"Your previous response violated the required output contract: "
                f"{reason}. Return STRICT JSON only, with ALL required fields "
                f"populated and correctly typed."
            )
        raise LLMProtocolError(module_name, last_reason, last_result)

    # ------------------------------------------------------------------
    # Static QA vignette parsing
    # ------------------------------------------------------------------

    def parse_static_vignette(self, state: DiagnosticState) -> None:
        parsed = self._call_module("VignetteParser", {"raw_case": state.case_summary})
        state.static_vignette = (
            parsed.get("vignette")
            or parsed.get("case_text")
            or state.case_summary
        )
        # Support both "question" and "question_stem" keys from LLM
        state.static_question = (
            parsed.get("question")
            or parsed.get("question_stem")
            or ""
        )
        # Normalise options: accept {id, description} or {option, value} or {id, value}
        raw_opts = parsed.get("options", [])
        if raw_opts:
            state.static_options = [
                {
                    "id":          o.get("id") or o.get("option") or str(i),
                    "description": o.get("description") or o.get("value") or "",
                }
                for i, o in enumerate(raw_opts)
            ]
        elif not getattr(state, "static_options", None):
            pre_set = getattr(state, "static_options_raw", None) or []
            state.static_options = [
                {
                    "id": o.get("id", str(i)),
                    "description": o.get("description", o.get("value", "")),
                }
                for i, o in enumerate(pre_set)
            ] if pre_set else []
        # Normalise evidence items: accept multiple LLM-invented key names for content
        evidence_list = (
            parsed.get("evidence_items")
            or parsed.get("evidence")
            or []
        )
        state.static_evidence_items = [
            EvidenceItem(
                id=item.get("id", f"direct::{idx}"),
                kind=item.get("kind", "direct"),
                # Try every common key name an LLM might use for the text content
                content=(
                    item.get("content")
                    or item.get("fact")
                    or item.get("description")
                    or (
                        f"{item['item']}: {item['value']}"
                        if "item" in item and "value" in item
                        else ""
                    )
                    or item.get("text")
                    or ""
                ),
                source_ids=item.get("source_ids", []),
                independent=item.get("independent", True),
                branch_links=item.get("branch_links", {}),
                metadata=item.get("metadata", {}),
            )
            for idx, item in enumerate(evidence_list)
            if item  # skip any None/empty dicts
        ]

    # ------------------------------------------------------------------
    # Safety, root, branches
    # ------------------------------------------------------------------

    def safety_screen(self, state):
        result = self._call_module("SafetyController", state.project_for("SafetyController"))
        return state.interrupt.__class__(
            active=result.get("interrupt_active", False),
            reason=result.get("reason", ""),
            required_actions=result.get("required_actions", []),
        )

    def _root_selector_payload(self, state) -> dict:
        """Build the RootSelector payload with answer options stripped out.

        Exposing static_options (the benchmark answer list) to RootSelector
        creates an anchoring risk: the model may skew its syndrome frame toward
        whichever option label sounds most salient.  We scrub that field and
        replace it with an empty list so the root is derived purely from clinical
        evidence.  The full options remain available to AnswerMapper later.
        """
        payload = state.project_for("RootSelector")
        payload["static_options"] = []      # hide answer choices from root selection
        # Also redact the raw case_summary question/options block if possible:
        # replace the block after the last blank line that precedes "Options:" or
        # "Question:" with a marker so the vignette narrative is preserved but
        # the MCQ stem is removed.
        import re
        if payload.get("case_summary"):
            payload["case_summary"] = re.sub(
                r"\n+(?:Question|Options)\s*:.*",
                "\n[Answer options redacted — use clinical findings only]",
                payload["case_summary"],
                flags=re.DOTALL | re.IGNORECASE,
            )
        return payload

    def select_root(self, state):
        payload = self._root_selector_payload(state)
        root_validator = lambda r: _validate_root_selector(
            r, max_words=self.config.max_root_label_words)
        result = self._call_module("RootSelector", payload, validator=root_validator)
        if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
            knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
            self.env.ingest_external_context(knowledge)
            result = self._call_module("RootSelector", payload, validator=root_validator)
        return RootNode(
            label=result.get("root_label", result.get("label", "Undifferentiated syndrome")),
            time_course=result.get("time_course", "unspecified"),
            severity="unspecified",
            confidence=result.get("confidence", 0.5),
            supporting_facts=result.get("supporting_facts", []),
            excluded_candidates=result.get("excluded_root_candidates", []),
            alarm_features=result.get("alarm_features", []),
            salient_findings=_clean_salient_findings(
                result.get("salient_findings", [])),
        )

    def _init_syndrome_axis_map(self):
        """Load the §23.14 syndrome→axis table (auto-discovered next to the LR
        cache when the path is unset). Returns None on any failure (fail-open)."""
        from .knowledge.syndrome_axis import SyndromeAxisMap
        base = (Path(self.config.lr_cache_json).parent if self.config.lr_cache_json
                else Path("data/knowledge_raw"))

        def _hand_map_path() -> str | None:
            p = self.config.syndrome_axis_map_json
            if not p:
                cand = base / "syndrome_axis_map.json"
                p = str(cand) if cand.exists() else None
            return p if p and Path(p).exists() else None

        # §31.13.18: A∪C union mode — syndrome detection via the hand map +
        # axis/domain partition from (offline LLM-axis cache ∪ curated seeds),
        # with hand-map fallback so coverage never regresses. Recommended
        # automation path (§31.13.17: 100% coverage / 0 axis error in iso-eval).
        if getattr(self.config, "union_axis_ac", False):
            hp = _hand_map_path()
            if hp:
                try:
                    from .knowledge.union_axis import UnionAxisMap
                    llm_cache = (self.config.llm_axis_cache_json
                                 or str(base / "auto_axis_cache.json"))
                    seeds = (self.config.override_seeds_json
                             or str(base / "syndrome_override_seeds.json"))
                    live_source = live_client = None
                    if getattr(self.config, "branch_llm_axis_live", False):
                        live_source, live_client = self._build_llm_axis_live_source(base)
                    um = UnionAxisMap.from_files(
                        hp,
                        llm_axis_cache_json=llm_cache,
                        override_seeds_json=seeds,
                        llm_source=live_source,
                        llm_client=live_client,
                        enable_phase_subaxis=getattr(self.config, "enable_phase_subaxis", False),
                    )
                    _logger.info("§31.13.18: BranchCreator using A∪C union axis map")
                    return um
                except Exception as e:  # pragma: no cover - defensive fail-open
                    _logger.warning("union_axis_ac requested but UnionAxisMap load "
                                    "failed (%s); falling back", e)
            else:
                _logger.warning("union_axis_ac requested but hand map (for syndrome "
                                "detection) not found; falling back")

        # §31.13: automation mode — derive the axis/domain partition from KBs
        # (SNOMED defining attributes + LR-cache recall) instead of the hand map.
        # Emits the SAME entry shape, so every downstream option is unchanged.
        if getattr(self.config, "auto_axis_kb", False):
            try:
                from .knowledge.auto_axis import KBAxisMap
                base = Path(self.config.lr_cache_json).parent if self.config.lr_cache_json else Path("data/knowledge_raw")
                km = KBAxisMap.from_files(
                    self.config.lr_cache_json or (base / "lr_cache.json"),
                    self.config.snomed_concepts_json or (base / "snomed_concepts.json"),
                    self.config.snomed_term_index_json or (base / "snomed_term_index.json"),
                    str(base / "snomed_relations.json"),
                    mechanism_to_disease_json=str(base / "mechanism_to_disease.json"),
                    diagnostic_markers_json=str(base / "diagnostic_markers.json"),
                )
                _logger.info("§31.13: BranchCreator using KB-derived axis map")
                return km
            except Exception as e:  # pragma: no cover - defensive fail-open
                _logger.warning("auto_axis_kb requested but KBAxisMap load failed "
                                "(%s); falling back to hand map", e)
        path = self.config.syndrome_axis_map_json
        if not path and self.config.lr_cache_json:
            cand = Path(self.config.lr_cache_json).parent / "syndrome_axis_map.json"
            path = str(cand) if cand.exists() else None
        if not path or not Path(path).exists():
            _logger.warning("Branch-knowledge enabled but syndrome_axis_map.json "
                            "not found; branch anchoring will be inert")
            return None
        try:
            return SyndromeAxisMap.from_file(path)
        except Exception as e:  # pragma: no cover - defensive
            _logger.warning("Failed to load SyndromeAxisMap: %s", e)
            return None

    def _build_llm_axis_live_source(self, base: Path):
        """§31.13.18 (opt-in): construct the (GuidelineBranchSource, llm_client)
        pair used by UnionAxisMap to GENERATE a missing syndrome's
        branch_knowledge live (write-through to the A-cache). Returns (None,
        None) on any failure → UnionAxisMap silently relies on cache ∪ seeds."""
        try:
            from .knowledge.rag_retriever import RAGRetriever
            from .knowledge.guideline_branch_source import (
                GuidelineBranchSource, build_disorder_vocab)
            from .knowledge.disease_name_resolver import DiseaseNameResolver
            import json as _json
            if self.llm is None or not self.config.rag_index_dir:
                return None, None
            retr = RAGRetriever(self.config.rag_index_dir)
            if not retr.is_ready:
                return None, None
            concepts_path = (self.config.snomed_concepts_json
                             or str(base / "snomed_concepts.json"))
            vocab = build_disorder_vocab(_json.loads(
                Path(concepts_path).read_text(encoding="utf-8")))
            resolver = DiseaseNameResolver()
            m2d = base / "mechanism_to_disease.json"
            if m2d.exists():
                resolver.load_mechanism_map(m2d)
            src = GuidelineBranchSource(retr, vocab, resolver=resolver)
            return src, self.llm
        except Exception as e:  # pragma: no cover - defensive fail-open
            _logger.warning("live LLM-axis source unavailable (%s); union mode "
                            "will use cache ∪ seeds only", e)
            return None, None

    def _init_case_report_source(self):
        """Construct the CaseReportBranchSource over the case-report TF-IDF index.
        Returns None on any failure (fail-open: branch anchoring falls back to
        the CPG-only marker/taxonomy path)."""
        try:
            from .knowledge.rag_retriever import RAGRetriever
            from .knowledge.case_report_source import (
                CaseReportBranchSource, build_case_report_vocab)
            from .knowledge.guideline_branch_source import build_disorder_vocab
            import json as _json

            idx = self.config.case_report_index_dir
            if not idx:
                cand = Path("data/corpus/case_report_index")
                idx = str(cand) if cand.exists() else None
            if not idx or not Path(idx).exists():
                _logger.warning("case-report branch source enabled but index not "
                                "found (%s); build with scripts/build_case_report_"
                                "{corpus,index}.py — augmentation inert", idx)
                return None
            retr = RAGRetriever(idx, device="cpu")
            if not retr.is_ready:
                _logger.warning("case-report index at %s not ready; augmentation inert", idx)
                return None
            base = (Path(self.config.lr_cache_json).parent
                    if self.config.lr_cache_json else Path("data/knowledge_raw"))
            concepts_path = (self.config.snomed_concepts_json
                             or str(base / "snomed_concepts.json"))
            vocab: set[str] = set()
            if Path(concepts_path).exists():
                vocab = build_disorder_vocab(_json.loads(
                    Path(concepts_path).read_text(encoding="utf-8")))
            # union the case-report ground-truth disease names (covers long-tail
            # golds SNOMED may miss: glucagonoma, blast-crisis phrasing, ...)
            norm_path = Path(idx).parent.parent / "case_reports" / "case_reports.jsonl"
            if not norm_path.exists():
                norm_path = Path("data/case_reports/case_reports.jsonl")
            vocab |= build_case_report_vocab(norm_path)
            # reuse the same resolver the knowledge layer already loaded (mechanism
            # canonicalisation + family expansion) when available.
            resolver = (getattr(self._knowledge_retriever, "resolver", None)
                        if self._knowledge_retriever is not None else None)
            if resolver is None:
                try:
                    from .knowledge.disease_name_resolver import DiseaseNameResolver
                    resolver = DiseaseNameResolver()
                    m2d = base / "mechanism_to_disease.json"
                    if m2d.exists() and hasattr(resolver, "load_mechanism_map"):
                        resolver.load_mechanism_map(str(m2d))
                except Exception:  # pragma: no cover - defensive
                    resolver = None
            src = CaseReportBranchSource(retr, vocab, resolver=resolver, top_k=20)
            _logger.info("Case-report branch source ready (index=%s, vocab=%d)",
                         idx, len(vocab))
            return src
        except Exception as e:  # pragma: no cover - defensive fail-open
            _logger.warning("case-report branch source init failed (%s); inert", e)
            return None

    def _init_cpg_branch_source(self):
        """Construct a GuidelineBranchSource over the CPG/StatPearls TF-IDF/FAISS
        index (rag_index_dir) for the step-3 dual-entrance CPG augmentation.
        Returns None on any failure (fail-open: the CPG main path stays
        marker/taxonomy-only)."""
        try:
            from .knowledge.rag_retriever import RAGRetriever
            from .knowledge.guideline_branch_source import (
                GuidelineBranchSource, build_disorder_vocab)
            import json as _json

            idx = self.config.rag_index_dir
            if not idx:
                cand = Path("data/corpus/cpg_index")
                idx = str(cand) if cand.exists() else None
            if not idx or not Path(idx).exists():
                _logger.warning("cpg branch source enabled but rag_index_dir not "
                                "found (%s); augmentation inert", idx)
                return None
            retr = RAGRetriever(idx, device="cpu")
            if not retr.is_ready:
                _logger.warning("cpg index at %s not ready; augmentation inert", idx)
                return None
            base = (Path(self.config.lr_cache_json).parent
                    if self.config.lr_cache_json else Path("data/knowledge_raw"))
            concepts_path = (self.config.snomed_concepts_json
                             or str(base / "snomed_concepts.json"))
            vocab: set[str] = set()
            if Path(concepts_path).exists():
                vocab = build_disorder_vocab(_json.loads(
                    Path(concepts_path).read_text(encoding="utf-8")))
            resolver = (getattr(self._knowledge_retriever, "resolver", None)
                        if self._knowledge_retriever is not None else None)
            if resolver is None:
                try:
                    from .knowledge.disease_name_resolver import DiseaseNameResolver
                    resolver = DiseaseNameResolver()
                    m2d = base / "mechanism_to_disease.json"
                    if m2d.exists() and hasattr(resolver, "load_mechanism_map"):
                        resolver.load_mechanism_map(str(m2d))
                except Exception:  # pragma: no cover - defensive
                    resolver = None
            src = GuidelineBranchSource(retr, vocab, resolver=resolver)
            _logger.info("CPG branch source ready (index=%s, vocab=%d)",
                         idx, len(vocab))
            return src
        except Exception as e:  # pragma: no cover - defensive fail-open
            _logger.warning("cpg branch source init failed (%s); inert", e)
            return None

    def _llm_ddx_entities(self, syndrome: str, salient: list[str],
                          context: str) -> list[str]:
        """4th entrance: ask the wired LLM for the full DDx of the presentation.
        Returns a de-duplicated list of specific disease entities (temperature 0,
        fail-open → [] on any error). Used only when
        enable_llm_ddx_branch_entrance is set."""
        if self.llm is None:
            return []
        prompt = (
            "You are an expert physician building the FULL differential diagnosis "
            "for a presenting syndrome. List EVERY plausible diagnosis a thorough "
            "clinician would consider, including rare/zebra causes. Return STRICT "
            'JSON: {"differentials": ["specific disease 1", ...]}. Give SPECIFIC '
            "disease entities (e.g. 'chronic myeloid leukemia', 'pancoast tumor', "
            "'glucagonoma'), 12-25 items, no prose."
        )
        payload = {
            "presenting_syndrome": syndrome,
            "salient_findings": list(salient or []),
            "context": (context or "")[:1500],
        }
        try:
            result = self.llm.call_module("LLMDdxEntrance", prompt, payload)
            if not isinstance(result, dict):
                return []
            out, seen = [], set()
            for x in (result.get("differentials") or []):
                s = str(x).strip()
                if s and s.lower() not in seen:
                    seen.add(s.lower())
                    out.append(s)
            return out[:25]
        except Exception as e:  # pragma: no cover - defensive fail-open
            _logger.warning("LLM DDx entrance failed (%s); skipping", e)
            return []

    def _collect_recall_rankings(
        self,
        *,
        syndrome: str,
        salient: list[str],
        context: str,
        top_k: int | None = None,
    ) -> list[tuple[str, dict[str, float]]]:
        """Shared L1/L2 case-report + CPG + LLM-DDx source collection.

        The returned rankings are still separate so callers can RRF-fuse them
        while retaining source rank/provenance. Empty ready sources are retained,
        matching the historical L1 ``n_entrances`` semantics.
        """
        fweight = getattr(self.config, "salient_finding_entrance_weight", 1.0)
        rankings: list[tuple[str, dict[str, float]]] = []
        for source_name, source, warning in (
            ("case_report", getattr(self, "_case_report_source", None),
             "case-report"),
            ("cpg", getattr(self, "_cpg_branch_source", None), "CPG"),
        ):
            if source is None:
                continue
            try:
                kwargs = {
                    "context": context,
                    "salient_findings": salient,
                    "finding_entrance_weight": fweight,
                }
                if top_k is not None:
                    kwargs["top_k"] = top_k
                rankings.append((source_name, source.recall(syndrome, **kwargs)))
            except Exception as e:  # pragma: no cover - defensive fail-open
                _logger.warning("recall-hints %s recall failed (%s)", warning, e)

        if getattr(self.config, "enable_llm_ddx_branch_entrance", False):
            ddx = self._llm_ddx_entities(syndrome, salient, context)
            if ddx:
                rankings.append((
                    "llm_ddx",
                    {d: 1.0 / (i + 1) for i, d in enumerate(ddx)},
                ))
        return rankings

    @staticmethod
    def _fuse_l2_recall_candidates(
        named_rankings: list[tuple[str, dict[str, float]]],
        *,
        query: str,
        cap: int,
    ) -> list[dict]:
        """RRF-fuse source rankings while retaining rank and provenance."""
        display: dict[str, str] = {}
        normalised_rankings: list[dict[str, float]] = []
        source_rows: dict[str, dict[str, tuple[int, float]]] = {}
        for source, ranking in named_rankings:
            norm: dict[str, float] = {}
            rows: dict[str, tuple[int, float]] = {}
            ordered = sorted(
                (ranking or {}).items(), key=lambda kv: kv[1], reverse=True
            )
            for source_rank, (disease, score) in enumerate(ordered, start=1):
                label = str(disease).strip()
                if not label:
                    continue
                key = label.casefold()
                display.setdefault(key, label)
                value = float(score)
                if key not in norm or value > norm[key]:
                    norm[key] = value
                    rows[key] = (source_rank, value)
            normalised_rankings.append(norm)
            source_rows[source] = rows

        from .knowledge.guideline_branch_source import GuidelineBranchSource
        fused = GuidelineBranchSource._rrf_merge(normalised_rankings, k=60)
        candidates: list[dict] = []
        for key, score in sorted(
            fused.items(), key=lambda kv: kv[1], reverse=True
        )[:cap]:
            source_rank: dict[str, int] = {}
            provenance: list[dict] = []
            for source, rows in source_rows.items():
                if key not in rows:
                    continue
                rank, raw_score = rows[key]
                source_rank[source] = rank
                provenance.append({
                    "source": source,
                    "rank": rank,
                    "score": raw_score,
                    "query": query,
                })
            candidates.append({
                "disease": display.get(key, key),
                "rrf_score": float(score),
                "source_rank": source_rank,
                "provenance": provenance,
            })
        return candidates

    def _extract_l2_knowledge_fragments(
        self,
        *,
        syndrome: str,
        salient: list[str],
        context: str,
        budget: int,
    ) -> list[dict]:
        """Collect bounded, structured on-topic hits from existing retrievers."""
        from .knowledge.cpg_chunk_gate import snippet_on_topic

        if budget <= 0:
            return []
        pools: list[list[dict]] = []
        for source_name, source in (
            ("case_report", getattr(self, "_case_report_source", None)),
            ("cpg", getattr(self, "_cpg_branch_source", None)),
        ):
            retriever = getattr(source, "_r", None) if source is not None else None
            if retriever is None or not getattr(retriever, "is_ready", False):
                continue
            queries: list[tuple[str, str]] = [
                (f"differential diagnosis of {syndrome}", syndrome),
                (f"causes and etiology of {syndrome}", syndrome),
            ]
            if context.strip():
                queries.append((
                    f"differential diagnosis of {syndrome}. clinical features: "
                    f"{context[:300]}",
                    syndrome,
                ))
            for finding in salient:
                finding = str(finding).strip()
                if finding:
                    queries.extend([
                        (f"differential diagnosis of {finding}", finding),
                        (finding, finding),
                    ])

            pool: list[dict] = []
            seen: set[str] = set()
            for query, gate_text in queries:
                try:
                    hits = retriever.search(
                        query, top_k=budget, score_threshold=0.0
                    )
                    if hasattr(retriever, "expand_ddx_siblings"):
                        hits = retriever.expand_ddx_siblings(hits)
                except Exception as e:  # pragma: no cover - fail-open
                    _logger.warning(
                        "L2 %s fragment retrieval failed (%s)", source_name, e
                    )
                    continue
                gate_tokens = {
                    token for token in re.findall(
                        r"[a-z0-9]+", gate_text.casefold()
                    ) if len(token) > 2
                }
                for index, hit in enumerate(hits or []):
                    title = str(hit.get("title", "") or "")
                    content = str(hit.get("content", "") or "")
                    if not content or not snippet_on_topic(
                        title=title,
                        content=content,
                        syndrome_tokens=gate_tokens,
                        chunk_type=hit.get("chunk_type"),
                        entry_type=hit.get("entry_type"),
                        syndrome_anchor=hit.get("syndrome_anchor"),
                        section_path=hit.get("section_path") or title,
                    ):
                        continue
                    fragment_id = str(
                        hit.get("id") or hit.get("chunk_id")
                        or hit.get("source_id")
                        or f"{source_name}::{index}"
                    )
                    dedup = f"{source_name}:{fragment_id}"
                    if dedup in seen:
                        continue
                    seen.add(dedup)
                    pool.append({
                        "source": source_name,
                        "title": title[:300],
                        "content": content[:1200],
                        "id": fragment_id,
                    })
                    if len(pool) >= budget:
                        break
                if len(pool) >= budget:
                    break
            if pool:
                pools.append(pool)

        # Round-robin avoids one corpus monopolising a shared fragment budget.
        fragments: list[dict] = []
        index = 0
        while len(fragments) < budget:
            added = False
            for pool in pools:
                if index < len(pool):
                    fragments.append(pool[index])
                    added = True
                    if len(fragments) >= budget:
                        break
            if not added:
                break
            index += 1
        return fragments

    def build_l2_case_recall_asset(self, state) -> dict:
        """Build the reusable case-level Mode-B asset exactly once.

        Candidate retrieval uses the same syndrome, salient findings, source
        collector and RRF inputs as ``_build_recall_hints``. The returned envelope
        is directly accepted by :meth:`freeze_l2_recall_asset`.
        """
        root = getattr(state, "root", None)
        syndrome = getattr(root, "label", "") if root is not None else ""
        salient = list(getattr(root, "salient_findings", []) or [])
        try:
            context = " ".join(
                str(x) for x in (
                    getattr(state, "case_summary", "") or "",
                    " ".join(self._raw_atomic_facts(state)[:40]),
                ) if x
            )
        except Exception:  # pragma: no cover - sparse integration state
            context = str(getattr(state, "case_summary", "") or "")
        snippet_budget = int(getattr(
            self.config, "l2_recall_snippet_budget", 12
        ))
        named = self._collect_recall_rankings(
            syndrome=syndrome,
            salient=salient,
            context=context,
            top_k=snippet_budget,
        ) if (syndrome or salient) else []
        candidates = self._fuse_l2_recall_candidates(
            named, query=syndrome, cap=24
        )
        fragments = self._extract_l2_knowledge_fragments(
            syndrome=syndrome,
            salient=salient,
            context=context,
            budget=snippet_budget,
        ) if (syndrome or salient) else []
        return {
            "asset_version": "l2_case_recall_v1",
            "query": {
                "syndrome": syndrome,
                "salient_findings": salient,
            },
            "candidate_limit": 24,
            "snippet_budget": snippet_budget,
            "candidates": candidates,
            "knowledge_fragments": fragments,
        }

    def _build_recall_hints(self, state) -> dict | None:
        """§32 recall-hints mode: build a FLAT, ranked ``candidate_diseases`` hint
        block from the 4-entrance union (case-report ∪ CPG ∪ LLM-DDx), WITHOUT any
        axis_map / partition / member-keyword projection.

        Rationale (§RESIDUAL_MISS §12/13): the LLM single-axis prompt already
        produces the best MECE L1 partition (9/9), while the axis_map that the
        legacy path used to DEFINE the partition is either unscalable (hand map)
        or low quality (KBAxisMap taxonomy). Meanwhile the entrances' RECALL is
        genuinely valuable on the long tail (RareArena). So here we keep ONLY the
        recall: fuse the entrances by RRF into one ranked disease list and hand it
        to the LLM as hints ("make sure your own partition has a home for the
        plausible ones"). No mandatory_coverage → the LLM's partition is never
        overridden; the block is strictly additive recall. Fail-open → None (→
        pure-LLM path) if nothing recalls."""
        root = getattr(state, "root", None)
        if root is None:
            return None
        syndrome = getattr(root, "label", "") or ""
        salient = list(getattr(root, "salient_findings", []) or [])
        if not (syndrome or salient):
            return None
        text = " ".join(
            str(x) for x in (
                getattr(state, "case_summary", "") or "",
                " ".join(self._raw_atomic_facts(state)[:40]),
            ) if x
        )
        named_rankings = self._collect_recall_rankings(
            syndrome=syndrome, salient=salient, context=text
        )
        if not named_rankings:
            return None
        rankings = [ranking for _source, ranking in named_rankings]

        # Reciprocal-rank fusion across entrances → one ranked candidate list.
        from .knowledge.guideline_branch_source import GuidelineBranchSource
        fused = GuidelineBranchSource._rrf_merge(rankings, k=60)
        cap = int(getattr(self.config, "branch_recall_hints_cap", 24))
        ranked = [d for d, _ in sorted(fused.items(), key=lambda kv: kv[1],
                                       reverse=True)][:cap]
        if not ranked:
            return None

        block = {
            "recall_hints_mode": True,
            "candidate_diseases": ranked,
            "syndrome_matched": syndrome,
            "n_entrances": len(rankings),
        }
        _logger.info("Branch recall-hints (§32): %d entrances → %d candidate "
                     "diseases (flat, LLM owns partition)", len(rankings),
                     len(ranked))
        return block

    def _l2_case_context(self, state) -> str:
        """Bounded clinical-only context; intentionally excludes answer/gold data."""
        root = getattr(state, "root", None)
        parts = [
            getattr(state, "case_summary", "") or "",
            getattr(root, "label", "") if root is not None else "",
        ]
        try:
            parts.append(" ".join(self._raw_atomic_facts(state)[:40]))
        except Exception:  # pragma: no cover - sparse integration state
            pass
        return " ".join(str(x).strip() for x in parts if str(x).strip())[:5000]

    def _build_l2_per_parent_asset(
        self, state, parent_branch: Branch
    ) -> tuple[list[dict], list[dict], dict]:
        """Mode A: fresh parent-conditioned recall with source-level audit."""
        root = getattr(state, "root", None)
        root_label = getattr(root, "label", "") if root is not None else ""
        salient = list(getattr(root, "salient_findings", []) or [])
        query = parent_branch.label
        if root_label:
            query = f"{parent_branch.label} within {root_label}"
        context = self._l2_case_context(state)
        snippet_budget = int(getattr(
            self.config, "l2_recall_snippet_budget", 12
        ))
        named = self._collect_recall_rankings(
            syndrome=query,
            salient=salient,
            context=context,
            top_k=snippet_budget,
        )
        fragments = self._extract_l2_knowledge_fragments(
            syndrome=query,
            salient=salient,
            context=context,
            budget=snippet_budget,
        )
        self._l2_parent_retrieval_calls += 1
        audit = {
            "mode": "per_parent",
            "parent_id": parent_branch.id,
            "parent_label": parent_branch.label,
            "query": query,
            "candidate_budget": int(getattr(
                self.config, "l2_recall_candidate_budget", 24
            )),
            "snippet_budget": snippet_budget,
            "sources": [source for source, _ranking in named],
            "fragment_count": len(fragments),
            "knowledge_fragments": fragments,
            "retrieval_calls": 1,
            "mapping_calls": 0,
        }
        if not named:
            audit["outcome"] = "no_recall_sources"
            return [], fragments, audit

        cap = int(getattr(self.config, "l2_recall_candidate_budget", 24))
        candidates = self._fuse_l2_recall_candidates(
            named, query=query, cap=cap
        )
        audit["candidate_count"] = len(candidates)
        audit["candidates"] = candidates
        audit["outcome"] = "recalled" if candidates else "empty_recall"
        return candidates, fragments, audit

    def _l2_asset_from_state_or_controller(self, state) -> dict:
        asset = self._l2_frozen_recall_asset
        if asset is None:
            asset = getattr(state, "l2_frozen_recall_asset", None)
        if asset is None:
            asset = getattr(state, "l2_recall_asset", None)
        if asset is None:
            return {"candidates": [], "knowledge_fragments": []}
        return self._normalise_l2_recall_asset(asset)

    @staticmethod
    def _semantic_parent_ids(disease: str, parents: list[Branch]) -> list[str]:
        """Deterministic no-retrieval fallback for incomplete/failed LLM mapping."""
        tokens = set(re.findall(r"[a-z0-9]+", disease.casefold()))
        scored: list[tuple[int, str]] = []
        for parent in parents:
            pt = set(re.findall(r"[a-z0-9]+", parent.label.casefold()))
            scored.append((len(tokens & pt), parent.id))
        best = max((score for score, _pid in scored), default=0)
        if best > 0:
            return [pid for score, pid in scored if score == best]
        # With no lexical signal, retaining the entity for every parent is safer
        # than silently losing recall; the L2 creator still filters plausibility.
        return [parent.id for parent in parents]

    def _assign_l2_reuse_asset(self, state, asset: dict) -> dict[str, list[dict]]:
        """Mode B: one case-level assignment pass, cached for every L1 parent."""
        case_key = str(getattr(state, "case_id", "") or id(state))
        if (self._l2_reuse_assignment_cache is not None
                and self._l2_reuse_assignment_case == case_key):
            return self._l2_reuse_assignment_cache

        parents = sorted(
            (b for b in getattr(state, "branches", {}).values() if b.level == 1),
            key=lambda b: b.id,
        )
        candidates = list(asset.get("candidates", []) or [])
        fragments = list(asset.get("knowledge_fragments", []) or [])
        mapping: dict[str, list[dict]] = {p.id: [] for p in parents}
        by_disease = {row["disease"].casefold(): row for row in candidates}
        assigned: set[str] = set()
        if self.llm is not None and parents and candidates:
            prompt = (
                "Map each specific disease candidate to every plausible numbered "
                "Level-1 parent by clinical meaning. This is assignment only: do "
                "not retrieve or invent candidates. Return STRICT JSON: "
                '{"assignments":[{"disease":"...", "parent_ids":["B1"]}, ...]}.'
            )
            payload = {
                "case_context": self._l2_case_context(state),
                "parents": [{"id": p.id, "label": p.label} for p in parents],
                "recall_candidates": candidates,
            }
            try:
                self._l2_reuse_mapping_calls += 1
                result = self.llm.call_module(
                    "L2RecallParentAssign", prompt, payload
                )
                for row in (
                    result.get("assignments", [])
                    if isinstance(result, dict) else []
                ):
                    disease = str(
                        row.get("disease") or row.get("entity") or ""
                    ).strip()
                    record = by_disease.get(disease.casefold())
                    if record is None:
                        continue
                    parent_ids = row.get("parent_ids")
                    if isinstance(parent_ids, str):
                        parent_ids = [parent_ids]
                    if not isinstance(parent_ids, list):
                        parent_id = row.get("parent_id")
                        parent_ids = [parent_id] if parent_id else []
                    valid = [pid for pid in parent_ids if pid in mapping]
                    if not valid:
                        continue
                    assigned.add(disease.casefold())
                    for pid in valid:
                        if record not in mapping[pid]:
                            mapping[pid].append(record)
            except Exception as e:  # pragma: no cover - defensive fail-open
                _logger.warning(
                    "L2 reuse_l1 parent assignment failed (%s); using semantic "
                    "fallback", e
                )

        # Complete mapping: an LLM omission must not become recall loss.
        for record in candidates:
            key = record["disease"].casefold()
            if key in assigned:
                continue
            for pid in self._semantic_parent_ids(record["disease"], parents):
                if record not in mapping[pid]:
                    mapping[pid].append(record)

        cap = int(getattr(self.config, "l2_recall_candidate_budget", 24))
        mapping = {pid: rows[:cap] for pid, rows in mapping.items()}
        fragment_cap = int(getattr(
            self.config, "l2_recall_snippet_budget", 12
        ))
        fragment_mapping: dict[str, list[dict]] = {}
        for parent in parents:
            terms = set(re.findall(
                r"[a-z0-9]+", parent.label.casefold()
            ))
            for candidate in mapping[parent.id]:
                terms.update(re.findall(
                    r"[a-z0-9]+", candidate["disease"].casefold()
                ))
            scored: list[tuple[int, int, dict]] = []
            for index, fragment in enumerate(fragments):
                text_tokens = set(re.findall(
                    r"[a-z0-9]+",
                    (
                        str(fragment.get("title", "")) + " "
                        + str(fragment.get("content", ""))
                    ).casefold(),
                ))
                scored.append((len(terms & text_tokens), -index, fragment))
            positive = [row for row in scored if row[0] > 0]
            selected = positive or scored
            selected.sort(key=lambda row: (row[0], row[1]), reverse=True)
            fragment_mapping[parent.id] = [
                row[2] for row in selected[:fragment_cap]
            ]
        self._l2_reuse_assignment_cache = mapping
        self._l2_reuse_fragment_cache = fragment_mapping
        self._l2_reuse_assignment_case = case_key
        return mapping

    def _l2_recall_for_parent(
        self, state, parent_branch: Branch
    ) -> tuple[list[dict], list[dict], dict]:
        if self._l2_mode == "per_parent":
            return self._build_l2_per_parent_asset(state, parent_branch)

        # Mode B invariant: this branch contains no source.recall call.
        asset = self._l2_asset_from_state_or_controller(state)
        asset_candidates = list(asset.get("candidates", []) or [])
        asset_fragments = list(asset.get("knowledge_fragments", []) or [])
        audit = {
            "mode": "reuse_l1",
            "parent_id": parent_branch.id,
            "parent_label": parent_branch.label,
            "candidate_budget": int(getattr(
                self.config, "l2_recall_candidate_budget", 24
            )),
            "snippet_budget": int(getattr(
                self.config, "l2_recall_snippet_budget", 12
            )),
            "frozen_asset_size": len(asset_candidates),
            "frozen_fragment_count": len(asset_fragments),
            "retrieval_calls": 0,
        }
        if not asset_candidates:
            audit.update({"outcome": "missing_frozen_asset", "mapping_calls": 0})
            return [], [], audit
        before = self._l2_reuse_mapping_calls
        mapping = self._assign_l2_reuse_asset(state, asset)
        candidates = mapping.get(parent_branch.id, [])
        fragments = (
            self._l2_reuse_fragment_cache or {}
        ).get(parent_branch.id, [])
        audit.update({
            "mapping_calls": self._l2_reuse_mapping_calls - before,
            "mapping_calls_total": self._l2_reuse_mapping_calls,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "fragment_count": len(fragments),
            "knowledge_fragments": fragments,
            "outcome": "mapped" if candidates else "empty_mapping",
        })
        return candidates, fragments, audit

    def _build_branch_candidates(self, state) -> dict | None:
        """§23.14 (Mode A) — DETERMINISTIC, pure: derive the KB anchoring block
        for BranchCreator. Returns None (→ legacy pure-LLM path) unless
        ``enable_branch_knowledge`` is set AND a syndrome matches.

        Output dict (injected as payload['branch_knowledge']):
          l1_classification_axis : the single L1 axis chosen for this syndrome
          axis_rationale         : why that axis (for the prompt)
          mandatory_coverage     : the MECE single-axis L1 domain partition the
                                   branches MUST cover (recall guarantee)
          candidate_entities_by_domain : recalled L3 entities per domain
                                   (T1 markers + taxonomy), for L2/L3 down-push —
                                   NOT to be used as L1 labels
          syndrome_matched       : matched syndrome id (provenance)

        All steps are table/array lookups — no LLM, no randomness — so the
        anchoring is identical across runs (removes the §22.8 branch-set
        variance at its highest-leverage point).

        §32 recall-hints mode (``branch_kb_recall_hints``): DECOUPLE the partition
        from recall — return a FLAT ``candidate_diseases`` hint list (union of the
        entrances, no axis_map, no mandatory_coverage) and let the LLM own the
        single-axis MECE partition. Takes priority over the coupled path below."""
        if getattr(self.config, "branch_kb_recall_hints", False):
            return self._build_recall_hints(state)
        axis_map = self._syndrome_axis_map
        if axis_map is None:
            return None
        text = " ".join(
            str(x) for x in (
                getattr(state, "case_summary", "") or "",
                " ".join(self._raw_atomic_facts(state)[:40]),
            ) if x
        )
        if not text.strip():
            return None
        entry = axis_map.match(text)
        split = getattr(self.config, "enable_phase_subaxis", False)
        domains = axis_map.domain_names(entry, split=split)
        if not domains:  # 'undifferentiated' fallback → no anchoring (fail-open)
            return None

        tl = text.lower()
        entities_by_domain: dict[str, list[str]] = {d: [] for d in domains}

        # T1 nomination: curated markers whose terms appear in the vignette →
        # their target diseases, projected onto the axis domain partition.
        retr = self._knowledge_retriever
        mi = getattr(retr, "diagnostic_markers", None) if retr is not None else None
        for m in (getattr(mi, "_manual_markers", []) or []):
            terms = m.get("terms", []) or []
            if not any((t or "").lower() in tl for t in terms):
                continue
            for d in (m.get("target_diseases", []) or []):
                dom = axis_map.project_entity(d, entry, split=split)
                if dom and d.lower() not in [e.lower() for e in entities_by_domain.get(dom, [])]:
                    entities_by_domain.setdefault(dom, []).append(d)

        # Taxonomy enrichment: for domains with no marker hit, expand the domain
        # label to canonical entities (reuses A′ resolver; best-effort).
        resolver = getattr(retr, "resolver", None) if retr is not None else None
        if resolver is not None and hasattr(resolver, "expand_to_entities"):
            for d in domains:
                if entities_by_domain[d]:
                    continue
                try:
                    ents = resolver.expand_to_entities(d) or []
                except Exception:  # pragma: no cover - defensive
                    ents = []
                if ents:
                    entities_by_domain[d] = ents[:3]

        # Dual-entrance case-report augmentation (long-tail recall): recall the
        # presentation→diagnosis mappings CPG under-covers, keyed on the syndrome
        # frame UNION the RootSelector salient findings (RRF-fused), and merge
        # the projected entities into the per-domain candidate sets. Strictly
        # additive — never removes a marker/taxonomy candidate.
        cr_added = 0
        cr_src = getattr(self, "_case_report_source", None)
        root = getattr(state, "root", None)
        if cr_src is not None and root is not None:
            syndrome = getattr(root, "label", "") or ""
            salient = list(getattr(root, "salient_findings", []) or [])
            if syndrome or salient:
                try:
                    _scored, cr_by_domain = cr_src.recall_for_branches(
                        syndrome, axis_map, entry, split=split,
                        salient_findings=salient, context=text,
                        finding_entrance_weight=getattr(
                            self.config, "salient_finding_entrance_weight", 1.0),
                    )
                except Exception as e:  # pragma: no cover - defensive fail-open
                    _logger.warning("case-report recall failed (%s); skipping", e)
                    cr_by_domain = {}
                for dom, ents in (cr_by_domain or {}).items():
                    if dom not in entities_by_domain:
                        continue  # only augment MECE domains of the matched axis
                    have = [e.lower() for e in entities_by_domain[dom]]
                    for e in ents:
                        if len(entities_by_domain[dom]) >= 8:
                            break
                        if e.lower() not in have:
                            entities_by_domain[dom].append(e)
                            have.append(e.lower())
                            cr_added += 1

        # Step-3 CPG dual-entrance augmentation (main path): recall from the
        # CPG/StatPearls index via the SAME dual entrance (syndrome ∪ salient),
        # projected onto the axis domains. Strictly additive.
        cpg_added = 0
        cpg_src = getattr(self, "_cpg_branch_source", None)
        if cpg_src is not None and root is not None:
            syndrome = getattr(root, "label", "") or ""
            salient = list(getattr(root, "salient_findings", []) or [])
            if syndrome or salient:
                try:
                    _scored, cpg_by_domain = cpg_src.recall_for_branches(
                        syndrome, axis_map, entry, split=split,
                        salient_findings=salient, context=text,
                        finding_entrance_weight=getattr(
                            self.config, "salient_finding_entrance_weight", 1.0),
                    )
                except Exception as e:  # pragma: no cover - defensive fail-open
                    _logger.warning("cpg dual recall failed (%s); skipping", e)
                    cpg_by_domain = {}
                for dom, ents in (cpg_by_domain or {}).items():
                    if dom not in entities_by_domain:
                        continue
                    have = [e.lower() for e in entities_by_domain[dom]]
                    for e in ents:
                        if len(entities_by_domain[dom]) >= 8:
                            break
                        if e.lower() not in have:
                            entities_by_domain[dom].append(e)
                            have.append(e.lower())
                            cpg_added += 1

        # 4th entrance: LLM-enumerated DDx, projected onto the axis domains.
        # Strictly additive. Makes this step LLM-dependent when enabled.
        llm_added = 0
        if (getattr(self.config, "enable_llm_ddx_branch_entrance", False)
                and root is not None):
            syndrome = getattr(root, "label", "") or ""
            salient = list(getattr(root, "salient_findings", []) or [])
            ddx = self._llm_ddx_entities(syndrome, salient, text)
            for dz in ddx:
                try:
                    dom = axis_map.project_entity(dz, entry, split=split)
                except Exception:  # pragma: no cover - defensive
                    dom = None
                if not dom or dom not in entities_by_domain:
                    continue
                if len(entities_by_domain[dom]) >= 8:
                    continue
                if dz.lower() not in [e.lower() for e in entities_by_domain[dom]]:
                    entities_by_domain[dom].append(dz)
                    llm_added += 1

        block = {
            "l1_classification_axis": entry.get("axis", ""),
            "axis_rationale": entry.get("axis_rationale", ""),
            "mandatory_coverage": domains,
            "candidate_entities_by_domain": {
                k: v for k, v in entities_by_domain.items() if v
            },
            "syndrome_matched": entry.get("id", ""),
            "case_report_entities_added": cr_added,
            "cpg_entities_added": cpg_added,
            "llm_ddx_entities_added": llm_added,
        }
        _logger.info("Branch-knowledge (§23.14): syndrome=%s axis=%s domains=%s "
                     "case_report_added=%d cpg_added=%d llm_ddx_added=%d",
                     block["syndrome_matched"], block["l1_classification_axis"],
                     domains, cr_added, cpg_added, llm_added)
        return block

    def _parse_branches(self, result: dict) -> dict:
        """Turn a BranchCreator JSON result into {id: Branch} (Level-1)."""
        branches: dict = {}
        raw_branches = result.get("branches", [])
        if isinstance(raw_branches, dict):
            raw_branches = list(raw_branches.values())
        for b in raw_branches:
            # Defensive: validator guarantees id+label, but guard anyway so a
            # malformed item never aborts the whole run.
            if not isinstance(b, dict) or not b.get("id") or not b.get("label"):
                continue
            branches[b["id"]] = Branch(
                id=b["id"],
                label=b["label"],
                parent="ROOT",
                level=1,
                status=b.get("status", "live"),
                prior=b.get("prior_estimate", 0.0),
                posterior=b.get("prior_estimate", 0.0),
                danger=b.get("danger", 0.0),
                actionability=0.0,
                explanatory_coverage=0.0,
                level_role=b.get("level_role", "family"),
                classification_axis=b.get("classification_axis", ""),
                representative_diseases=_clean_representative_diseases(
                    b.get("representative_diseases")),
                askable_discriminators=b.get("askable_discriminators", []),
                requestable_discriminators=b.get("requestable_discriminators", []),
                turn_cost_to_refine=b.get("turn_cost_to_refine", 0.0),
                diagnosis_commitment_gain=b.get("diagnosis_commitment_gain", 0.0),
                interrupt_relevance=b.get("interrupt_relevance", 0.0),
            )
        return branches

    def _gap_fill_branches(self, state, branches: dict, branch_knowledge) -> dict:
        """§32 Phase-B: recall-driven MECE gap repair (opt-in via
        ``branch_recall_gap_fill``, only in recall-hints mode).

        The recall-hints block hands the LLM a flat candidate list but does NOT
        force a partition — so a strong recalled candidate can still lack a home
        family if the LLM's partition is too narrow. This does ONE LLM assignment
        pass (each top candidate → a branch index or -1) and, if any high-rank
        candidate is UNCOVERED, issues ONE corrective BranchCreator re-call asking
        it to widen/add a family (single-axis MECE preserved) so the candidate has
        a reachable home. Keyed on RECALLED ENTITIES (not KB domains), so it can
        never impose a bad partition; fail-open → original branches on any error.
        """
        if not (getattr(self.config, "branch_recall_gap_fill", False)
                and isinstance(branch_knowledge, dict)
                and branch_knowledge.get("recall_hints_mode")):
            return branches
        cands = list(branch_knowledge.get("candidate_diseases", []) or [])
        if not cands or not branches:
            return branches
        # only probe the top hints — the tail is noise we intentionally ignore.
        top = cands[: min(10, len(cands))]
        labels = [b.label for b in branches.values()]
        try:
            uncovered = self._recall_gap_uncovered(top, labels)
        except Exception as e:  # pragma: no cover - fail-open
            _logger.warning("gap-fill assignment failed (%s); keeping partition", e)
            return branches
        if not uncovered:
            return branches
        _logger.info("§32 Phase-B: %d uncovered recall candidate(s) %s → repair "
                     "re-call", len(uncovered), uncovered[:5])
        bk_payload = state.project_for("BranchCreator")
        bk = dict(branch_knowledge)
        bk["uncovered_candidates"] = uncovered
        bk_payload["branch_knowledge"] = bk
        try:
            result = self._call_module("BranchCreator", bk_payload,
                                       validator=_validate_branch_creator)
            repaired = self._parse_branches(result)
        except Exception as e:  # pragma: no cover - fail-open
            _logger.warning("gap-fill repair re-call failed (%s); keeping "
                            "original partition", e)
            return branches
        # Guard: only accept the repair if it did not SHRINK coverage (repaired
        # must have ≥ the original family count) — never regress on a bad re-call.
        if repaired and len(repaired) >= len(branches):
            return repaired
        return branches

    def _recall_gap_uncovered(self, candidates: list[str],
                              labels: list[str]) -> list[str]:
        """LLM pass: for each candidate disease, assign it to the single best-fit
        family label (by mechanism/category) or -1 if NONE fits. Return the
        candidates that fit no family (the MECE gaps). Uses the wired LLM at
        temperature 0; fail-open → [] (treat all as covered)."""
        if self.llm is None or not candidates or not labels:
            return []
        numbered = "\n".join(f"{i}: {l}" for i, l in enumerate(labels))
        clist = "\n".join(f"- {c}" for c in candidates)
        prompt = (
            "For EACH candidate disease, decide whether it fits (by mechanism/"
            "category, NOT wording) into exactly one of the numbered first-level "
            "families. Answer the family index, or -1 if NONE of the families "
            "could plausibly contain it. Return STRICT JSON: "
            '{"assignments": [{"candidate": "...", "index": <int>}, ...]}.')
        payload = {"families": numbered, "candidates": clist}
        result = self.llm.call_module("RecallGapAssign", prompt, payload)
        if not isinstance(result, dict):
            return []
        out: list[str] = []
        for a in (result.get("assignments") or []):
            try:
                if int(a.get("index", -1)) < 0:
                    c = str(a.get("candidate", "")).strip()
                    if c:
                        out.append(c)
            except (TypeError, ValueError):
                continue
        return out

    def create_branches(self, state):
        bk_payload = state.project_for("BranchCreator")
        branch_knowledge = self._build_branch_candidates(state)
        if branch_knowledge:
            bk_payload["branch_knowledge"] = branch_knowledge
        result = self._call_module("BranchCreator", bk_payload,
                                   validator=_validate_branch_creator)
        if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
            knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
            self.env.ingest_external_context(knowledge)
            result = self._call_module("BranchCreator", bk_payload,
                                       validator=_validate_branch_creator)

        branches = self._parse_branches(result)

        # §32 Phase-B (opt-in): recall gap-fill. In recall-hints mode, verify the
        # LLM's partition actually gives every plausible recalled candidate a home
        # family; if not, one repair re-call revises the partition. Runs BEFORE
        # mandatory/entity/prior so a repaired partition flows through them.
        branches = self._gap_fill_branches(state, branches, branch_knowledge)

        # §26.5(3): enforce mandatory KB-anchored coverage — inject any L1 domain
        # the LLM omitted so the gold entity always has a reachable node. Runs
        # BEFORE entity population so injected families also get lookup entities.
        self._enforce_mandatory_branches(branches, branch_knowledge)

        # §22.2 (A′): mechanically attach canonical lookup entities derived from
        # the (now frozen) branch labels — NON-prompt, so labels stay at their
        # discriminative syndrome granularity (no hollowing). Must run BEFORE the
        # age prior so entity-keyed lookups are available downstream.
        self._populate_lookup_entities(branches)

        # Structured age/sex PRIOR adjustment: epidemiology shifts the pre-test
        # probability, so we apply it once at branch creation (renormalized,
        # before any evidence is incorporated). Strictly additive when disabled.
        self._apply_age_prior(branches, state)
        return branches, result.get("frontier", [])

    _COVERAGE_GENERIC = {
        "disorder", "disorders", "disease", "diseases", "syndrome", "syndromes",
        "condition", "conditions", "related", "other", "of", "with", "and", "the",
        "a", "an", "or", "due", "to", "non", "process", "causes", "cause",
        # structural / phase words that are NOT lineage-discriminative — coverage
        # must key on the lineage head noun (myeloid vs lymphoid), not these.
        "neoplasm", "neoplasms", "neoplastic", "tumor", "tumour", "tumors",
        "mass", "lesion", "increased", "decreased", "blast", "blasts", "crisis",
        "bearing", "incl", "phase", "low", "high", "excess", "associated",
        "mediated", "type", "primary", "secondary",
    }

    def _enforce_mandatory_branches(self, branches: dict, branch_knowledge) -> None:
        """§26.5(3): guarantee every KB ``mandatory_coverage`` L1 domain has a
        branch. Any domain the LLM omitted is injected as a deterministic family
        branch carrying that domain's candidate entities. No-op unless
        ``enable_mandatory_kb_branches`` is set and a KB block is present."""
        if not (getattr(self.config, "enable_mandatory_kb_branches", False)
                and isinstance(branch_knowledge, dict)):
            return
        domains = branch_knowledge.get("mandatory_coverage", []) or []
        if not domains:
            return
        ents_by_domain = branch_knowledge.get("candidate_entities_by_domain", {}) or {}
        axis = branch_knowledge.get("l1_classification_axis", "")

        def _strip_gloss(text: str) -> str:
            # §27.3 fix: a parenthetical gloss like "… (AML, MDS-EB, CML-BC)" is a
            # member list, NOT lineage-discriminative tokens. Counting it inflates
            # dom_tok so an existing broad branch (sharing only the head noun) can
            # never meet the 50% bar → spurious duplicate injection. Drop it.
            return re.sub(r"\([^)]*\)", " ", text or "")

        def _key_tokens(text: str) -> set[str]:
            toks = re.findall(r"[a-z0-9]+", _strip_gloss(text).lower())
            return {t for t in toks if len(t) > 2 and t not in self._COVERAGE_GENERIC}

        def _ent_set(items) -> set[str]:
            out: set[str] = set()
            for e in items or []:
                el = str(e).strip().lower()
                if el:
                    out.add(el)
            return out

        label_tokens = [_key_tokens(getattr(b, "label", "")) for b in branches.values()]
        # §27.3 fix ④: entity-set coverage. A domain is already covered if any
        # existing branch's representative diseases overlap the domain's candidate
        # entities — even when their LABEL tokens differ (e.g. LLM branch "Myeloid
        # Neoplasm with Increased Blasts" carrying ["acute myeloid leukemia", …]
        # vs KB domain glossed "(AML, MDS-EB, CML-BC)"). Prevents the §27.3
        # duplicate-branch / probability-fragmentation bug.
        branch_ent_sets = [_ent_set(getattr(b, "representative_diseases", None))
                           for b in branches.values()]
        injected = 0
        for dom in domains:
            dom_tok = _key_tokens(dom)
            if not dom_tok:
                continue
            dom_ents = _ent_set(ents_by_domain.get(dom, []))
            # covered if (token) some branch shares ≥1 distinctive token AND ≥50%
            # of the domain's distinctive tokens, OR (entity) some branch's
            # representative diseases overlap the domain's candidate entities.
            covered = any(
                (dom_tok & lt) and len(dom_tok & lt) >= max(1, (len(dom_tok) + 1) // 2)
                for lt in label_tokens
            ) or (bool(dom_ents) and any(dom_ents & bs for bs in branch_ent_sets))
            if covered:
                continue
            new_id = f"kb_{re.sub(r'[^a-z0-9]+', '_', dom.lower()).strip('_')[:24]}"
            if new_id in branches:
                new_id = f"{new_id}_{injected}"
            ents = _clean_representative_diseases(ents_by_domain.get(dom, []))
            branches[new_id] = Branch(
                id=new_id,
                label=dom,
                parent="ROOT",
                level=1,
                status="live",
                prior=0.0,
                posterior=0.0,
                danger=0.0,
                actionability=0.0,
                explanatory_coverage=0.0,
                level_role="family",
                classification_axis=axis,
                representative_diseases=ents,
                askable_discriminators=[],
                requestable_discriminators=[],
                turn_cost_to_refine=0.0,
                diagnosis_commitment_gain=0.0,
                interrupt_relevance=0.0,
            )
            label_tokens.append(dom_tok)
            branch_ent_sets.append(_ent_set(ents))
            injected += 1
        if injected:
            _logger.info("§26.5(3): injected %d mandatory KB branch(es) for "
                         "uncovered domains", injected)

    def _populate_lookup_entities(self, branches: dict) -> None:
        """§22.2 (A′ — corrected Fix A): attach 1-4 canonical disease entities to
        each branch via the resolver's family-expansion taxonomy, derived
        MECHANICALLY from the frozen label. The branch label and tree are
        untouched (no prompt change → no label hollowing, §21.14.5). Entities are
        an invisible side-channel consumed only for LR/KB lookup. No-op unless
        ``enable_taxonomy_entities`` is set; never overwrites entities a branch
        already carries; a miss stays cheap (empty)."""
        if not branches or not (
            getattr(self.config, "enable_taxonomy_entities", False)
            or getattr(self.config, "enable_branch_knowledge", False)
        ):
            return
        retr = self._knowledge_retriever
        resolver = getattr(retr, "resolver", None) if retr is not None else None
        if resolver is None or not hasattr(resolver, "expand_to_entities"):
            return
        for b in branches.values():
            if getattr(b, "representative_diseases", None):
                continue
            try:
                ents = resolver.expand_to_entities(getattr(b, "label", "") or "")
            except Exception as e:  # pragma: no cover - defensive
                _logger.debug("taxonomy entity expansion failed for %r: %s",
                              getattr(b, "label", ""), e)
                ents = []
            if ents:
                b.representative_diseases = ents
                _logger.info("A′ taxonomy entities: %r → %s",
                             getattr(b, "label", ""), ents)

    def _apply_age_prior(self, branches: dict, state) -> None:
        if self._prior_modifier is None or not branches:
            return
        # F7 fix (§21.10.2): the demographics MUST be cached per-CASE, never on the
        # shared controller. `self` is reused across cases (and concurrently across
        # worker threads), so caching on `self._patient_age_sex` leaked the first
        # patient's age/sex into every later/concurrent case (e.g. a 10yo girl ran
        # with age=55,male, suppressing her correct congenital branch ×0.4). Cache
        # on the per-case `state` object instead.
        age, sex = getattr(state, "_age_sex_cache", (None, None))
        if age is None:
            from .knowledge.prior_modifier import parse_age_sex
            text = " ".join(
                str(x) for x in (
                    getattr(state, "static_vignette", "") or "",
                    getattr(state, "case_summary", "") or "",
                    " ".join(self._raw_atomic_facts(state)[:5]),
                ) if x
            )
            age, sex = parse_age_sex(text)
            try:
                state._age_sex_cache = (age, sex)
            except Exception:  # pragma: no cover - defensive (slotted state)
                pass
        # Test-only override (§22.5): force a UNIFORM (age,sex) across ALL cases to
        # reproduce the F7-leak condition (e.g. TREE_DX_FORCE_AGE_SEX="55,male").
        # Strictly opt-in via env var; no effect when unset.
        import os as _os
        _force = _os.environ.get("TREE_DX_FORCE_AGE_SEX")
        if _force:
            try:
                _a, _s = _force.split(",")
                age, sex = int(_a.strip()), _s.strip().lower()
            except Exception:  # pragma: no cover - defensive
                pass
        if age is None:
            return
        try:
            trace = self._prior_modifier.apply(branches, age, sex)
        except Exception as e:  # pragma: no cover - defensive
            _logger.debug("age prior apply failed: %s", e)
            return
        if trace:
            _logger.info(
                "AGE-PRIOR age=%s sex=%s adjusted %d branch(es): %s",
                age, sex, len(trace),
                {t["label"]: t["multiplier"] for t in trace.values()},
            )

    def initialize_sdbench_top3(self, state: DiagnosticState) -> None:
        ranked = sorted(state.branches.values(), key=lambda b: b.posterior, reverse=True)
        state.frontier = [b.id for b in ranked[:3]]
        state.other_mass = sum(b.posterior for b in ranked[3:])

    # ------------------------------------------------------------------
    # Deliberation (SDBench / Static QA)
    # ------------------------------------------------------------------

    def run_deliberation(self, state: DiagnosticState) -> DeliberationState:
        d = DeliberationState()
        payload = state.project_for("Deliberation")
        d.hypothesis_analysis = self._call_module("Hypothesis", payload)
        d.test_chooser_analysis = self._call_module("TestChooser", payload)
        d.challenger_analysis = self._call_module("Challenger", payload)
        d.stewardship_analysis = self._call_module("Stewardship", payload)
        d.checklist_analysis = self._call_module(
            "Checklist",
            {"state": payload, "proposed_actions": d.test_chooser_analysis},
        )
        d.consensus_action = self._call_module(
            "Consensus",
            {
                "state": payload,
                "deliberation": {
                    "hypothesis": d.hypothesis_analysis,
                    "test_chooser": d.test_chooser_analysis,
                    "challenger": d.challenger_analysis,
                    "stewardship": d.stewardship_analysis,
                    "checklist": d.checklist_analysis,
                },
            },
        )
        return d

    def run_static_qa_deliberation(self, state: DiagnosticState) -> DeliberationState:
        d = DeliberationState()
        payload = state.project_for("Deliberation")
        d.hypothesis_analysis = self._call_module("Hypothesis", payload)
        d.test_chooser_analysis = self._call_module("EvidenceAllocator", payload)
        d.challenger_analysis = self._call_module("Challenger", payload)
        d.stewardship_analysis = self._call_module("ReasoningEconomyAuditor", payload)
        d.checklist_analysis = self._call_module("Checklist", payload)
        d.consensus_action = self._call_module(
            "Consensus", {"state": payload, "deliberation": d.checklist_analysis}
        )
        return d

    # ------------------------------------------------------------------
    # Leaf planning
    # ------------------------------------------------------------------

    def _inject_discrimination_profile(
        self,
        payload: dict,
        state: DiagnosticState,
        *,
        phase: str,
    ) -> None:
        """Inject bounded profile rules/provenance and retain a per-case trace."""
        runtime = self._discrimination_runtime
        if runtime is None:
            return
        candidates = [
            branch.label for branch in state.branches.values()
            if branch.status not in ("closed_for_now", "expanded")
        ]
        candidates = list(dict.fromkeys(name for name in candidates if name))
        if not candidates:
            return

        findings = self._gather_atomic_findings(state)
        if not findings:
            findings = [
                fact for fact in self._raw_atomic_facts(state)
                if fact and not _is_demographic_fact(fact)
            ]
        findings = list(dict.fromkeys(findings))[:8]

        rule_in: list[dict] = []
        rule_out: list[dict] = []
        provenance: list[dict] = []
        for finding in findings:
            try:
                result = runtime.evidence(finding, candidates)
            except Exception as exc:
                # Runtime assets were validated at startup; an individual lookup
                # is a coverage/shape miss and must not take down the case.
                _logger.warning(
                    "%s discrimination lookup failed for %r: %s",
                    runtime.profile, finding, exc,
                )
                continue
            for rule in result.rules:
                target = rule_out if rule.get("effect") == "rule_out" else rule_in
                if rule.get("effect") in {"rule_in", "rule_out"}:
                    target.append({"finding": finding, **dict(rule)})
            for row in result.evidence:
                provenance.append({
                    "finding": finding,
                    "candidate": row.get("candidate", ""),
                    "claim_id": row.get("claim_id", ""),
                    "source": row.get("source", ""),
                    "provenance": list(row.get("provenance") or ()),
                })

        # Keep prompt and trace bounded even with a large vignette/candidate set.
        payload["discrimination_profile"] = runtime.profile
        payload["discriminator_rules"] = rule_in[:24]
        payload["ruleout_rules"] = rule_out[:24]
        payload["evidence_provenance"] = provenance[:32]
        audit = {
            "profile": runtime.profile,
            "phase": phase,
            "timestep": state.timestep,
            "findings": findings,
            "candidates": candidates,
            "discriminator_rules": rule_in[:24],
            "ruleout_rules": rule_out[:24],
            "evidence_provenance": provenance[:32],
        }
        state.discrimination_audit.append(audit)
        del state.discrimination_audit[:-40]

        audit_path = getattr(self.config, "talp_disc_audit_path", None)
        if audit_path:
            path = Path(self._resolve_disc_path(audit_path))
            try:
                with self._disc_audit_lock:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(
                            {"case_id": state.case_id, **audit},
                            ensure_ascii=False,
                            sort_keys=True,
                        ) + "\n")
            except OSError as exc:
                _logger.warning("Failed to write discrimination audit: %s", exc)

    def plan_temporary_leaves(self, state):
        planner_module = (
            "TemporaryAnalyticLeafPlanner" if self._in_static_qa_mode()
            else "TemporaryLeafPlanner"
        )
        payload = state.project_for(planner_module)

        # Knowledge injection: add discriminator_hints for TALP
        if self._knowledge_retriever and self.config.enable_knowledge_injection:
            disease_names = [
                b.label for b in state.branches.values()
                if b.status not in ("closed_for_now", "expanded")
            ]
            if disease_names:
                try:
                    vignette = getattr(state, "static_vignette", "") or ""
                    hints_text = self._knowledge_retriever.format_discriminator_hints_for_prompt(
                        disease_names,
                        seen_evidence=state.seen_evidence_phenotypes,
                        max_lines=self.config.max_knowledge_prompt_lines,
                        vignette_text=vignette,
                        include_chains=self.config.enable_chain_discoverer,
                    )
                    if hints_text:
                        payload["discriminator_hints"] = hints_text
                except Exception as e:
                    _logger.warning("Knowledge injection for TALP failed: %s", e)

        self._inject_discrimination_profile(
            payload, state, phase="plan_temporary_leaves"
        )
        result = self._call_module(planner_module, payload, validator=_validate_talp)
        leaves = []
        for idx, x in enumerate(result.get("candidate_leaves_ranked", [])):
            # Defensive: validator guarantees the required keys, but guard so a
            # single malformed leaf is skipped rather than aborting the run.
            if not isinstance(x, dict) or not x.get("branch_id") \
                    or not x.get("type") or x.get("content") in (None, ""):
                continue
            raw_tb = x.get("target_branches", {x["branch_id"]: "support"})
            if isinstance(raw_tb, list):
                raw_tb = {bid: "support" for bid in raw_tb}
            leaves.append(
                CandidateLeaf(
                    leaf_id=f"{x['branch_id']}::{x['type']}::{idx}",
                    branch_id=x["branch_id"],
                    leaf_type=x["type"],
                    content=x["content"],
                    expected_information_gain=x.get("expected_information_gain", 0.0),
                    expected_cost=x.get("expected_cost", 0.0),
                    expected_delay=x.get("expected_delay", 0.0),
                    safety_value=x.get("safety_value", 0.0),
                    action_separation_value=x.get("action_separation_value", 0.0),
                    total_score=x.get("score", 0.0),
                    target_branches=raw_tb,
                    primary_function=x.get("primary_function", "confirm"),
                    falsification_value=x.get("falsification_value", 0.0),
                    invasiveness=x.get("invasiveness", 0.0),
                    urgency=x.get("urgency", "routine"),
                    redundancy_group=x.get("redundancy_group", ""),
                    bundle_independence=x.get("bundle_independence", 1.0),
                    result_dependency=x.get("result_dependency", False),
                    why=x.get("why", ""),
                )
            )
        # Legacy: selected_primary_action is no longer emitted by the new TALP
        # prompt, but we still parse it for sdbench mode backward compatibility.
        selected = result.get("selected_primary_action")
        if selected and self._in_sdbench_mode() and selected.get("type") in {"ASK", "TEST", "DIAGNOSE"}:
            mapping = {
                "ASK": "ASK_PATIENT",
                "TEST": "REQUEST_TEST_OR_MEASUREMENT",
                "DIAGNOSE": "DIAGNOSIS_READY",
            }
            selected = {"type": mapping[selected["type"]], "content": selected.get("content", "")}
        return leaves, selected

    def update_estimated_remaining_value(self, state: DiagnosticState) -> None:
        if not state.candidate_leaves:
            state.estimated_remaining_value = 0.0
            return
        state.estimated_remaining_value = max(
            (x.total_score for x in state.candidate_leaves), default=0.0
        )

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def execute_action_bundle(
        self, state: DiagnosticState, bundle: list
    ) -> list[dict]:
        """Execute each action in the bundle sequentially; collect results."""
        bundle_id = state.timestep
        results = []
        for position, action in enumerate(bundle):
            # Normalise: bundle items may be CandidateLeaf objects or plain dicts
            action_dict = _leaf_to_action_dict(action)
            raw_result = self._execute_single_action(state, action_dict, bundle_id, position, len(bundle))
            results.append({"action": action_dict, "raw_result": raw_result})
        return results

    def _execute_single_action(
        self,
        state: DiagnosticState,
        action: dict,
        bundle_id: int,
        bundle_position: int,
        bundle_size: int,
    ) -> dict:
        """Execute one action and append an extended record to actions_taken."""
        action_type = action["type"]
        content = action["content"]

        external_action = action_type
        if self._in_sdbench_mode():
            external_action = self._normalize_sdbench_action(action_type)
        elif self._in_patch_mode():
            external_action = self._normalize_agentclinic_patch_action(action_type)
        elif self._in_static_qa_mode():
            external_action = self._normalize_static_qa_action(action_type)

        state.latest_action_type = action_type
        # Append placeholder; raw_result backfilled after env call
        record: dict = {
            "timestep": state.timestep,
            "bundle_id": bundle_id,
            "bundle_position": bundle_position,
            "bundle_size": bundle_size,
            "action_type": action_type,
            "external_action": external_action,
            "content": content,
            "raw_result": None,       # backfilled below
            "result_summary": "",     # backfilled by annotate_evidence_bundle
        }
        state.actions_taken.append(record)

        raw_result = self._dispatch_env_call(state, action_type, external_action, content)

        # Backfill raw_result into the record we just appended
        state.actions_taken[-1]["raw_result"] = raw_result
        return raw_result

    # Keep backward-compatible single-action entry point used in tests
    def execute_primary_action(self, state, action):
        return self._execute_single_action(state, action, state.timestep, 0, 1)

    def _dispatch_env_call(
        self, state: DiagnosticState, action_type: str, external_action: str, content: str
    ) -> dict:
        """Route the action to the correct environment method."""
        if self._in_static_qa_mode():
            if action_type in {"USE_CALCULATOR", "RETRIEVE_KNOWLEDGE", "RETRIEVE_EXTERNAL_KNOWLEDGE"}:
                gate = self._call_module(
                    "ToolUseGate",
                    {"state": state.project_for("ToolUseGate"), "action_type": action_type, "content": content},
                )
                if not gate.get("allow", False):
                    return {"tool_blocked": True, "reason": gate.get("reason", "blocked")}
                state.tool_use_log.append({
                    "action_type": action_type,
                    "content": content,
                    "justification": gate.get("justification", ""),
                })
            if external_action in {"ANALYZE_VIGNETTE", "SELECT_OPTION"}:
                # evidence_items and options are already present in the state
                # payload passed to EvidenceAnnotator; omit them here to avoid
                # doubling the token cost.
                return {
                    "analysis_target": content,
                    "evidence_items_ref": "see state.static_evidence_items",
                    "question": state.static_question,
                }
            if external_action == "DIAGNOSIS_READY":
                state.benchmark_output_ready = True
                return {"diagnosis_ready": content}

        if self._in_sdbench_mode():
            if external_action == "ASK":
                return (
                    self.env.ask_gatekeeper(content)
                    if hasattr(self.env, "ask_gatekeeper")
                    else self.env.ask_patient(content)
                )
            if external_action == "TEST":
                return (
                    self.env.request_test(content)
                    if hasattr(self.env, "request_test")
                    else self.env.request_test_or_measurement(content)
                )
            if external_action == "DIAGNOSE":
                state.benchmark_output_ready = True
                return {"diagnosis_ready": content}

        if self._in_patch_mode():
            if external_action == "ASK_PATIENT":
                return self.env.ask_patient(content)
            if external_action == "REQUEST_TEST_OR_MEASUREMENT":
                if hasattr(self.env, "request_test_or_measurement"):
                    return self.env.request_test_or_measurement(content)
                if hasattr(self.env, "order_lab"):
                    return self.env.order_lab(content)
                raise ValueError("Environment missing request_test_or_measurement capability")
            if external_action == "USE_NOTEBOOK":
                if not self.config.allow_notebook:
                    raise PermissionError("USE_NOTEBOOK is disabled by configuration")
                return {"notebook_entry": content, "status": "recorded"}
            if external_action == "RETRIEVE_EXTERNAL_KNOWLEDGE":
                if not self.config.allow_external_knowledge:
                    raise PermissionError("External knowledge retrieval is disabled by configuration")
                return {"external_knowledge": self.knowledge_router(content)}
            if external_action == "DIAGNOSIS_READY":
                state.benchmark_output_ready = True
                return {"diagnosis_ready": content}

        # Default / agentclinic non-patch mode
        if action_type == "ASK_PATIENT":
            return self.env.ask_patient(content)
        if action_type in {
            "REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM",
            "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING",
        }:
            if action_type == "REQUEST_TEST_OR_MEASUREMENT" and hasattr(
                self.env, "request_test_or_measurement"
            ):
                return self.env.request_test_or_measurement(content)
            if action_type == "REQUEST_EXAM":
                return self.env.request_exam(content)
            if action_type == "REQUEST_VITAL":
                return self.env.request_vital(content)
            if action_type == "ORDER_LAB":
                return self.env.order_lab(content)
            return self.env.order_imaging(content)
        if action_type == "USE_NOTEBOOK":
            if not self.config.allow_notebook:
                raise PermissionError("USE_NOTEBOOK is disabled by configuration")
            return {"notebook_entry": content, "status": "recorded"}
        if action_type == "USE_CALCULATOR":
            if not self.config.allow_calculator:
                raise PermissionError("USE_CALCULATOR is disabled by configuration")
            return self.calculator_router(content, state)
        if action_type in {"RETRIEVE_KNOWLEDGE", "RETRIEVE_EXTERNAL_KNOWLEDGE"}:
            if not self.config.allow_external_knowledge:
                raise PermissionError("External knowledge retrieval is disabled by configuration")
            return {"external_knowledge": self.knowledge_router(content)}
        if action_type == "DIAGNOSIS_READY":
            state.benchmark_output_ready = True
            return {"diagnosis_ready": content}
        raise ValueError(f"Unknown action type: {action_type}")

    # ------------------------------------------------------------------
    # Action type normalisation (adapter layer)
    # ------------------------------------------------------------------

    def _normalize_sdbench_action(self, action_type: str) -> str:
        if action_type == "ASK_PATIENT":
            return "ASK"
        if action_type in {
            "REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM",
            "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING",
        }:
            return "TEST"
        if action_type == "DIAGNOSIS_READY":
            return "DIAGNOSE"
        raise ValueError(f"Illegal SDbench action type: {action_type}")

    def _normalize_agentclinic_patch_action(self, action_type: str) -> str:
        if action_type == "ASK_PATIENT":
            return "ASK_PATIENT"
        if action_type in {
            "REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM",
            "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING",
        }:
            return "REQUEST_TEST_OR_MEASUREMENT"
        if action_type in {"RETRIEVE_KNOWLEDGE", "RETRIEVE_EXTERNAL_KNOWLEDGE"}:
            return "RETRIEVE_EXTERNAL_KNOWLEDGE"
        if action_type in {"USE_NOTEBOOK", "DIAGNOSIS_READY"}:
            return action_type
        raise ValueError(f"Illegal AgentClinic patch action type: {action_type}")

    def _normalize_static_qa_action(self, action_type: str) -> str:
        if action_type in {"ANALYZE_VIGNETTE", "SELECT_OPTION", "DIAGNOSIS_READY"}:
            return action_type
        if action_type in {
            "ASK_PATIENT", "REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM",
            "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING",
        }:
            return "ANALYZE_VIGNETTE"
        # Graceful fallback: unknown types are treated as vignette analysis
        return "ANALYZE_VIGNETTE"

    # ------------------------------------------------------------------
    # Evidence annotation (single and bundle)
    # ------------------------------------------------------------------

    def _build_annotator_payload(self, state: DiagnosticState, raw_result) -> dict:
        """Build annotator payload, optionally injecting LR reference data."""
        payload = {"state": state.project_for("EvidenceAnnotator"), "raw_result": raw_result}
        if self._knowledge_retriever and self.config.enable_knowledge_injection:
            live_branches = [
                b for b in state.branches.values()
                if b.status not in ("closed_for_now", "expanded")
            ]
            disease_names = [b.label for b in live_branches]
            # §21.8a: canonical representative diseases resolve the specific
            # entity behind a broad family. Queried CACHE/MARKER-ONLY (fast) —
            # see _reconcile_annotation_with_kb for why RAG-per-rep is fatal.
            rep_names: list[str] = []
            if (self.config.enable_representative_disease_lr
                    or getattr(self.config, "enable_taxonomy_entities", False)
                    or getattr(self.config, "enable_branch_knowledge", False)):
                seen = {d.lower() for d in disease_names}
                for b in live_branches:
                    for rd in getattr(b, "representative_diseases", None) or []:
                        if rd.lower() not in seen:
                            seen.add(rd.lower())
                            rep_names.append(rd)
            # Match this turn's evidence to phenotypes first (populates the
            # accumulated phenotype set used for atomic finding extraction).
            finding_text = ""
            if state.actions_taken:
                finding_text = state.actions_taken[-1].get("content", "")
            if finding_text:
                try:
                    matches = self._knowledge_retriever.match_evidence_to_phenotypes(
                        [finding_text], threshold=0.3
                    )
                    for ev, match_list in matches.items():
                        for m in match_list:
                            state.seen_evidence_phenotypes.add(m["phenotype"])
                except Exception:
                    pass

            # Inject LR reference using ATOMIC findings (clean symptom phrases),
            # not the verbose discriminator question — the LR cache/markers are
            # keyed by short symptom terms (see _gather_atomic_findings).
            atomic = self._gather_atomic_findings(state)
            if atomic and disease_names:
                blocks: list[str] = []
                for f in atomic[:8]:
                    try:
                        t = self._knowledge_retriever.format_lr_reference_for_prompt(
                            f, disease_names,
                            fast=not self.config.enable_lr_rag_fallback,
                        )
                    except Exception as e:
                        # One malformed finding must NOT drop the rest of this
                        # turn's LR evidence (§13): skip it, keep injecting the
                        # remaining atomic findings' references.
                        _logger.warning("LR injection for Annotator failed on "
                                        "%r: %s", f, e)
                        continue
                    if t:
                        blocks.append(t)
                    if rep_names:  # cache/marker-only rep-disease reference
                        try:
                            t2 = self._knowledge_retriever.format_lr_reference_for_prompt(
                                f, rep_names, fast=True,
                            )
                            if t2:
                                blocks.append(t2)
                        except Exception as e:  # pragma: no cover - defensive
                            _logger.debug("rep-disease LR injection failed: %s", e)
                if blocks:
                    payload["lr_reference"] = "\n".join(blocks)[:4000]

            # §21.8b: pivotal-clue surfacing + anti-anchoring. Find the single
            # strongest finding→disease association this turn and surface it so
            # the annotator does not anchor on the common/framed diagnosis when
            # a specific finding most strongly implicates a different branch.
            if self.config.enable_anti_anchoring and atomic and (disease_names or rep_names):
                hint = self._compute_pivotal_hint(atomic, disease_names, rep_names)
                if hint:
                    payload["pivotal_evidence_hint"] = hint

        self._inject_discrimination_profile(
            payload, state, phase="evidence_annotator"
        )
        return payload

    def _compute_pivotal_hint(self, atomic: list[str], disease_names: list[str],
                              rep_names: list[str] | None = None) -> str:
        """Strongest (finding → disease, LR+) pairs this turn, as an anti-anchoring
        hint. Deterministic; reuses the LR retriever. Returns "" if nothing
        clearly discriminating is found. Representative-disease names are queried
        cache/marker-only (fast) to avoid the RAG fan-out stall (§21.8a)."""
        cfg = self.config
        # A pivotal clue need not be pathognomonic (LR+≥10); LR+≥5 already
        # outweighs most base-rate anchoring, so surface those too.
        pivotal_lr = 5.0
        best: list[tuple[float, str, str]] = []  # (lr+, finding, disease)
        for f in atomic[:8]:
            lr_items: dict = {}
            try:
                ref = self._knowledge_retriever.get_lr_reference(
                    f, disease_names, fast=not cfg.enable_lr_rag_fallback,
                )
                lr_items.update(ref.get("lr_data") or {})
            except Exception:  # pragma: no cover - defensive
                pass
            if rep_names:
                try:
                    ref2 = self._knowledge_retriever.get_lr_reference(
                        f, rep_names, fast=True,
                    )
                    for k, v in (ref2.get("lr_data") or {}).items():
                        if lr_items.get(k) is None:
                            lr_items[k] = v
                except Exception:  # pragma: no cover - defensive
                    pass
            for dis, entry in lr_items.items():
                if not isinstance(entry, dict):
                    continue
                # Exclude noisy/RAG-derived LRs: a "pivotal" hint built on a
                # hallucinated frequency estimate (e.g. spurious 'Hypertension'
                # LR+=6 → lymphoid) actively de-anchors AWAY from the correct
                # common diagnosis (observed: anti-anchoring alone 5/9 → 1/9).
                conf = str(entry.get("confidence", "")).lower()
                src = str(entry.get("source", "")).lower()
                if not cfg.rag_lr_can_override_direction and (
                    conf in ("rag_qualitative", "rag_extracted", "context", "low")
                    or "rag-quant" in src or "rag_quant" in src
                ):
                    continue
                lr = entry.get("lr_positive")
                try:
                    lr = float(lr) if lr is not None else None
                except (TypeError, ValueError):
                    lr = None
                # Only genuinely discriminating, present-direction signals.
                if lr is not None and lr >= pivotal_lr:
                    best.append((lr, f, dis))
        if not best:
            return ""
        best.sort(reverse=True)
        seen: set[str] = set()
        lines: list[str] = []
        for lr, f, dis in best:
            if dis.lower() in seen:
                continue
            seen.add(dis.lower())
            lines.append(f"  • '{f}' most strongly suggests {dis} (LR+≈{lr:.1f})")
            if len(lines) >= 3:
                break
        # §22.3 (B′): NEUTRAL FACTUAL surfacing only. The earlier wording told the
        # annotator to override "the most common or initially-framed diagnosis",
        # which biased it AWAY from correct common diagnoses (5/9→1/9, §21.13.3).
        # We now state the curated association as a fact and ask only that each
        # branch's effect be CONSISTENT with it — the anti-anchoring is carried by
        # the mechanical numeric LR update (kb_numeric_lr) in
        # _reconcile_annotation_with_kb, not by a contrarian instruction here.
        return (
            "CURATED FINDING→DISEASE ASSOCIATIONS (high specificity this turn). "
            "These are evidence-based likelihood ratios; make sure each branch's "
            "assigned effect is consistent with them (a finding with a high LR+ for "
            "a disease is supporting evidence for that branch):\n"
            + "\n".join(lines)
        )

    def annotate_evidence(self, state: DiagnosticState, raw_result) -> dict:
        """Annotate a single result (backward-compatible path)."""
        annotation = self._call_module(
            "EvidenceAnnotator", self._build_annotator_payload(state, raw_result)
        )
        annotation = self._clean_annotation(state, annotation)
        annotation = self._reconcile_annotation_with_kb(state, annotation)
        # Backfill result_summary into the latest actions_taken record
        if state.actions_taken:
            state.actions_taken[-1]["result_summary"] = annotation.get("result_summary", "")
        return annotation

    def annotate_evidence_bundle(
        self, state: DiagnosticState, bundle_results: list[dict]
    ) -> dict:
        """Annotate all results from a bundle in a single LLM call."""
        if len(bundle_results) == 1:
            return self.annotate_evidence(state, bundle_results[0]["raw_result"])

        bundle_payload = self._build_annotator_payload(state, bundle_results)
        annotation = self._call_module(
            "EvidenceAnnotator",
            bundle_payload,
        )
        annotation = self._clean_annotation(state, annotation)
        annotation = self._reconcile_annotation_with_kb(state, annotation)

        bundle_size = len(bundle_results)
        per_action = annotation.get("per_action_effects", [])

        if per_action and len(per_action) >= bundle_size:
            records = state.actions_taken[-bundle_size:]
            for i, record in enumerate(records):
                entry = per_action[i] if i < len(per_action) else {}
                record["result_summary"] = entry.get("micro_summary", "")
                record["per_action_branch_effects"] = entry.get("branch_effects", {})
        else:
            summary = annotation.get("result_summary", "")
            for record in state.actions_taken[-bundle_size:]:
                record["result_summary"] = summary

        self._update_branch_evidence_lists_bundle(state, annotation, bundle_size)

        return annotation

    def _clean_annotation(self, state: DiagnosticState, annotation: dict) -> dict:
        """Validate branch IDs; force expanded branches to neutral."""
        valid_ids = set(state.branches.keys())
        cleaned: dict = {
            bid: effect
            for bid, effect in annotation.get("branch_effects", {}).items()
            if bid in valid_ids
        }
        for bid in valid_ids:
            cleaned.setdefault(bid, "neutral")
        # Expanded branches are container nodes; their posterior is aggregated
        # from children, so direct evidence effects must be ignored.
        for bid, branch in state.branches.items():
            if branch.status == "expanded":
                cleaned[bid] = "neutral"
        annotation["branch_effects"] = cleaned
        return annotation

    # Approximate odds-multipliers (LR-like) for qualitative effect bands.
    # Used to blend the LLM's qualitative judgement with grounded numeric LRs
    # in the Bayesian (calculator) update path (F2).
    _EFFECT_PSEUDO_LR: dict[str, float] = {
        "strong_for": 8.0,
        "moderate_for": 3.0,
        "weak_for": 1.5,
        "neutral": 1.0,
        "weak_against": 0.67,
        "moderate_against": 0.33,
        "strong_against": 0.125,
    }

    @staticmethod
    def _effect_sign(label: str) -> int:
        if "for" in label:
            return 1
        if "against" in label:
            return -1
        return 0

    def _raw_atomic_facts(self, state: DiagnosticState) -> list[str]:
        """Raw atomic clinical facts (lossless boundaries) for the current turn.

        Source of truth is the structured evidence JSON VignetteParser produced
        (``state.static_evidence_items``); interactive mode falls back to the
        most recent observed result summaries. Shared by the present-finding and
        normal-value (LR-) extraction paths.
        """
        raw_facts: list[str] = []
        seen_raw: set[str] = set()

        def _add_raw(text: str) -> None:
            t = (text or "").strip(" \t-•*").strip()
            key = t.lower()
            if t and key not in seen_raw and any(ch.isalpha() for ch in t):
                seen_raw.add(key)
                raw_facts.append(t)

        for ev in getattr(state, "static_evidence_items", None) or []:
            content = ev.get("content", "") if isinstance(ev, dict) else getattr(ev, "content", "")
            _add_raw(str(content))

        if not raw_facts and not self._in_static_qa_mode():
            for a in state.actions_taken[-4:]:
                if isinstance(a, dict) and a.get("result_summary"):
                    _add_raw(str(a["result_summary"]))

        return raw_facts[:40]

    def _gather_normal_ruleout_findings(self, state: DiagnosticState) -> list[str]:
        """Abnormal phenotypes NEGATED by NORMAL lab/vital values this turn.

        Implements the LR- rule-out channel (EXTERNAL_KNOWLEDGE §12.8, B1 §7):
        a value in the normal range is legitimate evidence AGAINST diseases that
        (near-)always produce the corresponding abnormality. ``FindingNormalizer``
        flags such normal results (direction="N") and lists the abnormal
        phenotype(s) they negate in ``negated_hpo_terms``; we surface those so the
        reconciliation step can apply LR-=(1-Sn)/Sp with the finding treated as
        ABSENT. Gated by ``enable_normal_value_ruleout`` (default off).

        Returns [] when the gate is off, no normalizer is wired, or nothing
        normal/recognised is present.
        """
        if not self.config.enable_normal_value_ruleout:
            return []
        if self._knowledge_retriever is None:
            return []
        normalizer = getattr(self._knowledge_retriever, "finding_normalizer", None)
        if normalizer is None:
            return []

        out: list[str] = []
        seen: set[str] = set()

        def _add(term: str) -> None:
            key = (term or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(term.strip())

        for raw in self._raw_atomic_facts(state):
            # (a) NUMERIC normals: normalizer flags direction="N" and lists the
            # abnormal phenotype(s) the normal value negates.
            try:
                norms = normalizer.normalize_multi(raw)
            except Exception:  # pragma: no cover - defensive
                norms = []
            for norm in norms:
                if norm.direction == "N":
                    for term in getattr(norm, "negated_hpo_terms", None) or []:
                        _add(term)
            # (b) FREE-TEXT pertinent negatives ("no murmur", "abdomen
            # unremarkable"): map the negated abnormality to phenotype term(s).
            neg = _extract_negated_phenotype(raw)
            if neg is None:
                continue
            if neg.startswith("__system__:"):
                system = neg.split(":", 1)[1]
                for term in _NORMAL_SYSTEM_NEGATES.get(system, []):
                    _add(term)
                continue
            # Explicit named phenotype → controlled vocabulary via embedding.
            mapped = False
            try:
                matches = self._knowledge_retriever.match_evidence_to_phenotypes(
                    [neg], threshold=0.5
                )
                for m in matches.get(neg) or []:
                    pheno = m.get("phenotype", "")
                    if pheno:
                        _add(pheno)
                        mapped = True
                        break
            except Exception:  # pragma: no cover - defensive
                pass
            if not mapped:
                _add(neg)  # lossless fallback: query KB with the negated phrase
        return out[:15]

    def _gather_atomic_findings(self, state: DiagnosticState) -> list[str]:
        """Atomic, KB-queryable findings for the current turn (LOSSLESS path).

        The LR cache / marker index are keyed by SHORT symptom phrases, so we
        must query clean atomic findings (e.g. 'basophilia', 'splenomegaly'),
        NOT a free-text blob (the matcher embeds each item as one vector, so
        whole sentences / hypothesis-laden reasoning yield spurious matches).

        Source of truth is the structured evidence JSON that VignetteParser
        already produced — ``state.static_evidence_items`` — where each
        ``EvidenceItem.content`` is one atomic clinical fact. Interactive mode
        (no structured items) falls back to observed test/exam result summaries.

        Two-stage mapping per atomic fact:
          1. Numeric lab/vital → deterministic, VALUE-DIRECTION-AWARE HPO term
             via ``FindingNormalizer`` (e.g. "35% blasts" → "Elevated blast
             count", "Hemoglobin 10 g/dL" → "Decreased hemoglobin"). This avoids
             the embedding's direction-blind mis-maps (e.g. "Temperature 100°F"
             → "Cold skin temperature", "Pulse 120/min" → "Absent pulse"). When
             the normalizer recognises a lab whose value is NORMAL (or it cannot
             map the direction), the fact is SKIPPED rather than embedded —
             feeding a normal vital to the embedder is exactly what produced
             spurious abnormal phenotypes.
          2. Qualitative findings the normalizer does not recognise (e.g.
             "night sweats", "splenomegaly", "erythematous rash") → controlled
             phenotype vocabulary via embedding (one clean fact per vector).
             Raw fact retained as a lossless fallback when nothing maps.

        Returns [] when nothing is available (logged as a coverage gap).
        """
        if self._knowledge_retriever is None:
            return []

        raw_facts = self._raw_atomic_facts(state)
        if not raw_facts:
            return []

        findings: list[str] = []
        seen: set[str] = set()

        def _add(term: str) -> None:
            t = (term or "").strip()
            key = t.lower()
            if t and key not in seen:
                seen.add(key)
                findings.append(t)

        # ── Stage 1: deterministic numeric lab/vital normalization ──────────
        # Use normalize_multi so COMPOUND facts (e.g. "Leukocyte count:
        # 57,500/mm3 with 35% blasts") yield BOTH atomic findings (Leukocytosis
        # + Elevated blast count) instead of one garbled mis-map.
        normalizer = getattr(self._knowledge_retriever, "finding_normalizer", None)
        qualitative: list[str] = []  # facts the normalizer didn't recognise
        for raw in raw_facts:
            # Demographics (age/sex) are EPIDEMIOLOGY, not findings → they feed
            # the structured prior, never the finding→LR path.
            if _is_demographic_fact(raw):
                continue
            # Pertinent negatives ("no murmur", "abdomen unremarkable") are NOT
            # present findings; they are routed to the LR- rule-out channel by
            # _gather_normal_ruleout_findings. Skip here to avoid mis-scoring
            # the negated abnormality as PRESENT.
            if _extract_negated_phenotype(raw) is not None:
                continue
            norms = []
            if normalizer is not None:
                try:
                    norms = normalizer.normalize_multi(raw)
                except Exception:  # pragma: no cover - defensive
                    norms = []
            if not norms:
                # Not a numeric lab/vital → qualitative symptom; embed it.
                qualitative.append(raw)
                continue
            mapped_any = False
            for norm in norms:
                if norm.hpo_term:
                    # Recognised lab with abnormal, direction-correct HPO term.
                    _add(norm.hpo_term)
                    mapped_any = True
                # else: recognised lab that is NORMAL / unmappable direction →
                # intentionally skipped (do NOT embed a normal vital).
            if not mapped_any:
                # All clauses recognised but none abnormal → skip (normal vital).
                continue

        # ── Stage 2: embedding phenotype mapping for qualitative findings ───
        if qualitative:
            try:
                matches = self._knowledge_retriever.match_evidence_to_phenotypes(
                    qualitative, threshold=0.5
                )
            except Exception as e:  # pragma: no cover - defensive
                _logger.debug("atomic finding match failed: %s", e)
                matches = {}
            for raw in qualitative:
                mlist = matches.get(raw) or []
                if mlist:
                    _add(mlist[0].get("phenotype", ""))  # top-1 mapped phenotype
                else:
                    _add(raw)  # lossless fallback: query cache with the fact

        return findings[:15]

    def _kb_entry_to_signal(self, entry: dict):
        """Map a KB LR entry to ``(desired_effect, lr_pos, rank, is_floor)`` or
        ``None`` when the signal is too weak to act on.

        rank orders strength for picking the single strongest signal per branch:
        3 = pathognomonic inclusion (posterior floor), 2 = strong exclusion /
        argues-against, 1 = strong inclusion. Thresholds come from config so the
        behaviour matches the original per-branch logic exactly.
        """
        cfg = self.config
        conf = str(entry.get("confidence", "")).lower()
        marker_type = str(entry.get("marker_type", "")).lower()
        lr_pos = entry.get("lr_positive")
        try:
            lr_pos = float(lr_pos) if lr_pos is not None else None
        except (TypeError, ValueError):
            lr_pos = None
        is_exclusion = "exclusion" in conf or "exclud" in marker_type
        # Skip non-quantitative context snippets (RAG/PubMed context, no real LR)
        # — these are noisy and must never drive a direction override.
        noisy_conf = {"context-only", "context", "low", "indirect_chain"}
        # RAG-derived LRs (qual→quant) are frequency-language estimates with a
        # GUESSED specificity; field evidence showed them spuriously overriding
        # the LLM (e.g. "weight loss" LR+=0.15 → forced moderate_against). They
        # inform the prompt but must NOT drive a deterministic direction override
        # unless explicitly allowed (P1/P2 experiments).
        if not cfg.rag_lr_can_override_direction:
            noisy_conf = noisy_conf | {"rag_qualitative", "rag_extracted"}
        noisy = conf in noisy_conf
        if conf == "pathognomonic" and (
            lr_pos is None or lr_pos >= cfg.pathognomonic_lr_floor_threshold
        ):
            return ("strong_for", lr_pos, 3, True)
        if is_exclusion or (
            not noisy and lr_pos is not None and lr_pos <= cfg.strong_exclusion_lr_threshold
        ):
            return ("moderate_against", lr_pos, 2, False)
        # Strong inclusion is driven by the LR VALUE (EBM band), NOT the textual
        # confidence label: genuine cache entries are mostly tagged "medium" yet
        # carry conclusive LRs (e.g. basophilia→CML LR+=10.9). Requiring "high"
        # confidence here is exactly what made F1 inert in practice.
        if not noisy and lr_pos is not None and lr_pos >= cfg.strong_inclusion_lr_threshold:
            return ("moderate_for", lr_pos, 1, False)
        return None

    def _reconcile_annotation_with_kb(
        self, state: DiagnosticState, annotation: dict
    ) -> dict:
        """F1/F2: ground the annotator's qualitative branch_effects against the KB.

        A HIGH-confidence directional KB signal (pathognomonic marker,
        pathognomonic exclusion, or a strong EBM LR band) overrides a
        contradicting (or neutral) LLM sign. (Near-)pathognomonic hits also
        yield a per-branch numeric LR (enabling the Bayesian update) and flag
        the branch for a posterior floor. Conservative by design: only
        high-confidence hits override — noisy fuzzy LR never does.
        """
        cfg = self.config
        if not (cfg.enable_kb_direction_reconciliation
                and self._knowledge_retriever is not None
                and cfg.enable_knowledge_injection):
            return annotation

        atomic_findings = self._gather_atomic_findings(state)
        ruleout_findings = self._gather_normal_ruleout_findings(state)
        if not atomic_findings and not ruleout_findings:
            _logger.info("[%s t%s] KB reconcile: no atomic findings mapped "
                         "(phenotype match empty) — coverage gap",
                         getattr(state, "case_id", "?"),
                         getattr(state, "timestep", "?"))
            return annotation

        effects: dict[str, str] = dict(annotation.get("branch_effects", {}))
        diagnosable = {
            bid: b for bid, b in state.branches.items() if b.status != "expanded"
        }
        if not diagnosable:
            return annotation

        # First label wins (verbose LLM labels may collide after normalization).
        # §21.8a: also register each branch's canonical representative_diseases
        # as query strings → the disease-keyed LR cache can HIT on the specific
        # entity even though the family LABEL is intentionally too broad to key.
        # CRITICAL: representative diseases are queried CACHE/MARKER-ONLY (fast=
        # True, no RAG fallback). Letting RAG fire per rep-disease multiplied the
        # lookup fan-out by (1+#rep)×#branches; since RAG encode calls are
        # globally serialized, 9-way concurrency collapsed to a near-serial stall
        # (cases frozen >1 h). Canonical entities should hit the curated cache
        # directly; a miss must stay cheap.
        label_to_bid: dict[str, str] = {}
        for bid, b in diagnosable.items():
            label_to_bid.setdefault(b.label, bid)
        branch_labels = list(label_to_bid.keys())  # base path (RAG per run cfg)
        rep_labels: list[str] = []                  # §21.8a fast-only path
        if (cfg.enable_representative_disease_lr
                or getattr(cfg, "enable_taxonomy_entities", False)
                or getattr(cfg, "enable_branch_knowledge", False)):
            for bid, b in diagnosable.items():
                for rd in getattr(b, "representative_diseases", None) or []:
                    if rd not in label_to_bid:
                        label_to_bid[rd] = bid
                        rep_labels.append(rd)

        overrides: list[dict] = []
        kb_numeric_lr: dict[str, float] = {}
        floor_branches: list[str] = []
        recon_trace: list[dict] = []

        # One lookup per ATOMIC finding (covering all branch labels at once);
        # keep the STRONGEST directional signal per branch so correlated
        # findings are not double-counted.
        best_signal: dict[str, dict] = {}
        for finding in atomic_findings:
            lr_map: dict = {}
            try:
                ref = self._knowledge_retriever.get_lr_reference(
                    finding, branch_labels,
                    fast=not self.config.enable_lr_rag_fallback,
                )
                lr_map.update(ref.get("lr_data") or {})
            except Exception as e:  # pragma: no cover - defensive
                _logger.debug("KB reconcile lookup failed for %r: %s", finding, e)
                continue
            if rep_labels:  # §21.8a: cache/marker-only (fast), never RAG
                try:
                    ref2 = self._knowledge_retriever.get_lr_reference(
                        finding, rep_labels, fast=True,
                    )
                    for k, v in (ref2.get("lr_data") or {}).items():
                        if lr_map.get(k) is None:
                            lr_map[k] = v
                except Exception as e:  # pragma: no cover - defensive
                    _logger.debug("rep-disease lookup failed for %r: %s", finding, e)
            for label, entry in lr_map.items():
                if not isinstance(entry, dict):
                    continue
                bid = label_to_bid.get(label)
                if bid is None:
                    continue
                sig = self._kb_entry_to_signal(entry)
                if sig is None:
                    continue
                desired, lr_pos, rank, is_floor = sig
                prev = best_signal.get(bid)
                if (prev is None or rank > prev["rank"]
                        or (rank == prev["rank"]
                            and abs((lr_pos or 1.0) - 1.0) > abs((prev["lr_pos"] or 1.0) - 1.0))):
                    best_signal[bid] = {
                        "entry": entry, "finding": finding, "desired": desired,
                        "lr_pos": lr_pos, "rank": rank, "is_floor": is_floor,
                    }

        for bid, branch in diagnosable.items():
            current = effects.get(bid, "neutral")
            sig = best_signal.get(bid)
            if sig is None:
                recon_trace.append({"branch": branch.label, "kb": "MISS",
                                    "llm_effect": current})
                continue
            desired = sig["desired"]
            lr_pos = sig["lr_pos"]
            entry = sig["entry"]
            conf = str(entry.get("confidence", "")).lower()
            if desired == "strong_for":
                kb_numeric_lr[bid] = lr_pos if lr_pos else 100.0
                if sig["is_floor"]:
                    floor_branches.append(bid)
            elif lr_pos is not None:
                kb_numeric_lr[bid] = lr_pos
            trace_rec = {
                "branch": branch.label, "kb": "HIT", "finding": sig["finding"],
                "confidence": conf, "lr_positive": lr_pos,
                "kb_source": entry.get("source", ""), "llm_effect": current,
                "kb_desired": desired, "overridden": False,
            }
            if self._effect_sign(current) != self._effect_sign(desired):
                effects[bid] = desired
                trace_rec["overridden"] = True
                overrides.append({
                    "branch_id": bid, "from": current, "to": desired,
                    "lr_positive": lr_pos, "confidence": conf,
                    "source": entry.get("source", ""),
                })
            recon_trace.append(trace_rec)

        # ── LR- rule-out channel: NORMAL values argue against diseases that ──
        # (near-)always produce the negated abnormality. Applied AFTER present
        # signals and never to pathognomonic-floored branches. Multiplies into
        # the per-branch LR (independent evidence → odds multiply).
        if ruleout_findings:
            best_ruleout: dict[str, dict] = {}  # bid → strongest (smallest LR-)
            for finding in ruleout_findings:
                try:
                    ref = self._knowledge_retriever.get_lr_reference(
                        finding, branch_labels,
                        fast=not self.config.enable_lr_rag_fallback,
                    )
                except Exception as e:  # pragma: no cover - defensive
                    _logger.debug("rule-out lookup failed for %r: %s", finding, e)
                    continue
                for label, entry in (ref.get("lr_data") or {}).items():
                    if not isinstance(entry, dict):
                        continue
                    bid = label_to_bid.get(label)
                    if bid is None or bid in floor_branches:
                        continue
                    # P1/P2: direction consistency — never let a normal finding
                    # push DOWN a branch the present-finding path supported (or,
                    # under the stricter gate, moved at all) this same turn.
                    present_effect = effects.get(bid, "neutral")
                    if present_effect in ("strong_for", "moderate_for", "weak_for"):
                        continue
                    if (cfg.ruleout_require_present_path_silent
                            and present_effect != "neutral"):
                        continue
                    # RAG-quant sources are frequency-language Sn estimates with
                    # a GUESSED Sp; field evidence (case 13/24) showed a NORMAL
                    # temperature spuriously ruling out branches via a
                    # hallucinated "Hypothermia Sn=0.95". A rule-out must rest on
                    # a CURATED Sn/Sp, not RAG-quant — unless explicitly allowed.
                    src = str(entry.get("source", "")).lower()
                    conf = str(entry.get("confidence", "")).lower()
                    if not cfg.rag_lr_can_override_direction and (
                        "rag-quant" in src or "rag_quant" in src
                        or conf in ("rag_qualitative", "rag_extracted")
                    ):
                        continue
                    try:
                        sn = float(entry.get("sensitivity"))
                        lr_neg = float(entry.get("lr_negative"))
                    except (TypeError, ValueError):
                        continue
                    # P1 Sp gate: SnNout is only safe with a credible specificity.
                    if cfg.ruleout_min_specificity > 0:
                        sp = entry.get("specificity")
                        try:
                            sp = float(sp) if sp is not None else None
                        except (TypeError, ValueError):
                            sp = None
                        if sp is None or sp < cfg.ruleout_min_specificity:
                            continue
                    # Only a HIGHLY-sensitive finding, when ABSENT, is a
                    # meaningful rule-out; require a confidently below-1 LR-.
                    if (sn < cfg.ruleout_min_sensitivity
                            or lr_neg > cfg.ruleout_lr_negative_threshold
                            or lr_neg <= 0):
                        continue
                    prev = best_ruleout.get(bid)
                    if prev is None or lr_neg < prev["lr_neg"]:
                        best_ruleout[bid] = {
                            "finding": finding, "lr_neg": lr_neg, "sn": sn,
                            "source": entry.get("source", ""),
                        }
            for bid, ro in best_ruleout.items():
                lr_neg = ro["lr_neg"]
                # combine with any present signal (default 1.0 = no movement)
                kb_numeric_lr[bid] = kb_numeric_lr.get(bid, 1.0) * lr_neg
                # nudge qualitative effect toward "against" only if not already
                # supported by a present inclusion this turn.
                if effects.get(bid, "neutral") in ("neutral", "weak_against"):
                    effects[bid] = "moderate_against"
                recon_trace.append({
                    "branch": diagnosable[bid].label, "kb": "RULEOUT",
                    "finding": ro["finding"], "lr_negative": lr_neg,
                    "sensitivity": ro["sn"], "kb_source": ro["source"],
                })

        if recon_trace:
            n_hit = sum(1 for r in recon_trace if r["kb"] == "HIT")
            n_miss = sum(1 for r in recon_trace if r["kb"] == "MISS")
            _logger.info(
                "[%s t%s] KB reconcile: %d branches | %d HIT, %d MISS, %d override | findings=%s | %s",
                getattr(state, "case_id", "?"), getattr(state, "timestep", "?"),
                len(recon_trace), n_hit, n_miss, len(overrides),
                atomic_findings, recon_trace,
            )

        if not overrides and not kb_numeric_lr:
            return annotation

        annotation = dict(annotation)
        annotation["branch_effects"] = effects
        if overrides:
            annotation["kb_overrides"] = overrides
            _logger.info("KB direction reconciliation applied %d override(s): %s",
                         len(overrides),
                         [(o["branch_id"], o["from"], "→", o["to"]) for o in overrides])
        # F2: when at least one grounded numeric LR exists, build a full
        # per-branch LR vector (KB numeric where available, else derived from
        # the qualitative effect) so the Bayesian update can run coherently.
        if kb_numeric_lr and cfg.enable_numeric_lr_update:
            branch_lr: dict[str, float] = {}
            for bid in diagnosable:
                if bid in kb_numeric_lr:
                    branch_lr[bid] = kb_numeric_lr[bid]
                else:
                    branch_lr[bid] = self._EFFECT_PSEUDO_LR.get(
                        effects.get(bid, "neutral"), 1.0
                    )
            annotation["branch_lr"] = branch_lr
        if floor_branches:
            annotation["_pathognomonic_floor_branches"] = floor_branches
        return annotation

    def _update_branch_evidence_lists(
        self, state: DiagnosticState, annotation: dict
    ) -> None:
        """Append the result summary to branch.evidence_for/against based on effects."""
        summary = annotation.get("result_summary", "")
        if not summary:
            return
        for bid, effect in annotation.get("branch_effects", {}).items():
            branch = state.branches.get(bid)
            if branch is None or branch.status == "expanded":
                continue
            if "for" in effect:      # strong_for / moderate_for / weak_for
                branch.evidence_for.append(summary)
            elif "against" in effect:
                branch.evidence_against.append(summary)

    def _update_branch_evidence_lists_bundle(
        self, state: DiagnosticState, annotation: dict, bundle_size: int
    ) -> None:
        """Use per-action micro_summaries when available; fall back to aggregate."""
        per_action = annotation.get("per_action_effects", [])
        if per_action and len(per_action) >= bundle_size:
            for entry in per_action:
                micro = entry.get("micro_summary", "")
                if not micro:
                    continue
                for bid, effect in entry.get("branch_effects", {}).items():
                    branch = state.branches.get(bid)
                    if branch is None or branch.status == "expanded":
                        continue
                    if "for" in effect:
                        branch.evidence_for.append(micro)
                    elif "against" in effect:
                        branch.evidence_against.append(micro)
        else:
            self._update_branch_evidence_lists(state, annotation)

    # ------------------------------------------------------------------
    # Correlated evidence grouper (MULTI_ACTION_DESIGN_REVISION §10.7)
    # ------------------------------------------------------------------

    _STRONG_LABELS: frozenset[str] = frozenset({"strong_for", "strong_against"})
    _DOWNGRADE_MAP: dict[str, str] = {
        "strong_for": "moderate_for",
        "strong_against": "moderate_against",
    }

    def group_correlated_evidence(
        self, annotation: dict, bundle: "list[CandidateLeaf]"
    ) -> dict:
        """Attenuate double-counting when a multi-action bundle produces multiple
        aligned strong effects on the same branch.

        When bundle_size == 1 this is a no-op.  For larger bundles the
        EvidenceAnnotator has already tried to aggregate, but it cannot know
        whether two tests (e.g. troponin + ischemic ECG) are statistically
        correlated.  As a conservative correction we downgrade "strong"
        aggregate effects to "moderate" when:
          - bundle has more than one action AND
          - the annotation signals a single strong direction without the
            annotator having explicitly flagged net cancellation.

        Note: A full implementation would require per-action effect traces
        (before they are merged in annotate_evidence_bundle).  The current
        approach is a safe, conservative approximation.
        """
        if len(bundle) <= 1:
            return annotation
        effects: dict[str, str] = annotation.get("branch_effects", {})
        updated: dict[str, str] = {}
        for bid, label in effects.items():
            if label in self._STRONG_LABELS:
                updated[bid] = self._DOWNGRADE_MAP[label]
            else:
                updated[bid] = label
        annotation = dict(annotation)
        annotation["branch_effects"] = updated
        return annotation

    # ------------------------------------------------------------------
    # Probability update
    # ------------------------------------------------------------------

    def apply_probability_update(
        self, state: DiagnosticState, annotation: dict, method: str
    ) -> None:
        """Dispatch to the appropriate probability update strategy."""
        gate = bool(getattr(self.config, "enable_discrimination_gate", False))
        if method == "calculator":
            calculator_result = self.calculator_router(
                annotation.get("result_summary", ""), state
            )
            annotation["_calculator_result"] = calculator_result
            posteriors = calculator_update(state.branches, annotation,
                                           calculator_result, gate=gate)
        elif method == "rule_based":
            posteriors = rule_based_update(state.branches, annotation)
        else:
            posteriors = ordinal_update(state.branches, annotation, gate=gate)

        for bid, branch in state.branches.items():
            branch.prior = branch.posterior
            branch.posterior = posteriors[bid]

        # F1: pathognomonic posterior floor (recovers planned §11.9.5.4). When a
        # (near-)pathognomonic finding supports a branch, that branch's posterior
        # cannot be dragged below the floor by indirect counter-evidence.
        self._apply_pathognomonic_floor(state, annotation)

        if annotation.get("major_update", False):
            self._handle_major_update(state, annotation)

    def _apply_pathognomonic_floor(
        self, state: DiagnosticState, annotation: dict
    ) -> None:
        floor_branches = [
            bid for bid in annotation.get("_pathognomonic_floor_branches", [])
            if bid in state.branches
        ]
        if not floor_branches:
            return
        floor = self.config.pathognomonic_posterior_floor
        changed = False
        for bid in floor_branches:
            b = state.branches[bid]
            if b.status == "expanded":
                continue
            if b.posterior < floor:
                b.posterior = floor
                changed = True
        if not changed:
            return
        # Renormalize the diagnosable (non-expanded) layer so probabilities still
        # sum to 1 while preserving the floored branch(es).
        diagnosable = [b for b in state.branches.values() if b.status != "expanded"]
        floored = {bid for bid in floor_branches}
        fixed_mass = sum(b.posterior for b in diagnosable if b.id in floored)
        others = [b for b in diagnosable if b.id not in floored]
        other_mass = sum(b.posterior for b in others)
        remaining = max(0.0, 1.0 - fixed_mass)
        if other_mass > 0 and remaining >= 0:
            scale = remaining / other_mass
            for b in others:
                b.posterior *= scale
        self.recompute_parent_posteriors(state)

    def _handle_major_update(
        self, state: DiagnosticState, annotation: dict
    ) -> None:
        if annotation.get("contradiction_detected", False) and state.root is not None:
            state.root_revision_needed = True

    # ------------------------------------------------------------------
    # Multi-level expansion
    # ------------------------------------------------------------------

    def force_expand_all_l1(self, state: DiagnosticState) -> dict:
        """Expand every L1 branch for the harness partial-flow trace.

        This deliberately bypasses ExpansionGate eligibility, posterior, and
        per-cycle limits.  If SubBranchCreator declines or yields no usable
        child, attach one explicitly marked structural fallback so every L1 has
        an auditable L2 continuation rather than silently missing coverage.
        """
        records: list[dict] = []
        l1_branches = sorted(
            (branch for branch in state.branches.values() if branch.level == 1),
            key=lambda branch: branch.id,
        )
        for parent in l1_branches:
            existing = [
                branch.id
                for branch in state.branches.values()
                if branch.parent == parent.id and branch.level == 2
            ]
            if parent.children or existing:
                child_ids = list(dict.fromkeys(parent.children + existing))
                records.append({
                    "branch_id": parent.id,
                    "subbranch_creator_called": False,
                    "outcome": "already_expanded",
                    "child_ids": child_ids,
                    "fallback_used": False,
                })
                continue

            result = self.expand_branch(state, parent)
            child_ids = [
                branch.id
                for branch in state.branches.values()
                if branch.parent == parent.id and branch.level == 2
            ]
            fallback_used = False
            if not child_ids:
                fallback_used = True
                child = self._attach_partial_fallback_child(state, parent)
                child_ids = [child.id]

            records.append({
                "branch_id": parent.id,
                "subbranch_creator_called": True,
                "subbranch_creator_needs_expansion": bool(
                    (result or {}).get("needs_expansion", True)
                ),
                "outcome": "fallback_expanded" if fallback_used else "expanded",
                "child_ids": child_ids,
                "fallback_used": fallback_used,
                "fallback_reason": (
                    (result or {}).get("reason_if_not", "")
                    if fallback_used
                    else ""
                ),
            })

        expanded_count = sum(bool(record["child_ids"]) for record in records)
        total = len(records)
        return {
            "policy": "force_expand_all_l1",
            "gate_bypassed": True,
            "ignored_constraints": [
                "posterior",
                "max_structural_expansions_per_cycle",
                "expand_now",
            ],
            "l1_total": total,
            "l1_expanded": expanded_count,
            "l1_expansion_rate": (expanded_count / total) if total else 1.0,
            "branches": records,
        }

    def _attach_partial_fallback_child(
        self, state: DiagnosticState, parent: Branch
    ) -> Branch:
        """Attach a non-clinical L2 placeholder when forced generation declines."""
        base_id = f"{parent.id}.partial_fallback"
        child_id = base_id
        suffix = 2
        while child_id in state.branches:
            child_id = f"{base_id}_{suffix}"
            suffix += 1
        child = Branch(
            id=child_id,
            label=f"{parent.label} — unrefined L2",
            parent=parent.id,
            level=2,
            status="live",
            prior=1.0,
            posterior=1.0,
            danger=parent.danger,
            actionability=parent.actionability,
            explanatory_coverage=parent.explanatory_coverage,
            level_role="partial_flow_fallback",
            classification_axis=parent.classification_axis or "other",
        )
        state.branches[child.id] = child
        parent.children.append(child.id)
        self.initialize_child_posteriors(parent, [child])
        return child

    def run_expansion_gate(self, state: DiagnosticState) -> None:
        """Evaluate expand_now branches; expand those passing all gates.

        Implements ExpansionGate from MULTI_LEVEL_EXPANSION_DESIGN.md §3.
        At most config.max_structural_expansions_per_cycle branches are expanded.
        """
        eligible: list[tuple[float, Branch]] = []

        for bid, branch in state.branches.items():
            if branch.status != "live":
                continue
            # Check if PostUpdateStateReviser requested expansion
            # (we use live_subtype / expand_score as signal; status is reset to
            # "live" by revise_branch_states for keep_coarse/expand_now alike)
            if branch.expand_score <= 0:
                continue
            if not self._passes_expansion_gate(branch, state):
                continue
            eligible.append((branch.expand_score, branch))

        # Select top-K by score
        eligible.sort(key=lambda t: t[0], reverse=True)
        to_expand = eligible[: self.config.max_structural_expansions_per_cycle]

        for _, branch in to_expand:
            self.expand_branch(state, branch)

    def _passes_expansion_gate(self, branch: Branch, state: DiagnosticState) -> bool:
        """Hard-constraint checks for ExpansionGate (§3.2)."""
        # Hard constraints — any failure blocks expansion
        # allow_depth_4 raises the ceiling to 4 beyond max_tree_depth's default of 3
        effective_max_depth = 4 if self.config.allow_depth_4 else self.config.max_tree_depth
        if branch.level >= effective_max_depth:
            return False
        if branch.status == "confirmed":
            return False
        if branch.posterior < self.config.test_threshold:
            return False
        if branch.children:
            return False
        children_exist = any(
            b.parent == branch.id for b in state.branches.values()
        )
        if children_exist:
            return False

        # ALLOW conditions — at least one must hold
        proxy_score = (
            branch.diagnosis_commitment_gain
            * (1.0 - branch.turn_cost_to_refine / max(state.max_tree_depth * 2, 1))
        )
        action_diff_ok = proxy_score >= self.config.min_action_diff_to_expand
        danger_ok = branch.danger >= 0.7
        has_discriminator = self._has_unresolved_discriminator(branch, state)
        coexistence_ok = self._coexistence_suspected(branch, state)

        return action_diff_ok or danger_ok or has_discriminator or coexistence_ok

    def _has_unresolved_discriminator(self, branch: Branch, state: DiagnosticState) -> bool:
        already_asked = {a.get("content", "") for a in state.actions_taken}
        for q in branch.askable_discriminators + branch.requestable_discriminators:
            if q not in already_asked:
                return True
        return False

    def _coexistence_suspected(self, branch: Branch, state: DiagnosticState) -> bool:
        """Check whether evidence patterns suggest multi-diagnosis coexistence."""
        live_others = [
            b for b in state.branches.values()
            if b.id != branch.id and b.status in {"live", "reopened"}
        ]
        if not live_others:
            return False
        top_other = max(live_others, key=lambda b: b.posterior)
        return (branch.posterior + top_other.posterior) > 0.80

    def check_just_in_time_expansion(self, state: DiagnosticState) -> None:
        """Pre-leaf-planning expansion when action selection requires child detail.

        Implements §15.1: just_in_time_expansion is allowed only when action
        selection at the parent level cannot be made safely because the child
        branches imply different immediate actions.  This is intentionally
        narrow — it fires in cases like "biliary obstruction workup" where the
        child branches (ultrasound vs MRCP vs ERCP pathway) would each mandate
        a different first test.
        """
        effective_max_depth = 4 if self.config.allow_depth_4 else self.config.max_tree_depth
        for bid in list(state.frontier):
            branch = state.branches.get(bid)
            if branch is None:
                continue
            if branch.status not in {"live", "reopened"}:
                continue
            if branch.level >= effective_max_depth:
                continue
            if branch.children:
                continue
            if self._action_selection_requires_children(branch, state):
                self.expand_branch(state, branch)
                self.update_frontier_after_expansion(state)

    def _action_selection_requires_children(
        self, branch: Branch, state: DiagnosticState
    ) -> bool:
        """Return True when child-level distinction is necessary for action planning.

        Heuristic: the branch has high posterior, its classification_axis is
        'management_pathway' or 'test_pathway' (meaning sub-branches imply
        different action sets), and it has unresolved discriminators that can
        only be resolved via different investigative paths.
        """
        if branch.posterior < self.config.commit_threshold * 0.5:
            return False
        if branch.classification_axis not in {"management_pathway", "test_pathway"}:
            return False
        return self._has_unresolved_discriminator(branch, state)

    @staticmethod
    def _dedupe_l2_subbranches(result: dict) -> dict:
        """Case-insensitive disease-label and id de-duplication, order preserving."""
        if not isinstance(result, dict):
            return result
        out = dict(result)
        seen_labels: set[str] = set()
        seen_ids: set[str] = set()
        unique: list[dict] = []
        for row in result.get("sub_branches", []) or []:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label", "")).strip()
            branch_id = str(row.get("id", "")).strip()
            if not label or not branch_id:
                continue
            label_key = re.sub(r"\s+", " ", label).casefold()
            if label_key in seen_labels or branch_id in seen_ids:
                continue
            seen_labels.add(label_key)
            seen_ids.add(branch_id)
            unique.append(row)
        out["sub_branches"] = unique
        return out

    @staticmethod
    def _canonicalize_l2_subbranch_ids(
        result: dict, parent_id: str
    ) -> dict:
        """Bind opt-in recalled children to the actual parent's ID namespace.

        A model can copy the prompt example and emit ``B1.x`` while expanding a
        different parent. Because branch IDs are global keys, that would overwrite
        earlier children and silently empty an L1 scope.
        """
        out = dict(result)
        rows = []
        for index, raw in enumerate(
            result.get("sub_branches", []) or (), start=1
        ):
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            row["id"] = f"{parent_id}.{index}"
            row["parent_id"] = parent_id
            row["level"] = 2
            rows.append(row)
        out["sub_branches"] = rows
        out["sub_frontier"] = [row["id"] for row in rows]
        return out

    def _l2_recall_gap_uncovered(
        self, candidates: list[str], child_labels: list[str]
    ) -> list[str]:
        """Shared A/B semantic coverage assignment; fail-open means no gaps."""
        if self.llm is None or not candidates or not child_labels:
            return []
        prompt = (
            "For each recalled specific disease, decide whether it is represented "
            "by one of the generated specific-disease child labels (allow canonical "
            "synonyms, but do not map a disease merely because it shares an organ "
            "or family). Return child index, or -1 when absent. STRICT JSON: "
            '{"assignments":[{"candidate":"...", "index":<int>}, ...]}.'
        )
        payload = {
            "children": [
                {"index": i, "label": label}
                for i, label in enumerate(child_labels)
            ],
            "candidates": candidates,
        }
        try:
            result = self.llm.call_module(
                "RecallGapAssign", prompt, payload
            )
        except Exception as e:  # pragma: no cover - defensive fail-open
            _logger.warning("L2 gap assignment failed (%s); skipping repair", e)
            return []
        if not isinstance(result, dict):
            return []
        out: list[str] = []
        allowed = {c.casefold(): c for c in candidates}
        for row in result.get("assignments", []) or []:
            try:
                index = int(row.get("index", -1))
            except (TypeError, ValueError):
                continue
            candidate = str(row.get("candidate", "")).strip()
            canonical = allowed.get(candidate.casefold())
            if index < 0 and canonical and canonical not in out:
                out.append(canonical)
        return out

    def _gap_fill_l2_result(
        self,
        state,
        parent_branch: Branch,
        payload: dict,
        result: dict,
        candidates: list[dict],
        audit: dict,
    ) -> dict:
        """One-shot A/B repair with no-shrink and no-coverage-loss guards."""
        before_dedupe = len(result.get("sub_branches", []) or [])
        result = self._dedupe_l2_subbranches(result)
        audit["duplicates_removed"] = max(
            0, before_dedupe - len(result.get("sub_branches", []) or [])
        )
        if not getattr(self.config, "l2_recall_gap_fill", False):
            audit["gap_fill"] = "disabled"
            return result
        original = list(result.get("sub_branches", []) or [])
        if not original or not candidates:
            audit["gap_fill"] = "not_applicable"
            return result
        candidate_names = [row["disease"] for row in candidates]
        child_labels = [str(row.get("label", "")) for row in original]
        uncovered = self._l2_recall_gap_uncovered(
            candidate_names, child_labels
        )
        audit["uncovered_candidates"] = uncovered
        if not uncovered:
            audit["gap_fill"] = "covered"
            return result

        repair_payload = dict(payload)
        repair_payload["repair"] = {
            "uncovered_candidates": uncovered,
            "previous_sub_branches": original,
            "constraints": ["no_shrink", "no_coverage_loss"],
        }
        try:
            repaired = self._call_module(
                "L2RecallCreator",
                repair_payload,
                validator=_validate_subbranch,
            )
            repaired = self._dedupe_l2_subbranches(repaired)
        except Exception as e:  # pragma: no cover - defensive fail-open
            _logger.warning(
                "L2 recall repair failed (%s); retaining original children", e
            )
            audit["gap_fill"] = "repair_failed_open"
            return self._maybe_force_emit_uncovered_l2(
                result, uncovered, audit
            )

        repaired_rows = list(repaired.get("sub_branches", []) or [])
        old_coverage = {
            re.sub(r"\s+", " ", str(row.get("label", "")).strip()).casefold()
            for row in original if row.get("label")
        }
        new_coverage = {
            re.sub(r"\s+", " ", str(row.get("label", "")).strip()).casefold()
            for row in repaired_rows if row.get("label")
        }
        no_shrink = len(repaired_rows) >= len(original)
        no_loss = old_coverage.issubset(new_coverage)
        audit["repair_no_shrink"] = no_shrink
        audit["repair_no_coverage_loss"] = no_loss
        if repaired_rows and no_shrink and no_loss:
            audit["gap_fill"] = "repair_accepted"
            result = repaired
        else:
            audit["gap_fill"] = "repair_rejected"
            result = result
        return self._maybe_force_emit_uncovered_l2(
            result, uncovered, audit
        )

    @staticmethod
    def _child_labels_cover(name: str, child_labels: list[str]) -> bool:
        key = re.sub(r"\s+", " ", str(name or "").strip()).casefold()
        if not key:
            return True
        for lab in child_labels:
            other = re.sub(r"\s+", " ", str(lab or "").strip()).casefold()
            if not other:
                continue
            if key == other or key in other or other in key:
                return True
        return False

    def _force_emit_uncovered_subbranches(
        self,
        rows: list,
        uncovered: list[str],
    ) -> tuple[list, list[str]]:
        """Deterministically append still-missing uncovered names as children."""
        out = list(rows)
        child_labels = [str(r.get("label", "")) for r in out]
        emitted: list[str] = []
        max_emit = int(getattr(self.config, "l2_gap_force_emit_max", 3) or 0)
        if max_emit < 0:
            max_emit = 0
        for name in uncovered:
            if max_emit and len(emitted) >= max_emit:
                break
            label = str(name or "").strip()
            if not label:
                continue
            key = re.sub(r"\s+", " ", label).casefold()
            covered = False
            for lab in child_labels:
                other = re.sub(r"\s+", " ", str(lab or "").strip()).casefold()
                if other and (key == other or key in other or other in key):
                    covered = True
                    break
            if covered:
                continue
            out.append({
                "label": label,
                "danger": 0.0,
                "force_emitted_uncovered": True,
            })
            child_labels.append(label)
            emitted.append(label)
        return out, emitted

    def _maybe_force_emit_uncovered_l2(
        self,
        result: dict,
        uncovered: list[str],
        audit: dict,
    ) -> dict:
        if not getattr(self.config, "l2_gap_force_emit_uncovered", False):
            return result
        if not uncovered:
            return result
        rows = list(result.get("sub_branches", []) or [])
        new_rows, emitted = self._force_emit_uncovered_subbranches(rows, uncovered)
        audit["force_emit_uncovered"] = True
        audit["force_emitted_labels"] = emitted
        if not emitted:
            audit["force_emit_status"] = "already_covered"
            return result
        out = dict(result)
        out["sub_branches"] = new_rows
        audit["force_emit_status"] = "appended"
        audit["force_emit_n"] = len(emitted)
        return out

    def expand_branch(self, state: DiagnosticState, parent_branch: Branch) -> dict:
        """Attach children through legacy or opt-in L2 recall generation."""
        payload = {
            "state": state.project_for("SubBranchCreator"),
            "parent_branch": {
                "id": parent_branch.id,
                "label": parent_branch.label,
                "level": parent_branch.level,
                "posterior": parent_branch.posterior,
                "danger": parent_branch.danger,
                "evidence_for": parent_branch.evidence_for,
                "evidence_against": parent_branch.evidence_against,
                "unresolved_questions": parent_branch.unresolved_questions,
                "askable_discriminators": parent_branch.askable_discriminators,
                "requestable_discriminators": parent_branch.requestable_discriminators,
            },
            "target_level": parent_branch.level + 1,
        }
        legacy_payload = payload
        module_name = "SubBranchCreator"
        l2_audit: dict | None = None
        recall_candidates: list[dict] = []
        knowledge_fragments: list[dict] = []
        specialised = self._l2_mode != "none" and parent_branch.level == 1
        if specialised:
            try:
                (
                    recall_candidates,
                    knowledge_fragments,
                    l2_audit,
                ) = self._l2_recall_for_parent(state, parent_branch)
            except Exception as e:  # fail-open to the exact legacy call
                _logger.warning(
                    "L2 recall preparation failed (%s); using SubBranchCreator", e
                )
                l2_audit = {
                    "mode": self._l2_mode,
                    "parent_id": parent_branch.id,
                    "outcome": "recall_failed_open",
                    "error": str(e),
                    "retrieval_calls": (
                        0 if self._l2_mode == "reuse_l1" else 1
                    ),
                }
            if recall_candidates:
                module_name = "L2RecallCreator"
                payload = {
                    "case_context": self._l2_case_context(state),
                    "parent_branch": payload["parent_branch"],
                    "target_level": 2,
                    "recall_candidates": recall_candidates,
                    "knowledge_fragments": knowledge_fragments,
                }
            elif l2_audit is not None:
                l2_audit["fallback_module"] = "SubBranchCreator"

        try:
            result = self._call_module(
                module_name, payload, validator=_validate_subbranch
            )
        except Exception as e:
            if module_name != "L2RecallCreator":
                raise
            # Recall augmentation is optional: creator/protocol failure must not
            # prevent the historical expansion path from proceeding.
            _logger.warning(
                "L2RecallCreator failed (%s); using SubBranchCreator", e
            )
            module_name = "SubBranchCreator"
            payload = legacy_payload
            if l2_audit is not None:
                l2_audit.update({
                    "outcome": "generator_failed_open",
                    "fallback_module": "SubBranchCreator",
                    "error": str(e),
                })
            result = self._call_module(
                module_name, payload, validator=_validate_subbranch
            )

        # Optional external knowledge loop
        if (module_name == "SubBranchCreator"
                and result.get("need_external_knowledge", False)
                and self.config.allow_external_knowledge
                and not (
                    specialised and self._l2_mode == "reuse_l1"
                )):
            knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
            self.env.ingest_external_context(knowledge)
            result = self._call_module(
                "SubBranchCreator", payload, validator=_validate_subbranch
            )

        if module_name == "L2RecallCreator" and l2_audit is not None:
            result = self._gap_fill_l2_result(
                state,
                parent_branch,
                payload,
                result,
                recall_candidates,
                l2_audit,
            )
            original_ids = [
                str(row.get("id") or "")
                for row in result.get("sub_branches", []) or ()
                if isinstance(row, dict)
            ]
            result = self._canonicalize_l2_subbranch_ids(
                result, parent_branch.id
            )
            canonical_ids = [
                str(row.get("id") or "")
                for row in result.get("sub_branches", []) or ()
            ]
            l2_audit["child_ids_rewritten"] = (
                original_ids != canonical_ids
            )
            l2_audit["canonical_child_ids"] = canonical_ids
            l2_audit["generator_module"] = module_name
            l2_audit["generated_count"] = len(
                result.get("sub_branches", []) or []
            )

        if l2_audit is not None:
            safe_audit = json.loads(json.dumps(l2_audit, default=str))
            result = dict(result)
            result["l2_recall_audit"] = safe_audit
            self._l2_recall_audit.append(safe_audit)
            del self._l2_recall_audit[:-100]

        if not result.get("needs_expansion", True):
            # LLM decided expansion is not warranted
            return result

        children: list[Branch] = []
        for b in result.get("sub_branches", []):
            if not isinstance(b, dict) or not b.get("id") or not b.get("label"):
                continue
            child = Branch(
                id=b["id"],
                label=b["label"],
                parent=parent_branch.id,
                level=parent_branch.level + 1,
                status=b.get("status", "live"),
                prior=b.get("prior_estimate", 0.0),
                posterior=b.get("prior_estimate", 0.0),
                danger=b.get("danger", 0.0),
                actionability=0.0,
                explanatory_coverage=0.0,
                level_role=b.get("level_role", ""),
                classification_axis=b.get("classification_axis", ""),
                representative_diseases=_clean_representative_diseases(
                    b.get("representative_diseases")),
                askable_discriminators=b.get("askable_discriminators", []),
                requestable_discriminators=b.get("requestable_discriminators", []),
                turn_cost_to_refine=b.get("turn_cost_to_refine", 1.0),
                diagnosis_commitment_gain=b.get("diagnosis_commitment_gain", 0.0),
                interrupt_relevance=b.get("interrupt_relevance", 0.0),
            )
            state.branches[child.id] = child
            children.append(child)
            parent_branch.children.append(child.id)

        if children:
            # §22.2 (A′): attach taxonomy lookup entities to the new sub-branches
            # too (NON-prompt). Keyed by {id: branch} for the shared helper.
            self._populate_lookup_entities({c.id: c for c in children})
            self.initialize_child_posteriors(parent_branch, children)
        return result

    def initialize_child_posteriors(
        self, parent: Branch, children: list[Branch]
    ) -> None:
        """Distribute parent's posterior mass among children (Bayesian decomposition)."""
        total_prior = sum(c.prior for c in children)
        if total_prior <= 0:
            share = parent.posterior / len(children)
            for c in children:
                c.prior = share
                c.posterior = share
        else:
            for c in children:
                c.prior = parent.posterior * (c.prior / total_prior)
                c.posterior = c.prior
        # Parent becomes a container node
        parent.status = "expanded"
        parent.posterior = 0.0
        parent.prior = 0.0

    def recompute_parent_posteriors(self, state: DiagnosticState) -> None:
        """Bottom-up aggregation: sum children's posteriors into expanded parents."""
        for bid, branch in state.branches.items():
            if branch.status == "expanded" and branch.children:
                active_children = [
                    state.branches[cid]
                    for cid in branch.children
                    if cid in state.branches
                ]
                branch.posterior = sum(c.posterior for c in active_children)

    def update_frontier_after_expansion(self, state: DiagnosticState) -> None:
        """Replace expanded parents in frontier with their live children."""
        new_frontier: list[str] = []
        for bid in state.frontier:
            branch = state.branches.get(bid)
            if branch is None:
                continue
            if branch.children:
                for cid in branch.children:
                    child = state.branches.get(cid)
                    if child and child.status in {"live", "reopened"}:
                        new_frontier.append(cid)
            elif branch.status in {"live", "reopened"}:
                new_frontier.append(bid)
            # confirmed/closed_for_now/parked/expanded → excluded

        max_frontier = self.config.max_live_frontier
        if self._in_sdbench_mode():
            max_frontier = min(max_frontier, 3)
        state.frontier = new_frontier[:max_frontier]

    # ------------------------------------------------------------------
    # Branch-state revision
    # ------------------------------------------------------------------

    def revise_branch_states(self, state: DiagnosticState) -> None:
        result = self._call_module("PostUpdateStateReviser", state.project_for("PostUpdateStateReviser"),
                                   validator=_validate_post_update_reviser)
        new_frontier: list[str] = []
        for d in result.get("branch_decisions", []):
            if not isinstance(d, dict):
                continue
            bid = d.get("branch_id")
            if not bid or bid not in state.branches:
                continue
            branch = state.branches[bid]
            decision = d.get("decision", "keep_coarse")
            if decision == "confirm":
                branch.status = "confirmed"
            elif decision == "close_for_now":
                branch.status = "closed_for_now"
            elif decision == "park":
                branch.status = "parked"
            elif decision == "reopen":
                branch.status = "reopened"
                new_frontier.append(bid)
            elif decision == "expand_now":
                # Mark with a non-zero expand_score so run_expansion_gate picks it up.
                # Status stays "live" until ExpansionGate approves.
                branch.status = "live"
                branch.expand_score = max(branch.expand_score, 0.5)
                new_frontier.append(bid)
            else:
                # keep_coarse or unrecognised → stay live, clear expand signal
                if branch.status != "expanded":
                    branch.status = "live"
                    branch.expand_score = 0.0
                new_frontier.append(bid)

        max_frontier = self.config.max_live_frontier
        if self._in_sdbench_mode():
            max_frontier = min(max_frontier, 3)
        state.frontier = new_frontier[:max_frontier]

    def _apply_reopen_overrides(
        self, state: DiagnosticState, annotation: dict
    ) -> None:
        """Deterministically reopen branches flagged by EvidenceAnnotator."""
        max_frontier = self.config.max_live_frontier
        if self._in_sdbench_mode():
            max_frontier = min(max_frontier, 3)

        for bid in annotation.get("reopen_candidates", []):
            if bid not in state.branches:
                continue
            branch = state.branches[bid]
            if branch.status in {"closed_for_now", "parked"}:
                branch.status = "reopened"
                if bid not in state.frontier and len(state.frontier) < max_frontier:
                    state.frontier.append(bid)

    # ------------------------------------------------------------------
    # Turn budget
    # ------------------------------------------------------------------

    def account_turn_budget(
        self, state: DiagnosticState, bundle: list
    ) -> None:
        """Increment turn_budget_used according to bundle_budget_mode."""
        mode = self.config.bundle_budget_mode
        if mode == "per_action":
            state.turn_budget_used += len(bundle)
        elif mode == "time_weighted":
            delays = [
                getattr(a, "expected_delay", None) or (a.get("expected_delay", 0.5) if isinstance(a, dict) else 0.5)
                for a in bundle
            ]
            max_delay = max(delays) if delays else 0.5
            state.turn_budget_used += max(1, round(max_delay * 2))
        else:  # per_bundle (default)
            state.turn_budget_used += 1

    # ------------------------------------------------------------------
    # Differential history & diagnosis readiness
    # ------------------------------------------------------------------

    def record_differential_history(self, state: DiagnosticState) -> None:
        state.differential_history.append(
            {bid: b.posterior for bid, b in state.branches.items()}
        )

    def check_diagnosis_readiness(self, state: DiagnosticState) -> bool:
        if not state.branches:
            state.diagnosis_readiness_score = 0.0
            return False

        # Only leaf-level (non-expanded) branches represent diagnosable entities.
        # Expanded branches are structural containers — committing to one would
        # name a category, not a diagnosis.
        diagnosable = [
            b for b in state.branches.values()
            if b.status != "expanded"
        ]
        if not diagnosable:
            state.diagnosis_readiness_score = 0.0
            return False

        ranked = sorted(diagnosable, key=lambda b: b.posterior, reverse=True)
        leader = ranked[0]
        state.diagnosis_readiness_score = leader.posterior

        if leader.posterior < self.config.min_readiness_to_commit:
            return False

        # F4: separation-aware commit. Refuse to commit while the leader is not
        # separated from the runner-up by the required margin — a near-flat
        # distribution means the discriminator has not yet been resolved
        # (e.g. case 22 committed at posterior≈0.12). Only gate while turn
        # budget remains; the budget-exhaustion path still forces a commit.
        if len(ranked) > 1:
            margin = leader.posterior - ranked[1].posterior
            budget_remaining = (
                state.max_turn_budget is None
                or state.turn_budget_used < state.max_turn_budget
            )
            if margin < self.config.min_leader_margin_to_commit and budget_remaining:
                return False

        if self._in_patch_mode():
            dangerous_alternative_exists = any(
                b.id != leader.id and b.danger >= 0.7 and b.posterior >= 0.15
                for b in ranked
            )
            cheap_high_yield_exists = any(
                leaf.total_score >= 0.8 and leaf.expected_cost <= 0.2
                for leaf in state.candidate_leaves
            )
            repeated = self.detect_repeated_bundle(state)
            if dangerous_alternative_exists or cheap_high_yield_exists or repeated:
                return False

        return True

    def detect_repeated_bundle(self, state: DiagnosticState) -> bool:
        """Detect whether the most recent bundle's primary action is a repeat."""
        if len(state.actions_taken) < 2:
            return False
        current_content = state.actions_taken[-1]["content"]
        recent_primaries = [
            a["content"]
            for a in state.actions_taken[-4:-1]
            if a.get("bundle_position", 0) == 0
        ]
        return current_content in recent_primaries

    # ------------------------------------------------------------------
    # Termination & final aggregation
    # ------------------------------------------------------------------

    def check_termination(self, state: DiagnosticState) -> TerminationState:
        result = self._call_module("TerminationJudge", state.project_for("TerminationJudge"),
                                   validator=_validate_termination)
        ttype = result.get("termination_type", "continue")
        ready = bool(result.get("ready_to_stop", False))
        reason = result.get("reason", "")
        if self._in_static_qa_mode() and ttype == "emergency_override":
            ready = False
            ttype = "continue"
            reason = (
                f"[static mode override] {reason} "
                "— emergency_override suppressed in static_diagnosis_qa mode"
            )
        return TerminationState(
            ready_to_stop=ready,
            termination_type=ttype,
            reason=reason,
        )

    def _enforce_answer_consistency(
        self, final_answer: str, mapping: dict
    ) -> tuple[str, dict]:
        """F3: make the AnswerMapper self-consistent.

        - optionally soften the option distribution to counter LLM
          overconfidence (answer_mapping_softmax_temperature > 1);
        - force final_answer == argmax(mapping) so the committed letter agrees
          with the mapper's own probabilities (fixes e.g. case 23 where the
          final answer disagreed with the highest-probability option).
        """
        if not self.config.enforce_answer_mapper_consistency:
            return final_answer, mapping
        numeric = {
            k: float(v) for k, v in mapping.items()
            if isinstance(v, (int, float))
        }
        if not numeric:
            return final_answer, mapping

        temp = self.config.answer_mapping_softmax_temperature
        if temp and temp > 1.0:
            powered = {k: max(v, 1e-9) ** (1.0 / temp) for k, v in numeric.items()}
            total = sum(powered.values())
            if total > 0:
                numeric = {k: v / total for k, v in powered.items()}
                mapping = dict(mapping)
                mapping.update({k: round(numeric[k], 4) for k in numeric})

        argmax_opt = max(numeric, key=numeric.get)
        cur = (final_answer or "").strip().upper()
        if cur != argmax_opt:
            _logger.info(
                "AnswerMapper consistency: final_answer %r → %r (argmax of mapping)",
                final_answer, argmax_opt,
            )
            final_answer = argmax_opt
        return final_answer, mapping

    def final_aggregate(self, state: DiagnosticState):
        if self._in_static_qa_mode():
            mapped = self._call_module(
                "AnswerMapper",
                {"state": state.project_for("AnswerMapper"), "options": state.static_options},
                validator=_validate_answer_mapper,
            )
            mapping = mapped.get("answer_option_mapping", {})
            final_answer = mapped.get("final_answer", "")
            final_answer, mapping = self._enforce_answer_consistency(
                final_answer, mapping
            )
            state.answer_option_mapping = mapping
            return {
                "final_answer": final_answer,
                "answer_option_mapping": mapping,
                "internal_reasoning_state": state.to_dict(),
                # §30: surface recovered program faults so the harness can flag
                # the answer's trustworthiness (empty list = clean run).
                "internal_faults": list(getattr(state, "program_faults", []) or []),
            }

        if self._in_sdbench_mode():
            emitter = self._call_module(
                "FinalDiagnosisEmitter",
                {"state": state.to_dict(), "internal_reasoning_state": state.to_dict()},
            )
            diagnosis = emitter.get("final_diagnosis", "undetermined")
            submitted = None
            if hasattr(self.env, "submit_diagnosis"):
                submitted = self.env.submit_diagnosis(diagnosis)
            return {
                "diagnosis": diagnosis,
                "submission": submitted,
                "internal_reasoning_state": state.to_dict(),
            }

        final_output = self._call_module("FinalAggregator", state.to_dict())
        if hasattr(self.env, "review_with_moderator"):
            final_output = dict(final_output)
            final_output["moderator_review"] = self.env.review_with_moderator(
                final_output, state
            )

        if self._in_patch_mode():
            diagnosis = final_output.get("leading_diagnosis_or_parent", "undetermined")
            return {
                "internal_reasoning_state": final_output,
                "benchmark_output": f"Diagnosis Ready: {diagnosis}",
            }
        return final_output

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def root_changed_materially(self, state: DiagnosticState) -> bool:
        return self.env.root_changed_materially(state)

    def execute_emergent_actions(self, state: DiagnosticState) -> None:
        for action in state.interrupt.required_actions:
            self.env.take_emergent_action(action)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _leaf_to_action_dict(leaf) -> dict:
    """Convert a CandidateLeaf or plain dict to a minimal action dict."""
    if isinstance(leaf, dict):
        return leaf
    return {"type": leaf.leaf_type, "content": leaf.content}


def _action_dict_to_leaf(action: dict) -> "CandidateLeaf":
    """Wrap a plain action dict in a minimal CandidateLeaf for bundle processing.

    Accepts both 'type' (TemporaryLeafPlanner schema) and 'action_type'
    (Consensus module schema) as the action-type key.
    """
    leaf_type = action.get("type") or action.get("action_type") or "ASK_PATIENT"
    return CandidateLeaf(
        leaf_id="fallback::0",
        branch_id=action.get("branch_id", "unknown"),
        leaf_type=leaf_type,
        content=action.get("content", ""),
        expected_information_gain=0.0,
        expected_cost=0.0,
        expected_delay=0.0,
        safety_value=0.0,
        action_separation_value=0.0,
        total_score=0.0,
    )
