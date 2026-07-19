"""Production configuration profiles for discrimination evidence."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiscAgentConfig:
    """Feature switches shared by the evaluation harness and production runtime."""

    stage: str = "p0"
    symmetric: bool = False
    normalize: bool = False
    matrix: bool = False
    gate: bool = False
    veto: bool = False
    entail: bool = False
    route: bool = False
    consensus_none: bool = False
    consensus_strict: bool = False
    pheno_confirm: bool = False
    corpus_pheno: bool = False
    value_conditioned: bool = False
    self_consistency: int = 1
    assert_filter: bool = False
    soft_none: bool = False
    gate_key: str = "concrete"
    hier_aggregate: bool = False
    entry_gate: str = "legacy"
    per_cand: int = 2
    top_k: int = 12
    jaccard: float = 0.6
    multi_support_min: int = 2
    evidence_source: str = "legacy"
    cceg_claims: str = ""
    cceg_adjacency: str = ""
    cceg_corpus_metadata: str = ""
    cceg_max_hops: int = 2
    cceg_hydrate: bool = False
    membership_source: str = "none"
    p5kg_manifest: str = ""
    evidence_lane: str = "clinical"
    research_evidence_mode: str = "off"
    research_claims: str = ""
    research_adjacency: str = ""
    research_corpus_metadata: str = ""
    research_hydrate: bool = False
    p5kg_research_manifest: str = ""


_STAGE_ORDER = ["p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7"]


def _cfg_for_stage(stage: str) -> DiscAgentConfig:
    """Return the historical cumulative P0-P7 evaluation configuration."""
    stage = stage.lower()
    if stage in (
        "p5c", "p5cms", "p5cp", "p5cpms", "p5cc", "p5ccms",
        "p5ccv", "p5ccvms",
    ):
        cfg = _cfg_for_stage("p5")
        cfg.stage = stage
        cfg.consensus_none = True
        cfg.consensus_strict = stage.endswith("ms")
        cfg.pheno_confirm = stage.startswith(("p5cp", "p5cc"))
        cfg.corpus_pheno = stage.startswith("p5cc")
        cfg.value_conditioned = stage.startswith("p5ccv")
        return cfg
    index = _STAGE_ORDER.index(stage) if stage in _STAGE_ORDER else 0
    return DiscAgentConfig(
        stage=stage,
        symmetric=index >= 1,
        normalize=index >= 2,
        matrix=index >= 3,
        gate=index >= 4,
        veto=index >= 5,
        entail=index >= 6,
        route=index >= 7,
    )


def config_for_profile(profile: str, **overrides: object) -> DiscAgentConfig:
    """Build a frozen production profile, with explicit caller overrides."""
    key = profile.strip().lower()
    if key == "p5_headline":
        cfg = _cfg_for_stage("p5")
        cfg.evidence_source = "legacy"
        cfg.evidence_lane = "clinical"
        cfg.research_evidence_mode = "off"
    elif key == "g2ur":
        cfg = _cfg_for_stage("p5")
        cfg.evidence_lane = "research"
        cfg.evidence_source = "legacy"
        cfg.research_evidence_mode = "unary"
    else:
        raise ValueError(f"unknown discrimination profile: {profile!r}")
    for name, value in overrides.items():
        if not hasattr(cfg, name):
            raise TypeError(f"unknown DiscAgentConfig field: {name}")
        setattr(cfg, name, value)
    return cfg
