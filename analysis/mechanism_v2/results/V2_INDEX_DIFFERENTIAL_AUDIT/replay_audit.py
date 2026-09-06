#!/usr/bin/env python3
"""Full, provenance-linked replay of the historical 2x2 mechanical engine.

Production files are never modified. We compile an instrumented copy of the
installed run_case source; every surgery has an exact occurrence assertion.
Default replays retain B1/S7 and historical default F7 source lookup. Audit
metadata does not participate in production decisions. This module is
single-process/single-thread: engine configuration and hooks are module globals.

API: run(case_key, arm=0, intervention=None, config=None, detailed=True).
Interventions (all optional):
  delete_raw_ids: original merged-case extraction row indices, before gates;
  patch_raw: [{raw_id: int, changes: {...}}], before gates;
  append_raw: [{assertion: {...}, source_arm: optional, source_raw_id: optional}],
      before gates; appended ids begin at the original merged-case row count;
  force_bindings: [{raw_ids: [...], target_candidate: label}], after ordinary
      subject binding, before deduplication (explicit audit routing override);
  block_joins: [{candidate: label, raw_ids: [...], finding: optional_label}],
      after production best-match choice, before claimants/groups; no fallback;
  remove_contributions: same selectors, numeric score only, before layer 4;
      elimination and confirmation statuses are deliberately retained;
  block_layer4: selectors on the source candidate and assertion.
Selectors match a representative OR any of its deduplicated support raw rows.
Deleting one support raw row instead may expose a different representative.
"""
from __future__ import annotations

import argparse
import ast
import copy
import gzip
import hashlib
import inspect
import json
import os
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SRC = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
CODE = ROOT / "analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
PREVIOUS = OUT.parent / "POST_V2_RULE_SEMANTICS_AUDIT"
sys.path.insert(0, str(CODE))
import run_mechanical_engine as eng
import sweep_fixes as sw
import gate_assertions as gate
from measure_2x2_groups import ARMS

ARM_IDS = ["old_old", "free_old", "old_v2", "free_v2"]
for _name in ["norm", "tokens", "embed_sim"]:
    if not hasattr(getattr(eng, _name), "cache_info"):
        setattr(eng, _name, lru_cache(maxsize=500000)(getattr(eng, _name)))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=8)
def load(name):
    return json.loads((SRC / name).read_text())


@lru_cache(maxsize=1)
def job_index():
    out = defaultdict(list)
    for line in (PREVIOUS / "extraction_job_manifest.jsonl").read_text().splitlines():
        j = json.loads(line)
        out[j["arm"], j["case_key"]].append(j)
    return out


def row_ids(a):
    return a.get("_audit_support_raw_ids", [a["_audit_raw_index"]])


def row_meta(a):
    return {"_audit_raw_ids": list(row_ids(a)),
            "_audit_representative_raw_id": a["_audit_raw_index"],
            "_audit_source": a.get("_audit_source"),
            "_audit_relation": a.get("relation"),
            "_audit_polarity": a.get("polarity"),
            "_audit_modality": a.get("modality"),
            "_audit_context_type": a.get("context_type"),
            "_audit_gate": a.get("_gate"),
            "_audit_bind": a.get("_bind"),
            "_audit_join": a.get("_join"),
            "_audit_threshold": a.get("threshold")}


def selected(selector, label, ids, finding=None):
    if selector.get("candidate") is not None and selector["candidate"] != label:
        return False
    if "raw_ids" in selector and not set(selector["raw_ids"]) & set(ids):
        return False
    if selector.get("finding") is not None and selector["finding"] != finding:
        return False
    return True


def _capture(name, value):
    if eng._audit_state["detailed"]:
        eng._audit_state["stages"][name] = copy.deepcopy(value)


def _before_claimants(bound):
    for label, rows in bound.items():
        for a in rows:
            f = a.get("_finding")
            for sel in eng._audit_state["intervention"].get("block_joins", []):
                if f and selected(sel, label, row_ids(a), f["label"]):
                    eng._audit_state["applied"].append({"stage": "after_join_before_claimants", "candidate": label,
                        **row_meta(a), "finding": copy.deepcopy(f), "action": "block_join_no_fallback"})
                    a["_finding"] = None
                    a["_audit_blocked_join"] = a.pop("_join", None)
                    break


def _force_bindings(bound):
    for sel in eng._audit_state["intervention"].get("force_bindings", []):
        target = sel["target_candidate"]
        for label, rows in list(bound.items()):
            if label == target: continue
            for a in list(rows):
                if a["_audit_raw_index"] in sel["raw_ids"]:
                    rows.remove(a)
                    a["_audit_original_bound_candidate"] = label
                    bound[target].append(a)
                    eng._audit_state["applied"].append({"stage": "after_subject_bind_before_dedup",
                        "raw_id": a["_audit_raw_index"], "from": label, "to": target,
                        "action": "force_candidate_binding"})


def _annotate(value, local, kind):
    """Called only at original append sites; returns original dict plus metadata."""
    value = dict(value)
    is_group = kind == "group" or (kind == "elimination" and value.get("rule") == "criterion_group_violated")
    if is_group:
        members = local["members"]
        value.update({"_audit_raw_ids": sorted({i for m in members for i in row_ids(m)}),
                      "_audit_representative_raw_ids": [m["_audit_raw_index"] for m in members],
                      "_audit_group_key": list(local["key"]),
                      "_audit_members": [row_meta(m) for m in members],
                      "_audit_satisfied_raw_ids": [m["_audit_raw_index"] for m in local.get("sat", [])],
                      "_audit_violated_raw_ids": [m["_audit_raw_index"] for m in local.get("vio", [])],
                      "_audit_required": local.get("required"),
                      "_audit_soft_group": local.get("soft_group"),
                      "_audit_weight": local.get("w"),
                      "_audit_specificity_max": local.get("spec")})
    else:
        a = local["a"]
        value.update(row_meta(a))
        if a.get("_finding"):
            value["_audit_finding"] = copy.deepcopy(a["_finding"])
    value["_audit_stage"] = kind
    if kind == "group":
        value["_audit_score_delta"] = round(local["delta"], 3)
    elif kind == "atomic_score":
        value["_audit_score_delta"] = local["delta"]
        value["_audit_weight"] = local.get("w")
    elif kind == "confirmation_score":
        value["_audit_score_delta"] = 2.0
    elif kind == "layer4":
        value["_audit_score_delta"] = -0.5
    return value


def _score_adjust(label, score, contributions, pooled):
    reduction = 0.0
    for i, c in enumerate(contributions):
        c["_audit_contribution_id"] = i
        effective = c["_audit_score_delta"]
        if eng.FINDING_POOL_BETA and c["_audit_stage"] == "atomic_score":
            effective /= pooled[eng.norm(c.get("finding"))][1] ** eng.FINDING_POOL_BETA
        c["_audit_effective_score_delta"] = effective
        if any(selected(sel, label, c["_audit_raw_ids"], c.get("finding"))
               for sel in eng._audit_state["intervention"].get("remove_contributions", [])):
            reduction += effective
            c["_audit_removed_numeric_only"] = True
            eng._audit_state["applied"].append({"stage": "postscore_before_layer4", "candidate": label,
                "contribution_id": i, "raw_ids": c["_audit_raw_ids"], "removed_delta": effective})
    return score - reduction


def _block_layer4(label, a):
    hit = any(selected(sel, label, row_ids(a), (a.get("_finding") or {}).get("label"))
              for sel in eng._audit_state["intervention"].get("block_layer4", []))
    if hit:
        eng._audit_state["applied"].append({"stage": "layer4", "action": "skip_directional_penalty",
            "candidate": label, **row_meta(a)})
    return hit


def _finish(local):
    _capture("bound", local["bound"])
    _capture("groups", {label: [{"key": list(k), "members": v} for k, v in gs.items()]
                        for label, gs in local["groups"].items()})
    _capture("claimants", {k: sorted(v) for k, v in local["claimants"].items()})
    eng._audit_state["score_reconstruction"] = []
    for label, v in local["verdicts"].items():
        base = sum(c["_audit_effective_score_delta"] for c in v["contributions"]
                   if not c.get("_audit_removed_numeric_only"))
        reconstructed = round(base, 3)
        for penalty in v.get("layer4_penalties", []):
            reconstructed = round(reconstructed + penalty["_audit_score_delta"], 3)
        ok = abs(reconstructed - v["score"]) < 1e-8
        eng._audit_state["score_reconstruction"].append({"candidate": label, "pre_layer4_exact": base,
            "pre_layer4_rounded": round(base, 3), "layer4_n": len(v.get("layer4_penalties", [])),
            "reconstructed": reconstructed, "actual": v["score"], "pass": ok})
        if not ok:
            raise AssertionError((label, reconstructed, v["score"]))


class AppendMetadata(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "append" or not node.args:
            return node
        target = node.func.value
        if not isinstance(node.args[0], ast.Dict):
            return node
        d = node.args[0]
        keys = {k.value: v for k, v in zip(d.keys, d.values) if isinstance(k, ast.Constant)}
        kind = None
        if isinstance(target, ast.Name):
            if target.id == "contributions":
                kind = "group" if "n_members" in keys else "atomic_score" if "n_claimants" in keys else "confirmation_score"
            elif target.id == "eliminated": kind = "elimination"
            elif target.id == "confirmed": kind = "confirmation"
        elif isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute) and target.func.attr == "setdefault":
            if target.args and isinstance(target.args[0], ast.Constant) and target.args[0].value == "layer4_penalties":
                kind = "layer4"
        if kind:
            node.args[0] = ast.Call(func=ast.Name(id="_audit_annotate", ctx=ast.Load()),
                args=[d, ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]), ast.Constant(kind)], keywords=[])
        return node


def compile_instrumented():
    text = inspect.getsource(eng.run_case)
    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, (old, text.count(old))
        text = text.replace(old, new)
    replace("def run_case(", "def _audit_run_case(")
    replace("    candidates = task[\"candidates\"]", "    _audit_capture('post_gate', assertions)\n    candidates = task[\"candidates\"]")
    replace("    # ---- dedupe at assertion level, not passage level", "    _audit_force_bindings(bound)\n    _audit_capture('pre_dedup_bound', bound)\n    # ---- dedupe at assertion level, not passage level")
    replace('                a["_support"] = 1', '                a["_support"] = 1\n                a["_audit_support_raw_ids"] = [a["_audit_raw_index"]]')
    replace('                prev["_support"] += 1', '                prev["_support"] += 1\n                prev["_audit_support_raw_ids"].append(a["_audit_raw_index"])')
    replace("    # ---- bind predicates to findings", "    _audit_capture('post_dedup_bound', bound)\n    # ---- bind predicates to findings")
    replace("    # how many candidates claim each finding as their own feature?", "    _audit_capture('joined_before_intervention', bound)\n    _audit_before_claimants(bound)\n    # how many candidates claim each finding as their own feature?")
    replace("        verdicts[label] = {", "        score = _audit_score_adjust(label, score, contributions, pooled)\n        verdicts[label] = {")
    replace('"contributions": contributions[:25]', '"contributions": contributions')
    replace('            comp = a.get("comparator")', '            if _audit_block_layer4(label, a):\n                continue\n            comp = a.get("comparator")')
    replace('    ranked = sorted(verdicts.values(),', '    _audit_finish(locals())\n    ranked = sorted(verdicts.values(),')
    tree = AppendMetadata().visit(ast.parse(text))
    ast.fix_missing_locations(tree)
    for name, func in {"_audit_capture": _capture, "_audit_before_claimants": _before_claimants,
                      "_audit_annotate": _annotate, "_audit_score_adjust": _score_adjust,
                      "_audit_block_layer4": _block_layer4, "_audit_finish": _finish,
                      "_audit_force_bindings": _force_bindings}.items():
        eng.__dict__[name] = func
    exec(compile(tree, "<audit-instrumented-run_case>", "exec"), eng.__dict__)
    return eng._audit_run_case


INSTRUMENTED = compile_instrumented()
_DEFAULT_GATE_INDEX = None


def configure(config=None):
    global _DEFAULT_GATE_INDEX
    os.environ.pop("F7_EXTRA_RETRIEVAL", None)
    # The historical default F7 builds one index from default files. Cache it
    # between cases; no arm-specific replacement is silently made.
    if _DEFAULT_GATE_INDEX is None:
        gate._PASSAGE_INDEX = None
        _DEFAULT_GATE_INDEX = gate._load_passage_index()
    gate._PASSAGE_INDEX = _DEFAULT_GATE_INDEX
    sw.configure(sw.BASELINES["B1"], {**sw.stacks()["S7_+F7"], **(config or {})})
    eng.DISCRIMINATIVE_ONLY = False
    eng.RIGID_REQUIRED_ANY_MODALITY = False
    eng.RIGID_SUFFICIENT_CONFIRMS = False
    eng.RIGID_PATHO_READS_THRESHOLD = False
    eng.RIGID_REQUIRED_CLOSED_WORLD = False
    eng.NONCRITERION_INERT = bool((config or {}).get("noncriterion_inert", False))
    eng.FINDING_POOL_BETA = float((config or {}).get("finding_pool_beta", 0))
    eng.LAYER3_DROP = set()


def run(case_key, arm=0, intervention=None, config=None, detailed=True):
    """Replay one case. Raw indices always refer to original merged extraction."""
    if isinstance(arm, str): arm = ARM_IDS.index(arm)
    task = next(t for t in load("trial_tasks_11_all4.json") if t["case_key"] == case_key)
    ext = copy.deepcopy(next(e for e in load(ARMS[arm][1]) if e["case_key"] == case_key))
    intervention = copy.deepcopy(intervention or {})
    for i, a in enumerate(ext["assertions"]):
        a["_audit_raw_index"] = i
    for j in job_index()[ARM_IDS[arm], case_key]:
        for i in range(j["assertion_start"], j["assertion_stop_exclusive"]):
            ext["assertions"][i]["_audit_source"] = {k: j[k] for k in ["cache_id", "gid", "source", "passage_sha256", "focus", "doc_key"]}
            ext["assertions"][i]["_audit_source"]["normalized_local_index"] = i - j["assertion_start"]
            ext["assertions"][i]["_audit_source"]["job_assertion_start"] = j["assertion_start"]
    state = {"detailed": detailed, "stages": {}, "intervention": intervention, "applied": []}
    eng._audit_state = state
    _capture("raw", ext["assertions"])
    original_row_count = len(ext["assertions"])
    for offset, addition in enumerate(intervention.get("append_raw", [])):
        a = copy.deepcopy(addition["assertion"])
        a["_audit_raw_index"] = original_row_count + offset
        a.pop("_audit_support_raw_ids", None)
        a["_audit_injected_from"] = {k: addition.get(k) for k in ["source_arm", "source_raw_id"]}
        ext["assertions"].append(a)
        state["applied"].append({"stage": "raw_before_gate", "action": "append_audit_counterfactual",
            "raw_id": a["_audit_raw_index"], "source": a["_audit_injected_from"], "assertion": copy.deepcopy(a)})
    deletes = set(intervention.get("delete_raw_ids", []))
    for a in ext["assertions"]:
        for change in intervention.get("patch_raw", []):
            if change["raw_id"] == a["_audit_raw_index"]:
                state["applied"].append({"stage": "raw_before_gate", "raw_id": a["_audit_raw_index"],
                    "action": "patch", "before": copy.deepcopy(a), "changes": change["changes"]})
                a.update(copy.deepcopy(change["changes"]))
        if a["_audit_raw_index"] in deletes:
            state["applied"].append({"stage": "raw_before_gate", "raw_id": a["_audit_raw_index"], "action": "delete"})
    ext["assertions"] = [a for a in ext["assertions"] if a["_audit_raw_index"] not in deletes]
    configure(config)
    result = INSTRUMENTED(task, ext)
    for i, v in enumerate(result["ranking"], 1): v["_audit_rank"] = i
    answer = {"case_key": case_key, "arm": ARM_IDS[arm], "arm_name": ARMS[arm][0],
              "original_raw_count": original_row_count,
              "extraction_file": ARMS[arm][1], "retrieval_file": ARMS[arm][2],
              "configuration": {**sw.BASELINES["B1"], **sw.stacks()["S7_+F7"], **(config or {})},
              "gate_source_scope": "historical_default_stale", "intervention": intervention,
              "applied_interventions": state["applied"], "result": result,
              "score_reconstruction": state["score_reconstruction"],
              "effective_engine_flags": {name: getattr(eng, name) for name in ["WEIGHT_SCHEME", "JOIN_MODE",
                  "USE_CRITERION_GROUPS", "CLOSED_WORLD", "FIX_MARKER", "FIX_EMBED_TAU", "FIX_ORGANISM",
                  "FIX_ENUM", "FIX_ANCHOR_EMBED", "GROUP_ALL_IS_REQUIRED", "FIX_QUOTE_GATE", "FIX_NLI",
                  "DISCRIMINATIVE_ONLY", "RIGID_REQUIRED_ANY_MODALITY", "RIGID_SUFFICIENT_CONFIRMS",
                  "RIGID_PATHO_READS_THRESHOLD", "RIGID_REQUIRED_CLOSED_WORLD", "NONCRITERION_INERT",
                  "FINDING_POOL_BETA", "LR_CLIP"]}}
    if detailed:
        answer.update(task=task, findings=ext["findings"], stages=state["stages"])
    return answer


def remove_audit_fields(obj):
    if isinstance(obj, dict):
        return {k: remove_audit_fields(v) for k, v in obj.items() if not k.startswith("_audit")}
    if isinstance(obj, list): return [remove_audit_fields(x) for x in obj]
    return obj


def baseline_projection(result):
    r = remove_audit_fields(result)
    for v in r["ranking"]: v["contributions"] = v["contributions"][:25]
    return r


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2).encode()
    if str(path).endswith(".gz"):
        with path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz: gz.write(encoded)
    else: path.write_bytes(encoded)


def pack_path(case_key, arm):
    return OUT / "replay_outputs" / (case_key.replace("/", "__") + f"__{ARM_IDS[arm]}.json.gz")


def summary_row(pack):
    r = pack["result"]
    return {"case_key": pack["case_key"], "arm": pack["arm"], "gold": r["gold"],
            "gold_labels_in_set": r["gold_labels_in_set"], "gold_rank": r["gold_rank"],
            "top1": r["top1"], "gold_eliminated": r["gold_eliminated"],
            "n_raw": pack.get("original_raw_count", len(pack["stages"]["raw"]) if "raw" in pack.get("stages", {}) else None),
            "n_postgate": r["n_assertions"], "n_bound": r["n_assertions_bound"],
            "n_joined": r["join_stats"]["matched"],
            "n_contributions": sum(len(v["contributions"]) for v in r["ranking"]),
            "n_layer4_penalties": sum(len(v.get("layer4_penalties", [])) for v in r["ranking"]),
            "ranking": [{"rank": i, "candidate": v["label"], "score": v["score"],
                         "n_assertions": v["n_assertions"], "n_joined": v["n_joined"],
                         "n_contributions": len(v["contributions"]), "n_eliminations": len(v["eliminated"]),
                         "n_confirmations": len(v["confirmed"]), "n_layer4": len(v.get("layer4_penalties", []))}
                        for i, v in enumerate(r["ranking"], 1)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="")
    ap.add_argument("--arm", type=int, choices=range(4))
    args = ap.parse_args()
    tasks = load("trial_tasks_11_all4.json")
    output = OUT / "replay_outputs"
    output.mkdir(exist_ok=True)
    validation = {"production_file_sha256": sha(CODE / "run_mechanical_engine.py"),
                  "source_file_sha256": {fn: sha(SRC / fn) for fn in ["trial_tasks_11_all4.json", "join_embeddings.npz", "corpus_lift_table_all4.json", *[x[1] for x in ARMS]]},
                  "baseline": "B1/S7", "gate_scope": "historical_default_stale", "checks": []}
    summaries = []
    for arm in range(4):
        if args.arm is not None and args.arm != arm: continue
        prior = {r["case_key"]: r for r in json.loads((PREVIOUS / f"cohort_trace_{arm}_default_stale.json").read_text())}
        for t in tasks:
            key = t["case_key"]
            if args.case and args.case != key: continue
            pack = run(key, arm)
            projected = baseline_projection(pack["result"])
            equal = projected == prior[key]
            check = {"case_key": key, "arm": ARM_IDS[arm], "matches_prior_full_truncated_result": equal,
                     "candidate_score_reconstructions": len(pack["score_reconstruction"]),
                     "all_scores_reconstructed": all(v["pass"] for v in pack["score_reconstruction"])}
            validation["checks"].append(check)
            if not equal:
                write_json(output / "baseline_mismatch.json", {"new": projected, "previous": prior[key]})
                raise AssertionError(check)
            write_json(pack_path(key, arm), pack)
            summaries.append(summary_row(pack))
            print(ARM_IDS[arm], key, "rank", pack["result"]["gold_rank"], "full contributions", summaries[-1]["n_contributions"], flush=True)
            write_json(OUT / "replay_validation.json", validation)
    write_json(OUT / "replay_summary.json", summaries)
    validation["passed"] = len(validation["checks"]) == (1 if args.case else 11) * (1 if args.arm is not None else 4)
    write_json(OUT / "replay_validation.json", validation)


if __name__ == "__main__": main()
