#!/usr/bin/env python3
"""Build eval_projection JSON from baseline predictions.jsonl + trace.jsonl.

pred_ddx = ordered_diagnoses (length list_k; OX default 5).
pred_interpretation / pred_reasoning_trace from per-dx reasoning_summary in traces.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402

DEFAULT_LIST_K = 5
PROTOCOL_TAG = "baseline_ordered_topk_v1"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _walk_collect_dx_rows(node: Any, out: list[Mapping[str, Any]]) -> None:
    if isinstance(node, Mapping):
        has_dx = any(k in node for k in ("diagnosis", "name", "disease"))
        if has_dx and (
            "reasoning_summary" in node
            or "reasoning" in node
            or "rationale" in node
        ):
            out.append(node)
        for value in node.values():
            if isinstance(value, (Mapping, list, tuple)):
                _walk_collect_dx_rows(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _walk_collect_dx_rows(item, out)


def extract_reasoning_by_label(trace: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """Map disease label → list of reasoning_summary strings from nested traces."""
    if not isinstance(trace, Mapping):
        return {}
    rows: list[Mapping[str, Any]] = []
    _walk_collect_dx_rows(trace, rows)
    out: dict[str, list[str]] = {}
    for row in rows:
        label = str(
            row.get("diagnosis") or row.get("name") or row.get("disease") or ""
        ).strip()
        if not label:
            continue
        reason = str(
            row.get("reasoning_summary")
            or row.get("reasoning")
            or row.get("rationale")
            or ""
        ).strip()
        if not reason:
            continue
        bucket = out.setdefault(label, [])
        if reason not in bucket:
            bucket.append(reason)
    # Also index case-insensitive aliases to first canonical label
    aliases: dict[str, str] = {}
    for lab in list(out):
        aliases[lab.casefold()] = lab
    remapped: dict[str, list[str]] = {}
    for lab, reasons in out.items():
        remapped[lab] = list(reasons)
    remapped["_aliases"] = aliases  # type: ignore[assignment]
    return remapped


def _lookup_reasons(
    by_label: Mapping[str, Any],
    label: str,
) -> list[str]:
    if not label:
        return []
    if label in by_label and label != "_aliases":
        return [str(x) for x in (by_label.get(label) or []) if str(x).strip()]
    aliases = by_label.get("_aliases") or {}
    if isinstance(aliases, Mapping):
        canon = aliases.get(label.casefold())
        if canon and canon in by_label:
            return [str(x) for x in (by_label.get(canon) or []) if str(x).strip()]
    # Fuzzy: casefold match among keys
    for key, reasons in by_label.items():
        if str(key) == "_aliases":
            continue
        if str(key).casefold() == label.casefold():
            return [str(x) for x in (reasons or []) if str(x).strip()]
    return []


def ordered_from_prediction(
    pred: Mapping[str, Any],
    *,
    list_k: int,
) -> list[str]:
    ordered = pred.get("ordered_diagnoses")
    if not isinstance(ordered, list) or not ordered:
        ordered = pred.get("top2_diagnoses") or []
    return [str(x).strip() for x in ordered if str(x).strip()][: max(1, int(list_k))]


def build_reasoning_trace(
    *,
    pred_ddx: Sequence[Mapping[str, Any]],
    pred_interpretation: Mapping[str, Sequence[str]],
) -> str:
    lines: list[str] = []
    for row in pred_ddx:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        lines.append("Diagnosis: %s" % label)
        reasons = list(pred_interpretation.get(label) or [])
        if reasons:
            for reason in reasons[:5]:
                lines.append("Evidence: %s" % reason)
        else:
            lines.append("Evidence: (none recorded)")
    return "\n".join(lines)


def projection_from_baseline_row(
    pred: Mapping[str, Any],
    trace: Mapping[str, Any] | None,
    *,
    dataset: str,
    list_k: int,
) -> dict[str, Any]:
    source_id = str(pred.get("source_id") or "").strip()
    if not source_id:
        case_id = str(pred.get("case_id") or "")
        if "__" in case_id:
            source_id = case_id.split("__", 1)[1].lstrip("0") or case_id.split("__", 1)[1]
            if source_id == "":
                source_id = "0"
        else:
            source_id = case_id
    labels = ordered_from_prediction(pred, list_k=list_k)
    # Keep only non-empty for pred_ddx (matching ignores empties)
    pred_ddx = [
        {"id": "B%d" % (i + 1), "label": lab, "rank": i + 1}
        for i, lab in enumerate(labels)
        if lab
    ]
    reason_map = extract_reasoning_by_label(trace)
    # Drop internal alias map from interpretation output
    pred_interp: dict[str, list[str]] = {}
    evidence_used = False
    for row in pred_ddx:
        lab = str(row["label"])
        reasons = _lookup_reasons(reason_map, lab)
        if reasons:
            evidence_used = True
        pred_interp[lab] = reasons[:5]

    trace_text = build_reasoning_trace(
        pred_ddx=pred_ddx,
        pred_interpretation=pred_interp,
    )
    pred_diagnosis = str(pred_ddx[0]["label"]) if pred_ddx else ""
    return {
        "case_id": source_id,
        "schema_version": 1,
        "dataset": dataset,
        "protocol_tags": [PROTOCOL_TAG, str(dataset)],
        "pred_ddx": pred_ddx,
        "pred_interpretation": pred_interp,
        "pred_diagnosis": pred_diagnosis,
        "pred_reasoning_trace": trace_text,
        "n_pred_nonempty": len(pred_ddx),
        "sources": {
            "ranking": "baseline_ordered_topk",
            "list_k": int(list_k),
            "evidence": (
                ["trace.reasoning_summary"] if evidence_used else []
            ),
            "arm": pred.get("arm"),
            "replicate": pred.get("replicate"),
            "baseline_case_id": pred.get("case_id"),
        },
    }


def resolve_list_k(pred_dir: Path, override: int = 0) -> int:
    if override and int(override) > 0:
        return int(override)
    manifest = pred_dir / "manifest.json"
    if manifest.is_file():
        doc = _read_json(manifest)
        if isinstance(doc, Mapping) and doc.get("list_k"):
            return int(doc["list_k"])
    # Infer from first prediction
    preds = _load_jsonl(pred_dir / "predictions.jsonl")
    if preds:
        row = preds[0]
        if row.get("list_k"):
            return int(row["list_k"])
        ordered = row.get("ordered_diagnoses") or row.get("top2_diagnoses") or []
        if isinstance(ordered, list) and ordered:
            return max(2, len(ordered))
    return DEFAULT_LIST_K


def build_baseline_eval_projections(
    pred_dir: Path,
    *,
    dataset: str = "open_xddx",
    list_k: int = 0,
    case_ids: Sequence[str] = (),
    resume: bool = False,
    out_subdir: str = "eval_projection",
) -> dict[str, Any]:
    pred_dir = Path(pred_dir)
    k = resolve_list_k(pred_dir, list_k)
    ds = bc.normalize_dataset(dataset) if dataset else "open_xddx"
    if ds == "diagnosisarena":
        # Projection still works; gold loaders are OX/MCR only.
        ds = "open_xddx"

    preds = _load_jsonl(pred_dir / "predictions.jsonl")
    traces = _load_jsonl(pred_dir / "trace.jsonl")
    trace_by_case = {
        str(row.get("case_id") or ""): row.get("trace")
        for row in traces
        if row.get("case_id")
    }

    wanted = {str(x) for x in case_ids if str(x).strip()}
    out_dir = pred_dir / "annotate" / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    for pred in preds:
        source_id = str(pred.get("source_id") or "").strip()
        if not source_id:
            continue
        if wanted and source_id not in wanted and str(pred.get("case_id")) not in wanted:
            continue
        out_path = out_dir / ("%s.json" % source_id)
        if resume and out_path.is_file():
            skipped += 1
            continue
        case_key = str(pred.get("case_id") or "")
        trace = trace_by_case.get(case_key)
        if not isinstance(trace, Mapping):
            trace = {}
        doc = projection_from_baseline_row(
            pred,
            trace,
            dataset=ds,
            list_k=k,
        )
        _write_json(out_path, doc)
        written += 1

    summary = {
        "pred_dir": str(pred_dir.resolve()),
        "dataset": ds,
        "list_k": k,
        "protocol": PROTOCOL_TAG,
        "n_written": written,
        "n_skipped_resume": skipped,
        "out_dir": str(out_dir.resolve()),
    }
    _write_json(pred_dir / "annotate" / "baseline_projection_build.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred-dir", type=Path, required=True)
    ap.add_argument(
        "--dataset",
        default="open_xddx",
        choices=("open_xddx", "medcasereasoning", "rarearena", "ox", "mcr", "ra"),
    )
    ap.add_argument("--list-k", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out-subdir", default="eval_projection")
    args = ap.parse_args()
    ds = args.dataset
    if ds == "ox":
        ds = "open_xddx"
    elif ds == "mcr":
        ds = "medcasereasoning"
    elif ds == "ra":
        ds = "rarearena"
    summary = build_baseline_eval_projections(
        args.pred_dir,
        dataset=ds,
        list_k=int(args.list_k or 0),
        case_ids=list(args.case_id or []),
        resume=bool(args.resume),
        out_subdir=str(args.out_subdir or "eval_projection"),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
