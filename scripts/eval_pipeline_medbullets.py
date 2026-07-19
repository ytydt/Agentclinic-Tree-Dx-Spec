"""Concurrent full-pipeline accuracy eval on medbullets_hard_test.tsv diagnosis
cases, with knowledge injection (TALP discriminator_hints + LR lr_reference) ON
and the robustness layer (protocol validation + retry + skip-on-failure) active.

Design
------
- Loads the knowledge layer ONCE; a single shared controller is reused across
  worker threads. Per-case input is isolated via a thread-local env proxy
  (the controller writes no per-run state to `self`).
- Runs ALL diagnosis-cue cases (de-duplicated) once with `--workers` concurrency,
  tagging each as image-dependent or text-only, then reports BOTH口径:
    * 全量 (full)        — accuracy over all diagnosis cases
    * 不含图像 (no-image) — accuracy over the text-only subset
- LLMProtocolError (LLM refused to follow the output contract after retries) is
  caught and recorded as status PROTO (skipped, logged for later investigation),
  distinct from runtime errors (ERR).

Usage:
  python scripts/eval_pipeline_medbullets.py [--workers 10] [--limit N] [--model qwen/qwen3-32b]

Requires the gnn-llm env + VPN (clashon).
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait as futures_wait
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
# GPU-accelerated retrieval on a single free GPU (default cuda:2). NOTE: profiling
# showed retrieval is NOT the runtime bottleneck — a RAG query is ~11 ms and the
# FAISS search already parallelizes across workers (it runs outside the encode
# lock and releases the GIL); a 3-GPU encoder pool measured ~0 speedup. The wall
# time is dominated by the remote qwen3-32b reasoning LLM (240 s call timeout +
# retries). To enable the (opt-in) multi-GPU encoder pool anyway, set
# TREE_DX_EMBED_DEVICES="cuda:0,cuda:1,cuda:2". Force CPU with TREE_DX_EMBED_DEVICE=cpu.
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cuda:2")
os.environ.setdefault("TREE_DX_EMBED_BATCH", "256")
# §30 SEGFAULT FIX (CPU path): cap native OpenMP/MKL thread pools. The fork RCA
# found CPU-path segfaults from OpenMP thread explosion — 9 worker threads ×
# FAISS/PyTorch/BLAS each spawning their own OpenMP team (× N CPU processes)
# oversubscribes cores and corrupts native state. Pin to a small fixed count so
# the per-process thread budget stays bounded regardless of co-located procs.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "2")
# The server's default PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:4 crashes CUDA
# init; clear it unless the operator set a valid value (>20).
_alloc = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
if "max_split_size_mb:" in _alloc:
    try:
        if int(_alloc.split("max_split_size_mb:")[1].split(",")[0]) < 21:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""
    except (ValueError, IndexError):
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""

# ── Hang watchdog (root-cause instrumentation for the case_18 runaway) ────────
# A CPU-bound non-terminating loop in one worker thread pegs a core and stalls
# the whole process (the stuck future never resolves). faulthandler periodically
# dumps EVERY thread's stack to a file, so a recurrence reveals the spinning
# frame. Diagnostics only — no behavioural change. Tunable via env.
import faulthandler as _faulthandler
_WATCHDOG_SECS = int(os.environ.get("TREE_DX_WATCHDOG_SECS", "900"))
if _WATCHDOG_SECS > 0:
    _wd_path = os.environ.get(
        "TREE_DX_WATCHDOG_FILE",
        str(PROJECT_ROOT / "logs" / f"hang_watchdog_{os.getpid()}.txt"),
    )
    try:
        _wd_fh = open(_wd_path, "w")
        _faulthandler.enable(file=_wd_fh)
        # repeat=True → re-dump every interval while still alive (a healthy run
        # exits well before the first dump, so normal runs emit nothing).
        _faulthandler.dump_traceback_later(_WATCHDOG_SECS, repeat=True, file=_wd_fh)
    except Exception:
        pass

TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")
DATA = PROJECT_ROOT / "data"

DIAGNOSIS_CUES = (
    "most likely diagnosis", "most likely cause", "most likely underlying",
    "which of the following is the most likely", "best explains",
    "most consistent with", "underlying diagnosis", "responsible for",
    "most likely responsible", "best describes",
)
IMAGE_CUES = ("figure", "shown in", "image", "photograph", "ecg as seen", "as shown")


def load_dx_cases() -> list[dict]:
    """All diagnosis-cue cases, de-duplicated, each tagged is_image."""
    cases, seen = [], set()
    with TSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                opts = ast.literal_eval(row["options"])
            except Exception:
                opts = {}
            q = row["question"].strip()
            if not opts or not any(cue in q.lower() for cue in DIAGNOSIS_CUES):
                continue
            key = q[:120]
            if key in seen:
                continue
            seen.add(key)
            cases.append({
                "q": q, "options": opts,
                "answer_idx": row.get("answer_idx", "").strip(),
                "answer": row.get("answer", "").strip(),
                "is_image": any(c in q.lower() for c in IMAGE_CUES),
            })
    return cases


def build_case_text(c: dict) -> str:
    opt_lines = "\n".join(f"{k}. {v}" for k, v in sorted(c["options"].items()))
    return f"{c['q']}\n\nOptions:\n{opt_lines}\n"


class ThreadLocalEnv:
    """One shared env object; each worker thread sees its own case via TLS."""

    def __init__(self):
        self._local = threading.local()

    def set_case(self, text):
        self._local.case = text

    def get_case_summary(self):
        return self._local.case

    def root_changed_materially(self, state):
        return False

    def patient_still_unstable(self):
        return False

    def ingest_external_context(self, ctx):
        pass

    def take_emergent_action(self, action):
        pass


def _bump_http_pool(workers: int):
    """Enlarge the OpenRouter session connection pool for high concurrency."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from agentclinic_tree_dx import llm_client
    adapter = HTTPAdapter(
        max_retries=Retry(total=5, backoff_factor=2,
                          status_forcelist=[429, 500, 502, 503, 504],
                          allowed_methods=["POST"], raise_on_status=False),
        pool_connections=max(12, workers + 4),
        pool_maxsize=max(20, workers * 2),
    )
    llm_client._openrouter_session.mount("https://", adapter)
    llm_client._openrouter_session.mount("http://", adapter)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=10,
                    help="thread pool size; with --case-timeout, auto-raised to "
                         "len(cases) so every case starts concurrently")
    ap.add_argument("--case-timeout", dest="case_timeout", type=float, default=0.0,
                    help="PER-CASE wall-clock cap in seconds (0 = none). Cases run "
                         "concurrently, so this also bounds the whole repeat; a case "
                         "exceeding it is recorded status=TIMEOUT (no rigid 9-question "
                         "repeat limit). Suggested: 2x observed max single-case dt.")
    ap.add_argument("--limit", type=int, default=0, help="0 = all dx cases")
    ap.add_argument("--cases", default="", help="comma-separated case indices to rerun (subset)")
    # Backbone: qwen3-32b has higher base capability but underperformed in prior
    # runs (protocol/token-window issues, §conversation_export); temporarily
    # reverted to the known-stable llama-3.3-70b until qwen3 is re-validated.
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    # Experiment toggles (default = P0-fixed config: age prior ON, rule-out ON
    # with present-path-first + Sp gate, RAG LRs cannot override the LLM).
    ap.add_argument("--age-prior", dest="age_prior", action="store_true", default=True)
    ap.add_argument("--no-age-prior", dest="age_prior", action="store_false")
    ap.add_argument("--rag-override", dest="rag_override", action="store_true", default=False,
                    help="allow RAG-derived LRs to override the LLM direction (unsafe; for ablation)")
    ap.add_argument("--ruleout-present-first", dest="ruleout_present_first",
                    action="store_true", default=True)
    ap.add_argument("--no-ruleout-present-first", dest="ruleout_present_first",
                    action="store_false")
    ap.add_argument("--ruleout-min-sp", dest="ruleout_min_sp", type=float, default=0.0,
                    help="P1 specificity gate for LR- rule-out (0 = off)")
    ap.add_argument("--ruleout", dest="ruleout", action="store_true", default=True)
    ap.add_argument("--no-ruleout", dest="ruleout", action="store_false",
                    help="disable the LR- normal-value rule-out channel entirely")
    ap.add_argument("--temp", type=float, default=None,
                    help="decoding temperature (0.0 = deterministic; default provider 1.0)")
    ap.add_argument("--tag", default="", help="label prefix for log/json filenames")
    ap.add_argument(
        "--talp-disc-profile",
        choices=("off", "p5_headline", "g2ur"),
        default="p5_headline",
        help="TALP discrimination evidence profile (production default: p5_headline)",
    )
    ap.add_argument(
        "--talp-disc-research-claims",
        default=str(DATA / "cceg" / "unary_v1" / "claims.research_validated.jsonl"),
        help="G2UR research-validated unary claims JSONL",
    )
    ap.add_argument(
        "--talp-disc-research-manifest",
        default=str(DATA / "cceg" / "unary_v1"
                    / "p5kg_research_asset_manifest_v2.json"),
        help="G2UR immutable research asset manifest",
    )
    ap.add_argument(
        "--talp-disc-p5-manifest",
        default=str(DATA / "eval" / "p5_external_asset_manifest.json"),
        help="P5 immutable legacy evidence asset manifest",
    )
    ap.add_argument(
        "--talp-disc-cache-path", default=None,
        help="optional precompiled discrimination cache path",
    )
    ap.add_argument(
        "--talp-disc-audit-path", default=None,
        help="optional per-injection discrimination audit JSONL",
    )
    ap.add_argument(
        "--talp-disc-verify-assets", action="store_true", default=False,
        help="verify manifest asset sizes and SHA-256 at startup",
    )
    # §21.8 fixes
    ap.add_argument("--fix-a", dest="fix_a", action="store_true", default=False,
                    help="§21.8a: use branch representative_diseases for KB/LR lookup")
    ap.add_argument("--fix-b", dest="fix_b", action="store_true", default=False,
                    help="§21.8b: pivotal-clue anti-anchoring hint into annotator")
    # §22 corrected fixes
    ap.add_argument("--fix-a2", dest="fix_a2", action="store_true", default=False,
                    help="§22.2 (A′): taxonomy-derived representative entities (NON-prompt)")
    ap.add_argument("--branch-knowledge", dest="branch_knowledge", action="store_true",
                    default=False,
                    help="§23.14 (Mode A): KB-anchored axis/level-aware branch generation "
                         "(deterministic L1 domain partition via syndrome_axis_map.json)")
    ap.add_argument("--retrieval-priority", dest="retrieval_priority", action="store_true",
                    default=False,
                    help="§25.2(#1): HPO-exact concept match outranks sub-threshold fuzzy "
                         "token hit in LRRetriever.lookup_fuzzy")
    ap.add_argument("--match-guards", dest="match_guards", action="store_true",
                    default=False,
                    help="§25.2(#2): finding-match guards — reject negation/laterality "
                         "conflicts, raise pure-token bar to 0.5, downweight subset rule")
    ap.add_argument("--confidence-cascade", dest="confidence_cascade", action="store_true",
                    default=False,
                    help="§25.2(#3): low-confidence cache hit (subsumption/context-only) "
                         "no longer short-circuits RAG; RAG may override with numeric LR")
    ap.add_argument("--lr-detox", dest="lr_detox", action="store_true", default=False,
                    help="§26.5(1): use detoxed secondary cache + neutralise fabricated "
                         "strong-exclusion LRs (demographic dropped, default-Sp clamped)")
    ap.add_argument("--lr-clean", dest="lr_clean", action="store_true", default=False,
                    help="§27.6(1): use purified secondary cache (*.clean.json) + strip "
                         "ungrounded heuristic LR to context-only at live RAG (stricter "
                         "than --lr-detox; clean wins if both set)")
    ap.add_argument("--mandatory-kb-branches", dest="mandatory_kb_branches",
                    action="store_true", default=False,
                    help="§26.5(3): inject any omitted KB mandatory_coverage L1 domain "
                         "as a deterministic branch (requires --branch-knowledge)")
    ap.add_argument("--phase-subaxis", dest="phase_subaxis", action="store_true",
                    default=False,
                    help="§26.5(4): split syndrome-axis domains with opposite-direction "
                         "phase variants (requires --branch-knowledge)")
    ap.add_argument("--union-axis-ac", dest="union_axis_ac", action="store_true",
                    default=False,
                    help="§31.13.18: A∪C union axis map — LLM-built branch_knowledge "
                         "cache ∪ curated mandatory-floor seeds (hand-map syndrome "
                         "detection + fallback). Recommended automation mode; iso-eval "
                         "100%% coverage / 0 axis error. Requires --branch-knowledge")
    ap.add_argument("--branch-llm-axis-live", dest="branch_llm_axis_live",
                    action="store_true", default=False,
                    help="§31.13.18: when a syndrome is missing from the A-cache, "
                         "generate its branch_knowledge LIVE via the LLM (write-"
                         "through). Default off (cache ∪ seeds ∪ hand fallback only)")
    ap.add_argument("--no-secondary-cache", dest="no_secondary_cache",
                    action="store_true", default=False,
                    help="§30: disable the tier-2 RAG-LR cache — recompute every "
                         "RAG LR from raw data (no stale cross-generation entries, "
                         "no cross-process write contention)")
    ap.add_argument("--cache-namespace", dest="cache_namespace", default="",
                    help="§30: per-experiment cache isolation key (e.g. the arm "
                         "name). Each namespace gets its own writable tier-2 cache "
                         "(.ns_<NS>.json) so arms are independent and only reps of "
                         "the SAME arm share. Empty = shared production cache.")
    ap.add_argument("--resume", dest="resume", action="store_true", default=False,
                    help="§30: per-CASE resume — carry over already-scored (OK/XX) "
                         "cases from the newest prior JSON of this --tag and only "
                         "re-run unscored/contaminated (PROTO/ERR/TIMEOUT/NOANS/"
                         "missing) cases; preserves correct outputs instead of "
                         "re-running the whole 9.")
    args = ap.parse_args()

    _bump_http_pool(args.workers)

    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController, LLMProtocolError
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    from agentclinic_tree_dx.state import DiagnosticState

    config = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        max_turn_budget=5,
        min_readiness_to_commit=0.70,
        allow_external_knowledge=True,
        talp_disc_profile=args.talp_disc_profile,
        talp_disc_research_claims=args.talp_disc_research_claims,
        talp_disc_research_manifest=args.talp_disc_research_manifest,
        talp_disc_p5_manifest=args.talp_disc_p5_manifest,
        talp_disc_cache_path=args.talp_disc_cache_path,
        talp_disc_audit_path=args.talp_disc_audit_path,
        talp_disc_verify_manifest_assets=args.talp_disc_verify_assets,
        dxs_common_json=str(DATA / "knowledge_raw" / "Guideline_common.json"),
        dxs_rare_json=str(DATA / "knowledge_raw" / "Guideline_rare.json"),
        primekg_csv=str(DATA / "knowledge_raw" / "kg.csv"),
        lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
        doclogica_cache_json=str(DATA / "knowledge_raw" / "doclogica_cache.json"),
        pathognomonic_markers_json=str(DATA / "knowledge_raw" / "pathognomonic_markers.json"),
        auto_ambiguity_map_json=str(DATA / "knowledge_raw" / "auto_ambiguity_map.json"),
        # B1: numeric lab/vital → HPO normalizer (value-direction aware). Without
        # these paths the FindingNormalizer is never constructed (was dormant).
        lab_reference_ranges_json=str(DATA / "knowledge_raw" / "lab_reference_ranges.json"),
        loinc2hpo_json=str(DATA / "knowledge_raw" / "loinc2hpo_annotations.json"),
        unit_conversions_json=str(DATA / "knowledge_raw" / "unit_conversions.json"),
        # SNOMED CT synonym bridge (built by build_snomed_knowledge.py)
        snomed_concepts_json=str(DATA / "knowledge_raw" / "snomed_concepts.json"),
        snomed_term_index_json=str(DATA / "knowledge_raw" / "snomed_term_index.json"),
        snomed_relations_json=str(DATA / "knowledge_raw" / "snomed_relations.json"),
        enable_knowledge_injection=True,
        enable_lr_rag_fallback=True,
        # LR- rule-out channel: normal lab/vital values argue against diseases
        # that (near-)always produce the negated abnormality (gated, high-Sn).
        enable_normal_value_ruleout=args.ruleout,
        # Structured age/sex → incidence prior (epidemiology shifts the prior).
        enable_age_prior=args.age_prior,
        age_sex_incidence_json=str(DATA / "knowledge_raw" / "age_sex_incidence.json"),
        # P0: RAG-derived LRs inform the prompt but cannot override the LLM.
        rag_lr_can_override_direction=args.rag_override,
        # P1/P2: rule-out safety refinements.
        ruleout_require_present_path_silent=args.ruleout_present_first,
        ruleout_min_specificity=args.ruleout_min_sp,
        # §21.8 fixes (branch representative-disease KB lookup; anti-anchoring).
        enable_representative_disease_lr=args.fix_a,
        enable_taxonomy_entities=args.fix_a2,
        enable_anti_anchoring=args.fix_b,
        enable_branch_knowledge=args.branch_knowledge,
        enable_hpo_exact_priority=args.retrieval_priority,
        enable_finding_match_guards=args.match_guards,
        enable_confidence_gated_cascade=args.confidence_cascade,
        enable_lr_detox=args.lr_detox,
        enable_lr_clean=args.lr_clean,
        enable_secondary_lr_cache=not args.no_secondary_cache,
        secondary_lr_cache_namespace=args.cache_namespace,
        enable_mandatory_kb_branches=args.mandatory_kb_branches,
        enable_phase_subaxis=args.phase_subaxis,
        # §31.13.18: A∪C union axis map (cache ∪ curated seeds; hand fallback).
        union_axis_ac=args.union_axis_ac,
        branch_llm_axis_live=args.branch_llm_axis_live,
        override_seeds_json=str(DATA / "knowledge_raw" / "syndrome_override_seeds.json"),
        llm_axis_cache_json=str(DATA / "knowledge_raw" / "auto_axis_cache.json"),
        enable_chain_discoverer=True,
        max_knowledge_prompt_lines=40,
        rag_index_dir=str(DATA / "corpus" / "rag_index"),
        enable_pubmed_fallback=False,
        use_dual_channel_bundler=True,
        max_protocol_retries=2,
    )

    # call_timeout 240s: qwen3-32b is a reasoning model; under 10-way concurrency
    # complex PostUpdateStateReviser/Annotator calls often need 180-240s. A 180s
    # ceiling guaranteed timeout→retry (same cost) → multi-hour stalls. 240s lets
    # them finish on attempt 1; timeout_retry_cap=2 stops runaway when truly stuck.
    llm = RobustLLMClient(model=args.model, call_timeout=240, max_retries=5,
                          timeout_retry_cap=2, temperature=args.temp)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _tag = f"{args.tag}_" if args.tag else ""
    log_path = str(PROJECT_ROOT / "logs" / f"medbullets_conc_{_tag}{stamp}.log")
    json_path = str(PROJECT_ROOT / "logs" / f"medbullets_conc_{_tag}{stamp}.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    llm.configure_logging(log_path)

    # ── Per-case logging ──────────────────────────────────────────────────────
    # One log file per question. Both the LLM module I/O (via the thread-local
    # path set in run_one) and the controller/F1-F4 INFO logs are routed to the
    # SAME per-case file so the whole reasoning timeline is in one place.
    # configure_logging() only handles LLM I/O and never touched the Python
    # logging module, so controller INFO logs were previously dropped entirely.
    import logging as _logging
    from agentclinic_tree_dx.llm_client import get_thread_log_path, set_thread_log_path

    per_case_dir = log_path[:-4] + "_cases" if log_path.endswith(".log") else log_path + "_cases"
    os.makedirs(per_case_dir, exist_ok=True)
    setup_log_path = os.path.join(per_case_dir, "_setup.log")

    # §30: STABLE (tag-keyed, NOT timestamped) per-case RESULT sidecar dir. Each
    # case's record is persisted here the instant it finishes, so a mid-run
    # segfault (which writes no final JSON) never wastes already-produced
    # answers — `--resume` reads these sidecars and re-runs only the missing
    # cases. Keyed by the full tag (incl. rep) so reps stay independent.
    _stable = (args.tag or stamp)
    case_results_dir = str(PROJECT_ROOT / "logs" / "_case_results" / _stable)
    os.makedirs(case_results_dir, exist_ok=True)

    class PerCaseLogHandler(_logging.Handler):
        """Route each record to the calling thread's per-case file (falls back to
        the setup log for records emitted outside any case, e.g. warmup)."""

        def emit(self, record):
            try:
                path = get_thread_log_path() or setup_log_path
                with open(path, "a", encoding="utf-8") as f:
                    f.write(self.format(record) + "\n")
            except Exception:
                pass

    _pch = PerCaseLogHandler()
    _pch.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    for _lname in ("agentclinic_tree_dx.controller",
                   "agentclinic_tree_dx.updater",
                   "agentclinic_tree_dx.update_router"):
        _lg = _logging.getLogger(_lname)
        _lg.setLevel(_logging.INFO)
        _lg.addHandler(_pch)
        _lg.propagate = False

    env = ThreadLocalEnv()
    controller = AgentClinicTreeController(env=env, llm=llm, config=config)

    # Warm up lazy encoders (embedding + RAG) single-threaded to avoid races.
    try:
        controller._knowledge_retriever.format_discriminator_hints_for_prompt(
            ["chronic myeloid leukemia", "acute myeloid leukemia"],
            seen_evidence=[], max_lines=5, vignette_text="warmup", include_chains=False)
    except Exception as e:
        print(f"[warmup] {e}")

    all_cases = load_dx_cases()
    if args.cases:
        want = {int(x) for x in args.cases.split(",") if x.strip()}
        selected = [(i, c) for i, c in enumerate(all_cases) if i in want]
    elif args.limit:
        selected = list(enumerate(all_cases))[:args.limit]
    else:
        selected = list(enumerate(all_cases))
    # §30 per-CASE resume: carry over already-scored (OK/XX) cases from the
    # newest prior JSON of this tag; only re-run unscored/contaminated ones. This
    # preserves correct outputs instead of re-running the whole 9 — only
    # PROTO/ERR/TIMEOUT/NOANS/missing cases are recomputed.
    carried: dict[int, dict] = {}
    if getattr(args, "resume", False):
        import glob as _glob
        want_idx = {i for i, _ in selected}
        prev: dict[int, dict] = {}
        # (1) primary source: crash-proof per-case sidecars (survive a segfault
        # that never wrote a final JSON) — keyed by the SAME stable tag.
        for sf in _glob.glob(os.path.join(case_results_dir, "case_*.json")):
            try:
                r = json.load(open(sf, encoding="utf-8"))
                if r.get("idx") is not None:
                    prev[r["idx"]] = r
            except Exception:
                pass
        # (2) fallback: newest final JSON of this tag (older runs w/o sidecars).
        if _tag:
            finals = sorted(_glob.glob(str(PROJECT_ROOT / "logs" / f"medbullets_conc_{_tag}*.json")),
                            key=os.path.getmtime, reverse=True)
            if finals:
                try:
                    for r in json.load(open(finals[0], encoding="utf-8")):
                        prev.setdefault(r.get("idx"), r)
                except Exception:
                    pass
        for i in want_idx:
            r = prev.get(i)
            if r and r.get("status") in ("OK", "XX"):
                carried[i] = r
        if carried:
            selected = [(i, c) for i, c in selected if i not in carried]
            print(f"[resume] carried over {len(carried)} scored case(s) "
                  f"(sidecars+final); re-running {len(selected)}")

    n_img = sum(c["is_image"] for _, c in selected)
    print("=" * 80)
    print(f"CONCURRENT PIPELINE EVAL — {len(selected)} dx cases "
          f"({len(selected)-n_img} text-only, {n_img} image-dependent)"
          + (f"  [rerun subset: {sorted(i for i,_ in selected)}]" if args.cases else ""))
    _eff_workers = max(args.workers, len(selected)) if (args.case_timeout or 0) > 0 else args.workers
    print(f"  model={args.model}  workers={args.workers}"
          + (f" (→{_eff_workers} all-concurrent)" if _eff_workers != args.workers else "")
          + f"  case_timeout={args.case_timeout or 0:.0f}s  injection=ON  "
          f"protocol_retries={config.max_protocol_retries}  temp={args.temp}")
    print(f"  CFG tag={args.tag!r} age_prior={args.age_prior} rag_override={args.rag_override} "
          f"ruleout={args.ruleout} present_first={args.ruleout_present_first} "
          f"ruleout_min_sp={args.ruleout_min_sp} fixA={args.fix_a} fixA2={args.fix_a2} fixB={args.fix_b} branchKB={args.branch_knowledge} "
          f"retrievalPriority={args.retrieval_priority} matchGuards={args.match_guards} "
          f"confCascade={args.confidence_cascade} lrDetox={args.lr_detox} "
          f"lrClean={args.lr_clean} "
          f"mandKBbranch={args.mandatory_kb_branches} phaseSubaxis={args.phase_subaxis} "
          f"unionAxisAC={args.union_axis_ac} llmAxisLive={args.branch_llm_axis_live}")
    print(f"  log={log_path}")
    print("=" * 80, flush=True)

    lock = threading.Lock()
    results: dict[int, dict] = dict(carried)  # §30: seed with resumed scored cases

    def run_one(i: int, c: dict):
        case_log = os.path.join(per_case_dir, f"case_{i:02d}.log")
        set_thread_log_path(case_log)
        try:
            with open(case_log, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write(f"CASE {i}  gold={c['answer_idx']}  answer={c['answer']}  "
                        f"is_image={c['is_image']}\n")
                f.write("=" * 80 + "\n")
                f.write(build_case_text(c) + "\n")
                f.write("=" * 80 + "\n\n")
        except Exception:
            pass
        env.set_case(build_case_text(c))
        state = DiagnosticState(case_id=f"MB_{i}")
        t0 = time.time()
        rec = {"idx": i, "gold": c["answer_idx"], "is_image": c["is_image"],
               "answer": c["answer"], "pred": "?", "status": "ERR", "error": ""}
        try:
            res = controller.run(state)
            fa = (res.get("final_answer", "") or "").strip().upper()
            rec["pred"] = fa[0] if fa else "?"
            # §30: surface recovered program faults — a scored answer that came
            # from a degraded (program-fault) process is explicitly flagged
            # low-trust so it is never silently treated as a clean result.
            faults = res.get("internal_faults") or []
            if faults:
                rec["degraded"] = True
                rec["faults"] = faults
            # §30 count-integrity guard: only a VALID option letter may be scored
            # OK/XX. A run that completes without producing a real choice (pred
            # not in A–E) is a NO-ANSWER program outcome, NOT a wrong diagnosis —
            # status NOANS keeps it out of the accuracy denominator (acc() counts
            # only OK/XX) so program failures never inflate the "wrong" count.
            if rec["pred"] not in ("A", "B", "C", "D", "E"):
                rec["status"] = "NOANS"
                rec["error"] = "no valid option letter in final_answer"
            else:
                rec["status"] = "OK" if rec["pred"] == c["answer_idx"].upper() else "XX"
        except LLMProtocolError as e:
            rec["status"] = "PROTO"
            rec["error"] = f"{e.module_name}: {e.reason}"
        except Exception as e:
            rec["status"] = "ERR"
            rec["error"] = f"{type(e).__name__}: {e}"
        finally:
            set_thread_log_path(None)
        rec["dt"] = round(time.time() - t0, 1)
        # §30: persist this case's result immediately (crash-proof checkpoint).
        try:
            with open(os.path.join(case_results_dir, f"case_{i:02d}.json"),
                      "w", encoding="utf-8") as _sf:
                json.dump(rec, _sf, ensure_ascii=False)
        except Exception:
            pass
        with lock:
            results[i] = rec
            tag = "IMG" if c["is_image"] else "txt"
            print(f"[{rec['status']:<5}] case {i:<3} gold={rec['gold']} pred={rec['pred']} "
                  f"({tag},{rec['dt']:.0f}s) {c['answer'][:34]}"
                  f"{'  [DEGRADED/low-trust]' if rec.get('degraded') else ''}"
                  f"{('  '+rec['error']) if rec['error'] else ''}", flush=True)

    # §26.6: when a PER-CASE timeout is set, launch ALL cases concurrently
    # (workers ≥ #cases) and bound each by a single wall deadline. Because the
    # cases start together, "case_timeout seconds after start" is an effective
    # per-case cap, and the repeat is naturally bounded by the slowest case —
    # NO rigid per-repeat (9-question) limit. A case still running at the
    # deadline is recorded TIMEOUT; its (un-killable) thread is abandoned at
    # process exit. OpenRouter tolerates high concurrency (~40), so all 9 + many
    # repeats in parallel is fine.
    case_to = float(getattr(args, "case_timeout", 0.0) or 0.0)
    n_workers = max(args.workers, len(selected)) if case_to > 0 else args.workers
    abandoned = 0
    ex = ThreadPoolExecutor(max_workers=n_workers)
    fut_to_idx = {ex.submit(run_one, i, c): i for i, c in selected}
    if case_to > 0:
        done, not_done = futures_wait(list(fut_to_idx), timeout=case_to)
        abandoned = len(not_done)
        for fut in not_done:
            i = fut_to_idx[fut]
            if i not in results:
                with lock:
                    results[i] = {
                        "idx": i, "gold": "?", "is_image": False, "answer": "",
                        "pred": "?", "status": "TIMEOUT",
                        "error": f"per-case timeout {case_to:.0f}s", "dt": case_to,
                    }
                print(f"[TIMEOUT] case {i:<3} exceeded {case_to:.0f}s — abandoned",
                      flush=True)
        ex.shutdown(wait=False)
    else:
        for _ in as_completed(list(fut_to_idx)):
            pass
        ex.shutdown(wait=True)

    ordered = [results[i] for i in sorted(results)]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)

    def acc(subset):
        scored = [r for r in subset if r["status"] in ("OK", "XX")]
        ok = sum(r["status"] == "OK" for r in scored)
        return ok, len(scored), (ok / len(scored) if scored else 0.0)

    allr = ordered
    txt = [r for r in ordered if not r["is_image"]]
    proto = sum(r["status"] == "PROTO" for r in allr)
    err = sum(r["status"] == "ERR" for r in allr)
    tmo = sum(r["status"] == "TIMEOUT" for r in allr)
    noans = sum(r["status"] == "NOANS" for r in allr)
    degraded = sum(1 for r in allr if r.get("degraded"))

    print("\n" + "=" * 80)
    print("RESULTS (two口径)")
    print("=" * 80)
    ok_f, n_f, a_f = acc(allr)
    ok_t, n_t, a_t = acc(txt)
    print(f"  全量    (full):     {ok_f}/{n_f} = {a_f:.1%}   "
          f"(scored cases; {len(allr)-n_f} unscored)")
    print(f"  不含图像(no-image): {ok_t}/{n_t} = {a_t:.1%}")
    print(f"  protocol failures (skipped): {proto}   runtime errors: {err}   "
          f"timeouts: {tmo}   no-answer: {noans}   degraded/low-trust(scored): {degraded}")
    print(f"  results JSON: {json_path}")
    sys.stdout.flush()
    sys.stderr.flush()
    if abandoned > 0:
        # Worker threads are non-daemon; a timed-out case's thread is still blocked
        # on its (un-killable) LLM HTTP call and would hang interpreter shutdown.
        # JSON is already written, so hard-exit to honour the per-case cap.
        os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
