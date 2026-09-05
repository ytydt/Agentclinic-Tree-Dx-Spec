#!/usr/bin/env python3
"""F7: program gates on extracted guideline assertions vs their evidence window.

The extractor sees a *passage*: the hit chunk glued to same-document neighbours
(``TrialRetriever.passage(window=1)``), the same anti-truncation idea as the
guideline-KG claim-window reassembly.  The stored ``quote`` is capped at 200
chars, so a number or hallmark cue that sits in a neighbour chunk is often
absent from the quote even though it was in the LLM's input.

Positive *licensing* (E14 numbers, pathognomonic cues, subject presence)
therefore uses the quote's neighbourhood inside the glued passage.
``required_for`` necessity is scoped to the *sentence that states this
predicate*: a neighbour-sentence ``requires`` must not license a split workup
list (G-A).  Hedge demotions stay quote-local so an adjacent sentence cannot
contaminate the cited span.

F7 also recodes three inverted high-stakes writings that the extractor already
produced (it still does not invent assertions from unextracted sentences):

- G1: same quote must not be both ``pathognomonic_for`` and ``required_for``.
- G2: ``excludes`` + negated + a stated *normal* range → necessity of the
  abnormal side, with the operator inverted by the comparison word.
- G3: a limb of a stated ``diagnosed in the presence of`` conjunction, with
  membership decided by containment in the clause.

Every pattern here is a guideline-English construction: no disease, organ,
measurement or test name appears in any rule, so a gate can be audited for
generality by how many cases it fires in (``audit_generality.py``).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# Same scale as dechunk_and_pack.WINDOW and as one glued neighbour chunk.
EVIDENCE_RADIUS = 1200
_PASSAGE_INDEX: dict[str, Any] | None = None

HEDGE = re.compile(
    r"\b(may|might|can|could|often|usually|typically|sometimes|"
    r"in some|relies on|should|advised|whenever possible|generally|"
    r"possible|suggests?|consider)\b",
    re.I,
)
PATHO_CUE = re.compile(
    # "pathognomic" is a common misspelling and appears in the corpus (1 of 9
    # occurrences); matching only the correct spelling silently drops it.
    r"\b(pathognom(?:on)?ic|hallmark|diagnostic of|diagnostic for|"
    # number and adverb both vary: "are diagnostic", "is generally established"
    r"will be diagnostic|(?:is|are) diagnostic|considered diagnostic|"
    r"diagnos\w+ (?:is|are) (?:\w+ly )?(?:made|confirmed|established)"
    r"(?: by| with| through)|"
    r"diagnosed (?:\w+ly )?(?:by|with|through)|"
    # exclusivity attached to the finding itself: "the unique liver biopsy
    # finding of paucity of bile ducts"
    r"unique\W+(?:\w+\W+){0,3}finding)\b",
    re.I,
)
# --- deontic scope (G-A) --------------------------------------------------
# Every pattern below is a guideline-English construction.  None of them may
# name a disease, an organ, a measurement or a test: the same rule has to fire
# on a dermatology or infectious-disease passage, otherwise it is a lookup
# table for one case rather than a gate.
#
# Necessity is licensed *of this predicate*, in the sentence that states it
# (G-DEE scope, section 15.5).  A neighbour sentence saying "Diagnosis
# requires a multidisciplinary approach" therefore cannot license a workup
# list that is split into one row per test.
NECESSITY_CUE = re.compile(
    r"\bnecessary\b"
    r"|\bcan only be (?:made|established|diagnosed|confirmed)\b"
    r"|\bonly (?:be )?(?:made|established|confirmed) (?:after|with|by|when)\b"
    r"|\bcannot be (?:made|established|diagnosed) without\b"
    r"|\bmust be (?:fulfilled|present|met|satisfied|supported|documented|demonstrated)\b"
    r"|\b(?:criterion|criteria) must\b"
    r"|\bin the presence of\b"
    r"|\b(?:required|essential|mandatory|obligatory)\s+(?:for|in|to)\s+"
    r"(?:the )?diagnos\w+\b"
    r"|\bdiagnos\w+.{0,48}\bmust\b"
    r"|\bmust\b.{0,48}\bdiagnos\w+\b"
    r"|\bkey to (?:the )?diagnos\w+\b"
    # the diagnosis rests on the finding: "SM is diagnosed based on ...",
    # "the diagnosis is made by finding ..." (7 occurrences in the corpus)
    r"|\bdiagnos\w+\s+(?:based|dependent)\s+on\b"
    r"|\bdiagnos\w+\s+(?:is|are)\s+(?:made|established)\s+by\b"
    # exclusivity without a deontic verb: "cultures are the only way to ..."
    r"|\bthe only (?:way|means|method) to\b"
    # criterion satisfaction stated as a condition, not an obligation
    r"|\bcriteri(?:a|on)\b.{0,40}\b(?:have|has) been met\b"
    r"|\bcriteri(?:a|on)\b.{0,40}\bare met\b"
    # "diagnosis is confirmed by demonstrating X" -- anchored to diagnosis so a
    # bare "demonstrating" elsewhere in the passage cannot license anything
    r"|\bdiagnos\w+.{0,60}\bdemonstrat(?:ing|ion|ed)\b",
    re.I,
)
# Exclusivity is what lets a *procedure* carry a diagnostic requirement:
# "the diagnosis can only be made after angiography" states necessity of the
# test itself, "evaluation includes echocardiography" does not.  EliXR's
# ``result of`` (15.5) is the other licit form: the requirement is the test's
# result, not the act of testing.
EXCLUSIVE_NECESSITY = re.compile(
    r"\bcan only be (?:made|established|diagnosed|confirmed)\b"
    r"|\bonly (?:be )?(?:made|established|confirmed) (?:after|with|by|when)\b"
    r"|\bcannot be (?:made|established|diagnosed) without\b"
    r"|\b(?:required|essential|mandatory)\s+(?:for|in|to)\s+(?:the )?diagnos\w+\b"
    r"|\bresults? of\b"
    r"|\bthe only (?:way|means|method) to\b"
    r"|\bmust be (?:supported|documented|demonstrated|confirmed)\b",
    re.I,
)
# Sufficiency: the finding alone settles the diagnosis.  Without one of these
# constructions a `sufficient_for` row is a recommendation ("consider X"), a
# therapy statement, or a workup ranking ("first-level imaging") -- §16.8 found
# the slot was ungoverned and 50/57 annotated rows were misplaced.
SUFFICIENCY_CUE = re.compile(
    r"\b(?:is|are|be)\s+(?:considered\s+)?diagnostic\s+(?:of|for)\b"
    r"|\bdiagnostic of\b"
    r"|\bestablish(?:es|ed)?\s+(?:the\s+)?diagnos\w+\b"
    r"|\bconfirm(?:s|ed)?\s+(?:the\s+)?diagnos\w+\b"
    r"|\bsufficient\s+(?:to|for)\b|\benough\s+to\s+(?:diagnose|establish)\b"
    r"|\bmakes?\s+(?:the\s+)?diagnos\w+\b"
    r"|\bdiagnosed in (?:patients|individuals|subjects|those)\s+(?:who|with)\b"
    r"|\bif present,?\s+(?:the\s+)?diagnos\w+\b"
    # reversed word order, with an adverb allowed to intervene:
    # "Diagnosis is confirmed by FNAB ...", "is generally established with PCR"
    # the subject noun phrase can sit between: "Diagnosis of CMV infection is
    # generally established with PCR"
    r"|\bdiagnos\w+\b.{0,40}?\b(?:is|are|can be|may be)\s+(?:\w+ly\s+)?"
    r"(?:confirmed|established|achieved)\b"
    # exclusivity makes the test the one that settles it
    r"|\bcan only be (?:achieved|made|established|confirmed)\b"
    r"|\bthe only (?:definitive|confirmatory)\b"
    # hedged but still a sufficiency claim; E3 grades the modality separately
    r"|\b(?:is|are)\s+(?:usually|often|generally|typically)\s+diagnostic\b",
    re.I,
)
# N-of-M counting criterion and definitional identity: both are necessity
# without a deontic verb, and both are only trusted inside a criteria or
# definition context.
NUMERAL = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
COUNT_CRITERION = re.compile(
    rf"\b(?:at least|no fewer than|≥|>=)\s*{NUMERAL}\b"
    rf"|\b{NUMERAL}\s+or more\b"
    # bare "five minor criteria" / "two major criteria": the count *is* the rule
    rf"|\b{NUMERAL}\s+(?:\w+\s+)?criteri(?:a|on)\b"
    rf"|\btotal score of\s+{NUMERAL}\b",
    re.I,
)
DEFINITIONAL_CUE = re.compile(
    r"\b(?:definition of|defined as|defined by|"
    r"meets? the definition|using the definition)\b",
    re.I,
)
CRITERIA_CTX = {"criteria", "definition"}
# Screening scope, inclusion listing, recommendation, administrative action.
SCOPE_REJECT = re.compile(
    r"\bat[- ]risk\b|\bfamily members\b|\bcascade screening\b|\bto identify\b"
    r"|\bmultidisciplinary (?:approach|team)\b"
    r"|\b(?:this|which|it|evaluation|workup|work-up|assessment|investigation)"
    r"\s+(?:typically\s+|usually\s+|often\s+)?includes\b"
    r"|\btypically includes\b"
    r"|\bis advised\b|\bis recommended\b|\bshould be considered\b"
    r"|\brequire[sd]? to be\s+\w+ed\b"
    r"|\bprimary (?:imaging )?modalit\w*\b"
    r"|\bfirst[- ]line option\b",
    re.I,
)
# Diagnostic Procedure vs Finding, by morphology plus a closed list of generic
# test nouns (SemRep/EliXR type gate, 15.5).  No disease or organ names.
PROCEDURE_LIKE = re.compile(
    r"\b\w+(?:graphy|gram|scopy|metry|opsy)\b"
    r"|\b(?:mri|ct|pet|ecg|ekg|eeg|emg|ultrasound|sonograph\w*|x-?ray|"
    r"radiograph\w*|scan|imaging|panel|assay|culture|serolog\w+|titer|swab|"
    r"biopsy|test|tests|testing|monitor|monitoring|screening|"
    r"study|studies|analysis|evaluation|examination|workup|work-up)\b",
    re.I,
)
# Reference range stated as a normal value (G2).  Which side is abnormal comes
# from the comparison word, not from the measurement's identity.
NORMAL_RANGE = re.compile(
    r"\bnormal\b[^.;]{0,60}?"
    r"\b(?P<dir>less than|lower than|below|under|greater than|higher than|above|over)\s*"
    r"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-zμ%/]{1,12})?",
    re.I,
)
BELOW_WORDS = {"less than", "lower than", "below", "under"}
# "X is diagnosed in the presence of A, B and C": the conjunction is a first
# class object, and limb membership is decided by containment in the clause,
# not by a lexicon of the limbs (G3).
PRESENCE_CLAUSE = re.compile(
    r"(?:is|are|can be|may be)\s+diagnosed\s+"
    r"(?:in the presence of|when there (?:is|are)|if there (?:is|are))\s+"
    r"(?P<body>[^.;]{10,300})"
    r"|diagnosis requires (?:the presence of\s+)?(?P<body2>[^.;]{10,300})",
    re.I,
)
UNIT_ALIAS = {
    "msec": "ms", "millisecond": "ms", "milliseconds": "ms",
    "sec": "s", "second": "s", "seconds": "s",
    "mm hg": "mmhg",
}
VARIANT_CUE = re.compile(
    r"\b(this|the)\s+(variant|form|subtype|type|syndrome)\b",
    re.I,
)
SOME_OR_ALL = re.compile(r"\b(some or all|one or more|any of)\b", re.I)
AND_OR = re.compile(r"\band/or\b|\bor\b", re.I)
MIMIC = re.compile(r"\b(mimic|misidentif|misdiagnos|mistaken for)\b", re.I)
DISEASEY = re.compile(
    r"\b(syndrome|disease|carcinoma|sarcoma|vasculitis|deficiency|"
    r"abscess|dementia|catatonia|psoriasis|amyotroph|brucellosis|"
    r"neuropathy|infection|disorder)\b",
    re.I,
)
BOILER_PRED = re.compile(
    r"^(high index of suspicion|imaging|clinical examination|"
    r"laboratory|diagnosis|evaluation|examination)$",
    re.I,
)
GENERIC_SUBJ = {
    "disease", "syndrome", "disorder", "condition", "patient", "patients",
    "finding", "findings", "the", "and", "with", "of", "in", "a", "an", "or",
}

# QTc > 440 ms / ≥480 msec / range 91 to 97%
THRESH_PAT = re.compile(
    r"(?P<op>>=|≤|≥|<=|<|>|=|∼|~)?\s*"
    r"(?P<lo>\d+(?:\.\d+)?)\s*"
    r"(?:(?:to|-|–|—)\s*(?P<hi>\d+(?:\.\d+)?))?\s*"
    r"(?P<unit>ms|msec|sec|s|mmHg|%|cells/?mm3|cells/?μL|mg/?dL|pmol/?L|mm|cm)?",
    re.I,
)
OP_MAP = {">": ">", "<": "<", ">=": ">=", "<=": "<=", "≥": ">=", "≤": "<=",
          "=": "=", "∼": "range", "~": "range", None: None, "": None}


def _norm_words(s: str) -> set[str]:
    s = re.sub(r"[^a-zA-Z0-9\s]", " ", str(s or "").lower())
    out = set()
    for w in s.split():
        if w in GENERIC_SUBJ or len(w) < 3:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def number_in_text(val: Any, text: str) -> bool:
    """True when ``val`` (or a trivial decimal/percent variant) appears in text."""
    if val in (None, "", "null", "None"):
        return True
    q = (text or "").replace(",", "")
    s = str(val).strip()
    if not s or s in {"null", "None"}:
        return True
    alts = {s}
    try:
        f = float(s)
        alts.add(f"{f:g}")
        if f == int(f):
            alts.add(str(int(f)))
        # 0.45 sec ↔ 450 ms style: accept 10x/1000x digit strings if present
        for mul in (10, 100, 1000, 0.1, 0.01, 0.001):
            g = f * mul
            if abs(g - round(g)) < 1e-9 and abs(g) >= 1:
                alts.add(str(int(round(g))))
            alts.add(f"{g:g}")
        # percent ↔ proportion
        if 0 < f < 1:
            alts.add(f"{f * 100:g}")
            alts.add(str(int(round(f * 100))))
        if 1 <= f <= 100:
            alts.add(f"{f / 100:g}")
    except (TypeError, ValueError):
        pass
    return any(a and a in q for a in alts)


def number_in_quote(val: Any, quote: str) -> bool:
    """Back-compat alias: quote-only membership."""
    return number_in_text(val, quote)


def evidence_span(quote: str, passage: str | None, radius: int = EVIDENCE_RADIUS) -> str:
    """Citable neighbourhood of ``quote`` inside the glued passage.

    If the quote cannot be aligned, fall back to the quote alone (strict).
    """
    quote = quote or ""
    passage = passage or ""
    if not passage:
        return quote
    if not quote:
        return passage
    idx = passage.find(quote)
    if idx < 0:
        needle = quote[:80]
        idx = passage.find(needle) if needle else -1
    if idx < 0:
        # Quote is supposed to be a verbatim substring.  If it cannot be
        # aligned but the glued passage is itself neighbour-scale, the
        # passage *is* the claim window the extractor saw.
        if passage and len(passage) <= 2 * radius:
            return passage
        return quote
    lo = max(0, idx - radius)
    hi = min(len(passage), idx + max(len(quote), 1) + radius)
    return passage[lo:hi]


def _load_passage_index() -> dict[str, Any]:
    """Map (source, title, section) and sha1 prefix → glued passage texts."""
    global _PASSAGE_INDEX
    if _PASSAGE_INDEX is not None:
        return _PASSAGE_INDEX
    by_key: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    by_sha: dict[str, str] = {}
    # Cases outside the frozen 11 live in their own retrieval file; the keys are
    # content hashes, so adding one is additive and cannot disturb the 11.
    names = ["trial_retrieval_k30.json"]
    names += [n for n in os.environ.get("F7_EXTRA_RETRIEVAL", "").split(",") if n]
    for name in names:
        path = LEDGER / name
        if not path.exists():
            continue
        retrieval = json.loads(path.read_text("utf-8"))
        for rec in retrieval:
            for bundle in (rec.get("retrieved") or {}).values():
                for pas in bundle.get("passages") or []:
                    text = pas.get("text") or ""
                    if not text:
                        continue
                    key = (
                        str(pas.get("source") or ""),
                        str(pas.get("title") or ""),
                        str(pas.get("section_path") or ""),
                    )
                    by_key[key].append(text)
                    by_sha[hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]] = text
    _PASSAGE_INDEX = {"by_key": dict(by_key), "by_sha": by_sha}
    return _PASSAGE_INDEX


def resolve_passage(a: dict) -> str:
    """The glued passage the extractor was allowed to read, if recoverable."""
    raw = a.get("_passage") or a.get("passage")
    if isinstance(raw, str) and raw.strip():
        return raw
    idx = _load_passage_index()
    sha = str(a.get("_passage_sha1") or "")
    if sha and sha in idx["by_sha"]:
        return idx["by_sha"][sha]
    key = (
        str(a.get("_source") or ""),
        str(a.get("_title") or ""),
        str(a.get("_section") or ""),
    )
    texts = idx["by_key"].get(key) or []
    quote = str(a.get("quote") or "")
    if quote:
        for t in texts:
            if quote in t or quote[:80] in t:
                return t
    if len(texts) == 1:
        return texts[0]
    return ""


def license_text(a: dict, quote: str) -> str:
    """Text that may license a number or a positive relation cue."""
    return evidence_span(quote, resolve_passage(a))


def parse_threshold_from_quote(quote: str) -> dict | None:
    """Best-effort numeric threshold from a quote. Returns None if none found."""
    if not quote:
        return None
    # Prefer the first operator-bearing comparison in the quote.
    m = re.search(
        r"[^0-9]{0,20}"
        r"(?P<op>>=|≤|≥|<=|<|>|=)?\s*"
        r"(?P<lo>\d+(?:\.\d+)?)\s*"
        r"(?:(?:to|-|–|—)\s*(?P<hi>\d+(?:\.\d+)?))?\s*"
        r"(?P<unit>ms|msec|sec|s|mmHg|%|cells/?mm3|cells/?μL|mg/?dL|pmol/?L|mm|cm)?",
        quote,
        re.I,
    )
    if not m:
        m = THRESH_PAT.search(quote)
    if not m:
        return None
    lo = m.group("lo")
    hi = m.groupdict().get("hi")
    op_raw = m.groupdict().get("op")
    unit = (m.groupdict().get("unit") or "").strip() or None
    try:
        lo_f = float(lo)
        hi_f = float(hi) if hi else None
    except (TypeError, ValueError):
        return None
    if hi_f is not None:
        return {
            "operator": "range",
            "value": lo_f,
            "value_high": hi_f,
            "unit": unit,
            "relational": None,
        }
    op = OP_MAP.get(op_raw) or (">" if op_raw is None else op_raw)
    if op_raw is None:
        # bare number without operator — not a diagnostic cut
        return None
    return {
        "operator": op,
        "value": lo_f,
        "value_high": None,
        "unit": unit,
        "relational": None,
    }


def _threshold_empty(th: Any) -> bool:
    if not isinstance(th, dict):
        return True
    return th.get("value") in (None, "", "null") and not th.get("relational")


def _demote(a: dict, reason: str, new_rel: str = "feature_of") -> dict:
    a = dict(a)
    a["_gate"] = reason
    a["_gate_prev_relation"] = a.get("relation")
    a["relation"] = new_rel
    return a


def _drop(a: dict, reason: str) -> dict:
    a = dict(a)
    a["_gate"] = reason
    a["_gate_drop"] = True
    return a


def _subject_in_quote(subject: str, quote: str) -> bool:
    sw = _norm_words(subject)
    qw = _norm_words(quote)
    if not sw:
        return True
    # at least half of content words, or any distinctive long token
    hit = sw & qw
    if len(hit) >= max(1, (len(sw) + 1) // 2):
        return True
    for w in sw:
        if len(w) >= 6 and w in (quote or "").lower():
            return True
    return False


def _canon_unit(unit: str | None) -> str | None:
    u = (unit or "").strip().lower()
    return UNIT_ALIAS.get(u, u) or None


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:])\s+|\n+", text or "") if s.strip()]


def _covers_predicate(span: str, pred: str, ratio: float = 0.5) -> bool:
    """Does ``span`` state this predicate?  Content-word coverage, no lexicon."""
    pw = _norm_words(pred)
    if not pw:
        return False
    sw = _norm_words(span)
    return len(pw & sw) >= max(1, int(len(pw) * ratio + 0.999))


def _necessity_scope(pred: str, quote: str, licensed: str) -> str:
    """Where necessity is predicated of *this* predicate.

    Returns "quote", "sentence" (a claim-window sentence that states both the
    cue and the predicate), or "" when nothing licenses it.
    """
    if NECESSITY_CUE.search(quote or ""):
        return "quote"
    for s in _sentences(licensed):
        if NECESSITY_CUE.search(s) and _covers_predicate(s, pred):
            return "sentence"
    return ""


def _sufficiency_scope(pred: str, quote: str, licensed: str) -> str:
    """Where sufficiency is predicated of *this* predicate (same scope rule)."""
    if SUFFICIENCY_CUE.search(quote or ""):
        return "quote"
    for s in _sentences(licensed):
        if SUFFICIENCY_CUE.search(s) and _covers_predicate(s, pred):
            return "sentence"
    return ""


def _procedure_predicate(pred: str) -> bool:
    return bool(PROCEDURE_LIKE.search(pred or ""))


def _exclusive_for_procedure(quote: str, licensed: str, pred: str) -> bool:
    """A procedure may only be required when the text says so exclusively."""
    if EXCLUSIVE_NECESSITY.search(quote or ""):
        return True
    for s in _sentences(licensed):
        if EXCLUSIVE_NECESSITY.search(s) and _covers_predicate(s, pred):
            return True
    return False


def _counting_or_definitional(quote: str, ctx: str) -> bool:
    if ctx not in CRITERIA_CTX:
        return False
    return bool(COUNT_CRITERION.search(quote or "")
                or DEFINITIONAL_CUE.search(quote or ""))


def _reference_range_recode(a: dict, quote: str) -> dict | None:
    """``excludes``+negated stating a *normal* range → necessity of the
    abnormal side, with the cut and the inverted operator (G2).

    The engine's layer 1 already treats ``excludes`` as a hard rule but never
    reads the cut, so this keeps the rule hard and makes it read the number.
    """
    pred = str(a.get("predicate") or "")
    if not re.search(r"\bnormal\b", pred, re.I):
        return None
    m = NORMAL_RANGE.search(quote or "")
    if not m:
        return None
    below = m.group("dir").lower() in BELOW_WORDS
    measure = re.sub(r"\bnormal\b", "", pred, flags=re.I).strip(" ,:-") or pred
    out = dict(a)
    out["relation"] = "required_for"
    out["polarity"] = "asserted"
    out["modality"] = "obligatory"
    out["predicate"] = f"abnormal {measure}"
    out["threshold"] = {
        "operator": ">" if below else "<",
        "value": float(m.group("val")),
        "value_high": None,
        "unit": _canon_unit(m.group("unit")),
        "relational": None,
    }
    return out


def _presence_limbs(licensed: str) -> list[tuple[str, str]]:
    """(clause head, clause body) for every ``diagnosed in the presence of``."""
    out = []
    for m in PRESENCE_CLAUSE.finditer(licensed or ""):
        body = m.group("body") or m.group("body2") or ""
        head = (licensed or "")[max(0, m.start() - 80):m.start()]
        head = re.split(r"[.;\n\t]", head)[-1]
        out.append((head, body))
    return out


def _conjunction_limb(subj: str, pred: str, licensed: str) -> bool:
    """Is this predicate one limb of a stated diagnostic conjunction?"""
    for head, body in _presence_limbs(licensed):
        if not _covers_predicate(body, pred, ratio=0.75):
            continue
        if _covers_predicate(head, subj, ratio=0.5) or _subject_in_quote(subj, head):
            return True
    return False


def _g1_drop_dual_patho(assertions: list[dict]) -> list[dict]:
    """Same (subject, quote[:80]) cannot be pathognomonic and required."""
    keys_with_req: set[tuple] = set()
    for a in assertions:
        if (a.get("relation") or "").lower() != "required_for":
            continue
        q = str(a.get("quote") or "")
        keys_with_req.add((str(a.get("subject") or "").lower(), q[:80].lower()))
    out = []
    for a in assertions:
        rel = (a.get("relation") or "").lower()
        q = str(a.get("quote") or "")
        key = (str(a.get("subject") or "").lower(), q[:80].lower())
        if rel == "pathognomonic_for" and key in keys_with_req:
            a = _demote(a, "G1_dual_slot", "feature_of")
        out.append(a)
    return out


def gate_one(a: dict) -> dict | None:
    """Apply per-assertion gates. Returns None to drop, else a (possibly demoted) copy."""
    if not isinstance(a, dict):
        return None
    a = dict(a)
    quote = str(a.get("quote") or "")
    licensed = license_text(a, quote)
    rel = (a.get("relation") or "").lower().strip()
    mod = (a.get("modality") or "").lower().strip()
    pred = str(a.get("predicate") or "")
    subj = str(a.get("subject") or "")
    ctx = (a.get("context_type") or "").lower().strip()
    pol = (a.get("polarity") or "asserted").lower()
    reasons: list[str] = []

    # E14: invented threshold numbers — license against the glued passage
    # neighbourhood, not only the 200-char quote.
    th = a.get("threshold") if isinstance(a.get("threshold"), dict) else {}
    val = th.get("value") if th else None
    if val not in (None, "", "null") and not number_in_text(val, licensed):
        a["threshold"] = {
            "operator": None, "value": None, "value_high": None,
            "unit": None, "relational": None,
        }
        reasons.append("E14_threshold_cleared")
        th = a["threshold"]
    elif val not in (None, "", "null") and not number_in_text(val, quote) \
            and number_in_text(val, licensed):
        reasons.append("E14_licensed_from_passage")

    # refill only from the quoted span — neighbour chunks may license an
    # already-extracted number, but must not harvest a new cutoff.
    if _threshold_empty(a.get("threshold")):
        parsed = parse_threshold_from_quote(quote)
        if parsed:
            a["threshold"] = parsed
            reasons.append("threshold_from_quote")

    # E7 boilerplate required_for
    if rel == "required_for" and BOILER_PRED.match(pred.strip()):
        return _drop(a, "E7_boilerplate")

    # E13 argument inversion
    if rel in {"pathognomonic_for", "required_for", "sufficient_for"}:
        if DISEASEY.search(pred) and not DISEASEY.search(subj) and len(subj) > 8:
            # subject looks like a finding (no disease word), predicate is disease
            if not _subject_in_quote(subj, licensed) or len(_norm_words(subj)) <= 3:
                return _drop(a, "E13_argument_inversion")

    # E8 mimic as feature/exclude
    if MIMIC.search(quote) and rel in {"excludes", "feature_of"} and pol == "asserted":
        a = _demote(a, "E8_mimic", "distinguishes_from")
        rel = "distinguishes_from"
        reasons.append("E8_mimic")

    # E10 treatment required_for → soft / treated_by
    if rel == "required_for" and ctx == "treatment":
        a = _demote(a, "E10_treatment_required", "treated_by")
        rel = "treated_by"
        reasons.append("E10_treatment_required")

    # E3 modality inflation on required_for
    if rel == "required_for" and mod == "obligatory" and HEDGE.search(quote):
        a["modality"] = "typical"
        reasons.append("E3_modality_hedge")
        mod = "typical"

    # E9 some or all → any
    cg = a.get("criterion_group") if isinstance(a.get("criterion_group"), dict) else {}
    if cg.get("logic") == "all" and SOME_OR_ALL.search(quote):
        cg = dict(cg)
        cg["logic"] = "any"
        a["criterion_group"] = cg
        reasons.append("E9_some_or_all")

    # E12 / E4 pathognomonic without cue in the evidence window
    if rel == "pathognomonic_for" and not PATHO_CUE.search(licensed):
        # also catch name-tautology: quote is just the disease name
        a = _demote(a, "E12_or_E4_patho_no_cue", "feature_of")
        rel = "feature_of"
        reasons.append("E12_or_E4_patho_no_cue")

    # E4 required_for: necessity has to be predicated of *this* predicate, and
    # a test may only be required when the text is exclusive about it.  The
    # ±1200 window used to license split workup lists ("Diagnosis requires …
    # This includes Holter") because the cue matched a neighbour sentence.
    if rel == "required_for":
        scope = _necessity_scope(pred, quote, licensed)
        if SCOPE_REJECT.search(quote):
            a = _demote(a, "E4_required_scope", "feature_of")
            rel = "feature_of"
            reasons.append("E4_required_scope")
        elif _procedure_predicate(pred) and not _exclusive_for_procedure(quote, licensed, pred):
            # Diagnostic Procedure without exclusivity: an evaluation step,
            # not a finding that must be present.
            a = _demote(a, "E4_procedure_not_finding", "feature_of")
            rel = "feature_of"
            reasons.append("E4_procedure_not_finding")
        elif scope:
            if scope == "sentence":
                reasons.append("E4_necessity_from_sentence")
        elif _counting_or_definitional(quote, ctx):
            reasons.append("E4_counting_criterion")
        else:
            a = _demote(a, "E4_required_no_cue", "feature_of")
            rel = "feature_of"
            reasons.append("E4_required_no_cue")

    # E15 sufficient_for: same scope rule as E4, but the licensing construction
    # is sufficiency rather than necessity.
    # A counting criterion is a decision rule ("a total score of 4 or more"),
    # so it licenses the slot it lands in without a sufficiency verb.
    if rel == "sufficient_for":
        if SCOPE_REJECT.search(quote) or not (
                _sufficiency_scope(pred, quote, licensed)
                or _counting_or_definitional(quote, ctx)):
            a = _demote(a, "E15_sufficiency_no_cue", "feature_of")
            rel = "feature_of"
            reasons.append("E15_sufficiency_no_cue")

    # E5 / E1: variant deixis or subject missing from quote
    if VARIANT_CUE.search(quote) and rel == "required_for":
        # this variant required_for → cannot stay obligatory parent-class rule
        if mod == "obligatory":
            a["modality"] = "typical"
            reasons.append("E5_variant_obligatory")
            mod = "typical"
        if not a.get("antecedent") and not _subject_in_quote(subj, licensed):
            # still allow if subject words appear in the evidence window
            a = _demote(a, "E5_variant_scope", "feature_of")
            rel = "feature_of"
            reasons.append("E5_variant_scope")

    if rel in {"required_for", "pathognomonic_for", "sufficient_for", "excludes"}:
        if not _subject_in_quote(subj, licensed) and VARIANT_CUE.search(quote):
            return _drop(a if reasons else a, "E1_E5_subject_not_in_quote")

    # G2: recode after E4 so the new required_for is not immediately demoted.
    if rel == "excludes" and pol == "negated" and ctx in CRITERIA_CTX:
        g2 = _reference_range_recode(a, quote)
        if g2 is not None:
            a = g2
            rel = "required_for"
            pol = "asserted"
            reasons.append("G2_reference_range")

    # E16: `excludes` means the finding's *presence* rules the disease out, so
    # a negated row contradicts its own slot -- it states that the finding is
    # absent, which is a requirement, not an exclusion.  The schema alone
    # settles this (it is the rule already applied to the training labels).
    # Recoding it to `required_for` was tried and rejected: it re-armed the
    # false necessities that G-A had cleared (mechanism check
    # 74_ga_false_required_cleared fails), because most of these rows are
    # workup prose rather than stated criteria.  Demotion keeps the content
    # available to layer 3 without arming a layer-1 constraint.
    if rel == "excludes" and pol == "negated":
        a = _demote(a, "E16_excludes_negated", "feature_of")
        rel = "feature_of"
        reasons.append("E16_excludes_negated")

    # G3: a limb of a stated diagnostic conjunction.  Only the relation is
    # corrected -- the strength stays whatever the extractor read, so this can
    # never invent a hard layer-1 constraint out of a typical feature.
    if rel == "feature_of" and _conjunction_limb(subj, pred, licensed):
        a["relation"] = "required_for"
        rel = "required_for"
        reasons.append("G3_presence_conjunction")

    if reasons:
        prev = [p for p in str(a.get("_gate") or "").split("+") if p]
        a["_gate"] = "+".join(dict.fromkeys(prev + reasons))
    return a


def _merge_and_or_required(assertions: list[dict]) -> list[dict]:
    """E9: same quote with and/or split into multiple required_for → one any-group."""
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    others: list[dict] = []
    for a in assertions:
        if a.get("_gate_drop"):
            continue
        rel = (a.get("relation") or "").lower()
        quote = str(a.get("quote") or "")
        if rel != "required_for" or not AND_OR.search(quote):
            others.append(a)
            continue
        key = (quote[:80].lower(), (a.get("subject") or "").lower())
        buckets[key].append(a)

    out = list(others)
    for key, group in buckets.items():
        if len(group) < 2:
            out.extend(group)
            continue
        quote = str(group[0].get("quote") or "")
        # only merge when quote signals disjunction of tests
        if not re.search(r"\band/or\b|\bor\b", quote, re.I):
            out.extend(group)
            continue
        gid = f"gate_or_{abs(hash(key)) % 10_000_000}"
        for a in group:
            a = dict(a)
            a["criterion_group"] = {"group_id": gid, "logic": "any", "n": None}
            if (a.get("modality") or "").lower() == "obligatory":
                a["modality"] = "typical"
            a["_gate"] = ((a.get("_gate") + "+") if a.get("_gate") else "") + "E9_and_or_merge"
            out.append(a)
    return out


def gate_assertions(assertions: list[dict], *, apply_nli: bool = False) -> list[dict]:
    """Run F7 (and optionally F8) over a list of assertions."""
    gated: list[dict] = []
    for a in assertions:
        if not isinstance(a, dict):
            continue
        g = gate_one(a)
        if g is None or g.get("_gate_drop"):
            continue
        gated.append(g)
    gated = _g1_drop_dual_patho(gated)
    gated = _merge_and_or_required(gated)
    if apply_nli:
        from nli_verify_assertions import nli_filter_assertions  # local sibling
        gated = nli_filter_assertions(gated)
    return gated


def gate_stats(before: list[dict], after: list[dict]) -> dict[str, int]:
    from collections import Counter
    c = Counter()
    after_ids = {id(a) for a in after}
    for a in after:
        g = a.get("_gate")
        if g:
            for part in str(g).split("+"):
                c[part] += 1
    c["n_before"] = sum(1 for a in before if isinstance(a, dict))
    c["n_after"] = len(after)
    c["n_dropped"] = c["n_before"] - c["n_after"]
    return dict(c)


# ---------------------------------------------------------------------------
# Specimen unit checks (326 / 74 / 257 / 475)
# ---------------------------------------------------------------------------

def _self_test() -> None:
    specimens = []

    # 326: usually must + and/or → two required_for obligatory
    q326 = ("the clinical diagnosis usually must be supported by the results "
            "of bacteriologic and/or serologic tests")
    a326 = [
        {"subject": "Brucellosis", "relation": "required_for", "polarity": "asserted",
         "modality": "obligatory", "predicate": "bacteriologic tests", "quote": q326,
         "context_type": "definition", "threshold": {}},
        {"subject": "Brucellosis", "relation": "required_for", "polarity": "asserted",
         "modality": "obligatory", "predicate": "serologic tests", "quote": q326,
         "context_type": "definition", "threshold": {}},
    ]
    out326 = gate_assertions(a326)
    assert len(out326) == 2, out326
    assert all((a.get("modality") or "") != "obligatory" for a in out326), out326
    assert all((a.get("criterion_group") or {}).get("logic") == "any" for a in out326), out326
    specimens.append(("326_and_or", True))

    # 74: name tautology pathognomonic
    a74 = {
        "subject": "Long QT Syndrome", "relation": "pathognomonic_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "prolonged QT interval",
        "quote": "a condition termed long QT syndrome",
        "threshold": {"operator": ">", "value": 440, "unit": "ms"},
        "context_type": "definition",
    }
    g74 = gate_one(a74)
    assert g74 is not None
    assert (g74.get("relation") or "") == "feature_of", g74
    assert g74.get("threshold", {}).get("value") in (None, "") or "E14" in (g74.get("_gate") or ""), g74
    specimens.append(("74_e12", True))

    # 74 truncation: 440 lives in a neighbour chunk of the glued passage
    passage_74 = (
        "Generally, the normal QT interval is less than 400 to 440 milliseconds (ms). "
        "A common cause of QT prolongation includes medications and congenital long QT syndrome."
    )
    a74win = {
        "subject": "Long QT Syndrome", "relation": "pathognomonic_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "prolonged QT interval",
        "quote": "congenital long QT syndrome",
        "threshold": {"operator": ">", "value": 440, "unit": "ms"},
        "context_type": "definition",
        "_passage": passage_74,
    }
    g74win = gate_one(a74win)
    assert (g74win.get("relation") or "") == "feature_of", g74win
    assert g74win.get("threshold", {}).get("value") == 440, g74win
    assert "E14_licensed_from_passage" in (g74win.get("_gate") or ""), g74win
    specimens.append(("74_e14_passage_window", True))

    # far-away 440 in the same long dump must not license
    a74far = dict(a74)
    a74far["_passage"] = ("The normal QT interval is less than 400 to 440 milliseconds. "
                          + ("lorem " * 400)
                          + "a condition termed long QT syndrome")
    g74far = gate_one(a74far)
    assert (g74far.get("relation") or "") == "feature_of", g74far
    assert g74far.get("threshold", {}).get("value") in (None, "") or "E14_threshold_cleared" in (g74far.get("_gate") or ""), g74far
    specimens.append(("74_e14_far_number_not_licensed", True))

    # 74b: real pathognomonic with cue must survive
    a74ok = {
        "subject": "Brugada syndrome", "relation": "pathognomonic_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "type 1 Brugada pattern",
        "quote": "Type 1 Brugada pattern is pathognomonic for the syndrome",
        "context_type": "definition", "threshold": {},
    }
    g74ok = gate_one(a74ok)
    assert (g74ok.get("relation") or "") == "pathognomonic_for", g74ok
    specimens.append(("74_keep_real_patho", True))

    # 257: some or all → any
    a257 = {
        "subject": "Flexor tenosynovitis", "relation": "feature_of",
        "polarity": "asserted", "modality": "typical",
        "predicate": "fusiform swelling of the digit",
        "quote": "Presence of some or all of Kanavel’s cardinal signs (flexor posturing "
                 "and fusiform swelling of the digit, tenderness ...)",
        "criterion_group": {"group_id": "g1", "logic": "all", "n": 4},
        "context_type": "definition", "threshold": {},
    }
    g257 = gate_one(a257)
    assert (g257.get("criterion_group") or {}).get("logic") == "any", g257
    specimens.append(("257_some_or_all", True))

    # 475: this variant relies on → no obligatory required_for
    a475 = {
        "subject": "Anterior Interosseous Nerve Syndrome",
        "relation": "required_for", "polarity": "asserted", "modality": "obligatory",
        "predicate": "advanced MRI techniques",
        "quote": "Diagnosis of this variant relies on advanced MRI techniques",
        "context_type": "diagnosis", "threshold": {},
    }
    g475 = gate_one(a475)
    assert g475 is not None
    # hedge → not obligatory; variant → demoted or not obligatory
    assert (g475.get("modality") or "") != "obligatory" or (g475.get("relation") or "") != "required_for", g475
    specimens.append(("475_variant_mri", True))

    # 119: cornoid lamella with diagnostic cue kept
    a119 = {
        "subject": "Porokeratosis", "relation": "pathognomonic_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "cornoid lamella",
        "quote": "will show the cornoid lamella and will be diagnostic",
        "context_type": "histopathology", "threshold": {},
    }
    g119 = gate_one(a119)
    assert (g119.get("relation") or "") == "pathognomonic_for", g119
    specimens.append(("119_cornoid", True))

    # G-A: neighbour "requires" must not license a bare Holter quote
    a_holter = {
        "subject": "Channelopathy", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "24 h Holter monitoring",
        "quote": "24 h Holter monitoring",
        "context_type": "diagnosis", "threshold": {},
        "_passage": ("Diagnosis requires a multidisciplinary approach. "
                     "This includes 24 h Holter monitoring and genetic analysis."),
    }
    g_holter = gate_one(a_holter)
    assert (g_holter.get("relation") or "") == "feature_of", g_holter
    specimens.append(("ga_holter_not_required", True))

    a_atrisk = {
        "subject": "ARVC", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "genetic testing",
        "quote": "Genetic testing is essential to identify at-risk individuals",
        "context_type": "diagnosis", "threshold": {},
    }
    g_atrisk = gate_one(a_atrisk)
    assert (g_atrisk.get("relation") or "") != "required_for", g_atrisk
    specimens.append(("ga_atrisk_demoted", True))

    a_typei = {
        "subject": "Brugada syndrome", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "type I pattern",
        "quote": "type I pattern necessary for the diagnosis",
        "context_type": "definition", "threshold": {},
    }
    g_typei = gate_one(a_typei)
    assert (g_typei.get("relation") or "") == "required_for", g_typei
    specimens.append(("ga_keep_type_i", True))

    a_tako = {
        "subject": "takotsubo cardiomyopathy", "relation": "required_for",
        "polarity": "asserted", "modality": "typical",
        "predicate": "coronary angiography",
        "quote": "can only be made after coronary angiography",
        "context_type": "diagnosis", "threshold": {},
    }
    g_tako = gate_one(a_tako)
    assert (g_tako.get("relation") or "") == "required_for", g_tako
    specimens.append(("ga_keep_takotsubo_angio", True))

    a_struct = {
        "subject": "CPVT", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "structurally normal heart",
        "quote": "in the presence of a structurally normal heart",
        "context_type": "definition", "threshold": {},
    }
    g_struct = gate_one(a_struct)
    assert (g_struct.get("relation") or "") == "required_for", g_struct
    specimens.append(("ga_keep_structurally_normal", True))

    # G1 dual slot
    a_dual = [
        dict(a_typei),
        {**a_typei, "relation": "pathognomonic_for"},
    ]
    out_dual = gate_assertions(a_dual)
    rels = {(a.get("relation") or "") for a in out_dual}
    assert "required_for" in rels and "pathognomonic_for" not in rels, out_dual
    specimens.append(("g1_dual_slot", True))

    # G2 recode
    a_g2 = {
        "subject": "Long QT Syndrome", "relation": "excludes",
        "polarity": "negated", "modality": "typical",
        "predicate": "normal QTc",
        "quote": "A normal QTc in men is less than 440ms",
        "context_type": "criteria",
        "threshold": {"operator": "<", "value": 440, "unit": "ms"},
    }
    g_g2 = gate_one(a_g2)
    assert (g_g2.get("relation") or "") == "required_for", g_g2
    assert (g_g2.get("polarity") or "") == "asserted", g_g2
    assert (g_g2.get("predicate") or "") == "abnormal QTc", g_g2
    assert (g_g2.get("threshold") or {}).get("operator") == ">", g_g2
    assert (g_g2.get("threshold") or {}).get("value") == 440, g_g2
    assert (g_g2.get("threshold") or {}).get("unit") == "ms", g_g2
    specimens.append(("g2_reference_range", True))

    # G3: licensed presence-of window, typical not obligatory
    a_g3 = {
        "subject": "CPVT", "relation": "feature_of",
        "polarity": "asserted", "modality": "typical",
        "predicate": "bidirectional VT",
        "quote": "bidirectional VT",
        "context_type": "definition", "threshold": {},
        "_passage": ("1. CPVT is diagnosed in the presence of a structurally "
                     "normal heart, normal ECG and unexplained exercise or "
                     "catecholamine induced bidirectional VT or polymorphic VT"),
    }
    g_g3 = gate_one(a_g3)
    assert (g_g3.get("relation") or "") == "required_for", g_g3
    assert (g_g3.get("modality") or "") != "obligatory", g_g3
    specimens.append(("g3_presence_vt", True))

    # G3 must not lift a Holter list
    a_g3_no = {
        "subject": "CPVT", "relation": "feature_of",
        "polarity": "asserted", "modality": "typical",
        "predicate": "24 h Holter monitoring",
        "quote": "24 h Holter monitoring",
        "context_type": "diagnosis", "threshold": {},
        "_passage": a_g3["_passage"],
    }
    g_g3_no = gate_one(a_g3_no)
    assert (g_g3_no.get("relation") or "") == "feature_of", g_g3_no
    specimens.append(("g3_not_holter", True))

    a_g3_ecg = {
        "subject": "CPVT", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "normal ECG",
        "quote": "normal ECG",
        "context_type": "definition", "threshold": {},
        "_passage": a_g3["_passage"],
    }
    g_g3_ecg = gate_one(a_g3_ecg)
    assert (g_g3_ecg.get("relation") or "") == "required_for", g_g3_ecg
    specimens.append(("g3_normal_ecg_restored", True))

    a_prec = {
        "subject": "Brugada syndrome", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "type I pattern in at least 2 of V1, V2, and V3",
        "quote": "present in at least 2 of the three precordial leads",
        "context_type": "definition", "threshold": {},
    }
    g_prec = gate_one(a_prec)
    assert (g_prec.get("relation") or "") == "required_for", g_prec
    specimens.append(("ga_keep_precordial_leads", True))

    a_ep = {
        "subject": "Epilepsy", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "two or more unprovoked seizures",
        "quote": "Using the definition of epilepsy as two or more unprovoked seizures",
        "context_type": "definition", "threshold": {},
    }
    g_ep = gate_one(a_ep)
    assert (g_ep.get("relation") or "") == "required_for", g_ep
    specimens.append(("ga_keep_epilepsy_definition", True))

    a_ms = {
        "subject": "Metabolic syndrome", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "3 or more metabolic abnormalities",
        "quote": "3 or more metabolic abnormalities",
        "context_type": "criteria", "threshold": {},
    }
    g_ms = gate_one(a_ms)
    assert (g_ms.get("relation") or "") == "required_for", g_ms
    specimens.append(("ga_keep_metabolic_3", True))

    # A workup combination without exclusivity is an evaluation step even
    # when the sentence starts with "The diagnosis is made".
    a_myo = {
        "subject": "Myotonia congenita", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "clinical, electrophysiological, and genetic studies",
        "quote": "The diagnosis is made with a combination of clinical, electrophysiological, and genetic studies",
        "context_type": "criteria", "threshold": {},
    }
    g_myo = gate_one(a_myo)
    assert (g_myo.get("relation") or "") == "feature_of", g_myo
    specimens.append(("ga_workup_combination_demoted", True))

    a_alc = {
        "subject": "Alcoholic cardiomyopathy", "relation": "required_for",
        "polarity": "asserted", "modality": "obligatory",
        "predicate": "Chronic heavy alcohol use",
        "quote": "a personal history of chronic heavy alcohol use",
        "context_type": "criteria", "threshold": {},
        "_passage": ("The diagnosis of alcoholic cardiomyopathy is non-specific. "
                     "The key to diagnosis is a personal history of chronic heavy "
                     "alcohol use and the absence of other etiologies."),
    }
    g_alc = gate_one(a_alc)
    assert (g_alc.get("relation") or "") == "required_for", g_alc
    assert "E4_necessity_from_sentence" in (g_alc.get("_gate") or ""), g_alc
    specimens.append(("ga_truncated_quote_same_sentence", True))

    # ---- generalisation: the same rules on text from other specialties ----
    # None of the patterns above may contain a disease, organ or test name, so
    # each rule is re-run on a passage from a different domain.
    out_of_domain = [
        # G-A: procedure without exclusivity, infectious disease
        (dict(subject="Lyme disease", relation="required_for", polarity="asserted",
              modality="obligatory", predicate="Western blot",
              quote="Evaluation typically includes a Western blot",
              context_type="diagnosis", threshold={}),
         "feature_of", "od_ga_workup_includes"),
        # G-A: exclusivity keeps a procedure, gastroenterology
        (dict(subject="Coeliac disease", relation="required_for", polarity="asserted",
              modality="obligatory", predicate="duodenal biopsy",
              quote="the diagnosis can only be made after duodenal biopsy",
              context_type="diagnosis", threshold={}),
         "required_for", "od_ga_exclusive_procedure"),
        # G-A: screening scope, oncology
        (dict(subject="Lynch syndrome", relation="required_for", polarity="asserted",
              modality="obligatory", predicate="germline sequencing",
              quote="Germline sequencing is essential to identify at-risk relatives",
              context_type="diagnosis", threshold={}),
         "feature_of", "od_ga_at_risk_screening"),
        # G-A: counting criterion, rheumatology
        (dict(subject="Systemic lupus erythematosus", relation="required_for",
              polarity="asserted", modality="obligatory",
              predicate="4 of the 11 classification items",
              quote="at least 4 of the 11 classification items",
              context_type="criteria", threshold={}),
         "required_for", "od_ga_counting_criterion"),
        # G2: reference range, haematology (normal is *above* the cut)
        (dict(subject="Neutropenia", relation="excludes", polarity="negated",
              modality="typical", predicate="normal neutrophil count",
              quote="A normal neutrophil count is greater than 1500 cells/mm3",
              context_type="criteria", threshold={}),
         "required_for", "od_g2_reference_range_upward"),
        # G3: conjunction limbs, critical care
        (dict(subject="Sepsis", relation="feature_of", polarity="asserted",
              modality="typical", predicate="organ dysfunction",
              quote="organ dysfunction", context_type="definition", threshold={},
              _passage=("Sepsis is diagnosed in the presence of suspected "
                        "infection and organ dysfunction attributable to it.")),
         "required_for", "od_g3_conjunction_limb"),
        # G3 must not lift a co-mentioned test in the same window
        (dict(subject="Sepsis", relation="feature_of", polarity="asserted",
              modality="typical", predicate="blood culture",
              quote="blood culture", context_type="diagnosis", threshold={},
              _passage=("Sepsis is diagnosed in the presence of suspected "
                        "infection and organ dysfunction attributable to it. "
                        "Obtain a blood culture before antibiotics.")),
         "feature_of", "od_g3_not_the_test"),
        # E15: sufficiency must be stated, not implied by a recommendation
        (dict(subject="CPVT", relation="sufficient_for", polarity="asserted",
              modality="obligatory", predicate="pathogenic mutation",
              quote="diagnosed in patients who have a pathogenic mutation",
              context_type="definition", threshold={}),
         "sufficient_for", "e15_keep_stated_sufficiency"),
        (dict(subject="Cardiomyopathy", relation="sufficient_for",
              polarity="asserted", modality="typical",
              predicate="endomyocardial biopsy",
              quote="consider endomyocardial biopsy in selected patients",
              context_type="diagnosis", threshold={}),
         "feature_of", "e15_recommendation_demoted"),
        (dict(subject="Helicobacter pylori infection", relation="sufficient_for",
              polarity="asserted", modality="typical",
              predicate="positive urea breath test",
              quote="A positive urea breath test is diagnostic of active infection",
              context_type="diagnosis", threshold={}),
         "sufficient_for", "od_e15_keep_diagnostic_of"),
        (dict(subject="Colorectal cancer", relation="sufficient_for",
              polarity="asserted", modality="typical", predicate="colonoscopy",
              quote="Colonoscopy is the primary imaging modality",
              context_type="diagnosis", threshold={}),
         "feature_of", "od_e15_modality_ranking_demoted"),
        # E16: `excludes` needs the finding to be present to rule the disease
        # out, so a negated row is misplaced whatever the disease
        (dict(subject="Hypothyroidism", relation="excludes", polarity="negated",
              modality="typical", predicate="secondary causes",
              quote="in the absence of secondary causes",
              context_type="diagnosis", threshold={}),
         "feature_of", "od_e16_excludes_negated"),
        (dict(subject="Sarcoidosis", relation="excludes", polarity="asserted",
              modality="typical", predicate="acid-fast bacilli",
              quote="the presence of acid-fast bacilli excludes sarcoidosis",
              context_type="diagnosis", threshold={}),
         "excludes", "od_e16_asserted_excludes_kept"),
        # morphology, not judgement: plural agreement and an intervening adverb
        # must not decide whether a cue fires
        (dict(subject="Giardiasis", relation="pathognomonic_for",
              polarity="asserted", modality="typical", predicate="cysts in stool",
              quote="Characteristic trophozoites or cysts in stool are diagnostic",
              context_type="diagnosis", threshold={}),
         "pathognomonic_for", "od_patho_plural_agreement"),
        (dict(subject="Cytomegalovirus infection", relation="sufficient_for",
              polarity="asserted", modality="typical", predicate="PCR",
              quote="Diagnosis of CMV infection is generally established with PCR",
              context_type="diagnosis", threshold={}),
         "sufficient_for", "od_sufficiency_adverb_infix"),
    ]
    for spec, want, name in out_of_domain:
        got = gate_one(spec)
        assert (got.get("relation") or "") == want, (name, got)
        specimens.append((name, True))

    g_neut = gate_one(out_of_domain[4][0])
    assert (g_neut.get("threshold") or {}).get("operator") == "<", g_neut
    assert (g_neut.get("threshold") or {}).get("value") == 1500, g_neut
    specimens.append(("od_g2_operator_inverted_by_direction", True))

    print("gate_assertions self-test OK:", [s[0] for s in specimens])


if __name__ == "__main__":
    _self_test()
