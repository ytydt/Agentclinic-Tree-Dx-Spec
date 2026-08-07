#!/usr/bin/env bash
# DEPRECATED for corrected multi-step B04/B05/B06.
# Prefer: bash scripts/paper/run_fixed_baselines_d2_seq100.sh
# (fresh runs_root diagnosisarena_fixed_v1; real Dual-Inf / MDAgents / MAC).
#
# This wrapper forwards to the fixed harness (pure arms only).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SKIP_RAG=1
export PURE_ARMS="${ARMS:-B04-dual-inf,B05-mdagents,B06-mac-single-vendor}"
exec bash "$ROOT/scripts/paper/run_fixed_baselines_d2_seq100.sh"
