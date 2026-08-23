#!/usr/bin/env python3
"""Offline step-0 audit: is MultiStance's group_drop a same-core collision?

No LLM call. Reads the frozen `aphhm_c_multistance_v1` case_stages on the six
development slices and answers three questions the core-regroup design depends
on:

1. Under the runtime's own stance grouping (`concept.stances[0]`), which group
   held the gold, how large was that group, and which candidate was nominated
   over the gold?
2. If the grouping key were the deterministic lexical *core* instead of the
   stance, would the gold's core reach the finals — and how wide would the
   finals become?
3. What does core merging cost: how often does a merged component nominate a
   non-gold member over a gold member that currently reaches the finals?

The merge relation is deliberately lexical and deterministic (identical content
tokens, proper token subset, or shared head noun). No model judgement is used,
because C2's map gate failed precisely on free-form equivalence.

Endpoint caveat: `dc.match` is the legacy-chain matcher (PPV 56.48% for
clinical-complete). Every count below is a legacy-chain seat/hit count and is a
headroom instrument, not a clinical estimate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src", _ROOT / "analysis" / "backbone_v1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402
import r6_lib as r6  # noqa: E402

DEFAULT_OUT = _ROOT / "analysis" / "mechanism_v2" / "results" / "CORE_REGROUP_HEADROOM"
ARM = "multistance"

# Function words only. Clinical qualifiers (acute, primary, proliferative, ...)
# stay as content tokens: they are exactly the modifier information the design
# must not throw away.
FUNCTION_WORDS = {
    "a", "an", "and", "as", "at", "by", "due", "for", "from", "in", "of", "on",
    "or", "the", "to", "with", "without",
}
# Heads too generic to license a `stem_shared` merge on their own.
GENERIC_STEMS = {
    "syndrome", "disease", "disorder", "infection", "injury", "failure",
    "condition", "abnormality", "lesion", "reaction", "state", "process",
    "deficiency", "insufficiency", "dysfunction",
}
_PAREN = re.compile(r"\([^)]*\)")
_NONWORD = re.compile(r"[^a-z0-9]+")


def content_tokens(label: str) -> tuple[str, ...]:
    s = _PAREN.sub(" ", (label or "").lower())
    toks = [t for t in _NONWORD.split(s) if t]
    out: list[str] = []
    for t in toks:
        if t in FUNCTION_WORDS:
            continue
        if t not in out:
            out.append(t)
    return tuple(out)


def _singular(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        return tok[:-1]
    return tok


def head_token(toks: tuple[str, ...]) -> str:
    return _singular(toks[-1]) if toks else ""


def core_relation(a: str, b: str) -> str:
    """Deterministic lexical relation between two candidate labels."""
    ta, tb = content_tokens(a), content_tokens(b)
    if not ta or not tb:
        return "none"
    sa, sb = {_singular(t) for t in ta}, {_singular(t) for t in tb}
    if sa == sb:
        return "identical"
    if sa < sb or sb < sa:
        return "subset"
    if head_token(ta) and head_token(ta) == head_token(tb):
        return "head_shared"
    shared = {t for t in sa & sb if len(t) >= 5 and t not in GENERIC_STEMS}
    if shared:
        return "stem_shared"
    return "none"


# Two merge tiers. `subset_only` merges just modifier-addition pairs (the
# MODIFIER_HEADROOM criterion); `with_head` also merges same-head siblings such
# as bacterial vs viral meningitis, which removes E5's most expensive
# competition but can let the wrong sibling represent the core.
MERGE_TIERS: dict[str, set[str]] = {
    "subset_only": {"identical", "subset"},
    "with_head": {"identical", "subset", "head_shared"},
}
MERGE_RELATIONS = MERGE_TIERS["with_head"]


class Union:
    def __init__(self, keys: list[str]) -> None:
        self.parent = {k: k for k in keys}

    def find(self, k: str) -> str:
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def nominee_most_tokens(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Completeness-first within-core nominee: the most specific member.

    Most content tokens, then most support spans, then ledger rank. Its failure
    mode (an over-specific label displacing a correct coarser one) is measured,
    not hidden.
    """
    return sorted(
        members,
        key=lambda c: (
            -len(content_tokens(c["label"])),
            -len(c.get("support_spans") or []),
            c["rank"],
        ),
    )[0]


def nominee_best_rank(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Score-first within-core nominee: the runtime's own highest-ranked member."""
    return sorted(members, key=lambda c: c["rank"])[0]


NOMINEE_RULES = {
    "most_tokens": nominee_most_tokens,
    "best_rank": nominee_best_rank,
}


def shortlist_of(doc: dict) -> list[dict[str, Any]]:
    """Reconstruct the exact selector shortlist the runtime built.

    multistance is in `selector_all_concepts`, so the shortlist is the full
    ledger rank, and each candidate is placed in the group of its *first*
    stance (aphhm_c.py: `stance = (c.stances or ["unassigned"])[0]`).
    """
    stages = doc.get("stages") or {}
    reg = {c.get("concept_id"): c for c in (stages.get("registry") or [])}
    order = [cid for cid in (stages.get("ledger_rank") or []) if cid in reg]
    if not order:
        order = [cid for cid in reg if cid]
    out = []
    for rank, cid in enumerate(order):
        c = reg[cid]
        stances = [str(s) for s in (c.get("stances") or []) if str(s)]
        out.append(
            {
                "concept_id": str(cid),
                "label": str(c.get("preferred_label") or ""),
                "group": stances[0] if stances else "unassigned",
                "stances": stances,
                "support_spans": list(c.get("support_spans") or []),
                "rank": rank,
            }
        )
    return [c for c in out if c["label"]]


def audit_case(doc: dict, gold: str, dkey: str, sl: str, cid: str) -> Optional[dict]:
    stages = doc.get("stages") or {}
    sel = stages.get("frontier_selector") or {}
    cands = shortlist_of(doc)
    if not cands:
        return None
    rnd = r6.multistance_loss_round(doc, gold)

    fin_labels = [
        str(f.get("label") or "") if isinstance(f, dict) else str(f)
        for f in (sel.get("finalists") or [])
    ]
    fin_labels = [f for f in fin_labels if f]
    champion = str(sel.get("champion") or doc.get("champion") or "")

    gold_ids = {c["concept_id"] for c in cands if dc.match(c["label"], gold)}
    gold_seat_now = bool(fin_labels) and any(dc.match(f, gold) for f in fin_labels)

    # --- stance grouping as executed -------------------------------------
    by_group: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        by_group[c["group"]].append(c)
    group_sizes = {g: len(v) for g, v in by_group.items()}
    gold_groups = sorted({c["group"] for c in cands if c["concept_id"] in gold_ids})
    # which label was nominated out of the gold's stance group?
    eliminators = []
    for g in gold_groups:
        for f in fin_labels:
            if any(f == c["label"] for c in by_group[g]):
                eliminators.append({"group": g, "label": f})
    elim_rel = [
        {**e, "relation": core_relation(e["label"], gold)}
        for e in eliminators
        if not dc.match(e["label"], gold)
    ]

    # finals slots spent on same-core pairs
    wasted = 0
    for i in range(len(fin_labels)):
        for j in range(i + 1, len(fin_labels)):
            if core_relation(fin_labels[i], fin_labels[j]) in MERGE_RELATIONS:
                wasted += 1
    free_pass = sum(
        1
        for f in fin_labels
        for g, v in by_group.items()
        if len(v) == 1 and v[0]["label"] == f
    )

    # --- counterfactual: group by deterministic lexical core --------------
    all_pairs = [
        (cands[i], cands[j], core_relation(cands[i]["label"], cands[j]["label"]))
        for i in range(len(cands))
        for j in range(i + 1, len(cands))
    ]
    policies: dict[str, dict[str, Any]] = {}
    displaced_any: list[dict] = []
    cores_by_tier: dict[str, int] = {}
    # Sham controls: no grouping at all, just the top-N by the runtime's own
    # rank. If a core policy does not beat its equal-seat sham, the effect is
    # seat count, not object structure.
    by_rank = sorted(cands, key=lambda c: c["rank"])

    def _seat(members: list[dict]) -> dict[str, Any]:
        return {
            "n_seats": len(members),
            "gold_seat": any(c["concept_id"] in gold_ids for c in members),
            "finalists": [c["label"] for c in members],
        }

    merged_by_tier: dict[str, dict[str, int]] = {}
    biggest_core: dict[str, list[str]] = {}
    for tier, rels in MERGE_TIERS.items():
        uf = Union([c["concept_id"] for c in cands])
        tier_rel = Counter()
        for a, b, rel in all_pairs:
            if rel in rels:
                uf.union(a["concept_id"], b["concept_id"])
                tier_rel[rel] += 1
        comps: dict[str, list[dict]] = defaultdict(list)
        for c in cands:
            comps[uf.find(c["concept_id"])].append(c)
        # cores in the runtime's own rank order: a width cap stays gold-blind
        core_order = sorted(comps.values(), key=lambda v: min(c["rank"] for c in v))
        cores_by_tier[tier] = len(core_order)
        merged_by_tier[tier] = dict(tier_rel)
        biggest = max(core_order, key=len)
        biggest_core[tier] = [c["label"] for c in biggest] if len(biggest) > 1 else []

        for rule_name, rule in NOMINEE_RULES.items():
            nominees = [rule(v) for v in core_order]
            # merge harm: a core holds a gold member but nominates a non-gold one
            for v, nom in zip(core_order, nominees):
                ids = {c["concept_id"] for c in v}
                if ids & gold_ids and nom["concept_id"] not in gold_ids:
                    displaced_any.append(
                        {
                            "tier": tier,
                            "rule": rule_name,
                            "gold_members": [
                                c["label"] for c in v if c["concept_id"] in gold_ids
                            ],
                            "nominee": nom["label"],
                            "core": [c["label"] for c in v],
                        }
                    )
            for cap_name, cap in (
                ("one_seat_per_core", len(core_order)),
                ("width_matched", len(fin_labels)),
            ):
                seated = nominees[:cap] if cap else []
                policies[f"{tier}:{cap_name}:{rule_name}"] = _seat(seated)
        policies[f"sham_flat_topN:{tier}"] = _seat(by_rank[: len(core_order)])
    policies["sham_flat_width_matched"] = _seat(by_rank[: len(fin_labels)])

    return {
        "dataset": dkey,
        "slice": sl,
        "case_id": cid,
        "gold": gold,
        "loss_round": rnd,
        "n_shortlist": len(cands),
        "n_stance_groups": len(by_group),
        "stance_group_sizes": group_sizes,
        "n_finalists_now": len(fin_labels),
        "finalists_now": fin_labels,
        "champion": champion,
        "champion_vs_gold_relation": core_relation(champion, gold),
        "groups_without_finalist": max(0, len(by_group) - len(fin_labels)),
        "gold_group_had_no_finalist": bool(
            gold_groups and not eliminators and not gold_seat_now
        ),
        "free_pass_finalists": free_pass,
        "same_core_finalist_pairs": wasted,
        "gold_in_shortlist": bool(gold_ids),
        "gold_stance_groups": gold_groups,
        "gold_stance_group_size": max(
            [group_sizes[g] for g in gold_groups], default=0
        ),
        "gold_seat_now": gold_seat_now,
        "eliminators": elim_rel,
        "n_cores": cores_by_tier,
        "merge_relations": merged_by_tier,
        "largest_core_with_head": biggest_core.get("with_head") or [],
        "policies": policies,
        "gold_core_displaced": displaced_any,
    }


def _mean(xs: list[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 4) if xs else None


def aggregate(rows: list[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for scope in ("ALL", "da", "mcr"):
        sub = rows if scope == "ALL" else [r for r in rows if r["dataset"] == scope]
        if not sub:
            continue
        rounds = Counter(r["loss_round"] for r in sub)
        gd = [r for r in sub if r["loss_round"] == "group_drop"]
        ok = [r for r in sub if r["loss_round"] == "ok"]
        fd = [r for r in sub if r["loss_round"] == "final_drop"]

        # `group_drop` conflates two states: the gold never reached the selector
        # payload at all (registry merge / rank exclusion), and the gold was in
        # the payload but its stance group nominated someone else.
        gd_absent = [r for r in gd if not r["gold_in_shortlist"]]
        gd_seated = [r for r in gd if r["gold_in_shortlist"]]
        elim_rel = Counter()
        for r in gd_seated:
            for e in r["eliminators"]:
                elim_rel[e["relation"]] += 1

        # crude transfer of the observed finals win rate onto newly seated golds
        p_win = len(ok) / (len(ok) + len(fd)) if (len(ok) + len(fd)) else None
        policy_names = sorted(sub[0].get("policies") or {})
        policy_block: dict[str, Any] = {}
        for pol in policy_names:

            def seat(r: dict, pol: str = pol) -> bool:
                return bool((r["policies"].get(pol) or {}).get("gold_seat"))

            rescued = [r for r in gd if seat(r)]
            lost_ok = [r for r in ok if not seat(r)]
            lost_fd = [r for r in fd if not seat(r)]
            seats_cf = sum(1 for r in sub if seat(r))
            policy_block[pol] = {
                "seats_mean": _mean(
                    [float((r["policies"][pol] or {})["n_seats"]) for r in sub]
                ),
                "gold_seats_now": len(ok) + len(fd),
                "gold_seats_cf": seats_cf,
                "group_drop_seat_recovered": len(rescued),
                "ok_seat_lost": len(lost_ok),
                "final_drop_seat_lost": len(lost_fd),
                # optimistic: rescued seats convert at the current finals win
                # rate and no currently-winning case is disturbed except by an
                # outright seat loss. Ignores any width-induced conversion cost.
                "legacy_hit_delta_optimistic": (
                    round(len(rescued) * p_win - len(lost_ok), 2)
                    if p_win is not None
                    else None
                ),
                # pessimistic: every seated gold, old or new, converts only at
                # the average finals win rate.
                "legacy_hit_delta_pessimistic": (
                    round(seats_cf * p_win - len(ok), 2) if p_win is not None else None
                ),
            }

        out[scope] = {
            "n_cases": len(sub),
            "loss_rounds": dict(rounds),
            "shortlist_width_mean": _mean([r["n_shortlist"] for r in sub]),
            "n_finalists_now_mean": _mean([float(r["n_finalists_now"]) for r in sub]),
            "n_cores_mean": {
                tier: _mean([float(r["n_cores"][tier]) for r in sub])
                for tier in MERGE_TIERS
            },
            "stance_group_size_max_mean": _mean(
                [float(max(r["stance_group_sizes"].values() or [0])) for r in sub]
            ),
            "free_pass_finalists_mean": _mean(
                [float(r["free_pass_finalists"]) for r in sub]
            ),
            "cases_with_same_core_finalist_pair": sum(
                1 for r in sub if r["same_core_finalist_pairs"] > 0
            ),
            "merge_relation_totals": {
                tier: dict(
                    sum((Counter(r["merge_relations"][tier]) for r in sub), Counter())
                )
                for tier in MERGE_TIERS
            },
            "group_drop": {
                "n": len(gd),
                "gold_absent_from_selector_payload": len(gd_absent),
                "gold_in_payload_not_nominated": len(gd_seated),
                "gold_stance_group_size_mean": _mean(
                    [float(r["gold_stance_group_size"]) for r in gd_seated]
                ),
                "eliminator_core_relation": dict(elim_rel),
                "eliminator_shares_merge_core": sum(
                    1
                    for r in gd_seated
                    for e in r["eliminators"]
                    if e["relation"] in MERGE_RELATIONS
                ),
                "gold_group_produced_no_finalist": sum(
                    1 for r in gd_seated if not r["eliminators"]
                ),
            },
            "gold_displaced_within_core": {
                f"{tier}:{rule}": sum(
                    1
                    for r in sub
                    if any(
                        d["rule"] == rule and d["tier"] == tier
                        for d in r["gold_core_displaced"]
                    )
                )
                for tier in MERGE_TIERS
                for rule in sorted(NOMINEE_RULES)
            },
            "final_drop": {
                "n": len(fd),
                "champion_vs_gold_relation": dict(
                    Counter(r["champion_vs_gold_relation"] for r in fd)
                ),
                "n_finalists": dict(
                    sorted(Counter(r["n_finalists_now"] for r in fd).items())
                ),
            },
            "selector_compliance": {
                "n_stance_groups_mean": _mean(
                    [float(r["n_stance_groups"]) for r in sub]
                ),
                "cases_with_a_group_giving_no_finalist": sum(
                    1 for r in sub if r["groups_without_finalist"] > 0
                ),
                "group_drop_cases_where_gold_group_was_silent": sum(
                    1 for r in gd if r["gold_group_had_no_finalist"]
                ),
            },
            "funnel_legacy_chain": {
                "in_shortlist": len(ok) + len(fd) + len(gd),
                "reached_finals": len(ok) + len(fd),
                "won_final": len(ok),
            },
            "finals_win_rate_now": round(p_win, 4) if p_win is not None else None,
            "policies": policy_block,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    gold = r5.load_gold()
    rows: list[dict] = []
    missing = 0
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, ARM) is None:
            continue
        cids = [c for (dd, ss, c) in gold if dd == dkey and ss == sl]
        for cid in sorted(cids, key=lambda x: (len(x), x)):
            doc = r6.load_raw_doc(log_ds, ARM, cid)
            if not doc:
                missing += 1
                continue
            rec = audit_case(doc, gold[(dkey, sl, cid)], dkey, sl, cid)
            if rec is None:
                missing += 1
                continue
            rows.append(rec)

    summary = {
        "arm": ARM,
        "n_cases_audited": len(rows),
        "n_cases_unavailable": missing,
        "merge_relations_used": sorted(MERGE_RELATIONS),
        "endpoint_caveat": (
            "seats/hits are dc.match (legacy-chain) counts; PPV for "
            "clinical-complete is 56.48%. Headroom instrument, not an estimate."
        ),
        "scopes": aggregate(rows),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    with (args.out / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(summary["scopes"], indent=2, ensure_ascii=False, default=str))
    print(f"\nwrote {args.out}/summary.json and cases.jsonl ({len(rows)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
