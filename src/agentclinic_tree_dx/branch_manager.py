from .state import DiagnosticState


def run_branch_creator(env, state: DiagnosticState) -> dict:
    return env.call_module("BranchCreator", state)
