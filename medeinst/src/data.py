"""
Case records for ECR-Agent.

Paper: https://arxiv.org/abs/2601.06636
§3.1 defines control/trap pairs on MedEinst. That constructed set is not
released. Per user instruction, load this parent repo's MCR400 instead.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

# Copied from parent scripts/paper/diagnosisarena_adapter.py vignette_body.
# MCQ stem + Options are answer material, not observed findings.
_MCQ_TAIL_RE = re.compile(
    r"(?is)\n+\s*What is the most likely diagnosis\?\s*\n+Options:\s*\n.*\Z"
)


MCR400_RELATIVE = (
    "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/normalized_cases.json",
    "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/normalized_cases.json",
    "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1/normalized_cases.json",
)

# Parent-repo paper holdouts (200 each). Dev slices are mcr_val_seq100_v1/v2 and d2_seq100.
MCR_HELDOUT200B = (
    "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1/normalized_cases.json"
)
DA_HELDOUT200B = (
    "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1/normalized_cases.json"
)


@dataclass
class Case:
    """One diagnostic narrative.

    MedEinst pair fields (x_c, x_t, y_gt, y_bias) are optional. MCR400 fills
    only x / y_gt (§3.1 mapping f: X→Y with unpaired x).
    """

    case_id: str
    x: str
    y_gt: str
    slice_name: str
    x_c: str | None = None
    x_t: str | None = None
    y_bias: str | None = None
    runtime_case_id: str = ""
    options_stripped: bool = False

    @property
    def is_pair(self) -> bool:
        return self.x_t is not None and self.y_bias is not None


def strip_mcq_options(case_text: str) -> str:
    """Open vignette only. Same rule as parent `vignette_body`."""
    text = str(case_text or "").strip()
    text = _MCQ_TAIL_RE.sub("", text).strip()
    if "\nOptions:" in text:
        text = text.split("\nOptions:", 1)[0].strip()
    text = re.sub(
        r"(?is)\n+\s*What is the most likely diagnosis\?\s*\Z",
        "",
        text,
    ).strip()
    return text


def paper_runtime_ids(slice_name: str, case_id: str) -> tuple[str, str]:
    """Return (runtime_case_id, source_id) matching baseline_common.load_runtime_cases."""
    source_id = str(case_id)
    if str(slice_name).startswith("d2_") or "diagnosisarena" in str(slice_name):
        prefix = "diagnosisarena"
    else:
        prefix = "medcasereasoning"
    try:
        runtime_id = f"{prefix}__{int(source_id):06d}"
    except ValueError:
        runtime_id = f"{prefix}__{source_id}"
    return runtime_id, source_id


def _load_normalized_json(path: Path, slice_name: str) -> list[Case]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    cases: list[Case] = []
    for row in payload["cases"]:
        gold = row.get("gold") or row.get("gold_option_text") or ""
        raw = str(row["case_text"])
        x = strip_mcq_options(raw)
        runtime_id, source_id = paper_runtime_ids(slice_name, str(row["id"]))
        cases.append(
            Case(
                case_id=source_id,
                x=x,
                y_gt=str(gold),
                slice_name=slice_name,
                runtime_case_id=runtime_id,
                options_stripped=x != raw.strip(),
            )
        )
    return cases


def _require_normalized(parent_repo_root: str | Path, relative: str) -> Path:
    root = Path(parent_repo_root).resolve()
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(
            f"subset missing: {path}. Point parent_repo_root at the "
            "Agentclinic-Tree-Dx-Spec checkout."
        )
    return path


def load_mcr400(parent_repo_root: str | Path) -> list[Case]:
    """Load 400 MedCaseReasoning cases: mcr_v1(100)+mcr_v2(100)+mcr_200b(200).

    Does not download data. Paths are relative to the parent Agentclinic repo.
    """
    out: list[Case] = []
    for rel in MCR400_RELATIVE:
        path = _require_normalized(parent_repo_root, rel)
        out.extend(_load_normalized_json(path, path.parent.name))
    if len(out) != 400:
        raise ValueError(f"expected 400 MCR cases, got {len(out)}")
    return out


def load_mcr_heldout200(parent_repo_root: str | Path) -> list[Case]:
    """Load the MCR holdout 200 (`mcr_val_seq200b_v1`). Not the 200-case dev split."""
    path = _require_normalized(parent_repo_root, MCR_HELDOUT200B)
    cases = _load_normalized_json(path, path.parent.name)
    if len(cases) != 200:
        raise ValueError(f"expected 200 MCR held-out cases, got {len(cases)}")
    return cases


def load_da_heldout200(parent_repo_root: str | Path) -> list[Case]:
    """Load the DiagnosisArena holdout 200 (`d2_heldout200b_v1`)."""
    path = _require_normalized(parent_repo_root, DA_HELDOUT200B)
    cases = _load_normalized_json(path, path.parent.name)
    if len(cases) != 200:
        raise ValueError(f"expected 200 DA held-out cases, got {len(cases)}")
    return cases


def load_heldout_corpus(parent_repo_root: str | Path, corpus: str) -> list[Case]:
    """corpus: da | mcr | both."""
    name = corpus.strip().lower()
    if name == "da":
        return load_da_heldout200(parent_repo_root)
    if name == "mcr":
        return load_mcr_heldout200(parent_repo_root)
    if name == "both":
        return load_da_heldout200(parent_repo_root) + load_mcr_heldout200(parent_repo_root)
    raise ValueError(f"unknown corpus {corpus!r}; expected da, mcr, or both")


class MCR400Dataset:
    """Iterable over MCR400 (user substitute for MedEinst test pairs)."""

    def __init__(self, parent_repo_root: str | Path) -> None:
        self.cases = load_mcr400(parent_repo_root)

    def __len__(self) -> int:
        return len(self.cases)

    def __getitem__(self, idx: int) -> Case:
        return self.cases[idx]

    def __iter__(self) -> Iterator[Case]:
        return iter(self.cases)
