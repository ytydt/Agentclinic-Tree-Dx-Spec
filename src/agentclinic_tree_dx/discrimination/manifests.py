"""Validation of immutable discrimination input manifests."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ManifestValidation:
    valid: bool
    manifest: Mapping[str, Any]
    errors: tuple[str, ...] = ()
    checked_assets: int = 0

    def require_valid(self) -> Mapping[str, Any]:
        if not self.valid:
            raise ValueError("; ".join(self.errors))
        return self.manifest


def load_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(
    path: str | Path,
    *,
    root: str | Path | None = None,
    verify_assets: bool = False,
    expected_lane: str | None = None,
    expected_review_mode: str | None = None,
) -> ManifestValidation:
    """Validate shape/policy and optionally size/SHA-256 of every asset."""
    manifest_path = Path(path)
    errors: list[str] = []
    try:
        payload = load_manifest(manifest_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return ManifestValidation(False, {}, (f"invalid manifest: {exc}",))
    if payload.get("algorithm") not in (None, "sha256"):
        errors.append("manifest algorithm must be sha256")
    if expected_lane and payload.get("lane") != expected_lane:
        errors.append(f"manifest lane must be {expected_lane}")
    if expected_review_mode and payload.get("review_mode") != expected_review_mode:
        errors.append(f"manifest review_mode must be {expected_review_mode}")
    assets = payload.get("assets")
    if not isinstance(assets, dict):
        errors.append("manifest assets must be an object")
        assets = {}
    checked = 0
    if verify_assets:
        base = Path(root) if root is not None else manifest_path.parent
        for key, raw in assets.items():
            if not isinstance(raw, dict):
                errors.append(f"asset {key}: metadata must be an object")
                continue
            relpath = raw.get("path") or key
            asset_path = Path(relpath)
            if not asset_path.is_absolute():
                asset_path = base / asset_path
            if not asset_path.is_file():
                errors.append(f"asset {key}: missing {asset_path}")
                continue
            checked += 1
            size = asset_path.stat().st_size
            if raw.get("size") is not None and size != raw["size"]:
                errors.append(f"asset {key}: size mismatch")
            digest = _sha256(asset_path)
            if raw.get("sha256") and digest != raw["sha256"]:
                errors.append(f"asset {key}: sha256 mismatch")
    return ManifestValidation(not errors, payload, tuple(errors), checked)


def validate_research_manifest(
    path: str | Path,
    *,
    root: str | Path | None = None,
    verify_assets: bool = False,
) -> ManifestValidation:
    """Enforce the physical research lane and synthetic-review policy."""
    result = validate_manifest(
        path,
        root=root,
        verify_assets=verify_assets,
        expected_lane="research",
        expected_review_mode="synthetic_dual_llm",
    )
    errors = list(result.errors)
    if result.manifest and not result.manifest.get("freeze_id"):
        errors.append("research manifest requires freeze_id")
    return ManifestValidation(
        not errors, result.manifest, tuple(errors), result.checked_assets)
