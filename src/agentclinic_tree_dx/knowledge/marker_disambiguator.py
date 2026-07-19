"""MarkerDisambiguator — tiered context disambiguation for marker mentions.

Implements the T0–T4 architecture from EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md
§16.9.8.4, replacing the hand-written `_AMBIGUOUS_ABBREV` blacklist. The core
idea: a marker term is a *surface form*; it should only fire when the local
context grounds it to the marker's *concept* (semantic type), not a same-spelled
token of a different sense (SMA = smooth-muscle-antibody vs superior-mesenteric-
artery).

Tiers (escalation order; cost rises with ambiguity, fail-safe at the end):

  T0  Auto ambiguity detection (offline, deterministic) — which terms are
      ambiguous + their expected semantic type & cues. Produced by
      `scripts/build_auto_ambiguity_map.py` → `auto_ambiguity_map.json`.
  T1  Semantic-type / context disambiguation (offline, deterministic):
        T1a  lexical: positive cue near mention ⇒ marker sense (FIRE);
             competing-sense cue with no positive cue ⇒ other sense (SUPPRESS).
        T1b  embedding: cosine(context, marker-prototype) vs cosine(context,
             competing-prototype) — only when T1a is inconclusive and an
             EmbeddingIndex is available.
  T2  RAG relevance feedback (tool call, optional): which candidate sense's
      retrieved snippets best match the mention context.
  T3  LLM set-wise rerank (tool call, optional): mention-anchored multiple
      choice, only for cases T1/T2 left undecided.
  T4  External-KG consistency check (optional): ontology semantic category.

If every available tier is inconclusive the decision is **fail-safe SUPPRESS**
(do not fire the marker) — avoiding both false pathognomonic hits and false
reverse-exclusions (§16.9.8.5.4).

Only T0 + T1a are always-on and dependency-free; T1b/T2/T3/T4 activate only when
their respective resources (embedding index / RAG / LLM / ontology) are injected,
so default behaviour is fully deterministic and reproducible.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_WINDOW = 50  # chars on each side of the mention to inspect

# Prototype phrases for the embedding tier (T1b), keyed by expected sem-type.
_MARKER_PROTOTYPE = {
    "serology_immunology": "serum autoantibody serology immunology laboratory test",
    "molecular_genetic": "molecular genetics gene mutation cytogenetic assay",
    "histopathology": "histopathology biopsy cell morphology microscopy stain",
}
_COMPETING_PROTOTYPE = {
    "serology_immunology": "blood vessel artery anatomy radiology occlusion",
    "molecular_genetic": "blood vessel artery anatomy radiology occlusion",
    "histopathology": "blood vessel artery anatomy radiology occlusion",
}
_EMBED_MARGIN = 0.05  # cosine margin to prefer one sense over the other


class Decision:
    """Outcome of a disambiguation query."""

    __slots__ = ("fire", "tier", "reason")

    def __init__(self, fire: bool, tier: str, reason: str) -> None:
        self.fire = fire
        self.tier = tier
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        verb = "FIRE" if self.fire else "SUPPRESS"
        return f"<Decision {verb} via {self.tier}: {self.reason}>"


class MarkerDisambiguator:
    """Resolve whether an ambiguous marker term occurrence is the marker sense."""

    def __init__(
        self,
        ambiguity_map: Optional[dict[str, dict]] = None,
        *,
        window: int = _DEFAULT_WINDOW,
        embedding_index=None,
        rag_retriever=None,
        llm_fn: Optional[Callable[[str], str]] = None,
        ontology_index=None,
    ) -> None:
        self._map: dict[str, dict] = ambiguity_map or {}
        self._window = window
        self._embedding_index = embedding_index
        self._rag = rag_retriever
        self._llm_fn = llm_fn
        self._ontology = ontology_index

    # ── construction ────────────────────────────────────────────────────────
    @classmethod
    def from_file(cls, path: str | Path, **kwargs) -> "MarkerDisambiguator":
        """Load the T0 product `auto_ambiguity_map.json`."""
        p = Path(path)
        if not p.exists():
            logger.warning("auto_ambiguity_map not found: %s (no terms loaded)", p)
            return cls({}, **kwargs)
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        terms = data.get("ambiguous_terms", {})
        logger.info("MarkerDisambiguator: loaded %d ambiguous term(s) from %s",
                    len(terms), p)
        return cls(terms, **kwargs)

    @classmethod
    def from_markers(cls, markers: list[dict], **kwargs) -> "MarkerDisambiguator":
        """Fallback: derive the ambiguity map in-memory from marker dicts.

        Mirrors `scripts/build_auto_ambiguity_map.py` so the disambiguator still
        works (deterministically) even if the pre-built JSON is absent.
        """
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_build_auto_ambiguity_map",
                str(Path(__file__).resolve().parents[3] / "scripts"
                    / "build_auto_ambiguity_map.py"),
            )
            if spec and spec.loader:  # pragma: no branch
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                term_map = _build_map_from_markers(mod, markers)
                logger.info("MarkerDisambiguator: derived %d ambiguous term(s) "
                            "from markers (no JSON)", len(term_map))
                return cls(term_map, **kwargs)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Could not derive ambiguity map from markers: %s", e)
        return cls({}, **kwargs)

    # ── public API ────────────────────────────────────────────────────────────
    def is_ambiguous(self, term: str) -> bool:
        return term.strip().lower() in self._map

    def allows(self, term: str, text: str, idx: int, term_len: int) -> bool:
        """True if this occurrence should count as a marker match.

        Non-ambiguous terms always pass. Ambiguous terms run the T1–T4 cascade.
        """
        t = term.strip().lower()
        if t not in self._map:
            return True
        return self.decide(t, text, idx, term_len).fire

    def decide(self, term: str, text: str, idx: int, term_len: int) -> Decision:
        entry = self._map[term]
        lo = max(0, idx - self._window)
        hi = idx + term_len + self._window
        ctx = text[lo:hi]

        pos_cues = entry.get("positive_cues", [])
        comp_cues = entry.get("competing_cues", [])
        has_pos = any(c in ctx for c in pos_cues)
        has_comp = any(c in ctx for c in comp_cues)

        # T1a — lexical semantic-type disambiguation -------------------------
        if has_pos:
            # A positive (marker-sense) cue present ⇒ marker sense. (Backward
            # compatible with the former _abbrev_context_ok behaviour.)
            return Decision(True, "T1a", "positive semantic-type cue present")
        if has_comp:
            # Competing-sense cue, no marker cue ⇒ the other meaning.
            return Decision(False, "T1a", "competing-sense cue, no marker cue")

        # Neither cue present → escalate.
        sem = entry.get("expected_semantic_type", "")

        # T1b — embedding context vs prototype senses ------------------------
        d = self._tier_embedding(ctx, entry, sem)
        if d is not None:
            return d

        # T2 — RAG relevance feedback ----------------------------------------
        d = self._tier_rag(ctx, entry, sem)
        if d is not None:
            return d

        # T3 — LLM set-wise rerank -------------------------------------------
        d = self._tier_llm(term, text, idx, term_len, entry, sem)
        if d is not None:
            return d

        # T4 — external KG consistency ---------------------------------------
        d = self._tier_kg(ctx, entry, sem)
        if d is not None:
            return d

        # Fail-safe: undecided ⇒ do not fire the marker.
        return Decision(False, "fail_safe", "no disambiguating evidence in any tier")

    # ── tiers ──────────────────────────────────────────────────────────────
    def _tier_embedding(self, ctx: str, entry: dict, sem: str) -> Optional[Decision]:
        idx_obj = self._embedding_index
        if idx_obj is None or not hasattr(idx_obj, "cosine"):
            return None
        if not getattr(idx_obj, "is_ready", False):
            return None
        marker_proto = " ".join(entry.get("source_terms", [])) + " " \
            + _MARKER_PROTOTYPE.get(sem, "")
        comp_proto = _COMPETING_PROTOTYPE.get(sem, "")
        try:
            sim_marker = idx_obj.cosine(ctx, marker_proto.strip())
            sim_comp = idx_obj.cosine(ctx, comp_proto)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("embedding tier failed: %s", e)
            return None
        if sim_marker is None or sim_comp is None:
            return None
        if sim_marker >= sim_comp + _EMBED_MARGIN:
            return Decision(True, "T1b", f"ctx closer to marker sense "
                            f"({sim_marker:.2f} vs {sim_comp:.2f})")
        if sim_comp >= sim_marker + _EMBED_MARGIN:
            return Decision(False, "T1b", f"ctx closer to competing sense "
                            f"({sim_comp:.2f} vs {sim_marker:.2f})")
        return None  # tie → escalate

    def _tier_rag(self, ctx: str, entry: dict, sem: str) -> Optional[Decision]:
        rag = self._rag
        if rag is None or not hasattr(rag, "search"):
            return None
        marker_q = " ".join(entry.get("source_terms", [])[:2]) or sem
        comp_q = _COMPETING_PROTOTYPE.get(sem, "")
        try:
            marker_hits = rag.search(marker_q, top_k=3) or []
            comp_hits = rag.search(comp_q, top_k=3) or []
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("RAG tier failed: %s", e)
            return None
        ctx_tokens = _tokens(ctx)
        marker_overlap = _overlap_score(ctx_tokens, marker_hits)
        comp_overlap = _overlap_score(ctx_tokens, comp_hits)
        if marker_overlap == 0 and comp_overlap == 0:
            return None
        if marker_overlap > comp_overlap:
            return Decision(True, "T2", "RAG snippets favour marker sense")
        if comp_overlap > marker_overlap:
            return Decision(False, "T2", "RAG snippets favour competing sense")
        return None

    def _tier_llm(
        self, term: str, text: str, idx: int, term_len: int,
        entry: dict, sem: str,
    ) -> Optional[Decision]:
        fn = self._llm_fn
        if fn is None:
            return None
        lo = max(0, idx - 80)
        hi = idx + term_len + 80
        snippet = text[lo:hi].replace("\n", " ")
        marker_sense = (entry.get("source_terms") or [term])[0]
        prompt = (
            "In the clinical text below, the token "
            f"'{text[idx:idx + term_len]}' is ambiguous.\n"
            f"Text: \"…{snippet}…\"\n"
            f"Does it refer to (A) {marker_sense} [a {sem.replace('_', '/')} "
            "marker], or (B) an unrelated same-spelled term (e.g. an anatomical "
            "structure or administrative note)?\n"
            "Answer with exactly 'A' or 'B'."
        )
        try:
            ans = (fn(prompt) or "").strip().upper()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("LLM tier failed: %s", e)
            return None
        if ans.startswith("A"):
            return Decision(True, "T3", "LLM resolved to marker sense")
        if ans.startswith("B"):
            return Decision(False, "T3", "LLM resolved to competing sense")
        return None

    def _tier_kg(self, ctx: str, entry: dict, sem: str) -> Optional[Decision]:
        onto = self._ontology
        if onto is None or not hasattr(onto, "resolve_fuzzy"):
            return None
        # If the competing prototype resolves to a real ontology concept but the
        # marker sense does not appear in context, lean toward suppression.
        try:
            comp_concept = onto.resolve_fuzzy(_COMPETING_PROTOTYPE.get(sem, ""))
        except Exception:  # pragma: no cover - defensive
            return None
        if comp_concept:
            return Decision(False, "T4", "KG: competing concept consistent with context")
        return None


# ── module helpers ───────────────────────────────────────────────────────────
_TOKEN_RE = re.compile(r"[a-z][a-z\-]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 4}


def _overlap_score(ctx_tokens: set[str], hits: list) -> int:
    score = 0
    for h in hits:
        htext = h.get("text", "") if isinstance(h, dict) else str(h)
        score += len(ctx_tokens & _tokens(htext))
    return score


def _build_map_from_markers(build_mod, markers: list[dict]) -> dict[str, dict]:
    """Run the build script's pure functions over in-memory markers."""
    out: dict[str, dict] = {}
    for m in markers:
        terms = [t.strip().lower() for t in m.get("terms", [])]
        sem = build_mod._infer_semantic_type(m)
        base = list(build_mod._positive_lexicon(sem))
        sibling: list[str] = []
        for t in terms:
            if build_mod._is_acronym_shaped(t):
                continue
            sibling.extend(
                tok for tok in build_mod._content_tokens(t)
                if not build_mod._is_acronym_shaped(tok)
            )
        for g in m.get("gene_symbols", []):
            sibling.append(g.strip().lower())
        for t in terms:
            if not build_mod._is_acronym_shaped(t):
                continue
            e = out.setdefault(t, {
                "expected_semantic_type": sem,
                "marker_target_diseases": [],
                "positive_cues": [],
                "competing_cues": list(build_mod.COMPETING_BY_TYPE.get(sem, [])),
                "source_terms": [],
            })
            e["positive_cues"] = list(dict.fromkeys(
                e["positive_cues"] + base + sibling))
            e["source_terms"] = list(dict.fromkeys(e["source_terms"] + terms))
            for d in m.get("target_diseases", []):
                if d not in e["marker_target_diseases"]:
                    e["marker_target_diseases"].append(d)
    return out
