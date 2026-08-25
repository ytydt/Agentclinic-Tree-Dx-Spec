"""Paired DCI ablation on an existing no-leak held-out run.

Paper Table 2: CoT (no DCI) vs +DCI, CGME off. Here the no-DCI arm is the
already-recorded intuitive Top-k (stage=intuitive), scored with the same
official endpoints as the DCI arm (DA mapper@1, MCR Prompt 7).

  PYTHONPATH=. python -m src.ablate_dci \
    --dci-run runs/heldout_llama33_nomem_noleak_da200_mcr200 --parent ..
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.score_official import score_da, score_mcr
from src.utils import diagnoses_match, parse_json_object


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _norm(text: str) -> str:
    return " ".join(str(text).lower().split()).strip(" .;:,")


def _pad(names: list[str], k: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        text = str(name or "").strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= k:
            break
    while len(out) < k:
        out.append("")
    return out[:k]


def _intuitive_lists(trace_path: Path) -> dict[tuple[str, str], list[str]]:
    out: dict[tuple[str, str], list[str]] = {}
    for row in _read_jsonl(trace_path):
        if row.get("stage") != "intuitive":
            continue
        key = (str(row.get("slice") or ""), str(row.get("case_id") or ""))
        names: list[str] = []
        try:
            obj = parse_json_object(str(row.get("assistant") or ""))
            for item in obj.get("diagnoses") or []:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
        except ValueError:
            names = []
        out[key] = names
    return out


def write_cot_predictions(dci_run: Path, cot_run: Path) -> dict[str, Any]:
    cases = { (r["slice"], str(r["case_id"])): r for r in _read_jsonl(dci_run / "cases.jsonl") }
    intuit = _intuitive_lists(dci_run / "llm_calls.jsonl")
    stats = {
        "n_cases": 0,
        "n_cot_from_trace": 0,
        "n_cot_fallback_dset": 0,
        "n_audit_eq_cot1": 0,
        "n_audit_in_cot_list": 0,
        "n_audit_outside_cot": 0,
        "exact_cot1": 0,
        "exact_dci": 0,
        "by_slice": {},
    }
    for split, pred_src in (("da", dci_run / "da" / "predictions.jsonl"), ("mcr", dci_run / "mcr" / "predictions.jsonl")):
        dest = cot_run / split
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / "predictions.jsonl"
        lines: list[str] = []
        slice_stats = {
            "n": 0,
            "audit_eq_cot1": 0,
            "exact_cot1": 0,
            "exact_dci": 0,
        }
        for pred in _read_jsonl(pred_src):
            slice_name = str(pred.get("slice") or "")
            source_id = str(pred.get("source_id") or "")
            case = cases[(slice_name, source_id)]
            cot = intuit.get((slice_name, source_id)) or []
            used_trace = bool(cot)
            if not cot:
                cot = list(case.get("dset") or [])
            ordered = _pad(cot, 5)
            top2 = _pad(cot, 2)
            row = dict(pred)
            row["arm"] = "intuitive_cot_nodci"
            row["ordered_diagnoses"] = ordered
            row["top2_diagnoses"] = top2
            row["ablation"] = "no_dci_intuitive_topk"
            lines.append(json.dumps(row, ensure_ascii=False))
            diag = str(case.get("diagnosis") or "")
            cot1 = ordered[0]
            eq = _norm(diag) == _norm(cot1)
            inn = any(_norm(diag) == _norm(x) for x in ordered if x)
            stats["n_cases"] += 1
            stats["n_cot_from_trace"] += int(used_trace)
            stats["n_cot_fallback_dset"] += int(not used_trace)
            stats["n_audit_eq_cot1"] += int(eq)
            stats["n_audit_in_cot_list"] += int(inn)
            stats["n_audit_outside_cot"] += int(bool(diag) and not inn)
            stats["exact_cot1"] += int(diagnoses_match(cot1, case.get("y_gt") or ""))
            stats["exact_dci"] += int(diagnoses_match(diag, case.get("y_gt") or ""))
            slice_stats["n"] += 1
            slice_stats["audit_eq_cot1"] += int(eq)
            slice_stats["exact_cot1"] += int(diagnoses_match(cot1, case.get("y_gt") or ""))
            slice_stats["exact_dci"] += int(diagnoses_match(diag, case.get("y_gt") or ""))
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        stats["by_slice"][split] = slice_stats
    return stats


def _load_da_hits(records_path: Path) -> dict[str, bool]:
    if not records_path.is_file():
        return {}
    doc = json.loads(records_path.read_text(encoding="utf-8"))
    rows = doc.get("records") if isinstance(doc, dict) else doc
    out: dict[str, bool] = {}
    for row in rows or []:
        out[str(row.get("case_id") or "")] = bool(row.get("option_top1"))
    return out


def _load_mcr_hits(scores_dir: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if not scores_dir.is_dir():
        return out
    for path in scores_dir.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        out[str(doc.get("case_id") or path.stem)] = bool(doc.get("diagnostic_hit"))
    return out


def _paired(a: dict[str, bool], b: dict[str, bool]) -> dict[str, Any]:
    ids = sorted(set(a) & set(b))
    both = sum(1 for i in ids if a[i] and b[i])
    a_only = sum(1 for i in ids if a[i] and not b[i])
    b_only = sum(1 for i in ids if b[i] and not a[i])
    neither = sum(1 for i in ids if (not a[i]) and (not b[i]))
    n = len(ids)
    acc_a = (both + a_only) / n if n else None
    acc_b = (both + b_only) / n if n else None
    return {
        "n_paired": n,
        "acc_cot": acc_a,
        "acc_dci": acc_b,
        "delta_dci_minus_cot": (acc_b - acc_a) if n else None,
        "both_hit": both,
        "cot_only": a_only,
        "dci_only": b_only,
        "both_miss": neither,
        "n_discordant": a_only + b_only,
    }


def _verdict(da: dict[str, Any], mcr: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    da_delta = da.get("delta_dci_minus_cot")
    mcr_delta = mcr.get("delta_dci_minus_cot")
    notes = []
    da_help = da_delta is not None and da_delta > 0.02
    mcr_help = mcr_delta is not None and mcr_delta > 0.02
    da_harm = da_delta is not None and da_delta < -0.02
    mcr_harm = mcr_delta is not None and mcr_delta < -0.02
    if da_delta is not None:
        notes.append(f"DA mapper@1 DCI−CoT = {da_delta:+.3f}")
    if mcr_delta is not None:
        notes.append(f"MCR Prompt7 DCI−CoT = {mcr_delta:+.3f}")
    stay = override.get("n_audit_eq_cot1")
    total = override.get("n_cases")
    if stay is not None and total:
        notes.append(
            f"audit keeps CoT rank-1 on {stay}/{total} = {stay/total:.1%} of cases"
        )
    if da_help and mcr_help:
        useful, label = True, "DCI_ADDS_VALUE_BOTH"
    elif (da_help and mcr_harm) or (mcr_help and da_harm):
        useful, label = False, "DCI_MIXED_NOT_GENERALLY_USEFUL"
    elif da_harm or mcr_harm:
        useful, label = False, "DCI_HARMS_ON_THIS_SPLIT"
    elif da_help or mcr_help:
        useful, label = True, "DCI_ADDS_VALUE_ONE_ENDPOINT"
    else:
        useful, label = False, "DCI_NULL_ON_THIS_SPLIT"
    return {"useful_on_this_split": useful, "label": label, "notes": notes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dci-run",
        default="runs/heldout_llama33_nomem_noleak_da200_mcr200",
    )
    parser.add_argument("--parent", default="..")
    parser.add_argument("--skip-score", action="store_true")
    parser.add_argument("--mapper-workers", type=int, default=25)
    parser.add_argument("--judge-workers", type=int, default=50)
    parser.add_argument(
        "--mapper-model",
        default="meta-llama/llama-3.3-70b-instruct",
    )
    args = parser.parse_args()

    dci_run = Path(args.dci_run).resolve()
    parent = Path(args.parent).resolve()
    cot_run = dci_run / "ablation_cot"
    cot_run.mkdir(parents=True, exist_ok=True)

    protocol = {
        "design": "paired Table-2-style DCI ablation, CGME off",
        "cot_arm": "intuitive pathway Top-k already recorded in llm_calls.jsonl (stage=intuitive)",
        "dci_arm": "existing audit diagnosis / mapper top2 from the same run",
        "not_rerun": "no extra DCI LLM calls; CoT is not a new generation",
        "endpoints": {
            "da": "mapper option@1 typed_llm_disagreement_rag",
            "mcr": "prompt7 diagnostic_hit gemini-2.5-flash",
        },
        "paper_table2": {
            "cot_acc_base": 0.4025,
            "dci_acc_base": 0.5549,
            "dataset": "MedEinst (not this repo)",
        },
    }
    _write_json(cot_run / "protocol.json", protocol)
    override = write_cot_predictions(dci_run, cot_run)
    _write_json(cot_run / "override_stats.json", override)
    print(json.dumps({"wrote_cot_preds": str(cot_run), "override": override}, indent=2), flush=True)

    if not args.skip_score:
        print("[ablate] score CoT DA mapper@1 …", flush=True)
        cot_da = score_da(
            cot_run,
            parent,
            model=args.mapper_model,
            workers=args.mapper_workers,
        )
        print("[ablate] score CoT MCR Prompt-7 …", flush=True)
        cot_mcr = score_mcr(cot_run, parent, workers=args.judge_workers)
        metrics = cot_mcr.get("metrics") if isinstance(cot_mcr.get("metrics"), dict) else {}
        cot_scores = {
            "da": cot_da,
            "mcr": {
                "diagnostic_accuracy_single_trajectory": metrics.get(
                    "diagnostic_accuracy_single_trajectory"
                ),
                "n_cases": cot_mcr.get("n_cases_scored") or metrics.get("n_cases"),
                "n_hits": metrics.get("n_diagnostic_hits"),
                "judge_model": cot_mcr.get("judge_model_slug") or cot_mcr.get("judge_model"),
            },
        }
        _write_json(cot_run / "official_scores.json", cot_scores)
    else:
        cot_scores = json.loads((cot_run / "official_scores.json").read_text(encoding="utf-8"))

    dci_scores = json.loads((dci_run / "official_scores.json").read_text(encoding="utf-8"))
    da_pair = _paired(
        _load_da_hits(cot_run / "da" / "mapper" / "records.json"),
        _load_da_hits(dci_run / "da" / "mapper" / "records.json"),
    )
    mcr_pair = _paired(
        _load_mcr_hits(cot_run / "mcr" / "annotate" / "official_eval_llm" / "case_scores"),
        _load_mcr_hits(dci_run / "mcr" / "annotate" / "official_eval_llm" / "case_scores"),
    )
    compare = {
        "protocol": protocol,
        "override": override,
        "cot": cot_scores,
        "dci": {
            "da": dci_scores.get("da"),
            "mcr": dci_scores.get("mcr"),
        },
        "paired_da_mapper_top1": da_pair,
        "paired_mcr_prompt7": mcr_pair,
        "verdict": _verdict(da_pair, mcr_pair, override),
    }
    _write_json(dci_run / "dci_ablation.json", compare)
    print(json.dumps(compare["verdict"], indent=2), flush=True)
    print("wrote", dci_run / "dci_ablation.json", flush=True)


if __name__ == "__main__":
    main()
