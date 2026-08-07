# Asset incident: ablations_c2_da_raw.json overwrite

During T1-10 AB28 live recheck, `run_c2_da_selector_suite.py --run-ab28-live` wrote results to `runs/paper_v1/ablations_c2_da_raw.json`, overwriting the published C2 DA summary.

Mitigation:
1. Live AB28 result saved to `runs/paper_v1/ablations_t110_ab28_live.json`
2. `ablations_c2_da_raw.json` reconstructed from arm dirs + `ablations_c2_ab28_reused.json` (marked restored=True)
3. Suite patched to write AB28-only live runs to `ablations_t110_ab28_live.json`
4. New asset_guard snapshot taken after reconstruction

Live vs reused AB28 (frozen judge contract, typed_llm full inject):
- R_compat unchanged: opt1=0.72 opt2=0.78
- R_compat_inject_typed: reused 0.42/0.69/mrr0.628 → live 0.40/0.67/mrr0.608
