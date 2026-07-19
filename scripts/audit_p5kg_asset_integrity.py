#!/usr/bin/env python3
"""Create or verify a frozen, content-addressed P5KG asset manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict:
    path = path.resolve()
    try:
        stored = str(path.relative_to(ROOT))
    except ValueError:
        stored = str(path)
    return {"path": stored, "size": path.stat().st_size, "sha256": _sha256(path)}


def snapshot(claims: Path, adjacency: Path | None = None,
             oracle_claims: Path | None = None,
             membership_claims: Path | None = None,
             corpus_metadata: Path | None = None,
             research_assets: dict[str, Path | None] | None = None) -> dict:
    paths = {"claims": claims}
    if adjacency is not None:
        paths["adjacency"] = adjacency
    if oracle_claims is not None:
        paths["oracle_claims"] = oracle_claims
    if membership_claims is not None:
        paths["membership_claims"] = membership_claims
    if corpus_metadata is not None:
        paths["corpus_metadata"] = corpus_metadata
    paths.update({
        name: path for name, path in (research_assets or {}).items()
        if path is not None
    })
    missing = [name for name, path in paths.items() if not path.is_file()]
    return {
        "assets": {
            name: _record(path) for name, path in paths.items()
            if path.is_file()
        },
        "missing": missing,
    }


def _resolve(record: dict) -> Path:
    path = Path(record["path"])
    return path if path.is_absolute() else ROOT / path


def verify(manifest: Path, required: list[Path] | None = None,
           expected_lane: str | None = None) -> dict:
    payload = json.loads(manifest.read_text())
    failures = []
    for name, expected in payload.get("assets", {}).items():
        path = _resolve(expected)
        if not path.is_file():
            failures.append(f"missing: {name}:{path}")
            continue
        actual = {"path": expected["path"], "size": path.stat().st_size,
                  "sha256": _sha256(path)}
        if actual != expected:
            failures.append(
                f"changed: {name} expected={expected} actual={actual}")
    if not payload.get("freeze_id"):
        failures.append("manifest missing freeze_id")
    if expected_lane and payload.get("lane") != expected_lane:
        failures.append(
            f"manifest lane mismatch: expected={expected_lane} "
            f"actual={payload.get('lane')}")
    if expected_lane == "research" and payload.get(
            "review_mode") != "synthetic_dual_llm":
        failures.append(
            "research manifest requires review_mode=synthetic_dual_llm")
    tracked = {_resolve(record).resolve()
               for record in payload.get("assets", {}).values()}
    for path in required or []:
        if path.resolve() not in tracked:
            failures.append(f"untracked required input: {path.resolve()}")
    return {
        "verified": not failures,
        "freeze_id": payload.get("freeze_id"),
        "assets": len(payload.get("assets", {})),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--adjacency", type=Path)
    parser.add_argument("--oracle-claims", type=Path)
    parser.add_argument("--membership-claims", type=Path)
    parser.add_argument("--corpus-metadata", type=Path)
    parser.add_argument("--research", action="store_true")
    parser.add_argument("--unary-scope", type=Path)
    parser.add_argument("--review-report", type=Path)
    parser.add_argument("--pair-review-report", type=Path)
    parser.add_argument("--premise-index", type=Path)
    parser.add_argument("--derived-index", type=Path)
    parser.add_argument("--composition-rules", type=Path)
    parser.add_argument("--finding-normalizer", type=Path)
    parser.add_argument("--require", type=Path, action="append", default=[])
    parser.add_argument("--freeze-id")
    args = parser.parse_args()

    if args.verify:
        if not args.manifest.is_file():
            parser.error(f"missing P5KG manifest: {args.manifest}")
        report = verify(
            args.manifest, args.require,
            expected_lane="research" if args.research else None)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["verified"] else 1

    if args.manifest.exists():
        parser.error(f"refusing to overwrite {args.manifest}")
    if not args.claims or not args.freeze_id:
        parser.error("--create requires --claims and --freeze-id")
    current = snapshot(
        args.claims, args.adjacency, args.oracle_claims,
        args.membership_claims, args.corpus_metadata, {
            "unary_scope": args.unary_scope,
            "review_report": args.review_report,
            "pair_review_report": args.pair_review_report,
            "premise_index": args.premise_index,
            "derived_index": args.derived_index,
            "composition_rules": args.composition_rules,
            "finding_state_normalizer": args.finding_normalizer,
        })
    if current["missing"]:
        parser.error(f"missing P5KG assets: {current['missing']}")
    payload = {
        "schema_version": 1,
        "algorithm": "sha256",
        "freeze_id": args.freeze_id,
        "lane": "research" if args.research else "clinical",
        "review_mode": "synthetic_dual_llm" if args.research else "human",
        "purpose": (
            "P5KG research simulation inputs; clinical use forbidden"
            if args.research else
            "P5KG isolated evaluation inputs; outputs forbidden"),
        "assets": current["assets"],
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"created immutable P5KG asset manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
