#!/usr/bin/env python3
"""Local-only MedCPT dual-encoder helper for the phenotype-subgraph probe.

The helper is intentionally dependency-isolated because the repository's
primary analysis environment has scikit-learn but no torch, while the pinned
MedCPT environment has torch/transformers but no scikit-learn.  It accepts a
small JSON payload, loads local model directories only, and writes raw dot and
cosine matrices.  It never downloads a model or calls a service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from importlib import metadata as package_metadata
from pathlib import Path
from typing import Any, Sequence

import torch
from transformers import AutoModel, AutoTokenizer


TOKENIZER_ASSETS = (
    "added_tokens.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return None


def _git_worktree_clean(path: Path) -> bool | None:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return not bool(completed.stdout.strip())


def _tokenizer_asset_hashes(path: Path) -> dict[str, str | None]:
    return {name: _sha256(path / name) for name in TOKENIZER_ASSETS}


def _batches(values: Sequence[Any], size: int) -> list[Sequence[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def encode_queries(model_dir: Path, texts: list[str], batch_size: int) -> torch.Tensor:
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModel.from_pretrained(
        str(model_dir), local_files_only=True, use_safetensors=True
    ).eval()
    rows: list[torch.Tensor] = []
    with torch.no_grad():
        for batch in _batches(texts, batch_size):
            encoded = tokenizer(
                list(batch),
                truncation=True,
                padding=True,
                return_tensors="pt",
                max_length=64,
            )
            rows.append(model(**encoded).last_hidden_state[:, 0, :].float().cpu())
    return torch.cat(rows, dim=0)


def encode_articles(
    model_dir: Path, rows: list[list[str]], batch_size: int
) -> torch.Tensor:
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModel.from_pretrained(
        str(model_dir), local_files_only=True, use_safetensors=True
    ).eval()
    embeddings: list[torch.Tensor] = []
    with torch.no_grad():
        for batch in _batches(rows, batch_size):
            encoded = tokenizer(
                list(batch),
                truncation=True,
                padding=True,
                return_tensors="pt",
                max_length=512,
            )
            embeddings.append(model(**encoded).last_hidden_state[:, 0, :].float().cpu())
    return torch.cat(embeddings, dim=0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query-model", type=Path, required=True)
    parser.add_argument("--article-model", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    if not args.query_model.is_dir() or not args.article_model.is_dir():
        raise SystemExit("both model paths must be existing local directories")
    payload = _read_json(args.input)
    queries = payload["queries"]
    targets = payload["targets"]
    query_vectors = encode_queries(
        args.query_model, [row["text"] for row in queries], args.batch_size
    )
    article_vectors = encode_articles(
        args.article_model,
        [[row["title"], row["text"]] for row in targets],
        args.batch_size,
    )
    dots = query_vectors @ article_vectors.T
    cosine = torch.nn.functional.normalize(query_vectors, dim=1) @ torch.nn.functional.normalize(
        article_vectors, dim=1
    ).T

    result = {
        "schema_version": "phenotype-subgraph-medcpt-encode.v1",
        "query_ids": [row["id"] for row in queries],
        "target_ids": [row["id"] for row in targets],
        "dot_scores": dots.tolist(),
        "cosine_scores": cosine.tolist(),
        "official_representation_contract": {
            "query": "Query Encoder [CLS], max_length=64",
            "article": "Article Encoder [CLS], [title, body], max_length=512",
            "primary_similarity": "raw dot product",
            "cosine": "diagnostic only",
            "model_weights": "safetensors enforced",
        },
        "provenance": {
            "query_model": {
                "path": str(args.query_model),
                "git_commit": _git_head(args.query_model),
                "git_worktree_clean": _git_worktree_clean(args.query_model),
                "model_safetensors_sha256": _sha256(args.query_model / "model.safetensors"),
                "config_sha256": _sha256(args.query_model / "config.json"),
                "tokenizer_assets_sha256": _tokenizer_asset_hashes(args.query_model),
            },
            "article_model": {
                "path": str(args.article_model),
                "git_commit": _git_head(args.article_model),
                "git_worktree_clean": _git_worktree_clean(args.article_model),
                "model_safetensors_sha256": _sha256(args.article_model / "model.safetensors"),
                "config_sha256": _sha256(args.article_model / "config.json"),
                "tokenizer_assets_sha256": _tokenizer_asset_hashes(args.article_model),
            },
            "runtime": {
                "python": sys.version.split()[0],
                "torch": torch.__version__,
                "transformers": package_metadata.version("transformers"),
            },
        },
    }
    _write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
