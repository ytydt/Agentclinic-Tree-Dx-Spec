#!/usr/bin/env python3
"""Stage 1: hypothesis-conditioned retrieval for the 11 separable cases.

One retrieval per candidate hypothesis, not one per case: the audit showed 5 of
26 required assertions have a subject that never appears in the vignette,
because exclusion rules live in the competitor's own document.

Every retrieved passage is scored against the hand-built oracle (the full set of
chunks whose text satisfies an assertion's subject AND predicate regex), so a
downstream failure can be attributed to ranking rather than to coverage.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
TASKS = LEDGER / "trial_tasks_11.json"
OUT = LEDGER / "trial_retrieval.json"

import sys

sys.path.insert(0, str(Path(__file__).parent))
from trial_retriever import TrialRetriever  # noqa: E402

STOP = {
    "the", "and", "with", "without", "from", "that", "this", "your", "have",
    "disease", "syndrome", "disorder", "related", "underlying", "type",
}

QUERY_TEMPLATES = [
    ("definition", "{h}"),
    ("criteria", "{h} diagnostic criteria diagnosis features"),
    ("differential", "{h} differential diagnosis distinguish from"),
    ("case", "{h} {case_terms}"),
]


def label_forms(label: str, aliases: list[str]) -> list[str]:
    forms = {label}
    forms.update(aliases or [])
    forms.add(re.sub(r"\s*\([^)]*\)", "", label).strip())
    forms.add(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label))
    inner = re.findall(r"\(([^)]*)\)", label)
    forms.update(x.strip() for x in inner)
    return sorted({f.strip() for f in forms if len(f.strip()) >= 3})


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", text.lower()) if w not in STOP]


def subject_hit(text: str, forms: list[str]) -> str:
    """Mechanical anchor test: is the passage about this hypothesis at all?"""
    low = text.lower()
    for f in forms:
        if f.lower() in low:
            return "exact_form"
    for f in forms:
        words = content_words(f)
        if words and all(re.search(rf"\b{re.escape(w)}", low) for w in words):
            return "all_content_words"
    return ""


def case_terms(retriever: TrialRetriever, vignette: str, k: int = 12) -> str:
    """Top TF-IDF terms of the vignette, used to steer retrieval to this case."""
    v = retriever.vec.transform([vignette])
    # the pickled vectorizer predates sklearn 1.0 on this interpreter
    getter = getattr(retriever.vec, "get_feature_names_out", None) \
        or retriever.vec.get_feature_names
    names = getter()
    row = v.tocoo()
    pairs = sorted(zip(row.col, row.data), key=lambda x: -x[1])[:k]
    return " ".join(str(names[c]) for c, _ in pairs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k-per-query", type=int, default=12)
    ap.add_argument("--keep-per-hypothesis", type=int, default=8)
    ap.add_argument("--device", default="cuda:1")
    ap.add_argument("--no-dense", action="store_true")
    ap.add_argument("--arm", default="")
    ap.add_argument("--inject-oracle", action="store_true",
                    help="force-add one oracle passage per assertion, isolating "
                         "extraction and engine quality from retrieval ranking")
    ap.add_argument("--tasks", default="trial_tasks_11.json")
    ap.add_argument("--index", default="",
                    help="index directory; pass ceiling_trial_index_v2 to "
                         "retrieve over the repaired corpus (report S29)")
    args = ap.parse_args()
    out_path = LEDGER / (f"trial_retrieval_{args.arm}.json" if args.arm else "trial_retrieval.json")

    tasks = json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))
    t0 = time.time()
    print("loading index", flush=True)
    R = TrialRetriever(device=args.device, use_dense=not args.no_dense,
                       index=args.index or None)
    print(f"  index ready ({time.time()-t0:.0f}s, dense={R.use_dense})", flush=True)

    out = []
    for task in tasks:
        key = task["case_key"]
        terms = case_terms(R, task["vignette"])

        queries, provenance = [], []
        for cand in task["candidates"]:
            for name, tpl in QUERY_TEMPLATES:
                queries.append(tpl.format(h=cand["label"], case_terms=terms))
                provenance.append((cand["label"], name))

        hits = R.search(queries, top_k=args.top_k_per_query)

        # fuse the four templates per hypothesis, then keep only passages that
        # are actually anchored on that hypothesis
        per_hyp: dict[str, dict[int, dict]] = {}
        for (label, tname), hitlist in zip(provenance, hits):
            slot = per_hyp.setdefault(label, {})
            for h in hitlist:
                rec = slot.setdefault(h["gid"], {"gid": h["gid"], "rrf": 0.0, "templates": []})
                rec["rrf"] += h["rrf"]
                rec["templates"].append(tname)

        retrieved = {}
        for cand in task["candidates"]:
            label = cand["label"]
            forms = label_forms(label, cand.get("aliases") or [])
            scored = []
            for rec in sorted(per_hyp.get(label, {}).values(), key=lambda r: -r["rrf"]):
                pas = R.passage(rec["gid"])
                anchor = subject_hit(pas["text"] + " " + pas["title"], forms)
                if not anchor:
                    continue
                pas.update({"rrf": round(rec["rrf"], 6), "templates": sorted(set(rec["templates"])),
                            "anchor": anchor})
                scored.append(pas)
                if len(scored) >= args.keep_per_hypothesis:
                    break
            retrieved[label] = {
                "forms": forms,
                "n_candidate_passages": len(per_hyp.get(label, {})),
                "n_anchored": len(scored),
                "passages": scored,
            }

        if args.inject_oracle:
            for a in task["assertions"]:
                have = {g for r in retrieved.values() for p in r["passages"] for g in p["window_gids"]}
                if not a["oracle_gids"] or (set(a["oracle_gids"]) & have):
                    continue
                s_re = re.compile(a["subject_re"], re.I)
                owner = next((c["label"] for c in task["candidates"]
                              if s_re.search(c["label"])
                              or any(s_re.search(x) for x in c.get("aliases") or [])), None)
                bucket = retrieved.setdefault(
                    owner or f"__oracle__{a['subject']}",
                    {"forms": [a["subject"]], "n_candidate_passages": 0, "n_anchored": 0,
                     "passages": [], "injected_only": owner is None})
                pas = R.passage(a["oracle_gids"][0])
                pas.update({"rrf": 0.0, "templates": ["oracle_injected"], "anchor": "injected",
                            "injected_for": a["id"]})
                bucket["passages"].append(pas)

        # oracle recall
        all_gids = {g for r in retrieved.values() for p in r["passages"] for g in p["window_gids"]}
        oracle_report = []
        for a in task["assertions"]:
            ogids = set(a["oracle_gids"])
            got = sorted(ogids & all_gids)
            owner = [lbl for lbl, r in retrieved.items()
                     if ogids & {g for p in r["passages"] for g in p["window_gids"]}]
            oracle_report.append({
                "id": a["id"], "subject": a["subject"], "predicate": a["predicate"],
                "kind": a["kind"], "n_oracle_chunks": len(ogids),
                "retrieved": bool(got), "hit_gids": got[:10],
                "retrieved_under_hypotheses": owner,
            })

        n_pass = sum(len(r["passages"]) for r in retrieved.values())
        n_ok = sum(1 for o in oracle_report if o["retrieved"])
        print(f"  {key:24s} cands={len(task['candidates']):2d} passages={n_pass:3d} "
              f"oracle {n_ok}/{len(oracle_report)}", flush=True)
        out.append({"case_key": key, "case_terms": terms, "retrieved": retrieved,
                    "oracle": oracle_report})

    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    tot = sum(len(o["oracle"]) for o in out)
    ok = sum(1 for o in out for a in o["oracle"] if a["retrieved"])
    n_pass_all = sum(len(r["passages"]) for o in out for r in o["retrieved"].values())
    print(f"\noracle assertions retrieved: {ok}/{tot}; passages total: {n_pass_all}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
