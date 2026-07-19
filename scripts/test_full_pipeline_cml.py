#!/usr/bin/env python3
"""Full-pipeline diagnostic test for a CML-BC case.

Runs the actual AgentClinicTreeController with all knowledge layers enabled
in static_diagnosis_qa mode. Logs every LLM call to a file for post-hoc audit.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ── project root on sys.path ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Force CPU for sentence-transformers (avoid CUDA OOM)
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("TREE_DX_USE_PROXY", "1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ── CML vignette ────────────────────────────────────────────────────────────
CML_VIGNETTE = """\
A 52-year-old male presents to the emergency department with progressive fatigue,
night sweats, abdominal fullness, and blurred vision over the past 3 weeks. Past
medical history is unremarkable except for well-controlled hypertension.

Physical exam reveals:
- Massive splenomegaly (8 cm below costal margin)
- Bilateral retinal hemorrhages with cotton-wool spots on fundoscopy
- Scattered petechiae on lower extremities

Laboratory findings:
- WBC: 145,000/μL with 82% blasts
- Hemoglobin: 7.2 g/dL
- Platelets: 28,000/μL
- Basophilia: 8%
- LDH: 2,450 U/L (elevated)
- Uric acid: 11.2 mg/dL (elevated)
- Peripheral smear: left-shifted granulocytes at all stages of maturation

Cytogenetics / Molecular studies:
- Philadelphia chromosome (Ph) positive
- BCR-ABL1 fusion gene detected (p210 transcript)

Question: What is the most likely diagnosis?

Options:
A. Chronic Myeloid Leukemia - Blast Crisis (CML-BC)
B. Acute Myeloid Leukemia (AML)
C. Myelodysplastic Syndrome (MDS)
D. Chronic Lymphocytic Leukemia (CLL)
E. Acute Lymphoblastic Leukemia (ALL)
"""

CORRECT_ANSWER = "A"


# ── Mock environment ────────────────────────────────────────────────────────
class StaticQAEnv:
    """Minimal environment stub for static_diagnosis_qa mode."""

    def __init__(self, case_text: str):
        self._case_text = case_text

    def get_case_summary(self):
        return self._case_text

    def root_changed_materially(self, state):
        return False

    def patient_still_unstable(self):
        return False

    def ingest_external_context(self, ctx):
        pass

    def take_emergent_action(self, action):
        pass

    def call_module(self, module_name, payload):
        raise NotImplementedError("LLM client should be used, not env.call_module")


def main():
    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    from agentclinic_tree_dx.state import DiagnosticState

    DATA = PROJECT_ROOT / "data"

    config = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        max_turn_budget=5,
        min_readiness_to_commit=0.70,
        allow_external_knowledge=True,

        # Knowledge layers
        dxs_common_json=str(DATA / "knowledge_raw" / "Guideline_common.json"),
        dxs_rare_json=str(DATA / "knowledge_raw" / "Guideline_rare.json"),
        primekg_csv=str(DATA / "knowledge_raw" / "kg.csv"),
        lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
        doclogica_cache_json=str(DATA / "knowledge_raw" / "doclogica_cache.json"),

        enable_knowledge_injection=True,
        enable_chain_discoverer=True,
        max_knowledge_prompt_lines=40,

        rag_index_dir=str(DATA / "corpus" / "rag_index"),
        enable_pubmed_fallback=False,

        # Bundler
        use_dual_channel_bundler=True,
        min_marginal_ig_threshold=0.05,
        redundancy_similarity_threshold=0.60,
    )

    llm = RobustLLMClient(
        model="qwen/qwen3-32b",
        call_timeout=180,
        max_retries=5,
    )

    log_path = str(PROJECT_ROOT / "logs" / f"cml_full_pipeline_{datetime.now():%Y%m%d_%H%M%S}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    llm.configure_logging(log_path)

    env = StaticQAEnv(CML_VIGNETTE)

    controller = AgentClinicTreeController(
        env=env,
        llm=llm,
        config=config,
    )

    state = DiagnosticState(case_id="CML_BC_TEST_001")

    print("=" * 75)
    print("FULL PIPELINE CML-BC DIAGNOSTIC TEST")
    print("=" * 75)
    print(f"  Model:           {llm.model}")
    print(f"  Knowledge:       injection={config.enable_knowledge_injection}, "
          f"chain={config.enable_chain_discoverer}")
    print(f"  RAG:             {config.rag_index_dir}")
    print(f"  Turn budget:     {config.max_turn_budget}")
    print(f"  Log:             {log_path}")
    print(f"  Correct answer:  {CORRECT_ANSWER} (CML-BC)")
    print("=" * 75)
    print()

    try:
        result = controller.run(state)
    except Exception as e:
        print(f"\n*** PIPELINE ERROR: {e}")
        import traceback
        traceback.print_exc()
        result = None

    # ── Results ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print("DIAGNOSTIC RESULTS")
    print("=" * 75)

    if result:
        final_answer = result.get("final_answer", "?")
        mapping = result.get("answer_option_mapping", {})
        print(f"\n  Final answer:  {final_answer}")
        print(f"  Option mapping: {json.dumps(mapping, indent=4)}")
        correct = final_answer.strip().upper().startswith(CORRECT_ANSWER)
        print(f"\n  Correct answer: {CORRECT_ANSWER}")
        print(f"  VERDICT:       {'✓ CORRECT' if correct else '✗ INCORRECT'}")
    else:
        print("  No result returned.")

    # ── State summary ────────────────────────────────────────────────────────
    print(f"\n{'─' * 75}")
    print("STATE SUMMARY")
    print(f"{'─' * 75}")
    print(f"  Timesteps:       {state.timestep}")
    print(f"  Turn budget:     {state.turn_budget_used}/{config.max_turn_budget}")
    print(f"  Root:            {state.root.label if state.root else '?'}")

    if state.branches:
        print(f"\n  Branches ({len(state.branches)}):")
        for bid, b in sorted(state.branches.items(), key=lambda x: -x[1].posterior):
            print(f"    {bid}: {b.label}")
            print(f"      status={b.status}  posterior={b.posterior:.3f}  level={b.level}")
            if b.evidence_for:
                for ev in b.evidence_for[-3:]:
                    print(f"      [+] {ev[:100]}")
            if b.evidence_against:
                for ev in b.evidence_against[-3:]:
                    print(f"      [-] {ev[:100]}")

    print(f"\n  Actions taken ({len(state.actions_taken)}):")
    for i, a in enumerate(state.actions_taken):
        print(f"    [{i}] t={a.get('timestep')} "
              f"type={a.get('action_type')} "
              f"bundle={a.get('bundle_id')}/{a.get('bundle_position')}")
        print(f"        content: {a.get('content', '')[:120]}")
        print(f"        summary: {a.get('result_summary', '')[:120]}")

    if state.termination:
        print(f"\n  Termination: type={state.termination.termination_type}, "
              f"reason={state.termination.reason[:200]}")

    # ── Differential history ─────────────────────────────────────────────────
    if state.differential_history:
        print(f"\n  Differential trajectory:")
        for i, snap in enumerate(state.differential_history):
            parts = [f"{k}={v:.3f}" for k, v in sorted(snap.items(), key=lambda x: -x[1])]
            print(f"    t={i+1}: {', '.join(parts)}")

    print(f"\n  Full log: {log_path}")
    print("=" * 75)


if __name__ == "__main__":
    main()
