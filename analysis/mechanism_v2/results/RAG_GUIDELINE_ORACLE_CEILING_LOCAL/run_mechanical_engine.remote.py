#!/usr/bin/env python3
"""Stage 3: rank the candidate hypotheses with no model in the loop.

Implements the four-layer algorithm from MECHANICAL_RULE_FEASIBILITY.md 2.4 on
the extracted assertions and findings.  Every decision is a comparison between
schema fields, so the elimination chain it prints is the decision flow.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

MODALITY_W = {"obligatory": 1.0, "typical": 0.8, "frequent": 0.6,
              "occasional": 0.35, "rare": 0.15}
DEFAULT_W = 0.5

# contexts whose assertions may not drive layer 1 or 2: a differential list
# co-mentions diseases without asserting features of them, and a table row may
# be an artefact of two neighbouring rows.
SOFT_CONTEXTS = {"differential", "table_row", "epidemiology", "treatment", "prognosis"}

GENERIC = {
    "disease", "syndrome", "disorder", "condition", "patient", "patients",
    "finding", "findings", "presence", "absence", "level", "levels", "sign",
    "signs", "symptom", "symptoms", "history", "type", "form", "feature",
    "features", "normal", "abnormal", "increased", "decreased", "high", "low",
    "the", "and", "with", "without", "of", "in", "a", "an", "or", "for", "to",
}


def norm(s: str) -> str:
    s = re.sub(r"\s*\([^)]*\)", " ", str(s or ""))
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = re.sub(r"[^a-zA-Z0-9\s]", " ", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> set[str]:
    out = set()
    for w in norm(s).split():
        if w in GENERIC or len(w) < 3:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


JOIN_MODE = "strict"
DISCRIMINATIVE_ONLY = False

# How much a matched finding is worth as a function of how many candidates in
# this case's own hypothesis list claim it.  "none" is the plain sum that made
# the engine degenerate into a coverage count; the rest are specificity weights
# computed inside the candidate set, not over the corpus.
WEIGHT_SCHEME = "none"
USE_CRITERION_GROUPS = False
CLOSED_WORLD = False

# --- section 8 fixes, each independently switchable ------------------------
FIX_MARKER = False        # F2a: a shared alphanumeric marker token (p63, CD34) joins
FIX_EMBED_TAU = 0.0       # F2b: sentence-encoder fallback for the predicate join
FIX_ORGANISM = False      # F3 : Brucella <-> Brucellosis via medical stemming
FIX_ENUM = False          # F5a: relations that are really context types
CORPUS_LR = None          # F1 : {(candidate, finding) -> log likelihood ratio}
FIX_ANCHOR_EMBED = False  # F2c: require lexical anchoring before trusting the encoder
GROUP_ALL_IS_REQUIRED = False  # F4b: an `all` group is itself the requirement
FIX_QUOTE_GATE = False    # F7: demote/drop assertions that misrepresent their quote

# Layers 1 and 2 were scoped down when the relation labels were unreliable, so
# almost nothing reaches them and layer 3 decides every ranking.  These flags
# reopen each restriction one at a time; all default off so recorded results
# stand.  See §19 for what each one actually fires on.
RIGID_REQUIRED_ANY_MODALITY = False   # veto on required_for regardless of modality
RIGID_SUFFICIENT_CONFIRMS = False     # sufficient_for + present -> layer 2
RIGID_PATHO_READS_THRESHOLD = False   # a violated cutoff blocks the confirmation
RIGID_REQUIRED_CLOSED_WORLD = False   # a necessity that never joined counts as absent
FIX_NLI = False           # F8: NLI entailment check on high-stakes relations

# F9. When the gate rules that a predicate names a procedure or a treatment
# rather than a diagnostic criterion, it demotes the assertion into a scoring
# slot, so the verdict "this is not a criterion" is discarded at the moment it
# is reached and the row goes on adding score at layer 3.  This makes the
# verdict stick.  See §20.
NONCRITERION_INERT = False
NONCRITERION_GATES = ("E4_procedure_not_finding", "E10_treatment_required")

# F10. A finding is one fact about the patient, but layer 3 scores it once per
# assertion that mentions it, so a candidate with more guideline sentences about
# the same finding outscores one with fewer.  68% of scoring rows are repeat
# votes this way.  Repetition is not worthless -- several guidelines saying the
# same thing is weak evidence of consensus -- so instead of collapsing a pair to
# one vote, its summed delta is divided by n**FINDING_POOL_BETA: 0.0 leaves
# today's behaviour untouched, 1.0 reduces the pair to its mean.
FINDING_POOL_BETA = 0.0

# Oracle probe, not a fix: rows a clinician judged unable to separate this
# disease from its competitors.  Filling this from the audit labels measures
# what a perfect usefulness filter would be worth before anyone builds one.
LAYER3_DROP: set[tuple] = set()

_EMB: dict[str, Any] | None = None


def _embeddings() -> dict[str, Any]:
    global _EMB
    if _EMB is None:
        import numpy as np

        d = np.load(LEDGER / "join_embeddings.npz", allow_pickle=True)
        strings = list(d["strings"])
        _EMB = {"idx": {s: i for i, s in enumerate(strings)}, "emb": d["emb"]}
    return _EMB


def embed_sim(a: str, b: str) -> float:
    e = _embeddings()
    ia, ib = e["idx"].get(a.strip()), e["idx"].get(b.strip())
    if ia is None or ib is None:
        return 0.0
    return float(e["emb"][ia] @ e["emb"][ib])


MARKER_RE = re.compile(r"^(?:[a-z]{1,5}\d{1,3}[a-z]?|\d{1,3}[a-z]{1,3})$")


def markers(s: str) -> set[str]:
    """Immunohistochemical and molecular marker tokens: p63, CD34, Fli1, Ki67."""
    return {t.replace("-", "") for t in norm(s).split() if MARKER_RE.match(t.replace("-", ""))}


# Suffixes that turn an organism into the disease it causes, or a noun into its
# plural.  Stripping them lets "Brucella" bind to the candidate "Brucellosis".
MED_SUFFIXES = ("elloses", "ellosis", "iases", "iasis", "osis", "oses", "ae", "a", "s")


def med_stem(s: str) -> str:
    w = norm(s)
    if " " in w or len(w) < 6:
        return w
    for suf in MED_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 5:
            return w[: -len(suf)]
    return w


# Values the extractor writes into `relation` that are really context types.
# 475.a died here: "Neuralgic Amyotrophy (Parsonage-Turner)" came back with
# relation="definition", which no rule can consume.
RELATION_IS_CONTEXT = {
    "definition", "criteria", "differential", "histopathology", "imaging",
    "epidemiology", "treatment", "prognosis", "table_row", "pathophysiology",
    "anatomy", "diagnosis", "clinical", "complications", "course", "other",
}
RELATION_ALIASES = {
    "associated_with": "feature_of", "risk_factor_for": "caused_by",
    "presents_with": "feature_of", "characterized_by": "feature_of",
    "indicates": "feature_of", "suggests": "feature_of",
    "diagnosed_by": "feature_of", "includes": "variant_of",
    "subtype_of": "variant_of", "same_as": "synonym_of",
    "also_known_as": "synonym_of", "equivalent_to": "synonym_of",
}
LEGAL_RELATIONS = {
    "feature_of", "required_for", "sufficient_for", "pathognomonic_for",
    "excludes", "argues_against", "distinguishes_from", "variant_of",
    "synonym_of", "caused_by", "treated_by",
}


def clamp_relation(a: dict) -> dict:
    """F5a. Move out-of-enum relations to context_type or to their nearest legal
    value, instead of dropping the assertion on the floor."""
    rel = re.sub(r"[\s-]+", "_", (a.get("relation") or "").strip().lower())
    if rel in LEGAL_RELATIONS:
        return a
    a = dict(a)
    if rel in RELATION_ALIASES:
        a["relation"] = RELATION_ALIASES[rel]
    elif rel in RELATION_IS_CONTEXT:
        if not (a.get("context_type") or "").strip():
            a["context_type"] = rel
        a["relation"] = "feature_of"
    else:
        a["relation"] = "feature_of"
    a["_relation_clamped"] = rel
    return a


def specificity(n_claimants: int, n_candidates: int) -> float:
    c = max(int(n_claimants), 1)
    if WEIGHT_SCHEME == "none":
        return 1.0
    if WEIGHT_SCHEME == "binary":
        return 1.0 if c == 1 else 0.0
    if WEIGHT_SCHEME == "inv":
        return 1.0 / c
    if WEIGHT_SCHEME == "inv2":
        return 1.0 / (c * c)
    if WEIGHT_SCHEME == "k1bonus":
        # the pair-level test found gold enriched only at k == 1; the apparent
        # enrichment at large k is an artefact of coarse gold labels, so the
        # weight is a uniqueness bonus rather than a monotone decay
        return 2.0 if c == 1 else 1.0
    if WEIGHT_SCHEME == "idf":
        import math
        return math.log((n_candidates + 1) / (c + 0.5))
    raise ValueError(WEIGHT_SCHEME)


LR_CLIP = 1.0


def lr_weight(candidate: str, finding: str) -> float:
    """F1.  Corpus-side discriminativeness: how much more often this finding is
    stated in documents about this candidate than about the average candidate in
    the same case.  Returns a multiplier on the positive contribution, so a
    feature every competitor also has (syncope, fever) shrinks instead of
    counting once per candidate."""
    if not CORPUS_LR:
        return 1.0
    v = CORPUS_LR.get(f"{norm(candidate)}||{norm(finding)}")
    if v is None:
        return 1.0
    import math

    return math.exp(max(-LR_CLIP, min(LR_CLIP, float(v))))


def concept_match(a: str, b: str) -> str:
    """Deterministic join used both for subject->candidate and predicate->finding."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return ""
    if na == nb:
        return "exact"
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return ""
    if ta <= tb or tb <= ta:
        return "containment"
    inter = ta & tb
    if inter and len(inter) / len(ta | tb) >= 0.5:
        return "overlap"
    if JOIN_MODE == "loose" and inter:
        # a shared marker token such as p63 or cd34 carries the whole match;
        # "p63 positivity" vs "p63 staining" is Jaccard 0.33 and fails above.
        if any(re.search(r"\d", t) for t in inter) or len(inter) / len(ta | tb) >= 0.25:
            return "loose"
    return ""


def subject_match(a: str, b: str) -> str:
    """Assertion subject -> candidate label.  Deliberately does not use the
    encoder: 91's candidate is labelled "Hemangioma" with "Angiosarcoma" in its
    alias list, and a similarity join would glue benign and malignant together."""
    m = concept_match(a, b)
    if m:
        return m
    if FIX_ORGANISM:
        sa, sb = med_stem(a), med_stem(b)
        if sa and sb and len(sa) >= 5 and len(sb) >= 5 and (sa == sb or sa.startswith(sb)
                                                            or sb.startswith(sa)):
            return "med_stem"
    return ""


def predicate_match(a: str, b: str) -> str:
    """Assertion predicate -> case finding."""
    m = concept_match(a, b)
    if m:
        return m
    if FIX_MARKER:
        ma, mb = markers(a), markers(b)
        if ma & mb:
            return "marker"
    if FIX_EMBED_TAU and embed_sim(a, b) >= FIX_EMBED_TAU:
        # Ungated, the encoder joins echolalia to echopraxia and dyskeratosis to
        # hyperkeratosis: MiniLM scores morphological neighbours high, and in
        # clinical text those are precisely the pairs that must stay apart.
        # Anchoring demands a shared content token, marker, or word stem, so the
        # encoder only decides *whether* two lexically related phrases mean the
        # same thing, never invents a relation between unrelated ones.
        if not FIX_ANCHOR_EMBED or _anchored(a, b):
            return "embed"
    return ""


def _anchored(a: str, b: str) -> bool:
    ta, tb = tokens(a), tokens(b)
    if ta & tb or markers(a) & markers(b):
        return True
    for x in ta:
        for y in tb:
            if len(x) >= 5 and len(y) >= 5 and (x.startswith(y[:5]) or y.startswith(x[:5])):
                # cyanotic/cyanosis share six characters; echolalia/echopraxia
                # share four and are rejected.
                n = len(_common_prefix(x, y))
                if n >= 6 or (n >= 5 and abs(len(x) - len(y)) <= 3):
                    return True
    return False


def _common_prefix(x: str, y: str) -> str:
    i = 0
    while i < min(len(x), len(y)) and x[i] == y[i]:
        i += 1
    return x[:i]


def threshold_ok(assertion: dict, finding: dict) -> tuple[bool | None, str]:
    """None when the comparison cannot be made at all."""
    th = assertion.get("threshold") or {}
    op, val = th.get("operator"), th.get("value")
    fv = (finding.get("value") or {}).get("number")
    if op in (None, "null", "") or val is None or fv is None:
        return None, "no_numeric_pair"
    try:
        val = float(val)
        fv = float(fv)
    except (TypeError, ValueError):
        return None, "unparseable"
    unit_a = (th.get("unit") or "").lower().strip()
    unit_f = ((finding.get("value") or {}).get("unit") or "").lower().strip()
    if unit_a and unit_f and unit_a != unit_f:
        aliases = (
            {"ms", "msec", "millisecond", "milliseconds"},
            {"s", "sec", "second", "seconds"},
            {"mmhg", "mm hg"},
        )
        compatible = any(unit_a in g and unit_f in g for g in aliases)
        if not compatible:
            return None, f"unit_mismatch:{unit_a}/{unit_f}"
    ok = {"<": fv < val, "<=": fv <= val, ">": fv > val, ">=": fv >= val,
          "=": fv == val}.get(op)
    if ok is None and op == "range":
        hi = th.get("value_high")
        ok = hi is not None and val <= fv <= float(hi)
    if ok is None:
        return None, f"unknown_operator:{op}"
    return bool(ok), f"{fv}{unit_f} {op} {val}{unit_a}"


def run_case(task: dict, extraction: dict) -> dict:
    findings = [f for f in extraction["findings"] if isinstance(f, dict) and f.get("label")]
    assertions = [a for a in extraction["assertions"] if isinstance(a, dict)]
    if FIX_ENUM:
        assertions = [clamp_relation(a) for a in assertions]
    if FIX_QUOTE_GATE or FIX_NLI:
        from gate_assertions import gate_assertions
        assertions = gate_assertions(assertions, apply_nli=FIX_NLI)
    candidates = task["candidates"]

    # ---- bind assertion subjects to candidates ---------------------------
    bound: dict[str, list[dict]] = defaultdict(list)
    unbound = 0
    for a in assertions:
        hit = None
        for cand in candidates:
            names = [cand["label"], *(cand.get("aliases") or [])]
            for name in names:
                m = subject_match(a["subject"], name)
                if m:
                    hit = (cand["label"], m)
                    break
            if hit:
                break
        if hit is None:
            unbound += 1
            continue
        a = dict(a)
        a["_bind"] = hit[1]
        bound[hit[0]].append(a)

    # ---- dedupe at assertion level, not passage level --------------------
    for label, items in list(bound.items()):
        seen: dict[tuple, dict] = {}
        for a in items:
            k = (norm(a.get("predicate")), a.get("relation"), a.get("polarity"))
            prev = seen.get(k)
            if prev is None:
                a["_support"] = 1
                seen[k] = a
            else:
                prev["_support"] += 1
                if MODALITY_W.get(a.get("modality"), DEFAULT_W) > \
                        MODALITY_W.get(prev.get("modality"), DEFAULT_W):
                    prev["modality"] = a.get("modality")
        bound[label] = list(seen.values())

    # ---- bind predicates to findings -------------------------------------
    join_stats = {"matched": 0, "unmatched": 0}
    for label, items in bound.items():
        for a in items:
            best = None
            for f in findings:
                for side in (f.get("canonical"), f.get("label")):
                    m = predicate_match(a["predicate"], side or "")
                    if m:
                        rank = {"exact": 0, "containment": 1, "overlap": 2,
                                "marker": 3, "loose": 4, "embed": 5}[m]
                        if best is None or rank < best[0]:
                            best = (rank, f, m)
                        break
            if best:
                a["_finding"] = best[1]
                a["_join"] = best[2]
                join_stats["matched"] += 1
            else:
                a["_finding"] = None
                join_stats["unmatched"] += 1

    # how many candidates claim each finding as their own feature?  A finding
    # claimed by everyone carries no separating power, and summing over such
    # findings is what turns the score into a coverage count.
    claimants: dict[str, set[str]] = defaultdict(set)
    for label, items in bound.items():
        for a in items:
            f = a.get("_finding")
            if f is not None and (a.get("polarity") or "asserted") == "asserted":
                claimants[norm(f.get("label"))].add(label)

    # ---- criterion groups -------------------------------------------------
    # Members of one criterion set are evaluated together and contribute once,
    # instead of once each: summing them is what let a well-documented
    # competitor outscore the gold on sheer feature count.
    groups: dict[str, dict[tuple, list[dict]]] = defaultdict(lambda: defaultdict(list))
    if USE_CRITERION_GROUPS:
        for label, items in bound.items():
            for a in items:
                cg = a.get("criterion_group") or {}
                gid = cg.get("group_id")
                if not gid or cg.get("logic") not in {"all", "any", "at_least_n"}:
                    continue
                key = (a.get("_title"), a.get("_section"), a.get("_focus"), gid, norm(a["subject"]))
                groups[label][key].append(a)
        for label in list(groups):
            for key in list(groups[label]):
                if len(groups[label][key]) < 2:
                    del groups[label][key]
        grouped_ids = {id(a) for label in groups for key in groups[label] for a in groups[label][key]}
    else:
        grouped_ids = set()

    # ---- four layers ------------------------------------------------------
    verdicts = {}
    for cand in candidates:
        label = cand["label"]
        items = bound.get(label, [])
        eliminated: list[dict] = []
        confirmed: list[dict] = []
        score = 0.0
        contributions: list[dict] = []
        pooled: dict[str, tuple[float, int]] = {}   # F10: layer-3 votes per finding

        for key, members in groups.get(label, {}).items():
            cg = members[0].get("criterion_group") or {}
            logic = cg.get("logic")
            size = len(members)
            need = cg.get("n") if isinstance(cg.get("n"), int) else None
            sat = [m for m in members
                   if m.get("_finding") and m["_finding"].get("polarity") == "present"]
            vio = [m for m in members
                   if m.get("_finding") and m["_finding"].get("polarity") in {"absent", "normal"}]
            if not sat and not vio:
                continue
            w = max(MODALITY_W.get((m.get("modality") or "").lower(), DEFAULT_W) for m in members)
            spec = max((specificity(len(claimants.get(norm(m["_finding"].get("label")), ())) or 1,
                                    len(candidates)) * lr_weight(label, m["_finding"].get("label"))
                        for m in sat), default=1.0)
            required = any((m.get("relation") or "") == "required_for"
                           and (m.get("modality") or "").lower() == "obligatory" for m in members)
            if GROUP_ALL_IS_REQUIRED and logic == "all":
                # Diagnostic criteria are written as features of the disease, not
                # as requirements: Kanavel's four signs come back as
                # feature_of/typical, so the required_for+obligatory gate never
                # opens.  `all` already says every member must hold; keying the
                # gate on the group logic is what makes the group executable.
                required = True
            ctxs = {(m.get("context_type") or "").lower() for m in members}
            soft_group = ctxs <= SOFT_CONTEXTS

            if logic == "all":
                target = need or size
                met = len(sat) >= target and not vio
                if CLOSED_WORLD and not vio and len(sat) < target:
                    # a member the vignette never mentions is read as absent.
                    # The 257 flow ("only one of Kanavel's four signs is met")
                    # needs this: the case states the tenderness and is silent
                    # about the other three rather than denying them.
                    vio = [m for m in members if not m.get("_finding")]
                if vio and required and not soft_group:
                    eliminated.append({"layer": 1, "rule": "criterion_group_violated",
                                       "group": f"{logic}/{need or size}",
                                       "missing": [m["predicate"] for m in vio][:4],
                                       "satisfied": [m["predicate"] for m in sat][:4],
                                       "quote": members[0].get("quote")})
                    continue
                delta = w * spec * (1.0 if met else (len(sat) / target - 0.5 * len(vio)))
            elif logic == "at_least_n":
                target = need or 1
                delta = w * spec * (1.0 if len(sat) >= target else len(sat) / target * 0.5)
            else:                                   # "any"
                delta = w * spec * (1.0 if sat else 0.0)
            if delta:
                score += round(delta, 3)
                contributions.append({"why": f"group:{logic}/{need or size}", "delta": round(delta, 3),
                                      "n_members": size, "n_satisfied": len(sat),
                                      "n_violated": len(vio),
                                      "predicate": members[0]["predicate"]})

        for a in items:
            if id(a) in grouped_ids:
                continue                            # already scored as part of its group
            ctx = (a.get("context_type") or "").lower()
            soft = ctx in SOFT_CONTEXTS
            rel = (a.get("relation") or "").lower()
            pol = (a.get("polarity") or "asserted").lower()
            w = MODALITY_W.get((a.get("modality") or "").lower(), DEFAULT_W)
            f = a.get("_finding")

            # layer 1: hard constraints
            if not soft and pol == "asserted":
                obligatory = (a.get("modality") or "").lower() == "obligatory"
                if rel == "required_for" and (obligatory or RIGID_REQUIRED_ANY_MODALITY):
                    if f is not None:
                        ok, why = threshold_ok(a, f)
                        if f.get("polarity") in {"absent", "normal"}:
                            eliminated.append({"layer": 1, "rule": "required_but_absent",
                                               "predicate": a["predicate"], "quote": a.get("quote"),
                                               "finding": f["label"], "finding_polarity": f["polarity"]})
                            continue
                        if ok is False:
                            eliminated.append({"layer": 1, "rule": "threshold_violated",
                                               "predicate": a["predicate"], "quote": a.get("quote"),
                                               "finding": f["label"], "comparison": why})
                            continue
                    elif RIGID_REQUIRED_CLOSED_WORLD:
                        eliminated.append({"layer": 1, "rule": "required_never_joined",
                                           "predicate": a["predicate"], "quote": a.get("quote")})
                        continue
                if rel in {"excludes", "argues_against"} and f is not None:
                    if f.get("polarity") == "present":
                        eliminated.append({"layer": 1, "rule": "exclusion_triggered",
                                           "predicate": a["predicate"], "quote": a.get("quote"),
                                           "finding": f["label"]})
                        continue

            # layer 2: confirmation
            confirming = rel == "pathognomonic_for" or (
                RIGID_SUFFICIENT_CONFIRMS and rel == "sufficient_for")
            if not soft and confirming and pol == "asserted" \
                    and f is not None and f.get("polarity") == "present":
                cutoff_met = True
                if RIGID_PATHO_READS_THRESHOLD:
                    cutoff_met = threshold_ok(a, f)[0] is not False
                if cutoff_met:
                    confirmed.append({"layer": 2, "predicate": a["predicate"],
                                      "quote": a.get("quote"), "finding": f["label"]})
                    score += 2.0
                    contributions.append({"why": rel, "delta": 2.0,
                                          "predicate": a["predicate"],
                                          "finding": f["label"]})
                    continue

            # layer 3: weighted feature agreement
            if f is None or soft:
                continue
            if NONCRITERION_INERT and any(
                    g in (a.get("_gate") or "") for g in NONCRITERION_GATES):
                continue
            if LAYER3_DROP and (label, (a.get("relation") or "").lower(),
                                norm(a.get("predicate")),
                                (a.get("quote") or "")[:60]) in LAYER3_DROP:
                continue
            fp = f.get("polarity")
            delta = 0.0
            if pol == "asserted":
                if fp == "present":
                    delta = w
                elif fp in {"absent", "normal"}:
                    delta = -0.5 * w
            else:  # the guideline negates this feature for this disease
                if fp == "present":
                    delta = -w
                elif fp in {"absent", "normal"}:
                    delta = 0.3 * w
            ok, why = threshold_ok(a, f)
            if ok is False:
                delta -= 0.5 * w
            elif ok is True:
                delta += 0.5 * w
            n_claim = len(claimants.get(norm(f.get("label")), ())) or 1
            if delta > 0:
                # a finding every candidate claims separates nothing, so it is
                # discounted by how many candidates claim it
                delta *= specificity(n_claim, len(candidates))
                delta *= lr_weight(label, f.get("label"))
            if delta:
                if FINDING_POOL_BETA:
                    fk = norm(f.get("label"))
                    tot, n_votes = pooled.get(fk, (0.0, 0))
                    pooled[fk] = (tot + delta, n_votes + 1)
                else:
                    score += delta
                contributions.append({"why": f"{rel}/{pol}/{fp}", "delta": round(delta, 3),
                                      "predicate": a["predicate"], "finding": f["label"],
                                      "n_claimants": n_claim,
                                      "threshold": why if ok is not None else None})

        if FINDING_POOL_BETA:
            score += sum(tot / (n ** FINDING_POOL_BETA)
                         for tot, n in pooled.values())

        verdicts[label] = {
            "label": label, "n_assertions": len(items),
            "n_joined": sum(1 for a in items if a.get("_finding")),
            "eliminated": eliminated, "confirmed": confirmed,
            "score": round(score, 3), "contributions": contributions[:25],
            "gold_match": cand["gold_match"], "methods": cand["methods"],
        }

    # layer 4: directional comparison among survivors
    survivors = [v for v in verdicts.values() if not v["eliminated"]]
    for label, items in bound.items():
        if label not in {s["label"] for s in survivors}:
            continue
        for a in items:
            comp = a.get("comparator")
            if not comp or (a.get("relation") or "") not in {"distinguishes_from", "argues_against"}:
                continue
            f = a.get("_finding")
            if f is None or f.get("polarity") != "present":
                continue
            for other in survivors:
                if other["label"] != label and concept_match(comp, other["label"]):
                    other["score"] = round(other["score"] - 0.5, 3)
                    other.setdefault("layer4_penalties", []).append(
                        {"from": label, "predicate": a["predicate"]})

    # every joined (candidate, finding) pair, untruncated, for the specificity
    # analysis: is a finding claimed by few candidates more often the gold's?
    pairs = []
    for label, items in bound.items():
        for a in items:
            f = a.get("_finding")
            if f is None:
                continue
            pairs.append({
                "candidate": label,
                "finding": f.get("label"),
                "finding_polarity": f.get("polarity"),
                "n_claimants": len(claimants.get(norm(f.get("label")), ())) or 1,
                "relation": a.get("relation"),
                "polarity": a.get("polarity"),
                "modality": a.get("modality"),
                "context_type": a.get("context_type"),
                "join": a.get("_join"),
            })

    ranked = sorted(verdicts.values(),
                    key=lambda v: (bool(v["eliminated"]), -len(v["confirmed"]), -v["score"]))
    gold_labels = set(task["gold_labels_in_set"])
    top1 = ranked[0]["label"] if ranked else ""
    return {
        "case_key": task["case_key"],
        "gold": task["gold"],
        "gold_labels_in_set": sorted(gold_labels),
        "n_findings": len(findings),
        "n_assertions": len(assertions),
        "n_assertions_bound": sum(len(v) for v in bound.values()),
        "n_assertions_unbound": unbound,
        "join_stats": join_stats,
        "top1": top1,
        "top1_is_gold": top1 in gold_labels,
        "gold_rank": next((i + 1 for i, v in enumerate(ranked) if v["label"] in gold_labels), None),
        "gold_eliminated": [v["label"] for v in ranked
                            if v["label"] in gold_labels and v["eliminated"]],
        "ranking": ranked,
        "pairs": pairs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30")
    ap.add_argument("--suffix", default="")
    ap.add_argument("--join", choices=["strict", "loose"], default="strict")
    ap.add_argument("--discriminative-only", action="store_true",
                    help="score only findings claimed by a single candidate")
    ap.add_argument("--weight", default="none")
    ap.add_argument("--groups", action="store_true")
    ap.add_argument("--closed-world", action="store_true")
    ap.add_argument("--marker", action="store_true", help="F2a")
    ap.add_argument("--embed-tau", type=float, default=0.0, help="F2b")
    ap.add_argument("--organism", action="store_true", help="F3")
    ap.add_argument("--enum-clamp", action="store_true", help="F5a")
    ap.add_argument("--anchor-embed", action="store_true", help="F2c")
    ap.add_argument("--group-all-required", action="store_true", help="F4b")
    ap.add_argument("--quote-gate", action="store_true", help="F7: quote/modality/patho gates")
    ap.add_argument("--nli", action="store_true", help="F8: NLI on high-stakes relations")
    ap.add_argument("--corpus-lr", default="", help="F1: path to the lift table")
    ap.add_argument("--tasks", default="trial_tasks_11.json", help="F6: expanded candidate sets")
    args = ap.parse_args()
    global JOIN_MODE, DISCRIMINATIVE_ONLY, WEIGHT_SCHEME, USE_CRITERION_GROUPS
    global CLOSED_WORLD, FIX_MARKER, FIX_EMBED_TAU, FIX_ORGANISM, FIX_ENUM, CORPUS_LR
    global FIX_ANCHOR_EMBED, GROUP_ALL_IS_REQUIRED, FIX_QUOTE_GATE, FIX_NLI
    FIX_ANCHOR_EMBED = args.anchor_embed
    GROUP_ALL_IS_REQUIRED = args.group_all_required
    FIX_QUOTE_GATE = args.quote_gate
    FIX_NLI = args.nli
    JOIN_MODE = args.join
    DISCRIMINATIVE_ONLY = args.discriminative_only
    WEIGHT_SCHEME = args.weight
    USE_CRITERION_GROUPS = args.groups
    CLOSED_WORLD = args.closed_world
    FIX_MARKER = args.marker
    FIX_EMBED_TAU = args.embed_tau
    FIX_ORGANISM = args.organism
    FIX_ENUM = args.enum_clamp
    if args.corpus_lr:
        CORPUS_LR = json.loads((LEDGER / args.corpus_lr).read_text("utf-8"))
    tag = (f"{args.arm}{args.suffix}"
           + ("_loose" if args.join == "loose" else "")
           + ("_disc" if args.discriminative_only else ""))

    tasks = {t["case_key"]: t for t in json.loads((LEDGER / args.tasks).read_text("utf-8"))}
    extraction = {e["case_key"]: e for e in
                  json.loads((LEDGER / f"trial_extraction_{args.arm}{args.suffix}.json").read_text("utf-8"))}

    out: list[dict[str, Any]] = []
    for key, task in tasks.items():
        out.append(run_case(task, extraction[key]))

    path = LEDGER / f"trial_engine_{tag}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    n_ok = sum(1 for o in out if o["top1_is_gold"])
    print(f"arm={tag}  top1 gold-equivalent: {n_ok}/{len(out)}\n")
    for o in out:
        flag = "OK " if o["top1_is_gold"] else "   "
        print(f"{flag}{o['case_key']:24s} top1={o['top1'][:38]:38s} gold_rank={o['gold_rank']} "
              f"elim_gold={o['gold_eliminated']} join={o['join_stats']['matched']}/"
              f"{o['join_stats']['matched']+o['join_stats']['unmatched']}")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
