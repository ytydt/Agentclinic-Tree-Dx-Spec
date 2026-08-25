#!/usr/bin/env python3
"""Cache a normalized-input representation of the MCR vignettes, then ask whether
it can touch the cause the cluster line actually died of.

Every cluster refutation so far ran on generators that read the raw vignette. The
older APHHM full-tree pipeline has two components those runs never used:

* `VignetteParser` -- vignette -> structured evidence items (frozen artifacts
  already exist for `mcr_val_seq100_v1`, so this stage costs zero calls).
* `FindingNormalizer` -- deterministic `alias -> LOINC -> reference range ->
  direction -> loinc2hpo -> HPO`, turning "Potassium: 6.2 mEq/L" into
  `Hyperkalemia (H)` and a normal value into explicit rule-out targets.

`CLUSTER_SIGNAL_ANATOMY` located the failure precisely: the cluster signal is a
coarse projection of generation order, undecided on 42.7% of the decisive
within-case comparisons. So the question here is not "is normalization nicer" but
the narrow one: **does normalization raise the resolution of the observation
grouping, and over how much of the evidence?** Three of its effects could:

    split       compound strings become atoms  -> finer grouping
    canonical   different surface forms collapse to one HPO term -> cleaner identity
    negation    normal values become explicit rule-outs -> a signal the raw
                pipeline carries only as unlabelled text

Stages:

    build   normalize the frozen parses, write `normalized_cache.json`  (0 calls)
    gate    yield, resolution deltas, and the ceiling they imply        (0 calls)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agentclinic_tree_dx.knowledge.finding_normalizer import (  # noqa: E402
    FindingNormalizer,
    NormalizedFinding,
)

OUT = ROOT / "analysis/mechanism_v2/results/NORMALIZED_INPUT_PROBE"
KNOW = ROOT / "data/knowledge_raw"

# Both MCR slices have frozen parses, so the whole G1 cohort (67 cases spanning
# mcr_v1 + mcr_v2) is reachable without re-issuing a parser call. Several arms
# froze a parse per slice; the `fidelity` check in `build` confirms they agree
# verbatim, so which arm supplies it is immaterial.
SLICES = {
    "mcr_v1": ("medcasereasoning_mcr_val_seq100_v1", "medcasereasoning"),
    "mcr_v2": ("medcasereasoning_mcr_val_seq100_v2", "medcasereasoning_v2"),
}
PREFERRED_ARMS = ("aphhm_clean_v1", "compat_synonym_v1")

AGE_RE = re.compile(r"(\d{1,3})\s*[- ]?year[- ]?old", re.I)
FEMALE_RE = re.compile(r"\b(woman|female|girl|she|her)\b", re.I)
MALE_RE = re.compile(r"\b(man|male|boy|he|his)\b", re.I)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalizer() -> FindingNormalizer:
    return FindingNormalizer(
        KNOW / "lab_reference_ranges.json",
        KNOW / "loinc2hpo_annotations.json",
        KNOW / "unit_conversions.json",
    )


def demographics(vignette: str) -> tuple[float | None, str | None]:
    """Age and sex, which the reference ranges need to pick the right interval."""
    age = None
    m = AGE_RE.search(vignette or "")
    if m:
        try:
            age = float(m.group(1))
        except ValueError:
            age = None
    head = (vignette or "")[:400]
    female, male = bool(FEMALE_RE.search(head)), bool(MALE_RE.search(head))
    sex = "female" if female and not male else "male" if male and not female else None
    return age, sex


def as_dict(row: NormalizedFinding) -> dict[str, Any]:
    return {
        "hpo_term": row.hpo_term,
        "hpo_id": row.hpo_id,
        "direction": row.direction,
        "confidence": row.confidence,
        "source": row.source,
        "test_name": row.test_name,
        "value": row.value,
        "unit": row.unit,
        "negated_hpo_terms": list(row.negated_hpo_terms or []),
    }


def load_parses(slice_name: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Frozen parses for one slice, plus a check that the arms agree verbatim."""
    log_dir = SLICES[slice_name][0]
    by_arm: dict[str, dict[str, Any]] = {}
    for path in sorted(ROOT.glob(f"logs/{log_dir}/*/frozen/vignette_parser_frozen.json")):
        doc = json.loads(path.read_text())
        by_arm[path.parts[-3]] = {str(c["case_id"]): c for c in (doc.get("cases") or [])}
    if not by_arm:
        raise SystemExit(f"no frozen parse under logs/{log_dir}")
    chosen = next((a for a in PREFERRED_ARMS if a in by_arm), sorted(by_arm)[0])
    base = by_arm[chosen]

    def sig(case: dict[str, Any]) -> list[str]:
        return [str(e.get("content") or "") for e in (case.get("evidence_items") or [])]

    identical = {
        arm: sum(
            1
            for cid, case in base.items()
            if cid in other and sig(other[cid]) == sig(case)
        )
        for arm, other in by_arm.items()
    }
    return base, {
        "arm_used": chosen,
        "arms_found": sorted(by_arm),
        "cases_in_chosen_arm": len(base),
        "cases_identical_to_chosen": identical,
        "arms_are_interchangeable": all(v == len(base) for v in identical.values()),
    }


# --------------------------------------------------------------------------
# stage: build
# --------------------------------------------------------------------------


def stage_build(_: argparse.Namespace) -> int:
    fn = normalizer()
    cases: dict[str, Any] = {}
    fidelity: dict[str, Any] = {}

    for slice_name in SLICES:
        parses, fidelity[slice_name] = load_parses(slice_name)
        for cid, case in sorted(parses.items(), key=lambda kv: int(kv[0])):
            vignette = str(case.get("vignette") or "")
            age, sex = demographics(vignette)
            items = []
            for ev in case.get("evidence_items") or []:
                text = str(ev.get("content") or "")
                rows = fn.normalize_multi(text, gender=sex, age_years=age)
                items.append(
                    {
                        "id": str(ev.get("id") or ""),
                        "kind": str(ev.get("kind") or ""),
                        "text": text,
                        "normalized": [as_dict(r) for r in rows],
                    }
                )
            cases[f"{slice_name}/{cid}"] = {
                "slice": slice_name,
                "case_id": cid,
                "age_years": age,
                "sex": sex,
                "n_evidence_items": len(items),
                "items": items,
            }

    payload = {
        "artifact": "NORMALIZED_INPUT_CACHE",
        "created_at": utcnow(),
        "slices": sorted(SLICES),
        "calls": 0,
        "provenance": {
            "parser": "frozen VignetteParser output (no calls re-issued)",
            "normalizer": "FindingNormalizer, deterministic",
            "assets": [
                "data/knowledge_raw/lab_reference_ranges.json",
                "data/knowledge_raw/loinc2hpo_annotations.json",
                "data/knowledge_raw/unit_conversions.json",
            ],
        },
        "parse_fidelity": fidelity,
        "n_cases": len(cases),
        "cases": cases,
    }
    write_json(OUT / "normalized_cache.json", payload)
    n_items = sum(c["n_evidence_items"] for c in cases.values())
    n_norm = sum(
        1 for c in cases.values() for it in c["items"] if it["normalized"]
    )
    print(
        f"build: cases={len(cases)} items={n_items} normalized={n_norm} "
        f"({n_norm / max(n_items, 1):.4f}) arms_interchangeable="
        f"{ {k: v['arms_are_interchangeable'] for k, v in fidelity.items()} }"
    )
    return 0


# --------------------------------------------------------------------------
# stage: gate
# --------------------------------------------------------------------------


def stage_gate(_: argparse.Namespace) -> int:
    cache = json.loads((OUT / "normalized_cache.json").read_text())
    cases = cache["cases"]

    n_items = n_norm = n_term = n_multi = n_negation = 0
    atoms_from_multi = 0
    kinds = Counter()
    kinds_norm = Counter()
    directions = Counter()
    per_case_collapse: list[float] = []
    per_case_atom_delta: list[float] = []
    confidences = Counter()

    for case in cases.values():
        term_to_items: dict[str, set[str]] = defaultdict(set)
        case_items = case["items"]
        case_atoms = 0
        for it in case_items:
            n_items += 1
            kinds[it["kind"]] += 1
            rows = it["normalized"]
            if not rows:
                continue
            n_norm += 1
            # A parsed number is not yet a phenotype: tests with no reference range
            # (CA-125, say) come back with hpo_term None / direction unknown. Only
            # the term-bearing subset is a canonical name the pipeline could consume.
            n_term += int(any(r["hpo_term"] for r in rows))
            kinds_norm[it["kind"]] += 1
            case_atoms += len(rows)
            if len(rows) > 1:
                n_multi += 1
                atoms_from_multi += len(rows)
            for r in rows:
                directions[r["direction"]] += 1
                confidences[r["confidence"]] += 1
                if r["negated_hpo_terms"]:
                    n_negation += 1
                if r["hpo_term"]:
                    term_to_items[r["hpo_term"]].add(it["id"])
        # Canonicalisation only helps where >1 distinct raw item lands on one term.
        collapsed = sum(len(v) - 1 for v in term_to_items.values() if len(v) > 1)
        per_case_collapse.append(collapsed)
        normalized_items = sum(1 for it in case_items if it["normalized"])
        per_case_atom_delta.append(case_atoms - normalized_items)

    yield_rate = n_norm / max(n_items, 1)
    term_rate = n_term / max(n_items, 1)
    result = {
        "experiment": "NORMALIZED_INPUT_RESOLUTION_GATE",
        "created_at": utcnow(),
        "calls": 0,
        "n_cases": len(cases),
        "n_evidence_items": n_items,
        "coverage": {
            "items_parsed": n_norm,
            "parse_rate": round(yield_rate, 4),
            "items_with_hpo_term": n_term,
            "hpo_term_rate": round(term_rate, 4),
            "parsed_but_no_phenotype": n_norm - n_term,
            "items_by_kind": dict(kinds),
            "normalized_by_kind": dict(kinds_norm),
        },
        "resolution_effects": {
            "compound_items_split": n_multi,
            "atoms_from_split_items": atoms_from_multi,
            "mean_atom_gain_per_case": round(mean(per_case_atom_delta), 4),
            "mean_canonical_collapses_per_case": round(mean(per_case_collapse), 4),
            "items_with_explicit_ruleouts": n_negation,
        },
        "direction_histogram": dict(directions),
        "confidence_histogram": dict(confidences),
        # The signal died on a 0.4273 within-case tie rate. Normalization can only
        # act on the evidence it actually rewrites, so its yield is a hard ceiling
        # on how much of that tie mass it could ever redistribute.
        "ceiling_on_tie_rate_repair": {
            "anatomy_tie_rate_to_beat": 0.4273,
            "share_of_evidence_rewritten_to_a_canonical_name": round(term_rate, 4),
            "verdict": (
                "cannot plausibly repair"
                if term_rate < 0.25
                else "worth a preregistered re-test"
            ),
        },
    }
    write_json(OUT / "gate.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------
# stage: enrich
# --------------------------------------------------------------------------

MULTISTANCE = "logs/backbone_v1/{dataset}/aphhm_c_multistance_v1/case_stages/*.json"


def stage_enrich(_: argparse.Namespace) -> int:
    """Is normalizable evidence *disproportionately decisive*?

    A low yield would not settle the question on its own: laboratory findings are
    exactly the high-specificity ones, so 11% of the evidence could still carry
    most of the discriminative weight. This runs the normalizer over the frozen
    multistance fact ledger -- the same structure the cluster signal was computed
    on -- and asks whether normalizable facts are enriched in the support of
    clinically complete candidates relative to incomplete ones.
    """
    from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: PLC0415

    fn = normalizer()
    endpoint = ClinicalEndpoint()
    endpoint.drop_conflicts()

    fact_total = fact_norm = 0
    spec_norm: dict[str, list[int]] = defaultdict(list)
    modality_norm: dict[str, list[int]] = defaultdict(list)
    # Support-side shares, per candidate, split by clinical verdict.
    shares: dict[str, list[float]] = {"complete": [], "incomplete": []}
    groups_norm: dict[str, list[int]] = {"complete": [], "incomplete": []}
    judged = 0

    paths = [
        (sl, p)
        for sl, (_, dataset) in SLICES.items()
        for p in sorted(ROOT.glob(MULTISTANCE.format(dataset=dataset)))
    ]
    for slice_name, path in paths:
        doc = json.loads(path.read_text())
        stages = doc.get("stages") or {}
        cid = path.stem
        norm_of: dict[str, bool] = {}
        group_of: dict[str, str] = {}
        for fact in stages.get("facts") or []:
            fid = str(fact.get("fact_id") or "")
            span = str(fact.get("raw_span") or "")
            # Same tightening as `gate`: a parsed number without a phenotype is not
            # a canonical name, so it must not count as normalized here either.
            hit = any(r.hpo_term for r in fn.normalize_multi(span))
            norm_of[fid] = hit
            group_of[fid] = str(fact.get("correlation_group") or "")
            fact_total += 1
            fact_norm += int(hit)
            spec_norm[str(fact.get("specificity") or "?")].append(int(hit))
            modality_norm[str(fact.get("modality") or "?")].append(int(hit))

        for cand in stages.get("registry") or []:
            label = str(cand.get("preferred_label") or "")
            rel = endpoint.relation("mcr", slice_name, cid, label)
            if rel is None:
                continue
            judged += 1
            fids = [str(x) for x in (cand.get("support_fact_ids") or []) if x in norm_of]
            if not fids:
                continue
            bucket = "complete" if rel == COMPLETE else "incomplete"
            shares[bucket].append(sum(norm_of[f] for f in fids) / len(fids))
            groups_norm[bucket].append(
                len({group_of[f] for f in fids if norm_of[f] and group_of[f]})
            )

    def rate(rows: dict[str, list[int]]) -> dict[str, Any]:
        return {
            k: {"n": len(v), "normalized": sum(v), "rate": round(sum(v) / len(v), 4)}
            for k, v in sorted(rows.items(), key=lambda kv: -len(kv[1]))
            if v
        }

    result = {
        "experiment": "NORMALIZED_EVIDENCE_ENRICHMENT",
        "created_at": utcnow(),
        "calls": 0,
        "population": "mcr_v1 + mcr_v2, aphhm_c_multistance_v1 frozen fact ledger",
        "facts": {
            "n": fact_total,
            "normalized": fact_norm,
            "rate": round(fact_norm / max(fact_total, 1), 4),
        },
        "by_specificity": rate(spec_norm),
        "by_modality": rate(modality_norm),
        "candidates_judged": judged,
        "normalizable_support_share": {
            k: {
                "n_candidates": len(v),
                "mean_share": round(mean(v), 4) if v else None,
                "mean_normalizable_groups": (
                    round(mean(groups_norm[k]), 4) if groups_norm[k] else None
                ),
            }
            for k, v in shares.items()
        },
        "enrichment_complete_minus_incomplete": (
            round(mean(shares["complete"]) - mean(shares["incomplete"]), 4)
            if shares["complete"] and shares["incomplete"]
            else None
        ),
    }
    write_json(OUT / "enrichment.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="stage", required=True)
    sub.add_parser("build").set_defaults(fn=stage_build)
    sub.add_parser("gate").set_defaults(fn=stage_gate)
    sub.add_parser("enrich").set_defaults(fn=stage_enrich)
    args = ap.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
