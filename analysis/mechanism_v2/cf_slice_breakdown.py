#!/usr/bin/env python3
"""Per-slice decomposition of this round's two fixes.  Zero calls.

§11.4 of the upstream audit forbids reporting a pooled mean when DA and MCR could
move in opposite directions, so the headline +17 / +13 is not reportable until it
is shown to hold on both families.  This program recomputes the shipped arm and
the quarantine reach split by family and by slice, and flags any family whose net
is <= 0.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    ConceptNode,
    ConceptRegistry,
    ObservedFact,
)
from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402
from cf_identity_port_verify import production_frontier  # noqa: E402
from cf_quarantine_reach import FACT_FIELDS, NODE_FIELDS, _note  # noqa: E402
from cf_substrate_replay import (  # noqa: E402
    ARMS,
    OUT,
    SLICES,
    _first_complete,
    load_rows,
)
from agentclinic_tree_dx.mosaic import MosaicPipeline  # noqa: E402

COLLAPSE_ARM = "aphhm_c_collapse3c_v1"


def identity_by_slice() -> dict[str, Any]:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    rows = load_rows()
    pipes = {
        "Forest": MosaicPipeline(None, mode="forest"),
        "IMPC": MosaicPipeline(None, mode="impc"),
    }
    cells: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        arm = row["_arm"]
        fam = row["_family"]
        sl = row["_slice"]
        key = (arm, fam, sl)
        cells[key]["cases"] += 1

        observed = [
            str(c.get("preferred_name") or "")
            for c in row["stages"].get("frontier_final") or []
        ]
        before = _first_complete(clinical, row, observed) is not None
        after = (
            _first_complete(clinical, row, production_frontier(pipes[arm], arm, row["stages"]))
            is not None
        )
        cells[key]["b0_addressable"] += before
        cells[key]["fixed_addressable"] += after
        if after and not before:
            cells[key]["rescue"] += 1
        elif before and not after:
            cells[key]["harm"] += 1
    out: dict[str, Any] = {"by_slice": {}, "by_family": {}}
    fam_roll: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for (arm, fam, sl), c in sorted(cells.items()):
        out["by_slice"][f"{arm}|{fam}|{sl}"] = dict(c)
        fam_roll[(arm, fam)].update(c)
    for (arm, fam), c in sorted(fam_roll.items()):
        d = dict(c)
        d["net"] = d.get("rescue", 0) - d.get("harm", 0)
        out["by_family"][f"{arm}|{fam}"] = d
    return out


def quarantine_by_slice() -> dict[str, Any]:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    cells: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for dataset, (family, sl) in SLICES.items():
        base = ROOT / "logs/backbone_v1" / dataset / COLLAPSE_ARM / "case_stages"
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            stages = doc["stages"]
            cid = str(doc.get("source_id") or doc.get("case_id") or path.stem)
            key = (family, sl)
            cells[key]["cases"] += 1

            facts = [
                ObservedFact(**{k: r[k] for k in FACT_FIELDS if k in r})
                for r in stages.get("facts") or []
            ]
            registry = ConceptRegistry()
            for r in stages.get("registry") or []:
                node = ConceptNode(**{k: r[k] for k in NODE_FIELDS if k in r})
                registry.concepts[node.concept_id] = node
            front = [str(x) for x in (stages.get("frontier") or [])]
            before = {
                x: _note(registry.concepts[x]) for x in front if x in registry.concepts
            }
            cells[key]["contradict_spans"] += sum(
                len(n.contradict_spans) for n in registry.concepts.values()
            )
            rep = registry.audit_directions(facts, quarantine=True)
            cells[key]["contradict_unbound"] += int(rep["against_spans"]) - int(
                rep["against_spans_bound"]
            )
            if not registry.direction_quarantine:
                continue
            cells[key]["edges"] += len(registry.direction_quarantine)
            changed = False
            for r in registry.direction_quarantine:
                hit = r["concept_id"]
                if hit in before and _note(registry.concepts[hit]) != before[hit]:
                    changed = True
                    if clinical.relation(family, sl, cid, r["label"]) == COMPLETE:
                        cells[key]["edge_on_complete_candidate"] += 1
            cells[key]["payload_changed_cases"] += changed
    out: dict[str, Any] = {"by_slice": {}, "by_family": {}}
    fam_roll: dict[str, Counter[str]] = defaultdict(Counter)
    for (family, sl), c in sorted(cells.items()):
        d = dict(c)
        d["exact_citation_closure"] = round(
            1 - d.get("contradict_unbound", 0) / max(1, d.get("contradict_spans", 0)), 4
        )
        out["by_slice"][f"{family}|{sl}"] = d
        fam_roll[family].update(c)
    for family, c in sorted(fam_roll.items()):
        d = dict(c)
        d["exact_citation_closure"] = round(
            1 - d.get("contradict_unbound", 0) / max(1, d.get("contradict_spans", 0)), 4
        )
        out["by_family"][family] = d
    return out


def main() -> None:
    ident = identity_by_slice()
    quar = quarantine_by_slice()
    warnings: list[str] = []
    for key, d in ident["by_family"].items():
        if d.get("net", 0) <= 0:
            warnings.append(f"identity fix net <= 0 on {key}: {d}")
    report = {
        "schema_version": "cf-slice-breakdown-v1",
        "model_calls": 0,
        "rule": (
            "Upstream §11.4 forbids a pooled mean when DA and MCR could diverge, so "
            "a fix is only reportable if it holds on both families."
        ),
        "identity_fix": ident,
        "direction_quarantine": quar,
        "warnings": warnings,
        "verdict": "both_families_positive" if not warnings else "family_divergence",
    }
    (OUT / "slice_breakdown.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("=== identity 修复：按族 ===")
    for k, d in ident["by_family"].items():
        print(
            f"  {k:14s} n={d['cases']:3d}  B0={d.get('b0_addressable',0):3d} -> "
            f"修复后={d.get('fixed_addressable',0):3d}  rescue={d.get('rescue',0):2d} "
            f"harm={d.get('harm',0):2d} 净={d['net']:+3d}"
        )
    print("=== identity 修复：按切片 ===")
    for k, d in ident["by_slice"].items():
        print(
            f"  {k:34s} n={d['cases']:3d}  {d.get('b0_addressable',0):3d} -> "
            f"{d.get('fixed_addressable',0):3d}  resc={d.get('rescue',0):2d} harm={d.get('harm',0):2d}"
        )
    print("=== 方向隔离（Collapse3c）：按族 ===")
    for k, d in quar["by_family"].items():
        print(
            f"  {k:6s} n={d['cases']:3d}  边={d.get('edges',0):2d} "
            f"payload变动={d.get('payload_changed_cases',0):2d} "
            f"命中complete候选={d.get('edge_on_complete_candidate',0):2d}  "
            f"against闭合率={d['exact_citation_closure']:.4f}"
        )
    print(f"\n判决: {report['verdict']}")
    for w in warnings:
        print("  警告:", w)


if __name__ == "__main__":
    main()
