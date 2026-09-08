#!/usr/bin/env python3
"""Reproduce upstream implementation defects without model/network calls.

Invokes repository functions; only transport, filesystem roots, and the engine
body in output-name probes are mocked. The sparse-unchecked LLM client is read
from a pinned Git object and its original methods are AST-executed unchanged.
No source data, caches, or production files are mutated.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import types
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CODE = HERE.parent / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
DATA = REPO / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
BASE = "bbc036e8a6ec93583be915a4609fe86278ed062c"
sys.path.insert(0, str(CODE))
ex = importlib.import_module("run_trial_extraction")
ga = importlib.import_module("gate_assertions")
nli = importlib.import_module("nli_verify_assertions")
nl = importlib.import_module("extract_nl_rules")
eng = importlib.import_module("run_mechanical_engine")
sw = importlib.import_module("sweep_fixes")
ret = importlib.import_module("trial_retriever")
rr = importlib.import_module("run_trial_retrieval")
RESULTS: list[dict] = []
CONTROLS: list[dict] = []


def record(identifier, description, observed, condition=True):
    assert condition, (identifier, observed)
    RESULTS.append({"id": identifier, "description": description,
                    "observed": observed, "defect_reproduced": True})


def row(**kwargs):
    out = dict(subject="Disease Alpha", predicate="fever", relation="feature_of",
               polarity="asserted", modality="typical", context_type="criteria",
               quote="Disease Alpha is associated with fever.", threshold={},
               criterion_group={"group_id": None, "logic": None, "n": None})
    out.update(kwargs)
    return out


def extractor_without_transport(module, client):
    obj = object.__new__(module.Extractor)
    obj.model = "fixture/model"
    obj.workers = 2
    obj._local = threading.local()
    obj.stats = {"called": 0, "cached": 0, "empty": 0}
    obj._lock = threading.Lock()
    obj.client = lambda: client
    return obj


def cache_probes(tmp):
    class Client:
        def __init__(self):
            self.calls = []

        def call_module(self, module, prompt, payload):
            self.calls.append((module, prompt))
            return {"assertions": [{"subject": prompt, "predicate": module}]}

    for module in [ex, nl]:
        cache = tmp / module.__name__
        cache.mkdir()
        client = Client()
        obj = extractor_without_transport(module, client)
        with patch.object(module, "CACHE", cache):
            first = obj.call("same", "module_A", "prompt_A", {"passage": "same"})
            second = obj.call("same", "module_B", "prompt_B", {"passage": "same"})
            record("UP-R01-" + module.__name__, "Prompt and module omitted from cache key",
                   {"client_calls": client.calls, "first": first, "second": second},
                   first == second and len(client.calls) == 1)

    cache = tmp / "failures"
    cache.mkdir()
    client = Client()
    obj = extractor_without_transport(ex, client)
    with patch.object(ex, "CACHE", cache):
        obj.client = lambda: types.SimpleNamespace(call_module=lambda *a: (_ for _ in ()).throw(RuntimeError("fixture timeout")))
        first = obj.call("failure", "Module", "prompt", {})
        obj.client = lambda: client
        second = obj.call("failure", "Module", "prompt", {})
        record("UP-R02", "Transport failure persists as valid empty cached extraction",
               {"first": first, "second": second, "recovery_calls": client.calls,
                "cache_content": list(cache.glob("*.json"))[0].read_text()},
               first == second == {} and not client.calls)

    cache = tmp / "race"
    cache.mkdir()
    barrier = threading.Barrier(2)
    calls = []

    def race_call(*args):
        calls.append(threading.get_ident())
        barrier.wait(timeout=5)
        return {"assertions": [], "worker": threading.get_ident()}

    obj = extractor_without_transport(ex, types.SimpleNamespace(call_module=race_call))
    with patch.object(ex, "CACHE", cache):
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: obj.call("race", "Module", "prompt", {}), range(2)))
        record("UP-R03", "Simultaneous identical payloads both call transport and write same cache path",
               {"calls": len(calls), "distinct_results": len({v["worker"] for v in values}),
                "cache_files": len(list(cache.glob("*.json")))}, len(calls) == 2)
        key = ex.cache_key("corrupt", {}, obj.model)
        (cache / (key + ".json")).write_text('{"assertions":')
        error = None
        try:
            obj.call("corrupt", "Module", "prompt", {})
        except json.JSONDecodeError as exc:
            error = type(exc).__name__
        record("UP-R04", "A half-written cache file aborts the extraction worker before retry",
               {"error": error}, error == "JSONDecodeError")


def llm_parser_probes():
    source = subprocess.check_output(["git", "show", BASE + ":src/agentclinic_tree_dx/llm_client.py"],
                                     cwd=REPO, text=True)
    tree = ast.parse(source)
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RobustLLMClient")
    names = {"_strip_markdown_fences", "_sanitize_jsonish", "_looks_truncated_json",
             "_bump_direct_post_output_cap", "_parse_json_object", "call_module"}
    cls = ast.ClassDef(name="ProductionParser", bases=[], keywords=[],
                       body=[n for n in original.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names],
                       decorator_list=[])
    ns = {"json": json, "re": re, "os": os, "Any": Any}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 "<original_llm_client_AST>", "exec"), ns)
    parser = ns["ProductionParser"]()
    invalid = '{"quote":"A,}", "assertions":[],}'
    parsed = parser._parse_json_object(invalid)
    record("UP-R05", "Trailing-comma repair rewrites quoted source text",
           {"raw": invalid, "parsed": parsed}, parsed.get("quote") == "A}")
    duplicate = '{"threshold":{"value":480,"value":48},"assertions":[]}'
    parsed = parser._parse_json_object(duplicate)
    record("UP-R06", "Duplicate JSON keys silently select last semantic value",
           {"raw": duplicate, "parsed": parsed}, parsed["threshold"]["value"] == 48)
    parser.min_response_length = 1
    calls = []
    parser.get_robust_completion = lambda *a, **k: calls.append(k) or "{}"
    parser._write_log = lambda *a, **k: None
    with patch.dict(os.environ, {"TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192"}):
        parsed = parser.call_module("Module", "prompt", {})
    record("UP-R07", "Syntactically valid empty object and invalid parse share {} sentinel",
           {"completion_calls_for_valid_empty_object": len(calls), "returned": parsed},
           len(calls) == 3 and parsed == {})
    return {"path": "src/agentclinic_tree_dx/llm_client.py", "git_revision": BASE,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
            "execution_mode": "original_methods_AST_without_transport_imports"}


def extraction_and_gate_probes(tmp):
    variations = []
    for n in [None, "n/a", 2.9, True, False, "2.9", -2]:
        a = row(criterion_group={"group_id": "g", "logic": "at_least_n", "n": n})
        stats = Counter()
        ex.normalise_group(a, stats)
        variations.append({"input_n": n, "normalized": a["criterion_group"], "stats": dict(stats)})
    record("UP-R08", "Invalid count silently weakens to any; floats/bools accepted as integers",
           variations, variations[0]["normalized"]["logic"] == "any" and
           variations[2]["normalized"]["n"] == 2 and variations[3]["normalized"]["n"] == 1)
    a = row(relation=" REQUIRED_FOR ")
    b = eng.clamp_relation(a)
    record("UP-R09", "Legal normalized relation returns original unnormalized enum",
           {"input": a["relation"], "output": b["relation"]}, b["relation"] == " REQUIRED_FOR ")
    aliases = {rel: eng.clamp_relation(row(relation=rel))["relation"] for rel in
               ["risk_factor_for", "includes", "unspecified_relation"]}
    record("UP-R41", "Enum aliases infer causation, hierarchy or positive feature from weaker/unknown relation",
           aliases, aliases == {"risk_factor_for": "caused_by", "includes": "variant_of", "unspecified_relation": "feature_of"})

    passage = "Pulmonary edema is present. Arterial pressure is measured. Hypertension has other causes."
    output = {"mentioned_diseases": ["Pulmonary arterial hypertension"],
              "assertions": [row(subject="Pulmonary arterial hypertension", quote="An invented source quote states fever.")]}
    kept = ex.postprocess_grounded(output, passage)
    record("UP-R10", "Grounded subject gate accepts scattered word recombination and unverifiable quote",
           {"passage": passage, "kept": kept}, len(kept) == 1 and kept[0]["quote"] not in passage)

    parses = {q: ga.parse_threshold_from_quote(q) for q in [
        "In 2020, QTc > 480 ms established the criterion.",
        "QTc > 480 ms established the criterion.",
        "QTc > 480 msec established the criterion.",
        "A reading is from 10 to 20 msec.",
        "This is a very long label for QTc > 480 ms",
        "Patients aged 12-18 years require QTc > 480 ms.",
        "A temperature of -5 to -1 C was recorded."]}
    record("UP-R11", "Threshold parser selects first numeral/range, ignores later explicit comparison",
           parses, parses["In 2020, QTc > 480 ms established the criterion."] is None and
           parses["Patients aged 12-18 years require QTc > 480 ms."]["value"] == 12)
    record("UP-R12", "Unit alternatives truncate msec as ms and omit signs on numeric bounds",
           {"msec": parses["A reading is from 10 to 20 msec."],
            "negative": parses["A temperature of -5 to -1 C was recorded."]},
           parses["A reading is from 10 to 20 msec."]["unit"] == "ms" and
           parses["A temperature of -5 to -1 C was recorded."] is None)
    record("UP-R39", "Greedy nonnumeric regex consumes comparator unless prefix-length limit happens to stop it",
           {"short": parses["QTc > 480 ms established the criterion."],
            "long": parses["This is a very long label for QTc > 480 ms"]},
           parses["QTc > 480 ms established the criterion."] is None and
           parses["This is a very long label for QTc > 480 ms"]["operator"] == ">")

    values = {f"{v} in {q}": ga.number_in_text(v, q) for v, q in [(48, "1480 patients"), (480, "48 patients"), (5, "15 patients")]}
    a = row(predicate="marker concentration", quote="Disease Alpha has marker concentration 5 units.",
            threshold={"operator": "range", "value": 5, "value_high": 9999, "unit": "unmentioned"},
            _passage="Disease Alpha has marker concentration 5 units.")
    gated = ga.gate_one(a)
    record("UP-R13", "Numeric license accepts substrings/scaling and leaves upper bound/operator/unit unchecked",
           {"numeric_membership": values, "gated_threshold": gated["threshold"]},
           all(values.values()) and gated["threshold"]["value_high"] == 9999)

    passage = "Disease Alpha has a rare marker. Marker A is pathognomonic for another condition."
    a = row(relation="pathognomonic_for", quote="Disease Alpha has fever; this is fabricated.", _passage=passage)
    gated = ga.gate_one(a)
    record("UP-R14", "Unaligned fabricated quote falls back to short passage and borrows unrelated hallmark cue",
           {"passage": passage, "quote": a["quote"], "licensed": ga.license_text(a, a["quote"]),
            "output_relation": gated["relation"]}, gated["relation"] == "pathognomonic_for")

    passage = "A biomarker is required for diagnosis of Disease Alpha. Fever is common."
    broad = ga.gate_one(row(relation="required_for", modality="obligatory", quote=passage, _passage=passage))
    narrow = ga.gate_one(row(relation="required_for", modality="obligatory", quote="Fever is common.", _passage=passage))
    record("UP-R15", "Any necessity cue inside broad quote licenses unrelated predicate without predicate scope",
           {"broad_relation": broad["relation"], "narrow_relation": narrow["relation"]},
           broad["relation"] == "required_for" and narrow["relation"] == "feature_of")

    q = "Disease Alpha is defined if and only if marker X is present; marker X is required and diagnostic."
    dual = ga._g1_drop_dual_patho([row(predicate="marker X", relation="required_for", quote=q),
                                 row(predicate="marker X", relation="pathognomonic_for", quote=q)])
    record("UP-R16", "G1 assumes necessary and sufficient relations cannot coexist, removes valid biconditional half",
           [{"relation": a["relation"], "gate": a.get("_gate")} for a in dual],
           dual[1]["relation"] == "feature_of")
    a = row(predicate="normal marker", relation="excludes", polarity="negated",
            quote="Normal marker values are below 5 units.")
    g2 = ga._reference_range_recode(a, a["quote"])
    record("UP-R17", "Complement of normal x<5 becomes x>5, losing equality; recode also invents disease necessity",
           {"input": a, "output": g2, "missing_boundary_value": 5},
           g2["threshold"]["operator"] == ">")
    passage = "Disease Alpha is diagnosed in the presence of fever or rash."
    g3 = ga.gate_one(row(quote=passage, _passage=passage))
    record("UP-R18", "G3 upgrades a disjunction member to required_for without connective checking",
           {"input_passage": passage, "output": g3}, g3["relation"] == "required_for")

    local = tmp / "retrieval"
    local.mkdir()
    short = "Common opening text."
    old = short + " Marker X is pathognomonic for Disease Alpha."
    new = short + " No disease-specific rule follows."

    def write_ret(name, passage):
        (local / name).write_text(json.dumps([{"retrieved": {"Disease Alpha": {"passages": [
            {"source": "fixture", "title": "Title", "section_path": "Criteria", "text": passage}]}}}]))

    write_ret("trial_retrieval_k30.json", old)
    write_ret("actual_arm.json", new)
    a = row(_source="fixture", _title="Title", _section="Criteria", quote=short,
            _passage_sha1=hashlib.sha1(new.encode()).hexdigest()[:16])
    with patch.object(ga, "LEDGER", local), patch.object(ga, "_PASSAGE_INDEX", None), patch.dict(os.environ, {"F7_EXTRA_RETRIEVAL": ""}):
        resolved = ga.resolve_passage(a)
        os.environ["F7_EXTRA_RETRIEVAL"] = "actual_arm.json"
        after_env = ga.resolve_passage(a)
        record("UP-R19", "F7 default source table uses old window despite actual-arm hash; cached index ignores later env change",
               {"actual_window": new, "resolved": resolved, "after_env_update": after_env},
               resolved == after_env == old)
    prefix = "A" * 6000
    full = prefix + " This is the continuation that the extractor did not see."
    write_ret("trial_retrieval_k30.json", full)
    a = row(_source="fixture", _title="Title", _section="Criteria", quote="A" * 80,
            _passage_sha1=hashlib.sha1(prefix.encode()).hexdigest()[:16])
    with patch.object(ga, "LEDGER", local), patch.object(ga, "_PASSAGE_INDEX", None), patch.dict(os.environ, {"F7_EXTRA_RETRIEVAL": ""}):
        resolved = ga.resolve_passage(a)
        record("UP-R20", "Hash of truncated extraction payload cannot match full-window hash and falls back to full source",
               {"payload_length": len(prefix), "resolved_length": len(resolved),
                "prefix_hash": a["_passage_sha1"], "full_hash": hashlib.sha1(full.encode()).hexdigest()[:16]},
               resolved == full)

    quote = "Disease Alpha requires marker A or marker B."
    snippet = "import sys,json;sys.path.insert(0,sys.argv[1]);import gate_assertions as g;" \
              "a={'subject':'Disease Alpha','predicate':'marker A','relation':'required_for','quote':'Disease Alpha requires marker A or marker B.'};" \
              "b=dict(a,predicate='marker B');print(g._merge_and_or_required([a,b])[0]['criterion_group']['group_id'])"
    gids = []
    for seed in [1, 2]:
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        gids.append(subprocess.check_output([sys.executable, "-c", snippet, str(CODE)], env=env, text=True).strip())
    record("UP-R21", "Process-salted hash changes derived group ID for identical source/rows",
           {"PYTHONHASHSEED_1": gids[0], "PYTHONHASHSEED_2": gids[1]}, gids[0] != gids[1])


def backfill_and_nl_probes():
    texts = ["No laparoscopic appendectomy had been performed.",
             "Surgical clips are present in the left axilla.",
             "The lesion was not fluctuant."]
    outputs = [ex.backfill_findings(t, []) for t in texts]
    record("UP-R22", "Grounded regex backfill ignores negation and hardcodes right-iliac site",
           [{"vignette": t, "findings": fs} for t, fs in zip(texts, outputs)],
           all(fs[0]["polarity"] == "present" for fs in outputs) and
           outputs[1][0]["canonical"] == "surgical clips in right iliac fossa")
    text = "Initially SaO2 60%. Later platelet count 10000/mm3 and SaO2 80%."
    values = ex.backfill_findings(text, [])
    record("UP-R23", "Independent ordinal indexing fabricates shared SaO2/platelet timepoint",
           {"vignette": text, "findings": values},
           values[0]["qualifiers"]["timing"] == values[-1]["qualifiers"]["timing"] == "timepoint_1")
    existing = [{"label": "SaO2 60%", "canonical": "oxygen saturation", "polarity": "present"}]
    output = ex.backfill_findings(text, existing)
    record("UP-R24", "Existing one SaO2 label suppresses all missing serial platelet/saturation backfill",
           {"input": existing, "output": output}, output == existing)
    span = "A synthetic marker confirms DiseaseAlpha."
    kept, stats = nl.postprocess({"rules": [{"disease": "DiseaseAlpha", "sentence": span, "use": "diagnosis"}]}, span, {})
    record("UP-R25", "NL excerpt path drops a complete five-word diagnostic sentence solely by word count",
           {"sentence": span, "kept": kept, "stats": dict(stats)}, not kept and stats["dropped_too_short"] == 1)
    passage = "Pulmonary edema is present. Arterial pressure is measured. Hypertension has other causes."
    sentence = "Pulmonary edema is present. Arterial pressure is measured."
    kept, stats = nl.postprocess({"rules": [{"disease": "Pulmonary arterial hypertension", "sentence": sentence,
                                           "use": "unexpected_stage"}]}, passage, {})
    record("UP-R26", "NL excerpt accepts fabricated multiword disease identity and arbitrary use enum",
           {"kept": kept, "stats": dict(stats)}, len(kept) == 1 and kept[0]["use"] == "unexpected_stage")


def nli_probes(tmp):
    a = row(relation="required_for", quote="The absence of fever is required for diagnosis of Disease Alpha.")
    b = dict(a, polarity="negated")
    calls = []

    def predict(premise, hypothesis):
        calls.append(hypothesis)
        return "entailment" if "not the case" not in hypothesis else "contradiction"

    with patch.object(nli, "_cache", {}), patch.object(nli, "CACHE_PATH", tmp / "nli_cache.json"), patch.object(nli, "predict_label", predict):
        la, lb = nli.nli_check_one(a), nli.nli_check_one(b)
    record("UP-R27", "Opposite assertion polarity reuses NLI verdict although verbalized hypotheses differ",
           {"positive_hypothesis": nli.verbalize(a), "negative_hypothesis": nli.verbalize(b),
            "labels": [la, lb], "predict_calls": calls}, len(calls) == 1 and la == lb)
    record("UP-R28", "NLI negates whole necessity relation instead of predicate inside relation",
           {"schema_intention": "Absence of fever is required for diagnosis of Disease Alpha",
            "actual_hypothesis": nli.verbalize(b)},
           nli.verbalize(b) == "it is not the case that fever is required for the diagnosis of Disease Alpha")
    import numpy as np
    fake = types.SimpleNamespace(predict=lambda *a, **k: np.array([[0.0, 1.0, 0.0]]),
                                 model=types.SimpleNamespace(config=types.SimpleNamespace(id2label={0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"})))
    with patch.object(nli, "_get_model", lambda: fake):
        label = nli.predict_label("premise", "hypothesis")
    record("UP-R29", "Generic transformer id2label overrides known model mapping and entailment is silently neutral",
           {"argmax_index": 1, "id2label": fake.model.config.id2label, "returned_label": label}, label == "neutral")
    with patch.object(nli, "nli_check_one", lambda a: "skip"):
        kept = nli.nli_filter_assertions([a])
    record("UP-R30", "NLI unavailable/missing quote leaves high-stakes rule active without per-row unverified status",
           {"kept": kept}, kept[0]["relation"] == "required_for" and "_nli" not in kept[0])


def cli_probes(tmp):
    local = tmp / "cli"
    local.mkdir()
    tasks = [{"case_key": "fixture/1", "vignette": "A patient has fever."}]
    (local / "tasks.json").write_text(json.dumps(tasks))
    (local / "trial_retrieval_test.json").write_text(json.dumps([{"case_key": "fixture/1", "retrieved": {
        "Disease Alpha": {"passages": [{"text": "Disease Alpha has fever.", "source": "fixture", "title": "Title", "section_path": "Criteria"}]}}}]))

    class FakeExtractor:
        def __init__(self, *a):
            self.stats = {"called": 0, "cached": 0, "empty": 0}

        def call(self, kind, module, prompt, payload):
            if kind == "case":
                return {"findings": []}
            return {"mentioned_diseases": ["Disease Alpha"], "assertions": [row(_fixture_kind=kind)]}

    args = ["run_trial_extraction.py", "--arm", "test", "--tasks", "tasks.json", "--groups", "--strip-options", "--workers", "1"]
    with patch.object(ex, "LEDGER", local), patch.object(ex, "Extractor", FakeExtractor), patch.object(sys, "argv", args):
        ex.main()
    path = local / "trial_extraction_testclean_groups.json"
    first = json.loads(path.read_text())
    with patch.object(ex, "LEDGER", local), patch.object(ex, "Extractor", FakeExtractor), patch.object(sys, "argv", args + ["--grounded"]):
        ex.main()
    second = json.loads(path.read_text())
    record("UP-R31", "Grounded and ungrounded extraction main overwrite identical output path",
           {"output_name": path.name, "first_kind": first[0]["assertions"][0]["_fixture_kind"],
            "second_kind": second[0]["assertions"][0]["_fixture_kind"],
            "other_output_names": [p.name for p in local.glob("trial_extraction_*.json")]},
           first != second and len(list(local.glob("trial_extraction_*.json"))) == 1)
    tasks.append({"case_key": "fixture/2", "vignette": "A patient has rash."})
    (local / "tasks.json").write_text(json.dumps(tasks))
    with patch.object(ex, "LEDGER", local), patch.object(ex, "Extractor", FakeExtractor), patch.object(sys, "argv", args):
        ex.main()
    full_count = len(json.loads(path.read_text()))
    with patch.object(ex, "LEDGER", local), patch.object(ex, "Extractor", FakeExtractor), patch.object(sys, "argv", args + ["--only-case", "fixture/1"]):
        ex.main()
    partial_count = len(json.loads(path.read_text()))
    record("UP-R40", "--only-case writes partial extraction over full-arm output without completeness marker",
           {"same_output_path": path.name, "before_cases": full_count, "after_cases": partial_count},
           full_count == 2 and partial_count == 1)
    tasks.pop()
    (local / "tasks.json").write_text(json.dumps(tasks))
    (local / "trial_extraction_test.json").write_text(json.dumps([{"case_key": "fixture/1", "assertions": [], "findings": []}]))

    def fake_run(task, extraction):
        return {"case_key": task["case_key"], "top1": "Disease Alpha", "top1_is_gold": False,
                "gold_rank": None, "gold_eliminated": [], "join_stats": {"matched": 0, "unmatched": 0},
                "fixture_seen_weight": eng.WEIGHT_SCHEME, "fixture_seen_groups": eng.USE_CRITERION_GROUPS,
                "fixture_seen_nli": eng.FIX_NLI, "fixture_seen_quote_gate": eng.FIX_QUOTE_GATE}

    args = ["run_mechanical_engine.py", "--arm", "test", "--tasks", "tasks.json"]
    with patch.object(eng, "LEDGER", local), patch.object(eng, "run_case", fake_run), patch.object(sys, "argv", args):
        eng.main()
    path = local / "trial_engine_test.json"
    first = json.loads(path.read_text())
    with patch.object(eng, "LEDGER", local), patch.object(eng, "run_case", fake_run), patch.object(sys, "argv", args + ["--weight", "idf", "--groups", "--nli"]):
        eng.main()
    second = json.loads(path.read_text())
    record("UP-R32", "Engine CLI configuration changes overwrite identical pathname without manifest",
           {"output_name": path.name, "first_mock_observation": first, "second_mock_observation": second}, first != second)
    gate_calls = []

    class GateReached(Exception):
        pass

    def record_gate(assertions, *, apply_nli=False):
        gate_calls.append({"apply_nli": apply_nli, "rows": len(assertions)})
        raise GateReached()

    with patch.object(ga, "gate_assertions", record_gate), patch.object(eng, "FIX_NLI", True), patch.object(eng, "FIX_QUOTE_GATE", False):
        try:
            eng.run_case({}, {"findings": [], "assertions": []})
        except GateReached:
            pass
    assert gate_calls == [{"apply_nli": True, "rows": 0}], gate_calls
    CONTROLS.append({"id": "UP-C01", "description": "--nli independently invokes gate: rejected audit false positive",
                     "observed": {"actual_run_case_gate_calls": gate_calls,
                                  "actual_guard": "if FIX_QUOTE_GATE or FIX_NLI"},
                     "defect_reproduced": False, "expected_behavior_verified": True})
    sw.configure(sw.BASELINES["B0"], {"groups": "false"})
    record("UP-R35", "Programmatic configure accepts textual false as a truthy enabled group flag",
           {"stored_value": eng.USE_CRITERION_GROUPS, "effective_bool": bool(eng.USE_CRITERION_GROUPS)},
           bool(eng.USE_CRITERION_GROUPS))


def retrieval_probes(tmp):
    obj = object.__new__(ret.TrialRetriever)
    obj.n = 2
    obj.meta = [{"source": "fixture", "article_id": "", "title": title, "section_path": ""} for title in ["Disease Alpha", "Disease Beta"]]
    obj.doc_key = ["fixture|", "fixture|"]
    obj.text = lambda gid: ["Disease Alpha has fever.", "Disease Beta has rash."][gid]
    passage = obj.passage(0)
    record("UP-R36", "Blank article_id causes neighbour assembly across different articles",
           passage, passage["window_gids"] == [0, 1])
    forms = rr.label_forms("Disease Alpha (severe)", [])
    match = rr.subject_hit("An unrelated condition has severe features.", forms)
    record("UP-R37", "Parenthetical modifier becomes stand-alone subject alias and anchors unrelated passage",
           {"forms": forms, "match": match}, match == "exact_form" and "severe" in forms)
    import numpy as np

    class Tensor:
        def __init__(self, array):
            self.array = np.asarray(array)
            self.dtype = self.array.dtype

        def to(self, *args):
            return self

        @property
        def T(self):
            return Tensor(self.array.T)

        def __matmul__(self, other):
            return Tensor(self.array @ other.array)

        def float(self):
            return self

    requests = []

    def topk(tensor, k, dim):
        requests.append({"k": k, "available": tensor.array.shape[dim]})
        # A transport-free stand-in enforcing the documented top-k contract.
        if k > tensor.array.shape[dim]:
            raise ValueError("fixture top-k contract: k exceeds available dimension")
        raise AssertionError("fixture expects out-of-range request")

    obj.use_dense = True
    obj.device = "cpu"
    obj.encoder = types.SimpleNamespace(encode=lambda *a, **k: np.array([[1.0, 0.0]]))
    obj.dense = Tensor(np.eye(2))
    obj.torch = types.SimpleNamespace(from_numpy=Tensor, topk=topk)
    error = None
    try:
        obj._dense_ranks(["query"], 200)
    except ValueError as exc:
        error = str(exc)
    record("UP-R38", "Dense topk forwards requested pool without min(pool,n), unlike sparse path",
           {"requests": requests, "error": error,
            "execution": "actual _dense_ranks with lightweight tensor/top-k contract stand-in; no dense model"},
           requests == [{"k": 200, "available": 2}] and error is not None)


def historical_census():
    """Mechanical exposure/serialization census, not clinical error rates."""
    arms = {
        "old_old": "trial_extraction_x2_oldidxclean_groups.json",
        "free_old": "trial_extraction_x2_oldidxclean_groups_free.json",
        "old_v2": "trial_extraction_x2_v2idxclean_groups.json",
        "free_v2": "trial_extraction_x2_v2idxclean_groups_free.json",
    }
    counts = {}
    for arm, name in arms.items():
        path = DATA / name
        if not path.exists() or path.read_bytes()[:60].startswith(b"version https://git-lfs"):
            counts[arm] = {"status": "source_not_locally_available"}
            continue
        records = json.loads(path.read_text())
        c = Counter()
        examples = {}
        for record in records:
            for i, a in enumerate(record["assertions"]):
                c["assertions"] += 1
                for field in ["_passage_sha1", "_passage", "_cache_key", "_source_gid", "_focus", "_title"]:
                    c["has_" + field] += int(bool(a.get(field)))
                rel = a.get("relation")
                if isinstance(rel, str) and rel != rel.strip().lower():
                    c["relation_noncanonical_case_or_space"] += 1
                    examples.setdefault("noncanonical_relation", {"case_key": record["case_key"], "raw_index": i, "relation": rel})
                pol = a.get("polarity")
                if pol not in {"asserted", "negated"}:
                    c["noncanonical_polarity"] += 1
                    examples.setdefault("noncanonical_polarity", {"case_key": record["case_key"], "raw_index": i, "polarity": pol})
                cg = a.get("criterion_group") or {}
                if isinstance(cg, dict) and cg.get("group_id"):
                    c["group_member_rows"] += 1
                    if cg.get("logic") is None:
                        c["group_member_without_logic"] += 1
                th = a.get("threshold") or {}
                if isinstance(th, dict) and th.get("value_high") is not None:
                    c["rows_with_upper_threshold"] += 1
            for f in record["findings"]:
                c["findings"] += 1
                c["regex_backfilled_findings"] += int(bool(f.get("_backfill")))
        counts[arm] = {"counts": dict(c), "examples": examples,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    retrieval = {}
    for tag in ["oldidx", "v2idx"]:
        path = DATA / f"trial_retrieval_x2_{tag}.json"
        if not path.exists() or path.read_bytes()[:60].startswith(b"version https://git-lfs"):
            retrieval[tag] = {"status": "source_not_locally_available"}
            continue
        seen = Counter()
        c = Counter()
        for record in json.loads(path.read_text()):
            for label, bundle in record["retrieved"].items():
                for p in bundle["passages"]:
                    c["exposures"] += 1
                    c["over_6000_chars"] += int(len(p["text"]) > 6000)
                    payload = {"focus_disease": label, "source": p["source"], "document_title": p["title"],
                               "section_path": p["section_path"], "context_hint": ex.context_hint(p["source"], p["section_path"], p["title"]),
                               "passage": p["text"][:6000]}
                    seen[ex.cache_key("guideline_groups", payload, "meta-llama/llama-3.3-70b-instruct")] += 1
        c["unique_jobs"] = len(seen)
        c["repeated_job_exposures"] = sum(v - 1 for v in seen.values())
        c["repeated_payloads"] = sum(v > 1 for v in seen.values())
        retrieval[tag] = dict(c)
    return {"definition": "serialization and exposure counts only; no new clinical fidelity denominator",
            "arms": counts, "retrieval": retrieval}


def main():
    logs = io.StringIO()
    with tempfile.TemporaryDirectory(prefix="upstream_defects_") as directory, contextlib.redirect_stdout(logs):
        tmp = Path(directory)
        cache_probes(tmp)
        parser_manifest = llm_parser_probes()
        extraction_and_gate_probes(tmp)
        backfill_and_nl_probes()
        nli_probes(tmp)
        cli_probes(tmp)
        retrieval_probes(tmp)
    files = ["run_trial_extraction.py", "gate_assertions.py", "nli_verify_assertions.py", "extract_nl_rules.py",
             "run_mechanical_engine.py", "sweep_fixes.py", "trial_retriever.py", "run_trial_retrieval.py"]
    result = {"schema_version": "upstream_reproductions/1", "baseline_commit": BASE,
              "status": "observed_defects_reproduced_not_fixed", "network_calls": 0,
              "production_modifications": 0, "reproductions": RESULTS,
              "reproduction_count": len(RESULTS), "all_assertions_passed": True,
              "controls": CONTROLS, "control_count": len(CONTROLS),
              "source_manifest": [{"path": str((CODE / f).relative_to(REPO)),
                                   "sha256": hashlib.sha256((CODE / f).read_bytes()).hexdigest()} for f in files] + [parser_manifest],
              "historical_census": historical_census(),
              "limits": ["Synthetic defect witnesses do not estimate prevalence or clinical effect.",
                         "Dense top-k witness invokes implementation with a lightweight tensor contract stand-in; no torch/model loaded.",
                         "Cache race proves duplicate dispatch, not historical cache corruption.",
                         "NLI, grounded backfill and NL excerpts are outside frozen B1/S7 historical four arms.",
                         "No proposed repair or clinical diagnosis accuracy is validated."]}
    path = HERE / "reproduce_upstream_defects_results.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"reproduction_count": len(RESULTS), "control_count": len(CONTROLS), "all_assertions_passed": True,
                      "output": str(path.relative_to(REPO))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
