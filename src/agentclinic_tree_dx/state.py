from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

# Valid statuses for a Branch object.
# "expanded" means the branch has been structurally expanded into child branches;
# it no longer holds probability mass directly (children hold it instead).
VALID_BRANCH_STATUSES = {
    "live", "parked", "confirmed", "closed_for_now",
    "reopened", "expanded",
}


@dataclass
class RootNode:
    label: str
    time_course: str
    severity: str
    confidence: float
    supporting_facts: list[str] = field(default_factory=list)
    excluded_candidates: list[str] = field(default_factory=list)
    alarm_features: list[str] = field(default_factory=list)
    # Dual-entrance retrieval (§ dual-entry): the discrete, high-salience
    # symptoms / signs / pivotal findings that organise the presentation, kept
    # SEPARATE from the syndrome-frame ``label``. The syndrome label is a
    # deliberately abstract framing (good for MECE axis matching) but is often
    # lexically DISJOINT from the answer disease's corpus text (the c1/Pancoast
    # gap). These salient findings are the SECOND retrieval entrance: concrete
    # terms that hit the differential/case-report snippets the abstract frame
    # cannot reach. RRF-fused with the syndrome entrance downstream.
    salient_findings: list[str] = field(default_factory=list)


@dataclass
class Branch:
    id: str
    label: str
    parent: str
    level: int
    status: str
    prior: float
    posterior: float
    danger: float
    actionability: float
    explanatory_coverage: float
    expand_score: float = 0.0
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    closure_reason: str = ""
    reopen_triggers: list[str] = field(default_factory=list)

    # AgentClinic/SDBench patch-mode extensions.
    askable_discriminators: list[str] = field(default_factory=list)
    requestable_discriminators: list[str] = field(default_factory=list)
    turn_cost_to_refine: float = 0.0
    diagnosis_commitment_gain: float = 0.0
    interrupt_relevance: float = 0.0

    # Structured metadata for expansion decisions (MULTI_LEVEL_EXPANSION_DESIGN §15.4)
    level_role: str = ""            # domain|family|disease_class|specific_disease|subtype_or_management_variant
    classification_axis: str = ""   # anatomy|mechanism|urgency|management_pathway|test_pathway|etiology|risk_context|severity|other

    # Canonical specific disease entities this (broad family) branch covers.
    # Family labels are intentionally broad and do NOT key the disease-keyed LR
    # cache; these representative entities are what KB/LR lookups resolve against
    # so external evidence can fire on the correct branch (EXTERNAL_KNOWLEDGE §21.8a).
    representative_diseases: list[str] = field(default_factory=list)


@dataclass
class CandidateLeaf:
    leaf_id: str
    branch_id: str
    leaf_type: str
    content: str
    expected_information_gain: float
    expected_cost: float
    expected_delay: float
    safety_value: float
    action_separation_value: float
    total_score: float

    # Per-branch expected impact direction (TALP_BUNDLER_REDESIGN_SPEC §2.1)
    # Maps branch_id → "support" | "against" | "neutral"
    target_branches: dict[str, str] = field(default_factory=dict)
    # Cognitive motivation: confirm | challenge | differentiate | safety_ensure
    primary_function: str = "confirm"
    # Maximum probability displacement against branch_id under the most
    # adversarial plausible outcome (positive or negative). Non-zero only
    # for challenge candidates. (0-1)
    falsification_value: float = 0.0
    # Patient burden / procedure invasiveness (0-1)
    invasiveness: float = 0.0
    # Scheduling urgency: routine|urgent|emergent
    urgency: str = "routine"
    # Redundancy group label — only one action per group should enter a bundle
    redundancy_group: str = ""
    # Independence from other candidates (1.0 = fully independent target; 0.0 = redundant)
    bundle_independence: float = 1.0
    # True if this action requires the result of another action in the same candidate list
    result_dependency: bool = False
    why: str = ""


@dataclass
class EvidenceItem:
    id: str
    kind: str
    content: str
    source_ids: list[str] = field(default_factory=list)
    independent: bool = True
    branch_links: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliberationState:
    hypothesis_analysis: dict[str, Any] = field(default_factory=dict)
    test_chooser_analysis: dict[str, Any] = field(default_factory=dict)
    challenger_analysis: dict[str, Any] = field(default_factory=dict)
    stewardship_analysis: dict[str, Any] = field(default_factory=dict)
    checklist_analysis: dict[str, Any] = field(default_factory=dict)
    consensus_action: dict[str, Any] | None = None


@dataclass
class InterruptState:
    active: bool
    reason: str
    required_actions: list[str] = field(default_factory=list)


@dataclass
class TerminationState:
    ready_to_stop: bool
    termination_type: str
    reason: str


@dataclass
class DiagnosticState:
    case_id: str
    timestep: int = 0
    case_summary: str = ""
    root: RootNode | None = None
    branches: dict[str, Branch] = field(default_factory=dict)
    frontier: list[str] = field(default_factory=list)
    other_mass: float = 0.0
    candidate_leaves: list[CandidateLeaf] = field(default_factory=list)
    pending_results: list[dict[str, Any]] = field(default_factory=list)
    # Each record: {timestep, bundle_id, bundle_position, bundle_size, action_type,
    #               external_action, content, raw_result, result_summary}
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    differential_history: list[dict[str, float]] = field(default_factory=list)
    deliberation: DeliberationState = field(default_factory=DeliberationState)
    interrupt: InterruptState = field(default_factory=lambda: InterruptState(False, ""))
    termination: TerminationState = field(
        default_factory=lambda: TerminationState(False, "continue", "")
    )

    # AgentClinic/SDBench patch-mode extensions.
    turn_budget_used: int = 0
    estimated_remaining_value: float = 0.0
    max_turn_budget: int | None = None
    latest_action_type: str = ""
    diagnosis_readiness_score: float = 0.0
    benchmark_output_ready: bool = False

    # Static QA mode fields.
    static_vignette: str = ""
    static_question: str = ""
    static_options: list[str] = field(default_factory=list)
    static_evidence_items: list[EvidenceItem] = field(default_factory=list)
    seen_evidence_ids: list[str] = field(default_factory=list)
    # Phenotype terms already matched and used across turns (for evidence dedup)
    seen_evidence_phenotypes: set[str] = field(default_factory=set)
    mode_policy: dict[str, Any] = field(default_factory=dict)
    answer_option_mapping: dict[str, float] = field(default_factory=dict)
    tool_use_log: list[dict[str, Any]] = field(default_factory=list)

    # Root revision flag: set to True by _handle_major_update when a contradiction
    # is detected; cleared at the start of the next cycle after root re-selection.
    root_revision_needed: bool = False

    # §30 integrity: genuine PROGRAM faults that were RECOVERED mid-pipeline
    # (e.g. an empty-bundle fallback). A non-empty list means the final answer
    # came from a degraded process → the harness flags the record low-trust.
    # NOTE: this is NOT for knowledge-coverage misses (those fail-open silently
    # and are expected); only program-level degradations are recorded here.
    program_faults: list[str] = field(default_factory=list)

    # Bounded per-case trace of discrimination-profile evidence injected into
    # TALP / EvidenceAnnotator.  This is operational audit data, not clinical
    # state, and is dropped from ordinary module projections below.
    discrimination_audit: list[dict[str, Any]] = field(default_factory=list)

    # Mirror of config.max_tree_depth; passed to LLMs via to_dict() so prompts
    # can reference the current depth ceiling without accessing config directly.
    max_tree_depth: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ── Payload slimming (PAYLOAD_SLIMMING_PLAN.md) ────────────────────────────
    # Per-module DROP sets: fields removed from that module's projected payload
    # because the module does not consume them. Everything not listed is kept
    # (already compacted). Easy to extend / audit. The base compaction (action
    # ledger, branch prose distillation, vignette de-dup, differential numeric)
    # plus the always-attached ``reasoning_ledger`` apply to every module.
    _MODULE_DROP: ClassVar[dict[str, set[str]]] = {
        # RootSelector only frames the syndrome from the vignette + (scrubbed)
        # options; execution history / branches / planner output are irrelevant
        # and were the single biggest source of bloat (~10.7k tok).
        "RootSelector": {
            "actions_taken", "branches", "differential_history",
            "candidate_leaves", "pending_results", "frontier", "tool_use_log",
            "deliberation", "discrimination_audit",
        },
        "BranchCreator": {
            "actions_taken", "candidate_leaves", "pending_results",
            "tool_use_log", "deliberation", "discrimination_audit",
        },
        "EvidenceAnnotator": {
            "candidate_leaves", "pending_results", "tool_use_log",
            "differential_history", "discrimination_audit",
        },
        "PostUpdateStateReviser": {
            "candidate_leaves", "pending_results", "tool_use_log",
            "discrimination_audit",
        },
        "TerminationJudge": {
            "candidate_leaves", "pending_results", "tool_use_log",
            "actions_taken", "discrimination_audit",
        },
        "AnswerMapper": {
            "candidate_leaves", "pending_results", "tool_use_log",
            "actions_taken", "discrimination_audit",
        },
        "SafetyController": {
            "candidate_leaves", "pending_results", "tool_use_log",
            "differential_history", "discrimination_audit",
        },
    }

    @staticmethod
    def _clip(text: Any, n: int) -> str:
        s = str(text or "")
        return s if len(s) <= n else s[: n - 1] + "…"

    def _reasoning_ledger(self) -> dict[str, Any]:
        """Compact, bounded audit block derived purely from current state.

        Reserved interface for future bias-mitigation modules (anti-anchoring,
        confirmation-bias). Carries exactly the signals those modules need,
        computed cheaply (no LLM call) and capped in size. Always present so the
        schema is stable even before any consumer exists.
        """
        # anchor: earliest differential snapshot's top hypothesis.
        anchor: dict[str, Any] = {}
        hist = [h for h in self.differential_history if isinstance(h, dict) and h]
        if hist:
            first = hist[0]
            top_label, top_p = max(first.items(), key=lambda kv: kv[1])
            anchor = {
                "hypothesis": top_label,
                "t": 0,
                "posterior_at_anchor": round(float(top_p), 3),
            }

        # Top-1 label per historical snapshot → revisions + leading streak.
        top_seq: list[str] = []
        for snap in hist:
            top_seq.append(max(snap.items(), key=lambda kv: kv[1])[0])
        n_revisions = sum(1 for i in range(1, len(top_seq)) if top_seq[i] != top_seq[i - 1])

        # leader: current highest-posterior diagnosable branch.
        leader: dict[str, Any] = {}
        leader_evidence: dict[str, Any] = {}
        alternatives: list[str] = []
        live = {
            bid: b for bid, b in self.branches.items()
            if b.status not in ("expanded",)
        }
        if live:
            lid, lb = max(live.items(), key=lambda kv: kv[1].posterior)
            leading_since = 0
            for lbl in reversed(top_seq):
                if lbl == lb.label:
                    leading_since += 1
                else:
                    break
            leader = {
                "branch_id": lid,
                "label": lb.label,
                "posterior": round(float(lb.posterior), 3),
                "leading_since_t": leading_since,
                "n_revisions": n_revisions,
            }
            leader_evidence = {
                "confirming": len(lb.evidence_for),
                "disconfirming": len(lb.evidence_against),
                "last_disconfirming_digest": (
                    self._clip(lb.evidence_against[-1], 120) if lb.evidence_against else ""
                ),
            }
            alternatives = [
                bid for bid, b in sorted(
                    live.items(), key=lambda kv: kv[1].posterior, reverse=True
                )
                if bid != lid and b.posterior >= 0.05
            ][:3]

        # action_intents: infer confirm/refute/broaden w.r.t. the leader from
        # per-action branch effects when available (best-effort; key reserved).
        action_intents: list[dict[str, Any]] = []
        leader_id = leader.get("branch_id")
        for rec in self.actions_taken[-6:]:
            if not isinstance(rec, dict):
                continue
            eff = rec.get("per_action_branch_effects") or {}
            intent = "broaden"
            if leader_id and isinstance(eff, dict) and leader_id in eff:
                sign = str(eff[leader_id])
                if "for" in sign:
                    intent = "confirm"
                elif "against" in sign:
                    intent = "refute"
            action_intents.append({"t": rec.get("timestep", 0), "intent": intent})

        return {
            "anchor": anchor,
            "leader": leader,
            "leader_evidence": leader_evidence,
            "action_intents": action_intents,
            "considered_alternatives": alternatives,
        }

    def project_for(self, module: str, max_action_records: int = 6) -> dict[str, Any]:
        """Module-specific, slimmed payload (replaces blanket to_payload()).

        Starts from the compacted base, drops fields the module does not
        consume (``_MODULE_DROP``), and always attaches ``reasoning_ledger``.
        """
        d = self.to_payload(max_action_records=max_action_records)
        d["reasoning_ledger"] = self._reasoning_ledger()
        for field_name in self._MODULE_DROP.get(module, set()):
            d.pop(field_name, None)
        return d

    def to_payload(self, max_action_records: int = 6) -> dict[str, Any]:
        """Return a token-efficient version of to_dict() for LLM prompts.

        Growth-control measures (ordered by per-turn impact):

        actions_taken (~+2,200 chars/turn)
          - Strip ``raw_result`` (passed separately to EvidenceAnnotator).
          - Strip ``branch_coverage`` audit (only used for internal bookkeeping).
          - Keep at most *max_action_records* most-recent records (default 6 ≈
            1-2 turns of 3-4 actions each).

        branch.evidence_for/against (~+1,600 chars/turn)
          - Each active branch accumulates one result_summary per turn.
          - Cap each list at 2 entries to stop unbounded accumulation while
            preserving the two most recent evidence signals.

        branches — closed_for_now / parked (~+1,600 chars/turn from expansion)
          - Once a branch is definitively closed, its full structure no longer
            aids deliberation.  Closed branches are replaced with a compact
            stub {id, label, status, posterior} to save tokens.

        deliberation outputs (~+500 chars/turn)
          - The previous turn's deliberation results are stale; downstream
            modules re-compute deliberation fresh each cycle.  Exclude from
            payload to avoid carrying forward dead weight.

        differential_history
          - Limit to 3 most-recent probability snapshots.

        candidate_leaves
          - Planner output; not consumed by downstream modules.
        """
        d = asdict(self)
        # Internal trace remains readable on the state/to_dict(), but is injected
        # only through the controller's explicit bounded profile fields.
        d.pop("discrimination_audit", None)

        # ── actions_taken → compact structured ledger ───────────────────────
        # Per-record prose (result_summary) was the single biggest growth driver
        # (up to ~6k tok). Keep only what downstream modules read, with caps.
        trimmed = []
        for rec in d.get("actions_taken", [])[-max_action_records:]:
            rec = dict(rec)
            trimmed.append({
                "t":       rec.get("timestep", 0),
                "type":    rec.get("action_type", ""),
                "content": self._clip(rec.get("content", ""), 200),
                "summary": self._clip(rec.get("result_summary", ""), 300),
            })
        d["actions_taken"] = trimmed

        # ── branches: distil prose, keep structure ──────────────────────────
        MAX_EV_ENTRIES = 1
        EV_CLIP = 160
        for bid, branch in list(d.get("branches", {}).items()):
            # Closed/parked branches: compact stub (enough for Challenger to
            # reason about premature closure).
            if branch.get("status") in ("closed_for_now", "parked"):
                d["branches"][bid] = {
                    "id":             branch["id"],
                    "label":          branch["label"],
                    "level":          branch["level"],
                    "status":         branch["status"],
                    "posterior":      round(float(branch.get("posterior", 0.0)), 3),
                    "danger":         branch.get("danger", 0.0),
                    "parent":         branch.get("parent"),
                    "closure_reason": self._clip(branch.get("closure_reason", ""), EV_CLIP),
                    "evidence_against": [
                        self._clip(e, EV_CLIP)
                        for e in branch.get("evidence_against", [])[-1:]
                    ],
                }
                continue
            # Active branches: cap + clip evidence/question prose; drop verbose
            # internal-only lists that no prompt consumes.
            branch["evidence_for"] = [
                self._clip(e, EV_CLIP) for e in branch.get("evidence_for", [])[-MAX_EV_ENTRIES:]
            ]
            branch["evidence_against"] = [
                self._clip(e, EV_CLIP) for e in branch.get("evidence_against", [])[-MAX_EV_ENTRIES:]
            ]
            branch["unresolved_questions"] = [
                self._clip(q, 120) for q in branch.get("unresolved_questions", [])[:2]
            ]
            for verbose in ("reopen_triggers", "askable_discriminators",
                            "requestable_discriminators"):
                branch.pop(verbose, None)

        # ── deliberation outputs (stale; re-computed each turn) ────────────
        d["deliberation"] = {}

        # ── differential history → numeric top-3 snapshots ──────────────────
        compact_hist = []
        for snap in d.get("differential_history", [])[-3:]:
            if isinstance(snap, dict) and snap:
                top = sorted(snap.items(), key=lambda kv: kv[1], reverse=True)[:3]
                compact_hist.append({"top": [[k, round(float(v), 3)] for k, v in top]})
        d["differential_history"] = compact_hist

        # ── candidate leaves ───────────────────────────────────────────────
        d.pop("candidate_leaves", None)

        # ── vignette de-duplication ─────────────────────────────────────────
        # case_summary carries the full clinical narrative. static_vignette is a
        # near-duplicate (no prompt references it) and static_evidence_items is
        # consumed internally (atomic-finding extraction reads it off the state
        # object, not the payload) — both are dropped from the LLM payload.
        d.pop("static_vignette", None)
        d.pop("static_evidence_items", None)

        return d
