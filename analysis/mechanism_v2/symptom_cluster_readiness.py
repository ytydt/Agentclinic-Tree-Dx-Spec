#!/usr/bin/env python3
"""Zero-call readiness audit for symptom-cluster evidence (症状集群.md).

Answers nine questions against frozen artefacts only. No LLM calls, no panel.

  Q1  Does the fact schema already carry a cluster slot, and is it populated?
  Q2  What are the cluster sizes, and do they mean redundancy or conjunction?
  Q3  Is the named-composite lookup route (SNOMED syndrome) viable?
  Q4  Is ontology grounding (HPO) good enough to key clusters on?
  Q5  Do knowledge-side dependence edges (HPOA) cover this cohort?
  Q6  Can candidate evidence be re-expressed in cluster units offline?
  Q7  Is the bundling no-op universal, or arm-specific? (collapse3c/forest/IMPC)
  Q8  Where bundling IS live, does it help or hurt the clinical endpoint?
  Q9  Step 0 probe: does cluster-unit evidence beat span-count as a ranking?
  Q10 Do the training-free grounding fixes from the SOTA survey actually help?
  Q11 Where does pool recall come from, per stance? (gate scoping)

Usage:  python3 analysis/mechanism_v2/symptom_cluster_readiness.py
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "analysis" / "mechanism_v2"))

KR = ROOT / "data" / "knowledge_raw"
ARM = "logs/backbone_v1/medcasereasoning*/aphhm_c_multistance_v1/case_stages/*.json"
SUBSETS = ROOT / "data" / "benchmarks" / "medcasereasoning" / "subsets"

# score_concept constants, mirrored from aphhm_c.py so the recomputation in Q8
# is exact rather than approximate.
RELIABILITY_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4}
GROUP_CLIP = 3
SLICE_OF_DIR = {
    "medcasereasoning": "mcr_v1",
    "medcasereasoning_v2": "mcr_v2",
    "medcasereasoning_200b": "mcr_200b",
}


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(text).lower()).split())


def load_cases() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(ROOT.glob(ARM))]


def q1_q2_clusters(cases: list[dict]) -> dict:
    """Population and shape of the existing correlation_group slot."""
    filled = Counter()
    sizes: Counter[int] = Counter()
    groups_per_case = []
    for case in cases:
        facts = (case.get("stages") or {}).get("facts") or []
        if not facts:
            continue
        buckets: dict[str, int] = {}
        for fact in facts:
            key = str(fact.get("correlation_group") or "").strip()
            filled[bool(key)] += 1
            buckets[key] = buckets.get(key, 0) + 1
        groups_per_case.append(len(buckets))
        for count in buckets.values():
            sizes[count] += 1
    total_groups = sum(sizes.values())
    return {
        "cases": len(groups_per_case),
        "facts": sum(filled.values()),
        "correlation_group_filled": filled[True],
        "correlation_group_empty": filled[False],
        "groups": total_groups,
        "groups_per_case_mean": round(st.mean(groups_per_case), 2),
        "size_histogram": dict(sorted(sizes.items())),
        "share_size_ge_2": round(
            sum(v for k, v in sizes.items() if k >= 2) / total_groups, 4),
        "share_size_2_or_3": round(
            (sizes.get(2, 0) + sizes.get(3, 0)) / total_groups, 4),
    }


def q3_named_composite(cases: list[dict]) -> dict:
    """Can 2-3 finding conjunctions be recovered by SNOMED syndrome lookup?"""
    from agentclinic_tree_dx.knowledge.compound_finding import (
        SyndromeResolver, represent)

    concepts = json.loads((KR / "snomed_concepts.json").read_text())
    term_index = json.loads((KR / "snomed_term_index.json").read_text())
    entries: dict[str, list[dict]] = {}
    for term, ids in term_index.items():
        if "syndrome" not in term.lower():
            continue
        for cid in ids[:1]:
            concept = concepts.get(str(cid), {})
            if "disorder" in str(concept.get("tag", "")).lower():
                entries.setdefault(" ".join(term.lower().split()), []).append({
                    "concept_id": str(cid),
                    "label": concept.get("preferred", term),
                    "system": "SNOMED_CT",
                    "provenance": str(KR / "snomed_concepts.json"),
                    "entailed": True,
                    "confidence": 1.0,
                })
    resolver = SyndromeResolver(entries)

    spans = [
        str(fact.get("raw_span") or "")
        for case in cases
        for fact in ((case.get("stages") or {}).get("facts") or [])
    ]
    atoms: Counter[int] = Counter()
    resolved = []
    for span in spans:
        rep = represent(span, "dual", resolver)
        atoms[len(rep.atoms)] += 1
        if rep.syndrome:
            resolved.append((span, rep.syndrome.label))
    return {
        "snomed_term_index_terms": len(term_index),
        "syndrome_dictionary_entries": len(entries),
        "facts": len(spans),
        "syndrome_resolved": len(resolved),
        "syndrome_resolved_rate": round(len(resolved) / len(spans), 4),
        "atom_histogram": dict(sorted(atoms.items())),
        "surface_compound_rate": round(
            sum(v for k, v in atoms.items() if k > 1) / len(spans), 4),
        "resolved_examples": resolved[:5],
    }


def q4_grounding(cases: list[dict], n_samples: int = 12) -> dict:
    """Is HPO grounding reliable enough to key clusters on?"""
    import random

    from agentclinic_tree_dx.knowledge.hpo_index import HPOIndex

    index = HPOIndex.from_obo(KR / "hp.obo")
    facts = [
        fact
        for case in cases
        for fact in ((case.get("stages") or {}).get("facts") or [])
    ]
    spans = [str(f.get("raw_span") or "") for f in facts]
    exact = [s for s in spans if index.resolve(s)]
    fuzzy_only = [s for s in spans if not index.resolve(s) and index.resolve_fuzzy(s)]

    random.seed(0)
    sample = random.sample(fuzzy_only, min(n_samples, len(fuzzy_only)))
    audit = []
    for span in sample:
        hpo_id = index.resolve_fuzzy(span)
        audit.append({
            "span": span[:90],
            "hpo": index.get_name(hpo_id) if hpo_id else None,
            "hpo_id": hpo_id,
        })
    return {
        "hpo_terms": index.term_count,
        "hpo_synonyms": index.synonym_count,
        "facts": len(spans),
        "exact_grounded": len(exact),
        "exact_rate": round(len(exact) / len(spans), 4),
        "exact_plus_fuzzy_rate": round(
            (len(exact) + len(fuzzy_only)) / len(spans), 4),
        "modality_histogram": dict(
            Counter(f.get("modality") for f in facts).most_common()),
        "fuzzy_sample_audit": audit,
    }


def q5_dependence_edges() -> dict:
    """Do HPOA dependence edges cover this cohort's diagnoses?"""
    namespaces: Counter[str] = Counter()
    diseases: set[str] = set()
    names: dict[str, str] = {}
    rows = negated = with_frequency = 0
    with (KR / "phenotype.hpoa").open() as handle:
        for line in handle:
            if line.startswith("#") or line.startswith("database_id"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            rows += 1
            namespaces[parts[0].split(":")[0]] += 1
            diseases.add(parts[0])
            names[norm(parts[1])] = parts[0]
            if parts[2].strip() == "NOT":
                negated += 1
            if len(parts) > 7 and parts[7].strip():
                with_frequency += 1

    golds: list[str] = []
    for path in sorted(SUBSETS.glob("*/normalized_cases.json")):
        payload = json.loads(path.read_text())
        cohort = payload if isinstance(payload, list) else (payload.get("cases") or [])
        golds.extend(str(c["gold"]) for c in cohort if c.get("gold"))
    covered = sum(1 for g in golds if norm(g) in names)
    return {
        "hpoa_rows": rows,
        "hpoa_diseases": len(diseases),
        "hpoa_namespaces": dict(namespaces.most_common()),
        "hpoa_not_annotations": negated,
        "hpoa_rows_with_frequency": with_frequency,
        "cohort_golds": len(golds),
        "golds_in_hpoa": covered,
        "gold_coverage_rate": round(covered / len(golds), 4) if golds else None,
    }


def q6_cluster_units(cases: list[dict]) -> dict:
    """Can candidate evidence be re-expressed in cluster units, offline?"""
    spans = mapped = 0
    per_candidate: list[tuple[int, int]] = []
    for case in cases:
        stages = case.get("stages") or {}
        facts = [
            (str(f.get("raw_span") or ""), str(f.get("correlation_group") or ""))
            for f in (stages.get("facts") or [])
        ]
        for candidate in stages.get("registry") or []:
            support = [str(s).strip() for s in (candidate.get("support_spans") or [])]
            found: set[str] = set()
            for span in support:
                spans += 1
                hits = [g for raw, g in facts if raw and (span in raw or raw in span)]
                if hits:
                    mapped += 1
                    found.add(hits[0])
            if support:
                per_candidate.append((len(support), len(found)))
    redundant = sum(1 for n_spans, n_groups in per_candidate if n_groups < n_spans)
    return {
        "support_spans": spans,
        "spans_joined_to_a_fact": mapped,
        "join_rate": round(mapped / max(1, spans), 4),
        "candidates_with_support": len(per_candidate),
        "spans_per_candidate_mean": round(
            st.mean([a for a, _ in per_candidate]), 2),
        "distinct_groups_per_candidate_mean": round(
            st.mean([b for _, b in per_candidate]), 2),
        "candidates_with_redundant_evidence": redundant,
        "redundancy_rate": round(redundant / len(per_candidate), 4),
    }


def q7_bundling_universality() -> list[dict]:
    """Is the bundling no-op universal across candidate prototypes?

    Three regimes exist and they are not interchangeable:
      live    - c4 ran, ledger scores are non-zero, the clip actually applies
      inert   - facts carry correlation_group but c4 was skipped, so scores are 0
      absent  - the pipeline has no correlation_group slot at all
    """
    rows = []
    arms = sorted({
        p.parts[-3]
        for p in ROOT.glob("logs/backbone_v1/medcasereasoning*/*/case_stages/*.json")
    })
    for arm in arms:
        paths = sorted(ROOT.glob(
            f"logs/backbone_v1/medcasereasoning*/{arm}/case_stages/*.json"))
        if not paths:
            continue
        facts = tagged = skipped = present = nonzero = candidates = 0
        modes: set[str] = set()
        for path in paths[:60]:
            stages = (json.loads(path.read_text()).get("stages") or {})
            modes.add(str(stages.get("mode") or "-"))
            rows_f = stages.get("facts") or []
            facts += len(rows_f)
            tagged += sum(
                1 for f in rows_f if str(f.get("correlation_group") or "").strip())
            c4 = stages.get("c4")
            if isinstance(c4, dict) and c4.get("skipped"):
                skipped += 1
            elif c4:
                present += 1
            for cand in stages.get("registry") or []:
                candidates += 1
                if cand.get("score") not in (None, 0, 0.0):
                    nonzero += 1
        if facts == 0:
            regime = "absent"
        elif nonzero:
            regime = "live"
        else:
            regime = "inert"
        rows.append({
            "arm": arm,
            "cases": len(paths),
            "modes": sorted(modes),
            "facts": facts,
            "facts_with_correlation_group": tagged,
            "c4_skipped": skipped,
            "c4_present": present,
            "candidates": candidates,
            "candidates_with_nonzero_score": nonzero,
            "regime": regime,
        })
    return rows


def _score_variants(
    facts: dict[str, dict], cells: list[dict], concept_id: str
) -> tuple[float, float, int]:
    """Recompute score_concept with bundling on and off.

    Bundling changes two things at once: it clips the *summed* group value and it
    takes the group's maximum reliability. Turning it off scores every cell on its
    own fact, which is what `group_key`'s fact_id fallback would do if no fact ever
    shared a correlation_group.
    """
    groups: dict[str, list[tuple[str, float]]] = {}
    for cell in cells:
        if cell.get("concept_id") != concept_id or not cell.get("admitted"):
            continue
        fid = cell["fact_id"]
        fact = facts.get(fid)
        if fact is None:
            continue
        key = str(fact.get("correlation_group") or "") or fid
        groups.setdefault(key, []).append((fid, float(cell.get("value") or 0)))

    bundled = unbundled = 0.0
    binding = 0
    for items in groups.values():
        raw = sum(v for _, v in items)
        if abs(raw) > GROUP_CLIP:
            binding += 1
        reliability = max(
            RELIABILITY_WEIGHT.get(facts[fid].get("reliability"), 0.7)
            for fid, _ in items
        )
        bundled += reliability * max(-GROUP_CLIP, min(GROUP_CLIP, raw))
        for fid, value in items:
            unbundled += RELIABILITY_WEIGHT.get(
                facts[fid].get("reliability"), 0.7
            ) * max(-GROUP_CLIP, min(GROUP_CLIP, value))
    return bundled, unbundled, binding


def q8_bundling_effect(arms: tuple[str, ...]) -> dict:
    """Where bundling is live, does it help or hurt the clinical endpoint?

    `arms` must be modes outside SELECTOR_MODES, where the champion is the ledger
    argmax rather than an LLM selector pick, so a recomputed argmax is the
    counterfactual champion.
    """
    from clinical_endpoint import COMPLETE, PARTIAL, ClinicalEndpoint

    endpoint = ClinicalEndpoint()
    endpoint.drop_conflicts()
    out = {}
    for arm in arms:
        flips = unjudged = 0
        bundled_complete = unbundled_complete = 0
        bundled_cp = unbundled_cp = 0
        binding_groups = changed_scores = candidates = 0
        axis_bias: set[float] = set()
        for path in sorted(ROOT.glob(
            f"logs/backbone_v1/medcasereasoning*/{arm}/case_stages/*.json"
        )):
            sl = SLICE_OF_DIR.get(path.parts[-4])
            cid = path.stem
            stages = json.loads(path.read_text()).get("stages") or {}
            fact_rows = stages.get("facts") or []
            cells = (stages.get("ledger") or {}).get("cells") or []
            registry = stages.get("registry") or []
            if not (fact_rows and cells and registry):
                continue
            facts = {f["fact_id"]: f for f in fact_rows}
            ranked_b, ranked_u = [], []
            for cand in registry:
                bundled, unbundled, binding = _score_variants(
                    facts, cells, cand.get("concept_id"))
                binding_groups += binding
                candidates += 1
                if abs(bundled - unbundled) > 1e-9:
                    changed_scores += 1
                if cand.get("score") is not None:
                    axis_bias.add(round(float(cand["score"]) - bundled, 3))
                ranked_b.append((bundled, cand.get("preferred_label")))
                ranked_u.append((unbundled, cand.get("preferred_label")))
            if not ranked_b:
                continue
            best_b, best_u = max(ranked_b)[1], max(ranked_u)[1]
            if best_b == best_u:
                continue
            flips += 1
            rel_b = endpoint.relation("mcr", sl, cid, best_b)
            rel_u = endpoint.relation("mcr", sl, cid, best_u)
            if rel_b is None or rel_u is None:
                unjudged += 1
                continue
            bundled_complete += rel_b == COMPLETE
            unbundled_complete += rel_u == COMPLETE
            bundled_cp += rel_b in (COMPLETE, PARTIAL)
            unbundled_cp += rel_u in (COMPLETE, PARTIAL)
        out[arm] = {
            "candidates": candidates,
            "groups_hitting_the_clip": binding_groups,
            "candidates_whose_score_bundling_changed": changed_scores,
            "champion_flips": flips,
            "unjudged_flips": unjudged,
            "bundled_complete": bundled_complete,
            "unbundled_complete": unbundled_complete,
            "delta_complete": bundled_complete - unbundled_complete,
            "bundled_complete_or_partial": bundled_cp,
            "unbundled_complete_or_partial": unbundled_cp,
            "axis_bias_residuals": sorted(axis_bias)[:8],
        }
    return out


def q9_step0_probe() -> dict:
    """Does cluster-unit evidence beat span count as a top-1 ranking signal?"""
    from clinical_endpoint import COMPLETE, ClinicalEndpoint

    endpoint = ClinicalEndpoint()
    endpoint.drop_conflicts()
    cohort: list[list[dict]] = []
    for path in sorted(ROOT.glob(ARM)):
        sl = SLICE_OF_DIR.get(path.parts[-4])
        cid = path.stem
        stages = json.loads(path.read_text()).get("stages") or {}
        facts = [
            (str(f.get("raw_span") or ""),
             str(f.get("correlation_group") or ""),
             str(f.get("specificity") or ""))
            for f in (stages.get("facts") or [])
        ]
        registry = stages.get("registry") or []
        if not registry:
            continue
        candidates = []
        for i, cand in enumerate(registry):
            label = cand.get("preferred_label") or ""
            groups: set[str] = set()
            high: set[str] = set()
            for span in cand.get("support_spans") or []:
                span = str(span).strip()
                for raw, group, specificity in facts:
                    if raw and (span in raw or raw in span):
                        groups.add(group)
                        if specificity == "high":
                            high.add(group)
                        break
            against: set[str] = set()
            for span in cand.get("contradict_spans") or []:
                span = str(span).strip()
                for raw, group, _ in facts:
                    if raw and (span in raw or raw in span):
                        against.add(group)
                        break
            candidates.append({
                "i": i,
                "n_spans": len(cand.get("support_spans") or []),
                "n_groups": len(groups),
                "n_groups_against": len(against),
                "n_high_groups": len(high),
                "complete": endpoint.relation("mcr", sl, cid, label) == COMPLETE,
            })
        cohort.append(candidates)

    reachable = [c for c in cohort if any(x["complete"] for x in c)]
    strategies = {
        "gen_order": lambda x: (-x["i"],),
        "n_spans_desc": lambda x: (x["n_spans"], -x["i"]),
        "n_groups_desc": lambda x: (x["n_groups"], -x["i"]),
        "n_groups_minus_against_desc": lambda x: (
            x["n_groups"] - x["n_groups_against"], -x["i"]),
        "n_high_groups_desc": lambda x: (x["n_high_groups"], -x["i"]),
        "n_spans_asc": lambda x: (-x["n_spans"], -x["i"]),
        "n_groups_asc": lambda x: (-x["n_groups"], -x["i"]),
    }
    ranking = {
        name: sum(1 for c in reachable if max(c, key=key)["complete"])
        for name, key in strategies.items()
    }
    hybrids = {}
    for m in (1, 2, 3):
        hybrids[f"gen_order_skip_to_first_high_ge_{m}"] = sum(
            1 for c in reachable
            if next((x for x in c if x["n_high_groups"] >= m), c[0])["complete"]
        )
    # Candidate-level monotonicity: does conjunction of specific findings predict
    # correctness even when it cannot be turned into a better ranking?
    monotone = {}
    for m in (0, 1, 2, 3):
        bucket = [x for c in cohort for x in c if x["n_high_groups"] == m]
        monotone[f"n_high_groups_eq_{m}"] = {
            "candidates": len(bucket),
            "complete": sum(1 for x in bucket if x["complete"]),
            "complete_rate": round(
                sum(1 for x in bucket if x["complete"]) / len(bucket), 4)
            if bucket else None,
        }
    return {
        "cases": len(cohort),
        "pool_reachable_cases": len(reachable),
        "top1_complete_by_ranking": ranking,
        "conversion_by_ranking": {
            k: round(v / len(reachable), 4) for k, v in ranking.items()},
        "top1_complete_by_hybrid": hybrids,
        "candidate_level_monotonicity": monotone,
    }


def q10_grounding_fixes(cases: list[dict]) -> dict:
    """Measure the three training-free grounding fixes the SOTA survey proposes.

    Two of the three turn out to be no-ops here: every exact match already sits
    inside the phenotypic-abnormality subtree, and the short-synonym blacklist only
    matters for the substring fallback that the third fix deletes outright.
    """
    from agentclinic_tree_dx.knowledge.hpo_index import HPOIndex

    index = HPOIndex.from_obo(KR / "hp.obo")
    phenotypic_abnormality = "HP:0000118"

    def in_subtree(hpo_id: str) -> bool:
        return hpo_id == phenotypic_abnormality or phenotypic_abnormality in (
            index.get_ancestors(hpo_id))

    facts = [
        f for case in cases for f in ((case.get("stages") or {}).get("facts") or [])
    ]
    spans = [str(f.get("raw_span") or "") for f in facts]
    exact = [(s, index.resolve(s)) for s in spans if index.resolve(s)]
    exact_in_subtree = [(s, h) for s, h in exact if in_subtree(h)]

    # `_text_to_hpo` is the only handle on the lexicon; there is no public accessor.
    lexicon = index._text_to_hpo  # noqa: SLF001
    short = [t for t in lexicon if len(t) < 4]

    fuzzy_only = [
        s for s in spans if not index.resolve(s) and index.resolve_fuzzy(s)
    ]
    outside = root = via_short = 0
    for span in fuzzy_only:
        hpo_id = index.resolve_fuzzy(span)
        if hpo_id == "HP:0000001":
            root += 1
        if not in_subtree(hpo_id):
            outside += 1
        low = span.strip().lower()
        if any(t in low for t in short):
            via_short += 1

    modality = Counter(f.get("modality") for f in facts)
    deterministic = modality.get("laboratory", 0)
    snomed_only = (
        modality.get("history", 0)
        + modality.get("imaging", 0)
        + modality.get("treatment_response", 0)
    )
    return {
        "facts": len(spans),
        "exact_grounded": len(exact),
        "exact_inside_phenotypic_abnormality": len(exact_in_subtree),
        "exact_outside_subtree": len(exact) - len(exact_in_subtree),
        "subtree_restriction_is_noop_for_exact": len(exact) == len(exact_in_subtree),
        "lexicon_entries": len(lexicon),
        "lexicon_entries_shorter_than_4": len(short),
        "fuzzy_only_hits": len(fuzzy_only),
        "fuzzy_hits_outside_subtree": outside,
        "fuzzy_hits_on_root": root,
        "fuzzy_hits_via_short_synonym": via_short,
        "fuzzy_via_short_synonym_share": round(
            via_short / max(1, len(fuzzy_only)), 4),
        "laboratory_deterministic_share": round(deterministic / len(spans), 4),
        "exam_share": round(modality.get("exam", 0) / len(spans), 4),
        "snomed_only_spans": snomed_only,
        "snomed_only_share": round(snomed_only / len(spans), 4),
    }


def q11_stance_decomposition() -> dict:
    """Where does MultiStance's pool recall actually come from?

    Backs SYMPTOM_CLUSTER_GENERATION_PLAN.md §2 and §5.1: the per-stance complete
    rate, the marginal recall each stance buys, and the per-slice cohort sizes the
    recall-preservation gate is scoped to.
    """
    from clinical_endpoint import COMPLETE, ClinicalEndpoint

    endpoint = ClinicalEndpoint()
    endpoint.drop_conflicts()
    per_origin: Counter[str] = Counter()
    per_origin_complete: Counter[str] = Counter()
    exclusive: Counter[str] = Counter()
    first_origin: Counter[str] = Counter()
    slice_cases: Counter[str] = Counter()
    slice_reachable: Counter[str] = Counter()
    slice_commit_reachable: Counter[str] = Counter()
    reachable = commit_only_reachable = 0

    for path in sorted(ROOT.glob(ARM)):
        sl = SLICE_OF_DIR.get(path.parts[-4])
        cid = path.stem
        registry = (json.loads(path.read_text()).get("stages") or {}).get(
            "registry") or []
        if not registry:
            continue
        slice_cases[sl] += 1
        first_origin[str(registry[0].get("origin") or "?")] += 1
        complete_origins: set[str] = set()
        for cand in registry:
            origin = str(cand.get("origin") or "?")
            per_origin[origin] += 1
            if endpoint.relation(
                "mcr", sl, cid, cand.get("preferred_label") or ""
            ) == COMPLETE:
                per_origin_complete[origin] += 1
                complete_origins.add(origin)
        if complete_origins:
            reachable += 1
            slice_reachable[sl] += 1
            if "c3:commit" in complete_origins:
                commit_only_reachable += 1
                slice_commit_reachable[sl] += 1
            if len(complete_origins) == 1:
                exclusive[next(iter(complete_origins))] += 1

    dev_gate = slice_commit_reachable["mcr_v1"] + slice_commit_reachable["mcr_v2"]
    return {
        "candidates_by_origin": dict(per_origin.most_common()),
        "complete_by_origin": dict(per_origin_complete.most_common()),
        "complete_rate_by_origin": {
            o: round(per_origin_complete.get(o, 0) / n, 4)
            for o, n in per_origin.most_common()
        },
        "exclusive_rescues_by_origin": dict(exclusive.most_common()),
        "candidates_per_exclusive_rescue": {
            o: round(per_origin[o] / exclusive[o], 1)
            for o in exclusive
        },
        "first_candidate_origin": dict(first_origin.most_common()),
        "pool_reachable": reachable,
        "pool_reachable_commit_only": commit_only_reachable,
        "marginal_recall_of_non_commit_stances": reachable - commit_only_reachable,
        "by_slice": {
            sl: {
                "cases": slice_cases[sl],
                "reachable": slice_reachable[sl],
                "reachable_via_commit": slice_commit_reachable[sl],
            }
            for sl in ("mcr_v1", "mcr_v2", "mcr_200b")
        },
        "g1_gate_cases": dev_gate,
        "g1_gate_calls_two_arms": dev_gate * 2,
    }


def main() -> int:
    cases = load_cases()
    if not cases:
        print("no frozen multistance cases found", file=sys.stderr)
        return 1
    ledger_argmax_arms = (
        "aphhm_c_v1", "aphhm_c_v1_r2", "aphhm_c_noaxis_v1", "aphhm_c_nocond_v1")
    report = {
        "q1_q2_clusters": q1_q2_clusters(cases),
        "q3_named_composite": q3_named_composite(cases),
        "q4_grounding": q4_grounding(cases),
        "q5_dependence_edges": q5_dependence_edges(),
        "q6_cluster_units": q6_cluster_units(cases),
        "q7_bundling_universality": q7_bundling_universality(),
        "q8_bundling_effect": q8_bundling_effect(ledger_argmax_arms),
        "q9_step0_probe": q9_step0_probe(),
        "q10_grounding_fixes": q10_grounding_fixes(cases),
        "q11_stance_decomposition": q11_stance_decomposition(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    out = ROOT / "analysis/mechanism_v2/results/SYMPTOM_CLUSTER_READINESS/audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
