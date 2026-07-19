def choose_update_method(annotation: dict) -> str:
    # F2: numeric per-branch LRs (from KB direction reconciliation) take
    # precedence — they enable a true Bayesian odds×LR update.
    if annotation.get("branch_lr"):
        return "calculator"
    if annotation.get("calculator_applicable", False):
        return "calculator"
    if annotation.get("formal_rule_available", False):
        return "rule_based"
    return "ordinal"
