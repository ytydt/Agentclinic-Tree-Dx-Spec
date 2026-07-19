"""Investigate why RootSelector emitted a ~70-word run-on label on the synthetic
CML case while prior medbullets tests produced concise (~10-word) labels.

Calls RootSelector (qwen/qwen3-32b) standalone on:
  - the lab-dense synthetic CML vignette (full-pipeline input)
  - 2 narrative medbullets cases
and reports label word/char counts. No knowledge layer needed.
"""
from __future__ import annotations
import ast, csv, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ["CUDA_VISIBLE_DEVICES"] = ""
TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")

from agentclinic_tree_dx.llm_client import RobustLLMClient
from agentclinic_tree_dx.prompting import load_module_prompt

CML = """A 52-year-old male presents with progressive fatigue, night sweats, abdominal fullness,
and blurred vision over 3 weeks. Exam: massive splenomegaly, bilateral retinal hemorrhages.
Labs: WBC 145,000/uL with 82% blasts, Hgb 7.2, platelets 28,000, basophilia 8%, LDH 2450,
uric acid 11.2. Smear: left-shifted granulocytes. Ph chromosome positive, BCR-ABL1 p210."""


def load_narrative(n=2):
    out = []
    for row in csv.DictReader(TSV.open(encoding="utf-8"), delimiter="\t"):
        q = row["question"].strip()
        if "figure" in q.lower() or "shown in" in q.lower():
            continue
        if "most likely diagnosis" in q.lower():
            out.append(q)
        if len(out) >= n:
            break
    return out


def main():
    llm = RobustLLMClient(model="qwen/qwen3-32b", call_timeout=180, max_retries=4)
    prompt = load_module_prompt("RootSelector")

    def probe(name, vignette):
        payload = {"case_summary": vignette, "static_vignette": vignette, "static_options": []}
        res = llm.call_module("RootSelector", prompt, payload)
        lbl = res.get("root_label", res.get("label", ""))
        print(f"\n=== {name} ===")
        print(f"  words={len(lbl.split())}  chars={len(lbl)}")
        print(f"  label: {lbl[:400]}")
        return len(lbl.split())

    probe("CML synthetic (lab-dense)", CML)
    for i, q in enumerate(load_narrative(2)):
        probe(f"medbullets narrative #{i}", q)

    # ── exact pipeline payload (full state.to_dict via _root_selector_payload) ──
    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.state import DiagnosticState

    cfg = ControllerConfig(execution_mode="static_diagnosis_qa", enable_knowledge_injection=False)
    ctrl = AgentClinicTreeController(env=None, llm=llm, config=cfg)
    full_case = CML + "\n\nQuestion: What is the most likely diagnosis?\nOptions:\nA. CML-BC\nB. AML\nC. MDS\nD. CLL\nE. ALL\n"
    st = DiagnosticState(case_id="PROBE")
    st.case_summary = full_case
    st.static_vignette = CML
    full_payload = ctrl._root_selector_payload(st)
    print(f"\n[full payload key count = {len(full_payload)}]")
    prompt2 = load_module_prompt("RootSelector")
    for r in range(3):
        res = llm.call_module("RootSelector", prompt2, full_payload)
        lbl = res.get("root_label", res.get("label", ""))
        print(f"  full-payload run {r}: words={len(lbl.split())} chars={len(lbl)} | {lbl[:160]}")


if __name__ == "__main__":
    main()
