"""DiagnosisArena (D2) subset adapter for the paper P5+BFS harness."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

# DiagnosisArena case_text ends with an MCQ stem + Options block; those are
# answer material, not observed clinical findings.
_MCQ_TAIL_RE = re.compile(
    r"(?is)\n+\s*What is the most likely diagnosis\?\s*\n+Options:\s*\n.*\Z"
)
_BULLET_RE = re.compile(r"(?m)^\s*[-*•]\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_LABEL_PREFIX_RE = re.compile(
    r"^(?:"
    r"Image Title|Image Description|Biopsy Results|Tissue analysis|"
    r"Imaging Studies|CT scan|MRI|Laboratory|Labs?"
    r")\s*:\s*",
    re.IGNORECASE,
)
_SKIP_FINDING_RE = re.compile(
    r"(?i)^(options?|what is the most likely diagnosis|"
    r"no significant past medical history was mentioned|"
    r"image title|image description)\b"
)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_case_text(row: Mapping[str, Any]) -> str:
    sections = []
    for key in (
        "Case Information",
        "Physical Examination",
        "Diagnostic Tests",
    ):
        text = str(row.get(key) or "").strip()
        if text:
            sections.append(text)
    body = "\n\n".join(sections).strip()
    options = row.get("Options") or {}
    if not isinstance(options, Mapping) or not options:
        raise ValueError("case %s missing Options" % row.get("id"))
    option_lines = "\n".join(
        f"{letter}. {text}"
        for letter, text in sorted(
            ((str(k).upper(), str(v).strip()) for k, v in options.items()),
            key=lambda pair: pair[0],
        )
    )
    question = "What is the most likely diagnosis?"
    return f"{body}\n\n{question}\n\nOptions:\n{option_lines}\n"


def vignette_body(case_text: str) -> str:
    """Strip MCQ stem/options so only clinical narrative remains."""
    text = str(case_text or "").strip()
    text = _MCQ_TAIL_RE.sub("", text).strip()
    # Defensive: if the MCQ marker is missing, still drop a trailing Options block.
    if "\nOptions:" in text:
        text = text.split("\nOptions:", 1)[0].strip()
    return text


def extract_deterministic_finding_texts(
    case_text: str,
    *,
    limit: int = 40,
) -> list[str]:
    """Gold-blind observed-fact extraction without VignetteParser.

    DiagnosisArena M01 does not ship a reliable LLM findings extractor; this
    deterministic splitter turns Case Information / PE / Diagnostic Tests prose
    into a bounded finding catalog for L1 BFS / P5 / joint stages.
    """
    body = vignette_body(case_text)
    if not body:
        return []

    chunks: list[str] = []
    for block in re.split(r"\n\s*\n+", body):
        block = block.strip()
        if not block:
            continue
        # Prefer bullet lines when present; otherwise keep paragraph units.
        if _BULLET_RE.search(block):
            parts = _BULLET_RE.split(block)
            for part in parts:
                part = part.strip(" -\t")
                if part:
                    chunks.append(part)
        else:
            chunks.append(block)

    findings: list[str] = []
    seen: set[str] = set()

    def _push(raw: str) -> None:
        text = _LABEL_PREFIX_RE.sub("", " ".join(raw.split())).strip(" -;\t")
        if not text or len(text) < 8:
            return
        if _SKIP_FINDING_RE.match(text):
            return
        # Drop option-like leftovers.
        if re.match(r"^[A-D]\.\s+\S", text):
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        findings.append(text)

    for chunk in chunks:
        # Long imaging / biopsy blobs → sentence-level facts.
        if len(chunk) > 220 or chunk.count(".") >= 2:
            pieces = _SENTENCE_SPLIT_RE.split(chunk)
            for piece in pieces:
                _push(piece)
                if len(findings) >= limit:
                    return findings
        else:
            _push(chunk)
            if len(findings) >= limit:
                return findings
    return findings


def evidence_items_from_case_text(
    case_text: str,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Serialize EvidenceItem-compatible dicts for tree state / fixtures."""
    return [
        {
            "id": "E%d" % (index + 1),
            "kind": "direct",
            "content": text,
            "source_ids": [],
            "independent": True,
            "branch_links": {},
            "metadata": {
                "extractor": "diagnosisarena_deterministic_vignette_v1",
            },
        }
        for index, text in enumerate(
            extract_deterministic_finding_texts(case_text, limit=limit)
        )
    ]


def apply_deterministic_static_fields(state: Any, case: Mapping[str, Any]) -> int:
    """Ensure tree state has non-empty evidence + MCQ options (no LLM).

    Returns the number of evidence items written. Raises if extraction yields
    nothing — callers must not persist empty catalogs.
    """
    from agentclinic_tree_dx.state import EvidenceItem  # local import keeps adapter light

    case_text = str(case.get("case_text") or getattr(state, "case_summary", "") or "")
    items = evidence_items_from_case_text(case_text)
    if not items:
        raise RuntimeError(
            "%s: deterministic finding extraction produced empty catalog"
            % (case.get("id") or getattr(state, "case_id", "?"))
        )

    state.static_evidence_items = [
        EvidenceItem(
            id=str(row["id"]),
            kind=str(row.get("kind") or "direct"),
            content=str(row["content"]),
            source_ids=list(row.get("source_ids") or ()),
            independent=bool(row.get("independent", True)),
            branch_links=dict(row.get("branch_links") or {}),
            metadata=dict(row.get("metadata") or {}),
        )
        for row in items
    ]
    state.static_vignette = vignette_body(case_text) or case_text
    state.static_question = "What is the most likely diagnosis?"
    options = (
        (case.get("annotation") or {}).get("source_options")
        if isinstance(case.get("annotation"), Mapping)
        else None
    ) or {}
    if isinstance(options, Mapping) and options:
        state.static_options = [
            {"id": str(letter), "description": str(text)}
            for letter, text in sorted(
                options.items(), key=lambda pair: str(pair[0])
            )
        ]
    return len(state.static_evidence_items)


def load_vignette_parser_freeze(path: Path | str) -> dict[str, dict[str, Any]]:
    """Load signed-off VignetteParser freeze keyed by case_id."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not doc.get("human_signed_off"):
        raise ValueError(
            "vignette freeze %s is not human_signed_off" % path
        )
    out: dict[str, dict[str, Any]] = {}
    for row in doc.get("cases") or ():
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            continue
        out[case_id] = dict(row)
    if not out:
        raise ValueError("vignette freeze %s has no cases" % path)
    return out


def apply_frozen_vignette_parser_fields(
    state: Any,
    case: Mapping[str, Any],
    frozen_case: Mapping[str, Any],
) -> int:
    """Inject frozen VignetteParser fields (no live LLM parse)."""
    from agentclinic_tree_dx.state import EvidenceItem

    evidence = list(frozen_case.get("evidence_items") or ())
    if not evidence:
        raise RuntimeError(
            "%s: frozen vignette parser case has empty evidence"
            % (case.get("id") or getattr(state, "case_id", "?"))
        )
    state.static_evidence_items = [
        EvidenceItem(
            id=str(item.get("id") or ("E%d" % (index + 1))),
            kind=str(item.get("kind") or "direct"),
            content=str(item.get("content") or "").strip(),
            source_ids=list(item.get("source_ids") or ()),
            independent=bool(item.get("independent", True)),
            branch_links=dict(item.get("branch_links") or {}),
            metadata={
                **dict(item.get("metadata") or {}),
                "extractor": "diagnosisarena_vignette_parser_freeze_v2",
            },
        )
        for index, item in enumerate(evidence)
        if str(item.get("content") or "").strip()
    ]
    if not state.static_evidence_items:
        raise RuntimeError(
            "%s: frozen evidence items had no usable content"
            % (case.get("id") or getattr(state, "case_id", "?"))
        )

    case_text = str(case.get("case_text") or getattr(state, "case_summary", "") or "")
    state.static_vignette = str(
        frozen_case.get("vignette") or vignette_body(case_text) or case_text
    )
    state.static_question = str(
        frozen_case.get("question") or "What is the most likely diagnosis?"
    )

    frozen_options = frozen_case.get("options") or []
    if isinstance(frozen_options, list) and frozen_options:
        state.static_options = [
            {
                "id": str(opt.get("id") or ""),
                "description": str(opt.get("description") or ""),
            }
            for opt in frozen_options
            if str(opt.get("id") or "").strip()
        ]
    else:
        options = (
            (case.get("annotation") or {}).get("source_options")
            if isinstance(case.get("annotation"), Mapping)
            else None
        ) or {}
        state.static_options = [
            {"id": str(letter), "description": str(text)}
            for letter, text in sorted(options.items(), key=lambda pair: str(pair[0]))
        ]
    return len(state.static_evidence_items)


def findings_catalog_from_frozen_case(
    frozen_case: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build L1 finding-fixture rows from a frozen VignetteParser case."""
    if frozen_case.get("full_findings"):
        rows = []
        for index, item in enumerate(frozen_case["full_findings"]):
            text = str(item.get("text") or item.get("content") or "").strip()
            if not text:
                continue
            rows.append({
                "id": str(item.get("id") or ("F%d" % (len(rows) + 1))),
                "source_id": str(item.get("source_id") or item.get("id") or ("E%d" % (index + 1))),
                "text": text,
            })
        if rows:
            return rows
    rows = []
    for index, item in enumerate(frozen_case.get("evidence_items") or ()):
        text = str(item.get("content") or "").strip()
        if not text:
            continue
        rows.append({
            "id": "F%d" % (len(rows) + 1),
            "source_id": str(item.get("id") or ("E%d" % (index + 1))),
            "text": text,
        })
    return rows


def normalize_options(options: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(letter).upper(): str(text).strip()
        for letter, text in sorted(options.items(), key=lambda pair: str(pair[0]))
    }


def load_subset_cases(
    parquet_path: Path | str,
    *,
    case_ids: Sequence[str] = (),
    limit: int = 0,
) -> list[dict[str, Any]]:
    path = Path(parquet_path)
    frame = pd.read_parquet(path)
    wanted = {str(value) for value in case_ids if str(value).strip()}
    cases: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        case_id = str(row["id"])
        if wanted and case_id not in wanted:
            continue
        options = normalize_options(row["Options"])
        gold_diagnosis = str(row["Final Diagnosis"] or "").strip()
        gold_letter = str(row["Right Option"] or "").strip().upper()
        if gold_letter not in options:
            raise ValueError(
                "%s: Right Option %r not in options %s"
                % (case_id, gold_letter, sorted(options))
            )
        case_text = build_case_text(row)
        cases.append({
            "id": case_id,
            "corpus": "diagnosisarena",
            "dataset": "diagnosisarena_d2_seq100_v1",
            "source_row_id": case_id,
            "gold": gold_diagnosis,
            "gold_option": gold_letter,
            "gold_option_text": options[gold_letter],
            "case_text": case_text,
            "annotation": {
                "source_options": dict(options),
                "findings": [],
                "candidates": [],
            },
            "case_text_hash": stable_hash(case_text),
        })
        if limit > 0 and len(cases) >= limit:
            break
    if wanted:
        missing = sorted(wanted - {case["id"] for case in cases})
        if missing:
            raise ValueError("unknown case ids: %s" % missing)
    return cases


def candidates_from_state(state) -> list[dict[str, Any]]:
    branches = state.branches or {}
    l1_labels = {
        branch_id: branch.label
        for branch_id, branch in branches.items()
        if branch.level == 1
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for branch_id, branch in branches.items():
        if branch.level != 2:
            continue
        name = str(branch.label or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        parent_label = str(l1_labels.get(branch.parent, "") or name)
        candidates.append({
            "name": name,
            "l1_parent": parent_label,
            "is_gold": False,
            "branch_id": branch_id,
        })
    return candidates


def findings_from_state(state, case: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(getattr(state, "static_evidence_items", None) or ()):
        content = ""
        if isinstance(item, Mapping):
            content = str(
                item.get("content")
                or item.get("fact")
                or item.get("description")
                or ""
            ).strip()
        else:
            content = str(getattr(item, "content", "") or "").strip()
        if not content:
            continue
        findings.append({
            "finding_id": f"F{index + 1}",
            "finding": content,
            "in_vignette": True,
            "role": "observed",
            "decisive": False,
        })
    if not findings and case is not None:
        for index, text in enumerate(
            extract_deterministic_finding_texts(str(case.get("case_text") or ""))
        ):
            findings.append({
                "finding_id": f"F{index + 1}",
                "finding": text,
                "in_vignette": True,
                "role": "observed",
                "decisive": False,
            })
    return findings


def runtime_compiler_case(talp_case: Mapping[str, Any]) -> dict[str, Any]:
    """Gold-blind payload for P5 compiler / BFS runtime (no eval labels)."""
    return {
        "id": str(talp_case["id"]),
        "corpus": str(talp_case.get("corpus") or "diagnosisarena"),
        "l1_label": str(talp_case.get("l1_label") or ""),
        "candidates": [
            {
                "name": str(candidate["name"]),
                "l1_parent": str(
                    candidate.get("l1_parent") or candidate["name"]
                ),
            }
            for candidate in (talp_case.get("candidates") or ())
        ],
        "findings": [
            {
                "finding_id": str(
                    row.get("finding_id") or ("F%d" % (index + 1))
                ),
                "finding": str(row.get("finding") or ""),
                "in_vignette": True,
            }
            for index, row in enumerate(talp_case.get("findings") or ())
            if str(row.get("finding") or "").strip()
        ],
        "case_text": str(talp_case.get("case_text") or ""),
    }


def build_talp_case(case: Mapping[str, Any], state) -> dict[str, Any]:
    candidates = candidates_from_state(state)
    findings = findings_from_state(state, case)
    gold_norm = str(case.get("gold") or "").strip().lower()
    for candidate in candidates:
        candidate["is_gold"] = candidate["name"].strip().lower() == gold_norm
    l1_labels = sorted({
        str(candidate.get("l1_parent") or candidate["name"])
        for candidate in candidates
    })
    return {
        "id": str(case["id"]),
        "corpus": str(case.get("corpus") or "diagnosisarena"),
        "gold": str(case["gold"]),
        "gold_option": str(case.get("gold_option") or ""),
        "l1_label": l1_labels[0] if len(l1_labels) == 1 else "",
        "candidates": candidates,
        "findings": findings,
        "case_text": str(case["case_text"]),
    }


def l2_ranking_from_state(state) -> list[str]:
    branches = state.branches or {}
    parents = {
        branch_id: float(branch.posterior or 0.0)
        for branch_id, branch in branches.items()
        if branch.level == 1
    }
    scored: list[tuple[float, str]] = []
    for branch_id, branch in branches.items():
        if branch.level != 2:
            continue
        parent_score = float(parents.get(branch.parent, 0.0))
        leaf_score = float(branch.posterior or 0.0)
        scored.append((parent_score * max(leaf_score, 1e-6), str(branch_id)))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [leaf_id for _, leaf_id in scored]


def write_normalized_cases(
    cases: Sequence[Mapping[str, Any]],
    out_path: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "dataset": "diagnosisarena_d2_seq100_v1",
        "n_cases": len(cases),
        "cases": list(cases),
    }
    _atomic_json(out_path, payload)
