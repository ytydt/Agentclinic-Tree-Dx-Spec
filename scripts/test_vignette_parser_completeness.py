#!/usr/bin/env python3
"""Test VignetteParser evidence extraction completeness.

Sends a vignette through the LLM-based VignetteParser and checks that ALL
expected clinical facts appear in the extracted evidence_items. This catches
the class of failure where a correctly-written vignette loses pathognomonic
or high-value evidence during the parsing stage.

Usage:
    OPENROUTER_API_KEY2=... python scripts/test_vignette_parser_completeness.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY2", "")
MODEL = "qwen/qwen3-32b"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# ═══════════════════════════════════════════════════════════════════════════
# Test cases: (vignette, expected_evidence_keywords, correct_answer)
#
# expected_evidence_keywords is a list of (label, keywords) tuples.
# "keywords" is a list of strings — at least ONE must appear in at least
# one evidence_item's content for the check to pass.
# ═══════════════════════════════════════════════════════════════════════════

CML_VIGNETTE = """\
A 52-year-old male presents to the emergency department with progressive fatigue,
night sweats, abdominal fullness, and blurred vision over the past 3 weeks. Past
medical history is unremarkable except for well-controlled hypertension.

Physical exam reveals:
- Massive splenomegaly (8 cm below costal margin)
- Bilateral retinal hemorrhages with cotton-wool spots on fundoscopy
- Scattered petechiae on lower extremities

Laboratory findings:
- WBC: 145,000/μL with 82% blasts
- Hemoglobin: 7.2 g/dL
- Platelets: 28,000/μL
- Basophilia: 8%
- LDH: 2,450 U/L (elevated)
- Uric acid: 11.2 mg/dL (elevated)
- Peripheral smear: left-shifted granulocytes at all stages of maturation

Cytogenetics / Molecular studies:
- Philadelphia chromosome (Ph) positive
- BCR-ABL1 fusion gene detected (p210 transcript)

Question: What is the most likely diagnosis?

Options:
A. Chronic Myeloid Leukemia - Blast Crisis (CML-BC)
B. Acute Myeloid Leukemia (AML)
C. Myelodysplastic Syndrome (MDS)
D. Chronic Lymphocytic Leukemia (CLL)
E. Acute Lymphoblastic Leukemia (ALL)
"""

CML_EXPECTED = [
    ("age/sex",              ["52-year-old", "52 year old", "52yo", "52 years", "age: 52"]),
    ("fatigue",              ["fatigue"]),
    ("night sweats",         ["night sweat"]),
    ("blurred vision",       ["blurred vision", "visual"]),
    ("splenomegaly",         ["splenomegaly", "spleen"]),
    ("retinal hemorrhages",  ["retinal hemorrhag", "retinal haemorrhag", "fundoscop"]),
    ("cotton-wool spots",    ["cotton-wool", "cotton wool"]),
    ("petechiae",            ["petechiae", "petechia"]),
    ("WBC 145k",             ["145,000", "145000", "145k"]),
    ("82% blasts",           ["82%", "82 %"]),
    ("hemoglobin",           ["7.2", "hemoglobin", "haemoglobin", "Hgb"]),
    ("platelets",            ["28,000", "28000", "platelet"]),
    ("basophilia",           ["basophil"]),
    ("LDH elevated",         ["LDH", "2,450", "2450"]),
    ("uric acid elevated",   ["uric acid", "11.2"]),
    ("peripheral smear",     ["peripheral smear", "left-shifted", "left shifted", "granulocyte"]),
    ("Philadelphia chr+",    ["philadelphia", "Ph positive", "Ph+", "Ph ("]),
    ("BCR-ABL1 fusion",      ["BCR-ABL", "bcr-abl", "p210"]),
]

PNEUMONIA_VIGNETTE = """\
A 68-year-old female with a history of COPD and type 2 diabetes presents with
3 days of productive cough with rust-colored sputum, fever (39.2°C), and pleuritic
chest pain. On exam: tachypneic (RR 28), SpO2 89% on room air, right lower lobe
crackles on auscultation. Labs: WBC 18,200/μL with left shift, CRP 245 mg/L.
Chest X-ray: right lower lobe consolidation with air bronchograms.
Blood culture: Gram-positive diplococci.

Question: What is the most likely causative organism?

Options:
A. Streptococcus pneumoniae
B. Haemophilus influenzae
C. Klebsiella pneumoniae
D. Staphylococcus aureus
"""

PNEUMONIA_EXPECTED = [
    ("age/sex",              ["68-year-old", "68 year old"]),
    ("COPD",                 ["COPD", "chronic obstructive"]),
    ("diabetes",             ["diabetes"]),
    ("productive cough",     ["cough", "sputum"]),
    ("rust-colored sputum",  ["rust", "sputum"]),
    ("fever 39.2",           ["39.2", "fever"]),
    ("pleuritic chest pain", ["pleuritic", "chest pain"]),
    ("tachypneic",           ["tachypne", "RR 28", "respiratory rate"]),
    ("SpO2 89%",             ["89%", "SpO2", "oxygen"]),
    ("RLL crackles",         ["crackle", "right lower lobe"]),
    ("WBC 18.2k",            ["18,200", "18200", "leukocytosis"]),
    ("CRP 245",              ["CRP", "245"]),
    ("RLL consolidation",    ["consolidation"]),
    ("air bronchograms",     ["air bronchogram"]),
    ("Gram+ diplococci",     ["diplococc", "gram-positive", "gram positive"]),
]

TEST_CASES = [
    ("CML-BC (with Ph+/BCR-ABL1)", CML_VIGNETTE, CML_EXPECTED),
    ("Pneumonia (Gram stain)", PNEUMONIA_VIGNETTE, PNEUMONIA_EXPECTED),
]


def call_llm(system_prompt: str, payload: dict, max_retries: int = 3):
    import requests
    for attempt in range(max_retries):
        try:
            resp = requests.post(OPENROUTER_URL, json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, indent=2)},
                ],
                "temperature": 0.3,
                "max_tokens": 4000,
            }, headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            }, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
            json_match = re.search(r"\{.*\}", content, re.S)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            print(f"    LLM attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return None


def check_extraction(
    evidence_items: list[dict],
    expected: list[tuple[str, list[str]]],
) -> tuple[list[str], list[str]]:
    """Return (found_labels, missing_labels)."""
    all_content = "\n".join(
        item.get("content", "") for item in evidence_items
    ).lower()

    found, missing = [], []
    for label, keywords in expected:
        hit = any(kw.lower() in all_content for kw in keywords)
        if hit:
            found.append(label)
        else:
            missing.append(label)
    return found, missing


def main():
    from agentclinic_tree_dx.prompting import load_module_prompt

    if not OPENROUTER_KEY:
        print("ERROR: OPENROUTER_API_KEY2 not set")
        sys.exit(1)

    system_prompt = load_module_prompt("VignetteParser")

    print("=" * 75)
    print("VIGNETTE PARSER EVIDENCE EXTRACTION COMPLETENESS TEST")
    print("=" * 75)
    print(f"  Model: {MODEL}")
    print(f"  Test cases: {len(TEST_CASES)}")
    print()

    total_expected = 0
    total_found = 0
    total_missing = 0
    all_results = []

    for case_name, vignette, expected in TEST_CASES:
        print(f"{'─' * 75}")
        print(f"  Case: {case_name}")
        print(f"  Expected evidence items: {len(expected)}")
        print(f"{'─' * 75}")

        payload = {"raw_case": vignette}
        print("  Calling VignetteParser LLM...")
        t0 = time.time()
        result = call_llm(system_prompt, payload)
        elapsed = time.time() - t0
        print(f"  LLM response: {elapsed:.1f}s")

        if not result:
            print("  ✗ LLM call failed — no result")
            all_results.append((case_name, 0, len(expected), expected))
            total_expected += len(expected)
            total_missing += len(expected)
            continue

        evidence_items = result.get("evidence_items", result.get("evidence", []))
        print(f"  Extracted {len(evidence_items)} evidence items")

        # Print all extracted items
        for i, item in enumerate(evidence_items):
            content = item.get("content", item.get("fact", item.get("text", "?")))
            kind = item.get("kind", "?")
            eid = item.get("id", f"E{i+1}")
            print(f"    {eid} [{kind}]: {content}")

        # Check completeness
        found, missing = check_extraction(evidence_items, expected)

        print(f"\n  Coverage: {len(found)}/{len(expected)} "
              f"({100*len(found)/len(expected):.0f}%)")

        if missing:
            print(f"\n  ✗ MISSING ({len(missing)}):")
            for m in missing:
                kws = [kw for label, kws_list in expected for kw in kws_list if label == m]
                print(f"    - {m}  (searched: {kws})")
        else:
            print(f"\n  ✓ ALL EXPECTED EVIDENCE FOUND")

        # Check structural completeness
        vignette_text = result.get("vignette", "")
        question = result.get("question", result.get("question_stem", ""))
        options = result.get("options", [])

        structural_issues = []
        if not vignette_text:
            structural_issues.append("missing 'vignette' field")
        if not question:
            structural_issues.append("missing 'question' field")
        if not options:
            structural_issues.append("missing 'options' field")
        elif len(options) < 2:
            structural_issues.append(f"only {len(options)} options (expected ≥2)")

        if structural_issues:
            print(f"\n  ⚠ Structural issues: {structural_issues}")
        else:
            print(f"  ✓ Structure OK (vignette={len(vignette_text)}ch, "
                  f"question={len(question)}ch, options={len(options)})")

        total_expected += len(expected)
        total_found += len(found)
        total_missing += len(missing)
        all_results.append((case_name, len(found), len(expected), missing))
        print()

    # ── Summary ───────────────────────────────────────────────────────────
    print("=" * 75)
    print("SUMMARY")
    print("=" * 75)

    all_pass = True
    for case_name, found_n, total_n, missing in all_results:
        pct = 100 * found_n / total_n if total_n else 0
        status = "PASS" if not missing else "FAIL"
        if missing:
            all_pass = False
        print(f"  [{status}] {case_name}: {found_n}/{total_n} ({pct:.0f}%)")
        if missing:
            for m in missing:
                print(f"         ✗ missing: {m}")

    print(f"\n  Overall: {total_found}/{total_expected} "
          f"({100*total_found/total_expected:.0f}%)")
    print(f"  Verdict: {'✓ ALL PASS' if all_pass else '✗ FAILURES DETECTED'}")
    print("=" * 75)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
