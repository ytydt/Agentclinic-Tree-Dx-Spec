#!/usr/bin/env python3
"""Independent inventory of explicit negatives/normals in the 11 vignettes.

The 27.9% figure (absent+normal among extracted findings) is a *composition*
statistic of the extractor's output.  This file answers a different question:
of the negatives the vignette actually states, how many never entered the
finding set?

An item is an explicit negative only when the text denies, reports as normal,
or reports as unrevealing/unremarkable/negative.  Closed-world inferences
(Kanavel signs never mentioned) are out of scope.  Lists are split into
atomic members so collapsing can be told apart from a complete miss.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

OPTION_CUT = re.compile(r"\n\s*(what is the most likely diagnosis|options\s*:)", re.I)


def strip_options(text: str) -> str:
    m = OPTION_CUT.search(text)
    return text[: m.start()].rstrip() if m else text


# span must be a verbatim substring of the stripped vignette.  status is filled
# by matching against extracted findings (quote / label / canonical).
ITEMS: list[dict] = [
    # --- 522 ----------------------------------------------------------------
    {"case": "DA_d2_heldout200b/522", "span": "No focal neurologic deficits",
     "item": "focal neurologic deficits", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "Thyroid-stimulating hormone: normal",
     "item": "thyroid-stimulating hormone", "kind": "normal"},
    {"case": "DA_d2_heldout200b/522", "span": "Ammonia levels: normal",
     "item": "ammonia", "kind": "normal"},
    {"case": "DA_d2_heldout200b/522", "span": "Serum rapid plasma reagin: negative",
     "item": "rapid plasma reagin", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "HIV tests: negative",
     "item": "HIV", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "Urinalysis and blood cultures: negative for infection",
     "item": "urinalysis negative for infection", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "Urinalysis and blood cultures: negative for infection",
     "item": "blood cultures negative for infection", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis",
     "item": "LP infectious workup", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis",
     "item": "LP autoimmune workup", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis",
     "item": "LP malignant workup", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis",
     "item": "LP paraneoplastic encephalitis", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "without seizures",
     "item": "seizures on EEG", "kind": "absent"},
    {"case": "DA_d2_heldout200b/522", "span": "CT abdomen/pelvis with contrast: unrevealing",
     "item": "CT abdomen/pelvis", "kind": "absent"},
    # --- 773 ----------------------------------------------------------------
    {"case": "DA_d2_heldout200b/773", "span": "The patient was initially acyanotic",
     "item": "cyanosis (2010-2016)", "kind": "absent"},
    {"case": "DA_d2_heldout200b/773", "span": "with no parenchymal lesions",
     "item": "parenchymal lesions", "kind": "absent"},
    {"case": "DA_d2_heldout200b/773", "span": "indicating normal cardiac function",
     "item": "natriuretic peptide", "kind": "normal"},
    {"case": "DA_d2_heldout200b/773", "span": "No evidence of pulmonary embolism",
     "item": "pulmonary embolism", "kind": "absent"},
    {"case": "DA_d2_heldout200b/773", "span": "or pulmonary arteriovenous fistulae",
     "item": "pulmonary arteriovenous fistulae", "kind": "absent"},
    # --- 119 ----------------------------------------------------------------
    {"case": "DA_d2_seq100/119", "span": "no remarkable medical or family history",
     "item": "medical history", "kind": "absent"},
    {"case": "DA_d2_seq100/119", "span": "no remarkable medical or family history",
     "item": "family history", "kind": "absent"},
    {"case": "DA_d2_seq100/119", "span": "was not concurrently being treated with any medications",
     "item": "concurrent medications", "kind": "absent"},
    {"case": "DA_d2_seq100/119", "span": "which had no obvious effect",
     "item": "treatment response", "kind": "absent"},
    {"case": "DA_d2_seq100/119", "span": "The palms, soles, and oral mucosa were not involved",
     "item": "palms involvement", "kind": "absent"},
    {"case": "DA_d2_seq100/119", "span": "The palms, soles, and oral mucosa were not involved",
     "item": "soles involvement", "kind": "absent"},
    {"case": "DA_d2_seq100/119", "span": "The palms, soles, and oral mucosa were not involved",
     "item": "oral mucosa involvement", "kind": "absent"},
    {"case": "DA_d2_seq100/119", "span": "disclosed no abnormal findings",
     "item": "routine blood", "kind": "normal"},
    {"case": "DA_d2_seq100/119", "span": "disclosed no abnormal findings",
     "item": "liver function", "kind": "normal"},
    {"case": "DA_d2_seq100/119", "span": "disclosed no abnormal findings",
     "item": "kidney function", "kind": "normal"},
    {"case": "DA_d2_seq100/119", "span": "disclosed no abnormal findings",
     "item": "antistreptolysin O", "kind": "normal"},
    {"case": "DA_d2_seq100/119", "span": "disclosed no abnormal findings",
     "item": "C-reactive protein", "kind": "normal"},
    {"case": "DA_d2_seq100/119", "span": "disclosed no abnormal findings",
     "item": "antinuclear antibody", "kind": "normal"},
    {"case": "DA_d2_seq100/119", "span": "disclosed no abnormal findings",
     "item": "rheumatoid factor", "kind": "normal"},
    # --- 257 ----------------------------------------------------------------
    {"case": "MCR_seq200b/257", "span": "without skin break",
     "item": "skin break", "kind": "absent"},
    {"case": "MCR_seq200b/257", "span": "He was afebrile",
     "item": "fever", "kind": "absent"},
    {"case": "MCR_seq200b/257", "span": "intact bony anatomy",
     "item": "bony anatomy", "kind": "normal"},
    {"case": "MCR_seq200b/257", "span": "no fracture or dislocation",
     "item": "fracture", "kind": "absent"},
    {"case": "MCR_seq200b/257", "span": "no fracture or dislocation",
     "item": "dislocation", "kind": "absent"},
    # --- 326 ----------------------------------------------------------------
    {"case": "MCR_seq200b/326", "span": "provided no lasting benefit",
     "item": "cefprozil response", "kind": "absent"},
    {"case": "MCR_seq200b/326", "span": "he had no fever",
     "item": "fever on admission", "kind": "absent"},
    {"case": "MCR_seq200b/326", "span": "A serological test for tuberculosis was negative",
     "item": "TB serology", "kind": "absent"},
    # --- 475 ----------------------------------------------------------------
    {"case": "MCR_seq200b/475", "span": "A previously healthy 22-year-old woman",
     "item": "significant past illness", "kind": "absent"},
    {"case": "MCR_seq200b/475", "span": "There were no sensory deficits",
     "item": "sensory deficits", "kind": "absent"},
    {"case": "MCR_seq200b/475", "span": "Tendon reflexes were normal throughout",
     "item": "tendon reflexes", "kind": "normal"},
    {"case": "MCR_seq200b/475", "span": "there was no muscular wasting, pathological reflexes, or focal neurological signs",
     "item": "muscular wasting", "kind": "absent"},
    {"case": "MCR_seq200b/475", "span": "there was no muscular wasting, pathological reflexes, or focal neurological signs",
     "item": "pathological reflexes", "kind": "absent"},
    {"case": "MCR_seq200b/475", "span": "there was no muscular wasting, pathological reflexes, or focal neurological signs",
     "item": "focal neurological signs", "kind": "absent"},
    {"case": "MCR_seq200b/475", "span": "Routine laboratory tests and her personal and family history were unremarkable",
     "item": "routine laboratory tests", "kind": "normal"},
    {"case": "MCR_seq200b/475", "span": "Routine laboratory tests and her personal and family history were unremarkable",
     "item": "personal history", "kind": "absent"},
    {"case": "MCR_seq200b/475", "span": "Routine laboratory tests and her personal and family history were unremarkable",
     "item": "family history", "kind": "absent"},
    {"case": "MCR_seq200b/475", "span": "showed no abnormalities",
     "item": "MRI left upper extremity", "kind": "normal"},
    # --- 49 -----------------------------------------------------------------
    {"case": "MCR_v1_seq100/49", "span": "he had no other significant past medical history",
     "item": "other past medical history", "kind": "absent"},
    {"case": "MCR_v1_seq100/49", "span": "his hemodynamic and respiratory parameters were stable",
     "item": "hemodynamic parameters", "kind": "normal"},
    {"case": "MCR_v1_seq100/49", "span": "his hemodynamic and respiratory parameters were stable",
     "item": "respiratory parameters", "kind": "normal"},
    {"case": "MCR_v1_seq100/49", "span": "without peritoneal signs",
     "item": "peritoneal signs", "kind": "absent"},
    {"case": "MCR_v1_seq100/49", "span": "all other laboratory values were within normal limits",
     "item": "other laboratory values", "kind": "normal"},
    # --- 56 -----------------------------------------------------------------
    {"case": "MCR_v1_seq100/56", "span": "with no recurrence until now",
     "item": "recurrence of prior SCC", "kind": "absent"},
    {"case": "MCR_v1_seq100/56", "span": "He denied tobacco or alcohol use",
     "item": "tobacco use", "kind": "absent"},
    {"case": "MCR_v1_seq100/56", "span": "He denied tobacco or alcohol use",
     "item": "alcohol use", "kind": "absent"},
    {"case": "MCR_v1_seq100/56", "span": "vital signs were normal",
     "item": "vital signs", "kind": "normal"},
    {"case": "MCR_v1_seq100/56", "span": "without dysplasia",
     "item": "dysplasia", "kind": "absent"},
    {"case": "MCR_v1_seq100/56", "span": "negative for pan-cytokeratin and other epithelial markers",
     "item": "pan-cytokeratin", "kind": "absent"},
    {"case": "MCR_v1_seq100/56", "span": "negative for pan-cytokeratin and other epithelial markers",
     "item": "other epithelial markers", "kind": "absent"},
    # --- 74 -----------------------------------------------------------------
    {"case": "MCR_v1_seq100/74", "span": "She had no prior history of syncope, cardiac arrest, or known cardiovascular disease",
     "item": "prior syncope", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "She had no prior history of syncope, cardiac arrest, or known cardiovascular disease",
     "item": "prior cardiac arrest", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "She had no prior history of syncope, cardiac arrest, or known cardiovascular disease",
     "item": "known cardiovascular disease", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "her family denied any illicit drug or alcohol use",
     "item": "illicit drug use", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "her family denied any illicit drug or alcohol use",
     "item": "alcohol use", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "cardiovascular examination was unremarkable",
     "item": "cardiovascular examination", "kind": "normal"},
    {"case": "MCR_v1_seq100/74", "span": "normal chemistry panel and electrolytes",
     "item": "chemistry panel", "kind": "normal"},
    {"case": "MCR_v1_seq100/74", "span": "normal chemistry panel and electrolytes",
     "item": "electrolytes", "kind": "normal"},
    {"case": "MCR_v1_seq100/74", "span": "without any evidence of infarction, pre-excitation, or Brugada pattern",
     "item": "infarction on ECG", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "without any evidence of infarction, pre-excitation, or Brugada pattern",
     "item": "pre-excitation", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "without any evidence of infarction, pre-excitation, or Brugada pattern",
     "item": "Brugada pattern", "kind": "absent"},
    {"case": "MCR_v1_seq100/74", "span": "normal wall thickness",
     "item": "wall thickness", "kind": "normal"},
    {"case": "MCR_v1_seq100/74", "span": "no valvular abnormalities",
     "item": "valvular abnormalities", "kind": "absent"},
    # --- 91 -----------------------------------------------------------------
    {"case": "MCR_v1_seq100/91", "span": "vital signs were normal",
     "item": "vital signs", "kind": "normal"},
    {"case": "MCR_v1_seq100/91", "span": "without other focal deficits",
     "item": "other focal deficits", "kind": "absent"},
    {"case": "MCR_v1_seq100/91", "span": "Postoperative CT showed no complications",
     "item": "postoperative complications", "kind": "absent"},
    {"case": "MCR_v1_seq100/91", "span": "negative staining for CD34, EMA, desmin, muscle-specific actin, and Bcl-2",
     "item": "CD34", "kind": "absent"},
    {"case": "MCR_v1_seq100/91", "span": "negative staining for CD34, EMA, desmin, muscle-specific actin, and Bcl-2",
     "item": "EMA", "kind": "absent"},
    {"case": "MCR_v1_seq100/91", "span": "negative staining for CD34, EMA, desmin, muscle-specific actin, and Bcl-2",
     "item": "desmin", "kind": "absent"},
    {"case": "MCR_v1_seq100/91", "span": "negative staining for CD34, EMA, desmin, muscle-specific actin, and Bcl-2",
     "item": "muscle-specific actin", "kind": "absent"},
    {"case": "MCR_v1_seq100/91", "span": "negative staining for CD34, EMA, desmin, muscle-specific actin, and Bcl-2",
     "item": "Bcl-2", "kind": "absent"},
    # --- 179 ----------------------------------------------------------------
    {"case": "MCR_v2_seq100/179", "span": "other values were normal",
     "item": "other laboratory values (day 1)", "kind": "normal"},
    {"case": "MCR_v2_seq100/179", "span": "there were no signs of infection",
     "item": "signs of infection", "kind": "absent"},
    {"case": "MCR_v2_seq100/179", "span": "increased without transfusion",
     "item": "platelet transfusion", "kind": "absent"},
    {"case": "MCR_v2_seq100/179", "span": "He had no bleeding history or medications",
     "item": "bleeding history", "kind": "absent"},
    {"case": "MCR_v2_seq100/179", "span": "He had no bleeding history or medications",
     "item": "medications", "kind": "absent"},
    {"case": "MCR_v2_seq100/179", "span": "Prothrombin time, activated partial thromboplastin time, and INR were normal",
     "item": "prothrombin time", "kind": "normal"},
    {"case": "MCR_v2_seq100/179", "span": "Prothrombin time, activated partial thromboplastin time, and INR were normal",
     "item": "activated partial thromboplastin time", "kind": "normal"},
    {"case": "MCR_v2_seq100/179", "span": "Prothrombin time, activated partial thromboplastin time, and INR were normal",
     "item": "INR", "kind": "normal"},
    {"case": "MCR_v2_seq100/179", "span": "peripheral smear was unremarkable",
     "item": "peripheral smear", "kind": "normal"},
    {"case": "MCR_v2_seq100/179", "span": "Antiplatelet antibodies and platelet‐associated immunoglobulins were negative",
     "item": "antiplatelet antibodies", "kind": "absent"},
    {"case": "MCR_v2_seq100/179", "span": "Antiplatelet antibodies and platelet‐associated immunoglobulins were negative",
     "item": "platelet-associated immunoglobulins", "kind": "absent"},
    {"case": "MCR_v2_seq100/179", "span": "antinuclear and anti–double‐stranded DNA antibodies were normal",
     "item": "antinuclear antibodies", "kind": "normal"},
    {"case": "MCR_v2_seq100/179", "span": "antinuclear and anti–double‐stranded DNA antibodies were normal",
     "item": "anti-dsDNA antibodies", "kind": "normal"},
    {"case": "MCR_v2_seq100/179", "span": "Viral and bacterial studies were insignificant",
     "item": "viral and bacterial studies", "kind": "normal"},
]


def tokens(s: str) -> set[str]:
    s = re.sub(r"[^a-zA-Z0-9\s]", " ", (s or "").lower())
    return {w for w in s.split() if len(w) >= 3 and not w.isdigit()}


def norm_hyphen(s: str) -> str:
    return (s or "").replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")


def cover(item: dict, findings: list[dict]) -> tuple[str, dict | None]:
    """Return (hit|polarity_error|miss, matching finding)."""
    item_tok = tokens(item["item"])
    span_tok = tokens(item["span"])
    span_low = norm_hyphen(item["span"]).lower()
    item_low = item["item"].lower()
    head = max(item_tok, key=len) if item_tok else ""
    best = None
    for f in findings:
        blob = " ".join(str(f.get(k) or "") for k in ("label", "canonical", "quote"))
        blob_low = norm_hyphen(blob).lower()
        blob_tok = tokens(blob)
        shared_item = item_tok & blob_tok
        shared_span = span_tok & blob_tok
        quoted = span_low[:48] in blob_low or item_low in blob_low
        head_hit = bool(head) and len(head) >= 5 and head in blob_tok
        if not (quoted or shared_item or head_hit or len(shared_span) >= 3):
            continue
        pol = (f.get("polarity") or "").lower()
        quote_low = norm_hyphen(str(f.get("quote") or "")).lower()
        label_can = tokens(str(f.get("label") or "") + " " + str(f.get("canonical") or ""))
        quote_has_span = span_low[:40] in quote_low
        named = bool(item_tok) and (item_tok <= label_can or (len(head) >= 5 and head in label_can))
        ok_pol = pol in {item["kind"], "absent", "normal"}
        if not (quote_has_span or named or (quoted and ok_pol)):
            continue
        score = (0 if ok_pol else 1,
                 0 if quote_has_span or named else 1,
                 -len(shared_item))
        if best is None or score < best[0]:
            best = (score, f, ok_pol, quote_has_span)
    if best is None:
        return "miss", None
    if not best[2]:
        return ("polarity_error" if best[3] else "miss"), best[1]
    return "hit", best[1]


def main() -> int:
    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11.json").read_text("utf-8"))}
    extraction = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30oracleclean_groups.json").read_text("utf-8"))}

    rows = []
    for item in ITEMS:
        vign = strip_options(tasks[item["case"]]["vignette"])
        assert item["span"] in vign, (item["case"], item["span"][:80])
        status, f = cover(item, extraction[item["case"]]["findings"])
        rows.append({
            **item,
            "status": status,
            "matched_label": (f or {}).get("label", ""),
            "matched_polarity": (f or {}).get("polarity", ""),
        })

    out_csv = LEDGER / "explicit_negative_recall_11.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    c = Counter(r["status"] for r in rows)
    n = len(rows)
    entered = c["hit"] + c["collapsed_hit"]
    miss_or_pol = c["miss"] + c["polarity_error"]
    by_case: dict[str, Counter] = {}
    for r in rows:
        by_case.setdefault(r["case"], Counter())[r["status"]] += 1

    # finding-set composition (the 27.9% number)
    findings = [f for e in extraction.values() for f in e["findings"]]
    n_f = len(findings)
    n_neg_f = sum(1 for f in findings if f.get("polarity") in {"absent", "normal"})

    summary = {
        "n_source_items": n,
        "status": dict(c),
        "recall_entered": round(entered / n, 4),
        "miss_rate": round(c["miss"] / n, 4),
        "polarity_error_rate": round(c["polarity_error"] / n, 4),
        "not_in_finding_set": round(miss_or_pol / n, 4),
        "finding_set_negative_share": round(n_neg_f / n_f, 4),
        "n_findings": n_f,
        "n_negative_findings": n_neg_f,
        "by_case": {k: dict(v) for k, v in by_case.items()},
        "misses": [f"{r['case']} :: {r['item']}  [{r['span'][:80]}]"
                   for r in rows if r["status"] == "miss"],
        "polarity_errors": [f"{r['case']} :: {r['item']} -> {r['matched_label']}[{r['matched_polarity']}]"
                            for r in rows if r["status"] == "polarity_error"],
    }
    (LEDGER / "explicit_negative_recall_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"source explicit negatives/normals: {n}")
    print(f"  hit              {c['hit']:3d}  ({100*c['hit']/n:5.1f}%)")
    print(f"  miss             {c['miss']:3d}  ({100*c['miss']/n:5.1f}%)")
    print(f"  polarity_error   {c['polarity_error']:3d}  ({100*c['polarity_error']/n:5.1f}%)")
    print(f"not in finding set (miss + polarity_error): {miss_or_pol}/{n} = {100*miss_or_pol/n:.1f}%")
    print(f"finding-set share absent+normal: {n_neg_f}/{n_f} = {100*n_neg_f/n_f:.1f}%")
    print("\nmisses:")
    for m in summary["misses"]:
        print(f"  {m}")
    print("\npolarity errors:")
    for m in summary["polarity_errors"]:
        print(f"  {m}")
    print(f"\nwrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
