from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "p5kg_ladder", ROOT / "scripts/run_talp_p5kg_ab_ladder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ladder_keeps_all_arms_at_p5_and_isolates_tags():
    module = _module()
    flags = dict(module.ARM_FLAGS)
    assert set(flags) == {
        "G0", "G1", "G2PR", "G2UR", "G2CR", "G3R", "G4R"}
    assert "--research-evidence-mode=pair_direct" in flags["G2PR"]
    assert "--research-evidence-mode=unary" in flags["G2UR"]
    assert "--research-evidence-mode=composed" in flags["G2CR"]
    assert module.DEFERRED_ARMS == {"G5"}
    outputs = module._expected_outputs("p5kg_research_g4r", "7,11,13")
    assert len(outputs) == 3
    assert outputs[0].name.endswith("_dv2_p5.json")


def test_ladder_dry_run_records_conditions_and_audits(tmp_path, monkeypatch):
    module = _module()
    manifest = tmp_path / "run.json"
    argv = [
        "run_talp_p5kg_ab_ladder.py", "--dry-run",
        "--arms=G2PR,G2UR,G2CR,G3R,G4R,G5",
        f"--pair-claims={tmp_path / 'pair.jsonl'}",
        f"--unary-claims={tmp_path / 'unary.jsonl'}",
        f"--composed-claims={tmp_path / 'composed.jsonl'}",
        f"--adjacency={tmp_path / 'adj.json'}",
        f"--p5kg-research-manifest={tmp_path / 'assets.json'}",
        f"--manifest={manifest}",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0
    records = json.loads(manifest.read_text())
    by_arm = {record["arm"]: record for record in records}
    assert set(by_arm) == {"G2PR", "G2UR", "G2CR", "G3R", "G4R", "G5"}
    active = [record for record in records if record["arm"] != "G5"]
    assert all("--disc-stage=p5" in record["command"] for record in active)
    assert by_arm["G3R"]["condition"]
    assert by_arm["G4R"]["condition"]
    assert by_arm["G4R"]["pre_audits"] == by_arm["G4R"]["post_audits"]
    assert "--research" in by_arm["G4R"]["pre_audits"][1]
    assert any(
        flag.startswith("--research-corpus-metadata=")
        for flag in by_arm["G4R"]["command"])
    assert "--research-hydrate" in by_arm["G4R"]["command"]
    assert any(
        flag.startswith("--extra-dataset=")
        for flag in by_arm["G4R"]["command"])
    assert by_arm["G5"]["status"] == "deferred"
    assert all(
        record["tag"].startswith("p5kg_research_")
        for record in active)


def test_conditional_gate_rejects_direction_regression(tmp_path):
    module = _module()
    base = tmp_path / "base.json"
    candidate = tmp_path / "candidate.json"
    base.write_text(json.dumps({"summary": {
        "dir_ok": 2, "dir_n": 2, "ruleout_ok": 1, "ruleout_n": 1,
        "sel1": 1, "n_sel": 1, "shared_ok": 0, "shared_n": 1}}))
    candidate.write_text(json.dumps({"summary": {
        "dir_ok": 1, "dir_n": 2, "ruleout_ok": 1, "ruleout_n": 1,
        "sel1": 1, "n_sel": 1, "shared_ok": 1, "shared_n": 1}}))
    assert not module._gate_passes([base], [candidate])


def test_claim_type_gate_distinguishes_empty_and_forbidden_inputs(tmp_path):
    module = _module()
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    wrong = tmp_path / "wrong.jsonl"
    wrong.write_text(json.dumps({"claim_type": "membership"}) + "\n")
    assert module._claim_types(empty) == set()
    assert module._claim_types(wrong) == {"membership"}
