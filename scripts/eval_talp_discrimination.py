"""Block 1 of the TALP discrimination-capability test: the LLM's OWN capability
boundary (llama, NO knowledge base) PLUS an optional LLM+KB "potential" arm.

TALP's job is to pick the best evidence to DISCRIMINATE among candidate leaves
(`controller.plan_temporary_leaves`; scoring is purely LLM-self-reported, no
deterministic value-of-information). So the ceiling of that machinery is the raw
LLM. This harness isolates it: feed the vignette + a hand-built L2 candidate set
(correct leaf + strong distractors, some under different L1 parents) from
`data/eval/talp_discrimination_cases.json`, and measure:

  SELECT@1 / SELECT@2 : the LLM names the single most useful finding/test to
      separate the leading candidates; an LLM judge checks whether it matches one
      of the hand-curated DECISIVE discriminators (top-1 / within top-2).
  DIRECTION (rule-in)  : for each `rule_in_gold` finding, the LLM predicts which
      candidate it favors. Accuracy vs the dataset role.
  RULE-OUT             : for each `rule_out_distractor` finding, the LLM predicts
      which candidate the finding argues AGAINST. Accuracy vs `direction_target`
      (reported SEPARATELY from rule-in — rule-out is a distinct capability).
  SHARED-trap          : `shared_nondiscriminating` findings; correct answer for
      DIRECTION is "none" — measures whether the LLM avoids FALSE discrimination.
  PARENT/CHILD         : for cases with a `parent_child` block, two tests:
      TRAP  — a `parent_child_trap` finding (present in a child subtype) must NOT
              be read as ruling OUT the parent family.
      LIFT  — a child-specific decisive `rule_in_gold` finding SHOULD rule IN
              (support) the parent family.

  --kb : run a SECOND pass that injects the fused best-knowledge block
      (LR-grounded + CPG-mined + case_report-mined; from eval_evidence_precision.
      build_fused_discriminator_hints) into the SELECT/DIRECTION prompts, to
      measure the LLM-alone vs LLM+KB LIFT. Emits logs/talp_discrim_llm.json and
      logs/talp_discrim_kb.json.

    PYTHONPATH=src python scripts/eval_talp_discrimination.py [--model ...] [--kb]
Requires the gnn-llm env + VPN. --kb additionally loads the KB indices.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

DATA = PROJECT_ROOT / "data"


def load_vignettes() -> dict[str, str]:
    """gold_option (== runtime answer string) -> vignette question stem."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mb", PROJECT_ROOT / "scripts" / "eval_pipeline_medbullets.py")
    mb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mb)
    out = {}
    for c in mb.load_dx_cases():
        if not c["is_image"]:
            out[c["answer"].strip()] = c["q"].strip()
    return out


_SELECT_PROMPT = (
    "You are a diagnostician. Given a clinical vignette and a list of candidate "
    "diagnoses, decide the SINGLE most useful additional finding, test, or lab that "
    "would best DISCRIMINATE among these candidates (maximally separate the leading "
    "ones). Prefer a finding that is present in one candidate and absent in the "
    "others; avoid findings shared by most candidates. If a "
    "'typed_findings' list is provided, use its event type, terminology concepts, "
    "polarity and temporal fields as disambiguation aids; an empty concept list "
    "means abstention, not absence of clinical evidence. If a "
    "'non_discriminating_findings' list is provided, those findings are COMMON to "
    "several candidates and MUST NOT be chosen as the discriminator. If a "
    "'discriminator_rules' block is provided, follow its guidance: PREFER a "
    "finding it marks PREFER (evidence-grounded discriminator) and do NOT choose "
    "one it marks AVOID (evidence-grounded non-discriminating). Return STRICT "
    'JSON: {"best_discriminator": "<short finding/test name>", '
    '"ranked": ["<disc1>", "<disc2>", "<disc3>"], "rationale": "<one sentence>"}.')

_DIRECTION_PROMPT = (
    "You are a diagnostician. Given a clinical vignette, a list of candidate "
    "diagnoses, and ONE finding, decide which SINGLE candidate the finding most "
    "supports. If the finding is roughly equally common across the candidates "
    "(non-discriminating), answer exactly \"none\". If a "
    "'typed_finding' record is provided, honor its event type, concepts, polarity "
    "and temporal context; do not treat concept abstention as negative evidence. "
    "If a "
    "'non_discriminating_findings' list is provided and the finding appears in it "
    "(or is clinically equivalent to an item in it), you MUST answer \"none\". "
    "If a 'discriminator_rules' block is provided and the finding matches a rule "
    "there, use that rule's stated direction (it names the candidate the finding — "
    "at its stated result value — supports); if instead the finding is listed "
    "under 'NON-DISCRIMINATING', you MUST answer \"none\"; if it is listed under "
    "'LIKELY NON-SPECIFIC', treat it as WEAK evidence and answer \"none\" unless "
    "the vignette clearly ties it to ONE candidate; findings NOT in the "
    "block are judged normally. Answer ONLY with a candidate name copied verbatim "
    "from the list, or \"none\". "
    'Return STRICT JSON: {"favored": "<candidate name | none>", '
    '"why": "<one sentence>"}.')

_RULEOUT_PROMPT = (
    "You are a diagnostician. Given a clinical vignette, a list of candidate "
    "diagnoses, and ONE finding, decide which SINGLE candidate the finding argues "
    "MOST STRONGLY AGAINST (i.e. makes LEAST likely / helps RULE OUT). If the "
    "finding does not specifically argue against any one candidate, answer exactly "
    "\"none\". If a 'ruleout_rules' list is provided and the finding matches a "
    "rule there, use that rule's named RULE-OUT candidate (these carry a "
    "STRUCTURED, evidence-compiled rule_out effect — NOT prose about which "
    "candidate the finding supports). Answer ONLY with a candidate name copied "
    "verbatim from the list, or \"none\". Return STRICT JSON: "
    '{"argues_against": "<candidate name | none>", "why": "<one sentence>"}.')

_PARENT_PROMPT = (
    "You are a diagnostician reasoning about a DIAGNOSTIC FAMILY (a parent "
    "category that contains several subtypes). Given the vignette, the PARENT "
    "family name, and ONE finding, decide the finding's effect on the PROBABILITY "
    "OF THE PARENT FAMILY as a whole. Note: a finding that is characteristic of "
    "ONE SUBTYPE within the family still SUPPORTS (or is at worst NEUTRAL to) the "
    "parent family — it must NOT be treated as ruling the family out. Answer with "
    "exactly one of \"supports\", \"rules_out\", or \"neutral\". Return STRICT "
    'JSON: {"effect_on_parent": "supports|rules_out|neutral", "why": "<one '
    'sentence>"}.')

_DISC_AGENT_PROMPT = (
    "You are a DISCRIMINATOR-COMPILER agent. You are given ONE contested clinical "
    "finding/test, the candidate diagnoses, and EVIDENCE EXCERPTS retrieved from "
    "guidelines / case reports / likelihood-ratio tables. Your ONLY job is to "
    "compile, STRICTLY FROM THE EVIDENCE, how this finding should be used to tell "
    "the candidates apart — being explicit about the RESULT VALUE (e.g. HIGH vs LOW "
    "vs NORMAL), because the same test points opposite ways at different values "
    "(elevated PTH rules IN primary hyperparathyroidism and rules OUT milk-alkali; "
    "low/normal PTH does the reverse). "
    "HARD RULES: (1) Ground every claim in the provided evidence; if the evidence "
    "does NOT state a clear contrast for this finding across the candidates, you "
    "MUST return verdict \"common\" (do not guess from prior knowledge). (2) A "
    "negated/normal result must NOT rule IN the disease its bare marker points to. "
    "Return STRICT JSON: {\"verdict\": \"use|common\", "
    "\"value_condition\": \"<the result value this rule is about, or empty>\", "
    "\"rule_in\": \"<candidate name copied verbatim | empty>\", "
    "\"rule_out\": [\"<candidate name>\", ...], \"why\": \"<one sentence citing the "
    "evidence>\"}.")

# ── v2 (roadmap P3): full candidate-effect MATRIX, neutral vs unknown split ────
_DISC_AGENT_MATRIX_PROMPT = (
    "You are a DISCRIMINATOR-COMPILER agent. You are given ONE contested clinical "
    "finding/test (with its parsed result value/polarity when available), the "
    "candidate diagnoses, and EVIDENCE EXCERPTS (each tagged with an id like E1, a "
    "source, and the candidate it was retrieved for). Compile, STRICTLY FROM THE "
    "EVIDENCE, how this finding bears on EACH candidate. Be explicit about the "
    "RESULT VALUE (HIGH/LOW/NORMAL/ABSENT), because a test points opposite ways at "
    "different values (elevated PTH rules IN primary hyperparathyroidism and rules "
    "OUT milk-alkali; low/normal PTH does the reverse). "
    "For every candidate assign exactly one effect: "
    "'rule_in' (evidence states the finding — at this value — is present/typical/"
    "specific for it AND contrasts it from others), 'rule_out' (evidence states "
    "the finding argues AGAINST it), 'neutral' (evidence shows the finding is "
    "COMPATIBLE/present but does NOT distinguish it — a genuinely COMMON finding), "
    "or 'unknown' (the evidence does NOT say — insufficient, do NOT guess). "
    "CRITICAL: 'neutral' means 'there IS evidence and it shows no discriminating "
    "power'; 'unknown' means 'evidence is silent'. Keep them strictly separate. "
    "A finding is DISCRIMINATING only if >=1 candidate is rule_in/rule_out with a "
    "grounded contrast; if the best you can ground is that it is present across "
    "candidates, set discriminating=false and mark them neutral. Cite the excerpt "
    "ids you used per candidate. A negated/normal result must NOT rule IN the "
    "disease its bare marker points to. Return STRICT JSON: "
    '{"discriminating": true|false, '
    '"value_condition": "<result value this reading is about, or empty>", '
    '"candidate_effects": [{"candidate": "<verbatim name>", '
    '"effect": "rule_in|rule_out|neutral|unknown", '
    '"strength": "high|moderate|weak", "evidence_ids": ["E1", ...], '
    '"why": "<short, citing the evidence>"}], '
    '"why": "<one sentence overall>"}.')

# ── corpus-grounded phenotype MEMBERSHIP (distinct from the effect matrix) ──────
# Answers, per candidate and STRICTLY from that candidate's own retrieved text,
# the atomic question "is F an established/typical feature of disease D?" — NOT
# "does F discriminate D from others?". This is the unstructured analog of a KG
# phenotype set: it closes the KG's synonym gap ('hypercalcemia' == 'elevated
# calcium') and its true-absence gap (adhesions, sigmoid volvulus have no KG
# entry but ARE described in CPG/case-report text). It is deliberately framed as
# membership, not contrast, so it does NOT inherit the effect-matrix's tendency
# to upgrade a co-mentioned contrast into a rule_in.
_PHENO_MEMBER_PROMPT = (
    "You are a MEDICAL FEATURE-MEMBERSHIP checker. You are given ONE clinical "
    "finding/test result, the candidate diagnoses, and EVIDENCE EXCERPTS (each "
    "tagged with an id, a source, and the CANDIDATE it was retrieved for). For "
    "EACH candidate decide, USING ONLY that candidate's own excerpts, whether "
    "the finding is an ESTABLISHED / TYPICAL / RECOGNISED FEATURE of that disease "
    "(i.e. the disease can itself produce this finding). This is a MEMBERSHIP "
    "question, NOT a discrimination question: a finding may be a typical feature "
    "of SEVERAL candidates at once — say 'yes' for each one it is typical of. "
    "Do NOT judge whether it tells the diseases apart. Treat medically equivalent "
    "wording as the same feature (e.g. 'hypercalcemia' == 'elevated serum "
    "calcium'; 'leukocytosis' == 'raised white cell count'). Answer 'yes' only if "
    "the text supports it as a feature of THAT disease; 'no' if the text "
    "indicates it is NOT a feature / is atypical / argues against; 'unknown' if "
    "that candidate's excerpts are silent.{value_clause} Return STRICT JSON: "
    '{"membership": [{"candidate": "<verbatim name>", '
    '"member": "yes|no|unknown", "evidence_ids": ["E1", ...], '
    '"why": "<short, citing the evidence>"}]}.')

# Value-conditioning clause appended when the finding carries a direction/value.
# This is the fix for the §E1h PTH trap: "PTH" is a feature of every hypercalcemia
# candidate, but ELEVATED PTH is a feature of primary hyperparathyroidism ONLY —
# milk-alkali / malignancy have SUPPRESSED PTH. Membership must respect the value.
_VALUE_CLAUSE = (
    " CRITICAL — RESULT VALUE: the finding's result is {value_desc}. A test "
    "points OPPOSITE ways at different values, so judge membership of the finding "
    "AT THIS VALUE, not the bare test. e.g. ELEVATED parathyroid hormone is a "
    "feature of primary hyperparathyroidism but NOT of milk-alkali syndrome or "
    "malignancy (which have SUPPRESSED PTH) — answer 'no' for those. A "
    "normal/negated result is NOT a feature of the disease its raw marker points "
    "to.")

# ── v2 (roadmap P6): independent ENTAILMENT validator (decoupled from compiler) ─
_ENTAIL_PROMPT = (
    "You are an EVIDENCE ENTAILMENT checker (NOT a clinician giving an opinion). "
    "You are given a CLAIM of the form 'finding F (at value V) rules IN candidate "
    "A and rules OUT competitors B...', plus the EVIDENCE EXCERPTS the claim cites. "
    "Decide ONLY whether the quoted evidence TEXT explicitly entails BOTH halves: "
    "(1) F-at-V is present/typical/stronger for A, AND (2) F-at-V is absent/weaker/"
    "argues against at least one competitor. Judge textual entailment, NOT whether "
    "the claim is medically plausible. If the evidence only says F occurs in A "
    "(a single-disease association with NO competitor contrast), that is NOT "
    "entailment -> 'no'. If excerpts CONTRADICT each other (general rule vs rare "
    "exception), answer 'conflict'. Return STRICT JSON: "
    '{"entailed": "yes|no|conflict", "has_support": true|false, '
    '"has_contrast": true|false, "why": "<one sentence>"}.')

_JUDGE_PROMPT = (
    "You compare a diagnostician's proposed discriminating finding against a list "
    "of reference KEY discriminators (with clinical notes). Decide whether the "
    "proposal refers to the SAME clinical discriminator as any reference item (by "
    "meaning, not wording; e.g. 'LAP score' == 'leukocyte alkaline phosphatase'; "
    "'copper studies' == 'urinary copper' / 'ceruloplasmin'). Return STRICT JSON "
    "with BOTH fields: "
    '{"match_index": <int, 0-based index into references, or -1 if none>, '
    '"matched_finding": "<the reference finding text you matched, or empty>"}.')


def judge_match(llm, proposal: str, references: list[dict]) -> int:
    if not proposal or not references:
        return -1
    norm_proposal = _norm(re.sub(r"[^a-zA-Z0-9 ]+", " ", proposal))
    for i, ref in enumerate(references):
        aliases = [ref.get("finding", "")] + list(ref.get("select_aliases") or [])
        for alias in aliases:
            norm_alias = _norm(re.sub(r"[^a-zA-Z0-9 ]+", " ", alias))
            if norm_alias and (
                norm_alias == norm_proposal
                or norm_alias in norm_proposal
                or norm_proposal in norm_alias
            ):
                return i
    payload = {
        "proposal": proposal,
        "references": [{"i": i, "finding": r["finding"], "note": r.get("note", "")}
                       for i, r in enumerate(references)],
    }
    try:
        res = llm.call_module("DiscriminatorJudge", _JUDGE_PROMPT, payload)
        return int(res.get("match_index", -1))
    except Exception:  # noqa: BLE001
        return -1


_VALID_PROMPT = (
    "A diagnostician proposed a discriminating finding/test to tell a GOLD "
    "diagnosis apart from competing candidates. Judge ONLY whether the proposal is "
    "a CLINICALLY VALID discriminator: obtaining it would meaningfully shift "
    "probability toward or away from the gold relative to the other candidates "
    "(present in gold and typically absent in others, or vice versa). A test shared "
    "equally by all candidates is NOT valid. Return STRICT JSON with both fields: "
    '{"valid": true|false, "reason": "<one sentence>"}.')


def judge_valid(llm, proposal: str, gold: str, candidates: list[str]) -> bool:
    if not proposal:
        return False
    payload = {"proposal": proposal, "gold": gold,
               "other_candidates": [c for c in candidates if _norm(c) != _norm(gold)]}
    try:
        res = llm.call_module("DiscriminatorValidity", _VALID_PROMPT, payload)
        return bool(res.get("valid", False))
    except Exception:  # noqa: BLE001
        return False


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def match_candidate(answer: str, candidates: list[dict]) -> str:
    """Map a free-text LLM candidate answer to a canonical candidate name (or '')."""
    a = _norm(answer)
    if a in ("none", "non-discriminating", "shared", "neither", ""):
        return "none"
    names = [c["name"] for c in candidates]
    for n in names:
        if _norm(n) == a:
            return n
    for n in names:  # substring either direction
        if _norm(n) in a or a in _norm(n):
            return n
    return ""


def _expected_direction(role: str, f: dict, gold_name: str,
                        cands: list[dict]) -> str:
    """rule_in_gold -> gold; shared/parent_child_trap -> none (leaf level)."""
    if role == "rule_in_gold":
        return gold_name
    return "none"


def _resolve_name(want: str, cands: list[dict]) -> str:
    return next((c["name"] for c in cands if _norm(c["name"]) == _norm(want)),
                want)


def _typed_select_context(case: dict) -> list[dict]:
    """Typed SELECT context may expose only facts already in the vignette."""
    return [
        {"finding": f["finding"],
         "event_type": f["typed_finding"].get("event_type"),
         "concepts": f["typed_finding"].get("concepts", []),
         "temporal": f["typed_finding"].get("temporal", {})}
        for f in case["findings"]
        if f.get("typed_finding") and f.get("in_vignette", False)
    ]


def run_arm(llm, ds, vign, seed: int, kb_blocks: dict | None, tag: str,
            common_blocks: dict | None = None,
            disc_blocks: dict | None = None, local_ds: bool = False,
            select_pool: str = "legacy", candidate_order: str = "shuffle",
            judge_llm=None) -> dict:
    """One evaluation pass. kb_blocks maps case_id -> fused KB block string (or
    None for the LLM-alone arm). common_blocks maps case_id -> an explicit
    "these findings are COMMON to multiple candidates, do NOT discriminate on
    them" block (the denoise arm); None disables it. disc_blocks maps case_id ->
    the discriminator-agent-compiled USE/COMMON rule block (the --disc-agent
    arm); None disables it."""
    rng = random.Random(seed)
    kb_blocks = kb_blocks or {}
    common_blocks = common_blocks or {}
    disc_blocks = disc_blocks or {}
    rows = []
    tot = {"sel1": 0, "sel2": 0, "sel_valid": 0, "n_sel": 0,
           "dir_ok": 0, "dir_n": 0, "ruleout_ok": 0, "ruleout_n": 0,
           "shared_ok": 0, "shared_n": 0,
           "trap_ok": 0, "trap_n": 0, "lift_ok": 0, "lift_n": 0}
    judge_llm = judge_llm or llm
    for case_pos, case in enumerate(ds["cases"]):
        gold_opt = case["gold_option"]
        # Expansion datasets may embed their source vignette directly instead
        # of relying on the MedBullets answer->question join.
        vtext = str(case.get("vignette") or vign.get(gold_opt, "")).strip()
        if not vtext:
            print(f"[skip] {case['id']}: no vignette match for {gold_opt!r}")
            continue
        kb_block = kb_blocks.get(case["id"], "")
        common_block = common_blocks.get(case["id"], "")
        # disc_blocks[case_id] is EITHER a legacy combined string (v1 arm: applied
        # to SELECT + DIRECTION) OR a routed dict {select,direction,ruleout,parent}
        # (v2 roadmap P7: each consumer reads only its own structured field).
        _raw_disc = disc_blocks.get(case["id"], "")
        if isinstance(_raw_disc, dict):
            disc_sel = _raw_disc.get("select") or ""
            disc_dir = _raw_disc.get("direction") or ""
            disc_ro = _raw_disc.get("ruleout") or ""
            disc_parent = _raw_disc.get("parent") or ""
        else:
            disc_sel = disc_dir = _raw_disc
            disc_ro = disc_parent = ""
        cands = list(case["candidates"])
        if candidate_order == "shuffle":
            rng.shuffle(cands)
        elif candidate_order == "rotations" and cands:
            shift = (seed + case_pos) % len(cands)
            cands = cands[shift:] + cands[:shift]
        cand_names = [c["name"] for c in cands]
        gold_name = next(c["name"] for c in cands if c["is_gold"])
        if select_pool == "additional_only":
            decisive = [f for f in case["findings"]
                        if f.get("decisive") and not f.get("in_vignette", False)]
        elif select_pool == "typed_effect":
            decisive = [
                f for f in case["findings"]
                if any(e.get("effect") in {"rule_in", "rule_out"}
                       and e.get("strength") in {"high", "moderate"}
                       for e in (f.get("candidate_effects") or []))
            ]
        else:
            decisive = [f for f in case["findings"] if f.get("decisive")]

        def _payload(extra: dict, field: str = "dir",
                     cand_override: list | None = None) -> dict:
            p = {"vignette": vtext,
                 "candidates": cand_override or cand_names, **extra}
            if field == "select":
                typed = _typed_select_context(case)
                if typed:
                    p["typed_findings"] = typed
            if kb_block:
                p["knowledge_base_signals"] = kb_block
            if common_block:
                p["non_discriminating_findings"] = common_block
            # Route each consumer to its own block. Legacy v1 (`disc_sel ==
            # disc_dir` string) still injects the SAME prose into SELECT +
            # DIRECTION and nothing into RULE-OUT (its old scope). v2/P7 supplies
            # a STRUCTURED rule_out field so RULE-OUT can safely consume evidence
            # without the rule-IN prose that regressed it (77%->44%) the first time.
            if field == "select" and disc_sel:
                p["discriminator_rules"] = disc_sel
            elif field == "dir" and disc_dir:
                p["discriminator_rules"] = disc_dir
            elif field == "ruleout" and disc_ro:
                p["ruleout_rules"] = disc_ro
            return p

        # SELECT ---------------------------------------------------------------
        sel = {}
        try:
            sel = llm.call_module("DiscriminatorSelect", _SELECT_PROMPT,
                                  _payload({}, field="select"))
        except Exception as e:  # noqa: BLE001
            print(f"[err select] {case['id']}: {e}")
        best = str(sel.get("best_discriminator", "") or "")
        ranked = [str(x) for x in (sel.get("ranked") or [])][:2] or [best]
        m1 = judge_match(judge_llm, best, decisive)
        m2 = m1 if m1 >= 0 else max(
            (judge_match(judge_llm, r, decisive) for r in ranked), default=-1)
        sel_match = m1 >= 0
        sel_valid = judge_valid(judge_llm, best, gold_name, cand_names)
        # Aligned modes use conjunctive success. Legacy preserves historical
        # point estimates while recording the disagreement explicitly.
        sel1 = sel_match if select_pool == "legacy" else sel_match and sel_valid
        sel2 = (sel1 or m2 >= 0) if select_pool == "legacy" else (
            (sel_match or m2 >= 0) and sel_valid)
        if select_pool != "legacy":
            assert not sel1 or (sel_match and sel_valid), (
                "aligned SELECT@1 must be match AND clinically valid")
        if decisive:
            tot["n_sel"] += 1
            tot["sel1"] += int(sel1)
            tot["sel2"] += int(sel2)
            tot["sel_valid"] += int(sel_valid)
        # DIRECTION (rule-in) + SHARED + RULE-OUT ------------------------------
        dir_results = []
        for f in case["findings"]:
            role = f.get("role") or (
                "rule_in_gold" if f.get("favors") == "gold"
                else "shared_nondiscriminating")
            if role == "rule_out_distractor":
                target = _resolve_name(
                    f.get("direction_target") or f.get("target", ""), cands)
                ans = {}
                try:
                    ans = llm.call_module(
                        "DiscriminatorRuleOut", _RULEOUT_PROMPT,
                        _payload({"finding": f["finding"]} | (
                            {"typed_finding": f["typed_finding"]}
                            if f.get("typed_finding") else {}),
                                 field="ruleout"))
                except Exception as e:  # noqa: BLE001
                    print(f"[err ruleout] {case['id']}/{f['finding'][:20]}: {e}")
                got = match_candidate(str(ans.get("argues_against", "")), cands)
                ok = got != "none" and _norm(got) == _norm(target)
                tot["ruleout_n"] += 1
                tot["ruleout_ok"] += int(ok)
                dir_results.append({"finding": f["finding"], "role": role,
                                    "expected": target, "got": got, "ok": ok,
                                    "kind": "ruleout"})
                continue
            expected = _expected_direction(role, f, gold_name, cands)
            # A2 local decision-set: when this finding carries a `decision_set`
            # (the surviving candidate subset a real TALP leaf faces) and the flag
            # is on, show the model ONLY that subset. A finding "common to all 5"
            # may be a genuine discriminator inside the local binary: if the
            # dataset supplies `decision_set_favors`, re-label it as rule-in.
            local_cands = cands
            if local_ds and f.get("decision_set"):
                keep = {_norm(x) for x in f["decision_set"]}
                sub = [c for c in cands if _norm(c["name"]) in keep]
                if len(sub) >= 2:
                    local_cands = sub
                    dsf = f.get("decision_set_favors")
                    if dsf:
                        expected = _resolve_name(dsf, cands)
                        role = "rule_in_gold"      # local re-label for scoring
            ans = {}
            try:
                ans = llm.call_module(
                    "DiscriminatorDirection", _DIRECTION_PROMPT,
                    _payload({"finding": f["finding"]} | (
                        {"typed_finding": f["typed_finding"]}
                        if f.get("typed_finding") else {}), field="dir",
                             cand_override=[c["name"] for c in local_cands]))
            except Exception as e:  # noqa: BLE001
                print(f"[err dir] {case['id']}/{f['finding'][:20]}: {e}")
            got = match_candidate(str(ans.get("favored", "")), local_cands)
            ok = (got == expected) or (expected != "none" and got != "none"
                                       and _norm(got) == _norm(expected))
            is_shared = role in ("shared_nondiscriminating", "parent_child_trap")
            if is_shared:
                tot["shared_n"] += 1
                tot["shared_ok"] += int(got == "none")
            else:
                tot["dir_n"] += 1
                tot["dir_ok"] += int(ok)
            dir_results.append({"finding": f["finding"], "role": role,
                                "expected": expected, "got": got, "ok": ok,
                                "kind": "shared" if is_shared else "rulein"})
        # PARENT/CHILD ---------------------------------------------------------
        parent_results = []
        pc = case.get("parent_child")
        if pc:
            parent = pc["parent"]
            trap_findings = [f for f in case["findings"]
                             if f.get("role") == "parent_child_trap"]
            for f in trap_findings:
                ans = {}
                try:
                    ans = llm.call_module(
                        "ParentEffect", _PARENT_PROMPT,
                        {"vignette": vtext, "parent_family": parent,
                         "finding": f["finding"]}
                        | ({"knowledge_base_signals": kb_block} if kb_block
                           else {})
                        | ({"discriminator_rules": disc_parent} if disc_parent
                           else {}))
                except Exception as e:  # noqa: BLE001
                    print(f"[err trap] {case['id']}: {e}")
                eff = _norm(str(ans.get("effect_on_parent", "")))
                ok = eff != "rules_out"  # trap: must NOT rule out the parent
                tot["trap_n"] += 1
                tot["trap_ok"] += int(ok)
                parent_results.append({"finding": f["finding"], "test": "trap",
                                       "effect": eff, "ok": ok})
            # LIFT: a child-specific decisive rule_in_gold should support parent
            lift = next((f for f in case["findings"]
                         if f.get("role") == "rule_in_gold" and f.get("decisive")),
                        None)
            if lift:
                ans = {}
                try:
                    ans = llm.call_module(
                        "ParentEffect", _PARENT_PROMPT,
                        {"vignette": vtext, "parent_family": parent,
                         "finding": lift["finding"]}
                        | ({"knowledge_base_signals": kb_block} if kb_block
                           else {})
                        | ({"discriminator_rules": disc_parent} if disc_parent
                           else {}))
                except Exception as e:  # noqa: BLE001
                    print(f"[err lift] {case['id']}: {e}")
                eff = _norm(str(ans.get("effect_on_parent", "")))
                ok = eff == "supports"
                tot["lift_n"] += 1
                tot["lift_ok"] += int(ok)
                parent_results.append({"finding": lift["finding"], "test": "lift",
                                       "effect": eff, "ok": ok})

        rec = {"id": case["id"], "gold": gold_name, "best_discriminator": best,
               "ranked": ranked, "select@1": sel1, "select@2": sel2,
               "select_match": sel_match, "select_valid": sel_valid,
               "select_consistent": sel_match == sel_valid,
               "select_pool": select_pool, "candidate_order": candidate_order,
               "n_decisive": len(decisive),
               "direction": dir_results, "parent_child": parent_results}
        rows.append(rec)
        dshared = [r for r in dir_results if r["kind"] == "shared"]
        dkey = [r for r in dir_results if r["kind"] == "rulein"]
        dro = [r for r in dir_results if r["kind"] == "ruleout"]
        print(f"[{case['id']:<16}] SEL@1={'Y' if sel1 else 'n'} "
              f"@2={'Y' if sel2 else 'n'} valid={'Y' if sel_valid else 'n'} "
              f"DIR={sum(r['ok'] for r in dkey)}/{len(dkey)} "
              f"RO={sum(r['ok'] for r in dro)}/{len(dro)} "
              f"SHARED={sum(r['got']=='none' for r in dshared)}/{len(dshared)} "
              f"PC={sum(r['ok'] for r in parent_results)}/{len(parent_results)}",
              flush=True)

    n = max(1, tot["n_sel"])
    dn = max(1, tot["dir_n"])
    ron = max(1, tot["ruleout_n"])
    sn = max(1, tot["shared_n"])
    print("\n" + "=" * 72)
    print(f"[{tag}] TALP DISCRIMINATION (n_cases={len(rows)}, "
          f"KB={'ON' if kb_blocks else 'OFF'})")
    print(f"  SELECT@1 (best = a decisive one):   "
          f"{tot['sel1']}/{tot['n_sel']} ({100*tot['sel1']//n}%)")
    print(f"  SELECT@2 (within top-2):            "
          f"{tot['sel2']}/{tot['n_sel']} ({100*tot['sel2']//n}%)")
    print(f"  SELECT valid (#1 = valid disc.):    "
          f"{tot['sel_valid']}/{tot['n_sel']} ({100*tot['sel_valid']//n}%)")
    print(f"  DIRECTION (rule-in gold):           "
          f"{tot['dir_ok']}/{tot['dir_n']} ({100*tot['dir_ok']//dn}%)")
    print(f"  RULE-OUT (argues against distractor):"
          f"{tot['ruleout_ok']}/{tot['ruleout_n']} ({100*tot['ruleout_ok']//ron}%)")
    print(f"  SHARED-trap avoided (answered none):"
          f"{tot['shared_ok']}/{tot['shared_n']} ({100*tot['shared_ok']//sn}%)")
    print(f"  PARENT trap (does NOT rule out parent):"
          f"{tot['trap_ok']}/{tot['trap_n']}")
    print(f"  PARENT lift (child rule-in -> supports parent):"
          f"{tot['lift_ok']}/{tot['lift_n']}")
    case_metrics = {}
    for key, kind in (("direction", "rulein"), ("ruleout", "ruleout"),
                      ("shared", "shared")):
        vals = []
        for row in rows:
            rs = [r for r in row["direction"] if r["kind"] == kind]
            if rs:
                vals.append(sum(bool(r["ok"]) for r in rs) / len(rs))
        case_metrics[f"{key}_case_normalized"] = (
            sum(vals) / len(vals) if vals else None)
    case_metrics["select_case_normalized"] = (
        sum(bool(r["select@1"]) for r in rows if r["n_decisive"]) /
        max(1, sum(bool(r["n_decisive"]) for r in rows)))
    return {"summary": tot, "case_normalized": case_metrics, "rows": rows}


def _print_lift(base: dict, kb: dict) -> None:
    b, k = base["summary"], kb["summary"]
    print("\n" + "=" * 72)
    print("LLM-alone  vs  LLM+KB  LIFT")
    def _pct(d, num, den):
        v = d[den]
        return f"{d[num]}/{v} ({100*d[num]//max(1, v)}%)"
    for label, num, den in [
            ("SELECT@1     ", "sel1", "n_sel"),
            ("DIRECTION    ", "dir_ok", "dir_n"),
            ("RULE-OUT     ", "ruleout_ok", "ruleout_n"),
            ("SHARED-trap  ", "shared_ok", "shared_n"),
            ("PARENT trap  ", "trap_ok", "trap_n"),
            ("PARENT lift  ", "lift_ok", "lift_n")]:
        print(f"  {label}: alone {_pct(b, num, den):<16} -> "
              f"+KB {_pct(k, num, den)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--judge-model", default=None,
                    help="independent model for SELECT match/validity judging")
    ap.add_argument("--select-gold-pool", default="legacy",
                    choices=["legacy", "additional_only", "typed_effect"],
                    help="SELECT reference construction; non-legacy modes require "
                         "match AND validity for SELECT@1")
    ap.add_argument("--candidate-order", default="shuffle",
                    choices=["shuffle", "fixed", "rotations"])
    ap.add_argument("--concept-router", default="legacy",
                    choices=["legacy", "hpo", "multi"],
                    help="default-OFF typed concept routing audit")
    ap.add_argument("--compound-mode", default="legacy",
                    choices=["legacy", "atomic", "syndrome", "dual"],
                    help="default-OFF compound finding representation")
    ap.add_argument("--pathogen-source", default="none",
                    choices=["none", "snomed", "open_kb", "corpus", "fused"],
                    help="default-OFF organism-attribution knowledge adapter")
    ap.add_argument("--pathogen-open-kb", action="append", default=[])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tag", default="llm")
    ap.add_argument("--kb", action="store_true",
                    help="also run the LLM+KB arm (loads KB indices)")
    ap.add_argument("--denoise", action="store_true",
                    help="also run the LLM+KB+DENOISE arm: inject an explicit "
                         "KB-derived COMMON-findings block (implies --kb)")
    ap.add_argument("--disc-agent", action="store_true",
                    help="also run the LLM+KB+DISC-AGENT arm (v1 baseline): a "
                         "per-contested-finding compiler agent turns retrieved "
                         "evidence into value-conditioned USE/COMMON rules "
                         "(implies --kb)")
    ap.add_argument("--disc-stage", default=None,
                    help="run the v2 disc-agent at ONE cumulative stage "
                         "(p0..p7); p7 is the full arm. Extra tokens p5c / p5cms "
                         "= P5 + consensus-none SHARED-trap gate (full/strict); "
                         "p5cp / p5cpms add a multi-source (DiagRL∪PrimeKG) "
                         "phenotype-intersection confirmation. (implies --kb)")
    ap.add_argument("--disc-ablation", action="store_true",
                    help="run the full v2 cumulative ablation ladder p0..p7 "
                         "(one arm per stage; implies --kb). Expensive.")
    ap.add_argument("--disc-dry", action="store_true",
                    help="with --disc-stage/--disc-ablation: build + audit the "
                         "compiled rules but SKIP the downstream run_arm eval "
                         "(cheap P0 attribution / retrieval probe)")
    ap.add_argument("--rag", action="store_true",
                    help="use Layer-B RAG fallback when building the KB block")
    ap.add_argument("--disc-sc", type=int, default=1,
                    help="A1: self-consistency K — sample the disc-agent compiler "
                         "(matrix + membership) K times and majority-vote")
    ap.add_argument("--disc-model", default=None,
                    help="A4: use a DIFFERENT model for the disc-agent compiler "
                         "modules only (answer modules keep --model)")
    ap.add_argument(
        "--disc-block-cache", type=Path,
        help="optional fingerprint-validated cache for one v2 stage's compiled "
             "blocks; absent cache is created, matching cache is read-only")
    ap.add_argument(
        "--refresh-disc-block-cache", action="store_true",
        help="explicitly replace --disc-block-cache after signature validation")
    ap.add_argument(
        "--p5-asset-manifest", type=Path,
        help="immutable P5 input manifest included in disc-cache signature")
    ap.add_argument(
        "--evidence-source", default="legacy",
        choices=["legacy", "cpg_enhanced", "cceg_direct", "cceg_graph",
                 "cceg_pair_direct", "cceg_unary", "cceg_composed"],
        help="default-OFF P5KG evidence adapter; legacy preserves P5 semantics")
    ap.add_argument(
        "--evidence-lane", default="clinical", choices=["clinical", "research"],
        help="default-OFF isolated evidence lane; research never uses clinical "
             "CCEG serving adapters")
    ap.add_argument(
        "--research-evidence-mode", default="off",
        choices=["off", "pair_direct", "unary", "composed", "graph"],
        help="research-only evidence mode; requires --evidence-lane=research")
    ap.add_argument("--research-claims", type=Path,
                    help="research_validated claim JSON/JSONL")
    ap.add_argument("--research-adjacency", type=Path,
                    help="research-only finding-state adjacency")
    ap.add_argument("--research-corpus-metadata", type=Path,
                    help="research-only quote hydration corpus metadata")
    ap.add_argument("--research-hydrate", action="store_true",
                    help="hydrate research graph paths from original quotes")
    ap.add_argument("--p5kg-research-manifest", type=Path,
                    help="frozen research-only assets/review manifest")
    ap.add_argument("--cceg-claims", type=Path,
                    help="validated CCEG claim JSONL for direct/graph lookup")
    ap.add_argument("--cceg-adjacency", type=Path,
                    help="CCEG adjacency JSON/JSONL for bounded graph lookup")
    ap.add_argument("--cceg-corpus-metadata", type=Path,
                    help="original chunk JSON/JSONL used for quote hydration")
    ap.add_argument("--cceg-max-hops", type=int, default=2,
                    help="bounded CCEG traversal depth (1 or 2 recommended)")
    ap.add_argument("--cceg-hydrate", action="store_true",
                    help="hydrate graph hits with their original source quotes")
    ap.add_argument("--membership-source", default="none",
                    choices=["none", "case_report"],
                    help="default-OFF phenotype membership provider")
    ap.add_argument("--p5kg-manifest", type=Path,
                    help="frozen P5KG asset manifest included in cache signature")
    ap.add_argument("--assert-filter", action="store_true",
                    help="A5: drop co-mention-only excerpts before the compiler")
    ap.add_argument("--soft-none", action="store_true",
                    help="A6: route consensus-none as a DIRECTION down-weight/AVOID "
                         "hint instead of a hard 'answer none' override")
    ap.add_argument("--gate-key", default="concrete",
                    choices=["concrete", "abstract", "expand"],
                    help="B0/B1: retrieval/gate key — concrete candidate name "
                         "(default), abstract l1_parent family label, or "
                         "expand-to-concrete-entities")
    ap.add_argument("--local-decision-set", action="store_true",
                    help="A2: score SHARED/DIRECTION against each finding's "
                         "decision_set (surviving subset) when present")
    ap.add_argument("--disc-loo", action="store_true",
                    help="A3: leave-one-out ablation off the p7 stack")
    ap.add_argument("--disc-sweep", action="store_true",
                    help="A7: threshold sensitivity sweep")
    ap.add_argument("--hier-aggregate", action="store_true",
                    help="B2: hierarchical finding x concrete-disease -> L1 aggregation")
    ap.add_argument("--entry-gate", default="legacy",
                    choices=["legacy", "all_findings", "typed_uncertain"],
                    help="default-OFF compiler entrance experiment")
    ap.add_argument(
        "--extra-dataset", action="append", default=[],
        help="append cases from another TALP JSON (repeatable); expansion cases "
             "may carry an inline `vignette`. Default dataset remains unchanged")
    ap.add_argument(
        "--stage-only", action="store_true",
        help="with a v2 --disc-stage, skip duplicate LLM-alone and plain-KB "
             "answer runs; fused retrieval and the requested stage still run")
    ap.add_argument("--seeds", default=None,
                    help="A0 noise floor: comma-separated seeds to run in turn "
                         "(e.g. 7,11,13). Overrides --seed. Each seed writes a "
                         "separate per-seed JSON; pool them with scripts/talp_ci.py")
    ap.add_argument("--repeat", type=int, default=1,
                    help="A0 noise floor: repeat each (seed,arm) N times with "
                         "distinct sub-seeds to expose LLM sampling variance")
    args = ap.parse_args()
    research_aliases = {
        "cceg_pair_direct": "pair_direct",
        "cceg_unary": "unary",
        "cceg_composed": "composed",
    }
    if args.evidence_source in research_aliases:
        if args.evidence_lane != "research":
            ap.error(f"--evidence-source={args.evidence_source} requires "
                     "--evidence-lane=research")
        alias_mode = research_aliases[args.evidence_source]
        if args.research_evidence_mode not in {"off", alias_mode}:
            ap.error("conflicting research evidence modes")
        args.research_evidence_mode = alias_mode
    if (args.evidence_lane == "research" and args.evidence_source == "cceg_graph"
            and args.research_evidence_mode == "off"):
        args.research_evidence_mode = "graph"
    if args.stage_only and not (
        args.disc_stage or args.disc_ablation or args.disc_loo or args.disc_sweep
    ):
        ap.error("--stage-only requires a v2 discriminator stage")
    if args.stage_only and (args.denoise or args.disc_agent):
        ap.error("--stage-only cannot be combined with --denoise/--disc-agent")
    if (args.denoise or args.disc_agent or args.disc_stage or args.disc_ablation
            or args.disc_loo or args.disc_sweep):
        args.kb = True
    if args.cceg_max_hops not in (1, 2):
        ap.error("--cceg-max-hops must be 1 or 2")
    if (args.evidence_lane == "clinical"
            and args.evidence_source in {"cceg_direct", "cceg_graph"}
            and not args.cceg_claims):
        ap.error(f"--evidence-source={args.evidence_source} requires --cceg-claims")
    if (args.evidence_lane == "clinical"
            and args.evidence_source == "cceg_graph"
            and not args.cceg_adjacency):
        ap.error("--evidence-source=cceg_graph requires --cceg-adjacency")
    if args.cceg_hydrate and not args.cceg_corpus_metadata:
        ap.error("--cceg-hydrate requires --cceg-corpus-metadata")
    if args.evidence_lane == "clinical" and args.research_evidence_mode != "off":
        ap.error("clinical lane cannot enable --research-evidence-mode")
    if args.evidence_lane == "research":
        if args.research_evidence_mode == "off":
            ap.error("research lane requires a non-off --research-evidence-mode")
        if not args.research_claims:
            ap.error("research lane requires --research-claims")
        if args.research_evidence_mode == "graph" and not args.research_adjacency:
            ap.error("research graph mode requires --research-adjacency")
        if args.research_hydrate and not args.research_corpus_metadata:
            ap.error("--research-hydrate requires --research-corpus-metadata")
        if not args.p5kg_research_manifest:
            ap.error("research lane requires --p5kg-research-manifest")
        from agentclinic_tree_dx.discrimination.manifests import (
            validate_research_manifest,
        )
        validation = validate_research_manifest(
            args.p5kg_research_manifest)
        if not validation.valid:
            ap.error("; ".join(validation.errors))
        if not args.tag.startswith("p5kg_research_"):
            ap.error("research lane tag must start with p5kg_research_")
        if (args.disc_block_cache
                and "research" not in str(args.disc_block_cache).lower()):
            ap.error("research lane cache path must contain 'research'")
    elif args.tag.startswith("p5kg_research_"):
        ap.error("clinical lane cannot use a research tag")

    from agentclinic_tree_dx.llm_client import RobustLLMClient

    ds = json.loads((DATA / "eval" / "talp_discrimination_cases.json").read_text())
    for extra_path in args.extra_dataset:
        extra = json.loads(Path(extra_path).read_text())
        extra_cases = extra.get("cases") or []
        ds["cases"].extend(extra_cases)
        print(f"[dataset] appended {len(extra_cases)} cases from {extra_path}")
    args._compound_audit = None
    if args.compound_mode != "legacy":
        from agentclinic_tree_dx.knowledge.compound_finding import (
            SyndromeResolver, represent)
        kr = DATA / "knowledge_raw"
        entries = {}
        cp, tp = kr / "snomed_concepts.json", kr / "snomed_term_index.json"
        if cp.exists() and tp.exists():
            concepts = json.loads(cp.read_text())
            for term, ids in json.loads(tp.read_text()).items():
                if "syndrome" not in term.lower():
                    continue
                for cid in ids[:1]:
                    concept = concepts.get(str(cid), {})
                    if "disorder" in str(concept.get("tag", "")).lower():
                        entries.setdefault(" ".join(term.lower().split()), []).append({
                            "concept_id": str(cid),
                            "label": concept.get("preferred", term),
                            "system": "SNOMED_CT", "provenance": str(cp),
                            "entailed": True, "confidence": 1.0,
                        })
        resolver = SyndromeResolver(entries)
        n = n_multi = n_syndrome = 0
        for case in ds["cases"]:
            for finding in case["findings"]:
                original = finding["finding"]
                rep = represent(original, args.compound_mode, resolver)
                finding["source_finding"] = original
                finding["compound_representation"] = rep.to_dict()
                finding.setdefault("select_aliases", []).append(original)
                finding["finding"] = rep.prompt_text()
                n += 1
                n_multi += len(rep.atoms) > 1
                n_syndrome += rep.syndrome is not None
        args._compound_audit = {
            "mode": args.compound_mode, "n": n, "multi_atom": n_multi,
            "syndrome_resolved": n_syndrome,
            "syndrome_abstained": n - n_syndrome
            if args.compound_mode == "syndrome" else None,
        }
        print(f"[compound] {args._compound_audit}")
    args._router_audit = None
    if args.concept_router != "legacy":
        from agentclinic_tree_dx.knowledge.clinical_concept_router import (
            ClinicalConceptRouter, ConceptRef, route_fixture)
        kr = DATA / "knowledge_raw"
        snomed_map = {}
        concepts_path, terms_path = kr / "snomed_concepts.json", kr / "snomed_term_index.json"
        if concepts_path.exists() and terms_path.exists():
            concepts = json.loads(concepts_path.read_text())
            for term, ids in json.loads(terms_path.read_text()).items():
                snomed_map[term] = [
                    ConceptRef("SNOMED_CT", str(cid),
                               concepts.get(str(cid), {}).get("preferred", term),
                               str(concepts_path))
                    for cid in ids[:3]
                ]
        router = ClinicalConceptRouter(
            {"SNOMED_CT": snomed_map}, hpo_normalizer=_get_normalizer())
        args._router_audit = route_fixture(ds, router, args.concept_router)
        print(f"[concept-router] {args._router_audit}")
    args._pathogen_blocks = {}
    args._pathogen_audit = {}
    if args.pathogen_source != "none":
        from agentclinic_tree_dx.knowledge.pathogen_attribution_index import (
            PathogenAttributionIndex, PathogenEdge)
        edge_rows = []
        paths = []
        built = DATA / "knowledge_raw/pathogen_attribution_eval_index.json"
        if args.pathogen_source in {"snomed", "fused"} and built.exists():
            paths.append((built, "SNOMED_CT"))
        if args.pathogen_source in {"open_kb", "fused"}:
            paths.extend((Path(p), None) for p in args.pathogen_open_kb)
        corpus_edges = DATA / "eval/talp_pathogen_probe_edges.json"
        if args.pathogen_source in {"corpus", "fused"}:
            paths.append((corpus_edges, "CORPUS_ASSERTION"))
        for path, source_filter in paths:
            if not path.exists():
                continue
            for row in json.loads(path.read_text()).get("edges", []):
                if source_filter and row.get("source") != source_filter:
                    continue
                edge_rows.append(PathogenEdge(**row))
        pindex = PathogenAttributionIndex(edge_rows)
        for case in ds["cases"]:
            if case.get("task_type") != "organism_attribution":
                continue
            culture = next((
                f["finding"] for f in case["findings"]
                if f.get("in_vignette") and re.search(
                    r"\b(culture|isolated|grew|pcr)\b", f["finding"], re.I)
            ), None)
            result = pindex.attribute(
                case.get("l1_label", ""), culture_result=culture,
                vignette_only=not bool(culture))
            args._pathogen_audit[case["id"]] = result.to_dict()
            if result.decision == "resolved":
                args._pathogen_blocks[case["id"]] = (
                    f"TYPED CULTURE CONFIRMATION: {result.organism}.")
            else:
                args._pathogen_blocks[case["id"]] = (
                    "ORGANISM ATTRIBUTION ABSTENTION: the vignette lacks a "
                    "confirming culture/PCR; narrow the syndrome and request "
                    "microbiology rather than guessing a species.")
        print(f"[pathogen-source] edges={len(edge_rows)} "
              f"cases={len(args._pathogen_audit)}")
    vign = load_vignettes()
    llm = RobustLLMClient(model=args.model, call_timeout=180, max_retries=4,
                          timeout_retry_cap=2)
    args._judge_llm = (
        RobustLLMClient(model=args.judge_model, call_timeout=180, max_retries=4,
                        timeout_retry_cap=2)
        if args.judge_model and args.judge_model != args.model else llm
    )

    print(f"TALP discrimination (model={args.model}), {len(ds['cases'])} cases\n")

    # A0 noise floor: expand into (seed, repeat) runs, each with a unique tag
    # suffix so scripts/talp_ci.py can pool them for a bootstrap CI. Default
    # (--seed only, --repeat 1) reproduces the original single-run behaviour with
    # the ORIGINAL tag (no suffix), so existing log paths are unchanged.
    if args.seeds:
        seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    else:
        seeds = [args.seed]
    multi = len(seeds) > 1 or args.repeat > 1
    for sd in seeds:
        for rep in range(args.repeat):
            run_seed = sd + 1000 * rep
            suffix = f"_s{sd}r{rep}" if multi else ""
            _run_once(args, llm, ds, vign, run_seed, args.tag + suffix)
    return 0


def _run_once(args, llm, ds, vign, seed: int, tag: str) -> int:
    lds = args.local_decision_set
    eval_kwargs = {
        "local_ds": lds,
        "select_pool": args.select_gold_pool,
        "candidate_order": args.candidate_order,
        "judge_llm": args._judge_llm,
    }
    out = PROJECT_ROOT / "logs" / f"talp_discrim_{tag}.json"
    out.parent.mkdir(exist_ok=True)
    base = None
    if not args.stage_only:
        base = run_arm(llm, ds, vign, seed,
                       args._pathogen_blocks or None, tag, **eval_kwargs)
        if args._router_audit:
            base["concept_router_audit"] = args._router_audit
        if args._compound_audit:
            base["compound_audit"] = args._compound_audit
        if args._pathogen_audit:
            base["pathogen_audit"] = args._pathogen_audit
        out.write_text(json.dumps(base, ensure_ascii=False, indent=2))
        print(f"  detail → {out}")

    if args.kb:
        print("\n" + "#" * 72)
        print("Building fused best-knowledge blocks (LR + CPG + case_report) ...")
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "evp", PROJECT_ROOT / "scripts" / "eval_evidence_precision.py")
        evp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evp)
        kb = evp.FusedKB(rag=args.rag)
        kb_blocks = {c["id"]: evp.build_fused_discriminator_hints(kb, c)["block"]
                     for c in ds["cases"]}
        for cid, block in args._pathogen_blocks.items():
            kb_blocks[cid] = "\n".join(x for x in (kb_blocks.get(cid, ""), block) if x)
        kb_res = None
        if not args.stage_only:
            print("\nLLM+KB arm:\n")
            kb_res = run_arm(llm, ds, vign, seed, kb_blocks, "kb", **eval_kwargs)
            out2 = PROJECT_ROOT / "logs" / f"talp_discrim_{tag}_kb.json"
            out2.write_text(json.dumps(kb_res, ensure_ascii=False, indent=2))
            print(f"  detail → {out2}")
            _print_lift(base, kb_res)

        if args.denoise:
            common_blocks = _build_common_blocks(kb, ds)
            print("\n" + "#" * 72)
            print("LLM+KB+DENOISE arm (explicit KB-derived COMMON list):\n")
            dn_res = run_arm(llm, ds, vign, seed, kb_blocks, "denoise",
                             common_blocks=common_blocks, **eval_kwargs)
            out3 = PROJECT_ROOT / "logs" / f"talp_discrim_{tag}_denoise.json"
            out3.write_text(json.dumps(dn_res, ensure_ascii=False, indent=2))
            print(f"  detail → {out3}")
            print("\nLLM+KB  vs  LLM+KB+DENOISE  LIFT")
            _print_lift(kb_res, dn_res)

        if args.disc_agent:
            print("\n" + "#" * 72)
            print("Compiling evidence-grounded discriminator rules "
                  "(per contested finding) ...")
            da = _build_disc_blocks(llm, kb, ds)
            print("\nLLM+KB+DISC-AGENT arm (evidence-compiled USE/COMMON rules):\n")
            da_res = run_arm(llm, ds, vign, seed, kb_blocks, "disc_agent",
                             disc_blocks=da["blocks"], **eval_kwargs)
            out4 = PROJECT_ROOT / "logs" / f"talp_discrim_{tag}_disc_agent.json"
            da_res["disc_audit"] = da["audit"]
            out4.write_text(json.dumps(da_res, ensure_ascii=False, indent=2))
            print(f"  detail → {out4}")
            print("\nLLM+KB  vs  LLM+KB+DISC-AGENT  LIFT")
            _print_lift(kb_res, da_res)

        # ── v2 disc-agent (roadmap P0..P7) ────────────────────────────────────
        # A3 LOO: build (label, cfg) pairs = full p7 baseline + p7-minus-one for
        # each ablatable stage; A7 sweep: build (label, cfg) pairs scanning a
        # threshold grid. Otherwise the usual stage list.
        if args.disc_loo:
            stage_cfgs = _loo_stage_cfgs()
        elif args.disc_sweep:
            stage_cfgs = _sweep_stage_cfgs()
        else:
            stages = (_STAGE_ORDER if args.disc_ablation
                      else ([args.disc_stage] if args.disc_stage else []))
            stage_cfgs = [(s, _cfg_for_stage(s)) for s in stages]
        if stage_cfgs:
            if args.disc_block_cache and len(stage_cfgs) != 1:
                raise ValueError(
                    "--disc-block-cache supports exactly one v2 stage")
            normalizer = _get_normalizer()
            # PrimeKG (heavy) only needed when a stage uses the phenotype gate
            # (veto p5+ or a consensus/pheno-confirm variant).
            _need_pk = any(cfg.veto or cfg.consensus_none
                           for _, cfg in stage_cfgs)
            membership_path = (
                str(args.cceg_claims)
                if args.membership_source == "case_report" and args.cceg_claims
                else "")
            dxidx = _get_dxindex(
                with_primekg=_need_pk, membership_path=membership_path)
            # A4: optionally compile with a DIFFERENT model than the answerer.
            disc_llm = llm
            if args.disc_model:
                from agentclinic_tree_dx.llm_client import RobustLLMClient
                print(f"[A4] disc-agent compiler model = {args.disc_model}")
                disc_llm = RobustLLMClient(
                    model=args.disc_model, call_timeout=180, max_retries=4,
                    timeout_retry_cap=2)
            prev_res = kb_res
            for stg, cfg in stage_cfgs:
                # A1/A5/A6/B: eval-only overrides layered onto the stage config.
                # (LOO/sweep set their own; only fill fields they don't touch.)
                if not (args.disc_loo or args.disc_sweep):
                    cfg.self_consistency = max(1, args.disc_sc)
                    cfg.assert_filter = args.assert_filter
                    cfg.soft_none = args.soft_none
                    cfg.gate_key = args.gate_key
                    cfg.hier_aggregate = args.hier_aggregate
                    cfg.entry_gate = args.entry_gate
                    cfg.evidence_source = args.evidence_source
                    cfg.evidence_lane = args.evidence_lane
                    cfg.research_evidence_mode = args.research_evidence_mode
                    cfg.research_claims = str(args.research_claims or "")
                    cfg.research_adjacency = str(args.research_adjacency or "")
                    cfg.research_corpus_metadata = str(
                        args.research_corpus_metadata or "")
                    cfg.research_hydrate = args.research_hydrate
                    cfg.p5kg_research_manifest = str(
                        args.p5kg_research_manifest or "")
                    cfg.cceg_claims = str(args.cceg_claims or "")
                    cfg.cceg_adjacency = str(args.cceg_adjacency or "")
                    cfg.cceg_corpus_metadata = str(
                        args.cceg_corpus_metadata or "")
                    cfg.cceg_max_hops = args.cceg_max_hops
                    cfg.cceg_hydrate = args.cceg_hydrate
                    cfg.membership_source = args.membership_source
                    cfg.p5kg_manifest = str(args.p5kg_manifest or "")
                print("\n" + "#" * 72)
                print(f"Building v2 disc-agent blocks (stage={stg}, "
                      f"symmetric={cfg.symmetric} normalize={cfg.normalize} "
                      f"matrix={cfg.matrix} gate={cfg.gate} veto={cfg.veto} "
                      f"entail={cfg.entail} route={cfg.route}) ...")
                built = _load_or_build_disc_cache(
                    args, disc_llm, kb, ds, cfg, normalizer, dxidx)
                asum = _audit_summary(built["audit"])
                print(f"[audit {stg}] USE={asum['n_use']} "
                      f"contrast_not_retrieved={asum['contrast_not_retrieved']} "
                      f"contrast_retrieved_but_ignored="
                      f"{asum['contrast_retrieved_but_ignored']}")
                if args.disc_dry:
                    outd = (PROJECT_ROOT / "logs"
                            / f"talp_discrim_{tag}_dv2_{stg}_audit.json")
                    outd.write_text(json.dumps(
                        {"stage": stg, "evidence_lane": cfg.evidence_lane,
                         "research_evidence_mode": cfg.research_evidence_mode,
                         "audit_summary": asum,
                         "key_audit": built.get("key_audit", {}),
                         "entry_audit": built.get("entry_audit", {}),
                         "audit": built["audit"]}, ensure_ascii=False, indent=2))
                    print(f"  audit → {outd}")
                    continue
                print(f"\nLLM+KB+DISC-v2 [{stg}] arm:\n")
                v2 = run_arm(llm, ds, vign, seed, kb_blocks,
                             f"dv2_{stg}", disc_blocks=built["blocks"],
                             **eval_kwargs)
                v2["disc_audit"] = built["audit"]
                v2["audit_summary"] = asum
                v2["key_audit"] = built.get("key_audit", {})
                v2["entry_audit"] = built.get("entry_audit", {})
                v2["evidence_lane"] = cfg.evidence_lane
                v2["research_evidence_mode"] = cfg.research_evidence_mode
                outv = (PROJECT_ROOT / "logs"
                        / f"talp_discrim_{tag}_dv2_{stg}.json")
                outv.write_text(json.dumps(v2, ensure_ascii=False, indent=2))
                print(f"  detail → {outv}")
                if prev_res is not None:
                    print(f"\nprev-stage  vs  DISC-v2[{stg}]  LIFT")
                    _print_lift(prev_res, v2)
                prev_res = v2
    return 0


def _build_common_blocks(kb, ds, balanced: bool = True) -> dict:
    """For each case, list the findings that are genuinely COMMON to the
    candidates. Purely KB-derived (mention distribution + no grounded
    direction); NEVER uses the dataset role/favors labels (that would leak).

    A finding is flagged COMMON only when ALL of:
      * the fused KB gives it NO grounded direction (favored == ""), AND
      * it is mentioned for (nearly) EVERY candidate, AND
      * mentions are BALANCED — the runner-up is within 2/3 of the top count,
        i.e. no candidate stands out (`balanced=True`).

    The balance guard is the key fix over the naive "no-LR => common" rule:
    a MISSING likelihood ratio is a DATA GAP, not evidence of non-specificity,
    so decisive rule-in findings that merely lack an LR (elevated PTH, low LAP,
    situs) are NOT flagged, while truly ubiquitous findings (leukocytosis,
    hypercalcemia, abdominal distension) are."""
    blocks: dict = {}
    for case in ds["cases"]:
        cand_names = [c["name"] for c in case["candidates"]]
        need = max(2, len(cand_names) - 1)
        commons = []
        for f in case["findings"]:
            fav, sigs = kb.favored(f["finding"], cand_names, f.get("hpo") or "")
            if fav:  # KB points at ONE candidate -> discriminating, keep
                continue
            ms = sorted((sigs[c]["mention"] for c in cand_names), reverse=True)
            n_mentioned = sum(1 for m in ms if m > 0)
            if n_mentioned < need:
                continue
            top = ms[0]
            second = ms[1] if len(ms) > 1 else 0
            is_balanced = top > 0 and (second / top) >= (2 / 3)
            if (not balanced) or is_balanced:
                commons.append(f["finding"])
        if commons:
            blocks[case["id"]] = (
                "FINDINGS COMMON TO MULTIPLE CANDIDATES (non-specific; mentioned "
                "roughly equally across candidates — do NOT use them to "
                "discriminate):\n"
                + "\n".join(f"- {c}" for c in commons))
    return blocks


def _contested_findings(kb, case, balanced: bool = True) -> list[dict]:
    """The findings the mention-based denoise arm would (mis)flag as COMMON:
    mentioned for (nearly) every candidate, balanced, and with NO grounded KB
    direction. These are exactly where "mention == discrim" fails — some are
    truly common, some are DECISIVE-but-equally-written (elevated PTH, prior
    surgery, unilateral discharge). The discriminator agent re-adjudicates each
    from retrieved evidence. Data-gap findings (low/zero mention, e.g. low LAP)
    are DELIBERATELY excluded so they are never suppressed as "common"."""
    cand_names = [c["name"] for c in case["candidates"]]
    need = max(2, len(cand_names) - 1)
    out = []
    for f in case["findings"]:
        fav, sigs = kb.favored(f["finding"], cand_names, f.get("hpo") or "")
        if fav:
            continue
        ms = sorted((sigs[c]["mention"] for c in cand_names), reverse=True)
        n_mentioned = sum(1 for m in ms if m > 0)
        if n_mentioned < need:
            continue
        top = ms[0]
        second = ms[1] if len(ms) > 1 else 0
        is_balanced = top > 0 and (second / top) >= (2 / 3)
        if (not balanced) or is_balanced:
            out.append(f)
    return out


def _entry_findings(kb, case: dict, mode: str) -> tuple[list[dict], dict]:
    """Parameterized compiler entrance with explicit decisive-loss auditing."""
    legacy = _contested_findings(kb, case)
    if mode == "legacy":
        selected = legacy
    elif mode == "all_findings":
        selected = list(case["findings"])
    elif mode == "typed_uncertain":
        selected = list(legacy)
        seen = {f.get("finding_id") or f["finding"] for f in selected}
        for finding in case["findings"]:
            typed = finding.get("typed_finding") or {}
            uncertain = typed.get("abstained") or typed.get("event_type") not in {
                None, "phenotype"
            }
            key = finding.get("finding_id") or finding["finding"]
            if (uncertain or finding.get("decisive")) and key not in seen:
                selected.append(finding)
                seen.add(key)
    else:
        raise ValueError(f"unsupported entry gate: {mode}")
    selected_keys = {f.get("finding_id") or f["finding"] for f in selected}
    decisive = [f for f in case["findings"] if f.get("decisive")]
    missed = [
        f.get("finding_id") or f["finding"] for f in decisive
        if (f.get("finding_id") or f["finding"]) not in selected_keys
    ]
    return selected, {
        "mode": mode, "total": len(case["findings"]),
        "selected": len(selected), "decisive_total": len(decisive),
        "decisive_missed": missed,
    }


def _gather_evidence(kb, finding: str, cand_names: list[str],
                     per_cand: int = 1, cap: int = 10, top_k: int = 8) -> list[dict]:
    """Retrieve grounded EVIDENCE EXCERPTS about `finding` for each candidate
    from the CPG + case_report corpora (the same indices FusedKB loads). Returns
    de-duplicated {candidate, source, text} snippets that actually mention the
    finding — the raw material the agent compiles a directional rule from."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dcov_ev", PROJECT_ROOT / "scripts" / "eval_discriminator_coverage.py")
    dcov = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dcov)
    toks = dcov._salient_tokens(finding)
    excerpts: list[dict] = []
    seen: set = set()
    for c in cand_names:
        for retr, label in ((kb.cpg, "CPG"), (kb.crep, "CASE_REPORT")):
            if retr is None:
                continue
            added = 0
            for q in (f"{finding} in {c}",
                      f"{c}: differential diagnosis, diagnostic workup"):
                try:
                    hits = retr.search(q, top_k=top_k, score_threshold=0.05)
                except Exception:  # noqa: BLE001
                    hits = []
                for h in hits:
                    body = f"{h.get('title','')} {h.get('content','')}".strip()
                    if not dcov._mentions(body, toks):
                        continue
                    key = body[:80]
                    if key in seen:
                        continue
                    seen.add(key)
                    excerpts.append({"candidate": c, "source": label,
                                     "text": body[:400]})
                    added += 1
                    if added >= per_cand:
                        break
                if added >= per_cand:
                    break
    return excerpts[:cap]


def _build_disc_blocks(llm, kb, ds) -> dict:
    """Discriminator-agent arm. For each CONTESTED finding (see
    _contested_findings), retrieve evidence and have a compiler agent adjudicate
    — from the evidence only — whether the finding is truly COMMON or a USE-able
    (value-conditioned) discriminator. Grounding/abstain guard + polarity guard
    are enforced on the agent's output. Emits, per case, an injectable rule block
    and (for audit) the structured rules."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "evp_pol", PROJECT_ROOT / "scripts" / "eval_evidence_precision.py")
    evp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evp)
    blocks: dict = {}
    audit: dict = {}
    for case in ds["cases"]:
        cand_names = [c["name"] for c in case["candidates"]]
        contested = _contested_findings(kb, case)
        rules = []
        for f in contested:
            finding = f["finding"]
            ev = _gather_evidence(kb, finding, cand_names)
            verdict, rule_in, rule_out, cond, why = "common", "", [], "", ""
            if ev:
                try:
                    res = llm.call_module(
                        "DiscriminatorAgent", _DISC_AGENT_PROMPT,
                        {"finding": finding, "candidates": cand_names,
                         "evidence_excerpts": ev})
                except Exception as e:  # noqa: BLE001
                    print(f"[err disc-agent] {case['id']}/{finding[:20]}: {e}")
                    res = {}
                verdict = _norm(str(res.get("verdict", "common"))) or "common"
                rule_in = match_candidate(str(res.get("rule_in", "")),
                                          case["candidates"])
                rule_out = [match_candidate(str(x), case["candidates"])
                            for x in (res.get("rule_out") or [])]
                rule_out = [r for r in rule_out if r and r != "none"]
                cond = str(res.get("value_condition", "") or "")
                why = str(res.get("why", "") or "")
            # ── grounding + polarity guards ────────────────────────────────
            polarity = evp._finding_polarity(finding)
            use = (verdict == "use" and rule_in not in ("", "none")
                   and polarity > 0)
            rules.append({"finding": finding,
                          "verdict": "use" if use else "common",
                          "value_condition": cond, "rule_in": rule_in if use else "",
                          "rule_out": rule_out if use else [],
                          "why": why, "n_evidence": len(ev)})
        # PURELY ADDITIVE: only emit grounded USE rules. An abstain/COMMON verdict
        # is NOT injected as a directive — forcing "answer none" on findings the
        # agent merely failed to ground re-creates the denoise over-suppression
        # trap (it crushed rule-in). So the agent can only ADD a grounded
        # direction, never suppress a genuine discriminator (design §4.4:
        # "only down-weight, never force none").
        use_rules = [r for r in rules if r["verdict"] == "use"]
        if use_rules:
            lines = []
            for r in use_rules:
                cond = f" (at {r['value_condition']})" if r["value_condition"] else ""
                ro = f"; argues against {', '.join(r['rule_out'])}" if r["rule_out"] else ""
                lines.append(f"- {r['finding']} [USE]{cond}: supports "
                             f"{r['rule_in']}{ro}.")
            blocks[case["id"]] = (
                "EVIDENCE-COMPILED DISCRIMINATOR RULES (a per-finding agent read "
                "retrieved guideline/case-report evidence and compiled how — and at "
                "what result value — each contested finding separates the "
                "candidates). Use these to guide direction; findings NOT listed are "
                "unaffected — judge them normally:\n" + "\n".join(lines))
        audit[case["id"]] = rules
        n_use = sum(1 for r in rules if r["verdict"] == "use")
        print(f"[disc-agent {case['id']:<16}] contested={len(contested)} "
              f"USE={n_use} COMMON={len(rules) - n_use}", flush=True)
    return {"blocks": blocks, "audit": audit}


# =============================================================================
# Discriminator-compiler agent v2 (roadmap disc_agent_roadmap: P0..P8)
# =============================================================================
# The v1 arm above compiles a single rule_in per contested finding from
# first-triggered evidence, with only grounding+polarity guards. Its residual
# failure (§11.2.2): retrieval returns "related-but-not-comparative" single-
# disease chunks -> the compiler upgrades an ASSOCIATION into a leaf-level
# discrimination -> SELECT/DIRECTION faithfully amplify it (5/12 USE mis-compiled,
# SHARED-trap 40%). v2 adds, as cumulative + independently ablatable stages:
#   P0 provenance/audit, P1 symmetric+sibling+quota retrieval, P2 value/polarity
#   normalisation with typed rule-out, P3 full candidate-effect matrix
#   (neutral!=unknown), P4 deterministic USE admission OR-gate, P5 phenotype
#   set-difference + parent/child veto, P6 independent entailment validator,
#   P7 per-consumer field routing. All eval-only; production stays default OFF.

_COMPARE_RE = re.compile(
    r"\b(whereas|unlike|in contrast|contrast|differ|distinguish|distinguishes|"
    r"versus|vs\.?|rather than|as opposed to|compared|however|but not|"
    r"not seen in|absent in|excludes?|exclud|rule[sd]? out|rule[sd]? in|"
    r"argues against|specific for|pathognomonic|hallmark|characteristic of|"
    r"in favou?r of|suggest[s]? against)\b", re.I)
_HIGHSPEC_RE = re.compile(
    r"\b(pathognomonic|highly specific|virtually diagnostic|diagnostic of|"
    r"hallmark|classic(ally)?|characteristic of|specific for|"
    r"defining feature)\b", re.I)
_NUMDIR_RE = re.compile(
    r"\b(elevat\w*|increas\w*|high|low|decreas\w*|reduc\w*|suppress\w*|"
    r"normal|absent|present|positive|negative|"
    r"\d+\s*(?:mg|mmol|meq|u/l|ng|pg|iu|%|/\w+))\b", re.I)
# Negation/qualifier cues in a chunk body (mirrors eval_evidence_precision's
# _NEG_QUALIFIER_RE; kept local so retrieval flagging has no import dependency).
_NEG_BODY_RE = re.compile(
    r"\b(normal|negative|absent|unremarkable|within normal limits|wnl|"
    r"no evidence of|not elevated|non[- ]?elevated|ruled out|negative for|"
    r"without|rules? out|excludes?)\b", re.I)


@dataclass
class DiscAgentConfig:
    """Cumulative feature toggles for the v2 disc-agent ablation ladder."""
    stage: str = "p0"
    symmetric: bool = False   # P1: all-candidate symmetric + sibling + quota
    normalize: bool = False   # P2: value/polarity normalisation, typed rule-out
    matrix: bool = False      # P3: full candidate-effect matrix (neutral!=unknown)
    gate: bool = False        # P4: deterministic USE admission OR-gate
    veto: bool = False        # P5: phenotype set-diff + parent/child veto
    entail: bool = False      # P6: independent entailment validator
    route: bool = False       # P7: per-consumer field routing
    # P5c "consensus-none" gate (the multi-measure SHARED-trap fix): route a
    # finding to DIRECTION as "answer none" ONLY when independent signals agree
    # it is non-discriminating. `consensus_strict` restricts the trigger to the
    # highest-precision, zero-risk signal: the matrix ruled the finding IN for
    # >=2 candidates (a finding cannot rule IN two competitors -> it cannot
    # discriminate). Non-strict additionally admits the agent's own all-neutral
    # discriminating=false verdict. A surviving single-rule_in USE is NEVER
    # suppressed, so decisive findings cannot be crushed (unlike naive P7).
    consensus_none: bool = False
    consensus_strict: bool = False
    # P5cp: require an INDEPENDENT phenotype set-difference confirmation (from the
    # multi-source DiagRL ∪ PrimeKG provider) that the finding is in the candidate
    # INTERSECTION before routing it to DIRECTION "answer none". This protects
    # decisive findings that a noisy matrix double-labelled rule_in (e.g. 'weight
    # loss' is in NO candidate's phenotype set -> never suppressed), fixing the
    # DIR collapse of the mention/matrix-only consensus gate.
    pheno_confirm: bool = False
    # P5cc: use a corpus-grounded LLM MEMBERSHIP matrix (over the CPG/case-report
    # chunks we already retrieve, incl. Merck) as the independent confirmation,
    # INSTEAD OF / IN ADDITION TO the structured KG. Closes the KG synonym gap &
    # true-absence gap. Framed as membership (not discrimination) to avoid the
    # effect-matrix co-mention noise.
    corpus_pheno: bool = False
    # P5ccv: value-condition the corpus membership query (elevated vs suppressed
    # PTH resolve to different membership) — the §E1h PTH-trap fix.
    value_conditioned: bool = False
    # A1 (noise floor / self-consistency): sample the LLM compiler (effect
    # matrix + corpus membership) K times and MAJORITY-VOTE per candidate. K=1
    # reproduces the single-shot behaviour. Attacks single-sample matrix noise
    # (e.g. `weight loss` occasionally double-labelled rule_in) without new data.
    self_consistency: int = 1
    # A5 (input assertion filter): drop excerpts that only CO-MENTION F and D
    # without ASSERTING F is/ isn't a feature of D, before the compiler reads them.
    assert_filter: bool = False
    # A6 (soft-none): route a consensus-none finding as a DIRECTION down-weight /
    # AVOID hint instead of a hard "answer none" override.
    soft_none: bool = False
    # B0/B1 (retrieval-key hierarchy probe): which STRING keys the disc-agent uses
    # to retrieve evidence and query membership. "concrete" = the real candidate
    # name (current harness, masks the production defect); "abstract" = the L1
    # family label `l1_parent` (mirrors production plan_temporary_leaves using
    # b.label); "expand" = expand the abstract label back to concrete entities and
    # retrieve per-entity. Rule targets stay the REAL candidate identities so the
    # downstream eval is unchanged; only the knowledge side moves.
    gate_key: str = "concrete"
    # B2 (hierarchical aggregation): build a finding x concrete-disease matrix and
    # roll effects up to the L1 family with provenance (used only with expand).
    hier_aggregate: bool = False
    entry_gate: str = "legacy"
    per_cand: int = 2
    top_k: int = 12
    # A7 threshold sweep knobs (replace hard-coded magic numbers when swept).
    jaccard: float = 0.6           # phenotype token Jaccard match threshold
    multi_support_min: int = 2     # #rule_in candidates that flags multi_support
    # P5KG harness knobs. All defaults reproduce legacy P5 exactly.
    evidence_source: str = "legacy"
    cceg_claims: str = ""
    cceg_adjacency: str = ""
    cceg_corpus_metadata: str = ""
    cceg_max_hops: int = 2
    cceg_hydrate: bool = False
    membership_source: str = "none"
    p5kg_manifest: str = ""
    evidence_lane: str = "clinical"
    research_evidence_mode: str = "off"
    research_claims: str = ""
    research_adjacency: str = ""
    research_corpus_metadata: str = ""
    research_hydrate: bool = False
    p5kg_research_manifest: str = ""


_STAGE_ORDER = ["p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7"]


def _cfg_for_stage(stage: str) -> DiscAgentConfig:
    """Cumulative: p3 turns on P1,P2,P3; p7 turns on everything. The extra tokens
    p5c / p5cms are P5 + the consensus-none SHARED-trap gate (full / strict)."""
    stage = stage.lower()
    if stage in ("p5c", "p5cms", "p5cp", "p5cpms", "p5cc", "p5ccms",
                 "p5ccv", "p5ccvms"):
        cfg = _cfg_for_stage("p5")
        cfg.stage = stage
        cfg.consensus_none = True
        cfg.consensus_strict = stage.endswith("ms")
        # p5cp = structured (KG) confirm; p5cc = corpus (LLM membership) confirm;
        # p5ccv = corpus confirm + value-conditioned membership query.
        cfg.pheno_confirm = stage.startswith("p5cp") or stage.startswith("p5cc")
        cfg.corpus_pheno = stage.startswith("p5cc")
        cfg.value_conditioned = stage.startswith("p5ccv")
        return cfg
    i = _STAGE_ORDER.index(stage) if stage in _STAGE_ORDER else 0
    return DiscAgentConfig(
        stage=stage,
        symmetric=i >= 1, normalize=i >= 2, matrix=i >= 3,
        gate=i >= 4, veto=i >= 5, entail=i >= 6, route=i >= 7)


# Compatibility facade: production owns the profile contract; retaining the
# historical definitions above keeps this large evaluation script diff small.
from agentclinic_tree_dx.discrimination.config import (  # noqa: E402
    DiscAgentConfig as DiscAgentConfig,
    _cfg_for_stage as _cfg_for_stage,
)


def _disc_cache_signature(args, ds: dict, cfg: DiscAgentConfig) -> str:
    compiler_inputs = []
    for case in ds["cases"]:
        compiler_inputs.append({
            "id": case["id"],
            "candidates": [
                {"name": candidate["name"],
                 "l1_parent": candidate.get("l1_parent", "")}
                for candidate in case["candidates"]
            ],
            "findings": [
                {"finding": finding["finding"], "hpo": finding.get("hpo", "")}
                for finding in case["findings"]
            ],
        })
    def _file_sha(path) -> str | None:
        path = Path(path) if path else None
        return (hashlib.sha256(path.read_bytes()).hexdigest()
                if path and path.is_file() else None)

    p5kg_manifest = getattr(args, "p5kg_manifest", None)
    research_manifest = getattr(args, "p5kg_research_manifest", None)
    freeze_id = None
    active_manifest = (research_manifest
                       if getattr(args, "evidence_lane", "clinical") == "research"
                       else p5kg_manifest)
    if active_manifest and active_manifest.is_file():
        try:
            freeze_id = json.loads(active_manifest.read_text()).get("freeze_id")
        except (OSError, ValueError, TypeError):
            freeze_id = None
    payload = {
        "schema_version": 3,
        "compiler_inputs": compiler_inputs,
        "config": asdict(cfg),
        "compiler_model": args.disc_model or args.model,
        "p5_asset_manifest_sha256": _file_sha(
            getattr(args, "p5_asset_manifest", None)),
        "p5kg": {
            "claims_sha256": _file_sha(getattr(args, "cceg_claims", None)),
            "adjacency_sha256": _file_sha(getattr(args, "cceg_adjacency", None)),
            "corpus_metadata_sha256": _file_sha(
                getattr(args, "cceg_corpus_metadata", None)),
            "manifest_sha256": _file_sha(p5kg_manifest),
            "freeze_id": freeze_id,
            "evidence_source": getattr(args, "evidence_source", "legacy"),
            "membership_source": getattr(args, "membership_source", "none"),
            "max_hops": getattr(args, "cceg_max_hops", 2),
            "hydrate": bool(getattr(args, "cceg_hydrate", False)),
        },
        "p5kg_research": {
            "lane": getattr(args, "evidence_lane", "clinical"),
            "mode": getattr(args, "research_evidence_mode", "off"),
            "claims_sha256": _file_sha(
                getattr(args, "research_claims", None)),
            "adjacency_sha256": _file_sha(
                getattr(args, "research_adjacency", None)),
            "corpus_metadata_sha256": _file_sha(
                getattr(args, "research_corpus_metadata", None)),
            "hydrate": bool(getattr(args, "research_hydrate", False)),
            "manifest_sha256": _file_sha(research_manifest),
            "freeze_id": freeze_id if active_manifest == research_manifest else None,
        },
    }
    from agentclinic_tree_dx.discrimination.cache import stable_fingerprint
    return stable_fingerprint(payload)


def _load_or_build_disc_cache(args, disc_llm, kb, ds, cfg, normalizer, dxidx):
    path = args.disc_block_cache
    if path is None:
        return _build_disc_blocks_v2(
            disc_llm, kb, ds, cfg, normalizer, dxidx)
    signature = _disc_cache_signature(args, ds, cfg)
    if path.exists() and not args.refresh_disc_block_cache:
        cached = json.loads(path.read_text())
        if cached.get("signature") != signature:
            raise ValueError(
                f"disc block cache signature mismatch: {path}; use a distinct "
                "cache path or --refresh-disc-block-cache explicitly")
        print(f"[disc-cache] hit {path}", flush=True)
        return cached["built"]
    built = _build_disc_blocks_v2(
        disc_llm, kb, ds, cfg, normalizer, dxidx)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not args.refresh_disc_block_cache:
        raise FileExistsError(f"refusing to overwrite disc cache: {path}")
    path.write_text(json.dumps({
        "schema_version": 3,
        "signature": signature,
        "stage": cfg.stage,
        "built": built,
    }, ensure_ascii=False, indent=2))
    print(f"[disc-cache] created {path}", flush=True)
    return built


def _loo_stage_cfgs() -> list:
    """A3: leave-one-out ablation off the full P7 stack. Returns the P7 baseline
    plus one config per removable stage with just that stage disabled, so each
    row reports the MARGINAL contribution of that stage given all the others."""
    out = [("p7", _cfg_for_stage("p7"))]
    removable = ["normalize", "gate", "veto", "entail", "route"]
    for feat in removable:
        cfg = _cfg_for_stage("p7")
        setattr(cfg, feat, False)
        cfg.stage = f"p7_no_{feat}"
        out.append((f"p7_no_{feat}", cfg))
    return out


def _sweep_stage_cfgs() -> list:
    """A7: threshold sensitivity sweep. Scans per_cand (retrieval quota), the
    phenotype Jaccard match threshold, and the multi_support trigger count, on the
    p5c (consensus-none) base where those knobs bite. Each row is one setting."""
    out = []
    base = "p5c"
    for pc in (1, 2, 3):
        cfg = _cfg_for_stage(base)
        cfg.per_cand = pc
        cfg.stage = f"{base}_pc{pc}"
        out.append((f"{base}_pc{pc}", cfg))
    for jac in (0.5, 0.6, 0.7):
        cfg = _cfg_for_stage(base)
        cfg.jaccard = jac
        cfg.stage = f"{base}_j{int(jac*100)}"
        out.append((f"{base}_j{int(jac*100)}", cfg))
    for ms in (2, 3):
        cfg = _cfg_for_stage(base)
        cfg.multi_support_min = ms
        cfg.stage = f"{base}_ms{ms}"
        out.append((f"{base}_ms{ms}", cfg))
    return out


def _get_normalizer():
    try:
        from agentclinic_tree_dx.knowledge.finding_normalizer import FindingNormalizer
        kr = DATA / "knowledge_raw"
        return FindingNormalizer(
            kr / "lab_reference_ranges.json",
            kr / "loinc2hpo_annotations.json",
            kr / "unit_conversions.json")
    except Exception as e:  # noqa: BLE001
        print(f"[disc-v2] FindingNormalizer unavailable: {e}")
        return None


def _optional_p5kg_class(name: str, modules: tuple[str, ...]):
    """Resolve future CCEG runtime classes without making legacy P5 depend on them."""
    existing = globals().get(name)
    if existing is not None:
        return existing
    for module_name in modules:
        try:
            module = __import__(module_name, fromlist=[name])
            cls = getattr(module, name, None)
            if cls is not None:
                return cls
        except ImportError:
            continue
    return None


def _construct_compat(cls, *paths):
    """Tolerate the small constructor differences of staged CCEG index builds."""
    paths = tuple(path for path in paths if path)
    for factory in (
        "from_paths", "from_path", "from_file", "from_files", "from_jsonl", "load"
    ):
        method = getattr(cls, factory, None)
        if method is None:
            continue
        try:
            return method(*paths)
        except TypeError:
            continue
    attempts = (
        lambda: cls(*paths),
        lambda: cls(claims_path=paths[0],
                    adjacency_path=paths[1] if len(paths) > 1 else None),
        lambda: cls(path=paths[0]),
    )
    last = None
    for attempt in attempts:
        try:
            return attempt()
        except TypeError as exc:
            last = exc
    if last:
        raise last
    return cls()


def _call_compat(obj, methods: tuple[str, ...], *args, **kwargs):
    last = None
    for name in methods:
        method = getattr(obj, name, None)
        if method is None:
            continue
        for call in (
            lambda: method(*args, **kwargs),
            lambda: method(*args),
            lambda: method(
                finding=args[0],
                candidates=args[1] if len(args) > 1 else None,
                **kwargs),
            lambda: method(query=args[0], **kwargs),
        ):
            try:
                return call()
            except TypeError as exc:
                last = exc
    if last:
        raise last
    raise AttributeError(f"none of {methods!r} provided by {type(obj).__name__}")


class _CCEGClaimAdapter:
    """Validated claim/graph retrieval adapter used only by the P5KG harness."""

    def __init__(self, cfg: DiscAgentConfig):
        claim_cls = _optional_p5kg_class(
            "CCEGClaimIndex",
            ("agentclinic_tree_dx.knowledge.cceg_claim_index",
             "agentclinic_tree_dx.knowledge.cceg_index"))
        if claim_cls is None:
            raise RuntimeError(
                "CCEGClaimIndex unavailable; install/provide the CCEG index module")
        self.cfg = cfg
        self.claims = _construct_compat(claim_cls, Path(cfg.cceg_claims))
        self.graph = None
        if cfg.evidence_source == "cceg_graph":
            graph_cls = _optional_p5kg_class(
                "CCEGGraphRetriever",
                ("agentclinic_tree_dx.knowledge.cceg_graph_retriever",
                 "agentclinic_tree_dx.knowledge.cceg_index"))
            if graph_cls is None:
                raise RuntimeError(
                    "CCEGGraphRetriever unavailable for cceg_graph evidence")
            adjacency = Path(cfg.cceg_adjacency)
            chunk_texts = {}
            if cfg.cceg_corpus_metadata:
                from agentclinic_tree_dx.knowledge.cceg_graph_retriever import (
                    load_chunk_texts,
                )
                chunk_texts = load_chunk_texts(cfg.cceg_corpus_metadata)
            try:
                self.graph = graph_cls(
                    claim_index=self.claims, adjacency_path=adjacency,
                    chunk_texts=chunk_texts,
                    max_hops=cfg.cceg_max_hops)
            except TypeError:
                try:
                    self.graph = graph_cls(
                        claim_index=self.claims, chunk_texts=chunk_texts,
                        max_hops=cfg.cceg_max_hops)
                except TypeError:
                    try:
                        self.graph = graph_cls(
                            self.claims, adjacency,
                            max_hops=cfg.cceg_max_hops)
                    except TypeError:
                        self.graph = _construct_compat(
                            graph_cls, Path(cfg.cceg_claims), adjacency)

    @staticmethod
    def _flatten(raw) -> list[dict]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            if "claim" in raw and isinstance(raw["claim"], dict):
                claim = dict(raw["claim"])
                claim.setdefault("_path", raw.get("path"))
                return [claim]
            if "claims" in raw and "path" in raw:
                claims = _CCEGClaimAdapter._flatten(raw["claims"])
                for claim in claims:
                    claim.setdefault("_path", raw["path"])
                return claims
            for key in ("claims", "hits", "results", "paths"):
                if key in raw:
                    return _CCEGClaimAdapter._flatten(raw[key])
            return [raw]
        if isinstance(raw, (list, tuple)):
            out = []
            for item in raw:
                out.extend(_CCEGClaimAdapter._flatten(item))
            return out
        return []

    @staticmethod
    def _prevalidated(claim: dict) -> bool:
        status = str(claim.get("claim_status") or "")
        consumers = {str(value) for value in claim.get("allowed_consumers") or ()}
        if status.startswith("research_") or any(
                value.startswith("research_") for value in consumers):
            return False
        if claim.get("validated") is True:
            return True
        try:
            from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim
            return (claim.get("claim_status") == "grounded"
                    and bool(set(claim.get("allowed_consumers") or ())
                             & {"p3_soft", "p4_soft", "p5_soft", "p5_veto"})
                    and not validate_claim(claim))
        except (ImportError, TypeError):
            return False

    def search(self, finding: str, candidates: list[str], top_k: int) -> list[dict]:
        raw = []
        for index, left in enumerate(candidates):
            for right in candidates[index + 1:]:
                if self.graph is not None:
                    paths = _call_compat(
                        self.graph, ("retrieve", "search", "query"),
                        left, right, finding, top_k=top_k,
                        max_hops=self.cfg.cceg_max_hops)
                    for path in paths or []:
                        path_meta = {
                            "nodes": path.get("nodes", []),
                            "claim_ids": path.get("claim_ids", []),
                        }
                        for excerpt in path.get("evidence_excerpts", []):
                            raw.append({
                                "validated": True,
                                "claim_id": excerpt.get("claim_id"),
                                "candidate": excerpt.get("candidate"),
                                "relation": excerpt.get("relation"),
                                "quote": (excerpt.get("text")
                                          if self.cfg.cceg_hydrate else ""),
                                "_path": path_meta,
                            })
                else:
                    raw.extend(_call_compat(
                        self.claims, ("lookup", "search", "query"),
                        left, right, finding, top_k=top_k) or [])
        return [claim for claim in self._flatten(raw)
                if self._prevalidated(claim)]

    def evidence(self, finding: str, candidates: list[str],
                 top_k: int) -> list[dict]:
        out = []
        for claim in self.search(finding, candidates, top_k):
            provenance = claim.get("provenance") or {}
            quote = str(provenance.get("quote") or claim.get("quote") or "")
            if self.cfg.evidence_source == "cceg_graph" \
                    and self.cfg.cceg_hydrate and not quote:
                continue
            relation = str(claim.get("relation") or "")
            candidate = claim.get("candidate") or claim.get("candidate_a") or {}
            if relation.endswith("_b"):
                candidate = claim.get("candidate_b") or candidate
            if isinstance(candidate, dict):
                candidate = candidate.get("name", "")
            text = quote
            if relation:
                text = f"[validated CCEG {relation}] {text}".strip()
            path = claim.get("_path")
            if path:
                path_text = json.dumps(path, ensure_ascii=False, sort_keys=True)
                text = f"[graph path {path_text}] {text}"
            out.append({
                "chunk_id": str(claim.get("claim_id")
                                or provenance.get("chunk_id") or ""),
                "source": ("CCEG_GRAPH_HYDRATED"
                           if self.cfg.evidence_source == "cceg_graph"
                           and self.cfg.cceg_hydrate else
                           self.cfg.evidence_source.upper()),
                "candidate": str(candidate),
                "text": text[:400],
                "score": float(claim.get("score", 1.0)),
                "claim_id": str(claim.get("claim_id", "")),
                "path": path,
            })
        return out


class _ResearchClaimAdapter:
    """Physically separate reader for synthetic research evidence.

    It deliberately does not construct ``CCEGClaimIndex`` or call the clinical
    schema validator. Only explicitly research-validated/research-consumer rows
    enter this lane.
    """

    def __init__(self, cfg: DiscAgentConfig):
        self.cfg = cfg
        path = Path(cfg.research_claims)
        if path.suffix.lower() == ".jsonl":
            self.claims = [
                json.loads(line) for line in path.read_text().splitlines()
                if line.strip()]
        else:
            payload = json.loads(path.read_text())
            self.claims = (
                payload.get("claims", []) if isinstance(payload, dict)
                else payload)
        self.claims = [
            dict(claim) for claim in self.claims
            if isinstance(claim, dict) and self._research_valid(claim)]

    @staticmethod
    def _research_valid(claim: dict) -> bool:
        consumers = {str(value) for value in claim.get("allowed_consumers") or ()}
        return (
            claim.get("claim_status") == "research_validated"
            and any(value.startswith("research_") for value in consumers)
        )

    @staticmethod
    def _candidate_name(value) -> str:
        return str(value.get("name", "") if isinstance(value, dict) else value or "")

    @staticmethod
    def _finding_surface(claim: dict) -> str:
        finding = claim.get("finding") or claim.get("finding_state") or {}
        if isinstance(finding, dict):
            return str(finding.get("surface") or finding.get("finding") or "")
        return str(finding)

    def _mode_accepts(self, claim: dict) -> bool:
        mode = self.cfg.research_evidence_mode
        claim_type = str(claim.get("claim_type") or "")
        derived = bool(claim.get("derived")) or claim_type == "derived_contrast"
        unary = claim_type == "candidate_effect"
        pair = bool(claim.get("candidate_b")) and not derived and not unary
        return (
            (mode == "pair_direct" and pair)
            or (mode == "unary" and unary)
            or (mode == "composed" and derived)
            or (mode == "graph" and (derived or pair))
        )

    @staticmethod
    def _quotes(claim: dict) -> list[str]:
        rows = claim.get("provenance_bundle") or claim.get("provenance") or []
        if isinstance(rows, dict):
            rows = [rows]
        quotes = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                quote = row.get("quote") or row.get("text")
                if quote:
                    quotes.append(str(quote))
        quote = claim.get("quote")
        if quote:
            quotes.append(str(quote))
        return quotes

    def evidence(self, finding: str, candidates: list[str],
                 top_k: int) -> list[dict]:
        candidate_norms = {_norm(value): value for value in candidates}
        out = []
        for claim in self.claims:
            if not self._mode_accepts(claim):
                continue
            surface = self._finding_surface(claim)
            if surface and _norm(surface) != _norm(finding):
                continue
            left = self._candidate_name(claim.get("candidate_a"))
            right = self._candidate_name(claim.get("candidate_b"))
            if left and _norm(left) not in candidate_norms:
                continue
            if right and _norm(right) not in candidate_norms:
                continue
            effect = str(claim.get("candidate_effect")
                         or claim.get("relation") or "")
            candidate = left
            if effect.endswith("_b") and right:
                candidate = right
            quotes = self._quotes(claim)
            if (self.cfg.research_evidence_mode == "graph"
                    and not self.cfg.research_hydrate):
                quotes = []
            text = " ".join(quotes)
            prefix = (
                f"[research-only {self.cfg.research_evidence_mode} {effect}]")
            premise_ids = claim.get("premise_claim_ids") or []
            path = (
                {"claim_ids": list(premise_ids),
                 "mode": self.cfg.research_evidence_mode}
                if premise_ids or self.cfg.research_evidence_mode == "graph"
                else None)
            if path:
                prefix += " " + json.dumps(path, ensure_ascii=False,
                                            sort_keys=True)
            out.append({
                "chunk_id": str(claim.get("claim_id") or ""),
                "source": "CCEG_RESEARCH_" + self.cfg.research_evidence_mode.upper(),
                "candidate": candidate,
                "text": f"{prefix} {text}".strip()[:400],
                "score": float(
                    (claim.get("extraction") or {}).get("confidence", 1.0)),
                "claim_id": str(claim.get("claim_id") or ""),
                "path": path,
            })
        out.sort(key=lambda row: (-row["score"], row["claim_id"]))
        return out[:top_k]


# Compatibility name used by old harness tests and cache-building code.
from agentclinic_tree_dx.discrimination.adapters import (  # noqa: E402
    ResearchClaimAdapter as _ResearchClaimAdapter,
)


class _PhenoProvider:
    """Multi-source disease->phenotype set provider for the deterministic gate.

    Merges DiagRL-Corpus (`DxDiscriminatorIndex`) with PrimeKG
    (`PrimeKGIndex`). PrimeKG carries far richer phenotype coverage AND a fuzzy
    subtype resolver (`_resolve_disease_keys`) that operationalises the
    "abstract label -> concrete disease" pre-expansion (e.g. 'chronic myeloid
    leukemia' -> 'atypical chronic myeloid leukemia' with 166 phenotypes;
    'primary hyperparathyroidism' -> 'familial primary hyperparathyroidism').
    Both are ALREADY loaded in the production knowledge layer, so this is not a
    new dependency. The signal stays SAFE because it uses phenotype SET
    MEMBERSHIP (present-in / absent-from a disease's feature set), NOT corpus
    co-mention (which the §11.2.2 PTH trap shows is non-directional)."""

    def __init__(self, dia=None, pk=None, membership=None):
        self.dia = dia
        self.pk = pk
        self.membership = membership
        self._cache: dict = {}

    def get_phenotypes(self, name: str) -> set:
        key = (name or "").strip().lower()
        if key in self._cache:
            return self._cache[key]
        out: set = set()
        if self.dia is not None:
            out |= set(self.dia.get_phenotypes(name))
        if self.pk is not None:
            out |= set(self.pk.get_positive_phenotypes(name))
            try:
                for k in self.pk._resolve_disease_keys(key)[:3]:
                    out |= set(self.pk.get_positive_phenotypes(k))
            except Exception:  # noqa: BLE001
                pass
        if self.membership is not None:
            try:
                values = _call_compat(
                    self.membership,
                    ("get_phenotypes", "phenotypes_for", "lookup"),
                    name)
                for value in values or []:
                    if isinstance(value, dict):
                        consumers = value.get("allowed_consumers")
                        if consumers is not None and "p5_veto" not in consumers:
                            continue
                        value = (value.get("finding") or value.get("phenotype")
                                 or value.get("surface") or "")
                        if isinstance(value, dict):
                            value = value.get("surface") or value.get("display") or ""
                    if value:
                        out.add(str(value))
            except Exception:  # noqa: BLE001
                pass
        self._cache[key] = out
        return out


def _get_dxindex(with_primekg: bool = True, membership_path: str = ""):
    dia = None
    try:
        from agentclinic_tree_dx.knowledge.dx_discriminator_index import (
            DxDiscriminatorIndex)
        kr = DATA / "knowledge_raw"
        dia = DxDiscriminatorIndex.from_files(
            kr / "Guideline_common.json", kr / "Guideline_rare.json")
    except Exception as e:  # noqa: BLE001
        print(f"[disc-v2] DxDiscriminatorIndex unavailable: {e}")
    pk = None
    if with_primekg:
        try:
            from agentclinic_tree_dx.knowledge.primekg_index import PrimeKGIndex
            kg = DATA / "knowledge_raw" / "kg.csv"
            if kg.exists():
                print("[disc-v2] loading PrimeKG phenotype index ...", flush=True)
                pk = PrimeKGIndex.from_csv(kg)
        except Exception as e:  # noqa: BLE001
            print(f"[disc-v2] PrimeKGIndex unavailable: {e}")
    membership = None
    if membership_path:
        cls = _optional_p5kg_class(
            "CaseReportMembershipIndex",
            ("agentclinic_tree_dx.knowledge.case_report_membership_index",
             "agentclinic_tree_dx.knowledge.cceg_index"))
        if cls is not None:
            membership = _construct_compat(cls, Path(membership_path))
    if dia is None and pk is None and membership is None:
        return None
    return _PhenoProvider(dia, pk, membership)


def _finding_meta(normalizer, evp, finding: str) -> dict:
    """P2: structured (test / value_state / polarity). polarity<0 => negated or
    a normal/absent result (must NOT rule IN; routes to rule-OUT instead)."""
    polarity = evp._finding_polarity(finding)
    test_name, value_state, direction = None, "", "unknown"
    if normalizer is not None:
        try:
            nf = normalizer.normalize(finding)
        except Exception:  # noqa: BLE001
            nf = None
        if nf is not None:
            test_name = nf.test_name
            direction = nf.direction
            value_state = {"H": "high", "L": "low", "N": "normal"}.get(
                nf.direction, "")
            if nf.direction == "N":
                polarity = -1  # a normal result is negative-polarity
    return {"test": test_name, "value_state": value_state,
            "direction": direction, "polarity": polarity}


def _search_evidence(kb, dcov, finding: str, cand_names: list[str],
                     cfg: DiscAgentConfig,
                     query_keys: dict | None = None) -> list[dict]:
    """P0+P1: retrieve tagged evidence excerpts. When cfg.symmetric, retrieve
    symmetrically for EVERY candidate with sibling closure, an equal per-source
    quota, and a comparison/negation/numeric-direction priority; otherwise
    reproduce the v1 first-triggered gather. Each excerpt carries provenance
    (ev_id / chunk_id / source / candidate) + flags for downstream gates.

    B0/B1: `query_keys` optionally maps a candidate's REAL name -> the STRING
    used to query the corpus (abstract family label / expanded entity). The
    excerpt is still TAGGED with the real candidate, so admission/veto and the
    downstream eval are identity-stable; only the retrieval key changes."""
    toks = dcov._salient_tokens(finding)
    if not toks:
        return []
    query_keys = query_keys or {}
    excerpts: list[dict] = []
    seen: set = set()
    eid = 0
    if cfg.evidence_lane == "research":
        cache_key = (
            cfg.research_evidence_mode, cfg.research_claims,
            cfg.research_adjacency, cfg.research_corpus_metadata,
            cfg.p5kg_research_manifest)
        adapters = getattr(kb, "_p5kg_research_adapters", {})
        if cache_key not in adapters:
            adapters[cache_key] = _ResearchClaimAdapter(cfg)
            setattr(kb, "_p5kg_research_adapters", adapters)
        raw = adapters[cache_key].evidence(finding, cand_names, cfg.top_k)
        for item in raw:
            candidate = next(
                (c for c in cand_names if _norm(c) == _norm(item["candidate"])),
                item["candidate"] or cand_names[0])
            body = item["text"]
            cid = item["chunk_id"] or item.get("claim_id") or body[:60]
            if cid in seen:
                continue
            seen.add(cid)
            eid += 1
            excerpts.append({
                **item, "ev_id": f"E{eid}", "chunk_id": str(cid),
                "candidate": candidate,
                "has_compare": bool(_COMPARE_RE.search(body)),
                "has_neg": bool(_NEG_BODY_RE.search(body)),
                "has_num": bool(_NUMDIR_RE.search(body)),
                "has_highspec": bool(_HIGHSPEC_RE.search(body)),
            })
        if cfg.assert_filter:
            excerpts = _assert_filter(excerpts, cand_names)
        return excerpts
    if cfg.evidence_source in {"cceg_direct", "cceg_graph"}:
        cache_key = (
            cfg.evidence_source, cfg.cceg_claims, cfg.cceg_adjacency,
            cfg.cceg_max_hops, cfg.cceg_hydrate)
        adapters = getattr(kb, "_p5kg_claim_adapters", {})
        if cache_key not in adapters:
            adapters[cache_key] = _CCEGClaimAdapter(cfg)
            setattr(kb, "_p5kg_claim_adapters", adapters)
        raw = adapters[cache_key].evidence(finding, cand_names, cfg.top_k)
        for item in raw:
            candidate = next(
                (c for c in cand_names if _norm(c) == _norm(item["candidate"])),
                item["candidate"] or cand_names[0])
            body = item["text"]
            cid = item["chunk_id"] or item.get("claim_id") or body[:60]
            if cid in seen:
                continue
            seen.add(cid)
            eid += 1
            excerpts.append({
                **item, "ev_id": f"E{eid}", "chunk_id": str(cid),
                "candidate": candidate,
                "has_compare": bool(_COMPARE_RE.search(body)),
                "has_neg": bool(_NEG_BODY_RE.search(body)),
                "has_num": bool(_NUMDIR_RE.search(body)),
                "has_highspec": bool(_HIGHSPEC_RE.search(body)),
            })
        if cfg.assert_filter:
            excerpts = _assert_filter(excerpts, cand_names)
        return excerpts

    for c in cand_names:
        qk = query_keys.get(c, c)
        retrievers = (
            ((kb.cpg, "CPG_ENHANCED", True),
             (kb.crep, "CASE_REPORT", False))
            if cfg.evidence_source == "cpg_enhanced"
            else ((kb.cpg, "CPG", False),
                  (kb.crep, "CASE_REPORT", False)))
        for retr, label, enhanced_cpg in retrievers:
            if retr is None:
                continue
            cand_hits: list[dict] = []
            queries = [
                f"{finding} in {qk}",
                f"{qk}: differential diagnosis, diagnostic workup",
            ]
            if enhanced_cpg:
                queries.extend([
                    f"{finding}: {qk} versus {' versus '.join(cand_names)}",
                    f"{qk}: {finding} distinguishing feature rule out",
                ])
            for q in queries:
                try:
                    hits = retr.search(q, top_k=cfg.top_k, score_threshold=0.05)
                    if cfg.symmetric and hasattr(retr, "expand_ddx_siblings"):
                        hits = retr.expand_ddx_siblings(hits)
                except Exception:  # noqa: BLE001
                    hits = []
                for h in hits:
                    body = f"{h.get('title','')} {h.get('content','')}".strip()
                    if not dcov._mentions(body, toks):
                        continue
                    cid = str(h.get("id") or h.get("source_id") or body[:60])
                    if cid in seen:
                        continue
                    seen.add(cid)
                    cand_hits.append({
                        "chunk_id": cid, "source": label, "candidate": c,
                        "text": body[:400], "score": float(h.get("score", 0.0)),
                        "has_compare": bool(_COMPARE_RE.search(body)),
                        "has_neg": bool(_NEG_BODY_RE.search(body)),
                        "has_num": bool(_NUMDIR_RE.search(body)),
                        "has_highspec": bool(_HIGHSPEC_RE.search(body))})
            if cfg.symmetric:
                # de-bias ordering: comparison/negation/numeric chunks first,
                # then score. Then take an equal per-candidate/per-source quota.
                cand_hits.sort(
                    key=lambda e: (e["has_compare"] + e["has_neg"]
                                   + e["has_num"] + e["has_highspec"],
                                   e["score"]), reverse=True)
                cand_hits = cand_hits[:cfg.per_cand]
            else:
                cand_hits = cand_hits[:max(1, cfg.per_cand - 1)]
            for e in cand_hits:
                eid += 1
                e["ev_id"] = f"E{eid}"
                excerpts.append(e)
    if cfg.assert_filter:
        excerpts = _assert_filter(excerpts, cand_names)
    return excerpts


def _assert_filter(excerpts: list[dict], cand_names: list[str]) -> list[dict]:
    """A5: deterministic assertion filter. A pure CO-MENTION chunk (the finding
    and disease merely appear together, no comparison/negation/high-specificity/
    numeric-direction cue) does not ASSERT that F is/ isn't a feature of D, so it
    is the noise the compiler upgrades into a spurious discrimination (§11.2.2).
    Keep only excerpts carrying an assertive cue, but never starve a candidate:
    if filtering would drop ALL of a candidate's excerpts, keep its best one."""
    def _assertive(e):
        return e["has_compare"] or e["has_neg"] or e["has_highspec"] or e["has_num"]
    kept = [e for e in excerpts if _assertive(e)]
    kept_ids = {e["ev_id"] for e in kept}
    for c in cand_names:
        c_ex = [e for e in excerpts if e["candidate"] == c]
        if c_ex and not any(e["ev_id"] in kept_ids for e in c_ex):
            best = max(c_ex, key=lambda e: e["score"])
            kept.append(best)
            kept_ids.add(best["ev_id"])
    return [e for e in excerpts if e["ev_id"] in kept_ids]


def _admission(finding: str, rule_in: str, cand_names: list[str],
               ev: list[dict], kb, meta: dict) -> dict:
    """P4: deterministic USE admission OR-gate (does NOT trust model confidence).
    Admit iff ANY of: (a) PAIRED evidence — a supporting excerpt for rule_in AND
    a contrasting excerpt (comparison/negation) for a competitor; (b) a HIGH-
    SPECIFICITY claim in a rule_in excerpt; (c) a RELIABLE LR — the fused KB
    independently points at rule_in."""
    ri = _norm(rule_in)
    support = [e for e in ev if _norm(e["candidate"]) == ri]
    competitor = [e for e in ev if _norm(e["candidate"]) != ri]
    has_support = bool(support)
    has_contrast = any(e["has_compare"] or e["has_neg"] for e in competitor)
    paired = has_support and has_contrast
    highspec = any(e["has_highspec"] for e in support)
    reliable_lr = False
    try:
        fav, _sigs = kb.favored(finding, cand_names, "")
        reliable_lr = bool(fav) and _norm(fav) == ri
    except Exception:  # noqa: BLE001
        pass
    reasons = []
    if paired:
        reasons.append("paired")
    if highspec:
        reasons.append("highspec")
    if reliable_lr:
        reasons.append("reliable_lr")
    return {"admit": bool(reasons), "reasons": reasons,
            "has_support": has_support, "has_contrast": has_contrast,
            "paired": paired, "highspec": highspec, "reliable_lr": reliable_lr}


def _pheno_present(dxidx, dcov, finding: str, name: str,
                   jaccard: float = 0.6) -> bool:
    """Is `finding` a member of `name`'s phenotype set? Token-subset / high-
    Jaccard match of the finding's salient tokens against each phenotype string.
    (String-level; a residual synonym gap remains — e.g. 'hypercalcemia' vs an
    HPO label 'Elevated circulating calcium' — which HPO-ID normalisation would
    close; documented as backlog.)"""
    if dxidx is None:
        return False
    toks = set(dcov._salient_tokens(finding))
    if not toks:
        return False
    for p in dxidx.get_phenotypes(name):
        pt = set(dcov._salient_tokens(p))
        if not pt:
            continue
        if toks <= pt or pt <= toks:
            return True
        inter = toks & pt
        if inter and len(inter) / len(toks | pt) >= jaccard:
            return True
    return False


def _pheno_intersection(dxidx, dcov, finding: str,
                        cand_names: list[str], jaccard: float = 0.6) -> dict:
    """Phenotype set-membership across candidates (the SAFE structured signal).
    Returns present-map, count, and covered candidates."""
    present = {c: _pheno_present(dxidx, dcov, finding, c, jaccard)
               for c in cand_names}
    covered = [c for c in cand_names if dxidx and dxidx.get_phenotypes(c)]
    return {"present": present, "n_present": sum(1 for v in present.values() if v),
            "covered": covered}


def _corpus_pheno_intersection(llm, finding: str, cand_names: list[str],
                               ev: list[dict], meta: dict | None = None,
                               k: int = 1, query_keys: dict | None = None) -> dict:
    """Corpus-grounded phenotype MEMBERSHIP across candidates (the unstructured
    analog of `_pheno_intersection`). One LLM call, membership-framed (NOT
    discrimination-framed), answered per-candidate from that candidate's own
    excerpts. When `meta` carries a parsed value/direction/polarity the query is
    VALUE-CONDITIONED (the §E1h PTH-trap fix). Returns the same shape as
    `_pheno_intersection` so the gate logic is source-agnostic.

    B0/B1: the retrieval key already shaped WHICH excerpts each candidate got
    (see _search_evidence); membership is judged on those excerpts, so the real
    candidate names stay the question labels. `query_keys` is accepted for a
    uniform call signature and future per-key prompting."""
    present: dict = {c: False for c in cand_names}
    covered: list = []
    if not ev:
        return {"present": present, "n_present": 0, "covered": covered}
    value_clause = ""
    if meta:
        vs = str(meta.get("value_state") or "").strip()
        direction = str(meta.get("direction") or "").strip()
        polarity = meta.get("polarity", 1)
        desc = ""
        if vs:
            desc = vs
        elif direction and direction not in ("unknown", ""):
            desc = {"H": "HIGH/elevated", "L": "LOW/decreased",
                    "N": "NORMAL"}.get(direction, direction)
        if polarity is not None and polarity < 0 and "normal" not in desc.lower():
            desc = (desc + "; NEGATED/normal") if desc else "NEGATED/normal"
        if desc:
            value_clause = _VALUE_CLAUSE.format(value_desc=desc)
    prompt = _PHENO_MEMBER_PROMPT.replace("{value_clause}", value_clause)
    payload = {
        "finding": finding, "candidates": cand_names,
        "value_context": (value_clause[16:80] if value_clause else "none stated"),
        "evidence_excerpts": [{"ev_id": e["ev_id"], "candidate": e["candidate"],
                               "source": e["source"], "text": e["text"]}
                              for e in ev]}
    def _match_name(raw: str) -> str:
        r = _norm(raw)
        if not r:
            return ""
        for c in cand_names:
            if _norm(c) == r:
                return c
        for c in cand_names:
            nc = _norm(c)
            if r in nc or nc in r:
                return c
        return ""

    # A1: sample k times, majority-vote each candidate's membership verdict.
    from collections import Counter
    votes: dict = {c: Counter() for c in cand_names}
    n_ok = 0
    for _ in range(max(1, k)):
        try:
            res = llm.call_module("DiscriminatorPhenoMember", prompt, payload)
        except Exception:  # noqa: BLE001
            continue
        n_ok += 1
        for m in (res.get("membership") or []):
            cand = _match_name(str(m.get("candidate", "")))
            if not cand:
                continue
            votes[cand][_norm(str(m.get("member", "unknown"))) or "unknown"] += 1
    if not n_ok:
        return {"present": present, "n_present": 0, "covered": covered}
    for c in cand_names:
        if not votes[c]:
            continue
        verdict = votes[c].most_common(1)[0][0]
        if verdict in ("yes", "no"):
            covered.append(c)
        if verdict == "yes":
            present[c] = True
    return {"present": present,
            "n_present": sum(1 for v in present.values() if v),
            "covered": sorted(set(covered))}


def _vote_matrix(samples: list[dict], candidates: list[dict]) -> dict:
    """A1: majority-vote k effect-matrix samples per candidate. Reduces single-
    sample noise (a decisive finding occasionally double-labelled rule_in).
    `discriminating` is a majority bool; each candidate's effect is the modal
    label across samples; value_condition/why come from the first sample."""
    if not samples:
        return {}
    if len(samples) == 1:
        return samples[0]
    from collections import Counter
    cand_names = [c["name"] for c in candidates]
    disc_votes = sum(1 for s in samples if bool(s.get("discriminating")))
    eff_votes: dict = {c: Counter() for c in cand_names}
    ce_meta: dict = {}
    for s in samples:
        for ce in (s.get("candidate_effects") or []):
            cand = match_candidate(str(ce.get("candidate", "")), candidates)
            if not cand or cand == "none":
                continue
            eff_votes[cand][_norm(str(ce.get("effect", "unknown"))) or "unknown"] += 1
            ce_meta.setdefault(cand, ce)      # keep first seen strength/ids/why
    merged_effects = []
    for c in cand_names:
        if not eff_votes[c]:
            continue
        eff = eff_votes[c].most_common(1)[0][0]
        base = dict(ce_meta.get(c, {}))
        base.update({"candidate": c, "effect": eff})
        merged_effects.append(base)
    first = samples[0]
    return {"discriminating": disc_votes * 2 >= len(samples),
            "value_condition": first.get("value_condition", ""),
            "why": first.get("why", ""),
            "candidate_effects": merged_effects}


def _pheno_veto(dxidx, dcov, finding: str, rule_in: str,
                cand_names: list[str]) -> dict:
    """P5: phenotype set-difference veto. If the finding falls in the candidate
    INTERSECTION (in >=2 candidates' phenotype sets and NOT unique to rule_in),
    it cannot be a leaf-level discriminator. HARD veto only when coverage is
    sufficient (rule_in + >=1 competitor carry non-empty phenotype sets);
    otherwise SOFT (annotate, do not block)."""
    if dxidx is None:
        return {"veto": False, "hard": False, "reason": "no_index"}
    if not set(dcov._salient_tokens(finding)):
        return {"veto": False, "hard": False, "reason": "no_tokens"}
    pi = _pheno_intersection(dxidx, dcov, finding, cand_names)
    present, n_present, covered = pi["present"], pi["n_present"], pi["covered"]
    ri = next((c for c in cand_names if _norm(c) == _norm(rule_in)), rule_in)
    unique_to_ri = present.get(ri, False) and n_present == 1
    in_intersection = n_present >= 2 and not unique_to_ri
    sufficient = (len(covered) >= 2 and ri in covered)
    if in_intersection:
        return {"veto": True, "hard": bool(sufficient),
                "reason": f"in_intersection(n={n_present})", "present": present}
    return {"veto": False, "hard": False,
            "reason": f"n_present={n_present}", "present": present}


def _entail_check(llm, finding: str, rule_in: str, rule_out: list[str],
                  cond: str, ev: list[dict], used_ids: list[str]) -> dict:
    """P6: independent textual-entailment validator, decoupled from the compiler.
    Confirms the cited evidence entails BOTH support (rule_in present/stronger)
    AND contrast (competitor absent/weaker). Returns entailed yes/no/conflict."""
    cited = [e for e in ev if not used_ids or e["ev_id"] in used_ids] or ev
    claim = (f"finding '{finding}'"
             + (f" (at {cond})" if cond else "")
             + f" rules IN {rule_in}"
             + (f" and rules OUT {', '.join(rule_out)}" if rule_out else ""))
    try:
        res = llm.call_module(
            "DiscriminatorEntail", _ENTAIL_PROMPT,
            {"claim": claim,
             "evidence_excerpts": [{"id": e["ev_id"], "candidate": e["candidate"],
                                    "source": e["source"], "text": e["text"]}
                                   for e in cited]})
    except Exception as e:  # noqa: BLE001
        print(f"[err entail] {finding[:20]}: {e}")
        return {"entailed": "no", "why": "entail_error"}
    return {"entailed": _norm(str(res.get("entailed", "no"))) or "no",
            "has_support": bool(res.get("has_support")),
            "has_contrast": bool(res.get("has_contrast")),
            "why": str(res.get("why", ""))}


def _gate_query_keys(case, cfg, resolver=None) -> dict:
    """B0/B1: per-candidate retrieval/membership query STRING keyed on cfg.gate_key.
      concrete -> real candidate name (identity; masks the production defect).
      abstract -> the L1 family label l1_parent (mirrors production
                  plan_temporary_leaves keying on b.label).
      expand   -> expand the abstract family label back to concrete entities and
                  pick the one that best matches the candidate; falls back to the
                  abstract label when the resolver misses (measures resolver
                  coverage — the fix's ceiling)."""
    keys: dict = {}
    for c in case["candidates"]:
        name = c["name"]
        parent = c.get("l1_parent") or name
        if cfg.gate_key == "concrete":
            keys[name] = name
        elif cfg.gate_key == "abstract":
            keys[name] = parent
        elif cfg.gate_key == "expand":
            ents = []
            if resolver is not None:
                try:
                    ents = resolver.expand_to_entities(parent, limit=6)
                except Exception:  # noqa: BLE001
                    ents = []
            nl = _norm(name)
            hit = next((e for e in ents
                        if _norm(e) == nl or nl in _norm(e) or _norm(e) in nl), "")
            keys[name] = hit or (ents[0] if ents else parent)
    return keys


def _compile_rule(llm, kb, dcov, evp, normalizer, dxidx, case, f, cfg):
    """Compile one contested finding into a structured rule under config cfg."""
    finding = f["finding"]
    cand_names = [c["name"] for c in case["candidates"]]
    query_keys = case.get("_query_keys") or {}
    meta = (_finding_meta(normalizer, evp, finding) if cfg.normalize
            else {"polarity": evp._finding_polarity(finding), "value_state": "",
                  "direction": "unknown", "test": None})
    ev = _search_evidence(kb, dcov, finding, cand_names, cfg, query_keys)
    rule = {"finding": finding, "meta": meta, "n_evidence": len(ev),
            "evidence": ev, "verdict": "common", "rule_in": "", "rule_out": [],
            "value_condition": "", "why": "", "effects": [],
            "discriminating": False, "used_ids": [],
            "target_level": "leaf", "gates": {}}
    if not ev:
        rule["why"] = "no_evidence"
        return rule

    # ── compile (matrix in P3+, else single rule_in) ──────────────────────────
    if cfg.matrix:
        payload = {"finding": finding, "candidates": cand_names,
                   "evidence_excerpts": [
                       {"id": e["ev_id"], "candidate": e["candidate"],
                        "source": e["source"], "text": e["text"]} for e in ev]}
        if cfg.normalize and (meta["test"] or meta["value_state"]):
            payload["parsed_value"] = {"test": meta["test"],
                                       "value_state": meta["value_state"]}
        # A1: sample the matrix k times and majority-vote per candidate effect.
        _samples = []
        for _ in range(max(1, cfg.self_consistency)):
            try:
                _samples.append(llm.call_module(
                    "DiscriminatorAgentMatrix", _DISC_AGENT_MATRIX_PROMPT,
                    payload))
            except Exception as e:  # noqa: BLE001
                print(f"[err disc-matrix] {case['id']}/{finding[:20]}: {e}")
        res = _vote_matrix(_samples, case["candidates"]) if _samples else {}
        rule["discriminating"] = bool(res.get("discriminating"))
        rule["value_condition"] = str(res.get("value_condition", "") or "")
        rule["why"] = str(res.get("why", "") or "")
        effects = []
        for ce in (res.get("candidate_effects") or []):
            cand = match_candidate(str(ce.get("candidate", "")),
                                   case["candidates"])
            if not cand or cand == "none":
                continue
            effects.append({
                "candidate": cand,
                "effect": _norm(str(ce.get("effect", "unknown"))) or "unknown",
                "strength": _norm(str(ce.get("strength", "weak"))) or "weak",
                "evidence_ids": [str(x) for x in (ce.get("evidence_ids") or [])],
                "why": str(ce.get("why", ""))})
        rule["effects"] = effects
        rule_in_cands = [e["candidate"] for e in effects
                         if e["effect"] == "rule_in"]
        # A finding that "rules IN" >=2 candidates is self-evidently NON-
        # discriminating (it cannot make two competitors both more likely). Flag
        # it; the consensus-none gate turns this into a DIRECTION "answer none".
        rule["multi_support"] = len(rule_in_cands) >= cfg.multi_support_min
        rule["rule_in"] = rule_in_cands[0] if rule_in_cands else ""
        rule["rule_out"] = [e["candidate"] for e in effects
                            if e["effect"] == "rule_out"]
        rule["used_ids"] = sorted({i for e in effects
                                   for i in e["evidence_ids"]})
        rule["verdict"] = "use" if (rule["discriminating"]
                                    and (rule["rule_in"] or rule["rule_out"])) \
            else "common"
    else:
        try:
            res = llm.call_module(
                "DiscriminatorAgent", _DISC_AGENT_PROMPT,
                {"finding": finding, "candidates": cand_names,
                 "evidence_excerpts": [{"candidate": e["candidate"],
                                        "source": e["source"], "text": e["text"]}
                                       for e in ev]})
        except Exception as e:  # noqa: BLE001
            print(f"[err disc-agent] {case['id']}/{finding[:20]}: {e}")
            res = {}
        rule["verdict"] = _norm(str(res.get("verdict", "common"))) or "common"
        rule["rule_in"] = match_candidate(str(res.get("rule_in", "")),
                                          case["candidates"])
        rule["rule_out"] = [match_candidate(str(x), case["candidates"])
                            for x in (res.get("rule_out") or [])]
        rule["rule_out"] = [r for r in rule["rule_out"] if r and r != "none"]
        rule["value_condition"] = str(res.get("value_condition", "") or "")
        rule["why"] = str(res.get("why", "") or "")
        rule["discriminating"] = rule["verdict"] == "use"

    # ── P2 polarity routing: a negated/normal finding may NOT rule IN; if it
    #    named a rule_in, retype that as a rule-OUT of that same candidate ──────
    if meta["polarity"] < 0 and rule["rule_in"]:
        if cfg.normalize:
            rule["rule_out"] = sorted(set(rule["rule_out"]) | {rule["rule_in"]})
            rule["why"] = "polarity_retyped_ruleout; " + rule["why"]
        rule["rule_in"] = ""
    rule["verdict"] = "use" if (rule["rule_in"] or rule["rule_out"]) else "common"

    # ── phenotype-intersection confirmation (P5cp): the SAFE structured signal ─
    # Present-in >=2 candidates' phenotype sets AND NOT unique to the rule_in ->
    # the finding is genuinely in the candidate intersection (a real common).
    if cfg.consensus_none or cfg.veto:
        if cfg.corpus_pheno:
            pi = _corpus_pheno_intersection(
                llm, finding, cand_names, ev,
                meta if cfg.value_conditioned else None,
                k=cfg.self_consistency, query_keys=query_keys)
            rule["pheno_source"] = ("corpus_vc" if cfg.value_conditioned
                                    else "corpus")
        else:
            pi = _pheno_intersection(dxidx, dcov, finding, cand_names,
                                     jaccard=cfg.jaccard)
            rule["pheno_source"] = "kg"
        ri_name = next((c for c in cand_names
                        if _norm(c) == _norm(rule["rule_in"])), rule["rule_in"])
        unique_to_ri = pi["present"].get(ri_name, False) and pi["n_present"] == 1
        rule["pheno_present"] = pi["n_present"]
        rule["pheno_common"] = pi["n_present"] >= 2 and not unique_to_ri
        rule["pheno_covered"] = len(pi["covered"])
        rule["gates"]["pheno_intersection"] = {
            "source": rule["pheno_source"], "n_present": pi["n_present"],
            "present": pi["present"], "covered": pi["covered"]}

    # ── consensus-none collapse (P5c): a multi-candidate rule_in is not a USE ──
    # With pheno_confirm ON, only collapse when the phenotype intersection AGREES
    # (so a matrix that spuriously double-labels a decisive finding — e.g. weight
    # loss, absent from every phenotype set — is NOT collapsed).
    if cfg.consensus_none and rule.get("multi_support") and rule["rule_in"]:
        confirmed = (not cfg.pheno_confirm) or rule.get("pheno_common")
        if confirmed:
            rule["verdict"] = "common"
            rule["rule_in"] = ""
            rule["why"] = "multi_support_collapse; " + rule["why"]

    # ── audit provenance (P0): did we even RETRIEVE a contrast? ───────────────
    ri = _norm(rule["rule_in"] or (rule["rule_out"][0] if rule["rule_out"] else ""))
    rule["had_support_evidence"] = any(_norm(e["candidate"]) == ri for e in ev)
    rule["had_contrast_evidence"] = any(
        (_norm(e["candidate"]) != ri) and (e["has_compare"] or e["has_neg"])
        for e in ev)

    # ── P4 admission gate ─────────────────────────────────────────────────────
    if cfg.gate and rule["verdict"] == "use" and rule["rule_in"]:
        adm = _admission(finding, rule["rule_in"], cand_names, ev, kb, meta)
        rule["gates"]["admission"] = adm
        if not adm["admit"]:
            rule["verdict"] = "common"
            rule["why"] = "admission_denied; " + rule["why"]
            rule["rule_in"] = ""

    # ── P5 phenotype/parent-child veto ────────────────────────────────────────
    if cfg.veto and rule["rule_in"]:
        vres = _pheno_veto(dxidx, dcov, finding, rule["rule_in"], cand_names)
        rule["gates"]["veto"] = vres
        if vres["veto"] and vres["hard"]:
            rule["verdict"] = "common"
            rule["why"] = "pheno_veto_hard; " + rule["why"]
            rule["rule_in"] = ""
        # parent/child target_level from the case's documented subtype structure
        pc = case.get("parent_child")
        if pc:
            trap_set = {(_ff.get("finding") or "").lower()
                        for _ff in case["findings"]
                        if _ff.get("role") == "parent_child_trap"}
            if finding.lower() in trap_set:
                rule["target_level"] = "parent"

    # ── P6 independent entailment validation ──────────────────────────────────
    # The validator targets the §11.2.2 error: an ASSOCIATION-only USE (evidence
    # says "F occurs in A" with no competitor contrast). It may therefore veto a
    # USE that rests ONLY on paired-text — but must NOT veto one that also has an
    # INDEPENDENT anchor (a reliable LR or a high-specificity claim), else it
    # over-abstains on a sparse corpus (observed: USE 8->1). 'conflict' always
    # abstains (contradictory evidence).
    if cfg.entail and rule["verdict"] == "use" and rule["rule_in"]:
        ent = _entail_check(llm, finding, rule["rule_in"], rule["rule_out"],
                            rule["value_condition"], ev, rule["used_ids"])
        rule["gates"]["entail"] = ent
        adm = rule["gates"].get("admission") or {}
        anchored = ("reliable_lr" in adm.get("reasons", [])
                    or "highspec" in adm.get("reasons", []))
        veto = (ent["entailed"] == "conflict"
                or (ent["entailed"] == "no" and not anchored))
        if veto:
            rule["verdict"] = "common"
            rule["why"] = f"entail_{ent['entailed']}; " + rule["why"]
            rule["rule_in"] = ""
    # trim heavy evidence text from the audit payload (keep ids + flags)
    rule["evidence"] = [{k: e[k] for k in ("ev_id", "chunk_id", "source",
                                           "candidate", "has_compare", "has_neg",
                                           "has_num", "has_highspec")}
                        for e in ev]
    return rule


def _routed_blocks(rules: list[dict], cfg: DiscAgentConfig) -> dict:
    """P7: turn compiled rules into per-consumer injection blocks. When
    cfg.route is off, emit the legacy combined USE prose for SELECT + DIRECTION
    only (v1 scope). When on, split into select / direction / ruleout / parent."""
    use_rules = [r for r in rules if r["verdict"] == "use" and r["rule_in"]]
    # grounded-neutral findings: evidence-backed non-discriminating (P3 only) —
    # this is the SAFE denoise signal (unlike the mention-based common list).
    neutral_rules = [r for r in rules
                     if cfg.matrix and not r.get("discriminating")
                     and r.get("effects") and r["verdict"] != "use"]

    def _use_line(r):
        cond = f" (at {r['value_condition']})" if r["value_condition"] else ""
        ro = (f"; argues against {', '.join(r['rule_out'])}"
              if r["rule_out"] else "")
        return f"- {r['finding']} [USE]{cond}: supports {r['rule_in']}{ro}."

    # consensus-none list (P5c): findings independent signals agree are NON-
    # discriminating -> instruct DIRECTION to answer none. Restricted so a
    # surviving single-rule_in USE is never suppressed (no rule-in collapse).
    none_rules = []
    if cfg.consensus_none:
        for r in rules:
            if r["rule_in"]:            # a live USE — never suppress
                continue
            ms = bool(r.get("multi_support"))
            all_neutral = bool(cfg.matrix and not r.get("discriminating")
                               and r.get("effects"))
            trigger = ms or (all_neutral and not cfg.consensus_strict)
            # P5cp: require an INDEPENDENT phenotype-intersection confirmation
            # that the finding really is common before telling DIRECTION "none".
            if cfg.pheno_confirm and not r.get("pheno_common"):
                trigger = False
            if trigger:
                none_rules.append(r)
    none_block = ""
    if none_rules:
        if cfg.soft_none:
            # A6: soft signal — a DOWN-WEIGHT/AVOID hint, NOT a hard override.
            # Preserves the model's ability to still name a candidate when the
            # vignette strongly indicates one (protects a mis-graded decisive
            # finding), while nudging away from spurious rule-ins.
            none_block = ("\nLIKELY NON-SPECIFIC (independent signals suggest each "
                          "is compatible with MULTIPLE candidates — treat as weak "
                          "evidence and PREFER other findings; answer none unless "
                          "the vignette clearly ties it to ONE candidate):\n"
                          + "\n".join(f"- {r['finding']}" for r in none_rules))
        else:
            none_block = ("\nNON-DISCRIMINATING (evidence shows each is compatible "
                          "with / supports MULTIPLE candidates — for these you MUST "
                          "answer none):\n"
                          + "\n".join(f"- {r['finding']}" for r in none_rules))

    combined = ""
    if use_rules or none_block:
        head = (
            "EVIDENCE-COMPILED DISCRIMINATOR RULES (a per-finding agent read "
            "retrieved guideline/case-report evidence and compiled how — and at "
            "what result value — each contested finding separates the candidates)."
            " Use these to guide direction; findings NOT listed are unaffected — "
            "judge them normally:\n")
        combined = (head + "\n".join(_use_line(r) for r in use_rules)
                    + none_block).strip()

    if not cfg.route:
        # SELECT gets only the PREFER (USE) prose; DIRECTION also gets the
        # consensus none-list. (When there are no USE rules, SELECT stays empty.)
        sel_block = ""
        if use_rules:
            sel_block = (
                "EVIDENCE-COMPILED DISCRIMINATOR RULES: prefer these findings — "
                "each has an evidence-grounded discriminating direction:\n"
                + "\n".join(_use_line(r) for r in use_rules))
        return {"select": sel_block, "direction": combined,
                "ruleout": "", "parent": ""}

    # routed --------------------------------------------------------------------
    sel_lines = [f"- PREFER: {r['finding']}" for r in use_rules]
    sel_lines += [f"- AVOID (evidence-grounded non-discriminating): {r['finding']}"
                  for r in neutral_rules]
    select = ("EVIDENCE-COMPILED DISCRIMINATOR GUIDANCE (prefer the PREFER "
              "findings; the AVOID findings were shown by evidence to be common "
              "across candidates):\n" + "\n".join(sel_lines)) if sel_lines else ""

    # DIRECTION gets ONLY the grounded USE directions. Grounded-neutral findings
    # are deliberately NOT injected here as "answer none": doing so recreated the
    # denoise over-suppression (a single mis-graded neutral crushes rule-in —
    # DIR 86%->59% at the ablation p7). Neutral only steers SELECT (AVOID), which
    # is safe because it changes WHICH finding is picked, not the direction call.
    dir_lines = [_use_line(r) for r in use_rules]
    direction = ("EVIDENCE-COMPILED DISCRIMINATOR RULES (use the stated "
                 "direction; findings NOT listed are judged normally):\n"
                 + "\n".join(dir_lines)) if dir_lines else ""

    ro_rules = [r for r in rules if r["verdict"] == "use" and r["rule_out"]
                and r.get("target_level", "leaf") == "leaf"]
    ruleout = ""
    if ro_rules:
        rl = [f"- {r['finding']}"
              + (f" (at {r['value_condition']})" if r["value_condition"] else "")
              + f": argues AGAINST {', '.join(r['rule_out'])}." for r in ro_rules]
        ruleout = ("EVIDENCE-COMPILED RULE-OUT RULES (structured; the finding, at "
                   "its stated value, argues against the named candidate):\n"
                   + "\n".join(rl))

    parent_rules = [r for r in rules if r.get("target_level") == "parent"]
    parent = ""
    if parent_rules:
        pl = [f"- {r['finding']}: acts at the PARENT-FAMILY level (a subtype "
              f"feature — does NOT rule out the family)." for r in parent_rules]
        parent = ("EVIDENCE-COMPILED PARENT-LEVEL NOTES:\n" + "\n".join(pl))

    return {"select": select, "direction": direction,
            "ruleout": ruleout, "parent": parent}


def _build_disc_blocks_v2(llm, kb, ds, cfg: DiscAgentConfig,
                          normalizer=None, dxidx=None) -> dict:
    """v2 disc-agent builder. Runs the P0..P7 pipeline (per cfg) over each case's
    CONTESTED findings and emits routed injection blocks + a rich audit."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "evp_pol", PROJECT_ROOT / "scripts" / "eval_evidence_precision.py")
    evp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evp)
    spec2 = importlib.util.spec_from_file_location(
        "dcov_ev", PROJECT_ROOT / "scripts" / "eval_discriminator_coverage.py")
    dcov = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(dcov)

    # B0/B1: build a name resolver once when the arm queries with a non-concrete
    # key (abstract family label / expand-to-entities).
    resolver = None
    if cfg.gate_key in ("abstract", "expand"):
        try:
            from agentclinic_tree_dx.knowledge.disease_name_resolver import (
                DiseaseNameResolver)
            resolver = DiseaseNameResolver()
        except Exception as e:  # noqa: BLE001
            print(f"[disc-v2] DiseaseNameResolver unavailable: {e}")

    blocks: dict = {}
    audit: dict = {}
    keyaudit: dict = {}
    entry_audit: dict = {}
    for case in ds["cases"]:
        case["_query_keys"] = _gate_query_keys(case, cfg, resolver)
        if cfg.gate_key != "concrete":
            keyaudit[case["id"]] = dict(case["_query_keys"])
        contested, entry_audit[case["id"]] = _entry_findings(
            kb, case, cfg.entry_gate)
        rules = [_compile_rule(llm, kb, dcov, evp, normalizer, dxidx, case, f, cfg)
                 for f in contested]
        if cfg.hier_aggregate:
            rules = _hier_aggregate(rules, case)
        blocks[case["id"]] = _routed_blocks(rules, cfg)
        audit[case["id"]] = rules
        n_use = sum(1 for r in rules if r["verdict"] == "use")
        n_neu = sum(1 for r in rules if cfg.matrix
                    and not r.get("discriminating") and r.get("effects"))
        print(f"[disc-v2/{cfg.stage} {case['id']:<16}] contested={len(contested)} "
              f"USE={n_use} NEUTRAL={n_neu} COMMON={len(rules) - n_use}",
              flush=True)
    return {"blocks": blocks, "audit": audit, "key_audit": keyaudit,
            "entry_audit": entry_audit}


def _hier_aggregate(rules: list[dict], case) -> list[dict]:
    """B2: roll the finding x concrete-disease effect matrix up to the L1 family
    with provenance, enforcing parent/child consistency:
      R1 any live child supports F        -> family SUPPORTED (support parent)
      R2 ALL live children conflict with F -> family RULED OUT (rule-out parent)
      R3 a child-specific F (supports/rules a subset) -> discriminates that CHILD,
         NOT the whole family (do NOT rule the family out on one child).
    Annotates each rule with `hier` (per-parent verdict + which child) and, when a
    rule_out is only child-specific, retypes it as a leaf-level call carrying a
    parent note so a sibling-supported family is never wrongly excluded."""
    fam_of = {c["name"]: (c.get("l1_parent") or c["name"])
              for c in case["candidates"]}
    fams: dict = {}
    for c in case["candidates"]:
        fams.setdefault(c.get("l1_parent") or c["name"], []).append(c["name"])
    for r in rules:
        effects = r.get("effects") or []
        if not effects:
            continue
        eff_by_cand = {e["candidate"]: e["effect"] for e in effects}
        hier = {}
        for fam, children in fams.items():
            seen = [eff_by_cand.get(ch) for ch in children if ch in eff_by_cand]
            if not seen:
                continue
            supported = [ch for ch in children
                         if eff_by_cand.get(ch) == "rule_in"]
            conflict = [ch for ch in children
                        if eff_by_cand.get(ch) == "rule_out"]
            if supported:
                verdict, child = "support_parent", supported
            elif conflict and len(conflict) == len(
                    [ch for ch in children if ch in eff_by_cand]):
                verdict, child = "ruleout_parent", conflict
            elif conflict:
                verdict, child = "child_specific", conflict
            else:
                verdict, child = "neutral", []
            hier[fam] = {"verdict": verdict, "children": child}
        r["hier"] = hier
        # R3: a rule_out that only hits SOME children of the rule_in's family
        # must not rule out that family — keep it leaf-level (already leaf), but
        # flag so downstream never promotes it to a parent rule-out.
        if r.get("rule_out"):
            ro_fams = {fam_of.get(x) for x in r["rule_out"]}
            for fam in ro_fams:
                if hier.get(fam, {}).get("verdict") == "child_specific":
                    r["target_level"] = "leaf"
                    r.setdefault("hier_notes", []).append(
                        f"child_specific_ruleout:{fam}")
        # R2: whole-family rule-out is safe to act at parent level.
        if r.get("rule_out"):
            for fam, h in hier.items():
                if h["verdict"] == "ruleout_parent":
                    r["target_level"] = "parent"
                    r.setdefault("hier_notes", []).append(f"ruleout_parent:{fam}")
    return rules


def _audit_summary(audit: dict) -> dict:
    """P0 attribution baseline: over the compiled USE rules, split the ones that
    lack a contrast into 'contrast not retrieved' vs 'retrieved but ignored'."""
    n_use = n_no_contrast_retrieved = n_contrast_ignored = 0
    for rules in audit.values():
        for r in rules:
            if r["verdict"] != "use" or not r["rule_in"]:
                continue
            n_use += 1
            if not r.get("had_contrast_evidence"):
                n_no_contrast_retrieved += 1
            else:
                n_contrast_ignored += 1
    return {"n_use": n_use,
            "contrast_not_retrieved": n_no_contrast_retrieved,
            "contrast_retrieved_but_ignored": n_contrast_ignored}


if __name__ == "__main__":
    raise SystemExit(main())
