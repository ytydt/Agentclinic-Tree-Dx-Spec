#!/usr/bin/env python3
"""Freeze every read-only data/code dependency of the offline replay."""
import json
from replay_audit import OUT, SRC, CODE, PREVIOUS, ARMS, sha, write_json

def main():
    paths = [CODE / name for name in ["run_mechanical_engine.py", "gate_assertions.py", "sweep_fixes.py", "measure_2x2_groups.py"]]
    paths += [SRC / name for name in ["trial_tasks_11_all4.json", "join_embeddings.npz", "corpus_lift_table_all4.json",
        "trial_retrieval_k30.json", *sorted({a[1] for a in ARMS} | {a[2] for a in ARMS})]]
    paths += [PREVIOUS / "extraction_job_manifest.jsonl"]
    paths += [PREVIOUS / f"cohort_trace_{arm}_default_stale.json" for arm in range(4)]
    write_json(OUT / "replay_dependency_manifest.json", {
        "baseline_commit": "6fa8fd7aa2548cc01ac81f2d5261801190244d27",
        "F7_EXTRA_RETRIEVAL": "explicitly removed",
        "F7_default_lookup_file": "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_retrieval_k30.json",
        "network_or_new_LLM_calls": 0,
        "source_code_modification": "none; in-memory tracing copy only",
        "files": [{"path": str(p.relative_to(SRC.parent)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in paths]})

if __name__ == "__main__": main()
