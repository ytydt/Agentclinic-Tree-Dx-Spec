#!/usr/bin/env python3
"""What is actually in the 65,750 pmc_oa passages the length floor discards?

"Dropped on length" is only meaningful next to a control.  A 30-character
passage has far fewer chances to contain a disease name than a 700-character
one, so the raw hit rate against the 789-case candidate lists says nothing on
its own.  Three controls are measured alongside it:

  kept            the passages that survive should_keep_chunk, as they are
  length-matched  random windows cut from kept passages, same length profile
  covered         whether the dropped text already appears inside a kept
                  passage of the same article, in which case nothing is lost

and the dropped set is bucketed by shape, because administrative boilerplate
and a criteria member are both short but are not both worth recovering.
"""
from __future__ import annotations

import glob
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
sys.path.insert(0, str(ROOT / "scripts"))
from pmc_oa_ddx_common import should_keep_chunk  # noqa: E402

TASKS = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_tasks_all789.json"
OUT = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/dropped_passage_audit.json"
DUMP = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/dropped_passage_sample.md"

ANNOUNCE = re.compile(
    r"(following|criteri\w*|abnormalit\w*|features?|findings?|manifestations?|"
    r"signs?|symptoms?|elements?|components?|includ\w*|compris\w*|consists?)"
    r"[^.]{0,25}:\s*$", re.I)

# terms so generic that a match carries no diagnostic information
GENERIC = {
    "cancer", "tumor", "tumour", "infection", "trauma", "injury", "disease",
    "disorder", "syndrome", "neoplasm", "carcinoma", "mass", "lesion", "cyst",
    "inflammation", "pain", "fever", "shock", "bleeding", "haemorrhage",
    "hemorrhage", "abscess", "ulcer", "obesity", "malignancy", "sepsis",
    "anemia", "anaemia", "stroke", "seizure", "allergy", "burns", "poisoning",
    "toxicity", "deficiency", "failure", "arrest", "block", "murmur",
}

BOILERPLATE = re.compile(
    r"^(?:not applicable|none|n/?a|nil|see (?:table|figure|fig|section)|"
    r"data (?:not shown|are available)|the authors declare|all authors|"
    r"supplementary|abbreviations?|©|copyright|open access|correspondence|"
    r"received|accepted|published|conflicts? of interest|funding|"
    r"acknowledge?ments?|competing interests?|ethical approval|"
    r"informed consent|availability of data)\b", re.I)
HEADINGLIKE = re.compile(r"^[A-Z][^.!?]{0,60}$")
# a review article's own literature-screening criteria look exactly like a
# criteria set but say nothing about any disease
STUDY_CRITERIA = re.compile(
    r"\b(?:stud(?:y|ies)|article|paper|manuscript|publication|record|report|"
    r"abstract|literature|review|trial|citation)s?\b[^.]{0,60}\b"
    r"(?:includ|exclud|select|eligib|screen|retriev|search)|"
    r"\b(?:inclusion|exclusion|eligibility)\s+criteri|"
    r"\b(?:peer.?reviewed|full.?text|english.language|grey literature|"
    r"conference abstract|case report)s?\b", re.I)
NUMERIC = re.compile(r"\d")
CLINICAL = re.compile(
    r"\b(?:mg|mcg|\u00b5g|ml|dl|mmol|mmhg|kg|cm|mm|%|years?|months?|weeks?|days?|"
    r"hours?|patients?|diagnos\w+|treat\w+|therap\w+|symptom\w*|sign|test|"
    r"level|count|ratio|score|grade|stage|positive|negative|elevated|reduced|"
    r"normal|abnormal|present|absent)\b", re.I)


WORD = re.compile(r"[a-z0-9]+")


def build_vocab() -> tuple[set[str], list[int]]:
    """Candidate names as a token-n-gram set.

    A 251 kB regex alternation scanned over every passage costs about 100
    minutes on this corpus; hashing the text's own n-grams against a set is the
    same query and runs in a few minutes.
    """
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    terms: set[str] = set()
    for t in tasks:
        names = [t.get("gold") or ""]
        for c in t.get("candidates") or []:
            names.append(c.get("label") or "")
            names.extend(c.get("aliases") or [])
        for raw in names:
            s = re.sub(r"\s*\([^)]*\)\s*", " ", raw or "")
            toks = WORD.findall(s.lower())
            if not toks:
                continue
            key = " ".join(toks)
            if len(key) < 5:
                continue
            if len(toks) == 1 and key in GENERIC:
                continue
            # an all-caps short string is an acronym (PE, MI, SLE): too ambiguous
            if (raw or "").strip().isupper() and len((raw or "").strip()) <= 5:
                continue
            terms.add(key)
    sizes = sorted({len(k.split()) for k in terms})
    return terms, sizes


def hits(vocab: tuple[set[str], list[int]], text: str) -> bool:
    terms, sizes = vocab
    toks = WORD.findall(text.lower())
    for n in sizes:
        if n > len(toks):
            break
        for i in range(len(toks) - n + 1):
            if " ".join(toks[i:i + n]) in terms:
                return True
    return False


def bucket(text: str, under_announce: bool) -> str:
    if BOILERPLATE.match(text):
        return "boilerplate"
    if under_announce:
        return "criteria_member"
    if HEADINGLIKE.match(text) and not text.endswith("."):
        return "heading_or_label"
    if NUMERIC.search(text) and len(re.findall(r"[A-Za-z]{3,}", text)) <= 3:
        return "numeric_fragment"
    if CLINICAL.search(text):
        return "clinical_prose_fragment"
    return "other_fragment"


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    pats = build_vocab()
    print(f"vocabulary: {len(pats[0])} candidate names, "
          f"token lengths {pats[1]}", flush=True)

    files = sorted(glob.glob(str(ROOT / "data/cpg/raw/pmc_oa/*.json")))
    if limit:
        files = files[:limit]

    rng = random.Random(0)
    stat = Counter()
    buckets = Counter()
    bucket_hits = Counter()
    lens_dropped: list[int] = []
    lens_kept: list[int] = []
    control_pool: list[str] = []
    samples: dict[str, list[str]] = defaultdict(list)

    for fi, f in enumerate(files):
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        coll = payload[0] if isinstance(payload, list) else payload
        for doc in coll.get("documents") or []:
            title = ""
            stack: list[str] = []
            seq = []
            for ps in doc.get("passages") or []:
                inf = ps.get("infons") or {}
                pt = str(inf.get("type") or "")
                txt = (ps.get("text") or "").strip()
                if not txt:
                    continue
                if pt.startswith("title"):
                    lvl = int(re.sub(r"\D", "", pt) or "1")
                    while len(stack) >= lvl:
                        stack.pop()
                    stack.append(txt)
                    continue
                if pt in {"front", "abstract"}:
                    if pt == "front" and not title:
                        title = txt
                    continue
                seq.append((pt, txt, list(stack)))

            kept_texts = []
            dropped: list[tuple[str, bool]] = []
            for i, (pt, txt, st) in enumerate(seq):
                last = st[-1] if st else ""
                if should_keep_chunk(last, txt, pt, section_stack=st,
                                     article_title=title):
                    kept_texts.append(txt)
                    lens_kept.append(len(txt))
                    stat["kept"] += 1
                    if hits(pats, txt):
                        stat["kept_hit"] += 1
                    if len(control_pool) < 40000 and len(txt) > 200:
                        control_pool.append(txt)
                    continue
                if should_keep_chunk(last, txt + " x" * 60, pt,
                                     section_stack=st, article_title=title):
                    ann = any(ANNOUNCE.search(seq[j][1])
                              for j in range(max(0, i - 6), i))
                    dropped.append((txt, ann))

            blob = "\n".join(kept_texts)
            for txt, ann in dropped:
                stat["dropped"] += 1
                lens_dropped.append(len(txt))
                b = bucket(txt, ann)
                buckets[b] += 1
                h = hits(pats, txt)
                if h:
                    stat["dropped_hit"] += 1
                    bucket_hits[b] += 1
                if txt in blob:
                    stat["dropped_covered_elsewhere"] += 1
                if CLINICAL.search(txt):
                    stat["dropped_clinical_term"] += 1
                if h and CLINICAL.search(txt) and not BOILERPLATE.match(txt):
                    stat["dropped_hit_and_clinical"] += 1
                if STUDY_CRITERIA.search(txt):
                    stat["dropped_study_criteria"] += 1
                if len(samples[b]) < 12 and rng.random() < 0.02:
                    samples[b].append(txt[:220])

        if fi % 1500 == 0 and fi:
            print(f"  {fi}/{len(files)}", flush=True)

    # length-matched control: windows cut from kept passages
    ctrl_hit = ctrl_n = 0
    for L in lens_dropped:
        if not control_pool:
            break
        src = control_pool[rng.randrange(len(control_pool))]
        if len(src) <= L:
            continue
        s = rng.randrange(0, len(src) - L)
        ctrl_n += 1
        if hits(pats, src[s:s + L]):
            ctrl_hit += 1

    lens_dropped.sort()
    def pct(v, n):
        return f"{v / n:.2%}" if n else "n/a"

    d, k = stat["dropped"], stat["kept"]
    print(f"\ndropped on length : {d}")
    print(f"kept              : {k}")
    print(f"\nlength of dropped : median {lens_dropped[len(lens_dropped)//2]}  "
          f"p90 {lens_dropped[int(len(lens_dropped)*0.9)]}  "
          f"mean {sum(lens_dropped)/len(lens_dropped):.0f}")
    print(f"length of kept    : mean {sum(lens_kept)/len(lens_kept):.0f}")

    print("\ncandidate-name hit rate")
    print(f"  dropped                         {pct(stat['dropped_hit'], d)}")
    print(f"  length-matched control          {pct(ctrl_hit, ctrl_n)}")
    print(f"  kept (not length-matched)       {pct(stat['kept_hit'], k)}")

    print("\nis the dropped text lost?")
    print(f"  already inside a kept passage   "
          f"{stat['dropped_covered_elsewhere']:>6}  "
          f"{pct(stat['dropped_covered_elsewhere'], d)}")
    print(f"  carries a clinical term         "
          f"{stat['dropped_clinical_term']:>6}  "
          f"{pct(stat['dropped_clinical_term'], d)}")
    print(f"  candidate name AND clinical     "
          f"{stat['dropped_hit_and_clinical']:>6}  "
          f"{pct(stat['dropped_hit_and_clinical'], d)}")
    print(f"  a review's own study criteria   "
          f"{stat['dropped_study_criteria']:>6}  "
          f"{pct(stat['dropped_study_criteria'], d)}")

    print("\nshape of the dropped set")
    for b, n in buckets.most_common():
        print(f"  {b:<26}{n:>7}  {n/d:6.1%}   candidate-hit "
              f"{pct(bucket_hits[b], n)}")

    OUT.write_text(json.dumps({
        "dropped": d, "kept": k,
        "dropped_hit": stat["dropped_hit"],
        "kept_hit": stat["kept_hit"],
        "control_hit": ctrl_hit, "control_n": ctrl_n,
        "covered_elsewhere": stat["dropped_covered_elsewhere"],
        "clinical_term": stat["dropped_clinical_term"],
        "hit_and_clinical": stat["dropped_hit_and_clinical"],
        "study_criteria": stat["dropped_study_criteria"],
        "buckets": dict(buckets), "bucket_hits": dict(bucket_hits),
        "len_median": lens_dropped[len(lens_dropped) // 2],
        "len_mean": sum(lens_dropped) / len(lens_dropped),
    }, indent=2), encoding="utf-8")

    with DUMP.open("w", encoding="utf-8") as fh:
        fh.write("# 被长度下限丢弃的 passage 抽样（按形态分组）\n")
        for b, rows in samples.items():
            fh.write(f"\n## {b}  ({buckets[b]}, {buckets[b]/d:.1%})\n\n")
            for r in rows:
                fh.write(f"- {r}\n")
    print(f"\nwrote {OUT.name}, {DUMP.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
