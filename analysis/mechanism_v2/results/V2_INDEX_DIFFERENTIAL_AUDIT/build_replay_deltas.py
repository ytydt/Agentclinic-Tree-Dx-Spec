#!/usr/bin/env python3
"""Exact accounting of full replay scores. Repetition is not labelled invalid.

The decomposition is an arithmetic identity, not an additive causal model.
Common/added/removed findings are literal normalized fact labels; they do not
establish equivalent clinical scope or valid binding. Group credit is kept as
one separate program contribution rather than allocated to its leaf findings.
"""
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from replay_audit import OUT, ARM_IDS, load, pack_path, write_json, eng


def read_pack(key, arm):
    with gzip.open(pack_path(key, arm), "rt") as f: return json.load(f)


def contributor(c):
    return {k: c.get(k) for k in ["why", "predicate", "finding", "delta", "n_claimants",
        "_audit_raw_ids", "_audit_representative_raw_id", "_audit_representative_raw_ids",
        "_audit_effective_score_delta", "_audit_relation", "_audit_polarity", "_audit_modality",
        "_audit_join", "_audit_source", "_audit_stage", "_audit_group_key"] if k in c}


def decompose(pack):
    out = {}
    for v in pack["result"]["ranking"]:
        facts = defaultdict(lambda: {"atomic": [], "confirmation": [], "positive": 0., "negative": 0.})
        groups = []
        for c in v["contributions"]:
            stage = c["_audit_stage"]
            if stage == "group":
                groups.append(contributor(c))
            else:
                f = facts[eng.norm(c.get("finding"))]
                kind = "atomic" if stage == "atomic_score" else "confirmation"
                f[kind].append(contributor(c))
                amount = c["_audit_effective_score_delta"]
                f["positive" if amount > 0 else "negative"] += amount
        for f in facts.values():
            atoms = f["atomic"]
            f["n_atomic_votes"] = len(atoms)
            f["repeated_atomic_votes_beyond_one"] = max(0, len(atoms) - 1)
            amounts = [max(0, c["_audit_effective_score_delta"]) for c in atoms]
            f["positive_atomic_mass_beyond_strongest_single_vote"] = sum(amounts) - max(amounts, default=0)
            f["net_score"] = f["positive"] + f["negative"]
        atoms = [c for c in v["contributions"] if c["_audit_stage"] == "atomic_score"]
        conf = [c for c in v["contributions"] if c["_audit_stage"] == "confirmation_score"]
        gr = [c for c in v["contributions"] if c["_audit_stage"] == "group"]
        score_parts = {
            "atomic_positive": sum(c["_audit_effective_score_delta"] for c in atoms if c["_audit_effective_score_delta"] > 0),
            "atomic_negative": sum(c["_audit_effective_score_delta"] for c in atoms if c["_audit_effective_score_delta"] < 0),
            "confirmation": sum(c["_audit_effective_score_delta"] for c in conf),
            "group": sum(c["_audit_effective_score_delta"] for c in gr),
            "layer4": -0.5 * len(v.get("layer4_penalties", []))}
        score_parts["rounding"] = v["score"] - sum(score_parts.values())
        raw = pack["stages"]["bound"].get(v["label"], [])
        out[v["label"]] = {
            "rank": v["_audit_rank"], "score": v["score"],
            "eliminated": v["eliminated"], "confirmed": v["confirmed"],
            "score_parts": score_parts, "fact_scores": dict(facts), "group_contributions": groups,
            "layer4_penalties": v.get("layer4_penalties", []),
            "n_bound_deduplicated": len(raw), "n_bound_raw_support": sum(a.get("_support", 1) for a in raw),
            "n_atomic_votes": len(atoms), "n_atomic_facts": len({eng.norm(c.get("finding")) for c in atoms}),
            "repeated_atomic_votes_beyond_one": sum(f["repeated_atomic_votes_beyond_one"] for f in facts.values()),
            "positive_atomic_mass_beyond_strongest_single_vote": sum(f["positive_atomic_mass_beyond_strongest_single_vote"] for f in facts.values()),
            "empty_zero_score": not raw and v["score"] == 0,
            "rank_key": [bool(v["eliminated"]), -len(v["confirmed"]), -v["score"]]}
    return out


def stage_counts(pack):
    """Structural observations, not semantic-error prevalence labels."""
    st = pack["stages"]
    post = {a["_audit_raw_index"]: a for a in st["post_gate"]}
    stats = Counter()
    for a in st["raw"]:
        b = post.get(a["_audit_raw_index"])
        if b is None:
            stats["dropped_by_gate"] += 1
            continue
        for field in ["relation", "polarity", "modality", "context_type", "criterion_group"]:
            if a.get(field) != b.get(field): stats[field + "_changed_in_enum_or_gate"] += 1
        if b.get("_gate"): stats["rows_with_gate_annotation"] += 1
    for label, rows in st["bound"].items():
        for a in rows:
            stats["postdedup_bind_" + a.get("_bind", "unknown")] += 1
            if a.get("_finding"): stats["postdedup_join_" + a.get("_join", "unknown")] += 1
            if a.get("_support", 1) > 1: stats["representatives_with_multiple_raw_support"] += 1
            if post[a["_audit_raw_index"]].get("modality") != a.get("modality"):
                stats["modality_upgraded_by_crossrow_dedup"] += 1
    for groups in st["groups"].values():
        stats["assembled_multimember_engine_groups"] += len(groups)
        for group in groups:
            members = group["members"]
            stats["groups_with_mixed_relation"] += len({a.get("relation") for a in members}) > 1
            stats["groups_spanning_cache_jobs"] += len({a.get("_audit_source", {}).get("cache_id") for a in members}) > 1
            facts = [a["_finding"]["label"] for a in members if a.get("_finding") and a["_finding"].get("polarity") == "present"]
            stats["groups_counting_same_present_finding_repeatedly"] += len(facts) > len(set(facts))
            stats["groups_with_negated_members"] += any(a.get("polarity") == "negated" for a in members)
            stats["groups_with_numeric_threshold_members"] += any((a.get("threshold") or {}).get("value") is not None for a in members)
    return {"case_key": pack["case_key"], "arm": pack["arm"], "counts": dict(stats)}


def main():
    all_decomposed = {}
    checks = []
    repetition = []
    stages = []
    for task in load("trial_tasks_11_all4.json"):
        key = task["case_key"]
        all_decomposed[key] = {}
        for arm in range(4):
            pack = read_pack(key, arm)
            stages.append(stage_counts(pack))
            d = decompose(pack)
            all_decomposed[key][ARM_IDS[arm]] = d
            for label, v in d.items():
                checks.append({"case_key": key, "arm": ARM_IDS[arm], "candidate": label,
                    "pass": abs(sum(v["score_parts"].values()) - v["score"]) < 1e-8})
                repetition.append({"case_key": key, "arm": ARM_IDS[arm], "candidate": label,
                    "legacy_accepted_label": label in task["gold_labels_in_set"],
                    **{k: v[k] for k in ["rank", "score", "n_atomic_votes", "n_atomic_facts",
                        "repeated_atomic_votes_beyond_one", "positive_atomic_mass_beyond_strongest_single_vote",
                        "n_bound_deduplicated", "n_bound_raw_support", "empty_zero_score"]},
                    "atomic_positive_mass": v["score_parts"]["atomic_positive"],
                    "zero_score_tied_candidates": sum(w["score"] == 0 and w["rank_key"][:2] == v["rank_key"][:2] for w in d.values()) if v["score"] == 0 else 0})
        write_json(OUT / "replay_outputs" / (key.replace("/", "__") + "__score_accounting.json.gz"), all_decomposed[key])
    delta_rows = []
    for key, arms in all_decomposed.items():
        for a, b in [(0, 2), (1, 3), (0, 1), (2, 3)]:
            for label, old in arms[ARM_IDS[a]].items():
                new = arms[ARM_IDS[b]][label]
                old_f, new_f = old["fact_scores"], new["fact_scores"]
                shared = set(old_f) & set(new_f)
                added, removed = set(new_f) - set(old_f), set(old_f) - set(new_f)
                fd = {
                    "shared_fact_score_change": sum(new_f[f]["net_score"] - old_f[f]["net_score"] for f in shared),
                    "added_fact_score": sum(new_f[f]["net_score"] for f in added),
                    "removed_fact_score": -sum(old_f[f]["net_score"] for f in removed),
                    "group_score_change": new["score_parts"]["group"] - old["score_parts"]["group"],
                    "layer4_score_change": new["score_parts"]["layer4"] - old["score_parts"]["layer4"],
                    "rounding_change": new["score_parts"]["rounding"] - old["score_parts"]["rounding"]}
                delta = new["score"] - old["score"]
                assert abs(sum(fd.values()) - delta) < 1e-8, (key, label, fd, delta)
                delta_rows.append({"case_key": key, "old_arm": ARM_IDS[a], "new_arm": ARM_IDS[b],
                    "candidate": label, "old_rank": old["rank"], "new_rank": new["rank"],
                    "old_score": old["score"], "new_score": new["score"], "score_delta": delta,
                    "old_eliminated": bool(old["eliminated"]), "new_eliminated": bool(new["eliminated"]),
                    "old_confirmation_count": len(old["confirmed"]), "new_confirmation_count": len(new["confirmed"]),
                    "stage_score_deltas": {k: new["score_parts"][k] - old["score_parts"][k] for k in old["score_parts"]},
                    "fact_identity_decomposition": fd,
                    "shared_facts": [{"finding": f, "old_score": old_f[f]["net_score"], "new_score": new_f[f]["net_score"],
                        "delta": new_f[f]["net_score"] - old_f[f]["net_score"],
                        "old_atomic_votes": old_f[f]["n_atomic_votes"], "new_atomic_votes": new_f[f]["n_atomic_votes"]}
                        for f in sorted(shared)],
                    "added_facts": [{"finding": f, "score": new_f[f]["net_score"], "atomic_votes": new_f[f]["n_atomic_votes"]} for f in sorted(added)],
                    "removed_facts": [{"finding": f, "score": old_f[f]["net_score"], "atomic_votes": old_f[f]["n_atomic_votes"]} for f in sorted(removed)]})
    write_json(OUT / "candidate_delta_ledger.json.gz", delta_rows)
    write_json(OUT / "repeated_fact_vote_ledger.json", repetition)
    write_json(OUT / "stage_change_counts.json", stages)
    write_json(OUT / "score_decomposition_validation.json", {"checks": checks, "all_pass": all(c["pass"] for c in checks),
        "candidate_decompositions": len(checks), "candidate_pair_deltas": len(delta_rows),
        "interpretation": "Arithmetic accounting only; repeated votes are not automatically invalid, and score deltas are not additive causal effects on rank."})
    print("candidate score decompositions", len(checks), "pair deltas", len(delta_rows))


if __name__ == "__main__": main()
