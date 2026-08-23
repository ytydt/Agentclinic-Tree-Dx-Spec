# Pinned lab-audit benchmark snapshots

This directory contains the exact benchmark artifacts used to audit numeric
laboratory coverage. File revisions, sizes, SHA-256 hashes, schemas, and source
URLs are recorded in
[`../lab_reference_dataset_manifest.json`](../lab_reference_dataset_manifest.json).

Run the following command from the repository root to verify all four files or
restore a missing/corrupted file from its pinned upstream revision:

```bash
python scripts/download_lab_audit_datasets.py --verify-only
python scripts/download_lab_audit_datasets.py
```

| Snapshot | Upstream | Terms recorded by the pinned source |
|---|---|---|
| `diagnosisarena/test.parquet` | [DiagnosisArena](https://huggingface.co/datasets/SII-SPIRAL-MED/DiagnosisArena) | No SPDX dataset license in the card; research and model evaluation only; citation requested. |
| `medcasereasoning/validation.parquet` | [MedCaseReasoning](https://huggingface.co/datasets/zou-lab/MedCaseReasoning) | Dataset: CC BY 4.0, derived from the PMC Open Access Subset; code: MIT. Citation and attribution retained. |
| `open_xddx/Open-XDDx.xlsx` | [Dual-Inf / Open-XDDx](https://github.com/betterzhou/Dual-Inf) | No explicit LICENSE at pinned revision `a8ea4a9`; confirm further redistribution with the authors. |
| `rarebench/data.zip` | [RareBench](https://huggingface.co/datasets/chenxz/RareBench) | Hugging Face metadata declares Apache-2.0; citation and notices retained. |

The datasets are not covered by the Agentclinic-Tree-Dx-Spec repository's own
license. Copyright and database rights remain with their respective upstream
authors and source publications. Presence here is for research reproducibility
and does not authorize clinical use or remove upstream restrictions.
