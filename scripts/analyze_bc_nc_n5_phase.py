#!/usr/bin/env python3
"""BranchCreator stats for nc_n5_phase K=10 (rep1-10 × 9 cases).

Metrics (first BranchCreator @ timestep 1):
  1. KB injection failure → pure-LLM path (no branch_knowledge block)
  2. Branch creation errors:
     - coverage_fail: gold answer not reachable by any L1 branch/domain
     - axis_mixed: live L1 branches use >1 classification_axis
     - axis_vs_kb: live branch axis != KB l1_classification_axis
     - domain_miss: gold KB domain has no token-overlap branch (MECE gap)
     - axis_opposite: gold domain matched but best-overlap branch's
       why_included contradicts the vignette's key discriminator for gold
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter, defaultdict

CASES = [1, 9, 13, 14, 17, 18, 22, 23, 24]

# Expected §23.14 syndrome id per benchmark case (from vignette phenotype)
EXPECTED_SYNDROME: dict[int, str] = {
    1: "focal_limb_neuro_deficit",
    9: "leukocytosis",
    13: "hyperglycemia_with_skin",
    14: "",  # Kartagener — not in syndrome_axis_map → expect kb_fail
    17: "leukocytosis",
    18: "acute_abdomen_shock",
    22: "hypercalcemia",
    23: "bowel_obstruction",
    24: "unilateral_nasal_discharge",
}

CASE_IDS = CASES
REPS = list(range(1, 11))

GENERIC = {
    "disorder", "disorders", "disease", "diseases", "syndrome", "syndromes",
    "condition", "conditions", "related", "other", "with", "and", "the", "a",
    "an", "or", "due", "to", "non", "process", "causes", "cause", "neoplasm",
    "neoplasms", "tumor", "tumour", "tumors", "mass", "lesion", "increased",
    "decreased", "blast", "blasts", "crisis", "bearing", "incl", "phase",
    "low", "high", "excess", "associated", "mediated", "type", "primary",
    "secondary", "live", "family", "central", "peripheral", "vascular",
}


def _latest_case_dirs() -> dict[int, dict[int, str]]:
    """rep -> case_id -> log path (newest run dir)."""
    out: dict[int, dict[int, str]] = defaultdict(dict)
    for d in glob.glob("logs/medbullets_conc_nc_n5_phase_*_cases"):
        base = os.path.basename(d)
        m = re.match(r"medbullets_conc_nc_n5_phase_(\d+)_\d{8}_\d{6}_cases", base)
        if not m:
            continue
        rep = int(m.group(1))
        mt = os.path.getmtime(d)
        for cid in CASE_IDS:
            log = os.path.join(d, f"case_{cid:02d}.log")
            if not os.path.isfile(log):
                continue
            prev = out[rep].get(cid)
            if prev is None or mt > os.path.getmtime(os.path.dirname(prev)):
                out[rep][cid] = log
    return out


def _tokens(text: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in toks if len(t) > 2 and t not in GENERIC}


def _strip_gloss(text: str) -> str:
    return re.sub(r"\([^)]*\)", " ", text or "")


def _domain_overlap(dom: str, label: str) -> float:
    dt = _tokens(_strip_gloss(dom))
    lt = _tokens(_strip_gloss(label))
    if not dt:
        return 0.0
    return len(dt & lt) / len(dt)


def _extract_json_after(marker: str, text: str, start: int = 0) -> tuple[dict | None, int]:
    i = text.find(marker, start)
    if i < 0:
        return None, -1
    i = text.find("{", i + len(marker))
    if i < 0:
        return None, -1
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[i : j + 1]), j + 1
                except Exception:
                    return None, -1
    return None, -1


def _parse_first_bc(text: str) -> dict | None:
    """Extract first timestep-1 BranchCreator payload + response."""
    kb_m = re.search(
        r"Branch-knowledge \(§23\.14\): syndrome=(\S+) axis=(\S+) domains=(\[.*?\])",
        text,
    )
    kb = None
    if kb_m:
        try:
            domains = json.loads(kb_m.group(3).replace("'", '"'))
        except Exception:
            domains = []
        kb = {"syndrome": kb_m.group(1), "axis": kb_m.group(2), "domains": domains}

    pos = 0
    while True:
        idx = text.find(">>> Module: BranchCreator", pos)
        if idx < 0:
            break
        chunk = text[idx : idx + 400000]
        p_idx = chunk.find("Payload:")
        if p_idx < 0:
            pos = idx + 1
            continue
        payload, _ = _extract_json_after("Payload:", chunk, p_idx)
        if not payload or payload.get("timestep") != 1:
            pos = idx + 1
            continue
        r_idx = chunk.find("RAW LLM RESPONSE:")
        if r_idx < 0:
            pos = idx + 1
            continue
        response, _ = _extract_json_after("RAW LLM RESPONSE:", chunk, r_idx)
        if not response:
            pos = idx + 1
            continue

        bk = payload.get("branch_knowledge") or {}
        if kb and not bk:
            bk = {
                "l1_classification_axis": kb["axis"],
                "mandatory_coverage": kb["domains"],
                "candidate_entities_by_domain": {},
                "syndrome_matched": kb["syndrome"],
            }
        branches = response.get("branches", [])
        if isinstance(branches, dict):
            branches = list(branches.values())
        opts = {o["id"]: o.get("description", "") for o in payload.get("static_options", [])}
        return {
            "kb_log": kb,
            "branch_knowledge": bk if bk else None,
            "branches": branches,
            "static_options": opts,
            "case_summary": payload.get("case_summary", ""),
        }
    return None


def _gold_for_case(rep: int, cid: int) -> tuple[str, str]:
    js = sorted(
        glob.glob(f"logs/medbullets_conc_nc_n5_phase_{rep}_*.json"),
        key=os.path.getmtime,
        reverse=True,
    )
    if not js:
        return "?", ""
    for r in json.load(open(js[0])):
        if r.get("idx") == cid:
            return r.get("gold", "?"), r.get("answer", "")
    return "?", ""


def _project_gold_domain(gold_text: str, domains: list[str]) -> str | None:
    gt = _tokens(gold_text)
    best, score = None, 0.0
    for dom in domains:
        ents = _tokens(dom)
        # also match gold tokens against domain
        overlap = len(gt & ents) / max(len(gt), 1)
        do = _domain_overlap(dom, gold_text)
        s = max(overlap, do)
        if s > score:
            score, best = s, dom
    return best if score >= 0.15 else None


# Gold-answer synonym hooks for L1 coverage (family-level, not entity name)
GOLD_HOOKS: dict[str, list[str]] = {
    "apical lung tumor": ["apical", "pancoast", "compressive plexopathy", "superior sulcus"],
    "leukemoid reaction": ["reactive", "non-malignant leukocytosis", "leukemoid", "infection"],
    "alpha cell tumor": ["alpha", "glucagon", "pancreatic neuroendocrine", "hyperglycemia"],
    "diastolic murmur": ["ciliary", "kartagener", "cystic fibrosis", "primary ciliary", "sinopulmonary"],
    "chronic myelogenous leukemia": ["myeloid", "cml", "mpn", "blast", "leukocytosis", "myeloproliferative"],
    "vascular ectasia": ["hepatic", "peliosis", "vascular", "liver", "hepatobiliary"],
    "parathyroid hormone": ["hyperparathyroid", "pth", "hypercalcemia", "endocrine"],
    "adhesions": ["mechanical bowel", "obstruction", "adhesion", "post-surgical"],
    "foreign body": ["foreign body", "nasal", "rhinitis", "unilateral"],
}


def _gold_hooks(gold_text: str) -> set[str]:
    gl = gold_text.lower()
    hooks: set[str] = set(_tokens(gold_text))
    for key, kws in GOLD_HOOKS.items():
        if key in gl or any(k in gl for k in key.split()):
            hooks.update(kws)
    return hooks


def _coverage_fail(gold_text: str, branches: list, bk: dict | None) -> bool:
    hooks = _gold_hooks(gold_text)
    if not hooks:
        return True
    corpus = " ".join(
        b.get("label", "") + " " + b.get("why_included", "")
        for b in branches
        if isinstance(b, dict)
    ).lower()
    ct = _tokens(corpus)
    if hooks & ct:
        return False
    if any(h in corpus for h in hooks if len(h) > 4):
        return False
    if bk:
        ents = bk.get("candidate_entities_by_domain", {}) or {}
        for elist in ents.values():
            for e in elist:
                et = _tokens(e)
                if hooks & et or any(h in e.lower() for h in hooks):
                    return False
        dom = _project_gold_domain(gold_text, bk.get("mandatory_coverage", []) or [])
        if dom:
            for b in branches:
                if _domain_overlap(dom, b.get("label", "")) >= 0.34:
                    return False
    return True


def _axis_opposite(
    gold_text: str, gold_domain: str | None, branches: list, summary: str
) -> bool:
    """Branch for gold domain exists but why_included flips key discriminator."""
    if not gold_domain:
        return False
    best_b, best = None, 0.0
    for b in branches:
        if b.get("status", "live") == "closed_for_now":
            continue
        ov = _domain_overlap(gold_domain, b.get("label", ""))
        if ov > best:
            best, best_b = ov, b
    if not best_b or best < 0.25:
        return False
    why = (best_b.get("why_included") or "").lower()
    summ = summary.lower()
    # case-specific opposite patterns (key finding supports gold but branch rationale denies)
    patterns = [
        ("hypercalcemia", "malignancy", "low phosph", "primary hyperparathyroid"),
        ("leukocytosis", "reactive", "leukemoid", "non-malignant"),
        ("cml", "lymphoid", "myeloid neoplasm with increased blasts"),
        ("pancoast", "central (brain", "apical", "peripheral neuropathy only"),
        ("foreign body", "systemic", "malignancy"),
    ]
    for keys in patterns:
        if not all(k in summ or k in gold_text.lower() for k in keys[:2]):
            continue
        if any(k in why for k in keys[2:]):
            return True
    return False


def analyze_one(log_path: str, rep: int, cid: int) -> dict:
    text = open(log_path, encoding="utf-8", errors="replace").read()
    parsed = _parse_first_bc(text)
    gold_l, gold_text = _gold_for_case(rep, cid)
    if not parsed:
        return {"error": "no_bc_parse", "rep": rep, "case": cid}

    bk = parsed["branch_knowledge"]
    branches = [b for b in parsed["branches"] if isinstance(b, dict)]
    live = [b for b in branches if b.get("status", "live") != "closed_for_now"]

    kb_fail = bk is None or not bk.get("syndrome_matched")
    exp_syn = EXPECTED_SYNDROME.get(cid, "")
    matched_syn = (bk or {}).get("syndrome_matched") or (parsed["kb_log"] or {}).get("syndrome")
    syndrome_wrong = bool(exp_syn and matched_syn and matched_syn != exp_syn)
    pure_llm = kb_fail  # no block at all
    kb_misroute = syndrome_wrong  # block present but wrong syndrome
    axes = {b.get("classification_axis", "") for b in live if b.get("classification_axis")}
    kb_axis = (bk or {}).get("l1_classification_axis", "")
    axis_mixed = len(axes) > 1
    axis_vs_kb = bool(kb_axis and any(a != kb_axis for a in axes))

    domains = (bk or {}).get("mandatory_coverage", []) or []
    gold_dom = _project_gold_domain(gold_text, domains) if domains else None
    domain_miss = False
    if gold_dom:
        domain_miss = all(
            _domain_overlap(gold_dom, b.get("label", "")) < 0.34 for b in live
        )

    cov_fail = _coverage_fail(gold_text, live, bk)
    opp = _axis_opposite(gold_text, gold_dom, live, parsed["case_summary"])

    return {
        "rep": rep,
        "case": cid,
        "gold": gold_l,
        "gold_text": gold_text,
        "kb_fail": kb_fail,
        "pure_llm": pure_llm,
        "syndrome_wrong": syndrome_wrong,
        "kb_misroute": kb_misroute,
        "expected_syndrome": exp_syn,
        "syndrome": (bk or {}).get("syndrome_matched") or (parsed["kb_log"] or {}).get("syndrome"),
        "kb_axis": kb_axis,
        "coverage_fail": cov_fail,
        "axis_mixed": axis_mixed,
        "axis_vs_kb": axis_vs_kb,
        "domain_miss": domain_miss,
        "axis_opposite": opp,
        "n_branches": len(live),
        "branch_labels": [b.get("label", "") for b in live],
    }


def main() -> None:
    dirs = _latest_case_dirs()
    rows = []
    for rep in REPS:
        for cid in CASE_IDS:
            lp = dirs.get(rep, {}).get(cid)
            if not lp:
                rows.append({"rep": rep, "case": cid, "error": "no_log"})
                continue
            rows.append(analyze_one(lp, rep, cid))

    valid = [r for r in rows if "error" not in r]
    n = len(valid)
    print(f"nc_n5_phase BranchCreator 分析: {n} case-rep 有效 / {len(rows)} 总计\n")

    def rate(key: str) -> float:
        return 100.0 * sum(1 for r in valid if r.get(key)) / n if n else 0

    print("=== 1. 知识注入失败率 ===")
    print(f"  纯 LLM 路径（无 branch_knowledge）:     {sum(1 for r in valid if r['pure_llm'])}/{n} = {100*sum(1 for r in valid if r['pure_llm'])/n:.1f}%")
    print(f"  KB 误路由（syndrome 匹配错误）:       {sum(1 for r in valid if r['syndrome_wrong'])}/{n} = {100*sum(1 for r in valid if r['syndrome_wrong'])/n:.1f}%")
    print(f"  注入失败合计（纯LLM + 误路由）:       {sum(1 for r in valid if r['pure_llm'] or r['syndrome_wrong'])}/{n} = {100*sum(1 for r in valid if r['pure_llm'] or r['syndrome_wrong'])/n:.1f}%")
    syn = Counter(r.get("syndrome") for r in valid if not r["pure_llm"])
    print(f"  成功注入 syndrome 分布: {dict(syn.most_common())}")

    print("\n=== 2. 分支创建错误率 ===")
    print(f"  无法覆盖金标选项 (coverage_fail): {sum(1 for r in valid if r['coverage_fail'])}/{n} = {rate('coverage_fail'):.1f}%")
    print(f"  L1 混轴 (axis_mixed):             {sum(1 for r in valid if r['axis_mixed'])}/{n} = {rate('axis_mixed'):.1f}%")
    print(f"  分支轴 ≠ KB 轴 (axis_vs_kb):      {sum(1 for r in valid if r['axis_vs_kb'])}/{n} = {rate('axis_vs_kb'):.1f}%")
    print(f"  金标域无对应分支 (domain_miss):   {sum(1 for r in valid if r['domain_miss'])}/{n} = {rate('domain_miss'):.1f}%")
    print(f"  轴/域反向 (axis_opposite):        {sum(1 for r in valid if r['axis_opposite'])}/{n} = {rate('axis_opposite'):.1f}%")
    any_err = sum(
        1 for r in valid
        if r["coverage_fail"] or r["axis_mixed"] or r["axis_vs_kb"]
        or r["domain_miss"] or r["axis_opposite"]
    )
    print(f"  任一错误合计:                     {any_err}/{n} = {100*any_err/n:.1f}%" if n else "  任一错误合计: n/a")

    kb_ok = [r for r in valid if not r["pure_llm"] and not r["syndrome_wrong"]]
    nk = len(kb_ok)
    if nk:
        print(f"\n=== 2b. 仅 KB 成功注入子集 (n={nk}) ===")
        def rate_sub(key):
            return 100 * sum(1 for r in kb_ok if r.get(key)) / nk
        print(f"  coverage_fail: {sum(1 for r in kb_ok if r['coverage_fail'])}/{nk} = {rate_sub('coverage_fail'):.1f}%")
        print(f"  axis_mixed:    {sum(1 for r in kb_ok if r['axis_mixed'])}/{nk} = {rate_sub('axis_mixed'):.1f}%")
        print(f"  domain_miss:   {sum(1 for r in kb_ok if r['domain_miss'])}/{nk} = {rate_sub('domain_miss'):.1f}%")

    print("\n=== 3. 按 case 聚合（10 rep）===")
    print(f"{'case':>4} {'gold':>4}  pureLLM  misroute  cov_fail  dom_miss  axis_mix  axis≠kb")
    for cid in CASE_IDS:
        rs = [r for r in valid if r["case"] == cid]
        if not rs:
            continue
        gl = rs[0].get("gold", "?")
        def pct(k):
            return f"{sum(1 for r in rs if r.get(k))}/{len(rs)}"
        print(f"{cid:>4} {gl:>4}  {pct('pure_llm'):>7}  {pct('syndrome_wrong'):>8}  {pct('coverage_fail'):>8}  "
              f"{pct('domain_miss'):>8}  {pct('axis_mixed'):>8}  {pct('axis_vs_kb'):>7}")

    print("\n=== 4. 典型失败样例（coverage_fail 或 domain_miss）===")
    shown = 0
    for r in valid:
        if not (r["coverage_fail"] or r["domain_miss"] or r["axis_opposite"]):
            continue
        print(f"  rep{r['rep']} c{r['case']} gold={r['gold']} ({r['gold_text'][:40]}) "
              f"syndrome={r.get('syndrome')} cov={r['coverage_fail']} dom_miss={r['domain_miss']} "
              f"opp={r['axis_opposite']}")
        print(f"    branches: {r['branch_labels'][:4]}...")
        shown += 1
        if shown >= 12:
            break


if __name__ == "__main__":
    main()
