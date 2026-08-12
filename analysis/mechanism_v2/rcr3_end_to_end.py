#!/usr/bin/env python3
"""RCR-3 end-to-end relation-preserving diagnosis experiment.

Three fresh, target-blind arms share the same 300-case E6 relation-challenge
sample, backbone, safe identity registry and completeness-first selector:

* ``lite3_safe``: two history-isolated full-vignette generators + selector;
* ``rcr3_default``: grounded relation skeleton + batched typed generator +
  selector;
* ``compact4_true3gen``: three history-isolated generators + selector.  The
  first two generator records are byte-identically reused from ``lite3_safe``
  so the fourth-call contrast does not silently resample its shared stages.

The official OpenAI SDK path remains owned by ``RobustLLMClient`` and selected
through ``TREE_DX_LLM_TRANSPORT``.  ``OnlineJSONCaller`` supplies immutable
cache, target-leak checks, schema validation and telemetry only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    combined_file_sha256,
    file_sha256,
    json_sha256,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.e12_e7_factorial import (  # noqa: E402
    BRIDGE_PATH,
    load_jobs as load_e12_jobs,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    assert_target_blind,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    RunManifest,
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


EXPERIMENT_ID = "RCR3"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/RCR3_relation_preserving"

LITE3 = "lite3_safe"
RCR3 = "rcr3_default"
COMPACT4 = "compact4_true3gen"
ARMS = (LITE3, RCR3, COMPACT4)
LOGICAL_CALLS = {LITE3: 3, RCR3: 3, COMPACT4: 4}

VIEW_SYNDROME = "syndrome_anatomy"
VIEW_ETIOLOGY = "etiology_temporal"
VIEW_EXCEPTION = "subtype_exception"
FLAT_VIEWS = (VIEW_SYNDROME, VIEW_ETIOLOGY, VIEW_EXCEPTION)

CANDIDATE_TYPES = frozenset(
    {
        "disease",
        "etiology",
        "manifestation",
        "subtype",
        "composite",
        "syndrome",
        "other",
    }
)
POLARITIES = frozenset({"present", "absent", "uncertain"})
EPISTEMIC = frozenset(
    {"observed", "reported", "provisional", "author_suspicion", "definitive"}
)
RELATIONS = frozenset(
    {
        "before",
        "after",
        "causes",
        "located_at",
        "has_result",
        "contradicts",
        "refines",
        "same_episode_as",
        "response_to",
        "associated_with",
    }
)

ENDPOINT_CONTRACT = (
    "clean vignette -> arm-specific grounded generation -> exact/frozen-safe-"
    "synonym global registry -> deterministic main/protected frontier -> shared "
    "time/scope-aware completeness-first selector -> pre-mapper strict and "
    "root-audited clinical endpoints"
)

SKELETON_PROMPT = r"""You build an auditable clinical relation/event skeleton.
The record is the only source of patient facts. Do not diagnose and do not use
outside facts. Copy every raw_span exactly from the record (shortest sufficient
substring, at most 180 characters). Keep observations separate from prior or
author diagnostic assertions. Preserve negation, subject, time, anatomy and
scope. Relations are claims: emit one only when the record supports it.

Infer what level of object the question requests without naming an answer:
disease, etiology, subtype, manifestation, syndrome, or a composite. List the
obligations a complete answer must satisfy (for example anatomy, cause, time,
subtype, or multiple components).

Return JSON only:
{
  "observations": [
    {"fact_id":"F01","kind":"demographic|symptom|sign|history|laboratory|imaging|pathology|microbiology|genetics|treatment|other",
     "raw_span":"exact quote","normalized_fact":"brief literal normalization",
     "polarity":"present|absent|uncertain","subject":"patient|family|other",
     "time_anchor":"brief literal time or unknown","scope":"anatomic/object scope or whole_patient",
     "epistemic_status":"observed|reported|provisional|author_suspicion|definitive"}
  ],
  "relations": [
    {"source_fact_id":"F01","relation":"before|after|causes|located_at|has_result|contradicts|refines|same_episode_as|response_to|associated_with",
     "target_fact_id":"F02","justification_span":"exact quote"}
  ],
  "diagnostic_assertions": [
    {"raw_span":"exact quote","status":"provisional|author_suspicion|definitive"}
  ],
  "requested_object": {"kind":"disease|etiology|subtype|manifestation|syndrome|composite|other",
                       "obligations":["short non-answer obligation"]}
}
Keep 8-24 observations and no more than 32 relations.
"""

BATCHED_GENERATOR_PROMPT = r"""You are the typed candidate-generation call in
a relation-preserving diagnostic system. Read both the full record and the
grounded relation skeleton; the record remains source of truth. Generate three
history-isolated views inside one response. Each view must add candidates from
its assigned angle, not echo a single common list:

1. syndrome_anatomy: syndrome pattern and precise anatomic/object localization;
2. etiology_temporal: cause, exposure, chronology, response and mechanism;
3. subtype_exception: defining pathology/imaging/genetic subtype, composite
   obligations, uncommon but strongly supported exceptions.

Generate 2-5 concrete candidates per view. A manifestation is not a disease
unless the question requests it. Candidate evidence must reference skeleton
fact IDs. ``unique_evidence_fact_ids`` must distinguish that candidate from a
near competitor, not merely be compatible with every candidate. Keep broad
and narrow entities separate; never claim they are synonyms. Do not rank across
views and do not use answer options.

Return JSON only:
{"views":[
  {"view":"syndrome_anatomy|etiology_temporal|subtype_exception",
   "candidates":[
     {"label":"concrete diagnosis","candidate_type":"disease|etiology|manifestation|subtype|composite|syndrome|other",
      "support_fact_ids":["F01"],"counter_fact_ids":[],
      "unique_evidence_fact_ids":["F01"],
      "satisfies_obligations":["obligation text"],
      "missing_obligations":[],"rare_or_low_prior":false,
      "protected_reason":"empty unless low-prior candidate has unique case evidence"}
   ]}
]}
"""

FLAT_GENERATOR_PROMPTS: dict[str, str] = {
    VIEW_SYNDROME: r"""You are an independent syndrome/anatomy diagnostic
generator. Read the complete record. You cannot see any other generator.
Propose 3-5 concrete diagnoses covering the syndrome and exact anatomic/object
localization. Do not substitute a manifestation for an underlying disease
unless the question asks for the manifestation. Copy support/counter spans
exactly from the record, at most 180 characters. Do not rank against unseen
generators or use answer options.
Return JSON only:
{"view":"syndrome_anatomy","requested_object":{"kind":"disease|etiology|subtype|manifestation|syndrome|composite|other","obligations":["short obligation"]},
 "candidates":[{"label":"diagnosis","candidate_type":"disease|etiology|manifestation|subtype|composite|syndrome|other",
 "support_spans":["exact quote"],"counter_spans":[],"unique_evidence_spans":["exact quote"],
 "satisfies_obligations":[],"missing_obligations":[],"rare_or_low_prior":false,"protected_reason":""}]}
""",
    VIEW_ETIOLOGY: r"""You are an independent counter-anchor
etiology/temporal diagnostic generator. Read the complete record. You cannot
see any other generator. Challenge the obvious provisional or manifestation
answer by tracing cause, exposure, chronology, recurrence and treatment
response. Propose 3-5 concrete diagnoses. Copy support/counter spans exactly
from the record, at most 180 characters. Do not use answer options.
Return JSON only:
{"view":"etiology_temporal","requested_object":{"kind":"disease|etiology|subtype|manifestation|syndrome|composite|other","obligations":["short obligation"]},
 "candidates":[{"label":"diagnosis","candidate_type":"disease|etiology|manifestation|subtype|composite|syndrome|other",
 "support_spans":["exact quote"],"counter_spans":[],"unique_evidence_spans":["exact quote"],
 "satisfies_obligations":[],"missing_obligations":[],"rare_or_low_prior":false,"protected_reason":""}]}
""",
    VIEW_EXCEPTION: r"""You are an independent subtype/exception diagnostic
generator. Read the complete record. You cannot see any other generator.
Prioritize defining pathology, imaging, microbiology, genetics, composite
scope and rare low-prior entities supported by high-specificity evidence.
Propose 3-5 concrete diagnoses and retain broad/narrow entities separately.
Copy support/counter spans exactly from the record, at most 180 characters.
Do not use answer options.
Return JSON only:
{"view":"subtype_exception","requested_object":{"kind":"disease|etiology|subtype|manifestation|syndrome|composite|other","obligations":["short obligation"]},
 "candidates":[{"label":"diagnosis","candidate_type":"disease|etiology|manifestation|subtype|composite|syndrome|other",
 "support_spans":["exact quote"],"counter_spans":[],"unique_evidence_spans":["exact quote"],
 "satisfies_obligations":[],"missing_obligations":[],"rare_or_low_prior":true,"protected_reason":"brief unique case evidence or empty"}]}
""",
}

SELECTOR_PROMPT = r"""You are a completeness-first, time/scope-aware
contrastive diagnostic selector. Candidate IDs are opaque. Use the full record
as source of truth and the supplied grounded evidence as an index. You may not
add, merge, rename or delete candidates.

For every candidate, distinguish: complete requested diagnosis; partial/broad
family or isolated component; manifestation instead of cause; wrong anatomy,
subject, time, subtype or composite scope; or contradicted. Candidate count,
generator agreement and order are not evidence. Compare the two strongest
candidates directly using candidate-unique evidence and each one's strongest
counterexample. A rare candidate with unique high-specificity evidence must be
considered, but rarity alone gives no bonus. Missing tests are unknown, not
negative. Prefer the most specific candidate only when the record supports its
extra obligations.

Return JSON only:
{"candidate_assessments":[
  {"candidate_id":"C001","fit":"strong|plausible|weak|contradicted",
   "completeness":"complete|partial|manifestation|wrong_scope|unsupported",
   "temporal_scope_fit":"fits|conflicts|unknown",
   "support_fact_ids":[],"strongest_counter_fact_ids":[],
   "missing_obligations":["brief obligation"]}
 ],
 "decisive_pair":{"left_id":"C001","right_id":"C002","winner_id":"C001",
                  "contrast":"brief falsifiable contrast","source_fact_ids":[]},
 "counterexample_checked":"strongest way the runner-up could instead win",
 "champion_id":"C001","runner_up_id":"C002","margin":"high|medium|low",
 "rationale":"brief evidence- and completeness-grounded reason"}
"""


def _space(value: str) -> str:
    return " ".join(str(value or "").split())


def _grounded_span(span: str, vignette: str) -> bool:
    quote = _space(span)
    return bool(quote and len(quote) <= 180 and quote.casefold() in _space(vignette).casefold())


def _short_strings(value: Any, *, limit: int = 16, width: int = 180) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = _space(str(item or ""))[:width]
        if text and text not in output:
            output.append(text)
        if len(output) >= limit:
            break
    return output


def _candidate_type(value: Any) -> str:
    kind = str(value or "other").strip().lower()
    return kind if kind in CANDIDATE_TYPES else "other"


def validate_skeleton(response: Mapping[str, Any]) -> str | None:
    observations = response.get("observations")
    if not isinstance(observations, list) or not 4 <= len(observations) <= 40:
        return "observations must contain 4..40 rows"
    ids: list[str] = []
    for row in observations:
        if not isinstance(row, Mapping):
            return "observation row must be an object"
        fact_id = str(row.get("fact_id") or "").strip()
        if not re.fullmatch(r"F\d{1,3}", fact_id):
            return f"invalid fact_id {fact_id!r}"
        ids.append(fact_id)
        if str(row.get("polarity") or "").lower() not in POLARITIES:
            return "invalid observation polarity"
        if str(row.get("epistemic_status") or "").lower() not in EPISTEMIC:
            return "invalid observation epistemic_status"
        if not str(row.get("raw_span") or "").strip():
            return "observation raw_span is required"
    if len(ids) != len(set(ids)):
        return "fact_ids must be unique"
    relations = response.get("relations")
    if not isinstance(relations, list) or len(relations) > 48:
        return "relations must be a list of at most 48 rows"
    for row in relations:
        if not isinstance(row, Mapping):
            return "relation row must be an object"
        if str(row.get("relation") or "") not in RELATIONS:
            return "invalid relation type"
    requested = response.get("requested_object")
    if not isinstance(requested, Mapping):
        return "requested_object is required"
    if str(requested.get("kind") or "other").lower() not in {
        "disease", "etiology", "subtype", "manifestation", "syndrome", "composite", "other"
    }:
        return "invalid requested_object kind"
    if not isinstance(requested.get("obligations"), list):
        return "requested_object obligations must be a list"
    return None


def sanitize_skeleton(response: Mapping[str, Any], vignette: str) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    dropped_spans: list[dict[str, str]] = []
    for raw in response.get("observations") or []:
        fact_id = str(raw.get("fact_id") or "").strip()
        span = _space(str(raw.get("raw_span") or ""))
        if not _grounded_span(span, vignette):
            dropped_spans.append({"fact_id": fact_id, "raw_span": span})
            continue
        facts.append(
            {
                "fact_id": fact_id,
                "kind": _space(str(raw.get("kind") or "other"))[:40],
                "raw_span": span,
                "normalized_fact": _space(str(raw.get("normalized_fact") or span))[:260],
                "polarity": str(raw.get("polarity") or "uncertain").lower(),
                "subject": _space(str(raw.get("subject") or "patient"))[:80],
                "time_anchor": _space(str(raw.get("time_anchor") or "unknown"))[:120],
                "scope": _space(str(raw.get("scope") or "whole_patient"))[:120],
                "epistemic_status": str(raw.get("epistemic_status") or "observed").lower(),
            }
        )
    valid_ids = {row["fact_id"] for row in facts}
    relations: list[dict[str, Any]] = []
    for raw in response.get("relations") or []:
        source = str(raw.get("source_fact_id") or "")
        target = str(raw.get("target_fact_id") or "")
        relation = str(raw.get("relation") or "")
        span = _space(str(raw.get("justification_span") or ""))
        if source not in valid_ids or target not in valid_ids or relation not in RELATIONS:
            continue
        if span and not _grounded_span(span, vignette):
            continue
        relations.append(
            {
                "source_fact_id": source,
                "relation": relation,
                "target_fact_id": target,
                "justification_span": span,
            }
        )
    assertions: list[dict[str, str]] = []
    for raw in response.get("diagnostic_assertions") or []:
        if not isinstance(raw, Mapping):
            continue
        span = _space(str(raw.get("raw_span") or ""))
        status = str(raw.get("status") or "provisional").lower()
        if _grounded_span(span, vignette) and status in {
            "provisional", "author_suspicion", "definitive"
        }:
            assertions.append({"raw_span": span, "status": status})
    requested = dict(response.get("requested_object") or {})
    return {
        "observations": facts,
        "relations": relations,
        "diagnostic_assertions": assertions,
        "requested_object": {
            "kind": str(requested.get("kind") or "other").lower(),
            "obligations": _short_strings(requested.get("obligations"), limit=8, width=120),
        },
        "grounding_audit": {
            "raw_observation_n": len(response.get("observations") or []),
            "grounded_observation_n": len(facts),
            "dropped_observation_n": len(dropped_spans),
            "dropped_observations": dropped_spans,
            "grounded_relation_n": len(relations),
        },
    }


def validate_batched_generator(response: Mapping[str, Any]) -> str | None:
    views = response.get("views")
    if not isinstance(views, list) or len(views) != 3:
        return "views must contain exactly three rows"
    names = [str(row.get("view") or "") for row in views if isinstance(row, Mapping)]
    if set(names) != set(FLAT_VIEWS) or len(names) != 3:
        return "views must cover the three frozen view names exactly once"
    for view in views:
        candidates = view.get("candidates") if isinstance(view, Mapping) else None
        if not isinstance(candidates, list) or not 2 <= len(candidates) <= 6:
            return "each view must contain 2..6 candidates"
        for row in candidates:
            if not isinstance(row, Mapping) or not str(row.get("label") or "").strip():
                return "every candidate requires a label"
            if _candidate_type(row.get("candidate_type")) != str(
                row.get("candidate_type") or "other"
            ).strip().lower():
                return "invalid candidate_type"
            for key in ("support_fact_ids", "counter_fact_ids", "unique_evidence_fact_ids"):
                if not isinstance(row.get(key), list):
                    return f"{key} must be a list"
    return None


def validate_flat_generator(response: Mapping[str, Any], view: str) -> str | None:
    if str(response.get("view") or "") != view:
        return f"view must be {view}"
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= 6:
        return "candidates must contain 2..6 rows"
    for row in candidates:
        if not isinstance(row, Mapping) or not str(row.get("label") or "").strip():
            return "every candidate requires a label"
        if str(row.get("candidate_type") or "").lower() not in CANDIDATE_TYPES:
            return "invalid candidate_type"
        for key in ("support_spans", "counter_spans", "unique_evidence_spans"):
            if not isinstance(row.get(key), list):
                return f"{key} must be a list"
    requested = response.get("requested_object")
    if requested is not None and not isinstance(requested, Mapping):
        return "requested_object must be an object"
    return None


def validate_selector(response: Mapping[str, Any], candidate_ids: set[str]) -> str | None:
    if len(candidate_ids) < 2:
        return "selector requires at least two candidates"
    champion = str(response.get("champion_id") or "")
    runner = str(response.get("runner_up_id") or "")
    if champion not in candidate_ids:
        return "invalid champion_id"
    if runner not in candidate_ids or runner == champion:
        return "invalid runner_up_id"
    if str(response.get("margin") or "").lower() not in {"high", "medium", "low"}:
        return "margin must be high|medium|low"
    assessments = response.get("candidate_assessments")
    if not isinstance(assessments, list):
        return "candidate_assessments must be a list"
    seen = [
        str(row.get("candidate_id") or "")
        for row in assessments
        if isinstance(row, Mapping)
    ]
    if len(seen) != len(candidate_ids) or set(seen) != candidate_ids:
        return "candidate_assessments must cover each candidate exactly once"
    for row in assessments:
        if str(row.get("fit") or "") not in {"strong", "plausible", "weak", "contradicted"}:
            return "invalid assessment fit"
        if str(row.get("completeness") or "") not in {
            "complete", "partial", "manifestation", "wrong_scope", "unsupported"
        }:
            return "invalid assessment completeness"
        if str(row.get("temporal_scope_fit") or "") not in {"fits", "conflicts", "unknown"}:
            return "invalid temporal_scope_fit"
    pair = response.get("decisive_pair")
    if not isinstance(pair, Mapping):
        return "decisive_pair is required"
    left = str(pair.get("left_id") or "")
    right = str(pair.get("right_id") or "")
    winner = str(pair.get("winner_id") or "")
    if left not in candidate_ids or right not in candidate_ids or left == right:
        return "invalid decisive_pair candidates"
    if winner not in {left, right}:
        return "decisive_pair winner must be one member"
    return None


def load_jobs() -> tuple[list[dict[str, Any]], list[Path]]:
    rows, paths = load_e12_jobs(FrozenExactSynonymBridge(BRIDGE_PATH))
    jobs = [
        {
            "case_key": str(row["case_key"]),
            "slice_id": str(row["slice_id"]),
            "family": str(row["family"]),
            "source_id": str(row["source_id"]),
            "vignette": str(row["representations"]["raw"]["content"]),
            "gold": str(row["gold"]),
        }
        for row in rows
    ]
    if len(jobs) != 300 or Counter(job["family"] for job in jobs) != {"DA": 150, "MCR": 150}:
        raise AssertionError("RCR3 requires the frozen E12 DA150+MCR150 sample")
    return jobs, paths


def _evidence_id(case_key: str, span: str) -> str:
    return f"E{stable_seed('RCR3-evidence-v1', case_key, _space(span)) % 10**8:08d}"


def sanitize_flat_generator(
    response: Mapping[str, Any], vignette: str, case_key: str
) -> dict[str, Any]:
    evidence: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    invalid_spans: list[str] = []

    def admit(span: Any, role: str) -> str:
        text = _space(str(span or ""))
        if not _grounded_span(text, vignette):
            if text and text not in invalid_spans:
                invalid_spans.append(text)
            return ""
        eid = _evidence_id(case_key, text)
        evidence.setdefault(
            eid,
            {
                "fact_id": eid,
                "raw_span": text,
                "kind": "raw_span",
                "polarity": "present",
                "subject": "patient",
                "time_anchor": "from_record",
                "scope": "from_record",
                "epistemic_status": "observed",
                "source_role": role,
            },
        )
        return eid

    view = str(response.get("view") or "")
    for raw in response.get("candidates") or []:
        support = [admit(span, "support") for span in raw.get("support_spans") or []]
        counter = [admit(span, "counter") for span in raw.get("counter_spans") or []]
        unique = [admit(span, "unique") for span in raw.get("unique_evidence_spans") or []]
        candidates.append(
            {
                "label": _space(str(raw.get("label") or ""))[:220],
                "candidate_type": _candidate_type(raw.get("candidate_type")),
                "support_fact_ids": sorted({value for value in support if value}),
                "counter_fact_ids": sorted({value for value in counter if value}),
                "unique_evidence_fact_ids": sorted({value for value in unique if value}),
                "satisfies_obligations": _short_strings(raw.get("satisfies_obligations"), limit=8, width=120),
                "missing_obligations": _short_strings(raw.get("missing_obligations"), limit=8, width=120),
                "rare_or_low_prior": bool(raw.get("rare_or_low_prior")),
                "protected_reason": _space(str(raw.get("protected_reason") or ""))[:260],
                "view": view,
            }
        )
    requested = dict(response.get("requested_object") or {})
    return {
        "view": view,
        "evidence": sorted(evidence.values(), key=lambda row: row["fact_id"]),
        "candidates": candidates,
        "requested_object": {
            "kind": str(requested.get("kind") or "disease").lower(),
            "obligations": _short_strings(requested.get("obligations"), limit=8, width=120),
        },
        "grounding_audit": {
            "invalid_span_n": len(invalid_spans),
            "invalid_spans": invalid_spans,
            "grounded_evidence_n": len(evidence),
        },
    }


def sanitize_batched_generator(
    response: Mapping[str, Any], skeleton: Mapping[str, Any]
) -> dict[str, Any]:
    valid_ids = {str(row["fact_id"]) for row in skeleton["observations"]}
    views: list[dict[str, Any]] = []
    invalid_refs: list[dict[str, Any]] = []
    for raw_view in response.get("views") or []:
        view = str(raw_view.get("view") or "")
        candidates: list[dict[str, Any]] = []
        for raw in raw_view.get("candidates") or []:
            def refs(key: str) -> list[str]:
                values = [str(value) for value in raw.get(key) or []]
                invalid = sorted(set(values) - valid_ids)
                if invalid:
                    invalid_refs.append({"view": view, "label": raw.get("label"), "field": key, "ids": invalid})
                return sorted(set(values) & valid_ids)

            candidates.append(
                {
                    "label": _space(str(raw.get("label") or ""))[:220],
                    "candidate_type": _candidate_type(raw.get("candidate_type")),
                    "support_fact_ids": refs("support_fact_ids"),
                    "counter_fact_ids": refs("counter_fact_ids"),
                    "unique_evidence_fact_ids": refs("unique_evidence_fact_ids"),
                    "satisfies_obligations": _short_strings(raw.get("satisfies_obligations"), limit=8, width=120),
                    "missing_obligations": _short_strings(raw.get("missing_obligations"), limit=8, width=120),
                    "rare_or_low_prior": bool(raw.get("rare_or_low_prior")),
                    "protected_reason": _space(str(raw.get("protected_reason") or ""))[:260],
                    "view": view,
                }
            )
        views.append({"view": view, "candidates": candidates})
    return {
        "views": views,
        "invalid_reference_audit": {
            "invalid_reference_n": sum(len(row["ids"]) for row in invalid_refs),
            "rows": invalid_refs,
        },
    }


def _generic_requested_object() -> dict[str, Any]:
    return {
        "kind": "disease",
        "obligations": [
            "answer the object requested by the case",
            "preserve supported anatomy, etiology, time, subtype and composite scope",
        ],
    }


def build_registry(
    *,
    case_key: str,
    bridge: FrozenExactSynonymBridge,
    evidence_rows: Iterable[Mapping[str, Any]],
    candidate_rows: Iterable[Mapping[str, Any]],
    requested_object: Mapping[str, Any] | None,
) -> dict[str, Any]:
    evidence = {
        str(row["fact_id"]): dict(row)
        for row in evidence_rows
        if str(row.get("fact_id") or "")
    }
    grouped: dict[str, dict[str, Any]] = {}
    for raw in candidate_rows:
        label = _space(str(raw.get("label") or ""))[:220]
        key = bridge.canonical_key(label)
        if not key:
            continue
        row = grouped.setdefault(
            key,
            {
                "concept_key": key,
                "surface_labels": [],
                "candidate_types": [],
                "generator_views": [],
                "support_fact_ids": [],
                "counter_fact_ids": [],
                "unique_evidence_fact_ids": [],
                "satisfies_obligations": [],
                "missing_obligations": [],
                "rare_or_low_prior": False,
                "protected_reasons": [],
            },
        )
        for field, values in (
            ("surface_labels", [label]),
            ("candidate_types", [_candidate_type(raw.get("candidate_type"))]),
            ("generator_views", [str(raw.get("view") or "unknown")]),
            ("support_fact_ids", raw.get("support_fact_ids") or []),
            ("counter_fact_ids", raw.get("counter_fact_ids") or []),
            ("unique_evidence_fact_ids", raw.get("unique_evidence_fact_ids") or []),
            ("satisfies_obligations", raw.get("satisfies_obligations") or []),
            ("missing_obligations", raw.get("missing_obligations") or []),
            ("protected_reasons", [raw.get("protected_reason") or ""]),
        ):
            for value in values:
                text = str(value).strip()
                if text and text not in row[field]:
                    row[field].append(text)
        row["rare_or_low_prior"] = bool(row["rare_or_low_prior"] or raw.get("rare_or_low_prior"))

    id_order = sorted(
        grouped,
        key=lambda key: (stable_seed("RCR3-neutral-id-v1", case_key, key), key),
    )
    registry: list[dict[str, Any]] = []
    for index, key in enumerate(id_order, 1):
        row = grouped[key]
        labels = sorted(
            row["surface_labels"],
            key=lambda value: (-len(normalize_label(value)), normalize_label(value)),
        )
        row["candidate_id"] = f"C{index:03d}"
        row["label"] = labels[0]
        for field in (
            "support_fact_ids", "counter_fact_ids", "unique_evidence_fact_ids"
        ):
            row[field] = sorted(set(row[field]) & set(evidence))
        row["registry_priority_score"] = round(
            2.0 * len(row["support_fact_ids"])
            + 2.5 * len(row["unique_evidence_fact_ids"])
            + 0.5 * len(row["satisfies_obligations"])
            + 0.25 * max(0, len(row["generator_views"]) - 1)
            - 1.25 * len(row["counter_fact_ids"])
            - 0.5 * len(row["missing_obligations"]),
            3,
        )
        registry.append(row)

    ranked = sorted(
        registry,
        key=lambda row: (
            -float(row["registry_priority_score"]),
            stable_seed("RCR3-frontier-tie-v1", case_key, row["concept_key"]),
        ),
    )
    main = ranked[:6]
    main_ids = {row["candidate_id"] for row in main}
    protected = [
        row
        for row in ranked[6:]
        if row["candidate_id"] not in main_ids
        and row["support_fact_ids"]
        and (
            row["unique_evidence_fact_ids"]
            or row["rare_or_low_prior"]
            or row["protected_reasons"]
        )
    ][:2]
    frontier = main + protected
    if len(frontier) < min(8, len(ranked)):
        used = {row["candidate_id"] for row in frontier}
        frontier.extend(
            row for row in ranked if row["candidate_id"] not in used
        )
        frontier = frontier[: min(8, len(ranked))]
    frontier_ids = {row["candidate_id"] for row in frontier}
    payload_candidates = []
    for row in sorted(frontier, key=lambda value: value["candidate_id"]):
        payload_candidates.append(
            {
                "candidate_id": row["candidate_id"],
                "label": row["label"],
                "candidate_types": row["candidate_types"],
                "supporting_evidence": [evidence[eid] for eid in row["support_fact_ids"]],
                "counter_evidence": [evidence[eid] for eid in row["counter_fact_ids"]],
                "unique_evidence": [evidence[eid] for eid in row["unique_evidence_fact_ids"]],
                "satisfies_obligations": row["satisfies_obligations"],
                "missing_obligations": row["missing_obligations"],
            }
        )
    requested = dict(requested_object or _generic_requested_object())
    return {
        "evidence": sorted(evidence.values(), key=lambda row: row["fact_id"]),
        "registry": registry,
        "frontier_candidate_ids": sorted(frontier_ids),
        "archived_candidate_ids": sorted(
            row["candidate_id"] for row in registry if row["candidate_id"] not in frontier_ids
        ),
        "payload_candidates": payload_candidates,
        "requested_object": {
            "kind": str(requested.get("kind") or "disease")[:40],
            "obligations": _short_strings(requested.get("obligations"), limit=10, width=140),
        },
        "registry_sha256": canonical_sha256(registry),
        "frontier_sha256": canonical_sha256(payload_candidates),
    }


def _flat_registry(
    job: Mapping[str, Any], generator_docs: Sequence[Mapping[str, Any]], bridge: FrozenExactSynonymBridge
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    obligations: list[str] = []
    kinds: list[str] = []
    for doc in generator_docs:
        evidence.extend(dict(row) for row in doc["evidence"])
        candidates.extend(dict(row) for row in doc["candidates"])
        requested = dict(doc.get("requested_object") or {})
        kinds.append(str(requested.get("kind") or "disease"))
        for obligation in requested.get("obligations") or []:
            if obligation not in obligations:
                obligations.append(str(obligation))
    requested = {
        "kind": Counter(kinds).most_common(1)[0][0] if kinds else "disease",
        "obligations": obligations or _generic_requested_object()["obligations"],
    }
    return build_registry(
        case_key=str(job["case_key"]),
        bridge=bridge,
        evidence_rows=evidence,
        candidate_rows=candidates,
        requested_object=requested,
    )


def _rcr_registry(
    job: Mapping[str, Any], skeleton: Mapping[str, Any], generator: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
) -> dict[str, Any]:
    candidates = [
        dict(candidate)
        for view in generator["views"]
        for candidate in view["candidates"]
    ]
    return build_registry(
        case_key=str(job["case_key"]),
        bridge=bridge,
        evidence_rows=skeleton["observations"],
        candidate_rows=candidates,
        requested_object=skeleton["requested_object"],
    )


def selector_payload(
    job: Mapping[str, Any], registry: Mapping[str, Any], relation_context: Mapping[str, Any] | None
) -> dict[str, Any]:
    payload = {
        "case_id": str(job["case_key"]),
        "clinical_record": str(job["vignette"]),
        "requested_object": dict(registry["requested_object"]),
        "relation_context": dict(relation_context or {"kind": "grounded_span_ledger", "relations": []}),
        "candidates": list(registry["payload_candidates"]),
    }
    assert_target_blind(payload)
    return payload


def _stage_outcome(outcome: Any, sanitized: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": bool(outcome.success),
        "error": str(outcome.error),
        "cache_hit": bool(outcome.cache_hit),
        "cache_key": str(outcome.cache_key),
        "prompt_sha256": str(outcome.prompt_sha256),
        "payload_sha256": str(outcome.payload_sha256),
        "response": dict(outcome.response),
        "sanitized": dict(sanitized or {}),
    }


def _equivalent(label: str, gold: str, bridge: FrozenExactSynonymBridge) -> bool:
    return bool(label and gold and bridge.equivalent(label, gold))


def _result_from_stage(
    job: Mapping[str, Any], arm: str, stage: Mapping[str, Any], bridge: FrozenExactSynonymBridge
) -> dict[str, Any]:
    registry = dict(stage.get("registry") or {})
    selector = dict(stage.get("selector") or {})
    success = bool(stage.get("success"))
    response = dict(selector.get("response") or {}) if success else {}
    by_id = {
        str(row["candidate_id"]): row
        for row in registry.get("registry") or []
    }
    champion_id = str(response.get("champion_id") or "") if success else ""
    runner_id = str(response.get("runner_up_id") or "") if success else ""
    champion_label = str((by_id.get(champion_id) or {}).get("label") or "")
    runner_label = str((by_id.get(runner_id) or {}).get("label") or "")
    gold = str(job["gold"])
    all_registry = list(registry.get("registry") or [])
    frontier_ids = set(registry.get("frontier_candidate_ids") or [])
    return {
        "case_key": job["case_key"],
        "slice_id": job["slice_id"],
        "family": job["family"],
        "source_id": job["source_id"],
        "arm": arm,
        "logical_llm_calls": LOGICAL_CALLS[arm],
        "reused_generator_calls": 2 if arm == COMPACT4 else 0,
        "success": success,
        "error": str(stage.get("error") or ""),
        "gold": gold,
        "registry_n": len(all_registry),
        "frontier_n": len(frontier_ids),
        "registry_sha256": str(registry.get("registry_sha256") or ""),
        "frontier_sha256": str(registry.get("frontier_sha256") or ""),
        "raw_registry_exposure_hit": any(
            _equivalent(str(row.get("label") or ""), gold, bridge) for row in all_registry
        ),
        "frontier_exposure_hit": any(
            row.get("candidate_id") in frontier_ids
            and _equivalent(str(row.get("label") or ""), gold, bridge)
            for row in all_registry
        ),
        "champion_id": champion_id,
        "champion_label": champion_label,
        "runner_up_id": runner_id,
        "runner_up_label": runner_label,
        "strict_top1": _equivalent(champion_label, gold, bridge),
        "strict_top2": _equivalent(champion_label, gold, bridge)
        or _equivalent(runner_label, gold, bridge),
        "selector_response": response,
    }


def _case_stage_path(arm_dir: Path, job: Mapping[str, Any]) -> Path:
    return arm_dir / "case_stages" / f"{job['slice_id']}__{job['source_id']}.json"


def _caller(arm_dir: Path, stage: str, model: str) -> OnlineJSONCaller:
    return OnlineJSONCaller(
        out_dir=arm_dir / "calls" / stage,
        model=model,
        telemetry_path=arm_dir / "telemetry" / f"{stage}.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=2,
    )


def _run_flat_case(
    *,
    job: Mapping[str, Any],
    arm: str,
    arm_dir: Path,
    model: str,
    bridge: FrozenExactSynonymBridge,
    callers: Mapping[str, OnlineJSONCaller],
    lite_stage_dir: Path | None = None,
) -> dict[str, Any]:
    path = _case_stage_path(arm_dir, job)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    generator_stages: list[dict[str, Any]] = []
    views = FLAT_VIEWS[:2] if arm == LITE3 else FLAT_VIEWS
    if arm == COMPACT4:
        if lite_stage_dir is None:
            raise AssertionError("compact4 requires frozen lite3 stage directory")
        lite_path = lite_stage_dir / path.name
        if not lite_path.is_file():
            raise FileNotFoundError(f"compact4 shared lite3 stage missing: {lite_path}")
        lite = json.loads(lite_path.read_text(encoding="utf-8"))
        prior = list(lite.get("generators") or [])
        if len(prior) != 2 or [row.get("view") for row in prior] != list(FLAT_VIEWS[:2]):
            raise AssertionError("compact4 shared generator contract mismatch")
        generator_stages.extend(prior)

    for view in views:
        if arm == COMPACT4 and view in FLAT_VIEWS[:2]:
            continue
        payload = {
            "case_id": str(job["case_key"]),
            "clinical_record": str(job["vignette"]),
        }
        outcome = callers[view].call(
            module=f"RCR3_flat_{view}",
            prompt=FLAT_GENERATOR_PROMPTS[view],
            payload=payload,
            validator=lambda response, selected=view: validate_flat_generator(response, selected),
        )
        sanitized = (
            sanitize_flat_generator(outcome.response, str(job["vignette"]), str(job["case_key"]))
            if outcome.success
            else {}
        )
        generator_stages.append({"view": view, **_stage_outcome(outcome, sanitized)})

    failed = [row for row in generator_stages if not bool(row.get("success"))]
    if failed:
        document = {
            "case_key": job["case_key"],
            "arm": arm,
            "success": False,
            "error": "; ".join(str(row.get("error") or "generator failure") for row in failed),
            "generators": generator_stages,
            "registry": {},
            "selector": {},
        }
        atomic_json(path, document)
        return document
    sanitized_docs = [dict(row["sanitized"]) for row in generator_stages]
    registry = _flat_registry(job, sanitized_docs, bridge)
    if len(registry["payload_candidates"]) < 2:
        document = {
            "case_key": job["case_key"], "arm": arm, "success": False,
            "error": "fewer than two safe frontier candidates",
            "generators": generator_stages, "registry": registry, "selector": {},
        }
        atomic_json(path, document)
        return document
    payload = selector_payload(job, registry, None)
    ids = {str(row["candidate_id"]) for row in registry["payload_candidates"]}
    selected = callers["selector"].call(
        module="RCR3_completeness_pairwise_selector",
        prompt=SELECTOR_PROMPT,
        payload=payload,
        validator=lambda response: validate_selector(response, ids),
    )
    selector = _stage_outcome(selected)
    document = {
        "case_key": job["case_key"],
        "arm": arm,
        "success": selected.success,
        "error": selected.error,
        "generators": generator_stages,
        "registry": registry,
        "selector": selector,
    }
    atomic_json(path, document)
    return document


def _run_rcr_case(
    *, job: Mapping[str, Any], arm_dir: Path, bridge: FrozenExactSynonymBridge,
    callers: Mapping[str, OnlineJSONCaller],
) -> dict[str, Any]:
    path = _case_stage_path(arm_dir, job)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    skeleton_payload = {
        "case_id": str(job["case_key"]),
        "clinical_record": str(job["vignette"]),
    }
    skeleton_out = callers["skeleton"].call(
        module="RCR3_relation_event_skeleton",
        prompt=SKELETON_PROMPT,
        payload=skeleton_payload,
        validator=validate_skeleton,
    )
    skeleton = (
        sanitize_skeleton(skeleton_out.response, str(job["vignette"]))
        if skeleton_out.success
        else {}
    )
    skeleton_stage = _stage_outcome(skeleton_out, skeleton)
    if not skeleton_out.success or len(skeleton.get("observations") or []) < 4:
        error = skeleton_out.error or "fewer than four grounded observations"
        document = {
            "case_key": job["case_key"], "arm": RCR3, "success": False,
            "error": error, "skeleton": skeleton_stage, "generator": {},
            "registry": {}, "selector": {},
        }
        atomic_json(path, document)
        return document
    generator_payload = {
        "case_id": str(job["case_key"]),
        "clinical_record": str(job["vignette"]),
        "relation_skeleton": skeleton,
    }
    generated = callers["generator"].call(
        module="RCR3_batched_typed_generator",
        prompt=BATCHED_GENERATOR_PROMPT,
        payload=generator_payload,
        validator=validate_batched_generator,
    )
    generator = sanitize_batched_generator(generated.response, skeleton) if generated.success else {}
    generator_stage = _stage_outcome(generated, generator)
    if not generated.success:
        document = {
            "case_key": job["case_key"], "arm": RCR3, "success": False,
            "error": generated.error, "skeleton": skeleton_stage,
            "generator": generator_stage, "registry": {}, "selector": {},
        }
        atomic_json(path, document)
        return document
    registry = _rcr_registry(job, skeleton, generator, bridge)
    if len(registry["payload_candidates"]) < 2:
        document = {
            "case_key": job["case_key"], "arm": RCR3, "success": False,
            "error": "fewer than two safe frontier candidates",
            "skeleton": skeleton_stage, "generator": generator_stage,
            "registry": registry, "selector": {},
        }
        atomic_json(path, document)
        return document
    relation_context = {
        "kind": "grounded_relation_event_skeleton",
        "relations": skeleton["relations"],
        "diagnostic_assertions": skeleton["diagnostic_assertions"],
    }
    payload = selector_payload(job, registry, relation_context)
    ids = {str(row["candidate_id"]) for row in registry["payload_candidates"]}
    selected = callers["selector"].call(
        module="RCR3_completeness_pairwise_selector",
        prompt=SELECTOR_PROMPT,
        payload=payload,
        validator=lambda response: validate_selector(response, ids),
    )
    selector_stage = _stage_outcome(selected)
    document = {
        "case_key": job["case_key"], "arm": RCR3,
        "success": selected.success, "error": selected.error,
        "skeleton": skeleton_stage, "generator": generator_stage,
        "registry": registry, "selector": selector_stage,
    }
    atomic_json(path, document)
    return document


def _arm_archive(out: Path, arm: str) -> tuple[Path, Path]:
    arm_dir = out / "arms" / arm
    archive = out / f"RCR3_{arm}_RAW.tar.gz"
    sha = out / f"{archive.name}.sha256"
    with tarfile.open(archive, "w:gz") as bundle:
        for path in sorted(arm_dir.rglob("*")):
            if not path.is_file() or "cache" in path.parts:
                continue
            bundle.add(path, arcname=str(path.relative_to(out)))
    sha.write_text(f"{file_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, sha


def _append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def run_arm(
    *, arm: str, jobs: Sequence[Mapping[str, Any]], out: Path, model: str,
    workers: int, bridge: FrozenExactSynonymBridge, preregistration: Mapping[str, Any],
    input_hash: str,
) -> list[dict[str, Any]]:
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    (arm_dir / "case_stages").mkdir(parents=True, exist_ok=True)
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) != len(jobs):
            raise AssertionError(f"partial case_results requires audit: {len(rows)}/{len(jobs)}")
        _arm_archive(out, arm)
        return rows
    log_path = arm_dir / "run.log"
    for line in (
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"arm={arm}", f"model={model}", f"workers={workers}",
        f"jobs={len(jobs)}", f"logical_calls_per_case={LOGICAL_CALLS[arm]}",
    ):
        _append_log(log_path, line)

    if arm == RCR3:
        callers = {
            "skeleton": _caller(arm_dir, "skeleton", model),
            "generator": _caller(arm_dir, "generator", model),
            "selector": _caller(arm_dir, "selector", model),
        }
    else:
        active_views = FLAT_VIEWS[:2] if arm == LITE3 else (VIEW_EXCEPTION,)
        callers = {view: _caller(arm_dir, view, model) for view in active_views}
        callers["selector"] = _caller(arm_dir, "selector", model)
    lite_stage_dir = out / "arms" / LITE3 / "case_stages" if arm == COMPACT4 else None

    stages: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for job in jobs:
            if arm == RCR3:
                future = pool.submit(
                    _run_rcr_case, job=job, arm_dir=arm_dir, bridge=bridge, callers=callers
                )
            else:
                future = pool.submit(
                    _run_flat_case, job=job, arm=arm, arm_dir=arm_dir, model=model,
                    bridge=bridge, callers=callers, lite_stage_dir=lite_stage_dir,
                )
            futures[future] = job
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                stage = future.result()
            except Exception as exc:
                stage = {
                    "case_key": job["case_key"], "arm": arm, "success": False,
                    "error": f"{type(exc).__name__}: {exc}", "registry": {}, "selector": {},
                }
                atomic_json(_case_stage_path(arm_dir, job), stage)
            stages.append(stage)
            if done % 20 == 0 or done == len(jobs):
                line = (
                    f"completed={done}/{len(jobs)} "
                    f"failures={sum(not bool(row.get('success')) for row in stages)}"
                )
                print(line, flush=True)
                _append_log(log_path, line)

    by_key = {str(job["case_key"]): job for job in jobs}
    rows = [
        _result_from_stage(by_key[str(stage["case_key"])], arm, stage, bridge)
        for stage in stages
    ]
    rows.sort(key=lambda row: str(row["case_key"]))
    write_jsonl(result_path, rows)
    telemetry_rows: list[dict[str, Any]] = []
    for path in sorted((arm_dir / "telemetry").glob("*.jsonl")):
        telemetry_rows.extend(read_jsonl(path))
    telemetry_summary = aggregate_telemetry(telemetry_rows)
    telemetry_summary["logical_semantic_calls"] = len(rows) * LOGICAL_CALLS[arm]
    telemetry_summary["reused_semantic_calls_from_lite3"] = 2 * len(rows) if arm == COMPACT4 else 0
    atomic_json(arm_dir / "telemetry_summary.json", telemetry_summary)
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "arm": arm,
        "n": len(rows),
        "served": sum(bool(row["success"]) for row in rows),
        "failed": sum(not bool(row["success"]) for row in rows),
        "logical_calls_per_case": LOGICAL_CALLS[arm],
        "raw_registry_exposure_n": sum(bool(row["raw_registry_exposure_hit"]) for row in rows),
        "frontier_exposure_n": sum(bool(row["frontier_exposure_hit"]) for row in rows),
        "strict_top1_n": sum(bool(row["strict_top1"]) for row in rows),
        "strict_top2_n": sum(bool(row["strict_top2"]) for row in rows),
        "mean_registry_n": round(sum(int(row["registry_n"]) for row in rows) / len(rows), 4),
        "mean_frontier_n": round(sum(int(row["frontier_n"]) for row in rows) / len(rows), 4),
    }
    atomic_json(arm_dir / "summary.json", summary)
    prompt_hashes = {"selector": sha256_text(SELECTOR_PROMPT)}
    if arm == RCR3:
        prompt_hashes.update(
            skeleton=sha256_text(SKELETON_PROMPT),
            batched_generator=sha256_text(BATCHED_GENERATOR_PROMPT),
        )
    else:
        for view in (FLAT_VIEWS[:2] if arm == LITE3 else FLAT_VIEWS):
            prompt_hashes[view] = sha256_text(FLAT_GENERATOR_PROMPTS[view])
    RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id=arm,
        dataset="E6-frozen DA150+MCR150 relation-challenge development sample",
        model=model,
        workers=workers,
        rag=False,
        source_commit=str(preregistration["source_commit"]),
        prompt_hashes=prompt_hashes,
        input_hash=input_hash,
        selection_freeze="preregistration.json + fixed_inputs.jsonl + shared safe registry/selector",
        endpoint_contract=ENDPOINT_CONTRACT,
        excluded_variance_controls=[
            "repeat runs", "new confirmation set", "provider/retry standardisation"
        ],
        capabilities=dependency_capabilities(),
    ).write(arm_dir / "manifest.json")
    for line in (
        f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"served={summary['served']}/{summary['n']}",
        f"strict_top1={summary['strict_top1_n']}",
        f"frontier_exposure={summary['frontier_exposure_n']}",
    ):
        _append_log(log_path, line)
    _arm_archive(out, arm)
    return rows


def freeze_preregistration(
    out: Path, jobs: Sequence[Mapping[str, Any]], input_hash: str, model: str
) -> dict[str, Any]:
    candidate = {
        "schema": "RCR3_preregistration_v1",
        "experiment_id": EXPERIMENT_ID,
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "model": model,
        "input_hash": input_hash,
        "sample": {
            "source": "E6/E12 frozen relation-challenge development sample",
            "n": len(jobs),
            "family_counts": dict(Counter(str(job["family"]) for job in jobs)),
            "case_keys": [str(job["case_key"]) for job in jobs],
        },
        "arms": {
            LITE3: {
                "calls": 3,
                "contract": "two history-isolated full-record typed generators plus shared selector",
            },
            RCR3: {
                "calls": 3,
                "contract": "grounded relation/event skeleton plus batched three-view typed generator plus shared selector",
            },
            COMPACT4: {
                "calls": 4,
                "contract": "three history-isolated typed generators plus shared selector; first two calls reused byte-identically from lite3",
            },
        },
        "identity": {
            "policy": "exact plus frozen safe synonym bridge only",
            "bridge_sha256": FrozenExactSynonymBridge(BRIDGE_PATH).sha256,
            "forbidden": ["substring merge", "Jaccard merge", "broad/subtype silent merge"],
        },
        "frontier": {
            "main_k": 6,
            "protected_k": 2,
            "max_k": 8,
            "selector_payload_order": "neutral stable candidate ID",
            "generator vote/count withheld": True,
        },
        "primary_endpoint": "strict exact-or-frozen-safe-synonym pre-mapper top-1",
        "secondary_endpoints": [
            "strict top-2",
            "raw-registry and frontier reference exposure",
            "exposure-to-top1 conversion",
            "root-audited clinical complete top-1/top-2",
            "complete-or-partial scope sensitivity",
            "grounding fidelity, identity safety, cap displacement and selector rescue/harm",
            "semantic calls, attempts, tokens, latency and provider distribution",
        ],
        "primary_contrasts": [
            {"left": LITE3, "right": RCR3, "label": "rcr3_vs_lite3_same_3call_budget"},
            {"left": LITE3, "right": COMPACT4, "label": "third_generator_marginal_utility"},
            {"left": RCR3, "right": COMPACT4, "label": "compact4_vs_rcr3"},
        ],
        "multiplicity": "Holm across the three primary contrasts, separately by endpoint",
        "failure_policy": "intention-to-analyse; invalid/ungrounded stages retained and fail closed",
        "prompt_sha256": {
            "skeleton": sha256_text(SKELETON_PROMPT),
            "batched_generator": sha256_text(BATCHED_GENERATOR_PROMPT),
            **{view: sha256_text(prompt) for view, prompt in FLAT_GENERATOR_PROMPTS.items()},
            "selector": sha256_text(SELECTOR_PROMPT),
        },
        "payload_withheld": [
            "gold/reference", "answer options", "historical rank/score/vote/champion",
            "generator agreement/count", "registry priority score",
        ],
        "development_not_confirmation": True,
        "excluded_variance_controls": [
            "repeat runs", "new confirmation set", "provider/retry standardisation"
        ],
        "falsification": [
            "RCR3 does not improve clinical-complete exposure-to-top1 conversion over lite3",
            "grounded relation errors or dropped spans remain too frequent to support the proposed mechanism",
            "safe aggregation/frontier loses at least as many complete candidates as it rescues",
            "compact4's third independent generator adds churn without net complete endpoint gain",
        ],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("experiment_id", "model", "input_hash", "arms", "identity", "prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["sample"]["case_keys"] != candidate["sample"]["case_keys"]:
            raise AssertionError("sample differs from frozen preregistration")
        return frozen
    atomic_json(path, candidate)
    return candidate


def _write_fixed_inputs(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    rows = [
        {
            "case_key": job["case_key"],
            "slice_id": job["slice_id"],
            "family": job["family"],
            "source_id": job["source_id"],
            "vignette_sha256": json_sha256(job["vignette"]),
            "vignette_chars": len(str(job["vignette"])),
        }
        for job in jobs
    ]
    path = out / "fixed_inputs.jsonl"
    if path.is_file() and canonical_sha256(read_jsonl(path)) != canonical_sha256(rows):
        raise AssertionError("fixed RCR3 inputs drifted")
    write_jsonl(path, rows)


def finalize(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    missing = [arm for arm in ARMS if not (out / "arms" / arm / "case_results.jsonl").is_file()]
    if missing:
        raise AssertionError(f"cannot finalize; missing arms: {missing}")
    conditions: list[dict[str, Any]] = []
    for arm in ARMS:
        rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(rows) != len(jobs):
            raise AssertionError(f"arm incomplete: {arm}")
        conditions.extend(rows)
    conditions.sort(key=lambda row: (str(row["case_key"]), ARMS.index(str(row["arm"]))))
    write_jsonl(out / "case_conditions.jsonl", conditions)
    atomic_json(
        out / "run_completion.json",
        {
            "experiment_id": EXPERIMENT_ID,
            "n_cases": len(jobs),
            "n_arms": len(ARMS),
            "n_conditions": len(conditions),
            "all_arms_complete": True,
            "arm_summaries": {
                arm: json.loads((out / "arms" / arm / "summary.json").read_text(encoding="utf-8"))
                for arm in ARMS
            },
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, paths = load_jobs()
    input_hash = combined_file_sha256(paths)
    preregistration = freeze_preregistration(out, jobs, input_hash, args.model)
    _write_fixed_inputs(out, jobs)
    environment = out / "environment.json"
    if not environment.is_file():
        atomic_json(
            environment,
            {
                "capabilities": dependency_capabilities(),
                "model": args.model,
                "workers": workers,
                "llama_provider_policy": os.environ.get("TREE_DX_LLAMA_PROVIDER_POLICY"),
                "reasoning_controls": {
                    "effort": os.environ.get("TREE_DX_REASONING_EFFORT"),
                    "max_tokens": os.environ.get("TREE_DX_REASONING_MAX_TOKENS"),
                    "exclude": os.environ.get("TREE_DX_REASONING_EXCLUDE"),
                },
                "preregistration_sha256": file_sha256(out / "preregistration.json"),
                "fixed_inputs_sha256": file_sha256(out / "fixed_inputs.jsonl"),
            },
        )
    if args.prepare_only:
        print(json.dumps({"prepared": len(jobs), "input_hash": input_hash}, sort_keys=True))
        return 0
    if args.arm:
        if args.arm == COMPACT4 and not (out / "arms" / LITE3 / "case_results.jsonl").is_file():
            raise SystemExit("compact4 requires completed lite3_safe shared generator stages")
        rows = run_arm(
            arm=args.arm, jobs=jobs, out=out, model=args.model, workers=workers,
            bridge=bridge, preregistration=preregistration, input_hash=input_hash,
        )
        print(
            json.dumps(
                {
                    "arm": args.arm,
                    "served": sum(bool(row["success"]) for row in rows),
                    "strict_top1": sum(bool(row["strict_top1"]) for row in rows),
                    "frontier_exposure": sum(bool(row["frontier_exposure_hit"]) for row in rows),
                },
                sort_keys=True,
            )
        )
    if args.finalize:
        finalize(out, jobs)
        print(f"finalized {len(jobs)} cases across {len(ARMS)} arms")
    if not args.arm and not args.finalize:
        raise SystemExit("select --arm, --finalize, or --prepare-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
