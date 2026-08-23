"""Score CoreLift predictions on the Forest-report backbone_v1 chain.

The Forest / IMPC / Collapse3c 800-case table uses:

* DA task = llama-3.3-70b ``typed_llm_disagreement_rag`` option@1
* MCR task = official Prompt-7 ``diagnostic_hit`` (gemini-2.5-flash judge)
* concept  = ``dc.match(champion, gold)`` against ``r4_facts/pooled.tsv``

This is a different estimand from CoreLift's gemini DA projection.  Exporting
CoreLift champions into the mosaic ``predictions.jsonl`` contract and calling
the frozen ``score_da`` / ``score_mcr`` helpers is the only way to put the
numbers on the same table.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

from analysis.mechanism_v2.corelift_evaluate import exact_mcnemar  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    NON_RAG_MAX_WORKERS,
    RAG_MAX_WORKERS,
    atomic_json,
    validate_workers,
)
from run_backbone_v1 import SUBSETS, score_da, score_mcr  # noqa: E402

import disagreement_census as dc  # noqa: E402

LLAMA_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_SOURCE = (
    ROOT / "analysis/mechanism_v2/results/SLOT_YIELD_BREAKTHROUGH/case_conditions.jsonl"
)
DEFAULT_OUT = DEFAULT_SOURCE.parent / "legacy_backbone_score"
HOLDOUT_JSON = ROOT / "analysis/backbone_v1/mosaic_eval/aphhm_c_holdout.json"
FACTS_TSV = ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv"
LOGS = ROOT / "logs/backbone_v1"
REFERENCE_ARMS = {
    "Forest": "mosaic_forest_v1",
    "IMPC": "mosaic_impc_v1",
    "Collapse3c": "aphhm_c_collapse3c_v1",
}
SLICE_SPEC = {
    "DA_d2_seq100": {
        "family": "DA",
        "dataset_dir": "diagnosisarena",
        "adapter_dataset": "diagnosisarena",
        "facts_dataset": "da",
        "facts_slice": "d2_seq100",
        "subset": SUBSETS["diagnosisarena"],
    },
    "DA_d2_heldout100": {
        "family": "DA",
        "dataset_dir": "diagnosisarena_heldout",
        "adapter_dataset": "diagnosisarena",
        "facts_dataset": "da",
        "facts_slice": "d2_heldout100",
        "subset": SUBSETS["diagnosisarena_heldout"],
    },
    "DA_d2_heldout200b": {
        "family": "DA",
        "dataset_dir": "diagnosisarena_heldout200b",
        "adapter_dataset": "diagnosisarena",
        "facts_dataset": "da",
        "facts_slice": "d2_heldout200b",
        "subset": SUBSETS["diagnosisarena_heldout200b"],
    },
    "MCR_v1_seq100": {
        "family": "MCR",
        "dataset_dir": "medcasereasoning",
        "adapter_dataset": "medcasereasoning",
        "facts_dataset": "mcr",
        "facts_slice": "mcr_v1",
        "subset": SUBSETS["medcasereasoning"],
    },
    "MCR_v2_seq100": {
        "family": "MCR",
        "dataset_dir": "medcasereasoning_v2",
        "adapter_dataset": "medcasereasoning",
        "facts_dataset": "mcr",
        "facts_slice": "mcr_v2",
        "subset": SUBSETS["medcasereasoning_v2"],
    },
    "MCR_seq200b": {
        "family": "MCR",
        "dataset_dir": "medcasereasoning_200b",
        "adapter_dataset": "medcasereasoning",
        "facts_dataset": "mcr",
        "facts_slice": "mcr_200b",
        "subset": SUBSETS["medcasereasoning_200b"],
    },
}


def mosaic_case_id(adapter_dataset: str, source_id: str) -> str:
    try:
        return f"{adapter_dataset}__{int(source_id):06d}"
    except ValueError:
        return f"{adapter_dataset}__{source_id}"


def prediction_row(row: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    source_id = str(row["source_id"])
    champion = str(row.get("champion_label") or "").strip()
    runner = str(row.get("runner_up_label") or "").strip()
    ordered = [label for label in (champion, runner) if label]
    return {
        "arm": str(row["arm"]),
        "case_id": mosaic_case_id(str(spec["adapter_dataset"]), source_id),
        "source_id": source_id,
        "dataset": spec["dataset_dir"],
        "list_k": 2,
        "success": bool(row.get("success") and champion),
        "ordered_diagnoses": ordered,
        "top2_diagnoses": ordered[:2],
        "corelift_case_key": str(row["case_key"]),
        "corelift_slice": str(row["slice"]),
    }


def slice_dest(out: Path, arm: str, slice_id: str) -> Path:
    spec = SLICE_SPEC[slice_id]
    return Path(out) / "runs" / arm / spec["dataset_dir"]


def export_predictions(source: Path, out: Path) -> dict[str, Any]:
    rows = read_jsonl(source)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        slice_id = str(row["slice"])
        if slice_id not in SLICE_SPEC:
            raise AssertionError(f"unknown CoreLift slice {slice_id}")
        grouped[(str(row["arm"]), slice_id)].append(row)
    written = []
    for (arm, slice_id), group in sorted(grouped.items()):
        spec = SLICE_SPEC[slice_id]
        dest = slice_dest(out, arm, slice_id)
        dest.mkdir(parents=True, exist_ok=True)
        preds = [prediction_row(row, spec) for row in group]
        preds.sort(key=lambda item: int(item["source_id"]) if item["source_id"].isdigit() else item["source_id"])
        write_jsonl(dest / "predictions.jsonl", preds)
        atomic_json(
            dest / "export_manifest.json",
            {
                "arm": arm,
                "slice": slice_id,
                "n": len(preds),
                "n_served": sum(1 for row in preds if row["success"]),
                "source": str(source),
            },
        )
        written.append({"arm": arm, "slice": slice_id, "n": len(preds)})
    summary = {
        "schema_version": "corelift-legacy-export-v1",
        "source": str(source),
        "n_groups": len(written),
        "groups": written,
    }
    atomic_json(out / "export_summary.json", summary)
    return summary


def load_facts() -> dict[tuple[str, str, str], str]:
    gold = {}
    for row in csv.DictReader(FACTS_TSV.open(encoding="utf-8")):
        gold[(row["dataset"], row["slice"], str(row["case_id"]))] = row["gold"]
    return gold


def concept_flags(preds: Sequence[Mapping[str, Any]], spec: Mapping[str, Any], gold: Mapping[tuple[str, str, str], str]) -> dict[str, bool]:
    flags = {}
    for pred in preds:
        source_id = str(pred["source_id"])
        key = (spec["facts_dataset"], spec["facts_slice"], source_id)
        if key not in gold:
            raise AssertionError(f"gold missing for {key}")
        champion = (pred.get("ordered_diagnoses") or [""])[0]
        flags[source_id] = bool(champion and dc.match(str(champion), gold[key]))
    return flags


def scoring_complete(dest: Path, spec: Mapping[str, Any], *, da: bool, mcr: bool) -> bool:
    if spec["family"] == "DA" and da:
        return (dest / "mapper" / "summary.json").is_file()
    if spec["family"] == "MCR" and mcr:
        return (dest / "mcr_eval_summary.json").is_file()
    return True


def score_one_slice(
    dest: Path,
    spec: Mapping[str, Any],
    *,
    da: bool,
    mcr: bool,
    da_workers: int,
    mcr_workers: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {"dir": str(dest)}
    if spec["family"] == "DA" and da:
        scored = score_da(dest, spec["subset"], LLAMA_MODEL, workers=da_workers)
        result["da"] = scored
    if spec["family"] == "MCR" and mcr:
        scored = score_mcr(dest, spec["subset"] / "cases.parquet", workers=mcr_workers)
        result["mcr"] = scored
    return result


def load_option_top1(dest: Path) -> dict[str, bool]:
    path = dest / "mapper" / "records.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records", data) if isinstance(data, dict) else data
    return {
        str(row.get("source_id") or row["case_id"]): bool(row["option_top1"])
        for row in records
    }


def load_mcr_hits(dest: Path) -> dict[str, bool]:
    directory = dest / "annotate" / "official_eval_llm" / "case_scores"
    if not directory.is_dir():
        return {}
    flags = {}
    for path in directory.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        flags[str(row["case_id"])] = bool(row.get("diagnostic_hit"))
    return flags


def load_reference_task(arm_dir_name: str, spec: Mapping[str, Any]) -> dict[str, bool]:
    run = LOGS / spec["dataset_dir"] / arm_dir_name
    if spec["family"] == "DA":
        path = run / "mapper" / "records.json"
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("records", data) if isinstance(data, dict) else data
        return {
            str(row.get("source_id") or row["case_id"]): bool(row["option_top1"])
            for row in records
        }
    directory = run / "annotate" / "official_eval_llm" / "case_scores"
    if not directory.is_dir():
        return {}
    flags = {}
    for path in directory.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        flags[str(row["case_id"])] = bool(row.get("diagnostic_hit"))
    return flags


def load_reference_concept(arm_dir_name: str, spec: Mapping[str, Any], gold: Mapping[tuple[str, str, str], str]) -> dict[str, bool]:
    path = LOGS / spec["dataset_dir"] / arm_dir_name / "predictions.jsonl"
    if not path.is_file():
        return {}
    preds = read_jsonl(path)
    return concept_flags(preds, spec, gold)


def mcnemar(left: Mapping[str, bool], right: Mapping[str, bool]) -> dict[str, Any]:
    shared = sorted(set(left) & set(right))
    left_only = sum(1 for key in shared if left[key] and not right[key])
    right_only = sum(1 for key in shared if right[key] and not left[key])
    return {
        "n_paired": len(shared),
        "left_only": left_only,
        "right_only": right_only,
        "delta_right_minus_left": (right_only - left_only) / len(shared) if shared else None,
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
    }


def compile_report(out: Path) -> dict[str, Any]:
    gold = load_facts()
    published = json.loads(HOLDOUT_JSON.read_text(encoding="utf-8"))
    arms = sorted({path.parent.parent.name for path in Path(out).glob("runs/*/*/predictions.jsonl")})
    per_arm: dict[str, dict[str, Any]] = {}
    for arm in arms:
        da_task: dict[str, bool] = {}
        da_concept: dict[str, bool] = {}
        mcr_task: dict[str, bool] = {}
        mcr_concept: dict[str, bool] = {}
        served = {"DA": 0, "MCR": 0}
        intention = {"DA": 0, "MCR": 0}
        for slice_id, spec in SLICE_SPEC.items():
            dest = slice_dest(out, arm, slice_id)
            preds_path = dest / "predictions.jsonl"
            if not preds_path.is_file():
                continue
            preds = read_jsonl(preds_path)
            family = spec["family"]
            intention[family] += len(preds)
            served[family] += sum(1 for row in preds if row.get("success"))
            prefixed = {f"{spec['dataset_dir']}:{sid}": value for sid, value in concept_flags(preds, spec, gold).items()}
            if family == "DA":
                da_concept.update(prefixed)
                da_task.update(
                    {f"{spec['dataset_dir']}:{sid}": value for sid, value in load_option_top1(dest).items()}
                )
            else:
                mcr_concept.update(prefixed)
                mcr_task.update(
                    {f"{spec['dataset_dir']}:{sid}": value for sid, value in load_mcr_hits(dest).items()}
                )
        def _rate(flags: Mapping[str, bool], denom: int) -> dict[str, Any]:
            return {
                "n_scored": len(flags),
                "hits": sum(flags.values()),
                "rate_among_scored": (sum(flags.values()) / len(flags)) if flags else None,
                "rate_ita": (sum(flags.values()) / denom) if denom else None,
            }

        per_arm[arm] = {
            "intention": intention,
            "served": served,
            "DA": {
                "task": _rate(da_task, intention["DA"]),
                "concept": _rate(da_concept, intention["DA"]),
            },
            "MCR": {
                "task": _rate(mcr_task, intention["MCR"]),
                "concept": _rate(mcr_concept, intention["MCR"]),
            },
            "flags": {
                "DA_task": da_task,
                "DA_concept": da_concept,
                "MCR_task": mcr_task,
                "MCR_concept": mcr_concept,
            },
        }

    reference_flags: dict[str, dict[str, dict[str, bool]]] = {}
    for name, arm_dir in REFERENCE_ARMS.items():
        da_task: dict[str, bool] = {}
        da_concept: dict[str, bool] = {}
        mcr_task: dict[str, bool] = {}
        mcr_concept: dict[str, bool] = {}
        for spec in SLICE_SPEC.values():
            prefix = spec["dataset_dir"]
            task = {
                f"{prefix}:{sid}": value
                for sid, value in load_reference_task(arm_dir, spec).items()
            }
            concept = {
                f"{prefix}:{sid}": value
                for sid, value in load_reference_concept(arm_dir, spec, gold).items()
            }
            if spec["family"] == "DA":
                da_task.update(task)
                da_concept.update(concept)
            else:
                mcr_task.update(task)
                mcr_concept.update(concept)
        reference_flags[name] = {
            "DA_task": da_task,
            "DA_concept": da_concept,
            "MCR_task": mcr_task,
            "MCR_concept": mcr_concept,
        }

    contrasts = []
    for arm, payload in per_arm.items():
        for ref_name, ref_flags in reference_flags.items():
            for metric in ("DA_task", "DA_concept", "MCR_task", "MCR_concept"):
                contrasts.append(
                    {
                        "corelift_arm": arm,
                        "reference": ref_name,
                        "metric": metric,
                        **mcnemar(ref_flags[metric], payload["flags"][metric]),
                    }
                )

    compact = {
        arm: {
            "DA_task": payload["DA"]["task"]["rate_ita"],
            "DA_concept": payload["DA"]["concept"]["rate_ita"],
            "MCR_task": payload["MCR"]["task"]["rate_ita"],
            "MCR_concept": payload["MCR"]["concept"]["rate_ita"],
            "n_da_task_scored": payload["DA"]["task"]["n_scored"],
            "n_mcr_task_scored": payload["MCR"]["task"]["n_scored"],
        }
        for arm, payload in per_arm.items()
    }
    report = {
        "schema_version": "corelift-legacy-backbone-score-v1",
        "chain": {
            "da_task": "llama-3.3-70b typed_llm_disagreement_rag option@1",
            "mcr_task": "official Prompt-7 diagnostic_hit (gemini-2.5-flash)",
            "concept": "dc.match(champion, r4_facts gold)",
        },
        "published_forest_table": {
            "DA400": published["DA400"],
            "MCR400": published["MCR400"],
        },
        "corelift_arms": compact,
        "contrasts": contrasts,
        "warning": (
            "ITA rates treat mapper/judge failures as zero. Compare n_scored "
            "against intention=400 before reading a rate as the Forest table."
        ),
    }
    # Drop bulky flags from the written report; keep them only for contrasts.
    atomic_json(out / "legacy_leaderboard.json", report)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--score-da", action="store_true")
    parser.add_argument("--score-mcr", action="store_true")
    parser.add_argument("--arm", action="append", default=[])
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="optional override; RAG DA is capped at 25, non-RAG MCR at 50",
    )
    parser.add_argument("--da-workers", type=int, default=RAG_MAX_WORKERS)
    parser.add_argument("--mcr-workers", type=int, default=NON_RAG_MAX_WORKERS)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-score slices that already have mapper/mcr summaries",
    )
    parser.add_argument("--compile", action="store_true")
    return parser.parse_args(argv)


def resolve_workers(args: argparse.Namespace) -> tuple[int, int]:
    if args.workers is None:
        da_workers = args.da_workers
        mcr_workers = args.mcr_workers
    else:
        da_workers = min(int(args.workers), RAG_MAX_WORKERS)
        mcr_workers = min(int(args.workers), NON_RAG_MAX_WORKERS)
    return (
        validate_workers(da_workers, rag=True),
        validate_workers(mcr_workers, rag=False),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    da_workers, mcr_workers = resolve_workers(args)
    if args.export_only:
        print(json.dumps(export_predictions(args.source, out), indent=2))
        return 0
    wanted = set(args.arm)
    if args.score_da or args.score_mcr:
        for dest in sorted(out.glob("runs/*/*")):
            arm = dest.parent.name
            dataset_dir = dest.name
            if wanted and arm not in wanted:
                continue
            spec = next(s for s in SLICE_SPEC.values() if s["dataset_dir"] == dataset_dir)
            if spec["family"] == "DA" and not args.score_da:
                continue
            if spec["family"] == "MCR" and not args.score_mcr:
                continue
            if not args.force and scoring_complete(
                dest, spec, da=args.score_da, mcr=args.score_mcr
            ):
                print(f"skip complete {arm} {dataset_dir}", flush=True)
                continue
            print(
                f"scoring {arm} {dataset_dir} "
                f"da_workers={da_workers} mcr_workers={mcr_workers}",
                flush=True,
            )
            score_one_slice(
                dest,
                spec,
                da=args.score_da,
                mcr=args.score_mcr,
                da_workers=da_workers,
                mcr_workers=mcr_workers,
            )
    if args.compile:
        report = compile_report(out)
        print(json.dumps(report["corelift_arms"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
