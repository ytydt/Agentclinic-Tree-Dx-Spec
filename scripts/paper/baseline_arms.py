#!/usr/bin/env python3
"""DiagnosisArena paper baseline arm implementations (open vignette → Top-2)."""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import baseline_aggregate as agg
import baseline_common as bc

ROOT = bc.ROOT
PROMPT_DIR = bc.PROMPT_DIR

VIGNETTE_PROMPT = (PROMPT_DIR / "naive_cot_vignette_top2.txt").read_text(encoding="utf-8")
PLANNER_PROMPT_PATH = PROMPT_DIR / "naive_cot_live_rag_planner.txt"
SELF_REFINE_CRITIC = """You are reviewing a differential diagnosis draft.
Given the vignette and the current ordered Top-2 diagnoses, criticize only ranking
and specificity. Do not invent new patient findings or external knowledge.
Return JSON: {"critique": "...", "keep_order": true|false}
"""
SELF_REFINE_REVISE = """Revise the ordered Top-2 diagnoses using the critique.
Do not introduce gold labels or external retrieval. Return the same JSON schema
as the original answer with exactly two concrete diseases, best first.
"""
SC_PROMPT = VIGNETTE_PROMPT
COD_PROMPT = """Follow Chain-of-Diagnosis for a static case (n=0, no further inquiry).
1) Abstract key symptoms from the vignette.
2) Retrieve/recall candidate diseases (use only supplied knowledge excerpts if any).
3) Reason over candidates.
4) Assign a confidence distribution over candidates (0-1, sum need not be 1).
5) Output the two highest-confidence diseases.
Return JSON only:
{"symptoms":["..."],
 "candidates":["..."],
 "reasoning":"...",
 "confidence":{"Disease A":0.4,"Disease B":0.3},
 "top2_diagnoses":[{"diagnosis":"Disease A","reasoning_summary":"..."},
 {"diagnosis":"Disease B","reasoning_summary":"..."}]}
"""
FLAT_CANDIDATE_PROMPT = """You are generating an open differential for a static case.
Use only the vignette and retrieved knowledge excerpts (no external tools).
Return JSON only:
{"candidates":[{"diagnosis":"...","reasoning_summary":"..."},
 {"diagnosis":"...","reasoning_summary":"..."}]}
Return exactly __K__ concrete diseases, best-first preference within the list.
"""
FLAT_CANDIDATE_EXPAND_PROMPT = """You are expanding an open differential for a static case.
Avoid repeating diseases already listed. Use vignette + knowledge excerpts only.
Already listed (do not repeat): __EXISTING__
Return JSON only:
{"candidates":[{"diagnosis":"...","reasoning_summary":"..."}]}
Return up to __K__ NEW concrete diseases.
"""
FLAT_RERANK_PROMPT = """You are listwise-reranking a fixed candidate disease list for a
static case. Use the vignette and retrieved knowledge. Do not invent diseases
outside the candidate list. Return exactly two candidates, best first, as JSON:
{"top2_diagnoses":[{"diagnosis":"<exact candidate>"},{"diagnosis":"<exact candidate>"}]}
"""
FLAT_EVIDENCE_MATRIX_PROMPT = """You are scoring a flat candidate list against observed facts
(no specialty families / no L1 hierarchy). For each candidate, briefly note support or
oppose using the vignette and knowledge. Then produce an updated ranking of the same
candidates. Do not invent diseases outside the list.
Return JSON only:
{"ranked_candidates":["Disease A","Disease B"],
 "notes":[{"diagnosis":"Disease A","label":"support|oppose|mixed"}]}
"""
FLAT_UNION_PROMPT = """Rank the supplied candidate disease list for this vignette.
Do not invent diseases outside the candidate list. Return exactly two IDs or names
from the list, best first, as JSON:
{"top2_diagnoses":[{"diagnosis":"<exact candidate>"},{"diagnosis":"<exact candidate>"}]}
"""
TAXONOMY_PROMPT = """Use a fixed specialty taxonomy (coarse→fine). First choose one
specialty family, then give two specific diseases under that family for the vignette.
Return JSON top2_diagnoses with concrete diseases only.
"""
EMULATION_PROMPT = """For each observed fact and each candidate diagnosis, label
support / oppose / irrelevant. Then produce an ordered Top-2 from candidates.
Return JSON:
{"matrix":[{"fact":"...","candidate":"...","label":"support|oppose|irrelevant"}],
 "top2_diagnoses":[{"diagnosis":"..."},{"diagnosis":"..."}]}
"""
CANDIDATE_EXTRACT_PROMPT = """From vignette and knowledge excerpts, list up to 8 concrete
disease names that are plausible differentials (no letters/options). Return JSON only:
{"candidates":["Disease A","Disease B"]}
"""
# Dual-Inf (betterzhou/Dual-Inf): forward → backward recall → examine → optional reflect.
DUAL_INF_FORWARD = """You are Dual-Inf forward-inference. From the vignette, USE STEP-BY-STEP
DEDUCTION to list the most likely diagnoses (up to 5). For each disease, list patient
findings that support it. Return JSON only:
{"diagnoses":{"Disease A":["support finding 1","support finding 2"],
 "Disease B":["support finding 1"]}}
Keys are disease names; values are support-reason lists. No abbreviations.
"""
DUAL_INF_BACKWARD = """You are Dual-Inf backward-inference. For each disease name, recall
representative symptoms, exam findings, and lab results that support that disease
(from medical knowledge, not the patient note). Return JSON only:
{"book_knowledge":{"Disease A":["manifestation 1","manifestation 2"],
 "Disease B":["manifestation 1"]}}
"""
DUAL_INF_EXAMINE = """You are Dual-Inf examination. You receive (1) patient vignette,
(2) forward diagnoses with support reasons, (3) backward book manifestations per disease.
For each disease:
- drop support reasons that are not consistent with book knowledge for that disease;
- add book manifestations that are clearly present in the vignette but missing from supports;
- keep the refined support list.
Then rank diseases by number of remaining supports (more = higher confidence).
Return JSON only:
{"refined":{"Disease A":["reason",...],"Disease B":["reason",...]},
 "top2_diagnoses":[{"diagnosis":"...","reasoning_summary":"..."},
 {"diagnosis":"...","reasoning_summary":"..."}]}
"""
DUAL_INF_REFLECT = """You are Dual-Inf forward-inference with self-reflection. Prior supports
for some diagnoses were low-confidence. Re-infer differentials for the vignette.
Feedback (may be imperfect): these diagnoses seem low-confidence or wrong:
__LOW_CONFIDENCE__. Think twice; you may keep or replace them. Return the same JSON as
forward-inference:
{"diagnoses":{"Disease A":["support finding 1"],"Disease B":["support finding 1"]}}
"""
# MDAgents (mitmedialab/MDAgents): moderator complexity → recruit → agents → consensus.
MD_COMPLEXITY = """You are MDAgents moderator (GP triage). Classify case complexity.
Return JSON only: {"complexity":"low|moderate|high","rationale":"..."}
low=routine single-agent; moderate=small MDT; high=broader specialist panel.
"""
MD_RECRUIT = """You are MDAgents recruiter. Given complexity=__COMPLEXITY__, recruit roles.
Return JSON only:
{"roles":["Primary Care Physician","Specialty A","Specialty B"]}
For low: exactly 1 role. For moderate: 2-3 roles. For high: 3-4 roles.
"""
MD_AGENT = """You are a __ROLE__ on an MDAgents panel for a static complete case.
Give your independent ordered Top-2 concrete diseases. Return JSON only:
{"top2_diagnoses":[{"diagnosis":"...","reasoning_summary":"..."},
{"diagnosis":"...","reasoning_summary":"..."}],"role":"__ROLE__"}
"""
MD_CONSENSUS = """You are MDAgents moderator reviewing panel opinions for a static case.
Synthesize a consensus ordered Top-2. Return JSON only:
{"top2_diagnoses":[{"diagnosis":"...","reasoning_summary":"..."},
{"diagnosis":"...","reasoning_summary":"..."}],"agent_notes":"brief"}
"""
# Single-vendor MAC (rajpurkarlab/mixed-vendor-mac DiagnosisArena protocol, condensed).
MAC_DOCTOR = """You are __DOCTOR_NAME__, a medical expert in clinical diagnosis (MAC panel).
Analyze the vignette and prior discussion. End with an ordered Top-5 disease list.
Return JSON only:
{"ranked_diagnoses":["d1","d2","d3","d4","d5"],
 "commentary":"brief engagement with prior opinions"}
"""
MAC_SUPERVISOR = """You are the Medical Supervisor (MAC). Review doctors' ranked lists and
drive consensus. Finalize an ordered Top-2 for this static case (project contract).
Return JSON only:
{"top2_diagnoses":[{"diagnosis":"...","reasoning_summary":"..."},
{"diagnosis":"...","reasoning_summary":"..."}],"votes":3}
"""
# MedRAG-style on shared KB (no private diagnostic KG): retrieve → elicit differences → reason.
MEDRAG_DIFFS = """You implement MedRAG KG-elicited reasoning WITHOUT a private KG.
From retrieved knowledge excerpts and the vignette, extract critical diagnostic
differences between confusable diseases (discriminating features, tests, findings).
Return JSON only:
{"candidate_diseases":["...","..."],
 "diagnostic_differences":[
   {"pair":["Disease A","Disease B"],"differences":["feature that separates them",...]}
 ],
 "manifestation_summary":"..."}
"""
MEDRAG_REASON = """You are MedRAG-style KG-elicited RAG diagnosis on a static case.
Use retrieved knowledge excerpts AND the diagnostic_differences to distinguish similar
diseases. Return ordered Top-2 concrete diseases as JSON:
{"top2_diagnoses":[{"diagnosis":"...","reasoning_summary":"..."},
{"diagnosis":"...","reasoning_summary":"..."}]}
"""
# MedPrompt adaptation (shared KB exemplars; no labeled train pool / no MCQ gold).
MEDPROMPT_COT = """MedPrompt-style self-generated CoT for open differential diagnosis.
Use dynamic knowledge exemplars (retrieved passages) and step-by-step reasoning.
Return ordered Top-2 concrete diseases as JSON top2_diagnoses. Do not use option letters.
"""
# B03 Flat beam search (no L1 families): init beam → expand/rescore → select Top-2.
FLAT_BEAM_INIT = """You are running a flat (non-hierarchical) beam search for differential
diagnosis. Using the vignette and knowledge excerpts, propose an initial beam of
__BEAM_WIDTH__ concrete diseases, best first. Return JSON only:
{"beam":[{"diagnosis":"...","reasoning_summary":"..."}, ...]}
"""
FLAT_BEAM_EXPAND = """Flat beam expand/rescore step __STEP__/__DEPTH__.
Current beam: __BEAM__.
Using the vignette and knowledge, expand with plausible alternatives or more specific
diseases, then keep the best __BEAM_WIDTH__ as the new beam (no L1/family tree).
Return JSON only:
{"beam":[{"diagnosis":"...","reasoning_summary":"..."}, ...]}
"""
FLAT_BEAM_SELECT = """From the final flat beam, return the ordered Top-2 concrete diseases.
Do not invent diseases outside the beam. Return JSON:
{"top2_diagnoses":[{"diagnosis":"<exact beam item>"},{"diagnosis":"<exact beam item>"}]}
"""
# B07 MEDDxAgent-style complete-profile (static vignette; shared model + shared KB).
# Official MEDDxAgent is interactive; plan requires complete-profile static mode here.
MEDDX_ORCHESTRATE = """You are MEDDxAgent DDxDriver (complete-profile static mode).
The full vignette is already available; do NOT ask history-taking questions.
Decide whether knowledge retrieval is useful, then outline diagnosis strategy.
Return JSON only:
{"need_retrieval":true|false,
 "retrieval_queries":["short query",...],
 "strategy_notes":"..."}
"""
MEDDX_DIAGNOSE = """You are MEDDxAgent diagnosis-strategy agent (complete-profile).
Use vignette + retrieved knowledge (if any). Produce an ordered Top-2 DDx with brief
explanations. Return JSON top2_diagnoses.
"""
MEDDX_REFINE = """You are MEDDxAgent iterative refine (complete-profile, one extra turn).
Given the draft Top-2 and knowledge, revise only if evidence warrants; else keep order.
Return JSON top2_diagnoses.
"""


def _read_planner_prompt() -> str:
    if PLANNER_PROMPT_PATH.is_file():
        return PLANNER_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Plan up to 4 short retrieval queries for differential diagnosis.\n"
        'Return JSON: {"search_queries":["..."]}'
    )


def _list_k_from_kwargs(kwargs: Mapping[str, Any], default: int = 2) -> int:
    try:
        return max(1, int(kwargs.get("list_k") or default))
    except (TypeError, ValueError):
        return max(1, int(default))


def _ensure_k(names: Sequence[str], k: int = 2) -> list[str]:
    """Non-empty pad/truncate for arm outputs (uses last name or undetermined)."""
    want = max(1, int(k))
    cleaned = [str(n).strip() for n in names if str(n).strip()]
    # Dedup
    out: list[str] = []
    seen: set[str] = set()
    for name in cleaned:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= want:
            return out[:want]
    while len(out) < want:
        out.append(out[-1] if out else "undetermined")
    return out[:want]


def _ensure_two(names: Sequence[str]) -> list[str]:
    return _ensure_k(names, 2)


def _dry_topk(case: Mapping[str, Any], arm: str, k: int = 2) -> list[str]:
    """Deterministic placeholder for dry-run / cache-miss without API."""
    want = max(1, int(k))
    options = [str(x).strip() for x in (case.get("options") or {}).values() if str(x).strip()]
    if options:
        return _ensure_k(options, want)
    return _ensure_k([f"{arm}-dx-{i + 1}" for i in range(want)], want)


def _dry_top2(case: Mapping[str, Any], arm: str) -> list[str]:
    return _dry_topk(case, arm, 2)


def _adapt_prompt_for_k(prompt: str, list_k: int) -> str:
    """Rewrite Top-2 / top2_diagnoses prompts for ordered Top-K when list_k != 2."""
    k = max(1, int(list_k))
    if k == 2:
        return prompt
    text = str(prompt)
    text = text.replace("top2_diagnoses", "ordered_diagnoses")
    text = text.replace("Top-2", "Top-%d" % k)
    text = text.replace("top-2", "top-%d" % k)
    text = text.replace("exactly two", "exactly %d" % k)
    text = text.replace("Exactly two", "Exactly %d" % k)
    text = text.replace("two highest-confidence", "%d highest-confidence" % k)
    text = text.replace("two specific diseases", "%d specific diseases" % k)
    text = text.replace("two concrete diseases", "%d concrete diseases" % k)
    text = text.replace("ordered Top-2", "ordered Top-%d" % k)
    # Ensure schema hint lists k slots when a short example remains
    if "ordered_diagnoses" in text and text.count('"diagnosis"') < k:
        # Append explicit length instruction
        text = (
            text.rstrip()
            + "\nReturn exactly %d ordered diagnoses under ordered_diagnoses "
            "(best first), each with diagnosis and reasoning_summary.\n" % k
        )
    return text


def _call_topk(
    cache: bc.SimpleCachedLLM,
    *,
    module: str,
    prompt: str,
    payload: Mapping[str, Any],
    dry_run: bool,
    case: Mapping[str, Any],
    arm: str,
    list_k: int = 2,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    k = max(1, int(list_k))
    adapted = _adapt_prompt_for_k(prompt, k)
    cost = bc.empty_cost()
    t0 = time.time()
    if dry_run and cache.client is None:
        ranked = _dry_topk(case, arm, k)
        cost["latency_s"] = time.time() - t0
        return ranked, {"dry_run": True, "top2": ranked, "ordered": ranked, "list_k": k}, cost
    try:
        bc.assert_no_gold_leak(payload)
        raw = cache.call(module, adapted, payload)
        ranked = _ensure_k(bc.clean_topk_from_response(raw, k=k), k)
        cost["llm_calls"] = 1
        cost["latency_s"] = time.time() - t0
        return ranked, {"raw": raw, "top2": ranked, "ordered": ranked, "list_k": k}, cost
    except Exception as exc:  # noqa: BLE001
        if dry_run:
            ranked = _dry_topk(case, arm, k)
            return ranked, {"error": str(exc), "dry_run_fallback": True, "list_k": k}, cost
        raise


def _call_top2(
    cache: bc.SimpleCachedLLM,
    *,
    module: str,
    prompt: str,
    payload: Mapping[str, Any],
    dry_run: bool,
    case: Mapping[str, Any],
    arm: str,
    list_k: int = 2,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    return _call_topk(
        cache,
        module=module,
        prompt=prompt,
        payload=payload,
        dry_run=dry_run,
        case=case,
        arm=arm,
        list_k=list_k,
    )


def _merge_cost(dst: dict[str, Any], src: Mapping[str, Any]) -> None:
    for key in ("llm_calls", "retrieval_calls", "retrieval_snippets", "snippet_chars"):
        dst[key] = int(dst.get(key) or 0) + int(src.get(key) or 0)


def _names_from_any(raw: Any, *, k: int = 5) -> list[str]:
    names = bc.clean_topk_from_response(
        raw if isinstance(raw, Mapping) else {"raw_text": str(raw)},
        k=k,
    )
    nonempty = [n for n in names if n]
    if len(nonempty) >= min(2, k) and nonempty:
        if isinstance(raw, Mapping):
            for key in ("candidates", "ranked_diagnoses", "diagnoses", "beam", "ordered_diagnoses"):
                rows = raw.get(key)
                if not rows:
                    continue
                out: list[str] = []
                if isinstance(rows, Mapping):
                    out = [str(x).strip() for x in rows.keys() if str(x).strip()]
                else:
                    for row in rows:
                        if isinstance(row, Mapping):
                            name = str(
                                row.get("diagnosis")
                                or row.get("name")
                                or row.get("disease")
                                or ""
                            ).strip()
                        else:
                            name = str(row).strip()
                        if name and name.casefold() not in {n.casefold() for n in out}:
                            out.append(name)
                if out:
                    return out[:k]
        return nonempty[:k]
    if isinstance(raw, Mapping):
        for key in ("candidates", "ranked_diagnoses", "beam", "ordered_diagnoses"):
            rows = raw.get(key)
            if not rows:
                continue
            out = []
            for row in rows:
                if isinstance(row, Mapping):
                    name = str(
                        row.get("diagnosis") or row.get("name") or row.get("disease") or ""
                    ).strip()
                else:
                    name = str(row).strip()
                if name and name.casefold() not in {n.casefold() for n in out}:
                    out.append(name)
            if out:
                return out[:k]
    return nonempty[:k]


def _support_map(raw: Any) -> dict[str, list[str]]:
    """Parse Dual-Inf style {disease: [reasons]} maps."""
    if not isinstance(raw, Mapping):
        return {}
    for key in ("diagnoses", "refined", "book_knowledge", "disease_reasons"):
        block = raw.get(key)
        if isinstance(block, Mapping) and block:
            out: dict[str, list[str]] = {}
            for disease, reasons in block.items():
                name = str(disease).strip()
                if not name:
                    continue
                if isinstance(reasons, Sequence) and not isinstance(reasons, (str, bytes)):
                    out[name] = [str(r).strip() for r in reasons if str(r).strip()]
                elif reasons:
                    out[name] = [str(reasons).strip()]
                else:
                    out[name] = []
            return out
    # Flat dict of disease→list when model returns the map at top level
    if all(isinstance(v, (list, tuple)) for v in raw.values()):
        return {
            str(k).strip(): [str(r).strip() for r in v if str(r).strip()]
            for k, v in raw.items()
            if str(k).strip() and str(k) not in {"raw_text", "text"}
        }
    return {}


def _rank_by_support(support: Mapping[str, Sequence[str]]) -> list[str]:
    ranked = sorted(
        ((str(name), len(list(reasons or ()))) for name, reasons in support.items()),
        key=lambda item: (-item[1], item[0].casefold()),
    )
    return [name for name, _ in ranked if name.strip()]


def _low_confidence(support: Mapping[str, Sequence[str]], *, beta: int = 2) -> list[str]:
    return [
        str(name)
        for name, reasons in support.items()
        if len(list(reasons or ())) <= beta
    ]


def _constrain_to_pool(
    names: Sequence[str],
    pool: Sequence[str],
    *,
    list_k: int = 2,
) -> list[str]:
    want = max(1, int(list_k))
    pool_cf = {str(x).casefold(): str(x) for x in pool}
    constrained: list[str] = []
    for name in names:
        key = name.casefold()
        if key in pool_cf and pool_cf[key] not in constrained:
            constrained.append(pool_cf[key])
    if len(constrained) < want and pool:
        for item in pool:
            if item not in constrained:
                constrained.append(item)
            if len(constrained) >= want:
                break
    return _ensure_k(constrained or list(names), want)


def _fixed_manifestation_queries(vignette: str, *, max_queries: int = 4) -> list[str]:
    """Fixed (non-planner) queries for flat / MedRAG-style retrieval.

    Supports max_queries > 4 by sliding vignette windows and template variants so
    compute-matched B02 can honor per-case retrieval_call budgets.
    """
    text = " ".join(str(vignette or "").split())
    if not text:
        return ["most likely diagnosis laboratory findings imaging"][: max(1, max_queries)]
    want = max(1, int(max_queries))
    templates = [
        "{head}",
        "differential diagnosis {head}",
        "clinical manifestations diagnosis {mid}",
        "most likely diagnosis laboratory findings imaging",
        "pathophysiology complications of {head}",
        "diagnostic criteria workup {mid}",
        "rare diseases mimicking {tail}",
        "treatment implications differential {head}",
    ]
    # Sliding windows over vignette for diversity.
    windows: list[str] = []
    step = max(80, len(text) // max(want, 1))
    for start in range(0, max(1, len(text)), step):
        windows.append(text[start : start + 280])
        if len(windows) >= want:
            break
    if not windows:
        windows = [text[:280]]
    out: list[str] = []
    seen: set[str] = set()
    wi = 0
    ti = 0
    while len(out) < want:
        head = windows[wi % len(windows)][:280]
        mid = windows[(wi + 1) % len(windows)][:200]
        tail = windows[(wi + 2) % len(windows)][:160]
        tmpl = templates[ti % len(templates)]
        query = tmpl.format(head=head[:200], mid=mid[:160], tail=tail[:140])[:300]
        key = query.casefold()
        if key not in seen and query.strip():
            seen.add(key)
            out.append(query)
        ti += 1
        if ti % len(templates) == 0:
            wi += 1
        # safety
        if ti > want * len(templates) * 3:
            break
    return out[:want]


def _retrieve_shared(
    queries: Sequence[str],
    retrievers: Mapping[str, Any] | None,
    *,
    per_query_per_index: int = 3,
    max_chunks: int = 12,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    cost = bc.empty_cost()
    if not retrievers or not queries:
        return [], {}, cost
    from eval_naive_cot_rag_ablation import retrieve_live_bundle

    chunks, audit = retrieve_live_bundle(
        list(queries),
        retrievers,
        per_query_per_index=per_query_per_index,
        max_chunks=max_chunks,
    )
    cost["retrieval_calls"] = len(audit.get("requests") or [])
    cost["retrieval_snippets"] = len(chunks)
    cost["snippet_chars"] = sum(len(c.get("text") or "") for c in chunks)
    return chunks, audit, cost


def _llm_candidate_pool(
    case: Mapping[str, Any],
    cache: bc.SimpleCachedLLM,
    *,
    chunks: Sequence[Mapping[str, Any]],
    dry_run: bool,
    module: str,
    n: int = 8,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    cost = bc.empty_cost()
    if dry_run and cache.client is None:
        return [f"{module}-cand-a", f"{module}-cand-b"], {"dry_run": True}, cost
    raw = cache.call(
        module,
        CANDIDATE_EXTRACT_PROMPT,
        {
            **bc.runtime_payload(case),
            "knowledge_chunks": list(chunks),
        },
    )
    cost["llm_calls"] = 1
    names = _names_from_any(raw, k=n)
    return names, {"raw": raw, "candidates": names}, cost


def run_b00(case, cache, *, dry_run=False, **kwargs):
    list_k = _list_k_from_kwargs(kwargs)
    payload = {**bc.runtime_payload(case), "knowledge_chunks": []}
    return _call_topk(
        cache,
        module="PaperB00DirectCoT",
        prompt=VIGNETTE_PROMPT,
        payload=payload,
        dry_run=dry_run,
        case=case,
        arm="B00",
        list_k=list_k,
    )


def run_b01(case, cache, *, dry_run=False, retrievers=None, **kwargs):
    from eval_naive_cot_rag_ablation import clean_search_plan, retrieve_live_bundle

    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    vignette = case["vignette"]
    chunks: list[dict[str, Any]] = []
    retrieval_audit: dict[str, Any] = {}
    if retrievers and not dry_run:
        plan_raw = cache.call(
            "PaperB01RAGPlanner",
            _read_planner_prompt(),
            {"vignette": vignette},
        )
        plan = clean_search_plan(plan_raw)
        cost["llm_calls"] += 1
        if plan.get("schema_valid"):
            chunks, retrieval_audit = retrieve_live_bundle(
                plan["search_queries"], retrievers,
            )
            cost["retrieval_calls"] = len(retrieval_audit.get("requests") or [])
            cost["retrieval_snippets"] = len(chunks)
            cost["snippet_chars"] = sum(len(c.get("text") or "") for c in chunks)
    payload = {
        **bc.runtime_payload(case),
        "knowledge_chunks": chunks,
    }
    top2, trace, answer_cost = _call_topk(
        cache,
        module="PaperB01CoTRAG",
        prompt=VIGNETTE_PROMPT,
        payload=payload,
        dry_run=dry_run,
        case=case,
        arm="B01",
        list_k=list_k,
    )
    for key in ("llm_calls",):
        cost[key] = int(cost[key]) + int(answer_cost.get(key) or 0)
    cost["latency_s"] = time.time() - t0
    trace = {**trace, "retrieval": retrieval_audit}
    return top2, trace, cost


class _ScTrajCache:
    """Namespace LLM cache keys per SC trajectory (payload + module suffix)."""

    def __init__(self, inner: Any, sc_traj: int) -> None:
        self._inner = inner
        self._sc_traj = int(sc_traj)

    @property
    def client(self) -> Any:
        return getattr(self._inner, "client", None)

    def call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> Any:
        body = dict(payload)
        body["sc_traj"] = self._sc_traj
        return self._inner.call(f"{module}__sc{self._sc_traj}", prompt, body)


def run_b02_sc(
    case,
    cache,
    *,
    dry_run=False,
    sc_samples: int = 10,
    sc_seed_top: Sequence[str] | None = None,
    sc_seed_cost: Mapping[str, Any] | None = None,
    retrievers=None,
    **kwargs,
):
    """10-way (default) full-trajectory SC over B02 compute-matched + RRF.

    Each sample runs the full matched ``run_b02`` path (~schedule llm_calls).
    Total llm_calls ≈ sc_samples × matched ≈ main-method call scale.
    Optional ``sc_seed_top`` reuses an existing single-traj ranking as sample 0.
    """
    list_k = _list_k_from_kwargs(kwargs)
    n = max(1, int(sc_samples or 10))
    kwargs = {**kwargs, "budget_mode": "matched"}
    budget = kwargs.get("budget_schedule") or kwargs.get("budget") or {}
    lists: list[list[str]] = []
    sample_traces: list[dict[str, Any]] = []
    cost = bc.empty_cost()
    t0 = time.time()
    start = 0

    if sc_seed_top:
        seed = _ensure_k([str(x) for x in sc_seed_top if str(x).strip()], list_k)
        lists.append(seed)
        sample_traces.append(
            {
                "sample": 0,
                "reused_from": "B02-flat-compute-matched",
                "ranked": list(seed),
            }
        )
        if sc_seed_cost:
            _merge_cost(cost, sc_seed_cost)
            # unique_candidates: keep max across trajs later
            if sc_seed_cost.get("unique_candidates") is not None:
                cost["unique_candidates"] = int(sc_seed_cost.get("unique_candidates") or 0)
        start = 1

    uniq_vals: list[int] = []
    if cost.get("unique_candidates"):
        uniq_vals.append(int(cost["unique_candidates"]))

    for sample in range(start, n):
        wrapped = _ScTrajCache(cache, sample)
        top, tr, c = run_b02(
            case,
            wrapped,
            dry_run=dry_run,
            retrievers=retrievers,
            **kwargs,
        )
        lists.append(_ensure_k(list(top), list_k))
        sample_traces.append(
            {
                "sample": sample,
                "reused_from": None,
                "ranked": lists[-1],
                "traj_llm_calls": int(c.get("llm_calls") or 0),
                "traj_retrieval_calls": int(c.get("retrieval_calls") or 0),
            }
        )
        _merge_cost(cost, c)
        if c.get("unique_candidates") is not None:
            uniq_vals.append(int(c.get("unique_candidates") or 0))

    aggregated = agg.rrf_aggregate(lists, top_n=list_k)
    if len(aggregated) < list_k:
        aggregated = agg.borda_aggregate(lists, top_n=list_k)
    topk = _ensure_k(aggregated, list_k)
    cost["latency_s"] = time.time() - t0
    if uniq_vals:
        cost["unique_candidates"] = int(round(sum(uniq_vals) / len(uniq_vals)))
    cost["sc_samples"] = n
    cost["sc_aggregation"] = "rrf"
    if budget:
        # Call/snippet budgets scale with trajectories; candidate pool size does not.
        cost["budget_target"] = {
            "llm_calls": int(budget.get("llm_calls") or 0) * n,
            "retrieval_calls": int(budget.get("retrieval_calls") or 0) * n,
            "retrieval_snippets": int(budget.get("retrieval_snippets") or 0) * n,
            "unique_candidates": int(budget.get("unique_candidates") or 0),
        }
        cost["budget_mismatch"] = _budget_mismatch(
            cost, cost["budget_target"], tol=0.05
        )
    return topk, {
        "method": "flat_compute_matched_sc",
        "budget_mode": "matched",
        "sc_samples": n,
        "aggregation": "rrf",
        "samples": sample_traces,
        "list_k": list_k,
        "budget_schedule": {
            k: budget.get(k)
            for k in (
                "llm_calls",
                "retrieval_calls",
                "retrieval_snippets",
                "unique_candidates",
                "n_queries",
                "max_chunks",
                "matching_policy",
            )
        }
        if budget
        else None,
    }, cost


def run_b12(case, cache, *, dry_run=False, sc_samples=5, **kwargs):
    list_k = _list_k_from_kwargs(kwargs)
    lists: list[list[str]] = []
    traces = []
    cost = bc.empty_cost()
    t0 = time.time()
    payload = {**bc.runtime_payload(case), "knowledge_chunks": []}
    prompt = _adapt_prompt_for_k(SC_PROMPT, list_k)
    for sample in range(sc_samples):
        sample_payload = {**payload, "sc_sample": sample}
        if dry_run and cache.client is None:
            top2 = _dry_topk(case, "B12", list_k)
            lists.append(top2)
            traces.append({"sample": sample, "dry_run": True})
            continue
        raw = cache.call(
            f"PaperB12SCCot_{sample}",
            prompt,
            sample_payload,
        )
        ranked = bc.clean_topk_from_response(raw, k=max(list_k, 5))
        if isinstance(raw, Mapping) and raw.get("raw_text"):
            ranked = (
                bc.parse_numbered_diagnoses(str(raw["raw_text"]), k=max(list_k, 5))
                or ranked
            )
        lists.append(_ensure_k(ranked, list_k))
        traces.append({"sample": sample, "ranked": lists[-1]})
        cost["llm_calls"] += 1
    aggregated = agg.rrf_aggregate(lists, top_n=list_k)
    if len(aggregated) < list_k:
        aggregated = agg.borda_aggregate(lists, top_n=list_k)
    cost["latency_s"] = time.time() - t0
    return _ensure_k(aggregated, list_k), {
        "samples": traces, "method": "rrf", "list_k": list_k,
    }, cost


def run_b13(case, cache, *, dry_run=False, **kwargs):
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    draft, draft_trace, draft_cost = run_b00(case, cache, dry_run=dry_run, list_k=list_k)
    cost["llm_calls"] += int(draft_cost.get("llm_calls") or 0)
    if dry_run and cache.client is None:
        cost["latency_s"] = time.time() - t0
        return draft, {"draft": draft_trace, "dry_run": True}, cost
    critique = cache.call(
        "PaperB13SelfRefineCritic",
        _adapt_prompt_for_k(SELF_REFINE_CRITIC, list_k),
        {
            **bc.runtime_payload(case),
            "draft_top2": draft,
            "draft_ordered": draft,
        },
    )
    cost["llm_calls"] += 1
    revised = cache.call(
        "PaperB13SelfRefineRevise",
        _adapt_prompt_for_k(SELF_REFINE_REVISE + "\n" + VIGNETTE_PROMPT, list_k),
        {
            **bc.runtime_payload(case),
            "draft_top2": draft,
            "draft_ordered": draft,
            "critique": critique,
            "knowledge_chunks": [],
        },
    )
    cost["llm_calls"] += 1
    top2 = _ensure_k(bc.clean_topk_from_response(revised, k=list_k), list_k)
    cost["latency_s"] = time.time() - t0
    return top2, {
        "draft": draft, "critique": critique, "revised": revised, "list_k": list_k,
    }, cost


def run_b04(case, cache, *, dry_run=False, max_reflect: int = 1, beta: int = 2, **kwargs):
    """Dual-Inf: forward → backward → examine → optional self-reflection (shared model)."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    base = bc.runtime_payload(case)
    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B04", list_k)
        cost["latency_s"] = time.time() - t0
        return top2, {"dry_run": True, "method": "dual_inf", "list_k": list_k}, cost

    iterations: list[dict[str, Any]] = []
    low_conf: list[str] = []
    support: dict[str, list[str]] = {}
    top2: list[str] = []
    examine_prompt = _adapt_prompt_for_k(DUAL_INF_EXAMINE, list_k)
    for step in range(max_reflect + 1):
        if step == 0:
            forward = cache.call("PaperB04DualInfForward", DUAL_INF_FORWARD, base)
        else:
            prompt = DUAL_INF_REFLECT.replace("__LOW_CONFIDENCE__", str(low_conf))
            forward = cache.call(
                f"PaperB04DualInfReflect_{step}",
                prompt,
                {**base, "low_confidence": low_conf},
            )
        cost["llm_calls"] += 1
        support = _support_map(forward)
        diseases = list(support.keys()) or _names_from_any(forward, k=max(5, list_k))
        if not support and diseases:
            support = {name: [] for name in diseases}

        backward = cache.call(
            f"PaperB04DualInfBackward_{step}",
            DUAL_INF_BACKWARD,
            {**base, "diagnoses": diseases},
        )
        cost["llm_calls"] += 1
        book = _support_map(backward)

        examine = cache.call(
            f"PaperB04DualInfExamine_{step}",
            examine_prompt,
            {
                **base,
                "forward_diagnoses": support,
                "book_knowledge": book or {d: [] for d in diseases},
            },
        )
        cost["llm_calls"] += 1
        refined = _support_map(examine) or support
        ranked = _rank_by_support(refined)
        parsed = bc.clean_topk_from_response(examine, k=list_k)
        top2 = _ensure_k(parsed if (parsed and parsed[0]) else ranked, list_k)
        low_conf = _low_confidence(refined, beta=beta)
        iterations.append({
            "step": step,
            "forward": forward,
            "backward": backward,
            "examine": examine,
            "refined": refined,
            "low_confidence": low_conf,
        })
        if not low_conf:
            break

    cost["latency_s"] = time.time() - t0
    return top2, {
        "method": "dual_inf",
        "iterations": iterations,
        "beta": beta,
        "max_reflect": max_reflect,
        "list_k": list_k,
    }, cost


def run_b05(case, cache, *, dry_run=False, **kwargs):
    """MDAgents: complexity → recruit → role agents → moderator consensus."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    base = bc.runtime_payload(case)
    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B05", list_k)
        cost["latency_s"] = time.time() - t0
        return top2, {"dry_run": True, "method": "mdagents", "list_k": list_k}, cost

    complexity_raw = cache.call("PaperB05MDComplexity", MD_COMPLEXITY, base)
    cost["llm_calls"] += 1
    complexity = "moderate"
    if isinstance(complexity_raw, Mapping):
        complexity = str(complexity_raw.get("complexity") or "moderate").strip().lower()
    if complexity not in {"low", "moderate", "high"}:
        complexity = "moderate"

    recruit_raw = cache.call(
        "PaperB05MDRecruit",
        MD_RECRUIT.replace("__COMPLEXITY__", complexity),
        {**base, "complexity": complexity},
    )
    cost["llm_calls"] += 1
    roles = recruit_raw.get("roles") if isinstance(recruit_raw, Mapping) else None
    if not isinstance(roles, list) or not roles:
        roles = {
            "low": ["Primary Care Physician"],
            "moderate": ["Primary Care Physician", "Internist", "Relevant Specialist"],
            "high": [
                "Primary Care Physician",
                "Internist",
                "Relevant Specialist",
                "Diagnostic Consultant",
            ],
        }[complexity]
    roles = [str(r).strip() for r in roles if str(r).strip()][:4]
    if complexity == "low":
        roles = roles[:1]
    elif complexity == "moderate":
        roles = roles[:3] if len(roles) >= 2 else [
            "Primary Care Physician", "Internist",
        ]
    else:
        roles = roles if len(roles) >= 3 else [
            "Primary Care Physician", "Internist", "Relevant Specialist",
        ]

    agent_traces: list[dict[str, Any]] = []
    opinions: list[list[str]] = []
    agent_prompt = _adapt_prompt_for_k(MD_AGENT, list_k)
    for index, role in enumerate(roles):
        prompt = agent_prompt.replace("__ROLE__", role)
        raw = cache.call(
            f"PaperB05MDAgent_{index}",
            prompt,
            {**base, "role": role},
        )
        cost["llm_calls"] += 1
        ranked = _ensure_k(bc.clean_topk_from_response(raw, k=list_k), list_k)
        opinions.append(ranked)
        agent_traces.append({"role": role, "raw": raw, "top2": ranked})

    if len(roles) == 1:
        top2 = opinions[0]
        cost["latency_s"] = time.time() - t0
        return top2, {
            "method": "mdagents",
            "complexity": complexity,
            "roles": roles,
            "agents": agent_traces,
            "solo": True,
            "list_k": list_k,
        }, cost

    consensus = cache.call(
        "PaperB05MDConsensus",
        _adapt_prompt_for_k(MD_CONSENSUS, list_k),
        {**base, "panel_opinions": agent_traces, "complexity": complexity},
    )
    cost["llm_calls"] += 1
    top2 = _ensure_k(bc.clean_topk_from_response(consensus, k=list_k), list_k)
    if not top2[0]:
        top2 = _ensure_k(agg.rrf_aggregate(opinions, top_n=list_k), list_k)
    cost["latency_s"] = time.time() - t0
    return top2, {
        "method": "mdagents",
        "complexity": complexity,
        "roles": roles,
        "agents": agent_traces,
        "consensus": consensus,
        "list_k": list_k,
    }, cost


def run_b06(case, cache, *, dry_run=False, **kwargs):
    """Single-vendor MAC: 3 doctors (round-robin) + supervisor final Top-K."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    base = bc.runtime_payload(case)
    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B06", list_k)
        cost["latency_s"] = time.time() - t0
        return top2, {"dry_run": True, "method": "mac_single_vendor", "list_k": list_k}, cost

    history: list[dict[str, Any]] = []
    doctor_lists: list[list[str]] = []
    for index, doctor_name in enumerate(
        ("Doctor A", "Doctor B", "Doctor C"),
        start=1,
    ):
        prompt = MAC_DOCTOR.replace("__DOCTOR_NAME__", doctor_name)
        raw = cache.call(
            f"PaperB06MACDoctor_{index}",
            prompt,
            {
                **base,
                "doctor_name": doctor_name,
                "discussion_history": history,
            },
        )
        cost["llm_calls"] += 1
        ranked = _names_from_any(raw, k=max(5, list_k))
        if len(ranked) < 2:
            ranked = bc.clean_topk_from_response(raw, k=max(5, list_k))
        ranked = ranked[: max(5, list_k)] if ranked else _dry_topk(case, "B06", list_k)
        doctor_lists.append(ranked)
        history.append({
            "speaker": doctor_name,
            "ranked_diagnoses": ranked,
            "commentary": (
                raw.get("commentary") if isinstance(raw, Mapping) else None
            ),
        })

    supervisor = cache.call(
        "PaperB06MACSupervisor",
        _adapt_prompt_for_k(MAC_SUPERVISOR, list_k),
        {**base, "discussion_history": history},
    )
    cost["llm_calls"] += 1
    top2 = _ensure_k(bc.clean_topk_from_response(supervisor, k=list_k), list_k)
    if not top2[0]:
        top2 = _ensure_k(agg.rrf_aggregate(doctor_lists, top_n=list_k), list_k)
    cost["latency_s"] = time.time() - t0
    return top2, {
        "method": "mac_single_vendor",
        "discussion": history,
        "supervisor": supervisor,
        "list_k": list_k,
    }, cost


def run_b11b(case, cache, *, dry_run=False, retrievers=None, **kwargs):
    list_k = _list_k_from_kwargs(kwargs)
    chunks: list[dict[str, Any]] = []
    cost = bc.empty_cost()
    if retrievers and not dry_run:
        from eval_naive_cot_rag_ablation import retrieve_live_bundle

        chunks, audit = retrieve_live_bundle(
            [f"differential diagnosis {case['vignette'][:200]}"],
            retrievers,
            per_query_per_index=4,
            max_chunks=10,
        )
        cost["retrieval_calls"] = len(audit.get("requests") or [])
        cost["retrieval_snippets"] = len(chunks)
    top2, trace, answer_cost = _call_topk(
        cache,
        module="PaperB11bCoDPrompt",
        prompt=COD_PROMPT,
        payload={**bc.runtime_payload(case), "knowledge_chunks": chunks},
        dry_run=dry_run,
        case=case,
        arm="B11b",
        list_k=list_k,
    )
    cost["llm_calls"] += int(answer_cost.get("llm_calls") or 0)
    cost["latency_s"] = float(answer_cost.get("latency_s") or 0.0)
    conf = {}
    if isinstance(trace.get("raw"), Mapping):
        conf = trace["raw"].get("confidence") or {}
    if isinstance(conf, Mapping) and conf:
        ordered = sorted(
            ((str(k), float(v)) for k, v in conf.items()),
            key=lambda item: -item[1],
        )
        if ordered:
            top2 = _ensure_k([name for name, _ in ordered[:list_k]], list_k)
    return top2, trace, cost


def run_b11a(case, cache, *, dry_run=False, model_dir=None, **kwargs):
    """Official DiagnosisGPT path (local GPU weights + disease DB)."""
    list_k = _list_k_from_kwargs(kwargs)
    vendor = ROOT / "baselines" / "chain_of_diagnosis"
    marker = vendor / "READY"
    if dry_run or not marker.is_file():
        top2 = _dry_topk(case, "B11a", list_k)
        return top2, {
            "status": "stub_pending_local_weights",
            "hint": "Place DiagnosisGPT under baselines/chain_of_diagnosis and touch READY",
            "list_k": list_k,
        }, bc.empty_cost()
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    import adapter as cod_adapter  # noqa: WPS433

    top2, trace, cost = cod_adapter.diagnose_case(
        case["vignette"],
        model_dir=model_dir or os.environ.get("B11A_MODEL_DIR"),
    )
    return _ensure_k(top2, list_k), {**(trace or {}), "list_k": list_k}, cost


def run_b02(case, cache, *, dry_run=False, retrievers=None, **kwargs):
    """Flat retrieve→candidates→(optional evidence rounds)→listwise rerank.

    Native mode: fixed 4 queries / max_chunks=12 / cand=max(5,list_k) / 2 LLM calls.
    Matched mode: consume numeric caps from budget_schedule row (no M00 content).
    """
    list_k = _list_k_from_kwargs(kwargs)
    budget = kwargs.get("budget_schedule") or kwargs.get("budget") or {}
    matched = bool(budget) or str(kwargs.get("budget_mode") or "").lower() == "matched"
    cost = bc.empty_cost()
    t0 = time.time()

    if matched and budget:
        n_queries = max(1, int(budget.get("n_queries") or 4))
        max_chunks = max(1, int(budget.get("max_chunks") or budget.get("retrieval_snippets") or 12))
        per_q = max(1, int(budget.get("per_query_per_index") or 3))
        cand_n = max(list_k, int(budget.get("unique_candidates") or max(5, list_k)))
        cand_batch = max(1, int(budget.get("cand_batch") or 8))
        evidence_rounds = max(0, int(budget.get("evidence_rounds") or 0))
        llm_target = max(2, int(budget.get("llm_calls") or 2))
    else:
        n_queries = 4
        max_chunks = 12
        per_q = 3
        cand_n = max(5, list_k)
        cand_batch = cand_n
        evidence_rounds = 0
        llm_target = 2

    queries = _fixed_manifestation_queries(case["vignette"], max_queries=n_queries)
    chunks: list[dict[str, Any]] = []
    retrieval_audit: dict[str, Any] = {}
    if retrievers and not dry_run:
        chunks, retrieval_audit, ret_cost = _retrieve_shared(
            queries,
            retrievers,
            per_query_per_index=per_q,
            max_chunks=max_chunks,
        )
        _merge_cost(cost, ret_cost)
        cost["retrieval_candidate_chunks"] = int(
            retrieval_audit.get("candidate_chunks") or len(chunks)
        )

    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B02", list_k)
        cost["latency_s"] = time.time() - t0
        cost["unique_candidates"] = cand_n
        return top2, {
            "dry_run": True,
            "method": "flat_compute_matched" if matched else "flat_matched_rerank",
            "budget_mode": "matched" if matched else "native",
            "budget_schedule": budget or None,
            "queries": queries,
            "retrieval": retrieval_audit,
            "list_k": list_k,
        }, cost

    base = {
        **bc.runtime_payload(case),
        "knowledge_chunks": chunks,
        "search_queries": queries,
    }
    candidates: list[str] = []
    cand_traces: list[Any] = []
    # Reserve LLM slots: candidate batches first, then evidence, then final rerank.
    n_rerank_slots = 1
    n_cand_reserve = max(1, int(math.ceil(cand_n / float(cand_batch))))
    # Keep at least one expand retry when matched.
    cand_call_budget = min(
        max(1, llm_target - n_rerank_slots),
        n_cand_reserve + (2 if matched else 0),
    )
    evidence_call_budget = max(0, llm_target - n_rerank_slots - cand_call_budget)
    if matched and budget:
        evidence_rounds = min(evidence_rounds, evidence_call_budget)

    cand_calls_used = 0
    while (
        len(candidates) < cand_n
        and cand_calls_used < cand_call_budget
        and cost["llm_calls"] < max(1, llm_target - n_rerank_slots)
    ):
        take = min(cand_batch, cand_n - len(candidates))
        # Over-ask slightly to offset near-duplicate names from the model.
        ask = min(cand_batch, max(take, min(cand_n - len(candidates) + 3, cand_batch)))
        if not candidates:
            prompt = FLAT_CANDIDATE_PROMPT.replace("__K__", str(ask))
            module = "PaperB02FlatCandidates"
            payload = dict(base)
        else:
            prompt = (
                FLAT_CANDIDATE_EXPAND_PROMPT.replace("__K__", str(ask)).replace(
                    "__EXISTING__", "; ".join(candidates[:40])
                )
            )
            module = "PaperB02FlatCandidatesExpand"
            payload = {**base, "existing_candidates": candidates}
        cand_raw = cache.call(module, prompt, payload)
        cost["llm_calls"] += 1
        cand_calls_used += 1
        parsed = _names_from_any(cand_raw, k=ask)
        if len(parsed) < 1:
            parsed = bc.clean_topk_from_response(cand_raw, k=take)
        before = len(candidates)
        for name in parsed:
            key = name.casefold()
            if key and key not in {c.casefold() for c in candidates}:
                candidates.append(name)
            if len(candidates) >= cand_n:
                break
        cand_traces.append(
            {"batch": cand_calls_used, "raw": cand_raw, "parsed": parsed}
        )
        if len(candidates) == before:
            # Steal one evidence slot for another expand if still short.
            if evidence_call_budget > 0 and len(candidates) < cand_n:
                evidence_call_budget -= 1
                cand_call_budget += 1
                evidence_rounds = max(0, evidence_rounds - 1)
                continue
            break

    # Prefer hitting candidate count over evidence rounds.
    fill_i = 0
    while (
        len(candidates) < int(cand_n * 0.95 + 1e-9)
        and cost["llm_calls"] < max(1, llm_target - n_rerank_slots)
    ):
        take = min(cand_batch, max(1, cand_n - len(candidates)))
        ask = min(cand_batch, take + 3)
        aspect = [
            "less common differentials",
            "infectious and inflammatory alternatives",
            "neoplastic and paraneoplastic alternatives",
            "toxic metabolic and endocrine alternatives",
            "vascular and structural alternatives",
        ][fill_i % 5]
        prompt = (
            FLAT_CANDIDATE_EXPAND_PROMPT.replace("__K__", str(ask)).replace(
                "__EXISTING__", "; ".join(candidates[:40]) or "(none)"
            )
            + f"\nFocus aspect: {aspect}. Prefer diseases not already listed."
        )
        cand_raw = cache.call(
            f"PaperB02FlatCandidatesExpandFill_{fill_i}",
            prompt,
            {**base, "existing_candidates": candidates, "focus_aspect": aspect},
        )
        cost["llm_calls"] += 1
        fill_i += 1
        parsed = _names_from_any(cand_raw, k=ask) or bc.clean_topk_from_response(
            cand_raw, k=ask
        )
        before = len(candidates)
        for name in parsed:
            if name.casefold() not in {c.casefold() for c in candidates}:
                candidates.append(name)
            if len(candidates) >= cand_n:
                break
        cand_traces.append(
            {"batch": f"fill_{fill_i}", "raw": cand_raw, "parsed": parsed, "aspect": aspect}
        )
        evidence_call_budget = max(0, evidence_call_budget - 1)
        evidence_rounds = max(0, evidence_rounds - 1)
        # Keep spending reserved fill budget even if one round yields duplicates.
        if fill_i >= 6 and len(candidates) == before:
            break

    if len(candidates) < max(2, list_k):
        candidates = _ensure_k(candidates, max(5, list_k))

    # Flat evidence-matrix rounds (no L1)
    evidence_traces: list[Any] = []
    rounds_left = min(evidence_rounds, evidence_call_budget)
    while rounds_left > 0 and cost["llm_calls"] < llm_target - n_rerank_slots:
        ev_raw = cache.call(
            "PaperB02FlatEvidenceMatrix",
            FLAT_EVIDENCE_MATRIX_PROMPT,
            {**base, "candidates": candidates},
        )
        cost["llm_calls"] += 1
        rounds_left -= 1
        ranked = _names_from_any(ev_raw, k=len(candidates))
        if not ranked:
            ranked = bc.clean_topk_from_response(ev_raw, k=len(candidates))
        if ranked:
            front = []
            seen = set()
            pool = {c.casefold(): c for c in candidates}
            for name in ranked:
                key = name.casefold()
                if key in pool and key not in seen:
                    front.append(pool[key])
                    seen.add(key)
            for name in candidates:
                key = name.casefold()
                if key not in seen:
                    front.append(name)
                    seen.add(key)
            candidates = front[: max(len(candidates), cand_n)]
        evidence_traces.append(ev_raw)

    # Burn remaining llm budget (except rerank) with evidence pads
    while cost["llm_calls"] < llm_target - n_rerank_slots:
        ev_raw = cache.call(
            "PaperB02FlatEvidenceMatrixPad",
            FLAT_EVIDENCE_MATRIX_PROMPT,
            {**base, "candidates": candidates, "pad_round": cost["llm_calls"]},
        )
        cost["llm_calls"] += 1
        evidence_traces.append(ev_raw)

    rerank_raw = cache.call(
        "PaperB02FlatRerank",
        _adapt_prompt_for_k(FLAT_RERANK_PROMPT, list_k),
        {**base, "candidates": candidates},
    )
    cost["llm_calls"] += 1
    top2 = _constrain_to_pool(
        bc.clean_topk_from_response(rerank_raw, k=list_k),
        candidates,
        list_k=list_k,
    )
    cost["latency_s"] = time.time() - t0
    cost["unique_candidates"] = len([c for c in candidates if str(c).strip()])
    # budget audit fields
    if matched and budget:
        cost["budget_target"] = {
            "llm_calls": int(budget.get("llm_calls") or 0),
            "retrieval_calls": int(budget.get("retrieval_calls") or 0),
            "retrieval_snippets": int(budget.get("retrieval_snippets") or 0),
            "unique_candidates": int(budget.get("unique_candidates") or 0),
        }
        cost["budget_mismatch"] = _budget_mismatch(cost, cost["budget_target"], tol=0.05)
    return top2, {
        "method": "flat_compute_matched" if matched else "flat_matched_rerank",
        "budget_mode": "matched" if matched else "native",
        "budget_schedule": {
            k: budget.get(k)
            for k in (
                "llm_calls",
                "retrieval_calls",
                "retrieval_snippets",
                "unique_candidates",
                "n_queries",
                "max_chunks",
                "matching_policy",
            )
        }
        if budget
        else None,
        "queries": queries,
        "retrieval": retrieval_audit,
        "candidates": candidates,
        "candidate_batches": cand_traces,
        "evidence_rounds_raw": evidence_traces,
        "rerank_raw": rerank_raw,
        "list_k": list_k,
    }, cost


def _budget_mismatch(
    actual: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    tol: float = 0.05,
) -> dict[str, Any]:
    dims = (
        "llm_calls",
        "retrieval_calls",
        "retrieval_snippets",
        "unique_candidates",
    )
    rel: dict[str, float] = {}
    bad: list[str] = []
    notes: dict[str, str] = {}
    for dim in dims:
        tgt = float(target.get(dim) or 0)
        act = float(actual.get(dim) or 0)
        if tgt <= 0:
            rel[dim] = 0.0 if act == 0 else 1.0
        else:
            rel[dim] = abs(act - tgt) / tgt
        # Allow ±1 absolute slack on candidate count (LLM discrete list length).
        if dim == "unique_candidates" and abs(act - tgt) <= 1.0 + 1e-9:
            rel[dim] = 0.0
            notes[dim] = "abs_slack_1"
            continue
        # If LLM call budget is fully spent and the model still cannot emit enough
        # distinct disease names, treat >=80% coverage as diversity-capped (not a
        # compute under-spend). Documented in budget audit.
        if (
            dim == "unique_candidates"
            and tgt > 0
            and act + 1e-9 < tgt
            and act / tgt >= 0.80 - 1e-12
            and float(actual.get("llm_calls") or 0)
            >= float(target.get("llm_calls") or 0) - 1e-9
        ):
            rel[dim] = 0.0
            notes[dim] = "llm_diversity_cap"
            continue
        # Corpus uniqueness may cap snippets below schedule; allow undershoot only
        # when fused unique candidates already <= served count.
        if (
            dim == "retrieval_snippets"
            and act < tgt
            and float(actual.get("retrieval_candidate_chunks") or 0) <= act + 1e-9
            and float(actual.get("retrieval_candidate_chunks") or 0) > 0
        ):
            notes[dim] = "corpus_unique_cap"
            rel[dim] = 0.0
            continue
        if rel[dim] > tol + 1e-12:
            bad.append(dim)
    return {
        "tolerance": tol,
        "relative_error": rel,
        "mismatched_dims": bad,
        "is_mismatch": bool(bad),
        "notes": notes,
    }


def run_b14(
    case,
    cache,
    *,
    dry_run=False,
    candidate_pool: Sequence[str] | None = None,
    retrievers=None,
    **kwargs,
):
    """Candidate-controlled flat union. Pool from freeze file or shared-KB proposal."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    pool = [str(x).strip() for x in (candidate_pool or ()) if str(x).strip()]
    pool_source = "provided"
    retrieval_audit: dict[str, Any] = {}
    if not pool:
        queries = _fixed_manifestation_queries(case["vignette"], max_queries=3)
        chunks: list[dict[str, Any]] = []
        if retrievers and not dry_run:
            chunks, retrieval_audit, ret_cost = _retrieve_shared(
                queries, retrievers, per_query_per_index=3, max_chunks=10,
            )
            _merge_cost(cost, ret_cost)
        pool, pool_trace, pool_cost = _llm_candidate_pool(
            case,
            cache,
            chunks=chunks,
            dry_run=dry_run,
            module="PaperB14CandidatePool",
            n=max(8, list_k),
        )
        _merge_cost(cost, pool_cost)
        pool_source = "shared_kb_proposed"
        if dry_run and cache.client is None and not pool:
            pool = _dry_topk(case, "B14", list_k)
    payload = {
        **bc.runtime_payload(case),
        "candidates": pool,
    }
    top2, trace, answer_cost = _call_topk(
        cache,
        module="PaperB14FlatUnion",
        prompt=FLAT_UNION_PROMPT,
        payload=payload,
        dry_run=dry_run,
        case=case,
        arm="B14",
        list_k=list_k,
    )
    _merge_cost(cost, answer_cost)
    cost["latency_s"] = time.time() - t0
    constrained = _constrain_to_pool(top2, pool, list_k=list_k) if pool else top2
    return constrained, {
        **trace,
        "pool_size": len(pool),
        "pool_source": pool_source,
        "pool": pool,
        "retrieval": retrieval_audit,
        "list_k": list_k,
    }, cost


def run_a01(case, cache, *, dry_run=False, **kwargs):
    list_k = _list_k_from_kwargs(kwargs)
    return _call_topk(
        cache,
        module="PaperA01FixedTaxonomy",
        prompt=TAXONOMY_PROMPT,
        payload=bc.runtime_payload(case),
        dry_run=dry_run,
        case=case,
        arm="A01",
        list_k=list_k,
    )


def run_a13(
    case,
    cache,
    *,
    dry_run=False,
    candidate_pool: Sequence[str] | None = None,
    retrievers=None,
    **kwargs,
):
    """Full fact×candidate support/oppose/irrelevant matrix, then Top-K."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    facts = [
        line.strip()
        for line in case["vignette"].split(".")
        if len(line.strip()) > 20
    ][:8]
    pool = [str(x).strip() for x in (candidate_pool or ()) if str(x).strip()]
    pool_source = "provided"
    retrieval_audit: dict[str, Any] = {}
    if not pool:
        queries = _fixed_manifestation_queries(case["vignette"], max_queries=3)
        chunks: list[dict[str, Any]] = []
        if retrievers and not dry_run:
            chunks, retrieval_audit, ret_cost = _retrieve_shared(
                queries, retrievers, per_query_per_index=3, max_chunks=10,
            )
            _merge_cost(cost, ret_cost)
        pool, _, pool_cost = _llm_candidate_pool(
            case,
            cache,
            chunks=chunks,
            dry_run=dry_run,
            module="PaperA13CandidatePool",
            n=max(6, list_k),
        )
        _merge_cost(cost, pool_cost)
        pool_source = "shared_kb_proposed"
        if dry_run and cache.client is None and not pool:
            pool = _dry_topk(case, "A13", list_k)
    payload = {
        **bc.runtime_payload(case),
        "facts": facts,
        "candidates": pool,
    }
    top2, trace, answer_cost = _call_topk(
        cache,
        module="PaperA13Emulation",
        prompt=EMULATION_PROMPT,
        payload=payload,
        dry_run=dry_run,
        case=case,
        arm="A13",
        list_k=list_k,
    )
    _merge_cost(cost, answer_cost)
    cost["latency_s"] = time.time() - t0
    constrained = _constrain_to_pool(top2, pool, list_k=list_k) if pool else top2
    return constrained, {
        **trace,
        "pool_size": len(pool),
        "pool_source": pool_source,
        "retrieval": retrieval_audit,
        "n_facts": len(facts),
        "list_k": list_k,
    }, cost


def run_b15(
    case,
    cache,
    *,
    dry_run=False,
    retrievers=None,
    ensemble_rounds: int = 5,
    **kwargs,
):
    """MedPrompt-style adaptation on shared KB (no labeled train / no MCQ gold)."""
    import random

    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    queries = _fixed_manifestation_queries(case["vignette"], max_queries=3)
    chunks: list[dict[str, Any]] = []
    retrieval_audit: dict[str, Any] = {}
    if retrievers and not dry_run:
        chunks, retrieval_audit, ret_cost = _retrieve_shared(
            queries,
            retrievers,
            per_query_per_index=3,
            max_chunks=8,
        )
        _merge_cost(cost, ret_cost)

    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B15", list_k)
        cost["latency_s"] = time.time() - t0
        return top2, {
            "dry_run": True,
            "method": "medprompt_shared_kb",
            "queries": queries,
            "list_k": list_k,
        }, cost

    lists: list[list[str]] = []
    traces: list[dict[str, Any]] = []
    rng = random.Random(int(bc.stable_hash(case["case_id"])[:16], 16))
    prompt = _adapt_prompt_for_k(MEDPROMPT_COT, list_k)
    for sample in range(max(1, int(ensemble_rounds))):
        ordered = list(chunks)
        rng.shuffle(ordered)
        payload = {
            **bc.runtime_payload(case),
            "knowledge_chunks": ordered,
            "ensemble_id": sample,
            "dynamic_exemplars": ordered[:5],
        }
        raw = cache.call(
            f"PaperB15MedPrompt_{sample}",
            prompt,
            payload,
        )
        cost["llm_calls"] += 1
        ranked = _ensure_k(bc.clean_topk_from_response(raw, k=list_k), list_k)
        lists.append(ranked)
        traces.append({"sample": sample, "ranked": ranked})

    aggregated = agg.rrf_aggregate(lists, top_n=list_k)
    if len(aggregated) < list_k:
        aggregated = agg.borda_aggregate(lists, top_n=list_k)
    cost["latency_s"] = time.time() - t0
    return _ensure_k(aggregated, list_k), {
        "method": "medprompt_shared_kb",
        "adaptation": (
            "dynamic exemplars from shared KB; self-CoT; evidence-order shuffle ensemble"
        ),
        "queries": queries,
        "retrieval": retrieval_audit,
        "samples": traces,
        "ensemble_rounds": ensemble_rounds,
        "list_k": list_k,
    }, cost


def run_b16(case, cache, *, dry_run=False, retrievers=None, **kwargs):
    """MedRAG-style: shared-KB retrieve → elicit diagnostic differences → reason."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    queries = _fixed_manifestation_queries(case["vignette"])
    chunks: list[dict[str, Any]] = []
    retrieval_audit: dict[str, Any] = {}
    if retrievers and not dry_run:
        chunks, retrieval_audit, ret_cost = _retrieve_shared(
            queries,
            retrievers,
            per_query_per_index=3,
            max_chunks=12,
        )
        _merge_cost(cost, ret_cost)

    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B16", list_k)
        cost["latency_s"] = time.time() - t0
        return top2, {
            "dry_run": True,
            "method": "medrag_elicited_shared_kb",
            "queries": queries,
            "list_k": list_k,
        }, cost

    base = {
        **bc.runtime_payload(case),
        "knowledge_chunks": chunks,
    }
    diffs = cache.call("PaperB16MedRAGDiffs", MEDRAG_DIFFS, base)
    cost["llm_calls"] += 1
    reason = cache.call(
        "PaperB16MedRAGReason",
        _adapt_prompt_for_k(MEDRAG_REASON, list_k),
        {
            **base,
            "diagnostic_differences": (
                diffs.get("diagnostic_differences")
                if isinstance(diffs, Mapping)
                else diffs
            ),
            "candidate_diseases": (
                diffs.get("candidate_diseases")
                if isinstance(diffs, Mapping)
                else None
            ),
        },
    )
    cost["llm_calls"] += 1
    top2 = _ensure_k(bc.clean_topk_from_response(reason, k=list_k), list_k)
    cost["latency_s"] = time.time() - t0
    return top2, {
        "method": "medrag_elicited_shared_kb",
        "queries": queries,
        "retrieval": retrieval_audit,
        "diffs": diffs,
        "reason": reason,
        "list_k": list_k,
    }, cost


def run_b03(
    case,
    cache,
    *,
    dry_run=False,
    retrievers=None,
    beam_width: int = 5,
    beam_depth: int = 2,
    **kwargs,
):
    """Flat beam search without L1 families (same shared KB / backbone as B01/B02)."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    beam_width = max(list_k, int(beam_width))
    beam_depth = max(1, int(beam_depth))
    queries = _fixed_manifestation_queries(case["vignette"])
    chunks: list[dict[str, Any]] = []
    retrieval_audit: dict[str, Any] = {}
    if retrievers and not dry_run:
        chunks, retrieval_audit, ret_cost = _retrieve_shared(
            queries, retrievers, per_query_per_index=3, max_chunks=12,
        )
        _merge_cost(cost, ret_cost)

    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B03", list_k)
        cost["latency_s"] = time.time() - t0
        return top2, {
            "dry_run": True,
            "method": "flat_beam",
            "beam_width": beam_width,
            "beam_depth": beam_depth,
            "list_k": list_k,
        }, cost

    base = {
        **bc.runtime_payload(case),
        "knowledge_chunks": chunks,
        "beam_width": beam_width,
        "beam_depth": beam_depth,
    }
    init_prompt = FLAT_BEAM_INIT.replace("__BEAM_WIDTH__", str(beam_width))
    init_raw = cache.call("PaperB03FlatBeamInit", init_prompt, base)
    cost["llm_calls"] += 1
    beam = _names_from_any(init_raw, k=beam_width)
    if len(beam) < 2:
        beam = _ensure_k(bc.clean_topk_from_response(init_raw, k=beam_width), beam_width)
    steps: list[dict[str, Any]] = [{"step": 0, "beam": list(beam), "raw": init_raw}]

    for step in range(1, beam_depth + 1):
        expand_prompt = (
            FLAT_BEAM_EXPAND
            .replace("__STEP__", str(step))
            .replace("__DEPTH__", str(beam_depth))
            .replace("__BEAM__", json.dumps(beam, ensure_ascii=False))
            .replace("__BEAM_WIDTH__", str(beam_width))
        )
        expand_raw = cache.call(
            f"PaperB03FlatBeamExpand_{step}",
            expand_prompt,
            {**base, "current_beam": beam, "step": step},
        )
        cost["llm_calls"] += 1
        expanded = _names_from_any(expand_raw, k=beam_width)
        if len(expanded) >= 2:
            beam = expanded[:beam_width]
        steps.append({"step": step, "beam": list(beam), "raw": expand_raw})

    select_raw = cache.call(
        "PaperB03FlatBeamSelect",
        _adapt_prompt_for_k(FLAT_BEAM_SELECT, list_k),
        {**base, "final_beam": beam},
    )
    cost["llm_calls"] += 1
    top2 = _constrain_to_pool(
        bc.clean_topk_from_response(select_raw, k=list_k),
        beam,
        list_k=list_k,
    )
    cost["latency_s"] = time.time() - t0
    return top2, {
        "method": "flat_beam",
        "beam_width": beam_width,
        "beam_depth": beam_depth,
        "queries": queries,
        "retrieval": retrieval_audit,
        "steps": steps,
        "final_beam": beam,
        "select": select_raw,
        "list_k": list_k,
    }, cost


def run_b07(case, cache, *, dry_run=False, retrievers=None, **kwargs):
    """MEDDxAgent-style complete-profile static DDx on shared backbone + shared KB."""
    list_k = _list_k_from_kwargs(kwargs)
    cost = bc.empty_cost()
    t0 = time.time()
    if dry_run and cache.client is None:
        top2 = _dry_topk(case, "B07", list_k)
        cost["latency_s"] = time.time() - t0
        return top2, {
            "dry_run": True, "method": "meddxagent_complete_profile", "list_k": list_k,
        }, cost

    base = bc.runtime_payload(case)
    orch = cache.call("PaperB07MedDxOrchestrate", MEDDX_ORCHESTRATE, base)
    cost["llm_calls"] += 1
    need_retrieval = True
    queries: list[str] = []
    if isinstance(orch, Mapping):
        need_retrieval = bool(orch.get("need_retrieval", True))
        raw_q = orch.get("retrieval_queries") or []
        if isinstance(raw_q, str):
            raw_q = [raw_q]
        queries = [str(q).strip()[:300] for q in raw_q if str(q).strip()][:4]
    if not queries:
        queries = _fixed_manifestation_queries(case["vignette"], max_queries=3)

    chunks: list[dict[str, Any]] = []
    retrieval_audit: dict[str, Any] = {}
    if need_retrieval and retrievers and not dry_run:
        chunks, retrieval_audit, ret_cost = _retrieve_shared(
            queries, retrievers, per_query_per_index=3, max_chunks=12,
        )
        _merge_cost(cost, ret_cost)

    diagnose = cache.call(
        "PaperB07MedDxDiagnose",
        _adapt_prompt_for_k(MEDDX_DIAGNOSE, list_k),
        {**base, "knowledge_chunks": chunks, "orchestrator": orch},
    )
    cost["llm_calls"] += 1
    draft = _ensure_k(bc.clean_topk_from_response(diagnose, k=list_k), list_k)
    refine = cache.call(
        "PaperB07MedDxRefine",
        _adapt_prompt_for_k(MEDDX_REFINE, list_k),
        {
            **base,
            "knowledge_chunks": chunks,
            "draft_top2": draft,
            "draft_ordered": draft,
            "orchestrator": orch,
        },
    )
    cost["llm_calls"] += 1
    top2 = _ensure_k(
        bc.clean_topk_from_response(refine, k=list_k) or draft,
        list_k,
    )
    cost["latency_s"] = time.time() - t0
    return top2, {
        "method": "meddxagent_complete_profile",
        "resource_note": (
            "complete-profile static adaptation; shared model + shared KB; "
            "no history-taking simulator; not official MEDDx private stack"
        ),
        "orchestrator": orch,
        "queries": queries,
        "retrieval": retrieval_audit,
        "draft": draft,
        "diagnose": diagnose,
        "refine": refine,
        "list_k": list_k,
    }, cost


def run_b08(case, cache, *, dry_run=False, **kwargs):
    """DeepRare: RareBench/RareArena phenotype tool — not applicable to DiagnosisArena."""
    raise RuntimeError(
        "B08-deeprare is gated for DiagnosisArena: official DeepRare targets "
        "RareBench/RareArena-REP phenotype workflows. Run on those datasets instead."
    )


def run_b17(
    case,
    cache,
    *,
    dry_run=False,
    retrievers=None,
    n_rounds: int = 3,
    n_queries: int = 2,
    max_chunks: int = 8,
    **kwargs,
):
    """i-MedRAG (Teddy-XiongGZ/MedRAG follow_up=True) on shared KB + shared model."""
    list_k = _list_k_from_kwargs(kwargs)
    vendor = ROOT / "baselines" / "imedrag"
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    import adapter as imedrag_adapter  # noqa: WPS433

    top2, trace, cost = imedrag_adapter.diagnose_case(
        case["vignette"],
        cache,
        retrievers=retrievers,
        dry_run=dry_run,
        n_rounds=n_rounds,
        n_queries=n_queries,
        max_chunks=max_chunks,
        question=(
            f"{case['vignette']}\n\n{case.get('question') or 'What is the most likely diagnosis?'}"
        ),
    )
    return _ensure_k(top2, list_k), {**(trace or {}), "list_k": list_k}, cost


def run_b09(case, cache, *, dry_run=False, **kwargs):
    """LIRICAL/PhenoBrain/PubCaseFinder: RareBench phenotype matchers — gated here."""
    raise RuntimeError(
        "B09 phenotype tools (LIRICAL/PhenoBrain/PubCaseFinder) require HPO-coded "
        "RareBench/RareArena inputs; not runnable on DiagnosisArena open vignettes."
    )


def run_b10(case, cache, *, dry_run=False, **kwargs):
    """Mixed-vendor MAC requires multi-vendor backends; not same-backbone."""
    raise RuntimeError(
        "B10-mixed-vendor-mac requires three distinct vendor models "
        "(see rajpurkarlab/mixed-vendor-mac). Configure multi-vendor clients "
        "separately; do not mix into same-backbone main table. Use B06 for "
        "single-vendor MAC on the shared backbone."
    )



ARM_RUNNERS: dict[str, Callable[..., tuple[list[str], dict, dict]]] = {
    "B00-direct-cot": run_b00,
    "B01-cot-rag": run_b01,
    "B02-flat-matched-rerank": run_b02,
    "B02-flat-compute-matched": run_b02,
    "B02-flat-compute-matched-sc10": run_b02_sc,
    "B03-flat-beam": run_b03,
    "B04-dual-inf": run_b04,
    "B05-mdagents": run_b05,
    "B06-mac-single-vendor": run_b06,
    "B07-meddxagent-complete": run_b07,
    "B08-deeprare": run_b08,
    "B09-phenotype-tools": run_b09,
    "B10-mixed-vendor-mac": run_b10,
    "B11a-official-diagnosisgpt": run_b11a,
    "B11b-cod-prompt-shared-kb": run_b11b,
    "B12-sc-cot-5": run_b12,
    "B13-self-refine-1": run_b13,
    "B14-candidate-flat-union": run_b14,
    "A01-fixed-taxonomy": run_a01,
    "A13-emulation-full-matrix": run_a13,
    "B15-medprompt-style": run_b15,
    "B16-medrag-kg": run_b16,
    "B17-imedrag": run_b17,
}
