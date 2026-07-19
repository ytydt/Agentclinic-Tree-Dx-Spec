"""Shared-tree recall-hints-gap + offline-P5/G2UR TALP evaluation.

The production controller is used only as a BranchCreator/SubBranchCreator
service container.  ``controller.run`` and every action/termination stage are
intentionally absent.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import statistics
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

from agentclinic_tree_dx.composed_pipeline import (  # noqa: E402
    ComposedTALPPipeline,
    ObservedFact,
    observed_facts,
)
from agentclinic_tree_dx.state import Branch, DiagnosticState, RootNode  # noqa: E402

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_PROFILES = ("p5_headline", "g2ur")
BRANCH_SCRIPT = ROOT / "scripts" / "eval_branch_creation_medbullets.py"
PARTIAL_SCRIPT = ROOT / "scripts" / "eval_partial_flow_talp17.py"
TALP_SCRIPT = ROOT / "scripts" / "eval_talp_discrimination.py"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
DEFAULT_ARM_OUTPUTS = {
    "p5_headline": ROOT / "logs" / "talp_discrim_p5kg_g0_s7r0_dv2_p5.json",
    "g2ur": (
        ROOT / "logs" / "talp_discrim_p5kg_research_g2ur_s7r0_dv2_p5.json"
    ),
}
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is",
    "of", "on", "or", "the", "to", "with", "without",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.lower()) if token not in STOP}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _best_reference(text: str, findings: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = sorted(
        ((_similarity(text, str(row.get("finding", ""))), row) for row in findings),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return scored[0][1] if scored and scored[0][0] >= 0.18 else None


def _facts_for_case(state: DiagnosticState, annotation: Mapping[str, Any]):
    facts = list(observed_facts(state.static_evidence_items))
    seen = {" ".join(fact.text.lower().split()) for fact in facts}
    for row in annotation.get("findings") or []:
        if not row.get("in_vignette"):
            continue
        text = str(row.get("finding") or "").strip()
        key = " ".join(text.lower().split())
        if text and key not in seen:
            facts.append(ObservedFact("", text))
            seen.add(key)
    return tuple(
        ObservedFact(f"F{index + 1}", fact.text)
        for index, fact in enumerate(facts)
    )


def _serialize_state(state: DiagnosticState, branch_provenance: Mapping[str, Any]):
    evidence_items = [
        asdict(item) if is_dataclass(item)
        else dict(item) if isinstance(item, Mapping)
        else {"content": str(item)}
        for item in state.static_evidence_items
    ]
    return {
        "case_id": state.case_id,
        "case_summary": state.case_summary,
        "root": asdict(state.root) if state.root else None,
        "branches": {
            branch_id: asdict(branch) for branch_id, branch in state.branches.items()
        },
        "frontier": list(state.frontier),
        "static_evidence_items": evidence_items,
        "static_question": state.static_question,
        "branch_provenance": dict(branch_provenance),
    }


def _deserialize_state(payload: Mapping[str, Any]) -> DiagnosticState:
    state = DiagnosticState(case_id=str(payload["case_id"]))
    state.case_summary = str(payload.get("case_summary") or "")
    if payload.get("root"):
        state.root = RootNode(**dict(payload["root"]))
    state.branches = {
        branch_id: Branch(**dict(row))
        for branch_id, row in (payload.get("branches") or {}).items()
    }
    state.frontier = list(payload.get("frontier") or ())
    state.static_evidence_items = list(payload.get("static_evidence_items") or ())
    state.static_question = str(payload.get("static_question") or "")
    state.max_tree_depth = 2
    return state


class FrozenOfflineArms:
    """Re-route frozen P5/G2UR compiler audits to observed-fact IDs."""

    def __init__(self, talp_module, paths: Mapping[str, Path]) -> None:
        self.talp = talp_module
        self.paths = dict(paths)
        self.docs = {
            profile: json.loads(path.read_text(encoding="utf-8"))
            for profile, path in self.paths.items()
        }
        self.cfg = talp_module._cfg_for_stage("p5")

    def blocks(
        self, profile: str, case_id: str, facts: tuple[ObservedFact, ...]
    ) -> dict[str, dict[str, Any]]:
        rules = list(self.docs[profile].get("disc_audit", {}).get(case_id) or ())
        output = {}
        for fact in facts:
            matched = _best_reference(fact.text, rules)
            matched_rules = [matched] if matched is not None else []
            routed = self.talp._routed_blocks(matched_rules, self.cfg)
            evidence = list((matched or {}).get("evidence") or ())
            output[fact.id] = {
                **routed,
                "provenance": evidence[:12],
                "matched_compiler_finding": (
                    matched.get("finding") if matched is not None else None
                ),
                "n_evidence": int((matched or {}).get("n_evidence") or 0),
                "verdict": (matched or {}).get("verdict", "unmatched"),
            }
        return output

    def reference_metrics(self, profile: str) -> dict[str, Any]:
        doc = self.docs[profile]
        return {
            "source": str(self.paths[profile].relative_to(ROOT)),
            "summary": dict(doc.get("summary") or {}),
            "case_normalized": dict(doc.get("case_normalized") or {}),
            "audit_summary": dict(doc.get("audit_summary") or {}),
        }


def _make_llm_functions(llm):
    selector_prompt = (PROMPT_DIR / "observed_evidence_selector.txt").read_text()
    annotator_prompt = (PROMPT_DIR / "evidence_annotator.txt").read_text()

    def selector(payload):
        return llm.call_module(
            "ObservedEvidenceSelector", selector_prompt, dict(payload)
        )

    def annotator(payload):
        return llm.call_module("EvidenceAnnotator", annotator_prompt, dict(payload))

    return selector, annotator


def _strict_judge_factory(model: str):
    gold_module = _load_module(
        "composed_gold_judge",
        ROOT / "scripts" / "eval_partial_flow_gold_branch_metrics.py",
    )
    return gold_module._make_strict_gold_judge(model)


def _family_judge_factory(model: str):
    return _load_module("composed_branch", BRANCH_SCRIPT).make_judge(model)


def _judge_cached(
    judge: Callable[[str, list[str]], int],
    cache: dict[str, int],
    cache_path: Path,
    *,
    policy: str,
    case_id: str,
    gold: str,
    labels: list[str],
) -> int:
    key = f"{policy}::{case_id}::{_stable_hash(labels)[:16]}"
    if key not in cache:
        cache[key] = int(judge(gold, labels))
        _atomic_json(cache_path, cache)
    return int(cache[key])


def _rank(branches: list[Branch], index: int) -> int | None:
    if not 0 <= index < len(branches):
        return None
    ordered = sorted(
        range(len(branches)),
        key=lambda i: (-float(branches[i].posterior), branches[i].id),
    )
    return ordered.index(index) + 1


def _gold_metrics(
    state: DiagnosticState,
    *,
    gold: str,
    case_id: str,
    family_judge,
    strict_judge,
    judge_cache: dict[str, int],
    judge_cache_path: Path,
) -> dict[str, Any]:
    l1 = sorted(
        (branch for branch in state.branches.values() if branch.level == 1),
        key=lambda branch: branch.id,
    )
    l2 = sorted(
        (branch for branch in state.branches.values() if branch.level == 2),
        key=lambda branch: branch.id,
    )
    l1_idx = _judge_cached(
        family_judge, judge_cache, judge_cache_path,
        policy="family_v1", case_id=case_id, gold=gold,
        labels=[branch.label for branch in l1],
    )
    l2_idx = _judge_cached(
        strict_judge, judge_cache, judge_cache_path,
        policy="strict_l2_v1", case_id=case_id, gold=gold,
        labels=[branch.label for branch in l2],
    )

    def level(rows: list[Branch], index: int):
        rank = _rank(rows, index)
        branch = rows[index] if rank is not None else None
        return {
            "exists": branch is not None,
            "branch_id": branch.id if branch else None,
            "label": branch.label if branch else None,
            "posterior": branch.posterior if branch else None,
            "rank": rank,
            "top1": rank == 1,
            "count": len(rows),
        }

    l1m, l2m = level(l1, l1_idx), level(l2, l2_idx)
    return {
        "l1": l1m,
        "l2": l2m,
        "path_consistent": bool(
            l1m["exists"] and l2m["exists"]
            and l2[l2_idx].parent == l1[l1_idx].id
        ),
    }


def _score_selected(
    trace: Mapping[str, Any],
    annotation: Mapping[str, Any],
    state: DiagnosticState,
    gold_branch_id: str | None,
) -> dict[str, Any]:
    findings = list(annotation.get("findings") or ())
    selected = trace.get("selected_fact_ids") or ()
    rounds = trace.get("rounds") or ()
    scored = []
    for fact_id, round_row in zip(selected, rounds):
        fact_text = str(round_row.get("fact", {}).get("text") or "")
        reference = _best_reference(fact_text, findings)
        effects = round_row.get("annotation", {}).get("branch_effects") or {}
        role = (reference or {}).get("role") or (
            "rule_in_gold" if (reference or {}).get("favors") == "gold"
            else "shared_nondiscriminating"
        )
        correct = None
        kind = None
        if role == "rule_in_gold" and gold_branch_id:
            correct = "for" in str(effects.get(gold_branch_id, "neutral"))
            kind = "direction"
        elif role == "rule_out_distractor":
            target = str(
                (reference or {}).get("direction_target")
                or (reference or {}).get("target")
                or ""
            )
            candidates = [
                branch for branch in state.branches.values() if branch.level == 2
            ]
            scored_targets = sorted(
                ((_similarity(target, branch.label), branch) for branch in candidates),
                key=lambda pair: pair[0],
                reverse=True,
            )
            target_branch = (
                scored_targets[0][1]
                if scored_targets and scored_targets[0][0] >= 0.18 else None
            )
            correct = (
                "against" in str(effects.get(target_branch.id, "neutral"))
                if target_branch else None
            )
            kind = "ruleout"
        elif role in {"shared_nondiscriminating", "parent_child_trap"}:
            correct = not any(
                value in {
                    "strong_for", "moderate_for",
                    "strong_against", "moderate_against",
                }
                for value in effects.values()
            )
            kind = "trap" if role == "parent_child_trap" else "shared"
        scored.append({
            "fact_id": fact_id,
            "fact": fact_text,
            "matched_reference": (reference or {}).get("finding"),
            "role": role if reference else None,
            "decisive": bool((reference or {}).get("decisive")),
            "kind": kind,
            "direction_ok": correct,
        })
    valid = [
        row for row in scored
        if row["role"] in {"rule_in_gold", "rule_out_distractor"}
    ]
    return {
        "select@1": bool(scored and scored[0]["decisive"]),
        "select@2": any(row["decisive"] for row in scored[:2]),
        "select_valid": bool(valid),
        "direction_rows": scored,
    }


def _gold_trajectory(trace: Mapping[str, Any], branch_id: str | None):
    output = []
    for snapshot in trace.get("posterior_trajectory") or ():
        rows = list(snapshot.get("posteriors") or ())
        index = next(
            (i for i, row in enumerate(rows) if row.get("id") == branch_id), None
        )
        output.append({
            "round": snapshot.get("round"),
            "fact_id": snapshot.get("fact_id"),
            "exists": index is not None,
            "rank": index + 1 if index is not None else None,
            "top1": index == 0,
            "posterior": rows[index].get("posterior") if index is not None else None,
        })
    return output


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [row for row in records if row.get("status") == "OK"]

    def block(rows):
        l2 = [row["gold"]["final"]["l2"] for row in rows]
        ranks = [item["rank"] for item in l2 if item["rank"] is not None]
        direction = [
            item["direction_ok"]
            for row in rows
            for item in row["talp_metrics"]["direction_rows"]
            if item["direction_ok"] is not None
        ]
        by_kind = {
            kind: [
                item["direction_ok"]
                for row in rows
                for item in row["talp_metrics"]["direction_rows"]
                if item.get("kind") == kind and item["direction_ok"] is not None
            ]
            for kind in ("direction", "ruleout", "shared", "trap")
        }
        round_numbers = sorted({
            point["round"]
            for row in rows for point in row.get("gold_rounds") or ()
        })
        return {
            "cases": len(rows),
            "l2_gold_existence_rate": (
                sum(item["exists"] for item in l2) / len(rows) if rows else None
            ),
            "probability_at_1": (
                sum(item["top1"] for item in l2) / len(rows) if rows else None
            ),
            "top3": (
                sum(item["rank"] is not None and item["rank"] <= 3 for item in l2)
                / len(rows) if rows else None
            ),
            "top5": (
                sum(item["rank"] is not None and item["rank"] <= 5 for item in l2)
                / len(rows) if rows else None
            ),
            "mrr": (
                sum(1 / rank for rank in ranks) / len(rows) if rows else None
            ),
            "mean_rank_when_present": statistics.mean(ranks) if ranks else None,
            "median_rank_when_present": statistics.median(ranks) if ranks else None,
            "select@1": (
                sum(row["talp_metrics"]["select@1"] for row in rows) / len(rows)
                if rows else None
            ),
            "select@2": (
                sum(row["talp_metrics"]["select@2"] for row in rows) / len(rows)
                if rows else None
            ),
            "select_valid": (
                sum(row["talp_metrics"]["select_valid"] for row in rows) / len(rows)
                if rows else None
            ),
            "direction_accuracy_selected": (
                sum(direction) / len(direction) if direction else None
            ),
            "talp_selected_subset": {
                kind: {
                    "ok": sum(values),
                    "n": len(values),
                    "accuracy": sum(values) / len(values) if values else None,
                }
                for kind, values in by_kind.items()
            },
            "probability_at_1_by_round": {
                str(round_number): (
                    sum(
                        next(
                            point["top1"] for point in row["gold_rounds"]
                            if point["round"] == round_number
                        )
                        for row in rows
                    ) / len(rows)
                    if rows else None
                )
                for round_number in round_numbers
            },
            "profile_rule_hits": sum(row["profile_rule_hits"] for row in rows),
        }

    profiles = sorted({row.get("profile") for row in ok})
    by_profile = {
        profile: block([row for row in ok if row["profile"] == profile])
        for profile in profiles
    }
    paired = {}
    indexed = {(row["profile"], row["case_id"]): row for row in ok}
    case_ids = sorted({
        row["case_id"] for row in ok
        if all((profile, row["case_id"]) in indexed for profile in profiles)
    })
    if set(profiles) == set(DEFAULT_PROFILES):
        deltas = []
        for case_id in case_ids:
            p5 = indexed[("p5_headline", case_id)]["gold"]["final"]["l2"]["rank"]
            g2 = indexed[("g2ur", case_id)]["gold"]["final"]["l2"]["rank"]
            if p5 is not None and g2 is not None:
                deltas.append(g2 - p5)
        paired = {
            "cases": len(case_ids),
            "rank_comparable_cases": len(deltas),
            "mean_rank_delta_g2ur_minus_p5": (
                statistics.mean(deltas) if deltas else None
            ),
            "improved_worse_tied": [
                sum(delta < 0 for delta in deltas),
                sum(delta > 0 for delta in deltas),
                sum(delta == 0 for delta in deltas),
            ],
        }
    return {
        "completed": len(ok),
        "errors": len(records) - len(ok),
        "by_profile": by_profile,
        "paired": paired,
    }


def run(args) -> dict[str, Any]:
    partial = _load_module("composed_partial", PARTIAL_SCRIPT)
    branch = _load_module("composed_branch_runtime", BRANCH_SCRIPT)
    talp = _load_module("composed_talp", TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    profiles = tuple(
        token.strip() for token in args.profiles.split(",") if token.strip()
    )
    if set(profiles) - set(DEFAULT_PROFILES):
        raise ValueError(f"unknown profiles: {profiles}")
    arm_paths = {
        "p5_headline": args.p5_arm_output,
        "g2ur": args.g2ur_arm_output,
    }
    arms = FrozenOfflineArms(talp, arm_paths)
    identity = {
        "schema_version": 1,
        "model": args.model,
        "profiles": profiles,
        "evidence_limit": args.evidence_limit,
        "call_timeout": args.call_timeout,
        "branch_mode": "recall_hints_gap",
        "branch_source_sha256": _sha256(BRANCH_SCRIPT),
        "arm_outputs": {
            profile: {"path": str(path), "sha256": _sha256(path)}
            for profile, path in arm_paths.items()
        },
    }
    fingerprint = _stable_hash(identity)
    run_dir = args.output_dir / args.tag
    trace_dir, tree_dir = run_dir / "traces", run_dir / "shared_trees"
    _atomic_json(run_dir / "manifest.json", {
        **identity,
        "run_fingerprint": fingerprint,
        "cases": [case["id"] for case in cases],
        "offline_reference_metrics": {
            profile: arms.reference_metrics(profile) for profile in profiles
        },
    })

    from agentclinic_tree_dx.llm_client import RobustLLMClient
    llm = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
    )
    selector, annotator = _make_llm_functions(llm)
    pipeline = ComposedTALPPipeline(
        selector=selector,
        annotator=annotator,
        evidence_limit=args.evidence_limit,
    )
    family_judge = _family_judge_factory(args.model)
    strict_judge = _strict_judge_factory(args.model)
    judge_cache_path = run_dir / "judge_cache.json"
    try:
        judge_cache = json.loads(judge_cache_path.read_text())
    except (OSError, ValueError):
        judge_cache = {}

    controller = env = provenance = None
    records: list[dict[str, Any]] = []
    for case in cases:
        tree_path = tree_dir / f"{case['id']}.json"
        if args.resume and tree_path.is_file():
            tree_payload = json.loads(tree_path.read_text())
            if tree_payload.get("run_fingerprint") != fingerprint:
                raise ValueError(f"shared tree fingerprint mismatch: {tree_path}")
            frozen_state = _deserialize_state(tree_payload["state"])
        else:
            if controller is None:
                controller, env, _, provenance = branch.build_controller(
                    args.model,
                    branch_mode="recall_hints_gap",
                    config_overrides={"talp_disc_profile": "off"},
                )
            frozen_state = branch.run_case_branches(
                controller, env, case["case_text"]
            )
            frozen_state.case_id = case["id"]
            frozen_state.max_tree_depth = 2
            expansion = controller.force_expand_all_l1(frozen_state)
            if expansion.get("l1_expansion_rate") != 1.0:
                raise RuntimeError(f"{case['id']}: incomplete L1 expansion")
            tree_payload = {
                "run_fingerprint": fingerprint,
                "tree_hash": "",
                "state": _serialize_state(
                    frozen_state, (provenance or {}).get("last") or {}
                ),
                "expansion": expansion,
            }
            tree_payload["tree_hash"] = _stable_hash(tree_payload["state"]["branches"])
            _atomic_json(tree_path, tree_payload)
        tree_hash = tree_payload["tree_hash"]
        facts = _facts_for_case(frozen_state, case["annotation"])
        initial_gold = _gold_metrics(
            frozen_state, gold=case["gold"], case_id=case["id"],
            family_judge=family_judge, strict_judge=strict_judge,
            judge_cache=judge_cache, judge_cache_path=judge_cache_path,
        )

        for profile in profiles:
            trace_path = trace_dir / f"{profile}__{case['id']}.json"
            if args.resume and trace_path.is_file():
                existing = json.loads(trace_path.read_text())
                if (
                    existing.get("status") == "OK"
                    and existing.get("run_fingerprint") == fingerprint
                ):
                    records.append(existing)
                    continue
            started = time.monotonic()
            try:
                routed = arms.blocks(profile, case["id"], facts)
                final_state, trace = pipeline.run(
                    frozen_state,
                    profile=profile,
                    vignette=case["case_text"],
                    facts=facts,
                    routed_blocks=routed,
                )
                final_gold = _gold_metrics(
                    final_state, gold=case["gold"], case_id=case["id"],
                    family_judge=family_judge, strict_judge=strict_judge,
                    judge_cache=judge_cache, judge_cache_path=judge_cache_path,
                )
                profile_hits = sum(
                    int(routed[fact_id].get("n_evidence") or 0)
                    for fact_id in trace["selected_fact_ids"]
                )
                record = {
                    "status": "OK",
                    "schema_version": 1,
                    "run_fingerprint": fingerprint,
                    "profile": profile,
                    "case_id": case["id"],
                    "gold_diagnosis": case["gold"],
                    "shared_tree_hash": tree_hash,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "facts": [fact.to_dict() for fact in facts],
                    "profile_rule_hits": profile_hits,
                    "gold": {"initial": initial_gold, "final": final_gold},
                    "gold_rounds": _gold_trajectory(
                        trace, final_gold["l2"].get("branch_id")
                    ),
                    "talp_metrics": _score_selected(
                        trace, case["annotation"], final_state,
                        final_gold["l2"].get("branch_id"),
                    ),
                    "trace": trace,
                    "answer_mapper_called": False,
                }
            except Exception as exc:
                record = {
                    "status": "ERROR",
                    "schema_version": 1,
                    "run_fingerprint": fingerprint,
                    "profile": profile,
                    "case_id": case["id"],
                    "shared_tree_hash": tree_hash,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                    "answer_mapper_called": False,
                }
            _atomic_json(trace_path, record)
            records.append(record)
            _atomic_json(run_dir / "summary.json", _aggregate(records))
    summary = _aggregate(records)
    summary["run_fingerprint"] = fingerprint
    summary["offline_reference_metrics"] = {
        profile: arms.reference_metrics(profile) for profile in profiles
    }
    _atomic_json(run_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--profiles", default=",".join(DEFAULT_PROFILES))
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--evidence-limit", type=int, default=2)
    parser.add_argument(
        "--call-timeout", type=float, default=240.0,
        help="per-LLM-call timeout; a failed call records an ERROR trace",
    )
    parser.add_argument("--tag", default="talp17_shared_tree_p5_g2ur")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "logs" / "branch_talp_composed"
    )
    parser.add_argument(
        "--p5-arm-output", type=Path, default=DEFAULT_ARM_OUTPUTS["p5_headline"]
    )
    parser.add_argument(
        "--g2ur-arm-output", type=Path, default=DEFAULT_ARM_OUTPUTS["g2ur"]
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
