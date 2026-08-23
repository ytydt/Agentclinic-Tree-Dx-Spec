#!/usr/bin/env python3
"""MCR_SELECTION_LAYER_AUDIT: what is still extractable from the frozen MultiStance payload.

Zero online calls.  Everything here is read off the frozen `aphhm_c_multistance_v1`
case stages plus the frozen clinical endpoint, so the whole audit is replayable.

The audit answers four questions that were each raised as a candidate intervention
after MCR_SELECTOR_TRUNCATION_V1 returned NO_GO:

  1. loss_anatomy   -- what kind of wrong label does the comparator pick when the
                       complete label is in the pool?  (Is it a granularity retreat,
                       which the family-vs-subtype prompt rule would explain, or a
                       different disease entirely?)
  2. evidence_skew  -- in those losses, how does the evidence attached to the correct
                       candidate compare with the evidence attached to the champion?
  3. positional     -- how much of the comparator's output is explained by "take the
                       first candidate in payload order"?
  4. rerank         -- can any ranking computable from the frozen payload beat the
                       generation order the payload already carries?  Selection is on
                       dev (mcr_v1 + mcr_v2); holdout (mcr_200b) is reported alongside
                       but must not be used to choose a ranking.

Cohort throughout is the pool-reachable slice: cases whose registry contains at least
one label the clinical panel scored `complete_equivalent`.  That is the only slice on
which the selection layer can possibly gain, and it is the same 167-case cohort
MCR_SELECTOR_TRUNCATION_V1 used.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "src", ROOT / "analysis" / "backbone_v1", ROOT / "analysis" / "mechanism_v2"):
    sys.path.insert(0, str(p))

import r5_lib as r5  # noqa: E402
from analysis.mechanism_v2.clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402

LOGS = ROOT / "logs" / "backbone_v1"
ARM = "aphhm_c_multistance_v1"
# (log dataset dir, slice key)
SLICES = (
    ("medcasereasoning", "mcr_v1"),
    ("medcasereasoning_v2", "mcr_v2"),
    ("medcasereasoning_200b", "mcr_200b"),
)
DEV = {"mcr_v1", "mcr_v2"}
OUT = ROOT / "analysis" / "mechanism_v2" / "results" / "MCR_SELECTION_LAYER_AUDIT"


# --- frozen payload ---------------------------------------------------------
def load_doc(log_ds: str, cid: str) -> dict:
    for key in (cid, cid.lstrip("0") or "0"):
        p = LOGS / log_ds / ARM / "case_stages" / f"{key}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def ordered_candidates(stages: Mapping[str, Any]) -> list[dict]:
    """The candidate sequence in payload order, exactly as the selector saw it.

    `ledger_rank` is generation order for this arm: the evidence matrix is disabled so
    every `score` is 0.0 and the rank degenerates to sorted `concept_id`.
    """
    reg = {
        c.get("concept_id"): c
        for c in (stages.get("registry") or [])
        if str(c.get("preferred_label") or "").strip()
    }
    order = [cid for cid in (stages.get("ledger_rank") or []) if cid in reg]
    return [reg[cid] for cid in order] if order else list(reg.values())


class Case:
    """One pool-reachable case with its frozen payload order and panel relations."""

    def __init__(self, sl: str, cid: str, gold: str, seq: Sequence[Mapping[str, Any]],
                 rels: Sequence[str | None], champion: str) -> None:
        self.slice = sl
        self.case_id = cid
        self.gold = gold
        self.seq = list(seq)
        self.rels = list(rels)
        self.labels = [str(c.get("preferred_label") or "") for c in seq]
        self.champion = champion

    @property
    def is_dev(self) -> bool:
        return self.slice in DEV

    @property
    def champion_relation(self) -> str | None:
        return self.rels[self.labels.index(self.champion)] if self.champion in self.labels else None

    @property
    def complete_index(self) -> int:
        return next(i for i, r in enumerate(self.rels) if r == COMPLETE)


def load_cohort(ce: ClinicalEndpoint) -> tuple[list[Case], int]:
    """Pool-reachable cases, plus the total number of MCR cases with a frozen payload."""
    gold = r5.load_gold()
    cases: list[Case] = []
    n_all = 0
    for log_ds, sl in SLICES:
        for (dataset, slice_key, cid), g in gold.items():
            if (dataset, slice_key) != ("mcr", sl):
                continue
            doc = load_doc(log_ds, cid)
            seq = ordered_candidates(doc.get("stages") or {})
            if not seq:
                continue
            n_all += 1
            rels = [ce.relation("mcr", sl, cid, str(c.get("preferred_label"))) for c in seq]
            if COMPLETE not in rels:
                continue
            cases.append(Case(sl, cid, g, seq, rels, str(doc.get("champion") or "")))
    cases.sort(key=lambda c: (c.slice, int(c.case_id) if c.case_id.isdigit() else 0))
    return cases, n_all


# --- candidate features (all free, read off the frozen registry) ------------
def n_for(c: Mapping[str, Any]) -> int:
    return len(c.get("support_spans") or [])


def n_against(c: Mapping[str, Any]) -> int:
    return len(c.get("contradict_spans") or [])


def n_stances(c: Mapping[str, Any]) -> int:
    return len([s for s in (c.get("stances") or []) if str(s)])


def specificity(c: Mapping[str, Any]) -> int:
    """In-pool granularity signal: narrower than others minus broader than others."""
    return len(c.get("narrower_than") or []) - len(c.get("broader_than") or [])


RANKINGS: dict[str, Callable[[Sequence[Mapping[str, Any]]], list[int]]] = {
    "gen_order": lambda s: list(range(len(s))),
    "stance_desc": lambda s: sorted(range(len(s)), key=lambda i: (-n_stances(s[i]), i)),
    "specificity_desc": lambda s: sorted(range(len(s)), key=lambda i: (-specificity(s[i]), i)),
    "no_against_first": lambda s: sorted(range(len(s)), key=lambda i: (n_against(s[i]), i)),
    "for_desc": lambda s: sorted(range(len(s)), key=lambda i: (-n_for(s[i]), i)),
    "for_minus_against_desc": lambda s: sorted(
        range(len(s)), key=lambda i: (-(n_for(s[i]) - n_against(s[i])), i)
    ),
    "stance_then_specificity": lambda s: sorted(
        range(len(s)), key=lambda i: (-n_stances(s[i]), -specificity(s[i]), i)
    ),
    "specificity_then_stance": lambda s: sorted(
        range(len(s)), key=lambda i: (-specificity(s[i]), -n_stances(s[i]), i)
    ),
    "specificity_no_against_gen": lambda s: sorted(
        range(len(s)), key=lambda i: (-specificity(s[i]), n_against(s[i]), i)
    ),
}


# --- the four questions -----------------------------------------------------
def loss_anatomy(cases: Sequence[Case]) -> dict:
    """Q1: relation of the frozen champion, and what the losses look like."""
    dist = Counter(c.champion_relation for c in cases)
    losses = [c for c in cases if c.champion_relation != COMPLETE]
    return {
        "n": len(cases),
        "champion_relation": {str(k): v for k, v in dist.most_common()},
        "n_losses": len(losses),
        "examples": [
            {
                "slice": c.slice,
                "case_id": c.case_id,
                "gold": c.gold,
                "champion": c.champion,
                "champion_relation": c.champion_relation,
                "complete_in_pool": c.labels[c.complete_index],
            }
            for c in losses[:20]
        ],
    }


def evidence_skew(cases: Sequence[Case]) -> dict:
    """Q2: correct candidate vs chosen champion, on the evidence the selector saw."""
    pairs = []
    for c in cases:
        if c.champion_relation == COMPLETE or c.champion not in c.labels:
            continue
        ci, wi = c.complete_index, c.labels.index(c.champion)
        pairs.append((c, c.seq[ci], c.seq[wi], ci, wi))
    n = len(pairs)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "mean_for_correct": sum(n_for(x[1]) for x in pairs) / n,
        "mean_for_champion": sum(n_for(x[2]) for x in pairs) / n,
        "correct_has_fewer_for": sum(1 for x in pairs if n_for(x[1]) < n_for(x[2])),
        "correct_has_equal_for": sum(1 for x in pairs if n_for(x[1]) == n_for(x[2])),
        "correct_has_zero_for": sum(1 for x in pairs if n_for(x[1]) == 0),
        "champion_has_zero_for": sum(1 for x in pairs if n_for(x[2]) == 0),
        "correct_has_against": sum(1 for x in pairs if n_against(x[1]) > 0),
        "champion_has_against": sum(1 for x in pairs if n_against(x[2]) > 0),
        "correct_against_champion_clean": sum(
            1 for x in pairs if n_against(x[1]) > 0 and n_against(x[2]) == 0
        ),
        "mean_position_correct": sum(x[3] for x in pairs) / n,
        "mean_position_champion": sum(x[4] for x in pairs) / n,
        "correct_later_than_champion": sum(1 for x in pairs if x[3] > x[4]),
    }


def positional(cases: Sequence[Case], n_all: int) -> dict:
    """Q3: the comparator against two free decision rules on the same payload."""
    n = len(cases)
    argmax_for = [
        c.rels[sorted(range(len(c.seq)), key=lambda i: (-n_for(c.seq[i]), i))[0]] for c in cases
    ]
    return {
        "n": n,
        "n_all_mcr": n_all,
        "selector_complete": sum(1 for c in cases if c.champion_relation == COMPLETE),
        "position0_complete": sum(1 for c in cases if c.rels[0] == COMPLETE),
        "argmax_for_complete": sum(1 for r in argmax_for if r == COMPLETE),
        "selector_agrees_with_position0": sum(1 for c in cases if c.champion == c.labels[0]),
        "champion_at_position0": sum(
            1 for c in cases if c.champion in c.labels and c.labels.index(c.champion) == 0
        ),
        "complete_index_histogram": dict(
            sorted(Counter(c.complete_index for c in cases).items())
        ),
        "mean_width": sum(len(c.seq) for c in cases) / n,
    }


def rerank(cases: Sequence[Case]) -> dict:
    """Q4: can any frozen-payload ranking beat generation order?  Chosen on dev only."""
    out: dict[str, Any] = {"n_dev": sum(1 for c in cases if c.is_dev), "rankings": {}}
    out["n_holdout"] = len(cases) - out["n_dev"]
    for name, fn in RANKINGS.items():
        rec = {"dev": {"n": 0, "top1": 0, "top3": 0}, "holdout": {"n": 0, "top1": 0, "top3": 0}}
        for c in cases:
            rels = [c.rels[i] for i in fn(c.seq)]
            side = rec["dev"] if c.is_dev else rec["holdout"]
            side["n"] += 1
            side["top1"] += int(rels[0] == COMPLETE)
            side["top3"] += int(COMPLETE in rels[:3])
        for side in rec.values():
            side["top1_rate"] = side["top1"] / max(side["n"], 1)
            side["top3_rate"] = side["top3"] / max(side["n"], 1)
        rec["total_top1"] = rec["dev"]["top1"] + rec["holdout"]["top1"]
        rec["total_top3"] = rec["dev"]["top3"] + rec["holdout"]["top3"]
        out["rankings"][name] = rec
    best = max(out["rankings"], key=lambda k: out["rankings"][k]["dev"]["top1"])
    out["best_on_dev"] = best
    out["gen_order_is_best_on_dev"] = best == "gen_order"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    ce = ClinicalEndpoint()
    cases, n_all = load_cohort(ce)
    result = {
        "cohort": {
            "n_pool_reachable": len(cases),
            "n_all_mcr": n_all,
            "dev": sum(1 for c in cases if c.is_dev),
            "holdout": sum(1 for c in cases if not c.is_dev),
        },
        "q1_loss_anatomy": loss_anatomy(cases),
        "q2_evidence_skew": evidence_skew(cases),
        "q3_positional": positional(cases, n_all),
        "q4_rerank": rerank(cases),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not args.quiet:
        c = result["cohort"]
        print(f"cohort: pool-reachable {c['n_pool_reachable']}/{c['n_all_mcr']} "
              f"(dev {c['dev']} / holdout {c['holdout']})\n")
        print("Q1 frozen champion relation on the reachable cohort:")
        for k, v in result["q1_loss_anatomy"]["champion_relation"].items():
            print(f"  {k:<32} {v}")
        e = result["q2_evidence_skew"]
        print(f"\nQ2 correct candidate vs champion, n={e['n']} losses:")
        print(f"  mean `for` spans         correct {e['mean_for_correct']:.2f}  "
              f"champion {e['mean_for_champion']:.2f}")
        print(f"  correct has fewer `for`  {e['correct_has_fewer_for']}/{e['n']}")
        print(f"  has `against`            correct {e['correct_has_against']}  "
              f"champion {e['champion_has_against']}")
        print(f"  mean payload position    correct {e['mean_position_correct']:.2f}  "
              f"champion {e['mean_position_champion']:.2f}")
        print(f"  correct sits later       {e['correct_later_than_champion']}/{e['n']}")
        p = result["q3_positional"]
        print(f"\nQ3 decision rules on the same payload, n={p['n']}:")
        print(f"  comparator (1 LLM call)  {p['selector_complete']}  "
              f"({p['selector_complete'] / p['n']:.3f})")
        print(f"  take payload position 0  {p['position0_complete']}  "
              f"({p['position0_complete'] / p['n']:.3f})   zero calls")
        print(f"  take most `for` spans    {p['argmax_for_complete']}  "
              f"({p['argmax_for_complete'] / p['n']:.3f})   zero calls")
        print(f"  comparator == position 0 {p['selector_agrees_with_position0']}/{p['n']}")
        r = result["q4_rerank"]
        print(f"\nQ4 rankings computable from the frozen payload "
              f"(dev {r['n_dev']} / holdout {r['n_holdout']}):")
        print(f"  {'ranking':<28} {'dev top1':>10} {'dev top3':>10} "
              f"{'hold top1':>10} {'hold top3':>10}")
        for name, rec in sorted(
            r["rankings"].items(), key=lambda kv: -kv[1]["dev"]["top1"]
        ):
            print(f"  {name:<28} {rec['dev']['top1']:>10} {rec['dev']['top3']:>10} "
                  f"{rec['holdout']['top1']:>10} {rec['holdout']['top3']:>10}")
        print(f"\n  best on dev: {r['best_on_dev']}  "
              f"(generation order wins: {r['gen_order_is_best_on_dev']})")
        print(f"\nwrote {args.out / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
