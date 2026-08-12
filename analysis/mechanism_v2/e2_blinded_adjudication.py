#!/usr/bin/env python3
"""E2: heterogeneous, method-blind clinical completeness adjudication.

The experiment separates three objects that older trajectory audits conflated:

* whether the vignette uniquely supports the benchmark reference specificity;
* whether a system's pre-mapper diagnosis is clinically complete, partial, or
  wrong relative to that reference; and
* whether the benchmark task mapper/judge marks that output correct.

``freeze`` builds a deterministic 400/800 stratified audit cohort before any
review call.  ``run-reviewer`` sends only neutral candidate IDs, case text and
the benchmark reference to one heterogeneous reviewer.  Arm provenance,
strict-match flags and mapper outcomes never enter the online payload.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
import sys
import tarfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    DEVELOPMENT_SLICES,
    ROOT,
    clean_vignette,
    file_sha256,
    json_sha256,
    load_normalized_cases,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
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


EXPERIMENT_ID = "E2"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication"
DEFAULT_MODELS = {
    "reviewer_a": "google/gemini-2.5-flash",
    "reviewer_b": "deepseek/deepseek-v4-flash-0731",
}
TARGET_PER_FAMILY = 200
SELECTION_FREEZE = "E2-blinded-clinical-adjudication-v1"

DUAL_PATH = Path("analysis/backbone_v1/mosaic_eval/r5_dual/dual.tsv")
CHAIN_PATH = Path("analysis/backbone_v1/mosaic_eval/r6_winsets/matrix_chain.tsv")
SCORED_PATH = Path("analysis/backbone_v1/mosaic_eval/r6_winsets/matrix_scored.tsv")
STABLE_PATH = Path("analysis/backbone_v1/mosaic_eval/r6_winsets/matrix_chain_stable.tsv")
COVARIATE_PATH = Path("analysis/backbone_v1/mosaic_eval/r6_covariates.tsv")
SOURCE_TABLES = (DUAL_PATH, CHAIN_PATH, SCORED_PATH, STABLE_PATH, COVARIATE_PATH)

SLICE_LOOKUP = {
    ("da", "d2_seq100"): "DA_d2_seq100",
    ("da", "d2_heldout100"): "DA_d2_heldout100",
    ("da", "d2_heldout200b"): "DA_d2_heldout200b",
    ("mcr", "mcr_v1"): "MCR_v1_seq100",
    ("mcr", "mcr_v2"): "MCR_v2_seq100",
    ("mcr", "mcr_200b"): "MCR_seq200b",
}
SPEC_BY_ID = {spec.slice_id: spec for spec in DEVELOPMENT_SLICES}

# Stable metrics exist on the 400-case development subset only.
REPLICATED_ARMS = (
    "collapse3c",
    "multistance",
    "msplit",
    "aphhm_c_v1",
    "lite",
    "forest",
    "impc",
    "adaptive4v2",
    "e7",
    "v0",
)

NON_ARM_FIELDS = frozenset(
    {
        "dataset",
        "slice",
        "case_id",
        "gold",
        "n_arms_scored",
        "n_arms_correct",
        "difficulty",
    }
)

RELATIONS = frozenset(
    {
        "complete_equivalent",
        "partial_parent_or_component",
        "conflicting_subtype_or_scope",
        "manifestation_or_related",
        "not_equivalent",
        "uncertain",
    }
)
IDENTIFIABILITY = frozenset(
    {
        "unique_full_reference",
        "family_only_not_full_specificity",
        "multiple_complete_answers",
        "unsupported_reference_specificity",
        "insufficient_case_information",
        "uncertain",
    }
)

PROMPT = r"""You are an independent clinical reviewer. You do not know which
diagnostic system produced any candidate. Evaluate only the supplied clinical
record, benchmark reference diagnosis, and neutrally numbered candidates. Do
not infer quality from candidate order, wording polish, or string containment.

Perform two logically separate tasks.

A. Reference identifiability. Decide whether the clinical record uniquely
supports the FULL benchmark reference, including every required subtype,
etiology, anatomy, time/state, complication, stage, and composite component.
Distinguish a supported disease family from unsupported full specificity. A
direct author diagnostic assertion in the record is evidence of identifiability
but must be flagged; it is not independent diagnostic reasoning. Missing tests
are unknown rather than negative.

B. Candidate-to-reference relation in this case. Judge every candidate:
- complete_equivalent: same final diagnostic object and all case-defining
  components; harmless alias or wording variation is allowed;
- partial_parent_or_component: correct family, broader parent, compatible
  child, cause, manifestation, or one component, but a required component or
  specificity is absent;
- conflicting_subtype_or_scope: related entity that asserts an incompatible
  subtype, anatomy, cause, time/state, stage, or composite scope;
- manifestation_or_related: a manifestation, complication, association, or
  differential rather than the requested final object;
- not_equivalent: a different diagnostic entity;
- uncertain: the supplied record genuinely cannot resolve the relation.

Return strict JSON only. Cover every candidate_id exactly once:
{
  "reference_identifiability": {
    "judgment": "unique_full_reference|family_only_not_full_specificity|multiple_complete_answers|unsupported_reference_specificity|insufficient_case_information|uncertain",
    "reference_object_kind": "disease|etiology|subtype|manifestation|syndrome|composite|other",
    "direct_author_assertion": false,
    "decisive_spans": ["up to three short exact quotes"],
    "unsupported_components": ["unsupported or ambiguous component"],
    "rationale": "brief case-grounded reason",
    "confidence": "high|medium|low"
  },
  "candidate_relations": [
    {
      "candidate_id": "C01",
      "relation": "complete_equivalent|partial_parent_or_component|conflicting_subtype_or_scope|manifestation_or_related|not_equivalent|uncertain",
      "scope_detail": "none|broader_parent|compatible_child|missing_etiology|missing_anatomy|missing_time_or_stage|single_composite_component|conflicting_subtype|conflicting_scope|manifestation_only|related_differential|different_entity|other",
      "decisive_span": "one short exact quote or empty",
      "missing_or_conflicting_component": "brief or empty",
      "reason": "brief relation-specific reason",
      "confidence": "high|medium|low"
    }
  ],
  "case_quality_flags": ["optional concise flag"]
}
"""


def repo_text(relative: Path) -> str:
    """Read a tracked source in both full and sparse worktrees."""
    local = ROOT / relative
    if local.is_file():
        return local.read_text(encoding="utf-8")
    return subprocess.check_output(
        ["git", "show", f"HEAD:{relative.as_posix()}"], cwd=ROOT, text=True
    )


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_table(relative: Path) -> list[dict[str, str]]:
    text = repo_text(relative)
    first = text.splitlines()[0]
    delimiter = "\t" if "\t" in first else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


def key_for(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(row["dataset"]), str(row["slice"]), str(row["case_id"]))


def _bool_cell(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    return str(value).strip().lower() in {"1", "true", "yes"}


def is_composite_or_subtype(gold: str, covariate: Mapping[str, Any]) -> bool:
    value = str(gold or "").lower()
    phrases = (
        " and ",
        " with ",
        " secondary to ",
        " due to ",
        " associated with ",
        " syndrome type ",
        " type i",
        " type ii",
        " type 1",
        " type 2",
        "stage ",
        "grade ",
        "+",
        "/",
    )
    return _bool_cell(covariate.get("gold_has_subtype")) is True or any(
        phrase in value for phrase in phrases
    )


def derive_case_tags(
    chain: Mapping[str, Any],
    scored: Mapping[str, Any],
    stable: Mapping[str, Any] | None,
    covariate: Mapping[str, Any],
) -> dict[str, Any]:
    arms = [name for name in chain if name not in NON_ARM_FIELDS]
    mapper_rescue_arms: list[str] = []
    mapper_harm_arms: list[str] = []
    for arm in arms:
        chain_value = _bool_cell(chain.get(arm))
        task_value = _bool_cell(scored.get(arm))
        if chain_value is None or task_value is None:
            continue
        if task_value and not chain_value:
            mapper_rescue_arms.append(arm)
        if chain_value and not task_value:
            mapper_harm_arms.append(arm)

    stable_values: dict[str, bool] = {}
    if stable is not None:
        for arm in REPLICATED_ARMS:
            if _bool_cell(stable.get(f"{arm}_stable")) is True:
                value = _bool_cell(stable.get(arm))
                if value is not None:
                    stable_values[arm] = value
    stable_winners = sorted(arm for arm, value in stable_values.items() if value)
    stable_losers = sorted(arm for arm, value in stable_values.items() if not value)
    stable_exclusive = bool(
        stable_winners
        and stable_losers
        and (len(stable_winners) == 1 or len(stable_losers) == 1)
    )
    all_method_failure = int(float(chain.get("n_arms_correct") or 0)) == 0
    composite = is_composite_or_subtype(str(chain.get("gold") or ""), covariate)

    tags: list[str] = []
    if mapper_rescue_arms:
        tags.append("task_correct_chain_wrong")
    if mapper_harm_arms:
        tags.append("chain_correct_task_wrong")
    if stable_exclusive:
        tags.append("stable_exclusive")
    if all_method_failure:
        tags.append("all_method_strict_failure")
    if composite:
        tags.append("composite_or_subtype_reference")
    if not tags:
        tags.append("background")

    # Mutually exclusive sampling stratum. Rare endpoint-critical strata take
    # priority; all secondary tags remain available for analysis.
    if mapper_harm_arms:
        primary = "mapper_harm"
    elif stable_exclusive:
        primary = "stable_exclusive"
    elif mapper_rescue_arms:
        primary = "mapper_rescue"
    elif all_method_failure:
        primary = "all_method_failure"
    elif composite:
        primary = "composite_subtype"
    else:
        primary = "background"
    return {
        "tags": tags,
        "primary_stratum": primary,
        "mapper_rescue_arms": sorted(mapper_rescue_arms),
        "mapper_harm_arms": sorted(mapper_harm_arms),
        "stable_winners": stable_winners,
        "stable_losers": stable_losers,
    }


def _largest_remainder_alloc(
    sizes: Mapping[tuple[str, str], int], total: int
) -> dict[tuple[str, str], int]:
    """Allocate proportionally while giving every nonempty audit cell support."""
    available = sum(sizes.values())
    if total < 0 or total > available:
        raise ValueError(f"invalid allocation total={total} available={available}")
    if available == 0:
        return {key: 0 for key in sizes}
    nonempty = [key for key, size in sizes.items() if size]
    if total < len(nonempty):
        raise ValueError(
            f"target {total} cannot give positive inclusion probability to "
            f"all {len(nonempty)} nonempty cells"
        )
    allocation = {key: int(sizes[key] > 0) for key in sizes}
    residual_capacity = {key: sizes[key] - allocation[key] for key in sizes}
    residual_total = total - sum(allocation.values())
    residual_available = sum(residual_capacity.values())
    exact = {
        key: (
            residual_total * residual_capacity[key] / residual_available
            if residual_available
            else 0.0
        )
        for key in sizes
    }
    for key, value in exact.items():
        allocation[key] += min(residual_capacity[key], int(math.floor(value)))
    left = total - sum(allocation.values())
    order = sorted(
        sizes,
        key=lambda key: (
            -(exact[key] - math.floor(exact[key])),
            stable_seed(SELECTION_FREEZE, "allocation", *key),
            key,
        ),
    )
    for key in order:
        if left <= 0:
            break
        if allocation[key] < sizes[key]:
            allocation[key] += 1
            left -= 1
    if left:
        raise AssertionError(f"failed to allocate {left} rows")
    return allocation


def select_stratified(
    rows: Sequence[dict[str, Any]], target_per_family: int = TARGET_PER_FAMILY
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select all rare strata, then probability-sample remaining cells.

    Cells are family x slice x primary stratum. Mapper-harm and stable-exclusive
    cells are censused. Other cells receive proportional allocations within
    family, and deterministic hash ordering is the frozen random mechanism.
    """
    selected: list[dict[str, Any]] = []
    cells_meta: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        family_rows = [row for row in rows if row["family"] == family]
        mandatory = [
            row
            for row in family_rows
            if row["primary_stratum"] in {"mapper_harm", "stable_exclusive"}
        ]
        if len(mandatory) > target_per_family:
            raise AssertionError(f"rare {family} strata exceed family target")
        remaining = [row for row in family_rows if row not in mandatory]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in remaining:
            grouped[(row["slice"], row["primary_stratum"])].append(row)
        allocation = _largest_remainder_alloc(
            {key: len(values) for key, values in grouped.items()},
            target_per_family - len(mandatory),
        )
        chosen_ids = {row["case_key"] for row in mandatory}
        for key, values in sorted(grouped.items()):
            ranked = sorted(
                values,
                key=lambda row: (
                    stable_seed(SELECTION_FREEZE, "case", row["case_key"]),
                    row["case_key"],
                ),
            )
            chosen_ids.update(row["case_key"] for row in ranked[: allocation[key]])
        family_selected = [row for row in family_rows if row["case_key"] in chosen_ids]
        if len(family_selected) != target_per_family:
            raise AssertionError(
                f"selected {len(family_selected)} {family}, expected {target_per_family}"
            )
        selected.extend(family_selected)

        all_cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in family_rows:
            all_cells[(row["slice"], row["primary_stratum"])].append(row)
        for (slice_name, primary), values in sorted(all_cells.items()):
            n = sum(row["case_key"] in chosen_ids for row in values)
            population = len(values)
            cells_meta.append(
                {
                    "family": family,
                    "slice": slice_name,
                    "primary_stratum": primary,
                    "population_n": population,
                    "sample_n": n,
                    "inclusion_probability": n / population,
                    "analysis_weight": population / n,
                    "census_cell": n == population,
                }
            )
    weight_by_cell = {
        (row["family"], row["slice"], row["primary_stratum"]): row["analysis_weight"]
        for row in cells_meta
    }
    for row in selected:
        row["analysis_weight"] = weight_by_cell[
            (row["family"], row["slice"], row["primary_stratum"])
        ]
    return sorted(selected, key=lambda row: row["case_key"]), cells_meta


def make_candidate_registry(
    case_key: str, arm_rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    """Exact-surface deduplicate and assign neutral IDs in frozen random order."""
    labels: dict[str, str] = {}
    for row in arm_rows:
        label = " ".join(str(row.get("champion") or "").split()).strip()
        key = normalize_label(label)
        if key and key not in labels:
            labels[key] = label
    ordered = sorted(
        labels.items(),
        key=lambda item: (
            stable_seed(SELECTION_FREEZE, "candidate-order", case_key, item[0]),
            item[0],
        ),
    )
    by_key = {key: f"C{index:02d}" for index, (key, _label) in enumerate(ordered, 1)}
    registry = [
        {"candidate_id": by_key[key], "label": label}
        for key, label in ordered
    ]
    arm_map: dict[str, dict[str, Any]] = {}
    for row in arm_rows:
        label = " ".join(str(row.get("champion") or "").split()).strip()
        key = normalize_label(label)
        if not key or key not in by_key:
            continue
        arm_map[str(row["arm"])] = {
            "candidate_id": by_key[key],
            "surface_label": label,
            "method_family": str(row.get("family") or ""),
            "strict_chain_correct": _bool_cell(row.get("chain_correct")),
            "task_correct": _bool_cell(row.get("scored_correct")),
            "legacy_mapper_rescue": _bool_cell(row.get("mapper_rescue")),
        }
    return registry, arm_map


def _load_case_universe() -> tuple[list[dict[str, Any]], dict[str, str]]:
    tables = {path: read_table(path) for path in SOURCE_TABLES}
    chain_rows = tables[CHAIN_PATH]
    scored = {key_for(row): row for row in tables[SCORED_PATH]}
    stable = {key_for(row): row for row in tables[STABLE_PATH]}
    covariates = {key_for(row): row for row in tables[COVARIATE_PATH]}
    dual: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in tables[DUAL_PATH]:
        dual[key_for(row)].append(row)

    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    for spec in DEVELOPMENT_SLICES:
        normalized[spec.slice_id] = load_normalized_cases(spec.cases_json)

    rows: list[dict[str, Any]] = []
    for chain in chain_rows:
        key = key_for(chain)
        if key not in scored or key not in covariates or key not in dual:
            raise KeyError(f"incomplete E2 source join for {key}")
        slice_id = SLICE_LOOKUP[(key[0], key[1])]
        case = normalized[slice_id].get(key[2])
        if case is None:
            raise KeyError(f"normalized case absent for {key}")
        tags = derive_case_tags(chain, scored[key], stable.get(key), covariates[key])
        family = "DA" if key[0] == "da" else "MCR"
        case_key = f"{slice_id}/{key[2]}"
        registry, arm_map = make_candidate_registry(case_key, dual[key])
        if not registry:
            raise AssertionError(f"no candidate outputs for {case_key}")
        rows.append(
            {
                "case_key": case_key,
                "family": family,
                "dataset": key[0],
                "slice": key[1],
                "slice_id": slice_id,
                "source_id": key[2],
                "gold": str(chain["gold"]),
                "vignette": clean_vignette(str(case.get("case_text") or "")),
                "source_options": dict((case.get("annotation") or {}).get("source_options") or {}),
                "gold_option": str(case.get("gold_option") or ""),
                "candidate_registry": registry,
                "arm_map": arm_map,
                "strict_n_arms_correct": int(float(chain.get("n_arms_correct") or 0)),
                "difficulty": float(chain.get("difficulty") or 0.0),
                **tags,
            }
        )
    if len(rows) != 800:
        raise AssertionError(f"E2 expected 800 joined cases, found {len(rows)}")
    source_hashes = {path.as_posix(): text_sha256(repo_text(path)) for path in SOURCE_TABLES}
    for spec in DEVELOPMENT_SLICES:
        source_hashes[str(spec.cases_json.relative_to(ROOT))] = file_sha256(spec.cases_json)
    return rows, source_hashes


def blinded_card(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "blind_case_id": f"E2C{index:04d}",
        "case_key": str(row["case_key"]),
        "clinical_record": str(row["vignette"]),
        "reference_diagnosis": str(row["gold"]),
        "candidate_registry": [dict(item) for item in row["candidate_registry"]],
    }


def reviewer_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    """Online payload deliberately excludes case provenance and evaluation."""
    return {
        "blind_case_id": str(card["blind_case_id"]),
        "clinical_record": str(card["clinical_record"]),
        "reference_diagnosis": str(card["reference_diagnosis"]),
        "candidate_registry": [
            {
                "candidate_id": str(row["candidate_id"]),
                "label": str(row["label"]),
            }
            for row in card["candidate_registry"]
        ],
    }


def validate_review(response: Mapping[str, Any], allowed: set[str]) -> str | None:
    identity = response.get("reference_identifiability")
    if not isinstance(identity, Mapping):
        return "reference_identifiability is required"
    if str(identity.get("judgment") or "") not in IDENTIFIABILITY:
        return "invalid reference identifiability judgment"
    if not isinstance(identity.get("decisive_spans"), list):
        return "decisive_spans must be a list"
    if not isinstance(identity.get("unsupported_components"), list):
        return "unsupported_components must be a list"
    if str(identity.get("confidence") or "") not in {"high", "medium", "low"}:
        return "invalid reference confidence"
    relations = response.get("candidate_relations")
    if not isinstance(relations, list):
        return "candidate_relations must be a list"
    if not all(isinstance(row, Mapping) for row in relations):
        return "candidate relation rows must be objects"
    ids = [str(row.get("candidate_id") or "") for row in relations]
    if len(ids) != len(allowed) or set(ids) != allowed:
        return "candidate_relations must cover every candidate exactly once"
    for row in relations:
        if str(row.get("relation") or "") not in RELATIONS:
            return "invalid candidate relation"
        if str(row.get("confidence") or "") not in {"high", "medium", "low"}:
            return "invalid candidate confidence"
    if not isinstance(response.get("case_quality_flags"), list):
        return "case_quality_flags must be a list"
    return None


def _selection_summary(
    universe: Sequence[Mapping[str, Any]],
    selected: Sequence[Mapping[str, Any]],
    cells: Sequence[Mapping[str, Any]],
    source_hashes: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "selection_freeze": SELECTION_FREEZE,
        "source_commit": source_commit(),
        "universe_n": len(universe),
        "sample_n": len(selected),
        "family_counts": dict(sorted(Counter(row["family"] for row in selected).items())),
        "slice_counts": dict(sorted(Counter(row["slice_id"] for row in selected).items())),
        "primary_stratum_population": dict(
            sorted(Counter(row["primary_stratum"] for row in universe).items())
        ),
        "primary_stratum_sample": dict(
            sorted(Counter(row["primary_stratum"] for row in selected).items())
        ),
        "tag_population": dict(
            sorted(Counter(tag for row in universe for tag in row["tags"]).items())
        ),
        "tag_sample": dict(
            sorted(Counter(tag for row in selected for tag in row["tags"]).items())
        ),
        "candidate_count_hist": dict(
            sorted(Counter(len(row["candidate_registry"]) for row in selected).items())
        ),
        "sampling_cells": list(cells),
        "source_hashes": dict(sorted(source_hashes.items())),
        "excluded_variance_controls": [
            "repeat-run variance reduction",
            "confirmation-set expansion",
            "provider/retry standardisation as a treatment",
        ],
    }


def _preregistration(summary: Mapping[str, Any], cards_hash: str) -> str:
    return f"""# E2 预注册：严格完整性、reference 可识别性与 mapper 投影盲审

## 冻结对象

- 病例总体：R4/R5/R6 同一 800 例；本实验不是新增确认集。
- 冻结样本：400 例，DA/MCR 各 200；cards SHA-256 `{cards_hash}`。
- 选择版本：`{SELECTION_FREEZE}`；源提交 `{summary['source_commit']}`。
- 两位独立异构审阅员：Gemini 与 DeepSeek；不得复用生成这些轨迹的 Llama 族作为主审。
- 外部模型只作分包盲审；最终裁决、机制归因和结论由根审计负责。

## 抽样与可推断范围

主分层依次为 mapper harm、stable exclusive、mapper rescue、all-method strict failure、
composite/subtype、background。mapper-harm 与 stable-exclusive 单元全纳；其余在
`family × slice × primary_stratum` 单元内按冻结哈希抽样。每例保存 `N/n` 权重。
加权估计可回推此 800 例机制总体；未经权重的比例只能描述审计样本。稳定分歧只在
已有双次运行的 dev400 上定义，不外推到 200b。

## 独立的三个端点

1. **Strict/chain：** 原审计的精确或冻结同义桥命中，只作严格字符串端点。
2. **Clinical completeness：** pre-mapper 输出由盲审分为 complete、parent/component
   partial、conflicting scope、manifestation/related、wrong、uncertain。
3. **Task projection：** `scored_correct` 独立于临床关系；DA 的 mapper rescue/harm
   必须在 pre-mapper clinical relation 之后统计，不得把 option 命中当诊断完整。

Reference identifiability 是另一条轴：unique full、family-only、multiple complete、
unsupported specificity、insufficient、uncertain。不能因候选与 reference 同词就推断
病例能唯一支持该 reference。

## 盲法与候选范围

每例纳入 `r5_dual` 中所有可用终端 champion，按规范化后的**精确表面**去重；不做模糊
或临床合并。候选以冻结随机顺序编号。API 载荷只含病例正文、reference、候选 ID/文本；
不含数据集名、臂名、方法族、strict/task 标记、mapper 状态、分层标签或分数。

## 根级裁决范围

根审计至少覆盖：两审阅员全部 identifiability 分歧、全部候选 complete-vs-wrong/partial
端点分歧、任一方法的 strict/task/clinical 三口径冲突、所有审阅失败，以及按家族冻结的
一致阴性样本。根审计不得用方法声誉覆盖病例证据；查看臂映射只允许在关系裁决冻结之后。

## 否证条件与报告约束

- 若 clinical-complete 不能显著重排 strict 的主要臂序，则“差异主要由标签粒度造成”被削弱。
- 若重排只发生在 reference 非唯一/不支持全特异度病例，不得称为算法诊断能力改善。
- mapper rescue 若主要落在 clinical partial/wrong，说明任务投影在制造界面成功；若主要为
  complete，说明 strict bridge 漏掉临床同义。
- stable-exclusive 若经 clinical/identifiability 裁决消失，专长证据进一步被否证；若保留，
  才进入病例机制解剖，仍不自动代表题型专长。
- 所有模型失败留在 ITA 分母并单列；不得丢弃失败后只分析可服务病例。
"""


def freeze_design(out: Path) -> dict[str, Any]:
    universe, source_hashes = _load_case_universe()
    selected, cells = select_stratified(universe)
    out.mkdir(parents=True, exist_ok=True)
    design = out / "design"
    design.mkdir(parents=True, exist_ok=True)
    cards = [blinded_card(row, index) for index, row in enumerate(selected, 1)]
    write_jsonl(design / "selection.jsonl", selected)
    write_jsonl(design / "blinded_cards.jsonl", cards)
    write_jsonl(design / "sampling_cells.jsonl", cells)
    cards_hash = file_sha256(design / "blinded_cards.jsonl")
    summary = _selection_summary(universe, selected, cells, source_hashes)
    summary["selection_sha256"] = file_sha256(design / "selection.jsonl")
    summary["blinded_cards_sha256"] = cards_hash
    atomic_json(design / "summary.json", summary)
    (out / "PREREGISTRATION.md").write_text(
        _preregistration(summary, cards_hash), encoding="utf-8"
    )
    RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id="design_freeze",
        dataset="DA+MCR 800 universe; stratified n=400",
        model="none",
        workers=1,
        rag=False,
        source_commit=str(summary["source_commit"]),
        prompt_hashes={"clinical_reviewer": sha256_text(PROMPT)},
        input_hash=json_sha256(source_hashes),
        selection_freeze=SELECTION_FREEZE,
        endpoint_contract="strict + clinical completeness + task projection; identifiability separate",
        excluded_variance_controls=list(summary["excluded_variance_controls"]),
    ).write(design / "manifest.json")
    return summary


def _reviewer_archive(directory: Path) -> tuple[Path, Path]:
    archive = directory / "RAW_OUTPUTS.tar.gz"
    checksum = directory / f"{archive.name}.sha256"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in (
            "reviews.jsonl",
            "telemetry.jsonl",
            "telemetry_summary.json",
            "summary.json",
            "manifest.json",
            "run.log",
        ):
            path = directory / name
            if path.is_file():
                bundle.add(path, arcname=name)
    checksum.write_text(f"{file_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, checksum


def run_reviewer(
    out: Path,
    reviewer_id: str,
    model: str,
    workers: int,
    *,
    cache_only: bool = False,
) -> list[dict[str, Any]]:
    workers = validate_workers(workers, rag=False)
    if reviewer_id not in DEFAULT_MODELS:
        raise ValueError(f"reviewer_id must be one of {sorted(DEFAULT_MODELS)}")
    cards_path = out / "design/blinded_cards.jsonl"
    cards = read_jsonl(cards_path)
    if len(cards) != 400:
        raise AssertionError(f"expected 400 frozen E2 cards, found {len(cards)}")
    directory = out / reviewer_id
    directory.mkdir(parents=True, exist_ok=True)
    telemetry_path = directory / "telemetry.jsonl"
    log_path = directory / "run.log"
    log_path.write_text(
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}\n"
        f"reviewer_id={reviewer_id}\nmodel={model}\nworkers={workers}\n"
        f"cards_sha256={file_sha256(cards_path)}\ncache_only={int(cache_only)}\n",
        encoding="utf-8",
    )
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=240,
        max_retries=2,
    )

    def one(card: Mapping[str, Any]) -> dict[str, Any]:
        payload = reviewer_payload(card)
        allowed = {
            str(row["candidate_id"]) for row in payload["candidate_registry"]
        }
        try:
            outcome = caller.call(
                module=f"E2ClinicalReviewer_{reviewer_id}",
                prompt=PROMPT,
                payload=payload,
                validator=lambda response: validate_review(response, allowed),
                cache_only=cache_only,
            )
            return {
                "blind_case_id": str(card["blind_case_id"]),
                "case_key": str(card["case_key"]),
                "reviewer_id": reviewer_id,
                "model": model,
                "success": outcome.success,
                "error": outcome.error,
                "review": outcome.response,
                "cache_hit": outcome.cache_hit,
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        except Exception as exc:  # operational failure remains in ITA
            return {
                "blind_case_id": str(card["blind_case_id"]),
                "case_key": str(card["case_key"]),
                "reviewer_id": reviewer_id,
                "model": model,
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "review": {},
                "cache_hit": False,
                "cache_key": "",
                "prompt_sha256": sha256_text(PROMPT),
                "payload_sha256": json_sha256(payload),
            }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, card): str(card["blind_case_id"]) for card in cards}
        for done, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if done % 20 == 0 or done == len(cards):
                failures = sum(not row["success"] for row in rows)
                line = f"completed={done}/{len(cards)} failures={failures}"
                print(line, flush=True)
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
    rows.sort(key=lambda row: row["blind_case_id"])
    write_jsonl(directory / "reviews.jsonl", rows)
    telemetry = read_jsonl(telemetry_path)
    atomic_json(directory / "telemetry_summary.json", aggregate_telemetry(telemetry))
    relation_counts = Counter(
        str(item.get("relation"))
        for row in rows
        for item in ((row.get("review") or {}).get("candidate_relations") or [])
        if isinstance(item, Mapping)
    )
    identity_counts = Counter(
        str(
            (((row.get("review") or {}).get("reference_identifiability") or {}).get("judgment"))
            or "review_failure"
        )
        for row in rows
    )
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "reviewer_id": reviewer_id,
        "role": "method-blind heterogeneous subcontractor; root owns final adjudication",
        "model": model,
        "n_cases": len(rows),
        "n_success": sum(bool(row["success"]) for row in rows),
        "n_failure": sum(not bool(row["success"]) for row in rows),
        "cache_hits": sum(bool(row["cache_hit"]) for row in rows),
        "reference_identifiability_counts": dict(sorted(identity_counts.items())),
        "candidate_relation_counts": dict(sorted(relation_counts.items())),
        "prompt_sha256": sha256_text(PROMPT),
        "cards_sha256": file_sha256(cards_path),
        "capabilities": dependency_capabilities(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(directory / "summary.json", summary)
    RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id=reviewer_id,
        dataset="frozen stratified 400",
        model=model,
        workers=workers,
        rag=False,
        source_commit=source_commit(),
        prompt_hashes={"clinical_reviewer": sha256_text(PROMPT)},
        input_hash=file_sha256(cards_path),
        selection_freeze=SELECTION_FREEZE,
        endpoint_contract="identifiability separate from candidate completeness and task projection",
        excluded_variance_controls=[
            "repeat-run variance reduction",
            "provider/retry standardisation as a treatment",
        ],
    ).write(directory / "manifest.json")
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"completed_at_utc={datetime.now(timezone.utc).isoformat()}\n")
        stream.write(f"successes={summary['n_success']} failures={summary['n_failure']}\n")
    _reviewer_archive(directory)
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze", help="freeze the 400-case design")
    freeze.add_argument("--target-per-family", type=int, default=TARGET_PER_FAMILY)
    run = sub.add_parser("run-reviewer", help="run one method-blind reviewer")
    run.add_argument("--reviewer", required=True, choices=sorted(DEFAULT_MODELS))
    run.add_argument("--model", default="")
    run.add_argument("--workers", type=int, default=50)
    run.add_argument("--cache-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "freeze":
        if args.target_per_family != TARGET_PER_FAMILY:
            raise ValueError("E2 frozen contract requires exactly 200 cases per family")
        summary = freeze_design(args.out)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-reviewer":
        model = args.model or DEFAULT_MODELS[args.reviewer]
        rows = run_reviewer(
            args.out,
            args.reviewer,
            model,
            args.workers,
            cache_only=args.cache_only,
        )
        print(f"{args.reviewer}: {sum(row['success'] for row in rows)}/{len(rows)} successful")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
