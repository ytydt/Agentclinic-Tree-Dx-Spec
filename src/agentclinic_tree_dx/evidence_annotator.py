from .state import DiagnosticState


def run_evidence_annotator(env, state: DiagnosticState, raw_result: dict) -> dict:
    return env.call_module("EvidenceAnnotator", {"state": state, "raw_result": raw_result})
