#!/usr/bin/env python3
"""Sequentially extract a benchmark subset with quality gates.

Selection policy (PAPER plan Phase 1 pilot; shared across corpora):
  1. Scan raw rows in ascending source id order (NOT random).
  2. Optionally ``--skip-rows N`` to continue after a prior sequential slice.
  3. Optionally ``--exclude-ids-file`` as a hard anti-overlap guard.
  4. Skip if gold or any MCQ option fails the disease-name gate.
  5. Skip if gold or any option lacks retrievable DDx knowledge in this repo KB.
  6. Keep scanning until ``--target-size`` cases are collected.

Datasets (``--dataset``):
  - diagnosisarena  (default): D2 test.parquet
  - open_xddx       : Open-XDDx.xlsx via open_xddx_adapter
  - medcasereasoning: validation parquet via medcasereasoning_adapter
  - rarearena       : RareArena RDC JSONL via rarearena_adapter

Outputs under ``data/benchmarks/<dataset>/subsets/<version>/``:
  - ``cases.parquet``            selected rows (DiagnosisArena-shaped columns)
  - ``case_ids.txt``             one id per line (stable order)
  - ``normalized_cases.json``    harness-ready cases
  - ``selection_manifest.json``  counts + gate config
  - ``exclusion_log.jsonl``      every skipped row with reasons
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.knowledge.lr_retriever import _disease_match_score

import diagnosisarena_adapter as da  # noqa: E402

DATA = ROOT / "data"
DEFAULTS = {
    "diagnosisarena": {
        "raw": DATA / "benchmarks" / "diagnosisarena" / "raw" / "test.parquet",
        "out": DATA / "benchmarks" / "diagnosisarena" / "subsets" / "d2_seq100_v1",
        "version": "d2_seq100_v1",
    },
    "open_xddx": {
        "raw": DATA / "benchmarks" / "open_xddx" / "raw" / "Open-XDDx.xlsx",
        "out": DATA / "benchmarks" / "open_xddx" / "subsets" / "ox_seq100_v1",
        "version": "ox_seq100_v1",
    },
    "medcasereasoning": {
        "raw": (
            DATA / "benchmarks" / "medcasereasoning" / "raw"
            / "val-00000-of-00001.parquet"
        ),
        "out": (
            DATA / "benchmarks" / "medcasereasoning" / "subsets" / "mcr_val_seq100_v1"
        ),
        "version": "mcr_val_seq100_v1",
    },
    "rarearena": {
        "raw": DATA / "benchmarks" / "rarearena" / "raw" / "RDC.json",
        "out": DATA / "benchmarks" / "rarearena" / "subsets" / "ra_rdc_seq100_v1",
        "version": "ra_rdc_seq100_v1",
    },
}

_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")

_DISEASE_SUFFIX_HINTS = re.compile(
    r"("
    r"syndrome|disease|disorder|carcinoma|sarcoma|lymphoma|leukemia|leukaemia|"
    r"melanoma|infection|mycosis|osis|itis|emia|oma|pathy|plasia|malformation|"
    r"heterotopia|granuloma|granulomatosis|vasculitis|dermatosis|dermatitis|"
    r"enteritis|pneumonia|tuberculosis|histoplasmosis|trichosporonosis|amyloid|"
    r"prolactinoma|hemangioma|hemangioendothelioma|meningioma|glucagonoma|"
    r"malformations|angioma|fibroma|sarcoidosis|scleroderma|morphea|"
    r"histiocytosis|erythema|lymphoma|myeloma|xanthoma|lipoma|adenoma"
    r")\b",
    re.I,
)

_NON_DISEASE_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"^(scrotal|facial|cutaneous|oral|rectal|penile|vulvar)\s+(ulceration|ulcer)\b",
            re.I,
        ),
        "anatomic_ulceration",
    ),
    (
        re.compile(
            r"\bsecondary to (induction chemotherapy|chemotherapy|atRA|ATRA|radiotherapy|radiation therapy|surgery|trauma)\b",
            re.I,
        ),
        "treatment_complication",
    ),
    (re.compile(r"^iatrogenic (hyper|hypo)[a-z]+$", re.I), "iatrogenic_metabolic_finding"),
    (
        re.compile(r"^gadolinium[- ]associated plaques?\b", re.I),
        "drug_associated_imaging_finding",
    ),
    (re.compile(r"\bassociated retinopathy\b", re.I), "drug_associated_retinopathy"),
    (
        re.compile(
            r"^(severe )?(hyper|hypo)(kalemia|natremia|calcemia|glycemia)\b",
            re.I,
        ),
        "metabolic_finding_only",
    ),
]

_EPONYM_OR_KNOWN = re.compile(
    r"\b("
    r"crohn|kaposi|addison|basedow|paget|behcet|sjogren|still|wegener|hashimoto|"
    r"histoplasmosis|aspergillosis|candidiasis|toxoplasmosis|trichosporonosis"
    r")\b",
    re.I,
)


def _core_label(label: str) -> str:
    return _PAREN_RE.sub(" ", label).strip()


def is_disease_name(label: str) -> tuple[bool, str | None]:
    raw = (label or "").strip()
    if not raw:
        return False, "empty_label"

    for pattern, reason in _NON_DISEASE_RULES:
        if pattern.search(raw):
            return False, reason

    if re.search(r"\bwith secondary (optic nerve )?injury\b", raw, re.I):
        head = re.split(r"\bwith secondary\b", raw, maxsplit=1, flags=re.I)[0]
        if not _DISEASE_SUFFIX_HINTS.search(head) and not _EPONYM_OR_KNOWN.search(head):
            return False, "secondary_injury_without_primary_disease"

    core = _core_label(raw)
    if _DISEASE_SUFFIX_HINTS.search(core) or _EPONYM_OR_KNOWN.search(core):
        return True, None

    if " secondary to " in core.lower():
        head = core.lower().split(" secondary to ", 1)[0]
        if not _DISEASE_SUFFIX_HINTS.search(head) and not _EPONYM_OR_KNOWN.search(head):
            return False, "secondary_to_non_disease_head"

    tokens = core.split()
    if len(tokens) <= 2:
        return False, "ambiguous_short_label"

    if re.search(r"\b(ulceration|injury|plaques?|changes?|reaction| toxicity)\b", core, re.I):
        return False, "descriptive_non_disease_phrase"

    return True, None


def build_kb():
    cfg = ControllerConfig(
        allow_external_knowledge=True,
        dxs_common_json=str(DATA / "knowledge_raw" / "Guideline_common.json"),
        dxs_rare_json=str(DATA / "knowledge_raw" / "Guideline_rare.json"),
        primekg_csv=str(DATA / "knowledge_raw" / "kg.csv"),
        lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
        doclogica_cache_json=str(DATA / "knowledge_raw" / "doclogica_cache.json"),
        pathognomonic_markers_json=str(DATA / "knowledge_raw" / "pathognomonic_markers.json"),
        auto_ambiguity_map_json=str(DATA / "knowledge_raw" / "auto_ambiguity_map.json"),
        lab_reference_ranges_json=str(DATA / "knowledge_raw" / "lab_reference_ranges.json"),
        loinc2hpo_json=str(DATA / "knowledge_raw" / "loinc2hpo_annotations.json"),
        unit_conversions_json=str(DATA / "knowledge_raw" / "unit_conversions.json"),
        snomed_concepts_json=str(DATA / "knowledge_raw" / "snomed_concepts.json"),
        snomed_term_index_json=str(DATA / "knowledge_raw" / "snomed_term_index.json"),
        snomed_relations_json=str(DATA / "knowledge_raw" / "snomed_relations.json"),
        rag_index_dir=str(DATA / "corpus" / "rag_index"),
        enable_knowledge_injection=True,
        enable_lr_rag_fallback=True,
        enable_chain_discoverer=True,
        enable_pubmed_fallback=False,
    )
    ctrl = AgentClinicTreeController(env=None, llm=None, config=cfg)
    kr = ctrl._knowledge_retriever
    return kr, kr.lr, kr.dxs, kr.primekg, kr.rag


def make_kb_checker(kr, lr, dxs, pkg, rag):
    di = lr._disease_index
    dbridge = lr._disease_synonym_bridge

    def _lr_hit(name: str) -> str | None:
        dl = name.strip().lower()
        if di.get(dl):
            return "lr:exact"
        canon = dbridge.get(dl)
        if canon and di.get(canon):
            return "lr:synonym"
        best = None
        for candidate in di:
            score = _disease_match_score(dl, candidate)
            if score >= 0.6 and (best is None or score > best[1]):
                best = (candidate, score)
        if best:
            return "lr:fuzzy(%.2f)" % best[1]
        return None

    @lru_cache(maxsize=4096)
    def kb_covers(label: str) -> tuple[bool, str]:
        hit = _lr_hit(label)
        if hit:
            return True, hit

        resolved = kr.resolver.resolve_all_sources(label)
        hits = [src for src, val in resolved.items() if val]
        if hits:
            return True, "resolve:" + ",".join(sorted(hits))

        q = label.strip().lower()
        if dxs.search_diseases(q, limit=1):
            return True, "dxs:substring"
        if pkg.search_diseases(q, limit=1):
            return True, "primekg:substring"

        if rag and getattr(rag, "is_ready", False):
            snippets = rag.search(
                "differential diagnosis %s" % label,
                top_k=3,
                score_threshold=0.0,
            )
            canon = kr.resolver.canonicalize_entity(label).lower()
            for snippet in snippets:
                text = (snippet.get("text") or "").lower()
                if q in text or (len(canon) > 3 and canon in text):
                    return True, "rag:text_hit"
        return False, "none"

    return kb_covers


def evaluate_case(
    row: pd.Series,
    kb_covers,
    *,
    dataset: str = "diagnosisarena",
) -> tuple[bool, list[dict[str, Any]]]:
    if row.get("_adapter_error"):
        return False, [{
            "role": "adapter",
            "label": str(row.get("Final Diagnosis") or ""),
            "gate": "adapter",
            "reason": str(row["_adapter_error"]),
        }]
    labels = [("gold", row["Final Diagnosis"])]
    options = row["Options"]
    if isinstance(options, dict):
        labels.extend(("option_%s" % k, v) for k, v in sorted(options.items()))
    else:
        labels.extend(("option_%s" % i, v) for i, v in enumerate(options))

    # Soft disease-name fails recoverable when KB covers (or for transfer options).
    soft_name_reasons = {
        "ambiguous_short_label",
        "descriptive_non_disease_phrase",
    }
    # DiagnosisArena keeps DA Phase-1 strictness: every option needs KB.
    # Transfer corpora (long DDx lists) require KB on gold only.
    options_need_kb = dataset == "diagnosisarena"

    issues: list[dict[str, Any]] = []
    for role, text in labels:
        ok, reason = is_disease_name(text)
        covered, how = kb_covers(str(text))
        is_gold = str(role) == "gold"
        if not ok:
            if reason in soft_name_reasons and (covered or (not is_gold and not options_need_kb)):
                if is_gold and not covered:
                    issues.append({
                        "role": role, "label": text,
                        "gate": "disease_name", "reason": reason,
                    })
                continue
            issues.append({
                "role": role, "label": text, "gate": "disease_name", "reason": reason,
            })
            continue
        if is_gold and not covered:
            issues.append({
                "role": role, "label": text, "gate": "kb_coverage", "reason": how,
            })
        elif (not is_gold) and options_need_kb and not covered:
            issues.append({
                "role": role, "label": text, "gate": "kb_coverage", "reason": how,
            })

    return (not issues), issues


def iter_dataset_rows(dataset: str, raw_path: Path) -> Iterator[pd.Series]:
    if dataset == "diagnosisarena":
        df = (
            pd.read_parquet(raw_path)
            .sort_values("id", kind="stable")
            .reset_index(drop=True)
        )
        for _, row in df.iterrows():
            yield row
        return
    if dataset == "open_xddx":
        import open_xddx_adapter as ox

        yield from ox.iter_raw_rows(raw_path)
        return
    if dataset == "medcasereasoning":
        import medcasereasoning_adapter as mcr

        yield from mcr.iter_raw_rows(raw_path)
        return
    if dataset == "rarearena":
        import rarearena_adapter as ra

        yield from ra.iter_raw_rows(raw_path)
        return
    raise ValueError("unknown dataset %s" % dataset)


def write_normalized(dataset: str, cases_parquet: Path, out_json: Path) -> int:
    if dataset == "diagnosisarena":
        cases = da.load_subset_cases(cases_parquet)
        for case in cases:
            case["dataset"] = "diagnosisarena_d2_seq100_v1"
            case["corpus"] = "diagnosisarena"
    elif dataset == "open_xddx":
        import open_xddx_adapter as ox

        cases = ox.load_subset_cases(cases_parquet)
    elif dataset == "medcasereasoning":
        import medcasereasoning_adapter as mcr

        cases = mcr.load_subset_cases(cases_parquet)
    elif dataset == "rarearena":
        import rarearena_adapter as ra

        cases = ra.load_subset_cases(cases_parquet)
    else:
        raise ValueError(dataset)
    payload = {
        "schema_version": 1,
        "dataset": cases[0]["dataset"] if cases else dataset,
        "n_cases": len(cases),
        "cases": cases,
    }
    da._atomic_json(out_json, payload)
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="diagnosisarena",
        choices=sorted(DEFAULTS.keys()),
    )
    parser.add_argument(
        "--raw-parquet",
        type=Path,
        default=None,
        help="Raw input path (parquet/xlsx). Defaults per --dataset.",
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--target-size", type=int, default=100)
    parser.add_argument("--version", default=None)
    parser.add_argument(
        "--skip-rows",
        type=int,
        default=0,
        help=(
            "Skip the first N sequential raw rows before gating/selection. "
            "Use the previous subset's last selected id (or scanned_until-1) "
            "to continue the same ordered scan without overlap."
        ),
    )
    parser.add_argument(
        "--exclude-ids-file",
        type=Path,
        default=None,
        help=(
            "Optional case_ids.txt from a prior subset; those ids are never "
            "selected (safety net against overlap)."
        ),
    )
    args = parser.parse_args()

    cfg = DEFAULTS[args.dataset]
    raw_path = Path(args.raw_parquet) if args.raw_parquet else Path(cfg["raw"])
    out_dir = Path(args.out_dir) if args.out_dir else Path(cfg["out"])
    version = args.version or str(cfg["version"])

    if not raw_path.is_file():
        parser.error("missing raw file: %s" % raw_path)

    exclude_ids: set[str] = set()
    if args.exclude_ids_file is not None:
        excl_path = Path(args.exclude_ids_file)
        if not excl_path.is_file():
            parser.error("missing --exclude-ids-file: %s" % excl_path)
        exclude_ids = {
            line.strip()
            for line in excl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    print("Loading knowledge layer (LR + DxS + PrimeKG + RAG) ...")
    kr, lr, dxs, pkg, rag = build_kb()
    kb_covers = make_kb_checker(kr, lr, dxs, pkg, rag)
    print("RAG ready:", getattr(rag, "is_ready", False))
    print("Dataset:", args.dataset, "| sequential scan of", raw_path)
    if args.skip_rows:
        print("skip_rows:", args.skip_rows)
    if exclude_ids:
        print("exclude_ids:", len(exclude_ids), "from", args.exclude_ids_file)

    selected_rows: list[pd.Series] = []
    exclusion_log: list[dict[str, Any]] = []
    scanned = 0
    skipped_prefix = 0
    skipped_excluded = 0

    for row in iter_dataset_rows(args.dataset, raw_path):
        scanned += 1
        if len(selected_rows) >= args.target_size:
            break
        if scanned <= int(args.skip_rows):
            skipped_prefix += 1
            continue
        cid_raw = row.get("id")
        try:
            cid_key = str(int(cid_raw))
        except (TypeError, ValueError):
            cid_key = str(cid_raw)
        if cid_key in exclude_ids:
            skipped_excluded += 1
            continue
        ok, issues = evaluate_case(row, kb_covers, dataset=args.dataset)
        if ok:
            selected_rows.append(row)
            continue
        cid = row.get("id")
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            pass
        exclusion_log.append({
            "id": cid,
            "final_diagnosis": row.get("Final Diagnosis"),
            "issues": issues,
        })

    out_dir.mkdir(parents=True, exist_ok=True)

    selected_df = pd.DataFrame(selected_rows)
    drop_cols = [c for c in selected_df.columns if str(c).startswith("_")]
    if drop_cols:
        selected_df = selected_df.drop(columns=drop_cols)
    cases_path = out_dir / "cases.parquet"
    selected_df.to_parquet(cases_path, index=False)

    ids_path = out_dir / "case_ids.txt"
    ids_path.write_text(
        "\n".join(str(int(x)) for x in selected_df["id"]) + "\n",
        encoding="utf-8",
    )

    exclusion_path = out_dir / "exclusion_log.jsonl"
    with exclusion_path.open("w", encoding="utf-8") as handle:
        for entry in exclusion_log:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    norm_path = out_dir / "normalized_cases.json"
    n_norm = write_normalized(args.dataset, cases_path, norm_path)

    if args.dataset == "medcasereasoning":
        split = "validation"
    elif args.dataset == "open_xddx":
        split = "all"
    elif args.dataset == "rarearena":
        split = "rdc"
    else:
        split = "test"

    def _rel(p: Path) -> str:
        return str(Path(p).expanduser().resolve().relative_to(ROOT.resolve()))

    manifest = {
        "schema_version": "1.0",
        "subset_version": version,
        "dataset": args.dataset,
        "split": split,
        "selection_policy": "sequential_by_source_id",
        "target_size": args.target_size,
        "selected_size": len(selected_df),
        "raw_path": _rel(raw_path),
        "scanned_until_selected": scanned,
        "skip_rows": int(args.skip_rows),
        "n_skipped_prefix": skipped_prefix,
        "n_skipped_excluded_ids": skipped_excluded,
        "exclude_ids_file": (
            _rel(args.exclude_ids_file) if args.exclude_ids_file is not None else None
        ),
        "n_exclude_ids": len(exclude_ids),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gates": {
            "disease_name": "heuristic + morpheme/eponym rules (see script)",
            "kb_coverage": "LR cache OR resolver OR DxS OR PrimeKG OR RAG text hit",
        },
        "notes": {
            "open_xddx_gold": (
                "proxy=max_grounded_rationale (Open-XDDx has no single-label gold)"
                if args.dataset == "open_xddx" else None
            ),
            "medcasereasoning_options": (
                "gold=final_diagnosis; distractors from diagnostic_reasoning"
                if args.dataset == "medcasereasoning" else None
            ),
            "rarearena": (
                "gold=Orpha_name|diagnosis; open vignette; singleton Options={A:gold}; "
                "sequential by Pubmed-style _id; default raw=RDC.json"
                if args.dataset == "rarearena" else None
            ),
            "continuation": (
                "Continues the same sequential scan after --skip-rows; "
                "exclude-ids-file is a hard anti-overlap guard."
                if int(args.skip_rows) or exclude_ids else None
            ),
        },
        "outputs": {
            "cases_parquet": _rel(cases_path),
            "case_ids": _rel(ids_path),
            "normalized_cases": _rel(norm_path),
            "exclusion_log": _rel(exclusion_path),
        },
        "id_range": {
            "first": int(selected_df["id"].iloc[0]) if len(selected_df) else None,
            "last": int(selected_df["id"].iloc[-1]) if len(selected_df) else None,
        },
        "exclusion_reason_counts": {},
        "n_normalized_cases": n_norm,
    }
    reason_counts: dict[str, int] = {}
    for entry in exclusion_log:
        for issue in entry["issues"]:
            key = "%s:%s" % (issue["gate"], issue["reason"])
            reason_counts[key] = reason_counts.get(key, 0) + 1
    manifest["exclusion_reason_counts"] = dict(sorted(reason_counts.items()))

    manifest_path = out_dir / "selection_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("\nSelected %d/%d cases" % (len(selected_df), args.target_size))
    print("Scanned %d rows sequentially" % scanned)
    print("Wrote %s" % cases_path)
    print("Wrote %s" % norm_path)
    print("Wrote %s" % manifest_path)
    if len(selected_df) < args.target_size:
        print("WARNING: target size not reached", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
