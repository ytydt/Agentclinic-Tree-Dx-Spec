#!/usr/bin/env python3
"""Extract submodule-level signals from u29_full case logs for RCA."""
import re, glob, os, json

d = sorted(glob.glob("logs/medbullets_conc_u29_full_1_*_cases"))[-1]
GOLD = {1:"A",9:"D",13:"A",14:"A",17:"D",18:"E",22:"C",23:"A",24:"B"}


def extract_lr_findings(log_text):
    parts = log_text.split(">>> Module: EvidenceAnnotator")
    if len(parts) < 2:
        return []
    sec = parts[1].split("USER MESSAGE:", 1)[1].split("RAW LLM RESPONSE:", 1)[0]
    m = re.search(r'"lr_reference"\s*:\s*"', sec)
    if not m:
        return []
    i = m.end()
    lr = []
    while i < len(sec):
        c = sec[i]
        if c == "\\" and i + 1 < len(sec):
            lr.append("\n" if sec[i + 1] == "n" else sec[i + 1])
            i += 2
            continue
        if c == '"':
            break
        lr.append(c)
        i += 1
    text = "".join(lr)
    return list(dict.fromkeys(re.findall(r"\[LR Reference for '([^']+)'", text)))


def extract_talp_questions(log_text, n=6):
    parts = log_text.split(">>> Module: TemporaryAnalyticLeafPlanner")
    if len(parts) < 2:
        return []
    sec = parts[1].split("RAW LLM RESPONSE:", 1)[1][:12000]
    return re.findall(r'"content"\s*:\s*"((?:\\.|[^"\\]){20,200})"', sec)[:n]


def extract_final_mapping(log_text):
    m = re.search(r'"answer_option_mapping"\s*:\s*(\{[^}]+\})', log_text)
    fa = re.findall(r'"final_answer"\s*:\s*"([A-E])"', log_text)
    return (m.group(1) if m else ""), (fa[-1] if fa else "?")


def extract_leader(log_text):
    leads = re.findall(
        r'"leader"\s*:\s*\{"branch_id"\s*:\s*"([^"]+)",\s*"label"\s*:\s*"([^"]+)"',
        log_text,
    )
    return leads[-1] if leads else None


def extract_branch_labels(log_text):
    parts = log_text.split(">>> Module: BranchCreator")
    if len(parts) < 2:
        return []
    sec = parts[1].split("RAW LLM RESPONSE:", 1)[1][:8000]
    labels = re.findall(r'"label"\s*:\s*"([^"]+)"', sec)
    skip = {"diagnosis family label (MUST be broad family, NOT specific disease)"}
    out = []
    for l in labels:
        if l in skip or "syndrome-frame" in l.lower():
            continue
        if l not in out:
            out.append(l)
    return out[:8]


def extract_annotator_inversion(log_text):
    """LAP / direction inversion patterns."""
    inv = []
    if re.search(r"elevated leukocyte alkaline phosphatase.*in favor of a malignant", log_text, re.I):
        inv.append("LAP_direction_inverted")
    if re.search(r"leukocyte alkaline phosphatase.*against.*reactive", log_text, re.I):
        inv.append("LAP_vs_reactive")
    return inv


def extract_bundler_target(log_text):
    m = re.search(r'"target_branches"\s*:\s*(\{[^}]{0,200}\})', log_text)
    return m.group(1) if m else ""


for case in sorted(GOLD):
    p = os.path.join(d, f"case_{case:02d}.log")
    if not os.path.exists(p):
        continue
    t = open(p, encoding="utf-8", errors="replace").read()
    lr_f = extract_lr_findings(t)
    talp = extract_talp_questions(t, 4)
    mapping, pred = extract_final_mapping(t)
    leader = extract_leader(t)
    branches = extract_branch_labels(t)
    inv = extract_annotator_inversion(t)
    bundler = extract_bundler_target(t)
    # vignette first line
    vm = re.search(r"CASE \d+ — idx=\d+\n={10,}\n(.{0,120})", t)
    print(f"\n{'='*70}\nCASE {case} gold={GOLD[case]} pred={pred}")
    print("branches:", branches[:5])
    print("leader:", leader)
    print("lr_findings:", lr_f)
    print("lr_len_hit4k:", "YES" if len(t.split('"lr_reference"')[1][:4200]) > 3900 else "no")
    print("talp_q:", [q[:70].replace("\\n", " ") for q in talp[:3]])
    print("annotator_inv:", inv)
    print("bundler_sample:", bundler[:120])
    print("mapping:", mapping[:200])
