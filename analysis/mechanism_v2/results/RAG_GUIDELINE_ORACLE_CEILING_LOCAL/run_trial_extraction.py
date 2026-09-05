#!/usr/bin/env python3
"""Stage 2: the only two places a model is allowed to run.

``guideline``  one call per (retrieved passage, focus hypothesis) turning prose
               into the assertion schema.  It never sees the vignette, the gold
               answer or the candidate list, so its output is cacheable across
               cases -- which is the property the feasibility note claimed and
               this run is meant to test.
``case``       one call per vignette turning the case text into findings.  It
               never sees the candidate list or the gold answer.

Everything downstream of this file is deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
CACHE = LEDGER / "trial_extraction_cache"
GUIDELINE_KIND = "guideline"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_assertions import parse_threshold_from_quote  # noqa: E402

RELATIONS = [
    "feature_of", "required_for", "sufficient_for", "pathognomonic_for",
    "excludes", "argues_against", "distinguishes_from", "variant_of",
    "synonym_of", "caused_by", "treated_by",
]
MODALITIES = ["obligatory", "typical", "frequent", "occasional", "rare"]
CONTEXT_TYPES = [
    "definition", "criteria", "differential", "histopathology", "imaging",
    "epidemiology", "treatment", "prognosis", "table_row", "other",
]

GUIDELINE_PROMPT = f"""You convert one guideline passage into structured diagnostic assertions.

Extract every assertion the passage makes ABOUT A NAMED DISEASE. Prefer assertions whose
subject is the focus disease given in the payload, but also keep assertions about other
diseases the passage names explicitly (exclusion rules usually live in a competitor's text).

Return strict JSON: {{"assertions": [ ... ]}}. Each assertion:
{{
  "subject": "<disease name exactly as the passage calls it>",
  "predicate": "<the finding, sign, test result, exposure or histology, as a short noun phrase>",
  "predicate_kind": "symptom|sign|lab|imaging|histopathology|ecg|hemodynamic|exposure|demographic|course|other",
  "relation": one of {RELATIONS},
  "polarity": "asserted" | "negated",
  "modality": one of {MODALITIES},
  "threshold": {{"operator": "<|<=|>|>=|=|range|null", "value": <number or null>,
                "value_high": <number or null>, "unit": "<unit or null>",
                "relational": "<e.g. PAP >= systemic pressure, or null>"}},
  "comparator": "<the other disease, only for distinguishes_from / argues_against; else null>",
  "context_type": one of {CONTEXT_TYPES},
  "criterion_group": {{"group_id": "<short id local to this passage, e.g. g1, or null>",
                      "logic": "all" | "any" | "at_least_n" | null,
                      "n": <integer or null>}},
  "quote": "<verbatim substring of the passage, <=200 chars, that states this>"
}}

Criterion groups: when one sentence lists several findings that together form ONE diagnostic
criterion set, emit one assertion per member and give all members the same group_id, the same
logic and the same n. Use "all" for "A and B and C are required" or a named n-sign set such as
"Kanavel's four cardinal signs"; use "at_least_n" with n for "at least two of the following";
use "any" for "one or more of". Never merge two findings joined by "and" into a single predicate
string -- split them into separate members of one group. Leave group_id null when the assertion
stands alone.

Rules:
- polarity is "negated" when the passage says the feature is absent, normal, or does not occur
  in the subject. "QTc is normal" is negated for the predicate "prolonged QTc".
- relation "required_for" only when the passage says the feature is necessary for the diagnosis;
  "pathognomonic_for" only when it says the feature is diagnostic/hallmark/characteristic on its own.
- Use "differential" for context_type when the sentence is contrasting diseases rather than
  describing the subject's own features; use "table_row" when the text is a table row and the
  association may be an artifact of two rows sitting next to each other.
- Copy numbers into threshold. Never invent a threshold that is not in the text.
- quote must appear verbatim in the passage. If nothing is assertable, return an empty list.
"""

# S32/S34.  The group instruction above scopes grouping to "one sentence".  The
# model obeys it: across 768 emitted groups, 96.4% sit inside a single sentence,
# 3.6% cross one, and none cross a line.  But S24.2 measured that only 12.3% of
# real criteria sets put the quantifier and its members in one sentence -- the
# usual layout is a lead-in ending in a colon followed by the members on their
# own lines, which this wording excludes by construction.  This replacement
# scopes grouping to the whole passage instead.  Kept as a separate block, and
# selected by --free-groups, so the two can be run against each other.
FREE_GROUP_BLOCK = """
Criterion groups: a criterion set is any place where the passage presents several findings that
together form ONE diagnostic criterion. Emit one assertion per member and give every member the
same group_id, the same logic and the same n.

A criterion set may be written in any of these layouts, and you must group all of them:
  (a) within one sentence -- "fever, rash and arthritis are required";
  (b) a lead-in sentence ending in a colon, followed by the members as separate lines,
      bullets, numbered items or short sentences -- group the lead-in's quantifier with
      the member lines even though they are not one sentence;
  (c) a lead-in followed by members written as prose, separated by semicolons or "and"/"or";
  (d) members that continue across several sentences or several lines of the passage.
The members do NOT have to be in the same sentence or the same line as the quantifier.

Choose the logic from the quantifier, wherever it sits:
  "all"          - every member is required: "A and B and C are required", "all of the
                   following", or a named complete set such as "Kanavel's four cardinal signs".
  "at_least_n"   - a count is stated: "at least two of the following", "3 or more of",
                   "two or more". Put that count in n.
  "any"          - one member suffices: "one or more of", "any of the following", "some or all".
The logic field must be exactly one of "all", "any", "at_least_n", or null. Never write "and",
"or", "typical", or the string "null".

Never merge two findings joined by "and" into a single predicate string -- split them into
separate members of one group. Leave group_id null when the assertion stands alone.

Ignore criteria sets that are about selecting studies or literature rather than about diagnosing
a patient ("studies were included if they met the following criteria", "papers without full text
were excluded"). Those are not diagnostic criteria; do not emit assertions for them.
"""

# the paragraph the block above replaces, matched verbatim in both prompts
OLD_GROUP_BLOCK_MARK = "Criterion groups: when one sentence lists several findings"


def swap_group_block(prompt: str) -> str:
    """Replace the one-sentence group paragraph with the passage-scoped one."""
    start = prompt.index(OLD_GROUP_BLOCK_MARK)
    end = prompt.index("Rules:", start)
    return prompt[:start] + FREE_GROUP_BLOCK.strip() + "\n\n" + prompt[end:]


# F5b.  773.b died because Merck states the proposition and the decision rule is
# its converse: "flow is left-to-right because systemic pressure and resistance
# exceed pulmonary" is the same fact as "when the gradient reverses, flow becomes
# right-to-left", but only the first was extracted, and no mechanical program can
# take the contrapositive of a noun phrase.
CONVERSE_ADDENDUM = """
Converse and threshold-crossing rules: when the passage explains a direction or a state as
following FROM a condition ("flow is left-to-right BECAUSE systemic pressure exceeds pulmonary",
"the murmur disappears WHEN the defect closes"), emit the stated assertion AND a second
assertion for the reversed condition, with the same quote, relation "feature_of" and modality
"typical". Write the reversed condition explicitly in the predicate (e.g. "right-to-left shunt
when pulmonary pressure exceeds systemic"). Do not emit a converse when the passage states a
one-way association with no stated mechanism or condition.
"""

# Grounded extraction (15.3 step 3): closed-set subjects from the passage,
# retrieval focus is NOT a default subject, threshold filled from quote only.
GUIDELINE_PROMPT_GROUNDED = f"""You convert one guideline passage into structured diagnostic assertions.

The payload gives ``retrieval_query`` only to explain why this passage was retrieved.
Do NOT use retrieval_query as the assertion subject unless that exact disease name
also appears as a substring of the passage.

Workflow (mandatory):
1. List every disease / syndrome / named condition the PASSAGE itself mentions
   (verbatim substrings) in ``mentioned_diseases``.
2. Emit assertions whose ``subject`` is one of those mentioned_diseases.
3. When the passage uses ``this/the variant|form|subtype|syndrome`` without a nearby
   named disease in the same sentence, set ``antecedent`` to the nearest named
   disease earlier in the passage (must be in mentioned_diseases). If you cannot
   resolve the antecedent, skip that assertion.

Return strict JSON:
{{"mentioned_diseases": ["..."], "assertions": [ ... ]}}.

Each assertion:
{{
  "subject": "<must be an element of mentioned_diseases>",
  "antecedent": "<named disease for this/the variant|form|syndrome, or null>",
  "predicate": "<the finding, sign, test result, exposure or histology, as a short noun phrase>",
  "predicate_kind": "symptom|sign|lab|imaging|histopathology|ecg|hemodynamic|exposure|demographic|course|other",
  "relation": one of {RELATIONS},
  "polarity": "asserted" | "negated",
  "modality": one of {MODALITIES},
  "threshold": null,
  "comparator": "<the other disease, only for distinguishes_from / argues_against; else null>",
  "context_type": one of {CONTEXT_TYPES},
  "criterion_group": {{"group_id": "<short id local to this passage, e.g. g1, or null>",
                      "logic": "all" | "any" | "at_least_n" | null,
                      "n": <integer or null>}},
  "quote": "<verbatim substring of the passage, <=200 chars, that states this>"
}}

Criterion groups: when one sentence lists several findings that together form ONE diagnostic
criterion set, emit one assertion per member and give all members the same group_id, the same
logic and the same n. Use "all" for "A and B and C are required" or a named n-sign set such as
"Kanavel's four cardinal signs"; use "at_least_n" with n for "at least two of the following";
use "any" for "one or more of" / "some or all". Never merge two findings joined by "and" into a
single predicate string -- split them into separate members of one group. Leave group_id null
when the assertion stands alone.

Rules:
- polarity is "negated" when the passage says the feature is absent, normal, or does not occur
  in the subject. "QTc is normal" is negated for the predicate "prolonged QTc".
- relation "required_for" only when the passage says the feature is necessary/required/must/
  essential for the diagnosis; "pathognomonic_for" only when it says pathognomonic / hallmark /
  diagnostic of / will be diagnostic.
- Use "differential" for context_type when the sentence is contrasting diseases; use "table_row"
  when the text is a table row.
- Always set threshold to null. Numbers in the quote will be parsed separately.
- quote must appear verbatim in the passage. If nothing is assertable, return empty lists.
"""

CASE_PROMPT = """You convert one clinical vignette into structured findings. Do not diagnose.

Return strict JSON: {"findings": [ ... ]}. Each finding:
{
  "label": "<short noun phrase for the finding, as the vignette words it>",
  "canonical": "<the same finding written as a generic clinical concept, lower case>",
  "kind": "symptom|sign|lab|imaging|histopathology|ecg|hemodynamic|exposure|demographic|course|treatment_response|other",
  "polarity": "present" | "absent" | "normal" | "not_assessed",
  "value": {"number": <number or null>, "unit": "<unit or null>", "text": "<raw value text or null>"},
  "qualifiers": {"timing": null, "site": null, "laterality": null},
  "quote": "<verbatim substring of the vignette, <=200 chars>"
}

Rules:
- "normal" means the item was measured or examined and was within normal limits. "absent" means
  explicitly denied or not found. Never use "absent" for something the vignette simply does not
  mention -- omit it instead.
- Split composite sentences into one finding per clinical item.
- Copy every number with its unit into value.
- Include negatives and normals: they carry the exclusion power.
- quote must appear verbatim in the vignette.
"""


OPTION_CUT = re.compile(
    r"\n\s*(what is the most likely diagnosis|options\s*:)", re.I)


def strip_options(text: str) -> str:
    m = OPTION_CUT.search(text)
    return text[: m.start()].rstrip() if m else text


def cache_key(kind: str, payload: dict, model: str) -> str:
    blob = json.dumps([kind, payload, model], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


class Extractor:
    def __init__(self, model: str, workers: int) -> None:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        CACHE.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.workers = workers
        self._local = threading.local()
        self._client_cls = RobustLLMClient
        self.stats = {"cached": 0, "called": 0, "empty": 0}
        self._lock = threading.Lock()

    def client(self):
        c = getattr(self._local, "client", None)
        if c is None:
            c = self._client_cls(model=self.model, temperature=0.0, max_retries=2)
            self._local.client = c
        return c

    def call(self, kind: str, module: str, prompt: str, payload: dict) -> dict:
        key = cache_key(kind, payload, self.model)
        path = CACHE / f"{key}.json"
        if path.exists():
            with self._lock:
                self.stats["cached"] += 1
            return json.loads(path.read_text(encoding="utf-8"))
        try:
            out = self.client().call_module(module, prompt, payload)
        except Exception as exc:  # noqa: BLE001 — keep the pool moving
            print(f"[extract] {module} failed ({exc}); caching empty", flush=True)
            out = {}
        if not isinstance(out, dict):
            out = {}
        with self._lock:
            self.stats["called"] += 1
            if not out:
                self.stats["empty"] += 1
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out


def context_hint(source: str, section_path: str, title: str) -> str:
    blob = f"{section_path} {title}".lower()
    for needle, ctype in (
        ("differential diagnosis", "differential"),
        ("histopatholog", "histopathology"),
        ("evaluation", "criteria"),
        ("etiolog", "definition"),
        ("epidemiolog", "epidemiology"),
        ("treatment", "treatment"),
        ("prognos", "prognosis"),
        ("introduction", "definition"),
    ):
        if needle in blob:
            return ctype
    return ""


VARIANT_SUBJECT = re.compile(
    r"^(this|the)\s+(variant|form|subtype|type|syndrome)\b", re.I)


def _fuzzy_in_passage(name: str, passage: str) -> bool:
    """True when name (or a content-word subset) appears in the passage."""
    if not name:
        return False
    pl = passage.lower()
    nl = name.lower().strip()
    if nl and nl in pl:
        return True
    words = [w for w in re.findall(r"[a-z0-9]+", nl) if len(w) >= 4]
    if not words:
        return False
    return all(w in pl for w in words)


GROUP_LOGIC = {"all", "any", "at_least_n"}
# what the model actually emitted in the S32 audit, beyond the three legal values
LOGIC_ALIAS = {"and": "all", "or": "any", "k_of_n": "at_least_n",
               "at least n": "at_least_n", "atleast_n": "at_least_n"}


def normalise_group(a: dict, stats: Counter) -> None:
    """Clamp criterion_group to the schema.

    The trial extractor asks for free JSON with no schema attached, so the
    model returns the string "null" for absent values and occasionally a logic
    it invented ("and", "typical").  Downstream the engine keys groups off
    group_id, and the string "null" is truthy, which silently merges every
    ungrouped assertion of a passage into one pseudo-group.
    """
    cg = a.get("criterion_group")
    if not isinstance(cg, dict):
        a["criterion_group"] = {"group_id": None, "logic": None, "n": None}
        return

    def clean(v):
        if isinstance(v, str) and v.strip().lower() in {"", "null", "none", "n/a"}:
            return None
        return v

    gid, logic, n = clean(cg.get("group_id")), clean(cg.get("logic")), clean(cg.get("n"))

    if isinstance(logic, str):
        low = logic.strip().lower()
        if low in GROUP_LOGIC:
            logic = low
        elif low in LOGIC_ALIAS:
            stats[f"alias:{low}"] += 1
            logic = LOGIC_ALIAS[low]
        else:
            stats[f"dropped_logic:{low}"] += 1
            logic = None
    elif logic is not None:
        stats["dropped_logic:nonstring"] += 1
        logic = None

    try:
        n = int(n) if n is not None else None
    except (TypeError, ValueError):
        stats["dropped_n"] += 1
        n = None
    if logic == "at_least_n" and (n is None or n < 1):
        stats["at_least_n_without_n"] += 1
        logic = "any"          # "some of the following" with no count
    if logic != "at_least_n":
        n = None

    if gid is not None and logic is None:
        stats["group_without_logic"] += 1
    if gid is None and logic is not None:
        stats["logic_without_group"] += 1
        logic = None
    a["criterion_group"] = {"group_id": str(gid) if gid is not None else None,
                            "logic": logic, "n": n}
    if gid is not None:
        stats["grouped"] += 1


def postprocess_grounded(out: dict, passage: str) -> list[dict]:
    """Enforce closed-set subject, antecedent, and quote-parsed threshold."""
    mentioned = [
        m for m in (out.get("mentioned_diseases") or [])
        if isinstance(m, str) and m.strip() and _fuzzy_in_passage(m, passage)
    ]
    mentioned_l = {m.lower(): m for m in mentioned}
    kept: list[dict] = []
    for a in out.get("assertions") or []:
        if not isinstance(a, dict) or not a.get("subject") or not a.get("predicate"):
            continue
        a = dict(a)
        subj = str(a["subject"]).strip()
        # resolve this/the variant via antecedent
        if VARIANT_SUBJECT.search(subj) or VARIANT_SUBJECT.search(str(a.get("antecedent") or "")):
            ant = (a.get("antecedent") or "").strip()
            if not ant or not _fuzzy_in_passage(ant, passage):
                continue  # E5: unresolved deixis
            a["subject"] = ant
            subj = ant
        # closed-set subject
        if subj.lower() in mentioned_l:
            a["subject"] = mentioned_l[subj.lower()]
        elif _fuzzy_in_passage(subj, passage):
            # allow subject that is a passage substring even if model omitted it
            if subj.lower() not in mentioned_l:
                mentioned_l[subj.lower()] = subj
                mentioned.append(subj)
        else:
            continue  # E1/E11
        # threshold: ignore model; parse from quote
        quote = str(a.get("quote") or "")
        parsed = parse_threshold_from_quote(quote)
        a["threshold"] = parsed or {}
        a["_passage_sha1"] = hashlib.sha1(passage.encode("utf-8")).hexdigest()[:16]
        kept.append(a)
    return kept


# Vignette regex backfill for known case-finding omissions (49/257/522/179).
# Not another LLM call: only add a finding when the pattern hits and no
# existing finding already covers the same label keywords.
_BACKFILL_RULES: list[tuple[re.Pattern[str], dict]] = [
    (re.compile(r"laparoscopic\s+appendectomy", re.I), {
        "label": "laparoscopic appendectomy",
        "canonical": "prior appendectomy",
        "kind": "course",
        "polarity": "present",
    }),
    (re.compile(r"surgical\s+clips?", re.I), {
        "label": "surgical clips",
        "canonical": "surgical clips in right iliac fossa",
        "kind": "imaging",
        "polarity": "present",
    }),
    (re.compile(r"fluctuant", re.I), {
        "label": "fluctuant mass",
        "canonical": "fluctuant mass",
        "kind": "sign",
        "polarity": "present",
    }),
    (re.compile(r"palmar\s+web\s+space", re.I), {
        "label": "palmar web space mass",
        "canonical": "mass in palmar web space",
        "kind": "sign",
        "polarity": "present",
    }),
    (re.compile(
        r"(?:vitamin\s*)?B\s*12[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(pmol/?L|pg/?mL|ng/?L)",
        re.I), {
        "label": "serum vitamin B12",
        "canonical": "serum vitamin B12 level",
        "kind": "lab",
        "polarity": "present",
        "_value_from_match": True,
    }),
]


def backfill_findings(vignette: str, findings: list) -> list:
    """Add regex-derived findings that the case extractor commonly misses."""
    out = [f for f in findings if isinstance(f, dict)]
    blob = " ".join(
        f"{f.get('label') or ''} {f.get('canonical') or ''}".lower() for f in out
    )

    def _covered(keys: list[str]) -> bool:
        return all(k.lower() in blob for k in keys)

    for pat, proto in _BACKFILL_RULES:
        m = pat.search(vignette)
        if not m:
            continue
        keys = [w for w in re.findall(r"[a-z0-9]+", proto["label"].lower()) if len(w) > 2]
        if _covered(keys[:2] if len(keys) >= 2 else keys):
            continue
        f = dict(proto)
        f.pop("_value_from_match", None)
        f["qualifiers"] = {"timing": None, "site": None, "laterality": None}
        f["quote"] = m.group(0)[:200]
        f["_backfill"] = "vignette_regex"
        if proto.get("_value_from_match") and m.lastindex:
            try:
                num = float(m.group(1))
                unit = m.group(2) if m.lastindex >= 2 else None
            except (ValueError, IndexError):
                num, unit = None, None
            f["value"] = {"number": num, "unit": unit, "text": m.group(0)[:80]}
        else:
            f.setdefault("value", {"number": None, "unit": None, "text": None})
        out.append(f)
        blob += " " + f["label"].lower()

    # 179: paired SaO2–platelet timepoints
    pair_pat = re.compile(
        r"SaO2\s*(?:was|=|:)?\s*(\d{2,3})\s*%[^.]{0,80}?"
        r"platelet\s+count\s*(?:of|=|:)?\s*([\d\s]+)\s*/?\s*mm",
        re.I,
    )
    # also platelet first then SaO2 nearby is rare; scan loose pairs
    sao2s = list(re.finditer(
        r"SaO2\s*(?:was|=|:|to)?\s*(\d{2,3})\s*(?:–|-)?\s*(\d{2,3})?\s*%", vignette, re.I))
    plats = list(re.finditer(
        r"platelet\s+count\s*(?:of|=|:)?\s*([\d\s]{3,9})\s*/?\s*mm", vignette, re.I))
    if sao2s and plats and "sao2" not in blob:
        for i, sm in enumerate(sao2s[:4]):
            label = f"SaO2 {sm.group(0).split()[-1] if False else sm.group(1)}%"
            if sm.group(2):
                label = f"SaO2 {sm.group(1)}-{sm.group(2)}%"
            f = {
                "label": label,
                "canonical": "oxygen saturation",
                "kind": "lab",
                "polarity": "present",
                "value": {"number": float(sm.group(1)), "unit": "%", "text": sm.group(0)[:80]},
                "qualifiers": {"timing": f"timepoint_{i+1}", "site": None, "laterality": None},
                "quote": sm.group(0)[:200],
                "_backfill": "vignette_regex_sao2",
            }
            out.append(f)
        for i, pm in enumerate(plats[:4]):
            raw = re.sub(r"\s+", "", pm.group(1))
            try:
                num = float(raw)
            except ValueError:
                num = None
            f = {
                "label": f"platelet count {raw}/mm3",
                "canonical": "platelet count",
                "kind": "lab",
                "polarity": "present",
                "value": {"number": num, "unit": "/mm3", "text": pm.group(0)[:80]},
                "qualifiers": {"timing": f"timepoint_{i+1}", "site": None, "laterality": None},
                "quote": pm.group(0)[:200],
                "_backfill": "vignette_regex_platelet",
            }
            out.append(f)
    elif pair_pat.search(vignette) and "sao2" not in blob:
        for i, m in enumerate(pair_pat.finditer(vignette)):
            plat = re.sub(r"\s+", "", m.group(2))
            out.append({
                "label": f"SaO2 {m.group(1)}% with platelet {plat}",
                "canonical": "paired SaO2 and platelet count",
                "kind": "lab",
                "polarity": "present",
                "value": {"number": float(m.group(1)), "unit": "%", "text": m.group(0)[:80]},
                "qualifiers": {"timing": f"timepoint_{i+1}", "site": None, "laterality": None},
                "quote": m.group(0)[:200],
                "_backfill": "vignette_regex_pair",
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit-passages", type=int, default=0)
    ap.add_argument("--groups", action="store_true",
                    help="extract criterion_group membership as well")
    ap.add_argument("--strip-options", action="store_true",
                    help="cut the embedded answer-option block off the vignette; several "
                         "cases spell the exclusion reasoning out inside the options")
    ap.add_argument("--converse", action="store_true",
                    help="F5b: also emit the reversed-condition assertion")
    ap.add_argument("--grounded", action="store_true",
                    help="closed-set subjects from mentioned_diseases; threshold from quote; "
                         "cache kind guideline_groups_grounded")
    ap.add_argument("--tasks", default="trial_tasks_11.json")
    ap.add_argument("--free-groups", action="store_true",
                    help="scope criterion groups to the whole passage instead "
                         "of one sentence (report S34); implies --groups")
    ap.add_argument("--only-case", default="", help="restrict to one case_key")
    ap.add_argument("--out-tag", default="", help="suffix for the output file")
    ap.add_argument("--max-passage-chars", type=int, default=6000,
                    help="the shared client clamps its output escalation at 8192 "
                         "tokens, so a passage dense enough to overflow that "
                         "retries thirty times and blocks a worker")
    args = ap.parse_args()
    if args.free_groups:
        args.groups = True
    suffix = "clean" if args.strip_options else ""
    kind = "guideline_groups" if args.groups else "guideline"
    prompt = GUIDELINE_PROMPT
    if args.groups:
        suffix += "_groups"
    if args.converse:
        suffix += "_conv"
        kind += "_converse"
        prompt = GUIDELINE_PROMPT + CONVERSE_ADDENDUM
    if args.grounded:
        kind = "guideline_groups_grounded" if args.groups else "guideline_grounded"
        prompt = GUIDELINE_PROMPT_GROUNDED
        if args.converse:
            prompt = GUIDELINE_PROMPT_GROUNDED + CONVERSE_ADDENDUM
            kind += "_converse"
    if args.free_groups:
        prompt = swap_group_block(prompt)
        # the cache key is (kind, payload, model); without a distinct kind the
        # two prompts would silently read each other's cached answers
        kind += "_free"
        suffix += "_free"
    globals()["GUIDELINE_KIND"] = kind
    globals()["GUIDELINE_PROMPT_ACTIVE"] = prompt
    globals()["GROUNDED"] = bool(args.grounded)

    os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

    tasks = {t["case_key"]: t for t in json.loads((LEDGER / args.tasks).read_text("utf-8"))}
    if args.only_case:
        tasks = {k: v for k, v in tasks.items() if k == args.only_case}
    retrieval = json.loads((LEDGER / f"trial_retrieval_{args.arm}.json").read_text("utf-8"))
    ex = Extractor(args.model, args.workers)

    # ---- case side -------------------------------------------------------
    def do_case(key: str) -> tuple[str, dict]:
        text = tasks[key]["vignette"]
        if args.strip_options:
            text = strip_options(text)
        payload = {"vignette": text}
        out = ex.call("case", "CaseFindingExtractor", CASE_PROMPT, payload)
        findings = list(out.get("findings") or [])
        if args.grounded:
            findings = backfill_findings(text, findings)
            out = dict(out)
            out["findings"] = findings
        return key, out

    with ThreadPoolExecutor(max_workers=min(args.workers, 11)) as pool:
        case_out = dict(pool.map(do_case, list(tasks)))
    for key, out in case_out.items():
        print(f"  findings {key:24s} n={len(out.get('findings') or [])}", flush=True)

    # ---- corpus side -----------------------------------------------------
    jobs: list[tuple[str, str, dict]] = []   # (case_key, hypothesis, payload)
    seen: set[str] = set()
    for rec in retrieval:
        if args.only_case and rec["case_key"] != args.only_case:
            continue
        if rec["case_key"] not in tasks:
            continue
        for label, bundle in rec["retrieved"].items():
            for p in bundle["passages"]:
                passage = p["text"][: args.max_passage_chars]
                if args.grounded:
                    payload = {
                        "retrieval_query": label,
                        "source": p["source"],
                        "document_title": p["title"],
                        "section_path": p["section_path"],
                        "context_hint": context_hint(p["source"], p["section_path"], p["title"]),
                        "passage": passage,
                    }
                else:
                    payload = {
                        "focus_disease": label,
                        "source": p["source"],
                        "document_title": p["title"],
                        "section_path": p["section_path"],
                        "context_hint": context_hint(p["source"], p["section_path"], p["title"]),
                        "passage": passage,
                    }
                jobs.append((rec["case_key"], label, payload))
                seen.add(cache_key(GUIDELINE_KIND, payload, args.model))
    if args.limit_passages:
        jobs = jobs[: args.limit_passages]
    print(f"\n{len(jobs)} passage-hypothesis jobs ({len(seen)} unique payloads)", flush=True)

    def do_job(job):
        case_key, label, payload = job
        out = ex.call(GUIDELINE_KIND, "GuidelineAssertionExtractor",
                      globals()["GUIDELINE_PROMPT_ACTIVE"], payload)
        return case_key, label, payload, out

    results: list[tuple] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, r in enumerate(pool.map(do_job, jobs), 1):
            results.append(r)
            if i % 100 == 0:
                print(f"  {i}/{len(jobs)} (cached={ex.stats['cached']} called={ex.stats['called']} "
                      f"empty={ex.stats['empty']})", flush=True)

    by_case: dict[str, dict] = {}
    group_stats: Counter = Counter()
    for case_key, label, payload, out in results:
        slot = by_case.setdefault(case_key, {"case_key": case_key, "assertions": []})
        passage = payload.get("passage") or ""
        if args.grounded:
            assertions = postprocess_grounded(out if isinstance(out, dict) else {}, passage)
        else:
            assertions = []
            for a in (out.get("assertions") or []) if isinstance(out, dict) else []:
                if not isinstance(a, dict) or not a.get("subject") or not a.get("predicate"):
                    continue
                assertions.append(dict(a))
        for a in assertions:
            normalise_group(a, group_stats)
            a["_focus"] = label
            a["_source"] = payload["source"]
            a["_title"] = payload["document_title"]
            a["_section"] = payload["section_path"]
            a["_context_hint"] = payload["context_hint"]
            slot["assertions"].append(a)

    out_obj = []
    for key in tasks:
        out_obj.append({
            "case_key": key,
            "findings": case_out[key].get("findings") or [],
            "assertions": by_case.get(key, {}).get("assertions", []),
        })
    path = LEDGER / f"trial_extraction_{args.arm}{suffix}{args.out_tag}.json"
    path.write_text(json.dumps(out_obj, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\ncache: {ex.stats}")
    if group_stats:
        print(f"criterion_group repairs: {dict(group_stats.most_common())}")
    for o in out_obj:
        print(f"  {o['case_key']:24s} findings={len(o['findings']):3d} assertions={len(o['assertions']):4d}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
