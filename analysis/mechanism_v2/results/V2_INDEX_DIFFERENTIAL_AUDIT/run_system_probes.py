#!/usr/bin/env python3
"""Bounded mechanism probes on frozen rules/facts/candidate lists.

These switches are not asserted to be clinical fixes. F10 only pools atomic
layer-3 votes; it leaves groups, confirmations, eliminations and layer 4 intact.
No-embedding keeps lexical/marker matching, and cannot equalize historical
embedding coverage. Removing confirmation priority changes ranking only.
"""
import copy
import gzip
import hashlib
import json
from collections import defaultdict
from replay_audit import (OUT, CODE, SRC, PREVIOUS, ARM_IDS, load, run, write_json,
                          baseline_projection, sha)

PROBES = {
    "baseline": {},
    "no_embedding_fallback": {"config": {"embed_tau": 0.0}},
    "atomic_finding_pool_beta1": {"config": {"finding_pool_beta": 1.0}},
    "all_is_not_automatic_necessity": {"config": {"group_all_required": False}},
    "no_layer4_penalties": {"intervention": {"block_layer4": [{}]}},
    "no_confirmation_ranking_priority": {"postrank": True},
}


def rank_only(pack, task):
    pack = copy.deepcopy(pack)
    r = pack["result"]
    order = {c["label"]: i for i, c in enumerate(task["candidates"])}
    r["ranking"].sort(key=lambda v: (bool(v["eliminated"]), -v["score"], order[v["label"]]))
    for i, v in enumerate(r["ranking"], 1): v["_audit_rank"] = i
    r["top1"] = r["ranking"][0]["label"]
    r["top1_is_gold"] = r["top1"] in r["gold_labels_in_set"]
    r["gold_rank"] = next((i for i, v in enumerate(r["ranking"], 1) if v["label"] in r["gold_labels_in_set"]), None)
    r["gold_eliminated"] = [v["label"] for v in r["ranking"] if v["label"] in r["gold_labels_in_set"] and v["eliminated"]]
    pack["intervention"] = {"postranking_key": ["eliminated", "negative_score", "original_candidate_order"]}
    pack["applied_interventions"] = [{"stage": "postranking", "action": "remove_confirmation_count_from_sort_key_only"}]
    return pack


def metric(rows):
    return {"n": len(rows), "top1": sum(r["gold_rank"] == 1 for r in rows),
            "top3": sum(r["gold_rank"] <= 3 for r in rows),
            "mrr": sum(1 / r["gold_rank"] for r in rows) / len(rows),
            "per_case": {r["case_key"]: r["gold_rank"] for r in rows}}


def main():
    rows = []
    validation = {"baseline_equality_checks": [], "score_reconstruction_checks": 0,
        "production_source_sha256": sha(CODE / "run_mechanical_engine.py"),
        "replay_source_sha256": sha(OUT / "replay_audit.py"),
        "embedding_sha256": sha(SRC / "join_embeddings.npz"),
        "corpus_lift_sha256": sha(SRC / "corpus_lift_table_all4.json")}
    prior = [{x["case_key"]: x for x in json.loads((PREVIOUS / f"cohort_trace_{arm}_default_stale.json").read_text())}
             for arm in range(4)]
    for task in load("trial_tasks_11_all4.json"):
        key = task["case_key"]
        saved = []
        for arm in range(4):
            baseline = run(key, arm, detailed=False)
            eq = baseline_projection(baseline["result"]) == prior[arm][key]
            validation["baseline_equality_checks"].append({"case_key": key, "arm": ARM_IDS[arm], "pass": eq})
            assert eq
            base = {v["label"]: v for v in baseline["result"]["ranking"]}
            for name, params in PROBES.items():
                if name == "baseline": pack = baseline
                elif params.get("postrank"): pack = rank_only(baseline, task)
                else: pack = run(key, arm, detailed=False, **params)
                validation["score_reconstruction_checks"] += len(pack["score_reconstruction"])
                assert all(c["pass"] for c in pack["score_reconstruction"])
                r = pack["result"]
                sig = {"engine": pack["effective_engine_flags"], "intervention": pack["intervention"],
                    "gate_scope": pack["gate_source_scope"], "production": validation["production_source_sha256"],
                    "embedding": validation["embedding_sha256"], "lift": validation["corpus_lift_sha256"]}
                digest = hashlib.sha256(json.dumps(sig, sort_keys=True).encode()).hexdigest()
                pack["probe"] = name
                pack["configuration_sha256"] = digest
                saved.append(pack)
                candidates = []
                for v in r["ranking"]:
                    b = base[v["label"]]
                    candidates.append({"candidate": v["label"], "rank": v["_audit_rank"], "score": v["score"],
                        "score_delta": v["score"] - b["score"], "baseline_rank": b["_audit_rank"],
                        "elimination_count": len(v["eliminated"]), "confirmation_count": len(v["confirmed"]),
                        "layer4_count": len(v.get("layer4_penalties", [])),
                        "actual_layer4_penalties_removed": len(b.get("layer4_penalties", [])) - len(v.get("layer4_penalties", [])),
                        "n_assertions": v["n_assertions"], "n_joined": v["n_joined"]})
                rows.append({"case_key": key, "arm": ARM_IDS[arm], "probe": name, "configuration_sha256": digest,
                    "gold_rank": r["gold_rank"], "top1": r["top1"], "baseline_gold_rank": baseline["result"]["gold_rank"],
                    "gold_eliminated": r["gold_eliminated"], "candidates": candidates,
                    "applied_hook_count": len(pack["applied_interventions"]),
                    "actual_layer4_penalties_removed": sum(v["actual_layer4_penalties_removed"] for v in candidates)})
            print(key, ARM_IDS[arm], "six probe records", flush=True)
        write_json(OUT / "replay_outputs" / (key.replace("/", "__") + "__system_probes.json.gz"), saved)
        write_json(OUT / "system_probe_results.json", rows)
    agg = []
    for arm in ARM_IDS:
        for probe in PROBES:
            agg.append({"arm": arm, "probe": probe, **metric([r for r in rows if r["arm"] == arm and r["probe"] == probe])})
    write_json(OUT / "system_probe_metrics.json", agg)
    validation["passed"] = len(validation["baseline_equality_checks"]) == 44 and all(c["pass"] for c in validation["baseline_equality_checks"])
    validation["actual_engine_replays"] = len(validation["baseline_equality_checks"]) * 5
    validation["actual_engine_score_reconstructions"] = validation["score_reconstruction_checks"] // 6 * 5
    validation["postranking_reused_score_records"] = validation["score_reconstruction_checks"] // 6
    validation["interpretation"] = "Applied hook count is not cancelled penalty count. L4 cancellation uses baseline-minus-probe actual penalty lists. Postranking probe reuses baseline score reconstruction."
    write_json(OUT / "system_probe_validation.json", validation)


if __name__ == "__main__": main()
