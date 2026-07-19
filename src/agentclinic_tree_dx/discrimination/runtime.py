"""Controller-facing profile evidence and rule runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .adapters import ResearchClaimAdapter
from .cache import ProfileEvidenceCache, profile_cache_fingerprint
from .compiler import compile_profile_rules
from .config import DiscAgentConfig, config_for_profile
from .manifests import validate_research_manifest

LegacyEvidenceProvider = Callable[
    [str, list, DiscAgentConfig], Iterable[Mapping[str, Any]]
]


@dataclass(frozen=True)
class ProfileEvidence:
    """Stable response for one finding against one candidate set."""

    profile: str
    finding: str
    candidates: tuple[str, ...]
    evidence: tuple[Mapping[str, Any], ...]
    rules: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "finding": self.finding,
            "candidates": list(self.candidates),
            "evidence": [dict(row) for row in self.evidence],
            "rules": [dict(row) for row in self.rules],
        }


class DiscriminationRuntime:
    """Resolve profile evidence without depending on evaluation scripts."""

    def __init__(
        self,
        profile: str,
        *,
        config: DiscAgentConfig | None = None,
        legacy_provider: LegacyEvidenceProvider | None = None,
        verify_manifest_assets: bool = False,
        manifest_root: str | None = None,
        cache_path: str | None = None,
    ) -> None:
        self.profile = profile.strip().lower()
        self.config = config or config_for_profile(self.profile)
        self.legacy_provider = legacy_provider
        self.cache = (
            ProfileEvidenceCache(cache_path, self.profile) if cache_path else None
        )
        self._research: ResearchClaimAdapter | None = None
        if self.profile == "g2ur":
            if self.config.research_evidence_mode != "unary":
                raise ValueError("g2ur profile requires unary research evidence")
            if not self.config.research_claims:
                raise ValueError("g2ur profile requires research_claims")
            if not self.config.p5kg_research_manifest:
                raise ValueError("g2ur profile requires p5kg_research_manifest")
            validate_research_manifest(
                self.config.p5kg_research_manifest,
                root=manifest_root,
                verify_assets=verify_manifest_assets,
            ).require_valid()
            self._research = ResearchClaimAdapter(self.config)
        elif self.profile != "p5_headline":
            raise ValueError(f"unknown discrimination profile: {profile!r}")

    @staticmethod
    def _candidate_names(candidate_names: Iterable[str]) -> tuple[str, ...]:
        names = tuple(dict.fromkeys(
            str(name).strip() for name in candidate_names if str(name).strip()))
        if not names:
            raise ValueError("candidate_names must not be empty")
        return names

    def evidence(
        self, finding: str, candidate_names: Iterable[str]
    ) -> ProfileEvidence:
        """Return deterministic, profile-scoped evidence and direct claim rules."""
        finding = str(finding).strip()
        if not finding:
            raise ValueError("finding must not be empty")
        names = self._candidate_names(candidate_names)
        fingerprint = profile_cache_fingerprint(
            self.profile,
            self.config,
            finding=finding,
            candidates=list(names),
        )
        if self.cache is not None:
            cached = self.cache.get(fingerprint)
            if cached is not None:
                return ProfileEvidence(
                    profile=self.profile,
                    finding=finding,
                    candidates=names,
                    evidence=tuple(cached.get("evidence") or ()),
                    rules=tuple(cached.get("rules") or ()),
                )
        if self.profile == "g2ur":
            assert self._research is not None
            rows = self._research.evidence(finding, list(names), self.config.top_k)
        elif self.legacy_provider is None:
            rows = []
        else:
            rows = [
                dict(row)
                for row in self.legacy_provider(finding, list(names), self.config)
            ]
        frozen_rows = tuple(dict(row) for row in rows)
        result = ProfileEvidence(
            profile=self.profile,
            finding=finding,
            candidates=names,
            evidence=frozen_rows,
            rules=compile_profile_rules(
                frozen_rows,
                candidates=names,
                phenotype_veto=self.config.veto,
            ),
        )
        if self.cache is not None:
            self.cache.put(fingerprint, result.to_dict())
        return result


def profile_evidence(
    finding: str,
    candidate_names: Iterable[str],
    *,
    profile: str,
    config: DiscAgentConfig | None = None,
    legacy_provider: LegacyEvidenceProvider | None = None,
) -> ProfileEvidence:
    """Convenience API for stateless controller integrations."""
    return DiscriminationRuntime(
        profile, config=config, legacy_provider=legacy_provider
    ).evidence(finding, candidate_names)
