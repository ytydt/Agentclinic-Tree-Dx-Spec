#!/usr/bin/env python3
"""Stitch each assertion back to the passage it came from and the vignette item
it joined to, so the whole chain can be read in one place.

The extraction records keep provenance as (source, title, section) plus the
verbatim quote; the passage itself is recovered by locating the quote inside
the retrieved passages of the same case and focus hypothesis.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
from run_mechanical_engine import concept_match, norm  # noqa: E402


def find_passage(passages: list[dict], quote: str) -> dict | None:
    q = re.sub(r"\s+", " ", (quote or "")).strip()
    if len(q) < 12:
        return None
    for p in passages:
        flat = re.sub(r"\s+", " ", p["text"])
        if q[:80] in flat:
            return p
    # fall back to a distinctive fragment
    frag = " ".join(q.split()[:6])
    for p in passages:
        if frag and frag in re.sub(r"\s+", " ", p["text"]):
            return p
    return None


def context_window(text: str, quote: str, width: int = 420) -> str:
    flat = re.sub(r"[ \t]+", " ", text)
    q = re.sub(r"\s+", " ", (quote or "")).strip()
    idx = flat.find(q[:60]) if q else -1
    if idx < 0:
        return flat[:width].strip()
    lo = max(0, idx - width // 3)
    hi = min(len(flat), idx + len(q) + width // 3)
    return ("…" if lo else "") + flat[lo:hi].strip() + ("…" if hi < len(flat) else "")


def match_finding(pred: str, findings: list[dict]) -> tuple[dict | None, str]:
    best = None
    for f in findings:
        for side in (f.get("canonical"), f.get("label")):
            m = concept_match(pred, side or "")
            if m:
                rank = {"exact": 0, "containment": 1, "overlap": 2, "loose": 3}[m]
                if best is None or rank < best[0]:
                    best = (rank, f, m)
                break
    return (best[1], best[2]) if best else (None, "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30")
    ap.add_argument("--suffix", default="clean")
    ap.add_argument("--per-case", type=int, default=6)
    args = ap.parse_args()

    retrieval = {r["case_key"]: r for r in
                 json.loads((LEDGER / f"trial_retrieval_{args.arm}.json").read_text("utf-8"))}
    extraction = {e["case_key"]: e for e in
                  json.loads((LEDGER / f"trial_extraction_{args.arm}{args.suffix}.json").read_text("utf-8"))}
    engine = {e["case_key"]: e for e in
              json.loads((LEDGER / f"trial_engine_{args.arm}{args.suffix}.json").read_text("utf-8"))}
    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11.json").read_text("utf-8"))}

    lines: list[str] = ["# 断言 → 原文 → vignette 命中项 证据包", ""]
    records = []

    for key, task in tasks.items():
        ext = extraction[key]
        findings = [f for f in ext["findings"] if isinstance(f, dict) and f.get("label")]
        eng = engine[key]
        gold_labels = set(task["gold_labels_in_set"])
        by_label = {v["label"]: v for v in eng["ranking"]}

        lines += [f"## {key}", "",
                  f"- 金标：`{task['gold']}`",
                  f"- 候选集中被判为金标等价的标签：{task['gold_labels_in_set'] or '（无）'}",
                  f"- 引擎 top-1：`{eng['top1']}`（金标排名 {eng['gold_rank']}）", ""]

        # pick the assertions that actually moved the score, top-1 first then gold
        focus_labels = [eng["top1"]] + sorted(gold_labels - {eng["top1"]})
        for label in focus_labels:
            v = by_label.get(label)
            if not v:
                continue
            role = "top-1" + ("（同时是金标）" if label in gold_labels else "（竞争假设）") \
                if label == eng["top1"] else "金标"
            lines += [f"### `{label}` — {role}，得分 {v['score']}，"
                      f"接合 {v['n_joined']}/{v['n_assertions']} 条", ""]

            passages = (retrieval[key]["retrieved"].get(label) or {}).get("passages", [])
            contribs = sorted(v["contributions"], key=lambda c: -abs(c.get("delta", 0)))

            shown = 0
            for c in contribs:
                if shown >= args.per_case:
                    break
                cand = [a for a in ext["assertions"]
                        if a.get("_focus") == label
                        and norm(a.get("predicate")) == norm(c["predicate"])]
                if not cand:
                    cand = [a for a in ext["assertions"]
                            if norm(a.get("predicate")) == norm(c["predicate"])]
                if not cand:
                    continue
                a = cand[0]
                p = find_passage(passages, a.get("quote") or "")
                f, how = match_finding(a["predicate"], findings)
                th = {k: x for k, x in (a.get("threshold") or {}).items()
                      if x not in (None, "null", "")}

                lines += [
                    f"**断言** `{a['subject']}` —[{a.get('relation')}/{a.get('polarity')}/"
                    f"{a.get('modality')}]→ `{a['predicate']}`"
                    + (f"，阈值 `{th}`" if th else "")
                    + (f"，comparator `{a.get('comparator')}`" if a.get("comparator") else ""),
                    "",
                    f"- 出处：`{a.get('_source')}` / {a.get('_title') or '(无标题)'}"
                    + (f" › {a.get('_section')}" if a.get("_section") else "")
                    + f" · context_type=`{a.get('context_type')}`",
                    f"- 原文：{context_window(p['text'], a.get('quote') or '') if p else '（未能定位回段落）'}",
                    f"- 抽取所据引语：“{str(a.get('quote'))[:220]}”",
                ]
                if f:
                    val = f.get("value") or {}
                    valtxt = ""
                    if val.get("number") is not None:
                        valtxt = f"，值 {val.get('number')}{val.get('unit') or ''}"
                    lines += [
                        f"- **命中 vignette 项**：`{f.get('label')}`"
                        f"（canonical=`{f.get('canonical')}`，极性 `{f.get('polarity')}`{valtxt}，"
                        f"接合方式 `{how}`）",
                        f"- vignette 原句：“{str(f.get('quote'))[:200]}”",
                    ]
                else:
                    lines += ["- **命中 vignette 项**：无"]
                lines += [f"- 引擎影响：{c.get('why')}，Δ={c.get('delta')}", ""]
                records.append({"case": key, "hypothesis": label, "assertion": a,
                                "finding": f, "join": how, "contribution": c,
                                "passage_title": a.get("_title"), "source": a.get("_source")})
                shown += 1
            if shown == 0:
                lines += ["（该候选没有任何断言接合到 vignette 发现）", ""]

    out_md = LEDGER / f"evidence_pack_{args.arm}{args.suffix}.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    (LEDGER / f"evidence_pack_{args.arm}{args.suffix}.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_md} ({len(records)} chains)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
