from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RootNode:
    label: str
    time_course: str
    severity: str
    confidence: float
    supporting_facts: list[str] = field(default_factory=list)
    excluded_candidates: list[str] = field(default_factory=list)


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
    mode_policy: dict[str, Any] = field(default_factory=dict)
    answer_option_mapping: dict[str, float] = field(default_factory=dict)
    tool_use_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
