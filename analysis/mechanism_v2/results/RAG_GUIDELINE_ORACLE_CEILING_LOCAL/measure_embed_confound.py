#!/usr/bin/env python3
"""Were the four 2x2 arms even given the same joining tools?

`embed_sim` is a lookup into a frozen `join_embeddings.npz` keyed on the exact
predicate string; a string that is not in the table scores 0 and can never take
the `embed` join path.  Coverage of unique predicates is 59.5 / 50.2 / 50.3 /
43.8 percent across the arms, worst exactly where the corpus repair and the free
prompt produce new wording.  So S7's nominal `embed_tau=0.6` does not mean the
arms are equally equipped, and the S35 regression was read under that confound.

Turning the encoder path off equalises the tooling.  If the v2 drop survives, it
is not an artefact of table coverage; if it disappears, S35's attribution needs
re-reading.

    python measure_embed_confound.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402
import gate_assertions as gate  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

ARMS = [("old prompt / old index", "trial_extraction_x2_oldidxclean_groups.json"),
        ("new prompt / old index", "trial_extraction_x2_oldidxclean_groups_free.json"),
        ("old prompt / v2 index",  "trial_extraction_x2_v2idxclean_groups.json"),
        ("new prompt / v2 index",  "trial_extraction_x2_v2idxclean_groups_free.json")]


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    base = sw.stacks()["S7_+F7"]
    out = []
    print(f"{'arm':<24}{'embed':<9}{'E17':<6}{'joined':>8}{'top1':>7}{'top3':>7}{'MRR':>8}")
    for name, fn in ARMS:
        ext = {e["case_key"]: e for e in
               json.loads((LEDGER / fn).read_text("utf-8"))}
        for tau, tag in ((0.6, "on"), (0.0, "off")):
            for e17 in (False, True):
                gate.E17_ENABLED = e17
                sw.configure(sw.BASELINES["B1"], {**base, "embed_tau": tau})
                res = [eng.run_case(tasks[k], ext[k]) for k in tasks]
                m = sw.metrics(res)
                nj = sum(r.get("join_stats", {}).get("matched", 0) for r in res)
                print(f"{name if tag=='on' and not e17 else '':<24}{tag:<9}"
                      f"{str(e17):<6}{nj:>8}{m['top1']:>5}/11{m['top3']:>5}/11"
                      f"{m['mrr']:>8.3f}")
                out.append({"arm": name, "embed": tag, "e17": e17, "joined": nj,
                            "top1": m["top1"], "top3": m["top3"], "mrr": m["mrr"]})
        print()
    gate.E17_ENABLED = True
    p = LEDGER / "embed_confound_sweep.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
