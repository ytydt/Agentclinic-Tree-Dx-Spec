"""Gold-blind, relation-aware projection from ranked L2 leaves to MCQ options.

This module is intentionally independent from the production ``AnswerMapper``.
It is used only by the frozen A / ALL_B_b1 offline evaluation harness.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from .knowledge.disease_name_resolver import DiseaseNameResolver, _normalize_label


QUESTION_TARGETS = frozenset({
    "diagnosis", "etiology_pathogen", "mechanism", "finding", "treatment",
    "prognosis", "other",
})
RELATION_TYPES = frozenset({
    "equivalent", "subtype_of", "supertype_of", "etiology_of",
    "mechanism_of", "manifestation_of", "complication_of", "treatment_for",
    "unrelated", "unknown",
})
MATCH_RELATIONS = RELATION_TYPES - {"unrelated", "unknown"}
FORBIDDEN_PAYLOAD_KEYS = frozenset({
    "gold", "gold_diagnosis", "gold_option", "gold_letter", "acceptable_l2",
    "is_gold", "evaluation_alias",
})
CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})
_WORD_RE = re.compile(r"[a-z0-9]+")
_ABBREVIATIONS = {
    "aml": "acute myeloid leukemia",
    "cml": "chronic myeloid leukemia",
    "all": "acute lymphoblastic leukemia",
    "cll": "chronic lymphocytic leukemia",
    "pcd": "primary ciliary dyskinesia",
    "nms": "neuroleptic malignant syndrome",
}


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assert_gold_blind(payload: Any, path: str = "payload") -> None:
    """Reject evaluation labels anywhere in a runtime mapper payload."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            if key_text.lower() in FORBIDDEN_PAYLOAD_KEYS:
                raise AssertionError(
                    "gold-bearing mapper payload key at %s.%s" % (path, key_text)
                )
            assert_gold_blind(value, "%s.%s" % (path, key_text))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_gold_blind(value, "%s[%d]" % (path, index))


def load_offline_resolver(root: str | Path) -> DiseaseNameResolver:
    """Load the exact resolver assets frozen by the offline protocol."""
    root_path = Path(root)
    knowledge = root_path / "data" / "knowledge_raw"
    resolver = DiseaseNameResolver()
    mechanism = knowledge / "mechanism_to_disease.json"
    bridge = knowledge / "disease_name_bridge.json"
    doclogica = knowledge / "doclogica_cache.json"
    if mechanism.exists():
        resolver.load_mechanism_map(mechanism)
    if bridge.exists():
        resolver.load_bridge(bridge)
    if doclogica.exists():
        resolver.load_umls_from_doclogica(doclogica)
    return resolver


def infer_question_target(question: str) -> str:
    text = " ".join(str(question or "").lower().split())
    if any(token in text for token in (
        "treatment", "management", "therapy", "drug", "next step",
    )):
        return "treatment"
    if any(token in text for token in (
        "organism", "pathogen", "etiology", "cause", "causative",
    )):
        return "etiology_pathogen"
    if any(token in text for token in (
        "mechanism", "pathophysiology", "mutation", "defect",
    )):
        return "mechanism"
    if any(token in text for token in (
        "finding", "manifestation", "associated", "feature", "sign",
    )):
        return "finding"
    if any(token in text for token in ("prognosis", "survival", "outcome")):
        return "prognosis"
    if any(token in text for token in (
        "diagnosis", "condition", "disease", "most likely", "explanation",
    )):
        return "diagnosis"
    return "other"


def _tokens(value: str) -> set[str]:
    return set(_WORD_RE.findall(str(value).lower()))


def _surface_forms(value: str, resolver: DiseaseNameResolver) -> set[str]:
    normalized = _normalize_label(value)
    forms = {normalized, resolver.canonicalize_entity(value)}
    raw_tokens = _tokens(value)
    for token in raw_tokens:
        expanded = _ABBREVIATIONS.get(token)
        if expanded:
            forms.add(expanded)
    return {form for form in forms if form}


def leaf_rows_from_tree(
    tree: Mapping[str, Any], ranking: Sequence[str] = (),
) -> list[dict[str, Any]]:
    branches = tree.get("branches") or {}
    rank_pos = {
        str(leaf_id): index for index, leaf_id in enumerate(ranking, start=1)
    }
    leaves: list[dict[str, Any]] = []
    for leaf_id, node in sorted(branches.items()):
        if not isinstance(node, Mapping) or node.get("children"):
            continue
        label = str(node.get("label") or node.get("name") or "").strip()
        if not label:
            continue
        parent_id = str(node.get("parent") or "")
        parent = branches.get(parent_id) or {}
        leaves.append({
            "leaf_id": str(leaf_id),
            "leaf_label": label,
            "parent_id": parent_id,
            "parent_label": str(
                parent.get("label") or parent.get("name") or ""
            ).strip(),
            "joint_rank": rank_pos.get(str(leaf_id)),
            "posterior": float(node.get("posterior") or 0.0),
        })
    return leaves


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {str(value): str(value) for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        if left not in self.parent or right not in self.parent:
            return
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)

    def groups(self) -> list[list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for value in self.parent:
            grouped[self.find(value)].append(value)
        return [sorted(group) for group in grouped.values()]


def build_clone_groups(
    leaves: Sequence[Mapping[str, Any]],
    resolver: DiseaseNameResolver,
    semantic_groups: Sequence[Sequence[str]] = (),
) -> list[list[str]]:
    ids = [str(leaf["leaf_id"]) for leaf in leaves]
    union = _UnionFind(ids)
    by_key: dict[str, list[str]] = defaultdict(list)
    for leaf in leaves:
        label = str(leaf["leaf_label"])
        for key in _surface_forms(label, resolver):
            by_key[key].append(str(leaf["leaf_id"]))
    for members in by_key.values():
        for member in members[1:]:
            union.union(members[0], member)
    for members in semantic_groups:
        valid = [str(value) for value in members if str(value) in union.parent]
        for member in valid[1:]:
            union.union(valid[0], member)
    return sorted(union.groups(), key=lambda group: (group[0], len(group)))


def _clone_lookup(groups: Sequence[Sequence[str]]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for group in groups:
        normalized = sorted({str(value) for value in group})
        for value in normalized:
            lookup[value] = normalized
    return lookup


def _deterministic_map(
    options: Mapping[str, str],
    leaves: Sequence[Mapping[str, Any]],
    resolver: DiseaseNameResolver,
) -> dict[str, dict[str, Any]]:
    labels = [str(leaf["leaf_label"]) for leaf in leaves]
    resolver.register_source("answer_projection_leaves", labels)
    leaf_forms = {
        str(leaf["leaf_id"]): _surface_forms(str(leaf["leaf_label"]), resolver)
        for leaf in leaves
    }
    results: dict[str, dict[str, Any]] = {}
    for letter, option_text in sorted(options.items()):
        option_forms = _surface_forms(str(option_text), resolver)
        ids = [
            leaf_id for leaf_id, forms in leaf_forms.items()
            if option_forms & forms
        ]
        if not ids:
            resolved = resolver.resolve(
                str(option_text), "answer_projection_leaves",
            )
            if resolved:
                resolved_forms = _surface_forms(resolved, resolver)
                ids = [
                    leaf_id for leaf_id, forms in leaf_forms.items()
                    if resolved_forms & forms
                ]
        results[str(letter).upper()] = {
            "relation_type": "equivalent" if ids else "unknown",
            "matched_leaf_ids": sorted(set(ids)),
            "confidence": "high" if ids else "low",
            "confidence_score": 0.98 if ids else 0.0,
            "rationale": (
                "canonical/bridge entity match" if ids
                else "no deterministic entity relation"
            ),
            "source": "deterministic",
        }
    return results


def _confidence_score(value: Any) -> float:
    if isinstance(value, (float, int)):
        return max(0.0, min(1.0, float(value)))
    return {"high": 0.9, "medium": 0.65, "low": 0.3}.get(
        str(value).lower(), 0.0,
    )


def validate_llm_mapping(
    response: Mapping[str, Any],
    *,
    options: Mapping[str, str],
    leaf_ids: set[str],
    drop_invalid_clone_groups: bool = False,
) -> tuple[Optional[dict[str, Any]], list[str]]:
    errors: list[str] = []
    target = str(response.get("question_target") or "")
    if target not in QUESTION_TARGETS:
        errors.append("invalid_question_target")
    rows = response.get("option_relations")
    if not isinstance(rows, list):
        errors.append("option_relations_not_list")
        rows = []
    expected_letters = {str(letter).upper() for letter in options}
    seen: set[str] = set()
    cleaned_rows: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            errors.append("option_relation_not_object")
            continue
        letter = str(raw.get("option_letter") or "").upper()
        if letter not in expected_letters or letter in seen:
            errors.append("invalid_or_duplicate_option_letter:%s" % letter)
            continue
        seen.add(letter)
        relation = str(raw.get("relation_type") or "")
        if relation not in RELATION_TYPES:
            errors.append("invalid_relation:%s" % letter)
        matched = raw.get("matched_leaf_ids") or []
        if not isinstance(matched, list):
            errors.append("matched_leaf_ids_not_list:%s" % letter)
            matched = []
        matched_ids = [str(value) for value in matched]
        if any(value not in leaf_ids for value in matched_ids):
            errors.append("unknown_leaf_id:%s" % letter)
        if relation in {"unrelated", "unknown"} and matched_ids:
            errors.append("negative_relation_has_match:%s" % letter)
        confidence = str(raw.get("confidence") or "").lower()
        if confidence not in CONFIDENCE_VALUES:
            errors.append("invalid_confidence:%s" % letter)
        cleaned_rows.append({
            "option_letter": letter,
            "relation_type": relation,
            "matched_leaf_ids": sorted(set(matched_ids)),
            "confidence": confidence,
            "confidence_score": _confidence_score(
                raw.get("confidence_score", confidence),
            ),
            "rationale": str(raw.get("rationale") or "").strip(),
            "source": "typed_llm",
        })
    if seen != expected_letters:
        errors.append("incomplete_option_coverage")

    semantic_groups = response.get("semantic_clone_groups") or []
    if not isinstance(semantic_groups, list):
        errors.append("semantic_clone_groups_not_list")
        semantic_groups = []
    clean_groups: list[list[str]] = []
    dropped_clone_groups = 0
    for group in semantic_groups:
        if not isinstance(group, list):
            if drop_invalid_clone_groups:
                dropped_clone_groups += 1
            else:
                errors.append("semantic_clone_group_not_list")
            continue
        ids = sorted({str(value) for value in group})
        if len(ids) < 2 or any(value not in leaf_ids for value in ids):
            if drop_invalid_clone_groups:
                dropped_clone_groups += 1
            else:
                errors.append("invalid_semantic_clone_group")
            continue
        clean_groups.append(ids)
    if errors:
        return None, errors
    return {
        "question_target": target,
        "option_relations": cleaned_rows,
        "semantic_clone_groups": clean_groups,
        "dropped_semantic_clone_groups": dropped_clone_groups,
    }, []


def _call_module(
    client: Any, module: str, prompt: str, payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    assert_gold_blind(payload)
    if hasattr(client, "call_module"):
        return client.call_module(module, prompt, payload)
    if hasattr(client, "call"):
        return client.call(module, prompt, payload)
    if callable(client):
        return client(module, prompt, payload)
    raise TypeError("LLM client does not expose call_module/call")


def _rank_and_expand(
    *,
    mappings: Mapping[str, Mapping[str, Any]],
    leaves: Sequence[Mapping[str, Any]],
    clone_groups: Sequence[Sequence[str]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    leaf_by_id = {str(leaf["leaf_id"]): dict(leaf) for leaf in leaves}
    clones = _clone_lookup(clone_groups)
    output: dict[str, dict[str, Any]] = {}
    for letter, mapping in sorted(mappings.items()):
        direct = [
            str(value) for value in mapping.get("matched_leaf_ids") or ()
            if str(value) in leaf_by_id
        ]
        expanded: set[str] = set(direct)
        for leaf_id in direct:
            expanded.update(clones.get(leaf_id, [leaf_id]))
        ranked = [
            leaf_by_id[leaf_id] for leaf_id in expanded
            if leaf_by_id[leaf_id].get("joint_rank") is not None
        ]
        best_rank = min(
            (int(row["joint_rank"]) for row in ranked), default=None,
        )
        max_posterior = max(
            (float(leaf_by_id[value].get("posterior") or 0.0)
             for value in expanded),
            default=0.0,
        )
        rank_support = 1.0 / best_rank if best_rank else 0.0
        support = max(rank_support, max_posterior)
        output[letter] = {
            **dict(mapping),
            "matched_leaf_ids": sorted(set(direct)),
            "clone_leaf_ids": sorted(expanded),
            "matched": bool(expanded),
            "best_rank": best_rank,
            "support_score": support,
            "posterior": max_posterior,
        }

    finite = sorted({
        int(row["best_rank"]) for row in output.values()
        if row.get("best_rank") is not None
    })
    dense_rank = {value: index for index, value in enumerate(finite, start=1)}
    ordered = sorted(
        output,
        key=lambda letter: (
            output[letter].get("best_rank") is None,
            output[letter].get("best_rank")
            if output[letter].get("best_rank") is not None else 10**9,
            -float(output[letter].get("support_score") or 0.0),
            letter,
        ),
    )
    next_unranked = len(finite) + 1
    for letter in ordered:
        best_rank = output[letter].get("best_rank")
        output[letter]["option_rank"] = (
            dense_rank[int(best_rank)] if best_rank is not None
            else next_unranked
        )
    return output, ordered


_RELATION_PRIORITY = {
    "equivalent": 0,
    "subtype_of": 1,
    "supertype_of": 2,
    "etiology_of": 3,
    "mechanism_of": 4,
    "manifestation_of": 5,
    "complication_of": 6,
    "treatment_for": 7,
    "unrelated": 90,
    "unknown": 91,
}


def option_rank_ties(
    option_maps: Mapping[str, Mapping[str, Any]],
) -> dict[int, list[str]]:
    """Return option_rank → letters for ranks shared by ≥2 options."""
    buckets: dict[int, list[str]] = defaultdict(list)
    for letter, row in sorted(option_maps.items()):
        rank = row.get("option_rank")
        if rank is None:
            continue
        buckets[int(rank)].append(str(letter).upper())
    return {rank: letters for rank, letters in buckets.items() if len(letters) > 1}


def has_option_rank_ties(option_maps: Mapping[str, Mapping[str, Any]]) -> bool:
    return bool(option_rank_ties(option_maps))


def competition_total_order(
    option_maps: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Deterministic strict total order (no LLM). Breaks dense-rank ties."""
    return sorted(
        (str(letter).upper() for letter in option_maps),
        key=lambda letter: (
            option_maps[letter].get("best_rank") is None
            and not bool(option_maps[letter].get("matched")),
            option_maps[letter].get("best_rank")
            if option_maps[letter].get("best_rank") is not None else 10**9,
            _RELATION_PRIORITY.get(
                str(option_maps[letter].get("relation_type") or "unknown"), 91,
            ),
            -float(option_maps[letter].get("support_score") or 0.0),
            -float(option_maps[letter].get("confidence_score") or 0.0),
            letter,
        ),
    )


def _apply_total_order(
    option_maps: Mapping[str, Mapping[str, Any]],
    order: Sequence[str],
    *,
    matched_before_unmatched: bool = True,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    letters = [str(x).upper() for x in order]
    expected = sorted(str(k).upper() for k in option_maps)
    if sorted(letters) != expected or len(set(letters)) != len(letters):
        raise ValueError(
            "strict order must be a permutation of option letters; "
            f"got {letters}, expected {expected}"
        )
    key_by_upper = {
        str(k).upper(): k for k in option_maps
    }

    def _matched(letter: str) -> bool:
        row = option_maps[key_by_upper[letter]]
        if row.get("best_rank") is not None:
            return True
        if row.get("matched"):
            return True
        ids = list(row.get("matched_leaf_ids") or row.get("clone_leaf_ids") or ())
        rel = str(row.get("relation_type") or "")
        return bool(ids) and rel not in {"", "unrelated", "unknown"}

    if matched_before_unmatched:
        matched = [L for L in letters if _matched(L)]
        unmatched = [L for L in letters if not _matched(L)]
        letters = matched + unmatched

    out = {k: dict(v) for k, v in option_maps.items()}
    for index, letter in enumerate(letters, start=1):
        key = key_by_upper[letter]
        out[key]["option_rank"] = index
        out[key]["strict_order_position"] = index
        out[key]["matched_gate_partition"] = (
            "matched" if _matched(letter) else "unmatched"
        )
    return out, letters


def llm_strict_total_order(
    *,
    llm: Any,
    prompt: str,
    vignette: str,
    question: str,
    options: Mapping[str, str],
    leaves: Sequence[Mapping[str, Any]],
    option_maps: Mapping[str, Mapping[str, Any]],
    case_id: str = "",
) -> tuple[list[str], dict[str, Any]]:
    """Ask LLM for a strict permutation of option letters."""
    compact_maps = {}
    for letter, row in sorted(option_maps.items()):
        compact_maps[str(letter).upper()] = {
            "option_text": str(options.get(letter) or options.get(str(letter).upper()) or ""),
            "relation_type": row.get("relation_type"),
            "matched": bool(row.get("matched")),
            "matched_leaf_ids": list(row.get("matched_leaf_ids") or ()),
            "best_rank": row.get("best_rank"),
            "support_score": row.get("support_score"),
            "confidence_score": row.get("confidence_score"),
            "prior_option_rank": row.get("option_rank"),
        }
    payload = {
        "case_id": str(case_id),
        "vignette": str(vignette),
        "question": str(question),
        "options": {
            str(k).upper(): str(v) for k, v in sorted(options.items())
        },
        "leaves": [dict(row) for row in leaves],
        "option_maps": compact_maps,
        "require_strict_total_order": True,
    }
    assert_gold_blind(payload)
    raw = _call_module(llm, "L2OptionStrictTotalOrder", prompt, payload)
    order = [str(x).upper() for x in (raw.get("order") or ())]
    expected = sorted(str(k).upper() for k in option_maps)
    if sorted(order) != expected or len(set(order)) != len(order):
        raise ValueError(
            "L2OptionStrictTotalOrder returned invalid permutation: %s" % order
        )
    return order, {
        "called": True,
        "schema_valid": True,
        "rationale": str(raw.get("rationale") or ""),
        "raw_order": order,
    }


def enforce_strict_total_order(
    *,
    option_maps: Mapping[str, Mapping[str, Any]],
    llm: Any = None,
    prompt: str = "",
    vignette: str = "",
    question: str = "",
    options: Optional[Mapping[str, str]] = None,
    leaves: Optional[Sequence[Mapping[str, Any]]] = None,
    case_id: str = "",
    force_llm: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, Any]]:
    """Force unique option_rank 1..n.

    If the dense-rank maps already have unique ranks and ``force_llm`` is false,
    keep them. Otherwise prefer an LLM permutation; fall back to deterministic
    competition order when the LLM is unavailable or returns an invalid order.
    """
    ties = option_rank_ties(option_maps)
    meta: dict[str, Any] = {
        "had_ties": bool(ties),
        "tie_ranks": {str(k): v for k, v in sorted(ties.items())},
        "method": "identity",
        "llm": {"called": False},
    }
    if not ties and not force_llm:
        ordered = sorted(
            option_maps,
            key=lambda letter: (
                int(option_maps[letter].get("option_rank") or 10**9),
                str(letter).upper(),
            ),
        )
        out = {k: dict(v) for k, v in option_maps.items()}
        return out, [str(x).upper() for x in ordered], meta

    if llm is not None and prompt and options is not None:
        try:
            order, llm_meta = llm_strict_total_order(
                llm=llm,
                prompt=prompt,
                vignette=vignette,
                question=question,
                options=options,
                leaves=list(leaves or ()),
                option_maps=option_maps,
                case_id=case_id,
            )
            out, ordered = _apply_total_order(option_maps, order)
            meta["method"] = "llm_strict_total_order"
            meta["llm"] = llm_meta
            return out, ordered, meta
        except (RuntimeError, TypeError, ValueError) as exc:
            meta["llm"] = {
                "called": True,
                "schema_valid": False,
                "error": "%s: %s" % (type(exc).__name__, exc),
            }

    order = competition_total_order(option_maps)
    out, ordered = _apply_total_order(option_maps, order)
    meta["method"] = "competition_fallback" if meta["llm"].get("called") else "competition"
    return out, ordered, meta


class RelationAwareAnswerMapper:
    """Typed LLM mapper with deterministic checks and optional RAG critic."""

    def __init__(
        self,
        *,
        resolver: DiseaseNameResolver,
        llm: Any = None,
        relation_prompt: str = "",
        critic_prompt: str = "",
        strict_order_prompt: str = "",
        retrievers: Optional[Mapping[str, Any]] = None,
        confidence_threshold: float = 0.75,
        rag_top_k: int = 3,
        rag_max_snippets: int = 8,
        rag_max_chars: int = 1200,
        strict_total_order: bool = False,
    ) -> None:
        self.resolver = resolver
        self.llm = llm
        self.relation_prompt = relation_prompt
        self.critic_prompt = critic_prompt
        self.strict_order_prompt = strict_order_prompt
        self.retrievers = dict(retrievers or {})
        self.confidence_threshold = confidence_threshold
        self.rag_top_k = rag_top_k
        self.rag_max_snippets = rag_max_snippets
        self.rag_max_chars = rag_max_chars
        self.strict_total_order = bool(strict_total_order)

    def _typed_mapping(
        self, payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if self.llm is None:
            raise RuntimeError("typed mapping requires an LLM client")
        raw = _call_module(
            self.llm, "L2RelationAnswerMapper", self.relation_prompt, payload,
        )
        leaf_ids = {
            str(row["leaf_id"]) for row in payload.get("leaves") or ()
        }
        validated, errors = validate_llm_mapping(
            raw, options=payload["options"], leaf_ids=leaf_ids,
        )
        repair_used = False
        if validated is None:
            repair_payload = {
                **dict(payload),
                "invalid_response": dict(raw),
                "validation_errors": errors,
                "schema_repair": (
                    "Return strict JSON with every option exactly once and only "
                    "the provided leaf IDs."
                ),
            }
            raw = _call_module(
                self.llm,
                "L2RelationAnswerMapperRepair",
                self.relation_prompt,
                repair_payload,
            )
            validated, errors = validate_llm_mapping(
                raw,
                options=payload["options"],
                leaf_ids=leaf_ids,
                drop_invalid_clone_groups=True,
            )
            repair_used = True
        if validated is None:
            raise ValueError("invalid typed mapper response: %s" % errors)
        return validated, {
            "schema_valid": True,
            "schema_repair_used": repair_used,
            "dropped_semantic_clone_groups": int(
                validated.get("dropped_semantic_clone_groups") or 0
            ),
            "validation_errors": [],
        }

    def _retrieve(
        self,
        *,
        question_target: str,
        option_text: str,
        candidate_labels: Sequence[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        labels = " vs ".join(candidate_labels[:4])
        query = (
            "%s relation between option '%s' and diagnosis '%s'"
            % (question_target, option_text, labels)
        )
        snippets: list[dict[str, Any]] = []
        requests: list[dict[str, Any]] = []
        for source, retriever in sorted(self.retrievers.items()):
            if hasattr(retriever, "search_option_leaves"):
                hits = retriever.search_option_leaves(
                    str(option_text),
                    list(candidate_labels),
                    top_k=self.rag_top_k,
                    score_threshold=0.0,
                )
            else:
                hits = retriever.search(
                    query, top_k=self.rag_top_k, score_threshold=0.0,
                )
            requests.append({
                "source": source, "query": query, "returned": len(hits),
            })
            for hit in hits:
                snippets.append({
                    "source": source,
                    "chunk_id": str(hit.get("id") or ""),
                    "title": str(hit.get("title") or ""),
                    "text": str(hit.get("content") or "")[:self.rag_max_chars],
                    "score": float(hit.get("score") or 0.0),
                })
        snippets.sort(
            key=lambda row: (-float(row["score"]), row["source"], row["chunk_id"]),
        )
        return snippets[:self.rag_max_snippets], requests

    def _rag_critic(
        self,
        *,
        base_payload: Mapping[str, Any],
        question_target: str,
        disputes: Sequence[Mapping[str, Any]],
        leaves: Sequence[Mapping[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        if not disputes or self.llm is None or not self.retrievers:
            return {}, {
                "triggered": bool(disputes),
                "called": False,
                "fail_open": bool(disputes),
                "requests": [],
                "snippets": [],
            }
        leaf_by_id = {str(row["leaf_id"]): row for row in leaves}
        all_snippets: list[dict[str, Any]] = []
        requests: list[dict[str, Any]] = []
        critic_rows: list[dict[str, Any]] = []
        for dispute in disputes:
            candidate_ids = list(dispute.get("candidate_leaf_ids") or ())
            labels = [
                str(leaf_by_id[value]["leaf_label"])
                for value in candidate_ids if value in leaf_by_id
            ]
            snippets, req = self._retrieve(
                question_target=question_target,
                option_text=str(dispute["option_text"]),
                candidate_labels=labels,
            )
            all_snippets.extend(snippets)
            requests.extend(req)
            critic_rows.append({
                **dict(dispute),
                "public_knowledge_snippets": snippets,
            })
        critic_payload = {
            "case_id": base_payload.get("case_id"),
            "question": base_payload.get("question"),
            "question_target": question_target,
            "options": base_payload.get("options"),
            "leaves": list(leaves),
            "disputes": critic_rows,
        }
        try:
            raw = _call_module(
                self.llm,
                "L2RelationAnswerRAGCritic",
                self.critic_prompt,
                critic_payload,
            )
        except Exception as exc:
            return {}, {
                "triggered": True,
                "called": True,
                "fail_open": True,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "requests": requests,
                "snippets": all_snippets,
            }
        decisions = raw.get("decisions") if isinstance(raw, Mapping) else None
        cleaned: dict[str, dict[str, Any]] = {}
        valid_ids = set(leaf_by_id)
        valid_letters = {str(value["option_letter"]) for value in disputes}
        if isinstance(decisions, list):
            for row in decisions:
                if not isinstance(row, Mapping):
                    continue
                letter = str(row.get("option_letter") or "").upper()
                relation = str(row.get("relation_type") or "")
                matched = [str(value) for value in row.get("matched_leaf_ids") or ()]
                if (
                    letter not in valid_letters
                    or relation not in RELATION_TYPES
                    or any(value not in valid_ids for value in matched)
                ):
                    continue
                if relation in {"unrelated", "unknown"}:
                    matched = []
                cleaned[letter] = {
                    "relation_type": relation,
                    "matched_leaf_ids": sorted(set(matched)),
                    "confidence": str(row.get("confidence") or "medium"),
                    "confidence_score": _confidence_score(
                        row.get("confidence_score", row.get("confidence")),
                    ),
                    "rationale": str(row.get("rationale") or ""),
                    "source": "rag_critic",
                }
        return cleaned, {
            "triggered": True,
            "called": True,
            "fail_open": len(cleaned) != len(disputes),
            "requests": requests,
            "snippets": all_snippets,
            "response": dict(raw) if isinstance(raw, Mapping) else raw,
        }

    def map(
        self,
        *,
        case_id: str,
        vignette: str,
        question: str,
        options: Mapping[str, str],
        leaves: Sequence[Mapping[str, Any]],
        mode: str,
    ) -> dict[str, Any]:
        if mode not in {
            "deterministic_gold_blind", "typed_llm",
            "typed_llm_disagreement_rag", "typed_llm_synonym_kb",
        }:
            raise ValueError("unsupported mapper mode: %s" % mode)
        payload = {
            "case_id": str(case_id),
            "vignette": str(vignette),
            "question": str(question),
            "options": {
                str(letter).upper(): str(text)
                for letter, text in sorted(options.items())
            },
            "leaves": [dict(row) for row in leaves],
        }
        assert_gold_blind(payload)
        deterministic = _deterministic_map(
            payload["options"], leaves, self.resolver,
        )
        heuristic_target = infer_question_target(question)
        typed_audit: dict[str, Any] = {
            "called": False, "schema_valid": True, "schema_repair_used": False,
        }
        semantic_groups: list[list[str]] = []
        typed_rows: dict[str, dict[str, Any]] = {}
        typed_fail_open = False
        question_target = heuristic_target
        if mode != "deterministic_gold_blind":
            try:
                typed, typed_audit = self._typed_mapping(payload)
                typed_audit["called"] = True
                question_target = typed["question_target"]
                semantic_groups = list(typed["semantic_clone_groups"])
                typed_rows = {
                    str(row["option_letter"]): dict(row)
                    for row in typed["option_relations"]
                }
            except (RuntimeError, TypeError, ValueError) as exc:
                # Exhausted schema/transport repair is technical missingness, not
                # permission to drop the evaluation unit. Preserve a deterministic
                # gold-blind projection, make the failure explicit, and let the RAG
                # arm criticise every option.
                typed_fail_open = True
                typed_rows = {
                    letter: {
                        **dict(row),
                        "source": "typed_failure_deterministic_fail_open",
                        "confidence": "low",
                        "confidence_score": 0.0,
                    }
                    for letter, row in deterministic.items()
                }
                typed_audit = {
                    "called": True,
                    "schema_valid": False,
                    "schema_repair_used": True,
                    "fail_open": True,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }

        selected = (
            {letter: dict(row) for letter, row in deterministic.items()}
            if mode == "deterministic_gold_blind"
            else {letter: dict(row) for letter, row in typed_rows.items()}
        )
        disputes: list[dict[str, Any]] = []
        all_leaf_ids = [
            str(row.get("leaf_id"))
            for row in leaves
            if str(row.get("leaf_id") or "").strip()
        ]
        for letter, option_text in payload["options"].items():
            det = deterministic[letter]
            typed = typed_rows.get(letter, {})
            typed_ids = set(typed.get("matched_leaf_ids") or ())
            det_ids = set(det.get("matched_leaf_ids") or ())
            low_confidence = (
                float(typed.get("confidence_score") or 0.0)
                < self.confidence_threshold
            )
            unmatched = not typed_ids
            disagreement = bool(det_ids) and det_ids != typed_ids
            if mode == "typed_llm_synonym_kb":
                # Symmetric: every option gets synonym/granularity critic.
                # Candidate pool = shortlist leaves (gold-blind; enables re-bind
                # when typed said unrelated with empty matched ids).
                cands = sorted(set(all_leaf_ids) | det_ids | typed_ids)
                disputes.append({
                    "option_letter": letter,
                    "option_text": option_text,
                    "deterministic_relation": det,
                    "typed_relation": typed,
                    "candidate_leaf_ids": cands,
                    "trigger_reasons": ["synonym_kb_all_options"],
                })
            elif (
                mode == "typed_llm_disagreement_rag"
                and (
                    typed_fail_open or unmatched or low_confidence or disagreement
                )
            ):
                disputes.append({
                    "option_letter": letter,
                    "option_text": option_text,
                    "deterministic_relation": det,
                    "typed_relation": typed,
                    "candidate_leaf_ids": sorted(det_ids | typed_ids),
                    "trigger_reasons": [
                        reason for reason, active in (
                            ("typed_schema_fail_open", typed_fail_open),
                            ("unmatched", unmatched),
                            ("low_confidence", low_confidence),
                            ("deterministic_llm_disagreement", disagreement),
                        ) if active
                    ],
                })

        critic_rows, rag_audit = self._rag_critic(
            base_payload=payload,
            question_target=question_target,
            disputes=disputes,
            leaves=leaves,
        )
        selected.update(critic_rows)
        clone_groups = build_clone_groups(
            leaves, self.resolver, semantic_groups=semantic_groups,
        )
        option_maps, option_order = _rank_and_expand(
            mappings=selected, leaves=leaves, clone_groups=clone_groups,
        )
        strict_meta: dict[str, Any] = {"enabled": False}
        if self.strict_total_order:
            option_maps, option_order, strict_meta = enforce_strict_total_order(
                option_maps=option_maps,
                llm=self.llm,
                prompt=self.strict_order_prompt,
                vignette=str(vignette),
                question=str(question),
                options=payload["options"],
                leaves=leaves,
                case_id=str(case_id),
                force_llm=has_option_rank_ties(option_maps),
            )
            strict_meta["enabled"] = True
        return {
            "schema_version": 1,
            "case_id": case_id,
            "mode": mode,
            "question_target": question_target,
            "option_maps": option_maps,
            "option_order": option_order,
            "clone_groups": clone_groups,
            "audit": {
                "gold_blind": True,
                "payload_hash": stable_hash(payload),
                "deterministic": deterministic,
                "typed": typed_audit,
                "disputes": disputes,
                "rag": rag_audit,
                "strict_total_order": strict_meta,
            },
        }
