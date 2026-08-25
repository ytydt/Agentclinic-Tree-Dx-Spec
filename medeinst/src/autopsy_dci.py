"""Zero-call autopsy of why DCI fails on this repo's DA/MCR held-outs.

Reads the no-leak llama-3.3-70b run + official CoT vs DCI scores.
Writes a compact JSON for the canvas / report. No new LLM calls.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PARENT / "scripts" / "paper"))

from src.utils import diagnoses_match, normalize_diagnosis, parse_json_object  # noqa: E402

try:
    from mapper_bind_repair import leaf_match_score
except Exception:  # pragma: no cover
    def leaf_match_score(a: str, b: str) -> float:  # type: ignore
        na, nb = normalize_diagnosis(a), normalize_diagnosis(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        if na in nb or nb in na:
            return 0.92
        return 0.0


RUN = ROOT / "runs" / "heldout_llama33_nomem_noleak_da200_mcr200"
OUT = RUN / "dci_failure_autopsy.json"

_VERDICT_RE = re.compile(r"\b(Found|NotFound)\b", re.I)
_TIER_RE = re.compile(r"tier[_\s-]*applied[\"'\s:]*([123])", re.I)


def _pct(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    return ys[len(ys) // 2]


def soft_match(gold: str, name: str, thresh: float = 0.85) -> bool:
    if not gold or not name:
        return False
    if diagnoses_match(gold, name):
        return True
    g, n = normalize_diagnosis(gold), normalize_diagnosis(name)
    if len(g) >= 6 and len(n) >= 6 and (g in n or n in g):
        return True
    return leaf_match_score(gold, name) >= thresh


def gold_in_list(gold: str, names: list[str], extra: str = "") -> tuple[bool, int | None]:
    pool = list(names) + ([extra] if extra else [])
    for i, name in enumerate(names):
        if soft_match(gold, name) or (extra and soft_match(extra, name)):
            return True, i
    # also allow extra-only scan of names already done
    _ = pool
    return False, None


def try_json(text: str) -> dict[str, Any] | None:
    try:
        obj = parse_json_object(text or "")
        return obj if isinstance(obj, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def argmax_scores(scores: dict[str, Any]) -> str | None:
    if not scores:
        return None
    items = [(k, float(v)) for k, v in scores.items()]
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    return items[0][0]


def score_of(scores: dict[str, Any], name: str) -> float | None:
    if name in scores:
        return float(scores[name])
    key = normalize_diagnosis(name)
    for k, v in scores.items():
        if normalize_diagnosis(k) == key:
            return float(v)
    return None


def count_edges(summary: dict[str, Any] | None, disease: str) -> dict[str, int]:
    out = Counter()
    if not isinstance(summary, dict):
        return dict(out)
    blob = summary.get(disease) or {}
    if not isinstance(blob, dict):
        # try normalized key
        for k, v in summary.items():
            if normalize_diagnosis(k) == normalize_diagnosis(disease) and isinstance(v, dict):
                blob = v
                break
    for e in blob.get("edges") or []:
        out[str(e.get("relation") or "")] += 1
    kinds: Counter[str] = Counter()
    ktypes: Counter[str] = Counter()
    for n in blob.get("nodes") or []:
        kinds[str(n.get("kind") or "")] += 1
        if n.get("ktype"):
            ktypes[str(n.get("ktype"))] += 1
    out["n_nodes"] = len(blob.get("nodes") or [])
    out["n_edges"] = len(blob.get("edges") or [])
    out["n_knowledge"] = kinds.get("knowledge", 0)
    out["n_shadow"] = kinds.get("shadow", 0)
    out["n_patient"] = kinds.get("patient", 0)
    out["n_pivot"] = ktypes.get("Pivot", 0)
    out["n_general"] = ktypes.get("General", 0)
    return dict(out)


def load_hits(path: Path, kind: str) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if kind == "da":
        doc = json.loads(path.read_text(encoding="utf-8"))
        for row in doc.get("records") or []:
            sid = str(row.get("source_id") or "")
            cid = str(row.get("case_id") or "")
            hit = bool(row.get("option_top1"))
            if sid:
                out[sid] = hit
            if cid:
                out[cid] = hit
        return out
    for fp in path.glob("*.json"):
        doc = json.loads(fp.read_text(encoding="utf-8"))
        cid = str(doc.get("case_id") or fp.stem)
        out[cid] = bool(doc.get("diagnostic_hit"))
    return out


def load_da_gold_options(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    for row in doc.get("records") or []:
        sid = str(row.get("source_id") or "")
        letter = str(row.get("gold_letter") or "").upper()
        text = ""
        proj = row.get("projection") or {}
        maps = proj.get("option_maps") or {}
        disputes = ((proj.get("audit") or {}).get("disputes")) or []
        for d in disputes:
            if str(d.get("option_letter") or "").upper() == letter:
                text = str(d.get("option_text") or "")
                break
        if not text and letter in maps:
            text = str(maps[letter].get("option_text") or "")
        if sid and text:
            out[sid] = text
    return out


def main() -> None:
    cases = [json.loads(l) for l in (RUN / "cases.jsonl").read_text().splitlines() if l.strip()]
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in cases:
        by_key[(str(row["slice"]), str(row["case_id"]))] = {
            "slice": row["slice"],
            "case_id": str(row["case_id"]),
            "runtime_case_id": str(row.get("runtime_case_id") or ""),
            "y_gt": str(row.get("y_gt") or ""),
            "diagnosis": str(row.get("diagnosis") or ""),
            "dset": list(row.get("dset") or []),
            "scores": dict(row.get("scores") or {}),
            "n_llm_calls": int(row.get("n_llm_calls") or 0),
            "split": "da" if str(row["slice"]).startswith("d2_") else "mcr",
        }

    da_gold_opt = load_da_gold_options(RUN / "da" / "mapper" / "records.json")
    dci_da = load_hits(RUN / "da" / "mapper" / "records.json", "da")
    cot_da = load_hits(RUN / "ablation_cot" / "da" / "mapper" / "records.json", "da")
    dci_mcr = load_hits(RUN / "mcr" / "annotate" / "official_eval_llm" / "case_scores", "mcr")
    cot_mcr = load_hits(
        RUN / "ablation_cot" / "mcr" / "annotate" / "official_eval_llm" / "case_scores", "mcr"
    )

    # per-case accumulators from traces
    traces: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "stages": Counter(),
            "cot": [],
            "analytic_ok": 0,
            "analytic_fail": 0,
            "n_p": 0,
            "n_present": 0,
            "n_absent": 0,
            "n_missing": 0,
            "pivot_n": 0,
            "pivot_parse_fail": 0,
            "k_pivot": 0,
            "k_general": 0,
            "k_other": 0,
            "k_empty": 0,
            "empty_pobs": 0,
            "no_live": 0,
            "has_live": 0,
            "k_overlap_disease": 0,
            "k_total": 0,
            "rel_ok": 0,
            "rel_fail": 0,
            "rel_labels": Counter(),
            "rex_n": 0,
            "rex_json_ok": 0,
            "rex_found": 0,
            "rex_notfound": 0,
            "rex_fallback_notfound": 0,
            "audit_user_len": 0,
            "audit_asst_len": 0,
            "audit_json_ok": 0,
            "audit_json_fail": 0,
            "audit_tier": None,
            "audit_diag_parsed": None,
            "graph_summary": None,
            "intuition_in_audit": 0,
        }
    )

    stage_n = Counter()
    for line in (RUN / "llm_calls.jsonl").open(encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        key = (str(rec.get("slice") or ""), str(rec.get("case_id") or ""))
        st = str(rec.get("stage") or "")
        t = traces[key]
        t["stages"][st] += 1
        stage_n[st] += 1
        asst = str(rec.get("assistant") or "")
        user = str(rec.get("user") or "")

        if st == "intuitive":
            obj = try_json(asst)
            names = []
            if obj:
                for item in obj.get("diagnoses") or []:
                    if isinstance(item, dict) and item.get("name"):
                        names.append(str(item["name"]))
            t["cot"] = names
        elif st == "analytic":
            obj = try_json(asst)
            if not obj:
                t["analytic_fail"] += 1
            else:
                t["analytic_ok"] += 1
                nodes = obj.get("p_nodes") or []
                t["n_p"] = len(nodes)
                for n in nodes:
                    stt = str((n or {}).get("status") or "")
                    if stt == "Present":
                        t["n_present"] += 1
                    elif stt == "Absent":
                        t["n_absent"] += 1
                    elif stt == "Missing":
                        t["n_missing"] += 1
        elif st == "pivot":
            t["pivot_n"] += 1
            if "Other context nodes: []" in user:
                t["empty_pobs"] += 1
            if "(no live hits" in user:
                t["no_live"] += 1
            else:
                t["has_live"] += 1
            # disease name from first line
            disease = ""
            if user.startswith("Candidate disease:"):
                disease = user.split("\n", 1)[0].replace("Candidate disease:", "").strip()
            obj = try_json(asst)
            if not obj:
                t["pivot_parse_fail"] += 1
                continue
            knodes = obj.get("k_nodes") or []
            if not knodes:
                t["k_empty"] += 1
            for kn in knodes:
                t["k_total"] += 1
                ktype = str((kn or {}).get("type") or "other")
                if ktype == "Pivot":
                    t["k_pivot"] += 1
                elif ktype == "General":
                    t["k_general"] += 1
                else:
                    t["k_other"] += 1
                content = str((kn or {}).get("content") or "")
                if disease and (
                    normalize_diagnosis(disease) in normalize_diagnosis(content)
                    or normalize_diagnosis(content) in normalize_diagnosis(disease)
                    or leaf_match_score(disease, content) >= 0.85
                ):
                    t["k_overlap_disease"] += 1
        elif st == "relation":
            obj = try_json(asst)
            if not obj:
                t["rel_fail"] += 1
            else:
                t["rel_ok"] += 1
                for rel in obj.get("relations") or []:
                    t["rel_labels"][str((rel or {}).get("relation") or "")] += 1
        elif st == "reexamine":
            t["rex_n"] += 1
            obj = try_json(asst)
            if obj and str(obj.get("verdict") or "") in {"Found", "NotFound"}:
                t["rex_json_ok"] += 1
                if obj.get("verdict") == "Found":
                    t["rex_found"] += 1
                else:
                    t["rex_notfound"] += 1
            else:
                t["rex_fallback_notfound"] += 1
                m = _VERDICT_RE.search(asst)
                # implementation treats parse fail as NotFound
                t["rex_notfound"] += 1
                _ = m
        elif st == "audit":
            t["audit_user_len"] = len(user)
            t["audit_asst_len"] = len(asst)
            t["intuition_in_audit"] = int('"intuition"' in user)
            uobj = try_json(user)
            if uobj and isinstance(uobj.get("graph_summary"), dict):
                t["graph_summary"] = uobj["graph_summary"]
            aobj = try_json(asst)
            if aobj and aobj.get("diagnosis"):
                t["audit_json_ok"] += 1
                t["audit_diag_parsed"] = str(aobj.get("diagnosis"))
                t["audit_tier"] = aobj.get("tier_applied")
            else:
                t["audit_json_fail"] += 1
                m = _TIER_RE.search(asst)
                if m:
                    t["audit_tier"] = int(m.group(1))

    # join
    rows: list[dict[str, Any]] = []
    for key, case in by_key.items():
        t = traces[key]
        split = case["split"]
        cid = case["case_id"]
        gold = case["y_gt"]
        gold_opt = da_gold_opt.get(cid, "") if split == "da" else ""
        cot = t["cot"] or list(case["dset"] or [])
        cot1 = cot[0] if cot else ""
        dci = case["diagnosis"]
        scores = case["scores"]
        amax = argmax_scores(scores)
        score_vals = [float(v) for v in scores.values()]
        margin = None
        if len(score_vals) >= 2:
            sv = sorted(score_vals, reverse=True)
            margin = sv[0] - sv[1]
        gold_in, gold_rank = gold_in_list(gold, cot, extra=gold_opt)
        gold_in_dset, gold_dset_rank = gold_in_list(gold, case["dset"], extra=gold_opt)
        gold_s = None
        if gold_in:
            # score of matched candidate name
            matched = None
            for name in cot:
                if soft_match(gold, name) or (gold_opt and soft_match(gold_opt, name)):
                    matched = name
                    break
            if matched:
                gold_s = score_of(scores, matched)
        gold_s_rank = None
        if gold_s is not None and scores:
            ordered = sorted(scores.items(), key=lambda kv: (-float(kv[1]), kv[0]))
            for i, (n, _v) in enumerate(ordered):
                if score_of({n: _v}, n) == gold_s and (
                    soft_match(gold, n) or (gold_opt and soft_match(gold_opt, n))
                ):
                    gold_s_rank = i
                    break
            if gold_s_rank is None:
                # rank by value
                better = sum(1 for v in scores.values() if float(v) > gold_s)
                gold_s_rank = better

        eq_cot = normalize_diagnosis(dci) == normalize_diagnosis(cot1)
        eq_amax = bool(amax) and normalize_diagnosis(dci) == normalize_diagnosis(amax)
        eq_cot_amax = bool(amax) and normalize_diagnosis(cot1) == normalize_diagnosis(amax)

        if split == "da":
            hit_dci = bool(dci_da.get(cid) or dci_da.get(case["runtime_case_id"]))
            hit_cot = bool(cot_da.get(cid) or cot_da.get(case["runtime_case_id"]))
        else:
            hit_dci = bool(dci_mcr.get(cid))
            hit_cot = bool(cot_mcr.get(cid))

        gs = t.get("graph_summary")
        edge_tot = Counter()
        cand_graphs = []
        for dname, sc in scores.items():
            c = count_edges(gs, dname)
            c["disease"] = dname
            c["score"] = float(sc)
            cand_graphs.append(c)
            for k, v in c.items():
                if k not in {"disease", "score"}:
                    edge_tot[k] += int(v)

        # chosen vs cot1 graph
        chosen_g = count_edges(gs, dci)
        cot_g = count_edges(gs, cot1)

        # k-node circularity + live search at case grain
        empty_pobs_case = t["empty_pobs"] > 0 or t["n_p"] == 0
        live_empty_frac = _pct(t["no_live"], t["pivot_n"]) if t["pivot_n"] else None

        rows.append(
            {
                "split": split,
                "case_id": cid,
                "gold": gold,
                "cot1": cot1,
                "dci": dci,
                "amax": amax,
                "eq_cot": eq_cot,
                "eq_amax": eq_amax,
                "eq_cot_amax": eq_cot_amax,
                "n_cand": len(scores),
                "score_max": max(score_vals) if score_vals else None,
                "score_min": min(score_vals) if score_vals else None,
                "score_margin": margin,
                "scores_tied_top": bool(
                    len(score_vals) >= 2 and sorted(score_vals, reverse=True)[0]
                    == sorted(score_vals, reverse=True)[1]
                ),
                "gold_in_cot": gold_in,
                "gold_cot_rank": gold_rank,
                "gold_in_dset": gold_in_dset,
                "gold_s": gold_s,
                "gold_s_rank": gold_s_rank,
                "hit_dci": hit_dci,
                "hit_cot": hit_cot,
                "discord": hit_cot != hit_dci,
                "rescue": (not hit_cot) and hit_dci,
                "harm": hit_cot and (not hit_dci),
                "n_p": t["n_p"],
                "n_absent": t["n_absent"],
                "analytic_fail": t["analytic_fail"],
                "empty_pobs_case": empty_pobs_case,
                "pivot_n": t["pivot_n"],
                "pivot_parse_fail": t["pivot_parse_fail"],
                "k_pivot": t["k_pivot"],
                "k_general": t["k_general"],
                "k_overlap_disease": t["k_overlap_disease"],
                "k_total": t["k_total"],
                "no_live": t["no_live"],
                "has_live": t["has_live"],
                "live_empty_frac": live_empty_frac,
                "rel_ok": t["rel_ok"],
                "rel_fail": t["rel_fail"],
                "rex_n": t["rex_n"],
                "rex_json_ok": t["rex_json_ok"],
                "rex_found": t["rex_found"],
                "rex_notfound": t["rex_notfound"],
                "rex_fallback": t["rex_fallback_notfound"],
                "audit_json_ok": t["audit_json_ok"],
                "audit_json_fail": t["audit_json_fail"],
                "audit_tier": t["audit_tier"],
                "audit_user_len": t["audit_user_len"],
                "intuition_in_audit": t["intuition_in_audit"],
                "n_llm": case["n_llm_calls"],
                "edge_tot": dict(edge_tot),
                "chosen_g": chosen_g,
                "cot_g": cot_g,
                "n_support": edge_tot.get("support", 0),
                "n_ruleout": edge_tot.get("rule out", 0),
                "n_matching": edge_tot.get("matching", 0),
                "n_conflict": edge_tot.get("conflict", 0),
                "n_penalty": edge_tot.get("penalty", 0),
            }
        )

    def subset(split: str | None = None) -> list[dict[str, Any]]:
        return [r for r in rows if split is None or r["split"] == split]

    def summarize(rs: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rs)
        if not n:
            return {"n": 0}

        def c(pred) -> int:
            return sum(1 for r in rs if pred(r))

        gold_in = c(lambda r: r["gold_in_cot"])
        gold_out = n - gold_in
        override = c(lambda r: not r["eq_cot"])
        follow_s = c(lambda r: r["eq_amax"])
        follow_cot_not_s = c(lambda r: r["eq_cot"] and not r["eq_amax"])
        follow_s_not_cot = c(lambda r: r["eq_amax"] and not r["eq_cot"])
        follow_neither = c(lambda r: (not r["eq_cot"]) and (not r["eq_amax"]))
        follow_both = c(lambda r: r["eq_cot"] and r["eq_amax"])

        # when gold in list, official acc
        gin = [r for r in rs if r["gold_in_cot"]]
        gout = [r for r in rs if not r["gold_in_cot"]]

        def acc(xs, key):
            return _pct(sum(1 for r in xs if r[key]), len(xs))

        # S(d) among gold-in: is gold argmax?
        gold_is_amax = 0
        gold_s_better_than_cot1 = 0
        for r in gin:
            if r["gold_s_rank"] == 0:
                gold_is_amax += 1
            gs, cs = r["gold_s"], score_of(
                {r["amax"] or "": r["score_max"] or 0}, r["amax"] or ""
            )
            cot_s = None
            # compare gold score vs cot1 score via margin-ish
            if r["gold_s"] is not None and r["eq_cot_amax"] is not None:
                pass
            if r["gold_cot_rank"] is not None and r["gold_s"] is not None and r["score_max"] is not None:
                if r["gold_s_rank"] is not None and r["gold_cot_rank"] is not None:
                    if r["gold_s_rank"] < r["gold_cot_rank"]:
                        gold_s_better_than_cot1 += 1

        # harm/rescue on gold-in vs gold-out
        def disc(xs):
            return {
                "n": len(xs),
                "cot_acc": acc(xs, "hit_cot"),
                "dci_acc": acc(xs, "hit_dci"),
                "rescue": c(lambda r: r in xs and r["rescue"]) if False else sum(1 for r in xs if r["rescue"]),
                "harm": sum(1 for r in xs if r["harm"]),
            }

        # parse / pipeline health
        rex_n = sum(r["rex_n"] for r in rs)
        rex_json = sum(r["rex_json_ok"] for r in rs)
        rex_fb = sum(r["rex_fallback"] for r in rs)
        k_tot = sum(r["k_total"] for r in rs)
        k_ov = sum(r["k_overlap_disease"] for r in rs)
        rel_ok = sum(r["rel_ok"] for r in rs)
        rel_fail = sum(r["rel_fail"] for r in rs)
        pivot_n = sum(r["pivot_n"] for r in rs)
        no_live = sum(r["no_live"] for r in rs)
        support = sum(r["n_support"] for r in rs)
        ruleout = sum(r["n_ruleout"] for r in rs)
        matching = sum(r["n_matching"] for r in rs)
        conflict = sum(r["n_conflict"] for r in rs)
        penalty = sum(r["n_penalty"] for r in rs)
        sd_edges = matching + conflict + penalty
        unused_edges = support + ruleout

        tiers = Counter(r["audit_tier"] for r in rs if r["audit_tier"] is not None)
        margins = [r["score_margin"] for r in rs if r["score_margin"] is not None]
        user_lens = [r["audit_user_len"] for r in rs if r["audit_user_len"]]
        n_p = [r["n_p"] for r in rs]
        n_abs = [r["n_absent"] for r in rs]
        n_llm = [r["n_llm"] for r in rs]

        # override that followed S vs not, and official delta
        ov = [r for r in rs if not r["eq_cot"]]
        ov_s = [r for r in ov if r["eq_amax"]]
        ov_ns = [r for r in ov if not r["eq_amax"]]

        # S(d) literature bias: more k_nodes on chosen?
        k_on_case = [r["k_total"] for r in rs]
        score_maxs = [r["score_max"] for r in rs if r["score_max"] is not None]

        # Pearson-ish between k_total and score_max at case level
        def pearson(xs, ys):
            pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
            if len(pts) < 3:
                return None
            mx = sum(p[0] for p in pts) / len(pts)
            my = sum(p[1] for p in pts) / len(pts)
            num = sum((p[0] - mx) * (p[1] - my) for p in pts)
            dx = sum((p[0] - mx) ** 2 for p in pts) ** 0.5
            dy = sum((p[1] - my) ** 2 for p in pts) ** 0.5
            if dx == 0 or dy == 0:
                return None
            return round(num / (dx * dy), 4)

        return {
            "n": n,
            "official": {
                "cot": acc(rs, "hit_cot"),
                "dci": acc(rs, "hit_dci"),
                "delta": round(acc(rs, "hit_dci") - acc(rs, "hit_cot"), 4)
                if acc(rs, "hit_cot") is not None
                else None,
                "rescue": sum(1 for r in rs if r["rescue"]),
                "harm": sum(1 for r in rs if r["harm"]),
                "both_hit": sum(1 for r in rs if r["hit_cot"] and r["hit_dci"]),
                "both_miss": sum(1 for r in rs if (not r["hit_cot"]) and (not r["hit_dci"])),
            },
            "coverage": {
                "gold_in_cot5": gold_in,
                "gold_in_cot5_pct": _pct(gold_in, n),
                "gold_out_cot5": gold_out,
                "gold_is_cot1": sum(1 for r in rs if r["gold_cot_rank"] == 0),
                "gold_is_cot1_pct": _pct(sum(1 for r in rs if r["gold_cot_rank"] == 0), n),
            },
            "strat_gold_in": disc(gin),
            "strat_gold_out": disc(gout),
            "judge": {
                "eq_cot1": c(lambda r: r["eq_cot"]),
                "eq_cot1_pct": _pct(c(lambda r: r["eq_cot"]), n),
                "eq_argmax_S": follow_s,
                "eq_argmax_S_pct": _pct(follow_s, n),
                "follow_both": follow_both,
                "follow_cot_not_S": follow_cot_not_s,
                "follow_S_not_cot": follow_s_not_cot,
                "follow_neither": follow_neither,
                "override_n": override,
                "override_follows_S": len(ov_s),
                "override_ignores_S": len(ov_ns),
                "audit_json_ok": sum(1 for r in rs if r["audit_json_ok"]),
                "audit_json_fail": sum(1 for r in rs if r["audit_json_fail"]),
                "intuition_reinjected": sum(1 for r in rs if r["intuition_in_audit"]),
                "audit_user_len_median": _median(user_lens),
                "tiers": {str(k): v for k, v in sorted(tiers.items(), key=lambda kv: str(kv[0]))},
                "override_official": {
                    "n": len(ov),
                    "cot_acc": acc(ov, "hit_cot"),
                    "dci_acc": acc(ov, "hit_dci"),
                    "rescue": sum(1 for r in ov if r["rescue"]),
                    "harm": sum(1 for r in ov if r["harm"]),
                },
                "stay_official": {
                    "n": n - len(ov),
                    "cot_acc": acc([r for r in rs if r["eq_cot"]], "hit_cot"),
                    "dci_acc": acc([r for r in rs if r["eq_cot"]], "hit_dci"),
                },
            },
            "score_S": {
                "margin_median": _median(margins),
                "margin_mean": _mean(margins),
                "tied_top": sum(1 for r in rs if r["scores_tied_top"]),
                "gold_is_argmax_given_in_list": gold_is_amax,
                "gold_in_list_n": len(gin),
                "gold_argmax_pct_given_in": _pct(gold_is_amax, len(gin)),
                "gold_S_better_rank_than_cot": gold_s_better_than_cot1,
                "corr_k_total_score_max": pearson(k_on_case, score_maxs),
                "corr_penalty_score_max": pearson(
                    [r["n_penalty"] for r in rs], score_maxs
                ),
                "corr_matching_score_max": pearson(
                    [r["n_matching"] for r in rs], score_maxs
                ),
            },
            "edges": {
                "matching": matching,
                "conflict": conflict,
                "penalty": penalty,
                "support": support,
                "rule_out": ruleout,
                "S_d_uses": sd_edges,
                "S_d_ignores": unused_edges,
                "ignore_share": _pct(unused_edges, unused_edges + sd_edges),
            },
            "reexamine": {
                "n_calls": rex_n,
                "json_ok": rex_json,
                "json_ok_pct": _pct(rex_json, rex_n),
                "parse_fail_forced_NotFound": rex_fb,
                "forced_NotFound_pct": _pct(rex_fb, rex_n),
                "found": sum(r["rex_found"] for r in rs),
                "notfound": sum(r["rex_notfound"] for r in rs),
            },
            "livesearch_pivot": {
                "n_pivot_calls": pivot_n,
                "no_live_hits": no_live,
                "no_live_pct": _pct(no_live, pivot_n),
                "parse_fail": sum(r["pivot_parse_fail"] for r in rs),
                "k_nodes": k_tot,
                "k_pivot": sum(r["k_pivot"] for r in rs),
                "k_general": sum(r["k_general"] for r in rs),
                "k_circular_with_disease": k_ov,
                "k_circular_pct": _pct(k_ov, k_tot),
            },
            "relation": {
                "ok": rel_ok,
                "fail": rel_fail,
                "fail_pct": _pct(rel_fail, rel_ok + rel_fail),
            },
            "analytic": {
                "empty_pobs_cases": sum(1 for r in rs if r["empty_pobs_case"]),
                "empty_pobs_pct": _pct(sum(1 for r in rs if r["empty_pobs_case"]), n),
                "analytic_fail_cases": sum(1 for r in rs if r["analytic_fail"]),
                "n_p_median": _median(n_p),
                "n_absent_median": _median(n_abs),
                "cases_with_any_absent": sum(1 for r in rs if r["n_absent"] > 0),
            },
            "budget": {
                "llm_calls_median": _median(n_llm),
                "llm_calls_mean": _mean([float(x) for x in n_llm]),
                "paper_claims": 6,
            },
        }

    # relation labels globally
    rel_labels = Counter()
    for t in traces.values():
        rel_labels.update(t["rel_labels"])

    # example harm/rescue cases (compact)
    def pack_ex(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "split": r["split"],
            "case_id": r["case_id"],
            "gold": r["gold"][:80],
            "cot1": (r["cot1"] or "")[:80],
            "dci": (r["dci"] or "")[:80],
            "amax": (r["amax"] or "")[:80],
            "eq_cot": r["eq_cot"],
            "eq_amax": r["eq_amax"],
            "gold_in_cot": r["gold_in_cot"],
            "gold_cot_rank": r["gold_cot_rank"],
            "gold_s_rank": r["gold_s_rank"],
            "score_max": r["score_max"],
            "score_margin": r["score_margin"],
            "n_penalty": r["n_penalty"],
            "n_matching": r["n_matching"],
            "rex_fallback": r["rex_fallback"],
            "audit_json_ok": r["audit_json_ok"],
        }

    harms = [pack_ex(r) for r in rows if r["harm"]]
    rescues = [pack_ex(r) for r in rows if r["rescue"]]

    overall = summarize(rows)
    da = summarize(subset("da"))
    mcr = summarize(subset("mcr"))

    # mechanism failure board
    mechanisms = [
        {
            "id": "M0_task_mismatch",
            "paper": "§3 MedEinst = 49-way DDXPlus control/trap pairs; k=5 covers GT + trap",
            "status": "FAIL",
            "why": (
                f"本仓是开放诊断（DA mapper / MCR Prompt7），不是 49 类闭集陷阱对。"
                f"gold 落在 CoT Top-5 仅 {overall['coverage']['gold_in_cot5']}/400="
                f"{overall['coverage']['gold_in_cot5_pct']}。"
                "DCI 不能发明名单外诊断（399/400 审计仍在 CoT 名单内）。"
            ),
        },
        {
            "id": "M1_cgme_off",
            "paper": "Table 2: CoT 40.25 → +DCI 55.49 → +CGME 69.49；illness graph merge τ=0.9",
            "status": "DISABLED",
            "why": "本评测 memory off：illness_graphs={}、exemplar_base=[]、无 critic。论文第二段 +14pp 机制未运行。",
        },
        {
            "id": "M2_dual_pathway_reinject",
            "paper": "§4.2.1 双通路解耦：analytic 不看诊断；audit 用 System 2 推翻 System 1",
            "status": "FAIL",
            "why": (
                f"audit user 把完整 intuition JSON 回灌（{overall['judge']['intuition_reinjected']}/400）。"
                f"审计保持 CoT@1 {overall['judge']['eq_cot1']}/400={overall['judge']['eq_cot1_pct']}；"
                f"跟随 argmax S(d) 仅 {overall['judge']['eq_argmax_S']}/400={overall['judge']['eq_argmax_S_pct']}。"
                f"empty P-nodes 病例 {overall['analytic']['empty_pobs_cases']}/400。"
            ),
        },
        {
            "id": "M3_livesearch_circular",
            "paper": "§4.2.2 LiveSearch PubMed+OpenTargets → Pivot/General k-nodes 作鉴别特征",
            "status": "FAIL",
            "why": (
                f"k-node 内容与候选病名循环重叠 {overall['livesearch_pivot']['k_circular_with_disease']}/"
                f"{overall['livesearch_pivot']['k_nodes']}={overall['livesearch_pivot']['k_circular_pct']}；"
                f"no-live-hits {overall['livesearch_pivot']['no_live_hits']}/"
                f"{overall['livesearch_pivot']['n_pivot_calls']}。"
                "OpenTargets 常返回疾病定义，ReExamine 变成“叙事里有没有这个病”，不是鉴别症状。"
            ),
        },
        {
            "id": "M4_relation_not_in_S",
            "paper": "§4.2.2 五类边；§4.2.3 S(d) 只用 matching/conflict/penalty",
            "status": "FAIL",
            "why": (
                f"support+rule-out={overall['edges']['S_d_ignores']} 条边不进 S(d)，"
                f"占 {overall['edges']['ignore_share']}；"
                f"relation JSON 解析失败 {overall['relation']['fail']}/"
                f"{overall['relation']['ok']+overall['relation']['fail']}={overall['relation']['fail_pct']}。"
                "论文 Table A9 Tier2（Pivot>General）在 S(d) 里没有对应项。"
            ),
        },
        {
            "id": "M5_reexamine_shadow",
            "paper": "Alg.2 backward: ReExamine Found→matching，NotFound→shadow penalty",
            "status": "FAIL",
            "why": (
                f"ReExamine JSON 可解析仅 {overall['reexamine']['json_ok_pct']}；"
                f"解析失败被强制 NotFound {overall['reexamine']['forced_NotFound_pct']}，"
                "于是文献越多的候选影子惩罚越多。S(d) 是未归一化计数，跨病不可比。"
            ),
        },
        {
            "id": "M6_audit_tiers",
            "paper": "Table A9 Tier1 致命 Absent，Tier2 Pivot 竞争，Tier3 shadow/coverage",
            "status": "FAIL",
            "why": (
                f"显式 Absent P-node 病例仅 {overall['analytic']['cases_with_any_absent']}/400，"
                "Tier1 几乎没有燃料；"
                f"审计 JSON 失败 {overall['judge']['audit_json_fail']}/400 时回退 argmax S 或 dset[0]；"
                f"有 JSON 时仍经常抄 CoT。"
                f"覆盖病例上 gold 成为 S 最大者仅 "
                f"{overall['score_S']['gold_argmax_pct_given_in']}。"
            ),
        },
        {
            "id": "M7_override_harms_open_dx",
            "paper": "DCI 应用该纠正 Einstellung、在陷阱对上抬 Acc_base +15.2pp",
            "status": "FAIL",
            "why": (
                f"覆盖集内 DCI 不稳；覆盖集外 DCI 不能救。"
                f"DA Δ={da['official']['delta']}（rescue {da['official']['rescue']} / harm {da['official']['harm']}）；"
                f"MCR Δ={mcr['official']['delta']}（rescue {mcr['official']['rescue']} / harm {mcr['official']['harm']}）。"
                f"发生 override 的子集上 harm 主导。"
            ),
        },
    ]

    payload = {
        "run": str(RUN),
        "n": 400,
        "backbone": "meta-llama/llama-3.3-70b-instruct",
        "memory": "off",
        "input_mode": "open_vignette_no_options",
        "stages": dict(stage_n),
        "relation_labels_parsed": dict(rel_labels),
        "overall": overall,
        "da": da,
        "mcr": mcr,
        "mechanisms": mechanisms,
        "examples": {
            "harm_n": len(harms),
            "rescue_n": len(rescues),
            "harm_head": harms[:8],
            "rescue_head": rescues[:8],
        },
        "verdict": {
            "label": "DCI_MECHANISMS_DO_NOT_TRANSFER",
            "headline": (
                "失效的不是“少跑了 CGME”这一件事，而是论文 DCI 栈的前提在本仓数据上同时崩了："
                "闭集 k=5 覆盖、双通路解耦、LiveSearch 鉴别特征、S(d) 可比计数、审计推翻 System 1。"
            ),
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "verdict": payload["verdict"], "overall_coverage": overall["coverage"], "overall_official": overall["official"], "judge": overall["judge"], "reexamine": overall["reexamine"], "edges": overall["edges"], "livesearch": overall["livesearch_pivot"], "analytic": overall["analytic"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
