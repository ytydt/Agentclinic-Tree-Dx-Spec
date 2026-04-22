from .state import DiagnosticState


def run_root_selector(env, state: DiagnosticState) -> dict:
    return env.call_module("RootSelector", state)
