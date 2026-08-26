#!/usr/bin/env python3
"""Deterministic typed atom -> phenotype prototype alignment probe.

This is an offline mechanics probe, not a clinical classifier.  It uses the
reviewed ``phenotype_prototype_cards_v2.json`` seed pack and deliberately keeps
candidate retrieval separate from phenotype entailment:

1. contiguous atom n-grams address per-slot lexical postings;
2. postings aggregate a small candidate target set;
3. each candidate receives a maximum-weight one-to-one atom/slot alignment;
4. subject, time, polarity, modality, quality, and value gates emit T/F/U;
5. card ``required_logic`` decides entailed/contradicted/unknown; and
6. anything other than entailed is query-only abstention.

No symptom pairs or triples are materialized.  Dense similarity, LLM calls,
network access, learned weights, and gold labels are absent from inference.
Card weights are not consulted by retrieval, alignment, or truth evaluation.
They therefore cannot turn an unknown or false gate into a true phenotype
assertion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
CARDS = ROOT / "data" / "knowledge_raw" / "phenotype_prototype_cards_v2.json"
CASES = ROOT / "analysis" / "mechanism_v2" / "phenotype_typed_alignment_cases.json"
DEFAULT_OUT = (
    ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "PHENOTYPE_TYPED_ALIGNMENT_PROBE"
)
NORMALIZED_CACHE = (
    ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "NORMALIZED_INPUT_PROBE"
    / "normalized_cache.json"
)

TRUE = "T"
FALSE = "F"
UNKNOWN = "U"
VALID_QUALITY = {"valid", "validated", "reliable", "good", "diagnostic"}
INVALID_QUALITY = {
    "poor",
    "unreliable",
    "invalid",
    "contaminated",
    "artifact",
    "artefact",
}
CURRENT_TIMES = {"current", "acute", "same episode", "same study", "same panel"}
PAST_TIMES = {"past", "historical", "resolved", "remote"}


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


def _surface(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _atom_surface(atom: Mapping[str, Any]) -> str:
    pieces = [atom.get("text", ""), atom.get("name", "")]
    measurement = atom.get("measurement") or {}
    pieces.append(measurement.get("name", ""))
    pieces.extend(atom.get("aliases", []))
    return _surface(" ".join(str(piece) for piece in pieces if piece))


def _resource_id(atom: Mapping[str, Any]) -> str:
    """Collapse duplicate normalizations of one observation before alignment."""

    return str(atom.get("correlation_id") or atom.get("atom_id") or "")


@dataclass(frozen=True)
class Posting:
    surface: str
    prototype_id: str
    slot_id: str
    kind: str
    strength: float


def load_cards(path: Path = CARDS) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("schema_version") != "phenotype-prototype-card/2.0":
        raise ValueError("prototype card schema must be phenotype-prototype-card/2.0")
    contract = payload.get("global_contract", {})
    if contract.get("pair_or_triple_enumeration") is not False:
        raise ValueError("prototype pack does not prohibit pair/triple enumeration")
    prototypes = payload.get("prototypes", [])
    if not prototypes:
        raise ValueError("prototype pack is empty")
    seen: set[str] = set()
    for prototype in prototypes:
        prototype_id = prototype.get("prototype_id")
        if not prototype_id or prototype_id in seen:
            raise ValueError(f"invalid/duplicate prototype_id: {prototype_id!r}")
        seen.add(prototype_id)
        anchor_relation = prototype.get("ontology_anchor_relation")
        if anchor_relation not in {"identity", "related_query_only"}:
            raise ValueError(
                f"{prototype_id}: ontology_anchor_relation must be identity or related_query_only"
            )
        if (
            anchor_relation == "identity"
            and prototype.get("target_id") not in prototype.get("ontology_anchors", [])
        ):
            raise ValueError(f"{prototype_id}: identity anchor must contain target_id")
        slot_ids = [slot.get("slot_id") for slot in prototype.get("slots", [])]
        if len(slot_ids) != len(set(slot_ids)) or not all(slot_ids):
            raise ValueError(f"invalid/duplicate slot in {prototype_id}")
    return prototypes


class PostingIndex:
    """Atomic lexical address index; it never creates atom combinations."""

    def __init__(self, prototypes: Sequence[Mapping[str, Any]]) -> None:
        raw: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for prototype in prototypes:
            prototype_id = str(prototype["prototype_id"])
            for slot in prototype.get("slots", []):
                slot_id = str(slot["slot_id"])
                values: list[tuple[str, str]] = []
                values.extend((str(alias), "slot_alias") for alias in slot.get("aliases", []))
                values.append((str(slot.get("label", "")), "slot_label"))
                for spec_name in ("measurement", "derived_measurement"):
                    spec = slot.get(spec_name) or {}
                    values.extend((str(name), "measurement_name") for name in spec.get("names", []))
                    if spec_name == "derived_measurement" and spec.get("kind"):
                        values.append((str(spec["kind"]).replace("_", " "), "measurement_name"))
                for value, kind in values:
                    surface = _surface(value)
                    if surface:
                        raw[surface].append((prototype_id, slot_id, kind))

        prototype_count = len(prototypes)
        self.by_surface: dict[str, tuple[Posting, ...]] = {}
        for surface, rows in raw.items():
            target_df = len({row[0] for row in rows})
            idf = 1.0 + math.log((prototype_count + 1.0) / (target_df + 1.0))
            length_bonus = 0.05 * len(surface.split())
            unique_rows = sorted(set(rows))
            self.by_surface[surface] = tuple(
                Posting(surface, prototype_id, slot_id, kind, idf + length_bonus)
                for prototype_id, slot_id, kind in unique_rows
            )
        self.max_tokens = max((len(key.split()) for key in self.by_surface), default=1)

    def lookup(self, atom: Mapping[str, Any]) -> tuple[list[Posting], int]:
        tokens = _atom_surface(atom).split()
        hits: dict[tuple[str, str, str], Posting] = {}
        lookups = 0
        for start in range(len(tokens)):
            limit = min(len(tokens), start + self.max_tokens)
            for stop in range(start + 1, limit + 1):
                lookups += 1
                surface = " ".join(tokens[start:stop])
                for posting in self.by_surface.get(surface, ()):
                    key = (posting.prototype_id, posting.slot_id, posting.surface)
                    previous = hits.get(key)
                    if previous is None or posting.strength > previous.strength:
                        hits[key] = posting
        return sorted(
            hits.values(),
            key=lambda row: (-row.strength, row.prototype_id, row.slot_id, row.surface),
        ), lookups


def _gate_subject(atom: Mapping[str, Any], prototype: Mapping[str, Any]) -> str:
    expected = _surface((prototype.get("context_contract") or {}).get("subject", "patient"))
    actual = _surface(atom.get("subject", ""))
    if not actual:
        return UNKNOWN
    return TRUE if actual == expected else FALSE


def _gate_time(atom: Mapping[str, Any]) -> str:
    actual = _surface(atom.get("temporality", ""))
    if not actual:
        return UNKNOWN
    if actual in CURRENT_TIMES:
        return TRUE
    if actual in PAST_TIMES:
        return FALSE
    return UNKNOWN


def _gate_polarity(atom: Mapping[str, Any]) -> str:
    actual = _surface(atom.get("polarity", ""))
    if actual in {"present", "positive", "affirmed"}:
        return TRUE
    if actual in {"absent", "negative", "negated"}:
        return FALSE
    return UNKNOWN


def _accepted_modalities(prototype_id: str, slot_id: str) -> set[str]:
    if prototype_id == "PLV2_UIP_PATTERN":
        return {"ct", "hrct"}
    if prototype_id == "PLV2_HYPOXEMIA":
        if slot_id == "low_pao2":
            return {"abg", "laboratory", "measurement"}
        if slot_id == "low_spo2":
            return {"pulse oximetry", "measurement"}
        return {"clinical", "observation"}
    if prototype_id == "PLV2_NEPHROTIC_SYNDROME" and slot_id == "edema":
        return {"clinical", "examination", "observation"}
    if prototype_id == "PLV2_HEMOLYTIC_PROCESS" and slot_id == "schistocytes":
        return {"smear", "laboratory"}
    return {"laboratory"}


def _gate_modality(
    atom: Mapping[str, Any], prototype: Mapping[str, Any], slot: Mapping[str, Any]
) -> str:
    actual = _surface(atom.get("modality", ""))
    if not actual:
        return UNKNOWN
    accepted = _accepted_modalities(str(prototype["prototype_id"]), str(slot["slot_id"]))
    if actual not in accepted:
        return FALSE

    specimen = _surface(atom.get("specimen", ""))
    prototype_id = str(prototype["prototype_id"])
    slot_id = str(slot["slot_id"])
    if prototype_id == "PLV2_NEPHROTIC_SYNDROME":
        expected = "urine" if slot_id == "heavy_proteinuria" else (
            "blood" if slot_id in {"hypoalbuminemia", "hyperlipidemia"} else ""
        )
        if expected and not specimen:
            return UNKNOWN
        if expected and specimen != expected:
            return FALSE
    elif actual == "laboratory" and prototype_id != "PLV2_NEPHROTIC_SYNDROME":
        expected = "blood"
        if not specimen:
            return UNKNOWN
        if specimen != expected:
            return FALSE
    return TRUE


def _gate_quality(atom: Mapping[str, Any], slot: Mapping[str, Any]) -> str:
    quality = _surface(atom.get("quality", ""))
    if not quality:
        return UNKNOWN
    if quality in INVALID_QUALITY:
        return FALSE
    if quality not in VALID_QUALITY:
        return UNKNOWN
    if slot.get("quality_requires"):
        oxygen_context = atom.get("oxygen_context")
        if oxygen_context in (None, "", "unknown"):
            return UNKNOWN
    return TRUE


def _canonical_unit(value: Any) -> str:
    surface = _surface(value)
    aliases = {
        "percent": "percent",
        "%": "percent",
        "mmhg": "mmhg",
        "mm hg": "mmhg",
        "g dl": "g_per_dl",
        "g per dl": "g_per_dl",
        "g day": "g_per_day",
        "g per day": "g_per_day",
    }
    return aliases.get(surface, surface.replace(" ", "_"))


def _unit_gate(spec: Mapping[str, Any], measurement: Mapping[str, Any], atom: Mapping[str, Any]) -> str:
    family = spec.get("unit_family")
    if not family:
        return TRUE
    actual = _canonical_unit(measurement.get("unit", ""))
    expected = {
        "percent": "percent",
        "mmHg": "mmhg",
        "g_per_dL": "g_per_dl",
        "g_per_day_adult_only": "g_per_day",
    }.get(str(family), str(family).casefold())
    if not actual:
        return UNKNOWN
    if actual != expected:
        return FALSE
    if family == "g_per_day_adult_only":
        age_group = _surface(atom.get("age_group", ""))
        if not age_group:
            return UNKNOWN
        if age_group != "adult":
            return FALSE
    return TRUE


def _measurement_name_matches(spec: Mapping[str, Any], measurement: Mapping[str, Any]) -> bool:
    actual = _surface(measurement.get("name", ""))
    if not actual:
        return False
    names = {_surface(name) for name in spec.get("names", [])}
    if spec.get("kind"):
        names.add(_surface(str(spec["kind"]).replace("_", " ")))
    return actual in names


def _gate_numeric(
    spec: Mapping[str, Any], measurement: Mapping[str, Any], atom: Mapping[str, Any]
) -> str:
    if not _measurement_name_matches(spec, measurement):
        return UNKNOWN
    unit_state = _unit_gate(spec, measurement, atom)
    if unit_state != TRUE:
        return unit_state
    try:
        value = float(measurement["value"])
    except (KeyError, TypeError, ValueError):
        return UNKNOWN
    operator = spec.get("operator")
    threshold = spec.get("threshold")
    if operator == "gt_uln":
        try:
            threshold = float(measurement["uln"])
        except (KeyError, TypeError, ValueError):
            return UNKNOWN
        return TRUE if value > threshold else FALSE
    if threshold is None:
        return UNKNOWN
    threshold = float(threshold)
    passed = {
        "lt": value < threshold,
        "gt": value > threshold,
        "gte": value >= threshold,
        "lte": value <= threshold,
    }.get(str(operator))
    if passed is None:
        return UNKNOWN
    return TRUE if passed else FALSE


def _gate_value(atom: Mapping[str, Any], slot: Mapping[str, Any]) -> str:
    spec = slot.get("measurement") or slot.get("derived_measurement")
    if not spec:
        return TRUE
    measurement = atom.get("measurement")
    if isinstance(measurement, Mapping):
        return _gate_numeric(spec, measurement, atom)
    qualitative = _surface(atom.get("value_assertion", ""))
    if qualitative in {"supports", "entailed", "abnormal in required direction"}:
        return TRUE
    if qualitative in {"refutes", "normal", "opposite direction"}:
        return FALSE
    return UNKNOWN


def evaluate_edge(
    atom: Mapping[str, Any], prototype: Mapping[str, Any], slot: Mapping[str, Any]
) -> dict[str, Any]:
    gates = {
        "subject": _gate_subject(atom, prototype),
        "time": _gate_time(atom),
        "polarity": _gate_polarity(atom),
        "modality": _gate_modality(atom, prototype, slot),
        "quality": _gate_quality(atom, slot),
        "value": _gate_value(atom, slot),
    }
    scope_gates = ("subject", "time", "modality", "quality")
    if all(gates[name] == TRUE for name in scope_gates):
        if gates["polarity"] == FALSE or gates["value"] == FALSE:
            state = FALSE
        elif all(state == TRUE for state in gates.values()):
            state = TRUE
        else:
            state = UNKNOWN
    else:
        state = UNKNOWN
    return {"state": state, "gates": gates}


def _hungarian_max(weights: Sequence[Sequence[int]]) -> list[int]:
    """Maximum-weight row-to-column assignment in O(rows * columns * rows).

    The implementation is the rectangular Hungarian primal-dual algorithm.
    Callers append one zero-weight dummy column per row, so every slot may stay
    unassigned without enumerating combinations.
    """

    rows = len(weights)
    if rows == 0:
        return []
    columns = len(weights[0])
    if columns < rows or any(len(row) != columns for row in weights):
        raise ValueError("Hungarian matrix must be rectangular with columns >= rows")
    maximum = max(max(row) for row in weights)
    costs = [[maximum - value for value in row] for row in weights]
    u = [0] * (rows + 1)
    v = [0] * (columns + 1)
    p = [0] * (columns + 1)
    way = [0] * (columns + 1)
    infinity = 10**18
    for i in range(1, rows + 1):
        p[0] = i
        j0 = 0
        minimum = [infinity] * (columns + 1)
        used = [False] * (columns + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = infinity
            j1 = 0
            for j in range(1, columns + 1):
                if used[j]:
                    continue
                current = costs[i0 - 1][j - 1] - u[i0] - v[j]
                if current < minimum[j]:
                    minimum[j] = current
                    way[j] = j0
                if minimum[j] < delta:
                    delta = minimum[j]
                    j1 = j
            for j in range(columns + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [-1] * rows
    for j in range(1, columns + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    return assignment


def _logic_slot_ids(prototype: Mapping[str, Any]) -> set[str]:
    logic = prototype.get("required_logic", {})
    required = set(logic.get("all", []))
    at_least = logic.get("at_least") or {}
    if at_least:
        group = at_least.get("group")
        required.update(
            slot["slot_id"] for slot in prototype.get("slots", []) if slot.get("group") == group
        )
    return required


def _time_coherence(
    prototype: Mapping[str, Any], assignments: Sequence[Mapping[str, Any]]
) -> str:
    contract = _surface((prototype.get("context_contract") or {}).get("time", ""))
    if not contract.startswith("same"):
        return TRUE

    # Evaluate the card's Boolean requirement within a context rather than
    # demanding that every optional/alternative true slot share one context.
    # In particular, an extra marker from another episode must not invalidate
    # an already sufficient same-episode subset.
    logic = prototype.get("required_logic", {})
    all_slots = {str(slot_id) for slot_id in logic.get("all", [])}
    at_least = logic.get("at_least") or {}
    group = at_least.get("group")
    group_count = int(at_least.get("count", 0)) if at_least else 0
    group_slots = {
        str(slot["slot_id"])
        for slot in prototype.get("slots", [])
        if group and slot.get("group") == group
    }
    true_contexts = {
        str(row.get("slot_id")): str((row.get("assigned") or {}).get("context_id") or "")
        for row in assignments
        if row.get("slot_state") == TRUE and row.get("assigned")
    }

    if any(slot_id not in true_contexts for slot_id in all_slots):
        return UNKNOWN
    all_values = [true_contexts[slot_id] for slot_id in sorted(all_slots)]
    if any(not value for value in all_values):
        return UNKNOWN
    if len(set(all_values)) > 1:
        return FALSE
    anchor_context = all_values[0] if all_values else None

    if not at_least:
        return TRUE if all_values else UNKNOWN

    group_values = [
        true_contexts[slot_id]
        for slot_id in sorted(group_slots)
        if slot_id in true_contexts
    ]
    if len(group_values) < group_count:
        return UNKNOWN
    missing_count = sum(not value for value in group_values)
    known_counts = Counter(value for value in group_values if value)
    if anchor_context is not None:
        matching = known_counts.get(anchor_context, 0)
        if matching >= group_count:
            return TRUE
        return UNKNOWN if matching + missing_count >= group_count else FALSE
    if any(count >= group_count for count in known_counts.values()):
        return TRUE
    best_known = max(known_counts.values(), default=0)
    return UNKNOWN if best_known + missing_count >= group_count else FALSE


def _evaluate_required_logic(
    prototype: Mapping[str, Any], slot_states: Mapping[str, str]
) -> tuple[str, dict[str, Any]]:
    logic = prototype.get("required_logic", {})
    components: list[str] = []
    detail: dict[str, Any] = {}
    all_slots = list(logic.get("all", []))
    if all_slots:
        states = [slot_states.get(slot_id, UNKNOWN) for slot_id in all_slots]
        all_state = FALSE if FALSE in states else (TRUE if all(state == TRUE for state in states) else UNKNOWN)
        components.append(all_state)
        detail["all"] = {"slots": all_slots, "states": states, "state": all_state}
    at_least = logic.get("at_least") or {}
    if at_least:
        group = at_least["group"]
        count = int(at_least["count"])
        group_slots = [
            slot["slot_id"] for slot in prototype.get("slots", []) if slot.get("group") == group
        ]
        states = [slot_states.get(slot_id, UNKNOWN) for slot_id in group_slots]
        true_count = states.count(TRUE)
        possible_count = true_count + states.count(UNKNOWN)
        group_state = TRUE if true_count >= count else (FALSE if possible_count < count else UNKNOWN)
        components.append(group_state)
        detail["at_least"] = {
            "group": group,
            "count": count,
            "slots": group_slots,
            "states": states,
            "true_count": true_count,
            "possible_count": possible_count,
            "state": group_state,
        }
    state = FALSE if FALSE in components else (TRUE if components and all(x == TRUE for x in components) else UNKNOWN)
    return state, detail


def align_candidate(
    prototype: Mapping[str, Any],
    atoms: Sequence[Mapping[str, Any]],
    postings_by_atom: Mapping[str, Sequence[Posting]],
) -> tuple[dict[str, Any], dict[str, int]]:
    slots = sorted(prototype.get("slots", []), key=lambda row: str(row["slot_id"]))
    prototype_id = str(prototype["prototype_id"])
    resources: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for atom in atoms:
        resource = _resource_id(atom)
        if not resource:
            raise ValueError("every atom requires atom_id or correlation_id")
        resources[resource].append(atom)
    resource_ids = sorted(resources)
    edge_rows: dict[tuple[int, int], dict[str, Any]] = {}
    weights: list[list[int]] = []
    logic = prototype.get("required_logic", {})
    required_all = set(logic.get("all", []))
    at_least = logic.get("at_least") or {}
    required_group = {
        str(slot["slot_id"])
        for slot in slots
        if at_least and slot.get("group") == at_least.get("group")
    }
    # Truth-feasibility tiers are deliberately independent of card weights and
    # lexical/IDF strength.  One ALL slot outweighs every possible GROUP and
    # supportive assignment; one GROUP slot outweighs all supportive slots.
    # The final deterministic tie term cannot cross a tier boundary.
    slot_count = len(slots)
    resource_count = len(resource_ids)
    support_priority = 1
    group_priority = slot_count + 1
    all_priority = (slot_count + 1) ** 2
    tie_scale = (slot_count + 1) * (resource_count + 1)
    for slot_index, slot in enumerate(slots):
        row: list[int] = []
        for resource_index, resource in enumerate(resource_ids):
            evaluated: list[dict[str, Any]] = []
            for atom in sorted(resources[resource], key=lambda item: str(item.get("atom_id"))):
                atom_postings = [
                    posting
                    for posting in postings_by_atom.get(str(atom.get("atom_id")), ())
                    if posting.prototype_id == prototype_id and posting.slot_id == slot["slot_id"]
                ]
                if not atom_postings:
                    continue
                evaluation = evaluate_edge(atom, prototype, slot)
                posting_strength = max(posting.strength for posting in atom_postings)
                lexical_surface = sorted(
                    atom_postings, key=lambda item: (-item.strength, item.surface, item.kind)
                )[0]
                candidate = {
                    "atom_id": str(atom.get("atom_id")),
                    "resource_id": resource,
                    "state": evaluation["state"],
                    "gates": evaluation["gates"],
                    "posting_surface": lexical_surface.surface,
                    "posting_kind": lexical_surface.kind,
                    "posting_strength": round(posting_strength, 6),
                    "context_id": atom.get("context_id"),
                }
                evaluated.append(candidate)
            if not evaluated:
                row.append(0)
                continue

            # A correlation resource may contain multiple parser views of the
            # same observation.  Do not select T and silently discard F: fold
            # the resource first, then expose one aggregate edge to matching.
            states = {item["state"] for item in evaluated}
            resource_conflict = TRUE in states and FALSE in states
            if resource_conflict:
                aggregate_state = UNKNOWN
            elif TRUE in states:
                aggregate_state = TRUE
            elif FALSE in states:
                aggregate_state = FALSE
            else:
                aggregate_state = UNKNOWN
            representative_pool = (
                evaluated
                if resource_conflict
                else [item for item in evaluated if item["state"] == aggregate_state]
            )
            representative = min(representative_pool, key=lambda item: item["atom_id"])
            edge = dict(representative)
            edge["state"] = aggregate_state
            edge["resource_conflict"] = resource_conflict
            edge["true_atom_ids"] = sorted(
                item["atom_id"] for item in evaluated if item["state"] == TRUE
            )
            edge["false_atom_ids"] = sorted(
                item["atom_id"] for item in evaluated if item["state"] == FALSE
            )
            edge["unknown_atom_ids"] = sorted(
                item["atom_id"] for item in evaluated if item["state"] == UNKNOWN
            )
            edge_rows[(slot_index, resource_index)] = edge
            if aggregate_state == TRUE:
                slot_id = str(slot["slot_id"])
                if slot_id in required_all:
                    priority = all_priority
                elif slot_id in required_group:
                    priority = group_priority
                else:
                    priority = support_priority
                # Deterministic resource order is only a within-tier tie break.
                tie = resource_count - resource_index
                weight = priority * tie_scale + tie
                row.append(weight)
            else:
                row.append(0)
        row.extend([0] * len(slots))  # private dummy column for every slot
        weights.append(row)

    assignment = _hungarian_max(weights) if slots else []
    assigned_by_slot: dict[str, dict[str, Any]] = {}
    used_resources: set[str] = set()
    for slot_index, column in enumerate(assignment):
        if column < 0 or column >= len(resource_ids) or weights[slot_index][column] <= 0:
            continue
        edge = dict(edge_rows[(slot_index, column)])
        slot_id = str(slots[slot_index]["slot_id"])
        assigned_by_slot[slot_id] = edge
        if edge["resource_id"] in used_resources:
            raise AssertionError("one evidence resource filled more than one slot")
        used_resources.add(edge["resource_id"])

    assignment_rows: list[dict[str, Any]] = []
    slot_states: dict[str, str] = {}
    for slot_index, slot in enumerate(slots):
        slot_id = str(slot["slot_id"])
        assigned = assigned_by_slot.get(slot_id)
        observed = [
            edge_rows[(slot_index, resource_index)]
            for resource_index in range(len(resource_ids))
            if (slot_index, resource_index) in edge_rows
        ]
        clinical_false = [row for row in observed if row["state"] == FALSE]
        false_atom_ids = sorted(
            {
                atom_id
                for row in observed
                for atom_id in row.get("false_atom_ids", [])
            }
        )
        unknown_atom_ids = sorted(
            {
                atom_id
                for row in observed
                for atom_id in row.get("unknown_atom_ids", [])
            }
        )
        resource_conflict = any(row.get("resource_conflict") for row in observed)
        if assigned and false_atom_ids:
            slot_state = UNKNOWN  # simultaneous supporting and refuting observations
            conflict = True
        elif assigned:
            slot_state = TRUE
            conflict = False
        elif resource_conflict:
            slot_state = UNKNOWN
            conflict = True
        elif clinical_false:
            slot_state = FALSE
            conflict = False
        else:
            slot_state = UNKNOWN
            conflict = False
        slot_states[slot_id] = slot_state
        assignment_rows.append(
            {
                "slot_id": slot_id,
                "role": slot.get("role"),
                "group": slot.get("group"),
                "slot_state": slot_state,
                "assigned": assigned,
                "conflict": conflict,
                "false_atom_ids": false_atom_ids,
                "unknown_atom_ids": unknown_atom_ids,
                "resource_conflict_ids": sorted(
                    row["resource_id"] for row in observed if row.get("resource_conflict")
                ),
            }
        )

    logic_state, logic_detail = _evaluate_required_logic(prototype, slot_states)
    coherence = _time_coherence(prototype, assignment_rows)
    if logic_state == TRUE and coherence == TRUE:
        verdict = "entailed"
    elif logic_state == FALSE:
        verdict = "contradicted"
    else:
        verdict = "unknown"
    return (
        {
            "prototype_id": prototype_id,
            "target_id": prototype.get("target_id"),
            "label": prototype.get("label"),
            "verdict": verdict,
            "write_action": "assert_phenotype" if verdict == "entailed" else "query_only_abstain",
            "logic_state": logic_state,
            "time_coherence": coherence,
            "required_logic": logic_detail,
            "slot_alignment": assignment_rows,
            "aligned_resource_ids": sorted(used_resources),
            "one_to_one_valid": len(used_resources) == len(assigned_by_slot),
        },
        {
            "alignment_matrix_cells": len(slots) * (len(resource_ids) + len(slots)),
            "alignment_real_cells": len(slots) * len(resource_ids),
            "alignment_dummy_cells": len(slots) * len(slots),
        },
    )


def infer_case(
    case_id: str,
    atoms: Sequence[Mapping[str, Any]],
    prototypes: Sequence[Mapping[str, Any]],
    index: PostingIndex,
) -> dict[str, Any]:
    """Infer from atoms only.  Expected/gold fields are intentionally absent."""

    postings_by_atom: dict[str, list[Posting]] = {}
    candidate_raw: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)
    posting_lookups = 0
    posting_hits = 0
    for atom in atoms:
        atom_id = str(atom.get("atom_id", ""))
        if not atom_id:
            raise ValueError(f"{case_id}: atom without atom_id")
        hits, lookups = index.lookup(atom)
        postings_by_atom[atom_id] = hits
        posting_lookups += lookups
        posting_hits += len(hits)
        resource = _resource_id(atom)
        for hit in hits:
            key = (resource, hit.slot_id)
            candidate_raw[hit.prototype_id][key] = max(
                hit.strength, candidate_raw[hit.prototype_id].get(key, 0.0)
            )
    candidate_scores = {
        prototype_id: round(sum(values.values()), 6)
        for prototype_id, values in candidate_raw.items()
    }
    prototype_by_id = {str(row["prototype_id"]): row for row in prototypes}
    ordered_candidates = sorted(candidate_scores, key=lambda key: (-candidate_scores[key], key))
    alignments: list[dict[str, Any]] = []
    alignment_cells = 0
    alignment_real_cells = 0
    alignment_dummy_cells = 0
    for prototype_id in ordered_candidates:
        alignment, cell_counts = align_candidate(
            prototype_by_id[prototype_id], atoms, postings_by_atom
        )
        alignment["retrieval_score"] = candidate_scores[prototype_id]
        alignments.append(alignment)
        alignment_cells += cell_counts["alignment_matrix_cells"]
        alignment_real_cells += cell_counts["alignment_real_cells"]
        alignment_dummy_cells += cell_counts["alignment_dummy_cells"]
    entailed = [row for row in alignments if row["verdict"] == "entailed"]
    return {
        "case_id": case_id,
        "candidate_order": ordered_candidates,
        "candidates": alignments,
        "asserted_target_ids": sorted(str(row["target_id"]) for row in entailed),
        "abstained": not bool(entailed),
        "mechanics": {
            "atom_count": len(atoms),
            "posting_ngram_lookups": posting_lookups,
            "posting_hits": posting_hits,
            "candidate_count": len(ordered_candidates),
            "alignment_matrix_cells": alignment_cells,
            "alignment_real_cells": alignment_real_cells,
            "alignment_dummy_cells": alignment_dummy_cells,
            "atom_pairs_enumerated": 0,
            "atom_triples_enumerated": 0,
        },
    }


def evaluate_cases(
    cases: Sequence[Mapping[str, Any]], prototypes: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    index = PostingIndex(prototypes)
    rows: list[dict[str, Any]] = []
    verdict_correct = 0
    assertion_set_correct = 0
    by_expected_verdict: Counter[str] = Counter()
    by_expected_correct: Counter[str] = Counter()
    prototype_positive_coverage: Counter[str] = Counter()
    mechanics: Counter[str] = Counter()
    maxima: Counter[str] = Counter()
    for case in cases:
        expected = dict(case.get("expected", {}))
        prediction = infer_case(
            str(case["case_id"]), list(case.get("atoms", [])), prototypes, index
        )
        target = str(expected["prototype_id"])
        candidate = next(
            (row for row in prediction["candidates"] if row["prototype_id"] == target),
            None,
        )
        actual_verdict = candidate["verdict"] if candidate else "not_retrieved"
        correct = actual_verdict == expected["verdict"]
        expected_assertions = sorted(expected.get("asserted_target_ids", []))
        assertion_correct = prediction["asserted_target_ids"] == expected_assertions
        verdict_correct += int(correct)
        assertion_set_correct += int(assertion_correct)
        by_expected_verdict[str(expected["verdict"])] += 1
        by_expected_correct[str(expected["verdict"])] += int(correct)
        if expected["verdict"] == "entailed" and correct:
            prototype_positive_coverage[target] += 1
        for key, value in prediction["mechanics"].items():
            mechanics[key] += int(value)
            maxima[key] = max(maxima[key], int(value))
        rows.append(
            {
                **prediction,
                "expected": expected,
                "expected_target_actual_verdict": actual_verdict,
                "verdict_correct": correct,
                "assertion_set_correct": assertion_correct,
            }
        )
    total = len(cases)
    summary = {
        "schema_version": "phenotype-typed-alignment-summary/1.0",
        "interpretation": "Synthetic mechanics acceptance only; these cases do not estimate clinical accuracy, recall, calibration, or safety.",
        "method": {
            "retrieval": "atomic contiguous-ngram postings -> candidate aggregation",
            "alignment": "maximum-weight one-to-one Hungarian assignment with dummy abstention columns",
            "truth": "six typed T/F/U gates plus prototype required_logic",
            "write_policy": "assert only when entailed; otherwise query-only abstention",
            "weights": (
                "posting IDF affects candidate ordering only; card weights are not "
                "consumed by truth assignment; fixed ALL>GROUP>supportive feasibility "
                "tiers drive Hungarian alignment"
            ),
            "calibration": "none; no learned or gold-tuned threshold",
            "pair_or_triple_enumeration": False,
            "complexity": "O(total atom n-grams + candidate aggregation + sum_c S_c*(A+S_c)*S_c); no O(A^2) or O(A^3) finding construction",
        },
        "case_count": total,
        "verdict_correct": verdict_correct,
        "verdict_accuracy": round(verdict_correct / total, 6) if total else None,
        "assertion_set_correct": assertion_set_correct,
        "assertion_set_accuracy": round(assertion_set_correct / total, 6) if total else None,
        "expected_verdict_counts": dict(sorted(by_expected_verdict.items())),
        "expected_verdict_correct": dict(sorted(by_expected_correct.items())),
        "entailed_prototype_coverage": dict(sorted(prototype_positive_coverage.items())),
        "mechanics_totals": dict(sorted(mechanics.items())),
        "mechanics_maxima": dict(sorted(maxima.items())),
    }
    return rows, summary


def _normalized_item_atom(item: Mapping[str, Any]) -> dict[str, Any]:
    """Losslessly adapt a cached parser item without inventing missing context.

    The cache does not preserve subject, time, polarity, modality, specimen, or
    measurement quality.  Those fields therefore stay absent and force U at the
    validator.  A single parsed measurement is retained only as an addressable
    proposal feature; it cannot authorize truth without the missing gates.
    """

    atom: dict[str, Any] = {
        "atom_id": str(item.get("id") or ""),
        "correlation_id": str(item.get("id") or ""),
        "text": str(item.get("text") or ""),
    }
    normalized = [row for row in item.get("normalized", []) if isinstance(row, Mapping)]
    if len(normalized) == 1:
        row = normalized[0]
        if row.get("test_name") and row.get("value") is not None:
            atom["measurement"] = {
                "name": row.get("test_name"),
                "value": row.get("value"),
                "unit": row.get("unit"),
            }
    return atom


def screen_normalized_cache(
    payload: Mapping[str, Any],
    prototypes: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Proposal-load/safety screen only; the cache has no phenotype target gold."""

    index = PostingIndex(prototypes)
    rows: list[dict[str, Any]] = []
    candidate_counts: Counter[str] = Counter()
    verdict_counts: Counter[str] = Counter()
    n_with_candidates = 0
    n_with_assertions = 0
    n_items = 0
    for case_key, case in sorted((payload.get("cases") or {}).items()):
        atoms = [_normalized_item_atom(item) for item in case.get("items", [])]
        atoms = [atom for atom in atoms if atom["atom_id"] and atom["text"]]
        prediction = infer_case(str(case_key), atoms, prototypes, index)
        n_items += len(atoms)
        n_with_candidates += int(bool(prediction["candidate_order"]))
        n_with_assertions += int(bool(prediction["asserted_target_ids"]))
        candidate_counts.update(prediction["candidate_order"])
        verdict_counts.update(row["verdict"] for row in prediction["candidates"])
        rows.append(
            {
                "case_key": case_key,
                "candidate_order": prediction["candidate_order"],
                "candidate_verdicts": {
                    row["prototype_id"]: row["verdict"]
                    for row in prediction["candidates"]
                },
                "asserted_target_ids": prediction["asserted_target_ids"],
                "mechanics": prediction["mechanics"],
            }
        )
    summary = {
        "n_cases": len(rows),
        "n_items": n_items,
        "n_cases_with_candidates": n_with_candidates,
        "n_cases_with_assertions": n_with_assertions,
        "candidate_case_counts": dict(sorted(candidate_counts.items())),
        "candidate_verdict_counts": dict(sorted(verdict_counts.items())),
        "gold_available": False,
        "interpretation": (
            "Load and fail-closed safety screen only. Missing subject/time/polarity/"
            "modality/specimen/quality fields are not imputed, so candidate retrieval "
            "cannot become a phenotype assertion. Counts are not precision, recall, or FPR."
        ),
    }
    return rows, summary


def _write_outputs(
    out: Path,
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
    cards_path: Path = CARDS,
    cases_path: Path = CASES,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    predictions = out / "case_predictions.jsonl"
    predictions.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    _write_json(out / "summary.json", summary)
    (out / "normalized_cache_screen.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in normalized_rows
        ),
        encoding="utf-8",
    )
    _write_json(
        out / "input_manifest.json",
        {
            "schema_version": "phenotype-typed-alignment-input-manifest/1.0",
            "builder": {
                "path": str(Path(__file__).resolve().relative_to(ROOT)),
                "sha256": _sha256(Path(__file__).resolve()),
            },
            "inputs": [
                {
                    "path": str(cards_path.resolve().relative_to(ROOT)),
                    "sha256": _sha256(cards_path),
                },
                {
                    "path": str(cases_path.resolve().relative_to(ROOT)),
                    "sha256": _sha256(cases_path),
                },
                {
                    "path": str(NORMALIZED_CACHE.relative_to(ROOT)),
                    "sha256": _sha256(NORMALIZED_CACHE),
                },
            ],
            "inference_dependencies": ["python standard library"],
            "network_calls": 0,
            "llm_calls": 0,
        },
    )


def _compare_dirs(expected: Path, actual: Path) -> list[str]:
    names = [
        "case_predictions.jsonl",
        "input_manifest.json",
        "normalized_cache_screen.jsonl",
        "summary.json",
    ]
    return [name for name in names if not (expected / name).exists() or (expected / name).read_bytes() != (actual / name).read_bytes()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, default=CARDS)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="byte-check committed outputs")
    args = parser.parse_args(argv)
    prototypes = load_cards(args.cards)
    payload = _read_json(args.cases)
    cases = payload.get("cases", [])
    normalized_payload = _read_json(NORMALIZED_CACHE)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="phenotype-typed-alignment-") as temporary:
            generated = Path(temporary)
            rows, summary = evaluate_cases(cases, prototypes)
            normalized_rows, normalized_summary = screen_normalized_cache(
                normalized_payload, prototypes
            )
            summary["normalized_cache_screen"] = normalized_summary
            _write_outputs(
                generated, rows, summary, normalized_rows, args.cards, args.cases
            )
            mismatches = _compare_dirs(args.out, generated)
            if mismatches:
                raise RuntimeError(f"committed typed-alignment outputs differ: {mismatches}")
    else:
        rows, summary = evaluate_cases(cases, prototypes)
        normalized_rows, normalized_summary = screen_normalized_cache(
            normalized_payload, prototypes
        )
        summary["normalized_cache_screen"] = normalized_summary
        _write_outputs(args.out, rows, summary, normalized_rows, args.cards, args.cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
