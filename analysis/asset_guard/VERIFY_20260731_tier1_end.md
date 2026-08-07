# Asset guard verify note (Tier-1 end)

Against snapshot `20260731T040406Z` (taken mid-AB29), verify reported:

1. `logs/open_xddx_ox_seq100_v1/c2_ab29_v1/annotate/cache/**` — LLM cache growth during the campaign (expected).
2. `.../official_eval_llm_compat_rr_dsv4f/judge_cache.json` — second-judge cache append (T1-11).
3. `runs/paper_v1/ablations_c2_ox_raw.json` — **incident**: overwritten by STF suite; restored from on-disk arm summaries; see `INCIDENT_20260731_t109_ox_raw_overwrite.md`.

No deletes of published eval summaries. `ablations_c2_da_raw.json` / `ablations_c3_da_raw.json` / M00 & MCR official summaries matched the snapshot.

End-of-campaign snapshots: `20260731T084717Z` (pre-restore) and a post-restore snapshot taken after OX raw recovery.
