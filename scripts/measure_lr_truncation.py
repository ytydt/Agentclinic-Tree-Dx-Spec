#!/usr/bin/env python3
"""Measure 4a lr_reference truncation in case logs."""
import re
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def extract_lr_reference(payload: str) -> str:
    m = re.search(r'"lr_reference"\s*:\s*"', payload)
    if not m:
        return ""
    start = m.end()
    i = start
    lr = []
    while i < len(payload):
        c = payload[i]
        if c == "\\" and i + 1 < len(payload):
            nxt = payload[i + 1]
            lr.append("\n" if nxt == "n" else nxt)
            i += 2
            continue
        if c == '"':
            break
        lr.append(c)
        i += 1
    return "".join(lr)


def first_annotator_payload(log_text: str) -> str:
    parts = log_text.split(">>> Module: EvidenceAnnotator")
    if len(parts) < 2:
        return ""
    sec = parts[1]
    if "USER MESSAGE:" not in sec:
        return ""
    payload = sec.split("USER MESSAGE:", 1)[1]
    payload = payload.split("RAW LLM RESPONSE:", 1)[0]
    return payload


def main():
    dirs = sorted(glob.glob("logs/medbullets_conc_u29_full_*_cases"))
    if not dirs:
        print("no log dirs")
        return
    d = dirs[-1]
    print(f"log dir: {d}\n")
    print(f"{'case':<8} {'len':>5} {'blocks':>6} {'uniq':>4} {'hit4k':>5}  findings in payload")
    print("-" * 90)

    for case_n in range(1, 25):
        p = os.path.join(d, f"case_{case_n:02d}.log")
        if not os.path.exists(p):
            continue
        t = open(p, encoding="utf-8", errors="replace").read()
        payload = first_annotator_payload(t)
        lr = extract_lr_reference(payload)
        if not lr:
            continue
        blocks = re.findall(r"\[LR Reference for '([^']+)'", lr)
        uniq = list(dict.fromkeys(blocks))
        hit4k = len(lr) >= 3999
        # detect mid-block cut
        mid_cut = hit4k and (
            lr.rstrip().endswith("The ")
            or "[LR Reference for '" in lr[-80:]
            or not re.search(r"(no data|confidence=|\.\.\.)$", lr.rstrip()[-20:])
        )
        flag = "YES" if hit4k else "no"
        if mid_cut:
            flag += "*"
        print(
            f"case_{case_n:02d} {len(lr):5d} {len(blocks):6d} {len(uniq):4d} {flag:>5}  "
            f"{uniq[:6]}{'...' if len(uniq)>6 else ''}"
        )

    # case 9 detail: atomic findings via VignetteParser section
    print("\n=== case_09: static_evidence_items order (VignetteParser) ===")
    p = os.path.join(d, "case_09.log")
    t = open(p, encoding="utf-8", errors="replace").read()
    vp = t.split(">>> Module: VignetteParser", 1)
    if len(vp) > 1:
        raw = vp[1].split("RAW LLM RESPONSE:", 1)[1][:50000]
        contents = re.findall(r'"content"\s*:\s*"((?:\\.|[^"\\])*)"', raw)
        seen = set()
        ordered = []
        for c in contents:
            c = c.replace("\\n", " ").strip()
            if c and c not in seen:
                seen.add(c)
                ordered.append(c)
        for i, c in enumerate(ordered[:20], 1):
            mark = " <-- LAP" if "alkaline phosphatase" in c.lower() else ""
            in8 = " [in atomic[:8]]" if i <= 8 else " [BEYOND :8]"
            print(f"  {i:2}. {c[:70]}{mark}{in8}")

    # Simulate full block sizes if retriever available
    print("\n=== case_09: simulated 4a block sizes (if KB loads) ===")
    try:
        from agentclinic_tree_dx.knowledge.dx_feature_retriever import DxFeatureRetriever
        from agentclinic_tree_dx.config import ControllerConfig

        cfg = ControllerConfig()
        kr = DxFeatureRetriever(config=cfg)
        # typical branch labels from log
        diseases = [
            "Reactive / Non-malignant Leukocytosis",
            "Myeloid Neoplasm with Increased Blasts",
            "Chronic Myeloproliferative Neoplasm",
            "Lymphoid Neoplasm",
            "Plasma Cell Disorder",
        ]
        # use ordered evidence from parser
        findings = ordered[:15] if "ordered" in dir() else []
        from agentclinic_tree_dx.knowledge.finding_normalizer import FindingNormalizer
        fn = FindingNormalizer()
        atomic = []
        for raw in findings:
            if "age" in raw.lower() and "year" in raw.lower():
                continue
            norms = fn.normalize_multi(raw) if fn else []
            if norms:
                for n in norms:
                    if n.hpo_term:
                        atomic.append(n.hpo_term)
            else:
                atomic.append(raw)
        total = 0
        for idx, f in enumerate(atomic[:8], 1):
            blk = kr.format_lr_reference_for_prompt(f, diseases, fast=True)
            blen = len(blk) if blk else 0
            total += blen + 1
            print(f"  finding {idx}: {f[:50]:50s} block={blen:5d} cumul={total:5d}")
        print(f"  TOTAL before [:4000] cut: {total} (cap loses {max(0,total-4000)} chars)")
        # what's finding 9+ if any
        for idx, f in enumerate(atomic[8:12], 9):
            blk = kr.format_lr_reference_for_prompt(f, diseases, fast=True)
            print(f"  finding {idx} (dropped by [:8] or truncation): {f[:50]} block={len(blk or '')}")
    except Exception as e:
        print(f"  (simulation skipped: {e})")


if __name__ == "__main__":
    main()
