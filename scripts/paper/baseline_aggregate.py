#!/usr/bin/env python3
"""Aggregate multiple ranked diagnosis lists (Self-Consistency RRF / Borda)."""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence


def normalize_disease_key(name: str) -> str:
    text = " ".join(str(name or "").lower().split())
    text = text.replace("-", " ")
    return text


def rrf_aggregate(
    lists: Sequence[Sequence[str]],
    *,
    k: int = 60,
    top_n: int = 2,
) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    display: dict[str, str] = {}
    for ranked in lists:
        for rank, name in enumerate(ranked, start=1):
            key = normalize_disease_key(name)
            if not key:
                continue
            scores[key] += 1.0 / (k + rank)
            display.setdefault(key, str(name).strip())
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [display[key] for key, _ in ordered[:top_n]]


def borda_aggregate(
    lists: Sequence[Sequence[str]],
    *,
    list_len: int = 5,
    top_n: int = 2,
) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    display: dict[str, str] = {}
    for ranked in lists:
        for rank, name in enumerate(ranked, start=1):
            key = normalize_disease_key(name)
            if not key:
                continue
            scores[key] += float(list_len - rank + 1)
            display.setdefault(key, str(name).strip())
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [display[key] for key, _ in ordered[:top_n]]
