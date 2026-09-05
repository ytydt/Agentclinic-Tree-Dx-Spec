#!/usr/bin/env python3
"""Read-only remeasurement of section 34 proxies; no model calls or engine writes.

Run from any directory. The output is an audit of the measurement instrument,
not an estimate of clinical or extraction accuracy.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = HERE.parent / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(SRC))
from audit_criteria_fidelity import ALL_OF, ANY_OF, N_OF_M, passages, stated_logic
from measure_2x2_groups import ARMS, locate, prepare, real, span_of


def norm(v):
    return " ".join(str(v or "").split())


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def row_semantics(a):
    return tuple(norm(a.get(k)).lower() for k in
                 ("subject", "predicate", "predicate_kind", "relation", "polarity",
                  "modality", "comparator", "context_type", "_context_hint", "quote")) + (
        json.dumps(a.get("threshold"), sort_keys=True),
        json.dumps(a.get("criterion_group", {}).get("logic")),
        json.dumps(a.get("criterion_group", {}).get("n")),
    )


def census_arm(name, extraction, retrieval):
    data = json.loads((LEDGER / extraction).read_text())
    raw = json.loads((LEDGER / retrieval).read_text())
    by_case, case_gids = {}, {}
    for entry in raw:
        unique = {}
        for bundle in entry["retrieved"].values():
            for p in bundle["passages"]:
                unique.setdefault(str(p["gid"]), p)
        by_case[entry["case_key"]] = [prepare(p["text"]) for p in unique.values()]
        case_gids[entry["case_key"]] = set(unique)
    groups, rows = defaultdict(list), []
    for entry in data:
        for i, a in enumerate(entry.get("assertions") or []):
            if not isinstance(a, dict):
                continue
            rows.append((entry["case_key"], i, a))
            cg = a.get("criterion_group") or {}
            gid = cg.get("group_id")
            if not real(gid) and not isinstance(gid, (int, float)):
                continue
            k = (entry["case_key"], a.get("_source"), a.get("_title"),
                 a.get("_section"), a.get("_focus"), str(gid))
            groups[k].append(a)
    multi = {k:v for k,v in groups.items() if len(v)>=2}
    counts, spans, signatures = Counter(), Counter(), Counter()
    for k, members in multi.items():
        lg = {(a.get("criterion_group") or {}).get("logic") for a in members}
        ns = {(a.get("criterion_group") or {}).get("n") for a in members}
        subjects = {norm(a.get("subject")).lower() for a in members}
        counts["mixed_logic_groups"] += len(lg)>1
        counts["mixed_n_groups"] += len(ns)>1
        counts["mixed_subject_groups"] += len(subjects)>1
        fingerprints = [row_semantics(a) for a in members]
        counts["duplicate_member_rows_exact_semantics"] += len(fingerprints)-len(set(fingerprints))
        signatures[digest([k[1:4],sorted(set(fingerprints))])] += 1
        quotes = [norm(a.get("quote")) for a in members]
        hit = locate(quotes, by_case.get(k[0], []))
        label = span_of(quotes, *hit) if hit else "unlocatable"
        spans[label] += 1
        if hit:
            uniq = set(q for q in quotes if q)
            if any(q not in hit[0] for q in uniq):
                counts["groups_partially_located"] += 1
                counts["partially_located_but_cross_line"] += label=="cross_line"
            if len(uniq)==1 and "\n" not in quotes[0]:
                # one_quote is a special return before physical span inspection.
                q = quotes[0]
                if q in hit[0] and len(q)>1:
                    from measure_2x2_groups import line_of
                    start = hit[0].index(q)
                    counts["one_quote_actually_spans_lines"] += (
                        line_of(hit[1],start)!=line_of(hit[1],start+len(q)-1))
    ps = passages((retrieval,))
    crit = {g:p for g,p in ps.items() if stated_logic(norm(p["text"]))}
    ct = [(g,norm(p["text"])) for g,p in crit.items()]
    linked, join_counts = defaultdict(Counter), Counter()
    for case, i, a in rows:
        q=norm(a.get("quote"))
        if len(q)<12:
            continue
        matching=[g for g,t in ct if q in t]
        if not matching:
            continue
        g=matching[0]
        p=crit[g]
        join_counts["linked_assertions"]+=1
        join_counts["quote_matches_multiple_criteria_passages"]+=len(matching)>1
        join_counts["assigned_gid_not_retrieved_for_case"]+=g not in case_gids[case]
        join_counts["assigned_source_or_title_disagrees_with_assertion"]+=(
            norm(p.get("source"))!=norm(a.get("_source")) or
            norm(p.get("title"))!=norm(a.get("_title")))
        cg=a.get("criterion_group") or {}
        lg=cg.get("logic") if cg.get("group_id") else None
        linked[g][lg or "NO_GROUP"]+=1
    join_counts["passages_with_any_group_despite_more_NO_GROUP_rows"] = sum(
        bool([k for k in c if k in {"all","any","at_least_n"}]) and
        c["NO_GROUP"]>sum(c[k] for k in {"all","any","at_least_n"})
        for c in linked.values())
    decisions = {}
    for g,p in crit.items():
        c=linked.get(g,Counter())
        recognized=[k for k in c if k in {"all","any","at_least_n"}]
        got=max(recognized,key=lambda k:c[k]) if recognized else ("NO_GROUP" if c else "NOT_REACHED")
        decisions[g]={"wanted":stated_logic(norm(p["text"])),"got":got}
    return {
        "arm":name,"extraction":extraction,"retrieval":retrieval,
        "cases":len(data),"assertions":len(rows),"groups_ge2":len(multi),
        "group_members":sum(map(len,multi.values())),"spans":dict(spans),
        "group_identity_diagnostics":dict(counts),
        "distinct_group_semantic_signatures_ignoring_case_focus_gid":len(signatures),
        "repeated_group_semantic_signatures":sum(v>1 for v in signatures.values()),
        "excess_repeated_group_instances":sum(v-1 for v in signatures.values()),
        "relations":dict(Counter(a.get("relation") for _,_,a in rows)),
        "regex_criteria_passages":len(crit),"quote_join_diagnostics":dict(join_counts),
        "proxy_decisions":decisions,
    }


def main():
    result=[census_arm(*a) for a in ARMS]
    (HERE/"measurement_census.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    flips=[]
    for g,d in result[2]["proxy_decisions"].items():
        e=result[3]["proxy_decisions"][g]
        if (d["wanted"]==d["got"]) != (e["wanted"]==e["got"]):
            flips.append({"gid":g,"wanted":d["wanted"],"old":d["got"],"new":e["got"],
                          "reported_flip":"fixed" if e["wanted"]==e["got"] else "broke"})
    (HERE/"v2_proxy_paired_flips.json").write_text(json.dumps(flips,indent=2)+"\n")
    print(json.dumps([{k:v for k,v in r.items() if k not in {"relations","proxy_decisions"}} for r in result],indent=2,ensure_ascii=False))
    ps=passages(("trial_retrieval_x2_v2idx.json",))
    out=[]
    for g,p in ps.items():
        t=norm(p["text"])
        if not stated_logic(t):
            continue
        matches=[]
        for kind,rx in (("all",ALL_OF),("any",ANY_OF),("number",N_OF_M)):
            for m in rx.finditer(t):
                matches.append({"regex":kind,"matched_text":m.group(),
                                "context":t[max(0,m.start()-100):m.end()+200]})
        out.append({"gid":g,"source":p.get("source"),"title":p.get("title"),
                    "section":p.get("section_path"),"proxy_label":stated_logic(t),
                    "matches":matches})
    (HERE/"v2_proxy_criteria_contexts.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")


if __name__=="__main__":
    main()
