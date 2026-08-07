#!/usr/bin/env python3
"""DiagnosisArena: RAG-free VignetteParser probe + freeze candidate.

Runs the *production* VignetteParser module (same prompt + RobustLLMClient
path as AgentClinicTreeController.parse_static_vignette) on a small case
subset. No tree/RAG/KB is loaded.

Default concurrency equals the case count (5). On success, writes a freeze
candidate + human adjudication sheet under the output directory.

Usage:
  PYTHONPATH=src:scripts/paper python3 -u \\
    scripts/paper/run_diagnosisarena_vignette_parser_probe.py \\
    --cases 3,4,5,7,11 --workers 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")

import diagnosisarena_adapter as da  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from agentclinic_tree_dx.prompting import load_module_prompt  # noqa: E402

DEFAULT_CASES_JSON = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "normalized_cases.json"
)
DEFAULT_OUT = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "vignette_parser_probe_v2"
)
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DIRECT_POST_OUTPUT_CAP = 4096
# Do NOT force-overwrite TREE_DX_DIRECT_POST_OUTPUT_CAP at import time.
# Importing this module from the staged pipeline previously clobbered the
# pipeline's 8192 budget back to 4096 and caused DiscriminatorAgentMatrix /
# L2 JSON truncations. Apply the probe floor only inside run_probe().


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    da._atomic_json(path, payload)


def _load_cases(
    cases_json: Path,
    case_ids: Sequence[str],
    limit: int,
) -> list[dict[str, Any]]:
    doc = json.loads(cases_json.read_text(encoding="utf-8"))
    cases = list(doc.get("cases") or ())
    wanted = {str(token).strip() for token in case_ids if str(token).strip()}
    if wanted:
        cases = [case for case in cases if str(case["id"]) in wanted]
        missing = sorted(wanted - {str(case["id"]) for case in cases})
        if missing:
            raise ValueError("unknown case ids: %s" % missing)
    if limit > 0:
        cases = cases[:limit]
    if not cases:
        raise ValueError("no cases selected")
    return cases


def _evidence_rows(parsed: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = (
        parsed.get("evidence_items")
        or parsed.get("evidence")
        or []
    )
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw if isinstance(raw, list) else ()):
        if not isinstance(item, Mapping):
            continue
        content = str(
            item.get("content")
            or item.get("fact")
            or item.get("description")
            or item.get("text")
            or ""
        ).strip()
        if not content:
            continue
        rows.append({
            "id": str(item.get("id") or ("E%d" % (index + 1))),
            "kind": str(item.get("kind") or "direct"),
            "content": content,
        })
    return rows


def _parse_one(
    *,
    case: Mapping[str, Any],
    llm: RobustLLMClient | None,
    prompt: str,
    model: str,
    call_timeout: float,
) -> dict[str, Any]:
    case_id = str(case["id"])
    started = time.monotonic()
    # Per-task client: shared RobustLLMClient is not guaranteed thread-safe
    # under high concurrency (19-way VP freeze expansion).
    client = llm or RobustLLMClient(
        model=model,
        call_timeout=call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    payload = {"raw_case": str(case["case_text"])}
    parsed = client.call_module("VignetteParser", prompt, payload)
    evidence = _evidence_rows(parsed if isinstance(parsed, Mapping) else {})
    options = list(parsed.get("options") or ()) if isinstance(parsed, Mapping) else []
    question = ""
    vignette = ""
    if isinstance(parsed, Mapping):
        question = str(
            parsed.get("question") or parsed.get("question_stem") or ""
        ).strip()
        vignette = str(
            parsed.get("vignette") or parsed.get("case_text") or ""
        ).strip()
    ok = bool(evidence) and bool(isinstance(parsed, Mapping) and parsed)
    return {
        "case_id": case_id,
        "status": "OK" if ok else "EMPTY_OR_PARSE_FAIL",
        "duration_seconds": round(time.monotonic() - started, 3),
        "n_evidence": len(evidence),
        "n_options": len(options) if isinstance(options, list) else 0,
        "question": question,
        "vignette": vignette,
        "evidence_items": evidence,
        "options": options,
        "raw_parsed_keys": sorted(parsed.keys()) if isinstance(parsed, Mapping) else [],
        "case_text_chars": len(str(case["case_text"])),
        "review_status": "pending_human",
        "review_notes": "",
    }


def _freeze_case_ok(row: Mapping[str, Any]) -> bool:
    return bool(row.get("evidence_items") or row.get("full_findings"))


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    # Raise (never lower) the shared direct-POST cap for this probe only.
    prior_cap = os.environ.get("TREE_DX_DIRECT_POST_OUTPUT_CAP")
    try:
        prior_val = int(prior_cap) if prior_cap else 0
    except ValueError:
        prior_val = 0
    os.environ["TREE_DX_DIRECT_POST_OUTPUT_CAP"] = str(
        max(prior_val, DIRECT_POST_OUTPUT_CAP)
    )

    cases = _load_cases(args.cases_json, args.cases.split(","), args.limit)
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    reused: list[dict[str, Any]] = []
    resume_path = getattr(args, "resume_freeze", None)
    if resume_path:
        resume_path = Path(resume_path).expanduser().resolve()
        if resume_path.is_file():
            existing = {
                str(row.get("case_id") or "").strip(): dict(row)
                for row in (
                    json.loads(resume_path.read_text(encoding="utf-8")).get("cases")
                    or ()
                )
                if str(row.get("case_id") or "").strip() and _freeze_case_ok(row)
            }
            keep = []
            for case in cases:
                cid = str(case["id"])
                frozen = existing.get(cid)
                if frozen is None:
                    keep.append(case)
                    continue
                evidence = list(frozen.get("evidence_items") or ())
                if not evidence and frozen.get("full_findings"):
                    evidence = [
                        {
                            "id": str(item.get("source_id") or item.get("id") or ""),
                            "kind": "direct",
                            "content": str(item.get("text") or ""),
                        }
                        for item in frozen["full_findings"]
                        if str(item.get("text") or "").strip()
                    ]
                reused.append({
                    "case_id": cid,
                    "status": "REUSED",
                    "duration_seconds": 0.0,
                    "n_evidence": len(evidence),
                    "n_options": len(frozen.get("options") or ()),
                    "question": frozen.get("question") or "",
                    "vignette": frozen.get("vignette") or "",
                    "evidence_items": evidence,
                    "options": frozen.get("options") or [],
                    "raw_parsed_keys": [],
                    "case_text_chars": len(str(case["case_text"])),
                    "review_status": "accepted_from_freeze",
                    "review_notes": "loaded from %s" % resume_path.name,
                })
            cases = keep
            print(
                "[vp-probe] resume-freeze: reused=%d remaining=%d path=%s"
                % (len(reused), len(cases), resume_path),
                flush=True,
            )

    workers = args.workers if args.workers > 0 else max(1, len(cases))
    workers = min(workers, max(1, len(cases))) if cases else 1
    prompt = load_module_prompt("VignetteParser")

    records: list[dict[str, Any]] = list(reused)
    started = time.monotonic()
    if not cases:
        print("[vp-probe] all cases already frozen; skip LLM", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _parse_one,
                case=case,
                llm=None,
                prompt=prompt,
                model=args.model,
                call_timeout=args.call_timeout,
            ): case
            for case in cases
        }
        done = 0
        for future in as_completed(futures):
            case = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001 — surface per-case
                row = {
                    "case_id": str(case["id"]),
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "n_evidence": 0,
                    "evidence_items": [],
                    "review_status": "pending_human",
                    "review_notes": "",
                }
            records.append(row)
            done += 1
            print(
                "[vp-probe] %d/%d %s %s n_ev=%s"
                % (
                    done,
                    len(cases),
                    row.get("case_id"),
                    row.get("status"),
                    row.get("n_evidence"),
                ),
                flush=True,
            )

    records.sort(key=lambda row: str(row.get("case_id") or ""))
    wall = time.monotonic() - started
    ok = sum(1 for row in records if row.get("status") in {"OK", "REUSED"})
    summary = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "asset_kind": "diagnosisarena_vignette_parser_probe_v1",
        "model": args.model,
        "direct_post_output_cap": DIRECT_POST_OUTPUT_CAP,
        "workers": workers,
        "n_cases": len(records),
        "n_ok": ok,
        "n_reused": sum(1 for row in records if row.get("status") == "REUSED"),
        "n_fail": len(records) - ok,
        "wall_seconds": round(wall, 3),
        "rag_used": False,
        "human_signed_off": False,
        "freeze_ready": ok == len(records) and len(records) > 0,
        "case_ids": [row["case_id"] for row in records],
        "mean_evidence": (
            round(
                sum(int(row.get("n_evidence") or 0) for row in records)
                / len(records),
                2,
            )
            if records else None
        ),
    }

    probe_payload = {"summary": summary, "cases": records}
    _atomic_json(out_dir / "probe_results.json", probe_payload)

    adjudication = {
        "asset_kind": "diagnosisarena_vignette_parser_adjudication_v1",
        "human_signed_off": False,
        "instructions": (
            "For each case, mark review_status as accept|revise|reject and "
            "optionally edit evidence_items before freeze. Set "
            "human_signed_off=true only after all cases are accepted."
        ),
        "rows": [
            {
                "case_id": row["case_id"],
                "status": row.get("status"),
                "n_evidence": row.get("n_evidence"),
                "evidence_preview": [
                    item.get("content")
                    for item in (row.get("evidence_items") or [])[:8]
                ],
                "review_status": "pending_human",
                "review_notes": "",
            }
            for row in records
        ],
    }
    _atomic_json(out_dir / "adjudication_sheet.json", adjudication)

    if summary["freeze_ready"]:
        signed = bool(getattr(args, "force_signed_off", False))
        frozen = {
            "asset_kind": (
                "diagnosisarena_vignette_parser_frozen_v3"
                if signed
                else "diagnosisarena_vignette_parser_frozen_candidate_v1"
            ),
            "schema_version": 3 if signed else 1,
            "created_at": _utc_now(),
            "model": args.model,
            "direct_post_output_cap": DIRECT_POST_OUTPUT_CAP,
            "human_signed_off": signed,
            "note": (
                "Pipeline stress freeze (force_signed_off=true); formal "
                "adjudication may still be pending."
                if signed
                else (
                    "Candidate freeze after successful probe. Promote to "
                    "vignette_parser_frozen_v1.json only after human accept."
                )
            ),
            "cases": [
                {
                    "case_id": row["case_id"],
                    "question": row.get("question"),
                    "vignette": row.get("vignette"),
                    "options": row.get("options") or [],
                    "evidence_items": row.get("evidence_items") or [],
                    "full_findings": [
                        {
                            "id": "F%d" % (index + 1),
                            "source_id": item["id"],
                            "text": item["content"],
                        }
                        for index, item in enumerate(row.get("evidence_items") or [])
                    ],
                    "freeze_source": (
                        "resume_freeze"
                        if row.get("status") == "REUSED"
                        else "probe_auto"
                    ),
                }
                for row in records
                if row.get("status") in {"OK", "REUSED"}
            ],
        }
        candidate_path = out_dir / "vignette_parser_frozen_candidate_v1.json"
        _atomic_json(candidate_path, frozen)
        if signed:
            signed_path = Path(
                getattr(args, "freeze_output", None)
                or (out_dir / "vignette_parser_frozen.json")
            ).expanduser().resolve()
            _atomic_json(signed_path, frozen)
            summary["signed_freeze"] = str(signed_path)
            summary["human_signed_off"] = True
            print(
                "[vp-probe] signed freeze → %s (n=%d)"
                % (signed_path, len(frozen["cases"])),
                flush=True,
            )
        if args.merge_with:
            merge_path = Path(args.merge_with).expanduser().resolve()
            merged = _merge_freeze(
                base_path=merge_path,
                new_cases=frozen["cases"],
                model=args.model,
                force_signed_off=args.force_signed_off,
            )
            merge_out = Path(
                args.merge_output or (out_dir / "vignette_parser_frozen_merged.json")
            ).expanduser().resolve()
            _atomic_json(merge_out, merged)
            summary["merged_freeze"] = str(merge_out)
            summary["merged_n_cases"] = len(merged.get("cases") or ())
            print(
                "[vp-probe] merged freeze → %s (n=%d)"
                % (merge_out, summary["merged_n_cases"]),
                flush=True,
            )

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def _merge_freeze(
    *,
    base_path: Path,
    new_cases: Sequence[Mapping[str, Any]],
    model: str,
    force_signed_off: bool,
) -> dict[str, Any]:
    """Merge probe cases onto an existing freeze (base cases win on id clash)."""
    base = json.loads(base_path.read_text(encoding="utf-8"))
    by_id: dict[str, dict[str, Any]] = {}
    for row in base.get("cases") or ():
        cid = str(row.get("case_id") or "").strip()
        if not cid:
            continue
        item = dict(row)
        item.setdefault("freeze_source", "base_signed")
        by_id[cid] = item
    base_ids = set(by_id)
    added = 0
    for row in new_cases:
        cid = str(row.get("case_id") or "").strip()
        if not cid or cid in by_id:
            continue
        item = dict(row)
        item.setdefault("freeze_source", "probe_auto")
        by_id[cid] = item
        added += 1
    cases = [by_id[cid] for cid in sorted(by_id, key=lambda x: (len(x), x))]
    signed = bool(base.get("human_signed_off")) and force_signed_off
    return {
        "asset_kind": "diagnosisarena_vignette_parser_frozen_v3",
        "schema_version": 3,
        "created_at": _utc_now(),
        "model": model,
        "direct_post_output_cap": DIRECT_POST_OUTPUT_CAP,
        "human_signed_off": signed,
        "base_freeze": str(base_path),
        "base_case_ids": sorted(base_ids, key=lambda x: (len(x), x)),
        "added_case_ids": sorted(
            {str(c["case_id"]) for c in new_cases} - base_ids,
            key=lambda x: (len(x), x),
        ),
        "n_added": added,
        "note": (
            "Merged freeze: keep signed-off base cases; append probe-OK "
            "cases. human_signed_off=%s (force_signed_off=%s). "
            "19 probe cases are stress-usable; formal adjudication pending."
            % (signed, force_signed_off)
        ),
        "cases": cases,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-json", type=Path, default=DEFAULT_CASES_JSON)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--cases",
        default="3,4,5,7,11",
        help="Comma-separated case ids (default: stress probe set)",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Default 0 → one worker per case (concurrency = n_cases)",
    )
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument(
        "--merge-with",
        type=Path,
        default=None,
        help="Existing freeze JSON to merge probe cases into",
    )
    parser.add_argument(
        "--merge-output",
        type=Path,
        default=None,
        help="Merged freeze output path (default: <out>/vignette_parser_frozen_merged.json)",
    )
    parser.add_argument(
        "--force-signed-off",
        action="store_true",
        help=(
            "Mark written freeze human_signed_off=true for pipeline reuse; "
            "also keeps that flag when merging onto a signed base freeze"
        ),
    )
    parser.add_argument(
        "--resume-freeze",
        type=Path,
        default=None,
        help="Skip LLM for case_ids already present with evidence in this freeze",
    )
    parser.add_argument(
        "--freeze-output",
        type=Path,
        default=None,
        help="With --force-signed-off, write signed freeze here "
        "(default: <out>/vignette_parser_frozen.json)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = run_probe(args)
    if not summary.get("freeze_ready"):
        return 1
    if args.merge_with and not summary.get("merged_freeze"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
