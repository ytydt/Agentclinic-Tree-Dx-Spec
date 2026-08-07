#!/usr/bin/env python3
"""Batch 0-Z3: isolate WHY backbone S2 recall (0.71) < AB02 LLM-DDx entrance (0.86).

2x2 over {prompt} x {anchor} plus a no-S1 arm:

  P_bb  = prompts/backbone_wide_ddx.txt   (backbone file prompt)
  P_ab  = controller._llm_ddx_entities inline prompt string
  A_bb  = backbone S1 syndrome_frame + salient_findings
  A_ab  = AB02 tree root.label + root.salient_findings
  A_raw = no anchor abstraction; syndrome = case question, salient = [], full vignette

Writes only under logs/backbone_v1/probe_s2_anchor/ and analysis/backbone_v1/.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from mapper_bind_repair import leaf_match_score  # noqa: E402

OUT = ROOT / "logs/backbone_v1/probe_s2_anchor"
BB = ROOT / "logs/backbone_v1/diagnosisarena/v0_s4b_k5/case_stages"
TR = ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/annotate/shared_trees"
SUBSET = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1"
MODEL = "meta-llama/llama-3.3-70b-instruct"

P_BB = (ROOT / "src/agentclinic_tree_dx/prompts/backbone_wide_ddx.txt").read_text(
    encoding="utf-8"
)
P_AB = (
    "You are an expert physician building the FULL differential diagnosis "
    "for a presenting syndrome. List EVERY plausible diagnosis a thorough "
    "clinician would consider, including rare/zebra causes. Return STRICT "
    'JSON: {"differentials": ["specific disease 1", ...]}. Give SPECIFIC '
    "disease entities (e.g. 'chronic myeloid leukemia', 'pancoast tumor', "
    "'glucagonoma'), 12-25 items, no prose."
)

ARMS = {
    "p_bb__a_bb": ("bb", "bb"),   # = shipped backbone S2 (re-run for cache parity)
    "p_ab__a_bb": ("ab", "bb"),
    "p_bb__a_ab": ("bb", "ab"),
    "p_ab__a_ab": ("ab", "ab"),   # = AB02 entrance conditions
    "p_ab__a_raw": ("ab", "raw"),  # no S1 at all -> would let us delete a call
}


def _hit(gold: str, items: list[str], thr: float = 0.7) -> bool:
    return any(leaf_match_score(gold, x) >= thr for x in items)


def _near(gold: str, items: list[str]) -> float:
    return max([leaf_match_score(gold, x) for x in items] or [0.0])


def main() -> None:
    cases = bc.load_runtime_cases(dataset="diagnosisarena", subset_dir=SUBSET)
    by = {c["source_id"]: c for c in cases}

    anchors: dict[str, dict] = {}
    for f in sorted(BB.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        sid = d["source_id"]
        tp = TR / f"{sid}.json"
        if not tp.is_file() or sid not in by:
            continue
        root = json.loads(tp.read_text(encoding="utf-8"))["state"]["root"]
        s1 = d["stages"]["s1"]
        anchors[sid] = {
            "bb": (
                s1.get("syndrome_frame") or "",
                list(s1.get("salient_findings") or []),
            ),
            "ab": (
                str(root.get("label") or ""),
                list(root.get("salient_findings") or []),
            ),
            "raw": ("", []),
        }
    print(f"[probe] cases with both anchors: {len(anchors)}", flush=True)

    client = RobustLLMClient(
        model=MODEL, call_timeout=240, max_retries=5,
        timeout_retry_cap=2, temperature=0.0,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    llm = bc.SimpleCachedLLM(client, OUT / "cache.json", MODEL)

    report: dict[str, dict] = {}
    for arm, (pk, ak) in ARMS.items():
        prompt = P_BB if pk == "bb" else P_AB
        adir = OUT / arm
        adir.mkdir(parents=True, exist_ok=True)

        def task(sid: str) -> tuple[str, list[str]]:
            path = adir / f"{sid}.json"
            if path.is_file():
                return sid, json.loads(path.read_text(encoding="utf-8"))["differentials"]
            syn, sal = anchors[sid][ak]
            vig = str(by[sid]["vignette"])
            payload = {
                "presenting_syndrome": syn or "undifferentiated clinical presentation",
                "salient_findings": sal,
                "context": vig[:1500] if ak != "raw" else vig,
            }
            raw = llm.call("LLMDdxEntrance", prompt, payload)
            out, seen = [], set()
            for x in (raw.get("differentials") or []):
                s = str(x).strip()
                if s and s.lower() not in seen:
                    seen.add(s.lower())
                    out.append(s)
            out = out[:25]
            path.write_text(
                json.dumps({"source_id": sid, "differentials": out}, ensure_ascii=False),
                encoding="utf-8",
            )
            return sid, out

        got: dict[str, list[str]] = {}
        with ThreadPoolExecutor(max_workers=20) as ex:
            futs = {ex.submit(task, s): s for s in anchors}
            for fu in as_completed(futs):
                try:
                    sid, out = fu.result()
                    got[sid] = out
                except Exception as e:  # pragma: no cover
                    print(f"  [err] {futs[fu]}: {e}", flush=True)
        n = len(got)
        cov = sum(_hit(by[s]["_gold_text"], v) for s, v in got.items())
        top1 = sum(
            1 for s, v in got.items()
            if v and leaf_match_score(by[s]["_gold_text"], v[0]) >= 0.7
        )
        near = sum(
            1 for s, v in got.items()
            if not _hit(by[s]["_gold_text"], v) and _near(by[s]["_gold_text"], v) >= 0.5
        )
        size = sum(len(v) for v in got.values()) / max(1, n)
        report[arm] = {
            "n": n, "coverage": round(cov / max(1, n), 3),
            "top1_lexical": round(top1 / max(1, n), 3),
            "near_miss_0.5_0.7": near, "mean_list_len": round(size, 1),
        }
        print(f"[probe] {arm:12} n={n} cov={cov/max(1,n):.3f} "
              f"top1={top1/max(1,n):.3f} near={near} len={size:.1f}", flush=True)

    (Path(__file__).parent / "z3_s2_anchor_probe.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
