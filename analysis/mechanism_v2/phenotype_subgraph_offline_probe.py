#!/usr/bin/env python3
"""Offline target-centric phenotype-subgraph retrieval experiment.

This script makes no network or LLM calls.  It compares five deliberately
separated mechanisms on phenotype/syndrome target retrieval:

* the existing six Boolean regex proposal matchers (``rule_lookup``);
* lexical matching against only a target HPO/Mondo node;
* lexical matching against an automatically assembled phenotype ego-subgraph;
* dense matching between linked HPO atoms and a centroid of that ego-subgraph;
* optional local MedCPT Query-to-Article target matching.

The ego-subgraph is target-centric.  It is built from the card-supplied HPO anchor,
longest non-overlapping HPO phrase mentions in the node's definition/comment,
one-hop ``is_a`` neighbours, and exact target-label Mondo identity aliases.  It never
enumerates 2- or 3-finding combinations.  Definition mentions are emitted as
``unverified_text_mention`` edges: they are retrieval proposals, not clinical
entailment or evidence.

The HPO dense arm uses the repository's frozen all-MiniLM vectors and is not a
MedCPT result.  The MedCPT arm is included only when pinned local Query/Article
model directories and a compatible local interpreter are supplied; it cannot
silently fall back to a network download or another encoder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from importlib import metadata as package_metadata
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "PHENOTYPE_SUBGRAPH_OFFLINE_PROBE"
)
RULES = ROOT / "data" / "knowledge_raw" / "phenotype_lift_rules_v1.json"
CONTRASTS = ROOT / "analysis" / "mechanism_v2" / "phenotype_lift_contrast_cases.json"
STRESS = ROOT / "analysis" / "mechanism_v2" / "phenotype_subgraph_stress_cases.json"
NORMALIZED_CACHE = (
    ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "NORMALIZED_INPUT_PROBE"
    / "normalized_cache.json"
)
LEGACY_PROBE = ROOT / "analysis" / "mechanism_v2" / "phenotype_lift_offline_probe.py"
LEGACY_SUMMARY = (
    ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "PHENOTYPE_LIFT_OFFLINE_PROBE"
    / "summary.json"
)
FAILURE_AUDIT = (
    ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "PHENOTYPE_LIFT_FAILURE_AUDIT"
    / "audit.json"
)
MEDCPT_HELPER = (
    ROOT / "analysis" / "mechanism_v2" / "phenotype_subgraph_medcpt_encode.py"
)
HPO_OBO = ROOT / "data" / "knowledge_raw" / "hp.obo"
MONDO_OBO = ROOT / "data" / "knowledge_raw" / "mondo.obo"
HPO_META = ROOT / "data" / "knowledge_raw" / "hpo_embedding_metadata.json"
HPO_EMBEDDINGS = ROOT / "data" / "knowledge_raw" / "hpo_embeddings.npy"
LOINC2HPO_JSON = ROOT / "data" / "knowledge_raw" / "loinc2hpo_annotations.json"
LOINC2HPO_TSV = (
    ROOT
    / "data"
    / "knowledge_raw"
    / "phenotype_lift_sources"
    / "loinc2hpoAnnotation"
    / "loinc2hpo-annotations.tsv"
)

GENERIC_SINGLETONS = {
    "all",
    "abnormal",
    "abnormality",
    "acute",
    "adult",
    "body",
    "child",
    "clinical",
    "disease",
    "diffuse",
    "finding",
    "high",
    "increased",
    "low",
    "normal",
    "reduced",
    "severe",
    "syndrome",
}

MEDCPT_EXPECTED_PROVENANCE = {
    "query_model": {
        "git_commit": "d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc",
        "git_worktree_clean": True,
        "model_safetensors_sha256": (
            "19d78c0d5eaee2f81e6c47c5425bbadcc0c6af016cbb5da4a000d64e59d6e342"
        ),
        "config_sha256": (
            "3fea00b31d018d676d6b7e2f6cddcfe1abc69bcb88f5f09f51b848212e1671d1"
        ),
        "tokenizer_assets_sha256": {
            "added_tokens.json": "691a5ce0135045c12b8410af8d472ff8de864094df40ac9af418d6c644c7588d",
            "special_tokens_map.json": "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3",
            "tokenizer.json": "6e046044df8a2fcedb10607075dca187cae61d806c0d80a96c5b81017edc90c9",
            "tokenizer_config.json": "cabeefb4bbba68c42d40a56bfc1e73dd2e5dfb6e0ca90a66349519c375452d1e",
            "vocab.txt": "79489a52be45e6fa033521e8ce8e4f62aedc0a742ee2aa6fc04667e5b0b1454d",
        },
    },
    "article_model": {
        "git_commit": "d05a736da4bb84ee4057b7f7999485be6ed85465",
        "git_worktree_clean": True,
        "model_safetensors_sha256": (
            "a5d5ffe4d8666c1d0aa15f371b94fc3492ca8f927e5621abd4b3ee9fc845b0f3"
        ),
        "config_sha256": (
            "3fea00b31d018d676d6b7e2f6cddcfe1abc69bcb88f5f09f51b848212e1671d1"
        ),
        "tokenizer_assets_sha256": {
            "added_tokens.json": "691a5ce0135045c12b8410af8d472ff8de864094df40ac9af418d6c644c7588d",
            "special_tokens_map.json": "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3",
            "tokenizer.json": "6e046044df8a2fcedb10607075dca187cae61d806c0d80a96c5b81017edc90c9",
            "tokenizer_config.json": "cabeefb4bbba68c42d40a56bfc1e73dd2e5dfb6e0ca90a66349519c375452d1e",
            "vocab.txt": "79489a52be45e6fa033521e8ce8e4f62aedc0a742ee2aa6fc04667e5b0b1454d",
        },
    },
}
MEDCPT_EXPECTED_REPRESENTATION = {
    "query": "Query Encoder [CLS], max_length=64",
    "article": "Article Encoder [CLS], [title, body], max_length=512",
    "primary_similarity": "raw dot product",
    "cosine": "diagnostic only",
    "model_weights": "safetensors enforced",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _surface(text: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text).casefold()))


def _extract_quoted(line: str) -> str:
    match = re.search(r'"((?:[^"\\]|\\.)*)"', line)
    if not match:
        return ""
    return match.group(1).replace(r'\"', '"')


@dataclass
class OntologyTerm:
    term_id: str
    name: str = ""
    synonyms: list[str] = field(default_factory=list)
    definition: str = ""
    comment: str = ""
    parents: list[str] = field(default_factory=list)
    obsolete: bool = False


def parse_obo(path: Path, id_prefix: str) -> dict[str, OntologyTerm]:
    terms: dict[str, OntologyTerm] = {}
    current: OntologyTerm | None = None

    def commit() -> None:
        if current and current.term_id and not current.obsolete:
            terms[current.term_id] = current

    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line == "[Term]":
                commit()
                current = OntologyTerm("")
                continue
            if line.startswith("["):
                commit()
                current = None
                continue
            if current is None:
                continue
            if line.startswith(f"id: {id_prefix}"):
                current.term_id = line[4:].strip()
            elif line.startswith("name: "):
                current.name = line[6:].strip()
            elif line.startswith("synonym: "):
                value = _extract_quoted(line)
                if value:
                    current.synonyms.append(value)
            elif line.startswith("def: "):
                current.definition = _extract_quoted(line)
            elif line.startswith("comment: "):
                current.comment = line[9:].strip()
            elif line.startswith(f"is_a: {id_prefix}"):
                current.parents.append(line.split("is_a: ", 1)[1].split(" !", 1)[0].strip())
            elif line == "is_obsolete: true":
                current.obsolete = True
    commit()
    return terms


def _children(terms: Mapping[str, OntologyTerm]) -> dict[str, list[str]]:
    out: defaultdict[str, list[str]] = defaultdict(list)
    for term_id, term in terms.items():
        for parent in term.parents:
            out[parent].append(term_id)
    return {key: sorted(value) for key, value in out.items()}


def _unique_alias_index(terms: Mapping[str, OntologyTerm]) -> dict[str, str]:
    candidates: defaultdict[str, set[str]] = defaultdict(set)
    for term_id, term in terms.items():
        for text in (term.name, *term.synonyms):
            key = _surface(text)
            if key:
                candidates[key].add(term_id)
    return {
        alias: next(iter(ids))
        for alias, ids in candidates.items()
        if len(ids) == 1
    }


def definition_mentions(
    target_id: str,
    term: OntologyTerm,
    hpo_terms: Mapping[str, OntologyTerm],
    unique_aliases: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Extract longest non-overlapping HPO phrase mentions with source spans.

    These edges are intentionally *not* assigned a medical predicate.  A phrase
    in a definition can be a component, comparison, associated disease, or
    explicit negation.  The output status therefore remains
    ``unverified_text_mention``.
    """

    rows: list[dict[str, Any]] = []
    aliases = sorted(
        unique_aliases,
        key=lambda value: (-len(value.split()), -len(value), value),
    )
    for field_name, source_text in (
        ("definition", term.definition),
        ("comment", term.comment),
    ):
        normalized = _surface(source_text)
        occupied: list[tuple[int, int]] = []
        for alias in aliases:
            mention_id = unique_aliases[alias]
            if mention_id == target_id:
                continue
            if len(alias) < 5 or len(alias) > 80 or len(alias.split()) > 7:
                continue
            if len(alias.split()) == 1 and alias in GENERIC_SINGLETONS:
                continue
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")
            for match in pattern.finditer(normalized):
                span = match.span()
                if any(not (span[1] <= left or span[0] >= right) for left, right in occupied):
                    continue
                occupied.append(span)
                rows.append(
                    {
                        "source_field": field_name,
                        "normalized_span": [span[0], span[1]],
                        "mention_text": match.group(0),
                        "matched_alias": alias,
                        "hpo_id": mention_id,
                        "hpo_label": hpo_terms[mention_id].name,
                        "edge_status": "unverified_text_mention",
                    }
                )
    return sorted(
        rows,
        key=lambda row: (row["source_field"], row["normalized_span"], row["hpo_id"]),
    )


def _mondo_target_identity_matches(
    target_label: str, mondo_terms: Mapping[str, OntologyTerm]
) -> list[dict[str, Any]]:
    """Return Mondo rows whose name/synonym exactly names the requested target.

    The target's HPO anchor may intentionally be broader or narrower than the
    local target (for example HAGMA uses the metabolic-acidosis anchor).  Anchor
    names therefore must not be promoted to target identity.
    """
    wanted = {_surface(target_label)} if _surface(target_label) else set()
    rows: list[dict[str, Any]] = []
    for term_id, term in mondo_terms.items():
        aliases = [term.name, *term.synonyms]
        matched = sorted({alias for alias in aliases if _surface(alias) in wanted})
        if matched:
            rows.append(
                {
                    "mondo_id": term_id,
                    "name": term.name,
                    "matched_aliases": matched,
                    "definition": term.definition,
                }
            )
    return rows


def build_profiles() -> tuple[list[dict[str, Any]], dict[str, OntologyTerm]]:
    hpo_terms = parse_obo(HPO_OBO, "HP:")
    mondo_terms = parse_obo(MONDO_OBO, "MONDO:")
    children = _children(hpo_terms)
    unique_aliases = _unique_alias_index(hpo_terms)
    cards = _read_json(RULES)["rules"]
    profiles: list[dict[str, Any]] = []
    for order, card in enumerate(cards):
        target = card["target"]
        anchors = target.get("query_expansion_targets") or [target["id"]]
        hpo_anchors = [anchor for anchor in anchors if anchor.startswith("HP:")]
        if len(hpo_anchors) != 1 or hpo_anchors[0] not in hpo_terms:
            raise ValueError(f"target {card['rule_id']} lacks one resolvable HPO anchor")
        anchor = hpo_anchors[0]
        term = hpo_terms[anchor]
        mentions = definition_mentions(anchor, term, hpo_terms, unique_aliases)
        mention_ids = sorted({row["hpo_id"] for row in mentions})
        parent_ids = [item for item in term.parents if item in hpo_terms]
        child_ids = children.get(anchor, [])
        mondo = _mondo_target_identity_matches(target["label"], mondo_terms)

        node_parts = [target["label"], term.name, *term.synonyms, term.definition, term.comment]
        for row in mondo:
            node_parts.extend([row["name"], *row["matched_aliases"], row["definition"]])
        ego_parts = list(node_parts)
        for item in mention_ids:
            mention_term = hpo_terms[item]
            ego_parts.extend([mention_term.name, *mention_term.synonyms[:5]])
        for item in sorted(set(parent_ids + child_ids)):
            neighbour = hpo_terms[item]
            ego_parts.extend([neighbour.name, *neighbour.synonyms[:3]])
        target_surface = _surface(target["label"])
        medcpt_article_body_parts = [
            part for part in ego_parts if part and _surface(part) != target_surface
        ]

        profiles.append(
            {
                "order": order,
                "rule_id": card["rule_id"],
                "target_id": target["id"],
                "target_label": target["label"],
                "hpo_anchor": anchor,
                "hpo_name": term.name,
                "hpo_definition": term.definition,
                "hpo_comment": term.comment,
                "hpo_synonyms": term.synonyms,
                "definition_mentions": mentions,
                "definition_mention_ids": mention_ids,
                "is_a_parents": [
                    {"hpo_id": item, "label": hpo_terms[item].name} for item in parent_ids
                ],
                "is_a_children": [
                    {"hpo_id": item, "label": hpo_terms[item].name} for item in child_ids
                ],
                "mondo_target_identity_matches": mondo,
                "node_profile_text": " ".join(part for part in node_parts if part),
                "ego_profile_text": " ".join(part for part in ego_parts if part),
                "medcpt_article_body_text": " ".join(medcpt_article_body_parts),
                "dense_profile_hpo_ids": [anchor, *mention_ids],
                "edge_contract": (
                    "is_a retains ontology semantics; only exact target-label Mondo aliases "
                    "retain identity (HPO-anchor names are not target identity); "
                    "definition_mentions remain unverified_text_mention/query-only"
                ),
            }
        )
    return profiles, hpo_terms


class LexicalScorer:
    def __init__(self, profiles: Sequence[dict[str, Any]], field_name: str) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = [str(profile[field_name]) for profile in profiles]
        self.profiles = profiles
        self.word = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        self.char = TfidfVectorizer(
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
            sublinear_tf=True,
        )
        self.word_matrix = self.word.fit_transform(texts)
        self.char_matrix = self.char.fit_transform(texts)

    def score(self, texts: Sequence[str]) -> np.ndarray:
        word_scores = (self.word.transform(texts) @ self.word_matrix.T).toarray()
        char_scores = (self.char.transform(texts) @ self.char_matrix.T).toarray()
        return 0.5 * word_scores + 0.5 * char_scores


def _embedding_metadata_row_identity_valid(
    row: Mapping[str, Any], hpo_terms: Mapping[str, OntologyTerm]
) -> bool:
    term = hpo_terms.get(str(row.get("hpo_id", "")))
    text = row.get("text")
    if term is None or not text:
        return False
    allowed = {_surface(value) for value in (term.name, *term.synonyms) if value}
    return _surface(text) in allowed


class HpoDenseSubgraph:
    """Frozen node-vector matcher; no runtime text encoder is used."""

    def __init__(
        self,
        profiles: Sequence[dict[str, Any]],
        hpo_terms: Mapping[str, OntologyTerm],
    ) -> None:
        metadata = _read_json(HPO_META)
        embeddings = np.load(HPO_EMBEDDINGS, mmap_mode="r")
        if embeddings.shape[0] != len(metadata):
            raise ValueError("HPO metadata and embedding rows are not aligned")
        self.metadata = metadata
        self.embeddings = embeddings
        self.active_hpo_ids = frozenset(hpo_terms)
        self.raw_metadata_rows = len(metadata)
        self.active_id_metadata_rows = sum(
            row.get("hpo_id") in self.active_hpo_ids for row in metadata
        )
        self.identity_valid_metadata_rows = sum(
            _embedding_metadata_row_identity_valid(row, hpo_terms) for row in metadata
        )
        self.hpo_to_index: dict[str, int] = {}
        for index, row in enumerate(metadata):
            hpo_id = row.get("hpo_id")
            if (
                _embedding_metadata_row_identity_valid(row, hpo_terms)
                and not row.get("is_synonym")
                and hpo_id not in self.hpo_to_index
            ):
                self.hpo_to_index[hpo_id] = index
        for index, row in enumerate(metadata):
            hpo_id = row.get("hpo_id")
            if (
                _embedding_metadata_row_identity_valid(row, hpo_terms)
                and hpo_id not in self.hpo_to_index
            ):
                self.hpo_to_index[hpo_id] = index

        target_vectors: list[np.ndarray] = []
        self.target_vector_ids: list[list[str]] = []
        for profile in profiles:
            ids = [item for item in profile["dense_profile_hpo_ids"] if item in self.hpo_to_index]
            if not ids:
                raise ValueError(f"no dense vectors for {profile['rule_id']}")
            vector = np.asarray(
                [embeddings[self.hpo_to_index[item]] for item in ids], dtype=np.float32
            ).mean(axis=0)
            norm = float(np.linalg.norm(vector))
            target_vectors.append(vector / norm)
            self.target_vector_ids.append(ids)
        self.target_vectors = np.asarray(target_vectors, dtype=np.float32)

    def score_ids(self, id_rows: Sequence[Sequence[str]]) -> np.ndarray:
        scores = np.full((len(id_rows), len(self.target_vectors)), -1.0, dtype=np.float32)
        for row_index, ids in enumerate(id_rows):
            valid = sorted({item for item in ids if item in self.hpo_to_index})
            if not valid:
                continue
            vector = np.asarray(
                [self.embeddings[self.hpo_to_index[item]] for item in valid],
                dtype=np.float32,
            ).mean(axis=0)
            norm = float(np.linalg.norm(vector))
            if norm:
                scores[row_index] = (vector / norm) @ self.target_vectors.T
        return scores


class RawHpoLinker:
    """Char-TF-IDF proposal linker used only to feed the frozen dense arm."""

    def __init__(self, hpo_terms: Mapping[str, OntologyTerm]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        metadata = _read_json(HPO_META)
        self.active_hpo_ids = frozenset(hpo_terms)
        self.raw_metadata_rows = len(metadata)
        self.raw_unique_hpo_ids = len(
            {row.get("hpo_id") for row in metadata if row.get("hpo_id")}
        )
        self.labels: list[str] = []
        self.ids: list[str] = []
        self.active_id_metadata_rows = sum(
            row.get("hpo_id") in self.active_hpo_ids for row in metadata
        )
        for row in metadata:
            if row.get("text") and _embedding_metadata_row_identity_valid(
                row, hpo_terms
            ):
                self.labels.append(row["text"])
                self.ids.append(row["hpo_id"])
        self.identity_valid_metadata_rows = len(self.labels)
        self.excluded_inactive_or_unknown_metadata_rows = (
            self.raw_metadata_rows - self.active_id_metadata_rows
        )
        self.excluded_label_mismatch_metadata_rows = (
            self.active_id_metadata_rows - self.identity_valid_metadata_rows
        )
        self.active_unique_hpo_ids = len(set(self.ids))
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 4),
            lowercase=True,
            min_df=1,
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform(self.labels)

    @staticmethod
    def _segments(text: str) -> list[str]:
        return [
            item.strip()
            for item in re.split(r"[.;,:]|\b(?:and|with|but)\b", text, flags=re.IGNORECASE)
            if len(_surface(item)) >= 4
        ]

    def link_many(
        self, texts: Sequence[str], threshold: float = 0.45, min_margin: float = 0.02
    ) -> tuple[list[list[str]], list[list[dict[str, Any]]]]:
        segments: list[str] = []
        owners: list[int] = []
        for owner, text in enumerate(texts):
            for segment in self._segments(text):
                owners.append(owner)
                segments.append(segment)
        ids_out: list[list[str]] = [[] for _ in texts]
        rows_out: list[list[dict[str, Any]]] = [[] for _ in texts]
        if not segments:
            return ids_out, rows_out
        queries = self.vectorizer.transform(segments)
        dense_scores = (self.matrix @ queries.T).toarray()
        for column, (owner, segment) in enumerate(zip(owners, segments)):
            scores = dense_scores[:, column]
            if len(scores) < 2:
                continue
            top_two = np.argpartition(scores, -2)[-2:]
            top_two = top_two[np.argsort(scores[top_two])[::-1]]
            first, second = map(int, top_two)
            score = float(scores[first])
            margin = score - float(scores[second])
            if score < threshold or margin < min_margin:
                continue
            hpo_id = self.ids[first]
            row = {
                "segment": segment,
                "hpo_id": hpo_id,
                "matched_label": self.labels[first],
                "score": round(score, 6),
                "margin": round(margin, 6),
                "status": "lexical_proposal_without_assertion_or_numeric_validation",
            }
            rows_out[owner].append(row)
            if hpo_id not in ids_out[owner]:
                ids_out[owner].append(hpo_id)
        return ids_out, rows_out


def _load_legacy_module() -> Any:
    spec = importlib.util.spec_from_file_location("phenotype_lift_offline_probe", LEGACY_PROBE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import existing phenotype probe")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_cached_hpo_mapping(
    item: Mapping[str, Any],
    normalized: Mapping[str, Any],
    hpo_terms: Mapping[str, OntologyTerm],
) -> tuple[str | None, dict[str, Any] | None]:
    hpo_id = normalized.get("hpo_id")
    if not hpo_id:
        return None, None
    stored_label = normalized.get("hpo_term")
    term = hpo_terms.get(hpo_id)
    base = {
        "item_id": item.get("id"),
        "item_text": item.get("text"),
        "hpo_id": hpo_id,
        "stored_hpo_term": stored_label,
    }
    if term is None:
        return None, {**base, "reason": "inactive_or_unknown_hpo_id"}
    allowed_surfaces = {
        _surface(value) for value in (term.name, *term.synonyms) if value
    }
    if stored_label and _surface(stored_label) not in allowed_surfaces:
        return None, {
            **base,
            "current_hpo_name": term.name,
            "reason": "stored_label_current_ontology_mismatch",
        }
    return hpo_id, None


def load_eval_cases(
    hpo_terms: Mapping[str, OntologyTerm],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in _read_json(CONTRASTS)["cases"]:
        suite = row.get("suite", "unit_smoke")
        if suite == "unit_smoke":
            cohort = "unit_positive" if row["expected_trigger"] else "unit_negative_calibration"
        else:
            cohort = "adversarial_negative"
        cases.append(
            {
                **row,
                "source": "existing_contrast",
                "cohort": cohort,
                "gold_basis": "existing frozen contrast label",
                "atom_ids": [],
            }
        )
    for row in _read_json(STRESS)["cases"]:
        cases.append(
            {
                **row,
                "source": "surface_stress",
                "cohort": "surface_stress_positive",
                "gold_basis": "manual surface perturbation of an existing positive contrast",
                "atom_ids": [],
            }
        )

    cache = _read_json(NORMALIZED_CACHE)
    parsed_specs = (
        ("mcr_v1/2", "PLV1_HAGMA"),
        ("mcr_v1/82", "PLV1_HAGMA"),
    )
    for case_key, target in parsed_specs:
        row = cache["cases"][case_key]
        atom_ids: list[str] = []
        input_atom_ids: list[str] = []
        normalized_rows: list[dict[str, Any]] = []
        excluded_mappings: list[dict[str, Any]] = []
        for item in row["items"]:
            for normalized in item.get("normalized", []):
                hpo_id = normalized.get("hpo_id")
                if hpo_id and hpo_id not in input_atom_ids:
                    input_atom_ids.append(hpo_id)
                validated_id, issue = _validate_cached_hpo_mapping(
                    item, normalized, hpo_terms
                )
                if issue:
                    excluded_mappings.append(issue)
                if validated_id and validated_id not in atom_ids:
                    atom_ids.append(validated_id)
                if validated_id:
                    normalized_rows.append(
                        {
                            "item_id": item["id"],
                            "text": item["text"],
                            "hpo_id": hpo_id,
                            "hpo_term": normalized.get("hpo_term"),
                            "direction": normalized.get("direction"),
                        }
                    )
        cases.append(
            {
                "id": f"parsed_{case_key.replace('/', '_')}",
                "rule_id": target,
                "text": ". ".join(item["text"] for item in row["items"]),
                "expected_trigger": True,
                "source": "normalized_cache",
                "cohort": "parsed_positive_exploratory",
                "gold_basis": (
                    "existing query-only HAGMA rule event; not independent clinical gold"
                ),
                "case_key": case_key,
                "atom_ids": atom_ids,
                "input_atom_ids": input_atom_ids,
                "normalized_atoms": normalized_rows,
                "excluded_hpo_mappings": excluded_mappings,
            }
        )
    return cases, cache


def _rule_scores(
    module: Any, texts: Sequence[str], profiles: Sequence[dict[str, Any]]
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    scores = np.zeros((len(texts), len(profiles)), dtype=np.float32)
    details: list[dict[str, Any]] = []
    for row_index, text in enumerate(texts):
        row_details: dict[str, Any] = {}
        for column, profile in enumerate(profiles):
            triggered, matcher_details = module.MATCHERS[profile["rule_id"]](text)
            scores[row_index, column] = 1.0 if triggered else 0.0
            if triggered:
                row_details[profile["rule_id"]] = matcher_details
        details.append(row_details)
    return scores, details


def _rank_row(scores: Sequence[float], profiles: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    order = sorted(
        range(len(scores)),
        key=lambda index: (-float(scores[index]), int(profiles[index]["order"])),
    )
    return [
        {
            "rank": rank,
            "rule_id": profiles[index]["rule_id"],
            "target_label": profiles[index]["target_label"],
            "score": round(float(scores[index]), 8),
        }
        for rank, index in enumerate(order, 1)
    ]


def _thresholds(
    cases: Sequence[dict[str, Any]], score_matrices: Mapping[str, np.ndarray]
) -> dict[str, dict[str, Any]]:
    calibration = [
        index for index, case in enumerate(cases) if case["cohort"] == "unit_negative_calibration"
    ]
    out: dict[str, dict[str, Any]] = {}
    for arm, matrix in score_matrices.items():
        if arm == "rule_lookup":
            threshold = 0.5
            rule = "fixed Boolean trigger threshold"
        else:
            negative_max = max(float(np.max(matrix[index])) for index in calibration)
            threshold = negative_max + 1e-9
            rule = (
                "max top score over six unit-smoke negatives plus 1e-9; "
                "abstention-first calibration, no positive labels used"
            )
        out[arm] = {
            "threshold": threshold,
            "calibration_n_negative": len(calibration),
            "rule": rule,
        }
    return out


def _metrics(
    rows: Sequence[dict[str, Any]], cohorts: Sequence[str], arms: Sequence[str]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cohort in cohorts:
        subset = [row for row in rows if row["cohort"] == cohort]
        if not subset:
            continue
        cohort_result: dict[str, Any] = {"n": len(subset)}
        for arm in arms:
            positive = [row for row in subset if row["expected_trigger"]]
            negative = [row for row in subset if not row["expected_trigger"]]
            result: dict[str, Any] = {
                "n_positive": len(positive),
                "n_negative": len(negative),
                "n_proposed": sum(row["arms"][arm]["prediction"] is not None for row in subset),
                "n_abstained": sum(row["arms"][arm]["prediction"] is None for row in subset),
            }
            if positive:
                result.update(
                    {
                        "target_top1_rank_only": sum(
                            row["arms"][arm]["raw_top1"] == row["rule_id"] for row in positive
                        ),
                        "target_recall_at_3_rank_only": sum(
                            row["arms"][arm]["target_rank"] is not None
                            and row["arms"][arm]["target_rank"] <= 3
                            for row in positive
                        ),
                        "correct_after_abstention": sum(
                            row["arms"][arm]["prediction"] == row["rule_id"] for row in positive
                        ),
                        "wrong_target_after_abstention": sum(
                            row["arms"][arm]["prediction"] not in {None, row["rule_id"]}
                            for row in positive
                        ),
                    }
                )
            if negative:
                false_positives = sum(
                    row["arms"][arm]["prediction"] is not None for row in negative
                )
                result.update(
                    {
                        "absent_assigned_target_top1_rank_only": sum(
                            row["arms"][arm]["raw_top1"] == row["rule_id"]
                            for row in negative
                        ),
                        "false_positives": false_positives,
                        "false_positive_rate": round(false_positives / len(negative), 6),
                        "abstention_rate": round(1.0 - false_positives / len(negative), 6),
                    }
                )
            cohort_result[arm] = result
        out[cohort] = cohort_result
    return out


def _paired_target_separation(
    cases: Sequence[dict[str, Any]],
    profiles: Sequence[dict[str, Any]],
    matrices: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    positive_by_target = {
        case["rule_id"]: index
        for index, case in enumerate(cases)
        if case["cohort"] == "unit_positive"
    }
    negative_by_target = {
        case["rule_id"]: index
        for index, case in enumerate(cases)
        if case["cohort"] == "unit_negative_calibration"
    }
    profile_index = {profile["rule_id"]: index for index, profile in enumerate(profiles)}
    target_ids = sorted(set(positive_by_target) & set(negative_by_target))
    out: dict[str, Any] = {}
    for arm, matrix in matrices.items():
        rows: list[dict[str, Any]] = []
        for target in target_ids:
            column = profile_index[target]
            positive_score = float(matrix[positive_by_target[target], column])
            negative_score = float(matrix[negative_by_target[target], column])
            rows.append(
                {
                    "rule_id": target,
                    "positive_score": round(positive_score, 8),
                    "matched_negative_score": round(negative_score, 8),
                    "positive_minus_negative": round(positive_score - negative_score, 8),
                    "positive_higher": positive_score > negative_score,
                }
            )
        out[arm] = {
            "n_pairs": len(rows),
            "n_positive_higher": sum(row["positive_higher"] for row in rows),
            "rows": rows,
            "interpretation": (
                "Same-target positive versus matched unit negative. A non-positive margin "
                "means target semantic score alone cannot separate presence from the "
                "frozen counterexample."
            ),
        }
    return out


def _broad_cache_rows(
    cache: Mapping[str, Any], hpo_terms: Mapping[str, OntologyTerm]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_key, case in sorted(cache["cases"].items()):
        input_atom_ids: list[str] = []
        atom_ids: list[str] = []
        excluded_mappings: list[dict[str, Any]] = []
        input_mapping_events = 0
        valid_mapping_events = 0
        for item in case["items"]:
            for normalized in item.get("normalized", []):
                hpo_id = normalized.get("hpo_id")
                if hpo_id and hpo_id not in input_atom_ids:
                    input_atom_ids.append(hpo_id)
                if not hpo_id:
                    continue
                input_mapping_events += 1
                validated_id, issue = _validate_cached_hpo_mapping(
                    item, normalized, hpo_terms
                )
                if issue:
                    excluded_mappings.append(issue)
                    continue
                valid_mapping_events += 1
                if validated_id and validated_id not in atom_ids:
                    atom_ids.append(validated_id)
        excluded_atom_ids = sorted(
            {
                row["hpo_id"]
                for row in excluded_mappings
                if row["reason"] == "inactive_or_unknown_hpo_id"
            }
        )
        excluded_label_mismatch_ids = sorted(
            {
                row["hpo_id"]
                for row in excluded_mappings
                if row["reason"] == "stored_label_current_ontology_mismatch"
            }
        )
        rows.append(
            {
                "case_key": case_key,
                "text": ". ".join(item["text"] for item in case["items"]),
                "atom_ids": atom_ids,
                "input_atom_ids": input_atom_ids,
                "n_input_hpo_mapping_events": input_mapping_events,
                "n_valid_hpo_mapping_events": valid_mapping_events,
                "excluded_inactive_or_unknown_hpo_ids": excluded_atom_ids,
                "excluded_label_mismatch_hpo_ids": excluded_label_mismatch_ids,
                "excluded_hpo_mappings": excluded_mappings,
            }
        )
    return rows


def _proposal_summary(
    rows: Sequence[dict[str, Any]],
    profiles: Sequence[dict[str, Any]],
    matrices: Mapping[str, np.ndarray],
    thresholds: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    detailed: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"n_cases": len(rows), "arms": {}}
    for row_index, row in enumerate(rows):
        arm_rows: dict[str, Any] = {}
        for arm, matrix in matrices.items():
            ranking = _rank_row(matrix[row_index], profiles)
            top = ranking[0]
            threshold = float(thresholds[arm]["threshold"])
            raw_top_score = float(np.max(matrix[row_index]))
            prediction = top["rule_id"] if raw_top_score >= threshold else None
            raw_top1 = top["rule_id"]
            if arm == "rule_lookup" and raw_top_score == 0:
                raw_top1 = None
            arm_rows[arm] = {
                "raw_top1": raw_top1,
                "top_score": round(raw_top_score, 8),
                "prediction": prediction,
            }
        detailed.append(
            {
                "case_key": row["case_key"],
                "n_hpo_atoms": len(row["atom_ids"]),
                "n_input_hpo_atoms": len(row.get("input_atom_ids", row["atom_ids"])),
                "n_input_hpo_mapping_events": row.get(
                    "n_input_hpo_mapping_events", len(row["atom_ids"])
                ),
                "n_valid_hpo_mapping_events": row.get(
                    "n_valid_hpo_mapping_events", len(row["atom_ids"])
                ),
                "excluded_inactive_or_unknown_hpo_ids": row.get(
                    "excluded_inactive_or_unknown_hpo_ids", []
                ),
                "excluded_label_mismatch_hpo_ids": row.get(
                    "excluded_label_mismatch_hpo_ids", []
                ),
                "excluded_hpo_mappings": row.get("excluded_hpo_mappings", []),
                "arms": arm_rows,
            }
        )
    for arm in matrices:
        proposed = [row["arms"][arm]["prediction"] for row in detailed]
        top_scores = sorted(row["arms"][arm]["top_score"] for row in detailed)
        summary["arms"][arm] = {
            "n_proposed": sum(value is not None for value in proposed),
            "proposal_rate": round(sum(value is not None for value in proposed) / len(rows), 6),
            "prediction_counts": dict(Counter(value for value in proposed if value is not None)),
            "top_score_quantiles": {
                "p50": top_scores[len(top_scores) // 2],
                "p90": top_scores[math.ceil(0.9 * len(top_scores)) - 1],
                "p99": top_scores[math.ceil(0.99 * len(top_scores)) - 1],
            },
        }
    summary["warning"] = (
        "The 200-case normalized cache has no phenotype/syndrome target gold. "
        "Proposal counts are an abstention/load screen, not precision or false-positive rates."
    )
    return summary, detailed


def _is_lfs_pointer(path: Path) -> bool:
    if not path.exists() or path.stat().st_size > 1024:
        return False
    return path.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1")


def run_medcpt(
    cases: Sequence[dict[str, Any]],
    profiles: Sequence[dict[str, Any]],
    python_path: Path | None,
    query_model: Path | None,
    article_model: Path | None,
) -> tuple[np.ndarray | None, dict[str, Any] | None, str | None]:
    if not python_path or not query_model or not article_model:
        return None, None, "one or more MedCPT runtime paths were not supplied"
    if not python_path.is_file():
        return None, None, f"MedCPT interpreter not found: {python_path}"
    if not query_model.is_dir() or not article_model.is_dir():
        return None, None, "one or both local MedCPT model directories are absent"
    payload = {
        "queries": [{"id": case["id"], "text": case["text"]} for case in cases],
        "targets": [
            {
                "id": profile["rule_id"],
                "title": profile["target_label"],
                "text": profile["medcpt_article_body_text"],
            }
            for profile in profiles
        ],
    }
    with tempfile.TemporaryDirectory(prefix="phenotype_medcpt_") as temp_dir:
        input_path = Path(temp_dir) / "input.json"
        output_path = Path(temp_dir) / "output.json"
        _write_json(input_path, payload)
        command = [
            str(python_path),
            str(MEDCPT_HELPER),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--query-model",
            str(query_model),
            "--article-model",
            str(article_model),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout).strip()
            return None, None, f"MedCPT helper exit {completed.returncode}: {error[-2000:]}"
        result = _read_json(output_path)
    matrix = np.asarray(result["dot_scores"], dtype=np.float32)
    if matrix.shape != (len(cases), len(profiles)):
        return None, None, f"unexpected MedCPT score shape: {matrix.shape}"
    return matrix, result, None


def _enforce_medcpt_contract(
    matrix: np.ndarray | None,
    execution: Mapping[str, Any] | None,
    error: str | None,
    require_medcpt: bool,
) -> None:
    if not require_medcpt:
        return
    if matrix is None:
        raise RuntimeError(
            "canonical phenotype-subgraph output requires the pinned local MedCPT "
            f"arm; refusing to overwrite results without it: {error}"
        )
    if execution is None:
        raise RuntimeError(
            "canonical phenotype-subgraph output requires MedCPT execution "
            "provenance; refusing to overwrite results without it"
        )
    mismatches: list[str] = []
    provenance = execution.get("provenance", {})
    for model_role, expected_fields in MEDCPT_EXPECTED_PROVENANCE.items():
        observed_fields = provenance.get(model_role, {})
        for field_name, expected_value in expected_fields.items():
            observed_value = observed_fields.get(field_name)
            if observed_value != expected_value:
                mismatches.append(
                    f"{model_role}.{field_name}={observed_value!r} "
                    f"(expected {expected_value!r})"
                )
    representation = execution.get("official_representation_contract")
    if representation != MEDCPT_EXPECTED_REPRESENTATION:
        mismatches.append("official_representation_contract differs from frozen contract")
    if mismatches:
        raise RuntimeError(
            "canonical MedCPT provenance mismatch; refusing to overwrite results: "
            + "; ".join(mismatches)
        )


def audit_medcpt(
    execution: Mapping[str, Any] | None = None,
    execution_error: str | None = None,
) -> dict[str, Any]:
    dense_dir = ROOT / "data" / "corpus" / "cpg_medcpt_index"
    index_file = dense_dir / "index.faiss"
    embedding_file = dense_dir / "embeddings.npy"
    model_candidates = [
        ROOT / "models" / "MedCPT-Query-Encoder",
        Path("/tmp/MedCPT-Query-Encoder"),
        Path("/workspace/MedCPT-Query-Encoder"),
    ]
    model_path = next((path for path in model_candidates if path.is_dir()), None)
    prior: dict[str, Any] | None = None
    if LEGACY_SUMMARY.exists():
        old = _read_json(LEGACY_SUMMARY).get("cpg_retrieval", {})
        prior = {
            "provenance": str(LEGACY_SUMMARY.relative_to(ROOT)),
            "summary_sha256": _sha256(LEGACY_SUMMARY),
            "dense_available_then": old.get("dense_available"),
            "medcpt_query_encoder_commit": old.get("medcpt_query_encoder_commit"),
            "medcpt_query_encoder_sha256": old.get("medcpt_query_encoder_sha256"),
            "n_queries": len(old.get("rows", [])),
            "open_first_relevant_rank_at_10": {
                row.get("kind"): row.get("arms", {}).get("medcpt_open", {}).get(
                    "first_relevant_rank_at_10"
                )
                for row in old.get("rows", [])
            },
            "reuse_contract": (
                "historical five-query downstream CPG smoke only; not recomputed and "
                "not entered into the target-level arm comparison"
            ),
        }
    executed = execution is not None
    return {
        "executed_in_this_probe": executed,
        "reason": None if executed else (
            execution_error
            or "MedCPT query encoder/runtime was not supplied; no score matrix was produced"
        ),
        "execution": execution,
        "query_encoder_found": str(model_path) if model_path else None,
        "index_exists": index_file.exists(),
        "index_is_lfs_pointer": _is_lfs_pointer(index_file),
        "embeddings_exists": embedding_file.exists(),
        "embeddings_is_lfs_pointer": _is_lfs_pointer(embedding_file),
        "historical_committed_smoke": prior,
        "hpo_dense_arm_is_medcpt": False,
        "target_dense_contract": (
            "raw vignette -> Query Encoder [CLS,64]; target ego-profile -> Article "
            "Encoder [CLS,512]; raw dot product; query-only"
            if executed
            else None
        ),
    }


def audit_loinc2hpo(
    profiles: Sequence[dict[str, Any]], hpo_terms: Mapping[str, OntologyTerm]
) -> dict[str, Any]:
    target_ids = {
        profile["hpo_anchor"] for profile in profiles
    } | {
        item for profile in profiles for item in profile["definition_mention_ids"]
    }
    with LOINC2HPO_TSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    relevant = [row for row in rows if row["hpoTermId"] in target_ids]
    invalid_rows = [row for row in rows if row["hpoTermId"] not in hpo_terms]
    local_json = _read_json(LOINC2HPO_JSON)
    local_mapping_rows: list[dict[str, Any]] = []
    for loinc_code, property_rows in local_json.items():
        for property_code, direction_rows in property_rows.items():
            for direction, mapping in direction_rows.items():
                if mapping:
                    local_mapping_rows.append(
                        {
                            "loinc_code": loinc_code,
                            "property": property_code,
                            "direction": direction,
                            **mapping,
                        }
                    )
    local_inactive = [
        row for row in local_mapping_rows if row["hpo_id"] not in hpo_terms
    ]
    local_label_mismatch: list[dict[str, Any]] = []
    for row in local_mapping_rows:
        term = hpo_terms.get(row["hpo_id"])
        if term is None:
            continue
        allowed = {_surface(value) for value in (term.name, *term.synonyms) if value}
        if _surface(row.get("hpo_term", "")) not in allowed:
            local_label_mismatch.append({**row, "current_hpo_name": term.name})
    return {
        "upstream_tsv_rows": len(rows),
        "upstream_relevant_rows": len(relevant),
        "upstream_relevant_hpo_ids": sorted({row["hpoTermId"] for row in relevant}),
        "upstream_inactive_or_unknown_hpo_rows": len(invalid_rows),
        "upstream_inactive_or_unknown_hpo_ids": sorted(
            {row["hpoTermId"] for row in invalid_rows}
        ),
        "identity_gate": (
            "Only IDs present and active in the frozen HPO release may route; stored "
            "labels must match the current name or synonym, and obsolete IDs are not "
            "automatically followed through replaced_by."
        ),
        "local_json_loinc_keys": len(local_json),
        "local_json_mapping_rows": len(local_mapping_rows),
        "local_json_inactive_or_unknown_mapping_events": len(local_inactive),
        "local_json_inactive_or_unknown_hpo_ids": sorted(
            {row["hpo_id"] for row in local_inactive}
        ),
        "local_json_stored_label_mismatch_events": len(local_label_mismatch),
        "local_json_stored_label_mismatch_hpo_ids": sorted(
            {row["hpo_id"] for row in local_label_mismatch}
        ),
        "local_json_quarantined_mapping_events": len(local_inactive)
        + len(local_label_mismatch),
        "local_json_mismatch_examples": local_label_mismatch[:10],
        "role": (
            "observation/result-category to atomic HPO routing only; it does not "
            "supply multi-finding syndrome entailment"
        ),
    }


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return None


def run(
    output: Path,
    medcpt_python: Path | None = None,
    medcpt_query_model: Path | None = None,
    medcpt_article_model: Path | None = None,
    require_medcpt: bool = True,
) -> dict[str, Any]:
    profiles, hpo_terms = build_profiles()
    cases, cache = load_eval_cases(hpo_terms)
    texts = [case["text"] for case in cases]
    legacy = _load_legacy_module()

    node_lexical = LexicalScorer(profiles, "node_profile_text")
    ego_lexical = LexicalScorer(profiles, "ego_profile_text")
    dense = HpoDenseSubgraph(profiles, hpo_terms)
    linker = RawHpoLinker(hpo_terms)

    raw_indices = [index for index, case in enumerate(cases) if not case["atom_ids"]]
    linked_ids, link_rows = linker.link_many([cases[index]["text"] for index in raw_indices])
    for local_index, case_index in enumerate(raw_indices):
        cases[case_index]["atom_ids"] = linked_ids[local_index]
        cases[case_index]["raw_hpo_links"] = link_rows[local_index]

    rule_matrix, rule_details = _rule_scores(legacy, texts, profiles)
    matrices: dict[str, np.ndarray] = {
        "rule_lookup": rule_matrix,
        "ontology_node_lexical": node_lexical.score(texts),
        "phenotype_ego_lexical": ego_lexical.score(texts),
        "hpo_dense_ego": dense.score_ids([case["atom_ids"] for case in cases]),
    }
    medcpt_matrix, medcpt_execution, medcpt_error = run_medcpt(
        cases,
        profiles,
        medcpt_python,
        medcpt_query_model,
        medcpt_article_model,
    )
    _enforce_medcpt_contract(
        medcpt_matrix, medcpt_execution, medcpt_error, require_medcpt
    )
    if medcpt_matrix is not None:
        matrices["medcpt_target_dense"] = medcpt_matrix
    thresholds = _thresholds(cases, matrices)

    case_rows: list[dict[str, Any]] = []
    for row_index, case in enumerate(cases):
        arm_rows: dict[str, Any] = {}
        for arm, matrix in matrices.items():
            ranking = _rank_row(matrix[row_index], profiles)
            top = ranking[0]
            threshold = float(thresholds[arm]["threshold"])
            raw_top_score = float(np.max(matrix[row_index]))
            prediction = top["rule_id"] if raw_top_score >= threshold else None
            raw_top1 = top["rule_id"]
            target_rank = next(
                (row["rank"] for row in ranking if row["rule_id"] == case["rule_id"]),
                None,
            )
            if arm == "rule_lookup" and matrix[row_index].max() == 0:
                target_rank = None
                raw_top1 = None
            arm_rows[arm] = {
                "raw_top1": raw_top1,
                "top_score": round(raw_top_score, 8),
                "target_rank": target_rank,
                "threshold": threshold,
                "prediction": prediction,
                "top3": ranking[:3],
            }
        case_rows.append(
            {
                "id": case["id"],
                "source": case["source"],
                "cohort": case["cohort"],
                "rule_id": case["rule_id"],
                "expected_trigger": case["expected_trigger"],
                "gold_basis": case["gold_basis"],
                "text": case["text"],
                "case_key": case.get("case_key"),
                "atom_ids": case["atom_ids"],
                "input_atom_ids": case.get("input_atom_ids", case["atom_ids"]),
                "raw_hpo_links": case.get("raw_hpo_links", []),
                "normalized_atoms": case.get("normalized_atoms", []),
                "excluded_hpo_mappings": case.get("excluded_hpo_mappings", []),
                "rule_trigger_details": rule_details[row_index],
                "arms": arm_rows,
            }
        )

    cohort_order = (
        "unit_positive",
        "unit_negative_calibration",
        "adversarial_negative",
        "surface_stress_positive",
        "parsed_positive_exploratory",
    )
    arm_ids = tuple(matrices)
    metrics = _metrics(case_rows, cohort_order, arm_ids)

    broad = _broad_cache_rows(cache, hpo_terms)
    broad_texts = [row["text"] for row in broad]
    broad_rule, _ = _rule_scores(legacy, broad_texts, profiles)
    broad_matrices = {
        "rule_lookup": broad_rule,
        "ontology_node_lexical": node_lexical.score(broad_texts),
        "phenotype_ego_lexical": ego_lexical.score(broad_texts),
        "hpo_dense_ego": dense.score_ids([row["atom_ids"] for row in broad]),
    }
    broad_summary, broad_rows = _proposal_summary(
        broad, profiles, broad_matrices, thresholds
    )
    affected_cache_rows = [row for row in broad if row["excluded_hpo_mappings"]]
    cache_total_mapping_events = sum(
        row["n_input_hpo_mapping_events"] for row in broad
    )
    cache_excluded_mapping_events = sum(
        len(row["excluded_hpo_mappings"]) for row in affected_cache_rows
    )
    broad_summary["active_hpo_filter"] = {
        "raw_embedding_metadata_rows": linker.raw_metadata_rows,
        "active_id_embedding_metadata_rows": linker.active_id_metadata_rows,
        "identity_valid_embedding_metadata_rows": linker.identity_valid_metadata_rows,
        "excluded_inactive_or_unknown_metadata_rows": (
            linker.excluded_inactive_or_unknown_metadata_rows
        ),
        "excluded_stored_label_mismatch_metadata_rows": (
            linker.excluded_label_mismatch_metadata_rows
        ),
        "raw_unique_hpo_ids": linker.raw_unique_hpo_ids,
        "active_unique_hpo_ids": linker.active_unique_hpo_ids,
        "cache_cases_with_quarantined_mappings": len(affected_cache_rows),
        "cache_total_hpo_mapping_events": cache_total_mapping_events,
        "cache_quarantined_unique_hpo_ids": sorted(
            {
                hpo_id
                for row in affected_cache_rows
                for hpo_id in (
                    row["excluded_inactive_or_unknown_hpo_ids"]
                    + row["excluded_label_mismatch_hpo_ids"]
                )
            }
        ),
        "cache_excluded_mapping_events": cache_excluded_mapping_events,
        "cache_strict_quarantine_rate": round(
            cache_excluded_mapping_events / cache_total_mapping_events, 6
        ),
        "cache_label_mismatch_events": sum(
            row["reason"] == "stored_label_current_ontology_mismatch"
            for cache_row in affected_cache_rows
            for row in cache_row["excluded_hpo_mappings"]
        ),
        "policy": (
            "Only current active HPO IDs with a stored label matching the current "
            "official name or synonym enter dense scoring; mismatches are quarantined "
            "and obsolete IDs are not auto-followed through replaced_by."
        ),
        "known_example": {
            "case_key": "mcr_v1/11",
            "bad_cache_mapping": "Procalcitonin 71.6 -> HP:0410049",
            "current_hpo_status": (
                "HP:0410049 is obsolete Abnormal radial ray morphology, replaced_by "
                "HP:0006433; it is filtered before dense scoring"
            ),
        },
    }
    broad_summary["excluded_arms"] = {
        "medcpt_target_dense": (
            "narrow target-level arm was executed on the 25 labeled/exploratory cases, "
            "including two parsed vignettes; it was not expanded to this unlabeled "
            "200-case load screen"
        )
    }

    mention_occurrence_count = sum(len(profile["definition_mentions"]) for profile in profiles)
    mention_unique_edge_count = sum(
        len(profile["definition_mention_ids"]) for profile in profiles
    )
    result = {
        "artifact": "PHENOTYPE_SUBGRAPH_OFFLINE_PROBE",
        "schema_version": "phenotype-subgraph-offline-probe.v1",
        "repository_head": _git_head(),
        "execution_contract": {
            "network_calls_during_probe_scoring": 0,
            "new_llm_calls": 0,
            "legacy_or_production_inputs_modified": 0,
            "canonical_result_files_written": 5,
            "main_runtime": {
                "python": sys.version.split()[0],
                "numpy": np.__version__,
                "scikit_learn": package_metadata.version("scikit-learn"),
            },
            "medcpt_required_for_canonical_output": require_medcpt,
            "missing_medcpt_policy": (
                "fail_closed" if require_medcpt else "explicit_noncanonical_output_only"
            ),
            "target_premise_fields_used_by_subgraph_arms": False,
            "subgraph_edge_write_policy": "query_only",
        },
        "question": (
            "Can target-centric fuzzy phenotype ego-subgraphs replace explicit "
            "symptom-to-phenotype rules for reverse retrieval without enumerating pairs/triples?"
        ),
        "arms": {
            "rule_lookup": (
                "existing six Boolean whole-vignette regex matchers; candidate blind but "
                "not assertion/identity complete"
            ),
            "ontology_node_lexical": (
                "word/char TF-IDF against the card-supplied HPO anchor "
                "definition/comment/synonyms (anchor scope may differ from target) plus "
                "exact target-label Mondo identity aliases; query-only"
            ),
            "phenotype_ego_lexical": (
                "node lexical profile plus unverified definition-mention nodes and "
                "one-hop is_a neighbour labels"
            ),
            "hpo_dense_ego": (
                "cosine between frozen HPO atom-vector mean and target anchor plus "
                "definition-mention-vector mean; all-MiniLM vectors, not MedCPT"
            ),
            **(
                {
                    "medcpt_target_dense": (
                        "raw vignette through pinned MedCPT Query Encoder and target "
                        "ego-profile through pinned Article Encoder; raw dot product; "
                        "query-only"
                    )
                }
                if medcpt_matrix is not None
                else {}
            ),
        },
        "thresholds": thresholds,
        "metrics": metrics,
        "paired_target_separation": _paired_target_separation(cases, profiles, matrices),
        "normalized_cache_proposal_screen": broad_summary,
        "substrate": {
            "hpo_terms": len(hpo_terms),
            "raw_embedding_metadata_rows": linker.raw_metadata_rows,
            "active_id_embedding_metadata_rows": linker.active_id_metadata_rows,
            "identity_valid_embedding_metadata_rows": (
                linker.identity_valid_metadata_rows
            ),
            "excluded_inactive_or_unknown_embedding_rows": (
                linker.excluded_inactive_or_unknown_metadata_rows
            ),
            "excluded_stored_label_mismatch_embedding_rows": (
                linker.excluded_label_mismatch_metadata_rows
            ),
            "raw_embedding_unique_hpo_ids": linker.raw_unique_hpo_ids,
            "active_embedding_unique_hpo_ids": linker.active_unique_hpo_ids,
            "targets": len(profiles),
            "definition_mention_occurrences": mention_occurrence_count,
            "definition_mention_unique_target_node_edges": mention_unique_edge_count,
            "pairs_or_triples_enumerated": 0,
            "runtime_shape": (
                "link m observed atoms once; retrieve target postings/profiles; no O(m^2) "
                "or O(m^3) symptom-combination materialization"
            ),
        },
        "loinc2hpo": audit_loinc2hpo(profiles, hpo_terms),
        "medcpt": audit_medcpt(medcpt_execution, medcpt_error),
        "known_input_limitations": {
            "normalized_cache": (
                "200 cases, 212 HPO-bearing items, known numeric/entity/direction errors; "
                "not phenotype gold"
            ),
            "contrast": (
                "six positive and eleven negative cases; tiny engineered set"
            ),
            "surface_stress": (
                "six manual paraphrases; robustness probe, not independent clinical gold"
            ),
            "parsed_positive": (
                "two HAGMA cases selected from existing rule events; exploratory only"
            ),
        },
    }

    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "summary.json", result)
    _write_json(output / "profile_catalog.json", profiles)
    with (output / "case_predictions.jsonl").open("w", encoding="utf-8") as handle:
        for row in case_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (output / "normalized_cache_predictions.jsonl").open("w", encoding="utf-8") as handle:
        for row in broad_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    inputs = [
        Path(__file__).resolve(),
        MEDCPT_HELPER,
        RULES,
        CONTRASTS,
        STRESS,
        NORMALIZED_CACHE,
        LEGACY_PROBE,
        LEGACY_SUMMARY,
        FAILURE_AUDIT,
        HPO_OBO,
        MONDO_OBO,
        HPO_META,
        HPO_EMBEDDINGS,
        LOINC2HPO_JSON,
        LOINC2HPO_TSV,
    ]
    manifest = {
        "repository_head": result["repository_head"],
        "inputs": {
            str(path.relative_to(ROOT)): {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in inputs
        },
        "outputs": {
            name: {
                "bytes": (output / name).stat().st_size,
                "sha256": _sha256(output / name),
            }
            for name in (
                "summary.json",
                "profile_catalog.json",
                "case_predictions.jsonl",
                "normalized_cache_predictions.jsonl",
            )
        },
    }
    _write_json(output / "input_manifest.json", manifest)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--medcpt-python",
        type=Path,
        default=Path("/tmp/phenotype-medcpt-venv/bin/python"),
        help="Pinned local interpreter with torch/transformers; set to a missing path to skip.",
    )
    parser.add_argument(
        "--medcpt-query-model",
        type=Path,
        default=Path("/tmp/MedCPT-Query-Encoder"),
    )
    parser.add_argument(
        "--medcpt-article-model",
        type=Path,
        default=Path("/tmp/MedCPT-Article-Encoder"),
    )
    parser.add_argument(
        "--allow-missing-medcpt",
        action="store_true",
        help=(
            "Permit a reduced noncanonical run without MedCPT. This requires an "
            "explicit --output different from the committed canonical result path."
        ),
    )
    args = parser.parse_args()
    if args.allow_missing_medcpt and args.output.resolve() == DEFAULT_OUT.resolve():
        parser.error(
            "--allow-missing-medcpt requires a noncanonical --output; refusing to "
            "overwrite the committed full-arm result directory"
        )
    result = run(
        args.output,
        medcpt_python=args.medcpt_python,
        medcpt_query_model=args.medcpt_query_model,
        medcpt_article_model=args.medcpt_article_model,
        require_medcpt=not args.allow_missing_medcpt,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "targets": result["substrate"]["targets"],
                "definition_mention_occurrences": result["substrate"][
                    "definition_mention_occurrences"
                ],
                "medcpt_executed": result["medcpt"]["executed_in_this_probe"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
