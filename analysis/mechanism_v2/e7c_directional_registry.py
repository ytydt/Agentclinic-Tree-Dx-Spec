#!/usr/bin/env python3
"""E7c: directional clinical relations after safe registry identity.

E7b established that exact/frozen-synonym identity restores addressability but
that an undirected ``not equivalent`` warning does not improve top-1.  E7c
isolates the missing registry mechanism: clinical direction and bounded
evidence inheritance.  It uses the same exact candidate pool and candidate
order in every selector arm.  Gold labels, benchmark options, previous ranks,
scores, source views and old selector responses are excluded from every online
payload.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tarfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    combined_file_sha256,
    file_sha256,
    json_sha256,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.e7b_registry_selector import (  # noqa: E402
    _paired_exact,
    surface_matches_gold,
    validate_selector_response,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
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
    validate_workers,
)


EXPERIMENT_ID = "E7c"
DEFAULT_RELATION_MODEL = "google/gemini-2.5-flash"
DEFAULT_SELECTOR_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E7c_directional_registry"
E7B_BUNDLE = ROOT / "analysis/mechanism_v2/results/E7b_registry_selector_FULL_RESULTS.tar.gz"
UNSAFE_PAIRS = ROOT / "analysis/mechanism_v2/results/E7_registry_replay/unsafe_merge_pairs.jsonl"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
RELATION_CHUNK_MAX = 6

ARM_EXACT = "exact_control"
ARM_GENERIC = "generic_non_equivalence"
ARM_DIRECTIONAL = "directional_relation"
ARM_BOUNDED = "bounded_inheritance"
ARMS = (ARM_EXACT, ARM_GENERIC, ARM_DIRECTIONAL, ARM_BOUNDED)

RELATION_TYPES = frozenset(
    {
        "same_as",
        "parent_of",
        "subtype_of",
        "anatomic_refinement_of",
        "temporal_refinement_of",
        "etiologic_refinement_of",
        "complication_of",
        "manifestation_of",
        "component_of",
        "contrast_mimic",
        "cooccurs_with",
        "unrelated",
        "unresolved",
    }
)
SYMMETRIC_RELATIONS = frozenset(
    {"same_as", "contrast_mimic", "cooccurs_with", "unrelated", "unresolved"}
)

RELATION_PROMPT = """Role: blinded clinical relation annotator.

For each supplied label pair, classify the clinical relationship in the
context of the vignette. Do not decide which diagnosis is the benchmark answer.
Do not merge labels merely because one string contains the other. A pair may be
true synonyms, parent/subtype, an anatomy/time/etiology refinement, a
complication/manifestation/component relation, a contrastive mimic,
co-occurring, unrelated, or unresolved.

For directional relations, source_endpoint and target_endpoint define the
statement: source RELATION target. For symmetric relations use left then right.
Qualifier span must be copied verbatim from the supplied vignette or evidence;
use an empty list when direction is not supported by one span. Return every
pair exactly once, invent no pair IDs, and add no prose outside the JSON.

Allowed relation values:
same_as, parent_of, subtype_of, anatomic_refinement_of,
temporal_refinement_of, etiologic_refinement_of, complication_of,
manifestation_of, component_of, contrast_mimic, cooccurs_with, unrelated,
unresolved.

Return strict JSON only:
{
  "relations": [{
    "pair_id": "P#",
    "source_endpoint": "left|right",
    "target_endpoint": "left|right",
    "relation": "allowed value",
    "confidence": "high|medium|low",
    "qualifier_spans": ["zero or one short verbatim span"]
  }]
}
"""

SELECTOR_PROMPT = """Role: blinded clinical task-object selector.

Choose exactly one champion from the fixed candidate list. Candidate IDs and
order are arbitrary. You may not invent, rename, merge, or compose a diagnosis.
No gold label, benchmark options, previous score/rank, source view, vote, or
registry arm is available.

Use the full vignette, candidate-local evidence, and any relation_graph edges.
Relations describe distinct clinical objects and direction; they are not votes.
When an inheritance_policy is present, it permits only the stated base-disease
evidence transfer. A more specific candidate still requires its own qualifier
evidence. A parent, manifestation, component, etiology, or complication must
not silently substitute for the complete object requested by the vignette.
Negative findings rule out only within their valid time and scope.

Return strict JSON only:
{
  "champion_id": "D#",
  "runner_up_id": "D# or empty",
  "margin": "high|medium|low",
  "requested_object": "disease|etiology|manifestation|complication|subtype|composite|unclear",
  "decisive_spans": ["up to three supplied or vignette spans"],
  "rationale": "brief contrastive reason",
  "rejected": [{"candidate_id": "D#", "why": "brief reason"}]
}
"""


def read_bundle_jsonl(bundle: Path, suffix: str) -> list[dict[str, Any]]:
    """Read one JSONL member without materialising the committed full bundle."""
    with tarfile.open(bundle, "r:gz") as archive:
        matches = [name for name in archive.getnames() if name.endswith(suffix)]
        if len(matches) != 1:
            raise AssertionError(f"expected one {suffix!r} member; found {matches}")
        stream = archive.extractfile(matches[0])
        if stream is None:
            raise FileNotFoundError(matches[0])
        return [json.loads(line) for line in stream if line.strip()]


def load_source_rows(
    bundle: Path = E7B_BUNDLE,
    unsafe_pairs_path: Path = UNSAFE_PAIRS,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    conditions = read_bundle_jsonl(bundle, "/case_conditions.jsonl")
    exact = [
        dict(row)
        for row in conditions
        if row.get("arm") == "exact_synonym"
        and row.get("selection_stratum") == "unsafe_fold"
    ]
    pairs_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_jsonl(unsafe_pairs_path):
        case_key = f"{row['slice_id']}/{row['source_id']}"
        clean = {
            "pair_id": f"P{len(pairs_by_case[case_key]) + 1}",
            "left_label": str(row.get("left_label") or ""),
            "right_label": str(row.get("right_label") or ""),
        }
        pairs_by_case[case_key].append(clean)
    exact.sort(key=lambda row: str(row["case_key"]))
    if len(exact) != 299:
        raise AssertionError(f"expected 299 E7 unsafe-fold exact rows; got {len(exact)}")
    if {str(row["case_key"]) for row in exact} != set(pairs_by_case):
        raise AssertionError("unsafe-pair and exact-condition case sets differ")
    return exact, dict(pairs_by_case)


def _label_evidence(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for candidate in row.get("candidates") or []:
        label = str(candidate.get("label") or "")
        result.setdefault(normalize_label(label), dict(candidate))
    return result


def make_relation_payload(
    row: Mapping[str, Any], pairs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    evidence = _label_evidence(row)
    payload_pairs: list[dict[str, Any]] = []
    for pair in pairs:
        left = str(pair["left_label"])
        right = str(pair["right_label"])
        left_ev = evidence.get(normalize_label(left), {})
        right_ev = evidence.get(normalize_label(right), {})
        payload_pairs.append(
            {
                "pair_id": str(pair["pair_id"]),
                "left": {
                    "label": left,
                    "support_spans": list(left_ev.get("support_spans") or [])[:3],
                    "contradict_spans": list(left_ev.get("contradict_spans") or [])[:2],
                },
                "right": {
                    "label": right,
                    "support_spans": list(right_ev.get("support_spans") or [])[:3],
                    "contradict_spans": list(right_ev.get("contradict_spans") or [])[:2],
                },
            }
        )
    return {
        "case_id": str(row["case_key"]),
        "vignette": str(row.get("vignette") or "")[:6000],
        "pairs": payload_pairs,
    }


def validate_relation_response(
    response: Mapping[str, Any], expected_pair_ids: set[str]
) -> str | None:
    relations = response.get("relations")
    if not isinstance(relations, list):
        return "relations must be a list"
    seen: set[str] = set()
    for relation in relations:
        if not isinstance(relation, Mapping):
            return "each relation must be an object"
        pair_id = str(relation.get("pair_id") or "")
        if pair_id not in expected_pair_ids or pair_id in seen:
            return f"invalid or duplicate pair_id: {pair_id!r}"
        seen.add(pair_id)
        rel = str(relation.get("relation") or "")
        if rel not in RELATION_TYPES:
            return f"invalid relation for {pair_id}: {rel!r}"
        source = str(relation.get("source_endpoint") or "")
        target = str(relation.get("target_endpoint") or "")
        if source not in {"left", "right"} or target not in {"left", "right"}:
            return f"invalid endpoints for {pair_id}"
        if source == target:
            return f"source and target must differ for {pair_id}"
        if rel in SYMMETRIC_RELATIONS and (source, target) != ("left", "right"):
            return f"symmetric relation must use left->right for {pair_id}"
        if str(relation.get("confidence") or "").lower() not in {
            "high",
            "medium",
            "low",
        }:
            return f"invalid confidence for {pair_id}"
        spans = relation.get("qualifier_spans") or []
        if not isinstance(spans, list) or len(spans) > 1:
            return f"invalid qualifier_spans for {pair_id}"
    if seen != expected_pair_ids:
        return f"missing pair ids: {sorted(expected_pair_ids - seen)}"
    return None


def inheritance_policy(relation: str) -> str:
    if relation == "parent_of":
        return (
            "base disease evidence may flow source(parent)->target(child); "
            "target still requires independent qualifier evidence"
        )
    if relation in {
        "subtype_of",
        "anatomic_refinement_of",
        "temporal_refinement_of",
        "etiologic_refinement_of",
    }:
        return (
            "base disease evidence may flow target(base)->source(refinement); "
            "source still requires independent qualifier evidence"
        )
    if relation == "same_as":
        return (
            "evidence may be considered bidirectionally, but labels remain separate "
            "in this experiment"
        )
    return "no evidence inheritance; relation informs task-object contrast only"


def _candidate_id_by_label(row: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for candidate in row.get("candidates") or []:
        result.setdefault(
            normalize_label(str(candidate.get("label") or "")),
            str(candidate.get("candidate_id") or ""),
        )
    return result


def build_relation_graph(
    row: Mapping[str, Any],
    pairs: Sequence[Mapping[str, Any]],
    relation_response: Mapping[str, Any],
    arm: str,
) -> list[dict[str, Any]]:
    if arm == ARM_EXACT:
        return []
    candidate_ids = _candidate_id_by_label(row)
    pairs_by_id = {str(pair["pair_id"]): pair for pair in pairs}
    typed_by_id = {
        str(item.get("pair_id") or ""): item
        for item in relation_response.get("relations") or []
        if isinstance(item, Mapping)
    }
    graph: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for pair_id, pair in pairs_by_id.items():
        left_id = candidate_ids.get(normalize_label(str(pair["left_label"])))
        right_id = candidate_ids.get(normalize_label(str(pair["right_label"])))
        if not left_id or not right_id or left_id == right_id:
            continue
        if arm == ARM_GENERIC:
            item = {
                "source_id": left_id,
                "target_id": right_id,
                "relation": "generic_non_equivalence",
                "confidence": "not_applicable",
                "qualifier_spans": [],
            }
        else:
            typed = typed_by_id.get(pair_id)
            if not typed:
                continue
            source_label = str(
                pair["left_label"]
                if typed.get("source_endpoint") == "left"
                else pair["right_label"]
            )
            target_label = str(
                pair["left_label"]
                if typed.get("target_endpoint") == "left"
                else pair["right_label"]
            )
            source_id = candidate_ids.get(normalize_label(source_label))
            target_id = candidate_ids.get(normalize_label(target_label))
            if not source_id or not target_id or source_id == target_id:
                continue
            relation_name = str(typed.get("relation") or "unresolved")
            item = {
                "source_id": source_id,
                "target_id": target_id,
                "relation": relation_name,
                "confidence": str(typed.get("confidence") or "low"),
                "qualifier_spans": list(typed.get("qualifier_spans") or [])[:2],
            }
            if arm == ARM_BOUNDED:
                item["inheritance_policy"] = inheritance_policy(relation_name)
        edge_key = (item["source_id"], item["target_id"], item["relation"])
        if edge_key not in seen_edges:
            seen_edges.add(edge_key)
            graph.append(item)
    return graph


def make_selector_payload(
    row: Mapping[str, Any], relation_graph: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "case_id": str(row["case_key"]),
        "vignette": str(row.get("vignette") or "")[:6000],
        "candidates": [dict(candidate) for candidate in row.get("candidates") or []],
        "relation_graph": [dict(edge) for edge in relation_graph],
    }


def validate_e7c_selector(
    response: Mapping[str, Any], candidate_ids: set[str]
) -> str | None:
    error = validate_selector_response(response, candidate_ids)
    if error:
        return error
    requested = str(response.get("requested_object") or "").strip().lower()
    if requested not in {
        "disease",
        "etiology",
        "manifestation",
        "complication",
        "subtype",
        "composite",
        "unclear",
    }:
        return f"invalid requested_object: {requested!r}"
    return None


def summarize(rows: Sequence[Mapping[str, Any]], relation_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def group(group_rows: list[Mapping[str, Any]], name: str) -> dict[str, Any]:
        by_arm: dict[str, Any] = {}
        for arm in ARMS:
            arm_rows = [row for row in group_rows if row["arm"] == arm]
            served = [row for row in arm_rows if row["success"]]
            exposed = [row for row in served if row["gold_exposure_hit"]]
            by_arm[arm] = {
                "n_intention": len(arm_rows),
                "n_served": len(served),
                "n_failed": len(arm_rows) - len(served),
                "gold_exposure_n": sum(bool(row["gold_exposure_hit"]) for row in served),
                "gold_top1_n": sum(bool(row["gold_top1"]) for row in served),
                "gold_top1_rate": round(
                    sum(bool(row["gold_top1"]) for row in served) / len(served), 6
                ) if served else None,
                "exposure_to_top1": round(
                    sum(bool(row["gold_top1"]) for row in exposed) / len(exposed), 6
                ) if exposed else None,
                "mean_relation_edges": round(
                    sum(int(row["relation_n"]) for row in served) / len(served), 6
                ) if served else None,
                "requested_object": dict(Counter(str(row.get("requested_object")) for row in served)),
            }
        comparisons = [
            _paired_exact(group_rows, ARM_GENERIC, ARM_EXACT),
            _paired_exact(group_rows, ARM_DIRECTIONAL, ARM_EXACT),
            _paired_exact(group_rows, ARM_DIRECTIONAL, ARM_GENERIC),
            _paired_exact(group_rows, ARM_BOUNDED, ARM_DIRECTIONAL),
            _paired_exact(group_rows, ARM_BOUNDED, ARM_EXACT),
        ]
        return {"group_id": name, "n_cases": len({row["case_key"] for row in group_rows}), "arms": by_arm, "paired": comparisons}

    relation_items = [
        item
        for row in relation_rows
        if row.get("success")
        for item in (row.get("response", {}).get("relations") or [])
    ]
    return {
        "experiment_id": EXPERIMENT_ID,
        "groups": [
            group(list(rows), "ALL"),
            group([row for row in rows if row["family"] == "DA"], "DA"),
            group([row for row in rows if row["family"] == "MCR"], "MCR"),
        ],
        "relation_typing": {
            "n_chunk_calls": len(relation_rows),
            "n_cases": len({str(row.get("case_key")) for row in relation_rows}),
            "n_successful_chunks": sum(bool(row.get("success")) for row in relation_rows),
            "n_pairs_typed": len(relation_items),
            "relation_distribution": dict(Counter(str(item.get("relation")) for item in relation_items)),
            "confidence_distribution": dict(Counter(str(item.get("confidence")) for item in relation_items)),
        },
    }


def build_audit_queue(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[str(row["case_key"])].append(row)
    queue: list[dict[str, Any]] = []
    for case_key, case_rows in by_case.items():
        if len(case_rows) != len(ARMS):
            continue
        champions = {normalize_label(str(row.get("champion_label") or "")) for row in case_rows}
        correctness = {bool(row.get("gold_top1")) for row in case_rows}
        bounded = next(row for row in case_rows if row["arm"] == ARM_BOUNDED)
        if len(champions) == 1 and len(correctness) == 1:
            continue
        queue.append(
            {
                "case_key": case_key,
                "family": bounded["family"],
                "gold": bounded["gold"],
                "vignette": bounded["vignette"],
                "arms": [
                    {
                        "arm": row["arm"],
                        "champion_label": row.get("champion_label"),
                        "gold_top1": row.get("gold_top1"),
                        "requested_object": row.get("requested_object"),
                        "relation_graph": row.get("relation_graph"),
                        "response": row.get("response"),
                    }
                    for row in sorted(case_rows, key=lambda item: ARMS.index(str(item["arm"])))
                ],
            }
        )
    return sorted(
        queue,
        key=lambda row: (
            -sum(bool(arm.get("gold_top1")) for arm in row["arms"]),
            str(row["case_key"]),
        ),
    )


def write_case_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "case_key", "family", "arm", "success", "gold_exposure_hit", "gold_top1",
        "champion_label", "runner_up_label", "margin", "requested_object",
        "candidate_n", "relation_n", "relation_typing_success", "cache_hit", "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--relation-model", default=DEFAULT_RELATION_MODEL)
    parser.add_argument("--selector-model", default=DEFAULT_SELECTOR_MODEL)
    parser.add_argument(
        "--model",
        default="",
        help="compatibility override: use one model for both stages",
    )
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--bundle", type=Path, default=E7B_BUNDLE)
    parser.add_argument("--unsafe-pairs", type=Path, default=UNSAFE_PAIRS)
    parser.add_argument("--bridge", type=Path, default=BRIDGE_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.model:
        args.relation_model = args.model
        args.selector_model = args.model
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(args.bridge)
    exact_rows, pairs_by_case = load_source_rows(args.bundle, args.unsafe_pairs)
    wanted = {str(value) for value in args.case_id}
    if wanted:
        exact_rows = [
            row for row in exact_rows
            if str(row["case_key"]) in wanted
            or str(row["source_id"]) in wanted
            or str(row["case_id"]) in wanted
        ]
    if args.limit:
        exact_rows = exact_rows[: int(args.limit)]
    input_hash = combined_file_sha256([args.bundle, args.unsafe_pairs, args.bridge])
    implementation_hashes = {
        path.name: file_sha256(path)
        for path in (
            Path(__file__),
            ROOT / "analysis/mechanism_v2/online_runner.py",
            ROOT / "analysis/mechanism_v2/common.py",
        )
    }
    started = datetime.now(timezone.utc)
    prereg = {
        "experiment_id": EXPERIMENT_ID,
        "created_before_calls_utc": started.isoformat(),
        "source_commit": source_commit(),
        "input_hash": input_hash,
        "models": {
            "relation_annotator": args.relation_model,
            "selector": args.selector_model,
        },
        "workers": workers,
        "selection": {
            "rule": "all E7a unsafe-fold cases with an E7b exact-synonym fixed pool",
            "n_cases": len(exact_rows),
            "case_keys": [str(row["case_key"]) for row in exact_rows],
        },
        "arms": list(ARMS),
        "primary_endpoint": "displayed-label exact/frozen-synonym pre-mapper top-1",
        "primary_comparisons": [
            "directional_relation vs exact_control",
            "bounded_inheritance vs directional_relation",
        ],
        "payload_blinding": "no gold/options/old ranks/scores/source views/old responses",
        "candidate_contract": "same exact registry pool and order in every selector arm",
        "failure_policy": "intention-to-analyse; failed relation calls yield no typed edges and remain flagged",
        "relation_chunk_max_pairs": RELATION_CHUNK_MAX,
        "development_not_confirmation": True,
        "prompt_sha256": {
            "relation": sha256_text(RELATION_PROMPT),
            "selector": sha256_text(SELECTOR_PROMPT),
        },
        "implementation_sha256": implementation_hashes,
    }
    prereg_path = out / "preregistration.json"
    if prereg_path.is_file():
        frozen = json.loads(prereg_path.read_text(encoding="utf-8"))
        for key in ("experiment_id", "input_hash", "models", "arms", "prompt_sha256"):
            if frozen.get(key) != prereg.get(key):
                raise AssertionError(f"preregistration mismatch for {key}")
        if frozen.get("selection", {}).get("case_keys") != prereg["selection"]["case_keys"]:
            raise AssertionError("preregistered case set differs")
        prereg = frozen
        started = datetime.fromisoformat(prereg["created_before_calls_utc"])
    else:
        atomic_json(prereg_path, prereg)
    if args.prepare_only:
        pair_n = sum(len(pairs_by_case[row["case_key"]]) for row in exact_rows)
        chunk_n = sum(
            (len(pairs_by_case[row["case_key"]]) + RELATION_CHUNK_MAX - 1)
            // RELATION_CHUNK_MAX
            for row in exact_rows
        )
        print(json.dumps({"status": "prepared", "n_cases": len(exact_rows), "n_pairs": pair_n, "n_relation_chunks": chunk_n}, indent=2))
        return 0

    telemetry_path = out / "telemetry.jsonl"
    relation_caller = OnlineJSONCaller(
        out_dir=out,
        model=args.relation_model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )
    selector_caller = OnlineJSONCaller(
        out_dir=out,
        model=args.selector_model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )
    log_lines = [
        f"started_at_utc={started.isoformat()}",
        f"source_commit={source_commit()}",
        f"relation_model={args.relation_model}",
        f"selector_model={args.selector_model}",
        f"workers={workers}",
        f"n_cases={len(exact_rows)}",
        f"n_relation_pairs={sum(len(pairs_by_case[row['case_key']]) for row in exact_rows)}",
        f"relation_chunk_max_pairs={RELATION_CHUNK_MAX}",
        f"input_hash={input_hash}",
    ]

    relation_jobs: list[dict[str, Any]] = []
    for row in exact_rows:
        pairs = pairs_by_case[str(row["case_key"])]
        for start in range(0, len(pairs), RELATION_CHUNK_MAX):
            relation_jobs.append(
                {
                    "source": row,
                    "chunk_index": start // RELATION_CHUNK_MAX,
                    "pairs": pairs[start : start + RELATION_CHUNK_MAX],
                }
            )
    log_lines.append(f"n_relation_chunks={len(relation_jobs)}")

    def classify(job: Mapping[str, Any]) -> dict[str, Any]:
        row = job["source"]
        pairs = job["pairs"]
        payload = make_relation_payload(row, pairs)
        expected = {str(pair["pair_id"]) for pair in pairs}
        outcome = relation_caller.call(
            module="E7cClinicalRelation",
            prompt=RELATION_PROMPT,
            payload=payload,
            validator=lambda response: validate_relation_response(response, expected),
            cache_only=args.cache_only,
        )
        return {
            "case_key": row["case_key"],
            "family": row["family"],
            "chunk_index": job["chunk_index"],
            "success": outcome.success,
            "error": outcome.error,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
            "pairs": pairs,
            "response": outcome.response,
        }

    relation_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(classify, job): job for job in relation_jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            source = job["source"]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "case_key": source["case_key"],
                    "family": source["family"],
                    "chunk_index": job["chunk_index"],
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "cache_hit": False,
                    "cache_key": "",
                    "payload_sha256": canonical_sha256(make_relation_payload(source, job["pairs"])),
                    "pairs": job["pairs"],
                    "response": {},
                }
            relation_rows.append(result)
            if done % 25 == 0 or done == len(relation_jobs):
                message = f"relation_completed={done}/{len(relation_jobs)} failures={sum(not x['success'] for x in relation_rows)}"
                print(message, flush=True)
                log_lines.append(message)
    relation_rows.sort(key=lambda row: (str(row["case_key"]), int(row["chunk_index"])))
    write_jsonl(out / "relation_classifications.jsonl", relation_rows)
    relation_chunks_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation_row in relation_rows:
        relation_chunks_by_case[str(relation_row["case_key"])].append(relation_row)
    relation_by_case: dict[str, dict[str, Any]] = {}
    for case_key, chunks in relation_chunks_by_case.items():
        relation_by_case[case_key] = {
            "success": all(bool(chunk.get("success")) for chunk in chunks),
            "response": {
                "relations": [
                    item
                    for chunk in chunks
                    if chunk.get("success")
                    for item in (chunk.get("response", {}).get("relations") or [])
                ]
            },
        }

    jobs: list[dict[str, Any]] = []
    for row in exact_rows:
        relation_row = relation_by_case[str(row["case_key"])]
        for arm in ARMS:
            graph = build_relation_graph(
                row,
                pairs_by_case[str(row["case_key"])],
                relation_row.get("response") or {},
                arm,
            )
            jobs.append(
                {
                    "source": row,
                    "arm": arm,
                    "relation_graph": graph,
                    "relation_success": bool(relation_row.get("success")),
                    "payload": make_selector_payload(row, graph),
                }
            )

    def select(job: Mapping[str, Any]) -> dict[str, Any]:
        source = job["source"]
        candidate_map = {
            str(candidate["candidate_id"]): str(candidate["label"])
            for candidate in source.get("candidates") or []
        }
        outcome = selector_caller.call(
            module="E7cRegistrySelector",
            prompt=SELECTOR_PROMPT,
            payload=job["payload"],
            validator=lambda response: validate_e7c_selector(response, set(candidate_map)),
            cache_only=args.cache_only,
        )
        response = outcome.response
        champion_id = str(response.get("champion_id") or "") if outcome.success else ""
        runner_id = str(response.get("runner_up_id") or "") if outcome.success else ""
        champion_label = candidate_map.get(champion_id, "")
        runner_label = candidate_map.get(runner_id, "")
        gold = str(source.get("gold") or "")
        candidates = list(source.get("candidates") or [])
        return {
            "case_key": source["case_key"],
            "case_id": source.get("case_id"),
            "slice_id": source.get("slice_id"),
            "source_id": source.get("source_id"),
            "family": source["family"],
            "gold": gold,
            "vignette": source.get("vignette"),
            "arm": job["arm"],
            "success": outcome.success,
            "error": outcome.error,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
            "candidate_n": len(candidates),
            "relation_n": len(job["relation_graph"]),
            "relation_typing_success": job["relation_success"],
            "candidates": candidates,
            "relation_graph": job["relation_graph"],
            "response": response,
            "champion_id": champion_id,
            "champion_label": champion_label,
            "runner_up_label": runner_label,
            "margin": str(response.get("margin") or ""),
            "requested_object": str(response.get("requested_object") or ""),
            "gold_exposure_hit": any(
                surface_matches_gold(str(candidate.get("label") or ""), gold, bridge)
                for candidate in candidates
            ),
            "gold_top1": surface_matches_gold(champion_label, gold, bridge),
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(select, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                source = job["source"]
                gold = str(source.get("gold") or "")
                result = {
                    "case_key": source["case_key"],
                    "case_id": source.get("case_id"),
                    "slice_id": source.get("slice_id"),
                    "source_id": source.get("source_id"),
                    "family": source["family"],
                    "gold": gold,
                    "vignette": source.get("vignette"),
                    "arm": job["arm"],
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "cache_hit": False,
                    "cache_key": "",
                    "payload_sha256": canonical_sha256(job["payload"]),
                    "candidate_n": len(source.get("candidates") or []),
                    "relation_n": len(job["relation_graph"]),
                    "relation_typing_success": job["relation_success"],
                    "candidates": source.get("candidates") or [],
                    "relation_graph": job["relation_graph"],
                    "response": {},
                    "champion_id": "",
                    "champion_label": "",
                    "runner_up_label": "",
                    "margin": "",
                    "requested_object": "",
                    "gold_exposure_hit": any(
                        surface_matches_gold(str(candidate.get("label") or ""), gold, bridge)
                        for candidate in source.get("candidates") or []
                    ),
                    "gold_top1": False,
                }
            rows.append(result)
            if done % 25 == 0 or done == len(jobs):
                message = f"selector_completed={done}/{len(jobs)} failures={sum(not x['success'] for x in rows)}"
                print(message, flush=True)
                log_lines.append(message)
    rows.sort(key=lambda row: (str(row["case_key"]), ARMS.index(str(row["arm"]))))
    write_jsonl(out / "case_conditions.jsonl", rows)
    write_case_csv(out / "case_summary.csv", rows)
    queue = build_audit_queue(rows)
    write_jsonl(out / "audit_queue.jsonl", queue)
    summary = summarize(rows, relation_rows)
    telemetry_rows = read_jsonl(telemetry_path)
    telemetry = aggregate_telemetry(telemetry_rows)
    summary.update(
        {
            "source_commit": source_commit(),
            "input_hash": input_hash,
            "models": prereg["models"],
            "workers": workers,
            "n_cases": len(exact_rows),
            "n_conditions": len(rows),
            "n_audit_queue": len(queue),
            "telemetry": telemetry,
            "prompt_sha256": prereg["prompt_sha256"],
            "implementation_sha256": prereg["implementation_sha256"],
            "development_not_confirmation": True,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    atomic_json(out / "summary.json", summary)
    manifest = RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id="__".join(ARMS),
        dataset="all 299 E7a unsafe-fold development cases",
        model=(
            f"relation={args.relation_model};selector={args.selector_model}"
        ),
        workers=workers,
        rag=False,
        source_commit=source_commit(),
        prompt_hashes=prereg["prompt_sha256"],
        input_hash=input_hash,
        selection_freeze="all unsafe-fold cases; exact E7b pool/order fixed across four arms",
        endpoint_contract=(
            "clean vignette -> fixed exact registry -> blinded relation treatment -> "
            "fresh task-object selector -> displayed-label strict pre-mapper top-1"
        ),
        excluded_variance_controls=[
            "repeated multi-run execution",
            "expanded confirmation set",
            "provider/retry standardization arm",
        ],
        capabilities=dependency_capabilities(),
        created_at_utc=started.isoformat(),
    )
    manifest.write(out / "manifest.json")
    finished = datetime.now(timezone.utc)
    log_lines.extend(
        [
            f"finished_at_utc={finished.isoformat()}",
            f"duration_seconds={(finished-started).total_seconds():.3f}",
            f"relation_failures={sum(not row['success'] for row in relation_rows)}",
            f"selector_failures={sum(not row['success'] for row in rows)}",
            f"semantic_calls={telemetry['semantic_calls']}",
            f"physical_attempts={telemetry['physical_attempts']}",
            f"summary_hash={json_sha256(summary)}",
            "status=complete_e7c_directional_registry",
        ]
    )
    (out / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary["groups"][0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
