Pin Chain-of-Diagnosis + DiagnosisGPT here.

## Install

```bash
# upstream already at baselines/chain_of_diagnosis/upstream
# weights (DiagnosisGPT-6B, includes official disease DB + retriever):
#   baselines/chain_of_diagnosis/models/DiagnosisGPT-6B
# mark ready after download:
python -c "import sys; sys.path.insert(0,'baselines/chain_of_diagnosis'); import adapter; adapter.mark_ready()"
```

Touch `READY` (via `adapter.mark_ready()`) only after `config.json` and model shards exist.

## Runtime

B11a uses **local GPU** DiagnosisGPT (not shared rag_index/cpg_index).
Spawn process pool assigns one physical GPU per worker via `CUDA_VISIBLE_DEVICES`.

