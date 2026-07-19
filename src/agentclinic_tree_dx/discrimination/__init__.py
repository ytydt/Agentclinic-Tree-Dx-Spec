"""Production discrimination profiles and evidence runtime."""

from .adapters import ResearchClaimAdapter
from .cache import ProfileEvidenceCache, profile_cache_fingerprint, stable_fingerprint
from .compiler import compile_profile_rules
from .config import DiscAgentConfig, _cfg_for_stage, config_for_profile
from .manifests import (
    ManifestValidation,
    load_manifest,
    validate_manifest,
    validate_research_manifest,
)
from .runtime import DiscriminationRuntime, ProfileEvidence, profile_evidence

__all__ = [
    "DiscAgentConfig",
    "DiscriminationRuntime",
    "ManifestValidation",
    "ProfileEvidence",
    "ProfileEvidenceCache",
    "ResearchClaimAdapter",
    "_cfg_for_stage",
    "config_for_profile",
    "compile_profile_rules",
    "load_manifest",
    "profile_evidence",
    "profile_cache_fingerprint",
    "stable_fingerprint",
    "validate_manifest",
    "validate_research_manifest",
]
