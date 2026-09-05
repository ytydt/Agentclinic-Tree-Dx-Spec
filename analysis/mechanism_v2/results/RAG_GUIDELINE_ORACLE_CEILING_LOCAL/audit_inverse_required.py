#!/usr/bin/env python3
"""Before/after census: true diagnostic necessities vs other relation slots.

Compares the §14.4 inverse list (G1–G3) and the 15 original-OK ``required_for``
rows on case 74, raw vs F7-after-§16.7.  False workup ``required_for`` is out
of scope (already cleared).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import gate_assertions as ga  # noqa: E402


def uniq_key(a: dict) -> tuple:
    return (
        str(a.get("subject") or "").lower(),
        str(a.get("relation") or "").lower(),
        str(a.get("polarity") or "").lower(),
        str(a.get("modality") or "").lower(),
        str(a.get("predicate") or "").lower(),
        str(a.get("quote") or "")[:80].lower(),
    )


def uniq(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in rows:
        k = uniq_key(a)
        if k in seen:
            continue
        seen.add(k)
        out.append(a)
    return out


OK_PAT = [
    ("type_i_necessary", r"necessary for the diagnosis", r"type I|type 1"),
    ("type_i_precordial", r"precordial leads|at least 2 of", r"."),
    ("cpvt_struct", r"structurally normal", r"."),
    ("cpvt_ecg", r"^normal ECG$", r"."),
    ("arvc_criterion", r"at least 1 criterion must", r"."),
    ("epilepsy_seizures", r"two or more unprovoked", r"."),
    ("metabolic_3", r"3 or more metabolic", r"."),
    ("tako_angio", r"can only be made after", r"."),
    ("myotonia_combo", r"combination of clinical, electrophysiological", r"."),
    ("alcohol_history", r"chronic heavy alcohol", r"."),
]


def ok_tag(a: dict) -> str | None:
    q, p = a.get("quote") or "", a.get("predicate") or ""
    for name, qre, pre in OK_PAT:
        if re.search(qre, q, re.I) and re.search(pre, p + " " + q, re.I):
            return name
    return None


def find_gated(gated_all: list[dict], a0: dict) -> list[dict]:
    subj = (a0.get("subject") or "").lower()
    q = (a0.get("quote") or "")[:80].lower()
    return [
        g for g in gated_all
        if (g.get("subject") or "").lower() == subj
        and (g.get("quote") or "")[:80].lower() == q
    ]


def slot_of(hits: list[dict], orig_rel: str) -> str:
    """Best description of where this quote+subject landed."""
    if not hits:
        return "dropped"
    rels = {(h.get("relation") or "").lower() for h in hits}
    if orig_rel == "pathognomonic_for" and "required_for" in rels and "pathognomonic_for" not in rels:
        # dual-slot sibling kept, patho gone
        if any((h.get("_gate_prev_relation") or "") == "pathognomonic_for"
               or "G1_dual_slot" in str(h.get("_gate") or "")
               or "E12_or_E4_patho_no_cue" in str(h.get("_gate") or "")
               for h in hits):
            if any("G1_dual_slot" in str(h.get("_gate") or "") for h in hits):
                return "required_for (dual resolved; patho demoted)"
            if "feature_of" in rels:
                return "feature_of (patho demoted, not recovered)"
        return "required_for (sibling kept)"
    if "required_for" in rels:
        mods = {(h.get("modality") or "").lower()
                for h in hits if (h.get("relation") or "").lower() == "required_for"}
        gates = [str(h.get("_gate") or "") for h in hits
                 if (h.get("relation") or "").lower() == "required_for"]
        how = next((g for g in gates if g), "")
        mod = "obligatory" if "obligatory" in mods else (next(iter(mods)) if mods else "")
        return f"required_for/{mod}" + (f" [{how}]" if how else "")
    return "/".join(sorted(rels))


def main() -> int:
    hs = json.loads((LEDGER / "case74_highstakes_unique.json").read_text("utf-8"))
    ext = json.loads((LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))
    case = next(e for e in ext if e["case_key"].endswith("/74"))
    raw = [a for a in case["assertions"] if isinstance(a, dict)]
    gated_all = ga.gate_assertions(raw)

    req = [a for a in hs if (a.get("relation") or "").lower() == "required_for"]
    orig_ok = [(ok_tag(a), a) for a in req if ok_tag(a)]
    # type_i_precordial also matches type_i_necessary quotes? order in OK_PAT
    # puts necessary first.  Filter precordial to those with at least 2 / V1.
    orig_ok_dedup = []
    seen = set()
    for tag, a in orig_ok:
        k = uniq_key(a)
        if k in seen:
            continue
        seen.add(k)
        orig_ok_dedup.append((tag, a))

    ok_after = []
    for tag, a in orig_ok_dedup:
        hits = find_gated(gated_all, a)
        still = any((h.get("relation") or "").lower() == "required_for" for h in hits)
        ok_after.append({
            "tag": tag,
            "subject": a.get("subject"),
            "predicate": a.get("predicate"),
            "quote": a.get("quote"),
            "raw_relation": "required_for",
            "after": slot_of(hits, "required_for"),
            "kept": still,
        })

    g1 = [
        ("G1_type_i_dual_patho",
         lambda a: (a.get("relation") or "").lower() == "pathognomonic_for"
         and "necessary for the diagnosis" in (a.get("quote") or "").lower()),
        ("G1_lqts_tautology",
         lambda a: (a.get("relation") or "").lower() == "pathognomonic_for"
         and re.search(r"termed long QT|congenital long QT|Fig\.16\.35|"
                       r"prolonged QT syndrome|prolongation of the QT",
                       a.get("quote") or "", re.I)),
        ("G1_arvc_fibrofatty",
         lambda a: (a.get("relation") or "").lower() == "pathognomonic_for"
         and re.search(r"fibrofatty|fibrous tissue and fat|replacement of myocytes",
                       (a.get("quote") or "") + " " + (a.get("predicate") or ""), re.I)),
        ("G1_se_5min",
         lambda a: (a.get("relation") or "").lower() == "pathognomonic_for"
         and re.search(r"5 min", a.get("quote") or "", re.I)
         and re.search(r"seizure|epilepticus",
                       (a.get("predicate") or "") + (a.get("subject") or ""), re.I)),
    ]
    g2 = [
        ("G2_qtc_normal_cut",
         lambda a: (a.get("relation") or "").lower() == "excludes"
         and re.search(r"less than 440|less than 460", a.get("quote") or "", re.I)),
        ("G2_alc_absence_etio",
         lambda a: (a.get("relation") or "").lower() == "excludes"
         and "absence of other etiologies" in (a.get("quote") or "").lower()),
        ("G2_hcm_absence",
         lambda a: (a.get("relation") or "").lower() == "excludes"
         and re.search(r"in the absence of", a.get("quote") or "", re.I)
         and re.search(r"hypertrophic|HCM|hypertension|aortic|storage|Cardiomyopathy",
                       (a.get("subject") or "") + (a.get("quote") or ""), re.I)),
    ]
    g3 = [
        ("G3_cpvt_bidir",
         lambda a: (a.get("relation") or "").lower() == "feature_of"
         and re.search(r"CPVT|catecholaminergic", a.get("subject") or "", re.I)
         and re.search(r"bidirectional|polymorphic VT|polymorphic PVCs|catecholamine induced",
                       a.get("predicate") or "", re.I)),
        ("G3_qtc_prolonged_cut",
         lambda a: (a.get("relation") or "").lower() == "feature_of"
         and "QTc is prolonged (>440" in (a.get("quote") or "")),
        ("G3_hcm_defined_lvh",
         lambda a: re.search(r"defined_as|feature_of", a.get("relation") or "", re.I)
         and re.search(r"defined as left ventricular hypertrophy", a.get("quote") or "", re.I)),
    ]

    inverse = []
    for name, fn in g1 + g2 + g3:
        rows = uniq([a for a in hs if fn(a)])
        if not rows:
            rows = uniq([a for a in raw if fn(a)])
        rec = still = 0
        items = []
        for a in rows:
            hits = find_gated(gated_all, a)
            recovered = any((h.get("relation") or "").lower() == "required_for" for h in hits)
            rec += recovered
            still += not recovered
            items.append({
                "subject": a.get("subject"),
                "raw_relation": a.get("relation"),
                "predicate": a.get("predicate"),
                "quote": (a.get("quote") or "")[:120],
                "after": slot_of(hits, a.get("relation") or ""),
                "recovered_to_required_for": recovered,
            })
        inverse.append({
            "cluster": name,
            "n_unique": len(rows),
            "recovered_to_required_for": rec,
            "still_other_slot": still,
            "items": items,
        })

    n_req_after = len(uniq([
        a for a in gated_all if (a.get("relation") or "").lower() == "required_for"
    ]))
    n_req_440 = sum(
        1 for a in uniq([a for a in gated_all
                         if (a.get("relation") or "").lower() == "required_for"])
        if re.search(r"440|460", (a.get("quote") or "") + str(a.get("threshold") or ""))
    )

    report = {
        "case_key": "MCR_v1_seq100/74",
        "original_ok_required_for": {
            "n": len(orig_ok_dedup),
            "kept": sum(1 for r in ok_after if r["kept"]),
            "demoted": sum(1 for r in ok_after if not r["kept"]),
            "rows": ok_after,
        },
        "inverse_g1_g2_g3": inverse,
        "after_gate_unique_required_for": n_req_after,
        "after_gate_required_for_with_440_or_460": n_req_440,
        "raw_required_for_with_440_or_460": 0,
    }
    out = LEDGER / "case74_inverse_required_after_f9.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== original-OK required_for (census 15 + alcohol history) ===")
    for r in ok_after:
        flag = "KEEP  " if r["kept"] else "DEMOTE"
        print(f"  {flag} {r['tag']:20s} -> {r['after']}")
    print(f"  kept {report['original_ok_required_for']['kept']}/"
          f"{report['original_ok_required_for']['n']}")

    print("\n=== G1–G3 inverse (true necessity in another slot) ===")
    for c in inverse:
        print(f"  {c['cluster']:28s} recover {c['recovered_to_required_for']}/"
              f"{c['n_unique']}  still_other {c['still_other_slot']}")
    print(f"\nrequired_for with 440/460: raw 0 -> after {n_req_440}")
    print(f"unique required_for after gate: {n_req_after}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
