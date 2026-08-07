"""Branch-creation-ONLY production verification on the hard medbullets diagnosis
cases (§RESIDUAL_MISS C-table landing + B-table on).

Runs the REAL production controller but stops right after Level-1 branch creation
(select_root → create_branches) — no leaf planning, no evidence loop — and checks
the single property that matters at this stage: L1 NO-MISS (does a generated
Level-1 branch cover the gold diagnosis?). This isolates branch-generation quality
from the downstream reasoning the user is separately debugging.

Config under test (the landed improvements):
  * backbone = llama-3.3-70b (qwen3 temporarily reverted; see --model)
  * B-table ON: enable_case_report_branch_source + enable_cpg_branch_source
    + enable_llm_ddx_branch_entrance (4-entrance dual recall), branch_knowledge ON
  * salient_finding_entrance_weight = 0.5 (D-fusion default)
  * CPG branch source points at the rebuilt data/corpus/cpg_index (D-data Merck fix)
  * branch_creator.txt now carries the single-fundamentum-divisionis MECE rule

Coverage is judged by an LLM (same backbone): assign the gold disease to exactly
one generated family branch, or -1 if none fits. A hit on a NON-residual branch =
clean L1 coverage; a hit only on OTHER/residual = weak (reachable but unstructured);
-1 = MISS.

    PYTHONPATH=src python scripts/eval_branch_creation_medbullets.py [--limit N] [--include-image]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "2")

DATA = PROJECT_ROOT / "data"

# reuse the case loader / text builder / env from the full-pipeline harness
_spec = importlib.util.spec_from_file_location(
    "mb", PROJECT_ROOT / "scripts" / "eval_pipeline_medbullets.py")
_mb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mb)


def _residual(label: str) -> bool:
    lab = (label or "").lower()
    return ("other" in lab and ("less" in lab or "common" in lab or "unclass" in lab)) \
        or lab.strip() in {"other", "miscellaneous", "residual"}


def make_judge(model: str):
    import requests
    from agentclinic_tree_dx import llm_client
    sess = llm_client._openrouter_session
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
        "OPENROUTER_API_KEY2",
        "")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _json_of(txt: str) -> dict:
        depth = start = 0
        for i, ch in enumerate(txt):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(txt[start:i + 1])
                    except Exception:
                        continue
        return {}

    def assign(gold: str, labels: list[str]) -> int:
        numbered = "\n".join(f"{i}: {a}" for i, a in enumerate(labels))
        sysp = ("Assign the given specific diagnosis to the SINGLE best-fitting "
                "first-level family from the numbered list, by mechanism/category "
                "membership (NOT wording). If NONE fits, answer -1. Return STRICT "
                'JSON: {"index": <int>}.')
        for attempt in range(4):
            try:
                r = sess.post("https://openrouter.ai/api/v1/chat/completions",
                              headers=headers,
                              json={"model": model, "temperature": 0.0,
                                    "messages": [
                                        {"role": "system", "content": sysp},
                                        {"role": "user", "content":
                                         f"Diagnosis: {gold}\nFamilies:\n{numbered}"}]},
                              timeout=90)
                obj = _json_of(r.json()["choices"][0]["message"]["content"])
                return int(obj.get("index", -1))
            except Exception:
                time.sleep(2 * (attempt + 1))
        return -1
    return assign


# Branch-mode → which axis/domain source feeds the KB anchoring. This is the
# manual-curation-dependency axis of the audit:
#   handmap      : hand-curated syndrome_axis_map.json (+ B-table entrances)   [MANUAL]
#   auto_kb      : KB-derived axis (SNOMED attrs + LR cache) — no hand map     [SCALABLE, coupled]
#   pure_llm     : NO axis map at all; the single-axis LLM prompt does L1 alone [SCALABLE, no KB]
#   recall_hints : §32 DECOUPLED — LLM owns the partition, 4-entrance recall is
#                  passed as flat candidate_diseases hints (no partition/proj)  [SCALABLE, +KB recall]
def build_controller(
    model: str,
    branch_mode: str = "handmap",
    config_overrides: dict | None = None,
):
    """Build the production branch controller.

    ``config_overrides`` is reserved for harnesses that need to exercise the
    same production configuration under bounded execution controls.  The
    historical CLI passes no overrides and is therefore unchanged.
    """
    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    kb_on = branch_mode not in ("pure_llm",)
    cfg = dict(
        execution_mode="static_diagnosis_qa",
        max_turn_budget=5,
        allow_external_knowledge=True,
        dxs_common_json=str(DATA / "knowledge_raw" / "Guideline_common.json"),
        dxs_rare_json=str(DATA / "knowledge_raw" / "Guideline_rare.json"),
        primekg_csv=str(DATA / "knowledge_raw" / "kg.csv"),
        lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
        pathognomonic_markers_json=str(DATA / "knowledge_raw" / "pathognomonic_markers.json"),
        snomed_concepts_json=str(DATA / "knowledge_raw" / "snomed_concepts.json"),
        snomed_term_index_json=str(DATA / "knowledge_raw" / "snomed_term_index.json"),
        snomed_relations_json=str(DATA / "knowledge_raw" / "snomed_relations.json"),
        enable_knowledge_injection=True,
        # ── Branch-generation config under verification ──────────────────────
        enable_branch_knowledge=kb_on,
        enable_case_report_branch_source=kb_on,   # B-table
        enable_cpg_branch_source=kb_on,           # B-table
        enable_llm_ddx_branch_entrance=kb_on,     # B-table (LLM 4th entrance)
        salient_finding_entrance_weight=0.5,      # D-fusion default
        case_report_index_dir=str(DATA / "corpus" / "case_report_index"),
        # Point the CPG branch source at the rebuilt index (D-data Merck fix).
        rag_index_dir=str(DATA / "corpus" / "cpg_index"),
        max_knowledge_prompt_lines=40,
        max_protocol_retries=2,
    )
    if branch_mode == "auto_kb":
        # Scalable: derive the axis/domain partition from SNOMED + LR cache; the
        # hand map is NOT consulted (auto_axis_kb short-circuits before it).
        cfg["auto_axis_kb"] = True
    elif branch_mode == "recall_hints":
        # §32 DECOUPLED: LLM owns the partition; entrances → flat hint list.
        cfg["branch_kb_recall_hints"] = True
    elif branch_mode == "recall_hints_gap":
        # §32 + Phase-B: recall-hints PLUS gap-fill repair re-call.
        cfg["branch_kb_recall_hints"] = True
        cfg["branch_recall_gap_fill"] = True
    # handmap: leave auto flags off → SyndromeAxisMap.from_file(syndrome_axis_map.json)
    if config_overrides:
        cfg.update(config_overrides)
    config = ControllerConfig(**cfg)
    llm = RobustLLMClient(model=model, call_timeout=240, max_retries=5,
                          timeout_retry_cap=2)
    env = _mb.ThreadLocalEnv()
    controller = AgentClinicTreeController(env=env, llm=llm, config=config)

    # Instrument: record, per case, the axis-map provenance of the branch
    # anchoring (was the hand-curated map actually load-bearing?).
    prov = {"last": None}
    orig = controller._build_branch_candidates

    def _wrapped(state):
        bk = orig(state)
        if bk is None:
            prov["last"] = {"built": False, "syndrome": None}
        elif bk.get("recall_hints_mode"):
            prov["last"] = {"built": True, "mode": "recall_hints",
                            "syndrome": bk.get("syndrome_matched", ""),
                            "n_entrances": bk.get("n_entrances", 0),
                            "n_hints": len(bk.get("candidate_diseases", [])),
                            "hints": bk.get("candidate_diseases", [])[:12]}
        else:
            prov["last"] = {"built": True, "mode": "coupled",
                            "syndrome": bk.get("syndrome_matched", ""),
                            "axis": bk.get("l1_classification_axis", ""),
                            "domains": bk.get("mandatory_coverage", []),
                            "cr": bk.get("case_report_entities_added", 0),
                            "cpg": bk.get("cpg_entities_added", 0),
                            "llm": bk.get("llm_ddx_entities_added", 0)}
        return bk
    controller._build_branch_candidates = _wrapped
    return controller, env, config, prov


def run_case_branches(
    controller,
    env,
    case_text: str,
    *,
    parse_vignette: bool = True,
    prepare_state=None,
):
    """Execute ONLY select_root → create_branches (production code paths).

    parse_vignette=False skips the live VignetteParser call so callers can
    inject a frozen evidence catalog (DiagnosisArena M01 path).

    prepare_state, if given, runs after case_summary is set and before
    select_root / create_branches — matching the 17-case order where evidence
    is present before BranchCreator (e.g. apply frozen VignetteParser fields).
    """
    from agentclinic_tree_dx.state import DiagnosticState
    env.set_case(case_text)
    state = DiagnosticState(case_id="MB_BC")
    state.timestep = 1
    state.max_turn_budget = controller.config.max_turn_budget
    state.case_summary = env.get_case_summary()
    if controller._in_static_qa_mode():
        if parse_vignette:
            controller.parse_static_vignette(state)
        state.mode_policy = {"benchmark_purity": True,
                             "allow_external_knowledge": controller.config.allow_external_knowledge}
    if prepare_state is not None:
        prepare_state(state)
    try:
        state.interrupt = controller.safety_screen(state)
    except Exception:
        pass
    state.root = controller.select_root(state)
    state.branches, state.frontier = controller.create_branches(state)
    return state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--limit", type=int, default=0, help="0 = all text-only dx cases")
    ap.add_argument("--include-image", action="store_true",
                    help="also run image-dependent cases (default: text-only)")
    ap.add_argument("--tag", default="branchgen")
    ap.add_argument("--branch-mode", default="handmap",
                    choices=["handmap", "auto_kb", "pure_llm", "recall_hints",
                             "recall_hints_gap"],
                    help="handmap (MANUAL) | auto_kb (KB coupled) | pure_llm (no KB) "
                         "| recall_hints (§32 decoupled: LLM partition + flat recall)")
    args = ap.parse_args()

    print(f"Loading production controller (model={args.model}, B-table ON, "
          f"single-axis prompt, weight=0.5, branch_mode={args.branch_mode}) ...")
    controller, env, config, prov = build_controller(args.model, args.branch_mode)
    judge = make_judge(args.model)

    all_cases = _mb.load_dx_cases()
    cases = [c for c in all_cases if args.include_image or not c["is_image"]]
    if args.limit:
        cases = cases[:args.limit]
    print(f"Branch-creation verification on {len(cases)} "
          f"{'(incl. image)' if args.include_image else 'text-only'} dx cases\n")

    rows, clean, reachable = [], 0, 0
    for i, c in enumerate(cases):
        gold = c["answer"].strip()
        t0 = time.time()
        try:
            state = run_case_branches(controller, env, _mb.build_case_text(c))
            branches = list(state.branches.values())
            labels = [b.label for b in branches]
            idx = judge(gold, labels) if labels else -1
            hit = 0 <= idx < len(labels)
            is_clean = hit and not _residual(labels[idx])
            reachable += int(hit)
            clean += int(is_clean)
            root_lbl = getattr(state.root, "label", "?")
            assigned = labels[idx] if hit else None
            status = "CLEAN" if is_clean else ("residual" if hit else "MISS")
            pv = dict(prov["last"] or {"built": False})
            rows.append({"idx": i, "gold": gold, "root": root_lbl,
                         "n_branches": len(labels), "labels": labels,
                         "assigned": assigned, "status": status,
                         "provenance": pv,
                         "dt": round(time.time() - t0, 1)})
            print(f"[{status:<8}] case {i:<2} root={str(root_lbl)[:34]:<36} "
                  f"#br={len(labels)} gold={gold[:30]}")
            print(f"           branches: {labels}")
            print(f"           branch_knowledge: {pv}")
            if hit:
                print(f"           gold → [{assigned}]")
        except Exception as e:
            rows.append({"idx": i, "gold": gold, "status": "ERR",
                         "error": f"{type(e).__name__}: {e}",
                         "dt": round(time.time() - t0, 1)})
            print(f"[ERR    ] case {i:<2} {type(e).__name__}: {str(e)[:100]}")

    n = len([r for r in rows if r["status"] != "ERR"])
    print("\n" + "=" * 72)
    print(f"BRANCH-CREATION L1 COVERAGE (n={n})")
    print(f"  clean coverage (gold in a NON-residual family): {clean}/{n}")
    print(f"  reachable (incl. residual OTHER):               {reachable}/{n}")
    errs = sum(r["status"] == "ERR" for r in rows)
    if errs:
        print(f"  errors: {errs}")
    out = PROJECT_ROOT / "logs" / f"branchgen_{args.tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"  detail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
