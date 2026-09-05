#!/usr/bin/env python3
"""Dump every scored/eliminating rule for case 475, with quotes and sources."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

KEY = "MCR_seq200b/475"


def main() -> int:
    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11_all4.json").read_text())}
    ext = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text())}
    sw.configure(sw.BASELINES["B1"], sw.stacks()["S6_+F4b"])
    r = eng.run_case(tasks[KEY], ext[KEY])

    print("RANKING")
    for i, c in enumerate(r["ranking"], 1):
        elim = f" ELIM:{[e.get('rule') for e in c.get('eliminated') or []]}" if c.get("eliminated") else ""
        print(f"  {i:2d} {c['score']:8.3f} joined={c.get('n_joined',0):3d} "
              f"assert={c.get('n_assertions',0):4d} {c['label']}{elim}")
        for e in (c.get("eliminated") or [])[:4]:
            print(f"      {e.get('rule')}: pred={e.get('predicate')!r}")
            print(f"        finding={e.get('finding')!r} pol={e.get('finding_polarity')}")
            print(f"        quote={str(e.get('quote') or '')[:220]}")

    # Re-bind so we can print quotes for every joined assertion that scored.
    task, extraction = tasks[KEY], ext[KEY]
    findings = [f for f in extraction["findings"] if isinstance(f, dict) and f.get("label")]
    assertions = [a for a in extraction["assertions"] if isinstance(a, dict)]
    if eng.FIX_ENUM:
        assertions = [eng.clamp_relation(a) for a in assertions]
    bound: dict[str, list] = defaultdict(list)
    for a in assertions:
        hit = None
        for cand in task["candidates"]:
            names = [cand["label"], *(cand.get("aliases") or [])]
            for name in names:
                m = eng.subject_match(a["subject"], name)
                if m:
                    hit = (cand["label"], m, name)
                    break
            if hit:
                break
        if hit is None:
            continue
        a = dict(a)
        a["_bind"] = hit[1]
        a["_bind_name"] = hit[2]
        bound[hit[0]].append(a)
    for label, items in bound.items():
        for a in items:
            best = None
            for f in findings:
                for side in (f.get("canonical"), f.get("label")):
                    m = eng.predicate_match(a["predicate"], side or "")
                    if m:
                        rank = {"exact": 0, "containment": 1, "overlap": 2,
                                "marker": 3, "loose": 4, "embed": 5}[m]
                        if best is None or rank < best[0]:
                            best = (rank, f, m)
                        break
            if best:
                a["_finding"] = best[1]
                a["_join"] = best[2]
            else:
                a["_finding"] = None
                a["_join"] = None

    focus = [
        "Mononeuropathy", "Neuralgic Amyotrophy",
        "Anterior Interosseous Nerve Syndrome", "Anterior Interosseous Syndrome",
        "Brachial Plexitis", "Mononeuritis Multiplex", "Radial Neuropathy",
    ]
    keywords = (
        "biceps", "triceps", "deltoid", "interosseous", "ok sign", "ok",
        "pronator", "flexor digitorum", "thumb", "index", "plexus",
        "parsonage", "amyotroph", "young", "acute", "sensory", "mri",
        "wasting", "weakness", "fist", "grip",
    )

    print("\n===== JOINED ASSERTIONS (focus candidates, keyword-filtered + all gold/winner) =====")
    for label in focus:
        items = bound.get(label, [])
        joined = [a for a in items if a.get("_finding")]
        print(f"\n### {label}: bound={len(items)} joined={len(joined)}")
        show = joined if label in ("Mononeuropathy", "Neuralgic Amyotrophy",
                                   "Anterior Interosseous Nerve Syndrome") else [
            a for a in joined if any(k in json.dumps(a, ensure_ascii=False).lower()
                                     for k in keywords)
        ]
        # always show all joined for gold and winner; cap others
        if label not in ("Mononeuropathy", "Neuralgic Amyotrophy",
                         "Anterior Interosseous Nerve Syndrome"):
            show = show[:20]
        for a in show:
            f = a["_finding"]
            print(f"  [{a.get('_join'):12s}] {a.get('subject')!s:40s} "
                  f"-[{a.get('relation')}/{a.get('polarity')}/{a.get('modality')}/{a.get('context_type')}]→ "
                  f"{str(a.get('predicate'))[:70]}")
            print(f"       bind={a.get('_bind')} via {a.get('_bind_name')!r}")
            print(f"       finding={f.get('label')!r} pol={f.get('polarity')}")
            print(f"       src={a.get('_source')} | {str(a.get('_title'))[:80]}")
            print(f"       quote={str(a.get('quote') or '')[:240]}")
            cg = a.get("criterion_group") or {}
            if cg.get("group_id"):
                print(f"       group={cg}")

    print("\n===== KEYWORD HITS AMONG ALL BOUND ASSERTIONS (even unmatched) =====")
    for label, items in bound.items():
        for a in items:
            blob = json.dumps(a, ensure_ascii=False).lower()
            if any(k in blob for k in ("biceps", "triceps", "deltoid", "parsonage",
                                       "kanavel", "kiloh", "territor")):
                f = a.get("_finding")
                print(f"  {label:36s} join={a.get('_join')} "
                      f"{a.get('subject')} -[{a.get('relation')}]→ {str(a.get('predicate'))[:80]}")
                print(f"       finding={None if not f else f.get('label')}")
                print(f"       src={a.get('_source')} {str(a.get('_title'))[:70]}")
                print(f"       quote={str(a.get('quote') or '')[:240]}")

    print("\n===== CONTRIBUTIONS (engine, truncated at 25) =====")
    for label in ("Mononeuropathy", "Neuralgic Amyotrophy",
                  "Anterior Interosseous Nerve Syndrome", "Brachial Plexitis"):
        c = next((x for x in r["ranking"] if x["label"] == label), None)
        if not c:
            continue
        print(f"\n### {label} score={c['score']} elim={c.get('eliminated')}")
        for x in c.get("contributions") or []:
            print(f"  {x.get('delta',0):+7.3f} {x.get('why')} "
                  f"pred={str(x.get('predicate'))[:70]} find={str(x.get('finding'))[:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
