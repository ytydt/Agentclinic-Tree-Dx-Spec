# Dual-Inf pin (optional)

Runtime uses multi-module Dual-Inf in `scripts/paper/baseline_arms.run_b04`
(forward → backward → examine → optional reflect) on the shared project model.

Optional upstream clone for prompt audit:

```bash
git clone https://github.com/betterzhou/Dual-Inf.git baselines/dual_inf/upstream
git -C baselines/dual_inf/upstream checkout a8ea4a954479e38f318ae8a871192c4daa2b26ec
```
