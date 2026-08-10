#!/usr/bin/env python3
"""Score blind adjudications against rule labels; compute kappa & cluster FP.

Expects adjudicator JSONL at:
  analysis/backbone_v1/r4_adjudication/judgments/*.jsonl
each line: {key, cluster, fail_code, semantic_e7_correct, rationale?}
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import r4_lib as r4

OUT = r4.OUT / "r4_adjudication"
JUDG = OUT / "judgments"

# map rule binary cluster → 4-way for comparison
RULE_TO_4 = {
    "gold": "same_entity",
    "near": "sibling_family",  # rule "near" is loose; treat as sibling by default
    "other": "unrelated",
    "empty": "unrelated",
}


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    labels = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    idx = {l: i for i, l in enumerate(labels)}
    n = len(pairs)
    mat = [[0] * len(labels) for _ in labels]
    for a, b in pairs:
        mat[idx[a]][idx[b]] += 1
    po = sum(mat[i][i] for i in range(len(labels))) / n
    row = [sum(mat[i][j] for j in range(len(labels))) / n for i in range(len(labels))]
    col = [sum(mat[i][j] for i in range(len(labels))) / n for j in range(len(labels))]
    pe = sum(row[i] * col[i] for i in range(len(labels)))
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)


def main() -> int:
    sample = {r["key"]: r for r in r4.load_tsv(OUT / "sample.tsv")}
    judgments = []
    for p in sorted(JUDG.glob("*.jsonl")) if JUDG.is_dir() else []:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            judgments.append(json.loads(line))
    if not judgments:
        print("No judgments yet at", JUDG)
        return 1

    # dedupe by key (last wins)
    by_key = {}
    for j in judgments:
        by_key[j["key"]] = j
    judgments = list(by_key.values())

    code_pairs = []
    cluster_pairs = []
    near_fp = 0
    near_n = 0
    same_cluster_adj = 0
    base_win_rank_n = 0
    base_win_rank_same = 0

    conf_code = defaultdict(Counter)
    conf_cluster = defaultdict(Counter)

    rows_out = []
    for j in judgments:
        s = sample.get(j["key"])
        if not s:
            continue
        rule_code = s.get("rule_fail_code") or "other"
        rule_cl = s.get("rule_champ_cluster") or "other"
        adj_code = j.get("fail_code") or "other"
        adj_cl = j.get("cluster") or "unrelated"
        code_pairs.append((rule_code, adj_code))
        conf_code[rule_code][adj_code] += 1
        # cluster: compare rule gold/near/other vs 4-way
        rule_4 = RULE_TO_4.get(rule_cl, "unrelated")
        # for near_gold FP: rule said near but adjudicator said unrelated
        if rule_cl == "near":
            near_n += 1
            if adj_cl == "unrelated":
                near_fp += 1
        cluster_pairs.append((rule_4, adj_cl))
        conf_cluster[rule_4][adj_cl] += 1

        # re-estimate same-cluster share among base_win_rank
        if (s.get("layer_chain") or "") == "base_win_rank":
            base_win_rank_n += 1
            if adj_cl in ("same_entity", "parent_subtype", "sibling_family"):
                base_win_rank_same += 1
                same_cluster_adj += 1

        rows_out.append(
            {
                "key": j["key"],
                "rule_fail_code": rule_code,
                "adj_fail_code": adj_code,
                "rule_cluster": rule_cl,
                "adj_cluster": adj_cl,
                "semantic_e7_correct": j.get("semantic_e7_correct"),
                "layer_chain": s.get("layer_chain"),
                "rationale": j.get("rationale") or "",
            }
        )

    kappa_code = cohen_kappa(code_pairs)
    kappa_cluster = cohen_kappa(cluster_pairs)
    summary = {
        "n_judged": len(rows_out),
        "kappa_fail_code": round(kappa_code, 4),
        "kappa_cluster": round(kappa_cluster, 4),
        "near_gold_n": near_n,
        "near_gold_false_positive_as_unrelated": near_fp,
        "near_gold_fp_rate": (near_fp / near_n) if near_n else None,
        "base_win_rank_n_judged": base_win_rank_n,
        "base_win_rank_same_cluster_adj": base_win_rank_same,
        "base_win_rank_same_cluster_share_adj": (
            base_win_rank_same / base_win_rank_n if base_win_rank_n else None
        ),
        "rule_code_may_be_primary": kappa_code >= 0.6,
        "conf_fail_code": {a: dict(b) for a, b in conf_code.items()},
        "conf_cluster": {a: dict(b) for a, b in conf_cluster.items()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    r4.write_tsv(OUT / "judgment_vs_rule.tsv", rows_out)
    print(json.dumps({k: summary[k] for k in summary if k.startswith("conf") is False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
