#!/usr/bin/env python3
"""Build a provenance-first audit of sources for phenotype prototype overlays.

This is deliberately an extraction *candidate* builder, not a medical relation
extractor.  It keeps MedlinePlus relation-bearing sentences, Orphadata
disease--HPO postings, and DisMech evidence records in separate lanes.  No lane
is allowed to turn co-occurrence or a disease association into a phenotype
definition.

The script makes no network or LLM calls.  Inputs must be frozen local files.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import zipfile
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEDLINEPLUS = (
    ROOT
    / "data"
    / "knowledge_raw"
    / "phenotype_overlay_sources"
    / "medlineplus"
    / "mplus_topics_compressed_2026-08-25.zip"
)
DEFAULT_ORPHADATA = (
    ROOT
    / "data"
    / "knowledge_raw"
    / "phenotype_overlay_sources"
    / "orphadata"
    / "en_product4_2026-07.xml.gz"
)
DEFAULT_HOOM = (
    ROOT
    / "data"
    / "knowledge_raw"
    / "phenotype_overlay_sources"
    / "hoom"
    / "hoom_orphanet_2.6.zip"
)
DEFAULT_CARDS = ROOT / "data" / "knowledge_raw" / "phenotype_prototype_cards_v2.json"
DISMECH_COMMIT = "93a6b51f5821868fd364b51010424e41045f2b5e"
DEFAULT_DISMECH = (
    ROOT
    / "data"
    / "knowledge_raw"
    / "phenotype_overlay_sources"
    / "dismech"
    / DISMECH_COMMIT
    / "kb"
    / "modules"
)
DEFAULT_OUT = (
    ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "PHENOTYPE_OVERLAY_SOURCE_AUDIT"
)


RELATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "DEFINITION_CANDIDATE",
        re.compile(
            r"\b(?:is|are|was|were)\s+(?:clinically\s+)?(?:defined|characterized)\s+(?:as|by)\b|"
            r"\bdefinition\s+(?:is|includes?)\b",
            re.I,
        ),
    ),
    (
        "COMPONENT_CANDIDATE",
        re.compile(
            r"\b(?:consists?|comprises?|is composed)\s+(?:of\s+)?\b|"
            r"\b(?:triad|tetrad|constellation)\s+of\b",
            re.I,
        ),
    ),
    (
        "MANIFESTATION_CANDIDATE",
        re.compile(
            r"\b(?:signs?|symptoms?|features?|manifestations?)\s+"
            r"(?:can\s+|may\s+|often\s+|usually\s+)?(?:include|are|consist of)\b|"
            r"\b(?:common|typical|major)\s+(?:signs?|symptoms?|features?|manifestations?)\b",
            re.I,
        ),
    ),
    (
        "MEASUREMENT_CANDIDATE",
        re.compile(
            r"\b(?:diagnos(?:is|ed)|test result|level|measurement)\s+"
            r"(?:is|requires?|includes?|shows?)\b",
            re.I,
        ),
    ),
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_orphadata_content(path: Path) -> str:
    """Hash the XML bytes independently of the repository compression wrapper."""
    digest = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _surface(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _html_text(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(html.unescape(raw or ""))
    return re.sub(r"\s+", " ", parser.text()).strip()


def _sentences(text: str) -> list[str]:
    # MedlinePlus summaries are short patient-facing prose.  A conservative
    # punctuation split is preferable to adding a model dependency.
    return [
        row.strip()
        for row in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        if 20 <= len(row.strip()) <= 1200
    ]


def _target_catalog(cards: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for prototype in cards["prototypes"]:
        rows.append(
            {
                "prototype_id": prototype["prototype_id"],
                "target_id": prototype["target_id"],
                "label": prototype["label"],
                "aliases": sorted(
                    {prototype["label"], *prototype.get("aliases", [])},
                    key=str.casefold,
                ),
                "ontology_anchors": prototype.get("ontology_anchors", []),
                "ontology_anchor_relation": prototype.get(
                    "ontology_anchor_relation", "unspecified"
                ),
            }
        )
    return rows


def audit_medlineplus(
    archive: Path, targets: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    relation_rows: list[dict[str, Any]] = []
    target_hits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    relation_counts: Counter[str] = Counter()
    n_topics = 0
    n_english = 0
    generated_at: str | None = None

    with zipfile.ZipFile(archive) as bundle:
        xml_names = sorted(name for name in bundle.namelist() if name.endswith(".xml"))
        if len(xml_names) != 1:
            raise ValueError(f"expected one XML member in {archive}, found {xml_names}")
        with bundle.open(xml_names[0]) as stream:
            for event, element in ET.iterparse(stream, events=("start", "end")):
                if event == "start" and element.tag == "health-topics":
                    generated_at = element.attrib.get("date-generated")
                    continue
                if event != "end" or element.tag != "health-topic":
                    continue
                n_topics += 1
                if element.attrib.get("language") != "English":
                    element.clear()
                    continue
                n_english += 1
                title = element.attrib.get("title", "")
                topic_id = element.attrib.get("id")
                url = element.attrib.get("url")
                aliases = [
                    (node.text or "").strip()
                    for node in element.findall("also-called")
                    if (node.text or "").strip()
                ]
                aliases.extend(
                    (node.text or "").strip()
                    for node in element.findall("see-reference")
                    if (node.text or "").strip()
                )
                summary = _html_text(element.findtext("full-summary") or "")
                searchable = _surface(" ".join([title, *aliases, summary]))
                for target in targets:
                    matched = [
                        alias
                        for alias in target["aliases"]
                        if _surface(alias) and _surface(alias) in searchable
                    ]
                    if matched:
                        target_hits[target["prototype_id"]].append(
                            {
                                "topic_id": topic_id,
                                "title": title,
                                "url": url,
                                "matched_aliases": sorted(set(matched), key=str.casefold),
                                "match_scope": "title_alias_or_public_domain_summary",
                            }
                        )
                for index, sentence in enumerate(_sentences(summary)):
                    kinds = [name for name, pattern in RELATION_PATTERNS if pattern.search(sentence)]
                    if not kinds:
                        continue
                    for kind in kinds:
                        relation_counts[kind] += 1
                    relation_rows.append(
                        {
                            "source": "MedlinePlus health-topic full-summary",
                            "topic_id": topic_id,
                            "topic_title": title,
                            "topic_url": url,
                            "sentence_index": index,
                            "candidate_relation_types": kinds,
                            "sentence": sentence,
                            "edge_status": "unlinked_candidate_span",
                            "write_policy": "query-only pending entity linking and relation review",
                        }
                    )
                element.clear()

    summary = {
        "generated_at": generated_at,
        "n_topics_all_languages": n_topics,
        "n_topics_english": n_english,
        "n_relation_candidate_sentences": len(relation_rows),
        "relation_type_counts": dict(sorted(relation_counts.items())),
        "target_mentions": {
            target["prototype_id"]: {
                "n_topics": len(target_hits[target["prototype_id"]]),
                "topics": target_hits[target["prototype_id"]][:20],
            }
            for target in targets
        },
        "content_boundary": (
            "Only health-topic metadata and full-summary text are inspected. "
            "Third-party <site> pages and descriptions are excluded. Relation spans "
            "are candidates, not graph edges."
        ),
    }
    return summary, relation_rows


def _child_text(element: ET.Element, path: str) -> str | None:
    node = element.find(path)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def audit_orphadata(
    xml_path: Path, targets: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    target_by_hpo: dict[str, set[str]] = defaultdict(set)
    for target in targets:
        for hpo_id in target["ontology_anchors"]:
            target_by_hpo[hpo_id].add(target["prototype_id"])

    postings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    n_disorders = 0
    n_associations = 0
    unique_hpo: set[str] = set()
    header: dict[str, Any] = {}
    opener = gzip.open if xml_path.suffix == ".gz" else open
    with opener(xml_path, "rb") as stream:
        for event, element in ET.iterparse(stream, events=("start", "end")):
            if event == "start" and element.tag == "JDBOR" and not header:
                header = dict(element.attrib)
                continue
            if event != "end" or element.tag != "HPODisorderSetStatus":
                continue
            disorder = element.find("Disorder")
            if disorder is None:
                element.clear()
                continue
            n_disorders += 1
            orpha_code = _child_text(disorder, "OrphaCode")
            name = _child_text(disorder, "Name")
            disorder_type = _child_text(disorder, "DisorderType/Name")
            disorder_group = _child_text(disorder, "DisorderGroup/Name")
            for association in disorder.findall(
                "HPODisorderAssociationList/HPODisorderAssociation"
            ):
                n_associations += 1
                hpo_id = _child_text(association, "HPO/HPOId")
                if not hpo_id:
                    continue
                unique_hpo.add(hpo_id)
                for prototype_id in target_by_hpo.get(hpo_id, set()):
                    postings[prototype_id].append(
                        {
                            "orpha_code": orpha_code,
                            "disorder_name": name,
                            "disorder_type": disorder_type,
                            "disorder_group": disorder_group,
                            "hpo_id": hpo_id,
                            "hpo_term": _child_text(association, "HPO/HPOTerm"),
                            "frequency": _child_text(
                                association, "HPOFrequency/Name"
                            ),
                            "diagnostic_criterion": _child_text(
                                association, "DiagnosticCriteria/Name"
                            ),
                        }
                    )
            element.clear()

    summary = {
        "header": header,
        "n_disorders": n_disorders,
        "n_associations": n_associations,
        "n_unique_hpo_terms": len(unique_hpo),
        "target_posting_counts": {
            target["prototype_id"]: len(postings[target["prototype_id"]])
            for target in targets
        },
        "target_diagnostic_criterion_counts": {
            target["prototype_id"]: sum(
                bool(row.get("diagnostic_criterion"))
                for row in postings[target["prototype_id"]]
            )
            for target in targets
        },
        "role": (
            "Downstream phenotype-to-rare-disease postings and frequency cross-check. "
            "Disease--HPO association is not a phenotype composition or entailment edge."
        ),
    }
    return summary, dict(postings)


def audit_hoom(
    archive: Path, targets: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Stream HOOM's OWL association axioms without loading the 207 MB XML."""
    target_by_hpo: dict[str, set[str]] = defaultdict(set)
    for target in targets:
        for hpo_id in target["ontology_anchors"]:
            target_by_hpo[hpo_id].add(target["prototype_id"])

    postings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    n_associations = 0
    disorders: set[str] = set()
    dc_counts: Counter[str] = Counter()
    freq_counts: Counter[str] = Counter()
    modified: str | None = None
    version: str | None = None

    def iri(node: ET.Element | None) -> str | None:
        if node is None:
            return None
        return node.attrib.get("IRI") or node.attrib.get("abbreviatedIRI")

    with zipfile.ZipFile(archive) as bundle:
        members = sorted(name for name in bundle.namelist() if name.endswith(".owl"))
        if len(members) != 1:
            raise ValueError(f"expected one OWL member in {archive}, found {members}")
        with bundle.open(members[0]) as stream:
            for event, element in ET.iterparse(stream, events=("end",)):
                local = element.tag.rsplit("}", 1)[-1]
                if local == "Annotation" and (modified is None or version is None):
                    prop = next(
                        (
                            child
                            for child in element
                            if child.tag.rsplit("}", 1)[-1] == "AnnotationProperty"
                        ),
                        None,
                    )
                    literal = next(
                        (
                            child.text
                            for child in element
                            if child.tag.rsplit("}", 1)[-1] == "Literal"
                        ),
                        None,
                    )
                    prop_iri = iri(prop)
                    if prop_iri == "terms:modified":
                        modified = literal
                    elif prop_iri == "owl:versionInfo":
                        version = literal
                    element.clear()
                    continue
                if local != "EquivalentClasses":
                    continue
                direct_classes = [
                    child
                    for child in element
                    if child.tag.rsplit("}", 1)[-1] == "Class"
                ]
                association_iri = next(
                    (
                        iri(child)
                        for child in direct_classes
                        if (iri(child) or "").startswith("#Orpha:")
                        and "_HP:" in (iri(child) or "")
                    ),
                    None,
                )
                if not association_iri:
                    element.clear()
                    continue

                relations: dict[str, list[str]] = defaultdict(list)
                for relation in element.iter():
                    if relation.tag.rsplit("}", 1)[-1] != "ObjectSomeValuesFrom":
                        continue
                    children = list(relation)
                    if len(children) < 2:
                        continue
                    prop_iri = iri(children[0])
                    value_iri = iri(children[1])
                    if prop_iri and value_iri:
                        relations[prop_iri].append(value_iri)

                hpo_values = relations.get(
                    "http://purl.org/oban/association_has_object", []
                )
                disorder_values = relations.get(
                    "http://purl.org/oban/association_has_subject", []
                )
                if not hpo_values or not disorder_values:
                    element.clear()
                    continue
                hpo_id = hpo_values[0].rsplit("/", 1)[-1].replace("HP_", "HP:")
                disorder_id = disorder_values[0].rsplit("/", 1)[-1]
                frequency = (relations.get("#has_frequency") or [None])[0]
                frequency = frequency.lstrip("#") if frequency else None
                dc_attributes = [
                    value.lstrip("#")
                    for value in relations.get("#has_DC_attribute", [])
                ]
                n_associations += 1
                disorders.add(disorder_id)
                if frequency:
                    freq_counts[frequency] += 1
                dc_counts.update(dc_attributes)
                for prototype_id in target_by_hpo.get(hpo_id, set()):
                    postings[prototype_id].append(
                        {
                            "association_iri": association_iri,
                            "orpha_id": disorder_id,
                            "hpo_id": hpo_id,
                            "frequency_class": frequency,
                            "diagnostic_criterion_attributes": dc_attributes,
                        }
                    )
                element.clear()

    summary = {
        "version": version,
        "modified": modified,
        "n_associations": n_associations,
        "n_disorders": len(disorders),
        "frequency_counts": dict(sorted(freq_counts.items())),
        "diagnostic_criterion_attribute_counts": dict(sorted(dc_counts.items())),
        "target_posting_counts": {
            target["prototype_id"]: len(postings[target["prototype_id"]])
            for target in targets
        },
        "target_diagnostic_criterion_counts": {
            target["prototype_id"]: sum(
                bool(row["diagnostic_criterion_attributes"])
                for row in postings[target["prototype_id"]]
            )
            for target in targets
        },
        "role": (
            "Qualified rare-disease--HPO postings with frequency and occasional "
            "diagnostic-criterion attributes. These remain disease associations, "
            "not definitions of how component findings entail a phenotype target."
        ),
    }
    return summary, dict(postings)


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def audit_dismech(
    module_dir: Path, targets: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    modules = sorted(module_dir.glob("*.yaml"))
    for path in modules:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in _walk_dicts(payload):
            evidence = node.get("evidence")
            if not isinstance(evidence, list):
                continue
            node_text = " ".join(
                str(node.get(key, "")) for key in ("name", "description")
            )
            for item in evidence:
                if not isinstance(item, dict):
                    continue
                evidence_text = " ".join(
                    str(item.get(key, ""))
                    for key in ("reference_title", "snippet", "explanation")
                )
                searchable = _surface(node_text + " " + evidence_text)
                matched_targets = [
                    target
                    for target in targets
                    if any(_surface(alias) in searchable for alias in target["aliases"])
                ]
                for target in matched_targets:
                    rows.append(
                        {
                            "prototype_id": target["prototype_id"],
                            "module": path.name,
                            "node_name": node.get("name"),
                            "node_role": node.get("role"),
                            "reference": item.get("reference"),
                            "reference_title": item.get("reference_title"),
                            "supports": item.get("supports"),
                            "evidence_source": item.get("evidence_source"),
                            "snippet": item.get("snippet"),
                            "edge_status": "source_candidate_only",
                            "warning": (
                                "DisMech validates citation existence and exact snippets; "
                                "that is not clinical evidence-strength appraisal."
                            ),
                        }
                    )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (row["prototype_id"], row["module"], row["reference"], row["snippet"])
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return (
        {
            "commit": DISMECH_COMMIT,
            "modules": [path.name for path in modules],
            "n_target_evidence_candidates": len(deduped),
            "target_counts": dict(Counter(row["prototype_id"] for row in deduped)),
            "role": "Mechanism/coherence and source discovery only; never activation authority.",
        },
        deduped,
    )


def run(
    medlineplus: Path,
    orphadata: Path,
    hoom: Path,
    cards_path: Path,
    dismech_dir: Path,
    output: Path,
) -> dict[str, Any]:
    for path in (medlineplus, orphadata, hoom, cards_path):
        if not path.exists():
            raise FileNotFoundError(path)
    if not dismech_dir.is_dir():
        raise FileNotFoundError(dismech_dir)

    cards = _read_json(cards_path)
    targets = _target_catalog(cards)
    medlineplus_summary, medlineplus_rows = audit_medlineplus(medlineplus, targets)
    orphadata_summary, orphadata_postings = audit_orphadata(orphadata, targets)
    hoom_summary, hoom_postings = audit_hoom(hoom, targets)
    dismech_summary, dismech_rows = audit_dismech(dismech_dir, targets)

    output.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output / "medlineplus_relation_candidates.jsonl", medlineplus_rows)
    _write_json(output / "orphadata_target_postings.json", orphadata_postings)
    _write_json(output / "hoom_target_postings.json", hoom_postings)
    _write_json(output / "dismech_target_evidence_candidates.json", dismech_rows)

    manifest = {
        "schema_version": "phenotype-overlay-source-ledger/1.0",
        # A frozen source ledger must be byte-reproducible.  This is an as-of
        # date, not a fabricated wall-clock build timestamp; per-source release
        # timestamps and hashes below carry the exact temporal provenance.
        "ledger_date": "2026-08-25",
        "network_calls_during_build": 0,
        "new_llm_calls": 0,
        "builder": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": _sha256(Path(__file__).resolve()),
            "python_dependency": "PyYAML>=6.0",
        },
        "sources": {
            "medlineplus": {
                "path": str(medlineplus.relative_to(ROOT)),
                "sha256": _sha256(medlineplus),
                "source_url": "https://medlineplus.gov/xml/mplus_topics_compressed_2026-08-25.zip",
                "landing_page": "https://medlineplus.gov/xml.html",
                "license_boundary": (
                    "NLM MedlinePlus health-topic summaries are public-domain material; "
                    "third-party linked pages are excluded from extraction. Attribution retained."
                ),
            },
            "orphadata": {
                "path": str(orphadata.relative_to(ROOT)),
                "stored_sha256": _sha256(orphadata),
                "xml_content_sha256": _sha256_orphadata_content(orphadata),
                "source_url": "https://www.orphadata.com/data/xml/en_product4.xml",
                "landing_page": "https://sciences.orphadata.com/phenotypes/",
                "license": "CC-BY-4.0",
            },
            "hoom": {
                "path": str(hoom.relative_to(ROOT)),
                "sha256": _sha256(hoom),
                "source_url": "https://www.orphadata.com/data/ontologies/hoom/hoom_orphanet_2.6.zip",
                "landing_page": "https://sciences.orphadata.com/hoom/",
                "version": "2.6",
                "license": "CC-BY-4.0",
            },
            "dismech": {
                "path": str(dismech_dir.relative_to(ROOT)),
                "commit": DISMECH_COMMIT,
                "source_url": f"https://github.com/monarch-initiative/dismech/tree/{DISMECH_COMMIT}",
                "content_license": "CC-BY-4.0",
                "code_license": "BSD-3-Clause",
                "module_sha256": {
                    path.name: _sha256(path) for path in sorted(dismech_dir.glob("*.yaml"))
                },
            },
            "cards": {
                "path": str(cards_path.relative_to(ROOT)),
                "sha256": _sha256(cards_path),
            },
        },
    }
    _write_json(output / "source_manifest.json", manifest)

    summary = {
        "schema_version": "phenotype-overlay-source-audit/1.0",
        "artifact": "PHENOTYPE_OVERLAY_SOURCE_AUDIT",
        "question": (
            "Can anonymous/open structured and text sources support a prototype overlay "
            "without enumerating symptom pairs/triples or confusing association with definition?"
        ),
        "targets": targets,
        "medlineplus": medlineplus_summary,
        "orphadata": orphadata_summary,
        "hoom": hoom_summary,
        "dismech": dismech_summary,
        "complexity_contract": {
            "pair_or_triple_rows_materialized": 0,
            "online_shape": "atomic postings union followed by candidate-local typed alignment",
            "forbidden_inference": [
                "Orphadata disease-HPO association -> phenotype definition",
                "HOOM qualified disease-HPO association -> phenotype composition rule",
                "MedlinePlus sentence co-occurrence -> verified graph edge",
                "DisMech exact-snippet validation -> evidence strength or clinical truth",
            ],
        },
        "decision": {
            "ontology_plus_text_overlay": "GO-to-build under provenance and typed-edge governance",
            "automatic_edge_activation": "NO-GO",
            "pair_triple_enumeration": "NO-GO",
        },
    }
    _write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--medlineplus", type=Path, default=DEFAULT_MEDLINEPLUS)
    parser.add_argument("--orphadata", type=Path, default=DEFAULT_ORPHADATA)
    parser.add_argument("--hoom", type=Path, default=DEFAULT_HOOM)
    parser.add_argument("--cards", type=Path, default=DEFAULT_CARDS)
    parser.add_argument("--dismech-dir", type=Path, default=DEFAULT_DISMECH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    summary = run(
        args.medlineplus,
        args.orphadata,
        args.hoom,
        args.cards,
        args.dismech_dir,
        args.output,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "medlineplus_candidates": summary["medlineplus"]["n_relation_candidate_sentences"],
                "orphadata_disorders": summary["orphadata"]["n_disorders"],
                "hoom_associations": summary["hoom"]["n_associations"],
                "dismech_candidates": summary["dismech"]["n_target_evidence_candidates"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
