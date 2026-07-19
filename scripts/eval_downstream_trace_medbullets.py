"""Downstream failure LOCALIZATION on the hard medbullets dx cases (§RESIDUAL_MISS
(2)): branch creation is already L1-clean (9/9), so any final miss is DOWNSTREAM.
This harness runs the REAL full production controller (select_root → branches →
evidence loop → AnswerMapper) and, for each case, attributes a miss to the stage
that actually lost the gold direction.

Per-case trace captured from the returned state:
  * pred option letter vs gold letter                         (final correctness)
  * L1 branches + their FINAL posteriors + status
  * gold's L1 family (LLM judge over the L1 labels)
  * that family's posterior TRAJECTORY across differential_history
  * stage attribution for a miss:
      - OK               : pred == gold
      - MAP_FAIL         : gold L1 family ended TOP (rank-1) but pred≠gold
                           → AnswerMapper mapped the winning family to the wrong
                             option (commit/answer-mapping stage)
      - EVIDENCE_COLLAPSE: gold family started with mass (early rank≤2 / p≥0.2)
                           then decayed below top → evidence/probability update
      - PRIOR_STARVED    : gold family never gained mass (max posterior < 0.2)
                           → prior / frontier-coverage / leaf-planning starved it
      - L1_MISS          : no L1 family covers the gold (should not happen; the
                           branch stage is 9/9 — flags a regression)

Branch path = PURE-LLM single-axis (production default, NO curated axis map / NO
B-table). The manual-curation audit (eval_branch_creation_medbullets.py
--branch-mode) showed pure_llm already reaches 9/9 clean L1, so the scalable,
zero-curation branch path is what we diagnose downstream on.

    PYTHONPATH=src python scripts/eval_downstream_trace_medbullets.py [--limit N]
Requires the gnn-llm env + VPN.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
# GPU embedding (matches eval_pipeline_medbullets). CPU embedding under N
# concurrent worker threads oversubscribes cores and stalls the whole process.
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cuda:2")
os.environ.setdefault("TREE_DX_EMBED_BATCH", "256")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "2")
_alloc = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
if "max_split_size_mb:" in _alloc:
    try:
        if int(_alloc.split("max_split_size_mb:")[1].split(",")[0]) < 21:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""
    except (ValueError, IndexError):
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""
# Fully initialize torch in the MAIN thread before the worker pool. The
# chain-discoverer lazily imports torch.nn inside workers; concurrent first
# imports race into "partially initialized module 'torch' has no attribute
# 'nn'", silently degrading TALP knowledge injection (a downstream stage we are
# diagnosing). Import eagerly here so every worker sees a ready module.
try:
    import torch as _torch  # noqa: F401
    _ = _torch.nn  # noqa: B018
except Exception:  # noqa: BLE001
    pass

DATA = PROJECT_ROOT / "data"

_spec = importlib.util.spec_from_file_location(
    "mb", PROJECT_ROOT / "scripts" / "eval_pipeline_medbullets.py")
_mb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mb)

_bc_spec = importlib.util.spec_from_file_location(
    "bc", PROJECT_ROOT / "scripts" / "eval_branch_creation_medbullets.py")
_bc = importlib.util.module_from_spec(_bc_spec)
_bc_spec.loader.exec_module(_bc)


def build_controller(model: str, secondary_cache: bool = True,
                     branch_mode: str = "pure_llm", gate: bool = False):
    """Production config for the downstream stages (evidence loop / rule-out /
    age prior / AnswerMapper), single-axis prompt (landed). ``branch_mode`` picks
    the L1 branch source, so we can A/B whether the "4-way union / B-table full"
    path hurts DOWNSTREAM accuracy vs the scalable pure-LLM path:
      pure_llm : NO axis map, NO B-table entrances (default; §12 = 9/9 L1-clean)
      btable   : B-table FULLY ON — enable_branch_knowledge + case_report + cpg +
                 llm_ddx dual-entrance recall + hand-curated syndrome_axis_map
                 (the "best-config test-program" setting)."""
    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    btable = branch_mode == "btable"
    config = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        max_turn_budget=5,
        min_readiness_to_commit=0.70,
        allow_external_knowledge=True,
        dxs_common_json=str(DATA / "knowledge_raw" / "Guideline_common.json"),
        dxs_rare_json=str(DATA / "knowledge_raw" / "Guideline_rare.json"),
        primekg_csv=str(DATA / "knowledge_raw" / "kg.csv"),
        lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
        doclogica_cache_json=str(DATA / "knowledge_raw" / "doclogica_cache.json"),
        pathognomonic_markers_json=str(DATA / "knowledge_raw" / "pathognomonic_markers.json"),
        auto_ambiguity_map_json=str(DATA / "knowledge_raw" / "auto_ambiguity_map.json"),
        lab_reference_ranges_json=str(DATA / "knowledge_raw" / "lab_reference_ranges.json"),
        loinc2hpo_json=str(DATA / "knowledge_raw" / "loinc2hpo_annotations.json"),
        unit_conversions_json=str(DATA / "knowledge_raw" / "unit_conversions.json"),
        snomed_concepts_json=str(DATA / "knowledge_raw" / "snomed_concepts.json"),
        snomed_term_index_json=str(DATA / "knowledge_raw" / "snomed_term_index.json"),
        snomed_relations_json=str(DATA / "knowledge_raw" / "snomed_relations.json"),
        enable_knowledge_injection=True,
        enable_lr_rag_fallback=True,
        enable_normal_value_ruleout=True,
        enable_age_prior=True,
        age_sex_incidence_json=str(DATA / "knowledge_raw" / "age_sex_incidence.json"),
        rag_lr_can_override_direction=False,
        ruleout_require_present_path_silent=True,
        # Branch path: pure_llm (default) OR B-table full 4-way union.
        enable_branch_knowledge=btable,
        enable_case_report_branch_source=btable,
        enable_cpg_branch_source=btable,
        enable_llm_ddx_branch_entrance=btable,
        salient_finding_entrance_weight=0.5,
        case_report_index_dir=str(DATA / "corpus" / "case_report_index"),
        enable_chain_discoverer=True,
        max_knowledge_prompt_lines=40,
        # B-table points the CPG entrance at the rebuilt cpg_index (D-data fix);
        # pure_llm keeps the production rag_index (unused for branching there).
        rag_index_dir=str(DATA / "corpus" / ("cpg_index" if btable else "rag_index")),
        enable_pubmed_fallback=False,
        use_dual_channel_bundler=True,
        # Per-case subprocess isolation shares ONE secondary-LR-cache JSON across
        # 9 processes → constant full-file re-dumps + write contention stall the
        # LR-reference build (observed via stack self-dump: secondary_lr_cache.
        # _flush_locked / lr_retriever.lookup_fuzzy). Recompute per process
        # instead; behaviour is identical, only the cache write is skipped.
        enable_secondary_lr_cache=secondary_cache,
        enable_discrimination_gate=gate,
        max_protocol_retries=2,
    )
    llm = RobustLLMClient(model=model, call_timeout=240, max_retries=5,
                          timeout_retry_cap=2)
    env = _mb.ThreadLocalEnv()
    controller = AgentClinicTreeController(env=env, llm=llm, config=config)
    return controller, env, config


def _l1(branches: dict) -> dict:
    """Level-1 branches only: id → {label, posterior, status}."""
    out = {}
    for bid, b in (branches or {}).items():
        if int(b.get("level", 1)) == 1:
            out[bid] = {"label": b.get("label", ""),
                        "posterior": float(b.get("posterior", 0.0) or 0.0),
                        "status": b.get("status", "")}
    return out


def _rank_of(post_map: dict, bid: str) -> int:
    order = sorted(post_map.items(), key=lambda kv: kv[1], reverse=True)
    for r, (k, _) in enumerate(order):
        if k == bid:
            return r + 1
    return -1


def localize(gold: str, res: dict, judge) -> dict:
    st = res.get("internal_reasoning_state", {}) or {}
    branches = st.get("branches", {}) or {}
    l1 = _l1(branches)
    labels = [v["label"] for v in l1.values()]
    ids = list(l1.keys())
    gi = judge(gold, labels) if labels else -1
    if not (0 <= gi < len(ids)):
        return {"stage": "L1_MISS", "gold_family": None, "l1_labels": labels,
                "final_post": {}, "traj": []}
    gold_bid = ids[gi]
    gold_label = l1[gold_bid]["label"]

    final_post = {v["label"]: round(v["posterior"], 3) for v in l1.values()}
    # posterior trajectory of the gold family across differential history. The
    # history dicts are keyed by branch id (top-level) → posterior.
    hist = st.get("differential_history", []) or []
    traj = []
    for snap in hist:
        if isinstance(snap, dict) and gold_bid in snap:
            traj.append(round(float(snap[gold_bid]), 3))
    final_rank = _rank_of({k: v["posterior"] for k, v in l1.items()}, gold_bid)
    max_post = max(traj + [l1[gold_bid]["posterior"]], default=0.0)
    early_rank = None
    if hist:
        first = {k: v for k, v in hist[0].items() if k in l1} if isinstance(hist[0], dict) else {}
        if gold_bid in first:
            early_rank = _rank_of(first, gold_bid)

    return {"stage": None, "gold_family": gold_label, "gold_bid": gold_bid,
            "l1_labels": labels, "final_post": final_post,
            "final_rank": final_rank, "max_post": round(max_post, 3),
            "early_rank": early_rank, "traj": traj}


def attribute(pred_ok: bool, loc: dict) -> str:
    if pred_ok:
        return "OK"
    if loc.get("stage") == "L1_MISS":
        return "L1_MISS"
    fr = loc.get("final_rank", -1)
    mx = loc.get("max_post", 0.0)
    er = loc.get("early_rank")
    if fr == 1:
        return "MAP_FAIL"
    if mx >= 0.2 and (er is not None and er <= 2):
        return "EVIDENCE_COLLAPSE"
    if mx < 0.2:
        return "PRIOR_STARVED"
    return "EVIDENCE_COLLAPSE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--include-image", action="store_true")
    ap.add_argument("--case-timeout", type=float, default=600.0,
                    help="per-case wall cap (s); case 18 has a known CPU runaway")
    ap.add_argument("--only", type=int, default=-1,
                    help="run EXACTLY this case index in this process, append its "
                         "result to logs/downstream_<tag>.jsonl, and exit. Used by "
                         "the per-case subprocess orchestrator (isolates the "
                         "GIL-holding CPU-runaway case from the others).")
    ap.add_argument("--cases", default="", help="comma-separated case indices")
    ap.add_argument("--branch-mode", default="pure_llm",
                    choices=["pure_llm", "btable"],
                    help="pure_llm (scalable, no curation) | btable (4-way union, "
                         "B-table full + hand-curated axis map)")
    ap.add_argument("--tag", default="downstream")
    ap.add_argument("--gate", action="store_true",
                    help="§13 enable_discrimination_gate (freeze non-discriminative "
                         "turns so a broad correct family is not diluted)")
    args = ap.parse_args()

    from collections import Counter

    all_cases = _mb.load_dx_cases()
    cases = [(i, c) for i, c in enumerate(all_cases)
             if args.include_image or not c["is_image"]]
    if args.cases:
        want = {int(x) for x in args.cases.split(",") if x.strip()}
        cases = [(i, c) for i, c in cases if i in want]
    if args.limit:
        cases = cases[:args.limit]

    resdir = PROJECT_ROOT / "logs" / f"_downstream_{args.tag}"
    resdir.mkdir(parents=True, exist_ok=True)

    # ── single-case worker (own PROCESS → own GIL, isolates the CPU-runaway
    # case so it cannot starve the others) ────────────────────────────────────
    if args.only >= 0:
        return _run_single(args.only, dict(cases)[args.only], args.model, resdir,
                           args.branch_mode, args.gate)

    # ── orchestrator: one subprocess per case, all concurrent, per-proc kill ──
    import subprocess
    print(f"Downstream trace (model={args.model}, branch_mode={args.branch_mode}, "
          f"per-case subprocess, timeout={args.case_timeout:.0f}s)")
    print(f"Localizing {len(cases)} text-only dx cases (subprocess-isolated)\n")
    procs = {}
    for i, _ in cases:
        (resdir / f"case_{i}.json").unlink(missing_ok=True)
        lf = open(resdir / f"case_{i}.log", "w")
        p = subprocess.Popen(
            [sys.executable, __file__, "--only", str(i), "--tag", args.tag,
             "--model", args.model, "--branch-mode", args.branch_mode]
            + (["--gate"] if args.gate else []),
            stdout=lf, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONPATH": "src", "PYTHONUNBUFFERED": "1"},
            cwd=str(PROJECT_ROOT))
        procs[i] = (p, lf, time.time())

    deadline = time.time() + args.case_timeout
    while any(p.poll() is None for p, _, _ in procs.values()):
        if time.time() > deadline:
            for i, (p, _, _) in procs.items():
                if p.poll() is None:
                    p.kill()
                    print(f"[TIMEOUT] case {i} killed at {args.case_timeout:.0f}s "
                          f"(CPU runaway)", flush=True)
            break
        time.sleep(3)
    for p, lf, _ in procs.values():
        try:
            p.wait(timeout=10)
        except Exception:  # noqa: BLE001
            p.kill()
        lf.close()

    rows = []
    for i, _ in cases:
        f = resdir / f"case_{i}.json"
        if f.exists():
            rows.append(json.loads(f.read_text()))
        else:
            rows.append({"idx": i, "stage": "TIMEOUT",
                         "error": f"no result (timeout {args.case_timeout:.0f}s)"})
    rows.sort(key=lambda r: r["idx"])
    stages = Counter(r["stage"] for r in rows)
    scored = [r for r in rows if r["stage"] not in ("ERR", "PROTO", "TIMEOUT")]
    ok = sum(1 for r in scored if r.get("ok"))
    print("\n" + "=" * 72)
    print(f"DOWNSTREAM LOCALIZATION (n={len(scored)})")
    print(f"  final accuracy: {ok}/{len(scored)}")
    print(f"  stage attribution: {dict(stages)}")
    for r in rows:
        tag = "OK " if r.get("ok") else "XX "
        print(f"  {tag}case {r['idx']:<2} [{r['stage']:<16}] "
              f"gold={r.get('gold')} pred={r.get('pred','?')} "
              f"dx={str(r.get('gold_dx'))[:28]:<28} "
              f"fam={str(r.get('gold_family'))[:26]:<26} "
              f"rank={r.get('final_rank')} maxp={r.get('max_post')} "
              f"traj={r.get('traj')}")
    out = PROJECT_ROOT / "logs" / f"downstream_{args.tag}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"  detail → {out}")
    return 0


def _run_single(i: int, c: dict, model: str, resdir: Path,
                branch_mode: str = "pure_llm", gate: bool = False) -> int:
    """Run ONE case end-to-end in this process and write its result JSON."""
    # Self-dump every worker's stack if it runs too long, so a CPU-runaway case
    # reveals the spinning frame (localizes the hang without an external tool).
    import faulthandler
    _secs = int(os.environ.get("TREE_DX_SELFDUMP_SECS", "0"))
    if _secs > 0:
        faulthandler.dump_traceback_later(_secs, repeat=True)
    _mb._bump_http_pool(4)
    from agentclinic_tree_dx.controller import LLMProtocolError
    from agentclinic_tree_dx.state import DiagnosticState
    controller, env, config = build_controller(model, secondary_cache=False,
                                               branch_mode=branch_mode, gate=gate)
    try:
        controller._knowledge_retriever.format_discriminator_hints_for_prompt(
            ["chronic myeloid leukemia", "acute myeloid leukemia"],
            seen_evidence=[], max_lines=5, vignette_text="warmup",
            include_chains=False)
    except Exception as e:  # noqa: BLE001
        print(f"[warmup] {e}")
    judge = _bc.make_judge(model)

    gold_letter = c["answer_idx"].strip().upper()
    gold_dx = c["answer"].strip()
    env.set_case(_mb.build_case_text(c))
    state = DiagnosticState(case_id=f"MB_{i}")
    t0 = time.time()
    rec = {"idx": i, "gold": gold_letter, "gold_dx": gold_dx, "stage": "ERR"}
    try:
        res = controller.run(state)
        fa = (res.get("final_answer", "") or "").strip().upper()
        pred = fa[0] if fa else "?"
        pred_ok = pred == gold_letter
        loc = localize(gold_dx, res, judge)
        rec.update({"pred": pred, "ok": pred_ok,
                    "stage": attribute(pred_ok, loc),
                    "gold_family": loc.get("gold_family"),
                    "final_rank": loc.get("final_rank"),
                    "max_post": loc.get("max_post"),
                    "early_rank": loc.get("early_rank"),
                    "traj": loc.get("traj"),
                    "final_post": loc.get("final_post"),
                    "answer_option_mapping": res.get("answer_option_mapping", {})})
    except LLMProtocolError as e:
        rec.update({"stage": "PROTO", "error": str(e)})
    except Exception as e:  # noqa: BLE001
        rec.update({"stage": "ERR", "error": f"{type(e).__name__}: {e}"})
    rec["dt"] = round(time.time() - t0, 1)
    (resdir / f"case_{i}.json").write_text(json.dumps(rec, ensure_ascii=False))
    print(f"[{rec['stage']}] case {i} gold={gold_letter} pred={rec.get('pred','?')} "
          f"({rec['dt']:.0f}s)", flush=True)
    os._exit(0)  # hard-exit: a runaway daemon thread must not block process exit


if __name__ == "__main__":
    raise SystemExit(main())
