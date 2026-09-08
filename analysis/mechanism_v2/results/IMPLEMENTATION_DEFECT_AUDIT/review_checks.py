#!/usr/bin/env python3
"""Independent checks of evidence boundaries and selected claims, not bug fixes."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = HERE.parent / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
BASE = "bbc036e8a6ec93583be915a4609fe86278ed062c"


def main():
    checks = []
    def check(cid, ok, detail):
        checks.append({"id": cid, "passed": bool(ok), "detail": detail})
        assert ok, (cid, detail)

    files = ["reproduce_engine_defects_results.json", "identity_reproduction_results.json",
             "reproduce_upstream_defects_results.json", "auxiliary_reproduction_results.json"]
    payloads = {f: json.loads((HERE / f).read_text()) for f in files}
    manifest = {}
    def source(path, digest, owner):
        if path in manifest:
            check("cross_artifact_source_hash:" + owner + ":" + path, manifest[path] == digest,
                  "Overlapping audit families must attest the same frozen source content.")
        manifest[path] = digest
    engpack = payloads[files[0]]
    source(engpack["engine_path"], engpack["engine_sha256"], "engine")
    idpack = payloads[files[1]]
    source(idpack["production_file"], idpack["production_sha256"], "identity")
    uppack = payloads[files[2]]
    for row in uppack["source_manifest"]:
        source(row["path"], row["sha256"], "upstream")
    for path, digest in payloads[files[3]]["source_sha256"].items():
        source(path, digest, "auxiliary")
    for path, claimed in manifest.items():
        raw = subprocess.run(["git", "show", f"{BASE}:{path}"], cwd=ROOT,
                             capture_output=True, check=True, timeout=45).stdout
        digest = hashlib.sha256(raw).hexdigest()
        check("source_hash:" + path, digest == claimed, {"claimed": claimed, "frozen": digest})
        local = ROOT / path
        if local.exists():
            check("local_unchanged:" + path, hashlib.sha256(local.read_bytes()).hexdigest() == digest,
                  "Local production content matches frozen blob; scripts do not silently test a patched engine.")

    # Independent countercheck of the false claim initially made by a mocked CLI
    # witness. Only the optional gate function is stubbed to avoid model loading;
    # original run_case and its dispatch guard are executed unchanged.
    sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location("review_original_engine", SRC / "run_mechanical_engine.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    import gate_assertions
    calls = []
    def fake_gate(assertions, apply_nli=False):
        calls.append({"apply_nli": apply_nli, "n_assertions": len(assertions)})
        return assertions
    engine.FIX_QUOTE_GATE = False
    engine.FIX_NLI = True
    with patch.object(gate_assertions, "gate_assertions", fake_gate):
        result = engine.run_case({"case_key": "review_dispatch", "gold": "synthetic", "gold_labels_in_set": [],
                                  "candidates": []}, {"findings": [], "assertions": []})
    check("nli_only_dispatches_actual_gate", calls == [{"apply_nli": True, "n_assertions": 0}],
          {"actual_calls": calls, "original_run_case_used": True, "network_or_model_calls": 0})
    check("reject_false_nli_dispatch_claim", not any(
        "gate invocation remains disabled" in str(r.get("description", ""))
        for r in uppack["reproductions"]),
        "Original false-positive UP-R33 was removed or converted to a true dispatch control.")

    for name, rows, field in [(files[0], engpack["witnesses"], "id"),
                              (files[1], idpack["checks"], "id"),
                              (files[2], uppack["reproductions"], "id"),
                              (files[3], payloads[files[3]]["results"], "id")]:
        ids = [r[field] for r in rows]
        check("unique_check_ids:" + name, len(ids) == len(set(ids)), {"records": len(ids)})
    check("engine_historical_pack_denominator", engpack["historical_inventory"]["n_packs"] == 44,
          "44 case×arm packs, not 44 independent cases or extraction reruns.")
    expected = {"old_old": 93, "free_old": 87, "old_v2": 154, "free_v2": 188}
    got = {arm: rows["actual_layer4_penalties"] for arm, rows in engpack["historical_inventory"]["by_arm"].items()}
    check("historical_L4_counts", got == expected, {"counts": got, "not_interpretation": "not all penalties clinically wrong"})
    check("engine_controls_retained", {"S03", "S34"} <= {r["id"] for r in engpack["witnesses"]},
          "A nonmerge control and legitimate hard-action controls are part of the check count.")
    check("identity_control_retained", any(r["id"] == "IDR13" and r["probe_kind"] == "negative_control"
                                            for r in idpack["checks"]),
          "Marker-disabled nonmatch is a control, not an observed failure.")
    for fname in ("reproduce_engine_defects.py", "reproduce_identity_defects.py", "reproduce_upstream_defects.py", "reproduce_auxiliary_defects.py"):
        ast.parse((HERE / fname).read_text())
        check("python_ast:" + fname, True, "Parsed audit code; this check does not prove semantic correctness.")
    out = {"frozen_commit": BASE, "status": "passed", "checks": checks,
           "n_checks": len(checks), "input_artifact_hashes": {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest() for f in files},
           "limits": ["Independent static/machine evidence checks; not an additional clinical trial.",
                      "Mocked transport and fixture input assertions do not establish actual provider or source prevalence.",
                      "Defect IDs and witness/check counts overlap and cannot be summed into independent causal error counts."]}
    (HERE / "review_checks.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "passed", "n_checks": len(checks)}))


if __name__ == "__main__":
    main()
