"""
Shared helpers for MedEinst / ECR-Agent.

Paper: https://arxiv.org/abs/2601.06636
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM string.

    [UNSPECIFIED] Paper Tables A7–A9 require JSON but do not specify a parser.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in LLM output")
    return json.loads(text[start : end + 1])


def normalize_diagnosis(label: str) -> str:
    """[UNSPECIFIED] Paper uses f(x)=ygt equality with no normalization.

    Using: lowercase, strip, collapse whitespace, drop trailing punctuation.
    Alternatives: exact string match, UMLS CUI, LLM equivalence judge.
    """
    s = " ".join(str(label).lower().split())
    s = s.strip(" .;:,")
    return s


def diagnoses_match(pred: str, gold: str) -> bool:
    """§3.5 — indicator I(f(x)=ygt), with [UNSPECIFIED] normalized_exact."""
    return normalize_diagnosis(pred) == normalize_diagnosis(gold)


def l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Eq. 2 — cos(e_pscript, e_pobs). Vectors must be same length."""
    return sum(x * y for x, y in zip(a, b))


def bow_embed(text: str, vocab: Iterable[str] | None = None) -> list[float]:
    """[UNSPECIFIED] Paper never names the embedding model for Eq. 2.

    Using: L2-normalized bag-of-words over alphanumeric tokens.
    Alternatives: sentence-transformers, OpenAI embeddings, Qwen embeddings.
    """
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if vocab is None:
        vocab = sorted(set(tokens))
    vocab_list = list(vocab)
    index = {t: i for i, t in enumerate(vocab_list)}
    vec = [0.0] * max(len(vocab_list), 1)
    for t in tokens:
        if t in index:
            vec[index[t]] += 1.0
    return l2_normalize(vec)


def load_yaml(path: str | Path) -> Mapping[str, Any]:
    """Load configs/base.yaml. [UNSPECIFIED] paper does not define a config format."""
    import yaml

    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def pairwise_cosine(text_a: str, text_b: str) -> float:
    """Eq. 2 — cos(e_pscript, e_pobs).

    Default encoder is parent-repo MedCPT Query-Encoder (see src/embed.py).
    """
    from src.embed import active_mode, medcpt_cosine

    if active_mode() == "medcpt":
        return medcpt_cosine(text_a, text_b)
    vocab = sorted(set(re.findall(r"[a-z0-9]+", (text_a + " " + text_b).lower())))
    return cosine(bow_embed(text_a, vocab), bow_embed(text_b, vocab))
