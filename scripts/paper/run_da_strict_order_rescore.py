#!/usr/bin/env python3
"""DA strict-total-order mapper rescore (no option_rank ties).

For every DiagnosisArena arm (M00 paper rematch @0.71, live M00, C2/C3
ablations, baselines), re-emit projections where ``option_rank`` is a unique
permutation of 1..n.

Protocol
--------
* Non-tied cases: keep the existing projection ranks (identity).
* Tied cases: call ``L2OptionStrictTotalOrder`` (new module ⇒ old typed/critic
  caches are never reused for this step). Shared strict-order cache is used,
  but a hit that itself contains ties is rejected and recomputed.
* M00 paper (0.71): rebuild ``compat_parallel`` rematch from pre-compat
  projections (``at1_c1`` cache), then apply the same strict-order step.
* Outputs land under ``runs/paper_v1/da_strict_order_v1/`` and never overwrite
  the original mapper directories.

Usage
-----
  PYTHONPATH=src:scripts:scripts/paper \\
    python scripts/paper/run_da_strict_order_rescore.py --workers 12
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    _rank_and_expand,
    enforce_strict_total_order,
    has_option_rank_ties,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
import run_at1_calibration_smoke as smoke  # noqa: E402
import merge_calib_compat as compat  # noqa: E402

DA = ROOT / "logs/diagnosisarena_d2_m01_v1"
RUNS = ROOT / "runs/paper_v1"
OUT_ROOT = RUNS / "da_strict_order_v1"
PROMPT_PATH = (
    ROOT / "src/agentclinic_tree_dx/prompts/answer_option_strict_total_order.txt"
)
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


class TieRejectCachedLLM:
    """Disk cache that refuses hits whose stored value encodes a tied ranking.

    Used only for ``L2OptionStrictTotalOrder``. Old typed/critic mapper caches
    are never consulted by this wrapper.
    """

    def __init__(self, llm: Any, cache_path: Path, model: str) -> None:
        self.llm = llm
        self.cache_path = cache_path
        self.model = model
        self.temperature = float(getattr(llm, "temperature", 0.0) or 0.0)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}
        self.hits = 0
        self.misses = 0
        self.rejected_tie_hits = 0
        self._lock = threading.Lock()

    def call_module(
        self, module: str, prompt: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self.call(module, prompt, payload)

    def call(
        self, module: str, prompt: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        key = bfs_eval.stable_hash({
            "model": self.model,
            "temperature": self.temperature,
            "module": module,
            "prompt_sha256": __import__("hashlib")
            .sha256(prompt.encode())
            .hexdigest(),
            "payload": payload,
        })
        with self._lock:
            if key in self.cache:
                value = self.cache[key]
                order = [str(x).upper() for x in (value.get("order") or ())]
                # Reject degenerate cache entries (duplicates / incomplete).
                if order and len(order) == len(set(order)):
                    self.hits += 1
                    return dict(value)
                self.rejected_tie_hits += 1
                del self.cache[key]
        result = self.llm.call_module(module, prompt, dict(payload))
        if not isinstance(result, Mapping):
            raise ValueError("%s returned non-object JSON" % module)
        with self._lock:
            self.cache[key] = dict(result)
            self.misses += 1
            _atomic_json(self.cache_path, self.cache)
            return dict(result)


def _score(gold_letter: str, option_maps: Mapping[str, Any]) -> dict[str, Any]:
    gold = str(gold_letter or "").upper()
    row = option_maps.get(gold) or {}
    rank = row.get("option_rank")
    matched = bool(
        row.get("best_rank") is not None
        or row.get("matched")
        or (
            (row.get("matched_leaf_ids") or row.get("clone_leaf_ids"))
            and str(row.get("relation_type") or "") not in {"", "unrelated", "unknown"}
        )
    )
    if (not matched) or rank is None:
        return {
            "option_top1": False,
            "option_top2": False,
            "option_rr": 0.0,
            "option_rank": int(rank) if rank is not None else None,
            "gold_matched": matched,
        }
    rank_i = int(rank)
    return {
        "option_top1": rank_i <= 1,
        "option_top2": rank_i <= 2,
        "option_rr": 1.0 / rank_i,
        "option_rank": rank_i,
        "gold_matched": matched,
    }


def _leaves_from_projection(proj: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Best-effort leaf list for the strict-order prompt."""
    leaves: list[dict[str, Any]] = []
    seen: set[str] = set()
    for letter, row in sorted((proj.get("option_maps") or {}).items()):
        for lid in list(row.get("clone_leaf_ids") or row.get("matched_leaf_ids") or ()):
            sid = str(lid)
            if not sid or sid in seen:
                continue
            seen.add(sid)
            leaves.append({
                "leaf_id": sid,
                "leaf_label": sid,
                "parent_id": "",
                "parent_label": "",
                "joint_rank": row.get("best_rank"),
                "posterior": float(row.get("posterior") or 0.0),
            })
    # densify joint ranks if missing
    ranked = [r for r in leaves if r.get("joint_rank") is not None]
    ranked.sort(key=lambda r: int(r["joint_rank"]))
    for index, row in enumerate(ranked, start=1):
        row["joint_rank"] = index
    return leaves


def _options_from_row(row: Mapping[str, Any]) -> dict[str, str]:
    proj = row.get("projection") or {}
    om = proj.get("option_maps") or {}
    # Prefer explicit option texts stored on maps / row.
    options: dict[str, str] = {}
    for letter, mapped in om.items():
        text = (
            mapped.get("option_text")
            or mapped.get("text")
            or ""
        )
        options[str(letter).upper()] = str(text)
    # Fall back to audit deterministic keys if texts missing.
    det = ((proj.get("audit") or {}).get("deterministic") or {})
    for letter, mapped in det.items():
        key = str(letter).upper()
        if not options.get(key):
            options[key] = str(
                mapped.get("option_text") or mapped.get("text") or key
            )
    if options and all(options.values()):
        return options
    return options


def _vignette_from_row(row: Mapping[str, Any], case: Optional[Mapping[str, Any]]) -> tuple[str, str]:
    if case:
        text = str(case.get("case_text") or case.get("vignette") or "")
        if "\nOptions:" in text:
            body = text.split("\nOptions:", 1)[0].strip()
        else:
            body = text.strip()
        return body, "What is the most likely diagnosis?"
    return str(row.get("vignette") or ""), "What is the most likely diagnosis?"


def apply_strict_to_projection(
    *,
    row: Mapping[str, Any],
    llm: Any,
    prompt: str,
    vignette: str,
    question: str,
    options: Mapping[str, str],
    leaves: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    proj = dict(row.get("projection") or {})
    om = proj.get("option_maps") or {}
    if not om:
        raise ValueError("missing option_maps")
    # Fill option texts into maps for the LLM payload helper.
    options_u = {str(k).upper(): str(v) for k, v in options.items()}
    had_ties = has_option_rank_ties(om)
    new_om, order, meta = enforce_strict_total_order(
        option_maps=om,
        llm=llm if had_ties else None,
        prompt=prompt,
        vignette=vignette,
        question=question,
        options=options_u,
        leaves=leaves,
        case_id=str(row.get("case_id") or ""),
        force_llm=False,
    )
    # If ties existed but LLM was skipped somehow, force competition.
    if has_option_rank_ties(new_om):
        new_om, order, meta = enforce_strict_total_order(
            option_maps=om,
            llm=None,
            prompt="",
            vignette=vignette,
            question=question,
            options=options_u,
            leaves=leaves,
            case_id=str(row.get("case_id") or ""),
            force_llm=True,
        )
        meta["forced_competition_after_residual_ties"] = True

    gold = str(row.get("gold_letter") or "").upper()
    metrics = _score(gold, new_om)
    audit = dict(proj.get("audit") or {})
    audit["strict_total_order"] = meta
    new_proj = {
        **proj,
        "option_maps": new_om,
        "option_order": order,
        "mode": str(proj.get("mode") or "") + "+strict_total_order",
        "audit": audit,
    }
    out = {
        **{k: v for k, v in row.items() if k != "projection"},
        "projection": new_proj,
        **metrics,
        "strict_total_order": meta,
        "had_ties_before": had_ties,
    }
    return out


def summarize(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(records) or 1
    n_ok = sum(1 for r in records if r.get("status", "OK") == "OK")
    return {
        "n_cases": len(records),
        "n_ok": n_ok,
        "option_top1": round(
            sum(1 for r in records if r.get("option_top1")) / n, 4
        ),
        "option_top2": round(
            sum(1 for r in records if r.get("option_top2")) / n, 4
        ),
        "mean_option_rr": round(
            sum(float(r.get("option_rr") or 0.0) for r in records) / n, 4
        ),
        "n_had_ties_before": sum(1 for r in records if r.get("had_ties_before")),
        "n_llm_strict": sum(
            1
            for r in records
            if ((r.get("strict_total_order") or {}).get("method") == "llm_strict_total_order")
        ),
        "n_residual_ties": sum(
            1
            for r in records
            if has_option_rank_ties((r.get("projection") or {}).get("option_maps") or {})
        ),
    }


# ---------------------------------------------------------------------------
# Arm registry
# ---------------------------------------------------------------------------

def _proj_arm(
    key: str,
    label: str,
    proj_dirs: Sequence[Path],
    *,
    case_json_dirs: Sequence[Path] | None = None,
    kind: str = "projections",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": kind,
        "proj_dirs": [Path(p) for p in proj_dirs],
        "case_json_dirs": [Path(p) for p in (case_json_dirs or [])],
    }


def _records_arm(key: str, label: str, records_path: Path) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": "records",
        "records_path": Path(records_path),
    }


def registry() -> list[dict[str, Any]]:
    arms = [
        _proj_arm(
            "M00_paper_rematch_071",
            "M00 paper rematch (compat_parallel → 0.71 source)",
            [],
            kind="m00_rematch",
        ),
        _proj_arm(
            "M00_live_compat_b12",
            "M00 native compat+b12 live",
            [
                DA / "pilot24_compat_b12_live_v1/mapper/projections",
                DA / "remain76_compat_b12_live_v1/mapper/projections",
            ],
            case_json_dirs=[
                DA / "pilot24_compat_b12_live_v1",
                DA / "remain76_compat_b12_live_v1",
                DA / "downstream_top2_w12_v1",
                DA / "pipeline_remaining76_v1/annotate",
            ],
        ),
        _proj_arm(
            "M00_precompat",
            "M00 pre-compat native mapper",
            [
                DA / "downstream_top2_w12_v1/mapper/projections",
                DA / "pipeline_remaining76_v1/annotate/mapper/projections",
            ],
            case_json_dirs=[
                DA / "downstream_top2_w12_v1",
                DA / "pipeline_remaining76_v1/annotate",
            ],
        ),
        _proj_arm(
            "AB01", "AB01 fixed_icd",
            [DA / "c3_ab01_v1/annotate/mapper/projections"],
            case_json_dirs=[DA / "c3_ab01_v1"],
        ),
        _proj_arm(
            "AB02", "AB02 flat (exploratory)",
            [DA / "c3_ab02_v1/annotate/mapper/projections"],
            case_json_dirs=[DA / "c3_ab02_v1"],
        ),
        _proj_arm(
            "AB03", "AB03 random",
            [DA / "c3_ab03_v1/annotate/mapper/projections"],
            case_json_dirs=[DA / "c3_ab03_v1"],
        ),
        _proj_arm(
            "AB21", "AB21 contrastive",
            [DA / "c2_ab21_v1/annotate/mapper/projections"],
            case_json_dirs=[DA / "c2_ab21_v1"],
        ),
        _proj_arm(
            "AB22", "AB22 no-P5",
            [DA / "c2_ab22_v1/annotate/mapper/projections"],
            case_json_dirs=[DA / "c2_ab22_v1"],
        ),
    ]
    # Baselines: prefer authoritative roots used by the DA summary.
    baseline_specs = [
        ("B00", RUNS / "diagnosisarena_remaining_v1/B00-direct-cot/replicate_01"),
        ("B01", RUNS / "diagnosisarena_rag_smoke_live/B01-cot-rag/replicate_01"),
        ("B02-matched-rerank", RUNS / "diagnosisarena_fixed_v1/B02-flat-matched-rerank/replicate_01"),
        ("B02-compute-matched", RUNS / "diagnosisarena_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01"),
        ("B02-cm-sc10", RUNS / "diagnosisarena_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01"),
        ("B03", RUNS / "diagnosisarena_remaining_v1/B03-flat-beam/replicate_01"),
        ("B04", RUNS / "diagnosisarena_fixed_v1/B04-dual-inf/replicate_01"),
        ("B05", RUNS / "diagnosisarena_fixed_v1/B05-mdagents/replicate_01"),
        ("B06", RUNS / "diagnosisarena_fixed_v1/B06-mac-single-vendor/replicate_01"),
        ("B07", RUNS / "diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01"),
        ("B11a", RUNS / "diagnosisarena_b11a_smoke/B11a-official-diagnosisgpt/replicate_01"),
        ("B11b", RUNS / "diagnosisarena_rag_smoke_live/B11b-cod-prompt-shared-kb/replicate_01"),
        ("B12", RUNS / "diagnosisarena_remaining_v1/B12-sc-cot-5/replicate_01"),
        ("B13", RUNS / "diagnosisarena_remaining_v1/B13-self-refine-1/replicate_01"),
        ("B15", RUNS / "diagnosisarena_fixed_v1/B15-medprompt-style/replicate_01"),
        ("B16", RUNS / "diagnosisarena_fixed_v1/B16-medrag-kg/replicate_01"),
        ("B17", RUNS / "diagnosisarena_imedrag_v1/B17-imedrag/replicate_01"),
    ]
    for key, base in baseline_specs:
        rec = base / "mapper/records.json"
        if rec.is_file():
            arms.append(_records_arm(key, key, rec))
    return arms


def _load_cases(dirs: Sequence[Path]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for base in dirs:
        for name in ("normalized_cases.json",):
            path = base / name
            if not path.is_file():
                # also try parent annotate / arm root
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            for case in doc.get("cases") or []:
                by_id[str(case.get("id"))] = case
        # nested
        for path in base.rglob("normalized_cases.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            for case in doc.get("cases") or []:
                by_id.setdefault(str(case.get("id")), case)
    # global fallback
    g = ROOT / "data/benchmarks/diagnosisarena/normalized_cases.json"
    if g.is_file():
        doc = json.loads(g.read_text(encoding="utf-8"))
        for case in doc.get("cases") or []:
            by_id.setdefault(str(case.get("id")), case)
    return by_id


def _options_from_case(case: Mapping[str, Any]) -> dict[str, str]:
    opts = case.get("source_options") or case.get("options") or {}
    if isinstance(opts, Mapping) and opts:
        return {str(k).upper(): str(v) for k, v in opts.items()}
    # parse from case_text
    text = str(case.get("case_text") or "")
    out: dict[str, str] = {}
    marker = None
    for cand in ("\nOptions:", "\nOPTIONS:", "Options:"):
        if cand in text:
            marker = cand
            break
    if marker is None:
        return out
    block = text.split(marker, 1)[1]
    for line in block.splitlines():
        line = line.strip()
        if len(line) >= 3 and line[0].isalpha() and line[1] in {".", ")"}:
            out[line[0].upper()] = line[2:].strip()
    return out


def process_projection_arm(
    arm: Mapping[str, Any],
    *,
    llm: Any,
    prompt: str,
    workers: int,
    resume: bool,
    max_cases: int | None = None,
) -> dict[str, Any]:
    out_dir = OUT_ROOT / "arms" / str(arm["key"])
    proj_out = out_dir / "projections"
    proj_out.mkdir(parents=True, exist_ok=True)
    cases = _load_cases(arm.get("case_json_dirs") or [])
    jobs = []
    for d in arm["proj_dirs"]:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            jobs.append(path)
    if max_cases is not None:
        jobs = jobs[: int(max_cases)]

    def _one(path: Path) -> dict[str, Any]:
        cid = path.stem
        dest = proj_out / f"{cid}.json"
        if resume and dest.is_file():
            existing = json.loads(dest.read_text(encoding="utf-8"))
            if existing.get("status") == "OK" and not has_option_rank_ties(
                (existing.get("projection") or {}).get("option_maps") or {}
            ):
                return existing
        row = json.loads(path.read_text(encoding="utf-8"))
        case = cases.get(str(row.get("case_id") or cid)) or {}
        vignette, question = _vignette_from_row(row, case)
        options = _options_from_case(case) or _options_from_row(row)
        # Prefer option texts from source_options over empty placeholders.
        leaves = _leaves_from_case_result(arm, cid, row)
        try:
            out = apply_strict_to_projection(
                row=row,
                llm=llm,
                prompt=prompt,
                vignette=vignette,
                question=question,
                options=options,
                leaves=leaves,
            )
            out["status"] = "OK"
        except Exception as exc:  # noqa: BLE001
            out = {
                **row,
                "status": "ERROR",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "option_top1": False,
                "option_top2": False,
                "option_rr": 0.0,
            }
        _atomic_json(dest, out)
        return out

    records = _map_parallel(jobs, _one, workers=workers, label=str(arm["key"]))
    summary = summarize(records)
    summary.update({
        "arm": arm["key"],
        "label": arm["label"],
        "kind": "projections",
        "created_at": _utc(),
    })
    _atomic_json(out_dir / "summary.json", summary)
    _atomic_json(out_dir / "records.json", {"records": records, "summary": summary})
    return summary


def _leaves_from_case_result(
    arm: Mapping[str, Any], case_id: str, row: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Prefer joint ranking labels from case_results when available."""
    for base in arm.get("case_json_dirs") or []:
        for rel in (
            Path("annotate/case_results") / f"{case_id}.json",
            Path("case_results") / f"{case_id}.json",
        ):
            path = Path(base) / rel
            if not path.is_file():
                # also search one level down
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            labels = list((doc.get("l2") or {}).get("final_ranking_labels") or ())
            ids = list((doc.get("l2") or {}).get("final_ranking_ids") or ())
            if not labels and not ids:
                continue
            leaves = []
            for index, lid in enumerate(ids or [r.get("id") for r in labels], start=1):
                lab = next(
                    (r for r in labels if str(r.get("id")) == str(lid)), {}
                )
                leaves.append({
                    "leaf_id": str(lid),
                    "leaf_label": str(lab.get("label") or lid),
                    "parent_id": str(lab.get("parent") or ""),
                    "parent_label": "",
                    "joint_rank": index,
                    "posterior": float(lab.get("posterior") or 0.0),
                })
            if leaves:
                return leaves
    return _leaves_from_projection(row.get("projection") or {})


def process_records_arm(
    arm: Mapping[str, Any],
    *,
    llm: Any,
    prompt: str,
    workers: int,
    resume: bool,
    max_cases: int | None = None,
) -> dict[str, Any]:
    out_dir = OUT_ROOT / "arms" / str(arm["key"])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "records.json"
    if resume and dest.is_file() and max_cases is None:
        existing = json.loads(dest.read_text(encoding="utf-8"))
        if (existing.get("summary") or {}).get("n_residual_ties") == 0:
            return existing["summary"]

    src = json.loads(Path(arm["records_path"]).read_text(encoding="utf-8"))
    rows = list(src.get("records") or [])
    if max_cases is not None:
        rows = rows[: int(max_cases)]
    # Load DA cases for vignette/options by source_id / case_id
    cases = _load_cases([ROOT / "data/benchmarks/diagnosisarena"])
    # also try parent replicate normalized if any
    cases.update(_load_cases([Path(arm["records_path"]).parents[1]]))

    def _one(row: dict[str, Any]) -> dict[str, Any]:
        cid = str(row.get("source_id") or row.get("case_id") or "")
        case = cases.get(cid) or {}
        # baseline case_id is often diagnosisarena__000007
        if not case:
            for key, val in cases.items():
                if str(val.get("id")) == cid or str(val.get("source_id")) == cid:
                    case = val
                    break
        vignette, question = _vignette_from_row(row, case)
        options = _options_from_case(case)
        if not options:
            # recover from projection option_maps keys with empty text — use letters only
            om = (row.get("projection") or {}).get("option_maps") or {}
            options = {str(k).upper(): str(k).upper() for k in om}
        # Build leaves from top2
        top2 = list(row.get("top2_diagnoses") or ())
        leaves = []
        for index, label in enumerate(top2, start=1):
            leaves.append({
                "leaf_id": f"pred_{index}",
                "leaf_label": str(label),
                "parent_id": "",
                "parent_label": "",
                "joint_rank": index,
                "posterior": float(max(0.0, 2.0 - index)),
            })
        if not leaves:
            leaves = _leaves_from_projection(row.get("projection") or {})
        try:
            out = apply_strict_to_projection(
                row=row,
                llm=llm,
                prompt=prompt,
                vignette=vignette,
                question=question,
                options=options,
                leaves=leaves,
            )
            out["status"] = "OK"
        except Exception as exc:  # noqa: BLE001
            out = {
                **row,
                "status": "ERROR",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "option_top1": False,
                "option_top2": False,
                "option_rr": 0.0,
            }
        return out

    records = _map_parallel(rows, _one, workers=workers, label=str(arm["key"]))
    summary = summarize(records)
    summary.update({
        "arm": arm["key"],
        "label": arm["label"],
        "kind": "records",
        "source": str(arm["records_path"]),
        "created_at": _utc(),
    })
    _atomic_json(dest, {"records": records, "summary": summary})
    _atomic_json(out_dir / "summary.json", summary)
    return summary


def process_m00_rematch(
    *,
    llm: Any,
    prompt: str,
    workers: int,
    resume: bool,
    model: str,
    max_cases: int | None = None,
) -> dict[str, Any]:
    """Rebuild paper M00 (compat_parallel rematch) then strict-order."""
    out_dir = OUT_ROOT / "arms" / "M00_paper_rematch_071"
    proj_out = out_dir / "projections"
    proj_out.mkdir(parents=True, exist_ok=True)

    packs = smoke.load_cohort("all100")
    if max_cases is not None:
        packs = packs[: int(max_cases)]
    # Reuse at1_c1 cache for compat middleware.
    compat_cache_path = DA / "at1_c1_v1/cache/compat_parallel_llm_cache.json"
    raw_llm = RobustLLMClient(
        model=model, call_timeout=240, max_retries=5, timeout_retry_cap=2,
        temperature=0.0,
    )
    compat_cached = bfs_eval.CachedLLM(raw_llm, compat_cache_path, model)

    def _one(pack: dict[str, Any]) -> dict[str, Any]:
        cid = str(pack["case_id"])
        dest = proj_out / f"{cid}.json"
        if resume and dest.is_file():
            existing = json.loads(dest.read_text(encoding="utf-8"))
            if existing.get("status") == "OK" and not has_option_rank_ties(
                (existing.get("projection") or {}).get("option_maps") or {}
            ):
                return existing
        case = pack["case"]
        mapper = pack["mapper"]
        labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
        om = (mapper.get("projection") or {}).get("option_maps") or {}
        vignette = smoke._vignette(pack["meta"], case)
        findings = pack["findings"]
        routed = compat.run_compat_parallel(
            case=case,
            ranking_labels=labels,
            vignette=vignette,
            findings=findings,
            option_maps=om,
            gold_leaf_ids=[],
            cache=compat_cached,
            dry_run=False,
            k=5,
            alpha=1.0,
            beta=1.0,
            gamma=0.5,
            tau=0.5,
        )
        work_labels = list(routed.get("ranking_labels") or labels)
        ordered_ids = list(routed.get("ordered_ids") or ())
        maps = routed.get("option_maps") or om
        # Rebuild dense ranks under rematched leaf order (same as rematch_option_metrics).
        label_by_id = {
            str(r.get("id")): str(r.get("label") or "")
            for r in work_labels if r.get("id")
        }
        parent_by_id = {
            str(r.get("id")): str(r.get("parent") or "")
            for r in work_labels if r.get("id")
        }
        all_ids = list(ordered_ids)
        for _letter, mapped in maps.items():
            for lid in (mapped.get("matched_leaf_ids") or mapped.get("clone_leaf_ids") or ()):
                s = str(lid)
                if s not in all_ids:
                    all_ids.append(s)
        rank_pos = {lid: i for i, lid in enumerate(ordered_ids, start=1)}
        leaves = []
        for lid in all_ids:
            leaves.append({
                "leaf_id": lid,
                "leaf_label": label_by_id.get(lid, lid),
                "parent_id": parent_by_id.get(lid, ""),
                "parent_label": "",
                "joint_rank": rank_pos.get(lid),
                "posterior": 0.0,
            })
        mappings = {}
        for k, v in maps.items():
            expanded_ids = list(v.get("clone_leaf_ids") or v.get("matched_leaf_ids") or ())
            mappings[str(k).upper()] = {
                "matched_leaf_ids": expanded_ids,
                "relation_type": v.get("relation_type"),
                "confidence_score": v.get("confidence_score"),
                "matched": bool(expanded_ids),
            }
        expanded, _ordered_letters = _rank_and_expand(
            mappings=mappings, leaves=leaves, clone_groups=[[lid] for lid in all_ids],
        )
        # Carry forward richer fields from rematched maps when present.
        for letter, row in expanded.items():
            src = maps.get(letter) or maps.get(letter.lower()) or {}
            for key in ("confidence", "confidence_score", "rationale", "source", "support_score"):
                if key in src and key not in row:
                    row[key] = src[key]
        rematch_row = {
            **mapper,
            "case_id": cid,
            "projection": {
                **(mapper.get("projection") or {}),
                "option_maps": expanded,
                "option_order": _ordered_letters,
                "mode": "compat_parallel_rematch",
            },
            "gold_letter": mapper.get("gold_letter"),
        }
        options = smoke._options_for_pack(pack)
        try:
            out = apply_strict_to_projection(
                row=rematch_row,
                llm=llm,
                prompt=prompt,
                vignette=vignette,
                question="What is the most likely diagnosis?",
                options=options,
                leaves=leaves,
            )
            out["status"] = "OK"
            out["rematch_branch"] = (routed.get("branch") or routed.get("mode"))
        except Exception as exc:  # noqa: BLE001
            out = {
                **rematch_row,
                "status": "ERROR",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "option_top1": False,
                "option_top2": False,
                "option_rr": 0.0,
            }
        _atomic_json(dest, out)
        return out

    records = _map_parallel(packs, _one, workers=workers, label="M00_paper_rematch_071")
    summary = summarize(records)
    summary.update({
        "arm": "M00_paper_rematch_071",
        "label": "M00 paper rematch (compat_parallel) + strict total order",
        "kind": "m00_rematch",
        "anchor_note": (
            "Source is the same pre-compat projections rematched with "
            "compat_parallel that produced opt1=0.71 in at1_c1_v1 TSV"
        ),
        "created_at": _utc(),
    })
    _atomic_json(out_dir / "summary.json", summary)
    _atomic_json(out_dir / "records.json", {"records": records, "summary": summary})
    return summary


def _map_parallel(items, fn, *, workers: int, label: str) -> list[dict[str, Any]]:
    if not items:
        return []
    results: list[Optional[dict[str, Any]]] = [None] * len(items)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn, item): index for index, item in enumerate(items)}
        for fut in as_completed(futures):
            index = futures[fut]
            results[index] = fut.result()
            done += 1
            if done % 10 == 0 or done == len(items):
                print(f"[{label}] {done}/{len(items)}", flush=True)
    return [r for r in results if r is not None]


def write_aggregate(summaries: Sequence[Mapping[str, Any]]) -> None:
    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "protocol": {
            "endpoint": "strict_total_order option@1/@2",
            "tie_policy": (
                "L2OptionStrictTotalOrder LLM permutation when prior dense "
                "ranks tied; identity otherwise; competition fallback on LLM failure"
            ),
            "cache": (
                "Shared cache for L2OptionStrictTotalOrder only; entries whose "
                "order is not a unique permutation are rejected (treated as miss). "
                "Typed/critic mapper caches are not reused for the strict-order step."
            ),
            "m00_paper": "compat_parallel rematch of pre-compat projections (0.71 source)",
        },
        "arms": list(summaries),
    }
    _atomic_json(OUT_ROOT / "summary.json", doc)

    lines = [
        "# DA 禁止平局 mapper 重评（strict total order）",
        "",
        f"- 生成时间: `{doc['created_at']}`",
        f"- 输出根目录: `{OUT_ROOT}`",
        "- 协议: 有并列 → `L2OptionStrictTotalOrder` 强制唯一全序；无并列 → 保留原秩",
        "- 缓存: 仅严格全序模块使用共享缓存；**含重复 order 的缓存条目禁止 hit**",
        "- M00 论文版: 以 pre-compat → `compat_parallel` rematch（原 0.71 来源）为准后再破并列",
        "",
        "| 臂 | n | option@1 | option@2 | RR | 原并列例 | LLM破并列 | 残留并列 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            "| {arm} | {n} | {a1:.3f} | {a2:.3f} | {rr:.3f} | {t} | {llm} | {res} |".format(
                arm=s.get("arm"),
                n=s.get("n_cases"),
                a1=float(s.get("option_top1") or 0),
                a2=float(s.get("option_top2") or 0),
                rr=float(s.get("mean_option_rr") or 0),
                t=s.get("n_had_ties_before"),
                llm=s.get("n_llm_strict"),
                res=s.get("n_residual_ties"),
            )
        )
    lines += [
        "",
        "## 读数注意",
        "",
        "- 本表 **不入论文主表**，直至写入 `paper_ablation_plan.md` 并完成配对显著性检验。",
        "- `option@1` 在此定义为 gold 选项在严格全序中的位置 = 1（不再允许并列共享 rank 1）。",
        "- 与旧 option@1 的差额 ≈ 旧口径下「并列救回」被拆散后的损失。",
        "",
    ]
    (OUT_ROOT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", OUT_ROOT / "summary.md")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="all", help="comma list or 'all'")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", action="store_false", dest="resume")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-cases", type=int, default=None)
    args = ap.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    raw_llm = RobustLLMClient(
        model=args.model,
        call_timeout=240,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    cache_path = OUT_ROOT / "cache" / "strict_total_order_llm.json"
    llm: Any
    if args.dry_run:
        llm = None
    else:
        llm = TieRejectCachedLLM(raw_llm, cache_path, args.model)

    all_arms = registry()
    if args.arms.strip().lower() != "all":
        wanted = {x.strip() for x in args.arms.split(",") if x.strip()}
        all_arms = [a for a in all_arms if a["key"] in wanted]

    summaries: list[dict[str, Any]] = []
    for arm in all_arms:
        print(f"=== {arm['key']} ({arm['kind']}) ===", flush=True)
        started = time.monotonic()
        if arm["kind"] == "m00_rematch":
            summary = process_m00_rematch(
                llm=llm, prompt=prompt, workers=args.workers,
                resume=args.resume, model=args.model, max_cases=args.max_cases,
            )
        elif arm["kind"] == "records":
            summary = process_records_arm(
                arm, llm=llm, prompt=prompt, workers=args.workers,
                resume=args.resume, max_cases=args.max_cases,
            )
        else:
            summary = process_projection_arm(
                arm, llm=llm, prompt=prompt, workers=args.workers,
                resume=args.resume, max_cases=args.max_cases,
            )
        summary["wall_seconds"] = round(time.monotonic() - started, 1)
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)

    write_aggregate(summaries)
    if isinstance(llm, TieRejectCachedLLM):
        print(
            "cache hits=%s misses=%s rejected_tie_hits=%s"
            % (llm.hits, llm.misses, llm.rejected_tie_hits),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
