#!/usr/bin/env python3
"""Compare VignetteParser freeze versions: completeness checklist + hallucination audit."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import diagnosisarena_adapter as da  # noqa: E402

# Regression checklist from manual adjudication of v1 omissions.
REQUIRED_CUES: dict[str, list[tuple[str, list[str]]]] = {
    "11": [
        ("demographics_59F", ["59-year-old", "59 year old", "59yo", "woman", "female"]),
        ("orbital_pain", ["orbital pain"]),
        ("epiphora", ["epiphora"]),
        ("va_os", ["20/400"]),
        ("lacrimal_abscess", ["lacrimal sac abscess", "abscess"]),
        ("optic_nerve_injury", ["optic nerve"]),
        ("strep_pyogenes", ["streptococcus pyogenes", "s. pyogenes", "pyogenes"]),
    ],
    "3": [
        ("demographics_early50sF", ["early 50", "50s", "female", "woman"]),
        ("lesion_count_approx10", ["approximately 10", "about 10", "~10", "10 "]),
        ("compression_stockings", ["compression stocking"]),
        ("venous_pump", ["venous pump", "insufficient venous"]),
        ("krit1", ["krit1"]),
        ("family_ich", ["intracranial hemorrhage", "father"]),
    ],
    "4": [
        ("demographics_late20sF", ["late 20", "20s", "female", "woman"]),
        ("occasional_pain", ["pain"]),
        ("hhv8_neg", ["hhv-8", "hhv8", "herpesvirus 8"]),
        ("d2_40_neg", ["d2-40", "podoplanin"]),
        ("cd31_pos", ["cd31"]),
    ],
    "5": [
        ("demographics_teen_girl", ["teenage", "teen", "girl", "female"]),
        ("solid_and_cystic", ["solid", "cystic"]),
        ("opacifying", ["opacif"]),
        ("giant_cells", ["giant cell", "multinucleated"]),
        ("size_7cm", ["7.0", "7 ×", "7x"]),
    ],
    "7": [
        ("demographics_boy", ["boy", "male", "11-year-old", "11 year old"]),
        ("patella", ["patella"]),
        ("cd34", ["cd34"]),
        ("alcian_blue_neg", ["alcian"]),
        ("no_inflammation", ["no evidence of inflammation", "no inflammation"]),
    ],
}

STOP = {
    "with", "without", "from", "that", "this", "were", "been", "have", "into",
    "over", "left", "right", "both", "mild", "multiple", "direct", "image",
    "reference", "available", "text", "form", "showing", "results", "positive",
    "negative", "normal", "demonstrated", "revealed", "controlled", "history",
    "complaint", "patient", "years", "year", "days", "months", "weeks", "chief",
    "medical", "physical", "examination", "laboratory", "imaging", "studies",
    "demographics", "location", "patches", "plaques",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _tokens(text: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9×x./%\-]+", _norm(text))
        if len(t) >= 4 and t not in STOP
    ]


def evidence_blob(case: Mapping[str, Any]) -> str:
    return " ".join(
        str(item.get("content") or "")
        for item in (case.get("evidence_items") or ())
    )


def checklist_hits(
    case: Mapping[str, Any],
    cues: Sequence[tuple[str, list[str]]],
) -> dict[str, Any]:
    blob = _norm(evidence_blob(case))
    found, missing = [], []
    for label, kws in cues:
        if any(_norm(kw) in blob for kw in kws):
            found.append(label)
        else:
            missing.append(label)
    return {
        "found": found,
        "missing": missing,
        "n_found": len(found),
        "n_required": len(cues),
        "recall": round(len(found) / max(1, len(cues)), 3),
    }


def hallucination_audit(
    case: Mapping[str, Any],
    vignette_body: str,
) -> dict[str, Any]:
    body = _norm(vignette_body)
    body_tokens = set(_tokens(vignette_body))
    suspects: list[dict[str, Any]] = []
    for item in case.get("evidence_items") or ():
        content = str(item.get("content") or "")
        kind = str(item.get("kind") or "direct")
        # Protocol image placeholders are allowed if they quote a titled image.
        words = _tokens(content)
        if not words:
            continue
        hit = sum(1 for w in words if w in body_tokens or w in body)
        ratio = hit / len(words)
        absent = [w for w in words if w not in body_tokens and w not in body]
        # Flag only clearly weakly grounded direct/derived claims.
        if ratio < 0.5 and kind != "image_reference":
            suspects.append({
                "id": item.get("id"),
                "kind": kind,
                "content": content,
                "token_hit_ratio": round(ratio, 3),
                "absent_sample": absent[:12],
            })
        elif kind == "derived" and ratio < 0.7:
            suspects.append({
                "id": item.get("id"),
                "kind": kind,
                "content": content,
                "token_hit_ratio": round(ratio, 3),
                "absent_sample": absent[:12],
                "note": "derived weakly grounded",
            })
    return {
        "n_evidence": len(case.get("evidence_items") or ()),
        "n_suspect": len(suspects),
        "suspects": suspects,
    }


def load_frozen(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(
    *,
    cases_json: Path,
    old_path: Path,
    new_path: Path,
) -> dict[str, Any]:
    cases = {
        str(c["id"]): c
        for c in json.loads(cases_json.read_text(encoding="utf-8"))["cases"]
    }
    old = load_frozen(old_path)
    new = load_frozen(new_path)
    old_by = {str(c["case_id"]): c for c in old["cases"]}
    new_by = {str(c["case_id"]): c for c in new["cases"]}
    rows = []
    for cid in sorted(set(old_by) | set(new_by), key=str):
        cues = REQUIRED_CUES.get(cid, [])
        body = da.vignette_body(cases[cid]["case_text"])
        old_c = checklist_hits(old_by[cid], cues) if cid in old_by else None
        new_c = checklist_hits(new_by[cid], cues) if cid in new_by else None
        old_h = (
            hallucination_audit(old_by[cid], body) if cid in old_by else None
        )
        new_h = (
            hallucination_audit(new_by[cid], body) if cid in new_by else None
        )
        better = None
        if old_c and new_c and old_h and new_h:
            # Prefer higher checklist recall; tie-break fewer hallucinations,
            # then more evidence.
            old_score = (
                old_c["recall"],
                -old_h["n_suspect"],
                old_h["n_evidence"],
            )
            new_score = (
                new_c["recall"],
                -new_h["n_suspect"],
                new_h["n_evidence"],
            )
            better = "new" if new_score > old_score else (
                "old" if new_score < old_score else "tie"
            )
        rows.append({
            "case_id": cid,
            "old_checklist": old_c,
            "new_checklist": new_c,
            "old_hallucination": old_h,
            "new_hallucination": new_h,
            "better": better,
        })
    n_new_better = sum(1 for r in rows if r["better"] == "new")
    n_old_better = sum(1 for r in rows if r["better"] == "old")
    n_tie = sum(1 for r in rows if r["better"] == "tie")
    mean_new = sum(
        (r["new_checklist"] or {}).get("recall") or 0 for r in rows
    ) / max(1, len(rows))
    mean_old = sum(
        (r["old_checklist"] or {}).get("recall") or 0 for r in rows
    ) / max(1, len(rows))
    suspects_new = sum(
        (r["new_hallucination"] or {}).get("n_suspect") or 0 for r in rows
    )
    suspects_old = sum(
        (r["old_hallucination"] or {}).get("n_suspect") or 0 for r in rows
    )
    recommend_new = (
        mean_new > mean_old
        or (mean_new == mean_old and suspects_new <= suspects_old and n_new_better >= n_old_better)
    ) and suspects_new == 0
    # Allow promote if new is strictly better on recall and no increase in suspects
    recommend_new = (
        (mean_new > mean_old and suspects_new <= suspects_old)
        or (mean_new >= mean_old and suspects_new < suspects_old)
        or (mean_new >= 0.999 and suspects_new == 0 and mean_new >= mean_old)
    )
    return {
        "n_cases": len(rows),
        "mean_checklist_recall_old": round(mean_old, 3),
        "mean_checklist_recall_new": round(mean_new, 3),
        "hallucination_suspects_old": suspects_old,
        "hallucination_suspects_new": suspects_new,
        "n_new_better": n_new_better,
        "n_old_better": n_old_better,
        "n_tie": n_tie,
        "recommend_promote_new": bool(recommend_new),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases-json",
        type=Path,
        default=ROOT / "logs/diagnosisarena_d2_m01_v1/normalized_cases.json",
    )
    parser.add_argument(
        "--old",
        type=Path,
        default=ROOT / "logs/diagnosisarena_d2_m01_v1/vignette_parser_probe_v1/vignette_parser_frozen_v1.json",
    )
    parser.add_argument(
        "--new",
        type=Path,
        required=True,
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = compare(cases_json=args.cases_json, old_path=args.old, new_path=args.new)
    out = args.out or (args.new.parent / "compare_vs_v1.json")
    da._atomic_json(out, report)
    print(json.dumps({k: report[k] for k in report if k != "rows"}, indent=2))
    for row in report["rows"]:
        print(
            "case %s better=%s old_recall=%s new_recall=%s old_sus=%s new_sus=%s missing_new=%s"
            % (
                row["case_id"],
                row["better"],
                (row["old_checklist"] or {}).get("recall"),
                (row["new_checklist"] or {}).get("recall"),
                (row["old_hallucination"] or {}).get("n_suspect"),
                (row["new_hallucination"] or {}).get("n_suspect"),
                (row["new_checklist"] or {}).get("missing"),
            )
        )
    print("wrote", out)
    return 0 if report["recommend_promote_new"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
