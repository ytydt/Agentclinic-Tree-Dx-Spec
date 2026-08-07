#!/usr/bin/env python3
"""RA four-way root-cause autopsy: Ours / B04 / B00 / B06.

Writes analysis/transfer_metrics_v1/ra_rootcause_mechanisms.{md,json}.
Read-only over existing case_scores / trees / case_results / baseline runs.
Does not overwrite F6 Acc=0.47.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from audit_ox_budget_recalib import scored_active_leaves  # noqa: E402
from audit_ox_c2a_force_emit import _labs  # noqa: E402
from audit_ra_budget_recalib import _gold_map, _hit  # noqa: E402
from audit_ra_within_family_offline import (  # noqa: E402
    _climb_l1,
    _fam_mass,
    _gold_leaves_fams,
)
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_OURS = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_BASE = ROOT / "runs/paper_v1/rarearena_ra_rdc_seq100_v1"
DEFAULT_JSON = ROOT / "analysis/transfer_metrics_v1/ra_rootcause_mechanisms.json"
DEFAULT_MD = ROOT / "analysis/transfer_metrics_v1/ra_rootcause_mechanisms.md"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _load_hits(score_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in score_dir.glob("*.json"):
        if p.name.startswith("_"):
            continue
        d = _read_json(p)
        out[p.stem] = {
            "hit": bool(d.get("diagnostic_hit")),
            "pred": str(d.get("pred_diagnosis") or ""),
            "gold": str(d.get("gold_diagnosis") or ""),
        }
    return out


def _token_overlap(a: str, b: str) -> float:
    ta = {t for t in a.casefold().replace("-", " ").replace("/", " ").split() if t}
    tb = {t for t in b.casefold().replace("-", " ").replace("/", " ").split() if t}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def _fr_labels(case_doc: Mapping[str, Any]) -> list[str]:
    fr = (case_doc.get("l2") or {}).get("final_ranking_labels") or []
    out: list[str] = []
    for x in fr:
        if isinstance(x, dict):
            lab = str(x.get("label") or "").strip()
        else:
            lab = str(x).strip()
        if lab:
            out.append(lab)
    return out


def classify_case(
    *,
    cid: str,
    gold: str,
    judge: LexicalJudge,
    tree: Mapping[str, Any] | None,
    case_doc: Mapping[str, Any] | None,
    ours: Mapping[str, Any],
    b04: Mapping[str, Any],
    b00: Mapping[str, Any],
    b06: Mapping[str, Any],
) -> dict[str, Any]:
    am = ((case_doc or {}).get("l2") or {}).get("auto_metrics") or {}
    fr = _fr_labels(case_doc or {})
    ranking_len = len(fr)

    has_gold_leaf = False
    gold_fams: set[str] = set()
    l1_correct = False
    within_wrong = False
    champion_has_gold = False
    structural_reach = am.get("structural_reach")
    local_champion_recall = am.get("local_champion_recall")

    if tree:
        # Accept either raw tree doc or deserialized state (branches at top).
        state = tree.get("state") if isinstance(tree.get("state"), dict) else tree
        br = (state or {}).get("branches") or {}
        leaves = [b for b in br.values() if not (b.get("children") or [])]
        gold_leaves, gold_fams = _gold_leaves_fams(br, leaves, gold, judge)
        has_gold_leaf = bool(gold_leaves)
        l1 = [b for b in br.values() if int(b.get("level") or 0) == 1]
        fam_ranked = sorted(
            l1, key=lambda b: (-_fam_mass(br, b), str(b.get("id") or ""))
        )
        top_fam = str(fam_ranked[0]["id"]) if fam_ranked else None
        l1_correct = bool(top_fam and top_fam in gold_fams)
        if has_gold_leaf and gold_fams and l1_correct:
            fam_id = max(gold_fams, key=lambda fid: _fam_mass(br, br.get(fid) or {}))
            kids = [
                br[c]
                for c in ((br.get(fam_id) or {}).get("children") or [])
                if isinstance(br.get(c), dict)
            ]
            kids_sorted = sorted(
                kids,
                key=lambda b: (
                    -float(b.get("posterior") or 0.0),
                    str(b.get("id") or ""),
                ),
            )
            gold_ids = {
                str(b["id"]) for b in gold_leaves if _climb_l1(br, b) == fam_id
            }
            if kids_sorted and gold_ids:
                within_wrong = str(kids_sorted[0].get("id")) not in gold_ids

        # champions ≈ final_ranking parents' first leaves + ranking itself
        champion_has_gold = any(_hit(judge, lab, gold) for lab in fr)
        if not champion_has_gold and local_champion_recall is True:
            champion_has_gold = True
        # also check scored leaves for gold-in-leaf funnel
        leaf_labs = _labs(scored_active_leaves(state))
        gold_in_leaf_pool = any(_hit(judge, x, gold) for x in leaf_labs)
    else:
        gold_in_leaf_pool = False
        leaf_labs = []

    ours_hit = bool(ours.get("hit"))
    b04_hit = bool(b04.get("hit"))
    b00_hit = bool(b00.get("hit"))
    b06_hit = bool(b06.get("hit"))
    flat_hit = b00_hit or b06_hit
    ours_pred = str(ours.get("pred") or "")
    lex_top1 = bool(fr and _hit(judge, fr[0], gold))

    # Mutual-exclusive priority bucket for Ours misses (and also tag successes).
    bucket = "success"
    if ours_hit:
        bucket = "success"
    elif not has_gold_leaf:
        bucket = "no_gold_leaf"
    elif has_gold_leaf and structural_reach is False:
        bucket = "bind_reach_gap"
    elif has_gold_leaf and l1_correct and within_wrong:
        bucket = "within_family_wrong_leaf"
    elif champion_has_gold and not lex_top1:
        bucket = "arbiter_demote"
    elif flat_hit and not b04_hit:
        bucket = "flat_only_win"
    elif flat_hit or b04_hit:
        # strong baseline recovers with different name grain
        ov = max(
            _token_overlap(ours_pred, gold),
            _token_overlap(str(b00.get("pred") or ""), gold),
            _token_overlap(str(b04.get("pred") or ""), gold),
        )
        if ov < 0.55 or (
            ours_pred
            and gold
            and ours_pred.casefold() != gold.casefold()
            and not _hit(judge, ours_pred, gold)
        ):
            bucket = "granularity_name"
        else:
            bucket = "near_neighbor_other"
    else:
        bucket = "all_miss"

    tags: list[str] = []
    if not has_gold_leaf:
        tags.append("no_gold_leaf")
    if within_wrong:
        tags.append("within_family_wrong_leaf")
    if champion_has_gold and not lex_top1 and not ours_hit:
        tags.append("arbiter_demote")
    if structural_reach is False and has_gold_leaf:
        tags.append("bind_reach_gap")
    if flat_hit and not ours_hit and not b04_hit:
        tags.append("flat_only_win")
    if (b00_hit or b04_hit or b06_hit) and not ours_hit:
        tags.append("strong_baseline_recoverable")

    return {
        "case_id": cid,
        "gold": gold,
        "bucket": bucket,
        "tags": tags,
        "ours_hit": ours_hit,
        "b04_hit": b04_hit,
        "b00_hit": b00_hit,
        "b06_hit": b06_hit,
        "ours_pred": ours_pred,
        "b04_pred": str(b04.get("pred") or ""),
        "b00_pred": str(b00.get("pred") or ""),
        "b06_pred": str(b06.get("pred") or ""),
        "has_gold_leaf": has_gold_leaf,
        "gold_in_leaf_pool": gold_in_leaf_pool,
        "l1_correct": l1_correct,
        "within_wrong": within_wrong,
        "champion_has_gold": champion_has_gold,
        "lex_top1": lex_top1,
        "ranking_len": ranking_len,
        "final_ranking": fr,
        "structural_reach": structural_reach,
        "local_champion_recall": local_champion_recall,
        "error_attribution": am.get("error_attribution"),
        "n_leaves": len(leaf_labs),
    }


def _funnel(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(cases)
    leaf = sum(1 for c in cases if c.get("has_gold_leaf") or c.get("gold_in_leaf_pool"))
    # Use has_gold_leaf as primary (Lexical on leaves)
    leaf = sum(1 for c in cases if c.get("has_gold_leaf"))
    champ = sum(1 for c in cases if c.get("champion_has_gold"))
    fr_hit = sum(
        1
        for c in cases
        if c.get("champion_has_gold") and (c.get("ranking_len") or 0) > 0
    )
    lex = sum(1 for c in cases if c.get("lex_top1"))
    llm = sum(1 for c in cases if c.get("ours_hit"))
    mean_rank = (
        sum(int(c.get("ranking_len") or 0) for c in cases) / n if n else 0.0
    )
    return {
        "n": n,
        "gold_in_leaf": leaf,
        "gold_in_champions_or_ranking": champ,
        "has_final_ranking": fr_hit,
        "lex_top1": lex,
        "llm_hit": llm,
        "mean_ranking_len": round(mean_rank, 3),
        "conversion_champ_to_lex": (lex / champ) if champ else None,
        "conversion_champ_to_llm": (llm / champ) if champ else None,
    }


def _set_ids(cases: Sequence[Mapping[str, Any]], pred) -> list[str]:
    return sorted(
        (str(c["case_id"]) for c in cases if pred(c)),
        key=lambda x: int(x) if x.isdigit() else x,
    )


def render_md(doc: Mapping[str, Any]) -> str:
    f = doc["funnels"]["ours"]
    buckets = doc["bucket_counts"]
    wins = doc["exclusive_wins"]
    ops = doc["transfer_operators"]
    lines = [
        "# RA 根因深挖与强基线机制对照",
        "",
        f"协议：`{doc['protocol']}`  · 生成：`{doc['created_at']}`",
        f"锚点 Ours F6 LLM Acc = **{doc['acc']['ours']}**（不覆盖）",
        f"机器表：[`ra_rootcause_mechanisms.json`](ra_rootcause_mechanisms.json)",
        "",
        "## 1. Headline Acc",
        "",
        "| 臂 | LLM Acc | Hits |",
        "|----|--------:|------:|",
        f"| Ours F6 | **{doc['acc']['ours']}** | {doc['acc']['ours_hits']} |",
        f"| B04 Dual-Inf | {doc['acc']['b04']} | {doc['acc']['b04_hits']} |",
        f"| B00 Direct-CoT (#2) | {doc['acc']['b00']} | {doc['acc']['b00_hits']} |",
        f"| B06 MAC (并列 #2) | {doc['acc']['b06']} | {doc['acc']['b06_hits']} |",
        f"| 四者并集 oracle | {doc['acc']['union4']} | {doc['acc']['union4_hits']} |",
        "",
        "## 2. Ours 转化漏斗",
        "",
        f"gold∈leaf **{f['gold_in_leaf']}** → champion/ranking 含金 "
        f"**{f['gold_in_champions_or_ranking']}** → Lex top-1 **{f['lex_top1']}** "
        f"→ LLM **{f['llm_hit']}**；`final_ranking` 均长 **{f['mean_ranking_len']}**。",
        "",
        f"冠军→Lex 转化率 = **{f['conversion_champ_to_lex']}**；"
        f"冠军→LLM = **{f['conversion_champ_to_llm']}**。",
        "",
        "B04（文档口径）：候选约 45 → top-1 LLM 42（转化 ~93%），本表复算：",
        f"- B04 LLM hits={doc['acc']['b04_hits']}；"
        f"相对 Ours 独赢 {len(wins['b04_only_vs_ours'])} / "
        f"Ours 独赢 {len(wins['ours_only_vs_b04'])}。",
        "",
        "## 3. 失败类型学（Ours miss 互斥优先桶）",
        "",
        "| bucket | n |",
        "|--------|--:|",
    ]
    for k, v in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{k}` | {v} |")
    lines += [
        "",
        "权威对照：无叶≈26、组内错叶、仲裁降位、绑定缝、粒度命名、平坦独赢。",
        "",
        "### 代表例（每桶最多 6）",
        "",
    ]
    for buck, rows in (doc.get("bucket_examples") or {}).items():
        lines.append(f"**`{buck}`**")
        for r in rows[:6]:
            lines.append(
                f"- {r['case_id']}: ours=`{r['ours_pred']}` | "
                f"b04=`{r['b04_pred']}` | b00=`{r['b00_pred']}` | "
                f"gold=`{r['gold']}`"
            )
        lines.append("")

    lines += [
        "## 4. 独赢集合",
        "",
        f"- B04-only vs Ours ({len(wins['b04_only_vs_ours'])}): "
        f"`{', '.join(wins['b04_only_vs_ours'])}`",
        f"- B00-only vs Ours ({len(wins['b00_only_vs_ours'])}): "
        f"`{', '.join(wins['b00_only_vs_ours'])}`",
        f"- B06-only vs Ours ({len(wins['b06_only_vs_ours'])}): "
        f"`{', '.join(wins['b06_only_vs_ours'])}`",
        f"- B00∩B04 vs Ours miss ({len(wins['b00_and_b04_vs_ours'])}): "
        f"`{', '.join(wins['b00_and_b04_vs_ours'])}`",
        f"- flat-only (B00/B06 hit, Ours+B04 miss) ({len(wins['flat_only'])}): "
        f"`{', '.join(wins['flat_only'])}`",
        f"- strong-baseline recoverable ({len(wins['strong_recoverable'])}): "
        f"`{', '.join(wins['strong_recoverable'])}`",
        f"- Ours-only vs B04 ({len(wins['ours_only_vs_b04'])}): "
        f"`{', '.join(wins['ours_only_vs_b04'])}`",
        "",
        "### 机制短评",
        "",
        "- **B04 独赢**：近邻混淆上 examine/support 计数纠偏（Castleman、Cushing、"
        "Primary peritoneal、Mucormycosis 等）；转化率高。",
        "- **B00/B06**：与 B04 高度重叠；额外贡献平坦金标粒度命名"
        f"（flat-only={wins['flat_only']}）。",
        "- **Ours 独赢**：罕见具名实体召回（Desmoid 等）；无条件 Dual-Inf 重排常毁掉这类。",
        "",
        "## 5. 机制差异（写死）",
        "",
        "1. **Ours 偏低**：召回尚可（叶≈74、冠军池≈58），但 `final_ranking` 极短 + "
        "`explanatory_coverage≡0` → 承诺不足；另加 Orpha 无叶天花板与叶名粒度错位。",
        "2. **Dual-Inf 相对优秀**：在已混淆近邻上 backward+examine 做 support 承诺；"
        "少受「错细叶绑定」约束。",
        "3. **B00/B06 高**：平坦空间直接以金标粒度命名；MAC 多列表裁决与 CoT 单跳在 "
        "RA 上几乎同向。",
        "",
        "## 6. 可迁移算子（Phase B）",
        "",
        "| 算子 | 借自 | 作用点 | 针对桶 | 护栏 |",
        "|------|------|--------|--------|------|",
    ]
    for op in ops:
        lines.append(
            f"| `{op['name']}` | {op['source']} | {op['hook']} | "
            f"{op['buckets']} | {op['guardrail']} |"
        )
    lines += [
        "",
        "**约束**：默认保留树 top-1；不迁整段 MAC 建树 / 开放重生成主诊断；"
        "不用 Live S3 coverage 作主信号；正式 F6 Acc 不覆盖。",
        "",
        "## 7. 验证栈指针",
        "",
        "- C1 Gate δ sweep → `run_ra_dualinf_conditional_gate.py`",
        "- C2 Pair adjudicate → `run_ra_pair_adjudicate.py`",
        "- C3 Grain alias → `run_ra_grain_alias_align.py`",
        "- C4 Combo → `run_ra_transfer_combo.py`",
        "",
        "## 8. 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ra_rootcause_mechanisms.py",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ours-run", type=Path, default=DEFAULT_OURS)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--baselines-root", type=Path, default=DEFAULT_BASE)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    args = ap.parse_args(list(argv) if argv is not None else None)

    subset = Path(args.subset_dir)
    ids = [
        ln.strip()
        for ln in (subset / "case_ids.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    gold_by = _gold_map(subset / "cases.parquet", ids)
    judge = LexicalJudge()

    ours_h = _load_hits(
        Path(args.ours_run) / "annotate/official_eval_llm_compat/case_scores"
    )
    b04_h = _load_hits(
        Path(args.baselines_root)
        / "B04-dual-inf/replicate_01/annotate/official_eval_llm/case_scores"
    )
    b00_h = _load_hits(
        Path(args.baselines_root)
        / "B00-direct-cot/replicate_01/annotate/official_eval_llm/case_scores"
    )
    b06_h = _load_hits(
        Path(args.baselines_root)
        / "B06-mac-single-vendor/replicate_01/annotate/official_eval_llm/case_scores"
    )

    trees_dir = Path(args.ours_run) / "annotate/shared_trees"
    cr_dir = Path(args.ours_run) / "annotate/case_results"

    cases: list[dict[str, Any]] = []
    for cid in ids:
        tree = None
        tp = trees_dir / f"{cid}.json"
        if tp.is_file():
            try:
                tree = {"state": bep.load_tree_state(tp)}
            except Exception:  # noqa: BLE001
                tree = _read_json(tp)
        case_doc = None
        cp = cr_dir / f"{cid}.json"
        if cp.is_file():
            case_doc = _read_json(cp)
        gold = gold_by.get(cid) or (ours_h.get(cid) or {}).get("gold") or ""
        cases.append(
            classify_case(
                cid=cid,
                gold=gold,
                judge=judge,
                tree=tree,
                case_doc=case_doc,
                ours=ours_h.get(cid) or {},
                b04=b04_h.get(cid) or {},
                b00=b00_h.get(cid) or {},
                b06=b06_h.get(cid) or {},
            )
        )

    bucket_counts = Counter(c["bucket"] for c in cases)
    # For miss-focused view also count tags
    tag_counts = Counter(t for c in cases for t in c.get("tags") or [])

    bucket_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cases:
        if c["bucket"] == "success":
            continue
        bucket_examples[c["bucket"]].append(
            {
                "case_id": c["case_id"],
                "gold": c["gold"],
                "ours_pred": c["ours_pred"],
                "b04_pred": c["b04_pred"],
                "b00_pred": c["b00_pred"],
                "b06_pred": c["b06_pred"],
            }
        )

    wins = {
        "b04_only_vs_ours": _set_ids(
            cases, lambda c: c["b04_hit"] and not c["ours_hit"]
        ),
        "b00_only_vs_ours": _set_ids(
            cases, lambda c: c["b00_hit"] and not c["ours_hit"]
        ),
        "b06_only_vs_ours": _set_ids(
            cases, lambda c: c["b06_hit"] and not c["ours_hit"]
        ),
        "ours_only_vs_b04": _set_ids(
            cases, lambda c: c["ours_hit"] and not c["b04_hit"]
        ),
        "b00_and_b04_vs_ours": _set_ids(
            cases,
            lambda c: c["b00_hit"] and c["b04_hit"] and not c["ours_hit"],
        ),
        "flat_only": _set_ids(
            cases,
            lambda c: (c["b00_hit"] or c["b06_hit"])
            and not c["ours_hit"]
            and not c["b04_hit"],
        ),
        "strong_recoverable": _set_ids(
            cases,
            lambda c: not c["ours_hit"]
            and (c["b04_hit"] or c["b00_hit"] or c["b06_hit"]),
        ),
    }

    n = len(cases)
    acc = {
        "ours": sum(c["ours_hit"] for c in cases) / n,
        "ours_hits": sum(c["ours_hit"] for c in cases),
        "b04": sum(c["b04_hit"] for c in cases) / n,
        "b04_hits": sum(c["b04_hit"] for c in cases),
        "b00": sum(c["b00_hit"] for c in cases) / n,
        "b00_hits": sum(c["b00_hit"] for c in cases),
        "b06": sum(c["b06_hit"] for c in cases) / n,
        "b06_hits": sum(c["b06_hit"] for c in cases),
        "union4": sum(
            c["ours_hit"] or c["b04_hit"] or c["b00_hit"] or c["b06_hit"]
            for c in cases
        )
        / n,
        "union4_hits": sum(
            c["ours_hit"] or c["b04_hit"] or c["b00_hit"] or c["b06_hit"]
            for c in cases
        ),
    }

    transfer_operators = [
        {
            "name": "support_examine_gate",
            "source": "B04 Dual-Inf",
            "hook": "frozen champions/padded-ddx; override iff Δsupport≥δ",
            "buckets": "arbiter_demote / near-neighbor",
            "guardrail": "keep tree top-1 unless delta met",
            "script": "scripts/paper/run_ra_dualinf_conditional_gate.py",
        },
        {
            "name": "pair_adjudicate",
            "source": "B06 MAC supervisor (shrunk)",
            "hook": "pair LLM choose when top1–top2 near-tie",
            "buckets": "within_family_wrong_leaf / near ties",
            "guardrail": "only swap order; never open regenerate",
            "script": "scripts/paper/run_ra_pair_adjudicate.py",
        },
        {
            "name": "grain_alias_align",
            "source": "B00 Direct-CoT naming",
            "hook": "eval-time Orpha/synonym display-name align on top-1/ddx",
            "buckets": "granularity_name / partial no_gold_leaf",
            "guardrail": "do not change tree posteriors",
            "script": "scripts/paper/run_ra_grain_alias_align.py",
        },
    ]

    doc = {
        "protocol": "ra_rootcause_mechanisms_v1",
        "created_at": _utc(),
        "ours_run": str(args.ours_run),
        "n": n,
        "acc": acc,
        "funnels": {"ours": _funnel(cases)},
        "bucket_counts": dict(bucket_counts),
        "tag_counts": dict(tag_counts),
        "bucket_examples": {k: v[:8] for k, v in sorted(bucket_examples.items())},
        "exclusive_wins": wins,
        "transfer_operators": transfer_operators,
        "constraints": [
            "Default keep tree top-1; override only under guards.",
            "Do not migrate full MAC tree-building or open vignette regen.",
            "Do not use Live S3 coverage as primary signal.",
            "Do not overwrite formal F6 Acc=0.47.",
        ],
        "cases": cases,
        "baseline_funnels_note": {
            "b04": "open forward→examine support-count; high commitment conversion",
            "b00": "single CoT naming at gold grain",
            "b06": "3-doctor + supervisor / RRF; overlaps B00/B04 wins",
        },
    }

    _write_json(Path(args.out_json), doc)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render_md(doc), encoding="utf-8")
    print(
        json.dumps(
            {
                "out_json": str(args.out_json),
                "out_md": str(args.out_md),
                "acc": acc,
                "bucket_counts": dict(bucket_counts),
                "strong_recoverable": len(wins["strong_recoverable"]),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
