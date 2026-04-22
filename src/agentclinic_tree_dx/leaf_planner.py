from .state import DiagnosticState


def run_leaf_planner(env, state: DiagnosticState) -> dict:
    return env.call_module("TemporaryLeafPlanner", state)
