#!/usr/bin/env python3
"""P1 deterministic substrate replay for the counterfactual edge-audit route.

Zero model calls.  Every number here is recomputed from the frozen generator
payloads already committed under ``logs/backbone_v1``, so the only thing that
varies across arms is the substrate policy under test.

``COUNTERFACTUAL_INFERENCE_MECHANISM_TRANSFER_AUDIT.md`` §12 P0 names five
substrate defects and §12 P1 asks for exactly this replay before any
``CF_EDGE_AUDIT_V1`` call is spent.  The defects, as confirmed in code:

1. ``GlobalConceptRegistry._match`` accepts ``na in nb or nb in na`` once both
   normalized names reach six characters, so a composite silently becomes an
   alias of its own parent (DA 709).
2. ``_ingest_generator`` dedupes evidence on the *exact* string
   ``e.raw_span == span``, so case/punctuation variants of one clinical
   proposition each get their own evidence id (MCR 463).
3. ``score()`` then adds ``0.35 * (views - 1)`` and ``0.15 * (axis_nodes - 1)``,
   so provenance multiplicity is priced as if it were independent evidence.
4. ``EvidenceFact`` is constructed with ``raw_span``/``source_view`` only, so
   polarity, epistemic status, modality and reliability are frozen constants and
   temporality does not exist in the schema at all.
5. Collapse3c carries no ``against_fact_ids`` (audited separately).

What this program can and cannot identify, restated so no reader over-claims:

- Identifiable: candidate identity, addressability, deterministic pre-selector
  score and the two-lane frontier under each policy.
- Not identifiable: what the selector would have answered on a frontier it never
  saw.  A recovered candidate is reported as *addressable*, never as *answered*.

The intervention is therefore an ``addressability`` intervention, not a
``conversion`` claim, and the report must keep that wording.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, NamedTuple, Optional

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agentclinic_tree_dx.mosaic import _as_list, _norm  # noqa: E402
from clinical_endpoint import COMPLETE, PARTIAL, ClinicalEndpoint  # noqa: E402
from common import FrozenExactSynonymBridge  # noqa: E402

OUT = ROOT / "analysis/mechanism_v2/results/CF_SUBSTRATE_REPLAY"
MANIFEST = (
    ROOT
    / "analysis/mechanism_v2/results/COUNTERFACTUAL_INFERENCE_RESEARCH/input_manifest.json"
)
BRIDGE = ROOT / "data/knowledge_raw/disease_name_bridge.json"

# `logs/backbone_v1/<dir>` -> the `(family, slice)` pair `ClinicalEndpoint` keys on.
SLICES = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "diagnosisarena_heldout200b": ("da", "d2_heldout200b"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
    "medcasereasoning_200b": ("mcr", "mcr_200b"),
}

# Only the two `mosaic.py` arms are replayable from raw generator payloads.
# Collapse3c runs a different pipeline and is audited by `cf_collapse_direction`.
ARMS = {"Forest": "mosaic_forest_v1", "IMPC": "mosaic_impc_v1"}

MAIN_K = 4
PROTECTED_K = 2
PARENT_REFUND_K = 2

# arm name -> policy flags.  `bridge` and `parent_protect` exist because the
# shippable fix must be measured as it would actually ship: production
# `mosaic.py` runs with `resolver=None`, so a gain that depends on the analysis
# layer's frozen bridge is not a deliverable gain.
class Policy(NamedTuple):
    safe_identity: bool
    normalized_dedup: bool
    provenance_only: bool
    bridge: bool = True
    parent_protect: bool = False


POLICIES: dict[str, Policy] = {
    "B0_observed": Policy(False, False, False),
    "V1_safe_identity": Policy(True, False, False),
    "V1b_exact_only_no_bridge": Policy(True, False, False, bridge=False),
    "V1p_parent_protected": Policy(True, False, False, parent_protect=True),
    "V1bp_exact_parent_protected": Policy(
        True, False, False, bridge=False, parent_protect=True
    ),
    "V2_proposition_dedup": Policy(False, True, False),
    "V3_provenance_only": Policy(False, False, True),
    "VA_all_three": Policy(True, True, True),
}


# --------------------------------------------------------------------------
# faithful re-implementation of the registry under a configurable policy
# --------------------------------------------------------------------------
def _relation(a: str, b: str) -> str:
    """Directed containment relation of ``a`` w.r.t. ``b`` when not equal.

    Deliberately the *same* predicate `mosaic.py::_match` currently folds on and
    `aphhm_c.py::_relation` records on, so the only thing under test is what is
    done with it.
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb or na == nb:
        return ""
    aw, bw = set(na.split()), set(nb.split())
    if len(na) >= 6 and len(nb) >= 6:
        if nb in na or bw < aw:
            return "narrower_than"
        if na in nb or aw < bw:
            return "broader_than"
    return ""


class Fact:
    __slots__ = ("evidence_id", "raw_span", "source_view")

    def __init__(self, evidence_id: str, raw_span: str, source_view: str) -> None:
        self.evidence_id = evidence_id
        self.raw_span = raw_span
        self.source_view = source_view


class Concept:
    __slots__ = (
        "concept_id",
        "preferred_name",
        "aliases",
        "generator_views",
        "axis_nodes",
        "supporting_evidence",
        "contradicting_evidence",
        "protected_reason",
        "score_logit",
        "agent_votes",
        "narrower_than",
        "broader_than",
    )

    def __init__(self, concept_id: str, preferred_name: str) -> None:
        self.concept_id = concept_id
        self.preferred_name = preferred_name
        self.aliases: list[str] = []
        self.generator_views: list[str] = []
        self.axis_nodes: list[str] = []
        self.supporting_evidence: list[str] = []
        self.contradicting_evidence: list[str] = []
        self.protected_reason = ""
        self.score_logit = 0.0
        self.agent_votes = 0
        self.narrower_than: list[str] = []
        self.broader_than: list[str] = []


class Registry:
    """`GlobalConceptRegistry` with the three P0 policies switchable.

    ``safe_identity`` replaces substring containment with exact-or-frozen-synonym
    equivalence.  The frozen bridge is the same artefact `ClinicalEndpoint` keys
    on, and it resolves a full name followed by its own parenthetical initialism,
    so dropping containment does not shatter genuine abbreviation pairs.
    """

    def __init__(
        self,
        *,
        safe_identity: bool,
        provenance_only: bool,
        bridge: Optional[FrozenExactSynonymBridge],
        parent_protect: bool = False,
    ) -> None:
        self.safe_identity = safe_identity
        self.provenance_only = provenance_only
        self.bridge = bridge
        self.parent_protect = parent_protect
        self.concepts: dict[str, Concept] = {}
        self._alias_index: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []
        self._next_id = 1
        # merges that only the substring tier would have made
        self.containment_merges: list[dict[str, str]] = []

    # exposed at module level so the shipped `mosaic.py` and this replay share
    # one definition of the containment predicate
    def _canon(self, name: str) -> str:
        if self.bridge is None:
            return _norm(name)
        return self.bridge.canonical_key(name) or _norm(name)

    def _match(self, a: str, b: str) -> bool:
        if not a or not b:
            return False
        if _norm(a) == _norm(b):
            return True
        if self.safe_identity:
            # exact or frozen synonym only; no substring, no fuzzy tier
            ca, cb = self._canon(a), self._canon(b)
            return bool(ca) and ca == cb
        na, nb = _norm(a), _norm(b)
        return len(na) >= 6 and len(nb) >= 6 and (na in nb or nb in na)

    def _find(self, name: str) -> Optional[str]:
        key = _norm(name)
        if key in self._alias_index:
            return self._alias_index[key]
        for cid, c in self.concepts.items():
            if self._match(name, c.preferred_name):
                return cid
            for al in c.aliases:
                if self._match(name, al):
                    return cid
        return None

    def _containment_only(self, name: str, other: str) -> bool:
        """True when the observed tier would merge but safe identity would not."""
        na, nb = _norm(name), _norm(other)
        if na == nb:
            return False
        if not (len(na) >= 6 and len(nb) >= 6 and (na in nb or nb in na)):
            return False
        ca, cb = self._canon(name), self._canon(other)
        return not (ca and ca == cb)

    def merge_candidate(
        self,
        *,
        name: str,
        view: str,
        support_ids: list[str],
        contradict_ids: list[str],
        protected_reason: str = "",
        axis_node: str = "",
        count_vote: bool = False,
    ) -> str:
        name = str(name or "").strip()
        if not name:
            return ""
        existing = self._find(name)
        if existing:
            c = self.concepts[existing]
            if self._containment_only(name, c.preferred_name):
                self.containment_merges.append(
                    {"absorbed": name, "into": c.preferred_name, "view": view}
                )
            if view not in c.generator_views:
                c.generator_views.append(view)
            if name.lower() != c.preferred_name.lower() and name not in c.aliases:
                c.aliases.append(name)
            for e in support_ids:
                if e not in c.supporting_evidence:
                    c.supporting_evidence.append(e)
            for e in contradict_ids:
                if e not in c.contradicting_evidence:
                    c.contradicting_evidence.append(e)
            if protected_reason and not c.protected_reason:
                c.protected_reason = protected_reason
            if axis_node and axis_node not in c.axis_nodes:
                c.axis_nodes.append(axis_node)
            if count_vote:
                c.agent_votes += 1
            self.events.append(
                {"op": "merge", "concept_id": existing, "name": name, "view": view}
            )
            return existing
        cid = f"C{self._next_id:03d}"
        self._next_id += 1
        c = Concept(cid, name)
        if self.safe_identity:
            # The containment predicate that the observed tier used to fold is
            # reused here to *record* a relation, exactly as Collapse3c does.
            for other in self.concepts.values():
                rel = _relation(name, other.preferred_name)
                if rel == "narrower_than":
                    c.narrower_than.append(other.concept_id)
                    other.broader_than.append(cid)
                elif rel == "broader_than":
                    c.broader_than.append(other.concept_id)
                    other.narrower_than.append(cid)
        c.generator_views = [view]
        c.supporting_evidence = list(support_ids)
        c.contradicting_evidence = list(contradict_ids)
        c.protected_reason = protected_reason or ""
        c.axis_nodes = [axis_node] if axis_node else []
        c.agent_votes = 1 if count_vote else 0
        self.concepts[cid] = c
        self._alias_index[_norm(name)] = cid
        self.events.append({"op": "add", "concept_id": cid, "name": name, "view": view})
        return cid

    def score(self) -> None:
        for c in self.concepts.values():
            z = 1.0 * len(c.supporting_evidence)
            z -= 1.25 * len(c.contradicting_evidence)
            if not self.provenance_only:
                z += 0.35 * max(0, len(c.generator_views) - 1)
                z += 0.15 * max(0, len(c.axis_nodes) - 1)
            if c.protected_reason:
                z += 0.25
            if not c.supporting_evidence:
                z -= 0.5
            c.score_logit = z

    def two_lane_frontier(self) -> list[Concept]:
        live = list(self.concepts.values())
        live.sort(key=lambda c: (-c.score_logit, c.preferred_name.lower()))
        main = live[:MAIN_K]
        main_ids = {c.concept_id for c in main}
        rest = [c for c in live if c.concept_id not in main_ids]
        protected: list[Concept] = []
        for c in rest:
            if c.protected_reason or (
                len(c.supporting_evidence) >= 1 and len(c.generator_views) == 1
            ):
                protected.append(c)
            if len(protected) >= PROTECTED_K:
                break
        for c in rest:
            if len(protected) >= PROTECTED_K:
                break
            if c not in protected:
                protected.append(c)
        out = list(main)
        seen = {c.concept_id for c in out}
        for c in protected:
            if c.concept_id not in seen:
                out.append(c)
                seen.add(c.concept_id)
        if not self.parent_protect:
            return out
        # A jointly admitted parent/child pair descends from one pre-split
        # concept that cost one slot, so charging it two is what evicts an
        # unrelated candidate.  Refund one slot per such pair, capped, and fill
        # from the same score order.  Widening unconditionally is not an option:
        # E5 measured width 4->8 at about -17.68pp clinical-complete.
        # `narrower_than` holds the *broader* concepts, so each relation is
        # already recorded once from the narrower side.  Seating a refunded child
        # can complete a further pair, so grant to a fixpoint under the budget.
        granted = 0
        while granted < PARENT_REFUND_K:
            pairs = {
                frozenset((c.concept_id, broader))
                for c in out
                for broader in c.narrower_than
                if broader in seen
            }
            if len(pairs) <= granted:
                break
            nxt = next((c for c in live if c.concept_id not in seen), None)
            if nxt is None:
                break
            out.append(nxt)
            seen.add(nxt.concept_id)
            granted += 1
        return out


def ingest(
    *,
    registry: Registry,
    evidence: dict[str, Fact],
    raw: Mapping[str, Any],
    view: str,
    eid_prefix: str,
    normalized_dedup: bool,
    count_vote: bool = False,
) -> None:
    index: dict[str, str] = {}
    if normalized_dedup:
        for eid, fact in evidence.items():
            index.setdefault(_norm(fact.raw_span), eid)

    def lookup(span: str) -> Optional[str]:
        if normalized_dedup:
            return index.get(_norm(span))
        return next(
            (e.evidence_id for e in evidence.values() if e.raw_span == span), None
        )

    def add(span: str) -> str:
        eid = f"{eid_prefix}E{len(evidence)+1:03d}"
        evidence[eid] = Fact(eid, span, view)
        if normalized_dedup:
            index.setdefault(_norm(span), eid)
        return eid

    for span in _as_list(raw.get("key_evidence_spans")):
        span = str(span or "").strip()
        if not span:
            continue
        if lookup(span) is None:
            add(span)

    for item in _as_list(raw.get("candidates")):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        support_ids: list[str] = []
        for span in _as_list(item.get("support_spans")):
            span = str(span or "").strip()
            if not span:
                continue
            hit = lookup(span)
            support_ids.append(hit if hit is not None else add(span))
        contradict_ids: list[str] = []
        for span in _as_list(item.get("contradict_spans")):
            span = str(span or "").strip()
            if not span:
                continue
            hit = lookup(span)
            contradict_ids.append(hit if hit is not None else add(span))
        registry.merge_candidate(
            name=name,
            view=view,
            support_ids=support_ids,
            contradict_ids=contradict_ids,
            protected_reason=str(item.get("protected_reason") or ""),
            axis_node=str(item.get("axis_node") or ""),
            count_vote=count_vote,
        )


FOREST_VIEWS = ("ax_syndrome", "ax_mechanism", "ax_modality")
IMPC_VIEWS = ("D1", "D2", "D3")


def replay(
    stages: Mapping[str, Any],
    arm: str,
    policy: Policy,
    bridge: FrozenExactSynonymBridge,
) -> tuple[Registry, dict[str, Fact], list[Concept]]:
    normalized_dedup = policy.normalized_dedup
    registry = Registry(
        safe_identity=policy.safe_identity,
        provenance_only=policy.provenance_only,
        bridge=bridge if (policy.safe_identity and policy.bridge) else None,
        parent_protect=policy.parent_protect,
    )
    evidence: dict[str, Fact] = {}
    if arm == "Forest":
        for view in FOREST_VIEWS:
            ingest(
                registry=registry,
                evidence=evidence,
                raw=stages.get(view) or {},
                view=view,
                eid_prefix=view.upper()[:4],
                normalized_dedup=normalized_dedup,
            )
        registry.score()
        registry.two_lane_frontier()
        if "a1" in stages:
            ingest(
                registry=registry,
                evidence=evidence,
                raw=stages.get("a1") or {},
                view="a1",
                eid_prefix="A1",
                normalized_dedup=normalized_dedup,
            )
            registry.score()
    else:
        for view in IMPC_VIEWS:
            ingest(
                registry=registry,
                evidence=evidence,
                raw=stages.get(view) or {},
                view=view,
                eid_prefix=view,
                normalized_dedup=normalized_dedup,
                count_vote=True,
            )
        registry.score()
    return registry, evidence, registry.two_lane_frontier()


# --------------------------------------------------------------------------
# stage 1: provenance + fidelity
# --------------------------------------------------------------------------
def _blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def verify_inputs() -> dict[str, Any]:
    """Content-level check against the frozen 2,400-file manifest.

    The audit's source commit `726e7611...` lives in a different clone, so the
    git-blob comparison is done against the manifest's recorded hashes rather
    than against a local commit.  That is a strictly stronger check of the bytes
    and a strictly weaker check of the history, and the report says so.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    identical = missing = differs = 0
    for entry in manifest["entries"]:
        path = ROOT / entry["path"]
        if not path.is_file():
            missing += 1
        elif _blob(path) == entry["git_blob_sha1"]:
            identical += 1
        else:
            differs += 1
    if missing or differs:
        raise SystemExit(
            f"substrate drifted from manifest: missing={missing} differs={differs}"
        )
    return {
        "manifest_source_commit": manifest["source_commit"],
        "manifest_entries": len(manifest["entries"]),
        "identical": identical,
        "verification": "manifest_blob_sha1_content_match",
        "note": "source commit not present in this clone; bytes verified, history not",
    }


def _observed(stages: Mapping[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    return (
        list(stages.get("evidence") or []),
        list(stages.get("registry") or []),
        list(stages.get("frontier_final") or []),
    )


def fidelity(rows: list[dict[str, Any]], bridge: FrozenExactSynonymBridge) -> dict[str, Any]:
    """B0 must reproduce the logged substrate exactly, or nothing below is valid."""
    checked = 0
    mismatch: list[dict[str, Any]] = []
    for row in rows:
        stages = row["stages"]
        reg, ev, frontier = replay(stages, row["_arm"], POLICIES["B0_observed"], bridge)
        obs_ev, obs_reg, obs_frontier = _observed(stages)
        problems = []
        if [f.raw_span for f in ev.values()] != [e.get("raw_span") for e in obs_ev]:
            problems.append("evidence_spans")
        if list(ev) != [str(e.get("evidence_id")) for e in obs_ev]:
            problems.append("evidence_ids")
        got = [
            (
                c.concept_id,
                c.preferred_name,
                tuple(c.aliases),
                tuple(c.generator_views),
                tuple(c.axis_nodes),
                tuple(c.supporting_evidence),
                tuple(c.contradicting_evidence),
                round(c.score_logit, 6),
            )
            for c in reg.concepts.values()
        ]
        want = [
            (
                str(c.get("concept_id")),
                str(c.get("preferred_name")),
                tuple(c.get("aliases") or []),
                tuple(c.get("generator_views") or []),
                tuple(c.get("axis_nodes") or []),
                tuple(c.get("supporting_evidence") or []),
                tuple(c.get("contradicting_evidence") or []),
                round(float(c.get("score_logit") or 0.0), 6),
            )
            for c in obs_reg
        ]
        if got != want:
            problems.append("registry")
        if [c.concept_id for c in frontier] != [
            str(c.get("concept_id")) for c in obs_frontier
        ]:
            problems.append("frontier")
        checked += 1
        if problems:
            mismatch.append(
                {
                    "arm": row["_arm"],
                    "dataset": row["_dataset"],
                    "case_id": row["_cid"],
                    "fields": problems,
                }
            )
    return {
        "cases_checked": checked,
        "exact": checked - len(mismatch),
        "mismatched": len(mismatch),
        "examples": mismatch[:10],
    }


# --------------------------------------------------------------------------
# stage 2: policy replay + addressability accounting
# --------------------------------------------------------------------------
def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset, (family, sl) in SLICES.items():
        for arm, arm_dir in ARMS.items():
            base = ROOT / "logs/backbone_v1" / dataset / arm_dir / "case_stages"
            for path in sorted(base.glob("*.json")):
                doc = json.loads(path.read_text(encoding="utf-8"))
                doc["_arm"] = arm
                doc["_dataset"] = dataset
                doc["_family"] = family
                doc["_slice"] = sl
                doc["_cid"] = str(doc.get("source_id") or doc.get("case_id") or path.stem)
                rows.append(doc)
    return rows


def _rel(clinical: ClinicalEndpoint, row: Mapping[str, Any], label: str) -> Optional[str]:
    return clinical.relation(row["_family"], row["_slice"], row["_cid"], label)


def _first_complete(
    clinical: ClinicalEndpoint, row: Mapping[str, Any], labels: Iterable[str]
) -> Optional[str]:
    for label in labels:
        if _rel(clinical, row, label) == COMPLETE:
            return label
    return None


def analyse(
    rows: list[dict[str, Any]], clinical: ClinicalEndpoint, bridge: FrozenExactSynonymBridge
) -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    recovered_examples: list[dict[str, Any]] = []

    for arm in ARMS:
        arm_rows = [r for r in rows if r["_arm"] == arm]
        base: dict[str, Any] = {}
        for row in arm_rows:
            reg, ev, frontier = replay(row["stages"], arm, POLICIES["B0_observed"], bridge)
            base[row["_cid"] + "|" + row["_dataset"]] = {
                "addressable": [c.preferred_name for c in frontier],
                "pool_names": [c.preferred_name for c in reg.concepts.values()],
                "aliases": [a for c in reg.concepts.values() for a in c.aliases],
                "n_candidates": len(reg.concepts),
                "n_evidence": len(ev),
                "containment_merges": list(reg.containment_merges),
            }

        # B0 addressable-complete status per case, for the paired decomposition
        b0_complete = {
            row["_cid"] + "|" + row["_dataset"]: bool(
                _first_complete(clinical, row, base[row["_cid"] + "|" + row["_dataset"]]["addressable"])
            )
            for row in arm_rows
        }

        policies: dict[str, Any] = {}
        for policy_name, policy in POLICIES.items():
            n_cand: list[int] = []
            n_ev: list[int] = []
            n_frontier: list[int] = []
            addressable_complete = 0
            pool_complete = 0
            alias_masked = 0
            frontier_changed = 0
            top1_changed = 0
            rescue = harm = 0
            rel_counter: Counter[str] = Counter()
            for row in arm_rows:
                key = row["_cid"] + "|" + row["_dataset"]
                b = base[key]
                reg, ev, frontier = replay(row["stages"], arm, policy, bridge)
                names = [c.preferred_name for c in frontier]
                pool = [c.preferred_name for c in reg.concepts.values()]
                n_cand.append(len(reg.concepts))
                n_ev.append(len(ev))
                n_frontier.append(len(frontier))
                if names != b["addressable"]:
                    frontier_changed += 1
                if names[:1] != b["addressable"][:1]:
                    top1_changed += 1
                hit = _first_complete(clinical, row, names)
                if hit:
                    addressable_complete += 1
                    rel_counter[COMPLETE] += 1
                # A net gain that is really +20/-4 is a different mechanism from
                # a clean +16, so the paired cells are reported, not just the net.
                if hit and not b0_complete[key]:
                    rescue += 1
                    if policy_name == "V1_safe_identity" and len(recovered_examples) < 60:
                        recovered_examples.append(
                            {
                                "kind": "rescue",
                                "arm": arm,
                                "dataset": row["_dataset"],
                                "case_id": row["_cid"],
                                "recovered_label": hit,
                                "observed_frontier": b["addressable"],
                                "policy_frontier": names,
                                "containment_merges": b["containment_merges"],
                            }
                        )
                if b0_complete[key] and not hit:
                    harm += 1
                    if policy_name == "V1_safe_identity" and len(recovered_examples) < 60:
                        recovered_examples.append(
                            {
                                "kind": "harm",
                                "arm": arm,
                                "dataset": row["_dataset"],
                                "case_id": row["_cid"],
                                "observed_frontier": b["addressable"],
                                "policy_frontier": names,
                            }
                        )
                pool_hit = _first_complete(clinical, row, pool)
                if pool_hit:
                    pool_complete += 1
                # a complete object present only as an alias is unreachable:
                # the selector shortlist is built from preferred_name alone.
                if not hit:
                    masked = _first_complete(
                        clinical,
                        row,
                        [a for c in reg.concepts.values() for a in c.aliases],
                    )
                    if masked:
                        alias_masked += 1
            n = len(arm_rows)
            policies[policy_name] = {
                "cases": n,
                "mean_candidates": sum(n_cand) / n,
                "mean_evidence": sum(n_ev) / n,
                "mean_frontier": sum(n_frontier) / n,
                "addressable_complete_cases": addressable_complete,
                "addressable_complete_rate": addressable_complete / n,
                "pool_complete_cases": pool_complete,
                "alias_masked_complete_cases": alias_masked,
                "frontier_changed_vs_b0": frontier_changed,
                "top1_changed_vs_b0": top1_changed,
                "addressable_complete_rescue": rescue,
                "addressable_complete_harm": harm,
                "addressable_complete_net": rescue - harm,
            }
        # Where a rescued object lands decides whether P2 is worth any call: a
        # complete candidate admitted at the bottom of a six-slot frontier is
        # addressable but may still be unreachable in practice.  The eviction
        # column is the harm mechanism, since splitting raises candidate count
        # against a fixed frontier width.
        rescue_rank: Counter[int] = Counter()
        parent_retained = 0
        evicted_total = 0
        rescue_n = 0
        for row in arm_rows:
            key = row["_cid"] + "|" + row["_dataset"]
            if b0_complete[key]:
                continue
            reg, _ev, frontier = replay(row["stages"], arm, POLICIES["V1_safe_identity"], bridge)
            names = [c.preferred_name for c in frontier]
            hit = _first_complete(clinical, row, names)
            if not hit:
                continue
            rescue_n += 1
            rescue_rank[names.index(hit) + 1] += 1
            merges = base[key]["containment_merges"]
            parents = {m["into"] for m in merges if m["absorbed"] == hit}
            if parents and parents <= set(names):
                parent_retained += 1
            evicted_total += len(set(base[key]["addressable"]) - set(names))
        per_arm[arm] = {
            "policies": policies,
            "v1_rescue_detail": {
                "rescued_cases": rescue_n,
                "frontier_rank_of_rescued_label": dict(sorted(rescue_rank.items())),
                "bare_parent_also_retained": parent_retained,
                "b0_members_evicted_total": evicted_total,
            },
            "containment_merges_total": sum(
                len(v["containment_merges"]) for v in base.values()
            ),
            "cases_with_containment_merge": sum(
                1 for v in base.values() if v["containment_merges"]
            ),
        }

    return {"arms": per_arm, "v1_paired_examples": recovered_examples}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage", choices=("verify", "replay"), default="verify"
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    provenance = verify_inputs()
    bridge = FrozenExactSynonymBridge(BRIDGE)
    rows = load_rows()
    if len(rows) != 1600:
        raise SystemExit(f"expected 1600 mosaic stages, found {len(rows)}")

    fid = fidelity(rows, bridge)
    doc: dict[str, Any] = {
        "schema_version": "cf-substrate-replay-v1",
        "model_calls": 0,
        "provenance": provenance,
        "bridge_sha256": bridge.sha256,
        "policies": {k: v._asdict() for k, v in POLICIES.items()},
        "fidelity": fid,
    }
    if fid["mismatched"]:
        (OUT / "verify.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise SystemExit(
            f"B0 replay is not faithful ({fid['mismatched']}/{fid['cases_checked']}); "
            "downstream policy arms would be uninterpretable"
        )

    if args.stage == "verify":
        (OUT / "verify.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return

    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    doc["clinical_endpoint"] = clinical.audit()
    doc["analysis"] = analyse(rows, clinical, bridge)
    doc["identifiability"] = [
        "Addressability, deterministic score and frontier membership are identifiable.",
        "Selector responses on an unobserved frontier are not identifiable; a recovered candidate is addressable, not answered.",
        "Clinical relations are three-model panel sensitivity on a reused 800-case development set, not human root truth.",
    ]
    (OUT / "replay.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(doc["analysis"]["arms"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
