#!/usr/bin/env python3
"""Reconstruct the four extraction arms from retained raw cache, without calls.

Run from any directory. This writes only into this audit directory. Row indexes
are zero-based indexes in each case's stored assertions array.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(OUT.parent / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"))
import run_trial_extraction as ext

MODEL = "meta-llama/llama-3.3-70b-instruct"
ARMS = [
    ("old_old", "oldidx", False), ("free_old", "oldidx", True),
    ("old_v2", "v2idx", False), ("free_v2", "v2idx", True),
]

def digest(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()

def main():
    tasks = json.loads((LEDGER / "trial_tasks_11_all4.json").read_text())
    taskmap = {x["case_key"]: x for x in tasks}
    summary = {"base_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "model_for_cache_reconstruction": MODEL, "api_calls": 0,
        "index_payload_limit_chars": 6000, "arms": {},
        "limits": ["Cache filename reconstruction identifies raw payload/model/kind; it does not recover a historical prompt or provider version.",
                   "No original runtime environment manifest is retained by the x2 score script."]}
    inputs = {}
    alljobs, changes, passage_registry = [], [], {}
    for arm, idx, free in ARMS:
        rname = f"trial_retrieval_x2_{idx}.json"
        ename = f"trial_extraction_x2_{idx}clean_groups{'_free' if free else ''}.json"
        for name in (rname, ename):
            inputs[name] = digest((LEDGER / name).read_bytes())
        retrieval = json.loads((LEDGER / rname).read_text())
        stored = {e["case_key"]: e for e in json.loads((LEDGER / ename).read_text())}
        kind = "guideline_groups_free" if free else "guideline_groups"
        counts = Counter(); groupstats = Counter(); offsets = Counter()
        row_equal = True; case_equal = True
        cache_ids = set(); phashes = set(); key_to_passages = {}
        for rec in retrieval:
            key = rec["case_key"]
            clean = ext.strip_options(taskmap[key]["vignette"])
            ck = ext.cache_key("case", {"vignette": clean}, MODEL)
            cp = LEDGER / "trial_extraction_cache" / f"{ck}.json"
            if cp.exists():
                cf = json.loads(cp.read_text()).get("findings") or []
                eq = cf == stored[key]["findings"]
                case_equal &= eq; counts["case_cache_exact_matches"] += int(eq)
            else:
                counts["case_cache_missing"] += 1; case_equal = False
            for focus, bundle in rec["retrieved"].items():
                for pas in bundle["passages"]:
                    text = pas["text"][:6000]
                    payload = {"focus_disease": focus, "source": pas["source"],
                               "document_title": pas["title"], "section_path": pas["section_path"],
                               "context_hint": ext.context_hint(pas["source"], pas["section_path"], pas["title"]),
                               "passage": text}
                    cacheid = ext.cache_key(kind, payload, MODEL)
                    cachepath = LEDGER / "trial_extraction_cache" / f"{cacheid}.json"
                    counts["jobs"] += 1; cache_ids.add(cacheid)
                    ph = digest(text); phashes.add(ph)
                    passage_registry[(idx, ph)] = {"index": idx, "passage_sha256": ph,
                        "gid": pas["gid"], "window_gids": pas.get("window_gids"),
                        "doc_key": pas.get("doc_key"), "source": pas["source"],
                        "retrieval_path": str((LEDGER/rname).relative_to(ROOT)),
                        "case_key": key, "focus": focus,
                        "title": pas["title"], "section_path": pas["section_path"],
                        "chars": len(text), "source_chars": len(pas["text"])}
                    counts["truncated_jobs"] += int(len(pas["text"]) > 6000)
                    k = (key, focus, pas["source"], pas["title"], pas["section_path"])
                    key_to_passages.setdefault(k, set()).add(ph)
                    start = offsets[key]
                    if not cachepath.exists():
                        counts["cache_missing"] += 1; row_equal = False
                        continue
                    raw = json.loads(cachepath.read_text())
                    aa = raw.get("assertions") or [] if isinstance(raw, dict) else []
                    counts["empty_cache_jobs"] += int(not aa)
                    for raw_idx, a in enumerate(aa):
                        if not isinstance(a, dict) or not a.get("subject") or not a.get("predicate"):
                            counts["filtered_raw_rows"] += 1; continue
                        a = dict(a); before = a.get("criterion_group")
                        ext.normalise_group(a, groupstats)
                        if before != a.get("criterion_group"):
                            changes.append({"arm": arm, "case_key": key,
                                "assertion_index": offsets[key], "cache_id": cacheid,
                                "raw_index": raw_idx, "before": before, "after": a["criterion_group"]})
                        a.update(_focus=focus, _source=payload["source"], _title=payload["document_title"],
                                 _section=payload["section_path"], _context_hint=payload["context_hint"])
                        rowidx = offsets[key]
                        eq = rowidx < len(stored[key]["assertions"]) and a == stored[key]["assertions"][rowidx]
                        counts["exact_reconstructed_rows"] += int(eq)
                        counts["reconstructed_rows"] += 1
                        row_equal &= eq
                        offsets[key] += 1
                    alljobs.append({"arm": arm, "case_key": key, "focus": focus,
                        "gid": pas["gid"], "doc_key": pas.get("doc_key"),
                        "source": pas["source"], "passage_sha256": ph, "cache_id": cacheid,
                        "assertion_start": start, "assertion_stop_exclusive": offsets[key],
                        "cache_sha256": digest(cachepath.read_bytes()),
                        "raw_assertion_count": len(aa)})
        counts["unique_cache_jobs"] = len(cache_ids)
        counts["unique_passage_texts"] = len(phashes)
        counts["ambiguous_saved_provenance_keys"] = sum(len(v)>1 for v in key_to_passages.values())
        counts["stored_rows"] = sum(len(x["assertions"]) for x in stored.values())
        counts["stored_rows_with_passage_hash"] = sum(bool(a.get("_passage_sha1")) for x in stored.values() for a in x["assertions"])
        row_equal &= all(offsets[k] == len(v["assertions"]) for k,v in stored.items())
        summary["arms"][arm] = {**dict(counts), "all_rows_reconstructed_exactly": row_equal,
            "clean_case_findings_match_cache": case_equal, "normalisation_stats": dict(groupstats)}
    summary["input_sha256"] = inputs
    summary["source_selection"] = {"downloaded_lfs_objects": 0,
        "why": "All four frozen retrieval windows and raw extraction caches are ordinary Git blobs; index regeneration is unnecessary for source-fidelity replay.",
        "extra_source_files": ["data/cpg/raw/pmc_oa/bioc-pmc10971616.json", "data/cpg/text/pmc_oa/pmc-oa-ddx-pmc10971616.txt", "data/corpus/statpearls/statpearls_NBK430685/article-24945.nxml", "data/corpus/statpearls/statpearls_NBK430685/article-29656.nxml"]}
    for name, data in [("provenance_summary.json", summary), ("normalisation_changes.json", changes)]:
        (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
    for name, data in [("extraction_job_manifest.jsonl", alljobs), ("passage_manifest.jsonl", list(passage_registry.values()))]:
        (OUT/name).write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in data))
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
