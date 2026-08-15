#!/usr/bin/env python3
"""Audited online annotation and selector runner for ceiling closure.

The breakthrough experiment builder is intentionally offline-only.  This
module is the narrow online boundary for its annotations, model-panel reviews,
calibration predictions and immutable selector jobs.  It never reads benchmark
truth.  Every payload is checked for target leakage, every response is checked
against the exact frozen candidate/action/edge universe, and operational or
schema failures remain explicit rows for downstream fail-closed gates.

Examples::

  python -m analysis.mechanism_v2.ceiling_closure_online admission-typing \
    --out work/admission_typing --model google/gemini-2.5-flash
  python -m analysis.mechanism_v2.ceiling_closure_online factorization-annotate \
    --freeze work/factorization --out work/factor_annotations --model MODEL
  python -m analysis.mechanism_v2.ceiling_closure_online factorization-review \
    --freeze work/factorization --annotations work/factor_annotations/annotations.jsonl \
    --reviewer A=MODEL_A --reviewer B=MODEL_B --out work/factor_reviews
  python -m analysis.mechanism_v2.ceiling_closure_online selector \
    --jobs work/admission/jobs.jsonl --out work/admission/run --model MODEL

Review outputs produced here are a two-model panel.  They are not human or root
adjudication and must not be relabelled as such downstream.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
# The repository uses a src/ layout.  OnlineJSONCaller imports the production
# client lazily inside worker threads, so direct-script execution must make the
# package root available before those threads start.
sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import ROOT, file_sha256, source_commit  # noqa: E402
from analysis.mechanism_v2.ceiling_breakthrough_experiments import (  # noqa: E402
    _factor_review_payload,
    _factor_review_units,
    _immutable_job_sha256,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    assert_target_blind,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    validate_workers,
)


SCHEMA = "ceiling_closure_online_v1"
E4_POOLS = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/canonical_pools.jsonl"
E4_JOINED = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/E4_JOINED_RESULTS.tar.gz"
MODIFIER_AXES = (
    "etiology",
    "anatomy",
    "time_stage",
    "subtype",
    "complication",
    "composite_components",
)
OBJECT_KINDS = (
    "disease_entity",
    "etiology_agent",
    "anatomic_site",
    "complication",
    "disease_subtype",
    "disease_stage",
    "episode",
    "finding",
    "intervention",
    "other",
    "unresolved",
)
ACTION_TYPES = (
    "history",
    "physical_exam",
    "laboratory",
    "imaging",
    "pathology",
    "genetic",
    "microbiology",
    "procedure",
    "specialist_assessment",
    "other",
)
NEED_TYPES = (
    "etiology",
    "anatomy",
    "time_stage",
    "subtype",
    "complication",
    "object_identity",
    "disease_presence",
    "other",
    "unresolved",
)
MARGINS = frozenset({"high", "medium", "low"})

# Generic target-blindness does not cover all historical audit aliases used by
# this repository.  These keys are forbidden recursively at this online edge.
STRICT_FORBIDDEN_KEYS = frozenset(
    {
        "reference",
        "reference_diagnosis",
        "reference_answer",
        "root_truth",
        "root_relation",
        "truth",
        "label_truth",
        "historical_winner",
        "historical_winners",
        "historical_champion",
        "historical_champions",
        "audit_is_gold",
        "is_gold",
        "gold_candidate_ids",
        "source_option",
        "strict_top1",
        "task_correct",
        "outcome",
        "success",
    }
)

REQUESTED_OBJECT_PROMPT = f"""You are an outcome-blind requested-object parser.
Read only the clinical question/vignette. Do not infer or name the answer. Classify what kind of
object the question requests using exactly one of: {', '.join(OBJECT_KINDS)}. Mark only explicit
modifier axes using: {', '.join(MODIFIER_AXES)}. Return strict JSON:
{{"requested_object":{{"kind":"...","explicit_modifier_axes":["..."]}},"rationale":"brief"}}."""

CANDIDATE_TYPER_PROMPT = f"""You are an outcome-blind ontology typer. Candidate order is arbitrary.
For every supplied opaque candidate ID, classify the label's object kind using exactly one of:
{', '.join(OBJECT_KINDS)}. Do not rank candidates or discuss which answer is correct. Return strict
JSON: {{"candidates":[{{"candidate_id":"ID","object_kind":"..."}}]}}. Cover each ID once."""

FACTORIZER_PROMPT = f"""You are an outcome-blind disease-label factorizer. Candidate order is
arbitrary. For every supplied opaque ID, identify its core clinical entity and its relation to that
core without ranking candidates. Reuse a core_id only for a genuine shared core; never merge merely
related diseases. object_kind must be one of: {', '.join(OBJECT_KINDS)}. Return strict JSON:
{{"candidates":[{{"candidate_id":"ID","core_id":"opaque-core","core_label":"...",
"object_kind":"...","relation_to_core":"identity|qualified_form|component|other",
"unresolved":false}}]}}. Cover each ID once."""

MODIFIER_BINDER_PROMPT = f"""You are an outcome-blind modifier-obligation binder. Separate what an
existing surface diagnosis label asserts from whether the patient vignette supports it. For each
candidate, extract every modifier obligation explicitly asserted in surface_label. Every obligation
must cite one exact surface_span into that label. Then attach zero or more exact support_spans from
the supplied vignette; keep an empty support_spans list when the asserted obligation is unsupported.
Never erase an unsupported obligation, infer a new obligation, rank candidates, or synthesize an
answer. Axes are: {', '.join(MODIFIER_AXES)}. Return strict JSON:
{{"candidates":[{{"candidate_id":"ID","unresolved":false,"modifiers":{{"axis":[{{"value":"...",
"surface_span":{{"start":0,"end":1,"text":"exact label substring"}},"support_spans":
[{{"start":0,"end":1,"text":"exact vignette substring"}}]}}]}}}}]}}.
Cover every ID exactly once; use empty axis arrays only when the surface label asserts no such
obligation."""

FACTOR_REVIEW_PROMPT = """You are one member of an independent model-panel quality review. You are
not a human or root adjudicator. Audit only the explicit core-pair and modifier-axis units. The
payload binds each candidate's original surface_label and its modifier_source_obligations with
exact surface offsets. Do not choose a diagnosis. A core pair is correct only if both surface labels
genuinely share the proposed clinical core; a modifier-axis unit is correct only if every asserted
obligation is actually stated by the cited surface-label text. Echo every supplied unit_id exactly
once in its matching list. Return strict JSON:
{"core_pair_reviews":[{"unit_id":"FP-...","grouped_correct":true,
"unsafe_synonym_merge":false,"unresolved":false}],"modifier_axis_reviews":[
{"unit_id":"FM-...","modifier_correct":true,"unresolved":false}]}."""

ACTIVE_BUILDER_PROMPT = f"""You are an outcome-blind retrospective evidence-release builder. You see
only one raw clinical vignette, never answer options, candidates or benchmark truth. Extract one
contiguous initial-presentation span, then only later actions that were actually performed and have
an explicitly reported result. Do not include a final diagnosis, article title, retrospective answer
statement, an unperformed test, or absence as a negative test. All spans must be exact offsets into
raw_vignette. Return strict JSON:
{{"initial_span":{{"start":0,"end":1,"text":"exact substring"}},"actions":[{{"action_id":"A1",
"action_type":"one of {', '.join(ACTION_TYPES)}","action_name":"...","status":"performed",
"cost":1.0,"cost_band":"low|medium|high","delay":"brief","risk":"brief",
"result_span":{{"start":2,"end":3,"text":"exact substring"}}}}]}}."""

ACTIVE_REVIEW_PROMPT = f"""You are one member of an independent model-panel benchmark audit, not a
human or root adjudicator. Audit every proposed action for historical availability and direct-answer
leakage. Given the initial presentation and supplied candidate set, state the single most important
missing discriminator type using one of: {', '.join(NEED_TYPES)}. For every historically performed
action, independently audit whether its cost/risk metadata are usable, whether it is relevant to and
actually resolves that missing need, its ordinal information gain (0 none, 1 low, 2 moderate, 3 high),
whether its result is bound to the wrong patient episode/object, and whether it is an unnecessary
high-risk action. Do not see or infer which action a policy will later select. Return strict JSON:
{{"need_type":"...","direct_answer_leak":false,"action_reviews":[{{"action_id":"A1",
"availability_valid":true,"cost_valid":true,"risk_valid":true,"relevant":true,
"resolves_need":true,"information_gain":3,"wrong_episode_or_object_binding":false,
"unnecessary_high_risk_action":false}}]}}. Cover every action exactly once."""

ACTIVE_POLICY_PROMPT = f"""You are an outcome-blind typed evidence policy. From the initial
presentation and the supplied candidate/action IDs, state two distinct leading candidate IDs, one
missing discriminator type ({', '.join(NEED_TYPES)}), and exactly one performed action ID. Do not
infer or reveal a hidden result. Return strict JSON: {{"top_pair":["ID","ID"],
"need_type":"...","action_id":"A1","expected_result_and_odds_shift":"brief","abstain":false}}."""

RELATION_REVIEW_PROMPT = """You are one member of an independent model-panel substrate audit, not a
human or root adjudicator. Review every supplied directed is_a edge. Check both label-to-concept
mappings, child-to-parent direction, and whether each candidate's exact cited vignette span closes
the citation. Do not rank or choose a diagnosis. Return strict JSON:
{"edge_reviews":[{"source_id":"ID","target_id":"ID","mapping_correct":true,
"direction_correct":true,"citation_closed":true,"unresolved":false,
"inverse_or_cycle":false}]}. Cover every supplied edge exactly once."""


Validator = Callable[[Mapping[str, Any]], str | None]


@dataclass(frozen=True)
class OnlineTask:
    task_id: str
    module: str
    prompt: str
    payload: dict[str, Any]
    validator: Validator
    metadata: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tar_jsonl(path: Path, member: str = "case_conditions.jsonl") -> list[dict[str, Any]]:
    with tarfile.open(path, "r:gz") as archive:
        handle = archive.extractfile(member)
        if handle is None:
            raise FileNotFoundError(f"{member} absent from {path}")
        return [json.loads(line) for line in handle if line.strip()]


def _assert_closure_blind(value: Any, path: str = "payload") -> None:
    assert_target_blind(value, path)
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in STRICT_FORBIDDEN_KEYS:
                raise AssertionError(f"target/outcome leak at {path}.{key}")
            _assert_closure_blind(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_closure_blind(child, f"{path}[{index}]")


def _response_key_safety(value: Any, path: str = "response") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in STRICT_FORBIDDEN_KEYS:
                return f"forbidden response key at {path}.{key}"
            error = _response_key_safety(child, f"{path}.{key}")
            if error:
                return error
    elif isinstance(value, list):
        for index, child in enumerate(value):
            error = _response_key_safety(child, f"{path}[{index}]")
            if error:
                return error
    return None


def _exact_id_rows(
    rows: Any,
    expected_ids: Iterable[str],
    *,
    key: str = "candidate_id",
    noun: str = "candidate",
) -> tuple[str | None, dict[str, Mapping[str, Any]]]:
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        return f"{noun} rows must be a list of objects", {}
    expected = {str(value) for value in expected_ids}
    ids = [str(row.get(key) or "") for row in rows]
    if len(ids) != len(set(ids)):
        return f"duplicate {noun} IDs", {}
    if set(ids) != expected:
        return f"exact {noun} coverage mismatch", {}
    return None, {str(row[key]): row for row in rows}


def _valid_span(text: str, span: Any) -> bool:
    if not isinstance(span, Mapping):
        return False
    try:
        start, end = int(span.get("start", -1)), int(span.get("end", -1))
    except (TypeError, ValueError):
        return False
    return 0 <= start < end <= len(text) and text[start:end] == str(span.get("text") or "")


def _requested_object_validator(response: Mapping[str, Any]) -> str | None:
    error = _response_key_safety(response)
    if error:
        return error
    requested = response.get("requested_object")
    if not isinstance(requested, Mapping) or str(requested.get("kind")) not in OBJECT_KINDS:
        return "invalid requested_object.kind"
    axes = requested.get("explicit_modifier_axes")
    if not isinstance(axes, list) or len(axes) != len(set(map(str, axes))):
        return "explicit_modifier_axes must be a unique list"
    if set(map(str, axes)) - set(MODIFIER_AXES):
        return "unknown requested modifier axis"
    return None


def _candidate_typer_validator(expected_ids: set[str]) -> Validator:
    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        error, rows = _exact_id_rows(response.get("candidates"), expected_ids)
        if error:
            return error
        if any(str(row.get("object_kind")) not in OBJECT_KINDS for row in rows.values()):
            return "invalid candidate object_kind"
        return None
    return validate


def _factorizer_validator(expected_ids: set[str]) -> Validator:
    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        error, rows = _exact_id_rows(response.get("candidates"), expected_ids)
        if error:
            return error
        for row in rows.values():
            if not str(row.get("core_id") or "") or not str(row.get("core_label") or ""):
                return "empty core identity"
            if str(row.get("object_kind")) not in OBJECT_KINDS:
                return "invalid object_kind"
            if str(row.get("relation_to_core")) not in {"identity", "qualified_form", "component", "other"}:
                return "invalid relation_to_core"
            if not isinstance(row.get("unresolved"), bool):
                return "unresolved must be boolean"
        return None
    return validate


def _modifier_validator(expected_ids: set[str], vignette: str, surface_labels: Mapping[str, str]) -> Validator:
    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        error, rows = _exact_id_rows(response.get("candidates"), expected_ids)
        if error:
            return error
        for row in rows.values():
            if not isinstance(row.get("unresolved"), bool):
                return "unresolved must be boolean"
            modifiers = row.get("modifiers")
            if not isinstance(modifiers, Mapping) or set(map(str, modifiers)) - set(MODIFIER_AXES):
                return "invalid modifier axes"
            for values in modifiers.values():
                if not isinstance(values, list):
                    return "modifier axis value must be a list"
                for claim in values:
                    if not isinstance(claim, Mapping) or not str(claim.get("value") or ""):
                        return "invalid modifier claim"
                    if not _valid_span(str(surface_labels.get(str(row.get("candidate_id"))) or ""), claim.get("surface_span")):
                        return "modifier obligation lacks exact surface-label offset"
                    spans = claim.get("support_spans")
                    if not isinstance(spans, list) or not all(_valid_span(vignette, span) for span in spans):
                        return "modifier claim lacks exact-offset support"
        return None
    return validate


def _factor_review_validator(expected_units: Mapping[str, Mapping[str, Any]]) -> Validator:
    expected_pair_ids = {
        unit_id for unit_id, unit in expected_units.items()
        if unit.get("review_kind") == "core_pair"
    }
    expected_modifier_ids = {
        unit_id for unit_id, unit in expected_units.items()
        if unit.get("review_kind") == "modifier_axis"
    }

    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        error, pair_rows = _exact_id_rows(
            response.get("core_pair_reviews"), expected_pair_ids,
            key="unit_id", noun="core-pair unit",
        )
        if error:
            return error
        error, modifier_rows = _exact_id_rows(
            response.get("modifier_axis_reviews"), expected_modifier_ids,
            key="unit_id", noun="modifier-axis unit",
        )
        if error:
            return error
        for row in pair_rows.values():
            for key in ("grouped_correct", "unsafe_synonym_merge", "unresolved"):
                if not isinstance(row.get(key), bool):
                    return f"{key} must be boolean"
        for row in modifier_rows.values():
            for key in ("modifier_correct", "unresolved"):
                if not isinstance(row.get(key), bool):
                    return f"{key} must be boolean"
        return None
    return validate


def _active_builder_validator(raw: str) -> Validator:
    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        initial = response.get("initial_span")
        if not _valid_span(raw, initial):
            return "initial presentation is not an exact span"
        actions = response.get("actions")
        if not isinstance(actions, list) or not all(isinstance(action, Mapping) for action in actions):
            return "actions must be a list of objects"
        ids = [str(action.get("action_id") or "") for action in actions]
        if any(not re.fullmatch(r"A[1-9][0-9]*", action_id) for action_id in ids) or len(ids) != len(set(ids)):
            return "invalid or duplicate action IDs"
        initial_interval = (int(initial["start"]), int(initial["end"]))
        intervals: list[tuple[int, int]] = []
        for action in actions:
            if str(action.get("status")) != "performed":
                return "only historically performed actions are allowed"
            if str(action.get("action_type")) not in ACTION_TYPES:
                return "invalid action_type"
            if str(action.get("cost_band")) not in {"low", "medium", "high"}:
                return "invalid cost_band"
            if not isinstance(action.get("cost"), (int, float)) or float(action["cost"]) < 0:
                return "cost must be a non-negative number"
            span = action.get("result_span")
            if not _valid_span(raw, span):
                return "action result is not an exact span"
            interval = (int(span["start"]), int(span["end"]))
            if interval[0] < initial_interval[1]:
                return "action result is not later than initial presentation"
            if interval[0] < initial_interval[1] and initial_interval[0] < interval[1]:
                return "action result overlaps initial presentation"
            intervals.append(interval)
        if any(a[0] < b[1] and b[0] < a[1] for index, a in enumerate(intervals) for b in intervals[index + 1 :]):
            return "action result spans overlap"
        return None
    return validate


def _active_review_validator(actions_by_id: Mapping[str, Mapping[str, Any]]) -> Validator:
    action_ids = set(actions_by_id)

    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        if str(response.get("need_type")) not in NEED_TYPES:
            return "invalid need_type"
        if not isinstance(response.get("direct_answer_leak"), bool):
            return "direct_answer_leak must be boolean"
        error, rows = _exact_id_rows(response.get("action_reviews"), action_ids, key="action_id", noun="action")
        if error:
            return error
        for row in rows.values():
            for key in (
                "availability_valid", "cost_valid", "risk_valid", "relevant", "resolves_need",
                "wrong_episode_or_object_binding", "unnecessary_high_risk_action",
            ):
                if not isinstance(row.get(key), bool):
                    return f"{key} must be boolean"
            information_gain = row.get("information_gain")
            if not isinstance(information_gain, int) or isinstance(information_gain, bool) or information_gain not in {0, 1, 2, 3}:
                return "information_gain must be an integer from 0 to 3"
            if row.get("resolves_need") and (not row.get("relevant") or information_gain == 0):
                return "a resolving action must be relevant and informative"
        return None
    return validate


def _policy_validator(candidate_ids: set[str], action_ids: set[str]) -> Validator:
    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        pair = response.get("top_pair")
        if not isinstance(pair, list) or len(pair) != 2 or len(set(map(str, pair))) != 2:
            return "top_pair must contain two distinct IDs"
        if set(map(str, pair)) - candidate_ids:
            return "top_pair contains unknown candidate"
        if str(response.get("need_type")) not in NEED_TYPES:
            return "invalid need_type"
        if str(response.get("action_id")) not in action_ids:
            return "unknown/non-performed action_id"
        if not isinstance(response.get("abstain"), bool):
            return "abstain must be boolean"
        return None
    return validate


def _relation_review_validator(expected_edges: set[tuple[str, str]]) -> Validator:
    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        rows = response.get("edge_reviews")
        if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
            return "edge_reviews must be a list of objects"
        keys = [(str(row.get("source_id") or ""), str(row.get("target_id") or "")) for row in rows]
        if len(keys) != len(set(keys)) or set(keys) != expected_edges:
            return "exact directed-edge coverage mismatch"
        for row in rows:
            for key in ("mapping_correct", "direction_correct", "citation_closed", "unresolved", "inverse_or_cycle"):
                if not isinstance(row.get(key), bool):
                    return f"{key} must be boolean"
        return None
    return validate


def _selector_validator(
    payload: Mapping[str, Any], *, require_modifier_hallucination: bool = False
) -> Validator:
    candidate_rows = payload.get("candidates")
    if candidate_rows is None:
        candidate_rows = payload.get("main_frontier")
    if not isinstance(candidate_rows, list):
        raise AssertionError("selector payload has no candidate list")
    candidate_ids = {str(row["candidate_id"]) for row in candidate_rows}
    if len(candidate_ids) != len(candidate_rows) or not candidate_ids:
        raise AssertionError("selector candidate IDs are empty or duplicated")
    vignette = str(payload.get("vignette") or payload.get("initial_vignette") or "")
    lattice = payload.get("lattice")
    lattice_core_ids: set[str] = set()
    lattice_edge_by_candidate: dict[str, Mapping[str, Any]] = {}
    if lattice is not None:
        if not isinstance(lattice, Mapping):
            raise AssertionError("lattice must be an object")
        core_nodes = lattice.get("core_nodes")
        member_edges = lattice.get("member_edges")
        if not isinstance(core_nodes, list) or not isinstance(member_edges, list):
            raise AssertionError("lattice requires core_nodes and member_edges")
        lattice_core_ids = {str(row.get("core_id") or "") for row in core_nodes if isinstance(row, Mapping)}
        if len(lattice_core_ids) != len(core_nodes) or "" in lattice_core_ids:
            raise AssertionError("lattice core IDs are empty or duplicated")
        for edge in member_edges:
            if not isinstance(edge, Mapping):
                raise AssertionError("lattice member edge must be an object")
            candidate_id = str(edge.get("candidate_id") or "")
            core_id = str(edge.get("core_id") or "")
            if candidate_id in lattice_edge_by_candidate or candidate_id not in candidate_ids or core_id not in lattice_core_ids:
                raise AssertionError("invalid lattice member edge")
            obligations = edge.get("modifier_obligations")
            if not isinstance(obligations, Mapping) or set(map(str, obligations)) - set(MODIFIER_AXES):
                raise AssertionError("invalid lattice modifier obligations")
            lattice_edge_by_candidate[candidate_id] = edge
        if set(lattice_edge_by_candidate) != candidate_ids:
            raise AssertionError("lattice must cover every surface candidate exactly once")
        for node in core_nodes:
            members = [str(value) for value in node.get("member_candidate_ids") or []]
            expected_members = sorted(
                candidate_id for candidate_id, edge in lattice_edge_by_candidate.items()
                if str(edge["core_id"]) == str(node["core_id"])
            )
            if sorted(members) != expected_members or len(members) != len(set(members)):
                raise AssertionError("lattice core/member adjacency mismatch")

    def validate(response: Mapping[str, Any]) -> str | None:
        error = _response_key_safety(response)
        if error:
            return error
        champion = str(response.get("champion_id") or "")
        runner = str(response.get("runner_up_id") or "")
        if champion not in candidate_ids:
            return "champion_id is not a supplied candidate"
        if runner and (runner not in candidate_ids or runner == champion):
            return "invalid runner_up_id"
        if str(response.get("margin")) not in MARGINS:
            return "invalid margin"
        if require_modifier_hallucination and not isinstance(
            response.get("modifier_hallucination"), bool
        ):
            return "modifier_hallucination must be boolean"
        if lattice is not None:
            selected_core = str(response.get("selected_core_id") or "")
            if selected_core not in lattice_core_ids:
                return "selected_core_id is not a supplied core"
            if champion in lattice_edge_by_candidate and str(lattice_edge_by_candidate[champion]["core_id"]) != selected_core:
                return "champion is not a member of selected_core_id"
            obligations = lattice_edge_by_candidate.get(champion, {}).get("modifier_obligations") or {}
            expected_axes = {str(axis) for axis, values in obligations.items() if values}
            check = response.get("obligation_check")
            if not isinstance(check, Mapping) or set(map(str, check)) != expected_axes:
                return "obligation_check does not cover chosen surface obligations"
            if any(str(value) not in {"supported", "unsupported"} for value in check.values()):
                return "invalid obligation_check status"
        spans = response.get("decisive_spans")
        if not isinstance(spans, list) or not spans or not all(_valid_span(vignette, span) for span in spans):
            return "decisive_spans must contain exact vignette offsets"
        return None
    return validate


def _policy_job_validator(payload: Mapping[str, Any]) -> Validator:
    candidates = payload.get("candidates") or []
    actions = payload.get("action_menu") or []
    candidate_ids = {str(row["candidate_id"]) for row in candidates}
    action_ids = {str(row["action_id"]) for row in actions}
    if len(candidate_ids) != len(candidates) or len(action_ids) != len(actions):
        raise AssertionError("duplicated candidate/action IDs in policy job")
    return _policy_validator(candidate_ids, action_ids)


def _run_tasks(
    tasks: Sequence[OnlineTask],
    *,
    out_dir: Path,
    model: str,
    workers: int,
    cache_only: bool,
    call_timeout: int,
    max_retries: int,
    client_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    workers = validate_workers(workers, rag=False)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if len({task.task_id for task in tasks}) != len(tasks):
        raise AssertionError("duplicate online task_id")
    for task in tasks:
        _assert_closure_blind(task.payload)
    telemetry_path = out_dir / "telemetry.jsonl"
    # Materialize an empty raw ledger even when cache-only lookup never reaches
    # a provider.  Downstream gates can then bind a concrete zero-event file
    # instead of treating absence as evidence of zero calls.
    telemetry_path.touch(exist_ok=True)
    caller = OnlineJSONCaller(
        out_dir=out_dir,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=call_timeout,
        max_retries=max_retries,
        client_factory=client_factory,
    )

    def one(task: OnlineTask) -> dict[str, Any]:
        try:
            outcome = caller.call(
                module=task.module,
                prompt=task.prompt,
                payload=task.payload,
                validator=task.validator,
                cache_only=cache_only,
            )
            return {
                "schema": SCHEMA,
                "task_id": task.task_id,
                **task.metadata,
                "model": model,
                "success": bool(outcome.success),
                "error": outcome.error,
                "response": outcome.response,
                "cache_hit": bool(outcome.cache_hit),
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        except Exception as exc:  # ITA: operational failure is retained.
            return {
                "schema": SCHEMA,
                "task_id": task.task_id,
                **task.metadata,
                "model": model,
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "response": {},
                "cache_hit": False,
                "cache_key": "",
                "prompt_sha256": _sha_text(task.prompt),
                "payload_sha256": canonical_sha256(task.payload),
            }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, task): task.task_id for task in tasks}
        for done, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if done % 20 == 0 or done == len(tasks):
                print(f"completed={done}/{len(tasks)} failures={sum(not row['success'] for row in rows)}", flush=True)
    rows.sort(key=lambda row: str(row["task_id"]))
    result_path = out_dir / "raw_results.jsonl"
    write_jsonl(result_path, rows)
    telemetry = read_jsonl(telemetry_path)
    telemetry_summary = aggregate_telemetry(telemetry)
    atomic_json(out_dir / "telemetry_summary.json", telemetry_summary)
    manifest = {
        "schema": SCHEMA,
        "kind": "online_stage_manifest",
        "source_commit": source_commit(),
        "runner_code_sha256": file_sha256(Path(__file__)),
        "online_runner_code_sha256": file_sha256(ROOT / "analysis/mechanism_v2/online_runner.py"),
        "model": model,
        "workers": workers,
        "cache_only": bool(cache_only),
        "task_n": len(tasks),
        "success_n": sum(bool(row["success"]) for row in rows),
        "failure_n": sum(not bool(row["success"]) for row in rows),
        "cache_hit_n": sum(bool(row["cache_hit"]) for row in rows),
        "semantic_input_sha256": canonical_sha256([
            {"task_id": task.task_id, "module": task.module, "prompt": task.prompt, "payload": task.payload}
            for task in tasks
        ]),
        "prompt_sha256s": sorted({_sha_text(task.prompt) for task in tasks}),
        "results_sha256": canonical_sha256(rows),
        "results_file_sha256": file_sha256(result_path),
        "telemetry_sha256": file_sha256(telemetry_path) if telemetry_path.is_file() else "",
        "telemetry_summary": telemetry_summary,
        "api_called": bool(telemetry_summary.get("semantic_calls") or telemetry_summary.get("physical_attempts")),
        "capabilities": dependency_capabilities(),
        "created_at_utc": _utc_now(),
    }
    atomic_json(out_dir / "manifest.json", manifest)
    return rows


def _call_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "workers": args.workers,
        "cache_only": args.cache_only,
        "call_timeout": args.call_timeout,
        "max_retries": args.max_retries,
    }


def _e4_cases(pools: Path, joined: Path) -> list[dict[str, Any]]:
    vignettes: dict[str, str] = {}
    for row in _tar_jsonl(joined):
        vignettes.setdefault(str(row["case_key"]), str(row["vignette"]))
    cases: list[dict[str, Any]] = []
    for row in read_jsonl(pools):
        case_key = str(row["case_key"])
        candidates = [
            {"candidate_id": str(candidate["candidate_id"]), "label": str(candidate["label"])}
            for candidate in row["pool"]["candidates"]
        ]
        if case_key not in vignettes or len({c["candidate_id"] for c in candidates}) != len(candidates):
            raise AssertionError(f"invalid E4 source case {case_key}")
        cases.append({"case_key": case_key, "family": str(row["family"]), "vignette": vignettes[case_key], "candidates": candidates})
    if len({case["case_key"] for case in cases}) != len(cases):
        raise AssertionError("duplicate E4 case_key")
    return sorted(cases, key=lambda row: row["case_key"])


def run_admission_typing(
    *, out: Path, model: str, pools: Path = E4_POOLS, joined: Path = E4_JOINED,
    workers: int = 50, cache_only: bool = False, call_timeout: int = 240,
    max_retries: int = 2, client_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    cases = _e4_cases(pools, joined)
    tasks: list[OnlineTask] = []
    for case in cases:
        case_key = case["case_key"]
        tasks.append(OnlineTask(
            f"{case_key}|requested_object", "CeilingAdmissionRequestedObject", REQUESTED_OBJECT_PROMPT,
            {"case_key": case_key, "vignette": case["vignette"]}, _requested_object_validator,
            {"case_key": case_key, "stage": "requested_object"},
        ))
        ids = {c["candidate_id"] for c in case["candidates"]}
        tasks.append(OnlineTask(
            f"{case_key}|candidate_typer", "CeilingAdmissionCandidateTyper", CANDIDATE_TYPER_PROMPT,
            {"case_key": case_key, "candidates": case["candidates"]}, _candidate_typer_validator(ids),
            {"case_key": case_key, "stage": "candidate_typer"},
        ))
    raw = _run_tasks(tasks, out_dir=Path(out) / "online", model=model, workers=workers,
                     cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                     client_factory=client_factory)
    by_key = {(row["case_key"], row["stage"]): row for row in raw}
    annotations: list[dict[str, Any]] = []
    for case in cases:
        parser = by_key[(case["case_key"], "requested_object")]
        typer = by_key[(case["case_key"], "candidate_typer")]
        requested = (parser["response"].get("requested_object") if parser["success"] else None) or {
            "kind": "unresolved", "explicit_modifier_axes": []
        }
        typed = {str(row["candidate_id"]): row for row in (typer["response"].get("candidates") or [])} if typer["success"] else {}
        annotations.append({
            "case_key": case["case_key"],
            "requested_object": requested,
            "candidates": [
                {"candidate_id": candidate["candidate_id"], "object_kind": str((typed.get(candidate["candidate_id"]) or {}).get("object_kind") or "unresolved")}
                for candidate in case["candidates"]
            ],
            "annotation_success": bool(parser["success"] and typer["success"]),
            "stage_errors": {"requested_object": parser["error"], "candidate_typer": typer["error"]},
            "provenance": "outcome_blind_model_annotation",
        })
    return _finalize_product(Path(out), "admission_typing", annotations, [pools, joined], model=model)


def _freeze_cases(freeze: Path, component: str) -> tuple[list[dict[str, Any]], Path]:
    freeze = Path(freeze)
    cases_path = freeze / "cases.jsonl"
    manifest_path = freeze / "freeze.json"
    if not cases_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("freeze must contain cases.jsonl and freeze.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("component")) != component:
        raise AssertionError(f"expected {component} freeze")
    cases = read_jsonl(cases_path)
    if canonical_sha256(cases) != str(manifest.get("cases_sha256")):
        raise AssertionError("freeze cases hash mismatch")
    if len({str(case["case_key"]) for case in cases}) != len(cases):
        raise AssertionError("duplicate freeze case_key")
    for case in cases:
        _assert_closure_blind(case)
    return cases, cases_path


def _fallback_factor_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "candidate_id": str(candidate["candidate_id"]), "core_id": f"UNRESOLVED-{candidate['candidate_id']}",
        "core_label": str(candidate["label"]), "object_kind": "unresolved", "relation_to_core": "other",
        "surface_label": str(candidate["label"]),
        "modifiers": {axis: [] for axis in MODIFIER_AXES},
        "modifier_source_obligations": {axis: [] for axis in MODIFIER_AXES},
        "unresolved": True,
    } for candidate in candidates]


def run_factorization_annotations(
    *, freeze: Path, out: Path, model: str, workers: int = 50, cache_only: bool = False,
    call_timeout: int = 240, max_retries: int = 2, client_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    cases, cases_path = _freeze_cases(freeze, "factorization")
    first_tasks: list[OnlineTask] = []
    for case in cases:
        ids = {str(c["candidate_id"]) for c in case["candidates"]}
        first_tasks.extend([
            OnlineTask(f"{case['case_key']}|factorizer", "CeilingObjectFactorizer", FACTORIZER_PROMPT,
                       {"case_key": case["case_key"], "candidates": case["candidates"]},
                       _factorizer_validator(ids), {"case_key": case["case_key"], "stage": "factorizer"}),
            OnlineTask(f"{case['case_key']}|requested_object", "CeilingFactorRequestedObject", REQUESTED_OBJECT_PROMPT,
                       {"case_key": case["case_key"], "vignette": case["vignette"]},
                       _requested_object_validator, {"case_key": case["case_key"], "stage": "requested_object"}),
        ])
    first = _run_tasks(first_tasks, out_dir=Path(out) / "factorizer_parser", model=model, workers=workers,
                       cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                       client_factory=client_factory)
    first_index = {(row["case_key"], row["stage"]): row for row in first}
    binder_tasks: list[OnlineTask] = []
    for case in cases:
        factor = first_index[(case["case_key"], "factorizer")]
        if not factor["success"]:
            continue
        ids = {str(c["candidate_id"]) for c in case["candidates"]}
        surface_labels = {str(c["candidate_id"]): str(c["label"]) for c in case["candidates"]}
        factor_candidates = [
            {**row, "surface_label": surface_labels[str(row["candidate_id"])]}
            for row in factor["response"]["candidates"]
        ]
        binder_tasks.append(OnlineTask(
            f"{case['case_key']}|modifier_binder", "CeilingModifierBinder", MODIFIER_BINDER_PROMPT,
            {"case_key": case["case_key"], "vignette": case["vignette"], "candidates": factor_candidates},
            _modifier_validator(ids, str(case["vignette"]), surface_labels), {"case_key": case["case_key"], "stage": "modifier_binder"},
        ))
    binder = _run_tasks(binder_tasks, out_dir=Path(out) / "modifier_binder", model=model, workers=workers,
                        cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                        client_factory=client_factory)
    binder_index = {row["case_key"]: row for row in binder}
    annotations: list[dict[str, Any]] = []
    for case in cases:
        factor = first_index[(case["case_key"], "factorizer")]
        parser = first_index[(case["case_key"], "requested_object")]
        bound = binder_index.get(case["case_key"])
        merged = _fallback_factor_candidates(case["candidates"])
        if factor["success"] and bound and bound["success"]:
            factor_by_id = {str(row["candidate_id"]): row for row in factor["response"]["candidates"]}
            bind_by_id = {str(row["candidate_id"]): row for row in bound["response"]["candidates"]}
            merged = []
            for candidate in case["candidates"]:
                candidate_id = str(candidate["candidate_id"])
                mapped, binding = factor_by_id[candidate_id], bind_by_id[candidate_id]
                modifiers = {axis: list((binding.get("modifiers") or {}).get(axis) or []) for axis in MODIFIER_AXES}
                merged.append({
                    "candidate_id": candidate_id, "core_id": str(mapped["core_id"]),
                    "core_label": str(mapped["core_label"]), "object_kind": str(mapped["object_kind"]),
                    "relation_to_core": str(mapped["relation_to_core"]),
                    "surface_label": str(candidate["label"]),
                    "modifiers": modifiers, "modifier_source_obligations": modifiers,
                    "unresolved": bool(mapped.get("unresolved") or binding.get("unresolved")),
                })
        annotations.append({
            "case_key": case["case_key"],
            "requested_object": (parser["response"].get("requested_object") if parser["success"] else None) or {"kind": "unresolved", "explicit_modifier_axes": []},
            "candidates": merged,
            "annotation_success": bool(factor["success"] and parser["success"] and bound and bound["success"]),
            "stage_errors": {"factorizer": factor["error"], "requested_object": parser["error"], "modifier_binder": "missing_after_factorizer_failure" if not bound else bound["error"]},
            "provenance": "outcome_blind_model_annotation",
        })
    return _finalize_product(Path(out), "factorization_annotations", annotations, [cases_path], model=model)


def _review_specs(values: Sequence[str]) -> list[tuple[str, str]]:
    specs: list[tuple[str, str]] = []
    for value in values:
        reviewer_id, separator, model = value.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z0-9_.-]+", reviewer_id) or not model:
            raise ValueError("--reviewer must be REVIEWER_ID=MODEL")
        specs.append((reviewer_id, model))
    if len(specs) != 2 or len({item[0] for item in specs}) != 2 or len({item[1] for item in specs}) != 2:
        raise ValueError("exactly two distinct reviewer IDs and two distinct models are required")
    return specs


def _assert_review_spec_tuples(specs: Sequence[tuple[str, str]]) -> None:
    if (
        len(specs) != 2
        or len({str(item[0]) for item in specs}) != 2
        or len({str(item[1]) for item in specs}) != 2
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", str(item[0])) or not str(item[1]) for item in specs)
    ):
        raise ValueError("exactly two distinct reviewer IDs and two distinct models are required")


def _factor_decision(row: Mapping[str, Any]) -> str:
    if row.get("unresolved"):
        return "unresolved"
    grouped, modifier = bool(row.get("grouped_correct")), bool(row.get("modifier_correct"))
    return "accept" if grouped and modifier else ("reject_both" if not grouped and not modifier else ("reject_grouping" if not grouped else "reject_modifiers"))


def run_factorization_reviews(
    *, freeze: Path, annotations: Path, out: Path, reviewer_specs: Sequence[tuple[str, str]],
    workers: int = 50, cache_only: bool = False, call_timeout: int = 240, max_retries: int = 2,
    client_factories: Mapping[str, Callable[[], Any]] | None = None,
) -> list[dict[str, Any]]:
    _assert_review_spec_tuples(reviewer_specs)
    cases, cases_path = _freeze_cases(freeze, "factorization")
    anns = {str(row["case_key"]): row for row in read_jsonl(annotations)}
    if set(anns) != {str(case["case_key"]) for case in cases}:
        raise AssertionError("factor annotation case coverage mismatch")
    flat: list[dict[str, Any]] = []
    for reviewer_id, model in reviewer_specs:
        tasks: list[OnlineTask] = []
        for case in cases:
            ann = anns[case["case_key"]]
            payload = _factor_review_payload(case, ann)
            expected_units = _factor_review_units(payload)
            tasks.append(OnlineTask(
                f"{case['case_key']}|factor_review|{reviewer_id}", f"CeilingFactorModelPanel_{reviewer_id}", FACTOR_REVIEW_PROMPT,
                payload, _factor_review_validator(expected_units),
                {"case_key": case["case_key"], "reviewer_id": reviewer_id, "stage": "factorization_model_panel"},
            ))
        raw = _run_tasks(tasks, out_dir=Path(out) / reviewer_id, model=model, workers=workers,
                         cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                         client_factory=(client_factories or {}).get(reviewer_id))
        raw_by_case = {str(row["case_key"]): row for row in raw}
        for case in cases:
            row = raw_by_case[case["case_key"]]
            ann = anns[case["case_key"]]
            payload = _factor_review_payload(case, ann)
            units = _factor_review_units(payload)
            response = row["response"] if row["success"] else {}
            pair_response = {
                str(item["unit_id"]): item
                for item in response.get("core_pair_reviews", [])
            }
            modifier_response = {
                str(item["unit_id"]): item
                for item in response.get("modifier_axis_reviews", [])
            }
            for unit_id, unit in units.items():
                if unit["review_kind"] == "core_pair":
                    item = pair_response.get(unit_id) or {
                        "grouped_correct": False,
                        "unsafe_synonym_merge": False,
                        "unresolved": True,
                    }
                    grouped_correct = bool(item.get("grouped_correct"))
                    unsafe_merge = bool(item.get("unsafe_synonym_merge"))
                    unresolved = bool(item.get("unresolved", True))
                    decision = (
                        "accept" if grouped_correct and not unsafe_merge and not unresolved
                        else "reject_grouping"
                    )
                    unit_fields = {
                        "left_id": str(unit["left_id"]),
                        "right_id": str(unit["right_id"]),
                        "core_id": str(unit["core_id"]),
                        "grouped_correct": grouped_correct,
                        "modifier_correct": True,
                        "unsafe_synonym_merge": unsafe_merge,
                        "unresolved": unresolved,
                    }
                else:
                    item = modifier_response.get(unit_id) or {
                        "modifier_correct": False,
                        "unresolved": True,
                    }
                    modifier_correct = bool(item.get("modifier_correct"))
                    unresolved = bool(item.get("unresolved", True))
                    decision = "accept" if modifier_correct and not unresolved else "reject_modifiers"
                    unit_fields = {
                        "left_id": str(unit["candidate_id"]),
                        "right_id": str(unit["core_id"]),
                        "core_id": str(unit["core_id"]),
                        "modifier_axis": str(unit["modifier_axis"]),
                        "grouped_correct": True,
                        "modifier_correct": modifier_correct,
                        "unsafe_synonym_merge": False,
                        "unresolved": unresolved,
                    }
                flat.append({
                    "case_key": case["case_key"], "unit_id": unit_id,
                    "unit_sha256": str(unit["unit_sha256"]),
                    "review_kind": str(unit["review_kind"]), **unit_fields,
                    "reviewer_id": reviewer_id, "reviewer_model": model, "panel_provenance": "independent_model_panel",
                    "decision": decision, "success": bool(row["success"]), "error": row["error"],
                    "cache_key": row["cache_key"], "payload_sha256": row["payload_sha256"], "prompt_sha256": row["prompt_sha256"],
                    "response_sha256": canonical_sha256(row["response"]),
                })
    return _finalize_panel(Path(out), "factorization_reviews", flat, [cases_path, annotations], reviewer_specs)


def run_active_builder(
    *, freeze: Path, out: Path, model: str, workers: int = 50, cache_only: bool = False,
    call_timeout: int = 240, max_retries: int = 2, client_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    cases, cases_path = _freeze_cases(freeze, "active")
    tasks: list[OnlineTask] = []
    for case in cases:
        raw = str(case["builder_payload"]["raw_vignette"])
        # Deliberately pass no policy_candidates to the builder.
        payload = {"case_key": case["case_key"], "raw_vignette": raw}
        if "candidates" in payload:
            raise AssertionError("active builder candidate leak")
        tasks.append(OnlineTask(f"{case['case_key']}|active_builder", "CeilingActiveEvidenceBuilder", ACTIVE_BUILDER_PROMPT,
                                payload, _active_builder_validator(raw), {"case_key": case["case_key"], "stage": "active_builder"}))
    raw_rows = _run_tasks(tasks, out_dir=Path(out) / "online", model=model, workers=workers,
                          cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                          client_factory=client_factory)
    annotations: list[dict[str, Any]] = []
    raw_by_case = {str(row["case_key"]): row for row in raw_rows}
    for case in cases:
        row = raw_by_case[case["case_key"]]
        response = row["response"] if row["success"] else {}
        initial_span = response.get("initial_span") or {}
        annotations.append({
            "case_key": case["case_key"],
            "initial_text": str(initial_span.get("text") or ""),
            "initial_span": initial_span,
            "actions": list(response.get("actions") or []),
            "annotation_success": bool(row["success"]), "error": row["error"],
            "provenance": "outcome_blind_model_builder",
        })
    return _finalize_product(Path(out), "active_builder_annotations", annotations, [cases_path], model=model)


def _load_exact_annotations(path: Path, case_keys: set[str]) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path)
    if len({str(row["case_key"]) for row in rows}) != len(rows):
        raise AssertionError("duplicate annotation case_key")
    output = {str(row["case_key"]): row for row in rows}
    if set(output) != case_keys:
        raise AssertionError("annotation case coverage mismatch")
    return output


def run_active_reviews(
    *, freeze: Path, annotations: Path, out: Path, reviewer_specs: Sequence[tuple[str, str]],
    workers: int = 50, cache_only: bool = False, call_timeout: int = 240, max_retries: int = 2,
    client_factories: Mapping[str, Callable[[], Any]] | None = None,
) -> list[dict[str, Any]]:
    _assert_review_spec_tuples(reviewer_specs)
    cases, cases_path = _freeze_cases(freeze, "active")
    anns = _load_exact_annotations(annotations, {str(case["case_key"]) for case in cases})
    flat: list[dict[str, Any]] = []
    for reviewer_id, model in reviewer_specs:
        tasks: list[OnlineTask] = []
        for case in cases:
            ann = anns[case["case_key"]]
            actions_by_id = {str(action["action_id"]): action for action in ann.get("actions") or []}
            tasks.append(OnlineTask(
                f"{case['case_key']}|active_review|{reviewer_id}", f"CeilingActiveModelPanel_{reviewer_id}", ACTIVE_REVIEW_PROMPT,
                {"case_key": case["case_key"], "raw_vignette": case["builder_payload"]["raw_vignette"],
                 "policy_candidates": case["policy_candidates"], "builder_annotation": ann},
                _active_review_validator(actions_by_id), {"case_key": case["case_key"], "reviewer_id": reviewer_id, "stage": "active_model_panel"},
            ))
        raw = _run_tasks(tasks, out_dir=Path(out) / reviewer_id, model=model, workers=workers,
                         cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                         client_factory=(client_factories or {}).get(reviewer_id))
        for row in raw:
            ann = anns[row["case_key"]]
            response = row["response"] if row["success"] else {}
            action_review = {str(item["action_id"]): item for item in response.get("action_reviews", [])}
            relevant = sorted(action_id for action_id, item in action_review.items() if item.get("relevant") and item.get("availability_valid"))
            available = sorted(action_id for action_id, item in action_review.items() if item.get("availability_valid"))
            resolving = sorted(
                action_id for action_id, item in action_review.items()
                if item.get("resolves_need") and item.get("availability_valid")
            )
            cost_valid = sorted(action_id for action_id, item in action_review.items() if item.get("cost_valid"))
            risk_valid = sorted(action_id for action_id, item in action_review.items() if item.get("risk_valid"))
            flat.append({
                "case_key": row["case_key"], "reviewer_id": reviewer_id, "reviewer_model": model,
                "panel_provenance": "independent_model_panel", "need_type": str(response.get("need_type") or "unresolved"),
                "relevant_action_ids": relevant, "direct_answer_leak": bool(response.get("direct_answer_leak", True)),
                "available_action_ids": available,
                "resolving_action_ids": resolving, "cost_valid_action_ids": cost_valid,
                "risk_valid_action_ids": risk_valid,
                "action_audits": [
                    {
                        "action_id": action_id,
                        "availability_valid": bool(item.get("availability_valid")),
                        "cost_valid": bool(item.get("cost_valid")),
                        "risk_valid": bool(item.get("risk_valid")),
                        "relevant": bool(item.get("relevant")),
                        "resolves_need": bool(item.get("resolves_need")),
                        "information_gain": int(item.get("information_gain", 0)),
                        "wrong_episode_or_object_binding": bool(item.get("wrong_episode_or_object_binding")),
                        "unnecessary_high_risk_action": bool(item.get("unnecessary_high_risk_action")),
                    }
                    for action_id, item in sorted(action_review.items())
                ],
                "reviewed_action_ids": sorted(action_review), "expected_action_ids": sorted(str(action["action_id"]) for action in ann.get("actions") or []),
                "success": bool(row["success"]), "error": row["error"], "cache_key": row["cache_key"],
                "payload_sha256": row["payload_sha256"], "prompt_sha256": row["prompt_sha256"],
                "response_sha256": canonical_sha256(row["response"]),
            })
    return _finalize_panel(Path(out), "active_reviews", flat, [cases_path, annotations], reviewer_specs)


def run_active_predictions(
    *, freeze: Path, annotations: Path, out: Path, model: str, workers: int = 50,
    cache_only: bool = False, call_timeout: int = 240, max_retries: int = 2,
    client_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    cases, cases_path = _freeze_cases(freeze, "active")
    anns = _load_exact_annotations(annotations, {str(case["case_key"]) for case in cases})
    tasks: list[OnlineTask] = []
    for case in cases:
        ann = anns[case["case_key"]]
        actions = [
            {key: action[key] for key in ("action_id", "action_type", "action_name", "cost", "cost_band", "delay", "risk") if key in action}
            for action in ann.get("actions") or [] if action.get("status") == "performed"
        ]
        candidate_ids = {str(candidate["candidate_id"]) for candidate in case["policy_candidates"]}
        action_ids = {str(action["action_id"]) for action in actions}
        tasks.append(OnlineTask(
            f"{case['case_key']}|active_prediction", "CeilingActiveTypedPolicyCalibration", ACTIVE_POLICY_PROMPT,
            {"case_key": case["case_key"], "initial_vignette": ann["initial_text"], "candidates": case["policy_candidates"], "action_menu": actions},
            _policy_validator(candidate_ids, action_ids), {"case_key": case["case_key"], "stage": "active_prediction"},
        ))
    raw = _run_tasks(tasks, out_dir=Path(out) / "online", model=model, workers=workers,
                     cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                     client_factory=client_factory)
    predictions = [{
        "case_key": row["case_key"], "top_pair": list(row["response"].get("top_pair") or []),
        "need_type": str(row["response"].get("need_type") or "unresolved"),
        "action_id": str(row["response"].get("action_id") or ""),
        "expected_result_and_odds_shift": str(row["response"].get("expected_result_and_odds_shift") or ""),
        "abstain": bool(row["response"].get("abstain", True)), "success": bool(row["success"]),
        "error": row["error"], "provenance": "outcome_blind_model_policy_calibration",
    } for row in raw]
    return _finalize_product(Path(out), "active_predictions", predictions, [cases_path, annotations], model=model)


def _relation_decision(row: Mapping[str, Any]) -> str:
    if row.get("unresolved"):
        return "unresolved"
    return "accept" if all(bool(row.get(key)) for key in ("mapping_correct", "direction_correct", "citation_closed")) and not row.get("inverse_or_cycle") else "reject"


def run_relation_reviews(
    *, freeze: Path, out: Path, reviewer_specs: Sequence[tuple[str, str]], workers: int = 50,
    cache_only: bool = False, call_timeout: int = 240, max_retries: int = 2,
    client_factories: Mapping[str, Callable[[], Any]] | None = None,
) -> list[dict[str, Any]]:
    _assert_review_spec_tuples(reviewer_specs)
    cases, cases_path = _freeze_cases(freeze, "relation")
    flat: list[dict[str, Any]] = []
    for reviewer_id, model in reviewer_specs:
        tasks: list[OnlineTask] = []
        for case in cases:
            expected = {(str(edge["source_id"]), str(edge["target_id"])) for edge in case["relations"]}
            tasks.append(OnlineTask(
                f"{case['case_key']}|relation_review|{reviewer_id}", f"CeilingRelationModelPanel_{reviewer_id}", RELATION_REVIEW_PROMPT,
                {"case_key": case["case_key"], "vignette": case["vignette"], "candidates": case["candidates"], "nodes": case["nodes"], "relations": case["relations"]},
                _relation_review_validator(expected), {"case_key": case["case_key"], "reviewer_id": reviewer_id, "stage": "relation_model_panel"},
            ))
        raw = _run_tasks(tasks, out_dir=Path(out) / reviewer_id, model=model, workers=workers,
                         cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                         client_factory=(client_factories or {}).get(reviewer_id))
        by_case = {row["case_key"]: row for row in raw}
        for case in cases:
            result = by_case[case["case_key"]]
            reviewed = {(str(item["source_id"]), str(item["target_id"])): item for item in result["response"].get("edge_reviews", [])} if result["success"] else {}
            for edge in case["relations"]:
                key = (str(edge["source_id"]), str(edge["target_id"]))
                item = reviewed.get(key) or {"mapping_correct": False, "direction_correct": False, "citation_closed": False, "unresolved": True, "inverse_or_cycle": False}
                flat.append({
                    "case_key": case["case_key"], "source_id": key[0], "target_id": key[1],
                    "reviewer_id": reviewer_id, "reviewer_model": model, "panel_provenance": "independent_model_panel",
                    "mapping_correct": bool(item.get("mapping_correct")), "direction_correct": bool(item.get("direction_correct")),
                    "citation_closed": bool(item.get("citation_closed")), "unresolved": bool(item.get("unresolved", True)),
                    "inverse_or_cycle": bool(item.get("inverse_or_cycle")), "decision": _relation_decision(item),
                    "success": bool(result["success"]), "error": result["error"], "cache_key": result["cache_key"],
                    "payload_sha256": result["payload_sha256"], "prompt_sha256": result["prompt_sha256"],
                })
    return _finalize_panel(Path(out), "relation_reviews", flat, [cases_path], reviewer_specs)


def _validate_immutable_jobs(jobs: Sequence[Mapping[str, Any]]) -> list[OnlineTask]:
    tasks: list[OnlineTask] = []
    semantic_keys: set[tuple[str, str, str]] = set()
    for index, job in enumerate(jobs):
        prompt, payload = str(job.get("prompt") or ""), job.get("payload")
        if not prompt or not isinstance(payload, Mapping):
            raise AssertionError(f"job {index}: missing prompt/payload")
        if _sha_text(prompt) != str(job.get("prompt_sha256")) or canonical_sha256(payload) != str(job.get("payload_sha256")):
            raise AssertionError(f"job {index}: immutable hash mismatch")
        expected_job_sha = _immutable_job_sha256(job)
        declared_job_sha = str(job.get("job_sha256") or "")
        if declared_job_sha and declared_job_sha != expected_job_sha:
            raise AssertionError(f"job {index}: immutable job hash mismatch")
        if str(job.get("component") or "") == "factorization" and not declared_job_sha:
            raise AssertionError(f"job {index}: factorization job_sha256 missing")
        _assert_closure_blind(payload)
        # The frozen protocol forbids exposing internal arm identifiers.  A
        # compiler that embeds e.g. ``arm=qualified_frontier`` must be repaired
        # and re-frozen; the runner will never silently rewrite a hashed prompt.
        if re.search(r"\barm\s*=", prompt, flags=re.IGNORECASE):
            raise AssertionError(f"job {index}: internal arm name exposed in prompt")
        key = (str(job.get("case_key")), str(job.get("arm")), str(job.get("stage") or "selector"))
        if key in semantic_keys:
            raise AssertionError(f"job {index}: duplicate case/arm/stage")
        semantic_keys.add(key)
        stage = str(job.get("stage") or "selector")
        validator = (
            _policy_job_validator(payload)
            if stage == "policy"
            else _selector_validator(
                payload,
                require_modifier_hallucination=str(job.get("component") or "") == "factorization",
            )
        )
        task_id = "|".join(key)
        tasks.append(OnlineTask(
            task_id, f"CeilingSelector_{job.get('component')}_{stage}", prompt, dict(payload), validator,
            {
                "case_key": key[0], "arm": key[1], "stage": key[2],
                "component": str(job.get("component") or ""),
                "job_sha256": expected_job_sha,
            },
        ))
    return tasks


def run_selectors(
    *, jobs_path: Path, out: Path, model: str, workers: int = 50, cache_only: bool = False,
    call_timeout: int = 240, max_retries: int = 2, client_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    jobs = read_jsonl(jobs_path)
    tasks = _validate_immutable_jobs(jobs)
    raw = _run_tasks(tasks, out_dir=Path(out) / "online", model=model, workers=workers,
                     cache_only=cache_only, call_timeout=call_timeout, max_retries=max_retries,
                     client_factory=client_factory)
    responses = [{
        "case_key": row["case_key"], "family": next((str(job.get("family")) for job in jobs if str(job.get("case_key")) == row["case_key"] and str(job.get("arm")) == row["arm"] and str(job.get("stage") or "selector") == row["stage"]), ""),
        "component": row["component"], "arm": row["arm"], "stage": row["stage"],
        "success": bool(row["success"]), "error": row["error"], "response": row["response"],
        **({"champion_id": str(row["response"].get("champion_id") or "")} if row["stage"] != "policy" else {"action_id": str(row["response"].get("action_id") or "")}),
        "model": model, "cache_hit": row["cache_hit"], "cache_key": row["cache_key"],
        "prompt_sha256": row["prompt_sha256"], "payload_sha256": row["payload_sha256"],
        "job_sha256": row["job_sha256"],
    } for row in raw]
    return _finalize_product(Path(out), "selector_responses", responses, [jobs_path], model=model)


def _manifest_input(path: Path) -> dict[str, str]:
    resolved = Path(path).resolve()
    try:
        display = str(resolved.relative_to(ROOT))
    except ValueError:
        display = str(resolved)
    return {"path": display, "sha256": file_sha256(resolved)}


def _finalize_product(out: Path, product: str, rows: list[dict[str, Any]], inputs: Sequence[Path], *, model: str) -> list[dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    filename = {
        "admission_typing": "typing.jsonl",
        "factorization_annotations": "annotations.jsonl",
        "active_builder_annotations": "annotations.jsonl",
        "active_predictions": "predictions.jsonl",
        "selector_responses": "responses.jsonl",
    }[product]
    path = out / filename
    rows.sort(key=lambda row: (str(row.get("case_key")), str(row.get("arm")), str(row.get("stage"))))
    write_jsonl(path, rows)
    stage_manifests = sorted(out.glob("*/manifest.json"))
    atomic_json(out / f"{product}.manifest.json", {
        "schema": SCHEMA, "kind": "derived_product_manifest", "product": product,
        "source_commit": source_commit(), "generator_code_sha256": file_sha256(Path(__file__)),
        "model": model, "row_n": len(rows),
        "input_files": [_manifest_input(Path(value)) for value in inputs],
        "rows_sha256": canonical_sha256(rows), "file_sha256": file_sha256(path),
        "online_stage_manifests": [
            {"path": str(value.relative_to(out)), "sha256": file_sha256(value)}
            for value in stage_manifests
        ],
        "provenance": "outcome_blind_model_output", "created_at_utc": _utc_now(),
    })
    return rows


def _finalize_panel(out: Path, product: str, rows: list[dict[str, Any]], inputs: Sequence[Path], reviewer_specs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda row: (
        str(row.get("case_key")), str(row.get("review_kind") or ""),
        str(row.get("unit_id") or ""),
        str(row.get("left_id") or row.get("source_id") or ""),
        str(row.get("right_id") or row.get("target_id") or ""),
        str(row.get("modifier_axis") or ""), str(row.get("reviewer_id")),
    ))
    path = out / "reviews.jsonl"
    write_jsonl(path, rows)
    stage_manifests = sorted(out.glob("*/manifest.json"))
    manifest = {
        "schema": SCHEMA, "kind": "model_panel_manifest", "product": product,
        "source_commit": source_commit(), "generator_code_sha256": file_sha256(Path(__file__)),
        "panel_provenance": "two_independent_models_not_human_or_root",
        "reviewers": [{"reviewer_id": reviewer_id, "model": model} for reviewer_id, model in reviewer_specs],
        "row_n": len(rows), "input_files": [_manifest_input(Path(value)) for value in inputs],
        "rows_sha256": canonical_sha256(rows), "file_sha256": file_sha256(path), "created_at_utc": _utc_now(),
        "online_stage_manifests": [
            {"path": str(value.relative_to(out)), "sha256": file_sha256(value)}
            for value in stage_manifests
        ],
    }
    if product == "factorization_reviews":
        units = {
            str(row.get("unit_id")): str(row.get("unit_sha256"))
            for row in rows if row.get("unit_id")
        }
        manifest.update({
            "review_unit_n": len(units),
            "review_units_sha256": canonical_sha256([
                {"unit_id": unit_id, "unit_sha256": units[unit_id]}
                for unit_id in sorted(units)
            ]),
            "required_reviews_per_unit": 2,
        })
    atomic_json(out / f"{product}.manifest.json", manifest)
    return rows


def _add_online_options(parser: argparse.ArgumentParser, *, model: bool = True) -> None:
    if model:
        parser.add_argument("--model", required=True, help="exact provider/model identifier")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--cache-only", action="store_true", help="forbid uncached provider calls")
    parser.add_argument("--call-timeout", type=int, default=240)
    parser.add_argument("--max-retries", type=int, default=2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    admission = sub.add_parser("admission-typing", help="parse requested object and type every E4 candidate")
    _add_online_options(admission)
    admission.add_argument("--pools", type=Path, default=E4_POOLS)
    admission.add_argument("--joined", type=Path, default=E4_JOINED)
    factor = sub.add_parser("factorization-annotate", help="factorize, parse request and bind exact-offset modifiers")
    _add_online_options(factor)
    factor.add_argument("--freeze", type=Path, required=True)
    factor_review = sub.add_parser("factorization-review", help="run exactly two independent model-panel reviews")
    _add_online_options(factor_review, model=False)
    factor_review.add_argument("--freeze", type=Path, required=True)
    factor_review.add_argument("--annotations", type=Path, required=True)
    factor_review.add_argument("--reviewer", action="append", required=True, metavar="ID=MODEL")
    active_build = sub.add_parser("active-build", help="build exact-offset retrospective action banks")
    _add_online_options(active_build)
    active_build.add_argument("--freeze", type=Path, required=True)
    active_review = sub.add_parser("active-review", help="run exactly two independent model-panel action audits")
    _add_online_options(active_review, model=False)
    active_review.add_argument("--freeze", type=Path, required=True)
    active_review.add_argument("--annotations", type=Path, required=True)
    active_review.add_argument("--reviewer", action="append", required=True, metavar="ID=MODEL")
    active_predict = sub.add_parser("active-predict", help="run typed-policy calibration predictions")
    _add_online_options(active_predict)
    active_predict.add_argument("--freeze", type=Path, required=True)
    active_predict.add_argument("--annotations", type=Path, required=True)
    relation = sub.add_parser("relation-review", help="run exactly two independent model-panel edge reviews")
    _add_online_options(relation, model=False)
    relation.add_argument("--freeze", type=Path, required=True)
    relation.add_argument("--reviewer", action="append", required=True, metavar="ID=MODEL")
    selector = sub.add_parser("selector", help="execute hash-verified immutable selector/policy jobs")
    _add_online_options(selector)
    selector.add_argument("--jobs", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    options = _call_options(args)
    if args.command == "admission-typing":
        run_admission_typing(out=args.out, model=args.model, pools=args.pools, joined=args.joined, **options)
    elif args.command == "factorization-annotate":
        run_factorization_annotations(freeze=args.freeze, out=args.out, model=args.model, **options)
    elif args.command == "factorization-review":
        run_factorization_reviews(freeze=args.freeze, annotations=args.annotations, out=args.out, reviewer_specs=_review_specs(args.reviewer), **options)
    elif args.command == "active-build":
        run_active_builder(freeze=args.freeze, out=args.out, model=args.model, **options)
    elif args.command == "active-review":
        run_active_reviews(freeze=args.freeze, annotations=args.annotations, out=args.out, reviewer_specs=_review_specs(args.reviewer), **options)
    elif args.command == "active-predict":
        run_active_predictions(freeze=args.freeze, annotations=args.annotations, out=args.out, model=args.model, **options)
    elif args.command == "relation-review":
        run_relation_reviews(freeze=args.freeze, out=args.out, reviewer_specs=_review_specs(args.reviewer), **options)
    else:
        run_selectors(jobs_path=args.jobs, out=args.out, model=args.model, **options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
