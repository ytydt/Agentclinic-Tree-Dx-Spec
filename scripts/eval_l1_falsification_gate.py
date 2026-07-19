#!/usr/bin/env python3
"""Evaluate an external-evidence, disagreement-triggered falsification critic."""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_anti_anchor_debate as anti_eval  # noqa: E402
import eval_l1_contrastive_selection as isolated  # noqa: E402
import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import assert_no_gold_leak  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


CRITIC_PROMPT = (
    bfs.PROMPT_DIR / "l1_falsification_critic.txt"
).read_text(encoding="utf-8")
VERDICTS = {"falsified", "not_falsified", "insufficient"}


def _items(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    return [str(item) for item in values]


def _knowledge_packet(
    fact_id: str,
    *,
    facts_by_id: Mapping[str, Any],
    blocks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fact = facts_by_id.get(fact_id)
    block = dict(blocks.get(fact_id) or {})
    packet = {
        "fact_id": fact_id,
        "fact_text": fact.text if fact is not None else "",
        "matched_compiler_finding": str(
            block.get("matched_compiler_finding") or ""
        ),
        "compiler_verdict": str(block.get("verdict") or "unmatched"),
        "n_evidence": int(block.get("n_evidence") or 0),
        "select_rules": _items(block.get("select")),
        "direction_rules": _items(block.get("direction")),
        "ruleout_rules": _items(block.get("ruleout")),
        "provenance": _items(block.get("provenance")),
    }
    packet["has_external_evidence"] = bool(
        packet["n_evidence"]
        or packet["select_rules"]
        or packet["direction_rules"]
        or packet["ruleout_rules"]
        or packet["provenance"]
    )
    return packet


def _critic_result(response: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {"schema_valid": True}
    for key in ("proposal_a", "proposal_b"):
        raw = response.get(key) or {}
        verdict = str(raw.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            verdict = "insufficient"
            output["schema_valid"] = False
        output[key] = {
            "verdict": verdict,
            "why": str(raw.get("why") or ""),
            "citations": [
                str(value) for value in (raw.get("citations") or ())
            ],
        }
    return output


def _gate(
    current: Mapping[str, Any],
    anti: Mapping[str, Any],
    critic: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    if critic is None:
        return dict(anti), "no_disagreement_keep_anti"
    a_verdict = critic["proposal_a"]["verdict"]
    b_verdict = critic["proposal_b"]["verdict"]
    if a_verdict == "falsified" and b_verdict == "falsified":
        return {
            "verdict": "none",
            "best_fact_id": "",
            "ranked_fact_ids": [],
            "concept_keys": {},
            "comparisons": [],
            "rejected": [],
            "schema_valid": True,
        }, "both_falsified_abstain"
    if b_verdict == "falsified" and a_verdict != "falsified":
        return dict(current), "anti_falsified_fallback_current"
    return dict(anti), "anti_not_falsified_or_insufficient"


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    composed = bfs._load_module("falsification_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("falsification_partial", bfs.PARTIAL_SCRIPT)
    talp = bfs._load_module("falsification_talp", bfs.TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    frozen_arms = composed.FrozenOfflineArms(
        talp, {"p5_headline": bfs.DEFAULT_ARM_OUTPUTS["p5_headline"]}
    )
    inputs: dict[str, dict[str, Any]] = {}
    for case in cases:
        tree_payload = json.loads(
            (bfs.DEFAULT_SHARED_TREE_DIR / f"{case['id']}.json").read_text(
                encoding="utf-8"
            )
        )
        frozen_tree = composed._deserialize_state(tree_payload["state"])
        facts = bfs._facts_for_case(
            frozen_tree, case["annotation"], composed, deduplicate=True,
        )
        blocks = frozen_arms.blocks("p5_headline", case["id"], facts)
        inputs[case["id"]] = {
            "case": case,
            "facts": facts,
            "facts_by_id": {fact.id: fact for fact in facts},
            "blocks": blocks,
            "view": anti_eval._selector_view(
                isolated._selection_payload(case, frozen_tree, facts, blocks)
            ),
        }

    source = json.loads(args.source_summary.read_text(encoding="utf-8"))
    source_by_key: dict[tuple[int, str], dict[str, dict[str, Any]]] = (
        collections.defaultdict(dict)
    )
    source_records: dict[str, list[dict[str, Any]]] = {
        "contrastive_current": [],
        "anti_anchor_prompt": [],
    }
    for record in source.get("records") or []:
        arm = str(record.get("arm") or "")
        replicate = int(record.get("replicate") or 0)
        case_id = str(record.get("case_id") or "")
        if (
            arm not in source_records
            or replicate > args.replicates
            or case_id not in inputs
        ):
            continue
        source_by_key[(replicate, case_id)][arm] = dict(record["raw"])
        source_records[arm].append(record)

    gated_records: list[dict[str, Any]] = []
    critic_audits: list[dict[str, Any]] = []
    for replicate in range(1, args.replicates + 1):
        client = RobustLLMClient(
            model=args.model,
            call_timeout=args.call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=args.temperature,
        )
        cache = bfs.CachedLLM(
            client,
            args.output_dir / f"falsification_r{replicate:02d}_cache.json",
            args.model,
        )
        for case_id, case_inputs in inputs.items():
            pair = source_by_key.get((replicate, case_id), {})
            if set(pair) != {"contrastive_current", "anti_anchor_prompt"}:
                raise ValueError(
                    f"missing source proposals for replicate={replicate} "
                    f"case={case_id}"
                )
            current = pair["contrastive_current"]
            anti = pair["anti_anchor_prompt"]
            current_top1 = list(current.get("ranked_fact_ids") or [])[:1]
            anti_top1 = list(anti.get("ranked_fact_ids") or [])[:1]
            triggered = current_top1 != anti_top1
            critic: dict[str, Any] | None = None
            knowledge: list[dict[str, Any]] = []
            if triggered:
                fact_ids = list(dict.fromkeys(current_top1 + anti_top1))
                knowledge = [
                    _knowledge_packet(
                        fact_id,
                        facts_by_id=case_inputs["facts_by_id"],
                        blocks=case_inputs["blocks"],
                    )
                    for fact_id in fact_ids
                ]
                payload = {
                    "case_context": case_inputs["view"]["case_context"],
                    "candidates": case_inputs["view"]["candidates"],
                    "proposal_a": current,
                    "proposal_b": anti,
                    "external_knowledge": knowledge,
                }
                assert_no_gold_leak(payload)
                critic = _critic_result(cache.call(
                    "L1FalsificationCritic", CRITIC_PROMPT, payload,
                ))
            final_raw, action = _gate(current, anti, critic)
            final_record = anti_eval._audit_record(
                arm="falsification_gated",
                replicate=replicate,
                case_id=case_id,
                raw=final_raw,
                inputs=case_inputs,
                composed=composed,
            )
            final_record["gate"] = {
                "triggered": triggered,
                "action": action,
                "critic": critic,
                "external_knowledge": knowledge,
            }
            gated_records.append(final_record)
            critic_audits.append({
                "replicate": replicate,
                "case_id": case_id,
                "triggered": triggered,
                "action": action,
                "critic": critic,
                "external_coverage": (
                    any(row["has_external_evidence"] for row in knowledge)
                    if knowledge else False
                ),
            })

    current_records = source_records["contrastive_current"]
    anti_records = source_records["anti_anchor_prompt"]
    triggered_rows = [row for row in critic_audits if row["triggered"]]
    verdict_counts: dict[str, int] = collections.Counter()
    for row in triggered_rows:
        for key in ("proposal_a", "proposal_b"):
            verdict_counts[row["critic"][key]["verdict"]] += 1
    action_counts = collections.Counter(row["action"] for row in critic_audits)
    result = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "cases": sorted(inputs),
        "replicates": args.replicates,
        "design": {
            "primary": "anti_anchor_prompt",
            "trigger": "contrastive_current top1 != anti_anchor_prompt top1",
            "critic_scope": "falsification only; cannot rank or propose",
            "external_knowledge": "frozen compiler rules and provenance only",
            "fallback": "keep anti unless critic falsifies it; then use current",
        },
        "gate_audit": {
            "total": len(critic_audits),
            "triggered": len(triggered_rows),
            "trigger_rate": len(triggered_rows) / len(critic_audits),
            "triggered_with_external_coverage": sum(
                row["external_coverage"] for row in triggered_rows
            ),
            "critic_verdict_counts": dict(verdict_counts),
            "action_counts": dict(action_counts),
        },
        "arms": {
            "contrastive_current": anti_eval._aggregate(current_records),
            "anti_anchor_prompt": anti_eval._aggregate(anti_records),
            "falsification_gated": anti_eval._aggregate(gated_records),
        },
        "paired_case_bootstrap": {
            "gated_minus_current": isolated._paired_case_bootstrap(
                current_records, gated_records,
            ),
            "gated_minus_anti": isolated._paired_case_bootstrap(
                anti_records, gated_records,
            ),
        },
        "critic_audits": critic_audits,
        "records": gated_records,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=180.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--source-summary",
        type=Path,
        default=ROOT / "logs" / "l1_anti_anchor_debate_isolated_v1"
        / "summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "logs" / "l1_falsification_gate_isolated_v1",
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        "gate_audit": result["gate_audit"],
        "arms": {
            name: values["mean_across_replicates"]
            for name, values in result["arms"].items()
        },
    }, ensure_ascii=False, indent=2))
