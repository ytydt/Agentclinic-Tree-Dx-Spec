from dataclasses import dataclass


@dataclass
class ControllerConfig:
    test_threshold: float = 0.05
    commit_threshold: float = 0.75
    max_live_frontier: int = 4
