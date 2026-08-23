#!/usr/bin/env python3
"""MCR_SELECTOR_TRUNCATION_V1: replay the frozen MultiStance selector call on a
truncated candidate payload.

The frozen `aphhm_c_multistance_v1` arm makes exactly one selector call per case
(`AphhmCFrontierSelector`, tournament prompt).  Its payload is *not* stored in the
log, so it is rebuilt here from the frozen `stages.registry` + `stages.ledger_rank`
following `AphhmC._select_frontier` for the flags that arm actually ran with
(`selector_all_concepts`, `selector_candidate_evidence`, `selector_unanchored`,
`tournament`, no near-dedup).

G1 is not a statistical gate: the rebuilt payload is hashed with the same
`stable_hash` the runtime used, looked up in the frozen LLM cache, and the cached
response is compared against `stages.frontier_selector`.  A byte-exact match on
every case proves the reconstruction, so the `replay_full` arm costs zero calls.

Arms (all strict subsets of the frozen candidate set; nothing is ever added):

    replay_full  real stance groups, every candidate          (frozen identity)
    group5       real stance groups, first 5 in payload order
    flat5        one pseudo-group, first 5 in payload order
    flat3        one pseudo-group, first 3 in payload order

`ledger_rank` is *generation order*: for this arm the evidence matrix is disabled
so every score is 0.0 and `ledger_rank == sorted(concept_id)` on 400/400 cases.
Truncation therefore keeps the candidates the comparator already saw first and
injects no ranking the frozen payload did not carry.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT / "scripts" / "paper", ROOT / "analysis" / "backbone_v1"):
    sys.path.insert(0, str(p))

import baseline_common as bc  # noqa: E402

PROMPT_PATH = (
    ROOT
    / "src"
    / "agentclinic_tree_dx"
    / "prompts"
    / "aphhm_c_frontier_selector_tournament.txt"
)
PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
MODULE = "AphhmCFrontierSelector"
FROZEN_ARM = "aphhm_c_multistance_v1"
LOGS = ROOT / "logs" / "backbone_v1"

# (log dataset dir, runtime dataset name, slice key)
MCR_SLICES = (
    ("medcasereasoning", "medcasereasoning", "mcr_v1"),
    ("medcasereasoning_v2", "medcasereasoning", "mcr_v2"),
    ("medcasereasoning_200b", "medcasereasoning", "mcr_200b"),
)

FLAT_GROUP = "all"


# --- frozen-log plumbing ---------------------------------------------------
def frozen_dir(log_ds: str) -> Path:
    return LOGS / log_ds / FROZEN_ARM


def load_doc(log_ds: str, cid: str) -> dict:
    d = frozen_dir(log_ds) / "case_stages"
    for key in (cid, cid.lstrip("0") or "0"):
        p = d / f"{key}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    if cid.isdigit():
        p = d / f"{int(cid)}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def load_cases(log_ds: str, ds_name: str) -> list[Mapping[str, Any]]:
    man = json.loads((frozen_dir(log_ds) / "manifest.json").read_text(encoding="utf-8"))
    return list(bc.load_runtime_cases(dataset=ds_name, subset_dir=man["subset"], limit=0))


def frozen_cache(log_ds: str) -> dict:
    p = frozen_dir(log_ds) / "cache" / "aphhm_c_llm.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


# --- payload reconstruction ------------------------------------------------
def ordered_candidates(stages: Mapping[str, Any]) -> list[dict]:
    """The exact `frontier` list `_select_frontier` received, in payload order."""
    reg = {c.get("concept_id"): c for c in (stages.get("registry") or [])}
    order = [cid for cid in (stages.get("ledger_rank") or []) if cid in reg]
    return [reg[cid] for cid in order]


def _note(c: Mapping[str, Any]) -> dict:
    # selector_candidate_evidence=True for multistance: generator spans, no score
    return {
        "label": c.get("preferred_label") or "",
        "for": list(c.get("support_spans") or [])[:4],
        "against": list(c.get("contradict_spans") or [])[:3],
    }


def build_payload(
    stages: Mapping[str, Any],
    vignette: str,
    *,
    keep: Optional[int] = None,
    flatten: bool = False,
) -> dict:
    cands = ordered_candidates(stages)
    if keep is not None:
        cands = cands[:keep]
    notes = [_note(c) for c in cands]
    shortlist = [str(c.get("preferred_label") or "") for c in cands]
    groups: dict[str, list[dict]] = {}
    for c, note in zip(cands, notes):
        stances = [str(s) for s in (c.get("stances") or []) if str(s)]
        entry = dict(note)
        if len(stances) > 1:
            entry["also_found_by"] = stances[1:]
        key = FLAT_GROUP if flatten else (stances[0] if stances else "unassigned")
        groups.setdefault(key, []).append(entry)
    return {
        "vignette": vignette,
        "shortlist": shortlist,
        "groups": [{"group": g, "candidates": v} for g, v in groups.items()],
    }


ARMS: dict[str, dict[str, Any]] = {
    "replay_full": {"keep": None, "flatten": False},
    "group5": {"keep": 5, "flatten": False},
    "flat5": {"keep": 5, "flatten": True},
    "flat3": {"keep": 3, "flatten": True},
}


def payload_key(payload: Mapping[str, Any]) -> str:
    return bc.stable_hash({"module": MODULE, "prompt": PROMPT, "payload": payload})


def champion_of(raw: Mapping[str, Any], shortlist: list[str]) -> str:
    """Same normalisation the runtime applies after the selector call."""
    champ = str(raw.get("champion") or "").strip()
    if champ in shortlist or not shortlist:
        return champ
    low = {s.strip().lower(): s for s in shortlist}
    return low.get(champ.strip().lower(), shortlist[0])


# --- G1: reconstruction fidelity, zero calls -------------------------------
def verify_g1(slices: Iterable[tuple[str, str, str]] = MCR_SLICES) -> dict:
    out = {"per_slice": {}, "n": 0, "cache_hit": 0, "output_identical": 0, "mismatch": []}
    for log_ds, ds_name, sl in slices:
        cache = frozen_cache(log_ds)
        rec = {"n": 0, "cache_hit": 0, "output_identical": 0, "cache_entries": len(cache)}
        for case in load_cases(log_ds, ds_name):
            cid = str(case.get("source_id") or case.get("case_id") or "")
            doc = load_doc(log_ds, cid)
            stages = doc.get("stages") or {}
            if not stages.get("registry") or not stages.get("frontier_selector"):
                continue
            rec["n"] += 1
            payload = build_payload(stages, str(case.get("vignette") or ""))
            key = payload_key(payload)
            if key not in cache:
                out["mismatch"].append({"slice": sl, "case": cid, "why": "cache_miss"})
                continue
            rec["cache_hit"] += 1
            if cache[key] == stages["frontier_selector"]:
                rec["output_identical"] += 1
            else:
                out["mismatch"].append({"slice": sl, "case": cid, "why": "output_differs"})
        out["per_slice"][sl] = rec
        for k in ("n", "cache_hit", "output_identical"):
            out[k] += rec[k]
    out["cache_hit_rate"] = out["cache_hit"] / max(out["n"], 1)
    out["identical_rate"] = out["output_identical"] / max(out["n"], 1)
    out["pass"] = out["n"] > 0 and out["output_identical"] == out["n"]
    return out


# --- arm execution ---------------------------------------------------------
def run_arm(
    arm: str,
    *,
    slices: Iterable[tuple[str, str, str]] = MCR_SLICES,
    cohort: Optional[set[tuple[str, str]]] = None,
    model: str = "meta-llama/llama-3.3-70b-instruct",
    workers: int = 25,
    out_root: Optional[Path] = None,
    dry_run: bool = False,
) -> dict:
    """One selector call per case on the arm's payload. Frozen cache is read-only."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm}; choose from {sorted(ARMS)}")
    spec = ARMS[arm]
    out_root = out_root or (
        ROOT / "analysis" / "mechanism_v2" / "results" / "MCR_SELECTOR_TRUNCATION" / "runs"
    )
    out_dir = out_root / arm
    out_dir.mkdir(parents=True, exist_ok=True)

    client = None
    if not dry_run:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        client = RobustLLMClient(
            model=model,
            call_timeout=240,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=0.0,
        )
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "selector.json", model)

    jobs: list[tuple[str, str, str, dict, dict]] = []
    for log_ds, ds_name, sl in slices:
        frozen = frozen_cache(log_ds)
        for case in load_cases(log_ds, ds_name):
            cid = str(case.get("source_id") or case.get("case_id") or "")
            if cohort is not None and (sl, cid) not in cohort:
                continue
            doc = load_doc(log_ds, cid)
            stages = doc.get("stages") or {}
            if not stages.get("registry") or not stages.get("frontier_selector"):
                continue
            payload = build_payload(
                stages, str(case.get("vignette") or ""), keep=spec["keep"], flatten=spec["flatten"]
            )
            jobs.append((sl, cid, log_ds, payload, frozen))

    def one(job: tuple[str, str, str, dict, dict]) -> dict:
        sl, cid, log_ds, payload, frozen = job
        shortlist = list(payload["shortlist"])
        key = payload_key(payload)
        source = "frozen_cache" if key in frozen else "online"
        raw = dict(frozen[key]) if key in frozen else cached.call(MODULE, PROMPT, payload)
        champ = champion_of(raw, shortlist)
        return {
            "slice": sl,
            "case_id": cid,
            "arm": arm,
            "champion": champ,
            "shortlist": shortlist,
            "n_candidates": len(shortlist),
            "n_groups": len(payload["groups"]),
            "champion_in_slate": champ in shortlist,
            "raw": raw,
            "source": source,
        }

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rows.append(fut.result())
            if i % 25 == 0 or i == len(jobs):
                print(f"  [{i}/{len(jobs)}] {arm}", flush=True)

    rows.sort(key=lambda r: (r["slice"], int(r["case_id"]) if r["case_id"].isdigit() else 0))
    (out_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    summary = {
        "arm": arm,
        "n": len(rows),
        "online_calls": sum(1 for r in rows if r["source"] == "online"),
        "frozen_cache_hits": sum(1 for r in rows if r["source"] == "frozen_cache"),
        "mean_width": (sum(r["n_candidates"] for r in rows) / len(rows)) if rows else 0.0,
        "champion_in_slate": sum(1 for r in rows if r["champion_in_slate"]),
        "out": str(out_dir),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--g1", action="store_true", help="verify payload reconstruction, zero calls")
    ap.add_argument("--arm", choices=sorted(ARMS))
    ap.add_argument("--cohort", type=Path, help="jsonl with {slice, case_id} to restrict to")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true", help="frozen cache only, never call out")
    args = ap.parse_args()

    if args.g1:
        res = verify_g1()
        print(json.dumps({k: v for k, v in res.items() if k != "mismatch"}, indent=2))
        if res["mismatch"]:
            print(f"\nmismatches ({len(res['mismatch'])}), first 10:")
            for m in res["mismatch"][:10]:
                print("  ", m)
        print("\nG1:", "PASS" if res["pass"] else "FAIL")
        return 0 if res["pass"] else 1

    if args.arm:
        cohort = None
        if args.cohort:
            cohort = {
                (str(r["slice"]), str(r["case_id"]))
                for r in (json.loads(l) for l in args.cohort.read_text().splitlines() if l.strip())
            }
        print(json.dumps(run_arm(
            args.arm, cohort=cohort, model=args.model,
            workers=args.workers, dry_run=args.dry_run,
        ), indent=2))
        return 0

    ap.error("pass --g1 or --arm")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
