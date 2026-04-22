from __future__ import annotations

from pathlib import Path


PROMPT_FILE_BY_MODULE = {
    "SafetyController": "safety_controller.txt",
    "RootSelector": "root_selector.txt",
    "BranchCreator": "branch_creator.txt",
    "TemporaryLeafPlanner": "temporary_leaf_planner.txt",
    "EvidenceAnnotator": "evidence_annotator.txt",
    "PostUpdateStateReviser": "post_update_state_reviser.txt",
    "TerminationJudge": "termination_judge.txt",
    "FinalAggregator": "final_aggregator.txt",
    "Hypothesis": "hypothesis.txt",
    "TestChooser": "test_chooser.txt",
    "Challenger": "challenger.txt",
    "Stewardship": "stewardship.txt",
    "Checklist": "checklist.txt",
    "Consensus": "consensus.txt",
    "FinalDiagnosisEmitter": "final_diagnosis_emitter.txt",
    "VignetteParser": "vignette_parser.txt",
    "AnswerMapper": "answer_mapper.txt",
    "EvidenceAllocator": "evidence_allocator.txt",
    "ReasoningEconomyAuditor": "reasoning_economy_auditor.txt",
    "TemporaryAnalyticLeafPlanner": "temporary_analytic_leaf_planner.txt",
    "ToolUseGate": "tool_use_gate.txt",
}


def load_module_prompt(module_name: str) -> str:
    file_name = PROMPT_FILE_BY_MODULE[module_name]
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    return (prompts_dir / file_name).read_text(encoding="utf-8").strip()
