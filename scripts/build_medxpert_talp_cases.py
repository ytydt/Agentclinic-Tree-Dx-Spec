#!/usr/bin/env python3
"""Build a *draft* TALP discrimination expansion from MedXpertQA Hard.

The model creates candidate/finding structure only.  Output is deliberately
marked ``calibration_status=draft`` and must pass literature + human review
before it can be merged into the scored dataset.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_TSV = Path(
    "/home/wanghongyi/LLM-Structured-Data-main/"
    "som/MMLU/test/medxpertqar_hard_test.tsv"
)
DEFAULT_OUT = ROOT / "data/eval/talp_medxpert_expansion_cases.draft.json"

# Clear diagnosis / diagnostic-etiology items after a manual question-type
# screen.  This is selection provenance, not medical annotation.
SELECTED_INDICES = (11, 14, 36, 42, 45, 46, 55, 68, 75, 98)

PROMPT = """
You construct a DIAGNOSTIC DISCRIMINATION evaluation item from one medical
multiple-choice vignette. The supplied answer is the dataset gold, but do not
blindly invent facts to justify it.

Return STRICT JSON with:
{
  "gold": "<clinical diagnosis or diagnosis+etiology represented by the answer>",
  "l1_label": "<broad mutually-exclusive parent family>",
  "candidates": [
    {"name":"<diagnosis/etiology>", "l1_parent":"<broad family>",
     "is_gold": true|false}
  ],
  "findings": [
    {
      "finding":"<specific finding/test result>",
      "role":"rule_in_gold|rule_out_distractor|shared_nondiscriminating",
      "target":"<gold, distractor, or null>",
      "direction_target":"<distractor only for rule_out, otherwise null>",
      "in_vignette":true|false,
      "decisive":true|false,
      "note":"<short medical rationale>"
    }
  ]
}

Rules:
1. Give exactly 5 clinically plausible competing candidates, one gold.
2. Use diagnoses or etiologic diagnoses, not management actions.
3. Give 5 findings: at least 2 rule_in_gold, 1 rule_out_distractor, and
   1 shared_nondiscriminating. At least 2 must be present in the vignette.
4. A rule_in finding must preferentially support gold over the listed
   competitors. A shared finding must truly be non-specific within this set.
5. Mark exactly 1-2 findings decisive. Additional tests not in the vignette are
   allowed and should have in_vignette=false.
6. Do not use the answer wording itself as a finding.
7. If the supplied gold seems medically questionable, still encode it but add
   "GOLD_REVIEW_REQUIRED:" at the start of the relevant note.
"""


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def validate(case: dict) -> None:
    candidates = case.get("candidates") or []
    findings = case.get("findings") or []
    if len(candidates) != 5 or sum(bool(c.get("is_gold")) for c in candidates) != 1:
        raise ValueError("expected exactly five candidates and one gold")
    roles = [f.get("role") for f in findings]
    if len(findings) != 5:
        raise ValueError("expected exactly five findings")
    for needed in ("rule_in_gold", "rule_out_distractor",
                   "shared_nondiscriminating"):
        if needed not in roles:
            raise ValueError(f"missing role {needed}")
    if not 1 <= sum(bool(f.get("decisive")) for f in findings) <= 2:
        raise ValueError("expected one or two decisive findings")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tsv", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    args = parser.parse_args()

    from agentclinic_tree_dx.llm_client import RobustLLMClient

    rows = load_rows(args.tsv)
    llm = RobustLLMClient(
        model=args.model, call_timeout=180, max_retries=4, timeout_retry_cap=2
    )
    out = {
        "_readme": (
            "LLM-structured DRAFT from MedXpertQA Hard. Not scoreable until "
            "calibration_status is literature_reviewed and human_reviewed."
        ),
        "source": str(args.tsv),
        "selected_indices": list(SELECTED_INDICES),
        "cases": [],
    }

    for index in SELECTED_INDICES:
        row = rows[index]
        options = ast.literal_eval(row["options"])
        payload = {
            "source_index": index,
            "vignette": row["question"].split("Answer Choices:")[0].strip(),
            "answer": row["answer"],
            "answer_key": row["answer_idx"],
            "answer_choices": options,
        }
        result = llm.call_module("MedXpertTALPAnnotator", PROMPT, payload)
        validate(result)
        gold_name = next(c["name"] for c in result["candidates"] if c["is_gold"])
        for finding in result["findings"]:
            role = finding["role"]
            finding["favors"] = (
                "gold" if role == "rule_in_gold" else "shared"
            )
            if role == "rule_in_gold":
                finding["target"] = gold_name
            elif role == "shared_nondiscriminating":
                finding["target"] = None
                finding["direction_target"] = None
        result.update(
            {
                "id": f"mxh{index:03d}",
                "corpus": "medxpertqar_hard",
                "case_idx": index,
                "gold_option": row["answer"],
                "vignette": payload["vignette"],
                "source_answer": row["answer"],
                "source_answer_idx": row["answer_idx"],
                "source_options": options,
                "calibration_status": "draft",
                "annotation_provenance": {
                    "method": "LLM structured draft",
                    "model": args.model,
                    "medical_claims_verified": False,
                },
            }
        )
        out["cases"].append(result)
        print(f"[{index:03d}] {result['gold']} ({len(result['findings'])} findings)",
              flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"draft -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
