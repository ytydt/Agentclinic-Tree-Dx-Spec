#!/usr/bin/env python3
"""`DA_CHAMPION_AXIS_COMPLETION_V2` — four-arm champion-level axis completion on DA.

Executes the frozen contract in
`results/DA_FINALS_AXIS_COMPLETION/PREREGISTRATION.md`. Stages are separate
subcommands so the zero-call parts can be re-derived without touching the
network:

    cohort   200 heldout200b cases + frozen champions            (0 calls)
    complete restricted and unrestricted completion calls        (200 + 200)
    arms     apply the §3 contract offline -> four arms' labels  (0 calls)
    panel    C0 relation cards + M2 modifier gate                (600 + <=800)
    score    endpoints, McNemar, Holm, §6 gates                  (0 calls)

Two implementation decisions the preregistration leaves open, recorded here
because they are load-bearing:

1. `placebo_corrupt` shares the restricted completion call (§8 line 288). To
   keep the decoy from contaminating the arm it controls, `completed_label` and
   `modifiers` are emitted *before* `decoy` in the response schema: under
   autoregressive decoding the decoy tokens cannot influence tokens already
   emitted. The instruction text still mentions a decoy, which is an
   unremovable residual and is reported as a limitation rather than waved away.
2. §5 requires the three arms' new labels to be shuffled into one panel rather
   than batched by arm. Reusing C0's multi-candidate blind card satisfies this
   exactly: one card per case carries every distinct new label under neutral
   `C##` ids in a seeded shuffle, so the panel is paired by construction and
   costs 200x3 rather than 3x200x3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "backbone_v1", ROOT / "scripts" / "paper"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import baseline_common as bc  # noqa: E402

from analysis.mechanism_v2.clinical_endpoint import (  # noqa: E402
    COMPLETE,
    PARTIAL,
    ClinicalEndpoint,
    TaskEndpoint,
)
from analysis.mechanism_v2.core_regroup_headroom import content_tokens  # noqa: E402
from analysis.mechanism_v2.e2_blinded_adjudication import (  # noqa: E402
    PROMPT as C0_PROMPT,
)
from analysis.mechanism_v2.finals_loss_anatomy import (  # noqa: E402
    INFERENTIAL_MARKERS,
    added_tokens,
    axis_markers,
)

EXPERIMENT_ID = "DA_CHAMPION_AXIS_COMPLETION_V2"
OUT = ROOT / "analysis/mechanism_v2/results/DA_FINALS_AXIS_COMPLETION"
FROZEN_LOGS = ROOT / "logs/backbone_v1/diagnosisarena_heldout200b/aphhm_c_multistance_v1/case_stages"
SUBSET = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1"

DKEY, SLICE = "da", "d2_heldout200b"
COMPLETION_MODEL = "google/gemini-2.5-flash"
WORKERS = 25
SHUFFLE_SEED = 20260821

# §5 判定来源 2：复用 C0 的三模型盲评面板。
C0_REVIEWERS = {
    "reviewer_a": "google/gemini-2.5-flash",
    "reviewer_b": "deepseek/deepseek-v4-flash-0731",
    "reviewer_c": "openai/gpt-4.1",
}
# §5 幻觉率：复用 SLOT_YIELD M2 的两评审修饰词门，以便与 0.0587 / 0.1862 对齐。
MODIFIER_REVIEWERS = {
    "modifier_a": "anthropic/claude-sonnet-4.6",
    "modifier_b": "openai/gpt-5.6-sol",
}

SURFACE_AXES = ("anatomy", "subtype_histology", "composite_component")
INFERENTIAL_AXES = tuple(sorted(INFERENTIAL_MARKERS))
ALL_AXES = tuple(sorted(SURFACE_AXES + INFERENTIAL_AXES))
MAX_ADDED_TOKENS = 2

ARMS = ("frozen", "complete", "placebo_corrupt", "complete_unrestricted")

RESTRICTED_PROMPT = r"""Role: source-blind append-only diagnosis label completion implementer.

You receive one clinical vignette and one working diagnosis label. Decide
whether the vignette literally supports naming a MORE SPECIFIC diagnostic
object, and if so append the missing modifier to the working label.

Hard constraints:
- APPEND-ONLY. Every word of the working label must survive verbatim and in its
  original relative order. You may only add words around it. Never replace,
  reorder, paraphrase, abbreviate or re-case its words.
- Add the modifier as a PREFIX or as a SUFFIX, whichever yields a label a
  clinician would actually write: `Angiosarcoma` -> `Cutaneous angiosarcoma`,
  `Giant cell tumor` -> `Giant cell tumor of soft tissue`. The completed label
  must be a well-formed diagnosis name, not a word glued onto a phrase.
- Add AT MOST TWO content words in total.
- Allowed modifier axes ONLY: anatomy, subtype_histology, composite_component.
  FORBIDDEN axes: etiology, temporal_evolution, complication,
  scope_distribution. If the only defensible addition falls on a forbidden
  axis, or nothing is supported, return an empty completed_label.
- ABSTAIN when there is nothing to gain: if the working label already names the
  specific object the vignette supports, or the only available addition would
  restate a word already present in the label or a detail that does not narrow
  the diagnosis, return an empty completed_label. A gratuitous modifier is
  worse than no modifier.
- Every modifier needs a support_span quoted VERBATIM from the vignette.
- Polarity rejection: if the vignette contains a span that CONTRADICTS the
  modifier you would otherwise add, do not add it; quote that span verbatim in
  contradicting_span and return an empty completed_label.
- Use only literal patient facts. Never invent findings, tests or history.

Return strict JSON only, with the keys in exactly this order:
{"completed_label":"label or empty",
 "modifiers":[{"axis":"anatomy|subtype_histology|composite_component",
   "modifier":"the added word(s)","support_span":"verbatim vignette quotation"}],
 "contradicting_span":"verbatim vignette quotation or empty",
 "reason":"brief vignette-grounded reason",
 "decoy":{"axis":"same axis as your modifier","modifier":"the added word(s)",
   "support_span":"verbatim vignette quotation","why_wrong":"brief"}}

The decoy is an experimental control, never a diagnosis. It must be on the same
axis as your chosen modifier, appear verbatim in THIS vignette, and refer to a
DIFFERENT anatomical site, histological subtype or composite component than the
one you chose, so that it is clinically wrong for this case. Fill it only if
completed_label is non-empty; otherwise use empty strings.
"""

UNRESTRICTED_PROMPT = r"""Role: source-blind append-only diagnosis label completion implementer.

You receive one clinical vignette and one working diagnosis label. Decide
whether the vignette literally supports naming a MORE SPECIFIC diagnostic
object, and if so append the missing modifiers to the working label.

Hard constraints:
- APPEND-ONLY. Every word of the working label must survive verbatim and in its
  original relative order. You may only add words around it. Never replace,
  reorder, paraphrase, abbreviate or re-case its words.
- Add the modifiers as a PREFIX, a SUFFIX, or both, whichever yields a label a
  clinician would actually write: `Angiosarcoma` -> `Cutaneous angiosarcoma`,
  `Catatonia` -> `Catatonia related to underlying Lewy body dementia`. The
  completed label must be a well-formed diagnosis name, not words glued onto a
  phrase.
- There is NO limit on how many words you may add.
- All seven modifier axes are allowed: anatomy, subtype_histology,
  composite_component, etiology, temporal_evolution, complication,
  scope_distribution.
- ABSTAIN when there is nothing to gain: if the working label already names the
  specific object the vignette supports, or the only available addition would
  restate a word already present in the label or a detail that does not narrow
  the diagnosis, return an empty completed_label. A gratuitous modifier is
  worse than no modifier.
- Every modifier needs a support_span quoted VERBATIM from the vignette.
- Polarity rejection: if the vignette contains a span that CONTRADICTS a
  modifier you would otherwise add, do not add it; quote that span verbatim in
  contradicting_span.
- Use only literal patient facts. Never invent findings, tests or history.

Return strict JSON only:
{"completed_label":"label or empty",
 "modifiers":[{"axis":"one of the seven allowed axes",
   "modifier":"the added word(s)","support_span":"verbatim vignette quotation"}],
 "contradicting_span":"verbatim vignette quotation or empty",
 "reason":"brief vignette-grounded reason"}
"""

MODIFIER_PROMPT = r"""You are an independent binary modifier-support reviewer.
The diagnostic system and experimental arm are hidden. For every modifier,
decide whether (1) its quoted support_span occurs literally in the supplied
vignette and (2) that span clinically supports the modifier as a reasonable
part of the completed diagnosis label. Do not infer unobserved patient facts.
Return strict JSON and cover every modifier_id exactly once:
{"judgments":[{"modifier_id":"M001","supported":true,
"reason":"brief vignette-grounded reason"}]}"""

PROMPT_SHA = {
    "restricted_completion": hashlib.sha256(RESTRICTED_PROMPT.encode()).hexdigest(),
    "unrestricted_completion": hashlib.sha256(UNRESTRICTED_PROMPT.encode()).hexdigest(),
    "c0_relation_panel": hashlib.sha256(C0_PROMPT.encode()).hexdigest(),
    "m2_modifier_gate": hashlib.sha256(MODIFIER_PROMPT.encode()).hexdigest(),
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# stage: cohort
# --------------------------------------------------------------------------


def build_cohort() -> list[dict[str, Any]]:
    """§1: normalized vignette, non-empty frozen registry, non-empty champion.

    Admission deliberately ignores whether the champion is right and what its
    clinical relation is, so no endpoint information leaks into the cohort.
    """
    cases = bc.load_runtime_cases(subset_dir=SUBSET, dataset="diagnosisarena")
    by_source = {str(c["source_id"]): c for c in cases}
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()

    for path in sorted(FROZEN_LOGS.glob("*.json")):
        log = read_json(path)
        champion = str(log.get("champion") or "").strip()
        registry = ((log.get("stages") or {}).get("registry")) or []
        source_id = str(log.get("source_id") or "")
        case = by_source.get(source_id)
        if case is None:
            skipped["no_subset_row"] += 1
            continue
        if not champion:
            skipped["empty_champion"] += 1
            continue
        if not registry:
            skipped["empty_registry"] += 1
            continue
        if not str(case.get("vignette") or "").strip():
            skipped["empty_vignette"] += 1
            continue
        rows.append({
            "case_id": str(log.get("case_id")),
            "source_id": source_id,
            "vignette": str(case["vignette"]),
            "champion": champion,
            "pool_width": len(registry),
            # `_`-prefixed: §1 restricts gold to the analyze stage. The completion
            # payload is built from `vignette` and `champion` only.
            "_gold": str(case.get("_gold_text") or ""),
        })

    if skipped:
        raise AssertionError(f"cohort admission dropped cases: {dict(skipped)}")
    return rows


def stage_cohort(_: argparse.Namespace) -> int:
    rows = build_cohort()
    write_json(OUT / "cohort" / "cohort.json", {
        "experiment_id": EXPERIMENT_ID,
        "created_at": utcnow(),
        "slice": f"{DKEY}/{SLICE}",
        "frozen_baseline": FROZEN_LOGS.relative_to(ROOT).as_posix(),
        "n_cases": len(rows),
        "mean_pool_width": round(sum(r["pool_width"] for r in rows) / len(rows), 4),
        "cases": rows,
    })
    print(f"cohort n={len(rows)} mean_width={sum(r['pool_width'] for r in rows)/len(rows):.3f}")
    return 0


# --------------------------------------------------------------------------
# stage: complete
# --------------------------------------------------------------------------


def make_llm(cache: Path, model: str) -> bc.SimpleCachedLLM:
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    client = RobustLLMClient(model=model, temperature=0.0)
    return bc.SimpleCachedLLM(client, cache, model)


def run_pool(fn, items: Sequence[Any], workers: int) -> list[Any]:
    out: list[Any] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): item for item in items}
        for fut in as_completed(futures):
            out.append(fut.result())
    return out


def stage_complete(args: argparse.Namespace) -> int:
    cohort = read_json(OUT / "cohort" / "cohort.json")["cases"]
    variant = args.variant
    if args.limit:
        cohort = cohort[: args.limit]
    prompt = RESTRICTED_PROMPT if variant == "restricted" else UNRESTRICTED_PROMPT
    module = f"DaAxisCompletion_{variant}"
    llm = make_llm(OUT / "completion" / variant / "cache.json", COMPLETION_MODEL)

    def one(row: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "case_id": row["case_id"],
            "vignette": row["vignette"],
            "working_label": row["champion"],
            "allowed_axes": list(SURFACE_AXES if variant == "restricted" else ALL_AXES),
            "max_added_content_words": MAX_ADDED_TOKENS if variant == "restricted" else 0,
        }
        try:
            resp = llm.call(module, prompt, payload)
            return {"case_id": row["case_id"], "ok": True, "response": resp}
        except Exception as exc:  # noqa: BLE001 - recorded as non-service
            return {"case_id": row["case_id"], "ok": False, "error": repr(exc)[:400]}

    results = run_pool(one, cohort, WORKERS)
    results.sort(key=lambda r: r["case_id"])
    served = sum(1 for r in results if r["ok"])
    # A truncated run must not leave a file the `arms` stage would read as final.
    name = "responses.json" if not args.limit else f"responses_smoke{args.limit}.json"
    write_json(OUT / "completion" / variant / name, {
        "experiment_id": EXPERIMENT_ID,
        "variant": variant,
        "created_at": utcnow(),
        "model": COMPLETION_MODEL,
        "prompt_sha256": PROMPT_SHA[f"{variant}_completion"],
        "n": len(results),
        "n_served": served,
        "service_rate": round(served / len(results), 4),
        "online_calls": llm.calls,
        "results": results,
    })
    print(f"{variant}: n={len(results)} served={served} online_calls={llm.calls}")
    return 0


# --------------------------------------------------------------------------
# stage: arms (offline contract)
# --------------------------------------------------------------------------


def _ordered_subsequence(short: Sequence[str], long: Sequence[str]) -> bool:
    """True if `short` appears inside `long` in order (gaps allowed)."""
    it = iter(long)
    return all(tok in it for tok in short)


def check_contract(
    champion: str,
    completed: str,
    vignette: str,
    modifiers: Sequence[Mapping[str, Any]],
    contradicting: str,
    *,
    restricted: bool,
) -> tuple[str, list[str]]:
    """Return (accepted|rejected, violation codes). Rejected keeps the champion."""
    codes: list[str] = []
    if not completed or completed.strip() == champion.strip():
        return "no_completion", []

    base, done = content_tokens(champion), content_tokens(completed)
    if not _ordered_subsequence(base, done):
        codes.append("not_append_only")

    added = added_tokens(champion, completed)
    if not added:
        codes.append("no_added_tokens")
    if restricted:
        hits = axis_markers(added)
        if hits:
            codes.append("axis_violation")
        if len(added) > MAX_ADDED_TOKENS:
            codes.append("over_specified")
        for mod in modifiers:
            if str(mod.get("axis") or "") not in SURFACE_AXES:
                codes.append("axis_violation_declared")
                break
    else:
        for mod in modifiers:
            if str(mod.get("axis") or "") not in ALL_AXES:
                codes.append("axis_violation_declared")
                break

    if not modifiers:
        codes.append("no_modifier_supplied")
    for mod in modifiers:
        span = str(mod.get("support_span") or "")
        if not span or span not in vignette:
            codes.append("span_not_verbatim")
            break

    if contradicting:
        # §3 极性拒绝：矛盾 span 必须逐字，且其存在即要求拒绝该修饰词。
        codes.append(
            "polarity_reject" if contradicting in vignette else "polarity_span_not_verbatim"
        )

    return ("accepted" if not codes else "rejected"), sorted(set(codes))


def stage_arms(_: argparse.Namespace) -> int:
    cohort = {r["case_id"]: r for r in read_json(OUT / "cohort" / "cohort.json")["cases"]}
    out_rows: dict[str, dict[str, Any]] = {}
    stats: dict[str, Counter] = {v: Counter() for v in ("restricted", "unrestricted")}

    loaded = {}
    for variant in ("restricted", "unrestricted"):
        path = OUT / "completion" / variant / "responses.json"
        if not path.is_file():
            raise SystemExit(f"missing {path}; run `complete --variant {variant}` first")
        loaded[variant] = {r["case_id"]: r for r in read_json(path)["results"]}

    for cid, row in cohort.items():
        champion, vignette = row["champion"], row["vignette"]
        rec: dict[str, Any] = {
            "case_id": cid,
            "champion": champion,
            "labels": {"frozen": champion},
            "contract": {},
            "modifiers": {},
        }

        for variant, arm in (("restricted", "complete"), ("unrestricted", "complete_unrestricted")):
            res = loaded[variant].get(cid) or {}
            resp = res.get("response") or {}
            served = bool(res.get("ok"))
            completed = str(resp.get("completed_label") or "").strip()
            mods = [m for m in (resp.get("modifiers") or []) if isinstance(m, Mapping)]
            contradicting = str(resp.get("contradicting_span") or "").strip()
            status, codes = ("not_served", ["not_served"]) if not served else check_contract(
                champion, completed, vignette, mods, contradicting,
                restricted=(variant == "restricted"),
            )
            accepted = status == "accepted"
            rec["labels"][arm] = completed if accepted else champion
            rec["contract"][arm] = {
                "served": served,
                "status": status,
                "violations": codes,
                "proposed_label": completed,
                "n_added_content_tokens": len(added_tokens(champion, completed)) if completed else 0,
            }
            rec["modifiers"][arm] = [
                {
                    "axis": str(m.get("axis") or ""),
                    "modifier": str(m.get("modifier") or ""),
                    "support_span": str(m.get("support_span") or ""),
                    "literal_span_closed": str(m.get("support_span") or "") in vignette,
                }
                for m in mods
            ] if accepted else []
            stats[variant][status] += 1
            for code in codes:
                stats[variant][f"violation:{code}"] += 1

        # placebo_corrupt: swap the accepted restricted modifier for the decoy
        # supplied by the same call (same axis, verbatim in vignette, wrong site).
        res = loaded["restricted"].get(cid) or {}
        resp = res.get("response") or {}
        decoy = resp.get("decoy") if isinstance(resp.get("decoy"), Mapping) else {}
        placebo, p_status = champion, "unavailable"
        if rec["contract"]["complete"]["status"] == "accepted":
            d_mod = str((decoy or {}).get("modifier") or "").strip()
            d_span = str((decoy or {}).get("support_span") or "").strip()
            real = rec["modifiers"]["complete"][0] if rec["modifiers"]["complete"] else None
            good = str((real or {}).get("modifier") or "").strip()
            if d_mod and d_span and d_span in vignette and good and d_mod.lower() != good.lower():
                swapped = rec["labels"]["complete"]
                if good in swapped:
                    cand = swapped.replace(good, d_mod)
                    # The placebo must obey the same append-only contract.
                    st, _codes = check_contract(
                        champion, cand, vignette,
                        [{"axis": str((decoy or {}).get("axis") or ""), "support_span": d_span}],
                        "", restricted=True,
                    )
                    if st == "accepted":
                        placebo, p_status = cand, "corrupted"
                    else:
                        p_status = f"rejected:{st}"
                else:
                    p_status = "modifier_not_locatable"
            else:
                p_status = "no_usable_decoy"
        else:
            p_status = "upstream_not_accepted"
        rec["labels"]["placebo_corrupt"] = placebo
        rec["contract"]["placebo_corrupt"] = {"status": p_status}
        stats["restricted"][f"placebo:{p_status}"] += 1
        out_rows[cid] = rec

    widths = {arm: 1.0 for arm in ARMS}  # append-only never adds a seat
    changed = {
        arm: sum(1 for r in out_rows.values() if r["labels"][arm] != r["champion"])
        for arm in ARMS
    }
    write_json(OUT / "arms" / "arms.json", {
        "experiment_id": EXPERIMENT_ID,
        "created_at": utcnow(),
        "n_cases": len(out_rows),
        "labels_changed_vs_frozen": changed,
        "mean_width": widths,
        "contract_stats": {k: dict(sorted(v.items())) for k, v in stats.items()},
        "cases": [out_rows[c] for c in sorted(out_rows)],
    })
    print(json.dumps({"changed_vs_frozen": changed}, ensure_ascii=False))
    for variant, counter in stats.items():
        print(f"{variant}: {dict(sorted(counter.items()))}")
    return 0


# --------------------------------------------------------------------------
# stage: panel
# --------------------------------------------------------------------------

NON_FROZEN_ARMS = ("complete", "placebo_corrupt", "complete_unrestricted")


def build_cards(
    rows: Sequence[Mapping[str, Any]],
    ce: ClinicalEndpoint,
    sid_of: Mapping[str, str],
) -> list[dict[str, Any]]:
    """One blind card per case carrying every label the frozen sources miss.

    §5 forbids batching by arm, so the arms' labels share a card under neutral
    ids in a seeded shuffle; the reviewer cannot tell which arm produced which.
    """
    rng = random.Random(SHUFFLE_SEED)
    cards: list[dict[str, Any]] = []
    for row in rows:
        cid = row["case_id"]
        wanted: dict[str, list[str]] = {}
        for arm in NON_FROZEN_ARMS:
            label = row["labels"][arm]
            if label == row["champion"]:
                continue  # frozen champion relation is already covered
            if ce.relation(DKEY, SLICE, sid_of[cid], label) is not None:
                continue  # §5 source 1: frozen reuse
            wanted.setdefault(label, []).append(arm)
        if not wanted:
            continue
        labels = sorted(wanted)
        rng.shuffle(labels)
        cards.append({
            "blind_case_id": f"DAC{len(cards):04d}",
            "case_id": cid,
            "candidates": [
                {"candidate_id": f"C{i + 1:02d}", "label": lab, "_arms": wanted[lab]}
                for i, lab in enumerate(labels)
            ],
        })
    return cards


def stage_panel(args: argparse.Namespace) -> int:
    arms = read_json(OUT / "arms" / "arms.json")["cases"]
    cohort = {r["case_id"]: r for r in read_json(OUT / "cohort" / "cohort.json")["cases"]}
    ce = ClinicalEndpoint()
    if args.kind == "relation":
        return _panel_relation(arms, cohort, ce, args)
    return _panel_modifier(arms, cohort, args)


def _panel_relation(
    arms: Sequence[Mapping[str, Any]],
    cohort: Mapping[str, Any],
    ce: ClinicalEndpoint,
    args: argparse.Namespace,
) -> int:
    cards = build_cards(arms, ce, {c: r["source_id"] for c, r in cohort.items()})
    if args.limit:
        cards = cards[: args.limit]
    n_labels = sum(len(c["candidates"]) for c in cards)
    print(f"relation panel: cards={len(cards)} labels={n_labels} calls={len(cards) * 3}")

    all_rows: list[dict[str, Any]] = []
    for reviewer, model in sorted(C0_REVIEWERS.items()):
        llm = make_llm(OUT / "panel" / "relation" / reviewer / "cache.json", model)

        def one(card: Mapping[str, Any], _llm=llm, _rv=reviewer) -> dict[str, Any]:
            case = cohort[card["case_id"]]
            payload = {
                "blind_case_id": card["blind_case_id"],
                "clinical_record": case["vignette"],
                "reference_diagnosis": case["_gold"],
                "candidate_registry": [
                    {"candidate_id": c["candidate_id"], "label": c["label"]}
                    for c in card["candidates"]
                ],
            }
            try:
                resp = _llm.call(f"DaAxisRelationPanel_{_rv}", C0_PROMPT, payload)
                return {"blind_case_id": card["blind_case_id"], "reviewer": _rv,
                        "ok": True, "review": resp}
            except Exception as exc:  # noqa: BLE001
                return {"blind_case_id": card["blind_case_id"], "reviewer": _rv,
                        "ok": False, "error": repr(exc)[:400]}

        rows = run_pool(one, cards, WORKERS)
        rows.sort(key=lambda r: r["blind_case_id"])
        all_rows.extend(rows)
        served = sum(1 for r in rows if r["ok"])
        print(f"  {reviewer}: served={served}/{len(rows)} online={llm.calls}")

    write_json(OUT / "panel" / "relation" / "reviews.json", {
        "experiment_id": EXPERIMENT_ID,
        "created_at": utcnow(),
        "reviewers": C0_REVIEWERS,
        "prompt_sha256": PROMPT_SHA["c0_relation_panel"],
        "shuffle_seed": SHUFFLE_SEED,
        "cards": cards,
        "reviews": all_rows,
    })
    return 0


def _panel_modifier(
    arms: Sequence[Mapping[str, Any]],
    cohort: Mapping[str, Any],
    args: argparse.Namespace,
) -> int:
    """§5 hallucination rate, on the SLOT_YIELD M2 two-reviewer definition.

    `placebo_corrupt` is deliberately excluded: its modifier is constructed to be
    clinically wrong, so its hallucination rate is ~1.0 by design and measuring
    it would burn 200+ calls to confirm the construction.
    """
    cards: list[dict[str, Any]] = []
    for row in arms:
        for arm in ("complete", "complete_unrestricted"):
            mods = row["modifiers"][arm]
            if not mods:
                continue
            cards.append({
                "blind_completion_id": f"DAM{len(cards):04d}",
                "case_id": row["case_id"],
                "arm": arm,
                "parent_label": row["champion"],
                "completed_label": row["labels"][arm],
                "modifiers": [
                    {"modifier_id": f"M{i + 1:03d}", **m} for i, m in enumerate(mods)
                ],
            })
    if args.limit:
        cards = cards[: args.limit]
    print(f"modifier gate: cards={len(cards)} calls={len(cards) * 2}")

    all_rows: list[dict[str, Any]] = []
    for reviewer, model in sorted(MODIFIER_REVIEWERS.items()):
        llm = make_llm(OUT / "panel" / "modifier" / reviewer / "cache.json", model)

        def one(card: Mapping[str, Any], _llm=llm, _rv=reviewer) -> dict[str, Any]:
            payload = {
                "blind_completion_id": card["blind_completion_id"],
                "clinical_record": cohort[card["case_id"]]["vignette"],
                "parent_label": card["parent_label"],
                "completed_label": card["completed_label"],
                "modifiers": [
                    {
                        "modifier_id": m["modifier_id"],
                        "axis": m["axis"],
                        "modifier": m["modifier"],
                        "support_span": m["support_span"],
                    }
                    for m in card["modifiers"]
                ],
            }
            try:
                resp = _llm.call(f"DaAxisModifierGate_{_rv}", MODIFIER_PROMPT, payload)
                return {"blind_completion_id": card["blind_completion_id"],
                        "reviewer": _rv, "ok": True, "review": resp}
            except Exception as exc:  # noqa: BLE001
                return {"blind_completion_id": card["blind_completion_id"],
                        "reviewer": _rv, "ok": False, "error": repr(exc)[:400]}

        rows = run_pool(one, cards, WORKERS)
        rows.sort(key=lambda r: r["blind_completion_id"])
        all_rows.extend(rows)
        served = sum(1 for r in rows if r["ok"])
        print(f"  {reviewer}: served={served}/{len(rows)} online={llm.calls}")

    write_json(OUT / "panel" / "modifier" / "reviews.json", {
        "experiment_id": EXPERIMENT_ID,
        "created_at": utcnow(),
        "reviewers": MODIFIER_REVIEWERS,
        "prompt_sha256": PROMPT_SHA["m2_modifier_gate"],
        "excludes": "placebo_corrupt (wrong by construction)",
        "cards": cards,
        "reviews": all_rows,
    })
    return 0


# --------------------------------------------------------------------------
# stage: score
# --------------------------------------------------------------------------


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    lo = min(b, c)
    tail = sum(math.comb(n, k) for k in range(lo + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def holm(pvals: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values within one family."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (key, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[key] = round(running, 6)
    return out


def panel_relations(cards: Sequence[Mapping[str, Any]], reviews: Sequence[Mapping[str, Any]]):
    """(case_id, label) -> majority relation; a three-way split is `uncertain`."""
    by_card = {c["blind_case_id"]: c for c in cards}
    votes: dict[tuple[str, str], list[str]] = {}
    served: Counter[str] = Counter()
    for row in reviews:
        if not row.get("ok"):
            served["failed"] += 1
            continue
        served["ok"] += 1
        card = by_card.get(row["blind_case_id"])
        if card is None:
            continue
        labels = {c["candidate_id"]: c["label"] for c in card["candidates"]}
        for item in (row.get("review") or {}).get("candidate_relations") or []:
            label = labels.get(str(item.get("candidate_id") or ""))
            rel = str(item.get("relation") or "")
            if label and rel:
                votes.setdefault((card["case_id"], label), []).append(rel)

    out: dict[tuple[str, str], str] = {}
    for key, vs in votes.items():
        top, n = Counter(vs).most_common(1)[0]
        out[key] = top if n >= 2 else "uncertain"
    return out, dict(served)


def stage_score(_: argparse.Namespace) -> int:
    rows = read_json(OUT / "arms" / "arms.json")["cases"]
    cohort = {r["case_id"]: r for r in read_json(OUT / "cohort" / "cohort.json")["cases"]}
    rel_doc = read_json(OUT / "panel" / "relation" / "reviews.json")
    panel, panel_service = panel_relations(rel_doc["cards"], rel_doc["reviews"])

    ce_all = ClinicalEndpoint()
    ce_strict = ClinicalEndpoint()
    ce_strict.drop_conflicts()

    # The frozen sources key on the numeric source id, not the padded case id.
    sid_of = {c: r["source_id"] for c, r in cohort.items()}

    def relation_of(ce: ClinicalEndpoint, cid: str, label: str) -> str:
        frozen = ce.relation(DKEY, SLICE, sid_of[cid], label)
        if frozen is not None:
            return frozen
        return panel.get((cid, label), "unjudged")

    def per_arm(ce: ClinicalEndpoint, uncertain_as: str) -> dict[str, dict[str, Any]]:
        res: dict[str, dict[str, Any]] = {}
        for arm in ARMS:
            flags: dict[str, Any] = {}
            counts: Counter[str] = Counter()
            for row in rows:
                cid = row["case_id"]
                rel = relation_of(ce, cid, row["labels"][arm])
                counts[rel] += 1
                if rel in ("uncertain", "unjudged") and uncertain_as == "drop":
                    flags[cid] = None
                else:
                    flags[cid] = rel == COMPLETE
            res[arm] = {
                "complete": sum(1 for v in flags.values() if v),
                "complete_or_partial": sum(
                    1 for row in rows
                    if relation_of(ce, row["case_id"], row["labels"][arm]) in (COMPLETE, PARTIAL)
                ),
                "relations": dict(counts.most_common()),
                "_flags": flags,
            }
        return res

    def contrast(res: Mapping[str, Any], a: str, b: str) -> dict[str, Any]:
        """Paired: b is the reference arm, a the arm under test."""
        fa, fb = res[a]["_flags"], res[b]["_flags"]
        gain = [c for c in fa if fa[c] is True and fb.get(c) is False]
        loss = [c for c in fa if fa[c] is False and fb.get(c) is True]
        p = mcnemar_exact(len(gain), len(loss))
        return {
            "arm": a, "reference": b,
            "n_complete_arm": res[a]["complete"], "n_complete_reference": res[b]["complete"],
            "delta_cases": res[a]["complete"] - res[b]["complete"],
            "delta_pp": round(100 * (res[a]["complete"] - res[b]["complete"]) / len(rows), 3),
            "discordant_gain": len(gain), "discordant_loss": len(loss),
            "mcnemar_exact_p": round(p, 6),
            "gain_case_ids": sorted(gain)[:20], "loss_case_ids": sorted(loss)[:20],
        }

    primary = per_arm(ce_all, "failure")
    # §1 pinned the frozen baseline at 6/200 before execution. Reproducing it is
    # the fidelity check that the endpoint join is keyed correctly.
    frozen_cov = sum(
        1 for row in rows
        if ce_all.relation(DKEY, SLICE, sid_of[row["case_id"]], row["champion"]) is not None
    )
    fidelity = {
        "frozen_champion_endpoint_coverage": f"{frozen_cov}/{len(rows)}",
        "frozen_complete_observed": primary["frozen"]["complete"],
        "frozen_complete_preregistered": 6,
        "matches_preregistration": primary["frozen"]["complete"] == 6,
    }
    contrasts = {
        "complete_vs_frozen": contrast(primary, "complete", "frozen"),
        "complete_vs_placebo": contrast(primary, "complete", "placebo_corrupt"),
    }
    main_family = holm({k: v["mcnemar_exact_p"] for k, v in contrasts.items()})
    exchange = {
        "coverage_unrestricted_vs_complete": contrast(
            primary, "complete_unrestricted", "complete"
        ),
    }

    # §5 hallucination rate on the SLOT_YIELD M2 definition: a modifier counts as
    # supported only when every serving reviewer says so.
    mod_doc = read_json(OUT / "panel" / "modifier" / "reviews.json")
    mod_cards = {c["blind_completion_id"]: c for c in mod_doc["cards"]}
    mod_votes: dict[tuple[str, str], list[bool]] = {}
    for row in mod_doc["reviews"]:
        if not row.get("ok"):
            continue
        card = mod_cards.get(row["blind_completion_id"])
        if card is None:
            continue
        for j in (row.get("review") or {}).get("judgments") or []:
            mid = str(j.get("modifier_id") or "")
            if any(m["modifier_id"] == mid for m in card["modifiers"]):
                mod_votes.setdefault((card["blind_completion_id"], mid), []).append(
                    bool(j.get("supported"))
                )
    halluc: dict[str, dict[str, Any]] = {}
    for arm in ("complete", "complete_unrestricted"):
        ids = [k for k, c in mod_cards.items() if c["arm"] == arm]
        total = sum(len(mod_cards[i]["modifiers"]) for i in ids)
        served_keys = [k for k in mod_votes if k[0] in set(ids) and len(mod_votes[k]) == 2]
        unsupported = sum(1 for k in served_keys if not all(mod_votes[k]))
        agree = sum(1 for k in served_keys if len(set(mod_votes[k])) == 1)
        literal = sum(
            1 for i in ids for m in mod_cards[i]["modifiers"] if m.get("literal_span_closed")
        )
        halluc[arm] = {
            "n_completions": len(ids), "n_modifiers": total,
            "n_two_reviewer_served": len(served_keys),
            "service_rate": round(len(served_keys) / total, 4) if total else 0.0,
            "literal_closure": round(literal / total, 4) if total else 0.0,
            "raw_agreement": round(agree / len(served_keys), 4) if served_keys else None,
            "hallucination_rate": round(unsupported / len(served_keys), 4) if served_keys else 1.0,
        }

    # §5 secondary endpoints. Prediction 4 expects legacy `dc.match` to move the
    # OPPOSITE way from clinical-complete, because appending a modifier forfeits
    # the lexical credit `dc.match` gives coarse parents.
    import disagreement_census as dc  # noqa: PLC0415 - heavy import, analyze only

    legacy = {
        arm: sum(
            1 for row in rows
            if dc.match(row["labels"][arm], cohort[row["case_id"]]["_gold"])
        )
        for arm in ARMS
    }
    te = TaskEndpoint()
    task: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        judged = [
            te.correct(DKEY, SLICE, sid_of[row["case_id"]], row["labels"][arm])
            for row in rows
        ]
        covered = [v for v in judged if v is not None]
        task[arm] = {
            "frozen_coverage": f"{len(covered)}/{len(rows)}",
            "correct_within_covered": sum(1 for v in covered if v),
            "not_projected_online": len(rows) - len(covered),
        }

    completion_service = {
        v: read_json(OUT / "completion" / v / "responses.json")["service_rate"]
        for v in ("restricted", "unrestricted")
    }
    online = {
        p.parent.relative_to(OUT).as_posix(): len(read_json(p))
        for p in sorted(OUT.rglob("cache.json"))
    }

    gates = {
        "service_rate_all_arms_ge_0_98": min(completion_service.values()) >= 0.98,
        "complete_gt_frozen_holm_p_lt_0_05": (
            contrasts["complete_vs_frozen"]["delta_cases"] >= 0
            and main_family["complete_vs_frozen"] < 0.05
        ),
        "complete_gt_placebo_holm_p_lt_0_05": (
            contrasts["complete_vs_placebo"]["delta_cases"] >= 0
            and main_family["complete_vs_placebo"] < 0.05
        ),
        "hallucination_rate_le_0_10": halluc["complete"]["hallucination_rate"] <= 0.10,
        "mean_width_identical_to_frozen": True,  # append-only never adds a seat
    }

    summary = {
        "experiment_id": EXPERIMENT_ID,
        "created_at": utcnow(),
        "n_cases": len(rows),
        "prompt_sha256": PROMPT_SHA,
        "online_calls_by_cache": online,
        "online_calls_total": sum(online.values()),
        "completion_service_rate": completion_service,
        "panel_service": panel_service,
        "fidelity": fidelity,
        "arms": {
            a: {k: v for k, v in primary[a].items() if not k.startswith("_")}
            for a in ARMS
        },
        "primary_family_holm": main_family,
        "contrasts": contrasts,
        "exchange_rate_family": exchange,
        "hallucination": halluc,
        "secondary_legacy_dc_match": legacy,
        "secondary_task_endpoint": task,
        "gates": gates,
        "verdict": "GO" if all(gates.values()) else "NO_GO",
        "sensitivity": {
            "uncertain_dropped": {
                a: per_arm(ce_all, "drop")[a]["complete"] for a in ARMS
            },
            "drop_source_conflicts": {
                a: per_arm(ce_strict, "failure")[a]["complete"] for a in ARMS
            },
        },
    }
    write_json(OUT / "summary.json", summary)
    print(json.dumps({
        k: summary[k] for k in
        ("arms", "primary_family_holm", "contrasts", "exchange_rate_family",
         "hallucination", "gates", "verdict", "online_calls_total", "sensitivity")
    }, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=EXPERIMENT_ID)
    sub = ap.add_subparsers(dest="stage", required=True)
    sub.add_parser("cohort").set_defaults(fn=stage_cohort)
    c = sub.add_parser("complete")
    c.add_argument("--variant", required=True, choices=("restricted", "unrestricted"))
    c.add_argument("--limit", type=int, default=0, help="smoke-test the first N cases")
    c.set_defaults(fn=stage_complete)
    sub.add_parser("arms").set_defaults(fn=stage_arms)
    p = sub.add_parser("panel")
    p.add_argument("--kind", required=True, choices=("relation", "modifier"))
    p.add_argument("--limit", type=int, default=0, help="smoke-test the first N cards")
    p.set_defaults(fn=stage_panel)
    sub.add_parser("score").set_defaults(fn=stage_score)
    args = ap.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
