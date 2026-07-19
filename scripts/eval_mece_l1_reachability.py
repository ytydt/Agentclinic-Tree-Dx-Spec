#!/usr/bin/env python3
"""MECE L1 reachability prototype (§6 of RESIDUAL_MISS_ROOTCAUSE_AND_MECE.md).

Thesis: L1 no-miss is a STRUCTURAL guarantee, not a leaf-retrieval problem. If the
LLM generates a MECE + collectively-exhaustive L1 partition for the syndrome, the
gold disease always has a REACHABLE branch — regardless of whether that specific
leaf was pre-recalled by any retrieval arm.

Protocol (leakage-controlled — the generator never sees the gold):
  1. GENERATE: LLM produces an L1 partition for {syndrome, salient} — 5-9
     mutually-exclusive families covering the syndrome's cause space, PLUS an
     explicit catch-all ("other/less-common causes"). No gold, no hand axis map.
  2. JUDGE: a SEPARATE LLM call assigns the gold disease to exactly one branch
     index (or -1). Tests structural reachability.
  3. Metrics per case:
       reachable_specific : gold lands in a NON-catch-all branch (clean L1 hit)
       reachable_any      : gold lands in any branch incl. catch-all (no-miss)
       n_branches, has_catchall, judge_overlap (quick MECE sanity)

Compare reachability vs the leaf recall@20 (union_all) from the A/B — the gap is
the value of the structural guarantee.

    PYTHONPATH=src python scripts/eval_mece_l1_reachability.py --llm-model meta-llama/llama-3.3-70b-instruct
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "data" / "cpg" / "eval"


def _gold_names(case: dict) -> list:
    """Human-readable gold family names from the eval set's l1_target token-lists."""
    names = []
    for fam in case.get("l1_target") or []:
        for alt in fam:
            names.append(" ".join(alt))
    return names


def make_poster(model: str):
    import requests
    key = os.environ.get("OPENROUTER_API_KEY2", "")
    headers = {"Authorization": f"Bearer {key}", "HTTP-Referer": "google.com",
               "X-Title": "eval", "Content-Type": "application/json"}
    prov = {"order": ["novita", "deepinfra/base", "groq"], "allow_fallbacks": True}

    def chat(msgs: list) -> str:
        import time
        last = ""
        for attempt in range(5):
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                  headers=headers,
                                  json={"model": model, "messages": msgs,
                                        "temperature": 0.0, "provider": prov},
                                  timeout=120)
                return json.loads(r.text)["choices"][0]["message"]["content"]
            except Exception as e:  # transient proxy/SSL/rate errors → backoff
                last = f"{type(e).__name__}: {str(e)[:80]}"
                time.sleep(2 * (attempt + 1))
        print(f"    [llm] giving up after retries: {last}")
        return ""

    def _json_of(txt: str) -> dict:
        """First balanced {...} object that parses (robust to models that emit
        multiple JSON blocks / prose around the answer)."""
        depth = start = 0
        for i, ch in enumerate(txt):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(txt[start:i + 1])
                    except Exception:
                        continue
        return {}

    _P_MIXED = (
        "You are structuring the FIRST-LEVEL differential for a presenting "
        "syndrome as a MECE partition of its CAUSE SPACE. Produce 5-9 "
        "first-level families that are (1) MUTUALLY EXCLUSIVE (no disease fits "
        "two) and (2) COLLECTIVELY EXHAUSTIVE over the syndrome's etiologies, "
        "PLUS one explicit catch-all family named exactly 'other/less-common "
        "causes'. Families are BROAD mechanism/category buckets (e.g. "
        "'neoplastic/compressive', 'reactive/secondary', 'vascular/structural'), "
        "NOT specific diseases. Return STRICT JSON: "
        '{"branches":[{"label":"...","scope":"one-line what it covers"}]}.')
    # Single fundamentum divisionis: the dominant overlap root cause is AXIS
    # MIXING (anatomic buckets like 'hepatobiliary' beside mechanism buckets like
    # 'neoplastic' → a pancreatic tumor fits both). This prompt forces ONE axis.
    _P_SINGLE = (
        "You are structuring the FIRST-LEVEL differential for a presenting "
        "syndrome as a MECE partition of its CAUSE SPACE.\n"
        "CRITICAL RULE — SINGLE BASIS OF DIVISION (fundamentum divisionis): pick "
        "EXACTLY ONE classification axis for the whole partition (choose the one "
        "most natural for this syndrome: ETIOLOGIC-MECHANISM, or ANATOMIC-SITE, or "
        "PATHOPHYSIOLOGIC-PROCESS) and derive EVERY family from that same axis. "
        "Do NOT mix axes (e.g. never put an anatomic bucket like 'hepatobiliary' "
        "beside a mechanism bucket like 'neoplastic' — a pancreatic tumor would "
        "then fit both). Families must be PARALLEL and DISJOINT: any disease is "
        "classified into exactly ONE family by its PRIMARY value on that axis.\n"
        "Produce 5-9 such families + one explicit catch-all named exactly "
        "'other/less-common causes'. Families are BROAD buckets, NOT specific "
        "diseases. State the chosen axis. Return STRICT JSON: "
        '{"axis":"mechanism|anatomic|process","branches":[{"label":"...",'
        '"scope":"one-line what it covers"}]}.')

    def generate_partition(syndrome: str, salient: str, mode: str = "mixed") -> dict:
        sysp = _P_SINGLE if mode == "single" else _P_MIXED
        return _json_of(chat([{"role": "system", "content": sysp},
                              {"role": "user", "content":
                               f"Syndrome: {syndrome}\nSalient findings: {salient}"}]))

    def judge_assign(gold: str, branches: list) -> int:
        labs = [f"{i}: {b.get('label','')} — {b.get('scope','')}"
                for i, b in enumerate(branches)]
        sysp = (
            "Assign the given specific diagnosis to the SINGLE best-fitting "
            "first-level family from the numbered list. If none fits at all, "
            'answer -1. Return STRICT JSON: {"index": <int>}. Judge by mechanism/'
            "category membership, not wording.")
        obj = _json_of(chat([{"role": "system", "content": sysp},
                             {"role": "user", "content":
                              f"Diagnosis: {gold}\nFamilies:\n" + "\n".join(labs)}]))
        try:
            return int(obj.get("index", -1))
        except Exception:
            return -1

    def judge_assign_multi(dz: str, branches: list) -> list:
        """ALL first-level families the diagnosis plausibly fits (for MECE
        mutual-exclusivity: >1 non-catch-all fit = overlap violation)."""
        labs = [f"{i}: {b.get('label','')} — {b.get('scope','')}"
                for i, b in enumerate(branches)]
        sysp = (
            "List EVERY first-level family from the numbered list that the given "
            "diagnosis could plausibly belong to (by mechanism/category). A "
            "well-formed MECE partition should yield exactly ONE. Return STRICT "
            'JSON: {"indices": [<int>, ...]} ([] if none fits).')
        obj = _json_of(chat([{"role": "system", "content": sysp},
                             {"role": "user", "content":
                              f"Diagnosis: {dz}\nFamilies:\n" + "\n".join(labs)}]))
        out = []
        for x in (obj.get("indices") or []):
            try:
                out.append(int(x))
            except Exception:
                pass
        return out

    def generate_probes(syndrome: str, salient: str, n: int = 8) -> list:
        """Independent probe set of SPECIFIC diseases for the syndrome (does NOT
        see the partition) — the population over which MECE is measured."""
        sysp = (
            "List the {n} most important SPECIFIC diagnoses (mix of common and "
            "rare) that cause the presenting syndrome. Return STRICT JSON: "
            '{"diagnoses": ["specific disease", ...]}. No prose.').replace("{n}", str(n))
        obj = _json_of(chat([{"role": "system", "content": sysp},
                             {"role": "user", "content":
                              f"Syndrome: {syndrome}\nSalient findings: {salient}"}]))
        return [str(x) for x in (obj.get("diagnoses") or [])][:n]

    return generate_partition, judge_assign, judge_assign_multi, generate_probes


def is_catchall(branch: dict) -> bool:
    lab = (branch.get("label", "") or "").lower()
    return ("other" in lab and ("less" in lab or "common" in lab or "unclass" in lab)) \
        or lab.strip() in {"other", "miscellaneous"}


def run(cases: list, gen, judge, judge_multi, gen_probes, tag: str,
        n_probes: int, dump: list | None = None, gen_mode: str = "mixed") -> dict:
    n = spec = any_ = 0
    probe_tot = probe_excl_viol = probe_exhaust_gap = 0
    rows = []
    for c in cases:
        if not c.get("l1_target"):
            continue
        n += 1
        golds = _gold_names(c)
        part = gen(c["syndrome"], c.get("context", ""), gen_mode)
        branches = part.get("branches", []) or []
        non_catch = [i for i, b in enumerate(branches) if not is_catchall(b)]
        has_catch = len(non_catch) < len(branches)
        if dump is not None:
            case_rec = {"set": tag, "id": c["id"], "syndrome": c["syndrome"],
                        "branches": [{"label": b.get("label", ""),
                                      "scope": b.get("scope", ""),
                                      "catchall": is_catchall(b)}
                                     for b in branches],
                        "overlaps": []}
            dump.append(case_rec)
        # gold reachability
        best_specific = best_any = False
        assigned = None
        for g in golds:
            idx = judge(g, branches)
            if idx is not None and 0 <= idx < len(branches):
                best_any = True
                assigned = branches[idx].get("label", "")
                if not is_catchall(branches[idx]):
                    best_specific = True
                    break
        spec += int(best_specific)
        any_ += int(best_any)
        # MECE quality on an INDEPENDENT probe population (probes never see part)
        probes = gen_probes(c["syndrome"], c.get("context", ""), n_probes)
        pv = pg = 0
        for dz in probes:
            idxs = [i for i in judge_multi(dz, branches) if 0 <= i < len(branches)]
            nc_fits = [i for i in idxs if i in non_catch]
            probe_tot += 1
            if len(nc_fits) > 1:      # fits >1 non-catch-all family → overlap
                pv += 1; probe_excl_viol += 1
                if dump is not None:
                    case_rec["overlaps"].append(
                        {"probe": dz,
                         "labels": [branches[i].get("label", "") for i in nc_fits]})
            if len(nc_fits) == 0:     # only catch-all / none → exhaustiveness gap
                pg += 1; probe_exhaust_gap += 1
        rows.append((c["id"], len(branches), has_catch, best_specific, best_any,
                     assigned, golds[0] if golds else "", len(probes), pv, pg))
    print(f"\n=== {tag} (n={n}, probes/case={n_probes}) — MECE quality ===")
    print(f"{'id':<24}{'#br':<5}{'gold':<7}{'assigned':<28}"
          f"{'excl_viol':<11}{'exh_gap':<8}")
    for cid, nb, ca, sp, an, asg, g, npr, pv, pg in rows:
        gold_flag = "HIT" if sp else ("catch" if an else "MISS")
        print(f"{cid:<24}{nb:<5}{gold_flag:<7}{str(asg)[:26]:<28}"
              f"{pv}/{npr:<9}{pg}/{npr}")
    print(f"  gold reachable(specific)={spec}/{n}  (any incl.catch-all)={any_}/{n}")
    if probe_tot:
        print(f"  MECE mutual-exclusivity violation = {probe_excl_viol}/{probe_tot} "
              f"({100*probe_excl_viol/probe_tot:.0f}%)   "
              f"exhaustiveness gap = {probe_exhaust_gap}/{probe_tot} "
              f"({100*probe_exhaust_gap/probe_tot:.0f}%)")
    return {"n": n, "specific": spec, "any": any_, "probe_tot": probe_tot,
            "excl": probe_excl_viol, "gap": probe_exhaust_gap}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gen-model", default="meta-llama/llama-3.3-70b-instruct",
                    help="partition GENERATOR model")
    ap.add_argument("--judge-model", default=None,
                    help="INDEPENDENT judge/probe model (default = gen-model; set "
                         "a different model to remove generator self-confidence bias)")
    ap.add_argument("--probes", type=int, default=6, help="probe diseases per case")
    ap.add_argument("--rarearena", type=int, default=0,
                    help="also run N RareArena long-tail cases (gold=diagnoses)")
    ap.add_argument("--dump-overlaps", default=None,
                    help="write per-case partitions + overlapping probes to this JSON")
    ap.add_argument("--gen-mode", choices=["mixed", "single"], default="mixed",
                    help="'single'=force one fundamentum divisionis (anti-overlap)")
    args = ap.parse_args()
    dump = [] if args.dump_overlaps else None

    gen, _, _, _ = make_poster(args.gen_model)
    judge_model = args.judge_model or args.gen_model
    _, judge, judge_multi, gen_probes = make_poster(judge_model)
    print(f"MECE quality — generator={args.gen_model}  judge/probe={judge_model}")

    common = json.loads((EVAL / "branch_recall_eval_set.json").read_text())["cases"]
    rare = json.loads((EVAL / "branch_recall_eval_set_hard.json").read_text())["cases"]
    print(f"partition mode = {args.gen_mode}")
    rc = run(common, gen, judge, judge_multi, gen_probes, "COMMON (14)",
             args.probes, dump, args.gen_mode)
    rr = run(rare, gen, judge, judge_multi, gen_probes, "RARE/HARD (8)",
             args.probes, dump, args.gen_mode)

    ra = {"n": 0, "specific": 0, "any": 0, "probe_tot": 0, "excl": 0, "gap": 0}
    if args.rarearena > 0:
        ra_cases = _load_rarearena_as_cases(args.rarearena)
        ra = run(ra_cases, gen, judge, judge_multi, gen_probes,
                 f"RAREARENA long-tail ({len(ra_cases)})", args.probes, dump,
                 args.gen_mode)

    tot_n = rc["n"] + rr["n"] + ra["n"]
    pt = rc["probe_tot"] + rr["probe_tot"] + ra["probe_tot"]
    print(f"\n=== TOTAL (n={tot_n}) ===")
    print(f"  gold reachable(specific): {rc['specific']+rr['specific']+ra['specific']}/{tot_n}"
          f"   (any): {rc['any']+rr['any']+ra['any']}/{tot_n}")
    if pt:
        ev = rc['excl']+rr['excl']+ra['excl']; gp = rc['gap']+rr['gap']+ra['gap']
        print(f"  MECE excl-violation: {ev}/{pt} ({100*ev/pt:.0f}%)   "
              f"exhaustiveness gap: {gp}/{pt} ({100*gp/pt:.0f}%)")
    if dump is not None:
        Path(args.dump_overlaps).write_text(json.dumps(dump, indent=2))
        print(f"\n  overlap dump → {args.dump_overlaps}")
    return 0


def _load_rarearena_as_cases(n: int) -> list:
    """RareArena long-tail cases shaped like the eval sets (l1_target = gold dx)."""
    import random
    path = ROOT / "data" / "case_reports" / "case_reports.jsonl"
    pool = []
    for ln in open(path, encoding="utf-8"):
        d = json.loads(ln)
        if d.get("source") != "rarearena":
            continue
        dxs = d.get("diagnoses") or []
        pres = d.get("presenting") or ""
        if dxs and len(pres) > 120:
            pool.append({"id": d["case_id"], "syndrome": pres.split(".")[0][:160],
                         "context": pres[:400],
                         "l1_target": [[[dxs[0]]]]})
    random.Random(7).shuffle(pool)
    return pool[:n]


if __name__ == "__main__":
    sys.exit(main())
