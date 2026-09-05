#!/usr/bin/env python3
"""Extract the hypothesis sets the four target methods produced on the audit 48.

For every audited case and every method (Collapse3c, MultiStance, IMPC, MOSAIC
Forest) this pulls the full candidate registry, the per-candidate support /
contradiction spans and the selector outcome, then decides whether the frozen
gold diagnosis was *recalled* (present in the hypothesis set), *near-recalled*
(only a parent / component / sibling form is present) or missed.

Recall is measured on the hypothesis set, not on the final answer, because the
question this feeds is: given that the method did entertain the right answer,
did it have -- and use -- the findings that separate it from its competitors.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/manual_source_coverage_48_local_expanded.jsonl"
LOGS = ROOT / "logs/backbone_v1"
BENCH = ROOT / "data/benchmarks"

METHODS = {
    "collapse3c": "aphhm_c_collapse3c_v1",
    "multistance": "aphhm_c_multistance_v1",
    "impc": "mosaic_impc_v1",
    "forest": "mosaic_forest_v1",
}

# audit slice id -> (logs/backbone_v1 dataset dir, benchmark subset dir)
SLICES = {
    "DA_d2_seq100": ("diagnosisarena", "diagnosisarena/subsets/d2_seq100_v1"),
    "DA_d2_heldout100": ("diagnosisarena_heldout", "diagnosisarena/subsets/d2_heldout100_v1"),
    "DA_d2_heldout200b": ("diagnosisarena_heldout200b", "diagnosisarena/subsets/d2_heldout200b_v1"),
    "MCR_v1_seq100": ("medcasereasoning", "medcasereasoning/subsets/mcr_val_seq100_v1"),
    "MCR_v2_seq100": ("medcasereasoning_v2", "medcasereasoning/subsets/mcr_val_seq100_v2"),
    "MCR_seq200b": ("medcasereasoning_200b", "medcasereasoning/subsets/mcr_val_seq200b_v1"),
}


def load_upstream() -> Any:
    spec = importlib.util.spec_from_file_location(
        "upstream_audit",
        ROOT / "analysis/mechanism_v2/results/RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT/audit_rag_guideline_capacity.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["upstream_audit"] = module
    spec.loader.exec_module(module)
    return module


UP = load_upstream()
sys.path.insert(0, str(HERE))
from scan_expanded_source_capacity import camel_split, informative, norm_tokens  # noqa: E402

norm = UP.norm
bounded_contains = UP.bounded_contains


# --------------------------------------------------------------------------
# candidate extraction
# --------------------------------------------------------------------------
def registry_entries(stages: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for entry in stages.get("registry", []) or []:
        label = entry.get("preferred_label") or entry.get("preferred_name") or ""
        out.append(
            {
                "concept_id": entry.get("concept_id", ""),
                "label": label,
                "aliases": list(entry.get("aliases", []) or []),
                "score": entry.get("score", entry.get("score_logit")),
                "status": entry.get("status", ""),
                "support_spans": list(entry.get("support_spans", []) or []),
                "contradict_spans": list(entry.get("contradict_spans", []) or []),
                "support_evidence": list(entry.get("supporting_evidence", []) or []),
                "contradict_evidence": list(entry.get("contradicting_evidence", []) or []),
                "views": list(entry.get("generator_views", entry.get("stances", [])) or []),
                "axis_nodes": list(entry.get("axis_nodes", []) or []),
            }
        )
    return out


def generator_candidates(stages: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    """Per-view candidates with the model's own support/contradict rationale."""
    out: list[dict[str, Any]] = []

    def push(view: str, item: dict[str, Any]) -> None:
        out.append(
            {
                "view": view,
                "label": item.get("preferred_label") or item.get("name") or "",
                "support_spans": list(item.get("support_spans", []) or []),
                "contradict_spans": list(item.get("contradict_spans", []) or []),
                "why": item.get("why", ""),
                "axis_node": item.get("axis_node", ""),
            }
        )

    if mode in {"c4_selector_candev_nomatrix"}:
        for item in (stages.get("c3", {}) or {}).get("concepts", []) or []:
            push("c3", item)
    if mode == "multistance":
        for stance in (stages.get("c3", {}) or {}).get("stances", []) or []:
            for item in stance.get("concepts", []) or []:
                push(f"stance:{stance.get('stance','')}", item)
    if mode == "impc":
        for key in ("D1", "D2", "D3"):
            block = stages.get(key, {}) or {}
            for item in block.get("candidates", []) or []:
                push(key, item)
    if mode == "forest":
        for key in ("ax_syndrome", "ax_mechanism", "ax_modality"):
            block = stages.get(key, {}) or {}
            for item in block.get("candidates", []) or []:
                push(block.get("axis", key), item)
    return out


def selector_view(stages: dict[str, Any]) -> dict[str, Any]:
    sel = stages.get("selector") or stages.get("frontier_selector") or {}
    return {
        "champion": sel.get("champion", ""),
        "runner_up": sel.get("runner_up", ""),
        "why": sel.get("why") or sel.get("rationale") or "",
        "margin": sel.get("margin", ""),
        "rejected": [
            {"name": r.get("name") or r.get("label") or "", "why": r.get("why", "")}
            for r in (sel.get("rejected", []) or [])
        ],
        "finalists": [
            {
                "name": f.get("preferred_label") or f.get("name") or "",
                "group": f.get("group", ""),
                "why": f.get("why", ""),
            }
            for f in (sel.get("finalists", []) or [])
        ],
    }


# --------------------------------------------------------------------------
# gold matching
# --------------------------------------------------------------------------
def gold_forms(gold: str, aliases, canonicals, known) -> dict[str, list[str]]:
    variants = UP.label_variants(gold, aliases, canonicals, known)
    camel = camel_split(gold)
    if camel:
        variants.setdefault("camel_split", []).append(camel)
    return variants


STRONG_KINDS = ("exact", "camel_split", "parenthetical_stripped", "aliases")
STEM_PREFIX = 7


def kin(a: str, b: str) -> bool:
    """Treat inflectional kin as one token (metastatic ~ metastasis, -oma plurals)."""
    if a == b:
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= STEM_PREFIX


def covered(gold_tokens: list[str], cand_tokens: list[str]) -> int:
    return sum(1 for g in gold_tokens if any(kin(g, c) for c in cand_tokens))


def match_strength(candidate: str, variants: dict[str, list[str]]) -> str:
    """strong = candidate names the gold entity; near = parent/component overlap."""
    cnorm = norm(candidate)
    if not cnorm:
        return "none"
    for kind in STRONG_KINDS:
        for value in variants.get(kind, []):
            vnorm = norm(value)
            if not vnorm:
                continue
            if bounded_contains(cnorm, vnorm) or bounded_contains(vnorm, cnorm):
                return "strong"
    gold_tokens = set(informative(norm_tokens(" ".join(variants.get("exact", [])))))
    camel = variants.get("camel_split", [])
    if camel:
        gold_tokens |= set(informative(norm_tokens(camel[0])))
    cand_tokens = set(informative(norm_tokens(candidate)))
    if not gold_tokens or not cand_tokens:
        return "none"
    g, c = sorted(gold_tokens), sorted(cand_tokens)
    hit_g = covered(g, c)
    if not hit_g:
        return "none"
    if hit_g / len(g) >= 0.6 or covered(c, g) / len(c) >= 0.6:
        return "near"
    return "weak"


RANK = {"strong": 3, "near": 2, "weak": 1, "none": 0}


def best_match(labels: list[str], variants: dict[str, list[str]]) -> tuple[str, str]:
    best, best_label = "none", ""
    for label in labels:
        s = match_strength(label, variants)
        if RANK[s] > RANK[best]:
            best, best_label = s, label
    return best, best_label


# --------------------------------------------------------------------------
# evaluation join
# --------------------------------------------------------------------------
def da_records(dataset_dir: str, method_dir: str) -> dict[str, dict[str, Any]]:
    path = LOGS / dataset_dir / method_dir / "mapper/records.json"
    if not path.exists():
        return {}
    blob = json.loads(path.read_text(encoding="utf-8"))
    rows = blob.get("records", blob) if isinstance(blob, dict) else blob
    return {str(r.get("source_id", "")): r for r in rows}


def mcr_score(dataset_dir: str, method_dir: str, source_id: str) -> dict[str, Any]:
    path = LOGS / dataset_dir / method_dir / f"annotate/official_eval_llm/case_scores/{source_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_vignettes(subset: str) -> dict[str, dict[str, Any]]:
    path = BENCH / subset / "normalized_cases.json"
    if not path.exists():
        return {}
    blob = json.loads(path.read_text(encoding="utf-8"))
    rows = blob.get("cases", blob) if isinstance(blob, dict) else blob
    out = {}
    for row in rows:
        key = str(row.get("id", row.get("case_id", "")))
        out[key] = row
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/method_hypothesis_recall_48.jsonl")
    args = parser.parse_args()

    aliases, canonicals, known = UP.bridge_tables()
    ledger = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]

    vignette_cache: dict[str, dict[str, Any]] = {}
    record_cache: dict[tuple[str, str], dict[str, Any]] = {}

    rows = []
    for entry in ledger:
        slice_id, source_id = entry["case_key"].split("/", 1)
        dataset_dir, subset = SLICES[slice_id]
        if subset not in vignette_cache:
            vignette_cache[subset] = load_vignettes(subset)
        vig = vignette_cache[subset].get(source_id, {})
        variants = gold_forms(entry["gold"], aliases, canonicals, known)

        out: dict[str, Any] = {
            "case_key": entry["case_key"],
            "family": entry["family"],
            "sampling_stratum": entry["sampling_stratum"],
            "sampling_weight": entry["sampling_weight"],
            "gold": entry["gold"],
            "diagnostic_support_local": entry["diagnostic_support"],
            "diagnostic_support_upstream": entry["upstream_diagnostic_support"],
            "gold_variants": variants,
            "vignette_chars": len(vig.get("case_text", "") or ""),
            "methods": {},
        }

        for name, method_dir in METHODS.items():
            trace_path = LOGS / dataset_dir / method_dir / f"case_stages/{source_id}.json"
            if not trace_path.exists():
                out["methods"][name] = {"present": False}
                continue
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            stages = trace.get("stages", {}) or {}
            mode = stages.get("mode", "")

            reg = registry_entries(stages)
            gen = generator_candidates(stages, mode)
            sel = selector_view(stages)
            ordered = list(trace.get("ordered_diagnoses", []) or [])

            reg_labels = [r["label"] for r in reg] + [a for r in reg for a in r["aliases"]]
            gen_labels = [g["label"] for g in gen]
            all_labels = reg_labels + gen_labels + ordered + [sel["champion"], sel["runner_up"]]

            set_strength, set_label = best_match(all_labels, variants)
            champ_strength, _ = best_match([sel["champion"]] if sel["champion"] else [], variants)
            top2_strength, _ = best_match(ordered[:2], variants)

            if champ_strength == "strong":
                status = "champion_strong"
            elif top2_strength == "strong":
                status = "top2_strong"
            elif set_strength == "strong":
                status = "set_strong"
            elif set_strength == "near":
                status = "set_near"
            else:
                status = "miss"

            # which registry entry carried the gold, and which competed with it
            gold_entries, competitor_entries = [], []
            for r in reg:
                s = match_strength(r["label"], variants)
                if s == "none":
                    s, _ = best_match(r["aliases"], variants)
                (gold_entries if s in {"strong", "near"} else competitor_entries).append(
                    {**r, "gold_match": s}
                )

            if entry["family"] == "DA":
                key = (dataset_dir, method_dir)
                if key not in record_cache:
                    record_cache[key] = da_records(dataset_dir, method_dir)
                rec = record_cache[key].get(source_id, {})
                omaps = (rec.get("projection", {}) or {}).get("option_maps", {}) or {}
                matched = [k for k, v in omaps.items() if v.get("matched")]
                gold_letter = rec.get("gold_letter")
                correct = {
                    "metric": "option_top1",
                    "top1": rec.get("option_top1"),
                    "top2": rec.get("option_top2"),
                    "rank": rec.get("option_rank"),
                    "gold_letter": gold_letter,
                    "n_options": len(omaps),
                    "n_options_matched": len(matched),
                    "matched_all_options": bool(omaps) and len(matched) == len(omaps),
                    "gold_relation_type": (omaps.get(gold_letter, {}) or {}).get("relation_type"),
                    "gold_rationale": (omaps.get(gold_letter, {}) or {}).get("rationale"),
                    "option_relations": {
                        k: v.get("relation_type") for k, v in omaps.items()
                    },
                }
            else:
                sc = mcr_score(dataset_dir, method_dir, source_id)
                correct = {
                    "metric": "diagnostic_hit",
                    "top1": sc.get("diagnostic_hit"),
                    "top2": None,
                    "gold_diagnosis": sc.get("gold_diagnosis"),
                    "pred_diagnosis": sc.get("pred_diagnosis"),
                }

            out["methods"][name] = {
                "present": True,
                "mode": mode,
                "recall_status": status,
                "set_match_strength": set_strength,
                "matched_label": set_label,
                "champion": sel["champion"],
                "runner_up": sel["runner_up"],
                "selector_why": sel["why"],
                "selector_margin": sel["margin"],
                "selector_rejected": sel["rejected"],
                "selector_finalists": sel["finalists"],
                "ordered_diagnoses": ordered,
                "n_registry": len(reg),
                "n_generator_candidates": len(gen),
                "gold_registry_entries": gold_entries,
                "competitor_registry_entries": competitor_entries,
                "generator_candidates": gen,
                "evidence": stages.get("evidence", stages.get("facts", [])),
                "correct": correct,
            }
        rows.append(out)

    args.out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n",
        encoding="utf-8",
    )

    from collections import Counter

    print(json.dumps({"n_cases": len(rows)}, indent=2))
    for name in METHODS:
        c = Counter(r["methods"][name].get("recall_status", "absent") for r in rows)
        print(f"{name:12s}", dict(sorted(c.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
