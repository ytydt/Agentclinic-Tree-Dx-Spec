# APHHM answered-intersection prune funnel

## all n=300
- tree_recall=0.5467 → final_recall=0.29 (final|tree=0.5305) → acc=0.48 (acc|final=0.7586)
- prune_loss=77 (0.2567); aphhm_win=11 aphhm_lose=56
- loci={'final_ok': 66, 'tree_miss': 136, 'tree_hit_final_drop': 77, 'final_hit_judge_miss': 21}
- lose_loci={'tree_miss': 25, 'final_hit_judge_miss': 13, 'tree_hit_final_drop': 18}
- win_loci={'final_ok': 5, 'tree_miss': 4, 'tree_hit_final_drop': 2}
- e7 when pruned: {'n_pruned': 77, 'e7_correct': 34, 'rate': 0.4416}

## da n=200
- tree_recall=0.555 → final_recall=0.275 (final|tree=0.4955) → acc=0.59 (acc|final=0.8545)
- prune_loss=56 (0.28); aphhm_win=9 aphhm_lose=43
- loci={'final_ok': 47, 'tree_miss': 89, 'tree_hit_final_drop': 56, 'final_hit_judge_miss': 8}
- lose_loci={'tree_miss': 20, 'final_hit_judge_miss': 7, 'tree_hit_final_drop': 16}
- win_loci={'final_ok': 4, 'tree_miss': 3, 'tree_hit_final_drop': 2}
- e7 when pruned: {'n_pruned': 56, 'e7_correct': 29, 'rate': 0.5179}

## mcr n=100
- tree_recall=0.53 → final_recall=0.32 (final|tree=0.6038) → acc=0.26 (acc|final=0.5938)
- prune_loss=21 (0.21); aphhm_win=2 aphhm_lose=13
- loci={'tree_miss': 47, 'tree_hit_final_drop': 21, 'final_ok': 19, 'final_hit_judge_miss': 13}
- lose_loci={'tree_miss': 5, 'final_hit_judge_miss': 6, 'tree_hit_final_drop': 2}
- win_loci={'final_ok': 1, 'tree_miss': 1}
- e7 when pruned: {'n_pruned': 21, 'e7_correct': 5, 'rate': 0.2381}

