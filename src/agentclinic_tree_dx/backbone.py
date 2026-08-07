"""Lightweight four-step diagnostic backbone (independent of controller).

S1 parse → S2 wide_ddx → S3 entity_filter → S4 select
Optional S2 ablation: feed KB RRF disease-name pool into S3 instead of LLM DDx.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .updater import ORDINAL_WEIGHTS, _DISCRIMINATIVE_LABELS as DISCRIMINATIVE_LABELS

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

SELECT_VARIANTS = ("a", "b", "c", "d", "e", "f", "g", "h")
RANK_CREDITS = (1.0, 0.5, 0.25)
S2_MODES = ("single", "complement", "partition")

# Faithful to l1_evidence_bfs.symmetric_rank_update: bounded symmetric ordinal
# update with per-fact conflict cancellation. Sparse single-winner contract, so
# only RANK_CREDITS[0] is ever used.
ETA = math.log(3.0)

# Deployable stand-in for AB02's per-tree-node conditioning: a fixed etiologic
# partition of disease space, split into three roughly equal-mass groups.
S2_PARTITIONS = (
    "infectious disease; inflammatory, autoimmune and rheumatologic disease",
    "neoplastic and hematologic disease; genetic, congenital and metabolic disease",
    (
        "vascular, structural, degenerative and traumatic disease; "
        "drug, toxic and iatrogenic disease; endocrine disease; "
        "functional and psychogenic disorders"
    ),
)


def _read_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _resolve_label(value: Any, candidates: Sequence[str]) -> Optional[str]:
    """Sparse single-winner contract: map a response to exactly one candidate or
    abstain. Anything that does not resolve unambiguously is an abstention."""
    text = str(value or "").strip()
    if not text or text.casefold() in {"none", "null", "n/a", "-"}:
        return None
    fold = text.casefold()
    for c in candidates:
        if c.casefold() == fold:
            return c
    hits = [c for c in candidates if fold in c.casefold() or c.casefold() in fold]
    return hits[0] if len(hits) == 1 else None


def _as_str_list(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        if isinstance(item, Mapping):
            text = str(item.get("label") or item.get("diagnosis") or "").strip()
        else:
            text = str(item).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


@dataclass
class BackboneResult:
    case_id: str
    champion: str
    ordered_diagnoses: list[str]
    stages: dict[str, Any] = field(default_factory=dict)
    llm_calls: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def as_prediction(self, *, arm: str, source_id: str, dataset: str) -> dict[str, Any]:
        top = list(self.ordered_diagnoses) or ([self.champion] if self.champion else [])
        if self.champion and (not top or top[0] != self.champion):
            top = [self.champion] + [x for x in top if x != self.champion]
        return {
            "arm": arm,
            "case_id": self.case_id,
            "source_id": source_id,
            "dataset": dataset,
            "list_k": len(top[:2]),
            "ordered_diagnoses": top,
            "top2_diagnoses": top[:2],
            "cost": {
                "llm_calls": int(self.llm_calls),
                "retrieval_calls": int(
                    (self.stages.get("s2") or {}).get("retrieval_calls") or 0
                ),
            },
            "stages": self.stages,
            "config": self.config,
        }


class BackbonePipeline:
    """Standalone 4-step backbone. ``llm`` must expose ``call(module, prompt, payload)``."""

    def __init__(
        self,
        llm: Any,
        *,
        select_variant: str = "b",
        max_k: int = 5,
        entrance: str = "llm_ddx",
        kb_retriever: Any = None,
        s2_k: int = 1,
        s2_mode: str = "complement",
        skip_s1: bool = False,
        s3_strict: bool = False,
        s4_facts: int = 4,
        s4_fact_source: str = "salient_then_key",
        s4_inner_workers: int = 4,
    ) -> None:
        if select_variant not in SELECT_VARIANTS:
            raise ValueError(f"select_variant must be one of {SELECT_VARIANTS}")
        if entrance not in ("llm_ddx", "kb_only"):
            raise ValueError("entrance must be llm_ddx or kb_only")
        if s2_mode not in S2_MODES:
            raise ValueError(f"s2_mode must be one of {S2_MODES}")
        self.llm = llm
        self.select_variant = select_variant
        self.max_k = int(max_k)
        self.entrance = entrance
        self.kb_retriever = kb_retriever
        self.s2_k = max(1, int(s2_k))
        self.s2_mode = s2_mode
        self.skip_s1 = bool(skip_s1)
        self.s3_strict = bool(s3_strict)
        self.s4_facts = max(1, int(s4_facts))
        if s4_fact_source not in ("salient_then_key", "key", "atomised"):
            raise ValueError(
                "s4_fact_source must be salient_then_key, key or atomised"
            )
        self.s4_fact_source = s4_fact_source
        self.s4_inner_workers = max(1, int(s4_inner_workers))
        self.prompt_s4_rulein = _read_prompt("backbone_select_rulein.txt")
        self.prompt_s4_ruleout = _read_prompt("backbone_select_ruleout.txt")
        self.prompt_s4_joint = _read_prompt("backbone_select_joint.txt")
        self.prompt_s4_ranked = _read_prompt("backbone_select_ranked.txt")
        self.prompt_s4_ordinal = _read_prompt("backbone_select_ordinal.txt")
        self.prompt_atomise = _read_prompt("backbone_atomise.txt")
        self._last_atomise_calls = 0
        self.prompt_s1 = _read_prompt("backbone_parse.txt")
        self.prompt_s2 = _read_prompt("backbone_wide_ddx.txt")
        self.prompt_s2_comp = _read_prompt("backbone_wide_ddx_complement.txt")
        self.prompt_s2_part = _read_prompt("backbone_wide_ddx_partition.txt")
        self.prompt_s3 = _read_prompt("backbone_entity_filter.txt")
        self.prompt_s3_strict = _read_prompt("backbone_entity_filter_strict.txt")
        self.prompt_s4b = _read_prompt("backbone_select_free.txt")
        self.prompt_s4c = _read_prompt("backbone_select_granularity.txt")
        self.prompt_s4d = _read_prompt("backbone_select_perfact.txt")

    def _call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw = self.llm.call(module, prompt, dict(payload))
        return dict(raw) if isinstance(raw, Mapping) else {"raw": raw}

    def _pick_facts(self, s1: Mapping[str, Any], vignette: str) -> list[str]:
        """Deterministic fact budget: no LLM fact-selector call (AB02 spends
        ~12.6 calls/case on that; this tests whether it is load-bearing).

        ``salient_findings`` are pre-filtered by the same model that produced the
        candidate ordering, so they are correlated with the prior. ``key_facts``
        is the faithful, un-prioritised list and is the closer analogue of AB02's
        ``static_evidence_items``.
        """
        if self.s4_fact_source == "atomised":
            got = _as_str_list(
                self._call(
                    "BackboneAtomise",
                    self.prompt_atomise,
                    {"vignette": vignette},
                ).get("findings")
            )
            if got:
                self._last_atomise_calls = 1
                return got[: self.s4_facts]
        if self.s4_fact_source == "key":
            facts = _as_str_list(s1.get("key_facts"))
            if not facts:
                facts = _as_str_list(s1.get("salient_findings"))
            return facts[: self.s4_facts]
        facts = _as_str_list(s1.get("salient_findings"))
        for extra in _as_str_list(s1.get("key_facts")):
            if len(facts) >= self.s4_facts:
                break
            if extra.casefold() not in {f.casefold() for f in facts}:
                facts.append(extra)
        if not facts:
            facts = [
                ln.strip()
                for ln in vignette.replace(". ", ".\n").splitlines()
                if len(ln.strip()) > 15
            ]
        return facts[: self.s4_facts]

    def run(
        self,
        *,
        case_id: str,
        vignette: str,
        question: str = "What is the most likely diagnosis?",
        reuse_stages: Optional[Mapping[str, Any]] = None,
        skip_s4: bool = False,
    ) -> BackboneResult:
        """Run S1–S4. ``reuse_stages`` may supply prior S1/S2/S3 to avoid re-calls."""
        reuse = dict(reuse_stages or {})
        stages: dict[str, Any] = {}
        calls = 0

        # --- S1 ---
        if self.skip_s1:
            s1 = {
                "syndrome_frame": "",
                "salient_findings": [],
                "key_facts": [],
                "skipped": True,
            }
            stages["s1"] = s1
        elif "s1" in reuse:
            s1 = dict(reuse["s1"])
            stages["s1"] = s1
        else:
            s1_raw = self._call(
                "BackboneParse",
                self.prompt_s1,
                {
                    "vignette": vignette,
                    "question": question,
                },
            )
            calls += 1
            s1 = {
                "syndrome_frame": str(s1_raw.get("syndrome_frame") or "").strip(),
                "salient_findings": _as_str_list(s1_raw.get("salient_findings")),
                "key_facts": _as_str_list(s1_raw.get("key_facts")),
                "raw": s1_raw,
            }
            stages["s1"] = s1

        # --- S2 ---
        # kb_only ablation must never reuse an LLM-DDx S2 list.
        if "s2" in reuse and self.entrance != "kb_only":
            s2 = dict(reuse["s2"])
            stages["s2"] = s2
        elif self.entrance == "kb_only":
            if self.kb_retriever is None:
                raise RuntimeError("kb_only entrance requires kb_retriever")
            pool, meta = self.kb_retriever.recall(
                syndrome=s1.get("syndrome_frame") or "",
                salient=list(s1.get("salient_findings") or []),
                context=vignette[:1500],
                case_summary="",
            )
            s2 = {
                "differentials": list(pool),
                "source": "kb_rrf",
                "retrieval_calls": int(meta.get("retrieval_calls") or 0),
                "meta": meta,
            }
            stages["s2"] = s2
        elif "s2" in reuse and int(reuse.get("s2_k") or 1) == self.s2_k:
            s2 = dict(reuse["s2"])
            stages["s2"] = s2
        else:
            base_payload = {
                "presenting_syndrome": s1.get("syndrome_frame") or "",
                "salient_findings": list(s1.get("salient_findings") or []),
                "context": vignette[:1500] if not self.skip_s1 else vignette,
            }
            pooled: list[str] = []
            per_call: list[list[str]] = []
            for i in range(self.s2_k):
                if i == 0 or self.s2_mode == "single":
                    module, prompt = "BackboneWideDDx", self.prompt_s2
                    payload = dict(base_payload)
                elif self.s2_mode == "complement":
                    module, prompt = "BackboneWideDDxComplement", self.prompt_s2_comp
                    payload = dict(base_payload, already_considered=list(pooled))
                else:
                    module, prompt = "BackboneWideDDxPartition", self.prompt_s2_part
                    payload = dict(
                        base_payload,
                        focus_classes=S2_PARTITIONS[(i - 1) % len(S2_PARTITIONS)],
                    )
                got = _as_str_list(self._call(module, prompt, payload).get("differentials"))
                calls += 1
                per_call.append(got)
                have = {x.casefold() for x in pooled}
                pooled.extend(x for x in got if x.casefold() not in have)
                if self.s2_mode == "single" and i == 0:
                    break
            s2 = {
                "differentials": pooled,
                "source": "llm_ddx",
                "retrieval_calls": 0,
                "s2_k": self.s2_k,
                "s2_mode": self.s2_mode,
                "per_call": per_call,
            }
            stages["s2"] = s2
            stages["s2_k"] = self.s2_k

        differentials = list(s2.get("differentials") or [])
        anchor = differentials[0] if differentials else ""

        # --- S3 ---
        if "s3" in reuse and int(reuse.get("s3_max_k") or 0) == self.max_k:
            s3 = dict(reuse["s3"])
            stages["s3"] = s3
        elif self.s3_strict:
            s3_raw = self._call(
                "BackboneEntityFilterStrict",
                self.prompt_s3_strict,
                {
                    "case_context": {
                        "vignette": vignette[:2000],
                        "key_facts": list(s1.get("key_facts") or []),
                    },
                    "syndrome_frame": s1.get("syndrome_frame") or "",
                    "candidates": [
                        f"{i}. {d}" for i, d in enumerate(differentials)
                    ],
                    "max_k": self.max_k,
                },
            )
            calls += 1
            picked: list[str] = []
            n_invalid = 0
            for raw_idx in (s3_raw.get("shortlist_indices") or []):
                try:
                    idx = int(raw_idx)
                except (TypeError, ValueError):
                    n_invalid += 1
                    continue
                if 0 <= idx < len(differentials):
                    label = differentials[idx]
                    if label not in picked:
                        picked.append(label)
                else:
                    n_invalid += 1
            if not picked:
                picked = differentials[: self.max_k]
            shortlist = picked[: self.max_k]
            s3 = {
                "shortlist": shortlist,
                "max_k": self.max_k,
                "strict": True,
                "n_invalid_indices": n_invalid,
                "raw": s3_raw,
            }
            stages["s3"] = s3
            stages["s3_max_k"] = self.max_k
        else:
            s3_raw = self._call(
                "BackboneEntityFilter",
                self.prompt_s3,
                {
                    "case_context": {
                        "vignette": vignette[:2000],
                        "key_facts": list(s1.get("key_facts") or []),
                    },
                    "syndrome_frame": s1.get("syndrome_frame") or "",
                    "differentials": differentials,
                    "max_k": self.max_k,
                },
            )
            calls += 1
            shortlist = _as_str_list(s3_raw.get("shortlist"))
            if not shortlist:
                shortlist = differentials[: self.max_k]
            shortlist = shortlist[: self.max_k]
            s3 = {
                "shortlist": shortlist,
                "max_k": self.max_k,
                "raw": s3_raw,
            }
            stages["s3"] = s3
            stages["s3_max_k"] = self.max_k

        shortlist = list(s3.get("shortlist") or [])
        if not shortlist and differentials:
            shortlist = differentials[: self.max_k]
            stages["s3"]["shortlist"] = shortlist

        # --- S4 ---
        if skip_s4 or self.select_variant == "a":
            champion = shortlist[0] if shortlist else (anchor or "")
            s4 = {
                "variant": "a",
                "champion": champion,
                "llm_calls": 0,
                "rationale": "trivial first shortlist item",
            }
            stages["s4"] = s4
        elif "s4" in reuse and reuse.get("s4_variant") == self.select_variant:
            s4 = dict(reuse["s4"])
            stages["s4"] = s4
            champion = str(s4.get("champion") or "")
        elif self.select_variant == "h":
            facts = self._pick_facts(s1, vignette)
            calls += self._last_atomise_calls
            self._last_atomise_calls = 0
            cands = list(shortlist)
            numbered = [f"{i}. {c}" for i, c in enumerate(cands)]

            def _ordinal(fact: str) -> dict[str, str]:
                r = self._call(
                    "BackboneOrdinalEffects",
                    self.prompt_s4_ordinal,
                    {"fact": fact, "candidates": numbered},
                )
                raw = r.get("effects") or {}
                out: dict[str, str] = {}
                if isinstance(raw, Mapping):
                    for key, val in raw.items():
                        lab = str(val).strip().lower()
                        if lab not in ORDINAL_WEIGHTS:
                            continue
                        try:
                            idx = int(str(key).strip())
                        except (TypeError, ValueError):
                            resolved = _resolve_label(key, cands)
                            if resolved is None:
                                continue
                            idx = cands.index(resolved)
                        if 0 <= idx < len(cands):
                            out[cands[idx]] = lab
                return out

            with ThreadPoolExecutor(max_workers=self.s4_inner_workers) as pool:
                results = list(pool.map(_ordinal, facts))
            calls += len(facts)

            post = {c: 1.0 / len(cands) for c in cands} if cands else {}
            n_frozen = 0
            trace: list[dict] = []
            for fact, effects in zip(facts, results):
                # §13 discrimination gate: a fact whose labels are entirely
                # neutral/weak moves nothing. Without it, one weak_for on a
                # distractor bleeds every other candidate via renormalisation.
                discriminative = any(
                    lab in DISCRIMINATIVE_LABELS for lab in effects.values()
                )
                if not discriminative:
                    n_frozen += 1
                else:
                    raw = {
                        c: max(post[c], 1e-6) * ORDINAL_WEIGHTS.get(
                            effects.get(c, "neutral"), 1.0
                        )
                        for c in cands
                    }
                    total = sum(raw.values())
                    if total > 0:
                        post = {c: v / total for c, v in raw.items()}
                trace.append({"fact": fact, "effects": effects, "frozen": not discriminative})

            if cands:
                order = sorted(cands, key=lambda c: -post[c])
                champion = order[0]
                shortlist = order
                stages["s3"]["shortlist"] = shortlist
            else:
                champion = anchor
            s4 = {
                "variant": "h",
                "champion": champion,
                "llm_calls": len(facts),
                "n_facts": len(facts),
                "n_frozen": n_frozen,
                "posterior": {c: round(v, 4) for c, v in post.items()},
                "trace": trace,
            }
            stages["s4"] = s4
            stages["s4_variant"] = "h"
        elif self.select_variant == "g":
            facts = self._pick_facts(s1, vignette)
            cands = list(shortlist)

            def _ranked(fact: str) -> tuple[list[str], list[str], dict]:
                r = self._call(
                    "BackboneRuleInOutRanked",
                    self.prompt_s4_ranked,
                    {"fact": fact, "candidates": cands},
                )
                def _clean(key: str) -> list[str]:
                    out: list[str] = []
                    for v in (r.get(key) or [])[:3]:
                        lab = _resolve_label(v, cands)
                        if lab and lab not in out:
                            out.append(lab)
                    return out
                return _clean("rule_in"), _clean("rule_out"), r

            calls += self._last_atomise_calls
            self._last_atomise_calls = 0
            with ThreadPoolExecutor(max_workers=self.s4_inner_workers) as pool:
                results = list(pool.map(_ranked, facts))
            calls += len(facts)

            logodds = {c: 0.0 for c in cands}
            n_conflict = n_abstain = n_votes = 0
            trace: list[dict] = []
            for fact, (rin, rout, raw) in zip(facts, results):
                conflicts = set(rin) & set(rout)
                n_conflict += len(conflicts)
                rin = [c for c in rin if c not in conflicts]
                rout = [c for c in rout if c not in conflicts]
                if not rin and not rout:
                    n_abstain += 1
                for rank, c in enumerate(rin):
                    logodds[c] += ETA * RANK_CREDITS[rank]
                    n_votes += 1
                for rank, c in enumerate(rout):
                    logodds[c] -= ETA * RANK_CREDITS[rank]
                    n_votes += 1
                trace.append({"fact": fact, "rule_in": rin, "rule_out": rout})

            if cands:
                order = sorted(range(len(cands)), key=lambda j: -logodds[cands[j]])
                champion = cands[order[0]]
                shortlist = [cands[j] for j in order]
                stages["s3"]["shortlist"] = shortlist
            else:
                champion = anchor
            s4 = {
                "variant": "g",
                "champion": champion,
                "llm_calls": len(facts),
                "n_facts": len(facts),
                "n_conflict_cancelled": n_conflict,
                "n_abstain": n_abstain,
                "n_votes": n_votes,
                "logodds": {c: round(v, 3) for c, v in logodds.items()},
                "trace": trace,
            }
            stages["s4"] = s4
            stages["s4_variant"] = "g"
        elif self.select_variant in ("e", "f"):
            facts = self._pick_facts(s1, vignette)
            cands = list(shortlist)
            sep = self.select_variant == "e"

            def _one(fact: str) -> tuple[Optional[str], Optional[str], list[dict]]:
                payload = {"fact": fact, "candidates": cands}
                if not sep:
                    r = self._call(
                        "BackboneRuleInOutJoint", self.prompt_s4_joint, payload
                    )
                    return (
                        _resolve_label(r.get("favored"), cands),
                        _resolve_label(r.get("argues_against"), cands),
                        [{"fact": fact, "joint": r}],
                    )
                ri = self._call("BackboneRuleIn", self.prompt_s4_rulein, payload)
                ro = self._call("BackboneRuleOut", self.prompt_s4_ruleout, payload)
                return (
                    _resolve_label(ri.get("favored"), cands),
                    _resolve_label(ro.get("argues_against"), cands),
                    [{"fact": fact, "rule_in": ri, "rule_out": ro}],
                )

            calls += self._last_atomise_calls
            self._last_atomise_calls = 0
            with ThreadPoolExecutor(max_workers=self.s4_inner_workers) as pool:
                results = list(pool.map(_one, facts))
            calls += len(facts) * (2 if sep else 1)

            logodds = {c: 0.0 for c in cands}
            n_conflict = n_abstain = n_updates = 0
            trace: list[dict] = []
            for (fav, agn, tr) in results:
                if fav is not None and fav == agn:
                    n_conflict += 1
                    fav = agn = None
                if fav is None and agn is None:
                    n_abstain += 1
                else:
                    n_updates += 1
                if fav is not None:
                    logodds[fav] += ETA
                if agn is not None:
                    logodds[agn] -= ETA
                tr[0]["favored"] = fav
                tr[0]["argues_against"] = agn
                trace.extend(tr)

            if cands:
                order = sorted(range(len(cands)), key=lambda j: -logodds[cands[j]])
                champion = cands[order[0]]
                shortlist = [cands[j] for j in order]
                stages["s3"]["shortlist"] = shortlist
            else:
                champion = anchor
            s4 = {
                "variant": self.select_variant,
                "champion": champion,
                "llm_calls": len(facts) * (2 if sep else 1),
                "n_facts": len(facts),
                "separated": sep,
                "n_conflict_cancelled": n_conflict,
                "n_abstain": n_abstain,
                "n_effective_updates": n_updates,
                "logodds": {c: round(v, 3) for c, v in logodds.items()},
                "trace": trace,
            }
            stages["s4"] = s4
            stages["s4_variant"] = self.select_variant
        elif self.select_variant == "d":
            facts = list(s1.get("key_facts") or [])
            if not facts:
                facts = [
                    ln.strip()
                    for ln in vignette.replace(". ", ".\n").splitlines()
                    if len(ln.strip()) > 15
                ][:20]
            s4_raw = self._call(
                "BackboneSelectPerFact",
                self.prompt_s4d,
                {
                    "facts": [f"{i}. {f}" for i, f in enumerate(facts)],
                    "candidates": [
                        f"{i}. {c}" for i, c in enumerate(shortlist)
                    ],
                },
            )
            calls += 1
            totals = [0.0] * len(shortlist)
            n_rows = n_bad = 0
            for row in (s4_raw.get("effects") or []):
                if not isinstance(row, Mapping):
                    n_bad += 1
                    continue
                scores = row.get("scores") or []
                if len(scores) != len(shortlist):
                    n_bad += 1
                    continue
                n_rows += 1
                for j, sc in enumerate(scores):
                    try:
                        totals[j] += float(sc)
                    except (TypeError, ValueError):
                        pass
            if n_rows and shortlist:
                champion = shortlist[max(range(len(shortlist)), key=lambda j: totals[j])]
            else:
                champion = shortlist[0] if shortlist else anchor
            # deterministic re-ranking of the whole shortlist by accumulated score
            order = sorted(range(len(shortlist)), key=lambda j: -totals[j])
            shortlist = [shortlist[j] for j in order] or shortlist
            stages["s3"]["shortlist"] = shortlist
            s4 = {
                "variant": "d",
                "champion": champion,
                "llm_calls": 1,
                "n_fact_rows": n_rows,
                "n_bad_rows": n_bad,
                "totals": [round(t, 2) for t in sorted(totals, reverse=True)],
                "fell_back": not bool(n_rows),
                "raw": s4_raw,
            }
            stages["s4"] = s4
            stages["s4_variant"] = "d"
        else:
            if self.select_variant == "c":
                prompt = self.prompt_s4c
                module = "BackboneSelectGranularity"
                payload = {
                    "vignette": vignette[:2000],
                    "key_facts": list(s1.get("key_facts") or []),
                    "anchor_label": anchor or (shortlist[0] if shortlist else ""),
                    "shortlist": shortlist,
                }
            else:
                prompt = self.prompt_s4b
                module = "BackboneSelectFree"
                payload = {
                    "vignette": vignette[:2000],
                    "key_facts": list(s1.get("key_facts") or []),
                    "shortlist": shortlist,
                }
            s4_raw = self._call(module, prompt, payload)
            calls += 1
            champion = str(s4_raw.get("champion") or "").strip()
            # enforce membership in shortlist when possible
            if champion and shortlist and champion.casefold() not in {
                x.casefold() for x in shortlist
            }:
                # fuzzy: prefer exact shortlist match containing champion or vice versa
                matched = next(
                    (
                        x
                        for x in shortlist
                        if champion.casefold() in x.casefold()
                        or x.casefold() in champion.casefold()
                    ),
                    None,
                )
                champion = matched or shortlist[0]
            if not champion:
                champion = shortlist[0] if shortlist else anchor
            s4 = {
                "variant": self.select_variant,
                "champion": champion,
                "llm_calls": 1,
                "raw": s4_raw,
            }
            stages["s4"] = s4
            stages["s4_variant"] = self.select_variant

        ordered = []
        if champion:
            ordered.append(champion)
        for label in shortlist:
            if label.casefold() not in {x.casefold() for x in ordered}:
                ordered.append(label)

        return BackboneResult(
            case_id=case_id,
            champion=champion or "",
            ordered_diagnoses=ordered,
            stages=stages,
            llm_calls=calls,
            config={
                "select_variant": self.select_variant,
                "max_k": self.max_k,
                "entrance": self.entrance,
            },
        )


class KBRecallBridge:
    """Thin wrapper around case_report + cpg disease-name RRF (no LLM)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._cr = None
        self._cpg = None
        self._ready = False
        import threading
        self._lock = threading.Lock()

    def ensure(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            print("[KBRecallBridge] loading indexes (once)...", flush=True)
            from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
            from agentclinic_tree_dx.knowledge.case_report_source import (
                CaseReportBranchSource,
                build_case_report_vocab,
            )
            from agentclinic_tree_dx.knowledge.guideline_branch_source import (
                GuidelineBranchSource,
                build_disorder_vocab,
            )
            from agentclinic_tree_dx.knowledge.disease_name_resolver import (
                DiseaseNameResolver,
            )

            base = self.root / "data/knowledge_raw"
            vocab: set[str] = set()
            concepts = base / "snomed_concepts.json"
            if concepts.exists():
                vocab = build_disorder_vocab(
                    json.loads(concepts.read_text(encoding="utf-8"))
                )
            resolver = None
            try:
                resolver = DiseaseNameResolver()
                m2d = base / "mechanism_to_disease.json"
                if m2d.exists() and hasattr(resolver, "load_mechanism_map"):
                    resolver.load_mechanism_map(str(m2d))
            except Exception:
                resolver = None

            cr_idx = self.root / "data/corpus/case_report_index"
            if cr_idx.exists():
                retr = RAGRetriever(str(cr_idx), device="cpu")
                if retr.is_ready:
                    cr_vocab = set(vocab)
                    norm_path = self.root / "data/case_reports/case_reports.jsonl"
                    if norm_path.exists():
                        cr_vocab |= build_case_report_vocab(norm_path)
                    self._cr = CaseReportBranchSource(
                        retr, cr_vocab, resolver=resolver, top_k=20
                    )
            cpg_idx = self.root / "data/corpus/cpg_index"
            if cpg_idx.exists():
                retr = RAGRetriever(str(cpg_idx), device="cpu")
                if retr.is_ready:
                    self._cpg = GuidelineBranchSource(
                        retr, vocab, resolver=resolver, top_k=20
                    )
            self._ready = True
            print(
                f"[KBRecallBridge] ready cr={self._cr is not None} "
                f"cpg={self._cpg is not None}",
                flush=True,
            )

    def recall(
        self,
        *,
        syndrome: str,
        salient: Sequence[str],
        context: str,
        case_summary: str = "",
        cap: int = 24,
    ) -> tuple[list[str], dict[str, Any]]:
        self.ensure()
        from agentclinic_tree_dx.knowledge.guideline_branch_source import (
            GuidelineBranchSource,
        )

        named: list[tuple[str, dict[str, float]]] = []
        retrieval_calls = 0
        for name, src in (("case_report", self._cr), ("cpg", self._cpg)):
            if src is None:
                continue
            ranking = src.recall(
                syndrome,
                context=context or case_summary,
                salient_findings=list(salient or []),
                finding_entrance_weight=1.0,
                top_k=12,
            )
            retrieval_calls += 1
            named.append((name, ranking or {}))
        fused = GuidelineBranchSource._rrf_merge(
            [dict(r) for _, r in named], k=60
        )
        ranked = [
            d
            for d, _ in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        ][:cap]
        return ranked, {
            "retrieval_calls": retrieval_calls,
            "n_sources": len(named),
            "n_fused": len(ranked),
        }
