#!/usr/bin/env python3
"""Root-owned clinical adjudication of the frozen E14x audit queue.

No external model produced these labels.  Each judgment was made after reading
the clean vignette, reference, both historical champions/rationales, A1 output,
frontier trace when present, and DA mapper transition.  Because the historical
upstream calls differ, ``gate_utility`` describes the observed trajectory and
must not be read as an identified causal effect of A1.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import ROOT, file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


OUT = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"


def _j(
    lite: str,
    adaptive: str,
    a1: str,
    locus: str,
    utility: str,
    direction: str,
    note: str,
) -> dict[str, str]:
    return {
        "clinical_lite_equivalence": lite,
        "clinical_adaptive_equivalence": adaptive,
        "a1_information_role": a1,
        "conversion_locus": locus,
        "observed_gate_utility": utility,
        "clinical_direction": direction,
        "root_note": note,
    }


# ``yes`` means a clinically adequate complete answer, including an ordinary
# spelling synonym. ``partial_or_scope`` means that the champion captures the
# disease family/consequence but omits a material subtype, cause, site, stage,
# or composite component required by the vignette/reference.
MANUAL: dict[str, dict[str, str]] = {
    "DA_d2_seq100/7": _j(
        "no", "no", "merge_only", "projection", "neutral", "both_incorrect",
        "Scleredema and morphea both miss segmental stiff-skin syndrome. A1 only merges already available sclerosing labels; the adaptive mapper's option hit is therefore a projection false positive, not a diagnostic repair.",
    ),
    "DA_d2_seq100/11": _j(
        "partial_or_scope", "partial_or_scope", "new_decisive", "projection", "repair", "projection_only",
        "Both champions stop at lacrimal-sac abscess and omit acute dacryocystitis plus optic-nerve injury. A1 newly states dacryocystitis and the DA projection becomes correct, but the emitted concept remains incomplete.",
    ),
    "DA_d2_seq100/22": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "The amyopathic anti-MDA5 dermatomyositis trajectory is missed. A1 adds adult-onset Still disease, which the selector promotes on ferritin while discounting hallmark cutaneous/ILD evidence; the mapper then spuriously maps this wrong champion to the gold option.",
    ),
    "DA_d2_seq100/27": _j(
        "partial_or_scope", "no", "new_distractor", "selector", "harm", "lite_better",
        "Generic Sweet syndrome is the correct family for histiocytoid Sweet syndrome. A1 introduces leukemia cutis/neutrophilic labels and the adaptive selector switches to leukemia cutis despite the clinicopathologic Sweet pattern, losing the valid family-level answer.",
    ),
    "DA_d2_seq100/39": _j(
        "no", "no", "merge_only", "selector", "neutral", "clinically_equivalent",
        "The vignette supports metastatic cutaneous Crohn disease, but both arms choose granuloma inguinale despite sterile cultures and Crohn serology. A1 contains Crohn disease but does not convert it; its newly counted granuloma label is redundant error reinforcement.",
    ),
    "DA_d2_seq100/45": _j(
        "partial_or_scope", "yes", "new_decisive", "selector", "repair", "adaptive_better",
        "Lite names dermatomyositis but drops the reproducible ipilimumab cause. A1 supplies ipilimumab-induced myositis and adaptive emits ipilimumab-induced dermatitis/myositis, a clinically adequate rendering of drug-induced dermatomyositis despite the surface mismatch.",
    ),
    "DA_d2_seq100/63": _j(
        "no", "no", "not_triggered", "projection", "not_triggered", "both_incorrect",
        "Primary hyperoxaluria and cystinosis both misread freely mobile anterior-chamber cholesterol crystals and ignore the morning-glory/chronic-detachment composite. No A1 ran; the Lite-only option hit is mapper noise.",
    ),
    "DA_d2_seq100/67": _j(
        "no", "partial_or_scope", "new_redundant", "projection", "repair", "adaptive_better",
        "Bradycardia is only a finding. Severe sepsis is substantially closer to septic shock but omits anuric renal failure; A1's hypotension/respiratory-failure concepts add severity context without becoming champion. The option repair is clinically directional but incomplete.",
    ),
    "DA_d2_seq100/99": _j(
        "yes", "partial_or_scope", "not_triggered", "sampling_churn", "not_triggered", "lite_better",
        "Lite exactly identifies epidermolysis bullosa pruriginosa. The non-triggered A5 arm retreats to the broader dystrophic epidermolysis bullosa family even though the pruriginosa phenotype is explicit; this is selector-policy/upstream churn, not Call-4 evidence.",
    ),
    "DA_d2_seq100/100": _j(
        "no", "partial_or_scope", "not_triggered", "projection", "not_triggered", "adaptive_better",
        "Angiosarcoma conflicts with GATA3-positive intravascular breast carcinoma. Adaptive recovers cutaneous breast metastasis but omits the telangiectatic subtype; its option hit is a defensible broad-to-specific projection, with no A1 involved.",
    ),
    "DA_d2_seq100/103": _j(
        "no", "no", "not_triggered", "projection", "not_triggered", "clinically_equivalent",
        "Both runs emit OAVRT, which is incompatible with continuation of atrial tachycardia during adenosine block and misses IART. The champion is unchanged, so the option flip is pure mapper instability.",
    ),
    "DA_d2_seq100/111": _j(
        "partial_or_scope", "no", "new_distractor", "selector", "harm", "lite_better",
        "Lichen planus captures the inverse lichen-planus family; granuloma annulare does not fit the lichenoid interface biopsy. A1 supplies irrelevant alternatives and additional support is merged into granuloma annulare, producing a clear selection harm.",
    ),
    "DA_d2_seq100/132": _j(
        "partial_or_scope", "partial_or_scope", "new_distractor", "selector", "neutral", "clinically_equivalent",
        "Both labels fail to emit the observed trifascicular block progressing to complete block: Lite substitutes a degenerative etiology and adaptive emits a generic conduction-disease umbrella. A1's broad label wins but does not add diagnostic resolution.",
    ),
    "DA_d2_seq100/151": _j(
        "partial_or_scope", "partial_or_scope", "not_triggered", "projection", "not_triggered", "clinically_equivalent",
        "Cardioembolic stroke from atrial fibrillation is compatible with the large-MCA embolic reference but omits its territory/scope. Identical champions receive different option mappings, directly exposing projection instability.",
    ),
    "DA_d2_seq100/158": _j(
        "partial_or_scope", "partial_or_scope", "not_triggered", "projection", "not_triggered", "clinically_equivalent",
        "Pilomatrixoma is the underlying lesion but omits the diagnostically requested bullous variant. The unchanged champion's option flip is mapper-only variation.",
    ),
    "DA_d2_seq100/161": _j(
        "yes", "no", "new_distractor", "selector", "harm", "lite_better",
        "Hemosiderotic fibrolipomatous lesion is an adequate surface form of HFLT and matches the CD34-positive fibrofatty pathology. Adaptive switches to Nora lesion, a distinct bony proliferation, while A1 adds hematoma/pseudotumor distractors.",
    ),
    "DA_d2_seq100/163": _j(
        "no", "partial_or_scope", "new_distractor", "projection", "neutral", "adaptive_better",
        "Adaptive recognizes a myeloproliferative neoplasm with eosinophilia but omits FIP1L1-PDGFRA CEL and the associated GEH; Lite's eosinophilic-granuloma label is less coherent. A1's Langerhans candidate is distracting and the option reversal is not evidence of A1 utility.",
    ),
    "DA_d2_seq100/183": _j(
        "partial_or_scope", "partial_or_scope", "new_distractor", "selector", "neutral", "adaptive_better",
        "Glioma is too broad. IDH-mutant astrocytoma uses the supplied molecular evidence and is more specific, but omits grade IV, optic-nerve invasion, and intraocular extension; A1 improves taxonomy without reaching the reference trajectory.",
    ),
    "DA_d2_seq100/188": _j(
        "no", "no", "not_triggered", "projection", "not_triggered", "both_incorrect",
        "Neither ischemic cardiomyopathy nor ARVC names CAD with the transient giant-R-wave syndrome. The adaptive option hit despite an incorrect ARVC concept is a mapper false positive.",
    ),
    "DA_d2_seq100/194": _j(
        "partial_or_scope", "partial_or_scope", "not_triggered", "projection", "not_triggered", "clinically_equivalent",
        "Lamellar macular hole omits the defining trapped silicone-oil hyperoleon. The same champion and near-identical rationale map differently, so the flip is projection-only.",
    ),
    "DA_d2_seq100/198": _j(
        "partial_or_scope", "no", "not_triggered", "projection", "not_triggered", "lite_better",
        "Endometrial cancer is the correct disease but drops stage IA; Lynch syndrome is a predisposition and does not itself answer the cancer diagnosis. No A1 ran, and the projection correctly favors Lite only in one historical call.",
    ),
    "DA_d2_seq100/206": _j(
        "partial_or_scope", "partial_or_scope", "not_triggered", "projection", "not_triggered", "clinically_equivalent",
        "Graft occlusion identifies the cause but omits the acute posterior/inferior STEMI-equivalent consequence. Identical champions have different mapper outcomes; no gate can explain this.",
    ),
    "DA_d2_seq100/220": _j(
        "no", "no", "not_triggered", "projection", "not_triggered", "clinically_equivalent",
        "Both arms incorrectly call extranodal NK/T lymphoma instead of EBV-positive plasmablastic lymphoma. The unchanged champion's mapper flip is a task-interface artifact.",
    ),
    "DA_d2_seq100/225": _j(
        "partial_or_scope", "partial_or_scope", "new_distractor", "projection", "neutral", "clinically_equivalent",
        "DLBCL captures the transformed malignancy but omits antecedent CLL/Richter transformation and penile presentation. A1 adds unrelated cutaneous lymphoma labels; the unchanged champion's option repair is mapper variation rather than new clinical information.",
    ),
    "DA_d2_seq100/229": _j(
        "yes", "no", "not_triggered", "sampling_churn", "not_triggered", "lite_better",
        "Lite uses CCP, rheumatoid treatment, sterile granulomatous meningitis and negative chest imaging to identify rheumatoid meningitis. Adaptive switches to neurosarcoidosis without A1; both map to the gold option, showing that task projection masks concept harm.",
    ),
    "MCR_v1_seq100/3": _j(
        "no", "no", "merge_only", "selector", "neutral", "both_incorrect",
        "CIDP and peroneal neuropathy both miss eosinophilic granulomatosis with polyangiitis; the supplied excerpt lacks the later eosinophilic/vasculitic confirmation. A1 adds no novel frozen entity and cannot escape the local-neuropathy framing.",
    ),
    "MCR_v1_seq100/16": _j(
        "no", "yes", "new_decisive", "selector", "repair", "adaptive_better",
        "Urethral stricture is only the consequence. A1 explicitly adds amyloidosis of the urethra and adaptive emits urethral amyloidosis; negative systemic evaluation makes the localized scope clinically clear despite bridge formatting failure.",
    ),
    "MCR_v1_seq100/21": _j(
        "yes", "no", "not_triggered", "sampling_churn", "not_triggered", "lite_better",
        "Lite correctly prioritizes the decade-long expansile orbital bone lesion as fibrous dysplasia. The non-triggered A5 path chooses orbital meningioma from enhancement despite the lytic osseous pattern; this is not Call-4 utility.",
    ),
    "MCR_v1_seq100/27": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Massive ovarian edema is absent from both champions. A1 introduces ovarian fibroma and the selector promotes it from nonspecific preoperative imaging, reinforcing a tumor mimic rather than recovering the pathologic entity.",
    ),
    "MCR_v1_seq100/42": _j(
        "no", "no", "new_distractor", "selector", "neutral", "both_incorrect",
        "Both abscess and dermoid cyst miss keratocystic odontogenic tumor; the excerpt withholds decisive histology. A1 adds infection mimics but the adaptive winner is a pre-existing cyst, so no useful conversion occurs.",
    ),
    "MCR_v1_seq100/44": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Rapid postoperative necrosis, negative blood cultures and progression on antibiotics support pyoderma gangrenosum. A1 adds organism/sepsis/endocarditis labels and adaptive further specifies a pocket biofilm infection, amplifying the wrong infectious anchor.",
    ),
    "MCR_v1_seq100/47": _j(
        "partial_or_scope", "yes", "new_decisive", "selector", "repair", "adaptive_better",
        "Lite identifies hepatic metastatic melanoma but does not state the unknown primary. A1 generates both metastatic melanoma to liver and an occult-primary formulation; adaptive rationale explicitly uses absence of a primary, making the output clinically adequate despite strict surface failure.",
    ),
    "MCR_v1_seq100/61": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Both arms remain anchored to the prior erroneous adenoma biopsies and miss choriocarcinoma. A1 newly supplies hemorrhagic liver adenoma, which becomes champion and deepens rather than repairs the anchor.",
    ),
    "MCR_v1_seq100/63": _j(
        "no", "yes", "merge_only", "selector", "repair", "adaptive_better",
        "Lite chooses ureteral leiomyoma, while adaptive emits the exact fibroepithelial-polyp diagnosis. A1 repeats/merges the already exposed ureteral-polyp object and apparently strengthens its selection; this is conversion rather than new capture.",
    ),
    "MCR_v1_seq100/77": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "The parallel muscle-signal orbital band is an accessory extraocular muscle. A1 adds strabismus, thyroid ophthalmopathy and myositis; selecting strabismus answers a consequence rather than the anatomic lesion.",
    ),
    "MCR_v1_seq100/78": _j(
        "yes", "no", "not_triggered", "sampling_churn", "not_triggered", "lite_better",
        "Lite correctly diagnoses sciatic-nerve schwannoma. The non-triggered A5 path changes to neurofibroma on the same cystic nerve-sheath evidence, an unrelated selector/upstream fluctuation.",
    ),
    "MCR_v1_seq100/81": _j(
        "no", "no", "merge_only", "selector", "neutral", "both_incorrect",
        "Neither JIA nor juvenile dermatomyositis reaches macrophage myofasciitis; the excerpt lacks vaccine/pathology evidence. A1 only revisits existing inflammatory labels and cannot identify the hidden target.",
    ),
    "MCR_v1_seq100/99": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Both Melkersson-Rosenthal syndrome and cheilitis granulomatosa miss histoplasmosis; negative antigen/culture do not exclude localized/IRIS disease. A1 adds cheilitis and mycobacterial alternatives and further entrenches a morphologic mimic.",
    ),
    "MCR_v1_seq100/113": _j(
        "no", "no", "new_distractor", "selector", "neutral", "clinically_equivalent",
        "Both outputs correctly notice a Sister Mary Joseph metastasis but incorrectly assign colonic origin despite negative colonoscopy and miss jejunal adenocarcinoma. A1 adds more generic/colorectal umbilical-metastasis labels without solving the primary site.",
    ),
    "MCR_v1_seq100/114": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Inclusion/epidermoid cyst and A1 dermoid cyst all miss a subcutaneous ependymoma; definitive pathology is absent from the excerpt. The added cyst differential supplies no target information and sustains the wrong lesion class.",
    ),
    "MCR_v1_seq100/121": _j(
        "no", "no", "new_distractor", "selector", "neutral", "both_incorrect",
        "The painful cheek angioleiomyoma is not identifiable from the nonspecific preoperative description. A1 adds mucocele while selection drifts from lipoma to ectopic lymph node; neither is a mechanistic gain.",
    ),
    "MCR_v2_seq100/140": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Both epithelial-polyp labels miss gastric adenomyoma. A1 adds hyperplastic polyp, which becomes the adaptive champion and reinforces superficial endoscopic appearance without the resection pathology needed for adenomyoma.",
    ),
    "MCR_v2_seq100/142": _j(
        "yes", "no", "not_triggered", "sampling_churn", "not_triggered", "lite_better",
        "Lite correctly follows the markedly vascular bleeding auricular tumor to angiosarcoma. Adaptive instead selects Langerhans histiocytosis without A1 and without characteristic pathology; this is historical sampling/selection churn.",
    ),
    "MCR_v2_seq100/143": _j(
        "partial_or_scope", "yes", "not_triggered", "sampling_churn", "not_triggered", "adaptive_better",
        "Wegener granulomatosis is a plausible specific ANCA-associated vasculitis but the excerpt does not supply subtype-defining serology. Adaptive's umbrella answer exactly matches the requested diagnosis; no gate was invoked.",
    ),
    "MCR_v2_seq100/147": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Synovial chondromatosis and giant-cell tumor both miss angioleiomyoma. A1 newly adds giant-cell tumor/hemangioma/osteoid osteoma and the first becomes champion, demonstrating distractor capture without target capture.",
    ),
    "MCR_v2_seq100/168": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "ADEM and NMOSD ignore widespread lymphadenopathy/perirenal infiltration and the requested paraneoplastic encephalomyelitis. A1 generates multiple inflammatory myelitis labels and promotes NMOSD, widening the wrong mechanism family.",
    ),
    "MCR_v2_seq100/178": _j(
        "no", "yes", "not_triggered", "sampling_churn", "not_triggered", "adaptive_better",
        "Factitious disorder and malingering are not interchangeable; the instrumental medication-seeking/external incentives favor malingering. Adaptive repairs the concept without A1, so it cannot validate the runtime gate.",
    ),
    "MCR_v2_seq100/182": _j(
        "partial_or_scope", "partial_or_scope", "new_redundant", "selector", "neutral", "clinically_equivalent",
        "Both arms describe hepatic/extramedullary plasma-cell myeloma, clinically the plasmacytoma family but without the concise lesion label. A1's generic metastatic-liver candidate is redundant and the wording change adds no clear resolution.",
    ),
    "MCR_v2_seq100/192": _j(
        "no", "no", "new_distractor", "selector", "harm", "both_incorrect",
        "Both outputs stop at ischemic stroke and miss neurosyphilis as its cause; the supplied excerpt ends before the causal workup. A1 adds PFO/Moyamoya alternatives, broadening unsupported etiologies rather than discovering the reference.",
    ),
    "MCR_v2_seq100/205": _j(
        "no", "yes", "not_triggered", "sampling_churn", "not_triggered", "adaptive_better",
        "Adaptive correctly identifies disseminated/cutaneous cysticercosis from multiple mobile nodules including tongue involvement. Lite's NF1 label is unsupported; the repair occurs with no A1.",
    ),
    "MCR_v2_seq100/207": _j(
        "no", "no", "merge_only", "selector", "neutral", "both_incorrect",
        "CIDP and diabetic amyotrophy explain the neuropathy but miss the benchmark renal-cell carcinoma/paraneoplastic cause, whose decisive tumor evidence is absent from the excerpt. A1 only recycles neuropathy labels.",
    ),
    "MCR_v2_seq100/213": _j(
        "no", "yes", "new_decisive", "selector", "repair", "adaptive_better",
        "SJS is contradicted by a pruritic maculopapular eruption without mucosal/systemic features. A1 supplies maculopapular drug eruption, an ordinary clinical synonym of morbilliform drug eruption, and it becomes the correct champion despite the frozen bridge miss.",
    ),
    "MCR_v2_seq100/233": _j(
        "yes", "yes", "not_triggered", "sampling_churn", "not_triggered", "clinically_equivalent",
        "Double-Outlet Right Ventricle and Double Outlet Right Ventricle are the same diagnosis. The strict flip is solely the frozen normalizer retaining a hyphen; there is no clinical transition and no A1.",
    ),
    "MCR_v2_seq100/240": _j(
        "no", "no", "new_distractor", "selector", "neutral", "both_incorrect",
        "Kimura disease and myositis both miss IgG4-related disease; definitive immunopathology is absent from the excerpt. A1's chronic-osteomyelitis candidate adds another bony-destruction mimic without becoming champion.",
    ),
    "MCR_v2_seq100/241": _j(
        "partial_or_scope", "partial_or_scope", "merge_only", "selector", "harm", "lite_better",
        "Mucinous adenocarcinoma captures histology but omits the perianal fistula origin; anorectal cancer retains site but loses mucinous histology. A1 repeats these components and adaptive chooses the less pathologically specific label.",
    ),
    "MCR_v2_seq100/244": _j(
        "no", "partial_or_scope", "new_distractor", "selector", "neutral", "adaptive_better",
        "Fetal brain disruption sequence is mechanistically compatible with destructive cerebral loss after co-twin death but is not the morphologic hydranencephaly diagnosis. A1 improves the causal frame yet still fails the requested entity.",
    ),
}


VALID = {
    "clinical_lite_equivalence": {"yes", "partial_or_scope", "no"},
    "clinical_adaptive_equivalence": {"yes", "partial_or_scope", "no"},
    "a1_information_role": {"new_decisive", "new_redundant", "new_distractor", "merge_only", "not_triggered"},
    "conversion_locus": {"capture", "registry", "frontier", "selector", "projection", "sampling_churn", "not_applicable"},
    "observed_gate_utility": {"repair", "harm", "neutral", "not_triggered"},
    "clinical_direction": {"adaptive_better", "lite_better", "clinically_equivalent", "both_incorrect", "projection_only"},
}


def clinical_score(value: str) -> int:
    return {"no": 0, "partial_or_scope": 1, "yes": 2}[value]


def run(out: Path) -> dict[str, Any]:
    queue_path = out / "manual_audit_queue.jsonl"
    queue = read_jsonl(queue_path)
    expected = {str(row["case_key"]) for row in queue}
    if expected != set(MANUAL) or len(queue) != len(MANUAL):
        raise AssertionError(
            f"manual coverage mismatch missing={sorted(expected - set(MANUAL))} "
            f"extra={sorted(set(MANUAL) - expected)}"
        )
    rows: list[dict[str, Any]] = []
    for source in queue:
        key = str(source["case_key"])
        judgment = MANUAL[key]
        for field, allowed in VALID.items():
            if judgment[field] not in allowed:
                raise AssertionError(f"invalid {field}={judgment[field]!r} for {key}")
        if not judgment["root_note"].strip():
            raise AssertionError(f"empty note for {key}")
        rows.append({
            "case_key": key,
            "queue_reasons": source["queue_reasons"],
            "gold": source["gold"],
            "triggered": bool(source["triggered"]),
            "pre_gate": source["pre_gate"],
            "lite_champion": source["lite_champion"],
            "adaptive_champion": source["adaptive_champion"],
            "lite_strict_hit": bool(source["lite_strict_hit"]),
            "adaptive_strict_hit": bool(source["adaptive_strict_hit"]),
            "lite_option_top1": source.get("lite_option_top1"),
            "adaptive_option_top1": source.get("adaptive_option_top1"),
            "a1_candidate_labels": source["a1_candidate_labels"],
            "a1_new_labels": source["a1_new_labels"],
            "upstream_identical": bool(source["upstream_identical"]),
            **judgment,
        })
    write_jsonl(out / "manual_audit.jsonl", rows)
    triggered_flips = [
        row for row in rows
        if row["triggered"] and "triggered_champion_flip" in row["queue_reasons"]
    ]
    no_gate_strict = [
        row for row in rows
        if not row["triggered"] and "strict_concept_flip" in row["queue_reasons"]
    ]
    da_projection = [row for row in rows if "da_option_projection_flip" in row["queue_reasons"]]
    summary: dict[str, Any] = {
        "schema": "E14x_root_manual_audit_v1",
        "manual_case_n": len(rows),
        "triggered_champion_flip_n": len(triggered_flips),
        "judgment_counts": {
            field: dict(sorted(Counter(row[field] for row in rows).items()))
            for field in VALID
        },
        "triggered_champion_flips": {
            "n": len(triggered_flips),
            "observed_gate_utility_counts": dict(sorted(Counter(row["observed_gate_utility"] for row in triggered_flips).items())),
            "clinical_direction_counts": dict(sorted(Counter(row["clinical_direction"] for row in triggered_flips).items())),
            "a1_information_role_counts": dict(sorted(Counter(row["a1_information_role"] for row in triggered_flips).items())),
            "clinically_complete_lite_n": sum(row["clinical_lite_equivalence"] == "yes" for row in triggered_flips),
            "clinically_complete_adaptive_n": sum(row["clinical_adaptive_equivalence"] == "yes" for row in triggered_flips),
            "clinical_ordinal_delta_sum": sum(
                clinical_score(row["clinical_adaptive_equivalence"])
                - clinical_score(row["clinical_lite_equivalence"])
                for row in triggered_flips
            ),
        },
        "nontriggered_strict_flips": {
            "n": len(no_gate_strict),
            "adaptive_better_n": sum(row["clinical_direction"] == "adaptive_better" for row in no_gate_strict),
            "lite_better_n": sum(row["clinical_direction"] == "lite_better" for row in no_gate_strict),
            "clinically_equivalent_n": sum(row["clinical_direction"] == "clinically_equivalent" for row in no_gate_strict),
            "pairwise_a5_or_sampling_policy_warning": True,
        },
        "da_projection_flips": {
            "n": len(da_projection),
            "same_champion_n": sum(
                str(row["lite_champion"]).strip().lower()
                == str(row["adaptive_champion"]).strip().lower()
                for row in da_projection
            ),
            "projection_only_or_clinically_equivalent_n": sum(
                row["clinical_direction"] in {"projection_only", "clinically_equivalent"}
                for row in da_projection
            ),
            "mapper_masks_clinically_wrong_adaptive_n": sum(
                row["adaptive_option_top1"] is True
                and row["clinical_adaptive_equivalence"] == "no"
                for row in da_projection
            ),
        },
        "critical_findings": [
            "No primary pair has identical G1/G2, so these clinical directions do not identify an A1 causal effect.",
            "A1 can recover clinically valid surface variants missed by strict identity, but it more often introduces a selectable mimic in the triggered-flip audit set.",
            "DA option projection sometimes repairs scope, sometimes changes on an identical champion, and sometimes marks a clinically wrong champion correct.",
            "Non-triggered Adaptive-4v2 changes include A5 and fresh-upstream churn; they must not be credited to runtime gating.",
        ],
        "root_agent_final_responsibility": True,
        "external_llm_used_for_manual_judgment": False,
        "causal_identification": "none_historical_upstream_mismatch",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(out / "manual_audit_summary.json", summary)
    atomic_json(out / "manual_audit_manifest.json", {
        "schema": "E14x_root_manual_audit_manifest_v1",
        "frozen_queue_sha256": file_sha256(queue_path),
        "case_ledger_sha256": file_sha256(out / "case_ledger.jsonl"),
        "manual_rows_sha256": file_sha256(out / "manual_audit.jsonl"),
        "manual_n": len(rows),
        "root_agent_final_responsibility": True,
        "external_llm_used_for_manual_judgment": False,
    })
    (out / "manual_audit_run.log").write_text(
        "\n".join([
            f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
            "phase=E14x root clinical gate-trajectory audit",
            f"manual_cases={len(rows)}",
            f"triggered_champion_flips={len(triggered_flips)}",
            f"utility_counts={json.dumps(summary['triggered_champion_flips']['observed_gate_utility_counts'], sort_keys=True)}",
            "external_llm_used=false",
            "causal_identification=none_historical_upstream_mismatch",
        ]) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.out.resolve()), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

