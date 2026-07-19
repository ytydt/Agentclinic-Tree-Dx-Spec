from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ControllerConfig:
    test_threshold: float = 0.05
    commit_threshold: float = 0.75
    max_live_frontier: int = 6  # increased from 4 to accommodate multi-level frontiers

    # Specialized execution mode for AgentClinic physician runtime.
    execution_mode: str = "default"  # default | agentclinic_physician_patch | sdbench_patch | static_diagnosis_qa

    # Turn-aware controls for patch mode.
    max_turn_budget: int | None = None
    min_readiness_to_commit: float = 0.75

    # ── Harness-only partial controller flow ─────────────────────────────────
    # Disabled by default so production/controller behaviour is unchanged.
    # The evaluation harness enables these together to collect a deterministic
    # two-turn trace that stops immediately after turn-2 evidence annotation.
    partial_flow: bool = False
    max_timesteps: int = 2
    force_expand_all_l1: bool = False
    stop_after_evidence: bool = False

    # Benchmark/tool permissions.
    allow_external_knowledge: bool = True
    allow_calculator: bool = True
    allow_notebook: bool = False

    # ── Protocol enforcement (LLM output-contract validation) ─────────────────
    # When a critical module returns a response that violates its output contract
    # (missing required keys, empty label, over-long root label, …) the controller
    # re-calls the LLM up to `max_protocol_retries` extra times with a corrective
    # reminder. If it still fails, an LLMProtocolError is raised so the harness can
    # mark the case as a protocol failure (skip + log) instead of crashing.
    max_protocol_retries: int = 2
    # Soft upper bound on the RootSelector root_label (words) — a syndrome frame
    # should be a concise phrase, not an enumeration of every finding.
    max_root_label_words: int = 40

    # ── Multi-level tree expansion (MULTI_LEVEL_EXPANSION_DESIGN) ──────────────
    # Maximum depth of the diagnostic tree (L1-L3 by default; L4 via allow_depth_4)
    max_tree_depth: int = 3
    # Allow Level-4 subtype/variant expansion for cases requiring management detail
    allow_depth_4: bool = False
    # ActionDifferenceScore threshold for ExpansionGate ALLOW condition (A)
    min_action_diff_to_expand: float = 0.25
    # Maximum structural expansions allowed per cycle (K=1 routine, K=2 complex)
    max_structural_expansions_per_cycle: int = 2

    # ── Multi-action bundle (MULTI_ACTION_DESIGN_REVISION) ─────────────────────
    # Minimum expected information gain for a candidate to enter the bundle
    min_marginal_ig_threshold: float = 0.05
    # Jaccard similarity threshold above which two actions are considered redundant
    redundancy_similarity_threshold: float = 0.60
    # Minimum action_separation_value for Phase 2 cross-branch supplement actions
    min_separation_value_for_supplement: float = 0.50
    # Turn budget accounting mode: per_bundle | per_action | time_weighted
    bundle_budget_mode: str = "per_bundle"

    # ── Dual-channel bundler (TALP_BUNDLER_REDESIGN_SPEC) ────────────────────
    # Use Phase 1 + Phase 1b dual-channel bundler (False = legacy single-channel)
    use_dual_channel_bundler: bool = True
    # Leader posterior threshold for Phase 2 directional diversity guarantee
    leader_challenge_threshold: float = 0.3

    # ── Knowledge layer (EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN) ───────────
    # Paths to knowledge data files (None = layer disabled)
    dxs_common_json: str | None = None     # Layer 0: DiagRL-Corpus Guideline_common.json
    dxs_rare_json: str | None = None       # Layer 0: DiagRL-Corpus Guideline_rare.json
    primekg_csv: str | None = None         # Layer 1: PrimeKG kg.csv
    lr_cache_json: str | None = None       # Layer 2: unified_symptom_disease_cache.json
    doclogica_cache_json: str | None = None  # UMLS CUI bridging via docLogica umlsId fields
    # Enable knowledge injection into TALP and Annotator prompts
    enable_knowledge_injection: bool = False
    # Phase 3 RAG: LLM-based indirect reasoning chain discovery
    enable_chain_discoverer: bool = False
    # Layer 3a: StatPearls/Textbooks FAISS vector index directory
    rag_index_dir: str | None = None
    # Layer 3b: PubMed E-utilities (None = disabled; set NCBI API key for 10 req/s)
    pubmed_api_key: str | None = None
    enable_pubmed_fallback: bool = False
    # Exercise the RAG (Layer-3) fallback during LR injection/reconciliation.
    # When False the controller calls the retriever with fast=True, which skips
    # the loaded RAG index entirely (the historical default — RAG was loaded but
    # never used in the full pipeline). Set True to let cache-miss findings be
    # backfilled from StatPearls/textbook snippets (higher coverage, +latency).
    enable_lr_rag_fallback: bool = False
    # Max discriminator features per disease in TALP prompt injection
    max_discriminator_features: int = 8
    # Max lines of knowledge context injected into prompts
    max_knowledge_prompt_lines: int = 30

    # ── TALP discrimination production profile ───────────────────────────────
    # Production headline remains P5.  ``off`` is the explicit legacy escape
    # hatch; G2UR is research-only but may be selected explicitly in non-release
    # runs.  Missing P5 assets fail open so lightweight/test fixtures do not need
    # the full knowledge bundle.  G2UR validates its research manifest at startup.
    talp_disc_profile: str = "p5_headline"  # off | p5_headline | g2ur
    talp_disc_research_claims: str = (
        "data/cceg/unary_v1/claims.research_validated.jsonl"
    )
    talp_disc_research_manifest: str = (
        "data/cceg/unary_v1/p5kg_research_asset_manifest_v2.json"
    )
    talp_disc_p5_manifest: str = "data/eval/p5_external_asset_manifest.json"
    # Optional operational paths.  The cache is reserved for precompiled profile
    # assets; audit JSONL receives one bounded record per controller injection.
    talp_disc_cache_path: str | None = None
    talp_disc_audit_path: str | None = None
    talp_disc_verify_manifest_assets: bool = False

    # ── B3: Pathognomonic / diagnostic marker layer ────────────────────────
    pathognomonic_markers_json: str | None = None
    diagnostic_markers_json: str | None = None
    # 16.9.8 (T0): auto-generated ambiguity map for marker disambiguation.
    # None → DiagnosticMarkerIndex auto-discovers the default sibling JSON.
    auto_ambiguity_map_json: str | None = None

    # ── B1: Lab value normalization ────────────────────────────────────────
    lab_reference_ranges_json: str | None = None
    loinc2hpo_json: str | None = None
    unit_conversions_json: str | None = None

    # Mechanism/morphology → canonical-disease normalisation table. None →
    # auto-discovered next to lr_cache_json (mechanism_to_disease.json).
    mechanism_to_disease_json: str | None = None

    # Tier-2 cache of RAG-quantified LRs (separate from the curated primary
    # cache). None → auto-discovered next to lr_cache_json
    # (rag_lr_secondary_cache.json). Only used when enable_lr_rag_fallback.
    secondary_lr_cache_json: str | None = None

    # ── Structured age/sex → incidence PRIOR channel ──────────────────────────
    # Age & sex are epidemiology (they shift the PRIOR), not findings with an LR.
    # When enabled, branch priors are multiplied by a curated, bounded age/sex
    # incidence multiplier and renormalized. Default OFF.
    enable_age_prior: bool = False
    # Curated age/sex incidence table. None → auto-discovered next to
    # lr_cache_json (age_sex_incidence.json).
    age_sex_incidence_json: str | None = None

    # ── §21.8a: branch representative-disease KB lookup ───────────────────────
    # Broad family labels (e.g. "Myeloid Neoplasm with Increased Blasts") cannot
    # key the disease-keyed LR cache → 0 HIT. When enabled, the canonical
    # `representative_diseases` BranchCreator attached to each branch are ALSO
    # used as LR/KB query strings, so external evidence can fire on the correct
    # branch. Default OFF (ablation control).
    enable_representative_disease_lr: bool = False
    # ── §22.2 (A′): taxonomy-derived representative entities (NON-prompt) ──────
    # The corrected Fix A. Instead of asking BranchCreator to emit
    # `representative_diseases` (which hollows the branch LABEL into generic
    # organ buckets — §21.14.5), derive 1-4 canonical entities MECHANICALLY from
    # the (frozen) branch label via the disease-name resolver's family-expansion
    # taxonomy. The branch label and tree are untouched; the entities are an
    # invisible side-channel used ONLY for LR/KB lookup. When True, the
    # rep-disease consumption paths fire WITHOUT the prompt directive. Default OFF.
    enable_taxonomy_entities: bool = False
    # ── §21.8b: pathognomonic pivotal-clue surfacing + anti-anchoring ─────────
    # When enabled, inject a deterministic "pivotal evidence" hint into the
    # EvidenceAnnotator payload: the highest-LR+ (disease, finding) pairs found
    # this turn, so the annotator is nudged off the common/framed anchor toward
    # the branch a specific finding most strongly implicates. Default OFF.
    enable_anti_anchoring: bool = False

    # ── §23.14 (Mode A): KB-anchored, axis/level-aware branch generation ──────
    # When enabled, controller deterministically selects the L1 classification
    # axis from the root syndrome (syndrome_axis_map.json) and injects the MECE
    # single-axis L1 domain partition as `branch_knowledge.mandatory_coverage`
    # into the BranchCreator payload. The LLM must cover each domain (labels stay
    # at domain granularity); recalled disease entities are pushed DOWN to L2/L3
    # via the existing A′ representative-disease side-channel — never flattened
    # into L1 labels (prevents level collapse / hollowing). Default OFF: when
    # off, `_build_branch_candidates` returns None and the BranchCreator payload
    # is byte-identical to the legacy pure-LLM path (old path stays activatable).
    enable_branch_knowledge: bool = False
    # Curated syndrome→axis table; auto-discovered next to lr_cache_json
    # (syndrome_axis_map.json) when not set.
    syndrome_axis_map_json: str | None = None

    # ── Dual-entrance retrieval + case-report branch source ───────────────────
    # (GRAPHRAG_MULTISOURCE_FEASIBILITY_RESEARCH.md §4/§5) When enabled AND
    # enable_branch_knowledge is on, _build_branch_candidates augments the T1
    # marker/taxonomy nomination with a CaseReportBranchSource: a retrieval layer
    # over the case-report corpus (build_case_report_{corpus,index}.py) that
    # recalls the long-tail presentation→diagnosis mappings CPG under-recalls.
    # The recall uses a DUAL ENTRANCE — the syndrome frame (root.label) UNION the
    # RootSelector's concrete salient_findings — RRF-fused, so a rare gold
    # reachable only by a concrete sign (not the abstract frame) still enters the
    # candidate pool. Default OFF (byte-identical legacy branch anchoring).
    enable_case_report_branch_source: bool = False
    # TF-IDF index dir built by scripts/build_case_report_index.py. Auto-
    # discovered at data/corpus/case_report_index when unset.
    case_report_index_dir: str | None = None
    # Step-3 dual-entrance on the CPG MAIN path: when enabled AND
    # enable_branch_knowledge is on, _build_branch_candidates adds a
    # GuidelineBranchSource over rag_index_dir (StatPearls/Textbooks/CPG) recalled
    # via the SAME dual entrance (syndrome frame ∪ salient_findings), projected
    # onto the axis domains — strictly additive to the marker/taxonomy/case-report
    # candidates. Default OFF (byte-identical legacy branch anchoring).
    enable_cpg_branch_source: bool = False
    # 4th entrance: LLM-enumerated differential diagnoses. When enabled AND
    # enable_branch_knowledge is on AND an llm is wired, _build_branch_candidates
    # asks the LLM for the full DDx of {syndrome, salient_findings}, projects the
    # returned entities onto the axis domains, and merges them (strictly additive).
    # NOTE: this makes the branch-candidate step LLM-dependent (non-deterministic
    # at temperature>0); the call is issued at temperature 0 and fail-open.
    # Default OFF.
    enable_llm_ddx_branch_entrance: bool = False
    # D-fusion: RRF weight of the salient-finding (second) entrance relative to
    # the syndrome (first) entrance in GuidelineBranchSource/CaseReportBranchSource
    # recall. At 1.0 an equal-weight, broad salient finding can dilute the
    # syndrome-strong gold below the @20 cut (angiodysplasia 19→37, §RESIDUAL_MISS
    # §D-fusion). Empirically 0.5 is a clean win on the balanced 14/8
    # (COMMON cpg 8→9) + RareArena n=80 (37→38) with NO regressions on ANY set
    # (the idf salient-gate variant was net-negative and is NOT used). It is fully
    # deterministic and only takes effect when a dual-entrance source is enabled,
    # so 0.5 is the DEFAULT (the measured-best, zero-regression setting). Set 1.0
    # to restore the legacy equal-weight fusion.
    salient_finding_entrance_weight: float = 0.5
    # ── §31.13: KB-derived axis/domain partition (automation mode) ────────────
    # When True, BranchCreator's branch_knowledge is generated at runtime from
    # external KBs (SNOMED CT defining attributes for the axis partition + the
    # LR cache for symptom→disease recall and opposite-direction split), instead
    # of the hand-authored syndrome_axis_map.json. The generated block uses the
    # SAME schema, so mandatory_kb_branches / phase_subaxis / taxonomy_entities
    # all keep working unchanged. Requires enable_branch_knowledge. Default OFF
    # (hand map retained as the activatable legacy path / override seed).
    auto_axis_kb: bool = False

    # ── §25.2(#1): retrieval-priority fix — HPO-exact concept ≥ fuzzy token ────
    # When enabled, LRRetriever.lookup_fuzzy treats a same-HPO-concept cache
    # match (patient_hpo == cache_hpo) as a near-exact synonym (score 0.95) that
    # competes for best_entry, instead of a sub-threshold fallback shadowed by
    # any ≥0.35 token-Jaccard hit. Default OFF (legacy ordering retained).
    enable_hpo_exact_priority: bool = False
    # ── §25.2(#2): finding-match guards (precision) ───────────────────────────
    # Reject negation/laterality conflicts, raise the pure-token acceptance bar
    # to 0.5, and downweight the subset rule (0.6→0.5) in LRRetriever. Default
    # OFF (legacy permissive matching retained).
    enable_finding_match_guards: bool = False
    # ── §25.2(#3): confidence-gated cascade (cache↔RAG) ───────────────────────
    # A low-confidence cache hit (HPO subsumption / context-only) no longer
    # short-circuits RAG; RAG may override it with a higher-confidence numeric
    # LR. Default OFF (strict tier order: any cache hit blocks RAG).
    enable_confidence_gated_cascade: bool = False
    # ── §26.5(1): secondary-cache LR detox ────────────────────────────────────
    # Neutralise fabricated strong-exclusion LRs (demographic/normal-exam
    # findings dropped; default-specificity single-sided LRs clamped to [0.5,2]).
    # When on, the controller prefers the detoxed secondary cache file (if
    # present) and applies the same neutralisation at the live RAG path. Default
    # OFF (original noisy cache + raw quantification retained).
    enable_lr_detox: bool = False
    # ── §27.6(1): secondary-cache LR PURIFY (stricter than detox) ─────────────
    # Strip the fabricated numeric signal from ungrounded heuristic entries
    # (pct/phrase provenance + default specificity) → context-only, instead of
    # merely softening it. Keeps only genuinely grounded LRs (explicit Sn+Sp/LR
    # or a non-default specificity). When on, the controller prefers the
    # `*.clean.json` secondary cache and applies the same purify at the live RAG
    # path. Mutually exclusive with detox; clean wins if both set. Default OFF.
    enable_lr_clean: bool = False
    # ── §30: secondary (tier-2) RAG-LR cache kill-switch ──────────────────────
    # When False, the controller does NOT instantiate the tier-2 cache, so every
    # RAG-derived LR is re-computed from raw data each run (no read, no write).
    # Used to (a) validate code fixes that the persistent cache would otherwise
    # mask with stale cross-generation entries, and (b) avoid cross-process write
    # contention. The curated PRIMARY cache (lr_cache.json) is unaffected.
    enable_secondary_lr_cache: bool = True
    # §30: per-experiment cache isolation. When non-empty, the tier-2 cache file
    # is namespaced (`.ns_<arm>.json`) so each experiment ARM is independent and
    # only reps of the SAME arm share it. Empty (production) → the single shared
    # file (concurrent writes kept lossless by the flock-merge in
    # SecondaryLRCache). Note: a namespaced (writable) cache also takes
    # precedence over the read-only offline .clean/.detox artifacts.
    secondary_lr_cache_namespace: str = ""
    # ── §26.5(3): mandatory KB-anchored branches ──────────────────────────────
    # Promote the branch_knowledge `mandatory_coverage` domains from advisory to
    # MANDATORY: any L1 domain the LLM omits is injected as a deterministic
    # branch (carrying the domain's candidate entities), so the gold entity
    # always has a reachable node. Requires enable_branch_knowledge. Default OFF.
    enable_mandatory_kb_branches: bool = False
    # ── §26.5(4): phase / opposite-direction sub-axis split ───────────────────
    # Expand a syndrome-axis domain that carries `split_variants` into its
    # variants, separating sub-families whose key-finding LR direction opposes
    # the parent (e.g. chronic-phase MPN vs blast-bearing: "35% blasts" is FOR
    # one and AGAINST the other). Requires enable_branch_knowledge. Default OFF.
    enable_phase_subaxis: bool = False
    # ── §31.13: automated KB-derived axis map (replaces hand syndrome_axis_map) ─
    # When True, _load_syndrome_axis_map returns a KBAxisMap (knowledge/auto_axis)
    # that derives the syndrome→axis→MECE-domain partition from SNOMED `is_a`
    # ancestor clustering + lr_cache recall at runtime, instead of loading the
    # hand-curated syndrome_axis_map.json. Emits the identical branch_knowledge
    # contract, so all downstream options (mandatory/phase/taxonomy) are unchanged.
    # Default OFF (keeps the hand-map path). Requires the snomed_* artifacts.
    auto_axis_kb: bool = False

    # ── §32: KB recall-hints mode (DECOUPLE partition from recall) ────────────
    # The legacy branch-knowledge flow COUPLES two separable concerns: it lets an
    # axis_map (hand-curated syndrome_axis_map.json OR the KB KBAxisMap) DEFINE the
    # L1 MECE partition (mandatory_coverage → the LLM is ordered to emit one branch
    # per domain) AND route every recalled disease onto those domains via
    # member_keyword substring projection. Two failures follow (§RESIDUAL_MISS §12/13):
    #   (1) the partition is only as good as the axis_map — the hand map is
    #       unscalable, and KBAxisMap's SNOMED-taxonomy grouping is low quality
    #       (off-topic domains; 8/9 on the 8/14 set vs 9/9 for the free-LLM single-
    #       axis prompt). Anchoring the LLM to a bad partition HURTS.
    #   (2) member_keyword projection DROPS any recalled long-tail disease that
    #       doesn't substring-match a seed domain — discarding most of the very
    #       recall the entrances exist to add (RareArena proves that recall is good).
    # This mode DECOUPLES them: the LLM owns the single-axis MECE partition (the
    # proven 9/9 path — NO mandatory_coverage injected, NO axis_map needed), and the
    # 4-entrance union (case-report ∪ CPG ∪ LLM-DDx) recall is passed as a FLAT,
    # ranked ``candidate_diseases`` HINT list (not partitioned, not mandatory). The
    # LLM is told to ensure its own partition has a reachable home for the plausible
    # hints. KB thus becomes STRICTLY ADDITIVE (can only enrich recall, never impose
    # a partition or drop the LLM's) and requires ZERO hand curation. Requires
    # enable_branch_knowledge + ≥1 entrance flag. Default OFF (legacy coupled path
    # retained). Supersedes auto_axis_kb / enable_mandatory_kb_branches when set.
    branch_kb_recall_hints: bool = False
    # Max flat candidate-disease hints injected in recall-hints mode.
    branch_recall_hints_cap: int = 24
    # §32 Phase-B: recall-driven MECE gap repair. After the LLM builds its
    # partition in recall-hints mode, an LLM assignment pass checks whether each
    # TOP recalled candidate has a home family; if a high-rank candidate fits
    # NONE, ONE corrective BranchCreator re-call widens/adds a family so it is
    # reachable (single-axis MECE preserved, repair accepted only if it does not
    # shrink the family count). Keyed on recalled ENTITIES (not KB domains), so it
    # cannot impose a bad partition. Requires branch_kb_recall_hints. Default OFF.
    branch_recall_gap_fill: bool = False

    # ── L2 branch recall generation A/B core ─────────────────────────────────
    # ``none`` preserves the historical SubBranchCreator call byte-for-byte.
    # ``per_parent`` (A) performs fresh multi-source recall for each L1 parent.
    # ``reuse_l1`` (B) maps one pre-frozen, case-level recall asset to all L1
    # parents once and never performs parent-level retrieval.
    l2_branch_generation_mode: str = "none"  # none | per_parent | reuse_l1
    # Maximum recalled disease entities handed to the L2 creator per parent.
    l2_recall_candidate_budget: int = 24
    # Per-source retrieval breadth (number of snippets/hits considered).
    l2_recall_snippet_budget: int = 12
    # Shared A/B candidate-to-child coverage assignment + one-shot repair.
    l2_recall_gap_fill: bool = False

    # §13 discrimination gate for the per-turn posterior update. When ON, a turn
    # whose evidence is ENTIRELY non-discriminative (only neutral/weak labels, or
    # all numeric LRs within [1/1.5, 1.5]) FREEZES the posteriors instead of
    # renormalizing. Root cause it addresses: softmax-style renormalization lets a
    # lone weak_for on a distractor bleed a broad correct family down every turn
    # even when nothing argues against it → the correct family's posterior decays
    # monotonically ("evidence collapse", §13). Freezing mild turns stops the
    # dilution while leaving every genuinely discriminative turn fully intact.
    # Default OFF (byte-identical legacy update).
    enable_discrimination_gate: bool = False

    # ── §31.13.18: A∪C union axis map (LLM-built branch_knowledge ∪ curated
    #               mandatory-floor seeds) ────────────────────────────────────
    # When True, _init_syndrome_axis_map returns a UnionAxisMap. Syndrome
    # detection reuses the hand map's keyword matcher (the proven, small
    # recognition layer); the L1 axis/domain PARTITION is then taken from the
    # UNION of:
    #   A) LLM-built branch_knowledge entries cached in `llm_axis_cache_json`
    #      (generated offline by GuidelineBranchSource.build_branch_knowledge_llm;
    #       bypasses the SNOMED is_a partition wall, covers mechanism/anatomy-
    #       phrased golds SNOMED cannot resolve), and
    #   C) curated mandatory-floor seeds in `override_seeds_json` (a few domains
    #      per hard syndrome, pinning the standard differential).
    # Falls back to the hand map's own entry when neither A nor C has the
    # syndrome, so coverage NEVER regresses below the hand map. Emits the SAME
    # entry schema, so mandatory/phase/taxonomy downstream are unchanged.
    # Requires enable_branch_knowledge. Default OFF (legacy path retained).
    union_axis_ac: bool = False
    # A-source: offline LLM-axis cache (auto_axis_cache.json). Auto-discovered
    # next to the LR cache when unset.
    llm_axis_cache_json: str | None = None
    # C-source: curated override seeds (syndrome_override_seeds.json). Auto-
    # discovered next to the LR cache when unset.
    override_seeds_json: str | None = None
    # When True AND a syndrome is missing from the A-cache, generate its
    # branch_knowledge LIVE via the LLM at match() time (and write through to
    # the cache). Default OFF: the hot path stays deterministic + low-latency,
    # relying on the offline cache ∪ curated seeds ∪ hand fallback.
    branch_llm_axis_live: bool = False

    # ── SNOMED CT layer (synonym bridging + syndrome-chain relations) ─────────
    # Artifacts built by scripts/build_snomed_knowledge.py. None = layer off.
    snomed_concepts_json: str | None = None
    snomed_term_index_json: str | None = None
    snomed_relations_json: str | None = None
    # Use SNOMED synonyms to widen disease/finding name matching in the retriever.
    enable_snomed_synonym_bridge: bool = True

    # ── F1: knowledge-grounded probability update ─────────────────────────────
    # Reconcile the EvidenceAnnotator's qualitative `branch_effects` against the
    # knowledge base: when the KB has a HIGH-confidence directional signal
    # (pathognomonic marker, pathognomonic exclusion, or a strong EBM LR band)
    # that contradicts the LLM's sign, override the LLM sign. Conservative: only
    # high-confidence KB hits override (noisy fuzzy LR does NOT — see Bayesian
    # elicitation caveat that retrieval can otherwise corrupt good priors).
    enable_kb_direction_reconciliation: bool = True
    # LR+ at/above which a finding is treated as (near-)pathognomonic → the
    # supported branch's posterior is floored (recovers planned §11.9.5.4).
    pathognomonic_lr_floor_threshold: float = 50.0
    pathognomonic_posterior_floor: float = 0.70
    # LR+ at/above which the KB forces at least `moderate_for` (strong inclusion).
    strong_inclusion_lr_threshold: float = 10.0
    # LR+ at/below which the KB forces `against` (strong exclusion).
    strong_exclusion_lr_threshold: float = 0.2
    # Whether RAG-derived LRs (confidence rag_qualitative/rag_extracted) may
    # override the LLM's qualitative direction. Default OFF: these are
    # frequency-language estimates with a guessed specificity and were observed
    # to spuriously flip the annotator. They still appear in the prompt.
    rag_lr_can_override_direction: bool = False

    # ── LR- rule-out channel (normal/absent findings) ─────────────────────────
    # When a lab/vital value is NORMAL, treat the abnormal phenotype(s) it
    # negates as ABSENT and apply LR-=(1-Sn)/Sp against diseases that (near-)
    # always produce that abnormality (EXTERNAL_KNOWLEDGE §12.8, B1 §7).
    # Default OFF (conservative; enable after A/B). To avoid over-penalising on
    # weakly-sensitive findings, only fire when the negated finding's
    # sensitivity for the disease is high and the resulting LR- is meaningfully
    # below 1.
    enable_normal_value_ruleout: bool = False
    # Minimum sensitivity (Sn) of the negated finding for the disease required
    # before a normal value is allowed to push the disease down via LR-.
    ruleout_min_sensitivity: float = 0.8
    # LR- at/below which a normal result is treated as a meaningful rule-out.
    ruleout_lr_negative_threshold: float = 0.5
    # P1 (Sp gate + direction consistency): a reliable rule-out needs a credible
    # SPECIFICITY (SnNout still depends on Sp). When >0, skip rule-out entries
    # whose specificity is missing or below this floor. Also, never apply LR-
    # to a branch the PRESENT-finding path already supported this turn
    # (contradictory same-turn signals are dropped).
    ruleout_min_specificity: float = 0.0
    # P2 (present-path-first): only apply LR- rule-out to branches for which the
    # present-finding path produced NO signal this turn (effect == neutral).
    ruleout_require_present_path_silent: bool = False

    # ── F2: numeric Bayesian LR probability update ────────────────────────────
    # When per-branch numeric LRs are available (from KB reconciliation), update
    # posteriors via Bayes' rule (odds × LR) instead of ordinal weight bands.
    enable_numeric_lr_update: bool = True

    # ── F3: AnswerMapper faithfulness ─────────────────────────────────────────
    # Force final_answer == argmax(answer_option_mapping) (self-consistency) and
    # require leaf-level mapping (enforced in prompt + post-hoc argmax).
    enforce_answer_mapper_consistency: bool = True

    # ── F4: calibrated, separation-aware commit ───────────────────────────────
    # Do not commit while the leader leaf is not separated from the runner-up by
    # this margin (prevents committing on a near-flat distribution, e.g. case 22).
    min_leader_margin_to_commit: float = 0.15
    # Post-hoc temperature applied to the AnswerMapper option distribution to
    # counter LLM overconfidence (>1 softens; 1.0 = off).
    answer_mapping_softmax_temperature: float = 1.0
