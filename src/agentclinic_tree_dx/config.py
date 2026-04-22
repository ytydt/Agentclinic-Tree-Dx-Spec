from dataclasses import dataclass


@dataclass
class ControllerConfig:
    test_threshold: float = 0.05
    commit_threshold: float = 0.75
    max_live_frontier: int = 4

    # Specialized execution mode for AgentClinic physician runtime.
    execution_mode: str = "default"  # default | agentclinic_physician_patch | sdbench_patch | static_diagnosis_qa

    # Turn-aware controls for patch mode.
    max_turn_budget: int | None = None
    min_readiness_to_commit: float = 0.75

    # Benchmark/tool permissions.
    allow_external_knowledge: bool = True
    allow_calculator: bool = True
    allow_notebook: bool = False
