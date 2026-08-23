#!/usr/bin/env python3
"""200-case probe: CoreLift append-only completion on frozen MultiStance pools.

Holdout-200b only (100 DA + 100 MCR). The MultiStance registry is frozen;
generation is not re-run. One shared completion call per case feeds two treated
pools. All three arms use the CoreLift lite selector so the comparator is not
confounded with MultiStance's tournament.

Arms
  union     frozen MultiStance labels, no completions
  replace   each accepted child replaces its parent (width conserved)
  parallel  accepted children sit beside parents (width grows; extra cap 3)

This is a mechanism probe, not a confirmation study.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
if str(_ROOT / "analysis" / "backbone_v1") not in sys.path:
    sys.path.insert(0, str(_ROOT / "analysis" / "backbone_v1"))

from analysis.mechanism_v2.common import (  # noqa: E402
    DEVELOPMENT_SLICES,
    ROOT,
    FrozenExactSynonymBridge,
    clean_vignette,
    file_sha256,
    load_normalized_cases,
    source_commit,
)
from analysis.mechanism_v2.corelift_experiment import (  # noqa: E402
    DEFAULT_TYPE_MODEL,
    LITE_SELECTOR_PROMPT,
    MODIFIER_AXES,
    _literal_span,
    _span_text,
    candidate_payload,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    assert_target_blind,
    canonical_sha256,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    RunManifest,
    atomic_json,
    sha256_text,
    stable_seed,
    validate_workers,
)
import disagreement_census as dc  # noqa: E402

EXPERIMENT_ID = "MULTISTANCE_CORELIFT_PROBE_V1"
SCHEMA = "multistance_corelift_probe_v1"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/MULTISTANCE_CORELIFT_PROBE"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
GOLD_PATH = ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv"
# Same generator/selector family as MultiStance / APHHM-C (run_aphhm_c.DEFAULT_MODEL).
# CoreLift's DeepSeek lite selector is excluded: it is a new comparator, and in
# this environment it stalled at 300s timeouts / finish_reason=length.
SELECTOR_MODEL = "meta-llama/llama-3.3-70b-instruct"
N_PER_FAMILY = 100
MAX_PARALLEL_EXTRA = 3
DEFAULT_WORKERS = 25
ARMS = ("union", "replace", "parallel")
AXES = set(MODIFIER_AXES)
SAMPLE_SALT = "multistance-corelift-probe-v1"
LOG_STAGES = {
    "DA_d2_heldout200b": (
        ROOT
        / "logs/backbone_v1/diagnosisarena_heldout200b/aphhm_c_multistance_v1/case_stages"
    ),
    "MCR_seq200b": (
        ROOT
        / "logs/backbone_v1/medcasereasoning_200b/aphhm_c_multistance_v1/case_stages"
    ),
}
GOLD_KEYS = {
    "DA_d2_heldout200b": ("da", "d2_heldout200b"),
    "MCR_seq200b": ("mcr", "mcr_200b"),
}

COMPLETION_PROMPT = """Role: source-blind append-only diagnostic completer.
You receive a clean vignette and a frozen candidate list. Do not merge, rename,
delete, or reorder those candidates. Do not propose a different disease family.

For a parent you may propose AT MOST ONE completed child that adds a
vignette-supported modifier. Allowed axes: etiology, anatomy,
subtype_histology, complication, scope_distribution, temporal_evolution,
composite_component. The child must be a more specific diagnosable entity, not
a restatement of the parent. support_spans must be verbatim vignette
substrings.

Return strict JSON only:
{"completions":[{"parent_id":"R#","completed_label":"label",
"axes":["allowed axis"],"support_spans":["verbatim"],"reason":"brief"}]}
Completions may be empty. Never invent patient facts. Never emit a child that
matches any existing candidate.
"""
SELECTOR_PROMPT = LITE_SELECTOR_PROMPT + """
Keep the JSON compact. rationale ≤ 40 words. rejected has at most three
objects. decisive_items may be empty. Do not narrate outside JSON.
"""
PROMPT_HASHES = {
    "completion": sha256_text(COMPLETION_PROMPT),
    "lite_selector": sha256_text(SELECTOR_PROMPT),
}


def _spec(slice_id: str):
    for row in DEVELOPMENT_SLICES:
        if row.slice_id == slice_id:
            return row
    raise KeyError(slice_id)


def load_gold() -> dict[tuple[str, str, str], str]:
    with GOLD_PATH.open(encoding="utf-8") as handle:
        return {
            (row["dataset"], row["slice"], row["case_id"]): row["gold"]
            for row in csv.DictReader(handle)
        }


def _registry_rows(stage: Mapping[str, Any], vignette: str) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(stage.get("stages", {}).get("registry") or [], 1):
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("preferred_label") or "").strip()
        if not label:
            continue
        support = []
        for span in item.get("support_spans") or []:
            literal = _literal_span(vignette, span)
            if literal:
                support.append(literal)
        contradict = []
        for span in item.get("contradict_spans") or []:
            literal = _literal_span(vignette, span)
            if literal:
                contradict.append(literal)
        rows.append(
            {
                "candidate_id": f"R{index}",
                "label": label,
                "stances": list(item.get("stances") or []),
                "raw_support_spans": support[:8],
                "raw_contradict_spans": contradict[:6],
                "generator_assessments": [],
                "candidate_kind": "parent",
                "parent_candidate_id": "",
                "modifier_axes": [],
            }
        )
    return rows


def freeze_cohort(n_per_family: int = N_PER_FAMILY) -> dict[str, Any]:
    gold = load_gold()
    cases = []
    for slice_id, stage_dir in LOG_STAGES.items():
        spec = _spec(slice_id)
        dataset_key, slice_key = GOLD_KEYS[slice_id]
        normalized = load_normalized_cases(spec.cases_json)
        ranked = []
        for path in sorted(stage_dir.glob("*.json")):
            stage = json.loads(path.read_text(encoding="utf-8"))
            source_id = str(stage.get("source_id") or path.stem)
            case = normalized.get(source_id)
            truth = gold.get((dataset_key, slice_key, source_id))
            if case is None or not truth:
                continue
            vignette = clean_vignette(str(case.get("case_text") or ""))[:9000]
            registry = _registry_rows(stage, vignette)
            if not vignette or not registry:
                continue
            ranked.append(
                {
                    "case_key": f"{slice_id}/{source_id}",
                    "slice_id": slice_id,
                    "family": spec.family,
                    "source_id": source_id,
                    "vignette": vignette,
                    "gold": truth,
                    "registry": registry,
                    "original_champion": str(stage.get("champion") or ""),
                    "rank_seed": stable_seed(SAMPLE_SALT, spec.family, source_id),
                }
            )
        ranked.sort(key=lambda row: (row["rank_seed"], row["source_id"]))
        if len(ranked) < n_per_family:
            raise RuntimeError(f"{slice_id}: only {len(ranked)} eligible cases")
        cases.extend(ranked[:n_per_family])
    families = Counter(row["family"] for row in cases)
    return {
        "experiment_id": EXPERIMENT_ID,
        "schema": SCHEMA,
        "n": len(cases),
        "n_per_family": n_per_family,
        "families": dict(families),
        "sample_salt": SAMPLE_SALT,
        "source_commit": source_commit(),
        "prompt_hashes": PROMPT_HASHES,
        "max_parallel_extra": MAX_PARALLEL_EXTRA,
        "predictions": {
            "replace_width_equals_union": True,
            "parallel_width_exceeds_union": True,
            "replace_pool_recall_ge_union": True,
            "parallel_conversion_le_union": True,
            "replace_concept_ge_union_on_DA": True,
        },
        "cases": cases,
    }


def build_completion_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "case_id": case["case_key"],
        "vignette": case["vignette"],
        "candidates": [candidate_payload(row) for row in case["registry"]],
    }
    assert_target_blind(payload)
    return payload


def validate_completions(
    response: Mapping[str, Any],
    case: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
) -> dict[str, Any]:
    parents = {str(row["candidate_id"]): dict(row) for row in case["registry"]}
    existing = {
        key
        for key in (bridge.canonical_key(str(row["label"])) for row in case["registry"])
        if key
    }
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_parents: set[str] = set()
    raw = response.get("completions")
    if not isinstance(raw, list):
        return {
            "accepted": [],
            "rejected": [
                {"parent_id": "", "completed_label": "", "reason": "completions_not_list"}
            ],
        }
    for item in raw:
        if not isinstance(item, Mapping):
            rejected.append(
                {"parent_id": "", "completed_label": "", "reason": "malformed_completion"}
            )
            continue
        parent_id = str(item.get("parent_id") or item.get("parent_candidate_id") or "")
        label = str(item.get("completed_label") or "").strip()
        axes = item.get("axes") or item.get("modifier_axes")
        reason = ""
        spans: list[dict[str, Any]] = []
        if parent_id not in parents:
            reason = "unknown_parent_id"
        elif parent_id in seen_parents:
            reason = "duplicate_completion_for_parent"
        elif not label:
            reason = "empty_completed_label"
        elif not isinstance(axes, list) or not axes or len(axes) != len(set(map(str, axes))):
            reason = "invalid_axes"
        elif set(map(str, axes)) - AXES:
            reason = "unknown_axis"
        elif bridge.equivalent(str(parents[parent_id]["label"]), label):
            reason = "completion_equivalent_to_parent"
        elif bridge.canonical_key(label) in existing:
            reason = "completion_equivalent_to_other_candidate"
        elif not isinstance(item.get("support_spans"), list) or not item.get("support_spans"):
            reason = "no_support_span"
        else:
            for original in item["support_spans"]:
                literal = _literal_span(str(case["vignette"]), original)
                if literal is None:
                    reason = "nonliteral_support_span"
                    break
                spans.append(literal)
        seen_parents.add(parent_id)
        if reason:
            rejected.append(
                {"parent_id": parent_id, "completed_label": label, "reason": reason}
            )
            continue
        child = {
            "candidate_id": f"{parent_id}C",
            "label": label,
            "stances": list(parents[parent_id].get("stances") or []),
            "raw_support_spans": spans[:8],
            "raw_contradict_spans": [],
            "generator_assessments": [],
            "candidate_kind": "completion",
            "parent_candidate_id": parent_id,
            "modifier_axes": [str(axis) for axis in axes],
        }
        accepted.append(child)
        existing.add(bridge.canonical_key(label))
    return {"accepted": accepted, "rejected": rejected}


def pool_for_arm(
    registry: Sequence[Mapping[str, Any]],
    completions: Sequence[Mapping[str, Any]],
    arm: str,
    *,
    max_extra: int = MAX_PARALLEL_EXTRA,
) -> list[dict[str, Any]]:
    parents = [dict(row) for row in registry]
    if arm == "union":
        return parents
    children = [dict(row) for row in completions]
    if arm == "replace":
        replaced = {str(row["parent_candidate_id"]) for row in children}
        kept = [row for row in parents if str(row["candidate_id"]) not in replaced]
        return kept + children
    extras = children[: max(0, int(max_extra))]
    return parents + extras


def build_selector_payload(
    case: Mapping[str, Any], arm: str, pool: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    ordered = sorted(
        pool,
        key=lambda row: (
            stable_seed(
                SAMPLE_SALT, "selector-order", case["case_key"], arm, row["candidate_id"]
            ),
            str(row["candidate_id"]),
        ),
    )
    payload = {
        "case_id": case["case_key"],
        "vignette": case["vignette"],
        "candidates": [candidate_payload(row) for row in ordered],
    }
    assert_target_blind(payload)
    return payload


def _empty_selector(pool: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    champion = str(pool[0]["candidate_id"]) if pool else ""
    return {
        "champion_id": champion,
        "runner_up_id": "",
        "margin": "low",
        "decisive_items": [],
        "rationale": "selector_failed_fallback_first_candidate",
        "rejected": [],
    }


def accept_selector_response(
    response: Mapping[str, Any],
    candidate_ids: set[str],
    vignette: str,
) -> tuple[dict[str, Any], bool, list[str]]:
    """Serve iff champion_id is in the supplied pool.

    Llama CoreLift unserved mass came from failing the whole call when a
    decisive_item was not a verbatim vignette span. MultiStance does not use
    that gate. Ancillary field defects are recorded as quality flags.
    """
    flags: list[str] = []
    champion = str(response.get("champion_id") or "")
    if champion not in candidate_ids:
        return dict(response), False, ["champion_id_not_in_pool"]
    runner = str(response.get("runner_up_id") or "")
    if runner and (runner not in candidate_ids or runner == champion):
        flags.append("runner_up_id_dropped")
        runner = ""
    margin = str(response.get("margin") or "").lower()
    if margin not in {"high", "medium", "low"}:
        flags.append("margin_defaulted_low")
        margin = "low"
    raw_decisive = response.get("decisive_items")
    decisive: list[Any] = []
    if not isinstance(raw_decisive, list):
        flags.append("decisive_items_not_list")
    else:
        if len(raw_decisive) > 3:
            flags.append("decisive_items_truncated")
        for item in raw_decisive[:3]:
            text = _span_text(item)
            if not text:
                continue
            if text not in vignette:
                flags.append("decisive_item_not_verbatim")
                continue
            decisive.append(item)
    raw_rejected = response.get("rejected")
    rejected: list[Any] = []
    if not isinstance(raw_rejected, list):
        flags.append("rejected_not_list")
    else:
        for row in raw_rejected[:3]:
            if not isinstance(row, Mapping):
                flags.append("rejected_malformed")
                continue
            if str(row.get("candidate_id") or "") not in candidate_ids:
                flags.append("rejected_unknown_id")
                continue
            rejected.append(row)
    cleaned = {
        "champion_id": champion,
        "runner_up_id": runner,
        "margin": margin,
        "decisive_items": decisive,
        "rationale": str(response.get("rationale") or "")[:500],
        "rejected": rejected,
    }
    return cleaned, True, flags


def exact_mcnemar(a_only: int, b_only: int) -> float:
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(math.comb(n, i) for i in range(k + 1))
    return float(min(1.0, 2.0 * tail * (0.5**n)))


def _hit(label: str, gold: str) -> bool:
    return bool(label) and dc.match(label, gold)


def summarize(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, list[Mapping[str, Any]]] = {"DA": [], "MCR": []}
    for row in cases:
        by_family[str(row["family"])].append(row)
    families: dict[str, Any] = {}
    for family, rows in by_family.items():
        n = len(rows)
        block: dict[str, Any] = {"n": n}
        for arm in ARMS:
            widths = [int(row["arms"][arm]["width"]) for row in rows]
            pool_hits = [int(row["arms"][arm]["pool_hit"]) for row in rows]
            concept_hits = [int(row["arms"][arm]["concept_hit"]) for row in rows]
            pool_sum = sum(pool_hits)
            concept_sum = sum(concept_hits)
            conversion = (concept_sum / pool_sum) if pool_sum else 0.0
            block[arm] = {
                "width": round(sum(widths) / n, 3) if n else None,
                "pool_recall": round(pool_sum / n, 4) if n else None,
                "concept": round(concept_sum / n, 4) if n else None,
                "conversion": round(conversion, 4),
                "served": round(
                    sum(int(row["arms"][arm]["served"]) for row in rows) / n, 4
                )
                if n
                else None,
            }
        flags: Counter[str] = Counter()
        unserved = 0
        for row in rows:
            for arm in ARMS:
                cell = row["arms"][arm]
                if not cell.get("served"):
                    unserved += 1
                for flag in cell.get("quality_flags") or []:
                    flags[str(flag)] += 1
        block["unserved_conditions"] = unserved
        block["quality_flags"] = dict(flags)
        for left, right in (
            ("replace", "union"),
            ("parallel", "union"),
            ("replace", "parallel"),
        ):
            a_only = b_only = 0
            for row in rows:
                a = bool(row["arms"][left]["concept_hit"])
                b = bool(row["arms"][right]["concept_hit"])
                a_only += int(a and not b)
                b_only += int(b and not a)
            block[f"{left}_vs_{right}"] = {
                "left_only": a_only,
                "right_only": b_only,
                "delta_pp": round(
                    100.0
                    * ((block[left]["concept"] or 0) - (block[right]["concept"] or 0)),
                    2,
                ),
                "mcnemar_p": round(exact_mcnemar(a_only, b_only), 4),
            }
        families[family] = block
    n_complete = sum(len(row.get("accepted_completions") or []) for row in cases)
    predictions: dict[str, Any] = {}
    da = families.get("DA") or {}
    mcr = families.get("MCR") or {}
    if da and mcr:
        predictions = {
            "replace_width_equals_union": all(
                abs((fam["replace"]["width"] or 0) - (fam["union"]["width"] or 0)) < 1e-9
                for fam in (da, mcr)
            ),
            "parallel_width_exceeds_union": all(
                (fam["parallel"]["width"] or 0) > (fam["union"]["width"] or 0)
                for fam in (da, mcr)
            ),
            "replace_pool_recall_ge_union": all(
                (fam["replace"]["pool_recall"] or 0)
                >= (fam["union"]["pool_recall"] or 0)
                for fam in (da, mcr)
            ),
            "parallel_conversion_le_union": all(
                (fam["parallel"]["conversion"] or 0)
                <= (fam["union"]["conversion"] or 0)
                for fam in (da, mcr)
            ),
            "replace_concept_ge_union_on_DA": (da["replace"]["concept"] or 0)
            >= (da["union"]["concept"] or 0),
        }
    return {
        "n": len(cases),
        "selector_model": SELECTOR_MODEL,
        "completions_accepted_total": n_complete,
        "completions_per_case": round(n_complete / len(cases), 3) if cases else 0.0,
        "families": families,
        "prediction_held": predictions,
    }


def _write_report(out_dir: Path, summary: Mapping[str, Any]) -> None:
    lines = [
        "# MultiStance × CoreLift 200-case probe",
        "",
        f"Experiment `{EXPERIMENT_ID}`. Holdout-200b, 100 DA + 100 MCR. "
        "Frozen MultiStance registries; one shared append-only completion call; "
        f"three arms share the CoreLift lite selector on `{SELECTOR_MODEL}` "
        "(MultiStance/APHHM-C default; DeepSeek excluded).",
        "",
        "## Predictions (pre-registered)",
        "",
        "1. `replace` width ≈ `union` width.",
        "2. `parallel` width > `union` width.",
        "3. `replace` pool recall ≥ `union`.",
        "4. `parallel` conversion ≤ `union` conversion.",
        "5. `replace` concept ≥ `union` concept on DA.",
        "",
        "This is a mechanism probe. McNemar p-values are descriptive; n=100 per family.",
        "",
        "## Results",
        "",
        f"- completions accepted: {summary.get('completions_accepted_total')} "
        f"({summary.get('completions_per_case')} / case)",
        f"- prediction held: `{json.dumps(summary.get('prediction_held') or {}, ensure_ascii=False)}`",
        "",
    ]
    for family, block in (summary.get("families") or {}).items():
        lines.append(f"### {family} n={block['n']}")
        lines.append("")
        lines.append("| arm | width | pool recall | conversion | concept | served |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for arm in ARMS:
            row = block[arm]
            lines.append(
                f"| {arm} | {row['width']} | {row['pool_recall']} | "
                f"{row['conversion']} | {row['concept']} | {row['served']} |"
            )
        lines.append("")
        for key in ("replace_vs_union", "parallel_vs_union", "replace_vs_parallel"):
            contrast = block[key]
            lines.append(
                f"- `{key}`: {contrast['left_only']}-{contrast['right_only']}, "
                f"Δ {contrast['delta_pp']:+.2f}pp, p={contrast['mcnemar_p']}"
            )
        lines.append("")
    lines.extend(
        [
            "## How to read this",
            "",
            "- `parallel` is a negative control: extra siblings sitting beside parents.",
            "- Do not treat a parallel win as evidence that CoreLift belongs on a wide pool.",
            "- MCR had no CoreLift gain on the original ~4.7-wide experiment; do not expect task lift here.",
            "- Gold never entered an online payload. A case is served iff the selector returns a champion ID in the supplied pool. Non-verbatim decisive_items are quality flags, not service failures.",
            "",
        ]
    )
    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def run(out_dir: Path, *, workers: int, cache_only: bool = False) -> dict[str, Any]:
    workers = validate_workers(workers, rag=False)
    print(
        f"probe start workers={workers} selector={SELECTOR_MODEL} "
        f"completer={DEFAULT_TYPE_MODEL} cache_only={cache_only}",
        flush=True,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze_path = out_dir / "freeze.json"
    if freeze_path.is_file():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    else:
        freeze = freeze_cohort()
        atomic_json(freeze_path, freeze)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    completion_caller = OnlineJSONCaller(
        out_dir=out_dir / "completion_cache",
        model=DEFAULT_TYPE_MODEL,
        telemetry_path=out_dir / "completion_telemetry.jsonl",
        call_timeout=180,
        max_retries=1,
    )
    selector_caller = OnlineJSONCaller(
        out_dir=out_dir / "selector_cache_llama",
        model=SELECTOR_MODEL,
        telemetry_path=out_dir / "selector_telemetry.jsonl",
        call_timeout=180,
        max_retries=1,
    )

    def complete_one(case: dict[str, Any]) -> dict[str, Any]:
        payload = build_completion_payload(case)
        outcome = completion_caller.call(
            module="MultiStanceCoreLiftCompleter",
            prompt=COMPLETION_PROMPT,
            payload=payload,
            cache_only=cache_only,
        )
        response = outcome.response if outcome.success else {"completions": []}
        validated = validate_completions(response, case, bridge)
        return {
            **case,
            "completion_success": bool(outcome.success),
            "completion_error": outcome.error,
            "accepted_completions": validated["accepted"],
            "rejected_completions": validated["rejected"],
        }

    completed = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(complete_one, dict(case)) for case in freeze["cases"]]
        for future in as_completed(futures):
            completed.append(future.result())
    completed.sort(key=lambda row: row["case_key"])
    atomic_json(
        out_dir / "completions.json",
        {
            "n": len(completed),
            "cases": [
                {
                    "case_key": row["case_key"],
                    "accepted": row["accepted_completions"],
                    "rejected": row["rejected_completions"],
                    "success": row["completion_success"],
                }
                for row in completed
            ],
        },
    )

    jobs = []
    for case in completed:
        for arm in ARMS:
            pool_rows = pool_for_arm(
                case["registry"], case["accepted_completions"], arm
            )
            jobs.append(
                (case, arm, pool_rows, build_selector_payload(case, arm, pool_rows))
            )

    selected: dict[tuple[str, str], dict[str, Any]] = {}
    n_jobs = len(jobs)
    done_lock = threading.Lock()
    n_done = 0

    def select_one(
        item: tuple[dict[str, Any], str, list[dict[str, Any]], dict[str, Any]]
    ):
        case, arm, pool_rows, payload = item
        ids = {str(row["candidate_id"]) for row in pool_rows}
        flags: list[str] = []
        try:
            outcome = selector_caller.call(
                module="MultiStanceCoreLiftSelector",
                prompt=SELECTOR_PROMPT,
                payload=payload,
                cache_only=cache_only,
            )
            response = outcome.response if outcome.success else {}
            transport_error = "" if outcome.success else (outcome.error or "selector_transport_failure")
        except Exception as exc:
            response = {}
            transport_error = f"{type(exc).__name__}: {exc}"
        cleaned, champion_ok, flags = accept_selector_response(
            response, ids, str(case["vignette"])
        )
        served = champion_ok and not transport_error
        if not served:
            cleaned = _empty_selector(pool_rows)
            if transport_error:
                flags = [transport_error, *flags]
        by_id = {str(row["candidate_id"]): row for row in pool_rows}
        champion_id = str(cleaned.get("champion_id") or "")
        champion = str(by_id.get(champion_id, {}).get("label") or "")
        gold = str(case["gold"])
        labels = [str(row["label"]) for row in pool_rows]
        return (case["case_key"], arm), {
            "arm": arm,
            "width": len(pool_rows),
            "served": served,
            "selector_error": None if served else (transport_error or ";".join(flags) or "unserved"),
            "quality_flags": flags,
            "champion_id": champion_id,
            "champion": champion,
            "pool_hit": int(dc.any_match(labels, gold)),
            "concept_hit": int(_hit(champion, gold)),
            "labels": labels,
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(select_one, item) for item in jobs]
        for future in as_completed(futures):
            key, value = future.result()
            selected[key] = value
            with done_lock:
                n_done += 1
                if n_done % 25 == 0 or n_done == n_jobs:
                    print(
                        f"selector completed={n_done}/{n_jobs} "
                        f"workers={workers} model={SELECTOR_MODEL}",
                        flush=True,
                    )

    scored = []
    for case in completed:
        arms = {arm: selected[(case["case_key"], arm)] for arm in ARMS}
        scored.append(
            {
                "case_key": case["case_key"],
                "family": case["family"],
                "source_id": case["source_id"],
                "gold": case["gold"],
                "original_champion": case["original_champion"],
                "n_registry": len(case["registry"]),
                "accepted_completions": case["accepted_completions"],
                "n_accepted": len(case["accepted_completions"]),
                "arms": arms,
            }
        )
    summary = summarize(scored)
    atomic_json(out_dir / "scored.json", {"n": len(scored), "cases": scored})
    atomic_json(out_dir / "summary.json", summary)
    manifest = RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id="all_three",
        dataset="holdout200b_probe_DA100_MCR100",
        model=f"{DEFAULT_TYPE_MODEL}+{SELECTOR_MODEL}",
        workers=workers,
        rag=False,
        source_commit=str(freeze.get("source_commit") or source_commit()),
        prompt_hashes=PROMPT_HASHES,
        input_hash=file_sha256(freeze_path),
        selection_freeze="SHA sample_salt + frozen MultiStance registries",
        endpoint_contract="target-blind completion and selection; gold used only in analyze",
    )
    manifest.write(out_dir / "manifest.json")
    atomic_json(
        out_dir / "environment.json",
        {
            "python": sys.version.split()[0],
            "selector_model": SELECTOR_MODEL,
            "type_completion_model": DEFAULT_TYPE_MODEL,
            "workers": workers,
            "n": len(scored),
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    _write_report(out_dir, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.freeze_only:
        freeze = freeze_cohort()
        args.out.mkdir(parents=True, exist_ok=True)
        atomic_json(args.out / "freeze.json", freeze)
        print(json.dumps({"n": freeze["n"], "families": freeze["families"]}, indent=2))
        return 0
    summary = run(args.out, workers=args.workers, cache_only=args.cache_only)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
