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
}


def load_module_prompt(module_name: str) -> str:
    file_name = PROMPT_FILE_BY_MODULE[module_name]
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    return (prompts_dir / file_name).read_text(encoding="utf-8").strip()
