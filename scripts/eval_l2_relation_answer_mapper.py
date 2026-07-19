#!/usr/bin/env python3
"""Evaluate gold-blind relation-aware L2→MCQ mapping on frozen A/B-b1 ranks."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import eval_l1_evidence_bfs as bfs  # noqa: E402
import eval_l2_branch_generation_ab as ab  # noqa: E402
import eval_l2_targeted_gapfill_hybrid as hybrid  # noqa: E402
import eval_partial_flow_talp17 as talp17  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    leaf_rows_from_tree,
    load_offline_resolver,
    stable_hash,
)
from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    _normalize_label,
)
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

PROTOCOL = ROOT / "eval_fixtures" / "l2_relation_answer_mapper_protocol_v1.json"
OLD_RECORDS = ROOT / "logs" / "l2_mcq_option_from_ranking_v1" / "records.json"
V2_ADJ = ROOT / "eval_fixtures" / "l2_relation_answer_mapper_adjudication_v2.json"
A_CORRECTED = (
    ROOT / "logs" / "l2_mcq_option_from_ranking_v1" / "binding_audit"
    / "synonym_rank_corrected_records.json"
)
B_CORRECTED = (
    ROOT / "logs" / "l2_mcq_option_from_ranking_v1" / "binding_audit_b_b1"
    / "synonym_rank_corrected_records.json"
)
DEFAULT_OUT = ROOT / "logs" / "l2_mcq_mapper_v2"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
ALL_MODES = (
    "historical_oracle_assisted",
    "deterministic_gold_blind",
    "typed_llm",
    "typed_llm_disagreement_rag",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".%d.tmp" % os.getpid())
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_protocol(protocol: Mapping[str, Any]) -> dict[str, Any]:
    checks = []

    def check(path_value: str, expected: str, label: str) -> None:
        path = ROOT / path_value
        actual = _sha256(path)
        checks.append({
            "label": label,
            "path": path_value,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "valid": actual == expected,
        })

    for arm, row in protocol["arms"].items():
        check(
            row["generation_manifest"],
            row["generation_manifest_sha256"],
            "%s_generation_manifest" % arm,
        )
    frozen = protocol["frozen_ranking"]
    check(frozen["path"], frozen["sha256"], "frozen_ranking")
    for name, row in protocol["knowledge_assets"].items():
        if row.get("sha256"):
            check(row["path"], row["sha256"], name)
        elif row.get("config_sha256"):
            check(
                str(Path(row["path"]) / "config.json"),
                row["config_sha256"],
                "%s_config" % name,
            )
    for name, row in protocol["adjudication_assets"].items():
        if isinstance(row, Mapping) and row.get("sha256"):
            check(row["path"], row["sha256"], name)
    invalid = [row for row in checks if not row["valid"]]
    if invalid:
        raise ValueError("frozen protocol hash mismatch: %s" % invalid)
    return {"valid": True, "checks": checks}


def _tree(arm: str, case_id: str, replicate: int) -> Mapping[str, Any]:
    if arm == "A":
        path = (
            ROOT / "logs" / "l2_branch_generation_ab_v1" / "generation"
            / "traces" / "A" / ("r%02d__%s.json" % (replicate, case_id))
        )
        return _read_json(path)["tree"]
    if arm == "ALL_B_b1":
        path = (
            ROOT / "logs" / "l2_targeted_gapfill_hybrid_v1" / "generation"
            / "traces" / "_case" / ("r%02d__%s.json" % (replicate, case_id))
        )
        return hybrid._arm_trace(_read_json(path), "ALL_B_b1")["tree"]
    raise ValueError("unsupported frozen arm: %s" % arm)


def _split_case(case_text: str) -> tuple[str, str]:
    body = str(case_text).split("\nOptions:", 1)[0].strip()
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return "", ""
    question_index = None
    for index in range(len(lines) - 1, -1, -1):
        if "?" in lines[index]:
            question_index = index
            break
    if question_index is None:
        return body, lines[-1]
    question = " ".join(lines[question_index:])
    vignette = "\n".join(lines[:question_index]).strip()
    return vignette, question


def _case_options(case: Mapping[str, Any]) -> dict[str, str]:
    annotation = case.get("annotation") or {}
    options = annotation.get("source_options")
    if isinstance(options, Mapping) and options:
        return {
            str(letter).upper(): str(text).strip()
            for letter, text in sorted(options.items())
        }
    import analyze_l2_mcq_option_from_ranking as legacy
    return legacy._parse_options_from_case_text(str(case.get("case_text") or ""))


def _gold_letter(case: Mapping[str, Any], options: Mapping[str, str]) -> str:
    target = _normalize_label(str(case.get("gold_option") or ""))
    exact = [
        letter for letter, text in options.items()
        if _normalize_label(text) == target
    ]
    if len(exact) != 1:
        raise ValueError(
            "%s: gold option letter not uniquely resolved after mapping"
            % case.get("id")
        )
    return exact[0]


def _historical_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    option_maps: dict[str, dict[str, Any]] = {}
    finite = sorted({
        int(row["rank"]) for row in (record.get("option_maps") or {}).values()
        if row.get("rank") is not None
    })
    dense = {rank: index for index, rank in enumerate(finite, start=1)}
    fallback_rank = len(finite) + 1
    for letter, row in sorted((record.get("option_maps") or {}).items()):
        rank = row.get("rank")
        leaf_id = row.get("leaf_id")
        option_maps[str(letter)] = {
            "relation_type": "equivalent" if row.get("matched") else "unknown",
            "matched_leaf_ids": [str(leaf_id)] if leaf_id else [],
            "clone_leaf_ids": [str(leaf_id)] if leaf_id else [],
            "matched": bool(row.get("matched")),
            "best_rank": rank,
            "support_score": 1.0 / rank if rank else 0.0,
            "posterior": 0.0,
            "confidence": "high" if row.get("matched") else "low",
            "confidence_score": float(row.get("score") or 0.0),
            "rationale": "historical Jaccard/gold-alias binding",
            "source": "historical_oracle_assisted",
            "option_rank": dense[int(rank)] if rank is not None else fallback_rank,
        }
    order = sorted(
        option_maps,
        key=lambda letter: (
            option_maps[letter]["best_rank"] is None,
            option_maps[letter]["best_rank"]
            if option_maps[letter]["best_rank"] is not None else 10**9,
            letter,
        ),
    )
    return {
        "schema_version": 1,
        "case_id": record["case_id"],
        "mode": "historical_oracle_assisted",
        "question_target": "historical_untyped",
        "option_maps": option_maps,
        "option_order": order,
        "clone_groups": [],
        "audit": {
            "gold_blind": False,
            "historical_reference_only": True,
            "gold_alias_used": True,
        },
    }


def _build_v2_adjudication(
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Convert the signed-off v1 A correction pass into a blind semantic sheet.

    The fixture deliberately stores option text and accepted leaf labels, not
    gold letters. It is suitable for relation auditing but is not represented
    as a new human review.
    """
    source_payload = _read_json(A_CORRECTED)
    records = source_payload.get("records") or ()
    by_case_letter: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        for letter, row in (record.get("option_maps") or {}).items():
            by_case_letter[(str(record["case_id"]), str(letter))].append(row)

    rows = []
    for case in cases:
        case_id = str(case["id"])
        for letter, text in _case_options(case).items():
            source_rows = by_case_letter.get((case_id, letter), [])
            labels = sorted({
                _normalize_label(str(row.get("leaf_label") or ""))
                for row in source_rows if row.get("matched") and row.get("leaf_label")
            })
            rows.append({
                "case_id": case_id,
                "option_letter": letter,
                "option_text": text,
                "relation_type": "equivalent" if labels else "unknown",
                "acceptable_leaf_labels": labels,
                "adjudicated_relation_present": bool(labels),
                "source": "manual_v1_A_binding_correction_and_acceptance",
                "review_status": "transcribed_from_v1_not_newly_human_signed",
            })
    return {
        "schema_version": 2,
        "description": (
            "Gold-blind relation review fixture transcribed from the existing "
            "manual v1 Arm-A option-binding adjudication. Gold letters are "
            "deliberately absent; scoring joins them only after mapping."
        ),
        "human_signed_off": False,
        "n_cases": len(cases),
        "n_rows": len(rows),
        "source_assets": [
            str(A_CORRECTED.relative_to(ROOT)),
            str(B_CORRECTED.relative_to(ROOT)),
            "eval_fixtures/l2_mcq_option_binding_adjudication_v1.json",
            "eval_fixtures/l2_mcq_option_synonym_rank_v1.json",
        ],
        "rows": rows,
    }


def _expected_index(adjudication: Mapping[str, Any]) -> dict[tuple[str, str], dict]:
    return {
        (str(row["case_id"]), str(row["option_letter"])): dict(row)
        for row in adjudication.get("rows") or ()
    }


def _score(
    *,
    case: Mapping[str, Any],
    arm: str,
    replicate: int,
    projection: Mapping[str, Any],
    leaves: Sequence[Mapping[str, Any]],
    expected: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    options = _case_options(case)
    gold_letter = _gold_letter(case, options)
    option_maps = projection["option_maps"]
    gold = option_maps[gold_letter]
    gold_rank = gold.get("best_rank")
    gold_option_rank = int(gold.get("option_rank") or (len(options) + 1))
    distractor_ranks = [
        row.get("best_rank") for letter, row in option_maps.items()
        if letter != gold_letter
    ]
    strict = bool(
        gold_rank is not None
        and all(rank is None or int(gold_rank) < int(rank)
                for rank in distractor_ranks)
    )
    # An unmatched or unranked gold relation is not an answer ranking. Without
    # this gate, an all-unmatched option set would spuriously score Top-1.
    top1 = bool(gold_rank is not None and gold_option_rank <= 1)
    top2 = bool(gold_rank is not None and gold_option_rank <= 2)
    rr = 1.0 / gold_option_rank if gold_rank is not None else 0.0

    label_by_id = {
        str(row["leaf_id"]): _normalize_label(str(row["leaf_label"]))
        for row in leaves
    }
    relation_tp = relation_fp = relation_fn = 0
    option_audit = {}
    for letter, mapped in sorted(option_maps.items()):
        exp = expected.get((str(case["id"]), letter), {})
        expected_labels = set(exp.get("acceptable_leaf_labels") or ())
        predicted_labels = {
            label_by_id[value]
            for value in mapped.get("clone_leaf_ids") or ()
            if value in label_by_id
        }
        relation_expected = bool(exp.get("adjudicated_relation_present"))
        hit = bool(predicted_labels & expected_labels)
        predicted = bool(predicted_labels)
        if relation_expected and hit:
            relation_tp += 1
        elif predicted and not hit:
            relation_fp += 1
        if relation_expected and not hit:
            relation_fn += 1
        option_audit[letter] = {
            "expected_relation_present": relation_expected,
            "expected_leaf_labels": sorted(expected_labels),
            "predicted_leaf_labels": sorted(predicted_labels),
            "relation_hit": hit,
        }

    if not gold.get("matched"):
        failure = "relation_miss_or_l2_absent"
    elif gold_rank is None:
        failure = "matched_but_unranked"
    elif strict:
        failure = "success_strict"
    elif top1:
        failure = "same_rank_non_strict_success"
    else:
        failure = "option_rank_loss"
    return {
        "arm": arm,
        "mapper_mode": projection["mode"],
        "case_id": case["id"],
        "replicate": replicate,
        "gold_letter": gold_letter,
        "gold_best_rank": gold_rank,
        "gold_option_rank": gold_option_rank,
        "option_top1": top1,
        "option_top2": top2,
        "option_rr": rr,
        "gold_beats_all_strict": strict,
        "gold_option_mapped": bool(gold.get("matched")),
        "gold_option_ranked": gold_rank is not None,
        "matched_but_unranked": bool(gold.get("matched") and gold_rank is None),
        "failure_stage": failure,
        "question_target": projection.get("question_target"),
        "option_order": list(projection.get("option_order") or ()),
        "option_maps": option_maps,
        "relation_tp": relation_tp,
        "relation_fp": relation_fp,
        "relation_fn": relation_fn,
        "option_relation_audit": option_audit,
        "schema_valid": bool(
            (projection.get("audit") or {}).get("typed", {}).get(
                "schema_valid", True,
            )
        ),
    }


def _aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(records)
    total_tp = sum(int(row["relation_tp"]) for row in records)
    total_fp = sum(int(row["relation_fp"]) for row in records)
    total_fn = sum(int(row["relation_fn"]) for row in records)
    precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    return {
        "n_units": n,
        "n_cases": len({str(row["case_id"]) for row in records}),
        "top1": statistics.fmean(float(row["option_top1"]) for row in records)
        if records else 0.0,
        "top2": statistics.fmean(float(row["option_top2"]) for row in records)
        if records else 0.0,
        "mrr": statistics.fmean(float(row["option_rr"]) for row in records)
        if records else 0.0,
        "gold_beats_all_strict": statistics.fmean(
            float(row["gold_beats_all_strict"]) for row in records
        ) if records else 0.0,
        "gold_option_coverage": statistics.fmean(
            float(row["gold_option_mapped"]) for row in records
        ) if records else 0.0,
        "gold_option_ranked": statistics.fmean(
            float(row["gold_option_ranked"]) for row in records
        ) if records else 0.0,
        "matched_but_unranked": sum(
            int(row["matched_but_unranked"]) for row in records
        ),
        "relation_precision": precision,
        "relation_recall": recall,
        "relation_counts": {"tp": total_tp, "fp": total_fp, "fn": total_fn},
        "failure_stages": dict(sorted(Counter(
            str(row["failure_stage"]) for row in records
        ).items())),
        "schema_valid_rate": statistics.fmean(
            float(row["schema_valid"]) for row in records
        ) if records else 0.0,
    }


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * probability
    lo, hi = int(math.floor(index)), int(math.ceil(index))
    if lo == hi:
        return float(ordered[lo])
    weight = index - lo
    return float(ordered[lo] * (1 - weight) + ordered[hi] * weight)


def _bootstrap(
    records: Sequence[Mapping[str, Any]], *, repeats: int, seed: int,
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row["case_id"])].append(row)
    case_ids = sorted(grouped)
    rng = random.Random(seed)
    distributions = {"top1": [], "top2": [], "mrr": []}
    for _ in range(repeats):
        sampled = [rng.choice(case_ids) for _ in case_ids]
        sample_rows = [
            row for case_id in sampled for row in grouped[case_id]
        ]
        distributions["top1"].append(statistics.fmean(
            float(row["option_top1"]) for row in sample_rows
        ))
        distributions["top2"].append(statistics.fmean(
            float(row["option_top2"]) for row in sample_rows
        ))
        distributions["mrr"].append(statistics.fmean(
            float(row["option_rr"]) for row in sample_rows
        ))
    return {
        metric: {
            "mean": statistics.fmean(values),
            "ci95_low": _percentile(values, 0.025),
            "ci95_high": _percentile(values, 0.975),
        }
        for metric, values in distributions.items()
    }


def _paired_comparison(
    records: Sequence[Mapping[str, Any]],
    *,
    baseline: str,
    challenger: str,
    repeats: int,
    seed: int,
) -> dict[str, Any]:
    indexed = {
        (
            str(row["arm"]), str(row["case_id"]), int(row["replicate"]),
            str(row["mapper_mode"]),
        ): row
        for row in records
    }
    output: dict[str, Any] = {}
    for arm in ("A", "ALL_B_b1"):
        pairs = []
        for key, base in indexed.items():
            key_arm, case_id, replicate, mode = key
            if key_arm != arm or mode != baseline:
                continue
            other = indexed.get((arm, case_id, replicate, challenger))
            if other is not None:
                pairs.append((base, other))
        transitions = {}
        for metric in ("option_top1", "option_top2"):
            transitions[metric] = {
                "gain": sum(
                    int(not bool(base[metric]) and bool(other[metric]))
                    for base, other in pairs
                ),
                "loss": sum(
                    int(bool(base[metric]) and not bool(other[metric]))
                    for base, other in pairs
                ),
                "unchanged_success": sum(
                    int(bool(base[metric]) and bool(other[metric]))
                    for base, other in pairs
                ),
                "unchanged_failure": sum(
                    int(not bool(base[metric]) and not bool(other[metric]))
                    for base, other in pairs
                ),
            }
        deltas = {
            "top1": statistics.fmean(
                float(other["option_top1"]) - float(base["option_top1"])
                for base, other in pairs
            ) if pairs else 0.0,
            "top2": statistics.fmean(
                float(other["option_top2"]) - float(base["option_top2"])
                for base, other in pairs
            ) if pairs else 0.0,
            "mrr": statistics.fmean(
                float(other["option_rr"]) - float(base["option_rr"])
                for base, other in pairs
            ) if pairs else 0.0,
        }
        by_case: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = (
            defaultdict(list)
        )
        for base, other in pairs:
            by_case[str(base["case_id"])].append((base, other))
        case_ids = sorted(by_case)
        if not case_ids:
            output[arm] = {
                "n_pairs": 0,
                "delta": deltas,
                "transitions": transitions,
                "bootstrap_delta_ci95": {
                    metric: {"low": 0.0, "high": 0.0}
                    for metric in ("top1", "top2", "mrr")
                },
            }
            continue
        rng = random.Random(seed)
        distributions = {"top1": [], "top2": [], "mrr": []}
        for _ in range(repeats):
            sampled = [rng.choice(case_ids) for _ in case_ids]
            sample_pairs = [
                pair for case_id in sampled for pair in by_case[case_id]
            ]
            for name, field in (
                ("top1", "option_top1"),
                ("top2", "option_top2"),
                ("mrr", "option_rr"),
            ):
                distributions[name].append(statistics.fmean(
                    float(other[field]) - float(base[field])
                    for base, other in sample_pairs
                ))
        output[arm] = {
            "n_pairs": len(pairs),
            "delta": deltas,
            "transitions": transitions,
            "bootstrap_delta_ci95": {
                metric: {
                    "low": _percentile(values, 0.025),
                    "high": _percentile(values, 0.975),
                }
                for metric, values in distributions.items()
            },
        }
    return output


class _CacheMissLLM:
    temperature = 0.0

    def call_module(self, module: str, _prompt: str, _payload: Mapping[str, Any]):
        raise RuntimeError("--skip-llm cache miss in %s" % module)


def _llm_adapter(args: argparse.Namespace) -> ab.CachedModuleAdapter:
    if args.skip_llm:
        client: Any = _CacheMissLLM()
    else:
        client = RobustLLMClient(
            model=args.model,
            call_timeout=args.call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=0.0,
        )
    cached = bfs.CachedLLM(
        client,
        args.output_dir / "cache"
        / ("llm_cache%s.json" % (
            ("_" + args.cache_shard) if args.cache_shard else ""
        )),
        args.model,
    )
    return ab.CachedModuleAdapter(cached)


def _retrievers(enable: bool) -> dict[str, Any]:
    if not enable:
        return {}
    out = {}
    for name, path in (
        ("rag_index", ROOT / "data" / "corpus" / "rag_index"),
        ("cpg_index", ROOT / "data" / "corpus" / "cpg_index"),
    ):
        retriever = RAGRetriever(path, device="cpu")
        if retriever.is_ready:
            out[name] = retriever
    return out


def _write_tsv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> dict[str, Any]:
    protocol = _read_json(args.protocol)
    protocol_audit = _verify_protocol(protocol)
    cases = talp17.assemble_cases()
    case_by_id = {str(case["id"]): case for case in cases}
    adjudication = _build_v2_adjudication(cases)
    _atomic_json(V2_ADJ, adjudication)
    expected = _expected_index(adjudication)

    old_payload = _read_json(OLD_RECORDS)
    old_records = list(old_payload.get("records") or ())
    expected_units = int(protocol["frozen_ranking"]["expected_units"])
    if len(old_records) != expected_units:
        raise ValueError(
            "frozen ranking expected %d units, found %d"
            % (expected_units, len(old_records))
        )
    modes = [value.strip() for value in args.modes.split(",") if value.strip()]
    if any(mode not in ALL_MODES for mode in modes):
        raise ValueError("unsupported mode in --modes")
    needs_llm = any(mode.startswith("typed_llm") for mode in modes)
    adapter = _llm_adapter(args) if needs_llm else None
    retrievers = _retrievers("typed_llm_disagreement_rag" in modes)
    relation_prompt = (
        PROMPT_DIR / "answer_relation_mapper.txt"
    ).read_text(encoding="utf-8")
    critic_prompt = (
        PROMPT_DIR / "answer_relation_rag_critic.txt"
    ).read_text(encoding="utf-8")
    mapper = RelationAwareAnswerMapper(
        resolver=load_offline_resolver(ROOT),
        llm=adapter,
        relation_prompt=relation_prompt,
        critic_prompt=critic_prompt,
        retrievers=retrievers,
        confidence_threshold=float(
            protocol["rag_trigger"]["confidence_threshold"]
        ),
        rag_top_k=int(protocol["rag_trigger"]["top_k_per_index"]),
        rag_max_snippets=int(protocol["rag_trigger"]["max_snippets"]),
        rag_max_chars=int(protocol["rag_trigger"]["max_chars_per_snippet"]),
    )

    records: list[dict[str, Any]] = []
    logical_calls: Counter[str] = Counter()
    trace_root = args.output_dir / "mapping_traces"
    rag_root = args.output_dir / "rag_snippets"
    filtered = [
        row for row in old_records
        if not args.case_filter
        or str(row["case_id"]) in set(args.case_filter.split(","))
    ]
    if args.limit:
        allowed_cases = sorted({str(row["case_id"]) for row in filtered})[
            :args.limit
        ]
        filtered = [
            row for row in filtered if str(row["case_id"]) in allowed_cases
        ]

    for old in filtered:
        arm = str(old["arm"])
        case_id = str(old["case_id"])
        replicate = int(old["replicate"])
        case = case_by_id[case_id]
        tree = _tree(arm, case_id, replicate)
        leaves = leaf_rows_from_tree(tree, old.get("ranking") or ())
        vignette, question = _split_case(str(case["case_text"]))
        options = _case_options(case)
        for mode in modes:
            trace_path = (
                trace_root / mode / arm
                / ("r%02d__%s.json" % (replicate, case_id))
            )
            if args.resume and trace_path.exists():
                projection = _read_json(trace_path)
            elif mode == "historical_oracle_assisted":
                projection = _historical_projection(old)
                _atomic_json(trace_path, projection)
            else:
                projection = mapper.map(
                    case_id=case_id,
                    vignette=vignette,
                    question=question,
                    options=options,
                    leaves=leaves,
                    mode=mode,
                )
                _atomic_json(trace_path, projection)
            rag_audit = (projection.get("audit") or {}).get("rag") or {}
            typed_audit = (projection.get("audit") or {}).get("typed") or {}
            if typed_audit.get("called"):
                logical_calls["typed_requests"] += 1
            if typed_audit.get("schema_repair_used"):
                logical_calls["typed_schema_repairs"] += 1
            if typed_audit.get("fail_open"):
                logical_calls["typed_fail_open"] += 1
            logical_calls["dropped_semantic_clone_groups"] += int(
                typed_audit.get("dropped_semantic_clone_groups") or 0
            )
            if rag_audit.get("called"):
                logical_calls["rag_critic_requests"] += 1
            if rag_audit.get("fail_open"):
                logical_calls["rag_critic_fail_open"] += 1
            if rag_audit.get("triggered"):
                _atomic_json(
                    rag_root / mode / arm
                    / ("r%02d__%s.json" % (replicate, case_id)),
                    {
                        "case_id": case_id,
                        "replicate": replicate,
                        "arm": arm,
                        "requests": rag_audit.get("requests") or [],
                        "snippets": rag_audit.get("snippets") or [],
                        "fail_open": bool(rag_audit.get("fail_open")),
                    },
                )
            records.append(_score(
                case=case,
                arm=arm,
                replicate=replicate,
                projection=projection,
                leaves=leaves,
                expected=expected,
            ))

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[(row["mapper_mode"], row["arm"])].append(row)
    aggregates = {
        mode: {
            arm: _aggregate(grouped.get((mode, arm), []))
            for arm in ("A", "ALL_B_b1")
        }
        for mode in modes
    }
    bootstrap = {
        mode: {
            arm: _bootstrap(
                grouped.get((mode, arm), []),
                repeats=args.bootstrap,
                seed=args.seed,
            )
            for arm in ("A", "ALL_B_b1")
        }
        for mode in modes
    }
    comparisons = {}
    for baseline, challenger in (
        ("deterministic_gold_blind", "typed_llm"),
        ("typed_llm", "typed_llm_disagreement_rag"),
        ("deterministic_gold_blind", "typed_llm_disagreement_rag"),
        ("historical_oracle_assisted", "typed_llm_disagreement_rag"),
    ):
        if baseline in modes and challenger in modes:
            key = "%s__to__%s" % (baseline, challenger)
            comparisons[key] = _paired_comparison(
                records,
                baseline=baseline,
                challenger=challenger,
                repeats=args.bootstrap,
                seed=args.seed,
            )
    call_audit = adapter.audit() if adapter is not None else {
        "requested": 0, "model": 0, "cache_hits": 0, "by_module": {},
    }
    rag_counts = Counter()
    for mode in modes:
        for arm in ("A", "ALL_B_b1"):
            for path in (rag_root / mode / arm).glob("*.json"):
                row = _read_json(path)
                rag_counts["traces"] += 1
                rag_counts["requests"] += len(row.get("requests") or ())
                rag_counts["snippets"] += len(row.get("snippets") or ())
                rag_counts["fail_open"] += int(bool(row.get("fail_open")))

    summary = {
        "schema_version": 2,
        "protocol": str(args.protocol.relative_to(ROOT)),
        "protocol_audit": protocol_audit,
        "scope": "offline_A_and_ALL_B_b1_only",
        "production_files_modified": False,
        "modes": modes,
        "n_records": len(records),
        "aggregates": aggregates,
        "bootstrap": bootstrap,
        "paired_comparisons": comparisons,
        "calls": {
            "execution_this_invocation": call_audit,
            "logical_from_completed_traces": dict(sorted(logical_calls.items())),
        },
        "retrieval": dict(sorted(rag_counts.items())),
        "adjudication": {
            "path": str(V2_ADJ.relative_to(ROOT)),
            "human_signed_off": False,
            "scope": "transcribed_manual_v1_A_relations",
        },
    }
    _atomic_json(args.output_dir / "records.json", {
        "schema_version": 2, "records": records,
    })
    _atomic_json(args.output_dir / "summary.json", summary)
    _atomic_json(args.output_dir / "bootstrap.json", bootstrap)
    _atomic_json(args.output_dir / "paired_comparisons.json", comparisons)

    transfer_rows = []
    by_case_mode_arm: dict[tuple[str, str, str], list[Mapping[str, Any]]] = (
        defaultdict(list)
    )
    for row in records:
        by_case_mode_arm[
            (str(row["case_id"]), str(row["mapper_mode"]), str(row["arm"]))
        ].append(row)
    for arm in ("A", "ALL_B_b1"):
        for case_id in sorted(case_by_id):
            base = by_case_mode_arm.get(
                (case_id, "historical_oracle_assisted", arm), [],
            )
            base_top1 = (
                statistics.fmean(float(row["option_top1"]) for row in base)
                if base else None
            )
            for mode in modes:
                current = by_case_mode_arm.get((case_id, mode, arm), [])
                if not current:
                    continue
                top1 = statistics.fmean(
                    float(row["option_top1"]) for row in current
                )
                transfer_rows.append({
                    "arm": arm,
                    "case_id": case_id,
                    "mapper_mode": mode,
                    "top1": top1,
                    "historical_top1": base_top1,
                    "delta_top1": (
                        top1 - base_top1 if base_top1 is not None else None
                    ),
                })
    _write_tsv(
        args.output_dir / "case_transfers.tsv",
        transfer_rows,
        ("arm", "case_id", "mapper_mode", "top1", "historical_top1",
         "delta_top1"),
    )
    _write_tsv(
        args.output_dir / "blind_adjudication.tsv",
        adjudication["rows"],
        ("case_id", "option_letter", "option_text", "relation_type",
         "acceptable_leaf_labels", "adjudicated_relation_present", "source",
         "review_status"),
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--modes", default=",".join(ALL_MODES))
    parser.add_argument(
        "--model", default="meta-llama/llama-3.3-70b-instruct",
    )
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument(
        "--cache-shard",
        default="",
        help="Independent cache suffix for disjoint concurrent case shards.",
    )
    args = parser.parse_args(argv)
    summary = run(args)
    print(json.dumps(summary["aggregates"], ensure_ascii=False, indent=2))
    print(json.dumps({
        "calls": summary["calls"],
        "retrieval": summary["retrieval"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
