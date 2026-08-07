"""Steps 10–14 of the explainer pipeline for DiagnosisArena (L2 + joint + metrics)."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_branch_generation_ab as l2_ab  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
import eval_l2_dynamic_evidence_marginals as dynamic  # noqa: E402
import eval_l2_joint_dynamic_pipeline as joint  # noqa: E402
from agentclinic_tree_dx.config import ControllerConfig  # noqa: E402
from agentclinic_tree_dx.controller import AgentClinicTreeController  # noqa: E402
from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    DiseaseNameResolver,
    _normalize_label,
)
from agentclinic_tree_dx.state import Branch, DiagnosticState, RootNode  # noqa: E402

PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
JOINT_ARM = "A3-joint-primary"
JOINT_SPEC = joint.ARM_SPECS[JOINT_ARM]


def findings_catalog(state: DiagnosticState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(state.static_evidence_items or ()):
        if isinstance(item, Mapping):
            text = str(
                item.get("content")
                or item.get("fact")
                or item.get("description")
                or ""
            ).strip()
            source_id = str(item.get("id") or item.get("source_id") or "")
        else:
            text = str(getattr(item, "content", "") or "").strip()
            source_id = str(getattr(item, "id", "") or "")
        if not text:
            continue
        rows.append({
            "id": "F%d" % (len(rows) + 1),
            "source_id": source_id or ("E%d" % (index + 1)),
            "text": text,
        })
    return rows


def l1_posterior_rows(state: DiagnosticState) -> list[dict[str, Any]]:
    return [
        {
            "id": branch.id,
            "label": branch.label,
            "posterior": float(branch.posterior or 0.0),
        }
        for branch in sorted(
            (row for row in state.branches.values() if row.level == 1),
            key=lambda row: (-float(row.posterior or 0.0), row.id),
        )
    ]


def f2_from_bfs_trace(
    findings: Sequence[Mapping[str, Any]],
    trace: Mapping[str, Any],
) -> list[dict[str, Any]]:
    selected = [
        str(fact_id)
        for fact_id in (trace.get("selected_fact_ids") or ())
        if str(fact_id)
    ]
    if not selected:
        return []
    by_text = {
        str(row.get("text") or row.get("finding") or ""): str(row["id"])
        for row in findings
    }
    mapped: list[str] = []
    for fact_id in selected:
        if fact_id in {str(row["id"]) for row in findings}:
            mapped.append(fact_id)
            continue
        for row in trace.get("rounds") or ():
            if str(row.get("fact_id") or "") != fact_id:
                continue
            text = str(row.get("fact_text") or row.get("text") or "")
            catalog_id = by_text.get(text)
            if catalog_id:
                mapped.append(catalog_id)
            break
    if not mapped:
        mapped = selected[:2]
    return joint._facts_for_ids(findings, mapped[:2])


def deserialize_state(payload: Mapping[str, Any]) -> DiagnosticState:
    state = DiagnosticState(case_id=str(payload.get("case_id") or ""))
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


def run_config_a_l2_generation(
    *,
    serialized_state: Mapping[str, Any],
    cached_adapter: l2_ab.CachedModuleAdapter,
    candidate_budget: int = 24,
    snippet_budget: int = 8,
    force_emit_uncovered: bool = False,
    force_emit_max: int = 3,
    tree_semantic_dedupe: bool = True,
) -> tuple[DiagnosticState, dict[str, Any]]:
    """Step 10: strip prior L2, regenerate with Config A (per_parent recall)."""
    seed = l2_ab.strip_l2_seed(serialized_state)
    state = deserialize_state(seed)
    config = ControllerConfig(
        talp_disc_profile="off",
        l2_branch_generation_mode="per_parent",
        l2_recall_candidate_budget=int(candidate_budget),
        l2_recall_snippet_budget=int(snippet_budget),
        l2_recall_gap_fill=True,
        l2_gap_force_emit_uncovered=bool(force_emit_uncovered),
        l2_gap_force_emit_max=int(force_emit_max),
        tree_semantic_dedupe=bool(tree_semantic_dedupe),
        force_expand_all_l1=True,
        enable_case_report_branch_source=True,
        enable_cpg_branch_source=True,
        enable_llm_ddx_branch_entrance=True,
        allow_external_knowledge=False,
    )
    controller = AgentClinicTreeController(
        env=SimpleNamespace(ingest_external_context=lambda _value: None),
        llm=cached_adapter,
        config=config,
    )
    expansion = controller.force_expand_all_l1(state)
    if expansion.get("l1_expansion_rate") != 1.0:
        raise RuntimeError(
            "Config A L2 expansion incomplete: %s"
            % expansion.get("l1_expansion_rate")
        )
    recall_audit = controller.get_l2_recall_audit()
    n_force = 0
    for row in (recall_audit or {}).values() if isinstance(recall_audit, dict) else ():
        if isinstance(row, Mapping):
            n_force += int(row.get("force_emit_n") or 0)
    return state, {
        "expansion": expansion,
        "recall_audit": recall_audit,
        "config_a": {
            "mode": "per_parent",
            "candidate_budget": candidate_budget,
            "snippet_budget": snippet_budget,
            "force_emit_uncovered": bool(force_emit_uncovered),
            "force_emit_max": int(force_emit_max),
            "force_emit_n_total": n_force,
            "tree_semantic_dedupe": bool(tree_semantic_dedupe),
        },
    }


def run_joint_primary(
    *,
    case_text: str,
    state: DiagnosticState,
    findings: Sequence[Mapping[str, Any]],
    f2_facts: Sequence[Mapping[str, Any]],
    cache,
    local_evidence_budget: int = 4,
    between_evidence_budget: int = 2,
    scope_mode: str = "per_family",
) -> dict[str, Any]:
    """Steps 11–12: dynamic local champions + A3 joint arbiter final ranking."""
    selector_prompt = dynamic.PROMPT_PATH.read_text(encoding="utf-8")
    annotator_prompt = competition.ANNOTATOR_PROMPT_PATH.read_text(encoding="utf-8")
    arbiter_prompt = joint.JOINT_ARBITER_PROMPT_PATH.read_text(encoding="utf-8")
    l1_rows = l1_posterior_rows(state)
    local_n = max(1, int(local_evidence_budget))
    between_n = max(1, int(between_evidence_budget))

    dynamic_assets = joint._build_champions(
        mode="dynamic",
        cache=cache,
        selector_prompt=selector_prompt,
        annotator_prompt=annotator_prompt,
        case_text=case_text,
        findings=findings,
        l1_rows=l1_rows,
        tree_state=state,
        true_f2=f2_facts,
    )
    # Always re-run local evidence with the configured stop_after so budget
    # sweeps (incl. local==4) share one code path. Cheap cache hits when the
    # seeded F6 cache already stored the same selector/annotator payloads.
    dynamic_assets = _rebuild_champions_with_local_budget(
        cache=cache,
        selector_prompt=selector_prompt,
        annotator_prompt=annotator_prompt,
        case_text=case_text,
        findings=findings,
        l1_rows=l1_rows,
        tree_state=state,
        true_f2=f2_facts,
        local_n=local_n,
        scope_mode=scope_mode,
    )
    between_candidates = joint._selector_candidates(dynamic_assets["champions"])
    between_selection = dynamic.dynamic_l2_evidence_order(
        cache=cache,
        module="L2JointDynamicBetweenEvidenceSelector",
        prompt=selector_prompt,
        case_text=case_text,
        findings=findings,
        candidates=between_candidates,
        stop_after=between_n,
    )
    dynamic_f2 = joint._facts_for_ids(
        findings,
        between_selection.get("selected_fact_ids") or [],
    )[:between_n] or list(f2_facts)

    champions = list(dynamic_assets["champions"])
    if champions and dynamic_f2:
        arbiter = joint._joint_arbitrate(
            cache=cache,
            module=joint.ARBITER_MODULE,
            prompt=arbiter_prompt,
            case_text=case_text,
            findings=findings,
            selected_facts=dynamic_f2,
            champions=champions,
            include_prior=bool(JOINT_SPEC["prior"]),
            include_audit=bool(JOINT_SPEC["audit"]),
            context_mode=str(JOINT_SPEC["context"]),
            selector_effects=[],
        )
    else:
        arbiter = {
            "schema_valid": False,
            "repair_used": False,
            "ranking": [],
            "rejected": ["missing_champions_or_evidence"],
        }

    scope_ids = [
        branch.id
        for branch in state.branches.values()
        if branch.level == 2
    ]
    return {
        "arm": JOINT_ARM,
        "spec": dict(JOINT_SPEC),
        "f2_facts": [dict(row) for row in f2_facts],
        "dynamic_f2_facts": [dict(row) for row in dynamic_f2],
        "between_selection": between_selection,
        "local_evidence_budget": local_n,
        "between_evidence_budget": between_n,
        "dynamic_assets": {
            "champions": dynamic_assets["champions"],
            "all_valid": dynamic_assets["all_valid"],
            "local_outputs": dynamic_assets.get("local_outputs") or {},
        },
        "arbiter": arbiter,
        "final_ranking": list(arbiter.get("ranking") or ()),
        "scope_ids": scope_ids,
        "champion_ids": [str(row["id"]) for row in champions],
    }


def _rebuild_champions_with_local_budget(
    *,
    cache,
    selector_prompt: str,
    annotator_prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    l1_rows: Sequence[Mapping[str, Any]],
    tree_state: DiagnosticState,
    true_f2: Sequence[Mapping[str, Any]],
    local_n: int,
    scope_mode: str = "per_family",
) -> dict[str, Any]:
    """Same as joint._build_champions dynamic mode but with configurable local_n.

    scope_mode:
      per_family — default: one annotator call per L1 family
      global     — single annotator call over all L2 leaves (flat recomputation)
    """
    parent_ids = [str(row["id"]) for row in l1_rows]
    parent_scores = {
        str(row["id"]): float(row["posterior"]) for row in l1_rows
    }
    champions = []
    local_outputs = {}
    selections = {}
    mode = str(scope_mode or "per_family").strip().lower()
    if mode == "global":
        # Flat recomputation: one scope covering every L2 leaf.
        branches = competition.rescale_l2_scope(
            tree_state, l1_rows, parent_ids, use_parent_mass=False,
        )
        candidate_rows = competition._candidate_rows(branches, tree_state)
        selection = dynamic.dynamic_l2_evidence_order(
            cache=cache,
            module="L2JointDynamicLocalEvidenceSelector",
            prompt=selector_prompt,
            case_text=case_text,
            findings=findings,
            candidates=joint._selector_candidates(candidate_rows),
            stop_after=local_n,
        )
        selected_facts = joint._facts_for_ids(
            findings, selection["selected_fact_ids"][:local_n],
        )
        # Attribute the global output to each parent so writeback still scales
        # by parent mass (leaves keep their real parent ids).
        if selected_facts:
            output = competition._annotate_scope(
                cache=cache,
                module="L2JointLocalAnnotator_dynamic_global",
                prompt=annotator_prompt,
                case_text=case_text,
                findings=findings,
                selected_facts=selected_facts,
                branches=branches,
                tree_state=tree_state,
            )
        else:
            branch_objs = (
                list(branches.values()) if isinstance(branches, Mapping) else list(branches)
            )
            output = {
                "schema_valid": True,
                "posteriors": [
                    {
                        "id": b.id,
                        "label": b.label,
                        "posterior": float(b.posterior or 0.0),
                        "explanatory_coverage": float(
                            getattr(b, "explanatory_coverage", 0.0) or 0.0
                        ),
                    }
                    for b in sorted(
                        branch_objs,
                        key=lambda br: (-float(br.posterior or 0.0), str(br.id)),
                    )
                ],
            }
        for parent_id in parent_ids:
            # Slice posteriors belonging to this parent.
            kids = {
                str(b.id)
                for b in tree_state.branches.values()
                if int(getattr(b, "level", 0) or 0) == 2
                and str(getattr(b, "parent", "") or "") == parent_id
            }
            sliced = {
                **output,
                "posteriors": [
                    p
                    for p in (output.get("posteriors") or [])
                    if str(p.get("id") or "") in kids
                ],
            }
            local_outputs[parent_id] = sliced
            selections[parent_id] = selection
            # Champion = top posterior in family
            posts = list(sliced.get("posteriors") or [])
            posts.sort(
                key=lambda p: (-float(p.get("posterior") or 0.0), str(p.get("id") or ""))
            )
            if posts:
                top = posts[0]
                champions.append(
                    {
                        "id": top["id"],
                        "label": top.get("label"),
                        "parent_id": parent_id,
                        "local_score": float(top.get("posterior") or 0.0),
                        "parent_posterior": float(parent_scores.get(parent_id) or 0.0),
                    }
                )
        return {
            "champions": champions,
            "all_valid": True,
            "local_outputs": local_outputs,
            "selections": selections,
            "scope_mode": "global",
        }

    for parent_id in parent_ids:
        branches = competition.rescale_l2_scope(
            tree_state, l1_rows, [parent_id], use_parent_mass=False,
        )
        candidate_rows = competition._candidate_rows(branches, tree_state)
        selection = dynamic.dynamic_l2_evidence_order(
            cache=cache,
            module="L2JointDynamicLocalEvidenceSelector",
            prompt=selector_prompt,
            case_text=case_text,
            findings=findings,
            candidates=joint._selector_candidates(candidate_rows),
            stop_after=local_n,
        )
        selected_facts = joint._facts_for_ids(
            findings, selection["selected_fact_ids"][:local_n],
        )
        selections[parent_id] = selection
        if selected_facts:
            output = competition._annotate_scope(
                cache=cache,
                module="L2JointLocalAnnotator_dynamic",
                prompt=annotator_prompt,
                case_text=case_text,
                findings=findings,
                selected_facts=selected_facts,
                branches=branches,
                tree_state=tree_state,
            )
        else:
            # rescale_l2_scope returns Mapping[id -> branch]
            branch_objs = list(branches.values()) if isinstance(branches, Mapping) else list(branches)
            output = {
                "schema_valid": True,
                "posteriors": [
                    {
                        "id": b.id,
                        "label": b.label,
                        "posterior": float(b.posterior or 0.0),
                        "explanatory_coverage": float(
                            getattr(b, "explanatory_coverage", 0.0) or 0.0
                        ),
                    }
                    for b in sorted(
                        branch_objs,
                        key=lambda br: (-float(br.posterior or 0.0), str(br.id)),
                    )
                ],
            }
        local_outputs[parent_id] = output
        if output.get("schema_valid") and output.get("posteriors"):
            parent = tree_state.branches[parent_id]
            # Prefer Dual-Inf-style coverage, then local posterior.
            posts = list(output["posteriors"])
            posts.sort(
                key=lambda p: (
                    -float(p.get("explanatory_coverage") or 0.0),
                    -float(p.get("posterior") or 0.0),
                    str(p.get("id") or ""),
                )
            )
            winner = dict(posts[0])
            champions.append({
                "id": winner["id"],
                "label": winner["label"],
                "parent_id": parent_id,
                "parent_label": parent.label,
                "local_rank": 1,
                "local_score": float(winner.get("posterior") or 0.0),
                "explanatory_coverage": float(
                    winner.get("explanatory_coverage") or 0.0
                ),
                "parent_posterior": parent_scores[parent_id],
                "local_evidence_ids": [str(r["id"]) for r in selected_facts],
            })
    return {
        "mode": "dynamic",
        "champions": champions,
        "local_outputs": local_outputs,
        "selections": selections,
        "champions_per_parent": 1,
        "all_valid": bool(champions),
    }


def apply_live_posteriors_and_cap(
    state: DiagnosticState,
    *,
    l1_rows: Sequence[Mapping[str, Any]],
    local_outputs: Mapping[str, Any],
    l2_candidate_max: int = 6,
    writeback_mode: str = "normal",
    shuffle_seed: int | None = None,
) -> dict[str, Any]:
    """Write local-annotator posteriors onto L2 leaves; cap children per L1.

    writeback_mode:
      normal           — write computed posteriors, then cap (default / deployed)
      placebo_refresh  — run cap/children reorder using NEW scores, then restore
                         PRE posteriors onto surviving leaves (serialization
                         refresh without score update)
      shuffled         — after writing NEW scores, permute them across touched
                         leaves (preserve multiset) before cap
    """
    mode = str(writeback_mode or "normal").strip().lower()
    # Snapshot PRE scores for placebo / fidelity.
    pre_scores: dict[str, float] = {}
    for bid, branch in state.branches.items():
        if int(getattr(branch, "level", 0) or 0) == 2:
            pre_scores[str(bid)] = float(getattr(branch, "posterior", 0.0) or 0.0)

    parent_mass = {
        str(r["id"]): float(r.get("posterior") or 0.0) for r in l1_rows
    }
    n_updated = 0
    touched: list[Any] = []
    for parent_id, output in (local_outputs or {}).items():
        posts = list((output or {}).get("posteriors") or ())
        if not posts:
            continue
        mass = float(parent_mass.get(str(parent_id)) or 0.0)
        # Normalize local posts then scale by parent mass.
        total = sum(max(float(p.get("posterior") or 0.0), 0.0) for p in posts) or 1.0
        cov_map = (output or {}).get("explanatory_coverage") or {}
        for p in posts:
            bid = str(p.get("id") or "")
            branch = state.branches.get(bid)
            if branch is None:
                continue
            local = max(float(p.get("posterior") or 0.0), 0.0) / total
            branch.posterior = mass * local if mass > 0 else local
            cov = float(
                p.get("explanatory_coverage")
                if p.get("explanatory_coverage") is not None
                else cov_map.get(bid, 0.0)
                or 0.0
            )
            if hasattr(branch, "explanatory_coverage"):
                branch.explanatory_coverage = cov
            n_updated += 1
            touched.append(branch)

    if mode == "shuffled" and touched:
        import random

        rng = random.Random(shuffle_seed if shuffle_seed is not None else 20260731)
        scores = [float(getattr(b, "posterior", 0.0) or 0.0) for b in touched]
        rng.shuffle(scores)
        for b, s in zip(touched, scores):
            b.posterior = s

    # Cap children per live L1 family by posterior.
    n_dropped = 0
    cap = max(1, int(l2_candidate_max))
    for parent_id, parent in list(state.branches.items()):
        if getattr(parent, "level", None) != 1 and str(getattr(parent, "parent", "") or ""):
            continue
        if str(getattr(parent, "parent", "") or "").strip():
            continue
        children = list(getattr(parent, "children", None) or [])
        child_rows = []
        for cid in children:
            b = state.branches.get(cid)
            if b is not None:
                child_rows.append(b)
        child_rows.sort(
            key=lambda b: (-float(getattr(b, "posterior", 0.0) or 0.0), str(b.id))
        )
        keep = {str(b.id) for b in child_rows[:cap]}
        parent.children = [str(b.id) for b in child_rows if str(b.id) in keep]
        for b in child_rows:
            if str(b.id) not in keep:
                b.posterior = 0.0
                n_dropped += 1

    if mode == "placebo_refresh":
        # Cap/reorder already applied using NEW scores; restore PRE posteriors
        # onto leaves that still exist (capped-out stay at 0).
        for bid, score in pre_scores.items():
            branch = state.branches.get(bid)
            if branch is None:
                continue
            if float(getattr(branch, "posterior", 0.0) or 0.0) == 0.0 and bid not in {
                str(x) for p in state.branches.values() for x in (getattr(p, "children", None) or [])
            }:
                # Leave capped-out at 0.
                continue
            parent_id = str(getattr(branch, "parent", "") or "")
            parent = state.branches.get(parent_id)
            kids = list(getattr(parent, "children", None) or []) if parent is not None else []
            if kids and bid not in {str(x) for x in kids}:
                continue  # capped out
            branch.posterior = score

    return {
        "n_posterior_updated": n_updated,
        "n_capped_dropped": n_dropped,
        "writeback_mode": mode,
        "n_pre_scores": len(pre_scores),
    }


def _label_match(
    left: str,
    right: str,
    resolver: DiseaseNameResolver,
) -> bool:
    a = _normalize_label(left)
    b = _normalize_label(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    try:
        return resolver.canonicalize_entity(left) == resolver.canonicalize_entity(right)
    except Exception:
        return False


def build_gold_l2(
    *,
    gold_label: str,
    state: DiagnosticState,
    resolver: DiseaseNameResolver,
) -> dict[str, Any]:
    acceptable = []
    for branch in state.branches.values():
        if branch.level != 2:
            continue
        if _label_match(branch.label, gold_label, resolver):
            acceptable.append({
                "id": branch.id,
                "label": branch.label,
            })
    if acceptable:
        return {"status": "present", "acceptable_l2": acceptable}
    return {"status": "absent", "acceptable_l2": []}


def score_l2(
    *,
    ranking: Sequence[str],
    gold: Mapping[str, Any],
    scope_ids: Sequence[str],
    schema_valid: bool,
    champion_ids: Sequence[str],
) -> dict[str, Any]:
    """Step 14: offline L2 Top-1 / Top-2 / MRR."""
    return competition.score_ranking(
        ranking,
        gold,
        scope_ids=scope_ids,
        schema_valid=schema_valid,
        local_champion_ids=champion_ids,
    )


def serialize_state(state: DiagnosticState) -> dict[str, Any]:
    return l2_ab._serialise_state(state)
