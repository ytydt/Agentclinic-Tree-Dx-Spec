"""§32 long-tail validation: does the recall-HINTS injection actually improve the
LLM's L1 partition COVERAGE on true long-tail (RareArena) cases?

`eval_llm_ddx_rarearena.py` already proved the 4-entrance UNION recalls the gold
family @20 more often than the LLM alone. What it did NOT test is the piece §32
adds: after we inject that recall as a FLAT hint list, does the LLM actually build
a partition whose Level-1 family COVERS the gold? This harness closes that loop.

Protocol (leakage-controlled, mirrors eval_llm_ddx_rarearena):
  * N RareArena cases with a gold ``diagnoses``; STRIP the gold tokens from the
    presentation so no arm can echo the name.
  * Case-report entrance uses LEAVE-ONE-OUT (drop the case's own report).
  * ONE controller, sources built once. select_root is run ONCE per case and the
    root REUSED for both arms (KB does not affect root selection → fair + cheap).
  * Two arms, differing ONLY in create_branches:
      - pure_llm     : branch_kb_recall_hints OFF, no axis map → pure LLM partition
      - recall_hints : branch_kb_recall_hints ON  → LLM partition + flat recall hints
  * Judge: assign the gold diagnosis to one generated family (or -1). CLEAN = gold
    in a NON-residual family; reachable = incl. residual OTHER; else MISS.

    PYTHONPATH=src python scripts/eval_recall_hints_rarearena.py --n 40
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
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "2")

DATA = PROJECT_ROOT / "data"

# reuse RareArena loader/strip/gold helpers + branch-creation judge/controller
_ra_spec = importlib.util.spec_from_file_location(
    "ra", PROJECT_ROOT / "scripts" / "eval_llm_ddx_rarearena.py")
_ra = importlib.util.module_from_spec(_ra_spec)
_ra_spec.loader.exec_module(_ra)
_bc_spec = importlib.util.spec_from_file_location(
    "bc", PROJECT_ROOT / "scripts" / "eval_branch_creation_medbullets.py")
_bc = importlib.util.module_from_spec(_bc_spec)
_bc_spec.loader.exec_module(_bc)


def _residual(label: str) -> bool:
    lab = (label or "").lower()
    return ("other" in lab and ("less" in lab or "common" in lab or "unclass" in lab)) \
        or lab.strip() in {"other", "miscellaneous", "residual"}


def build_controller(model: str):
    """recall_hints-capable controller: entrances ON + branch_kb_recall_hints ON,
    NO hand map / auto_kb (zero curation). Toggle config.branch_kb_recall_hints
    per arm; when OFF and no axis map is loaded, the branch path is pure LLM."""
    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    config = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        max_turn_budget=5,
        allow_external_knowledge=True,
        lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
        snomed_concepts_json=str(DATA / "knowledge_raw" / "snomed_concepts.json"),
        snomed_term_index_json=str(DATA / "knowledge_raw" / "snomed_term_index.json"),
        snomed_relations_json=str(DATA / "knowledge_raw" / "snomed_relations.json"),
        enable_knowledge_injection=True,
        enable_branch_knowledge=True,
        enable_case_report_branch_source=True,
        enable_cpg_branch_source=True,
        enable_llm_ddx_branch_entrance=True,
        branch_kb_recall_hints=True,
        salient_finding_entrance_weight=0.5,
        case_report_index_dir=str(DATA / "corpus" / "case_report_index"),
        rag_index_dir=str(DATA / "corpus" / "cpg_index"),
        max_knowledge_prompt_lines=40,
        max_protocol_retries=2,
    )
    llm = RobustLLMClient(model=model, call_timeout=240, max_retries=5,
                          timeout_retry_cap=2)
    env = _bc._mb.ThreadLocalEnv()
    controller = AgentClinicTreeController(env=env, llm=llm, config=config)
    return controller, env


def install_loo(controller):
    """Wrap the case-report source retriever so the current case's own report is
    excluded from every search (leakage control)."""
    src = getattr(controller, "_case_report_source", None)
    if src is None or getattr(src, "_r", None) is None:
        print("[WARN] no case-report source → LOO inactive (CR entrance leaks)")
        return {"exclude": None}
    retr = src._r
    orig = retr.search
    holder = {"exclude": None}

    def loo_search(q, **kw):
        hits = orig(q, **kw)
        ex = holder["exclude"]
        if ex is None:
            return hits
        return [h for h in hits
                if str(h.get("source_id") or "") != ex
                and str(h.get("article_id") or "") != ex]
    retr.search = loo_search
    return holder


def run_arm(controller, env, state_cls, case_text, recall_hints: bool, root):
    """create_branches under one arm, reusing the shared root."""
    controller.config.branch_kb_recall_hints = recall_hints
    env.set_case(case_text)
    st = state_cls(case_id="RA")
    st.timestep = 1
    st.max_turn_budget = controller.config.max_turn_budget
    st.case_summary = case_text
    if controller._in_static_qa_mode():
        st.mode_policy = {"benchmark_purity": True,
                          "allow_external_knowledge": True}
    st.root = root
    st.branches, st.frontier = controller.create_branches(st)
    return [b.label for b in st.branches.values()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tag", default="rh_ra")
    args = ap.parse_args()

    from agentclinic_tree_dx.state import DiagnosticState

    print(f"Loading recall_hints controller (model={args.model}) ...")
    controller, env = build_controller(args.model)
    holder = install_loo(controller)
    judge = _bc.make_judge(args.model)

    cases = _ra.load_rarearena(args.n, args.seed)
    print(f"RareArena LOO reachability A/B on {len(cases)} cases "
          f"(pure_llm vs recall_hints)\n")

    rows = []
    tot = {"pure_llm": {"clean": 0, "reach": 0},
           "recall_hints": {"clean": 0, "reach": 0}}
    n = 0
    for c in cases:
        dxs = c.get("diagnoses") or []
        if not dxs:
            continue
        gold = dxs[0]
        pres = c.get("presenting") or ""
        clean_text = _ra.strip_gold(pres, dxs)
        if len(clean_text) < 80:
            continue
        n += 1
        holder["exclude"] = "case_report__" + str(c["case_id"])
        env.set_case(clean_text)
        state = DiagnosticState(case_id="RA")
        state.timestep = 1
        state.max_turn_budget = controller.config.max_turn_budget
        state.case_summary = clean_text
        try:
            root = controller.select_root(state)
        except Exception as e:  # noqa: BLE001
            print(f"[ERR select_root] {c['case_id'][:24]}: {e}")
            continue

        rec = {"case_id": c["case_id"], "gold": gold}
        for arm in ("pure_llm", "recall_hints"):
            try:
                labels = run_arm(controller, env, DiagnosticState, clean_text,
                                 arm == "recall_hints", root)
                idx = judge(gold, labels) if labels else -1
                hit = 0 <= idx < len(labels)
                clean = hit and not _residual(labels[idx])
                tot[arm]["reach"] += int(hit)
                tot[arm]["clean"] += int(clean)
                rec[arm] = {"labels": labels, "hit": hit, "clean": clean,
                            "assigned": labels[idx] if hit else None}
            except Exception as e:  # noqa: BLE001
                rec[arm] = {"error": f"{type(e).__name__}: {e}"}
        holder["exclude"] = None
        rows.append(rec)
        pl = rec.get("pure_llm", {})
        rh = rec.get("recall_hints", {})
        flag = ""
        if rh.get("clean") and not pl.get("clean"):
            flag = "  ★ HINTS RESCUE"
        elif pl.get("clean") and not rh.get("clean"):
            flag = "  ⚠ HINTS REGRESS"
        print(f"[{n:>3}] {c['case_id'][:22]:<24} gold={gold[:30]:<32} "
              f"pure={'C' if pl.get('clean') else ('r' if pl.get('hit') else '-')} "
              f"hints={'C' if rh.get('clean') else ('r' if rh.get('hit') else '-')}{flag}",
              flush=True)

    print("\n" + "=" * 72)
    print(f"RAREARENA LOO REACHABILITY A/B (n={n})")
    for arm in ("pure_llm", "recall_hints"):
        c, r = tot[arm]["clean"], tot[arm]["reach"]
        print(f"  {arm:<13} clean {c}/{n} ({100*c//max(1,n)}%)   "
              f"reachable {r}/{n} ({100*r//max(1,n)}%)")
    rescue = sum(1 for x in rows if x.get("recall_hints", {}).get("clean")
                 and not x.get("pure_llm", {}).get("clean"))
    regress = sum(1 for x in rows if x.get("pure_llm", {}).get("clean")
                  and not x.get("recall_hints", {}).get("clean"))
    print(f"  hints RESCUE (hints clean, pure miss): {rescue}")
    print(f"  hints REGRESS (pure clean, hints miss): {regress}")
    out = PROJECT_ROOT / "logs" / f"recall_hints_ra_{args.tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"  detail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
