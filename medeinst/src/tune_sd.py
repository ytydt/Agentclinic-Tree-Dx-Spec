"""Zero-call S(d) weight + override-margin search on an existing DCI run.

Replays stored causal graphs (audit user payload). No new LLM calls.

  PYTHONPATH=. python -m src.tune_sd \
    --run-dir runs/heldout_llama33_nomem_noleak_da200_mcr200
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
_PAPER = str(ROOT.parent / "scripts" / "paper")
if _PAPER not in sys.path:
    sys.path.insert(0, _PAPER)

from src.ablate_dci import _load_da_hits, _load_mcr_hits
from src.loss import (
    RelationCounts,
    ScoreWeights,
    count_relations_detailed,
    pick_diagnosis,
    score_from_counts,
)
from src.utils import normalize_diagnosis, parse_json_object

try:
    from mapper_bind_repair import leaf_match_score
except Exception:  # pragma: no cover
    def leaf_match_score(a: str, b: str) -> float:  # type: ignore
        na, nb = normalize_diagnosis(a), normalize_diagnosis(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        if na in nb or nb in na:
            return 0.92
        return 0.0


def _soft(gold: str, name: str) -> bool:
    if not gold or not name:
        return False
    g, n = normalize_diagnosis(gold), normalize_diagnosis(name)
    if g == n:
        return True
    if len(g) >= 6 and len(n) >= 6 and (g in n or n in g):
        return True
    return leaf_match_score(gold, name) >= 0.85


def _counts_to_dict(c: RelationCounts) -> dict[str, int]:
    return asdict(c)


def _counts_from_dict(d: MappingLike) -> RelationCounts:
    return RelationCounts(
        **{k: int(d.get(k, 0)) for k in RelationCounts.__dataclass_fields__}
    )


MappingLike = dict[str, Any]


@dataclass
class TuneCase:
    split: str
    slice_name: str
    case_id: str
    runtime_case_id: str
    fold: str  # tune | test  (even/odd case_id)
    gold: str
    gold_opt: str
    cot1: str
    dci: str
    dset: list[str]
    hit_cot: bool
    hit_dci: bool
    features: dict[str, dict[str, int]]  # disease -> RelationCounts dict


def _try_json(text: str) -> dict[str, Any] | None:
    try:
        obj = parse_json_object(text or "")
        return obj if isinstance(obj, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _load_gold_options(records_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not records_path.is_file():
        return out
    doc = json.loads(records_path.read_text(encoding="utf-8"))
    for row in doc.get("records") or []:
        sid = str(row.get("source_id") or "")
        letter = str(row.get("gold_letter") or "").upper()
        text = ""
        disputes = (((row.get("projection") or {}).get("audit") or {}).get("disputes")) or []
        for item in disputes:
            if str(item.get("option_letter") or "").upper() == letter:
                text = str(item.get("option_text") or "")
                break
        if sid and text:
            out[sid] = text
    return out


def extract_cases(run_dir: Path) -> list[TuneCase]:
    cases_raw = [
        json.loads(line)
        for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_key = {(str(r["slice"]), str(r["case_id"])): r for r in cases_raw}
    gold_opt = _load_gold_options(run_dir / "da" / "mapper" / "records.json")
    dci_da = _load_da_hits(run_dir / "da" / "mapper" / "records.json")
    cot_da = _load_da_hits(run_dir / "ablation_cot" / "da" / "mapper" / "records.json")
    dci_mcr = _load_mcr_hits(run_dir / "mcr" / "annotate" / "official_eval_llm" / "case_scores")
    cot_mcr = _load_mcr_hits(
        run_dir / "ablation_cot" / "mcr" / "annotate" / "official_eval_llm" / "case_scores"
    )

    cot_map: dict[tuple[str, str], list[str]] = {}
    graphs: dict[tuple[str, str], dict[str, Any]] = {}
    for line in (run_dir / "llm_calls.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        key = (str(rec.get("slice") or ""), str(rec.get("case_id") or ""))
        stage = rec.get("stage")
        if stage == "intuitive":
            obj = _try_json(str(rec.get("assistant") or ""))
            names: list[str] = []
            if obj:
                for item in obj.get("diagnoses") or []:
                    if isinstance(item, dict) and item.get("name"):
                        names.append(str(item["name"]))
            cot_map[key] = names
        elif stage == "audit" and key not in graphs:
            obj = _try_json(str(rec.get("user") or ""))
            if obj and isinstance(obj.get("graph_summary"), dict):
                graphs[key] = obj["graph_summary"]

    out: list[TuneCase] = []
    for key, row in by_key.items():
        split = "da" if str(row["slice"]).startswith("d2_") else "mcr"
        cid = str(row["case_id"])
        dset = [str(x) for x in (row.get("dset") or []) if str(x).strip()]
        cot = cot_map.get(key) or dset
        cot1 = cot[0] if cot else (dset[0] if dset else "")
        dci = str(row.get("diagnosis") or "")
        gold = str(row.get("y_gt") or "")
        summary = graphs.get(key) or {}
        feats: dict[str, dict[str, int]] = {}
        for name in dset:
            feats[name] = _counts_to_dict(count_relations_detailed(summary, name))
        try:
            fold = "tune" if int(cid) % 2 == 0 else "test"
        except ValueError:
            fold = "tune" if (sum(map(ord, cid)) % 2 == 0) else "test"
        if split == "da":
            hit_cot = bool(cot_da.get(cid) or cot_da.get(str(row.get("runtime_case_id") or "")))
            hit_dci = bool(dci_da.get(cid) or dci_da.get(str(row.get("runtime_case_id") or "")))
        else:
            hit_cot = bool(cot_mcr.get(cid))
            hit_dci = bool(dci_mcr.get(cid))
        out.append(
            TuneCase(
                split=split,
                slice_name=str(row["slice"]),
                case_id=cid,
                runtime_case_id=str(row.get("runtime_case_id") or cid),
                fold=fold,
                gold=gold,
                gold_opt=gold_opt.get(cid, "") if split == "da" else "",
                cot1=cot1,
                dci=dci,
                dset=dset,
                hit_cot=hit_cot,
                hit_dci=hit_dci,
                features=feats,
            )
        )
    return out


def official_or_proxy(case: TuneCase, pick: str) -> bool:
    """Reuse mapper/Prompt7 when pick is a known arm; else lexical/leaf proxy."""
    npick = normalize_diagnosis(pick)
    if npick == normalize_diagnosis(case.dci):
        return case.hit_dci
    if npick == normalize_diagnosis(case.cot1):
        return case.hit_cot
    if case.split == "da":
        return _soft(case.gold_opt, pick) or _soft(case.gold, pick)
    return _soft(case.gold, pick)


def known_official(case: TuneCase, pick: str) -> bool | None:
    npick = normalize_diagnosis(pick)
    if npick == normalize_diagnosis(case.dci):
        return case.hit_dci
    if npick == normalize_diagnosis(case.cot1):
        return case.hit_cot
    return None


def scores_for(case: TuneCase, weights: ScoreWeights) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, feat in case.features.items():
        out[name] = score_from_counts(_counts_from_dict(feat), weights)
    return out


def pick_for(case: TuneCase, weights: ScoreWeights) -> str:
    return pick_diagnosis(
        case.dset,
        scores_for(case, weights),
        cot1=case.cot1,
        override_margin=weights.override_margin,
        tie_break=weights.tie_break,
    )


def summarize(cases: list[TuneCase], picks: dict[str, str]) -> dict[str, Any]:
    def acc(subset: list[TuneCase], fn) -> float | None:
        if not subset:
            return None
        return round(sum(1 for c in subset if fn(c)) / len(subset), 4)

    def key(c: TuneCase) -> str:
        return f"{c.split}:{c.case_id}"

    da = [c for c in cases if c.split == "da"]
    mcr = [c for c in cases if c.split == "mcr"]
    reuse_n = 0
    new_n = 0
    for c in cases:
        if known_official(c, picks[key(c)]) is None:
            new_n += 1
        else:
            reuse_n += 1
    override = sum(
        1
        for c in cases
        if normalize_diagnosis(picks[key(c)]) != normalize_diagnosis(c.cot1)
    )
    return {
        "n": len(cases),
        "da_proxy": acc(da, lambda c: official_or_proxy(c, picks[key(c)])),
        "mcr_proxy": acc(mcr, lambda c: official_or_proxy(c, picks[key(c)])),
        "da_cot": acc(da, lambda c: c.hit_cot),
        "mcr_cot": acc(mcr, lambda c: c.hit_cot),
        "da_dci_llm": acc(da, lambda c: c.hit_dci),
        "mcr_dci_llm": acc(mcr, lambda c: c.hit_dci),
        "eq_cot1": round(
            sum(
                1
                for c in cases
                if normalize_diagnosis(picks[key(c)]) == normalize_diagnosis(c.cot1)
            )
            / len(cases),
            4,
        )
        if cases
        else None,
        "n_override": override,
        "n_official_reuse": reuse_n,
        "n_proxy_only": new_n,
        "joint": None,
    }


def _attach_joint(stats: dict[str, Any]) -> dict[str, Any]:
    da = stats.get("da_proxy")
    mcr = stats.get("mcr_proxy")
    if da is None or mcr is None:
        stats["joint"] = None
    else:
        stats["joint"] = round(0.5 * da + 0.5 * mcr, 4)
    return stats


def eval_weights(cases: list[TuneCase], weights: ScoreWeights) -> dict[str, str]:
    return {f"{c.split}:{c.case_id}": pick_for(c, weights) for c in cases}


def grid() -> Iterator[ScoreWeights]:
    for w_m, w_c, w_s, w_sup, w_ro, w_pv, gscale, absent, norm, tau, dq in itertools.product(
        (0.5, 1.0, 2.0),
        (0.0, 1.0, 2.0, 4.0),
        (0.0, 0.5, 1.0, 2.0, 4.0),
        (0.0, 0.5),
        (0.0, 1.0),
        (0.0, 1.0),
        (0.0, 1.0),
        (False, True),
        ("none", "n_k"),
        (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 99.0),
        (False, True),
    ):
        yield ScoreWeights(
            w_match=w_m,
            w_conflict=w_c,
            w_shadow=w_s,
            w_support=w_sup,
            w_ruleout=w_ro,
            w_pivot=w_pv,
            generic_match_scale=gscale,
            absent_match_as_conflict=absent,
            normalize=norm,
            disqualify_absent_pivot=dq,
            override_margin=tau,
            tie_break="cot1",
            audit_mode="cot_unless_margin",
        )


def _rank_key(tune: dict[str, Any], weights: ScoreWeights) -> tuple:
    # Prefer MCR (where LLM-DCI hurt), then DA, then fewer overrides (larger margin).
    mcr = tune.get("mcr_proxy") or 0.0
    da = tune.get("da_proxy") or 0.0
    cot_mcr = tune.get("mcr_cot") or 0.0
    cot_da = tune.get("da_cot") or 0.0
    # Soft penalty if we fall below CoT on either slice.
    penalty = 0.0
    if mcr + 1e-9 < cot_mcr:
        penalty += 10.0 * (cot_mcr - mcr)
    if da + 1e-9 < cot_da - 0.02:
        penalty += 5.0 * ((cot_da - 0.02) - da)
    return (
        round(mcr - penalty, 6),
        round(da - penalty, 6),
        float(weights.override_margin),
        -float(weights.w_match),
    )


def write_replay(
    run_dir: Path,
    cases: list[TuneCase],
    picks: dict[str, str],
    dest: Path,
    weights: ScoreWeights,
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "da").mkdir(exist_ok=True)
    (dest / "mcr").mkdir(exist_ok=True)
    by_raw = {
        (str(row["slice"]), str(row["case_id"])): row
        for row in [
            json.loads(line)
            for line in (run_dir / "cases.jsonl").read_text().splitlines()
            if line.strip()
        ]
    }
    pred_lines: dict[str, list[str]] = {"da": [], "mcr": []}
    case_lines = []
    for case in cases:
        pick = picks[f"{case.split}:{case.case_id}"]
        raw = by_raw[(case.slice_name, case.case_id)]
        scores = scores_for(case, weights)
        row = dict(raw)
        row["diagnosis"] = pick
        row["scores"] = scores
        row["repair"] = "sd_tuned_no_llm_audit"
        row["correct"] = _soft(case.gold, pick)
        case_lines.append(json.dumps(row, ensure_ascii=False))
        ordered: list[str] = []
        for name in [pick, *case.dset]:
            if name and not any(name.casefold() == seen.casefold() for seen in ordered):
                ordered.append(name)
            if len(ordered) >= 5:
                break
        while len(ordered) < 5:
            ordered.append("")
        pred = {
            "case_id": case.runtime_case_id,
            "source_id": case.case_id,
            "arm": "ecr_agent_dci_sd_tuned",
            "replicate": 1,
            "list_k": 5,
            "ordered_diagnoses": ordered,
            "top2_diagnoses": ordered[:2],
            "slice": case.slice_name,
            "cost": {"n_llm_calls": 0, "replay": True},
            "options_stripped": True,
        }
        pred_lines[case.split].append(json.dumps(pred, ensure_ascii=False))
    (dest / "cases.jsonl").write_text("\n".join(case_lines) + "\n", encoding="utf-8")
    for split in ("da", "mcr"):
        (dest / split / "predictions.jsonl").write_text(
            "\n".join(pred_lines[split]) + "\n", encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-dir",
        default="runs/heldout_llama33_nomem_noleak_da200_mcr200",
    )
    parser.add_argument("--max-report", type=int, default=8)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()

    print("[tune_sd] extracting graphs from traces …", flush=True)
    cases = extract_cases(run_dir)
    cache = run_dir / "sd_features.json"
    cache.write_text(
        json.dumps(
            [
                {
                    "split": c.split,
                    "case_id": c.case_id,
                    "fold": c.fold,
                    "gold": c.gold,
                    "gold_opt": c.gold_opt,
                    "cot1": c.cot1,
                    "dci": c.dci,
                    "dset": c.dset,
                    "hit_cot": c.hit_cot,
                    "hit_dci": c.hit_dci,
                    "features": c.features,
                }
                for c in cases
            ],
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    tune_cs = [c for c in cases if c.fold == "tune"]
    test_cs = [c for c in cases if c.fold == "test"]
    print(f"[tune_sd] n={len(cases)} tune={len(tune_cs)} test={len(test_cs)}", flush=True)

    baselines: dict[str, ScoreWeights] = {
        "paper_1_1_1_argmax": ScoreWeights(audit_mode="argmax", override_margin=0.0),
        "paper_1_1_1_tau2": ScoreWeights(audit_mode="cot_unless_margin", override_margin=2.0),
        "paper_1_1_1_tau4": ScoreWeights(audit_mode="cot_unless_margin", override_margin=4.0),
        "always_cot": ScoreWeights(audit_mode="cot_unless_margin", override_margin=99.0),
    }

    def pack(name: str, w: ScoreWeights) -> dict[str, Any]:
        pt = eval_weights(tune_cs, w)
        ps = eval_weights(test_cs, w)
        pa = eval_weights(cases, w)
        return {
            "name": name,
            "weights": asdict(w),
            "tune": _attach_joint(summarize(tune_cs, pt)),
            "test": _attach_joint(summarize(test_cs, ps)),
            "all": _attach_joint(summarize(cases, pa)),
        }

    baseline_rows = [pack(n, w) for n, w in baselines.items()]
    # LLM audit as a pseudo-policy
    llm_picks = {f"{c.split}:{c.case_id}": c.dci for c in cases}
    llm_row = {
        "name": "llm_audit_current",
        "weights": None,
        "tune": _attach_joint(
            summarize(tune_cs, {f"{c.split}:{c.case_id}": c.dci for c in tune_cs})
        ),
        "test": _attach_joint(
            summarize(test_cs, {f"{c.split}:{c.case_id}": c.dci for c in test_cs})
        ),
        "all": _attach_joint(summarize(cases, llm_picks)),
    }

    print("[tune_sd] grid search …", flush=True)
    best: tuple | None = None
    best_w: ScoreWeights | None = None
    best_tune: dict[str, Any] | None = None
    n_grid = 0
    for weights in grid():
        n_grid += 1
        picks = eval_weights(tune_cs, weights)
        stats = _attach_joint(summarize(tune_cs, picks))
        key = _rank_key(stats, weights)
        if best is None or key > best:
            best = key
            best_w = weights
            best_tune = stats
        if n_grid % 20000 == 0:
            print(f"  … {n_grid} configs, current best MCR={best_tune and best_tune.get('mcr_proxy')}", flush=True)

    assert best_w is not None and best_tune is not None
    winner = pack("grid_winner_tune_only", best_w)
    # A few nearby reports: top is winner; also always_cot already in baselines

    report = {
        "protocol": {
            "no_new_llm_calls": True,
            "split": "even case_id = tune, odd = test, within each slice",
            "objective": "max MCR proxy on tune, then DA, then larger override_margin; penalize dropping below CoT",
            "proxy": (
                "If pick equals CoT@1 or LLM-DCI diagnosis, reuse official mapper@1 / Prompt7. "
                "Else DA leaf_match vs gold option, MCR soft/leaf vs gold."
            ),
            "n_grid": n_grid,
        },
        "llm_audit_current": llm_row,
        "baselines": baseline_rows,
        "winner": winner,
    }
    out_path = run_dir / "sd_tune_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replay = run_dir / "sd_replay"
    all_picks = eval_weights(cases, best_w)
    write_replay(run_dir, cases, all_picks, replay, best_w)
    print(json.dumps({"wrote": str(out_path), "replay": str(replay), "winner": winner}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
