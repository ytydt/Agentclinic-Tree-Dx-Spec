#!/usr/bin/env python3
"""Root-agent manual E8 ledger, veto and trajectory adjudication."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import ROOT, file_sha256  # noqa: E402
from analysis.mechanism_v2.e8_temporal_veto import HARD, INVALID, LEGAL, SOFT  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E8_temporal_veto"

# Every row was reviewed against the clean vignette, extraction quote, all
# structured fields and four selector outputs.  ``ledger_a_fidelity`` concerns
# only the unperturbed builder output.  ``invalid_time_meaning_change`` concerns
# the deliberate ledger-B rotation and is never folded into builder fidelity.
MANUAL: dict[str, dict[str, Any]] = {
    "DA_d2_heldout100/349": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "not_applicable",
        "issues": [], "primary_mechanism": "false_hard_veto_with_soft_schema_failure",
        "reason": "Absence of fever and internal-organ involvement does not exclude primary/localized cutaneous histoplasmosis. Hard veto removes exposed gold; soft response is invalid, so rescue is unobservable.",
    },
    "DA_d2_heldout100/330": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "not_applicable",
        "issues": [], "primary_mechanism": "legal_order_instability_under_pool_miss",
        "reason": "The negatives preserve the source. Gold is absent from the strict pool; a row-order-only change swaps wrong conduction labels and cannot establish clinical benefit.",
    },
    "DA_d2_heldout100/368": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "not_applicable",
        "issues": [], "primary_mechanism": "legal_order_instability_under_pool_miss",
        "reason": "Negation kinds preserve the denied family history and absent atypical cells. Order changes the wrong subtype champion while the complete ichthyosiform reference is unexposed.",
    },
    "DA_d2_heldout100/374": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "stable_wrong_under_invalid_time",
        "reason": "Rotating prior-history and arrival anchors changes event meaning, yet all variants remain on atrial tachycardia; the fixed pool lacks the complete atypical AVNRT reference.",
    },
    "DA_d2_heldout200b/486": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "false_hard_veto_plus_order_instability",
        "reason": "Absent nerve thickening/anhidrosis do not override storiform histology and abundant acid-fast bacilli. Soft removes the false veto but only legal row order selects histoid leprosy.",
    },
    "DA_d2_heldout200b/523": {
        "ledger_a_fidelity": "minor_error", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": ["N1 keeps only the transfusion clause from a compound risk-history negative"],
        "primary_mechanism": "invalid_time_flip_under_pool_miss",
        "reason": "HCV seroconversion and high viral load identify the composite reference, but it is absent from the pool. Rotating the before-1990 anchor changes meaning and flips two incomplete candidates.",
    },
    "DA_d2_heldout200b/530": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "legal_order_instability_under_pool_miss",
        "reason": "The complete calcinosis-in-Sjögren object is not exposed. Mere legal order swaps Sjögren and limited systemic sclerosis; the time rotation additionally moves the current-treatment anchor.",
    },
    "DA_d2_seq100/243": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "not_applicable",
        "issues": [], "primary_mechanism": "stable_pool_miss",
        "reason": "Serum-negative PVB19 is faithfully distinguished from biopsy-positive PVB19, but the complete JSE-associated-with-PVB19 object is absent and all reviewed outputs remain incomplete/wrong.",
    },
    "DA_d2_seq100/57": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "invalid_time_flip_under_pool_miss",
        "reason": "Negation kinds correctly encode no scale/nonresponse. Rotating rash-onset and recent-treatment anchors changes meaning but only swaps two wrong drug/immunotherapy labels because EAE is unexposed.",
    },
    "DA_d2_seq100/87": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "false_hard_veto_rescue",
        "reason": "Absence of a rub is not required for myopericarditis. Hard veto removes the gold; soft retains it and selects it. Normal coronaries remain valid hard evidence against obstructive MI/ACS.",
    },
    "DA_d2_seq100/95": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "invalid_time_flip_under_pool_miss",
        "reason": "The source ledger is faithful. Moving the eight-month throat-spasm episode to genetic testing is clinically invalid and changes the wrong champion; PAPT itself is absent from the pool.",
    },
    "MCR_seq200b/283": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "not_applicable",
        "issues": [], "primary_mechanism": "legal_order_induced_harm",
        "reason": "Imaging directly supports dermoid cyst and the base soft arm is correct. A row-order-only replay changes to orbital lymphangioma, demonstrating nonsemantic selector instability.",
    },
    "MCR_seq200b/288": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "order_and_time_instability_under_pool_miss",
        "reason": "The pancreatic cyst negatives are faithful, but cystic lymphangioma is not exposed and is not uniquely identified without pathology. Legal order and rotated episodes swap other cystic neoplasms.",
    },
    "MCR_seq200b/290": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "stable_wrong_despite_invalid_time",
        "reason": "The unperturbed events correctly distinguish first visit, severe home attack and repeat MRI. Rotation corrupts those episodes, but all soft variants still miss unexposed FND.",
    },
    "MCR_seq200b/336": {
        "ledger_a_fidelity": "major_error", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "changed",
        "issues": ["N3-N5 infer normality from bare numeric values despite the vignette-only contract", "episode labels are partly inferred"],
        "primary_mechanism": "false_hard_veto_rescue_with_builder_noise",
        "reason": "Denial of systemic symptoms does not exclude subacute thyroiditis. Soft rescues gold, whereas wrong time rotation reverses that gain. The ledger also contains unsupported normal-value inferences.",
    },
    "MCR_seq200b/345": {
        "ledger_a_fidelity": "major_error", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "changed",
        "issues": ["N6 turns absence of a metabolic evaluation into a patient negative", "N1 collapses personal and family scope"],
        "primary_mechanism": "false_hard_veto_rescue_with_order_harm",
        "reason": "The FGF23-independent biochemical pattern supports HHRH despite tension with normal urine calcium. Hard absolute veto is excessive; soft is correct, but legal row order alone loses the gain.",
    },
    "MCR_seq200b/352": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "absent",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "invalid_time_flip_under_unidentifiable_reference",
        "reason": "No pathology identifies mucoepidermoid carcinoma, and the reference is absent from the pool. The exam-negative nodes coexist with CT-positive cervical nodes; rotating time only swaps wrong tumor labels.",
    },
    "MCR_seq200b/374": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "soft_comparative_rescue_without_gold_veto",
        "reason": "Serial antibiotic/anti-TB nonresponse and negative cultures directly support organizing pneumonia. Soft selects gold over lung cancer without a gold-veto transition; this is broader comparative prompting, not isolated veto rescue.",
    },
    "MCR_seq200b/377": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "invalid_time_flip_under_pool_miss",
        "reason": "The source negatives are faithful, but hemorrhagic synovial cyst is unexposed and not uniquely fixed by the supplied imaging. Rotated episodes change the wrong meningioma/schwannoma champion.",
    },
    "MCR_seq200b/470": {
        "ledger_a_fidelity": "major_error", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": ["N6 assigns the father's intraocular pressure to patient scope", "N5 compresses a father-specific statement into family scope"],
        "primary_mechanism": "soft_prompt_harm_with_order_time_rescue",
        "reason": "Hard is correct; base soft switches to Stargardt, while legal order and invalid time switch back. This pattern and father/proband scope collision reject a clean time-veto explanation.",
    },
    "MCR_seq200b/480": {
        "ledger_a_fidelity": "major_error", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "changed",
        "issues": ["The six-event cap omits the decisive negative fatigue and neostigmine tests while retaining broad normal panels"],
        "primary_mechanism": "false_hard_veto_without_rescue",
        "reason": "Early absence of diplopia/dysphagia/weakness does not absolutely exclude bulbar MG. Soft removes that overreach but remains anchored on TIA; vignette support for gold is itself incomplete after negative tests.",
    },
    "MCR_v1_seq100/11": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "order_and_time_instability_under_pool_miss",
        "reason": "The original episode anchors are faithful. Legal order and invalid-time variants alternate MIS and antiphospholipid syndrome, while the complete benchmark object is not strictly exposed.",
    },
    "MCR_v1_seq100/28": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "false_hard_veto_without_rescue",
        "reason": "Current afebrile status cannot erase the documented prior month of fever or exclude TEN. Yet soft still favors DRESS; the vignette itself leaves clinically material TEN-versus-DRESS ambiguity.",
    },
    "MCR_v1_seq100/6": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "absent",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "order_and_time_instability_under_unidentifiable_reference",
        "reason": "The source ledger preserves postoperative timing, but the species Exophiala xenobiotica cannot be identified without culture data. Legal order/time rotation only moves broad fungal labels.",
    },
    "MCR_v1_seq100/68": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "not_applicable",
        "issues": [], "primary_mechanism": "stable_pool_identity_miss",
        "reason": "Events are faithful and outputs are stable, but the pool/strict bridge exposes lipofibromatous hamartoma rather than the benchmark macrodystrophia lipomatosa object.",
    },
    "MCR_v2_seq100/173": {
        "ledger_a_fidelity": "major_error", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "invalid_construction", "invalid_time_meaning_change": "not_applicable",
        "issues": ["N6 fabricates 'no other abnormalities' from a CT explicitly showing a 15-mm subdural collection and 13-mm midline shift"],
        "primary_mechanism": "construction_induced_false_veto",
        "reason": "A relationship-reversing extraction error creates a false normal-CT event and hard vetoes the exposed gold. This is builder failure, not evidence that hard or soft veto policy is intrinsically superior.",
    },
    "MCR_v2_seq100/174": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "overreach", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "false_hard_veto_rescue",
        "reason": "Negative antibodies and nearly normal endoscopy do not negate corpus histology and reduced H+/K+-ATPase. Soft correctly retains autoimmune gastritis and rescues top-1.",
    },
    "MCR_v2_seq100/178": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "legal_order_induced_harm",
        "reason": "Volitional behavior supports malingering but factitious disorder remains a close intent-based alternative. Base soft is correct; legal row order alone changes to factitious disorder.",
    },
    "MCR_v2_seq100/220": {
        "ledger_a_fidelity": "faithful", "reference_identifiability": "partial",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": [], "primary_mechanism": "soft_prompt_harm_on_ambiguous_reference",
        "reason": "Hard selects Kawasaki, whereas every soft variant selects MIS-C. Classic Kawasaki signs coexist with age/GI/COVID-context evidence for MIS-C, so this cannot validate hard veto policy.",
    },
    "MCR_v2_seq100/242": {
        "ledger_a_fidelity": "major_error", "reference_identifiability": "direct",
        "reference_hard_veto_validity": "not_applicable", "invalid_time_meaning_change": "changed",
        "issues": ["N1-N3 assign maternal history to patient rather than maternal scope", "N5 similarly obscures whose workup was normal"],
        "primary_mechanism": "scope_collision_and_invalid_time_flip_under_pool_miss",
        "reason": "Fetal imaging identifies intraventricular hemorrhage, but the gold is absent. Maternal/fetal scope loss and time rotation make the resulting wrong-candidate flip uninterpretable as temporal reasoning.",
    },
}


def run(out: Path) -> dict[str, Any]:
    prereg = json.loads((out / "external_audit_preregistration.json").read_text(encoding="utf-8"))
    proxy_expected = list(prereg["case_keys"])
    manual_only = ["DA_d2_heldout100/349"]
    expected = sorted([*proxy_expected, *manual_only])
    if set(expected) != set(MANUAL) or len(expected) != len(MANUAL):
        raise AssertionError("manual audit cases do not match frozen proxy + all-hard-veto selection")
    construction = {row["case_key"]: row for row in read_jsonl(out / "construction/case_results.jsonl")}
    arms = {
        arm: {row["case_key"]: row for row in read_jsonl(out / "arms" / arm / "case_results.jsonl")}
        for arm in (HARD, SOFT, LEGAL, INVALID)
    }
    proxy = {row["case_key"]: row for row in read_jsonl(out / "external_audit/case_results.jsonl")}
    rows: list[dict[str, Any]] = []
    for key in expected:
        manual = dict(MANUAL[key])
        proxy_row = proxy.get(key) or {}
        proxy_response = dict(proxy_row.get("response") or {})
        selection_reasons = (
            prereg["selection_reasons"][key]
            if key in prereg["selection_reasons"]
            else ["reference_hard_veto_soft_schema_failure"]
        )
        row = {
            "case_key": key, "family": arms[SOFT][key]["family"],
            "selection_reasons": selection_reasons,
            "gold": arms[SOFT][key]["gold"], "gold_exposed": arms[SOFT][key]["gold_exposed"],
            "negative_events": construction[key]["negative_events"],
            "champions": {arm: arms[arm][key]["champion_label"] if arms[arm][key]["success"] else None
                          for arm in (HARD, SOFT, LEGAL, INVALID)},
            "gold_top1": {arm: bool(arms[arm][key]["gold_top1"]) if arms[arm][key]["success"] else None
                          for arm in (HARD, SOFT, LEGAL, INVALID)},
            "proxy_sampled": key in proxy,
            "proxy_served": bool(proxy_row.get("success")),
            "proxy_ledger_a_fidelity": proxy_response.get("ledger_overall"),
            "proxy_reference_identifiability": proxy_response.get("reference_identifiability"),
            "proxy_reference_hard_veto_validity": proxy_response.get("reference_hard_veto_validity"),
            "proxy_invalid_time_meaning_change": proxy_response.get("ledger_b_meaning_change"),
            **manual,
        }
        row["proxy_disagreements"] = [
            field for field in (
                "ledger_a_fidelity", "reference_identifiability",
                "reference_hard_veto_validity", "invalid_time_meaning_change",
            )
            if row.get(f"proxy_{field}") is not None and row.get(f"proxy_{field}") != row[field]
        ]
        rows.append(row)
    write_jsonl(out / "manual_audit.jsonl", rows)
    summary = {
        "schema": "E8_root_manual_audit_v1",
        "manual_case_n": len(rows),
        "selection_reason_counts": dict(Counter(reason for row in rows for reason in row["selection_reasons"])),
        "ledger_a_fidelity": dict(Counter(row["ledger_a_fidelity"] for row in rows)),
        "reference_identifiability": dict(Counter(row["reference_identifiability"] for row in rows)),
        "reference_hard_veto_validity": dict(Counter(row["reference_hard_veto_validity"] for row in rows)),
        "invalid_time_meaning_change": dict(Counter(row["invalid_time_meaning_change"] for row in rows)),
        "primary_mechanisms": dict(Counter(row["primary_mechanism"] for row in rows)),
        "proxy_served_n": sum(row["proxy_served"] for row in rows),
        "proxy_sampled_n": sum(row["proxy_sampled"] for row in rows),
        "proxy_disagreement_case_n": sum(bool(row["proxy_disagreements"]) for row in rows),
        "proxy_disagreement_field_n": sum(len(row["proxy_disagreements"]) for row in rows),
        "proxy_disagreement_fields": dict(Counter(field for row in rows for field in row["proxy_disagreements"])),
        "critical_findings": {
            "reference_hard_veto_cases": sum(
                any(reason.startswith("reference_hard_veto") for reason in row["selection_reasons"])
                for row in rows
            ),
            "reference_hard_veto_overreach": sum(row["reference_hard_veto_validity"] == "overreach" for row in rows),
            "reference_hard_veto_invalid_construction": sum(row["reference_hard_veto_validity"] == "invalid_construction" for row in rows),
            "major_ledger_a_error_cases": sum(row["ledger_a_fidelity"] == "major_error" for row in rows),
            "unidentifiable_reference_cases": sum(row["reference_identifiability"] == "absent" for row in rows),
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(out / "manual_audit_summary.json", summary)
    manifest = {
        "schema": "E8_root_manual_audit_manifest_v1",
        "frozen_selection_sha256": file_sha256(out / "external_audit_preregistration.json"),
        "external_proxy_results_sha256": file_sha256(out / "external_audit/case_results.jsonl"),
        "root_manual_rows_sha256": file_sha256(out / "manual_audit.jsonl"),
        "root_agent_final_responsibility": True,
        "external_proxy_used_as_subcontractor_only": True,
    }
    atomic_json(out / "manual_audit_manifest.json", manifest)
    (out / "manual_audit_run.log").write_text(
        "\n".join([
            f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
            "phase=E8 root-agent ledger/veto/trajectory audit",
            f"manual_cases={len(rows)}", f"proxy_served={summary['proxy_served_n']}",
            f"proxy_disagreement_cases={summary['proxy_disagreement_case_n']}",
        ]) + "\n", encoding="utf-8",
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv); summary = run(args.out.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
