"""Structured synonym / granularity snippets for AnswerMapper RAG critic.

Gold-blind: lookup is driven only by option text + candidate leaf labels
(symmetric across options). Uses frozen disease_name_bridge.

Resolution is intentionally conservative (exact / abbrev / long-prefix only)
to avoid false CUI links from substring noise.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_WORD_RE = re.compile(r"[a-z0-9]+", re.I)
_PAREN_RE = re.compile(r"\(([^)]+)\)")


def _norm(text: str) -> str:
    return " ".join(_WORD_RE.findall(str(text or "").lower()))


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(str(text or "").lower()))


class SynonymGranularityRetriever:
    """Duck-typed retriever: ``search`` + ``search_option_leaves``."""

    def __init__(
        self,
        bridge_path: str | Path,
        *,
        max_aliases: int = 8,
    ) -> None:
        path = Path(bridge_path)
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        self._by_canonical: dict[str, dict[str, Any]] = {
            _norm(k): v
            for k, v in (data.get("by_canonical") or {}).items()
            if isinstance(v, dict)
        }
        self._by_alias: dict[str, str] = {}
        for k, v in (data.get("by_alias") or {}).items():
            self._by_alias[_norm(k)] = _norm(v)
        for canon in self._by_canonical:
            self._by_alias.setdefault(canon, canon)
        # sorted alias keys for prefix search (length desc)
        self._alias_keys_desc = sorted(self._by_alias.keys(), key=len, reverse=True)
        self.max_aliases = int(max_aliases)
        self._ready = bool(self._by_canonical)

    @property
    def is_ready(self) -> bool:
        return self._ready

    def _entry_for_canon(self, canon_norm: str) -> Optional[dict[str, Any]]:
        hit = self._by_canonical.get(_norm(canon_norm))
        return hit if isinstance(hit, dict) else None

    def _resolve(self, label: str) -> Optional[dict[str, Any]]:
        key = _norm(label)
        if not key:
            return None
        # 1) exact
        if key in self._by_canonical:
            return self._by_canonical[key]
        mapped = self._by_alias.get(key)
        if mapped:
            hit = self._entry_for_canon(mapped)
            if hit:
                return hit
        # 2) parenthetical abbreviations, e.g. "(GCRG)" / "(MVH)"
        for abbr in _PAREN_RE.findall(str(label or "")):
            akey = _norm(abbr)
            if len(akey) < 2:
                continue
            if akey in self._by_canonical:
                return self._by_canonical[akey]
            mapped = self._by_alias.get(akey)
            if mapped:
                hit = self._entry_for_canon(mapped)
                if hit:
                    return hit
        # 3) strip parentheticals then exact
        stripped = _norm(_PAREN_RE.sub(" ", str(label or "")))
        if stripped and stripped != key:
            if stripped in self._by_canonical:
                return self._by_canonical[stripped]
            mapped = self._by_alias.get(stripped)
            if mapped:
                hit = self._entry_for_canon(mapped)
                if hit:
                    return hit
            key = stripped
        # 4) conservative long-prefix: alias startswith key+" " (anatomic qualifier)
        if len(key) >= 12:
            for alias in self._alias_keys_desc:
                if len(alias) < len(key):
                    break
                if alias == key or alias.startswith(key + " "):
                    hit = self._entry_for_canon(self._by_alias[alias])
                    if hit:
                        return hit
                if key.startswith(alias + " ") and len(alias) >= 12:
                    hit = self._entry_for_canon(self._by_alias[alias])
                    if hit:
                        return hit
        return None

    def _entry_chunk(self, label: str, role: str) -> Optional[dict[str, Any]]:
        entry = self._resolve(label)
        if not entry:
            return None
        canon = str(entry.get("canonical") or label)
        aliases = [str(a) for a in (entry.get("aliases") or [])][: self.max_aliases]
        ids = entry.get("ids") if isinstance(entry.get("ids"), Mapping) else {}
        umls = str((ids or {}).get("umls") or "")
        text = (
            "[%s] surface='%s'; canonical='%s'; aliases=%s; umls=%s. "
            "Use only for option↔leaf synonym / granularity (equivalent, "
            "subtype_of, supertype_of). Do not select the MCQ answer."
            % (role, label, canon, aliases, umls or "NA")
        )
        return {
            "id": "syn:%s:%s" % (role, _norm(canon)[:80]),
            "title": "synonym_bridge:%s" % canon,
            "content": text,
            "score": 1.0,
            "canonical": canon,
            "umls": umls,
        }

    def _lexical_pair_chunk(self, option_text: str, leaf_label: str) -> dict[str, Any]:
        ot, lt = _tokens(option_text), _tokens(leaf_label)
        stop = {"left", "right", "of", "the", "a", "an", "with", "and", "or", "in"}
        ot2, lt2 = ot - stop, lt - stop
        inter = ot2 & lt2
        union = ot2 | lt2
        jacc = (len(inter) / len(union)) if union else 0.0
        on, ln = _norm(option_text), _norm(leaf_label)
        if on and ln and (on in ln or ln in on):
            gran = "surface_containment_possible_granularity"
            score = max(0.7, jacc)
        elif jacc >= 0.5:
            gran = "high_token_overlap_possible_synonym"
            score = 0.65 + 0.2 * jacc
        elif jacc >= 0.3:
            gran = "moderate_token_overlap"
            score = 0.45
        else:
            gran = "low_token_overlap"
            score = 0.2
        text = (
            "Lexical pair (no trusted CUI link): option='%s' vs leaf='%s'. "
            "shared_tokens=%s; jaccard=%.2f; hint=%s. "
            "If clinical identity/granularity is defensible, prefer "
            "equivalent/subtype_of/supertype_of over unrelated. "
            "Do not select the MCQ answer."
            % (option_text, leaf_label, sorted(inter)[:8], jacc, gran)
        )
        return {
            "id": "lex:%s|%s" % (on[:40], ln[:40]),
            "title": "lexical_pair:%s" % gran,
            "content": text,
            "score": float(score),
        }

    def _pair_chunk(
        self,
        option_text: str,
        leaf_label: str,
        opt_entry: Mapping[str, Any],
        leaf_entry: Mapping[str, Any],
    ) -> dict[str, Any]:
        o_canon = str(opt_entry.get("canonical") or option_text)
        l_canon = str(leaf_entry.get("canonical") or leaf_label)
        o_ids = opt_entry.get("ids") if isinstance(opt_entry.get("ids"), Mapping) else {}
        l_ids = leaf_entry.get("ids") if isinstance(leaf_entry.get("ids"), Mapping) else {}
        o_umls = str((o_ids or {}).get("umls") or "")
        l_umls = str((l_ids or {}).get("umls") or "")
        same_cui = bool(o_umls and o_umls == l_umls)
        same_canon = _norm(o_canon) == _norm(l_canon)
        o_aliases = {_norm(a) for a in (opt_entry.get("aliases") or [])} | {_norm(o_canon)}
        l_aliases = {_norm(a) for a in (leaf_entry.get("aliases") or [])} | {_norm(l_canon)}
        overlap = sorted(o_aliases & l_aliases)
        on, ln = _norm(o_canon), _norm(l_canon)
        if same_cui or same_canon:
            gran = "likely_equivalent_or_synonym"
            score = 1.0
        elif on and ln and (on in ln or ln in on):
            gran = "possible_subtype_supertype_granularity"
            score = 0.85
        elif overlap:
            gran = "alias_overlap"
            score = 0.75
        else:
            gran = "distinct_bridge_entities"
            score = 0.35
        text = (
            "Pair option='%s' (canonical='%s', umls=%s) vs leaf='%s' "
            "(canonical='%s', umls=%s). shared_alias_norms=%s; "
            "granularity_hint=%s; same_umls=%s. "
            "If granularity_hint suggests synonym/subtype, prefer binding "
            "equivalent/subtype_of/supertype_of over unrelated. "
            "Do not choose which option is clinically correct."
            % (
                option_text,
                o_canon,
                o_umls or "NA",
                leaf_label,
                l_canon,
                l_umls or "NA",
                overlap[:6],
                gran,
                same_cui,
            )
        )
        return {
            "id": "pair:%s|%s" % (_norm(o_canon)[:40], _norm(l_canon)[:40]),
            "title": "granularity_pair:%s" % gran,
            "content": text,
            "score": score,
        }

    def pair_match_score(self, option_text: str, leaf_label: str) -> float:
        """Option↔leaf identity/granularity score only (excludes self-chunks).

        ``search_option_leaves`` also emits per-side synonym_bridge chunks with
        score=1.0 for RAG context. Bind-repair must **not** use those; callers
        that need a match score should use this method (or filter ``pair:`` /
        ``lex:`` hits).
        """
        opt_entry = self._resolve(option_text)
        leaf_entry = self._resolve(str(leaf_label))
        if opt_entry and leaf_entry:
            pair = self._pair_chunk(
                option_text, str(leaf_label), opt_entry, leaf_entry
            )
        else:
            pair = self._lexical_pair_chunk(option_text, str(leaf_label))
        return float(min(1.0, max(0.0, float(pair.get("score") or 0.0))))

    def search_option_leaves(
        self,
        option_text: str,
        candidate_labels: Sequence[str],
        *,
        top_k: int = 8,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Return RAG-oriented snippets for option↔leaf critic.

        Includes self-chunks (``syn:option`` / ``syn:leaf``, score=1.0 when the
        surface resolves) plus true pair chunks (``pair:`` / ``lex:``). For
        bind scoring use :meth:`pair_match_score`, not ``hits[0].score``.
        """
        hits: list[dict[str, Any]] = []
        opt_chunk = self._entry_chunk(option_text, "option")
        if opt_chunk and float(opt_chunk["score"]) >= score_threshold:
            hits.append(opt_chunk)
        opt_entry = self._resolve(option_text)
        for lab in candidate_labels:
            leaf_chunk = self._entry_chunk(str(lab), "leaf")
            if leaf_chunk and float(leaf_chunk["score"]) >= score_threshold:
                hits.append(leaf_chunk)
            leaf_entry = self._resolve(str(lab))
            if opt_entry and leaf_entry:
                pair = self._pair_chunk(option_text, str(lab), opt_entry, leaf_entry)
            else:
                pair = self._lexical_pair_chunk(option_text, str(lab))
            if float(pair["score"]) >= score_threshold:
                hits.append(pair)
        hits.sort(key=lambda h: (-float(h.get("score") or 0.0), str(h.get("id"))))
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for hit in hits:
            hid = str(hit.get("id") or "")
            if hid in seen:
                continue
            seen.add(hid)
            out.append(hit)
            if len(out) >= top_k:
                break
        return out

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        q = str(query or "")
        opt = ""
        labels: list[str] = []
        m = re.search(r"option '([^']*)'", q)
        if m:
            opt = m.group(1)
        m2 = re.search(r"diagnosis '([^']*)'", q)
        if m2:
            labels = [p.strip() for p in m2.group(1).split(" vs ") if p.strip()]
        if opt or labels:
            return self.search_option_leaves(
                opt, labels, top_k=top_k, score_threshold=score_threshold,
            )
        chunk = self._entry_chunk(q, "query")
        return [chunk] if chunk else []
