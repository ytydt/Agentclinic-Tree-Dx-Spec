#!/usr/bin/env python3
import glob, sys
from analyze_payload_breakdown import parse_blocks, ntok, key_breakdown

logs = sorted(glob.glob("logs/*_cases/case_*.log"))
rows = []
biggest_block = None  # (utok, file, module, usr)
for f in logs:
    text = open(f, errors="replace").read()
    for name, sysm, usr, rsp in parse_blocks(text):
        ut = ntok(usr)
        rows.append((ut, ntok(sysm), f, name))
        if biggest_block is None or ut > biggest_block[0]:
            biggest_block = (ut, f, name, usr)

rows.sort(reverse=True)
print("=== TOP 15 user payloads across ALL case logs ===")
print(f"{'user_tok':>9s} {'sys_tok':>8s}  {'module':26s} file")
for ut, st, f, name in rows[:15]:
    print(f"{ut:9d} {st:8d}  {name:26s} {f.split('/')[-2]}/{f.split('/')[-1]}")

ut, f, name, usr = biggest_block
print(f"\n=== Per-key breakdown of GLOBAL max: {name}  ({ut} tok)  {f} ===")
bd = key_breakdown(usr)
if bd:
    for k, t in sorted(bd.items(), key=lambda x: -x[1]):
        if t <= 1:
            continue
        print(f"  {k:34s} {t:7d} tok  {100.0*t/max(1,ut):5.1f}%")
