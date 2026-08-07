#!/usr/bin/env python3
"""Shared contract for paper baselines (open vignette → ordered Top-K)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import diagnosisarena_adapter as da  # noqa: E402
import medcasereasoning_adapter as mcr_ad  # noqa: E402
import open_xddx_adapter as ox_ad  # noqa: E402
import rarearena_adapter as ra_ad  # noqa: E402

DATA = ROOT / "data"
DEFAULT_SUBSET = DATA / "benchmarks" / "diagnosisarena" / "subsets" / "d2_seq100_v1"
DEFAULT_OX_SUBSET = DATA / "benchmarks" / "open_xddx" / "subsets" / "ox_seq100_v1"
DEFAULT_MCR_SUBSET = (
    DATA / "benchmarks" / "medcasereasoning" / "subsets" / "mcr_val_seq100_v1"
)
DEFAULT_RA_SUBSET = (
    DATA / "benchmarks" / "rarearena" / "subsets" / "ra_rdc_seq100_v1"
)
DEFAULT_CASES = DEFAULT_SUBSET / "cases.parquet"
DEFAULT_RUNS = ROOT / "runs" / "paper_v1" / "diagnosisarena"
DEFAULT_OX_RUNS = ROOT / "runs" / "paper_v1" / "open_xddx"
DEFAULT_MCR_RUNS = ROOT / "runs" / "paper_v1" / "medcasereasoning"
DEFAULT_RA_RUNS = ROOT / "runs" / "paper_v1" / "rarearena"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"

DATASET_DIAGNOSISARENA = "diagnosisarena"
DATASET_OPEN_XDDX = "open_xddx"
DATASET_MCR = "medcasereasoning"
DATASET_RAREARENA = "rarearena"

# OX formal DDx length must match tree-system ddx_k (5 or 7).
OX_LIST_K_ALLOWED = frozenset({5, 7})
DEFAULT_OX_LIST_K = 5

ARM_IDS = {
    "B00-direct-cot",
    "B01-cot-rag",
    "B02-flat-matched-rerank",
    "B02-flat-compute-matched",
    "B02-flat-compute-matched-sc10",
    "B03-flat-beam",
    "B04-dual-inf",
    "B05-mdagents",
    "B06-mac-single-vendor",
    "B07-meddxagent-complete",
    "B08-deeprare",
    "B09-phenotype-tools",
    "B10-mixed-vendor-mac",
    "B11a-official-diagnosisgpt",
    "B11b-cod-prompt-shared-kb",
    "B12-sc-cot-5",
    "B13-self-refine-1",
    "B14-candidate-flat-union",
    "A01-fixed-taxonomy",
    "A13-emulation-full-matrix",
    "B15-medprompt-style",
    "B16-medrag-kg",
    "B17-imedrag",
}

GOLD_KEYS = frozenset({
    "gold", "gold_diagnosis", "gold_option", "gold_letter", "final_diagnosis",
    "right_option", "acceptable_l2", "is_gold", "evaluation_alias",
    "ddx_set", "interpretation", "diagnostic_reasoning", "reasoning_points",
})


def normalize_dataset(name: str) -> str:
    ds = str(name or DATASET_DIAGNOSISARENA).strip().lower().replace("-", "_")
    if ds in {"da", "diagnosis_arena", "diagnosisarena"}:
        return DATASET_DIAGNOSISARENA
    if ds in {"ox", "open_xddx", "openxddx"}:
        return DATASET_OPEN_XDDX
    if ds in {"mcr", "medcase", "medcasereasoning", "med_case_reasoning"}:
        return DATASET_MCR
    if ds in {"ra", "rarearena", "rare_arena", "ra_rdc"}:
        return DATASET_RAREARENA
    raise ValueError("unknown dataset: %s" % name)


def default_subset_for(dataset: str) -> Path:
    ds = normalize_dataset(dataset)
    if ds == DATASET_OPEN_XDDX:
        return DEFAULT_OX_SUBSET
    if ds == DATASET_MCR:
        return DEFAULT_MCR_SUBSET
    if ds == DATASET_RAREARENA:
        return DEFAULT_RA_SUBSET
    return DEFAULT_SUBSET


def default_runs_root_for(dataset: str) -> Path:
    ds = normalize_dataset(dataset)
    if ds == DATASET_OPEN_XDDX:
        return DEFAULT_OX_RUNS
    if ds == DATASET_MCR:
        return DEFAULT_MCR_RUNS
    if ds == DATASET_RAREARENA:
        return DEFAULT_RA_RUNS
    return DEFAULT_RUNS


def default_list_k_for(dataset: str) -> int:
    ds = normalize_dataset(dataset)
    if ds == DATASET_OPEN_XDDX:
        return DEFAULT_OX_LIST_K
    return 2


def validate_list_k(dataset: str, list_k: int) -> int:
    ds = normalize_dataset(dataset)
    k = int(list_k)
    if k < 1:
        raise ValueError("list_k must be >= 1")
    if ds == DATASET_OPEN_XDDX and k not in OX_LIST_K_ALLOWED:
        raise ValueError(
            "open_xddx list_k must be 5 or 7 (got %s); required for fair "
            "comparison with tree-system ddx_k" % k
        )
    return k


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


_JSONL_LOCKS: dict[str, Any] = {}
_JSONL_LOCKS_GUARD = None


def _jsonl_lock(path: Path):
    import threading

    global _JSONL_LOCKS_GUARD
    if _JSONL_LOCKS_GUARD is None:
        _JSONL_LOCKS_GUARD = threading.Lock()
    key = str(path.resolve())
    with _JSONL_LOCKS_GUARD:
        lock = _JSONL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _JSONL_LOCKS[key] = lock
        return lock


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _jsonl_lock(path):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def assert_no_gold_leak(payload: Any, path: str = "payload") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key).lower() in GOLD_KEYS:
                raise AssertionError(f"gold leak at {path}.{key}")
            assert_no_gold_leak(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_no_gold_leak(value, f"{path}[{index}]")


def _case_ids_from_subset(
    subset_dir: Path,
    case_ids: Sequence[str],
    limit: int,
) -> tuple[list[str], int]:
    ids = list(case_ids)
    ids_file = subset_dir / "case_ids.txt"
    if not ids and ids_file.is_file():
        ids = [
            line.strip()
            for line in ids_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    lim = int(limit)
    if lim > 0 and ids:
        ids = list(ids)[:lim]
        lim = 0
    return ids, lim


def load_runtime_cases(
    *,
    subset_dir: Path | None = None,
    case_ids: Sequence[str] = (),
    limit: int = 0,
    dataset: str = DATASET_DIAGNOSISARENA,
) -> list[dict[str, Any]]:
    """Load cases and strip gold from runtime-facing fields."""
    ds = normalize_dataset(dataset)
    subset = Path(subset_dir) if subset_dir is not None else default_subset_for(ds)
    parquet = subset / "cases.parquet"
    ids, lim = _case_ids_from_subset(subset, case_ids, limit)

    if ds == DATASET_OPEN_XDDX:
        raw = ox_ad.load_subset_cases(parquet, case_ids=ids, limit=lim)
        prefix = "open_xddx"
    elif ds == DATASET_MCR:
        raw = mcr_ad.load_subset_cases(parquet, case_ids=ids, limit=lim)
        prefix = "medcasereasoning"
    elif ds == DATASET_RAREARENA:
        raw = ra_ad.load_subset_cases(parquet, case_ids=ids, limit=lim)
        prefix = "rarearena"
    else:
        raw = da.load_subset_cases(parquet, case_ids=ids, limit=lim)
        prefix = "diagnosisarena"

    runtime: list[dict[str, Any]] = []
    for case in raw:
        source_id = str(case["id"])
        vignette = da.vignette_body(case["case_text"]) or str(case["case_text"] or "")
        # OX/MCR/RareArena: open vignette only — do not inject MCQ options into arms.
        options: dict[str, str] = {}
        if ds == DATASET_DIAGNOSISARENA:
            options = da.normalize_options(case["annotation"]["source_options"])
        try:
            cid_num = int(source_id)
            case_id = f"{prefix}__{cid_num:06d}"
        except ValueError:
            case_id = f"{prefix}__{source_id}"
        row: dict[str, Any] = {
            "case_id": case_id,
            "source_id": source_id,
            "dataset": ds,
            "subset": subset.name,
            "vignette": vignette,
            "question": "What is the most likely diagnosis?",
            "options": options,
            "_gold_letter": case.get("gold_option") or "",
            "_gold_text": case.get("gold") or "",
            "runtime_hash": stable_hash({
                "vignette": vignette,
                "options": options,
                "source_id": source_id,
                "dataset": ds,
            }),
        }
        runtime.append(row)
    return runtime


def runtime_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    """Gold-free payload for LLM arms."""
    return {
        "case_id": case["case_id"],
        "vignette": case["vignette"],
        "question": case["question"],
    }


def run_dir(arm: str, replicate: int, *, runs_root: Path = DEFAULT_RUNS) -> Path:
    return runs_root / arm / f"replicate_{int(replicate):02d}"


def empty_cost() -> dict[str, Any]:
    return {
        "llm_calls": 0,
        "input_tokens_est": 0,
        "output_tokens_est": 0,
        "retrieval_calls": 0,
        "retrieval_snippets": 0,
        "snippet_chars": 0,
        "latency_s": 0.0,
    }


def write_manifest(
    out: Path,
    *,
    arm: str,
    replicate: int,
    subset: str,
    model: str,
    budget_mode: str,
    extra: Mapping[str, Any] | None = None,
) -> None:
    payload = {
        "schema_version": "1.0",
        "arm": arm,
        "replicate": replicate,
        "subset": subset,
        "model": model,
        "budget_mode": budget_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_mode": "open_vignette_no_options",
        "output_contract": "ordered_top2_diagnoses",
        "scoring": "RelationAwareAnswerMapper",
    }
    if extra:
        payload.update(dict(extra))
    atomic_json(out / "manifest.json", payload)


def pad_ordered(names: Sequence[str], *, list_k: int) -> list[str]:
    """Pad/truncate to exactly list_k slots (empty string for missing)."""
    k = max(1, int(list_k))
    cleaned = [str(item).strip() for item in names if str(item).strip()]
    # Dedup case-insensitive, preserve order
    out: list[str] = []
    seen: set[str] = set()
    for name in cleaned:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= k:
            break
    while len(out) < k:
        out.append("")
    return out[:k]


def prediction_row(
    case: Mapping[str, Any],
    *,
    arm: str,
    replicate: int,
    top2: Sequence[str],
    cost: Mapping[str, Any],
    trace: Mapping[str, Any] | None = None,
    list_k: int = 2,
) -> dict[str, Any]:
    k = max(1, int(list_k))
    ordered = pad_ordered(top2, list_k=k)
    top2_compat = pad_ordered(ordered, list_k=2)
    return {
        "case_id": case["case_id"],
        "source_id": case["source_id"],
        "arm": arm,
        "replicate": replicate,
        "list_k": k,
        "ordered_diagnoses": ordered,
        "top2_diagnoses": top2_compat,
        "cost": dict(cost),
        "runtime_hash": case["runtime_hash"],
        "trace_digest": stable_hash(trace or {}),
    }


_DIAG_LINE_RE = re.compile(
    r"^\s*(?:\d+[\.\)]\s*|[-*]\s*)?([A-Za-z][^;\n]{2,120})",
)


def parse_numbered_diagnoses(text: str, *, k: int = 2) -> list[str]:
    """Extract ordered disease names from free-form / numbered LLM output."""
    found: list[str] = []
    seen: set[str] = set()
    for line in str(text or "").splitlines():
        match = _DIAG_LINE_RE.match(line.strip())
        if not match:
            continue
        name = match.group(1).strip().rstrip(";,. ")
        key = name.casefold()
        if len(name) < 3 or key in seen:
            continue
        seen.add(key)
        found.append(name)
        if len(found) >= k:
            break
    return found


def clean_topk_from_response(
    response: Mapping[str, Any] | str,
    *,
    k: int = 2,
) -> list[str]:
    """Parse ordered diagnoses from LLM JSON / text (length up to k)."""
    want = max(1, int(k))
    if isinstance(response, str):
        return parse_numbered_diagnoses(response, k=want)
    keys = (
        "ordered_diagnoses",
        "top2_diagnoses",
        "top2_answers",
        "diagnoses",
        "ranked_diagnoses",
        "beam",
        "candidates",
    )
    for key in keys:
        rows = response.get(key) if isinstance(response, Mapping) else None
        if not rows:
            continue
        names: list[str] = []
        if isinstance(rows, Mapping):
            # Dual-Inf style disease→reasons map: preserve insertion order
            for disease in rows.keys():
                name = str(disease).strip()
                if name and name.casefold() not in {n.casefold() for n in names}:
                    names.append(name)
                if len(names) >= want:
                    return names[:want]
            if names:
                return pad_ordered(names, list_k=want)
            continue
        for row in rows:
            if isinstance(row, Mapping):
                name = str(
                    row.get("diagnosis") or row.get("name") or row.get("disease") or ""
                ).strip()
            else:
                name = str(row).strip()
            if name and name.casefold() not in {n.casefold() for n in names}:
                names.append(name)
            if len(names) >= want:
                return names[:want]
        if names:
            return pad_ordered(names, list_k=want)
    raw = ""
    if isinstance(response, Mapping):
        raw = response.get("raw_text") or response.get("text") or ""
    if raw:
        return parse_numbered_diagnoses(str(raw), k=want)
    return pad_ordered([], list_k=want)


def clean_top2_from_response(response: Mapping[str, Any] | str) -> list[str]:
    return clean_topk_from_response(response, k=2)


class SimpleCachedLLM:
    """Minimal disk-cached wrapper around RobustLLMClient.call_module."""

    def __init__(self, client: Any, cache_path: Path, model: str) -> None:
        import threading

        self.client = client
        self.cache_path = cache_path
        self.model = model
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_path.is_file():
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        else:
            self._cache = {}
        self.calls = 0
        self._lock = threading.Lock()

    def call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        assert_no_gold_leak(payload)
        key = stable_hash({"module": module, "prompt": prompt, "payload": payload})
        with self._lock:
            if key in self._cache:
                return dict(self._cache[key])
        if self.client is None:
            raise RuntimeError(
                f"cache miss for {module} and no LLM client (dry-run/cache-only)"
            )
        result = self.client.call_module(module, prompt, dict(payload))
        if not isinstance(result, Mapping):
            result = {"raw_text": str(result)}
        with self._lock:
            self._cache[key] = dict(result)
            self.calls += 1
            atomic_json(self.cache_path, self._cache)
            return dict(result)
