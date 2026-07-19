"""Auditable stopping policies for L1 Evidence-BFS.

The scores consumed here are ordinal algorithm scores, not calibrated clinical
probabilities.  Policies therefore operate as bounded evidence-processing
governors; they do not implement SPRT, Bayesian EVSI, or diagnostic confidence.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence


STOP_SCHEMA_VERSION = 1
VALID_ACTIONS = frozenset({"continue", "stop"})
VALID_CHALLENGE_STATUS = frozenset({"continue", "none", "uncertain"})
FORBIDDEN_STOP_KEYS = frozenset({
    "is_gold",
    "gold",
    "gold_option",
    "gold_diagnosis",
    "role",
    "favors",
    "decisive",
    "direction_target",
    "target",
    "confidence",
    "probability",
})

ChallengeAdvisor = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _assert_label_blind(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_STOP_KEYS:
                raise ValueError(f"forbidden stopping field at {path}.{key}")
            _assert_label_blind(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_label_blind(item, path=f"{path}[{index}]")


def _normalized(values: Mapping[str, float]) -> dict[str, float]:
    positive = {
        str(key): max(float(value), 1e-12) for key, value in values.items()
    }
    total = sum(positive.values())
    if not positive:
        return {}
    if total <= 0:
        return {key: 1.0 / len(positive) for key in positive}
    return {key: value / total for key, value in positive.items()}


def jensen_shannon_divergence(
    before: Mapping[str, float], after: Mapping[str, float],
) -> float:
    """Return natural-log Jensen-Shannon divergence over matching branch IDs."""
    keys = sorted(set(before) | set(after))
    if not keys:
        return 0.0
    left = _normalized({key: before.get(key, 0.0) for key in keys})
    right = _normalized({key: after.get(key, 0.0) for key in keys})
    midpoint = {key: (left[key] + right[key]) / 2.0 for key in keys}

    def kl(source: Mapping[str, float]) -> float:
        return sum(
            source[key] * math.log(source[key] / midpoint[key])
            for key in keys
            if source[key] > 0 and midpoint[key] > 0
        )

    # Round-off can produce a tiny negative value even though JS divergence is
    # non-negative by definition. Keep the serialized stopping contract exact.
    return max(0.0, 0.5 * (kl(left) + kl(right)))


def _ordered_ids(values: Mapping[str, float]) -> list[str]:
    return sorted(values, key=lambda key: (-float(values[key]), str(key)))


@dataclass(frozen=True)
class StopSnapshot:
    """Label-blind cycle-boundary state used by every stopping policy."""

    cycle_index: int
    micro_round: int
    queue_length: int
    eligible_count: int
    top1_id: str
    top2_id: str
    top1_stable_cycles: int
    margin_z: float
    cycle_js: float
    effective_updates: int
    target_turnover: bool
    canonical_novel_count: int
    compiler_hit_count: int
    provenance_hit_count: int
    pool_exhausted: bool
    empty_queue_streak: int = 0
    leader_support_count: int = 0
    leader_against_count: int = 0
    schema_version: int = STOP_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != STOP_SCHEMA_VERSION:
            raise ValueError("unsupported StopSnapshot schema version")
        for name in (
            "cycle_index",
            "micro_round",
            "queue_length",
            "eligible_count",
            "top1_stable_cycles",
            "effective_updates",
            "canonical_novel_count",
            "compiler_hit_count",
            "provenance_hit_count",
            "empty_queue_streak",
            "leader_support_count",
            "leader_against_count",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.queue_length > self.micro_round:
            raise ValueError("queue_length cannot exceed completed micro_rounds")
        if not math.isfinite(self.margin_z) or not math.isfinite(self.cycle_js):
            raise ValueError("stopping scores must be finite")
        if self.cycle_js < 0:
            raise ValueError("cycle_js must be non-negative")
        if self.pool_exhausted != (self.eligible_count == 0):
            raise ValueError("pool_exhausted must match eligible_count")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StopSnapshot":
        snapshot = cls(**dict(value))
        snapshot.validate()
        return snapshot


@dataclass(frozen=True)
class StopDecision:
    """Serializable policy output.  It never contains evaluation labels."""

    action: str
    policy: str
    reason: str
    cycle_index: int
    micro_round: int
    shadow: bool = False
    advisor_called: bool = False
    challenge_status: str = ""
    challenge_fact_ids: tuple[str, ...] = ()
    fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = STOP_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != STOP_SCHEMA_VERSION:
            raise ValueError("unsupported StopDecision schema version")
        if self.action not in VALID_ACTIONS:
            raise ValueError(f"invalid stop action: {self.action}")
        if self.challenge_status and self.challenge_status not in VALID_CHALLENGE_STATUS:
            raise ValueError("invalid challenge status")
        if len(set(self.challenge_fact_ids)) != len(self.challenge_fact_ids):
            raise ValueError("challenge fact IDs must be unique")
        _assert_label_blind(self.metadata, path="decision.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        output = asdict(self)
        output["challenge_fact_ids"] = list(self.challenge_fact_ids)
        return output

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StopDecision":
        data = dict(value)
        data["challenge_fact_ids"] = tuple(data.get("challenge_fact_ids") or ())
        decision = cls(**data)
        decision.validate()
        return decision


def build_stop_snapshot(
    *,
    cycle_index: int,
    micro_round: int,
    queue_length: int,
    eligible_count: int,
    before_scores: Mapping[str, float],
    after_scores: Mapping[str, float],
    previous_top1_id: str,
    previous_stable_cycles: int,
    effective_updates: int,
    canonical_novel_count: int,
    compiler_hit_count: int,
    provenance_hit_count: int,
    empty_queue_streak: int = 0,
    leader_support_count: int = 0,
    leader_against_count: int = 0,
) -> StopSnapshot:
    before_order = _ordered_ids(before_scores)
    after_order = _ordered_ids(after_scores)
    top1_id = after_order[0] if after_order else ""
    top2_id = after_order[1] if len(after_order) > 1 else ""
    stable_cycles = (
        previous_stable_cycles + 1
        if top1_id and top1_id == previous_top1_id else 0
    )
    margin = 0.0
    if top1_id and top2_id:
        normalized = _normalized(after_scores)
        margin = math.log(normalized[top1_id]) - math.log(normalized[top2_id])
    snapshot = StopSnapshot(
        cycle_index=cycle_index,
        micro_round=micro_round,
        queue_length=queue_length,
        eligible_count=eligible_count,
        top1_id=top1_id,
        top2_id=top2_id,
        top1_stable_cycles=stable_cycles,
        margin_z=margin,
        cycle_js=jensen_shannon_divergence(before_scores, after_scores),
        effective_updates=effective_updates,
        target_turnover=before_order[:3] != after_order[:3],
        canonical_novel_count=canonical_novel_count,
        compiler_hit_count=compiler_hit_count,
        provenance_hit_count=provenance_hit_count,
        pool_exhausted=eligible_count == 0,
        empty_queue_streak=empty_queue_streak,
        leader_support_count=leader_support_count,
        leader_against_count=leader_against_count,
    )
    snapshot.validate()
    return snapshot


class StopPolicy(Protocol):
    name: str

    def decide(
        self,
        snapshot: StopSnapshot,
        *,
        context: Mapping[str, Any] | None = None,
        shadow: bool = False,
    ) -> StopDecision:
        ...


@dataclass(frozen=True)
class FixedBudgetPolicy:
    max_micro_rounds: int = 4
    name: str = "fixed_budget"

    def __post_init__(self) -> None:
        if self.max_micro_rounds < 1:
            raise ValueError("max_micro_rounds must be positive")

    def decide(
        self,
        snapshot: StopSnapshot,
        *,
        context: Mapping[str, Any] | None = None,
        shadow: bool = False,
    ) -> StopDecision:
        del context
        if snapshot.pool_exhausted:
            action, reason = "stop", "pool_exhausted"
        elif snapshot.micro_round >= self.max_micro_rounds:
            action, reason = "stop", "fixed_budget_reached"
        else:
            action, reason = "continue", "fixed_budget_remaining"
        return StopDecision(
            action=action,
            policy=self.name,
            reason=reason,
            cycle_index=snapshot.cycle_index,
            micro_round=snapshot.micro_round,
            shadow=shadow,
            metadata={"max_micro_rounds": self.max_micro_rounds},
        )


@dataclass(frozen=True)
class SaturationPolicy:
    min_micro_rounds: int = 2
    max_micro_rounds: int = 8
    stable_cycles: int = 2
    max_cycle_js: float = 0.01
    max_effective_updates: int = 0
    min_margin_z: float = math.log(2.0)
    max_empty_queue_streak: int = 2
    name: str = "saturation"

    def __post_init__(self) -> None:
        if not 1 <= self.min_micro_rounds <= self.max_micro_rounds:
            raise ValueError("invalid adaptive micro-round bounds")
        if self.stable_cycles < 1 or self.max_effective_updates < 0:
            raise ValueError("invalid saturation thresholds")
        if self.max_cycle_js < 0 or not math.isfinite(self.min_margin_z):
            raise ValueError("invalid score thresholds")
        if self.max_empty_queue_streak < 1:
            raise ValueError("max_empty_queue_streak must be positive")

    def is_saturated(self, snapshot: StopSnapshot) -> bool:
        return bool(
            snapshot.top1_stable_cycles >= self.stable_cycles
            and snapshot.cycle_js <= self.max_cycle_js
            and snapshot.effective_updates <= self.max_effective_updates
            and snapshot.margin_z >= self.min_margin_z
        )

    def decide(
        self,
        snapshot: StopSnapshot,
        *,
        context: Mapping[str, Any] | None = None,
        shadow: bool = False,
    ) -> StopDecision:
        del context
        if snapshot.pool_exhausted:
            action, reason = "stop", "pool_exhausted"
        elif snapshot.micro_round >= self.max_micro_rounds:
            action, reason = "stop", "max_micro_rounds_reached"
        elif snapshot.empty_queue_streak >= self.max_empty_queue_streak:
            action, reason = "stop", "empty_queue_fail_safe"
        elif snapshot.micro_round < self.min_micro_rounds:
            action, reason = "continue", "minimum_budget_not_reached"
        elif self.is_saturated(snapshot):
            action, reason = "stop", "saturated"
        else:
            action, reason = "continue", "not_saturated"
        return StopDecision(
            action=action,
            policy=self.name,
            reason=reason,
            cycle_index=snapshot.cycle_index,
            micro_round=snapshot.micro_round,
            shadow=shadow,
            metadata={
                "min_micro_rounds": self.min_micro_rounds,
                "max_micro_rounds": self.max_micro_rounds,
                "stable_cycles": self.stable_cycles,
                "max_cycle_js": self.max_cycle_js,
                "max_effective_updates": self.max_effective_updates,
                "min_margin_z": self.min_margin_z,
            },
        )


@dataclass(frozen=True)
class EvidenceAnchoredF4Policy:
    """Conservative F2-or-F4 policy.

    Unlike :class:`SaturationPolicy`, a schema-valid discriminative update is
    positive evidence for an early exit rather than a reason to keep running.
    The policy never extends beyond the established F4 anchor.
    """

    early_micro_rounds: int = 2
    max_micro_rounds: int = 4
    min_margin_z: float = math.log(3.0)
    min_effective_updates: int = 1
    name: str = "evidence_anchored_f4"

    def __post_init__(self) -> None:
        if not 1 <= self.early_micro_rounds < self.max_micro_rounds:
            raise ValueError("early exit must precede the F4 hard anchor")
        if not math.isfinite(self.min_margin_z):
            raise ValueError("min_margin_z must be finite")
        if self.min_effective_updates < 1:
            raise ValueError("min_effective_updates must be positive")

    def decide(
        self,
        snapshot: StopSnapshot,
        *,
        context: Mapping[str, Any] | None = None,
        shadow: bool = False,
    ) -> StopDecision:
        del context
        if snapshot.pool_exhausted:
            action, reason = "stop", "pool_exhausted"
        elif snapshot.micro_round >= self.max_micro_rounds:
            action, reason = "stop", "f4_anchor_reached"
        elif snapshot.micro_round < self.early_micro_rounds:
            action, reason = "continue", "minimum_early_budget_not_reached"
        elif (
            snapshot.micro_round == self.early_micro_rounds
            and snapshot.margin_z >= self.min_margin_z
            and snapshot.effective_updates >= self.min_effective_updates
        ):
            action, reason = "stop", "f2_evidence_anchored_exit"
        else:
            action, reason = "continue", "continue_to_f4_anchor"
        return StopDecision(
            action=action,
            policy=self.name,
            reason=reason,
            cycle_index=snapshot.cycle_index,
            micro_round=snapshot.micro_round,
            shadow=shadow,
            metadata={
                "early_micro_rounds": self.early_micro_rounds,
                "max_micro_rounds": self.max_micro_rounds,
                "min_margin_z": self.min_margin_z,
                "min_effective_updates": self.min_effective_updates,
            },
        )


@dataclass(frozen=True)
class EvidenceQuorumF4Policy:
    """Stop at F2 only when independent facts form a leader-directed quorum."""

    early_micro_rounds: int = 2
    max_micro_rounds: int = 4
    min_margin_z: float = math.log(1.5)
    min_leader_support: int = 2
    max_leader_against: int = 0
    require_new_leader: bool = True
    name: str = "evidence_quorum_f4"

    def __post_init__(self) -> None:
        if not 1 <= self.early_micro_rounds < self.max_micro_rounds:
            raise ValueError("early exit must precede the F4 hard anchor")
        if not math.isfinite(self.min_margin_z):
            raise ValueError("min_margin_z must be finite")
        if self.min_leader_support < 1 or self.max_leader_against < 0:
            raise ValueError("invalid evidence quorum")

    def decide(
        self,
        snapshot: StopSnapshot,
        *,
        context: Mapping[str, Any] | None = None,
        shadow: bool = False,
    ) -> StopDecision:
        del context
        if snapshot.pool_exhausted:
            action, reason = "stop", "pool_exhausted"
        elif snapshot.micro_round >= self.max_micro_rounds:
            action, reason = "stop", "f4_anchor_reached"
        elif snapshot.micro_round < self.early_micro_rounds:
            action, reason = "continue", "minimum_early_budget_not_reached"
        elif (
            snapshot.micro_round == self.early_micro_rounds
            and snapshot.margin_z >= self.min_margin_z
            and snapshot.leader_support_count >= self.min_leader_support
            and snapshot.leader_against_count <= self.max_leader_against
            and (
                not self.require_new_leader
                or snapshot.top1_stable_cycles == 0
            )
        ):
            action, reason = "stop", "f2_evidence_quorum_exit"
        else:
            action, reason = "continue", "continue_to_f4_anchor"
        return StopDecision(
            action=action,
            policy=self.name,
            reason=reason,
            cycle_index=snapshot.cycle_index,
            micro_round=snapshot.micro_round,
            shadow=shadow,
            metadata={
                "early_micro_rounds": self.early_micro_rounds,
                "max_micro_rounds": self.max_micro_rounds,
                "min_margin_z": self.min_margin_z,
                "min_leader_support": self.min_leader_support,
                "max_leader_against": self.max_leader_against,
                "require_new_leader": self.require_new_leader,
            },
        )


def _clean_challenge_response(
    response: Mapping[str, Any], eligible_ids: Sequence[str],
) -> tuple[str, tuple[str, ...]]:
    _assert_label_blind(response, path="advisor.response")
    status = str(response.get("status") or response.get("verdict") or "").lower()
    if status not in VALID_CHALLENGE_STATUS:
        raise ValueError("advisor returned invalid status")
    raw_ids = response.get("challenge_fact_ids") or []
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    allowed = set(eligible_ids)
    output: list[str] = []
    for value in raw_ids:
        fact_id = str(value or "").strip()
        if fact_id in allowed and fact_id not in output:
            output.append(fact_id)
    if status == "continue" and not output:
        status = "uncertain"
    if status in {"none", "uncertain"}:
        output = []
    return status, tuple(output)


@dataclass
class BoundedAgenticPolicy:
    governor: SaturationPolicy
    advisor: ChallengeAdvisor
    fallback_micro_rounds: int = 4
    audit_all_cycles: bool = False
    name: str = "saturation_challenge"

    def __post_init__(self) -> None:
        if self.fallback_micro_rounds < self.governor.min_micro_rounds:
            raise ValueError("fallback budget cannot be below minimum budget")
        if self.fallback_micro_rounds > self.governor.max_micro_rounds:
            raise ValueError("fallback budget cannot exceed hard maximum")

    def decide(
        self,
        snapshot: StopSnapshot,
        *,
        context: Mapping[str, Any] | None = None,
        shadow: bool = False,
    ) -> StopDecision:
        base = self.governor.decide(snapshot, context=context, shadow=shadow)
        hard_stop = base.reason in {
            "pool_exhausted",
            "max_micro_rounds_reached",
            "empty_queue_fail_safe",
        }
        should_consult = (
            base.reason == "saturated"
            or (
                self.audit_all_cycles
                and not hard_stop
                and snapshot.micro_round >= self.governor.min_micro_rounds
            )
        )
        if not should_consult:
            return StopDecision(
                action=base.action,
                policy=self.name,
                reason=base.reason,
                cycle_index=snapshot.cycle_index,
                micro_round=snapshot.micro_round,
                shadow=shadow,
                metadata={"governor": base.to_dict(), "advisor_audit_only": False},
            )

        payload = dict((context or {}).get("advisor_payload") or {})
        eligible_ids = tuple((context or {}).get("eligible_fact_ids") or ())
        _assert_label_blind(payload, path="advisor.payload")
        try:
            response = self.advisor(payload)
            if not isinstance(response, Mapping):
                raise ValueError("advisor returned non-object response")
            status, challenge_ids = _clean_challenge_response(
                response, eligible_ids,
            )
        except Exception as exc:
            before_fallback = snapshot.micro_round < self.fallback_micro_rounds
            return StopDecision(
                action="continue" if before_fallback else "stop",
                policy=self.name,
                reason=(
                    "advisor_failure_continue_to_f4"
                    if before_fallback else "advisor_failure_stop"
                ),
                cycle_index=snapshot.cycle_index,
                micro_round=snapshot.micro_round,
                shadow=shadow,
                advisor_called=True,
                challenge_status="uncertain",
                fallback=True,
                metadata={
                    "governor": base.to_dict(),
                    "advisor_error": f"{type(exc).__name__}: {exc}",
                },
            )

        if challenge_ids:
            action, reason = "continue", "challenge_veto"
        elif base.reason == "saturated":
            action, reason = "stop", "saturated_no_challenge"
        else:
            action, reason = base.action, base.reason
        return StopDecision(
            action=action,
            policy=self.name,
            reason=reason,
            cycle_index=snapshot.cycle_index,
            micro_round=snapshot.micro_round,
            shadow=shadow,
            advisor_called=True,
            challenge_status=status,
            challenge_fact_ids=challenge_ids,
            metadata={
                "governor": base.to_dict(),
                "advisor_audit_only": base.reason != "saturated",
            },
        )


def policy_config(policy: StopPolicy) -> dict[str, Any]:
    """Return a stable, serializable policy contract for manifests/traces."""
    if isinstance(policy, FixedBudgetPolicy):
        return {
            "type": type(policy).__name__,
            "name": policy.name,
            "max_micro_rounds": policy.max_micro_rounds,
        }
    if isinstance(policy, SaturationPolicy):
        return {"type": type(policy).__name__, **asdict(policy)}
    if isinstance(policy, EvidenceAnchoredF4Policy):
        return {"type": type(policy).__name__, **asdict(policy)}
    if isinstance(policy, EvidenceQuorumF4Policy):
        return {"type": type(policy).__name__, **asdict(policy)}
    if isinstance(policy, BoundedAgenticPolicy):
        return {
            "type": type(policy).__name__,
            "name": policy.name,
            "fallback_micro_rounds": policy.fallback_micro_rounds,
            "audit_all_cycles": policy.audit_all_cycles,
            "governor": asdict(policy.governor),
        }
    return {"type": type(policy).__name__, "name": getattr(policy, "name", "")}
