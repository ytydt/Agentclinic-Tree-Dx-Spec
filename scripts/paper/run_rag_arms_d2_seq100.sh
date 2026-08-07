#!/usr/bin/env bash
# DEPRECATED for corrected B02/B15/B16 (and keeps B01/B11b only if requested).
# Prefer: bash scripts/paper/run_fixed_baselines_d2_seq100.sh
#
# Default now runs corrected RAG arms on diagnosisarena_fixed_v1.
# To include B01/B11b: RAG_ARMS=B01-cot-rag,B02-...,B11b-...,B16-... SKIP_PURE=1 ...
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SKIP_PURE=1
export RAG_ARMS="${ARMS:-B02-flat-matched-rerank,B15-medprompt-style,B16-medrag-kg}"
exec bash "$ROOT/scripts/paper/run_fixed_baselines_d2_seq100.sh"
