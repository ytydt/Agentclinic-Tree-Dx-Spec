#!/usr/bin/env python3
"""Mechanism checks: did the chain each fix targets actually start running?

With 11 cases the aggregate MRR cannot separate a fix that works from noise, so
each fix is also asked a yes/no question about the specific link that section 4
of the trial report showed was broken.  A fix that moves MRR but does not close
its own link has not been demonstrated; a fix that closes its link but does not
move MRR is blocked downstream, and the check says where.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

# (case, assertion id, subject regex, predicate regex, expected patient finding
#  regex).  Taken from sections 4.3-4.5 and 11.5 of the trial report.
LINKS = [
    ("MCR_v1_seq100/56", "56.a", r"squamous cell carcinoma", r"p63", r"p63"),
    ("MCR_seq200b/326", "326.a", r"brucell", r"unpasteuri|raw milk", r"unpasteuri"),
    ("MCR_seq200b/326", "326.c", r"^brucella$", r"gram.?negative", r"gram.?negative|blood culture"),
    ("MCR_v1_seq100/74", "74.a", r"catecholaminergic|cpvt", r"structurally normal",
     r"normal wall|no valvular|structurally normal"),
    ("MCR_seq200b/257", "257.a1", r"tenosynovitis", r"tenderness.*flexor tendon sheath",
     r"tenderness"),
    ("MCR_seq200b/257", "257.a2", r"tenosynovitis", r"fusiform swelling", r"swelling"),
    ("MCR_seq200b/257", "257.a3", r"tenosynovitis", r"flexor posturing", r"motion|posturing"),
    ("MCR_seq200b/257", "257.a4", r"tenosynovitis", r"passive digit extension", r"pain|extension"),
    ("MCR_seq200b/475", "475.a", r"neuralgic amyotrophy|parsonage", r".", r"."),
]


def run(tasks, ext, base: str, fix: dict) -> dict[str, dict]:
    sw.configure(sw.BASELINES[base], fix)
    e = sw.eng
    ext_use = ext["groups"] if e.USE_CRITERION_GROUPS else ext["plain"]
    return {k: e.run_case(tasks[k], ext_use[k]) for k in tasks}


def link_report(tasks, ext, base: str, fix: dict) -> list[dict]:
    """For each targeted link: is the assertion bound, and is it joined to the
    intended finding?  Reads the engine's own annotations, not a re-match."""
    sw.configure(sw.BASELINES[base], fix)
    e = sw.eng
    ext_use = ext["groups"] if e.USE_CRITERION_GROUPS else ext["plain"]
    out = []
    for case, aid, srx, prx, frx in LINKS:
        res = e.run_case(tasks[case], ext_use[case])
        s_re, p_re, f_re = (re.compile(x, re.I) for x in (srx, prx, frx))
        # the engine keeps bound assertions only inside verdicts, so re-derive
        # the binding the same way it does and then look at what it recorded
        raw = [a for a in ext_use[case]["assertions"]
               if isinstance(a, dict) and s_re.search(a.get("subject") or "")
               and p_re.search(a.get("predicate") or "")]
        bound_to = None
        joined = None
        join_kind = None
        for a in raw:
            for cand in tasks[case]["candidates"]:
                names = [cand["label"], *(cand.get("aliases") or [])]
                if any(e.subject_match(a["subject"], n) for n in names):
                    bound_to = bound_to or cand["label"]
                    break
            for f in ext_use[case]["findings"]:
                if not isinstance(f, dict):
                    continue
                for side in (f.get("canonical"), f.get("label")):
                    m = e.predicate_match(a["predicate"], side or "")
                    if m and f_re.search(f.get("label") or ""):
                        joined, join_kind = f.get("label"), m
                        break
                if joined:
                    break
            if joined:
                break
        out.append({"case": case, "id": aid, "n_assertions": len(raw),
                    "bound_to": bound_to, "joined_finding": joined, "join_kind": join_kind,
                    "gold_rank": res["gold_rank"], "top1": res["top1"]})
    return out


def group_report(tasks, ext, base: str, fix: dict) -> list[dict]:
    """Did any criterion group produce a contribution or an elimination?"""
    res = run(tasks, ext, base, fix)
    out = []
    for key, r in res.items():
        contribs = [c for v in r["ranking"] for c in v["contributions"]
                    if str(c.get("why", "")).startswith("group:")]
        elims = [x for v in r["ranking"] for x in v["eliminated"]
                 if x.get("rule") == "criterion_group_violated"]
        out.append({"case": key, "n_group_contributions": len(contribs),
                    "n_group_eliminations": len(elims),
                    "sat_total": sum(c.get("n_satisfied", 0) for c in contribs),
                    "vio_total": sum(c.get("n_violated", 0) for c in contribs)})
    return out


def enum_report(ext) -> dict:
    from collections import Counter

    seen = Counter()
    for case in ext["plain"].values():
        for a in case["assertions"]:
            if not isinstance(a, dict):
                continue
            rel = (a.get("relation") or "").strip().lower()
            if rel not in eng.LEGAL_RELATIONS:
                seen[rel] += 1
    total = sum(len(c["assertions"]) for c in ext["plain"].values())
    return {"n_assertions": total, "n_illegal_relation": sum(seen.values()),
            "top_illegal": seen.most_common(20)}


def f7_mechanism_checks(tasks, ext_groups: dict[str, dict], base_fix: dict) -> list[dict]:
    """Yes/no checks for the ranking-critical extraction defects (section 16).

    326  gold must not be eliminated via serologic/required_but_absent once gated
    74   LQTS must not get pathognomonic confirmation from a name-only quote
    119  cornoid lamella pathognomonic must survive the gate
    475  AIN ``advanced MRI`` required_for+obligatory must be demoted
    74   G-A / G1 / G2 / G3 delivery targets (section 16.7)
    """
    from gate_assertions import gate_assertions, gate_one

    rows = []

    # --- 326 ---
    ck326 = next(k for k in tasks if k.endswith("/326"))
    sw.configure(sw.BASELINES["B1"], {**base_fix, "quote_gate": True})
    r326 = eng.run_case(tasks[ck326], ext_groups[ck326])
    serology_elim = [
        e for v in r326["ranking"] for e in v.get("eliminated") or []
        if e.get("rule") == "required_but_absent"
        and re.search(r"serologic", e.get("predicate") or "", re.I)
        and v["label"] == tasks[ck326]["gold"]
    ]
    # also check gold_eliminated overall
    rows.append({
        "id": "326_no_serology_required_absent",
        "pass": tasks[ck326]["gold"] not in (r326.get("gold_eliminated") or [])
                and not serology_elim,
        "gold_eliminated": r326.get("gold_eliminated"),
        "serology_elim": serology_elim,
        "gold_rank": r326["gold_rank"],
    })

    # --- 74 ---
    ck74 = next(k for k in tasks if k.endswith("/74"))
    raw74 = [a for a in ext_groups[ck74]["assertions"] if isinstance(a, dict)]
    name_only = [
        a for a in raw74
        if (a.get("relation") or "").lower() == "pathognomonic_for"
        and re.search(r"termed long QT|called long QT|long QT syndrome",
                      a.get("quote") or "", re.I)
        and not re.search(r"pathognomonic|hallmark|diagnostic of|will be diagnostic",
                          a.get("quote") or "", re.I)
    ]
    gated74 = gate_assertions(name_only, apply_nli=False)
    still_patho = [a for a in gated74
                   if (a.get("relation") or "").lower() == "pathognomonic_for"]
    sw.configure(sw.BASELINES["B1"], {**base_fix, "quote_gate": True})
    r74 = eng.run_case(tasks[ck74], ext_groups[ck74])
    lqts_patho_confirm = [
        c for v in r74["ranking"] for c in v.get("confirmed") or []
        if v["label"].lower().startswith("long qt")
        and re.search(r"termed long QT|called long QT", c.get("quote") or "", re.I)
    ]
    rows.append({
        "id": "74_no_name_tautology_patho",
        "pass": not still_patho and not lqts_patho_confirm,
        "n_name_only_raw": len(name_only),
        "n_still_patho_after_gate": len(still_patho),
        "lqts_name_confirms": lqts_patho_confirm,
        "gold_rank": r74["gold_rank"],
    })

    # --- 119 ---
    ck119 = next(k for k in tasks if k.endswith("/119"))
    cornoid = [
        a for a in ext_groups[ck119]["assertions"] if isinstance(a, dict)
        and (a.get("relation") or "").lower() == "pathognomonic_for"
        and re.search(r"cornoid\s+lamella", a.get("predicate") or "", re.I)
    ]
    kept_cornoid = []
    for a in cornoid:
        g = gate_one(a)
        if g and (g.get("relation") or "").lower() == "pathognomonic_for":
            kept_cornoid.append(g)
    rows.append({
        "id": "119_cornoid_patho_survives",
        "pass": len(kept_cornoid) >= 1,
        "n_raw": len(cornoid),
        "n_kept": len(kept_cornoid),
        "sample_quote": (kept_cornoid[0].get("quote") if kept_cornoid else None),
    })

    # --- 475 ---
    ck475 = next(k for k in tasks if k.endswith("/475"))
    mri_req = [
        a for a in ext_groups[ck475]["assertions"] if isinstance(a, dict)
        and (a.get("relation") or "").lower() == "required_for"
        and (a.get("modality") or "").lower() == "obligatory"
        and re.search(r"MRI|magnetic resonance", a.get("predicate") or "", re.I)
        and re.search(r"anterior interosseous|AIN", a.get("subject") or "", re.I)
    ]
    demoted = 0
    for a in mri_req:
        g = gate_one(a)
        if g is None:
            demoted += 1
            continue
        if (g.get("modality") or "").lower() != "obligatory" \
                or (g.get("relation") or "").lower() != "required_for":
            demoted += 1
    sw.configure(sw.BASELINES["B1"], {**base_fix, "quote_gate": True})
    r475 = eng.run_case(tasks[ck475], ext_groups[ck475])
    ain_mri_elim = [
        e for v in r475["ranking"] for e in v.get("eliminated") or []
        if e.get("rule") == "required_but_absent"
        and re.search(r"MRI|magnetic resonance", e.get("predicate") or "", re.I)
        and re.search(r"anterior interosseous", v["label"], re.I)
    ]
    rows.append({
        "id": "475_ain_mri_not_obligatory_kill",
        "pass": (not mri_req or demoted == len(mri_req)) and not ain_mri_elim,
        "n_mri_obligatory_raw": len(mri_req),
        "n_demoted": demoted,
        "ain_mri_elim": ain_mri_elim,
        "gold_rank": r475["gold_rank"],
    })

    # --- 74 G-A / G1 / G2 / G3 (section 16.7) ---
    def _uniq74(rows):
        seen, out = set(), []
        for a in rows:
            k = (str(a.get("subject") or "").lower(),
                 str(a.get("relation") or "").lower(),
                 str(a.get("predicate") or "").lower(),
                 str(a.get("quote") or "")[:80].lower())
            if k in seen:
                continue
            seen.add(k)
            out.append(a)
        return out

    gated_all74 = gate_assertions(raw74, apply_nli=False)
    still_req = _uniq74([
        a for a in gated_all74
        if (a.get("relation") or "").lower() == "required_for"
    ])

    def _has(pred_re, quote_re):
        return any(re.search(pred_re, a.get("predicate") or "", re.I)
                   and re.search(quote_re, a.get("quote") or "", re.I)
                   for a in still_req)

    false_left = [
        a for a in still_req
        if re.search(r"holter|at-risk|exercise testing|resting ECG|"
                     r"pharmacological stress|genetic analysis",
                     (a.get("predicate") or "") + " " + (a.get("quote") or ""), re.I)
        and not re.search(r"necessary for the diagnosis|can only be made|"
                          r"must be fulfilled|in the presence of",
                          a.get("quote") or "", re.I)
    ]
    rows.append({
        "id": "74_ga_false_required_cleared",
        "pass": not false_left,
        "n_still_required_unique": len(still_req),
        "n_false_left": len(false_left),
        "false_left": [(a.get("predicate"), (a.get("quote") or "")[:80])
                       for a in false_left[:8]],
    })
    keep_ok = (
        _has(r"type I pattern", r"necessary for the diagnosis")
        and _has(r"structurally normal", r"in the presence of")
        and _has(r"coronary angiography", r"can only be made")
        and _has(r"criterion|abnormalit", r"must be fulfilled|at least 1 criterion")
    )
    rows.append({
        "id": "74_ga_true_required_kept",
        "pass": keep_ok,
        "kept_type_i": _has(r"type I pattern", r"necessary for the diagnosis"),
        "kept_struct": _has(r"structurally normal", r"in the presence of"),
        "kept_tako": _has(r"coronary angiography", r"can only be made"),
        "kept_arvc": _has(r"criterion|abnormalit", r"must be fulfilled|at least 1 criterion"),
    })

    dual_left = [
        a for a in gated_all74
        if (a.get("relation") or "").lower() == "pathognomonic_for"
        and re.search(r"necessary for the diagnosis", a.get("quote") or "", re.I)
    ]
    rows.append({
        "id": "74_g1_no_dual_type_i",
        "pass": not dual_left,
        "n_dual_left": len(dual_left),
    })

    lqts_thr = [
        e for v in r74["ranking"] for e in v.get("eliminated") or []
        if re.search(r"long qt", v["label"], re.I)
        and e.get("rule") == "threshold_violated"
        and re.search(r"QTc|440|460", str(e.get("comparison") or "") + str(e.get("predicate") or ""), re.I)
    ]
    rows.append({
        "id": "74_g2_lqts_qtc_threshold_violated",
        "pass": bool(lqts_thr) and r74["gold_rank"] == 1,
        "n_lqts_threshold_hits": len(lqts_thr),
        "sample": lqts_thr[:2],
        "gold_rank": r74["gold_rank"],
        "gold_eliminated": r74.get("gold_eliminated"),
    })

    g3_vt = [
        a for a in gated_all74
        if (a.get("relation") or "").lower() == "required_for"
        and re.search(r"bidirectional", a.get("predicate") or "", re.I)
        and re.search(r"CPVT|catecholaminergic", a.get("subject") or "", re.I)
        and (a.get("modality") or "").lower() != "obligatory"
    ]
    g3_holter_up = [
        a for a in gated_all74
        if (a.get("relation") or "").lower() == "required_for"
        and re.search(r"holter", a.get("predicate") or "", re.I)
        and "G3_presence_conjunction" in str(a.get("_gate") or "")
    ]
    rows.append({
        "id": "74_g3_consensus_vt_required_not_holter",
        "pass": bool(g3_vt) and not g3_holter_up,
        "n_g3_vt": len(g3_vt),
        "n_g3_holter": len(g3_holter_up),
    })
    return rows


def embed_sample(tasks, ext, tau: float, n: int = 25) -> list[dict]:
    """What does the encoder join that the token sets did not?  Sampled so the
    false-positive rate of the fix can be eyeballed rather than assumed."""
    sw.configure(sw.BASELINES["B1"], {"embed_tau": tau})
    e = sw.eng
    rows = []
    for key, task in tasks.items():
        case = ext["groups"][key]
        findings = [f for f in case["findings"] if isinstance(f, dict) and f.get("label")]
        for a in case["assertions"][:4000]:
            if not isinstance(a, dict):
                continue
            pred = a.get("predicate") or ""
            for f in findings:
                for side in (f.get("canonical"), f.get("label")):
                    if not side:
                        continue
                    if e.concept_match(pred, side):
                        break
                    if e.embed_sim(pred, side) >= tau:
                        rows.append({"case": key, "predicate": pred, "finding": side,
                                     "sim": round(e.embed_sim(pred, side), 3)})
                        break
                else:
                    continue
                break
    rows.sort(key=lambda r: -r["sim"])
    step = max(len(rows) // n, 1)
    return rows[::step][:n] + [{"n_total_embed_only_joins": len(rows)}]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30oracleclean")
    ap.add_argument("--tasks", default="trial_tasks_11.json")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in json.loads((LEDGER / args.tasks).read_text("utf-8"))}
    plain = {e["case_key"]: e for e in
             json.loads((LEDGER / f"trial_extraction_{args.arm}.json").read_text("utf-8"))}
    grouped = {e["case_key"]: e for e in
               json.loads((LEDGER / f"trial_extraction_{args.arm}_groups.json").read_text("utf-8"))}
    ext = {"plain": plain, "groups": grouped}

    report: dict = {}

    print("=== F2/F3 targeted links (baseline B1) ===")
    for name, fix in [("baseline", {}), ("F2a_marker", {"marker": True}),
                      ("F2b_embed60", {"embed_tau": 0.60}),
                      ("F2_both+F3", {"marker": True, "embed_tau": 0.60, "organism": True})]:
        rows = link_report(tasks, ext, "B1", fix)
        report[f"links_{name}"] = rows
        ok = sum(1 for r in rows if r["joined_finding"])
        bd = sum(1 for r in rows if r["bound_to"])
        print(f"  {name:14s} bound {bd}/{len(rows)}  joined {ok}/{len(rows)}")
        for r in rows:
            print(f"     {r['id']:7s} bound={str(r['bound_to'])[:28]:28s} "
                  f"join={str(r['joined_finding'])[:30]:30s} kind={r['join_kind']}")

    print("\n=== F4 criterion groups ===")
    for name, fix in [("groups", {"groups": True}),
                      ("groups+embed60", {"groups": True, "embed_tau": 0.60}),
                      ("groups+embed60+cwa", {"groups": True, "embed_tau": 0.60,
                                              "closed_world": True})]:
        rows = group_report(tasks, ext, "B1", fix)
        report[f"groups_{name}"] = rows
        print(f"  {name:20s} contributions={sum(r['n_group_contributions'] for r in rows):3d} "
              f"eliminations={sum(r['n_group_eliminations'] for r in rows):2d} "
              f"257={[r for r in rows if r['case'].endswith('/257')][0]}")

    print("\n=== F5a enum clamp ===")
    report["enum"] = enum_report(ext)
    print(f"  {report['enum']['n_illegal_relation']}/{report['enum']['n_assertions']} "
          f"assertions carry an out-of-enum relation")
    for rel, n in report["enum"]["top_illegal"]:
        print(f"     {rel:24s} {n}")

    print("\n=== F2b embedding-only joins, sampled ===")
    report["embed_sample"] = embed_sample(tasks, ext, 0.60)
    for r in report["embed_sample"]:
        if "sim" in r:
            print(f"  {r['sim']:.3f}  {r['predicate'][:44]:44s} :: {r['finding'][:40]}")
        else:
            print(f"  total embed-only joins: {r['n_total_embed_only_joins']}")

    print("\n=== F7 quote-gate mechanism checks (B1+S6) ===")
    s6 = sw.stacks()["S6_+F4b"]
    report["f7_mechanism"] = f7_mechanism_checks(tasks, grouped, s6)
    for row in report["f7_mechanism"]:
        flag = "PASS" if row["pass"] else "FAIL"
        print(f"  {flag}  {row['id']}  { {k: row[k] for k in row if k not in {'id', 'pass'}} }")

    out = LEDGER / "fix_mechanism_checks.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
