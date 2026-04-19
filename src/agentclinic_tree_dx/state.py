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
    candidate_leaves: list[CandidateLeaf] = field(default_factory=list)
    pending_results: list[dict[str, Any]] = field(default_factory=list)
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    interrupt: InterruptState = field(default_factory=lambda: InterruptState(False, ""))
    termination: TerminationState = field(
        default_factory=lambda: TerminationState(False, "continue", "")
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
