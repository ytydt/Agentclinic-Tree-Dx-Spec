#!/usr/bin/env python3
"""Extract complex guideline-KG residuals from claim-aware windows.

Credentials are accepted only through ``OPENROUTER_API_KEY``.  Prompts and
source passages are never written to telemetry.  A success cache entry is
created only after JSON, closed-inventory, exact-offset, and full-graph
validation pass; failures remain in an append-only attempt ledger.

The default semantic unit is a ``ClaimWindow`` reconstructed from source-native
entries and mapped character-for-character back to one or more immutable
``Passage`` records.  The LLM selects an evidence-unit ID, exact surface, and
1-based occurrence; this runner alone materializes absolute offsets, refuses
unmapped text, and projects accepted evidence back to exact source spans before
graph validation.  The former one-Passage-per-call path is retained only behind
the explicitly named ``--legacy-passage-queue`` option.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping, NamedTuple, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.guideline_kg_extraction import (  # noqa: E402
    RecordAccumulator,
    convert_validated_llm_slots,
    evidence_sentence_inventory,
    llm_candidate_inventory,
    load_disease_aliases,
    normalize_term,
    passage_metadata,
    sentence_spans,
    sha256_text,
)
from agentclinic_tree_dx.knowledge.guideline_kg_schema import (  # noqa: E402
    EvidenceSpan,
    ExtractionActivity,
    GraphValidationIndex,
    assert_valid_graph,
    record_to_dict,
    stable_id_for,
)

PIPELINE_NAME = "guideline_kg_citation_bounded_residual"
PIPELINE_VERSION = "0.5.0"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_FALLBACK = "google/gemini-2.5-flash"
DEFAULT_GRAPH = (
    ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/build/graph.internal.jsonl"
)
DEFAULT_CLAIM_WINDOWS = (
    ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/production_queue"
    / "claim_windows.production.internal.jsonl"
)
DEFAULT_ALIASES = ROOT / "data/knowledge_raw/disease_name_bridge_flat.json"
DEFAULT_OUTPUT = ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/llm_pilot"
MAX_ASSERTIONS_PER_CALL = 12
OUTPUT_ENVELOPE_RESERVE_TOKENS = 320
OUTPUT_TOKENS_PER_ASSERTION_FLOOR = 240
MIN_OUTPUT_TOKENS = (
    OUTPUT_ENVELOPE_RESERVE_TOKENS
    + MAX_ASSERTIONS_PER_CALL * OUTPUT_TOKENS_PER_ASSERTION_FLOOR
)
DEFAULT_MAX_OUTPUT_TOKENS = MIN_OUTPUT_TOKENS

COMPLETE_COVERAGE_STATUSES = {"complete", "nothing_extractable"}
RESPLIT_COVERAGE_STATUSES = {
    "resplit_assertion_capacity",
    "resplit_evidence_unit",
    "resplit_output_capacity",
}
REVIEW_COVERAGE_STATUSES = {
    "review_scope_ambiguity",
    "review_other",
}
ALL_COVERAGE_STATUSES = (
    COMPLETE_COVERAGE_STATUSES
    | RESPLIT_COVERAGE_STATUSES
    | REVIEW_COVERAGE_STATUSES
)

ROLE_TO_DIRECTION = {
    "defining": "supports",
    "necessary": "supports",
    "sufficient": "supports",
    "supporting": "supports",
    "typical": "supports",
    "compatible": "supports",
    "argues_against": "argues_against",
    "excluding": "argues_against",
    "risk_factor": "supports",
}

# Builder-emitted, source-free admission labels.  They only decide whether an
# empty response needs independent confirmation; they never create assertions.
BLOCK_LOCAL_DIAGNOSTIC_GATE_REASONS = {
    "text:explicit_diagnostic_cue",
    "section:diagnostic_or_clinical",
    "heading:diagnostic_or_clinical",
}
_DIAGNOSTIC_SECTION_RE = re.compile(
    r"\b(?:diagnos(?:is|tic)|diagnostic criteria|differential(?: diagnosis)?|"
    r"clinical features?|symptoms? and signs?|testing)\b",
    re.I,
)
_DIAGNOSTIC_RELATION_RE = re.compile(
    r"\b(?:diagnos(?:is|ed|tic)|characteri[sz]ed|suggests?|consistent with|"
    r"pathognomonic|rules? out|unlikely|criteria|criterion|confirm(?:s|ed|atory)?|"
    r"distinguish(?:es|ed|ing)?|more likely|less likely)\b",
    re.I,
)

SYSTEM_PROMPT = """You extract ONLY diagnostic assertions explicitly stated in one supplied guideline claim-window.

Hard rules:
1. A diagnosis must use a candidate_id from TARGET_CANDIDATES. Use UNRESOLVED only when the diagnosis surface itself occurs exactly in the cited evidence unit and that unit explicitly calls it diagnosed, characterized, or diagnostic.
2. Cite exactly one EVIDENCE_UNIT mention_id. An evidence unit is normally one complete primary claim block and may contain a header, multiple sentences, bullets, or table rows. Copy feature_surface exactly, without leading/trailing whitespace, and return feature_occurrence_index: count exact non-overlapping matches from left to right within the selected EVIDENCE_UNIT text, starting at 1. Do not return character offsets and do not paraphrase. For every non-atomic component, use the same exact-surface plus 1-based occurrence rule within that same evidence unit.
3. Never infer from medical knowledge. Do not convert a differential list into a diagnostic criterion. Do not treat treatment recommendations as diagnostic evidence.
4. Preserve absence, uncertainty, diagnostic role, necessity, AND/OR/k-of-n/sequence, time, population, thresholds, and comparisons. Do not return direction: the runner derives it mechanically from diagnostic_role. For atomic logic return feature_components=[]; for non-atomic logic return each exact component and its 1-based occurrence index. Return k=0 unless logic_operator=k_of_n; for k_of_n return the positive required count.
5. Use assertion_type=differential only when the cited evidence unit explicitly compares two diagnoses; both diagnoses must be inventory IDs.
6. coverage_status=complete means assertions contains every safely extractable diagnostic assertion in the supplied units and has 1–12 items. If nothing is extractable, use nothing_extractable and assertions=[]. If more than 12 assertions are needed, return resplit_assertion_capacity with assertions=[]. If the complete JSON may not fit the output budget, return resplit_output_capacity with assertions=[]. Use resplit_evidence_unit for an evidence unit whose internal scope is too broad, and review_scope_ambiguity or review_other when extraction needs human or stronger-model review. NEVER return a partial prefix as complete. Resplit and review statuses must not be treated as empty coverage.
7. CONTEXT_ONLY may clarify a subject or scope but is never citable evidence. Every returned feature_surface, feature_occurrence_index, and evidence_mention_id must belong to one EVIDENCE_UNIT.
Return strict JSON conforming to the requested schema; no markdown."""
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assertions", "coverage_status"],
    "properties": {
        "coverage_status": {
            "type": "string",
            "enum": sorted(ALL_COVERAGE_STATUSES),
        },
        "assertions": {
            "type": "array",
            "maxItems": MAX_ASSERTIONS_PER_CALL,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "assertion_type", "target_candidate_id", "target_surface",
                    "diagnosis_a_candidate_id", "diagnosis_b_candidate_id", "favors",
                    "evidence_mention_id", "feature_surface",
                    "feature_occurrence_index", "feature_type", "polarity",
                    "diagnostic_role", "necessity", "logic_operator",
                    "feature_components",
                    "k", "scope_note", "confidence",
                ],
                "properties": {
                    "assertion_type": {
                        "type": "string", "enum": ["diagnostic", "differential"],
                    },
                    "target_candidate_id": {"type": "string"},
                    "target_surface": {"type": "string"},
                    "diagnosis_a_candidate_id": {"type": "string"},
                    "diagnosis_b_candidate_id": {"type": "string"},
                    "favors": {
                        "type": "string",
                        "enum": ["a", "b", "neither", "context_dependent", ""],
                    },
                    "evidence_mention_id": {"type": "string"},
                    "feature_surface": {"type": "string"},
                    "feature_occurrence_index": {"type": "integer", "minimum": 1},
                    "feature_type": {
                        "type": "string",
                        "enum": [
                            "symptom", "sign", "laboratory", "imaging", "pathology",
                            "genetics", "procedure", "history", "demographic", "exposure",
                            "medication", "course", "other",
                        ]
                    },
                    "polarity": {
                        "type": "string", "enum": ["present", "absent", "uncertain"],
                    },
                    "diagnostic_role": {
                        "type": "string",
                        "enum": [
                            "defining", "necessary", "sufficient", "supporting", "typical",
                            "compatible", "argues_against", "excluding", "risk_factor",
                        ]
                    },
                    "necessity": {
                        "type": "string",
                        "enum": ["necessary", "sufficient", "optional", "not_stated"],
                    },
                    "logic_operator": {
                        "type": "string",
                        "enum": ["atomic", "and", "or", "k_of_n", "sequence"],
                    },
                    "feature_components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "feature_surface", "feature_occurrence_index",
                                "feature_type", "polarity",
                            ],
                            "properties": {
                                "feature_surface": {"type": "string"},
                                "feature_occurrence_index": {
                                    "type": "integer", "minimum": 1,
                                },
                                "feature_type": {
                                    "type": "string",
                                    "enum": [
                                        "symptom", "sign", "laboratory", "imaging",
                                        "pathology", "genetics", "procedure", "history",
                                        "demographic", "exposure", "medication", "course",
                                        "other",
                                    ]
                                },
                                "polarity": {
                                    "type": "string",
                                    "enum": ["present", "absent", "uncertain"],
                                },
                            },
                        },
                    },
                    "k": {"type": "integer", "minimum": 0},
                    "scope_note": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected object")
            rows.append(value)
    return rows


def count_tokens(value: str) -> tuple[int, str]:
    try:
        import tiktoken  # type: ignore
        return len(tiktoken.get_encoding("o200k_base").encode(value)), "o200k_base"
    except Exception:
        return max(1, (len(value) + 3) // 4), "chars_div_4"


def response_format_for_mode(structured_mode: str) -> dict[str, Any]:
    if structured_mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "guideline_diagnostic_residuals",
                "strict": True,
                "schema": RESPONSE_SCHEMA,
            },
        }
    if structured_mode == "json_object":
        return {"type": "json_object"}
    raise ValueError(f"unsupported structured mode {structured_mode!r}")


def provider_routing_for_mode(
    structured_mode: str,
    *,
    provider_sort: str,
    provider_data_collection: str,
    strict_require_parameters: bool,
) -> dict[str, Any]:
    """Build auditable OpenRouter preferences without pinning a provider."""

    if provider_sort not in {"throughput", "latency", "price"}:
        raise ValueError(f"unsupported provider sort {provider_sort!r}")
    if provider_data_collection not in {"allow", "deny"}:
        raise ValueError(
            f"unsupported provider data_collection {provider_data_collection!r}"
        )
    value: dict[str, Any] = {
        "sort": provider_sort,
        "data_collection": provider_data_collection,
    }
    if structured_mode == "json_schema":
        value["require_parameters"] = bool(strict_require_parameters)
    return value


def messages_for_mode(
    messages: Sequence[Mapping[str, str]], structured_mode: str,
) -> list[dict[str, str]]:
    request_messages = [dict(item) for item in messages]
    if structured_mode == "json_object":
        # Providers without response_format=json_schema must see the same exact
        # closed contract in-band.  Preflight uses this helper too, so fallback
        # schema overhead can never bypass the hard input limit.
        request_messages[-1] = {
            **request_messages[-1],
            "content": (
                str(request_messages[-1]["content"])
                + "\n\nOUTPUT_JSON_SCHEMA (follow exactly):\n"
                + canonical_json(RESPONSE_SCHEMA)
            ),
        }
    return request_messages


def rendered_prompt_token_estimates(
    messages: Sequence[Mapping[str, str]], modes: Sequence[str],
) -> tuple[dict[str, int], str]:
    """Conservatively count messages plus provider-visible schema contracts."""

    estimates: dict[str, int] = {}
    tokenizers: set[str] = set()
    for mode in modes:
        contract = {
            "messages": messages_for_mode(messages, mode),
            # Strict providers may include response_format schema tokens in
            # their context accounting.  Include it for both modes.
            "response_format": response_format_for_mode(mode),
        }
        count, tokenizer = count_tokens(canonical_json(contract))
        estimates[mode] = count
        tokenizers.add(tokenizer)
    return estimates, "+".join(sorted(tokenizers))


def parse_json_object(raw: str) -> dict[str, Any]:
    stripped = (raw or "").strip()
    if stripped.startswith("```"):
        stripped = "\n".join(
            line for line in stripped.splitlines()
            if not line.strip().startswith("```")
        ).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group())
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value


class OpenRouterError(RuntimeError):
    def __init__(
        self, status: int | None, message: str,
        retry_after: float | None = None,
        response_payload: Mapping[str, Any] | None = None,
        error_category: str | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.response_payload = dict(response_payload or {})
        self.error_category = error_category


def parse_retry_after(value: str | None) -> float | None:
    """Parse an HTTP Retry-After delta or date without trusting huge sleeps."""

    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            now = datetime.now(retry_at.tzinfo or timezone.utc)
            return max(0.0, (retry_at - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def post_openrouter(
    *,
    api_key: str,
    model: str,
    messages: Sequence[Mapping[str, str]],
    max_output_tokens: int,
    structured_mode: str,
    timeout_seconds: int,
    provider_sort: str = "throughput",
    provider_data_collection: str = "deny",
    strict_require_parameters: bool = True,
) -> tuple[dict[str, Any], str]:
    request_messages = messages_for_mode(messages, structured_mode)
    body: dict[str, Any] = {
        "model": model,
        "messages": request_messages,
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "reasoning": {"enabled": False, "exclude": True},
        "provider": provider_routing_for_mode(
            structured_mode,
            provider_sort=provider_sort,
            provider_data_collection=provider_data_collection,
            strict_require_parameters=strict_require_parameters,
        ),
    }
    body["response_format"] = response_format_for_mode(structured_mode)
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=canonical_json(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ytydt/Agentclinic-Tree-Dx-Spec",
            "X-Title": "AgentClinic guideline KG",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        try:
            error_payload = json.loads(body_text)
        except json.JSONDecodeError:
            error_payload = {}
        retry_seconds = parse_retry_after(exc.headers.get("Retry-After"))
        error_category = None
        if exc.code == 400 and structured_mode == "json_schema":
            error_category = "structured_schema_http_400"
        raise OpenRouterError(
            exc.code, body_text, retry_seconds,
            response_payload=error_payload
            if isinstance(error_payload, Mapping) else {},
            error_category=error_category,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OpenRouterError(None, f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("choices"):
        raise OpenRouterError(None, f"malformed provider response: {str(payload)[:500]}")
    choice = payload["choices"][0]
    finish_reason = str(choice.get("finish_reason") or "")
    if finish_reason not in {"stop", "end_turn"}:
        raise OpenRouterError(None, f"incomplete finish_reason={finish_reason!r}")
    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str):
        raise OpenRouterError(None, "response content is not text")
    try:
        payload["_parsed_content"] = parse_json_object(content)
    except (json.JSONDecodeError, ValueError) as exc:
        raise OpenRouterError(
            None, f"invalid_json_object:{type(exc).__name__}",
            response_payload=payload,
        ) from exc
    return payload, structured_mode


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(value) + "\n")


def append_private_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    """Append a private audit row and force owner-only file permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(canonical_json(value) + "\n")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def append_private_rejection(
    path: Path | None,
    *,
    semantic_mode: str,
    semantic_unit_id: str,
    cache_key_value: str,
    stage: str,
    response_object: Mapping[str, Any],
    rejections: Sequence[Mapping[str, Any]],
    normalizations: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Optionally retain raw rejected output outside public telemetry."""

    if path is None:
        return
    append_private_jsonl(path, {
        "pipeline": f"{PIPELINE_NAME}@{PIPELINE_VERSION}",
        "semantic_mode": semantic_mode,
        "semantic_unit_id": semantic_unit_id,
        "cache_key": cache_key_value,
        "stage": stage,
        "response_sha256": sha256_text(canonical_json(response_object)),
        "response": dict(response_object),
        "rejections": [dict(item) for item in rejections],
        "normalizations": [dict(item) for item in normalizations],
        "includes_prompt_or_evidence_inventory": False,
        "may_contain_source_text_from_model_output": True,
    })


def commit_validated_call_delta(
    accumulator: RecordAccumulator,
    tracker: Mapping[str, Any],
    validation_index: GraphValidationIndex,
) -> list[str]:
    """Validate/commit one extraction delta or atomically roll it back."""

    delta_ids = accumulator.delta_ids(tracker)
    delta_records = [accumulator.records[record_id] for record_id in delta_ids]
    try:
        validation_index.apply_delta(delta_records)
    except Exception:
        accumulator.rollback_delta(tracker)
        raise
    return accumulator.commit_delta(tracker)


class ClaimWindowError(ValueError):
    """Raised when a claim window cannot be losslessly traced to Passages."""


def _window_id(window: Mapping[str, Any]) -> str:
    value = str(window.get("window_id") or window.get("id") or "").strip()
    if not value:
        raise ClaimWindowError("claim window requires window_id or id")
    return value


def normalize_claim_window(
    window: Mapping[str, Any],
    passage_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate and normalize the lossless ClaimWindow interchange contract.

    Canonical offset-map entries use half-open window and Passage offsets::

        {window_start_char, window_end_char, passage_id,
         passage_start_char, passage_end_char, kind}

    ``source_map`` is accepted as an alias for ``offset_map``.  Source-derived
    overlap/header copies remain traceable and may use ``context_copy`` or
    ``overlap``; inserted separators are deliberately absent from the map.
    """

    value = dict(window)
    value["window_id"] = _window_id(value)
    text = value.get("text")
    if not isinstance(text, str) or not text:
        raise ClaimWindowError("claim window text must be a non-empty string")
    rechunker_version = str(value.get("rechunker_version") or "").strip()
    if not rechunker_version:
        raise ClaimWindowError("claim window requires rechunker_version")
    value["rechunker_version"] = rechunker_version
    declared_hash = value.get("text_sha256")
    actual_hash = sha256_text(text)
    if declared_hash is not None and str(declared_hash) != actual_hash:
        raise ClaimWindowError("claim window text_sha256 mismatch")
    raw_map = value.get("offset_map")
    if raw_map is None:
        raw_map = value.get("source_map")
    if not isinstance(raw_map, list) or not raw_map:
        raise ClaimWindowError("claim window requires non-empty offset_map/source_map")

    normalized: list[dict[str, Any]] = []
    allowed_kinds = {"source", "context_copy", "overlap"}
    for position, raw in enumerate(raw_map):
        if not isinstance(raw, Mapping):
            raise ClaimWindowError(f"offset_map[{position}] must be an object")
        try:
            window_start = int(raw.get("window_start_char"))
            window_end = int(raw.get("window_end_char"))
            passage_start = int(
                raw.get("passage_start_char", raw.get("source_start_char"))
            )
            passage_end = int(
                raw.get("passage_end_char", raw.get("source_end_char"))
            )
        except (TypeError, ValueError) as exc:
            raise ClaimWindowError(
                f"offset_map[{position}] requires integer half-open offsets"
            ) from exc
        passage_id = str(raw.get("passage_id") or "")
        kind = str(raw.get("kind") or "source")
        if kind not in allowed_kinds:
            raise ClaimWindowError(f"offset_map[{position}] has unsupported kind={kind!r}")
        eligible_for_evidence = raw.get("eligible_for_evidence", kind == "source")
        if not isinstance(eligible_for_evidence, bool):
            raise ClaimWindowError(
                f"offset_map[{position}].eligible_for_evidence must be boolean"
            )
        if kind == "context_copy" and eligible_for_evidence:
            raise ClaimWindowError(
                f"offset_map[{position}] context_copy cannot be evidence eligible"
            )
        if not (0 <= window_start < window_end <= len(text)):
            raise ClaimWindowError(f"offset_map[{position}] window range is invalid")
        passage = passage_index.get(passage_id)
        if not passage or passage.get("record_type") != "Passage":
            raise ClaimWindowError(
                f"offset_map[{position}] references missing Passage {passage_id!r}"
            )
        passage_text = str(passage.get("text") or "")
        if not (0 <= passage_start < passage_end <= len(passage_text)):
            raise ClaimWindowError(f"offset_map[{position}] Passage range is invalid")
        if window_end - window_start != passage_end - passage_start:
            raise ClaimWindowError(f"offset_map[{position}] is not character preserving")
        if text[window_start:window_end] != passage_text[passage_start:passage_end]:
            raise ClaimWindowError(f"offset_map[{position}] mapped source text mismatch")
        normalized.append({
            "window_start_char": window_start,
            "window_end_char": window_end,
            "passage_id": passage_id,
            "passage_start_char": passage_start,
            "passage_end_char": passage_end,
            "kind": kind,
            "eligible_for_evidence": eligible_for_evidence,
        })
    normalized.sort(key=lambda item: (
        item["window_start_char"], item["window_end_char"], item["passage_id"]
    ))
    previous_end = -1
    for position, item in enumerate(normalized):
        if item["window_start_char"] < previous_end:
            raise ClaimWindowError(
                f"offset_map[{position}] overlaps another window-coordinate segment"
            )
        previous_end = item["window_end_char"]
    value["text_sha256"] = actual_hash
    value["offset_map"] = normalized
    value["offset_map_sha256"] = hashlib.sha256(
        canonical_json(normalized).encode("utf-8")
    ).hexdigest()
    return value


def project_window_range(
    window: Mapping[str, Any],
    start_char: int,
    end_char: int,
    *,
    allow_unmapped_whitespace: bool,
    require_evidence_eligible: bool = True,
) -> list[dict[str, Any]]:
    """Project one half-open window range to exact original-Passage ranges."""

    text = str(window.get("text") or "")
    if not (0 <= start_char < end_char <= len(text)):
        raise ClaimWindowError("window projection range is invalid")
    pieces: list[dict[str, Any]] = []
    covered: list[tuple[int, int]] = []
    for item in window.get("offset_map") or []:
        if require_evidence_eligible and not item.get("eligible_for_evidence", False):
            continue
        overlap_start = max(start_char, int(item["window_start_char"]))
        overlap_end = min(end_char, int(item["window_end_char"]))
        if overlap_start >= overlap_end:
            continue
        source_start = int(item["passage_start_char"]) + (
            overlap_start - int(item["window_start_char"])
        )
        source_end = source_start + (overlap_end - overlap_start)
        piece = {
            "window_start_char": overlap_start,
            "window_end_char": overlap_end,
            "passage_id": item["passage_id"],
            "passage_start_char": source_start,
            "passage_end_char": source_end,
            "kind": item["kind"],
            "eligible_for_evidence": bool(item.get("eligible_for_evidence")),
        }
        if pieces and (
            pieces[-1]["passage_id"] == piece["passage_id"]
            and pieces[-1]["window_end_char"] == piece["window_start_char"]
            and pieces[-1]["passage_end_char"] == piece["passage_start_char"]
        ):
            pieces[-1]["window_end_char"] = piece["window_end_char"]
            pieces[-1]["passage_end_char"] = piece["passage_end_char"]
        else:
            pieces.append(piece)
        covered.append((overlap_start, overlap_end))
    cursor = start_char
    for covered_start, covered_end in covered:
        if covered_start > cursor:
            gap = text[cursor:covered_start]
            if not allow_unmapped_whitespace or gap.strip():
                raise ClaimWindowError("cited range contains unmapped source characters")
        cursor = max(cursor, covered_end)
    if cursor < end_char:
        gap = text[cursor:end_char]
        if not allow_unmapped_whitespace or gap.strip():
            raise ClaimWindowError("cited range contains unmapped source characters")
    if not pieces:
        raise ClaimWindowError("cited range contains no mapped source characters")
    return pieces


def claim_window_candidate_inventory(
    window: Mapping[str, Any],
    passage_index: Mapping[str, Mapping[str, Any]],
    aliases: Mapping[str, str],
    *,
    max_candidates: int = 40,
) -> list[dict[str, str]]:
    """Aggregate candidates from the reassembled text and all source Passages."""

    metadata = dict(window.get("metadata") or {})
    for key in (
        "source", "source_family", "source_id", "entry_title",
        "syndrome_anchor", "title_root", "section_path",
    ):
        if key in window and key not in metadata:
            metadata[key] = window[key]
    metadata["section_path"] = claim_window_section_context(window)
    synthetic = {
        "id": window["window_id"], "record_type": "Passage", "text": window["text"],
        "extensions": metadata,
    }
    labels: list[str] = []
    seen: set[str] = set()

    def add_label(raw: Any) -> None:
        if len(labels) >= max_candidates:
            return
        if not isinstance(raw, str):
            return
        surface = " ".join(raw.strip(" :;,.\t\r\n").split())
        normalized = normalize_term(surface)
        if normalized in {
            "diagnosis", "diagnostic criteria", "clinical features",
            "evaluation", "differential diagnosis", "testing",
        }:
            return
        canonical = aliases.get(normalized, surface)
        canonical_normalized = normalize_term(canonical)
        if canonical_normalized and canonical_normalized not in seen:
            seen.add(canonical_normalized)
            labels.append(canonical)

    # Rechunking deliberately aggregates source-native entry context.  Consume
    # every aggregated title/link, not just an arbitrary primary Passage's
    # metadata, or the improved context window would lose its diagnosis target.
    scalar_keys = ("entry_title", "entry_label", "syndrome_anchor", "title_root")
    list_keys = (
        "entry_title_candidates", "syndrome_anchor_candidates",
        "title_root_candidates", "wiki_links", "diagnosis_candidates",
        "candidate_surfaces",
    )
    for container in (window, metadata):
        for key in scalar_keys:
            add_label(container.get(key))
        for key in list_keys:
            values = container.get(key) or []
            if isinstance(values, str):
                values = [values]
            if isinstance(values, Sequence):
                for value in values:
                    add_label(value)
        if len(labels) >= max_candidates:
            break
    sources: list[Mapping[str, Any]] = [synthetic]
    source_ids = list(dict.fromkeys(
        str(item["passage_id"]) for item in window["offset_map"]
    ))
    sources.extend(passage_index[source_id] for source_id in source_ids)
    for source in sources:
        for item in llm_candidate_inventory(source, aliases, max_candidates=max_candidates):
            label = str(item["label"])
            normalized = normalize_term(label)
            if normalized and normalized not in seen:
                seen.add(normalized)
                labels.append(label)
                if len(labels) >= max_candidates:
                    break
        if len(labels) >= max_candidates:
            break
    return [
        {"candidate_id": f"dx{index:03d}", "label": label}
        for index, label in enumerate(labels, start=1)
    ]


def claim_window_section_context(window: Mapping[str, Any]) -> list[str]:
    """Return all source-native section paths without selecting a primary one."""

    raw_paths = window.get("section_paths")
    if raw_paths is None:
        raw_paths = (window.get("metadata") or {}).get("section_paths")
    paths: list[Any]
    if isinstance(raw_paths, list) and raw_paths and all(
        isinstance(item, (list, tuple)) for item in raw_paths
    ):
        paths = raw_paths
    else:
        single = window.get("section_path") or (
            window.get("metadata") or {}
        ).get("section_path") or []
        paths = [single]
    rendered: list[str] = []
    for path in paths:
        if isinstance(path, str):
            value = " ".join(path.split())
        elif isinstance(path, (list, tuple)):
            value = " > ".join(str(item) for item in path if item)
        else:
            value = ""
        if value and value not in rendered:
            rendered.append(value)
    return rendered


def claim_window_evidence_inventory(
    window: Mapping[str, Any],
    *,
    max_units: int,
    max_sentence_subspans: int,
) -> tuple[list[dict[str, Any]], str]:
    """Build claim-block evidence units with exact window-global coordinates.

    A sentence fallback exists only for pre-v1/diagnostic fixtures and is
    explicitly labeled.  Production ClaimWindows must carry
    ``primary_claim_blocks`` so header/list/table closure remains one unit.
    """

    raw_blocks = window.get("primary_claim_blocks")
    if not raw_blocks:
        fallback = evidence_sentence_inventory(
            {"text": window["text"]}, max_sentences=max_sentence_subspans,
        )
        return [
            {**item, "unit_type": "legacy_sentence_fallback"}
            for item in fallback
        ], "legacy_sentence_fallback"
    if not isinstance(raw_blocks, list):
        raise ClaimWindowError("primary_claim_blocks must be a list")
    if any(not isinstance(raw, Mapping) for raw in raw_blocks):
        raise ClaimWindowError("every primary_claim_blocks item must be an object")
    eligible_blocks = [
        raw for raw in raw_blocks
        if isinstance(raw, Mapping) and raw.get("eligible_for_evidence") is True
    ]
    if not eligible_blocks:
        raise ClaimWindowError("claim window has no evidence-eligible primary claim block")
    if len(eligible_blocks) > max_units:
        raise ClaimWindowError(
            f"claim window has {len(eligible_blocks)} evidence units; refusing silent "
            f"truncation at {max_units}"
        )
    units: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    previous_end = -1
    total_subspans = 0
    for position, raw in enumerate(eligible_blocks, start=1):
        block_id = str(raw.get("block_id") or "").strip()
        if not block_id or block_id in seen_ids:
            raise ClaimWindowError("claim blocks require unique non-empty block_id")
        seen_ids.add(block_id)
        try:
            start = int(raw.get("window_start_char"))
            end = int(raw.get("window_end_char"))
        except (TypeError, ValueError) as exc:
            raise ClaimWindowError(f"primary claim block {block_id!r} lacks offsets") from exc
        if start < previous_end:
            raise ClaimWindowError("primary claim blocks overlap or are out of order")
        previous_end = end
        project_window_range(
            window, start, end,
            allow_unmapped_whitespace=True,
            require_evidence_eligible=True,
        )
        block_text = str(window["text"])[start:end]
        subspans = [
            {
                "subspan_id": f"b{position:03d}_s{sub_index:03d}",
                "start_char": start + local_start,
                "end_char": start + local_end,
            }
            for sub_index, (local_start, local_end, _) in enumerate(
                sentence_spans(block_text), start=1,
            )
        ]
        total_subspans += len(subspans)
        if total_subspans > max_sentence_subspans:
            raise ClaimWindowError(
                f"claim window has more than {max_sentence_subspans} sentence "
                "subspans; refusing silent truncation"
            )
        units.append({
            "mention_id": f"b{position:03d}",
            "block_id": block_id,
            "unit_type": "primary_claim_block",
            "block_type": str(raw.get("block_type") or "other"),
            "structural_role": str(raw.get("structural_role") or "other"),
            "logic_cues": list(raw.get("logic_cues") or []),
            "diagnostic_gate_reasons": list(
                raw.get("diagnostic_gate_reasons") or []
            ),
            "contains_scope_cue": bool(raw.get("contains_scope_cue")),
            "start_char": start,
            "end_char": end,
            "text": block_text,
            "sentence_subspans": subspans,
        })
    return units, "primary_claim_block"


def claim_window_context_inventory(window: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose mapped semantic overlap as non-citable context without duplication."""

    contexts: list[dict[str, Any]] = []
    for item in window.get("offset_map") or []:
        if item.get("eligible_for_evidence"):
            continue
        start = int(item["window_start_char"])
        end = int(item["window_end_char"])
        contexts.append({
            "context_id": f"c{len(contexts) + 1:03d}",
            "kind": str(item.get("kind") or "context"),
            "start_char": start,
            "end_char": end,
            "text": str(window["text"])[start:end],
            "eligible_for_evidence": False,
        })
    return contexts


def prompt_evidence_inventory(
    evidence: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Remove repeated audit-only fields while preserving every source byte.

    Large guidelines often contain many one-sentence prose blocks.  Repeating
    verbose structural keys for each block can cost several times more tokens
    than the source itself.  The prompt view keeps exact text/global offsets and
    emits subspan offsets only when a block actually contains multiple spans;
    the full inventory remains authoritative for validation and caching.
    """

    result: list[dict[str, Any]] = []
    for item in evidence:
        value: dict[str, Any] = {
            "mention_id": item["mention_id"],
            "start_char": item["start_char"],
            "end_char": item["end_char"],
            "text": item["text"],
        }
        for key in ("block_type", "structural_role"):
            if item.get(key) not in (None, "", "other"):
                value[key] = item[key]
        if item.get("logic_cues"):
            value["logic_cues"] = item["logic_cues"]
        if item.get("contains_scope_cue"):
            value["contains_scope_cue"] = True
        subspans = item.get("sentence_subspans") or []
        if len(subspans) > 1:
            value["sentence_subspans"] = [
                [subspan["start_char"], subspan["end_char"]]
                for subspan in subspans
            ]
        result.append(value)
    return result


def prompt_context_inventory(
    contexts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "context_id": item["context_id"],
            "kind": item["kind"],
            "start_char": item["start_char"],
            "end_char": item["end_char"],
            "text": item["text"],
            "citable": False,
        }
        for item in contexts
    ]


def _normalized_phrase_occurs(label: str, text: str) -> bool:
    """Match a candidate as normalized whole tokens, never as a substring."""

    normalized_label = normalize_term(label)
    normalized_text = normalize_term(text)
    if not normalized_label or not normalized_text:
        return False
    return f" {normalized_label} " in f" {normalized_text} "


def empty_confirmation_signals(
    *,
    evidence_inventory: Sequence[Mapping[str, Any]],
    candidate_inventory: Sequence[Mapping[str, Any]],
    section_path: Sequence[str],
) -> list[str]:
    """Return source-free reasons why an LLM empty needs independent review.

    The detector only gates caching.  It cannot create an assertion, and a
    signal does not imply that the window truly contains an extractable claim.
    False positives therefore cost a confirmation call but cannot pollute the
    graph; false negatives are bounded by combining builder metadata, structure,
    and exact normalized candidate/relation co-occurrence.
    """

    signals: set[str] = set()
    candidate_labels = [
        str(item.get("label") or "")
        for item in candidate_inventory
        if str(item.get("label") or "").strip()
    ]
    for unit in evidence_inventory:
        gate_reasons = {
            str(value) for value in (unit.get("diagnostic_gate_reasons") or [])
        }
        if gate_reasons & BLOCK_LOCAL_DIAGNOSTIC_GATE_REASONS:
            signals.add("block_local_diagnostic_gate")
        if (
            str(unit.get("structural_role") or "") == "criteria_closure"
            or str(unit.get("block_type") or "").startswith("criteria")
        ):
            signals.add("criteria_structure")
        text = str(unit.get("text") or "")
        candidate_present = any(
            _normalized_phrase_occurs(label, text) for label in candidate_labels
        )
        if candidate_present and _DIAGNOSTIC_RELATION_RE.search(text):
            signals.add("candidate_diagnostic_relation_cooccurrence")
        if candidate_present and bool(unit.get("contains_scope_cue")):
            signals.add("candidate_scope_cue_cooccurrence")
    if _DIAGNOSTIC_SECTION_RE.search(" > ".join(str(item) for item in section_path)):
        signals.add("diagnostic_section_scope")
    return sorted(signals)


def requires_empty_confirmation(
    coverage_status: str, signal_codes: Sequence[str],
) -> bool:
    """True only for provisional empties that must bypass the success cache."""

    return coverage_status == "nothing_extractable" and bool(signal_codes)


def _materialize_exact_occurrence(
    *,
    surface_value: Any,
    occurrence_value: Any,
    mention: Mapping[str, Any],
    error_prefix: str,
) -> tuple[int, int, str, bool] | list[str]:
    """Resolve a model-selected exact quote occurrence to absolute offsets.

    The model never supplies numeric character offsets.  It selects a literal
    source surface and its 1-based occurrence within one closed evidence unit;
    this deterministic step is the only place where absolute offsets are
    created.  No fuzzy, case-folded, or nearest-occurrence repair is allowed.
    """

    if not isinstance(surface_value, str) or not surface_value:
        return [f"{error_prefix}_surface_required"]
    if surface_value != surface_value.strip():
        return [f"{error_prefix}_surface_not_trimmed"]
    if (
        not isinstance(occurrence_value, int)
        or isinstance(occurrence_value, bool)
        or occurrence_value < 1
    ):
        return [f"{error_prefix}_occurrence_index_invalid"]
    evidence_text = str(mention.get("text") or "")
    positions = [
        match.start()
        for match in re.finditer(re.escape(surface_value), evidence_text)
    ]
    occurrence_repaired = False
    if occurrence_value > len(positions):
        # A bad index carries no spatial information.  It is safe to ignore it
        # only when the exact, case-sensitive surface has one possible location
        # in the selected evidence unit.  Zero or repeated matches remain hard
        # failures; no nearest/first/fuzzy repair is permitted.
        if len(positions) != 1:
            return [f"{error_prefix}_occurrence_index_out_of_range"]
        local_start = positions[0]
        occurrence_repaired = True
    else:
        local_start = positions[occurrence_value - 1]
    absolute_start = int(mention["start_char"]) + local_start
    return (
        absolute_start,
        absolute_start + len(surface_value),
        surface_value,
        occurrence_repaired,
    )


def materialize_occurrence_offsets(
    slots: Sequence[Mapping[str, Any]],
    *,
    evidence_inventory: Sequence[Mapping[str, Any]],
    normalizations_out: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert exact-surface occurrence selectors into converter-ready slots.

    Any invalid selector rejects the entire response upstream.  Returning a
    list of per-slot errors keeps source prose out of rejection telemetry.
    """

    evidence_by_id = {
        str(item.get("mention_id") or ""): item
        for item in evidence_inventory
    }
    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for slot_index, raw_slot in enumerate(slots):
        if not isinstance(raw_slot, Mapping):
            rejected.append({
                "slot_index": slot_index,
                "errors": ["slot_not_object"],
            })
            break
        slot = dict(raw_slot)
        role = str(slot.get("diagnostic_role") or "")
        direction = ROLE_TO_DIRECTION.get(role)
        if direction is None:
            rejected.append({
                "slot_index": slot_index,
                "errors": ["direction_derivation_failed_invalid_diagnostic_role"],
            })
            break
        slot["direction"] = direction
        if normalizations_out is not None:
            normalizations_out.append({
                "slot_index": slot_index,
                "action": "direction_derived_from_diagnostic_role",
                "diagnostic_role": role,
                "normalized_value": direction,
            })
        mention_id = str(slot.get("evidence_mention_id") or "")
        mention = evidence_by_id.get(mention_id)
        if mention is None:
            rejected.append({
                "slot_index": slot_index,
                "errors": ["evidence_mention_id_not_in_inventory"],
            })
            break
        feature = _materialize_exact_occurrence(
            surface_value=slot.get("feature_surface"),
            occurrence_value=slot.get("feature_occurrence_index"),
            mention=mention,
            error_prefix="feature",
        )
        if isinstance(feature, list):
            rejected.append({"slot_index": slot_index, "errors": feature})
            break
        feature_start, feature_end, feature_surface, feature_repaired = feature
        requested_feature_occurrence = slot.get("feature_occurrence_index")
        slot.pop("feature_occurrence_index", None)
        slot.update({
            "feature_surface": feature_surface,
            "feature_start_char": feature_start,
            "feature_end_char": feature_end,
        })
        if feature_repaired and normalizations_out is not None:
            normalizations_out.append({
                "slot_index": slot_index,
                "action": "occurrence_index_repaired_unique_exact_surface",
                "field": "feature_occurrence_index",
                "evidence_mention_id": mention_id,
                "requested_value": requested_feature_occurrence,
                "normalized_value": 1,
            })

        logic_operator = str(slot.get("logic_operator") or "atomic")
        raw_components = slot.get("feature_components") or []
        if logic_operator == "atomic":
            # Required-but-redundant component arrays have no semantic role for
            # atomic assertions; the exact top-level selector is authoritative.
            slot["feature_components"] = []
        else:
            if not isinstance(raw_components, list):
                rejected.append({
                    "slot_index": slot_index,
                    "errors": ["feature_components_not_list"],
                })
                break
            components: list[dict[str, Any]] = []
            component_errors: list[str] = []
            for component_index, raw_component in enumerate(raw_components):
                if not isinstance(raw_component, Mapping):
                    component_errors.append(
                        f"component_{component_index}_not_object"
                    )
                    continue
                component = dict(raw_component)
                resolved = _materialize_exact_occurrence(
                    surface_value=component.get("feature_surface"),
                    occurrence_value=component.get("feature_occurrence_index"),
                    mention=mention,
                    error_prefix=f"component_{component_index}",
                )
                if isinstance(resolved, list):
                    component_errors.extend(resolved)
                    continue
                start, end, surface, component_repaired = resolved
                requested_component_occurrence = component.get(
                    "feature_occurrence_index"
                )
                component.pop("feature_occurrence_index", None)
                component.update({
                    "feature_surface": surface,
                    "feature_start_char": start,
                    "feature_end_char": end,
                })
                if component_repaired and normalizations_out is not None:
                    normalizations_out.append({
                        "slot_index": slot_index,
                        "component_index": component_index,
                        "action": "occurrence_index_repaired_unique_exact_surface",
                        "field": "component_occurrence_index",
                        "evidence_mention_id": mention_id,
                        "requested_value": requested_component_occurrence,
                        "normalized_value": 1,
                    })
                components.append(component)
            if component_errors:
                rejected.append({
                    "slot_index": slot_index,
                    "errors": component_errors,
                })
                break
            slot["feature_components"] = components
        materialized.append(slot)
    if rejected:
        return [], rejected
    return materialized, []


def _project_assertion_evidence(
    *,
    window: Mapping[str, Any],
    slot: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    assertion_id: str,
    passage_index: Mapping[str, Mapping[str, Any]],
    accumulator: RecordAccumulator,
    slot_new_ids: set[str],
) -> str:
    """Replace a converter's temporary window citation with source citations."""

    mention = evidence_by_id.get(str(slot.get("evidence_mention_id") or ""))
    if not mention:
        raise ClaimWindowError("evidence mention is absent from closed inventory")
    try:
        feature_start = int(slot.get("feature_start_char"))
        feature_end = int(slot.get("feature_end_char"))
    except (TypeError, ValueError) as exc:
        raise ClaimWindowError("feature offsets are required") from exc
    # A feature may cross an old chunk boundary separated only by inserted
    # whitespace.  Its assertion citation is then represented by multiple exact
    # source EvidenceSpans, never one fictional span across the delimiter.
    project_window_range(
        window, feature_start, feature_end, allow_unmapped_whitespace=True,
    )
    for component in slot.get("feature_components") or []:
        if str(slot.get("logic_operator") or "atomic") == "atomic":
            break
        project_window_range(
            window,
            int(component.get("feature_start_char")),
            int(component.get("feature_end_char")),
            allow_unmapped_whitespace=True,
        )
    projections = project_window_range(
        window, int(mention["start_char"]), int(mention["end_char"]),
        allow_unmapped_whitespace=True,
    )
    real_spans: list[str] = []
    for projection in projections:
        passage = passage_index[str(projection["passage_id"])]
        source_start = int(projection["passage_start_char"])
        source_end = int(projection["passage_end_char"])
        quote = str(passage["text"])[source_start:source_end]
        span = accumulator.add(EvidenceSpan(
            passage_id=str(passage["id"]),
            start_char=source_start,
            end_char=source_end,
            quote=quote,
            # Keep this identical to deterministic/template citations so an
            # already-present exact span deduplicates without a stable-ID
            # collision.  Window lineage belongs to the assertion/activity.
            extensions={"quote_sha256": sha256_text(quote)},
        ))
        real_spans.append(str(span["id"]))

    assertion = dict(accumulator.records[assertion_id])
    temporary_span_ids = list(assertion.get("evidence_span_ids") or [])
    accumulator.records.pop(assertion_id, None)
    for span_id in temporary_span_ids:
        if span_id in slot_new_ids:
            accumulator.records.pop(span_id, None)
    assertion["evidence_span_ids"] = real_spans
    extensions = dict(assertion.get("extensions") or {})
    extensions["claim_window_provenance"] = {
        "window_id": window["window_id"],
        "rechunker_version": window["rechunker_version"],
        "window_sha256": window["text_sha256"],
        "offset_map_sha256": window["offset_map_sha256"],
    }
    assertion["extensions"] = extensions
    assertion["id"] = stable_id_for(assertion)
    return str(accumulator.add(assertion)["id"])


def convert_claim_window_slots(
    window: Mapping[str, Any],
    slots: Sequence[Mapping[str, Any]],
    *,
    candidate_inventory: Sequence[Mapping[str, str]],
    evidence_inventory: Sequence[Mapping[str, Any]],
    activity_id: str,
    accumulator: RecordAccumulator,
    passage_index: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Compile slots against window offsets, then atomically source-project."""

    conversion_delta = accumulator.begin_delta()
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    evidence_by_id = {
        str(item["mention_id"]): item for item in evidence_inventory
    }
    synthetic_passage = {
        "id": window["window_id"],
        "record_type": "Passage",
        "text": window["text"],
        "extensions": {
            **dict(window.get("metadata") or {}),
            "section_path": claim_window_section_context(window),
        },
    }
    for slot_index, slot in enumerate(slots):
        slot_delta = accumulator.begin_delta()
        slot_accepted, slot_rejected = convert_validated_llm_slots(
            synthetic_passage, [slot],
            candidate_inventory=candidate_inventory,
            evidence_inventory=evidence_inventory,
            activity_id=activity_id,
            accumulator=accumulator,
        )
        if slot_rejected or len(slot_accepted) != 1:
            accumulator.rollback_delta(slot_delta)
            rejected.extend({
                **item, "slot_index": slot_index,
            } for item in slot_rejected or [{"errors": ["slot_not_compiled"]}])
            break
        try:
            accepted.append(_project_assertion_evidence(
                window=window,
                slot=slot,
                evidence_by_id=evidence_by_id,
                assertion_id=slot_accepted[0],
                passage_index=passage_index,
                accumulator=accumulator,
                slot_new_ids=set(accumulator.delta_ids(slot_delta)),
            ))
        except (ClaimWindowError, KeyError, TypeError, ValueError) as exc:
            accumulator.rollback_delta(slot_delta)
            rejected.append({
                "slot_index": slot_index,
                "errors": [f"source_projection_failed:{type(exc).__name__}"],
            })
            break
        else:
            accumulator.commit_delta(slot_delta)
    if rejected:
        accumulator.rollback_delta(conversion_delta)
        return [], rejected
    accumulator.commit_delta(conversion_delta)
    return accepted, []


def cache_key(
    *, semantic_unit: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]], messages: Sequence[Mapping[str, str]],
    prompt_token_estimates: Mapping[str, int], models: Sequence[str],
    args: argparse.Namespace,
) -> str:
    semantic_mode = str(semantic_unit.get("semantic_mode") or "claim_window")
    value = {
        "pipeline": f"{PIPELINE_NAME}@{PIPELINE_VERSION}",
        "schema_sha256": hashlib.sha256(canonical_json(RESPONSE_SCHEMA).encode()).hexdigest(),
        "prompt_sha256": PROMPT_SHA256,
        "rendered_messages_sha256": hashlib.sha256(
            canonical_json(messages).encode("utf-8")
        ).hexdigest(),
        "rendered_prompt_token_estimates": dict(prompt_token_estimates),
        "semantic_mode": semantic_mode,
        "semantic_unit_id": semantic_unit["id"],
        "semantic_unit_sha256": sha256_text(str(semantic_unit.get("text") or "")),
        "candidate_inventory_sha256": hashlib.sha256(canonical_json(candidates).encode()).hexdigest(),
        "evidence_inventory_sha256": hashlib.sha256(canonical_json(evidence).encode()).hexdigest(),
        "ontology_snapshot_sha256": file_sha256(args.disease_aliases),
        "models": list(models),
        "structured_output": args.structured_output,
        "provider_routing": {
            "sort": getattr(args, "provider_sort", "throughput"),
            "data_collection": getattr(
                args, "provider_data_collection", "deny"
            ),
            "strict_require_parameters": bool(
                getattr(args, "strict_require_parameters", True)
            ),
        },
        "max_input_tokens": args.max_input_tokens,
        "max_source_tokens": args.max_source_tokens,
        "soft_rendered_prompt_tokens": args.soft_rendered_prompt_tokens,
        "max_output_tokens": args.max_output_tokens,
        "temperature": 0,
    }
    if semantic_mode == "claim_window":
        value.update({
            "rechunker_version": semantic_unit["rechunker_version"],
            "window_sha256": semantic_unit["text_sha256"],
            "offset_map_sha256": semantic_unit["offset_map_sha256"],
        })
    else:
        value["legacy_passage_unit"] = True
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def response_usage(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") or {}
    if not isinstance(usage, Mapping):
        usage = {}
    return {
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
        "cached_tokens": int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        "cost": usage.get("cost"),
    }


class ProviderJob(NamedTuple):
    """One semantic unit whose physical provider attempts may run in a worker."""

    prepared_index: int
    semantic_call: int
    prepared_call: Mapping[str, Any]
    reservation_tokens: int


class ProviderCallResult(NamedTuple):
    """Provider-only result; graph/cache mutation is deliberately absent."""

    prepared_index: int
    semantic_call: int
    response_object: dict[str, Any] | None
    response_model: str | None
    telemetry_rows: list[dict[str, Any]]
    provider_reported_tokens: int
    budget_accounted_tokens: int
    completed_monotonic: float


def worst_case_provider_reservation(
    prompt_token_estimates: Mapping[str, int],
    *,
    models: Sequence[str],
    structured_modes: Sequence[str],
    max_attempts_per_model: int,
    max_output_tokens: int,
) -> int:
    """Reserve every physically possible fallback/retry before dispatch.

    This is intentionally more conservative than reserving one nominal call:
    a semantic unit may consume a strict-schema request, its retry, a JSON-mode
    fallback, and the same sequence on a fallback model.  Reservations are
    released and reconciled against usage as each unit completes.
    """

    if not models or not structured_modes:
        raise ValueError("at least one model and structured mode are required")
    if max_attempts_per_model < 1 or max_output_tokens < 0:
        raise ValueError("invalid provider reservation parameters")
    total = 0
    for _model in models:
        for mode in structured_modes:
            estimated_input = int(prompt_token_estimates.get(mode, 0))
            if estimated_input < 1:
                raise ValueError(f"missing positive prompt estimate for {mode!r}")
            total += max_attempts_per_model * (
                estimated_input + max_output_tokens
            )
    return total


def _accounted_attempt_tokens(
    usage: Mapping[str, Any],
    *,
    estimated_input_tokens: int,
    max_output_tokens: int,
    status: int | None,
    provider_success: bool,
) -> int:
    """Use provider usage when present and a safe upper bound when unknowable."""

    reported = int(usage.get("input_tokens") or 0) + int(
        usage.get("output_tokens") or 0
    )
    if reported:
        return reported
    # These failures occur before a completion is generated and are normally
    # uncharged.  Network/5xx/parse failures are ambiguous, so retain the full
    # per-attempt reservation instead of silently treating them as free.
    pre_generation_statuses = {400, 401, 402, 403, 404, 409, 422, 429}
    if not provider_success and status in pre_generation_statuses:
        return 0
    return estimated_input_tokens + max_output_tokens


def run_provider_job(
    job: ProviderJob,
    *,
    api_key: str,
    models: Sequence[str],
    structured_modes: Sequence[str],
    max_attempts_per_model: int,
    max_output_tokens: int,
    timeout_seconds: int,
    soft_rendered_prompt_tokens: int,
    provider_sort: str = "throughput",
    provider_data_collection: str = "deny",
    strict_require_parameters: bool = True,
    post_fn: Callable[..., tuple[dict[str, Any], str]] = post_openrouter,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ProviderCallResult:
    """Run only network/fallback/retry work for one semantic call.

    The function neither touches files nor mutates RecordAccumulator.  This is
    the only function submitted to the thread pool.
    """

    prepared_call = job.prepared_call
    semantic_mode = str(prepared_call["semantic_mode"])
    semantic_unit_id = str(prepared_call["semantic_unit_id"])
    semantic_unit = prepared_call["semantic_unit"]
    evidence = prepared_call["evidence"]
    evidence_unit_mode = str(prepared_call["evidence_unit_mode"])
    messages = prepared_call["messages"]
    source_tokens = int(prepared_call["source_tokens"])
    prompt_token_estimates = dict(prepared_call["prompt_token_estimates"])
    estimated_worst_input = int(
        prepared_call["rendered_prompt_tokens_worst_case"]
    )
    key = str(prepared_call["cache_key"])
    response_object: dict[str, Any] | None = None
    response_model: str | None = None
    telemetry_rows: list[dict[str, Any]] = []
    provider_reported_tokens = 0
    budget_accounted_tokens = 0
    physical_attempt_index = 0

    for model in models:
        if response_object is not None:
            break
        for mode_index, structured_mode in enumerate(structured_modes):
            if response_object is not None:
                break
            for attempt in range(1, max_attempts_per_model + 1):
                physical_attempt_index += 1
                started = time.monotonic()
                telemetry: dict[str, Any] = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "pipeline": f"{PIPELINE_NAME}@{PIPELINE_VERSION}",
                    "semantic_mode": semantic_mode,
                    "semantic_unit_id": semantic_unit_id,
                    "cache_key": key,
                    "prompt_sha256": PROMPT_SHA256,
                    "semantic_unit_sha256": sha256_text(
                        str(semantic_unit.get("text") or "")
                    ),
                    "requested_model": model,
                    "structured_mode": structured_mode,
                    "semantic_call": job.semantic_call,
                    "physical_attempt": attempt,
                    "physical_attempt_index": physical_attempt_index,
                    "estimated_source_tokens": source_tokens,
                    "estimated_rendered_prompt_tokens_for_mode": (
                        prompt_token_estimates[structured_mode]
                    ),
                    "estimated_rendered_prompt_tokens_worst_case": (
                        estimated_worst_input
                    ),
                    "semantic_call_reserved_tokens": job.reservation_tokens,
                    "evidence_unit_mode": evidence_unit_mode,
                    "evidence_unit_count": len(evidence),
                    "prompt_soft_limit_exceeded": (
                        estimated_worst_input > soft_rendered_prompt_tokens
                    ),
                    "provider_sort": provider_sort,
                    "provider_data_collection": provider_data_collection,
                    "provider_require_parameters": (
                        bool(strict_require_parameters)
                        if structured_mode == "json_schema" else None
                    ),
                }
                if semantic_mode == "claim_window":
                    telemetry.update({
                        "rechunker_version": semantic_unit["rechunker_version"],
                        "offset_map_sha256": semantic_unit["offset_map_sha256"],
                    })
                try:
                    payload, _used_mode = post_fn(
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        max_output_tokens=max_output_tokens,
                        structured_mode=structured_mode,
                        timeout_seconds=timeout_seconds,
                        provider_sort=provider_sort,
                        provider_data_collection=provider_data_collection,
                        strict_require_parameters=strict_require_parameters,
                    )
                    response_object = payload["_parsed_content"]
                    response_model = str(payload.get("model") or model)
                    usage = response_usage(payload)
                    reported = usage["input_tokens"] + usage["output_tokens"]
                    accounted = _accounted_attempt_tokens(
                        usage,
                        estimated_input_tokens=prompt_token_estimates[structured_mode],
                        max_output_tokens=max_output_tokens,
                        status=None,
                        provider_success=True,
                    )
                    provider_reported_tokens += reported
                    budget_accounted_tokens += accounted
                    telemetry.update({
                        "status": "provider_success",
                        "returned_model": response_model,
                        "provider": payload.get("provider"),
                        "finish_reason": (
                            payload.get("choices") or [{}]
                        )[0].get("finish_reason"),
                        "budget_accounted_tokens": accounted,
                        **usage,
                    })
                    telemetry_rows.append({
                        **telemetry,
                        "latency_seconds": round(time.monotonic() - started, 4),
                    })
                    break
                except OpenRouterError as exc:
                    usage = response_usage(exc.response_payload)
                    reported = usage["input_tokens"] + usage["output_tokens"]
                    accounted = _accounted_attempt_tokens(
                        usage,
                        estimated_input_tokens=prompt_token_estimates[structured_mode],
                        max_output_tokens=max_output_tokens,
                        status=exc.status,
                        provider_success=False,
                    )
                    provider_reported_tokens += reported
                    budget_accounted_tokens += accounted
                    telemetry.update({
                        "status": "provider_error",
                        "http_status": exc.status,
                        "error_class": type(exc).__name__,
                        "error_category": exc.error_category,
                        "error_sha256": sha256_text(str(exc)),
                        "returned_model": exc.response_payload.get("model"),
                        "provider": exc.response_payload.get("provider"),
                        "retry_after_seconds": exc.retry_after,
                        "budget_accounted_tokens": accounted,
                        **usage,
                    })
                    nonretryable = exc.status in {400, 401, 402, 403}
                    structured_unsupported = (
                        exc.status == 400 and structured_mode == "json_schema"
                    )
                    retry_delay: float | None = None
                    if (
                        not nonretryable
                        and attempt < max_attempts_per_model
                    ):
                        retry_delay = min(
                            max(exc.retry_after if exc.retry_after is not None else 2.0, 0.0),
                            60.0,
                        )
                        telemetry["retry_sleep_seconds"] = retry_delay
                    telemetry_rows.append({
                        **telemetry,
                        "latency_seconds": round(time.monotonic() - started, 4),
                    })
                    if structured_unsupported and mode_index + 1 < len(structured_modes):
                        break
                    if nonretryable:
                        break
                    if retry_delay is not None:
                        sleep_fn(retry_delay)

    return ProviderCallResult(
        prepared_index=job.prepared_index,
        semantic_call=job.semantic_call,
        response_object=response_object,
        response_model=response_model,
        telemetry_rows=telemetry_rows,
        provider_reported_tokens=provider_reported_tokens,
        budget_accounted_tokens=budget_accounted_tokens,
        completed_monotonic=time.monotonic(),
    )


def _unexpected_provider_failure(
    job: ProviderJob, exc: BaseException,
) -> ProviderCallResult:
    """Turn a worker crash into a source-free, conservatively charged result."""

    prepared_call = job.prepared_call
    semantic_unit = prepared_call["semantic_unit"]
    telemetry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline": f"{PIPELINE_NAME}@{PIPELINE_VERSION}",
        "semantic_mode": prepared_call["semantic_mode"],
        "semantic_unit_id": prepared_call["semantic_unit_id"],
        "cache_key": prepared_call["cache_key"],
        "prompt_sha256": PROMPT_SHA256,
        "semantic_unit_sha256": sha256_text(str(semantic_unit.get("text") or "")),
        "semantic_call": job.semantic_call,
        "status": "provider_worker_exception",
        "error_class": type(exc).__name__,
        "error_sha256": sha256_text(str(exc)),
        "semantic_call_reserved_tokens": job.reservation_tokens,
        "budget_accounted_tokens": job.reservation_tokens,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "cost": None,
        "latency_seconds": None,
    }
    return ProviderCallResult(
        prepared_index=job.prepared_index,
        semantic_call=job.semantic_call,
        response_object=None,
        response_model=None,
        telemetry_rows=[telemetry],
        provider_reported_tokens=0,
        budget_accounted_tokens=job.reservation_tokens,
        completed_monotonic=time.monotonic(),
    )


def execute_provider_jobs(
    jobs: Sequence[ProviderJob],
    *,
    workers: int,
    budget_total_tokens: int,
    worker_fn: Callable[[ProviderJob], ProviderCallResult],
    completion_callback: Callable[[ProviderCallResult], None] | None = None,
) -> tuple[
    dict[int, ProviderCallResult], int, int, list[int], dict[str, int]
]:
    """Dispatch provider-only work under a strict in-flight reservation gate.

    Results are keyed by ``prepared_index`` so downstream graph conversion can
    run in the original prepared order even when network calls finish out of
    order.  The callback executes only in this coordinating (main) thread.
    """

    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    if budget_total_tokens < 0:
        raise ValueError("budget_total_tokens must be nonnegative")
    results: dict[int, ProviderCallResult] = {}
    budget_accounted = 0
    provider_reported = 0
    reserved_inflight = 0
    max_reserved_inflight = 0
    stopped: list[int] = []
    next_job = 0
    submitted = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        inflight: dict[Future[ProviderCallResult], ProviderJob] = {}
        while next_job < len(jobs) or inflight:
            while next_job < len(jobs) and len(inflight) < workers:
                job = jobs[next_job]
                if (
                    budget_accounted
                    + reserved_inflight
                    + job.reservation_tokens
                    > budget_total_tokens
                ):
                    break
                future = executor.submit(worker_fn, job)
                inflight[future] = job
                reserved_inflight += job.reservation_tokens
                max_reserved_inflight = max(
                    max_reserved_inflight, reserved_inflight
                )
                submitted += 1
                next_job += 1

            if not inflight:
                # Prepared-order admission: never skip an unaffordable job to
                # cherry-pick a cheaper later semantic unit.
                stopped.extend(job.prepared_index for job in jobs[next_job:])
                break

            done, _pending = wait(inflight, return_when=FIRST_COMPLETED)
            completed: list[ProviderCallResult] = []
            for future in done:
                job = inflight.pop(future)
                reserved_inflight -= job.reservation_tokens
                try:
                    result = future.result()
                except BaseException as exc:  # executor isolation boundary
                    result = _unexpected_provider_failure(job, exc)
                completed.append(result)
            completed.sort(key=lambda item: item.completed_monotonic)
            for result in completed:
                results[result.prepared_index] = result
                budget_accounted += result.budget_accounted_tokens
                provider_reported += result.provider_reported_tokens
                if completion_callback is not None:
                    completion_callback(result)

    scheduler_stats = {
        "provider_jobs_planned": len(jobs),
        "provider_jobs_submitted": submitted,
        "provider_jobs_budget_stopped": len(stopped),
        "max_reserved_inflight_tokens": max_reserved_inflight,
    }
    return results, budget_accounted, provider_reported, stopped, scheduler_stats


def validate_response_envelope(value: Mapping[str, Any]) -> list[str]:
    """Minimal local JSON-Schema enforcement for json_object fallbacks."""

    errors: list[str] = []
    expected_keys = {"assertions", "coverage_status"}
    if set(value) != expected_keys:
        errors.append("top_level_keys_must_equal_status_and_assertions_contract")
    assertions = value.get("assertions")
    if not isinstance(assertions, list):
        return [*errors, "assertions_not_list"]
    if len(assertions) > MAX_ASSERTIONS_PER_CALL:
        errors.append("assertions_exceeds_max_items")
    coverage_status = value.get("coverage_status")
    if coverage_status not in ALL_COVERAGE_STATUSES:
        errors.append("invalid_coverage_status")
    if coverage_status != "complete" and assertions:
        errors.append("noncomplete_coverage_must_not_return_partial_assertions")
    if coverage_status == "complete" and not assertions:
        errors.append("empty_complete_response_must_use_nothing_extractable")
    item_schema = RESPONSE_SCHEMA["properties"]["assertions"]["items"]
    required = set(item_schema["required"])
    allowed = set(item_schema["properties"])
    for index, item in enumerate(assertions):
        if not isinstance(item, Mapping):
            errors.append(f"assertions[{index}]_not_object")
            continue
        missing = required - set(item)
        extra = set(item) - allowed
        if missing:
            errors.append(f"assertions[{index}]_missing:{','.join(sorted(missing))}")
        if extra:
            errors.append(f"assertions[{index}]_extra:{','.join(sorted(extra))}")
        logic_operator = item.get("logic_operator")
        k_value = item.get("k")
        if logic_operator == "k_of_n":
            if (
                not isinstance(k_value, int)
                or isinstance(k_value, bool)
                or k_value < 1
            ):
                errors.append(f"assertions[{index}]_k_of_n_requires_positive_k")
        elif (
            not isinstance(k_value, int)
            or isinstance(k_value, bool)
            or k_value != 0
        ):
            errors.append(f"assertions[{index}]_non_k_of_n_requires_k_zero")
        components = item.get("feature_components")
        if not isinstance(components, list):
            errors.append(f"assertions[{index}]_feature_components_not_list")
            continue
        component_schema = item_schema["properties"]["feature_components"]["items"]
        component_required = set(component_schema["required"])
        component_allowed = set(component_schema["properties"])
        for component_index, component in enumerate(components):
            if not isinstance(component, Mapping):
                errors.append(
                    f"assertions[{index}]_components[{component_index}]_not_object"
                )
                continue
            component_missing = component_required - set(component)
            component_extra = set(component) - component_allowed
            if component_missing:
                errors.append(
                    f"assertions[{index}]_components[{component_index}]_missing:"
                    + ",".join(sorted(component_missing))
                )
            if component_extra:
                errors.append(
                    f"assertions[{index}]_components[{component_index}]_extra:"
                    + ",".join(sorted(component_extra))
                )
    return errors


def _row_source(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    return str(
        row.get("source") or row.get("source_family")
        or metadata.get("source") or metadata.get("source_family") or "unknown"
    )


def _row_id(row: Mapping[str, Any]) -> str:
    return str(
        row.get("window_id") or row.get("id") or row.get("passage_id") or ""
    )


def load_included_unit_ids(paths: Sequence[Path] | None) -> set[str]:
    """Load only semantic-unit IDs from source-free replay ledgers."""

    result: set[str] = set()
    for path in paths or []:
        for line_number, row in enumerate(load_jsonl(path), start=1):
            semantic_unit_id = row.get("semantic_unit_id")
            if not isinstance(semantic_unit_id, str) or not semantic_unit_id.strip():
                raise ValueError(
                    f"{path}:{line_number}: replay ledger requires semantic_unit_id"
                )
            result.add(semantic_unit_id.strip())
    return result


def _claim_window_eligible(row: Mapping[str, Any]) -> bool:
    quarantine = row.get("quarantine")
    if quarantine not in (None, False, "", [], {}):
        return False
    status = row.get("status")
    if status is not None and str(status).casefold() not in {
        "eligible", "ready", "admitted", "llm_eligible",
    }:
        return False
    eligibility = row.get("eligibility")
    if eligibility is None:
        return True
    if isinstance(eligibility, bool):
        return eligibility
    if isinstance(eligibility, Mapping):
        if eligibility.get("eligible") is False:
            return False
        eligibility = eligibility.get("status", "eligible")
    return str(eligibility).casefold() in {
        "eligible", "ready", "admitted", "true", "llm_eligible",
    }


def select_queue(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    included_unit_ids = load_included_unit_ids(
        getattr(args, "include_unit_ids_from", None)
    )
    if included_unit_ids:
        rows = [row for row in rows if _row_id(row) in included_unit_ids]
    rows = [
        row for row in rows
        if int(row.get("priority", row.get("residual_priority", 0)) or 0)
        >= args.min_residual_priority
    ]
    if args.source:
        wanted = {value.casefold() for value in args.source}
        rows = [row for row in rows if _row_source(row).casefold() in wanted]
    rows.sort(key=lambda row: (
        -int(row.get("priority", row.get("residual_priority", 0)) or 0),
        _row_id(row),
    ))
    if args.sample_seed is not None:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[_row_source(row)].append(row)
        rng = random.Random(args.sample_seed)
        for group in grouped.values():
            rng.shuffle(group)
        interleaved: list[dict[str, Any]] = []
        while any(grouped.values()):
            for source in sorted(grouped):
                if grouped[source]:
                    interleaved.append(grouped[source].pop())
        rows = interleaved
    return rows[:args.limit] if args.limit is not None else rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    semantic_input = parser.add_mutually_exclusive_group()
    semantic_input.add_argument(
        "--claim-windows", type=Path, default=DEFAULT_CLAIM_WINDOWS,
        help="claim-aware window JSONL (default semantic unit)",
    )
    semantic_input.add_argument(
        "--legacy-passage-queue", type=Path,
        help=(
            "LEGACY ONLY: residual_queue.jsonl for one-Passage-per-call; "
            "never selected by default"
        ),
    )
    parser.add_argument("--disease-aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--primary-model", default=DEFAULT_MODEL)
    parser.add_argument("--fallback-model", default=DEFAULT_FALLBACK)
    parser.add_argument("--source", action="append")
    parser.add_argument(
        "--include-unit-ids-from", type=Path, action="append",
        help=(
            "source-free needs_review/rejection JSONL; select rows only by "
            "semantic_unit_id (repeatable)"
        ),
    )
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--sample-seed", type=int, default=20260825)
    parser.add_argument("--min-residual-priority", type=int, default=0)
    parser.add_argument("--max-evidence-units", type=int, default=160)
    parser.add_argument("--max-evidence-sentences", type=int, default=320)
    parser.add_argument("--max-source-tokens", type=int, default=6000)
    parser.add_argument("--soft-rendered-prompt-tokens", type=int, default=10000)
    parser.add_argument("--max-input-tokens", type=int, default=12000)
    parser.add_argument(
        "--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS,
    )
    parser.add_argument("--max-attempts-per-model", type=int, default=2)
    parser.add_argument("--budget-total-tokens", type=int, default=500000)
    parser.add_argument(
        "--workers", type=int, default=1,
        help=(
            "concurrent physical OpenRouter calls (1-8); graph conversion, "
            "validation, cache writes, and output remain deterministic/main-thread"
        ),
    )
    parser.add_argument("--structured-output", choices=("required", "prefer"), default="prefer")
    parser.add_argument(
        "--provider-sort", choices=("throughput", "latency", "price"),
        default="throughput",
        help="OpenRouter provider ordering; no provider slug is pinned",
    )
    parser.add_argument(
        "--provider-data-collection", choices=("deny", "allow"), default="deny",
    )
    parser.add_argument(
        "--strict-require-parameters",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "set OpenRouter provider.require_parameters for json_schema calls "
            "(default: true)"
        ),
    )
    parser.add_argument(
        "--private-rejection-output", type=Path,
        help=(
            "optional mode-0600 JSONL containing raw rejected model objects; "
            "never copied into public telemetry"
        ),
    )
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not 1 <= args.max_attempts_per_model <= 2:
        parser.error("--max-attempts-per-model must be 1 or 2")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    if args.max_input_tokens < 1000:
        parser.error("token caps are implausibly small")
    if args.max_output_tokens < MIN_OUTPUT_TOKENS:
        parser.error(
            f"--max-output-tokens must be at least {MIN_OUTPUT_TOKENS} for "
            f"{MAX_ASSERTIONS_PER_CALL} assertions x "
            f"{OUTPUT_TOKENS_PER_ASSERTION_FLOOR} tokens plus "
            f"{OUTPUT_ENVELOPE_RESERVE_TOKENS} envelope tokens"
        )
    if not 1000 <= args.max_source_tokens <= args.max_input_tokens:
        parser.error("--max-source-tokens must be between 1000 and --max-input-tokens")
    if not args.max_source_tokens <= args.soft_rendered_prompt_tokens <= args.max_input_tokens:
        parser.error(
            "--soft-rendered-prompt-tokens must be between source and hard input caps"
        )
    if args.max_evidence_units < 1 or args.max_evidence_sentences < 1:
        parser.error("evidence-unit and sentence-subspan caps must be positive")

    base_records = load_jsonl(args.graph)
    assert_valid_graph(base_records)
    index = {record["id"]: record for record in base_records}
    legacy_mode = args.legacy_passage_queue is not None
    semantic_input_path = (
        args.legacy_passage_queue if legacy_mode else args.claim_windows
    )
    assert semantic_input_path is not None
    queue = select_queue(load_jsonl(semantic_input_path), args)
    aliases = load_disease_aliases(args.disease_aliases)
    models = [args.primary_model]
    if args.fallback_model and args.fallback_model not in models:
        models.append(args.fallback_model)
    structured_modes = ["json_schema"]
    if args.structured_output == "prefer":
        structured_modes.append("json_object")

    preflight: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    for row in queue:
        window: dict[str, Any] | None = None
        if legacy_mode:
            passage = index.get(str(row.get("passage_id")))
            if not passage or passage.get("record_type") != "Passage":
                preflight.append({
                    "semantic_mode": "legacy_passage", "semantic_unit_id": row.get("passage_id"),
                    "status": "missing_passage",
                })
                continue
            semantic_mode = "legacy_passage"
            semantic_unit_id = str(passage["id"])
            text_record = passage
            candidates = llm_candidate_inventory(passage, aliases)
            section_path = passage_metadata(passage).get("section_path", [])
            semantic_unit = {
                "semantic_mode": semantic_mode, "id": semantic_unit_id,
                "text": str(passage.get("text") or ""),
            }
        else:
            if not _claim_window_eligible(row):
                preflight.append({
                    "semantic_mode": "claim_window", "semantic_unit_id": _row_id(row),
                    "status": "quarantined_by_rechunker",
                })
                continue
            try:
                window = normalize_claim_window(row, index)
            except ClaimWindowError as exc:
                preflight.append({
                    "semantic_mode": "claim_window", "semantic_unit_id": _row_id(row),
                    "status": "invalid_claim_window", "detail": str(exc),
                })
                continue
            semantic_mode = "claim_window"
            semantic_unit_id = str(window["window_id"])
            text_record = {
                "id": semantic_unit_id, "record_type": "Passage", "text": window["text"],
                "extensions": {
                    **dict(window.get("metadata") or {}),
                    "section_path": claim_window_section_context(window),
                },
            }
            candidates = claim_window_candidate_inventory(window, index, aliases)
            section_path = claim_window_section_context(window)
            semantic_unit = {
                "semantic_mode": semantic_mode, "id": semantic_unit_id,
                "text": window["text"],
                "rechunker_version": window["rechunker_version"],
                "text_sha256": window["text_sha256"],
                "offset_map_sha256": window["offset_map_sha256"],
            }
        if not candidates:
            preflight.append({
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "status": "no_target_candidates",
            })
            continue
        source_tokens, source_tokenizer = count_tokens(str(text_record.get("text") or ""))
        if source_tokens > args.max_source_tokens:
            preflight.append({
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "status": "source_window_overflow_no_truncation",
                "source_tokens": source_tokens,
                "source_tokenizer": source_tokenizer,
                "max_source_tokens": args.max_source_tokens,
            })
            continue
        try:
            if window is not None:
                evidence, evidence_unit_mode = claim_window_evidence_inventory(
                    window,
                    max_units=args.max_evidence_units,
                    max_sentence_subspans=args.max_evidence_sentences,
                )
                context_only = claim_window_context_inventory(window)
            else:
                evidence = [
                    {**item, "unit_type": "legacy_passage_sentence"}
                    for item in evidence_sentence_inventory(
                        text_record, max_sentences=args.max_evidence_sentences,
                    )
                ]
                evidence_unit_mode = "legacy_passage_sentence"
                context_only = []
        except (ClaimWindowError, ValueError) as exc:
            preflight.append({
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "status": "requires_claim_window_resplit",
                "detail": str(exc),
            })
            continue
        empty_signal_codes = empty_confirmation_signals(
            evidence_inventory=evidence,
            candidate_inventory=candidates,
            section_path=[str(item) for item in section_path],
        )
        payload = {
            "claim_window_id" if not legacy_mode else "legacy_passage_id": semantic_unit_id,
            "section_path": section_path,
            "TARGET_CANDIDATES": candidates,
            "CONTEXT_ONLY": prompt_context_inventory(context_only),
            "EVIDENCE_UNITS": prompt_evidence_inventory(evidence),
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": canonical_json(payload)},
        ]
        prompt_token_estimates, prompt_tokenizer = rendered_prompt_token_estimates(
            messages, structured_modes,
        )
        rendered_prompt_tokens = max(prompt_token_estimates.values())
        if rendered_prompt_tokens > args.max_input_tokens:
            preflight.append({
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "status": "context_overflow_no_truncation",
                "source_tokens": source_tokens,
                "rendered_prompt_tokens_json_schema": prompt_token_estimates.get("json_schema"),
                "rendered_prompt_tokens_json_object": prompt_token_estimates.get("json_object"),
                "rendered_prompt_tokens_worst_case": rendered_prompt_tokens,
                "tokenizer": prompt_tokenizer,
            })
            continue
        key = cache_key(
            semantic_unit=semantic_unit, candidates=candidates, evidence=evidence,
            messages=messages, prompt_token_estimates=prompt_token_estimates,
            models=models, args=args,
        )
        prepared.append({
            "semantic_mode": semantic_mode,
            "semantic_unit_id": semantic_unit_id,
            "semantic_unit": semantic_unit,
            "passage": passage if legacy_mode else None,
            "window": window,
            "candidates": candidates,
            "evidence": evidence,
            "evidence_unit_mode": evidence_unit_mode,
            "empty_confirmation_signal_codes": empty_signal_codes,
            "messages": messages,
            "source_tokens": source_tokens,
            "prompt_token_estimates": prompt_token_estimates,
            "rendered_prompt_tokens_worst_case": rendered_prompt_tokens,
            "cache_key": key,
        })
        preflight.append({
            "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
            "status": "ready",
            "source_tokens": source_tokens,
            "rendered_prompt_tokens_json_schema": prompt_token_estimates.get("json_schema"),
            "rendered_prompt_tokens_json_object": prompt_token_estimates.get("json_object"),
            "rendered_prompt_tokens_worst_case": rendered_prompt_tokens,
            "tokenizer": prompt_tokenizer,
            "prompt_soft_limit_exceeded": (
                rendered_prompt_tokens > args.soft_rendered_prompt_tokens
            ),
            "candidate_count": len(candidates),
            "evidence_unit_count": len(evidence),
            "evidence_unit_mode": evidence_unit_mode,
            "empty_confirmation_signal_codes": empty_signal_codes,
            "cache_key": key,
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "preflight.jsonl").open("w", encoding="utf-8") as handle:
        for row in preflight:
            handle.write(canonical_json(row) + "\n")
    dry_summary = {
        "selected_queue_rows": len(queue),
        "ready_calls": len(prepared),
        "estimated_source_tokens": sum(row["source_tokens"] for row in prepared),
        "estimated_rendered_prompt_tokens_by_mode": {
            mode: sum(row["prompt_token_estimates"].get(mode, 0) for row in prepared)
            for mode in structured_modes
        },
        "estimated_rendered_prompt_tokens_worst_case": sum(
            row["rendered_prompt_tokens_worst_case"] for row in prepared
        ),
        "estimated_worst_case_provider_reservation_tokens": sum(
            worst_case_provider_reservation(
                row["prompt_token_estimates"],
                models=models,
                structured_modes=structured_modes,
                max_attempts_per_model=args.max_attempts_per_model,
                max_output_tokens=args.max_output_tokens,
            )
            for row in prepared
        ),
        "output_capacity_contract": {
            "schema_max_assertions": MAX_ASSERTIONS_PER_CALL,
            "configured_max_output_tokens": args.max_output_tokens,
            "envelope_reserve_tokens": OUTPUT_ENVELOPE_RESERVE_TOKENS,
            "per_assertion_token_floor": OUTPUT_TOKENS_PER_ASSERTION_FLOOR,
            "minimum_compatible_output_tokens": MIN_OUTPUT_TOKENS,
            "capacity_overflow_statuses": [
                "resplit_assertion_capacity", "resplit_output_capacity",
            ],
            "partial_complete_allowed": False,
        },
        "calls_above_prompt_soft_limit": sum(
            row["rendered_prompt_tokens_worst_case"] > args.soft_rendered_prompt_tokens
            for row in prepared
        ),
        "semantic_mode": "legacy_passage" if legacy_mode else "claim_window",
        "semantic_input": str(semantic_input_path),
        "models": models,
        "workers": args.workers,
        "provider_routing": {
            "sort": args.provider_sort,
            "data_collection": args.provider_data_collection,
            "strict_schema_require_parameters": args.strict_require_parameters,
        },
        "include_unit_ids_from": [
            str(path) for path in (args.include_unit_ids_from or [])
        ],
        "prompt_sha256": PROMPT_SHA256,
        "source_text_written_to_preflight": False,
    }
    if args.dry_run:
        print(json.dumps(dry_summary, indent=2))
        return 0

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key and not args.cache_only:
        parser.error("OPENROUTER_API_KEY is required unless --dry-run or --cache-only")

    additions_path = args.output_dir / "llm_records.jsonl"
    telemetry_path = args.output_dir / "attempt_telemetry.jsonl"
    errors_path = args.output_dir / "rejections.jsonl"
    resplit_path = args.output_dir / "needs_resplit.jsonl"
    review_path = args.output_dir / "needs_review.jsonl"
    manifest_path = args.output_dir / "manifest.json"
    private_rejection_path = args.private_rejection_output
    cache_dir = args.output_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    public_output_paths = (
        additions_path, telemetry_path, errors_path, resplit_path,
        review_path, manifest_path,
    )
    if private_rejection_path is not None and (
        private_rejection_path.resolve()
        in {path.resolve() for path in public_output_paths}
    ):
        parser.error("--private-rejection-output must not replace a public output")
    guarded_output_paths = [*public_output_paths]
    if private_rejection_path is not None:
        guarded_output_paths.append(private_rejection_path)
    if not args.resume and not args.force and any(
        path.exists() for path in guarded_output_paths
    ):
        parser.error("output exists; use --resume or --force")
    if args.force and not args.resume:
        # Files are replaced individually, never recursively deleting a directory.
        for path in guarded_output_paths:
            if path.exists():
                path.unlink()

    # The full base graph was validated above.  Per-call extraction treats it
    # as immutable and validates only the newly inserted records; one full
    # graph validation is retained after all calls as a defense-in-depth gate.
    accumulator = RecordAccumulator(
        base_records, merge_identity_metadata=False,
    )
    validation_index = GraphValidationIndex.from_validated_records(
        accumulator.records.values()
    )
    added_ids: list[str] = []
    totals = Counter()
    cached_results: dict[int, tuple[dict[str, Any], str]] = {}
    provider_jobs: list[ProviderJob] = []
    provider_job_by_cache_key: dict[str, int] = {}
    coalesced_provider_indexes: dict[int, int] = {}
    cache_only_misses: set[int] = set()
    cache_hits = 0
    for prepared_index, prepared_call in enumerate(prepared):
        key = str(prepared_call["cache_key"])
        cache_path = cache_dir / f"{key}.json"
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                cached = {}
            if (
                cached.get("status") == "validated_success"
                and isinstance(cached.get("response"), dict)
            ):
                cached_results[prepared_index] = (
                    cached["response"], str(cached.get("model") or "cache")
                )
                continue
        if args.cache_only:
            cache_only_misses.add(prepared_index)
            continue
        if key in provider_job_by_cache_key:
            coalesced_provider_indexes[prepared_index] = (
                provider_job_by_cache_key[key]
            )
            continue
        reservation = worst_case_provider_reservation(
            prepared_call["prompt_token_estimates"],
            models=models,
            structured_modes=structured_modes,
            max_attempts_per_model=args.max_attempts_per_model,
            max_output_tokens=args.max_output_tokens,
        )
        provider_jobs.append(ProviderJob(
            prepared_index=prepared_index,
            semantic_call=len(provider_jobs) + 1,
            prepared_call=prepared_call,
            reservation_tokens=reservation,
        ))
        provider_job_by_cache_key[key] = prepared_index

    def record_provider_completion(result: ProviderCallResult) -> None:
        # Called by the scheduler in the coordinating/main thread.  Individual
        # workers never append to a shared JSONL file.
        for telemetry in result.telemetry_rows:
            append_jsonl(telemetry_path, telemetry)
            status = str(telemetry.get("status") or "")
            if status in {"provider_success", "provider_error"}:
                totals["physical_attempts"] += 1
            if status:
                totals[status] += 1

    if provider_jobs:
        (
            provider_results,
            budget_accounted,
            provider_reported_tokens,
            budget_stopped,
            scheduler_stats,
        ) = execute_provider_jobs(
            provider_jobs,
            workers=args.workers,
            budget_total_tokens=args.budget_total_tokens,
            worker_fn=lambda job: run_provider_job(
                job,
                api_key=api_key,
                models=models,
                structured_modes=structured_modes,
                max_attempts_per_model=args.max_attempts_per_model,
                max_output_tokens=args.max_output_tokens,
                timeout_seconds=args.timeout_seconds,
                soft_rendered_prompt_tokens=args.soft_rendered_prompt_tokens,
                provider_sort=args.provider_sort,
                provider_data_collection=args.provider_data_collection,
                strict_require_parameters=args.strict_require_parameters,
            ),
            completion_callback=record_provider_completion,
        )
    else:
        provider_results = {}
        budget_accounted = 0
        provider_reported_tokens = 0
        budget_stopped = []
        scheduler_stats = {
            "provider_jobs_planned": 0,
            "provider_jobs_submitted": 0,
            "provider_jobs_budget_stopped": 0,
            "max_reserved_inflight_tokens": 0,
        }
    semantic_calls = scheduler_stats["provider_jobs_submitted"]
    budget_stopped_set = set(budget_stopped)
    totals["budget_stop"] += len(budget_stopped)

    # All stateful graph conversion, validation, success-cache writes, and
    # final output occur here in the immutable `prepared` order.
    for prepared_index, prepared_call in enumerate(prepared):
        if prepared_index in budget_stopped_set:
            break
        semantic_mode = str(prepared_call["semantic_mode"])
        semantic_unit_id = str(prepared_call["semantic_unit_id"])
        semantic_unit = prepared_call["semantic_unit"]
        passage = prepared_call["passage"]
        window = prepared_call["window"]
        candidates = prepared_call["candidates"]
        evidence = prepared_call["evidence"]
        evidence_unit_mode = str(prepared_call["evidence_unit_mode"])
        prompt_token_estimates = dict(prepared_call["prompt_token_estimates"])
        key = str(prepared_call["cache_key"])
        cache_path = cache_dir / f"{key}.json"
        response_object: dict[str, Any] | None = None
        response_model: str | None = None
        cached_result = cached_results.get(prepared_index)
        if cached_result is not None:
            response_object, response_model = cached_result
            cache_hits += 1
        elif prepared_index in cache_only_misses:
            append_jsonl(errors_path, {
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "error": "cache_miss",
            })
            totals["cache_miss"] += 1
            continue
        else:
            provider_result_index = coalesced_provider_indexes.get(
                prepared_index, prepared_index
            )
            provider_result = provider_results.get(provider_result_index)
            if provider_result is not None:
                response_object = provider_result.response_object
                response_model = provider_result.response_model
                if prepared_index in coalesced_provider_indexes:
                    cache_hits += 1
                    totals["inflight_cache_key_coalesced"] += 1

        if response_object is None:
            append_jsonl(errors_path, {
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "error": "all_models_failed", "cache_key": key,
            })
            totals["all_models_failed"] += 1
            continue
        response_digest = sha256_text(canonical_json(response_object))
        slots = response_object.get("assertions")
        envelope_errors = validate_response_envelope(response_object)
        if envelope_errors or not isinstance(slots, list):
            append_jsonl(errors_path, {
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "error": "invalid_response_envelope",
                "errors": envelope_errors, "cache_key": key,
                "response_sha256": response_digest,
            })
            append_private_rejection(
                private_rejection_path,
                semantic_mode=semantic_mode,
                semantic_unit_id=semantic_unit_id,
                cache_key_value=key,
                stage="invalid_response_envelope",
                response_object=response_object,
                rejections=[{"errors": envelope_errors}],
            )
            totals["invalid_response_shape"] += 1
            continue
        coverage_status = str(response_object.get("coverage_status") or "")
        if coverage_status in RESPLIT_COVERAGE_STATUSES:
            append_jsonl(resplit_path, {
                "semantic_mode": semantic_mode,
                "semantic_unit_id": semantic_unit_id,
                "cache_key": key,
                "coverage_status": coverage_status,
                "rechunker_version": semantic_unit.get("rechunker_version"),
                "window_sha256": semantic_unit.get("text_sha256"),
                "contains_source_text": False,
            })
            totals["needs_resplit"] += 1
            totals[coverage_status] += 1
            # A partial-capacity response is never a success cache entry and
            # never reaches the graph, even when its assertions array is empty.
            continue
        if coverage_status in REVIEW_COVERAGE_STATUSES:
            append_jsonl(review_path, {
                "semantic_mode": semantic_mode,
                "semantic_unit_id": semantic_unit_id,
                "cache_key": key,
                "coverage_status": coverage_status,
                "rechunker_version": semantic_unit.get("rechunker_version"),
                "window_sha256": semantic_unit.get("text_sha256"),
                "contains_source_text": False,
            })
            totals["needs_review"] += 1
            totals[coverage_status] += 1
            # Ambiguous coverage is neither a completed empty result nor an
            # automatic resplit request.  It is never cached or written.
            continue

        empty_signal_codes = list(
            prepared_call.get("empty_confirmation_signal_codes") or []
        )
        if coverage_status == "nothing_extractable":
            totals["model_reported_nothing_extractable"] += 1
            if requires_empty_confirmation(coverage_status, empty_signal_codes):
                append_jsonl(review_path, {
                    "semantic_mode": semantic_mode,
                    "semantic_unit_id": semantic_unit_id,
                    "cache_key": key,
                    # Keep the established mutually exclusive review enum.  The
                    # deterministic subtype records why the runner overrode the
                    # model's provisional empty status.
                    "coverage_status": "review_other",
                    "model_coverage_status": "nothing_extractable",
                    "review_kind": "empty_confirmation",
                    "empty_confirmation_signal_codes": empty_signal_codes,
                    "rechunker_version": semantic_unit.get("rechunker_version"),
                    "window_sha256": semantic_unit.get("text_sha256"),
                    "response_sha256": response_digest,
                    "contains_source_text": False,
                })
                totals["needs_review"] += 1
                totals["review_other"] += 1
                totals["empty_confirmation_required"] += 1
                # A high-signal empty is provisional: it creates neither an
                # ExtractionActivity nor a reusable success-cache entry.
                continue

        contract_normalizations: list[dict[str, Any]] = []
        slots, selector_rejections = materialize_occurrence_offsets(
            slots,
            evidence_inventory=evidence,
            normalizations_out=contract_normalizations,
        )
        for event in contract_normalizations:
            totals[f"normalization_{event['action']}"] += 1
        if selector_rejections:
            append_jsonl(errors_path, {
                "semantic_mode": semantic_mode,
                "semantic_unit_id": semantic_unit_id,
                "cache_key": key,
                "error": "slot_rejections",
                "rejections": selector_rejections,
                "normalizations": contract_normalizations,
                "response_sha256": response_digest,
            })
            append_private_rejection(
                private_rejection_path,
                semantic_mode=semantic_mode,
                semantic_unit_id=semantic_unit_id,
                cache_key_value=key,
                stage="occurrence_materialization",
                response_object=response_object,
                rejections=selector_rejections,
                normalizations=contract_normalizations,
            )
            totals["rejected_slots"] += sum(
                len(item.get("errors") or []) for item in selector_rejections
            )
            totals["responses_rejected_atomically"] += 1
            continue

        call_delta = accumulator.begin_delta()
        input_sha = sha256_text(canonical_json({
            "semantic_mode": semantic_mode,
            "semantic_unit_id": semantic_unit_id,
            "semantic_unit_sha256": sha256_text(str(semantic_unit.get("text") or "")),
            "offset_map_sha256": semantic_unit.get("offset_map_sha256"),
            "candidates": candidates, "evidence": evidence,
        }))
        activity = ExtractionActivity(
            pipeline_name=PIPELINE_NAME, pipeline_version=PIPELINE_VERSION,
            extractor_type="llm", input_sha256=input_sha,
            model=response_model, prompt_sha256=PROMPT_SHA256,
            parameters={
                "cache_key": key, "temperature": 0,
                "max_input_tokens": args.max_input_tokens,
                "max_source_tokens": args.max_source_tokens,
                "soft_rendered_prompt_tokens": args.soft_rendered_prompt_tokens,
                "max_output_tokens": args.max_output_tokens,
                "semantic_mode": semantic_mode,
                "rechunker_version": semantic_unit.get("rechunker_version"),
                "offset_map_sha256": semantic_unit.get("offset_map_sha256"),
                "evidence_unit_mode": evidence_unit_mode,
                "rendered_prompt_token_estimates": prompt_token_estimates,
                "contract_normalizations": contract_normalizations,
            },
        )
        accumulator.add(activity)
        if semantic_mode == "claim_window":
            assert window is not None
            accepted, rejected = convert_claim_window_slots(
                window, slots,
                candidate_inventory=candidates, evidence_inventory=evidence,
                activity_id=activity.id, accumulator=accumulator,
                passage_index=index,
            )
        else:
            assert passage is not None
            accepted, rejected = convert_validated_llm_slots(
                passage, slots,
                candidate_inventory=candidates, evidence_inventory=evidence,
                activity_id=activity.id, accumulator=accumulator,
            )
        if rejected:
            append_jsonl(errors_path, {
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "cache_key": key,
                "error": "slot_rejections", "rejections": rejected,
                "normalizations": contract_normalizations,
                "response_sha256": response_digest,
            })
            append_private_rejection(
                private_rejection_path,
                semantic_mode=semantic_mode,
                semantic_unit_id=semantic_unit_id,
                cache_key_value=key,
                stage="slot_conversion",
                response_object=response_object,
                rejections=rejected,
                normalizations=contract_normalizations,
            )
            totals["rejected_slots"] += len(rejected)
            # A response with any invalid slot is never a success cache entry.
            # Roll back the entire semantic call rather than silently keeping a
            # valid-looking subset whose omissions depend on provider errors.
            accumulator.rollback_delta(call_delta)
            totals["responses_rejected_atomically"] += 1
            continue
        try:
            new_ids = commit_validated_call_delta(
                accumulator, call_delta, validation_index,
            )
        except Exception as exc:
            # The helper rolls the matching accumulator delta back in O(delta)
            # and never mutates the validation index on a failed validation.
            append_jsonl(errors_path, {
                "semantic_mode": semantic_mode, "semantic_unit_id": semantic_unit_id,
                "cache_key": key,
                "error": "graph_validation_failed", "error_sha256": sha256_text(str(exc)),
                "response_sha256": response_digest,
            })
            append_private_rejection(
                private_rejection_path,
                semantic_mode=semantic_mode,
                semantic_unit_id=semantic_unit_id,
                cache_key_value=key,
                stage="graph_validation",
                response_object=response_object,
                rejections=[{"errors": ["graph_validation_failed"]}],
                normalizations=contract_normalizations,
            )
            totals["graph_validation_failed"] += 1
            continue
        added_ids.extend(new_ids)
        totals["accepted_assertions"] += len(accepted)
        totals["nothing_extractable"] += int(
            coverage_status == "nothing_extractable"
        )
        cache_payload = {
            "status": "validated_success", "cache_key": key,
            "model": response_model, "response": response_object,
            "accepted_assertion_ids": accepted,
            "contract_normalizations": contract_normalizations,
        }
        temp_cache = cache_path.with_suffix(".tmp")
        temp_cache.write_text(canonical_json(cache_payload) + "\n", encoding="utf-8")
        os.replace(temp_cache, cache_path)

    additions = [accumulator.records[record_id] for record_id in dict.fromkeys(added_ids)]
    with additions_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in additions:
            handle.write(canonical_json(record) + "\n")
    assert_valid_graph(accumulator.values())
    manifest = {
        "pipeline": f"{PIPELINE_NAME}@{PIPELINE_VERSION}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_graph": str(args.graph), "base_graph_sha256": file_sha256(args.graph),
        "semantic_mode": "legacy_passage" if legacy_mode else "claim_window",
        "legacy_passage_unit": legacy_mode,
        "semantic_input": str(semantic_input_path),
        "semantic_input_sha256": file_sha256(semantic_input_path),
        "models": models, "prompt_sha256": PROMPT_SHA256,
        "structured_output": args.structured_output,
        "provider_routing": {
            "sort": args.provider_sort,
            "data_collection": args.provider_data_collection,
            "strict_schema_require_parameters": args.strict_require_parameters,
            "provider_slug_pinned": False,
        },
        "replay_filter": {
            "include_unit_ids_from": [
                str(path) for path in (args.include_unit_ids_from or [])
            ],
            "selection_key": "semantic_unit_id_only",
            "source_text_copied_from_ledger": False,
        },
        "selected_queue_rows": len(queue), "ready_calls": len(prepared),
        "semantic_calls": semantic_calls, "cache_hits": cache_hits,
        "budget_total_tokens": args.budget_total_tokens,
        "concurrency": {
            "workers": args.workers,
            "scope": "physical_provider_requests_and_retries_only",
            "stateful_processing": "main_thread_prepared_order",
            "reservation_policy": (
                "all model x structured-mode x retry attempts, each at its "
                "rendered input estimate plus max output"
            ),
            **scheduler_stats,
        },
        "graph_validation": {
            "base_gate": "full_assert_valid_graph",
            "per_semantic_call": "immutable_index_plus_atomic_delta",
            "delta_checks": [
                "local_shape_and_stable_id",
                "all_domain_range_references",
                "exact_evidence_quote",
                "reachable_logic_cycles",
                "immutable_existing_record",
            ],
            "failed_delta_policy": "rollback_all_records_from_semantic_call",
            "final_gate": "full_assert_valid_graph",
        },
        "token_limits": {
            "target_source_tokens": 3000,
            "max_source_tokens": args.max_source_tokens,
            "soft_rendered_prompt_tokens": args.soft_rendered_prompt_tokens,
            "hard_rendered_prompt_tokens": args.max_input_tokens,
            "overflow_policy": "explicit_reject_never_truncate",
            "rendered_prompt_estimation": (
                "json_schema includes response_format schema; json_object includes "
                "the in-band full schema; worst case governs soft/hard gates, budget, "
                "and cache identity"
            ),
        },
        "evidence_unit_policy": {
            "production": "primary_claim_block",
            "sentence_subspans_retained": True,
            "fallback": "legacy_sentence_fallback_explicitly_labeled",
            "max_evidence_units": args.max_evidence_units,
            "max_sentence_subspans": args.max_evidence_sentences,
            "model_citation_contract": (
                "mention_id + exact surface + 1-based occurrence index"
            ),
            "absolute_offset_materialization": (
                "deterministic main-thread exact-match projection"
            ),
            "out_of_range_repair": (
                "only_when_exact_surface_occurs_once_in_selected_evidence_unit"
            ),
        },
        "extraction_contract_normalization": {
            "direction": "derived_from_diagnostic_role_never_model_supplied",
            "normalizations_recorded_in_activity_or_public_rejection": True,
        },
        "response_coverage_policy": {
            "max_assertions_per_call": RESPONSE_SCHEMA["properties"]["assertions"]["maxItems"],
            "coverage_status_required": True,
            "coverage_status_values": sorted(ALL_COVERAGE_STATUSES),
            "partial_prefix_cacheable": False,
            "needs_resplit_ledger": str(resplit_path),
            "needs_resplit_records": len(load_jsonl(resplit_path))
            if resplit_path.exists() else 0,
            "needs_review_ledger": str(review_path),
            "needs_review_records": len(load_jsonl(review_path))
            if review_path.exists() else 0,
            "high_signal_nothing_extractable_policy": (
                "review_other/empty_confirmation_never_cached"
            ),
            "output_capacity_contract": {
                "configured_max_output_tokens": args.max_output_tokens,
                "envelope_reserve_tokens": OUTPUT_ENVELOPE_RESERVE_TOKENS,
                "per_assertion_token_floor": OUTPUT_TOKENS_PER_ASSERTION_FLOOR,
                "minimum_compatible_output_tokens": MIN_OUTPUT_TOKENS,
                "partial_complete_allowed": False,
            },
        },
        "provider_reported_tokens_used": provider_reported_tokens,
        "budget_accounted_tokens_used": budget_accounted,
        "counts": dict(sorted(totals.items())),
        "llm_records": {
            "path": str(additions_path), "sha256": file_sha256(additions_path),
            "records": len(additions), "contains_short_source_surfaces": True,
        },
        "telemetry": {
            "path": str(telemetry_path),
            "sha256": file_sha256(telemetry_path) if telemetry_path.exists() else None,
            "contains_prompts_or_credentials": False,
        },
        "private_rejection_audit": {
            "enabled": private_rejection_path is not None,
            "path": str(private_rejection_path)
            if private_rejection_path is not None else None,
            "sha256": file_sha256(private_rejection_path)
            if private_rejection_path is not None
            and private_rejection_path.exists() else None,
            "mode": "0600" if private_rejection_path is not None else None,
            "includes_prompts_or_evidence_inventories": False,
            "may_contain_source_text_from_model_output": (
                private_rejection_path is not None
            ),
        },
        "full_graph_validation": "passed",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
