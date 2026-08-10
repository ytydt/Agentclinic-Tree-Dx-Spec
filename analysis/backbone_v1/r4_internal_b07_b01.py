#!/usr/bin/env python3
"""Phase 3b: B07 refine field audit + B01 RAG access-id characterization."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import disagreement_census as dc
import r4_lib as r4

OUT = r4.OUT / "r4_internal"


def inspect_b07_traces() -> dict:
    """Check refine.top2_diagnoses shape across all B07 runs in census."""
    shapes = Counter()
    refine_eq_draft = 0
    refine_eq_diagnose = 0
    draft_hit = 0
    refine_hit = 0
    diagnose_hit = 0
    n = 0
    examples = []
    for ds_name, slices in (("da", dc.DA_SLICES), ("mcr", dc.MCR_SLICES)):
        for sl, spec in slices.items():
            run = spec.get("B07")
            if not run:
                continue
            trace_path = dc.ROOT / run / "trace.jsonl"
            if not trace_path.is_file():
                continue
            for line in trace_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                doc = json.loads(line)
                tr = doc.get("trace") or {}
                refine = tr.get("refine")
                draft = tr.get("draft")
                diagnose = tr.get("diagnose") or {}
                n += 1
                shapes[type(refine).__name__] += 1
                # normalize labels
                def labs(x):
                    if x is None:
                        return []
                    if isinstance(x, list):
                        out = []
                        for i in x:
                            if isinstance(i, dict):
                                out.append(str(i.get("diagnosis") or i.get("label") or ""))
                            else:
                                out.append(str(i))
                        return out
                    if isinstance(x, dict):
                        t2 = x.get("top2_diagnoses") or x.get("diagnoses") or []
                        return labs(t2)
                    return [str(x)]

                d_labs = labs(draft)
                r_labs = labs(refine)
                g_labs = labs(diagnose.get("top2_diagnoses") if isinstance(diagnose, dict) else diagnose)
                if d_labs and r_labs and d_labs == r_labs:
                    refine_eq_draft += 1
                if r_labs and g_labs and r_labs == g_labs:
                    refine_eq_diagnose += 1
                if len(examples) < 5:
                    examples.append(
                        {
                            "case_id": doc.get("case_id"),
                            "draft_type": type(draft).__name__,
                            "refine_type": type(refine).__name__,
                            "diagnose_type": type(diagnose).__name__,
                            "draft": d_labs[:2],
                            "refine": r_labs[:2],
                            "diagnose": g_labs[:2],
                            "refine_raw_keys": list(refine.keys())
                            if isinstance(refine, dict)
                            else None,
                        }
                    )

    # locus-based hit rates from r4 facts
    rows = r4.load_tsv(r4.R4 / "pooled.tsv")
    locus_ct = Counter(r.get("B07_locus") for r in rows)
    return {
        "n_traces": n,
        "refine_type_hist": dict(shapes),
        "refine_eq_draft_rate": refine_eq_draft / n if n else None,
        "refine_eq_diagnose_rate": refine_eq_diagnose / n if n else None,
        "locus_hist": dict(locus_ct),
        "examples": examples,
        "verdict": (
            "If refine_eq_draft_rate≈1 and refine_hit locus count≈0, refine is a no-op "
            "passthrough (parsing may be fine but the stage adds no information)."
        ),
    }


def inspect_b01() -> dict:
    rows = r4.load_tsv(r4.R4 / "pooled.tsv")
    b01 = [r for r in rows if r.get("B01_correct") not in ("", None)]
    locus = Counter(r.get("B01_locus") for r in b01)
    # chunk counts from loci if present
    chunks = []
    for r in b01:
        try:
            chunks.append(int(r.get("B01_n_chunks") or 0))
        except Exception:
            pass
    return {
        "n": len(b01),
        "locus_hist": dict(locus),
        "mean_chunks": (sum(chunks) / len(chunks)) if chunks else None,
        "limit": (
            "served_access_ids exist in traces but chunk bodies are not stored; "
            "cannot verify whether RAG evidence actually supports the final diagnosis."
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    b07 = inspect_b07_traces()
    b01 = inspect_b01()
    doc = {"b07": b07, "b01": b01}
    (OUT / "b07_b01_summary.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("B07 refine types", b07["refine_type_hist"])
    print("refine==draft", b07["refine_eq_draft_rate"], "refine==diagnose", b07["refine_eq_diagnose_rate"])
    print("B07 locus", b07["locus_hist"])
    print("B01", b01["locus_hist"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
