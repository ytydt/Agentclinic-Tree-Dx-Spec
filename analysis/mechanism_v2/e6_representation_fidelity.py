#!/usr/bin/env python3
"""E6: raw vignette versus flat facts versus a typed clinical event graph."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    DEVELOPMENT_SLICES,
    ROOT,
    FrozenExactSynonymBridge,
    clean_vignette,
    combined_file_sha256,
    file_sha256,
    load_normalized_cases,
    normalize_label,
    source_commit,
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
    sha256_text,
    stable_seed,
    validate_workers,
)


EXPERIMENT_ID = "E6"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E6_representation_fidelity"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"

RAW = "raw_vignette"
FLAT = "flat_facts"
GRAPH = "typed_event_graph"
ARMS = (RAW, FLAT, GRAPH)
WORD_CAP = 1_200
PAD_TOKEN = "[LENGTH_CONTROL_PAD]"

TEMPORAL_RE = re.compile(
    r"\b(?:previously|initially|subsequently|later|after|before|"
    r"follow(?:ed|ing|[- ]up)|progress(?:ed|ive|ion)?|years? ago|"
    r"months? ago|days? later|over the next|since|recurrent|then|prior|"
    r"eventually|on day \d+|at \d+ (?:days?|weeks?|months?|years?))\b",
    re.IGNORECASE,
)
NEGATIVE_RE = re.compile(
    r"\b(?:no|without|denied|negative|normal|unremarkable|absence|absent|"
    r"failed to|did not|ruled out|excluded|unlikely|not detected|no evidence)\b",
    re.IGNORECASE,
)
COMPOSITE_RE = re.compile(
    r"\b(?:with|due to|associated with|secondary to|causing|complicated by|"
    r"presenting (?:as|with))\b|\band\b",
    re.IGNORECASE,
)

NODE_KINDS = {
    "symptom", "sign", "test", "imaging", "pathology", "exposure",
    "treatment", "response", "diagnosis", "anatomy", "demographic",
    "family_history", "other",
}
POLARITIES = {"present", "absent", "uncertain", "historical"}
SCOPES = {"patient", "family", "maternal", "fetal", "other"}
RELATION_TYPES = {
    "before", "after", "causes", "supports", "contradicts", "located_at",
    "component_of", "progresses_to", "responds_to", "co_occurs_with",
    "same_episode_as", "different_episode_from",
}

BUILDER_PROMPT = """Role: candidate-blind clinical representation builder.

Transform the supplied vignette into TWO faithful representations. Do not
diagnose the case, rank diseases, add outside medical facts, or infer a final
answer. Every fact/node must cite a short verbatim quote from the vignette.

Representation A is an UNORDERED flat fact list. Preserve concrete findings,
tests, treatments and explicit negatives, but do not encode typed edges or use
list order to imply time/causality. Keep each fact concise.

Representation B is a typed event graph. Nodes preserve entity/event type,
polarity, explicit time anchor and whose scope it concerns. Relations must be
supported by the vignette and use only the allowed relation types. Do not turn
mere co-occurrence into causation.

Return strict JSON only:
{
  "flat_facts":[
    {"fact_id":"F01","text":"concise faithful fact","source_quote":"verbatim quote"}
  ],
  "graph_nodes":[
    {"node_id":"N01","kind":"symptom|sign|test|imaging|pathology|exposure|treatment|response|diagnosis|anatomy|demographic|family_history|other",
     "text":"concise faithful node","polarity":"present|absent|uncertain|historical",
     "time_anchor":"explicit text such as presentation, 2 years earlier, after treatment, or unspecified",
     "scope":"patient|family|maternal|fetal|other","source_quote":"verbatim quote"}
  ],
  "graph_relations":[
    {"source_id":"N01","relation":"before|after|causes|supports|contradicts|located_at|component_of|progresses_to|responds_to|co_occurs_with|same_episode_as|different_episode_from",
     "target_id":"N02","justification":"brief vignette-grounded reason"}
  ]
}

Use 8-24 flat facts, 8-28 graph nodes and 4-36 relations. Prefer omission to
unsupported inference; preserve high-specificity pathology, imaging, temporal
change, treatment response and explicit negative scope."""

SELECTOR_PROMPT = """Role: source-blind clinical differential ranker.

The supplied clinical record may be prose or a structured representation.
Ignore [LENGTH_CONTROL_PAD]. Infer the most likely complete diagnosis from the
record alone. Produce exactly five distinct diagnosis candidates in ranked
order. Preserve requested cause, anatomy, stage, complication and temporal
scope when the record supports them. Do not answer with a test, evidence
sentence, isolated symptom, or generic category when a complete diagnosis is
supported. Treat a negative result according to its time and scope; do not
convert an early, insensitive or differently scoped negative into an absolute
veto.

Return strict JSON only:
{
  "candidates":[
    {"candidate_id":"D1","label":"complete diagnosis","confidence":0.0,
     "support_refs":["record quote or structured ID"],
     "contradiction_refs":["record quote or structured ID"],
     "missing_or_uncertain":["brief item"]}
  ],
  "champion_id":"D1","runner_up_id":"D2",
  "top1_probability":0.0,"margin":"high|medium|low",
  "rationale":"brief direct contrast including time/scope when decisive"
}

Candidate order is the ranking. IDs are arbitrary and every candidate must be
a diagnosis."""


def whitespace_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def challenge_flags(vignette: str, gold: str) -> dict[str, Any]:
    temporal_marker_n = len(TEMPORAL_RE.findall(vignette))
    negative_marker_n = len(NEGATIVE_RE.findall(vignette))
    return {
        "temporal": temporal_marker_n >= 2,
        "negative": negative_marker_n >= 6,
        "composite_target": bool(COMPOSITE_RE.search(gold)),
        "temporal_marker_n": temporal_marker_n,
        "negative_marker_n": negative_marker_n,
    }


def select_cases(per_family: int = 150) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in DEVELOPMENT_SLICES:
        for source_id, case in load_normalized_cases(spec.cases_json).items():
            vignette = clean_vignette(str(case.get("case_text") or ""))
            gold = str(case.get("gold") or case.get("gold_option_text") or "").strip()
            if not vignette or not gold:
                continue
            flags = challenge_flags(vignette, gold)
            # Composite targets receive double sampling priority because they
            # are rarer and relation loss is otherwise dominated by chronology.
            challenge_weight = (
                int(flags["temporal"])
                + int(flags["negative"])
                + 2 * int(flags["composite_target"])
            )
            by_family[spec.family].append({
                "case_key": f"{spec.slice_id}/{source_id}",
                "slice_id": spec.slice_id,
                "family": spec.family,
                "source_id": source_id,
                "case_path": str(spec.cases_json.relative_to(ROOT)),
                "vignette": vignette[:9_000],
                "gold": gold,
                "challenge": flags,
                "challenge_weight": challenge_weight,
            })
    selected: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        ranked = sorted(
            by_family[family],
            key=lambda row: (
                -int(row["challenge_weight"]),
                stable_seed("E6-case-sample-v1", row["case_key"]),
                row["case_key"],
            ),
        )
        if len(ranked) < per_family:
            raise AssertionError(f"only {len(ranked)} eligible {family} cases")
        selected.extend(ranked[:per_family])
    return sorted(selected, key=lambda row: row["case_key"])


def quote_is_grounded(quote: str, vignette: str) -> bool:
    quote_norm = whitespace_normalize(quote)
    return bool(len(quote_norm) >= 3 and quote_norm in whitespace_normalize(vignette))


def repair_grounded_quote(quote: str, vignette: str) -> str | None:
    """Return the exact vignette span for punctuation-only quote drift.

    The builder sometimes replaces source bullets with commas or omits a
    Markdown ``*``.  Accepting the generated string as "verbatim" would weaken
    the audit contract.  Instead, align an identical contiguous sequence of
    case-folded word tokens and copy the corresponding characters from the
    source vignette.  No fuzzy substitutions, omissions or reorderings pass.
    """
    quote_norm = whitespace_normalize(quote)
    vignette_norm = whitespace_normalize(vignette)
    if quote_is_grounded(quote_norm, vignette_norm):
        return quote_norm
    quote_tokens = [match.group(0).casefold() for match in re.finditer(r"\w+", quote_norm)]
    source_matches = list(re.finditer(r"\w+", vignette_norm))
    if not quote_tokens or len(quote_norm) < 3 or len(quote_tokens) > len(source_matches):
        return None
    source_tokens = [match.group(0).casefold() for match in source_matches]
    width = len(quote_tokens)
    for start in range(len(source_tokens) - width + 1):
        if source_tokens[start:start + width] != quote_tokens:
            continue
        matched = vignette_norm[
            source_matches[start].start():source_matches[start + width - 1].end()
        ]
        if len(matched) >= 3:
            return matched
    # A literal ellipsis is an explicit omission marker, not a fuzzy edit.
    # Locate every unchanged segment in source order and return the shortest
    # exact source span that covers them.  This keeps the stored quote truly
    # verbatim while refusing substitutions or reordered tokens.
    if re.search(r"(?:\.{3}|…)", quote_norm):
        segment_tokens = [
            [match.group(0).casefold() for match in re.finditer(r"\w+", segment)]
            for segment in re.split(r"(?:\.{3}|…)", quote_norm)
        ]
        segment_tokens = [tokens for tokens in segment_tokens if tokens]
        candidates: list[tuple[int, int]] = []
        if len(segment_tokens) >= 2:
            first = segment_tokens[0]
            for start in range(len(source_tokens) - len(first) + 1):
                if source_tokens[start:start + len(first)] != first:
                    continue
                cursor = start + len(first)
                end = cursor - 1
                complete = True
                for segment in segment_tokens[1:]:
                    located = None
                    for probe in range(cursor, len(source_tokens) - len(segment) + 1):
                        if source_tokens[probe:probe + len(segment)] == segment:
                            located = probe
                            break
                    if located is None:
                        complete = False
                        break
                    end = located + len(segment) - 1
                    cursor = end + 1
                if complete:
                    candidates.append((start, end))
        if candidates:
            start, end = min(
                candidates,
                key=lambda pair: (
                    source_matches[pair[1]].end() - source_matches[pair[0]].start(),
                    pair[0],
                ),
            )
            matched = vignette_norm[
                source_matches[start].start():source_matches[end].end()
            ]
            if len(matched) <= 400:
                return matched
    return None


def normalize_builder_response(
    response: Mapping[str, Any], vignette: str
) -> tuple[dict[str, Any], list[str]]:
    """Apply bounded, target-blind schema repairs while retaining provenance."""
    normalized = json.loads(json.dumps(dict(response), ensure_ascii=False))
    actions: list[str] = []
    raw_facts = normalized.get("flat_facts")
    raw_nodes = normalized.get("graph_nodes")
    raw_relations = normalized.get("graph_relations")
    facts = list(raw_facts) if isinstance(raw_facts, list) else []
    nodes = list(raw_nodes) if isinstance(raw_nodes, list) else []
    relations = list(raw_relations) if isinstance(raw_relations, list) else []

    if len(facts) > 24:
        actions.append(f"trim_flat_facts:{len(facts)}->24")
        facts = facts[:24]
    if len(nodes) > 28:
        actions.append(f"trim_graph_nodes:{len(nodes)}->28")
        nodes = nodes[:28]

    for index, row in enumerate(facts):
        if not isinstance(row, dict):
            continue
        wanted_id = f"F{index + 1:02d}"
        if row.get("fact_id") != wanted_id:
            actions.append(f"canonicalize_fact_id:{row.get('fact_id')}->{wanted_id}")
            row["fact_id"] = wanted_id
        quote = str(row.get("source_quote") or "")
        repaired = repair_grounded_quote(quote, vignette)
        if repaired is not None and repaired != whitespace_normalize(quote):
            row["source_quote"] = repaired
            actions.append(f"repair_flat_quote:{wanted_id}")

    kind_aliases = {
        "event": "other", "history": "other", "procedure": "other",
        "lab": "test", "laboratory": "test", "medication": "treatment",
        "therapy": "treatment", "finding": "sign",
    }
    polarity_aliases = {
        "positive": "present", "negative": "absent", "unknown": "uncertain",
        "possible": "uncertain", "past": "historical",
    }
    scope_aliases = {"self": "patient", "subject": "patient", "unknown": "other"}
    for row in nodes:
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("node_id") or "")
        kind = str(row.get("kind") or "").strip().lower()
        if kind not in NODE_KINDS and kind in kind_aliases:
            row["kind"] = kind_aliases[kind]
            actions.append(f"canonicalize_kind:{node_id}:{kind}->{row['kind']}")
        polarity = str(row.get("polarity") or "").strip().lower()
        if polarity not in POLARITIES and polarity in polarity_aliases:
            row["polarity"] = polarity_aliases[polarity]
            actions.append(
                f"canonicalize_polarity:{node_id}:{polarity}->{row['polarity']}"
            )
        scope = str(row.get("scope") or "").strip().lower()
        if scope not in SCOPES and scope in scope_aliases:
            row["scope"] = scope_aliases[scope]
            actions.append(f"canonicalize_scope:{node_id}:{scope}->{row['scope']}")
        if not str(row.get("time_anchor") or "").strip():
            row["time_anchor"] = "unspecified"
            actions.append(f"fill_unspecified_time:{node_id}")
        quote = str(row.get("source_quote") or "")
        repaired = repair_grounded_quote(quote, vignette)
        if repaired is not None and repaired != whitespace_normalize(quote):
            row["source_quote"] = repaired
            actions.append(f"repair_node_quote:{node_id}")

    node_ids = {
        str(row.get("node_id") or "") for row in nodes if isinstance(row, Mapping)
    }
    kept_relations: list[Any] = []
    for index, row in enumerate(relations, 1):
        if not isinstance(row, Mapping):
            kept_relations.append(row)
            continue
        source_id = str(row.get("source_id") or "")
        target_id = str(row.get("target_id") or "")
        reason = None
        if source_id not in node_ids or target_id not in node_ids:
            reason = "missing_endpoint"
        elif source_id == target_id:
            reason = "self_loop"
        if reason is not None:
            actions.append(f"drop_relation_{index}:{reason}")
            continue
        kept_relations.append(row)
    if len(kept_relations) > 36:
        actions.append(f"trim_graph_relations:{len(kept_relations)}->36")
        kept_relations = kept_relations[:36]
    normalized["flat_facts"] = facts
    normalized["graph_nodes"] = nodes
    normalized["graph_relations"] = kept_relations
    return normalized, actions


def validate_builder(response: Mapping[str, Any], vignette: str) -> str | None:
    facts = response.get("flat_facts") or []
    nodes = response.get("graph_nodes") or []
    relations = response.get("graph_relations") or []
    if not isinstance(facts, list) or not 8 <= len(facts) <= 24:
        return "flat_facts must contain 8-24 rows"
    if not isinstance(nodes, list) or not 8 <= len(nodes) <= 28:
        return "graph_nodes must contain 8-28 rows"
    if not isinstance(relations, list) or not 4 <= len(relations) <= 36:
        return "graph_relations must contain 4-36 rows"
    if not all(isinstance(row, Mapping) for row in facts + nodes + relations):
        return "all representation rows must be objects"
    fact_ids = [str(row.get("fact_id") or "") for row in facts]
    node_ids = [str(row.get("node_id") or "") for row in nodes]
    if "" in fact_ids or len(set(fact_ids)) != len(fact_ids):
        return "flat fact IDs must be nonempty and unique"
    if "" in node_ids or len(set(node_ids)) != len(node_ids):
        return "graph node IDs must be nonempty and unique"
    for row in facts:
        if not str(row.get("text") or "").strip():
            return "flat fact text must be nonempty"
        if not quote_is_grounded(str(row.get("source_quote") or ""), vignette):
            return "flat fact source_quote must be a vignette substring"
    for row in nodes:
        if str(row.get("kind") or "") not in NODE_KINDS:
            return "invalid graph node kind"
        if str(row.get("polarity") or "") not in POLARITIES:
            return "invalid graph node polarity"
        if str(row.get("scope") or "") not in SCOPES:
            return "invalid graph node scope"
        if not str(row.get("text") or "").strip() or not str(row.get("time_anchor") or "").strip():
            return "graph node text/time_anchor must be nonempty"
        if not quote_is_grounded(str(row.get("source_quote") or ""), vignette):
            return "graph node source_quote must be a vignette substring"
    node_set = set(node_ids)
    for row in relations:
        if str(row.get("source_id") or "") not in node_set or str(row.get("target_id") or "") not in node_set:
            return "graph relation endpoint absent from nodes"
        if str(row.get("source_id")) == str(row.get("target_id")):
            return "graph relation cannot self-loop"
        if str(row.get("relation") or "") not in RELATION_TYPES:
            return "invalid graph relation type"
        if not str(row.get("justification") or "").strip():
            return "graph relation justification must be nonempty"
    if len({normalize_label(str(row.get("text") or "")) for row in facts}) != len(facts):
        return "flat facts must be surface-unique"
    return None


def serialize_flat(response: Mapping[str, Any]) -> str:
    lines = ["CASE REPRESENTATION", "UNORDERED FACTS (list order has no meaning):"]
    for row in response.get("flat_facts") or []:
        lines.append(f"{row['fact_id']} :: {whitespace_normalize(str(row['text']))}")
    return "\n".join(lines)


def serialize_graph(response: Mapping[str, Any]) -> str:
    lines = ["CASE REPRESENTATION", "TYPED EVENT GRAPH", "NODES:"]
    for row in response.get("graph_nodes") or []:
        lines.append(
            f"{row['node_id']} | {row['kind']} | polarity={row['polarity']} | "
            f"time={whitespace_normalize(str(row['time_anchor']))} | scope={row['scope']} "
            f":: {whitespace_normalize(str(row['text']))}"
        )
    lines.append("RELATIONS:")
    for row in response.get("graph_relations") or []:
        lines.append(
            f"{row['source_id']} --{row['relation']}--> {row['target_id']}"
        )
    return "\n".join(lines)


def serialize_raw(vignette: str) -> str:
    return "CASE REPRESENTATION\nCLINICAL RECORD:\n" + vignette.strip()


def whitespace_word_count(value: str) -> int:
    return len(re.findall(r"\S+", value))


def truncate_words(value: str, target: int) -> tuple[str, int]:
    parts = re.findall(r"\S+|\s+", value)
    output: list[str] = []
    words = removed = 0
    total = whitespace_word_count(value)
    for part in parts:
        if part.isspace():
            if words < target:
                output.append(part)
            continue
        if words >= target:
            removed += 1
            continue
        output.append(part)
        words += 1
    removed = max(removed, total - words)
    return "".join(output).rstrip(), removed


def pad_to_words(value: str, target: int) -> tuple[str, int]:
    current = whitespace_word_count(value)
    if current >= target:
        return value, 0
    padding = target - current
    return value.rstrip() + "\n" + " ".join([PAD_TOKEN] * padding), padding


def matched_representations(
    vignette: str, builder_response: Mapping[str, Any], word_cap: int = WORD_CAP
) -> dict[str, dict[str, Any]]:
    originals = {
        RAW: serialize_raw(vignette),
        FLAT: serialize_flat(builder_response),
        GRAPH: serialize_graph(builder_response),
    }
    target = min(max(whitespace_word_count(text) for text in originals.values()), word_cap)
    output: dict[str, dict[str, Any]] = {}
    for arm, original in originals.items():
        truncated, removed = truncate_words(original, target)
        matched, padding = pad_to_words(truncated, target)
        if whitespace_word_count(matched) != target:
            raise AssertionError("word matching failed")
        output[arm] = {
            "text": matched,
            "original_whitespace_words": whitespace_word_count(original),
            "matched_whitespace_words": target,
            "padding_words": padding,
            "truncated_words": removed,
            "original_characters": len(original),
            "matched_characters": len(matched),
            "matched_sha256": canonical_sha256({"text": matched}),
        }
    return output


def validate_selector(response: Mapping[str, Any]) -> str | None:
    candidates = response.get("candidates") or []
    if not isinstance(candidates, list) or len(candidates) != 5:
        return "candidates must contain exactly five rows"
    if not all(isinstance(row, Mapping) for row in candidates):
        return "candidate rows must be objects"
    ids = [str(row.get("candidate_id") or "") for row in candidates]
    labels = [normalize_label(str(row.get("label") or "")) for row in candidates]
    if "" in ids or len(set(ids)) != 5:
        return "candidate IDs must be nonempty and unique"
    if "" in labels or len(set(labels)) != 5:
        return "candidate labels must be nonempty and unique"
    for row in candidates:
        try:
            confidence = float(row.get("confidence"))
        except (TypeError, ValueError):
            return "candidate confidence must be numeric"
        if not 0 <= confidence <= 1:
            return "candidate confidence must be in [0,1]"
        for key in ("support_refs", "contradiction_refs", "missing_or_uncertain"):
            if not isinstance(row.get(key), list):
                return f"{key} must be a list"
    champion = str(response.get("champion_id") or "")
    runner = str(response.get("runner_up_id") or "")
    if ids[:2] != [champion, runner]:
        return "champion/runner must be the first two ranked candidates"
    try:
        probability = float(response.get("top1_probability"))
    except (TypeError, ValueError):
        return "top1_probability must be numeric"
    if not 0 <= probability <= 1:
        return "top1_probability must be in [0,1]"
    if str(response.get("margin") or "").lower() not in {"high", "medium", "low"}:
        return "margin must be high|medium|low"
    if not str(response.get("rationale") or "").strip():
        return "rationale must be nonempty"
    return None


def runtime_environment(directory: Path, model: str, workers: int, phase: str) -> None:
    path = directory / "environment.json"
    environment = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else dependency_capabilities()
    )
    environment.update({
        "capture_phase": phase,
        "model": model,
        "workers": workers,
        "runtime_controls": {
            key: os.environ.get(key)
            for key in (
                "TREE_DX_PROXY_MODE",
                "TREE_DX_LLM_TRANSPORT",
                "TREE_DX_DIRECT_POST_OUTPUT_CAP",
                "TREE_DX_DIRECT_POST_OUTPUT_MAX_CAP",
                "TREE_DX_REASONING_MAX_TOKENS",
                "TREE_DX_REASONING_EXCLUDE",
                "TREE_DX_LLAMA_PROVIDER_POLICY",
            )
        },
    })
    atomic_json(path, environment)


def run_builder(
    out: Path, jobs: Sequence[Mapping[str, Any]], model: str, workers: int
) -> list[dict[str, Any]]:
    phase = out / "representations"
    phase.mkdir(parents=True, exist_ok=True)
    runtime_environment(phase, model, workers, "online representation builder")
    result_path = phase / "case_representations.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            return rows
        raise AssertionError("partial representation build requires explicit audit")
    telemetry_path = phase / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=phase,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "case_id": job["case_key"],
            "vignette": job["vignette"],
            "representation_limits": {
                "flat_facts": "8-24",
                "graph_nodes": "8-28",
                "graph_relations": "4-36",
            },
        }
        outcome = caller.call(
            module="E6_representation_builder",
            prompt=BUILDER_PROMPT,
            payload=payload,
            validator=lambda response: validate_builder(response, str(job["vignette"])),
        )
        normalized, normalization_actions = normalize_builder_response(
            outcome.response, str(job["vignette"])
        )
        normalized_error = validate_builder(normalized, str(job["vignette"]))
        return {
            "case_key": job["case_key"],
            "family": job["family"],
            "challenge": job["challenge"],
            "success": not bool(normalized_error),
            "error": normalized_error or "",
            "online_schema_success": outcome.success,
            "online_schema_error": outcome.error,
            "normalization_applied": bool(normalization_actions),
            "normalization_actions": normalization_actions,
            "raw_response_sha256": canonical_sha256(outcome.response),
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
            "response": normalized,
        }

    rows: list[dict[str, Any]] = []
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"model={model}", f"workers={workers}", f"jobs={len(jobs)}",
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "case_key": job["case_key"], "family": job["family"],
                    "challenge": job["challenge"], "success": False,
                    "error": f"{type(exc).__name__}: {exc}", "cache_hit": False,
                    "cache_key": "", "payload_sha256": "", "response": {},
                    "online_schema_success": False, "online_schema_error": "",
                    "normalization_applied": False, "normalization_actions": [],
                    "raw_response_sha256": "",
                }
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    atomic_json(phase / "telemetry_summary.json", aggregate_telemetry(read_jsonl(telemetry_path)))
    log.extend([
        f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"served={sum(row['success'] for row in rows)}",
    ])
    (phase / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def build_manifest(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    builder_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_case = {str(row["case_key"]): row for row in builder_rows}
    rows: list[dict[str, Any]] = []
    for job in jobs:
        built = by_case[str(job["case_key"])]
        if built.get("success"):
            representations = matched_representations(str(job["vignette"]), built["response"])
        else:
            raw = serialize_raw(str(job["vignette"]))
            representations = {
                RAW: {
                    "text": raw,
                    "original_whitespace_words": whitespace_word_count(raw),
                    "matched_whitespace_words": whitespace_word_count(raw),
                    "padding_words": 0,
                    "truncated_words": 0,
                    "original_characters": len(raw),
                    "matched_characters": len(raw),
                    "matched_sha256": canonical_sha256({"text": raw}),
                }
            }
        rows.append({
            "case_key": job["case_key"], "slice_id": job["slice_id"],
            "family": job["family"], "source_id": job["source_id"],
            "challenge": job["challenge"], "builder_success": built["success"],
            "builder_error": built["error"], "representations": representations,
        })
    write_jsonl(out / "representation_manifest.jsonl", rows)
    public = []
    for row in rows:
        public.append({
            **{key: row[key] for key in (
                "case_key", "slice_id", "family", "source_id", "challenge",
                "builder_success", "builder_error",
            )},
            "representations": {
                arm: {key: value for key, value in record.items() if key != "text"}
                for arm, record in row["representations"].items()
            },
        })
    write_jsonl(out / "representation_metrics.jsonl", public)
    return rows


def freeze_builder_audit_sample(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    builder_rows: Sequence[Mapping[str, Any]],
    per_family: int = 15,
) -> list[dict[str, Any]]:
    path = out / "representation_audit_sample.jsonl"
    jobs_by_case = {str(job["case_key"]): job for job in jobs}
    selected: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        eligible = [row for row in builder_rows if row["success"] and row["family"] == family]
        eligible.sort(key=lambda row: (
            stable_seed("E6-representation-audit-v1", row["case_key"]), row["case_key"]
        ))
        if len(eligible) < per_family:
            raise AssertionError(f"only {len(eligible)} successful {family} representations")
        for row in eligible[:per_family]:
            job = jobs_by_case[str(row["case_key"])]
            selected.append({
                "case_key": row["case_key"], "family": family,
                "challenge": job["challenge"], "gold": job["gold"],
                "vignette": job["vignette"], "builder_response": row["response"],
            })
    selected.sort(key=lambda row: row["case_key"])
    if path.is_file():
        frozen = read_jsonl(path)
        if [row["case_key"] for row in frozen] != [row["case_key"] for row in selected]:
            raise AssertionError("frozen representation audit sample changed")
        return frozen
    write_jsonl(path, selected)
    return selected


def selector_result_row(
    job: Mapping[str, Any],
    arm: str,
    representation: Mapping[str, Any],
    response: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
    *,
    success: bool,
    error: str = "",
    cache_hit: bool = False,
    cache_key: str = "",
    payload_sha256: str = "",
) -> dict[str, Any]:
    candidates = list(response.get("candidates") or []) if success else []
    champion_id = str(response.get("champion_id") or "") if success else ""
    champion = next(
        (candidate for candidate in candidates if str(candidate.get("candidate_id")) == champion_id),
        {},
    )
    gold_ranks = [
        index for index, candidate in enumerate(candidates, 1)
        if bridge.equivalent(str(candidate.get("label") or ""), str(job["gold"]))
    ]
    return {
        "case_key": job["case_key"], "slice_id": job["slice_id"],
        "family": job["family"], "source_id": job["source_id"],
        "challenge": job["challenge"], "arm": arm, "gold": job["gold"],
        "success": bool(success), "error": error, "cache_hit": bool(cache_hit),
        "cache_key": cache_key, "payload_sha256": payload_sha256,
        "representation_metrics": {key: value for key, value in representation.items() if key != "text"},
        "response": dict(response), "candidates": candidates,
        "raw_gold_recall": bool(gold_ranks), "gold_rank": min(gold_ranks, default=None),
        "champion_id": champion_id, "champion_label": str(champion.get("label") or ""),
        "strict_top1": bridge.equivalent(str(champion.get("label") or ""), str(job["gold"])),
        "champion_confidence": champion.get("confidence") if success else None,
        "top1_probability": response.get("top1_probability") if success else None,
        "margin": str(response.get("margin") or "") if success else "",
    }


def run_arm(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    builder_rows: Mapping[str, Mapping[str, Any]],
    arm: str,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    runtime_environment(arm_dir, model, workers, f"online selector arm {arm}")
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            return rows
        raise AssertionError("partial selector arm requires explicit audit")
    telemetry_path = arm_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=arm_dir, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        built = builder_rows[str(job["case_key"])]
        if arm != RAW and built.get("success") is not True:
            return selector_result_row(
                job, arm, {}, {}, bridge, success=False,
                error=f"construction_failure: {built.get('error') or 'unknown builder failure'}",
            )
        if built.get("success"):
            representation = matched_representations(str(job["vignette"]), built["response"])[arm]
        else:
            raw = serialize_raw(str(job["vignette"]))
            representation = {
                "text": raw,
                "original_whitespace_words": whitespace_word_count(raw),
                "matched_whitespace_words": whitespace_word_count(raw),
                "padding_words": 0,
                "truncated_words": 0,
                "original_characters": len(raw),
                "matched_characters": len(raw),
                "matched_sha256": canonical_sha256({"text": raw}),
            }
        payload = {"case_id": job["case_key"], "clinical_record": representation["text"]}
        assert_target_blind(payload)
        outcome = caller.call(
            module="E6_representation_selector",
            prompt=SELECTOR_PROMPT,
            payload=payload,
            validator=validate_selector,
        )
        return selector_result_row(
            job, arm, representation, outcome.response, bridge,
            success=outcome.success, error=outcome.error,
            cache_hit=outcome.cache_hit, cache_key=outcome.cache_key,
            payload_sha256=outcome.payload_sha256,
        )

    rows: list[dict[str, Any]] = []
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"arm={arm}", f"model={model}", f"workers={workers}", f"jobs={len(jobs)}",
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = selector_result_row(
                    job, arm, {}, {}, bridge, success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    atomic_json(arm_dir / "telemetry_summary.json", aggregate_telemetry(read_jsonl(telemetry_path)))
    log.extend([
        f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"served={sum(row['success'] for row in rows)}",
        f"raw_gold_recall={sum(row['raw_gold_recall'] for row in rows)}",
        f"strict_top1={sum(row['strict_top1'] for row in rows)}",
    ])
    (arm_dir / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def paired(
    rows: Sequence[Mapping[str, Any]], left: str, right: str, endpoint: str
) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    counts: Counter[tuple[bool, bool]] = Counter()
    flips = comparable = 0
    rank_deltas: list[float] = []
    for arms in indexed.values():
        if left not in arms or right not in arms:
            continue
        before, after = arms[left], arms[right]
        if not before["success"] or not after["success"]:
            continue
        comparable += 1
        counts[(bool(before[endpoint]), bool(after[endpoint]))] += 1
        flips += normalize_label(str(before["champion_label"])) != normalize_label(str(after["champion_label"]))
        if before["gold_rank"] is not None and after["gold_rank"] is not None:
            rank_deltas.append(float(after["gold_rank"]) - float(before["gold_rank"]))
    left_only, right_only = counts[(True, False)], counts[(False, True)]
    discordant = left_only + right_only
    pvalue = 1.0
    if discordant:
        tail = sum(math.comb(discordant, index) for index in range(min(left_only, right_only) + 1))
        pvalue = min(1.0, 2 * tail / (2**discordant))
    return {
        "left": left, "right": right, "endpoint": endpoint,
        "n_comparable": comparable, "left_only": left_only,
        "right_only": right_only, "both": counts[(True, True)],
        "neither": counts[(False, False)],
        "delta_right_minus_left": round((right_only - left_only) / comparable, 6) if comparable else None,
        "exact_mcnemar_p": pvalue, "champion_flip_n": flips,
        "mean_gold_rank_delta": round(sum(rank_deltas) / len(rank_deltas), 6) if rank_deltas else None,
    }


def finalize(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        arm_rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(arm_rows) != len(jobs):
            raise AssertionError(f"incomplete arm {arm}: {len(arm_rows)}/{len(jobs)}")
        rows.extend(arm_rows)
    rows.sort(key=lambda row: (row["case_key"], ARMS.index(row["arm"])))
    write_jsonl(out / "case_conditions.jsonl", rows)
    groups: list[tuple[str, list[dict[str, Any]]]] = [("all", rows)]
    groups += [(family, [row for row in rows if row["family"] == family]) for family in ("DA", "MCR")]
    for flag in ("temporal", "negative", "composite_target"):
        groups.append((flag, [row for row in rows if row["challenge"][flag]]))
    summary: dict[str, Any] = {"experiment_id": EXPERIMENT_ID, "n_cases": len(jobs), "groups": {}}
    for group, group_rows in groups:
        arm_stats: dict[str, Any] = {}
        for arm in ARMS:
            arm_rows = [row for row in group_rows if row["arm"] == arm]
            served = [row for row in arm_rows if row["success"]]
            arm_stats[arm] = {
                "n": len(arm_rows), "served": len(served),
                "raw_gold_recall_n": sum(row["raw_gold_recall"] for row in served),
                "strict_top1_n": sum(row["strict_top1"] for row in served),
                "mean_gold_rank": round(
                    sum(row["gold_rank"] for row in served if row["gold_rank"] is not None)
                    / sum(row["gold_rank"] is not None for row in served), 6
                ) if any(row["gold_rank"] is not None for row in served) else None,
            }
        contrasts = []
        for left, right in ((RAW, FLAT), (RAW, GRAPH), (FLAT, GRAPH)):
            for endpoint in ("raw_gold_recall", "strict_top1"):
                contrasts.append(paired(group_rows, left, right, endpoint))
        summary["groups"][group] = {"arms": arm_stats, "paired": contrasts}
    atomic_json(out / "summary.json", summary)
    fields = [
        "case_key", "slice_id", "family", "source_id", "arm", "success",
        "raw_gold_recall", "gold_rank", "strict_top1", "champion_label",
        "champion_confidence", "top1_probability", "margin", "cache_hit", "error",
    ]
    with (out / "case_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def freeze_preregistration(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    input_hash: str,
    model: str,
) -> dict[str, Any]:
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E6_representation_fidelity_prereg_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(), "input_hash": input_hash, "model": model,
        "sample": {
            "rule": "within-family weighted challenge oversample: temporal + negative + 2*composite, then outcome-blind SHA",
            "n": len(jobs), "family_counts": dict(Counter(job["family"] for job in jobs)),
            "challenge_counts": {
                flag: sum(bool(job["challenge"][flag]) for job in jobs)
                for flag in ("temporal", "negative", "composite_target")
            },
            "case_keys": [job["case_key"] for job in jobs],
            "raw_hashes": {job["case_key"]: canonical_sha256({"vignette": job["vignette"]}) for job in jobs},
        },
        "arms": list(ARMS),
        "builder_prompt_sha256": sha256_text(BUILDER_PROMPT),
        "selector_prompt_sha256": sha256_text(SELECTOR_PROMPT),
        "length_control": {
            "metric": "whitespace-delimited words after representation serialization",
            "per_case_target": "maximum of raw/flat/graph, capped at 1200",
            "pad_token": PAD_TOKEN,
            "truncation": "all conditions truncate at common cap; actual counts retained",
        },
        "primary_endpoint": "strict exact-or-frozen-synonym top-1",
        "secondary_endpoints": [
            "raw differential gold recall", "gold rank", "champion flip",
            "manual key-relation preservation", "manual time/scope false veto",
        ],
        "primary_contrasts": [f"{right} - {left}" for left, right in ((RAW, FLAT), (RAW, GRAPH), (FLAT, GRAPH))],
        "predictions": [
            "flat compression harms temporal/composite cases relative to raw",
            "typed graph improves relation preservation and strict top-1 relative to flat",
            "typed time/scope lowers false veto relative to flat",
            "if flat equals raw and graph adds no gain, the KeyFacts-sufficiency hypothesis survives",
        ],
        "failure_policy": "intention-to-analyse; raw may run after builder failure, flat/graph fail closed; no imputation",
        "development_not_confirmation": True,
        "excluded_variance_controls": ["repeat runs", "new confirmation set", "provider/retry standardisation"],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("input_hash", "model", "arms", "builder_prompt_sha256", "selector_prompt_sha256", "length_control"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["sample"]["case_keys"] != candidate["sample"]["case_keys"]:
            raise AssertionError("frozen sample changed")
        if frozen["sample"]["raw_hashes"] != candidate["sample"]["raw_hashes"]:
            raise AssertionError("frozen raw inputs changed")
        return frozen
    atomic_json(path, candidate)
    return candidate


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--per-family", type=int, default=150)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--build-representations", action="store_true")
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs = select_cases(args.per_family)
    input_paths = sorted({ROOT / job["case_path"] for job in jobs} | {BRIDGE_PATH})
    prereg = freeze_preregistration(out, jobs, combined_file_sha256(input_paths), args.model)
    environment_path = out / "environment.json"
    if not environment_path.is_file():
        atomic_json(environment_path, {
            "capabilities": dependency_capabilities(), "model": args.model,
            "workers": workers, "preregistration_sha256": file_sha256(out / "preregistration.json"),
        })
    if args.prepare_only:
        print(json.dumps(prereg["sample"], indent=2))
        return 0
    if args.build_representations:
        rows = run_builder(out, jobs, args.model, workers)
        build_manifest(out, jobs, rows)
        audit = freeze_builder_audit_sample(out, jobs, rows)
        print(f"representations served={sum(row['success'] for row in rows)}/{len(rows)}")
        print(f"frozen semantic audit cases={len(audit)}")
        return 0
    builder_path = out / "representations" / "case_representations.jsonl"
    if args.arm or args.finalize:
        builder_rows = read_jsonl(builder_path)
        if len(builder_rows) != len(jobs):
            raise AssertionError(f"incomplete representation construction: {len(builder_rows)}/{len(jobs)}")
        by_case = {str(row["case_key"]): row for row in builder_rows}
    else:
        by_case = {}
    if args.arm:
        rows = run_arm(out, jobs, by_case, args.arm, args.model, workers, bridge)
        print(f"arm={args.arm} served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.finalize:
        finalize(out, jobs)
        print(f"finalized {len(jobs) * len(ARMS)} conditions")
    if not (args.arm or args.finalize):
        raise SystemExit("choose --prepare-only, --build-representations, --arm, or --finalize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
