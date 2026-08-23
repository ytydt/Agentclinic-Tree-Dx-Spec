#!/usr/bin/env python3
"""Offline anatomy of MultiStance's `final_drop`: what would actually fix it?

No LLM call. Two independent questions, one per benchmark family, both on the
frozen `aphhm_c_multistance_v1` case_stages.

B (DA): the finals loss is dominated by lexical kin (45/72). Is that loss
reachable by *append-only modifier completion*? A case is reachable only if some
pool candidate is a strict content-token subset of the reference, so the
reference can be produced by adding modifiers rather than by swapping objects.
Cases where the reference is instead a subset of the champion are the opposite
defect (over-specification) and completion cannot help them.

C (MCR): the finals loss is dominated by unrelated objects (24/41). A
candidate-pair counterfactual discriminator can only help if the reference owns
evidence no competitor shares. `evidence_discriminability` measures exactly that
on the frozen support spans, so the question is decidable offline: compare the
reference's discriminability in lost finals against won finals. The tournament
prompt also states that "a candidate with a strong `against` entry is usually
wrong", so the reference's own `contradict_spans` are counted as a second,
independent kill channel.

Every axis judgement here is a deterministic lexical proxy over frozen text. It
localizes mechanism; it is not a clinical annotation and cannot replace one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src", _ROOT / "analysis" / "backbone_v1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402
import r6_lib as r6  # noqa: E402

from analysis.mechanism_v2.core_regroup_headroom import (  # noqa: E402
    content_tokens,
    core_relation,
    shortlist_of,
)

DEFAULT_OUT = _ROOT / "analysis" / "mechanism_v2" / "results" / "FINALS_LOSS_ANATOMY"
ARM = "multistance"

# Markers for the four axes whose completion hallucination rate was 0.1862 in
# SLOT_YIELD's M2 gate. If none of them fires on the tokens the reference adds,
# the addition is plausibly on a surface axis (0.0587). Kept deliberately small:
# a wide "surface" lexicon would beg the question.
INFERENTIAL_MARKERS = {
    "temporal_evolution": {
        "acute", "chronic", "subacute", "recurrent", "relapsing", "persistent",
        "transient", "progressive", "early", "late", "advanced", "ancient",
        "congenital", "acquired", "chronicity", "longstanding", "evolving",
        "healed", "healing", "residual", "sequelae", "old", "new", "prior",
    },
    "etiology": {
        "caused", "due", "induced", "related", "associated", "secondary",
        "idiopathic", "iatrogenic", "drug", "radiation", "pressure", "traumatic",
        "postoperative", "post", "infectious", "autoimmune", "paraneoplastic",
        "hereditary", "familial", "genetic", "toxic", "ischemic", "embolic",
    },
    "complication": {
        "complicated", "complication", "perforation", "hemorrhage", "haemorrhage",
        "rupture", "failure", "injury", "obstruction", "necrosis", "abscess",
        "sepsis", "shock", "crisis", "compression", "invasion", "metastasis",
        "metastatic", "involvement",
    },
    "scope_distribution": {
        "disseminated", "localized", "localised", "generalized", "generalised",
        "limited", "systemic", "focal", "multifocal", "segmental", "diffuse",
        "extensive", "widespread", "unilateral", "bilateral", "isolated",
    },
}
_COMPOSITE = re.compile(r"\b(with|and|plus|complicated by|secondary to|due to)\b", re.I)


def added_tokens(base: str, target: str) -> tuple[str, ...]:
    tb, tt = set(content_tokens(base)), content_tokens(target)
    return tuple(t for t in tt if t not in tb)


def axis_markers(tokens: tuple[str, ...]) -> list[str]:
    hits = []
    for axis, lex in INFERENTIAL_MARKERS.items():
        if any(t in lex for t in tokens):
            hits.append(axis)
    return sorted(hits)


def token_subset(a: str, b: str) -> bool:
    """True if a's content tokens are a proper subset of b's."""
    sa, sb = set(content_tokens(a)), set(content_tokens(b))
    return bool(sa) and bool(sb) and sa < sb


def token_jaccard(a: str, b: str) -> float:
    sa, sb = set(content_tokens(a)), set(content_tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _cands_for_disc(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"label": c["label"], "for": c.get("support_spans") or []} for c in cands]


def collect() -> list[dict[str, Any]]:
    gold = r5.load_gold()
    rows: list[dict[str, Any]] = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, ARM) is None:
            continue
        for cid in sorted(
            [c for (dd, ss, c) in gold if dd == dkey and ss == sl],
            key=lambda x: (len(x), x),
        ):
            doc = r6.load_raw_doc(log_ds, ARM, cid)
            if not doc:
                continue
            g = gold[(dkey, sl, cid)]
            rnd = r6.multistance_loss_round(doc, g)
            if rnd not in ("final_drop", "ok"):
                continue
            stages = doc.get("stages") or {}
            sel = stages.get("frontier_selector") or {}
            cands = shortlist_of(doc)
            if not cands:
                continue
            champ = str(sel.get("champion") or doc.get("champion") or "")
            fin_labels = [
                str(f.get("label") or "") if isinstance(f, dict) else str(f)
                for f in (sel.get("finalists") or [])
            ]
            fin_labels = [f for f in fin_labels if f]
            gold_members = [c for c in cands if dc.match(c["label"], g)]
            if not gold_members:
                continue
            # the pool label that legacy-chain credits as the reference
            gm = min(gold_members, key=lambda c: c["rank"])
            disc_pool = _cands_for_disc(cands)
            rows.append(
                {
                    "dataset": dkey,
                    "slice": sl,
                    "case_id": cid,
                    "loss_round": rnd,
                    "gold": g,
                    "gold_pool_label": gm["label"],
                    "gold_is_exact_pool_label": gm["label"].strip().lower()
                    == g.strip().lower(),
                    "champion": champ,
                    "champion_vs_gold": core_relation(champ, g),
                    "n_finalists": len(fin_labels),
                    # --- B: is the reference reachable by adding modifiers? ---
                    "champion_subset_of_gold": token_subset(champ, g),
                    "gold_subset_of_champion": token_subset(g, champ),
                    # Accounting checks on the loss itself, not on the model.
                    # A credited pool label that is a proper subset of the
                    # champion means legacy-chain scored a bare parent as the
                    # reference and penalized a *more* specific answer.
                    "credited_label_subset_of_champion": token_subset(
                        gm["label"], champ
                    ),
                    "champion_gold_jaccard": round(token_jaccard(champ, g), 3),
                    "finalist_parents": [f for f in fin_labels if token_subset(f, g)],
                    "finalist_parents_nonscoring": [
                        f
                        for f in fin_labels
                        if token_subset(f, g) and not dc.match(f, g)
                    ],
                    "pool_subset_of_gold": [
                        c["label"] for c in cands if token_subset(c["label"], g)
                    ],
                    "tokens_gold_adds_over_champion": added_tokens(champ, g),
                    "tokens_gold_adds_over_pool_label": added_tokens(gm["label"], g),
                    # --- C: is there reference-unique evidence to point at? ---
                    "gold_disc": r6.evidence_discriminability(disc_pool, gm["label"]),
                    "champ_disc": r6.evidence_discriminability(disc_pool, champ),
                    "gold_n_support": len(gm.get("support_spans") or []),
                    "gold_n_contradict": len(
                        [
                            s
                            for s in (
                                next(
                                    (
                                        e.get("contradict_spans")
                                        for e in (stages.get("registry") or [])
                                        if str(e.get("preferred_label") or "")
                                        == gm["label"]
                                    ),
                                    [],
                                )
                                or []
                            )
                            if str(s).strip()
                        ]
                    ),
                    "selector_why": str(sel.get("why") or "")[:400],
                }
            )
    return rows


def _mean(xs: list[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def section_b(rows: list[dict]) -> dict[str, Any]:
    """DA finals loss: how much of it is append-only reachable?"""
    out: dict[str, Any] = {}
    for dkey in ("da", "mcr"):
        fd = [r for r in rows if r["dataset"] == dkey and r["loss_round"] == "final_drop"]
        kin = [r for r in fd if r["champion_vs_gold"] != "none"]
        reachable = [r for r in kin if r["pool_subset_of_gold"]]
        champ_parent = [r for r in kin if r["champion_subset_of_gold"]]
        over_specific = [r for r in kin if r["gold_subset_of_champion"]]
        marker_hits = Counter()
        for r in reachable:
            hits = axis_markers(r["tokens_gold_adds_over_pool_label"])
            marker_hits[",".join(hits) if hits else "none_surface_plausible"] += 1
        composite = sum(1 for r in reachable if _COMPOSITE.search(r["gold"]))
        surface = [
            r for r in reachable if not axis_markers(r["tokens_gold_adds_over_pool_label"])
        ]
        out[dkey] = {
            "final_drop_n": len(fd),
            "kin_loss_n": len(kin),
            "kin_loss_with_a_pool_subset_of_gold": len(reachable),
            "kin_loss_champion_is_parent_of_gold": len(champ_parent),
            "kin_loss_gold_is_parent_of_champion": len(over_specific),
            "reachable_added_token_axis_markers": dict(marker_hits),
            "reachable_gold_is_composite_label": composite,
            # The append-only target: a surface-axis addition applied to the
            # candidate that actually won. Anything outside it needs the
            # completed non-champion to *also* overturn the final.
            "surface_axis_reachable": len(surface),
            "surface_axis_reachable_and_champion_is_the_parent": sum(
                1 for r in surface if r["champion_subset_of_gold"]
            ),
            "kin_loss_paraphrase_suspect_jaccard_ge_0_5": sum(
                1 for r in kin if r["champion_gold_jaccard"] >= 0.5
            ),
            "legacy_chain_pool_label_is_not_the_gold_string": sum(
                1 for r in fd if not r["gold_is_exact_pool_label"]
            ),
        }
    return out


def section_b_finals_ladder(rows: list[dict]) -> dict[str, Any]:
    """Ceiling ladder for a completion that acts on the finals seats.

    The design under test completes the 2-3 finalists, not the champion, so the
    target is a finalist that is a coarse parent of the reference. The ladder
    exists because two filters remove almost all of it: a finalist that already
    satisfies `dc.match` scores today, so completing it changes no score, and a
    completion whose added tokens hit an inferential-axis marker sits on the
    0.1862 hallucination rate rather than the 0.0587 one.
    """
    out: dict[str, Any] = {}
    for dkey in ("da", "mcr"):
        fd = [r for r in rows if r["dataset"] == dkey and r["loss_round"] == "final_drop"]
        any_parent = [r for r in fd if r["finalist_parents"]]
        nonscoring = [r for r in fd if r["finalist_parents_nonscoring"]]
        surface, le2 = [], []
        for r in nonscoring:
            adds = [
                added_tokens(p, r["gold"])
                for p in r["finalist_parents_nonscoring"]
            ]
            adds = [a for a in adds if not axis_markers(a)]
            if not adds:
                continue
            surface.append(r)
            if min(len(a) for a in adds) <= 2:
                le2.append(r)
        out[dkey] = {
            "final_drop_n": len(fd),
            "a_finalist_is_a_parent_of_the_reference": len(any_parent),
            "...and_it_does_not_already_score": len(nonscoring),
            "...and_the_added_tokens_are_surface_axis": len(surface),
            "...and_at_most_two_tokens_are_added": len(le2),
        }
    return out


def section_c(rows: list[dict]) -> dict[str, Any]:
    """MCR finals loss: is there reference-unique evidence the comparator ignored?"""
    out: dict[str, Any] = {}
    for dkey in ("mcr", "da"):
        sub = [r for r in rows if r["dataset"] == dkey]
        strata = {
            "ok": [r for r in sub if r["loss_round"] == "ok"],
            "final_drop_unrelated": [
                r
                for r in sub
                if r["loss_round"] == "final_drop" and r["champion_vs_gold"] == "none"
            ],
            "final_drop_kin": [
                r
                for r in sub
                if r["loss_round"] == "final_drop" and r["champion_vs_gold"] != "none"
            ],
        }
        block = {}
        for name, rs in strata.items():
            if not rs:
                continue
            block[name] = {
                "n": len(rs),
                "gold_disc_mean": _mean([r["gold_disc"] for r in rs]),
                "champ_disc_mean": _mean([r["champ_disc"] for r in rs]),
                "gold_disc_is_1_0": sum(1 for r in rs if r["gold_disc"] == 1.0),
                "gold_disc_is_0_0": sum(1 for r in rs if r["gold_disc"] == 0.0),
                "gold_has_contradict_span": sum(
                    1 for r in rs if r["gold_n_contradict"] > 0
                ),
                "gold_n_support_mean": _mean([float(r["gold_n_support"]) for r in rs]),
                "champ_disc_gt_gold_disc": sum(
                    1
                    for r in rs
                    if r["champ_disc"] is not None
                    and r["gold_disc"] is not None
                    and r["champ_disc"] > r["gold_disc"]
                ),
                "credited_label_subset_of_champion": sum(
                    1 for r in rs if r["credited_label_subset_of_champion"]
                ),
            }
        out[dkey] = block
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    rows = collect()
    summary = {
        "arm": ARM,
        "n_rows": len(rows),
        "scope": "cases where the reference reached the finals (ok + final_drop)",
        "caveats": [
            "dc.match is legacy-chain; the credited pool label may be a parent "
            "of the true reference, so a finals win is not clinical-complete.",
            "axis markers are a deterministic lexical proxy, not an annotation.",
            "evidence_discriminability is computed over frozen support spans "
            "only; a span shared by two candidates may still be decisive.",
        ],
        "B_da_completion_reachability": section_b(rows),
        "B_finals_layer_ceiling_ladder": section_b_finals_ladder(rows),
        "C_evidence_discriminability": section_c(rows),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    with (args.out / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(summary["B_da_completion_reachability"], indent=2, ensure_ascii=False))
    print(json.dumps(summary["C_evidence_discriminability"], indent=2, ensure_ascii=False))
    print(f"\nwrote {args.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
