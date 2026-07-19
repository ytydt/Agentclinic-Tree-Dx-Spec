"""Test: Does the LLM actually use multi-hop chain hints when injected into TALP payload?

Three conditions (A/B/C) are tested on the same CML case #68 scenario:
  A) Baseline:   no discriminator_hints
  B) 1-hop only: standard pairwise feature differences (current system output)
  C) 2-hop chain: 1-hop hints + indirect reasoning chains with intermediate concepts

We measure whether the LLM generates candidates that reference the intermediate
phenotype (leukostasis) or investigate indirect associations.
"""

import json
import os
import re
import types
from pathlib import Path
from time import sleep

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── API Configuration ────────────────────────────────────────────────────────

OPENROUTER_KEY = os.environ.get(
    "OPENROUTER_API_KEY2",
    "",
)
MODEL = "qwen/qwen3-32b"
PROVIDER = {"order": ["alibaba", "chutes"], "allow_fallbacks": False}
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_USE_PROXY = os.environ.get("TREE_DX_USE_PROXY", "1").lower() not in ("0", "false")
_PROXY_URL = f"http://127.0.0.1:7890"
_PROXIES = {"https": _PROXY_URL, "http": _PROXY_URL} if _USE_PROXY else {}

_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
if _PROXIES:
    _session.proxies.update(_PROXIES)

# ── Load TALP prompt ─────────────────────────────────────────────────────────

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "src" / "agentclinic_tree_dx" / "prompts"
PROMPT = (PROMPTS_DIR / "temporary_analytic_leaf_planner.txt").read_text(encoding="utf-8").strip()


def call_llm(system_prompt: str, payload: dict, max_retries: int = 5) -> dict:
    user_content = json.dumps(payload, default=str, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Module: TemporaryAnalyticLeafPlanner\n"
                "Return strict JSON only, no markdown.\n"
                f"Payload:\n{user_content}"
            ),
        },
    ]

    for attempt in range(1, max_retries + 1):
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "HTTP-Referer": "google.com",
                "X-Title": "google.com",
                "Content-Type": "application/json",
            }
            resp = _session.post(
                OPENROUTER_URL,
                headers=headers,
                json={
                    "model": MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "provider": PROVIDER,
                    "max_tokens": 8000,
                },
                timeout=180,
            )
            resp_json = resp.json()

            if "error" in resp_json:
                print(f"  [API] Attempt {attempt}: {resp_json['error']}")
                sleep(5)
                continue

            raw_text = resp_json["choices"][0]["message"]["content"]
            raw_stripped = raw_text.strip()
            if raw_stripped.startswith("```"):
                raw_stripped = "\n".join(
                    line for line in raw_stripped.splitlines()
                    if not line.strip().startswith("```")
                ).strip()

            # Try parsing JSON
            try:
                return json.loads(raw_stripped)
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", raw_stripped, re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group())
                    except json.JSONDecodeError:
                        pass
                print(f"  [Parse] Attempt {attempt}: JSON parse failed. Raw[:200]: {raw_stripped[:200]}")
                sleep(3)
                continue
        except Exception as exc:
            print(f"  [Error] Attempt {attempt}: {exc}")
            sleep(5)
            continue

    print("  [FATAL] All attempts exhausted.")
    return {}


# ── Simulated CML Case #68 state ─────────────────────────────────────────────

BASE_PAYLOAD = {
    "case_id": "case_68_cml_test",
    "timestep": 2,
    "static_vignette": (
        "A 52-year-old male presents with progressive fatigue over 3 weeks, "
        "unintentional weight loss of 8 kg over 2 months, and bilateral visual "
        "acuity loss over the past 5 days. On exam: massive splenomegaly (8 cm "
        "below costal margin), scattered petechiae. Labs: WBC 285,000/μL with "
        "35% blasts, basophilia (12%), Hgb 7.2, platelets 45,000. Peripheral "
        "smear shows left-shifted granulocytes at all stages of maturation. "
        "Fundoscopy reveals bilateral retinal hemorrhages with cotton-wool spots."
    ),
    "static_question": "What is the most likely diagnosis?",
    "static_options": [
        "A. Acute myeloid leukemia (AML)",
        "B. Chronic myeloid leukemia in blast crisis (CML-BC)",
        "C. Acute lymphoblastic leukemia (ALL)",
        "D. Myelodysplastic syndrome (MDS)",
    ],
    "branches": {
        "B1": {
            "id": "B1",
            "label": "Acute Myeloid Leukemia (AML)",
            "status": "live",
            "prior": 0.35,
            "posterior": 0.42,
            "danger": 0.9,
            "level": 1,
            "parent": "root",
            "evidence_for": [
                "35% blasts support AML diagnosis",
            ],
            "evidence_against": [],
        },
        "B2": {
            "id": "B2",
            "label": "Chronic Myeloid Leukemia - Blast Crisis (CML-BC)",
            "status": "live",
            "prior": 0.30,
            "posterior": 0.33,
            "danger": 0.85,
            "level": 1,
            "parent": "root",
            "evidence_for": [
                "Massive splenomegaly and basophilia suggest chronic myeloproliferative process",
            ],
            "evidence_against": [],
        },
        "B3": {
            "id": "B3",
            "label": "Acute Lymphoblastic Leukemia (ALL)",
            "status": "live",
            "prior": 0.15,
            "posterior": 0.12,
            "danger": 0.85,
            "level": 1,
            "parent": "root",
            "evidence_for": [],
            "evidence_against": [
                "Left-shifted granulocytes at all stages argue against ALL",
            ],
        },
        "B4": {
            "id": "B4",
            "label": "Myelodysplastic Syndrome (MDS)",
            "status": "live",
            "prior": 0.10,
            "posterior": 0.08,
            "danger": 0.5,
            "level": 1,
            "parent": "root",
            "evidence_for": [],
            "evidence_against": [
                "WBC 285k with 35% blasts is atypical for MDS",
            ],
        },
    },
    "frontier": ["B1", "B2", "B3", "B4"],
    "actions_taken": [
        {
            "content": "Analyze whether 35% blasts and WBC 285k support AML vs CML-BC",
            "result_summary": "35% blasts are consistent with both AML and CML blast crisis. "
            "However, basophilia 12% and left-shifted granulocytes at all maturation "
            "stages are more characteristic of CML.",
        },
    ],
    "differential_history": [
        {"B1": 0.35, "B2": 0.30, "B3": 0.15, "B4": 0.10},
        {"B1": 0.42, "B2": 0.33, "B3": 0.12, "B4": 0.08},
    ],
}

HINTS_1HOP = """[Knowledge Layer: coverage=75%, source=HPO+PrimeKG]

Acute Myeloid Leukemia (AML) vs Chronic Myeloid Leukemia - Blast Crisis (CML-BC):
  Favours AML only: gum hypertrophy (LR+ 5.2), disseminated intravascular coagulation (LR+ 3.8), Auer rods (LR+ ∞)
  Favours CML-BC only: basophilia (LR+ 4.1), massive splenomegaly (LR+ 3.5), chronic fatigue (LR+ 2.8), night sweats (LR+ 2.1)
  Present in patient → favours CML-BC: basophilia 12%, massive splenomegaly, progressive fatigue over weeks

NOT typically seen in AML: chronic fatigue over months, massive splenomegaly (>6cm below costal margin)
NOT typically seen in CML-BC: Auer rods, gum hypertrophy, DIC

Related diagnoses for CML-BC: chronic myelogenous leukemia BCR-ABL1 positive, atypical CML"""

HINTS_2HOP_CHAIN = HINTS_1HOP + """

[Indirect reasoning chains (PrimeKG 2-hop):]

Chain 1: bilateral visual acuity loss → (phenotype_phenotype) → leukostasis retinopathy
  → (disease_phenotype) → CML blast crisis
  Intermediate sensitivity: leukostasis occurs in ~17% of CML-BC (HPO: Occasional)
  but in <5% of de novo AML
  Clinical note: leukostasis is caused by extreme leukocytosis (WBC >100k) with
  blast predominance; retinal hemorrhages + cotton-wool spots on fundoscopy are
  classic manifestations of leukostasis syndrome.
  ★ Suggestion: Analyze whether the bilateral visual loss + fundoscopy findings
    (retinal hemorrhages, cotton-wool spots) constitute a leukostasis syndrome,
    which would strongly favor CML-BC over de novo AML.

Chain 2: progressive fatigue (3 weeks) + weight loss (2 months) → (temporal_pattern)
  → chronic myeloproliferative phase → (disease_phenotype) → CML blast crisis
  Intermediate sensitivity: chronic myeloproliferative phase is Obligate (100%) for CML
  Clinical note: CML-BC is always preceded by a chronic phase; the 2-month weight
  loss timeline suggests a pre-existing chronic process now accelerating. De novo
  AML typically presents acutely (days to 1-2 weeks).
  ★ Suggestion: Analyze whether the temporal dissociation between the chronic
    symptoms (months) and acute symptoms (days-weeks) argues for a biphasic
    disease (chronic → blast crisis) rather than de novo acute leukemia.

When indirect_reasoning_chains are present, generate candidates that investigate
the INTERMEDIATE phenotype to confirm or rule out the indirect association."""


def build_payload(condition: str) -> dict:
    payload = json.loads(json.dumps(BASE_PAYLOAD))
    if condition == "B":
        payload["discriminator_hints"] = HINTS_1HOP
    elif condition == "C":
        payload["discriminator_hints"] = HINTS_2HOP_CHAIN
    return payload


# ── Analysis ──────────────────────────────────────────────────────────────────

CHAIN_KEYWORDS = {
    "leukostasis",
    "cotton-wool",
    "cotton wool",
    "fundoscop",
    "hyperviscosity",
    "hyperleukocytosis",
}

INTERMEDIATE_CONCEPTS = {
    "leukostasis",
    "hyperleukocytosis",
}

CHRONICITY_KEYWORDS = {
    "subacute",
    "chronic process",
    "chronic underlying",
    "chronic phase",
    "biphasic",
    "temporal dissociation",
    "chronic myeloproliferative",
    "chronic myeloproliferation",
    "preceded by",
    "accelerating",
}

VISUAL_KEYWORDS = {
    "visual loss",
    "visual acuity",
    "retinal hemorrhage",
    "retinal haemorrhage",
    "cotton-wool",
    "cotton wool",
    "fundoscop",
}


def analyze_response(result: dict, condition: str) -> dict:
    candidates = result.get("candidate_leaves_ranked", [])
    analysis = {
        "condition": condition,
        "num_candidates": len(candidates),
        "chain_references": 0,
        "intermediate_references": 0,
        "chronicity_references": 0,
        "visual_chain_references": 0,
        "candidates_detail": [],
        "cml_bc_support_candidates": 0,
    }

    for i, c in enumerate(candidates):
        content_full = (c.get("content", "") + " " + c.get("why", "")).lower()
        detail = {
            "idx": i,
            "branch": c.get("branch_id", "?"),
            "func": c.get("primary_function", "?"),
            "content_preview": c.get("content", "")[:150],
            "hits_chain": False,
            "hits_intermediate": False,
            "hits_chronicity": False,
            "hits_visual": False,
        }

        if any(kw in content_full for kw in CHAIN_KEYWORDS):
            analysis["chain_references"] += 1
            detail["hits_chain"] = True

        if any(kw in content_full for kw in INTERMEDIATE_CONCEPTS):
            analysis["intermediate_references"] += 1
            detail["hits_intermediate"] = True

        if any(kw in content_full for kw in CHRONICITY_KEYWORDS):
            analysis["chronicity_references"] += 1
            detail["hits_chronicity"] = True

        if any(kw in content_full for kw in VISUAL_KEYWORDS):
            analysis["visual_chain_references"] += 1
            detail["hits_visual"] = True

        tb = c.get("target_branches", {})
        if tb.get("B2") == "support" or (
            c.get("branch_id") == "B2" and c.get("primary_function") == "confirm"
        ):
            analysis["cml_bc_support_candidates"] += 1

        analysis["candidates_detail"].append(detail)

    return analysis


def run_test(n_runs: int = 3):
    conditions = ["A", "B", "C"]
    all_runs = {cond: [] for cond in conditions}
    all_raw = {cond: [] for cond in conditions}

    for run_idx in range(1, n_runs + 1):
        print(f"\n\n{'#'*70}")
        print(f"  RUN {run_idx}/{n_runs}")
        print(f"{'#'*70}")

        for cond in conditions:
            label = {"A": "Baseline (no hints)", "B": "1-hop hints", "C": "2-hop chain hints"}[cond]
            print(f"\n{'='*70}")
            print(f"  [{run_idx}] Condition {cond}: {label}")
            print(f"{'='*70}")

            payload = build_payload(cond)
            raw_result = call_llm(PROMPT, payload)
            all_raw[cond].append(raw_result)
            analysis = analyze_response(raw_result, cond)
            all_runs[cond].append(analysis)

            print(f"\n  Candidates generated: {analysis['num_candidates']}")
            print(f"  Chain keyword refs: {analysis['chain_references']}")
            print(f"  Intermediate (leukostasis) refs: {analysis['intermediate_references']}")
            print(f"  Chronicity refs: {analysis['chronicity_references']}")
            print(f"  Visual chain refs: {analysis['visual_chain_references']}")
            print(f"  CML-BC support candidates: {analysis['cml_bc_support_candidates']}")
            print(f"\n  Candidate details:")
            for d in analysis["candidates_detail"]:
                flags = []
                if d["hits_chain"]:
                    flags.append("CHAIN")
                if d["hits_intermediate"]:
                    flags.append("INTERMEDIATE")
                if d["hits_chronicity"]:
                    flags.append("CHRONICITY")
                if d["hits_visual"]:
                    flags.append("VISUAL")
                flag_str = f" [{','.join(flags)}]" if flags else ""
                print(f"    [{d['idx']}] {d['branch']}/{d['func']}{flag_str}")
                print(f"        {d['content_preview']}")

    # ── Aggregate across runs ─────────────────────────────────────────────────

    def avg(runs, key):
        return sum(r[key] for r in runs) / len(runs)

    print(f"\n\n{'='*70}")
    print(f"  AGGREGATE SUMMARY ({n_runs} runs per condition)")
    print(f"{'='*70}")
    header = f"  {'Metric':<45} {'A':>7} {'B':>7} {'C':>7} {'C-B':>6}"
    print(header)
    print("  " + "-" * 72)
    metrics = [
        ("Total candidates (avg)", "num_candidates"),
        ("Chain keyword refs (avg)", "chain_references"),
        ("Intermediate concept (avg)", "intermediate_references"),
        ("Chronicity refs (avg)", "chronicity_references"),
        ("Visual chain refs (avg)", "visual_chain_references"),
        ("CML-BC support (avg)", "cml_bc_support_candidates"),
    ]
    for label, key in metrics:
        a = avg(all_runs["A"], key)
        b = avg(all_runs["B"], key)
        c = avg(all_runs["C"], key)
        delta = c - b
        marker = " ★" if delta > 0.1 else ""
        print(f"  {label:<45} {a:>7.1f} {b:>7.1f} {c:>7.1f} {delta:>+6.1f}{marker}")

    # Per-run detail
    print(f"\n  Per-run intermediate concept (leukostasis) counts:")
    for cond in conditions:
        counts = [r["intermediate_references"] for r in all_runs[cond]]
        print(f"    {cond}: {counts}  (hit rate: {sum(1 for c in counts if c > 0)}/{n_runs})")

    print(f"\n  Per-run chain keyword counts:")
    for cond in conditions:
        counts = [r["chain_references"] for r in all_runs[cond]]
        print(f"    {cond}: {counts}  (hit rate: {sum(1 for c in counts if c > 0)}/{n_runs})")

    # ── Verdict ───────────────────────────────────────────────────────────────

    c_inter_avg = avg(all_runs["C"], "intermediate_references")
    b_inter_avg = avg(all_runs["B"], "intermediate_references")
    a_inter_avg = avg(all_runs["A"], "intermediate_references")
    c_chain_avg = avg(all_runs["C"], "chain_references")
    b_chain_avg = avg(all_runs["B"], "chain_references")

    c_inter_hit = sum(1 for r in all_runs["C"] if r["intermediate_references"] > 0)
    b_inter_hit = sum(1 for r in all_runs["B"] if r["intermediate_references"] > 0)

    print(f"\n{'='*70}")
    print("  VERDICT")
    print(f"{'='*70}")

    if c_inter_avg > b_inter_avg and c_inter_hit >= 2:
        print("  ✅ 2-hop chain injection WORKS (robust across runs):")
        print(f"     Intermediate concept hit rate: C={c_inter_hit}/{n_runs} vs B={b_inter_hit}/{n_runs}")
        print(f"     Avg intermediate refs: A={a_inter_avg:.1f}, B={b_inter_avg:.1f}, C={c_inter_avg:.1f}")
        feasibility = "FEASIBLE"
    elif c_inter_avg > 0 and c_chain_avg > b_chain_avg:
        print("  △ PARTIAL SUCCESS: 2-hop chain hints improve chain-following,")
        print("     but not consistently across all runs.")
        print(f"     Intermediate hit rate: C={c_inter_hit}/{n_runs}")
        print(f"     Avg chain refs: B={b_chain_avg:.1f}, C={c_chain_avg:.1f}")
        feasibility = "PARTIAL"
    elif c_chain_avg > b_chain_avg:
        print("  △ WEAK: Chain keywords increase but intermediate concept not used.")
        feasibility = "WEAK"
    else:
        print("  ❌ NO clear effect from 2-hop chain injection.")
        feasibility = "FAILED"

    c_chron_avg = avg(all_runs["C"], "chronicity_references")
    b_chron_avg = avg(all_runs["B"], "chronicity_references")
    if c_chron_avg > b_chron_avg:
        print(f"\n  Chronicity reasoning uplift: B={b_chron_avg:.1f} → C={c_chron_avg:.1f}")

    out_path = Path(__file__).parent / "multihop_test_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "n_runs": n_runs,
                "raw_results": all_raw,
                "analyses": {k: v for k, v in all_runs.items()},
                "feasibility": feasibility,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n  Full results saved to: {out_path}")

    return all_runs, feasibility


if __name__ == "__main__":
    run_test()
