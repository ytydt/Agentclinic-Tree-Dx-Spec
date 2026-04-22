from .state import DiagnosticState


def run_safety_controller(env, state: DiagnosticState) -> dict:
    return env.call_module("SafetyController", state)
